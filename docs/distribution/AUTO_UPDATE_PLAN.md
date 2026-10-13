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
