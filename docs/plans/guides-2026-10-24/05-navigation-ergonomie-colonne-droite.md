# [PLAN 05/07] Guides : navigation, liens Quêtes et colonne droite

> **DRAFT — développement partiel. Ne pas fusionner avant couverture du lot et certification finale du SHA.**

**Objectif :** Regrouper dans une PR ergonomique cohérente les interactions du lecteur et la colonne d'informations rétractable, sans changer le contenu des parcours.

**Révision initiale auditée :** 5849fb05828d56b5b5a15fe762e762a71f6b913c

## Avancement vérifiable au 25 octobre 2026

- [x] Colonne droite classique : bouton de rétraction/réouverture et mémorisation de la largeur en pixels, sans remise systématique à 230 px lors d'une navigation.
- [x] Raccourci Quête par fiche : pictogramme dédié au thème, zone cliquable de 30 px, focus clavier, nom exact, infobulle locale à 350 ms et contexte de navigation conservés.
- [x] Le centre du lecteur classique reçoit seul l'espace supplémentaire ; la largeur mémorisée du panneau droit reste fixe.
- [x] La recherche locale du Sommaire est réappliquée après reconstruction de sa liste, avec test de navigation Sommaire ouvert.
- [x] Le bouton de la colonne droite est masqué dans la fiche Quête et restauré dans le lecteur classique.
- [x] La position de défilement droite est mémorisée par guide lors des navigations et restaurée après reconstruction Qt.
- [x] Déplacements directs : commande /travel validée, exclusion des destinataires hors ligne/inconnus, copie plutôt qu'envoi en l'absence de cible. Aucun /zaap déduit.
- [x] Actions contiguës sur même position chiffrée : regroupement visuel compact sans concaténation du texte, sans suppression de ligne et sans modification métier.
- [x] Ajout d'un test de lien Quête depuis la deuxième fiche, avec guide_index et manual_stage_id exacts.
- [x] Tests de régression ajoutés pour le panneau droit et le bouton Quête (présents dans le code, non exécutés dans cet audit).
- [ ] Validation Windows/DPI, navigation multi-guides, scroll, mémoire, Doctor et certification du SHA final.
- [x] Après échec de certification au SHA 83a726f : restaurer la preuve de connexion dans le mock de déplacement, ajouter une issue fail-closed si le service ne fournit pas d'inventaire des personnages, et comparer le texte HTML de groupe après déséchappement. Deux régressions bloquantes identifiées parmi 1 475 tests de domaine.
- [ ] Vérifier le Sommaire, les commandes de déplacement, les groupes d'actions et les scénarios N1 à N8.
- [ ] Vérifier en UI Windows le délai réel des infobulles Quêtes et les dispositions de panneau droit.
- [ ] Aucun résultat de test Qt n'est revendiqué dans ce document.

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
- [ ] Pas de fuite Qt ni de widget orphelin après navigation ; tests guides_phase3, doctor_ui_qt, guide_ultime_manual_ui_navigation, UI Windows réelle et mémoire ciblée.
- [ ] Respect intégral de l'en-tête déjà validé en PR04.

## Compléments explicites — contenu interactif et commandes
- [ ] Conserver/sécuriser la présentation des combats cochables **« ✔ x5 Nom du monstre »** avec quantité, cible et état corrects ; cliquer ne valide pas une quête non prouvée.
- [ ] Fusionner les actions contiguës qui décrivent réellement la même étape de carte, par exemple « parler à PNJ » puis « prendre objet », **sans modifier leur ordre, signification ou les données métier** ; éviter les phrases coupées ou doublées.
- [ ] Ne pas réintroduire les blocs obsolètes `Succès liés`, `Destination suivante`, les sources techniques ou un deuxième bouton de lien Quête sur la même fiche ; préserver la carte Légende en première fiche.
- [ ] Séparer raccourci Quête **par fiche** et navigation entre fiches : un seul accès pertinent à la Quête, nom exact en tooltip, retour à la fiche/étape source, titres chapitres/actes lisibles et repliables.
- [ ] Vérifier la chaîne de déplacement **coordonnées [x,y] → /travel x,y direct si possible ; trajet nécessitant un zaap → /zaap approprié puis /travel x,y** uniquement lorsque la preuve d'itinéraire le justifie ; Organizer désigne les destinataires réellement sélectionnés. Aucun /zaap inventé.
- [ ] Contrôler l'outil de création d'étapes : libellés courts, distinction combat/donjon/PNJ/objet/position et rendu final correspondant, sans modifier silencieusement les étapes déjà enregistrées.
- [ ] Vérifier que la fermeture/réouverture de la colonne droite conserve largeur, état et scroll y compris après parcours Guide → Quête → Guide ; tester seulement les lecteurs où cette colonne existe.
- [ ] Préparer exactement les **trois captures de contrôle utiles** : accueil Guides, en-tête + fiche Guide Succès Opti, et un guide Ganymède réel quand activé ; ne pas multiplier les captures inutiles.

