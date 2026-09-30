# Guide tools consolidation

Canonical entry points introduced by the Phase 7E tool consolidation:

- `tools.guide_gps`: player-safe GPS generation entry point.
- `tools.guide_forensic`: forensic validation with the corrected Bonta Order rank contract.
- `tools.validate_guide_ultime_manual_transversals`: canonical transversal validator.
- `tools.guide_tools`: stable facade for Guide Integrity / agent integration.

The historical GPS and forensic base implementations remain internal dependencies until their large bodies can be absorbed safely without changing behavior. Versioned/strict wrappers are retired and must not be reintroduced.
