# Distribution Windows et mises à jour automatiques

## Architecture cible
- Dépôt source canonique : `r9327/Dof-Atlas` (code, Doctor, Graphify, IA, tests, docs).
- Dépôt de distribution proposé : `r9327/Dof-Atlas-App`, alimenté automatiquement après validation de `main` (ne jamais maintenir le code en double).
- Publication de versions Windows via GitHub Releases, compilées depuis un commit source identifié.
- Un seul raccourci visible : Dofus Atlas. Un processus updater distinct remplace les fichiers fermés, puis lance l'application.
- Progression réelle : vérification, téléchargement (octets reçus/total), vérification, installation, lancement.
- Données JSON et ressources versionnées séparément lorsque compatibles ; aucune recompilation pour une mise à jour de données seules.

## Conditions de sécurité
- Pas de publication depuis une PR ou une CI rouge.
- Manifestes SHA-256, version et SHA source ; chemins autorisés uniquement.
- Téléchargement temporaire, contrôle d'intégrité, installation atomique, retour arrière si échec.
- Ne jamais écraser profils, sauvegardes, progression, préférences ou caches locaux.
- Hors ligne : lancer la dernière version saine ; échec réseau non bloquant.
- Verrou anti double lancement ; pas de mise à jour d'un exécutable en cours d'utilisation.
- Ne pas introduire de jeton GitHub privé dans le client.
- Conserver les modules QtWebEngine, plugins Qt, workers subprocess et données runtime nécessaires.

## Réalisation (PR indépendante de l'audit)
1. Inventorier chemins d'écriture, imports dynamiques, QtWebEngine et workers ; établir la liste réelle des fichiers runtime.
2. Construire et tester un bundle Windows reproductible avec ses ressources et licences.
3. Ajouter un updater autonome, interface PySide6 légère avec progression, états d'erreur et rollback.
4. Ajouter un workflow de validation + synchronisation filtrée du second dépôt ; créer/configurer le second dépôt et ses permissions de publication.
5. Publier les Releases Windows avec manifeste versionné ; différencier code et données.
6. Tester installation neuve, mise à jour, absence de réseau, corruption, verrou Windows, échec et rollback.
7. Certifier sur Windows après stabilisation de l'audit ; ne pas fusionner ni publier avant preuve de fonctionnement.

## Contraintes
- Ne pas toucher aux optimisations et audits en cours.
- Ne pas recopier les outils de développement dans le dépôt de distribution.
- Les versions distribuées sont construites par CI, jamais par le PC client.
- Aucun benchmark RAM lourd pendant l'implémentation ; tests ciblés puis certification finale.

## Exigences complémentaires — mises à jour et exploitation
1. **Téléchargements différentiels** : ne transférer que les fichiers/blocs modifiés quand le manifeste et le format de distribution le permettent ; repli sûr vers le paquet complet.
2. **Contrat de compatibilité données/code** : versions de schéma, contraintes min/max et refus d'appliquer des JSON incompatibles avec le binaire installé.
3. **Migration des données utilisateur** : migrations versionnées, idempotentes, sauvegarde avant migration et restauration vérifiée ; ne jamais écraser profils, progression ou paramètres.
4. **Versionnement séparé** : version de l'application, version du jeu de données, version du schéma et version du protocole de mise à jour.
5. **Auto-réparation** : comparer les fichiers installés au manifeste signé ou authentifié et restaurer les fichiers absents/corrompus sans supprimer les données utilisateur.
6. **Canaux de diffusion** : stable par défaut ; bêta/test sur opt-in explicite ; empêcher tout passage involontaire vers un canal moins stable.
7. **Reprise sur interruption** : téléchargement reprenable si le serveur le permet, fichiers temporaires vérifiés, reprise sûre après fermeture, crash ou perte réseau.
8. **Test PC vierge** : démarrage, WebEngine, workers et parcours principaux sur Windows sans Python ni dépendances de développement installés.
9. **Diagnostic respectueux de la vie privée** : journaux locaux bornés, erreurs exploitables, aucune donnée sensible, aucun jeton ou chemin personnel publié ; collecte distante uniquement sur consentement.
10. **Garde-fous de publication** : releases exclusivement depuis un commit certifié, provenance exacte SHA, permissions CI minimales, vérification de l'artefact et aucune diffusion depuis PR non validée.
11. **Updater minimal** : ne pas démarrer QtWebEngine ni charger toute l'application pour afficher la progression ; choisir une interface native/légère et mesurer son temps de démarrage.
12. **Progrès honnête** : progression calculée à partir des octets et étapes réelles, état indéterminé quand la durée est inconnue, messages explicites en cas d'échec.
13. **Cohérence multi-dépôts** : traçabilité SHA source → snapshot distribué → release ; synchronisation idempotente, sans commits en boucle et sans dépendance à un secret dans le client.
14. **Rollback applicatif et données** : transaction de mise à jour cohérente ; conserver la dernière version saine et vérifier le redémarrage avant de purger les sauvegardes.
15. **Validation ciblée** : tests unitaires du manifeste, compatibilité, migration, interruption, reprise et restauration pendant le développement ; validation Windows complète avant fusion.


## Avancement de l'intégration (PR #159)

Le code du protocole de mise à jour, du téléchargement, des slots transactionnels, de la fenêtre Tkinter, du signal Qt de santé, de la persistance des profils et de l'export applicatif est présent sur cette PR. Les tests unitaires ciblés sont intégrés dans un workflow indépendant des certifications lourdes.

**À ne pas confondre avec une publication prête :** aucun EXE n'est réputé fonctionnel sans le job Windows PyInstaller suivi d'un test réel, et aucun second dépôt n'a été créé par cette PR.

### Configuration de publication (après validation et fusion)
- Créer le dépôt public GitHub **r9327/Dof-Atlas-App** avec branche \`main\`.
- Créer dans le dépôt source le secret **ATLAS_DISTRIBUTION_TOKEN**, limité au second dépôt avec permission Contents en écriture, et droits de publication Releases.
- Autoriser explicitement la publication en configurant la variable source **ATLAS_DISTRIBUTION_ENABLED=true** uniquement après vérification Windows complète.
- La publication s'exécute sur le SHA **exact de main** validé par le workflow *Phase Certification*. Un SHA périmé est bloqué avant build.
- Les images et autres binaires volumineux restent dans la Release Windows ; le dépôt App conserve le code applicatif et les données structurées utiles, pas Doctor/Graphify/tests.
- Distribuer le fichier \`DofusAtlas.exe\` de la Release comme seul point d'entrée visible. Les binaires d'application sont téléchargés dans le dossier utilisateur.

### Points restant à certifier / développer avant un merge de production
- Validation Windows vierge des imports QtWebEngine, sous-processus gelés, images LFS, premier lancement et rollback.
- Contrôle exhaustif des écritures hors des chemins utilisateur dédiés, après audit architectural.
- Mise à jour **des données seules** sans reconstruire l'exécutable, avec version de schéma et migration vérifiée.
- Téléchargements différentiels multi-assets, purge bornée des anciennes installations, mise à jour du bootstrap lui-même.
- Vérification de provenance complète des artefacts compilés et du modèle de permissions du dépôt de distribution.

**Règle de sortie :** pas de merge ni de publication stable sur cette seule base documentaire ou sur des tests purement Python.
