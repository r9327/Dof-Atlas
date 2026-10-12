# Lot 3 — RAM, latence, lifecycle et architecture prouvée

Statut : **EXÉCUTION ANTICIPÉE — INSTRUMENTATION PARTIELLE POUSSÉE — NON CERTIFIÉ**.

## Journal d'exécution indépendant (2026-10-12)

- **L3.1 partiel — CODE POUSSÉ** : le benchmark existant capture maintenant `after_guide_home_stabilized` après 1,50 s de stabilisation, avec trois métriques explicatives : `guide_retained_tree_delta_stabilized_mb`, `guide_incremental_retained_tree_delta_mb` et `guide_home_stabilization_delta_mb`. Les phases du sampler et l'échantillonnage process-tree existants sont conservés.
- Commits d'implémentation : [85e81cad](https://github.com/r9327/Dof-Atlas/commit/85e81cad90eb1c2a16b97f40ae78113de5efee12) puis [320637e2](https://github.com/r9327/Dof-Atlas/commit/320637e2fe8727c86878491e034468f51d21c00b). Fichiers : `tools/benchmark_phase8_memory.py`, `tests/test_phase8_memory_benchmark_contract.py`.
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
