# Doctor UI — oracles visuels réels, Succès et anti-faux PASS

> PLAN DE TRAVAIL — PR brouillon, aucun correctif applicatif encore implémenté. Ne pas fusionner sur la seule présence de ce document.

## Référence vérifiée

- Dépôt canonique : `r9327/Dof-Atlas` ; base au démarrage : `main` @ `6dcdd2a86e7dfbe0b30bb92f70528e308a615227` (2026-10-17).
- Audit Doctor × Graphify du 17 octobre : 13 488 nœuds, 39 334 arêtes, 976 fichiers Python ; 0 blocage architectural démontré par le graphe.
- Source : registre des 51 priorités, CI applicative complète et artefacts exact-SHA. Les statuts « REVIEW » sont des hypothèses, non des régressions confirmées.
- Condition impérative : recontrôler le HEAD GitHub réel à la reprise, `git rev-parse HEAD`, `git status --short`; ne pas réutiliser une preuve d'un autre SHA.

## Périmètre strict — 7 tâches

- [ ] **P1-01 — Rendu carré des glyphes dans les PNG Qt.** Comparer environnement offscreen Windows, fontes Qt, glyphes UTF-8 et EXE réel; produire une image de référence accentuée lisible; défaut runner ≠ défaut produit.
- [ ] **P1-02 — Oracle de lisibilité/typographie.** Vérifier glyphes, texte attendu, troncature, clipping, contraste utile et rendu; statut NOT_COVERED si l'oracle visuel ne sait pas conclure, sans faux PASS.
- [ ] **P1-03 — Scénario clic Succès → fiche réellement visible.** Cliquer une entrée réelle et vérifier l'identifiant, les données, z-order, taille, visibilité effective après événements Qt et preuve PNG/arbre sur deux tailles; cible le défaut #201 sans réparer le produit ici.
- [ ] **P1-04 — Oracle d'effet final des actions.** Pour liens, navigation, cases, cadenas et transitions, comparer le résultat final à un état attendu; les signaux/callbacks seuls ne suffisent pas.
- [ ] **P1-06 — Géométrie, scroll, hit-test et boutons.** Tester overlaps, contrôles masqués, scroll horizontal, cibles réelles, clipping et viewport; distinguer descendants et éléments légitimement hors cadre.
- [ ] **P1-08 — Verdicts de preuves exact-SHA.** Bloquer PASS si scénario requis non exécuté, preuve corrompue/absente, hash/SHA incohérent, couverture partielle ou PNG inexploitable; conserver NOT_COVERED, BLOCKED et REVIEW.
- [ ] **P2-17 — Extension ciblée de Doctor UI.** Inventorier familles d'écrans avec/sans oracle réel; ajouter scénarios à valeur d'utilisateur (Succès/Quêtes/Guides, puis équipement/organizer/zaap/craft) avec budget et sélection par impact.

## Frontières et dépendances

Socle indépendant. S'intégrer aux correctifs produit de #201 sans les dupliquer; cette PR modifie Doctor et ses tests, pas le moteur des Guides.

## Réalisation attendue

1. Inventorier toutes les preuves connues et les consommateurs réels, établir baseline exacte et état de couverture.
2. Reproduire les problèmes signalés par un témoin cassé et sain, isoler la cause, justifier chaque changement; ne modifier que le sous-système de la présente PR.
3. Ajouter des tests ciblés de non-régression et les assertions de comportement, pas seulement des tests de présence d'API.
4. Publier les artefacts de résultats structurés (SHA, fichier/fonction/ligne, source, statut, limite, impact, proposition, contrôle exécuté).
5. Réexécuter Doctor/Graphify/tests UI/benchmark selon l'impact de la modification et vérifier les gates obligatoires à la fusion.
6. Maintenir une liste claire RESTE / FAIT / NON COUVERT; aucun PASS déduit d'un test sauté ou d'une preuve ancienne.

## Critères de sortie mesurables

Tests synthétiques sains et cassés + vraies fenêtres Qt, cold et hot, captures originales hachées, tailles 1280×720 et 1920×1080 (ou dimensions canoniques), vrai contenu public. Régression injectée doit échouer. Selection UI ciblée par le code modifié; aucun FULL non motivé.

- Toute sous-tâche ci-dessus doit être `PASS` prouvé ou `BLOCKED` avec motif et vérification restante; un candidat attendu peut être `NO_CHANGE_JUSTIFIED` documenté.
- Revue des erreurs de CI + régressions post-merge, documentation utilisateur/agence mise à jour si comportement public modifié.
- Aucune suppression, fusion de fichiers, refonte ou optimisation RAM sans preuve et tests d'impact.

## Carte des PR du programme

