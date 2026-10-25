# Complément demandé le 24/10/2026 — thème intégral DOFUS Unity pour Atlas


> **Mise à jour des sources réelles (24/10/2026, commit `f17b4724`) :** le dépôt contient maintenant l'archive du **fond original**, neuf sous-archives ZIP regroupant les **103 PNG originaux** réellement transmis, et le ZIP de sélection avec manifeste/aperçu/script. Voir `docs/design/dofus-unity/README.md`. Les **47 sprites UI précis** du manifeste, les **10 fichiers TTF** et le **fond PNG individuel** ont ensuite été importés dans `app/assets/themes/dofus_unity` (voir section H). Les ZIPs déjà présents ne sont pas encore utilisés par le runtime. Les mentions ci-dessous « non versionnée ici » décrivent l'état initial de la préparation avant ce commit.

> **À réaliser dans la PR #254 existante, sans supprimer ni réécrire les fonctionnalités déjà implémentées.** Ce document est une spécification versionnée, PAS la preuve que le thème est intégré. Le fond original et 103 PNG extraits sont joints à la branche en ZIP ; les 47 PNG spécifiques de boutons/cadres et les 10 TTF restent sur le PC utilisateur, non joints. Les archives existantes ne sont pas intégrées au runtime. Aucune certification Windows ou preuve de rendu n'est attestée ici.

## A. État contrôlé de la PR #254

La branche `plan/guides-20261024-06-accueil-guides-bibliotheque` contient déjà des modifications applicatives sur `GuideCatalogView`, `GuideHomeColumns`, `FeaturedGuideCard` et `EncyclopediaPage` :
- exactement deux grandes cartes **Guide Succès Opti** et **Sylvestre Opti**, accessibles souris/clavier ;
- Bonta/Brâkmar dans l'arbre Alignements ; familles Optimisés/Alignements/Dofus/Dimensions/Éliocalypse/Régions/Événements/Îles/Autres ;
- suppression de la recherche globale Encyclopédie, de la recherche Guides et des filtres Tous/En cours/Terminés ; les recherches Quêtes/Succès/Sommaire demeurent ;
- grille Dofus adaptative, sous-menus persistants, sources Ganymède metadata-only inactives, progressions réelles sans « 0 % » inventé ;
- retour catalogue léger et captures Doctor prévues. Ne pas régresser ces fonctions.

## B. Références visuelles *réelles*

**Fond validé par l'utilisateur :** capture originale de la sélection de personnages DOFUS Unity, 1919 × 1079, SHA-256 `3834e92f6432019e2fde2b5f0ccb7f3b2236fda48ea7a6d368c60a660ef5fdeb`. Capture détenue dans la conversation et désormais versionnée dans une archive ZIP sous `docs/design/dofus-unity/sources/` (pas encore déployée dans l'app). Scène cosmique cyan / bleu / violet, étoiles, nuages et rochers flottants. Les trois icônes natives en haut à droite ne doivent pas être reproduites en éléments décoratifs Atlas ; préparer un fond nettoyé *sans toucher à l'original*, après validation.

**Extraction réalisée localement sur Windows :**
- DOFUS Unity installé sous `%LOCALAPPDATA%\Ankama\Dofus-dofus3`.
- `Picto/UI` : 44/44 bundles traités, 8 537 PNG.
- cinq bundles d'UI : `uiassets_assets_.bundle`, `uiassets_assets_1x.bundle`, `uiassets_assets_2x.bundle`, `uidarkstone_assets_all.bundle`, `uielements_assets_all.bundle`.
- Extraction ciblée `--force-object` : **3 359 PNG et 10 TTF** déclarés par l'utilisateur, et **47 candidats visuels** présélectionnés dans `Atlas_UI_Manifest_Cible.csv` (le manifeste des 47 noms est désormais versionné dans `06b-dofus-unity-asset-manifest.csv`, mais les 47 PNG originaux et les 10 TTF SONT maintenant dans Git (section H)). La sélection visuelle et les ZIP de référence de la conversation ne remplacent pas ces 47 PNG originaux, distincts des 103 PNG déjà archivés.
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

Racine locale de l'extraction : `%USERPROFILE%\Documents\Atlas-Dofus-UI-Composants`. Les préfixes `uiassets_assets_*`, `uidarkstone_assets_all`, `uielements_assets_all` correspondent aux dossiers créés par le script Windows. La liste candidate de 47 noms est versionnée dans `docs/plans/guides-2026-10-24/06b-dofus-unity-asset-manifest.csv` et un importeur ciblé existe dans `tools/assets/import_dofus_unity_ui.ps1`. Les chemins et variantes doivent être réconciliés avec les **fichiers originaux** et leur rendu inspecté avant intégration.

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

