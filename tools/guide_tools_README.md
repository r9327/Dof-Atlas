# Canonical Guide tools

Diagnostic command:

```powershell
py -3.13 -m tools.guide_tools_cli doctor
```

Canonical modules are intentionally unversioned. `tools.agent doctor` remains the project-wide diagnostic command; this Guide-specific doctor is the focused dependency surface that can be wired into it without reviving legacy wrappers.

Canonical entry points:

- `tools.guide_gps`: player-safe GPS generation;
- `tools.guide_forensic`: forensic validation;
- `tools.validate_guide_ultime_manual_transversals`: transversal validation;
- `tools.guide_tools`: stable Guide Integrity facade.

The semantic boundary is `tools.guide_integrity_contracts`. Runtime and UI producers normalize action dictionaries into `GuideAction` values so Guide Integrity can validate structured data instead of rendered text. Text heuristics remain compatibility diagnostics and must not be promoted blindly from REVIEW to HARD.

Historical versioned wrappers and mutators remain retired. The canonical transversal entry delegates to the retained v15 engine; older implementations remain available in Git history rather than as parallel entry points.

Audit output retention is bounded. Local Guide archive rotation keeps the four most recent runs under `artifacts/archive/guide_ultime/`; fixed-name Doctor and Guide reports overwrite their previous output. Routine GitHub audit artifacts expire after four days, while phase-certification evidence keeps its longer dedicated retention.
