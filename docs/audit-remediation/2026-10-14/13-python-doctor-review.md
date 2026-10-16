# Revue Python ciblée, 98 diagnostics Doctor et consumers dynamiques

> **Résultats du 16 octobre 2026.** Le plan historique ci-dessous reste traçable ;
> le registre de décision final distingue corrections, conservation et blocages.
> Les 898 fichiers ne sont pas certifiés sémantiquement par cette revue ciblée.

## Résultat final de ce lot

[98 décisions individuelles](13-doctor-decisions.json), sans suppression des IDs,
preuves ni statuts historiques. Base de revue et Graphify 0.9.72 :
`a88dcc1802e059259d5d053353504c43a31aad98` ; fichiers consommateurs et hashes
de source joints. Ce SHA intègre #172 et le correctif Graphify de #174.
La preuve finale CI porte sur le candidat publié, pas sur cette base d’analyse.

66 cas ont une décision de conservation ou un correctif déjà livré ; **32 restent
explicitement BLOCKED** : 17 parcours complets de workers, huit vérifications
visuelles et sept équivalences sémantiques de noms partagés. BLOCKED signifie
preuve manquante, pas défaut confirmé ni autorisation de supprimer.

Trois risques de verdict ouvert ont été reproduits jusqu’au caller : DR-016
retourne 2 même si le fichier de preuve périmé ne peut être effacé (PowerShell
exige également le code zéro) ; DR-017 reste BLOCKED devant protection GitHub
403/404 ; DR-018 impose FULL quand le plan Doctor est illisible. Les nouveaux
tests couvrent ces cas sans changer ou affaiblir les gates.

PC-09 : les sept modules widgets sont exposés par le contrat public lazy ;
tests de dispatch réel Qt et d’identité de type préservés. Les scans
`consumer-sites` des huit candidats atteignent leur budget : ils ne prouvent
pas l’absence de consumers. La revue manuelle de leurs entrées est dans
[le rapport Graphify](14-graphify-community-review.md).

PC-10 : les règles d’objectifs du calculator et du view model appellent toutes
deux `solution_objective`, dédoublonnent les IDs et préservent leur ordre.
Leur corps AST est identique ; comparaison exécutée sur les 1 976 vraies
quêtes publiques : zéro divergence des listes ordonnées d’objectifs.
PC-11 : `_sleep_ms` et `windows.timing.wait_ms` ont un corps AST identique,
y compris le test final d’arrêt et l’horloge monotone. **CONSERVER** ces
candidats facultatifs : aucun défaut ni gain mesuré n’impose une migration.
Les seules consolidations obligatoires AT-019/020 ont déjà été livrées par #165.

Validation locale : 95 tests Doctor/Graphify/policy et lifecycle, puis 24 tests
des trois gates incluant les nouveaux cas négatifs, et 20 contrats lazy/
réutilisation du ledger/profils/runtime manuel, tous réussis. Ces suites sont
des preuves ciblées ; elles ne remplacent pas une FULL Windows exacte-SHA.

