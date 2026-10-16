# [PLAN 12] JSON bruts Doduda, métiers et provenance des datasets (PC-07)

> **Implémentation et audit du 16 octobre 2026.** La provenance publique est
> maintenant contrôlée avant/après une FULL. Les anomalies de relations brutes
> restent explicitement en REVIEW ; aucune donnée métier n'est inventée.

## Résultats et preuves consultables

Base applicative inspectée : `e109913698ed84b25c7873d70303d83391732cce`.
Graphify 0.9.72 a été généré sur le candidat propre
`d0943824e5b9afd074c45f84fe435ee7cae13e67` avant la modification : 49 nœuds et
175 arêtes liés aux propriétaires inventaire/provenance/build ont été examinés.
Les liens importants ont ensuite été confrontés aux sources Quest/Craft,
aux providers Succès et au workflow de certification.

- [Réconciliation nominative des 240 JSON historiques](12-json-reconciliation.csv) :
  aucun fichier disparu, les 239 décisions CONSERVER maintenues, AT-013/JS-039
  déjà traité dans #166. Les hashes actuels sont enregistrés sans transformer
  un changement de hash en permission de migration. L'inventaire de base
  contient désormais 246 JSON : les six ajouts sont quatre registres/documents
  d'audit et les deux locks publics Quest/Craft. Aucun sharding supplémentaire.
- [Inventaire public et décisions de relations](12-raw-dataset-review.json) :
  28 fichiers réellement présents, SHA-256 égaux aux locks
  `dofusdude/dofus3-main@3.7.10.10`, fingerprint de dataset
  `71082672c6e4bc43b6c4f529702a26483cb80b4cb50c1c0a227957768274d2af`.
  Chaque fichier expose schéma, cardinalités et classes de références ; les
  effets imbriqués ne sont pas comptés comme autant d'objets métier.
- Quêtes : 1 976 quêtes, 2 225 étapes et 15 547 objectifs. Les liens déclarés
  quêtes/catégories/étapes/objectifs sont complets. Quatre objectifs bruts
  (19530–19533) pointent vers l'étape 3225 absente et ne font pas partie des
  15 543 liens d'objectifs déclarés par les étapes existantes : conserver les
  sources, observation de reliquat, pas de suppression.
- Succès : 2 775 succès et 8 923 objectifs bruts. 322 références déclarées
  n'ont pas de cible, dont 37 dans les familles conservées ; 102 objectifs
  pointent vers un succès absent. Les IDs sont tous conservés dans le registre.
  Le provider assemble les objectifs existants par `achievementId` puis
  parcourt les succès existants : les objectifs orphelins ne créent pas de
  succès. Les 37 références conservées exigent la revue métier de #170,
  sans fabriquer de critères ou modifier la route canonique dans #172.
- Craft : seed public construit avec les sources exactes, 21 554 objets nommés,
  23 métiers, 4 743 recettes, 24 591 ingrédients. Zéro référence manquante
  résultat/objet, métier, ingrédient/objet ; zéro recette sans ingrédient ;
  `PRAGMA integrity_check=ok`. Les tailles/vecteurs/quantités de toutes les
  recettes brutes sont valides. Le seed est temporaire et ne remplace pas une
  base utilisateur. Les contrats existants de préservation de cette base
  restent testés.

## PC-07 — contrôle exécuté par chaque nouvelle FULL

`tools.atlas_json_inventory --raw-inputs --candidate-sha <HEAD> --output <rapport>`
réutilise exclusivement les inventaires des locks Quest/Craft. Le nouveau
helper `tools.atlas_json_raw` ne lit ni profils, ni progression, ni fichiers
arbitraires de cache. Le mode privé existant `--include-local` reste limité
aux comptes et tailles ; il ne peut pas être combiné au snapshot public.

Le workflow capture `inputs_before.json` après matérialisation du catalogue,
exige une provenance valide pour commencer la FULL, puis produit
`inputs_after.json --verify-against inputs_before.json`, même après un échec
de test. Le verdict final refuse une acquisition incomplète ou une dérive.
Les preuves CI lient le vrai SHA candidat à un fingerprint distinct des
octets de données. Une mise à jour Doduda différente des pins doit faire
l'objet d'une revue des locks ; une provenance inconnue n'est jamais PASS.
La réutilisation d'une FULL GitHub reste limitée à l'arbre Git identique et à
son run de provenance, sans exécuter de nouveaux tests sur d'autres données.

Tests négatifs : modification de même taille, autre dataset pourtant repiné,
SHA de code différent, source absente ou malformée, symlink, locks incohérents,
fingerprint falsifié et sortie CLI non nulle sur dérive. Les relations manquantes
conservent leurs IDs et leur statut REVIEW indépendamment de la provenance.

Reproduction depuis un checkout de la PR (données publiques uniquement) :

```powershell
py -3.13 -m scripts.windows.quest_assets --download
py -3.13 -m scripts.windows.craft_seed --download
$sha = git rev-parse HEAD
py -3.13 -m tools.atlas_json_inventory --raw-inputs --candidate-sha $sha --output artifacts/raw_before.json
py -3.13 -m unittest tests.test_atlas_json_raw tests.test_atlas_json_inventory tests.test_phase_certification_guardrails tests.test_distribution_craft_seed tests.test_distribution_quest_assets
py -3.13 -m tools.atlas_json_inventory --raw-inputs --candidate-sha $sha --verify-against artifacts/raw_before.json --output artifacts/raw_after.json
```

Les relevés locaux ci-dessus sont préliminaires : ils décrivent le dataset et
la base applicative cités. Les preuves avant/après du candidat final proviennent
de la CI de cette PR, pas d'un ancien SHA ni de ces chiffres documentaires.
Le bureau Windows interactif, Npcap/UAC, captures en jeu et données utilisateur
privées ne sont pas certifiés par cet audit ; #175 en reste propriétaire.

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
- [x] Inventaire complet du périmètre raw public versionné effectivement disponible
- [x] Relations examinées avec sources prouvées : Craft PASS, observations Quêtes/Succès REVIEW documentées nominativement
- [x] Preuve exacte-SHA et fingerprint distinct, contrôlés avant/après chaque nouvelle FULL
- [x] Aucun nouveau sharding, aucune bascule runtime ni migration d'état utilisateur

## Dépendances et conflits à éviter
#166 possède AT-013 (hash canonique) ; #159 possède packaging dataset ; #163 cache/rebuild ; pas de changement des 239 JSON CONSERVER en masse.

## Règles
- Lire le HEAD réel, les consumers et le registre original avant action ; preuve datée exact-SHA.
- Tests ciblés uniquement pendant les analyses/développement. FULL conditionnelle finale après stabilisation.
- Conserver sources, données, IDs, état joueur, boundaries lazy et caches jusqu'à preuve contraire.
- Le statut NON CONFIRMÉ n'est pas un défaut garanti ; consigner les environnements indisponibles.
- Aucune fusion/merge tant que le travail effectif n'est pas réalisé.
