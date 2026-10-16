# PR 1 — Réparations Guide Succès + Lanyel Sylvestre

**Statut : cadrage à implémenter — aucun correctif de code n'est encore intégré.**  
**Base :** `main` @ `b8d63e03711c65e5db85c72a5ab64378f5264713` (constat du 16 octobre 2026).  
**Périmètre strict :** anomalies et régressions des guides existants ; **aucune nouvelle fonctionnalité ou refonte visuelle**.

## Constats à reproduire avant de modifier

Captures fournies le 16/10/2026 (ne pas supposer que leur binaire correspond au HEAD courant) :
- **Guide Succès, page 1/267 :** panneau `À FAIRE MAINTENANT` affiché deux fois sur l'une des captures, dont un exemplaire étroit sous la carte principale ; une autre capture de la même page n'affiche pas ce doublon. Anomalie possiblement intermittente.
- **Lanyel Sylvestre, page 8/1672 :** des lignes sur Ganymède / le livre du temple restent visibles hors de la carte active `Fécaline la Sage`. Déterminer si c'est un reliquat d'une ancienne page, un double montage de widgets ou une donnée composée incorrectement.
- **Guide Succès, page 3/267 :** consignes de ressources potentiellement répétées entre `À PRÉPARER` et `À FAIRE MAINTENANT` ; distinguer **redite injustifiée** d'une action réellement nécessaire à deux moments différents.
- Certaines formulations sont anormales (ex. `la quête la quête en cours`) : remonter à la source de composition ; ne pas corriger à l'aveugle dans le widget.
- Cases de suivi parfois ambiguës et multiples sur une ligne ; contrôler le rattachement objectif/preuve/validation, y compris combats requis.
- `Déverrouillé` accompagné visuellement d'un cadenas fermé : vérifier la cohérence du statut et de l'icône, sans changer la politique de verrouillage.

**Important :** un défaut apparent sur capture ne constitue pas à lui seul une preuve de cause. Vérifier les données et le code en production au SHA exact.

## Code et contrats existants à préserver

- Rendu partagé canonique : `app/modules/encyclopedia/views/shared_manual_guide_view.py` (`SharedGuideManualView`, `SharedGuideManualCard`).
- Routeur : `app/modules/encyclopedia/views/manual_route_guides_view.py`.
- Services : `GuideUltimeManualRuntimeService` et `GuideCatalogManualRuntimeService` ; méthode `manual_sections_for_card`.
- Contrat : **Lanyel et Guide Succès gardent le même moteur de rendu, pas de classe UI spécifique Lanyel**.
- Préserver la légende page 1, les six sections existantes, les liens PNJ/coordonnées/quêtes, cases, combats, progression persistante, validation auto/manuelle, navigation, verrouillage et données existantes.
- Examiner la logique `_without_prepare_duplicates` déjà présente : ne pas dupliquer un dédoublonnage qui existe ; distinguer doublons de texte, d'actions et de widgets.

## Ordre d'exécution pour Codex

1. Confirmer le HEAD réel (`git rev-parse HEAD`, `git status --short`) et comparer aux preuves capturées ; démarrer par les règles `AGENTS.md`, `AI_CONTEXT.md`, `DEVELOPMENT_GUARDRAILS.md` et les outils Doctor/Graphify requis par le dépôt.
2. Reproduire pages 1/267, 3/267 et 8/1672, avec aller/retour de pages, changement Lanyel ↔ Succès, ouverture/fermeture, restauration des états, redimensionnement et scroll ; journaliser le nombre de widgets actifs et les sections/rows reçues.
3. Isoler **où naît chaque duplication** : catalogue/route, `manual_sections_for_card`, normalisation, montage `SharedGuideManualCard`, remplacement ou libération des widgets de `_render_window`, rafraîchissement différé/Qt. Vérifier aussi les connecteurs de signal/slot, cache, lazy rendering. Ne pas supposer qu'un CSS `display:none` ou qu'un `clear` opportuniste résout le problème.
4. Corriger **à la source**, avec le changement minimal. Rendre le montage idempotent et ne jamais afficher de section issue de la page précédente. Préserver les vraies répétitions utiles (une ressource à préparer puis une étape à exécuter).
5. Corriger les phrases réellement mal générées et les états de validation/icônes **uniquement si le défaut est confirmé**.
6. Réaliser des régressions automatisées ciblées et un contrôle visuel de l'application Windows si l'environnement le permet. Si non, expliciter ce qui reste non testé.

