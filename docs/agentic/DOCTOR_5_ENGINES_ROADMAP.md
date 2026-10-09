# Doctor Atlas — cinq moteurs, dix-huit capacités

Objectif : intégration profonde de Graphify, observations dynamiques vérifiables et validations rapides.
Ce fichier décrit une trajectoire, pas une certification complète.

## Graph Intelligence
- Existant : Graphe AST, cycles, communautés, hubs, candidats orphelins et comparaison SHA.
- Nouveau : reachability depuis les points d'entrée connus, doublons AST exacts, exceptions silencieuses suspectes, références JSON.
- En cours : règles spécifiques à tous les domaines, lineage JSON jusqu'à l'UI, quasi-doublons et vérification des contrats.

## Runtime Inspector
- Nouveau : observations Python opt-in, imports, fichiers, processus et sites d'appels Qt/PySide.
- Nouveau : marqueurs de cycle de vie et références faibles enregistrés explicitement, traces bornées et datées par SHA.
- En cours : véritables scénarios Qt, callbacks natifs, corrélation RAM/CPU et ownership des objets WebEngine.
- Absence d'observation ne prouve jamais qu'un composant est inutilisé.

## Change Intelligence
- Existant : analyseur d'impact Agent, règles Atlas Integrity, comparaison Graphify.
- Nouveau : changements Git, imports restés vers un fichier déplacé ou supprimé, simulation de refactorisation sans mutation.
- En cours : garde-fous par domaine, analyse incrémentale avancée et classement historique des régressions.

## Test Intelligence
- Existant : Agent Planner et Atlas Integrity sont les autorités canoniques pour choisir les tests.
- Les commandes de consultation n'exécutent ni Full Suite, ni RAM benchmark, ni reconstruction du graphe.
- La certification obligatoire est différée, jamais déclarée PASS si elle n'a pas tourné.
- En cours : statistiques de coût et couverture dynamique par scénarios réels.

## Doctor UI
- Nouveau : Graphify local interactif, navigation GitHub, recherche, zoom, filtres, raisons de signalement.
- Nouveau : superposition des appels Python réels avec comparaison du SHA de la trace.
- En cours : très grands graphes paginés, navigation IDE et historique comparatif enrichi.

## Les commandes
- python -m tools.atlas_doctor change-plan --base-ref origin/main --json
- python -m tools.atlas_doctor code-inspect --base-ref origin/main --json
- python -m tools.atlas_doctor refactor-preview app/modules/encyclopedia/providers/guide_provider.py --action remove --json
- python -m tools.atlas_doctor runtime-trace --module tests.test_atlas_doctor_runtime_observation
- python -m tools.atlas_doctor graph --rebuild
- python -m tools.atlas_doctor graph-ui --open

## Gates
1. Aucun test de quatre heures sur chaque commit. Un changement local passe des tests ciblés.
2. Aucun statut PASS issu d'un graphe périmé, d'un test non exécuté ou d'une hypothèse.
3. Aucun code supprimé sur la seule base d'une communauté isolée ou d'un indice de duplication.
4. Aucun dépassement des seuils de RAM Phase 8 pour faire passer un gate.
5. PR #123 reste draft jusqu'à la convergence avec #116 et certification exacte-SHA.

Etat : fondations fonctionnelles dans les cinq moteurs, capacités avancées encore partielles.

## Suivi Git interactif et léger

`python -m tools.atlas_doctor graph-live --open` lance un serveur strictement local (`127.0.0.1`), avec un écran interactif et une lecture du diff Git toutes les 2,5 secondes. La carte AST est figée tant que `graph --rebuild` n'est pas exécuté explicitement. Les fichiers modifiés sont surlignés et l'interface annonce les chemins non représentés. `graph-live --once --json` affiche le même état sans serveur. Aucun test ni benchmark n'est lancé par le mode live. Ctrl+C arrête le serveur.

### Mode événementiel — priorité aux sessions de code

Graphify LIVE ne lance plus un `git diff` toutes les 2,5 secondes. La page active réactualise l'état Git à l'ouverture, au retour du focus et via « Actualiser Git » ; un battement local toutes les 60 secondes maintient uniquement le serveur (sans lire le dépôt), qui s'arrête après 180 secondes sans présence du navigateur. Aucun moniteur n'est embarqué dans Dofus Atlas. Hooks éditeur sur sauvegarde et CI sur push pourront déclencher ensuite les analyses ciblées ; ce ne sont pas encore des actions automatiques incluses dans cette version.

