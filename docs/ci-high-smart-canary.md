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
   belonging to this repository, with the exact Phase job and mandatory
   executed scoped steps. A skipped test, failed job, stale/foreign run or
   full step relabeled as SMART blocks. `Public PR / Safe Validation`
   must also PASS, including every Doctor-selected UI/benchmark specialist.
5. Manual phase certification and main branch release certification still
   mandate FULL. No change to the required FULL policy, guide baselines,
   benchmark limits or release status vocabulary.

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
