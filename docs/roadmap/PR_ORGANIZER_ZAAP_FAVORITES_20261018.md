# PR Organizer — commande Zaap 3.7, favori persistant et slots épurés

Date : 18 octobre 2026. Base : main SHA 6a52522d1bd7e501a5c3b4d6d58253bfec755fdc.
Statut : périmètre et premières corrections ; **ne pas merger avant tests Windows**.

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

## Tests et preuves
- Unitaires parse de `/zaap`, commandes combinées, collisions ciblage, favori et migration ; Qt Organizer redémarrage et structure slots ; Windows réel multi-fenêtres (1/2/5), avec logs par HWND résolu, aucune fenêtre supplémentaire ciblée.
- CI ciblée, Doctor UI/raster, tests persistance et intégration Guide, réseau ID fail-closed ; validation Windows nécessaire avant fusion.
