# [PLAN 06] Doctor preuves fiables, pagination et exports lazy (AT-013/014/015/016/028)

> PLAN PRÉPARATOIRE — aucun correctif applicatif implémenté ici. PR DRAFT à compléter en code et tests ciblés avant revue/fusion.

Audit source : PR #160, SHA audité `ac07be9b894718f5e68e7c3a91016d7651e3065b`. Branche de base : `main` ; éviter de mélanger les modifications de PR #159 et #138.

## Objectif
Rendre Doctor exact dans l’identité et la couverture de chaque constat, en séparant détection statique, preuve réelle et absence de preuve.

## Dépendances et ordre
Peut avancer après 01 ; rattacher les témoins d’intégration réels ; coordonner contrats hash avec provenance Git.

## Constat et preuves détaillées
### AT-013 — Les contrats des gros JSON dépendent des fins de ligne Windows
- Priorité / état : P2 / CONFIRMÉ / main.
- Localisation : data/large_file_contracts.json:6 sha256 de quests_enriched; data/large_file_contracts.json:19 sha256 de image_manifest; tools/atlas_doctor_lib/audit.py:395 _validated_large_file_contracts; tools/atlas_json_inventory.py:24 _sha256; .gitattributes:1 text=auto.
- Cause : Les empreintes du contrat sont celles des fichiers CRLF, alors que Git fournit LF ici. Doctor et l’inventaire affichent deux contrats invalides sur le même contenu logique du commit.
- Preuve audit : SHA LF quests=e6d7c5b90ced5768c4b4f4b044146c9928bef23286547001ae0cff97a75bf165 ; image=c2c32139d1a6d14cb77936aa586b7a34fcf3a0525e395c882f0902e6e9b6729d. Conversion LF→CRLF reproduit exactement les deux empreintes attendues. Faux positif de corruption, vrai défaut de portabilité du contrat.
- Correction du registre : Choisir une représentation byte canonique explicite (eol=lf pour ces JSON et régénération autorisée des empreintes) ou un hash du blob Git canonique clairement séparé de l’intégrité disque. Éviter un hash JSON sémantique qui pourrait masquer une corruption.

### AT-014 — Deux diagnostics distincts partagent le même identifiant Doctor
- Priorité / état : P2 / CONFIRMÉ / main.
- Localisation : tools/atlas_doctor_lib/core.py:29 Issue.id; tools/atlas_doctor_lib/audit.py:713 émission invalid_large_file_contract.
- Cause : L’ID ne contient que rule/path/line/title. Les deux entrées de large_file_contracts.json ont toutes ces valeurs identiques et donc le même ID, malgré des cibles différentes. Une comparaison/indexation par ID peut les écraser.
- Preuve audit : doctor-fast-py313.json contient deux erreurs files[0]/files[1] avec id=cad8e520683a3aee. La collision est prouvée ; une perte effective dans une UI particulière n’est pas prétendue.
- Correction du registre : Ajouter un sujet stable (chemin du fichier contracté ou JSON pointer de l’entrée) à l’identité. Garder l’identité stable quand le texte de preuve/digest change.

### AT-015 — La découverte de consumers ne résout pas les façades lazy pourtant explicites
- Priorité / état : P2 / CONFIRMÉ / main.
- Localisation : tools/atlas_doctor_lib/consumer_sites.py:55 inspect_consumer_sites; app/modules/encyclopedia/widgets/__init__.py:16 _LAZY_EXPORT_MODULES; app/modules/encyclopedia/widgets/__init__.py:104 __getattr__.
- Cause : Pour GuideStepWidget le rapport n’établit aucun consumer statique, cite l’import f-string comme UNKNOWN_TARGET et s’arrête à 120 fichiers sur 176 candidats. La table littérale locale indique pourtant exactement le module exporté. Cela ne prouve pas que ce widget est utilisé dans un parcours produit, mais permet de prouver l’exposition publique.
- Preuve audit : consumer-lazy-widget.out et façade relue : GuideStepWidget→guide_step_widget. Les sept alertes unreferenced_module concernent des modules exportés dans la même table. Tests des exports lazy PASS ; aucun de ces fichiers n’est déclaré mort dans ce rapport.
- Correction du registre : Compléter l’analyse AST par la résolution limitée des dictionnaires littéraux de façades du dépôt ; étiqueter PUBLIC_LAZY_EXPORT séparément de RUNTIME_CONSUMER. Garder l’état REVIEW pour les appels réellement dynamiques ; proposer une pagination/partition des candidats.

### AT-016 — La CLI Graph-audit masque une partie des communautés candidates
- Priorité / état : P2 / CONFIRMÉ / main.
- Localisation : tools/atlas_doctor.py:700 graph-audit parser; tools/atlas_doctor_lib/graph_audit.py:54 inspect_graph; tools/atlas_doctor_lib/graph_audit.py:235 sections paginées; tools/atlas_doctor_lib/graph_intelligence.py:484 analyze_community_boundaries.
- Cause : La CLI expose --offset pour les weak nodes seulement ; inspect_graph permet pourtant community_offset/orphan_offset. La cohésion et le plan limitent aussi l’affichage à 30. Un seul graph-audit --deep n’est pas l’exhaustivité annoncée par une utilisation superficielle.
- Preuve audit : graph-audit-0.json/limits : 334 candidats weak, 107 communautés isolées, 77 communautés non rapportées. La pagination API a été effectuée dans cet audit ; graph-all-candidates.json et graph-communities.json contiennent toutes les sections. Il ne s’agit pas de 107 défauts.
- Correction du registre : Exposer les offsets de sections existants ou un export intégral borné explicite. Marquer la troncature et le total dans chaque section ; réutiliser un graphe chargé une seule fois, sans refaire une lourde recherche globale par page.

