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

Doctor's check is the canonical opt-in execution stage: `--run-tests` now
also runs approved **local, scoped, read-only** OSS analyzers automatically
when present (Ruff for Python; zizmor offline for workflows). Absent tools
are explicitly reported, not installed and not counted as PASS.
`--run-oss` remains the explicit OSS-only option; `--no-oss` skips
third-party diagnostics without skipping required Doctor tests. The
`oss_selection` field in every Agent action describes suggestions but does
not authorize any other external executable. See `docs/doctor-oss-routing.md`.

## Specialist tools and truthful evidence

Before choosing an auxiliary executable, consult the repository-local
`tools/skills/dofus-atlas-tools/SKILL.md` and the **derived**
`py -3.13 -m tools.tool_catalog --preferred-only --safe-only --ready-only --json`
view. Never create a second tool list, invoke an unreviewed binary or
auto-install candidates from the 29 + 5 OSS study.

Doctor's `oss_selection` is a recommendation, **not** an execution log.
`agent check --run-tests` invokes only the two approved, locally available
and in-scope scanners (Ruff for Python, zizmor offline for GitHub workflows).
Read `oss_advisory.execution_summary` for `expected_tools`,
`confirmed_executions`, and `gaps`. Missing/timeout/error results and
truncated file coverage must remain visible; no partial advisory makes the
canonical Doctor result PASS.

Actual native qualification of both scanners is an **explicit** separate
command: `doctor oss <python.py> <.github/workflows/file.yml> --verify-live --json`.
`LIVE_PASS` on a runner does not attest the user's Windows machine;
see `docs/doctor-oss-routing.md` and issue #346. All other OSS projects
remain adoption candidates, not automatically executable adapters.

Use `--structural` for moves, deletion, dependency, cycle or architecture work.
That route requires exact-SHA Graphify evidence. Use `agent explain` when a
route is unclear; do not guess around `REVIEW` or `BLOCKED`.

## Required PR review

For every PR, apply the commit-by-commit logic audit defined in `AGENTS.md`
before its global final review. Give a precise judgment for each commit,
including concrete missing changes or tests when justified; a commit can be a
valid intermediate step without being independently shippable. Then audit the
**entire integrated PR** for cross-commit consistency, risks, regressions and
validation gaps. Report one final **logic-review** verdict: `REVIEW OK`,
`IMPROVEMENTS ADVISED` or `CHANGES REQUIRED`, with demonstrated issues
separated from hypothetical risks. These are not CI/Doctor `VALIDATED` or
`CERTIFIED` states. Do not request cosmetic refactors or infer FULL
certification from a review or partial/skip test results.

## Agent and AI rule changes

When a PR adds, edits or removes agent instructions, skills, policy rules,
CI requirements or provider entrypoints, also run the **bounded rule audit**
in `AGENTS.md`. Verify scope, authority, conflicts/duplication,
paths/commands, real CI triggers and safety before and after the change.
Keep canonical contracts in their owning files and link to them rather
than copying whole policies into each agent entrypoint. Document confirmed
findings and required corrections; do not invent an extra certification gate.

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
