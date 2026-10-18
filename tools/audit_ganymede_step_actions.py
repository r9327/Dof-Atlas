"""Non-destructive factual action candidate audit for Ganymède source steps."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from tools.audit_ganymede_master_refs import ROOT

DIRECTORY = Path("data/encyclopedia/guides")
DEFAULT = DIRECTORY / "ganymede_2205_action_candidates.json"
KINDS = {"guide_dependency", "quest_prerequisite", "prepare_object",
         "optional_preparation", "quest_start", "quest_finish",
         "talk", "interact", "move", "drop_object",
         "optional_delivery", "check_object", "collect_object", "craft", "group_mechanic", "optional_capture", "optional_drop", "check_equipment", "equip", "goal_reward", "combat", "dungeon", "repeat_interaction"}


def audit_action_candidates(root: Path, path: Path = DEFAULT) -> dict:
    root = Path(root).resolve()
    path = path if path.is_absolute() else root / path
    issues = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        gid = data["source_guide_id"]
        matching = []
        for source in (root / DIRECTORY).glob("ganymede_*_observed_links.json"):
            obj = json.loads(source.read_text(encoding="utf-8"))
            if obj.get("source", {}).get("guide_id") == gid:
                matching.append(obj)
        if len(matching) != 1:
            raise ValueError("source snapshot missing or duplicated")
        raw = matching[0]
        raw_steps = raw["steps"]
        by_number = {s["source_step_number"]: s for s in raw_steps}
        if len(by_number) != len(raw_steps) or len(raw_steps) != data["source_step_count"]:
            raise ValueError("invalid source step cardinality")
        if (data.get("certified_actions") != 0 or
                data.get("ready_to_replace") is not False or
                data.get("editorial_text_copied") is not False):
            raise ValueError("candidate evidence cannot certify replacement")
        observed = set()
        previous = 0
        for step in data["steps"]:
            num = step["source_step_number"]
            if type(num) is not int or num <= previous or num not in by_number:
                issues.append(f"duplicate, unordered or unknown step: {num}")
                continue
            previous = num
            observed.add(num)
            source = by_number[num]
            if step.get("stable_step_id") != f"ganymede_{gid}_step_{num:04d}":
                issues.append(f"unstable stage ID: {num}")
            if (step.get("review_status") != "REVIEW_SOURCE_ACTION" or
                    step.get("quest_objectives_verified") is not False):
                issues.append(f"false objective certification: {num}")
            for name in ("at", "next"):
                if step.get(name) not in source["coordinate_mentions"]:
                    issues.append(f"unobserved {name} coordinate: {num}")
            actions = step.get("actions")
            if not isinstance(actions, list) or not actions:
                issues.append(f"missing factual actions: {num}")
                continue
            for action in actions:
                kind = action.get("kind")
                if kind not in KINDS or not isinstance(action.get("label"), str) or not action["label"].strip():
                    issues.append(f"invalid action type/label: {num}")
                    continue
                for name, ns in (("quest_id", "quest"), ("object_id", "object"), ("monster_id", "monster"), ("dungeon_id", "dungeon")):
                    if name in action and (type(action[name]) is not int or
                                            action[name] not in source["external_dofusdb_ids"][ns]):
                        issues.append(f"unobserved {name}: {num}")

                for plural, ns in (("object_ids", "object"),):
                    if plural in action and (not isinstance(action[plural], list) or
                                             any(type(v) is not int or v not in source["external_dofusdb_ids"][ns]
                                                 for v in action[plural])):
                        issues.append(f"unobserved {plural}: {num}")
                if "participants_min" in action and (type(action["participants_min"]) is not int or action["participants_min"] < 1):
                    issues.append(f"invalid participants_min: {num}")
                if "guide_id" in action and action["guide_id"] not in source["linked_guide_ids"]:
                    issues.append(f"unobserved guide link: {num}")
                if "quantity" in action and (type(action["quantity"]) is not int or action["quantity"] <= 0):
                    issues.append(f"invalid quantity: {num}")
        return {"status": "FAIL" if issues else "REVIEW_ACTION_CANDIDATES_ONLY",
                "source_guide_id": gid, "source_steps": len(raw_steps),
                "reviewed_steps": len(observed), "remaining_steps": len(raw_steps) - len(observed),
                "certified_actions": 0, "ready_to_replace": False, "issues": issues}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return {"status": "FAIL", "certified_actions": 0,
                "ready_to_replace": False, "issues": [str(exc)]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--candidate", type=Path, default=DEFAULT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit_action_candidates(args.root, args.candidate)
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 1 if report["status"] == "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
