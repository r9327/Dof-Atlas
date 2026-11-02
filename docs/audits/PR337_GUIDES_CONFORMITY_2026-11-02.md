# PR #337 — Audit des 15 parcours à consignes locales

**Date :** 2026-11-02  
**Commit de code audité :** `ac449ddd369cbc243f6144d991e2386d0291ba7b`  
**Verdict :** **CHANGES REQUIRED — 0/15 parcours certifiés à 100 %**  
**Périmètre :** les 15 fichiers `data/encyclopedia/guides/ganymede_<id>_instructions.json` présents à ce HEAD. Aucun nouveau guide n'est créé dans cet audit.

## Résultat vérifiable

- **15 fichiers rédigés**, **212 étapes numérotées**, **645 actions structurées**.
- **15/15** ont des snapshots de liens factuels locaux. Ces snapshots déclarent `quest_objective_mapping_verified: 0` et `route_order_certified: false` : ils ne contiennent **pas** les objectifs de jeu complets ni l'ordre éditorial certifié de la source.
- **231 actions avec coordonnées** : **229** portent une position également mentionnée dans le relevé de leur étape ; **2** ne correspondent pas à ce critère. Ce critère ne garantit pas qu'une coordonnée présente soit correcte en jeu.
- Les 15 fichiers passent le contrôle **statique de structure** (étapes numérotées, textes/actions présents, types admissibles). Cela ne valide ni les PNJ, dialogues, quantités, embranchements, optimisations, prérequis ni combats réels.
- L'accès web direct à des guides `ganymede-app.com/guides/<id>` a renvoyé un document HTML sans texte lisible exploitable pour une confrontation éditoriale intégrale dans cet environnement. **Aucune comparaison exhaustive 1:1 avec les pages originales n'est démontrée.**
- Aucun **test PySide6/Qt/Windows**, essai sur jeu réel, exécution de Doctor/benchmark ni certification exacte-SHA n'a été produit pour ces 15 parcours durant cet audit.

## Inventaire par guide

| Source | Parcours Atlas (nom courant) | Étapes | Actions | Actions GPS | GPS à examiner | Conformité 100 % |
|---|---|---:|---:|---:|---|---|
| 2219 | Otomaï 1 | 7 | 21 | 5 | Aucun écart de relevé | NON PROUVÉE |
| 2220 | Otomaï 2 | 7 | 19 | 6 | Aucun écart de relevé | NON PROUVÉE |
| 2224 | Sidimote 1 | 25 | 79 | 34 | Aucun écart de relevé | NON PROUVÉE |
| 2227 | Koalaks | 9 | 33 | 10 | Aucun écart de relevé | NON PROUVÉE |
| 2240 | Xélorium 1 | 27 | 71 | 29 | Aucun écart de relevé | NON PROUVÉE |
| 2247 | Dofus Nébuleux | 6 | 22 | 5 | Aucun écart de relevé | NON PROUVÉE |
| 2248 | Dolmanax | 9 | 30 | 1 | Aucun écart de relevé | NON PROUVÉE |
| 2252 | Otomaï 3 | 13 | 37 | 12 | **Étape 1 [-48,19]** | NON PROUVÉE |
| 2259 | Sidimote 5 | 25 | 71 | 44 | Aucun écart de relevé | NON PROUVÉE |
| 2273 | Argenté Scintillant | 15 | 47 | 15 | **Étape 8 [-71,-78]** | NON PROUVÉE |
| 2274 | Roc des Salbatroces | 26 | 62 | 21 | Aucun écart de relevé | NON PROUVÉE |
| 2284 | Le secret des Dofus : Prologue | 21 | 75 | 27 | Aucun écart de relevé | NON PROUVÉE |
| 2285 | Dom de Pin | 4 | 15 | 3 | Aucun écart de relevé | NON PROUVÉE |
| 2290 | Dofus Sylvestre (source) | 2 | 9 | 1 | Aucun écart de relevé | NON PROUVÉE |
| 2590 | Halouine | 16 | 54 | 18 | Aucun écart de relevé | NON PROUVÉE |
| **TOTAL** | | **212** | **645** | **231** | **2** | **0/15 certifié** |

**Interprétation des écarts GPS :**