Référence : [PR #160](https://github.com/r9327/Dof-Atlas/pull/160), SHA du code audité `ac07be9b894718f5e68e7c3a91016d7651e3065b`.

## Objectif
Compléter l'analyse sémantique ciblée du code Python et des avertissements Doctor que l'inventaire AST ne peut pas valider seul, sans inventer une absence de consommateurs.

## Périmètre à ne pas omettre
898 fichiers Python, 10 287 définitions inventoriées, 98 diagnostics DR, PC-09 et coopération PC-10/11

## Sources
- registres/python-files.json / python-symbols.json / doublons.json
- registres/diagnostics-doctor.json (98 : 12 FAUX POSITIF, 86 NON CONFIRMÉ)
- registres/signaux-callbacks-workers.json et ecritures-persistence.json
- app/modules/encyclopedia/widgets/__init__.py et widgets publics lazy

## Méthode et étapes
1. Relier chaque diagnostic DR à un sujet canonique, une fonction et des consumers vérifiés, en réutilisant les statuts déjà déterminés ; revoir les 86 NON CONFIRMÉ dans un ordre de risque.
2. Pour les 898 fichiers, prioriser propriétaires centraux runtime, persistance, Qt, réseau, data et workers ; AST seul n'atteste pas toutes les 10 287 branches.
3. Analyser callsites dynamiques/imports différés/Qt signals/slots/CLI/PS1 et faux positifs de code mort ; PC-09 : ne déprécier aucune façade lazy sans preuve consumer réel et compatibilité.
4. Regrouper les clones de fonctions uniquement si leur sémantique, effets de bord et policies sont égaux ; pour PC-10 et PC-11, instruire la parité puis laisser la correction à #165 si réellement justifiée.
5. Tester reachability depuis DOFUS.bat, launch, main, fenêtres et modules métiers, puis scénarios de destruction et débranchement ; l'absence dans une trace courte n'est pas preuve universelle.
6. Classer constats par CONFIRMÉ / PROBABLE / NON CONFIRMÉ / FAUX POSITIF, avec file:line, reproduction, blast radius et critère de correction ; aucune suppression sans evidence.
7. Distinguer analyse ciblée menée ici et exhaustivité sémantique impossible ; éviter de refaire Doctor #166 pour la mécanique de pagination/ID.

## Sortie vérifiable
- [x] 98 DR individuellement conservés dans le registre de décision, dont 86 investigués ou explicitement BLOCKED
- [ ] Candidats Python à fusion/suppression avec consommateurs et tests ; rien supprimé d'après un seul degré
- [x] PC-09/10/11 documentés ; évolution dans #165 ou une PR de correction après preuve
- [ ] Sorties de couverture réelles et insuffisances clairement visibles pour tous les fichiers

## Dépendances et conflits à éviter
#166 possède moteur Doctor (IDs, lazy exports, pagination) ; #165 possède refactor partagé ; #169 possède routage Graphify ; ne pas dupliquer ces changements.

## Règles
- Lire le HEAD réel, les consumers et le registre original avant action ; preuve datée exact-SHA.
- Tests ciblés uniquement pendant les analyses/développement. FULL conditionnelle finale après stabilisation.
- Conserver sources, données, IDs, état joueur, boundaries lazy et caches jusqu'à preuve contraire.
- Le statut NON CONFIRMÉ n'est pas un défaut garanti ; consigner les environnements indisponibles.
- Aucune fusion/merge tant que le travail effectif n'est pas réalisé.

## Premier résultat prouvé — exports lazy publics (15/10/2026)

En comparant `DR-030` à `DR-036` avec `app/modules/encyclopedia/widgets/__init__.py`,
les sept modules sans import direct sont présents dans la table
`_LAZY_EXPORT_MODULES` et leurs symboles dans `__all__`, avec `__getattr__`.
Ce sont des **exports publics**, pas des preuves d'exécution ni du code mort.

Correction de l'analyse Doctor : `unreferenced_module` n'est plus émis pour
une façade lazy effectivement prouvée par AST ; les modules réellement sans
entrée statique ou lazy restent des candidats `suspect`. Aucun widget Qt
importé pour cette vérification. Test positif et négatif dans
`tests.test_atlas_doctor`. Les 86 avertissements historiques du registre
ne sont pas effacés : la décision de l'audit original reste traçable.

**Reste à faire :** traiter individuellement les autres cas DR, consumer-sites
runtime et priorités Python. Ne pas revendiquer la clôture des 898 fichiers.


## Seconde vérification — façade dynamique *réellement* branchée (15/10/2026)

Le premier correctif DR-030…036 n'exigeait que la présence d'une
`_LAZY_EXPORT_MODULES`, de `__all__` et d'un `__getattr__` quelconque.
Un `__getattr__` qui lève systématiquement `AttributeError` suffisait
donc à supprimer le warning `unreferenced_module`, alors que son export
n'était pas utilisable.

Correction : inspecter le corps AST du `__getattr__` et exiger au minimum
qu'il référence à la fois la table `_LAZY_EXPORT_MODULES` et
`import_module`. Un `__getattr__` muet garde le statut suspect ;
la façade réelle de `encyclopedia/widgets` conserve son contrat lazy.
Ce contrôle prouve **une structure de dispatch statique**, pas que la branche
s'exécute, ni qu'un widget est affiché. Aucun import Qt n'est exécuté.

### Triage ciblé des diagnostics restants

- DR-011 (`atlas_full_suite_proof.py:101`) : l'exception
  `ValueError` concerne explicitement le `_ErrorHolder` de
  `unittest`, qui ne désigne pas un vrai `TestCase`. Suppression du
  diagnostic sans changement de comportement déconseillée ; signal
  **FAUX POSITIF ciblé**, à distinguer du registre historique.
- DR-012 (`atlas_integrity.py:630`) : écriture facultative des
  breadcrumbs. Un `OSError` est volontairement non bloquant pour
  préserver l'autorité du verdict de certification. **FAUX POSITIF ciblé**.
- DR-013/014/015 (`benchmark_phase8_memory.py` et
  `benchmark_phase8_preload.py`) : mutations de `sys.path` visibles,
  utilisées par ces entrypoints de mesure. **NON CONFIRMÉ** comme défaut ;
  réécrire les imports sans reproduire les commandes Windows risquerait
  de casser les benchmarks.
- DR-016 (`ci_guide_full_evidence.py:215`) : l'`unlink` tente
  d'enlever une preuve réutilisable après erreur et finit en code 2,
  donc la réutilisation devrait être refusée par le consommateur. Le
  comportement si `unlink` échoue et qu'un ancien fichier persiste
  nécessite un scénario appelant. **NON CONFIRMÉ**, test de refus de
  preuve stale à prévoir.
- DR-017 (`doctor_policy_authority.py:151`) : exception d'API HTTP
  ignorée, permettant de revenir à une protection signalée non activée.
  Le sens du verdict et l'échec en mode stricte doivent être testés
  face à 403/404. **NON CONFIRMÉ**.
- DR-018 (`phase_adaptive_gate.py:181`) : absence de plan après
  chargement raté ; la décision d'acheminement doit être FULL_REQUIRED.
  Test de la politique `choose_route` requis avant verdict.
  **NON CONFIRMÉ**.

Ce triage n'efface aucun diagnostic historique : il explicite les
cas examinés et les preuves encore nécessaires.


### Couverture négative complémentaire

Le `__getattr__` ne doit pas seulement **mentionner** `import_module` :
Doctor exige désormais un appel AST `import_module(...)` et une lecture de
`_LAZY_EXPORT_MODULES`. Les fixtures couvrent la façade fonctionnelle,
la façade muette et le faux dispatch qui attribue simplement
`import_module = None`. Ce signal reste statique, jamais assimilé à une
preuve d'exécution Qt.
