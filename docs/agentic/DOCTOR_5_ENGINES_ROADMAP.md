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
