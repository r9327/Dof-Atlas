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