1. `ganymede_2252_instructions.json` (Otomaï 3), étape 1, indique `[-48,19]` pour le professeur Fournesol. L'observation associée à l'étape 1 ne mentionne aucune coordonnée ; `[-48,19]` apparaît à l'étape 2. Cela peut être un trajet introduit trop tôt, **pas une preuve de fausse position en jeu**.
2. `ganymede_2273_instructions.json` (Argenté Scintillant), étape 8, indique l'entrée d'Externam en `[-71,-78]`, tandis que le relevé local mentionne `[-74,-83]` à cette même étape. Une vérification de destination et de contexte est requise. **Ne pas corriger automatiquement en recopiant le relevé.**

## Écart fonctionnel majeur : présentation actuelle

`app/modules/encyclopedia/views/guide_catalog_view.py` crée `GanymedeSourceReader`, un dialogue `QDialog` de 950×700 pixels et affiche `_format_offline_instruction()` via un **`QPlainTextEdit` en lecture seule**. Il fournit Précédent / Actuelle / Suivant, Valider l'étape, copie du premier `/travel`, et progression manuelle par personnage.

**Ce n'est pas le rendu du grand Guide Succès optimisé** : aucune preuve de cartes avec icônes d'objets, combats cochables individuellement, préparations fusionnées, sections riches de navigation ou fiche stylisée équivalente. Le JSON contient des phrases et des types d'action, **mais pas nécessairement toutes les données structurées nécessaires à cette UX**. L'import des consignes n'établit pas la parité de l'interface.

## Faux positif de certification à éviter

`tools/audit_ganymede_instruction_coverage.py` compte une route comme `complete_offline_instruction_routes` si le fichier et ses étapes respectent le contrat de **structure**. Même si ce compteur atteignait 95/95, `PASS_INSTRUCTION_COVERAGE` ne certifierait **ni conformité à l'intégralité des étapes source ni vérification dans le jeu**. Toujours séparer :
- **rédigé / parseable** ;
- **correspondance source vérifiée étape par étape** ;
- **tests runtime/jeu/UX validés** ;
- **certifié à 100 % sur SHA exact**.

## Conditions nécessaires avant toute nouvelle route

1. Pour **chacun des 15**, disposer d'une référence exhaustive et fiable du chemin réellement attendu, puis rapprocher chaque étape et chaque action (pré-requis, destination, dialogue, collecte, combat, quantité, embranchement, objectifs parallèles et fin de quête) ; relever chaque ajout/manque.
2. Résoudre les deux positions litigieuses sur preuve externe ou en jeu, plutôt que substituer une coordonnée non vérifiée.
3. Tester le lecteur réel et le rendu demandé (y compris états de progression, commande /travel, images d'objets, préparation et combat), vérifier que les deux gros guides optimisés ne changent pas.
4. Exécuter les tests ciblés, Doctor et les validations Windows appropriées. Puis documenter **pour chaque guide** un état `CERTIFIÉ` uniquement lorsque la preuve de parité complète et d'exécution est disponible.
5. **Blocage de production du contenu : pas de nouveaux parcours tant que la conformité des parcours déjà rédigés n'est pas vérifiée**, conformément à la demande du propriétaire de l'application. Conserver PR Draft et ne lancer ni fusion ni release avant résolution.

**Note de méthode :** cette revue est un **audit statique factuel des fichiers réellement présents à GitHub**, et non un audit de contenu complet de Ganymède ou une capture Windows authentique. Elle n'apporte aucune preuve de réussite en jeu.

## Reprise du 2 novembre — contrôle éditorial et parité de rendu (PR #337)

**Règle acceptée :** chacun des 95 parcours doit réutiliser l'expérience de
`SharedGuideManualView` des deux parcours optimisés (en-tête compact, route /
préparation / succès, sommaire et personnage, progression, navigation et styles).
Les positions doivent être **en gras et copiables au clic**, les objets à
acheter/récolter **copiables avec les mêmes couleurs** que les guides optimisés,
et les PNJ identifiés par **les mêmes règles de couleur**. Il faut réutiliser les
règles et composants existants, sans introduire une seconde palette ou altérer
les deux grands parcours optimisés. L'actuel `QPlainTextEdit` du lecteur local
ne satisfait pas ces critères : **UI NON CONFORME, non certifiée**.

**Certification obligatoire avant chaque nouveau guide :** confronter dans
l'ordre chaque étape de la référence Ganymède à la route Atlas (préparation,
objets et quantités, PNJ/dialogues, coordonnées, combats, interactions,
bifurcations, renvois et validations) et inscrire les écarts ; vérifier ensuite
copie des coordonnées/objets, en-tête, progression par personnage, rendu Qt,
persistance et performances. Aucun statut CERTIFIÉ par simple conformité JSON,
coordonnées présentes ou tests simulés. Revue en jeu/Windows non exécutée et
toujours bloquante pour la certification finale. La source sert à contrôler le
**chemin et les objectifs**, sans recopier le texte éditorial protégé.

