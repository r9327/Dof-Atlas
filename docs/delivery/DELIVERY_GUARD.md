# Atlas Delivery Guard — contrat de livraison anti-oubli

**Objectif** : ne jamais confondre code fusionné, fonctionnalité réellement finie, validation
automatique et essai manuel. Complément d'Atlas Doctor, Graphify, Phase Certification,
de la politique de release et des tests Windows existants — aucun de ces contrôles
n'est désactivé ou affaibli.

## 1. Le contrat indépendant (issue GitHub)

Avant de commencer une PR, ouvrir **une issue source dédiée**. Sa description contient
un unique bloc JSON délimité comme suit :

<!-- ATLAS_DELIVERY_CONTRACT_START -->
{
  "schema_version": 1,
  "requirements": [
    {"id": "REQ-001", "description": "Behavior and result expected, measurably described", "kind": "code"},
    {"id": "REQ-002", "description": "Real DOFUS/Npcap multi-window acceptance", "kind": "manual"}
  ]
}
<!-- ATLAS_DELIVERY_CONTRACT_END -->

Les IDs (p. ex. REQ-001) sont stables. Les types reconnus sont code, docs, manual.
Inclure le parcours nominal, les erreurs/rollback, les tests de régression,
les migrations, l'interface et les validations Windows réelles s'ils concernent
le sujet. Une PR ne peut pas remplacer la portée de l'issue : le contrôle compare
tous les IDs de l'issue externe au rapport de la PR. Une modification ultérieure
des exigences source **nécessite une revue humaine explicite**; ce premier
contrôle n'est pas un registre cryptographiquement immuable d'historique.

Pour un lot technique volontairement partiel : documenter explicitement dans
l'issue les comportements finaux attendus et les reports autorisés. Enregistrer
chacun de ces reports dans une **issue ouverte et distincte**, avec son ID, son
responsable et son critère de résolution. Les reports de code ou de docs ne sont
acceptés que si l'exigence source contient déjà `"allow_deferral": true`.
Les exigences manuelles restent reportables avec suivi ouvert. Pas de retrait silencieux.

## 2. Rapport par PR — SHA strict

Le template .github/pull_request_template.md fournit un second bloc JSON,
"ATLAS_DELIVERY_REPORT", dont les lignes correspondent une à une aux IDs source.
Il contient delivery_issue (numéro source), head_sha (40 caractères du vrai HEAD)
et requirements.

Pour une exigence code livrée :

    {
      "id": "REQ-001",
      "status": "DONE",
      "evidence_files": ["app/quelque_chose.py"],
      "test_files": ["tests/test_quelque_chose.py"]
    }

Le garde vérifie des chemins sûrs réellement présents dans le checkout du SHA exact,
au moins un fichier de preuve modifié dans le diff exact et un fichier de test
présent sous tests/test_*.py pour une exigence code. **Il ne prouve PAS que le
test a réussi ni que le comportement est correct** : Doctor, la CI ciblée et
Phase Certification demeurent responsables de l'exécution et de la provenance.

Pour une exigence manuelle non validée ou un report explicitement autorisé :

    {
      "id": "REQ-002",
      "status": "DEFERRED",
      "followup_issue": 265,
      "safety_evidence": "La fonction reste non certifiée et n'est pas activée en Stable en attente de DOFUS réel."
    }

Le garde exige une issue de suivi **ouverte** dans le même dépôt, qui mentionne
l'ID exact. Chaque report reste visible dans un résultat TRACKED_PARTIAL.
Un report **n'est jamais une certification**. Le texte de confinement est une
déclaration à inspecter en revue : le script ne prétend pas prouver l'absence
de chemin d'exécution en production. Une validation manuelle ne peut pas se
déclarer DONE uniquement par un agent : elle doit être traitée via le
parcours humain documenté dans l'issue.