**Spécification intégrée à #254 ; fond PNG original, 47 sprites ciblés et 10 polices TTF présents dans Git (section H) ; thème global NON implémenté dans le runtime ; droits de redistribution non validés ; aucune certification finale.** Ne pas marquer cette section « terminée » en confondant l'inventaire fait sur le PC de l'utilisateur et l'intégration Windows / Git du thème.


## H. Livraison des sources originales — 24/10/2026 (à jour)

- **47 PNG sur 47 importés individuellement dans Git** en `app/assets/themes/dofus_unity/sprites` (46 textures utilisables) et `app/assets/themes/dofus_unity/references/logoDofus.png` (identité de référence uniquement). Commit `756c2b02c192f3f8bd9a321934a752c45548f8a9`.
- **10 TTF sur 10 importés individuellement** sous `app/assets/themes/dofus_unity/fonts`. Commit `518924be8518fc48b264d7fa750238322a5ef836`.
- **Capture originale de fond PNG** également importée comme fichier individuel : `app/assets/themes/dofus_unity/background_selection_original.png`, SHA-256 `3834e92f6432019e2fde2b5f0ccb7f3b2236fda48ea7a6d368c60a660ef5fdeb`. Commit `4c2c9b9deeb103093b4a193a9ac00ef73c75d661`.
- Contrôle ZIP `Atlas-UI-Selection-Originale.zip` : 47 PNG, 10 TTF, 1 CSV, archive sans erreur CRC. Contrôle GitHub par lecture des blobs : `btn_green_normal.png`, `Lexend-Regular.ttf`, `Rowdies-Regular.ttf`, `logoDofus.png` et fond original, SHAs conformes.
- **Fichiers intégrés ≠ thème appliqué :** aucun branchement global QSS/Qt/WebView, aucun retrait des trois icônes du fond ni test Doctor/Windows réalisé à ce stade. Conserver la PR en brouillon.
- **Droits :** les familles de polices existent sous licence OFL en amont, mais les copies précises extraites du jeu, les sprites, le logo et la capture ne sont pas présumés libres. Ne pas produire ni publier de release réutilisant ces fichiers avant revue de licence/autorisations ; voir `app/assets/themes/dofus_unity/README.md`.


## Progression d'intégration — synchronisation avec main après PR #253

- [x] Base fusionnée sans écraser les modules de progression/navigation et les protections CI précédentes ; Doctor combine les contrôles #254 avec les scénarios #253.
- [x] Première couche de thème local **opt-in** via `ATLAS_THEME=dofus_unity` : tokens sémantiques communs, vrais états de boutons/checkbox/onglets lorsque présents, bordures 9-slice, fond en couverture centrée sans distorsion, unique pixmap cachée par shell, focus clavier préservé et repli en absence de ressources.
- [x] Par défaut, le thème Atlas reste intact ; aucune police extraite du jeu n'est enregistrée au runtime ni incluse par l'export Python-only vers l'App.
- [ ] Nettoyage fidèle des trois icônes de la capture d'origine, intégration visuelle de toutes les pages/WebView, licence/autorisation des sprites et des fonts, mesures DPI et RAM Windows, contrôle réel du thème et certification du SHA final. Aucun PASS visuel ou licence n'est revendiqué.

## Complément de code — habillage Qt/HTML

- [x] Palette et police centrale : Lexend/Rowdies **si installées légalement sur le système** ; aucun TTF extrait ne s'enregistre ni ne s'exporte automatiquement.
- [x] Styles spécifiques transparents des racines d'accueil, Encyclopédie, Organizer, panneaux, listes et dialogues, avec cartes foncées lisibles.
- [x] Boutons de navigation, actions primaires/secondaires, navigation, états hover/pressed/disabled, cases et onglets, focus Qt ; aucun remplacement fonctionnel de contrôles.
- [x] Icône de Guide depuis le sprite local pour les deux cartes majeures seulement, sans chargement massif au démarrage.
- [x] Texte HTML interne Quêtes utilise les mêmes tokens de police/palette Qt. La page Équipement ouvre un site **externe** : aucune injection CSS chez un tiers.
- [x] Tests unitaires synthétiques supplémentaires pour les PNG locaux, les états de bouton, les vues transparentes, le bitmap unique et le fallback.
- [ ] À prouver sur Windows : rendu exact DPI/mémoire, nettoyage du fond original des trois icônes et droits de distribution, captures de référence. Les assertions ci-dessus ne sont pas un PASS Windows.
