# Ganymède first — catalogue de références et futurs guides Atlas originaux

État (2026-10-18) : **premier inventaire de métadonnées et contrôle automatisable uniquement**.
Ce chantier est indépendant du moteur de la PR #226 et ne certifie encore **aucun**
itinéraire ni aucune fiche générée.

## Décision de conception

- **Ganymède = référence principale de l'ordonnancement et de la progression.**
  Le guide complet est un orchestrateur de guides spécialisés : ne pas confondre
  ces deux niveaux, ni concaténer naïvement toutes les fiches externes.
- **Atlas / données Doduda = source de vérité des ID canoniques et états réels.**
  Ne jamais identifier une quête ou un objectif seulement par un titre.
- **DPLN = référence prioritaire du détail des actions et prérequis** ;
  Tougli, JOL, Skyzio et autres = recoupement indépendant et détection des écarts.
- Conserver les guides Atlas actuels : ils ont leurs IDs de progression,
  guides de Dofus, alignements, succès et variantes de classes ; les nouveaux
  itinéraires doivent **réutiliser** ces ID et non créer des sauvegardes parallèles.
- Ne pas reproduire les textes, captures ou le contenu éditorial complet d'un
  service tiers sans permission. Établir un graphe de faits vérifiés et produire
  des fiches de conception et rédaction **originales** dans Atlas ; conserver
  les liens, dates, sources et autorisations.

## Premières références confirmées

Catalogue original : https://ganymede-app.com/tree?view=list

La page publique annonçait **95 guides** au moment de l'inventaire. Les
**95 fiches de métadonnées** publiques (noms, liens, niveaux affichés) sont
maintenant inventoriées dans data/encyclopedia/guides/ganymede_main_index.json.
En revanche, **24 correspondances** avec des guides Atlas (13 liens initiaux et **11 candidats thématiques** sans rapprochement des quêtes)
existants sont établies dans data/encyclopedia/guides/ganymede_source_crosswalk.json.
**Aucun des 95 parcours ni texte d'étape n'est importé ou certifié.**

### Avancement vérifié : graphe public des guides (18/10/2026)

- Les 95 fiches de l'arbre public contiennent désormais un `listed_step_count`
  et la liste `public_tree_prerequisite_guide_ids` (identifiants Ganymède,
  **pas** identifiants de quêtes Atlas).
- **57 liens de prérequis entre guides**, répartis sur **40 guides**, ont été
  rapprochés aux 95 IDs du même arbre. Aucun ID externe orphelin ni cycle
  détecté au moment de cette collecte.
- Traçabilité : `snapshot.public_tree_prerequisite_graph` avec URL, date,
  volume de données et marqueur impératif `SOURCE_METADATA_ONLY`.
- L'audit contrôle : nombre d'étapes positif, existence et unicité des guides
  prérequis, absence de dépendance à soi-même, absence de cycle, cohérence des
  totaux et **interdiction de certifier des itinéraires depuis les métadonnées**.
- Le rapport JSON expose désormais `guide_coverage` pour les 95 entrées,
  `unmapped_guide_ids` (actuellement **71**), et
  `tree_prerequisite_edges` (57) pour piloter l'enrichissement par guide.

Les **11 correspondances thématiques candidates** portent sur Pourpre, Domakuro,
Dorigami, Turquoise, Nébuleux, Abyssal, Vulbis, Tacheté, Dom de Pin,
Cauchemar et Forgelave. Elles rapprochent les identités de guides existants
du catalogue Atlas et les références de l'arbre Ganymède, **sans** comparaison
d'IDs de quêtes/étapes. Le rapport distingue `CANDIDATE_METADATA_ONLY`
de `CROSSWALK_METADATA_ONLY` et `UNMAPPED`. **Sylvestre Opti** reste
un guide Atlas distinct : ne pas le confondre avec le « Sylvan Dofus » de l'arbre.

**Limite importante :** le graphe de l'arbre Ganymède est un graphe de
**prérequis de guides**. Il ne démontre pas les prérequis **de quêtes**,
l'exactitude de chaque étape, les positions ou la pertinence d'un trajet.
L'étape suivante reste l'analyse factuelle des étapes du guide complet
(MG0) et des sous-guides, le rapprochement par IDs canoniques Atlas et le
recoupement DPLN/Tougli/JOL. Aucun guide Atlas n'a encore été remplacé.

Source publique des liens/compteurs :
https://ganymede-app.com/tree?view=list (instantané du 18 octobre 2026).

Exemples : guide complet, Incarnam/Astrub (Argenté), Cawotte, Émeraude,
Dokoko, Dolmanax, Veilleurs, Glaces, Ébène, Ivoire, introduction
Bonta/Brâkmar et guides d'alignement Bonta/Brâkmar. Le site courant utilise
parfois des identifiants et versions localisées (par ex. MG0/GP0) :
conserver l'ID de page exact et éviter de supposer l'équivalence entre éditions.

