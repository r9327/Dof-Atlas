# DOFUS ATLAS — Opti V3 : plan de travail contractuel
_Date : 2026-11-04 — source : issue #366 — état : cadrage uniquement, **aucune amélioration déclarée livrée**._

## Résultat attendu

Réduire le temps jusqu'au premier contenu réellement utilisable et les blocages Qt dans **tous les modules existants** ; conserver la RAM et les coûts CPU/IO bornés ; rendre les règles anti-régression **applicables aux prochaines modifications et fonctionnalités**, à travers les propriétaires de règles/Doctor/CI déjà présents. L'utilisateur demande une Opti V3 globale : **pas de restriction par un classement P0/P1/P2**. L'implémentation est organisée en lots cohérents vérifiables, pas en grandes réécritures aveugles.

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

## Découpage de développement : une PR, lots indépendants

**A. Baseline et traçabilité** — doctor/graph/QA exact SHA, état 31/36/50, baseline froide/chaude, synthèse des coûts et des chemins. Préserver les preuves et les budgets.

**B. Accès données + caches** — index/SQLite/JSON, requêtes N+1 et `SELECT *`, signatures, tailles, corruption sans masquer, parité persistance.

**C. UI + ressources** — Qt, virtualisation, rendu visible, annulation de résultats obsolètes, images, Unity, tailles, FPS native seulement en validation Windows.

**D. Démarrage + concurrence + mémoire** — cold/warm, préload utile, workers, teardown, mémoire par process, réouvertures, budget Guide/Home.

**E. Garde-fous du futur code** — canonique performance, Doctor/Integrity existants, tests contractuels ciblés, audit de cohérence des règles.

**F. Recette finale** — audit chaque commit et PR globale, 31/36/50 sans omission, Doctor ciblé/FAST/Graphify exact SHA et Windows natif, puis une certification finale sur HEAD Ready.

## Non-chevauchement avec les PR actives

- **#285** Launcher / installation différentielle : métriques et intégration uniquement, pas de code launcher concurrent.
- **#325** Organizer / Macro / Miroir : tests d'impact et interfaces communes, pas de modification fonctionnelle des macros.
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
