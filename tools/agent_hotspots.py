from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

from tools import agent, atlas_integrity


ROOT = agent.ROOT
HOTSPOT_RISK_LEVELS = {"HIGH", "CRITICAL"}
HOTSPOT_MIN_SHARED_CONSUMERS = 2


def _shared_dependency_consumers(
    manifests: dict[str, dict[str, Any]],
) -> dict[str, list[str]]:
    consumers = {scope: [] for scope in manifests}
    for consumer_scope, manifest in manifests.items():
        for dependency in manifest.get("shared_dependencies", []):
            if dependency not in consumers:
                continue
            if consumer_scope not in consumers[dependency]:
                consumers[dependency].append(consumer_scope)
    return consumers


def _scope_hotspot_detail(
    context_map: dict[str, Any],
    manifests: dict[str, dict[str, Any]],
    consumers: dict[str, list[str]],
    scope: str,
) -> dict[str, Any] | None:
    config = context_map["scopes"][scope]
    manifest = manifests[scope]
    if agent._scope_implementation(config, manifest) == "placeholder":
        return None

    review_entries = agent._unique(
        [
            *manifest.get("working_set", []),
            *config.get("canonical_entries", []),
        ]
    )
    risk = atlas_integrity.classify_risk(review_entries)
    consumer_scopes = list(consumers.get(scope, []))
    indicators: list[str] = []
    if risk["risk"] in HOTSPOT_RISK_LEVELS:
        indicators.append(f"risk:{risk['risk']}")
    if len(consumer_scopes) >= HOTSPOT_MIN_SHARED_CONSUMERS:
        indicators.append("shared_dependency:multiple_consumers")
    if not indicators:
        return None

    return {
        "scope": scope,
        "kind": config.get("kind"),
        "risk": risk["risk"],
        "risk_reasons": list(risk.get("reasons", [])),
        "affected_groups": list(risk.get("affected_groups", [])),
        "consumer_scopes": consumer_scopes,
        "consumer_count": len(consumer_scopes),
        "indicators": indicators,
        "review_entries": review_entries,
    }


def hotspots_payload(
    root: Path = ROOT,
    scopes: Iterable[str] | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    context_map, manifests = agent._model(root)
    selected = agent._unique(scopes or context_map["scopes"].keys())
    unknown = [scope for scope in selected if scope not in context_map["scopes"]]
    if unknown:
        raise agent.AgentConfigError(f"unknown scope: {unknown[0]}")

    consumers = _shared_dependency_consumers(manifests)
    hotspots: list[dict[str, Any]] = []
    for scope in selected:
        detail = _scope_hotspot_detail(context_map, manifests, consumers, scope)
        if detail is not None:
            hotspots.append(detail)

    return {
        "schema_version": 1,
        "source": "atlas-integrity-risk-and-scope-dependencies",
        "mode": "INFORMATIONAL",
        "blocking": False,
        "selection": {
            "risk_levels": sorted(HOTSPOT_RISK_LEVELS),
            "min_shared_consumers": HOTSPOT_MIN_SHARED_CONSUMERS,
        },
        "scopes": selected,
        "hotspot_count": len(hotspots),
        "hotspots": hotspots,
    }


def _print_payload(payload: dict[str, Any]) -> None:
    print(f"mode: {payload['mode']}")
    print(f"blocking: {payload['blocking']}")
    print(f"hotspot_count: {payload['hotspot_count']}")
    for item in payload["hotspots"]:
        indicators = ", ".join(item["indicators"])
        consumers = ", ".join(item["consumer_scopes"]) or "none"
        print(
            f"- {item['scope']}: risk={item['risk']}; "
            f"consumers={consumers}; indicators={indicators}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Informational ROAD IA V2 hotspot report; never a product gate."
    )
    parser.add_argument("scopes", nargs="*")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        payload = hotspots_payload(ROOT, args.scopes)
    except (agent.AgentConfigError, RuntimeError, OSError) as exc:
        print(f"agent hotspots error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        _print_payload(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
