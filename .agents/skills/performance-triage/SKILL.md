---
name: performance-triage
description: Investigate startup, UI-thread, memory and loading regressions using existing performance tools and measured evidence.
---

# performance triage

Use for startup delays, UI freezes, memory growth, preload or cache regressions.

1. Read `AI_ENTRYPOINT.md`, `PERFORMANCE_GUARDRAILS.md` and current performance baselines/tests.
2. Reproduce a representative scoped workload and record environment, inputs and measurements before optimizing.
3. Discover canonical Doctor and performance tools via `tools.tool_catalog` before inventing a profiler or benchmark framework.
4. Inspect Qt thread work, repeated data parsing, unnecessary preloads, long-lived references, resource cleanup and invalidation.
5. Change the canonical owner minimally, remeasure comparable before/after runs and run functional regression tests.
6. For structural rewrites or shared-service movement, follow exact-SHA Graphify requirements.

Do not hide slow code behind timers, relax budgets merely to pass or call a headless measurement proof of Windows UI performance.
