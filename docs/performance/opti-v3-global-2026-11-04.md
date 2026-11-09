# DOFUS ATLAS — Opti V3 : plan de travail contractuel
_Date : 2026-11-04 — source : issue #366 — état : cadrage uniquement, **aucune amélioration déclarée livrée**._

## Résultat attendu

Réduire le temps jusqu'au premier contenu réellement utilisable et les blocages Qt dans **tous les modules existants** ; conserver la RAM et les coûts CPU/IO bornés ; rendre les règles anti-régression **applicables aux prochaines modifications et fonctionnalités**, à travers les propriétaires de règles/Doctor/CI déjà présents. L'utilisateur demande une Opti V3 globale. La révision du 9 novembre ajoute une cible **18/20 minimum sur chacun des cinq axes**, avec des priorités d'exécution fondées sur l'audit ; aucun axe n'est exclu. L'implémentation est organisée en lots cohérents vérifiables, pas en grandes réécritures aveugles.

**Objectif transversal — coûts, maintenabilité et développement multi-IA :** cette PR ne se limite ni à la performance brute ni à Codex. Elle vise à diminuer les coûts réels de fonctionnement et de développement (CPU, RAM, I/O, stockage, temps machine et humain, durée et fréquence de CI, éventuels appels payants), tout en gardant Atlas rapide, fiable, simple à utiliser et à faire évoluer. Les contributions futures doivent être compréhensibles, testables et reprenables par un humain ou plusieurs assistants/agents IA, notamment ChatGPT, Codex ou d'autres, **en local comme directement sur GitHub** et sans dépendance à un modèle, un outil ou un lieu d'exécution unique. Comparer les coûts avant/après sur scénarios identiques ; ne pas prétendre à une économie financière ou de tokens sans mesure. Préserver les fonctionnalités et les protections existantes ; ne pas installer un nouveau cadre d'agents ou un service pour ce seul objectif.

**Contrôle au début de chaque lot :** lire le HEAD et les changements concurrents, vérifier les exigences concernées et lancer le préflight/plan Doctor approprié avant toute édition ; ne lancer ensuite que les tests ciblés et mesures A/B utiles à la modification, puis auditer le diff et le commit. La certification complète est réservée au HEAD final ; pas de FULL systématique par lot.


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

**PLAN_ONLY / NOT_IMPLEMENTED** : C01..C12 restent à exécuter ; aucun gain, refactor, score 18/20 ou test Windows n'est déclaré livré par ce document. Les 43 IDs et types OPTV de #366 sont conservés. Les critères concernés sont précisés dans la révision approuvée du 9 novembre ci-dessous et dans le contrat source ; les autres sujets restent chez leurs propriétaires, sans transfert implicite de leur implémentation. Aucun critère source n'est supprimé, aucun report n'est autorisé implicitement, aucun gate nouveau n'est créé.

Les changements documentaires de cadrage s'arrêtent au plan et à ses critères d’acceptation. La PR reste **Draft** ; le rapport final `ATLAS_DELIVERY_REPORT` et la certification attendront les véritables commits de développement et leurs preuves au SHA exact.


## Compléments approuvés le 9 novembre — critères concrets dans les 12 lots

Cette révision répond à l'accord utilisateur sur les compléments de l'audit. **Périmètre documentaire uniquement** : aucun scénario ci-dessous n'est déclaré exécuté par son ajout au plan. Les 12 lots C01..C12 restent les mêmes. Les précisions sont portées dans #366 sous les IDs existants **OPTV-011, 033, 038, 039, 040, 041, 042 et 043** ; les 43 IDs, types et contraintes précédents sont préservés, sans nouveau gate ou report implicite.

### Correspondance des 20 constats avec leurs preuves de résolution

Les numéros reprennent le Top 20 de l'audit du 9 novembre sur `main@ac656f6069e0820ddf90c320244ebfda06f63316`. Cette table est le suivi intégré au plan, **pas un second registre machine**. Les preuves futures doivent indiquer SHA, fichier/test/artifact, environnement, résultat et limites. Tous les points restent ouverts à la réévaluation de C01 ; une suspicion ou un risque peut être écarté par une preuve, sans correction artificielle.

| N° audit / constat | Lot / exigence source | Propriétaire et preuve attendue pour clôturer |
| --- | --- | --- |
| 1 — Zaap après perte de focus | C09 / OPTV-039,041 | #398/#322 : régression échouant sur base, passant sur candidat ; absence d'activation/émission suivante ; preuve native séparée |
| 2 — Exception de focus Miroir | C09 / OPTV-039,041 | #398/#322 : lecture Win32 en erreur traitée sans replay/restauration indue ; tests puis scénario natif |
| 3 — Home au-dessus de 100 Mio | C04/C05/C07 / OPTV-033,036,038 | #367/#297 : Home stabilisé <100 Mio sur les parcours, machine et caches définis ; mémoire conservée expliquée |
| 4 — Préchargement de 36 s | C04/C07 / OPTV-033,038 | #367 : première action utile et preload mesurés séparément ; budget fixé en C01 puis respecté sur essais comparables |
| 5 — Premier détail Succès coûteux | C06 / OPTV-032,033,035 | #367 : A/B source/frozen sur détail froid, contenu identique, gain répété et RAM bornée |
| 6 — Premier détail Quête coûteux | C06 / OPTV-032,033,035 | #367 : phases de compilation mesurées, recalculs éliminés sur preuve, parité métier et caches invalidés correctement |
| 7 — Widgets conservés après Guide | C05 / OPTV-034,036 | #367 : propriétaires et durée de vie identifiés ; comptage après fermeture/annulation et cycles longs ; fuite illimitée non présumée |
| 8 — Réception DOFUS non certifiée | C09/C12 / OPTV-039,041 | #322/#334 : vrais comptes 2/4/6/8, focus/collisions/arrêt et réception observés ; fixtures explicitement distinctes |
| 9 — Sélection de tests divergente | C02 / OPTV-037,039,040 | #367/#358 : plan/check/lot/CI choisissent les mêmes suites spécifiques et les dépendances nécessaires |
| 10 — Risque de paire JSON/INI incohérente | C09 / OPTV-039,041 | #331 : interruption entre écritures, reprise cohérente, profils/bindings/ordre conservés ; risque non présenté comme perte déjà survenue |
| 11 — Méthodes macro très longues | C08/C09 / OPTV-036,039 | Propriétaires macro : changement structurel coordonné après correctif focus ; traces et comportements préservés ; surface de modification réduite |
| 12 — Main/Guide/providers concentrés | C08 / OPTV-032,036,039 | #367 : responsabilités et consommateurs confirmés, changements plus locaux sur tâches représentatives, pas de nouvelle couche sans besoin |
| 13 — Fonctions annoncées non livrées | C01/C10/C12 / OPTV-039,043 | État précis de Bestiaire, Almanax, Chasse, Ocre, Tutoriels et builder natif ; fonction livrée avec preuve ou décision produit explicite ; un placeholder ne rapporte pas de point de fonctionnalité |
| 14 — Compatibilité Stuffs surtout destinée aux tests | C10 / OPTV-011,039 | #365, coordination V3 : tests du comportement externe migrés avant retrait des faux loaders ; ouverture refusée/acceptée et navigation préservées |
| 15 — WebEngine encore requis/emballé | C10 / OPTV-011,042 | #285 : consommateurs vérifiés, décision de packaging explicite et comparaison du vrai bundle ; aucun retrait aveugle |
| 16 — Delta réseau mais coût disque NTFS | C04/C09/C10 / OPTV-038,042 | #285/#287 : octets téléchargés/lus/écrits et temps séparés ; NTFS/ReFS distingués ; hashes/isolation/rollback conservés |
| 17 — Campagnes courtes et pic sous-agrégé | C04/C12 / OPTV-038,041 | #297 : pic >= instantanés applicables, provenance commune et effectifs publiés ; aucun p99 représentatif déduit de trois échantillons |
| 18 — Branche CI spéciale PR 303 | C03 / OPTV-040 | #367/#358 : sélection par scope et dépendances ; cas docs/JSON/workflow testés, sans FULL documentaire inutile |
| 19 — État de livraison dispersé | C01/C03/C12 / OPTV-040,043 | #269 : exigence → owner/PR → code → preuve → reste ; ne pas déduire la livraison du seul statut merged |
| 20 — Bootstrap/tests purs dépendants de Qt | C03 / OPTV-039,040 | #367/#358 : environnements pur Python/Qt/Windows reproductibles ; suites réellement pures exécutables sans Qt, ordre d'initialisation UI préservé |

### Temps jusqu'à la première action utile — C01/C04/C07

- Définir en C01 la machine Windows de référence (CPU, RAM, disque, version Windows), les données, l'état des caches et les étapes du parcours. Mesurer séparément lancement → fenêtre peinte, première action acceptée, résultat utile affiché et fin du preload ; un bouton activé sans résultat disponible ne suffit pas.
- **Fixer et versionner avant optimisation un budget numérique pour lancement → première action utile**, en froid et en chaud, avec effectifs et statistique retenue. La baseline observée à 36,07 s est celle du preload, pas un temps utilisateur interchangeable. Le budget reste à déterminer en C01 ; il ne peut pas être déclaré satisfait tant qu'il n'est pas fixé et mesuré.
- Conserver les seuils indépendants Home <100 Mio, pic arbre <=250 Mio et contenu utilisable <=10 s par module testé. Une baisse du preload ne doit pas déplacer le coût sur le premier clic ni augmenter la RAM sans bénéfice justifié.

### Légèreté disque et coût réel des updates — C04/C07/C10

- Relever taille du téléchargement, taille installée, caches disque, logs, temporaires et versions conservées, avant/après navigation, update et relance ; distinguer données source, état utilisateur et données reconstructibles.
- Publier les limites/rétentions existantes, puis un budget adapté en C01 pour chaque catégorie modifiée. Réutiliser rotation/purge déjà présentes ; aucune suppression de profils, progression, sauvegardes utiles ni version nécessaire au rollback pour gagner artificiellement de la place.
- Mesurer séparément réseau, lectures, écritures, temps et espace temporaire maximal d'une mise à jour sur **NTFS** et **ReFS** lorsqu'ils sont disponibles. Un delta réseau ne vaut pas économie d'I/O ; COW absent ou impossible doit rester visible. Plateforme indisponible = NOT_RUN, pas extrapolation.

### Reprise après incidents et sauvegardes — C09/C12

- Sur les chemins réellement concernés, prévoir des injections ciblées : **disque plein**, accès refusé/lecture seule, **fichier verrouillé**, arrêt pendant écriture ou update, paire JSON/INI de générations différentes, migration depuis un ancien format et restauration d'une sauvegarde. Le comportement concurrent est vérifié si plusieurs instances peuvent écrire la même donnée.
- Acceptation : erreur diagnostiquable, état ancien ou nouveau cohérent, reprise/rollback documenté, absence de perte des profils, bindings, ordre et progression ; sauvegarde restaurée et relue par l'application. Aucun fichier utilisateur réel n'est utilisé comme fixture destructive.
- Réutiliser #331 et #285/#287. Les cas purs peuvent être simulés localement ; les comportements Windows de verrouillage et de l'application installée exigent leur preuve native. Il s'agit de scénarios à vérifier, **pas de nouveaux bugs déclarés**.

### Navigation simple et accessibilité — C10/C12