Commande hors réseau, depuis la racine :

    py -3.13 -m tools.audit_ganymede_crosswalk --output artifacts/guides/ganymede_crosswalk_audit.json

Cette commande vérifie les domaines/IDs d'URL, les doublons et l'existence des
guides Atlas cibles. PASS_METADATA_ONLY **ne signifie PAS** que le contenu,
les prérequis ni l'ordre des étapes de Ganymède sont vérifiés.

## Feuille de route — livrables bloquants

1. **Inventaire complet.** Identifier toutes les entrées du parcours principal
   actuel (titre, langue/version, ID de guide, URL, niveau, prérequis externes,
   guide maître ou sous-guide, date) ; distinguer les guides principaux de la
   communauté et les variantes obsolètes. Générer un rapport de couverture
   24/N puis N/N, pas un faux PASS.
2. **Graphe inter-guides.** Représenter les renvois du guide complet vers les
   guides détaillés : prérequis, tranches d'étapes, étapes optionnelles, ordres,
   alignements et choix mutuellement exclusifs. Détecter les cycles et les
   étapes inaccessibles. Les changements externes ne deviennent pas
   automatiquement des changements certifiés.
3. **Correspondances quêtes/objectifs.** Faire correspondre par **IDs Atlas**
   chaque obligation utile, combat, PNJ, carte, succès, donjon, capture, clé,
   pierre, ressource et jalon de progression. Chaque correspondance a une
   preuve et une confiance ; ambigu/absent => REVIEW. Les faits sont
   revalidés DPLN, Tougli et JOL si nécessaire.
4. **Optimisation globale dans #226.** Comparer des itinéraires qui respectent
   le graphe de dépendances ; prendre toutes les quêtes avant de combattre
   ou d'entrer en donjon, grouper les combats et succès compatibles, limiter
   les passages de zone/PNJ, prévoir les captures et ressources au bon moment,
   et choisir les trajets réellement éligibles. Optimiser par personnage ET
   pour le groupe sans briser leurs dépendances respectives.
5. **Nouveaux parcours thématiques Atlas.** Proposer un guide aventure complet
   et des parcours Dofus, alignements Bonta/Brâkmar, régions, donjons et succès.
   Générer un contenu Atlas ORIGINAL à partir des faits vérifiés, avec
   variantes intégrées aux catégories existantes, références visibles en audit,
   ID de progression uniques et migration testée des sauvegardes.
6. **Preuves de qualité.** Comparatifs reproductibles sur mêmes données
   (route héritée Atlas, route originale Atlas améliorée et jalons Ganymède) :
   couverture d'objectifs, prérequis, allers-retours, donjons, cartes, captures,
   matériaux et temps/RAM de génération. Exiger zéro perte d'objectifs,
   zéro saut de prérequis, tests multi-personnages 0/1/2/5, tests d'intégration
   UI #225 et Organizer #227, Doctor/Graphify/Windows, FULL vert au SHA final.

Le rapprochement des métadonnées appartient à cette PR indépendante ; la
génération V2 et la validation bout en bout restent dans **#226**.
Ne pas fusionner ce registre avec une promesse implicite de guides terminés.


## Graphe de renvois du guide maître Ganymède MG0 — données observées

Le guide complet public `https://ganymede-app.com/guides/2251` a été lu
sur **4 pages** de 50 étapes (dernière page : 6). Son index contient **156
étapes numérotées, sans trou**. Le fichier
`data/encyclopedia/guides/ganymede_master_observed_links.json` enregistre
uniquement des faits structurés observables, sans reproduire la rédaction :

- étape source, page de provenance, IDs des autres guides liés ;
- IDs de liens DOFUSDB identifiés par type (quête/donjon/objet/monstre) ;
- coordonnées mentionnées comme **données non interprétées**, pas comme
  commandes Travel ni positions certifiées d'actions.

Mesures de cet instantané : **234 occurrences de liens de guides**, **91
guides liés distincts**, dont **89 dans l'arbre principal** ; les IDs
**3238** et **3768** sont des liens hors de ses 95 entrées et restent à
qualifier. Le guide contient également **84 occurrences d'IDs de quêtes**,
**123 donjons**, **359 objets**, **110 monstres** et **81 mentions de
coordonnées**. Les comptages sont par étape après déduplication **dans
chaque étape**, pas des objectifs de jeu uniques.

Audit dédié :

    py -3.13 -m tools.audit_ganymede_master_refs --output artifacts/guides/ganymede_master_refs_audit.json

