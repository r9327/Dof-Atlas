# PR #225 — UI Guide Succès / Lanyel : REPRODUCTION FIDÈLE DE LA MAQUETTE VALIDÉE

Date : 18 octobre 2026. Branche : `feature/guide-ui-compact-20261018`.
**ÉTAT : design verrouillé, NON implémenté. Ne pas fusionner sans comparaison visuelle avec la maquette validée.**

## CONSIGNE ABSOLUE — pas de liberté sur l'UI

L'interface doit **ressembler exactement à la dernière maquette validée avec l'utilisateur**, en conservant le style visuel déjà en place du guide Lanyel (couleurs, fonds, composants, typographie, espacements, cartes et contrôles). Les maquettes précédentes ne priment pas sur les dernières corrections. Cette PR NE DOIT PAS être interprétée comme « refaire un design inspiré de ». **C'est une reproduction 1:1 de la composition acceptée, à l'exception des suppressions explicites ci-dessous.**

Ne pas inventer :
- panneau dédié aux déplacements / Zaaps, boutons « Copier la commande », badges sur les coordonnées, statut macro permanent, légende supplémentaire de transport ;
- bloc « Quêtes liées à cette fiche », bloc local « À préparer », « Sources du guide », « Succès liés », « Pourquoi cet ordre ? », « Étapes précédentes », « À suivre » ou « Destination suivante » ;
- grosse liste de personnages, cartes individuelles de personnages ou tableau multicomptes toujours visible ;
- changement de structure par rapport à la capture validée du panneau **Préparation générale du guide** : conserver la carte ouverte, ses quatre filtres, ses lignes concrètes et le bloc Pierres d'âme ; ne pas substituer l'ancien menu générique « PRÉREQUIS » du catalogue.

Si un détail visuel n'est pas explicitement documenté ici, **préserver l'existant/maquette**, ne pas improviser ; confronter les captures Doctor UI à la composition validée avant de déclarer PASS.

## STRUCTURE VISUELLE EXACTE, DANS CET ORDRE

\`\`\`text
┌─────────────────────────────────────────────────────────┐
│ Guide Succès / Dofus Sylvestre                    [⚙]   │
│                                                         │
│   (donut GLOBAL %)       Route       n / total           │
│                          ━━━━━━━━━━                     │
│                          Préparation n / total           │
│                          ━━━━━━━━━━                     │
│                          Succès      n / total           │
│                          ━━━━━━━━━━                     │
│                                                         │
│ [      Aller à la fiche      ] [Retour actuelle] [🗺]   │
├─────────────────────────────────────────────────────────┤
│ [ ▤ Préparation générale du guide              ▾ ]    │
│   (ouvert : Préparation complète ; Tout · Métiers ·      │
│    Potions · Objets ; exigences réelles ; pierres)       │
│    Pierres d'âme : possédé 50 | besoin 150 | manque 100 │
├─────────────────────────────────────────────────────────┤
│                                       [👥] [Sommaire ▾]  │
│       (Mes personnages : portraits si menu ouvert)       │
│       (Sommaire : demeure ouvert après choix d'une fiche)│
│ ┌─────────────────────────────────────────────────────┐ │
│ │ FICHE N · CHAPITRE X                               │ │
│ │ Titre court de la fiche                           │ │
│ │ [x,y] (clic identique ; trajet derrière)           │ │
│ │ Actions PNJ/combats/récoltes/drops...              │ │
│ │   [petit bouton Quêtes UNE fois par quête/fiche]   │ │
│ │   □ ×5 Nom exact du monstre                        │ │
│ │   Survol de ligne : nom de la quête                │ │
│ │                                                     │ │
│ │ [ Précédent ] [ Valider ] [ Suivant ]               │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
\`\`\`

Le dessin ci-dessus décrit la HIÉRARCHIE des éléments, **pas un redesign graphique**. Le rendu visuel réel doit conserver les composants, mesures et apparences approuvés de la maquette de conversation et du Guide Lanyel.

### 1. En-tête fixe et compact — LE NOM DU GUIDE CHOISI
- Le **titre principal** est **le titre exact du guide ouvert depuis la liste/catalogue**, sans texte générique : si l'utilisateur ouvre `Dofus Sylvestre`, en-tête `Dofus Sylvestre` ; s'il ouvre `Guide Succès`, en-tête `Guide Succès` ; même règle pour Lanyel ou tout autre guide. Le libellé varie dynamiquement au changement de guide, sans refaire tout le panneau. Le titre est la référence du guide sur lequel l'utilisateur a cliqué au catalogue, pas un bouton inventé pour changer de guide.
- **SUPPRIMER totalement le sous-titre `Progression générale du parcours`** et le titre générique `Guide optimisé`.
- Petit engrenage paramètres à droite du titre réel ; en dessous, donut global à gauche et exactement trois barres à droite : `Route`, `Préparation`, `Succès`, avec compteurs RÉELS. Garder les dimensions/couleurs retenues.
- **Ligne des boutons** : `Aller à la fiche` (large), immédiatement à côté `Retour à l'actuelle` (bouton visible avec libellé et icône retour), puis petit bouton Overlay icon-only. Ce bouton revient instantanément à la fiche active courante, par opposition à la fiche parcourue via Sommaire, flèches ou accès direct. Ne pas modifier la sélection active ni les validations ; bouton désactivé ou neutre si déjà sur l'actuelle.
- **En-tête non repliable, ne disparaît pas au scroll**. Pas de quatrième barre. Progression Route = fiches réellement validées / total, jamais index de navigation ; ne pas coder en dur les comptes fictifs de la maquette.

