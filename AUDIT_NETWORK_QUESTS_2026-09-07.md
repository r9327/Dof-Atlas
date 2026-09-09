# Audit réseau et chargement Quêtes — 7 septembre 2026

## Périmètre et état final

Correctifs locaux validés automatiquement. Le réseau complet en jeu n'est **pas déclaré rétabli** : aucune capture de reconnexion réelle n'a été effectuée pendant cet audit. Aucune manipulation clavier, souris, fenêtre native ou navigateur du poste. Les essais Qt utilisent exclusivement le mode offscreen et des fichiers de progression temporaires.

Le diagnostic local consulté pendant l'audit indiquait `mapping_no_exact_match`. Le répertoire `data/network/protocol_mappings` ne contenait que son README. Le build détecté était `bb365710c18d32608db03e11902b4fc16b2264da1c6acc795b00b5c92811fe64`. Ce constat est un instantané, pas une preuve que le protocole du jeu ne transmet pas les données manquantes. Aucun mapping n'a été inventé ou installé.

## PERSONNAGES

Causes démontrées dans le code et les tests :

- La calibration enregistrait l'identité mais ne la notifiait pas indépendamment des preuves de quêtes. La liste pouvait donc ne pas être activée malgré une identité apprise.
- Une identité acceptée sans modification de progression était éliminée par le runtime avant d'atteindre les consommateurs Qt.
- Le repli par PID pouvait associer le nouveau nom d'un personnage à l'ancien ID occupant le même processus. Un titre générique avec un PID réutilisé était également considéré comme preuve suffisante pour récupérer une session.
- Une ancienne session encore ouverte pouvait remplacer le niveau/profil d'une reconnexion plus récente.

Corrections : file de notifications d'identité indépendante de la certification des quêtes, transmission des identités acceptées même sans écriture, refus des replis ambigus, et propriété du profil réservée à la dernière session identifiée. La calibration alimente aussi le modèle volatile des caractéristiques vérifiées. L'état local consulté exposait déjà un personnage canonique connecté : le symptôme utilisateur complet n'a donc pas été reproduit de bout en bout.

État : **RÉPARÉ sur scénarios automatisés ; accès réel après reconnexion à confirmer.**

## RÉSEAU GLOBAL

| Domaine | État | Preuves et limites |
|---|---|---|
| Personnages | RÉPARÉ / validation réelle restante | Identité indépendante du journal, garde de reconnexion et test de PID recyclé. Aucun contournement de l'identité vérifiée. |
| Skins | PROBLÈME RESTANT | `CharacterPage` accepte un résolveur de skin optionnel ; le shell ne le fournit pas. Aucun décodage actuel vérifié ne relie une apparence reçue à ce consommateur. Ce n'est pas une preuve d'absence dans le protocole Dofus. |
| Équipements | PROBLÈME RESTANT | Emplacements visuels sans alimentation réseau d'inventaire/équipement. La page de construction d'équipement reste un outil distinct. Aucun champ réseau supposé n'a été ajouté. |
| Succès | FONCTIONNEL pour les conséquences des quêtes ; PROBLÈME RESTANT pour le flux natif | Le pont de progression et la cohérence Quêtes/Guide/Succès sont testés. Le mapping courant ne prouve pas les événements natifs de succès ni le score réel. Les sommes de points déduites d'une forme de paquet ont été désactivées. |
| Quêtes | FONCTIONNEL sur événements vérifiés testés ; validation réelle restante | Le profil revu utilise l'identité `kvi/kva`, la fin d'étape `idz` contrôlée contre la dernière étape locale, et le rattrapage additif du journal `idr` sous ses garde-fous de calibration. Les contrats génériques de début/objectifs ne constituent pas un mapping actif. |
| Niveau et statistiques | FONCTIONNEL sur fixtures vérifiées | Niveau de sélection `kva` et statistiques revues `kub` conservés. Les alias historiques et formes répétées de paquets inconnus ne prouvent plus un niveau ou un score de succès. |
| Autres paquets | NON UTILISÉ | Le trafic non mappé reste ignoré ; il ne doit pas muter la progression. |

