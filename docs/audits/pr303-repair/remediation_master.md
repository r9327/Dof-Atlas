# PR #303 — réparation globale : registre maître des problèmes, preuves et critères de clôture

**Dépôt** `r9327/Dof-Atlas` | **PR mère** [#303](https://github.com/r9327/Dof-Atlas/pull/303) | **HEAD audité** `c04c8134870bd22c52bb414ebc6c530fe6094d12` | **base Git** `0ee44aeeb09358783dcceca799b743c6fb375299`. Cette PR de réparation cible la branche de la #303 pour éviter de dupliquer ses 387 commits dans un nouveau diff `main`.

**Règles non négociables :** anomalies statiques `REVIEW` ≠ bugs, `SKIPPED/NOT_RUN` ≠ `PASS`, mesures de scénarios distincts non additionnées, aucun fichier supprimé sans consommateur et parité vérifiés, aucun seuil affaibli, aucune fusion/release automatisée, remise à jour de l'index .ai en ordre canonique si les sources changent. **Cette PR en Draft est un lot de réparation et un suivi, pas une certification acquise.**

## P0 — défauts confirmés et blockers d'audit

| ID | Source / observation | Action exigée | Validation pour VERIFIÉ |
|---|---|---|---|
| P0-01 | FULL #41197183499 : route Sylvestre refusée à `Precompile portable Sylvestre itinerary`; chemin relatif vers SQLite via `as_uri` dans `guide_catalog_route_store.py` (2 sites) | `path.resolve().as_uri()` aux 2 lectures, test dossier relatif, conserver signature/hash et fallback sûr | test régression + véritable build Sylvestre + EXE/installer Windows au nouveau SHA |
| P0-02 | Pas d'artefact final de bundle Windows certifié | Vérifier build EXE, launcher, installer, prérequis, réinstallation, update différentiel, SHA256, rollback/offline, dossier choisi, même fenêtre update→lancement, aucune perte d'assets | preuves Windows exact SHA et bundle téléchargeable |
| P0-03 | FULL déjà passée sur `c04c813` mais verdict FAIL en cascade après packaging | Distinguer erreur primaire et gates dépendants; refaire sans rendre facultatifs les contrôles | rapport complet de la nouvelle FULL, tous les tests requis et aucune preuve obsolète |
| P0-04 | Scan Doctor JSON complet + liens sur `613ec84`, pas `c04c813`; scoped-pr-ci Draft-only | Exécuter `--with-json --with-links --links-all` et conserver le dump exhaustif sur chaque SHA final, y compris Ready (routage explicite) | `json_syntax_coverage` + liens avec 0 omissions de fichier, SHA et limites |
| P0-05 | 387 commits / 92 fichiers : inventaire acquis, historique patch-by-patch incomplet | Registre 387 SHA, inspection machine diff pour chaque SHA puis décisions humaines, revue séparée de tous les patches finaux et mergers | `387/387` patches inspectés, aucun manquant et revue manuelle justifiée par commit |
| P0-06 | Reste 27 passages placeholders sur 60 nav, qui ne sont PAS 27 modules vérifiés | Distinguer `FUNCTIONAL`, `PLACEHOLDER`, `NOT_RUN`, tester les opérations de chaque écran annoncé | matrice des fonctionnalités réelles et preuves de comportements |

## P1 — performances et mémoire

| ID | Observation / anomalie | Suite mesurable |
|---|---|---|
| P1-01 | Home stabilisé **115,73 Mio** (cible <100), ancien stress ~115,3–115,5 Mio | owner Qt, Python/native, traceback allocations, caches/threads; ne pas maquiller par trim du working set |
| P1-02 | Pic Guides **247,61 Mio** pour plafond 250 : marge seulement 2,39 Mio (0,96 %) | répéter bench sur même runner/scénario et réduire le pic sans casser les données |
| P1-03 | Préload Guides **13 897,99 ms**, navigation courte **6794,85 ms** | profiler domaine/IO/source/parsing/cold/warm, supprimer travail doublé prouvé |
| P1-04 | Guides 52/52 ; p50/p95/p99 **103,25/284,54/309,39ms** ; top latence `dofus_du_cauchemar` et `dofus_dom_de_pin` | compteurs causaux et tests ouverture fiches/étapes |
| P1-05 | 0 gel Qt ≥250ms sur HEAD mais 6 sur ancienne campagne | répétitions n≥3 même configuration pour contrôler la variance, analyser stack Qt échantillonnée sans conclusion causale hâtive |
| P1-06 | 8 Atlas simulés ≠ 8 clients DOFUS ; CPU 1 cœur, 10 parcours et 60s idle couverts en CI | labelliser exactement les scénarios, conserver p50/p95/p99, CPU/RSS/arbre/pids/temps |
| P1-07 | Comparateur Phase8 : environ 512ms de gain total sur UNE paire, pas une moyenne certifiée | >=3 paires baseline/candidat avec provenance runner/attempt, refus de comparer des workloads différents |
| P1-08 | `lru_cache(maxsize=4096)` Guide et `maxsize=2048` Quête | peser valeur + fermeture/invalidations + taux de hits, ne pas réduire arbitrairement |

## P2 — audit architecture/liaisons/doublons/erreurs des données : TOUS les signaux conservés

| ID | Signal source | Contrôle et garde-fou |
|---|---|---|
| P2-01 | **213 groupes AST identiques, 706 occurrences** : 120 tests-only, 73 touchent app | ligne par ligne, API/sémantique/persistance consommateurs; dédupliquer uniquement si preuve sans régression; ne pas fusionner `setUpClass` triviales |
| P2-02 | **253 sites d'exception silencieuse candidats** | classifier exception attendue / masquage / fallback / log / statut, en priorité launcher, warmup, pages, providers, sauvegardes |
| P2-03 | **33 411 ressources** sans consommateur statique prouvé sur ancien scan : 28 918 PNG, 4 335 WebP, 153 JSON, 5 TTF | associer path→runtime→manifest→build/release→fallback, état ACTIVE/LEGACY/UNUSED_CONFIRMED, aucune suppression heuristique |
| P2-04 | **582** références ressources non résolues et **537** unsafe/ambiguous sur ancien scan; **111** possibles | exporter **toutes** les lignes et leur origine, ne pas se limiter aux 40 exemples; contrôler chemins relatifs/dynamiques/Qt, générateurs et Win32 |
| P2-05 | **420 JSON/420 syntaxes valides** sur `613ec84`, mais pas totalité des schémas et IDs au HEAD | identifiants Quêtes/Succès/Guide/Objets/Images, références croisées, data LFS, cutover Ganymède, vérif provenance/packaging |
| P2-06 | **2 fichiers** à collisions d'ID candidates, dans des journaux Doctor historiques (pas quêtes métier) | identifier l'ID `cad8e520683a3aee`/`ffac453b55dce4bb`, vérifier unicité attendue avant toute modification |
| P2-07 | **2 669 références JSON littérales** détectées; imports dynamiques hors preuve | graphe source→consommateur→bundle (génération si besoin) et contrats de disponibilité |
| P2-08 | Graphify HEAD : **1198/1198** Python, **11816** fonctions, **16787 nœuds / 48375 arêtes** ; moteur `REVIEW` | tri exhaustif paginé des anomalies, mesures causales avant refactor, conserver source et SHA |
| P2-09 | Ancien Graphify : **6 orphelins**, **8 fichiers sans arête import**, **345 candidats faiblement connectés**, **118 communautés isolées**, **80 à faible cohésion** | vérifier scripts de lancement externes/Qt et imports différés; pas « fichier mort » par défaut |
| P2-10 | **4 cycles d'import candidats** : macros/runtime_state, Quest catalog/details/index, Guide ultime/shared view, Guide vs Quest detail | distinguer cycles exécutables vs imports typés/différés; refactor ciblé seulement si bloquant |
| P2-11 | **50 modules** à fanout élevé, notamment `guides_view.py`, `encyclopedia_page.py`, launcher, réseau | trier limites de responsabilité, jamais refactor massif sans gain concret |
| P2-12 | Graphe interactif borné à **15 000/16 787 nœuds**, 18 communautés brutes <3 nœuds, 234 sections omises du rendu | paginer/filtrer via moteur réel sans prétendre que vue HTML = inventaire brut complet |
| P2-13 | **15 QSS Unity overrides locaux** et styles anciens en coexistence | correspondance thème officiel/boutons/typographie/ombres/selection/DPI/launcher, captures visuelles natives |
| P2-14 | 124 candidats Ganymède et 189 variantes de route `_vN` déjà répertoriés | table d'usage active, versions historiques, manifest/étapes/pages/packaging, parité guide/combat/validation |
| P2-15 | 36 objectifs principaux dans le backlog sans liens exhaustifs entre commit et preuve | registre objectif→commit→test→mesure→état `TODO/IMPLEMENTED/VERIFIED/BLOCKED`, revues par domaine |
| P2-16 | Déduplication des caches/providers/effets QSS, copies QImage/QPixmap et sourcemaps | empreintes logiques, taille mémoire, hit rate, cycle de vie, absence de mutation croisée |

## RAM — 50 items et statut exhaustif

D'après `docs/performance/atlas-ram-inventory-v1.json` au HEAD #303 : **16 measured, 4 instrumented, 30 todo**. Un item `measured` ne prouve pas un gain.

**Les 30 TODO non refermés :** RAM-07 allocations Python/natif; RAM-08 tracemalloc; RAM-09 heap C++/Shiboken; RAM-10 références anciennes pages; RAM-11 signaux/timers/callbacks; RAM-12 threads/résultats différés; RAM-13 cartes perso; RAM-14 watcher Unity; RAM-16 sous-nav placeholders; RAM-19 carto/SQLite; RAM-20 virtualisation des fiches; RAM-21 saut étape 134/267; RAM-23 QImage/QPixmap; RAM-27 LRU détail Quêtes; RAM-28 provider Succès; RAM-29 dédup graphe Guide/Quête/Succès; RAM-31 recherche items; RAM-32 sous-onglets différés; RAM-34 effets Unity; RAM-35 chevauchement warmup; RAM-36 EXE Windows vierge; RAM-37 private bytes/GPU; RAM-40 10–20 aller-retours; RAM-41 PC faible/DPI; RAM-42 budget caches; RAM-44 assets doublés; RAM-45 services fond; RAM-47 CPython/GC; RAM-49 QFont; RAM-50 RAM launcher.

**Les 4 instrumentés sans bilan final :** RAM-04 QWidget vivants; RAM-05 propriétaires de widgets; RAM-06 pages lazy/vives; RAM-24 QPixmapCache. Les 16 measured doivent relier preuve→date→SHA et rester ouverts si budgets non atteints.

## Domaines de recette complémentaires (non certifiés par seuls tests Qt offscreen)

- Vérifier cohérence UI Guide Succès et Ganymède : en-tête, progression par personnage, étapes/quête, préparation images et copier, combats et validation, sommaire, retour Home, pas d'ancien parcours actif non voulu.
- Vérifier les modules Encyclopédie, Bestiaire, Guide, Crafts, Map Monde, Chasse, Ocre, Almanax, Stuffs, macros et caractérisation des placeholders.
- Vérifier sessions multi-instances, préchargements, lifecycle Qt, asynchrone, Data/JSON/LFS, integrity sha and no duplicate cargo.
- Vérifier véritable UI native Windows DPI/animations/ombres, launcher V2 en deux phases dans la même fenêtre, dossier d'installation, prerequis, no-op si aucun update, downloader différentiel et anti-stall.
- Auditer recherche de fichiers `replacement_drafts`, anciennes routes, anciens QSS, `ganymede_*`, variantes `_vN`; ne rien supprimer sans référence et preuves exactes.
- Séparer tests réels de contrats de simulation, pas de faux `PASS` sur 8 clients DOFUS, FPS natif, installation vierge ou navigation d'un placeholder.

## Audit des commits (obligatoire)

Voir [commit_ledger.md](commit_ledger.md), **387 SHA uniques**. Le script `tools/audit_pr303_commits.py` doit examiner le diff de chacun, sa couverture tests et les risques; il ne déclare pas revue humaine sans une décision explicite. Les deux commits de merge requièrent examen des deux parents, les quatre reverts comparaison avant/après, et les commits `[skip ci]` vérification de leurs tests par cumul. Aucun commit n'est omis du registre. Chaque correction ajoutée à la réparation aura son propre audit avant intégration.

## Provenance des mesures et limitations

- Bench navigation HEAD [41197183460](https://github.com/r9327/Dof-Atlas/actions/runs/41197183460) : 60 parcours (33 fonctions, 27 placeholders), preload 6,794.85ms, pic 207.83Mio, Home 115.73Mio.
- Guides HEAD [41197183453](https://github.com/r9327/Dof-Atlas/actions/runs/41197183453) : 52/52, p50/p95/p99 103.25/284.54/309.39ms, 0 blocage Qt ≥250ms, pic 247.61Mio, preload 13,897.99ms.
- [Graphify HEAD 41197183675](https://github.com/r9327/Dof-Atlas/actions/runs/41197183675) : 1198 Python, 16787 nœuds, 48375 arêtes ; exécution PASS mais contenu REVIEW.
- [FULL HEAD 41197183499](https://github.com/r9327/Dof-Atlas/actions/runs/41197183499) : FAIL sur l'itinéraire Sylvestre, échecs de gates en cascade (non indépendants).
- Données exhaustives candidates (anciennes) : [Scoped Doctor Draft 613ec84](https://github.com/r9327/Dof-Atlas/commit/613ec84c29537b10f97093de2f57cfdf168d82a5); la campagne actuelle doit refaire syntaxe/liaisons sur SHA exact. Ancien scan ne prouve pas quels candidats restent actifs.

## Critères finaux de clôture

1. Aucune erreur P0 ; build EXE/installer réel, SHA intact et tests Windows du même HEAD.
2. 387/387 diffs machine parcourus + **revue humaine de tous les changements critiques** et des deux merges, 92/92 fichiers finaux couverts ; nouveaux commits inclus.
3. Toutes les anomalies candidates sorties en entier avec provenance et verdict par item ou justification honnête `OPEN/REVIEW/NOT_RUN`, jamais effacées faute de place.
4. Objectif Home <100Mio et pic process-tree ≤250Mio si ces budgets restent le contrat ; benchmark répété sur scénarios comparables.
5. Aucun `SKIPPED` pris pour `PASS`, aucun artefact d'un SHA précédent réutilisé comme preuve du nouveau, audit UI natif explicite.
6. Phase Certification, audit Doctor/Graphify/JSON/links et rapports de merge cohérents ; PR #303 et réparation restent non fusionnées sans validation finale.


## Consolidation des résultats FULL et des nouveaux commits #303 — 31/10/2026

**Document détaillé désormais obligatoire :** [audit_results_gap_matrix_20261031.md](audit_results_gap_matrix_20261031.md) — 20 écarts `GAP-01..GAP-20`, **36/36 objectifs OPT individuellement reportés**, **50/50 pistes RAM** avec statut source, bilan factuel des jobs GitHub et index nominatif des D-001..213, E-001..253, 33411 assets et liens. Ce document complète le registre maître, sans substituer un `DONE` aux preuves.

**Écart de SHA découvert après publication de cette base :** la #303 compte **389 commits** au HEAD `cfab5616c848db9c3bb220aa9308fd4d900acb0f` ; le présent registre historique #310 s'arrête au **387e**, `c04c813`. Les deux commits nouveaux sont `7e2ebb04f2cbb2537d275d28ea4955d39f1f48ad` (correctif URI Sylvestre **déjà codé autrement** dans #310) et `cfab5616c848db9c3bb220aa9308fd4d900acb0f` (registres 388 précédents). Il faut rebaser proprement et contrôler les recouvrements, pas pousser deux versions du même correctif aveuglément.

**Preuves strictement attachées à #310@`ab73c56` (SHA précédant l'ajout de cette note) :** [audit patches](https://github.com/r9327/Dof-Atlas/actions/runs/41200996544) **SUCCESS** pour **387/387** diffs automatisés, mais revue humaine `NOT_RUN` ; [Doctor complet JSON et ressources](https://github.com/r9327/Dof-Atlas/actions/runs/41200996549) **SUCCESS technique**, verdict métier `REVIEW`, **1201/1201 Python**, **420/420 JSON syntaxiquement valides**, **213 groupes AST**, **253 exceptions**, **33411 ressources non reliées statiquement**, **582 unresolved**, **537 unsafe**, **111 correspondances possibles**. La [preuve Windows Guides de ce même SHA](https://github.com/r9327/Dof-Atlas/actions/runs/41200996594) a été **SKIPPED**. La [FULL ancienne](https://github.com/r9327/Dof-Atlas/actions/runs/41197183499), sur `c04c813`, a échoué avant construction de l'EXE réel. Les deux nouveaux commits documentaires doivent être audités à leur tour.

**Contrat final ajouté :** classer chaque anomalie par ID en `KEEP / CONFIRMED_OPEN / FIX_COMMITTED_PROOF_PENDING / VERIFIED / REVIEW / BLOCKED` avec cause, fichier, modification, SHA et test réel. Ne pas déclarer les 213, 253 ou 33411 candidats corrigés, et ne pas déduire un installateur certifié des tests statiques. Rappel des mesures réelles sur `c04c813` : **Home 115,73 Mio >100**, **Guide 247,61 Mio ≤250 mais marge 2,39 Mio**, **préload Guide 13,898 s**, **27 placeholders parmi 60 visites**. La responsabilité du launcher demeure dans **#285**.


## Règle de réparation obligatoire : REVIEW = travail ouvert, pas conformité

**Décision du 31 octobre 2026.** Toute entrée `REVIEW`, `NOT_RUN`, `BLOCKED`, `CONFIRMED_OPEN` ou `FIX_COMMITTED_PROOF_PENDING` reste un **travail ouvert et non certifié**. Un scan exhaustif qui signale une hypothèse ne prouve ni une anomalie réelle, ni sa conformité. Le mot `REVIEW` ne peut plus servir de statut terminal ni justifier une fusion.

### Résolution obligatoire de chaque entrée
1. **Examiner** l'occurrence réelle (fichier/ligne/ID/SHA et consommation statique, dynamique, packaging, données). Recouper Doctor et Graphify sans confondre piste et bug.
2. **Décider** à partir des preuves :
   - `FIX_REQUIRED` : défaut confirmé, corriger la cause minimale, conserver le comportement attendu, tester et mesurer ; statut terminal uniquement `FIXED_VERIFIED`.
   - `KEEP_REQUIRED` : comportement intentionnel ou faux positif ; consigner pourquoi, prouver le ou les consommateurs et exécuter le contrôle adéquat ; statut terminal uniquement `KEEP_VERIFIED`.
   - `BLOCKED` / `NOT_RUN` / `REVIEW` : manque de preuve ou de contrôle, **reste ouvert**, même si la CI de détection est verte.
3. **Tracer** pour chaque ID : catégorie, cause, criticité, statut initial et final, fichier/ligne, décision et justification, commit de correction éventuel, test réussi/échoué, run, SHA exact, impacts Windows/Qt/data, risque résiduel et preuve de parité.
4. **Contre-exemples et faux positifs** : ne pas modifier des interfaces AST identiques volontairement, ne pas supprimer un script PowerShell orphelin seulement dans le graphe Python, ne pas supprimer un PNG référencé par ID, ne pas transformer un fallback d'exception délibéré en crash. La conformité doit être **démontrée**, pas supposée.
5. **Vérification en lots** : les milliers de ressources peuvent être classées par une règle déterministe (manifeste, SHA, mapping ID, consommateur, distribution) à condition de conserver **une ligne nominative par fichier et sa preuve** ; chaque exception de la règle passe en revue individualisée. Ne pas accepter un simple résultat agrégé `33411 reviewed`.
6. **Clôture/fusion** : chaque défaut confirmé doit être réparé et testé ; chaque signal non confirmé doit être résolu par une preuve `KEEP_VERIFIED` ou demeurer ouvert, identifié comme bloquant selon sa criticité. Les P0, références actives non résolues, erreurs de packaging, intégrité/progression et budgets mémoire non atteints bloquent la fusion. Aucun faux `PASS` pour un contrôle Windows `SKIPPED`.

### Priorité de réparation (ne pas commencer par des refactors abstraits)
- **P0 immédiat** : réconcilier les deux commits Sylvestre #303/#310, corriger le packaging Windows réellement bloqué, valider l'EXE/installateur ; réconcilier l'audit des 389 commits, contrôle final exact-SHA ; Home 115,73 Mio contre <100 Mio.
- **P1 données fonctionnelles** : 582+537+111 références à qualifier, schémas/IDs/liaisons Ganymède et données réelles, erreurs silencieuses confirmées ; conserver les assets validés.
- **P1 mémoire/performance** : Guide 247,61 Mio (marge insuffisante) et préload 13,898 s à mesurer puis optimiser sur scénarios comparables, cycles Qt, écrans et placeholders.
- **P2 maintenabilité/style** : 213 groupes AST, 253 exceptions, 33411 assets, 4 cycles, 6 orphelins, 8 imports non reliés, 15 QSS ; classifier précisément, corriger uniquement les défauts confirmés ou la dette réellement risquée.
- **Certification** : références par ID, tests Windows natifs/Qt, Doctor, Graphify, comparaison RAM/latence, revue finale des commits et du diff exact HEAD, résultat non tronqué.

**Ce registre constitue un engagement de réparation/justification, pas la preuve que ces réparations ont déjà été codées.**


## Audit détaillé de la PR #310 — 8 commits, 11 fichiers, 34 écarts (HEAD 687c9c78)

**Rapport officiel versionné :** [pr310-full-audit-20261031.md](pr310-full-audit-20261031.md). Audit direct de **8/8 commits**, **11/11 fichiers** de la PR #310 au HEAD `687c9c78d41b1880d53bd6fa6e256da256c66719`, **34 écarts A-01..A-34**, preuves CI, comparatif de branches et manque de validations. Toute entrée à traiter selon la politique `FIXED_VERIFIED / KEEP_VERIFIED` ; aucune clôture par simple `REVIEW`.

**P0 nouveaux constatés :** fusion impossible `mergeable_state=dirty` ; aucune CI au HEAD audité ; index `.ai/context_index.json` désynchronisé sur `docs` ; scan Doctor `--links-all` **n'exporte pas les 582 références non résolues, les 537 unsafe ni les 111 liaisons possibles dans leur intégralité** (seules 33 411 ressources sans consommateur statique sont réellement exportées intégralement). Le scanner de patches a aussi un **défaut vérifié** de reconnaissance des suffixes `.json/.png/.qss`. Le README historique reste à 387 commits alors que la #303 compte 389 commits. **Ces nouveaux défauts sont formellement ouverts dans le rapport.**

**Preuves précédentes correctement qualifiées :** Doctor Linux [#41200996549](https://github.com/r9327/Dof-Atlas/actions/runs/41200996549) `SUCCESS technique / REVIEW métier`, revue patch [#41200996544](https://github.com/r9327/Dof-Atlas/actions/runs/41200996544) 387/387 automatique seulement, Windows [#41200996594](https://github.com/r9327/Dof-Atlas/actions/runs/41200996594) `SKIPPED`, vieille FULL [#41197183499](https://github.com/r9327/Dof-Atlas/actions/runs/41197183499) `FAIL`. Les commits publiant cette nouvelle annexe ne sont pas attestés par ces anciens runs.
