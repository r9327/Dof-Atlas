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

### 117.1 classification baseline

The Graphify report at the baseline SHA reports exactly these 15 weakly connected symbols:

| Symbol | Source | Classification | Action |
| --- | --- | --- | --- |
| `PathProfile` | `guide_path_profiles.py` | active Guide model; Graphify misses constructor usage | keep |
| `_PcapInterface` | `npcap_capture.py` | ctypes/Npcap ABI structure | keep |
| `_PcapPacketHeader` | `npcap_capture.py` | ctypes/Npcap ABI structure | keep |
| `_Sockaddr` | `npcap_capture.py` | ctypes socket ABI structure | keep |
| `_SockaddrIn` | `npcap_capture.py` | ctypes socket ABI structure | keep |
| `_Timeval` | `npcap_capture.py` | ctypes/Npcap ABI structure | keep |
| `ScopeResult` | `tools/guide_ultime_scope_v4.py` | dead tool model; definition had no consumer | remove in 117.1 |
| `_MibTcpRowOwnerPid` | `windows_tcp.py` | ctypes Windows TCP ABI structure | keep |
| `_HotkeyWindowMixin` | `test_character_hotkey_mapping.py` | test-only mixin used by local fake windows | keep |
| `KBDLLHOOKSTRUCT` | `hotkeys.py` | ctypes Win32 keyboard hook ABI structure | keep |
| `MouseClick` | `input_state.py` | dead model; definition had no consumer | remove in 117.1 |
| `MSLLHOOKSTRUCT` | `mouse_hooks.py` | ctypes Win32 mouse hook ABI structure | keep |
| `POINT` | `mouse_hooks.py` | ctypes Win32 mouse ABI structure | keep |
| `guides` | `data/encyclopedia/guides/manifest.json` | canonical manifest data key, not a code symbol | keep |
| `schema_version` | `data/encyclopedia/guides/manifest.json` | canonical manifest version key, not a code symbol | keep |

Evidence used for the keep decisions is direct runtime/source usage: `PathProfile` is instantiated throughout `PROFILES`; the Npcap/Win32 structures are consumed through `ctypes.POINTER`, `ctypes.cast`, `sizeof`, or `from_buffer_copy`; and `_HotkeyWindowMixin` is inherited by the test fake windows. Those dynamic/native relationships are expected to be under-represented by an AST graph.

The two removals are intentionally limited to definitions with no extracted graph edge beyond their containing file and no local consumer. No replacement abstraction is introduced.

117.1 measured result on `a627aee1e24fe1acd9a71791c6695d1d8dfd0160`: 11,146 nodes, 32,753 relationships, 421 communities, 13 Graphify weakly connected symbols, 173 thin communities, 1,825 inferred edges, and 0 import cycles. AI Context and Graphify are green.

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

### 117.2 triage result

The post-117.1 graph still reports 173 thin communities. They are classified before any merge/refactor:

| Bucket | Count | Disposition |
| --- | ---: | --- |
| structural/file-only Graphify clusters | 73 | keep; graph structure/no production refactor |
| tests only | 83 | keep unless a later test cleanup has independent evidence |
| tools/scripts/hooks | 4 | inspect only for explicit legacy/consumer evidence |
| active `app/` runtime | 9 | reviewed individually; thinness alone is not actionable |
| mixed app + test | 1 | keep; active network status contract plus its test |
| `local_dofus_data` | 1 | keep; active Validator boundary |
| standalone entrypoint | 1 | keep; lifecycle cleanup in `main.py` |
| data manifest | 1 | keep; canonical Guide manifest keys |

The nine active-runtime thin communities are `GuideUltimeUniversalView`,
`ManualRouteGuidesView`, `_LazyCompatQuestDetailPanel`, `NetworkDebugGate`,
`WorldMenuScrollArea`, `QuestsPage`, the lazy `app.pages` package boundary,
`travel_command_from_url()`, and the `app.modules` package boundary. Their graph
nodes all have live runtime/test/native edges or intentionally lazy/package semantics;
none is merged merely to reduce the community count.

117.2 therefore performs **no production refactor**. The first proven legacy candidate
for the next Guide lot is the separate zero-degree file node
`tools/run_guide_ultime_v5.ps1`: the existing legacy-consumer contract already proves
it has no live consumers and marks it as deferred legacy.

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

### 117.5 — Première revue ciblée des hubs (8 octobre 2026)

Revue de code réalisée sur le HEAD initial de la PR #123 `375d5d6d`, **distinct** du HEAD RAM #116 `6c2f6b9a`. Il s'agit d'une première classification, **pas** d'une certification exhaustive Graphify 117.5.

| Hub / domaine | Indices vérifiés dans le code #123 | Décision à ce stade |
| --- | --- | --- |
| `normalize_text()` | fonction pure `app/quest_catalog.py:62`, utilisée par `guides_view.py` ; normalisation fonctionnelle métier | **KEEP**, aucun split cosmétique |
| `QuestCatalog` / `QuestRecord` | modèles `app/quest_catalog.py:199,247`, catalogue lazy branché depuis `quest_provider.py:19-51` | **KEEP**, chargement à la demande et références faibles critiques RAM |
| `load_manual_chapter()` | `guide_ultime_manual_route.py:470-533`, copie défensive, invalidation des signatures, limite de cache 96 entrées | **REVIEW**, ne pas changer le cache sans mesure process-tree/Guide et contrats de composition |
| `GuidesView` | `guides_view.py:1106`, même module `~4100` lignes, helpers VM tardifs et chargement images asynchrone | **REVIEW**, séparation éventuelle par responsabilité uniquement après preuve des consommateurs et comparaison RAM |
| `AtlasWindow` | `main.py:738`, factories différées `main.py:153-206`, pilotage lifecycle/preload | **KEEP provisoire**, aucune extraction avant stabilisation et replay des benchmarks RAM #116 |
| Progression Quêtes/Succès | `progress_service.py:207-260,549-588`, synchro dérivée, caches invalidés lors de sauvegarde | **REVIEW**, protéger la source de vérité et l'atomicité ; pas de fusion de services sans preuve |
| `DataStore`, `Guide`, autres hubs | chemins et consommateurs non établis lors de cette passe | **NOT REVIEWED**, à tracer dans le graphe exact-SHA et les sources avant verdict |