La vérification impose : couverture 1→156, ordre et pagination exacts,
références numériques valides, absence de duplications au sein d'une étape,
totaux cohérents, et traçabilité des IDs hors index. Le statut positif
`PASS_OBSERVED_LINKS_ONLY` **ne certifie ni prérequis de quête ni
itinéraire**. Les liens peuvent correspondre à des conseils, exemples,
options, étapes futures ou contenus requis : aucun automatisme ne les
transforme en actions obligatoires avant analyse sémantique contrôlée.
DofusDB n'est pas traité comme preuve que son ID est identique à l'ID
canonique Atlas : le rapprochement reste à effectuer et vérifier.

**Prochain verrou de #229** : qualifier chaque liaison du guide maître
(obligatoire / optionnelle / information), extraire les intervalles
d'étapes des sous-guides et rattacher les actions aux véritables
`quest_id` / `objective_id` d'Atlas, avec provenance et validation DPLN.
Le moteur #226 ne doit pas optimiser sur des liens encore non qualifiés.


## Premiers sous-guides détaillés — couverture source 13 / 95

Trois sous-guides prioritaires ont été parcourus sur les pages publiques du
18 octobre 2026, en complément du guide complet MG0 :

| Guide source | ID Ganymède | Étapes publiques | Fichier instantané |
| --- | ---: | ---: | --- |
| Guide complet MG0 | 2251 | 156 | `ganymede_master_observed_links.json` |
| Dofus Argenté | 2203 | 237 | `ganymede_argente_observed_links.json` |
| Dofus Cawotte | 2205 | 64 | `ganymede_cawotte_observed_links.json` |
| Dofus Émeraude | 2211 | 52 | `ganymede_emeraude_observed_links.json` |

Premier lot : **509 étapes sur 4 guides**. Au total, **1 103 étapes sur 13 / 95 guides** documentés
au niveau des liens factuels. Les titres d'étapes pouvant comporter des
coordonnées, l'inventaire prend en compte **les coordonnées du titre ET du
corps**, avec déduplication sur une même étape.

La commande d'audit s'applique à chaque fichier via `--snapshot` :

    py -3.13 -m tools.audit_ganymede_master_refs --snapshot data/encyclopedia/guides/ganymede_argente_observed_links.json

`tools.audit_ganymede_crosswalk` agrège désormais automatiquement les
fichiers nommés `ganymede_*_observed_links.json` et indique pour
chacun des 95 guides `OBSERVED_UNCLASSIFIED` ou `NOT_INGESTED`,
avec un total `observed_source_steps`. Une source incohérente bloque
l'audit global. **Il ne reste pas « 91 guides terminés » : il reste
82 / 95 guides non inventoriés à ce niveau de détail.**

Ces liens sont des observations non interprétées. L'analyse des quêtes
avec DPLN/Tougli/JOL, les véritables `quest_id` et `objective_id`
d'Atlas, les intervalles de sous-guides, les consommables exacts et
l'optimisation de route restent à réaliser.


### Deuxième lot — cinq autres guides collectés

| Guide public | ID Ganymède | Étapes |
| --- | ---: | ---: |
| Dolmanax | 2248 | 9 |
| Où sont les Dofus ? | 2204 | 26 |
| Dokoko | 2208 | 49 |
| Dofus Pourpre | 2276 | 45 |
| Dofus des Veilleurs | 2209 | 88 |

Les 217 étapes de ce deuxième lot complètent les 509 du premier.
Toutes sont numérotées et rattachées à leur guide/page source. Le
rapprochement des **quêtes et objectifs canoniques Atlas n'est pas encore
fait** et aucun trajet généré ne peut utiliser ces liens comme consignes
certifiées.

### Collecteur HTML contrôlé pour la suite

`tools.ganymede_source_link_ingest` est le collecteur reproductible.
Il utilise exclusivement les articles d'étapes des pages publiques et
ne sauvegarde **ni rédaction, ni HTML, ni illustration externe**. Il
conserve les ID de liens et les coordonnées mentionnées, sans les
transformer en objectifs ou en commandes.

Exemple, sans écriture :

    py -3.13 -m tools.ganymede_source_link_ingest --guide-id 2248 --fetch --checked-on 2026-10-18

Pour créer explicitement un instantané vérifié après contrôle :

    py -3.13 -m tools.ganymede_source_link_ingest --guide-id 2248 --fetch --checked-on 2026-10-18 --apply

Pour travailler sans réseau, remplacer `--fetch` par
`--html-dir <dossier>` (fichiers locaux `2248-1.html`, etc.).
Les téléchargements échoués, pages renvoyant un autre numéro,
pagination tronquée ou guide absent de l'index interrompent la
collecte **avant toute modification du JSON final**. À ce stade,
l'outil prend volontairement **un seul guide explicite à la fois** ;
pas de parcours silencieux des 95 pages source, ni de modification
de la progression Atlas.

