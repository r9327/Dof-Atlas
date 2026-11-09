# DOFUS ATLAS — Opti V3 : plan de travail contractuel
_Date : 2026-11-04 — source : issue #366 — état : cadrage uniquement, **aucune amélioration déclarée livrée**._

## Résultat attendu

Réduire le temps jusqu'au premier contenu réellement utilisable et les blocages Qt dans **tous les modules existants** ; conserver la RAM et les coûts CPU/IO bornés ; rendre les règles anti-régression **applicables aux prochaines modifications et fonctionnalités**, à travers les propriétaires de règles/Doctor/CI déjà présents. L'utilisateur demande une Opti V3 globale. La révision du 9 novembre ajoute une cible **18/20 minimum sur chacun des cinq axes**, avec des priorités d'exécution fondées sur l'audit ; aucun axe n'est exclu. L'implémentation est organisée en lots cohérents vérifiables, pas en grandes réécritures aveugles.

### Sources de vérité à lire avant chaque lot

- `AI_ENTRYPOINT.md`, `AGENTS.md`, `tools/AGENTS.md`, `ZERO_TRUST_RULES.md`, `DEVELOPMENT_GUARDRAILS.md`, `PERFORMANCE_GUARDRAILS.md`, `PHASE_CERTIFICATION.md`, `GRAPHIFY.md`, `docs/delivery/DELIVERY_GUARD.md`.
- `docs/performance/atlas-full-optimization-backlog-20261030.md` (36 `OPT-*`), `docs/performance/atlas-ram-inventory-v1.json` (50 `RAM-*`), `docs/performance/atlas-ram-audit-roadmap-20261030.md`, `docs/performance/atlas-lazy-loading-inventory-20261030.md`.
- `tools.tool_catalog`, `tools.atlas_doctor agent plan/check/validate`, `tools.atlas_doctor graph` et le profilage déjà propriétaire de Doctor. Graphify exact SHA est obligatoire pour modifications structurelles.
- Ne jamais appeler la seule présence d'une règle ou d'un test une preuve d'exécution sur le HEAD.

## Matrice exhaustive des 31 règles initiales

Chaque ligne porte l'exigence source `OPTV-001..031` du Delivery Guard. **L'audit courant doit être confirmé sur HEAD par sources/tests/Doctor ; les statuts suivants ne sont pas un verdict final ni une implémentation.** Les règles sans objet web doivent avoir une justification exacte et un éventuel équivalent desktop, sans fausses nouvelles dépendances.

