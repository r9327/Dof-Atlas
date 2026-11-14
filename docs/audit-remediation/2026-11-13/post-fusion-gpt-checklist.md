# DOFUS ATLAS — reprise après fusions (lot GPT du 13/11/2026)

**Source et périmètre** : [contrat #430](https://github.com/r9327/Dof-Atlas/issues/430) ; `main@76c0008bdfcbb8dca3315121496e5e52388e0b9f` au cadrage ; uniquement les 19 PR fusionnées/fermées du 6 au 13 novembre 2026.

**PR concernées** : #285, #292, #293, #325, #358, #371, #392, #394, #397, #398, #406, #407, #413, #415, #416, #420, #425, #426, #429. Aucune PR encore ouverte n'est auditéе ni terminée dans ce lot. Aucun travail sur l'UI globale/Guides/Opti V3 en cours ne doit être dupliqué.

## Règles de travail

- **DRAFT tant que le lot est en développement** ; CI ciblées locales/Doctor à chaque correction, *une* Phase Certification finale au SHA stabilisé et après revue des commits. Pas de fusion automatique.
- Première étape : vérifier l'état *actuel* sur main, les consommateurs et tests des éléments en cause, les statuts des exigences, puis l'impact des fusions ultérieures. Les cases DONE dans une PR sont des déclarations d'inventaire, pas une recette native.
- **Ne jamais corriger un écart supposé** : repro documentée, cause identifiée, test qui échoue avant et passe après, modification minimale. Préserver les services canoniques (hooks, Sender, MacroLock, Atlas Doctor, stockage) et les données utilisateur.
- Toute modification structurelle exige les vérifications et Graphify exact-SHA prévues par AGENTS.md ; toute modification non triviale suit le parcours Doctor `plan → check → validate`.
- Les tests Windows Qt synthétiques ne prouvent pas la réception des entrées dans le jeu DOFUS Unity.
- Les fichiers et états produits par l'application et les captures/logs sensibles ne sont pas commités ; uniquement des preuves expurgées et autorisées.

## Travail GPT — checklist de lots

### GQA-001 — Réconcilier les fusions [docs]
- [ ] Reconstruire un tableau pour chaque PR : contrat, statut historique, code actuel sur main, correctif postérieur éventuel, tests au SHA concerné.
- [ ] Requalifier individuellement les **29 PENDING + 2 DEFERRED historiques de #325** après les fusions #398, #406, #416, #425 et #429. Ne pas transformer PENDING en bug certain.
- [ ] Distinguer `CONFIRMÉ / PARTIEL / NON FAIT / NON VÉRIFIABLE` et `P0/P1/P2` avec preuve et lien.
- [ ] Retirer de la liste active ce que les PR fusionnées plus tard ont réellement corrigé.

### GQA-002 — Organizer, callbacks, sûreté [code et tests ciblés]
- [ ] Examiner `app/macros/mirror_input.py`, `app/macros/zaap.py`, `app/macros/auto_group.py`, `app/macros/input_tools.py`, `app/core/macro_lock.py`, `app/pages/organizer/organizer_ui.py`, ainsi que leurs consommateurs et tests actuels.
- [ ] Vérifier par instrumentation/test les conditions d'activation explicite du Miroir, Stop/Relancer, focus inconnu, DOWN/UP, absence de double émission, ordre du roster, identité du maître, persistance et prévention de doubles callbacks.
- [ ] Vérifier les signaux des boutons Macro/Miroir, Précédent/Suivant, raccourcis, Zaap, auto-groupe, vitesses et camembert ; **ne pas prétendre que le jeu a reçu un événement**.
- [ ] N'ajouter une correction et ses tests que pour une anomalie reproductible. Préserver l'interface approuvée de #429 et éviter toute nouvelle palette/thème local.

### GQA-003 — Craft et bundle [code et tests ciblés]
- [ ] Inspecter `app/pages/craft_page.py`, `app/craft_preload.py`, `local_dofus_data/` et tests existants.
- [ ] Confirmer le clic unique sur un métier, la priorité des vrais guides et le fallback honnête en leur absence ; vérifier le chemin `data/raw/json/gamosaurus/metiers_leveling.json` ignoré par Git.
- [ ] Contrôler les chemins et la présence des icônes en archive publiée (LFS), la recherche normalisée, l'ordre d'ajout, le scroll, Échap et la classification des armes.
- [ ] Corriger uniquement un bug vérifié ; n'inventer ni guides Gamosaurus ni quantité/XP ni source éditoriale. Les sources manquantes restent signalées explicitement.

### GQA-004 — Launcher V2 [code et tests ciblés]
- [ ] Revoir `app/distribution/install.py`, `launcher.py`, `health.py`, `archive_parts.py` et les contrats existants.
- [ ] Vérifier no-op (aucune installation sans changement), delta réseau, vérification SHA, rollback atomique, crash et mutex, progression et Home réellement interactive dans les limites des tests disponibles.
- [ ] Constater la limitation connue de `_copy_unchanged_verified` : sur volume sans clone CoW, le fichier inchangé est recopié dans le nouveau slot. Mesurer avant une proposition d'optimisation ; ne jamais substituer un hardlink mutable dangereux.
- [ ] N'altérer le moteur que si bug confirmé et test de régression disponible.

### GQA-005 — Doctor, CI, dépendances [code et tests ciblés]
- [ ] Vérifier l'intégration effective des correctifs #392, #394, #397, #413 et #426 sur le code actuel et les propriétaires de tests.
- [ ] Vérifier les pinning et exécutions des changements d'actions #292/#293/#371/#426, sans modifier ou relancer des workflows non concernés.
- [ ] Contrôler les décisions d'outillage #358 : sélection opt-in, absent=NOT_RUN, versions/provenance et exécution prouvée ; éviter les installations de 34 outils non nécessaires.
- [ ] Pour chaque CI revendiquée, vérifier le **SHA exact**, la conclusion, le workflow et la pertinence des tests ; aucune assimilation à un PASS DOFUS réel.

### GQA-006 — Preuves et retours [docs]
- [ ] Tenir une matrice `fonction → fichier → test → SHA → résultat → preuve → limites → propriétaire`.
- [ ] Consigner les retours de l'utilisateur : scénario, version, nombre de comptes, résultat OK/KO, symptômes, logs/screens expurgés.
- [ ] Rattacher chaque défaut confirmé à un correctif minimal et à un test ciblé ; si impossible de reproduire, marquer `NON VÉRIFIABLE`, jamais `FAIT`.

### GQA-007 — Sortie du lot [docs]
- [ ] Revue de chaque commit dans l'ordre et audit final du diff, des régressions, du respect du périmètre et du code actuel.
- [ ] Tests ciblés Doctor/Qt/CI pertinents, preuves du HEAD courant ; aucune preuve historique appliquée à un SHA différent.
- [ ] Phase Certification finale uniquement lorsque tout le code du lot est terminé, puis verdict `REVIEW OK / IMPROVEMENTS ADVISED / CHANGES REQUIRED`.

## Tests que l'utilisateur fera **plus tard** sur son PC (hors attestation automatique GPT)

La validation humaine est volontairement **NOT_RUN** tant que l'utilisateur n'a pas transmis un résultat. Ne pas refaire une liste de faux PASS et ne pas lui demander de tout tester d'un seul coup.

1. **DOFUS réel 2 puis 4/8 comptes** : activation Miroir uniquement sur commande, clic/double-clic/molette/clavier, perte de focus, Stop → Relancer, roue, Précédent/Suivant, maître après réorganisation et redémarrage.
2. **Zaap et Auto-groupe** : touche Espace ouvre le chat, texte envoyé et action reçue réellement.
3. **Trois vitesses** : comparer l'effet effectivement perçu, sans présumer Instantané imperceptible.
4. **Organizer visuel** : 8 slots, étoile décorative du premier, boutons/raccourcis/padding, ratio Personnages/Zaap, fond et débordements à taille normale. Comparaison de PNG exacts à viewport/DPI égal, cf. #424.
5. **Launcher installé** : zéro changement, mise à jour de quelques fichiers, interruption/rollback, Home réellement utilisable, cf. #287.
6. **Craft installé** : popup métier récolte/fabrication, images, armes, recherche, ajout/scroll/Échap, fallback sans guide éditorial, cf. #421.

**Format de retour suffisant** : `module | action | attendu | observé | nombre de comptes | Atlas SHA/version | capture/log si disponible`. GPT confirme la cause dans le code avant toute correction.

## État au premier commit

- Contrat et matrice de travail rédigés, **aucun correctif de code poussé**.
- **Aucun nouveau test exécuté**, aucune capture nouvellement générée, pas de certification Windows/Unity ou Phase revendiquée pour ce lot.
- Les rapports des PR fusionnées ne sont que des pistes initiales : la requalification de leur état sur main reste le prochain travail.

## Requalification post-fusion — état vérifié au 14/11/2026

> Lecture **source/statique**, à ne pas confondre avec une campagne native ni une certification. Les liens `#PR` ci-dessous désignent les contrats/rapports historiques ; leurs cases DONE sont des **déclarations à confronter au code actuel**. Dernier candidat examiné avant ce document : `b820eb59dc808b9dc48ec7a402ad021d604b2e0f`. Les tests de la PR #431 **n'ont pas été relancés** dans cette session.

### Inventaire exhaustif des 19 PR de l'issue #430

| PR fusionnée | Contrat/rapport historique | Reprise / propriétaire technique actuel | Conclusion au stade de lecture |
| --- | --- | --- | --- |
| #285 | LV2 : 9 DONE, 5 DEFERRED | `app/distribution/{launcher,install,health,archive_parts}.py` ; `tests/test_distribution_*.py` | PARTIEL : recette installée et performance NTFS non démontrées |
| #292 | 1 DONE | GitHub Actions checkout | PARTIEL : pinning à relire au SHA de livraison |
| #293 | 1 DONE | GitHub Actions setup-python | PARTIEL : pinning à relire au SHA de livraison |
| #325 | 12 DONE, **29 PENDING, 2 DEFERRED** | `app/{core,macros,input}/` ; #398, #406, #416, #425, #429 | PARTIEL / NON VÉRIFIABLE : voir 31 lignes ci-dessous |
| #358 | 6 DONE, 4 DEFERRED | `tools/atlas_doctor_lib/oss_router.py`, `tests/test_doctor_oss_*.py` | PARTIEL : outillage opt-in, absence d'outil != PASS |
| #371 | 1 DONE | GitHub Actions upload-artifact | PARTIEL : pinning et run effectif à qualifier |
| #392 | 2 DONE, 1 DEFERRED | Qt Linux / Doctor | PARTIEL : requalification des suites Qt requise |
| #394 | 2 DONE | Tests hooks Miroir/Qt | PARTIEL : propriétaires de tests à confirmer |
| #397 | 5 DONE | Analyseur Miroir ciblé | PARTIEL : exécution exact-SHA à vérifier |
| #398 | 3 DONE, 1 DEFERRED | `app/macros/{mirror_input,zaap}.py` | PARTIEL : correction focus déclarée, DOFUS non reçu |
| #406 | 23 DONE, 2 DEFERRED | `app/core/runtime_state.py`, Miroir/Stop, roue/slots | PARTIEL : vraies entrées et mesures non certifiées |
| #407 | 7 DONE, 2 DEFERRED | `app/pages/craft_page.py`, catégorisation/images | PARTIEL : distribution de données/images non attestée |
| #413 | 4 DONE | Suites FULL Windows | PARTIEL : pas de preuve FULL au nouveau SHA |
| #415 | Synchronisation de branche, pas de rapport d'exigences | Code partagé/Guide | NON VÉRIFIABLE isolément : pas de feature distincte revendiquée |
| #416 | 9 DONE, 1 DEFERRED | Slots, favori, chat et vitesses | PARTIEL : Espace in-game non testé |
| #420 | 4 DONE, 1 DEFERRED | `app/craft_preload.py`, fallback leveling offline | PARTIEL : installation Craft native non testée |
| #425 | 9 DONE, 1 DEFERRED | `app/pages/organizer/organizer_ui.py` | PARTIEL : design livré, recette native manquante |
| #426 | 2 DONE | setup-python 7.1.0 | PARTIEL : exact-SHA et exécution à qualifier |
| #429 | 8 DONE, 3 DEFERRED | Slots/étoile/glass Organizer | PARTIEL : capture et validation réelle en attente |

### Réexamen **individuel** des 29 PENDING + 2 DEFERRED de #325

Contrat exact : [#321](https://github.com/r9327/Dof-Atlas/issues/321), rapport #325 ; comparer notamment aux corrections #398, #406, #416, #425, #429 et aux fichiers courants. `PARTIEL` = traces de code et/ou tests dans les PR suivantes, **pas** réception Unity ni PASS exact-SHA #431. `NON VÉRIFIABLE` = test natif ou preuve absente, **pas** bug confirmé.

| ID historique | Qualification / priorité | Recouvrement ou raison encore ouverte |
| --- | --- | --- |
| MIRR-002 | NON VÉRIFIABLE / P1 | Envoi sans focus vers Unity jamais attesté ; #322 |
| MIRR-005 (DEFERRED) | NON VÉRIFIABLE / P0 | Recette native 1/2/4/8, UIPI/latences ; #322 |
| MIRR-006 | PARTIEL / P0 | Clics maître, paires physiques et double émission ; #406, `mirror_input.py`, tests hooks |
| MIRR-007 | PARTIEL / P0 | FIFO bornée et tests simulés #325/#406 ; acquittement Unity différé #322 non fait |
| MIRR-008 | PARTIEL / P0 | Vérification HWND/focus/fenêtre et repli ; #398/#406 ; DPI/minimisation native non attestés |
| MIRR-009 | PARTIEL / P0 | Stop, libération et MacroLock ; #406 ; watchdog/états natifs non attestés |
| MIRR-010 | PARTIEL / P1 | Journaux Doctor et diagnostics #358/#406 ; mesures réelles p50/p95/p99 manquantes |
| MIRR-011 | PARTIEL / P1 | Switch/Direction/Auto-groupe/Zaap ; #398/#406/#416 et correctifs #431 en cours |
| MIRR-012 | PARTIEL / P1 | Fanout simulé 2/4/6/8, sans latence/CPU/RAM DOFUS réelle ; #406/#411 |
| MIRR-013 | PARTIEL / P1 | Tests Miroir/Qt et suites Windows synthétiques #406 ; recette physique non réalisée |
| ATOR-001 | PARTIEL / P0 | Stop urgence et verrouillage #406, `test_runtime_state.py` ; vrai PC non testé |
| ATOR-004 | PARTIEL / P1 | Overlay hors Atlas et focus #406 ; validation native hors fenêtres de test manquante |
| ATOR-005 | PARTIEL / P2 | Portraits/affichage radial #406/#425 ; rendu final non signé |
| ATOR-006 | PARTIEL / P2 | Typographie/titre radial #425/#429 ; validation capture non signée |
| ATOR-007 | PARTIEL / P2 | Centre de la roue/logo #406/#425 ; validation capture non signée |
| ATOR-008 | PARTIEL / P2 | Style Unity radial #425/#429 ; validation visuelle native manquante |
| ATOR-011 | PARTIEL / P1 | Retrait Positions #416/#425 ; vérification consommateurs Graphify exact-SHA requise |
| ATOR-012 | PARTIEL / P1 | Auto-groupe et exclusions, `auto_group.py`/#406 ; vrai chat Unity non reçu |
| ATOR-015 | PARTIEL / P2 | Alignement Organizer #425/#429 ; capture DPI finale non signée |
| ATMC-001 | PARTIEL / P1 | Orchestration 2–8 simulée #406 ; temps de réaction DOFUS réel inconnu |
| ATMC-003 | NON VÉRIFIABLE / P1 | Objets interactifs Unity / changement de carte non testés |
| ATZP-002 | PARTIEL / P2 | Croix Zaap/espacement #425/#429 ; rendu native DPI à vérifier |
| ATZP-003 | PARTIEL / P1 | Suppression Positions #416/#425 ; audit Graphify consommateurs requis |
| ATZP-004 | PARTIEL / P1 | Profils/vitesses #416/#431 ; effet Unity et latence non mesurés |
| ATZP-005 | PARTIEL / P2 | Taille/survol suppression de raccourci #425 ; capture non signée |
| ATQA-002 (DEFERRED) | NON VÉRIFIABLE / P0 | Recette multi-DOFUS Unity #322/#412 non effectuée |
| MIRR-014 | PARTIEL / P0 | Séquence DOWN/UP, source et cibles #406, suites hooks ; vérification native absente |
| MIRR-015 | PARTIEL / P0 | Résolution raccourcis et suppression doublons #406, `test_hotkeys.py` |
| MIRR-016 | PARTIEL / P0 | Changement de mode/profil et annulation des générations #406/#431 ; worker déjà en vol à vérifier |
| MIRR-017 | PARTIEL / P1 | Consommateurs profils Normal/Rapide/Instantané #416/#431 ; fiabilité/latences natives inconnues |
| MIRR-018 | PARTIEL / P1 | Doctor/hooks/diagnostics #358/#406 ; p50/p95/p99 exhaustifs sur DOFUS manquants |

**Comptabilité :** 31/31 requalifiés, aucun promu artificiellement en DONE ou bug avéré. Seuls des tests actuels, la revue de l'implémentation et la recette native pourront fermer les obligations correspondantes. Les réclamations uniquement visuelles ou natives restent propriétaires des issues de preuve existantes, pas de la PR UI ouverte.

### Matrice ciblée de preuves / risques du candidat #431

| Contrat | Sources actuellement inspectées | Tests/éléments historiques | Constat et limite | Propriétaire |
| --- | --- | --- | --- | --- |
| GQA-002 Miroir/Stop/vitesses | `app/core/{runtime_state,settings,macro_lock}.py`, `app/pages/organizer/organizer_hotkeys.py`, `app/macros/{mirror_input,auto_group,zaap,input_tools}.py` | `test_runtime_state.py`, `test_organizer_macro_generation.py`, `test_organizer_speed_presets.py`, `test_organizer_sendinput.py` | ÉCHEC confirmé au HEAD précédent `cfd1024a`: 2 erreurs de fixtures `SimpleNamespace` dans 169 tests synthétiques Windows. Fixtures rectifiées au commit suivant ; **non rejouées**. Réception Unity : NOT_RUN | GPT + #322/#412 |
| GQA-003 Craft | `app/pages/craft_page.py`, `app/craft_preload.py`, `app/constants.py`, `local_dofus_data/repositories.py` | #407/#420 ; `test_craft_fixes.py`, `test_craft_leveling_offline.py` | Clic métier décale popup avec QTimer ; guide éditorial `data/raw/json/gamosaurus/metiers_leveling.json` optionnel et non garanti dans archive ; fallback local non optimisé ; images/LFS et installation NOT_RUN | GPT + #421 |
| GQA-004 Launcher | `app/distribution/{install,launcher,archive_parts,health}.py` | #285 ; `test_distribution_smart_update.py`, `test_distribution_launcher_noop_offline.py` | Manifest SHA, rollback, CoW si disponible ; repli copie des octets inchangés sur volume ordinaire. Ne **pas** changer en hardlink mutable ; temps réseau/NTFS/Home installés NOT_RUN | GPT + #287 |
| GQA-005 Doctor | `AI_ENTRYPOINT.md`, `tools/atlas_doctor_lib/oss_router.py` et runs historiques #392/#394/#397/#413/#426 | #358, tests `test_doctor_oss_*.py` ; SHA/artefacts encore à réconcilier | Appels opt-in, outil absent != PASS ; aucun Doctor exact-SHA exécuté dans cette session | GPT + #346 |
| GQA-006/GQA-007 | Contrat #430, checklist présente, commits #431 | Windows synthetic au précédent HEAD : Guard candidat tests PASS, contrat FAIL (SHA ancien) ; Phase SKIPPED | Écriture des preuves au **dernier HEAD** seulement. Aucun résultat natif, aucune certification ou revue globale finale prétendue | GPT puis utilisateur |

**Garde de sortie :** poursuivre les vérifications sans lancer de FULL répétées ; une décision finale de revue nécessite la revue commit-par-commit, l'audit global, les tests ciblés et les preuves du **HEAD final**. La recette physique demeure NOT_RUN si elle n'est pas fournie.
