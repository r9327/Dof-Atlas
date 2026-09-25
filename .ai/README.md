# Dofus Atlas — fichiers IA générés

`context_index.json` est généré par `py -3.13 -m tools.ai_context sync` et automatiquement resynchronisé par le hook `pre-commit`.

Il stocke des empreintes Git compactes des grandes zones du dépôt. Une modification, création, suppression ou renommage dans une zone suivie change son empreinte.

Ne pas éditer `context_index.json` manuellement.
