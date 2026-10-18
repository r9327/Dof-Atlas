# PR Organizer — commande Zaap 3.7, favori persistant et slots épurés

Date : 18 octobre 2026. Base : main SHA 6a52522d1bd7e501a5c3b4d6d58253bfec755fdc.
Statut : implémentation locale terminée ; **ne pas merger avant tests Windows et CI du SHA poussé**.

## Implémentation réalisée
- Zaap Organizer : commande directe `/zaap x,y` depuis les coordonnées canoniques, sans Havre-Sac, calibration ni clic ; refus sûr lorsque les coordonnées manquent.
- Favori principal : persistance par `character:<id>` vérifié, repli nom+classe uniquement s'il est unique, migration sûre des anciennes valeurs HWND et refus des identités ambiguës.
- Guide Succès/Lanyel : participants explicites et persistants par ID stable, y compris hors ligne ; un clic transmet une seule commande au runtime ciblé. Zéro sélection, cible ambiguë ou toutes les cibles hors ligne restent fail-closed.
- Travel ciblé : seules les formes `/travel x,y` et `/zaap zx,zy ; /travel x,y` sont acceptées, avec une séquence au plus par client Unity vérifié.
- Slots : les numéros visibles ont été retirés sans modifier les indices internes, raccourcis, exports ni l'ordre des sessions.

## Validation locale disponible
- Tests ciblés Zaap, identité/favori, runtime Travel et UI participants : PASS.
- Doctor Agent HARD des micro-lots : PASS ; syntaxe et `git diff --check` : PASS.
- Doctor FAST source-only : les groupes architecture, identité, persistance, démarrage, lazy loading, budgets et cibles du diff passent. Les groupes async/golden restent bloqués uniquement par les données Doduda/LFS absentes de ce checkout (`data/cache/dofus_maps/raw/doduda_cli/quest_categories.json`).
- Restent obligatoires avant fusion : test Windows réel multi-fenêtres 1/2/5, vérification stop/focus/fenêtre fermée, matérialisation des données pour les groupes FAST bloqués, puis CI exacte du SHA poussé.

## Bug favori de la fenêtre principale
Diagnostic dans `app/pages/organizer/character_sessions.py` : `set_primary_window` enregistre `hwnd:<handle>` ; au redémarrage, Windows peut affecter un autre HWND. `sanitize_profiles` conserve pourtant ce jeton éphémère, mais l'étoile ne retrouve plus le client et le primaire est perdu visuellement et fonctionnellement.

- Persister une identité de personnage **stable et vérifiée**, si disponible ID personnage/liaison réseau, sinon nom+classe uniques et non ambigus ; HWND uniquement comme résolution de session temporaire.
- À la prochaine détection de session, réassocier l'étoile et le primaire au bon personnage ; ne jamais attribuer un favori à un autre compte par simple indice de slot ou ancien PID.
- Si identité ambiguë, statut neutre et explication ; conserver la préférence sans l'affecter à un mauvais personnage. Préserver les profils existants et envisager migration sûre des HWND historiques quand ancien nom+ID prouvable.
- Tests : sélectionner favori, fermer/reouvrir Atlas, redémarrer DOFUS, varier HWND/PID et ordre des slots, 2 persos même classe, noms génériques, absence d'une session, sécurité contre attribution erronée.
- Les FAVORIS ZAAP (dans `zaap_shortcuts.json`) sont distincts de l'étoile d'un personnage ; vérifier leur persistance par redémarrage également. La sélection courante de Zaap ne doit pas être confondue avec la liste de favoris.

