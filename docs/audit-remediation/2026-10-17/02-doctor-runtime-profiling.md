# Doctor Runtime — Qt lifecycle, CPU/RAM, baselines et diagnostic exact-SHA

> PLAN DE TRAVAIL — PR brouillon, aucun correctif applicatif encore implémenté. Ne pas fusionner sur la seule présence de ce document.

## Référence vérifiée

- Dépôt canonique : `r9327/Dof-Atlas` ; base au démarrage : `main` @ `6dcdd2a86e7dfbe0b30bb92f70528e308a615227` (2026-10-17).
- Audit Doctor × Graphify du 17 octobre : 13 488 nœuds, 39 334 arêtes, 976 fichiers Python ; 0 blocage architectural démontré par le graphe.
- Source : registre des 51 priorités, CI applicative complète et artefacts exact-SHA. Les statuts « REVIEW » sont des hypothèses, non des régressions confirmées.
- Condition impérative : recontrôler le HEAD GitHub réel à la reprise, `git rev-parse HEAD`, `git status --short`; ne pas réutiliser une preuve d'un autre SHA.

## Périmètre strict — 5 tâches

- [ ] **P1-07 — Suivi des cycles de vie Qt et WebEngine.** Observer QThreads, timers, callbacks connect/disconnect, deleteLater, signaux doublés, WebEngine et objets après fermeture; tests ouverture→retour Home→réouverture, GC, processus.
- [ ] **P2-08 — Corrélation Graphify × runtime.** Relier traces horodatées CPU/RAM/Qt/UI aux fonctions et connexions exactes du même SHA; ne jamais déclarer une arête statique cause de fuite sans trace.
- [ ] **P2-09 — Baselines runtime robustes.** Mesurer 3 processus frais sur même runner/catalogue, fixer baseline SHA+environnement, vérifier variance, first-open vs hot, regression threshold et anomalie > 3 secondes; blocage Success existant à diagnostiquer précisément.
- [ ] **P2-10 — Mémoire de longue durée.** Protocole cyclique multi-modules avec après-retour Home/GC, arbres de processus et durée; différencier caches légitimes, high-water allocator, rétention Qt réelle; ne pas rétablir un budget RAM arbitraire.
- [ ] **P2-16 — Observabilité réelle Qt.** Instrumentation explicite et réversible des signaux Qt, dispatch main thread, callbacks natifs, owners QObject/worker, events; coûts d'observation mesurés et bornés.

## Frontières et dépendances

À intégrer avec le module Doctor Runtime déjà existant, sans instrumentation permanente de DOFUS Atlas. Le traitement produit du gel Succès reste #201.

## Réalisation attendue

1. Inventorier toutes les preuves connues et les consommateurs réels, établir baseline exacte et état de couverture.
2. Reproduire les problèmes signalés par un témoin cassé et sain, isoler la cause, justifier chaque changement; ne modifier que le sous-système de la présente PR.
3. Ajouter des tests ciblés de non-régression et les assertions de comportement, pas seulement des tests de présence d'API.
4. Publier les artefacts de résultats structurés (SHA, fichier/fonction/ligne, source, statut, limite, impact, proposition, contrôle exécuté).
5. Réexécuter Doctor/Graphify/tests UI/benchmark selon l'impact de la modification et vérifier les gates obligatoires à la fusion.
6. Maintenir une liste claire RESTE / FAIT / NON COUVERT; aucun PASS déduit d'un test sauté ou d'une preuve ancienne.

## Critères de sortie mesurables

Probes injectées (fuite, double signal, blocage du thread), témoins sains/cassés, preuve exacte du thread, 3 fresh processes Windows, zéro instrumentation cachée en production, comparaisons coût diagnostic activé/désactivé; aucun label PASS sur trace absente.

- Toute sous-tâche ci-dessus doit être `PASS` prouvé ou `BLOCKED` avec motif et vérification restante; un candidat attendu peut être `NO_CHANGE_JUSTIFIED` documenté.
- Revue des erreurs de CI + régressions post-merge, documentation utilisateur/agence mise à jour si comportement public modifié.
- Aucune suppression, fusion de fichiers, refonte ou optimisation RAM sans preuve et tests d'impact.

## Carte des PR du programme

- Réparations de Guides/Succès : **#201** (ne pas dupliquer les fixes).
- Nouveautés non spécifiées : **#202** (ne pas toucher).
- Audit natif historique : **#175 FERMÉE sans fusion** ; relayée par lot natif distinct.
- Les autres travaux sont répartis en PR brouillon indépendantes créées dans la même campagne. Le programme couvre 51/51 IDs sans duplication de responsabilité.
