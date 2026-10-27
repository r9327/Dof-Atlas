# Atlas CI Bounded Repair — GitHub-only manual V1

A bounded, **human-triggered** recovery workflow; not a general code-writing
agent, new router, merge approval, or Phase certification. It uses the existing
trusted tools.ai_context index renderer.

## Run it from GitHub

After this workflow has been reviewed, certified and merged into the default
branch, open **Actions → Atlas CI Bounded Repair (manual) → Run workflow**.
Select the default branch. Fill in:

- PR number (open PR from **this** repository; forks are refused).
- Failed **pull_request** Actions run ID.
- Leave propose_fix false for read-only analysis. Toggle true only if you
  approve a new Draft fix proposal for a proven stale context index.

Job diagnose uses read-only permissions and produces an exact-SHA, bounded
JSON report plus GitHub Step Summary. It requires the GitHub-hosted run to
have failed, with AI Context / Targeted Validation and its
Verify committed context index step failed, and log evidence
AI context index: STALE/MISSING. It also requires the run's candidate SHA
to equal the **current** head SHA of the referenced same-repository PR,
and the run must independently reference that exact PR/SHA. An incomplete
GitHub job inventory is refused, including when a paginated result is omitted.

Other errors, missing evidence, stale SHA, forks, cancelled/skipped jobs and
closed PRs return REVIEW_REQUIRED without edits. Treat this as diagnostic
feedback, not a declaration that other jobs succeeded.

If explicitly opted in and eligible, the separately permissioned propose
job checks out the default-branch *trusted* Python implementation and the
exact failing PR SHA as **data** without persistent credentials. It never
imports or executes a Python module from the candidate, or a shell command
from GitHub logs. The GitHub token is sent on the initial API request only,
never to a redirected job-log download URL. It calls
`tools.ai_context.sync_index` on that candidate
checkout, then enforces that exactly .ai/context_index.json changed and
its bytes match the existing trusted index renderer.

The job re-fetches host evidence immediately before writing, creates a
**new uniquely named repair branch based on the failing PR's head**, writes
only the context index and opens a **Draft PR targeting the original PR's
branch**, not main. It never force-pushes or modifies the source PR branch.
A repeated dispatch of the same incident cannot silently overwrite the
existing fix branch; a moved source PR SHA invalidates the attempt.
Review/merge that Draft into the original branch separately, then allow all
usual GitHub checks to rerun on the new SHA.

## Guarantees and limitations

- There is **one** supported automatic repair. No generic LLM prompt,
  arbitrary command execution, test weakening, hidden lint suppression,
  workflow/ruleset edits or automatic merge.
- The workflow is dispatch-only on the trusted default branch and is not
  invoked by PR code, issue comments, or workflow_run from untrusted forks.
- The write token is present only in the gated propose job. An eligible
  diagnosis and an explicit boolean opt-in are both needed to reach it.
- An index repair is not proof of a passing AI Context job after the new
  commit, other tests, Qt/Windows behavior, FULL or Phase certification.
- The index repair is intentionally refused if the candidate checkout is
  dirty, the path escapes the checkout via a symlink, the index is already
  current, GitHub metadata conflicts, or the generated patch touches other
  files. A report of REVIEW_REQUIRED is a safe non-repair outcome.
- GitHub Actions permissions/settings may block branch creation or PR creation.
  An API failure never counts as successful repair.

## Validation

Before merging, run the stdlib unittest discovery for
tests/test_ci_failure_autofix.py (also part of Draft stdlib feedback) and the
repository's existing exact-SHA merge certification.

The scenario tests include mocked hosted run/job/step/PR evidence,
stale SHA, forks, skipped steps, spoofed/nonmatching errors, dirty worktrees,
symlink paths, canonical index regeneration and replay refusal.

Next possible extension: additional *individually reviewed* deterministic
fix recipes with distinct tests and SHA-preserving GitHub host evidence.
An autonomous general code-writing agent should remain a separate, evaluated
project with explicit authorizations and no self-certification.
