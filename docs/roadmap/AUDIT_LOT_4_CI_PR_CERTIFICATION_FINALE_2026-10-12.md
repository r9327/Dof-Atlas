# Lot 4 — CI intelligente, nettoyage PR et certification finale

Statut : **PLAN PRÉPARÉ — CODE NON IMPLÉMENTÉ — NON CERTIFIÉ**.
Base de préparation `f6deb4a4fc8828ab9fc9372adc8653842303a7e9`. Dépendances : lots 1, 2, 3 terminés selon leurs critères ; ce lot **clôture** le chantier.
Règle : optimiser le *temps mur Windows*, pas supprimer les tests utiles.

## Situation GitHub vérifiée le 2026-10-12

PR ouvertes sur `r9327/Dof-Atlas` :
- #134 **Encyclopedia widgets lazy exports**, draft, mémoire/preload : relève du **Lot 3** pour évaluation/merge, ne pas dupliquer.
- #138 **PySide6 6.11.2 atomic lock**, ready : inclure au **Lot 4** seulement après validation Windows runtime, dépendances/hashes et impact Qt.
- #141 **Guide criterion cache** (ready), #142 **topological order and cache** (draft), #143 **FULL timing + Guide fixture reuse** (draft), #144 **Guide graph + FULL coverage** (ready), #145 **FULL test timing + cold Guide fixture copy** (draft), #146 **per-test FULL timing and fixtures** (draft).
Ces **six PR #141–#146 se chevauchent** (caches, topological sort, instrumentations, fixtures). Ne jamais les fusionner en bloc ni créer un 7e moteur de profiling. Elles peuvent être rebasées/fermées **uniquement après** revue de leurs diffs, vérification de dépendances, comparaison CI et provenance des correctifs intégrés.

## Travail exécutable

### L4.1 — Choisir les seules PR utiles
- [ ] Pour chaque #134, #138, #141–#146 : base/head réels, commits, diff par fichier et API publique, conflits, tests, comportement, gain mesuré, coût RAM, risques et recouvrement.
- [ ] Construire une matrice par capacité : cache de critères, tri topologique, Guide fixture/route cache, profilage unittest par test et fixtures, mutualisation exact-SHA, PySide6 lock, imports widgets lazy.
- [ ] Définir propriétaire unique de chaque amélioration et une PR "source of truth" : reprendre le **meilleur correctif prouvé** dans sa PR existante, rebaser sur main, vérifier compatibilité et tests, et fermer les doublons avec lien vers commit intégré.
- [ ] #134 est une dépendance du lot RAM ; coordonner, ne pas l'intégrer ici une deuxième fois.
- [ ] #138 reste indépendante de l'accélération FULL, ne pas lui attribuer les mêmes validations.

### L4.2 — FULL : profilage sans affaiblir l'intégrité
- [ ] Utiliser les durées de **la dernière FULL mesurée et valide** ; la certification rouge du SHA `f6deb4a4` a fourni 2 486 tests en **1 259,643 s** mais avec 3 échecs — c'est un profil de coût, **pas** une baseline certifiée.
- [ ] Relever latences setup/fixtures, données JSON, Guide builder, groupes DATA_INTEGRITY/GOLDEN_FLOWS, temps d'installation pip/Qt et temps total Actions.
- [ ] Comparer les vrais top 20 et causes d'initialisation répétées. Éliminer les calculs redondants **uniquement** si équivalence de sorties et suites prouvée.
- [ ] Mesurer absence de tests perdus : registre exhaustif test par test, `testsRun`, skipped, expected failures, mêmes assertions, même candidat SHA ; interdiction de synthétiser `FULL PASS` à partir de tests ciblés.
- [ ] Si parallélisation, isoler tests Qt/WebEngine, fixtures partagées, locks disque et mutation globale ; tester déterminisme/ordre; ne pas provoquer plus de contention RAM.
- [ ] Aucun benchmark FULL pendant développement quotidien ; **une certification exhaustive finale** seulement quand le lot est stabilisé ou quand les exigences de sécurité l'imposent.

