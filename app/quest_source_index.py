"""Read individual records from Atlas' monolithic JSON sources.

Only byte offsets are cached. JSON values are decoded by the standard library
on demand; no executable serialization and no persistent user data are used.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import mmap
import tempfile
import weakref
from collections import OrderedDict, defaultdict
from collections.abc import Mapping
from pathlib import Path
from threading import RLock

from app.constants import LOGGER

_OPTIONAL_SOURCE_FIELDS = frozenset({("quests_enriched.json", "quests")})
_JSON_WS = frozenset(b" \t\r\n")


class QuestSourceError(RuntimeError):
    """Raised when a required quest business source cannot be read safely."""


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


def _skip_ws(source: mmap.mmap, cursor: int) -> int:
    size = len(source)
    while cursor < size and source[cursor] in _JSON_WS:
        cursor += 1
    return cursor


def _scan_string_end(source: mmap.mmap, cursor: int) -> int:
    if cursor >= len(source) or source[cursor] != 0x22:  # '"'
        raise ValueError("JSON string expected")
    cursor += 1
    escaped = False
    size = len(source)
    while cursor < size:
        byte = source[cursor]
        cursor += 1
        if escaped:
            escaped = False
            continue
        if byte == 0x5C:  # '\\'
            escaped = True
            continue
        if byte == 0x22:
            return cursor
    raise ValueError("Unterminated JSON string")


def _scan_value_end(source: mmap.mmap, cursor: int) -> int:
    """Return the byte offset immediately after one JSON value.

    The scanner never decodes the complete source. Strings are skipped with
    escape awareness and nested arrays/objects are tracked directly on the
    memory map, so first-run indexing has constant source-memory overhead.
    """

    cursor = _skip_ws(source, cursor)
    size = len(source)
    if cursor >= size:
        raise ValueError("JSON value expected")

    first = source[cursor]
    if first == 0x22:
        return _scan_string_end(source, cursor)

    if first in (0x7B, 0x5B):  # { [
        stack = [0x7D if first == 0x7B else 0x5D]
        cursor += 1
        in_string = False
        escaped = False
        while cursor < size:
            byte = source[cursor]
            cursor += 1
            if in_string:
                if escaped:
                    escaped = False
                elif byte == 0x5C:
                    escaped = True
                elif byte == 0x22:
                    in_string = False
                continue
            if byte == 0x22:
                in_string = True
            elif byte == 0x7B:
                stack.append(0x7D)
            elif byte == 0x5B:
                stack.append(0x5D)
            elif byte in (0x7D, 0x5D):
                if not stack or byte != stack[-1]:
                    raise ValueError("Mismatched JSON container")
                stack.pop()
                if not stack:
                    return cursor
        raise ValueError("Unterminated JSON container")

    while cursor < size and source[cursor] not in b",]} \t\r\n":
        cursor += 1
    return cursor


def _decode_json_string(source: mmap.mmap, start: int, end: int) -> str:
    value = json.loads(source[start:end])
    if not isinstance(value, str):
        raise ValueError("JSON object key must be a string")
    return value


def _find_container(source: mmap.mmap, field: str) -> tuple[int, int]:
    """Locate a named JSON collection anywhere in the source.

    Doduda exports do not guarantee that ``RefIds`` is a top-level member.
    The legacy indexer therefore searched for the named field anywhere in the
    document. Preserve that contract without decoding the complete file: use
    mmap's byte search, then validate ``:`` and the collection opener.
    """

    needle = json.dumps(field, ensure_ascii=False).encode("utf-8")
    search_from = 0
    size = len(source)
    while search_from < size:
        key_start = source.find(needle, search_from)
        if key_start < 0:
            raise KeyError(field)
        cursor = _skip_ws(source, key_start + len(needle))
        if cursor >= size or source[cursor] != 0x3A:  # :
            search_from = key_start + 1
            continue
        value_start = _skip_ws(source, cursor + 1)
        if value_start >= size:
            raise ValueError("JSON value expected")
        opener = source[value_start]
        if opener == 0x7B:  # {
            return value_start + 1, 0x7D
        if opener == 0x5B:  # [
            return value_start + 1, 0x5D
        search_from = key_start + 1
    raise KeyError(field)


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
        # v2: offsets are built from a memory-mapped byte scanner instead of a
        # full decoded Python string. Keep a distinct cache signature so CI and
        # first-run evidence exercise the new low-heap path once.
        signature = [str(path.resolve()), *self._stamp, field, self.doduda, 2]
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
        """Build byte spans without allocating a decoded copy of the source."""

        if self.path.stat().st_size <= 0:
            raise ValueError("Empty JSON source")

        offsets: dict[str, tuple[int, int]] = {}
        with self.path.open('rb') as stream:
            with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as source:
                try:
                    cursor, container_end = _find_container(source, field)
                except KeyError:
                    self._source_failure(f"champ requis absent ({field})")
                    return {}

                while True:
                    cursor = _skip_ws(source, cursor)
                    if cursor >= len(source):
                        raise ValueError("Unterminated JSON collection")
                    if source[cursor] == container_end:
                        break

                    if self.doduda:
                        start = cursor
                        value_end = _scan_value_end(source, cursor)
                        value = json.loads(source[start:value_end])
                        row = value.get('data') if isinstance(value, dict) else None
                        key = row.get('id') if isinstance(row, dict) else None
                    else:
                        key_start = cursor
                        key_end = _scan_string_end(source, key_start)
                        key = _decode_json_string(source, key_start, key_end)
                        cursor = _skip_ws(source, key_end)
                        if cursor >= len(source) or source[cursor] != 0x3A:  # :
                            raise ValueError("Missing JSON member separator")
                        start = _skip_ws(source, cursor + 1)
                        value_end = _scan_value_end(source, start)

                    if key is not None:
                        offsets[str(key)] = (start, value_end)

                    cursor = _skip_ws(source, value_end)
                    if cursor < len(source) and source[cursor] == 0x2C:  # ,
                        cursor += 1
                        continue
                    if cursor < len(source) and source[cursor] == container_end:
                        break
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