### Déclenchement par événements de développement

Le hook Git pré-commit existant ajoute désormais un **indice Doctor non bloquant**, limité aux fichiers réellement indexés : aucune exécution de tests supplémentaire et aucun rebuild Graphify. La CI sur push reste l'autorité de validation ciblée. Pour un éditeur, un événement `save` peut être appelé explicitement, sans installer de watcher permanent : `python -m tools.atlas_doctor dev-event --event save app/ui/components.py --json`. Pour contrôler un lot avant push : `python -m tools.atlas_doctor dev-event --event push --base-ref origin/main --json`. Les tests sont suggérés, pas exécutés. Le gate de validation Atlas Integrity conserve son autorité.

### Véritable inspection AST différentielle sur événement

L'API locale `graph-live` compare maintenant les imports AST **des fichiers Python modifiés seulement** au contenu exact du commit Graphify ; 12 fichiers, 256 Kio par fichier, 32 imports par sens au maximum. Le panneau du nœud affiche les imports ajoutés/supprimés et leurs lignes ; les erreurs et troncatures sont explicitement signalées. Le graphe statique reste figé jusqu'au rebuild. Aucun cycle de scan permanent ni instrumentation runtime n'est lancé par cette action.

### Graphify LIVE sur worktree déjà modifié

Si la carte Graphify précédente est périmée mais syntaxiquement valide et rattachée à un commit Git existant, **seul le mode LIVE** peut l'afficher comme un instantané `REVIEW` avec les imports AST courants comparés au commit de l'ancien graphe. Les audits Doctor `graph-audit` et `graph-ui` ordinaires conservent la règle stricte `PASS` exact-SHA : aucun résultat historique n'est présenté comme diagnostic source validé sur le code courant.

### Budget CI Graphify

Le workflow lourd `Graphify Code Map` est déclenché explicitement (`workflow_dispatch`) ou automatiquement lors de changements structurels sélectionnés (code applicatif / moteur Graphify / analyses de graphe) et de PR structurelles vers main. Les changements UI Doctor, docs et hooks seuls ne déclenchent plus sa reconstruction à chaque push. `Graphify Focused Architecture` reste automatique sur chaque push de #123. **Une reconstruction Graphify exacte-SHA finale reste nécessaire avant toute fusion**, ainsi que les gates RAM et FULL de Phase 8 ; aucun PASS par omission.

### Consommateurs dynamiques candidats

`python -m tools.atlas_doctor consumer-sites app/pages/character_page.py --json` : inspecte les consommateurs statiques prouvés par l'outil Agent existant et un nombre borné de fichiers contenant des mentions du module. Les appels `import_module` littéraux, imports non littéraux, lieux `signal.connect` et attributs réflexifs sont classés comme **pistes**, jamais comme preuves d'exécution ou de code mort. Les noms construits sans le nom du module peuvent échapper à la recherche textuelle ; `safe_to_delete` reste faux. Aucun graphe reconstruit, aucune suite lancée.

### Enquête groupée sur les nœuds isolés

`python -m tools.atlas_doctor isolate-triage --limit 5 --json` réutilise `graph_audit.inspect_graph` et les recherches de consommateurs existantes. Le lot ne dépasse jamais 10 fichiers source et refuse un graphe périmé. Les résultats distinguent imports statiques confirmés, indices dynamiques et absence de preuves ; ils ne concluent **jamais** qu'un fichier est supprimable automatiquement. Pas de FULL_SUITE ni rebuild dans la commande.

### Pagination nœuds faibles et communautés

`python -m tools.atlas_doctor isolate-triage --kind weak --offset 0 --limit 5 --json` inspecte uniquement les premiers candidats de ce volet, fournit `next_offset`, puis reprend les suivants sans lancer de tests. Les catégories `orphan` et `community` sont disponibles séparément. La pagination concerne les candidats remontés par Graphify, non une preuve exhaustive de code mort ; `safe_to_remove` reste faux.

## Vérification Graphify — inventaire réel et pagination

L'artefact du commit `db88754a6679bf08c9596a1daf9ef8ec1308eed9` contient 11 366 nœuds, 33 269 relations et exactement 797 fichiers Python distincts. L'inventaire Git du même commit contient également 797 fichiers Python avec les mêmes chemins (contrôle des dénombrements par racine et empreinte calculée sur les chemins). Cela prouve une représentation complète des *fichiers* pour ce SHA, pas une couverture fonctionnelle ni l'absence de code mort. Le rapport signale 6 nœuds isolés, 334 nœuds faiblement connectés, 90 communautés isolées (6 avec du code applicatif) et aucune inversion `app → tools` confirmée.

