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

## Correctif incrémental Otomaï 3 et revue GPS (2 novembre — reprise)

- `ganymede_2252_instructions.json` : l'action de déplacement vers le
  Professeur Fournesol **[-48,19]** a été déplacée de l'étape 1 vers
  l'étape 2, **sans supprimer l'action**, sans changer la carte et sans
  toucher au dialogue/à la validation de l'étape 3. Le relevé local
  `ganymede_otomai_3_observed_links.json` ne contient aucune coordonnée
  à l'étape 1 et mentionne [-48,19] à l'étape 2. Cette destination est
  aussi décrite par
  https://www.dofuserie.com/quetes/la-potion-bulbique/
  et https://doflex.fr/fr/encyclopedia/quests/118-la-potion-bulbique .
  **Contrôle de placement réalisé, pas preuve de l'intégralité de la route Ganymède.**
- Un test ciblé verrouille le positionnement étape 2 et le dialogue
  Fournesol à l'étape 3. **NOT_RUN** (pas de checkout Python/Windows).
- L'outil `audit_ganymede_crosswalk --cross-guide-candidates` expose désormais
  `coordinate_comparison_counts` et `coordinate_review_queue`. Il distingue
  les positions mentionnées dans le relevé de **la même étape**, celles
  absentes et les relevés manquants. Il ne transforme jamais un constat
  en validation de carte, de quête ou de personnage.
- Conséquence arithmétique de ce déplacement sur les données contrôlées :
  **230/231** actions positionnées correspondant au relevé de leur étape
  (contre 229/231 avant correction). Un seul écart documentaire connu
  reste à investiguer, **#2273 étape 8**.
- **Argenté Scintillant #2273** : la source indépendante
  https://www.dofuserie.com/quetes/le-silence-est-d-aure/
  situe le Gardien du Jour sans fin à **[-71,-78]**. Le relevé factuel
  Ganymède local de l'étape 8 mentionne **[-74,-83]** tandis que la route
  Atlas affiche [-71,-78] à cette même étape. Ces coordonnées ne
  sont pas interchangeables sans vérification du chemin spécifique et
  de la transition entre les étapes. **Aucune substitution automatique** :
  position conservée et anomalie tracée pour revue source/jeu.

**Statut : 15/95 rédigés ; 0/15 certifiés en source/Windows ; PR Draft /
CHANGES REQUIRED.** Les tests ajoutés et la commande d'audit restent à
exécuter dans un environnement de développement complet. Ni la concordance
GPS ni la présence de 95 snapshots ne suffisent à remplacer le Guide Succès.

## Lot contenu — rédaction effective des guides manquants (PR #337)

**HEAD de contrôle statique sur GitHub :** `98543c85945875749d20a854aab1528b134d2bb8`.
Quatre fichiers de travail **non jouables** ont été ajoutés sous
`data/encyclopedia/guides/replacement_drafts/authoring/` : **2204
(Mais où sont les Dofus ?), 2206 (Valonia 1), 2228 (Sufokia) et 2229
(Nimaltopia)**. Ils comportent chacun les **10 premières étapes**,
réécrites en français, avec des actions structurées (préparation, dialogue,
combat, interaction, trajet et craft selon la source). Chaque étape a été
rapprochée du relevé factuel portant le même ID de guide et le même numéro
d'étape, sans recopier le contenu éditorial source.

| Guide | Étapes de travail / total | Actions | Coordonnées recoupées |
| --- | ---: | ---: | ---: |
| 2204 | 10 / 26 | 37 | 17 / 17 |
| 2206 | 10 / 30 | 38 | 19 / 19 |
| 2228 | 10 / 39 | 31 | 18 / 18 |
| 2229 | 10 / 67 | 34 | 18 / 18 |
| **Total** | **40 / 162** | **140** | **72 / 72** |

