"""Independent, read-only, fail-closed semantic diff of authorized guide exports.

This module intentionally has no imports from the retired PR #337 or from the Qt
runtime. PARITY_PASS is a data comparison result, NEVER a gameplay certificate.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

# Static contract for Atlas Doctor's derived AI tool catalog; no import side effects.
TOOL_SPEC = {
    "schema_version": 1,
    "id": "atlas-guide-conformity",
    "role": "guide_independent_parity",
    "capabilities": ["guide","validation"],
    "modes": ["before_after_reports","explicit_output_directory"],
    "cost_hint": "variable",
    "side_effects": "repo_mutation_explicit",
    "structured_output": True,
    "canonical": False,
    "recommended_tests": ["tests.test_atlas_guide_conformity"],
    "target_scopes": ["encyclopedia_guide"],
}

# Evidence locators document how to verify a source and do not need to
# appear as displayed Atlas gameplay fields. Every other field, including
# source_url, coordinates, media links, complete and capture metadata on
# individual actions, MUST be compared; otherwise missing information can
# falsely yield PARITY_CHECK_PASS.
_IGNORED_REFERENCE_KEYS = frozenset({"evidence_ref"})
_ID_KEYS = {"guide": "guide_id", "step": "source_step_id", "action": "action_id"}
_COLLECTIONS = {"guides": "guide", "steps": "step", "actions": "action"}
# Match the Qt-free adapter identity grammar independently at the diff boundary.
_STABLE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}\Z")
# Structural collection names are meaningful only at canonical route paths.
# Generic source metadata may also contain "guides", "steps" or "actions".
_GUIDE_NODE = re.compile(r"\.guides\[[A-Za-z0-9][A-Za-z0-9._-]{0,119}\]\Z")
_STEP_NODE = re.compile(
    r"\.guides\[[A-Za-z0-9][A-Za-z0-9._-]{0,119}\]"
    r"\.steps\[[A-Za-z0-9][A-Za-z0-9._-]{0,119}\]\Z"
)


# Independent format validation: a pair of equally malformed exports must
# not pass just because their values are equal. Keep the supported action
# grammar aligned with the canonical Qt-free route adapter.
_KNOWN_ACTION_KINDS = frozenset({
    "travel", "talk", "item", "collect", "craft", "interact", "fight",
    "combat", "dungeon", "quest", "achievement", "choice", "warning",
    "prepare", "keep", "optional",
})
_ITEM_ACTION_KINDS = frozenset({"item", "collect", "craft", "keep", "prepare"})
# Match the independent reference against the canonical rendering order too:
# two identical unsupported sections or reversed rows cannot constitute parity.
_RENDER_ORDER = ("now", "opportunity", "keep", "boss", "before_leave")
_VALID_SECTIONS = frozenset((*_RENDER_ORDER, "prepare"))
_DEFAULT_SECTION = {"warning": "before_leave", "keep": "keep", "prepare": "prepare"}


def _valid_position(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple)) and len(value) == 2
        and all(type(x) is int and abs(x) <= 10000 for x in value)
    )


def _digest(payload: Any) -> str:
    raw = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _snapshot(value: Any) -> Any:
    # Evidence must be complete, not an ellipsized 160-character approximation.
    # Only changed values are copied; the complete source is never mutated.
    return copy.deepcopy(value)


def _identifier(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    result = str(value)
    # Never normalize a source ID before comparing inventories. Stripping
    # whitespace here can turn two malformed exports into a false parity PASS.
    return result if _STABLE_ID.fullmatch(result) else None


def compare(reference: dict[str, Any], atlas: dict[str, Any]) -> dict[str, Any]:
    """Compare all reference and Atlas guides in both directions, without mutation.

    The caller must provide an independent, authorized reference. A checksum or
    self-declared rights_verified flag alone cannot certify source authenticity.
    """
    issues: list[dict[str, Any]] = []
    inspected = Counter()
    context: dict[str, Any] = {"guide_id": None, "source_step_id": None, "action_id": None}

    def report(code: str, path: str, expected: Any = None, actual: Any = None,
               evidence: str | None = None, severity: str = "BLOCKER") -> None:
        issues.append({
            "issue_code": code, "severity": severity, "field_path": path,
            "guide_id": context["guide_id"], "source_step_id": context["source_step_id"],
            "action_id": context["action_id"], "expected": _snapshot(expected),
            "actual": _snapshot(actual), "source_evidence_ref": evidence,
            "proposed_fix": {
                "MISSING_GUIDE": "Ajouter le guide vérifié manquant",
                "MISSING_STEP": "Ajouter l'étape vérifiée dans l'ordre",
                "MISSING_ACTION": "Ajouter l'action vérifiée dans l'ordre",
                "MISSING_FIELD": "Ajouter l'élément vérifié à cet emplacement",
                "EXTRA_GUIDE": "Examiner et retirer le guide non justifié",
                "EXTRA_STEP": "Examiner et retirer l'étape non justifiée",
                "EXTRA_ACTION": "Examiner et retirer l'action non justifiée",
                "EXTRA_FIELD": "Vérifier et retirer l'ajout non justifié",
                "VALUE_MISMATCH": "Corriger la valeur après examen de la preuve",
                "TYPE_MISMATCH": "Corriger le type selon le schéma source",
                "ORDER_CHANGED": "Rétablir l'ordre confirmé par la source",
                "DUPLICATE": "Résoudre les identifiants en double",
                "AMBIGUOUS": "Examiner les deux enregistrements avec preuve source indépendante",
                "UNVERIFIABLE": "Obtenir une preuve indépendante vérifiable",
            }.get(code, "Examiner la référence et corriger"), "review_required": True,
        })

    if not isinstance(reference, dict) or not isinstance(atlas, dict):
        raise ValueError("Reference and Atlas exports must be JSON objects")

    def collection_witness(field: str, values: list[Any]) -> dict[str, Any]:
        # A missing key in a full export can hold thousands of complete
        # actions. Keep a precise SHA and count on the parent, while each
        # guide/step/action is reported individually below. Never deepcopy
        # the whole hierarchy into a second redundant issue.
        return {"collection": field, "count": len(values), "sha256": _digest(values)}

    def route_collection_kind(parent_path: str, field: str) -> str | None:
        if field == "guides" and parent_path == "":
            return "guide"
        if field == "steps" and _GUIDE_NODE.fullmatch(parent_path):
            return "step"
        if field == "actions" and _STEP_NODE.fullmatch(parent_path):
            return "action"
        return None

    def walk(expected: Any, actual: Any, path: str, evidence: str | None) -> None:
        inspected["fields"] += 1
        if type(expected) is not type(actual):
            report("TYPE_MISMATCH", path, expected, actual, evidence)
            return
        if isinstance(expected, dict):
            ref_fields = set(expected) - _IGNORED_REFERENCE_KEYS
            atlas_fields = set(actual) - _IGNORED_REFERENCE_KEYS
            for key in sorted(ref_fields - atlas_fields):
                kind = route_collection_kind(path, key)
                is_collection = kind is not None and isinstance(expected[key], list)
                original = (collection_witness(key, expected[key])
                            if is_collection else expected[key])
                report("MISSING_FIELD", f"{path}.{key}", original, None, evidence)
                # Expand only real route collections, not arbitrary metadata.
                if is_collection:
                    collection(expected[key], [], f"{path}.{key}", kind, evidence)
            for key in sorted(atlas_fields - ref_fields):
                kind = route_collection_kind(path, key)
                is_collection = kind is not None and isinstance(actual[key], list)
                original = (collection_witness(key, actual[key])
                            if is_collection else actual[key])
                report("EXTRA_FIELD", f"{path}.{key}", None, original, evidence)
                if is_collection:
                    collection([], actual[key], f"{path}.{key}", kind, evidence)
            for key in sorted(ref_fields & atlas_fields):
                kind = route_collection_kind(path, key)
                if kind is not None:
                    collection(expected[key], actual[key], f"{path}.{key}", kind,
                               evidence)
                else:
                    walk(expected[key], actual[key], f"{path}.{key}", evidence)
            return
        if isinstance(expected, list):
            if len(expected) != len(actual):
                report("VALUE_MISMATCH", f"{path}.length", len(expected), len(actual), evidence)
            for i in range(min(len(expected), len(actual))):
                walk(expected[i], actual[i], f"{path}[{i}]", evidence)
            for i in range(len(actual), len(expected)):
                report("MISSING_FIELD", f"{path}[{i}]", expected[i], None, evidence)
            for i in range(len(expected), len(actual)):
                report("EXTRA_FIELD", f"{path}[{i}]", None, actual[i], evidence)
        elif expected != actual:
            report("VALUE_MISMATCH", path, expected, actual, evidence)

    def collection(expected: Any, actual: Any, path: str, kind: str,
                   parent_evidence: str | None) -> None:
        if not isinstance(expected, list) or not isinstance(actual, list):
            report("TYPE_MISMATCH", path, "list", type(actual).__name__, parent_evidence)
            # A malformed replacement must not hide all original actions.
            # Only recurse with two actual lists to avoid type-error loops.
            if isinstance(expected, list):
                collection(expected, [], path, kind, parent_evidence)
            if isinstance(actual, list):
                collection([], actual, path, kind, parent_evidence)
            return
        key = _ID_KEYS[kind]
        def index(items: list[Any], side: str) -> tuple[dict[str, dict], list[str]]:
            unique: dict[str, dict] = {}
            order: list[str] = []
            for i, item in enumerate(items):
                identifier = _identifier(item.get(key)) if isinstance(item, dict) else None
                if identifier is None:
                    # The actual malformed value is essential to diagnosis:
                    # unlike None, 0/False, a Unicode or a path-like ID can
                    # be distinguished and corrected at the exact location.
                    raw = item.get(key) if isinstance(item, dict) else item
                    report("UNVERIFIABLE", f"{path}.{side}[{i}].{key}",
                           f"canonical {key}", raw, parent_evidence)
                    continue
                if identifier in unique:
                    report("DUPLICATE", f"{path}.{side}[{i}].{key}",
                           identifier, identifier, parent_evidence)
                    if unique[identifier] != item:
                        # Identical collisions are duplicates; two distinct
                        # records competing for the same stable identity are
                        # also ambiguous and require independent adjudication.
                        def summary(value: dict[str, Any]) -> dict[str, Any]:
                            # Keep the full underlying difference auditable
                            # even when two records have an identical title
                            # but distinct nested actions/steps.
                            return {
                                k: (collection_witness(k, v)
                                    if k in _COLLECTIONS and isinstance(v, list)
                                    else v)
                                for k, v in value.items()
                            }
                        report("AMBIGUOUS", f"{path}.{side}[{i}].{key}",
                               summary(unique[identifier]), summary(item),
                               parent_evidence)
                    continue
                unique[identifier] = item
                order.append(identifier)
            return unique, order

        lhs, lhs_order = index(expected, "reference")
        rhs, rhs_order = index(actual, "atlas")
        if kind == "guide":
            inspected["reference_guides"] += len(lhs)
            inspected["atlas_guides"] += len(rhs)
        elif kind == "step":
            inspected["reference_steps"] += len(lhs)
            inspected["atlas_steps"] += len(rhs)
        else:
            inspected["reference_actions"] += len(lhs)
            inspected["atlas_actions"] += len(rhs)
        # When an entire guide or step is absent, comparing only shared
        # parent IDs hides its missing individual steps/actions. Enumerate
        # descendants without duplicating their subtrees in every issue.
        def report_descendants(
            document: dict[str, Any], parent_path: str, parent_kind: str,
            missing: bool, evidence: str | None,
        ) -> None:
            if parent_kind == "guide":
                field, child_kind = "steps", "step"
            elif parent_kind == "step":
                field, child_kind = "actions", "action"
            else:
                return
            children = document.get(field)
            if not isinstance(children, list):
                return  # The independent inventory reports malformed lists.
            child_key = _ID_KEYS[child_kind]
            for child in children:
                if not isinstance(child, dict):
                    continue
                child_id = _identifier(child.get(child_key))
                if child_id is None:
                    continue  # The independent inventory/ID checks reject it.
                child_path = f"{parent_path}.{field}[{child_id}]"
                previous_id = context[child_key]
                context[child_key] = child_id
                child_evidence = child.get("evidence_ref", evidence)
                # Emit each source object exactly once, not a quadratic copy
                # of all its descendants under both guide and step issues.
                summary = {
                    key: value for key, value in child.items()
                    if key not in {"steps", "actions"}
                }
                report(
                    ("MISSING_" if missing else "EXTRA_") + child_kind.upper(),
                    child_path,
                    summary if missing else None,
                    None if missing else summary,
                    child_evidence if missing else evidence,
                )
                report_descendants(child, child_path, child_kind, missing, child_evidence)
                context[child_key] = previous_id

        target = _ID_KEYS[kind]
        for identifier in lhs_order:
            if identifier not in rhs:
                previous_id = context[target]
                context[target] = identifier
                report("MISSING_" + kind.upper(), f"{path}[{identifier}]",
                       {"id": identifier, "title": lhs[identifier].get("title")},
                       None, lhs[identifier].get("evidence_ref", parent_evidence))
                report_descendants(lhs[identifier], f"{path}[{identifier}]", kind, True,
                                   lhs[identifier].get("evidence_ref", parent_evidence))
                context[target] = previous_id
        for identifier in rhs_order:
            if identifier not in lhs:
                previous_id = context[target]
                context[target] = identifier
                report("EXTRA_" + kind.upper(), f"{path}[{identifier}]", None,
                       {"id": identifier, "title": rhs[identifier].get("title")}, parent_evidence)
                report_descendants(rhs[identifier], f"{path}[{identifier}]", kind, False,
                                   parent_evidence)
                context[target] = previous_id
        shared_lhs = [x for x in lhs_order if x in rhs]
        shared_rhs = [x for x in rhs_order if x in lhs]
        if shared_lhs != shared_rhs:
            report("ORDER_CHANGED", path, shared_lhs, shared_rhs, parent_evidence)
        previous = context[kind + "_id"] if kind != "step" else context["source_step_id"]
        target = {"guide": "guide_id", "step": "source_step_id", "action": "action_id"}[kind]
        for identifier in shared_lhs:
            context[target] = identifier
            evidence = lhs[identifier].get("evidence_ref", parent_evidence)
            if type(lhs[identifier][key]) is not type(rhs[identifier][key]):
                report("TYPE_MISMATCH", f"{path}[{identifier}].{key}",
                       lhs[identifier][key], rhs[identifier][key], evidence)
            walk({k: v for k, v in lhs[identifier].items() if k != key},
                 {k: v for k, v in rhs[identifier].items() if k != key},
                 f"{path}[{identifier}]", evidence)
            context[target] = previous

    # A matching but invalid schema version is not valid parity. Historical
    # comparator fixtures omit this optional field, but a declared version
    # must be an integer v1 on both sides (bool is not an integer schema).
    for side, document in (("reference", reference), ("atlas", atlas)):
        if "schema_version" in document and (
            type(document["schema_version"]) is not int
            or document["schema_version"] != 1
        ):
            report("UNVERIFIABLE", f"{side}.schema_version",
                   "integer schema_version=1", document["schema_version"])
    if reference.get("reference_verified") is not True or reference.get("rights_verified") is not True:
        report("UNVERIFIABLE", "reference.provenance",
               "independent source and rights evidence", "not verified")
    if reference.get("complete") is not True:
        report("UNVERIFIABLE", "reference.complete", True, reference.get("complete"))
    # Atlas exports may omit source-only provenance claims. Explicit false
    # declarations must not be silently discarded by the parity comparison.
    for flag in ("complete", "rights_verified", "reference_verified"):
        if flag in atlas and atlas[flag] is not True:
            report("UNVERIFIABLE", f"atlas.{flag}", True, atlas[flag])
    if not isinstance(reference.get("guides"), list) or not reference["guides"]:
        report("UNVERIFIABLE", "reference.guides", "nonempty complete guide inventory",
               reference.get("guides"))
    # Report complete inventories even when a whole guide is missing and
    # fail closed on matching-but-empty source and Atlas documents.
    def inventory(document: dict[str, Any], side: str) -> None:
        rows = document.get("guides")
        inspected[f"{side}_full_guides"] = len(rows) if isinstance(rows, list) else 0
        inspected[f"{side}_full_steps"] = 0
        inspected[f"{side}_full_actions"] = 0
        if not isinstance(rows, list) or not rows:
            report("UNVERIFIABLE", f"{side}.guides", "nonempty guide inventory", rows)
            return
        for gi, guide in enumerate(rows):
            if not isinstance(guide, dict):
                report("UNVERIFIABLE", f"{side}.guides[{gi}]", "guide object", guide)
                continue
            if not isinstance(guide.get("title"), str) or not guide["title"].strip():
                report("UNVERIFIABLE", f"{side}.guides[{gi}].title",
                       "nonempty guide title", guide.get("title"))
            steps = guide.get("steps")
            if not isinstance(steps, list) or not steps:
                report("UNVERIFIABLE", f"{side}.guides[{gi}].steps",
                       "nonempty ordered steps", steps)
                continue
            inspected[f"{side}_full_steps"] += len(steps)
            for si, step in enumerate(steps):
                if not isinstance(step, dict):
                    report("UNVERIFIABLE", f"{side}.guides[{gi}].steps[{si}]",
                           "step object", step)
                    continue
                prefix = f"{side}.guides[{gi}].steps[{si}]"
                if not isinstance(step.get("title"), str) or not step["title"].strip():
                    report("UNVERIFIABLE", f"{prefix}.title",
                           "nonempty step title", step.get("title"))
                if step.get("coordinates") is not None and not _valid_position(
                    step["coordinates"]
                ):
                    report("UNVERIFIABLE", f"{prefix}.coordinates",
                           "[integer x, integer y] in verified bounds",
                           step["coordinates"])
                for field in ("quest_ids", "quest_names", "prerequisites"):
                    values = step.get(field, [])
                    if not isinstance(values, list):
                        report("UNVERIFIABLE", f"{prefix}.{field}",
                               "structured list", values)
                for quest_idx, quest_id in enumerate(
                    step.get("quest_ids", []) if isinstance(step.get("quest_ids", []), list)
                    else []
                ):
                    if type(quest_id) is not int or quest_id <= 0:
                        report("UNVERIFIABLE", f"{prefix}.quest_ids[{quest_idx}]",
                               "positive integer quest ID", quest_id)
                if isinstance(step.get("quest_names", []), list):
                    for quest_idx, quest_name in enumerate(step.get("quest_names", [])):
                        if not isinstance(quest_name, str) or not quest_name.strip():
                            report("UNVERIFIABLE", f"{prefix}.quest_names[{quest_idx}]",
                                   "nonempty quest name", quest_name)
                if isinstance(step.get("prerequisites", []), list):
                    for gate_idx, gate in enumerate(step.get("prerequisites", [])):
                        if not isinstance(gate, dict) or not gate:
                            report("UNVERIFIABLE", f"{prefix}.prerequisites[{gate_idx}]",
                                   "nonempty structured gate object", gate)
                actions = step.get("actions")
                if not isinstance(actions, list) or not actions:
                    report("UNVERIFIABLE",
                           f"{side}.guides[{gi}].steps[{si}].actions",
                           "nonempty ordered actions", actions)
                    continue
                inspected[f"{side}_full_actions"] += len(actions)
                previous_rank = -1
                for ai, action in enumerate(actions):
                    action_path = f"{prefix}.actions[{ai}]"
                    if not isinstance(action, dict):
                        report("UNVERIFIABLE", action_path, "action object", action)
                        continue
                    kind = action.get("kind")
                    if not isinstance(kind, str) or kind not in _KNOWN_ACTION_KINDS:
                        report("UNVERIFIABLE", f"{action_path}.kind",
                               "supported action kind", kind)
                    section = action.get("section", _DEFAULT_SECTION.get(kind, "now"))
                    if not isinstance(section, str) or section not in _VALID_SECTIONS:
                        report("UNVERIFIABLE", f"{action_path}.section",
                               "supported shared UI section", section)
                    elif section == "prepare":
                        if kind != "prepare":
                            report("UNVERIFIABLE", f"{action_path}.section",
                                   "only prepare actions in the inventory panel", section)
                        if previous_rank >= 0:
                            report("UNVERIFIABLE", f"{action_path}.section",
                                   "preparation before all other visible actions",
                                   section)
                    elif kind == "prepare":
                        report("UNVERIFIABLE", f"{action_path}.section",
                               "prepare action belongs in the inventory panel", section)
                        rank = _RENDER_ORDER.index(section)
                        if rank < previous_rank:
                            report("UNVERIFIABLE", f"{action_path}.section",
                                   "monotonic shared UI section order", section)
                        previous_rank = max(previous_rank, rank)
                    else:
                        rank = _RENDER_ORDER.index(section)
                        if rank < previous_rank:
                            report("UNVERIFIABLE", f"{action_path}.section",
                                   "monotonic shared UI section order", section)
                        previous_rank = max(previous_rank, rank)
                    # The canonical shared UI places section=prepare in its
                    # dedicated item panel. A pair of identical non-item
                    # actions in that section is not renderable as preparation.
                    if section == "prepare" and (
                        not isinstance(action.get("items"), list)
                        or not action["items"]
                    ):
                        report(
                            "UNVERIFIABLE", f"{action_path}.items",
                            "nonempty structured preparation items",
                            action.get("items"),
                        )
                    text = action.get("text")
                    if not isinstance(text, str) or not text.strip():
                        report("UNVERIFIABLE", f"{action_path}.text",
                               "nonempty action text", text)
                    npc = action.get("npc")
                    if npc is not None and (
                        not isinstance(npc, str) or not npc.strip()
                    ):
                        report("UNVERIFIABLE", f"{action_path}.npc",
                               "nonempty NPC name", npc)
                    if action.get("coordinates") is not None and not _valid_position(
                        action["coordinates"]
                    ):
                        report("UNVERIFIABLE", f"{action_path}.coordinates",
                               "[integer x, integer y] in verified bounds",
                               action["coordinates"])
                    if kind == "travel" and not (
                        _valid_position(action.get("coordinates"))
                        or _valid_position(step.get("coordinates"))
                    ):
                        report("UNVERIFIABLE", f"{action_path}.coordinates",
                               "verified travel position", action.get("coordinates"))
                    for field in ("items", "monsters"):
                        entries = action.get(field)
                        if entries is None:
                            if (field == "items" and kind in _ITEM_ACTION_KINDS) or (
                                field == "monsters" and kind in {"fight", "combat"}
                            ):
                                report("UNVERIFIABLE", f"{action_path}.{field}",
                                       "nonempty structured list", entries)
                            continue
                        required = (
                            (field == "items" and kind in _ITEM_ACTION_KINDS)
                            or (field == "monsters" and kind in {"fight", "combat"})
                        )
                        if not isinstance(entries, list) or (required and not entries):
                            report("UNVERIFIABLE", f"{action_path}.{field}",
                                   "nonempty structured list" if required else "structured list",
                                   entries)
                            continue
                        for item_index, item in enumerate(entries):
                            item_path = f"{action_path}.{field}[{item_index}]"
                            if not isinstance(item, dict):
                                report("UNVERIFIABLE", item_path,
                                       "structured resource or monster", item)
                                continue
                            name, quantity = item.get("name"), item.get("quantity")
                            if not isinstance(name, str) or not name.strip():
                                report("UNVERIFIABLE", f"{item_path}.name",
                                       "nonempty name", name)
                            if type(quantity) is not int or quantity <= 0:
                                report("UNVERIFIABLE", f"{item_path}.quantity",
                                       "positive integer", quantity)
                            if field == "items" and item.get("item_id") is not None:
                                item_id = item["item_id"]
                                if type(item_id) is not int or item_id <= 0:
                                    report(
                                        "UNVERIFIABLE", f"{item_path}.item_id",
                                        "positive integer item ID", item_id,
                                    )

    inventory(reference, "reference")
    inventory(atlas, "atlas")
    # Only reference-authorization flags live outside the projected Atlas
    # payload. All other top-level fields, including schema_version and
    # unexpected extras, are part of the diff contract.
    provenance = frozenset({"reference_verified", "rights_verified", "complete"})
    walk({key: value for key, value in reference.items() if key not in provenance},
         {key: value for key, value in atlas.items() if key not in provenance},
         "", None)
    issues.sort(key=lambda x: (str(x["guide_id"]), str(x["source_step_id"]),
                               str(x["action_id"]), x["field_path"], x["issue_code"]))
    return {
        "schema_version": 1, "reference_sha256": _digest(reference),
        "atlas_sha256": _digest(atlas),
        "status": "PARITY_CHECK_PASS" if not issues else "PARITY_CHECK_BLOCKED",
        "certified": False, "reason": "Gameplay, permissions and Windows proof are independent",
        "coverage": dict(inspected), "issue_count": len(issues),
        "issue_codes": dict(sorted(Counter(x["issue_code"] for x in issues).items())),
        "issues": issues,
    }


def before_after(reference: dict[str, Any], before: dict[str, Any],
                 after: dict[str, Any]) -> dict[str, Any]:
    """Compare two snapshots against ONE pinned reference; expose all regressions."""
    a, b = compare(reference, before), compare(reference, after)
    def grouped(report: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {}
        for issue in report["issues"]:
            identity = _digest([
                issue["issue_code"], issue["field_path"], issue["guide_id"],
                issue["source_step_id"], issue["action_id"],
                issue["expected"],
            ])
            # Include the independent *reason* for each finding. A malformed
            # coordinate and a missing travel position share the same code
            # and path but have different expected contracts. Pairing them by
            # arrival order would mark the wrong defect as persistent. The
            # expected value stays pinned to the one reference; actual
            # observations may change without falsely resolving an issue.
            result.setdefault(identity, []).append(issue)
        return result

    old, new = grouped(a), grouped(b)
    resolved: list[dict[str, Any]] = []
    introduced: list[dict[str, Any]] = []
    persistent: list[dict[str, Any]] = []
    for identity in sorted(old.keys() | new.keys()):
        previous, current = old.get(identity, []), new.get(identity, [])
        shared = min(len(previous), len(current))
        persistent.extend({
            "before": previous[i], "after": current[i],
            "changed": previous[i] != current[i],
        } for i in range(shared))
        resolved.extend(previous[shared:])
        introduced.extend(current[shared:])
    return {
        "schema_version": 1, "reference_sha256": a["reference_sha256"],
        "before_sha256": a["atlas_sha256"], "after_sha256": b["atlas_sha256"],
        "before_status": a["status"], "after_status": b["status"],
        "resolved": resolved,
        "persistent": persistent,
        "introduced": introduced,
        "certified": False, "status": b["status"],
    }


def _load_strict_json(path: Path) -> dict[str, Any]:
    """Parse only unambiguous, RFC-compatible JSON exports at the CLI boundary."""
    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    def reject_nonfinite(value: str) -> Any:
        raise ValueError(f"non-finite JSON constant {value!r}")

    def finite_float(raw: str) -> float:
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError(f"out-of-range JSON float {raw!r}")
        return value

    document = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=unique_pairs,
        parse_constant=reject_nonfinite,
        parse_float=finite_float,
    )
    if not isinstance(document, dict):
        raise ValueError("JSON root must be an object")
    return document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline independent guide conformity reports")
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        ref, old, new = (
            _load_strict_json(args.reference),
            _load_strict_json(args.before),
            _load_strict_json(args.after),
        )
    except (OSError, ValueError) as exc:
        parser.error(f"invalid or ambiguous source JSON: {exc}")
    prior, current = compare(ref, old), compare(ref, new)
    delta = before_after(ref, old, new)
    # Reports must never overwrite any Atlas data, guide, user state or
    # prior audit evidence. A fresh output directory is mandatory.
    if ".." in args.output_dir.parts:
        parser.error("parent traversal in report output is forbidden")
    output = args.output_dir.absolute()
    if any(part.casefold() in {"data", ".git", "saves", "profiles", "user_data"}
           for part in output.parts):
        parser.error("output directory must be outside Atlas data and saves")
    if output.is_symlink() or any(parent.is_symlink() for parent in output.parents):
        parser.error("symlinked output directories are forbidden")
    source_root = Path(__file__).resolve().parents[1]
    try:
        within_checkout = output.relative_to(source_root)
    except ValueError:
        within_checkout = None
    if within_checkout is not None and (
        len(within_checkout.parts) < 2
        or within_checkout.parts[0].casefold() != "artifacts"
    ):
        parser.error("report output must be outside repository sources or under artifacts/")
    try:
        output.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        parser.error(f"output directory must be new: {exc}")
    for filename, payload in (("before.json", prior), ("after.json", current),
                              ("before_after.json", delta)):
        with (output / filename).open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
    print(json.dumps({"status": current["status"], "issues": current["issue_count"],
                      "output_dir": str(args.output_dir)}, ensure_ascii=False))
    return 0 if not current["issues"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