L'interface Graphify conserve jusqu'à 15 000 nœuds / 50 000 arêtes dans les données de cet artefact, mais affiche désormais 1 200 nœuds par page pour plafonner le coût de dessin. La recherche, les filtres par domaine, communauté (avec effectif), priorité Doctor et preuves signalées portent sur le graphe entier : seul le dessin du sous-ensemble courant est paginé. Les arêtes sont montrées entre nœuds de la page, et non supprimées du graphe. L'inspecteur d'un nœud permet de naviguer vers un voisin d'une autre page et recentre la vue sur celui-ci. Entrée dans la recherche centre le premier résultat ; le lien GitHub ouvre la ligne source quand sa position est disponible. Le JavaScript généré est vérifié syntaxiquement dans les tests ciblés quand Node.js est présent. Ce rendu paginé ne certifie ni un temps d'interaction maximal, ni l'absence de code mort. Les commandes `isolate-triage --kind weak --offset <N>` et `--kind community --offset <N>` paginent les examens par petits lots (max. 10 fichiers par exécution), avec `next_offset` comme prochain curseur. Aucun examen limité par fenêtre ne doit être présenté comme exhaustif et aucun candidat ne doit être supprimé sans preuve indépendante.

Ce constat concerne le SHA de l'artefact, non les commits postérieurs de la PR. Le dernier SHA candidat nécessite ses propres contrôles ciblés ; la certification complète reste distincte.

### Indices AST sur les nœuds Graphify

Le mode `graph-ui` inspecte explicitement **au maximum 16 fichiers Python signalés** (erreurs d'import, exceptions avalées, références JSON littérales, structures proches), en respectant les bornes de `scan_sources`. Les indices sont visibles dans la fiche du nœud avec leurs lignes, sans être convertis en preuve de code mort ni en statut critique. Le graphe historique ne déclenche aucune inspection de sources actuelles. Aucune surveillance périodique ou exécution de tests n'est ajoutée à l'application.


### Simulation de refactorisation avec consommateurs runtime observés

`python -m tools.atlas_doctor refactor-preview app/pages/character_page.py --trace .ai/runtime/atlas_doctor/traces/scenario.json --json`

Le plan non mutatif combine les consommateurs Graphify confirmés avec les **appels Python réellement observés** et les **enregistrements Qt explicites** de la trace. La trace est acceptée seulement si le SHA correspond au HEAD courant, si le worktree est propre, si les événements ne sont pas tronqués et si le fichier reste dans `.ai/runtime` (10 Mo et 50 000 événements au maximum). Les événements dédupliqués restent limités à 60 consommateurs Python et 60 connexions Qt; un scénario non observé ne signifie jamais « code mort ». Une trace périmée est marquée `STALE` et ses résultats n'entrent pas dans les suggestions de fichiers à modifier. Aucun benchmark, graphe régénéré ni test n'est déclenché par la commande.

### Lignage JSON observé (Doctor code-inspect)

`python -m tools.atlas_doctor code-inspect app/core/catalog.py --trace .ai/runtime/atlas_doctor/traces/scenario.json --json` joint les tentatives d'ouverture de JSON réellement observées dans ce scénario avec les arêtes d'appels Python également observées vers les fichiers de vue. Le résultat `observed_json_to_ui` est borné (50 000 événements, 80 ouvertures, quatre sauts, 512 fichiers) et exige SHA exact, worktree propre et trace complète. Le diagnostic reste `REVIEW` : ouverture du JSON ≠ lecture effective; coexistence d'appels ≠ transfert de données ni rendu visuel. La recherche statique préexistante `data_lineage_to_ui` est conservée séparément. Aucun hook permanent ni benchmark.

### Événement d'entrée callback Qt, observation opt-in

`wrapped = observer.wrap_qt_slot(slot)` puis enregistrement explicite du callable `wrapped` dans un scénario Qt. L'événement `qt_callback_invoked` est émis seulement à l'entrée de la fonction Python sous trace active; retour et exceptions inchangés, sans interception des connexions de l'application. `code-inspect` et `refactor-preview --trace` séparent cet événement du simple retour de `signal.connect`. Les signatures Qt natives doivent être validées scénario par scénario; aucun ownership C++, fuite mémoire ni couverture totale ne sont présumés.

### Graphify : callbacks Qt exécutés dans le Canvas

Le graphe interactif et l'export de preuves par nœud distinguent désormais `QT_CONNECT_RETURNED` (enregistrement du signal) de `QT_CALLBACK_INVOKED` (entrée observée d'un callback Python explicitement instrumenté). Aucune arête d'exécution n'est affichée sans trace correspondant au SHA exact et à un worktree propre ; les callbacks non observés et l'ownership C++ restent non prouvés.

