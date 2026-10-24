# [PLAN 04/07] Guide Succès Opti : en-tête EXACT de la maquette

> **DRAFT PLAN SEUL — aucune fonctionnalité implémentée. Ne jamais fusionner avant développement + CI finale.**

**Objectif :** Refaire EXCLUSIVEMENT l'en-tête du Guide Succès selon le dernier screenshot validé dans la conversation. La capture sert UNIQUEMENT pour l'en-tête, jamais pour le contenu en dessous.

**Révision auditée :** 5849fb05828d56b5b5a15fe762e762a71f6b913c

## Pourquoi et état actuel
- [ ] shared_manual_guide_view.py compose aujourd'hui le titre, les trois barres verticalement empilées, le cercle, la saisie fiche, un bouton inutile Aller à la fiche, Overlay séparé, puis des panneaux placés plus bas.
- [ ] Le bouton Guides placé avant le titre occupe de la place et assure actuellement aussi un retour vers le catalogue/fiche active ; ses actions doivent être vérifiées avant disparition.
- [ ] Overlay existe mais est explicitement désactivé dans le runtime actuel ; le repositionner ne crée pas une fonction artificielle.
- [ ] Les trois barres sont connectées aux services de progression et la barre Route reste cliquable suivant la politique de verrouillage.

## Modifications exigées
- [ ] Reproduire la hiérarchie : un grand anneau rond unique à l'extrême gauche, centré sur environ deux lignes et sans cercle près du titre ; pourcentage central grand, anneau épais, couleurs sobres sur fond sombre.
- [ ] Première ligne à sa droite : icône du guide actif + titre Guide Succès ; sélecteur Fiche X ; bouton Actuelle ; Overlay compact ; Paramètres compact à l'extrême droite.
- [ ] Seconde ligne : TROIS blocs horizontaux équidistants, Route (cible/rouge/barre fine/% à droite), Préparation (cube/vert/barre fine/%), Succès (trophée/jaune/barre fine/%). Ne jamais empiler les trois métriques en colonnes verticales.
- [ ] Troisième ligne : exactement Préparation à gauche, Sommaire au centre et Mes personnages à droite, trois boutons larges de hauteur alignée, conservant leurs véritables panneaux actuels et leur état. Mes personnages expose le nombre et une icône sans libellé encombrant quand la maquette/l'espace l'exige, avec accessibleName/tooltip.
- [ ] Déplacer les contrôles et leurs panneaux existants en préservant les signaux et les composants ; ne pas construire de nouveaux menus déroulants ou panneaux de contenu à la place.
- [ ] Sélecteur Fiche X toujours synchronisé avec la fiche réellement affichée ; changement immédiat dès choix sans clic de confirmation ; éviter boucle de signaux lors de setValue programmatique.
- [ ] Actuelle revient à la première fiche encore nécessaire pour les personnages ; ne pas déplacer l'utilisateur lorsqu'il consulte une ancienne fiche ; préserver Précédent/Suivant et navigation par Sommaire.
- [ ] Retirer Guides, Aller à la fiche, conteneurs vides et doublons. Conserver un chemin de retour au catalogue ailleurs sans rajouter de quatrième ligne dans l'en-tête.
- [ ] Overlay et Paramètres aux positions de la capture, boutons discrets. Conserver Paramètres/verrouillage de barre Route ; ne pas annoncer Overlay opérationnel tant que son runtime reste désactivé.
- [ ] Barres et cercle alimentés UNIQUEMENT par les valeurs réelles des services ; pourcentage exact, inconnu représenté comme inconnu, pas de fictif ni de progression décorative.
- [ ] Redimensionnement Qt : toute largeur utilisée, marges régulières, barres qui grandissent horizontalement, aucune étirement en hauteur, aucune superposition, texte tronqué ou clipping à la taille réelle Windows et aux tailles réduites.
- [ ] Réduire effectivement la hauteur mesurée de l'en-tête et augmenter la hauteur disponible pour les fiches ; garder une légende/navigateur inférieur inchangés.
- [ ] Ne pas modifier contenu de fiche, quêtes, textes, combats, navigations sous l'en-tête, préparation métier ni logique de calcul métier pendant cette PR.

## Connexions et surfaces concernées
- [ ] shared_manual_guide_view.py : _build_compact_header, _build_preparation_panel, _build_sheet_header, _refresh_header ; boutons GuideCompact* et panneaux Guide* ; widgets réutilisés par Guide Succès et Sylvestre.
- [ ] Test de non régression pour les deux Guides utilisant SharedGuideManualView, route_lock_check, sélecteur, donut et lecture de progressions per-character.

## Critères d'acceptation
- [ ] Capture Doctor du VRAI QWidget Atlas à taille réelle + petite et grande largeur ; comparer UNIQUEMENT l'en-tête au screenshot validé ; cercle unique, 3 lignes, 3 barres côte à côte, 3 boutons bas alignés.
- [ ] Navigation fiche immédiate, Actuelle, Sommaire sticky, Paramètres et verrouillage fonctionnent par clic réel ; aucune fonction utile perdue malgré suppression de Guides.
- [ ] Vérifier tailles, bounding boxes, zones cliquables, chevauchements, proportion du cercle et gain réel de hauteur ; 0/1/n personnages.
- [ ] Tests ciblés guide_ultime_manual_ui_navigation, lanyel_shared_manual_ui, doctor_ui_qt et captures UI Windows ; pas de changement de contenu.

