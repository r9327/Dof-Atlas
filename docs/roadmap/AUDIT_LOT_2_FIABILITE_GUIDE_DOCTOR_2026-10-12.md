# Lot 2 — Fiabilité du Guide, Doctor et parcours fonctionnels

Statut : **PLAN PRÉPARÉ — CODE NON IMPLÉMENTÉ — NON CERTIFIÉ**.
Base de rédaction `f6deb4a4fc8828ab9fc9372adc8653842303a7e9`. Dépendance de clôture : **Lot 1 certifié**.
PR #148 et #149 sont déjà fusionnées ; réutiliser leurs détecteurs plutôt que les remplacer.

## Inventaire d'entrée : signes, pas bugs prouvés

Artefacts d'audit antérieurs (SHA exact `faaaccea3178e1a4d5727d16732934fe67eb84ed` ; invalider/recalculer si le HEAD change) :
- **22 pistes Doctor/Graphify P3**, **0 import interdit confirmé** : aucun refactor autorisé sur simple compteur ;
- **6 nœuds isolés** (frontières/packages/scripts dans le rapport), **4 cycles différés/TYPE_CHECKING** : pas de code mort ou de panne démontré ;
- **141 observations de qualité des instructions Guide**, **204 avertissements prérequis**, zéro erreur dure dans le rapport source ancien ;
- contrôle spécifique post-#149 : reclasser et redédupliquer les alertes, inspecter chaque trajet et distinguer mentions dans `À préparer`, conditions de sortie et actions exécutables.
Les listes ne suffisent pas à autoriser une modification de route ; le scénario joueur et les prérequis métiers font foi.

## Travail exécutable, par ordre

### L2.1 — Guide Ultime : prérequis, sens de jeu, narration
- [ ] Régénérer les audits avec les outils **canoniques** `tools/audit_guide_ultime_manual_prerequisites.py`, `tools/audit_guide_ultime_action_quality.py`, `tools/audit_guide_ultime_manual_final_coverage.py`, sur même SHA après Lot 1 ; capturer JSON et signatures.
- [ ] Refaire l'inventaire des **22 alertes d'ordre historiquement encore à vérifier** ; ce nombre est **historique**, ne pas le présenter comme courant sans nouveau rapport. Vérifier chaque prérequis et les chemins conditionnels/transversaux complets, alternatives OR, gates temporaires, sources de progression ; pour chacune inscrire `TRUE` si bug reproduit, `FALSE` si faux positif démontré, `UNVERIFIED` tant que preuve insuffisante.
- [ ] Examiner d'abord les **18 conditions vagues**, puis les 123 autres remarques de rédaction : corriger les instructions ambiguës pour un joueur, éviter les reformulations qui changent l'ordre, la prise de quête, les items ou la complétion.
- [ ] Vérifier Lanyelle/Sylvestre, Wabbit, Xélorium, branches d'alignement, niveau 191–200 et 200+, registre temporel, Ocre, Dofus Nébuleux et conditions de sortie.
- [ ] Ne pas altérer `data/routes/guide_ultime_manual/manifest_v1.json` ou `canonical_lock_v1.json` sans preuve, contrats et certification du lot.

### L2.2 — Doctor et Graphify : 18 fonctionnalités réellement utilisables
- [ ] Construire une matrice **18/18 depuis les capacités effectivement exposées par `tools/atlas_doctor.py` et `tools/atlas_doctor_lib/capability_matrix.py`** : entrée CLI, code exécuté, sortie JSON, exemples, preuve test et limites ; ne jamais simuler un 18/18 par comptage de fichiers.
- [ ] Scénarios : imports statiques/dynamiques, callbacks & signaux Qt, workers, traces runtime, consommateurs réels depuis `DOFUS.bat` et fenêtres, nœuds isolés, communautés/bridges, duplications de responsabilités, cycles, hotspots, resource lifecycle, file coverage, simulations de refactor, blasts radius, source impact, test intelligence, scénario coverage, Graphify interactif, comparaison exact-SHA.
- [ ] Tester explicitement les fausses alertes, les absences de preuves, les graphes obsolètes, truncations et erreurs de parsing : conserver l'état interne `UNVERIFIED` même si l'interface de **correctifs confirmés** expose seulement TRUE/FALSE ; FALSE = défaut non démontré, jamais garantie de sûreté universelle.
- [ ] Doctor doit indiquer pour chaque correction proposée : règle, sévérité, source fichier/ligne, consommateur prouvé, contrat violé, reproduction, effet, tests et action concrète ; pas de proposition de suppression sans contrôle des consommateurs dynamiques.
- [ ] Examiner les 22 leads Doctor et statuer au cas par cas, pas un merge de communautés par heuristique ; tests : `tests/test_atlas_doctor_graph_audit.py`, `tests/test_atlas_doctor_graph_intelligence.py`, `tests/test_atlas_doctor_isolate_triage.py`, `tests/test_atlas_doctor_runtime_observation.py`, `tests/test_atlas_doctor_capabilities.py` et tests associés réels.

### L2.3 — Parcours fonctionnels bout-en-bout
- [ ] Windows/PySide6 : Quêtes → Guide → Succès → quête liée → Home → retour ; Lanyelle ; navigation précédent/suivant ; prérequis/recherche/tooltip ; progression/combats/étapes persistés par personnage.
- [ ] Vérifier les modules Équipement (WebEngine uniquement à l'ouverture), Organizer, Scan Monde, Zaap, et interactions navigation/macro sans créer de seconde source de vérité.
- [ ] Vérifier persistance multi-personnages `character:<id_dofus>`, plusieurs fenêtres/instances selon contrat, relance à froid, lecture en course et arrêt propre.
- [ ] Documenter la capture UI testée, les logs, le statut des callbacks/threads et les preuves de résultats ; tests fonctionnels et non simple import/smoke.

### L2.4 — Validation de lot
- [ ] Rejouer uniquement les tests ciblés pendant développement, construire Graphify exact-SHA seulement si changement structurel.
- [ ] Après stabilisation, exécuter les contrats Windows touchés, les gates CI exigés et la certification requise par `PHASE_CERTIFICATION.md` ; aucune modification de seuil ou `skip`.
- [ ] Joindre un registre de tous les signaux : `id/règle`, source exacte, `proven_defect: true|false`, `proof_status`, disposition, tests, commit correctif, retest ; rien n'est perdu même si les faux positifs n'apparaissent plus dans l'UI principale.

## Références

`GRAPHIFY.md`, `GUIDE_ULTIME_STATUS.md`, `DEVELOPMENT_GUARDRAILS.md`, `tools/atlas_doctor_lib/{integrated_investigation,graph_audit,isolate_triage,capability_matrix}.py`, `tools/guide_tools_cli.py`, `data/routes/guide_ultime_manual/`, `app/modules/encyclopedia/views/`.

## Définition de terminé

- [ ] Toutes les 18 capacités **réellement exercées**, retour exploitable, jeux de preuves positifs/négatifs.
- [ ] Alertes Guide requalifiées sur HEAD courant, vrais défauts corrigés, faux positifs expliqués ; **zéro anomalie confirmée laissée ouverte sans justification**.
- [ ] Parcours Windows de l'application validés et progression préservée.
- [ ] Aucun `TRUE` sans preuve, aucun `FALSE` utilisé pour masquer une incertitude, aucun code détruit sur graphe seul.
- [ ] Tests ciblés puis certification finale requise sur exact-SHA `PASS`.

## Hors périmètre

Pas d'optimisation structurelle RAM/perf sans mesures (Lot 3), pas de modification du moteur de sélection CI (Lot 4), pas de fusion avant Lot 1.
