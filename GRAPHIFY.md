# Dofus Atlas — Graphify

Graphify is an optional development map for navigating the Dofus Atlas codebase. It complements `AI_CONTEXT.md` and `tools/ai_context.py`; it does not replace the repository contracts, tests, or source code as the source of truth.

## Local Windows setup

From the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/graphify.ps1 -Open
```

The script installs the pinned `graphifyy` tool through `uv`, then builds an AST-only graph with no LLM/API key required.

Generated local files:

- `graphify-out/graph.html` — interactive visual map;
- `graphify-out/GRAPH_REPORT.md` — structural summary;
- `graphify-out/graph.json` — queryable graph data.

`graphify-out/` is intentionally ignored by Git so normal code changes do not create large noisy graph diffs.

## GitHub generation

The `Graphify Code Map` workflow can be started manually from GitHub Actions. It builds the same AST-only map and uploads `graphify-out/` as a workflow artifact.

## Safety / project integration

The first integration deliberately does **not** run `graphify hook install` and does not let Graphify rewrite `AGENTS.md` or `.codex/hooks.json`. Dofus Atlas already owns repository-local Git hooks and AI instructions. Any always-on Graphify/Codex integration must be merged deliberately with those existing mechanisms instead of replacing them.

Use Graphify as a navigation and impact-analysis aid. Confirm important relationships against the current code and tests, especially for inferred edges.
