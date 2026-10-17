# Graphify DEEP — dépendances, cycles, hubs, responsabilités et refactor prudent

> PLAN DE TRAVAIL — PR brouillon, aucun correctif applicatif encore implémenté. Ne pas fusionner sur la seule présence de ce document.

## Référence vérifiée

- Dépôt canonique : `r9327/Dof-Atlas` ; base au démarrage : `main` @ `6dcdd2a86e7dfbe0b30bb92f70528e308a615227` (2026-10-17).
- Audit Doctor × Graphify du 17 octobre : 13 488 nœuds, 39 334 arêtes, 976 fichiers Python ; 0 blocage architectural démontré par le graphe.
- Source : registre des 51 priorités, CI applicative complète et artefacts exact-SHA. Les statuts « REVIEW » sont des hypothèses, non des régressions confirmées.
- Condition impérative : recontrôler le HEAD GitHub réel à la reprise, `git rev-parse HEAD`, `git status --short`; ne pas réutiliser une preuve d'un autre SHA.

## Périmètre strict — 7 tâches

- [ ] **P2-19 — Inventaire code mort, doublons, responsabilités, JSON→UI.** Inspecter fichiers/fonctions/consommateurs import statique + dynamique et Qt; prouver inaccessibilité ou duplication par scénario, analyser lineage JSON, ownership data et UI; produire propositions de refactor sûres.
- [ ] **P3-01 — 17 hotspots structurels.** Dossier par fichier : classes/fonctions/lignes,  consommateur, imports, responsabilité, risque concret, gain hypothétique, tests avant/après; prioriser guides_view, encyclopedia_page, network/bootstrap.
- [ ] **P3-02 — 4 familles cycles d'imports.** Distinguer import-time, deferred, TYPE_ONLY; tests d'ordre d'import et mécanismes de chargement; ne corriger que cycle provoquant régression réelle.
- [ ] **P3-07 — 42 fichiers à haut fanout / 460 imports interdomaines.** Matrice orientée app/modules/network/pages/core; séparation interface/provider/service/transport; statuer légitime vs couplage nocif avec preuve.
- [ ] **P3-08 — 2 222 liens inférés.** Classer liens EXTRACTED/INFERRED, assurer validation source, tracer faux positifs, dépendances dynamiques et sites Qt; ne pas promouvoir une inférence en preuve.
- [ ] **P3-09 — Conserver 6 API communes légitimes.** Protéger constants, contracts, text, logger, ui/components, json_store et interfaces stables; aucun découpage arbitraire des hubs partagés.
- [ ] **P3-11 — Décision sur une architecture événementielle.** Étudier uniquement des transitions prouvées problématiques, proposer petit RFC event-driven/adapters, mesurer coût RAM/CPU et rollback; ne pas réécrire Atlas.

## Frontières et dépendances

Audit en lecture seule en premier. Recalcul Graphify exact-SHA; ne pas déployer de réseau événementiel ni fusionner du code sur un score de graph seul.

## Réalisation attendue

1. Inventorier toutes les preuves connues et les consommateurs réels, établir baseline exacte et état de couverture.
2. Reproduire les problèmes signalés par un témoin cassé et sain, isoler la cause, justifier chaque changement; ne modifier que le sous-système de la présente PR.
3. Ajouter des tests ciblés de non-régression et les assertions de comportement, pas seulement des tests de présence d'API.
4. Publier les artefacts de résultats structurés (SHA, fichier/fonction/ligne, source, statut, limite, impact, proposition, contrôle exécuté).
5. Réexécuter Doctor/Graphify/tests UI/benchmark selon l'impact de la modification et vérifier les gates obligatoires à la fusion.
6. Maintenir une liste claire RESTE / FAIT / NON COUVERT; aucun PASS déduit d'un test sauté ou d'une preuve ancienne.

## Critères de sortie mesurables

Graphify exact-SHA, Doctor graph-audit deep, source-consumer review, dynamique quand disponible, tests de scénarios concernés, refactor-preview sans mutation; comparaison baseline après changement sans fausse baisse des nœuds. Aucun code produit modifié dans le lot initial.

- Toute sous-tâche ci-dessus doit être `PASS` prouvé ou `BLOCKED` avec motif et vérification restante; un candidat attendu peut être `NO_CHANGE_JUSTIFIED` documenté.
- Revue des erreurs de CI + régressions post-merge, documentation utilisateur/agence mise à jour si comportement public modifié.
- Aucune suppression, fusion de fichiers, refonte ou optimisation RAM sans preuve et tests d'impact.

## Carte des PR du programme

- Réparations de Guides/Succès : **#201** (ne pas dupliquer les fixes).
- Nouveautés non spécifiées : **#202** (ne pas toucher).
- Audit natif historique : **#175 FERMÉE sans fusion** ; relayée par lot natif distinct.
- Les autres travaux sont répartis en PR brouillon indépendantes créées dans la même campagne. Le programme couvre 51/51 IDs sans duplication de responsabilité.