Les instantanés déjà présents restent la source versionnée utilisée
par Doctor ; aucune récupération réseau au démarrage d'Atlas.


### Troisième lot — quatre guides prioritaires supplémentaires

| Guide public | ID Ganymède | Étapes |
| --- | ---: | ---: |
| Krosmoz | 2230 | 51 |
| Dofus Turquoise | 2217 | 87 |
| Dofus Ivoire | 2256 | 118 |
| Frigost 3 / Dofus des Glaces | 2216 | 121 |

Cette vague ajoute **377 étapes**, portant la couverture des liens
factuels à **13 guides / 1 103 étapes**. Restent **82 guides
sans inventaire détaillé**. L'index général reste à 95 références et
les correspondances guide→Atlas à 24 (dont 11 candidates) : ces nombres
mesurent des opérations différentes et ne doivent jamais être additionnés.

Les sources sont des pages publiques d'octobre 2026 ; les instantanés
conservent leur URL et date. La correspondance vers les IDs de quêtes
et d'objectifs Atlas, le statut des actions obligatoires, les besoins
et la route générée ne sont **pas certifiés**.

### Quatrième lot — premiers parcours de progression (18/10/2026)

Six guides d'aventure supplémentaires sont inventoriés : **Campements Bwork/Gobelins** (34), **Otomaï 1** (7), **Sufokia** (39), **Valonia 1** (30), **Sidimote 1** (25) et **Koalaks** (9). Soit **144 étapes** supplémentaires.

**Couverture cumulée : 19/95 guides, 1247 étapes de liens factuels**, 76 guides restant sans instantané d'étapes. Ce n'est ni une reprise des textes Ganymède, ni la preuve d'une équivalence avec les ID de quêtes Atlas ; génération et optimisation restent bloquées tant que les liens ne sont pas qualifiés et recoupés.


### Rapprochement des IDs de quêtes — audit préliminaire

Le nouvel outil `tools.audit_ganymede_quest_candidates` compare, guide par
guide, les IDs de quêtes cités dans les liens DOFUSDB publics à ceux des
étapes `type=quest` des guides Atlas actuellement versionnés.

    py -3.13 -m tools.audit_ganymede_quest_candidates --output artifacts/guides/ganymede_quest_candidates.json

Il fournit pour chaque guide : les IDs externes observés et les numéros
d'étapes où ils apparaissent, les IDs de quêtes présents dans ses guides
Atlas associés, les intersections numériques, les références citées
seulement par la source et celles présentes seulement dans Atlas.

**Un identifiant numérique identique ne prouve pas encore une identité
de quête vérifiée** : l'intersection est étiquetée
`REVIEW_NUMERIC_ID_ONLY`, avec
`quest_identity_confirmed=false` et
`required_objective_confirmed=false`. Les références absentes du guide
Atlas local ne sont pas présumées absentes du catalogue global Doduda.
Les renvois Ganymède non rapprochés à un guide Atlas sont distingués
par `GUIDE_UNMAPPED`. Aucune donnée n'est écrite dans les guides,
aucune progression n'est modifiée et aucun prérequis/itinéraire n'est
déduit de ces liens.

La **prochaine validation** doit relier les candidats aux fiches de
quête canoniques Atlas/Doduda et vérifier nom, version et objectifs
contre DPLN et si besoin Tougli/JOL. En cas de divergence :
`REVIEW` ou `BLOCKED`, sans basculer la nouvelle route #226.


### Cinquième lot — premières dimensions, Île d'Otomaï et Ecaflipus

Cinq guides supplémentaires ont leurs étapes et références structurées :
**Enudorado 1** (29), **Ecaflipus 1** (48), **Otomaï 2** (7),
**Xélorium 1** (27) et **Otomaï 3** (13).

Le total passe à **24 guides sur 95**, pour **1 371 étapes sources
inventoriées**. **71 guides** restent à inventorier. La vérification
des correspondances de quêtes (nouvel audit) conserve tous ses résultats
au statut `REVIEW_NUMERIC_ID_ONLY` tant que les données canoniques et
les détails DPLN n'ont pas été recoupés. Aucun nouvel itinéraire Atlas
n'est activé.


### Premier rapprochement indépendant : Dofus Cawotte