| # | Règle auditée | Application ou qualification Windows | Zone indicative |
| --- | --- | --- | --- |
| 1 | Squelettes vs indicateurs d'attente | Qt : état de chargement utile, non bloquant ; éviter les placeholders artificiels | UI Guide/Succès |
| 2 | WebP/AVIF, redimensionnement | Assets locaux : décoder à la taille affichée et mesurer conversion sans perte Unity | ImageService/Unity |
| 3 | Appels API doublés | Cache local partagé + source de vérité unique ; éliminer relectures doublées | Providers, services |
| 4 | Debounce | Qt : minuterie bornée sur filtres lourds et résultats obsolètes ignorés | Quêtes/Succès/Crafts |
| 5 | Pagination serveur | Sans API : pagination locale / détails à la demande / liste modèle | SQLite/catalogues |
| 6 | CDN statique | Sans objet desktop offline ; ne pas rendre les images dépendantes du réseau | Assets/Release |
| 7 | File de jobs | Workers bornés et annulables ; aucun accès QWidget hors thread UI | Startup/preload |
| 8 | N+1 | Bulk SQL/index partagé ; comparer nb requêtes et données | QuestDetails/Guide |
| 9 | Brotli/gzip HTTP | Sans objet HTTP ; mesurer les formats de cache local zlib/SQLite | Guide route store |
| 10 | Redis | Sans objet ; cache local SQLite/LRU existant à dimensionner | Caches |
| 11 | Dépendances JS inutiles | Équivalent desktop : imports Python/Qt et dépendances runtime réellement inutiles | requirements/bootstrap |
| 12 | Timeouts API externes | Réseau/launcher : deadline, annulation, erreur diagnostiquée ; conserver offline | Launcher/net |
| 13 | IA streaming | Sans objet tant qu'aucune génération IA distante n'est active | Intégrations éventuelles |
| 14 | UI optimiste | Qt : mise à jour ciblée avec persistance atomique, rollback sûr si échec | Progression |
| 15 | Images hors écran | Lazy decode et cache LRU ; contrôle mémoire QPixmap/QImage visibles | Guide/Map/Unity |
| 16 | Parallélisme indépendant | Paralléliser seulement si temps gagné ET RSS sous budget | Warmup/workers |
| 17 | Index SQL | EXPLAIN sur requêtes chaudes et index sans sur-indexation | world_db/QuestDetails |
| 18 | OpenTelemetry backend | Sans objet backend ; Doctor instrumentation événement Qt/CPU/mémoire locale | Doctor |
| 19 | Serveur et base proche | Sans objet : SQLite embarqué | SQLite |
| 20 | SSR/SSG | Sans objet Qt natif ; réutiliser index précompilés locaux | Encyclopédie |
| 21 | Scripts tiers différés | Sans objet web ; équivalent : imports et initialisations optionnelles différés | Startup |
| 22 | JS split par page | Équivalent : imports Python et pages Qt lazy, pas de Chromium au bootstrap | Main/Modules |
| 23 | Listes virtualisées | Modèles Qt, matérialisation bornée, suppression du rendu des éléments cachés | Guide/Succès/Crafts |
| 24 | Colonnes SQL utiles | Mesurer SELECT * et remplacer précisément sans casser consommateurs | World DB |
| 25 | Pool de connexions | SQLite locale : durée et concurrence des handles ; pas de pool serveur ajouté d'office | SQLite |
| 26 | Re-renders inutiles | Comparer snapshots/signatures et invalider seulement les widgets affectés | UI/persistance |
| 27 | Cache-Control | Sans objet HTTP ; cache local signé, versionné, invalidation atomique | Caches |
| 28 | Load balancing | Sans objet application mono-PC ; surveiller la concurrence multi-processus | Runtime |
| 29 | WOFF2/2 graisses | Sans objet exigence web ; mesurer polices Qt locales/fallback et coût au démarrage | Unity Skin |
| 30 | Core Web Vitals | Équivalent : métriques réelles Windows, Doctor non intrusif, pas de télémétrie imposée | Doctor/Bench |
| 31 | Throttling mobile/3G | Équivalent : Windows faible CPU/disque/RAM/DPI, tests réseau limité seulement launcher | Tests Windows |

## Ajouts Opti V3 au-delà des 31 règles

1. **Premier écran réellement utilisable** : distinguer fenêtre peinte, action utilisable, cache prêt, premier détail entièrement visible ; profiler les premiers accès froids et les ouvertures suivantes.
2. **Événements Qt** : temps clic → paint, backlog boucle d'événements, freezes >250 ms, signal/slot, signal obsolète et navigation annulée ; pas de spinner qui bloque Retour.
3. **CPU, RAM et objets vivants** : composant/pid, Python vs Qt/C++, `QWidget`, `QImage`, `QPixmap`, workers, caches, timer, hooks ; éviter d'appeler fuite mémoire une seule hausse RSS.
4. **Caches versionnés** : taille maximale, signature d'entrée, invalidation ciblée et atomique, LRU, statistiques hit/miss et restauration après redémarrage ; ne pas reconstruire ce qui est encore valide.
5. **Sources Dofus volumineuses** : éviter de charger ou copier 69 Mio quêtes enrichies et manifestes images complets pour un seul détail ; inspecter SQLite/index offsets, batch N+1, `SELECT *`, recherche et tri.
6. **Isolation des travaux** : travail lourd hors UI, limites de concurrence, bornes de mémoire, annulation, remise en marche après échec et absence de fuite de références.
7. **Conception à long terme** : chaque nouveau module suit lazy data → détail demandé → images visibles, publication d'invalidation, rendu ciblé, caches partagés, modèles Qt adaptés aux grandes listes, et garde des ressources.
8. **QtWebEngine, assets et polices** : ne pas démarrer Chromium ni importer un lourd module facultatif trop tôt ; préserver Unity, les ressources locales et le comportement offline.
9. **Installation et mise à jour** : inclure dans les métriques de performance globales, mais laisser l'implémentation exclusivement dans la PR Launcher #285 ; aucune double implémentation dans Opti V3.
10. **Pratiques anti-régression** : tests représentatifs des vrais écrans, données utilisateur persistantes, 1/4/8 Atlas, fenêtres Dofus facultatives ; comparer les scénarios Windows sur même machine, même état de cache et même données.
11. **Dépendances et copies** : vérifier les imports concurrents, multiples providers, JSON redondants, doublons de calcul et matériaux inutilisés ; suppression uniquement après preuve Graphify des consommateurs et parité tests.
12. **Fichiers futurs** : analyse des fichiers modifiés dans les outils déjà canoniques (Doctor/Integrity/CI), règles adaptées à la nature du fichier ; métrique bloquante uniquement si reproductible et significative, sinon REVIEW motivé.

