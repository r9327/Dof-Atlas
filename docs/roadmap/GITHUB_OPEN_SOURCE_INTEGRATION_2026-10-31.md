# DOFUS ATLAS — intégration ciblée de projets GitHub (31 octobre 2026)

> **État : PROPOSÉ — cadrage vérifié sur GitHub ; intégrations externes NON EXÉCUTÉES.** Contrat source [#313](https://github.com/r9327/Dof-Atlas/issues/313). La présence d'un outil dans un document ou d'un binaire sur une machine ne prouve ni son branchement, ni son fonctionnement. Cette PR n'altère pas la certification.

## Principes obligatoires

1. Respecter [AGENTS.md](../../AGENTS.md), [AI_ENTRYPOINT.md](../../AI_ENTRYPOINT.md), [ZERO_TRUST_RULES.md](../../ZERO_TRUST_RULES.md), [DEVELOPMENT_GUARDRAILS.md](../../DEVELOPMENT_GUARDRAILS.md), [PHASE_CERTIFICATION.md](../../PHASE_CERTIFICATION.md), [Graphify](../../GRAPHIFY.md), [performance](../../PERFORMANCE_GUARDRAILS.md) et [Delivery Guard](../delivery/DELIVERY_GUARD.md).
2. **Aucun plugin/DI/plugin runtime supplémentaire, second Doctor, second benchmark, second code graph ou second registre.** Les projets candidats se greffent dans les modules canoniques ci-dessous avec un comportement désactivé en absence d'outil.
3. **D'abord mesurer la baseline sur le même matériel**, puis comparer avec/sans outil à SHA, données, version Python, Windows et conditions identiques. La cible Phase 8 est **Home stabilisé < 100 Mio**, pic process-tree **≤ 250 Mio** ; performances UI/démarrage mesurées dans les scénarios réels, pas inférées du simple parse JSON.
4. **Runtime Windows x64/CPython 3.13** : toute dépendance chargée dans le produit exige wheel Windows compatible, version + SHA-256 ajoutés au verrou `requirements-pyside.txt`, revue de licence, coût de RAM et preuve de non-régression. Préférer les outils de dev/CI hors runtime et l'invocation ponctuelle.
5. **UI PySide6 / QtWebEngine** : ne pas charger les outils Qt pendant le démarrage ; ne pas charger WebEngine avant équipement ; tester un vrai bureau Windows séparément de `offscreen`.
6. **Données Dofus** : aucune génération automatique de coordonnées/prérequis, aucune suppression des anciens JSON/variants sans preuve des consommateurs + packaging ; protéger `character:<id_dofus>` et les stores utilisateur.
7. Toute modification structurelle : Graphify **du HEAD exact** avant édition ; sans artefact disponible ici, rester au cadrage et marquer les tests NON EXÉCUTÉS.
8. Garder la PR **Draft** tant que le développement, la revue commit-par-commit, les tests et les vérifications réelles ne sont pas terminés. Ne pas déclencher FULL/bench/CI lourde à chaque commit.

## Inventaire 23 projets GitHub : placement exact et décision

**Statut commun : candidats à qualifier, pas installés par ce document.** Licence indiquée via métadonnées GitHub lorsque déterminable ; **à revalider par version/artifact avant livraison**.

| ID | GitHub | Décision conseillée | Raccordement dans les propriétaires EXISTANTS | Critère mesurable / anti-doublon |
|---|---|---|---|---|
| ATOSS-01 | [pytest-qt](https://github.com/pytest-dev/pytest-qt) | P0 ADAPT dev | `tests/test_atlas_doctor_ui_qt.py`, `tests/test_doctor_ui_qt.py`, `tests/test_qt_async_non_accumulation.py` | Signaux, arrêt, navigation sous Windows ; si tests Qt existants suffisent, ne pas ajouter |
| ATOSS-02 | [Hypothesis](https://github.com/HypothesisWorks/hypothesis) | P0 EVAL dev | `tests/test_json_store.py`, `tests/test_achievement_progress_json_store.py`, `tests/test_ci_delivery_guard.py` | Fuzz transactions de progrès : write atomique, migrations, crash, double-écriture, rollback ; seed enregistrée |
| ATOSS-03 | [pywinauto](https://github.com/pywinauto/pywinauto) | P0 EVAL Windows | `scripts/windows/atlas_setup_entry.py`, `app/distribution/setup.py`, `app/distribution/launcher_ui.py`, tests Windows existants | Vrai écran installation/upgrade/annulation/75 % bloqué/choix dossier ; pas de simulation CI = PASS natif |
| ATOSS-04 | [py-spy](https://github.com/benfred/py-spy) | P0 **REUSE_EXISTING** | `tools.atlas_doctor perf --deep --py-spy` via `tools/atlas_doctor_lib/exhaustive_performance.py` et [Doctor Performance Lab](../doctor_performance_lab.md) | Vérifier son déclenchement et son coût sur Windows ; ne pas ajouter un second profiler permanent |
| ATOSS-05 | [ast-grep](https://github.com/ast-grep/ast-grep) | P1 EVAL dev | `tools/agent.py` / `tools/agent_graph.py` en aide *read-only* ; Graphify source d'impact structurel | Meilleur rappel des consommateurs par cas Atlas, faux positifs et coût avant adoption |
| ATOSS-06 | [zizmor](https://github.com/zizmorcore/zizmor) | P0 EVAL sécurité | `.github/workflows/`, politique `tools/ci_scope_gate.py` / `tools/ci_domain_certification.py` | Détecter une fixture workflow vulnérable sans affaiblir la CI |
| ATOSS-07 | [Gitleaks](https://github.com/gitleaks/gitleaks) | P0 EVAL sécurité | `.githooks/`, jobs de contrôle sécurité existants ; jamais dans runtime | Vérifier secret fictif et absence de secret en rapport |
| ATOSS-08 | [Ruff](https://github.com/astral-sh/ruff) | P1 EVAL dev | `tools/ci_dev_tests.py` et tests ciblés ; n'introduire que règles réellement utiles | Aucun formatage global ni faux passe dans l'Integrity Gate |
| ATOSS-09 | [OSV-Scanner](https://github.com/google/osv-scanner) | P1 CHOOSE_ONE | Dépendances dev/Windows, contrôle existant ; alternative à `pip-audit` | Mesurer couverture et dates de données, ne garder qu'un scanner principal |
| ATOSS-10 | [jsonschema](https://github.com/python-jsonschema/jsonschema) | P1 EVAL données | `tools/atlas_json_inventory.py`, `tools/atlas_json_raw.py`, `tests/test_critical_json_schema.py` | Nouveaux liens/IDs malformés détectés ; ne remplace pas les règles métier ni le scan exhaustif Doctor |
| ATOSS-11 | [orjson](https://github.com/ijl/orjson) | P1 BENCH_ONLY | `tools/atlas_json_benchmark.py`, `app/quest_catalog.py`, providers ; garder le parseur standard tant que gain non prouvé | Comparer vitesse, type, Unicode, NaN, ordre clés, grosse RAM et sortie sérialisée |
| ATOSS-12 | [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) | P1 BENCH_ONLY | Recherche Encyclopédie / `app/quest_source_index.py`, sans toucher l'index persistant | Mesurer requêtes rapides, exactitude, CPU, RAM, faux positifs et cache |
| ATOSS-13 | [python-zstandard](https://github.com/indygreg/python-zstandard) | P2 EVAL distribution | `app/distribution/archive_parts.py`, `app/distribution/data_pack_store.py`, `app/distribution/data_pack_verify.py` | Taille/delta/décompression + vérification hash, compatibilité launcher V2 #285, rollback |
| ATOSS-14 | [PyInstaller](https://github.com/pyinstaller/pyinstaller) | P1 **ASSESS_EXISTING** | `scripts/windows/package_release.py`, `scripts/windows/certify_public_install.py`, workflow Windows | Vérifier packager déjà utilisé avant d'en ajouter un autre ; test EXE Windows complet |
| ATOSS-15 | [Nuitka](https://github.com/Nuitka/Nuitka) | P2 REFERENCE_ONLY | Aucun remplacement packaging sans métriques et revue licence AGPL, dépendances plugins Qt | Benchmark isolé avant toute migration ; risques de distribution Windows et Qt |
| ATOSS-16 | [VizTracer](https://github.com/gaogaotiantian/viztracer) | P2 REUSE_PLAN | `tools.atlas_doctor perf --deep`, [Doctor Performance Lab](../doctor_performance_lab.md) | Trace sur parcours bloquant, surcharge quantifiée, OFF par défaut |
| ATOSS-17 | [Scalene](https://github.com/plasma-umass/scalene) | P2 REUSE_PLAN | `tools.atlas_doctor perf --deep`, [Doctor Performance Lab](../doctor_performance_lab.md) | Choisir une investigation ciblée selon support Windows, CPU/alloc, coût ; pas d'instrumentation partout |
| ATOSS-18 | [pyinstrument](https://github.com/joerick/pyinstrument) | P2 EVAL profilage | `tools/atlas_doctor_lib/perf.py`, `tools/benchmark_atlas_exhaustive.py` | Un seul moteur de campagnes Doctor ; profils séparés des percentiles normaux |
| ATOSS-19 | [Semgrep](https://github.com/semgrep/semgrep) | P1 EVAL dev | `tools/agent.py`, conseil de règles statiques et `tools/ci_dev_tests.py` | Analyse ciblée comparée à AST Doctor/Graphify ; aucun nouveau veto sur heuristique non validée |
| ATOSS-20 | [pip-audit](https://github.com/pypa/pip-audit) | P1 CHOOSE_ONE | `requirements-pyside.txt`, dépendances build, CI sécurité ; alternative à OSV | Versions/hashes exacts, qualité des résultats et prise en charge offline explicite |
| ATOSS-21 | [MCP Inspector](https://github.com/modelcontextprotocol/inspector) | P2 REFERENCE_ONLY | Agent tooling/documentation, test de MCP externe hors application | Aucun serveur MCP introduit dans la fenêtre Atlas, pas de nouveau service permanent |
| ATOSS-22 | [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) | P2 REFERENCE_ONLY | Tooling développeur piloté par agent et Doctor, **pas de plugin framework runtime** | Adopter seulement si une capacité existante ne peut pas être reliée sans SDK |
| ATOSS-23 | [Pydantic](https://github.com/pydantic/pydantic) | P2 DEFER | `tools/guide_action_contract.py`, `tools/atlas_json_inventory.py` | Déjà beaucoup de contrats natifs ; conserver si pas de bénéfice mesuré |

**Ne jamais confondre :** GitHub compatible ≠ wheel Python 3.13/Windows disponible ; licence du dépôt ≠ redistribution validée ; documenté ≠ installé ; installé ≠ branché ; tests existants ≠ exécutés.

## Matrice d'intégration réelle par domaine

| Domaine | Point d'entrée canonique | Sélection possible (sous conditions) | Refus et dépendances |
|---|---|---|---|
| **Doctor/diagnostic** | `tools/atlas_doctor.py` + `tools/atlas_doctor_lib/` | Profiles ponctuels py-spy/VizTracer/Scalene/pyinstrument selon phénomène mesuré | Pas de nouveau Doctor, pas de profileurs au démarrage ; chevauchement #303/#310 |
| **Graphify / code** | `tools/graphify.py`, `tools/agent.py`, `tools/tool_catalog.py` | ast-grep / Semgrep read-only si consommateur concret et tests | Graphify obligatoire avant refactor structurel ; pas de deuxième graphe |
| **Qt UI** | `app/ui/theme.py`, `app/ui/components.py`, tests UI | pytest-qt et pywinauto sur bancs séparés | Ne pas déplacer le travail lourd au thread UI ; chevauchement #304/#306 |
| **JSON / progression** | `app/modules/encyclopedia/providers/`, `app/storage.py`, `tools/atlas_json_*.py` | Hypothesis/jsonschema ; orjson seulement après bench comparatif | Persistance atomique, identités, SHA de manifestes ; chevauchement #303/#310 |
| **Recherche** | `app/quest_source_index.py`, `app/quest_catalog.py` | RapidFuzz si son index prouve un gain | Pas de scan complet à chaque frappe ; #303 reste propriétaire |
| **Launcher / archive** | `app/distribution/`, `scripts/windows/package_release.py` | zstandard/PyInstaller si support et mesures favorables | Un seul launcher V2 et format manifest ; PR #285 propriétaire |
| **Sécurité / QA** | `tools/ci_dev_tests.py`, `tools/ci_scope_gate.py`, workflows existants | zizmor, Gitleaks, Ruff, scanner dépendances unique | Pas de nouvelles FULL, ni checks trompeurs, ni auto-installation à chaque CI |
| **Plugins et IA** | `tools/tool_catalog.py`, `tools/atlas_doctor.py`, `tools/skills/` | Assistant externe par capabilities si nécessaire | Pas de second registry/SDK MCP runtime, zéro mutation sans autorisation |

### Lots de développement et ordre

- **AT-L01 Préflight (P0)** : baseline du HEAD dans Doctor, catalogue dérivé des vraies capacités, versions/licences et consumers, conflits de branches. Créer vraie carte `outil → owner → test → proof` alimentée par l'existant. Statuts distincts `ABSENT / AVAILABLE / CONNECTED / VERIFIED / BLOCKED` ; `AVAILABLE` ne doit jamais impliquer `VERIFIED`.
- **AT-L02 Qt/Windows (P0)** : pytest-qt et pywinauto branchés à leurs suites canoniques ; tests desktop natifs et tests Qt offscreen séparés, trajectoire #285 (launcher) et #304 (UI).
- **AT-L03 Doctor perf (P0)** : vérifier le py-spy existant, activer uniquement après installation explicite, profilage sur parcours lent et stockage dans `artifacts/`. VizTracer/Scalene/pyinstrument *mutuellement évalués*, non empilés ; benchmark canonique inchangé.
- **AT-L04 JSON (P0/P1)** : Hypothesis/jsonschema sur progression et liens ; comparer orjson via `tools/atlas_json_benchmark.py`, ne pas modifier JSON contenu/format sans bilan de parité. Travail coordonné #303/#310, pas concurrent.
- **AT-L05 Sécurité (P1)** : Ruff et zizmor en advisory, gitleaks sur secrets fictifs, comparaison OSV/pip-audit puis choix unique ; rapport exact-SHA et tests de faux positifs.
- **AT-L06 Recherche/packaging (P1)** : bench RapidFuzz sur recherche et zstd sur packages, pas de changement production si gain non mesuré. Projet launcher #285 est propriétaire du delta.
- **AT-L07 Code intelligence (P1)** : ast-grep/Semgrep adaptés aux besoins réels et aux traces Graphify ; invocation de l'outil via commandes autorisées par Doctor, aucun autre orchestrateur.
- **AT-L08 Comparatifs/références (P2)** : Nuitka, MCP Inspector/SDK, Pydantic ; décisions KEEP_EXISTING/DEFER/REJECT documentées avec justification, sans installation par défaut.

## Critères d'acceptation (AT-AC01 à AT-AC15)

- [ ] AT-AC01 : les 23 IDs ATOSS-01..23 sont complets, sans doublon, avec propriétaire existant et lien officiel ;
- [ ] AT-AC02 : chaque candidat est classé `EXISTING / MISSING / PARTIAL / REFERENCE / REJECT` par inspection du code réel et tests ;
- [ ] AT-AC03 : toutes les 8 exigences source issue #313 sont couvertes sans réécrire ni réduire leur intention ;
- [ ] AT-AC04 : Graphify exact-SHA + recherche des consommateurs avant les changements structurels ;
- [ ] AT-AC05 : tool_catalog et Doctor ne déclarent CONNECTED/VERIFIED qu'après appel réussi observé ; statuts explicites si absent ;
- [ ] AT-AC06 : 23 licences, versions, provenance et compatibility Python 3.13 Windows validées *avant* ajout runtime ;
- [ ] AT-AC07 : les gains RAM/latence sont prouvés à machines/scénarios identiques, incluant coût de l'instrumentation ;
- [ ] AT-AC08 : installation/upgrade/rollback/exe/launcher testés sur Windows réel sans simulation de PASS ;
- [ ] AT-AC09 : tests de mutation/propriété prouvent progression utilisateurs et corruption/roundtrip/atomicité ;
- [ ] AT-AC10 : contrôles sécurité et CI restent non destructifs, sans nouveaux gates inutiles, et exécutés avant annonce de gain ;
- [ ] AT-AC11 : aucune deuxième implémentation Doctor/bench/Graphify/catalogue/recherche/launcher ;
- [ ] AT-AC12 : PR #285/#303/#304/#306/#310 et branches associées sans conflit de fichier non arbitré ;
- [ ] AT-AC13 : tests au HEAD et verdict de Doctor/CI ne sont jamais réduits aux noms de jobs ou à `SKIPPED` ;
- [ ] AT-AC14 : audit de **chaque commit** puis audit global du diff intégré avant passage Ready ;
- [ ] AT-AC15 : un outil insuffisant est explicitement REJECT/DEFER et ne gonfle pas le binaire.

## Audit croisé initial — DOF ATLAS vs Holding PR #60

- **Convergences** : Hypothesis, pytest-qt, pywinauto, py-spy, ast-grep, Semgrep, Ruff, zizmor, Gitleaks, OSV/pip-audit, MCP. *Partage des retours d'expérience*, pas de dépendance runtime entre dépôts.
- **Différence d'owner** : Holding orchestre les agents, Atlas Doctor contrôle la validation du dépôt/application. Leurs catalogues, contrôles et autorisations sont spécifiques au repo. Aucun import croisé à créer.
- **Recouvrements vérifiés ATLAS** : `tools/atlas_doctor.py`, `tools/tool_catalog.py`, `tools/atlas_json_benchmark.py`, `tools/benchmark_atlas_exhaustive.py`, `docs/doctor_performance_lab.md`, `app/distribution/`, `tests/test_tool_catalog.py`.
- **Conflits confirmés potentiels** : #303 modifie `tools/atlas_doctor.py`, `tools/tool_catalog.py`, benchmarks et JSON ; #310 se base sur #303 ; #285 détient le launcher V2 ; #304 UI ; #306 guides. N'apporter aucun changement de ces fichiers depuis une branche parallèle sans synchroniser et rebaser le propriétaire.
- **Écarts de preuve** : l'audit GitHub et la présence des fichiers ne prouvent ni les gains mémoire, ni l'installation Windows, ni le comportement d'un outil absent. **Doctor, Graphify et bench NON_RUN** depuis ce travail distant.

### Audit initial PR Holding #60

PR source : [Holding #60](https://github.com/r9327/Atlas-Holding/pull/60), dossier [21 candidats](https://github.com/r9327/Atlas-Holding/blob/docs/github-open-source-integration-20261031/docs/roadmap/GITHUB_OPEN_SOURCE_INTEGRATION_2026-10-31.md).

- **Commit 1** : inventaire documentaire, sans modifications runtime ni preuve que les 21 outils fonctionnent. Vérifier la conformité des URLs/versions/licences avant intégration.
- **Commit 2** : lien README vers le catalogue ; pas de nouveau chemin d'exécution.
- **Global** : aucune CI/bench/Doctor exécutée pour adoption, aucune licence prouvée version par version ; manque un véritable passage `AVAILABLE→CONNECTED→VERIFIED` avec invocation/traces et test de non-régression. À traiter dans des PR de code rattachées aux propriétaires existants.
- **Verdict** : **IMPROVEMENTS ADVISED** pour le cadrage, **CHANGES REQUIRED** avant toute annonce d'intégration opérationnelle, **NOT_CERTIFIED**.

## Limites et statut réel

Cette première modification est **documentaire**. Les 23 projets ont été comparés aux composants et PR visibles du dépôt ; **aucun des 23 n'a été installé, activé, ni mesuré dans cette PR**. Les lots AT-L01..08 restent à développer. Les tests Docker, Qt, Windows, Doctor perf, GitHub CI, Graphify et le FULL final ne sont **pas exécutés ici**. Préserver le Draft et ne pas présenter l'issue #313 comme DONE.

Ne pas lancer une FULL avant que les modifications de code de la PR soient réellement terminées, conformément au contrat CI.