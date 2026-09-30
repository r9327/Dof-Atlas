# Canonical Guide tools

Diagnostic command during Phase 7E consolidation:

```powershell
py -3.13 -m tools.guide_tools_cli doctor
```

Canonical modules are intentionally unversioned. `tools.agent doctor` remains the project-wide diagnostic command; this Guide-specific doctor is the focused dependency surface that can be wired into it without reviving legacy wrappers.