**Lot 117.5-A effectué en parallèle :** registre `tools/guide_tools_status.py` complété pour inclure l'ancien module `validate_guide_ultime_manual_transversals_v15` ; `tests/test_guide_tools_status.py` couvre désormais l'existence des modules canoniques et l'absence des outils déclarés retirés. Ce correctif ne modifie **aucun runtime / cache / preload**.

**Blocage de certification à résoudre après #116 :** la comparaison Git des deux HEAD initiaux indique une divergence depuis `f40b6069` : #116 possède **32 commits** non repris par #123, et #123 **57 commits** non repris par #116. Ne pas merger, rebaser ou écraser les branches à l'aveugle. Rejouer les contrats/Graphify sur le HEAD de convergence réel et vérifier spécifiquement `encyclopedia_page.py`, `progress_service.py`, Guide et preload. Les seuls checks Graphify/AI Context sur l'ancien SHA ne valident **pas** les tests globaux ni le budget mémoire final.

### 117.5 — Hub triage across all nine declared hubs (8 October 2026)

This is a **read-only classification** based on the two available real Graphify artifacts and directly inspected repository code. It is not a new Graphify build for the merged SHA.

Evidence: exact-SHA Graphify artifacts of `d16ca717` (Phase 8) and `375d5d6d` (Graphify); inspected files on the reconciled candidate `a803425e`. The link counts below are **undirected adjacency counts from Graphify**, not distinct source dependencies, errors, or reasons to split classes.

| Canonical hub | Phase 8 links | Graphify links | Decision / source evidence |
| --- | ---: | ---: | --- |
| `normalize_text()` | 272 | 271 | KEEP: pure shared text normalization in `app/quest_catalog.py:62`; many legitimate app/tool/test consumers |
| `QuestCatalog` | 182 | 182 | KEEP: `app/quest_catalog.py:247`; lazy catalogue and short-lived provider references preserve Phase 8 RAM behavior |
| `QuestRecord` | 174 | 174 | KEEP: `app/quest_catalog.py:199`; canonical record model, not a duplicated progress authority |
| `load_manual_chapter()` | 158 | 158 | KEEP with performance watch: `guide_ultime_manual_route.py:470-533` has bounded cache / deepcopy / invalidation; changing it needs same-runner RAM, Guide detail and composition tests |
| `QuestProgressService` | 157 | 157 | KEEP: `quest_progress_service.py:49+` uses path-scoped coordinator, generation and reloading to protect cross-widget persistence |
| `AtlasWindow` | 137 | 136 | KEEP: `main.py:738+`; high-degree shell orchestrator with deferred factories, no proven cheap low-risk split |
| `GuidesView` | 135 | 135 | KEEP for this PR: `guides_view.py:1106+` is large but asynchronous image paths / lazy detail ownership are memory-sensitive; a split based only on source length is unjustified |
| `Guide` | 111 | 111 | KEEP: immutable dataclass in `app/modules/encyclopedia/models/guide.py:13`; required_steps and linked_entities are canonical computed views |
| `DataStore` | 100 | 100 | KEEP: `local_dofus_data/data_store.py:26` owns SQLite WAL connection/transactions/migrations; do not change schema or lifecycle merely to reduce graph degree |

**Result:** all nine hubs reviewed; **zero evidence-backed hub refactors warranted for this PR**. Any future performance- or bug-proven hotspot belongs in its own bounded PR with benchmarks, not speculative architecture cleanup. Inferred Graphify edges are leads, not consumer proof.

**Orphan triage:** Phase 8 Graphify reports 7 zero-degree graph nodes. The earlier Graphify candidate has 6: `run_guide_ultime_v5.ps1` has been retired; `graphify.ps1`, `install_git_hooks.ps1`, `pre_commit.ps1`, `pre_push.ps1` are external/PowerShell or hook entry points; the two `__init__.py` nodes are package boundaries. No further deletion solely from zero degree.

**Community/cycle evidence:** the Phase 8 artifact records **11,181 nodes / 32,818 relationships / 424 communities / 171 thin**, with **zero detected import cycles**. The Graphify pre-reconciliation artifact records **11,060 / 32,488 / 417 / 177 thin**, with **zero detected import cycles**. These are **different SHAs and code baselines**, so their difference is **not** a valid before/after score for the merged candidate.

### Reconciliation against Phase 8 (PR #116)

The Graphify branch now contains a two-parent integration commit `a803425e`, combining the Graphify head `84d795e` and RAM head `d16ca717`. The root tree was based on the RAM candidate with Graphify's proven changes overlaid; the only overlapping production file, `encyclopedia_page.py`, preserves the RAM-side changes while migrating `ProgressiveQuestsPage` consumers to `LazyQuestsPage`. AI Context fingerprints were regenerated from the combined Git trees.

**Important:** resolving Git conflicts and checking the tree are *not* runtime or CI certification. Before merge, build Graphify from the **actual new HEAD**, run targeted and FULL/required Windows CI, and re-run RAM/preload tests from the integrated candidate. If #116 moves or merges, recheck ancestry/compare to the final new base.

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
