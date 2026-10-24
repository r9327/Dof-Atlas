# [PLAN 07/07] Ganymède : parcours continus, intégration et activation contrôlée

> **DRAFT PLAN SEUL — aucune fonctionnalité implémentée. Ne jamais fusionner avant développement + CI finale.**

**Objectif :** Remplacer les itinéraires Atlas Dofus admissibles par les étapes continues Ganymède sans coexistence de deux routes, pertes de sauvegardes ou faux compléments automatiques.

**Révision auditée :** 5849fb05828d56b5b5a15fe762e762a71f6b913c

## Pourquoi et état actuel
- [ ] Le catalogue Atlas contient 22 Dofus et 2 Alignements ; le manifeste contient 20 remplacements Dofus TRUSTED_SOURCE_STEPS activables seulement si le catalogue marque explicitement l'UI prête.
- [ ] Les entrées Ganymède du catalogue source sont metadata_only (95 références), aucune ne doit devenir jouable automatiquement.
- [ ] GuideProvider.select_verified_replacement_path impose un manifeste, un payload SHA-256, un ordre de pas signé, une preuve de complétude et un mode manuel sûr.
- [ ] Le lecteur ContinuousGuideRoutePanel existe déjà et diffère de SharedGuideManualView ; la sauvegarde multi-personnages est fournie par ContinuousGuideNavigation.

## Modifications exigées
- [ ] Cartographier et documenter les 20 remplacements Dofus par guide_id, source_guide_id, nombre de pas, champs requis, manifest, fingerprint et hash ; relever les Dofus sans correspondance et ne rien fabriquer pour Dofoozbz/Dokille.
- [ ] Préserver exactement l'ordre Ganymède des étapes ; désactiver l'ancienne route lorsque la nouvelle est sélectionnée, ne jamais afficher les deux parcours parallèlement.
- [ ] Adapter le lecteur continu aux composants et interactions Guides communs : fiche courante, consultation d'une autre fiche, Actuelle, Précédent/Suivant, Sommaire, Préparation, personnages, progression et boutons.
- [ ] Ne pas remplacer le Guide Succès optimisé par le parcours Ganymède brut : garder exclusivement les optimisations du Guide Succès dans son propre moteur ; Ganymède est source de parcours continus classiques.
- [ ] Préserver l'identité des étapes (source guide + rang) et le guide_id Atlas ; sauvegarde par character:<id>, validation manuelle et aucune complétion de quête/succès à partir de texte de source.
- [ ] Différencier une action candidate de source, une étape manuelle jouable et une action canonique réellement vérifiée ; aucune quantité, possession, déplacement ou objectif certifié inventé.
- [ ] Traiter les préparations Ganymède à partir des structures disponibles et des preuves de source, en indiquant clairement les inconnues ; garder le même cadre d'identité et de validation qu'en PR01/02/03.
- [ ] Tester planificateur de déplacements seulement avec projections vérifiées, sinon montrer la marche manuelle ; aucun /travel ou /zaap dangereux.
- [ ] Activer progressivement uniquement les guides complets dont les tests de parity source, manifeste, ordonnancement et UI sont verts ; modifier ganymede_manual_ui_ready guide par guide/groupe certifié.
- [ ] Pour Alignements Bonta/Brâkmar et les autres catégories : auditer les catégories et prérequis séparément, ne pas activer tant que la couverture et le rendu ne sont pas prouvés ; le catalogue les affiche selon leur statut réel.
- [ ] Préserver progression historique sous les anciens guides sans migration mensongère ; distinguer marques manuelles de nouvelles étapes, anciennes validations et quêtes réellement terminées.
- [ ] Prévoir rollback au guide ancien en cas de manifeste invalide sans effacer les nouvelles ou anciennes sauvegardes ; vérifier remplacement en EXE et données de distribution.
- [ ] Assurer lisibilité du texte, labels PNJ/monstre/donjon, positions, combats et durées sans importer du texte source incomplet ou de la prose non autorisée ; contrôle des 95 métadonnées séparé du statut jouable.
- [ ] Ne pas charger les 7705 étapes possibles au démarrage ; ne charger que le guide sélectionné et garder CPU/RAM dans les budgets existants.

## Connexions et surfaces concernées
- [ ] guide_ganymede_cutover.py ; guide_provider.py ; manual_route_guides_view.py ; guides_view.py ; guide_continuous_route_panel.py ; guide_continuous_navigation.py ; guide_continuous_preparation.py ; guide_library_sources.py.
- [ ] data/encyclopedia/guides/catalog.json ; replacement_drafts/cutovers/cutover_manifest.json et guide payloads, snapshots et source crosswalks ; états de progression et export runtime Windows.

## Critères d'acceptation
- [ ] Sur un guide certifié : nombre exact de pas et ordre source, aucune étape manquante, une seule route visible, navigation rapide et fiche actuelle cohérente après relancement.
- [ ] Sur un guide non certifié : aucun bouton jouable trompeur, retour de repli et ancienne progression intacte.
- [ ] Deux personnages valident des pas différents sans corruption ni auto-complétion de quêtes ; Ganymède source ne se confond pas avec Guide Succès Opti.
- [ ] Tests ganymede_* ciblés (manifest/fingerprint/actions/parity/prepa), guide_continuous_navigation, guide_continuous_route_panel, Doctor UI Windows, performance et packaging ; preuve par guide/groupe avant activation.
- [ ] La PR entière est considérée finie uniquement après identification claire des guides activés et de ceux restant bloqués ; ne jamais proclamer 95/95 jouables par le simple index.