### L4.3 — Doctor FAST/SMART/FULL et preuve de réutilisation
- [ ] Auditer `tools/phase_adaptive_gate.py`, `tools/doctor_certification.py`, `tools/atlas_full_suite_proof.py`, `tools/ci_scope_gate.py`, `tools/atlas_integrity.py`, `tools/doctor_github_provenance.py`, `tools/doctor_policy_authority.py`.
- [ ] Vérifier sur changements tests purs, code UI Qt, callbacks dynamiques, Guide data, policy/workflows, changements mixtes, SHAs inconnus : sélection attendue, refus fail-closed, provenance runner+workflow, empreintes dépendances et artefacts.
- [ ] Contrôler la réutilisation inter-jobs : même SHA, tests identiques et réellement exécutés, artefact authentifié ; invalider si fixture, environnement, dépendance, contrat ou SHA diffèrent. Ne jamais contourner la FULL de phase.
- [ ] Les workflows `.github/workflows/{doctor-certification,scoped-pr-ci,public-pr-ci,phase-certification,app-ci}.yml` doivent conserver les gates obligatoires et ne pas masquer le statut d'un job `skipped`.
- [ ] Comparer temps mur FAST/SMART/FULL avant/après avec frais d'installation et sans confondre durée unittest et durée workflow GitHub.

### L4.4 — Sécurité et robustesse finale
- [ ] Revoir sécurité transport/capture réseau, entrées externes, données JSON non fiables, chemin/fichiers, accès persistants, locks et transactions multi-instances.
- [ ] Métaintegrity, fault injection, mutation ciblée, ordre aléatoire et lifecycle soak selon le contrat DEEP ; étendre seulement quand la catégorie de changement le demande.
- [ ] Refaire vérification de présence des consommateurs des outils/compat, duplications, vieux wrappers, et supprimer **seulement** les éléments sans contrat ni appel réel.
- [ ] Aucune modification de hook Git/Graphify ou chaîne de confiance sans test contre une tentative de contournement.

### L4.5 — Clôture finale exacte et preuve audit
- [ ] Après intégration des lots, régénérer AI Context et Graphify sur le HEAD final, vérifier branch protection, check names et provenance.
- [ ] Exécuter Doctor FAST et ciblés, Windows journeys, Phase 8 memory/preload, Doctor DEEP là où imposé, FULL officielle exacte, phase verdict, puis App CI post-merge.
- [ ] Produire tableau final : SHA, run IDs, durée totale de chaque CI, nombre tests, verdict des gates, RAM stabilisée, pic process-tree, premier détail Succès, avertissements Guide, 18/18 Doctor, anomalies TRUE/FALSE/proofs, PR fermées.
- [ ] Zéro rouge **non expliqué** et zéro défaut prouvé non traité ; vérifications non exécutées restent `NOT_RUN` et jamais `PASS`.

## Documents et tests de référence

`PHASE_CERTIFICATION.md`, `DOCTOR_ADAPTIVE_CERTIFICATION.md`, `ROAD_IA.md`, `ZERO_TRUST_RULES.md`, `tools/atlas_full_suite_proof.py`, `tools/ci_scope_gate.py`, `tests/test_full_suite_structured_reuse.py`, `tests/test_ci_scope_gate.py`, `tests/test_phase_adaptive_gate.py`, `tests/test_doctor_github_provenance.py`, `tests/test_tool_audit.py`.

## Définition de terminé

- [ ] Toutes les 8 PR préexistantes ont une décision documentée (intégrée, maintenue, ou fermée avec preuve), sans suppression aveugle ni changement hors scope.
- [ ] CI plus rapide **si résultat mesuré**, FULL et protections maintenues ; aucune optimisation factice.
- [ ] Certifications officielles nécessaires exact-SHA `PASS`, preuve de tous les tests réellement exécutés, budgets inchangés.
- [ ] Rapport A→Z final avec limitations honnêtes et actions restantes, aucun faux PASS/vert synthétique.

## Hors périmètre

Ne pas reconstruire Doctor/Graphify de zéro, ne pas lancer simultanément six chantiers identiques sur la FULL, ne pas absorber les modifications Produit/Guide/RAM déjà prises en charge par les lots précédents.
