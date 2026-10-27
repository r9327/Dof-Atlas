# AGENTS.md — Dofus Atlas

Canonical AI entrypoint: read `AI_ENTRYPOINT.md` first and route non-trivial
changes through `py -3.13 -X utf8 -m tools.atlas_doctor agent plan ... --json`.

Install the repository-local Git hooks once with `powershell -NoProfile -ExecutionPolicy Bypass -File tools/install_git_hooks.ps1`.

For every non-trivial task, first run `py -3.13 -m tools.ai_context status` and use `AI_CONTEXT.md` as the compact navigation layer. This does not replace the permanent project contracts below. The generated `.ai/context_index.json` is maintained by the pre-commit hook and must not be edited manually.

Before executing non-trivial AI work, establish a quality/consumption work card with `py -3.13 -m tools.agent_task_profiles`. Use the task topology to propose a sensible `economy`, `balanced` or `best` quality, but honor an explicitly requested quality even when it differs from the recommendation. The router selects the lowest-consumption configured tier that satisfies the chosen quality. This routing is independent from Atlas Doctor SOFT/MEDIUM/HARD validation levels: never use one system to infer, lower or replace the other. Actual provider model IDs are environment-specific; `.ai/task_profiles.json` is the stable routing policy, not a provider price list.

For every non-trivial structural task, Graphify is mandatory before modifying code. This includes refactors, code deletion or moves, dependency/cycle analysis, consumer discovery, architecture cleanup and blast-radius analysis. Read `GRAPHIFY.md`, use a graph built for the exact current candidate SHA when available, and inspect the relevant graph/report before editing. Use Graphify to discover relationships, then confirm important consumers and runtime behavior against the current source and tests. A text search alone is not sufficient justification for structural deletion. Trivial edits that do not change code structure do not require Graphify. If the environment cannot run Graphify and cannot access an exact-SHA Graphify artifact, stop before a structural refactor and report that limitation rather than pretending the graph was used.

Read `ZERO_TRUST_RULES.md` for the permanent short contribution contract.

## Universal PR CI cadence (all current and future PRs)

**Finish the entire scoped PR before running its GitHub CI certification.**
Keep every implementation PR in **Draft** while editing, even across multiple
commits. During development, use only focused local unit, contract and Doctor
checks; do not repeatedly dispatch full CI, phase certification, memory
benchmarks or Windows distribution workflows. Never interpret skipped/not-run
checks as PASS. This applies to guides, Doctor, Graphify, launcher, Organizer,
data, and every other PR without exception.

Once implementation, dependencies, tests and self-review are finished, ensure
the branch contains the complete final candidate and mark the PR **Ready for
review**. This single transition triggers Phase Certification on that SHA.
If final certification fails, return to Draft while fixing as appropriate,
then mark Ready for review again, or manually dispatch certification for the
new exact SHA. Never merge with stale evidence or skip mandatory tests.
Do not use `[skip ci]` as the primary workflow control: the official PR
trigger is intentionally limited to `ready_for_review`. Normal `main`
push/release safeguards remain enabled.


## Mandatory PR logic audit (each commit, then whole PR)

Before declaring a PR ready or recommending merge, review the **logic of every
commit** in order. Inspect each commit against its parent (not only the final
aggregate diff): the purpose of the change, correctness, compatibility with
existing behavior, consequences, regressions, security/persistence impacts, and
whether focused tests or missing checks are warranted. Give an explicit
per-commit assessment and, when justified, concrete additions or corrections.
A commit does not have to pass independently when it is an intentional step
toward a complete PR; judge its role and its effect on subsequent commits.

After the individual reviews, perform a **cross-commit/global PR audit** of the
full final candidate: consistency of decisions, interactions between commits,
integration, final diff, tests, remaining risks and compliance with the PR
scope. An apparently correct final diff or green CI cannot replace the
per-commit logic review; conversely, individually sound commits do not prove
the final composition is sound.

For the final verdict, use **VALIDATED** (no blocking issue found),
**IMPROVEMENTS RECOMMENDED** (non-blocking worthwhile corrections), or
**BLOCKED** (specific corrections required before merge). Distinguish
verified findings from hypotheses and untested areas. Avoid cosmetic changes,
speculative blockers and unnecessary refactors. Never claim certification
without the separate Phase Certification evidence on the exact SHA.

## Library documentation (Context7)

When an external library or API detail matters, prefer Context7 MCP (if available) for up-to-date, version-specific documentation before changing code. If MCP is unavailable, Codex can use the repository-scoped `.agents/skills/find-docs/SKILL.md` with the `npx ctx7@latest` CLI (Node.js 18+ required). Do not query both modes for the same answer. For example, verify PySide6 / QtWebEngine usage against the relevant version. Prefer focused documentation queries; cross-check the current code and tests. Context7 never overrides Atlas guardrails or becomes a source of Dofus game data. Never send secrets, personal data, or proprietary source to external documentation services. If neither Context7 mode is available, use official docs; do not block runtime or CI.

## Mandatory project contract

Before any non-trivial modification, read and follow:

- `DEVELOPMENT_GUARDRAILS.md`
- `PHASE_CERTIFICATION.md` when closing a phase or major lot

That file contains the project-specific anti-regression rules for the Guide Ultime, persistent progression, UI, runtime Windows, databases, launcher, CI and architecture. It takes precedence over generic cleanup instincts.

`PHASE_CERTIFICATION.md` defines the mandatory distinction between code completed, targeted validation and phase certification. A green PR is not phase certification.

