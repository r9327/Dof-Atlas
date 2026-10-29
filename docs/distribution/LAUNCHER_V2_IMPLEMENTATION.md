# Launcher V2 — architecture réellement implémentée et limites vérifiables

Ce document décrit le **code candidat de la PR #285**. Il ne constitue ni un
certificat de performance ni une permission de publier la Release stable.
Le contrat et ses exigences numérotées restent dans
[`launcher-v2-startup-contract.md`](../performance/launcher-v2-startup-contract.md)
et dans l'issue #286. Le protocole de mesure est dans
[`launcher-v2-trace-lot1.md`](../performance/launcher-v2-trace-lot1.md).

## Flux de livraison DEV → APP

`r9327/Dof-Atlas` fournit le code source et exécute les contrôles Doctor,
Graphify, Phase Certification et Windows Distribution. Le job Windows
`ready_for_review` d'une PR autorisée produit uniquement des **artefacts
candidats**, contrôlés par le SHA exact du commit : il ne pousse ni code vers
APP ni Release stable. L'évènement `workflow_run` d'une Phase Certification
réussie sur `main`, si `ATLAS_DISTRIBUTION_ENABLED=true` et que les
contrôles de provenance passent, produit le build Windows, exporte le runtime
allowlisté vers `r9327/Dof-Atlas-App/main` et publie les fichiers dans une
Release **APP**, jamais DEV.

Fichiers de Release : `atlas-manifest.json`, `atlas-channel.json`,
`DofusAtlas.exe`, `DofusAtlasSetup.exe`, archive intégrale
`atlas-windows.zip` ou parties vérifiées `atlas-windows.part*`, et
éventuellement `atlas-delta.zip`. Les parties ont une taille/empreinte
SHA-256 et sont assemblées avant le contrôle de l'archive intégrale.
Les manifests décrivent des chemins relatifs sûrs, un protocole de version 1,
les versions application/données, le SHA Git source, tailles et SHA-256 des
fichiers. `app/distribution/manifest.py` rejette chemins dangereux,
doublons, tailles hors limites et schémas inconnus. **Aucune signature
cryptographique indépendante du canal GitHub n'est revendiquée** : les
hashes attestent la cohérence des octets avec le manifeste récupéré.

Code propriétaire : `.github/workflows/atlas-windows-distribution.yml`,
`scripts/windows/package_release.py`,
`scripts/windows/export_app_repository.py`,
`app/distribution/manifest.py` et `app/distribution/release_client.py`.
La PR de synchronisation APP #4 doit rester ouverte et Draft : le workflow
stable n'a pas besoin de la fusionner.

## Installation, chemins et prérequis

`DofusAtlasSetup.exe` est construit avec PyInstaller en `onefile` et
embarque `DofusAtlas.exe`. `app/distribution/setup.py` installe ce
lanceur compact dans `%LOCALAPPDATA%/Programs/DofusAtlas/`, prépare un
outil de maintenance et crée un raccourci Bureau via PowerShell/COM.
`DofusAtlas.exe` est lui aussi un binaire Python PyInstaller autonome ;
le programme `AtlasApp.exe` est empaqueté en `onedir` avec PySide6,
QtWebEngine, workers et ressources runtime. Le **parcours gelé normal ne
doit pas installer Python/Qt en dehors du bundle**, et l'installateur par
utilisateur ne demande pas d'élévation administrateur.

Le bootstrap **source/legacy** `scripts/windows/bootstrap_dofus_atlas.ps1`
est une voie distincte : il peut rechercher puis installer Python 3.13.15
via des voies Windows en cas d'absence de Python adéquat. Cela ne doit pas
être confondu avec le Setup gelé. Les dépendances de build PySide6 sont
déclarées dans `requirements-pyside.txt`; le packaging Windows épingle
PyInstaller 6.16.0. La disponibilité des bibliothèques système, les
permissions réelles et le comportement antivirus restent à certifier sur un
Windows vierge. Les prérequis de plateforme non inventoriés demeurent
explicitement **LV2-006 PENDING**.

La racine des données persistantes est `%LOCALAPPDATA%/DofusAtlas/`.
`app/distribution/install_location.py` stocke le dossier choisi dans
`installation.json` (schéma 1) : le gros runtime peut aller sur un autre
disque, tandis que launcher, journaux et profils restent dans LocalAppData.
Le déplacement copie dans un staging voisin, vérifie le nouvel exécutable,
puis commute la configuration ; il conserve l'ancien emplacement pour
récupération. Les liens symboliques/junctions, dossiers imbriqués et
emplacements réseau non sûrs sont rejetés. L'usage réel avec chemins Unicode,
DPI et antivirus doit encore être validé dans #287.

## Vérification, cache et installation transactionnelle

`app/distribution/launcher.py` prend un verrou de mise à jour et vérifie
qu'aucune instance Atlas ne détient le verrou graphique avant de modifier
un slot. `release_client.py` demande la Release stable officielle APP,
compare le SHA Git installé, puis ne télécharge pas d'archive d'application
si la version est inchangée. Une indisponibilité du réseau n'entraîne pas
de réinstallation forcée lorsqu'un binaire sain est déjà installé.
L'exécutable actif est contrôlé contre sa taille/SHA-256 stockés ;
`--atlas-verify-install` force une validation approfondie.

Le cache multipart vérifie longueurs et hashes avant réutilisation. Un
fragment entier corrompu est supprimé puis téléchargé à nouveau, avec
tentatives et parallélisme bornés. `network_bytes` compte les octets
effectivement transférés ; `cached_bytes` ne crédite pas les octets
obtenus dans la même tentative. Le cache local `.atlas-file-index.json`
est un **indice** d'optimisation associé au SHA source : chaque contenu
réutilisé est vérifié avant son activation.

