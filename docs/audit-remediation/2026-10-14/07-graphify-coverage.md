# [PLAN 07] Graphify chemins structurants et réutilisation vérifiable (AT-017)

**DRAFT : plan préparatoire uniquement, aucun code applicatif modifié.**

Référence audit : [PR #160](https://github.com/r9327/Dof-Atlas/pull/160), SHA `ac07be9b894718f5e68e7c3a91016d7651e3065b`. La détection de chemins manquants AT-017 est confirmée dans le registre publié.

## Périmètre
`.github/workflows/graphify-map.yml`, `main.py`, `launch.py`, `local_dofus_data/`, `tools/atlas_doctor.py`, `tools/atlas_doctor_lib/`, Graphify sources/configs et tests CI.

## Travaux précis
1. Compléter .github/workflows/graphify-map.yml : pull_request.paths et push.paths couvrent main.py, launch.py, local_dofus_data/, tools/atlas_doctor.py, tools/atlas_doctor_lib/ et toute entrée Graphify vraiment structurante.
2. Vérifier que les changements docs-only n'activent pas un rebuild lourd. Les changements impactant Graphify mais non couverts doivent être signalés STALE/MISSING plutôt que PASS.
3. Réutiliser les graphes uniquement sous égalité exacte du SHA code, empreintes des entrées, configuration et version de l'analyse ; paginer sans reconstruire.
4. Ne pas confondre arêtes inferred, imports AST confirmés et appels runtime. Aucune proposition safe_to_delete provenant de la seule connectivité.
5. Réaliser tests de routage avec fichiers de chaque famille ; documenter un cache invalide et un graphe périmé.

## Tests ciblés
- [ ] tests.test_graphify_workflow_budget
- [ ] tests.test_ci_runner_guardrails
- [ ] changement isolé main.py / launch.py / local_dofus_data / atlas_doctor_lib déclenche l'analyse
- [ ] docs-only ne génère pas de rebuild superflu
- [ ] SHA/config changé -> graphe STALE explicite, pas réutilisé comme preuve

## Sortie et dépendances
- [ ] Test positif et négatif pour chemins structurants / documentation.
- [ ] Les méta-données indiquent EXACT / STALE / MISSING et provenance SHA/version.
- [ ] Même graphe réutilisé pendant pagination, aucune reconstruction artificielle.
- [ ] Distinction claire des preuves runtime / AST / inferred.
- [ ] AI Context synchronisé après code ; tests ciblés PASS et FULL seulement si policy.

Coordonner le contrat de provenance avec [PR Doctor prévue](https://github.com/r9327/Dof-Atlas/pull/166), sans implémentation doublonnée. Ne rien fusionner avant code et certification.

[Rapport intégral](https://github.com/r9327/Dof-Atlas/blob/docs/audit-integral-2026-10-14/docs/audits/AUDIT_INTEGRAL_DOFUS_ATLAS_2026-10-14.md).
