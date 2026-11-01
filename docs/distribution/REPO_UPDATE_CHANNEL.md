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
