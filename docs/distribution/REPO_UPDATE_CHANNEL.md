# Launcher V2 — canal de mises à jour hors Release (NRU, issue #336)

## Objectif précis

Le launcher unique installé depuis une **Release certifiée** doit pouvoir
récupérer ensuite des correctifs applicatifs validés **sans créer une nouvelle
GitHub Release à chaque synchronisation**. Cela ne signifie pas exécuter
les fichiers Python présents dans `APP/main` : AtlasApp est un bundle
PyInstaller gelé. Les correctifs de code doivent être compilés en Windows,
puis distribués comme deltas de vrais fichiers du bundle.

## État du code au commit initial

Le protocole de pointeur immuable est ajouté au parseur déjà canonique
`app/distribution/manifest.py` et au constructeur hors ligne
`scripts/windows/build_repo_update_pointer.py`. Ces fonctions réutilisent
`ReleaseManifest`, son SHA et `install_release(..., delta=True)` ; elles
n'ajoutent pas de nouvel installeur. Elles **ne sont pas encore reliées
au réseau, au launcher ou au workflow de publication**. Aucune activation
ou publication nouvelle ne découle de leur présence.

## Sonde légère en lecture seule (NRU-002 partiel)

`app.distribution.release_client.probe_repo_update(installed_source_sha)`
peut maintenant lire **un seul pointeur de 4 Kio maximum** depuis l'adresse
APP codée en dur, avec un timeout de 5 secondes. Un SHA identique renvoie
`None` sans demander de manifeste ni de ZIP ; une base différente ou un
pointeur invalide bloque la sonde, sans modifier l'installation.
Une installation sans SHA valide reste sur le bootstrap Release.

**Cette sonde n'est pas branchée au launcher** : le pointeur sur `APP/main`
ne constitue pas à lui seul une attestation de certification. L'activation,
les preuves de publication de paquets immuables, le multi-sauts, le rollback
natif et la recette Windows restent nécessaires avant toute mise à jour
automatique par ce canal. Aucun nouveau téléchargement applicatif.

### Vérification de manifeste épinglé (NRU-002, NRU-005 partiels)

La fonction explicite `inspect_repo_update(installed_source_sha)`
réutilise la sonde du pointeur puis lit au maximum un manifeste immuable
`APP/<app_commit_sha>/updates/<source_sha>/atlas-manifest.json`.
Le SHA-256 du manifeste, l'identité source/base, le delta annoncé et sa
taille sont comparés au pointeur. Un SHA déjà installé entraîne une seule
requête de pointeur et **zéro requête de manifeste/ZIP**. Les URL raw
arbitraires, les sources Python et les ZIP restent refusés.

Un outil explicitement invoqué peut ensuite appeler
`download_repo_update_delta(pointer, raw_manifest, directory)` : il
réutilise le téléchargeur et le cache delta déjà présents, ses contrôles
HTTP Range et l'empreinte SHA-256 du ZIP. Le chemin raw est toujours
limité au fichier ZIP immuable étiqueté par le commit APP et le SHA DEV.
Un ZIP corrompu est supprimé, un 404 refuse la préparation, et aucun slot
d'installation ni sauvegarde n'est modifié. Ceci **n'installe pas Atlas**.

Aucune installation, extraction ou activation automatique :
la signature de certification indépendante, les droits, la publication
réelle et le rollback Windows restent à construire. Cette méthode n'est
pas appelée automatiquement par le lanceur.

## Qualification synthétique hors ligne du canal candidat

La suite `tests.test_distribution_repo_update_pointer` couvre désormais :
- le pointeur écrit atomiquement : en cas de verrouillage ou d'échec
  d'`os.replace`, la version précédente et les fichiers sources restent intacts ;
- le contrôle strict des membres ZIP contre le manifeste (taille, SHA-256,
  contenu, liens, fichiers inattendus) avant construction du pointeur ;