## Compléments explicites — contrat de remplacement Ganymède
- [ ] Assurer un **suivi continu intégral** de la première à la dernière étape pour les parcours effectivement activés, pas une simple liste d'objectifs ou de quêtes associées.
- [ ] Les deux catégories **Dofus et Alignements** doivent préserver leurs règles spécifiques ; Bonta/Brâkmar ne doivent pas devenir actifs sur le seul drapeau de disponibilité d'un Dofus, et les guides non couverts restent clairement identifiés.
- [ ] Les étapes Ganymède conservent leur ordre source **sans optimisation automatique** ; les modifications d'itinéraires et de regroupements sont réservées au moteur du Guide Succès Opti, pas au remplacement source.
- [ ] Tester chaque guide activé avec au moins une séquence d'étapes contenant déplacements, PNJ, combats, préparation, passage de fiche et sauvegarde de deux personnages ; les actions inconnues sont clairement distinguées des actions vérifiées.
- [ ] Les catégories Dimensions / Éliocalypse / Événements / Régions / Îles restent affichées à l'accueil avec leur vrai statut, sans confondre inventaire source et contenu entièrement certifié.
- [ ] Preuves livrées en fin de PR : **liste nominative et nombre exact de guides actifs/bloqués**, parité des étapes, captures réelles d'un guide Ganymède, diff des données exportées vers Atlas App et vérification de l'absence de régression des anciennes sauvegardes.

## Contrat d'activation et UI continue (préparation)

**Blocage architectural confirmé :** `ContinuousGuideNavigation.__init__` refuse toute route où `category != "dofus"`, ou dont l'ordre source, le nombre d'étapes et les propriétés manuelles ne sont pas exacts. Il n'est donc pas possible d'activer Bonta/Brâkmar en renommant seulement une catégorie. `ContinuousGuideRoutePanel` utilise actuellement un `QToolButton` avec `QMenu.InstantPopup` pour les personnages ; à **ne pas recopier** si l'interface cible impose des panneaux réels stables.

**Livrables par groupe de guides :** table `guide_id Atlas ↔ source_guide_id Ganymède ↔ SHA du payload ↔ count attendu/observé ↔ statut manifeste ↔ statut UI ↔ ancien progrès conservé ↔ nouvelles étapes complétées ↔ statut de certification`. Séparer « 95 guides indexés » de « 20 Dofus source-trusted déclarés au cutover » et « guides effectivement activés ». Dofoozbz/Dokille restent sans correspondance si les données ne changent pas.

**Gates et scénarios :**
- [ ] G1 : guide certifié Dofus => lire chaque étape dans l'ordre source, texte/source/provenance conservés, une seule route, état individuel par ID stable ; pas d'auto-vrai à partir de prose.
- [ ] G2 : ancien guide non remplacé => route Atlas et anciennes marques inchangées ; cutover désactivé si manifeste/empreinte invalide, sans effacer les nouveaux enregistrements.
- [ ] G3 : 2 personnages cochent des étapes différentes, le lecteur se ferme/rouvre et Actualiste les points de reprise ; aucun report automatique sur succès/quête.
- [ ] G4 : sans sélection => `ContinuousGuideNavigation.position().status == NO_SELECTED_CHARACTER` et aucun clic Valider de groupe ; guide consultable.
- [ ] G5 : source action inconnue ou quantité non vérifiée => texte de source visible, validation manuelle permise seulement sur l'étape identifiée ; aucune commande de déplacement auto déduite.
- [ ] G6 : Alignements Bonta/Brâkmar => moteur et schéma adaptés séparément, contrôles d'ordre/branches conservés ; statut BLOQUÉ si couverture de source ou identités d'étape insuffisantes.
- [ ] G7 : UI alignée sur composants Guides (Sommaire stable, préparation détaillée, vrais panneaux Mes personnages, boutons de fiche, retour), **pas de QMenu/QComboBox** substitués ; aucune matérialisation de 7705 widgets au démarrage.
- [ ] G8 : prévisualisation/activation de lot ne modifie aucun chemin source, même si le guide reçoit des quêtes connues ; liste des guides activés et non certifiables publiée avec motif exact.

**Contrôles ciblés vérifiables :** `test_ganymede_cutover.py`, `test_ganymede_trusted_cutovers.py`, `test_ganymede_replacement_readiness.py`, `test_guide_continuous_navigation.py`, `test_guide_continuous_route_panel.py`, `test_guide_continuous_preparation.py`, `test_guide_ganymede_travel_review.py`. Ajouter un scénario Doctor Ganymède ciblé si les scénarios CI existants ne couvrent que guides-success et guides-lanyel.

## Protocole de développement et certification
- [ ] PR brouillon de CADRAGE : le premier commit est documentaire uniquement ; pas d'implémentation tant que le lot n'est pas engagé et ne jamais fusionner le plan seul.
- [ ] Une seule PR de développement à la fois, terminer intégralement, rebaser sur le main mis à jour depuis la PR précédente, puis passer à la suivante sans redemander le découpage.
- [ ] Pas de certification CI à chaque commit. Exécuter seulement les tests locaux très ciblés nécessaires pour déboguer, et corriger les tests obsolètes sans supprimer leurs garde-fous.
- [ ] Quand le lot est terminé : preuve des critères, Doctor/scénarios Qt/Windows selon l'impact, contrôles RAM si nécessaire, puis Ready for review pour certification intelligente UNIQUE du SHA final. Pas de FULL inutile.
- [ ] Une correction après échec invalide les anciennes preuves et impose une certification finale du nouveau SHA ; ne jamais revendiquer de test non exécuté.
- [ ] Préserver performances du chargement différé, intégrité, vraie identité des personnages, progression historique et ressources packagées dans l'EXE.
- [ ] Ne pas intégrer la branche accidentelle fix/guide-opti-compact-controls-character-progress-20261024 ni modifier le contenu des fiches en dehors des périmètres explicitement listés.
