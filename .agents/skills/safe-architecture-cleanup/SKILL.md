---
name: safe-architecture-cleanup
description: Audit suspected dead code, duplicate tools and dependency risks using existing Graphify and Doctor tools without deleting by default.
---

# safe architecture cleanup

Use for cleanup, tool consolidation, renames, deletions, consumer discovery, refactors and dependency audits. **Audit-only is the default.**

1. Read `AI_ENTRYPOINT.md`, `ZERO_TRUST_RULES.md`, `GRAPHIFY.md` and `tools/skills/dofus-atlas-tools/SKILL.md`.
2. Record candidate HEAD and preserve unrelated work. Structural changes require a Graphify graph for the **exact candidate SHA**, from a local rebuild or matching workflow artifact.
3. Use existing inventory: `py -3.13 -m tools.tool_catalog --preferred-only --safe-only --ready-only --json` and `py -3.13 -m tools.tool_audit --json`.
4. As needed inspect `py -3.13 -m tools.atlas_doctor graph-audit --deep --json`, `graph --impact <path> --json`, `consumer-sites`, `isolate-triage` or the canonical file investigation route.
5. Confirm likely consumers in source and tests, accounting for dynamic imports, Qt signals, configuration paths, assets, entry points, scripts and external callers.
6. Produce candidate path, source evidence, confidence, blast radius, compatibility risk, proposed action, rollback and targeted tests.
7. Only after adequate proof and authorization for any risky/destructive action, plan with `--structural`, change a bounded scope and revalidate relevant behavior.

A Graphify isolated node or zero references is **not proof of dead code**. If no exact-SHA graph can be executed or retrieved, stop before risky structural edits. Never remove user state or cleanup Git branches as a hidden audit side effect.
