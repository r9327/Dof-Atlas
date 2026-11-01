# DOFUS ATLAS — projets GitHub utiles, audit et raccordement canonique
_Cadrage du 31/10/2026 — main étudié : `0ee44aeeb09358783dcceca799b743c6fb375299` ; issue de livraison [#311](https://github.com/r9327/Dof-Atlas/issues/311)._

> **État : étude et plan de câblage, pas d'intégration effective.** Les 29 projets évalués ici ne sont pas 29 nouvelles dépendances proposées au binaire. Tout outil nouveau passe par l'owner canonique, un benchmark ou un test contradictoire, et une décision documentée ; les projets REDUNDANT/REJECT ne seront pas installés. L'analyse documentaire est exécutée ; Doctor, Graphify, tests Qt/Windows, benchmark, certification et essais DOFUS **NOT_RUN dans cette PR**.

## 1. Pourquoi Atlas demande une approche différente de Holding

DOFUS ATLAS est un runtime **Windows x64 / CPython 3.13 / PySide6 6.12**, avec lock de distribution `requirements-pyside.txt` à empreintes SHA256. Le temps d'ouverture des modules, la rétention RAM en Qt, la continuité des guides Ganymède, l'intégrité des JSON/assets, les contrôles Windows et le lancement différentiel sont les coûts réels à optimiser.

**Ne pas ajouter une deuxième instance de ce que fait déjà Atlas.** Owners vérifiés sur `main` :
- Planification et routage : `tools.atlas_doctor` + `tools/atlas_doctor_lib/*`, `tools.agent`, `tools.ai_context`, `tools.tool_catalog` (dérivé des `TOOL_SPEC` ; pas un registre à recopier), `tools.tool_audit`, `tools.graphify`.
- Benchmark : `tools.atlas_doctor perf` → `tools/atlas_doctor_lib/exhaustive_performance.py`, `tools/benchmark_atlas_exhaustive.py`, `tools/atlas_perf_attribution.py`, `tools/benchmark_phase8_memory.py`, `tools/benchmark_phase8_preload.py` et `docs/doctor_performance_lab.md`. **Un seul moteur de mesure.**
- Données : `app/quest_source_index.py`, `app/quest_catalog.py`, `app/local_data_cache.py`, `app/modules/encyclopedia/providers`, `tools/atlas_json_inventory.py`, `tools/atlas_json_shards.py`. Conserver offsets/shards existants jusqu'à preuve de supériorité.
- UI Unity : `app/ui/theme.py`, `app/ui/unity_skin.py`, `app/ui/components.py`, `app/ui/styles/`, vues Encyclopedia, et `app/distribution/launcher_ui.py`. Ne pas remplacer le thème.
- Launcher : `app/distribution/launcher.py`, `release_client.py`, `install.py`, `manifest.py`, `data_pack_plan.py`, `data_pack_store.py`, `health.py`, `self_update.py`, `install_location.py`. **Une seule chaîne d'update, hash, staging et rollback.**
- Guides : code sous `app/modules/encyclopedia/` + `tools/guide_integrity.py`, `tools/ganymede_*`, progrès/identités existants. Aucun fournisseur GitHub ne doit devenir une nouvelle source canonique de données DOFUS.

## 2. Catalogue de 29 projets — affectation précise

### A. Qualité Qt/Windows et tests (5)

| ID | GitHub | Décision | Propriétaire et usage exact | Acceptance / anti-doublon |
|---|---|---|---|---|
| ATOSS-01 | [pytest-qt](https://github.com/pytest-dev/pytest-qt) | **ASSESS P0** | Tests `tests/test_*qt*.py`, `tests/test_atlas_doctor_app_ui_smoke.py` ; piloter `QSignalSpy`, événements et interactions Guides | Rejouer un clic/validation, fermeture/reprise, signal ; comparer aux helpers PySide6 existants ; uniquement dev/CI |
| ATOSS-02 | [Hypothesis](https://github.com/HypothesisWorks/hypothesis) | **ASSESS P0** | Tests d'invariants sur `app/storage.py`, services de progression, delta/install et Guide | Cas génératifs de crash, double clic, corruption JSON, reprise/rollback, key canonical ; graine reproductible |
| ATOSS-03 | [pywinauto](https://github.com/pywinauto/pywinauto) | **ASSESS P0** | `tests/test_distribution_*`, vraie installation/launcher Windows, `app/distribution/launcher.py` | Manipuler un vrai setup en VM ; succès, UAC, dossier custom, 75 % bloqué, rollback, sans proclamer réussite sur Linux |
| ATOSS-04 | [pytest-benchmark](https://github.com/ionelmc/pytest-benchmark) | **OPTION P2** | Tests micro de parser/offset/lookup via Doctor Perf Lab, **pas nouvelle mesure process-tree** | Comparaison même machine, même ensemble d'IDs, sortie importée au rapport Doctor ; non retenu si benchmark canonique suffit |
| ATOSS-05 | [pytest-xdist](https://github.com/pytest-dev/pytest-xdist) | **OPTION P2** | `tools/ci_dev_tests.py`, sélection Doctor de tests indépendants | Vérifier isolation caches/Qt/ports et reproductibilité ; ne paralléliser ni tests UI/processus ni persistance commune sans isolation |

### B. Profiling CPU, RAM et latence (5)

| ID | GitHub | Décision | Propriétaire et usage exact | Acceptance / anti-doublon |
|---|---|---|---|---|
| ATOSS-06 | [py-spy](https://github.com/benfred/py-spy) | **ADAPT_EXISTING P0** | Déjà documenté en option `--py-spy` sous **Doctor Perf Lab** ; ne pas refaire un profiler | Utiliser le switch existant ; preuve trace Speedscope sur guide lent ; surcoût et process arbre indiqués |
| ATOSS-07 | [VizTracer](https://github.com/gaogaotiantian/viztracer) | **OPTION P1** | Doctor Perf Lab, `tools/atlas_perf_attribution.py` seulement en diagnostic ciblé | Mesurer coût sur un freeze UI réellement reproduit, éviter trace permanente ; écarter si py-spy suffit |
| ATOSS-08 | [Scalene](https://github.com/plasma-umass/scalene) | **OPTION P1** | Doctor Perf Lab / Phase 8 memory : allocations Python et CPU, sans inclure trace instrumentée dans baseline | Vérifier support CPython 3.13 et Windows, résultats comparés `tracemalloc` ; sinon rejet |
| ATOSS-09 | [pyinstrument](https://github.com/joerick/pyinstrument) | **OPTION P2** | Doctor Perf Lab ; profiler temps Python à la demande, concurrent de cProfile déjà intégré | Garder uniquement si un blocage non expliqué demeure et si overhead acceptable |
| ATOSS-10 | [psutil](https://github.com/giampaolo/psutil) | **ADAPT_EXISTING P1** | Utiliser les collecteurs process-tree de `tools/benchmark_phase8_memory.py` / Doctor ; psutil seulement si attribution nouvelle manque | Même PID/tree, mémoire RSS des enfants, coût ; **pas de deuxième collecteur parallèle** |

### C. Données, images et recherche (7)

| ID | GitHub | Décision | Propriétaire et usage exact | Acceptance / anti-doublon |
|---|---|---|---|---|
| ATOSS-11 | [msgspec](https://github.com/msgspec/msgspec) | **ASSESS P0** | `app/quest_source_index.py`, providers, parsing JSON seulement après benchmark offsets/caches existants | Même schéma/IDs/Unicode et séquences ; cold/warm + pic RSS Qt ; ne pas lire un fichier entier plus tôt |
| ATOSS-12 | [orjson](https://github.com/ijl/orjson) | **OPTION P1** | `tools/atlas_json_benchmark.py` comparer avec stdlib/msgspec, même catalogue réel | Parité stricte, mêmes arguments, conversions compatibles ; choisir **au plus un parser** si gain net |
| ATOSS-13 | [ijson](https://github.com/ICRAR/ijson) | **OPTION P1** | Gros JSON, `tools/atlas_json_inventory.py`/index quêtes ; streaming si profilé nécessaire | Vérifier 68,97 Mio de Quêtes et 26,93 Mio manifeste images avec parité et mémoire mesurées ; pas d'ajout au démarrage sans gain |
| ATOSS-14 | [python-zstandard](https://github.com/indygreg/python-zstandard) | **OPTION P1** | `app/distribution/data_pack_*`, `app/distribution/release_client.py`, sans casser format actuel | Comparer taille/CPU/runtime/install/delta ; version de protocole, compatibilité anciens clients, SHA, reprise et rollback |
| ATOSS-15 | [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) | **ASSESS P1** | `tools/ganymede_*` et rapprochement de libellés pour **propositions à vérifier**, pas décision d'ID | Faux rapprochements bloqués, provenance Ganymède/Doduda, cohérence des IDs existants ; jamais de matching runtime canonique automatique |
| ATOSS-16 | [ImageHash](https://github.com/JohannesBuchner/imagehash) | **ASSESS P1** | Audit d'assets `tools/atlas_doctor_lib/*`, `app/assets/` ; doublons visuels suspects | Rapport advisory seulement (variants/icônes Unity), pas suppression de fichiers selon distance perceptuelle |
| ATOSS-17 | [fontTools](https://github.com/fonttools/fonttools) | **OPTION P2** | Audit fonts `app/assets/themes/dofus_unity/`, QFont et fallback ; outil offline de build/audit | Noms/coverage glyphes/licence, rendu exact Windows/DPI ; ne pas embarquer de police non autorisée |

### D. Code intelligence, sécurité et évaluation IA (8)

| ID | GitHub | Décision | Propriétaire et usage exact | Acceptance / anti-doublon |
|---|---|---|---|---|
| ATOSS-18 | [ast-grep](https://github.com/ast-grep/ast-grep) | **ASSESS P1** | `tools/agent.py`, `tools/atlas_doctor_lib/consumer_sites.py` ; recherche AST complémentaire à Graphify | Consommateurs runtime confirmés, pas de refactor ni correction automatique sur heuristique seule |
| ATOSS-19 | [Semgrep](https://github.com/semgrep/semgrep) | **ASSESS P1** | Doctor / analyse ciblée de motifs sûreté, **pas nouveau verdict de certification** | Comparer aux détecteurs existants/AST, cas de faux positif, budget de temps, rapports advisory |
| ATOSS-20 | [Ruff](https://github.com/astral-sh/ruff) | **ASSESS P1** | `tools/ci_dev_tests.py` et Doctor `agent check`; contrôle sur changements ciblés | Baseline, pin version, pas d'autoformatage massif ni seuil changé pour « vert » |
| ATOSS-21 | [zizmor](https://github.com/zizmorcore/zizmor) | **ASSESS P1** | Audit `.github/workflows/` et `tools/ci_* ; GitHub CI sécurité existante | Tests sur fixture de workflow malveillant ; pas de nouvelle CI lourde imposée à chaque commit |
| ATOSS-22 | [Gitleaks](https://github.com/gitleaks/gitleaks) | **ASSESS P1** | Contrôle secrets de commit sur CI/hooks Git existants ; erreurs expurgées | Secret fixture détecté, faux positif documenté, pas d'envoi de secrets, pas de scanner parallèle sans besoin |
| ATOSS-23 | [OSV-Scanner](https://github.com/google/osv-scanner) | **OPTION P1** | Audit de `requirements-pyside.txt` / chaîne de release, choisir contre scanners existants | Rapport version/dépendance/Windows/lock authentifié, aucune mise à jour implicite |
| ATOSS-24 | [Pydantic Evals](https://github.com/pydantic/pydantic-ai) | **OPTION P2** | Jeux de scénarios Doctor / agents, **pas d'IA en production** | Les cas évaluent changements code sur SHA exact et tests indépendants ; pas d'autonotation de succès |
| ATOSS-25 | [OpenTelemetry Python](https://github.com/open-telemetry/opentelemetry-python) | **OPTION P2** | Faire correspondre spans/IDs aux événements existants de Doctor et `tools/atlas_doctor_lib/cost_attribution.py` | Aucune double collecte de durée ni diffusion réseau par défaut, surcharge RAM/CPU mesurée |

### E. Extensions à rejeter ou à activer seulement si besoin (4)

| ID | GitHub | Décision | Motif |
|---|---|---|---|
| ATOSS-26 | [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) | **OPTION P2** | Le tooling Atlas est Python/TOOL_SPEC, non un hub MCP. Connecter **dans Holding** et n'exposer des diagnostics Atlas que via les interfaces du dépôt, après besoin vérifié ; ne pas démarrer de daemon Atlas |
| ATOSS-27 | [MCP Inspector](https://github.com/modelcontextprotocol/inspector) | **OPTION P2** | Test côté **Holding** du pont MCP pour outils Atlas ; pas une application embarquée dans le runtime Atlas |
| ATOSS-28 | [QtAwesome](https://github.com/spyder-ide/qtawesome) | **REJECT défaut** | Atlas possède déjà les assets et icônes Unity. Doublon esthétique, imports Qt et charge mémoire inutiles, sauf manque réel de pictogrammes démontré |
| ATOSS-29 | [PyQtDarkTheme](https://github.com/5yutan5/PyQtDarkTheme) | **REJECT défaut** | Thème Unity canonique présent ; substituer une palette générique introduirait des régressions de cohérence visuelle |

**Projets supplémentaires étudiés, sans adoption :** [OpenHands SDK](https://github.com/OpenHands/software-agent-sdk) est pertinent pour le moteur Holding, pas pour l'application Atlas ; [LangGraph](https://github.com/langchain-ai/langgraph) ne doit pas devenir un second orchestrateur. `Pillow` figure **déjà dans la lock runtime** ; ne pas l'ajouter une deuxième fois. `Graphify`, `Doctor`, `py-spy` et le benchmark existant ont la priorité sur leurs remplaçants.

## 3. Raccordement réel à développer, dans l'ordre et sans duplication

> Les chemins indiquent **les endroits où modifier le code si un écart est prouvé**, pas une installation réalisée par cette PR. Les services existants demeurent responsables et aucune dépendance externe ne peut modifier seule le runtime, les capacités ou la certification.

| Lot | Owners / fonctions canoniques | Composants candidats | Première preuve requise | PR existante à respecter |
|---|---|---|---|---|
| AT-L01 **Preflight** | `tools.tool_catalog`, `tools.tool_audit`, `tools.ai_context`, Doctor `agent plan` | tous en inventory seulement | Manifest réel installed/available/version/licence et tests existants, import sans side effect, README/outil consommateur | #303/#310 |
| AT-L02 **Bottlenecks** | Doctor Perf Lab, `atlas_perf_attribution`, `benchmark_phase8_*` | py-spy existant, VizTracer/Scalene/psutil facultatifs | Comparer deux mesures cold/warm/idle avec durée et RAM/children ; isoler I/O vs CPU vs Qt ; overhead de profiler explicite | #303 et #310 |
| AT-L03 **JSON/Quêtes** | `quest_source_index`, `atlas_json_*`, providers/Quêtes | msgspec vs orjson vs ijson (un seul candidat final) | Parité noms/IDs/indices + 68,97 Mio JSON ; impact sur 1er rendu et process-tree ; revenir au parser existant si gain non démontré | #303/#310 |
| AT-L04 **Guide/Ganymède** | `guide_integrity`, `ganymede_*`, services progression et vues | RapidFuzz outil de diagnostic, Hypothesis, pytest-qt | Séquence 20 Dofus, 1694 étapes, liens sûrs, caractère/personnage et UI vraie ; ne jamais inventer ID | #306 + #304, et #303 pour perf |
| AT-L05 **Qt/Unity** | `app/ui/theme.py`, `unity_skin.py`, widgets/Encyclopedia, tests Qt | pytest-qt, ImageHash/fontTools en outil de revue | Screenshots références et DPI (100/125/150 %), focus, scroll, Qt signals, conformité UI Unity | #304 ; #303 UI QA |
| AT-L06 **Launcher** | `app/distribution/*`, tests install/delta/rollback/health | pywinauto, Hypothesis, zstandard **seulement si utile** | 75 % jamais figé, 1 fenêtre, dossier custom, no-op update, cold install, ZIP signée/hash, fail/rollback et EXE réel | #285 exclusivement |
| AT-L07 **Doctor/CI/agent** | `tools/atlas_doctor_lib/*`, `tools/ci_*`, `tool_catalog` | ast-grep, Semgrep, Ruff, zizmor, Gitleaks, OSV, Pydantic Evals | Tool call observé, tests de mutation/erreur, SHA, permissions ; outil consultatif != garde de certification | #310 puis #303 |
| AT-L08 **Pont Holding existant** | Atlas `tools.atlas_doctor` CLI JSON ; Holding possède déjà `holding/atlas_doctor_runner.py` et `holding/atlas_doctor_evidence.py` | **KEEP_EXISTING** pour Doctor ; MCP seulement pour des outils non couverts | Tester le pont `atlas-doctor-agent/v1` déjà implémenté sur Windows : SHA, worktree dirty, offline, quotas, timeout, worker ; **ne pas le remplacer par MCP** | Holding #60 |
| AT-L09 **Mesures finales** | Doctor → certification Phase & Windows réelle | pytest-benchmark micro seulement si utile, OpenTelemetry optionnel | Baseline vs post-changement même SHA/données/runner ; Home <100 Mio stabilisés, pic <=250 Mio, UI sans freeze et aucun gain fictif | #303/#310 + #285 |

**Graphe :** AT-L01 → AT-L02 et AT-L03 en parallèle → AT-L04/05/06 par PR propriétaire → AT-L07 et AT-L08 une fois les APIs stables → AT-L09 sur chaque dernier candidat. Un lot se termine par tests ciblés et audit des commits ; aucune FULL répétée au milieu des développements.

## 4. Audit croisé anti-oubli — Atlas + Holding, et conflits PR

- **Holding [#60](https://github.com/r9327/Atlas-Holding/pull/60)** : 21 candidats, 8 lots documentés ; aucune des nouvelles dépendances activée par #60. **Audit du code : le pont direct existe déjà** dans `holding/atlas_doctor_runner.py` et `holding/atlas_doctor_evidence.py` : CLI JSON Doctor, contrôle SHA/worktree et protocole `atlas-doctor-agent/v1`. Il faut tester ce pont sur Windows, pas le recréer. Le SDK MCP/Inspector concerne d'autres outils sans pont existant, avec `holding/mcp_policy.py` comme politique.
- **Atlas [#303](https://github.com/r9327/Dof-Atlas/pull/303)** : **fusionnée le 1er novembre 2026**. Les optimisations et instruments effectivement présents dans `main` sont la référence à auditer (aucun objectif RAM n'est présumé atteint). Ne pas ouvrir de branche `perf` concurrente ; ajouter un profiler au runtime UI violerait le budget sans preuve.
- **Atlas [#310](https://github.com/r9327/Dof-Atlas/pull/310)** : **fusionnée le 1er novembre 2026**, avant #303. Son registre d'audit et ses correctifs Doctor/CI sont à examiner dans le `main` actuel ; les cas `REVIEW` et `NOT_RUN` historiques ne deviennent pas automatiquement PASS du seul fait de la fusion ou d'un nouvel outil.
- **Atlas [#285](https://github.com/r9327/Dof-Atlas/pull/285)** : launcher/packaging/delta et fenêtres au propriétaire unique. Tester vrais binaires avec pywinauto ; ne pas redévelopper update/rollback.
- **Atlas [#306](https://github.com/r9327/Dof-Atlas/pull/306)** : continuité Ganymède ; les outils de rapprochement restent de l'aide à l'audit, non l'autorité Dofus.
- **Atlas [#304](https://github.com/r9327/Dof-Atlas/pull/304)** : écran Guides Unity ; n'importer aucun thème tiers concurrent.
- **Backlog local** : `ROAD_IA.md` conserve un seul NEXT (IA-1), `docs/roadmap/ATLAS_IDEES_AMELIORATIONS_2026-10-28.md` conserve son statut idées ; cette étude ne leur change pas d'état ni ne ferme leur portée. Le `tools.tool_catalog` reste dérivé des `TOOL_SPEC`, pas alimenté de promesses non testées.

### Déficits à examiner avant les intégrations (constat vs question)

1. **Vérifié** : `requirements-pyside.txt` ne contient aucun des nouveaux parsers ou profilers dans les premières dépendances consultées ; chaque paquet runtime exigerait version et hash Windows réels, compatibilité Py3.13 et inclusion EXE. **Ne pas ajouter en runtime par défaut.**
2. **Vérifié** : Doctor possède déjà un profiler `--py-spy` optionnel et `cProfile/tracemalloc` ; ne pas publier un second système de capture. Les autres profilers restent hypothèses non démontrées.
3. **Vérifié** : Ganymède, UI et launcher ont chacun leur PR active. Toute mutation concurrente doit être faite dans la branche propriétaire, en aval ou avec un plan de réintégration explicite.
4. **À vérifier en développement** : existence effective de l'exécutable py-spy sur le runner ; le document n'atteste pas de son exécution.
5. **À vérifier en développement** : compatibilité, licences par version et redistribution des wheels/binaries ; métadonnées GitHub générales insuffisantes.
6. **À vérifier en développement** : scripts/tool calls et vrais consommateurs, impact import/résident, sécurité, limites de température et RAM sur un PC faible ; aucune donnée du benchmark ci-dessus n'est un résultat neuf.
7. **Vérifié sur Holding** : l'adaptateur Doctor/CLI est déjà implémenté avec vérification stricte des identités ; son exécution réelle end-to-end sur Windows reste à prouver, ce qui est distinct d'un manque d'intégration Python.

**Actualisation du 1er novembre 2026 :** #285, #304 et #306 sont toujours des PR propriétaires Draft ; leurs changements et tests sont à vérifier sur les HEAD respectifs avant tout essai d'outil. La PR documentaire #312 n'implémente aucun lot de code AT-L01..L09 et ne doit pas être utilisée pour masquer les contrôles manquants de ces PR. Le contrat original est conservé sans réécrire rétrospectivement son étude du 31 octobre.

## 5. Acceptation et métriques obligatoires (AT-AC01…AT-AC14)

- [ ] AT-AC01 : tous les 29 projets sont identifiés avec URL, décision, propriétaire et coût/risque.
- [ ] AT-AC02 : cartographie des consommateurs réels au HEAD de la PR propriétaire avec Graphify exact-SHA avant tout changement structurel.
- [ ] AT-AC03 : aucun second benchmark, moteur de test, registre, cache, guide, updater, thème ou exécuteur.
- [ ] AT-AC04 : test de la vraie capacité d'un outil avant déclaration `automation_ready` ou `READY`.
- [ ] AT-AC05 : ajouter une dépendance seulement avec licence par version, Python 3.13/Windows, digest, poids runtime et plan rollback.
- [ ] AT-AC06 : isolation du test Qt, reprise/fenêtre fermée et aucun accès Qt depuis thread worker.
- [ ] AT-AC07 : cohérence Ganymède : route/étape/identité stable/persistance/chargement sans données inventées.
- [ ] AT-AC08 : JSON : ID, valeurs, relations, source hash, index offset et parité froide/chaude, consommation réelle.
- [ ] AT-AC09 : mémoire process-tree/CPU/latence P50/P95/P99, temps cold/warm, preload, Home stabilisé, mesure sur même runner.
- [ ] AT-AC10 : sécurité installer, no-op update, reprise, delta, rollback, données utilisateur et EXE Windows signés/vérifiés selon contrat existant.
- [ ] AT-AC11 : tool calls consultatifs, tests anti-injection, faux positif, tests de permissions et absence de connexions payantes ou externes automatiques.
- [ ] AT-AC12 : suite Doctor ciblée puis certification intelligente/FULL seulement au bon moment, résultats exact-SHA et NOT_RUN explicites.
- [ ] AT-AC13 : audit commit par commit puis global des PR propriétaires, inventaire des omissions, compatibilité des commits adjacents.
- [ ] AT-AC14 : décision `KEEP_EXISTING / ADAPT_EXISTING / TRIAL / REJECT` avec gain prouvé, pas adoption sur réputation GitHub.

## 6. Portée exacte de cette PR

**LIVRÉ :** recherche comparative, liens source, propriétaires présents vérifiés, décisions par candidat, lotissement, dépendances PR, audit croisé et découverte depuis README. Les outils déjà disponibles restent les seuls exécutables autorisés par leurs contrats actuels.

**NON LIVRÉ / NON EXÉCUTÉ :** aucun package installé ou modifié ; ni outil activé dans le catalogue, ni changement de code `app`/`tools`, ni benchmark, ni test Windows, ni Graphify exact-SHA sur cette branche, ni validation de release. L'audit croisé ne certifie pas les PR #60/#303/#310/#285/#304/#306 ; leurs tests et attestations restent indépendants.

Les intégrations futures doivent être réalisées **dans les PR propriétaires ou des PR petites sans chevauchement**, à partir de leurs vrais HEAD avec code, tests ciblés, contrôle de l'impact et mesures. **Ne jamais réduire une exigence de la PR existante parce qu'un outil est nouveau.**

## Références de gouvernance

[AGENTS.md](../../AGENTS.md), [AI_ENTRYPOINT.md](../../AI_ENTRYPOINT.md), [DEVELOPMENT_GUARDRAILS.md](../../DEVELOPMENT_GUARDRAILS.md), [PERFORMANCE_GUARDRAILS.md](../../PERFORMANCE_GUARDRAILS.md), [PHASE_CERTIFICATION.md](../../PHASE_CERTIFICATION.md), [ROAD_IA.md](../../ROAD_IA.md), [Graphify](../../GRAPHIFY.md), [Doctor Perf Lab](../doctor_performance_lab.md), [Delivery Guard](../delivery/DELIVERY_GUARD.md), [outillage IA](../../tools/skills/dofus-atlas-tools/SKILL.md).


## 7. Compléments de l'audit croisé — cinq candidats supplémentaires

Les **29 projets du tableau principal restent le contrat documentaire de la PR**. La recherche parallèle #314 a identifié **5 références supplémentaires non présentes dans ces 29** (soit **34 projets examinés** au total). Elles ne sont **pas ajoutées d'office aux dépendances**, aux 29 IDs ni au plan de test ; leur sort se décide dans les propriétaires existants et peut être `KEEP_EXISTING` ou `REJECT`. Cette annexe évite une perte de recherche sans déplacer le scope ou réduire les exigences de l'issue #311.

| ID annexe | Projet GitHub | Propriétaire existant / décision provisoire | Preuve exigée avant adoption |
|---|---|---|---|
| AT-SUP-01 | [jsonschema](https://github.com/python-jsonschema/jsonschema) | `tools/atlas_json_inventory.py` et `tests/test_critical_json_schema.py` ; **TRIAL** sur schémas non déjà couverts | Fixtures de liens/IDs invalides, compatibilité avec règles de progression Dofus, coût dans Doctor, zéro second validateur de référence |
| AT-SUP-02 | [PyInstaller](https://github.com/pyinstaller/pyinstaller) | `scripts/windows/package_release.py` et `scripts/windows/certify_public_install.py` ; **ASSESS_EXISTING** | Identifier le packager réel et sa version sur la branche propriétaire #285, puis tester build/EXE/antivirus/QtWebEngine sur Windows sans migration inutile |
| AT-SUP-03 | [Nuitka](https://github.com/Nuitka/Nuitka) | Packaging Windows ; **REFERENCE_ONLY** | Comparaison isolée contre build actuel, licence/redistribution (GitHub signale AGPL-3.0), taille, mémoire, cold start, coût CI ; pas de remplacement par défaut |
| AT-SUP-04 | [pip-audit](https://github.com/pypa/pip-audit) | Validation de `requirements-pyside.txt` ; **CHOOSE_ONE** face à OSV-Scanner | Audit exact des versions verrouillées, faux positifs, fraîcheur/conditions offline, pas de deux scanners obligatoires à chaque PR |
| AT-SUP-05 | [Pydantic](https://github.com/pydantic/pydantic) | Contrats JSON et actions `tools/guide_action_contract.py` ; **DEFER** | Montrer une validation utile absente des dataclasses/contrats natifs ; sinon conserver les règles existantes et zéro import runtime |

**Audit consolidé (Holding #60 et Atlas #312)** : la liaison `holding/atlas_doctor_runner.py` / `holding/atlas_doctor_evidence.py` doit être éprouvée en réel, **pas réimplémentée en MCP**. Les deux PR restent documentaires, leurs lots futurs sont `NOT_IMPLEMENTED`. Le suivi des exigences d'**implémentation effective** est distinct du dossier #311 et se trouve dans l'[issue Atlas #313](https://github.com/r9327/Dof-Atlas/issues/313) ; aucune de ses exigences code n'est déclarée accomplie. Une simple présence dans ce tableau ne vaut pas `TOOL_SPEC`, `READY` ou test d'exécution.
