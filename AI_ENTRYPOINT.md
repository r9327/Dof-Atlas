# Dofus Atlas — AI entrypoint

Every coding agent starts here. Atlas Doctor is the repository control plane;
it plans evidence and validation, while the agent remains responsible for code.

## Required loop

```powershell
py -3.13 -X utf8 -m tools.atlas_doctor agent plan <paths> --base-ref HEAD --json
# implement only the planned change
py -3.13 -X utf8 -m tools.atlas_doctor agent check <paths> --base-ref HEAD --run-tests --json
py -3.13 -X utf8 -m tools.atlas_doctor agent validate <paths> --base-ref HEAD --json
```

Use `--structural` for moves, deletion, dependency, cycle or architecture work.
That route requires exact-SHA Graphify evidence. Use `agent explain` when a
route is unclear; do not guess around `REVIEW` or `BLOCKED`.

## Required PR review

For every PR, apply the commit-by-commit logic audit defined in `AGENTS.md`
before its global final review. Give a precise judgment for each commit,
including concrete missing changes or tests when justified; a commit can be a
valid intermediate step without being independently shippable. Then audit the
**entire integrated PR** for cross-commit consistency, risks, regressions and
validation gaps. Report one final verdict: `VALIDATED`,
`IMPROVEMENTS RECOMMENDED` or `BLOCKED`, with demonstrated issues separated
from hypothetical risks. Do not request cosmetic refactors or infer FULL
certification from a review or partial/skip test results.

## Machine contract

- Protocol: `atlas-doctor-agent/v1`.
- Exit `0`: `READY` or `PASS`.
- Exit `1`: `REVIEW`; evidence is incomplete or judgment is required.
- Exit `2`: `BLOCKED` or `FAIL`; do not continue automatically.
- `edit_contract` limits the initial paths and identifies protected areas.
- `selected_checks` is the minimum validation, not permission to skip failures.
- `guardians` selects the relevant UI, quest/guide, network, persistence,
  performance, release, security and simplicity review lenses. Their tests are
  deduplicated into the existing execution batch; they are not parallel gates.
- `certification.full_certified` remains false until the independent exact-SHA
  Phase Certification workflow proves FULL.

Read the rule files returned by Doctor. `AGENTS.md`,
`DEVELOPMENT_GUARDRAILS.md`, `ZERO_TRUST_RULES.md` and
`PHASE_CERTIFICATION.md` remain authoritative.
