# Dofus Atlas — Phase Certification

Ce document définit la règle de clôture des phases et gros lots de Dofus Atlas.

## Principe

Une PR verte, un build qui compile ou une validation publique partielle ne suffisent jamais à déclarer une phase terminée.

Les états officiels sont :

- `CODE_DONE` : le code demandé est implémenté et le diff a été relu ;
- `VALIDATED` : les tests ciblés du comportement modifié ont réellement été exécutés et sont `PASS` ;
- `CERTIFIED` : la validation complète correspondant au périmètre de la phase a réussi sur le SHA exact à certifier.

Seul l'état `CERTIFIED` autorise les formulations « phase terminée », « phase validée définitivement », « 100 % terminée » ou équivalent.

## Source machine de vérité

La politique de validation est définie par `tools/atlas_integrity_policy.json` et exécutée par `tools.atlas_integrity`.

La certification application utilise au minimum le mode `FULL`.

Le mode `FULL` doit notamment exécuter :

- méta-intégrité et syntaxe ;
- architecture ;
- identité personnage ;
- persistence ;
- startup et lazy loading ;
- cycle de vie async / Qt ;
- budgets de ressources ;
- intégrité des tests ;
- intégrité CI ;
- golden flows ;
- tests modifiés du diff (`DIFF_TARGETS`) ;
- découverte complète des tests (`FULL_SUITE`) ;
- intégrité Guide / données (`DATA_INTEGRITY`).

Pour le périmètre `APPLICATION`, `DATA_INTEGRITY` reste toujours exécuté et rapporté, mais n'est pas un groupe bloquant tant que le Guide canonique est explicitement dans un état de construction (`BUILDING`). Les dettes Guide ne sont jamais transformées en `PASS` : elles restent visibles comme diagnostic et doivent être fermées par la certification Guide dédiée.

Une validation obligatoire du périmètre à certifier qui est `BLOCKED`, `NOT_RUN`, `FAILED` ou absente interdit la certification.

`APPLICATION CERTIFIED` ne signifie jamais `GUIDE CERTIFIED`. Une phase qui modifie ou prétend clôturer le Guide Ultime doit obtenir, en plus de la certification application, le `PASS` du workflow Guide dédié exécutant `tools/run_guide_ultime_ci.ps1` en mode strict.

## CI

`Public PR / Safe Validation` est un garde-fou de PR. Même entièrement vert, il ne constitue pas une certification de phase.

La certification application est portée par `Phase Certification / Full Validation` (`.github/workflows/phase-certification.yml`). Elle peut être lancée manuellement, mais elle est aussi déclenchée automatiquement à chaque mise à jour d'une PR interne dont le titre commence par `Phase ` et dont la branche source appartient au dépôt lui-même.

Pour une PR de phase, le workflow checkout explicitement le SHA de tête de la PR et utilise le SHA de base de la PR pour classifier le diff. La certification suit donc le candidat exact ; une nouvelle modification rend l'ancien résultat obsolète et déclenche une nouvelle validation.

Le workflow ne délivre `PHASE CERTIFICATION: PASS` que si :

1. le checkout correspond au SHA à certifier ;
2. les fixtures LFS requises sont matérialisées ;
3. le catalogue Dofus local est matérialisé ;
4. `tools.atlas_integrity full` retourne `PASS` pour le périmètre `APPLICATION` ;
5. aucune validation obligatoire de ce périmètre n'est `BLOCKED` ou `NOT_RUN`.

Le SHA certifié doit apparaître dans le résumé GitHub Actions.

Le Guide Ultime conserve son workflow strict séparé. Un échec `GUIDE_PREREQUISITE_DATA`, `GUIDE_FINAL_COVERAGE` ou toute autre dette Guide reste un échec de certification Guide et ne doit jamais être masqué, supprimé ou présenté comme résolu par la certification application.

## Règles de travail

Pour chaque micro-lot, les tests ciblés restent obligatoires avant de passer au lot suivant. La certification de phase ne remplace pas cette validation ciblée ; elle clôt seulement l'ensemble.

Un test couvrant un comportement utile ne doit pas être supprimé uniquement parce que l'ancien module qui le portait disparaît. Le contrat doit être migré vers le nouveau chemin canonique ou explicitement démontré comme obsolète.

Les shims de compatibilité peuvent subsister lorsqu'ils sont réellement nécessaires, mais le code moderne interne doit utiliser directement le chemin canonique dès que la migration est possible.

## Rapport final

Tout rapport de clôture doit distinguer explicitement :

- `PASS` : exécuté et réussi ;
- `FAIL` : exécuté et échoué ;
- `NOT RUN` : non exécuté ;
- `BLOCKED` : exécution empêchée ou précondition non satisfaite ;
- `MEASURED_ONLY_FAILED` : audit exécuté et rouge, conservé comme diagnostic hors périmètre bloquant de la certification en cours.

Ne jamais transformer `NOT RUN`, `BLOCKED` ou `MEASURED_ONLY_FAILED` en validation implicite.

Si `Phase Certification / Full Validation` n'est pas `PASS` sur le SHA exact, la phase application reste ouverte. Si la phase porte sur le Guide, le workflow Guide strict doit également être `PASS` sur le SHA correspondant avant toute déclaration de clôture du Guide.