En attendant le canal Atlas Bêta (#265), utiliser un scénario manuel avec :
PR, SHA, Windows, version DOFUS, étapes, résultat, date, opérateur, logs expurgés.
Un nouveau SHA invalide l'attestation précédente.

## 3. États et refus

- DONE : seules les exigences code/docs avec preuves de fichiers et, pour code,
  référence à un test existant. Cela signifie **accounted**, jamais CERTIFIED.
- DEFERRED : seulement avec issue ouverte, même ID, justification de confinement;
  l'automate imprime TRACKED_PARTIAL.
- PENDING, BLOCKED, SKIPPED, NOT_RUN, PASS auto-proclamé, ID manquant, fichier absent,
  SHA obsolète, issue close ou contrat inaccessible : **bloque** le contrôle.
- Les exigences manuelles ne passent **jamais** à DONE par ce contrôle; elles
  restent suivies et requièrent la confirmation humaine indépendante avant tout
  statut de fonctionnalité validée.
- Jamais de changement silencieux du contrat de l'issue. Review explicite des
  révisions d'issue, du scope et de l'issue de report.

## 4. Workflow de sécurité

.github/workflows/delivery-guard.yml est indépendant et purement read-only :
- déclenché sur ouverture, réouverture, édition du corps de PR, nouveau commit,
  passage Ready et retour Draft, sur main ;
- checkout de la BASE **de confiance** pour le validateur et ses tests;
- checkout du HEAD exact de la PR comme **données à inspecter**, jamais
  pour exécuter un validateur modifié par l'auteur avec GH_TOKEN;
- vérification du HEAD du checkout, du diff base/head, de l'issue source et des
  issues de report via l'API GitHub read-only;
- aucune permission write, aucun token persistant dans le checkout;
- produit un JSON traçable avec explicitement
  full_certified=false, manual_certified=false, merge_authorized=false.

Le statut de job à rendre obligatoire est :
**Atlas Delivery Guard / Delivery Contract**.

Important : GitHub utilise les workflows de la branche BASE sur l'événement
pull_request ; le nouveau workflow ne sera utilisable comme porte habituelle
qu'une fois cette PR revue et fusionnée. Le ruleset distant actuel protège
main avec Public PR / Safe Validation et Certification Policy / Merge Gate.
La **configuration admin** de son nouveau required status check est
obligatoire et suivie par **#266**. Ce fichier ne modifie pas le ruleset.

Une issue non modifiable cryptographiquement, une protection des edits d'issue
et une attestation humaine signée ne sont PAS implémentées par cette v1.
L'approbation de modifications au contrat initial reste un devoir de revue.

## 5. Mise en service et critères de recette

1. Revue du code et des tests adversariaux tests/test_ci_delivery_guard.py.
2. CI Doctor/Phase Certification sur le SHA exact, plus tests ciblés du garde.
3. Fusion après revue; ACTIVER le check dans Settings > Rules > Rulesets
   sans supprimer les deux contrôles existants (#266).
4. Créer une PR d'essai avec un contrat source valide : retirer un ID =>
   échec; changer le commit sans actualiser head_sha => échec; supprimer le
   test de preuve => échec; report sans issue ouverte => échec; exigences
   comptabilisées => ACCOUNTED ou TRACKED_PARTIAL (jamais CERTIFIED).
5. Vérifier sur une vraie PR que personne ne transforme TRACKED_PARTIAL en
   annonce de fonctionnalité terminée. Les versions Stable dépendent toujours
   des gates Phase et release indépendantes.
6. Assurer la migration des PR déjà ouvertes, notamment Dependabot, avec
   des issues et reports adaptés plutôt que bypass implicites.

## 6. Futur Atlas Bêta/Testeur

L'installateur Bêta, les deltas sécurisés, la séparation Stable/Bêta, le
rollback, les scénarios assistés, les diagnostics consentis/expurgés et le
verdict utilisateur Windows/DOFUS au SHA exact sont **hors de cette PR v1**.
Ils sont décrits et suivis dans **#265**. Il serait faux d'affirmer qu'un
testeur Windows Bêta existe déjà ou que ces tests ont été exécutés.

Un contrôle de contrat ne trouve pas automatiquement tous les bugs cachés.
Son rôle est d'empêcher la disparition **silencieuse** d'engagements connus.
