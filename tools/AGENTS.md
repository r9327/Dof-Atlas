# Tooling-local agent guidance

The root `AGENTS.md`, `ZERO_TRUST_RULES.md` and certification rules still apply.

Inside `tools/`:

- audits, gates and baselines exist to detect product regressions; do not weaken them to make a failing build green;
- prefer deterministic, inspectable scripts with explicit non-zero exit codes on failure;
- keep FAST/local checks reasonably cheap and reserve expensive full validation for the existing full/certification paths;
- changes to integrity, certification, mutation, coverage, performance or hook tooling require targeted tests;
- generated metadata must be reproducible from the repository and must not become a second manual source of truth.

AI-facing tooling contract for new or modernized entry points:

- prefer callable Python modules and module execution (`py -3.13 -m tools.<name>`) over ad-hoc launch-only scripts when platform-specific shell behavior is not required;
- expose stable machine-readable output (`--json`) with an explicit `schema_version` for agent-consumable commands;
- keep diagnostic/discovery commands read-only by default; any repository mutation must require an explicit apply/write/repair-style opt-in and remain obvious in help/output;
- anchor paths from the repository/tool location rather than the caller's current working directory; do not add `sys.path` hacks;
- keep CLI parsing thin and reusable logic callable as Python functions so orchestrators and agents compose engines instead of spawning duplicate scripts;
- prefer one canonical implementation per contract; versioned wrappers and compatibility shims are temporary and must not become the default agent entry point;
- make failures structured and deterministic where practical, while retaining useful human-readable summaries;
- document or expose a cost/mode boundary for commands that can become expensive; route broad FAST/FULL/DEEP validation through canonical orchestrators rather than teaching agents many equivalent commands;
- every executable tool intended for recurring use needs targeted contract tests before it is promoted as a preferred AI entry point;
- `tools.tool_audit` and `tools.tool_catalog` are read-only derived views: use them to discover consolidation/readiness issues, never as sole proof that a file is dead or safe to delete.