## Contrats de navigation et état de colonne (préparation)

**État constaté :** `guides_view.py::_configure_detail_layout` fixe `right_panel.setVisible(True)` et réimpose les largeurs 220–230 px à chaque entrée de guide classique ; le splitter `FixedColumnSplitter` ne permet pas le redimensionnement classique par poignée. Il faut une action explicite, pas seulement `right_panel.hide()` dans un handler qui sera annulé au prochain render.

**Scénarios et détenteurs d'état :**
- [ ] N1 : guide classique + colonne visible => activer rétraction : panneau caché et **languette de restauration réellement cliquable**, centre prend la place libérée.
- [ ] N2 : aller Guide → Quête → même Guide ; rechanger onglet / guide / redimensionner => préférence de colonne et scroll conservés selon la portée définie, sans largeur négative ni min-width bloquant.
- [ ] N3 : Ganymède continu masque volontairement droite ; ne pas créer de languette trompeuse sur ce lecteur. Guide Succès/Sylvestre utilisant la vue partagée ne doivent pas recevoir ce QSplitter.
- [ ] N4 : Quête accessible une seule fois **par quête et par fiche**, zone de clic et tooltip exacts ; retour fidèle au `guide_id`, `guide_stage_id`, `guide_index` émis par `_open_quest_from_card`.
- [ ] N5 : sommaire sticky et chapitres/actes repliables conservent leur état ; retour « fiche actuelle » distinct de retour catalogue ; navigation Précédent/Suivant sans perdre la sélection.
- [ ] N6 : chaîne de commandes destination `[x,y]` → `/travel x,y` ou `/zaap` puis `/travel`, **uniquement** sur route connue et destinataires actuellement connectés/vérifiés ; sinon copier la commande ou afficher explicitement indisponible.
- [ ] N7 : combats checkables `✔ xN monstre`, groupements PNJ/objets, carte Légende et texte compact ; la normalisation visuelle ne doit pas fusionner deux objectifs métier distincts.
- [ ] N8 : captures Doctor limitées aux écrans demandés, vrais événements Qt, test de détachement des anciennes cartes QWidget (`hide` + `deleteLater`) et absence d'empilement après plusieurs retours.

**Critère de livraison :** cette PR est UNE PR ergonomique cohérente, pas une PR pour la seule colonne droite ; vérifier la non-régression Guide Succès, Sylvestre, Dofus classique, Alignements et contenu Ganymède accessible.

## Protocole de développement et certification
- [ ] PR brouillon de CADRAGE : le premier commit est documentaire uniquement ; pas d'implémentation tant que le lot n'est pas engagé et ne jamais fusionner le plan seul.
- [ ] Une seule PR de développement à la fois, terminer intégralement, rebaser sur le main mis à jour depuis la PR précédente, puis passer à la suivante sans redemander le découpage.
- [ ] Pas de certification CI à chaque commit. Exécuter seulement les tests locaux très ciblés nécessaires pour déboguer, et corriger les tests obsolètes sans supprimer leurs garde-fous.
- [ ] Quand le lot est terminé : preuve des critères, Doctor/scénarios Qt/Windows selon l'impact, contrôles RAM si nécessaire, puis Ready for review pour certification intelligente UNIQUE du SHA final. Pas de FULL inutile.
- [ ] Une correction après échec invalide les anciennes preuves et impose une certification finale du nouveau SHA ; ne jamais revendiquer de test non exécuté.
- [ ] Préserver performances du chargement différé, intégrité, vraie identité des personnages, progression historique et ressources packagées dans l'EXE.
- [ ] Ne pas intégrer la branche accidentelle fix/guide-opti-compact-controls-character-progress-20261024 ni modifier le contenu des fiches en dehors des périmètres explicitement listés.