### 2. Préparation générale du guide — LA CAPTURE FOURNIE EST LA RÉFÉRENCE

**CORRECTION PRIORITAIRE (18 octobre 2026) : l'utilisateur a fourni une capture d'écran de la vraie maquette. Les précédentes instructions qui imposaient le mini-menu `PRÉREQUIS` de `GuidesView.CollapsibleInfoSection` étaient une mauvaise interprétation et sont annulées.** Ne pas conserver ce vieux menu à la place de la préparation complète. La composition souhaitée est celle de la capture utilisateur, **« à peu près »**, avec ses éléments distinctifs, dans le style Qt/Atlas/Lanyel. Cette section n'est pas la liste de prérequis de la fiche.

**Structure exacte du bandeau fermé :**
- Une seule bande arrondie compactement placée sous la rangée `Aller à la fiche` / `Retour à l'actuelle` / Overlay.
- À gauche, une **icône clipboard/liste** ; au centre le **titre `Préparation générale du guide`**, puis en gris la description **`Métiers, potions et objets · Parcours complet`** ; à droite chevron ouvrir/fermer.
- Ne pas afficher de remplacement `PRÉREQUIS`, de pastille de statut d'un guide du catalogue ou de compteur des prérequis du catalogue en lieu du vrai titre. Fermé par défaut ; clic sur la bande/chevron ouvre la carte complète, clic à nouveau referme.

**Structure exacte du contenu déroulé, comme la capture :**
- Une carte encadrée à l'intérieur du panneau, titre **`Préparation complète`** en haut.
- Sous le titre, sur **une même ligne** : onglets/filtre **`Tout` / `Métiers` / `Potions` / `Objets`**. `Tout` sélectionné par défaut ; changement de filtre sans refermer le menu ni modifier la fiche. Pas d'onglets hors de cette carte ni de recherche/formulaire géant.
- En dessous, lignes de **vraies exigences globales du parcours** avec petit rond de statut à gauche, une exigence concise et sa valeur calculée. Catégories possibles : `Alignement requis : Bonta`, `Métier requis : Alchimiste niveau 40`, `Potions de rappel et de cité`, `Ressources à acheter et à récolter` ; **ces exemples de la capture ne sont PAS des données réelles à hardcoder**. Afficher les noms/quantités réellement nécessaires pour le guide et ses personnages, regrouper/filtrer sans perdre des éléments. `Tout` affiche toutes les catégories ; `Métiers` uniquement les exigences métiers ; `Potions` les consommables/transport ; `Objets` les ressources/objets/captures, avec l'alignement et conditions d'accès dans `Tout` (ou sous-catégorie fiable si modèle prévu).
- Les ronds de statut ne sont pas des confirmations réseau fictives ni des validations de fiche ; ne montrer accompli que ce qui est prouvé ou déclaré de façon explicite. Ne pas inventer `Vérifier les métiers`, `Prévoir des potions` génériques à la place de vraies quantités et noms. Eviter les doublons et les objets acquis naturellement sur le trajet : cohérence avec #226.
- Après la liste, **fine séparation horizontale**, puis un bloc intégré **`Pierres d'âme du guide`** avec petite icône pierre et sous-titre **`Inventaire déclaré manuellement`**.
- Deux contrôles côte à côte à contour discret et coins très arrondis, tels que la capture : **`J'en possède`** = valeur saisissable (exemple 50), **`Total nécessaire`** = total affiché par le moteur (exemple 150, non modifiable si calcul fiable ; ne pas le déduire du seul nombre de fiches).
- En dessous : **`Stock disponible`** à gauche, **`50 / 150`** à droite, **barre de progression horizontale ambrée**, puis **`100 pierres manquantes`** avec icône d'attention. `manquantes = max(0, nécessaires − possédées)`; afficher 0 proprement si surplus. Afficher les types/puissances/besoins réels lorsqu'ils sont connus, sans remplacer le récapitulatif de la capture par une liste illisible.
- Petit texte de contexte tout en bas, discret : besoins calculés selon captures restantes, stock saisi **non présenté comme preuve d'inventaire réseau**. Pas de prérequis immotivés ni contenu hardcodé.
- Toutes les quantités et filtres sont **réellement fonctionnels** : mise à jour immédiate, saisie valide et non négative, sauvegarde après relance, recalcul si modification de progression réseau / participants / route. Métiers, potions, objets et accès ne doivent pas être traités comme des cases manuelles destinées à valider des quêtes.

