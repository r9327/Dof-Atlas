# Dofus Atlas — Phase Certification

Ce document définit la règle de clôture des phases et gros lots de Dofus Atlas.

## Principe

Une PR verte, un build qui compile ou une validation publique partielle ne suffisent jamais à déclarer une phase terminée.

Les états officiels sont :

- `CODE_DONE` : le code demandé est implémenté et le diff a été relu ;
- `VALIDATED` : les tests ciblés du comportement modifié ont réellement été exécutés et sont `PASS` ;
- `CERTIFIED` : la validation complète correspondant au périmètre réel de la phase a réussi sur le SHA exact à certifier.

Seul l'état `CERTIFIED` autorise les formulations « phase terminée », « phase validée définitivement », « 100 % terminée » ou équivalent.

## Calendrier des certifications automatiques

- Une **PR Phase en brouillon** est en développement : Doctor Adaptive
  Certification, Doctor FAST, Graphify et les contrôles ciblés peuvent
  donner du feedback, mais la FULL Phase n'est pas lancée automatiquement
  à chaque commit du brouillon.
- Le passage à **ready for review** (ou une PR Phase déjà non-brouillon)
  déclenche la certification FULL de la Phase, sur le SHA candidat exact.
  Tout nouveau commit sur une PR Phase non-brouillon relance cette FULL.
- Un **push sur main** et le déclenchement manuel explicite conservent
  leur FULL historique. La validation finale d'une phase n'est **jamais**
  remplacée par un passeport Doctor ciblé.
- Un brouillon ne peut pas être déclaré `CERTIFIED` uniquement parce que
  le nouveau workflow adaptatif est vert. Une sortie de brouillon, puis
  un rapport FULL PASS sur le bon SHA, restent nécessaires.

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

Une phase ne doit pas être forcée à terminer une feature explicitement encore en construction si cette dette existait déjà, à l'identique, sur une ancre de référence antérieure et si ni les phases intermédiaires ni la phase courante ne touchent les sources responsables de cette dette.

Cette exception est volontairement très étroite. Pour Phase 2, le Guide Ultime est encore déclaré `BUILDING` et deux audits Guide stricts étaient déjà rouges sur le `main` de Phase 1. Leur état de référence est figé dans `tools/guide_phase2_baseline.json`. Ce SHA reste une ancre immuable : les phases suivantes ne le remplacent pas par leur propre base uniquement pour rendre la CI verte.

Le verdict `PASS_BASELINE_NON_REGRESSION` n'est accepté que si toutes les conditions suivantes sont vraies :

1. le SHA enregistré dans le baseline Phase 2 est un ancêtre du SHA de base résolu de la phase courante ;
2. aucun fichier propriétaire de la dette Guide n'a changé entre cette ancre figée et la base de la phase courante, hors exceptions explicitement autorisées ;
3. tous les groupes `FULL` autres que `DATA_INTEGRITY`, notamment `FULL_SUITE`, sont `PASS` ;
4. les seuls blockers restants sont exactement des blockers Guide explicitement autorisés par le baseline ;
5. le manifeste Guide est toujours `BUILDING` ;
6. les empreintes des erreurs de prérequis et de couverture finale sont inchangées ;
7. aucun fichier propriétaire de ces audits n'a changé dans le diff de la phase courante ;
8. les rares fichiers autorisés à changer sont explicitement listés dans le baseline et ne portent pas les dettes concernées.

Toute dérive de contenu, nouveau blocker, base qui ne descend plus de l'ancre figée, changement d'un fichier protégé dans l'historique hérité ou dans le diff courant, ou modification du périmètre de couverture fait repasser la certification à `NOT CERTIFIED`.

`PASS_BASELINE_NON_REGRESSION` décrit historiquement la non-régression de cette
dette ; il ne transforme jamais la dette Guide en `PASS` global et ne signifie
jamais `GUIDE CERTIFIED`. Dès que le chantier Guide est déclaré `CERTIFIED`, ce
baseline reste une trace de transition mais ne peut plus autoriser un verdict
final : un FULL `BLOCKED` ou un `GUIDE_NOT_CERTIFIED` fait échouer la
certification.

## CI

`Public PR / Safe Validation` est un garde-fou de PR. Même entièrement vert, il ne constitue pas une certification de phase.

La certification est portée par `Phase Certification / Full Validation` (`.github/workflows/phase-certification.yml`). Elle peut être lancée manuellement, mais elle est aussi déclenchée automatiquement à chaque mise à jour d'une PR interne dont le titre commence par `Phase ` et dont la branche source appartient au dépôt lui-même.

Pour une PR de phase, le workflow checkout explicitement le SHA de tête de la PR et utilise le SHA de base de la PR pour classifier le diff courant. Lorsqu'une dette figée est transportée par non-régression, le validateur contrôle en plus la descendance depuis l'ancre du baseline et les changements de fichiers protégés entre cette ancre et la base courante. La certification suit donc le candidat exact ; une nouvelle modification rend l'ancien résultat obsolète et déclenche une nouvelle validation.

Le workflow ne délivre `PHASE CERTIFICATION: PASS` que si :

