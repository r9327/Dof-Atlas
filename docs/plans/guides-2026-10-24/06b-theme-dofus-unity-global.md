# Complément demandé le 24/10/2026 — thème intégral DOFUS Unity pour Atlas


> **Mise à jour des sources réelles (24/10/2026, commit `f17b4724`) :** le dépôt contient maintenant l'archive du **fond original**, neuf sous-archives ZIP regroupant les **103 PNG originaux** réellement transmis, et le ZIP de sélection avec manifeste/aperçu/script. Voir `docs/design/dofus-unity/README.md`. Les **47 sprites UI précis** du manifeste et les **10 fichiers TTF** restent absents du dépôt : ils sont sur le PC de l'utilisateur et nécessitent un import distinct. Les ZIPs déjà présents ne sont pas encore utilisés par le runtime. Les mentions ci-dessous « non versionnée ici » décrivent l'état initial de la préparation avant ce commit.

> **À réaliser dans la PR #254 existante, sans supprimer ni réécrire les fonctionnalités déjà implémentées.** Ce document est une spécification versionnée, PAS la preuve que le thème est intégré. Les PNG/TTF originaux sont sur le PC de l'utilisateur ; ils ne sont pas joints à la branche. Aucune certification Windows ou preuve de rendu n'est attestée ici.

## A. État contrôlé de la PR #254

La branche `plan/guides-20261024-06-accueil-guides-bibliotheque` contient déjà des modifications applicatives sur `GuideCatalogView`, `GuideHomeColumns`, `FeaturedGuideCard` et `EncyclopediaPage` :
- exactement deux grandes cartes **Guide Succès Opti** et **Sylvestre Opti**, accessibles souris/clavier ;
- Bonta/Brâkmar dans l'arbre Alignements ; familles Optimisés/Alignements/Dofus/Dimensions/Éliocalypse/Régions/Événements/Îles/Autres ;
- suppression de la recherche globale Encyclopédie, de la recherche Guides et des filtres Tous/En cours/Terminés ; les recherches Quêtes/Succès/Sommaire demeurent ;
- grille Dofus adaptative, sous-menus persistants, sources Ganymède metadata-only inactives, progressions réelles sans « 0 % » inventé ;
- retour catalogue léger et captures Doctor prévues. Ne pas régresser ces fonctions.

## B. Références visuelles *réelles*

**Fond validé par l'utilisateur :** capture originale de la sélection de personnages DOFUS Unity, 1919 × 1079, SHA-256 `3834e92f6432019e2fde2b5f0ccb7f3b2236fda48ea7a6d368c60a660ef5fdeb`. Capture détenue dans la conversation, non versionnée ici. Scène cosmique cyan / bleu / violet, étoiles, nuages et rochers flottants. Les trois icônes natives en haut à droite ne doivent pas être reproduites en éléments décoratifs Atlas ; préparer un fond nettoyé *sans toucher à l'original*, après validation.

**Extraction réalisée localement sur Windows :**
- DOFUS Unity installé sous `%LOCALAPPDATA%\Ankama\Dofus-dofus3`.
- `Picto/UI` : 44/44 bundles traités, 8 537 PNG.
- cinq bundles d'UI : `uiassets_assets_.bundle`, `uiassets_assets_1x.bundle`, `uiassets_assets_2x.bundle`, `uidarkstone_assets_all.bundle`, `uielements_assets_all.bundle`.
- Extraction ciblée `--force-object` : **3 359 PNG et 10 TTF** déclarés par l'utilisateur, et **47 candidats visuels** présélectionnés dans `Atlas_UI_Manifest_Cible.csv` (ce manifeste et les fichiers originaux ne sont PAS encore dans Git). La sélection visuelle de la conversation ne remplace pas ces 47 originaux.
- Catégories observées : boutons normal / over / pressed / disabled, cases normales/sélectionnées, onglets, bordures et ombres de fenêtres, icônes de navigation.

**Police :** dix ressources extraites : `Lexend-Regular/Medium/SemiBold/Bold`, `Rowdies-Regular`, `LexendDeca-Regular`, `LexendGiga-Regular`, `NotoSans-Medium`, `NotInter-Regular`, `Roboto-MediumItalic`. Leur présence est confirmée ; **l'affectation exacte par écran est à vérifier**. Recommandation Atlas : Lexend pour contrôles/texte, Rowdies pour titres expressifs parcimonieux, variantes spécialisées au besoin. Ne jamais distribuer les TTF extraits du jeu sans vérification de licence/droits ; préférer les distributions officielles redistribuables des polices lorsqu'elles existent.

## C. Périmètre de thème attendu