### Chaîne réelle et propriétaires

`main.build_quest_preload` fournit le contexte à Home, puis à `NetworkUiBridge`. Le bridge Qt draine les résultats avec son timer de 180 ms ; il ne fait ni capture ni écriture métier. `NetworkApplicationCoordinator` possède le travail de coordination dans son worker et sélectionne calibration ou runtime vérifié.

La source Windows élevée partagée dialogue avec le helper par IPC JSON authentifié. Le helper choisit Npcap ou le repli WindowsRaw ; les flux TCP sont associés aux processus et réassemblés avant extraction des messages Protobuf. Les décodeurs contrôlés, le normaliseur et le pont de progression relient ensuite les événements à `character:<id>`. Les services Quêtes/Succès restent les sources de progression, le Guide en consomme les conséquences. Les résultats reviennent par files puis signaux Qt. Le shell adresse désormais explicitement sa page Encyclopédie ; le polling réseau ne scanne plus `QApplication.allWidgets()`.

### Erreurs, arrêt, files et dette restante

- Une rupture IPC remonte comme `capture_helper_disconnected`, arrête le lecteur et actualise le statut du contrôleur. Elle ne laisse plus un lecteur actif tourner sur une source fermée.
- Les erreurs Protobuf d'un type explicitement mappé sont journalisées une fois par type ; les transitions de statut et les échecs de recherche des handles sont visibles. Le trafic ordinaire inconnu ne remplit pas les logs.
- L'ambiguïté entre mappings exacts est distinguée de l'absence de mapping.
- Les files de résultats ne tronquent pas arbitrairement les événements acceptés : le test injecte et récupère 5 000 notifications. Cela prouve cette file, pas une garantie de capture réseau exhaustive.
- Les trames IPC ont une limite de 16 MiB ; la file de course des commandes a une borne avec erreur explicite. Les files métier non bornées gardent un risque de croissance si un consommateur ne suit plus.
- **Limite conservée :** lors d'une pause/transfert/fermeture, les trames de transport restantes de la session sortante ne sont pas rejouées dans le nouveau runtime. Leur abandon est maintenant signalé hors debug. Garantir « aucun événement critique perdu » sur toute la capture et ces frontières n'est pas établi. Rejouer aveuglément dans une nouvelle identité serait dangereux ; aucune nouvelle logique de rejeu intersession n'a été introduite.
- Le lancement global élevé, l'organisation des fenêtres et les garde-fous du helper n'ont pas été refondus.

## PERFORMANCE QUÊTES

Avant : `QuestCatalog.load` matérialisait toutes les fiches, étapes, objectifs, récompenses et enrichissements, même depuis le cache JSON. L'arborescence Qt était déjà partiellement différée : il serait faux d'attribuer une réduction du nombre initial de widgets à ce lot.

Après : le catalogue normal contient les métadonnées nécessaires aux noms, niveaux, zones, prérequis, filtres et suites. Les cinq ensembles documentaires (`steps`, `rewards`, `source_info`, `source_solution_steps`, `solution_blocks`) sont compilés seulement à la demande. Le chargeur documentaire existant reste utilisé.

Un cache SQLite reconstructible est nommé par signature des sources et du chargeur. Il ne contient aucune progression. Un LRU garde au maximum 32 fiches compilées ; l'éviction peut relire une fiche du cache disque sans recompilation. Les sources JSON monolithiques sont indexées en positions d'octets, avec au maximum 128 valeurs brutes conservées par source. La première indexation lit temporairement le texte d'une source et décode ses membres successivement ; elle ne conserve pas le dictionnaire entier ni toutes les fiches. Les handles sont fermés après compilation. Une génération de catalogue ancienne ne compile pas des sources ayant changé.

