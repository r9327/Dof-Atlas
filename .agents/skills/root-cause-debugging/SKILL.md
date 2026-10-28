---
name: root-cause-debugging
description: Diagnose bugs and regressions from reproducible evidence before implementing a targeted fix.
---

# root cause debugging

Use for functional bugs, intermittent failures and unexplained regressions.

1. Read `AI_ENTRYPOINT.md`, `DEVELOPMENT_GUARDRAILS.md` and affected source/tests.
2. Separate expected behavior from what was observed. Reproduce with the smallest safe test, trace or log available.
3. Follow the actual call, signal, data and thread paths until the earliest violated contract is identified. Use existing Doctor investigation tools; consult Graphify for structural impact.
4. Fix the canonical owner without introducing parallel mechanisms, silent broad exception handling or timer-based symptom patches.
5. Add or adjust a focused regression test when practical; run Doctor `agent check` and `agent validate` at the selected risk level.
6. Report what is proven, what changed, which tests actually ran and what remains uncertain.

Static inspection is not proof that a Windows GUI bug is fixed.
