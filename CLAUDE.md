# Claude — Dofus Atlas

Read `AI_ENTRYPOINT.md` first; read root and nested `AGENTS.md` files for the scope.
Doctor is the mandatory **planning and validation control plane** for every
non-trivial code change, not a replacement for implementing or reviewing code.

1. Before editing, invoke `py -3.13 -X utf8 -m tools.atlas_doctor agent plan <paths> --base-ref HEAD --json`.
2. Implement only the reviewed edit contract; use exact-SHA Graphify evidence before structural changes.
3. After editing, invoke `py -3.13 -X utf8 -m tools.atlas_doctor agent check <paths> --base-ref HEAD --run-tests --json`.
4. Before marking a PR ready, invoke `py -3.13 -X utf8 -m tools.atlas_doctor agent validate <paths> --base-ref HEAD --json` and audit every commit, then the whole PR.

Consult `tools/skills/dofus-atlas-tools/SKILL.md` and `tools.tool_catalog`
for safe, owner-approved specialist tools. The `oss_selection` plan is advisory:
a tool recommended by Doctor is **not** proof that it is installed or executed.
`oss_advisory.execution_summary` and `doctor oss --verify-live` provide
separate local evidence. Never claim Windows-PC validation from hosted CI.
Keep Draft until development and targeted checks are complete; follow the
existing exact-SHA Phase Certification before merging.
