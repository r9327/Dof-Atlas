# PR Guide Tools — Guide Opti V2 : planificateur intégral

## Pont concret Ganymède 20 guides → #226 → #225 (19/10/2026)

Le service `guide_ganymede_continuous_plan.project_ganymede_continuous_plan`
charge **uniquement** les cutovers Dofus signés par #229 (`replacement_drafts/cutovers/`),
vérifie le manifeste et son SHA-256, puis joint le rapport `audit_ganymede_stage_needs`
par `source_guide_id + stable_step_id + source_action_index + source_label`.
Il conserve **toutes** les étapes, même celles sans proposition de préparation.
Vérifications de données visées : **20 guides / 1 694 étapes / 6 166 actions
sources**, avec ordre initial immuable. Refus d'une divergence de libellé,
d'objet, de quête, de monstre, de donjon ou de guide à ID connu.

Sortie par fiche : `id`, `source_step_number`, `source_page`, titre exact
et `short_title` sans préfixe numéroté, positions observées **non exécutables**,
`action_rows` avec classe de proposition, identités externes typées et statut
facultatif, `preparation_rows` par personnage (stock explicitement connu ou
inconnu, quantités indicatives), `pending_character_keys` et
`manually_completed_character_keys`. `actual_step_id` est la première fiche
inachevée par **au moins un** personnage sélectionné. Aucune ancienne
progression importée ; les coches source restent manuelles. Les 15 liens
prédécesseurs de l'arbre Ganymède ne sont pas des quêtes automatiquement
validées ; les 9 renvois non confirmés sont de la navigation uniquement.

Les libellés français localisés restent un overlay facultatif attesté par
`resolve_ganymede_action_labels` : le texte source n'est jamais modifié.
Les 6 récompenses Dofus qui figuraient en introductions ne sont jamais
classées comme objets à acheter. Les prises en route conservent leur caractère
conditionnel et ne sont pas comptabilisées comme achats obligatoires.

**Frontière d'intégration :** ce pont fournit le parcours **source en suivi
manuel** à l'UI #225, pas une simulation attestée des quêtes. La navigation
réseau/Organizer, la certitude des objectifs et les trajets exécutables exigent
les preuves séparées des services correspondants ; `verified_travel_plan=None`
est intentionnel en absence d'une preuve de transport par personnage. Les
optimisations du planificateur canonique restent appliquées uniquement à ses
`RouteAction` réels. Ne pas inventer des transformations depuis les liens
Ganymède vers des `RouteAction` vérifiés.

Tests ajoutés : `tests.test_guide_ganymede_continuous_plan` (20 parcours,
1 694/6 166, chargement signé, progression 0/1/2/5, préparation individuelle,
ID source et navigation), `tests.test_guide_route_naming` et
`tests.test_guide_route_planner` (pas de Zaap inutile). **Ne pas déclarer
CERTIFIED avant l'exécution de la CI finale sur le SHA figé.**


Date : 18 octobre 2026. Base : main SHA 6a52522d1bd7e501a5c3b4d6d58253bfec755fdc.
Statut : **socle moteur implémenté et testé de façon ciblée ; certification CI exacte encore requise**. La route réelle complète dépend toujours des données locales vérifiées et ne doit pas être déclarée certifiée depuis les seuls tests unitaires.

## Implémentation livrée dans cette PR
- `GuideRoutePlanner` compose le moteur canonique `AdventureRouteEngine` sans créer de second générateur. Il calcule une route indépendante pour chaque identité `character:<id>`, puis groupe uniquement les actions que chaque participant doit encore faire.
- Les besoins de préparation et de pierres d'âme restent ventilés par personnage, avec quantité requise, stock connu et reste à acquérir. Les captures `soul_stone`, `zone_special` et `drop` sont des contrats explicites ; aucun mot présent dans un titre ne suffit à inférer une pierre.
- `GuideTravelPlan` expose `direct` et `zaap_then_travel`. Un Zaap exige destination exacte, monde connu, preuve, et éligibilité explicite de tous les participants ; sinon le moteur revient au trajet direct ou bloque si la destination est inconnue.
- Les succès incompatibles sont distribués en passages déterministes. Les actions bloquées et transports incomplets restent des constats auditables.
- Le nommage partagé conserve les noms officiels et remonte en REVIEW les longueurs ou doublons ambigus, sans troncature silencieuse.
- Le builder GPS V5 exporte titres, contrat de titre et gabarit de trajet direct. Le gabarit statique ne contient volontairement aucun faux participant : les identités doivent être liées au runtime par l'Organizer.