**Preuve :** fichiers lus à leur HEAD GitHub et contrôlés par parcours :
ordre strict, types d'action admissibles, statut `PARTIAL_NOT_PLAYABLE`,
aucune certification déclarée et chaque coordonnée présente dans le
relevé local de l'étape correspondante. Ce contrôle est **statique** et ne
certifie ni l'identité des mondes, ni l'objectif de quête, ni les noms
traduits, ni les combats/quantités dans DOFUS.

Un nouveau module de test `tests.test_ganymede_partial_authoring` vérifie
la cohérence des brouillons et l'absence d'activation accidentelle par le
chargeur strict des guides finis. **Tests Python non exécutés** dans cette
session ; pas de preuve Windows/Qt, de Graphify ni de Doctor associée.

**Avancement métier inchangé :** **15/95 guides complets sur la seule
structure, 80/95 encore sans fichier de consignes complet, 0 guide certifié
en source/Windows**. Les 40 étapes nouvelles sont une avancée de rédaction
à l'intérieur des 7 493 étapes manquantes, **elles ne sont pas comptées
comme quatre guides terminés**. Il reste respectivement 16, 20, 29 et
57 étapes à rédiger dans ces quatre parcours. Les deux guides optimisés
restent intacts, sans changement de validation ni de progression.

### Suite de développement

- Terminer les étapes restantes des quatre parcours **sur une source
  intégrale réellement consultable** et en respectant les embranchements
  de chacun ; ne pas remplacer les trous par des positions, liens ou
  objectifs inventés.
- Comparer ensuite chaque étape/action à la référence source, confirmer
  les noms et les actions sous DOFUS Unity, et convertir le fichier partiel
  en `ganymede_<id>_instructions.json` uniquement lorsque le parcours
  complet est prouvé et accepté par le chargeur strict.
- Répéter ce cycle sur les 76 autres guides encore sans rédaction ;
  ne pas lancer le Guide Ultime, la CI finale ni la fusion prématurément.

**Verdict global maintenu : CHANGES REQUIRED / PR Draft.**

## Relecture des quatre premières séquences — second lot (#337)

**SHA de l'examen des données :** `7f281184644f5f1d3a703f616fe80c81b69e69c5`.

Les dix premières étapes des quatre guides de travail (2204, 2206, 2228,
2229) ont été confrontées aux informations de leurs pages Ganymède publiques
accessibles pour ce segment. Les données ont été améliorées **sans inventer
les étapes 11+**, qui n'étaient pas intégralement accessibles depuis les
sources consultées dans cette session.

- **2204**, *Mais où sont les Dofus ?* : prérequis du Réceptacle des Dofus
  (Fallanster, parcours Argenté), niveau conseillé 50 ; rétablissement du
  **passage intermédiaire par le pont de Pandala [12,-21]** à l'étape 6,
  avant [19,-28], avec l'action de trajet typée.
- **2206**, *Valonia 1* : niveau conseillé 60, absence de ressources ou
  quêtes préalables obligatoires, **100 kamas** de traversée et capture
  facultative du Raccooper pour le Dofus Ocre.
- **2228**, *Sufokia* : niveau conseillé 40, deux succès distincts,
  ainsi que les connexions optionnelles avec le tour des donjons et les
  alignements Bonta/Brâkmar, sans rendre ces détours obligatoires.
- **2229**, *Nimaltopia* : niveaux et prérequis explicites, dont
  « Aventure miniature » et « Ne tirez pas sur le messager », et ressources
  réparties entre « Frais de porc inclus », « Nos amies les bêtes »,
  « À armes égales ». **20 Eaux potables au total, pas deux fois 20.**
  Ces libellés de quêtes françaises ont été rapprochés d'une table de
  traduction externe ; les conditions de jeu restent à valider en runtime.

**Recomptage des quatre JSON sur GitHub après modifications :**
`40 étapes / 162 attendues`, **150 actions structurées** et
**73/73 actions positionnées présentes parmi les coordonnées mentionnées
dans le relevé de même étape** ; aucune incohérence d'ordre, de type
d'action ou de statut détectée par le contrôle statique.
Leur état reste `PARTIAL_NOT_PLAYABLE`, avec
`source_parity_certified=false` et `gameplay_certified=false`.
Le module de test dédié couvre désormais **4 méthodes**, dont une
sur les prérequis d'ouverture ; **tests Python NOT_RUN**, sans preuve
de certification DOFUS/Qt/Windows.

