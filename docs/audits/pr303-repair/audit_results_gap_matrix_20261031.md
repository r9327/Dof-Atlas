# PR #310 — Synthèse vérifiée des audits et registre des écarts à réparer
**Date :** 31 octobre 2026. **Dépôt :** `r9327/Dof-Atlas`. **PR mère #303 :** `cfab5616c848db9c3bb220aa9308fd4d900acb0f` (389 commits). **PR #310, dernier HEAD audité :** `ab73c56cd4754ff040cb10b9a66b661defcc5c18` (5 commits de réparation sur base `c04c813`). **Statut : audit automatisé fini, traitement métier et certification finale NON TERMINÉS.** Ce document a été ajouté postérieurement à ce HEAD et doit lui-même être revérifié sur son nouveau commit.

## Résultats réellement obtenus et provenance
| Campagne | SHA et run | Résultat observé | Ce que ce résultat ne prouve pas |
|---|---|---|---|
| Patches Git de #303 | `ab73c56`, [41200996544](https://github.com/r9327/Dof-Atlas/actions/runs/41200996544) | SUCCESS ; **387/387** patches historiques parcourus, deux merges comparés à chaque parent ; 18 commits présentant des assertions supprimées, 4 reverts et 2 mentions `skip ci` à examiner | AUCUNE revue humaine des 387 commits : `human_review=NOT_RUN` ; les **deux commits ultérieurs de #303 sont hors de ce scan** |
| Doctor JSON / ressources | `ab73c56`, [41200996549](https://github.com/r9327/Dof-Atlas/actions/runs/41200996549) | SUCCESS technique, **REVIEW métier** ; 1201/1201 Python, 11825 fonctions, 420/420 JSON syntaxiquement valides, aucun fichier absent, aucun parse error, 117975267 octets JSON ; 13 liens chapitre, 24 manifestes, 157 références de base statiques contrôlés | Pas de preuve de toutes les références dynamiques, identités métier, valeurs JSON, images actives, packs ni vues réelles |
| Détection statique | `ab73c56`, même run Doctor | 213 groupes AST / 706 occurrences, 253 exceptions candidates, 15 QSS, 2 fichiers d'audit historiques à collisions d'ID possibles, 0 clé JSON dupliquée signalée | Les candidats NE SONT PAS 213 ou 253 bugs confirmés ; les collisions ne concernent pas nécessairement les quêtes |
| Ressources | `ab73c56`, même run Doctor | 73495 ressources ; 40043 résolues statiquement, **33411** sans consommateur statique, **582** unresolved, **537** unsafe/ambiguous, **111** liens possibles ; artefact annoncé non tronqué par le rapport de campagne | Un asset non lié statiquement peut être chargé par ID, thème ou manifeste ; les 582+537 occurrences exigent vérification individuelle |
| Focus Guides Windows de réparation | `ab73c56`, [41200996594](https://github.com/r9327/Dof-Atlas/actions/runs/41200996594) | **SKIPPED** (job `Guides / Selected unit + Qt Windows`) | Aucun `PASS` Windows ciblé sur le HEAD #310 |
| FULL/EXE Windows précédente | `c04c813`, [41197183499](https://github.com/r9327/Dof-Atlas/actions/runs/41197183499) | **FAIL** à `Precompile portable Sylvestre itinerary` ; les étapes suivantes d'EXE, installer, SHA256 et distribution ont été ignorées en cascade | Aucune preuve de build réel post-correctif ; les tests de contrat updater séparés SUCCESS ne sont pas un installer certifié |
| Graphify précédent | `c04c813`, [41197183675](https://github.com/r9327/Dof-Atlas/actions/runs/41197183675) | Job SUCCESS : 1198 Python, 16787 nœuds, 48375 relations ; contenu sémantique **REVIEW** | Le graphe est antérieur à #310, imports dynamiques et widgets Qt non couverts par seule analyse AST |
| Guides & navigation précédents | `c04c813`, [guides 41197183453](https://github.com/r9327/Dof-Atlas/actions/runs/41197183453), [navigation 41197183460](https://github.com/r9327/Dof-Atlas/actions/runs/41197183460) | 52/52 guides et 60/60 transitions PASS techniques ; Guides p50/p95/p99 103,25/284,54/309,39 ms, 0 gel Qt ≥250ms dans ce run, **247,61 Mio** pic Guide ; Guide preload **13,898 s** ; navigation preload **6,795 s**, dernier Home **115,73 Mio** | 27 transitions portent sur des placeholders ; le dernier Home manque l'objectif <100 Mio ; résultats non transférables au HEAD #310 |

### IMPORTANT — divergence entre PR #303 et PR #310
Depuis le HEAD de base `c04c813` utilisé dans le registre des 387 commits, **deux commits supplémentaires ont été poussés directement sur #303** :
1. [`7e2ebb04f2cb`](https://github.com/r9327/Dof-Atlas/commit/7e2ebb04f2cbb2537d275d28ea4955d39f1f48ad) : même cause racine Sylvestre/URI SQLite relatif déjà traitée par `07646f0` dans #310 ; vérifier la parité des deux implémentations et des tests, **résoudre le chevauchement sans double correction ni régression**.
2. [`cfab5616c848`](https://github.com/r9327/Dof-Atlas/commit/cfab5616c848db9c3bb220aa9308fd4d900acb0f) : registre détaillé d'audit (36 OPT, 213 D, 253 E, 33411 ASSET, etc.), plus inventaire des 388 commits antérieurs.

La #303 comporte donc **389 commits** au moment du relevé, mais le test automatique réussi sur #310 prouve **387/387**, pas 389/389. Il faut intégrer la nouvelle base, comparer les versions du correctif et auditer les nouveaux commits et le diff final. Ne pas prétendre que #310 est à jour sans ce contrôle.

## Anomalies et preuves à compléter — matrice d'action
Chaque anomalie doit finir avec **`statut / cause / décision KEEP ou FIX / fichier(s) / commit SHA / test exact SHA / mesure ou justification / propriétaire PR`**. `VERIFIED` est interdit pour une simple mention dans la PR.

| ID | Priorité | Constat / périmètre | Statut au relevé | Réparation / preuve obligatoire |
|---|---|---|---|---|
| GAP-01 | P0 | SHA #303 389 vs ancien périmètre 387, base #310 en retard et Sylvestre corrigé deux fois | `CONFIRMED_OPEN` | Synchroniser la base, rapprocher les deux correctifs et auditer les 2 SHA additionnels, puis chaque nouveau commit |
| GAP-02 | P0 | 18 commits ayant retiré des assertions, 2 merges, 4 reverts, 2 `skip ci` | `REVIEW` | Décision motivée par patch et tests ; vérifier merge contre les deux parents, absence de trou de couverture |
| GAP-03 | P0 | Véritable build EXE/installer Windows interrompu sur Sylvestre, étapes de bundle ignorées | `FIX_COMMITTED_PROOF_PENDING` | Rejouer précompilation + lecture portable sur chemin relatif et Windows, hash/signature, build réel, installation vierge et smoke du binaire |
| GAP-04 | P0 | 582 références non résolues, 537 ambiguës, 111 liens par nom seul | `REVIEW` | Exploiter l'artefact intégral du run #41200996549, qualifier **chaque occurrence** selon référence active/générée/historique, chemin canonique, lecteur réel ; ne pas convertir un lien heuristique en bug |
| GAP-05 | P0 | Budget Home **115,73 Mio**, cible **<100 Mio** ; écart **15,73 Mio** | `CONFIRMED_OPEN` | Mesurer widgets/QObjects, références/threads/timers/caches, Python et natif (10–20 cycles), corriger la cause et répéter le bench |
| GAP-06 | P1 | Pic Guides **247,61 Mio**, seulement **2,39 Mio** sous le plafond ≤250 ; préload **13,898 s** | `REVIEW` | Profiler QPixmap/QImage, pages et caches, coûts cold/warm et 26 guides ×2 avec empreinte process-tree |
| GAP-07 | P1 | 27 transitions placeholders, Windows bureau natif/GPU/DPI et contrôles internes UI non couverts | `NOT_RUN` | Matrice par fonction réelle : clic→slot→donnée→rendu, préparation, combat, validation, personnages, captures DPI, performance native |
| GAP-08 | P1 | 213 groupes AST identiques, 706 occurrences | `REVIEW` | D-001..D-213 : classifier `INTENTIONAL`, `DUPLICATE_BUSINESS_LOGIC`, `UNUSED_CONFIRMED`, `NOT_PROVEN` par consommateurs et tests ; ne pas refactorer à l'aveugle |
| GAP-09 | P1 | 253 exceptions candidates | `REVIEW` | E-001..E-253 : vérifier fallback attendu vs erreur masquée ; ajouter diagnostics/tests seulement aux sites effectivement fautifs |
| GAP-10 | P1 | 33411 ressources non liées statiquement sur 73495 | `REVIEW` | ASSET-00001..33411 : retrouver usages dynamiques, index ID, thèmes, LFS, génération, manifests, PyInstaller/launcher, vérifier les SHA ; aucune suppression spéculative |
| GAP-11 | P1 | 420/420 JSON parseables mais cohérence métier et deux fichiers d'audit à IDs suspects | `REVIEW` | Unicité par portée, liens Quête/Étape/Succès/Objet/Monstre, valeurs non finies, manifest, cutover Ganymède et progression par personnage |
| GAP-12 | P1 | 4 cycles d'import candidats, 6 orphelins, 8 fichiers sans arête et 345 symboles faibles | `REVIEW` | Déterminer imports dynamiques/type-only et vrais chemins runtime ; vérifier widgets/signal/slot avant tout nettoyage |
| GAP-13 | P1 | 15 overrides QSS et thème Unity incomplet à prouver | `REVIEW` | Vérifier les 15 sites, tokens/états, polices/assets/ombres, Qt Windows 100/125/150% ; ne pas supprimer ressources sur absence d'arête |
| GAP-14 | P1 | 36 actions OPT et 50 pistes RAM sans preuve avant/après close par ID | `REVIEW` | Une ligne par ID (ci-dessous), code + test + même scénario + mesure + statut ; `measured` n'est pas `VERIFIED` |
| GAP-15 | P1 | 8 Atlas simulés et 60 transitions mêlant 27 placeholders | `REVIEW` | Conserver libellé exact `8 Atlas`, pas `8 DOFUS` ; isoler tests fonctionnels/placeholder et stress natif |
| GAP-16 | P1 | Launcher V2 blocage 75%, install/MAJ/no-op/rollback/dossier | `NOT_RUN` sur #310 | Tests utilisateurs Windows et contrats dans **#285 uniquement** ; #310 suit les preuves, sans moteur launcher concurrent |
| GAP-17 | P1 | Doctor/CI des runs `SKIPPED` après échec, preuves sur anciens SHA | `CONFIRMED_OPEN` en certification | Ne pas confondre PASS du scan statique et FULL ; verdict par sous-test et SHA ; préserver seuils et refuser les certificats obsolètes |
| GAP-18 | P2 | Rendu Graphify 15000 nœuds / 16787 totaux, 118 communautés isolées et 50 modules à fanout élevé | `REVIEW` | Export paginé complet, revue comportement de chaque candidat avant changement de responsabilités |
| GAP-19 | P2 | Guide Ganymède, routes `_vN`, `replacement_drafts` et données riches Quêtes/Succès | `REVIEW` | Source→manifest→route→étape→combat→progression→UI→bundle ; parité sans perte et aucune suppression d'historique sans preuve |
| GAP-20 | P2 | Doctor outils disponibles ≠ outils exécutés, attribution CPU/RSS/IO et corrélation ≠ causalité | `REVIEW` | États AVAILABLE/SELECTED/EXECUTED/BLOCKED/NOT_RUN, artefacts exact-SHA et coût par module, réutiliser même moteur de bench |

## Registre individuel **36/36 OPT**
Les descriptions et critères sont recopiés de [l'inventaire #303](https://github.com/r9327/Dof-Atlas/blob/cfab5616c848db9c3bb220aa9308fd4d900acb0f/docs/performance/pr303-audit-registre-integral-20261031.md) afin que #310 n'oublie aucune action. **Statut uniforme = `REVIEW` tant que la preuve de résolution individuelle n'est pas examinée ; ce document ne réévalue pas les optimisations déjà codées.**

| ID | Objectif existant | Critère de vérification | Statut |
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

## Registre individuel **50/50 RAM**
Source : [registre RAM versionné #303](https://github.com/r9327/Dof-Atlas/blob/cfab5616c848db9c3bb220aa9308fd4d900acb0f/docs/performance/atlas-ram-inventory-v1.json). Répartition historique **16 mesurés / 4 instrumentés / 30 TODO** ; *mesuré* et *instrumenté* ne veulent jamais dire *corrigé*. Les valeurs et le propriétaire correspondent au fichier source, sans inventer d'action déjà accomplie.

| ID | Priorité | Domaine | Contrôle attendu | Statut source | Propriétaire technique |
|---|---|---|---|---|---|
| RAM-01 | P0 | Runtime | RSS processus et arbre PID | `measured` | `tools/benchmark_phase8_memory.py` |
| RAM-02 | P0 | Home | Dérive Home sur plusieurs retours | `measured` | `tools/doctor_quick_app_probe.py` |
| RAM-03 | P0 | Modules | RAM avant/puis après chaque module | `measured` | `tools/doctor_quick_app_probe.py` |
| RAM-04 | P0 | Qt | Nombre de QWidget vivants | `instrumented` | `tools/atlas_doctor_lib/ram_inventory.py` |
| RAM-05 | P0 | Qt | Répartition des widgets par page propriétaire | `instrumented` | `tools/atlas_doctor_lib/ram_inventory.py` |
| RAM-06 | P0 | Qt | État pages chargées vs lazy | `instrumented` | `tools/atlas_doctor_lib/ram_inventory.py` |
| RAM-07 | P0 | Mesure | Séparer allocations Python et natif Qt | `todo` | `tools/doctor_quick_app_probe.py` |
| RAM-08 | P1 | Python | Profil mémoire tracemalloc séparé | `todo` | `tools/atlas_doctor.py` |
| RAM-09 | P1 | Qt | Profilage heap C++ et shiboken | `todo` | `tools/atlas_doctor.py` |
| RAM-10 | P1 | Qt | Références aux anciennes pages libérées | `todo` | `main.py` |
| RAM-11 | P1 | Qt | Signal-slot, timers, callbacks, closures | `todo` | `main.py` |
| RAM-12 | P1 | Workers | Durée de vie threads et résultats différés | `todo` | `app/ui/world_scan_panel.py` |
| RAM-13 | P1 | Organizer | Reconstruire uniquement cartes de personnages modifiées | `todo` | `app/pages/organizer/organizer_ui.py` |
| RAM-14 | P1 | Organizer | Watcher Unity et scans de sessions | `todo` | `app/pages/organizer_page.py` |
| RAM-15 | P1 | Home | Réemploi des icônes et liste de personnages inchangée | `measured` | `main.py` |
| RAM-16 | P2 | UI | Sous-navigation et boutons temporaires | `todo` | `main.py` |
| RAM-17 | P1 | WorldMap | QPixmap natif du monde caché | `measured` | `app/ui/world_scan_panel.py` |
| RAM-18 | P1 | WorldMap | QImage tardifs de workers cartographiques | `measured` | `app/ui/world_scan_panel.py` |
| RAM-19 | P2 | WorldMap | Lignes cartographiques et SQLite du monde | `todo` | `app/cartography/world_service.py` |
| RAM-20 | P1 | Guides | Virtualisation de longues fiches visibles | `todo` | `app/modules/encyclopedia/views/guides_view.py` |
| RAM-21 | P0 | Guides | Saut profond vers étape 134/267 | `todo` | `app/modules/encyclopedia/views/guides_view.py` |
| RAM-22 | P1 | Guides | LRU des miniatures de l'Encyclopédie | `measured` | `app/modules/encyclopedia/services/image_service.py` |
| RAM-23 | P1 | Images | Copies simultanées QImage/QPixmap/images brutes | `todo` | `app/modules/encyclopedia/views/guides_view.py` |
| RAM-24 | P1 | Qt | Capacité QPixmapCache native | `instrumented` | `tools/atlas_doctor_lib/ram_inventory.py` |
| RAM-25 | P1 | Guides | Cache itinéraire Sylvestre précompilé | `measured` | `app/modules/encyclopedia/services/guide_catalog_prebuilt_route.py` |
| RAM-26 | P1 | Quests | SQLite Quêtes et chargement différé | `measured` | `app/quest_catalog_details.py` |
| RAM-27 | P1 | Quests | LRU des détails de quêtes lourds | `todo` | `app/quest_catalog_details.py` |
| RAM-28 | P1 | Success | Fournisseurs succès en mémoire | `todo` | `app/modules/encyclopedia/views/encyclopedia_page.py` |
| RAM-29 | P1 | Encyclopedia | Déduplication graphes guides-quêtes-succès | `todo` | `app/modules/encyclopedia/views/encyclopedia_page.py` |
| RAM-30 | P2 | Craft | release_runtime et nettoyage icônes | `measured` | `app/pages/craft_page.py` |
| RAM-31 | P2 | Craft | Index de recherche et lookup d'items | `todo` | `app/pages/craft_page.py` |
| RAM-32 | P2 | Bestiary | Chargement réellement différé des sous-onglets | `todo` | `tools/doctor_quick_app_probe.py` |
| RAM-33 | P2 | Stuffs | Éviter WebEngine embarqué si inutile | `measured` | `app/pages/equipment_page.py` |
| RAM-34 | P2 | Unity | Ressources de thème, ombres, effets QSS | `todo` | `app/ui/theme.py` |
| RAM-35 | P0 | Preload | Chevauchement et mémoire des processus de warmup | `todo` | `app/startup_cache_warmup.py` |
| RAM-36 | P1 | Release | Test natif Windows EXE vierge | `todo` | `launch.py` |
| RAM-37 | P0 | Windows | Private Bytes, Working Set, partages et GPU | `todo` | `tools/benchmark_phase8_memory.py` |
| RAM-38 | P1 | Perf | Temps d'ouverture des guides conservé | `measured` | `tools/benchmark_atlas_exhaustive.py` |
| RAM-39 | P1 | MultiInstance | 8 Atlas indépendants avec isolation des profils | `measured` | `tools/atlas_doctor_lib/parallel_app.py` |
| RAM-40 | P1 | Cycles | Test 10 et 20 aller-retours par module | `todo` | `tools/doctor_quick_app_probe.py` |
| RAM-41 | P2 | Hardware | Machine faible RAM, CPU contraint et DPI réel | `todo` | `tools/atlas_doctor.py` |
| RAM-42 | P1 | Caches | Budgets et taux de hits des caches globaux | `todo` | `tools/atlas_doctor_lib/ram_inventory.py` |
| RAM-43 | P1 | CI | Mesures exact-SHA et statut d'audit honnête | `measured` | `tools/atlas_doctor.py` |
| RAM-44 | P2 | Assets | Fichiers/image manifest dupliqués ou inutiles | `todo` | `docs/performance/atlas-full-optimization-backlog-20261030.md` |
| RAM-45 | P2 | Extensions | Plugins et services de fond réellement actifs | `todo` | `app/pages/home_page.py` |
| RAM-46 | P2 | Profiles | Pas de suppression des progressions ou identités | `measured` | `main.py` |
| RAM-47 | P2 | Python | Allocateur CPython, GC et mémoire non rendue | `todo` | `tools/doctor_quick_app_probe.py` |
| RAM-48 | P2 | Images | Décodage directement à la taille d'affichage | `measured` | `app/modules/encyclopedia/services/image_service.py` |
| RAM-49 | P3 | Fonts | Police Qt, QFont et cache de textes | `todo` | `app/ui/theme.py` |
| RAM-50 | P3 | Launcher | Mémoire du launcher durant install/mise à jour | `todo` | `launch.py` |

## Index des registres individuels massifs (pas de duplication ni perte)
- **D-001…D-213 (706 occurrences)**, **E-001…E-253**, **QSS-001…QSS-015**, **ASSET-00001…ASSET-33411** : fichiers et lignes/chemins enregistrés dans le [JSON candidat de #303](https://github.com/r9327/Dof-Atlas/blob/cfab5616c848db9c3bb220aa9308fd4d900acb0f/docs/performance/pr303-audit-candidats-20261031.json). Les groupes/occurrences restent à qualifier un à un, **aucun verdict individuel implicite**.
- **582 unresolved + 537 unsafe + 111 possible** : le [run Doctor de #310](https://github.com/r9327/Dof-Atlas/actions/runs/41200996549) déclare l'export intégral comme artefact ; l'ancien registre #303 ne donne que 40 exemples de chaque famille. Pour garantir un dossier consultable sans perdre les 542 + 497 occurrences restantes, **conserver les artefacts bruts et importer leurs identifiants dans un registre versionné avant clôture**. Ne pas inventer les chemins.
- **389 commits #303** : [inventaire historique #310 des 387 premiers](commit_ledger.md) + [7e2ebb0](https://github.com/r9327/Dof-Atlas/commit/7e2ebb04f2cbb2537d275d28ea4955d39f1f48ad) + [cfab5616](https://github.com/r9327/Dof-Atlas/commit/cfab5616c848db9c3bb220aa9308fd4d900acb0f). Le nouveau registre #303 fournit déjà les **388 prédécesseurs** de `cfab5616`. Aucun historique 389/389 certifié par le run antérieur.

## Critères de sortie stricts
1. Synchroniser la base de #310 avec le HEAD courant de #303 avant fusion, résoudre le double correctif SQLite Sylvestre et réauditer la différence réelle ; les deux nouveaux commits doivent figurer dans la trace.
2. Rejouer les vérifications adaptées sur **l'exact SHA du correctif intégré**, y compris build Windows natif et précompilation Sylvestre ; un job `SKIPPED` reste `NOT_RUN`.
3. Pour toutes les catégories `D / E / ASSET / liens / QSS / OPT / RAM`, conserver une décision par ID ou laisser `REVIEW` avec une preuve clairement manquante ; jamais de suppression silencieuse.
4. Home stabilisé **<100 Mio**, pic process-tree **≤250 Mio** (avec marge anti-fluctuation mesurée), comparaison appariée froide/chaude sur runner et données comparables ; aucune baisse des seuils pour passer la CI.
5. Audit du diff final et des données Quête/Guide/Succès/Ganymède, retour Home et progression ; bilan `FIXED / KEEP / REVIEW / BLOCKED` avec signatures/artefacts et les risques explicités.
6. **Pas de fusion automatique** ni de release tant que les prérequis et la preuve finale sont incomplets.
