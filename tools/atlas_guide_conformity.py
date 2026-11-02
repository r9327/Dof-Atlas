"""Independent, read-only, fail-closed semantic diff of authorized guide exports.

This module intentionally has no imports from the retired PR #337 or from the Qt
runtime. PARITY_PASS is a data comparison result, NEVER a gameplay certificate.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

# Evidence locators document how to verify a source and do not need to
# appear as displayed Atlas gameplay fields. Every other field, including
# source_url, coordinates, media links, complete and capture metadata on
# individual actions, MUST be compared; otherwise missing information can
# falsely yield PARITY_CHECK_PASS.
_IGNORED_REFERENCE_KEYS = frozenset({"evidence_ref"})
_ID_KEYS = {"guide": "guide_id", "step": "source_step_id", "action": "action_id"}
_COLLECTIONS = {"guides": "guide", "steps": "step", "actions": "action"}


def _digest(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _snapshot(value: Any) -> Any:
    # Evidence must be complete, not an ellipsized 160-character approximation.
    # Only changed values are copied; the complete source is never mutated.
    return copy.deepcopy(value)


def _identifier(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    result = str(value).strip()
    return result if result else None


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
                "UNVERIFIABLE": "Obtenir une preuve indépendante vérifiable",
            }.get(code, "Examiner la référence et corriger"), "review_required": True,
        })

    if not isinstance(reference, dict) or not isinstance(atlas, dict):
        raise ValueError("Reference and Atlas exports must be JSON objects")

    def walk(expected: Any, actual: Any, path: str, evidence: str | None) -> None:
        inspected["fields"] += 1
        if type(expected) is not type(actual):
            report("TYPE_MISMATCH", path, expected, actual, evidence)
            return
        if isinstance(expected, dict):
            ref_fields = set(expected) - _IGNORED_REFERENCE_KEYS
            atlas_fields = set(actual) - _IGNORED_REFERENCE_KEYS
            for key in sorted(ref_fields - atlas_fields):
                report("MISSING_FIELD", f"{path}.{key}", expected[key], None, evidence)
            for key in sorted(atlas_fields - ref_fields):
                report("EXTRA_FIELD", f"{path}.{key}", None, actual[key], evidence)
            for key in sorted(ref_fields & atlas_fields):
                if key in _COLLECTIONS:
                    collection(expected[key], actual[key], f"{path}.{key}",
                               _COLLECTIONS[key], evidence)
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
            return
        key = _ID_KEYS[kind]
        def index(items: list[Any], side: str) -> tuple[dict[str, dict], list[str]]:
            unique: dict[str, dict] = {}
            order: list[str] = []
            for i, item in enumerate(items):
                identifier = _identifier(item.get(key)) if isinstance(item, dict) else None
                if identifier is None:
                    report("UNVERIFIABLE", f"{path}.{side}[{i}].{key}",
                           f"nonempty {key}", None, parent_evidence)
                    continue
                if identifier in unique:
                    report("DUPLICATE", f"{path}.{side}[{i}].{key}",
                           identifier, identifier, parent_evidence)
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
        target = _ID_KEYS[kind]
        for identifier in lhs_order:
            if identifier not in rhs:
                previous_id = context[target]
                context[target] = identifier
                report("MISSING_" + kind.upper(), f"{path}[{identifier}]",
                       {"id": identifier, "title": lhs[identifier].get("title")},
                       None, lhs[identifier].get("evidence_ref", parent_evidence))
                context[target] = previous_id
        for identifier in rhs_order:
            if identifier not in lhs:
                previous_id = context[target]
                context[target] = identifier
                report("EXTRA_" + kind.upper(), f"{path}[{identifier}]", None,
                       {"id": identifier, "title": rhs[identifier].get("title")}, parent_evidence)
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

    if reference.get("reference_verified") is not True or reference.get("rights_verified") is not True:
        report("UNVERIFIABLE", "reference.provenance",
               "independent source and rights evidence", "not verified")
    if reference.get("complete") is not True:
        report("UNVERIFIABLE", "reference.complete", True, reference.get("complete"))
    if not isinstance(reference.get("guides"), list) or not reference["guides"]:
        report("UNVERIFIABLE", "reference.guides", "nonempty complete guide inventory",
               reference.get("guides"))
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
    def keyed(report: dict[str, Any]) -> dict[str, dict]:
        return {
            _digest([v["issue_code"], v["field_path"], v["guide_id"],
                     v["source_step_id"], v["action_id"]]): v
            for v in report["issues"]
        }
    old, new = keyed(a), keyed(b)
    return {
        "schema_version": 1, "reference_sha256": a["reference_sha256"],
        "before_sha256": a["atlas_sha256"], "after_sha256": b["atlas_sha256"],
        "before_status": a["status"], "after_status": b["status"],
        "resolved": [old[k] for k in sorted(old.keys() - new.keys())],
        # Preserve both observations. A quantity changing 8 -> 9 is still the
        # same unresolved field, but the evolution must not disappear.
        "persistent": [
            {"before": old[k], "after": new[k], "changed": old[k] != new[k]}
            for k in sorted(old.keys() & new.keys())
        ],
        "introduced": [new[k] for k in sorted(new.keys() - old.keys())],
        "certified": False, "status": b["status"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline independent guide conformity reports")
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    def read(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))
    ref, old, new = read(args.reference), read(args.before), read(args.after)
    prior, current = compare(ref, old), compare(ref, new)
    delta = before_after(ref, old, new)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for filename, payload in (("before.json", prior), ("after.json", current),
                              ("before_after.json", delta)):
        (args.output_dir / filename).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": current["status"], "issues": current["issue_count"],
                      "output_dir": str(args.output_dir)}, ensure_ascii=False))
    return 0 if not current["issues"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
