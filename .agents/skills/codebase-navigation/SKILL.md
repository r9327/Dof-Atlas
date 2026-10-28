---
name: codebase-navigation
description: Locate canonical Dofus Atlas owners, consumers and scoped tests before unfamiliar or cross-module changes.
---

# codebase navigation

Use for unfamiliar code, uncertain ownership or cross-module tasks. Skip the extra routing work for a trivial known-file edit.

1. Read `AI_ENTRYPOINT.md`, `AGENTS.md`, `AI_CONTEXT.md` and any nested `AGENTS.md`.
2. Inspect the real HEAD, worktree and affected source before planning a change.
3. Use `py -3.13 -m tools.ai_context status` and `py -3.13 -m tools.ai_context route <paths>`.
4. For non-trivial edits use Doctor's canonical `agent plan` and respect its edit contract, checks and guardians.
5. Find the canonical implementation and its consumers. For structural impact, follow `GRAPHIFY.md` and require an exact-candidate-SHA graph.
6. Summarize real ownership, dependency paths, existing tests and unknowns without inventing a second context index or claiming unavailable checks.
