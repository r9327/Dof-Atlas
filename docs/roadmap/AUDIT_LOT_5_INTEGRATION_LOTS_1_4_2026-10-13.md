# Lot 5 — Audit préalable A→Z et reprise après les lots 1 à 4
Date : 13 octobre 2026. Statut : **audit des preuves GitHub, réintégration sur main, certification du nouvel exact-SHA à effectuer**.

## Références et provenance
- Dépôt canonique : `r9327/Dof-Atlas`.
- Lot 1 PR #152, Lot 2 PR #150, Lot 3 PR #151 : fusionnés, preuves officielles consignées dans leurs PR.
- Lot 4 PR #157 : fusionné par squash sur main `8d65f506c7c9075603355bcae35ada660c004409`.
- Lot 5 PR #153 : candidat de départ `dfa4b18e975626bb72a8fd25df0426ba976cb139`, ancien parent partagé `113a163db37317c2f5755e7b94cb5cf3573d9c28`.
- L'ancien candidat du lot 5 possède des preuves de certification `38382528809` (Phase), `38382137668` (Public PR), `38382137630` (Graphify Focused), `38382137611` (AI Context), `38382528741` (RAM), `38382528789` (Preload), toutes SUCCESS sur l'ancien SHA. **Elles ne certifient pas le contenu Lot 4 combiné.**
- Certification post-fusion du lot 4 sur main, run `38433503067` : IN_PROGRESS au moment de l'audit. Ne pas déclarer PASS tant que la fin et le verdict ne sont pas accessibles.

## Inventaire du travail spécifique au lot 5, contre le merge-base
La comparaison GitHub `main...plan/atlas-audit-lot4-ci-pr-certification-finale-20261012` avant intégration donne 10 chemins :
1. `.ai/context_index.json` : régénérer depuis le nouveau tree Git, ne pas conserver la version de l'ancien SHA.
2. `docs/roadmap/AUDIT_LOT_4_CI_PR_CERTIFICATION_FINALE_2026-10-12.md` : feuille de route historique, correspond dorénavant au lot 5.
3. `tests/test_ci_runner_guardrails.py`
4. `tests/test_full_suite_structured_reuse.py`
5. `tests/test_full_suite_timing_profile.py`
6. `tests/test_guide_final_coverage_cache.py`
7. `tools/atlas_full_suite_proof.py`
8. `tools/audit_guide_ultime_manual_final_coverage.py`
9. `tools/ci_guide_full_evidence.py`
10. `tools/run_guide_ultime_ci.ps1`.

Les 57 fichiers du diff de PR #153 **avant sa mise à jour** incluent des apports déjà fusionnés via lots 1 à 3 : ce nombre n'est pas une liste de 57 changements indépendants à ré-appliquer. Conserver une seule source par fonctionnalité.

## Doctor / Graphify — preuves exactes et limites
- Graphify Code Map sur main `8d65f506` : run `38433503190` SUCCESS ; journal atteste 896/896 fichiers Python couverts, 12 612 nœuds, 36 404 liens, 0 inversion d'import runtime vers tools ; `python -m tools.atlas_doctor graph-audit --deep --json` exécuté, sans erreur bloquante de vérification SHA.
- Graphify Focused sur lot 4 `51a323f9` : run `38432361822` SUCCESS, inclut les contrats AST, traces dynamiques, simulateur de refactor, Graphify/Doctor.
- Doctor Adaptive lot 4 : run `38432361778`, FAST + parcours Windows SUCCESS ; job Windows Scoped Evidence SKIPPED, ne pas convertir en succès.
- Les nœuds isolés, communautés, goulets, consumers lexicaux et pistes de refactor sont **ADVISORY** sans preuve code/source/runtime : aucun effacement automatique de production. Le graphe AST n'est pas une observation exhaustive d'une session graphique réelle.
- Pas de diagnostic mensonger TRUE/FALSE : une alerte non reproductible reste UNVERIFIED.

