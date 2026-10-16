# [PLAN 01] Réparer alignements et test provider compact réel (AT-001)

> PLAN PRÉPARATOIRE — aucun correctif applicatif implémenté ici. PR DRAFT à compléter en code et tests ciblés avant revue/fusion.

Audit source : PR #160, SHA audité `ac07be9b894718f5e68e7c3a91016d7651e3065b`. Branche de base : `main` ; éviter de mélanger les modifications de PR #159 et #138.

## Objectif
Réparer la propagation des quêtes d’alignement vers les succès en utilisant la classe réellement exportée et le provider compact du produit.

## Dépendances et ordre
Indépendant ; à intégrer en premier, avant distribution #159.

## Constat et preuves détaillées
### AT-001 — Les succès d’alignement perdent les IDs des guides compacts
- Priorité / état : P1 / CONFIRMÉ / main.
- Localisation : app/modules/encyclopedia/services/memory_bound_achievement_progress_service.py:15 _alignment_main_quest_ids; app/modules/encyclopedia/providers/memory_bound_guide_provider.py:523 _summary_from_compact_row; app/modules/encyclopedia/services/progress_service.py:305 sync_from_quest_progress; tests/test_memory_bound_achievement_progress.py:66 test_alignment_progress_uses_compact_guide_summaries; tests/test_memory_policy_contract.py:306 test_achievement_sync_uses_compact_alignment_guide_ids.
- Cause : La classe réellement exportée par services/__init__.py surcharge le helper corrigé de la classe de base. Elle lit required_steps dans les résumés compacts, qui n’exposent plus les étapes. Le compteur Pa reste à zéro malgré des quêtes d’alignement terminées. Le témoin actuel utilise un fake qui conserve required_steps ; le garde source vérifie la classe de base, pas l’override actif.
- Preuve audit : alignment-contract-reproduction.json : construction réelle des résumés, IDs extraits des deux JSON canoniques ; index compact 109 IDs par guide, helper actif retourne deux tuples vides, helper de base retrouve les IDs. Critère isolé Pa>0 : false dans le service actif, true avec la base. Ces IDs ne représentent pas une nouvelle règle métier de 109 niveaux.
- Correction du registre : Lire progress_quest_ids_for en priorité dans le helper actif ; conserver le fallback get_summary_by_id pour les providers de compatibilité. Réutiliser la logique déjà présente dans progress_service, sans réhydrater les détails et sans changer les quêtes canoniques.

## Implémentation attendue
1. Réviser _alignment_main_quest_ids dans memory_bound_achievement_progress_service pour consulter progress_quest_ids_for et conserver le fallback de compatibilité.
2. Ne pas réhydrater les détails Guide et ne pas modifier les IDs ou critères des guides canoniques.
3. Remplacer les fixtures enrichies trompeuses par un véritable résumé metadata-only/index compact provenant du provider actuel.
4. Vérifier l’enchaînement Quêtes → Guide compact → service Succès effectif → compteur et vue (Pa/Pr, Bonta/Brâkmar).

## Validations ciblées
- [ ] tests.test_memory_bound_achievement_progress
- [ ] tests.test_memory_policy_contract
- [ ] tests.test_achievements_lot7
- [ ] tests.test_progress_concurrent_instances

## Critères de sortie
- [ ] Pa/Pr reflète les quêtes réellement cochées et le décochage.
- [ ] Test échoue sur main ac07be9b avant fix et passe après.
- [ ] Espion qui échoue si get_by_id ou détails lourds sont chargés.
- [ ] Pas d’augmentation de coût warmup/Guide par réhydratation.

## Garde-fous communs
- Conserver toutes les fonctionnalités, les sources JSON et le comportement lazy sauf correction justifiée.
- Vérifier HEAD réel, git status et diff avant de coder. Aucun refactor de masse fondé sur le seul degré Graphify.
- Faire tests ciblés pendant le développement ; FULL uniquement à la certification si la policy l'exige.
- Recouper les observations avec les preuves de PR #160 ; distinguer CONFIRMÉ, PROBABLE, NON CONFIRMÉ.
- Mettre à jour AI Context avec son générateur après code, puis preuve exacte-SHA.
- Pas de merge automatique de cette PR préparatoire.

Sources : [rapport intégral](https://github.com/r9327/Dof-Atlas/blob/docs/audit-integral-2026-10-14/docs/audits/AUDIT_INTEGRAL_DOFUS_ATLAS_2026-10-14.md) ; [registre anomalies](https://github.com/r9327/Dof-Atlas/blob/docs/audit-integral-2026-10-14/docs/audits/2026-10-14-ac07be9b/registres/anomalies.json).
