# Doctor HIGH → SMART — Canary Guide progression (policy v1)

**Status: candidate policy, not globally enabled or proven against a real HIGH PR.**

The HIGH risk label is not a reason to call an ordinary unit test a FULL
certification. This migration starts with a **single exact owner**:
`app/modules/encyclopedia/services/guide_progress_service.py`.
The only additional code paths allowed in its candidate diff are
`tests/test_guide_progress_persistence.py`,
`tests/test_progress_cross_surface_reload.py`, generated
`.ai/context_index.json`, and ordinary docs. Every other runtime owner, a
deleted/renamed file, an unknown dependency, a changed workflow, certification
policy, or a CRITICAL path retains **FULL_REQUIRED**.

## Independent approval chain

1. Canonical scope checks the exact path, the existence of **both** mandated
   regressions and direct test ownership. It never grants certification.
2. Doctor checks the exact head/base SHA, tests selected, reverse source
   consumers, dynamic import uncertainty, transitive test coverage and all
   independently required scenario contracts. **Any pending Qt/memory/startup/
   data metric forces FULL**; a mere test PASS is insufficient.
3. The independent Doctor policy and Phase gate check the same closed-world
   source and tests. Phase runs the real scoped tests on Windows and checks
   the passport on the candidate SHA. A scoped PASS remains
   `SCOPED_PASS_NOT_FULL`, never `CERTIFIED`.
4. The GitHub merge-policy gate cannot approve this HIGH route from PR JSON.
   It requires an actual **successful exact-head pull_request workflow**,
   bound to the PR number, source branch, base branch and exact base SHA,
   belonging to this repository, with the exact Phase job and mandatory
   executed scoped steps. A skipped test, failed job, stale/foreign run or
   full step relabeled as SMART blocks. `Public PR / Safe Validation`
   must also PASS, including every Doctor-selected UI/benchmark specialist.
5. Manual phase certification and main branch release certification still
   mandate FULL. The FULL policy, guide baselines and release status vocabulary
   remain unchanged. The Phase 8 memory benchmark retains its targets but
   permits a maximum +5% measurement tolerance, with explicit warnings for
   over-target readings; missing, malformed, non-finite or boolean stage,
   preload, retained and peak RSS observations remain blocking. Craft retention
   beyond 2.10 MB still fails.

The remote `Certification Policy / Merge Gate` is **still advisory**
(`--enforce false`). Activating enforcement and replacing the broader
HIGH default requires a separate administrator-approved branch-rule change;
a green canary cannot be represented as a release certificate.

## Non-regression cases

Test the positive bounded route; mixed HIGH sources; changes to policy;
deletions; an absent mandatory test; unmapped imports; metrics obligations;
wrong SHA; stale, spoofed and skipped host steps; manual FULL override;
and a separate unchanged CRITICAL path.

**Next gate before production claims:** evaluate a real Guide progress change
against source impact and independent metrics. If the required metrics
cannot be independently attested, the desired result is FULL_REQUIRED,
not an automatic promotion to SMART.

## CI acceleration audit — historical work reused, not duplicated

This PR builds on already **merged** #130 (diff-scoped developer tests,
bounded pure-tooling parallelism, timing and duplicate inventory), #137
(Doctor adaptive policies), #140 (host-verified unique main FULL), #153
(exact per-test/fixture FULL timings and same-SHA Guide reuse), #204
(single CI router), #230 (final certification after Draft), #257 (bounded
specialist selection) and #258 (DIFF_TARGETS early abort). The locked pip
cache-dependency-path is already configured on the relevant Windows jobs.

The Doctor PR mini-audit now persists `artifacts/doctor_ci/pr_mini_audit.json`
with exact SHA/base, sensitive CI/policy paths, removed/renamed file inventory,
uncovered/unclassified paths (where the canonical router supplies them),
required jobs, route constraints and specialist fallback. The Markdown PR
summary is generated from that same advisory-only record. It is not a deep
source-security review, test execution, or merge PASS.

Doctor / CI Verdict also persists `artifacts/doctor_ci/job_timings.json` and
a Job Summary with elapsed durations, earliest completed failed job, a measured
run span, and explicitly excluded/pending/invalid observations. GitHub has
reported a **negative 1-second timestamp for a skipped Windows job** (run
#40140997450); the observer now excludes that skipped job instead of
discarding every valid timing. Actual GitHub billable minutes and genuine
dependency-graph critical path are **not** inferred from overlapping intervals.
Observability cannot waive any required job.

Existing `Scoped PR Feedback` now runs a cheap stdlib-only smoke automatically
on Draft PR opens/updates. The **actual** Doctor CI planner also generates
`artifacts/doctor_ci/plan.json` and the structured
`artifacts/doctor_ci/pr_mini_audit.json`, publishes a Markdown summary, and
archives both as `doctor-draft-audit-<run>-<attempt>`. It reuses the existing
router and does not launch Qt, LFS, specialist jobs or FULL. New audit/timing
regressions run alongside the historical selector tests.
The Windows scoped runner is still **manual-only**, and the Phase Ready/full
certification is unchanged. A Draft verdict can only say
`DRAFT_ROUTE_ONLY_NOT_CERTIFIED`, never claim Windows evidence or FULL. The final
Phase artifact upload runs **after** verdict enforcement, preserving a final
canonical verdict JSON when it exists. The independent diagnostic
`05_phase_outcome.json` is always attempted after enforcement, including on
failed/timeout paths; it has `certified: false` and cannot confer certification.
Aborted/timeout preflight also records a fail-closed status if the ordinary
report is unavailable. Git deletions and renames preserve their removed-path
semantics in the merge policy. PR classification uses the **merge-base diff**,
not unrelated changes that arrived on main. Every PR-hosted proof also requires
the independent successful `Public PR / Safe Validation` job on that same run,
including when the overall workflow has completed.

### Pending verification (not claimed complete)

- Benchmark Draft/Ready latency, green critical path and runner costs at the
  **final** candidate SHA, including cost of the PR-specific DIFF_TARGETS preflight.
- Demonstrate the HIGH → SMART route on a separate, bounded Guide progress
  source PR with real Windows, source-impact and GitHub host evidence.
- Experiment with immutable input caches and Windows FULL sharding only if
  all required test identities, fixture hashes, environment, failures and
  policy-equivalent results are proven; neither is enabled here.
- Cross-SHA reuse remains disabled until policy and dependency equivalence
  receive independent authenticated proof.

The older run #40133005156 measured Craft retained memory at 2.66 MB above
the 2.10 MB hard ceiling. Its failure remains valid for that candidate and
cannot be waived; it is not a validation of the current SHA.

### Observed certification failures, not waivers

[Run #40140997450](https://github.com/r9327/Dof-Atlas/actions/runs/40140997450)
found a malformed diagnostic JSON newline (fixed in `ab85ce2`) and reproduced
Craft retained RSS at **2.62 MB vs its 2.10 MB ceiling**. The Qt widget count
returned to its pre-Craft level after Home, but RSS did not: avoid claiming a
Qt-widget leak or classifying this as repaired without a Windows retest.
The preceding measurement was 2.66 MB. The independent pre-FULL gate correctly
skipped FULL, avoiding expensive work **but not certifying the PR**. No memory
threshold or required certificate has been relaxed.