**État ouvert, représentation textuelle de la capture :**

```text
┌───────────────────────────────────────────────────────────────┐
│ ▤  Préparation générale du guide                           ⌃ │
│    Métiers, potions et objets · Parcours complet              │
├───────────────────────────────────────────────────────────────┤
│  Préparation complète                                        │
│                                                               │
│  [ Tout ]    Métiers    Potions    Objets                      │
│                                                               │
│  ● Alignement requis : Bonta                         (exemple)│
│  ● Métier requis : Alchimiste niveau 40              (exemple)│
│  ● Potions de rappel et de cité                      (exemple)│
│  ● Ressources à acheter et à récolter                (exemple)│
│  ─────────────────────────────────────────────────────────── │
│  ◉ Pierres d'âme du guide                                    │
│    Inventaire déclaré manuellement                           │
│                                                               │
│  J'en possède                 Total nécessaire                │
│  [         50         ]       [         150         ]         │
│                                                               │
│  Stock disponible                               50 / 150       │
│  ━━━━━━━━━━━━━━━━━━━───────────────────────────────────────  │
│  ⚠ 100 pierres manquantes                                   │
│  Texte discret expliquant que le stock est déclaré           │
└───────────────────────────────────────────────────────────────┘
```

**Tests de fidélité :** capture d'état fermé et d'état ouvert confrontées à la capture de référence de l'utilisateur ; vérifier titre/sous-titre, filtres en ligne, statut circulaire par exigence, séparateur, deux champs, barre et manque. Tests filtrage (Tout/Métiers/Potions/Objets), besoins non fictifs, quantité exacte, persistance `50/150 -> manque 100`, 0 besoin, 0 stock, surplus, progression réseau, absence de bloc `À préparer` par fiche. FAIL si remplacé par l'ancien mini-menu `PRÉREQUIS` ou par une simple liste générique.

### 3. Commandes Personnages / Sommaire — SANS `Mon parcours`
- **SUPPRIMER complètement le titre `Mon parcours` et son commentaire/sous-titre `Fiche N / total` placé dessous. Le numéro de fiche est déjà visible dans l'en-tête/contrôle de pagination de la fiche : ne jamais le dupliquer.
- Garder à droite sur une **petite ligne compacte sans titre** : un bouton icône `Personnages` puis le bouton `Sommaire` avec chevron, aux positions et tailles de la maquette, juste avant la fiche.
- Au clic Personnages, ouvrir l'ANCIEN MENU compact masqué par défaut, avec en-tête littéral **`Mes personnages`**, jamais `Personnages du guide`.
- Une ligne de petites **vraies images de classes** circulaires (36–42 px), anneau de progression et indication de sélection distincte ; pas de noms fixes ni de grosses cartes. Survol de chaque portrait => **vrai pseudo**, classe et % progression dans un tooltip près du curseur, sans sélection automatique. Cliquer portrait => inclure/exclure sa participation au guide et aux macros ; état persisté par ID stable et guide, y compris offline.
- **SUPPRIMER intégralement** le texte d'aide `Appuie sur un portrait pour inclure/exclure...` (ou tout équivalent), le panneau `Déclarer une progression antérieure`, ses champs `Chapitre fini avec` / `Guide fini avec`, et tout compteur manuel historique. **On exploite le réseau pour progression et validation automatiques** ; garder seulement le bouton `Valider` existant en secours manuel au cas où, sans falsifier les preuves réseau.
- **Sommaire** : bouton ouvre/ferme explicitement le panneau (par clic sur Sommaire/chevron), avec recherche, chapitres et fiches dépliables ; **un clic sur un chapitre ou une fiche NE LE FERME JAMAIS automatiquement**. Un clic fiche affiche la nouvelle fiche à droite/en dessous selon la mise en page existante et laisse le panneau visible. Fermeture uniquement par clic explicite sur Sommaire. Navigation manuelle via Précédent/Suivant, Aller à la fiche ou Retour à l'actuelle ne doit pas non plus fermer automatiquement le sommaire. La virtualisation garantit une seule fiche réelle montée à la fois.
- Première fiche = `Légende`, sans ajouter les sources en plein écran.

