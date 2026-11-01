# Dofus Atlas

Dofus Atlas est une application Windows en Python/PySide6 qui réunit une
encyclopédie hors ligne, le suivi de progression, des guides et itinéraires,
des outils de cartographie et des fonctions d’assistance au jeu.

> **État du projet : développement actif.** Les contrats de données, les
> parcours Windows et la distribution évoluent encore. Une CI verte sur une
> pull request ne remplace pas la certification du SHA finalement fusionné.

## Fonctionnalités

- encyclopédie à chargement différé : quêtes, succès, équipements et données locales ;
- Guide Ultime structuré avec prérequis, navigation et progression persistante ;
- cartographie, trajets et raccourcis de zaaps ;
- gestion de personnages, équipements, artisanat et macros ;
- capture réseau optionnelle avec séparation explicite des privilèges ;
- Atlas Doctor et Graphify pour planifier, diagnostiquer et valider les changements.

## Prérequis

- Windows x64 ;
- CPython 3.13 ;
- les dépendances verrouillées dans `requirements-pyside.txt`.

Installation assistée :

```powershell
scripts\windows\Install_Dofus_Atlas.bat
```

Installation développeur :

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install --require-hashes --no-deps -r requirements-pyside.txt
```

Lancez ensuite `DOFUS.bat`. Le lanceur vérifie Python et les dépendances,
prépare les caches en arrière-plan, puis démarre l’application. Les journaux de
démarrage sont écrits dans `logs/start_log.txt`.

## Développer sans perdre de temps

Le point d’entrée commun aux humains et aux agents IA est
[`AI_ENTRYPOINT.md`](AI_ENTRYPOINT.md). Le cycle normal reste ciblé :

```powershell
py -3.13 -X utf8 -m tools.atlas_doctor agent plan <chemins> --base-ref HEAD --json
# modification bornée
py -3.13 -X utf8 -m tools.atlas_doctor agent check <chemins> --base-ref HEAD --run-tests --json
py -3.13 -X utf8 -m tools.atlas_doctor agent validate <chemins> --base-ref HEAD --json
```

N’exécutez pas FULL à chaque modification. Utilisez les tests ciblés et FAST
pendant le développement ; les gates larges et la certification exacte-SHA
restent réservées aux étapes prévues par [`PHASE_CERTIFICATION.md`](PHASE_CERTIFICATION.md).

Règles essentielles :

- ne jamais masquer un échec avec `skip`, `xfail`, ignore ou seuil affaibli ;
- ne jamais conclure qu’un fichier est mort à partir du graphe seul ;
- protéger les données utilisateur, notamment `data/local/zaaps.json` ;
- distinguer `PASS`, `REVIEW`, panne d’environnement et certification finale.

Consultez le [guide de contribution](docs/CONTRIBUTING.md) avant d’ouvrir une PR.

### RTK pour Codex (optionnel)

`tools/install_rtk.ps1` est un utilitaire **manuel** de configuration RTK,
non requis pour lancer Atlas, Doctor ou la CI et non destiné à une exécution
automatique par un agent. Pour une configuration limitée au projet, sur Windows :

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/install_rtk.ps1 -Project
```

Le script installe RTK et, sauf `-SkipRipgrep`, ripgrep via `winget` **uniquement
si ces commandes manquent**. Une installation requiert `winget` ; si les outils
sont déjà présents, `winget` n'est pas nécessaire. L'option `-Project`
configure Codex pour ce projet ; sans elle, `rtk init -g --codex` modifie
la configuration globale de Codex. À utiliser seulement sur demande explicite,
sans intégration au démarrage ni à la validation automatique.

## Documentation technique

- [`GRAPHIFY.md`](GRAPHIFY.md) — carte d’architecture et preuves structurelles ;
- [`DEVELOPMENT_GUARDRAILS.md`](DEVELOPMENT_GUARDRAILS.md) — garde-fous de développement ;
- [`PERFORMANCE_GUARDRAILS.md`](PERFORMANCE_GUARDRAILS.md) — budgets et règles de performance ;
- [`ZERO_TRUST_RULES.md`](ZERO_TRUST_RULES.md) — règles de preuve et de sécurité ;
- [`docs/distribution/SETUP.md`](docs/distribution/SETUP.md) — distribution Windows.
- [`docs/roadmap/GITHUB_OPEN_SOURCE_INTEGRATION_2026-10-31.md`](docs/roadmap/GITHUB_OPEN_SOURCE_INTEGRATION_2026-10-31.md) — audit de 29 projets GitHub, raccordement dans les modules existants, exclusions et validation avant adoption.

## Licence et marques

Aucune licence racine n’est publiée dans ce dépôt à ce jour. La visibilité
publique du code ne vaut donc pas autorisation générale de réutilisation ou de
redistribution. Dofus et les marques associées appartiennent à leurs titulaires
respectifs ; ce dépôt ne se présente pas comme un produit officiel.