1. **Fond global** sur l'ensemble du shell Atlas (accueil, Guides, Quêtes, Succès, Bestiaire, Organizer, Zaap et autres pages), pas seulement la carte Guide. Le ciel reste visible, pas de filtre noir uniforme ; panneaux superposés lisibles et translucides, tout en préservant contraste WCAG et lisibilité du texte.
2. **Boutons fidèles** aux ressources DOFUS Unity : silhouettes, contours, reliefs, reflets, états normal/hover/pressed/disabled/selected. Privilégier les vrais éléments validés ; fournir le même résultat au clavier (focus visible). Conserver les actions et tailles minimales cliquables, sans transformer les menus en nouveaux widgets.
3. **Panneaux, fenêtres, onglets, tooltips, dialogues, listes, séparateurs, cases, barres de progression** : décliner les textures darkStone et Figma UI. Préserver états métier, messages d'erreur et couleurs sémantiques (success/warning/danger) ; ne pas appliquer le vert action à toutes les progressions.
4. **Icônes et identité :** réutiliser uniquement les vrais éléments relevés pour Guide, Quête, Succès, Encyclopédie, personnage, Dofus, carte, inventaire ; préserver les pictogrammes de classe vérifiés et leur cache. Ne pas remplacer le nom/logo Atlas par le logo DOFUS ni laisser croire à une application officielle Ankama.
5. **Typo et palette globales** : thème central partagé Qt/QSS + pages WebView CSS, avec tokens sémantiques et état de focus. Palette provisoire de design à valider sur les captures réelles (ce ne sont PAS des couleurs officielles mesurées dans les bundles) :
   - fond base `#151821` ; bleu nuit `#192657` ; violet nébuleuse `#625D9F` ;
   - accent bleu `#5372CD` ; clair `#D9EAF2` ; texte principal `#F1F6FB` ; texte secondaire `#B8C6E3` ;
   - accent pierre/or `#A1966E` ; vert CTA à calibrer depuis les sprites réels, *pas* un rectangle `#D1F202` appliqué partout.
6. **Adaptation visuelle :** image plein écran sans étirement géométrique (cover avec recadrage centré / letterbox délibéré selon écran), 1x/2x pour DPI, traitement 9-slice pour bordures agrandissables (ne pas étirer les coins), option de repli en l'absence de ressource.
7. **Perf et distribution :** aucune extraction ni analyse de bundles pendant l'exécution Atlas, pas de réseau ni de disque massif au démarrage, ressources chargées à la demande puis mises en cache borné ; ne pas créer un QPixmap pleine taille par page ; vérifier RAM et temps de changement de page. Les assets propriétaires restent locaux et optionnels tant que les droits de redistribution ne sont pas clarifiés. Le thème Atlas existant reste un repli fonctionnel.

## D. Ressources exactes sélectionnées à importer (47 candidats)

Racine locale de l'extraction : `%USERPROFILE%\Documents\Atlas-Dofus-UI-Composants`. Les préfixes `uiassets_assets_*`, `uidarkstone_assets_all`, `uielements_assets_all` correspondent aux dossiers créés par le script Windows. Les chemins complets sont conservés dans le CSV local `Atlas_UI_Manifest_Cible.csv` ; les noms ci-dessous doivent être réconciliés avec les **fichiers originaux**, et leur rendu inspecté avant intégration.

**Boutons principaux — 8 :**
- `Assets_UI_Themes_darkStone_common_btn_greenLargeBorder_{normal,over,pressed,disabled}-png.png`
- `btn_green_{normal,over,pressed,disabled}.png`

**Boutons secondaires — 8 :**
- `btn_green_small_{normal,over,pressed,disabled}.png`
- `btn_yellow2_{normal,over,pressed,disabled}.png`