### 4. Corps de fiche — visuel Lanyel conservé
- UNE fiche visible, titre court fourni par #226, identité/pagination stable, coordonnées cliquables dans le texte **exactement comme avant** ; toutes les actions réellement nécessaires dans l'ordre de parcours : PNJ/dialogues, récoltes/drops, combats, donjons, captures, validations.
- Nom exact des monstres et quantités : ligne à cocher `×5 Tournesol sauvage` ; ne pas montrer `Faire les combats` sans cibles réelles. Les combats de quête sont cochables, y compris via intégration à l'onglet Quêtes ; gestion des preuves et validation manuelle conservées.
- Termes adaptés : `Récolter` pour les objets de métier, `Acheter` seulement si réellement achetable, `Obtenir`/`Récupérer` pour les drops et objets non échangeables. Les actions ne sont pas noyées dans de longs paragraphes.
- Les vrais liens/noms de quêtes **dans le contexte d'une action** restent cliquables avec infobulle du nom complet si nécessaire. **Ne jamais ajouter un bloc/liste `Quêtes liées`**.
- **Interdiction des sections suivantes dans la fiche** : `À préparer`, `Quêtes liées`, `Sources`, `Succès liés`, `Pourquoi cet ordre ?`, zone de contrôle Travel/Zaap ou boîte de confirmation de déplacement. L'ordre du guide doit faire le travail en amont. Garder les métadonnées et vérifications en arrière-plan.
- Boutons inférieurs UNIQUES : `Précédent`, `Valider`, `Suivant`, conserver comportement et position validés. La validation réseau fiable et le mode manuel doivent rester disponibles sans faux positifs.
- Conserver le style de la fiche Guide Lanyel existante : marges, polices, survols, contraste, alternances, cartes, tooltips, dimensions et règles de clic ; **pas d'écran réinventé**.

### 5. Clic sur [x,y] — AUTOMATIQUE, INVISIBLE VISUELLEMENT
- Le même texte `[x,y]`, les mêmes couleur, graisse, zone de clic et tooltip existants.
- Clic gauche = déclenche pour les seuls personnages participants et fenêtres Unity reconnues, le plan `/travel x,y` OU `/zaap zx,zy ; /travel x,y` choisi par le planificateur #226 et exécuté par Organizer #227.
- Ne PAS afficher `Zaap conseillé`, nouvelle carte trajet, bouton supplémentaire, icône nouvelle, chaîne de commande ni une notification de prévisualisation permanente.
- Identité de session vérifiée avant toute commande, arrêt d'urgence et refus sûr en absence de certitude ; les sources / règles de choix restent dans les données et diagnostics internes.

## Contrat graphique STRICT — vrais portraits, images et icônes des boutons

**Les boutons doivent avoir leurs vraies icônes, selon la maquette approuvée ; aucun bouton représenté par un caractère de remplacement, un carré, un emoji arbitraire, un glyphe police absent ou une image cassée.** Ne pas substituer une nouvelle charte graphique. Les boutons à texte conservent leur texte et leur style déjà validés. Les boutons icône-seule restent discrets et de mêmes dimensions que les contrôles voisins.

