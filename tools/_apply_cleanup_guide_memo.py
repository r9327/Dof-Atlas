from __future__ import annotations

import ast
from pathlib import Path

ROUTE = Path("app/modules/encyclopedia/services/guide_ultime_manual_route.py")
SERVICE = Path("app/modules/encyclopedia/services/guide_ultime_manual_runtime_service.py")
TEST = Path("tests/test_guide_ultime_v5_runtime.py")


def function_node(source: str, name: str) -> ast.FunctionDef:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise RuntimeError(f"function not found: {name}")


def replace_function(source: str, name: str, replacement: str) -> str:
    node = function_node(source, name)
    lines = source.splitlines(keepends=True)
    lines[node.lineno - 1 : node.end_lineno] = [replacement.rstrip() + "\n\n"]
    return "".join(lines)


def patch_route() -> None:
    source = ROUTE.read_text(encoding="utf-8")
    if "manual_route_resolution_scope" in source:
        raise SystemExit("manual route resolution scope already exists")
    source = source.replace(
        "import copy\nimport json\n",
        "import copy\nfrom contextlib import contextmanager\nfrom contextvars import ContextVar\nimport json\n",
        1,
    )
    source = source.replace("from typing import Any\n", "from typing import Any, Iterator\n", 1)
    cache_anchor = "_MAX_CHAPTER_CACHE_ENTRIES = 96\n"
    if source.count(cache_anchor) != 1:
        raise SystemExit("chapter cache anchor changed")
    source = source.replace(
        cache_anchor,
        cache_anchor
        + '_RESOLUTION_MEMO: ContextVar[dict[tuple[str, bool], dict[str, Any]] | None] = ContextVar(\n'
        + '    "guide_ultime_manual_resolution_memo", default=None\n'
        + ")\n\n\n"
        + "@contextmanager\n"
        + "def manual_route_resolution_scope() -> Iterator[None]:\n"
        + '    """Reuse complete chapter resolutions during one immutable bundle composition."""\n\n'
        + "    current = _RESOLUTION_MEMO.get()\n"
        + "    if current is not None:\n"
        + "        yield\n"
        + "        return\n"
        + "    token = _RESOLUTION_MEMO.set({})\n"
        + "    try:\n"
        + "        yield\n"
        + "    finally:\n"
        + "        _RESOLUTION_MEMO.reset(token)\n",
        1,
    )
    source = replace_function(
        source,
        "load_manual_chapter",
        '''def load_manual_chapter(
    path: Path,
    *,
    _seen: set[Path] | None = None,
    _expand_hooks: bool = True,
) -> dict[str, Any]:
    """Resolve one chapter with persistent top-level and scoped recursive caches."""

    resolved = Path(path).resolve()
    # Cycle detection must win over every cache, including the scoped memo.
    if _seen is not None and resolved in _seen:
        raise ValueError(f"Cycle de composition détecté: {resolved}")

    memo = _RESOLUTION_MEMO.get()
    memo_key = (str(resolved), bool(_expand_hooks))
    if memo is not None and memo_key in memo:
        return copy.deepcopy(memo[memo_key])

    if _seen is not None:
        result = _load_manual_chapter_uncached(
            resolved,
            _seen=_seen,
            _expand_hooks=_expand_hooks,
        )
        if memo is not None:
            memo[memo_key] = copy.deepcopy(result)
        return result

    key: tuple[object, ...] = (
        str(resolved),
        bool(_expand_hooks),
        _manual_tree_signature(resolved.parent),
    )
    with _CACHE_LOCK:
        cached = _CHAPTER_CACHE.get(key)
        if cached is not None:
            if memo is not None:
                memo[memo_key] = copy.deepcopy(cached)
            return copy.deepcopy(cached)
    result = _load_manual_chapter_uncached(resolved, _expand_hooks=_expand_hooks)
    frozen = copy.deepcopy(result)
    with _CACHE_LOCK:
        stale = [
            cached_key
            for cached_key in _CHAPTER_CACHE
            if cached_key[0] == str(resolved) and cached_key[1] == bool(_expand_hooks)
        ]
        for cached_key in stale:
            _CHAPTER_CACHE.pop(cached_key, None)
        _CHAPTER_CACHE[key] = frozen
        while len(_CHAPTER_CACHE) > _MAX_CHAPTER_CACHE_ENTRIES:
            _CHAPTER_CACHE.pop(next(iter(_CHAPTER_CACHE)))
    if memo is not None:
        memo[memo_key] = copy.deepcopy(frozen)
    return copy.deepcopy(frozen)
''',
    )
    ast.parse(source)
    ROUTE.write_text(source, encoding="utf-8", newline="\n")


