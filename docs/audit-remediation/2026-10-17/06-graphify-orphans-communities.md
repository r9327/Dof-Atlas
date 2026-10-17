# Graphify — triage exhaustif nœuds faibles, orphelins et communautés

> PLAN DE TRAVAIL — PR brouillon, aucun correctif applicatif encore implémenté. Ne pas fusionner sur la seule présence de ce document.

## Référence vérifiée

- Dépôt canonique : `r9327/Dof-Atlas` ; base au démarrage : `main` @ `6dcdd2a86e7dfbe0b30bb92f70528e308a615227` (2026-10-17).
- Audit Doctor × Graphify du 17 octobre : 13 488 nœuds, 39 334 arêtes, 976 fichiers Python ; 0 blocage architectural démontré par le graphe.
- Source : registre des 51 priorités, CI applicative complète et artefacts exact-SHA. Les statuts « REVIEW » sont des hypothèses, non des régressions confirmées.
- Condition impérative : recontrôler le HEAD GitHub réel à la reprise, `git rev-parse HEAD`, `git status --short`; ne pas réutiliser une preuve d'un autre SHA.

## Périmètre strict — 6 tâches

- [ ] **P2-20 — Pagination d'analyse réellement exhaustive.** Itérer pages weak/orphan/community avec next_offset; compteur parcouru/total, staleness, erreurs et reprise après interruption. Aucun échantillon LIMIT=30 présenté comme un audit complet.
- [ ] **P3-03 — 8 fichiers sans arêtes import statique.** Rechercher points d'entrée externes, imports différés, callbacks, CLI et packaging avant toute qualification.
- [ ] **P3-04 — 6 nœuds réellement isolés du graphe global.** Vérifier chaque identité, disponibilité, entrées PowerShell ou init; classement utile/boundary/candidat non joint et preuve d'usage.
- [ ] **P3-05 — 333 nœuds de production de degré 1.** Triage intégral par pages sans scan aveugle; consumer-sites, reachability, tests runtime/CLI, classification; aucun code mort sans preuve.
- [ ] **P3-06 — 95 communautés isolées.** Examiner 95/95 dont 30 publiées par aperçu, 65 non qualifiées; expliciter imports, rôle, ownership et groupements; ne pas fusionner selon seul clustering.
- [ ] **P3-10 — 53 communautés de cohésion faible et 1 734 ponts.** Revoir les groupes et ponts inter-communautés, responsabilités redondantes vs API de frontière; proposer action seulement avec impact mesuré et tests.

## Frontières et dépendances

Complément du lot de structure Graphify, sans chevaucher les correctifs applicatifs. Repartir de l'artefact exact SHA du lot structural.

## Réalisation attendue

1. Inventorier toutes les preuves connues et les consommateurs réels, établir baseline exacte et état de couverture.
2. Reproduire les problèmes signalés par un témoin cassé et sain, isoler la cause, justifier chaque changement; ne modifier que le sous-système de la présente PR.
3. Ajouter des tests ciblés de non-régression et les assertions de comportement, pas seulement des tests de présence d'API.
4. Publier les artefacts de résultats structurés (SHA, fichier/fonction/ligne, source, statut, limite, impact, proposition, contrôle exécuté).
5. Réexécuter Doctor/Graphify/tests UI/benchmark selon l'impact de la modification et vérifier les gates obligatoires à la fusion.
6. Maintenir une liste claire RESTE / FAIT / NON COUVERT; aucun PASS déduit d'un test sauté ou d'une preuve ancienne.

## Critères de sortie mesurables

Rapport exhaustif avec ID/path/ligne, compteur entrées traitées, classification CONFIRMÉ/ATTENDU/REVIEW, absence de suppression automatique, données exportables JSON/CSV, signatures SHA, reproduction des cas non importés; zéro fausse preuve par simple degré.

- Toute sous-tâche ci-dessus doit être `PASS` prouvé ou `BLOCKED` avec motif et vérification restante; un candidat attendu peut être `NO_CHANGE_JUSTIFIED` documenté.
- Revue des erreurs de CI + régressions post-merge, documentation utilisateur/agence mise à jour si comportement public modifié.
- Aucune suppression, fusion de fichiers, refonte ou optimisation RAM sans preuve et tests d'impact.

## Carte des PR du programme

- Réparations de Guides/Succès : **#201** (ne pas dupliquer les fixes).
- Nouveautés non spécifiées : **#202** (ne pas toucher).
- Audit natif historique : **#175 FERMÉE sans fusion** ; relayée par lot natif distinct.
- Les autres travaux sont répartis en PR brouillon indépendantes créées dans la même campagne. Le programme couvre 51/51 IDs sans duplication de responsabilité.