- Avec #365/#333, vérifier les parcours fréquents choisis en C01 : retrouver/reprendre un guide, ouvrir un détail, changer de personnage, revenir Home et ouvrir un outil disponible. Relever les actions, détours et états d'attente avant/après ; automatiser une répétition seulement si le comportement utile est préservé.
- Recette ciblée : clavier seul, ordre et visibilité du focus, libellés utiles aux technologies d'assistance, petite fenêtre supportée et DPI Windows **100/125/150/200 %** sur les écrans concernés. Documenter les configurations réellement testées ; pas de certification d'accessibilité globale déduite d'une capture.
- Acceptation : aucune action essentielle inaccessible, aucun contrôle essentiel coupé, retours et états indisponibles cohérents ; la clarification d'un module en préparation ne vaut pas livraison de sa logique métier.

### Dépendances, packaging et diagnostics — C09/C10

- Réutiliser le verrou, les manifests et vérifications existants : versions/hashes, origine des dépendances et fichiers réellement embarqués, ressources LFS nécessaires, plugins Qt et workers gelés. Examiner les vulnérabilités pertinentes avec les moyens disponibles ; une analyse absente n'est pas « zéro vulnérabilité » et ne justifie pas l'installation automatique d'un nouveau service.
- Conserver la recette reproductible : SHA, dépendances, outils de build, entrées et commande. Lors d'une campagne de livraison, comparer les manifests/hashes de deux builds isolés si possible, expliquer les variations ; ne pas annoncer un binaire identique octet pour octet sans preuve. Ne pas doubler les builds à chaque commit documentaire.
- Vérifier que les diagnostics exportés excluent secrets et données personnelles non nécessaires ; réutiliser les mécanismes locaux/volontaires et d’expurgation lorsqu’ils existent, et vérifier leur résultat. Ne pas activer de télémétrie. Une identité/signature d'éditeur ne se déduit pas du seul hash de contenu.

### GitHub et deux tâches IA reproductibles — C03/C12

- Vérifier en lecture la configuration effective des contrôles requis, règles de branche et triggers, en lien avec **#266** ; la présence du YAML ne prouve pas l'activation du contrôle distant. Absence de droit admin = état non vérifié explicite, sans contournement ni modification des permissions dans ce lot documentaire.
- **Tâche A : corriger un petit bug.** Partir de l'issue, retrouver le propriétaire, reproduire, modifier le minimum, lancer les tests pertinents puis produire le résumé de PR au SHA exact.
- **Tâche B : ajouter une petite fonctionnalité** dans un module existant, avec réutilisation d'un composant/service, préservation des contrats et validation ciblée. C01 choisit et fige deux cas concrets représentatifs, puis compare l'ancien et le nouveau workflow avec mêmes cas et environnement.
- Pour chaque cas : fichiers consultés/modifiés, commandes, durée setup/tests/CI et contexte nécessaire à une reprise par un autre agent ; séparer attente CI et travail de l'agent. Garder un handoff court dans le mécanisme existant. Aucun quota arbitraire de tokens, aucune économie chiffrée sans observation.
- Acceptation : même sélection canonique agent/Doctor/CI, environnement propre reproductible, échec relié au bon test/SHA et reprise possible sans relire tout l'historique ; contrôles requis effectifs ou blocage identifié, jamais annoncés actifs sans preuve.

### Alignement avec #366 et état de livraison

La demande utilisateur « ajoute ça à la PR » valide l'ajout de ces précisions au plan et l'alignement du contrat source annoncé lors de la revue. Les descriptions **OPTV-011,033,038,039,040,041,042,043** sont complétées sans retirer leur texte initial, changer leurs types, autoriser un report ou modifier les critères restants. OPTV-043 porte la correspondance des 20 constats et le bilan des cinq axes ; les preuves manuelles restent attachées aux exigences manuelles.

**Statut : PLAN_ONLY / NOT_IMPLEMENTED.** Les contrôles de ce changement portent sur le document, la cohérence de ses références et le contrat ; aucun gain, scénario natif, build reproductible, sécurité complète ni note >=18/20 n'est acquis. La PR reste Draft. Les budgets encore à fixer en C01 et les preuves manquantes restent visibles jusqu'à résolution.
## Audit complémentaire vérifié — 9 novembre 2026 (itération 1)

> **Document de diagnostic, pas résultat runtime.** Audit en lecture sur `main@2ce1f5b4f65f435b5ceabec95590cfd8da02f7dc` et `#367@2cf5aaa7f3148531e99df75fb2c3517822afd6e5`. Ces SHA datent de l'observation, pas d'une future baseline A/B. **Aucun test, Graphify, Doctor ni essai Windows exécuté dans cette itération.** Les informations historiques ci-dessus restent de l'historique et ne doivent pas être traitées comme état actuel.

### Préparation impérative avant C01

- La comparaison GitHub `main...#367` est **DIVERGED : 993 commits behind / 5 ahead**, merge-base `060803282269098dfc6919e6e85f24309d2c485f`. Le diff V3 actuel ne contient que `.ai/context_index.json` et les deux documents Opti V3 : **aucune optimisation applicative nouvelle**. Ne pas développer sur cette vieille base comme si elle était récente.
- Avant toute synchronisation, relever **les deux nouveaux SHA**, inspecter les modifications des trois chemins V3, sauvegarder le HEAD de la branche et préférer l'intégration non destructive de `main` (merge avec résolution auditée des conflits) ; **pas de reset, force-push ni cherry-pick massif**. Recalculer ensuite la divergence, Doctor/Integrity ciblé, puis figer une nouvelle baseline. Un ancien run `main@ac656f60` ne certifie pas `main@2ce1f5b4` ni la future branche synchronisée.
- **PR propriétaires au moment de la vérification** : #325 et **#398 fusionnées**, ainsi que #303/#310 ; #285, #358, #363, #365, #306 sont ouvertes en Draft. #297, #322, #331, #333, #334, #346, #266, #287, #336 et #269 sont des **issues**, non des PR ; leur ouverture n'est pas une preuve d'implémentation. Les références historiques à « #398 ouverte » ci-dessus sont périmées.
- La PR #367 demeure **Draft / PLAN_ONLY / NOT_IMPLEMENTED** : aucune des 43 exigences n'est certifiée par le texte, et les cinq scores cible ≥18/20 ne sont pas acquis.

### Ordre d'exécution amendé, sans nouveau lot ni nouveau gate

**Synchronisation sûre → C01 (budget et traçabilité) → C04 (fiabilité des mesures) → C02 (routage canonique des tests) → C05/C06 (hotspots prouvés) → C07 (startup) → C03 (en parallèle : workflow IA et CI) → C08 (simplification mesurée) → C09/C10 (intégrations/packaging) → C11 (facultatif) → C12 (recette finale).** C03 peut démarrer parallèlement à C04 après les propriétaires C02 pertinents ; éviter qu'un chantier de documentation IA retarde la résolution des latences utilisateur. C09 démarre en coordination avec les issues propriétaires sans recopier leur implémentation. Les lots C05/C06 ne sont indépendants que si fichiers/consommateurs et tests ne se chevauchent pas.

**Début de C01** : versionner avant optimisation machine Windows, données, caches froid/chaud, seuil numérique première action utile et méthode de mesure séparant fenêtre peinte, clic accepté, résultat utile et preload fini ; distinguer performances source/offscreen, EXE natif et tests réels DOFUS. **C04 avant modifications de performance** : corriger la provenance du pic échantillonné vs instantanés et vérifier la cohérence du banc existant. Les durées anciennes (preload 36,07 s ; Succès 7,00 s ; Home après Guide 103,07 Mio) sont des points d'enquête, **pas** des résultats du HEAD actuel.

### Règles de décision contre la surarchitecture

