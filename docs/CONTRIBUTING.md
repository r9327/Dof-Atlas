# Contribuer à Dofus Atlas

Merci de garder les changements petits, vérifiables et centrés sur une cause
racine. Une PR doit pouvoir être comprise et validée sans affaiblir les contrats
existants ni toucher aux données utilisateur.

## Avant de modifier

1. Créez une branche depuis un `main` à jour.
2. Lisez `AGENTS.md` et les règles retournées par Atlas Doctor.
3. Planifiez les chemins réellement concernés :

```powershell
py -3.13 -X utf8 -m tools.atlas_doctor agent plan <chemins> --base-ref origin/main --json
```

Utilisez `--structural` pour une suppression, un déplacement, une dépendance,
un cycle ou un changement d’architecture. Si le plan retourne `REVIEW` ou
`BLOCKED`, traitez la raison au lieu de contourner le verdict.

## Implémentation

- préférez un lot cohérent à un refactor transversal opportuniste ;
- réutilisez les services et validateurs canoniques avant d’ajouter une voie parallèle ;
- conservez les formats, migrations et lectures historiques nécessaires aux utilisateurs ;
- n’éditez pas les artefacts générés pour faire disparaître un échec ;
- n’ajoutez aucun `skip`, `xfail`, ignore ou whitelist destiné à obtenir un PASS.

Les changements de persistance doivent démontrer la compatibilité ou fournir
une migration. Les changements Qt doivent vérifier le cycle de vie, les signaux
et la destruction ciblée. Les changements réseau doivent préserver les limites
de confiance, les identités de session et l’arrêt propre des workers.

## Cadence CI commune à toutes les PR

Ouvrir les PR en **Draft** et effectuer d'abord la totalité du travail prévu
(implémentation, contrats, tests ciblés, intégrations, relecture). Les commits
intermédiaires ne doivent **pas** déclencher une FULL/Phase Certification.

Quand la PR est réellement complète, la passer en **Ready for review** pour
déclencher **une certification CI** du SHA final. En cas d'échec, corriger,
puis recertifier le nouveau SHA (nouveau passage Draft → Ready ou
`workflow_dispatch` manuel). Ne jamais réutiliser un résultat d'un ancien
SHA. Le push sur `main` et les garde-fous de publication restent inchangés.

## Validation proportionnée

Pendant le développement, lancez d’abord le module de test le plus proche puis
le contrôle ciblé proposé par Doctor :

```powershell
py -3.13 -m unittest tests.test_module_concerne
py -3.13 -X utf8 -m tools.atlas_doctor agent check <chemins> --base-ref origin/main --run-tests --json
```

Avant la PR, exécutez la validation indiquée par le plan. Ne lancez pas FULL par
réflexe : FAST et les suites ciblées servent au feedback de développement ; les
workflows de certification restent l’autorité pour le SHA fusionné.

Un test ignoré pour une capacité système réellement absente doit rester
distinguable d’un test fonctionnel réussi. Ne présentez jamais une comparaison
de modes différents comme une régression ou comme un PASS comparable.

## Contenu de la PR

La description doit indiquer :

- le problème et sa cause racine ;
- la portée exacte et les fichiers sensibles éventuels ;
- les commandes exécutées, leur résultat et le SHA testé ;
- ce qui n’a pas été testé ou certifié ;
- les dépendances avec d’autres PR et l’ordre de fusion, le cas échéant.

Pour une modification visuelle, joignez une capture ou un scénario Doctor UI.
Pour une modification structurelle, joignez une preuve Graphify à jour et
confirmez les consommateurs avant toute suppression.

## Données et secrets

Ne commitez jamais de jetons, captures réseau privées, chemins personnels,
bases locales ou progression utilisateur. `data/local/zaaps.json` est une donnée
utilisateur protégée. Utilisez des fixtures synthétiques minimales dans les
tests et vérifiez `git diff --check` ainsi que `git status` avant le push.
