# PR #310 — État de réparation et preuves exact-SHA (31/10/2026)

**Portée :** cette page complète les [58 constats](pr310-full-audit-20261031.md) et le [registre maître](remediation_master.md). Elle ne réduit pas les obligations de vérification individuelle pour les signaux de Doctor ni la certification native Windows. État revu après le merge de la PR mère #303 dans la branche de réparation.

## Réparations codées et vérifications réellement obtenues

| Écart historique | Changement codé | Preuve contrôlée | État |
|---|---|---|---|
| A-01 / A-02 | Fusion de #303@`25ef753` dans #310@`3c22ea5a`, correction URI Sylvestre conservée et **deux tests de répertoire relatif** complémentaires | GitHub compare : 0 commit en retard sur #303 à cet instant, `mergeable=true`; Windows natif encore `NOT_RUN` | **Git FIXED_VERIFIED**, Windows PROOF_PENDING |
| A-03 / A-29 | Audit des patches sur HEAD Git dynamiques, sans compteur historique figé | [CI 41209627690](https://github.com/r9327/Dof-Atlas/actions/runs/41209627690) : 390/390 historiques #303 ; 421/421 ancêtres de #310, 6 tests scanner PASS, `human_review=NOT_RUN` | **Inventaire FIXED_VERIFIED**, analyse humaine OPEN |
| A-08 / A-10 / A-11 / C-01 / C-02 / C-05 | Export de **toutes** les références non résolues/unsafe/ambiguës et de tous les assets statiques non reliés, ajout des **JSON Pointer**, des clés JSON et des lecteurs dans `scripts/windows/` et `tools/` | [CI 41209627705](https://github.com/r9327/Dof-Atlas/actions/runs/41209627705) : 10/10 tests ressources, 28/28 tests full-scope, 3/3 tests SQLite ; export brut complet | **Export FIXED_VERIFIED**, qualification des chemins OPEN |
| A-09 / B-01 / B-02 / B-03 / C-08 / C-09 / C-10 / C-15 | Correctifs du scanner : extensions usuelles .json/.png/.qss/.svg/.webp/etc., exceptions typées, frontières RAM, assertions supprimées, décodage strict, timeout Git | 6 tests du scanner PASS au SHA `3c22ea5a`; nouveaux tests de provenance par fichier/ligne ajoutés ultérieurement | **Base FIXED_VERIFIED**, dernier test exact-HEAD à suivre |
| B-04 | Liaisons `alerte→fichier→ligne de diff` plutôt que compteur commit seul | Test inter-fichiers ajouté après le run 41209627690 ; ne pas revendiquer ce test comme passé avant nouvelle CI | **FIX_COMMITTED_PROOF_PENDING** |
| B-05 / B-06 / C-13 / A-30 | Événement `ready_for_review`, artefacts requis (`error`), Python 3.13 épinglé sur les deux workflows | Premier run de ressources PASS, scanner republié ensuite : vérifier le dernier HEAD | **FIX_COMMITTED_PROOF_PENDING** |
| B-07 / C-11 | SQLite `stat()` inclus dans le `try` et refus du flux zlib avec octets parasites | [CI 41209627705](https://github.com/r9327/Dof-Atlas/actions/runs/41209627705) : 3/3 tests de cache SQLite, dont course de fichier et corruption | **Contrats ciblés FIXED_VERIFIED**, vrai EXE NOT_RUN |

## Doctor : chiffres réellement observés sur `3c22ea5a91a9cdba9630b36c9c0c758e3d50729f`

| Mesure | Valeur |
|---|---:|
| Sources Python analysées | **1201 / 1201** |
| JSON syntaxiquement valides | **422 / 422** |
| Chaînes candidates contrôlées | **167253** |
| Références résolues statiquement (occurrences) | **165671** |
| Ressources de production recensées | **73495** |
| Ressources sans consommateur statique identifié | **33401** |
| Références littérales non résolues | **845** |
| Références littérales unsafe | **540** |
| Correspondances basename-only, non certifiées | **197** |
| Chaînes >320 caractères écartées avec compteur | **6240** |
| Chaînes URI écartées avec compteur | **193207** |
| Chaînes multi-lignes écartées avec compteur | **4937** |

Les 845+540+197 = **1582 références candidates** sont intégralement présentes dans l'artefact [PR310 Doctor static-all 41209627705](https://github.com/r9327/Dof-Atlas/actions/runs/41209627705) (artifact ID `13045727595`). La liste complète des **33401** ressources s'y trouve aussi. **Ce scan NE PROUVE PAS 1582 liens cassés ni 33401 fichiers inutiles.** Il inclut des références à des états utilisateur générés, des chemins d'images logiques et des outils de développement. Aucune suppression en masse n'est autorisée. Les artefacts GitHub expirent ; les inventaires doivent être reconstruits sur le dernier SHA plutôt que réutilisés hors contexte.

## Restant non clôturable

- **La PR #310 reste Draft**, sans fusion dans #303 ou `main` ni release. Toute validation relève de l'**exact HEAD final**.
- **Graphify exact-SHA, validation des 213 groupes AST, 253 exceptions, ressources dynamiques, quêtes/Succès/Ganymède, UI Unity et interactions**, classification de chaque signal `KEEP_VERIFIED / FIXED_VERIFIED` : **OPEN / NOT_RUN**.
- **RAM Home <100 Mio, pic process-tree ≤250 Mio**, latences froid/chaud/p95/p99, stabilité des vues et attributs de consommation : **aucune nouvelle mesure native comparable** depuis les corrections de Doctor.
- **Véritable distribution Windows** : précompilation Sylvestre, EXE, paquet, installateur, bootstrap sans Python, mise à jour/delta/rollback/choix dossier et launcher #285 : **NOT_RUN** sur la version réparée.
- **Revue sémantique commit par commit** : les 390 et 421 patches ont été inventoriés automatiquement, pas individuellement validés comme corrects. L'audit nouveau contient des commits de diagnostic ; toute nouvelle modification exige une preuve propre.

**Règle** : le tableau ci-dessus distingue les défauts de l'outil désormais corrigés de l'ensemble des anomalies produit encore à traiter. Pas de faux certificat FULL, aucune baisse des budgets.

## Lot ciblé — intégrité du cache et des preuves Doctor

Correctifs de code avec tests associés : valeur `ready=1` strictement exigée pour réutiliser le cache SQLite Quêtes (valeurs corrompues refusées sans crash), type booléen exact exigé pour `worktree_clean` dans les listes Doctor, et coordonnées de fichier/ligne réinitialisées dans l'audit des patches. Ces protections évitent respectivement un faux cache prêt, un faux état Git propre et une attribution erronée du risque. Tests : `test_startup_warmup_subprocess_flags.py`, `test_doctor_candidate_worklist.py`, `test_pr303_commit_audit.py`.

**Validation :** code et tests versionnés ; exécution locale Python/Windows et CI du nouveau SHA **NOT_RUN** au moment du commit. Pas de gain RAM revendiqué, aucun seuil abaissé, aucune suppression de données, aucune FULL déclenchée intentionnellement.

## Lot de fermeture des faux « complets » Doctor et du cache Quêtes

Le cache source-offset Quêtes contenant seulement un schéma SQLite mais **aucune ligne** dans `offsets` doit être reconstruit, et non accepté comme warmup terminé. Doctor refuse désormais de générer une worklist « exhaustive » depuis un rapport global ou liens `BLOCKED`, ou depuis un scan avec erreurs (même si les compteurs correspondent). Le scan des ressources classe comme `UNSAFE_RESOURCE_LITERAL_REVIEW` les littéraux avec espaces extérieurs ou segments `./`, `../`, `//` avant toute prétention de résolution ; aucun lien ou fichier n'est supprimé automatiquement. Les régressions sont enregistrées dans les trois modules de tests ciblés existants. **Code + tests ajoutés ; résultats Python/Windows, benchmark et FULL du HEAD nouveau à contrôler, pas de PASS anticipé.**

## Audit patch par patch : emplacement exact des assertions retirées

Le scanner `tools/audit_pr303_commits.py` conserve désormais, en plus du nombre et du drapeau `REMOVED_ASSERTIONS_REVIEW`, un champ `deleted_assertion_locations` par parent : fichier du diff et numéro de ligne **dans l'ancien fichier**. Les coordonnées sont réinitialisées à chaque fichier et à chaque hunk ; les lignes ajoutées continuent d'être attribuées au nouveau fichier. Le test cible deux fichiers, plusieurs hunks, et exclut les commentaires. Ce tableau d'alertes reste un **indice de revue de logique**, jamais une preuve de régression ni une approbation humaine. Exécution des tests du nouveau SHA à confirmer.

## Cas d'audit évités : exceptions nommées et suppression de `pytest.fail`

La détection consultative des nouveaux gestionnaires d'exception couvre à présent `except Exception as exc`, les tuples avec alias et `except*` (groupes d'exception Python), que l'ancienne regex omettait. La revue des assertions supprimées inclut les lignes `pytest.fail(...)` et conserve leur localisation d'origine. Tests unitaires dédiés ajoutés ; classification heuristique uniquement, aucune exception supprimée automatiquement et aucune revue humaine revendiquée. La validation doit porter sur l'exact HEAD final.

## Intégrité des artefacts multi-domaines à chaud

Le cache `app/startup_cache_warmup.py` exige que chaque fichier d'artefact annoncé par un worker soit un chemin de type chaîne exact (aucun booléen, entier, chemin tronqué ou espace de bord) et que deux artefacts ne résolvent jamais vers le **même fichier physique**. Le scanner refuse toute liste dupliquée en retour `[]` : ni un cache frauduleux ni deux alias d'un même index ne peuvent déclarer Guide/Quêtes/Succès prêts. Test ajouté pour les alias `cache.bin`/`./cache.bin`, les doublons, les valeurs malformées et le cas positif. Preuves d'exécution exact HEAD à consulter ; aucun seuil de performance abaissé.

## Correction de la source du cache Quêtes : SQLite disque

Le lecteur canonique `app/quest_source_index.py` refuse désormais aussi les bases `offsets` à schéma valide mais **zéro ligne** et reconstruit les index concernés à partir des sources JSON. Les connexions de contrôle et de lecture utilisent des URI SQLite **`mode=ro`**, empêchant de recréer une base vide si son fichier disparaît entre vérification et lecture. Deux tests dans `tests/test_quest_source_boundaries.py` couvrent reconstruction et course suppression/ouverture ; les connexions d'écriture du constructeur restent inchangées. Ces modifications ne prouvent pas de gain RAM ou p95 : elles corrigent les défaillances de cache sans affaiblir les contrôles.

## Patches historiques : tests entiers supprimés sans assertion explicite

Le registre technique est désormais capable de signaler la suppression d'une définition `def test_...` ou `async def test_...`, même lorsque la différence ne retire aucune ligne `assert`. Le nouveau champ `deleted_test_locations` conserve chaque ancien fichier, numéro de ligne et définition ; le drapeau `REMOVED_TEST_DEFINITIONS_REVIEW` est remonté au niveau du commit, en plus des assertions supprimées. Une suppression ou un renommage reste un **candidat à justifier**, pas une régression automatiquement prouvée. Test multi-fichier et test intégré `review()` ajoutés ; final PASS humain/CI jamais inféré du seul scanner.

## Warmup Guide : cache JSONL incomplet auto-réparé

Le worker qui prépare les Guides ne s'appuie plus sur la seule première ligne de métadonnées pour considérer le cache JSONL utilisable : il valide les lignes du fichier, exige au moins un enregistrement `guide` avec valeur structurée et **reconstruit une fois** si le fichier est vide ou corrompu, y compris si sa signature de source correspond encore. Après reconstruction, un fichier toujours incomplet provoque une erreur explicite au lieu d'annoncer le Guide prêt. Régression ciblée : header seul, JSONL tronqué, valeur nulle et cas positif. Le parsing est effectué dans le **worker jetable**, pas sur le thread UI.

## Contrat CI ciblé pour les lecteurs et workers de cache

**Audit de règle CI borné** : le workflow existant `.github/workflows/guides-focused-proof.yml` écoutait les modifications du fichier de tests `test_quest_source_boundaries.py`, mais **pas les modifications isolées du moteur** `app/quest_source_index.py`, ni celles de `app/startup_cache_domain_worker.py`. Ajout exclusivement de ces **deux chemins** au déclencheur du workflow Windows ciblé existant, sans nouvelle CI et sans diminution des critères. Test de contrat dans `test_startup_warmup_subprocess_flags.py` vérifiant tous les chemins de cache concernés. Cohérence avec `AGENTS.md`, `PHASE_CERTIFICATION.md`, `DEVELOPMENT_GUARDRAILS.md` : Draft + ciblé, aucun basculement FULL, refus de confondre PASS ciblé et CERTIFIED. Verdict règles : **REVIEW OK** sur ce déclencheur (risque résiduel : coût du Windows ciblé si l'un des moteurs change ; comportement voulu).

## Détection des tests mis de côté dans les patches

Sans modifier le verdict de certification ni autoriser de nouveau skip, l'audit commit-par-commit signale désormais les **ajouts de décorateurs `unittest.skip{If,Unless}` / `pytest.mark.skip{,if}` / `xfail`** et les appels `pytest.skip`, `pytest.xfail`, `self.skipTest` dans `TEST_SKIP` avec position fichier/ligne. Le niveau commit remonte `ADDED_TEST_SKIP_REVIEW`. Les marqueurs sont des **indices de revue**, car un skip peut avoir une raison légitime : pas de suppression automatique, pas de rejet arbitraire et aucun `NOT_RUN` converti en `PASS`. Tests paramétrés des signatures et test `review()` inclus.

## Success : index compact corrompu et comptages trompeurs

Le worker Succès ne considère plus comme READY un fichier `*.idx.json` présent mais malformé : il vérifie le `schema_version` exact, les comptes entiers (pas booléens ni chaînes), `0 < retained_count <= achievement_count`, la taille et les types de `retained_ids` ainsi que la présence et la cardinalité de `offsets`. Toute incohérence impose **une reconstruction du cache canonique**, puis une seconde vérification avec erreur explicite si la réparation échoue, au lieu d'un échec persistant sans tentative de réparation. Les fichiers de données et la validation native ne sont pas modifiés ; test de contrat multicas ajouté au worker de démarrage.

## Bug racine corrigé : constructeur Succès réutilisant un sidecar invalide

Le contrôle du worker Succès pouvait détecter un index `*.idx.json` invalide, mais `memory_bound_achievement_provider._build_compact_cache` revenait prématurément si l'en-tête JSONL était intact et `achievement_count` positif, **sans reconstruire le sidecar**. Ajout d'un paramètre compatible `force_rebuild=False` au constructeur canonique ; le worker ne le passe à `True` **que** lorsque la métadonnée du cache est encore valide mais que le sidecar a échoué à la validation. Construction, verrou inter-processus, écriture atomique et formats existants sont conservés. Test d'intégration ciblé pour montrer qu'un appel normal réutilise le cache et que la réparation forcée franchit vraiment la garde de réutilisation. Aucune validation Windows/FULL anticipée.

## Sidecar Succès : correspondance offsets ↔ octets JSONL

Au-delà des compteurs, le worker valide maintenant tous les IDs retenus uniques et présents dans `offsets`, les spans au format canonique **[début, longueur]**, et `0 <= début < début + longueur <= taille du JSONL`. Les types booléens, longueurs nulles, offsets hors fichier et références à un autre ID imposent reconstruction. Le contrôle est borné au sidecar sans charger les fiches JSONL dans la RAM de l'App. Tests des cas positifs, corruptions, doublons et fichier JSONL disparu ajoutés ; preuves exact HEAD à vérifier.

## Lot ciblé — intégrité des enregistrements Succès et repli applicatif (31/10/2026)

Le précédent contrôle des offsets retenus garantissait uniquement des bornes et des IDs présents dans le sidecar. Le fichier JSONL pouvait contenir une autre fiche à l'offset exact, tout en ayant des longueurs cohérentes. Le **worker jetable** ouvre maintenant le JSONL en binaire et vérifie chaque ligne retenue à la position déclarée (fin de ligne, type `achievement`, ID entier strict et égal à la clé de l'index). Les corruptions, objets JSON non dictionnaires et décalages sont refusés avant l'annonce de disponibilité ; la voie `force_rebuild` existante reste propriétaire de la reconstruction atomique sous verrou.

Côté Atlas, `MemoryBoundAchievementProvider._compact_value_by_id` refuse une ligne de type ou d'identifiant incorrect au lieu de rendre la mauvaise fiche ; `_load()` retombe sur l'extraction déjà existante si l'index du catalogue compact échoue après validation de l'en-tête. Aucun cache utilisateur persistant n'est modifié par ce lot.

Tests ciblés étendus avec lignes JSONL réelles, offsets intervertis, IDs booléens, lignes de type inattendu et repli de lecture ; le workflow Windows Guides/Succès existant exécute désormais explicitement les tests de ces lecteurs lors d'un changement des modules ou des tests. Aucun workflow parallèle, budget abaissé ni résultat `FULL PASS` présumé. **Validation à réaliser sur le SHA exact publié ; aucune mesure de gain de performance ou RAM déclarée.**

## Guide : réutilisation des caches JSONL incomplets interdite (31/10/2026)

`ensure_guide_compact_cache` comptait auparavant les lignes contenant littéralement `"kind":"guide"` après la seule validation du header : un JSONL tronqué, avec doublons ou sans index de relation pouvait être annoncé disponible et même rendre un catalogue Guide partiel. Le chemin existant exige maintenant les deux cardinalités `guide_count` / `entity_index_count` et vérifie les IDs uniques, les types de lignes et les références index→Guide avant de réutiliser le cache. Sinon, il conserve **la reconstruction existante**, sans nouveau générateur ni suppression de données utilisateur. Les anciens headers incomplets ne sont pas acceptés comme preuve.

Régression `test_guide_cold_relation_lookup.py` : plusieurs corruptions valides et invalides, dupliqués, manque d'index et cas de cache intact sans reconstruction. Cette validation prépare la réduction des faux retours « prêt » ; **aucun gain de latence/RAM n'est encore démontré** et aucune FULL n'est déclenchée manuellement.

## Guide : cohérence des contrats de relations à l'index (31/10/2026)

Les références `entity_index.entity_keys` sont maintenant contrôlées dans le worker jetable et dans le chemin `ensure_guide_compact_cache` (paire `[type, id]`, nom non vide, ID entier positif et non booléen). Les lignes `meta` tardives/dupliquées et les types inconnus sont rejetés par la recherche rapide de relations au lieu de requalifier arbitrairement un cache incomplet en index valide. Tests ciblés ajoutés : ID booléen, relation incomplète, en-tête forgé en fin de fichier et reconstruction du cache. Un cache non vérifié reste éligible au **fallback canonique**, jamais à un succès silencieux.

Cette modification est limitée aux caches jetables : progression, sources Ganymède, formats de routes et UI restent inchangés. La preuve Windows exacte, la mémoire, la vraie interface et l'EXE restent des validations distinctes non présumées.

## Unification des points d'entrée de validation Guide (31/10/2026)

La commande existante `--ensure-compact-cache` acceptait encore un JSONL incomplet en ne comptant que les sous-chaînes `"kind":"guide"`, contrairement au chemin `ensure_guide_compact_cache` corrigé. Elle réutilise maintenant **ce contrôle existant** avant de préparer les cartes manuelles ; si aucun guide validé n'est disponible, elle remonte une erreur claire plutôt que de déclarer un faux cache prêt. Régression par mocks du point d'entrée : résultat positif et échec avec absence de lancement du préchargement manuel. Un sous-processus de reconstruction supplémentaire n'apparaît que lors de la réparation d'un cache déjà invalide, pas en fonctionnement normal.

Aucune suppression, aucune migration de données ni changement d'identité de progression. Tests Windows et performances exact-SHA encore à vérifier.

## Compatibilité EXE figé de la commande Guide (31/10/2026)

La mutualisation de `--ensure-compact-cache` conserve expressément le cas `sys.frozen` : lorsque le validateur ne peut pas réutiliser le cache, il reconstruit en processus courant par `_build_compact_guide_cache` puis revérifie avant de déclarer READY. Il n'essaie pas d'exécuter `python -m` depuis un EXE figé. Régression dédiée : chemin gelé, reconstruction unique et seconde vérification. La vraie recette de l'EXE Windows reste `NOT_RUN` tant que le paquet exact-SHA n'est pas testé.

## Lookup à froid Quêtes → Guides : répétition d'index bornée (31/10/2026)

`MemoryBoundGuideProvider.guide_ids_for_quest_fast` relisait et décodait l'ensemble du JSONL à chaque appel, y compris plusieurs fois pour le même ID lors des parcours de Quêtes. Le résultat n'est maintenant conservé que pour **64 requêtes récentes par instance**, sous contrôle inchangé de la signature de source et d'une empreinte `path + taille + mtime_ns` du fichier compact ; une reconstruction concurrente détectée après le scan empêche la mise en cache. `reload` / `release_catalogue` libèrent immédiatement les entrées. Aucun index complet résident, nouvelle dépendance, cache persistant ni mutation de progression.

Tests ciblés : seconde recherche identique ne reparcourt pas le JSONL (seule la lecture du header reste), maximum 64 relations, changement d'index suivi d'invalidation et même réponse métier. Ce test établit une **réduction d'opérations de décodage sur réutilisation** dans la fixture ; il ne mesure ni un gain de temps Windows ni une baisse de RAM globale. Les plafonds Home <100 Mio / pic <=250 Mio restent inchangés.

## Index compact des objets Guide : intégrité des IDs (31/10/2026)

`dofus_item_provider._read_guide_items_index` renvoyait une correspondance incomplète en **ignorant silencieusement** les clés invalides et lignes non dictionnaires. Il refuse désormais le cache entièrement vide, une entrée mal formée, un identifiant `id` booléen/non entier, non canonique ou différent de la clé JSON. Les données de source restent inchangées et **la reconstruction existante** est automatiquement utilisée quand ce cache jetable est invalide. Tests positifs et négatifs ajoutés à `test_compact_guide_item_effects.py`, inclus dans le Windows ciblé Guide lors de tout changement de moteur ou test concerné.

Cet effort évite de présenter des objets manquants comme une génération de cache correcte ; il ne prétend pas corriger le contenu Dofus absent à la source ni prouver un gain RAM/latence. La validation exact-SHA et la recette EXE restent distinctes.

## Compatibilité exacte des identifiants d'objets du cache (31/10/2026)

La correction précédente des index objets ne doit pas inventer une restriction métier `id > 0` absente du writer original. Le validateur accepte désormais tout identifiant entier **canonique** effectivement émis par `str(item.id)`, y compris `0` et les entiers signés, tout en refusant les alias `"042"`, les clés malformées, les booléens et les divergences clé/valeur. Test de compatibilité ajouté sans toucher aux données ni au format du cache.

## Navigation Guide : repli source après disparition du cache compact (31/10/2026)

`get_guides_for_entity` pouvait lever une exception si l'index JSONL disparaissait entre la vérification de l'en-tête et son ouverture, ou si son contenu devenait illisible. Le bloc de lecture est désormais protégé contre les erreurs I/O et de décodage prévues ; les anomalies sont journalisées et le fournisseur réutilise le **chemin de secours existant** fondé sur les détails Guide, sans mémoriser un résultat partiel. Le cache mémoire reste borné à 64 relations. Régression dédiée et couverture du workflow Windows Guides/Succès existant.

Aucune source métier, progression ou règle de certification modifiée ; preuve Windows et benchmarks restant à vérifier au SHA exact.

## Réduction de l'allocation transitoire : publication de l'index objets Guide (31/10/2026)

`_build_guide_items_index` ne construit plus une chaîne JSON entière via `json.dumps` avant l'écriture : `json.dump` sérialise directement le `payload` existant dans le fichier temporaire, avec le même encodage, séparateurs, schéma, signature et publication atomique. Le `finally` nettoie ce temporaire unique après succès ou erreur `write/replace`, en préservant la génération précédente. Test d'échec d'écriture, de partage Windows simulé et succès ; pas de perte de données métier.

Ce changement **supprime une copie transitoire évitable du JSON en mémoire**, mais le gain RSS/temps exact n'est pas encore mesuré ; les seuils Home/peak et la nécessité du benchmark Windows comparé restent identiques.

## Intégrité du cache de noms Succès : refus des doublons et IDs malformés (31/10/2026)

`achievement_name_index` n'ignore plus silencieusement une fiche Succès dont l'ID est manquant, non entier (y compris booléen) ou déjà présent, ni une ligne `achievement` sans dictionnaire. Il rejette le cache incomplet avec `{}`. Le writer canonique `write_achievement_name_index`, protégé par son verrou et son remplacement atomique, **refuse de publier un index vide** et conserve le dernier fichier valide si la lecture de la source a échoué. Tests ciblés des lignes valides, doublons, anomalies et de la publication conservatrice ; branchement sur le workflow Windows Guide/Succès existant.

Les sources métier et caches utilisateurs ne sont pas modifiés ; aucun gain RAM/perf ni certificat de distribution Windows revendiqué.

## Cohérence des compteurs Succès lors du warmup et réemploi (31/10/2026)

`startup_cache_domain_worker._success_domain` exige maintenant `achievement_name_count == achievement_count` après construction ; le manifeste `startup_cache_warmup._domain_payload_complete` rejette aussi un index partiel **même si ses compteurs sont strictement positifs**, ainsi qu'un `retained_count` supérieur au total. Cette règle s'applique au résultat de nouveau worker **et** aux domaines réutilisés depuis le disque. Test du cas 1411 noms pour 1412 Succès, sans modifier les valeurs Dofus ni la politique de certification.

Aucun gain de RAM présumé. Le HEAD exact doit passer ses contrôles ciblés avant tout autre verdict.

## Warm start Succès : éviter les écritures disque inutiles (31/10/2026)

Sous le **verrou interprocessus existant**, `write_achievement_name_index` compare le cache de noms courant au résultat canonicalisé déjà calculé et retourne directement si contenu identique : aucune nouvelle écriture temporaire, `replace`, retry Win32 ni invalidation d'horodatage sur les démarrages sans changement. Cache manquant, corrompu ou différent : la publication atomique originale reste strictement préservée. Test vérifiant qu'un cache valide bloque une tentative artificielle de `replace` et conserve son mtime. Le bénéfice est une suppression d'I/O redondante sur la voie chaude, **sans chiffre de gain Windows/RSS prétendu**.

## Cache Quêtes → Guides : invalidation après remplacement atomique horodaté (31/10/2026)

L'empreinte d'invalidation du cache LRU de 64 relations ne repose plus seulement sur `path/size/mtime_ns` : elle prend aussi `ctime_ns` et `st_ino`. Une autre instance peut remplacer un fichier par un contenu de **même taille et de même mtime** sans que l'ancien résultat de relation ne soit valable. Le contrôle avant/à la fin du scan utilise la même empreinte. Test avec remplacement atomique et horodatage restauré ; aucun changement de format disque ni ajout d'index résiduel.

## Requêtes Guide par entité : index incomplet non mémorisé (31/10/2026)

Le chemin `MemoryBoundGuideProvider.get_guides_for_entity` ne vérifiait ni la cardinalité finale des `entity_index`, ni l'unicité des IDs Guide, et pouvait publier un faux résultat négatif après une troncature JSONL pourtant parsable. La lecture limitée aux lignes d'index contrôlées exige désormais `entity_index_count` du header, des IDs présents et uniques et des couples `entity_keys` valides avant de mémoriser les relations. Sinon le **fallback source existant** est utilisé. Test : en-tête annonçant 2 index mais un seul présent (fallback) puis index complet (lookup direct).

Cette validation reste localisée à la navigation par entité, sans double cache, source métier modifiée ou preuve RAM/Windows inventée.

## Contrat Guide compact schéma 2 : en-tête signé obligatoire pour les relations à froid

La recherche `guide_ids_for_quest_fast` accepte désormais seulement les caches possédant **les deux compteurs entiers canoniques** `guide_count` et `entity_index_count`, déjà exigés par le worker et le chemin `ensure_guide_compact_cache`. Un ancien en-tête sans cardinalité ne peut plus rendre `()` et masquer une relation avec une quête absente d'un cache tronqué. Il renvoie `None` pour déclencher le fallback canonique. Test ciblé pour absence de chacun des deux compteurs ; aucune migration des données utilisateur, aucun changement de format du writer.

## Runtime Windows figé : priorité au cache Guide réellement préchargé (31/10/2026)

Correction du chemin `MemoryBoundGuideProvider._load()` : l'ancien test `sys.frozen` imposait systématiquement `_load_in_process()` **avant** de consulter le JSONL compact, même si le préchargement avait produit des résumés valides. Les installations Windows packagées perdaient donc le bénéfice mémoire de ce cache et relisaient les gros JSON sources dans le processus UI. Pour les sources canoniques, la lecture compacte validée est maintenant utilisée **également en EXE figé**. Si cache absent ou corrompu : repli `_load_in_process` préexistant, sans tentative d'exécuter `python -m` depuis l'EXE. Les sources personnalisées restent en mode in-process. Tests ciblés des trois branches (cache valide, absent, corrompu) avec `sys.frozen` simulé.

Le chemin compact élimine le chargement lourd **dans ce scénario**, mais le gain RSS/latence réel et le fonctionnement d'un EXE packagé restent à mesurer sur Windows exact-SHA. Aucun contrat de données ou progression modifié.

## Runtime Windows figé : même optimisation sur Succès (31/10/2026)

`MemoryBoundAchievementProvider._load()` contournait lui aussi le cache compact dès que `sys.frozen` était vrai : le runtime Windows lisait alors les sources complètes dans la mémoire UI malgré un cache de catalogue valide. La lecture compacte devient prioritaire pour les sources canoniques, y compris dans un EXE. Si elle échoue ou que le cache n'existe pas, le chemin in-process d'origine reste le repli sans lancer de subprocess Python depuis l'EXE. Les sources personnalisées conservent leur comportement. Deux tests de la priorité cache et du repli, ajoutés à la campagne Windows ciblée existante.

Les contrats de progression et de détails riches ne sont pas modifiés. Les gains RAM/latence et la recette EXE exigent toujours une mesure Windows sur le SHA exact.

## Cache global warmup : génération disque reconnue au-delà du mtime (31/10/2026)

Le manifeste de `startup_cache_warmup` comparait uniquement `st_size` et `st_mtime_ns` des artefacts Guide/Succès. Deux fichiers différents avec même taille et horodatage restauré pouvaient alors être réutilisés à tort après un remplacement atomique. L'empreinte compare maintenant aussi `st_ctime_ns` et `st_ino`; le schéma interne du **manifeste jetable** passe de 2 à 3 pour forcer une reconstruction contrôlée une seule fois des manifestes anciens. Le traitement spécial des SQLite Quêtes, avec vérification de leur propre structure, reste inchangé. Régression sur vrai `Path.replace()`, même taille et même `mtime_ns`.

Ce n'est ni un hash complet des gros fichiers ni une garantie cryptographique : Doctor garde la responsabilité de la validation approfondie. L'utilisateur ne perd aucune progression et le cache métier ne change pas de format.

## Brouillons Guide : ne jamais les masquer par le cache compact publié (31/10/2026)

Le cache Guide normal représente le catalogue publié et ne couvre pas `include_drafts=True`. Le nouveau chemin préférentiel de l'EXE ne doit donc **pas** être appliqué aux requêtes incluant explicitement des brouillons ; la même vérification supprime un ancien écart de ce type en développement. `MemoryBoundGuideProvider._load()` garde `_load_in_process` pour ces requêtes, quel que soit `sys.frozen`. Test de non-contournement du chemin source dans les deux contextes, sans modifier les données ni le schéma JSONL.

## Effets Dofus/Objets Guide : pic transitoire borné dans le worker (31/10/2026)

`DofusItemProvider._load_in_process` retenait un `bytearray` de **toutes** les lignes `effectId` de `items.json` jusqu'à la fin de la découverte des `possibleEffects`. L'extraction continue d'effectuer **un seul parcours des sources** (les RID utiles peuvent être connus après leur définition), mais conserve maintenant les tuples binaires dans un `SpooledTemporaryFile` : maximum **1 Mio en mémoire pour ce tampon**, puis débordement vers un fichier temporaire clos automatiquement. `_selected_effect_instances` accepte ce flux et le lit par lots fixes de 4096 lignes (40 octets par ligne), en maintenant `dernier RID gagnant` et les nombres signés. Les appels existants avec `bytes`/`bytearray` restent supportés.

Régression : 4097 entrées, RID dupliqué à travers la frontière des lots, requête absente et débordement disque forcé. Ce changement borne **ce tampon**, pas la totalité du process-tree ; l'impact sur le pic RSS, le temps et les I/O Windows doit être établi par le benchmark exact-SHA. Aucun format métier, données, seuil ou workflow additionnel.

## Guides brouillons : parité des relations Quêtes → Guides (31/10/2026)

Le repli correct `_load_in_process` pour `include_drafts=True` ne suffisait pas : `MemoryBoundGuideProvider.get_guides_for_entity` redemandait ensuite l'index compact **du catalogue publié**, ce qui pouvait cacher silencieusement des relations de guides brouillons, puis mémoriser un faux résultat. La recherche par entité ignore désormais cet index dans ce mode et utilise les détails canoniques déjà existants. Test avec accès interdit à l'index compact, résultat positif issu du brouillon et second accès via cache de résultat borné. Sources de progression et statut des guides inchangés.

## Écriture noms Succès : sérialisation directe et rollback sur disque plein (31/10/2026)

`write_achievement_name_index` encode désormais directement le dictionnaire de noms avec `json.dump` dans le temporaire atomique, sans garder sa représentation complète `json.dumps` en mémoire. Le nettoyage du temporaire englobe **aussi les erreurs d'écriture/sérialisation**, qui auparavant précédaient le `try/finally` et laissaient un `.tmp` inachevé. Le verrou interprocessus, la détection de contenu inchangé et le remplacement Win32 inchangés. Régression vérifiant un disque plein simulé : génération précédente intacte et zéro temporaire résiduel.

L'amélioration concerne la copie transitoire et la fiabilité, sans démonstration d'un gain RSS sur une installation réelle.

## Preuve d'intégration du tampon d'effets dans le vrai constructeur Objets (31/10/2026)

En plus du test autonome des 4097 lignes, la régression `CompactGuideItemEffectTests.test_real_item_worker_uses_spool_and_retains_late_effect_override` traverse `DofusItemProvider._load_in_process` avec les références source synthétiques : ligne d'effet RID 77 avant et après l'objet Dofus, valeur finale 9, une seule ouverture de `SpooledTemporaryFile(max_size=1048576)`. Elle couvre le branchement effectif du nouveau tampon dans le worker, sans lire ni modifier les données réelles. Le budget RSS Windows n'est pas encore attesté.

## Empreinte des sources du preload : remplacement atomique détecté (31/10/2026)

`startup_cache_warmup._source_stamp` comparait encore uniquement taille et `mtime_ns` des JSON **source**, laissant une différence avec la protection déjà ajoutée aux artefacts jetables. La signature des sources inclut maintenant `ctime_ns` et `st_ino`, et `_DOMAIN_STAMP_VERSION` passe de 1 à 2 : anciens manifestes automatiquement invalidés une fois, sans migration utilisateur. Une installation/synchronisation qui remplace un JSON par un autre de même taille et `mtime_ns` ne peut plus réutiliser son ancien manifeste sur cette seule empreinte. Test avec réel `Path.replace()` et date restaurée, sur la voie canonicalisée `_source_stamp`.

Pas de lecture complète ou hash des contenus à chaque démarrage : il s'agit d'une empreinte système rapide, avec les mêmes limites de sécurité qu'un stat, pas d'une certification cryptographique.

## Navigation par entité : relecture de génération avant mise en cache (31/10/2026)

`get_guides_for_entity` ne validait pas une seconde fois l'empreinte du JSONL après le parcours des `entity_index`. Un autre processus pouvait publier un nouveau cache entre contrôle de signature et calcul de la relation, laissant une réponse potentiellement périmée dans la LRU de navigation. Le lecteur contrôle désormais `size/mtime_ns/ctime_ns/inode` avant et après lecture, et conserve le fallback sur les fiches sources si ces valeurs changent. Test injectant un changement de génération après lecture d'un cache valide et vérifiant la relation positive en secours. Pas de fichier supplémentaire, pas de changement des données ni de travail de parsing sur les chemins de cache-hit déjà mémorisés.

## Guide objets : sources manquantes hors dépôt gérées sans exception (31/10/2026)

Une signature de sources sur un `data_dir` personnalisé extérieur au dépôt échouait en `ValueError` dans le chemin `except OSError` lorsqu'un fichier était encore absent, avant de pouvoir servir de signal de cache périmé. Le chemin manquant est maintenant normalisé comme les chemins existants, avec repli sur le chemin absolu et séparateurs canoniques. Test dossier temporaire externe, fichiers manquants puis apparition de `items.json`. Aucune modification des données utilisateur ni du format des signatures des sources canoniques.

## Cache objets Guide : reprise après preload tardif et remplacement atomique (31/10/2026)

`DofusItemProvider._guide_index_row` mémorisait `{}` à la première consultation d'un index absent/invalide et ne retentait ensuite **jamais** le chemin compact, même lorsque le worker avait terminé le preload. Le fournisseur garde maintenant l'empreinte légère `size/mtime_ns/ctime_ns/inode` de l'index jetable et ne recharge son dictionnaire qu'après une véritable nouvelle génération. Une publication concurrente pendant la lecture provoque un repli prudent et une nouvelle tentative au prochain lookup. Tests : absence initiale, apparition de l'index, remplacement atomique avec taille/mtime identiques, puis résolution d'une nouvelle ID. Cache d'objets récents déjà borné à 32 inchangé, aucune allocation de catalogue supplémentaire au repos.

## Catalogue Dofus : libération des lignes brutes Guide après chargement total (31/10/2026)

Lorsque `DofusItemProvider.get_by_id` était sollicité avant `load_all()`, le provider conservait `_guide_index_rows` (dictionnaire complet d'objets Guide) **même après** avoir créé les objets `DofusItem` du catalogue complet et leur index `_by_id`. Le cache brut n'est plus consulté lorsque `_loaded=True` ; `_ensure_loaded` le libère désormais après `_load` réussi, ainsi que son empreinte. Tests réels sur un index synthétique : consultation item à froid, chargement complet Dofus, libération du graphe brut et restitution d'un objet Dofus identique.

Gain : suppression d'une rétention doublonnée dans ce scénario. La baisse effective du RSS et le coût du catalogue complet restent à mesurer sous Windows.

## Guide compact : signature de source cohérente avec le warmup (31/10/2026)

`_guide_compact_source_signature` ne distinguait pas deux fichiers Guide différents ayant la même taille et le même `mtime_ns`, même si le manifeste de preload était désormais invalidé. Les lignes de signature embarquées dans les caches compacts enregistrent maintenant aussi `ctime_ns` et `inode` (et des sentinelles pour les fichiers inaccessibles). Le cache ancien est **reconstructible** et sera invalidé/reconstruit une fois pendant le preload contrôlé ; en EXE figé sans preload, le fallback canonique reste disponible. Régression sur remplacement atomique source de même taille/date ; aucune donnée utilisateur migrée. L'impact du premier démarrage après cette invalidation sera à mesurer séparément.

## Succès compact : signature des sources renforcée contre les remplacements (31/10/2026)

`_achievement_compact_source_signature` inclut maintenant taille, `mtime_ns`, `ctime_ns` et inode, alignée sur les garde-fous du preload et du catalogue Guide. Une installation qui remplace un `achievements.json` par un fichier de même longueur et de même date de modification ne peut plus reprendre un index Success vieux mais toujours signé par l'ancien couple taille/mtime. Régression sur une vraie opération `Path.replace` avec sidecar et en-tête factices. Les caches antérieurs seront reconstruits au prochain warmup contrôlé ; aucune écriture utilisateur ni migration des profils.

## Objets Guide : cache invalidé après remplacement source à mtime constant (31/10/2026)

`_guide_item_source_signature` utilise désormais la même empreinte `size/mtime_ns/ctime_ns/inode` pour `items.json`, `item_types.json`, `effects.json`, traductions et fichiers Guide ; les sources manquantes utilisent quatre sentinelles homogènes. Le writer et le reader partagent déjà cette fonction : un ancien index v1 reconstruit automatiquement au preload ne peut plus survivre à une mise à jour remplaçant le JSON source à taille/mtime identiques. Test de la signature avec dossier externe, index réel synthétique et remplacement atomique du fichier source. Le changement ne modifie pas la structure des items, uniquement la signature reconstructible ; premier démarrage post-migration à mesurer.

## Index Guide : invalidation des réponses de navigation déjà mémorisées (31/10/2026)

Le contrôle de génération avant/après le scan de `get_guides_for_entity` ne protégeait pas un résultat **déjà présent** dans `_by_entity` : le retour anticipé court-circuitait la vérification après publication d'un nouveau JSONL par une autre instance. Le cache borné de relations est maintenant invalidé par `stat(size/mtime_ns/ctime_ns/inode)` **avant chaque lookup en mode publié** ; le chemin brouillons et la construction canonique gardent leur comportement. Aucun décodage JSON sur cache-hit. Test de remplacement atomique avec même taille et mtime, vérifiant la disparition d'une ancienne relation positive et l'apparition de la nouvelle. Reset explicite du stamp à la libération/recharge. Aucun gain RAM déclaré sans benchmark.

## Objets Guide : invalidation des éléments récents après remplacement atomique (31/10/2026)

Le dictionnaire de 32 `DofusItem` récemment décodés retournait un résultat avant de contrôler la génération de `GUIDE_ITEMS_INDEX`. `_guide_index_row` savait déjà se recharger, mais le cache des objets **l'en empêchait sur les hits**. La vérification légère `size/mtime_ns/ctime_ns/inode` a été mutualisée avec le lecteur compact et invalide seulement les objets récents lorsque la génération change. Le catalogue Dofus `_loaded=True` conserve ses objets et évite cette vérification, et le cleanup de chargement complet libère l'empreinte. Test : même ID, nom « Old »→« New », remplacement atomique à taille et mtime identiques sans fallback source. Aucune mesure de gain de RAM annoncée.

## Préparation Guide : garder réellement les 32 objets les plus récemment utilisés (31/10/2026)

Le cache `DofusItemProvider._by_id` plafonné à 32 objets fonctionnait en FIFO : les consultations d'un objet déjà chargé n'actualisaient pas sa position et un prérequis populaire pouvait être expulsé au prochain ajout. La récupération en mode **catalogue froid** déplace maintenant un hit en fin du dictionnaire, ce qui réalise une politique LRU réelle sans augmenter la capacité ni modifier la voie `_loaded=True` du catalogue complet. Test de 33 objets, hit sur le premier avant insertion du 33e : le premier reste, le deuxième est expulsé. Aucun gain temporel prétendu avant mesure.

## Navigation Guide : LRU de 64 relations réellement basée sur l'usage (31/10/2026)

`_by_entity` limitait déjà la taille à 64 entrées, mais la restitution des requêtes existantes ne rafraîchissait jamais leur position ; les relations souvent consultées étaient expulsées comme en FIFO. Les hits de navigation (positifs ou négatifs) déplacent désormais l'entrée en fin de dictionnaire avant le retour d'une copie, sans changer le contrat de `_building_compact_cache` ni la limite. Test 64 entrées, réutilisation d'une relation négative, 65e insertion : conservation de l'entrée chaude et éviction de la plus ancienne non réutilisée. Aucun gain de temps prétendu sans bench.

## Lecture du catalogue Guide : intégrité de génération pendant chargement (31/10/2026)

Le lecteur `_load_from_compact_cache` vérifie désormais l'empreinte `size/mtime_ns/ctime_ns/inode` avant et après la lecture des résumés. Un autre worker publiant une nouvelle génération pendant le décodage ne peut plus faire installer des fiches partiellement périmées : `RuntimeError` conserve le repli existant. Régression avec remplacement concurrent simulé et absence d'appel à `_install_summaries`. Deux `stat` supplémentaires par lecture froide, aucun second scan JSONL ; impacts RSS et latence Windows non mesurés.

## Succès : cohérence de la cache des relations de quêtes (31/10/2026)

Le lecteur des relations retenues mémorisait à tort une liste vide en cas de JSONL incomplet ou illisible. Le chemin compact vérifie désormais l'en-tête, les IDs retenus (unicité et cardinalité), la frontière external_start et la stabilité size/mtime_ns/ctime_ns/inode du fichier. Il s'arrête à cette frontière pour ne pas lire les succès externes. Une corruption retourne temporairement une liste vide sans mémoriser le faux négatif ; les appels suivants retentent. Toute nouvelle génération invalide les entrées déjà mémorisées dans la LRU de 24. Tests : troncature puis correction et remplacement atomique taille/date identiques. Aucun gain RAM/temps global n'est déclaré sans mesure Windows.
