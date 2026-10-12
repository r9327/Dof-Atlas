# Lot 1 — Stabilisation de main, tests FULL et certification

Statut vérifié le 12 octobre 2026 : **STABILISATION FUSIONNÉE, FULL ET PHASE PASS, APPLICATION CI POST-MERGE PASS**.

> Les cases non cochées et les références « plan préparé » des sections historiques ci-dessous sont la photographie du chantier **avant exécution**, conservée pour traçabilité. Le verdict final est documenté dans la section « Clôture certifiée et limites » en fin de fichier.
Dépôt : `r9327/Dof-Atlas` ; base de préparation : `f6deb4a4fc8828ab9fc9372adc8653842303a7e9` (2026-10-12).
Dépendances : **aucune** ; lot prioritaire, bloque les lots 2 à 4 pour leur clôture.
Responsabilité : restaurer des verdicts fiables sans désactiver un seul contrôle.

## Preuves observées sur la base exacte

- Phase Certification, workflow [38241991428](https://github.com/r9327/Dof-Atlas/actions/runs/38241991428), **failure**. La FULL a réellement exécuté **2 486 tests**, dont **3 échecs** (1 259,643 s de suite de tests). Les traces de `tests/test_ai_context.py` confirment notamment `test_drift_warns_without_blocking_unknown_routes` (`index_current=False`) et une comparaison d'index qui diverge. **Extraire les trois noms exacts** du `05_full_unittest.log` avant tout correctif ; ne pas inférer le troisième.
- L'intégrité FULL signale `FULL_SUITE_FAILED`. Le verdict de phase rejette logiquement les preuves : il ne faut pas corriger le verdict lui-même.
- Application CI [38245860466](https://github.com/r9327/Dof-Atlas/actions/runs/38245860466) et [38242020819](https://github.com/r9327/Dof-Atlas/actions/runs/38242020819) : `BLOCKED: no reusable authenticated exact-SHA Phase FULL`. Il s'agit d'un blocage **en aval** de la certification, pas de la preuve autonome d'un second bug applicatif.
- Le rapport de phase signale `Guide baseline owners changed`, `manifest status changed: expected BUILDING, got CERTIFIED`, `prerequisite baseline fingerprint drift`, `final coverage baseline fingerprint drift`, `state_counts.partial/uncovered missing`. Déterminer ce qui provient de la référence gelée historique et ce qui est un vrai écart métier.
- PR #148 et #149 déjà fusionnées, respectivement filtres Doctor et correction du détecteur d'ordre ; **ne pas revenir en arrière**.

## Plan initial — travail prévu (historique avant livraison)

### L1.1 — Localiser précisément la cause des 3 échecs FULL
- [ ] Récupérer HEAD réel, `git status --short`, brancher sur cette PR existante ; regarder les artefacts `phase-certification-38241991428-1` et le `05_full_unittest.log` complet.
- [ ] Reproduire isolément les 3 tests échoués, en comparant le SHA `faaaccea` vert précédent et le SHA actuel ; distinguer contenu indexé, génération, ordre de tests, environnement Windows et cache stale.
- [ ] Revoir `tools/ai_context.py`, `.ai/context_index.json`, `tests/test_ai_context.py`, les règles de régénération et les hooks Git. Si l'index est généré, corriger son producteur et la synchronisation plutôt qu'un snapshot à la main.
- [ ] Ajouter tests anti-régression reproduisant la cause, puis réexécuter les tests ciblés en lot unique. Aucun `skip`, `xfail`, suppression de test, timeout artificiel ou relâchement d'assertion.

### L1.2 — Contrats Guide protégés et baseline figée
- [ ] Comparer `data/routes/guide_ultime_manual/manifest_v1.json`, `canonical_lock_v1.json`, `success_contracts_v2.json`, les chapitres canoniques, et `GUIDE_ULTIME_STATUS.md` aux attendus et preuves sur SHA courant.
- [ ] Contrôler `tools/phase_certification_verdict.py`, `tools/audit_guide_ultime_manual_prerequisites.py`, `tools/audit_guide_ultime_manual_final_coverage.py` et l'origine de la baseline figée (owners, empreintes, décomptes).
- [ ] Déterminer et consigner pour chaque drift : `TRUE_DEFECT` avec reproduction ou `BASELINE_STALE` avec preuve d'évolution métier approuvée ; ne jamais changer la baseline uniquement pour obtenir du vert.
- [ ] Assurer le maintien des 13 chapitres, 267 macro-fiches de référence **si c'est bien la route officielle de ce HEAD**, et l'absence de perte de données ou de progression ; ne pas forcer ces chiffres comme une règle figée.
- [ ] Comparer le verdict du Guide, l'intégrité DATA/FINAL_COVERAGE et la preuve shadow exact-SHA.

### L1.3 — Lifecycle Encyclopédie sous Windows
- [ ] Cibler `tests/test_encyclopedia_phase1.py` (worker en fin de test), `tests/test_atlas_window_runtime_cleanup.py`, `tests/test_qt_async_non_accumulation.py`, `app/modules/encyclopedia/views/encyclopedia_page.py`.
- [ ] Vérifier fermeture Guide/Succès/Quêtes, signaux, locks `quest_progress.json.lock`, destruction de widgets, callbacks Qt, timers et threads ; prouver qu'un test de fixture rapide ne masque pas une fuite de production.
- [ ] Pas d'allongement arbitraire de timeout ni de destruction forcée au risque de perte de progression ; privilégier ownership, arrêt, événement fini et join borné lorsqu'un défaut réel est prouvé.

### L1.4 — Rétablir la chaîne de certification
- [ ] Faire passer les tests ciblés sur un seul SHA, avec `py -3.13 -m tools.ai_context status`, `py -3.13 -m tools.atlas_doctor quick` puis routes sélectionnées.
- [ ] Après code stabilisé seulement, lancer les vérifications obligatoires : Doctor FAST, Graphify exact-SHA si architecture touchée, AI Context, UI Windows et **une FULL requise sur ce SHA**.
- [ ] Vérifier `Phase Certification / Full Validation` vraiment `PASS` et artefact authentifié ; vérifier ensuite le chemin post-merge de réutilisation exact-SHA de `Dofus Atlas Application CI`.
- [ ] En cas de FAIL, réparer la cause puis revalider le SHA modifié ; ne pas réutiliser une preuve d'un autre commit.

## Références et points d'entrée

`PHASE_CERTIFICATION.md`, `DOCTOR_ADAPTIVE_CERTIFICATION.md`, `GUIDE_ULTIME_STATUS.md`, `tools/atlas_full_suite_proof.py`, `tools/phase_certification_verdict.py`, `tests/test_ai_context.py`, `.github/workflows/{phase-certification,app-ci,ai-context-ci}.yml`.

## Définition de terminé — critères planifiés (historique)

- [ ] Chaque échec de la FULL reproduit/corrigé, avec régression ciblée ; résultat exhaustif `PASS`, 0 test perdu.
- [ ] Contrats Guide et fingerprints expliqués et conformes, aucun faux relâchement de baseline.
- [ ] Cycle de vie Qt vérifié ; ressources détruites et fichiers temporaires libérés.
- [ ] Certification Phase exacte du SHA `PASS`, puis Application CI `PASS` et preuves post-merge si fusion.
- [ ] Les logs/JSON exact-SHA, le nombre de tests, la durée et le résultat sont joints à la PR.

## Hors périmètre

Pas d'optimisation FULL concurrente avec #141–#146, pas d'audit cosmétique Graphify, pas de refactor massif du Guide, pas de hausse des budgets RAM. Les lots 2–4 sont **bloqués pour leur fusion finale** tant que Lot 1 n'est pas fiable.

## Exécution vérifiée — 12 octobre 2026

- Commit correctif [124a5b8c](https://github.com/r9327/Dof-Atlas/commit/124a5b8c8e2b865a578dbee55b665a0f669793a8) : régénération exacte de l'index AI Context (30/30 top-level Git tree), CI de fraîcheur universelle à chaque PR, test anti-régression et trace intégrale `05_full_unittest.log` en cas de FULL échouée (supprimée si succès). AI Context [38265550026](https://github.com/r9327/Dof-Atlas/actions/runs/38265550026), Doctor FAST et Graphify focalisé : PASS.
- La FULL initiale [38241991428](https://github.com/r9327/Dof-Atlas/actions/runs/38241991428) prouve 2 486 tests et 3 échecs ; ses sorties n'incluent que les 40 dernières lignes et l'artefact ne contient pas `05_full_unittest.log`. Deux assertions AI Context sont identifiées ; **le troisième nom exact reste inconnu**, à extraire d'une prochaine FULL échouée si nécessaire. Ne pas inventer le troisième.
- Audits Guide du SHA `f6deb4a4` : `ci_summary=PASS`, 17/17 contrôles, prérequis `COMPLETE_BY_PROVIDER_ORDER`, 0 erreur dure, 267 étapes, 1 976 quêtes ; couverture `COMPLETE_BY_EVIDENCE`, 1 418 succès, 13 chapitres et 267 étapes. Les 1 418 états sont répartis en `covered_all_linked_entities=691` et `covered_direct_success=727`. Les anciens champs `partial`/`uncovered` du freeze Phase 2 ne représentent plus ce contrat actuel. Le verdict ne consulte le freeze que quand l'intégrité FULL est bloquée ; **ne pas modifier le freeze pour le faire passer**.
- Rapport `ASYNC_LIFECYCLE=PASS` sur 36 tests Windows. Aucune fuite worker de production prouvée ; analyse runtime approfondie encore à confirmer. Aucun timeout étendu ni destruction forcée.
- **État : CODE PARTIEL + TESTS CIBLÉS PASS. NON CERTIFIÉ.** Restent les validations spécifiques Windows, une FULL vraie sur le SHA final, l'identification de tout échec restant, et le chemin post-merge exact-SHA. Pas de fusion avant ces preuves.


## Clôture certifiée et limites — preuves GitHub exact-SHA (12/10/2026)

**Statut du lot 1 : STABILISATION LIVRÉE ET CERTIFIÉE.** PR [#152](https://github.com/r9327/Dof-Atlas/pull/152) **fusionnée** par merge commit `9c32a0130f83de74c5510631d6447dc5450e7ec8`.

| Contrat | Résultat vérifié | Preuve |
| --- | --- | --- |
| Correctifs AI Context et garde de synchronisation d'index | Implémentés, tests anti-régression ajoutés | Commit [a1918b9b](https://github.com/r9327/Dof-Atlas/commit/a1918b9b66ce2dbd0f43b9ba2f4cc57736703276) et vérifications AI Context |
| FULL du candidat | **PASS**, 2 487 tests (le point de départ en avait 2 486 et trois échecs) | [Phase Certification 38266201839](https://github.com/r9327/Dof-Atlas/actions/runs/38266201839) sur `a1918b9b` ; artefact `phase-certification-38266201839-1` |
| Verdict Guide réel | **GUIDE_CERTIFIED**, `raw_integrity_verdict=PASS`, `baseline_debt=[]`, `errors=[]` | Verdict de phase dans [38266201839](https://github.com/r9327/Dof-Atlas/actions/runs/38266201839) ; baseline gelée Phase 2 **non modifiée** |
| Certification après fusion | **PASS**, FULL 2 487 tests sur le merge commit | [Phase Certification 38268360659](https://github.com/r9327/Dof-Atlas/actions/runs/38268360659) ; artefact `phase-certification-38268360659-1` |
| Validation rapide de `main` | **PASS** | [Application CI 38268360662](https://github.com/r9327/Dof-Atlas/actions/runs/38268360662) |
| Réutilisation FULL authentifiée et lifecycle Qt en même processus | **PASS**, **76 tests** exécutés, catalogue de **1 976 quêtes** | [Application CI / workflow_run 38271738654](https://github.com/r9327/Dof-Atlas/actions/runs/38271738654) |

**Ancien échec FULL :** le troisième nom de test en échec dans la run 38241991428 demeure indéterminable à partir des anciennes sorties tronquées ; ne pas le deviner. Les trois échecs ne se reproduisent plus dans les deux FULL finales vertes. La correction de `tools/atlas_integrity.py` conserve désormais les logs FULL complets **en cas de nouvel échec**, sans les recopier inutilement après succès.

**Baseline Guide :** les dérives signalées par comparaison au gel historique `BUILDING` ne sont pas, à elles seules, des défauts du contrat Guide actuel `CERTIFIED`. Les prérequis actuels (0 erreur dure, 267 étapes et 1 976 quêtes), la couverture des 1 418 succès et les audits du Guide sont validés par la certification de phase, sans déverrouiller le gel. Aucune régression Guide n'est attestée par ces rapports.

**Cycle de vie :** les 36 tests `ASYNC_LIFECYCLE` et les 76 tests intégrés post-fusion sont PASS. Ils apportent une preuve des contrats automatisés Qt (workers/fermeture/navigation) mais **ne prouvent pas l'absence de fuite mémoire dans une longue session réelle** ; cette dernière relève du lot 3 (RAM/runtime). Aucun problème de production spécifique supplémentaire n'a été prouvé dans ce lot et aucun assouplissement artificiel de timeout n'est utilisé pour clore ce dossier.

**Après le lot 1 :** le correctif séparé [#154](https://github.com/r9327/Dof-Atlas/pull/154) a supprimé le `--force-full` récurrent sur `main` et a lui aussi passé sa certification post-fusion [38272560359](https://github.com/r9327/Dof-Atlas/actions/runs/38272560359). Ce travail supplémentaire n'est pas un changement du périmètre initial du lot 1.

Les validations ayant déjà été exécutées et authentifiées sur les SHA cités, **ne pas relancer de FULL** pour une simple mise à jour documentaire de cette clôture.
