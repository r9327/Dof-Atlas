# Dofus Atlas — Phase Certification

Ce document définit la règle de clôture des phases et gros lots de Dofus Atlas.

## Principe

Une PR verte, un build qui compile ou une validation publique partielle ne suffisent jamais à déclarer une phase terminée.

Les états officiels sont :

- `CODE_DONE` : le code demandé est implémenté et le diff a été relu ;
- `VALIDATED` : les tests ciblés du comportement modifié ont réellement été exécutés et sont `PASS` ;
- `CERTIFIED` : la validation complète correspondant au périmètre réel de la phase a réussi sur le SHA exact à certifier.

Seul l'état `CERTIFIED` autorise les formulations « phase terminée », « phase validée définitivement », « 100 % terminée » ou équivalent.

## Doctor en premier : orchestration automatique

`Doctor / CI Plan` est le premier job de chaque PR et push sur `main`.
Le workflow conserve son nom historique `Phase Certification` et son chemin
`phase-certification.yml` pour préserver les attestations GitHub et les chaînes
de publication existantes. Il orchestre désormais la CI entière.

Doctor compare le SHA de base au SHA candidat exact, réutilise la politique
adaptative canonique et les consommateurs UI, puis appelle les validations
nécessaires. Le titre et le statut brouillon de la PR ne décident plus de la
validation : un changement critique ou incertain exige FULL, même en brouillon.
Un diff éligible exécute tous les tests ciblés canoniques ; les documents
ordinaires seuls conservent les contrôles PR et métadonnées sans suite lourde.
Les documents de politique seuls ne bénéficient pas de cette exclusion.

La FULL ne signifie pas rejouer tous les spécialistes : sur un périmètre connu,
Doctor conserve la FULL canonique et les spécialistes des consommateurs touchés.
Les suppressions incertaines, les modifications de l'exécuteur de certification
et les périmètres inconnus conservent le repli large. Les fichiers CI connus
sélectionnent les contrats CI ciblés et le smoke réel du validateur UI, sans
FULL applicative ; ils ne sont pas assimilés à un changement des écrans Guides/Quêtes. Un mélange avec une
modification UI conserve tous les scénarios des consommateurs concernés.

Les anciens filtres de chemins spécialisés résident dans
`tools/atlas_doctor_lib/ci_routes.json`. Les workflows appelés n'ont plus de
`pull_request` ou `push` indépendant. Les diagnostics manuels et les chaînes
post-validation de publication restent explicites ; Doctor ne publie rien
sur une PR. `Scoped PR Feedback` reste un diagnostic manuel, son exécution
ciblée automatique étant déjà portée par le gate Phase canonique.

Les changements limités aux documents ordinaires ou aux propriétaires CI connus
produisent une preuve hôte `Doctor / Focused CI Evidence`. Le diff Git exact
est revérifié sans Qt ; pour le tooling, tous les contrats CI du registre
`ci_tooling_scope.py` sont réellement exécutés. La FULL reste non exécutée.
La liste est explicite : aucun fichier applicatif, dépendance, ruleset ou outil
inconnu n'est admis. Une suppression de code impose FULL ; seule la suppression
du workflow public remplacé est prévue. Le JSON d'intégrité n'est admis que
pour ajouter des modules CI testés, sans retirer de tests ni modifier la politique.
Un mélange avec un changement applicatif réutilise le gate Phase canonique.
Après fusion, la CI applicative accepte cette preuve comme validation ciblée,
jamais comme FULL. La distribution
exige une vraie preuve FULL avant tout téléchargement ou préparation de publication ;
un résultat SCOPED ou documentation seule ne déclenche pas de release.

Une analyse absente ou un mauvais SHA bloque le contrôle PR requis. Une
incertitude de périmètre ou une suppression non prévue impose FULL ; une sélection
UI ambiguë exécute tous les scénarios UI enregistrés en plus de FULL, sans
étendre leur portée de preuve. Un diff ou SHA invalide reste bloquant. Le résumé
Doctor indique les chemins, le risque, les CI retenues et leurs raisons.
`Doctor / CI Verdict` refuse une validation sélectionnée mais ignorée, annulée
ou en échec. Une sélection n'est jamais un résultat d'exécution.

`Public PR / Safe Validation` garde exactement son nom requis et devient le
verdict agrégé PR : il exige Doctor FAST (`Doctor / PR FAST`) et toutes les CI
sélectionnées. Aucun changement de ruleset distant n’est nécessaire.
`Phase Certification / Full Validation` reste le seul propriétaire de la FULL
automatique ; la vérification de provenance exige l'unique job de ce nom et
toutes ses étapes obligatoires parmi la liste complète des jobs GitHub.

Pour déclarer `CERTIFIED`, il faut toujours la FULL réelle, les parcours Doctor
et les budgets RAM/preload PASS sur le même SHA exact. Une route SCOPED et un
verdict Doctor vert signifient seulement VALIDATED ; ils n'autorisent pas la
fusion automatique et ne certifient pas une phase.

## Réutilisation contrôlée des tests dans la FULL

L'audit du run 38134779396 a trouvé des tests rejoués malgré une
`FULL_SUITE` déjà réussie : `DIFF_TARGETS`, `GOLDEN_FLOWS`,
plusieurs groupes ciblés et trois modules Guide/Succès/Shell.

`FULL_SUITE` emploie désormais le runner `tools.atlas_full_suite_proof`
avec la **même découverte canonique** `tests/test_*.py`.
Sa sortie structurée `artifacts/ci_app_logs/05_full_unittest_proof.json`
est générée par les événements terminaux `unittest` de chaque test,
pas par des expressions régulières sur un log pollué par des runners
imbriqués. Elle contient la SHA exacte, tous les IDs découverts, les
réussites et les tests non réutilisables (skip / expected failure).

