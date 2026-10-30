# Atlas — plan d'optimisation intégrale, JSON et runtime (30 octobre 2026)

> **Périmètre :** cahier des charges et état de référence, pas une implémentation ni une certification de gains. Tous les éléments ci-dessous sont `TODO` jusqu'à des commits de code et des preuves.
>
> **Source de vérité :** `r9327/Dof-Atlas` sur `main@9128e7ca40e50ba5251289ea22f41068a19104a7`. Contrat indépendant [#302](https://github.com/r9327/Dof-Atlas/issues/302). Le Launcher V2 garde son chantier [#285](https://github.com/r9327/Dof-Atlas/pull/285) et son contrat [#286](https://github.com/r9327/Dof-Atlas/issues/286) ; Doctor Performance Lab suit aussi [#297](https://github.com/r9327/Dof-Atlas/issues/297). Ne jamais modifier le périmètre contractuel de #285 par un ajout silencieux.
>
> **Provenance :** [Doctor intégral, run 40982772985](https://github.com/r9327/Dof-Atlas/actions/runs/40982772985) (`dba3003f`, sondes spécialisées PASS, agrégation ancienne FAILURE par doublon de rapports) et [Phase Certification post-fusion #300, run 41019075070](https://github.com/r9327/Dof-Atlas/actions/runs/41019075070) (`9128e7ca`, sous-tests vérifiés ; verdict global à vérifier). La PR #300 est fusionnée, et ne constitue pas un gain de performance. Toutes les mesures sont des scénarios distincts, sur runners Windows / Qt offscreen : elles ne se cumulent pas et ne démontrent ni le FPS d'un vrai bureau ni un PC client.

## Résultats à préserver comme baselines

| Mesure | Valeur et conditions | Statut / limite |
|---|---:|---|
| Premier paint Qt, scénario Phase 8 nouveau HEAD | 141,81 ms | Fenêtre visible, non égal à premier contenu utilisable |
| Préload complet constructeur → READY, Phase 8 | 22 909,94 ms | `quests/encyclopedia/craft = READY` |
| Préload court des 20 routes, run Doctor exhaustif | 9 158,23 ms | **Scénario différent**, non comparable directement à 22,91 s |
| Quête #18, premier détail riche | 7 081,57 ms | Dont 7 045,40 ms post-navigation et chargement de source |
| Compilation quête : enrichissement | 3 193,74 ms | 45 % de l'ouverture de quête #18 |
| Compilation quête : étapes riches | 2 553,42 ms | 36 % |
| Compilation quête : noms/liens | 975,28 ms | 14 % |
| Compilation quête : index images / XP | 213,80 ms | 3 % |
| Succès #20, premier détail riche | 5 434,12 ms | Appel de navigation 5 283,94 ms |
| Guide alignement Bonta, premier détail | 2 480,27 ms | Parcours Phase 8 |
| Premier parcours complet du benchmark Phase 8 | 38 172,14 ms | Préload + ouverture des premiers contenus ; **+1 096,34 ms** contre le baseline de ce run, mesure unique/non statistique |
| Mesure runtime : quête/succès/guide (onglets) | 162,53 / 101,18 / 109,06 ms | Ne pas confondre avec détail riche |
| Mesure runtime : RAM startup / après vues / après retours | 90,55 / 116,29 / 126,25 Mio | Des vues et retours différents |
| Préload Phase 8 : RSS stable / pic RSS | 72,18 / 201,68 Mio | Préload en test dédié |
| Phase 8 RAM : pic process-tree | 220,66 Mio | Dont 144,00 Mio de deux processus de préchauffage au pic |
| Phase 8 RAM : dernier retour Home guide | 106,18 Mio | Seuil cible Home <100 Mio : **warning**, non failure |
| Phase 8 RAM : guide retenu | +16,05 Mio | N'établit pas à lui seul une fuite |
| Doctor navigation : routes | 60 / 60, dont 45 fonctionnelles et 15 placeholders | 20 routes × 3 cycles, 5 routes placeholders |
| Doctor navigation : pic / dernier Home | 208,08 / 124,21 Mio | Scénario différent du Phase 8 |
| Guides | 26 guides jouables × 2 = 52 / 52 PASS | P50/P95/P99 = 169,93 / 2 484,41 / 10 935,58 ms |
| Guide Sylvestre : ouverture au 2e cycle | 28 118,94 ms | Suspicion forte, hors résumé des 10 ouvertures les plus lentes |
| Méthode `ensure_catalog_manual_view` | 24 007,99 ms exclusifs en cycle 2 ; 9 562,63 ms en cycle 1 | Attribué par instrumentation de fonction |
| Guide complet : checkpoint carte 134/267 | 7 301,78 ms | Point de passage lent |
| UI : gels Qt | 26 événements >250 ms | Qt offscreen, pas FPS desktop natif |
| Guides : pic mémoire | **307,70 Mio** | Dépasse cible pic process-tree ≤250 Mio |
| Huit Atlas indépendants | 8/8 PASS, 1 009,70 Mio de pic agrégé | Ce ne sont PAS 8 clients DOFUS |
| Profiling de sources de données | 392 fichiers mesurés, lecture cumulée 38,723 ms et parse JSON 249,129 ms | Profil de cette opération : **pas** total de tous les accès/compilations JSON |
| Graphify AST | 1 173/1 173 fichiers Python suivis, 16 198 nœuds, 46 794 relations | 22 pistes `REVIEW`, zéro doublon de responsabilité confirmé automatiquement |
| Doctor UI ciblée | 5 scénarios sélectionnés, 118 PASS, artefacts captures/arbre | Pas de preuve desktop native |
| Bundle candidat Windows | 2 688 421 009 octets pour l'artefact GitHub | N'est pas une mesure de durée d'installation sur PC utilisateur |

## Inventaire JSON vérifié sur main

| Source | Fichiers suivis / poids |
|---|---|
| `data/encyclopedia/quests/quests_enriched.json` | 72 317 050 octets (~68,97 Mio) |
| `data/encyclopedia/quests/image_manifest.json` | 28 237 353 octets (~26,93 Mio) |
| `data/encyclopedia/quests/source_mapping.json` | 1 836 299 octets (~1,75 Mio) |
| `data/encyclopedia/guides/` | 152 JSON racine (~5,27 Mio), dont 124 fichiers `ganymede_*` (~4,28 Mio) ; sous-répertoire `replacement_drafts` non compté ici |
| `data/routes/guide_ultime_manual/` | 189 JSON (~1,54 Mio) dont de nombreuses variantes `_vN` |
| **Sous-ensemble ci-dessus** | **~104,46 Mio** ; ne représente PAS tous les JSON ni toutes les images d'Atlas |

**Constats du code inspecté, sans inférence de causalité non prouvée :**
- `app/quest_catalog.py` : source `quests_enriched.json` pour `apply_quest_enrichment`, profil `rich_quest_steps` et `enrichment`, signature + cache gzip `quest_catalog_v2.json.gz`.
- `app/quest_source_index.py` : `JsonSourceMapping`, index d'offsets par octets, cache LRU borné à 128 par mapping, index optionnel SQLite et décodage à la demande. Scanner tout le JSON pour recréer ces index demeure une hypothèse à tester, surtout à froid.
- `app/quest_catalog_details.py` : cache SQLite reconstructible signé, `QuestDetails.get` et premier chargement d'une seule quête ; `ensure_detail_source_offsets` prépare les index. Vérifier qu'aucun chargement de détail ne reconstruit sous un autre namespace un index préparé par préload.
- `app/startup_cache_warmup.py` : trois domaines séquentiels `guide → quest → success`, estampilles sources et artefacts et réutilisation éventuelle. Mesurer distinctement `reused` / `rebuilt`, startup cold/warm et le coût de chacun.
- `app/modules/encyclopedia/views/manual_route_guides_view.py` : `ensure_catalog_manual_view` construit un service et une vue `SharedGuideManualView` après `get_by_id`. Le coût instrumenté de 24 s impose une mesure des sous-phases avant tout refactoring.
- Les variantes `_vN` et fichiers Ganymède candidats/observations ne sont **pas** prouvés inutiles. Examiner manifestes, consommateurs runtime, packaging et certificats avant de déplacer/supprimer. Ne jamais supprimer une source canonique.

## Backlog complet — 36 actions, par priorité

Chaque ligne est `TODO`. La priorité est fondée sur impact utilisateur / coût mesuré ; les gains potentiels doivent être prouvés avant/après.

### P0 — Temps avant Atlas réellement utilisable

| ID | À réaliser | Preuve de fin attendue |
|---|---|---|
| OPT-P0-01 | Launcher coincé à 75 % : isoler téléchargement, assemblage multipart, vérifications, extraction, rollback et lancement ; corriger la cause, pas seulement l'affichage. **Implémentation dans #285**, sans doublon. | Trace intégrale d'une vraie installation Windows, progression basée sur travail réel, arrêt/récupération sûre |
| OPT-P0-02 | Préchargement 22,91 s : profiler `guide/quest/success` et dépendances ; enlever les recalculs et rendre le non-essentiel non bloquant. | Premier contenu utilisable avant préload facultatif, parcours initial comparé cold/warm |
| OPT-P0-03 | Guides : `ensure_catalog_manual_view` 24 s ; profiler par sous-fonction, différer construction des cartes, virtualiser les longues vues. | Sylvestre cycle 1/2 et Guide complet carte 134/267 rebenchés, aucune carte manquante |
| OPT-P0-04 | Détail quête #18 7,08 s : optimiser compilation, enrichissement, étapes riches, noms/liens, images. | Décomposition 3,19/2,55/0,98/0,21 s avant/après, par ID |
| OPT-P0-05 | Détail succès #20 5,43 s : attribuer 5,28 s de navigation à ses fonctions avant correction. | CPU et temps inclusif/exclusif des sous-phases, rendu complet |
| OPT-P0-06 | Parcours Phase 8 38,17 s : réduire la latence jusqu'aux premiers vrais contenus, pas seulement premier paint. | Même runner/machine, mêmes données, cold/warm, p50/p95 et absence de régression |

### P1 — RAM, CPU et expérience Qt

| ID | À réaliser | Preuve de fin attendue |
|---|---|---|
| OPT-P1-07 | Ramener le pic du test Guides 307,7 Mio sous 250 Mio. | Process-tree réel, mêmes guides, instrumentation des allocations |
| OPT-P1-08 | Ramener le Home stabilisé sous 100 Mio après séquences répétées. | Mesure stabilisée et cycles équivalents sur la même machine |
| OPT-P1-09 | Réduire les deux workers de préchauffage totalisant 144 Mio lors du pic Phase 8. | RAM PID par PID, RSS à l'extinction, pas de conservation superflue |
| OPT-P1-10 | Auditer les ~16 Mio retenus après Guide et la conservation des objets caches/views. | Distinguer cache utile et fuite, référence mémoire + GC + durées de session |
| OPT-P1-11 | Éliminer les 26 gels Qt >250 ms sans faux PASS sur FPS. | Événements Qt, durée bloquante, test Windows visuel |
| OPT-P1-12 | Réduire les p95/p99 et gros outliers Guides, pas juste la médiane. | 52/52 guides, échantillonnage normal non perturbé par profileur intrusif |
| OPT-P1-13 | Régressions navigation/retours Home : widgets, timers, signaux, listeners, caches. | 10/20/50 cycles, compte des instances avant/après |
| OPT-P1-14 | Attribution CPU/RAM/IO par appel et composant, appels redondants inclus. | Temps exclusif + cumulatif, coût CPU total et arborescence de processus |

### P2 — JSON, caches, architecture des données et launcher

| ID | À réaliser | Preuve de fin attendue |
|---|---|---|
| OPT-P2-15 | Construire et mutualiser les index quêtes, IDs, noms et liens ; éviter parcours globaux. | Nombre de rebuilds/accès, coût froid/chaud, parités |
| OPT-P2-16 | Cache d'enrichissement `quests_enriched.json` par quête, résultat précompilé versionné ou index partagé au besoin. | Premier et second accès, réponse exacte, empreinte mémoire bornée |
| OPT-P2-17 | Étapes riches à la demande, sans reconstituer le parcours complet à chaque fiche. | Coût de `rich_quest_steps` et conformité textes, combats, images |
| OPT-P2-18 | Guides : virtualiser listes/cartes et limiter la taille des caches/sous-vues. | Temps carte 134/267, mémoire des 26 guides, interaction complète |
| OPT-P2-19 | Caches versionnés/signés : réutiliser entre lancements sans recopier ni recalculer ; invalidations atomiques ciblées. | Warm-cache réellement réutilisé, invalidation testée par changement de source |
| OPT-P2-20 | Préload par dépendances avec priorisation sans worker inutile ni double charge des sources. | Durées domaine et pids, Home utilisable, no-op stable |
| OPT-P2-21 | Launcher : delta de fichiers plutôt que nouveau full de 2,7 Go si manifestes compatibles (**#285**). | Transfert nul si version exacte, patch minimum avec parité et SHA |
| OPT-P2-22 | Launcher : ne pas rehasher/reparcourir plusieurs fois archive multipart, sans réduire les contrôles intégrité (**#285**). | Temps/bytes de chaque phase, reprise après corruption et coupure |
| OPT-P2-23 | Launcher : fenêtre unique Unity, prérequis, choix dossier, reprise, diagnostics, rollback (**#285**). | Recette native Windows et preuves contrat #286/#287 |
| OPT-P2-24 | Launcher : lancement direct sur version identique, aucun réseau ou réinstallation de blocage (**#285**). | Test froid/chaud/offline / no-op exacte version |

**Sous-audit JSON obligatoire lié à OPT-P2-15/16/17/19/20 :**
1. Inventorier **tous** les JSON du dépôt et du bundle : taille, statut canonique/candidat/trace, références, déduplication structurelle et métier (IDs, étapes, références), fichiers jamais consommés. Ne pas extrapoler les ~104 Mio à tout le dépôt.
2. Diagnostiquer les 72 Mo d'enrichissement et 28 Mo de manifeste images : lecture, décodage, scan offsets, construction index, cache SQLite, traitement des enregistrements ciblés ; réduire les copies/relectures.
3. Établir les chemins d'utilisation exacts des 124 `ganymede_*`, des 189 versions `_vN` et de `replacement_drafts` : source de vérité, manifeste, runtime, certificats, publication APP. **Aucune suppression par nom ou simple présence d'une variante.**
4. Vérifier la cohérence des sources Doduda, des ID quête/succès/étape, noms FR, pictos, liens, images et assets manquants ; comparer données avant/après par hachage logique et tests.
5. Auditer `read_json_file` (fallback silencieux) vs `json_store` fail-closed ; aucune corruption persistante ou progression utilisateur effacée ; préserver les écritures atomiques.
6. Examiner le coût de gzip/SQLite, requêtes SQL, indexes, multiples `QuestSources`, ressources non fermées, collisions d'indexes et caches de première utilisation. Profiling différentiel avant de remplacer le format.
7. Taille d'archive et packaging : vérifier présence de fichiers de travail/transitoires **réellement** superflus avant toute exclusion ; pas de modification de source métier ou de données sans accord et validation.

### P3 — Doctor, certification, couverture et dette vérifiable

| ID | À réaliser | Preuve de fin attendue |
|---|---|---|
| OPT-P3-25 | Bench natif launcher complet install/update/multipart/offline/disque lent/rollback. | Timestamps et SHA final, vrai EXE |
| OPT-P3-26 | Profiler sur Windows contraint CPU/RAM/disque, DPI et résolutions usuelles. | Environnement déclaré, pas de machine inventée |
| OPT-P3-27 | Stress par instance Atlas, 1/4/8 clients Atlas, CPU/RAM/IO, pas 8 clients DOFUS supposés. | Attributions individuelles et process-tree |
| OPT-P3-28 | Compléter 5 routes `PLACEHOLDER` ou les marquer clairement non fonctionnelles ; tester toutes les fonctions publiées. | Couverture fonctionnelle honnête |
| OPT-P3-29 | Validation UI native Windows, FPS, clic→paint, responsiveness et screenshots. | Tests desktop/EXE réels, Qt offscreen distinct |
| OPT-P3-30 | Auditer 19 exceptions silencieuses repérées et traitement d'erreurs JSON. | Causes, alternatives sûres, diagnostics non masqués |
| OPT-P3-31 | Graphify : investiguer 22 pistes sans éliminer des chemins utilisés. | Preuves consommateurs/régression avant cleanup |
| OPT-P3-32 | Étendre le contrôle doublons au runtime/data/index/caches, en plus AST. | Graphe de provenance, doublons vraiment confirmés |
| OPT-P3-33 | Doctor : pourcentage de coût par fonction/module et phase, IO/CPU/RSS, rapport exact SHA lisible. | Pas d'attribution de pic RAM non causal ou chiffres inventés |
| OPT-P3-34 | CI intelligente : vérifier relances post-#300, artefacts attempt exact, pas de FULL systématique. | Réexécutions ciblées et plan de couverture explicite |
| OPT-P3-35 | Budgets anti-régression : Home <100 Mio stabilisés, pic ≤250 Mio, temps froid/chaud/P95/P99 et seuils contextualisés, tolérance 5 % contrôlée. | Gates basés sur mesures comparables, signalement des tests non exécutés |
| OPT-P3-36 | Audit commit par commit, transversal final, zéro référence cassée, certif exact-SHA, tests Windows & rollbacks avant fusion. | Traçabilité et verdict final ; aucun `DONE` sans preuves |

## Plan de réalisation sans dupliquer #285 ni Doctor

1. **Lot A — Launcher (#285 uniquement).** Correctif 75 % et pipeline install/update, suivi et critères du contrat #286 et validation réelle #287.
2. **Lot B — Données/JSON + preload.** OPT-P0-02/04, OPT-P2-15/16/17/19/20 + sous-audit JSON ; mesurer avant de changer un format de stockage.
3. **Lot C — Guides/succès/Qt.** OPT-P0-03/05, OPT-P1-11/12, OPT-P2-18 ; ne pas perturber la progression ni les parcours Ganymède.
4. **Lot D — RAM/CPU/lifecycle.** OPT-P1-07/08/09/10/13/14 ; pas de `gc.collect()` ajouté sans preuve.
5. **Lot E — Doctor, cleanup, certification.** OPT-P3-25..36, réutiliser une seule campagne Doctor et Graphify, y compris un test natif séparé.

Chaque lot comporte : (a) inventaire des chemins/source et baseline exacte, (b) audit commit-par-commit, (c) changement minimum réversible, (d) tests ciblés de parité/régression, (e) benchmark avant/après comparable, (f) rapport de gain/risque, (g) CI intelligente, puis certification finale seulement si prêt. **Aucun retrait de fichiers, valeurs JSON, étapes de guides ni changement de format persistant par simple intuition.**

## Conditions de clôture du backlog

- Tous les items ont un état explicite `TODO / IMPLEMENTED / VERIFIED / BLOCKED`, des commits et un lien vers leur preuve.
- Tout ralentissement identifié est traité ou documenté comme limite résiduelle mesurée, pas caché sous une CI verte.
- Les tests physiques non faits restent `NOT RUN`; les 5 placeholders sont décomptés séparément.
- Les cibles mémoire ne sont pas abaissées pour faire PASS ; les mesures de différents scénarios ne sont jamais additionnées.
- Les modifications app runtime, données et launcher sont regroupées en lots indépendants avec contrats de parité des quêtes, succès, guides, personnages et données personnelles.
- **Ce document n'est qu'un cadrage à développer**. Aucun des 36 items ne passe à `IMPLEMENTED` du seul fait de sa présence ici.


## Obligation nouvelle — exhaustivité vérifiable (OPT-EXH, aucune analyse partielle certifiée)

**Demande :** inventorier **100 % des objets du périmètre déclaré**, mesurer la part réellement analysée et **refuser une conclusion `AUDIT_COMPLET` si un fichier, scénario obligatoire, symbole ou lien requis n'a pas été vérifié**. Un résultat partiel peut servir au diagnostic rapide FAST, mais doit être explicitement `PARTIAL / NOT_RUN / REVIEW / BLOCKED`, avec les manques, et ne peut jamais être présenté comme une certification complète.

### Lacunes existantes confirmées dans le code de main

- `tools/atlas_doctor_lib/deep_intelligence.py` : `MAX_FILES = 150`, `MAX_FUNCTIONS = 4000`, `MAX_SOURCE_BYTES = 512 * 1024`, `MAX_FINDINGS = 80`. Cette analyse **bornée** ne couvre donc pas forcément tous les fichiers Python du dépôt ; `duplicate_evidence.py` indique explicitement qu'un PASS de la sélection AST ne certifie pas un scan du dépôt entier.
- `tools/atlas_doctor_lib/graph_audit.py` : `MAX_CANDIDATES = 30` dans les rapports paginés ; `--all-candidates` existe pour des sections, mais le rapport tronqué ne doit jamais être interprété comme une absence d'autres problèmes. Graphify a couvert **1 173/1 173 fichiers Python suivis** dans le run précédent ; cela **ne signifie pas** qu'il a exécuté toutes les branches et interfaces.
- `tools/atlas_doctor_lib/runtime_file_focus.py` : les imports AST statiques ne captent pas exhaustivement imports dynamiques, signaux Qt, callbacks, entrées externes ou registre de plugins. Un fichier isolé **n'est pas** prouvé mort.
- `tools/atlas_doctor_lib/scenario_coverage.py` : les traces prouvent uniquement les scénarios effectivement observés. Un symbole absent d'une trace **n'est pas** une preuve d'inutilité.
- Doctor UI : les 5 scénarios sélectionnés/118 actions PASS précédemment ne prouvent ni tous les écrans ni leur qualité visuelle sur Windows natif.

### Livrables à implémenter pour une certification exhaustive

1. **Inventaire de référence immuable et sans trous** : `git ls-files -z`, SHA du candidat, tous fichiers suivis et générés/embarqués dans la Release pour les périmètres applicables ; séparer code, JSON/source, assets, QSS, écrans, launcher, tests, scripts et caches. Décompter `total/analysés/non analysés/erreurs/inaccessibles/exclus` par catégorie. Fichiers non suivis et caches personnels : **hors périmètre explicite**, jamais parcourus ou effacés sans autorisation.
2. **Audit complet du graphe et des sources** : parcourir par lots déterministes toutes les sources Python éligibles, sans omettre les fichiers après le cap 150 ; parser tous les symboles éligibles sans écrêter le résultat final à 4 000 fonctions ; rapport paginé, compte total conservé, fichiers >512 Kio traités explicitement ou `BLOCKED`. Détecter imports absents, cycles, points d'entrée, API re-exportées, symboles isolés, doublons AST et comportements redondants (candidats), appels indirects et responsabilités contradictoires. Rapprocher les consommations Graphify et les traces Doctor.
3. **Connexions / fonctionnalités** : relier chaque menu, page, bouton, signal, slot, action, plugin, macro, worker, fichier de données et route à un point d'entrée, un consommateur, une preuve d'exécution et un résultat de test. Cas des actions optionnelles explicités. Examiner les signalements `NO_STATIC_IMPORT_EDGES_REVIEW` et chemins dynamiques avant toute décision.
4. **JSON et ressources** : inventorier toutes les sources canoniques, historiques, Ganymède et candidates ; fichiers chargés / non chargés, références ID, images, liens et SHA ; distinguer versions archivables des dépendances réellement actives. En cas de données manquantes, collisions, doublons de responsabilité ou source jamais lue, publier fichier, consommateur et preuve. Conserver parité complète quêtes/succès/guides et sauvegardes.
5. **Couverture runtime honnête** : matrice de tous les écrans/fonctions jouables, états et transitions ; par fonction/action : `TESTED`, `NOT_TESTED`, `NOT_APPLICABLE_JUSTIFIED` ou `FAILED`. Inclure les 5 placeholders séparément sans les compter comme fonctionnalités réussies. Distinguer tests Qt hors écran, EXE desktop Windows, sessions réelles, cas dégradés et 8 Atlas distincts (pas 8 DOFUS).
6. **Croisement automatique** : associer à chaque anomalie `fichier:ligne`, `symbole`, utilisateurs/dépendances, preuve statique, trace runtime, mesures wall/CPU/RSS, statut de confiance, gravité, hypothèse et test ciblé. Pour les anomalies réellement confirmées, proposer changement minimal réversible et estimation à vérifier, jamais un gain chiffré inventé.
7. **Vérificateur de complétude dans Doctor** : sortie structurée avec `inventory_sha`, `inspected_sha`, `all_files_covered`, `missing_files`, `candidate_count_total`, `candidate_count_reviewed`, `truncated`, `scenario_coverage`, `native_windows_status` et `status`. Toute source erreur, absence de preuve obligatoire, troncature non résolue ou SHA différent interdit `COMPLETE_PASS`. Les scans FAST bornés restent possibles **mais obligatoirement marqués PARTIAL**, jamais remplacés par un banc de test concurrent.
8. **Recette** : fixtures dépassant 150 fichiers, 4 000 fonctions, 30 anomalies, imports dynamiques, Qt signaux et sources >512 Kio ; comparaison exhaustif vs lots paginés. Aucune suppression automatique de code sans preuve positive multi-source et tests fonctionnels ; audit commit par commit puis global.

**Limite fondamentale :** même avec inventaire statique exhaustif, on ne peut pas prouver automatiquement que tous les comportements possibles de Python/Qt ou toutes les configurations utilisateur ont été exécutés. Afficher exactement la couverture de scénarios revendiquée, et classer les scénarios non observés `NOT_RUN` plutôt que d'affirmer « 100 % de comportement » à tort.

## Obligation nouvelle — style et cohérence UI Unity / Launcher (OPT-STYLE)

### Ce qui existe déjà et ce qui n'est pas certifié

- `app/ui/unity_skin.py` fixe `UNITY_PALETTE`, les règles globales, sprites/bordures, focus et fonds ; `unity_enabled()` retourne toujours vrai : le thème Unity est la référence, non un thème alternatif.
- `app/ui/theme.py` centralise `PALETTE`, `TYPOGRAPHY`, `SPACING`, `SIZES`, les tokens QSS et un catalogue conséquent de `LEGACY_COLOR_ROLES` / `LEGACY_LITERAL_ALIASES`. Ces **alias de compatibilité** ne prouvent pas que tous les styles historiques ont disparu, ni qu'ils sont tous visuellement corrects.
- `tests/test_unity_skin.py` teste tokens, sprites locaux, fallback, focus et quelques sélecteurs. Les tests Doctor UI effectuent des interactions/captures Qt, mais **aucune comparaison visuelle exhaustive Windows native n'est démontrée**. La présence d'un QSS valide ne prouve pas un rendu pixel, une police ou une mise en page.
- Le Launcher V2 peut utiliser des fenêtres Tk alors que l'application est en Qt ; une apparence Unity équivalente et une seule transition fluide doivent être **testées dans #285**, pas présumées par les constantes de palette.
- Les polices et sprites personnels restent des assets **locaux facultatifs** hors release publique ; ne pas diffuser d'assets ou polices protégés. Valider **avec et sans** assets locaux pour le fallback public.

### Audit visuel exhaustif à intégrer à Doctor, sans second moteur UI

1. **Inventaire de tous les composants graphiques** : chaque page/fenêtre/menu/dialogue/popup et états réels (normal, hover, pressed, focus clavier, disabled, selected, chargement, erreur, vide, scrollbar, infobulle, navigation, dock). Comptabilité des composants non couverts et des sélecteurs QSS sans consommateur ou masqués par priorité/cascade Qt.
2. **Style commun** : couleurs et transparence dérivées des tokens Unity, typographies/taille/gras, espacement, bordures, rayons, iconographie, fonds, boutons, barres, checkboxes, onglets, panneaux, raccourcis ; identifier les **littéraux codés en dur** et anciennes règles QSS, corriger leurs consommateurs avant suppression. Privilégier des rôles sémantiques plutôt que remplacer aveuglément les couleurs d'alerte.
3. **Cohérence du launcher** : la même identité visuelle, tailles de police et boutons entre Tk et Qt ; passage mise à jour → lancement dans la même fenêtre visible, progression vérifiable et états d'erreur ; contrat et implémentation de ce point **#285**.
4. **Comparaison visuelle automatisée** : captures par scénario et état depuis le **même SHA**, résolution, DPI, polices et données. Diff perceptuel avec zones dynamiques masquées et seuils par famille de composant ; toute divergence inattendue doit être examinée humainement, **pas corrigée en acceptant la nouvelle baseline sans justification**.
5. **Windows réel + matrice d'affichage** : DPI 100/125/150 %, 1080p/1440p/4K, petite fenêtre, textes longs/français, défilement et listes volumineuses, thème avec assets/fallback ; vérifier contenu coupé, chevauchement, contrastes, focus clavier, lisibilité, accessibilité, alt/icon et usage souris/clavier. Qt hors écran seul = preuve partielle.
6. **Mesures coût du style** : latence du premier rendu, CSS/QSS recalculé, polices chargées, pixmaps et sprites reconstruits, temps de paint, coût des effets, tailles de widgets, freezes et RAM par écran ; corréler à Graphify pour savoir **quel composant** introduit régression visuelle ou performance.
7. **Qualité / style du code** : inventaire complet règles Python/Qt et formats : répétitions QSS, helpers styles dupliqués, constantes magiques, fonctions trop complexes, imports inter-domaines, exceptions silencieuses, normes de nommage et contrats type. Mettre des linters ciblés sur **tout le périmètre déclaré**, publier le décompte de violations et distinguer dette existante de régression, sans reformatage massif créant des régressions.
8. **Gates et preuves** : rapport `ui_style_coverage.json` avec `sha`, `screens_total/screens_tested`, `states_required/states_tested`, `styles_consumer_coverage`, `screenshots_compared`, `fallback_tested`, `native_desktop_tested`, `errors`, `truncated` ; style `PASS` uniquement si le périmètre requis est entièrement testé et conforme. La couverture **statique** des tokens et celle du **rendu natif** doivent être deux statuts distincts.

### Ordre d'exécution et dépendances

- **Immédiat en ciblé** : détecter les anciens styles QSS, problèmes de sélecteurs, valeurs codées en dur, doublons de déclarations, inventaire de pages/contrôles ; résultat `REVIEW` si la preuve du rendu manque.
- **Après correctifs UI** : campagne de captures Qt avec tous scénarios obligatoires ; budget latence et visuel par écran. Conserver les tests existants, **aucun duplicata** d'outillage.
- **Avant release** : validation du launcher + fenêtres Qt **Windows natif**, sur EXE exact-SHA et cas de fallback ; preuve par DPI et état, audit d'identité visuelle finale.

**Statut : `TODO`.** L'ajout de cette exigence au document et à la PR ne constitue pas l'implémentation du moteur d'audit visuel ou la certification d'exhaustivité.


## Lot implémenté : inventaire statique Doctor (à certifier)

Commits de la PR #303 : `tools/atlas_doctor_lib/full_scope.py`, commande `full-scope` de `tools/atlas_doctor.py`, tests `tests/test_atlas_doctor_full_scope.py`, exécution stdlib Draft dans `scoped-pr-ci.yml`.

- `python -m tools.atlas_doctor full-scope --json --output artifacts/doctor_full_scope/report.json` : parcourt **tous les Python suivis Git**, sans plafonds 150 fichiers/4 000 fonctions ni limite source 512 Kio, inventorie les fichiers Git suivis par famille (JSON, QSS, assets), classe les doublons AST, exceptions silencieuses, imports internes suspects et styles QSS locaux. Source erronée, absente ou worktree sale = `BLOCKED` ; SHA exact possible avec `--expected-sha`.
- `python -m tools.atlas_doctor full-scope --with-graph --json` : réutilise le graphe Graphify **déjà construit et exact-SHA**, audite toutes les sections paginées existantes sans troncature et refuse `BLOCKED` si le graphe manque/est périmé ; ne génère pas le graphe implicitement.
- Les JSON/assets sont actuellement **inventoriés**, non parsés/vérifiés en totalité ; les signaux Qt dynamiques, le rendu Unity et le launcher Windows natifs sont toujours `NOT_RUN`. Le verdict global reste donc `REVIEW` même si la couverture statique Python vaut `PASS` ; aucune certification de l'application entière n'est revendiquée.
- Les tests couvrent des fixtures dépassant les anciens plafonds, les mauvaises sources, le SHA, les rapports confiné sous `artifacts/`, la couche style statique, le graphe manquant et l'intégration CLI. **Ne pas remplacer une mesure réelle par une hypothèse statique.**

### Validation de l'inventaire réel (CI Draft)

Le job existant `Scoped PR Feedback / PR / Stdlib Scope Plan` exécute désormais `Doctor full-scope` directement sur l'exact HEAD GitHub, sans Qt, rebuild Graphify ou FULL concurrent. Le JSON intégral est archivé dans le même artifact que le mini-audit Doctor : `artifacts/doctor_full_scope/report.json`. Le contrôle refuse les sources Python manquantes, illisibles, non analysées ou l'inventaire tronqué ; il vérifie le compte `total == inspected`, le SHA exact et le statut `REVIEW` (jamais `COMPLETE_PASS`). Si cette étape échoue, publier son échec avant toute prétention de certification ; les tests antérieurs ne suffisent pas. Aucun résultat réel n'est anticipé ici : lire le run du nouveau commit.

### Graphify réel, exact SHA, sans réimplémentation du graphe

Pour les changements du moteur Doctor/Graphify, la nouvelle entrée `doctor-full-scope-graphify.yml` **appelle le workflow Graphify canonique déjà existant** (pas un second générateur). `graphify-map.yml` exécute ensuite `Doctor full-scope --with-graph` sur le même checkout SHA, vérifie la couverture de tous les Python et le verdict de dépendances sans troncature, puis archive la preuve `graphify-out/doctor_full_scope.json`. Une mauvaise correspondance de commit ou une anomalie d'architecture confirmée bloque ce test. Les signaux Qt et l'apparence Windows native restent des validations distinctes : même une carte Graphify complète ne prouve pas tous les comportements dynamiques.


---

## Annexe d'exécution — anomalies réelles Doctor + Graphify (30 octobre 2026)

**Ce chapitre complète les 36 actions OPT-P0..P3 qui précèdent : ce sont des sous-tâches de réalisation et des preuves nouvelles, non 30 nouveaux chantiers autonomes.** Ne jamais écraser les relevés historiques. Aucun de ces contrôles ne passe à DONE par la seule rédaction de cette annexe.

### Baseline mesurée, provenance et portée

| Preuve / SHA | Ce qui a vraiment été mesuré | Ce qui n'est PAS démontré |
|---|---|---|
| [Doctor full-scope #41033795200](https://github.com/r9327/Dof-Atlas/actions/runs/41033795200), SHA `0c405ded` | **1176/1176** fichiers Python suivis ; **11435** fonctions ; **0** parse error, **0** fichiers omis ; **211** groupes AST identiques, **242** gestionnaires d'exception candidats, **15** sites QSS locaux, **419** JSON et **73102** assets visuels inventoriés | Pas 211 bugs, pas 242 bugs ; les contenus JSON et les images ne sont pas tous validés, Qt natif NOT_RUN |
| [Graphify exact-SHA #41034529375](https://github.com/r9327/Dof-Atlas/actions/runs/41034529375), SHA `863af641` | **1176/1176** Python représentés, **16246 nœuds**, **46935 relations**, **345 candidats faiblement connectés**, **6 nœuds orphelins**, **137 communautés isolées**, **65 communautés à faible cohésion**, **4 cycles d'import candidats**, sans import interdit app→tools confirmé | Les signaux Qt, imports conditionnels, scripts externes, données et fonctionnalités runtime ne sont pas tous prouvés connectés |
| [Navigation courte #41034529121](https://github.com/r9327/Dof-Atlas/actions/runs/41034529121), SHA `863af641` | **60/60** passages PASS, préload court **9157,38 ms**, pic process-tree **210,85 Mio**, dernier Home **124,44 Mio** | Route PASS ≠ contenu détaillé vérifié, 5 routes de type placeholder restent distinctes |
| [Guides complets #41034529104](https://github.com/r9327/Dof-Atlas/actions/runs/41034529104), SHA `863af641` | **26 guides ×2, 52/52** ouvertures PASS ; p50/p95/p99 **260,19 / 3918,98 / 10525,35 ms** ; **27 gels Qt >250 ms** ; pic process-tree **308,57 Mio** | PASS fonctionnel ≠ seuil de performance PASS, Qt offscreen ≠ vrai bureau natif |
| [Phase 8 comparable #41019075070](https://github.com/r9327/Dof-Atlas/actions/runs/41019075070), SHA `9128e7ca` | Préload constructeur **22,91 s**, quête riche **7,08 s**, succès riche **5,43 s**, guide Bonta **2,48 s** et parcours combiné **38,17 s** (régression +1,10 s, 1 échantillon) | Ne pas additionner/comparer ces chiffres au préload court d'un autre scénario |

**Important :** les valeurs varient entre runs indépendants. Ne pas attribuer les fluctuations à un gain ou à une régression de code sans répétitions comparables sur mêmes machines/données/paramètres, avec p50/p95 et cold/warm.

### P0 — Corrections visibles et mesurables (bloquants performance)

| ID | Constats / priorité | Action, test obligatoire et propriétaire |
|---|---|---|
| **AX-01** | **32,34 s** exclusifs pour `ManualRouteGuidesView.ensure_catalog_manual_view` (Sylvestre cycle 2) | **OPT-P0-03/OPT-P2-18** — Profiler construction service/catalogue/vue et quantité de cartes ; supprimer les calculs répétés, charger par étapes, garder le comportement du Guide et les étapes inchangés. Mesurer cycle 1 ET cycle 2 sans charge intrusive. |
| **AX-02** | Sylvestre cycle 2 **38,00 s** (un autre run : 42,89 s) | **OPT-P0-03/OPT-P1-12** — Tracer route sélection → premier contenu prêt ; exclure les faux gains de simple sélection d'onglet. Tester au moins cold+warm et chemins d'étapes. |
| **AX-03** | Guide complet carte 134/267 **9,81 s** | **OPT-P0-03/OPT-P2-18** — Réduire le coût des checkpoints, des grandes listes et des widgets construits hors champ ; garantir validation/précédent/suivant, états cochés et images. |
| **AX-04** | `GuidesView._populate_guide_info` **7,09 s** instrumentés ; 27 gels Qt >250 ms dans la campagne | **OPT-P1-11/OPT-P1-12** — Attribuer coût calcul / accès JSON / Qt, garder l'UI réactive, réduire les blocages au même checkpoint. |
| **AX-05** | Pic mémoire Guides **308,57 Mio** pour une cible **≤250 Mio** | **OPT-P1-07/09/10** — Profil allocations et processus ; dédupliquer caches, fermer workers et widgets hors écran, conserver la progression. Retester tous les guides sur mêmes conditions. |
| **AX-06** | Dernier Home **124,44 Mio**, objectif stabilisé **<100 Mio** | **OPT-P1-08/13** — Mesurer mémoire retenue par module/cache, observer plusieurs retours Home, différencier caches intentionnels et vrais leaks. Pas de `gc.collect()` cosmétique. |
| **AX-07** | Préload court **9,16 s** et préload Phase 8 **22,91 s**, protocoles différents | **OPT-P0-02/06/OPT-P2-20** — Instrumenter leurs phases séparées (guide/quest/success), détection cache warm/cold, supprimer les double-warmups et bloquages du thread UI. |
| **AX-08** | Quête enrichie **7,08 s** (3,19 s enrichissement ; 2,55 s étapes ; 0,98 s noms/liens) ; succès **5,43 s** | **OPT-P0-04/05 et OPT-P2-15..17** — Profil interne, caches/index réellement réutilisés et rendu complet, pas seulement ouverture du menu. |
| **AX-09** | Launcher utilisateur observé bloqué à **75 %** (cause non reproduite) | **OPT-P0-01 / PR #285 uniquement** — Diagnostiquer vraie installation, réseau/disque/assemblage/SHA, progression réelle et récupération ; garder le même launcher et fenêtre de deux phases, sans réimplémenter dans #303. |

### P1 — Corriger la cause et l'architecture à partir des candidats (sans faux positifs)

| ID | Inventaire mesuré | Action et preuve à obtenir |
|---|---|---|
| **AX-10** | **211 groupes AST identiques** sur 11435 fonctions | **OPT-P3-32** — Passer **tous** les groupes en revue (pagination, aucun résultat masqué). Déprioriser trivialités/tests/accès identiques, confirmer les responsabilités dupliquées via appels réels et contrats avant fusion de code. Étiquettes `CONFIRMED / INTENTIONAL / FALSE_POSITIVE / NEEDS_RUNTIME`. |
| **AX-11** | **242 exceptions silencieuses candidates**, dont **183 dans `app/`** | **OPT-P3-30** — Classer chaque occurrence selon fallback attendu, corruption masquée, diagnostic manquant et sécurité des données. Prioriser `app/network/character_runtime_decoder.py`, `build_fingerprint.py`, `quest_snapshot_decoder.py`, puis `app/windows/unity_windows.py`. Tests d'erreur/fallback, aucune exception réécrite à l'aveugle. |
| **AX-12** | **345 candidats de nœuds faibles** | **OPT-P3-31** — Corréler Graphify avec entrypoints, méthodes appelées dynamiquement, événements Qt, conditions feature-flag et traces runtime avant classement. Aucun « fichier mort » uniquement à cause du degré du nœud. |
| **AX-13** | **6 nœuds orphelins** : un `app/services/__init__.py` et cinq scripts PowerShell de `tools/` | **OPT-P3-31/32** — Vérifier invocation par ligne de commande/CI/setup externe et rôle de paquet Python ; ne pas supprimer une entrée PowerShell sur simple absence d'import. |
| **AX-14** | **137 communautés isolées**, **65 candidates à faible cohésion** | **OPT-P3-31** — Prioriser communautés de production et flux critiques avec consommation mesurée ; sortir un verdict par communauté, distinguer sous-systèmes volontairement autonomes. |
| **AX-15** | **4 cycles d'import candidats** | **OPT-P3-31** — Qualifier leur nature `IMPORT_TIME / DEFERRED / TYPE_ONLY` et prouver un éventuel coût/bogue au démarrage ; corriger seulement les cycles problématiques (macros/runtime_state, deux vues Guide, guides_view/quest_detail_view, quest_catalog/quest_catalog_details). |
| **AX-16** | `app/modules/encyclopedia/widgets/progress_card.py` apparaît dans une île du graphe | **OPT-P3-28/31** — Identifier l'instanciation / connexion de ce widget, inspecter les appels Qt et tests de rendu avant verdict `UNUSED`. |
| **AX-17** | **0 imports internes suspects** dans la sonde AST actuelle | **OPT-P3-33** — Ne pas conclure que tous les liens sont valides : ajouter les imports dynamiques, les callbacks Qt, les ressources par chemins, les sous-processus et plugins aux preuves de couverture. |

### P1 — UI Unity, styles, signaux et accessibilité

| ID | Constat | Correction / recette obligatoire |
|---|---|---|
| **AX-18** | **15 appels `setStyleSheet` locaux** dans 4 fichiers | **OPT-STYLE** — Vérifier `guide_catalog_view.py` (3), `guide_featured_home.py` (4), `shared_manual_guide_view.py` (7), `preload_popup.py` (1). Comparer chaque effet aux tokens Unity et aux règles QSS, supprimer seulement les overrides prouvés redondants ou incohérents. |
| **AX-19** | Présence du thème Unity ≠ rendu identique | **OPT-STYLE** — Capturer tous les écrans/composants/états répertoriés : normal, hover, selected, pressed, disabled, focus clavier, loading, empty, erreur, dialogues et popups. Comparer sur le **même SHA** à baseline visuelle verrouillée. |
| **AX-20** | Qt offscreen ne prouve ni disposition Windows ni identité launcher | **OPT-STYLE + #285** — Tests bureau Windows natif DPI 100/125/150 %, petites fenêtres/1080p/1440p/4K, polices/sprites locaux facultatifs et fallback public ; contrôle contrastes, débordements, tailles de cibles, alignements et navigation clavier. Aucun asset privé diffusé. |
| **AX-21** | Connexions Qt/menus pas entièrement observées | **OPT-EXH / OPT-P3-28/29** — Matrice signal→slot→action→résultat, boutons inopérants, slots déconnectés, vues fantômes, 5 routes `placeholder`, menus réels, modals et interactions profondes. Distinguer `TESTED` / `NOT_RUN` / `BLOCKED`. |
| **AX-22** | Conventions et littéraux UI historiques | **OPT-STYLE / OPT-P3-30/32** — Audit code QSS/palette/typo/espacement/îlots style, sélecteurs masqués, widgets non couverts, contrastes et effets coûtant CPU/RAM ; limiter les changements aux différences prouvées. |

### P2 — JSON, assets, préload et provenance complète

| ID | Constat | Correction / preuve |
|---|---|---|
| **AX-23** | **419 JSON suivis inventoriés**, contenu non intégralement certifié | **OPT-P2-15..20/OPT-EXH** — Parcourir et parser chaque JSON **disponible**, rapport 419/419 ou expliciter manquants/pointeurs LFS ; vérifier schéma, doublons métier, IDs, relations, noms, progression, images et compatibilité avant/après. Aucun accès à l'état privé non suivi. |
| **AX-24** | `quests_enriched.json` 68,97 Mio, `image_manifest.json` 26,93 Mio | **OPT-P2-15..17/19** — Tracer requêtes réellement faites, index offsets/SQLite, gzip, coûts de compilation/relecture/copie, mesure cold+warm et données bit/semantiquement équivalentes. **Ne pas** migrer vers SQLite sans gain prouvé. |
| **AX-25** | 189 variantes `_vN` des routes ; 124 Ganymède candidats et traces dans Guides | **OPT-P2-19/OPT-P3-32** — Graphier chaque source→manifest→consommateur→packaging→cache ; classer `ACTIVE / ARCHIVE / GENERATOR_ONLY / UNUSED_CONFIRMED / REVIEW` ; aucune suppression sur simple ressemblance de nom. |
| **AX-26** | **73102 assets visuels inventoriés** | **OPT-P3-28/32/STYLE** — Vérifier les références actives et le packaging (image manquante, pointeur LFS, doublon réellement équivalent, sprite absent), pas l'ouverture individuelle manuelle des images ; rapport exhaustif des chemins contrôlés. |
| **AX-27** | Pistes de références JSON littérales nombreuses, connexions runtime incomplètes | **OPT-P2-15/OPT-P3-33** — Associer le fichier JSON à ses readers, cache, serializers, générateurs, routes, écrans et métriques de runtime ; afficher `NO_CONSUMER_CONFIRMED` seulement si analyses indépendantes convergent, sinon `REVIEW`. |

### P2/P3 — Doctor, gates, méthode de correction et livraison

| ID | Travail | Critère de clôture |
|---|---|---|
| **AX-28** | **OPT-EXH / OPT-P3-25..29/33** — Rapport Doctor croisé Graphify + benchmarks + données + Qt (fichier/ligne, symbole, dépendances, appels, wall/CPU/RAM/IO, scénario/cold-warm, preuve et degré de confiance), sans second moteur ; inventaire total/analysé/exclus/bloqué, provenance exacte du SHA. | Aucune source/scénario non couvert ne passe `COMPLETE_PASS` ; résultats longs paginés et comptés, rapport explicite `NOT_RUN` pour Windows natif ou flux non testé. |
| **AX-29** | **OPT-P3-34/35** — CI réellement ciblée et seuils de régression : Home stabilisé <100 Mio, pic ≤250 Mio, budgets par vrai contenu / p95 / gels Qt et marge contrôlée 5 %. N'exécuter FULL qu'après les gros lots/règles exigeant FULL ; préserver exact SHA et les gardes Windows. | Comparaison statistiquement pertinente (plusieurs répétitions, mêmes conditions) ; aucun PASS si une sonde obligatoire est SKIPPED, si un rapport manque ou si le budget est dépassé. |
| **AX-30** | **OPT-P3-36** — Dev par lots B/C/D/E, audit de **chaque commit**, audit global, vérifications de non-régression des quêtes/succès/guides/progression/manifestes, test install/update dans #285, synchronisation vers APP seulement après garde. | Tableau `TODO / IMPLEMENTED / VERIFIED / BLOCKED` par item et lien commit + run + artefact ; zéro suppression spéculative, aucune modification de données personnelles et verdict final documenté avant fusion. |

### Priorité de correction concrète et non-duplication des PR

1. **En parallèle :** blocage launcher dans **#285**, sans doublon dans #303 ; **Doctor/Graphify dans #303**, garder l'outil canonique.
2. **Premier lot performances dans #303** : AX-01 à AX-04 (vrais contenus Guides), AX-07/08 (préload/quête/succès), test régressions ciblé.
3. **Deuxième lot mémoire** : AX-05/06 ; puis AX-10/11/15/16 selon preuves de cause profonde (un candidat statique seul n'impose pas de refactor).
4. **Données et couverture** : AX-12..14/17, AX-21, AX-23..27 ; tests d'intégrité, liens dynamiques, revues des candidats par lots sans omissions.
5. **UI et clôture** : AX-18..22 puis AX-28..30, capture Windows native / vérification release, certification ciblée + finale.

### Définition du « terminé »

- `STATIC_COVERAGE` : tous les Python suivis réellement analysés et graphe exact-SHA ; chaque anomalie candidate a un statut et une preuve, même si elle est classée bénigne.
- `DATA_COVERAGE` : tous les JSON suivis **disponibles** inspectés avec résultat `VALID / INVALID / NOT_AVAILABLE / REVIEW`, sources et références actives attestées ; fichiers LFS absents non présentés comme PASS.
- `RUNTIME_COVERAGE` : chaque fonctionnalité annoncée a une action et un résultat observés ; cas `NOT_RUN` visibles ; les 5 placeholders ne comptent jamais comme 5 vraies fonctionnalités validées.
- `VISUAL_COVERAGE` : fenêtres, contrôles et états sur Qt + Windows natif, comparaison Unity, DPI, fallback ; même traitement du launcher dans #285.
- `PERFORMANCE_COVERAGE` : temps avant vrai contenu, CPU/RAM/IO par module, gels Qt et process-tree testés sur mêmes scénarios, seuils non abaissés.
- `RELEASE` : audit commit par commit + transversal final, statut vérifié à l'exact HEAD, CI pertinente et artefacts, sans sortie de Draft ni fusion sur une seule réussite de tests techniques.

**État de cette annexe : TODO/REVIEW ; seuls les contrôles statiques précédemment livrés sont IMPLEMENTED/TESTED. Les optimisations de latence, le nettoyage et le rendu Windows natif restent NON LIVRÉS.**
