# Atlas Guides — contrat technique des actions hors ligne

> Document de compatibilité du moteur universel, conservé sous ce chemin historique
> parce que la PR #363 y fait référence. **Il ne définit ni une méthode de rédaction
> manuelle ni une certification de parcours.**

## Répartition des responsabilités

- **PR #337 (architecture)** : catalogue, modèle de fiche, projection ordonnée
  `project_ganymede_authored_cards`, lecteur partagé `SharedGuideManualView/Card`,
  navigation, copies exactes, préparation, combats, progression persistante
  par `character:<id_dofus>` et validation spécifique à chaque parcours.
- **PR #363 (contenu)** : extraction depuis des sources autorisées, reconstruction,
  import transactionnel, comparaison indépendante étape par étape, droits,
  publication et certification individuelle des routes.
- `guide_complet` et `dofus_sylvestre` conservent leur comportement et leurs
  données canoniques. Aucune deuxième interface ou source de progression.

## Interface de données existante

Le chargeur `app/modules/encyclopedia/views/guide_library_sources.py`
définit la validation **structurelle** de `ganymede_<source_guide_id>_instructions.json`.
Le projecteur situé dans
`app/modules/encyclopedia/services/guide_catalog_manual_runtime_service.py`
transforme ses étapes en fiches communes. Le code actuel fait foi si un
champ ou une limite diffère de ce résumé.

Pour chaque route : `schema_version=1`, `source_guide_id` numérique,
`source_url` conforme à l'inventaire, `expected_source_step_count`,
`rights_basis` et `steps` ordonnées sans trou. Une étape contient
`source_step_number`, `title`, `instructions` et une liste non vide
d'`actions` typées.

Types actuellement reconnus : `travel`, `talk`, `interact`, `fight`,
`prepare`, `use_item`, `deliver`, `craft`, `information`.
Une action contient `kind` et `text`, et peut porter `coordinates`
(deux entiers), `copy_values` (liste bornée de textes exacts) et
`items` (objets structurés avec leur nom et les métadonnées fournies,
notamment quantité). La projection doit conserver **chaque action dans
l'ordre**, les coordonnées et les champs structurés sans les réinventer
ou les déduire d'une phrase.

Les champs de copie et les positions sont rendus par le composant
universel ; les styles et couleurs sont ceux d'Atlas, pas ceux d'un
éditeur de routes. La progression et la validation appartiennent au
guide et au personnage, et ne se déduisent jamais d'un JSON chargé.

## Limites et conditions de livraison

Un JSON complet, des empreintes SHA ou des tests de structure ne prouvent
**ni** que les actions correspondent à la source, **ni** qu'elles fonctionnent
dans DOFUS. Les 15 anciennes consignes et 5 brouillons historiquement
ajoutés à #337 sont **non certifiés** et doivent sortir de cette PR après
l'analyse Graphify exact-SHA des consommateurs. Ils ne sont pas une
référence de vérité pour #363.

Au HEAD du 2 novembre 2026, l'ancien lecteur de consignes peut encore
présenter ces fichiers ; sa neutralisation/remplacement et le retrait
du contenu restent **TODO**, sans statut PASS implicite. Ne pas supprimer
le code, les archives legacy ou les données utilisateur à l'aveugle.

Les contrôles à réaliser avant Ready : Graphify exact-SHA pour le nettoyage
structurel, Doctor `agent plan --structural`, `agent check`,
`agent validate`, tests ciblés Qt/contrat/progression/export, benchmark
puis revue logique des commits et audit global. La Phase CI officielle
reste distincte et intervient sur le candidat final.

Pour la chaîne de collecte et de validation indépendante, voir
`docs/guides/ATLAS_GUIDE_IMPORTER.md` **dans la PR #363**.