`app/distribution/install.py` valide d'abord l'archive, extrait dans un
nouveau répertoire temporaire, vérifie SHA-256 et taille de chaque fichier,
puis installe un slot immuable dans `runtime/versions/`.
L'état `runtime/state.json` est écrit en fichier temporaire, flush/fsync
et `os.replace` ; `pending` conserve la version précédente jusqu'au
healthcheck réussi. `rollback_pending` restaure les métadonnées de
l'ancien slot de façon idempotente, sans détruire les données utilisateur.
L'isolation des slots et la préservation de l'ancienne version évitent
les hardlinks mutables ; quand un clone CoW ReFS n'est pas disponible, la
copie vérifiée des fichiers inchangés dans le staging **réécrit des octets
sur NTFS**. L'exigence « zéro fichier inchangé réécrit » **LV2-003 n'est
donc pas encore atteinte** sur tous les systèmes de fichiers.

Les `os.replace` sur un même volume apportent une opération de renommage,
**pas une transaction atomique universelle entre répertoires Windows et
fichiers ouverts**. Verrouillage antivirus, manque d'espace et interruption
physique demandent une validation native ; ne pas déclarer LV2-004 terminé
sans ces preuves.

## Handoff Tk → Qt → Home

`DofusAtlas.exe` affiche son panneau Tk minimal (statut et progression)
pendant la vérification, le téléchargement, l'installation et l'attente
de Home. `DOFUS_ATLAS_LAUNCHER_HANDOFF=1` est transmis uniquement à la
voie GUI ; dans ce cas, `app/ui/preload_popup.py` exécute le chargement
Qt sans afficher une deuxième fenêtre et `main.py` supprime le splash
intermédiaire. Un lancement direct d'Atlas, sans cet indicateur, conserve
le préchargement visible ordinaire.

Un binaire récent publie des marqueurs temporaires `.capable`, `.ready`
et `.home` avec **PID du processus lancé** :
`.ready` atteste l'entrée dans la boucle Qt, `.capable` annonce le
support du nouveau protocole, et `.home` est envoyé après un
`QEvent.Paint` de Home suivi d'un tour de boucle. Le lanceur garde Tk
visible jusqu'au signal Home et ne considère pas les marqueurs d'un autre
PID. Les anciennes versions sans `.capable` conservent le relais legacy
Tk → popup Qt à `.ready`. Un timeout d'un processus encore vivant ne
déclenche pas une seconde instance ni un rollback concurrent.

**Limitation déterminante :** le premier paint et un tour de boucle
ne démontrent pas à eux seuls la réponse réelle aux clics utilisateur.
L'absence de scintillement, les DPI 100/125/150 %, la réactivité durable
de Home et les temps p50/p95 doivent être mesurés sur l'EXE du SHA final.
LV2-001, LV2-007, LV2-008, LV2-009, LV2-012 et la recette #287
conservent leurs statuts de suivi tant que ces preuves manquent.

## Mesures et tests, sans confusion des niveaux de preuve

`app/distribution/startup_trace.py` émet des événements monotoniques
corrélés à une session dans un JSONL opt-in limité à 2 MiB.
`tools/startup_trace_report.py` compare des campagnes avec p50/p95
et alertes conservatrices au-delà de 5 % pour cinq sessions ou plus.
Il ne mesure pas magiquement le double-clic natif avant l'entrée Python
ni l'interaction humaine. Les benchmarks CI de préchargement, navigation
et process-tree sont **des scénarios différents**, non interchangeables.

Les contrats ciblés sont couverts notamment par
`tests/test_distribution_smart_update.py`,
`tests/test_distribution_launcher_noop_offline.py`,
`tests/test_distribution_health.py`,
`tests/test_startup_preload_window_visibility.py` et les tests
`test_distribution_*.py`. Le job
`atlas_windows_distribution / Windows bundle (gated certification)`
construit le binaire gelé, exécute ses smokes Qt, Guide, Succès, Craft et
l'intégrité du ZIP, puis archive un **candidat non publié** pour la PR.
Seules les runs GitHub effectivement terminées SUCCESS au SHA exact
constituent une preuve automatique ; aucune de ces runs ne remplace
la recette humaine #287.

## Ownership, cleanup et dangers connus

- Binaires : slots versionnés du runtime, remplaçables exclusivement par
  transaction validée ; ne pas toucher au slot actif pendant son exécution.
- Données privées : profils, suivi de quêtes, progression et bases locales
  sous la racine utilisateur ; ne jamais exporter, réinitialiser ni effacer
  depuis un nettoyage de slots ou une Release APP.
- Cache : archives et fragments téléchargés, nettoyés uniquement selon
  les marqueurs et règles d'intégrité connus ; le cache n'est pas une
  preuve suffisante du contenu installé.
- Logs : `%LOCALAPPDATA%/DofusAtlas/logs/updater.log`, journaux de trace
  opt-in sous la même racine. Expurger les chemins privés avant partage.
- Risques ouverts : latence native double-clic → Home interactive,
  RAM après navigation sous 100 Mio, gains Windows froid/chaud,
  coût des copies NTFS, conditions de crash/antivirus, migration Unicode
  et validation visuelle DPI. Les tests unitaires verts ne ferment pas
  ces exigences par anticipation.

**Définition de sortie :** preuves de code et de tests associées à chaque
LV2 dans le rapport de PR, certification de phase au HEAD final, build gelé
au même SHA, recette humaine #287 et Release APP publiée uniquement ensuite.
Un résultat `TRACKED_PARTIAL` du Delivery Guard est un inventaire
comptable, pas une permission de fusion ni de publication.
