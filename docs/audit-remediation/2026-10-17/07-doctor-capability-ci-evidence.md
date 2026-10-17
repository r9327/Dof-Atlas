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

## Validation CI indépendante du 17/10 — SHA 097425e4

Run GitHub [39048421383](https://github.com/r9327/Dof-Atlas/actions/runs/39048421383) **SUCCESS global**, y compris `Doctor / CI Verdict`, `Doctor / PR FAST`, AI Context, Graphify, Doctor UI Qt et `Doctor / Focused CI Evidence`. Le workflow déclenche bien le chemin `tooling_only`, sans FULL produit. Les jobs volontairement non sélectionnés sont **skipped**, pas PASS.

Le job ciblé a effectivement exécuté **18/18 témoins positifs + 18/18 contrôles négatifs** et vérifié le JSON de preuve, ainsi que l'export/relecture de `agent_plan.json` sur un vrai fichier source. Les 380 tests de contrats du job sont PASS. Voir l'[artefact 12107090329](https://github.com/r9327/Dof-Atlas/actions/runs/39048421383/artifacts/12107090329) : `focused.json`, `capability_evidence.json`, `agent_plan.json` (associés au SHA `097425e4b081b586231a3e9dd32db292422221d5`).

Limites persistantes : `TESTED` au titre des 36 témoins n'est pas `FULL_CERTIFIED` ; cela ne prouve pas le comportement d'un EXE installé. L'export JSON est consommable par un agent classique et reproduit automatiquement par la CI, mais l'intégration d'un agent connecté extérieur au workflow n'est pas attestée.

## P3-12 — garde indépendant de comparaison des quatre régressions

Un nouveau consommateur **en lecture seule**, `doctor_ui_ci regression-watch`, compare deux **sessions UI réelles et hash-vérifiées** : état sain avant correction, candidat à un autre SHA. Le rapport `doctor_ui_regression_watch/v1` contient pour chaque parcours les assertions de base/candidat, les absences et un verdict distinct, sans modifier ni remplacer les correctifs de la #201 ou les générateurs de preuves de la #216.

Assertions contractuelles requises :
- Clic sur une fiche Succès : `achievement-detail/click-opens-detail`.
- Guide vers le détail Quêtes : `guide-quests/guide_complet-quest-0` ET `guide-quests/dofus_sylvestre-quest-0`.
- Premier chargement paresseux du détail Succès : `achievement-detail/first-open-lazy`.
- Rendu/captures : géométrie du Guide Succès et de Lanyel en largeur 1200 et 960 (`guides-success/geometry-1-{1200,960}`, `guides-lanyel/geometry-1-{1200,960}`) **et** deux géométries du détail Succès (`achievement-detail/geometry-{1200,960}`).

Les assertions `achievement-detail/...` sont des **contrats attendus**, **pas** des contrôles actuellement prouvés ; leur production réelle et leurs oracles relèvent de la #216, tandis que les correctifs produit relèvent de la #201. Une campagne `validator-smoke` verte, une capture sans assertion rattachée ou la seule réussite `guides-success` ne peuvent valider P3-12.

Après livraison et extraction des sessions de baseline/candidat :

```bash
python -m tools.atlas_doctor_lib.doctor_ui_ci regression-watch \
  --baseline-sha SHA_AVANT --baseline-session CHEMIN_SESSION_AVANT \
  --candidate-sha SHA_APRES --candidate-session CHEMIN_SESSION_APRES \
  --watch-output artifacts/doctor_ui/regression_watch.json
```

Des sessions supplémentaires de la même version peuvent être déclarées en répétant `--baseline-session` ou `--candidate-session`. Les dossiers doivent inclure leur `manifest.json`, `ui_verdict.json`, `actions.json`, `request.json`, `worker.log` et les PNG d'assertion. La lecture revalide les empreintes, la cohérence du SHA, les IDs exacts, les verdicts, les doublons et le rattachement explicite des captures. Chaque PNG utilisé comme preuve est aussi vérifié comme image structurée (signature, dimensions bornées, chunks CRC et IEND), pas seulement par son nom ou son empreinte. Une preuve manquante → `NOT_COVERED` ; une incohérence/altération → `BLOCKED` ; une assertion précédemment PASS devenue FAIL → `REGRESSION_REVIEW` ; uniquement les quatre parcours observés PASS aux deux SHAs → `NO_REGRESSION_OBSERVED`. Le CLI sort non-zéro tant que les quatre parcours ne sont pas couverts et stables.

**À ne pas confondre :** une comparaison de sessions hors parcours installé n'est pas une certification produit et ne doit pas ouvrir le merge gate. Les preuves avant/après du détail Succès ne sont pas encore disponibles pour cette PR ; conserver `P3-12 = NOT_COVERED` tant qu'elles manquent.

## Blocage P3-12 rendu visible par la CI ciblée

Pour chaque PR outillage `tooling_only`, le job `Doctor / Focused CI Evidence` produit désormais `artifacts/doctor_ci/ui_regression_watch.json`. Tant que les sessions avant/après du détail Succès ne sont pas fournies, ce JSON porte **quatre statuts `NOT_COVERED`** (`achievement-click`, `guide-to-quests`, `achievement-first-open`, `render-and-capture`) ; il enregistre le SHA de base et le SHA courant, et indique `tests_executed=false` / `release_certified=false`. Ce n'est pas un échec de l'outillage : la CI vérifie que le rapport n'invente aucun PASS. Ce n'est **pas** non plus un feu vert pour fusionner les réparations UI ; il faudra fournir les sessions réelles de la #201 et les oracles de la #216, puis lancer `regression-watch` avec les deux révisions et des captures valides.
