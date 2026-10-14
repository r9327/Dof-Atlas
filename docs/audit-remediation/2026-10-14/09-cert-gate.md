# [PLAN 09] Gate de certification adaptative exigé au merge (AT-026)

**PLAN SEULEMENT — pas d'implémentation ni de certification.**

Source : audit [PR #160](https://github.com/r9327/Dof-Atlas/pull/160), SHA audité `ac07be9b894718f5e68e7c3a91016d7651e3065b`, anomalies **AT-026**.

## Objectif
Imposer sur GitHub une preuve de certification exacte-SHA lorsque la policy l’exige, sans FULL inutile pour chaque PR.

## Fichiers et frontières à vérifier
- `.github/rulesets/integration-branch.json`
- `PHASE_CERTIFICATION.md`
- `.github/workflows/phase-certification.yml`
- `Public PR / Safe Validation (contexte CI)`

## Implémentation prévue
1. Créer un seul check de policy qui route les demandes FULL ou SCOPED selon le risque et les chemins modifiés.
2. Vérifier preuve authentifiée, exacte-SHA, fraîche et complète ; refuser fail, stale, autre HEAD ou skip d’un stage requis.
3. Conserver les PR docs-only et LOW sans FULL si policy les autorise, avec justification visible.
4. Tester le nouveau required check et son nom réel avant de toucher au ruleset distant 22696080.
5. Ne pas changer les bypass ou fusionner #138/#159/#160 au titre de cette PR ; opération administrateur séparée explicite.

## Tests ciblés obligatoires
- [ ] FULL_REQUIRED sans preuve FAIL ; mauvaise SHA FAIL
- [ ] FULL échouée / stage requis skipped FAIL
- [ ] doc-only LOW sans FULL justifiée PASS
- [ ] vraie PR smoke avant update des rulesets

## Dépendances
Après stabilisation des corrections et preuves CI ; modifier les règles GitHub seulement une fois le gate testé.

## Critères de sortie
- [ ] Reproduction/contrat de départ documenté et corrigé par modification réelle du code.
- [ ] Aucun consumer ou scénario métier cassé ; différences revues précisément.
- [ ] Résultats avec niveau de preuve, provenance, limites de couverture et SHA exact.
- [ ] AI Context synchronisé via son générateur après changement de code.
- [ ] Tests ciblés verts ; FULL seulement à certification selon policy, pas en boucle.
- [ ] Pas de fusion automatique ni de renommage/découpage JSON arbitraire.

[Rapport intégral](https://github.com/r9327/Dof-Atlas/blob/docs/audit-integral-2026-10-14/docs/audits/AUDIT_INTEGRAL_DOFUS_ATLAS_2026-10-14.md) — [Registre de preuves](https://github.com/r9327/Dof-Atlas/blob/docs/audit-integral-2026-10-14/docs/audits/2026-10-14-ac07be9b/registres/anomalies.json).
