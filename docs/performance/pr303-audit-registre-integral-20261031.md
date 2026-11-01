# PR #303 — Registre intégral des anomalies et suites de l'audit Doctor

> **Document de suivi, PAS certification ni autorisation de suppression.** Périmètre relevé le 31 octobre 2026, instantané PR `7e2ebb04f2cbb2537d275d28ea4955d39f1f48ad` (388 commits). Les chiffres détaillés de candidats AST/JSON/assets viennent du scan **antérieur** `613ec84` ; la projection Graphify précédente vient de `f9d25c7`; le graphe exact-SHA observé sur `c04c813` a 1 198 fichiers/16 787 nœuds/48 375 liens et une conclusion sémantique **REVIEW**. Les candidats anciens ne sont pas réputés encore présents ni des bugs confirmés.

## Fichiers du registre et mode d'emploi

- [Inventaire détaillé machine, toutes les entrées disponibles](pr303-audit-candidats-20261031.json) : `ast_duplicate_groups[0..212]`, `silent_exception_candidates[0..252]`, `unity_style_candidates[0..14]`, `no_static_consumer_candidates[0..33410]`, exemples de références, cycles, nœuds et couplages. `ASSET-00001` correspond à l'index `0` des ressources. **Pas de suppression automatique.**
- [Historique complet des commits](pr303-audit-commits-20261031.json) : `388/388` SHA + titre, vérification patch automatisée `387/388` au point de capture antérieur, **revue humaine individuelle non effectuée**, y compris merges et reverts. Le présent commit documentaire sera additionnel.
- [Plan des 36 optimisations](atlas-full-optimization-backlog-20261030.md) et [50 chantiers RAM](atlas-ram-inventory-v1.json) : registres existants conservés, repris ci-dessous pour liaison directe.
- Les 582 références non résolues et les 537 références classées dangereuses/ambiguës par le résolveur **n'ont que 40 exemples exportés pour chaque famille**. Export exhaustif des 542 et 497 restants = **BLOCKED / preuve manquante** ; ne pas inventer de noms de fichiers.

## Règles de classement et de clôture

| Statut | Signification |
|---|---|
| `CONFIRMED_OPEN` | Échec reproduit ou budget mesuré non atteint et non corrigé |
| `FIX_COMMITTED_PROOF_PENDING` | Code corrigé sur une révision donnée ; preuve finale sur le HEAD encore non validée |
| `REVIEW` | Candidat statique/heuristique ; aucun bug confirmé ni suppression autorisée |
| `NOT_RUN` / `BLOCKED` | Contrôle nécessaire ou source exhaustive indisponible |
| `VERIFIED` | Correctif + test applicable PASS + preuve Git SHA + mesure avant/après si performance |

## P0 — Bugs, preuves de livraison et vérification FULL

| ID | Sujet | Statut au relevé | Résultat exigé pour clore |
|---|---|---|---|
| P0-01 | Route portable Sylvestre : précompilation Windows rejetée (`RuntimeError`), `Path.as_uri()` sur SQLite relatif | `FIX_COMMITTED_PROOF_PENDING` — `7e2ebb0`, deux `resolve()` + test | Installer/EXE réel et build routes PASS sur nouveau SHA, contrat read-only et SHA conservés |
| P0-02 | Réelle installation, update, rollback, prérequis, SHA256 et lancement sous Windows | `NOT_RUN`/échec sur SHA précédent ; propriétaire distinct Launcher V2 #285 | Preuve Windows vierge, delta, choix dossier et parcours installation→lancement, pas seulement contrat mock |
| P0-03 | JSON/ressources/liens exhaustifs sur HEAD : dernière collecte `--with-json --with-links --links-all` ancienne Draft | `NOT_RUN` sur HEAD `7e2ebb0` | Refaire scanner exhaustif, publier inventaire exact-SHA et vérifier les consommateurs runtime |
| P0-04 | 582 références non résolues, 537 suspectes : seulement 40 exemples de chaque type exportés | `BLOCKED` quant au détail complet | Ré-exporter la totalité via le moteur existant et qualifier chaque chemin par génération/scope/consommateur |
| P0-05 | Audit de chaque commit : 388 SHA inventoriés, 387 patches analysés automatiquement au SHA `c04c813` | `REVIEW`, revue manuelle 388/388 `NOT_RUN` | Revue des 388 diffs individuels (y compris deux merges et quatre reverts), risques/tests et verdict avant fusion |
| P0-06 | 36 optimisations sans matrice exhaustive action→commit→test→mesure→verdict | `REVIEW` | Lier toute action à preuve et fermer seulement si objectifs réels atteints |

## P1 — Performances et runtime mesurés (Qt offscreen Windows ; pas PC client)

| ID | Problème | Valeur observée sur `c04c813` | État / preuve attendue |
|---|---|---:|---|
| P1-01 | RSS après retour Home | **115,73 Mio** | `CONFIRMED_OPEN`, objectif **<100 Mio** : −15,73 Mio minimum |
| P1-02 | Pic processus-arbre Guides | **247,61 Mio** | Budget ≤250 Mio tenu mais **2,39 Mio** de marge : optimiser et rebench |
| P1-03 | Préchargement Guides | **13,898 s** | `REVIEW` performance et pipeline startup |
| P1-04 | Préchargement navigation complète | **6,795 s** | Comparer aux mêmes scénarios et au vrai contenu utilisable |
| P1-05 | Ouverture Guides p50/p95/p99 | **103,25 / 284,54 / 309,39 ms** | Outliers à profiler par carte/Guide |
| P1-06 | Gels Qt ≥250ms | **0** sur dernier 52/52, **6** sur un précédent | Variabilité, pas de conclusion « aucun gel » sans répétitions |
| P1-07 | 27 visites de placeholders sur 60 parcours | **33 fonctions réelles + 27 placeholders** | Ne jamais qualifier les placeholders comme modules fonctionnels |
| P1-08 | 8 processus Atlas simultanés | PASS par CI | Ce ne sont pas 8 clients du jeu DOFUS ; test terrain `NOT_RUN` |
| P1-09 | Contrôles bas niveau heap C++/Qt, Private Bytes, GPU, DPI et machine faible | `NOT_RUN`/partiellement instrumentés | Exécuter scénarios natifs et attribuer les rétentions, non la RSS seule |
| P1-10 | Preuve avant/après répétée homogène | Ancienne comparaison ≈512 ms directionnels sur une paire | `REVIEW`, ≥3 comparaisons appariées sur même runner |

## P2 — Architecture, dépendances, duplications, données

