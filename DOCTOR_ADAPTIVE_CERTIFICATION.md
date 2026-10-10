# Doctor Atlas — Adaptive Certification Architecture

## Goal

Make Doctor the **single planning interface** for test selection and impact
analysis; make the Atlas Integrity + phase policy the **independent authority**
for mandatory certification. Reuse canonical selectors, Source Impact,
Graphify, existing contracts, and historical cost evidence. Do not create a
second independent risk classifier that can waive established FULL gates.

The new workflow is a functional, **advisory** implementation: it executes
directly proven scoped tests when safe and reports \`FULL_REQUIRED\` otherwise.
It does **not** override the current \`PHASE_CERTIFICATION.md\` contract.

## Current implementation (v1)

- \`python -m tools.atlas_doctor certify --base-ref origin/main --json\`
  builds an exact-SHA plan without running tests.
- \`python -m tools.atlas_doctor certify --base-ref origin/main --run-tests --json\`
  executes eligible scoped modules with the canonical scope runner and reports
  the actual process exit code. Same standalone workflow through
  \`python -m tools.doctor_certification --base-ref <SHA> --expected-sha <SHA> --run
  --output artifacts/doctor_certification/report.json\`.
- Doctor combines the canonical CI scope decision, a separate root-of-trust
  escalation, source-confirmed reverse imports (at most two hops), documented
  boundary tests, and domain labels.
- A missing base, invalid SHA, broad/unknown/critical diff, deleted/renamed
  file, missing direct test, missing boundary contract, stale/truncated import
  evidence, unresolved dynamic consumer, or unmapped impacted source forces
  \`FULL_REQUIRED\`.
- \`FAST\` and \`SMART\` are scoped validation profiles, *not* certification
  levels equivalent to the FULL. Qt/data/performance changes can require
  SMART, but only with evidence and fully mapped coverage.
- Local evidence is bound to base/head SHA, plan fingerprint, exact modules,
  exit code and completed flag. Different SHA/environment is never reusable
  in v1. JSON digests are identifiers, **not signatures/attestations**.
- \`.github/workflows/doctor-certification.yml\` validates the planner
  contracts on Windows/Python 3.13 and runs eligible scoped checks on PRs,
  emitting the diagnostic report even when the plan requires FULL.

## Architecture boundaries and trust rules

1. **Doctor / Graphify:** describes impact. A static graph edge is not runtime
   evidence; graph stale, budget overrun, reflective Qt or dynamic unknowns
   require widened coverage.
2. **CI scope router:** maps changed paths to directly coupled tests and
   refuses undocumented coverage. The planner may **add** boundary contracts
   but may never remove an obligated test or downgrade a FULL.
3. **Atlas Integrity / phase policy:** controls official certification. Its
   FULL_SUITE and DATA_INTEGRITY gates remain unchanged in this PR.
4. **GitHub Actions:** executes actual commands, records their exit statuses.
   Running the planner is not a PASS for tests it did not execute.
5. **Evidence store:** v1 exact-SHA replay helper is conservative. No
   cross-SHA equivalence claim until complete dependency closure, pinned
   environment and trusted provenance are formally verified.

If the planner itself, its workflow or a certification root-of-trust file
changes, the independent requirement remains FULL. A green Doctor advisory
check **cannot** unlock a merge blocked by another check.

## Matrix

| Change | Doctor outcome | Remaining obligation |
|---|---|---|
| Known, directly tested tooling | FAST candidate, scoped tests | Existing required checks |
| Widget provider/export change with mapped contracts | SMART candidate, Qt boundary tests | Existing phase policy; performance when required |
| Guide builder, manifest, changed CI policy | FULL_REQUIRED | Atlas Integrity FULL + phase decision |
| Unmapped application consumer, unknown dynamic import | FULL_REQUIRED | Add tests or FULL |
| Unrelated test code with exact module | FAST candidate | Existing required checks |
| Release or final phase | FULL_REQUIRED regardless of advisory PASS | Exact-SHA FULL as defined in phase contract |

## Integration & acceptance plan (do not bypass gates prematurely)

**Stage 1 — implemented in this PR.** Doctor CLI + deterministic risk and
impact planner; Windows advisory workflow; failure-safe contracts and
exact-SHA evidence with transparent profile and reasons. Scope engine remains
authoritative, duplicate Guide rebuilds remain owned by #131. NO heavy RAM,
preload or FULL runs while developing this PR.

**Stage 2 — required before any policy switch.** Add a signed/trusted
cross-workflow evidence registry with dependency closure (imports + Qt
signals + callbacks + dynamic traces), fixture/data hashes, environment
versions and tool-policy digests. Prove revocation on any changed dependency,
runner/policy version, unknown edge or mixed diff. Audit against past
certification runs and adversarial mutations.

**Stage 3 — phase policy migration, separate dedicated PR.** Introduce an
independently reviewed Policy Engine defining which end-to-end scenario
families and benchmarks are required for each change, with a reproducible
risk report. Run shadow decisions alongside mandatory FULL for a sample of
representative historical and new phase candidates. A smaller certificate
must receive its own explicit status, never \`FULL_SUITE PASS\`.

**Stage 4 — optimize unavoidable FULL.** Profile highest-cost Guide builders
and repeated data initializations, build independent Windows shards, isolate
Qt/WebEngine/shared mutation tests, and prove no test is lost or skipped.
Use critical dependency/contract tests first for fast failure and schedule
reliable independent work in parallel. Validate memory/preload on their
original budgets. Optimize based on measured end-to-end time, not estimates.

## Non-negotiable invariants

- Every record identifies an immutable candidate SHA and comparison base.
- No FULL result can be synthesized from scoped results.
- No test may be silently removed, skipped or masked as passed.
- Phase closure must continue to satisfy the original phase contract.
- No stale Graphify graph can justify reduced test coverage.
- Path deletions, renamed modules and unknown dynamic Qt callbacks escalate.
- A failed test never passes by rerun or flaky heuristic.
- The planner's own source changes force enhanced independent validation.
- A missing proof is a blocked certificate, not a default PASS.
- PR #127, #131, #134, #136 and their code remain untouched.

## Initial efficiency targets (not measured promises)

- Routine FAST: 1–3 min, SMART: 3–10 min, DEEP: 10–20 min,
  unavoidable FULL: reduce toward 15–30 min through safe sharding and fixing
  expensive fixture generation.
- Measure actual Windows CI wall-clock including dependency installation.
- For each adaptive run record the modules actually tested, uncovered impact,
  time and explicit reason when a FULL remains mandatory.

## Review and rollout checklist

- [x] Runtime-independent read-only planner and exact-SHA command.
- [x] Safety: canonical scope fail-closed, source impact and boundary mapping.
- [x] Windows PR pipeline and isolated unit contract suite.
- [x] Explicit separate SCOPED/PASS, FULL_REQUIRED and BLOCKED vocabulary.
- [x] Documentation of the unmodified FULL certification contract.
- [ ] Windows checks for the final exact SHA **PASS**.
- [ ] Cross-SHA evidence registry with trusted provenance and policy coverage.
- [ ] Shadow comparison against exhaustive FULL on representative risks.
- [ ] Independently reviewed policy migration allowing alternative phase
      certificates, with no silent waiver.
- [ ] Verified measured reduction for FULL and scoped CI, including Guide cases.

Do **not** merge this PR before its focused checks and the repo's current
required checks pass. The stage 2–4 items are explicit future gates, not
features silently claimed complete by v1.


## Stage 1B — implemented additive policy, passports and offline shadow reviews

Doctor now also has the following concrete components (all scoped to the
existing feature branch and existing FULL requirements):

- \`tools/atlas_doctor_lib/certification_policy.py\`: **independent**
  additional contracts for Encyclopedia navigation, Guide progression,
  startup resources, Qt lifecycle, memory/preload and data integrity.
  Each points to existing test modules, affected integrity groups and
  benchmark dimensions; the policy enforcer rejects missing scenario tests.
- \`tools/atlas_doctor_lib/certification_passport.py\`: per-SHA passport
  describing actual tests, outstanding metrics, environment versions,
  selection explanations and unresolved reasons. Local hash mismatch or
  incorrect candidate SHA blocks artifact consumption; hashes alone do
  **not** attest GitHub provenance, and automatic cross-SHA reuse remains
  disabled.
- \`tools/atlas_doctor_lib/certification_shadow.py\`: compares a candidate
  plan with a **previously completed** FULL Integrity JSON from the same
  candidate SHA and explicitly flags potentially missed regressions.
  It does not start a FULL and never waives phase obligations.
- Command usage:
  \`python -m tools.doctor_certification --base-ref origin/main --expected-sha <HEAD> --run --output artifacts/doctor_certification/report.json --passport-output artifacts/doctor_certification/passport.json\`
- Optional exact-SHA shadow comparison:
  \`python -m tools.atlas_doctor certify --base-ref origin/main --shadow-full-report artifacts/completed-full.json --json\`.
  Malformed or mismatched FULL evidence is blocked, never interpreted as PASS.
- Tests: \`tests.test_doctor_certification\`,
  \`tests.test_doctor_certification_policy\`, and
  \`tests.test_doctor_certification_shadow\` are CI-targeted.

The passport always reports required but **unexecuted** performance metrics.
It is an advisory result, not a new authorized release certificate.
The remaining Stage 2–4 work above (trusted attestation, replay of real
end-to-end scenarios, shadow campaigns, validated shards, independent
policy migration) remains explicitly **NOT IMPLEMENTED** in this PR.


## Immediate CI time saving — Phase draft gate

Phase Certification no longer auto-runs FULL on each update to a **draft**
Phase PR. It continues to run when that PR becomes ready for review, on
subsequent ready Phase PR commits, when explicitly dispatched, and after
pushes to main. This changes *when* the exhaustive phase suite runs, not its
required tests or verdict. Draft PRs still run Doctor Adaptive/Doctor FAST/
scoped feedback, and cannot declare their phase certified. See
\`PHASE_CERTIFICATION.md\` and the specific draft/ready guardrail test.


## Stage 1C — cheap plan before optional Windows tests

The Doctor workflow now separates two cost profiles:

- **Plan:** Ubuntu/Python 3.13 with only stdlib imports. Checks contracts,
  Git diff, independent policy, Source Impact, exact SHA and emits
  \`plan.json\`/\`plan_passport.json\`. **No pip/Qt install.**
- **Scoped:** Windows/PySide6 **only** when the plan is
  \`READY_TO_RUN_SCOPED\`. Rechecks exact SHA, repeats fail-closed selection,
  executes the actual canonical test modules and emits a final passport.
- **FULL_REQUIRED** deliberately does *not* start a Windows scoped job. It is
  not a waiver of the separately required Phase/Release FULL.
- The planning report contains real group/test selection justifications;
  all outstanding metrics and the FULL certification status remain explicit.

This optimizes the **Doctor adaptive workflow** immediately. Existing
Public PR and other independent Windows validation jobs still have their
own scheduling and may require separate optimization. Do not claim their
time was reduced without a comparable measured run.


Planner test collection uses \`unittest discover -s tests -p
'test_doctor_certification*.py'\` to bypass the app-wide
\`tests/__init__.py\` Qt harness during the fast standard-library-only job.
Actual application test execution on Windows keeps its original canonical
imports and PySide6 requirements. This is an isolation of the **planning
contract tests**, not a shortcut for Qt functional validation.