### Identités et portraits cliquables (obligatoire)
- L'ancien MENU DÉROULANT des personnages reste à sa place : petit bouton icône juste avant `Sommaire` sur la ligne compacte SANS titre `Mon parcours`. Il ouvre le **même panneau compact précédent**, fermé par défaut et repliable au clic ; ne pas utiliser un sélecteur de liste, un modal, des cartes par personnage ou des checkboxes à côté du pseudo.
- Chaque **portrait de classe est lui-même le bouton** (QToolButton/QWidget accessible et réellement cliquable), pas juste une image décorative. Clic gauche : inclure/exclure ce personnage du GUIDE courant. Sélection = appartenance aux quêtes/captures/déplacements du guide, **sans modifier sa progression**. À l'ouverture, recharger les choix persistés, même si Organizer a changé l'ordre des fenêtres.
- Pour les classes reconnues, image réelle issue de `data/images/classes/<class_key>.png` (ex. `pandawa.png`, `huppermage.png`, `ecaflip.png`, `enutrof.png`, `feca.png`, `forgelance.png` ; même principe pour les 19 fichiers). Réutiliser l'éventuel helper canonique `app/pages/organizer/common.py` pour résolution et variantes, mais **ne pas prendre la même icône pour tous les personnages**.
- Les images disponibles dans le dépôt sont **stockées via Git LFS** (un objet `*.png` de ~130 octets lu sans filtre est typiquement un pointeur LFS, pas une image). Le chargement, le packaging PyInstaller et les tests Windows doivent garantir les vrais octets d'image décodables ; ne pas considérer l'existence d'un fichier comme la preuve que QPixmap peut l'afficher. En cas d'image invalide, rapport Doctor UI FAIL avec classe/chemin, pas de validation de captures de « carrés » ou de lettres fictives.
- Diamètre visuel du portrait : environ **36 à 42 px**, avec une **fine couronne circulaire de progression** distincte du statut sélectionné. Images centrées, non déformées, fond identique aux contrôles précédents ; l'anneau ne doit pas cacher le portrait. Un **discret check/contour** matérialise la sélection, différence également perceptible sans couleur seule ; non-sélectionné atténué mais reconnaissable.
- Au survol du portrait : une infobulle compacte affichée près du pointeur avec le VRAI pseudo, classe, progression fiable, origine de preuve et état réseau/offline ; **pas de texte permanent sous les portraits**. Deux personnages de même classe conservent chacun leur bouton, leur pseudo et leur propre état.
- Ligne de portraits compacte, avec espacement homogène ; adaptation responsive quand >5 personnages : défilement horizontal du panneau si nécessaire, sans couper/cacher le dernier portrait ni agrandir la hauteur du guide. Aucune case numérotée. Permettre navigation clavier/focus et activation Enter/Space.
- Les personnages offline restent visibles et sélectionnables, mais ne sont jamais ciblés par une macro ; si aucun personnage sélectionné : aucune macro, jamais repli sur « tous les clients ».
- **Aucune saisie de progression antérieure** ni compteurs de chapitres/guides déjà finis. Le réseau est prioritaire pour la progression ; le seul secours manuel reste le bouton `Valider` de la fiche.

### Inventaire des contrôles et icônes à reproduire
| Emplacement | Visuel demandé | Interaction | Consignes graphiques |
| --- | --- | --- | --- |
| En-tête à droite | **Petit engrenage paramètres** | Ouvrir réglages | Même pictogramme et dimensions que la maquette ; utiliser icône valide, pas « ⚙ » en texte si fonte incertaine |
| Ligne navigation | Bouton **Aller à la fiche** + bouton **Retour à l'actuelle** juste à côté | Accès direct + retour à la fiche active après exploration | Garder la disposition compacte et l'icône de retour cohérente |
| À sa droite | **Bouton Overlay : icône carte uniquement** | Afficher/masquer l'overlay | Petit carré, pas de libellé ajouté, état actif/inactif |
| Préparation générale du guide | **Icône clipboard/liste + titre, sous-titre « Métiers, potions et objets · Parcours complet », chevron** | Dérouler/fermer la carte « Préparation complète » avec les filtres Tout/Métiers/Potions/Objets, vraies exigences et Pierres d'âme | Respecter la capture du 18/10, pas le menu catalogue « PRÉREQUIS » |
| Ligne avant fiche (sans titre) | **Icône personnages (groupe)**, icône seule | Afficher/masquer le menu **Mes personnages** | Juste avant Sommaire, même taille que bouton Overlay |
| Ligne avant fiche (sans titre) | **Icône sommaire/liste** + texte `Sommaire` + chevron | Ouvrir/fermer manuellement, **ne pas fermer sur sélection fiche** | Même ligne, pas de bouton de remplacement |
| Liste chapitres | Coche/cercle de progression + chevrons | Dérouler / aller à une fiche | Icônes discrètes et cohérentes avec les couleurs du thème |
| Fiche | Positions **[x,y] en gras** et apparence déjà existante | Clic unique macro auto Travel/Zaap selon #226/#227 | **AUCUNE** nouvelle icône, badge, image, marqueur Zaap ni bouton copier à côté |
| Fiche | **Cases de validation de combats** | Cocher ×N monstre précis | Vraies checkbox du style Lanyel ; pas de faux caractères □ / ■ |
| Navigation bas | `Précédent` flèche gauche, `Valider` état validé, `Suivant` flèche droite | Changer de fiche / validation | Garder les 3 boutons, ordre, proportions, labels, feedback existants |
| Overlay | Images/icônes **déjà fournies par Atlas** | Afficher les éléments existants | Aucune refonte des assets ou du placement en #225 |