**Navigation — 8 :**
- `Assets_UI_Themes_darkStone_common_btn_close_normal-png.png`, `btn_close_{over,pressed,disabled}.png` (famille mixte : vérifier la cohérence, ne pas présumer qu'ils sont interchangeables)
- `btn_arrow_pagination_{normal,over,pressed,disabled}.png`

**Checkboxes et onglets — 6 :**
- `Assets_UI_Themes_darkStone_common_btn_checkbox_{normal,selected}-png.png`
- `Assets_UI_Themes_darkStone_common_bg_tab_selected_normal-png.png`
- `Assets_UI_Themes_darkStone_common_bg_tab_disabled_{normal,over,pressed}-png.png` (suffixe « disabled » peut désigner une variété de fond ; vérifier l'usage réel)

**Fenêtres / bordures — 8 :**
- `window_border_top.png`, `window_border_bottom.png`, `window_border_top_right.png`, `window_border_popup_bottom.png`
- `Assets_UI_Themes_darkStone_common_bg_small_border_light-png.png`
- `Assets_UI_Themes_Figma_window_headerHighlight-png.png`, `Assets_UI_Themes_Figma_window_windowShadow-png.png`, `Assets_UI_Themes_Figma_window_ornaments_ornamentStandard-png.png`

**Icônes navigation — 8 :**
- `Assets_UI_Themes_Figma_menuIcons_1x_{guide,quest,success,encyclopedia,character,dofus,map,inventory}-png.png`

**Identité — 1 :**
- `logoDofus.png` : **référence de provenance uniquement** ; ne pas remplacer la marque Atlas par DOFUS.

## E. Architecture sans régression

- Source canonique actuelle : `app/ui/theme.py` (`PALETTE`, `TYPOGRAPHY`, `THEME_TOKENS`, `render_theme_template`), `app/ui/components.py` (`AtlasButton` et variantes), et styles locaux de `app/modules/encyclopedia/views/guide_featured_home.py`. Ne **pas** introduire une seconde palette concurrente par module : créer un seul thème `dofus_unity` activable, avec fallback au thème Atlas actuel. La valeur par défaut pourra être basculée une fois que toutes les surfaces principales et la distribution auront été validées.
- Qt stylesheet QSS seul ne permet pas nécessairement tous les états / images extensibles ; utiliser un style centralisé, peinture ciblée ou `QBorderImage` quand prouvé compatible, sans injecter des sous-classes pour chaque bouton.
- WebView : harmonisation CSS basée sur les mêmes tokens ; ne pas appliquer des fonds opaques sur le ciel ; traiter séparément les contenus externes difficiles à styler.
- Conserver objectName et property state déjà utilisés, connexions signals/slots, accessibles names, progression vérifiée, identité des personnages, cache image. Thème = présentation, pas refonte des comportements.
- PR #252 garde exclusivement la géométrie de l'en-tête Guide Succès, PR #253 la colonne droite/navigation, PR #250 la validation multi-personnages. Ce complément DOFUS Unity à #254 **n'autorise aucun débordement fonctionnel ou re-layout** sur ces PRs.
- Mettre à jour les exports/manifestes de distribution et les ressources disponibles hors ligne **uniquement après validation des droits** ; ne pas ajouter de LFS pointer non matérialisé ou un chemin `C:\Users\Rabsk\...` dans l'exécutable.

## F. Critères d'acceptation

- [ ] Réception des **47 originaux** (pas uniquement JPG planches et métadonnées), validation de dimensions/alpha/doublons, mapping du vrai état de chaque texture et droit de distribution.
- [ ] Copie de fond source contrôlée contre SHA-256 et détourage non destructif des trois icônes au coin haut droit ; capture de l'app réelle sans distorsion ni filtre opaque.
- [ ] Familles `AtlasButton` et menus testées : clic souris, clavier, survol, appuyé, disabled, focus, forte luminosité du fond ; bordures non étirées.
- [ ] Lexend/Rowdies intégrées par sources autorisées (fallback Segoe UI), tailles, glyphes français et rendu DPI 100/125/150 % ; tester libellés longs et texte à 125/150 %.
- [ ] Accueil Guides PR #254 inchangé fonctionnellement (deux cartes, catégories, raccourcis, recherche supprimée) et rendu au thème conforme ; ne pas confondre visualisation maquettée et screenshot Doctor du QWidget réel.
- [ ] Couverture par captures Doctor utiles (accueil Guides ; Guide Succès Opti ; guide Ganymède réel si jouable), **pas une avalanche de screenshots**. Ajouter captures globales shell / Organizer si nécessaire pour prouver le thème global et uniquement ces vues.
- [ ] Petit/grand écran : panneaux lisibles, pas de superposition ni bouton perdu, colonne et en-tête respectent PR #252/#253.
- [ ] Tests ciblés : `test_guide_library_home`, `test_guide_home_two_columns`, `test_guide_home_async_images`, `test_guide_home_image_cache_budget`, `test_guide_image_memory_policy`, `test_doctor_ui_qt` + tests du thème / boutons / packaging ajoutés selon code.
- [ ] Mesurer RAM au démarrage, après Guide, retour Home, multiple changements de thèmes/pages. Pas de chargement récurrent de 3 359 images ni de régression RAM non qualifiée.
- [ ] CI/Doctor adaptatif sur **SHA final seulement**, après tests locaux strictement ciblés. Aucune FULL répétée ; aucun PASS annoncé sans preuves, aucune fusion avant tests et contrôles de distribution exact-SHA.

## G. État de réalisation au moment de l'ajout

**Spécification intégrée à #254 ; thème global NON encore implémenté ; droits et binaires sources non vérifiés ; aucune certification finale.** Ne pas marquer cette section « terminée » en confondant l'inventaire fait sur le PC de l'utilisateur et l'intégration Windows / Git du thème.