If code and the guardrails appear inconsistent, inspect the current implementation and tests before changing either one. Do not silently bypass a guardrail.

---

## Project

Dofus Atlas is a Windows desktop application built mainly with Python, PySide6 and QtWebEngine.

The project evolves frequently.

Use the current repository, existing implementation and current task as the source of truth.

---

## Working method

For non-trivial tasks:

1. Inspect the relevant code before changing it.
2. Understand the current behavior and architecture.
3. For bugs, identify the root cause.
4. Choose a clean and robust solution.
5. Implement the requested behavior.
6. Validate the result.

Do not blindly follow a proposed technical implementation when a better solution exists.

Focus on the requested outcome.

### Ponytail discipline (repository-level)

For agents working directly from the repository, apply Ponytail-style minimalism as an additional decision filter. Project-specific Atlas guardrails always take precedence. The shared machine-readable profile is `tools/ponytail_policy.json`; Atlas Doctor consumes the same profile through `py -3.13 -m tools.atlas_doctor ponytail --json`.

Before adding code:

1. Skip work that is not actually required by the requested outcome.
2. Reuse the current canonical implementation before creating another one.
3. Prefer the standard library, native platform features or an already-installed dependency before adding a new dependency or abstraction.
4. Use the smallest coherent implementation that fully solves the current problem.
5. Do not generalize for hypothetical future needs or create parallel systems "just in case".
6. Never trade away validation, security, data-loss protection, accessibility or project guardrails merely to make the diff smaller.

---

## Autonomy

Use full engineering judgment.

For requests to build, change or fix something:

- make the necessary in-scope code changes;
- inspect related code when needed;
- refactor when genuinely justified;
- run relevant non-destructive tests and validation;
- fix problems introduced by the change before finishing.

Do not ask for confirmation for normal local development actions.

Ask before destructive actions, external side effects or major expansion beyond the requested scope.

Avoid unrelated rewrites or cleanup.

---

## Existing behavior

Unless the task explicitly changes it:

- preserve unrelated functionality;
- preserve user data and configuration;
- avoid unnecessary dependencies;
- avoid duplicate implementations;
- reuse existing components and systems when appropriate.

Prefer the smallest coherent and robust solution, not necessarily the smallest diff.

---

## UI

Dofus Atlas must feel like one coherent application.

Before creating or modifying UI, inspect existing relevant screens and reusable components.

Keep equivalent elements consistent across tabs, including where applicable:

- visual language;
- typography;
- spacing;
- controls;
- cards;
- navigation;
- interaction states.

Reuse established project patterns when appropriate.

Do not create an isolated visual style for one screen without a reason.

Do not preserve an outdated pattern when the current task intentionally changes or improves the shared design.

---

## Layout and scrolling

Interfaces must remain usable at reasonable window sizes.

Prefer proper Qt layouts and size policies over fragile fixed positioning.

Avoid unintended:

- overlap;
- clipping;
- content escaping its container;
- elements hidden behind other widgets;
- horizontal scrolling.

Scrolling should normally belong to the content area that actually overflows rather than unnecessarily scrolling an entire page.

Use fixed dimensions only when they are intentional parts of the design.

---

## Architecture and data

Respect the current architecture while allowing it to evolve when necessary.

Prefer:

- clear separation of data, logic and presentation;
- reusable components;
- one source of truth;
- simple maintainable solutions.

Avoid unnecessary abstraction and parallel systems solving the same problem.

Never fabricate application or game data.

Preserve persistent user data when changing formats and maintain compatibility when reasonably possible.

---

## Reliability

Fix root causes rather than hiding symptoms.

Avoid unnecessary:

- special cases;
- timers;
- fixed-size workarounds;
- duplicated logic;
- silent broad exception handling.

Unexpected failures should remain diagnosable.

Keep the application responsive and avoid unnecessary work on the Qt UI thread.

---

## Validation

A task is not complete merely because the code runs.

Use validation appropriate to the change.

For logic changes:

- run relevant tests when available;
- add or update targeted tests when useful.

For UI changes, when possible:

- launch the application;
- inspect the affected screen;
- interact with the affected behavior;
- resize the window;
- check nearby functionality for regressions.

If the change introduces a problem, fix it before finishing.

For a phase or major lot, do not report `CERTIFIED`, `phase terminée`, `100 % terminée` or an equivalent final state unless the `Phase Certification / Full Validation` workflow has passed on the exact candidate SHA. `Public PR / Safe Validation` alone is never sufficient.

After a phase has both `Public PR / Safe Validation` = PASS and `Phase Certification / Full Validation` = PASS on the same exact SHA, perform a conservative Git cleanup for that phase before moving on: remove only branches proven redundant, merged or temporary, preserve anything containing unique work, and do not change the certified product SHA as part of cleanup.

---

## Scope

Stay focused on the requested result.

Do not modify unrelated parts of the project simply because they could be improved.

Adjacent changes are allowed when they are genuinely required for correctness, consistency or a clean root-cause fix.

---

## Final review

Before finishing:

1. Inspect the final diff.
2. Remove accidental unrelated changes.
3. Run relevant validation.
4. Confirm that the requested behavior actually works.
5. Check relevant existing behavior for regressions.
6. For phase closure, confirm the exact SHA has a successful phase-certification run.

Keep the final report concise and mention:

- what changed;
- root cause when relevant;
- important files modified;
- validation performed;
- anything that could not be verified.
