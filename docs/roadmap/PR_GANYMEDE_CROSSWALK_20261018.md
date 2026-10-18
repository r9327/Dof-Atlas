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
