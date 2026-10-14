# [PLAN 10] Revue Guide : 141 observations, 200 prérequis, UI et images

> **DRAFT / préparation** : aucune correction implémentée et aucune preuve supplémentaire exécutée dans cette PR.

**Référence audit :** PR #160, main audité `ac07be9b894718f5e68e7c3a91016d7651e3065b`.

## Mission
Faire le triage exhaustif des 141 notes de formulation et 200 avertissements de prérequis contre données canoniques et parcours Guide réel, puis corriger seulement les anomalies prouvées.

## Couverture sans doublons
141 observations Guide GA, 200 avertissements GP, PC-06 et PC-08

## Sources à lire
- registres/guide-ga.json et guide-gp.json dans l'archive #160
- app/modules/encyclopedia/views/shared_manual_guide_view.py:588
- app/modules/encyclopedia/tools/audit_quests_guides.py:848
- Guide/Quêtes/Succès actifs, canonical_lock et datasets nécessaires

## Enchaînement de vérification
1. Relier chaque remarque GA/GP à un ID stable de guide/quête/succès et à la version exacte-SHA, sans assimiler un warning à un bug.
2. Trier toutes les 141 remarques et 200 avertissements : erreur prouvée, à confirmer, comportement voulu ou faux positif ; capturer preuve minimale.
3. Exécuter des scénarios réels de guides longs et scrolling/focus/accessibilité aux tailles Windows 900×600 et 1180×720 ; PC-08 reste NON CONFIRMÉ avant ces tests.
4. Prober la corruption d'images réelles modifiées et distinguer un en-tête valide d'un décodage effectif ; PC-06 reste NON CONFIRMÉ.
5. Pour toute correction Guide, protéger les chemins d'identité et les verrouillages canoniques ; ne pas rouvrir le contenu métier sans preuve.
6. Documenter les items bloqués par données Doduda raw absentes plutôt que les déclarer PASS.

## Critères de sortie
- [ ] 341 remarques individuellement décidées, avec références d'ID et statut
- [ ] Aucun ajustement de route/ordre manuel sans preuve et tests d'intégrité Guide
- [ ] UI et décodage image testés sur scénarios représentatifs ou explicitement bloqués Windows/raw
- [ ] Preuves ciblées et tableaux de décision consultables ; pas de nouvelle FULL avant code stabilisé

## Dépendances
Coordonner avec #161 pour les succès d'alignement, #164 pour le shell UI, #172 pour les données raw ; ne pas fusionner Guide renderer.

## Méthode commune
- Commencer par HEAD réel et git status. Ne pas inventer de défaut à partir d'un graphe inferred.
- Diff minime, test ciblé, vérification des consumers et impacts, AI Context régénéré après code.
- Conserver les contrats JSON, la progression utilisateur et le lazy-loading ; no FULL en boucle.
- Aucun merge tant que corrections effectives et preuves exact-SHA n'existent.

[Rapport](https://github.com/r9327/Dof-Atlas/blob/docs/audit-integral-2026-10-14/docs/audits/AUDIT_INTEGRAL_DOFUS_ATLAS_2026-10-14.md) | [Index des preuves](https://github.com/r9327/Dof-Atlas/blob/docs/audit-integral-2026-10-14/docs/audits/2026-10-14-ac07be9b/README.md).
