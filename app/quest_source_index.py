"""Read individual records from Atlas' monolithic JSON sources.

Only byte offsets are cached. JSON values are decoded by the standard library
on demand; no executable serialization and no persistent user data are used.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
import sqlite3
import tempfile
import weakref
from collections import OrderedDict, defaultdict
from collections.abc import Mapping
from contextlib import closing
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
    def __init__(
        self,
        path: Path,
        cache_root: Path,
        field: str,
        *,
        doduda=False,
        required=True,
        disk_backed=False,
        disk_connection_observer=None,
    ):
        self.path, self.doduda, self.required = path, doduda, bool(required)
        self.disk_backed = bool(disk_backed)
        self._lock = RLock()
        self._cache = OrderedDict()
        self._offsets = None
        self._disk_index = None
        self._disk_connection = None
        self._disk_connection_observer = disk_connection_observer
        self._cache_root, self._field = cache_root, field
        self._stream = None

    def _disk_offset_connection(self) -> sqlite3.Connection:
        if self._disk_index is None:
            raise RuntimeError("Disk-backed source index is not initialized")
        if self._disk_connection is None:
            self._disk_connection = sqlite3.connect(
                self._disk_index,
                check_same_thread=False,
            )
        if self._disk_connection_observer is not None:
            self._disk_connection_observer(self)
        return self._disk_connection

    def _close_disk_connection(self) -> None:
        if self._disk_connection is not None:
            self._disk_connection.close()
            self._disk_connection = None

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
        disk_index = cache_root / f"source_{digest}.sqlite3"
        if self.disk_backed and disk_index.is_file():
            try:
                with closing(sqlite3.connect(disk_index)) as connection:
                    connection.execute("SELECT COUNT(*) FROM offsets").fetchone()
                self._disk_index = disk_index
                self._offsets = {}
                return
            except sqlite3.Error:
                disk_index.unlink(missing_ok=True)
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
        normalized_offsets = {
            int(key) if self.doduda else key: tuple(span)
            for key, span in offsets.items()
        }
        if self.disk_backed:
            cache_root.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                dir=cache_root,
                suffix=".sqlite3.tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
            try:
                with closing(sqlite3.connect(temporary_path)) as connection:
                    with connection:
                        connection.execute(
                            "CREATE TABLE offsets (key TEXT PRIMARY KEY, start INTEGER, end INTEGER)"
                        )
                        connection.executemany(
                            "INSERT INTO offsets VALUES (?, ?, ?)",
                            (
                                (str(key), int(span[0]), int(span[1]))
                                for key, span in normalized_offsets.items()
                            ),
                        )
                temporary_path.replace(disk_index)
            finally:
                temporary_path.unlink(missing_ok=True)
            self._disk_index = disk_index
            self._offsets = {}
        else:
            self._offsets = normalized_offsets

    def _build_offsets(self, field):
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

        # Regex and bytes.find run in native code: rich Quest enrichment can
        # contain tens of megabytes of quoted text. Avoid a Python iteration
        # for each byte without changing JSON nesting or disk/cache contracts.
        structural_token = re.compile(rb'["{}\[\]]')

        def read_string_span() -> tuple[int, int]:
            start_pos = reader.tell()
            if reader.get() != ord('"'):
                raise ValueError("Expected JSON string")
            previous_backslashes = 0
            while reader._fill():
                begin = reader.index
                quote = reader.buffer.find(b'"', begin)
                if quote < 0:
                    cursor = len(reader.buffer) - 1
                    while cursor >= begin and reader.buffer[cursor] == 92:
                        cursor -= 1
                    previous_backslashes = (
                        len(reader.buffer) - 1 - cursor
                        + (previous_backslashes if cursor < begin else 0)
                    )
                    reader.index = len(reader.buffer)
                    continue
                cursor = quote - 1
                while cursor >= begin and reader.buffer[cursor] == 92:
                    cursor -= 1
                backslashes = quote - 1 - cursor
                if cursor < begin:
                    backslashes += previous_backslashes
                reader.index = quote + 1
                previous_backslashes = 0
                if backslashes % 2 == 0:
                    return start_pos, reader.tell()
            raise ValueError("Unterminated JSON string")

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
                while True:
                    # Only quotes and structural delimiters matter; braces
                    # inside strings are skipped by the escape-aware parser.
                    if not reader._fill():
                        raise ValueError("Unterminated JSON value")
                    token = structural_token.search(reader.buffer, reader.index)
                    if token is None:
                        reader.index = len(reader.buffer)
                        continue
                    reader.index = token.start()
                    value = reader.peek()
                    if value == ord('"'):
                        read_string_span()
                        continue
                    reader.get()
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
        try:
            while True:
                skip_space()
                value = reader.peek()
                if value is None:
                    raise ValueError("Unterminated JSON container")
                if value == closing:
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
                if key is not None:
                    offsets[str(key)] = (value_start, value_end)

                skip_space()
                delimiter = reader.peek()
                if delimiter == ord(","):
                    reader.get()
                elif delimiter == closing:
                    break
                elif delimiter is None:
                    raise ValueError("Unterminated JSON container")
                else:
                    raise ValueError("Missing JSON member delimiter")
        finally:
            reader.close()
            values.close()
        return offsets

    def __getitem__(self, key):
        with self._lock:
            self._ensure()
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            if self._disk_index is not None:
                row = self._disk_offset_connection().execute(
                    "SELECT start, end FROM offsets WHERE key=?",
                    (str(key),),
                ).fetchone()
                if row is None:
                    raise KeyError(key)
                start, end = int(row[0]), int(row[1])
            else:
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
        with self._lock:
            self._ensure()
            if self._disk_index is not None:
                rows = self._disk_offset_connection().execute(
                    "SELECT key FROM offsets"
                ).fetchall()
                return iter(
                    int(row[0]) if self.doduda else row[0]
                    for row in rows
                )
            return iter(self._offsets)

    def __len__(self):
        with self._lock:
            self._ensure()
            if self._disk_index is not None:
                row = self._disk_offset_connection().execute(
                    "SELECT COUNT(*) FROM offsets"
                ).fetchone()
                return max(0, int(row[0] if row else 0))
            return len(self._offsets)

    def close(self):
        with self._lock:
            if self._stream is not None:
                self._close_stream()
                self._stream = None
            self._close_disk_connection()
            # A completed Quest detail is already retained as a bounded rich
            # record (and stored in SQLite). Keeping its decoded source rows
            # too duplicates memory across the Guide/Quest/Home lifecycle.
            # Preserve byte-offset indexes so subsequent details stay fast.
            self._cache.clear()


class QuestSources:
    MAX_OPEN_DISK_CONNECTIONS = 6

    def __init__(self, cache_root, *, disk_backed=False):
        self.cache_root = cache_root
        self.disk_backed = bool(disk_backed)
        self._mappings = {}
        self._disk_connections = OrderedDict()
        self._objectives_by_step = None
        self._image_index = None
        self.context = {}

    def _retain_disk_connection(self, mapping: JsonSourceMapping) -> None:
        key = id(mapping)
        self._disk_connections.pop(key, None)
        self._disk_connections[key] = mapping
        while len(self._disk_connections) > self.MAX_OPEN_DISK_CONNECTIONS:
            _key, stale = self._disk_connections.popitem(last=False)
            stale._close_disk_connection()

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
                disk_backed=self.disk_backed,
                disk_connection_observer=(
                    self._retain_disk_connection if self.disk_backed else None
                ),
            )
        return self._mappings[key]

    def rows(self, path):
        return self.mapping(path, 'RefIds', doduda=True, required=True)

    def prime_objective_steps(self, index: dict[int, list[int]]) -> None:
        """Reuse the objective IDs indexed by the versioned Quest SQLite cache.

        Only row identifiers are retained; objective payloads are still loaded
        from the canonical source on demand, with normal source validation.
        """
        if self._objectives_by_step is None:
            self._objectives_by_step = defaultdict(
                list,
                {
                    int(step_id): [int(objective_id) for objective_id in ids]
                    for step_id, ids in index.items()
                },
            )

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
        self._disk_connections.clear()
