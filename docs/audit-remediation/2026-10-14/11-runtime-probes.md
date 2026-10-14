# [PLAN 11] Probes runtime : performance Guide/Craft, warmup et lifecycle (PC-01 à PC-05)

> **DRAFT / préparation** : aucune correction implémentée et aucune preuve supplémentaire exécutée dans cette PR.

**Référence audit :** PR #160, main audité `ac07be9b894718f5e68e7c3a91016d7651e3065b`.

## Mission
Mesurer les coûts et risques dans de vrais parcours avant de prescrire cache, thread cancel ou suppression d'un préloader.

## Couverture sans doublons
PC-01, PC-02, PC-03, PC-04, PC-05 (toutes NON CONFIRMÉES)

## Sources à lire
- memory_bound_guide_provider.py:256 et consumers Quest UI
- app/pages/craft_page.py:773
- DOFUS.bat:82 et app/startup_cache_warmup.py:145
- app/modules/encyclopedia/views/encyclopedia_page.py:950
- main.py:510/530 et app/preload.py:30

## Enchaînement de vérification
1. PC-01 : spy réel des requêtes relations sur une session Guide/Quêtes ; conserver search-text cache déjà en place, indexer seulement si un coût est mesuré.
2. PC-02 : fixture SQLite avec correspondances métier au-delà de limit=160, puis refaire une recherche avec filtrage catégorie ; mesurer ordre SQL/filter vs affichage.
3. PC-03 : deux lancements Windows proches, traces mono-instance, collision de fichiers .tmp et workers ; un soupçon de concurrence ne vaut pas preuve d'écrasement.
4. PC-04 : fermer Encyclopédie/Home pendant un chargement froid, observer weakrefs, QThread, deleteLater et stabilisation en fin de worker ; distinguer rétention transitoire et fuite.
5. PC-05 : lister consommateurs source et externes de run_startup_preload/build_preload_payload, tests et CLI avant toute suppression, tracer chemins hérités.
6. Conserver le bilan NON CONFIRMÉ lorsque Windows/data manque ; corriger uniquement un comportement reproduit ; relier les corrections prouvées aux PR #163/#164/#167 si elles sont déjà propriétaires.

## Critères de sortie
- [ ] 5 pistes chacune avec reproduction, verdict et verdict négatif si applicable
- [ ] Pas de nouvelle couche de cache ou suppression de code sur la seule connectivité Graphify
- [ ] Scénarios anti-régression ajoutés si bug avéré, gain perf/RAM mesuré sans détour

## Dépendances
Coordonner #163 caches, #164 UX Craft, #167 performance ; Win32 native requis pour PC-03, session Qt réelle pour PC-04.

## Méthode commune
- Commencer par HEAD réel et git status. Ne pas inventer de défaut à partir d'un graphe inferred.
- Diff minime, test ciblé, vérification des consumers et impacts, AI Context régénéré après code.
- Conserver les contrats JSON, la progression utilisateur et le lazy-loading ; no FULL en boucle.
- Aucun merge tant que corrections effectives et preuves exact-SHA n'existent.

[Rapport](https://github.com/r9327/Dof-Atlas/blob/docs/audit-integral-2026-10-14/docs/audits/AUDIT_INTEGRAL_DOFUS_ATLAS_2026-10-14.md) | [Index des preuves](https://github.com/r9327/Dof-Atlas/blob/docs/audit-integral-2026-10-14/docs/audits/2026-10-14-ac07be9b/README.md).
