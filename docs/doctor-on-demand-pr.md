# Doctor / Graphify à la demande sur une PR

Issue de livraison : [#368](https://github.com/r9327/Dof-Atlas/issues/368).

## Deux environnements, une seule source de vérité

- **Checkout local Windows :** utiliser les commandes canoniques Doctor et
  Graphify documentées dans [AI_ENTRYPOINT.md](../AI_ENTRYPOINT.md) et
  [GRAPHIFY.md](../GRAPHIFY.md). Les tests locaux sont prioritaires pendant le
  développement : pas de nouvelle dépendance pour l'application Atlas.
- **Agent limité à GitHub :** depuis le commentaire d'une PR **ouverte**
  (Draft compris), un collaborateur du dépôt peut demander un diagnostic
  distant sans passer la PR en Ready :

  ```text
  /atlas doctor
  /atlas graphify
  /atlas doctor <SHA HEAD de 40 caractères>
  /atlas graphify <SHA HEAD de 40 caractères>
  ```

  Le SHA explicite est recommandé pour éviter d'analyser une nouvelle révision
  par erreur. Sans SHA, le serveur GitHub résout le HEAD au moment de la demande,
  et l'inscrit dans chaque rapport. Les commentaires doivent contenir uniquement
  la commande, sans Markdown ni autres arguments.

- **Alternative manuelle :** GitHub → Actions →
  **Atlas Doctor / Graphify — On Demand** → Run workflow, en indiquant
  `pr_number`, `mode` et facultativement `expected_sha`.

**Prérequis :** le workflow doit être fusionné sur la branche par défaut pour
que GitHub traite les événements `issue_comment`. Une connexion API GitHub
capable de commenter mais dont l'identité n'a pas le rôle
`OWNER/MEMBER/COLLABORATOR` ne peut pas déclencher l'exécution.
L'action manuelle exige les permissions GitHub appropriées. L'accès à l'API
ne fournit pas à lui seul un interpréteur Python ou un poste Windows.

## Résultats accessibles aux agents

1. Ouvrir le run **Atlas Doctor / Graphify — On Demand** correspondant à la
   demande (les runs `issue_comment` peuvent montrer le SHA de `main`
   comme SHA d'événement : ce **n'est pas** le SHA diagnostiqué).
2. Vérifier l'artefact
   `atlas-on-demand-pr-<PR>-<doctor|graphify>-<SHA>` sous ce run ;
   la conservation est de **7 jours**.
3. Pour Doctor, lire `artifacts/doctor_on_demand/doctor.json` :
   `candidate_sha`, `base_sha`, `status`, `execution.status`,
   `executed_modules`. `FULL_REQUIRED_NOT_DISPATCHED` ne signifie pas PASS.
4. Pour Graphify, lire `graphify-out/graph.json`, `GRAPH_REPORT.md`,
   `graph.html` et `artifacts/doctor_on_demand/graph_doctor.json`.
5. Vérifier que le job **freshness** de ce même run a réussi : il contrôle
   le HEAD actuel sur un runner séparé, après le diagnostic, sans exposer
   de jeton aux scripts du code de PR.
6. Croiser l'artefact avec le HEAD **actuel** de la PR. Si le HEAD a changé,
   si le SHA du graphe diffère, si la commande échoue, ou si l'artefact manque
   ou a expiré : déclarer `STALE`, `FAIL` ou `UNAVAILABLE`, jamais PASS.
   Ne pas faire de refactor structurel sans Graphify exact-SHA disponible.

API GitHub : lister les exécutions du workflow, puis les artefacts du run
candidat. Les connecteurs qui ne savent pas déclencher `workflow_dispatch`
peuvent utiliser les commentaires de PR **uniquement si leur identité est
autorisée**. Ne pas contourner cette restriction.

## Limites et coût

- **Doctor** appelle le planificateur canonique
  `tools.doctor_certification --run` : seulement les modules ciblés
  explicitement jugés sûrs. Une FULL nécessaire n'est **jamais** déclenchée.
- **Graphify** lance, explicitement, `tools.atlas_doctor graph --rebuild`
  avec la version AST épinglée `graphifyy==0.9.72` ; aucune IA, API ou
  clé payante. Ce calcul est volontairement à la demande, pas à chaque push.
- Exécution sur **Ubuntu / Python 3.13** ; ce n'est ni un test Windows desktop
  ni un essai avec 2 à 8 comptes DOFUS Unity. Ces preuves restent NOT_RUN.
- Refus des forks, des PR fermées, des commentaires non autorisés, des modes
  inconnus et des SHA périmés. Checkout par SHA avec
  `persist-credentials: false` et permissions GitHub en lecture seule.
- Le workflow est un **diagnostic de développement**, jamais une nouvelle
  preuve `CERTIFIED` ni une dispense de la
  [Phase Certification](../PHASE_CERTIFICATION.md).

## Validation

Contrats ciblés : `python -m unittest discover -s tests
-p 'test_doctor_pr_on_demand.py' -v`. Pour la recette end-to-end,
après fusion du workflow sur la branche par défaut, demander les deux modes
sur une PR Draft et vérifier les SHA, artefacts, états `NOT_RUN` et refus
de l'ancienne révision. Une recette qui n'a pas été effectivement exécutée
reste `NOT_RUN`.

## Tests ciblés d'un lot récent, même si la PR entière demande FULL

Sur une PR Draft longue, `/atlas doctor` conserve le diagnostic **global**
(`FULL_REQUIRED` signifie qu'aucun test automatique ciblé n'est déclaré
suffisant pour toute la PR). Pour tester uniquement le lot récent, utiliser :

```text
/atlas doctor-lot <SHA du commit AVANT le lot> <SHA HEAD exact de la PR>
```

Exemple pour la PR #325 : le SHA avant lot peut être son ancien HEAD
`c2f71285fc6f9b26dfabdcd396c7de4dfa9d23e9`. Toujours reprendre le
HEAD actuel, et non un exemple périmé. Via `workflow_dispatch`, sélectionner
`doctor-lot` avec `expected_sha` et `lot_base_sha`.

Le résolveur approuvé vérifie les rôles GitHub, le dépôt d'origine, la PR
ouverte et le HEAD exact. Le sélecteur Doctor-lot est extrait **séparément de
la branche de confiance `main`** : il fonctionne donc aussi sur les anciennes
PR Draft qui ne contiennent pas encore son module Python, sans importer un
sélecteur fourni par la PR sous test. Les tests applicatifs s'exécutent
toujours dans le checkout exact du candidat, sans jeton. Le routeur de lot :

- exige que la base soit un ancêtre réel du HEAD, avec **1 à 20 commits**,
  **1 à 16 fichiers**, sans suppression/renommage ;
- sélectionne uniquement des modules de tests existants liés aux sources
  modifiées ; refuse les fichiers de politique/CI ou non reconnus ; affiche
  `REVIEW` si un code n'a pas de tests directs, sans prétendre le couvrir ;
- utilise l'exécuteur ciblé canonique `ci_scope_gate._run_scoped_modules`
  et fournit `doctor_lot.json`, avec modules réellement lancés, code retour,
  SHA exact et lacunes éventuelles ;
- recalcule **séparément** le classement de la PR entière depuis son SHA
  de base. Le classement `FULL_REQUIRED`, les contrôles de fusion et Phase
  Certification ne sont jamais modifiés, allégés ni remplacés.

Un `PASS` de tests de lot n'est **ni** une validation de l'interface en jeu,
**ni** une preuve de fonctionnement des comptes DOFUS Unity, ni une
certification complète. Pour valider les clients 1/2/4/6/8 sur un vrai PC,
suivre l'issue #322. Le job `freshness` recontrôle le HEAD après les tests.
