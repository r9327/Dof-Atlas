# GitHub protection for the integration branch

Observed on 2026-09-09: the repository is reachable through the configured Git remote, but GitHub CLI is not installed and unauthenticated REST access cannot inspect this private repository (`401` for branch protection, `404` for repository/rulesets). Protection, bypass and deletion settings are therefore **NOT VERIFIED / ADMIN ACTION REQUIRED**.

The reviewed API payload is tracked at `.github/rulesets/integration-branch.json`; GitHub does not apply that file automatically.

## Admin action

In **Settings -> Rules -> Rulesets**, create a branch ruleset from that payload or reproduce it exactly:

- target `feature/guide-ultime-v5-ui`;
- active enforcement, no bypass actors;
- require a pull request, resolve conversations, zero approvals for the current solo workflow;
- require the branch to be up to date before merge;
- block deletion and non-fast-forward/force pushes;
- require these real job names: `Integrity Policy / Fast Code Validation`, `Architecture`, `Identity / Persistence`, `Startup / Lazy`, `Qt Lifecycle / Async`, `Resource Budgets`, `Golden Flows`, `Monolithic Lifecycle`, `Full Application Suite`.

Do **not** require `Guide / Quests / Success / Data Integrity` yet: it is intentionally red while `GUIDE_PREREQUISITE_DATA` and `GUIDE_FINAL_COVERAGE` remain blocking. Add it as a required check only after the Guide content project fixes both failures without weakening the audits.

CODEOWNERS marks sensitive files but does not block changes alone. Required code-owner approval is intentionally disabled in the solo payload because an author cannot approve their own pull request. Enable it only when another trusted reviewer is available.

## Permanent contribution flow

Create `ai/*`, `codex/*`, `work/*` or `fix/*` branch -> push that branch -> open a pull request -> wait for required checks -> merge through GitHub. Never push directly to the protected integration branch.