## Critères d'acceptation (tous à satisfaire avant fusion)

- [ ] Même page reconstruite/réaffichée **une seule fois** : une seule feuille active et pas de panneaux fantômes, y compris en revenant de Lanyel vers Succès.
- [ ] Aucun texte de page N-1 dans N, notamment exemple Ganymède → Fécaline de Lanyel.
- [ ] Chaque section attendue existe une fois, les lignes sont rattachées à la bonne page et les doublons inutiles sont supprimés sans effacer les instructions voulues.
- [ ] Case(s) de validation et combats toujours reliés au bon objectif ; progression inchangée lors des allers-retours.
- [ ] Fonctionnement inchangé pour liens cliquables, coordonnées, `À préparer`, validation automatique/manuelle, boutons Précédent/Valider/Suivant et statuts de verrouillage.
- [ ] Tests ciblés verts : `tests/test_lanyel_shared_manual_ui.py`, `tests/test_shared_guide_single_renderer_contract.py`, `tests/test_shared_guide_visual_flow_contract.py`, `tests/test_guide_manual_long_layout.py`, plus nouveaux tests de non-duplication/idempotence, navigation et libération des widgets.
- [ ] Doctor/Graphify et CI ciblées liées au SHA candidat ; aucune certification déclarée sur la base d'une ancienne preuve.
- [ ] Pas de nouvelle interface, restructuration de JSON, changement de route ou refactorisation non justifiée.

## Contexte / limites

PR de cadrage préparée à la demande du propriétaire, **pas une réparation déjà effectuée**. Les preuves sont les cinq captures partagées dans la conversation du 16 octobre ; ne pas inventer d'URL GitHub pour ces images. Le développement reste à réaliser sur cette branche et la PR doit rester en brouillon jusque-là.

## Complément de périmètre — inspection UI et preuves de non-régression (16/10)

Cette section complète les corrections précédentes ; elle ne transforme pas cette PR en projet d'outillage Doctor général. L'outillage réutilisable est spécifié dans une **PR Doctor UI séparée**, et le correctif doit rester livrable avec les tests Qt ciblés existants si cet outillage n'est pas encore fusionné.

### Points manquants à vérifier

1. **Faire la différence entre nombre déclaré et réalité Qt.** `rendered_card_count == 1` est fixé par le code, il ne prouve pas qu'il n'existe pas d'autres `GuideManualSheet` encore visibles, détachées ou en attente de `deleteLater()`. Compter les vrais `QWidget` visibles, parents, références et entrées de layout ; examiner les créations/destructions et traiter les événements différés. Les erreurs peuvent être un résidu du rendu précédent **ou** une seconde feuille incluse par l'arborescence/layout : tester les deux.
2. **Distinguer 3 niveaux de redondance** : (a) même QWidget/section rendu deux fois, (b) même ligne matérialisée deux fois dans la même section, (c) consigne sémantiquement similaire présente dans `prepare`, `now` ou `keep` mais justifiée par deux moments différents. Ne dédupliquer que les véritables doublons en préservant quantités, ressources, ordre et validation.
3. **Pages et versions des données** : retrouver l'étape par identité canonique (guide/stage/route) et conserver l'index/capture à titre de repère ; ne pas appliquer une correction spécifique aux index 1, 3 ou 8 si le catalogue évolue. Vérifier le `card`/sections/clé de progression de la version exécutée et de l'EXE réellement capturé.
4. **Résilience du cycle de vie** : répétitions `_render_window`, `_follow_active_after_progress_change`, changement de personnage/guide, signal Qt tardif, retour Home puis réouverture, navigation rapide avant libération différée, scroll et redimensionnement ; absence de fuite de widgets et de progression corrompue.
5. **États et associations sémantiques** : chaque bouton/case correspond à une action unique, état visuel et état réel concordent ; liens PNJ/quête/objet et commande `/travel` restent fonctionnels ; combats requis associés aux bonnes quêtes ; absence de validation automatique abusive ou de perte de l'état manuel.
6. **Présentations et géométries** : pas de panneau rémanent sous le conteneur principal, de section en demi-largeur imprévue, de débordement horizontal, de chevauchement entre actions et cases, de boutons masqués sur les pages longues. Comparer au moins deux tailles de fenêtre et vérifier l'accessibilité de navigation et de validation après scroll. Ne pas réaliser de refonte visuelle dans cette PR.
7. **Phrases fautives** : isoler le texte fourni par les données du texte composé par le moteur ; corriger les fautes systématiques à la source sans réécrire les étapes de jeu.

