# Lot 4 — Inventaire GitHub des JSON et décision par famille (13/10/2026)

**Statut : inventaire statique réel de GitHub, pas une certification Windows ni un profilage de runtime.**
Référence : `main` exact `113a163db37317c2f5755e7b94cb5cf3573d9c28` (lots #152, #150 et #151 déjà fusionnés).
Méthode : énumération des arbres Git par sous-répertoires pour contourner la troncature de l'arbre racine (> 60 000 entrées), filtre strict `.json`. Tailles **Git** et non taille RAM désérialisée. Les caches générés et les fichiers non suivis, notamment les données locales des utilisateurs, **ne sont pas couverts** par ce relevé. Les 239 fichiers comprennent aussi les fichiers d'outillage et de configuration.

| Sous-ensemble suivi dans Git | JSON | Octets | Décision |
| --- | ---: | ---: | --- |
| `data/encyclopedia/quests` | 3 | 102 390 702 | Optimiser les accès ciblés ; seules les grosses sources candidates à dérivation |
| `data/routes/guide_ultime_manual` | 189 | 1 615 874 | **KEEP** : déjà découpé par chapitre |
| `data/encyclopedia/guides` | 28 | 1 034 712 | **KEEP** : guides individualisés ; `guide_complet` à profiler avant changement |
| `data/cartography` | 3 | 96 205 | **KEEP** |
| `data/local` | 1 | 22 414 | **KEEP** : Zaaps |
| `data/network` | 3 | 25 332 | **KEEP** : recherche de protocole |
| `tools` | 7 | 77 249 | **KEEP** : règles et données d'outillage |
| `tests` | 1 | 10 083 | **KEEP** : contrat de tests |
| `.github` | 2 | 2 288 | **KEEP** : politiques de dépôt |
| `.ai` | 2 | 5 999 | **KEEP** : contexte de développement |
| **Total** | **239** | **105 280 858** | |

**Point de concentration** : `quests_enriched.json` (72 317 050 octets) et `image_manifest.json` (28 237 353 octets) représentent ensemble **95,51 %** de la taille de tous ces JSON suivis. Cette concentration ne prouve pas à elle seule une consommation RAM ; seuls les consommateurs réellement chargés comptent.

## Décisions ciblées, sans défaire les lots 1–3

1. **Quêtes enrichies (72,3 Mo)** : conserver la source canonique. Le lecteur par offsets `QuestSources` et SQLite acquis en lots antérieurs prévalent. Le générateur `tools/atlas_json_shards.py` produit des partitions dérivées par plages d'IDs avec SHA et contrôle de parité, **hors runtime**, sans source concurrente. L'accès Guide à tous les prérequis auparavant obtenu par `json.loads` du monolithe est repris depuis la #156 avec le lecteur existant. Le gain est `NOT_MEASURED`, le coût de décodage par enregistrement reste à relever. Une bascule de consommateurs vers les shards n'est **pas autorisée avant profilage et tests de parité**.
2. **Manifeste d'images (28,2 Mo)** : source déclarée **index de provenance**, utilisée par les outils offline `audit_quest_visuals.py` et `integrate_quest_visuals_lot6.py`. Un index URL/SHA ou des partitions par hash sont candidats *seulement* si les usages offline sont coûteux et si le générateur `enrich_quests.py` est migré avec les consommateurs. Aucun chargement massif dans l'UI démontré ; **REVIEW**.
3. **Mapping Quêtes (1,84 Mo)** : garder les clés/identifiants et le contrat de progression inchangés ; mesurer les recherches réellement coûteuses. **REVIEW / INDEX_ONLY** selon profil.
4. **Guide/Succès/Bestiaire** : aucune preuve qu'il faut redécouper les 189 chapitres Guide, les 28 guides individualisés ou une source Succès déjà couverte par des index compacts. Préserver les accès existants et vérifier dans leurs producteurs/importeurs toute source **hors Git** avant de décider.
5. **Métiers, recettes, items, équipements** : les six répertoires `data/routes/{alchimiste,bucheron,chasseur,mineur,paysan,pecheur}` inspectés ne contiennent **aucun JSON suivi**, mais des fichiers PNG (généralement pointeurs LFS). `local_dofus_data` contient des importeurs/repos Python, **aucun JSON Git**. Il faut auditer ses magasins SQLite / caches générés et les API consommatrices **sans fabriquer artificiellement des partitions métiers JSON**.
6. **Autres familles** : les petits JSON cartographiques, Zaaps, protocoles, politiques et fixtures restent tels quels : aucun bénéfice identifié à les fractionner.

## Contrôle reproductible sur un checkout Windows complet

```powershell
py -3.13 -m unittest tests.test_atlas_json_inventory tests.test_atlas_json_shards tests.test_guide_prerequisite_lookup tests.test_quest_source_boundaries
py -3.13 -m tools.atlas_json_inventory --output artifacts/lot4/json_inventory.json
py -3.13 -m tools.atlas_json_shards --source data/encyclopedia/quests/quests_enriched.json --output .cache/dofus_atlas/quests_shards
py -3.13 -m tools.atlas_json_shards --verify-only
```

Le rapport local doit confirmer **tous les JSON réellement suivis dans le checkout exact**, les SHA-256 des octets matérialisés, la présence des sources LFS, les contrats déclarés et les références lexicales **non prouvées**. Une différence de compte nécessite enquête, pas correction cosmétique des statistiques. Les producteurs, consommateurs et états runtime ne sont **pas** certifiés par une simple recherche de chaînes : Graphify/Doctor et les tests de parcours demeurent requis.

**Critères bloquants avant fusion #157** : parité données/IDs, comportement Guide/Quêtes/Succès/Équipement/Craft, versions et rollback, mémoire et latence Windows comparables, CI ciblées vertes puis certification officielle au SHA final. Les runs SKIPPED/NOT_RUN ne valent pas PASS. La PR #153 (nouveau lot 5) reste indépendante, non fusionnable avant clôture du lot 4.
