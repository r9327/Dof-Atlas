# Dofus Atlas — Agent / Certification Decision Arena (P0)

This is a **reproducible, read-only routing benchmark**, not a new CI authority.
It complements certif bis #274 and deliberately reuses the existing domain,
Doctor CI and Qt-impact selectors. It does not introduce an agent executor,
a new gate, a new policy, or a Graphify replacement.

## What is implemented

- 32 explicit scenarios in tools/atlas_doctor_lib/ci_decision_arena_cases.json:
  ordinary docs, AI/agent instructions, CI policy, changed CI code,
  Guide/Quest/UI/Craft/startup/identity/persistence/data, mixed domains,
  unknown paths and removal.
- Each case is checked against tools.ci_domain_certification.plan_domains.
  Cases asking for UI evidence additionally execute the real
  doctor_ui_ci.classify_ui and ci_orchestrator.select_workflows selectors.
  They assert mandatory and unjustified specialist selections, not test PASS.
- A mismatch is an advisory failure and is covered by
  tests/test_doctor_ci_decision_arena.py, also in cheap Draft stdlib feedback.
  Host job conclusions and certification are **not** inferred from selected jobs.

## How to replay

From an up-to-date repository worktree, run:

    py -3.13 -m unittest -v tests.test_doctor_ci_decision_arena

For the JSON report, pass two real 40-digit SHA strings (used as scenario
identifiers, **not** authenticated Git checkout or merge-base evidence):

    py -3.13 -m tools.atlas_doctor_lib.ci_decision_arena --cases tools/atlas_doctor_lib/ci_decision_arena_cases.json --base-sha BASE_SHA --candidate-sha HEAD_SHA

Exit codes: 0 means expectations match (advisory); 1 indicates mismatch;
2 means input/error BLOCKED. No local result authorizes merge.

## Limits and the next increments

1. These synthetic cases do **not** prove complete consumer closure, dynamic
   imports, Windows/Qt runtime, real task completion or quality of an LLM.
2. Before optimizing broad app/**, tools/** and tests/** CI patterns,
   replay historical PR diffs against their original base/head and preserve
   exact baseline obligations, with independently recorded GitHub checks.
3. A next iteration should record per-change required coverage and actual
   job state (NOT_SELECTED, PENDING, RUNNING, SUCCESS, FAILURE,
   CANCELLED, SKIPPED, BLOCKED), and reject missing host evidence.
   PR-provided JSON never counts as independent host proof.
4. After the certification selector has measurable regression coverage, an
   actual **Agent Arena** can replay historical bug/refactor tasks with a
   separate code-writing agent, score tests/behavior, latency and cost, and
   observe bounded retries. Atlas Doctor retains plan/check/validate and
   CI/release remain the authoritative gates; agent outputs never certify
   themselves.

## Coordination

This is a stacked PR on #274 so routing expectations and the known CI-only
UI-classification fix are shared. When #274 is merged, retarget onto main
and rerun the official checks on the new exact head. PR #275 adds skills and
also edits .github/workflows/scoped-pr-ci.yml; retain **both** sets of Draft
tests when integrating. PR #268 (Atlas Delivery Guard) addresses actual
requirement-to-delivery tracing; this arena does not replace it.

Never turn a disabled, skipped or missing specialist into SUCCESS on the
basis of these examples, and never lower root-of-trust, FULL, Windows or
release conditions.
