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

## Atlas Doctor: human and agent entry point

Launch `Atlas_Doctor.bat` and choose **Architecture / Graph**. Viewing a graph does not regenerate it. The submenu explicitly offers rebuild, pinned installation through uv, or opening the HTML.

CLI:

```powershell
py -3.13 -m tools.atlas_doctor quick
py -3.13 -m tools.atlas_doctor graph --json
py -3.13 -m tools.atlas_doctor graph --rebuild --open
py -3.13 -m tools.atlas_doctor graph --install --open
py -3.13 -m tools.atlas_doctor report --json
py -3.13 -m tools.agent plan tools/atlas_doctor.py --structural --json
```

The quick diagnostic never probes, installs or executes Graphify. Architecture reads an existing graph by default. Doctor reuses its HEAD/worktree cache and validates the graph signature, pinned version and expected outputs; absent, unverified, stale or invalid graphs are explicit states. Tracked changes and untracked file contents invalidate provenance. Generated data remains ignored.

`tools/agent.py` owns context, scope, impact and plans. For refactors, deletion/moves, consumer discovery, dependency or cycle analysis, architecture cleanup and tool consolidation, agents must request `plan --structural`; that preflight requires a current graph and never starts a scan implicitly. A local non-structural edit uses the regular plan. Doctor owns diagnostics; `tools/graphify.py` owns the single pinned safe Graphify command sequence. `tools.atlas_integrity` remains the validation authority.

Doctor reads Graphify 0.9.72's real `nodes` / `links` format, `source_file` and `relation` fields. It reports counts, communities, connected components, isolated nodes, connections between files and count changes between snapshots. These rankings are observations, not anomaly scores or deletion verdicts. The JSON export is undirected; import-cycle findings remain in Graphify's report, not invented from undirected edges.

## Local Windows setup

From the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/graphify.ps1 -Open
```

The PowerShell wrapper preserves the low-level Windows setup entry. It delegates explicit installation to `tools.graphify` and generation to Doctor. The canonical Python engine executes the same three safe steps locally and in CI:

1. `graphify extract . --code-only` — AST extraction, no LLM/API key;
2. `graphify cluster-only . --no-label` — community clustering and structural report without LLM labels;
3. `graphify export html --graph graphify-out/graph.json` — interactive HTML viewer.

Generated local files include:

- `graphify-out/graph.html` — interactive visual map;
- `graphify-out/GRAPH_REPORT.md` — structural summary;
- `graphify-out/graph.json` — queryable graph data.

`graphify-out/` is intentionally ignored by Git so normal code changes do not create large noisy graph diffs.

## GitHub generation

The `Graphify Code Map` workflow builds an AST-only map for pull-request candidate SHAs and for canonical `main` updates. It calls Doctor and the canonical Python engine to cluster the graph without LLM labels, export the HTML viewer, verify the outputs and upload `graphify-out/` as a workflow artifact.

This keeps an exact-SHA structural map available to GitHub-based agents without committing generated graph data to the repository.

## Safety / project integration

Do **not** run `graphify hook install`. Dofus Atlas already owns repository-local Git hooks and AI instructions, so Graphify must integrate with those mechanisms rather than replacing them.

Graphify is a navigation and impact-analysis tool. Confirm important relationships against the current code and tests, especially inferred edges. A cleaner graph never justifies a functional, performance or persistence regression.