- Réparations de Guides/Succès : **#201** (ne pas dupliquer les fixes).
- Nouveautés non spécifiées : **#202** (ne pas toucher).
- Audit natif historique : **#175 FERMÉE sans fusion** ; relayée par lot natif distinct.
- Les autres travaux sont répartis en PR brouillon indépendantes créées dans la même campagne. Le programme couvre 51/51 IDs sans duplication de responsabilité.

## Implémentation en cours — oracle Succès réel (17/10/2026)

**Nouveau scénario Doctor UI** `achievement-detail` : il est ajouté au catalogue des scénarios et sélectionnable explicitement dans le workflow Windows. Le plan d'impact choisit désormais également ce scénario lorsque le détecteur Doctor UI ou un des consommateurs réels du détail Succès change, en plus du `validator-smoke` lorsque pertinent.

Le worker `doctor_ui_qt.py` :
1. vérifie que `AchievementsView` n'avait pas été matérialisée avant le premier accès à l'onglet Succès ;
2. ouvre l'onglet **réel** de l'Encyclopédie et attend une liste non vide issue du fournisseur de données publiques ;
3. choisit une ligne existante `QListWidgetItem`, lit son véritable `Qt.UserRole` et le nom dans le fournisseur ; `QTest.mouseClick` est envoyé sur le vrai viewport après contrôle du hit-test ; aucun callback n'est mocké ;
4. compare l'ID courant, le statut d'ouverture, le widget actif du `AchievementDetailStack`, la visibilité de `GuideRightPanelScroll`, de `AchievementDetailBody` et du libellé `AchievementDetailTitle`, l'ID du modèle présent dans le corps et le titre réel du fournisseur ;
5. vérifie aux **deux tailles 1200×800 et 960×640** que le panneau a une largeur/hauteur utilisable et que le titre est réellement atteignable au hit-test Qt, avec arbre de widgets et PNG produit par la session.

Les quatre assertions exigées par `required_assertions` sont `achievement-detail/first-open-lazy`, `achievement-detail/click-opens-detail`, `achievement-detail/geometry-1200`, `achievement-detail/geometry-960`. Elles correspondent exactement aux références consommées par le comparateur P3-12 de la #222. L'absence d'une assertion ou un échec bloque le verdict comme auparavant.

**Tests négatifs nouveaux** : une `QListWidget` réelle dont le signal `itemClicked` a été déconnecté reçoit toujours le clic, mais ne prouve plus aucun effet ; un inspecteur de la chaîne finale signale à quelle étape une mauvaise destination, une mauvaise ID, un panneau de largeur nulle, une fiche absente, un titre incorrect ou un hit-test masqué casse l'interaction.

**Limites** : cela est une **implémentation candidate**, pas un PASS CI ni la réparation du produit. La régression utilisateur est encore à prouver sur l'EXE installé ; toute rupture réellement observée doit rester FAIL. La production de la session Qt au SHA exact et son artefact PNG dépend du run Windows, tandis que les réparations restent exclusivement dans la #201. Les autres tâches de la #216 (glyphes/typographie, autres familles d'écrans, seuils de contraste) ne sont pas déclarées achevées.

## Routage CI du détecteur Doctor UI sans certification inutile

Le premier run du nouveau détecteur a prouvé deux points : le routage de l'Encyclopédie inclut désormais `achievement-detail` (ancien test d'ensemble mis à jour), mais l'ancien `ci_tooling_scope` ne connaissait pas `doctor_ui.py`, `doctor_ui_qt.py` et `test_doctor_ui_qt.py` comme outillage isolé, et avait déclenché le fallback **FULL_REQUIRED / DOCTOR_PLAN_UNAVAILABLE** sur des fichiers n'appartenant pas au produit.

Un contrat ciblé et *fail-closed* a été ajouté :
- Ces **trois chemins précis** peuvent être reconnus comme changements du détecteur uniquement après lecture AST valide de la source locale (racine vérifiée, taille bornée, pas de symlink, pas d'import `app`/`PySide6` au chargement des modules de coordination, pas d'`__import__` dynamique au niveau module).
- Le plan `Doctor CI` ne peut conclure `tooling_only` que si le plan UI exact du candidat est `UI_REQUIRED` et sélectionne **à la fois `validator-smoke` et `achievement-detail`**. Le job Windows réel reste obligatoire. Les chemins produit, les changements mixtes, l'absence de source vérifiable, les scénarios non sélectionnés ou `REVIEW_REQUIRED` conservent la FULL.
- Des tests de contrat vérifient la route ciblée, la route FULL de repli et l'injection d'imports non autorisés. Une FULL automatique n'est pas requalifiée rétroactivement en PASS par ce changement.

Cette sélection ne certifie ni l'EXE installé ni la correction du défaut utilisateur ; le scénario réel peut parfaitement échouer et ses preuves doivent alors rester visibles. La validation est à constater par la CI du SHA **après** la modification et par l'artefact d'impact ciblé.