1. Chaque amélioration proposée a : `ID(s)`, fichier/ligne, SHA, cause mesurée, coût/bénéfice, risque, test ciblé, A/B comparable et propriétaire. Relier plusieurs OPT/RAM/OPTV au **même défaut réel**, sans fabriquer 117 sous-projets.
2. Ne pas recréer les mécanismes déjà présents (SQLite signé et reconstruit, LRU d'images de l'Encyclopédie, lazy factories, travaux d'annulation ou écriture atomique) ; vérifier leurs **consommateurs**, limites et efficacité avant de les changer.
3. **Ne pas confondre les huit processus de `tools/atlas_doctor_lib/parallel_app.py` avec huit interfaces Windows natives** : le runner utilise des profils isolés et des probes Qt offscreen, tandis que `app/windows/single_instance.py` définit un mutex mono-instance dans le lancement réel. La recette DOFUS 2/4/6/8 reste propriétaire de #322/#334.
4. La qualité « ≥18/20 » exige des preuves par critère, avec `NOT_RUN/BLOCKED` explicites : aucune moyenne ne compense un axe insuffisant ; ne pas attribuer de nouvelle note produit sans nouvelle campagne représentative.

### Itération 2 — audit ciblé des chemins chauds et des faux travaux (lecture `main@2ce1f5b4`)

| Constat / source et ligne à la référence auditée | État de preuve | ID(s) / owner | Action ciblée, coût/risque et critère de clôture |
| --- | --- | --- | --- |
| `app/modules/encyclopedia/views/guides_view.py:214-262,493-508` : anciens chemins d'images de contenu Guide présents et décodés en taille complète ; **candidat nettoyage après transition Ganymède, pas nouveau développement**. | **CONFIRMED_STATIC / BLOCKED_BY_363** | C09/C11, OPTV-002/015/034/036, RAM-23/48 ; transition propriétaire #363 | **Ne pas optimiser cet ancien parcours d'images Guide** : vérifier en C09 sa non-utilisation après #363, puis étudier son retrait en C11 avec Graphify, tests et packaging. Conserver séparément les assets Unity et images des autres modules. |
| `app/modules/encyclopedia/services/image_service.py:12-100,104-145` : un service partagé existe déjà, LRU 64 éléments/8 Mio et décodage `QImageReader.setScaledSize`. `guide_home_image_cache.py` est un wrapper vers le même service. | **IMPLEMENTED (mécanisme), efficacité NOT_RUN** | C05/C11, OPTV-034, RAM-22/48 | **REUSE** l'existant ; mesurer les références, mémoire native et hit/miss avant modification ; ne pas créer de cache image V2 parallèle ou retirer le wrapper sans audit de consommateurs. |
| `main.py:2250-2485` : préloads Quêtes/Encyclopédie/Craft sérialisés avec états et relais ; `main.py:904+` réutilise **un timer par tâche** pour les retries. Le Home dépend au moins de la fin Quêtes. | **CONFIRMED_STATIC / impact NOT_RUN** | C04/C07, OPTV-033/036/038, RAM-35 | Mesurer première action utile distincte de fin Guide/Succès/Craft ; démontrer quels travaux sont indispensables à Home. Ne pas créer de nouveau scheduler et ne pas rendre Home fictivement interactif. |
| `app/preload.py:51-101` : `StartupPreloader.run` utilise un daemon worker, `processEvents()` et un timeout qui ne signale pas explicitement l'arrêt du worker ; `main.py:555` contient un ancien point d'entrée `run_startup_preload`. | **REVIEW, utilisation production à confirmer** | C07/C11, OPTV-033/036 | Graphify + recherche des consommateurs/tests/entrypoints avant de corriger ou supprimer ; vérifier qu'un timeout n'abandonne pas un traitement encore actif. Ne pas conclure à un bug du chemin de lancement courant sur simple existence du helper. |
| `app/quest_catalog_details.py:215-275,319-425` : détail `SELECT detail FROM quests WHERE id=?`, compilation source lors d'un miss, écriture SQLite, LRU en mémoire et cache signé. | **IMPLEMENTED (mécanismes), gain NOT_RUN** | C06, OPTV-008/017/024/035, RAM-26/27 | Profiler `sqlite_lookup_ms`, `source_index_and_context_ms`, `source_compile_ms`, `sqlite_serialize_and_persist_ms` **déjà exposés** ; corriger l'étape dominante, pas ajouter un pool SQL ou un second index par défaut. |
| `tools/benchmark_phase8_memory.py:389-447,615+` : sampler 50 ms avec instantanés ponctuels et correction ponctuelle des pics de warmup ; une observation détaillée peut dépasser le pic déclaré selon le protocole historique. | **CONFIRMED_STATIC / anomalie numérique à reproduire** | C04, OPTV-038, RAM-01/03/37 | Résultat publié = maximum cohérent entre échantillons, snapshots applicables et high-water comparables, avec source/PID/phase ; éviter double comptage entre processus parent et enfant. Tester avec une fixture où le snapshot dépasse les échantillons. |
| `tools/atlas_doctor_lib/parallel_app.py:68-149` exécute 8 **processus de sonde Doctor offscreen** avec profils isolés ; `app/windows/single_instance.py:7,42+` contrôle un mutex mono-instance du lancement courant. | **CONFIRMED_STATIC** | C04/C12, OPTV-038/041, RAM-39/41 | Garder la sonde multi-processus pour charge CPU/RAM, mais **ne jamais** l'étiqueter « huit fenêtres Atlas natives ». Recette native différenciée et DOFUS 2/4/6/8 chez #322/#334. |
| `.github/workflows/scoped-pr-ci.yml:62-101` : audit JSON complet déclenché par `PR_NUMBER == 303`, non par nature du diff ; `.ai/context-map.yaml:72-80` lie Zaap à un smoke générique, tandis que `tools/doctor_dev_lot.py:24-57` ne contient pas de propriétaire direct Zaap. | **CONFIRMED_STATIC / décisions effectives à exécuter** | C02/C03, OPTV-037/039/040, #358 | Établir **une sélection canonique** pilotée par chemins/dépendances (ne pas coller du YAML partout) et injecter un diff Zaap/mirror/JSON/docs fictif en test. Confirmer l'exécution du test spécifique, la couverture et l'absence de FULL documentaire inutile. |
| `tests/__init__.py:35-43` crée une `QApplication` si le package `tests` est importé ; **le workflow Draft contourne déjà cet import** via `unittest discover -s tests` (`.github/workflows/scoped-pr-ci.yml:108-149`). | **IMPLEMENTED_STATIC pour le contournement Draft / autres usages à vérifier** | C03, OPTV-039/040 | Éviter toute refonte globale de fixtures Qt. Mesurer uniquement les invocations `python -m unittest tests.xxx` et leurs coûts si elles sont réellement répétées ; conserver le chemin stdlib sans Qt déjà présent. |
| `app/core/json_store.py:60+` distingue validation critique et repli contrôlé, et `write_json_atomic` protège `PROFILE_FILE`; issue #331 documente une publication JSON/INI multi-fichiers non atomique. | **PARTIAL — protections en place, incident non démontré** | C09, OPTV-039/041, owner #331 | Tests crash entre fichiers, générations, disque plein et restauration isolée ; pas de nouveau framework de persistance en V3. |

**Audit anti-doublon :** les mécanismes `ImageService`, `_connect` SQLite, LRU, `_schedule_preload_retry`, checks SHA et scripts Doctor/Graphify sont **déjà présents** ; l'optimisation consiste à mesurer leur efficacité et corriger les vrais écarts. La présence statique ne prouve pas l'exécution, la sécurité de tous les chemins ni un PASS au nouveau HEAD.

**Validation non effectuée dans cette itération :** Doctor/Graphify/Integrity, CI, machine Windows, vraie recette 2/4/6/8 DOFUS, A/B, p95/p99 ; tous restent `NOT_RUN`.

### Décision produit du 9 novembre — Guides Ganymède sans images de contenu

**Décision utilisateur** : les futurs Guides suivent Ganymède et **n'auront plus d'images de contenu**. Les optimisations du décodage et du cache des anciennes captures/illustrations **des Guides** ne constituent donc **plus une priorité V3** et ne doivent pas être développées pour un parcours destiné à disparaître. Cette décision prévaut sur les anciennes pistes générales C05/C06 et RAM-23/48 lorsqu'elles concernent spécifiquement ces images.

- **#363 est toujours propriétaire** de la transition des parcours. Avant sa livraison validée, la présence de `_decode_guide_image`, `_decode_solution_image` et des caches actuels n'autorise ni suppression prématurée ni conclusion qu'ils sont inutilisés. En C09, inspecter le HEAD réellement intégré, les consommateurs/testeurs, les exceptions éventuelles et la parité de progression ; le ménage éventuel appartient ensuite à **C11**, uniquement si bénéfice réel prouvé.
- **V3 ne doit pas réintroduire les images de parcours Guide**. Conserver séparément les ressources d'interface (icônes de navigation, logos/skins Unity, polices) et les images nécessaires à **Bestiaire, Map, Crafts, Stuffs** ou d'autres écrans ; leur coût de décodage reste à profiler indépendamment.
- **Remplacement de priorité** : C05 reste focalisé sur lifecycle/retour Home, C06 sur premier détail Quête/Succès. Pour OPTV-002/015/034, vérifier les images actives hors Guide ; classer l'ancien chemin d'images de contenu Guide **BLOCKED_BY_363 / CANDIDATE_CLEANUP**, et non « optimisation manquante à développer ». Un nettoyage visuel ne doit pas supprimer les informations métier, combats, prérequis ou fonctionnalités utiles.
- **Preuves de clôture** : #363 fusionné et contenu contrôlé au SHA exact, navigation de Guide sans images de contenu, dépendances et ressources mortes confirmées avec Graphify + code/tests et packaging, métriques mémoire/bundle avant-après si suppression. **NOT_RUN** à cette étape documentaire.

### Itération 3 — audit Map, Crafts, Encyclopédie, Stuffs (sans images des futurs Guides)

Audit en lecture, **non exécuté**, basé sur `main@2ce1f5b4` ; ne pas confondre ce diagnostic avec une mesure sur #367. Les éléments déjà présents ne doivent **pas** générer un nouveau développement.

| Chemin et observation statique | Classification / propriétaire | Décision minimale et preuve |
| --- | --- | --- |
| `app/ui/world_scan_panel.py:338-393,464-483` : génération incrémentale des requêtes et coalescence vers le dernier choix, rejet des réponses obsolètes, retrait des pixels `QImage` si Map est masquée. `tests/test_world_scan_async_loading.py` contient des tests dédiés. | **IMPLEMENTED_STATIC / C05-C07 / V3** | Ne pas recréer une file de jobs Map ni un second mécanisme d'annulation. Rejouer tests sur SHA exact puis stress navigation/retour Home ; chercher seulement dérive RAM, jobs qui restent et délai d'application de la dernière sélection. |
| `app/ui/world_scan_panel.py:444-460,549+` : une image de carte est encore chargée en `QImage(str(path))` à taille source et transmise pour conversion `QPixmap` sur l'UI. | **PARTIAL / C05-C06 / V3 Map** | Candidat prioritaire **à la place des images de contenu Guide** : profiler taille réelle des cartes, temps de décodage, RSS/Qt natif et coût de conversion ; tester décodage redimensionné ou tuilage **uniquement si la résolution/zoom et les interactions sont préservés**. Un rendu zoomable ne doit pas être dégradé pour gagner quelques Mio. |
| `app/pages/craft_page.py:421-432,487-491,629-683,798-854` : debounce recherche 120 ms, résultat plafonné sur chemins SQLite, batches de widgets et libération des listes/cache au retour Home. `tests/test_craft_minimal_lazy.py` couvre batch et release. | **IMPLEMENTED_STATIC / C05-C06 / V3 Crafts** | Pas de nouveau debounce, virtualiseur ou cache par principe. Rejouer les tests et profiler les très grands résultats, réouverture et widgets conservés ; intervenir seulement si la borne existante montre une latence excessive ou un manque fonctionnel. |
| `app/modules/encyclopedia/views/encyclopedia_page.py:141-162,595-652,1040-1230` : threads daemon de chargement Quêtes/Guide/Succès, suivi des threads actifs, `_join_runtime_threads` sans délai explicite dans `closeEvent` et la destruction. | **REVIEW / C05-C07 / V3 Encyclopédie** | Vérifier le **risque de fermeture bloquée** si un worker reste lent/verrouillé (non reproduit) et le risque d'ancienne réponse livrée après changement de génération ; tests ciblés fermeture pendant charge, erreur et annulation, mesure blocage UI et arrêt sûr sans `join()` illimité sur le thread Qt. Aucune nouvelle couche de threading avant attribution de la cause. |
| `app/quest_catalog_details.py:220-275,285-315` et `tests/test_quest_catalog_details.py` : séquençage/phase profiling, batches de recherche de 32, cache borné et tests concurrents existants. | **IMPLEMENTED_STATIC / C06 / V3 Quêtes** | Réutiliser les chronos par phase et tests déjà établis, ne pas créer de bench SQL parallèle ; quantifier uniquement le premier détail froid sur mêmes données/SHA. |
| `app/pages/equipment_page.py:1-162` : Stuffs/Équipement redirige vers Huzounet externe ; le chargement WebEngine en production est neutralisé et la classe legacy est uniquement injectable pour les tests. | **IMPLEMENTED_STATIC pour absence de WebEngine chargé / fonction builder native NON LIVRÉE ; C09-C10 / #285 et propriétaire Stuffs** | Ne pas promettre de gain par retrait d'un WebEngine déjà **non importé en runtime**, ni annoncer builder intégré livré. Mesurer seulement si `PySide6-QtWebEngine` est encore **emballé dans le binaire** et qui le consomme avant proposition de retrait. |
| `app/pages/home_page.py:377-389` conserve un placeholder Almanax. | **PARTIAL PRODUIT / C01-C09 / propriétaire fonctionnel** | Ne jamais attribuer des points de fonctionnalité à un placeholder ou étendre V3 pour refaire l'Almanax ; préciser périmètre réellement disponible. |

**Tests propriétaires déjà identifiés :** `tests.test_world_scan_async_loading`, `tests.test_craft_minimal_lazy`, `tests.test_encyclopedia_on_demand_loading`, `tests.test_quest_catalog_details` et `tests.test_optimized_achievements_refresh`. Présence **confirmée dans main** ; exécution exacte-SHA **NOT_RUN**. Première décision de C02 : vérifier que le même diff Map/Crafts/Guide entraîne ces tests dans Agent/Doctor/CI sans une deuxième carte de routage.

**Économie de développement :** réserver les modifications V3 aux défauts qui restent après cette revue : fermeture des threads, mesure des images **Map**, hotspots du premier détail et dérive Home. Ne pas ajouter une nouvelle optimisation d'images Guide si le contenu Ganymède n'en utilise plus.

### Itération 4 — threads, retour Home et fiabilité du benchmark (audit statique)

Vérification ciblée des consommateurs sur `main@2ce1f5b4f65f435b5ceabec95590cfd8da02f7dc`. Ce tableau établit **les chemins de code**, pas une régression reproduite sous Windows. Résultats Doctor, Graphify, tests et profiling : **NOT_RUN**.

| Risque constaté, preuve exacte | Priorité / décision C05-C07 | Test minimal et garde-fou |
| --- | --- | --- |
| **Attente illimitée de worker Qt** : `app/modules/encyclopedia/views/encyclopedia_page.py:141-145` appelle `thread.join()` sans limite ; `:612-614` l'attache au signal `destroyed` ; `:639-643` l'appelle aussi au `closeEvent`. `main.py:1835-1856,1900-1930` détruit la page Encyclopédie à chaque retour Home via `deleteLater` puis `sendPostedEvents(DeferredDelete)` + `gc.collect()`. Un worker ralenti en I/O peut donc bloquer le **thread UI à la destruction**, même après avoir quitté l'onglet. | **P0 à reproduire avant correction** : la cause potentielle est étayée ; durée réelle du blocage inconnue. Vérifier les fonctions workers, ownership et signaux. Ne pas remplacer aveuglément `join()` par un abandon du worker (risque de cycle de vie et signaux tardifs). | Test isolé/sous-processus avec worker bloqué par `Event`, déclenchement Home et seuil temps Qt ; test de fermeture normale, exception et worker terminé ; étudier annulation coopérative, signal de fin fiable, weakref et attente **hors** thread UI. Aucune modification des parcours Ganymède. |
| **Nettoyage synchrone sur Home** : `main.py:1851-1862,1896-1904` programme `collect_released_page_cycles`, qui appelle `QApplication.sendPostedEvents(None, DeferredDelete)` puis `gc.collect()` **sur Qt**. Cela libère utilement les wrappers mais peut ajouter un pic de latence à l'action Home. | **P1 / instrumenter plutôt que supprimer**. L'intention anti-fuite est déjà présente ; la supprimer peut dégrader RAM. | Chronométrer chaque nettoyage et le délai du clic Home au premier frame/interactivité, avec 10/20/50 allers-retours ; distinguer pause GC, signal destroyed/joins, DeferredDelete, et travail réellement libéré. |
| **Map : éviction sûre existante** : `main.py:1867-1896` refuse l'hibernation avec worker actif, `world_scan_panel.py:340-388,462-480,960-972` coalesce, relance et libère des pixels quand masqué. `tests/test_world_scan_async_loading.py` contient déjà des scénarios de résultat tardif, menu et cache suspendu. | **P2 / conserver**. Aucun nouveau scheduler ni mécanisme de cancellation tant qu'un test ne démontre une perte d'état. | Rejouer les tests Map ciblés et allers-retours, surtout lorsque dernière génération est encore en vol, vérifier RSS et sélection du monde conservée. |
| **Benchmark différent du lancement utilisateur** : `tools/benchmark_phase8_memory.py:575-605` instancie `AtlasWindow()` puis fait `window.show()` avant d'attendre la fin du preload ; le vrai `main.py:2830-2854` garde la fenêtre principale cachée jusqu'à la fin de Quêtes et affiche un dialogue de chargement. | **P0 mesure / C01-C04**. Le benchmark RAM actuel reste intéressant, mais **ne mesure pas à lui seul le vrai temps de première action utile en lancement normal**. | Scénario séparé utilisant `main()`/chemin launcher natif et événements horodatés splash→dialogue→Home peint→clic accepté→réponse utile→Guide/Succès prêts. Ne pas adapter le test en affichant Home plus tôt sans changement de produit approuvé. |
| **Précision pic RAM** : `tools/benchmark_phase8_memory.py:272-330` calcule arbre instantané + warmup sibling distinct ; `:389-430` échantillonne à 50 ms ; `:589-671` diffère volontairement le sampler dans le mode « token sans PID warmup » afin de réduire l'effet observateur, et recourt au parent PeakWorkingSetSize. | **P0 mesure / C04**, pas un bug prouvé : pic parent et pic arbre ne sont pas équivalents et les cas de sibling warmup nécessitent un protocole explicite. | Fixture instrumentée parent/enfant/sibling et événement bref entre deux ticks ; conserver `sampled_tree_peak` vs `parent_peak` séparés, horodater les échantillons, rapporter conditions d'inclusion et une limite de détection, ne jamais additionner des pics survenant à des instants distincts. |

**Invariants avant une modification de code** : 1) les chargements asynchrones ne doivent ni geler l'UI ni livrer vers un `QObject` détruit ; 2) Home doit retrouver sa RAM stabilisée **sans** travaux cachés infinis ; 3) les gains sont comparés sur les mêmes scénarios, données, environnement et SHA ; 4) préserver tous les garde-fous utiles et éliminer uniquement les doublons prouvés ; 5) pas de travaux sur les anciennes illustrations des Guides Ganymède.

