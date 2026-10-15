# [PLAN 13] Revue Python réelle, 98 diagnostics Doctor et consumers dynamiques

> **PLAN PRÉPARATOIRE — zéro correctif implémenté ici.** Aucun constat non confirmé ne doit être promu en bug sans reproduction.

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
- [ ] 98 DR individuellement conservés dans le registre de décision, dont 86 investigués ou explicitement BLOCKED
- [ ] Candidats Python à fusion/suppression avec consommateurs et tests ; rien supprimé d'après un seul degré
- [ ] PC-09/10/11 documentés ; évolution dans #165 ou une PR de correction après preuve
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
