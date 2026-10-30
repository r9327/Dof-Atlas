# Audit des frontières de chargement — DOFUS ATLAS, 30 octobre 2026

Dépôt public `r9327/Dof-Atlas`, PR #303. Inspection de code sur
`cf5330a89d73cec60b0043c84d56703cc696aa12` ; les performances
et la couverture ne sont certifiées **que** par les runs du HEAD final.

## Règle à appliquer partout

Conserver en RAM uniquement les index, identifiants stables, métadonnées de
navigation et état de progression nécessaires. Hydrater le contenu volumineux
et les widgets sur une action réelle. Précharger un voisinage borné quand la
latence est visible. Libérer ce contenu au retour Home. Un index incomplet
ne doit **jamais** décaler une validation déjà sauvegardée.

## Revue des domaines (constat de code, pas certification de performance)

| Domaine | Chemin vérifié | Politique existante | Diagnostic/action |
|---|---|---|---|
| Sylvestre (Guide de catalogue, 1 672 fiches) | `services/guide_catalog_manual_runtime_service.py`, `services/guide_catalog_route_store.py`, `views/shared_manual_guide_view.py` | **PR #303 :** index stable complet en SQLite, corps des fiches compressé séparément ; lecture active + prélecture bornée (jusqu'à 9, LRU 10). Repli ancien cache et sources canoniques | **P0**. Avant correction, 198 quêtes construites en une seule passe même si une seule fiche était visible. **Reste** : premier chargement à froid, CPU Qt, RAM globale |
| Quêtes | `providers/quest_provider.py`, `app/quest_catalog_details.py`, `app/pages/lazy_quests_page.py` | Catalogue léger partagé ; détails `DeferredQuestRecord` via SQLite, arbre hiérarchique chargé progressivement ; cache détails borné | Déjà lazy. **P0 suivi** : le premier détail riche était coûteux ; mesurer compilation et coût des recherches, ne pas gonfler arbitrairement la RAM |
| Succès | `providers/memory_bound_achievement_provider.py`, `views/achievements_view.py` | Index compact, résumés et détail séparés ; batch Qt + chargement différé de l'onglet | Déjà progressif, **P1 suivi** : premier détail et matérialisation des objectifs, vérifier l'absence de scan global à chaque sélection |
| Guides classiques | `providers/memory_bound_guide_provider.py`, `views/guides_view.py` | Index `jsonl` compact, un seul détail de Guide retenu, éléments de l'UI partiellement différés | **P1** : `_populate_guide_info` / récompenses peuvent encore hydrater des données de quêtes en bloc ; audit Doctor par Guide, sans toucher au catalogue sain |
| Guide Ultime manuel | `services/guide_ultime_manual_runtime_core.py`, `views/shared_manual_guide_view.py` | Cache route compact complet (267 fiches), UI une seule fiche Qt ; contenu et progression propres | **P1** : le cache runtime JSON existant restaure la route complète, contrairement au nouvel index Sylvestre ; évaluer une indexation similaire, en conservant strictement les branches classe/Ordres |
| Crafts | `app/craft_preload.py`, `app/pages/craft_page.py` | Précharge uniquement les métadonnées des métiers et la sélection ; items recherchés dans SQLite, résultats Qt par lots | Déjà lazy. **P1 suivi** : vérifier le coût d'une première recherche et la rétention des images après Home |
| Stuffs / équipement | `app/pages/equipment_page.py` | Initialisation Chromium/WebEngine différée jusqu'à ouverture réelle | Déjà différé, **P2** : surveiller coût initial du processus WebEngine et sa libération après navigation |
| Carte monde | `app/cartography/world_db.py`, `app/cartography/world_service.py`, `app/ui/map_canvas_widget.py` | Données mondes dans SQLite ; rendu carte distinct de la base | **P2** : l'existence de SQLite ne prouve pas que les textures visibles sont chargées par tuile ; profiler QPixmap/affichage avant de modifier |
| Accueil / changement de domaine | `app/modules/encyclopedia/views/memory_bound_encyclopedia_page.py`, `app/pages/home_page.py` | Widgets onglets lazy + relâchement des catalogues/reconstitutions au retour Home | **P0** : RAM Home et destruction effective des QObject à quantifier ; pas de full preload par défaut |
| Préchargement initial | `app/preload.py`, `app/startup_cache_warmup.py`, `app/startup_cache_domain_worker.py` | Workers jetables, caches par famille, versions et réutilisation ; préparation initiale distincte de l'hydratation UI | **P0** : éviter les doubles constructions et les workers simultanés ; garder les temps d'ouverture et de première installation séparés |
| Bestiaire, Almanax, Ocre, Chasse | La revue du présent lot n'a pas établi de chemin de détail runtime comparable à celui des Guides | **Non vérifié**, ne pas affirmer un chargement intelligent | **P2** : tracer les vrais points d'entrée de navigation et les scans de données avant toute modification |

## Contrats spécifiques Sylvestre (PR #303)

1. `manual_stage_id`, `index`, `manual_quest_ids`, sommaire et
   `a_preparer` demeurent disponibles pour **toutes** les fiches sans
   décompresser leur contenu narratif.
2. Les sources `manual_sections` détaillées et `manual_lines` vivent en
   lignes SQLite compressées indépendantes, restaurées uniquement par les API
   `manual_sections_for_card` et `manual_lines_for_card`.
   Les informations `prepare` nécessaires au panneau global restent dans
   l'index léger pour préserver les besoins des participants.
3. Au rendu, la fiche visible est hydratée et un voisinage d'au plus neuf
   fiches est préchargé dans une LRU de dix. Aucun cache ne stocke la
   progression ni un `QWidget`.
4. Toute modification des sources Quêtes ou du Guide invalide la génération.
   Une génération ne remplace l'ancienne qu'après transaction et publication
   atomique. Les caches sont reconstructibles.
5. Les builds source ou installés doivent conserver des identités stables ;
   les caches anciens `json.gz` se migrent sans réécrire la progression.
6. Cache **froid** : la génération des 198 quêtes reste synchrone jusqu'à
   création d'un premier index. Ce lot ne prétend pas avoir résolu ce coût.
7. Non-régression impérative : sélections, validations, sauts de fiches,
   participants multiples, préparation globale, objets et combats, 52 scénarios
   Guides, mémoire et gels Qt. Si un scénario échoue, PR non certifiable.

## Ordre des travaux suivants

- **P0** : prouver la parité du nouvel index et la baisse de consommation
  et de latence sur le HEAD exact, avec Doctor et Graphify.
- **P0** : éliminer le coût de première génération, sans déplacer dix secondes
  ni un pic mémoire vers un préchargement bloquant au démarrage.
- **P0** : traiter les pics >250 Mio et le retour Home >100 Mio à partir des
  attributions du Doctor, pas sur une intuition.
- **P1** : mesurer les premières ouvertures détaillées Quêtes/Succès et les
  enrichissements de Guides classiques.
- **P1** : examiner l'indexation du Guide Ultime, sans toucher à ses règles
  de classe et d'Ordre.
- **P2** : cartographie, WebEngine et outils annexes seulement après preuves
  de chargement ou de rétention excessifs.

Cet inventaire ne remplace pas une certification Windows réelle ; aucune
optimisation supplémentaire ne doit être marquée PASS sans mesure.
