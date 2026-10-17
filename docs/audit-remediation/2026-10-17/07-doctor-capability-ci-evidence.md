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

## Livraison intermédiaire de la PR #222 (non certifiée)

- Matrice de **18 témoins positifs et 18 contrôles négatifs** rattachés à des méthodes `unittest` distinctes. La présence des fonctions n'est pas une preuve d'exécution.
- Contrat `doctor_capability_test_evidence` **schema_version 2** : exécute les 36 méthodes en un sous-processus `unittest -v`; associe les verdicts aux IDs exacts, rejette skipped / xfail / doublon / sortie 0 sans compte correct / log tronqué / changement de SHA ou de worktree. L'ancien JSON v1 ne peut pas être réutilisé comme preuve v2.
- Contrat existant `atlas-doctor-agent/v1` enrichi du champ optionnel `source_evidence` : SHA source, symboles AST avec fichier et ligne, erreurs explicites, tests conseillés, statut d'exécution et absence de preuve CI indiquée par des valeurs nulles. Ni Codex ni ChatGPT n'ont besoin d'accès privés supplémentaires pour interpréter ce JSON ; ils doivent appliquer leur politique d'accès au dépôt pour les liens non publics.

Commandes de reproduction (lancer sur le clone au **HEAD exact**, propre, dépendances Python nécessaires installées) :

```bash
python -m unittest -v tests.test_atlas_doctor_capabilities tests.test_atlas_doctor_capability_evidence tests.test_atlas_doctor_agent_protocol
python -m tools.atlas_doctor --json capabilities --run-tests --timeout 300
python -m tools.atlas_doctor --json agent plan tools/atlas_doctor_lib/capability_evidence.py --base-ref HEAD
```

**Limites** : les témoins restent des tests du code et de ses garde-fous, pas une certification des comportements réels sur le Windows installé ; les quatre régressions UI et l'attestation indépendante CI restent à établir. Aucun résultat de commande ci-dessus n'est affirmé PASS sans exécution vérifiée.

## Validation supplémentaire — CI et contrat agents

- Incident réellement reproduit : run [39046923009](https://github.com/r9327/Dof-Atlas/actions/runs/39046923009), `Doctor / Focused CI Evidence` en échec car un journal de 36 témoins dépassait la limite historique de 12 000 caractères. Ce FAIL était correct (aucun faux PASS), mais empêchait d'examiner les verdicts complets.
- Correctif : transcription `unittest -v` conservée jusqu'à une **limite bornée de 256 000 caractères** ; au-delà, verdict `BLOCKED` inchangé, sans réutilisation de journal incomplet. Les champs `raw_stderr_chars` et `log_limit_chars` documentent la longueur observée. Le job envoie aussi les diagnostics et archive le JSON en cas d'échec, sans masquer le FAIL CI.
- La CI ciblée appelle et valide le rapport `doctor_capability_test_evidence/v2` au SHA exact (18 cas positifs + 18 contrôles négatifs). Le fichier `artifacts/doctor_ci/capability_evidence.json` est publié dans l'artefact `doctor-focused-<run>-<attempt>`.
- En parallèle, Doctor produit `artifacts/doctor_ci/agent_plan.json` par `run_agent_action(action="plan")` sur **un vrai fichier Python du dépôt**, puis le recharge via `json.loads` comme le ferait un client standard. La vérification impose `protocol=atlas-doctor-agent/v1`, SHA identique, ancrage de la fonction `run_capability_witnesses` avec ligne strictement positive et `SOURCE_DEFINITION_ONLY`, sans attribuer à ce simple export une certification FULL ou une attestation GitHub indépendante.
- Le format est du JSON ordinaire, sans API propriétaire. Codex, ChatGPT et d'autres clients peuvent le lire sous réserve d'accès aux fichiers, mais leur consommation réelle en dehors de cette vérification reste à tester séparément ; aucune intégration externe n'est prétendue ici.

**État de sortie :** nouveaux artefacts et contrats en cours de validation au prochain HEAD de la PR. Aucune de ces mesures ne prouve à elle seule les quatre parcours UI sur Windows ni ne remplace la certification indépendante exigée pour les modifications produit.