**Priorité immédiate réévaluée** : vérifier le blocage potentiel `destroyed → join` et son intersection avec le nettoyage Home, puis fiabiliser C04. Ces deux pistes sont plus importantes que le décodage des images des anciens Guides.

### Itération 5 — tri des corrections réellement utiles avant développement

- **P0 à investiguer** : `EncyclopediaPage.destroyed → _join_runtime_threads` durant `Home → deleteLater → DeferredDelete`. Risque de gel sur worker lent, **pas** de régression démontrée. Critère : une fermeture/transition ne doit pas attendre indéfiniment sur Qt et doit conserver l'absence de signaux vers des objets détruits.
- **P0 métrologie** : mesurer séparément le démarrage utilisateur réel (fenêtre cachée, popup, Home) et le benchmark memory offscreen ; vérifier la provenance du pic process-tree avec parent/warmup sibling. Critère : aucune comparaison de pics incompatibles, chronos p50/p95/p99 sur scénario identique.
- **P1 routage ciblé** : ne corriger les sélecteurs de tests que là où l'un des tests existants a une vraie couverture directe ; préserver `FULL_REQUIRED` pour les autres. Les modules ont déjà `Doctor agent`, `CI Decision Arena` et un `Scoped PR Feedback` qui reste advisory.
- **HORS priorité** : caches/batch/retry Map-Craft déjà présents, refonte générale des fixtures Qt, ancienne optimisation des images de contenu Guide, duplication de Ponytail/Graphify/Doctor ou nouvel orchestrateur IA.
- **Dépendance structurelle** : #367 a toujours la base très ancienne `060803282269098dfc6919e6e85f24309d2c485f` (au constat de cette itération). **N'ajouter aucun patch applicatif V3 basé sur cette branche avant synchronisation sûre avec main**, vérification du diff et requalification des tests.

### Itération 6 — début de C04 implémenté, branche synchronisée (9 novembre)

**État de la branche, pas certification V3 :** #367 synchronisée avec `main@2ce1f5b4f65f435b5ceabec95590cfd8da02f7dc` par vrai commit de fusion `a0207f4ff63334175dcbc6ae39dc821fdb072f5f`, parents PR + main, **sans force-push**. La sauvegarde `backup/opti-v3-367-before-c04-20261109` conserve le HEAD documentaire précédent. Les **cinq seuls chemins** différents de main au merge sont l'index IA, les deux plans et les deux fichiers C04 ci-dessous. Les mentions de « 993 commits de retard » des itérations précédentes sont un **constat historique avant fusion**, désormais résolu pour ce main.

**Code C04 livré en petit lot :**
- `tools/benchmark_phase8_memory.py` : nouveau calcul `_largest_checkpoint_tree_sample(stages)` limité aux mesures instantanées du RSS arbre, ignores valeurs absentes, NaN, infini et booléens, préserve l'identité du checkpoint.
- Diagnostics JSON ajoutés : `checkpoint_tree_peak_rss_mb`, `checkpoint_tree_peak_sample`, `checkpoint_exceeds_reported_tree_peak`. Le champ existant `peak_tree_rss_mb` et **le seuil de CI restent inchangés** pour permettre une comparaison fidèle avant d'envisager une réconciliation normative.
- `tests/test_phase8_memory_benchmark_contract.py` : trois tests de contrat et de la fonction (pic maximum sans sommer des high-water non simultanés, lectures invalides, non-remplacement du gate). Les tests utilisent l'AST réel du benchmark sans dépendance Qt.

**Preuve GitHub** : run `42649440512` du commit `a0207f4ff63334175dcbc6ae39dc821fdb072f5f` : **Scoped PR Feedback PASS** ; dans son log, les trois tests `CheckpointTreePeakTests` sont `ok`, et la suite correspondante indique 11 tests OK. **Ce PASS est limité à la suite exécutée dans ce run**, pas au benchmark Windows/DOFUS. Run `42649440039` Phase Certification `SKIPPED` (Draft).

**Blocage documentaire réel et volontairement conservé** : run `42649439761` Atlas Delivery Guard **FAIL** avec `DELIVERY_GUARD_BLOCKED: Exactly one delivery contract/report block is required`. Le guard `tools/ci_delivery_guard.py` impose un rapport sur **43 exigences avec statuts uniquement DONE assorti de preuves ou DEFERRED autorisé par issue** ; le plan V3 inachevé ne peut pas en publier un honnêtement. **Ne jamais fabriquer ces statuts ni assouplir le guard pour obtenir vert.** Rédiger le bloc uniquement quand l'inventaire est véritablement admissible et les preuves attachées.

**Contrainte C05 réévaluée avant correction** : `tests/test_encyclopedia_cold_worker_release.py` teste explicitement la destruction Qt d'une page pendant que le worker Guide est en cours et sa libération Python après la fin. Le `destroyed → thread.join()` illimité reste un risque de gel ; **une suppression brute du join ou un délai arbitraire ne peut pas être validé à l'aveugle**. Préparer un test spécifique Home/Qt réellement non bloquant, examiner l'ownership des signaux et la réponse obsolète, puis modifier le chemin étroit avec preuve Windows quand disponible.

**À faire C04** : confirmer l'écart `checkpoint_exceeds_reported_tree_peak` sur une campagne réelle Windows, horodater la provenance, mesurer première action utile et réévaluer le budget sans changer silencieusement le gate. Les 43 exigences OPTV et les cinq scores ≥18/20 restent **NON CERTIFIÉS**.

## Itération 7 — audit **seul**, reprise du 9 novembre 2026

**Référence examinée :** `#367@a244086cb6458223127f673432cb72d8d5d4365a`, `main@2ce1f5b4f65f435b5ceabec95590cfd8da02f7dc`, même version du code applicatif examiné pour les chemins ci-dessous. **Aucun code, test, configuration CI ni seuil modifié dans cette itération.** Les observations sont statiques, les campagnes de performance Windows et Graphify étant non exécutées ici.

### Vérifications factuelles supplémentaires

