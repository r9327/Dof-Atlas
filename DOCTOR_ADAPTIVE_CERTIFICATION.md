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


## Stage 1D — cumulative risk and strict historical FULL evidence

- Optional \`--cumulative-base-ref <SHA/ref>\` for
  \`python -m tools.atlas_doctor certify\` or
  \`python -m tools.doctor_certification\` widens the risk horizon
  beyond just the PR diff. Git ancestry and HEAD are verified; dangerous
  accumulated changes, deletions, large diffs or mixed runtime/data domains
  trigger \`FULL_REQUIRED\`. Invalid ancestry is BLOCKED. This feature may
  **escalate**, never reduce obligations.
- The cumulative reference is a Git comparison ref, **not** evidence that
  this ref had a successful FULL. \`base_full_proven\` and
  \`authorizes_skipping_tests\` remain false.
- Shadow comparison now requires an actual \`schema_version=1\`,
  \`mode=FULL\` Atlas Integrity report, the exact candidate SHA, all
  currently mandatory groups from \`tools/atlas_integrity_policy.json\`,
  coherent group statuses and test execution records for \`FULL_SUITE\`.
  FAST/CRITICAL/DEEP reports, sparse JSONs claiming PASS, and missing
  execution records become \`INVALID_EVIDENCE\`.
- Even a correctly shaped local JSON cannot authenticate GitHub workflow
  provenance; an authenticated evidence store still belongs to Stage 2.

Examples (advisory planning, no tests executed):

\`\`\`bash
python -m tools.atlas_doctor certify --base-ref origin/main --cumulative-base-ref <older_ancestor_sha> --json
python -m tools.atlas_doctor certify --base-ref origin/main --shadow-full-report artifacts/existing_exact_sha_full.json --json
\`\`\`

The new \`tests.test_doctor_certification_cumulative\` cases run using a
minimal isolated Git fixture, not the real application or a FULL.


## Stage 1E — avoid duplicate Windows installation for canonical PR scoped feedback

\`.github/workflows/scoped-pr-ci.yml\` now keeps the existing
\`PR / Scoped Test Feedback\` required check name, but separates execution:

1. **Stdlib Ubuntu planning** runs the existing \`test_ci_scope_gate.py\`
   and \`test_ci_dev_tests.py\` contracts as isolated test files, and invokes
   the **unchanged canonical scope selector** without \`--run\`.
2. **Windows tests** only when the canonical selector returns \`TARGETED\`.
   The exact candidate SHA and scope are rechecked, then Python dependencies
   are installed and the same canonical selector runs required modules.
3. **Final verdict** runs after both jobs. If the planner failed, or Windows
   was required but failed/skipped, the original \`PR / Scoped Test Feedback\`
   check fails. A \`FULL_REQUIRED\` classification explicitly skips the
   Windows scoped job and does **not** claim FULL PASS.

The independent \`Public PR / Safe Validation\` Doctor FAST gate stays
mandatory and is not reduced by this scheduling optimization. The canonical
\`tests/test_ci_scope_gate.py\` workflow contract has been deliberately
updated to ensure the new dependent verdict cannot mask failed tests.
This is a scheduling optimization only, not a coverage relaxation.


## Stage 2A — runtime trace binding and conservative evidence review

These are implemented **advisory features** rather than simulated PASS gates:

- \`--trace .ai/runtime/...json\` (repeatable, maximum 12) binds the
  existing Doctor scenario-coverage analyzer to the candidate SHA. The
  trace must be non-stale, untruncated, inside the runtime boundary and
  must show actual execution of all changed/impacted application Python
  files. Otherwise \`FULL_REQUIRED\` is recorded; a runtime observation
  is **not** a completed functional assertion, Qt teardown certification,
  or memory/preload benchmark.
- \`--prior-passport artifacts/previous/passport.json\` performs a safe
  *cross-SHA eligibility review*. It validates internal passport checksum,
  current OS/Python/pinned dependency digest, prior executed test subset,
  exact Git ancestry/HEAD, and requires **every changed Git object**
  between those SHAs to be a \`docs/**/*.md\` documentation file. Any
  code, data, tests, workflow, fixture, or dependency change makes the
  previous evidence ineligible.
- The \`evidence_reuse_review\` reports
  \`CANDIDATE_FOR_INDEPENDENT_PROVENANCE_REVIEW\` versus \`NOT_ELIGIBLE\`.
  **No tests are skipped.** Git SHA plus a self-reported JSON digest
  cannot prove that GitHub Actions produced a successful, unmodified
  certificate. An independently authenticated artifact origin and a
  separately reviewed policy are still required before any execution
  waiver can be implemented.

## Stage 2B — actual historical FULL ingestion and offline shadow cohorts

The tool \`python -m tools.doctor_shadow_campaign\` now accepts **actual**
downloaded Atlas Integrity reports without starting a single new FULL:

\`\`\`bash
python -m tools.doctor_shadow_campaign --inspect-full artifacts/phase_certification/03_atlas_integrity_full.json --output artifacts/doctor/shadow_inspection.json
python -m tools.doctor_shadow_campaign --pair previous_doctor_plan.json matching_exact_sha_full.json --output artifacts/doctor/shadow_campaign.json
\`\`\`

The two modes are deliberately distinct:

- \`--inspect-full\` validates the real report's mode, schema, exact SHA,
  every mandatory policy group, status consistency, and positive
  \`FULL_SUITE\` execution records. It **does not pretend to have run
  Doctor on that historical SHA**.
- \`--pair\` requires an actual plan and a FULL report for the **same
  candidate SHA**, aggregates candidate missed regressions, and exits
  non-zero on invalid evidence or observed false negatives. Up to 12
  report inputs; local JSON provenance remains untrusted until attested.

### Observed real baseline (not synthetic; not a shadow pair)

GitHub Actions run
\`38034553541\`, PR #127, HEAD
\`a63aa598b321a5cb48a4724309e83c3816e73ef7\`
contains artifact
\`phase-certification-38034553541-1\`, and its
\`phase_certification/03_atlas_integrity_full.json\` reports:

- \`mode=FULL\`, \`verdict=PASS\`, all 16 required groups PASS.
- \`FULL_SUITE\`: **2267 tests, 4135.928 seconds**.
- \`DATA_INTEGRITY\`: 415.486 seconds;
  \`GOLDEN_FLOWS\`: 167.709 seconds.
- Entire Atlas Integrity execution: **4864.007 seconds (~81.1 min)**.

This establishes a *real cost baseline* and a real archived FULL record.
It does **not** demonstrate any current PR #137 shadow agreement, nor
validate that historical #127 behavior matches newer code. The separate
Guide-fixture speedup remains owned by PR #131; no duplicate rewrite here.

### Remaining safety work

- Authenticate run identity, attempt, conclusion, artifact digest, GitHub
  workflow SHA and repository origin **outside PR-modifiable code** before
  allowing evidence reuse.
- Collect actual Doctor-vs-FULL **same-SHA** pairs and adversarial
  mutation samples for all scenario families; one successful FULL alone
  cannot certify the selector's false-negative rate.
- Implement trusted policy migration and resource-budget/runnable
  scenario gates in a separately reviewed rollout. Keep the current
  mandatory FULL untouched until proven safe.


## Stage 2C — authenticated GitHub artifact bytes, not policy provenance

\`python -m tools.doctor_github_provenance\` performs an *opt-in*
independent check of a previously downloaded Doctor artifact ZIP.

\`\`\`bash
# Requires a read-only GITHUB_TOKEN for the GitHub REST API.
python -m tools.doctor_github_provenance \
  --repo r9327/Dof-Atlas --run-id <github_run_id> \
  --artifact-id <artifact_id> --expected-sha <40-character_SHA> \
  --archive /path/to/downloaded-doctor-plan.zip \
  --output /path/to/origin-report.json
\`\`\`

The verifier looks up the run and artifact on GitHub's API (never trusting
JSON inside the ZIP as its origin), requires a completed successful run
from the named canonical repository and workflow, matches repository ID,
candidate SHA and run ID, validates the GitHub-reported SHA256 of the
ZIP, parses one bounded Doctor passport, and checks the passport's
digest and mandatory no-FULL/no-merge claims. Failures block.

The result is named \`ARTIFACT_ORIGIN_VERIFIED_NOT_POLICY_TRUSTED\`,
**not** \`CERTIFIED\`. A PR-modifiable workflow could itself publish a
misleading artefact. A separate, default-branch-protected policy and
workflow-code provenance decision is still necessary before automated
cross-SHA reuse.

### Real current-run artifact check (GitHub run metadata + ZIP bytes)

For the PR #137 HEAD \`6c42d202388051bbb25cd570824c15e5ebe403a4\`:

- Doctor Adaptive Certification run \`38129227192\` succeeded.
- GitHub reported artifact \`11698522059\`:
  \`doctor-plan-38129227192-1\`, origin SHA matching the PR HEAD,
  \`digest=sha256:d8a9bf8d5fd66a25a1bced3808b578890bbf679bea56233c66b37de59894893e\`.
- The downloaded ZIP was independently hashed and had **exactly the
  same SHA256**. It contained \`plan.json\` and \`plan_passport.json\`
  both bound to the same candidate HEAD. The passport was
  \`FULL_PENDING\`, not an unwarranted \`FULL PASS\`.

This is a real artifact-origin consistency measurement, not a signed
release attestation. The read-only verifier's full API-driven execution
remains an opt-in command; all its attack cases are tested offline in CI.

### Remaining work for completion

Actual **safe automatic** cross-SHA test reuse is still blocked by an
independently authenticated default-branch policy and complete dynamic
dependency closure; real end-to-end scenario assertions and expensive
FULL sharding/Guide builders must likewise be demonstrated before
official release policy migration. These are *not* marked done here.


## Stage 3 implementation — complete feature coding batch for PR #137

This final development batch builds on existing independent, conservative
selection; it does not silently change Phase/FULL release policy.

### Verified source policy and provenance

- \`tools/doctor_policy_authority.py\` compares the full set of
  certification root-of-trust **Git blobs** on the candidate with immutable
  \`main\` blob IDs retrieved from the GitHub API. Branch protection requires
  independently observed required PR reviews and status checks and forbids
  force pushes and deletion. Missing GitHub permissions/rulesets or changed
  policy files yields \`BLOCKED\`; no authentication is inferred from a
  PR-owned JSON field.
- The existing GitHub archive digest verifier and cross-SHA eligible-docs
  inspector remain distinct. Even if all three were satisfied, **automatic
  cross-SHA test reuse is not enabled in this PR**: policy lock-down must be
  deployed on the protected default branch first and complete dynamic
  dependency closure independently demonstrated.
- All new policy/memory/verification modules and Guide evidence scripts are
  classified as root-of-trust changes requiring FULL by Doctor's scope router.

### Actual user-journey contract execution, not a fabricated GUI PASS

\`tools/doctor_scenario_runner.py\` provides five explicit end-user contract
families (actual existing test modules, no generated mock tests):

- \`guide_quest_succes\`: Guide -> Quest links -> achievement mapping and UI
  navigation contracts;
- \`home_qt_lifecycle\`: Qt/WebEngine/home teardown contracts;
- \`progress_persistence\`: Guide, Quest and Success persistence contracts;
- \`startup_preload\`: startup, preload and resource contracts;
- \`guide_full_fixture_budget\`: PR #131 one-catalog-build and exact FULL test
  identity guardrails.

Only a clean exact-SHA worktree can execute these via the **canonical
unittest scope runner**, which rejects zero collected tests. Missing modules
and failures block. The successful status is specifically
\`CONTRACTS_PASS_METRICS_NOT_RUN\`, **not** a live Dofus session, complete
GUI replay, memory/CPU certification, or a Phase FULL PASS.

\`Doctor Adaptive Certification\` runs these Windows journeys only after
the PR leaves draft and the fast policy job succeeded; it does not rebuild
the catalog on each development commit. The final mandatory Phase FULL
still controls phase closure.

### Budget review and selected/unselected test traceability

- \`certification_metrics.py\` validates actual Phase 8 benchmark JSON
  numerically: preload ≤95 MB, each Home return strictly <100 MB,
  process-tree peak ≤220 MB, retention delta limits 15/20/2/1 MB.
  Missing values, duplicate stages, NaN/negative and boundary regressions
  become \`BLOCKED\`. A local JSON has no SHA provenance and can only
  earn \`LOCAL_NUMBERS_IN_BUDGET_UNATTESTED\`.
- \`certification_explain.py\` inventories every test and records why it was
  selected or deferred. An unselected test is **not** misrepresented as
  independent proof of no dynamic dependencies.
- \`certification_readiness.py\` produces an actionable deficiency list:
  runtime traces, exact-SHA scenario assertions, bounded metrics, GitHub
  provenance, policy trust, real shadow pairs, and mandatory FULL. No
  scenario or advisory PASS authorizes a merge.

### FULL performance improvement from PR #131 (integrated here, without
merging or deleting the still-open #131)

- Share a **single real GuideCatalogBuilder.build()** between the original
  Guide integration assertions and network-free guide file preservation;
  persist quest progress in one validated batch.
- Reuse three existing Guide runner suites only after parsing their **exact
  successful unittest IDs in the same successful FULL**. Any incomplete
  report/skip/failure falls back to executing those test modules normally.
- Preserve 100% discovery, all tests/assertions, independent Doctor FAST
  and all RAM/preload budgets.
- Keep PR #131 unchanged until this combined candidate has completed final
  certification; no double merge or competing builders.

### Historical FULL and real same-SHA shadow

During *final Phase Certification only*, the workflow creates
\`doctor_same_sha_plan.json\` and compares it with
\`03_atlas_integrity_full.json\` using \`doctor_shadow_campaign --pair\`.
It adds an independent failure condition on an invalid shadow record.
The combined report is archived alongside the original Phase verdict and
the FULL execution logs; no second FULL is launched. A FULL_REQUIRED plan
paired with a passing FULL merely confirms the conservative decision, it
does NOT establish that a targeted strategy can replace all future FULLs.

### Commands and release gate

During development, run no memory benchmark or heavy Guide/FULL.
After coding is complete:

1. Run the focused Doctor/Graphify/AI Context/Guide contracts and verify
   every required PR check on the **last exact SHA**.
2. Change the candidate out of draft for final Windows journey contracts.
   For a Phase-labeled PR the canonical \`Phase Certification\` FULL runs
   only at readiness/explicit dispatch; it must report PASS on that SHA.
3. Analyze FULL/Guide timings against recorded baseline; do not claim the
   target 15–30min FULL without a measured comparison.
4. Confirm mandatory Phase/FULL, data integrity, shadow, source trust,
   merger conflicts, branch rules, and never merge with a blocked check.

**Not automatically certifiable yet:** cross-SHA skipping across
PR-supplied policies, a real in-game GUI recording, and a formal policy
change waiving Phase FULL remain deliberately locked until independent
provenance, real runs, and policy review are complete. These are security
gates, not optional untracked TODOs.


## Windows journey isolation corrective

The first non-draft Windows journey run exposed a genuine test isolation
failure: a test accessing the QuestGraphService encountered
\`sqlite3.OperationalError: database is locked\` after other Qt/Quest tests
had run in the **same** Python interpreter.

The scenario executor now runs each selected canonical unittest module in a
**fresh Python process**, sequentially. All selected test modules still
execute and are recorded individually with exit codes, duration and
process-isolation evidence; no skip, xfail, module exclusion, or downgrade
of the phase FULL is used. A failed module makes the entire journey verdict
BLOCKED even if other modules pass. The Doctor evidence reader also rejects
a purported PASS missing any selected module or a nonzero module result.

This is an isolation fix for the *scenario test runner*, not proof that
application SQLite runtime locking was corrected. A reproducible error
under ordinary use must be fixed in the application separately.