### JSON ouverts jusqu'aux vues UI, dans Graphify

L'inspecteur de nœud et l'export JSON intègrent désormais, depuis une trace opt-in exacte-SHA, les ouvertures de JSON et les chaînes d'appels Python co-observées jusqu'aux vues. Les preuves sont bornées et étiquetées `OBSERVATION_NOT_DATA_FLOW` : aucun transfert de données ni rendu visuel n'est déduit. Absence de trace valide = aucune preuve runtime affichée.

### Destruction explicite QObject, sans faux diagnostic de fuite

En scénario opt-in, `observer.watch_qt_destroyed(obj, label='guide_view')` raccorde un callback faible au signal `QObject.destroyed`, sans capturer l'objet et sans instrumentation permanente de Dofus Atlas. La trace et l'inspecteur Graphify indiquent uniquement la **réception du signal**, sous provenance exacte-SHA. Ce n'est pas une preuve de collecte du wrapper Python, de libération native WebEngine ni d'absence de fuite RAM. Aucun benchmark n'est déclenché.

### Scénario PySide6 réel, lancé uniquement sur demande

`python -m tools.atlas_doctor runtime-trace --module tools.atlas_doctor_lib.qt_smoke_scenario --json` exécute un mini-scénario avec un vrai `QCoreApplication`, un signal Qt réel, un slot Python instrumenté et le signal `QObject.destroyed` lors d'une destruction explicite. Le scénario ne démarre jamais automatiquement avec Dofus Atlas et exige PySide6/shiboken6 installés. Un test ciblé l'exécute seulement quand Qt est disponible ; un SKIP n'est pas une certification Qt. Correction associée : `connect_qt_signal` suit `__wrapped__` pour identifier la source réelle d'un callback enveloppé, et non le fichier de l'instrumenteur.

### Tentatives d’import Python observées dans Graphify

Les événements Python `import_attempt` (issus d’imports statiques ou dynamiques, sans distinction certaine) enregistrés par un scénario opt-in créent des relations `RUNTIME_IMPORT_ATTEMPT` distinctes des imports AST et des appels de fonctions. La conversion module→fichier est limitée aux fichiers Python présents dans le graphe exact-SHA et à 256 paires au maximum ; la trace doit être complète et le worktree propre. L'interface et l'export de preuves les affichent comme tentatives et **jamais comme succès d'import ou preuve de code mort**.

### Test Intelligence : coûts historiques sans exécuter de suite

`python -m tools.atlas_doctor test-costs --report .ai/runtime/<rapport_integrity>.json --json` lit jusqu'à huit rapports Atlas Integrity locaux déjà produits. Médiane/min/max des durées de groupes réellement exécutés avec succès ; réutilisations `FULL_SUITE` à 0 seconde, échecs, durées incomplètes et NaN exclus. Les données restent historiques, pas des prévisions ni une preuve de couverture. Aucun test, benchmark, Graphify rebuild ou watcher lancé. Les fichiers restent confinés à `.ai/runtime`.


## Lot d'intégration Doctor/Graphify — preuves utiles avant certification

Ce lot n'active aucune surveillance automatique dans DOFUS.bat, main.py, Guide ou
QWebEngine. Les mesures ne se font que dans un scénario explicitement lancé.

### Runtime Inspector — preuves progressives et bornées

- `RuntimeObserver.read_json("data/catalog.json")` décode le JSON avec succès et
  rend (valeur, jeton opaque). Aucun contenu JSON n'entre dans la trace.
- `RuntimeObserver.mark_ui_bound(token)` doit être appelé explicitement **après**
  l'affectation des données à la vue Python. Doctor fait correspondre les jetons,
  les fichiers et le SHA de la trace; un callback qui ne décode pas, un jeton inconnu
  ou une trace tronquée ne fournit pas cette preuve.
- `trace_explicit_json_bindings` et `code-inspect` conservent séparément les
  pistes d'ouvertures de fichiers et les **liaisons explicites**. La présence du
  marqueur ne prouve pas un frame Qt affiché ni un rendu WebEngine.