1. **Registre RAM exhaustif du point de vue des références, pas des preuves :** le JSON `docs/performance/atlas-ram-inventory-v1.json` contient **50 IDs RAM-01..RAM-50 sans trou ni doublon**, **23 chemins de fichiers propriétaires distincts**, et **23/23 existent à ce HEAD** (vérification de disponibilité via GitHub). Statuts conservés de l'inventaire historique : **16 `measured`**, **4 `instrumented`**, **30 `todo`** ; aucune de ces 16 mentions historiques ne devient un nouveau `PASS` sur le HEAD. `tools/atlas_doctor_lib/ram_inventory.py:275-319` prévoit bien `PARTIAL` tant qu'il reste des items à traiter et refuse d'inférer l'allocation native Qt.
2. **36 OPT historiques :** les lignes `OPT-P0-01..06`, `OPT-P1-07..14`, `OPT-P2-15..24`, `OPT-P3-25..36` existent dans `docs/performance/atlas-full-optimization-backlog-20261030.md:91-150`. Les chiffres initiaux, notamment 307,7 Mio et 22,91 s, restent des **baselines historiques**. Leur résolution code et tests A/B ne sont **pas vérifiés individuellement** par la seule existence du registre.
3. **Différence majeure entre objectif produit et contrôle CI :** `.github/workflows/phase8-memory-benchmark.yml:227-271` traite **Home 100 MB en simple avertissement** et non en échec. Le même workflow, lignes 274-287, impose **220 MB de pic arbre cible avec plafond dur 231 MB** (marge 5 % dans `tools/phase8_memory_tolerance.py`), soit plus strict que le plafond produit ≤250 Mio. **Une CI verte ne prouve pas « Home <100 Mio »** ; inversement les unités/conditions des budgets et du produit doivent rester distinguées. Ne pas affaiblir/renforcer le gate avant arbitrage et A/B. Le nouveau `checkpoint_tree_peak_rss_mb` de C04 est uniquement **diagnostique** et n'entre pas dans le gate actuel.
4. **Dépendances :** `requirements-pyside.txt:6-16` inclut explicitement **PySide6_WebEngine** et **PySide6_Pdf**, hashés, alors que `app/pages/equipment_page.py:15-36,137-158` n'instancie en production **aucun navigateur WebEngine intégré** et ouvre Huzounet via `QDesktopServices`. **Ne pas conclure que les wheels sont dans le bundle final** ni qu'ils sont inutilisés ailleurs : rechercher consommateurs et contenu réel de l'EXE chez #285 avant recommandation de retrait. Il existe une opportunité d'audit du poids de la dépendance, pas de gain prouvé.
5. **Fermeture Qt, vraie limite de la couverture actuelle :** `encyclopedia_page.py:141-145,612-643` bloque sans timeout pour joindre les threads ; `main.py:1840-1858,1896-1931` supprime la page et flush ses `DeferredDelete` au retour Home. `tests/test_encyclopedia_cold_worker_release.py` couvre la **libération finale** quand le worker termine, mais **pas une garantie de réactivité du retour Home pendant une charge lente**. Ce risque P0 est **confirmé en structure**, durée/blocage utilisateur non reproduit ; ne pas annoncer un bug mesuré ou supprimer le join à l'aveugle.
6. **CI HEAD courant :** `Scoped PR Feedback` du run `42650095985` **SUCCESS (feedback stdlib/targeted)**, `Phase Certification` `SKIPPED` (Draft), `Atlas Delivery Guard` du run `42650177689` **FAIL** parce que les 43 exigences ne sont pas clôturées via le format contractuel. Ce dernier garde-fou n'est **pas à contourner** ; un audit en cours ne peut déclarer ses 43 lignes `DONE` ni `DEFERRED` sans preuves et autorisation.

### Qualification initiale de chacune des 31 règles (non certification)

`PARTIAL_STATIC` signifie que **seul un mécanisme ou sous-périmètre** est attesté en lecture, pas une règle entièrement close. `N/A_*` correspond au concept web/serveur strictement sans objet, **pas** à la dispense de tester son équivalent desktop. `UNVERIFIED_RUNTIME`, `OWNER_NOT_RUN` et `NATIVE_NOT_RUN` restent ouverts.

| ID | Qualification actuelle | Source technique/raison | Preuve manquante |
| --- | --- | --- | --- |
| OPTV-001 | PARTIAL_STATIC | `encyclopedia_page.py` (EncyclopediaWarmupView) | État et interaction réellement utiles encore non mesurés |
| OPTV-002 | PARTIAL_STATIC | `image_service.py:104-145` (QImageReader à taille cible) | Autres surfaces et vrais assets Unity non exhaustifs |
| OPTV-003 | PARTIAL_STATIC | `quest_catalog_details.py` (cache signé), providers | Déduplication de chaque source concurrente non démontrée |
| OPTV-004 | PARTIAL_STATIC | `craft_page.py` (minuterie de recherche 120 ms) | Quêtes/Succès et événements obsolètes à retester |
| OPTV-005 | PARTIAL_STATIC | `craft_page.py` (lots bornés et SQLite lazy) | Catalogues Quêtes/Succès/Guide à profiler |
| OPTV-006 | N/A_WEB | Runtime Qt/local, assets empaquetés | Vérifier packaging offline, pas déployer un CDN |
| OPTV-007 | RISK_REVIEW | `encyclopedia_page.py:141-145,612-643`; `world_scan_panel.py:340-388` | Attente `Thread.join()` illimitée à reproduire sur Home |
| OPTV-008 | UNVERIFIED_RUNTIME | `quest_catalog_details.py:215-275` (SELECT direct) | Aucun décompte N+1/EXPLAIN actuel |
| OPTV-009 | N/A_WEB | Pas de livraison du runtime par HTTP | Coûts du launcher à garder chez #285 |
| OPTV-010 | N/A_SERVER | Caches SQLite/LRU locaux existants | Aucun Redis à ajouter |
| OPTV-011 | PARTIAL_STATIC | `requirements-pyside.txt:6-16` (Qt WebEngine et Pdf verrouillés) | Consommateurs réels + contenu bundle non audités |
| OPTV-012 | OWNER_NOT_RUN | Launcher #285, réseau optionnel distinct | Timeout/offline, erreurs natives et rollback à prouver |
| OPTV-013 | N/A_CURRENT_SCOPE | Pas de génération IA distante dans le parcours analysé | Réévaluer uniquement si un service IA actif apparaît |
| OPTV-014 | UNVERIFIED_RUNTIME | `app/core/json_store.py` (écriture atomique unitaire) | Cohérence UI/progression et paires JSON/INI via #331 |
| OPTV-015 | PARTIAL_STATIC | `world_scan_panel.py:960-972`, `image_service.py` | Hors Guides Ganymède ; mémoire image carte/Unity non mesurée |
| OPTV-016 | PARTIAL_STATIC | `main.py:2195-2450` (séquence preload) | CPU/pics, premier clic et bénéfice parallélisme non mesurés |
| OPTV-017 | PARTIAL_STATIC | `quest_catalog_details.py:215-275` (id lookup) | Index réels, EXPLAIN et coûts autres bases non audités |
| OPTV-018 | N/A_BACKEND | Doctor local et journalisation déjà existants | Pas d'OpenTelemetry distant imposé |
| OPTV-019 | N/A_SERVER | SQLite sur poste utilisateur | Reprises/disques Windows à vérifier |
| OPTV-020 | N/A_WEB | Application Qt sans SSR/SSG | Ne pas introduire un serveur de rendu |
| OPTV-021 | PARTIAL_STATIC | `main.py` (services différés) | Imports secondaires et coûts de package non mesurés |
| OPTV-022 | PARTIAL_STATIC | `main.py:1902-2055` (page_factories et lazy) | Non-régression tous onglets et widgets froids non vérifiée |
| OPTV-023 | PARTIAL_STATIC | `craft_page.py:629-685` et lots de résultats | Virtualisation réellement adaptée aux grands catalogues à confirmer |
| OPTV-024 | PARTIAL_STATIC | `quest_catalog_details.py:215-275` (SELECT detail) | Autres parcours SQL/SELECT * non passés en revue complète |
| OPTV-025 | N/A_SERVER | Connexions SQLite courtes (`quest_catalog_details.py`) | Concurrence/locks SQLite à mesurer, pas de pool serveur |
| OPTV-026 | PARTIAL_STATIC | Signatures + caches SQLite/UI existants | Rerenders Qt, retour Home et hit/miss non profilés |
| OPTV-027 | N/A_WEB | Caches versionnés, pas de Cache-Control HTTP | Expiration et invalidation locales à tester |
| OPTV-028 | N/A_SERVER | Mono-poste, stress Doctor multi-processus | 2–8 vrais comptes DOFUS ≠ 8 Atlas offscreen |
| OPTV-029 | N/A_WOFF2 | `app/ui/theme.py` / polices Qt locales | Assets/fonts packaging, fallback et DPI non certifiés |
| OPTV-030 | PARTIAL_STATIC | `benchmark_phase8_memory.py` + Doctor RAM | Mesures réelles native GUI/p95/p99 NON_RUN |
| OPTV-031 | NATIVE_NOT_RUN | Scénarios Windows faible PC exigés par #366 | DPI 100/125/150/200, disque lent, I/O et temps natifs manquent |

### Verdict de reprise et prochain périmètre d'audit

- **Vérifié :** inventaire 43/31/36/50 sur l'existence documentaire, 23/23 owners RAM présents, pratiques réellement déjà en place sur les modules cités, écarts Home/pic dans les contrôles CI, comportement exact du loader Stuffs.
- **Non clos :** audit statique exhaustif de chaque source SQLite, de l'usage des packages WebEngine/Pdf et du packaging, intégration #363, tests de fermeture pendant chargement, distribution Windows/NTFS, tests des 43 exigences, Graphify exact SHA, premier clic utile, p50/p95/p99 et réception 2/4/6/8 vrais comptes DOFUS.
- **Priorité audit suivante** : (1) consommation/visibilité des threads Encyclopédie + test spécifique de non-blocage, (2) provenance et validité des campagnes RAM/C04, (3) dépendances du vrai bundle et outils CI/Doctor, (4) index SQL et retours Home répétés. **Pas de code applicatif dans cette phase.**


## Itération 9 — clôture de l'inventaire **d'audit statique** (9 novembre 2026)

**Champ :** 31 règles web + 36 pistes OPT + 50 items RAM + 12 exigences complémentaires OPTV-032..043, tous réconciliés **en lecture seule** avec les mécanismes identifiés. Audit au `#367@0a7b3d5d3712996a0208340813adea009ffd714c`. Cela **ne clôt pas** les exigences produit ni les tests de performance ; un `measured` historique n'est jamais un PASS récent. Les chemins et commandes sont des preuves de présence et d'intention, pas de résultats d'exécution.

### 36/36 pistes historiques — verdict de tri par cause/propriétaire

