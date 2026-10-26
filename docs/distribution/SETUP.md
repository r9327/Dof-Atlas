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

## Parcours du lanceur unique

Le raccourci **Dofus Atlas** continue de pointer vers le même
`DofusAtlas.exe`. Le lanceur reste léger (Tkinter/stdlib) et vérifie le
**dernier paquet certifié publié sur GitHub Releases**, jamais le code brut
de `main` ou une PR. Le flux normal est automatique :

1. **Version identique** : contrôle rapide de la Release, aucun téléchargement
   ni écran de mise à jour ; démarrage direct d'`AtlasApp.exe`.
2. **Version publiée plus récente** : téléchargement du différentiel vérifié
   lorsque le SHA de base correspond à la version installée, vérification
   et installation transactionnelle ; secours par archive complète si
   le différentiel ne peut pas être appliqué.
3. **GitHub inaccessible** : lancement de la dernière version locale viable,
   sans effacer les données de l'utilisateur.
4. **Après démarrage d'Atlas** : l'écran de préchargement Qt affiche l'état
   réel des Quêtes, Guides/Succès et Craft. Il reprend la même palette que
   le lanceur, sans refaire une seconde fois les opérations de chargement.
5. **Nouveau lanceur disponible** : remplacement automatique signé par
   empreinte SHA-256 via le helper de maintenance après activation saine.
   Le raccourci ne change jamais.

Sur un démarrage normal sans mise à jour, le lanceur reste masqué : seul le
préchargement propre à l'application est visible. Pendant une installation ou
un téléchargement, son interface présente les phases et le progrès réels.
Les profils, personnages et progressions résident hors des slots remplaçables.
Aucune mise à jour ne doit provenir d'un simple push non certifié.

**Dépendance de publication :** la synchronisation DEV → APP ne rend pas
automatiquement une version téléchargeable. La Release stable est créée
uniquement après un résultat `Phase Certification` réussi sur le SHA exact
et quand `ATLAS_DISTRIBUTION_ENABLED=true` avec un jeton de publication
valide. Un échec de CI bloque donc volontairement les mises à jour du lanceur.
Ne pas contourner ce garde-fou pour débloquer une mise à jour.

## Fonctionnement

Un seul exécutable exposé à l'utilisateur : `DofusAtlas.exe` (launcher).
L'application `AtlasApp.exe` est stockée sous le dossier des versions et
n'est pas proposée comme raccourci. Les données utilisateur résident dans
`%LOCALAPPDATA%/DofusAtlas/user`, hors des dossiers remplacés.

Les builds manuels produisent des artefacts candidats, **jamais** une Release
stable automatique. Le dépôt secondaire et le jeton restent à configurer.

## État de certification du candidat

La validation Windows complète de la PR #159, SHA exact
`c3c4dab331d5bff6429e9ac90afc71b1e4dc0e36`, est **PASS** :
https://github.com/r9327/Dof-Atlas/actions/runs/38521409821

Elle a vérifié les ressources Git LFS complètes, l'application et les workers
gelés, le bootstrap du launcher, l'installateur, le raccourci Bureau, le
démarrage d'une vraie fenêtre Qt, les archives ZIP et l'intégrité SHA-256
de chaque morceau. Le ZIP original dépassait la limite d'un seul asset
GitHub Releases de 2 Gio : le protocole multipart
`atlas-windows.part0001`, `part0002`, etc. est maintenant en place.
Le downloader reconstitue un ZIP après contrôle des SHA de chaque morceau
et de l'archive complète, avec reprise HTTP. Les petites releases avec un
seul ZIP restent compatibles.

Le candidat complet est accessible dans les artefacts de ce run (7 jours de
rétention, expiration le 21 octobre 2026) ; il ne constitue **pas** une
publication stable ni la preuve d'un vrai upgrade sur un PC utilisateur.

## Mise en service : opérations manuelles obligatoires

1. Depuis https://github.com/new, créer **public**
   `r9327/Dof-Atlas-App` avec `main` initialisée (README suffit).
   Ne pas copier les outils Doctor/Graphify ni les fichiers de développement.
2. Dans GitHub, créer un **fine-grained personal access token** réservé
   uniquement à `r9327/Dof-Atlas-App`, permission Repository
   `Contents: Read and write`. Ne jamais inclure ce jeton dans le code.
3. Dans **r9327/Dof-Atlas → Settings → Secrets and variables → Actions**,
   ajouter le Repository secret `ATLAS_DISTRIBUTION_TOKEN`.
   Ajouter la Repository variable `ATLAS_DISTRIBUTION_ENABLED=false` :
   la publication stable doit rester désactivée.
4. Préparer un essai sur Windows avec les fichiers candidats. Confirmer
   l'installation depuis un profil vierge, l'import d'un dossier `DOFUS.bat`,
   la conservation des progressions/profils et le démarrage des onglets métier.
   Simuler une coupure réseau, un téléchargement interrompu, puis une mise à
   jour cassée pour observer la restauration de la version précédente.
5. Confirmer les **droits de redistribution** des ressources Dofus et
   les limites des assets, puis fusionner la PR quand toutes ces validations
   ont passé. Ne passer `ATLAS_DISTRIBUTION_ENABLED=true` qu'après
   validation : le workflow publiera uniquement après une certification
   réussie de `main` au SHA exact en cours.

En l'absence du secret, du dépôt ou de sa branche `main`, le contrôle
`classify-release` échoue **avant le build Windows coûteux**, sans
publier de Release.

## Limites restantes

- La branche JSON-only et les téléchargements différentiels sont testés
  avec des paquets synthétiques mais pas encore validés par une paire de
  releases publiques réelles.
