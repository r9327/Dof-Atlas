---
name: dofus-atlas-tools
description: Route AI agents through the canonical Dofus Atlas repository tooling for discovery, diagnostics, dependency analysis, integrity checks and controlled maintenance work.
---

# Dofus Atlas Tools

Use this skill when the task concerns repository tooling, diagnostics, code-health analysis, dependency/consumer discovery, integrity, Guide validation, CI/quality checks or controlled maintenance in Dofus Atlas.

This file is a routing playbook, not a second registry. The canonical machine-readable source of truth for AI-facing tools is `tools/tool_catalog.py` plus each tool's `TOOL_SPEC`. Never copy a tool's full CLI contract into this skill when the catalog can expose it directly.

## Start here

1. Read the root `AGENTS.md` and `tools/AGENTS.md`.
2. For non-trivial work, run `py -3.13 -m tools.ai_context status` and use the current ROAD IA scope.
3. Discover the current tool surface from the repository itself:

```powershell
py -3.13 -m tools.tool_catalog --json
```

For automatic agent execution, prefer canonical entry points that are both safe and automation-ready:

```powershell
py -3.13 -m tools.tool_catalog --preferred-only --safe-only --ready-only --json
```

Inspect one exact tool before using it when its contract, side effects or cost are not already known:

```powershell
py -3.13 -m tools.tool_catalog --tool tools/atlas_doctor.py --json
```

Filter by a required capability rather than guessing a script name:

```powershell
py -3.13 -m tools.tool_catalog --capability validation --safe-only --json
```

Use `--max-cost` and `--limit` when the task calls for a bounded/cheap discovery pass.

## Routing rules

- Broad repository health or post-change verification: select the current Doctor contract through `tools.tool_catalog` and follow its declared modes/costs.
- Structural refactor, deletion, dependency/cycle work or blast-radius analysis: Graphify is mandatory under the root contract. Read `GRAPHIFY.md`, use an exact-candidate-SHA graph when available, and confirm important consumers against source/tests before changing code.
- Tool inventory, consolidation or readiness analysis: use `py -3.13 -m tools.tool_audit --json` together with `tools.tool_catalog`; neither is sole proof that an apparently unused file is dead.
- AI context/navigation: use `tools.ai_context` and the scope manifests under `.ai/scopes/` rather than inventing a parallel context index.
- Integrity, Guide, agent/planner or other specialist work: query the catalog for the capability first, then use the selected canonical entry point and its `TOOL_SPEC`.

## Safety and mutations

Read-only discovery is the default. Do not automatically execute a tool merely because `safe_for_agent` is true; automatic execution requires `automation_ready=true` in the catalog.

Never automatically run a tool whose mutation state is unguarded or unknown. Repository mutation must be explicit through the tool's declared apply/write/repair-style gate. Respect declared side effects, verification requirements and cost boundaries.

Do not weaken tests, integrity gates, certification checks or guardrails to make validation green. Do not infer that a file is deletable from reference counts alone. Structural deletion requires Graphify/consumer evidence plus source/runtime/test confirmation.

## Validation discipline

Use the narrowest canonical validation that proves the requested change first. Escalate to broader Doctor/full/certification paths only when the task or project contract requires it.

For tooling changes, validate at least the directly affected contract tests and the relevant catalog/audit checks. Before reporting a phase or major lot as certified, follow `PHASE_CERTIFICATION.md`; a green PR alone is not certification.

## Reporting

When an agent used repository tooling, report the selected canonical tool or capability, the important validation performed, and any verification that could not be completed. Do not claim Graphify, Doctor, FULL validation or certification was run unless evidence exists for the exact candidate SHA.