- Utiliser les pictogrammes **cohérents avec les composants Qt/Atlas déjà en place**, icônes SVG/PNG réellement décodées ou icônes dessinées vectoriellement de façon fiable si l'équivalent Atlas existe déjà. Pas de dépendance à des caractères Unicode pour rendre un bouton fonctionnel, pas de « texte de secours » visible à la place d'images connues.
- Si une icône de la maquette est absente du dépôt, reprendre d'abord l'équivalent visuel dans les composants existants, documenter la provenance/licence d'un éventuel nouvel asset et faire valider son rendu ; **ne pas inventer un dessin ou remplacer par un emoji**. Garder le thème sombre/clair, survol, focus, état désactivé et écran HDPI cohérents.
- Bouton Retour à l'actuelle : icône et libellé, placé IMMÉDIATEMENT à côté de Aller à la fiche ; toute sélection Sommaire reste ouverte.
- Boutons icône-seule : `setAccessibleName`, vrai tooltip, état de bascule lisible ; éviter les signaux déclenchés au survol. Les zones cliquables restent suffisantes sans agrandir visuellement les icônes.

### Validation visuelle et packaging graphique
- Screenshots Doctor UI **avant/après** pour : (1) état initial menus fermés ; (2) Préparation générale du guide ouverte ; (3) personnes ouvertes, avec vrais portraits de 5 classes différentes ; (4) un portrait déselectionné et deux de même classe avec progression distincte ; (5) sommaire ouvert ; (6) fiche Lanyel et Succès ; (7) zoom/HDPI, écran minimal.
- Checks Qt d'existence d'image réelle : `QPixmap.isNull() == False`, taille lisible, décodage de tous les assets utilisés, absence de pointeur Git LFS dans la version Windows distribuée ; contrôles interactifs associés aux bonnes fonctions ; pas d'icône invisible ni de texte tronqué.
- Comparer **la forme, l'espacement, la position et le contenu** de chaque bouton et portrait à la maquette approuvée, pas simplement la présence d'un widget portant le bon objectName.
- Faire échouer la certification UI si des portraits/boutons sont des carrés ou du texte de remplacement, si le panneau Personnages a été changé en liste, ou si la sélection ne survit pas au redémarrage.

## Contrat de SURVOL et de navigation liée aux quêtes — obligatoire sur chaque ligne utile

**Règle de présentation : le texte de la fiche reste COURT. L'identité de la quête est portée par la ligne et apparaît au SURVOL, pas dans une section supplémentaire.**

### Personnages
- Le survol d'un petit portrait de classe dans le MENU DÉROULANT des personnages affiche **le vrai NOM/ PSEUDO du personnage** (élément obligatoire et vérifié), puis classe, progression pertinente, état de connexion et preuve réseau/manuelle/inconnue dans une **mini-infobulle au niveau de la souris**.
- Si plusieurs personnages ont la même classe ou la même icône, afficher leur nom propre et le bon taux ; aucun tooltip générique `Pandawa` au lieu du pseudo. Pas de pseudo écrit sous les icônes en permanence.
- Clic sur le portrait = inclure/exclure ce personnage du guide et des macros ; SURVOL = information seulement, pas de sélection, de macro ni de validation.