Recoupement effectué le 18 octobre 2026 sur les 11 quêtes principales du
[Dofus Cawotte selon DPLN](https://www.dofuspourlesnoobs.com/dofus-cawotte.html).

- **11/11 quêtes nommées** ont été rapprochées par leurs IDs de quêtes dans
  DofusDB, par leur apparition dans les 64 étapes du guide Ganymède 2205,
  et par leur présence dans les étapes du guide Atlas `dofus_cawotte`.
- Les huit quêtes du succès « Rusé comme une Lenalde » correspondent aux
  IDs 836 à 843 ; les trois du succès « Un Wa de pacotille » aux IDs
  833 à 835. C'est une correspondance **nom + ID candidat** et non la
  certification d'un ordre d'exécution ou des objectifs de ces quêtes.
- Les quêtes 2193 (Un sage parmi les sages, prérequis) et 827
  (Intrusion chez les wabbits, accès à l'île) sont distinguées des
  **11 quêtes principales**.
- Les références des deux donjons, des trois équipements du Wa et des
  ressources DPLN sont conservées dans
  `ganymede_dpln_cawotte_evidence.json` comme besoins de source,
  **pas** comme courses immédiates de « À préparer ». Leur planification
  dépendra de l'itinéraire et du nombre de personnages.
- Atlas contient 39 étapes sur ce guide, avec des alternatives et du
  contexte supplémentaire. Ce total ne peut être comparé directement
  aux 11 quêtes du cœur du parcours ni aux 64 étapes éditoriales de Ganymède.

L'audit `tools.audit_ganymede_quest_candidates` utilise automatiquement
ces preuves et les distingue des autres intersections numériques sous le
statut `REVIEW_TRIANGULATED_SOURCES`. Une source manquante, un ID absent
du guide Atlas/Ganymède ou une prétention de certification erronée font
échouer le contrôle. Les compteurs `certified_quest_mappings` et
`certified_quest_objectives` restent à **0**.

Étape encore requise pour l'exploitation par #226 : associer chaque
quête à ses véritables objectifs Atlas/Doduda, leurs prérequis réels,
les consommables utiles et leur étape d'acquisition, puis vérifier les
branches facultatives et les déplacements multi-personnages.


### Deuxième rapprochement indépendant : Dolmanax

Les données publiques **DPLN / DofusDB / Ganymède / Atlas** concordent sur
la quête **L'année du dragon**, ID 954. Le guide Atlas Dolmanax contient
une étape de quête ID 954, citée dans l'étape source 2 de Ganymède 2248.

La particularité du Dolmanax est documentée dans
`ganymede_dpln_dolmanax_evidence.json` avec provenance et contraintes
temporelles : **365 pages de calendrier**, au maximum **une offrande par jour**.
Son statut de planification est
`NON_BLOCKING_LONG_TERM_GOAL` : ne pas forcer 365 jours d'attente
avant les autres guides, ne pas acheter automatiquement 365 offrandes
sans calendrier, et suivre l'avancement **par personnage**.

L'audit produit désormais **12 correspondances de noms/IDs recoupées**
sur Cawotte et Dolmanax, toutes au statut
`REVIEW_TRIANGULATED_SOURCES`. Il valide la forme des informations
temporelles mais ne valide pas encore les objectifs précis ni le trajet.
Le moteur #226 devra tenir compte de la limite journalière et du
calendrier réel ; il ne doit pas déduire un nombre de jours restant
depuis cette seule donnée.

Références : [quête](https://www.dofuspourlesnoobs.com/lanneacutee-du-dragon.html),
[calendrier](https://www.dofuspourlesnoobs.com/calendrier-de-lalmanax.html),
[DofusDB quête 954](https://dofusdb.fr/fr/database/quest/954).

### Sixième lot — neuf guides courts (18/10/2026)

Inventaire des étapes factuelles et des liens sur les guides Ganymède : Sylvan Dofus (ID 2290, 2 étapes), Pine Done (2285, 4), Cloudy/Nébuleux (2247, 6), Argenté scintillant (2273, 15), Al Howin (2590, 16), Secret of the Dofus : Prologue (2284, 21), Sidimote 5 (2259, 25), Albatrocious Rock (2274, 26) et Srambad 1 (2244, 29).

**Couverture : 33/95 guides, 1 515 étapes observées, 62 guides encore sans instantané d'étapes.** Les fichiers `ganymede_<ID>_observed_links.json` sont datés, validés sur le compteur d'étapes et non certifiés comme trajets. **Sylvan Dofus n'est pas le guide Atlas « Sylvestre Opti »** : aucune équivalence ne doit être déduite de la ressemblance de leurs noms.

### Septième lot — neuf guides (18/10/2026)

Servitude (2278, 29 étapes), Amber Ochre (2214, 30), Sidimote 3 (2235, 31), Valonia 2 (2265, 32), Destroyed (2282, 32), Dofus Ocre (2218, 33), Ecaflipus 3 (2258, 39), Corruption (2280, 40) et Crocuzko (2264, 40). **9 nouveaux guides / 306 étapes**, pour 42 guides et 1 821 étapes cumulées.

### Huitième lot — huit guides (18/10/2026)

Atoll of the Possessed (2291, 41), Evil Forest (2255, 43), Misery (2279, 43), Cania 2 (2232, 44), Vigilantes (2236, 45), Vulbis Dofus (2260, 47), Enudorado 2 (2238, 50), Sidimote 4 (2254, 52). **8 nouveaux guides / 365 étapes**, pour **50 guides sur 95, 2 186 étapes observées**, **45 guides sans instantané détaillé**. Les 52 étapes de Sidimote 4 ont été vérifiées sur deux pages sans trou. Les instantanés ne contiennent ni textes éditoriaux ni statut de quête certifié. L'audit des 12 correspondances nommées Cawotte/Dolmanax demeure distinct de ces observations.

### Neuvième lot — huit guides avec pagination (18/10/2026)

**Tous les guides suivants ont été parcourus sur deux pages, avec vérification continue de la numérotation :** War (2277, 53 étapes), Sidimote 2 (2225, 54), Bonta / Brakmar *introduction* (2226, 54), Future Fantastic (2275, 54), Dofus du Cauchemar (2283, 55), Six sur Six (2272, 56), Pandala 2 (2253, 59) et Cania 1 (2223, 60).

**Couverture cumulée : 58/95 guides et 2 631 étapes de références**, 37 guides restant à inventorier en détail. Bonta/Brakmar 2226 est l'introduction et **ne remplace pas** les parcours d'alignement complets 2249 (774 étapes) et 2263 (696 étapes), qui nécessiteront leur propre couverture. Tous les nouveaux instantanés restent `OBSERVED_UNCLASSIFIED` ; les étapes et prérequis Atlas ne sont pas encore certifiés.

### Dixième lot — huit autres guides sur deux pages (18/10/2026)

Xélorium 2 (2241, 61), Dofus Tacheté (2271, 62), Dorigami (2221, 64), Royaume d'Amakna (2231, 65), Aube Pourpre / Crimson Dawn (2286, 65), Enudorado 3 (2239, 65), Nimaltopia (2229, 67) et Fleaster (2595, 67). **8 guides, 516 étapes**, chacune rattachée à la page et au numéro source.

La couverture factuelle atteint **66/95 guides, 3 147 étapes observées**, avec **29 guides restant à parcourir en détail**. Les autres travaux (qualification des 12 noms de quêtes Cawotte/Dolmanax, prérequis, ID/objectifs canoniques Atlas, vérification DPLN et génération #226) demeurent des verrous indépendants. Ne pas convertir ces observations en ordre de trajet ni déduire leur caractère obligatoire.

### Onzième lot — 17 guides de progression (18/10/2026)

Toutes les étapes des guides suivants ont été relevées sur deux ou trois pages avec contrôle de continuité : After the Rain (2281, 69), Srambad 2 (2245, 71), Ohwymi 3 (2266, 71), Kingdom of Freezammer (2292, 72), Srambad 3 (2246, 73), Xélorium 3 (2243, 73), Ohwymi 2 (2222, 74), Ohwymi 1 (2210, 76), Cania 3 (2262, 79), Valonia 3 (2288, 79), Brotherhood of the Forgotten (2233, 87), Ecaflipus 2 (2257, 91), Osavora (3738, 97), Frigost 2 (2215, 101), Eliocalypse: Resonance (2268, 101), Kwismas (3795, 103) et Tree Hiding the Forest (2289, 112).

**1 429 étapes observées supplémentaires, couverture cumulée 83/95 guides et 4 576 étapes**, restant 12 guides sources à inventorier. Le guide Eliocalypse a été relu entièrement après une limite de requêtes sur l'une de ses pages ; aucun instantané tronqué n'a été enregistré. Les grandes séries restantes comprennent notamment les alignements complets Bonta et Brâkmar. Aucune de ces observations n'est une validation de parcours ni un remplacement des guides Atlas.

### Onzième lot — Vulkania (18/10/2026)

Vulkania, guide source Ganymède 3737, a été parcouru sur **3 pages** avec **113 étapes numérotées sans trou**, liens factuels et mentions de coordonnées conservés sans rédaction externe. **Couverture cumulée : 84 guides sur 95, 4 689 étapes observées ; 11 guides restant sans instantané détaillé**. Domakuro et Pandala 3 n'ont pas été intégrés lors de cette collecte : consultation limitée ou première page vide. Aucun prérequis ni objectif Atlas n'est certifié par le simple référencement.

### Douzième lot — Domakuro (18/10/2026)

Le guide source Domakuro 2212 a été observé en entier : **120 étapes continues** sur **trois pages**. Liens publics et mentions de coordonnées sont archivés comme faits non classifiés, sans texte éditorial. **85 guides sur 95, 4 809 étapes observées, 10 guides non détaillés**. Les consultations d'Ébène et Forgelave ont été limitées ; aucun instantané partiel n'a été ajouté. Aucun objectif Atlas n'est certifié.

### Treizième lot — Dofus Ébène (18/10/2026)

Ganymède guide **2261 / Ébène : 142 étapes** publiques successives sur 3 pages. Fichier de références factuelles, aucune reproduction éditoriale et zéro certification d'objectif/route. Le lot porte l'inventaire à **86/95 guides / 4 951 étapes**, 9 guides restant à inventorier. Forgelave reste non détaillé : la consultation de sa deuxième page a été bloquée, et aucun instantané incomplet n'a été enregistré.

### Quatorzième lot — Abyssal et Frigost 1 (18/10/2026)

Le guide Ganymède **Dofus Abyssal 2269** est collecté sur 4 pages, **174 étapes** numérotées sans trou ; **Frigost 1 2213**, également sur 4 pages, **181 étapes**. Deux nouveaux instantanés de références factuelles non interprétées. **88/95 guides, 5 306 étapes** de liens sources observés, **7 guides non détaillés**. Le simple référencement d'une quête ne justifie ni son caractère obligatoire, ni ses prérequis, ni l'ordre du parcours ; la certification Atlas/DPLN reste distincte.

### Quinzième lot — Quatre sur cinq (18/10/2026)

Le guide Ganymède 2270 « Four Over Five » est observé sur **trois pages, 141 étapes** sans lacune. **89/95 guides, 5 447 étapes** de références factuelles ; **six guides** restent à détailler. Pandala 3 n'a pas été ajouté : la troisième page de source a été bloquée à la consultation, aucune donnée partielle n'étant considérée suffisante. Zéro itinéraire ou objectif Atlas certifié depuis ces simples liens.

### Seizième lot — Pandala 1 (18/10/2026)

Le guide public Ganymède **Pandala 1 / ID 2234** est documenté sur **5 pages, 212 étapes** numérotées sans trou. Couverture cumulée : **90 des 95 guides**, **5 659 étapes** de références observées, **5 guides** sans instantané : Pandala 3, Forgelave, Frigost complémentaire et les deux alignements Bonta/Brâkmar. Les descriptions externes ne sont pas importées et les actions ne sont pas classifiées comme objectives de quête certifiées.

### Collecte des 95 guides terminée au niveau des références publiques — 18/10/2026

Le corpus de références structurées couvre **95/95 guides, 7 705/7 705 étapes numérotées**. Le travail déjà intégré en parallèle a apporté Vulkania (113), Domakuro (120), Ébène (142), Abyssal (174), Frigost 1 (181) et Quatre sur cinq (141). Le dernier lot contient Forgelave (150), Pandala 3 (138), Pandala 1 (212), Frigost complémentaire (288), **Alignement Bonta complet (774)** et **Alignement Brâkmar complet (696)**. Les deux alignements sont distincts du guide d'introduction Bonta/Brâkmar ID 2226.

Les gros guides ont été lus avec `stepsPerPage=250` ; l'outil de collecte supporte désormais explicitement `--steps-per-page 250` (50 par défaut) et ses tests couvrent ce choix. Chaque instantané contient uniquement les identifiants de liens, les coordonnées mentionnées, la provenance page/étape et la date, **jamais les textes éditoriaux ni des actions automatiquement obligatoires**.

L'audit de couverture doit confirmer **95 sources et 7 705 étapes** au SHA final. Les contrôles d'identité des quêtes, d'objectifs, de prérequis, de branchement Bonta/Brâkmar et de ressources par personnage restent à réaliser avec Atlas/Doduda, DPLN et les sources croisées. Les **12 rapprochements nom/ID** Cawotte/Dolmanax restent en revue. Le planificateur #226 et la nouvelle interface #225 ne doivent pas consommer ces références comme des parcours certifiés. Garder la PR #229 en brouillon avant validation FULL.


### Rapprochement avec les véritables données Doduda — outil CLI indépendant

Le nouvel audit **`tools.audit_ganymede_doduda_ids`** parcourt les 95
instantanés de références de quêtes et confronte chaque **ID numérique**
à la table `RefIds` de `quests.json` issue de **l'installation canonique
Doduda d'Atlas**. Il réutilise `QuestSources` et ses index sur disque avec
répertoire temporaire libéré à la fin : pas d'importation des 72 Mo
d'enrichissements dans la mémoire principale et aucune modification
des quêtes, guides ni sauvegardes.

Sur une installation disposant des données runtime :

    python -m tools.audit_ganymede_doduda_ids --raw-quests CHEMIN/quests.json --output artifacts/guides/doduda_id_review.json

Résultats strictement différenciés :

- `PASS_RAW_ID_EXISTENCE_ONLY` : les numéros cités sont présents parmi
  les `RefIds` canoniques ; **cela ne confirme aucun nom, aucune étape ni
  aucun objectif**.
- `REVIEW_RAW_ID_GAPS` : des références externes ne figurent pas dans
  la version installée de Doduda ; investigation de version/correspondance
  nécessaire.
- `BLOCKED_CANONICAL_SOURCE_UNAVAILABLE` : `quests.json` manque, donc
  **aucune absence de quête n'est déduite** (code de sortie 2).
- `FAIL` : index/snapshot invalide ou source canonique corrompue.

Le dépôt source ne distribue pas `data/cache/dofus_maps/raw/doduda_cli/quests.json` ;
une CI sans installation runtime ne peut **pas** déclarer le recoupement
avec les données du jeu effectué. Les 7 tests utilisent une petite source
Doduda factice pour prouver le classement, l'absence de fausse
certification et le comportement en cas de fichier manquant.

**Prochaine couche** : noms localisés via `languages/fr.json`, objectifs
réels depuis `quest_steps.json` / `quest_objectives.json`, critères de
lancement, branches OR, nombre de personnages, ressources et combats.
Sans ces preuves, #226 ne doit pas réordonner les étapes.

### Troisième rapprochement nominatif : Dokoko (5 quêtes)

DPLN cite les cinq quêtes du succès **Koko Boy** ;
DofusDB fournit les IDs 1666 à 1670. Les cinq références apparaissent
également dans le guide Ganymède 2208 et dans les 5 quêtes du
guide Atlas `dokoko`.

Le nouvel inventaire `ganymede_dpln_dokoko_evidence.json` associe
ces cinq noms et URLs à **`REVIEW_TRIANGULATED_SOURCES`** sans certifier
les actions. Il conserve explicitement la variante de nom de l'ID
1669 : DPLN « Squelettes et amulettes » / DofusDB
« Squelettes et amulette » ; la version localisée Doduda reste à contrôler.
Les préparations DPLN (1 Casque, 1 Ailes en bois, donjons Village
Kanniboul / Bateau du Chouque / Arbre de Moon, combats) sont listées
comme besoins de source **et non comme achats ou combats à programmer
sans contrôle**.

Cela porte à **17** le nombre de références nominatives recoupées :
11 Cawotte, 1 Dolmanax, 5 Dokoko ; zéro objectif ni itinéraire certifié.

Références : [quêtes du Dokoko](https://www.dofuspourlesnoobs.com/quecirctes-du-dokoko.html),
[succès Koko Boy](https://www.dofuspourlesnoobs.com/koko-boy.html),
[guide public Ganymède 2208](https://ganymede-app.com/guides/2208).


### Quatrième rapprochement nominatif : Dofus Émeraude (8 quêtes)

DPLN liste **huit quêtes** du succès « Vert émeraude ».
Les IDs DofusDB **1463, 1464, 1465, 1466, 1467, 1469, 1470, 1471**
ont été recoupés par nom et numéro avec les 52 étapes Ganymède 2211
et le guide Atlas `dofus_emeraude`. Les huit quêtes figurent dans
les deux collections d'IDs ; le guide Atlas demeure « partial »
car il inclut d'autres contextes et alternatives.

Le fichier `ganymede_dpln_emeraude_evidence.json` conserve séparément
les **ressources**, **dragodindes**, **donjon**, **captures d'âmes**,
**succès préalables**, **métiers** et les classes de combats
(**7 en groupe**, **1 tactique seul**, **4 seuls**, autres aléatoires)
indiquées dans le récapitulatif de DPLN. Les prérequis du succès
« Mais où sont les Dofus ? » restent à développer en quêtes
canoniques vérifiées.

Ces informations de source ne sont pas une liste d'achats, ne
valident pas les objectifs et ne prennent pas encore en charge les
quantités par personnage. Le futur #226 devra dédupliquer et
positionner les préparations au bon moment avant l'UI #225.

Cela porte à **25 correspondances de noms/IDs recensées** :
11 Cawotte, 1 Dolmanax, 5 Dokoko et 8 Émeraude,
**aucun objectif ni route certifié**.

Sources : [Dofus Émeraude DPLN](https://www.dofuspourlesnoobs.com/dofus-emeraude.html),
[Vert émeraude](https://www.dofuspourlesnoobs.com/vert-eacutemeraude.html),
[guide Ganymède 2211](https://ganymede-app.com/guides/2211).
