# Tests-local agent guidance

The root `AGENTS.md` and project guardrails still apply.

Inside `tests/`:

- tests describe required behavior and regression contracts; do not rewrite expectations merely to accept a product bug;
- when behavior intentionally changes, change the product and the smallest relevant tests together with a clear reason;
- keep critical tests meaningful: no empty assertions, unconditional skips or broad exception swallowing;
- prefer targeted regression coverage for a root-cause fix instead of duplicating large suites;
- preserve the distinction between targeted validation, full suite and phase certification.
