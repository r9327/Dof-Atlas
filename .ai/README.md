# Dofus Atlas — fichiers IA générés

`context_index.json` est généré par `py -3.13 -m tools.ai_context sync` et automatiquement resynchronisé par le hook `pre-commit`.

Il stocke une empreinte Git compacte de chaque entrée du niveau racine du dépôt. Pour un répertoire, son SHA de tree change dès qu'un fichier suivi est créé, modifié, supprimé ou renommé n'importe où dessous.

`.ai/` est volontairement exclu de l'empreinte pour éviter une auto-référence de `context_index.json`.

Ne pas éditer `context_index.json` manuellement.
