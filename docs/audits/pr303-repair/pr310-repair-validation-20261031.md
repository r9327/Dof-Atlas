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
