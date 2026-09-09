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

_SPACE = re.compile(r'\s*')


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
    def __init__(self, path: Path, cache_root: Path, field: str, *, doduda=False):
        self.path, self.doduda = path, doduda
        self._lock = RLock()
        self._cache = OrderedDict()
        self._offsets = None
        self._cache_root, self._field = cache_root, field
        self._stream = None

    def _ensure(self):
        if self._offsets is not None:
            return
        path, cache_root, field = self.path, self._cache_root, self._field
        stat = path.stat()
        self._stamp = (stat.st_mtime_ns, stat.st_size)
        signature = [str(path.resolve()), *self._stamp, field, self.doduda, 1]
        digest = hashlib.sha256(json.dumps(signature).encode()).hexdigest()
        cache = cache_root / f"source_{digest}.json.gz"
        offsets = None
        if cache.exists():
            try:
                with gzip.open(cache, 'rt', encoding='utf-8') as stream:
                    offsets = json.load(stream)
                if not isinstance(offsets, dict) or any(
                    not isinstance(span, list) or len(span) != 2
                    or not all(isinstance(value, int) for value in span)
                    or not 0 <= span[0] < span[1] <= stat.st_size
                    for span in offsets.values()
                ):
                    offsets = None
            except (ValueError, OSError):
                pass
        if offsets is None:
            offsets = self._build_offsets(field)
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

    def mapping(self, path, field, *, doduda=False):
        key = (path, field, doduda)
        if key not in self._mappings:
            self._mappings[key] = JsonSourceMapping(path, self.cache_root, field, doduda=doduda)
        return self._mappings[key]

    def rows(self, path):
        if not path.exists():
            return {}
        return self.mapping(path, 'RefIds', doduda=True)

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