## JSON — conservation du lot 4
- `JSON Focused Data Contract` run `38432361776` SUCCESS : 31 tests ciblés PASS, inventaire Git/runtime borné, preuves de corruption/duplicate/rollback, parité.
- Données canoniques Quêtes : 1 976 enregistrements, 74 partitions dérivées, générées hors runtime, source originale préservée avec SHA et comparaison exhaustive. Le lecteur existant `QuestSources` reste autorité ; pas de bascule de consommateurs non prouvée.
- `quests_enriched.json` 72,3 Mo, `image_manifest.json` 28,2 Mo représentent 95,51 % des octets JSON suivis dans l'inventaire de départ ; volume disque non synonyme de RAM.
- Métiers : aucun JSON Git suivi dans les six familles de routes auditées ; les états locaux et caches non suivis font l'objet d'un inventaire agrégé facultatif, sans exposer leurs contenus privés. Ne pas inventer des shards métiers.
- Assurer que `.github/workflows/json-focused-data-contract.yml`, `tools/atlas_json_*.py`, `tests/test_atlas_json_*.py`, `app/modules/encyclopedia/services/guide_path_profiles.py` ne sont ni supprimés ni remplacés.

## Mémoire / préchargement / performance
- Run RAM lot 4 `38432361757` SUCCESS : pic process-tree 213,26 Mo (seuil 220 Mo) et écart Guide après Home 0,28 Mo. Cible HOME <100 Mo **advisory** par décision de l'utilisateur, pas gate de fusion ; les mesures de stabilité et les autres garde-fous ne sont pas désactivés.
- Run preload comparable `38432361799` SUCCESS : après préchargement 72,67 → 71,07 Mo (-1,60 Mo) ; pic du benchmark 202,16 → 198,65 Mo (-3,51 Mo).
- FULL du candidat de lot 5 antérieur au lot 4 : run `38382528809` SUCCESS et verdict GUIDE_CERTIFIED, **non réutilisable** comme preuve du nouveau tree.
- Baseline chronométrée antérieure #151 run `38370137976` : 2 528 tests PASS, FULL_SUITE 1 444,99 s, DATA_INTEGRITY 197,745 s ; à comparer aux étapes identiques après intégration. Le gain de 69,131 s espéré des deux stages Guide est une hypothèse, pas une mesure certifiée.

## Robustesse CI, sécurité et exclusions
- Le correctif du lot 5 doit conserver l'invalidation fail-closed de la réutilisation exacte par SHA, test ID, suite, fixtures et provenance ; fallback vers l'exécution canonique si preuve manquante ou ambiguë.
- Maintenir les protections des données JSON arbitraires : identifiants uniques, intégrité des sources, SHA, limites de traversée, aucune lecture de données privées hors inventaire agrégé.
- Maintenir les tests négatifs CI, séquence Windows/Qt, absence de duplication ou perte de tests et authentification du ledger. Un job SKIPPED, une preuve historique ou une simulation Doctor ne valent pas certification.
- PR #134, #141–#146 fermées après tri; #138 (PySide6 atomic lock) reste indépendante et non fusionnée. Ne pas absorber son verrou Qt dans le lot 5.
- Aucun benchmark RAM/preload lourd ni FULL en boucle en phase de développement ; exécuter une certification exhaustive officielle sur le candidat final.

## Suite obligatoire
1. Intégrer `main` dans la branche #153 **sans forcer, sans écraser ses commits** ; résoudre `.ai/context_index.json` par régénération top-level Git vérifiée.
2. Valider l'arbre combiné et l'absence de disparition des contrats JSON ; lire Doctor/Graphify/CI au nouvel exact-SHA.
3. Exécuter les tests ciblés et les protections; corriger toute régression de cause prouvée sans changement opportuniste de baseline ou contournement.
4. Une seule FULL de certification finale à code stabilisé, comparer temps mur réel Actions, registres FULL et les deux stages Guide, puis verdict et Application CI post-merge.
5. Ne fusionner #153 que si les gates obligatoires exact-SHA sont SUCCESS; sinon rester ouvert en explicitant les NOT_RUN, FAIL ou BLOCKED.

Ce rapport décrit des **preuves observées sur GitHub** et non une exécution locale Windows dans cette session. Les workflows sont les exécuteurs de Doctor, Graphify et des benchmarks.
