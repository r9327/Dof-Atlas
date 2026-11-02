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

Use `--structural` for moves, deletion, dependency, cycle or architecture work.
That route requires exact-SHA Graphify evidence. Use `agent explain` when a
route is unclear; do not guess around `REVIEW` or `BLOCKED`.

## Machine-readable tool execution contract

Every non-trivial coding agent **must consume** `ai_tool_workflow` in
`tools.atlas_doctor agent plan/check/validate --json`, not merely skim the
project documentation. This object names the required phases, relevant
native owners, approved OSS scanner executions and explicit gaps.

- **Before editing:** run `agent plan <paths> --json` and inspect
  `status`, `edit_contract`, `selected_checks`, `ai_tool_workflow` and
  `oss_selection`. If status is REVIEW/BLOCKED, resolve the reason.
  Use exact-SHA Graphify before structural edits.
- **After editing:** run `agent check <paths> --run-tests --json`. Read
  `execution` and `ai_tool_workflow.approved_oss_execution.tools`.
  `CLEAN` and `FINDINGS` are actual scanner responses; `NOT_RUN`,
  `NOT_AVAILABLE`, `TIMEOUT`, `ERROR` are not PASS.
- **Before proposing fusion:** run `agent validate`, then audit each
  commit and the integrated PR. Only the existing exact-SHA Phase
  Certification provides phase certification.
- **Specialist routes:** `ai_tool_workflow.native_routes` describes
  existing owners to consult; `native_routes_executed_by_selection=false`
  means their **recommendation is never an execution witness**.
- **Windows scanner qualification:** `tools/setup_doctor_oss.ps1` checks
  local Ruff/zizmor without installation by default. `-Install` is a
  separate, explicit developer-only step. Neither command is a runtime
  dependency. `docs/doctor-oss-routing.md` has the full procedure.

34 catalogued third-party candidates do **not** mean 34 installed tools.
Only approved adapters may run automatically. Keep open #313 for selective
tool integrations and #346 for the user's real-PC Windows evidence.

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
