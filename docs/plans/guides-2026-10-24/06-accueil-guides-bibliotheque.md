# [PLAN 06/07] Guides : accueil compact et catalogue cohérent

> **DRAFT PLAN SEUL — aucune fonctionnalité implémentée. Ne jamais fusionner avant développement + CI finale.**

**Objectif :** Reconstruire l'accueil actuel en interface légère, lisible et fonctionnelle, sans faux guides jouables ni coût RAM excessif.

**Révision auditée :** 5849fb05828d56b5b5a15fe762e762a71f6b913c

## Pourquoi et état actuel
- [ ] GuideCatalogView et guide_featured_home.py imposent aujourd'hui quatre grandes cartes mises en avant dont deux Alignements.
- [ ] Une recherche permanente, les filtres Tous/En cours/Terminés, le titre DOFUS et des métadonnées techniques occupent de l'espace.
- [ ] Le modèle léger d'accueil est distinct du lecteur complet et la fonction _restore_guides_catalog_home() reconstruit le catalogue au retour.

## Modifications exigées
- [ ] N'afficher en zone prioritaire que DEUX cartes principales compactes et de taille égale : Guide Succès Opti et Sylvestre Opti, avec images, état de progression réel et cartes entièrement cliquables.
- [ ] Retirer les deux grandes cartes Bonta/Brâkmar de cette zone, mais conserver leurs parcours et les proposer dans Explorer les guides avec catégorie Alignements réellement visible et ouvrable.
- [ ] Conserver la navigation latérale : Dofus, Alignements, Dimensions, Éliocalypse, Régions, Événements, Îles, Autres aventures ; harmoniser les familles Atlas et Ganymède sans inventer de guides jouables.
- [ ] Retirer la recherche permanente de l'accueil Guides et les contrôles superfétatoires, sans supprimer par erreur la recherche locale des fiches Quêtes ou Sommaire ; enquêter séparément sur le champ global Encyclopédie dont la suppression a aussi été demandée.
- [ ] Supprimer les filtres Dofus Tous/En cours/Terminés et les libellés techniques 'parcours Ganymède référencés/non jouables', compteurs et métadonnées superflues sans cacher l'état réellement non jouable des sources.
- [ ] Réorganiser la grille Dofus : cases symétriques, redimensionnement correct, pas de titre DOFUS occupant une cellule, pas de libellé 'Dofus' répété dans toutes les cartes.
- [ ] Montrer la progression correcte, l'icône réellement embarquée, les catégories optimisées et les états pas commencé/en cours/terminé sans les inventer.
- [ ] Les sources Ganymède metadata-only ne doivent jamais devenir des entrées actives par une simple correction visuelle ; aucune navigation vers un guide non certifié.
- [ ] Conserver les signaux select_guide/guideRequested et le passage du catalogue léger vers le lecteur riche ; après retour, ne conserver qu'une vue légère et ne pas empiler les anciens widgets.
- [ ] Préserver 95 références comme inventaire interne tout en affichant une interface publique utile ; pagination/virtualisation de la grille et images asynchrones sans accumulation.
- [ ] Tester les tailles de fenêtres réelles, navigation clavier, clic sur toute la carte, absence de débordement et temps d'ouverture.

## Connexions et surfaces concernées
- [ ] guide_catalog_view.py ; guide_featured_home.py ; guide_card.py (GuideHomeColumns/GuideListModel/GuideCardDelegate) ; guide_library_sources.py ; encyclopedia_page.py ; provider GuideProvider.
- [ ] Retour catalogue DeferredAchievementGuidesView, mise en cache des images, modèle de progression, états des catégories et ressources EXE.

## Critères d'acceptation
- [ ] Accueil montre exactement deux cartes prioritaires, Bonta/Brâkmar trouvables et ouvrables dans Explorer ; chaque carte entièrement cliquable.
- [ ] Grille Dofus utilisable à largeur normale et réduite sans duplications, titres superflus ni filtre inutile ; aucun faux Ganymède disponible.
- [ ] Recherche globale Encyclopédie traitée conformément à la demande utilisateur après contrôle des dépendances aux autres onglets.
- [ ] Tests guide_library_home, guide_home_two_columns, guides_home_render_cache, hidden_home_refresh, home_manual_guide_import_deferral, doctor_ui_qt et coût RAM/chargement.

## Compléments explicites — accueil validé et recherche globale
- [ ] Organiser les familles sur la surface d'exploration selon la présentation retenue : **Optimisés + Alignements à gauche ; Dofus à droite**, sous-menus repliables alignés et stables, avec Dimensions / Éliocalypse / Événements / Régions / Îles dans des groupes cohérents. Conserver les sous-menus ouverts pendant la navigation si l'utilisateur ne les ferme pas.
- [ ] Supprimer **effectivement la barre de recherche générale de l'Encyclopédie** demandée par l'utilisateur, après cartographie de sa gestion dans `EncyclopediaPage` : ne pas simplement masquer le champ de l'accueil Guides en oubliant celui de l'onglet. Préserver les fonctions de recherche internes légitimes de Quêtes, Sommaire ou des autres modules si elles sont distinctes.
- [ ] Ne pas sacrifier la zone de navigation principale à des titres/compteurs techniques ou cartes Alignement prioritaires : seules les deux cartes **Guide Succès Opti** et **Sylvestre Opti** y restent.
- [ ] Les cartes Dofus doivent être réellement symétriques et entièrement cliquables ; chaque carte affiche un titre distinctif sans préfixe répétitif `Dofus` quand non nécessaire, état calculé et ressource image vérifiée.
- [ ] Les 95 entrées source non jouables peuvent rester consultables de manière informative, mais jamais sous forme de boutons de lancement trompeurs ; signaler clairement la disponibilité réelle du guide sans texte technique inutile.
- [ ] Vérifier l'accueil dans l'EXE Windows réel après passage accueil → Guide → retour catalogue, en contrôlant la destruction de la vue riche pour éviter l'accumulation de RAM.

## Protocole de développement et certification
- [ ] PR brouillon de CADRAGE : le premier commit est documentaire uniquement ; pas d'implémentation tant que le lot n'est pas engagé et ne jamais fusionner le plan seul.
- [ ] Une seule PR de développement à la fois, terminer intégralement, rebaser sur le main mis à jour depuis la PR précédente, puis passer à la suivante sans redemander le découpage.
- [ ] Pas de certification CI à chaque commit. Exécuter seulement les tests locaux très ciblés nécessaires pour déboguer, et corriger les tests obsolètes sans supprimer leurs garde-fous.
- [ ] Quand le lot est terminé : preuve des critères, Doctor/scénarios Qt/Windows selon l'impact, contrôles RAM si nécessaire, puis Ready for review pour certification intelligente UNIQUE du SHA final. Pas de FULL inutile.
- [ ] Une correction après échec invalide les anciennes preuves et impose une certification finale du nouveau SHA ; ne jamais revendiquer de test non exécuté.
- [ ] Préserver performances du chargement différé, intégrité, vraie identité des personnages, progression historique et ressources packagées dans l'EXE.
- [ ] Ne pas intégrer la branche accidentelle fix/guide-opti-compact-controls-character-progress-20261024 ni modifier le contenu des fiches en dehors des périmètres explicitement listés.