- `RuntimeObserver.snapshot_watches(label=...)` compte les références faibles
  vivantes, sans conserver les objets; ne prouve jamais une fuite.
- `RuntimeObserver.snapshot_process_tree(label=...)` relève à la demande le RSS
  d'un arbre de processus et le nombre de noms QtWebEngineProcess visibles,
  avec `psutil` facultatif et 64 enfants maximum. Absence de permission ou de
  bibliothèque = UNAVAILABLE/REVIEW, pas un faux PASS. Cette mesure **n'est pas
  lancée ici** et ne remplace pas les benchmarks Phase 8.

### Test Intelligence / Change Intelligence

- `python -m tools.atlas_doctor scenario-coverage --trace .ai/runtime/atlas_doctor/traces/guide.json --trace .ai/runtime/atlas_doctor/traces/quests.json --require-file app/pages/home.py --json`
  regroupe jusqu'à 12 traces exact-SHA. Les fichiers non rencontrés sont
  `unobserved_required_files`, **jamais des fichiers supprimables**. Une trace
  incomplète, d'un autre SHA ou malformée ne donne aucune couverture positive.
- `code-inspect` expose désormais les indices de frontières architecturales
  confirmés par AST, en inspection bornée à 16 fichiers, sans inventer de règle
  bloquante sur des couches qui ont des exceptions réelles.
- `refactor-preview --action consolidate` ajoute les corps AST identiques ou
  similaires parmi les fichiers ciblés; l'équivalence comportementale et toute
  fusion/suppression automatique restent expressément non prouvées.

### Graphify interactif

- Les nœuds affichent maintenant les traces `json_decoded → json_ui_bound`
  distinctement des simples chaînes d'appels ou ouvertures JSON.
- `graph-ui --ide-links --open` fournit un lien `vscode://file/...` par nœud
  Python : cette option est désactivée par défaut car elle inscrit le chemin
  local absolu dans le HTML exporté. Aucune liaison VS Code permanente.
- Recherche, communautés, pagination, snapshots historiques, inspections de
  consommateurs et export des preuves précédemment intégrés restent inchangés.

### Conditions de fin des 18 capacités

L'implémentation des primitives n'est **pas** une preuve de couverture réelle des
flux Guide / Quêtes / Succès / Équipement. La liaison Qt et WebEngine native ne
peut pas être déduite de la seule trace Python; un sous-processus WebEngine
observé n'est pas une preuve de propriété d'un QObject. Il faut encore exercer
des scénarios réels et valider les garde-fous de comportement, puis figer le
HEAD pour les suites de certification finale. Tant que ces scénarios et les
checks obligatoires ne sont pas validés : **DRAFT, non certified, no merge**.
Aucune relance répétée des benchmarks RAM/preload pendant le développement.


### Scénario réel Équipement, sans navigateur et sans benchmark

