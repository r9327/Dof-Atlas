# Outils et benchmarks à la demande — PR Draft incluses

Contrat de livraison : [issue #372](https://github.com/r9327/Dof-Atlas/issues/372).
Ce mécanisme complète `docs/doctor-on-demand-pr.md` : il **ne remplace pas**
Doctor, Graphify ni la certification des phases.

## Commandes depuis un commentaire de PR GitHub (ou ChatGPT connecté)

Chaque commande est une demande volontaire du collaborateur, même si la PR
est **Draft**. Le suffixe SHA est recommandé pour empêcher les analyses
involontaires d'une révision ultérieure :

```text
/atlas tools
/atlas audit
/atlas ponytail
/atlas oss
/atlas bench quick
/atlas bench runtime
/atlas bench memory
/atlas bench preload
/atlas bench 8
/atlas bench full
/atlas bench memory <HEAD_SHA_40_HEX>
```

Lancer une commande **seule dans son commentaire**, sans autre texte. L'ancien
`/atlas doctor` et `/atlas graphify` restent dans leur workflow propre.

Alternative : **Actions → Atlas Tools / Bench — On Demand → Run workflow**,
avec `pr_number`, `mode` et `expected_sha` facultatif. Ni un commentaire
non autorisé ni un fork ne doit pouvoir faire exécuter du code.

## Ce qui s'exécute vraiment

| Mode | Moteur canonique existant | Runner / coût | Limite |
|---|---|---|---|
| `tools` | `tools.tool_catalog` + `tools.tool_audit` | Ubuntu / léger | Inventaire, pas exécution automatique de chaque script |
| `audit` | Doctor `quick` + `code-inspect` | Ubuntu / léger | Statique, verdict consultatif |
| `ponytail` | Doctor `ponytail` | Ubuntu / léger | Audit, pas réparation automatique |
| `oss` | Doctor `oss --run` | Ubuntu / ciblé | Ruff 0.17.3 et zizmor 1.30.1 épinglés, fichiers du diff uniquement, max 16 |
| `bench quick` | Doctor `perf --files-only` | Ubuntu / léger | Profilage de fichiers, **pas** RAM/Qt Windows |
| `bench runtime` | Doctor `perf` | Windows / moyen | Performance runtime, machine CI et non PC réel utilisateur |
| `bench memory` | `tools/benchmark_phase8_memory.py` | Windows / moyen | Navigations, RSS/arbre processus, scénarios Qt offscreen |
| `bench preload` | `tools/benchmark_phase8_preload.py` | Windows / moyen | **Candidat seul**, pas de comparaison certifiée avec base |
| `bench 8` | Doctor `perf --app --parallel-instances 8` | Windows / élevé | **8 processus Atlas simulés**, PAS 8 comptes DOFUS Unity |
| `bench full` | Doctor `perf --app`, `perf --deep`, memory, preload et huit processus | Windows / très élevé, opt-in seulement | Campagne développeur multi-sondes, **PAS** `Atlas Doctor Complete Benchmark` ni FULL de release |

Les modes Windows s'appuient sur les dépendances PySide épinglées,
`scripts.windows.quest_assets --download` et
`scripts.windows.craft_seed --download`, comme le banc existant
`atlas-short-full-app.yml`. Aucun nouveau moteur de mesure.
Le mode `bench full` ne remplace **pas**
`.github/workflows/atlas-doctor-complete-benchmark.yml` : ce dernier
reste une orchestration indépendante dédiée à la certification élargie.

## Preuves et frontières de confiance

1. Le résolveur de commande est **chargé depuis `main`**, valide le rôle
   `OWNER/MEMBER/COLLABORATOR`, la PR ouverte et non fork, ainsi que le HEAD.
2. L'agent distant exécute l'outil nommé sur le code **du SHA candidat**.
   Le lanceur autorisé est lui aussi chargé depuis `main`, même si la PR
   est ancienne et ne contient pas ce nouveau fichier.
3. Le job de développement n'a **aucun jeton GitHub**. Le job `freshness`
   vérifie séparément que le HEAD est encore actuel.
4. Le job isolé `freshness` **essaie** d'ajouter un accusé de réception à la PR (URL du run, `run_id`, mode, SHA, états Ubuntu/Windows et fraîcheur). Selon les restrictions du jeton Actions, GitHub peut refuser ce commentaire avec HTTP 403 **même si `Issues: write` est affiché**. Ce refus n'invalide pas un diagnostic réellement exécuté : le job conserve `COMMENT_UNAVAILABLE` dans l'artefact séparé `atlas-tools-receipt-<run_id>/receipt.json` et le résumé du run. Les deux états sont des informations de livraison, jamais des certificats. Utiliser Actions ou le connecteur GitHub pour lister les runs ; ne pas inventer leur ID si le commentaire manque.
5. Récupérer les artefacts du run
   `atlas-tools-pr-<PR>-<mode>-<SHA>` (rétention 7 jours) :
   `artifacts/atlas_tools_on_demand/report.json`, `summary.json`, sorties
   de chaque commande et éventuels résultats `memory.json`, `preload.json`,
   `eight.json`, `guides.json`.
6. Croiser le `candidate_sha` du rapport, le HEAD **actuel** de la PR et
   le statut du job `freshness`. Si un seul diverge : `STALE`, jamais PASS.
   Les outils absents ou sans chemin applicable restent `UNAVAILABLE` ou
   `NOT_APPLICABLE` — jamais certifiés.

**États :** `EXECUTED_NOT_CERTIFIED` signifie que la commande a bien tourné,
pas que sa mesure est conforme aux budgets. `REVIEW` signale que les
résultats nécessitent interprétation. `FAIL`, `BLOCKED` et `TIMEOUT`
restent des échecs. `NOT_RUN` et `NOT_APPLICABLE` ne sont pas PASS.
Si une suite inclut une étape manquante, ne pas annoncer un benchmark complet.

## Sécurité, limites et coûts

- N'autoriser **aucun argument arbitraire**, chemin exécutable fourni par
  un commentaire, réparation automatique, installation dans l'EXE ou commande
  dangereuse. Le catalogue présente les outils supplémentaires, mais ne les
  exécute pas sans examen de leurs `TOOL_SPEC`.
- Les benchmarks Windows ne remplacent jamais un vrai Windows utilisateur
  avec 2/4/8 comptes DOFUS ; ces scénarios restent à valider séparément.
- Les workflows ne tournent **pas** au push ni à chaque commit ; les modes
  Windows et `bench full` consomment du temps GitHub Actions uniquement après
  une demande explicite.
- Le mode FULL de release, les gates indépendants, les signatures et le
  Delivery Guard restent inchangés.

## Vérifications

```powershell
py -3.13 -m unittest discover -s tests -p test_atlas_tools_on_demand.py -v
py -3.13 -m unittest discover -s tests -p test_doctor_pr_on_demand.py -v
py -3.13 -m unittest discover -s tests -p test_ci_domain_certification.py -v
```

Un vrai `PASS` d'accès ChatGPT exige, après fusion du workflow sur `main`,
un commentaire sur une PR Draft, un run et un artefact lus dans la même session,
ainsi que la correspondance du SHA. Une description ou une CI qui teste le code
du workflow n'est pas une preuve d'utilisation réelle.
