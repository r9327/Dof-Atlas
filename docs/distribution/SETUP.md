# Configuration initiale — Dofus Atlas App

Ce document accompagne la PR #159. Il ne doit PAS être interprété comme une
autorisation de publier tant que les tests d'installation Windows n'ont pas passé.

## Dépôt secondaire

Créer une seule fois le dépôt public \`r9327/Dof-Atlas-App\` avec sa branche
\`main\`. Le dépôt source \`r9327/Dof-Atlas\` reste la source de vérité.
Le script \`scripts/windows/export_app_repository.py\` produit les fichiers
runtime sous une provenance SHA exacte ; aucune édition manuelle du code
copié n'est prévue. Les ressources volumineuses sont intégrées au bundle
GitHub Releases depuis le dépôt source, indépendamment de l'arborescence Git
publique minimale du second dépôt.

## Permissions Actions

Configurer, dans les **secrets Actions du dépôt source**, un jeton GitHub
à permissions minimales, limité au dépôt \`r9327/Dof-Atlas-App\`, avec droit
\`Contents: Read and write\` (nom : \`ATLAS_DISTRIBUTION_TOKEN\`).
Ne jamais mettre ce jeton dans l'application ou le code.

Créer la variable Actions \`ATLAS_DISTRIBUTION_ENABLED\` avec la valeur
\`false\` par défaut. La mettre à \`true\` uniquement après validation de :
compilation Windows, intégrité manifeste, QtWebEngine, workers, migration des
profils, installation vierge, reconnexion réseau, interruption et rollback.

Le workflow distribue uniquement après la réussite de la certification
\`Phase Certification\` de la branche \`main\` sur le SHA courant exact.

## Fonctionnement

Un seul exécutable exposé à l'utilisateur : \`DofusAtlas.exe\` (launcher).
L'application \`AtlasApp.exe\` est stockée sous le dossier des versions et
n'est pas proposée comme raccourci. Les données utilisateur résident dans
\`%LOCALAPPDATA%/DofusAtlas/user\`, hors des dossiers remplacés.

Les builds manuels produisent des artefacts candidats, **jamais** une Release
stable automatique. Le second dépôt et la variable d'activation n'ont pas
encore été créés/configurés par cette PR.

## Limites initiales connues

- Versionnement app/data présent dans le manifeste ; diffusion incrémentale
  de jeux de données autonomes et migrations de schéma à implémenter.
- ZIP de version complète actuellement téléchargé par l'updater ; les
  téléchargements différentiels restent à développer après stabilité.
- La présence des fichiers QtWebEngine ne suffit pas à certifier une session
  complète : faire un smoke test réel de fenêtre et des workers sur Windows.
- Valider droits de redistribution et volume des assets Dofus avant publication.
