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
        self._rid_offsets: dict[int, tuple[int, int]] | None = None
        self._ids_by_type: dict[int, tuple[int, ...]] | None = None
        self._metadata_cache: Path | None = None

    def _source_failure(self, message: str, exc: BaseException | None = None):
        detail = f"{message}: {self.path}"
        if self.required:
            error = QuestSourceError(detail)
            if exc is not None:
                raise error from exc
            raise error
        LOGGER.warning("Source JSON Quêtes optionnelle ignorée: %s", detail)
        self._offsets = {}

    @staticmethod
    def _valid_span_map(value, source_size: int) -> bool:
        return isinstance(value, dict) and all(
            isinstance(span, list) and len(span) == 2
            and all(isinstance(item, int) for item in span)
            and 0 <= span[0] < span[1] <= source_size
            for span in value.values()
        )

    @staticmethod
    def _valid_type_map(value) -> bool:
        return isinstance(value, dict) and all(
            isinstance(ids, list) and all(isinstance(item, int) for item in ids)
            for ids in value.values()
        )

    def _load_doduda_metadata(self, path: Path, source_size: int) -> bool:
        if not self.doduda or not path.exists():
            return False
        try:
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                payload = json.load(stream)
        except (ValueError, OSError):
            return False
        if not isinstance(payload, dict):
            return False
        rid_offsets = payload.get("rid_offsets")
        ids_by_type = payload.get("ids_by_type")
        if not self._valid_span_map(rid_offsets, source_size) or not self._valid_type_map(ids_by_type):
            return False
        self._rid_offsets = {
            int(key): tuple(span)
            for key, span in rid_offsets.items()
        }
        self._ids_by_type = {
            int(key): tuple(int(item) for item in ids)
            for key, ids in ids_by_type.items()
        }
        return True

    def _write_doduda_metadata(
        self,
        path: Path,
        rid_offsets: dict[str, tuple[int, int]],
        ids_by_type: dict[str, list[int]],
    ) -> None:
        if not self.doduda or self.path.name != "items.json":
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as temp:
            temp_path = Path(temp.name)
        try:
            with gzip.open(temp_path, "wt", encoding="utf-8", compresslevel=1) as stream:
                stream.write(
                    json.dumps(
                        {
                            "rid_offsets": {
                                str(key): [int(span[0]), int(span[1])]
                                for key, span in rid_offsets.items()
                            },
                            "ids_by_type": {
                                str(key): [int(item) for item in ids]
                                for key, ids in ids_by_type.items()
                            },
                        },
                        separators=(",", ":"),
                    )
                )
            temp_path.replace(path)
        finally:
            temp_path.unlink(missing_ok=True)

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
        metadata_cache = cache_root / f"source_{digest}_doduda_meta.json.gz"
        self._metadata_cache = metadata_cache
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
        metadata: dict[str, object] = {}
        capture_doduda_metadata = self.doduda and path.name == "items.json"
        if offsets is None:
            try:
                offsets = self._build_offsets(field, metadata=metadata)
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
            if capture_doduda_metadata:
                self._write_doduda_metadata(
                    metadata_cache,
                    metadata.get("rid_offsets", {}),
                    metadata.get("ids_by_type", {}),
                )
        self._offsets = {int(key) if self.doduda else key: tuple(span) for key, span in offsets.items()}
        if capture_doduda_metadata:
            if not self._load_doduda_metadata(metadata_cache, stat.st_size):
                self._rid_offsets = {}
                self._ids_by_type = {}
        elif self.doduda:
            self._rid_offsets = {}
            self._ids_by_type = {}

    def _build_offsets(self, field, *, metadata: dict[str, object] | None = None):
        """Build byte spans without decoding the monolithic source as one string."""

        field_marker = json.dumps(str(field), ensure_ascii=False).encode("utf-8")
        field_pattern = re.compile(re.escape(field_marker) + rb"\s*:\s*([\[{])")
        chunk_size = 256 * 1024
        overlap_size = 1024
        container_start: int | None = None
        container_open: int | None = None

        with self.path.open("rb") as stream:
            tail = b""
            while True:
                chunk = stream.read(chunk_size)
                if not chunk:
                    break
                data = tail + chunk
                base = stream.tell() - len(chunk) - len(tail)
                match = field_pattern.search(data)
                if match is not None:
                    container_open = match.group(1)[0]
                    container_start = base + match.end()
                    break
                tail = data[-overlap_size:]

        if container_start is None or container_open is None:
            self._source_failure(f"champ requis absent ({field})")
            return {}

        class _Reader:
            def __init__(self, path: Path, position: int) -> None:
                self.stream = path.open("rb")
                self.stream.seek(position)
                self.buffer = b""
                self.index = 0
                self.base = position

            def close(self) -> None:
                self.stream.close()

            def _fill(self) -> bool:
                if self.index < len(self.buffer):
                    return True
                self.base += len(self.buffer)
                self.buffer = self.stream.read(64 * 1024)
                self.index = 0
                return bool(self.buffer)

            def tell(self) -> int:
                return self.base + self.index

            def peek(self) -> int | None:
                return self.buffer[self.index] if self._fill() else None

            def get(self) -> int | None:
                value = self.peek()
                if value is not None:
                    self.index += 1
                return value

        whitespace = {9, 10, 13, 32}
        closing = ord("}") if container_open == ord("{") else ord("]")
        reader = _Reader(self.path, container_start)
        values = self.path.open("rb")

        def read_span(start_pos: int, end_pos: int) -> bytes:
            values.seek(start_pos)
            return values.read(max(0, end_pos - start_pos))

        def skip_space() -> None:
            while reader.peek() in whitespace:
                reader.get()

        def read_string_span() -> tuple[int, int]:
            start_pos = reader.tell()
            if reader.get() != ord('"'):
                raise ValueError("Expected JSON string")
            escaped = False
            while True:
                value = reader.get()
                if value is None:
                    raise ValueError("Unterminated JSON string")
                if escaped:
                    escaped = False
                    continue
                if value == ord("\\"):
                    escaped = True
                    continue
                if value == ord('"'):
                    return start_pos, reader.tell()

        def read_value_span() -> tuple[int, int]:
            skip_space()
            start_pos = reader.tell()
            first = reader.peek()
            if first is None:
                raise ValueError("Missing JSON value")

            if first == ord('"'):
                return read_string_span()

            if first in {ord("{"), ord("[")}:
                stack: list[int] = []
                in_string = False
                escaped = False
                while True:
                    value = reader.get()
                    if value is None:
                        raise ValueError("Unterminated JSON value")
                    if in_string:
                        if escaped:
                            escaped = False
                        elif value == ord("\\"):
                            escaped = True
                        elif value == ord('"'):
                            in_string = False
                        continue
                    if value == ord('"'):
                        in_string = True
                        continue
                    if value in {ord("{"), ord("[")}:
                        stack.append(value)
                        continue
                    if value in {ord("}"), ord("]")}:
                        if not stack:
                            raise ValueError("Unexpected JSON closing delimiter")
                        opened = stack.pop()
                        if (
                            (opened == ord("{") and value != ord("}"))
                            or (opened == ord("[") and value != ord("]"))
                        ):
                            raise ValueError("Mismatched JSON delimiters")
                        if not stack:
                            return start_pos, reader.tell()

            last_non_space = start_pos
            while True:
                value = reader.peek()
                if value is None or value in {ord(","), closing}:
                    return start_pos, last_non_space
                value = reader.get()
                if value not in whitespace:
                    last_non_space = reader.tell()

        offsets: dict[str, tuple[int, int]] = {}
        rid_offsets: dict[str, tuple[int, int]] = {}
        ids_by_type: dict[str, list[int]] = defaultdict(list)
        try:
            while True:
                skip_space()
                value = reader.peek()
                if value is None or value == closing:
                    break
                if value == ord(","):
                    reader.get()
                    continue

                key = None
                if not self.doduda:
                    key_start, key_end = read_string_span()
                    key = json.loads(read_span(key_start, key_end))
                    skip_space()
                    if reader.get() != ord(":"):
                        raise ValueError("Missing JSON member separator")
                    skip_space()

                value_start, value_end = read_value_span()
                if self.doduda:
                    raw_value = json.loads(read_span(value_start, value_end))
                    row = raw_value.get("data") if isinstance(raw_value, dict) else None
                    key = row.get("id") if isinstance(row, dict) else None
                    if metadata is not None and self.path.name == "items.json":
                        rid = raw_value.get("rid") if isinstance(raw_value, dict) else None
                        if rid is not None:
                            rid_offsets[str(rid)] = (value_start, value_end)
                        type_id = row.get("typeId") if isinstance(row, dict) else None
                        if key is not None and type_id is not None:
                            try:
                                ids_by_type[str(int(type_id))].append(int(key))
                            except (TypeError, ValueError):
                                pass
                if key is not None:
                    offsets[str(key)] = (value_start, value_end)

                skip_space()
                delimiter = reader.peek()
                if delimiter == ord(","):
                    reader.get()
                elif delimiter == closing:
                    break
                elif delimiter is not None:
                    raise ValueError("Missing JSON member delimiter")
        finally:
            reader.close()
            values.close()
        if metadata is not None and self.doduda:
            metadata["rid_offsets"] = rid_offsets
            metadata["ids_by_type"] = dict(ids_by_type)
        return offsets

    def _ensure_doduda_metadata(self) -> None:
        self._ensure()
        if not self.doduda:
            return
        if self._rid_offsets or self._ids_by_type:
            return
        try:
            stat = self.path.stat()
        except OSError:
            return
        metadata: dict[str, object] = {}
        # Legacy offset caches predate the metadata sidecar. Upgrade them once,
        # still with one bounded source scan, then reuse the sidecar thereafter.
        self._build_offsets(self._field, metadata=metadata)
        rid_offsets = metadata.get("rid_offsets", {})
        ids_by_type = metadata.get("ids_by_type", {})
        if self._metadata_cache is not None:
            self._write_doduda_metadata(self._metadata_cache, rid_offsets, ids_by_type)
            self._load_doduda_metadata(self._metadata_cache, stat.st_size)

    def ids_for_type(self, type_id: int) -> tuple[int, ...]:
        self._ensure_doduda_metadata()
        return tuple((self._ids_by_type or {}).get(int(type_id), ()))

    def data_by_rid(self, rid: int):
        self._ensure_doduda_metadata()
        span = (self._rid_offsets or {}).get(int(rid))
        if span is None:
            raise KeyError(rid)
        start, end = span
        with self.path.open("rb") as stream:
            stream.seek(start)
            value = json.loads(stream.read(end - start))
        if not isinstance(value, dict):
            raise KeyError(rid)
        data = value.get("data")
        if not isinstance(data, dict):
            raise KeyError(rid)
        return data

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

    def row_ids_for_type(self, path, type_id):
        return self.rows(path).ids_for_type(int(type_id))

    def row_by_rid(self, path, rid):
        return self.rows(path).data_by_rid(int(rid))

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
