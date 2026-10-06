"""Read individual records from Atlas' monolithic JSON sources.

Only byte offsets are cached. JSON values are decoded by the standard library
on demand; no executable serialization and no persistent user data are used.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
import tempfile
import weakref
from collections import OrderedDict, defaultdict
from collections.abc import Mapping
from pathlib import Path
from threading import RLock

from app.constants import LOGGER

_SPACE = re.compile(r'\s*')
_OPTIONAL_SOURCE_FIELDS = frozenset({("quests_enriched.json", "quests")})


class QuestSourceError(RuntimeError):
    """Raised when a required quest business source cannot be read safely."""

_JSON_OBJECT_MEMBER_RE = re.compile(
    rb'(?<!\\)"((?:\\.|[^"\\])*)"\s*:\s*'
)


def read_selected_json_object_values(
    path: Path,
    field: str,
    selected_keys: set[str] | frozenset[str],
    *,
    required: bool = True,
) -> dict[str, object]:
    """Read selected members from a large JSON object with bounded memory.

    The source is scanned in fixed-size chunks and only requested values are
    decoded. This prevents compact-cache workers from retaining the monolithic
    localization JSON or a full offset dictionary.
    """

    wanted = {str(key) for key in selected_keys}
    if not wanted:
        return {}
    path = Path(path)
    if not path.is_file():
        if required:
            raise QuestSourceError(f"fichier indisponible: {path}")
        return {}

    field_marker = json.dumps(str(field), ensure_ascii=False).encode("utf-8")
    field_pattern = re.compile(re.escape(field_marker) + rb"\s*:\s*\{")
    chunk_size = 256 * 1024
    overlap_size = 1024

    with path.open("rb") as scan, path.open("rb") as values:
        tail = b""
        container_start: int | None = None
        while True:
            chunk = scan.read(chunk_size)
            if not chunk:
                break
            data = tail + chunk
            base = scan.tell() - len(chunk) - len(tail)
            match = field_pattern.search(data)
            if match is not None:
                container_start = base + match.end()
                break
            tail = data[-overlap_size:]

        if container_start is None:
            if required:
                raise QuestSourceError(f"champ requis absent ({field}): {path}")
            return {}

        result: dict[str, object] = {}
        scan.seek(container_start)
        tail = b""
        emit_from = container_start
        decoder = json.JSONDecoder()

        while wanted:
            chunk = scan.read(chunk_size)
            eof = not chunk
            data = tail + chunk
            if not data:
                break
            base = scan.tell() - len(chunk) - len(tail)
            safe_limit = len(data) if eof else max(0, len(data) - overlap_size)

            for match in _JSON_OBJECT_MEMBER_RE.finditer(data):
                absolute_match = base + match.start()
                if absolute_match < emit_from:
                    continue
                if not eof and match.start() >= safe_limit:
                    break
                try:
                    key = str(json.loads(b'"' + match.group(1) + b'"'))
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                if key not in wanted:
                    continue

                value_start = base + match.end()
                values.seek(value_start)
                payload = bytearray()
                parsed = False
                for _ in range(64):
                    part = values.read(64 * 1024)
                    if not part:
                        break
                    payload.extend(part)
                    try:
                        text = bytes(payload).decode("utf-8")
                        value, _end = decoder.raw_decode(text.lstrip())
                    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
                        continue
                    result[key] = value
                    wanted.remove(key)
                    parsed = True
                    break
                if not parsed and required:
                    raise QuestSourceError(
                        f"valeur JSON illisible pour {key}: {path}"
                    )
                if not wanted:
                    break

            if eof:
                break
            emit_from = base + safe_limit
            tail = data[safe_limit:]

    return result


class SelectedJsonValueMapping(Mapping):
    """Small read-only mapping backed by a bounded scan of one JSON object."""

    def __init__(
        self,
        path: Path,
        field: str,
        selected_keys: set[str] | frozenset[str],
        *,
        required: bool = True,
    ) -> None:
        self._values = read_selected_json_object_values(
            path,
            field,
            selected_keys,
            required=required,
        )

    def __getitem__(self, key):
        return self._values[str(key)]

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def close(self) -> None:
        self._values.clear()



def build_image_index(images_root: Path) -> dict[str, str]:
    """Index documentary images without importing the Quest catalogue."""

    index: dict[str, str] = {}
    image_suffixes = {".png", ".jpg", ".jpeg", ".webp"}
    folders = (
        images_root / "items",
        images_root / "resources",
        images_root / "misc",
        images_root / "archive",
    )
    for folder in folders:
        if not folder.exists():
            continue
        try:
            paths = sorted(
                (path for path in folder.rglob("*") if path.suffix.casefold() in image_suffixes),
                key=lambda path: ("archive" in path.parts, len(path.parts), str(path).casefold()),
            )
        except OSError:
            continue
        for path in paths:
            index.setdefault(path.stem, str(path))
    return index


class JsonSourceMapping(Mapping):
    def __init__(self, path: Path, cache_root: Path, field: str, *, doduda=False, required=True):
        self.path, self.doduda, self.required = path, doduda, bool(required)
        self._lock = RLock()
        self._cache = OrderedDict()
        self._offsets = None
        self._cache_root, self._field = cache_root, field
        self._stream = None

    def _source_failure(self, message: str, exc: BaseException | None = None):
        detail = f"{message}: {self.path}"
        if self.required:
            error = QuestSourceError(detail)
            if exc is not None:
                raise error from exc
            raise error
        LOGGER.warning("Source JSON Quêtes optionnelle ignorée: %s", detail)
        self._offsets = {}

    def _ensure(self):
        if self._offsets is not None:
            return
        path, cache_root, field = self.path, self._cache_root, self._field
        try:
            stat = path.stat()
        except OSError as exc:
            self._source_failure("fichier indisponible", exc)
            return
        self._stamp = (stat.st_mtime_ns, stat.st_size)
        signature = [str(path.resolve()), *self._stamp, field, self.doduda, 1]
        digest = hashlib.sha256(json.dumps(signature).encode()).hexdigest()
        cache = cache_root / f"source_{digest}.json.gz"
        offsets = None
        if cache.exists():
            try:
                with gzip.open(cache, 'rt', encoding='utf-8') as stream:
                    offsets = json.load(stream)
                valid_cache = isinstance(offsets, dict) and all(
                    isinstance(span, list) and len(span) == 2
                    and all(isinstance(value, int) for value in span)
                    and 0 <= span[0] < span[1] <= stat.st_size
                    for span in offsets.values()
                )
                if not valid_cache:
                    LOGGER.warning("Cache d'index Quêtes invalide, reconstruction: %s", cache)
                    offsets = None
            except (ValueError, OSError) as exc:
                LOGGER.warning(
                    "Cache d'index Quêtes illisible, reconstruction: %s (%s)",
                    cache,
                    exc,
                )
                offsets = None
        if offsets is None:
            try:
                offsets = self._build_offsets(field)
            except (OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
                self._source_failure("lecture/parsing impossible", exc)
                return
            cache_root.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=cache_root, suffix='.tmp', delete=False) as temp:
                temp_path = Path(temp.name)
            try:
                with gzip.open(temp_path, 'wt', encoding='utf-8', compresslevel=1) as stream:
                    stream.write(json.dumps(offsets, separators=(',', ':')))
                temp_path.replace(cache)
            finally:
                temp_path.unlink(missing_ok=True)
        self._offsets = {int(key) if self.doduda else key: tuple(span) for key, span in offsets.items()}

    def _build_offsets(self, field):
        # Decode one raw JSON member at a time with CPython's JSON parser.
        # The source text is temporary; only byte spans survive this pass.
        # Never construct the full source dictionary or rich quest records.
        data = self.path.read_bytes().decode('utf-8')
        marker = re.search(r'"' + re.escape(field) + r'"\s*:\s*([\[{])', data)
        if marker is None:
            self._source_failure(f"champ requis absent ({field})")
            return {}
        decoder = json.JSONDecoder()
        cursor = marker.end()
        byte_cursor = len(data[:cursor].encode('utf-8'))
        previous = cursor
        offsets = {}
        end = ']' if self.doduda else '}'
        while True:
            cursor = _SPACE.match(data, cursor).end()
            if data[cursor:cursor + 1] == end:
                break
            if not self.doduda:
                key, cursor = decoder.raw_decode(data, cursor)
                cursor = _SPACE.match(data, cursor).end()
                if data[cursor:cursor + 1] != ':':
                    raise ValueError("Missing JSON member separator")
                cursor = _SPACE.match(data, cursor + 1).end()
            byte_cursor += len(data[previous:cursor].encode('utf-8'))
            start = byte_cursor
            value, value_end = decoder.raw_decode(data, cursor)
            byte_cursor += len(data[cursor:value_end].encode('utf-8'))
            if self.doduda:
                row = value.get('data') if isinstance(value, dict) else None
                key = row.get('id') if isinstance(row, dict) else None
            if key is not None:
                offsets[str(key)] = (start, byte_cursor)
            previous = value_end
            cursor = _SPACE.match(data, value_end).end()
            if data[cursor:cursor + 1] == ',':
                cursor += 1
            elif data[cursor:cursor + 1] != end:
                raise ValueError("Missing JSON member delimiter")
        return offsets

    def __getitem__(self, key):
        with self._lock:
            self._ensure()
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            start, end = self._offsets[key]
            if self._stream is None:
                self._stream = self.path.open('rb')
                self._close_stream = weakref.finalize(self, self._stream.close)
            self._stream.seek(start)
            value = json.loads(self._stream.read(end - start))
            if self.doduda:
                value = value['data']
            self._cache[key] = value
            while len(self._cache) > 128:
                self._cache.popitem(last=False)
            return value

    def __iter__(self):
        self._ensure()
        return iter(self._offsets)

    def __len__(self):
        self._ensure()
        return len(self._offsets)

    def close(self):
        with self._lock:
            if self._stream is not None:
                self._close_stream()
                self._stream = None


class QuestSources:
    def __init__(self, cache_root):
        self.cache_root = cache_root
        self._mappings = {}
        self._objectives_by_step = None
        self._image_index = None
        self.context = {}

    def mapping(self, path, field, *, doduda=False, required=None):
        path = Path(path)
        if required is None:
            required = (path.name, str(field)) not in _OPTIONAL_SOURCE_FIELDS
        key = (path, field, doduda, bool(required))
        if key not in self._mappings:
            self._mappings[key] = JsonSourceMapping(
                path,
                self.cache_root,
                field,
                doduda=doduda,
                required=required,
            )
        return self._mappings[key]

    def rows(self, path):
        return self.mapping(path, 'RefIds', doduda=True, required=True)

    def objectives_for_steps(self, path, step_ids):
        rows = self.rows(path)
        if self._objectives_by_step is None:
            self._objectives_by_step = defaultdict(list)
            for key, row in rows.items():
                self._objectives_by_step[row.get('stepId')].append(key)
        return (rows[key] for step in step_ids for key in self._objectives_by_step.get(step, ()))

    def image_index(self, root):
        if self._image_index is None:
            self._image_index = build_image_index(root)
        return self._image_index

    def close(self):
        for mapping in self._mappings.values():
            mapping.close()
