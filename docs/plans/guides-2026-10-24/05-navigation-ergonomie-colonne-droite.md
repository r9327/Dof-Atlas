# [PLAN 05/07] Guides : navigation, liens Quêtes et colonne droite

> **DRAFT PLAN SEUL — aucune fonctionnalité implémentée. Ne jamais fusionner avant développement + CI finale.**

**Objectif :** Regrouper dans une PR ergonomique cohérente les interactions du lecteur et la colonne d'informations rétractable, sans changer le contenu des parcours.

**Révision auditée :** 5849fb05828d56b5b5a15fe762e762a71f6b913c

## Pourquoi et état actuel
- [ ] Les liens inline des quêtes sont des petits boutons icône de fichier, infobulles Qt standard, un seul raccourci par quête et par fiche ; rendu actuellement jugé mauvais.
- [ ] Le Sommaire est sticky et doit le rester ; la navigation interne guide-vers-quête passe par navigate_entity avec contexte guide_id/stage/index.
- [ ] La colonne droite du lecteur classique a une largeur minimale 220 px, est rendue visible à chaque affichage, et FixedColumnSplitter désactive les poignées.

## Modifications exigées
- [ ] Conserver Précédent/Suivant, Actuelle, vue historique, Sommaire et navigation de fiches sans ouverture/fermeture intempestives ni retour automatique sur fiche actuelle.
- [ ] Vérifier les chapitres/actes repliables, la recherche locale du Sommaire, et le retour vers la fiche exacte depuis Quêtes, avec guide_id, guide_stage_id et guide_index ; préserver le contexte et le scroll.
- [ ] Refaire le style des liens Quêtes inline : icône propre au thème, zone de clic accessible, tooltip du vrai nom, une occurrence par quête et par fiche ; ouvrir la bonne fiche Quête.
- [ ] Réduire modérément le délai des infobulles de quête, sans changement global excessif de tous les tooltips Qt et sans perte d'accessibilité clavier.
- [ ] Conserver les liens de coordonnées, /travel x,y, /zaap et les déplacements de personnages réellement sélectionnés ; bloquer actions risquées lorsque l'identité ou la route n'est pas vérifiée.
- [ ] Vérifier les textes/formatages déjà générés (combats cochables, quantités, PNJ, groupes d'actions) sans réécrire les données des guides ; corriger uniquement l'affichage/liaison confirmé défaillant.
- [ ] Colonne GuideRightPanel sur le lecteur CLASSIQUE : ajouter un bouton discret de rétraction et une languette de réouverture, restaurer la largeur enregistrée, préserver le scroll et répartir automatiquement l'espace libéré vers le centre.
- [ ] Maintenir les règles propres à chaque lecteur : Dofus classique, Alignement, Guide Opti, et Ganymède continu qui masque déjà la colonne droite. Ne pas appliquer le splitter à tous par accident.
- [ ] Préserver la disposition du panneau gauche, le mode étapes repliées, l'affichage Quêtes dans QStackedWidget, et la conservation des états au changement de guide/onglet.
- [ ] Vérifier Overlay seulement sur les surfaces où un véritable runtime existe et préserver ses protections ; éviter bouton actif mais sans effet.
- [ ] Garantir que toutes les interactions restent utilisables sur fenêtre réduite, grande fenêtre et DPI Windows.

## Connexions et surfaces concernées
- [ ] app/modules/encyclopedia/views/guides_view.py, guide_ultime_manual_view.py, shared_manual_guide_view.py, guide_ultime_manual_view.py (liens inline), widgets/dashboard.py et contextes de navigation EncyclopediaPage.
- [ ] Signaux questRequested/open_quest_from_guide, QSplitter/QStackedWidget, panneaux GuideLeft/Center/Right, positions de scroll.

## Critères d'acceptation
- [ ] Aller Guide → Quête → retour bonne fiche sans perdre l'étape consultée ; Sommaire ouvert reste ouvert, infobulle plus réactive, icônes cohérentes.
- [ ] Rétracter colonne droite plusieurs fois, changement Guide/Quête, redimensionnement, sauvegarde/restauration largeur et scroll ; centre gagne l'espace.
- [ ] Pas de fuite Qt ni de widget orphelin après navigation ; tests guid es_phase3, doctor_ui_qt, guide_ultime_manual_ui_navigation, UI Windows réelle et mémoire ciblée.
- [ ] Respect intégral de l'en-tête déjà validé en PR04.

## Protocole de développement et certification
- [ ] PR brouillon de CADRAGE : le premier commit est documentaire uniquement ; pas d'implémentation tant que le lot n'est pas engagé et ne jamais fusionner le plan seul.
- [ ] Une seule PR de développement à la fois, terminer intégralement, rebaser sur le main mis à jour depuis la PR précédente, puis passer à la suivante sans redemander le découpage.
- [ ] Pas de certification CI à chaque commit. Exécuter seulement les tests locaux très ciblés nécessaires pour déboguer, et corriger les tests obsolètes sans supprimer leurs garde-fous.
- [ ] Quand le lot est terminé : preuve des critères, Doctor/scénarios Qt/Windows selon l'impact, contrôles RAM si nécessaire, puis Ready for review pour certification intelligente UNIQUE du SHA final. Pas de FULL inutile.
- [ ] Une correction après échec invalide les anciennes preuves et impose une certification finale du nouveau SHA ; ne jamais revendiquer de test non exécuté.
- [ ] Préserver performances du chargement différé, intégrité, vraie identité des personnages, progression historique et ressources packagées dans l'EXE.
- [ ] Ne pas intégrer la branche accidentelle fix/guide-opti-compact-controls-character-progress-20261024 ni modifier le contenu des fiches en dehors des périmètres explicitement listés.
