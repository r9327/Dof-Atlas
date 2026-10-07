# Graphify 117 — staged graph cleanup

This roadmap prepares the Graphify cleanup that follows Phase 8 memory certification.
It is intentionally split into small, independently reviewable sections. No section may
silently grow into a repository-wide refactor.

## Baseline

Reference graph: commit `f40b60690b8c05885e52e906f2b28f81ff621b7f`.

- 11,148 nodes
- 32,756 relationships
- 438 communities
- 173 thin communities with fewer than 3 nodes omitted from the standard report
- 15 weakly connected symbols reported by Graphify
- 0 detected import cycles
- extraction: 94% extracted / 6% inferred
- 1,825 inferred edges, average confidence 0.92

Important hubs at this baseline include `normalize_text()`, `QuestCatalog`,
`QuestRecord`, `load_manual_chapter()`, `QuestProgressService`, `AtlasWindow`,
`GuidesView`, `Guide`, and `DataStore`.

The objective is **not** to minimize the raw community count. Legitimate isolation and
domain boundaries must remain isolated when that is the clean architecture.

## Working rules

Each section is a separate implementation lot. A lot should normally stay inside one
domain and touch at most a small handful of production files. If the evidence requires
a broader change, stop that lot and open a dedicated follow-up instead of widening scope.

After every implementation lot:

1. run targeted tests for the touched domain;
2. rebuild Graphify from the exact candidate SHA;
3. compare nodes, relationships, communities, isolated symbols, inferred edges, and import cycles;
4. reject any unexplained new isolated symbol or import cycle;
5. keep Phase 8 memory/preload contracts intact when the touched path can affect startup, Encyclopedia, Guide, Quests, Success, Craft, or Equipment.

No file or symbol is removed merely because Graphify calls it isolated. FFI structures,
platform adapters, test-only helpers, CLI entrypoints, and compatibility boundaries may
be legitimately weakly connected.

## 117.1 — Isolated-symbol classification

Scope: the 15 weakly connected symbols highlighted by the current Graphify report.

Classify every item as one of:

- legitimate platform/FFI boundary;
- legitimate tool/test/CLI boundary;
- dead or retired code with usage proof;
- missing architectural edge / incorrect import boundary;
- duplicate compatibility wrapper.

Only actionable items are changed. Legitimate isolation is documented and retained.

Exit criteria:

- every reported isolated symbol is classified;
- zero unjustified isolated production symbol remains;
- no new isolated production symbol;
- 0 import cycles.

## 117.2 — Thin-community triage

Scope: the 173 communities with fewer than 3 nodes.

Do not process all 173 as one refactor. Split them into buckets first:

- tests;
- tools / audit / maintenance;
- native / platform adapters;
- active application runtime;
- legacy / compatibility;
- generated or deliberately standalone entrypoints.

Only active-runtime and proven legacy/duplicate buckets are actionable.

Exit criteria:

- actionable thin communities have an owner/domain and disposition;
- no merge is performed only to reduce the community count;
- no cross-domain coupling is introduced.

## 117.3 — Guide legacy and duplicate boundaries

Scope: Guide-only subgraphs that represent versioned, compatibility, retired, or
duplicated entrypoints.

Work one subgraph at a time. Preserve canonical Guide / Quest / Success contracts,
manual route behavior, progress behavior, and current memory architecture.

Exit criteria for each subgraph:

- one canonical path remains where duplication is proven;
- targeted Guide tests pass;
- Graphify shows no new isolated nodes/cycles;
- Guide open/detail performance and Phase 8 memory gates do not regress.

## 117.4 — Encyclopedia / progress service boundaries

Scope: cross-community bridges around `QuestProgressService`, Guide progress,
Success progress, and Encyclopedia orchestration.

The target is cleaner responsibility boundaries, not lower degree for its own sake.
Shared services may remain hubs when the dependencies are legitimate.

Exit criteria:

- no dependency inversion violation introduced;
- no duplicated progress authority;
- no eager-import regression;
- 0 import cycles;
- memory/preload contracts stay green.

## 117.5 — High-connectivity hubs

Review the major Graphify hubs individually:

- `normalize_text()`
- `QuestCatalog`
- `QuestRecord`
- `load_manual_chapter()`
- `QuestProgressService`
- `AtlasWindow`
- `GuidesView`
- `Guide`
- `DataStore`

A hub is changed only when Graphify plus source evidence proves mixed responsibilities,
avoidable imports, or duplicated adapters. High degree alone is not a defect.

Each hub remediation is its own small PR/lot when production behavior changes.

## 117.6 — Final graph certification

Final acceptance after all chosen cleanup lots:

- 0 detected import cycles;
- no unjustified isolated production symbols;
- no unexplained increase in thin communities;
- no unexplained increase in inferred relationships;
- Graphify outputs present and current for the final SHA;
- Public PR CI green;
- AI Context green;
- Phase certification green;
- Phase 8 memory/preload budgets remain green.

The final comparison must report both the baseline and final Graphify metrics. A lower
community count is a useful signal only when the removed boundaries were genuinely
duplicate or obsolete.
