# Configuration initiale — Dofus Atlas App

Ce document accompagne la PR #159. Il ne doit PAS être interprété comme une
autorisation de publier tant que les tests d'installation Windows n'ont pas passé.

## Dépôt secondaire

Créer une seule fois le dépôt public `r9327/Dof-Atlas-App` avec sa branche
`main`. Le dépôt source `r9327/Dof-Atlas` reste la source de vérité.
Le script `scripts/windows/export_app_repository.py` produit les fichiers
runtime sous une provenance SHA exacte ; aucune édition manuelle du code
copié n'est prévue. Les ressources volumineuses sont intégrées au bundle
GitHub Releases depuis le dépôt source, indépendamment de l'arborescence Git
publique minimale du second dépôt.

## Permissions Actions

Configurer, dans les **secrets Actions du dépôt source**, un jeton GitHub
à permissions minimales, limité au dépôt `r9327/Dof-Atlas-App`, avec droit
`Contents: Read and write` (nom : `ATLAS_DISTRIBUTION_TOKEN`).
Ne jamais mettre ce jeton dans l'application ou le code.

Créer la variable Actions `ATLAS_DISTRIBUTION_ENABLED` avec la valeur
`false` par défaut. La mettre à `true` uniquement après validation de :
compilation Windows, intégrité manifeste, QtWebEngine, workers, migration des
profils, installation vierge, reconnexion réseau, interruption et rollback.

Le workflow distribue uniquement après la réussite de la certification
`Phase Certification` de la branche `main` sur le SHA courant exact.

## Fonctionnement

Un seul exécutable exposé à l'utilisateur : `DofusAtlas.exe` (launcher).
L'application `AtlasApp.exe` est stockée sous le dossier des versions et
n'est pas proposée comme raccourci. Les données utilisateur résident dans
`%LOCALAPPDATA%/DofusAtlas/user`, hors des dossiers remplacés.

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

## Évolution intégrée sur la PR #159 (non publiée)

Les releases futures peuvent inclure dans `atlas-manifest.json` les champs
`launcher_sha256` et `launcher_size`. Un `DofusAtlasMaintenance.exe` est
installé silencieusement à côté du launcher initial, sans deuxième raccourci.
Il attend la fermeture du launcher en cours, conserve
`DofusAtlas.exe.previous` puis applique un remplacement atomique vérifié.
Les releases historiques sans ces champs continuent de fonctionner.

Les releases peuvent aussi inclure un bloc `delta` avec SHA de la version
précédente, liste des fichiers modifiés et SHA-256/poids de `atlas-delta.zip`.
Le client ne l'utilise que si le slot local correspond exactement à la version
de base. Chaque fichier réutilisé est vérifié contre le nouveau manifeste.
En cas d'échec, le ZIP intégral constitue la voie de secours. Cela diminue
la quantité téléchargée, sans mettre à jour les fichiers d'un processus actif.

**Limites actuelles :** la diffusion de JSON indépendamment de la compilation
Windows n'est pas encore branchée à un canal de publication dédié. La
certification intégrale du bundle Windows (LFS, workers, QtWebEngine, PC vierge)
et les droits de redistribution doivent toujours être validés. La variable
`ATLAS_DISTRIBUTION_ENABLED` doit rester à `false` jusque-là.
