# DOFUS ATLAS — Organizer : finition UI fidèle (cadrage uniquement)

> **SPEC ONLY — AUCUN CODE D'APPLICATION MODIFIÉ.**
> Contrat source exhaustif : [issue #428](https://github.com/r9327/Dof-Atlas/issues/428).
> Version fonctionnelle servant de base : [PR #425 fusionnée](https://github.com/r9327/Dof-Atlas/pull/425).
> Thème, composants et design system : [PR #365](https://github.com/r9327/Dof-Atlas/pull/365) / [issue #364](https://github.com/r9327/Dof-Atlas/issues/364).
> Capture réelle de contrôle : [PR permanente #422](https://github.com/r9327/Dof-Atlas/pull/422) — **ne pas fermer/fusionner**.

## Invariants non négociables

1. **Conserver le screenshot original et le code de #425** comme base réelle. L'objectif est une finition humaine sobre, pas une nouvelle UI, ni la reproduction artificielle d'un mockup IA. Taille, 5 modules, navigation, boutons, textes, raccourcis, icônes, rangées et géométrie inchangés.
2. **AUCUNE modification de police** (famille, taille, graisse), de typographie globale, des logos officiels ni des libellés. Aucun changement de thème : réutiliser les couleurs/tokens Unity officiels sans créer de palette locale.
3. Garder les 3 modules supérieurs et les deux inférieurs, personnages sur deux tiers et Zaap sur un tiers ; **8 slots en 2 colonnes de 4**, fenêtre compacte à hauteur de fin des personnages. Ne pas agrandir la fenêtre pour absorber des marges supplémentaires.
4. Garder le glass actuel de #425, **`GLASS_INTENSITY=0.5`**, et le rendre sobre : ne pas augmenter les reflets, contrastes verts, bordures brillantes, rayons, ombres ou effets iOS. Ne pas créer de nouveau matériau QSS/Qt.
5. Conserver le contrôle Macro/Miroir, ses raccourcis et son armement réel, les trois vitesses, Précédent/Suivant, Stop urgence, l'ordre personnages et les favoris Zaap 2×2. Ne pas modifier les moteurs/services ou d'autres modules.

## Slots Personnage — composition exacte attendue

**Sur chacune des 8 lignes, de gauche à droite** :
`[poignée drag & drop] [portrait/icône existante] [pseudo aligné à gauche] [étoile décorative SI premier personnage] ... [bouton raccourci existant à droite]`

- Retirer les étoiles cliquables et **toutes les cases, QLayouts, largeurs réservées, faux pads ou colonnes vides** qui les accueillaient. Aucun rectangle fantôme à leur ancien emplacement sur les 8 lignes.
- Sur **la première personne effectivement affichée dans l'ordre courant seulement**, placer une **unique étoile pleine, activée en permanence, immédiatement à DROITE du pseudo** (après un petit espacement constant). L'étoile est **non cliquable, non focusable, sans hover de bouton ni raccourci**. Aucune étoile dans les 7 autres lignes.
- **Tous les pseudos commencent près du bord gauche utile** (après poignée et portrait), au même décalage dans leur colonne ; les textes ne sont plus repoussés par les anciens favoris. La première ligne ne doit pas se décaler vers le milieu à cause de son étoile.
- Les raccourcis restent fixés à droite, avec les dimensions/marges existantes. Le nom peut s'ellipser proprement si trop long ; il ne recouvre jamais l'étoile ou le raccourci.
- Le premier personnage peut changer avec le glisser-déposer : **ne jamais coder en dur « Pandawa Witsis » ni une identité**. Si un emplacement est vide, l'indicateur suit le premier personnage effectif affiché. Après restart/reload, il reste cohérent avec l'ordre sauvegardé.
- Préserver le comportement réel des macros, du « personnage maître »/favori et des identités ; inspecter l'ancienne sélection de favori avant d'adapter son état. Un seul comportement canonique, aucun favori historique invisible ou désynchronisé.

## Couleur, contour, alignement

- Les fonds actuels des lignes sont trop proches du noir : les rendre **un peu plus présents, bleu ardoise / bleu-gris Unity** au moyen des tokens déjà disponibles ; contraste délicat par rapport au panneau « Personnage », légère variation verticale éventuelle **sans texture inventée ni nouveau coloris**.
- Préserver l'allure desktop professionnelle : bordures fines, reflets très discrets, relief réduit, padding uniforme, 8 lignes lisibles. Les boutons raccourcis se détachent modérément avec leur style partagé, sans aspect plastique ou mobile.
- Aucune nouvelle zone vide, ligne de texte, badge, décor, animation, contrôle ou colonne. Ne pas ajouter de carte pour une personnalité.
- La finition des contrôles communs relève de **#365 uniquement**. Ce lot Organizer doit adopter ce qui existe sans copier/recoder les classes de thème ou modifier la police. Si un défaut est global, ouvrir/traiter le point dans #365, pas ici.
- Les contraintes de taille compactes du screenshot source priment sur les proportions artificiellement étendues des générations d'images.

## Lots futurs (non exécutés dans cette PR de cadrage)

1. **Analyse ciblée** de `app/pages/organizer/organizer_ui.py`, `app/pages/organizer_page.py`, de la persistance `app/storage.py`, des composants `app/pages/organizer/glass_material.py` et des contrats UI canoniques de #365 ; comparer sans doublon avec #425.
2. **Placement étoile / suppression des espaces fantômes** : modifier uniquement la composition des slots et les dépendances de favori strictement nécessaires pour garder le fonctionnement cohérent.
3. **Finition locale des lignes** : contrastes existants, bordures, marges/alignement ; aucune refonte du panneau, ni police, ni matériau glass nouveau.
4. **Tests ciblés et capture Windows réelle** via #422, comparer avant/après au vrai screenshot pour 1/2/4/6/8 personnages, positionnements, slots vides, réorganisation, persistance, longs pseudos, DPI 100/125/150 et fenêtre compacte (référence 1290×500 et adaptation réelle sans débordement).
5. **Audit/Doctor/CI** sur le SHA exact : vérifier nul changement Macro/Miroir, Zaap, Stop, profil, raccourcis, temps de rendu/performance, composants communs. S'il y a changement fonctionnel des favoris, recette native Windows/DOFUS documentée séparément selon #424.

## Critères bloquants (issue #428)
OFIN-001 étoile unique décorative juste après premier pseudo ; OFIN-002 zéro ancien espace favori et alignement gauche ; OFIN-003 8 slots/reorder/persistance/commandes préservés ; OFIN-004 fond bleu-gris officiel plus lisible sans toucher police/layout/glass ; OFIN-005 aucun doublon de #365/#425 ; OFIN-006 tests Qt ciblés ; OFIN-007 screenshot Qt Windows au SHA exact ; OFIN-008 audit final et preuve distincte Unity si applicable.

**État initial : 0 développement, 0 test, 0 capture, 0 certification. Cette PR sert exclusivement à cadrer les travaux ; ne pas la fusionner en l'état.**
