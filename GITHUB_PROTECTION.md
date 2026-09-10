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

The current live ruleset still contains one owner bypass (`r9327`, mode `always`). That is the main remaining protection gap: a compromised owner session can bypass the normal PR/check path.

## Hardened solo target

`.github/rulesets/integration-branch.json` is the hardened policy intended for a repository with one trusted maintainer:

- zero bypass actors;
- deletion and force-push blocked;
- linear history required;
- every change goes through a pull request;
- `Public PR / Safe Validation` is strict and blocking;
- unresolved review conversations block merge;
- squash is the only allowed merge method;
- no mandatory approval is required, because a solo author cannot provide an independent approval to their own PR.

This is stronger than keeping an owner bypass: the owner can still merge their own checked PR, but cannot skip the protected PR/check path.

## Maximum-security target

`.github/rulesets/max-security.json` is the maximum-security policy for the day a second trusted reviewer is available. It additionally requires:

- signed commits on the protected branch;
- one approving CODEOWNER review;
- approval from someone other than the last pusher;
- zero bypass actors;
- linear history and squash-only merges;
- the same strict blocking public PR check.

With a single repository owner, applying this maximum policy intentionally prevents the owner from merging their own PR. Use the hardened solo target until a second trusted reviewer exists.

## Dependency security prerequisite

The public PR workflow runs GitHub Dependency Review and fails closed for any known vulnerability at severity `low` or above. GitHub requires the repository **Dependency Graph** to be enabled for that action.

Admin action: **Settings -> Security / Code security -> Dependency graph -> Enable**.

Until Dependency Graph is enabled, `Public PR / Safe Validation` is expected to stay red at the dependency-review verdict rather than silently skip the security check.

## Native GitHub settings to harden

After merging the hardening PR, align the live GitHub settings with the tracked policy:

- remove the current `r9327` `always` bypass from the `main` ruleset;
- reproduce `.github/rulesets/integration-branch.json` in the live ruleset;
- enable Dependency Graph;
- enable private vulnerability reporting / **Report a vulnerability** when available;
- keep squash merge enabled and avoid merge/rebase methods for protected `main`;
- enable automatic deletion of merged temporary branches if desired.

These repository-admin settings are not applied merely because the JSON/policy files exist in Git.

## Supply-chain and runner policy

- Every external GitHub Action is pinned to an immutable 40-character commit SHA.
- Checkout credentials are never persisted after checkout.
- Automatic public CI runs only on GitHub-hosted runners.
- Self-hosted workflows are manual-only and additionally require the repository owner dispatching trusted `main` code.
- Workflow `GITHUB_TOKEN` permissions are read-only.
- Python runtime dependencies and transitives are pinned and authenticated with SHA-256 hashes.
- Dependabot covers GitHub Actions and Python dependencies.
- The application runtime does not disable the QtWebEngine sandbox.
- The embedded Equipment WebView blocks local/custom top-level navigation and secondary popup windows.
- Probable secret patterns are rejected before merge.

## Permanent contribution flow

Create a temporary branch -> open a pull request -> wait for `Public PR / Safe Validation` -> inspect the diff -> squash merge. Do not weaken, skip, swallow, downgrade, or bypass a failed security check merely to obtain green.
