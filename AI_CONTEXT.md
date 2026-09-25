# Dofus Atlas — AI Context Router

Ce fichier est une **carte de navigation courte** pour les agents. Il ne remplace jamais `AGENTS.md`, `ZERO_TRUST_RULES.md`, `DEVELOPMENT_GUARDRAILS.md`, `PERFORMANCE_GUARDRAILS.md` ni `PHASE_CERTIFICATION.md`.

## Préflight standard

Pour toute tâche non triviale :

```powershell
git rev-parse HEAD
git status --short
git branch --show-current
git remote get-url origin
py -3.13 -m tools.ai_context status
```

Ensuite lire le code réellement concerné, rechercher ses appels/consommateurs et identifier la source de vérité avant de modifier quoi que ce soit.

## Carte rapide

- `main.py`, `launch.py`, `app/preload.py`, `app/background_work.py` : démarrage, orchestration et cycle de vie.
- `app/core/` : primitives et contrats métier centraux.
- `app/services/` : services applicatifs partagés ; préférer les services canoniques aux écritures directes depuis l'UI.
- `app/ui/`, `app/pages/` : shell et UI globale ; réutiliser thème et composants existants.
- `app/modules/encyclopedia/` : Quêtes, Succès, Guides, Bestiaire et logique Encyclopédie, séparée en modèles/providers/services/views/widgets.
- `data/` : données applicatives et métier ; distinguer source canonique, données utilisateur persistantes et runtime généré.
- `tools/` : audits, gates, budgets, certification et maintenance du dépôt.
- `tests/` : contrats de non-régression ; ne jamais les affaiblir pour rendre un lot vert.
- `.github/workflows/`, `.githooks/` : exécution CI et contrôles locaux.

## Règles à ne pas perdre de vue

- Cause racine avant patch de symptôme.
- Une seule source de vérité par donnée ou responsabilité métier.
- Progression/persistence partagée : `lock -> reload current -> mutate -> atomic write -> publish/invalidate -> unlock`.
- UI : cohérence globale, pas de deuxième interface légère/placeholder reconstruite en parallèle de l'UI finale.
- Performance : éviter le travail lourd inutile sur le thread Qt et les chargements globaux quand seul le contenu visible est nécessaire.
- Données Dofus : ne rien inventer ; vérifier les données actuelles et les identifiants.
- Guide Ultime manuel : respecter le manifeste et les chapitres canoniques définis par les guardrails.
- Une PR verte n'est pas une certification de phase ; le SHA exact doit passer le workflow de certification prévu.

## Index automatique

`.ai/context_index.json` contient uniquement des empreintes Git compactes des grandes zones (`app`, `data`, `tools`, `tests`, etc.) et de quelques fichiers root importants.

Il n'est pas destiné à être lu intégralement à chaque tâche. Il sert à prouver que le contexte correspond bien au contenu committé sans maintenir une liste géante de fichiers.

Le hook `pre-commit` le régénère automatiquement. Ne pas l'éditer manuellement.

## Routage

Utiliser :

```powershell
py -3.13 -m tools.ai_context route app/modules/encyclopedia/views/guides_view.py
```

ou plusieurs chemins à la fois. La commande indique les domaines et documents supplémentaires utiles ; elle ne remplace pas la recherche réelle des imports, appels, tests et consommateurs.
