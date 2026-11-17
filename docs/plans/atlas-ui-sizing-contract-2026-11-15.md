# DOFUS ATLAS — dimensions et responsive (PR #365)

Statut : **P0 Dev UI implémenté ; adoption globale encore à faire**.
Le présent document ne certifie aucune recette Windows ni aucune capture.

## Architecture retenue

- Source Qt-free : `app/ui/unity_palette.py` (tailles, espacements, presets,
  contraintes réutilisables et breakpoints).
- Fenêtre réelle : `app/constants.py` lit les presets compact/standard ;
  ne plus dupliquer ses quatre nombres de dimension.
- Composants communs : `app/ui/components.py` réutilise les métriques de
  dialogue ; `app/ui/theme.py` conserve son QSS global et ses tokens historiques.
- Dev UI : la famille existante `metrics` expose la table complète et une
  grille de trois vrais widgets Qt dont les emplacements restent fixes
  indépendamment de la largeur du conteneur.
  Elle ne contient pas de moteur de layout parallèle, de palette locale ou de
  fausse capture Windows.
- La sélection d'un format **plafonne la largeur** de la démonstration, mais
  n'agrandit pas artificiellement une petite fenêtre. Le reflow dépend de la
  largeur réellement utilisable, et les dimensions indiquées sont des
  **formats de référence**, pas une simulation de DPI physique.

## Références de départ (à valider visuellement)

| Fenêtre | Largeur × hauteur |
| --- | ---: |
| Compacte (minimum réel) | 900 × 600 px |
| Standard (initiale réelle) | 1180 × 720 px |
| Grande | 1440 × 900 px |
| Full HD | 1920 × 1080 px |

**Décision d'architecture (15/11/2026) :** la structure d'une page ne
change jamais d'ordre ni de colonne au redimensionnement. Les trois panneaux
de démonstration utilisent toujours la même rangée 50/25/25.
Les breakpoints historiques restent disponibles uniquement pour les
*collections de cartes indépendantes*, jamais pour déplacer les modules,
sous-menus ou zones de sélection d'une page.

## Contrôles et garde-fous

- Garder les hauteurs de contrôles existantes (24 / 32 / 40 px) et les
  tailles d'icônes (16 / 20 / 24 / 32 px) pendant la validation initiale.
- Les modules à peu de contenu ne s'étirent pas verticalement pour
  compenser le vide ; les listes/cartes/éléments détaillés reçoivent
  préférentiellement l'espace restant.
- Ne pas écraser les dimensions des images métier, canvases, portraits,
  raccourcis ou slots Organizer avec un `setFixedSize` global.
- Ne pas changer le moteur de l'Organizer (#325) ni les données Guides (#363).
- Respecter la palette Unity, le fond étoilé disponible et les styles
  déjà indexés, sans seconde implémentation de thème.

## Migration restant à faire (P1)

1. Inventorier chaque valeur fixe/mini/max des écrans et les qualifier :
   style commun, contrainte de contenu, exception de rendu ou redondance.
2. Raccorder les principaux conteneurs (Accueil, Personnage, Encyclopédie,
   Succès, Quêtes, Guides, Craft, Stuffs, Almanax, Réseau, Launcher,
   Organizer UI uniquement) aux tokens et aux règles de proportions.
3. Contrôler les cas 900×600 / 1180×720 / 1440×900 / 1920×1080,
   puis 125 % / 150 % DPI Windows avec vrais contenus.
4. Vérifier absence de défilement horizontal non voulu, textes tronqués,
   chevauchement, vide excessif et perte de fonctions au resize.
5. Captures visuelles réelles avant/après + contrôle interactions ciblé ;
   ne certifier aucune plateforme sans preuve de son exécution.

Tests ajoutés dans ce lot : contrats Qt-free de dimensions et grille Dev UI
(rendu, choix du format, positions constantes, index visuel préservé).
**Exécution locale non disponible dans l'environnement de ce lot** :
les validations Qt réelles restent à lancer avant la généralisation.

