# ATLAS — Harmonisation UI et finitions transversales

> **Statut : PLAN / DRAFT — aucune implémentation de cette checklist ne peut être déduite de ce document.**
>
> Contrat source non modifiable silencieusement : [issue #364](https://github.com/r9327/Dof-Atlas/issues/364) (**43 exigences restantes dont 3 recettes réelles ; 25 critères transférés à #325**). Les ID restants `ATUI-*`, `ATHM-*`, `ATCH-*`, `ATLN-*`, `ATGD-*`, `ATQT-*`, `ATSC-*`, `ATNW-*`, `ATBS-*`, `ATAL-*`, `ATQA-001/003/004` doivent figurer dans le rapport de livraison final. `ATOR-*`, `ATMC-*`, `ATZP-*` et `ATQA-002` sont transférés à #321/#325.

## Objectif

Mettre fin aux divergences d'interface et aux bugs d'utilisation sans refonte gratuite ni deuxième architecture UI. Les contraintes précises sont celles du contrat #364, pas des exemples ci-dessous.

## Contrat transversal de classes et couleurs globales — UI Unity unique

**Exigences ajoutées par demande explicite : ATUI-009 à ATUI-016, contrat source #364.**
L'architecture existante est la source de vérité : `app/ui/unity_skin.py` (palette Unity), `app/ui/theme.py` (THEME_TOKENS, typographie, espaces, tailles, QSS), `app/ui/components.py` (composants partagés, ex. AtlasButton et AtlasPageTitle).

- **Globaliser ce qui est commun :** les couleurs et états sémantiques, menus déroulants sur le comportement du menu Succès, boutons, onglets, commutateurs, barres d'Ariane, titres, panneaux, dialogues, popups, tooltips, barres de progression, notifications, scrollbars, tailles, bordures, espacements, images et icônes.
- **Une seule définition, N consommateurs** : modifier un composant commun ou un token doit propager son apparence sur tous les écrans sans patch répétitif par module. Un module garde ses interactions/données propres ; pas de style divergeant sans raison vérifiable.
- **Même langage partout :** Accueil, Personnage, Encyclopédie/Quêtes/Succès/Guides/Bestiaire, Outils, Stuffs, Almanax, Réseau, Launcher et overlays/menus contextuels. Les composants visuels globaux restent également applicables à Organizer/Macro/Miroir/Zaap, dont les modifications métier sont dans #325. Les fenêtres indépendantes reçoivent les mêmes tokens et composants ou un adaptateur minimal si la technologie l'impose.
- **Etats vérifiés** : normal, survol, sélection, actif, désactivé, chargement, focus, erreur, succès ; cohérence du resize, titres, barres d'Ariane et alignements. Images Unity et logos transparents sans fond noir.
- **Anti-régression** : établir une matrice écrans × composants, vérifier les consommateurs avec Graphify du SHA exact avant refactor, tests des contrats UI partagés, screenshots Doctor UI sous Windows. Ne pas lancer de refonte générale spéculative, réutiliser ce qui fonctionne.

## Dépendances / responsabilités

| Branche / PR | Responsabilité | Règle pour cette PR |
| --- | --- | --- |
| [#363](https://github.com/r9327/Dof-Atlas/pull/363) | Architecture d'en-tête universelle, extracteur, certification guide pilote Cawotte | **Ne pas modifier son moteur, ses données ni certifier les guides ici.** Attendre le pilote 100 % certifié avant d'intégrer l'en-tête et d'évaluer la couverture des guides. Préserver les deux guides optimisés. |
| [#325](https://github.com/r9327/Dof-Atlas/pull/325) | Toutes les fonctionnalités Organizer/Macro/Miroir/Zaap et la recette Windows multi-fenêtres | Aucun changement de moteur, hook, raccourci ou UI spécifique ici ; les composants visuels globaux restent applicables. |
| [#285](https://github.com/r9327/Dof-Atlas/pull/285) | Launcher V2 | Ne pas réimplémenter l'installation différentielle ; ne corriger l'affichage/logo/finalisation que sur base compatible. |
| [#306](https://github.com/r9327/Dof-Atlas/pull/306) | Catalogue/lecteur Guides | Eviter la duplication et vérifier compatibilité avec #363 avant de fusionner. |
| [#358](https://github.com/r9327/Dof-Atlas/pull/358) | Atlas Doctor et outils | Réutiliser les outils approuvés et enregistrer leurs preuves exact-SHA. |

## Migration Organizer/Macro/Zaap vers #325 — décision du 03/11/2026

Le correctif Switch clic Unity ATMC-003 et les 24 autres critères Organizer/Macro/Zaap/recette multi-fenêtres sont dans #321/#325. **Transfert des fichiers effectué** : au moment de la migration, le diff de #365 ne conservait que les fichiers UI globaux. Des lots UI supplémentaires ont depuis modifié l'Accueil, la navigation, le catalogue Guide et leurs tests ; ce constat historique ne décrit plus la liste exhaustive des fichiers de la PR. Le clic physique source DOWN/UP, les hooks molette/clavier, les corrections du clic synthétique et leurs tests sont portés dans #325. **La validation reste à faire** : Graphify exact-SHA, Doctor/tests ciblés, audit d'intégration et recette DOFUS Unity 2/4/6/8. Aucun PASS ni certification n'est déduit du transfert.

## Ordre de lots de développement conseillé

1. **UI commune et navigation** — source du thème `app/ui/theme.py`, composants `app/ui/components.py` ; normaliser menus sur Succès, onglets, barre d'Ariane, resize, fond étoilé ; corriger Bestiaire ↔ Encyclopédie / Outils et annulation d'un chargement de quête.
2. **Accueil / Personnage** — cartes progression avec logos Unity réellement transparents, raccordement Almanax, module Personnage et persistance `character:<id_dofus>`.
3. **Quêtes / Succès / Bestiaire** — colonnes et masquage, affichage plus rapide à la demande, instructions et positions vérifiées, masquer modules incorrects du Bestiaire.
4. **Guide** — corrections de panneaux, menu de catégories, images, scroll, fil d'Ariane et visibilité ; appliquer le rendu universel **uniquement après prérequis #363 satisfaits**, sans extraction ou certification opportuniste de guides.
5. **Réseau / voyages / Almanax** — compléter les flux selon sources de vérité, raccordement travel/zaap, fonctionnement hors ligne, privilèges, calendrier jours futurs, objets et bonus.
6. **Launcher** — corriger thème, transparence, popup 100 % et séquencement lancement après installation validée, en conservant le moteur V2.
7. **Recette et intégration** — audit commit par commit, audit global, tests ciblés, performances mesurées sur baseline identique, Windows/DOFUS réels et certification du SHA exact.

> Ces lots sont des domaines de commits, pas de nouvelles PR. Faire plusieurs commits ciblés par lot si nécessaire et ne pas estimer arbitrairement le nombre de commits. Aucun lot n'est coché par ce fichier.

## Préflight et contrôles obligatoires

- Lire `AI_ENTRYPOINT.md`, `AGENTS.md`, `AI_CONTEXT.md`, `ZERO_TRUST_RULES.md`, `DEVELOPMENT_GUARDRAILS.md`, `PERFORMANCE_GUARDRAILS.md`, les instructions locales et `docs/delivery/DELIVERY_GUARD.md`.
- Vérifier `git rev-parse HEAD`, branche, base, liste des PR ouvertes et chemins effectivement concernés.
- Avant code, `py -3.13 -m tools.ai_context status`, `tools.agent_task_profiles`, `tools.work_spec` pour ce chantier transverse, puis `py -3.13 -X utf8 -m tools.atlas_doctor agent plan <paths> --base-ref origin/main --json`.
- Avant toute restructuration/suppression, `--structural` et **Graphify du SHA exact** avec consommation prouvée. Ne pas supprimer un composant uniquement parce qu'une recherche texte ne le trouve pas.
- Après chaque lot, Doctor `agent check <paths> --base-ref origin/main --run-tests --json` puis `agent validate`, tests ciblés, revue du diff et des effets secondaires. Captures Doctor UI pour changements visuels ; mesures p50/p95/p99 et RAM si parcours de chargement concernés.
- Les contrôles Windows / vraie application DOFUS, la superposition sur les fenêtres, les touches, le réseau et le Launcher ne sont pas prouvables par des tests unitaires Linux ; garder leur statut **NOT_TESTED** en attendant une recette humaine enregistrée.
- **Draft jusqu'à fin de tous les critères**. Aucune FULL ou Phase Certification pendant le développement de cette PR ; ne pas lancer la CI des guides de #363 avant son pilote Cawotte 100 % certifié. Une fois candidat fini, rapport `ATLAS_DELIVERY_REPORT` pour les 43 IDs restant dans #364 au SHA final, audit logique et contrôles de certification selon le protocole du dépôt. Les statuts `NOT_RUN` et `SKIPPED` ne valent jamais `PASS`.

## Critères de refus de fusion

- Un ID #364 absent, un comportement non livré masqué par un autre module ou un report non autorisé.
- Une classe UI dupliquée, une donnée Dofus inventée, un fallback réseau présent mais non affiché, une dégradation de navigation/resize/performance non justifiée.
- Une modification transverse qui écrase #363, #325, #285, #306 ou #358 sans résolution de conflits et preuve d'intégration.
- Une suppression de code sans recherche de consommateurs + Graphify ou une validation Windows/DOFUS présentée comme automatique.
- Un résultat Doctor/CI sur un ancien SHA, ou une prétendue certification du pilote Cawotte.

## État de reprise — 13 novembre 2026

**PR #365 toujours en Draft et non certifiée.** Le présent plan est un document de suivi ; les critères et autorisations restent exclusivement ceux de l'issue #364.

- Les lots existants ont introduit le fond étoilé via `UnityBackdrop`, plusieurs styles Unity communs, la sous-navigation réutilisable et des corrections du catalogue Guide. Ce sont des implémentations partielles, **pas** une validation de l'ensemble des 43 exigences.
- **Accueil / ATUI-002 (partiel)** : commit `0c40f6de` — réduction ciblée des seules largeurs minimales des cartes Guide et Almanax et de la colonne droite, afin que les trois colonnes puissent tenir dans la largeur minimale de fenêtre de 900 px. Aucun déplacement de panneau, changement de palette, police ni contenu.
- **Test de non-régression** : commit `1b16827b` — test Qt du placement des trois colonnes aux dimensions minimale et par défaut dans `tests/test_unity_skin.py`. **Committed, pas encore exécuté/certifié** au moment de cette mise à jour.
- **Almanax / ATHM-003 et ATAL-001 : non livré** : la page du shell et la carte de l'Accueil sont encore des placeholders. Aucun calendrier, bonus ou objet non sourcé ne doit être affiché comme réel.
- **Intégration** : la branche avait 1 432 commits de retard sur `main` au début de la reprise du 13/11. Elle a été resynchronisée par merge `f351e601` (second parent `main@76c0008b`) en réappliquant les 12 fichiers de modifications en contexte exact, sans écraser l'Organizer et le Launcher fusionnés.
- **Validation** : tests Qt réels et Doctor/Graphify du HEAD final, contrôles visuels Windows, vérification du Launcher V2, audit commit par commit et contrôle des 43 critères **encore nécessaires**. Les tests ciblés de lots antérieurs ne représentent pas une Phase Certification.

Ne cocher aucun ID de #364 sur cette seule base. Ne pas fusionner tant que les obligations du contrat et les recettes Windows ne sont pas satisfaites.

## Contrôle technique de la reprise du 13/11/2026

- **Graphify exact-SHA avant déplacement de test** : [workflow #43388403004](https://github.com/r9327/Dof-Atlas/actions/runs/43388403004), diagnostic et fraîcheur PASS pour `f351e601f8153de2a5c0b77cb857296847f9a352`. Ce n'est pas une validation des interactions UI.
- **Doctor à la même base** : [workflow #43388400626](https://github.com/r9327/Dof-Atlas/actions/runs/43388400626), diagnostic réussi mais `FULL_REQUIRED_NOT_DISPATCHED`; aucun PASS de tests complets ne peut être déduit.
- **Routage CI ciblé** : la suite non propriétaire `tests/test_shell_reliability.py` bloquait le mini-audit (`UNKNOWN_OWNER_BLOCKS_MODULAR_CERTIFICATE`, [run #43388278457](https://github.com/r9327/Dof-Atlas/actions/runs/43388278457)). Le seul test spécifique à cette PR (`test_module_subnav_reuses_buttons_and_keeps_clicks_correct`) est déplacé avec ses assertions vers `tests/test_unity_skin.py`, suite Qt/UI propriétaire. L'ancien fichier est restauré octet pour octet à `main`. La mise à jour doit encore être validée sur le nouveau HEAD.
- **Contrat livraison** : les 43 IDs de l'issue #364 sont présents dans le rapport de PR, tous `PENDING`. Aucune preuve n'autorise de les cocher globalement ni de fusionner.
- **Fond étoilé** : rendu de secours dessiné par Qt présent ; le fichier de fond personnel nettoyé n'est pas distribué. Ne pas publier la capture source du jeu sans validation des droits.
- **Manques prouvés** : Almanax encore placeholder à l'Accueil et dans le shell. Les autres exigences doivent être confrontées aux véritables comportements/captures du candidat final. Windows/DOFUS et performances restent non certifiés.

### Correction fil d'Ariane Guide — 13 novembre

- **ATGD-005 / ATUI-003 (partiel)** : le `GuidesView.build_detail_page()` plaçait `GuideHeader` avant `GuideBreadcrumb`, à l'inverse du contrat. L'ordre du `QVBoxLayout` est corrigé en **breadcrumb → entête → contenu**, sans changer les panneaux, les composants ou les données Guide.
- Test Qt dans `tests/test_guide_library_home.py` avec construction du vrai widget de détail et vérification des indices de layout; seul `QuestDetailView` est remplacé dans le test pour éviter un chargement métier hors périmètre.
- Les autres barres d'Ariane et l'essai Windows restent à contrôler ; **aucun PASS global** pour ATGD-005/ATUI-003 avant les recettes et le SHA final.

### Propriété des tests — fil d'Ariane

- L'exécution de la suite `tests/test_guide_library_home.py` au SHA `0cd1e2f47c855376cd90ea670e87ed00fa78d319` a passé ses 11 cas, dont le fil d'Ariane ; mais le routeur Doctor de lot rendait `REVIEW`, car `app/modules/encyclopedia/views/guides_view.py` n'avait pas de test reconnu comme propriétaire direct.
- Le même scénario Qt est placé **une seule fois** dans `tests/test_guides_view.py`, correspondant directement au module de production sans modifier la carte des tests ou assouplir le planificateur Doctor. L'ancien test est retiré de `tests/test_guide_library_home.py` et ce fichier retourne à la version du SHA précédent.
- Validation du nouveau HEAD et de sa suite Qt en attente ; ne pas interpréter `REVIEW` ou l'absence de FULL comme un PASS.

### Quêtes — 3e colonne masquable/restaurable (ATQT-001 partiel)

- La feuille partagée `QuestDetailView` réutilise maintenant le bouton `GuideRightPanelToggle`, avec des couleurs/états issus de `app/ui/theme.py`. Pas de palette locale, ni de nouveau renderer.
- Un clic masque uniquement la colonne « informations » et libère son espace ; le bouton reste accessible dans l'en-tête pour la réafficher. La largeur utile et le défilement de la quête courante sont conservés. Lors d'un changement de quête, le défilement repart du haut.
- La même feuille est utilisée par Quêtes et le détail Quêtes des Guides ; la progression, les données et les actions restent inchangées.
- Le test Qt `tests/test_quest_detail_view.py` couvre le round-trip, l'état du bouton, la conservation du défilement et le thème commun. La validation Doctor ciblée, l'ouverture réelle Windows et l'harmonisation du menu Quêtes restent **à prouver** ; ATQT-001 n'est pas globalement DONE.

### Correction ciblée du routage CI — Quêtes/Guide

- Le [mini-audit Scoped PR](https://github.com/r9327/Dof-Atlas/actions/runs/43393190509) a confirmé un `UNKNOWN_OWNER_BLOCKS_MODULAR_CERTIFICATE` pour `app/modules/encyclopedia/widgets/quest_detail_view.py`, malgré la présence du test Qt dédié.
- Ajout **strictement de deux chemins exacts** dans `tools/ci_domain_certification.py` : le composant partagé et son test. Les trois domaines réellement consommateurs sont `quests`, `guides` et `ui` (rapport Graphify au HEAD `bb2b44ae`). Aucun wildcard, contournement du FULL, skip ni nouvelle porte CI.
- Un test `test_shared_quest_detail_sheet_has_exact_three_domain_ownership` couvre les domaines, la planification et le refus du voisin non enregistré. L'ancien routage de toutes les autres familles reste inchangé.
- Le test UI n'exige plus qu'un QLabel hors écran génère artificiellement une barre de défilement ; il vérifie le contrat Qt avec une plage explicite et le retour borné. La présence visuelle sous Windows reste une recette distincte.
- **Statuts** : tests CI et UI au SHA de ce lot à exécuter. L'exécution des tests ciblés ne remplace ni la Phase Certification ni les critères Delivery Guard de #364.

### Guide — bouton de colonne droite, états Qt uniformisés (ATGD-004 partiel)

- Le bouton `GuideRightPanelToggle` du détail Guide utilise désormais la même politique de focus clavier et le même curseur que la fiche Quêtes ; le style QSS Unity est unique et déjà livré.
- La propriété `collapsed` reflète maintenant réellement l'état masqué/réaffiché, avec rafraîchissement ciblé de son style (sans reconstruction de la page, sans modifier les données du Guide ni la logique de splitters).
- La suite Qt propriétaire `tests/test_guides_view.py` vérifie clics, propriété, libellés accessibles et retour de la colonne. Placement visuel réel sur Windows non certifié, critère non déclaré DONE.


### Succès — colonne de détail persistante et navigation clavier (ATSC-001 partiel)

- **Défaut réel** : le catalogue créait déjà un `FixedColumnSplitter` à trois enfants, mais sa colonne de détail vide pouvait se réduire et un second clic sur le même succès la vidait. Le clavier n'activait pas la même action que le clic.
- La troisième colonne a désormais une largeur minimale de 240 px et n'est pas repliable via le séparateur ; l'état sans sélection affiche un texte discret existant (`MutedLabel`), sans précharger les détails riches sur le thread Qt.
- Réactiver un succès déjà affiché conserve sa fiche, sans deuxième chargement. `itemActivated` partage la même action que `itemClicked` pour Enter/Return et l'accessibilité.
- Un test Qt propriétaire `tests/test_achievements_view.py` couvre présence de la colonne, état vide, double activation et activation clavier, sans modifier les sources de données ou la progression.
- **Toujours partiel** : resize et navigation sur Windows réel, données métier et activation du catalogue restent à recetter ; ne pas marquer ATSC-001 comme DONE à cette étape.


### Bestiaire ↔ Encyclopédie — visibilité conservée après hydratation (ATBS-001 / ATUI-006 partiels)

- **Cause vérifiée dans le code** : `EncyclopediaPage.replace_tab_widget()` retire puis réinsère l'onglet lazy chargé ; le nouvel onglet reprend par défaut l'état visible, ce qui peut faire réapparaître un onglet Succès/Guides caché pendant une session Bestiaire.
- Le remplacement mémorise et rétablit la visibilité exacte de l'onglet, garde la sélection précédente et restaure aussi l'état de blocage des signaux Qt du parent.
- Test propriétaire `tests/test_encyclopedia_page.py` : remplacement différé de Succès pendant que Donjons est sélectionné, conservation des autres onglets masqués, et remplacement du volet courant avec signaux déjà bloqués.
- Périmètre volontairement limité à la logique des onglets ; aucun service Bestiaire nouveau, aucune donnée fictive et aucun changement du composant de navigation partagé.
- **Toujours partiel** : séquence complète de navigation et dimensions des onglets à certifier sur vrai Windows avant de clôturer ATBS-001/ATUI-006.


### Validation du routage CI Bestiaire / Encyclopédie — exact-SHA

- Le mini-audit Scoped PR a bloqué le HEAD `aeda800d` pour `tests/test_encyclopedia_page.py` : `UNKNOWN_OWNER_BLOCKS_MODULAR_CERTIFICATE`. **Ce n'est pas un échec du test Qt**, dont le lot Doctor exact-SHA est `READY` / exécution `PASS`.
- Enregistrement de **ce seul chemin exact** dans l'ensemble existant `guides` / `ui` de `tools/ci_domain_certification.py`, à côté de la page dont il certifie la visibilité. Aucun wildcard ni assouplissement du refus pour des suites inconnues.
- Ajout d'un test de routage dans `tests/test_ci_domain_certification.py` : owner de la source et de la suite, plan READY, absence de validation Phase et refus du voisin non enregistré.
- Mini-audit, tests Qt et statut de la nouvelle branche doivent être revérifiés sur le nouveau SHA avant toute conclusion de validation globale.


### Guide — références visibles à droite sans faux parcours (ATGD-006 partiel)

- Les rubriques avec des guides seulement **référencés** (ex. Zones et régions) n'affichaient aucun élément à droite malgré les données locales dans `ganymede_main_index.json`. Les références restaient uniquement dans l'arbre de gauche.
- Dans la colonne de droite, les **cartes des vrais guides jouables** sont conservées et les entrées non disponibles sont maintenant présentées séparément sous « PARCOURS RÉFÉRENCÉS · NON DISPONIBLES » : lignes textuelles désactivées, sans clic, jauge, progression, route inventée, appel réseau ou provenance externe affichée.
- La sélection de catégorie et la recherche actualisent les deux collections ; les lignes inchangées sont réutilisées lors d'une simple actualisation de progression. Le message « aucun parcours » n'est montré que si aucun résultat local ne correspond.
- Les tests existants de bibliothèque sont ajustés pour ce comportement explicitement demandé par ATGD-006 ; nouveau test Qt propriétaire `tests/test_guide_catalog_view.py` couvrant plusieurs références, blocage de l'activation, recherche et réutilisation.
- **ATGD-006 reste partiel** : essais visuels Windows et contrôle des catégories réelles indispensables ; aucune certification de guide issue de #363 n'est revendiquée.


### Personnage — colonnes adaptées à la fenêtre minimale (ATUI-002 / ATCH-001 partiels)

- **Cause dans le code** : `CharacterPage` fixait l'Équipement à 650 px min, les Statistiques à 250 px min, puis ajoutait un espacement de 8 px et deux marges de 10 px. Total **928 px** incompressibles alors que la fenêtre Atlas peut être réduite à 900 px ; cela provoquait des débordements et une croissance non souhaitée du layout.
- Modification strictement ciblée des minimas des deux cartes (Équipement **610 px**, Statistiques **235 px**), sans toucher aux proportions 70/30, aux slots 64 px, à la taille du sélecteur, aux données ou à la persistance des personnages.
- Le test Qt existant `tests/test_character_page_modern.py` vérifie les géométries réelles à **900 et 1180 px**, l'absence de débordement, la présence du sélecteur et les mêmes panneaux. Rien ne prétend valider le DPI Windows sans capture réelle.
- Reste **partiel** pour ATUI-002/ATCH-001 : autres pages, changement de DPI et scénario Windows complet à tester ; pas de statut DONE global.


### Reprise du 13 novembre — fond étoilé et progression Launcher (ATUI-004 / ATLN-002 partiels)

- **Fond étoilé** : le fallback de `UnityBackdrop` était déjà implémenté dans le shell ; aucun sprite ou fond original soumis à restriction n'a été embarqué. Ajout du test Qt `test_shell_home_margins_reveal_shared_fallback_stars` dans `tests/test_unity_skin.py`. Après une première erreur de construction de contexte corrigée en `a1e82e0b`, l'instanciation complète d'`AtlasWindow` a bloqué le runner Qt hors écran : le commit `8a33b938` remplace cette préparation lourde par la **composition réelle des sélecteurs du fond, de la pile et de la page Home**. Le test compare un pixel déterministe avec et sans étoile derrière la surface Home. [Doctor-lot #43405598127](https://github.com/r9327/Dof-Atlas/actions/runs/43405598127) : **23/23 tests PASS**, `READY`, fraîcheur PASS au SHA `8a33b938` ; pas de preuve Windows réelle ni de licence de redistribution du fond personnel. ATUI-004 demeure partiel.
- **Launcher / changement d'emplacement** : dans `app/distribution/launcher.py`, la copie des fichiers affichait **100 % immédiatement** à la fin de la migration, avant la validation de l'installation et l'acquittement Home. Le commit `6ee25111` plafonne cet avancement intermédiaire à **96 %**, sans modifier les copies transactionnelles, les checksums, le verrouillage ou le rollback ; seul le signal final de succès de lancement donne 100 %. Le commit `dfb476bf` étend le test existant `test_folder_picker_guards_migration_before_launch_and_handoff` dans `tests/test_distribution_launcher_noop_offline.py` : une copie simulée à 100 % affiche 96 %, puis 100 % une seule fois après `run_update` confirmé.
- **Validation Launcher réelle** : [Doctor-lot #43404904095](https://github.com/r9327/Dof-Atlas/actions/runs/43404904095) a **exécuté 31/31 tests PASS**, y compris ce scénario ; verdict agrégé **REVIEW**, car le propriétaire CI du chemin `app/distribution/launcher.py` n'est pas totalement couvert par la classification de ce lot (domaine UI). Il n'y a ni Phase Certification, ni validation d'un poste Windows propre. Ne pas modifier le routage de sécurité uniquement pour blanchir ce résultat.
- **Intégration** : les exigences de l'issue #364 restent en PENDING. Vérifier les deux familles de tests sur le HEAD exact après stabilisation, puis poursuivre les autres modules manquants ; ne pas considérer le fond personnel Unity comme un asset public autorisé.


### Lot transversal 13/11 — sélection stable et catalogue Guide sans vide

- **ATUI-012/013, partiels** — les lignes de Guide et de Succès réservent désormais la bordure gauche en état normal autant qu'en état sélectionné. Le QSS effectivement prioritaire de Succès (3 px) est traité, sans modifier ses couleurs Unity, ses données ou ses dimensions de panneau. Commits `0bcf370e`, `df3e5da4`, `ac308c20`, `26f20834`; test propriétaire `tests/test_theme_runtime_cache.py`. Les **10 tests passent** dans le [Doctor-lot #43407909700](https://github.com/r9327/Dof-Atlas/actions/runs/43407909700), mais son diagnostic de couverture conserve **REVIEW** (`app/ui/theme.py` non reconnu comme entièrement couvert), donc ni certification ni PASS global.
- **ATGD-006, partiel** — l'ouverture par la flèche d'une rubrique sélectionne désormais cette catégorie avec le flux `currentItemChanged` déjà existant. Elle affiche immédiatement les parcours correspondants à droite, sans déclencher les entrées seulement référencées. Commits `4685cb21` et `a7b99c71`; test Qt dans `tests/test_guide_catalog_view.py`. [Doctor-lot #43408548190](https://github.com/r9327/Dof-Atlas/actions/runs/43408548190) **SUCCESS / execution PASS / freshness SUCCESS** au SHA `a7b99c71401df3277f5db774ef7efb8c5a43270b`.
- **ATUI-013 / ATGD-006, partiels** — dans une catégorie sans parcours jouable, le catalogue absorbe la hauteur résiduelle *sous* la liste des références : titre et lignes restent groupés en haut ; si des guides jouables existent, leur grille conserve l'espace de scroll. Commits `b3b7f595`, `44649931` ; test géométrique Qt propriétaire. [Doctor-lot #43409797675](https://github.com/r9327/Dof-Atlas/actions/runs/43409797675) **SUCCESS / execution PASS / freshness SUCCESS** au SHA `44649931578030b2387b3fb201efd92ff9ba6d03`.
- **Preuve visuelle** — [Doctor Guides Windows #43409787740](https://github.com/r9327/Dof-Atlas/actions/runs/43409787740), jobs capture et verdict **SUCCESS** au SHA `44649931578030b2387b3fb201efd92ff9ba6d03`. Les captures `004-guides-catalog-alignements-open.png` et `005-guides-catalog-dimensions-open.png` montrent le bon contenu à droite et la suppression du vide vertical. Ce sont des captures Qt Windows en CI, pas une recette humaine avec DOFUS actif.
- **Launcher** — aucune retouche de son aspect dans ces lots. Le correctif antérieur de pourcentage lors de la migration de disque appartient à `6ee25111`/`dfb476bf` ; son visuel natif Tk et la recette réelle Windows restent à capturer. Ne pas utiliser une maquette comme preuve.
- **Statut** : la PR #365 reste Draft et le rapport des 43 IDs de #364 demeure PENDING jusqu'à preuves complètes (dont 3 recettes humaines), audit commit par commit et Phase Certification sur un HEAD final. Aucun report, faux PASS ou fusion implicite.


### P0 — socle Unity et composants communs (13/11/2026)

**Objectif inchangé :** `ATUI-009..016` ; réutiliser `app/ui/unity_skin.py`, `app/ui/theme.py` et `app/ui/components.py`, sans nouveau framework, sans palette alternative, sans modification de comportement métier et sans certifier prématurément l'ensemble des écrans.

- **`55cb1887`** — remplace les couleurs codées en dur des familles de widgets Unity communs par les rôles sémantiques existants : textes, bordures, sélection, focus, cartes, menus, champs et progression ; badges Accueil/Almanax reliés aux tokens. Valeurs par défaut inchangées.
- **`895548f0`** — les variantes de `atlas_stylesheet(overrides)` traversent désormais la couche `unity_skin_stylesheet` via une palette temporaire, sans mutation de `UNITY_PALETTE`, ni perte du cache normal. Tests de propagation et d'absence de mutation.
- **`58c52b64`** — `AtlasPanelToggle` dans le propriétaire UI partagé ; Guides et Quêtes réutilisent une seule source pour les flèches, focus, `collapsed`, infobulles et nom accessible. Leurs callbacks, splitters, positions de scroll et données restent indépendants. Les tests de Guides, Quêtes et Unity ont réellement exécuté **30/30 PASS** sur [Doctor-lot #43418088307](https://github.com/r9327/Dof-Atlas/actions/runs/43418088307), mais le diagnostic global du lot reste **REVIEW/FAIL** car `app/ui/components.py` n'est pas encore couvert par le routeur de propriété : il ne s'agit pas d'un certificat de PR.
- **`5b89cb86`** — `AtlasButton.set_style_name()` consolide le repolish Qt des états des boutons des onglets Outils/Stuffs et des boutons de navigation globale. Les widgets existants sont réutilisés, sans changement de taille, callback ou thème. Test du passage entre variantes et états ajouté à `tests/test_unity_skin.py`. [Doctor-lot #43418647257](https://github.com/r9327/Dof-Atlas/actions/runs/43418647257) : `NOT_RUN` car `main.py` est hors périmètre du routeur de lot et `components.py` non couvert ; aucune assertion n'y a été exécutée, les suites complètes restent nécessaires.
- **Graphify** — [carte exacte de `895548f0`](https://github.com/r9327/Dof-Atlas/actions/runs/43417365864) et [carte exacte de `58c52b64`](https://github.com/r9327/Dof-Atlas/actions/runs/43418095120) : diagnostics/fraîcheur SUCCESS, propriétaires et consommateurs examinés avant mutualisation. Un nouveau commit rend ces graphes historiques, pas preuves du HEAD final.

**À poursuivre en P0 :** inventaire écrans × composants et recensement des QSS locaux ; migrer uniquement les doublons confirmés, vérifier menus/breadcrumbs, icônes, états et Launcher/Organizer sans écraser leurs propriétaires ; demander captures Windows comparables et tests complets à la fin de l'implémentation. `ATUI-009..016` restent **PARTIELS / PENDING** ; aucune preuve Windows native DOFUS ni Phase globale ou fusion déclarée.


### P0 — suppression des faux parcours et contrôle réel des clics Guide (13/11/2026)

- **Demande :** supprimer entièrement de l'interface « PARCOURS RÉFÉRENCÉS · NON DISPONIBLES », ses listes et les entrées désactivées de l'arbre Guides. Les métadonnées source Ganymède restent intactes dans leur propriétaire de collecte (#363), mais ne sont ni chargées ni affichées comme routes jouables par le catalogue Guide.
- **Chemins UI :** suppression du panneau, de la liste, du spacer spécifique, du chargement de l'index et de la construction des faux enfants, sans affecter les vraies cartes, la catégorie Dofus et les deux guides optimisés.
- **Contrat de clic/connexion :** vrai clic souris Qt sur la grille Guide, vrai clic sur un enfant d'arbre jouable, clic souris et touche Entrée sur les cartes optimisées, changement de catégorie, absence d'ouverture pour les références non jouables et absence de double émission après activation. Les tests résident dans le **même commit que la correction** (`tests/test_guide_catalog_view.py`).
- **Vérification exigée :** suite Qt propriétaire au HEAD exact et parcours `GuideCatalogView.guideRequested` vers `EncyclopediaPage.navigate_to_guide`, puis captures CI Windows si disponibles. Un `uncovered_paths`, `NOT_RUN` ou un scénario sans capture n'est pas un PASS et doit rester consigné.


### P0 — cartes Guides optimisés / propagation Unity et clic de bout en bout (13/11/2026)

- **Cause vérifiée :** `FeaturedGuideCard` imposait son propre `setStyleSheet()` sur la carte, le titre, le sous-titre et la progression, masquant les règles de `unity_skin_stylesheet()` malgré un sélecteur Guide commun. Un changement global Unity ne traversait donc pas les deux cartes.
- **Modification ciblée :** retirer ces QSS locaux et rendre aux composants leur `objectName` propre (`GuideFeaturedTitle`, `FeaturedSubtitle`, `GuideFeaturedProgress`), avec normal/survol/focus/texte/progression dans la seule couche Unity. Utiliser les tokens existants (pas de palette parallèle) et conserver dimensions, ombre, rôle de la carte et action cachée de compatibilité.
- **Tests dans le même commit :** vérifier l'absence de style local, la propagation de `unity_skin_stylesheet(overrides)` aux cartes/enfants et le vrai clic souris ; ajout du parcours `QTest.mouseClick` → `GuideCatalogView.guideRequested` → méthodes réelles `EncyclopediaPage.navigate_to_guide/open_pending_lazy_tab` jusqu'à `select_guide(id)` sur un détail léger. Ce dernier test vérifie le câblage de navigation, **pas** le rendu d'un Guide riche ni le jeu Windows.
- **Sortie :** tests Qt propriétaires exact-SHA, Doctor-lot/visuel le cas échéant. Tout `NOT_RUN`, écart de screenshot, ou absence de validation native reste explicitement à traiter.


### Priorité immédiate — UI universelle avant finitions métier (13/11/2026)

- **Périmètre bloquant :** ATUI-009..016 avant tout autre chantier de #365. Ne pas refaire les mêmes styles par module. Les comportements des modules restent à leurs propriétaires ; #325 conserve Organizer et #285 conserve la logique Launcher.
- **Couleurs et verre Unity :** `ff8c0169` fait suivre les rôles sémantiques `UNITY_PALETTE` par les fonds de cartes, colonnes Guide, onglets, tableaux/listes, scrolls, progress, menus, dialogues, champs de saisie et tooltips. Les cinq rôles d'overlay (LIST_SURFACE, NAV_SURFACE, SCROLL_SURFACE, TOOLTIP_SURFACE, FIELD_SURFACE) sont ajoutés **à la même palette Unity** avec les valeurs visuelles déjà utilisées, sans nouvelle feuille QSS. Opacité inchangée.
- **Contrat test :** `85e7259` ajoute les assertions de propagation de ces rôles et de non-mutation de la palette. Le fait qu'un test soit committé n'est pas la preuve de son exécution.
- **Laboratoire de validation visuelle :** `app/pages/dev_ui_page.py` expose les *vrais* `AtlasButton`, `AtlasPanelToggle`, `AtlasDialog`, en-têtes, onglets, combos, menus, cases, champs, progress, transparences et couleurs. **Accès : Paramètres → Dev · Bibliothèque UI Unity → Retour aux paramètres.** La page est lazy, se libère au retour Home, n'a aucun `setStyleSheet()` local ni donnée/macro DOFUS et ne doit jamais activer le runtime.
- **Connexions cliquables :** tests dans `tests/test_unity_skin.py` pour les variantes et états de navigation, menu QAction, menu déroulant, onglets, bouton de panneau (masquer/restaurer), slider→progress, popup non bloquante et retour Paramètres. Le test vérifie aussi l'absence de style local.
- **Validation utilisateur :** ouvrir ce module dans une build Windows de ce SHA, comparer couleurs, tailles, bordures, polices, survol/focus/désactivé, scroll et popup, puis noter les écarts. Ce laboratoire **ne remplace pas** les vérifications réelles des autres modules, du Launcher natif ou d'Organizer, et ne certifie pas à lui seul ATUI-015/016.
- **Statut :** ce lot reste **partiel** tant que les suites CI au dernier HEAD, les preuves visuelles et l'inventaire de chaque écran ne sont pas passés. Ne pas cocher les 43 exigences ou fusionner sur cette seule implémentation.


### P0 UI — lot regroupé, une validation CI par priorité (13/11/2026)

- Contrat de travail : **grouper code + tests + documentation dans un seul commit par lot**, puis un contrôle CI ciblé **à la fin de P0**, pas une série de validations volontairement déclenchées à chaque micro-correction. Les checks GitHub automatiques liés au push restent sous le contrôle du dépôt : les commits de ce lot doivent donc être groupés avant push.
- **Source unique confirmée :** la fenêtre de préchargement (`app/ui/preload_popup.py`) possédait encore son `setStyleSheet` local (fenêtre, titres, progression). Les règles sont migrées à `app/ui/theme.py`, où les mêmes tokens de couleurs, font et dimensions s'appliquent à toutes les instances sans masquer le style global. Le contrôleur de préchargement, ses états et son handoff ne changent pas.
- **Validation Dev :** la bibliothèque UI expose maintenant un aperçu des vrais widgets `PreloadPopupTitle`, `PreloadPopupCurrent` et `PreloadPopupProgress`, sans instancier de worker ou d'écran modal. Les tests vérifient la propagation des tokens et l'absence de stylesheet local ainsi que la présence des widgets dans la galerie.
- **Statut :** ce lot prouve uniquement la suppression d'un doublon identifié et reste P0 partiel tant que le scénario Windows réel, les autres QSS locaux et la validation finale à HEAD exact ne sont pas bouclés.

- **Guide, finition P0** : les valeurs RGBA historiques de ses en-têtes compacts, lignes de préparation, cadres avertissement, navigation et survol Copier sont maintenant dans les rôles sémantiques de `UNITY_PALETTE` avec les **mêmes valeurs et opacités**. La bibliothèque Dev expose leurs vrais sélecteurs et teste le clic « Copier » sans aucune copie de logique métier. Tests d'override et de clic dans `tests/test_unity_skin.py`.
- **Contrôle du test préchargement** : l'assertion cible désormais le vrai nom d'appel Python `setStyleSheet` (et pas la chaîne avec parenthèses), pour détecter efficacement toute réintroduction de QSS local.


### P0 — inventaire ciblé du prochain lot de propagation

- `app/distribution/launcher_ui.py` : source Tk légère avec `UNITY_PALETTE` locale **encore dupliquée**. Les valeurs actuelles correspondent à Unity ; un test de parité basé sur l'AST de `app/ui/unity_skin.py` détecte désormais toute divergence sans charger PySide6 dans le Launcher. **Ce garde-fou n'est pas une source de vérité unique** ; extraction vers un module de tokens stdlib partagés à faire uniquement après Graphify exact-SHA et vérification packaging EXE.
- `app/pages/organizer/organizer_ui.py` : plusieurs styles locaux `OrganizerTransparentHost` identiques et un `glass_qss` spécifique au matériau. **Ne pas supprimer le matériau vitré** : une consolidation éventuelle des seuls hosts transparents exige la carte des consommateurs et un test de rendu Qt. Aucun changement du moteur Macro/Miroir/Zaap dans ce lot.
- `app/pages/dev_ui_page.py` : l'inventaire interactif inclut désormais arborescence et tableaux (sélection réelle + callbacks), saisie texte/numérique/multiligne (signaux), boutons et états précédents. Les champs numériques, éditeurs et tableaux ont le même trait de focus Unity ; test de token + clic souris Qt ajouté.
- **Limite** : contrôle des sources et tests ajoutés ne valent pas capture Windows, test DOFUS ou phase certifiée ; finaliser `ATUI-009..016` seulement après preuve des consommateurs réels.

- **Qualification des tests propriétaires** : le lot Doctor `670195ef` a exécuté les deux suites existantes : **65/65 PASS** sur les assertions, mais `REVIEW` à cause de `uncovered_paths=[app/pages/dev_ui_page.py]`. Les trois tests de la galerie (vrais clics Qt, navigation/saisie, lazy shell) sont déplacés sans duplication vers `tests/test_dev_ui_page.py`, propriétaire exact recommandé par `ai_context.recommended_tests`. Pas de modification des politiques, wildcards ni seuils du routeur. Le verdict du nouveau SHA reste à vérifier ; cela ne certifie pas la PR entière.


### P0 — palette Unity unique pour Launcher Tk et application Qt (13/11/2026)

- **Graphify préalable exact-SHA :** [#43437093712](https://github.com/r9327/Dof-Atlas/actions/runs/43437093712) : diagnostic et fraîcheur SUCCESS pour `2029029fbb87c023d65a16aea5663371f2a7ad30`. Consommateurs vérifiés : `unity_skin.py` → thème et widgets Qt, `launcher_ui.py` → `launcher.py` Tk. Aucun module de logique d'installation modifié.
- **Correction racine :** les littéraux `UNITY_PALETTE` sont déplacés sans changement de valeur dans `app/ui/unity_palette.py`, **sans PySide6 ni effet de bord**, et importés par `app/ui/unity_skin.py`. Le Launcher importe seulement l'adaptateur `launcher_colors()` du même module pur ; plus de deuxième palette couleur Tk.
- **Compatibilité :** les anciens symboles publics `unity_skin.UNITY_PALETTE`, `launcher_ui.UNITY_PALETTE` et `launcher_ui.COLORS` restent disponibles. Couleurs/dimensions/logiciel d'installation inchangés ; PyInstaller suit l'import standard du module Python sans nouvelle ressource.
- **Validation dans le lot :** `tests/test_unity_palette.py` (source/overrides/sans Qt), `tests/test_launcher_ui.py` (vrais consommateurs Tk), suite branding adaptée pour exiger une dépendance vers le seul module pur, et suppression du test AST obsolète de `test_distribution_launcher_noop_offline.py`. Doctor-lot exact-SHA et tests packagés Windows encore nécessaires, aucune certification déduite des tests committés.

- **Retour mini-CI du commit palette** : le plan indépendant a identifié exactement `tests/test_unity_palette.py` comme `UNKNOWN_OWNER_BLOCKS_MODULAR_CERTIFICATE`, bien que le Doctor-lot exécute les tests. Ajout de **ce seul chemin de test** au propriétaire `ui` existant dans `tools/ci_domain_certification.py`, avec test de chemin voisin refusé ; aucune modification des contrôles `FULL_REQUIRED`, aucune exemption `[skip ci]` ni déclassement de risque.


### P0 — supprimer les cinq QSS identiques sur les hosts Organizer

- **Graphify exact-SHA obligatoire validé** : [#43438955697](https://github.com/r9327/Dof-Atlas/actions/runs/43438955697) pour `192e71a7fa36eb27eefda9c0a23e70a51978e2b1` (diagnostic et fraîcheur SUCCESS). Consommateurs examinés : `organizer_ui.py`, `organizer_page.py`, le thème partagé, `glass_material.py` et les suites Qt.
- **Cause et changement minimal** : cinq `setStyleSheet` identiques pour `OrganizerTransparentHost` masquaient la règle exacte déjà incluse dans le `glass_qss` de l'Organizer. Suppression des **seuls cinq doublons**, sans déplacer le matériau glass, sans couleur locale ajoutée, sans toucher aux dimensions/raccourcis/clics/Zaap/Miroir. Le bouton avec padding des raccourcis reste intact.
- **Tests direct-owner** : `tests/test_organizer_ui.py` construit le vrai `CharacterSlotsPanel`, clique physiquement sur Actualiser et exige l'absence de style local sur son conteneur. `tests/test_organizer_layout.py` construit le vrai Organizer avec ses fichiers isolés et vérifie tous les hosts transparents héritant de l'unique règle QSS, sans perdre le glass.
- **Preuve restant nécessaire** : exécution du lot exact-SHA et capture Windows ; essais DOFUS multi-comptes restent à la PR #325, non annoncés PASS ici.

- **CI / clôture P0 Organizer :** le mini-audit a bloqué sur l'unique fichier `tests/test_organizer_ui.py` (`UNKNOWN_OWNER_BLOCKS_MODULAR_CERTIFICATE`) malgré sa suite Qt réelle. Propriétaire exact ajouté au routeur fermé dans les trois domaines consommateurs existants `organizer/ui/identity`, avec un test de chemin voisin toujours refusé. Aucun wildcard, skip ou modification des obligations `FULL_REQUIRED`.


### P0 — Contrat déroulants Successes / Guide Ultime (13/11/2026)

- **Racine** : le thème global expose déjà un unique `QComboBox` (normal, focus, hover, disabled, popup) pour les Succès, Quêtes, Personnage, etc. Cependant `#GuideUltimeGeneratedView QComboBox` avait **deux règles locales concurrentes** (fonds `PANEL_HOVER`, marges 6×10 et 4×8, hover `GREEN_BORDER`), qui empêchaient la propagation du modèle commun.
- **Fix minimal** : supprimer les deux règles de dropdown spécifiques et les styles bouton doublonnés devenus inutiles en haut de la feuille ; conserver le bloc final `#GuideUltimeGeneratedView QPushButton/QToolButton` et les règles métier du Guide. La sélection, les données et les callbacks des véritables Guides ne sont pas modifiés.
- **Validation dans le même commit** : `tests/test_theme_runtime_cache.py` vérifie absence d'exception Guide, couleurs popup/survol sur overrides et maintien du style bouton. La bibliothèque Dev offre le vrai parent `GuideUltimeGeneratedView` et un `QComboBox` cliquable ; `tests/test_dev_ui_page.py` exerce changement de sélection et navigation clavier Qt réelle jusqu'au callback.
- **Limites** : aucune capture du vrai écran Guide Ultime ni test de ses données métier n'est implicitement acquis ; Doctor-lot et captures Windows à vérifier sur le HEAD précis.

- **Doctor-lot #43442711796** a exécuté **18/18 tests PASS**, mais a produit `REVIEW` car `app/ui/theme.py` n'avait pas de test propriétaire au nom exact. Le test comportemental est conservé et déplacé vers `tests/test_theme.py` (source `app/ui/theme.py` → test direct), avec une assertion séparée sur le style des boutons. Ce chemin précis rejoint le domaine UI fermé ; les noms voisins restent refusés. Aucun relâchement du Doctor-lot ni de la certification globale.


### P0 — non-régression fond étoilé sur toutes les racines de modules (13/11/2026)

- Le shell `AtlasWindow` utilise déjà un unique `UnityBackdrop`, et `register_page` / `ensure_pending_page_loaded` attribuent `atlasUnityPage=true` aux pages affichées. Le stylesheet Unity possède des exceptions transparentes explicites pour les racines Encyclopédie et Guides.
- Le test Qt `tests/test_unity_skin.py::test_starry_backdrop_remains_visible_under_all_shared_shell_roots` construit un vrai backdrop et onze widgets racines aux noms exacts (Accueil, Encyclopédie, Guide, Organizer, monde, Craft, Équipement, placeholders, Paramètres, Dev). Pour chaque racine, il compare le rendu de l'étoile de fallback avec/sans étoile à la même coordonnée, après navigation de `QStackedWidget` ; le test passe uniquement si le décor n'est pas masqué par la feuille QSS.
- Il s'agit d'une **preuve Qt offscreen d'un fond de repli libre d'assets**, pas d'une capture Windows de tous les modules réels ni de la texture Unity personnelle. Les panneaux de données opaques restent intentionnellement lisibles ; pas de modification du peintre ni des performances runtime.


### P0 — un seul parcours de navigation par activation dans la grille Guides (13/11/2026)

- **Cause vérifiée dans le code** : `GuideCatalogView.home_dofus_list` connectait **à la fois** `QListView.clicked` et `QListView.activated` à `_on_clicked` ; la double activation native Qt pouvait relancer `guideRequested`, doublant la transition et le chargement du détail.
- **Correction minimale** : garder `clicked` comme unique voie souris. Deux raccourcis `QShortcut` locaux au vrai `QListView` prennent en charge `Return` et `Enter` du pavé numérique sur l'index courant, sans installer de filtre global ni perturber le composant partagé.
- **Tests du même commit** : émission `clicked` suivie de `activated` => une seule demande ; vrais événements clavier Qt pour Return/Numpad Enter => chacun ouvre le Guide sélectionné ; sélection invalide => zéro ouverture. Les cartes Guides optimisés conservent leurs propres callbacks existants.
- **Validation requise** : Doctor-lot exact SHA et CI Guides Windows ; ce changement n'est ni une certification des parcours #363 ni une recette utilisateur DOFUS.


### P0 — navigation du bandeau Unity au clavier, sans changer le survol (13/11/2026)

- **Défaut réel** : `HoverMenuButton` était `Qt.NoFocus` ; tous ses menus (Encyclopédie, Bestiaire, Outils, Stuffs, Tutoriels) étaient impossibles à atteindre via Tab, même si leur `QMenu` avait des actions Qt fonctionnelles.
- **Correction** : le bouton accepte maintenant `Qt.TabFocus` et ouvre son menu par Flèche bas/F4. Le menu natif Qt reçoit sa première action activable ; `QMenu` conserve Entrée, Échap et les clics souris. Le minuteur de suivi du curseur reste **uniquement** pour le survol afin qu'un menu ouvert au clavier ne se ferme pas alors que le pointeur est ailleurs.
- **Tests du même commit** : `tests/test_unity_skin.py` vérifie l'accès Tab, le vrai `QTest.keyClick` pour ouvrir le QMenu, le déclenchement d'un QAction par Entrée, ainsi que l'ouverture/fermeture au survol et l'arrêt du minuteur. Aucun écran métier, callback de navigation ni moteur Organizer/DOFUS modifié.
- **Limite** : l'utilisation réelle au clavier dans le shell Windows reste à vérifier dans les CI ciblées ; ne pas certifier tous les 43 critères sur ce lot.


### P0 — composants communs avant toute finition par module (13/11/2026)

- **Graphify préalable exact-SHA** : [#43451149982](https://github.com/r9327/Dof-Atlas/actions/runs/43451149982) : `061d70f4aca760f85b885d2c09e0574eb62cf4cb`, diagnostic/fraîcheur SUCCESS. Le graphe couvre `app/ui/components.py`, `app/ui/theme.py`, le shell et les vues consommatrices. Pas de modification du moteur Organizer ou des providers Guides.
- **Source unique de variantes** : `AtlasButton.BUTTON_OBJECT_NAMES` définit désormais aussi `navigation` et `navigation_active`. Les boutons de navigation du shell, les sous-onglets Outils/Stuffs, le HoverMenuButton et la galerie Dev passent par `AtlasButton(..., variant=...)` / `set_variant()` au lieu de recopier des `objectName` UI. Les identifiants QSS réels et les callbacks restent identiques.
- **Styles partagés** : `app/ui/theme.py` remplace les valeurs en dur de 11/12px et rayons 4/6/8/10px par les tokens sémantiques **déjà existants**, conservant les valeurs de rendu actuelles. Les variantes bouton principal/secondaire partagent maintenant une seule règle typographie/alignement/marges, sans perdre leurs états de couleur respectifs. Ce sont des changements à la **source commune**, pas des retouches isolées d'écran.
- **Contrôles de lot** : `tests/test_theme.py` vérifie la propagation des variantes de police, marges et rayons ; `tests/test_unity_skin.py` vérifie la commutation des états via `set_variant()` et couvre déjà la navigation réelle Qt ; aucun test déclaré PASS avant exécution Doctor/CI à ce HEAD.
- **Non inclus** : comportements Guide/Quêtes, raccourcis clavier, rendu glass et logos spécifiques. Ils ne doivent pas passer devant la clôture ATUI-009..016.

- **Couverture propriétaire des composants communs** : le Doctor-lot `061d70f4..e8fa53bd` signale `app/ui/components.py` sans test au nom exact et refuse `main.py` (module hors périmètre de ses mini-certificats). Il n'a donc **pas exécuté** les tests du lot malgré les CI habituelles vertes. `tests/test_components.py` exerce maintenant de vrais clics Qt et la propagation des rôles sur les boutons, le toggle et le dialogue. Propriétaire `ui` limité à ce seul nouveau test dans le routeur, avec test d'un chemin voisin toujours bloqué. **Aucune exemption de `main.py`, aucun test PASS inventé, aucune modification du moteur ou de la règle FULL.**


### P0 — centralisation des surfaces des fiches Guides (13/11/2026)

- **Audit des consommateurs préalable** : Graphify exact SHA `b2d6137921617bee193e901dd881eaa125567d70`, [run #43457044440](https://github.com/r9327/Dof-Atlas/actions/runs/43457044440), diagnostic et fraîcheur SUCCESS. Source `SharedGuideManualCard`, Guides différés/optimisés, rendu legacy délégué et thème global inspectés. Aucune modification du service de progression.
- **Cause réelle** : `shared_manual_guide_view.py` appliquait cinq `setStyleSheet()` locaux aux sections/lignes/cibles de combat, textes et cases, avec des niveaux de gris opaques qui masquaient le thème Unity; un changement des couleurs partagées n'était pas répercuté.
- **Correction** : supprimer ces cinq QSS locaux; donner un rôle distinct `GuideManualCombatLineRow` aux seules lignes de combat; gérer tous les rôles depuis `app/ui/theme.py`. Les surfaces et bordures glass légères sont dérivées de `PANEL_HOVER` et `BORDER_SOFT`, y compris lors des overrides, sans nouvelle palette. Même matériau subtil pour sections/combats, fond neutre pour les autres lignes. Les règles de validation, données et clics restent intactes.
- **Tests** : source propriétaire `tests/test_shared_manual_guide_view.py` vérifie absence de style local sur les vrais constructeurs de fiches; `tests/test_theme.py` vérifie propagation des couleurs/marges/rayons sur le QSS; `tests/test_lanyel_shared_manual_ui.py` conserve les vrais clics et vérifie les vrais widgets montés sans QSS local. Propriétaire CI strict `guides/ui`, aucun wildcard.
- **Pas encore preuve de release** : Doctor-lot et captures Windows doivent être évalués au HEAD exact. Les tests de contrats ne valent pas une navigation DOFUS native.


### P0 — rayons du skin Unity raccordés au thème commun (13/11/2026)

- **Un seul propriétaire des rayons partagés :** `UNITY_RADII` dans `app/ui/unity_palette.py` (module sans Qt déjà consommé par le Launcher) ; `app/ui/theme.py::SIZES` le réutilise au lieu de recopier les valeurs.
- **Propagation inter-couches vérifiable :** `unity_skin_stylesheet(overrides)` consomme les mêmes rayons pour les groupes/onglets, cartes Guides en relief, barres de progression et survol Copier. Une modification de `RADIUS_XS/SM/MD` dans `atlas_stylesheet(overrides)` ne laisse plus des règles postérieures du skin avec des valeurs 4/6/8px figées. Les rayons historiques spécifiques 5/9px restent inchangés tant que leur rôle n'est pas validé comme commun.
- **Non-régression :** les valeurs par défaut, états, assets Unity, performances, données Guides et logique Organizer/Launcher restent inchangés. Tests ciblés dans `tests/test_theme.py` et `tests/test_unity_skin.py`; certificat Doctor/Windows à confirmer au SHA exact. Ne pas déclarer les critères ATUI-009..016 DONE sur ce seul lot.

- **Diagnostic Doctor du lot rayons :** [run #43461403077](https://github.com/r9327/Dof-Atlas/actions/runs/43461403077) — FAIL (2 assertions de `tests/test_theme.py`, antérieures au lot, qui visaient respectivement le premier bloc commun plutôt que le dernier bloc de couleur secondaire et un sélecteur `QCheckBox#...` absent alors que le QSS utilise `#GuideManualCombatCheck`). Les deux sélecteurs existants et leur comportement restent inchangés ; corrections **uniquement dans les assertions** pour tester la règle réellement appliquée. Revalider au nouveau SHA, sans maquiller les FAIL historiques.


### UI commune — rôles de liens mutualisés entre Guides, Quêtes et Succès (13/11/2026)

- Les rôles `guide_breadcrumb`, `guide_quest_link` et `guide_achievement_link` ont un seul propriétaire : `AtlasButton.BUTTON_OBJECT_NAMES` dans `app/ui/components.py`. Les vues Guides, Quêtes et Succès passent le rôle à `AtlasButton(..., variant=...)` plutôt que copier un `setObjectName` local.
- L'ancien sélecteur `GuideBreadcrumbButton` dupliqué dans le bloc Guide est supprimé ; la règle sémantique de `app/ui/theme.py` demeure la seule source de style. Les identifiants QSS, couleurs effectives, comportements de clic, textes et destinations existants restent inchangés.
- La galerie `Dev · Bibliothèque UI Unity` présente les trois vrais boutons et leurs signaux Qt. Tests directs : `tests/test_components.py`, `tests/test_dev_ui_page.py`, `tests/test_theme.py` (identité et propagation des couleurs, absence du double sélecteur).
- **Statut : implémentation ciblée, pas certification.** Doctor et CI au SHA exact, puis contrôle visuel Windows restent nécessaires ; aucune modification métier, du réseau ni des données Guides.


### Bibliothèque Dev — inventaire visuel complet des familles UI (13/11/2026)

**Périmètre de ce lot uniquement** : enrichissement du laboratoire `app/pages/dev_ui_page.py`, pas de refonte visuelle des écrans métier ni de certification de la globalisation.

- **15 familles visibles** avec titres explicites, sections existantes conservées et sommaire fixe `Aller à une famille` qui fait défiler la zone centrale jusqu'à la catégorie voulue : boutons/états, onglets/menus/navigation, listes/arbres/tableaux, scroll/redimensionnement, champs simples, formulaires avancés (lecture seule, désactivé, mots de passe, date/heure/nombres), statuts/badges, surfaces/cartes/typographies, panneaux repliables, préchargement, surfaces Guides, icônes/raccourcis/tooltips, matrice des modules consommateurs, dialogues, palette Unity.
- **Comparaison réelle** : composants existants (`AtlasButton`, `AtlasPanelToggle`, `AtlasDialog`, `AtlasPageTitle`) et contrôles Qt qui héritent du thème ; identifiants QSS communs uniquement, pas de `setStyleSheet` local. Les candidats non encore généralisés sont montrés comme inventaire, sans prétendre qu'ils sont déjà consommés partout.
- **Palette exhaustive** : chaque entrée de `app.ui.theme.PALETTE` s'affiche automatiquement en swatch 3 colonnes (le Launcher Tk reste séparé, via l'adaptateur de la palette pure). Pictogrammes Unity locaux affichés uniquement lorsqu'ils existent, un indicateur neutre apparaît sinon : aucun faux asset.
- **Interactions vérifiables** : choix d'onglet, menus, clics, boutons d'état, champs, arborescence, tableau, scroll/splitter, progression/busy, navigation vers la section, popups et retours. Aucun runtime DOFUS, téléchargement ou création de données métier. Tests ajoutés à `tests/test_dev_ui_page.py` : couverture de l'inventaire, boutons/clics, propriétés de statut, palette exhaustive, sections et scroll/navigation, absence de QSS local.
- **Contrôle visuel demandé** : sur une vraie build Windows, ouvrir Paramètres → Dev · Bibliothèque UI Unity ; contrôler le bandeau/sommaire, les 15 sections, le scroll, la largeur minimale et la popup, puis prendre une capture Qt. Une image de simulation extérieure à Qt ne constitue PAS cette preuve.
- **Consigne de livraison** : ne pas déclencher de CI manuelle avant la fin de la globalisation entière ; tests et recettes exact-SHA finaux seulement. La CI automatique éventuellement déclenchée au push reste distincte d'une certification.


### UI darkStone — couleurs par usage, tailles et icônes communes (13/11/2026)

**Objectif de design** : s'inspirer des positions et états des composants du client DOFUS Unity, dans la variante **darkStone** dont les sprites sont déjà fournis pour usage local. Ce n'est pas une nouvelle palette personnelle, ni la preuve d'une copie pixel-perfect de la version live (l'interface du jeu et ses thèmes évoluent). Éviter d'importer de nouveaux logos de jeu.

**Mapping unique composant → couleurs → états** :
- Fenêtres/cartes : `BG/PANEL/BORDER`, référence `window_border_top.png` / `Assets_UI_Themes_darkStone_common_bg_small_border_light-png.png`.
- En-têtes/navigation : `NAV_SURFACE/TEXT_SOFT`, sélection d'onglet `PANEL_ACTIVE/GREEN_BORDER`, sprite d'onglet sélectionné si localement disponible.
- Bouton d'action : `GREEN/GREEN_BORDER`, sprites `btn_green_{normal,over,pressed,disabled}.png` ; bouton secondaire : `PANEL_2/BORDER_CARD`, sprite `btn_yellow2_{normal,over,pressed,disabled}.png` quand disponible.
- Champs/listes : `FIELD_SURFACE/LIST_SURFACE` et bordures communes ; survol : `PANEL_HOVER` ; tooltips : `TOOLTIP_SURFACE`.
- Les 18 noms legacy spécifiques aux Guides restent acceptés pour compatibilité, mais leur rendu par défaut est maintenant dérivé des tokens Unity génériques via `resolve_unity_colors`. Les overrides explicites Guide restent possibles. Un changement des tokens globaux se propage dans QSS et `unity_skin_stylesheet()`.
- La galerie Dev met **10 couleurs principales** en avant avec une grille de leurs emplacements ; les autres rôles techniques sont masqués par défaut mais consultables. Les gradients QSS sont rendus avec leurs vrais stops, pas un `QColor` invalide.

**Tailles et icônes** :
- Une seule échelle `UNITY_SIZES_PX` : boutons 24/32/40 px et icônes 16/20/24/32 px. Les dimensions existantes restent inchangées, les nouvelles variantes sont montrées dans `Dev UI`. `AtlasButton` partage la hauteur compacte avec `theme.SIZES`.
- L'appel unique `unity_ui_icon(name, size)` utilise en priorité l'icône DOFUS Unity locale autorisée, et sinon un fallback vectoriel monochrome Qt. Plus de `—` dans la galerie Dev ; aucun nouveau sprite de jeu dans une release publique.
- Tests ajoutés `tests/test_unity_palette.py`, `tests/test_theme.py`, `tests/test_unity_skin.py`, `tests/test_dev_ui_page.py` : propagation de couleurs, maintien des overrides, SVG-like raster Qt de secours, palette détaillée, taille des contrôles, rendu d'un dégradé et interactions de la galerie.

**Statut** : unification ciblée implémentée, mais le résultat graphique sur le vrai poste Windows et la conformité avec les derniers écrans du client DOFUS restent à vérifier visuellement. Une capture ou un mockup ne vaut pas une certification. Pas de CI manuelle avant la fin de la globalisation entière ; les actions déclenchées automatiquement par GitHub lors du push ne constituent pas une demande manuelle de validation.
