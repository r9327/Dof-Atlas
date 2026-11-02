# GitHub Copilot — Dofus Atlas

Read `/AI_ENTRYPOINT.md` and relevant `AGENTS.md` files before editing.
For every non-trivial code change, follow the one canonical Doctor cycle:

```powershell
py -3.13 -X utf8 -m tools.atlas_doctor agent plan <paths> --base-ref HEAD --json
# implement only the reviewed scope
py -3.13 -X utf8 -m tools.atlas_doctor agent check <paths> --base-ref HEAD --run-tests --json
py -3.13 -X utf8 -m tools.atlas_doctor agent validate <paths> --base-ref HEAD --json
```

Read the returned edit contract, selected checks and blockers; do not treat
`REVIEW`, `BLOCKED`, `NOT_AVAILABLE` or `NOT_RUN` as PASS. For structural
work use the exact-SHA Graphify evidence required by `GRAPHIFY.md`.
Use `tools/skills/dofus-atlas-tools/SKILL.md` and the derived
`tools.tool_catalog` to choose only owner-approved, automation-ready
specialists. `oss_selection` recommends; `oss_advisory.execution_summary`
reports actual scanner results; neither is a Phase Certification.

For **every PR**, stay Draft while implementing and testing; audit each
commit and the integrated diff, then mark Ready only after the final scope is
complete. Use existing exact-SHA Phase Certification, not repeated intermediate
full CI. A hosted runner does not prove installation or acceptance on the
user's Windows PC (see `docs/doctor-oss-routing.md` and issue #346).