## Captures de référence à quatre résolutions

`tools/dev_ui_snapshot.py` produit à présent quatre captures **réelles de
QWidget Qt offscreen** (une par preset), avec les métadonnées
`viewport_profiles.<preset>.size/columns/horizontal_scroll_max`. Les images
sont nommées `dev-ui-responsive-compact.png`,
`dev-ui-responsive-standard.png`, `dev-ui-responsive-large.png`,
`dev-ui-responsive-full_hd.png`.

Les deux workflows Dev UI valident l'absence de défilement horizontal
pour chacun des formats. Les tests ne codent plus en dur un nombre obsolète
de familles (23 sont actuellement enregistrées).

Une capture Qt offscreen sous Windows n'est pas une preuve de DPI réel,
de polices installées chez l'utilisateur ou de rendu des données privées.
La recette manuelle reste requise avant fusion et généralisation P1.

## Correction issue des captures réelles du 15/11/2026

Les captures sous Windows Qt hors écran au SHA `7cb8a9f` ont mesuré
`horizontal_scroll_max=0` aux **quatre** tailles de référence (avec le
QSS global appliqué). Un test autonome reproduisait incorrectement le
rendu sans QSS et échouait sur les dimensions natives de Qt ; le test
reproduit désormais l'initialisation du vrai shell.

L'aperçu 1920×1080 montrait en outre un bandeau « Actions » occupant
inutilement toute la largeur : la grille à trois *modules* utilise désormais
une répartition 50/25/25 sur une seule rangée. Les modes une et deux
colonnes conservaient leur comportement précédent jusqu'au changement de
contrat du 15/11 ; voir décision ci-dessous.

## Contrat de stabilité validé pour la phase Dev UI — 15/11/2026

- Quatre **repères de calibration**, sans snap, sélection obligatoire ni
  largeur forcée : 900×600, 1180×720, 1440×900, 1920×1080.
- `UNITY_LAYOUT_PROFILE_PX` donne les marges/paddings/espacements aux
  quatre repères et `unity_layout_metrics(width)` interpole entre eux.
  En-dehors de ces repères, les valeurs restent plafonnées ; pas de marges
  qui grossissent indéfiniment.
- Les tailles sémantiques des contrôles, listes, sélections, flèches,
  menus déroulants et icônes restent liées à leurs tokens existants ;
  pas de zoom proportionnel généralisé.
- Les modules de structure conservent **exactement les mêmes rangées,
  colonnes et ordre** au resize. Seuls la largeur utile, les marges et
  le contenu flexible s'adaptent.
- La galerie Dev UI montre la disposition fixe 50/25/25 et les
  références d'espacement. Le pilote ne change pas l'Organizer métier,
  ni les guides de la PR #363.
- `tools/dev_ui_snapshot.py` compare les positions des trois vrais
  QWidget dans les quatre formats et refuse toute permutation.
- Pour le déploiement P1 : valider les minima réels des écrans, l'ancrage
  des popups et sous-menus, le défilement vertical sans barre horizontale,
  les troncatures, le focus clavier et les DPI Windows 125/150 %.

**Statut :** pilote Dev UI et contrat partagés ajoutés ; migration intégrale
des écrans et dialogues non encore certifiée. Les anciens screenshots
montrant 1/2/3 colonnes sont antérieurs au nouveau contrat.

## Lot suivant — géométrie des 23 familles Dev UI

Les 23 groupes de la galerie utilisent désormais `unity_layout_metrics(width)`
pour leurs marges latérales et leur espacement vertical. Les contrôles ne
changent ni d'ordre ni de colonne. L'implémentation réutilise le QVBoxLayout
déjà présent sur chaque groupe ; elle ne crée aucun nouveau moteur responsive.