`python -m tools.atlas_doctor runtime-trace --module tools.atlas_doctor_lib.app_ui_smoke_scenario --max-events 50000 --json` exerce un vrai `EquipmentPage` sous `QApplication` (PySide6 offscreen) : construction du widget, changement de section, observation faible, réception `QObject.destroyed`, destruction C++ explicite. Le scénario ne montre aucune fenêtre, n'ouvre pas Huzounet et n'importe pas Chromium. À lancer **manuellement** avec `QT_QPA_PLATFORM=offscreen`; il ne prouve ni le Guide/Succès ni le fonctionnement du navigateur externe. Test ciblé disponible dans `tests/test_atlas_doctor_app_ui_smoke.py` (SKIP lorsque Qt/offscreen n'est pas configuré).

### Comparaison de scénarios historiques sans fausse régression

Les traces lancées par `runtime-trace` incluent leur nom de module `scenario_module`. La commande `python -m tools.atlas_doctor scenario-diff --before .ai/runtime/atlas_doctor/traces/before.json --after .ai/runtime/atlas_doctor/traces/after.json --json` compare uniquement deux **mêmes scénarios**, complets et datés par SHA, en classant les relations Python/Qt observées qui disparaissent comme `REVIEW`. Un appel non observé dans une nouvelle exécution n'est pas une preuve de bug, de code mort ni de suppression sûre. Aucun scénario, test, graph rebuild ou benchmark n'est lancé pendant la comparaison.


### Scénarios réels Guides / Succès en chargement différé

`python -m tools.atlas_doctor runtime-trace --module tools.atlas_doctor_lib.encyclopedia_deferred_smoke --max-events 50000 --json` vérifie, uniquement à la demande et avec `QT_QPA_PLATFORM=offscreen`, la création des vrais `GuidesView` et `AchievementsView` en `defer_runtime=True`. Les fournisseurs sont volontairement inertes, les chemins de progression du Guide sont temporaires, les catalogues ne sont pas hydratés, et la destruction QObject est observée. Ce scénario ne valide pas le détail d'une quête ni l'exactitude des guides; ceux-ci requièrent une session d'intégration avec les données de l'application. Test manuel ciblé : `tests/test_atlas_doctor_encyclopedia_smoke.py`; un SKIP sans PySide6/offscreen ne prouve rien.


### Scénario Qt Quêtes sans catalogue massif

Le scénario `encyclopedia_deferred_smoke` couvre aussi `QuestsPage` avec `QuestCatalog([])`, `QuestProvider` et `QuestGraphService(eager=False)` réels, plus des chemins de profil/progression temporaires. Il confirme que le panneau de détail n'est pas construit et que le widget peut être détruit sans importer les données complètes. Cette vérification porte sur le **shell à zéro quête** : la recherche, le graphe des prérequis et le détail de vraies quêtes doivent encore être exercés dans une session applicative dédiée.


### Validité native QObject distincte de la référence Python

`RuntimeObserver.snapshot_qt_objects(label=...)` inspecte seulement les widgets/objets Qt explicitement enregistrés via `watch(..., kind='qwidget'|'qobject'|'qt')`. `shiboken6.isValid` distingue objets C++ encore valides, wrappers Python pointant vers un objet C++ invalidé et wrappers déjà collectés. Borne stricte : 128 références **faibles**, sans garder de QWidget vivant. Le graphe montre les cas d'invalidation observés, jamais une preuve de fuite, d'ownership, ni d'absence de mémoire native retenue. Les scénarios Qt réels Équipement/Guides/Quêtes/Succès prennent chacun un instantané avant et après destruction ; ces scénarios ne tournent jamais avec l'application normale et restent à valider en environnement Qt offscreen.


### JSON décodé → véritable QLabel Qt dans l'application

`RuntimeObserver.bind_json_label_text(token, label, value)` effectue
lui-même `QLabel.setText`, relit `QLabel.text` et enregistre uniquement la
réussite, le jeton opaque et le fichier Python du widget propriétaire.
La trace n'embarque jamais le texte ni le contenu JSON. Le scenario
`app_ui_smoke_scenario` crée une entrée JSON temporaire sous
`.ai/runtime/atlas_doctor`, la décode, alimente réellement
`EquipmentPage.section_label`, vérifie le résultat et supprime le fichier.
Le moteur `trace_explicit_json_bindings` distingue le marqueur déclaratif
`EXPLICIT_UI_BINDING_MARKER` de
`EXPLICIT_QT_LABEL_SETTEXT_RETURNED` (liaison textuelle effectivement
exécutée). Ce n'est toujours pas la preuve qu'un frame a été peint ni qu'une
valeur est arrivée dans QWebEngine. Rien ne s'exécute au lancement normal de
Dofus Atlas, et aucun benchmark n'est déclenché.


### Graphify multi-scénarios sans surveillant permanent

La commande `graph-ui --trace .ai/runtime/atlas_doctor/traces/guide.json --extra-trace .ai/runtime/atlas_doctor/traces/quests.json --open` superpose les preuves de deux à huit scénarios **complets, exact-SHA et worktree propre**, avec un plafond partagé de 50 000 événements. Elle n'exécute pas de scénario et ne lance ni CI ni benchmark. Le compteur de scénarios figure dans la vue.

Les événements sont rattachés explicitement à leur scénario (`_trace_group`), y compris les jetons JSON `json-1` qui peuvent être identiques dans des exécutions différentes : aucune lecture d'un scénario ne peut être reliée à une affectation QLabel ou à une chaîne d'appels d'un autre. En cas de provenance partielle ou périmée, l'ensemble est refusé plutôt qu'un faux résultat positif. L'absence de preuve dans ces scénarios ne prouve toujours pas qu'un fichier est inutilisé. `--trace` unique conserve son fonctionnement antérieur.


### Reachability conservative et filtre Graphify par scénario

`code-inspect` sépare désormais les modules atteints par les imports AST ou les appels Python/Qt réellement observés, et les *tentatives* d'imports Python vers des modules du dépôt. Un import déclenché par l'audit hook peut échouer : ces cibles apparaissent dans `unreached_with_runtime_import_attempt`, et ne deviennent jamais « atteintes » ou « supprimables » par ce seul événement. Les traces malformées/incomplètes sont refusées.

Dans `graph-ui`, un filtre « Scénario runtime » permet de retrouver les nœuds rencontrés pendant chaque trace du lot agrégé, avec provenance exact-SHA. Un nom de scénario peut se répéter sans confusion : la sélection repose sur son rang dans le lot, pas sur une égalité de noms. Les traces séparées ne sont pas recollées en flux de données artificiel. Aucun watcher ni test lancé à l'ouverture du graphe.


### Capture guidée des scénarios Qt réels

`QT_QPA_PLATFORM=offscreen python -m tools.atlas_doctor capture-ui encyclopedia --json` lance **uniquement sur demande** le scénario offscreen prévu pour Guide/Quêtes/Succès. Les variantes `capture-ui equipment` et `capture-ui qt` sont également disponibles ; les noms sont limités à une liste de trois modules validés, pas de lancement libre de `main.py`. La commande range sa trace dans `.ai/runtime/atlas_doctor/traces/atlas_ui_<scenario>.json`, sans création de watcher permanent, sans exécuter la FULL_SUITE et sans benchmark RAM/preload. La fonctionnalité n'est pas exécutée lors des builds normaux et n'installe aucun hook applicatif. Le JSON des preuves se combine ensuite explicitement via `graph-ui --trace ... --extra-trace ...`.


### Intégration opérationnelle Doctor : enquêtes Graphify et coût des tests

`isolate-triage --kind weak --limit 5 --trace .ai/runtime/<trace1>.json --trace .ai/runtime/<trace2>.json --json`
conserve les contrôles du graphe et des consommateurs source tout en recoupant, à la demande,
les appels Python réellement entrés et callbacks Qt explicitement observés.
Les traces doivent être complètes, sous `.ai/runtime`, issues d'un worktree propre,
et correspondre exactement au SHA du graphe courant (maximum huit traces, 50k événements combinés).
Les preuves positives `RUNTIME_OBSERVED` sont conservées, mais un fichier non observé reste
`NOT_OBSERVED_NOT_DEAD_CODE` et `safe_to_remove=false`. Les tentatives d'import sont
des pistes séparées des appels réellement exécutés. Aucun observateur permanent.

`change-plan --base-ref origin/main --cost-report .ai/runtime/<integrity-report>.json --json`
présente désormais un ordre *conseillé* des groupes déjà requis par le plan Agent/Integrity,
du groupe historiquement le plus rapide au plus lent. Les durées sont lues uniquement
dans des rapports de validations **réellement exécutées** ; les coûts inconnus restent explicites.
Les groupes obligatoires sont conservés, aucun FULL_SUITE/DEEP gate n'est supprimé,
et l'ordre n'est ni une prévision de durée ni une certification. Cette consultation ne lance
aucun test, benchmark ou reconstruction du graphe. La PR reste DRAFT et non fusionnée.


### Checkpoints CPU/RAM par scénario opt-in (aucun benchmark lancé)

`RuntimeObserver.snapshot_process_tree(label=...)` peut à présent relever, outre
le RSS courant de l'arbre Python + enfants, le temps CPU **cumulatif** de ces
processus et une empreinte anonyme de leur ensemble d'identités (PID et heure
de création condensés). Ni adresse, ni arguments, ni contenu utilisateur ne
sont enregistrés. En cas de dépendance `psutil` absente, d'inaccessibilité,
de données CPU partielles ou de tronquature, la métrique concernée est
signalée indisponible, jamais remplacée par une valeur de confort.