Le worker de détail ne touche aucun widget. Une seule demande est compilée à la fois et seule la sélection courante est rendue par Qt. Les sélections intermédiaires ne provoquent pas une multiplication de workers. A → B → A réutilise les données de A. La recherche enrichie ne démarre qu'à une demande atteignant le seuil existant ; elle parcourt les données par lots de 32, sans enrichissement documentaire ni remplissage du cache des fiches. Son index textuel complet reste un coût à la première recherche. Le préchauffage du graphe ne construit plus cet index riche ni toutes les fiches.

### Mesures

Windows, Python 3.13.15, PySide6 6.11.1 ; processus de benchmark offscreen, 1 976 quêtes locales, profils temporaires, sélection 1847 → 1441 → 1847. Valeurs d'une exécution par scénario, pas des percentiles ni des mesures du lancement complet d'Atlas.

| Mesure | Avant cache chaud | Après cache chaud | Avant sans cache | Après sans cache |
|---|---:|---:|---:|---:|
| Catalogue + liste | 1,509 s | 0,110 s | 19,118 s | 0,737 s |
| RSS après liste | 220,3 Mo | 65,1 Mo | 598,2 Mo | 110,8 Mo |
| CPU consommé entre début et liste | 1,500 s | 0,125 s | 18,141 s | 0,688 s |
| Widgets initiaux | 72 | 72 | 72 | 72 |
| Première fiche A, après liste | 0,093 s | environ 0,10 s | 0,063 s | 3,261 s |
| Fiche B, après A | 0,010 s | environ 0,04 s | 0,008 s | 0,423 s |
| Retour A | 0,034 s | environ 0,03 s | 0,026 s | 0,032 s |

À cache chaud : environ **−93 % de temps catalogue/liste et −70 % de RSS du processus après liste**. Sans cache, la première fiche paie encore l'indexation des sources ; le temps jusqu'à la première fiche reste environ 4 s contre 19,2 s auparavant. Après A/B/A à froid, RSS mesurée autour de 207 Mo contre 607 Mo auparavant. Les lectures déclarées par Windows augmentent sur ce parcours froid (environ 308 Mo cumulés contre 249 Mo) : ce lot ne promet pas une baisse de tous les compteurs.

Limites : mémoire résidente mesurée à des points précis, pas pic mémoire ; CPU du processus, pas consommation système. L'espacement maximal observé de la boucle d'événements était environ 90 ms sur A froid et 164 ms sur B froid. Le processus passe de 4 à 14 threads dans ce parcours froid, contre 4 avec fiches en cache ; ce décompte inclut les bibliothèques et n'est pas le nombre de workers Quêtes (un worker de détail, un de recherche au maximum par page). Le CPU au repos, le démarrage complet, un redimensionnement visible et une session de jeu réelle n'ont pas été mesurés. Les anciennes générations de cache ne sont pas purgées automatiquement.

Reproduction : `python scripts/benchmark_quest_loading.py --cache-root <nouveau-dossier-cache>`, puis la même commande pour le scénario chaud. Les mesures brutes locales sont dans `.cache/network_audit/quests_before.json`, `quests_before_cold.json`, `quests_final_cold_v3.json` et `quests_final_warm_v3.json`. La référence froide a exécuté les modules de HEAD départ via un chargeur temporaire, en neutralisant lecture/écriture de leur cache ; le checkout n'a pas été remplacé.

## SOCLE

- `character:<id>` conservé ; aucune création de données `slot:N` ajoutée.
- Aucune migration legacy, aucun déplacement de progression, aucune modification volontaire des données personnelles.
- Guide / Quêtes / Succès restent synchronisés dans le test de fin de quête avec rechargement des trois surfaces. La synchronisation native de tous les succès en jeu reste distincte et non prouvée.
- Identifiants et métadonnées comparés pour les 1 976 quêtes : aucune différence avec le catalogue de référence. Onze fiches détaillées échantillonnées : aucune différence de champs sérialisés. Ce n'est pas une comparaison exhaustive des 1 976 documents enrichis.

