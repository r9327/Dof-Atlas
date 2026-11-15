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