## Registre historique exhaustif

- Réconcilier **`OPT-P0-01..06`, `OPT-P1-07..14`, `OPT-P2-15..24`, `OPT-P3-25..36`** : 36 entrées, statut réévalué sur SHA exact. Ne pas considérer les mentions « plan » ni les commits de #303/#310 comme preuve de gains actuels.
- Réconcilier **`RAM-01..50`** depuis `docs/performance/atlas-ram-inventory-v1.json` : chaque entrée garde son owner, sa preuve et ses limites ; aucune suppression silencieuse.
- Associer à chaque ticket : `owner`, `ancien statut`, `preuve actuelle`, `coût`, `action ou motif sans objet`, `tests`, `benchmark A/B`, `commit` ; distinguer `VERIFIED`, `PARTIAL`, `BLOCKED`, `NOT_RUN`, `NOT_APPLICABLE`.
- Les 31 règles initiales, 36 anciens OPT et 50 pistes RAM **se recoupent** : les relier à une **même** action/régression si nécessaire, ne pas fabriquer 117 modules ou 117 tests inutiles.

## Contrat permanent pour le code à venir (OPTV-037/039)

**Implémentation prévue après l'audit, pas livrée avec ce cadrage.**

- Renforcer **`PERFORMANCE_GUARDRAILS.md`** comme propriétaire humain, puis l'owner machine existant dans Doctor/Integrity pour vérification conditionnelle des changements : performance vs coût, confiance et surface concernée.
- Sur nouveaux imports/pages : vérifier paresse et absence de gros préload hors besoin explicite ; sur nouveaux listings : modèle/virtualisation/batches ; nouveaux filtres : debounce si réellement coûteux ; nouveau SQL : index/débits N+1/colonnes ; nouvelle image : décodage à taille voulue/cache borné ; nouveau worker : lifecycle/annulation/Qt-safe ; nouveau cache : signature/invalidation/bornes.
- Des tests ciblés doivent **prouver** la régression évitée : fixtures synthétiques, accès paresseux, nombre d'appels SQL, limites de cache, réponse nouvelle génération, nombre de widgets, réutilisation et retour Home. Sur règles non applicables, un motif explicite, pas un faux FAIL.
- Ne créer **aucune** deuxième politique, nouvelle CI intégrale ou nouveau service permanent, si le contrat existant suffit. Tout changement de politique doit passer l'audit borné `AGENTS.md` et les tests de routage/CI concernés.

## Familles techniques conservées — détaillées dans la séquence du 9 novembre

**A. Baseline et traçabilité** — doctor/graph/QA exact SHA, état 31/36/50, baseline froide/chaude, synthèse des coûts et des chemins. Préserver les preuves et les budgets.

**B. Accès données + caches** — index/SQLite/JSON, requêtes N+1 et `SELECT *`, signatures, tailles, corruption sans masquer, parité persistance.