La limite d'éléments visibles du menu partagé `AtlasComboBox` utilise
`UNITY_CONTROL_LIMITS["dropdown_visible_rows"]` (8 lignes), son délégué
la hauteur `UNITY_CONTROL_SIZES_PX["dropdown_row"]`. L'en-tête des dialogues
réutilise les tailles indexées de son icône et ses espacements. Les flèches,
les barres de progression et les contrôles Guide de Dev UI utilisent les
mêmes tokens que leurs composants de référence.

Une modification des tokens se propage aux consommateurs **qui y sont
branchés**, au prochain chargement du composant. Les dimensions spécifiques
d'un écran qui ne consomme pas encore ces tokens ne sont pas automatiques.
Les tests Qt ciblés vérifient les quatre dimensions et le maintien de l'ordre
des 23 familles.

## Adoption initiale dans le Guide réel — PR #365

L'en-tête commun de `shared_manual_guide_view.py` (employé par les
guides, sans en modifier les contenus) consomme maintenant les tokens
`progress_primary`, `progress_secondary`,
`progress_toggle_width/height` et les mêmes largeurs de
quantité/validation que la démonstration Dev UI. Les icônes compactes
utilisent le même rôle `icon_small`. Une modification du token partagé
est donc répercutée sur Dev UI **et** sur ce rendu Guide réel au prochain
chargement ; les autres vues qui n'ont pas adopté ces métriques restent
à migrer séparément.

Seules les tailles existantes ont été rebranchées ; aucune logique métier,
sélection de participants, traitement de quête ou donnée Ganymède changée.

## Index de géométrie par module — nouveau lot P0

Les tailles existantes des modules ont été relevées dans les sources et
regroupées dans `UNITY_MODULE_GEOMETRY_PX` et
`UNITY_MODULE_GEOMETRY_OWNERS`, avec une table inspectable dans la famille
« Dimensions » de Dev UI. L'Organizer reste indexé dans son dictionnaire
`UNITY_ORGANIZER_METRICS_PX` existant, étendu avec ses contraintes
réellement présentes. Les rôles ne créent aucune nouvelle taille visuelle.

Trois catégories sont distinctes : dimensions communes réutilisables
(`UNITY_SIZES_PX` et `UNITY_LAYOUT_SIZES_PX`), règles de resize des quatre
références (`UNITY_LAYOUT_PROFILE_PX`), et contraintes intrinsèques des
contenus (`UNITY_MODULE_GEOMETRY_PX`). Ces dernières ne doivent pas être
appliquées indistinctement à tous les modules.

**Attention** : l'inventaire ne certifie pas que chaque valeur est déjà
consommée. Cette distinction reste explicite dans Dev UI. La migration des
consommateurs est le lot suivant et doit conserver les dimensions réelles
sans changer leur placement.

## Couverture réelle de toute l'application — lot d'adoption #365 (17/11/2026)

Objectif existant ATUI-009..016 du contrat #364 : **une seule implémentation par
composant visuel réellement commun, aucun style local concurrent**. L'index
`UNITY_UI_FAMILY_INDEX` (23 familles) et les 12 entrées
`UNITY_UI_CONSUMERS` recensent des propriétaires et exemples, **pas** une
preuve d'adoption intégrale. Ne pas ajouter de deuxième palette, framework,
registre de style ou couche de thème.

### Matrice de vérification obligatoire avant Ready

Partir des **13 scénarios réels** de `tests/capture_app_shell_ui.py` :
Accueil, Organizer, Paramètres, Dev UI, Almanax, Craft, Équipement,
Carte du monde, Personnage, Quêtes, Guides, Succès et Bestiaire. Compléter
avec les sous-vues et le module Réseau, puis avec le Launcher Tk indépendant,
les overlays Organizer/radial/splash et toutes les familles de dialogues
de `tests/capture_app_popups_ui.py` (dont menus/contextuels, calendrier,
préchargement, ressources Craft, Leveling, Route, images zoomées, Zaap,
confirmation/erreur, popup de sélection).

