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
- `local_dofus_data/` : accès local aux données Dofus utilisées par le runtime.
- `data/`, `config/` : données applicatives, métier et configuration ; distinguer source canonique, données utilisateur persistantes et runtime généré.
- `tools/`, `scripts/` : audits, gates, budgets, certification et maintenance du dépôt.
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

`.ai/context_index.json` contient des empreintes Git compactes de **tout le niveau racine du dépôt**, fichiers et répertoires compris. Chaque sous-arbre est représenté par son SHA Git : créer, modifier, supprimer ou renommer un fichier n'importe où sous ce sous-arbre change donc automatiquement l'empreinte correspondante.

Seul `.ai/` est exclu de l'empreinte pour éviter que `context_index.json` se référence lui-même. L'index ne contient pas une liste de dizaines de milliers de fichiers.

Le hook `pre-commit` le régénère automatiquement à partir de l'arbre réellement staged. Ne pas l'éditer manuellement.

## Routage et impact

Utiliser :

```powershell
py -3.13 -m tools.ai_context route app/modules/encyclopedia/views/guides_view.py
```

ou plusieurs chemins à la fois. La commande indique :

- le domaine concerné ;
- les documents de contexte utiles ;
- les ancres canoniques existantes à relire ;
- les tests ciblés existants les plus pertinents.

Les recommandations sont une aide au ciblage. Elles ne remplacent pas la recherche réelle des imports, appels, consommateurs et contrats.

Pour repérer un nouveau chemin que le routeur ne sait pas encore classer :

```powershell
py -3.13 -m tools.ai_context drift
```

Un chemin non classé produit un warning à examiner. Il ne bloque pas automatiquement une évolution légitime. Un index manquant ou périmé reste en revanche une erreur de cohérence.
