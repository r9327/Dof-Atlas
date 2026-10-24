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

## Protocole de développement et certification
- [ ] PR brouillon de CADRAGE : le premier commit est documentaire uniquement ; pas d'implémentation tant que le lot n'est pas engagé et ne jamais fusionner le plan seul.
- [ ] Une seule PR de développement à la fois, terminer intégralement, rebaser sur le main mis à jour depuis la PR précédente, puis passer à la suivante sans redemander le découpage.
- [ ] Pas de certification CI à chaque commit. Exécuter seulement les tests locaux très ciblés nécessaires pour déboguer, et corriger les tests obsolètes sans supprimer leurs garde-fous.
- [ ] Quand le lot est terminé : preuve des critères, Doctor/scénarios Qt/Windows selon l'impact, contrôles RAM si nécessaire, puis Ready for review pour certification intelligente UNIQUE du SHA final. Pas de FULL inutile.
- [ ] Une correction après échec invalide les anciennes preuves et impose une certification finale du nouveau SHA ; ne jamais revendiquer de test non exécuté.
- [ ] Préserver performances du chargement différé, intégrité, vraie identité des personnages, progression historique et ressources packagées dans l'EXE.
- [ ] Ne pas intégrer la branche accidentelle fix/guide-opti-compact-controls-character-progress-20261024 ni modifier le contenu des fiches en dehors des périmètres explicitement listés.
