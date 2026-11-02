---
name: evidence-driven-validation
description: Choose targeted tests and Doctor risk gates, and report verified versus unverified outcomes for Dofus Atlas changes.
---

# evidence driven validation

Use before finishing non-trivial edits, when tests fail and when preparing a PR or phase review.

1. Read `AI_ENTRYPOINT.md`, `ZERO_TRUST_RULES.md` and `PHASE_CERTIFICATION.md`.
2. Classify diff risk LOW, MEDIUM, HIGH or CRITICAL; run `py -3.13 -X utf8 -m tools.atlas_doctor agent plan <paths> --base-ref HEAD --json` for non-trivial work.
3. Follow the selected edit contract and focused tests, then run Doctor `agent check <paths> --base-ref HEAD --run-tests --json` and `agent validate <paths> --base-ref HEAD --json`. Inspect `oss_advisory.execution_summary.gaps`: selected, available, executed and certified are different states. Respect the existing Integrity policy for FAST/CRITICAL/FULL/DEEP.
4. Check exact SHA, test results, relevant regressions, final diff and `git diff --check`; do not weaken a gate to pass.
5. Keep PRs Draft until all scoped implementation and self-review is complete; existing exact-SHA Phase Certification, not a green PR, is the only FULL certification evidence.
6. State the difference between executed tests, static checks, UI/runtime observations and remaining uncertainty.

Skipped, blocked, stale or unavailable validation is never PASS.
