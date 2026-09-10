# GitHub protection for Dof'Atlas `main`

Repository: `r9327/Dof-Atlas` (public).

## Verified live protection

The live repository ruleset currently protects the default branch with:

- active enforcement on `main`;
- branch deletion blocked;
- non-fast-forward / force-push blocked;
- pull request required;
- stale approvals dismissed after new pushes;
- CODEOWNERS review required;
- review conversations must be resolved;
- `Public PR / Safe Validation` required and strict/up-to-date.

The current live ruleset still contains one owner bypass (`r9327`, mode `always`). That is convenient for a solo maintainer but is not maximum-security configuration: a compromised owner session can use that bypass.

## Maximum-security target

`.github/rulesets/max-security.json` is the reviewed target policy. It adds:

- zero bypass actors;
- signed commits required on the protected branch;
- linear history required;
- squash-only merges;
- one approving CODEOWNER review;
- approval from someone other than the last pusher;
- the same strict blocking public PR check.

Applying that target requires a second trusted reviewer. With a single repository owner, one required independent approval plus zero bypass actors intentionally prevents the owner from merging their own PR.

## Dependency security prerequisite

The public PR workflow runs GitHub Dependency Review and fails closed for any known vulnerability at severity `low` or above. GitHub requires the repository **Dependency Graph** to be enabled for that action.

Admin action: **Settings -> Security / Code security -> Dependency graph -> Enable**.

Until Dependency Graph is enabled, `Public PR / Safe Validation` is expected to stay red at the dependency-review verdict rather than silently skip the security check.

## Supply-chain and runner policy

- Every external GitHub Action is pinned to an immutable 40-character commit SHA.
- Checkout credentials are never persisted after checkout.
- Automatic public CI runs only on GitHub-hosted runners.
- Self-hosted workflows are manual-only and additionally require the repository owner dispatching trusted `main` code.
- Workflow `GITHUB_TOKEN` permissions are read-only.
- Python runtime dependencies and transitives are pinned and authenticated with SHA-256 hashes.
- Dependabot covers GitHub Actions and Python dependencies.

## Permanent contribution flow

Create a temporary branch -> open a pull request -> wait for `Public PR / Safe Validation` -> review -> squash merge. Do not weaken, skip, swallow, or bypass a failed security check just to obtain green.