`summarize_process_checkpoints` compare uniquement deux checkpoints
successifs si les mêmes processus ont été relevés : différences RSS et
temps CPU cumulé. En cas de changement d'un processus WebEngine ou autre,
la comparaison est refusée. L'observation est exposée dans
`code-inspect --trace` et dans le panneau de Graphify `graph-ui --trace`.
Les scénarios offscreen optionnels Équipement et Encyclopédie émettent ces
checkpoints lors de leur exécution manuelle. **Aucune attente active,
instrumentation de DOFUS.bat, exécution répétée ni certification de pic
RAM/performance ne découle de ces fonctions.** Elles ne prouvent ni la
propriété native d'un QObject ni la mémoire libérée par QWebEngine.


### Véritable cycle QThread, sans faux diagnostic de worker bloqué

`RuntimeObserver.watch_qt_thread(thread, label=...)` instrumente uniquement,
sur demande explicite, les **signaux Qt réels** `QThread.started` et
`QThread.finished`. Les callbacks ne conservent pas le QThread : ils
référencent l'observateur faiblement. Borne stricte de 128 watchers Qt;
les événements indiquent le module du scénario, un jeton d'instance et
le type de signal effectivement livré.

`summarize_runtime_lifecycle` recoupe démarrage/fin sur le jeton et le groupe
de scénario, empêchant qu'un `finished` d'une autre exécution fasse croire
qu'un QThread est terminé. L'inspecteur Graphify et l'export par nœud
signalent les débuts restés sans fin observée (`REVIEW`), mais ne
concluent **jamais** à une fuite mémoire, un deadlock ou une propriété native.