| ID | Famille | Quantité / détail | Statut |
|---|---|---|---|
| P2-01 | Groupes AST de corps identiques | 213 groupes / 706 occurrences ; tests dominants ; logique app à évaluer | `REVIEW` ; `D-001..D-213` ci-dessous et JSON complet |
| P2-02 | Exceptions potentiellement avalées | 253 sites | `REVIEW` ; `E-001..E-253` ci-dessous |
| P2-03 | Ressources sans consommateur **statique prouvé** | 33 411 chemins dans le JSON brut (identifiants `ASSET-00001..ASSET-33411`) | `REVIEW` ; ressource morte non établie |
| P2-04 | Références non résolues | 582, 40 exemples explicitement disponibles | `REVIEW` ; reste `BLOCKED` |
| P2-05 | Références ambiguës/dangereuses pour l'auditeur | 537, 40 exemples explicitement disponibles | `REVIEW` ; reste `BLOCKED` |
| P2-06 | Ressources liées uniquement par basename possible | 111 | `REVIEW` |
| P2-07 | Collisions d'ID dans deux rapports JSON historiques | 2 fichiers, pas les données Quêtes métier | `REVIEW` |
| P2-08 | Graphe AST exact-SHA sur `c04c813` | 1198/1198 Python, 16787 nœuds, 48375 relations ; `REVIEW` sémantique | `REVIEW` même si workflow PASS |
| P2-09 | Cycles de dépendances d'import | 4 cycles observés par l'ancien Graphify | `REVIEW` ; un cycle statique ≠ crash runtime |
| P2-10 | Nœuds sans liaison Graphify | 6 orphelins sur ancienne carte | `REVIEW` (scripts d'entrée possibles) |
| P2-11 | Fichiers sans arête import statique | 8 fichiers applicatifs | `REVIEW` ; modules dynamiques et subprocess possibles |
| P2-12 | Faible connectivité et couplage | 345 candidats faibles, 118 communautés isolées, 50 fichiers à fort fanout (anciens rapports) | `REVIEW` ; pas de refactor sans consommateur prouvé |
| P2-13 | Doublons sémantiques potentiels Guides/Quêtes/Succès | Services de progression, lectures source, caches, images, manifestes | `REVIEW` : classifier chaque groupe, tests de parité avant fusion |
| P2-14 | Caches Guide/Quête bornés en nombre mais pas en octets | LRU 4096 / 2048 entrées | `REVIEW` : poids réel, hits/misses et invalidations |
| P2-15 | Ressources temporaires / variantes `_vN`, Ganymède et drafts | Manifest→source→runtime→package non exhaustivement reliés | `REVIEW` ; conserver assets actifs |
| P2-16 | Vérifications JSON syntaxiques != cohérence métier | 420/420 JSON syntaxiquement valides à `613ec84` | Validation schémas/IDs/références active incomplète |
| P2-17 | Coût de pages/threads/QPixmap et cycles de vie | TODO dans registre RAM | `REVIEW` à profiler (pas fuite confirmée) |

## P3 — UI/Unity, intégration, limites de test

| ID | Sujet | Statut |
|---|---|---|
| P3-01 | 15 overrides QSS locaux ; effet relief, ombre, typographie, états et sélecteurs | `REVIEW` |
| P3-02 | Rendu Unity Windows natif (GPU/DPI/fallback, launcher TK/Qt) | `NOT_RUN` malgré 5 scénarios Qt offscreen PASS |
| P3-03 | Navigation par menu ≠ clic sur chaque contrôle/texte/combat/objet | `NOT_RUN` exhaustivité interaction |
| P3-04 | Corrélations Doctor : plans d'outils et scénarios `PLANNED_NOT_RUN` ≠ mesures | `REVIEW`; conserver différence observé/proposé |
| P3-05 | Dashboard Graphify : max nœuds à l'écran inférieur aux 16787 nœuds brut | `REVIEW`, pagination/filtrage sans effacer le graphe |
| P3-06 | Builds Windows prêts à fusionner : le SHA antérieur `c04c813` a échoué dans Sylvestre | `FIX_COMMITTED_PROOF_PENDING`; ne pas fusionner |

## Inventaire des 36 objectifs d'origine (statut INDIVIDUEL à rapprocher des preuves)

| ID | Objectif à clôturer | Vérification attendue | État |
|---|---|---|---|
| OPT-P0-01 | Launcher coincé à 75 % : isoler téléchargement, assemblage multipart, vérifications, extraction, rollback et lancement ; corriger la cause, pas seulement l'affichage. **Implémentation dans #285**, sans doublon. | Trace intégrale d'une vraie installation Windows, progression basée sur travail réel, arrêt/récupération sûre | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P0-02 | Préchargement 22,91 s : profiler `guide/quest/success` et dépendances ; enlever les recalculs et rendre le non-essentiel non bloquant. | Premier contenu utilisable avant préload facultatif, parcours initial comparé cold/warm | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P0-03 | Guides : `ensure_catalog_manual_view` 24 s ; profiler par sous-fonction, différer construction des cartes, virtualiser les longues vues. | Sylvestre cycle 1/2 et Guide complet carte 134/267 rebenchés, aucune carte manquante | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P0-04 | Détail quête #18 7,08 s : optimiser compilation, enrichissement, étapes riches, noms/liens, images. | Décomposition 3,19/2,55/0,98/0,21 s avant/après, par ID | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P0-05 | Détail succès #20 5,43 s : attribuer 5,28 s de navigation à ses fonctions avant correction. | CPU et temps inclusif/exclusif des sous-phases, rendu complet | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P0-06 | Parcours Phase 8 38,17 s : réduire la latence jusqu'aux premiers vrais contenus, pas seulement premier paint. | Même runner/machine, mêmes données, cold/warm, p50/p95 et absence de régression | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P1-07 | Ramener le pic du test Guides 307,7 Mio sous 250 Mio. | Process-tree réel, mêmes guides, instrumentation des allocations | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P1-08 | Ramener le Home stabilisé sous 100 Mio après séquences répétées. | Mesure stabilisée et cycles équivalents sur la même machine | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P1-09 | Réduire les deux workers de préchauffage totalisant 144 Mio lors du pic Phase 8. | RAM PID par PID, RSS à l'extinction, pas de conservation superflue | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P1-10 | Auditer les ~16 Mio retenus après Guide et la conservation des objets caches/views. | Distinguer cache utile et fuite, référence mémoire + GC + durées de session | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P1-11 | Éliminer les 26 gels Qt >250 ms sans faux PASS sur FPS. | Événements Qt, durée bloquante, test Windows visuel | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P1-12 | Réduire les p95/p99 et gros outliers Guides, pas juste la médiane. | 52/52 guides, échantillonnage normal non perturbé par profileur intrusif | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P1-13 | Régressions navigation/retours Home : widgets, timers, signaux, listeners, caches. | 10/20/50 cycles, compte des instances avant/après | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P1-14 | Attribution CPU/RAM/IO par appel et composant, appels redondants inclus. | Temps exclusif + cumulatif, coût CPU total et arborescence de processus | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P2-15 | Construire et mutualiser les index quêtes, IDs, noms et liens ; éviter parcours globaux. | Nombre de rebuilds/accès, coût froid/chaud, parités | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P2-16 | Cache d'enrichissement `quests_enriched.json` par quête, résultat précompilé versionné ou index partagé au besoin. | Premier et second accès, réponse exacte, empreinte mémoire bornée | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P2-17 | Étapes riches à la demande, sans reconstituer le parcours complet à chaque fiche. | Coût de `rich_quest_steps` et conformité textes, combats, images | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P2-18 | Guides : virtualiser listes/cartes et limiter la taille des caches/sous-vues. | Temps carte 134/267, mémoire des 26 guides, interaction complète | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P2-19 | Caches versionnés/signés : réutiliser entre lancements sans recopier ni recalculer ; invalidations atomiques ciblées. | Warm-cache réellement réutilisé, invalidation testée par changement de source | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P2-20 | Préload par dépendances avec priorisation sans worker inutile ni double charge des sources. | Durées domaine et pids, Home utilisable, no-op stable | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P2-21 | Launcher : delta de fichiers plutôt que nouveau full de 2,7 Go si manifestes compatibles (**#285**). | Transfert nul si version exacte, patch minimum avec parité et SHA | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P2-22 | Launcher : ne pas rehasher/reparcourir plusieurs fois archive multipart, sans réduire les contrôles intégrité (**#285**). | Temps/bytes de chaque phase, reprise après corruption et coupure | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P2-23 | Launcher : fenêtre unique Unity, prérequis, choix dossier, reprise, diagnostics, rollback (**#285**). | Recette native Windows et preuves contrat #286/#287 | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P2-24 | Launcher : lancement direct sur version identique, aucun réseau ou réinstallation de blocage (**#285**). | Test froid/chaud/offline / no-op exacte version | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P3-25 | Bench natif launcher complet install/update/multipart/offline/disque lent/rollback. | Timestamps et SHA final, vrai EXE | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P3-26 | Profiler sur Windows contraint CPU/RAM/disque, DPI et résolutions usuelles. | Environnement déclaré, pas de machine inventée | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P3-27 | Stress par instance Atlas, 1/4/8 clients Atlas, CPU/RAM/IO, pas 8 clients DOFUS supposés. | Attributions individuelles et process-tree | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P3-28 | Compléter 5 routes `PLACEHOLDER` ou les marquer clairement non fonctionnelles ; tester toutes les fonctions publiées. | Couverture fonctionnelle honnête | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P3-29 | Validation UI native Windows, FPS, clic→paint, responsiveness et screenshots. | Tests desktop/EXE réels, Qt offscreen distinct | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P3-30 | Auditer 19 exceptions silencieuses repérées et traitement d'erreurs JSON. | Causes, alternatives sûres, diagnostics non masqués | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P3-31 | Graphify : investiguer 22 pistes sans éliminer des chemins utilisés. | Preuves consommateurs/régression avant cleanup | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P3-32 | Étendre le contrôle doublons au runtime/data/index/caches, en plus AST. | Graphe de provenance, doublons vraiment confirmés | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P3-33 | Doctor : pourcentage de coût par fonction/module et phase, IO/CPU/RSS, rapport exact SHA lisible. | Pas d'attribution de pic RAM non causal ou chiffres inventés | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P3-34 | CI intelligente : vérifier relances post-#300, artefacts attempt exact, pas de FULL systématique. | Réexécutions ciblées et plan de couverture explicite | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P3-35 | Budgets anti-régression : Home <100 Mio stabilisés, pic ≤250 Mio, temps froid/chaud/P95/P99 et seuils contextualisés, tolérance 5 % contrôlée. | Gates basés sur mesures comparables, signalement des tests non exécutés | `REVIEW` — mapping commit/test/mesure non finalisé |
| OPT-P3-36 | Audit commit par commit, transversal final, zéro référence cassée, certif exact-SHA, tests Windows & rollbacks avant fusion. | Traçabilité et verdict final ; aucun `DONE` sans preuves | `REVIEW` — mapping commit/test/mesure non finalisé |

## Les 50 pistes mémoire, conservées individuellement

`measured` signifie mesure réalisée, **pas optimisation terminée** ; `instrumented` signifie observabilité existante, pas RAM gagnée.

| ID | Priorité | Domaine | Sujet | État source | Preuve / responsable |
|---|---|---|---|---|---|
| RAM-01 | P0 | Runtime | RSS processus et arbre PID | `measured` | Comparer RSS et pics sur des phases nommées; `tools/benchmark_phase8_memory.py` |
| RAM-02 | P0 | Home | Dérive Home sur plusieurs retours | `measured` | RSS initial, après 1/3/10/20 cycles; `tools/doctor_quick_app_probe.py` |
| RAM-03 | P0 | Modules | RAM avant/puis après chaque module | `measured` | Conserver les mesures brutes et deltas, sans attribution abusive; `tools/doctor_quick_app_probe.py` |
| RAM-04 | P0 | Qt | Nombre de QWidget vivants | `instrumented` | Compter après DeferredDelete, avant allocation d'objets de diagnostic; `tools/atlas_doctor_lib/ram_inventory.py` |
| RAM-05 | P0 | Qt | Répartition des widgets par page propriétaire | `instrumented` | Chaîne parentWidget et catégorie inconnue explicite; `tools/atlas_doctor_lib/ram_inventory.py` |
| RAM-06 | P0 | Qt | État pages chargées vs lazy | `instrumented` | État de la factory après chaque retour Home; `tools/atlas_doctor_lib/ram_inventory.py` |
| RAM-07 | P0 | Mesure | Séparer allocations Python et natif Qt | `todo` | Profiler les heaps séparément; ne jamais sommer des estimations en RSS; `tools/doctor_quick_app_probe.py` |
| RAM-08 | P1 | Python | Profil mémoire tracemalloc séparé | `todo` | Comparaison snapshots hors benchmark de vitesse, top traceback; `tools/atlas_doctor.py` |
| RAM-09 | P1 | Qt | Profilage heap C++ et shiboken | `todo` | Durée de vie QObject natifs et preuves Windows; `tools/atlas_doctor.py` |
| RAM-10 | P1 | Qt | Références aux anciennes pages libérées | `todo` | weakref et shiboken isValid avant/après destruction; `main.py` |
| RAM-11 | P1 | Qt | Signal-slot, timers, callbacks, closures | `todo` | Lister propriétaires et références retenues après fermeture; `main.py` |
| RAM-12 | P1 | Workers | Durée de vie threads et résultats différés | `todo` | Résultat lourd abandonné, aucune GUI Qt dans worker; `app/ui/world_scan_panel.py` |
| RAM-13 | P1 | Organizer | Reconstruire uniquement cartes de personnages modifiées | `todo` | Widget count/RSS/icon decode, watcher inchangé; `app/pages/organizer/organizer_ui.py` |
| RAM-14 | P1 | Organizer | Watcher Unity et scans de sessions | `todo` | Un seul watcher vivant, nettoyage sûr et état multi-comptes préservé; `app/pages/organizer_page.py` |
| RAM-15 | P1 | Home | Réemploi des icônes et liste de personnages inchangée | `measured` | Test reconnect/classe/sélection et comparatif RSS; `main.py` |
| RAM-16 | P2 | UI | Sous-navigation et boutons temporaires | `todo` | Compter anciennes lignes de boutons Qt avant/après navigation; `main.py` |
| RAM-17 | P1 | WorldMap | QPixmap natif du monde caché | `measured` | Pixels libérés sans changer sélection/historique; `app/ui/world_scan_panel.py` |
| RAM-18 | P1 | WorldMap | QImage tardifs de workers cartographiques | `measured` | Image non conservée hors écran; recharge async; `app/ui/world_scan_panel.py` |
| RAM-19 | P2 | WorldMap | Lignes cartographiques et SQLite du monde | `todo` | Nombre de lignes, curseurs et fermeture DB sur navigation; `app/cartography/world_service.py` |
| RAM-20 | P1 | Guides | Virtualisation de longues fiches visibles | `todo` | Limiter widgets aux étapes voisines, navigation inchangée; `app/modules/encyclopedia/views/guides_view.py` |
| RAM-21 | P0 | Guides | Saut profond vers étape 134/267 | `todo` | Neutraliser blocage 9,86s sans cacher erreurs; `app/modules/encyclopedia/views/guides_view.py` |
| RAM-22 | P1 | Guides | LRU des miniatures de l'Encyclopédie | `measured` | Budget 8 MiB/64 entrées, hits et empreinte réelle; `app/modules/encyclopedia/services/image_service.py` |
| RAM-23 | P1 | Images | Copies simultanées QImage/QPixmap/images brutes | `todo` | Diff de nb images et octets décodés à chaque phase; `app/modules/encyclopedia/views/guides_view.py` |
| RAM-24 | P1 | Qt | Capacité QPixmapCache native | `instrumented` | Capacité uniquement; occupation réelle inconnue; `tools/atlas_doctor_lib/ram_inventory.py` |
| RAM-25 | P1 | Guides | Cache itinéraire Sylvestre précompilé | `measured` | Reste sur disque; timings et mémoire par guide; `app/modules/encyclopedia/services/guide_catalog_prebuilt_route.py` |
| RAM-26 | P1 | Quests | SQLite Quêtes et chargement différé | `measured` | Détails non importés dans Home; `app/quest_catalog_details.py` |
| RAM-27 | P1 | Quests | LRU des détails de quêtes lourds | `todo` | Hit rate, cardinalité et objets retenus après retour Home; `app/quest_catalog_details.py` |
| RAM-28 | P1 | Success | Fournisseurs succès en mémoire | `todo` | Compter sources compactes et graphes actifs; `app/modules/encyclopedia/views/encyclopedia_page.py` |
| RAM-29 | P1 | Encyclopedia | Déduplication graphes guides-quêtes-succès | `todo` | Identité des objets et cycles interprovider, parité fonctionnelle; `app/modules/encyclopedia/views/encyclopedia_page.py` |
| RAM-30 | P2 | Craft | release_runtime et nettoyage icônes | `measured` | Absence de rétention d'adapters/lists Widgets; `app/pages/craft_page.py` |
| RAM-31 | P2 | Craft | Index de recherche et lookup d'items | `todo` | Dédup par nom, limiter résultats matérialisés; `app/pages/craft_page.py` |
| RAM-32 | P2 | Bestiary | Chargement réellement différé des sous-onglets | `todo` | Distinction placeholder et vrai contenu; pas de faux PASS; `tools/doctor_quick_app_probe.py` |
| RAM-33 | P2 | Stuffs | Éviter WebEngine embarqué si inutile | `measured` | Aucun Chromium natif en production; `app/pages/equipment_page.py` |
| RAM-34 | P2 | Unity | Ressources de thème, ombres, effets QSS | `todo` | CPU paint/RSS widgets/ressources avant-après; `app/ui/theme.py` |
| RAM-35 | P0 | Preload | Chevauchement et mémoire des processus de warmup | `todo` | Arbre PID phase, peak, durée de vie; intervalle optimal; `app/startup_cache_warmup.py` |
| RAM-36 | P1 | Release | Test natif Windows EXE vierge | `todo` | Compiler/tester vraie release, fenêtre visible et processus enfants; `launch.py` |
| RAM-37 | P0 | Windows | Private Bytes, Working Set, partages et GPU | `todo` | Utiliser APIs natives, ne pas confondre RSS privé et RAM partagée; `tools/benchmark_phase8_memory.py` |
| RAM-38 | P1 | Perf | Temps d'ouverture des guides conservé | `measured` | 52/52, p50 p95 p99 et gels, exact SHA; `tools/benchmark_atlas_exhaustive.py` |
| RAM-39 | P1 | MultiInstance | 8 Atlas indépendants avec isolation des profils | `measured` | Mémoire par PID, pas 8 comptes simulés dans un seul process; `tools/atlas_doctor_lib/parallel_app.py` |
| RAM-40 | P1 | Cycles | Test 10 et 20 aller-retours par module | `todo` | Pente RSS, widgets et plateau stable; sans changement données perso; `tools/doctor_quick_app_probe.py` |
| RAM-41 | P2 | Hardware | Machine faible RAM, CPU contraint et DPI réel | `todo` | Temps et mémoire sur vrai Windows, pas seulement 1 cœur virtuel; `tools/atlas_doctor.py` |
| RAM-42 | P1 | Caches | Budgets et taux de hits des caches globaux | `todo` | Identifier doublons, plafonds et miss pénalisants; `tools/atlas_doctor_lib/ram_inventory.py` |
| RAM-43 | P1 | CI | Mesures exact-SHA et statut d'audit honnête | `measured` | Pas de PASS complet quand preuves native manquantes; `tools/atlas_doctor.py` |
| RAM-44 | P2 | Assets | Fichiers/image manifest dupliqués ou inutiles | `todo` | Preuve consommateurs + intégrité avant suppression; `docs/performance/atlas-full-optimization-backlog-20261030.md` |
| RAM-45 | P2 | Extensions | Plugins et services de fond réellement actifs | `todo` | PID, timers, mémoire, aucun accès additionnel inutile; `app/pages/home_page.py` |
| RAM-46 | P2 | Profiles | Pas de suppression des progressions ou identités | `measured` | Contrôle données utilisateurs inchangées; `main.py` |
| RAM-47 | P2 | Python | Allocateur CPython, GC et mémoire non rendue | `todo` | Vérifier objet vivant vs RSS après gc/idle, ne pas forcer trim; `tools/doctor_quick_app_probe.py` |
| RAM-48 | P2 | Images | Décodage directement à la taille d'affichage | `measured` | QImageReader scaled, vignette en cache borné; `app/modules/encyclopedia/services/image_service.py` |
| RAM-49 | P3 | Fonts | Police Qt, QFont et cache de textes | `todo` | Mesurer volume/retention avant changement de thème; `app/ui/theme.py` |
| RAM-50 | P3 | Launcher | Mémoire du launcher durant install/mise à jour | `todo` | Suivre dans PR #285 sans doublonner son développement; `launch.py` |

## Index nominatif des 213 groupes AST — tous les candidats

Chaque ligne référence le **groupe complet** dans `pr303-audit-candidats-20261031.json → ast_duplicate_groups[index]`. Les occurrences ne sont pas supprimables automatiquement.

| Identifiant | Occurrences | Premier symbole / emplacement | Statut |
|---|---:|---|---|
| D-001 | 41 | `tests/test_application_runtime_characterization.py:95` — `setUpClass` | `REVIEW` |
| D-002 | 19 | `app/modules/encyclopedia/providers/memory_bound_guide_provider.py:131` — `get_by_id` | `REVIEW` |
| D-003 | 18 | `tests/test_guide_progress_persistence.py:17` — `tearDown` | `REVIEW` |
| D-004 | 17 | `app/macros/switch_click.py:36` — `reset` | `REVIEW` |
| D-005 | 15 | `tests/test_network_calibration_catchup.py:25` — `_varint` | `REVIEW` |
| D-006 | 13 | `app/modules/encyclopedia/services/achievement_progress_logic.py:6` — `_safe_int` | `REVIEW` |
| D-007 | 13 | `app/network/elevated_capture.py:49` — `wait` | `REVIEW` |
| D-008 | 12 | `app/modules/encyclopedia/services/related_data_service.py:21` — `load_all` | `REVIEW` |
| D-009 | 12 | `app/pages/_quests_page_impl.py:115` — `openLinks` | `REVIEW` |
| D-010 | 9 | `tests/test_network_calibration_catchup.py:38` — `_v` | `REVIEW` |
| D-011 | 9 | `tests/test_network_calibration_catchup.py:42` — `_b` | `REVIEW` |
| D-012 | 8 | `tests/test_guide_ultime_fratrie_necronyx_causality.py:14` — `_stage` | `REVIEW` |
| D-013 | 7 | `app/modules/encyclopedia/tools/audit_quests_guides_semantic.py:46` — `now_iso` | `REVIEW` |
| D-014 | 7 | `app/modules/encyclopedia/views/guide_ultime_manual_view.py:689` — `_sync_order_combo` | `REVIEW` |
| D-015 | 7 | `tests/test_character_runtime_decoder.py:68` — `reset` | `REVIEW` |
| D-016 | 6 | `app/macros/auto_group.py:15` — `__init__` | `REVIEW` |
| D-017 | 6 | `app/modules/encyclopedia/services/guide_preparation_model.py:64` — `_positive_int` | `REVIEW` |
| D-018 | 6 | `app/modules/encyclopedia/views/guide_ultime_generated_view.py:602` — `load_retained` | `REVIEW` |
| D-019 | 6 | `tests/test_network_calibration_runtime_stop_lifecycle.py:20` — `start` | `REVIEW` |
| D-020 | 5 | `app/network/instrumentation.py:67` — `session_closed` | `REVIEW` |
| D-021 | 5 | `app/network/instrumentation.py:72` — `reset` | `REVIEW` |
| D-022 | 5 | `local_dofus_data/image_indexer.py:76` — `_link_asset` | `REVIEW` |
| D-023 | 5 | `local_dofus_data/repositories.py:64` — `__init__` | `REVIEW` |
| D-024 | 5 | `tests/test_atlas_lifecycle_soak.py:9` — `test_passes` | `REVIEW` |
| D-025 | 5 | `tests/test_character_runtime_decoder.py:65` — `session_closed` | `REVIEW` |
| D-026 | 5 | `tests/test_distribution_launcher_noop_offline.py:93` — `__init__` | `REVIEW` |
| D-027 | 5 | `tests/test_guide_auto_validation_cache.py:68` — `builder` | `REVIEW` |
| D-028 | 5 | `tests/test_guide_ultime_fratrie_necronyx_causality.py:18` — `_texts` | `REVIEW` |
| D-029 | 5 | `tools/audit_guide_ultime_canonical_dependencies.py:43` — `_load` | `REVIEW` |
| D-030 | 4 | `app/modules/encyclopedia/services/adventure_route_adapter.py:135` — `_array` | `REVIEW` |
| D-031 | 4 | `app/modules/encyclopedia/widgets/dashboard.py:50` — `mousePressEvent` | `REVIEW` |
| D-032 | 4 | `app/network/character_resolver.py:388` — `_positive_int` | `REVIEW` |
| D-033 | 4 | `app/network/mapped_decoder.py:143` — `_is_sha256` | `REVIEW` |
| D-034 | 4 | `app/pages/craft_page.py:559` — `is_navigation_ready` | `REVIEW` |
| D-035 | 4 | `local_dofus_data/d2i_importer.py:12` — `__init__` | `REVIEW` |
| D-036 | 4 | `tests/test_application_runtime_characterization.py:64` — `set_character_key` | `REVIEW` |
| D-037 | 4 | `tests/test_elevated_capture_control_buffer.py:28` — `close` | `REVIEW` |
| D-038 | 4 | `tests/test_encyclopedia_corrective.py:479` — `forbidden_socket` | `REVIEW` |
| D-039 | 4 | `tests/test_guides_home_render_cache.py:154` — `setUp` | `REVIEW` |
| D-040 | 4 | `tests/test_known_session_recovery.py:24` — `decode` | `REVIEW` |
| D-041 | 4 | `tests/test_network_calibration_runtime_stop_lifecycle.py:51` — `reset` | `REVIEW` |
| D-042 | 3 | `app/core/settings.py:176` — `int_value` | `REVIEW` |
| D-043 | 3 | `app/modules/encyclopedia/providers/achievement_provider.py:288` — `_ensure_loaded` | `REVIEW` |
| D-044 | 3 | `app/modules/encyclopedia/services/guide_catalog_builder.py:1107` — `_write_json` | `REVIEW` |
| D-045 | 3 | `app/modules/encyclopedia/services/guide_progress_service.py:21` — `_empty_progress` | `REVIEW` |
| D-046 | 3 | `app/modules/encyclopedia/services/guide_progress_service.py:35` — `_current_disk_signature` | `REVIEW` |
| D-047 | 3 | `app/modules/encyclopedia/services/guide_progress_service.py:254` — `_validate_write_snapshot` | `REVIEW` |
| D-048 | 3 | `app/modules/encyclopedia/tools/benchmark_guides_performance.py:41` — `milliseconds` | `REVIEW` |
| D-049 | 3 | `app/modules/encyclopedia/tools/benchmark_guides_performance.py:112` — `pump_events` | `REVIEW` |
| D-050 | 3 | `app/network/correlated_identity_decoder.py:231` — `_build_matches` | `REVIEW` |
| D-051 | 3 | `app/network/deobfs_bundle.py:254` — `_positive_int` | `REVIEW` |
| D-052 | 3 | `app/services/maps/map_manifest.py:178` — `write_json` | `REVIEW` |
| D-053 | 3 | `local_dofus_data/api_static_importer.py:26` — `__init__` | `REVIEW` |
| D-054 | 3 | `tests/test_atlas_doctor_runtime_observation.py:195` — `__init__` | `REVIEW` |
| D-055 | 3 | `tests/test_character_runtime_decoder.py:28` — `_scalar` | `REVIEW` |
| D-056 | 3 | `tests/test_character_runtime_decoder.py:32` — `_message` | `REVIEW` |
| D-057 | 3 | `tests/test_distribution_launcher_noop_offline.py:104` — `__init__` | `REVIEW` |
| D-058 | 3 | `tests/test_distribution_launcher_noop_offline.py:107` — `start` | `REVIEW` |
| D-059 | 3 | `tests/test_encyclopedia_corrective.py:74` — `temp_paths` | `REVIEW` |
| D-060 | 3 | `tests/test_guide_ultime_ddg_nebuleux_exit_causality.py:15` — `setUpClass` | `REVIEW` |
| D-061 | 3 | `tests/test_guide_ultime_ddg_nebuleux_exit_causality.py:24` — `_route_text` | `REVIEW` |
| D-062 | 3 | `tests/test_guide_ultime_ddg_nebuleux_exit_causality.py:78` — `test_canonical_stage_count_is_unchanged` | `REVIEW` |
| D-063 | 3 | `tests/test_guide_ultime_manual_route_composition.py:15` — `_write` | `REVIEW` |
| D-064 | 3 | `tests/test_guide_ultime_refresh_performance.py:14` — `reload_progress` | `REVIEW` |
| D-065 | 3 | `tests/test_memory_bound_achievement_progress.py:98` — `load_retained` | `REVIEW` |
| D-066 | 3 | `tests/test_network_calibration_runtime_stop_lifecycle.py:54` — `status` | `REVIEW` |
| D-067 | 3 | `tests/test_network_correlated_identity.py:25` — `varint_field` | `REVIEW` |
| D-068 | 3 | `tests/test_network_correlated_identity.py:29` — `bytes_field` | `REVIEW` |
| D-069 | 3 | `tests/test_network_deobfs_audit.py:35` — `report_text` | `REVIEW` |
| D-070 | 3 | `tests/test_network_discovery.py:22` — `varint_field` | `REVIEW` |
| D-071 | 3 | `tests/test_network_finished_quest_snapshot_bridge.py:32` — `sync_from_quest_progress` | `REVIEW` |
| D-072 | 3 | `tests/test_tool_audit.py:15` — `_write` | `REVIEW` |
| D-073 | 3 | `tools/agent.py:138` — `_unique` | `REVIEW` |
| D-074 | 3 | `tools/atlas_doctor_lib/deep_intelligence.py:215` — `is_ui` | `REVIEW` |
| D-075 | 2 | `app/cartography/scan_status_service.py:38` — `mark_verified` | `REVIEW` |
| D-076 | 2 | `app/cartography/scan_status_service.py:42` — `mark_unverified` | `REVIEW` |
| D-077 | 2 | `app/cartography/scan_status_service.py:46` — `set_current` | `REVIEW` |
| D-078 | 2 | `app/distribution/quest_evidence_pack.py:31` — `_positive` | `REVIEW` |
| D-079 | 2 | `app/distribution/quest_evidence_pack.py:35` — `_name` | `REVIEW` |
| D-080 | 2 | `app/input/hotkeys.py:425` — `stop` | `REVIEW` |
| D-081 | 2 | `app/input/managed_hooks.py:71` — `stop` | `REVIEW` |
| D-082 | 2 | `app/input/managed_hooks.py:88` — `__getattr__` | `REVIEW` |
| D-083 | 2 | `app/macros/input_tools.py:176` — `_sleep_ms` | `REVIEW` |
| D-084 | 2 | `app/modules/encyclopedia/models/__init__.py:62` — `__getattr__` | `REVIEW` |
| D-085 | 2 | `app/modules/encyclopedia/models/guide.py:56` — `required_steps` | `REVIEW` |
| D-086 | 2 | `app/modules/encyclopedia/providers/dofus_item_provider.py:680` — `_read_json` | `REVIEW` |
| D-087 | 2 | `app/modules/encyclopedia/providers/guide_provider.py:89` — `get_by_id` | `REVIEW` |
| D-088 | 2 | `app/modules/encyclopedia/providers/memory_bound_achievement_provider.py:1702` — `line_bytes` | `REVIEW` |
| D-089 | 2 | `app/modules/encyclopedia/services/adventure_route_adapter.py:121` — `_norm` | `REVIEW` |
| D-090 | 2 | `app/modules/encyclopedia/services/guide_auto_validation_contract.py:442` — `_file_stamp` | `REVIEW` |
| D-091 | 2 | `app/modules/encyclopedia/services/guide_catalog_manual_runtime_service.py:833` — `manual_checked` | `REVIEW` |
| D-092 | 2 | `app/modules/encyclopedia/services/guide_catalog_prebuilt_route.py:60` — `_steps_digest` | `REVIEW` |
| D-093 | 2 | `app/modules/encyclopedia/services/guide_progress_calculator.py:208` — `trackable_objective_ids` | `REVIEW` |
| D-094 | 2 | `app/modules/encyclopedia/services/guide_progress_service.py:222` — `_load` | `REVIEW` |
| D-095 | 2 | `app/modules/encyclopedia/services/guide_quest_view_model.py:984` — `_positive_level` | `REVIEW` |
| D-096 | 2 | `app/modules/encyclopedia/services/guide_ultime_manual_route.py:31` — `_read_json` | `REVIEW` |
| D-097 | 2 | `app/modules/encyclopedia/tools/benchmark_guides_performance.py:120` — `wait_until` | `REVIEW` |
| D-098 | 2 | `app/modules/encyclopedia/tools/benchmark_guides_performance.py:323` — `summarize_samples` | `REVIEW` |
| D-099 | 2 | `app/modules/encyclopedia/views/encyclopedia_page.py:649` — `_current_character_sources_signature` | `REVIEW` |
| D-100 | 2 | `app/modules/encyclopedia/views/encyclopedia_page.py:663` — `_guide_progress_state` | `REVIEW` |
| D-101 | 2 | `app/modules/encyclopedia/views/guide_catalog_view.py:250` — `_on_clicked` | `REVIEW` |
| D-102 | 2 | `app/modules/encyclopedia/views/guides_view.py:2154` — `restore_side_scrolls` | `REVIEW` |
| D-103 | 2 | `app/modules/encyclopedia/views/guides_view.py:2598` — `_add_breadcrumb_separator` | `REVIEW` |
| D-104 | 2 | `app/modules/encyclopedia/views/guides_view.py:3413` — `_progress_file_stamp` | `REVIEW` |
| D-105 | 2 | `app/modules/encyclopedia/widgets/__init__.py:113` — `__dir__` | `REVIEW` |
| D-106 | 2 | `app/modules/encyclopedia/widgets/dashboard.py:146` — `clear` | `REVIEW` |
| D-107 | 2 | `app/modules/encyclopedia/widgets/dashboard.py:154` — `finish` | `REVIEW` |
| D-108 | 2 | `app/network/calibration_controller.py:66` — `is_running` | `REVIEW` |
| D-109 | 2 | `app/network/calibration_runtime.py:41` — `is_running` | `REVIEW` |
| D-110 | 2 | `app/network/current_protocol_profile.py:206` — `_is_current_type_url` | `REVIEW` |
| D-111 | 2 | `app/network/deobfs_audit.py:47` — `load_consensus` | `REVIEW` |
| D-112 | 2 | `app/network/elevated_capture.py:176` — `is_started` | `REVIEW` |
| D-113 | 2 | `app/network/quest_snapshot_decoder.py:215` — `_active_entry_quest_id` | `REVIEW` |
| D-114 | 2 | `app/pages/_character_page_impl.py:368` — `_file_stamp` | `REVIEW` |
| D-115 | 2 | `app/pages/craft_page.py:672` — `restyle_button` | `REVIEW` |
| D-116 | 2 | `app/pages/home_page.py:50` — `_resolve_quest_provider` | `REVIEW` |
| D-117 | 2 | `app/services/maps/providers/base_provider.py:14` — `is_available` | `REVIEW` |
| D-118 | 2 | `app/storage.py:1271` — `_schedule_owned_callback` | `REVIEW` |
| D-119 | 2 | `local_dofus_data/data_store.py:264` — `_loads` | `REVIEW` |
| D-120 | 2 | `local_dofus_data/image_downloader.py:27` — `__init__` | `REVIEW` |
| D-121 | 2 | `local_dofus_data/source_registry.py:11` — `__init__` | `REVIEW` |
| D-122 | 2 | `tests/test_achievement_provider_lazy_rewards.py:13` — `_doduda` | `REVIEW` |
| D-123 | 2 | `tests/test_achievements_lot7.py:42` — `setUpClass` | `REVIEW` |
| D-124 | 2 | `tests/test_achievements_lot7.py:107` — `setUpClass` | `REVIEW` |
| D-125 | 2 | `tests/test_application_runtime_characterization.py:469` — `__init__` | `REVIEW` |
| D-126 | 2 | `tests/test_application_runtime_characterization.py:473` — `refresh_characters` | `REVIEW` |
| D-127 | 2 | `tests/test_application_runtime_characterization.py:497` — `character_icon_path` | `REVIEW` |
| D-128 | 2 | `tests/test_application_runtime_characterization.py:503` — `sync_selected_character_to_pages` | `REVIEW` |
| D-129 | 2 | `tests/test_atlas_doctor.py:19` — `_git` | `REVIEW` |
| D-130 | 2 | `tests/test_atlas_doctor_change_intelligence.py:29` — `git` | `REVIEW` |
| D-131 | 2 | `tests/test_atlas_doctor_dev_events.py:26` — `git` | `REVIEW` |
| D-132 | 2 | `tests/test_character_hotkey_mapping.py:86` — `start` | `REVIEW` |
| D-133 | 2 | `tests/test_character_hotkey_mapping.py:90` — `__init__` | `REVIEW` |
| D-134 | 2 | `tests/test_character_runtime_decoder.py:15` — `_varint` | `REVIEW` |
| D-135 | 2 | `tests/test_character_runtime_decoder.py:57` — `__init__` | `REVIEW` |
| D-136 | 2 | `tests/test_character_runtime_decoder.py:62` — `decode` | `REVIEW` |
| D-137 | 2 | `tests/test_character_shell.py:369` — `__init__` | `REVIEW` |
| D-138 | 2 | `tests/test_character_shell.py:372` — `reload_hotkeys` | `REVIEW` |
| D-139 | 2 | `tests/test_character_shell.py:383` — `refresh_global_characters` | `REVIEW` |
| D-140 | 2 | `tests/test_clean_foundation_guardrails.py:13` — `_text` | `REVIEW` |
| D-141 | 2 | `tests/test_distribution_launcher_noop_offline.py:99` — `get` | `REVIEW` |
| D-142 | 2 | `tests/test_distribution_quest_assets.py:99` — `__enter__` | `REVIEW` |
| D-143 | 2 | `tests/test_distribution_resume.py:14` — `__init__` | `REVIEW` |
| D-144 | 2 | `tests/test_doctor_ram_inventory.py:73` — `__init__` | `REVIEW` |
| D-145 | 2 | `tests/test_doctor_ui.py:46` — `pixels` | `REVIEW` |
| D-146 | 2 | `tests/test_doctor_ui.py:61` — `test_archived_windows_screenshot_with_real_to_fu_glyphs_fails` | `REVIEW` |
| D-147 | 2 | `tests/test_doctor_ui.py:90` — `test_real_grayscale_hollow_box_pattern_is_visual_failure` | `REVIEW` |
| D-148 | 2 | `tests/test_doctor_ui.py:101` — `test_legitimate_few_control_squares_do_not_trigger_false_failure` | `REVIEW` |
| D-149 | 2 | `tests/test_doctor_ui.py:120` — `test_truncated_or_oversized_raster_fails_closed` | `REVIEW` |
| D-150 | 2 | `tests/test_encyclopedia_corrective.py:56` — `make_catalog` | `REVIEW` |
| D-151 | 2 | `tests/test_encyclopedia_corrective.py:97` — `rows` | `REVIEW` |
| D-152 | 2 | `tests/test_encyclopedia_corrective.py:173` — `hydrate_guides` | `REVIEW` |
| D-153 | 2 | `tests/test_encyclopedia_on_demand_loading.py:65` — `__init__` | `REVIEW` |
| D-154 | 2 | `tests/test_encyclopedia_on_demand_loading.py:68` — `set_character_key` | `REVIEW` |
| D-155 | 2 | `tests/test_ganymede_dokoko_step_actions.py:25` — `audit` | `REVIEW` |
| D-156 | 2 | `tests/test_ganymede_trusted_cutovers.py:131` — `test_missing_actions_never_activates` | `REVIEW` |
| D-157 | 2 | `tests/test_guide_ganymede_continuous_plan.py:78` — `_canonical_quest_start` | `REVIEW` |
| D-158 | 2 | `tests/test_guide_ganymede_continuous_plan.py:462` — `__init__` | `REVIEW` |
| D-159 | 2 | `tests/test_guide_ganymede_plan_input.py:20` — `setUpClass` | `REVIEW` |
| D-160 | 2 | `tests/test_guide_home_async_images.py:38` — `__init__` | `REVIEW` |
| D-161 | 2 | `tests/test_guide_home_two_columns.py:42` — `load_all` | `REVIEW` |
| D-162 | 2 | `tests/test_guide_manual_bundle_cache.py:79` — `__init__` | `REVIEW` |
| D-163 | 2 | `tests/test_guide_manual_bundle_cache.py:82` — `get_catalog` | `REVIEW` |
| D-164 | 2 | `tests/test_guide_ultime_auto_validation_contract.py:21` — `load_all` | `REVIEW` |
| D-165 | 2 | `tests/test_guide_ultime_auto_validation_contract.py:26` — `completed_quest_ids` | `REVIEW` |
| D-166 | 2 | `tests/test_guide_ultime_ilyzaelle_bonta99_causality.py:14` — `setUpClass` | `REVIEW` |
| D-167 | 2 | `tests/test_guide_ultime_ivoire_sylargh_exit_causality.py:75` — `test_sylargh_repair_preserves_canonical_stage_count` | `REVIEW` |
| D-168 | 2 | `tests/test_guide_ultime_manual_bonta_order.py:16` — `alignment_order_choice` | `REVIEW` |
| D-169 | 2 | `tests/test_guide_ultime_manual_class_branch.py:17` — `__init__` | `REVIEW` |
| D-170 | 2 | `tests/test_guide_ultime_manual_class_branch.py:20` — `get_quest` | `REVIEW` |
| D-171 | 2 | `tests/test_guide_ultime_manual_quest_links.py:54` — `manual_lines_for_card` | `REVIEW` |
| D-172 | 2 | `tests/test_guide_ultime_runtime_progress_cache.py:35` — `__init__` | `REVIEW` |
| D-173 | 2 | `tests/test_guides_batch_progress.py:43` — `_sync_achievement_progress` | `REVIEW` |
| D-174 | 2 | `tests/test_lazy_quests_page_performance.py:41` — `quest` | `REVIEW` |
| D-175 | 2 | `tests/test_lazy_quests_page_performance.py:620` — `run_thread` | `REVIEW` |
| D-176 | 2 | `tests/test_managed_hooks_lazy.py:121` — `stop` | `REVIEW` |
| D-177 | 2 | `tests/test_network_application_coordinator.py:27` — `poll` | `REVIEW` |
| D-178 | 2 | `tests/test_network_bootstrap.py:26` — `get_by_id` | `REVIEW` |
| D-179 | 2 | `tests/test_network_calibrated_mapping_install.py:89` — `setUp` | `REVIEW` |
| D-180 | 2 | `tests/test_network_calibration_catchup.py:46` — `_kvi` | `REVIEW` |
| D-181 | 2 | `tests/test_network_calibration_runtime.py:106` — `__init__` | `REVIEW` |
| D-182 | 2 | `tests/test_network_calibration_runtime.py:111` — `stop` | `REVIEW` |
| D-183 | 2 | `tests/test_network_calibration_runtime_stop_lifecycle.py:23` — `stop` | `REVIEW` |
| D-184 | 2 | `tests/test_network_correlated_identity_cost.py:29` — `fingerprint_provider` | `REVIEW` |
| D-185 | 2 | `tests/test_network_elevated_capture.py:190` — `CloseHandle` | `REVIEW` |
| D-186 | 2 | `tests/test_network_finished_quest_snapshot_bridge.py:20` — `resolve` | `REVIEW` |
| D-187 | 2 | `tests/test_network_finished_quest_snapshot_bridge.py:29` — `__init__` | `REVIEW` |
| D-188 | 2 | `tests/test_network_finished_quest_snapshot_bridge.py:38` — `_bridge` | `REVIEW` |
| D-189 | 2 | `tests/test_network_mapping_audit.py:44` — `consensus` | `REVIEW` |
| D-190 | 2 | `tests/test_network_offline_quest_reconciliation.py:73` — `__init__` | `REVIEW` |
| D-191 | 2 | `tests/test_network_progress_runtime.py:44` — `get_by_id` | `REVIEW` |
| D-192 | 2 | `tests/test_network_progress_runtime.py:55` — `start` | `REVIEW` |
| D-193 | 2 | `tests/test_network_protocol_calibration.py:88` — `_quest` | `REVIEW` |
| D-194 | 2 | `tests/test_network_quest_completion_info_decoder.py:175` — `test_delegates_other_opcodes_and_forwards_lifecycle` | `REVIEW` |
| D-195 | 2 | `tests/test_optimized_achievements_refresh.py:13` — `refresh_if_changed` | `REVIEW` |
| D-196 | 2 | `tests/test_phase7d_cumulative_closeout.py:12` — `setUpClass` | `REVIEW` |
| D-197 | 2 | `tests/test_phase8_preload_priority_memory.py:12` — `setUp` | `REVIEW` |
| D-198 | 2 | `tests/test_phase8_preload_priority_memory.py:66` — `setUp` | `REVIEW` |
| D-199 | 2 | `tests/test_progress_service_reload_fast_paths.py:18` — `fake_read` | `REVIEW` |
| D-200 | 2 | `tests/test_qt_async_non_accumulation.py:74` — `_destroy` | `REVIEW` |
| D-201 | 2 | `tests/test_quest_catalog_details.py:56` — `write_rows` | `REVIEW` |
| D-202 | 2 | `tests/test_quest_progress_reload_fast_path.py:17` — `fake_load` | `REVIEW` |
| D-203 | 2 | `tests/test_runtime_lazy_settings.py:12` — `fake_load_settings` | `REVIEW` |
| D-204 | 2 | `tests/test_theme_runtime_cache.py:10` — `setUp` | `REVIEW` |
| D-205 | 2 | `tests/test_unity_assets_inventory.py:31` — `chunk` | `REVIEW` |
| D-206 | 2 | `tools/agent.py:142` — `_test_module_path` | `REVIEW` |
| D-207 | 2 | `tools/atlas_doctor_lib/audit.py:170` — `_expression_key` | `REVIEW` |
| D-208 | 2 | `tools/atlas_doctor_lib/deep_intelligence.py:292` — `valid` | `REVIEW` |
| D-209 | 2 | `tools/atlas_doctor_lib/report.py:41` — `_is_cost_metric` | `REVIEW` |
| D-210 | 2 | `tools/atlas_json_inventory.py:41` — `_sha256` | `REVIEW` |
| D-211 | 2 | `tools/audit_ganymede_action_to_doduda.py:27` — `positive_int` | `REVIEW` |
| D-212 | 2 | `tools/audit_guide_ultime_route_forensic.py:77` — `_norm` | `REVIEW` |
| D-213 | 2 | `tools/build_guide_ultime_gps_route.py:77` — `load_json` | `REVIEW` |

## Index nominatif des 253 exceptions silencieuses candidates

| ID | Source | Ligne | Statut |
|---|---|---:|---|
| E-001 | `app/background_work.py` | 111 | `REVIEW` |
| E-002 | `app/core/admin.py` | 35 | `REVIEW` |
| E-003 | `app/core/admin.py` | 46 | `REVIEW` |
| E-004 | `app/core/item_identity.py` | 12 | `REVIEW` |
| E-005 | `app/core/json_store.py` | 134 | `REVIEW` |
| E-006 | `app/core/zaap_shortcuts.py` | 15 | `REVIEW` |
| E-007 | `app/craft_preload.py` | 120 | `REVIEW` |
| E-008 | `app/distribution/cleanup.py` | 85 | `REVIEW` |
| E-009 | `app/distribution/cleanup.py` | 58 | `REVIEW` |
| E-010 | `app/distribution/health.py` | 20 | `REVIEW` |
| E-011 | `app/distribution/launcher.py` | 305 | `REVIEW` |
| E-012 | `app/distribution/launcher.py` | 403 | `REVIEW` |
| E-013 | `app/distribution/launcher_ui.py` | 158 | `REVIEW` |
| E-014 | `app/distribution/manifest.py` | 229 | `REVIEW` |
| E-015 | `app/distribution/release_client.py` | 332 | `REVIEW` |
| E-016 | `app/input/hotkeys.py` | 213 | `REVIEW` |
| E-017 | `app/modules/encyclopedia/providers/dofus_item_provider.py` | 76 | `REVIEW` |
| E-018 | `app/modules/encyclopedia/providers/dofus_item_provider.py` | 340 | `REVIEW` |
| E-019 | `app/modules/encyclopedia/providers/dofus_item_provider.py` | 351 | `REVIEW` |
| E-020 | `app/modules/encyclopedia/providers/guide_provider.py` | 782 | `REVIEW` |
| E-021 | `app/modules/encyclopedia/providers/memory_bound_achievement_provider.py` | 90 | `REVIEW` |
| E-022 | `app/modules/encyclopedia/providers/memory_bound_achievement_provider.py` | 115 | `REVIEW` |
| E-023 | `app/modules/encyclopedia/providers/memory_bound_achievement_provider.py` | 975 | `REVIEW` |
| E-024 | `app/modules/encyclopedia/providers/memory_bound_achievement_provider.py` | 942 | `REVIEW` |
| E-025 | `app/modules/encyclopedia/providers/memory_bound_achievement_provider.py` | 1244 | `REVIEW` |
| E-026 | `app/modules/encyclopedia/providers/memory_bound_achievement_provider.py` | 1686 | `REVIEW` |
| E-027 | `app/modules/encyclopedia/providers/memory_bound_achievement_provider.py` | 1087 | `REVIEW` |
| E-028 | `app/modules/encyclopedia/providers/memory_bound_guide_provider.py` | 57 | `REVIEW` |
| E-029 | `app/modules/encyclopedia/providers/memory_bound_guide_provider.py` | 82 | `REVIEW` |
| E-030 | `app/modules/encyclopedia/providers/memory_bound_guide_provider.py` | 316 | `REVIEW` |
| E-031 | `app/modules/encyclopedia/services/achievement_progress_logic.py` | 9 | `REVIEW` |
| E-032 | `app/modules/encyclopedia/services/adventure_route_adapter.py` | 131 | `REVIEW` |
| E-033 | `app/modules/encyclopedia/services/guide_auto_validation_contract.py` | 43 | `REVIEW` |
| E-034 | `app/modules/encyclopedia/services/guide_catalog_builder.py` | 1082 | `REVIEW` |
| E-035 | `app/modules/encyclopedia/services/guide_catalog_manual_runtime_service.py` | 167 | `REVIEW` |
| E-036 | `app/modules/encyclopedia/services/guide_catalog_prebuilt_route.py` | 125 | `REVIEW` |
| E-037 | `app/modules/encyclopedia/services/guide_catalog_route_store.py` | 122 | `REVIEW` |
| E-038 | `app/modules/encyclopedia/services/guide_criterion_scope.py` | 24 | `REVIEW` |
| E-039 | `app/modules/encyclopedia/services/guide_ganymede_cutover.py` | 178 | `REVIEW` |
| E-040 | `app/modules/encyclopedia/services/guide_path_profiles.py` | 406 | `REVIEW` |
| E-041 | `app/modules/encyclopedia/services/guide_prebuilt_rewards.py` | 197 | `REVIEW` |
| E-042 | `app/modules/encyclopedia/services/guide_preparation_model.py` | 41 | `REVIEW` |
| E-043 | `app/modules/encyclopedia/services/guide_preparation_model.py` | 69 | `REVIEW` |
| E-044 | `app/modules/encyclopedia/services/guide_progress_calculator.py` | 164 | `REVIEW` |
| E-045 | `app/modules/encyclopedia/services/guide_progress_service.py` | 38 | `REVIEW` |
| E-046 | `app/modules/encyclopedia/services/guide_quest_view_model.py` | 987 | `REVIEW` |
| E-047 | `app/modules/encyclopedia/services/guide_quest_view_model.py` | 1150 | `REVIEW` |
| E-048 | `app/modules/encyclopedia/services/guide_ultime_generated_service.py` | 25 | `REVIEW` |
| E-049 | `app/modules/encyclopedia/services/guide_ultime_manual_runtime_core.py` | 241 | `REVIEW` |
| E-050 | `app/modules/encyclopedia/services/guide_ultime_manual_runtime_core.py` | 536 | `REVIEW` |
| E-051 | `app/modules/encyclopedia/services/guide_ultime_manual_runtime_core.py` | 1934 | `REVIEW` |
| E-052 | `app/modules/encyclopedia/services/guide_ultime_manual_runtime_core.py` | 151 | `REVIEW` |
| E-053 | `app/modules/encyclopedia/services/guide_ultime_route_adapter.py` | 17 | `REVIEW` |
| E-054 | `app/modules/encyclopedia/services/progress_service.py` | 611 | `REVIEW` |
| E-055 | `app/modules/encyclopedia/services/quest_progress_service.py` | 72 | `REVIEW` |
| E-056 | `app/modules/encyclopedia/services/quest_progress_service.py` | 455 | `REVIEW` |
| E-057 | `app/modules/encyclopedia/services/serialized_achievement_progress_service.py` | 60 | `REVIEW` |
| E-058 | `app/modules/encyclopedia/tools/audit_quests_guides.py` | 887 | `REVIEW` |
| E-059 | `app/modules/encyclopedia/tools/benchmark_guides_performance.py` | 55 | `REVIEW` |
| E-060 | `app/modules/encyclopedia/tools/benchmark_guides_performance.py` | 107 | `REVIEW` |
| E-061 | `app/modules/encyclopedia/tools/validate_guides.py` | 152 | `REVIEW` |
| E-062 | `app/modules/encyclopedia/views/achievements_view.py` | 1110 | `REVIEW` |
| E-063 | `app/modules/encyclopedia/views/achievements_view.py` | 516 | `REVIEW` |
| E-064 | `app/modules/encyclopedia/views/encyclopedia_page.py` | 806 | `REVIEW` |
| E-065 | `app/modules/encyclopedia/views/guide_ultime_generated_view.py` | 284 | `REVIEW` |
| E-066 | `app/modules/encyclopedia/views/guide_ultime_manual_view.py` | 433 | `REVIEW` |
| E-067 | `app/modules/encyclopedia/views/guide_ultime_universal_view.py` | 691 | `REVIEW` |
| E-068 | `app/modules/encyclopedia/views/guide_ultime_walkthrough_card.py` | 385 | `REVIEW` |
| E-069 | `app/modules/encyclopedia/views/guide_ultime_walkthrough_card.py` | 46 | `REVIEW` |
| E-070 | `app/modules/encyclopedia/views/guides_view.py` | 3882 | `REVIEW` |
| E-071 | `app/modules/encyclopedia/views/shared_manual_guide_view.py` | 635 | `REVIEW` |
| E-072 | `app/modules/encyclopedia/views/shared_manual_guide_view.py` | 1399 | `REVIEW` |
| E-073 | `app/modules/encyclopedia/views/shared_manual_guide_view.py` | 1439 | `REVIEW` |
| E-074 | `app/modules/encyclopedia/views/shared_manual_guide_view.py` | 1470 | `REVIEW` |
| E-075 | `app/modules/encyclopedia/views/shared_manual_guide_view.py` | 1894 | `REVIEW` |
| E-076 | `app/network/build_fingerprint.py` | 33 | `REVIEW` |
| E-077 | `app/network/build_fingerprint.py` | 54 | `REVIEW` |
| E-078 | `app/network/build_fingerprint.py` | 67 | `REVIEW` |
| E-079 | `app/network/build_fingerprint.py` | 96 | `REVIEW` |
| E-080 | `app/network/build_fingerprint.py` | 132 | `REVIEW` |
| E-081 | `app/network/build_fingerprint.py` | 249 | `REVIEW` |
| E-082 | `app/network/build_fingerprint.py` | 176 | `REVIEW` |
| E-083 | `app/network/calibrated_mapping_install.py` | 361 | `REVIEW` |
| E-084 | `app/network/calibrated_mapping_install.py` | 371 | `REVIEW` |
| E-085 | `app/network/calibration_runtime.py` | 141 | `REVIEW` |
| E-086 | `app/network/calibration_runtime.py` | 217 | `REVIEW` |
| E-087 | `app/network/capture_helper.py` | 148 | `REVIEW` |
| E-088 | `app/network/capture_helper.py` | 143 | `REVIEW` |
| E-089 | `app/network/character_resolver.py` | 94 | `REVIEW` |
| E-090 | `app/network/character_resolver.py` | 286 | `REVIEW` |
| E-091 | `app/network/character_resolver.py` | 391 | `REVIEW` |
| E-092 | `app/network/character_resolver.py` | 234 | `REVIEW` |
| E-093 | `app/network/character_runtime_decoder.py` | 128 | `REVIEW` |
| E-094 | `app/network/character_runtime_decoder.py` | 173 | `REVIEW` |
| E-095 | `app/network/character_runtime_decoder.py` | 182 | `REVIEW` |
| E-096 | `app/network/character_runtime_decoder.py` | 265 | `REVIEW` |
| E-097 | `app/network/character_runtime_decoder.py` | 206 | `REVIEW` |
| E-098 | `app/network/character_runtime_decoder.py` | 279 | `REVIEW` |
| E-099 | `app/network/character_runtime_decoder.py` | 380 | `REVIEW` |
| E-100 | `app/network/character_runtime_decoder.py` | 425 | `REVIEW` |
| E-101 | `app/network/character_runtime_decoder.py` | 429 | `REVIEW` |
| E-102 | `app/network/character_runtime_state.py` | 80 | `REVIEW` |
| E-103 | `app/network/character_runtime_state.py` | 137 | `REVIEW` |
| E-104 | `app/network/character_runtime_state.py` | 147 | `REVIEW` |
| E-105 | `app/network/character_runtime_state.py` | 167 | `REVIEW` |
| E-106 | `app/network/correlated_identity_decoder.py` | 214 | `REVIEW` |
| E-107 | `app/network/correlated_identity_decoder.py` | 227 | `REVIEW` |
| E-108 | `app/network/correlated_identity_decoder.py` | 234 | `REVIEW` |
| E-109 | `app/network/deobfs_bundle.py` | 259 | `REVIEW` |
| E-110 | `app/network/discovery.py` | 233 | `REVIEW` |
| E-111 | `app/network/discovery_evidence.py` | 314 | `REVIEW` |
| E-112 | `app/network/discovery_probe.py` | 138 | `REVIEW` |
| E-113 | `app/network/known_session_recovery.py` | 27 | `REVIEW` |
| E-114 | `app/network/known_session_recovery.py` | 106 | `REVIEW` |
| E-115 | `app/network/mapped_decoder.py` | 93 | `REVIEW` |
| E-116 | `app/network/mapped_decoder.py` | 101 | `REVIEW` |
| E-117 | `app/network/normalizer.py` | 156 | `REVIEW` |
| E-118 | `app/network/progress_bridge.py` | 568 | `REVIEW` |
| E-119 | `app/network/protobuf_fields.py` | 120 | `REVIEW` |
| E-120 | `app/network/protocol_calibration.py` | 435 | `REVIEW` |
| E-121 | `app/network/protocol_calibration.py` | 417 | `REVIEW` |
| E-122 | `app/network/protocol_extract.py` | 249 | `REVIEW` |
| E-123 | `app/network/protocol_extract.py` | 317 | `REVIEW` |
| E-124 | `app/network/protocol_status.py` | 124 | `REVIEW` |
| E-125 | `app/network/quest_completion_info_decoder.py` | 107 | `REVIEW` |
| E-126 | `app/network/quest_completion_info_decoder.py` | 144 | `REVIEW` |
| E-127 | `app/network/quest_completion_info_decoder.py` | 150 | `REVIEW` |
| E-128 | `app/network/quest_completion_info_decoder.py` | 184 | `REVIEW` |
| E-129 | `app/network/quest_final_step_filter.py` | 64 | `REVIEW` |
| E-130 | `app/network/quest_journal_decoder.py` | 98 | `REVIEW` |
| E-131 | `app/network/quest_journal_decoder.py` | 169 | `REVIEW` |
| E-132 | `app/network/quest_journal_decoder.py` | 187 | `REVIEW` |
| E-133 | `app/network/quest_journal_decoder.py` | 210 | `REVIEW` |
| E-134 | `app/network/quest_journal_decoder.py` | 238 | `REVIEW` |
| E-135 | `app/network/quest_snapshot_decoder.py` | 95 | `REVIEW` |
| E-136 | `app/network/quest_snapshot_decoder.py` | 102 | `REVIEW` |
| E-137 | `app/network/quest_snapshot_decoder.py` | 200 | `REVIEW` |
| E-138 | `app/network/quest_snapshot_decoder.py` | 220 | `REVIEW` |
| E-139 | `app/network/quest_snapshot_decoder.py` | 119 | `REVIEW` |
| E-140 | `app/network/quest_snapshot_decoder.py` | 247 | `REVIEW` |
| E-141 | `app/network/quest_snapshot_discovery.py` | 72 | `REVIEW` |
| E-142 | `app/network/quest_snapshot_discovery.py` | 85 | `REVIEW` |
| E-143 | `app/network/quest_snapshot_discovery.py` | 143 | `REVIEW` |
| E-144 | `app/network/quest_snapshot_discovery.py` | 161 | `REVIEW` |
| E-145 | `app/network/quest_snapshot_discovery.py` | 191 | `REVIEW` |
| E-146 | `app/network/runtime.py` | 129 | `REVIEW` |
| E-147 | `app/network/windows_capture.py` | 541 | `REVIEW` |
| E-148 | `app/network/windows_capture.py` | 506 | `REVIEW` |
| E-149 | `app/network/windows_capture.py` | 513 | `REVIEW` |
| E-150 | `app/network/windows_tcp.py` | 147 | `REVIEW` |
| E-151 | `app/network/windows_tcp.py` | 154 | `REVIEW` |
| E-152 | `app/pages/_quests_page_impl.py` | 934 | `REVIEW` |
| E-153 | `app/pages/home_page.py` | 65 | `REVIEW` |
| E-154 | `app/pages/lazy_quests_page.py` | 176 | `REVIEW` |
| E-155 | `app/pages/lazy_quests_page.py` | 479 | `REVIEW` |
| E-156 | `app/pages/organizer/common.py` | 66 | `REVIEW` |
| E-157 | `app/pages/organizer/common.py` | 73 | `REVIEW` |
| E-158 | `app/pages/quests_page.py` | 370 | `REVIEW` |
| E-159 | `app/quest_catalog.py` | 525 | `REVIEW` |
| E-160 | `app/quest_catalog.py` | 674 | `REVIEW` |
| E-161 | `app/quest_catalog.py` | 701 | `REVIEW` |
| E-162 | `app/quest_catalog.py` | 708 | `REVIEW` |
| E-163 | `app/quest_catalog.py` | 715 | `REVIEW` |
| E-164 | `app/quest_index_prebuilt.py` | 127 | `REVIEW` |
| E-165 | `app/quest_index_prebuilt.py` | 163 | `REVIEW` |
| E-166 | `app/services/character_data_service.py` | 126 | `REVIEW` |
| E-167 | `app/services/character_data_service.py` | 160 | `REVIEW` |
| E-168 | `app/services/maps/map_manifest.py` | 110 | `REVIEW` |
| E-169 | `app/startup_cache_warmup.py` | 261 | `REVIEW` |
| E-170 | `app/startup_timing.py` | 114 | `REVIEW` |
| E-171 | `app/startup_timing.py` | 94 | `REVIEW` |
| E-172 | `app/storage.py` | 287 | `REVIEW` |
| E-173 | `app/storage.py` | 618 | `REVIEW` |
| E-174 | `app/storage.py` | 688 | `REVIEW` |
| E-175 | `app/storage.py` | 701 | `REVIEW` |
| E-176 | `app/storage.py` | 712 | `REVIEW` |
| E-177 | `app/storage.py` | 734 | `REVIEW` |
| E-178 | `app/ui/map_canvas_widget.py` | 258 | `REVIEW` |
| E-179 | `app/ui/map_canvas_widget.py` | 247 | `REVIEW` |
| E-180 | `app/ui/map_canvas_widget.py` | 282 | `REVIEW` |
| E-181 | `app/ui/world_scan_panel.py` | 238 | `REVIEW` |
| E-182 | `app/validation_log.py` | 71 | `REVIEW` |
| E-183 | `app/windows/focus.py` | 112 | `REVIEW` |
| E-184 | `app/windows/unity_windows.py` | 78 | `REVIEW` |
| E-185 | `app/windows/unity_windows.py` | 88 | `REVIEW` |
| E-186 | `app/windows/unity_windows.py` | 99 | `REVIEW` |
| E-187 | `app/windows/unity_windows.py` | 112 | `REVIEW` |
| E-188 | `app/windows/unity_windows.py` | 137 | `REVIEW` |
| E-189 | `app/windows/unity_windows.py` | 148 | `REVIEW` |
| E-190 | `app/windows/unity_windows.py` | 188 | `REVIEW` |
| E-191 | `app/windows/unity_windows.py` | 199 | `REVIEW` |
| E-192 | `app/windows_embed.py` | 205 | `REVIEW` |
| E-193 | `local_dofus_data/zaap_importer.py` | 174 | `REVIEW` |
| E-194 | `local_dofus_data/zaap_importer.py` | 181 | `REVIEW` |
| E-195 | `main.py` | 336 | `REVIEW` |
| E-196 | `main.py` | 1278 | `REVIEW` |
| E-197 | `main.py` | 1402 | `REVIEW` |
| E-198 | `scripts/scan_cartography_bundles.py` | 707 | `REVIEW` |
| E-199 | `scripts/windows/craft_seed.py` | 107 | `REVIEW` |
| E-200 | `tests/test_network_elevated_capture.py` | 82 | `REVIEW` |
| E-201 | `tests/test_network_progress_runtime.py` | 70 | `REVIEW` |
| E-202 | `tests/test_network_runtime_robustness.py` | 34 | `REVIEW` |
| E-203 | `tests/test_quests_guides_audit.py` | 26 | `REVIEW` |
| E-204 | `tools/agent_graph.py` | 29 | `REVIEW` |
| E-205 | `tools/atlas_doctor_lib/actions_step_costs.py` | 15 | `REVIEW` |
| E-206 | `tools/atlas_doctor_lib/audit.py` | 173 | `REVIEW` |
| E-207 | `tools/atlas_doctor_lib/audit.py` | 687 | `REVIEW` |
| E-208 | `tools/atlas_doctor_lib/audit.py` | 693 | `REVIEW` |
| E-209 | `tools/atlas_doctor_lib/capability_matrix.py` | 119 | `REVIEW` |
| E-210 | `tools/atlas_doctor_lib/capability_matrix.py` | 166 | `REVIEW` |
| E-211 | `tools/atlas_doctor_lib/ci_tooling_scope.py` | 66 | `REVIEW` |
| E-212 | `tools/atlas_doctor_lib/ci_tooling_scope.py` | 137 | `REVIEW` |
| E-213 | `tools/atlas_doctor_lib/consumer_sites.py` | 117 | `REVIEW` |
| E-214 | `tools/atlas_doctor_lib/consumer_sites.py` | 126 | `REVIEW` |
| E-215 | `tools/atlas_doctor_lib/core.py` | 133 | `REVIEW` |
| E-216 | `tools/atlas_doctor_lib/deep_intelligence.py` | 47 | `REVIEW` |
| E-217 | `tools/atlas_doctor_lib/diagnostic_correlation.py` | 21 | `REVIEW` |
| E-218 | `tools/atlas_doctor_lib/doctor_ui_ci.py` | 316 | `REVIEW` |
| E-219 | `tools/atlas_doctor_lib/doctor_ui_ci.py` | 364 | `REVIEW` |
| E-220 | `tools/atlas_doctor_lib/integrated_investigation.py` | 21 | `REVIEW` |
| E-221 | `tools/atlas_doctor_lib/live_graph.py` | 306 | `REVIEW` |
| E-222 | `tools/atlas_doctor_lib/ram_forensics.py` | 68 | `REVIEW` |
| E-223 | `tools/atlas_doctor_lib/runtime_benchmark.py` | 37 | `REVIEW` |
| E-224 | `tools/atlas_doctor_lib/runtime_benchmark.py` | 92 | `REVIEW` |
| E-225 | `tools/atlas_doctor_lib/runtime_observation.py` | 80 | `REVIEW` |
| E-226 | `tools/atlas_doctor_lib/runtime_observation.py` | 92 | `REVIEW` |
| E-227 | `tools/atlas_doctor_lib/runtime_observation.py` | 106 | `REVIEW` |
| E-228 | `tools/atlas_doctor_lib/runtime_observation.py` | 331 | `REVIEW` |
| E-229 | `tools/atlas_doctor_lib/runtime_observation.py` | 370 | `REVIEW` |
| E-230 | `tools/atlas_doctor_lib/runtime_observation.py` | 382 | `REVIEW` |
| E-231 | `tools/atlas_doctor_lib/source_impact.py` | 45 | `REVIEW` |
| E-232 | `tools/atlas_full_suite_proof.py` | 101 | `REVIEW` |
| E-233 | `tools/atlas_integrity.py` | 649 | `REVIEW` |
| E-234 | `tools/atlas_meta_integrity.py` | 222 | `REVIEW` |
| E-235 | `tools/atlas_mutation.py` | 17 | `REVIEW` |
| E-236 | `tools/audit_guide_ultime_route_forensic.py` | 86 | `REVIEW` |
| E-237 | `tools/benchmark_atlas_exhaustive.py` | 579 | `REVIEW` |
| E-238 | `tools/benchmark_phase8_preload.py` | 166 | `REVIEW` |
| E-239 | `tools/benchmark_phase8_preload.py` | 147 | `REVIEW` |
| E-240 | `tools/benchmark_phase8_preload.py` | 153 | `REVIEW` |
| E-241 | `tools/benchmark_phase8_preload.py` | 190 | `REVIEW` |
| E-242 | `tools/ci_guide_full_evidence.py` | 215 | `REVIEW` |
| E-243 | `tools/ci_required_certification.py` | 382 | `REVIEW` |
| E-244 | `tools/ci_required_certification.py` | 400 | `REVIEW` |
| E-245 | `tools/doctor_policy_authority.py` | 151 | `REVIEW` |
| E-246 | `tools/phase8_memory_tolerance.py` | 27 | `REVIEW` |
| E-247 | `tools/phase_adaptive_gate.py` | 195 | `REVIEW` |
| E-248 | `tools/tool_audit.py` | 83 | `REVIEW` |
| E-249 | `tools/tool_audit.py` | 122 | `REVIEW` |
| E-250 | `tools/tool_audit.py` | 603 | `REVIEW` |
| E-251 | `tools/tool_audit.py` | 445 | `REVIEW` |
| E-252 | `tools/tool_catalog.py` | 78 | `REVIEW` |
| E-253 | `tools/tool_catalog.py` | 209 | `REVIEW` |

## Les 15 overrides locaux de style Unity/QSS

| ID | Source | Ligne | Statut |
|---|---|---:|---|
| U-001 | `app/modules/encyclopedia/views/guide_catalog_view.py` | 160 | `REVIEW` |
| U-002 | `app/modules/encyclopedia/views/guide_catalog_view.py` | 174 | `REVIEW` |
| U-003 | `app/modules/encyclopedia/views/guide_catalog_view.py` | 97 | `REVIEW` |
| U-004 | `app/modules/encyclopedia/views/guide_featured_home.py` | 40 | `REVIEW` |
| U-005 | `app/modules/encyclopedia/views/guide_featured_home.py` | 50 | `REVIEW` |
| U-006 | `app/modules/encyclopedia/views/guide_featured_home.py` | 62 | `REVIEW` |
| U-007 | `app/modules/encyclopedia/views/guide_featured_home.py` | 68 | `REVIEW` |
| U-008 | `app/modules/encyclopedia/views/shared_manual_guide_view.py` | 839 | `REVIEW` |
| U-009 | `app/modules/encyclopedia/views/shared_manual_guide_view.py` | 863 | `REVIEW` |
| U-010 | `app/modules/encyclopedia/views/shared_manual_guide_view.py` | 476 | `REVIEW` |
| U-011 | `app/modules/encyclopedia/views/shared_manual_guide_view.py` | 522 | `REVIEW` |
| U-012 | `app/modules/encyclopedia/views/shared_manual_guide_view.py` | 550 | `REVIEW` |
| U-013 | `app/modules/encyclopedia/views/shared_manual_guide_view.py` | 526 | `REVIEW` |
| U-014 | `app/modules/encyclopedia/views/shared_manual_guide_view.py` | 555 | `REVIEW` |
| U-015 | `app/ui/preload_popup.py` | 75 | `REVIEW` |

## Deux JSON contenant des collisions d'identifiants candidates

| ID | Source | Identifiants | Statut |
|---|---|---|---|
| J-001 | `docs/audit-remediation/2026-10-14/13-doctor-decisions.json` | cad8e520683a3aee, ffac453b55dce4bb | `REVIEW` (fichier historique) |
| J-002 | `docs/audits/2026-10-14-ac07be9b/registres/diagnostics-doctor.json` | cad8e520683a3aee, ffac453b55dce4bb | `REVIEW` (fichier historique) |

## Les quatre cycles d'import statiques candidats

| ID | Fichiers / hypothèse | Statut |
|---|---|---|
| C-001 | `app/core/runtime_state.py` ↔ `app/macros/auto_group.py` ↔ `app/macros/direction.py` ↔ `app/macros/switch_character.py` ↔ `app/macros/switch_click.py` ↔ `app/macros/travel.py` ↔ `app/macros/zaap.py` | `REVIEW` (non bloquant à ce stade) |
| C-002 | `app/quest_catalog.py` ↔ `app/quest_catalog_details.py` ↔ `app/quest_index_prebuilt.py` | `REVIEW` (non bloquant à ce stade) |
| C-003 | `app/modules/encyclopedia/views/guide_ultime_manual_view.py` ↔ `app/modules/encyclopedia/views/shared_manual_guide_view.py` | `REVIEW` (non bloquant à ce stade) |
| C-004 | `app/modules/encyclopedia/views/guides_view.py` ↔ `app/modules/encyclopedia/widgets/quest_detail_view.py` | `REVIEW` (non bloquant à ce stade) |

## Six nœuds sans liaison dans l'ancien graphe et huit fichiers sans import statique

| ID | Fichier/symbole | Statut |
|---|---|---|
| O-001 | `app/services/__init__.py` | `REVIEW` |
| O-002 | `tools/assets/import_dofus_unity_ui.ps1` | `REVIEW` |
| O-003 | `tools/graphify.ps1` | `REVIEW` |
| O-004 | `tools/install_git_hooks.ps1` | `REVIEW` |
| O-005 | `tools/pre_commit.ps1` | `REVIEW` |
| O-006 | `tools/pre_push.ps1` | `REVIEW` |
| I-001 | `app/distribution/health.py` | `REVIEW` |
| I-002 | `app/modules/encyclopedia/services/link_service.py` | `REVIEW` |
| I-003 | `app/modules/encyclopedia/widgets/progress_card.py` | `REVIEW` |
| I-004 | `app/preload.py` | `REVIEW` |
| I-005 | `app/startup_cache_warmup.py` | `REVIEW` |
| I-006 | `app/startup_preflight.py` | `REVIEW` |
| I-007 | `app/ui/splash_image.py` | `REVIEW` |
| I-008 | `app/windows/single_instance.py` | `REVIEW` |

## Fichiers à fort fanout — 30 premiers du scan précédent

| ID | Fichier | Dépendances proches | Statut |
|---|---|---:|---|
| F-001 | `app/constants.py` | 117 | `REVIEW` |
| F-002 | `app/quest_catalog.py` | 128 | `REVIEW` |
| F-003 | `app/modules/encyclopedia/views/guides_view.py` | 66 | `REVIEW` |
| F-004 | `app/services/maps/cartography_asset_recovery.py` | 40 | `REVIEW` |
| F-005 | `app/modules/encyclopedia/providers/quest_provider.py` | 67 | `REVIEW` |
| F-006 | `app/network/transport.py` | 58 | `REVIEW` |
| F-007 | `app/modules/encyclopedia/services/guide_quest_view_model.py` | 36 | `REVIEW` |
| F-008 | `app/modules/encyclopedia/providers/guide_provider.py` | 32 | `REVIEW` |
| F-009 | `app/modules/encyclopedia/views/encyclopedia_page.py` | 35 | `REVIEW` |
| F-010 | `app/core/text.py` | 28 | `REVIEW` |
| F-011 | `app/modules/encyclopedia/providers/__init__.py` | 52 | `REVIEW` |
| F-012 | `app/modules/encyclopedia/providers/memory_bound_guide_provider.py` | 29 | `REVIEW` |
| F-013 | `app/pages/_quests_page_impl.py` | 27 | `REVIEW` |
| F-014 | `app/modules/encyclopedia/services/quest_progress_service.py` | 49 | `REVIEW` |
| F-015 | `app/storage.py` | 36 | `REVIEW` |
| F-016 | `app/network/contracts.py` | 23 | `REVIEW` |
| F-017 | `app/modules/encyclopedia/views/shared_manual_guide_view.py` | 34 | `REVIEW` |
| F-018 | `app/network/bootstrap.py` | 23 | `REVIEW` |
| F-019 | `app/core/character_identity.py` | 21 | `REVIEW` |
| F-020 | `app/ui/components.py` | 21 | `REVIEW` |
| F-021 | `app/core/logger.py` | 20 | `REVIEW` |
| F-022 | `app/modules/encyclopedia/views/achievements_view.py` | 26 | `REVIEW` |
| F-023 | `app/modules/encyclopedia/providers/achievement_provider.py` | 22 | `REVIEW` |
| F-024 | `app/modules/encyclopedia/widgets/quest_detail_view.py` | 23 | `REVIEW` |
| F-025 | `app/modules/encyclopedia/services/guide_catalog_builder.py` | 21 | `REVIEW` |
| F-026 | `app/modules/encyclopedia/providers/memory_bound_achievement_provider.py` | 22 | `REVIEW` |
| F-027 | `app/modules/encyclopedia/models/entity_ref.py` | 21 | `REVIEW` |
| F-028 | `app/modules/encyclopedia/services/guide_progress_calculator.py` | 20 | `REVIEW` |
| F-029 | `app/modules/encyclopedia/services/guide_progress_service.py` | 40 | `REVIEW` |
| F-030 | `app/modules/encyclopedia/services/guide_catalog_manual_runtime_service.py` | 23 | `REVIEW` |

## Les 40 références littérales non résolues disponibles (sur 582)

| ID | Fichier source | Ligne | Littéral | Statut |
|---|---|---:|---|---|
| L-001 | `app/constants.py` | 23 | `zaap_shortcuts.json` | `REVIEW` |
| L-002 | `app/constants.py` | 28 | `client_profiles.json` | `REVIEW` |
| L-003 | `app/constants.py` | 30 | `client_index.json` | `REVIEW` |
| L-004 | `app/constants.py` | 32 | `network_character_bindings.json` | `REVIEW` |
| L-005 | `app/constants.py` | 33 | `craft_selection.json` | `REVIEW` |
| L-006 | `app/constants.py` | 35 | `quest_progress.json` | `REVIEW` |
| L-007 | `app/constants.py` | 37 | `metiers_leveling.json` | `REVIEW` |
| L-008 | `app/constants.py` | 39 | `pyside_harvest_assets_report.json` | `REVIEW` |
| L-009 | `app/distribution/cleanup.py` | 16 | `.atlas-file-index.json` | `REVIEW` |
| L-010 | `app/distribution/data_pack_store.py` | 46 | `state.json` | `REVIEW` |
| L-011 | `app/distribution/data_pack_store.py` | 82 | `state.json` | `REVIEW` |
| L-012 | `app/distribution/data_pack_store.py` | 170 | `state.json` | `REVIEW` |
| L-013 | `app/distribution/install.py` | 20 | `state.json` | `REVIEW` |
| L-014 | `app/distribution/install.py` | 189 | `.atlas-file-index.json` | `REVIEW` |
| L-015 | `app/distribution/install_location.py` | 17 | `installation.json` | `REVIEW` |
| L-016 | `app/distribution/install_location.py` | 51 | `Emplacement Atlas enregistre invalide; corrigez installation.json` | `REVIEW` |
| L-017 | `app/distribution/launch_pack_recovery.py` | 23 | `state.json` | `REVIEW` |
| L-018 | `app/distribution/release_client.py` | 33 | `atlas-manifest.json` | `REVIEW` |
| L-019 | `app/distribution/release_client.py` | 27 | `/releases/latest/download/atlas-channel.json` | `REVIEW` |
| L-020 | `app/distribution/user_data.py` | 14 | `data/client_profiles.json` | `REVIEW` |
| L-021 | `app/distribution/user_data.py` | 14 | `data/client_profiles.json` | `REVIEW` |
| L-022 | `app/distribution/user_data.py` | 15 | `data/client_index.json` | `REVIEW` |
| L-023 | `app/distribution/user_data.py` | 15 | `data/client_index.json` | `REVIEW` |
| L-024 | `app/local_data_cache.py` | 12 | `local_data_manifest.json` | `REVIEW` |
| L-025 | `app/local_data_cache.py` | 128 | `recipes.json` | `REVIEW` |
| L-026 | `app/modules/encyclopedia/providers/achievement_provider.py` | 36 | `achievement_rewards.json` | `REVIEW` |
| L-027 | `app/modules/encyclopedia/providers/achievement_provider.py` | 37 | `items.json` | `REVIEW` |
| L-028 | `app/modules/encyclopedia/providers/achievement_provider.py` | 38 | `spells.json` | `REVIEW` |
| L-029 | `app/modules/encyclopedia/providers/achievement_provider.py` | 39 | `titles.json` | `REVIEW` |
| L-030 | `app/modules/encyclopedia/providers/achievement_provider.py` | 40 | `emoticons.json` | `REVIEW` |
| L-031 | `app/modules/encyclopedia/providers/achievement_provider.py` | 41 | `ornaments.json` | `REVIEW` |
| L-032 | `app/modules/encyclopedia/providers/achievement_provider.py` | 42 | `alterations.json` | `REVIEW` |
| L-033 | `app/modules/encyclopedia/providers/achievement_provider.py` | 135 | `achievement_rewards.json` | `REVIEW` |
| L-034 | `app/modules/encyclopedia/providers/achievement_provider.py` | 296 | `fr.json` | `REVIEW` |
| L-035 | `app/modules/encyclopedia/providers/achievement_provider.py` | 302 | `achievements.json` | `REVIEW` |
| L-036 | `app/modules/encyclopedia/providers/achievement_provider.py` | 318 | `dungeons.json` | `REVIEW` |
| L-037 | `app/modules/encyclopedia/providers/achievement_provider.py` | 711 | `items.json` | `REVIEW` |
| L-038 | `app/modules/encyclopedia/providers/achievement_provider.py` | 743 | `spells.json` | `REVIEW` |
| L-039 | `app/modules/encyclopedia/providers/achievement_provider.py` | 752 | `titles.json` | `REVIEW` |
| L-040 | `app/modules/encyclopedia/providers/achievement_provider.py` | 761 | `emoticons.json` | `REVIEW` |

## Les 40 exemples de référence ambiguë disponibles (sur 537 signaux)

| ID | Fichier source | Ligne | Littéral | Statut |
|---|---|---:|---|---|
| A-001 | `app/cartography/map_asset_loader.py` | 11 | `placeholder_map.png` | `REVIEW` |
| A-002 | `app/cartography/map_view_manifest.py` | 10 | `map_views.json` | `REVIEW` |
| A-003 | `app/constants.py` | 18 | `dofus_atlas_logo.png` | `REVIEW` |
| A-004 | `app/constants.py` | 19 | `dofus_atlas.ico` | `REVIEW` |
| A-005 | `app/constants.py` | 34 | `zaaps.json` | `REVIEW` |
| A-006 | `app/modules/encyclopedia/providers/dofus_item_provider.py` | 20 | `dofus_unknown.svg` | `REVIEW` |
| A-007 | `app/modules/encyclopedia/providers/guide_provider.py` | 36 | `catalog.json` | `REVIEW` |
| A-008 | `app/modules/encyclopedia/providers/guide_provider.py` | 37 | `manifest.json` | `REVIEW` |
| A-009 | `app/modules/encyclopedia/services/guide_catalog_builder.py` | 351 | `manifest.json` | `REVIEW` |
| A-010 | `app/modules/encyclopedia/services/guide_catalog_manual_runtime_service.py` | 131 | `quests_enriched.json` | `REVIEW` |
| A-011 | `app/modules/encyclopedia/services/guide_catalog_prebuilt_route.py` | 52 | `quests_enriched.json` | `REVIEW` |
| A-012 | `app/modules/encyclopedia/services/guide_catalog_prebuilt_route.py` | 54 | `encyclopedia/quests/quests_enriched.json` | `REVIEW` |
| A-013 | `app/modules/encyclopedia/services/guide_catalog_prebuilt_route.py` | 56 | `encyclopedia/quests/quests_enriched.json` | `REVIEW` |
| A-014 | `app/modules/encyclopedia/services/guide_ganymede_continuous_plan.py` | 196 | `cutover_manifest.json` | `REVIEW` |
| A-015 | `app/modules/encyclopedia/services/guide_ganymede_cutover.py` | 13 | `cutover_manifest.json` | `REVIEW` |
| A-016 | `app/modules/encyclopedia/services/guide_ganymede_travel_review.py` | 74 | `cutover_manifest.json` | `REVIEW` |
| A-017 | `app/modules/encyclopedia/services/guide_path_profiles.py` | 362 | `source_mapping.json` | `REVIEW` |
| A-018 | `app/modules/encyclopedia/services/guide_path_profiles.py` | 386 | `quests_enriched.json` | `REVIEW` |
| A-019 | `app/modules/encyclopedia/services/guide_ultime_manual_conditions.py` | 48 | `manifest_v1.json` | `REVIEW` |
| A-020 | `app/modules/encyclopedia/services/guide_ultime_manual_runtime_core.py` | 25 | `manifest_v1.json` | `REVIEW` |
| A-021 | `app/modules/encyclopedia/services/guide_ultime_manual_runtime_core.py` | 554 | `manifest_v1.json` | `REVIEW` |
| A-022 | `app/modules/encyclopedia/tools/audit_lot6_documentary_fidelity.py` | 20 | `quests_enriched.json` | `REVIEW` |
| A-023 | `app/modules/encyclopedia/tools/audit_quest_visuals.py` | 17 | `quests_enriched.json` | `REVIEW` |
| A-024 | `app/modules/encyclopedia/tools/audit_quest_visuals.py` | 18 | `source_mapping.json` | `REVIEW` |
| A-025 | `app/modules/encyclopedia/tools/audit_quest_visuals.py` | 19 | `image_manifest.json` | `REVIEW` |
| A-026 | `app/modules/encyclopedia/tools/audit_quests_guides.py` | 38 | `catalog.json` | `REVIEW` |
| A-027 | `app/modules/encyclopedia/tools/audit_quests_guides.py` | 39 | `manifest.json` | `REVIEW` |
| A-028 | `app/modules/encyclopedia/tools/audit_quests_guides.py` | 40 | `quests_enriched.json` | `REVIEW` |
| A-029 | `app/modules/encyclopedia/tools/audit_quests_guides.py` | 41 | `source_mapping.json` | `REVIEW` |
| A-030 | `app/modules/encyclopedia/tools/audit_quests_guides.py` | 42 | `image_manifest.json` | `REVIEW` |
| A-031 | `app/modules/encyclopedia/tools/audit_quests_guides.py` | 195 | `catalog.json` | `REVIEW` |
| A-032 | `app/modules/encyclopedia/tools/audit_quests_guides.py` | 195 | `manifest.json` | `REVIEW` |
| A-033 | `app/modules/encyclopedia/tools/audit_quests_guides_semantic.py` | 26 | `source_mapping.json` | `REVIEW` |
| A-034 | `app/modules/encyclopedia/tools/audit_quests_guides_semantic.py` | 27 | `quests_enriched.json` | `REVIEW` |
| A-035 | `app/modules/encyclopedia/tools/enrich_quests.py` | 39 | `source_mapping.json` | `REVIEW` |
| A-036 | `app/modules/encyclopedia/tools/enrich_quests.py` | 40 | `quests_enriched.json` | `REVIEW` |
| A-037 | `app/modules/encyclopedia/tools/enrich_quests.py` | 41 | `image_manifest.json` | `REVIEW` |
| A-038 | `app/modules/encyclopedia/tools/integrate_lot6_codex_candidates.py` | 41 | `quests_enriched.json` | `REVIEW` |
| A-039 | `app/modules/encyclopedia/tools/integrate_lot6_codex_candidates.py` | 42 | `source_mapping.json` | `REVIEW` |
| A-040 | `app/modules/encyclopedia/tools/integrate_lot6_codex_candidates.py` | 43 | `image_manifest.json` | `REVIEW` |

## Index de l'ensemble des 33 411 ressources candidates

**Liste intégrale préservée une fois, sans duplication de 33 411 lignes Markdown**, dans `pr303-audit-candidats-20261031.json` → `no_static_consumer_candidates`. La ligne n°1 du tableau JSON correspond à `ASSET-00001`, la dernière à `ASSET-33411`. Chaque fichier est un **candidat d'absence de consommateur statique**, pas un « fichier mort ». Avant toute suppression, vérifier code dynamique, métadonnées/manifestes, collections et paquets Windows.

## Critères de clôture, obligatoires pour CHAQUE entrée

1. Enregistrer le chemin précis, le consommateur ou le test concerné, et la révision Git **du constat**.
2. Classer `CONFIRMED`, `FALSE_POSITIVE`, `NOT_APPLICABLE` ou `REVIEW` après investigation ; ne jamais convertir automatiquement un candidat en anomalie avérée.
3. Pour `CONFIRMED`, associer un commit correctif, les contrats préservés, test ciblé PASS, absence de régression, benchmark même runner si coût/perf.
4. Pour données/assets/JSON, conserver les références runtime, manifestes et hash ; aucun « nettoyage par mot-clé » et aucune suppression automatique.
5. Publier dans Doctor un export exact-SHA non tronqué des **582/582** références non résolues et **537/537** références classées ambiguës/dangereuses, puis reprendre leurs dossiers.
6. Les captures offscreen, tests mockés et tests à 8 Atlas **ne certifient pas** l'apparence native, l'installation Windows vierge ni les 8 clients DOFUS.
7. `PASS` workflow ≠ audit sémantique `REVIEW`, `SKIPPED` ≠ test exécuté ; aucune fusion automatique.

**Verdict documentaire au moment du relevé :** `AUDIT_INVENTORIED / CORRECTIONS_NOT_ALL_COMMITTED / REVIEW_REQUIRED`.
