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
