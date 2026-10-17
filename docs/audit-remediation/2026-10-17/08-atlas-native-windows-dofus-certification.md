# Atlas natif — certification Dofus/Npcap, EXE installé, update et rollback

> PLAN DE TRAVAIL — PR brouillon, aucun correctif applicatif encore implémenté. Ne pas fusionner sur la seule présence de ce document.

## Référence vérifiée

- Dépôt canonique : `r9327/Dof-Atlas` ; base au démarrage : `main` @ `6dcdd2a86e7dfbe0b30bb92f70528e308a615227` (2026-10-17).
- Audit Doctor × Graphify du 17 octobre : 13 488 nœuds, 39 334 arêtes, 976 fichiers Python ; 0 blocage architectural démontré par le graphe.
- Source : registre des 51 priorités, CI applicative complète et artefacts exact-SHA. Les statuts « REVIEW » sont des hypothèses, non des régressions confirmées.
- Condition impérative : recontrôler le HEAD GitHub réel à la reprise, `git rev-parse HEAD`, `git status --short`; ne pas réutiliser une preuve d'un autre SHA.

## Périmètre strict — 3 tâches

- [ ] **P2-11 — Vrais événements Dofus/Npcap et personnage.** Tester session réelle autorisée, identification personnage sans ambiguïté, quest journal/snapshot/completion, succès, connexions/déconnexions, déduplication, profil de privilèges, fallback et absence de cross-character.
- [ ] **P2-12 — EXE Windows public réellement installé.** Vérifier setup public, installation personnalisée, update auto, interruption, récupération, réparation, rollback effectif, persistance paramètres et nettoyage; preuves exact Release/manifest/hash.
- [ ] **P2-13 — Parcours natifs installés non couverts.** Sur binaire installable Windows, parcourir Home, Guides, Quêtes, Succès, Craft SQLite, Équipement WebEngine, Organizer, Zaap, fermeture et réouverture, workers, équipements, sans Python de dev.

## Frontières et dépendances

Remplace le travail encore ouvert de l'ancienne PR #175, désormais fermée sans merge; réutiliser ses preuves comme historique uniquement, jamais comme PASS du SHA actuel. Respecter les corrections #201 et les engagements de certification.

## Réalisation attendue

1. Inventorier toutes les preuves connues et les consommateurs réels, établir baseline exacte et état de couverture.
2. Reproduire les problèmes signalés par un témoin cassé et sain, isoler la cause, justifier chaque changement; ne modifier que le sous-système de la présente PR.
3. Ajouter des tests ciblés de non-régression et les assertions de comportement, pas seulement des tests de présence d'API.
4. Publier les artefacts de résultats structurés (SHA, fichier/fonction/ligne, source, statut, limite, impact, proposition, contrôle exécuté).
5. Réexécuter Doctor/Graphify/tests UI/benchmark selon l'impact de la modification et vérifier les gates obligatoires à la fusion.
6. Maintenir une liste claire RESTE / FAIT / NON COUVERT; aucun PASS déduit d'un test sauté ou d'une preuve ancienne.

## Critères de sortie mesurables

Matrice PASS/FAIL/BLOCKED/NOT_COVERED des parcours natifs. Windows runner frozen E2E (réel) + Dofus/Npcap terrain quand environnement autorisé disponible; si absent, blocage explicite, jamais synthèse ≠ réel. Protéger infos personnelles et ne pas inventer de sessions jeu.

- Toute sous-tâche ci-dessus doit être `PASS` prouvé ou `BLOCKED` avec motif et vérification restante; un candidat attendu peut être `NO_CHANGE_JUSTIFIED` documenté.
- Revue des erreurs de CI + régressions post-merge, documentation utilisateur/agence mise à jour si comportement public modifié.
- Aucune suppression, fusion de fichiers, refonte ou optimisation RAM sans preuve et tests d'impact.

## Carte des PR du programme

- Réparations de Guides/Succès : **#201** (ne pas dupliquer les fixes).
- Nouveautés non spécifiées : **#202** (ne pas toucher).
- Audit natif historique : **#175 FERMÉE sans fusion** ; relayée par lot natif distinct.
- Les autres travaux sont répartis en PR brouillon indépendantes créées dans la même campagne. Le programme couvre 51/51 IDs sans duplication de responsabilité.