**C. UI + ressources** — Qt, virtualisation, rendu visible, annulation de résultats obsolètes, images, Unity, tailles, FPS native seulement en validation Windows.

**D. Démarrage + concurrence + mémoire** — cold/warm, préload utile, workers, teardown, mémoire par process, réouvertures, budget Guide/Home.

**E. Garde-fous du futur code** — canonique performance, Doctor/Integrity existants, tests contractuels ciblés, audit de cohérence des règles.

**F. Recette finale** — audit chaque commit et PR globale, 31/36/50 sans omission, Doctor ciblé/FAST/Graphify exact SHA et Windows natif, puis une certification finale sur HEAD Ready.

## Non-chevauchement avec les PR actives

- **#285** Launcher / installation différentielle : métriques et intégration uniquement, pas de code launcher concurrent.
- **#325**, fusionnée sur `main@ac656f6069e0820ddf90c320244ebfda06f63316`, et **#398**, ouverte : réutiliser les correctifs Organizer/Macro/Miroir et leurs preuves ; pas de seconde implémentation dans V3. Recette native #322.
- **#358** Doctor OSS : réutiliser les outils qualifiés ; s'appuyer sur le contrôle existant, pas redévelopper les adaptateurs.
- **#363** Guide Ganymède : aucune modification de contenu, ID, contrat de certification ou nouvelle route avant les règles de cette PR.
- **#365** Harmonisation UI : ne pas rebrancher le thème/sprites/onglets ; performances compatibles seulement.
- **#297** Doctor Performance Lab V3 : reprendre l'instrumentation propriétaire et compléter les scénarios sans doublon de benchmark.

## Mesures, validation et protection des données

- Cibles héritées : Home stabilisé **<100 Mio**, pic process-tree **≤250 Mio** et ouverture utilisable **≤10 s par module** comme objectif produit, pas preuve que ces seuils sont atteints. Suivi `p50/p95/p99`, temps de premier contenu complet, freezes Qt, CPU au repos, taille des caches et cycles de fermeture.
- Mesurer cold/chaud, 1/4/8 processus **Atlas** et comparaison mêmes données/machine ; le banc Qt offscreen n'est pas une recette GPU native.
- Garder les tests de progression, migrations, identités `character:<id>`, atomicité/rollback, intégrité des Guides et données utilisateur, compatibilité Offline ; jamais une optimisation qui supprime une information fonctionnelle.
- Chaque lot = plan Doctor avant édition, preuves d'impact, commit cohérent, check ciblé, A/B, nouvelle revue ; **Draft jusqu'à la fin**. `NOT_RUN` n'est jamais `PASS`. Aucun PASS/REVIEW OK global ni certification sur la seule base de ce document.

## État initial de la PR

- `DOCS_ONLY / PLANNED` — seul ce cadrage est ajouté.
- 43 exigences de l'issue source [#366](https://github.com/r9327/Dof-Atlas/issues/366) ouvertes ; les checks de Delivery Guard ne peuvent pas être verts sans développement, tests et rapport `ATLAS_DELIVERY_REPORT` sur le SHA final.
- Aucune nouvelle mesure Doctor/Graphify effectuée par l'agent lors de la création de cette PR ; ne pas les déclarer exécutées.


## Révision du 9 novembre — application légère et développement IA simple

**Demande utilisateur :** réunir dans Opti V3 les travaux utiles pour rendre Atlas plus léger, compréhensible, maintenable et facile à améliorer, avec une cible de **18/20 au minimum sur chaque axe**, sans sacrifier les fonctions ni la stabilité. Cette révision est un **plan de commits**, pas leur implémentation ni une nouvelle note obtenue. Les cinq axes sont évalués séparément : une moyenne de 18 ne compense pas un axe inférieur.

### Point de départ vérifiable

