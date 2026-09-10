# Security Policy

Dof'Atlas is a work-in-progress desktop application. Security reports are welcome and should be handled privately whenever they could expose users, credentials, local files, GitHub Actions, or the update/install path.

## Supported version

Only the current `main` branch is supported for security fixes. Older snapshots and abandoned branches are not maintained as security-supported releases.

## Reporting a vulnerability

Use GitHub's private **Report a vulnerability** / Security Advisory flow when it is available for this repository.

Do **not** publish exploit details, credentials, tokens, personal paths, private data, or weaponized proof-of-concept code in a public issue or pull request. If private vulnerability reporting is not available, open only a minimal public issue saying that a private security contact is required; do not include sensitive technical details there.

A useful private report includes the affected commit/version, attack preconditions, impact, a minimal non-destructive reproduction, and any proposed mitigation.

## Security response rules

Security fixes must preserve the repository's Zero-Trust guardrails. A red security check must not be skipped, swallowed, downgraded, or converted to informational merely to merge a change. Changes to workflows, dependency locks, installers, identity/persistence boundaries, WebView policy, or security guardrails require the same protected-PR path as other sensitive changes.
