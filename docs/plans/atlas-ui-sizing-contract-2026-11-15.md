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
  grille de trois vrais widgets Qt réorganisés selon la largeur du conteneur.
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

La grille de démonstration utilise 1 colonne en-dessous de 560 px utiles,
2 colonnes entre 560 et 999 px, et 3 à partir de 1000 px. Ces seuils
portent sur la **largeur du contenu**, pas sur l'écran entier. Les modules
avec contraintes métier peuvent avoir une variante documentée.

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
(rendu, choix du format, reflow 1/2/3 colonnes, index visuel préservé).
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