- Audit de `main@ac656f6069e0820ddf90c320244ebfda06f63316` ; branche V3 avant cette révision : `f15a5f2f6cf80ad9a71d9e55cf51323b40a36a1d`. Les mesures de main ne sont **pas** des mesures de cette branche ancienne.
- Note d'audit indicative : fiabilité **13/20**, performance **11/20**, architecture **10/20**, données/distribution **15/20**, développement IA/validation **13/20**. Cette appréciation antérieure n'a pas été produite par le barème détaillé ci-dessous : **ne pas comparer mécaniquement les deux scores**. Refaire une baseline avec ce barème avant de chiffrer le progrès.
- [CI exacte main 42538804282](https://github.com/r9327/Dof-Atlas/actions/runs/42538804282) : preload 36,07 s ; détails froids Quête 5,21 s, Guide 3,59 s, Succès 7,00 s ; Home après Guide 103,07 Mio, répétitions 105,52 puis 106,62 Mio ; pic arbre échantillonné 220,56 Mio. Scénarios Windows offscreen, pas réception DOFUS.
- Les widgets passent de 134 à 136, 138 puis 140 après retours Guide : suspicion de rétention, **cause à prouver**. Le scalaire de pic processus est inférieur à un instantané de détail observé : consolider le sampler et les instantanés.
- Les owners de tests diffèrent entre `.ai/context-map.yaml` et `tools/doctor_dev_lot.py` pour Miroir/Zaap ; l'audit JSON de `.github/workflows/scoped-pr-ci.yml` reste conditionné à la PR 303 ; `tests/__init__.py` initialise Qt même pour certaines suites sans UI.
- Les caches bornés, index JSONL/SQLite, lazy loading, écritures atomiques, rollback, delta et outils Doctor/Graphify **existent déjà**. Les compléter, jamais les recréer.
- Limites de la baseline : aucun p95/p99 représentatif, aucune mesure CPU/I/O native complète, ni essai réel 2/4/6/8 comptes ; images LFS en grande partie non hydratées localement. La revue logique de tous les commits historiques n'est pas présentée comme achevée.

### Barème explicite et preuve du 18/20

Chaque axe comporte cinq critères, chacun noté de 0 à 4 : **0** absent/non vérifié ; **1** plan ou preuve partielle ; **2** comportement partiellement implémenté et testé ; **3** comportement complet dans le périmètre déclaré, tests ciblés au SHA exact ; **4** niveau 3 et preuves représentatives, répétées ou natives lorsque nécessaires, avec limites et coûts vérifiés. Une documentation seule ne fait pas monter un critère runtime au niveau 3 ou 4.

| Axe | Cinq critères, chacun sur 4 | Conditions indispensables pour annoncer au moins 18/20 |
| --- | --- | --- |
| Fiabilité et fonctions | F1 parcours utiles réellement disponibles ; F2 focus/annulation/fermeture ; F3 erreurs et reprise ; F4 non-régression fonctionnelle ; F5 preuves natives et traçabilité | Aucun P0/P1 connu non résolu dans le périmètre déclaré ; focus Win32 et réception DOFUS prouvés par les propriétaires concernés ; une route placeholder ne vaut pas fonctionnalité livrée |
| Performance | P1 Home/pics ; P2 démarrage et premier contenu ; P3 CPU/I/O/UI ; P4 cycles/ressources/annulation ; P5 protocole A/B et statistiques | Home <100 Mio, pic arbre <=250 Mio, ouverture utilisable <=10 s pour les modules testés sur machine/protocole définis ; pas d'accumulation d'objets de page ; mesures froid/chaud distinctes, effectifs publiés |
| Architecture et simplicité | A1 propriétaires et interfaces ; A2 séparation UI/métier/données ; A3 orchestrateurs compréhensibles ; A4 dépendances/duplications ; A5 facilité d'évolution | Pas de seconde source de vérité ; deux tâches représentatives réalisables avec moins de lecture/modifications ou une justification mesurée ; chaque extraction/suppression a des consommateurs et une preuve de parité |
| Données, distribution et robustesse | D1 persistance cohérente ; D2 corruption/migration/sauvegarde ; D3 update/rollback/offline ; D4 intégrité/packaging ; D5 compatibilité Windows et preuve de reprise | Cohérence JSON/INI après interruption démontrée ; mise à jour depuis version précédente, interruption et relance réelles ; données conservées ; identité des données et vérifications d'intégrité préservées |
| Développement IA sur GitHub | I1 entrée et contexte utiles ; I2 owners/tests cohérents ; I3 environnement reproductible ; I4 CI ciblée et feedback ; I5 reprise/review/traçabilité | Même sélection canonique pour agent/Doctor/CI ; pas de FULL inutile pour docs ; setup pur/Qt/Windows explicite ; résumé exploitable du SHA exact ; tâche reprenable sans relire tout l'historique |

**La note n'est pas un nouveau gate CI.** La calculer dans la revue finale avec fichier, test/artifact, SHA, date, évaluateur et limites pour chaque critère. Ne pas déplacer le périmètre, baisser un seuil, masquer un manque natif ou transformer un report en DONE pour atteindre 18. Les fonctions annoncées mais absentes restent visibles : elles exigent livraison par leur propriétaire ou décision produit explicite, pas une requalification opportuniste.

### Séquence complète des commits à développer

Les identifiants C01..C12 désignent des **travaux prévus**, pas des commits déjà créés. Ce sont des lots de commits cohérents : un lot peut nécessiter plusieurs commits justifiés, jamais des commits vides pour satisfaire un compteur. Les intitulés sont indicatifs. La séquence fixe le périmètre, le résultat, les dépendances et l’acceptation de chaque lot ; le plan Doctor de son SHA de départ précisera les consommateurs, risques, tests et effort avant implémentation.

| Lot / priorité et intention de commit | Dépendances / propriétaire | Fichiers ou périmètre et résultat attendu | Validation d'acceptation |
| --- | --- | --- | --- |
| C01 P1 — `docs(perf): fixer baseline, preuves et séquence V3` | V3 ; OPTV-038/040/043 | Rapprocher main, HEAD V3, 31 règles/36 OPT/50 RAM et audit courant ; relever les fonctions livrées/partielles, PR ouvertes, sources de mesures et capacités d'environnement | Chaque constat a SHA/source/statut ; pas de faux gain ni doublon ; baseline du nouveau barème publiée |
| C02 P1 — `fix(dev): unifier la sélection des tests et les owners` | C01 ; V3, coordination #358 ; OPTV-037/039/040 | `.ai/context-map.yaml`, `.ai/scopes`, Doctor plan/check/lot et propriétaires CI : une source canonique réutilisée ; corriger les omissions Miroir/Zaap sans framework supplémentaire | Les changements Miroir/Zaap sélectionnent les suites spécifiques ; dépendances affectées incluses ; cas docs/JSON/CI pertinents testés ; aucune règle affaiblie |
| C03 P1 — `perf(dev): simplifier setup, feedback CI et reprise des agents` | C02 ; V3/#358/#269 ; OPTV-037/039/040/043 | Entrée IA courte, profils pur Python/Qt/Windows et outils existants ; scope CI fondé sur chemins, plus condition PR 303 ; résumé SHA/tests/erreurs/NOT_RUN et handoff existant | Session propre reproductible ; deux tâches représentatives reprises sans recherche globale répétée ; docs sans FULL inutile ; ni nouvel orchestrateur ni nouveau registre concurrent |
| C04 P1 — `fix(bench): consolider pics et scénarios comparables` | C01/C02 ; V3, propriétaire #297 ; OPTV-038 | Sampler mémoire + instantanés + high-water, métriques fenêtre/action/contenu distinctes, scénarios froid/chaud, CPU/I/O et retard Qt ; étendre le banc existant | Pic publié >= chaque instantané applicable ; n/machine/cache/SHA connus ; p50/p95 descriptifs avec effectifs, p99 seulement campagne suffisante ; pas de faux Windows/DOFUS |
| C05 P1 — `fix(ui): libérer les ressources Guide au retour Home` | C04 ; V3 ; OPTV-034/036 | Lifecycle des vues Guides/Encyclopédie, parents, connexions, callbacks obsolètes ; trouver la cause des deux widgets retenus avant correction | Objets de page revenus à leur niveau attendu après fermeture/annulation ; cycles 10 puis stress 20/50 dédiés ; progression et navigation conservées ; aucun GC forcé pour masquer le problème |
| C06 P1 — `perf(data): réduire le premier détail Quête et Succès` | C04 ; V3 ; OPTV-032/033/035 | Providers, compilation de détails, JSONL/SQLite/index existants ; réutiliser seulement les calculs démontrés redondants ; caches bornés et invalidation correcte | A/B même machine/données, chaque contenu testé <=10 s ; parité métier, offline et cache corrompu ; source ET binaire gelé ; RAM non dégradée |
| C07 P1 — `perf(startup): réduire le preload utile et borner les workers` | C05/C06 ; V3 ; OPTV-033/036 | `main.py`, preload/warmup et workers ; supprimer doublons et travail non utile, garder annulation/backpressure et contrat Home/warmup | Délai jusqu'au contenu utile réduit sur essais répétés ; Home <100 Mio et pic <=250 ; pas de jobs accumulés, UI réactive ; concurrence supplémentaire seulement si gain mesuré |
| C08 P2 — `refactor(core): simplifier les orchestrateurs réellement concernés` | C02/C05/C06/C07 et correctifs de focus intégrés ; V3 ; OPTV-032/036/039 | Extraire phases stables déjà couvertes dans les owners concernés ; réduire les embranchements et wrappers inutiles ; Graphify exact SHA avant structure | API et comportements utiles préservés, deux consommateurs réels avant abstraction partagée, moins de duplication/surface de modification ; pas de refactor global cosmétique |
| C09 P1/P2 — `test(integration): vérifier fiabilité, sessions et livraison` | SHA intégrés des propriétaires #398/#322, #331, #285/#287/#336 ; OPTV-039/041/042/043 | V3 coordonne et vérifie l'intégration ; chaque implémentation reste chez son propriétaire tant qu'un transfert explicite n'a pas été décidé | Focus corrigé sans replay ; interruption JSON/INI récupérable ; update précédent/offline/interruption/custom path/quit/relaunch ; réception DOFUS distincte des fixtures ; aucune copie concurrente de correctif |
| C10 P2 — `perf(package): réduire les dépendances et clarifier les parcours` | C01/C08/C09 ; propriétaires #285/#365/#306/#363 ; OPTV-011/034/039/042/043 | WebEngine preflight/packaging à évaluer après consommateurs ; anciens faux loaders à migrer avec leurs tests ; états indisponibles cohérents ; guides/UX chez leurs propriétaires | Poids et durée du vrai bundle avant/après ; aucun import/asset manquant ; ouverture externe et parcours utiles préservés ; pas de gain Atlas masquant le coût du navigateur externe |
| C11 P3 — `chore: retirer seulement les doublons devenus sans consommateurs` | Preuves de C08/C10 et LFS disponibles ; V3/#358 ; OPTV-011/034/043 | Petit lot rentable de ressources/outils/docs réellement obsolètes ; conserver archives de preuve et commandes utiles | Recherche statique + runtime + packaging ; gain mesuré ; zéro suppression basée uniquement sur Graphify ou absence de référence textuelle |
| C12 P1 — `test(perf): valider V3 et réévaluer les cinq axes` | Tous les lots nécessaires et dépendances intégrées ; OPTV-040/041/042/043 | Audit logique par commit puis global, barème 5x20, parcours natifs Windows faible PC, contrats/progression, exact-SHA Graphify et rapport de livraison ; Ready uniquement après développement achevé | >=18/20 sur CHAQUE axe justifié ; critères indispensables remplis ; manuel attesté humainement ; certification finale exacte ; sinon conserver les manques et ne pas annoncer l'objectif atteint |

Ordre critique : **C01 → C02 → C03/C04 → C05/C06 → C07 → C08 → C09/C10 → C12**. C09 se prépare en parallèle dans les PR propriétaires ; C11 est facultatif tant que son absence n'empêche pas un critère essentiel. C12 réévalue les preuves, il ne fabrique pas un score. Effort indicatif : C02/C03 2–4 jours chacun, C04 1–3, C05/C06/C07 5–10 cumulés selon diagnostic, C08 3–6 ; la durée des dépendances et de la recette native n'est pas garantie. Ces estimations ne sont pas des engagements de gain.

### Développement IA directement sur GitHub

Parcours cible : **issue bornée → scope canonique → plan Doctor → changement minimal → tests ciblés → PR avec preuves → CI sur SHA exact → feedback exploitable**. Le graphe exact reste requis pour le structurel ; ne pas réimposer une lecture complète du graphe pour une correction documentaire.

- Une issue doit exposer résultat attendu, comportements à préserver et acceptation ; les chemins/tests suggérés sont dérivés du scope, pas une liste concurrente entretenue à la main.
- Un agent doit pouvoir identifier rapidement entrée métier, dépendances et tests après lecture des règles obligatoires applicables ; éviter la relecture systématique des rapports historiques et des anciens logs, pointer vers les propriétaires canoniques au lieu de recopier les politiques.
- Réutiliser `ai_context handoff`, `.ai/context-map.yaml`, manifests, `agent plan/check/validate`, hooks et résumés CI. Examiner la cohérence avant toute modification des instructions.
- Une erreur CI doit montrer le test concerné, le SHA, l'exception utile, les fichiers de preuve et la prochaine vérification ; pas de promesse de correction automatique ni de dump massif comme seul feedback.
- Mesurer sur deux tâches : fichiers lus/modifiés, commandes, durée setup/tests/CI et capacité de reprise par un autre agent. Les économies de tokens ou de minutes doivent être observées, pas inventées.
- Ne pas installer OmniRoute/PostHog/Harness ou une orchestration LLM dans le runtime Atlas. Holding conserve ses responsabilités ; GitHub Actions et Doctor restent les propriétaires actuels.

### Portée et prévention des doublons

**Une seule PR Opti V3 coordonne le résultat global ; elle ne doit pas copier tous les commits de toutes les PR.** Les corrections déjà fusionnées sont récupérées en actualisant la branche depuis main avant codage, après inspection du diff. Les changements ouverts chez un autre propriétaire sont intégrés après sa validation ou après un transfert de périmètre explicite, jamais par cherry-pick aveugle.

- #398 remplace le suivi de #325 pour le correctif focus actuel ; #322 conserve la preuve DOFUS native. #331 traite la cohérence JSON/INI ; vérifier l'existence d'une branche avant création.
- #285/#287/#336 conservent le launcher et sa distribution ; #365/#333 l'UI/accessibilité ; #306/#363 le contenu des guides ; #358/#346 l'OSS et sa qualification Windows ; #297 les mesures ; #269 la traçabilité historique.
- Les fonctions non livrées (Bestiaire/Almanax/Chasse/Ocre/builder natif) sont recensées explicitement. Leur développement complet demande un périmètre produit propre ; des placeholders plus propres ne les rendent pas livrées ni éligibles à des points de fonctionnalité.
- La cible globale >=18 dépend de ces preuves externes. Une V3 documentaire ou quelques tests ciblés verts ne peuvent pas l'atteindre à eux seuls.

### État et contrat après cette révision

**PLAN_ONLY / NOT_IMPLEMENTED** : C01..C12 restent à exécuter ; aucun gain, refactor, score 18/20 ou test Windows n'est déclaré livré par ce document. Les 43 IDs OPTV de #366 restent inchangés. Les correspondances ci-dessus rendent leur exécution concrète ; les sujets supplémentaires sont des objectifs explicites de coordination et doivent faire l'objet d'une révision humaine du contrat avant toute extension d'implémentation hors scope. Aucun critère source n'est supprimé, aucun report n'est autorisé implicitement, aucun gate nouveau n'est créé.

Le présent changement documentaire s'arrête à l'ajout du plan. La PR reste **Draft** ; le rapport final `ATLAS_DELIVERY_REPORT` et la certification attendront les véritables commits de développement et leurs preuves au SHA exact.
