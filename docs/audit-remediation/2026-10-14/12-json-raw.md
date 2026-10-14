# [PLAN 12] JSON bruts Doduda, métiers et provenance des datasets (PC-07)

> **PLAN PRÉPARATOIRE — zéro correctif implémenté ici.** Aucun constat non confirmé ne doit être promu en bug sans reproduction.

Référence : [PR #160](https://github.com/r9327/Dof-Atlas/pull/160), SHA du code audité `ac07be9b894718f5e68e7c3a91016d7651e3065b`.

## Objectif
Compléter la vérification des données que l'audit ne pouvait pas lire : sources Doduda externes, métiers/recettes, relations, catalogues et empreintes d'inputs de certification. Ne pas redécouper 239 JSON conservés.

## Périmètre à ne pas omettre
240 JSON suivis, documents utilisateur non suivis, catégories Doduda brutes et PC-07 (NON CONFIRMÉ)

## Sources
- docs/audits/2026-10-14-ac07be9b/JSON_DECISIONS.md
- registres/json-decisions.json dans archive #160
- data/encyclopedia/quests/{quests_enriched,image_manifest,source_mapping}.json
- raw Doduda languages/fr, quest/steps/objectives/achievements/items/jobs/recipes/monsters/maps
- base SQLite Craft et données privées de progression, sans collecte de données personnelles réelles

## Méthode et étapes
1. Reconciler les 240 décisions JS (239 CONSERVER, 1 NETTOYER déjà propriétaire #166), les candidats consumers et les limites de preuve par famille.
2. Sur un dataset brut Doduda versionné autorisé, inventorier fichiers, schémas, cardinalités, contraintes d'identités/relations et dépendances de vrais lecteurs.
3. Valider provenance/version/hash des inputs externes chargés pendant chaque run Phase Certification (PC-07), ne pas confondre SHA du code et SHA du jeu de données.
4. Examiner métiers/recettes et catalogues SQL après génération : vérifier items/jobs/recipes, liens absents/dupliqués, parcours Craft représentatifs ; blocage documenté si dataset manquant.
5. Vérifier sélection JSON utilisateur et bases persistance comme états de session non distribuables, sans les supprimer ou les partitionner.
6. Comparer les 74 shards dérivés à l'index offset existant seulement si une nouvelle hypothèse de gain mesurable le justifie ; prioriser offset source déjà ~31x plus rapide sur l'échantillon audit.
7. Établir une liste explicite des validations impossibles localement faute de données Windows/Doduda, sans PASS fictifs.
8. Coordonner avec #159 la matérialisation des fichiers requis dans l'EXE, sans dupliquer l'implémentation de packaging.

## Sortie vérifiable
- [ ] Inventaire complet sur dataset raw réellement disponible OU lacune marquée BLOCKED avec version attendue
- [ ] Relations métiers/recettes/quests/achievements validées avec tests ciblés et sources prouvées
- [ ] Preuve exacte-SHA inclut la provenance des entrées externes, pas seulement Git
- [ ] Aucun nouveau sharding/bascule runtime sans parité et gain prouvé

## Dépendances et conflits à éviter
#166 possède AT-013 (hash canonique) ; #159 possède packaging dataset ; #163 cache/rebuild ; pas de changement des 239 JSON CONSERVER en masse.

## Règles
- Lire le HEAD réel, les consumers et le registre original avant action ; preuve datée exact-SHA.
- Tests ciblés uniquement pendant les analyses/développement. FULL conditionnelle finale après stabilisation.
- Conserver sources, données, IDs, état joueur, boundaries lazy et caches jusqu'à preuve contraire.
- Le statut NON CONFIRMÉ n'est pas un défaut garanti ; consigner les environnements indisponibles.
- Aucune fusion/merge tant que le travail effectif n'est pas réalisé.
