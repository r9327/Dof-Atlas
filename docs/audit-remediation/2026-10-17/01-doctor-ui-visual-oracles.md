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
