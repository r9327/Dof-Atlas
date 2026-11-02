# Organizer — Camembert de sélection des personnages (#320 / PR #324)

## Fonctionnement implémenté sur la branche

- Le bouton **« Sélection personnage »** remplace l'ancien « Slot libre »
  dans la carte Macro. Cliquer sur le bouton ou sa pastille de raccourci permet
  d'enregistrer une touche ou une combinaison ; le petit X supprime le raccourci.
- En jeu, **maintenir la touche** configurée affiche un disque au **centre exact
  de l'écran** sur lequel se trouve la souris, jamais centré sur le curseur.
- Le menu ne prend pas le focus de Dofus et n'intercepte pas les clics.
- Déplacer la souris vers une part met le personnage en surbrillance. Le curseur
  doit bouger volontairement et rester dans l'anneau pour sélectionner.
- **Relâcher la touche masque le menu immédiatement**, même sans sélectionner
  de part. Une sélection valide peut alors activer sa fenêtre Dofus.
- Échap annule, sans activer de fenêtre ; le disque reste fermé jusqu'au
  relâchement de la touche configurée.
- Menu 0–8 parts égales, aucun emplacement vide. La fenêtre doit être dans les
  sessions Organizer, détectée, avec inclusion explicite et identité contrôlée.
- Le nouveau bouton rond de chaque personnage permet de l'inclure/exclure du
  camembert. La sélection initiale est figée au premier raccourci configuré :
  une nouvelle fenêtre simplement détectée n'est jamais ajoutée implicitement.
- L'ordre des parts suit la liste des sessions Organizer. Sur relâchement,
  le handle, le nom et le PID (quand disponible) sont revérifiés.
- Portrait optionnel par `portrait_path`, sinon icône de classe disponible ;
  libellé et surbrillance visibles.

## Implémentation et tests ajoutés

- `app/pages/organizer/radial_selection.py` : géométrie, identités, filtre,
  décision sur relâchement et écrans aux coordonnées négatives.
- `app/pages/organizer/radial_overlay.py` : widget Qt translucide non activant,
  rendu et contrôleur d'appui/relâchement.
- `app/pages/organizer_page.py`, `organizer_ui.py`,
  `organizer_hotkeys.py` : raccordement, raccourci, persistance et opt-in.
- `tests/test_organizer_radial_selection.py`,
  `tests/test_organizer_radial_overlay.py`,
  `tests/test_organizer_hotkey_capture.py` : tests ajoutés, **non exécutés
  dans cet environnement** faute de runtime PySide6 / Windows accessible.

## Limites à vérifier avant Ready / fusion

Le contrôleur utilise `GetAsyncKeyState` **uniquement sur Windows avec un
raccourci défini** ; il ne crée aucun second moteur de macros et ne modifie pas
les hooks existants. Cette lecture d'état **ne consomme pas la touche dans
Dofus et ne distingue pas toutes les entrées synthétiques**. Une touche déjà
utilisée par le jeu peut donc aussi y déclencher son action. Les collisions
avec les raccourcis Atlas/Direction connus sont refusées.

- Vérifier le popup réel avec Dofus Unity (fenêtré / borderless), multi-écrans,
  DPI 100/125/150/200 %, clavier maintenu et jeu au premier plan.
- Vérifier les interruptions et la coexistence avec MacroLock/hook clavier.
  Ne pas prétendre que le polling équivaut à un hook natif filtrant.
- Vérifier que des portraits personnalisés sont bien fournis par le profil
  courant ou utiliser le fallback de classe.
- Tester, mesurer et auditer les commits au SHA final, appliquer le routage CI
  Organizer (#328), puis obtenir les preuves Windows exigées par #322/RAD-005.
- **Cette PR reste Draft ; les essais réels Windows et la certification finale
  sont NOT_RUN jusqu'à preuve explicite.**
