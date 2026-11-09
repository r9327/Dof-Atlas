# Claude entrypoint

Read `AI_ENTRYPOINT.md` first and use `tools.atlas_doctor agent` for every
non-trivial code change. Repository `AGENTS.md` files and the paths returned by
Doctor remain authoritative.

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