### Vérifications automatisées et preuves obligatoires

- Ajouter un scénario de tests PySide6 sur le **vrai moteur partagé** (pas un QWidget factice) avec services/fixtures isolés, sans toucher au profil ni à la progression utilisateur.
- Tester explicitement Guide Succès première carte, carte avec nombreuses ressources, et Lanyel transition vers Fécaline : séquences `render → page suivante → précédente → autre guide → retour → refresh × N`.
- Mesurer pour chaque point : identifiant de carte attendue, nombre de feuilles, sections, widgets visibles, parent et géométrie, chaînes visibles, état/cible des checkboxes et boutons ; tester aussi après `processEvents()` et `DeferredDelete`.
- Ajouter assertions de non-contamination entre pages, idempotence du rendu et stabilité de la progression persistée après changement/rechargement ; s'assurer que les tests **échouent avant** correction sur un cas qui reproduit réellement la défaillance. Si la reproduction n'est pas obtenue, le signaler et garder un test préventif explicite.
- Produire un paquet de preuves **avant/après** : captures PNG réelles et structure Qt JSON quand un environnement Qt permet de le faire, résolution et version PySide6/Qt indiquées, SHA exact, capture des pages courtes et longues. Le mode offscreen est un contrôle Qt réel **mais ne remplace pas un contrôle desktop Windows du binaire installé** ; qualifier distinctement chaque niveau de preuve.
- Ne pas confondre un rendu PNG avec un scénario utilisateur vérifié : confirmer les changements de pages, clics, callbacks, états et persistance par assertions comportementales.
- Exécuter au minimum les tests de la checklist principale ainsi que `tests/test_guide_ultime_manual_ui_navigation.py` et les contrôles `tests/test_atlas_doctor_capture_ui.py` si le scénario Doctor est utilisé. Aucun FULL ou benchmark lourd systématique hors exigence du routage CI et de la politique de certification.
- Documenter les constats `CONFIRMED`, `NOT_REPRODUCED` ou `BLOCKED`, avec lien à la preuve ; ne jamais interpréter une trace statique Graphify comme une capture visuelle.

### Hors périmètre explicite

Pas de nouvelle navigation par chapitre, de refonte de légende, de redesign, ni de nouveau moteur de vues dans cette PR. La PR #202 demeure **sans spécification**. Ne pas rendre les réparations dépendantes d'un futur outil Doctor si les tests Qt ciblés suffisent à confirmer le correctif.


## Anomalie supplémentaire signalée — boutons de quête vers l'onglet Quêtes

**Régression fonctionnelle signalée par l'utilisateur :** les boutons/liens de quête issus des fiches Guides ne dirigent pas correctement vers l'onglet Quêtes. Ce défaut fait partie des **réparations** #201 ; ne pas attendre la livraison de #203 pour le corriger.

### Vérifications obligatoires avant correction