Validation locale ciblée : `tests.test_guide_route_planner`, `tests.test_guide_route_naming` et `tests.test_guide_ultime_v5_or_runtime`. Cette validation ne remplace ni les scénarios avec le jeu et ses données matérialisées, ni `Public PR / Safe Validation`, ni `Phase Certification / Full Validation` sur le SHA candidat exact.

## Mission
Produire un parcours COMPLET et cohérent (Quêtes / Succès / Guide Lanyel / Guide Succès), non une succession de lignes isolées, en minimisant les passages de zone, déplacements, retours PNJ et donjons, sans franchir un prérequis, perdre une étape ou contredire une quête. L'affichage garde les décisions de la PR UI.

## Entrées canoniques
- Données locales DOFUS / Doduda, quêtes-objectifs par ID, succès, bestiaire, drops, captures, donjons, métiers, ressources, maps, Zaaps accessibles.
- Guides DPLN (priorité), Tougli et JOL pour contrôle croisé : ordre dialogues, PNJ, positions, prérequis, situations spéciales. Conserver liens/provenance, version, degré de confiance dans la donnée interne ; ne pas recopier les sites en intégralité. Divergences => REVIEW, jamais faux fait positif.
- Sources existantes : `tools/build_guide_ultime_gps_route.py`, `tools/guide_action_model.py`, `tools/guide_action_normalizer.py`, `tools/guide_action_contract.py`, `app/modules/encyclopedia/services/guide_ultime_manual_route.py`, `guide_auto_validation_contract.py`. Une seule source de vérité ; ne pas dupliquer les générateurs.

## Planification structurée
1. Inventaire intégral des nœuds / actions : quête et objectif ID exact, PNJ, carte/coordonnées/monde, métier/niveau, item/quantité/type d'acquisition, mob ID, boss, donjon, succès, capture, interlocuteur et retour.
2. Graphe de dépendances explicite : quête commencée/active/terminée, prérequis et critères stricts, branches d'alignement/classe/ordre, niveau, ressources à acquérir naturellement, dangers. Bloquage si preuve insuffisante (pas de prise en charge abusive d'un événement `actif` comme `terminé`).
3. Regrouper par zone/carte et phase : activer les quêtes avant le même combat ; cumuler les objectifs compatibles et drops, quantités exactes, conditions et limites ; planifier les rencontres de PNJ sur une seule carte ; prévoir les retours obligatoires.
4. Donjons : rassembler les quêtes à activer AVANT entrée, boss à capturer, succès compatibles/incompatibles, clés, captures après boss, quêtes à valider avant de quitter ; distinguer un passage inévitable supplémentaire.
5. Captures : boss / archimonstres, puissance de pierre, éligibilité réelle DOFUS 3.7, nombre requis par personnage, stock saisi par l'utilisateur, stock déjà acquis, déjà capturé, besoins restants `50/150 => 100` ; les objectifs de zone et drops ne créent PAS faussement une obligation de pierre d'âme.
6. Préparation : liste globale dédupliquée ; acquisition naturelle vs achat/récolte, évite l'achat abusif de drops exclusifs de quête et les préparations devenues inutiles.
7. Zaap / Travel : chaque position cliquable garde exactement son rendu texte, mais porte en DONNÉES un plan typé `direct` ou `zaap_then_travel` avec coordonnées Zaap et cible ; optimiser depuis position estimée fiable, mondes/conditions, coût/détour ; si incertitude, pas de téléportation hasardeuse. Format supporté DOFUS 3.7 : `/travel x,y` ou `/zaap zx,zy ; /travel x,y`. Aucun contrôle Zaap visible dans le guide.
8. Multicomptes : personnages participant au guide (sélection persistante Organizer), prérequis individuels, étapes/succès déjà faits, sessions online/offline ; recommander le meilleur groupement d'activités sans confondre les progressions. Ne pas supposer qu'une quête se valide pour toute l'équipe.
9. Plan stable : IDs persistants par chapitre / étape, migrer sans perte ; recalcul incrémental à changement réseau, choix utilisateur et stock déclaré ; éviter de réordonner brutalement les fiches déjà validées.
10. Explicabilité interne : pour chaque choix, garder les dépendances, quêtes, résultats escomptés, alternative et preuves ; UI n'affiche pas les sources ni des explications non désirées.

