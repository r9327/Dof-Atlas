# Revue des communautés et candidats Graphify

> Résultats du 16 octobre 2026, regroupés dans #173 avec la revue Doctor.
> Le plan historique est conservé ci-dessous ; aucune suppression ou fusion
> de code produit n’est déduite des métriques seules.

## Résultat et couverture réelle

[Registre nominatif](14-graph-decisions.json), Graphify 0.9.72 sur le candidat
propre `a88dcc1802e059259d5d053353504c43a31aad98`, avant les nouvelles preuves
et tests de ce lot. Le périmètre tooling examiné compte 103 nœuds / 341 arêtes.
Le graphe entier compte 13 215 nœuds / 38 459 liens et 483 communautés.

Les 496 communautés historiques sont rapprochées par **chemins de fichiers**,
avec les absences explicites. Les 483 communautés courantes ont leur liste de
membres et une empreinte stable de cette liste : leurs numéros Leiden ne sont
pas des identités persistantes. La décision de conservation ne prétend pas que
toutes leurs fonctions ont subi une revue sémantique.

104 communautés isolées et 334 nœuds faibles sont exportés sans troncature,
avec décision **INVESTIGATION BLOQUÉE** sur l’identité des bindings dynamiques,
la reachability complète et l’absence de gain mesuré. Ce sont des pistes ouvertes,
pas des anomalies garanties ni des suppressions prouvées. Les 64 candidats de
cohésion courants restent sans fusion ; le compteur historique de 76 ne peut
pas être remplacé par ces nouveaux IDs (sa liste nominative n’est pas dans
`graph-all-candidates.json` archivé).

Quatre cycles vérifiés dans les sources courantes : runtime/macros avec retour
TYPE_ONLY ; vue manuelle/shared avec import DEFERRED ; guides/détail de quête
avec import DEFERRED ; catalogue/détails avec import DEFERRED. **Zéro sous-cycle
IMPORT_TIME confirmé** par l’analyse AST ; cela ne certifie pas les imports
dynamiques. Aucun import runtime app → tools confirmé.

Les six orphelins de degré zéro sont conservés avec leur entrée réelle : deux
`__init__.py` de packages, `graphify.ps1` et `install_git_hooks.ps1` documentés
dans AGENTS/GRAPHIFY, `pre_commit.ps1` et `pre_push.ps1` appelés par `.githooks`.

### Huit candidats de suppression : consommateurs vérifiés

| Fichier | Consumer source confirmé ; décision CONSERVER |
|---|---|
| `app/distribution/health.py` | `main.py:2666`, import différé `announce_ready` |
| `services/link_service.py` | table lazy `services/__init__.py:72`, `guides_view.py:1156` construit LinkService |
| `widgets/progress_card.py` | table publique `_LAZY_EXPORT_MODULES` et `__all__`, contrat lazy testé |
| `app/preload.py` | `main.py:60` importe PreloadTask/StartupPreloader, tests et introspection |
| `app/startup_cache_warmup.py` | `DOFUS.bat:67` et `launch.py:133`, entrée `-m` |
| `app/startup_preflight.py` | `DOFUS.bat:47`, entrée `-m` et tests preflight |
| `app/ui/splash_image.py` | `main.py:66`, helper de splash et test dédié |
| `app/windows/single_instance.py` | `main.py:69`, mutex avant QApplication ; probe multi-processus #171 |

Les huit scans automatiques `consumer-sites` ont atteint leur budget : leur
absence de relation retournée ne remplace pas ces consumers manuels vérifiés.
Les limites sont conservées dans le registre ; aucune preuve de code mort.

Correctifs de l’outil : cohésion calculée sur paires distinctes de fichiers
runtime (y compris local_dofus_data/launch/sitecustomize), exclusion du bruit
tests/tools et pagination indépendante `--cohesion-offset`. Les cas négatifs
et l’union exacte de pages sont testés. Aucun refactor applicatif, migration,
nouveau cache ou gain RAM prétendu ; les blocages natifs restent dans #175.

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


## Complément ciblé — composants runtime hors `app/` (15/10/2026)

Le premier filtre de cohésion traitait `app/` et `main.py` comme seuls
composants Python de production, ce qui omettait les fichiers chargés depuis
`local_dofus_data/` et les entrypoints `launch.py` et
`sitecustomize.py`. Le correctif limite toujours les rapports aux
paires distinctes de fichiers runtime et exclut `tools/` et `tests/`,
sans modifier les autres diagnostics qui utilisent `_production()`.
Un test injecte volontairement vingt liens venant de `tools/`
et six liens runtime distincts ; seuls ces six comptent.

### Quatre cycles du graphe historique : décisions sourcées

Les quatre cycles ci-dessous sont tirés du chapitre 5 de l'audit
`AUDIT_INTEGRAL_DOFUS_ATLAS_2026-10-14.md`, construit sur
`main@ac07be9b`. Ils sont **historiques**, pas une certification du
runtime actuel après corrections :

| Famille | Portée établie dans l'audit original | Décision |
|---|---|---|
| `runtime_state ↔ macros` | imports de macros DEFERRED, retour TYPE_ONLY | CONSERVER, cold start et tests de modules préservés |
| `guide_ultime_manual_view ↔ shared_manual_guide_view` | au moins un import DEFERRED | CONSERVER, la façade protège les consumers |
| `guides_view ↔ quest_detail_view` | chemins DEFERRED | CONSERVER, détail chargé à la demande |
| `quest_catalog ↔ quest_catalog_details` | séparation de l'accès metadata/détails | CONSERVER, pas de panne IMPORT_TIME prouvée |

Un nouveau test exact-SHA de cycle IMPORT_TIME réel serait nécessaire
pour changer ces décisions. Ne pas transformer les cycles en bugs ou
supprimer la façade pour améliorer un compteur.

### Groupes historiques déjà classés

| Communauté(s) | Décision | Motif |
|---|---|---|
| 1, 5 | CONSERVER | modèle, infrastructure transverse et hooks; regroupement statistique |
| 2 | CONSERVER | catalogue/détails et chargement différé distincts |
| 4 | CONSERVER | pipeline capture/sécurité, frontières utiles |
| 7 | CONSERVER | Craft/Organizer partagent des primitives, pas un seul propriétaire |
| 21 | CONSERVER | UI/service/store persistance séparés |
| 276, 359, 396, 415, 416, 419, 438 | NON SUPPRIMABLE d'après le seul graphe | nœuds isolés dans des fichiers effectivement connectés |

Les 496 communautés et 76 candidats n'ont **pas** été vérifiés
individuellement au HEAD courant : le registre complet de l'archive #160
reste la source, et les prochains triages doivent disposer des membres,
consumers et tests, pas seulement d'un score Leiden.


## Pagination sans reconstruction répétée — 15/10/2026

La section `community_cohesion` ne publiait que `candidates[:30]` même
si `--community-offset` paginait déjà les **communautés isolées**
(autre section). Un examen réparti en pages faisait donc perdre des
candidats de cohésion après la première page.

L'API `analyze_community_boundaries(..., offset=...)` et la CLI
`graph-audit --cohesion-offset N` exposent maintenant la tranche,
le total et la troncature de **cette** section. Le graphe est lu et
validé une fois par commande, et peut être réutilisé par l'appelant
pour paginer sans relancer `graph --rebuild`. Un test négatif refuse
offset négatif ou limite nulle ; un test à 35 candidats vérifie
l'union exacte des pages sans répétition. Les décisions restent
advisory ; aucune fusion/suppression automatique.