### Lignes de quête : infobulle sur la LIGNE ENTIÈRE
- Chaque ligne d'action ou d'objectif lié à une ou plusieurs quêtes doit afficher **au survol de sa zone utile** le(s) **nom(s) complet(s) et EXACT(s) des quêtes réellement associées à CETTE ligne**. Cela concerne, sans exception oubliée : PNJ/dialogues, déplacements avec objectifs de quête, combats (y compris les checkboxes `×N monstre`), collecte/récolte, drops, donjons, captures, validation/rendre quête.
- Prendre les **IDs des quêtes et des objectifs en données** ; résoudre leur vrai nom depuis le provider de quêtes. Ne pas déduire l'association en copiant toute la liste des quêtes d'une fiche sur toutes les lignes. **Pas de fausse association** : si aucun quest_id probant, pas de nom inventé ; si plusieurs quêtes, les lister une seule fois chacune, dans un ordre stable.
- L'infobulle est un petit commentaire contextuel **près du pointeur**, pas un encadré qui prend de la place dans la fiche. Format minimal : `Quête : <nom complet>` ou `Quêtes : <nom 1> ; <nom 2>`. Si pertinent et prouvé, ajouter l'objectif associé, sans longues phrases. Une étape de trajet non liée à une quête n'affiche pas arbitrairement une quête.
- Tooltip requis lorsque la souris se trouve SUR LE TEXTE mais également sur la zone cliquable associée et sur les cases de combats ; veiller au propagations Qt `QFrame`/`QLabel`/`QCheckBox`. Le survol ne doit ni recouvrir ni désactiver le clic sur `[x,y]`.
- Tooltip sur le petit bouton de navigation : **nom complet de la quête + `Ouvrir dans Quêtes`** ; le même objectif/quête doit être affiché pour la ligne et pour son bouton.

### Petit bouton « aller à la quête » SUR SA LIGNE — existant, à réparer/completer
- Le bouton est **déjà partiellement présent** dans `GuideUltimeManualCard._add_inline_quest_links` de `app/modules/encyclopedia/views/guide_ultime_manual_view.py` : `QToolButton` 24×24, icône Qt `SP_FileIcon`, objet `GuideManualQuestInlineButton`, tooltip du nom. Il est ajouté par `SharedGuideManualCard._add_line_section` dans `app/modules/encyclopedia/views/shared_manual_guide_view.py`. **RÉUTILISER CE CONTRÔLE** et le style validé plutôt que créer un gros bouton, une colonne dédiée ou une liste `Quêtes liées`.
- **Règle utilisateur définitive : UN SEUL petit bouton par quête et par fiche**, même si cette quête est associée à plusieurs lignes. Le mécanisme existant `_shown_quest_ids` est intentionnel et doit être **CONSERVÉ**. Le bouton apparaît sur la première ligne pertinente, jamais une deuxième fois pour le même `quest_id` dans cette fiche. Le compteur de déduplication est réinitialisé au changement de fiche ; la même quête peut avoir son unique bouton dans une autre fiche. L'absence de second bouton ne retire jamais les infobulles des lignes suivantes.
- Au clic, ouvrir **directement l'onglet Quêtes avec la bonne fiche quête, identifiée par quest_id**, pour le personnage sélectionné ; ne pas seulement afficher le titre, copier le nom, aller au sommaire ou rouvrir la fiche Guide. Réutiliser `questRequested = Signal(int, str, int)`, `SharedGuideManualView._open_quest_from_card` et `EncyclopediaPage.navigate_to_entity("quest", id, source="guide_gps", ...)` (à revalider au HEAD final), sans duplicer de système de navigation.
- Si une action sert **plusieurs** quêtes, le survol liste les vrais noms ; afficher au maximum **un bouton par `quest_id` sur toute la fiche** (chacune de ces quêtes peut posséder son accès unique sur la première ligne correspondante). Pas de lien arbitraire vers la mauvaise quête, pas de menu ni de répétition sur toutes les lignes.
- Si la ligne n'est liée à aucune quête vérifiée, **aucun faux bouton « aller à la quête »**. Les liens de progression du guide, et le bouton `Guide` unique déjà existant, doivent garder leur comportement.
- Cliquer la coordonnée `[x,y]` reste exclusivement le geste de déplacement (macro Organizer Travel ou Zaap+Travel suivant le plan) ; **cliquer le petit bouton de la ligne** est exclusivement le geste de navigation dans l'onglet Quêtes. Cliquer le checkbox combat coche l'objectif ; aucune de ces actions ne doit déclencher les autres par propagation accidentelle.

