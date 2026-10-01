---
name: atlas-doctor
description: Use Dofus Atlas Doctor for broad repository diagnostics, issue triage, architecture checks, performance inspection, targeted verification, and compact AI reports. Prefer this facade before calling lower-level diagnostic scripts directly.
---

# Atlas Doctor

Use `tools.atlas_doctor` as the canonical broad diagnostic facade. Start narrow and escalate only when the task needs more evidence.

## Default workflow

1. Confirm the repository state and current context with `py -3.13 -m tools.ai_context status`.
2. Run the cheapest Doctor mode that answers the question.
3. Prefer `--json` when another agent or script will consume the result.
4. Treat WARN/FAIL as evidence to investigate, not something to suppress by weakening checks.
5. Use specialized tools only when Doctor points to a domain that needs deeper inspection.

## Commands

- Fast health/audit summary: `py -3.13 -m tools.atlas_doctor quick --json`
- Static audit: `py -3.13 -m tools.atlas_doctor audit --json`
- Architecture graph inspection: `py -3.13 -m tools.atlas_doctor graph --json`
- Current actionable issues: `py -3.13 -m tools.atlas_doctor issues --json`
- Compact agent report: `py -3.13 -m tools.atlas_doctor report --json`
- Compare with previous audit: `py -3.13 -m tools.atlas_doctor compare --json`
- Live runtime/I/O inspection: `py -3.13 -m tools.atlas_doctor live --json`
- Performance lab: `py -3.13 -m tools.atlas_doctor perf --json`
- Targeted verification: `py -3.13 -m tools.atlas_doctor verify --hard --base-ref <ref> --json`
- Full Doctor pass: `py -3.13 -m tools.atlas_doctor all --json`

`--json` is accepted globally by Doctor even when placed after the subcommand.

## Cost and safety

`quick`, `audit`, `issues`, `report`, and `compare` are the normal first choices. `graph`, `live`, `perf`, `verify`, and especially `all` can be more expensive or environment-dependent.

`clean` deletes Doctor temporary files. Never run `py -3.13 -m tools.atlas_doctor clean` automatically unless cleanup is explicitly requested or clearly required by the current task.

Doctor observations are diagnostic evidence. They do not prove a file is dead, a dependency is removable, or a phase is certified. Structural deletion still requires exact-current-source/test evidence and Graphify when required by `AGENTS.md`. Phase closure still requires the certification workflow on the exact candidate SHA.

## Escalation

- For dependency/cycle/consumer questions, read the `atlas-graph-analysis` skill.
- For choosing among repository tools, read `atlas-tool-routing`.
- For change risk and validation gates, read `atlas-integrity`.
- For context routing and handoffs, read `atlas-ai-context`.