1. le checkout correspond au SHA à certifier ;
2. les fixtures LFS requises sont matérialisées ;
3. le catalogue Dofus local est matérialisé ;
4. `tools.atlas_integrity full` a réellement exécuté les groupes requis ;
5. le verdict strict est `PASS` et le Guide est `GUIDE_CERTIFIED` ; `PASS_BASELINE_NON_REGRESSION` reste diagnostique et ne ferme pas le chantier Guide ;
6. le validateur `tools.phase_certification_verdict` accepte les preuves et le SHA exact.

Pour le Guide, le verdict distinct `GUIDE_CERTIFIED` n'est émis que lorsque le
manifeste est `CERTIFIED`, que les catalogues Quêtes et Succès sont réellement
chargés et non vides, que les audits prérequis et actions ne contiennent aucune
erreur dure, que la couverture retenue ne contient aucun succès partiel ou
absent, et que tous les contrats vérifiés sont couverts. Un catalogue absent,
un rapport incomplet ou un verdict FULL `BLOCKED` produit
`GUIDE_NOT_CERTIFIED` et fait échouer la certification.

Le SHA certifié et le type de verdict doivent apparaître dans le résumé GitHub Actions.

## Règles de travail

Pour chaque micro-lot, les tests ciblés restent obligatoires avant de passer au lot suivant. La certification de phase ne remplace pas cette validation ciblée ; elle clôt seulement l'ensemble.

Un test couvrant un comportement utile ne doit pas être supprimé uniquement parce que l'ancien module qui le portait disparaît. Le contrat doit être migré vers le nouveau chemin canonique ou explicitement démontré comme obsolète.

Les shims de compatibilité peuvent subsister lorsqu'ils sont réellement nécessaires, mais le code moderne interne doit utiliser directement le chemin canonique dès que la migration est possible.

## Verrou cumulatif Phase 7D après Phase 7E

L'audit cumulatif Phase 1 → 7D reste une preuve historique de l'état qu'il a certifié. Il ne suffit pas, à lui seul, à fermer définitivement les Phases 1 → 7 après des changements ultérieurs de Phase 7E.

Avant tout démarrage de la Phase 8, après le merge du dernier correctif de Phase 7E, un rejeu cumulatif Phase 1 → 7E est obligatoire sur le SHA exact de `main`.

Ce rejeu doit :

1. vérifier les contrats historiques des Phases 1 → 7D ainsi que tous les contrats ajoutés en 7E ;
2. couvrir les tests, données, UI, Guide, performances et garde-fous applicables au périmètre cumulé ;
3. exécuter `tools.atlas_integrity full` et obtenir `Phase Certification / Full Validation = PASS` sur ce même SHA exact ;
4. ne laisser aucun `FAIL`, `NOT RUN` ou `BLOCKED` obligatoire, ni aucun skip qui masque un contrôle requis ;
5. conserver un worktree propre pour la preuve locale de clôture lorsqu'une exécution locale fait partie de l'audit ;
6. considérer toute régression d'une phase antérieure comme bloquante pour la clôture cumulative et pour le démarrage de la Phase 8.

Une certification obtenue avant le dernier merge 7E ne satisfait pas ce verrou. Les Phases 1 → 7 ne peuvent être déclarées « 100 % terminées » qu'après ce rejeu cumulatif `PASS` sur le `main` final.

## Phase 8 — état initial

Statut : `STARTED` le 3 octobre 2026, après certification cumulative des Phases 1 → 7 sur le SHA exact de `main` `8f6357ce0e731d98ad700138d795533ae21ea4fa`.

Baseline initiale :

- Atlas Integrity FULL : `PASS`, 1 906 tests dans la suite globale, 0 erreur et 0 échec ;
- Doctor HARD : `REVIEW` uniquement pour les limites d'ownership et d'impact borné déclarées, avec son autorité FULL interne à `PASS` ;
- Graphify 0.9.72 : `PASS`, 10 282 nœuds, 30 715 liens, aucun cycle d'import signalé dans le rapport Graphify ;
- budgets de ressources : `PASS` ; mesures Doctor conservées sous `.ai/runtime/atlas_doctor/`, `artifacts/doctor/perf/` et `graphify-out/`, tous emplacements canoniques ignorés par Git ;
- CI post-merge : `Phase Certification / Full Validation`, `Full Application Suite`, `Graphify / AST Code Map`, validation FAST et signature à `PASS` sur ce même SHA.

Premier chantier repris de la roadmap Phase 8 existante : `DA-LOG-015` — supprimer l'initialisation du logging par effet de bord lors de l'import de `app.constants`, puis installer explicitement le journal au bootstrap de l'application. Ce chantier doit préserver la rotation, l'idempotence et la visibilité des erreurs filesystem.

## Rapport final

Tout rapport de clôture doit distinguer explicitement :

- `PASS` : exécuté et réussi ;
- `FAIL` : exécuté et échoué ;
- `NOT RUN` : non exécuté ;
- `BLOCKED` : exécution empêchée ou précondition non satisfaite ;
- `PASS_BASELINE_NON_REGRESSION` : phase certifiée sans régression d'une dette préexistante, figée et hors périmètre de la phase ; cette dette reste ouverte.

Ne jamais transformer `NOT RUN`, `BLOCKED` ou une dette non figée en validation implicite.

Si `Phase Certification / Full Validation` n'est pas `PASS` sur le SHA exact, la phase reste ouverte.
