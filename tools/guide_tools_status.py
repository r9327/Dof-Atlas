from __future__ import annotations

"""Machine-readable consolidation state consumed by future doctor integration."""

STATUS = {
    "schema_version": 1,
    "canonical": {
        "gps": "tools.guide_gps",
        "forensic": "tools.guide_forensic",
        "transversals": "tools.validate_guide_ultime_manual_transversals",
        "structured_contracts": "tools.guide_integrity_contracts",
    },
    "retired": [
        "tools.build_guide_ultime_gps_route_strict",
        "tools.audit_guide_ultime_route_forensic_v2",
        "tools.validate_guide_ultime_manual_transversals_v16",
    ],
}