Pour **chaque écran et fenêtre**, comparer les mêmes composants aux
familles Dev UI existantes : boutons/états, champs/sélecteurs numériques
et listes, menus, onglets, navigation/fil d'Ariane, tableaux, panneaux,
couleurs/polices/liens, icônes transparentes, badges/progression,
focus/clavier, tooltips, scroll et tailles/espacements. Examiner les
widgets créés dynamiquement, y compris leur état après retour Home.
Les 12 propriétaires indexés ne remplacent pas cet inventaire :
Paramètres et Dev UI doivent être explicitement contrôlés, et l'Almanax
est construit dans `main.py`, pas seulement `home_page.py`.

Pour chaque divergence, consigner **fichier + widget + consommateur
réel + propriétaire canonique + décision** :
- dupliqué : raccorder au composant/token existant et tester la propagation ;
- spécifique métier : garder la géométrie/le dessin nécessaire, mais utiliser
  les couleurs, états et typographies communs, avec motif documenté ;
- prototype sans consommateur (animations, notifications flottantes) :
  ne pas construire un service nouveau sans usage démontré.

Les 4 repères 900×600, 1180×720, 1440×900, 1920×1080 doivent conserver
rangées/colonnes/ordre. Vérifier aussi DPI Windows 125/150 %, contenu long,
nombres négatifs/préfixes/suffixes, popup ancrée, clavier, absence de coupe
et de scroll horizontal involontaire. Les contrôles Qt offscreen ne valent
pas recette Windows/Dofus en conditions réelles.

### Partage des responsabilités et critères de sortie

**#365** détient l'UI commune et son adoption globale.
**#363** détient l'import/les données/la certification du pilote Cawotte :
`SharedGuideManualView` et `SharedGuideManualCard` restent le
lecteur/conteneur commun de **tous** les guides, sans en-tête Cawotte
parallèle. Le suivi #433 ne reporte **pas** la création de styles communs
dans #363 ; il suit uniquement la conformité des données et le branchement
réel des guides autorisés. Le Launcher conserve son adaptateur Tk ; Organizer
conserve ses dessins/gestes métier, mais pas une palette concurrente.

Sortie demandée pour ATUI-010/011/013/015/016 : matrice couvrant chaque
écran/overlay/popup, absence de duplication prouvée ou exception justifiée,
tests de propagation des tokens sur les consommateurs vérifiés, captures
comparées et tests ciblés **sur HEAD exact**. Les statuts DONE actuels du
rapport #365 sont des déclarations d'implémentation, pas un certificat
d'exhaustivité ; toute lacune trouvée doit être corrigée ou explicitement
requalifiée avant Ready. Aucun effet ni animation optionnels ajoutés pour
remplacer cette vérification.

## Extension de la couverture Dev UI — 17/11/2026

Le registre de référence existant `UNITY_UI_CONSUMERS` et sa projection
`UI_CONSUMER_INDEX` comptent désormais **18 zones**, dont les 13 vues
du véritable shell (`tests/capture_app_shell_ui.py`) : Accueil, Organizer,
Paramètres, Dev UI, Almanax, Craft, Équipement/Stuffs, Carte du monde,
Personnage, Quêtes, Guides, Succès et Bestiaire. Il conserve aussi les
consommateurs Réseau, Launcher Tk et l'agrégat Outils.

La section « Couverture » de Dev UI présente également **12 scénarios de
popups/dialogues**, issus des vrais widgets de la fixture
`tests/capture_app_popups_ui.py`, et **4 surfaces d'overlay/démarrage**
(Organizer radial et sélection, splash Unity, préchargement). Chaque ligne
renvoie au **fichier source existant** ; ce sont des inventaires,
**pas des copies de widgets ni des maquettes de nouveaux comportements**.
Le Launcher reste Tk, l'Organizer garde ses interactions métier.

Le contrat Qt vérifie la correspondance entre les scénarios du shell et
les 18 entrées, les 12 scénarios de popups de capture, et refuse
toute nouvelle feuille QSS locale sur les fichiers Qt indexés.
`main.py` n'a que quatre appels `setStyleSheet` explicitement
autorisés : les applications du **thème global** et le fond transparent
du splash natif. Tout autre appel depuis le shell doit faire échouer
ce garde-fou.