def patch_service() -> None:
    source = SERVICE.read_text(encoding="utf-8")
    import_anchor = "    _manual_tree_signature,\n    load_manual_chapter,\n"
    if source.count(import_anchor) != 1:
        raise SystemExit("manual route import anchor changed")
    source = source.replace(
        import_anchor,
        "    _manual_tree_signature,\n    load_manual_chapter,\n    manual_route_resolution_scope,\n",
        1,
    )
    method_anchor = "    def _load_manual_preview_uncached(self) -> None:\n"
    if source.count(method_anchor) != 1:
        raise SystemExit("manual preview method anchor changed")
    source = source.replace(
        method_anchor,
        "    @manual_route_resolution_scope()\n" + method_anchor,
        1,
    )
    ast.parse(source)
    SERVICE.write_text(source, encoding="utf-8", newline="\n")


def patch_test() -> None:
    source = TEST.read_text(encoding="utf-8")
    source = source.replace("import unittest\n", "import unittest\nfrom unittest.mock import patch\n", 1)
    import_anchor = "from app.modules.encyclopedia.services.guide_progress_service import GuideProgressService\n"
    if source.count(import_anchor) != 1:
        raise SystemExit("runtime test import anchor changed")
    source = source.replace(
        import_anchor,
        "from app.modules.encyclopedia.services import guide_ultime_manual_route as manual_route\n" + import_anchor,
        1,
    )
    end_anchor = '\n\nif __name__ == "__main__":\n    unittest.main()\n'
    if source.count(end_anchor) != 1:
        raise SystemExit("runtime test end anchor changed")
    methods = '''

    def test_manual_route_scope_reuses_shared_resolution_without_aliasing(self):
        root = Path(self.tmp.name) / "manual"
        root.mkdir()
        shared = root / "shared.json"
        first_path = root / "first.json"
        second_path = root / "second.json"
        shared.write_text(json.dumps({"stages": [{"id": "S1", "title": "Shared"}]}), encoding="utf-8")
        first_path.write_text(json.dumps({
            "base_file": "shared.json",
            "stage_patches": {"S1": {"replace": {"title": "First"}}},
        }), encoding="utf-8")
        second_path.write_text(json.dumps({
            "base_file": "shared.json",
            "stage_patches": {"S1": {"replace": {"title": "Second"}}},
        }), encoding="utf-8")

        manual_route.clear_manual_route_cache()
        with patch.object(manual_route, "_read_json", wraps=manual_route._read_json) as read_json:
            with manual_route.manual_route_resolution_scope():
                first = manual_route.load_manual_chapter(first_path)
                second = manual_route.load_manual_chapter(second_path)
                shared_copy = manual_route.load_manual_chapter(shared)
                shared_copy["stages"][0]["title"] = "Mutated"
                shared_again = manual_route.load_manual_chapter(shared)

        shared_reads = sum(
            Path(call.args[0]).resolve() == shared.resolve()
            for call in read_json.call_args_list
        )
        self.assertEqual(shared_reads, 1)
        self.assertEqual(first["stages"][0]["title"], "First")
        self.assertEqual(second["stages"][0]["title"], "Second")
        self.assertEqual(shared_again["stages"][0]["title"], "Shared")

    def test_manual_route_scope_never_masks_cycle_detection(self):
        root = Path(self.tmp.name) / "manual-cycle"
        root.mkdir()
        chapter = root / "chapter.json"
        chapter.write_text(json.dumps({"stages": [{"id": "S1"}]}), encoding="utf-8")

        manual_route.clear_manual_route_cache()
        with manual_route.manual_route_resolution_scope():
            manual_route.load_manual_chapter(chapter)
            with self.assertRaisesRegex(ValueError, "Cycle de composition"):
                manual_route.load_manual_chapter(chapter, _seen={chapter.resolve()})
'''
    source = source.replace(end_anchor, methods + end_anchor, 1)
    ast.parse(source)
    TEST.write_text(source, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    patch_route()
    patch_service()
    patch_test()
