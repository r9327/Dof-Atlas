# Dofus Atlas — fichiers IA générés

`context_index.json` est généré par `py -3.13 -m tools.ai_context sync` et automatiquement resynchronisé par le hook `pre-commit`.

Il stocke une empreinte Git compacte de chaque entrée du niveau racine du dépôt. Pour un répertoire, son SHA de tree change dès qu'un fichier suivi est créé, modifié, supprimé ou renommé n'importe où dessous.

`.ai/` est volontairement exclu de l'empreinte pour éviter une auto-référence de `context_index.json`.

Ne pas éditer `context_index.json` manuellement.

## Manifests de scopes

`context-map.yaml` référence un manifest sous `.ai/scopes/` pour chaque scope ROAD IA V2.

Chaque manifest reste compact et descriptif :

- `scope` et `kind` identifient le domaine ;
- `working_set` contient les ancres à examiner en premier ;
- `shared_dependencies` référence uniquement des scopes `shared_infrastructure` déjà déclarés dans `context-map.yaml` ;
- `context_entries` contient les fichiers voisins utiles à comprendre le scope sans les déclarer propriétaires du domaine ;
- `implementation: placeholder` est conservé lorsqu'une surface n'a pas encore d'implémentation canonique dédiée.

Ces manifests ne remplacent ni les sources de vérité produit, ni les guardrails, ni `atlas_integrity`. Le routage explicite des règles existantes appartient à ROAD IA V2-5.
