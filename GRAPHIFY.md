# Dofus Atlas — Graphify

Graphify is the structural code map for Dofus Atlas. It complements `AI_CONTEXT.md` and `tools/ai_context.py`; it does not replace repository contracts, tests, or source code as the source of truth.

Graphify is mandatory for non-trivial structural work: refactors, code deletion or moves, dependency/cycle analysis, consumer discovery, architecture cleanup and blast-radius analysis. It is optional for trivial edits that do not change code structure.

## Agent contract

Before a structural change:

1. identify the exact candidate SHA;
2. use a Graphify graph built from that same SHA;
3. inspect the relevant nodes, hubs, cycles, communities and cross-community relationships;
4. use the graph to discover likely consumers and impact paths;
5. confirm important relationships in the current source and tests before editing;
6. after the change, regenerate Graphify when the structural impact is meaningful and compare the affected area.

Do not justify deletion or decoupling from text search alone when Graphify can expose structural consumers.

If an agent has a local checkout, it should generate or refresh the graph locally. If it only has GitHub access, it should use the `Graphify Code Map` workflow artifact for the exact SHA when available. If neither is possible, the agent must state that limitation and stop before a risky structural refactor rather than claiming Graphify was used.

## Local Windows setup

From the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/graphify.ps1 -Open
```

The script installs the pinned `graphifyy` tool through `uv`, then performs the three deterministic local steps used by this repository:

1. `graphify extract . --code-only` — AST extraction, no LLM/API key;
2. `graphify cluster-only . --no-label` — community clustering and structural report without LLM labels;
3. `graphify export html --graph graphify-out/graph.json` — interactive HTML viewer.

Generated local files include:

- `graphify-out/graph.html` — interactive visual map;
- `graphify-out/GRAPH_REPORT.md` — structural summary;
- `graphify-out/graph.json` — queryable graph data.

`graphify-out/` is intentionally ignored by Git so normal code changes do not create large noisy graph diffs.

## GitHub generation

The `Graphify Code Map` workflow builds an AST-only map for pull-request candidate SHAs and for canonical `main` updates. It clusters the graph without LLM labels, exports the HTML viewer, verifies the outputs and uploads `graphify-out/` as a workflow artifact.

This keeps an exact-SHA structural map available to GitHub-based agents without committing generated graph data to the repository.

## Safety / project integration

Do **not** run `graphify hook install`. Dofus Atlas already owns repository-local Git hooks and AI instructions, so Graphify must integrate with those mechanisms rather than replacing them.

Graphify is a navigation and impact-analysis tool. Confirm important relationships against the current code and tests, especially inferred edges. A cleaner graph never justifies a functional, performance or persistence regression.
