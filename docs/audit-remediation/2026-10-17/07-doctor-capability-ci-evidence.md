# Doctor — 18 capacités certifiables, CI ciblée et preuves lisibles par agents

> PLAN DE TRAVAIL — PR brouillon, aucun correctif applicatif encore implémenté. Ne pas fusionner sur la seule présence de ce document.

## Référence vérifiée

- Dépôt canonique : `r9327/Dof-Atlas` ; base au démarrage : `main` @ `6dcdd2a86e7dfbe0b30bb92f70528e308a615227` (2026-10-17).
- Audit Doctor × Graphify du 17 octobre : 13 488 nœuds, 39 334 arêtes, 976 fichiers Python ; 0 blocage architectural démontré par le graphe.
- Source : registre des 51 priorités, CI applicative complète et artefacts exact-SHA. Les statuts « REVIEW » sont des hypothèses, non des régressions confirmées.
- Condition impérative : recontrôler le HEAD GitHub réel à la reprise, `git rev-parse HEAD`, `git status --short`; ne pas réutiliser une preuve d'un autre SHA.

## Périmètre strict — 4 tâches

- [ ] **P2-15 — 18 capacités Doctor: preuves comportementales.** Établir matrice G01–G04 R05–R09 C10–C13 T14–T16 U17–U18, chaque capacité ayant commande d'appel, témoin sain/cassé réel, artefacts, résultat, portée et limite; distinguer wired AST vs réellement certifié.
- [ ] **P2-18 — CI intelligente et non redondante.** Scoper automatiquement avec diff, import impact et contrats; UI seulement si impact, Doctor FAST avant Full, Full seulement si requis, pas de contrôle skipped interprété PASS, zéro test doit échouer.
- [ ] **P2-21 — Contrat d'usage Codex/ChatGPT/agents.** Schéma d'export JSON documenté pour un client sans accès spécial, preuve source/lien/run/SHA, changement/priorité/action/test, erreur non masquer; tester reproduction d'un diagnostic via outil agent.
- [ ] **P3-12 — Surveiller quatre régressions après correctifs.** Bloquer régression visible après réparations: clic Succès, transition Guide→Quêtes, first-open Succès, rendu/capture; publier delta baseline lié au SHA.

## Frontières et dépendances

Socle transverse avant de marquer les nouvelles capacités Doctor comme certifiées; surveiller l'impact CI des lots UI/Runtime/Graphify.

## Réalisation attendue

1. Inventorier toutes les preuves connues et les consommateurs réels, établir baseline exacte et état de couverture.
2. Reproduire les problèmes signalés par un témoin cassé et sain, isoler la cause, justifier chaque changement; ne modifier que le sous-système de la présente PR.
3. Ajouter des tests ciblés de non-régression et les assertions de comportement, pas seulement des tests de présence d'API.
4. Publier les artefacts de résultats structurés (SHA, fichier/fonction/ligne, source, statut, limite, impact, proposition, contrôle exécuté).
5. Réexécuter Doctor/Graphify/tests UI/benchmark selon l'impact de la modification et vérifier les gates obligatoires à la fusion.
6. Maintenir une liste claire RESTE / FAIT / NON COUVERT; aucun PASS déduit d'un test sauté ou d'une preuve ancienne.

## Critères de sortie mesurables

Docteur ne renvoie jamais 18/18 PASS à partir d'un inventaire AST; vrai witness fresh process et cas négatifs, preuves CI exactes, coût/latence mesurés, aucun FULL ni Windows lourd déclenché sans obligation, verdict NOT_APPLICABLE explicite.

- Toute sous-tâche ci-dessus doit être `PASS` prouvé ou `BLOCKED` avec motif et vérification restante; un candidat attendu peut être `NO_CHANGE_JUSTIFIED` documenté.
- Revue des erreurs de CI + régressions post-merge, documentation utilisateur/agence mise à jour si comportement public modifié.
- Aucune suppression, fusion de fichiers, refonte ou optimisation RAM sans preuve et tests d'impact.

## Carte des PR du programme

- Réparations de Guides/Succès : **#201** (ne pas dupliquer les fixes).
- Nouveautés non spécifiées : **#202** (ne pas toucher).
- Audit natif historique : **#175 FERMÉE sans fusion** ; relayée par lot natif distinct.
- Les autres travaux sont répartis en PR brouillon indépendantes créées dans la même campagne. Le programme couvre 51/51 IDs sans duplication de responsabilité.