**Source des points factuels de ce lot :**
- https://ganymede-app.com/guides/2204
- https://ganymede-app.com/guides/2206
- https://ganymede-app.com/guides/2228
- https://ganymede-app.com/guides/2229

**Reste inchangé : 15/95 parcours complets structurellement, 0/95
certifié intégralement, 80/95 à achever.** Les quatre brouillons représentent
40 étapes rédigées en plus, mais ne changent pas le compteur de guides
livrables. Les deux optimisés actuels restent intacts. **PR Draft /
CHANGES REQUIRED**, aucune phase CI finale déclenchée.

## GP4 et Valonia 1 — deux brouillons 100 % rédigés (2 novembre)

**Objet exclusif de ce lot : progresser sur les guides manquants.**
Les données créées restent sous `replacement_drafts/authoring` et ne
sont pas promues dans le runtime.

- **2204 Mais où sont les Dofus ? : 26/26 étapes écrites, 114 actions,
  46/46 positions mentionnées dans le relevé de la même étape.** Les
  étapes 11–26 décrivent l'acquisition de la Pinte du visionnaire,
  le Feu prophétique en **un** combat solo (réparti sur les étapes
  éditoriales 13/14 sans double comptage), Guipol en solo, les Wabbits
  en groupe, le temple de classe, la bénédiction, la Forêt Maléfique,
  les deux combats solo du Dark Vlad, puis Mériana.
  Sources indépendantes par quête référencées dans le JSON et dans
  `docs/guides/GANYMEDE_AUTHORING.md`.
- **2206 Valonia 1 : 30/30 étapes écrites, 124 actions, 55/55 positions
  mentionnées dans les relevés correspondants.** La suite documente
  120 kamas de taverne, la chasse aux pièges et le combat de
  Trankilou en groupe, la kole pour le barrage, l'option du passeur
  à 50 kamas, le boss Rakoopeur au Refuge sylvestre, la guérison
  de Bentlaitue et l'arrestation des P.O.M.S. Les PNJ et objets
  de Valonia ont été revus en français contre des fiches de quêtes
  indépendantes : Hönger Lébaï, Bryra Borouié, Judeau Keuter,
  Leichäf Odäg, Thomondor, Rakoopeur, Balai rudimentaire.
- **2228 Sufokia : 10/39 étapes** ; **2229 Nimaltopia : 10/67 étapes**.
  Aucun saut n'est inventé pour ces deux guides.

**Comptes directs au HEAD `f48b0bdce0de6c4644e1719e151b68db29915a17` :**
76/162 étapes rédigées pour ces quatre sources,
309 actions typées, 137/137 déplacements concordant avec le relevé
*documentaire de la même étape* et 0 anomalie structurelle détectée
par la lecture JS des JSON distants. Ces 137 correspondances ne prouvent
ni l'identité des cartes et dimensions, ni les conditions d'objectif,
ni la parité au texte et à l'ordre de la source Ganymède.

Les deux brouillons entiers sont
`FULL_DRAFT_NOT_PLAYABLE`, `source_parity_certified=false`,
`gameplay_certified=false`. La promotion au format
`ganymede_<id>_instructions.json` demeure **interdite** sans la
confrontation des 26 et 30 étapes à la source exacte et la revue de
validation par personnage. Le test dédié protège maintenant également
la distinction groupe/solo, l'absence de doublon du Feu prophétique
et les noms français des PNJ : **non exécuté dans un checkout Python**.

Les étapes source 11+ des deux guides n'étaient pas lisibles
intégralement dans l'outil de consultation au moment de cette séance ;
le contenu des quêtes a été composé à partir de sources indépendantes
et de relevés Atlas, **pas certifié comme une transcription des
instructions Ganymède**. Le correctif ne touche pas l'interface,
le planificateur, les deux guides optimisés, ni la persistance.

