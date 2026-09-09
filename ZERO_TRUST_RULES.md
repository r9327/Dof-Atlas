# Dofus Atlas — permanent Zero-Trust rules

This short contract applies to Codex, Work, GPT, humans and other contributors. `DEVELOPMENT_GUARDRAILS.md` remains the detailed authority.

1. Architecture is frozen: do not add runtime patches, new version layers, service locators, DI/plugin frameworks or parallel sources of truth.
2. Reuse the current canonical owner for data, logic, persistence and UI behavior.
3. Every new character-scoped write uses `character:<id_dofus>`; slot/order/PID/name identities are compatibility-read boundaries only.
4. Classify the diff risk before validation: LOW, MEDIUM, HIGH or CRITICAL.
5. Run focused tests for every changed executable contract.
6. Run the Integrity Gate required by risk (`FAST`, `CRITICAL`, `FULL`; `DEEP` is periodic/manual).
7. Never weaken guardrails, audits, discovery, debt baselines, required checks or budgets to obtain green.
8. Never add skip/xfail or swallow a failure to repair a red result.
9. Review the final diff and run `git diff --check` before commit.
10. Never commit runtime/generated files, user state, WAL/SHM, logs, captures, dumps, profiles or transient artifacts.
11. Protected integration branches accept changes through a temporary branch, pull request, checks and merge — never direct push.
12. Stop only for real ambiguity involving data loss/corruption, identity/persistence, required architecture reopening, irreducible native crash, unjustified major dependency/change, Guide content, or unavailable admin authority.

The known Guide blockers `GUIDE_PREREQUISITE_DATA` and `GUIDE_FINAL_COVERAGE` remain blocking. Known does not mean allowed.
