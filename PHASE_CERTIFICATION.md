# Dofus Atlas — Phase Certification

Ce document définit la règle de clôture des phases et gros lots de Dofus Atlas.

## Principe

Une PR verte, un build qui compile ou une validation publique partielle ne suffisent jamais à déclarer une phase terminée.

Les états officiels sont :

- `CODE_DONE` : le code demandé est implémenté et le diff a été relu ;
- `VALIDATED` : les tests ciblés du comportement modifié ont réellement été exécutés et sont `PASS` ;
- `CERTIFIED` : la validation complète correspondant au périmètre réel de la phase a réussi sur le SHA exact à certifier.

Seul l'état `CERTIFIED` autorise les formulations « phase terminée », « phase validée définitivement », « 100 % terminée » ou équivalent.

## Source machine de vérité

La validation technique générale est définie par `tools/atlas_integrity_policy.json` et exécutée par `tools.atlas_integrity`.

La certification de phase utilise au minimum le mode `FULL`, qui doit notamment couvrir :

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

`FULL_SUITE` doit toujours être `PASS` pour certifier une phase. Aucun échec applicatif, architectural, identité, persistence, lifecycle, CI ou test modifié ne peut être masqué par une dette antérieure.

## Dette préexistante et non-régression

Une phase ne doit pas être forcée à terminer une feature explicitement encore en construction si cette dette existait déjà, à l'identique, sur son SHA de base et si la phase ne touche pas les sources responsables de cette dette.

Cette exception est volontairement très étroite. Pour Phase 2, le Guide Ultime est encore déclaré `BUILDING` et deux audits Guide stricts étaient déjà rouges sur le `main` de Phase 1. Leur état de référence est figé dans `tools/guide_phase2_baseline.json`.

Le verdict `PASS_BASELINE_NON_REGRESSION` n'est accepté que si toutes les conditions suivantes sont vraies :

1. le SHA de base résolu est exactement celui enregistré dans le baseline Phase 2 ;
2. tous les groupes `FULL` autres que `DATA_INTEGRITY`, notamment `FULL_SUITE`, sont `PASS` ;
3. les seuls blockers restants sont exactement des blockers Guide explicitement autorisés par le baseline ;
4. le manifeste Guide est toujours `BUILDING` ;
5. les empreintes des erreurs de prérequis et de couverture finale sont inchangées ;
6. aucun fichier propriétaire de ces audits (routes actives, providers, résolution de route, politique Succès, catalogue Quêtes ou audits concernés) n'a changé ;
7. les rares fichiers autorisés à changer sont explicitement listés dans le baseline et ne portent pas les dettes concernées.

Toute dérive de contenu, nouveau blocker, changement d'un fichier protégé, changement du SHA de base ou modification du périmètre de couverture fait repasser la certification à `NOT CERTIFIED`.

`PASS_BASELINE_NON_REGRESSION` certifie donc la phase contre toute régression de cette dette ; il ne transforme jamais la dette Guide en `PASS` global et ne signifie jamais `GUIDE CERTIFIED`. La future phase Guide devra supprimer ce baseline de transition en fermant réellement les audits Guide.

## CI

`Public PR / Safe Validation` est un garde-fou de PR. Même entièrement vert, il ne constitue pas une certification de phase.

La certification est portée par `Phase Certification / Full Validation` (`.github/workflows/phase-certification.yml`). Elle peut être lancée manuellement, mais elle est aussi déclenchée automatiquement à chaque mise à jour d'une PR interne dont le titre commence par `Phase ` et dont la branche source appartient au dépôt lui-même.

Pour une PR de phase, le workflow checkout explicitement le SHA de tête de la PR et utilise le SHA de base de la PR pour classifier le diff. La certification suit donc le candidat exact ; une nouvelle modification rend l'ancien résultat obsolète et déclenche une nouvelle validation.

Le workflow ne délivre `PHASE CERTIFICATION: PASS` que si :

1. le checkout correspond au SHA à certifier ;
2. les fixtures LFS requises sont matérialisées ;
3. le catalogue Dofus local est matérialisé ;
4. `tools.atlas_integrity full` a réellement exécuté les groupes requis ;
5. le verdict strict est `PASS`, ou le seul écart est accepté par le contrat `PASS_BASELINE_NON_REGRESSION` décrit ci-dessus ;
6. le validateur `tools.phase_certification_verdict` accepte les preuves et le SHA exact.

Le SHA certifié et le type de verdict doivent apparaître dans le résumé GitHub Actions.

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
- `PASS_BASELINE_NON_REGRESSION` : phase certifiée sans régression d'une dette préexistante, figée et hors périmètre de la phase ; cette dette reste ouverte.

Ne jamais transformer `NOT RUN`, `BLOCKED` ou une dette non figée en validation implicite.

Si `Phase Certification / Full Validation` n'est pas `PASS` sur le SHA exact, la phase reste ouverte.