| Piste | Statut audit (non livraison) | Mécanisme, propriétaire ou dette constatée | Preuve encore nécessaire |
| --- | --- | --- | --- |
| OPT-P0-01 | HORS_V3_OWNER | Launcher #285; pipeline install/update | Recette Windows EXE, 75–100 %, rollback, SHA |
| OPT-P0-02 | MECANISME_PRESENT | main.py: start_preload séquentiel + _reveal_after_preload | A/B première action utile froide/chaude |
| OPT-P0-03 | HISTORIQUE_GUIDE | Ancien ensure_catalog_manual_view; remplacement #363 Ganymède | Requalifier sur routes Ganymède ; éviter réoptimisation legacy |
| OPT-P0-04 | MECANISME_PRESENT | app/quest_catalog_details.py: phases et détail lazy | Froid/chaud sur même ID, contenu identique |
| OPT-P0-05 | MECANISME_PRESENT | Encyclopédie: Success runtime différé + instrumentable | Tracer détail Succès natif froid/chaud |
| OPT-P0-06 | MECANISME_PRESENT | tools/benchmark_phase8_preload.py | Comparer chemin réel main() vs bench offscreen |
| OPT-P1-07 | MESURE_HISTORIQUE | Pic Guides ancien, source #363 en remplacement | Pic arbre nouveau Guide, mêmes caches/données |
| OPT-P1-08 | ECART_CI_PRODUIT | Home 100 MiB advisory dans workflow RAM | Mesures 10/20/50 retours + objectif <100 MiB |
| OPT-P1-09 | A_REQUALIFIER | Workers preload sérialisés actuellement dans main.py | Attribution PID et pic concurrent natif |
| OPT-P1-10 | A_VERIFIER | Widgets et graphes Guide retenus : cause non attribuée | Weakref/Qt natif, comparer pages après Home |
| OPT-P1-11 | RISQUE_CONFIRME_STATIQUE | encyclopedia_page.py: join() sans timeout pendant destruction | Reproduire freeze Qt sur Home puis corriger dans lot ultérieur |
| OPT-P1-12 | HISTORIQUE_GUIDE | p95/p99 des anciennes routes V5 | Campagne Ganymède 52/52 si applicable, scénario réel |
| OPT-P1-13 | MECANISME_PRESENT | doctor_quick_app_probe: cycles 1/2/3/5/10 | Étendre 20/50 sur protocole séparé mesuré |
| OPT-P1-14 | OUTIL_PRESENT | tools/atlas_perf_attribution.py: SpanAttributor + CPU/IO | Preuve A/B et observer-effect mesuré |
| OPT-P2-15 | MECANISME_PRESENT | app/quest_catalog_details.py: QuestSources disk_backed, source_offsets | Contrôler rebuilds par source et cache hit |
| OPT-P2-16 | MECANISME_PRESENT | SQLite détail Quêtes et signature source | Invalidation/corruption et premier enrichissement froid |
| OPT-P2-17 | MECANISME_PRESENT | DeferredQuestRecord, champs riches à la demande | Parité des étapes/combats selon Guide Ganymède |
| OPT-P2-18 | HISTORIQUE_GUIDE | Ancien vues longues : #363 propriétaire du remplacement | Benchmark cartes Ganymède et widgets actuels uniquement |
| OPT-P2-19 | MECANISME_PRESENT | signature + SQLite détail + LRU borné | Invalidate et relance froide/chaude, ne pas recréer cache |
| OPT-P2-20 | MECANISME_PRESENT | main.py: préload ordonné quests→encyclopedia→craft | CPU/latence premier clic/pic RAM réel |
| OPT-P2-21 | HORS_V3_OWNER | #285 delta launcher | Comparatif réseau+disque, hash et rollback |
| OPT-P2-22 | HORS_V3_OWNER | #285 archive multipart | Coût vérification, suppression de doublon prouvée |
| OPT-P2-23 | HORS_V3_OWNER | #285 parcours launcher Unity | Installation Windows path custom + relance |
| OPT-P2-24 | HORS_V3_OWNER | #285 no-op version identique | Chrono sans réseau, version SHA identique |
| OPT-P3-25 | HORS_V3_OWNER | #285 installation/release | Vraie installation et mise à jour native |
| OPT-P3-26 | NATIF_NON_EXECUTE | Doctor offscreen/un cœur ≠ PC faible natif | CPU/RAM/disque/DPI sur Windows réel |
| OPT-P3-27 | OUTIL_PRESENT | parallel_app.py lance 8 instances Atlas isolées | Mesurer PID, pas confondre avec 8 comptes DOFUS |
| OPT-P3-28 | FONCTION_NON_LIVREE | main.py: show_placeholder Chasse/Ocre, Stuffs externe | Produits vrais vs placeholder ; propriétaire fonctionnel distinct |
| OPT-P3-29 | NATIF_NON_EXECUTE | Qt offscreen et tests unitaires existants | Clic→paint DPI et GPU UI Windows |
| OPT-P3-30 | HISTORIQUE_NON_REVERIFIE | 19 exceptions silencieuses du backlog ancien | Cas source + erreur réellement remontée |
| OPT-P3-31 | GRAPHIFY_NON_EXECUTE | Moteur et workflow Graphify existants | Artefact + impact graph exact SHA, pas de suppression aveugle |
| OPT-P3-32 | OUTIL_PRESENT | tool_catalog AST + Doctor/Graphify existants | Dédup runtime/data à prouver consommateur par consommateur |
| OPT-P3-33 | OUTIL_PRESENT | atlas_perf_attribution, ram_forensics et cost_attribution | Chiffrer coûts CPU/IO per module sans attribution inventée |
| OPT-P3-34 | CI_CIBLEE_VERIFIEE | Scoped PR Feedback PASS au SHA observé | Delivery Guard et Phase toujours bloqués/en Draft |
| OPT-P3-35 | ECART_CI_PRODUIT | CI Home advisory ; pic target 220 MB +5 % hard 231 MB | Clarifier métriques/unités, ne pas modifier seuil sans A/B |
| OPT-P3-36 | NON_CERTIFIE | PR Draft, 43 exigences Delivery Guard ouvertes | Audit commits+Graphify+Windows puis validation finale |

### 50/50 points RAM — inventaire et réévaluation sur code

Le registre canonique historique classe **16 `measured`, 4 `instrumented`, 30 `todo`**. Les 23 chemins propriétaires distincts sont toujours présents. **La colonne « Historique » est copiée du registre source**, tandis que la dernière colonne est la réévaluation actuelle ; certains `todo` possèdent déjà une *instrumentation partielle* à ne pas recréer. Les 50 cases restent à valider dans leurs scénarios propres ; pas de score « 50/50 PASS ».

| Item | Historique | Priorité | Owner canonique | Réévaluation statique / vérification restante |
| --- | --- | --- | --- | --- |
| RAM-01 | MEASURED | P0 | tools/benchmark_phase8_memory.py | Sampler arbre présent ; campagnes au HEAD non exécutées |
| RAM-02 | MEASURED | P0 | tools/doctor_quick_app_probe.py | Cycles et delta Home présents ; <100 MiB non prouvé |
| RAM-03 | MEASURED | P0 | tools/doctor_quick_app_probe.py | Snapshots par module présents ; effet causal non confirmé |
| RAM-04 | INSTRUMENTED | P0 | tools/atlas_doctor_lib/ram_inventory.py | Compteur QWidget Doctor présent ; natif Qt non attribué |
| RAM-05 | INSTRUMENTED | P0 | tools/atlas_doctor_lib/ram_inventory.py | Chaîne owner des widgets Doctor présente ; hors-parent distinct |
| RAM-06 | INSTRUMENTED | P0 | tools/atlas_doctor_lib/ram_inventory.py | États pages LAZY/LOADED Doctor présents |
| RAM-07 | TODO | P0 | tools/doctor_quick_app_probe.py | ram_forensics + tracemalloc et mémoire privée existent PARTIELLEMENT ; heap C++ manque |
| RAM-08 | TODO | P1 | tools/atlas_doctor.py | tracemalloc opt-in dans ram_forensics présent ; sans run |
| RAM-09 | TODO | P1 | tools/atlas_doctor.py | shiboken/Qt native heap hors tracemalloc ; essai manquant |
| RAM-10 | TODO | P1 | main.py | Tests weakref et destruction existent ; cycles Home longs à mesurer |
| RAM-11 | TODO | P1 | main.py | Timers/signaux + delayed delete à recenser ; freeze potentiel join |
| RAM-12 | TODO | P1 | app/ui/world_scan_panel.py | Map génération et résultat différé présents ; test d'IO lent natif à faire |
| RAM-13 | TODO | P1 | app/pages/organizer/organizer_ui.py | Organizer cartes UI : rafraîchissements non profilés |
| RAM-14 | TODO | P1 | app/pages/organizer_page.py | Organizer watcher : propriétaire #325/#398, cycle native non prouvé |
| RAM-15 | MEASURED | P1 | main.py | Réutilisation Home historique ; nouvel A/B non exécuté |
| RAM-16 | TODO | P2 | main.py | Sous-navigation deleteLater dans main ; widget churn à mesurer |
| RAM-17 | MEASURED | P1 | app/ui/world_scan_panel.py | Éviction des pixels Map cachée présente ; RSS native non mesurée |
| RAM-18 | MEASURED | P1 | app/ui/world_scan_panel.py | Résultats carte tardifs filtrés/différés ; robustesse à stresser |
| RAM-19 | TODO | P2 | app/cartography/world_service.py | world_db.py : index SQLite + SELECT * ; EXPLAIN/débit manquants |
| RAM-20 | TODO | P1 | app/modules/encyclopedia/views/guides_view.py | Ancienne fiche Guide, attendre cutover #363 avant verdict |
| RAM-21 | TODO | P0 | app/modules/encyclopedia/views/guides_view.py | 134/267 concerne route legacy ; requalifier nouveau Guide |
| RAM-22 | MEASURED | P1 | app/modules/encyclopedia/services/image_service.py | LRU 8 MiB/64 entrées existant ; vérifier consommateurs Bestiaire/UI |
| RAM-23 | TODO | P1 | app/modules/encyclopedia/views/guides_view.py | Anciennes images de contenu Ganymède hors scope ; Unity/Map distinctes |
| RAM-24 | INSTRUMENTED | P1 | tools/atlas_doctor_lib/ram_inventory.py | QPixmapCache.cacheLimit mesuré, occupation native inconnue |
| RAM-25 | MEASURED | P1 | app/modules/encyclopedia/services/guide_catalog_prebuilt_route.py | Cache ancien itinéraire existant ; maintien selon #363 |
| RAM-26 | MEASURED | P1 | app/quest_catalog_details.py | Quêtes SQLite lazy/offsets existent, pas de gain certifié |
| RAM-27 | TODO | P1 | app/quest_catalog_details.py | LRU de détails 32 présent dans QuestDetails ; hits/retention non mesurés |
| RAM-28 | TODO | P1 | app/modules/encyclopedia/views/encyclopedia_page.py | Succès providers différés ; graphes en vie à mesurer |
| RAM-29 | TODO | P1 | app/modules/encyclopedia/views/encyclopedia_page.py | Graphes _quest_graph réutilisés dans shell ; duplication non prouvée |
| RAM-30 | MEASURED | P2 | app/pages/craft_page.py | Craft release_runtime arrête timers et libère listes/adapters |
| RAM-31 | TODO | P2 | app/pages/craft_page.py | Craft debounce/recherche batch déjà présents ; no need duplicate |
| RAM-32 | TODO | P2 | tools/doctor_quick_app_probe.py | Bestiaire : tester fonctionnalité réelle vs onglet/placeholder |
| RAM-33 | MEASURED | P2 | app/pages/equipment_page.py | Stuffs ouvre URL externe : aucun Chromium embedded runtime |
| RAM-34 | TODO | P2 | app/ui/theme.py | theme.py Qt QSS volumineux, aucun profilage paint récent |
| RAM-35 | TODO | P0 | app/startup_cache_warmup.py | Préload séquentiel existant, peak par PID encore à mesurer |
| RAM-36 | TODO | P1 | launch.py | EXE propre Windows dépend de #285 / test natif non exécuté |
| RAM-37 | TODO | P0 | tools/benchmark_phase8_memory.py | Working Set et PrivateUsage présents via ram_forensics ; partage/GPU absent |
| RAM-38 | MEASURED | P1 | tools/benchmark_atlas_exhaustive.py | Benchmark exhaustif existe ; nouvelles routes Ganymède à profiler |
| RAM-39 | MEASURED | P1 | tools/atlas_doctor_lib/parallel_app.py | 8 processus Atlas offscreen disponibles, ≠ 8 DOFUS |
| RAM-40 | TODO | P1 | tools/doctor_quick_app_probe.py | Doctor quick cycles max 10 ; essai 20/50 manquant |
| RAM-41 | TODO | P2 | tools/atlas_doctor.py | Affinité 1 coeur disponible, ≠ PC réel lent/DPI |
| RAM-42 | TODO | P1 | tools/atlas_doctor_lib/ram_inventory.py | Cache LRU et owners visibles ; hit/miss global non comparé |
| RAM-43 | MEASURED | P1 | tools/atlas_doctor.py | CI exact SHA + statuts honnêtes ; tests Windows manquants |
| RAM-44 | TODO | P2 | docs/performance/atlas-full-optimization-backlog-20261030.md | Aucun retrait avant consommateurs Graphify/packaging |
| RAM-45 | TODO | P2 | app/pages/home_page.py | Services Home/network en différé ; RAM inactive non attribuée |
| RAM-46 | MEASURED | P2 | main.py | Persistance/identités préservées par contrat ; conflit #331 encore à tester |
| RAM-47 | TODO | P2 | tools/doctor_quick_app_probe.py | GC/Home et heap CPython observables, interprétation/native à confirmer |
| RAM-48 | MEASURED | P2 | app/modules/encyclopedia/services/image_service.py | QImageReader.setScaledSize + LRU existants, Unity/Map séparés |
| RAM-49 | TODO | P3 | app/ui/theme.py | Polices ressources QSS, pas de profilage natif |
| RAM-50 | TODO | P3 | launch.py | Launcher RAM owner #285 ; installation native NON_RUN |

