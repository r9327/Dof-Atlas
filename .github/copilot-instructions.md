# GitHub Copilot entrypoint

Read `/AI_ENTRYPOINT.md` before editing. Start non-trivial work with
`py -3.13 -X utf8 -m tools.atlas_doctor agent plan <paths> --base-ref HEAD --json`
and obey the returned edit contract, checks and forbidden claims.

For **every** PR: keep Draft until the entire scope and focused local tests
are complete. Do not run GitHub CI on intermediate commits. Mark Ready for
review only when the final candidate is complete; certify that exact SHA once,
then fix and recertify only if necessary. Read AGENTS.md for the global rule.

Read the machine-readable `ai_tool_workflow` in each Doctor JSON report;
recommended native/OSS tools do not count as executed until their owner
returns real evidence. Follow `AI_ENTRYPOINT.md` for authority and CI cadence.

For each relevant edit, consume Doctor's `agent plan` → `agent check --run-tests`
→ `agent validate` JSON phases. Discover only safe, automation-ready owner
tools with `py -3.13 -m tools.tool_catalog --preferred-only --safe-only --ready-only --json`
and follow `tools/skills/dofus-atlas-tools/SKILL.md`. Separate selected,
available, actually executed and certified evidence. See
`docs/doctor-oss-routing.md` for the explicit Windows Ruff/zizmor `--verify-live`
qualification; missing tools are not PASS.