Le moteur ne réutilise un groupe que si tous les tests de ses modules
ont été réellement exécutés et réussis. Toute preuve manquante,
ambiguë ou non conforme entraîne la réexécution du groupe. L'inventaire
critique `TEST_INTEGRITY` reste **toujours exécuté directement** avec
les IDs exigés ; les audits Guide restent obligatoires.

Pour les trois tests Guide/Succès/Shell, `ci_guide_full_evidence`
contrôle les **IDs exacts** contre le registre et le SHA de ce même
checkout ; un échec de preuve restaure la commande originale.
L'installation pip interne Guide peut être sautée uniquement si le
workflow Phase a déjà installé les dépendances dans le même
environnement Python. Le rapport `evidence_reused_groups` et les
`evidence_test_cases` permettent de vérifier l'économie réellement
constatée. Aucun gain de temps n'est affirmé avant mesure Windows.

## Après fusion sur main : une FULL propriétaire unique

Sur `main`, `Phase Certification` reste propriétaire de l'unique
`tools.atlas_integrity full` et du verdict de phase, avec les audits Guide,
le catalogue et l'inventaire critique. La CI applicative conserve son job
rapide de push appelé après le plan Doctor, mais **ne relance plus une FULL automatiquement**.

Après la conclusion de `Phase Certification`, `Dofus Atlas Application CI`
reçoit l'événement GitHub `workflow_run`. Un job indépendant vérifie
le résultat officiel GitHub (`completed/success`), la branche `main`,
l'événement `push`, le dépôt, le SHA de checkout et les étapes
obligatoires de la FULL. En absence de preuve exacte, le job **échoue**
sans transformer les contrôles manquants en PASS. Le job exécute alors
les tests Qt / lifecycle **ensemble dans un seul processus**, l'exigence
spécifique restante de l'ancien workflow Application FULL.

`Application FULL` reste disponible via `workflow_dispatch` pour
diagnostic manuel, sans devenir une condition automatique sur chaque
push. L'application ne réutilise jamais les preuves d'une autre révision ;
la sortie distingue les tests effectivement exécutés des preuves hôtes
réutilisées. Les gates RAM et preload indépendants restent inchangés.

## Source machine de vérité

La validation technique générale est définie par `tools/atlas_integrity_policy.json` et exécutée par `tools.atlas_integrity`.

La clôture officielle d'une phase utilise au minimum le mode `FULL`, qui doit notamment couvrir :

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

Le contrôle adaptatif (FULL ou tests ciblés avec attestation explicite) est porté par `Phase Certification / Full Validation` (`.github/workflows/phase-certification.yml`). Elle peut être lancée manuellement, mais Doctor la sélectionne désormais automatiquement selon les changements de chaque PR, sans condition sur le titre.

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


## Doctor shadow on a completed FULL (Phase 8 certification)

After the full Atlas Integrity gate, the phase workflow now generates a
read-only Doctor candidate plan and compares it with the actual FULL JSON
from **the same checked-out SHA**. Both artifacts are stored alongside the
original phase log. Invalid shadow evidence is an independent failure;
there is no second FULL execution and no retroactive waiver.

The Doctor shadow campaign is **advisory when the scope is FULL_REQUIRED**:
it shows what was and was not checked, but cannot manufacture a Phase PASS.
The authoritative Phase verdict still comes only from Atlas Integrity FULL,
the critical Guide/data evidence and the phase verdict engine.


## Certification Policy / Merge Gate (AT-026)

The pull-request workflow exposes exactly one additional job/check context:
`Certification Policy / Merge Gate`. Its executable policy lives in
`tools/ci_required_certification.py` and writes
`artifacts/cert_policy/merge_gate.json` bound to the checked-out **PR head SHA**
and the exact PR base SHA.

- **SCOPED** is permitted for docs-only or independently classified LOW/MEDIUM
  diffs only if `Public PR / Safe Validation` on that head succeeded. The
  decision is `PASS_SCOPED_NOT_FULL`, not a Phase/FULL certificate.
- Known CI-only owners use the explicit `ci_tooling_scope.py` contracts and
  successful aggregate Safe Validation. Their original risk classification is
  retained; this is targeted validation, never a Phase certificate.
- **FULL_REQUIRED** applies to application HIGH/CRITICAL changes, unknown scope,
  certification executor/policy changes outside that bounded profile and rulesets. The check accepts
  only authenticated GitHub API results for
  `.github/workflows/phase-certification.yml` with the exact candidate SHA,
  a successful completed real FULL job and **every** mandatory stage (checkout
  verification, LFS, Doduda catalog, Atlas FULL, final strict verdict) successful.
  Stale runs older than seven days, wrong heads, failed/skipped stages, missing
  API access or insufficient pagination remain BLOCKED.
- The public PR FAST check remains required and distinct. A successful FAST
  cannot waive a FULL that policy requires. Do not reuse same-named jobs from
  other workflows as evidence.

**Staged activation:** As initially delivered in PR #168, the new job uses
`ATLAS_CERT_POLICY_ENFORCE=false`. It publishes the real candidate decision and
job name for a smoke test but is NOT YET a mandatory merge gate.
Before enforcement, verify a real LOW PR and a FULL_REQUIRED PR (both positive
and negative cases), then change the workflow to `--enforce true` and update
the remote ruleset **22696080** with context
`Certification Policy / Merge Gate` in one reviewed administrative operation.
Do not silently update remote rulesets, bypass actors or replace the existing
`Public PR / Safe Validation` required check. A LOW smoke success and a
FULL_REQUIRED missing-proof BLOCKED must be visible in the generated JSON;
a green *advisory job* alone is not certification.