- le nettoyage des anciens `atlas-delta.zip` et
  `atlas-windows.partNNNN` lors d'un build dans un répertoire réutilisé ;
- avec **des binaires et données fictifs seulement**, le chemin existant
  téléchargement du delta → `install_release(delta=True)` → slot en attente
  → absence d'ACK/rollback → préservation d'un profil utilisateur ;
  puis refus d'une base locale corrompue et confirmation d'un slot sain.

Commande ciblée : `python -m unittest tests.test_distribution_repo_update_pointer -v`.
Cette suite peut être exécutée sur les runners Ubuntu/Windows, mais ne constitue
**ni une preuve de publication APP**, ni une recette d'EXE Windows, ni une
qualification sur un jeu en cours d'exécution. La route automatique du launcher
reste inchangée ; le nouvel endpoint APP ne devient pas autorité à partir de
ces tests. Les exigences LV2/NRU et contrôles de certification demeurent ouverts.

## Publication cible (NON ENCORE ACTIVÉE)

1. `Dof-Atlas/main` passe les tests d'intégration et la certification
   exigée pour le SHA exact ; la destination `Dof-Atlas-App` est contrôlée.
2. Pour un changement compatible, builder le bundle Windows gelé puis créer
   le delta **réel** et le `atlas-manifest.json` existant ; les JSON seuls
   peuvent reprendre l'EXE précédent via le chemin JSON-only.
3. Rejeter ce canal si le delta dépasse 95 Mio, si les droits de
   redistribution sont incertains, si le lanceur doit être remplacé, si la
   base incompatible est absente ou si les vérifications d'intégrité échouent.
   Dans ces cas, garder la Release précédente et utiliser la chaîne de
   distribution complète lorsqu'une nouvelle version stable est prête.
4. Publier les deux fichiers immuables du paquet, sous
   `updates/<source_sha>/atlas-delta.zip` et
   `updates/<source_sha>/atlas-manifest.json` ; la destination publique
   doit être durable et compatible avec les limites réelles du fournisseur.
5. **Après** confirmation distante du stockage, obtenir le vrai SHA Git
   du commit APP qui contient le paquet. Construire le petit pointeur
   `updates/stable.json` depuis `build_repo_update_pointer.py`
   et le publier *en dernier*. Le pointeur impose SHA Git complet du commit
   de paquet, digest du manifeste et digest/taille du delta.
6. Dans une future intégration client, ne regarder ce canal que si l'EXE
   actif est sain, que le protocole est compatible et que la source de
   confiance a été authentifiée par le publisher. Télécharger uniquement
   le delta compatible avec l'installation ; vérifier les octets, passer
   par les **slots/rollback/ACK existants** et ne changer les données
   utilisateur ni les raccourcis.
7. Prévoir les mises à jour multi-sauts, l'amorçage des anciennes installations,
   la gestion de la chaîne de base et la rétention des paquets. Un pointeur
   unique base→cible ne suffit **pas encore** à livrer plusieurs
   correctifs consécutifs à tous les clients.

## Limites et protections

- Le SHA-256 ne constitue pas une signature cryptographique indépendante
  de GitHub. La CI doit empêcher la publication d'un pointeur issu d'une
  branche non certifiée.
- La base/source doivent différer, les noms et hôtes sont construits et
  non injectés depuis du JSON, et un paquet supérieur à 95 Mio est rejeté.
- Le téléchargement brut du code de `main` dans l'EXE est **interdit**.
- Aucune modification n'est autorisée dans `Dof-Atlas-App/main` ou la PR
  permanente #4 par ce prototype.
- Tests Windows, compilation gelée, Graphify/Doctor exact-SHA, certification
  et pilote de publication : **NOT RUN / restant à développer**.
- Le contrat source du Launcher V2 (#286) reste inchangé ; les exigences
  spécifiques NRU-001…010 appartiennent à l'issue #336.