**Ce qui reste à faire :** le catalogue couvre davantage de véritables
surfaces, mais l'existence d'une ligne ne prouve ni la présence d'une
démonstration Qt de **chaque** variante métier, ni l'absence de tous les
widgets hors registre. Recenser les derniers composants dynamiques,
comparer leur UI réelle aux 23 familles Dev UI, raccorder les styles
communs manquants et contrôler la propagation / resize par captures
Windows exact-SHA. Les notifications flottantes et animations restent
des prototypes sans usage production certifié ; ne pas inventer de
nouveau service ou effet pour cocher artificiellement une case.

## Dialogues et popups — mutualisation sans usine à widgets (17/11/2026)

**Décision produit (PR #365) :** ne pas confondre *12 scénarios de
capture* avec 12 implémentations souhaitées. Dev UI est la **référence
de styles, composants et variantes** ; les fenêtres métier sont leurs
consommateurs. `tests/capture_app_popups_ui.py` vérifie des
présentations existantes, **ne définit pas** l'architecture.

### Composition commune existante (aucune nouvelle classe)

- `AtlasDialog` dans `app/ui/components.py` est le conteneur des
  **dialogues classiques** ; il fournit l'objet de thème, les marges
  et espacements partagés et la largeur minimale indexée. Son en-tête
  est `AtlasDialogHeader`, les boutons sont `AtlasButton`.
  Le contenu, les textes, les boutons disponibles, la modalité et
  les actions métier appartiennent **au consommateur**. Le
  dimensionnement doit suivre le contenu et les limites de fenêtre,
  sans taille fixe globale appliquée à toutes les fenêtres.
- La galerie Dev UI montre **cinq variantes interactives d'un
  même `AtlasDialog`** : information, attention, erreur,
  confirmation (Annuler/Valider) et formulaire (case/quantité
  dimensionnée par `fit_unity_number_spinbox`). Ces exemples
  sont sans sauvegarde ni action métier : une démo n'est pas
  un deuxième moteur de dialogue.
- Les **menus et suggestions** restent des widgets Qt légers
  (`QMenu`, `AtlasComboBox`, liste de suggestions Zaap), mais
  consomment la palette et les états partagés.
- Les **surfaces spécifiques** (zoom d'image non modal,
  radial Organizer, splash, préchargement avec handoff) conservent
  la géométrie et les interactions nécessaires. Elles réutilisent
  les tokens/states compatibles ; ne pas leur imposer
  `AtlasDialog` ou le resize d'une fenêtre de confirmation.

L'inventaire secondaire **déduplique** désormais le préchargement
listé initialement dans les dialogues et les overlays. Les 12
scénarios popup + 4 références d'overlay représentent **15 surfaces
distinctes** dans Dev UI, **pas 15 composants à construire**.
Les tests de capture gardent leurs scénarios sans suppression
de fonctionnalité.

### Audit ciblé du restant — code inspecté au HEAD de ce lot

| Source | État observé | Traitement |
| --- | --- | --- |
| `main.py:CloseActionDialog` | Hérite déjà de `AtlasDialog` | Préserver, contrôler les actions fermeture/réduction |
| `app/pages/craft_page.py:CraftResourceDialog` | `QDialog` avec header, marges, actions propres | Candidat prioritaire à raccordement, sans toucher aux quantités ni cases |
| `app/pages/craft_page.py:ItemSetDialog` | `QDialog` et contenu/liste de panoplie propre | Raccorder seulement la présentation commune, préserver l'ajout des objets |
| `app/pages/craft_page.py:LevelingDialog` | `QDialog`, header et footer locaux | Réutiliser la composition commune après vérification de la popup et du clic métier |
| `app/pages/craft_page.py:RouteDialog` | `QDialog` avec zoom/navigation spécifique | Garder la logique et la zone image, uniformiser seulement le contour/header/actions compatibles |
| `app/ui/preload_popup.py:PreloadProgressPopup` | `QDialog` sans cadre, cycle de démarrage/handoff | Exception légitime ; ne pas imposer `AtlasDialog` classique |
| `app/modules/encyclopedia/views/guides_view.py:SolutionImageLabel` | `QDialog(Qt.Popup)` pour le zoom | Exception non modale adaptée aux images |
| `app/storage.py:ZaapWidget` | Liste de suggestions ancrée et dimensionnée à l'écran | Exception popup légère, pas un dialogue modal |
| `app/pages/organizer/radial_overlay.py` | Overlay `QWidget` radial spécialisé | Ne pas modifier les gestes ni le diamètre métier |

**Non prouvé à ce stade :** qu'aucun autre `QDialog`, composant
local ou panneau dynamique ne reste hors de ce sous-ensemble inspecté.
Un inventaire de code et des consommateurs sur la totalité du dépôt,
puis les captures Qt comparées au HEAD final et les tests Windows,
restent nécessaires. Une conversion de conteneurs métiers constitue
un refactor structurel : obtenir d'abord Graphify exact-SHA et les
contrats Doctor, conserver les callbacks, l'accessibilité, Échap,
le focus, la persistance et le rendu aux 4 tailles de référence.

### Critères de sortie supplémentaires

1. Chaque dialogue classique testé utilise **les mêmes tokens de
   matériaux, typographie, boutons, marges et en-tête**, ou une
   exception documentée justifiée par un comportement spécifique.
2. Le contenu métier est distinct de la structure commune ; aucune
   deuxième palette, feuille QSS complète ou copie d'`AtlasDialog`
   ne doit être créée pour une seule utilisation.
3. Les listes/suggestions et overlays ne sont **pas** remplacés
   par des fenêtres lourdes ; préserver leur focus, ancrage, fermeture,
   interactions clavier, zoom et comportement non modal.
4. Test ciblé des cinq variantes Dev UI et des vrais cas métier ;
   comparaison de captures, absence de scroll horizontal, et
   tailles réelles à 900×600, 1180×720, 1440×900, 1920×1080.
   Ne pas revendiquer `PASS` sans exécution au HEAD exact.

## Catalogue réellement actionnable : quatre fenêtres Craft et comptage des primitives

Dev UI affiche désormais un **sélecteur `AtlasComboBox` unique et un
bouton `AtlasButton` unique** pour ouvrir les quatre *vrais* dialogues
de `app/pages/craft_page.py`, avec des exemples sans données
personnelles ni écritures :

- `CraftResourceDialog` — ressources et quantités ;
- `ItemSetDialog` — panoplie et éléments ;
- `LevelingDialog` — métier et paliers ;
- `RouteDialog` — navigation d'une route sans capture inventée.

**Ne pas confondre ces quatre usages avec quatre nouvelles classes ajoutées
à la bibliothèque** : les classes existaient déjà. Cette démonstration
ne transforme pas leur héritage `QDialog` en `AtlasDialog`. Leur
migration visuelle vers le conteneur/en-tête commun reste un travail
séparé, soumis à l'audit Graphify des consommateurs réels.

La section Couverture affiche des **compteurs d'implémentations et
variantes**, dérivés de la source existante plutôt que maintenus dans
un tableau concurrent :

| Élément contrôlé | Propriétaires / implémentations mutualisées | Variantes / usages actuellement référencés |
| --- | --- | --- |
| Boutons classiques | 1 `AtlasButton` | 13 rôles dans `BUTTON_OBJECT_NAMES` ; les contrôles spécialisés restent distincts seulement si leur comportement le justifie |
| Menus de sélection | 1 `AtlasComboBox` | Quantités d'options propres à chaque écran |
| Compteurs numériques | `QSpinBox` Qt + 1 règle `fit_unity_number_spinbox` | Min/max, x/x et suffixes propres à chaque contexte |
| Dialogues classiques | 1 `AtlasDialog`, 1 `AtlasDialogHeader` | 5 variantes dans la démonstration |
| Dialogues Craft | 4 `QDialog` déjà présents à **raccorder** | 4 usages prévisualisables, aucun clone de fenêtre créé |
| Popups et overlays | Les widgets Qt ou métier existants | 15 scénarios distincts indexés, pas 15 composants à créer |

Objectif de simplification : **moins de propriétaires de style et de
conteneur, pas moins de fonctionnalités ni de cas d'usage**. Ne pas
créer de superclasse abstraite ou de moteur popup supplémentaire,
ne pas convertir le préchargement/zoom/Zaap/radial en modaux.

Tests ajoutés dans `tests/test_dev_ui_page.py` : ouverture des quatre
vraies fenêtres, classe effective, absence de stylesheet local, compteurs
liés aux rôles et variantes existants, absence d'écriture dans les exemples.
**Exécution Qt/Doctor/Windows exacte-SHA à effectuer : NOT_RUN** dans
cette session. Les preuves visuelles et l'inventaire exhaustif des widgets
dynamiques restent des critères obligatoires de #365.


## Mutualisation appliquée — 18 besoins Dev UI et quatre dialogues Craft

**État du code (remplace le restant Craft annoncé dans les lots précédents) :**

- `CraftResourceDialog`, `ItemSetDialog`, `LevelingDialog` et
  `RouteDialog` héritent désormais **tous d'`AtlasDialog`** dans
  `app/pages/craft_page.py`. Ils réutilisent chacun le même
  `content_layout` et `AtlasDialogHeader`, sans classe de thème
  supplémentaire ni QSS local. Les fenêtres conservent leurs callbacks,
  choix, images, scroll et navigation métier ; leurs dimensions de
  démarrage restent les métriques Craft indexées dans
  `UNITY_MODULE_GEOMETRY_PX`. Pour garder la densité antérieure,
  les quatre fenêtres utilisent `AtlasDialog(density="compact")`,
  avec les marges 14×12 et l'écart 8 indexés dans
  `UNITY_LAYOUT_SIZES_PX` (variante `normal` inchangée).
  La fenêtre Panoplie vide reste prise en charge (`item_set=None`).
- La fenêtre **Ressources Craft reste non modale** côté `CraftPage` :
  `show_resources()` applique `dialog.setModal(False)` avant
  `show()`. Les autres dialogues restent modaux dans leurs flux
  `exec()`. La confirmation à Échap propre aux ressources est
  conservée. Tests ajoutés dans `tests/test_craft_fixes.py` et
  `tests/test_dev_ui_page.py` : héritage commun, conteneur unique,
  en-têtes réels, panoplie vide et fenêtre ressources non modale.
- Le **panneau Couverture** de Dev UI recense **18 besoins** (boutons,
  sélections, quantités, fenêtres, cases, saisie, progression, panneaux,
  titres, bordures, glass, images, navigation, onglets, listes, tooltips,
  badges, scroll/resize). Ce sont des **entrées d'audit** rattachées aux
  23 familles UI existantes, pas 18 nouvelles classes.
  Chaque ligne affiche la base commune, le nombre de sélecteurs QSS
  indexés ou de variantes explicitement connues, le nombre de modules
  dont les **fichiers sources enregistrés contiennent un appel
  correspondant**, et l'écart réellement vérifié. Les modules
  agrégateurs et la galerie Dev UI sont exclus du décompte afin
  d'éviter un faux double comptage. Les propriétaires affichés viennent
  directement de `UNITY_UI_FAMILY_INDEX`.
- Les chiffres sont **des indices statiques, pas un relevé des widgets
  instanciés ni une preuve de migration**. Les doublons non analysés
  affichent « Non audité » plutôt qu'un faux zéro. La famille Dialogues
  relève automatiquement la transition **Craft 4/4 sur AtlasDialog,
  0 classe Craft encore héritée directement de QDialog**.
  `UI_MUTUALIZATION_TARGETS` et
  `inspect_ui_mutualization_sources()` vivent dans l'index
  `app/ui/ui_registry.py`, sans créer une seconde palette ou un
  moteur de composants.

### Suite de l'audit, avant Ready

Vérifier le rendu interactif réel des quatre fenêtres aux quatre
tailles et sur Windows, en particulier la largeur de Panoplie :
`item_set_dialog_size=(390,460)` et
`dialog_min_width=400` impliquent désormais une largeur minimale
effective de 400 px. Examiner les modules non encore certifiés de
la matrice et les chemins de création dynamique ; distinguer les
widgets métier légitimes d'une duplication visuelle avant toute
conversion. Le préchargement frameless, les suggestions Zaap,
le zoom Guide, la carte et le radial Organizer conservent
leurs mécanismes dédiés.

**Exécution de Qt/Doctor/Graphify/captures Windows au HEAD de ce lot :
NOT_RUN dans cette session.** Le travail de code est présent en PR,
pas déclaré certifié ou fusionnable sans validation exacte-SHA.

## Audit des consommateurs — boutons Zaap et sélecteurs Succès (17/11/2026)

- Le dernier bouton de nom de favori Zaap identifié dans `app/storage.py` utilise désormais `AtlasButton` avec **`variant="zaap_favorite"`**, dont le rôle existant `favoriteChipName` est déclaré dans `BUTTON_OBJECT_NAMES`. Le style global `#favoriteChipName` et le conteneur existant `#favoriteChip` restent propriétaires du rendu. Aucune nouvelle classe ni palette n'a été créée. Dev UI montre ce rôle réellement partagé dans sa famille **Boutons** ; l'index QSS et le contrat visuel le répertorient.
- Les champs de niveau minimum et maximum du panneau `AchievementFilterPanel` consomment désormais les mêmes règles `fit_unity_number_spinbox` que Quêtes, Craft et Guides. Les bornes 0–999, les signaux et les filtres métier n'ont pas changé.
- Le registre `UI_CONSUMER_INDEX` associe maintenant explicitement `app/storage.py` à Organizer (Zaap) et `app/modules/encyclopedia/widgets/filter_panel.py` à Succès. Ce sont des références à leurs vrais propriétaires, pas de nouveaux modules UI.
- La matrice de Dev UI utilise un scan **AST des constructeurs Qt** dans les fichiers consommateurs enregistrés pour indiquer le nombre réel de créations directes `QPushButton` et `QComboBox` et leurs emplacements ; les modules incomplets sont signalés, jamais considérés comme sans doublons. Les autres familles restent marquées « Non audité » si aucun contrôle de doublon exhaustif n'existe.
- Le bouton **masqué** `FeaturedGuideCard.open_button` était encore un `QPushButton` brut. Il est désormais un `AtlasButton` conservant son `objectName`, son état masqué, son signal d'ouverture et l'activation au clavier de la carte. Un test Qt ciblé a été ajouté sans modifier l'interface visible.
- Le test de contrat exige maintenant **zéro instanciation directe `QPushButton` / `QComboBox` dans les sources Qt enregistrées** (hors Dev UI elle-même, zones agrégées et Launcher Tk) ; les boutons Qt spécialisés `QToolButton`, les champs natifs et les popups non modaux restent permis selon leur fonction. Le garde-fou porte sur cette couverture mesurée, pas sur tout fichier Python non indexé.

**Bilan de code vérifié sur GitHub :** 1 classe `AtlasButton` et **13 rôles visuels** (le style Zaap existait déjà avant son référencement comme variante), 1 `AtlasComboBox`, 1 helper numérique partagé et 4 fenêtres Craft sur `AtlasDialog`. Cette mesure ne prouve pas l'unification exhaustive des widgets dynamiques de tout le dépôt.

**Restant avant Ready :** lancer les tests Qt réels, contrôler les comportements Zaap/favoris et les filtres Succès, puis les captures Windows exact-SHA et le resize aux quatre tailles. Aucun résultat d'exécution Qt/Windows nouveau n'est revendiqué pour ce lot.
