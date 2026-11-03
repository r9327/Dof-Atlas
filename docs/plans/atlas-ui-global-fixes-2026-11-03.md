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

Le correctif Switch clic Unity ATMC-003 et les 24 autres critères Organizer/Macro/Zaap/recette multi-fenêtres ont été **transférés** de #364 vers #321. Les correctifs des événements souris ont été commités historiquement sur #365 mais **leur code y est encore présent** ; la migration technique doit préserver le clic physique source et les hooks Miroir/molette existants dans #325. Ne retirer les modifications natives de #365 qu'après transfert vérifié et contrôle Graphify exact-SHA des consommateurs, sans perte des tests. Pas de certification Unity implicite.

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

**À ce stade : document de cadrage uniquement, code produit inchangé et aucun test exécuté.**