## Source de vérité visuelle — point de vigilance
- [ ] Le **screenshot validé dans la conversation n'est pas joint comme image dans cette branche**. La disposition et les contraintes ont été retranscrites dans ce document ; cette transcription ne constitue **pas une preuve de fidélité pixel à pixel**.
- [ ] Avant d'annoncer l'interface « exactement conforme », rapprocher une capture Doctor du vrai QWidget de la **référence originale**, effectivement accessible à l'exécutant ; si la référence n'est pas disponible dans son environnement, le signaler comme **comparaison visuelle non certifiée**, sans inventer un résultat.
- [ ] La capture de comparaison ne doit porter QUE sur l'en-tête. Aucune intervention sur les textes/cartes de la fiche située en dessous.

## Vérification exhaustive de la référence visuelle (screenshot validé)
- [ ] L'anneau général est **avant toute navigation, progression et action**, à gauche du titre et des trois barres ; il prend visuellement la hauteur d'environ deux rangées, sans grossir toute la barre supérieure.
- [ ] **Mes personnages** est le contrôle le plus à droite de la troisième rangée ; `Préparation` est à gauche et `Sommaire` au centre, sans bouton à menu déroulant substitué aux vrais panneaux.
- [ ] Ne pas déplacer le grand anneau à droite du titre ni ajouter une autre progression ronde à la fiche : **un seul cercle général** pour tout l'en-tête.
- [ ] Première rangée compacte : `Guide Succès`, `Fiche X`, `Actuelle`, `Overlay`, `Paramètres` ; boutons Overlay et Paramètres vraiment au bout, pas de grand espace vide ni de bouton caché à une quatrième rangée.
- [ ] Tester les états panneaux ouverts, longueurs de titres, texte zoomé, Windows DPI et largeur actuelle de l'application ; aucune action cliquable perdue ni fuite de taille.
- [ ] Ne pas substituer une image générée, une maquette approximative ou un faux QWidget à la **capture du runtime Qt réel** ; les vérifications visuelles ne s'appliquent qu'à l'en-tête, jamais aux fiches sous celui-ci.

## Géométrie, interactions et référence de capture (préparation)

**Reference fonctionnelle à ne pas inventer :** le screenshot original est dans la conversation utilisateur, **pas** dans le dépôt. Conserver ses proportions et demander une preuve de comparaison au moment du développement, mais ne pas prétendre ici connaître des coordonnées exactes ni produire une fausse capture.

**Architecture réelle :** `SharedGuideManualView._build_compact_header` (`shared_manual_guide_view.py`) contient le titre, le donut, les barres et Fiche/Actuelle ; `_build_preparation_panel` et `_build_sheet_header` tiennent actuellement les vrais panneaux. Déplacer visuellement leurs déclencheurs dans les trois lignes du nouvel en-tête tout en préservant les conteneurs, propriétés de visibilité et signaux Qt — **jamais** remplacer les panneaux par des `QComboBox` ou `QMenu` factices.

**Scénarios de capture/acceptation :**
- [ ] H1 : ouverture Guide Succès à la vraie largeur par défaut => un anneau global à gauche, 3 barres Route/Préparation/Succès sur une même ligne, 3 contrôles Préparation/Sommaire/Mes personnages sur la ligne suivante.
- [ ] H2 : fenêtre agrandie, réduite, titres longs, Windows 100/125/150 % DPI => aucun chevauchement/clipping, bouton Personnages à droite, taille de l'anneau proportionnée, en-tête réellement moins haut qu'avant.
- [ ] H3 : Fiche X change immédiatement la fiche sans bouton Aller ; mise à jour du sélecteur lors de Précédent/Suivant et navigation Sommaire, sans récursion des signaux Qt.
- [ ] H4 : Sommaire/Préparation/Personnages s'ouvrent et **restent ouverts pendant navigation** jusqu'à fermeture volontaire ; vérifier les focus et tabulations.
- [ ] H5 : barres et cercle affichent des données calculées réelles, pas de pourcentage décoratif ; état sans personnage et valeurs indéterminées lisibles.
- [ ] H6 : bouton Guides legacy retiré, mais retour vers catalogue réellement accessible depuis le contexte équivalent ; `Actuelle` ne doit jamais devenir un faux bouton « Accueil ».
- [ ] H7 : Overlay est explicitement désactivé dans le runtime présent ; son nouvel emplacement doit être fidèle, mais **aucune activation mensongère** sans moteur réellement connecté. Démontrer état accessible et explication si indisponible.

**Contrôle UI :** trois captures utiles pour l'ensemble du chantier, dont UNE de la page Guide Succès ; pour PR04 comparer exclusivement l'en-tête, via rectangles mesurés, état des clics réels et valeur avant/après de la hauteur Qt. Tester Guide Succès et Sylvestre sur le composant partagé.

## Protocole de développement et certification
- [ ] PR brouillon de CADRAGE : le premier commit est documentaire uniquement ; pas d'implémentation tant que le lot n'est pas engagé et ne jamais fusionner le plan seul.
- [ ] Une seule PR de développement à la fois, terminer intégralement, rebaser sur le main mis à jour depuis la PR précédente, puis passer à la suivante sans redemander le découpage.
- [ ] Pas de certification CI à chaque commit. Exécuter seulement les tests locaux très ciblés nécessaires pour déboguer, et corriger les tests obsolètes sans supprimer leurs garde-fous.
- [ ] Quand le lot est terminé : preuve des critères, Doctor/scénarios Qt/Windows selon l'impact, contrôles RAM si nécessaire, puis Ready for review pour certification intelligente UNIQUE du SHA final. Pas de FULL inutile.
- [ ] Une correction après échec invalide les anciennes preuves et impose une certification finale du nouveau SHA ; ne jamais revendiquer de test non exécuté.
- [ ] Préserver performances du chargement différé, intégrité, vraie identité des personnages, progression historique et ressources packagées dans l'EXE.
- [ ] Ne pas intégrer la branche accidentelle fix/guide-opti-compact-controls-character-progress-20261024 ni modifier le contenu des fiches en dehors des périmètres explicitement listés.