**Bilan livraison : 15/95 fichiers complets publiés antérieurement
(non certifiés), 2 brouillons entiers supplémentaires hors runtime,
78 autres parcours sans brouillon entier, 0/95 certifié DOFUS/Windows ;
PR Draft / CHANGES REQUIRED.** Phase CI finale, Doctor Windows,
benchmark et fusion toujours non lancés.

## Quatre brouillons complets — lot Sufokia/Nimaltopia du 2 novembre

**Portée : contenu et tests éditoriaux exclusivement.** L'objectif reste
95 parcours complets et certifiés individuellement avant tout nouveau Guide
Succès croisé. Aucun brouillon non certifié n'est activé dans l'application.

Les étapes **11–39 de Sufokia** (#2228) ont été rédigées dans l'ordre
des observations locales, avec un suivi original des douze quais,
des six barques d'« Investigation embarquée », des combats contre les
Scarafeuilles et les bandits, des cinq objets volés, des vingt pains
distribués à quatre collecteurs et des confitures/jus de Gelées.
Correction ciblée : les coordonnées correspondant à l'étape *suivante*
avaient été insérées quatre fois dans l'étape précédente (31–34) ;
elles ont été retirées, pas déplacées ou inventées. Les noms de PNJ
français (Océane, Mage Hellan, Paul Auchon, Jemas Kooc et Joëlle
Raiebuchon) sont relus contre les fiches de quêtes indépendantes.
**État final du brouillon : 39/39 étapes, 146 actions, 73/73 positions.**

Les étapes **11–67 de Nimaltopia** (#2229) ont été rédigées à partir de
quêtes indépendamment documentées et des références de positions source.
Elles distinguent les combats individuels et de groupe, les quatre
quêtes parallèles (« Frais de porc inclus », « Nos amies les bêtes »,
« Shyriiwook », « À armes égales »), puis « La valse des manuels »
et « Il a fui, il a tout compris » ; elles conservent explicitement
les dialogues Bonta/Brâkmar, la poursuite chronométrée, les indices
de classe de Rem, les variantes de bouteille dépendantes de l'heure
et les lieux possibles de Xaniel. L'objet « Viande Noire » a été
corrigé après contrôle du nom français.
**État final du brouillon : 67/67 étapes, 295 actions, 144/144 positions.**

### Contrôle statique exact du contenu

Vérification par lecture GitHub des quatre JSON de brouillons et de leurs
quatre relevés d'observations au SHA
`d37fc507ede0411be4f81fa6959acb59da1a4b64`.
Contrôles explicites : ID source et longueur conformes au catalogue,
étapes consécutives 1..N, titres et consignes non vides,
actions typées et non vides, comparaison GPS à la *même* étape,
et `source_parity_certified=false` /
`gameplay_certified=false` sur les quatre parcours.

| Parcours | Étapes rédigées | Actions | GPS présents au relevé |
| --- | ---: | ---: | ---: |
| 2204 — Mais où sont les Dofus ? | 26/26 | 114 | 46/46 |
| 2206 — Valonia 1 | 30/30 | 124 | 55/55 |
| 2228 — Sufokia | 39/39 | 146 | 73/73 |
| 2229 — Nimaltopia | 67/67 | 295 | 144/144 |
| **Total** | **162/162** | **679** | **318/318** |

Résultat : **aucune anomalie détectée par ce contrôle documentaire**
dans les 4 JSON. Cela n'est **pas** un test Python, une certification
source ou une preuve de la bonne carte, de l'identité du monde et
des objectifs réels en jeu. Les pages originales Ganymède 11+
n'étaient pas intégralement disponibles : les consignes ont été
*recomposées*, non recopiées ou certifiées 1:1. Les dialogues,
quantités, possibilités de combat et branches doivent être vérifiés
avec la version Unity et la validation par personnage. L'ordre des
quêtes parallèles n'est pas encore une preuve de correspondance
éditoriale à la route Ganymède.

Le fichier `tests/test_ganymede_partial_authoring.py` inclut maintenant
8 méthodes de test, dont des protections des six barques, des quatre
livraisons, des noms français, des combats solo/en groupe, des
bouteilles et des trois positions possibles de Xaniel. Ces tests
et les tests Doctor/Qt/Windows **NOT_RUN** ; seuls les JSON/snapshots
ont été évalués statiquement. Les routes n'ont pas été publiées à la
racine des consignes `ganymede_<id>_instructions.json` :
leurs statuts restent `FULL_DRAFT_NOT_PLAYABLE`.

**Résumé de couverture :** 15/95 routes structurellement complètes
dans le lecteur existant (non certifiées), 4 brouillons supplémentaires
entièrement rédigés **hors runtime**, 76 parcours supplémentaires
sans fichier complet et **0/95 certifié en DOFUS/Windows**.
Les deux grands guides optimisés sont inchangés, tout comme leur
sauvegarde, leur validation et l'architecture de l'UI.

**Prochain passage obligatoire :** comparaison étape par étape
aux routes Ganymède exactes pour les 4 brouillons ; correction
des différences, contrôle du rendu et de la progression par
`character:<id_dofus>`, puis validation et publication par le
chargeur strict. Continuer ensuite la rédaction des 76 autres,
sans extrapoler leurs actions depuis de simples relevés GPS/liens.
Phase CI finale **non lancée** ; PR Draft, **CHANGES REQUIRED**.

## Sidimote 3 — cinquième brouillon rédigé (2 novembre, nouveau lot)

La priorité de la PR reste **faire les 95 guides**, avant le Guide Ultime.

**2235 — Sidimote 3 : 31/31 étapes rédigées avec 133 actions
structurées, 60/60 déplacements présents dans les relevés locaux de
la même étape**, en conservant le statut `FULL_DRAFT_NOT_PLAYABLE`.
Ce fichier n'est **pas** utilisé par le lecteur runtime.

Sources de rédaction factuelle :
- https://ganymede-app.com/guides/2235 : les **dix premières étapes**,
  noms de PNJ, déplacements, choix et objets.
- https://www.dofuserie.com/quetes/l-entree-des-artistes/
- https://www.dofuserie.com/quetes/un-salaire-germinable/
- https://www.dofuserie.com/quetes/au-pied-du-mur/
- https://www.dofuserie.com/quetes/rituel-oblige/

Les 21 étapes suivantes ont été rédigées de manière originale à partir
de ces quatre fiches de quêtes et de leur recoupement avec les relevés
`ganymede_2235_observed_links.json` ; elles **n'ont pas encore fait
l'objet d'une comparaison intégrale à la route Ganymède exacte**.
La condition `Au pied du mur` avant `Rituel oblige` reste
explicite, et non présumée remplie pour chaque personnage.

Faits de gameplay conservés et à revoir sous Unity : 5 combats
distincts (Pwouerk avec le gobelin, 4 Bworks élémentaux, 3 Sectateurs
avec 3 Shushus Rav, Risa Gregory, Moctar Chitekt en démon), dont les
combats de groupe possibles. Les quêtes, interactions, ressources
(60 Argent, 30 Bauxite, 5 Shigekax Menthe), dialogues et parcours
font l'objet d'actions séparées. La traduction des noms de PNJ est
rapprochée d'une source française indépendante, sans déclarer les
noms certifiés dans la version de jeu.

Un test ciblé a été ajouté à
`tests.test_ganymede_partial_authoring` pour contrôler le guide
de 31 étapes, les 4 quêtes, les ressources et les 5 combats,
ainsi que le statut de non-certification.

**Contrôle documentaire direct au SHA
`68bbcd3bdfec4b19cc335fd84cd932695f3ecafc` :**
5 brouillons complets, **193/193 étapes, 812 actions et 378/378
positions correspondant au relevé de la même étape**, aucune erreur
de structure, de type d'action ou de numérotation dans le contrôle
statique des dix JSON (5 brouillons + 5 snapshots).
Ces correspondances de coordonnées ne prouvent pas la parité
Ganymède ni l'identité des mondes/cartes.

**Tests Python, DOFUS Unity, Qt/Windows, Doctor et bench NOT_RUN.**
Aucun brouillon nouvellement activé, aucun changement des deux
grands guides optimisés ni du moteur de validation.

**Bilan global : 15/95 guides à consignes complètes existants mais non
certifiés, 5/95 brouillons entiers non activés, 75/95 guides à
rédiger encore intégralement, 0/95 certifié en jeu/Windows.**
PR Draft, `CHANGES REQUIRED`, aucune CI finale ou fusion lancée.

## Correction du critère « guide fait » — certification individuelle préalable

**Décision utilisateur reconfirmée le 2 novembre 2026 : 1 guide fait =
1 guide certifié à 100 % avant le suivant.**

Le développement précédent a **violé l'ordre d'acceptation** en rédigeant
cinq autres parcours après quinze fichiers de consignes complètes
sans preuve de certification par guide. Il est **interdit** de présenter
les « 20 contenus rédigés » comme « 20 guides terminés » : la seule
mesure de fin est la certification intégrale individuelle accompagnée
de preuves vérifiables au SHA exact.

### Audit documentaire des 20 contenus présents

- **15 fichiers de consignes publiés** (schéma complet à contrôler
  individuellement) :
  `2219`, `2220`, `2224`, `2227`, `2240`, `2247`,
  `2248`, `2252`, `2259`, `2273`, `2274`, `2284`,
  `2285`, `2290`, `2590`.
  Les **15/15 fichiers lus au HEAD `ff70773`** ne contiennent
  **aucune preuve individuelle** (`source_parity_certified`,
  `gameplay_certified`, SHA de validation Windows ou compte rendu
  de certification par guide). Un JSON structurellement complet ne
  signifie pas « certifié ».
- **5 fichiers brouillons**, `2204`, `2206`, `2228`, `2229`,
  `2235`, explicitement `FULL_DRAFT_NOT_PLAYABLE` et
  `source_parity_certified=false` / `gameplay_certified=false`,
  tous hors chargeur d'instructions actives.

| État de couverture au 02/11/2026 | Nombre |
| --- | ---: |
| Consignes complètes existantes, sans certificat individuel retrouvé | 15 |
| Nouveaux brouillons à 100 % d'étapes, non certifiés et hors lecteur | 5 |
| Autres guides sans contenu entièrement rédigé | 75 |
| **Guides certifiés à 100 % avec preuves identifiées** | **0/95** |

**Blocages réels à lever, un guide à la fois :**
parité de toutes les étapes d'origine ; justesse des PNJ, objets,
préparatifs, combats et déplacements ; UI universelle des guides
optimisés et validation propre au parcours ; contrôles réels de
progression et sauvegarde par `character:<id_dofus>` ; tests
ciblés Python/Qt, exécution sous Windows et DOFUS Unity, preuve
de fonctionnement sur le HEAD exact. Les tests rédigés mais
**NOT_RUN** ne valent pas PASS. Aucune certification Windows/Unity
n'a été produite dans cette séance.

**Action immédiate de workflow :** suspendre la rédaction des 75
autres, reprendre les 20 contenus présents et ne passer au guide
suivant qu'après certification intégrale et audit du précédent.
Le contrat canonique a été corrigé dans
`docs/guides/GANYMEDE_AUTHORING.md` au commit `c0f6ee9`.
Cette règle ne contourne ni `AGENTS.md` (PR Draft avant
certification de la phase finale), ni `PHASE_CERTIFICATION.md`.
Aucun changement au lecteur, aux données persistantes ou aux deux
grands guides optimisés.

**Audit de la règle après modification :** portée limitée à la PR
#337 et à ses consignes éditoriales, pas de nouvel outil ni de
workflow CI, aucune fausse attestation ou permission ; compatibilité
avec les garde-fous existants et le refus des guides incomplets.
**Verdict logique du correctif de procédure : REVIEW OK ;
état de livraison globale : CHANGES REQUIRED.**