## Noms des chapitres, fiches et actions : COURTS et compréhensibles
- Le générateur nomme les **chapitres et fiches** avec des intitulés naturels, utiles, distincts et aussi courts que possible ; le titre décrit ce qu'on fait, pas les explications ni la liste entière des quêtes concernées.
- **Objectifs indicatifs contrôlés** : chapitre <= 40 caractères, fiche <= 48 caractères, de préférence 2 à 6 mots. Ne pas couper arbitrairement un nom officiel de PNJ, monstre, donjon ou quête. Si une exception dépasse la limite pour rester exacte, la justifier et la signaler au diagnostic (REVIEW, non suppression silencieuse).
- Commencer par un verbe d'action uniquement quand cela clarifie le but. Éviter les titres génériques (`Étape suivante`, `Faire des choses`), les chaînes de prérequis, les coordonnées redondantes, les noms complets de plusieurs quêtes et les formules artificielles (`Optimisation intelligente des objectifs...`).
- Exemples attendus : `Alignement Bonta` (chapitre) ; `Retour à Amayiro`, `Combats des Scarafeuilles`, `Donjon des Blops`, `Capturer le Bouftou Royal` (fiches). La fiche explique les conditions et les objectifs dans son **contenu**, jamais en surcharge du titre.
- Pour les actions, libellé concis mais **nom exact du monstre / PNJ / objet + quantité si nécessaire** : `×5 Tournesol sauvage`, `Parler à Amayiro`, `Récolter 10 Orties`. Ne pas abréger au point de rendre un objectif ambigu. Garder dans les données les identifiants et les liens complets.
- Si plusieurs fiches auraient le même titre, ajouter un discriminant minimal de zone, type d'action ou donjon, pas un suffixe générique `(2)` sans contexte. Une renumérotation ne doit pas casser les identifiants persistants.
- Créer un module de **naming déterministe partagé** par les outils de génération, les Guides Succès et Lanyel ; une règle unique pour titres/chapitres/actions, au lieu de retouches visuelles ou de chaînes tronquées par CSS.
- Doctor Guide/Integrity vérifie automatiquement la longueur, les titres peu informatifs, les duplications ambiguës, les identifiants perdus, les noms inventés et la lisibilité ; échantillonner des centaines de titres réels et valider les exceptions manuellement.
- **Ne pas injecter d'autres panneaux dans l'UI** pour résoudre un titre trop long. Les prérequis, les quêtes liées et les sources restent des données internes sans affichage systématique dans les fiches.

## Points supplémentaires verrouillés — intégration terrain
- **Captures de zones, pas seulement boss** : détecter séparément les objectifs de capture/collecte spéciaux de zone et les pierres d'âme classiques. Ne jamais écarter silencieusement une capture de zone ni l'assimiler automatiquement à une pierre. Vérifier pour chaque version du jeu les conditions exactes, le nombre de monstres/groupes et si une ressource consommable est réellement nécessaire.
- **Déplacement optimisé au niveau de la route entière** : chaque coordonnée cliquable existante est reliée à un plan de déplacement déterministe, calculé à la génération, jamais à une heuristique d'affichage. Tenir compte du dernier point fiable, de l'accès au Zaap, du monde et des retours obligatoires des quêtes. Si l'information est insuffisante, n'envoyer aucune commande risquée.
- **Participants exacts** : sélectionner dans Organizer des identités distinctes (pas seulement le nombre de personnages) ; étudier qui a déjà validé quoi pour éviter les étapes inutiles. Une capture de boss/zone et une pierre déjà acquise ne sont pas nécessairement équivalentes : traiter stock et validation séparément.
- **Préparation générale réelle** : agréger le total du guide et les besoins RESTANTS selon les participants choisis, avec quantités par puissance/type de pierre, acquisition de ressources au fil du trajet et suivi 50 possédées / 150 nécessaires. Prévoir correction manuelle et historique de stock sans inventer des possessions.
- **Mesure de qualité** : la réussite ne dépend pas seulement du nombre de fiches. Garder les objectifs exhaustifs, les coordonnées exactes, les textes d'action courts, les noms propres exacts et tous les prérequis ; comparer et faire contrôler les trajets, la clarté des fiches, les captures de zone, les doublons de PNJ et la stabilité des sauvegardes. Les sources sont conservées seulement pour l'audit interne.

