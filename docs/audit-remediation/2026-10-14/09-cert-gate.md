# [PLAN 09] Gate de certification adaptative exigé au merge (AT-026)

**Code, workflow advisory et tests de policy livrés sur la branche ; validation CI et activation administrative encore à réaliser.**

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
- [x] Tests unitaires FULL_REQUIRED sans preuve et mauvaise SHA : BLOCKED (exécution CI à vérifier)
- [x] Tests FULL échouée / stage requis skipped : BLOCKED (exécution CI à vérifier)
- [x] Test docs-only LOW : PASS_SCOPED_NOT_FULL, justification enregistrée (exécution CI à vérifier)
- [ ] Vraie PR smoke du nouveau contexte puis activation distante des rulesets par opération administrateur distincte

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

## Implémentation AT-026 et périmètre effectif

- `tools/ci_required_certification.py` classe les fichiers depuis le diff Git exact base/head via `tools.atlas_integrity.classify_risk`, surdétermine les owners sensibles depuis `tools.phase_adaptive_gate.critical_changed` ; le plan, les labels et les sorties non vérifiées du PR ne déterminent pas le risque.
- Le statut `PASS_SCOPED_NOT_FULL` exige que le job Public PR / Safe Validation soit réussi sur le même commit. `FULL_REQUIRED` refuse l'absence de FULL et accepte exclusivement les runs/actions issus de l'API GitHub authentifiée, même SHA et repo, moins de sept jours, avec job et cinq étapes obligatoires réussies. Un stage skipped, mauvais head, mauvaise workflow, temps obsolète ou erreur API : BLOCKED.
- `.github/workflows/public-pr-ci.yml` crée le contexte `Certification Policy / Merge Gate` dépendant de `safe-validation`; mode advisory `ATLAS_CERT_POLICY_ENFORCE=false` pour *smoke* du nom réel et preuve JSON avant tout verrou distant. La sortie du job en mode observation ne remplace PAS la décision du rapport JSON.
- `tests/test_ci_required_certification.py` vérifie tous les chemins refusés et des données d'API simulées, avec cas positif FULL authentifié. Aucun token GitHub réel dans les fixtures, aucun résultat local auto-attesté.
- `PHASE_CERTIFICATION.md` décrit la distinction SCOPED / FULL et la séquence d'activation séparée après preuve positive/negative sur des PR réelles. `.github/rulesets/integration-branch.json` et le ruleset distant `22696080` restent **inchangés** : pas de contournement ni changement admin sans revue.
- **Statut de fin :** tests CI, inspection de job name et smoke encore à vérifier ; activation distante non tentée ; une seule nouvelle PR ne peut pas à elle seule prouver le scénario LOW et FULL de manière authentifiée.