1. Reproduire par **clic réel**, dans l'Encyclopédie assemblée (Guide Succès + Lanyel), avec une quête ID connue, et obtenir un état observable de l'onglet Quêtes et du détail. Ne pas se contenter d'un `navigate_entity` remplacé par un mock.
2. Chaîne à suivre dans le code existant : `GuideManualQuestInlineButton` → `questRequested` → `SharedGuideManualView._open_quest_from_card` → `LinkService.navigate_to_entity` → `EncyclopediaPage.navigate_to_entity` → `QUESTS_TAB` → `quest_page.select_quest`.
3. Le test `tests/test_guide_ultime_manual_quest_links.py` existant ne valide que l'appel au callback simulé ; ajouter **une intégration Qt bout en bout** avec la vraie page Encyclopédie, y compris chemin cold/lazy, et vérifier **onglet actif, ID sélectionné et détail visible**.
4. Isoler la première étape qui échoue, puis corriger minimalement sans changer le contrat des autres navigations (Guides, Succès, Quêtes) ni forcer un chargement lourd systématique.
5. Vérifier à nouveau les liens pour les deux guides, successivement, après retour dans Guide, et sous deux états de chargement. Un clic qui émet correctement un signal mais n'ouvre pas la quête doit être `FAIL`, non `PASS`.

Critère de sortie : [ ] le lien de chaque guide testé ouvre réellement la **bonne** quête dans le **bon** onglet, sans bouton inerte ni simple callback simulé. Préserver la navigation des autres types d'entités.

**Distinction :** le bug rapporté est à reproduire ; la lecture du code prouve déjà une **lacune de couverture du test actuel**, mais ne prouve pas encore la cause du dysfonctionnement dans le binaire de l'utilisateur.


## Revue UI supplémentaire — 16 octobre 2026

**Retours utilisateur sur l'application installée : à reproduire et corriger dans #201. Ces points sont des réparations, pas des nouveautés #202.** La preuve Doctor UI \`validator-smoke\` ne les certifie pas.

### Critique P0 — Succès : clic sans affichage de la fiche

**Symptôme rapporté :** lorsqu'on clique sur un succès dans l'onglet Succès, son détail ne s'affiche plus du tout. Reproduire sur le vrai widget et la version exacte. Tracer \`AchievementsView.list_widget.itemClicked\` → \`on_achievement_clicked\` → \`show_achievement\` → \`get_detail_by_id\` → \`AchievementDetailStack\`/\`detail_scroll\`/\`AchievementDetailWidget\`. Le code branche un callback mais cela ne prouve pas un panneau visible : contrôler création, visibilité, largeur du splitter, focus, données, erreurs Qt, état sélectionné et chargement différé. Tester un succès normal, un succès lié à des quêtes et un succès d'alignement, premier chargement puis retours; clic réel + capture + texte/objectif du détail, pas de simple mock.

### P1 — combats à faire

