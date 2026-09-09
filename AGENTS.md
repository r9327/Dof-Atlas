# AGENTS.md — Dofus Atlas

Install the repository-local Git hooks once with `powershell -NoProfile -ExecutionPolicy Bypass -File tools/install_git_hooks.ps1`.

Read `ZERO_TRUST_RULES.md` for the permanent short contribution contract.

## Mandatory project contract

Before any non-trivial modification, read and follow:

- `DEVELOPMENT_GUARDRAILS.md`

That file contains the project-specific anti-regression rules for the Guide Ultime, persistent progression, UI, runtime Windows, databases, launcher, CI and architecture. It takes precedence over generic cleanup instincts.

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

Keep the final report concise and mention:

- what changed;
- root cause when relevant;
- important files modified;
- validation performed;
- anything that could not be verified.
