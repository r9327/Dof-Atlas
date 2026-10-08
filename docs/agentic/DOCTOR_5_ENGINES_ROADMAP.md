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
