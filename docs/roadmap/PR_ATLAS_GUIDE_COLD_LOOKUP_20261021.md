# PR — Premier accès Guide : requêtes de relations sans chargement global

## Problème étayé
Le rapport `docs/audit-remediation/2026-10-14/11-runtime-probes.md` (PC-01,
16/10/2026) a reproduit un premier appel `QuestGraphService.guide_ids(2464)`
avec `MemoryBoundGuideProvider` qui matérialise le catalogue de 26 guides.
La répétition a été corrigée par un cache borné, mais le premier coût (~13,8 s
dans le dernier relevé local) n'a **pas** été résolu. Ce chiffre n'est ni une
mesure Windows ni un budget universel.

## Périmètre et propriétaires
- `app/modules/encyclopedia/providers/memory_bound_guide_provider.py` :
  interroger les IDs de guides concernés par une quête à partir des données
  compactes existantes, sans matérialiser toutes les fiches lors d'une seule
  requête. Vérifier la signature/version et la cohérence du cache avant usage.
- `app/modules/encyclopedia/services/quest_graph_service.py` : réutiliser
  cette primitive si elle est vérifiée, **sans nouveau fournisseur parallèle**.
- Tests unitaires existants liés au provider/relations + cas cold/hot.
- Ne modifier `guides_view.py`, le planificateur #226 ni le panneau #225.

## Preuves de sortie
- [ ] Avant modification, test de reproduction instrumenté : nombre de détails
  effectivement chargés + délai premier appel/2 répétitions + RSS.
- [ ] Premier lookup sur cache valide n'entraîne pas le chargement des 26
  détails complets ; résultat ID exact et stable.
- [ ] Mode cache absent/invalide : fallback borné, résultat exact ou état
  explicite, sans fausse réussite ni boucle répétée.
- [ ] Vérifier quêtes sans guide, plusieurs guides, ordre/IDs canoniques,
  invalidation après changements des sources et libération des caches.
- [ ] Mesurer la réduction sur même machine/données et mesurer RAM process-tree,
  sans seuil de durée arbitraire entre machines.
- [ ] Les suites ciblées + Doctor/Graphify avant/après et certification finale
  sur SHA exact PASS. Aucun changement du parcours Ganymède ou de progression.

## Dépendances et limites
PR autonome pour le provider, mais valider les interfaces après intégration
#226 et #225. Garder Draft tant que correctif et preuves manquent. Aucune CI
FULL pendant développement. Pas de refonte des Guides, pas d'index géant ni
de cache non borné. À l'ouverture de la PR : **spécification uniquement**.