Le scénario réel `tools.atlas_doctor_lib.qt_smoke_scenario` comprend un
`QThread` à exécution courte, créé et détruit en PySide6; il reste
strictement opt-in, sans travail de fond dans Dofus Atlas. Sa vérification
Qt n'est pas considérée PASS si PySide6 est absent et que le test est SKIP.
Aucun benchmark RAM/preload ni certification finale n'est lancé dans ce lot.


### Doctor — audit Qt/WebEngine/caches et frontières privées

La commande code-inspect expose désormais resource_lifecycle : revue AST bornée des constructions QWebEngineView/Page/Profile, QThread, QTimer, QNetworkAccessManager, des arguments parent=, des appels de nettoyage et des caches Python sans limite explicite. layer_boundaries détecte aussi les imports vers les vues/widgets privés d'un autre domaine. Ces signaux servent à prioriser les scénarios réels : absence de parent explicite n'est pas une fuite prouvée, et une référence Python ne prouve jamais la propriété C++ d'un QObject.

Mode consultation uniquement : aucun test, benchmark, import applicatif ni reconstruction Graphify implicite. Les scénarios Qt réels et la certification finale restent nécessaires avant merge.


### Indices de parenté QObject natifs (scénarios manuels uniquement)

Les snapshots existants interrogent shiboken6.isValid puis QObject.parent() pour les wrappers Qt explicitement observés. Ils comptent les wrappers WebEngine, ceux qui ont un parent Qt natif valide et les cas sans parent visible, par scénario. Un parent Qt présent ne prouve pas la libération de Chromium ; son absence ne prouve pas une fuite. Ces indices sont disponibles dans summarize_runtime_lifecycle, sans instrumentation automatique de Dofus Atlas et sans nouveaux tests lancés.


### Scénario WebEngine isolé, strictement manuel

Doctor propose capture-ui webengine (QT_QPA_PLATFORM=offscreen). Ce scénario distinct du parcours Équipement crée un profil WebEngine sans persistance, sa page et sa vue, puis relève les relations QObject.parent(), la validité native des wrappers et les instantanés facultatifs du processus. Il ne navigue pas, n'utilise aucune donnée utilisateur et ne démarre jamais avec DOFUS.bat. Il peut lancer des processus Chromium lors de son exécution explicite et doit donc rester réservé à la certification finale, pas aux commits de développement. La fin des wrappers natifs ne prouve pas la libération du RSS Chromium.


### Suivi historique multi-scénarios, sans fausse régression

La commande scenario-trend --trace A --trace B [--trace C ...] lit entre 2 et 8 traces complètes, ordonnées et étiquetées par SHA, pour le même scénario. Elle compare les relations Python/Qt réellement observées et distingue une absence ponctuelle d'une absence répétée sur au moins quatre captures. Un écart reste REVIEW, jamais une régression fonctionnelle prouvée : une différence de branche d'exécution ou d'ordonnancement Qt suffit à l'expliquer. Lecture locale uniquement, 32 Mo maximum au total, sans exécution de tests, sans benchmark, sans watcher et sans rebuild Graphify.


### Graphify affiche les pistes WebEngine et caches

Les diagnostics source de cycle de vie Qt/WebEngine et de caches non bornés sont désormais directement associés aux nœuds des fichiers concernés dans l'inspecteur du graphe et son filtre par catégorie Doctor. Ils sont calculés seulement sur les 16 fichiers explicitement sélectionnés pour le diagnostic courant ; un graphe historique ne relit jamais des sources modernes. Tous les avertissements restent candidats à vérifier, sans suppression automatique ni déduction de fuite.