## TESTS

Commande finale via `.cache/network_audit/run_validation.py` avec les motifs exacts suivants :

```text
test_character_page*.py
test_encyclopedia_character_sync_dedupe.py
test_progress_cross_surface_reload.py
test_network*.py
test_character_runtime*.py
test_known_session_recovery.py
test_lazy_quests_page_performance.py
test_quest_catalog_safe_cache.py
test_quest_catalog_details.py
```

**439 tests, 0 échec, 0 erreur, 0 ignoré ; 4,834 s.** Aucun traceback de worker dans cette sortie finale. Le runner interdit les écritures sous les répertoires réels `data`, `config`, `logs` ; les fixtures utilisent des dossiers temporaires. Les tests ajoutés couvrent notamment l'identité sans journal, le PID recyclé, l'ancienne session, la rupture IPC, le diagnostic borné, 5 000 résultats, l'éviction du cache, le changement de sources, les requêtes concurrentes, A/B/A, les index Unicode et la recherche par lots.

Passage complémentaire exact : `test_quest_graph*.py`, `test_quest_hierarchy*.py`, `test_lazy_quests_page_performance.py`, `test_quest_catalog_safe_cache.py` : **14 tests, 1 échec et 2 erreurs**, identiques sur les modules de départ et le code final. Il s'agit de l'assertion de préfixe de stylesheet dans `test_quest_hierarchy`, et de deux références au seuil supprimé du shim `quest_hierarchy_lazy_patch`. Ils n'ont pas été masqués par un changement de production. Un autre test de synchronisation, fragile aux guillemets produits par `ast.unparse`, a été corrigé pour inspecter les nœuds AST sans affaiblir sa vérification.

La baseline initiale réseau/cache comptait 410 tests et deux échecs : diagnostic d'ambiguïté corrigé, et ordre des personnages dont l'attente a été alignée sur l'ordre connecté d'abord déjà existant. `git diff --check` passe. Les benchmarks et la comparaison de données ont été exécutés. Pas de suite exhaustive de tout le dépôt ; pas de validation par capture/reconnexion réelle ni d'interaction physique avec l'application.

## GIT

HEAD départ : `2d38717cb0d556b96d7a64445b155ec3ea44ab7a`, branche `feature/guide-ultime-v5-ui`.

Commits de code :

- `c99b5f17` — Fix verified character notifications and network failure handling.
- `686be8798dc235ee361c39301f858025de3d7fc8` — Load quest documentary details on demand with bounded caching.

Le commit de ce rapport suit ces deux commits ; son hash final est donné dans la réponse et accessible avec `git rev-parse HEAD`. Aucun push.

Fichiers de code principaux : `app/network/{application_coordinator,bootstrap,calibration_bootstrap,calibration_controller,calibration_runtime,character_runtime_decoder,character_runtime_state,controller,elevated_capture,known_session_recovery,mapped_decoder,protocol_calibration,runtime}.py`, `app/ui/network_bridge.py`, `main.py`, `app/quest_catalog.py`, `app/quest_catalog_details.py`, `app/quest_source_index.py`, `app/pages/lazy_quests_page.py`, `app/pages/quest_graph_prewarm.py`, `scripts/benchmark_quest_loading.py`. Tests concernés : `test_character_runtime_decoder`, `test_encyclopedia_character_sync_dedupe`, `test_known_session_recovery`, `test_network_application_coordinator`, `test_network_calibration_catchup`, `test_network_character_slot_resolver`, `test_network_current_protocol_safety`, `test_network_audit_regressions`, `test_quest_catalog_details`.

Modifications personnelles déjà présentes au départ, exclues des commits : `data/encyclopedia/progress/achievement_progress.json`, `data/encyclopedia/progress/guide_progress.json`, `data/local/craft_selection.json`, `logs/start_log.txt`. Le dossier local de mesures est ignoré par Git.