### AT-028 — Le catalogue heuristique sous-estime l’intégration des scénarios Doctor
- Priorité / état : P2 / CONFIRMÉ / main.
- Localisation : tools/tool_audit.py:1 audit heuristique; tools/tool_catalog.py:85 _literal_tool_spec; tools/atlas_doctor.py:1 UI_SCENARIOS; tools/atlas_doctor_lib/app_ui_smoke_scenario.py:1 main; tools/atlas_doctor_lib/encyclopedia_deferred_smoke.py:1 main.
- Cause : tool-audit déclare les scénarios non référencés/sans tests ciblés et deux comme mutation sans gate. Ils sont pourtant routés par capture-ui, testés et exigent un active_observer ; leurs écritures sont des fixtures temporaires. Les diagnostics heuristiques sont annoncés advisory, donc ne doivent pas autoriser une suppression.
- Preuve audit : tool-audit.json ; quatre captures effectivement enregistrées, tests.test_atlas_doctor_capture_ui, *_app_ui_smoke, *_encyclopedia_smoke PASS et source des scénarios relue. La preuve invalide l’absence d’usage de ces quatre scénarios, pas celle de tout outil classé heuristic.
- Correction du registre : Ajouter les contrats explicites/relations de routage aux seuls entry points récurrents mal classés ; distinguer fixture temporaire de mutation du dépôt canonique. Ne pas recopier une seconde liste de commandes dans le skill.

## Implémentation attendue
1. AT-014 : former l’Issue.id à partir de la règle, du chemin, de la localisation et d’un sujet stable (ex JSON pointer), jamais du texte de preuve instable.
2. AT-015 : parser les tables littérales de _LAZY_EXPORT_MODULES et __getattr__, distinguer STATIC_REF / PUBLIC_LAZY_EXPORT / RUNTIME_CONSUMER / UNKNOWN ; zéro safe_to_delete si ambigu.
3. AT-016 : exposer offsets/total/returned/truncated, union de pages sans perte et export complet opt-in depuis un graphe chargé une fois.
4. AT-013 : définir l’intégrité byte Git/LF/CRLF et distribution ; normaliser gitattributes/contrats sans affaiblir les hashes.
5. AT-028 : déclarer les contrats/entrypoints de scénarios UI et leurs tests, sans fausses alertes d’outils orphelins.
6. Enrichir les rapports avec exact-SHA, type de preuve, provenance/limites, raisons skipped/unreachable et niveau CONFIRMÉ / PROBABLE / NON CONFIRMÉ / FAUX POSITIF.
7. Mettre à jour les tests, la CLI et AI Context uniquement après code effectif ; pas de nouvelle couche d’IA.

## Validations ciblées
- [ ] tests.test_atlas_doctor
- [ ] tests.test_atlas_doctor_consumer_sites
- [ ] tests.test_atlas_doctor_graph_audit
- [ ] tests.test_atlas_doctor_graph_intelligence
- [ ] tests.test_tool_audit et tests.test_tool_catalog
- [ ] LF/CRLF identiques dans le contrat choisi et corruption byte détectée

## Critères de sortie
- [ ] Deux entrées JSON distinctes obtiennent deux IDs stables.
- [ ] Pagination exhaustive vérifiée sur >30 candidats sans doubles/oubli.
- [ ] Exports lazy identifiés sans inventer un appel runtime.
- [ ] Scénarios UI déjà protégés ne sont plus classés sans tests.
- [ ] Aucun contrôle d’intégrité silencieusement assoupli.

## Garde-fous communs
- Conserver toutes les fonctionnalités, les sources JSON et le comportement lazy sauf correction justifiée.
- Vérifier HEAD réel, git status et diff avant de coder. Aucun refactor de masse fondé sur le seul degré Graphify.
- Faire tests ciblés pendant le développement ; FULL uniquement à la certification si la policy l'exige.
- Recouper les observations avec les preuves de PR #160 ; distinguer CONFIRMÉ, PROBABLE, NON CONFIRMÉ.
- Mettre à jour AI Context avec son générateur après code, puis preuve exacte-SHA.
- Pas de merge automatique de cette PR préparatoire.

Sources : [rapport intégral](https://github.com/r9327/Dof-Atlas/blob/docs/audit-integral-2026-10-14/docs/audits/AUDIT_INTEGRAL_DOFUS_ATLAS_2026-10-14.md) ; [registre anomalies](https://github.com/r9327/Dof-Atlas/blob/docs/audit-integral-2026-10-14/docs/audits/2026-10-14-ac07be9b/registres/anomalies.json).