## Zaap — remplacer Havre-Sac + clic hasardeux
- `app/macros/zaap.py` effectue aujourd'hui H -> clic calibré -> saisie. Le chemin principal DOFUS >=3.7 doit employer **/zaap x,y**, sans Havre-Sac/calibration/clic automatique. Identifier les coordonnées depuis `ZaapWidget` et la source canonique `zaaps.json` ; valider avant envoi, jamais chercher le nom avec clic comme comportement par défaut.
- Les macros Travel et Zaap partagent l'exécuteur chat vers les clients : enchaînement `/zaap zx,zy ; /travel x,y` sur la même fenêtre, sans parallélisme entre macros concurrentes.
- Prendre une liste explicite et immuable de destinataires du guide (IDs stables puis fenêtres Unity validées), aucune réutilisation du sélecteur global `ordered_clients_from_source()` pour un clic de guide ; conserver le comportement existant des boutons Organizer hors guide.
- Gestion des mondes et Zaaps incompatibles : ne pas émettre `/zaap` en cas de destination non vérifiée ; prévoir repli direct conforme au plan ou erreur claire. Stop d'urgence, fenêtre fermée, focus, timings, restauration, pas de doublons en cas de double clic.
- Sortie UI : coords des guides inchangées visuellement ; lien cliqué déclenche immédiatement la commande prévue, pas d'encadré, pas de confirmation systématique ni mode "copier" imposé.

## Slots
- Supprimer **uniquement les numéros visuels** des slots vides et remplis dans `app/pages/organizer/organizer_ui.py`. Garder slots internes, indices de raccourcis clavier, order/export et drag&drop inchangés.
- Vérifier aucune perte d'alignement, aucun bouton invisible ou conflit de largeur.

## Persistance et routage : cas à ne surtout pas oublier
- **Favori de personnage (étoile)** : distinguer « favori choisi », identité de personnage stable et fenêtre actuellement reconnue. Après fermeture et réouverture d'Atlas, le même personnage doit garder son étoile active ; après redémarrage de DOFUS, résoudre le NOUVEAU HWND et restaurer la sélection sans attribuer l'étoile à une mauvaise fenêtre.
- **Favoris Zaap** : conserver les étoiles de Zaaps et vérifier la **sélection visible du Zaap favori actif** après redémarrage, si cette sélection était enregistrée. Distinguer la persistance de la liste des favoris, du choix courant et de la préférence de fenêtre principale : ces états ne doivent pas s'écraser mutuellement lors de la sauvegarde.
- **Déplacement de guide** : aucun participant sélectionné, tous hors ligne ou identités ambiguës => zéro commande envoyée et retour explicite ; ne jamais passer silencieusement à « tous les clients ». Les participants sélectionnés qui sont hors ligne gardent leur participation au guide.
- **Un clic sur une coordonnée** dans Guide Succès ou Lanyel => **une seule exécution** qui envoie sur chaque fenêtre Unity vérifiée au plus une séquence `/travel x,y` OU `/zaap zx,zy ; /travel x,y`, selon le plan pré-calculé. Pas de panneau ou bouton additionnel, pas d'envoi aux fenêtres d'autres personnages, et arrêt d'urgence utilisable.
- **Macro Zaap Organizer autonome** : la sélection d'un Zaap continue de fonctionner hors guide et utilise les coordonnées de l'index, non le nom collé dans l'ancien champ Havre-Sac. Échec sûr si coordonnées manquantes ou Zaap invalide ; pas de repli silencieux aux clics hasardeux.
- **Tests ciblés** : préférences enregistrées puis deux redémarrages successifs, inversion de slots et HWND, plusieurs personnages de même classe, 0/1/5 cibles, fenêtres disparues entre planification et exécution, favoris Zaap choisis et retrouvés, et aucune numérotation visuelle malgré les raccourcis internes préservés.

## Tests et preuves
- Unitaires parse de `/zaap`, commandes combinées, collisions ciblage, favori et migration ; Qt Organizer redémarrage et structure slots ; Windows réel multi-fenêtres (1/2/5), avec logs par HWND résolu, aucune fenêtre supplémentaire ciblée.
- CI ciblée, Doctor UI/raster, tests persistance et intégration Guide, réseau ID fail-closed ; validation Windows nécessaire avant fusion.
