# Tooling-local agent guidance

The root `AGENTS.md`, `ZERO_TRUST_RULES.md` and certification rules still apply.

Inside `tools/`:

- audits, gates and baselines exist to detect product regressions; do not weaken them to make a failing build green;
- prefer deterministic, inspectable scripts with explicit non-zero exit codes on failure;
- keep FAST/local checks reasonably cheap and reserve expensive full validation for the existing full/certification paths;
- changes to integrity, certification, mutation, coverage, performance or hook tooling require targeted tests;
- generated metadata must be reproducible from the repository and must not become a second manual source of truth.
