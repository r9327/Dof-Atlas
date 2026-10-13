# Lot 4 — Découpage intelligent et accès ciblé à tous les JSON

**Statut : préparation détaillée uniquement — AUCUNE migration de données réalisée dans cette PR de préparation. Non certifié, non fusionné.**

**Ordre contractuel actualisé (13/10/2026) :** Lot 1 **#152** → Lot 2 **#150** → Lot 3 **#151** → **Lot 4 (cette PR)** → Lot 5 **#153** (ex-lot 4, CI intelligente/certification finale). La PR **#156** est un micro-correctif existant d'accès aux prérequis Quêtes à reprendre/réconcilier, et **n'est pas une preuve de partitionnement physique**.

## Précondition obligatoire : reprise exacte des lots antérieurs

- [ ] Lire le **HEAD réel** de `main` et des PR liées avant toute intervention. Vérifier les merges de #152/#150/#151 avec commits et validations **réels**. En cas d'écart ou de correction encore ouverte, reprendre/intégrer les correctifs de leurs branches au bon endroit **avant** de commencer la migration du lot 4 ; ne rien écraser ni rejouer aveuglément.
- [ ] Recenser les APIs, caches et optimisations acquis en lots 1–3 : index Quêtes par offsets, cache SQLite des détails, catalogue/index Succès avec lecture partielle, loaders lazy et tests/certification adaptative ; les conserver. Lire le diff et les validations de #156 avant de décider de reprendre sa lecture bornée ; éviter deux moteurs concurrents.
- [ ] Construire et conserver un comparatif exact-SHA des comportements Quêtes/Succès/Guide, RAM/latence Windows et des contrats de progression avant migration. Rebaser depuis le `main` intégrant les prédécesseurs ; ne pas utiliser un historique périmé ni déclarer les anciens PASS sur un nouveau SHA.
- [ ] Ne **pas** démarrer le lot 5 (#153) comme clôture finale avant intégration et certification du lot 4. Après lot 4, actualiser/revalider les preuves de #153 ; les anciennes FULL ne prouvent pas un nouveau format de données.

## Objectif et règle de décision

Faire l'inventaire de **100 % des fichiers JSON et de leurs producteurs/consommateurs**, supprimer les lectures intégrales inutiles des données volumineuses, puis **découper physiquement seulement les ensembles pour lesquels cela améliore réellement la charge, les mises à jour ou la maintenabilité**. Ne pas transformer de petits fichiers en milliers de micro-fichiers. Ne pas reconstruire les systèmes existants qui font déjà le travail.

**Critères de choix par jeu de données** :
1. Si petit, consommé entier, ou fichier persistant utilisateur → **conserver tel quel**.
2. Si gros mais accès ponctuel par ID → **index existant par offsets/SQLite** en premier ; si insuffisant, partitions stables et index léger.
3. Si lecture séquentielle ou reconstruction → source canonique monolithique autorisée côté générateur/offline, mais runtime lit un index/des unités ciblées ; pas de préchargement déguisé.
4. Si recherche/filtrage multi-ensembles → index dédié compact (recherche, relations, progression), construit offline et chargé à la demande.
5. Avant tout changement de représentation → profilage d'usage et justification documentée ; choisir entre index, SQLite, JSONL, shards JSON. Le nom « découpage » **ne doit pas dégrader** les temps d'ouverture, la RAM, les tests ni multiplier les accès disque Windows.

## L4.1 — Audit exhaustif, classification et carte de dépendances

- [ ] Inventorier automatiquement tout `*.json` du dépôt (y compris données métiers, objets, recettes, ressources, monstres, équipements, quêtes, succès, guides, images, bestiaire, cartes et autres familles présentes), sans se limiter à l'Encyclopédie ; exclure explicitement seulement fichiers temporaires/générés externes justifiés.
- [ ] Établir pour chacun : chemin, taille, nombre d'objets, schéma et version, clés/IDs, fréquence de lecture, cas d'usage UI vs offline, producteur, consommateurs réels (imports, chemins dynamiques, outils, build, tests), statut source vs cache, écritures atomiques, présence de données utilisateur.
- [ ] Employer **Graphify exact-SHA** et Doctor pour cartographier les dépendances, puis confirmer les accès dans le code, les requêtes et les scénarios runtime. Ne jamais conclure « inutilisé » à partir d'une simple absence de lien AST ; aucune suppression sans preuve.
- [ ] Produire une **matrice de décision par fichier/famille** : `KEEP`, `INDEX_ONLY`, `SPLIT`, `ALREADY_OPTIMIZED`, `REVIEW`, avec raison, coût connu, taille avant/après et risque. Fichiers non mesurés = `NOT_MEASURED`, jamais optimisation prétendue.
- [ ] Déterminer la propriété des IDs, collisions, références croisées et sources canoniques avant de choisir une clé de partition.

## L4.2 — Stratégie par domaine, sans découpage aveugle

- **Quêtes :** examiner `data/encyclopedia/quests/quests_enriched.json` (~72,3 Mo) et `image_manifest.json` (~28,2 Mo) ; préserver identifiants, prérequis, critères, étapes, dialogues, liens Guide et enrichissement. Réutiliser d'abord `QuestSources`/offsets et le cache SQLite du détail. Si `SPLIT` prouvé utile, shards déterministes par **ID stable de quête** (lots bornés en taille, non 1 fichier par quête) + index `quest_id → shard/emplacement`, champs et recherche dissociés selon usages ; adaptateurs de lecture rétrocompatibles. Modifier aussi les **producteurs** tels que `enrich_quests.py` après vérification de leur chemin réel.
- **Succès :** conserver le catalogue compact et la lecture partielle déjà implémentés. Si nécessaire, découper **par ID de succès** avec index des catégories, sous-succès, objectifs, quêtes requises et liens Guide ; jamais de partition exclusivement par catégorie lorsque les références se croisent. Tester progression, recherche, déverrouillage et détail.
- **Métiers, recettes, objets, équipements, ressources :** inventorier les fichiers réels, puis accès par métier/type + ID de recette/objet, avec index inverses des ingrédients et produits et filtres de niveau. Ne pas charger toutes les recettes pour une seule fiche ; maintenir les liens item↔recette↔métier↔ressource et les données nécessaires au Craft/Équipement.
- **Monstres, bestiaire, zones et cartes :** index stable par ID de monstre/zone et références croisées aux succès, ressources et guides ; partitions pertinentes selon volume et usage mesuré, pas seulement l'arborescence visuelle.
- **Guide Ultime et Lanyel :** les ~189 petits JSON manuels signalés dans #156 restent **non fragmentés par défaut** ; conserver l'ordre, les lignes, les combats, étapes, prérequis et liens. Optimiser uniquement les index/caches transversaux réellement trop lourds.
- **Manifestes images et autres grands index :** index URL/SHA/ID ou partitions hash déterministes **si besoin mesuré**, consultation ciblée côté outil de génération, pas de chargement complet dans l'UI. Ne jamais déplacer simplement le coût en scan de shards.
- **JSON de configuration, état joueur, progression, locaux, schémas de test et petits fichiers :** schéma/chemin inchangés par défaut, écriture atomique conservée, aucune perte de données utilisateurs. Découpage uniquement avec cas d'usage prouvé et migration explicite.

## L4.3 — Format cible, générateurs et migration réversible

- [ ] Garder **une seule source de vérité** et un pipeline déterministe idempotent `source → normalisation/validation → index/partitions dérivés`. Séparer fichiers d'édition/source et données runtime ; ne pas maintenir deux sources modifiables en parallèle.
- [ ] Définir un manifeste versionné et léger par famille : `schema_version`, version générateur, hash source, nombre d'enregistrements, hash/tailles par shard, clés stables, clé→shard (et offset quand pertinent), signature de dépendances/caches. Respecter l'encodage UTF-8 et les chemins Windows.
- [ ] Choisir les tailles de shards **sur mesures** (pas de seuil universel) ; éviter autant les monolithes réhydratés que 10 000 petits fichiers. Utiliser cache de taille bornée et chargement à la demande ; index mmap/offset/SQLite existants préférés si plus simples et plus rapides.
- [ ] Migrer **producteurs ET consommateurs** avec un lecteur canonique/adaptateur temporaire compatible ancien/nouveau format ; compatibilité du chemin de génération, des CI, des outils de mise à jour et des usages embarqués/exécutables.
- [ ] Opérations dry-run, inventaire/diff et validation avant écriture ; publication atomique d'un jeu cohérent (répertoire/version temporaire puis bascule du manifeste), sauvegarde/rollback, refus explicite des versions incompatibles. Jamais de données partiellement migrées, de shards manquants silencieusement ou de récupération en fond qui cache le coût.
- [ ] Cache invalidé sur contenu **et** version générateur/format ; corriger le risque de cache stale en cas d'update partielle, sans reconstruire au démarrage lorsque les dérivés valides existent.
- [ ] Conserver les monolithes canoniques tant que la migration n'a pas démontré sa parité complète. Ne retirer un ancien chemin qu'après la preuve d'absence de consommateurs et une fenêtre de compatibilité décidée.

## L4.4 — Validation data, comportement, temps et mémoire

- [ ] **Parité exhaustive** avant/après : nombre d'entités, ensemble d'IDs, champs et valeurs, unicité, ordre sémantique, `null` vs manquant, listes et doublons, références croisées, contenu source et données Guide, liens métiers/recettes/items/monstres ; rapport de diff canonique avec **zéro perte**. Tests property-based/cas limites si utiles.
- [ ] Lectures aléatoires d'IDs existants/absents, recherche globale, catalogues/détails, mises à jour incrémentales, caches froids/chauds, refresh, corruption/troncature, shard manquant, index périmé, collision, lecteur concurrent, permissions et retour arrière.
- [ ] Scénarios Windows/Python 3.13/PySide6 : Quêtes, Succès, Guide, Craft, Équipement, Bestiaire, recherche/navigation rapide et retour Home ; absence de blocage UI, persistence inchangée, RAM/process-tree mesurés et budgets **inchangés**.
- [ ] Mesurer temps **global** du premier lancement et de chaque interaction, CPU, I/O, taille sur disque, nombre de fichiers et consommation mémoire comparables à `main` avant/après, à froid et à chaud ; une accélération isolée qui décale le coût ailleurs n'est pas une réussite.
- [ ] Tests ciblés en développement, Doctor/AI Context/Graphify/Integrity selon diff ; **FULL officielle et Phase Certification exact-SHA à la fin uniquement**, après code stabilisé. Aucun `skipped` ou `NOT_RUN` déclaré `PASS`, ne pas multiplier les benches lourds par micro-commit.

## L4.5 — Livraison, intégration au lot 5

- [ ] Livraison attendue : **inventaire exhaustif**, matrice de décision, script(s) de génération/migration réversible, manifestes/index réels utiles, adaptateurs consommateur, tests de parité, rapports avant/après, documentation de maintenance et rollback.
- [ ] Prouver pour chaque famille : `KEEP / INDEX_ONLY / SPLIT`, source de vérité, consommateurs couverts, taille/temps/RAM mesurés, justification de non-découpage s'il y a lieu.
- [ ] Réconcilier **#156** : conserver ses changements validés par reprise propre/cherry-pick/merge selon diff et provenance ; fermer ou fusionner cette PR uniquement avec justification, sans deux implémentations parallèles.
- [ ] Après PASS exact-SHA et fusion du lot 4 sur `main`, **rebaser/actualiser le lot 5 (#153)**, vérifier conflits, règles Doctor CI, nouvelle couverture JSON, risques data, puis obtenir ses validations propres. Ne pas fusionner #153 avant cette reprise.

### Définition de terminé

- **100 % des JSON inventoriés et classés**, grands JSON optimisés/découpés quand le profil l'impose ; petits et données locales gardés raisonnablement intacts.
- **Parité intégrale**, relations croisées et progression préservées ; migration robuste et réversible ; performances et budgets RAM non dégradés.
- **Réutilisation des lots 1–3**, aucun retour en arrière de leur architecture, de leurs index, de leurs gates ou de leurs correctifs ; lien #156 traité.
- **Certifications requises au SHA final effectivement PASS** ; aucune preuve ancienne, faux positif ou succès présumé.

**Hors périmètre :** refonte complète des providers, nouvelle architecture de stockage parallèle « au cas où », refonte UI, modification des données du jeu, modification de la politique RAM/CI et fusion anticipée du lot 5.


## Implémentation initiale du 13/10 — micro-lots sur la PR #157

- [x] **Inventaire automatisé** `tools/atlas_json_inventory.py` sur tous les JSON suivis par Git, sans modifier les données. SHA-256, rôles déclarés (contrat des gros fichiers), consommateurs lexicaux explicitement NON prouvés, état LFS, décisions conservatrices `KEEP / INDEX_ONLY / ALREADY_OPTIMIZED / REVIEW`, `NOT_MEASURED` tant que non mesuré. Tests : `tests/test_atlas_json_inventory.py`.
- [x] **Générateur hors runtime** `tools/atlas_json_shards.py` : découpage dérivé `quests_enriched.json` par plages stables d'ID de quête (32 ID par partition par défaut) ; manifeste SHA source et SHA/tailles de chaque shard, index ID→shard, validation parité de toutes les valeurs, publication atomique d'un pointeur et versions conservées pour retour arrière. Réutilise `QuestSources` issu des lots précédents. Tests : `tests/test_atlas_json_shards.py`.
- [ ] Exécuter les tests et l'inventaire sur le checkout complet (non disponibles depuis l'environnement GitHub-seul). Les tests et workflows qui n'ont pas abouti ne sont PAS PASS.
- [ ] Lire le rapport exhaustif pour classifier chaque famille, identifier les producteurs et lecteurs avec Graphify exact-SHA + preuves runtime, choisir les autres divisions réellement utiles.
- [ ] Réconcilier PR #156 et migrer les producteurs/consommateurs uniquement après parité et profils mesurés. Pas de connexion runtime aux shards à ce stade ; la source reste canonique et les caches Quêtes/Succès existants demeurent actifs.
- [ ] Mesurer des gains réels Windows (temps premier détail, I/O, RSS, RAM) et certifier le SHA final avant merge, puis reprendre le lot 5 #153.

Commandes ciblées (pas de FULL pendant développement) :

```powershell
py -3.13 -m unittest tests.test_atlas_json_inventory tests.test_atlas_json_shards
py -3.13 -m tools.atlas_json_inventory --output artifacts/lot4/json_inventory.json
py -3.13 -m tools.atlas_json_shards --source data/encyclopedia/quests/quests_enriched.json --output .cache/dofus_atlas/quests_shards
py -3.13 -m tools.atlas_json_shards --verify-only
```

Le générateur produit une **représentation dérivée expérimentale**, pas encore un gain produit ni un changement d'interface de lecture. Les JSON métiers, Succès, Guides et manifestes restent à classifier et traiter selon usage réel, pas par principe.


## Avancement technique — garde-fous de perte de données et mesure comparative

- Le contrôle `_reject_duplicate_json_keys` de `tools/atlas_json_shards.py` passe en flux sur le JSON canonique **hors runtime** (256 Kio/lecture) et refuse les membres répétés à toute profondeur avant publication, y compris les IDs échappés JSON ou masqués par un index d'offsets antérieur. Les données canoniques ne sont pas modifiées. Les tests sont dans `tests/test_atlas_json_shards.py`.
- `tools/atlas_json_benchmark.py` compare sur un échantillon déterministe d'IDs les lectures du `QuestSources` préexistant avec `read_by_id` des partitions. Le contrôle de parité complète est préalable au chronométrage. Il mesure distinctement vérification, initialisation des offsets et lectures, sans déduire de RAM applicative ni de vitesse de démarrage à partir de ce seul résultat.
- **Garde de décision** : ne pas migrer l'UI vers les shards par principe. Le moteur existant lit déjà directement le JSON par offsets et met les détails en cache SQLite ; un shard de 32 quêtes peut au contraire désérialiser davantage qu'un seul détail demandé. Choisir `INDEX_ONLY` tant qu'une amélioration nette et reproductible du cas réel n'a pas été démontrée. Il n'existe pas encore de chiffre de comparaison Windows certifié pour cette nouvelle branche.
- Aucun nouveau format n'est imposé aux fichiers Métiers, Succès, Guide et progression qui ont déjà un stockage ou un chargement approprié. Pas de suppression des monolithes canoniques.

Commandes ciblées, **uniquement une fois le checkout à jour** :

```powershell
py -3.13 -m unittest -v tests.test_atlas_json_shards tests.test_atlas_json_inventory tests.test_atlas_json_benchmark tests.test_guide_prerequisite_lookup
py -3.13 -m tools.atlas_json_inventory --output artifacts/lot4/json_inventory.json
py -3.13 -m tools.atlas_json_shards --output .cache/dofus_atlas/quests_shards
py -3.13 -m tools.atlas_json_benchmark --shards .cache/dofus_atlas/quests_shards --sample-count 64 --output artifacts/lot4/json_comparison.json
```

Cette section documente du **code poussé**, pas un PASS des tests, ni une preuve de gain RAM/latence. La FULL n'est légitime qu'au candidat stabilisé après les corrections ciblées et les checks indépendants.