### 43/43 exigences OPTV — frontière audit / livraison

- `OPTV-001..031` (**31/31**) : état et preuve manquante **qualifiés individuellement** dans l'itération 7 ; les N/A « web » doivent conserver leurs équivalents desktop appropriés, sans nouvelle infrastructure.
- `OPTV-032..040` (**9 exigences code**) : aucune ne doit recevoir `DONE` à partir d'un inventaire, d'un plan, de 3 tests C04 ou d'un mécanisme ancien. Pistes : caches/Qt/startup, requêtes, images Unity hors Guides Ganymède, workers, règles futures, perf Doctor, tests/CI.
- `OPTV-041..042` (**2 exigences manuelles**) : Windows faible PC, DPI, 2/4/6/8 DOFUS et vraie distribution/livraison ; **NON_RUN** par cet audit et indispensables avant réception.
- `OPTV-043` (**1 exigence documentation**) : les 31/36/50, 20 constats, 5 notes et propriétaires sont désormais inventoriés ; l'exigence n'est **pas DONE**, car elle réclame également preuve des écarts traités et réévaluation avec mesures.
- **Total = 31 + 9 + 2 + 1 = 43**, IDs source inchangés, aucun report autorisé inventé. `Atlas Delivery Guard` est bloquant tant que les 43 états obligatoires ne sont pas valides ; ne pas lui fournir de rapport fictif.

### Constats critiques priorisés — audit prêt pour décision de développement ultérieure

| Priorité | Constat | Niveau de preuve | Décision après audit |
| --- | --- | --- | --- |
| P0 | `EncyclopediaPage` sur destruction Qt attend ses workers par `Thread.join()` non borné (`encyclopedia_page.py:141-145,612-643`), alors que retour Home détruit la page (`main.py:1840-1856,1896-1930`). | **Chemin de blocage confirmé statiquement** ; durée de gel et incidence non mesurées | Ajouter un test de réactivité Qt avec worker lent + preuve de libération sûre ; corriger ensuite sans data race |
| P0 | Démarrage utilisateur réel (`main.py:2815-2860`, fenêtre masquée avant Quêtes) ≠ `doctor_quick_app_probe.py:260-300` (`window.show()` immédiat) et benchmark mémoire offscreen. | **Écart de scénario confirmé** ; premier clic utile native non mesuré | Deux métriques distinctes + chronos froid/chaud et lancement réel |
| P0 | L'objectif Home `<100 MiB` n'est **qu'advisory** dans le workflow mémoire ; le pic workflow cible `220 MB` avec limite `231 MB`, plus strict que l'objectif produit `≤250 MiB`. | **Configuration CI vérifiée** (`.github/workflows/phase8-memory-benchmark.yml:227-287`) | Distinguer unités / seuils produits et gates ; décisions sur preuve et non sur un simple PASS CI |
| P1 | `world_db.py:362-407,570-605` et `_map_select_clause()` utilisent `SELECT *`/`maps.*`. Mais index `map_views(parent_view_key)`, `maps(view_key,x,y)` et autres existent (`:185-189`) ; connexions SQLite sont fermées via `connection_scope()` (`:61-82`). | **Requêtes confirmées, aucun coût excessif confirmé** | EXPLAIN/compteur tailles lignes + profile avant une réduction de colonnes ; ne pas ajouter de pool serveur |
| P1 | `requirements-pyside.txt:6-16` inclut WebEngine/Pdf mais `equipment_page.py:20-38,91-103,137-160` n'instancie pas Chromium en production. | **Présence dépendances/verrou + absence dans Stuffs** confirmées ; autres consommateurs/bundle non prouvés | Inventaire packaging réel #285, source → wheel → bundle → taille installée avant toute suppression |
| P1 | Historiques `OPT-P0-03,P1-12,P2-18` et `RAM-20,21,23,25,38` concernent des fiches/images de parcours Guide anciens ; #363 Ganymède est encore Draft. | **Risque de travail inutile** | Ne pas optimiser/détruire les anciens contenus : requalifier juste après cutover certifié #363, préserver pictos Unity/Bestiaire/Map |
| P1 | `ram_forensics.py`, `atlas_perf_attribution.py`, `doctor_quick_app_probe.py` existent et offrent `tracemalloc`, private commit, working set, CPU/IO/attribution. | **Instrumentation confirmée** ; résultats Windows non exécutés | Réutiliser les modes off/on distincts ; combler seulement le vrai manque d'attribution native Qt |
| P1 | `main.py:1650-1705` montre encore des pages `Chasse au trésor`/`Ocre` en préparation, `equipment_page.py` ouvre Stuffs à l'extérieur. | **Limites fonctionnelles confirmées** | Distinguer route navigable de fonctionnalité livrée ; transférer développement au propriétaire produit, pas à V3 |
| P2 | Les caches LRU, chargements différés, Qt cleanup, retry, scopes Doctor/Graphify et outils 8 Atlas offscreen sont déjà présents. | **Existence confirmée** | Conserver et mesurer ; aucun framework/orchestrateur/caches doublons |

**Conclusion d'audit au HEAD initial 0a7b3d5d3712996a0208340813adea009ffd714c: INVENTAIRE_STATIQUE_CLOS, PERFORMANCE_NON_CERTIFIEE, DEVELOPPEMENT_HORS_PERIMETRE_ACTUEL.** Aucun bench, Graphify ou test Windows/DOFUS nouveau n'a été lancé au cours de cette itération. Les preuves de certification et l'implémentation doivent être traitées séparément, avec des SHA ultérieurs. Les constats sont prêts à être priorisés sans faux `DONE`.

## Itération 10 — registre des 20 défauts/risques de la PR et de ses commits (9 novembre 2026)

**But :** consigner les vingt points signalés après la revue des **20 commits** de `#367@5d46d6499de75eae4c1d2c9d693ec97d9b7c0aa7` pour qu'ils ne soient pas perdus au moment des futurs lots. Les libellés **CONFIRMED** indiquent un état vérifié (document, configuration ou chemin de code) ; **NOT_RUN** et **IMPACT_UNKNOWN** n'indiquent pas un bug runtime démontré. **L'ajout de cette section est seulement documentaire, sans développement applicatif ni assouplissement CI.**

