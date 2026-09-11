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

Le mode `FULL` couvre notamment :

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
- découverte complète des tests (`FULL_SUITE`).

Une validation application obligatoire `BLOCKED`, `NOT_RUN`, `FAILED` ou absente interdit la certification application.

## Certification Guide / données

`DATA_INTEGRITY` est une certification de domaine distincte. Elle reste bloquante pour toute phase dont l'objectif est de certifier ou modifier le contenu Guide / données, mais elle ne bloque pas une phase purement architecture, persistence, UI ou simplification qui ne prétend pas certifier ce contenu.

Le mode `DEEP` conserve `DATA_INTEGRITY` et le runner Guide canonique. Une phase Guide / données ne peut donc être déclarée `CERTIFIED` qu'avec, sur le SHA candidat applicable :

1. la certification application `FULL` en `PASS` ;
2. la certification Guide / données (`DATA_INTEGRITY`) en `PASS`.

Un blocage Guide connu n'est jamais transformé en succès : il reste rouge dans sa certification de domaine jusqu'à sa résolution. Cette séparation évite uniquement qu'une dette Guide planifiée pour une phase ultérieure empêche de certifier un lot d'architecture sans rapport avec elle.

## CI

`Public PR / Safe Validation` est un garde-fou de PR. Même entièrement vert, il ne constitue pas une certification de phase.

La certification application est portée par `Phase Certification / Full Validation` (`.github/workflows/phase-certification.yml`). Elle peut être lancée manuellement, mais elle est aussi déclenchée automatiquement à chaque mise à jour d'une PR interne dont le titre commence par `Phase ` et dont la branche source appartient au dépôt lui-même.

Pour une PR de phase, le workflow checkout explicitement le SHA de tête de la PR et utilise le SHA de base de la PR pour classifier le diff. La certification suit donc le candidat exact ; une nouvelle modification rend l'ancien résultat obsolète et déclenche une nouvelle validation.

Le workflow ne délivre `PHASE CERTIFICATION: PASS` que si :

1. le checkout correspond au SHA à certifier ;
2. les fixtures LFS requises sont matérialisées ;
3. le catalogue Dofus local est matérialisé ;
4. `tools.atlas_integrity full` retourne `PASS` ;
5. aucune validation application obligatoire n'est `BLOCKED` ou `NOT_RUN`.

Le SHA certifié doit apparaître dans le résumé GitHub Actions.

Pour une phase Guide / données, ce PASS application doit être complété par le PASS du contrôle `DATA_INTEGRITY` ; le PASS application seul ne suffit pas à certifier le domaine Guide.

## Règles de travail

Pour chaque micro-lot, les tests ciblés restent obligatoires avant de passer au lot suivant. La certification de phase ne remplace pas cette validation ciblée ; elle clôt seulement l'ensemble.

Un test couvrant un comportement utile ne doit pas être supprimé uniquement parce que l'ancien module qui le portait disparaît. Le contrat doit être migré vers le nouveau chemin canonique ou explicitement démontré comme obsolète.

Les shims de compatibilité peuvent subsister lorsqu'ils sont réellement nécessaires, mais le code moderne interne doit utiliser directement le chemin canonique dès que la migration est possible.

## Rapport final

Tout rapport de clôture doit distinguer explicitement :

- `PASS` : exécuté et réussi ;
- `FAIL` : exécuté et échoué ;
- `NOT RUN` : non exécuté ;
- `BLOCKED` : exécution empêchée ou précondition non satisfaite.

Ne jamais transformer `NOT RUN` ou `BLOCKED` en validation implicite.

Si `Phase Certification / Full Validation` n'est pas `PASS` sur le SHA exact, la phase application reste ouverte. Si la phase porte sur Guide / données, elle reste également ouverte tant que `DATA_INTEGRITY` n'est pas `PASS`.