**Premier écart revu (Otomaï 1 #2219) :** le guide de référence GP6/MG6 situe
les trois combats du bateau à l'étape 4, après l'embarquement de l'étape 3.
Le JSON Atlas les affectait à tort à l'étape 3. **Correctif proposé dans ce
lot :** déplacer l'action de combat à l'étape 4 et rendre la transition claire,
avec test de non-régression. Références :
https://ganymede-app.com/guides/2219 et
https://ganymede-app.com/guides/183 .
Ce contrôle **local de deux étapes ne certifie pas** l'intégralité d'Otomaï 1,
encore moins les 14 autres. Statut inchangé : **0/15 certifié**, PR Draft,
aucune Phase Certification ni release demandée.

## Recontrôle des relevés factuels et réparation du chargeur (2 novembre, lot suivant)

**Révision GitHub analysée :** `40be25d6976adeb2ed2cb99b221865d5cf35c145`.
La comparaison ci-dessous a été recalculée sur les JSON lus depuis GitHub,
en rapprochant chaque action possédant `coordinates` du
`coordinate_mentions` de la **même étape** de son relevé factuel local.
Ce n'est pas un test Python/Qt exécuté ni une preuve de conformité éditoriale.

- Les **15 consignes locales** représentent toujours **212 étapes,
  645 actions et 231 actions positionnées**.
- **229/231** coordonnées se retrouvent dans les observations **à la même
  étape** ; seules les deux divergences déjà listées ci-dessus demeurent
  (#2252 étape 1, #2273 étape 8). Aucun de ces relevés ne certifie le trajet
  réel dans le jeu ou l'identité d'une carte/dimension.
- Le catalogue annonce **95 sources / 7 705 étapes** et le répertoire
  contient **95 relevés factuels**. Un défaut confirmé du chargeur ne
  reconnaissait pas les **10 fichiers historiques** nommés `argente`,
  `cawotte`, `dokoko`, `dolmanax`, `emeraude`, `glaces`,
  `ivoire`, `pourpre`, `turquoise` et `veilleurs`.
  Le mapping `_LOCAL_OBSERVATION_ALIASES` de
  `guide_library_sources.py` comprend désormais **24 alias**, dont les
  identités et décomptes de ces 10 fichiers ont été confirmés à leur source
  JSON. **95/95 chemins sont résolus** depuis les IDs du catalogue ; cela
  prouve l'existence des fichiers, pas leur certification de contenu.
- Un test ciblé a été ajouté pour charger les observations des **95 IDs**
  et vérifier numérotation et décompte ; **NON EXÉCUTÉ** sur Windows/CI
  dans cette session. Les 9 tests de l'analyse inter-guides sont également
  **NON EXÉCUTÉS** ; aucun PASS n'est revendiqué.

La nouvelle commande `py -3.13 -m tools.audit_ganymede_crosswalk
--cross-guide-candidates` fournit à l'avenir le diagnostic répétable par
guide, les références externes réutilisées et les recoupements de coordonnées.
Elle **n'active ni regroupement automatique ni validation** et refuse de
déclarer le Guide Succès remplacé.

**Verdict maintenu : CHANGES REQUIRED.** Certification réelle des 15 guides :
**0/15**. Révision de la route originale étape par étape, correction des
divergences, tests UI/Windows/DOFUS, Doctor et Graphify exact-SHA restent
indispensables avant une refonte commune et la certification des 80 suivants.
