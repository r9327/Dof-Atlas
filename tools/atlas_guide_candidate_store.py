"""Atomic candidate bundle storage for independently prepared Atlas guide routes.

This module NEVER writes into installed Atlas data, the Guide manifest, or
character progress. It does not activate a runtime route or claim certification.
It preserves multiple immutable candidates and an atomic local selection pointer.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from app.modules.encyclopedia.services.guide_shared_route_contract import (
    GuideRouteContractError,
    project_authorized_guide,
)

# Static contract for Atlas Doctor's derived AI tool catalog; no import side effects.
TOOL_SPEC = {
    "schema_version": 1,
    "id": "atlas-guide-candidate-store",
    "role": "guide_staged_candidate_storage",
    "capabilities": ["guide","generation"],
    "modes": ["trusted_publish_api","selection_lookup","rollback_api"],
    "cost_hint": "variable",
    "side_effects": "repo_mutation_explicit",
    "structured_output": True,
    "canonical": False,
    "recommended_tests": ["tests.test_atlas_guide_candidate_store"],
    "target_scopes": ["encyclopedia_guide"],
}

_FORMAT = "atlas-guide-candidate-store/v1"
_ROOT_MARKER = ".atlas-guide-candidates-v1.json"
_SELECTED = "selected.json"
_FORBIDDEN_PARTS = frozenset({".git", ".cache", "data", "saves", "profiles", "user_data"})
_NO_SELECTION = "NONE"


def _json_bytes(value: Any) -> bytes:
    try:
        payload = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise GuideRouteContractError("candidate contains non-JSON-compatible values") from exc
    return (payload + "\n").encode("utf-8")


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _source_coordinates(value: Any) -> str:
    if value is None:
        return ""
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or any(type(number) is not int or abs(number) > 10000 for number in value)):
        raise GuideRouteContractError("invalid verified source coordinates")
    return f"{value[0]},{value[1]}"


def _validate_candidate(preview: dict[str, Any]) -> None:
    if not isinstance(preview, dict):
        raise GuideRouteContractError("preview must be a JSON object")
    if (type(preview.get("schema_version")) is not int
            or preview["schema_version"] != 1
            or preview.get("mode") != "DRY_RUN_ONLY"):
        raise GuideRouteContractError("preview must come from the dry-run importer")
    if preview.get("status") != "PREVIEW_ONLY_NOT_CERTIFIED" or preview.get("certified") is not False:
        raise GuideRouteContractError("candidate must remain NOT_CERTIFIED")
    source_hash = preview.get("source_sha256")
    if (not isinstance(source_hash, str) or source_hash == "0" * 64
            or len(source_hash) != 64 or any(
                char not in "0123456789abcdef" for char in source_hash
            )):
        raise GuideRouteContractError("missing source SHA-256")
    routes = preview.get("routes")
    if not isinstance(routes, list) or not routes:
        raise GuideRouteContractError("nonempty projected routes required")
    ids: set[str] = set()
    count = 0
    for route in routes:
        if not isinstance(route, dict) or route.get("source_compliance") != "NOT_CERTIFIED":
            raise GuideRouteContractError("route cannot claim certification")
        identifier = route.get("id")
        if not isinstance(identifier, str) or not identifier.startswith("source_guide:"):
            raise GuideRouteContractError("invalid candidate route ID")
        if identifier in ids:
            raise GuideRouteContractError("duplicate candidate route")
        ids.add(identifier)
        steps = route.get("steps")
        if not isinstance(steps, list) or not steps:
            raise GuideRouteContractError("route without steps")
        keys: set[str] = set()
        for step in steps:
            if not isinstance(step, dict):
                raise GuideRouteContractError("invalid projected step")
            key = step.get("manual_stage_id")
            source_step_id = step.get("source_step_id")
            chapter = step.get("manual_chapter_id")
            if (not isinstance(source_step_id, str)
                    or not isinstance(chapter, str)
                    or not isinstance(key, str)
                    or key != f"source:{chapter}:{source_step_id}"
                    or identifier != f"source_guide:{chapter}"
                    or key in keys):
                raise GuideRouteContractError("invalid/duplicate canonical stage identity")
            keys.add(key)
            metadata = step.get("manual_runtime_metadata")
            if not isinstance(metadata, dict) or not isinstance(
                metadata.get("source_step"), dict
            ):
                raise GuideRouteContractError("missing original source step")
            source_step = metadata["source_step"]
            if str(source_step.get("source_step_id")) != source_step_id:
                raise GuideRouteContractError("stage identity differs from original source")
            if (step.get("manual_title") != source_step.get("title")
                    or step.get("manual_route_position")
                    != _source_coordinates(source_step.get("coordinates"))
                    or step.get("manual_quest_ids") != source_step.get("quest_ids", [])
                    or step.get("manual_quest_names") != source_step.get("quest_names", [])
                    or step.get("hard_runtime_gates") != source_step.get("prerequisites", [])):
                raise GuideRouteContractError("stage title, position or prerequisites altered")
            actions = source_step.get("actions")
            if not isinstance(actions, list) or not actions or any(
                not isinstance(item, dict) for item in actions
            ):
                raise GuideRouteContractError("invalid original source actions")
            sections = step.get("manual_sections")
            if not isinstance(sections, dict):
                raise GuideRouteContractError("missing projected UI sections")
            order = ("prepare", "now", "opportunity", "keep", "boss", "before_leave")
            if set(sections) - set(order):
                raise GuideRouteContractError("unexpected projected UI section")
            presented: list[tuple[str, dict[str, Any]]] = []
            rendered: list[dict[str, Any]] = []
            for section in order:
                rows = sections.get(section, [])
                if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                    raise GuideRouteContractError("invalid projected UI rows")
                presented.extend((section, row) for row in rows)
                if section != "prepare":
                    rendered.extend(rows)
            if len(presented) != len(actions):
                raise GuideRouteContractError("projected UI action coverage mismatch")
            if step.get("manual_lines") != rendered:
                raise GuideRouteContractError("rendered UI lines differ from projected sections")
            resource_names: list[str] = []
            preparation: list[dict[str, Any]] = []
            for (section, row), action in zip(presented, actions):
                kind = action.get("kind")
                if not isinstance(kind, str):
                    raise GuideRouteContractError("invalid source action kind")
                expected_section = action.get("section", {
                    "prepare": "prepare", "warning": "before_leave",
                    "keep": "keep",
                }.get(kind, "now"))
                expected_kind = ("combat" if kind in {"fight", "combat"} else
                                 "warning" if kind == "warning" else "action")
                position = _source_coordinates(action.get("coordinates")) or (
                    _source_coordinates(source_step.get("coordinates"))
                )
                if (section != expected_section
                        or row.get("source_action_id") != str(action.get("action_id"))
                        or row.get("source_action_kind") != kind
                        or row.get("source_action") != action
                        or row.get("kind") != expected_kind
                        or row.get("text") != action.get("text")
                        or row.get("position") != (f"[{position}]" if position else "")):
                    raise GuideRouteContractError("projected UI action altered or reordered")
                items = action.get("items")
                if items is not None:
                    if not isinstance(items, list) or any(not isinstance(i, dict) for i in items):
                        raise GuideRouteContractError("invalid original source items")
                    for item in items:
                        name = item.get("name")
                        if not isinstance(name, str) or not name:
                            raise GuideRouteContractError("invalid source resource")
                        if name not in resource_names:
                            resource_names.append(name)
                        if section == "prepare":
                            preparation.append({
                                "name": name, "quantity": item.get("quantity"),
                                "item_id": item.get("item_id"),
                                "source_action_id": str(action.get("action_id")),
                            })
            if step.get("manual_resource_names") != resource_names:
                raise GuideRouteContractError("resource copy links missing from UI")
            if step.get("a_preparer") != preparation:
                raise GuideRouteContractError("preparation panel differs from source items")
        # No alternate rendering fields can sneak into a candidate bundle:
        # round-trip the original authorized step documents through the one
        # canonical adapter and demand identical UI data, including header,
        # page indexes, source flags, and any future schema extension.
        source_meta = route.get("source_guide_metadata")
        if not isinstance(source_meta, dict) or "steps" in source_meta:
            raise GuideRouteContractError("missing/invalid original guide metadata")
        if not isinstance(source_meta.get("title"), str):
            raise GuideRouteContractError("missing canonical source guide title")
        original = dict(source_meta)
        original["steps"] = [
            card["manual_runtime_metadata"]["source_step"] for card in steps
        ]
        reconstructed = project_authorized_guide(original)
        if reconstructed != route:
            raise GuideRouteContractError(
                "candidate route differs from canonical source-to-UI projection"
            )
        count += len(steps)
    for label in ("guide_count", "step_count", "action_count",
                  "expected_guide_count", "expected_step_count"):
        if type(preview.get(label)) is not int or preview[label] <= 0:
            raise GuideRouteContractError(f"invalid candidate {label}")
    if type(preview.get("is_partial")) is not bool:
        raise GuideRouteContractError("invalid candidate partial marker")
    if preview["guide_count"] != len(routes) or preview["step_count"] != count:
        raise GuideRouteContractError("preview coverage mismatch")
    action_count = sum(
        len(step["manual_runtime_metadata"]["source_step"]["actions"])
        for route in routes for step in route["steps"]
    )
    if preview["action_count"] != action_count:
        raise GuideRouteContractError("candidate action coverage mismatch")
    if preview["is_partial"]:
        if (preview["guide_count"] > preview["expected_guide_count"]
                or preview["step_count"] > preview["expected_step_count"]):
            raise GuideRouteContractError(
                "partial candidate exceeds the declared guide/step limits"
            )
    else:
        if preview["guide_count"] != preview["expected_guide_count"]:
            raise GuideRouteContractError("incomplete full guide inventory")
        if preview["step_count"] != preview["expected_step_count"]:
            raise GuideRouteContractError("incomplete full step inventory")


def _safe_root(root: Path) -> Path:
    candidate = Path(root).absolute()
    if candidate.is_symlink() or any(part.casefold() in _FORBIDDEN_PARTS
                                    for part in candidate.parts):
        raise GuideRouteContractError("candidate root must not be an Atlas data/save/cache directory")
    # An explicit staging root may be outside the checkout or inside its
    # disposable artifacts/ directory. Never accept a source, CI-policy,
    # user-data or UI directory merely because it was initially empty.
    # The store cannot reliably know a Windows install path, so this is an
    # additional source-tree guard, not a substitute for the forbidden parts.
    source_root = Path(__file__).resolve().parents[1]
    try:
        within_checkout = candidate.relative_to(source_root)
    except ValueError:
        within_checkout = None
    if within_checkout is not None and (
        not within_checkout.parts or within_checkout.parts[0].casefold() != "artifacts"
    ):
        raise GuideRouteContractError(
            "candidate root must be outside repository sources or under artifacts/"
        )
    if candidate.is_file():
        raise GuideRouteContractError("candidate root is a file")
    for parent in candidate.parents:
        if parent.is_symlink():
            raise GuideRouteContractError("symlinked parent is not supported")
    return candidate


def _sync_file(path: Path, contents: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(contents)
        stream.flush()
        os.fsync(stream.fileno())


def _atomic_file(path: Path, content: bytes) -> None:
    if path.is_symlink() or path.parent.is_symlink():
        raise GuideRouteContractError("symlink in candidate output path")
    # Same directory guarantees a same-volume os.replace on Windows.
    fd, name = tempfile.mkstemp(prefix=".atlas-stage-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise GuideRouteContractError(f"symlinked candidate metadata: {path.name}")

    def no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for key, value in pairs:
            if key in data:
                raise ValueError(f"duplicate JSON key {key!r}")
            data[key] = value
        return data

    def no_nonfinite(value: str) -> Any:
        raise ValueError(f"non-finite JSON constant {value!r}")

    def finite_float(value: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError(f"out-of-range JSON float {value!r}")
        return parsed

    try:
        result = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=no_duplicate_keys,
            parse_constant=no_nonfinite,
            parse_float=finite_float,
        )
    except (ValueError, OSError) as exc:
        raise GuideRouteContractError(f"invalid store file: {path.name}: {exc}") from exc
    if not isinstance(result, dict):
        raise GuideRouteContractError(f"invalid store JSON object: {path.name}")
    return result


@contextmanager
def _locked(root: Path) -> Iterator[Path]:
    root = _safe_root(root)
    # No implicit adoption of existing directories with arbitrary user data.
    if not root.exists():
        root.mkdir(parents=True, exist_ok=False)
    if not root.is_dir():
        raise GuideRouteContractError("candidate store is not a directory")
    marker = root / _ROOT_MARKER
    if not marker.exists():
        if list(root.iterdir()):
            raise GuideRouteContractError("unmanaged nonempty candidate directory")
        _sync_file(marker, _json_bytes({"format": _FORMAT, "runtime_activation": False}))
    if _read_json(marker) != {"format": _FORMAT, "runtime_activation": False}:
        raise GuideRouteContractError("wrong candidate directory marker")
    lock = root / ".writer.lock"
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise GuideRouteContractError("concurrent publisher or interrupted write: manual review required") from exc
    try:
        yield root
    finally:
        # Only the owner of a successfully created lock removes it.
        lock.rmdir()


def _checked_pointer(value: Any, label: str) -> str:
    if not isinstance(value, str) or (value != _NO_SELECTION and (
        value == "0" * 64 or len(value) != 64
        or any(x not in "0123456789abcdef" for x in value)
    )):
        raise GuideRouteContractError(f"invalid {label}: SHA-256 or NONE required")
    return value


def _selection(root: Path) -> str:
    path = root / _SELECTED
    # A dangling symlink reports exists() == False; it is NOT an empty store.
    if path.is_symlink():
        raise GuideRouteContractError("symlinked candidate selection")
    if not path.exists():
        return _NO_SELECTION
    doc = _read_json(path)
    value = doc.get("candidate_sha256")
    if doc.get("format") != _FORMAT or doc.get("runtime_activation") is not False:
        raise GuideRouteContractError("invalid selection marker")
    return _checked_pointer(value, "selection")


def _candidate_file(root: Path, digest: str) -> Path:
    return root / "generations" / (digest + ".json")


def _verify_generation(root: Path, digest: str) -> None:
    if digest == _NO_SELECTION:
        return
    path = _candidate_file(root, digest)
    if path.is_symlink() or path.parent.is_symlink():
        raise GuideRouteContractError("symlinked candidate generation")
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise GuideRouteContractError(f"missing candidate generation: {digest}") from exc
    if _digest(payload) != digest:
        raise GuideRouteContractError(f"candidate generation SHA mismatch: {digest}")
    _validate_candidate(_read_json(path))


def publish_candidate(
    preview: dict[str, Any],
    *,
    root: Path,
    expected_selected: str = _NO_SELECTION,
) -> dict[str, Any]:
    """Immutable candidate + atomic CAS selection; not a live Atlas install.

    The expected selection must be from a fresh call to selected_candidate()
    or explicitly NONE when initializing. A stale selection fails closed.
    """
    _validate_candidate(preview)
    _checked_pointer(expected_selected, "expected_selected")
    payload = _json_bytes(preview)
    digest = _digest(payload)
    with _locked(root) as store:
        old = _selection(store)
        _verify_generation(store, old)
        if old != expected_selected:
            raise GuideRouteContractError("stale candidate selection; compare-and-swap rejected")
        folder = store / "generations"
        if folder.is_symlink():
            raise GuideRouteContractError("symlinked candidate generations directory")
        folder.mkdir(exist_ok=True)
        target = _candidate_file(store, digest)
        if target.exists():
            _verify_generation(store, digest)
        else:
            # Never write partial bytes directly to a content-addressed name.
            # Commit an fsynced temp file atomically; failure leaves either
            # no generation or a complete one, while selection stays old.
            _atomic_file(target, payload)
        _atomic_file(store / _SELECTED, _json_bytes({
            "format": _FORMAT, "candidate_sha256": digest,
            "runtime_activation": False,
        }))
    return {
        "status": "CANDIDATE_STORED_NOT_ACTIVE",
        "candidate_sha256": digest, "previous_sha256": old,
        "certified": False, "runtime_activation": False,
    }


def selected_candidate(root: Path) -> str:
    """Read and verify a managed selection; reject any invalid/foreign directory."""
    root = _safe_root(root)
    marker = _read_json(root / _ROOT_MARKER)
    if marker != {"format": _FORMAT, "runtime_activation": False}:
        raise GuideRouteContractError("not a candidate store")
    value = _selection(root)
    _verify_generation(root, value)
    return value


def rollback_candidate(
    *,
    root: Path,
    expected_selected: str,
    restore_sha256: str = _NO_SELECTION,
) -> dict[str, Any]:
    """CAS rollback of the candidate selection only, never character progress."""
    _checked_pointer(expected_selected, "expected_selected")
    _checked_pointer(restore_sha256, "restore_sha256")
    with _locked(root) as store:
        actual = _selection(store)
        _verify_generation(store, actual)
        if actual != expected_selected:
            raise GuideRouteContractError("stale rollback; selection changed")
        if restore_sha256 != _NO_SELECTION:
            _verify_generation(store, restore_sha256)
        _atomic_file(store / _SELECTED, _json_bytes({
            "format": _FORMAT, "candidate_sha256": restore_sha256,
            "runtime_activation": False,
        }))
    return {"status": "CANDIDATE_ROLLED_BACK_NOT_ACTIVE",
            "candidate_sha256": restore_sha256, "certified": False}


__all__ = ["publish_candidate", "selected_candidate", "rollback_candidate"]