- Une réussite CI sur Windows Server ne remplace pas une installation/
  mise à jour réelle sur le PC utilisateur.
- Toute future migration du schéma des profils/données doit être versionnée
  et testée, sans écraser les données personnelles.
- Les droits de redistribution des ressources Dofus restent à confirmer.

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

**JSON indépendants du binaire :** lorsqu'un commit certifié sur `main`
ne modifie que les JSON publiables sous `data/`, le workflow choisit le job
`json-only-release` au lieu du build PyInstaller. Il repart du bundle Windows
déjà certifié, vérifie ses fichiers contre le manifeste, applique uniquement
les JSON modifiés, puis génère le ZIP complet et le différentiel. L'exécutable
compilé et l'installateur sont réutilisés sans recompilation. Un changement de
Python, schéma ou code déclenche le chemin de build classique.

**Limites actuelles :** cette voie est implémentée et testée sur des paquets
synthétiques, mais pas encore certifiée sur une Release de production.
La certification intégrale Windows (LFS, workers, QtWebEngine, PC vierge),
la compatibilité métier détaillée des JSON et les droits de redistribution
restent à valider. La variable `ATLAS_DISTRIBUTION_ENABLED` doit rester
à `false` jusque-là.

## Import de l'ancienne installation Python

L'installateur prend en charge l'option facultative `--legacy-root "C:\\chemin\\ancien-atlas"`.
Il retrouve aussi l'ancien dossier automatiquement lorsque `DofusAtlasSetup.exe`
est lancé depuis un dossier contenant `DOFUS.bat`. Au premier lancement,
les fichiers personnels existants (profils, progressions, préférences,
itinéraires) sont importés sans écraser ceux déjà présents dans
`%LOCALAPPDATA%/DofusAtlas/user`. Les versions compilées et leurs
ressources restent séparées. L'import ne transforme pas les schémas
métiers : toute évolution future nécessitera une migration versionnée,
testée, avec sauvegarde préalable.


## Certification du transfert (Doctor + Graphify restent côté développement)

La liste de transfert est une **allowlist révisable** dans
`scripts/windows/export_app_repository.py`. Seuls les points d'entrée Python,
les modules runtime `app/*.py` et `local_dofus_data/*.py` (hors dossiers
`tools`), les JSON/DB/INI des domaines de données autorisés et les icônes
essentielles vont dans le second dépôt. Aucun outil Doctor/Graphify, rapport
d'audit, test, capture de débogage, profil utilisateur ou secret n'est transféré.

`python -m scripts.windows.certify_app_export --root . --destination app-publish
--source-sha <HEAD> --output artifacts/atlas-transfer-certificate.json`

Le certificat créé **dans le dépôt de développement** vérifie les noms exacts,
la provenance SHA, tous les fichiers et leurs SHA-256, l'absence de fichiers
imprévus et les imports Python statiques entre fichiers publiables. Une erreur
bloque le push ; elle ne se transforme pas en avertissement vert.

Il s'agit d'une certification **spécifique au transfert** à base d'inventaire
Doctor et de dépendances AST de type Graphify. Elle **ne prétend pas** être une
nouvelle exécution complète de Doctor/Graphify, ni prouver les imports
dynamiques, callbacks Qt, assets LFS de la Release ou comportement runtime.
Les contrôles Doctor, Graphify, Phase Certification et les tests Windows
restent indépendants dans le dépôt source. Aucun de ces outils n'est exécuté
par le dépôt secondaire.

La publication stable demeure désactivée pendant la mise en service.


Le job PR `Focused updater contracts` effectue aussi un **export réel non publié** dans le dossier temporaire du runner, matérialise uniquement le logo LFS requis et exécute le certificat sur le résultat avant tout push. Cela contrôle directement la sélection sur les vrais fichiers du commit.

### Certificat sur chaque PR (sans copie dans le dépôt App)

Le job ciblé **Focused updater + transfer contracts** construit un export temporaire sur le **HEAD exact de la PR** (et non sur un commit de fusion GitHub), exécute le certificat statique et vérifie les empreintes SHA-256 et les chemins. Son résultat se trouve dans le résumé GitHub Actions ; le JSON `atlas-app-transfer-<SHA>` est téléchargeable comme artefact de la CI.

Il ne pousse rien vers le dépôt de distribution et ne contient **ni Doctor, ni Graphify**, seulement leurs principes de contrôle d'inventaire et de graphe. Une destination symbolique ou un SHA incohérent bloque explicitement la certification. Les contrôles Doctor/Graphify et la compilation Windows sont toujours séparés.

## Choix du disque et vérification rapide

Le `DofusAtlasSetup.exe` interactif propose de choisir le dossier des fichiers
volumineux avant le premier téléchargement. Le petit lanceur et les profils
restent dans LocalAppData, mais les archives téléchargées et les versions
complètes sont stockées sur le disque choisi.

Les installations antérieures sans `installation.json` voient une seule fois
ce choix au lancement suivant. Pour changer de disque plus tard, relancer le
Setup ou lancer `DofusAtlas.exe --atlas-configure`. Si une version existe
déjà, elle est copiée vers le nouveau disque sans re-téléchargement. L'ancien
dossier est préservé pour reprise en cas de problème : ne le supprimer
manuellement qu'après validation du nouveau lancement et des modules.

Au démarrage ordinaire, le lanceur consulte la dernière version et contrôle
l'exécutable actif mais ne re-calcule plus tous les SHA-256 des fichiers
installés lorsqu'aucune mise à jour n'est disponible. Les nouvelles versions
et les fichiers différentiels restent intégralement vérifiés. Pour forcer
une inspection complète/réparation depuis Windows :
`DofusAtlas.exe --atlas-verify-install`.