Afficher un titre explicite **« Faire les combats : »**, puis **une case cochable et une ligne par objectif réel**, sous la forme \`☐ ×5 Tournesol sauvage\`, \`☐ ×5 [nom du monstre]\`. Quantité/nom exacts selon l'objectif de quête, aucune cible inventée, pas de bloc vague. Réutiliser les \`GuideManualCombatCheck\` déjà implémentés et leur progression partagée \`(quest_id, objective_id)\`, sans créer un doublon de case ni perdre la validation. Vérifier chaque case, objectif et enregistrement après navigation/rechargement pour Guide Succès et Lanyel.

### P1 — ressources, métiers, préparation et trajet

- Pour une ressource acquise par récolte de métier (paysan, alchimiste, etc.), formuler **« Récolter [quantité] [nom] »** et non « monter le stock ». Vérifier réellement la méthode d'obtention : ne pas dire récolter pour drop/achat/craft.
- Une ressource prévue à la collecte **pendant le trajet optimisé et avant son utilisation** ne doit **pas** apparaître en double dans **« À préparer »**. La laisser uniquement dans l'étape correcte de collecte ; préserver la quantité et vérifier sa disponibilité à l'heure requise. Si la quantité disponible sur le trajet est insuffisante, pré-remplir « À préparer » uniquement avec le manque indispensable. Garder les vrais blocages avant départ dans ce bloc.
- Corriger les formulations à la source dans les données ou le composeur, sans masquer les actions réellement nécessaires.

### P1 — quêtes, infobulles et lignes cohérentes

- Au survol de chaque quête/raccourci de quête dans une page de guide, afficher une **mini-infobulle immédiatement près du curseur** avec le **nom exact de la quête**. Préserver le clic et l'icône réelle et lisible déjà demandés ; vérifier tooltip/captures/hit-tests en différentes tailles/scroll.
- Quand un PNJ permet au même dialogue de démarrer une quête, afficher **une seule ligne** du type « Parler à Fécaline la Sage et accepter la quête “Espoir et tragédie” » plutôt que deux consignes fragmentées. Le retour utilisateur écrit « Décaline » : **vérifier le PNJ canonique et la relation exacte avec la quête** dans la source avant de fusionner les actions, ne rien inventer.
- Reproduire et corriger les phrases incompréhensibles, par exemple **« prendre la galette secrète avant le passage aux champs afin que les œufs chimériques puissent tomber »**. Vérifier l'identité des objets, le mécanisme de drop, le timing, et les données/texte source ; réécrire en français clair « action → lieu/condition → résultat » sans inventer les conditions du jeu.
- **Lanyel est la référence architecturale souhaitée** pour la présentation et l'enchaînement des informations ; garder **un moteur partagé** pour Guide Succès et Lanyel, sans dupliquer les composants.

### P1 — guides Dofus : ne pas répéter les prérequis

Tous les prérequis des guides Dofus doivent être affichés **uniquement dans la section « Prérequis »**, pas parmi les étapes à faire comme s'il fallait recommencer des quêtes/succès. Privilégier **le nom du Succès prérequis** aux longues listes de toutes ses quêtes lorsque le Succès couvre effectivement la condition ; offrir accès à son détail plutôt que saturer le guide. Préserver les conditions restantes non incluses dans ce succès et l'état de progression réel ; ne pas supprimer les quêtes qui sont **de véritables actions propres à l'étape courante**. Tester prérequis terminés et non terminés, guides Dofus différents, retour à l'écran et preuve UI.

### Conserver les demandes précédentes

Accueil Guides desktop **en deux colonnes** : **gauche** Guide Succès → Guides optimisés → Alignements empilés et alignés ; **droite** grille Dofus. Raccourci vers l'onglet Quêtes : icône véritable, **un seul par quête et par page à la première occurrence utile**, clic de bout en bout jusque dans le détail réel, même après initialisation lazy. Corriger également les doublons de blocs, pages fantômes, textes répétés, état du cadenas, combats, débordement Lanyel et persistance de progression.

**Hors périmètre immédiat :** réduction et regroupement du **nombre de pages** des deux guides. Le propriétaire demande expressément de reporter l'optimisation du parcours et du nombre de pages à une phase suivante, après fiabilisation de cette UI. Ne pas utiliser cette réparation pour restructurer la route.

**Critères de sortie :** diagnostiquer chaque retour CONFIRMED / NOT_REPRODUCED / BLOCKED, test reproduisant l'échec avant correction quand possible, assertion comportementale réelle après, captures Qt/arbre d'éléments/hit-tests deux tailles avec Doctor UI, preuves rattachées au SHA exact ; pas de PASS sur les tests hors périmètre. L'onglet Succès nécessite un vrai scénario Doctor UI dédié, pas seulement le smoke Guide existant. #201 reste DRAFT et non fusionnée tant que ce travail n'est pas validé. #202 demeure intacte.


## Clarification propriétaire — converger les guides Dofus vers le style Lanyel existant

**Demande confirmée :** la cible visuelle n'est **PAS** la maquette générique à colonnes/cartes proposée dans la discussion : **réutiliser l'aspect et les composants du vrai guide Lanyel déjà présent dans l'application**. Les guides Dofus, Guide Succès et Lanyel doivent avoir une expérience cohérente. Ne pas entreprendre une refonte artistique ni inventer de nouveaux widgets lorsque les widgets canoniques existent.

### État architectural vérifié au 16/10

- \`SharedGuideManualView\` + \`SharedGuideManualCard\` dans \`app/modules/encyclopedia/views/shared_manual_guide_view.py\` affichent **déjà Guide Succès et Lanyel** : barre de progression en haut, bouton unique « Guide », pourcentage, cadenas et numéro de page, feuille centrale défilante, navigation Précédent / Valider / Suivant sous la feuille.
- Sections canoniques déjà utilisées : \`À PRÉPARER\`, \`À FAIRE MAINTENANT\`, \`À PROFITER ICI\`, \`À CONSERVER POUR PLUS TARD\`, \`BOSS / CAPTURES\`, \`AVANT DE PARTIR\` ; légende sur la première page, coordonnées et liens en ligne, checkboxes liées aux objectifs. Ne pas afficher de section vide, doublée ou d'une ancienne page.
- **Les guides Dofus ordinaires ne suivent pas cette même vue aujourd'hui :** \`GuidesView._show_guide_overview_standard\` assemble un détail avec \`FixedColumnSplitter\`, \`center_panel\`, \`right_panel\` et des panneaux récapitulatifs. La convergence vers Lanyel doit concerner **l'interface effectivement affichée** des guides Dofus, pas une simple modification stylistique hors du chemin utilisé.

### Comportement cible des guides Dofus

1. **Même squelette visuel que Lanyel** : en-tête Guide/progression/verrou/page ; **une fiche active au centre** dans le même style typographique, espacements, bordures, rubriques, icônes et navigation ; commandes Précédent, Valider, Suivant familières. Conserver l'identité et le titre du Dofus sans modifier la navigation existante silencieusement.
2. Les **Prérequis** constituent un **bloc dédié et distinct**, rattaché à la présentation du guide (accessible en début de guide ou via une zone dédiée selon le contrat existant), non réinjecté comme tâches à accomplir au milieu du déroulé. Synthétiser en **Succès requis** quand pertinent, ne pas lister toutes les quêtes constitutives du Succès, ne pas supprimer les vrais prérequis non couverts.
3. Les étapes courantes adoptent les **mêmes rubriques et éléments interactifs que Lanyel** uniquement quand sémantiquement applicables : \`À préparer\`, \`À faire maintenant\`, \`À profiter ici\`, \`À conserver\`, \`Boss/captures\`, \`Avant de partir\` ; actions claires, coordonnées, tooltip des quêtes, objectifs de combat quantifiés, progression. Les exigences métier propres aux guides Dofus restent vraies, sans inventer de trajets ou nouveaux objectifs.
4. **Réutiliser le moteur/rendu Qt partagé ou ses composants visuels canoniques**, par adaptation légère des données Dofus si nécessaire. Éviter un rendu parallèle dupliqué et préserver les services, le graphe des dépendances, la persistance et le comportement lazy. Si une migration complète dans #201 présente un risque de régression, documenter le découpage minimal nécessaire sans masquer la demande.
5. Le **Guide Succès n'a pas besoin d'un nouveau layout** puisqu'il partage déjà celui de Lanyel. Réparer plutôt son contenu et ses bugs : textes, doublons, interactions, combat/ressources et progression.
6. Tests Qt et Doctor UI comparatifs **Lanyel / Succès / Dofus** sur le vrai chemin de rendu (captures, arborescences, états, hit-tests à deux résolutions, navigation, lazy, retour accueil). Contrôle visuel : un utilisateur doit reconnaître immédiatement le style de Lanyel, **pas un tableau de bord Dofus distinct**.
7. **Ne pas réduire le nombre de pages** ni réorganiser les circuits de quête lors de cette passe : cette optimisation reste explicitement reportée.

**Validation interdite sur capture artificielle ou seule égalité de noms de widgets.** Joindre avant/après, scénario couvert, constat exact-SHA, limites de validation Windows EXE s'il y en a.
