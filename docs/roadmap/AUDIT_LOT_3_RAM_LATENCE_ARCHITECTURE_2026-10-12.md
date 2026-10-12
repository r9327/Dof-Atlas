# Lot 3 — RAM, latence, lifecycle et architecture prouvée

## L3.3 — Reprise priorité latence Succès (2026-10-12)

- **Décision utilisateur** : reporter l'investigation des faibles écarts RAM, **sans supprimer ni assouplir les gates**. La mémoire du dernier candidat reste **FAIL** ([run 38294628576](https://github.com/r9327/Dof-Atlas/actions/runs/38294628576)) : 100,11 Mo après 2e Guide→Home pour budget strict <100, et pic process-tree 220,63 Mo pour budget ≤220. Ce FAIL ne devient pas PASS par décision de priorité.
- **Comparatif propre Windows** : [Phase 8 Preload #38294628558](https://github.com/r9327/Dof-Atlas/actions/runs/38294628558) **PASS sur les contrôles**, mais le premier détail Succès réel **42 010,29 ms (main) → 43 258,54 ms (candidat)**, soit +1 248,25 ms et non un gain. Ceci invalide toute prétention que les exports lazy ont accéléré ce scénario.
- **Cause source prouvée** : `MemoryBoundAchievementProvider.get_detail_by_id()` exécute `subprocess.run(--dump-detail)` de façon synchrone à la navigation. L'ancienne entrée du processus `_dump_default_detail()` reconstruisait **toutes** les sources via `_load_in_process()`, y compris sélection préalable des text IDs. En revanche, le générateur compact `_build_compact_cache()` dispose déjà de `_load_disposable_worker_fast()`, qui réutilise les index d'offsets source et réalise une seule passe.
- **Correctif borné** : [78cc392f](https://github.com/r9327/Dof-Atlas/commit/78cc392f1d91a8667cd31630edf275ae2ff35cf6) remplace uniquement l'initialisation du sous-processus détail par le chargeur rapide **déjà exploité dans le dépôt** ; `prepare_detail_sources()`, `_get_detail_in_process()`, JSON complet et signal d'échec restent inchangés. Le processus est toujours éphémère, sans épingler les sources en RAM permanente ni déplacer un chargement vers le preload.
- **Validation développée, non encore exécutée** : [278992a3](https://github.com/r9327/Dof-Atlas/commit/278992a3c5ad9ab2f30745ad5ae8e8e1571fc596) ajoute deux vrais `unittest.TestCase` : contrat JSON complet (id, nom, objectifs, récompenses, source rapide invoquée, source lente non invoquée) et échec `None → exit 2`. Les tests réels de données et la certification restent à vérifier dans les runners.
- **Observabilité comparative** : [4e596825](https://github.com/r9327/Dof-Atlas/commit/4e596825ba7b98e3b597cf74c2307e652d984f61) conserve `deep_achievement_detail_ms` et ajoute `achievement_detail_phases_ms` (tab_ready, catalogue_lookup, navigation_call, post_navigation_wait). [Contrat 412314d5](https://github.com/r9327/Dof-Atlas/commit/412314d59d635537ee10330db602af08831a83e8) vérifie que le chronomètre total englobe toujours le détail réellement ouvert.
- **Critère de sortie** : mesurer à nouveau sur runner Windows identique, deux caches froids indépendants, même ID Succès, puis comparer surtout `deep_achievement_detail_ms` et la nouvelle phase `navigation_call` ; aucune preuve de gain n'est avancée avant ce résultat. Conserver Graphify/Doctor ciblés et la certification finale d'après exigences projet.


Statut : **LOT 1 ET LOT 2 FUSIONNÉS — L3.1 INSTRUMENTATION ÉTENDUE — NON CERTIFIÉ**.

## Changement applicatif et verrouillage final de la mesure

- **L3 optimisation bornée :** les exports différés de la [PR #134](https://github.com/r9327/Dof-Atlas/pull/134) ont été repris dans cette branche, sans les workflows comparatifs historiques ni leurs anciens fichiers d'index. Les **42 exports `__all__` ont été comparés valeur par valeur et ordre par ordre** à la façade précédente ; ils correspondent exactement. **19 sous-modules Qt** sont résolus seulement à l'usage via `__getattr__`. Le test réel `tests/test_encyclopedia_widgets_lazy_exports.py` est intégré. #134 reste non fusionnée pendant la validation, puis doit être clôturée comme redondante **uniquement après** intégration prouvée de la #151.
- **Graphify préflight exact-SHA** : [38293752152](https://github.com/r9327/Dof-Atlas/actions/runs/38293752152) `PASS` sur `bd3aeba7`, 12 482 nœuds, 36 131 liens, 886 fichiers Python, zéro fichier manquant ; le point d'entrée `widgets/__init__.py` a bien **19 liens `re_exports`** et **34 imports** AST. Aucune suppression de fichier ni de classe. Une cartographie finale post-changement doit confirmer les dépendances sur le SHA candidat livré.
- **Renforcement du gate mémoire** : `after_guide_home_stabilized` et les six retours Home des deux cycles Quêtes/Succès/Guide sont désormais **obligatoires et soumis au même seuil strict <100 Mo**, sans modifier le pic hard de **220 Mo**. Tests `unittest` des sept nouveaux budgets présents. Ce correctif empêche de qualifier `PASS` un processus qui monte à 104 Mo après plusieurs navigations.
- **Interprétation Qt recalée** : [run 38293261068](https://github.com/r9327/Dof-Atlas/actions/runs/38293261068) prouve **145 widgets stables après chaque retour Home** une fois `DeferredDelete` explicitement traité dans la pompe synthétique, tandis que les RSS du deuxième cycle restent 100,86 Mo et le pic 220,29 Mo : **FAIL réel des budgets** sur ce commit, non corrigé par le seul test. La correction applicative lazy doit être mesurée avant de conclure.
- **Preload équitable** : deux passages depuis caches Atlas effacés, sur le même runner Windows ; les anciens chiffres de gains sur code identique (caches froids puis chauds) restent notés **INVALID_COMPARISON**, et ne peuvent être utilisés pour prétendre que le lot 3 a accéléré Succès.
- **Aucun résultat final anticipé** : les nouveaux tests de mémoire, la comparaison preload froide, les tests widgets et la FULL ne valent `PASS` que lorsque leurs workflows ont réellement réussi sur le SHA exact final.

## Analyse des preuves RAM/preload et correction de la mesure (2026-10-12)

- [Mémoire #38291681600](https://github.com/r9327/Dof-Atlas/actions/runs/38291681600) sur `25466e82` **FAIL** : pic process-tree **223,64 Mo** (limite inchangée 220), phase `preload` ; **149,13 Mo** des processus de préchauffage, dont trois processus recensés. `after_guide_home_stabilized` = 98,31 Mo ; `after_equipment_home_stabilized` = 98,35 Mo ; retour Guide 2e cycle = 104,55 Mo avec 446 widgets Qt. Aucune anomalie de threads Python (3 stables).
- [Mémoire #38292722508](https://github.com/r9327/Dof-Atlas/actions/runs/38292722508) sur `59744a58` **PASS mais marge préchauffage minime** : pic **219,80 Mo** ; warmup 145,26 Mo dont worker Python 122,30 Mo, orchestrateur 16,16 Mo, conhost 6,80 Mo. Après Équipement→Home : 98,17 Mo ; retours Guide cycles 1/2 : 102,62 / 104,47 Mo ; widgets Qt 274→360→446, dont 9 objets `EncyclopediaPage` recensés après le deuxième cycle. Une observation directe sous pompe Qt synthétique ne constitue pas encore une fuite en session utilisateur.
- **Cause de biais Qt vérifiée via documentation officielle Qt6** : `QCoreApplication.processEvents()` en boucle locale hors `QApplication.exec()` ne traite **pas automatiquement** les `DeferredDelete` de `deleteLater()`. Le benchmark utilise précisément ce mode. Correctif [2970c316](https://github.com/r9327/Dof-Atlas/commit/2970c3161946000e97a04b4d60bfac4d6f96dfd1) : `QApplication.sendPostedEvents(None, QEvent.DeferredDelete)` **avant** chaque capture RSS et du recensement Qt, sans changer la gestion production ; [test associé](https://github.com/r9327/Dof-Atlas/commit/d6da5a485f8cab2a86c4909a6aac2b89a04d6190). L'écart de widgets doit être **remesuré** pour distinguer artefact de test et rétention réelle. Aucun cache, budget ou test supprimé.
- [Preload #38291681485](https://github.com/r9327/Dof-Atlas/actions/runs/38291681485) a rendu `PASS` mais était **comparativement invalide** : il exécutait `main` avec caches froids, puis candidat avec les caches générés par le premier passage, bien que le code applicatif soit identique. Résultat apparent premier détail Succès 63,80 s → 8,26 s : **ne pas l'attribuer aux modifications du lot 3**. Correction `59744a58` de `.github/workflows/phase8-preload-benchmark.yml` : effacer les caches Atlas générés **avant chacun des deux runs**, contrôle `unittest` dédié.
- L'optimisation du préchauffage (worker 122,30 Mo au pic) reste `UNVERIFIED` : n'autoriser un changement d'architecture que si un comparatif reproductible confirme la marge insuffisante ; le 219,80 Mo constitue un `PASS` de seuil sur une exécution, **pas** une garantie en longue durée.

## État de livraison et protocole exact-SHA

- **Code livré dans #151 :** checkpoints RAM Guide stabilisée (maintien des budgets historiques), compteurs de widgets Qt et threads Python, **deux cycles réels** Quêtes → Home / Succès → Home / Guide détaillé → Home après Équipement, delta RSS de rétention et tests `unittest` qui exigent cette instrumentation. Le contrôle de chargement Guide attend maintenant `_runtime_ready` avant de compter la fiche comme affichée.
- **Validations du précédent HEAD `7a47643a` :** AI Context, Doctor FAST, Graphify Focused et Public PR CI `PASS` ; mémoire/preload/phase `SKIPPED`, donc **NOT_RUN**, pas `PASS`. Les vérifications du SHA final sont indépendantes.
- **Graphify complet du `main` certifié** : run [38286442745](https://github.com/r9327/Dof-Atlas/actions/runs/38286442745), exact SHA `617a6975` ; 12 475 nœuds, 36 120 liens, 886 fichiers Python tracés, 0 fichier Python suivi manquant, 0 inversion runtime→tools déclarée. Graphe architectural de référence **non exact-SHA pour #151**, utilisable pour investigation seulement, **pas** comme preuve de suppression de code.
- **Optimisation existante #134** : exports lazy de 42 symboles, 19 sous-modules Qt différés. Les benchmarks anciens du candidat sont verts mais sa [Phase Certification #38088747588](https://github.com/r9327/Dof-Atlas/actions/runs/38088747588) était `FAIL` ; **aucun transfert/fusion dans #151** avant certification compatible du code, et aucun gain RAM sur le SHA actuel n'est allégué. #134 conserve son propre propriétaire.
- **Performance Succès** : le chemin canonique `app/modules/encyclopedia/tools/benchmark_guides_performance.py::first_achievement_detail` expose déjà `first_achievement_detail_ms` et `first_achievement_detail_max_ui_block_ms`. Le benchmark `tools/benchmark_phase8_preload.py::measure_deep_first_content` chronomètre aussi `achievement_detail_ms` dans une navigation réelle. Réutiliser ces outils pour le comparatif Windows avant/après.
- **Mesures restantes avant statut CERTIFIED** : résultat Phase 8 RAM, Phase 8 Preload, preuve d'accès Succès froid/chaud, Doctor Windows UI/lifecycle et Phase Certification FULL sur **l'exact même HEAD final**. Des résultats `skipped`, `not_run` ou historiques ne satisfont pas le contrat. Ne relever aucun budget pour accélérer la fusion.

## Reprise sur main certifié (2026-10-12)

- Lot 1 #152 fusionné, Lot 2 #150 fusionné et certifié : base canonique `617a69752805c5ed047105132a189e319d0db800`. La PR #151 a été mise à jour par merge conservateur [390c7539](https://github.com/r9327/Dof-Atlas/commit/390c7539f438917c5f2ec2e1df6924b7395167fd), sans écrasement ni suppression des précédents travaux ; `main...lot3` était alors uniquement en avance de 7 commits, 0 retard.
- L'index AI Context a été régénéré par le même algorithme de fingerprints top-level que `tools.ai_context` (comparaison **octet pour octet** avec le producteur sur l'arbre main précédent), suite à l'échec vrai `STALE/MISSING` du run [38287451384](https://github.com/r9327/Dof-Atlas/actions/runs/38287451384). Correction [f23ab66](https://github.com/r9327/Dof-Atlas/commit/f23ab66be2e49c6b2e962661c0b308dcefc8ab5b) ; [AI Context CI 38287677212](https://github.com/r9327/Dof-Atlas/actions/runs/38287677212) PASS, Doctor FAST et Graphify ciblé PASS sur ce même SHA.
- Instrumentation additionnelle **L3.1/L3.2** : `python_threads_alive` et `qt_widgets_alive` sur les checkpoints mesurés, **après** la capture RSS (pour éviter la perturbation de l'échantillonnage). Commits [17993adc](https://github.com/r9327/Dof-Atlas/commit/17993adc8a299d32e3e55417cc4f1d1b05ef3da6) et [79890f7c](https://github.com/r9327/Dof-Atlas/commit/79890f7c522e505e563cde1616ce647b81eb9e9f), avec test `unittest` sur l'ordre de capture. Ces compteurs sont des indices de rétention, **pas une preuve de fuite**.
- **PR #134 observée, non absorbée** : mesure Windows publiée sur SHA antérieur `9a9348b9` : pic process-tree 219,57 Mo (marge 0,43 Mo sous budget 220 Mo), retour Home Guide 94,86 Mo ; cold import package de 245,47 à 4,55 ms dans un essai comparatif. Ces résultats ne décrivent pas le SHA du lot 3 et doivent être revalidés après intégration ; conserver le propriétaire #134 pour éviter une deuxième implémentation des mêmes exports.
- **Restant** : RUN Windows RAM/preload exact-SHA, mesure à froid du détail Succès, cycles répétés Qt et comparaison sur même environnement ; revue Graphify exact-SHA avant tout refactor structurel. `Phase 8 Memory`, `Phase 8 Preload` et `Phase Certification` SKIPPED sur les runs de développement ne prouvent aucun PASS. Aucun gain produit prétendu à ce stade.


## Journal d'exécution indépendant (2026-10-12)

- **L3.1 partiel — CODE POUSSÉ** : le benchmark existant capture maintenant `after_guide_home_stabilized` après 1,50 s de stabilisation, avec trois métriques explicatives : `guide_retained_tree_delta_stabilized_mb`, `guide_incremental_retained_tree_delta_mb` et `guide_home_stabilization_delta_mb`. Les phases du sampler et l'échantillonnage process-tree existants sont conservés.
- Commits d'implémentation : [85e81cad](https://github.com/r9327/Dof-Atlas/commit/85e81cad90eb1c2a16b97f40ae78113de5efee12) puis [320637e2](https://github.com/r9327/Dof-Atlas/commit/320637e2fe8727c86878491e034468f51d21c00b), enfin [95b70aa4](https://github.com/r9327/Dof-Atlas/commit/95b70aa4ecbd6be886beca4b207fc58e4707761f) (contrat transformé en `unittest.TestCase` réellement découvrable). Fichiers : `tools/benchmark_phase8_memory.py`, `tests/test_phase8_memory_benchmark_contract.py`.
- **Rétrocompatibilité intentionnelle** : les métriques historiques et les seuils du workflow restent inchangés. Le nouvel échantillon n'est pas injecté dans la validation existante ; il sert à différencier coût transitoire et rétention réelle du Guide, avec une attribution incrémentale indépendante des Succès.
- **Preuve CI sur le commit de test 320637e2** : `Graphify Focused Architecture` PASS (run [38267633378](https://github.com/r9327/Dof-Atlas/actions/runs/38267633378)), `Doctor Adaptive Certification` PASS limité aux contrôles exécutés (run [38267633268](https://github.com/r9327/Dof-Atlas/actions/runs/38267633268)), `Scoped PR Feedback` PASS **mais scope FULL_REQUIRED / Windows scoped SKIPPED** (run [38267633380](https://github.com/r9327/Dof-Atlas/actions/runs/38267633380)). Cela ne constitue ni le test Windows de ce benchmark, ni une FULL, ni une certification Phase 8. Le statut `Public Pull Request CI` reste à contrôler.
- **L3.1 baseline / L3.2–L3.5 : NOT_RUN/UNVERIFIED**. Pas de Windows/PySide6 exécuté dans cette session ; aucun gain RAM ou latence revendiqué ; ne pas lancer la FULL ou les benchmarks lourds pendant ce micro-lot.
- **Succès** : `tools/benchmark_phase8_preload.py::measure_deep_first_content` mesure déjà un vrai détail `achievement_detail_ms`, et pas seulement la liste ; le reprendre pour une comparaison sur même environnement avant d'ajouter un deuxième instrument concurrent.
- **Coordination #134** : [PR #134](https://github.com/r9327/Dof-Atlas/pull/134) réalise déjà les exports différés de widgets. Aucun doublon ou cherry-pick anticipé ; réévaluer le diff et ses conflits avant intégration au lot 3, une fois les lots 1 et 2 stabilisés.

Prochaine preuve requise : tests ciblés du contrat benchmark sur runner compatible, puis baseline RAM/latence Windows identique avant/après sur SHA intégrés ; classement des hotspots seulement après résultats et Graphify de même SHA. **Ne pas cocher les critères de sortie du lot tant que ces preuves manquent.**
Base `f6deb4a4fc8828ab9fc9372adc8653842303a7e9`. Dépendances de clôture : Lots 1 et 2 stabilisés.
Doit utiliser Doctor/Graphify exact-SHA et les contrats `docs/PERFORMANCE_MEMORY_POLICY.md` et `PERFORMANCE_GUARDRAILS.md`.

## Baselines et seuils

- L'objectif produit est une empreinte RAM stabilisée proche de **100 Mo** ; cible de travail **<100 Mo après retour Home**, mesurer RSS *process-tree* séparément du process principal. Le budget preload **95 Mo** mentionné historiquement doit être vérifié contre la configuration du HEAD avant de le déclarer contractuel.
- Objectif de pic process-tree ancien **<=250 Mo**, cible d'optimisation **~220 Mo** ; ne jamais remplacer le budget officiel sans décision. La valeur historique ~219,52 Mo et les ~98 Mo après Guide n'autorisent aucune conclusion sur le SHA actuel.
- Une latence du premier détail Succès de **8,49 s** avait été mesurée sur un benchmark antérieur ; refaire les mesures avant correctif.
- **16 hotspots statiques** du rapport Doctor précédent, **331 candidats faiblement liés** et **11 communautés isolées avec code de production** sont des **pistes**, pas des bugs, fuites ou code mort confirmés. Les chiffres sont attachés à l'ancien SHA.

## Travail exécutable

### L3.1 — Caractériser l'état réel, sans démultiplier les benchs
- [ ] Vérifier le HEAD canonique et le profil Windows/Python 3.13 ; conserver version Qt, OS, paramètres et méthode de mesure.
- [ ] Une baseline contrôlée : démarrage, after_preload, Quêtes/Guide/Succès/Équipement/Craft actifs, retours Home stabilisés, cycles répétés, sortie et nettoyage ; collecter RSS principal, descendants Chromium, CPU repos, latences, nombre threads/QObjects, pics.
- [ ] Vérifier warmup séquencé et coût de chargement/retour des vues ; isoler caches lourds et empreinte après fermeture. Comparer sur **même environnement**.
- [ ] Conserver des traceurs `guide_active -> after_guide_home -> after_guide_home_stabilized` et points analogues pour chaque module ; différencier drift monotone et simple high-water sans fuite.

### L3.2 — Cycle de vie RAM Windows
- [ ] Auditer propriétaires réels des `QTimer`, `QThread`/threads, signaux, callbacks et lambdas capturant un widget, `deleteLater()`, workers Guide/Succès, caches d'image, provider lazy, WebEngine.
- [ ] Utiliser Doctor `resource_lifecycle`, `runtime_observation`, `runtime_benchmark`, `trace_regressions`, `integrated_investigation` ; aucun `PASS` ne peut être inféré d'une capture AST.
- [ ] Corriger seulement des accumulations reproduites, nettoyer les timers et workers sur désactivation, borner les caches et conserver les chemins chauds nécessaires. Tests ciblés de non-accumulation Windows.

### L3.3 — Latence UI et disponibilité
- [ ] Chronométrer 1er détail Succès à froid, suivants à chaud, Guide, quête, recherche, changement personnage, retour écran ; distinguer index IO, JSON parse, subprocess, thread UI, paint Qt et hydratation.
- [ ] Lire `app/modules/encyclopedia/providers/memory_bound_achievement_provider.py`, `app/modules/encyclopedia/views/{encyclopedia_page,guides_view}.py`, `app/quest_catalog.py`, les budgets runtime.
- [ ] Toute optimisation réduit réellement le temps de l'interaction, sans déplacer le coût de 8,49 s vers preload/démarrage ni violer le budget RAM ; conserver lazy by-id, caches bornés, échec explicite.
- [ ] Vérifier liste Quêtes virtuelle, recherche debounce, mutations incrémentales, garde lazy WebEngine et images.

### L3.4 — Graphify dynamique, hotspots et simplification ciblée
- [ ] Vérifier graph AST `graphify-out/graph.json` construit pour même HEAD, nombre de nœuds et liens ; pas d'utilisation de graphe stale pour supprimer/refactor.
- [ ] Compléter par traces **réellement collectées** sur scénarios : imports dynamiques, signaux Qt, callbacks, workers et points d'entrée externes, avec provenance, couverture, limites.
- [ ] Revoir hubs `guides_view.py`, `quest_catalog.py`, `encyclopedia_page.py`, `runtime_state.py` et autres fichiers signalés. Un nœud central n'est pas un goulot sans mesure.
- [ ] Tester les 331 candidats et 11 communautés comme point de départ uniquement ; confirmer liens et usages (y compris réflexions/imports indirects) avant classification. Ne pas tenter de fusionner 108 communautés par compteur.
- [ ] Consolider doublons uniquement s'ils portent la **même responsabilité démontrée** ; supprimer du code seulement après preuve positive d'absence d'usage, tests et simulation d'impact.
- [ ] Simuler refactor avec `tools/agent.py plan --structural`, consulter reverse-impact, Graphify avant/après ; ne pas déclencher un chantier transversal hors cause.

### L3.5 — Mesure après et certification
- [ ] Comparer RAM/CPU/latence/process-tree au scénario baseline **identique**, calculer écarts et marges.
- [ ] Exécuter tests ciblés par micro-lot, puis Phase 8 Memory/Preload exact-SHA, lifecycle tests, Doctor/Graphify et autres gates obligatoires.
- [ ] Aucune nouvelle perf "gagnée" sans tableau before/after avec mêmes conditions ; aucune régression Guide, progression, stockage ni startup.

## Tests et entrypoints potentiels

`tools/benchmark_phase8_memory.py`, `tools/benchmark_phase8_preload.py`, `tools/atlas_lifecycle_soak.py`, `tools/atlas_doctor.py`, `tests/test_atlas_window_runtime_cleanup.py`, `tests/test_qt_async_non_accumulation.py`, `tests/test_memory_policy_contract.py`, `tests/test_phase8_memory_benchmark_contract.py`, `tests/test_phase8_preload_benchmark_contract.py`, `tests/test_lazy_quests_page_performance.py` (vérifier existence avant invocation), `docs/PERFORMANCE_MEMORY_POLICY.md`.

## Définition de terminé

- [ ] Benchmark avant/après fiable sur même environnement ; budgets officiels RAM/preload/pic vérifiés et respectés, sans fuites monotones.
- [ ] Performance 1er accès/retours Home caractérisée et améliorée **si goulot prouvé**, sans coûts déplacés invisiblement.
- [ ] Graphify runtime : couverture, traces, limites et provenance ; 0 refactor justifié par simple heuristique.
- [ ] Contrats UI, lifecycle, startup, persistence et CI applicative/phase `PASS` sur exact-SHA.

## Hors périmètre

Pas de profilage FULL et refactor des moteurs de tests (Lot 4), pas de reprise générale du contenu du Guide (Lot 2), aucune mesure lourde répétée pendant développement.
