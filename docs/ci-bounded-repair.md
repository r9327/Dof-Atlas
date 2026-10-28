# Atlas CI Bounded Repair — read-only workflow and optional local publication

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
  request a **read-only artifact** for a proven stale context index.
  Neither option creates a branch or PR.

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

If explicitly opted in and eligible, the separately permissioned **read-only**
propose job checks out the default-branch trusted implementation and the
exact failing PR SHA as **data**. It re-fetches GitHub host evidence and
regenerates the canonical `.ai/context_index.json` without importing or
executing Python or shell from the candidate. Tokens authenticate only
initial GitHub API requests and never accompany redirected log downloads.
It uploads exactly the generated index as an Actions artifact for review.
**No workflow job modifies GitHub, creates branches or opens Draft PRs.**

After inspecting this proposal, a human operator can explicitly approve
publication and run the separate `publish` CLI outside GitHub Actions with
independently managed credentials and an exact-SHA candidate checkout.
That path re-verifies GitHub evidence, creates a fresh single-purpose branch
based on the original PR HEAD and opens a stacked **Draft PR** targeting the
original branch, not `main`. It never force-pushes or modifies the source PR
branch. The Draft still needs ordinary review and fresh CI evidence.

## Guarantees and limitations

- There is **one** supported automatic repair. No generic LLM prompt,
  arbitrary command execution, test weakening, hidden lint suppression,
  workflow/ruleset edits or automatic merge.
- The workflow is dispatch-only on the trusted default branch and is not
  invoked by PR code, issue comments, or workflow_run from untrusted forks.
- All workflow jobs are read-only. An eligible diagnosis and explicit opt-in
  are necessary even to generate the proposal artifact. Publication uses
  separate, explicitly authorized local credentials only.
- An index repair is not proof of a passing AI Context job after the new
  commit, other tests, Qt/Windows behavior, FULL or Phase certification.
- The index repair is intentionally refused if the candidate checkout is
  dirty, the path escapes the checkout via a symlink, the index is already
  current, GitHub metadata conflicts, or the generated patch touches other
  files. A report of REVIEW_REQUIRED is a safe non-repair outcome.
- Optional human-initiated publication may be blocked by GitHub branch/PR
  permissions or stale evidence. An API failure never counts as repair.

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