## Contrat préparation : quantités et stocks pour sélection multicomptes (18/10)

- **Besoins calculés PAR identité stable de personnage** pour chaque guide, étape non terminée et objet réel identifié (item_id/type/puissance/usage). N'utiliser la somme des participants sélectionnés que pour afficher le résumé, jamais comme raccourci `besoin d'un perso × nombre de comptes`.
- **Ne pas compter une action déjà validée sur un personnage** mais pas sur un autre. Garder les coûts par personne (potions, pierres, clés selon consommation réelle), et les dépendances communes uniquement si le partage est vérifié. Les quêtes peuvent avoir un ordre/progrès différent et une classe peut avoir des prérequis propres.
- Exposer au rendu #225 les quantités `required`, `owned` (stock déclaré, vérifié ou inconnu), `missing` (inconnu si données insuffisantes), `selected_character_ids`, `breakdown_by_character`, `item_id`, `category`, `transferability/sharing_mode`, `evidence` ; contrat stable, simple, paresseux et versionné, pouvant utiliser d'autres noms de champs réels.
- Les potions sont groupées sous **catégorie Potions**, les pierres d'âme et autres ressources sous **Objets**. La vue `Tout` ne présente que des **agrégats par catégorie** et les conditions générales : évite les doublons et rend le panneau fluide pour des centaines d'items.
- Ex. quantités de potions encore nécessaires : Panda 4, Hupper 2 => besoin 6 si tous deux choisis, 4/2 lorsqu'un seul participe. Les stocks respectifs ou stock commun prouvé se soustraient **une fois au bon périmètre**, jamais une fois par personnage pour le même objet déclaré partagé. Les objets de métier collectés en cours de guide ne deviennent pas automatiquement un achat anticipé.
- Un participant hors ligne mais sélectionné conserve un besoin prévisionnel fondé sur la dernière progression fiable ; sa progression devient inconnue si données insuffisantes, et il n'est jamais ajouté par défaut en absence de sélection. Mutation de sélection, progression, guide, inventaire déclaré ou statut de prérequis -> invalidation/recalcul ciblé.
- Pour les pierres, distinguer capture boss/archimonstres, variantes par puissance/type, captures de zone spéciales et ressources de drop ; ne déduire une consommation de pierre que d'un mécanisme étayé, pas du titre de l'objectif.
- Tests unitaires/métier : permutations de sélection, 0/1/2/5 participants, besoin différent par perso, accomplissement sur un seul compte, stock partagé vs séparé, catégorie métier/potion/objet, inconnues, quantités nulles, deux pierres incompatibles, guide variable, coût mémoire pour liste de 1 000 références. Doctor signale stocks négatifs, doublons, besoins hors catégorie et inférences non prouvées.


## Contrat « prêt en un clic » et « À prévoir » juste à temps

- **Article prêt manuellement** : le rendu #225 doit pouvoir déclarer en un clic `prepared=true` pour un ensemble explicite de participants sélectionnés et d'items réels. Le moteur conserve cette **déclaration utilisateur** distincte de la preuve réseau, d'une quantité exacte possédée et de l'achèvement d'une quête. Elle ne doit PAS alimenter les validations automatiques de quêtes.
- Le contrat persistant de couverture associe guide, item_id/type/puissance/usage, identité(s) stable(s) de personnage(s), contexte du besoin et quantité exigée au moment de la confirmation. `Prêt` est vrai pour la sélection seulement si **chaque** participant avec besoin restant est couvert ; ajout d'un autre personnage ou augmentation de besoin révoque/affiche `à vérifier` pour cet ID, jamais auto-validation du nouveau besoin. La valeur numérique manquante et l'origine des stocks restent consultables, sans être inventées par le clic ✓.
- **Classification temporelle rigoureuse des besoins** : `avant_depart` (vraies préparations globales), `juste_avant_action` (clé de donjon, pierre adaptée avant boss, potion consommée à cet instant), `obtenu_sur_parcours` (récolte/drops exploités dans la route) et `objectif_quete` (action réelle). Toute exigence porte son item_id, sa quantité, sa condition, son action_id/fichier/étape et sa portée par personnage ; le rendu peut produire un rappel `À prévoir : item ×N` **contextuel**, mais JAMAIS une nouvelle liste `À préparer` par fiche.
- **Anti-doublon** : ne pas répéter l'inventaire global sur chaque fiche, ne pas requalifier les récoltes/drops naturels en prérequis d'achat, et ne pas afficher `À prévoir` lorsqu'un besoin est couvert par une confirmation `Prêt`, une possession réellement prouvée ou une étape planifiée avant l'action. Si préparation globale déjà signalée mais toujours manquante au point de blocage, autoriser **un seul rappel court** sur l'action critique, non une répétition des listes.
- **Multicomptes** : l'alerte reflète seulement les participants concernés par la fiche et non prêts. Une clé consommée individuellement ×3 n'est pas un seul achat pour tout le groupe ; si Panda couvert et Hupper non couvert, l'alerte affiche Hupper uniquement / un manque fiable. Ne pas multiplier aveuglément les besoins et ne pas utiliser un stock possédé par un autre compte non transférable.
- **Contrats dérivés par étape** (noms à adapter au code existant) : `StagePreparationNeed(item_id, quantity, need_kind, stage_id, action_id, character_id, source_evidence)`, `PreparationCoverage(guide_id, item_id, character_id, required_at_check, status=declared_ready)`. Conserver les identifiants exacts et une seule source de vérité entre panneau global et fiche.
- Doctor Guide / tests : besoins just-in-time vs global, captures de zone ne nécessitant aucune pierre, donjon avec clés déjà possédées, collecte pendant la route, consommables différents selon personnage, item confirmé prêt puis besoin modifié, sélection d'un 3e participant, refus d'inventer une preuve réseau, absence de duplication de lignes locales.

## Interface vers les autres PRs
- Exposer `GuideTravelPlan(destination, mode, zaap_coords?, world?, eligible_character_keys)` et `GuideParticipantSelection(guide_id, character_keys)` ou contrats équivalents versionnés, sans imposer ces noms de classes.
- La PR Organizer exécute strictement la commande typée, après validation des fenêtres sélectionnées et sans envoyer à d'autres comptes.
- La PR UI rend les textes et anneaux existants, aucun nouveau panneau.

## Audits et tests exigés
- Jeux de cas réels : Bonta/Amayiro, quêtes multi-zone, PNJ répétés, drops partagés, donjons avec succès mutuellement exclusifs, captures boss / archis, mondes différents, Zaap inaccessible, combat bloqué.
- Comparaison ancien/nouveau parcours : nombres de visites de cartes/zones, retours PNJ, donjons, combats, pierres, km/Zaaps estimés **sans inventer de métrique réelle**. Les chemins calculés doivent être prouvés au niveau des IDs et des étapes.
- Doctor Guide/Graphify : objectifs orphelins, doublons, erreurs de quantités, recettes impossibles, mauvais mob, manque capture, transport invalide, prérequis sautés, liens d'identifiants, boucle ou branche bloquante.
- Contre-exemples (fausse alternative HDV, besoin de 2 donjons, un participant déjà terminé, réseau partiel) + régression Guide Lanyel, Quêtes, Succès, intégrité, RAM et certification HEAD exact.
