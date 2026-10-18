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
