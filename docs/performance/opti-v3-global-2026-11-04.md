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
