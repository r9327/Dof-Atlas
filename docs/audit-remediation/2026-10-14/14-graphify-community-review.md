# [PLAN 14] Audit des communautés, nœuds faibles et fusions Graphify vérifiables

> PR DRAFT de triage — rapport et plan, **aucun refactor ou suppression autorisés sans preuve**. Source : [audit PR #160](https://github.com/r9327/Dof-Atlas/pull/160), main `ac07be9b894718f5e68e7c3a91016d7651e3065b`.

## Objectif
Traiter les registres Graphify individuels restés hors des 28 anomalies ciblées, sans confondre métrique de graphe et architecture réellement défectueuse.

## Registres et périmètre
- `registres/graph-nodes.json`, `graph-communities.json`, `graph-all-candidates.json`, `graph-weak-candidates.csv` (archive #160).
- 12 637 nœuds / 36 460 liens selon l'extraction exacte-SHA ; 496 groupes, 107 communautés isolées, 76 candidats cohésion.
- Familles du rapport : imports différés, façades lazy, responsabilités, doublons, hubs, connexions faibles, cycles.

## Triage et preuves
1. Partir des registres publiés graph-nodes.json, graph-communities.json, graph-all-candidates.json et graph-weak-candidates.csv ; vérifier identité de la version Graphify 0.9.72 et exact-SHA du code.
2. Trier les 496 communautés, 107 communautés isolées, 76 candidats de cohésion et tous les nœuds faibles selon le rôle réel ; ne pas produire un backlog de 496 pseudo-bugs.
3. Pour chaque candidat prioritaire (fort couplage, orphelin apparent, cycle, duplicate), confronter les liens inferred avec imports AST, exports lazy, callbacks, registre d'entrypoints, consumer sites et captures runtime.
4. Vérifier d'abord les familles critiques : Guide/Quêtes/Succès, réseau/capture, runtime Qt, persistance utilisateur, Craft et Scan Monde ; déduire un impact réel avant toute proposition de déplacement.
5. Contrôler les quatre composantes d'imports cycliques documentées (différés/type-only) ; ne pas les classer cassées sans import-time ou scénario défaillant.
6. Publier une décision nominative exploitable : CONSERVER (raison), FUSION CANDIDATE (consumer + tests + gain), EXTRACTION CANDIDATE, DELETABLE PROUVÉ (critère très strict), ou INVESTIGATION BLOQUÉE.
7. Simuler blast radius et préparer uniquement les patchs justifiés ; si AT-001/015/016/017 sont déjà corrigés dans #161/#166/#169, réutiliser leurs preuves sans refaire le travail.
8. Documenter les limites de reachability dynamique et exclure toute fusion de communautés faite seulement pour optimiser Leiden/degré.

## Critères de sortie
- [ ] Chaque famille prioritaire a une décision et la référence d'une preuve ; la couverture exhaustive des candidats est mesurable.
- [ ] Aucune suppression de module/script/namespace/public lazy export sans démonstration d'absence de consumer et test de compatibilité.
- [ ] 4 cycles documentés reclassés selon IMPORT_TIME / DEFERRED / TYPE_ONLY sans diagnostic inventé.
- [ ] Recommandations de fusion explicites au niveau des méthodes/fichiers concernés, avec coût, impacts et tests.

## Dépendances
- [PR #166](https://github.com/r9327/Dof-Atlas/pull/166) : meilleure pagination, consumer-sites et ID diagnostic.
- [PR #169](https://github.com/r9327/Dof-Atlas/pull/169) : provenance et déclenchements Graphify.
- [PR #173](https://github.com/r9327/Dof-Atlas/pull/173) : triage reachability / doublons Python et Doctor.
- [PR #165](https://github.com/r9327/Dof-Atlas/pull/165) : uniquement les fusions déjà démontrées.

Règles : HEAD réel, plan ciblé, tests prouvés et exact-SHA avant merge, pas de FULL/bench en boucle ni fusion de JSON.

## Premier correctif ciblé — cohésion Graphify (15/10/2026)

Le calcul `analyze_community_boundaries` pouvait inclure dans le ratio de cohésion
des arêtes entre nœuds `tools/`, `tests/` et nœuds de production membres des
mêmes communautés Leiden. Il comptait également plusieurs arêtes de symboles
pour une même paire de fichiers : ces deux facteurs gonflent artificiellement
la suggestion « fragmentation ». Ils ne démontrent aucun défaut runtime.

Le correctif proposé limite le ratio aux **paires distinctes de fichiers de
production Python** (code extrait), ignore les liens de symboles du même fichier,
et conserve `automatic_merge=False`. Régressions ciblées : trafic tests/outils,
doublons de symboles et véritables ponts entre fichiers `app/`.

**Important :** ce changement améliore le signal de triage ; il ne remplace
ni l'enquête des 496 communautés historiques, ni la preuve de non-utilisation.
Ce lot reste DRAFT jusqu'aux CI du SHA exact et à la revue nominative.