**État au démarrage de ce registre :** PR OPEN/Draft, 0 commit derrière `main`, **5 fichiers différant de main** (2 docs, 1 index IA, 1 instrumentation de benchmark et 1 fichier de tests). La revue commit par commit est également consignée dans la [discussion #367](https://github.com/r9327/Dof-Atlas/pull/367#issuecomment-6745470822). Les commits de la colonne « commits » sont les révisions qui **documentent, introduisent ou rendent visibles** un constat, pas nécessairement sa cause dans l'application.

**Statut des lignes :** `OPEN_AUDITED` (inventorié, non résolu). Les conclusions de diagnostic/revue ne doivent pas être promues automatiquement en `DONE` contractuel sur l'issue #366.

| ID | Priorité | Nature | Niveau de preuve | Défaut/risque vérifié | Commits concernés | Travail à prévoir (pas exécuté) | Critère de résolution |
| --- | --- | --- | --- | --- | --- | --- | --- |
| D367-01 | P0 | PR | CONFIRMED | Le périmètre livré est majoritairement documentaire : aucune amélioration runtime prouvée ; C04 est seulement une instrumentation. | `[895cfa6e](https://github.com/r9327/Dof-Atlas/commit/895cfa6e)`, `[f15a5f2f](https://github.com/r9327/Dof-Atlas/commit/f15a5f2f)`, `[9008833b](https://github.com/r9327/Dof-Atlas/commit/9008833b)`, `[4886d6c8](https://github.com/r9327/Dof-Atlas/commit/4886d6c8)` | Décider si #367 reste une PR d'audit ou devient une PR de réalisation par lots. Ne pas présenter le plan comme un gain. | Un objectif de PR non ambigu, liste de livrables/mesures exact-SHA distincte des plans. |
| D367-02 | P0 | APP-RISK | CONFIRMED_STATIC / NOT_REPRODUCED | `encyclopedia_page.py:141-145,612-643` appelle `Thread.join()` sans borne ; destruction différée sur Home via `main.py`. Gel possible, non mesuré. | `[7e24d914](https://github.com/r9327/Dof-Atlas/commit/7e24d914)`, `[8639baff](https://github.com/r9327/Dof-Atlas/commit/8639baff)`, `[b7e91407](https://github.com/r9327/Dof-Atlas/commit/b7e91407)` | Tester fermeture/Home pendant un worker volontairement lent et protéger les signaux/références avant de modifier la jonction. | Qt non bloqué, worker se termine, view collectée, pas de signal vers QObject détruit. |
| D367-03 | P0 | BENCH-GAP | CONFIRMED_STATIC | `main.py` laisse Home masquée jusqu'au préload Quêtes ; `doctor_quick_app_probe.py:260-300` affiche `AtlasWindow` immédiatement. Les chronos ne modélisent pas exactement le premier usage réel. | `[4637fbf5](https://github.com/r9327/Dof-Atlas/commit/4637fbf5)`, `[b7e91407](https://github.com/r9327/Dof-Atlas/commit/b7e91407)`, `[9a019b78](https://github.com/r9327/Dof-Atlas/commit/9a019b78)` | Conserver le protocole offscreen et ajouter une métrique distincte de première action réelle en démarrage normal. | Cold/warm, premier vrai contenu et clic→paint tracés avec SHA/hardware. |
| D367-04 | P0 | CI-POLICY | CONFIRMED | Dans `phase8-memory-benchmark.yml:227-271`, Home ≥100 MB produit un avertissement, pas un FAIL ; le pic est ciblé à 220 MB avec un plafond dur à 231 MB, à distinguer de l'objectif produit ≤250 Mio. | `[b7e91407](https://github.com/r9327/Dof-Atlas/commit/b7e91407)`, `[9a019b78](https://github.com/r9327/Dof-Atlas/commit/9a019b78)` | Documenter l'écart objectifs produit/gate et décider de sa politique après mesures comparables, sans affaiblir silencieusement la CI. | État Home PASS/WARN/FAIL explicite, unités et protocole cohérents, tests de seuil. |
| D367-05 | P0 | PR-GATE | CONFIRMED | Issue #366 : 43 exigences ; Delivery Guard FAIL, Phase Certification SKIPPED sur PR Draft. Aucun rapport complet autorisé. | `[a244086c](https://github.com/r9327/Dof-Atlas/commit/a244086c)`, `[b7e91407](https://github.com/r9327/Dof-Atlas/commit/b7e91407)`, `[9a019b78](https://github.com/r9327/Dof-Atlas/commit/9a019b78)` | Clôturer exigences avec preuves ou report autorisé par #366 ; ne pas créer de faux DONE/DEFERRED. | Delivery Guard SUCCESS réel et Phase Certification exacte-SHA lorsque la PR est prête. |
| D367-06 | P1 | MEASURE-GAP | PARTIAL_STATIC | `ram_forensics.py` fournit déjà `tracemalloc`, private commit et Working Set ; la rétention native Qt/shiboken, les pixmaps GPU et owners ne sont pas attribués. | `[b7e91407](https://github.com/r9327/Dof-Atlas/commit/b7e91407)`, `[0a7b3d5d](https://github.com/r9327/Dof-Atlas/commit/0a7b3d5d)`, `[9a019b78](https://github.com/r9327/Dof-Atlas/commit/9a019b78)` | Réutiliser Doctor, mesurer séparément allocations Python et heap C++/Qt sur Windows avant toute optimisation. | Rapport natif/CPython non additionné artificiellement et référence par phase. |
| D367-07 | P1 | EXECUTION-GAP | NOT_RUN | Pas de campagne exacte-SHA prouvée sur Windows desktop/EXE et PC faible ; le Qt offscreen ne constitue pas cette preuve. | `[a244086c](https://github.com/r9327/Dof-Atlas/commit/a244086c)`, `[b7e91407](https://github.com/r9327/Dof-Atlas/commit/b7e91407)`, `[9a019b78](https://github.com/r9327/Dof-Atlas/commit/9a019b78)` | Utiliser la recette native avec matériel/DPI/SSD déclarés et artefacts. | Temps/RAM/CPU/IO, incidents, SHA, paramètres et environnement reproductibles. |
| D367-08 | P1 | EXECUTION-GAP | NOT_RUN | p95/p99 et gels Qt sur les routes actuelles ne sont pas certifiés au HEAD ; anciennes valeurs de Guide restent historiques. | `[4637fbf5](https://github.com/r9327/Dof-Atlas/commit/4637fbf5)`, `[7e24d914](https://github.com/r9327/Dof-Atlas/commit/7e24d914)`, `[9a019b78](https://github.com/r9327/Dof-Atlas/commit/9a019b78)` | Mesurer parcours utilisateur froid/chaud après stabilisation Ganymède ; qualifier les valeurs extrêmes. | Distribution p50/p95/p99 et blocages par étape/module avec baseline comparable. |
| D367-09 | P1 | EXECUTION-GAP | PARTIAL_STATIC / NOT_RUN | `doctor_quick_app_probe.py` limite `cycles` à 1/2/3/5/10 ; aucune preuve 20/50 retours Home et d'absence de rétention native. | `[7e24d914](https://github.com/r9327/Dof-Atlas/commit/7e24d914)`, `[b7e91407](https://github.com/r9327/Dof-Atlas/commit/b7e91407)`, `[9a019b78](https://github.com/r9327/Dof-Atlas/commit/9a019b78)` | Prévoir campagne de stabilité 20/50 cycles séparée des tests rapides, sans imposer FULL à chaque push. | Pente RSS/Qt widgets/threads et plateau Home vérifiés, données utilisateur préservées. |
| D367-10 | P1 | GRAPH-GAP | NOT_RUN | Graphify exact-SHA est disponible via workflow à la demande mais aucun artefact exact-SHA avec fraîcheur validée n'a été présenté pour #367. | `[d4b31dd2](https://github.com/r9327/Dof-Atlas/commit/d4b31dd2)`, `[0a7b3d5d](https://github.com/r9327/Dof-Atlas/commit/0a7b3d5d)`, `[9a019b78](https://github.com/r9327/Dof-Atlas/commit/9a019b78)` | Déclencher Graphify approuvé au HEAD de la PR avant toute suppression/refonte structurelle. | Graphe lié au SHA et test consommateurs/inversions sur zones modifiées. |
| D367-11 | P1 | BUNDLE-GAP | CONFIRMED_DEPENDENCIES / UNVERIFIED_USE | `requirements-pyside.txt` verrouille PySide6_WebEngine/Pdf ; `equipment_page.py` ouvre Huzounet en externe. Autres usages/poids réellement embarqué inconnus. | `[b7e91407](https://github.com/r9327/Dof-Atlas/commit/b7e91407)`, `[9a019b78](https://github.com/r9327/Dof-Atlas/commit/9a019b78)` | Vérifier imports transitifs, dépendances et contenu du bundle via #285 avant retrait. | Inventaire source→wheel→EXE, taille et tests si suppression justifiée. |
| D367-12 | P1 | SQL-GAP | CONFIRMED_QUERY / IMPACT_UNKNOWN | `world_db.py` utilise `SELECT *`/`maps.*`, mais possède des index et ferme les connexions ; aucun ralentissement démontré. | `[f4ba9531](https://github.com/r9327/Dof-Atlas/commit/f4ba9531)`, `[b7e91407](https://github.com/r9327/Dof-Atlas/commit/b7e91407)`, `[9a019b78](https://github.com/r9327/Dof-Atlas/commit/9a019b78)` | Mesurer latence/volume/EXPLAIN sur données réelles avant de réduire les projections. | Plan de requête, coût/temps avant-après, résultat identique. |
| D367-13 | P1 | BENCH-GAP | PARTIAL_DELIVERED / NOT_RUN_NATIVE | Commit C04 ajoute les pics des checkpoints RAM en diagnostic ; `peak_tree_rss_mb` de référence et le gate ne changent pas, pas d'A/B Windows. | `[9008833b](https://github.com/r9327/Dof-Atlas/commit/9008833b)`, `[4886d6c8](https://github.com/r9327/Dof-Atlas/commit/4886d6c8)`, `[a244086c](https://github.com/r9327/Dof-Atlas/commit/a244086c)` | Comparer les deux mesures sur campagne Windows avec child PIDs et raison d'écart, puis décider s'il faut ajuster l'agrégateur. | Aucun pic sous-estimé non expliqué ; tests de temps/processus comparables. |
| D367-14 | P1 | MULTI-ACCOUNT-GAP | SIMULATOR_ONLY | `parallel_app.py` simule 8 processus Atlas offscreen, pas 2/4/6/8 comptes réels DOFUS Unity. | `[f4ba9531](https://github.com/r9327/Dof-Atlas/commit/f4ba9531)`, `[b7e91407](https://github.com/r9327/Dof-Atlas/commit/b7e91407)`, `[9a019b78](https://github.com/r9327/Dof-Atlas/commit/9a019b78)` | Ne pas convertir le PASS 8 Atlas en preuve multi-comptes ; garder la recette Windows DOFUS indépendante. | Tests 2/4/6/8 comptes natifs, latence/CPU/RAM et stabilité. |
| D367-15 | P2 | PR-SCOPE | CONFIRMED | Deux commits de code/tests RAM (`9008833b`, `4886d6c8`) ont été ajoutés sans mandat de développement dans une phase attendue en audit. | `[9008833b](https://github.com/r9327/Dof-Atlas/commit/9008833b)`, `[4886d6c8](https://github.com/r9327/Dof-Atlas/commit/4886d6c8)` | Décider explicitement de les conserver dans #367 ou de les déplacer dans une PR distincte, sans réécrire les commits par défaut. | Périmètre corrigé et décision tracée ; aucun changement applicatif indu pendant audit. |
| D367-16 | P2 | DOC-CONSISTENCY | CONFIRMED | Des passages historiques du plan indiquent `PLAN_ONLY/NOT_IMPLEMENTED`, alors qu'un petit C04 diagnostic a été ajouté ensuite. Leur portée temporelle n'est pas partout explicite. | `[4637fbf5](https://github.com/r9327/Dof-Atlas/commit/4637fbf5)`, `[a244086c](https://github.com/r9327/Dof-Atlas/commit/a244086c)`, `[9a019b78](https://github.com/r9327/Dof-Atlas/commit/9a019b78)` | Marquer les états anciens comme snapshots ; conserver un état courant unique et daté en tête de PR. | Lecteur distingue facilement historique, C04 partiel et certification NOT_RUN. |
| D367-17 | P2 | PR-HYGIENE | CONFIRMED_INFO / NON_BLOCKING | Historique audit : 20 commits dont nombreux ajouts documentaires ; lisibilité perfectible, pas un défaut fonctionnel. Merge main à deux parents doit être préservé. | `[895cfa6e..5d46d649](https://github.com/r9327/Dof-Atlas/commit/895cfa6e..5d46d649)` | Garder tableau de correspondance commits↔observations ; envisager squash seulement si demandé et sans casser preuves SHA. | Historique intelligible ; aucune force-update non autorisée. |
| D367-18 | P2 | OWNERSHIP | PARTIAL_STATIC | Certaines optimisations historiques visent les images et cartes des Guides anciens ; #363 Ganymède doit remplacer les parcours et ses Guides n'ont pas d'images de contenu. | `[167f9fbe](https://github.com/r9327/Dof-Atlas/commit/167f9fbe)`, `[4e38e078](https://github.com/r9327/Dof-Atlas/commit/4e38e078)`, `[9a019b78](https://github.com/r9327/Dof-Atlas/commit/9a019b78)` | Après cutover certifié #363, réévaluer ces optimisations ; préserver icônes Unity, Bestiaire et Map. | Backlog legacy retiré/requalifié sur état réel sans duplications. |
| D367-19 | P2 | OVERENGINEERING-RISK | PREVENTION / NO_DUPLICATE_PROVEN | Doctor, Graphify, LRU images, caches SQLite et profils RAM sont déjà présents ; risque futur de refaire les mêmes fonctions, aucun doublon nouveau démontré ici. | `[d4b31dd2](https://github.com/r9327/Dof-Atlas/commit/d4b31dd2)`, `[0a7b3d5d](https://github.com/r9327/Dof-Atlas/commit/0a7b3d5d)`, `[9a019b78](https://github.com/r9327/Dof-Atlas/commit/9a019b78)` | Mesurer et réutiliser les outils existants ; demander preuve consommateur/impact avant refonte. | Aucun deuxième orchestrateur, cache ou profiler sans gain démontré. |
| D367-20 | P2 | REVIEW-GAP | CONFIRMED_STATUS | Aucune revue ni thread GitHub enregistrés sur #367 à la date de vérification ; Draft non certifiée. | `[9a019b78](https://github.com/r9327/Dof-Atlas/commit/9a019b78)`, `[5d46d649](https://github.com/r9327/Dof-Atlas/commit/5d46d649)` | Obtenir revue structurée et répondre aux éventuels threads avant passage Ready. | Avis enregistré et 0 thread bloquant non résolu avant fusion. |

### Ordre de travail recommandé (après la phase d'audit, sur mandat explicite)

1. **Préparer la PR :** D367-15 (deux commits de code hors mandat), D367-16 (états historiques), D367-01 (nature exacte de #367) ; D367-17/20 sont de l'hygiène de revue, pas de nouvelles fonctionnalités.
2. **Sécurité/réactivité & métrologie fiables :** D367-02 (Home/Qt), D367-03 (premier contenu réel), D367-04 (politique RAM), D367-13 (provenance pic) ; priorité aux tests qui séparent un risque supposé d'un bug confirmé.
3. **Campagnes ciblées et analyse native :** D367-06..10, D367-14 ; utiliser Doctor/Graphify déjà présents et publier les artefacts exact-SHA. Tests des 2–8 vrais comptes DOFUS distincts des 8 Atlas offscreen.
4. **Optimisations seulement après preuve :** D367-11/12 (WebEngine/Pdf et SQL), D367-18/19 (Guides Ganymède et non-duplication). Garder les owners #285/#363/#358/#365.
5. **Certification finale :** D367-05, puis D367-20 ; Delivery Guard **43 exigences** et Phase Certification exact-SHA, pas de certificat de substitution basé sur un simple audit.

### Interdictions de clôture artificielle

- Ne pas réécrire/squasher les **20 commits existants** ni déplacer C04 sans demande explicite.
- Ne pas noter « 20/20 défauts corrigés » : **20/20 inventoriés, 0/20 déclarés résolus par cette documentation**.
- Ne pas assimiler une exécution Scope Feedback à des performances Windows, une note 18/20 ou une preuve multi-comptes.
- Ne pas relancer FULL/Graphify systématiquement pour des changements de documentation ; se fier au routage CI existant.

**Verdict du registre : AUDIT_DES_20_POINTS_PUBLIE / PR_DRAFT_NON_CERTIFIÉE / CORRECTIFS_NON_COMMENCÉS.**
