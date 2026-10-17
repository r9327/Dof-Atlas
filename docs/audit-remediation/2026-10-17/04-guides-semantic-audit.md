# Guides — qualifier exhaustivement 55 remarques et 200 prérequis

> PLAN DE TRAVAIL — PR brouillon, aucun correctif applicatif encore implémenté. Ne pas fusionner sur la seule présence de ce document.

## Référence vérifiée

- Dépôt canonique : `r9327/Dof-Atlas` ; base au démarrage : `main` @ `6dcdd2a86e7dfbe0b30bb92f70528e308a615227` (2026-10-17).
- Audit Doctor × Graphify du 17 octobre : 13 488 nœuds, 39 334 arêtes, 976 fichiers Python ; 0 blocage architectural démontré par le graphe.
- Source : registre des 51 priorités, CI applicative complète et artefacts exact-SHA. Les statuts « REVIEW » sont des hypothèses, non des régressions confirmées.
- Condition impérative : recontrôler le HEAD GitHub réel à la reprise, `git rev-parse HEAD`, `git status --short`; ne pas réutiliser une preuve d'un autre SHA.

## Périmètre strict — 2 tâches

- [ ] **P2-01 — 55 remarques Guide à traiter unitairement.** Exporter inventaire complet 37 formulations et 18 conditions vagues; retrouver guide/partie/page/ligne, source Dofus, statut CONFIRMÉ/FAUX_POSITIF/BLOCKED, correction exacte et test de rendu.
- [ ] **P2-02 — 200 avertissements de prérequis à qualifier.** Contrôler 173 ordres de complétion, 19 dépendances conditionnelles/transversales, 6 quêtes déjà actives, 2 conditions opaques; vérifier causalité (niveau, succès, chaîne, accès), ordre et déduplication; aucun raccourci par compteur.

## Frontières et dépendances

PR d'audit/qualification non mutatif. Les corrections des Guides et du moteur appartiennent uniquement à #201; l'accueil et les nouveautés restent hors périmètre; #202 est réservée.

## Réalisation attendue

1. Inventorier toutes les preuves connues et les consommateurs réels, établir baseline exacte et état de couverture.
2. Reproduire les problèmes signalés par un témoin cassé et sain, isoler la cause, justifier chaque changement; ne modifier que le sous-système de la présente PR.
3. Ajouter des tests ciblés de non-régression et les assertions de comportement, pas seulement des tests de présence d'API.
4. Publier les artefacts de résultats structurés (SHA, fichier/fonction/ligne, source, statut, limite, impact, proposition, contrôle exécuté).
5. Réexécuter Doctor/Graphify/tests UI/benchmark selon l'impact de la modification et vérifier les gates obligatoires à la fusion.
6. Maintenir une liste claire RESTE / FAIT / NON COUVERT; aucun PASS déduit d'un test sauté ou d'une preuve ancienne.

## Critères de sortie mesurables

Traçabilité 55/55 et 200/200 en fichier lisible machine+humain; pas de suppression mécanique; preuve Dofus ou état à confirmer; tests ciblés de cohérence JSON/Guide; issue/liaison des corrections prouvées vers #201, pas de doublons d'implémentation.

- Toute sous-tâche ci-dessus doit être `PASS` prouvé ou `BLOCKED` avec motif et vérification restante; un candidat attendu peut être `NO_CHANGE_JUSTIFIED` documenté.
- Revue des erreurs de CI + régressions post-merge, documentation utilisateur/agence mise à jour si comportement public modifié.
- Aucune suppression, fusion de fichiers, refonte ou optimisation RAM sans preuve et tests d'impact.

## Carte des PR du programme

- Réparations de Guides/Succès : **#201** (ne pas dupliquer les fixes).
- Nouveautés non spécifiées : **#202** (ne pas toucher).
- Audit natif historique : **#175 FERMÉE sans fusion** ; relayée par lot natif distinct.
- Les autres travaux sont répartis en PR brouillon indépendantes créées dans la même campagne. Le programme couvre 51/51 IDs sans duplication de responsabilité.
