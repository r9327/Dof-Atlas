# Guide tools consolidation

Canonical entry points introduced by the Phase 7E tool consolidation:

- `tools.guide_gps`: player-safe GPS generation entry point.
- `tools.guide_forensic`: forensic validation with the corrected Bonta Order rank contract.
- `tools.validate_guide_ultime_manual_transversals`: canonical transversal validator.
- `tools.guide_tools`: stable facade for Guide Integrity / agent integration.

The historical GPS and forensic base implementations remain internal dependencies until their large bodies can be absorbed safely without changing behavior. Versioned/strict wrappers are retired and must not be reintroduced.

## Historical transversal family retirement

The `validate_guide_ultime_manual_transversals_v2.py` through `_v14.py` scripts are retired. The consumer/replacement review was performed on `7f77670cac674ff5903a5fbd342043953c9b8a2b` before deletion ([tracked-tree proof](https://github.com/r9327/Dof-Atlas/actions/runs/36784373709)).

Evidence:

- `tools.tool_audit` and a case-insensitive search of every tracked file found no consumer outside the historical family. The broader transversal stem search covered indirect selectors, source, tests, docs, AGENTS, hooks, workflows and Windows scripts.
- Versions 2–8 were standalone historical validators. The only references to versions 9–14 were the import chain 14 → 13 → 12 → 11 → 10 → 9. No current entry point consumed its head.
- Their historical chapter/temporal contracts belong to earlier manifests. The [canonical entry](validate_guide_ultime_manual_transversals.py) owns current manifest compatibility and delegates to the independent [v15 implementation](validate_guide_ultime_manual_transversals_v15.py), including the current 267-stage contract. That implementation does not import the retired family.
- Current consumers already use the canonical entry: `guide_integrity.py`, `guide_integrity_entrypoints.py`, `guide_tools.py`, `guide_tools_status.py`, `run_guide_ultime_ci.ps1`, and the canonical transversal / final-validator / CI-runner tests.

The canonical entry and v15 engine keep their existing rules and bytes. Retirement removes the closed historical family atomically; historical sources remain available in Git history. Targeted Guide tests, Atlas Integrity and full exact-HEAD certification validate the resulting tree.

Remaining versioned tools are retained by evidence:

- `guide_ultime_scope_v4.py`: `tests/test_guide_ultime_v4_scope.py`.
- `guide_ultime_scope_v5.py`: the adventure route adapter, v5 scope tests, forensic audit and final builder.
- `apply_verified_guides_v2.py` / `v3.py`: historical mutators with no proven canonical replacement; zero consumers remains a review signal.
- The v15 transversal engine: internal dependency of the canonical entry, not a preferred command.

GPS, forensic, Guide Integrity, the Guide facade and structured actions keep their canonical entry points.