### Tests de survol et navigation à ajouter dans Doctor UI / Qt
1. Ouvrir Personnages : survol de chaque portrait => pseudo exact, classe exacte, progression individuelle ; classes identiques avec pseudos différents, offline, état inconnu. Fermer/rouvrir le menu et l'app => sélections sauvegardées.
2. Survol d'une ligne PNJ => nom quête exact ; survol combats/checkbox => nom complet de la quête + monstre/quantité ; survol récolte/drop/capture => bon quest_id ; ligne multi-quêtes => tous les noms ; ligne non liée => aucun faux nom.
3. Même quête sur **deux lignes successives** : le bouton n'apparaît qu'UNE fois sur la première ligne pertinente de cette fiche, mais **les DEUX lignes** affichent le bon nom de quête au survol ; les boutons des autres quêtes respectent la même règle de déduplication.
4. Clic bouton => onglet Quêtes, vraie quête ouverte sur le bon personnage, sans modifier l'état des fiches ; clic coordonnée => macro sans navigation Quêtes ; clic case combat => objectif uniquement ; survol => zéro déclenchement.
5. Captures Doctor UI réelles avec infobulles visibles près du curseur : **portrait**, **texte d'action**, **case combat**, **bouton quête**, et captures état sans survol pour prouver aucune pollution visuelle.
6. Le contrat doit être appliqué aux DEUX présentations Guide Succès / Lanyel depuis le rendu partagé et ne pas écraser les réparations de la PR #201.

## Scénarios supplémentaires de validation obligatoires
- Ouvrir Guide Succès, puis Dofus Sylvestre depuis le catalogue : le titre principal affiche EXACTEMENT le nouveau nom (pas `Guide optimisé`), aucun sous-titre de progression ; les barres sont conservées et liées au bon guide.
- Ouvrir Sommaire puis choisir Fiche 643 : le Sommaire reste ouvert. Choisir ensuite Fiche 641 et utiliser `Retour à l'actuelle` : retour à la vraie fiche active sans fermeture du Sommaire et sans validation parasite.
- En mode normal, les commandes icône Personnages et Sommaire sont présentes à droite mais SANS `Mon parcours` ni `Fiche 643/x` répété sous ce titre ; la pagination reste dans son emplacement existant.
- Menu Personnages ouvert : titre `Mes personnages`, vrais portraits avec pseudo au survol ; vérifier ABSENCE de message d'aide et de `Déclarer une progression antérieure`, pas de champs historique. Réseau prioritaire ; bouton Valider secours manuel conservé.

## Contrôle de fidélité obligatoire
1. Rendre une capture COMPLÈTE en **état par défaut** : en-tête fixe, préparation refermée, personnages refermés, sommaire refermé, une fiche seule. Comparer visuellement à la **dernière maquette approuvée dans le fil de discussion**, pas à un mockup plus ancien.
2. Rendre des captures distinctes **Préparation générale du guide ouverte**, **Personnages ouvert**, **Sommaire ouvert**, **Fiche Lanyel**, **Fiche Succès**, **état scrollé**. Comparer disposition, ordre, marges, largeurs, typographies, positions, boutons, couleurs, aucune zone superflue.
3. Tests d'absence explicite des sections interdites, tests screenshot Doctor Atlas produisant de VRAIS pixels lisibles (pas des carrés), détection des contrôles et de leurs chevauchements ; petit écran et minimum 900 px.
4. Tests Qt interaction : aucune macro déclenchée par hover, une seule macro par clic gauche, position identique, sélection de 0/1/5 participants, mêmes classes, offline/online, migration des IDs, progression réseau et secours manuel, persistance du stock 50/150 après redémarrage.
5. Tests de non-régression des progressions Quêtes/Succès, Guide Lanyel/Guide Succès, de l'intégration du rendu partagé #201 et de la libération Qt au retour Home. Rebaser après #201, puis validation Doctor/Graphify et CI au HEAD final.

**CRITÈRE DE SORTIE : si l'UI n'est pas reconnaissable comme la maquette validée, la PR est FAIL même si les tests unitaires passent.**
