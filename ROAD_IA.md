# Dofus Atlas — ROAD IA

Cette roadmap est le chantier permanent qui améliore la qualité de travail des agents IA sur Dofus Atlas sans remplacer les règles projet existantes.

## Commande de reprise

Quand l'utilisateur dit **`go road ia`**, reprendre le premier lot qui n'est pas `DONE`. Ne pas redemander le contexte déjà présent dans le dépôt. Commencer par vérifier le HEAD, la branche, le statut Git et exécuter `py -3.13 -m tools.ai_context status`.

La ROAD IA est indépendante de la ROAD V3 produit : elle améliore la manière de travailler sur toute l'application, pas une fonctionnalité métier précise.

## Principes

- `AGENTS.md`, `ZERO_TRUST_RULES.md`, `DEVELOPMENT_GUARDRAILS.md`, `PERFORMANCE_GUARDRAILS.md` et `PHASE_CERTIFICATION.md` restent les contrats permanents.
- Le contexte IA doit être **court, routé et vérifiable**, jamais un deuxième cahier des charges géant.
- Le dépôt réel, les tests et le code courant restent la source de vérité.
- Toute donnée de contexte automatiquement dérivable du dépôt doit être générée automatiquement plutôt que maintenue à la main.
- Une amélioration du système IA ne doit pas affaiblir la CI, les audits, les tests ou les règles anti-régression.
- Les changements se font en micro-lots cohérents et testables.
- `IMPLEMENTED — VALIDATION PENDING` signifie que le code du lot est présent mais qu'il ne doit pas être considéré fermé tant que la preuve machine prévue n'existe pas sur le SHA exact.
- Un lot `DONE` reste valide uniquement si le workflow de certification associé au HEAD courant est vert.

## Lots

### IA-0 — Baseline et non-régression des règles — DONE

Objectif : conserver les règles existantes et les utiliser comme socle au lieu de les remplacer.

Preuve : le dépôt possède déjà `AGENTS.md`, `ZERO_TRUST_RULES.md`, `DEVELOPMENT_GUARDRAILS.md`, `PERFORMANCE_GUARDRAILS.md`, `PHASE_CERTIFICATION.md` et les hooks Git locaux.

### IA-1 — Routeur de contexte compact + index automatique — DONE

Objectif : qu'un agent sache immédiatement où regarder sans charger tout le dépôt.

Livrables présents :

- `AI_CONTEXT.md` : carte courte des sources de vérité et routage par zone ;
- `tools/ai_context.py` : état live du dépôt, classification, routage et synchronisation ;
- `.ai/context_index.json` : empreintes compactes de toutes les entrées racine, sauf `.ai/` pour éviter l'auto-référence ;
- mise à jour automatique de l'index au `pre-commit` à partir de l'arbre staged ;
- `.github/workflows/ai-context-ci.yml` : validation ciblée légère ;
- tests empêchant de considérer comme courant un index périmé ;
- tests Git temporaires couvrant création, modification, renommage, suppression et synchronisation staged.

Preuve : validation ciblée réussie sur le SHA candidat certifié.

### IA-2 — Instructions locales par zone — DONE

Objectif : donner à l'agent seulement les règles locales utiles au code qu'il touche.

Livrables présents :

- `app/AGENTS.md` ;
- `data/AGENTS.md` ;
- `tools/AGENTS.md` ;
- `tests/AGENTS.md`.

Règle permanente : ajouter un `AGENTS.md` plus local uniquement lorsqu'une zone possède de vraies contraintes propres et stables. Éviter les doublons et les fichiers d'instructions partout.

Preuve : validation ciblée réussie sans contradiction détectée avec le contrat global.

### IA-3 — Carte d'impact et tests ciblés — DONE

Objectif : avant une modification, proposer les validations et sources de vérité les plus probables.

État implémenté :

- `status` et `route` recommandent des documents de contexte ;
- ils proposent des ancres canoniques existantes selon le domaine ;
- ils proposent des modules de tests ciblés existants ;
- un test portant directement le nom d'un fichier Python modifié est détecté automatiquement lorsqu'il existe ;
- les recommandations absentes du dépôt sont filtrées au lieu d'être inventées.

Les recommandations restent une aide au ciblage et ne remplacent jamais la recherche réelle des imports, appels, consommateurs et contrats.

Preuve : tests ciblés ROAD IA réussis sur le SHA candidat certifié.

### IA-4 — Détection de dérive architecturale — DONE

Objectif : détecter les nouveaux fichiers ou nouvelles zones qui ne rentrent dans aucune catégorie utile.

État implémenté :

- tout nouveau fichier ou répertoire racine est automatiquement couvert par l'index Git compact ;
- `py -3.13 -m tools.ai_context drift` signale les chemins modifiés que le routeur ne sait pas classifier ;
- un chemin non classé produit un warning et ne bloque pas une évolution légitime ;
- un index manquant ou périmé reste une erreur de cohérence.

Preuve : validation machine des cas connus et volontairement non classés réussie.

### IA-5 — Handoff agent / reprise de chantier — DONE

Objectif : rendre une reprise ChatGPT/Codex fiable sans énorme prompt manuel.

État implémenté :

- `py -3.13 -m tools.ai_context handoff` produit un handoff compact ;
- il contient branche, SHA, base, objectif, fichiers réellement modifiés, état vérifié, tests déclarés, blocages, prochaine action et tests ciblés suggérés ;
- aucun log massif ni copie de dépôt n'est inclus ;
- le format texte est couvert par un test ciblé.
Preuve : test ciblé et validation de reprise/handoff réussis.

### IA-6 — Certification ROAD IA — DONE

Objectif : prouver que la couche IA aide sans dégrader le produit.

Validation finale obtenue :

- tests ciblés ROAD IA : PASS ;
- intégrité FAST : PASS ;
- full suite application : PASS ;
- hook/index et cohérence du contexte : PASS ;
- création, modification, renommage et suppression : couverts par tests ;
- aucun changement de comportement produit Dofus Atlas introduit par la ROAD IA.

Preuve machine de fermeture avant synchronisation documentaire finale :

- branche : `road/ai-agent-context-v1` ;
- base de validation : `2c19ce59269773a03a8741af24728299f69723ed` ;
- SHA certifié : `e5a0803f0eb7e66889b7d91b62aab9caf53a18c9` ;
- GitHub Actions run : `36182042785` ;
- catalogue matérialisé : `1976` quêtes ;
- Atlas Integrity FAST : `PASS`, dette critique `0`, blockers `0` ;
- full suite : `1595` tests, `OK`.

La synchronisation finale de `ROAD_IA.md` et `.ai/context_index.json` doit elle-même conserver un workflow vert sur son HEAD exact ; aucune nouvelle modification documentaire n'est nécessaire après cette dernière preuve.

---

# ROAD IA V2 — Context Router Global + Outillage Agent Minimal

La V2 prolonge la ROAD IA existante. Elle ne la remplace pas et ne crée pas une deuxième autorité de validation.

Objectif : router une demande vers un **scope fonctionnel explicite**, un petit working set de fichiers réellement utiles et les validations adaptées, sans scan global du dépôt et sans modifier le comportement produit.

Contraintes permanentes de la V2 :

- réutiliser `AI_CONTEXT.md`, `tools/ai_context.py`, `.ai/context_index.json`, les `AGENTS.md` et les guardrails existants ;
- réutiliser `tools/atlas_integrity.py`, `tools/atlas_integrity_policy.json`, `DIFF_TARGETS` et les contrôles existants au lieu de créer un validateur parallèle ;
- aucun refactor global, aucun déplacement massif de fichiers et aucune modification produit uniquement pour faciliter le routeur ;
- les scopes doivent être dérivés du dépôt réel ; un module absent ne doit jamais être inventé pour rendre la carte plus jolie ;
- travailler en micro-lots et arrêter après chaque phase ;
- la ROAD V3 produit reprend seulement après fermeture de la V2.

## V2-1 — Audit de l'existant — DONE

Constat : les briques de base existent déjà et doivent être conservées.

À réutiliser :

- routeur compact et handoff de `tools/ai_context.py` ;
- empreinte Git de `.ai/context_index.json` ;
- règles globales et locales `AGENTS.md` ;
- `tools/atlas_integrity.py`, sa policy, ses groupes de risque et `DIFF_TARGETS` ;
- inventaire critique, checks générés et workflows de certification existants.

Manques identifiés pour la V2 : ownership fonctionnel précis, carte globale des scopes, manifests de scopes, commandes agent minimales, index symboles/imports léger, détection `UNOWNED`/`AMBIGUOUS`, mapping tests et hotspots indicatifs.

Aucun fichier produit n'a été modifié pendant cette phase.

## V2-2 — Cartographie fonctionnelle réelle FEATURE / SHARED INFRASTRUCTURE — DONE

Objectif : définir les domaines réels avant de générer le futur `context-map`. Cette phase est **descriptive uniquement** : elle ne crée pas encore `.ai/context-map.yaml`, `.ai/scopes/*.yaml`, `tools/agent.py` ni d'index AST.

### Scopes FEATURE

- `home` — tableau d'accueil, personnage actif, reprise Guide et état réseau. Ancres : `app/pages/home_page.py`, `main.py`.
- `character` — sélection/édition des personnages et ordre d'affichage. Ancres : `app/pages/character_page.py`, `app/pages/_character_page_impl.py`, `app/services/character_data_service.py`, `app/services/character_order_service.py`.
- `organizer` — sessions Dofus, ordre des clients, lancement et orchestration des actions multi-compte. Ancres : `app/pages/organizer_page.py`, `app/pages/organizer_icon_cache.py`.
- `equipment` — surface Équipement. Ancre : `app/pages/equipment_page.py`.
- `craft` — catalogue/crafts, sélection et données de métiers/ressources. Ancres : `app/pages/craft_page.py`, `local_dofus_data/compatibility_adapter.py`.
- `zaap` — macro Zaap déclenchée depuis le runtime/Organizer. Ancre : `app/macros/zaap.py`.
- `travel` — déplacement automatisé déclenché depuis le runtime/Organizer. Ancre : `app/macros/travel.py`.
- `world_scan` — Scan Monde et état de scan visible. Ancres : `app/ui/world_scan_panel.py`, `app/cartography/scan_status_service.py`.
- `encyclopedia_shell` — navigation, lazy lifecycle et coordination entre sous-domaines Encyclopédie. Ancres : `app/modules/encyclopedia/views/encyclopedia_page.py`, `app/modules/encyclopedia/constants.py`.
- `encyclopedia_quests` — catalogue, rendu et progression Quêtes. Ancres : `app/quest_catalog.py`, `app/pages/quests_page.py`, `app/pages/progressive_quests_page.py`, `app/modules/encyclopedia/providers/`.
- `encyclopedia_achievements` — catalogue, détail et progression Succès. Ancres : `app/modules/encyclopedia/views/achievements_view.py`, `app/modules/encyclopedia/achievement_catalog_policy.py`, `app/modules/encyclopedia/services/`.
- `encyclopedia_guide` — Guides et Guide Ultime manuel, route canonique, runtime et progression. Ancres : `app/modules/encyclopedia/views/guides_view.py`, `app/modules/encyclopedia/views/guide_ultime_manual_view.py`, `app/modules/encyclopedia/services/guide_ultime_manual_runtime_service.py`, `data/routes/guide_ultime_manual/`.
- `encyclopedia_bestiary` — surface de navigation Donjons/Monstres/Archimonstres/Avis de recherche. Les onglets existent dans le shell mais restent des placeholders tant qu'aucune implémentation canonique dédiée n'est matérialisée ; ne pas leur inventer un backend. Ancres : `app/modules/encyclopedia/constants.py`, `app/modules/encyclopedia/views/encyclopedia_page.py`.

`Almanax` est actuellement une surface explicitement marquée « En travaux » dans `main.py`. Il n'est donc pas promu en scope fonctionnel implémenté par la V2.

### Scopes SHARED INFRASTRUCTURE

- `cartography` — données monde, assets, services de carte et canvas partagés par Scan/Map Monde. Ancres : `app/cartography/`, `app/services/maps/`, `app/ui/map_canvas_widget.py`.
- `persistence_identity` — identité `character:<id>`, JSON atomiques, coordination de progression, profils et données personnage. Ancres : `app/core/character_identity.py`, `app/core/json_store.py`, `app/core/progress_coordinator.py`, `app/storage.py`, `app/services/`.
- `startup_lifecycle` — lancement, preload, orchestration du shell et travail de fond. Ancres : `launch.py`, `main.py`, `app/preload.py`, `app/background_work.py`.
- `network_capture` — capture réseau, calibration, résolution personnage, décodage/runtime et pont UI. Ancres : `app/network/`, `app/ui/network_bridge.py`.
- `dofus_data` — lecture/import/cache des données locales Dofus et couche de compatibilité. Ancres : `local_dofus_data/`, `app/local_data_cache.py`, `app/quest_catalog.py`.
- `shared_ui` — thème global, composants réutilisables, styles et primitives de shell. Ancres : `app/ui/theme.py`, `app/ui/components.py`, `app/ui/styles/`.
- `windows_qt_runtime` — fenêtres Unity, focus/clics, single-instance, DPI et intégration OS. Ancres : `app/windows/`, `main.py`.
- `input_hotkeys` — hooks clavier/souris, état d'entrée et lifecycle des hooks. Ancre : `app/input/`.
- `macro_runtime` — primitives communes aux macros de changement de personnage, clic, direction et auto-groupe ; Zaap/Travel gardent leur scope FEATURE propre. Ancres : `app/macros/input_tools.py`, `app/macros/switch_character.py`, `app/macros/switch_click.py`, `app/macros/direction.py`, `app/macros/auto_group.py`.
- `quality_ci` — validation, audits, policy de risque, tests et workflows. Ancres : `tools/atlas_integrity.py`, `tools/atlas_integrity_policy.json`, `tests/`, `.github/workflows/`, `.githooks/`.

### Règles d'ownership pour les phases suivantes

- Chaque chemin doit recevoir un scope primaire unique lorsque c'est possible.
- Une dépendance partagée reste dans un scope `SHARED INFRASTRUCTURE` même si plusieurs features la consomment.
- Un fichier Encyclopédie spécifique à Quêtes/Succès/Guide appartient au sous-scope correspondant ; les fichiers de coordination générale restent dans `encyclopedia_shell`.
- Les routes `data/routes/guide_ultime_manual/` appartiennent à `encyclopedia_guide`, pas à un scope générique `data`.
- Les tests ne sont pas encore associés automatiquement aux scopes : ce mapping est réservé à V2-10.
- Les imports/symboles ne sont pas encore analysés : cette dépendance automatique est réservée à V2-7 et V2-8.
- Une surface placeholder n'est jamais présentée comme une feature implémentée.
- Cette cartographie ne justifie aucun déplacement de code existant.

Critères de fermeture V2-2 :

- les principales surfaces utilisateur réellement câblées sont nommées ;
- les infrastructures transversales critiques sont séparées des features ;
- les ancres citées existent dans le dépôt courant ;
- les zones non implémentées restent explicitement identifiées comme telles ;
- aucun code produit, format persistant ou comportement runtime n'a été modifié.

## V2-3 — `.ai/context-map.yaml` — DONE

Matérialiser la cartographie V2-2 dans une carte machine compacte, sans dupliquer le dépôt ni les guardrails.

## V2-4 — Manifests `.ai/scopes/*.yaml` — DONE

Définir par scope le petit working set, les dépendances partagées et les entrées de contexte réellement utiles.

## V2-5 — Routage des règles existantes — DONE

Relier les scopes aux `AGENTS.md`, guardrails et sources de vérité existants sans recopier leurs contenus.

## V2-6 — `tools/agent.py` minimal — DONE

Les commandes `doctor`, `inspect`, `impact` et `validate` sont présentes dans `tools/agent.py`. `validate` délègue directement à `tools.atlas_integrity.main` et ne devient pas une deuxième autorité de validation.

Preuve de fermeture :

- commit candidat : `5f4a4f01783bee1b3b2747c3f188e3c666dc0bd1` ;
- test ciblé : `tests/test_agent_tool.py` ;
- Public Pull Request CI : PASS ;
- AI Context CI : PASS ;
- Phase Certification / Full Validation : PASS sur le SHA exact ;
- aucun changement produit et aucun lot V2-7+ inclus.

## V2-7 — Index symboles AST léger — DONE

`tools/agent.py symbols <scope>` indexe uniquement les définitions Python top-level utiles au routage (`class`, `def`, `async def`) présentes dans les fichiers `.py` déjà déclarés par le scope via son working set, ses context entries et ses canonical entries. Aucun import n'est suivi et aucune dépendance n'est dérivée dans ce lot ; V2-8 reste séparé.

Preuve de fermeture :

- commit candidat certifié : `230fda073c8865a145a2da4704f845ba815a0fc4` ;
- tests ciblés `tests/test_agent_tool.py` : PASS ;
- Atlas Integrity FAST : PASS ;
- full application suite : PASS ;
- Public Pull Request CI : PASS ;
- AI Context CI : PASS ;
- Phase Certification / Full Validation : PASS sur le SHA exact ;
- PR temporaire #37 fermée sans merge ;
- aucun changement produit et aucun lot V2-8+ inclus.

## V2-8 — Dépendances imports — DONE

`tools/agent.py imports <scope>` dérive uniquement les imports Python internes directs des fichiers déclarés dans le working set du scope. Les imports absolus et relatifs sont résolus uniquement lorsqu'ils correspondent à un fichier ou package réellement présent dans le dépôt ; les dépendances externes sont ignorées. L'enrichissement reste borné à un seul niveau : les fichiers importés ne sont pas reparcourus, donc aucun scan global ni fermeture transitive n'est introduit.

Preuve de fermeture :

- commit candidat certifié : `6e56fe2180e65cd793400e87c048b9778c234319` ;
- tests ciblés `tests/test_agent_tool.py` : PASS ;
- Atlas Integrity FAST : PASS ;
- full application suite : PASS ;
- Public Pull Request CI : PASS ;
- AI Context CI : PASS ;
- Phase Certification / Full Validation : PASS sur le SHA exact ;
- PR temporaire #38 utilisée uniquement pour validation, sans merge ;
- aucun changement produit et aucun lot V2-9+ inclus.

## V2-9 — Maintenance minimale de la carte — DONE

`tools/agent.py ownership <paths...>` classe les chemins demandés en `OWNED`, `UNOWNED` ou réellement `AMBIGUOUS`. La sélection donne priorité à l'ancre active la plus spécifique ; les scopes `placeholder` restent visibles comme contexte mais ne deviennent jamais propriétaires métier. `impact` expose la même décision d'ownership et `doctor` bloque les doubles ancres exactes entre scopes actifs afin de détecter une dérive simple de la carte sans scan global.

Deux conflits réels de working set révélés pendant la validation ont été normalisés sans changement produit :

- `app/quest_catalog.py` garde `dofus_data` comme propriétaire primaire ; `encyclopedia_quests` le consomme via `context_entries` et sa dépendance partagée `dofus_data` ;
- `main.py` garde `startup_lifecycle` comme propriétaire primaire ; `windows_qt_runtime` le conserve uniquement dans `context_entries`.

Preuve de fermeture :

- commit candidat certifié : `c066569549db4a81d77942583bc7482c4af41e69` ;
- tests ciblés `tests/test_agent_tool.py` : PASS ;
- Atlas Integrity FAST : PASS ;
- full application suite : PASS ;
- Public Pull Request CI : PASS ;
- AI Context CI : PASS ;
- Phase Certification / Full Validation : PASS sur le SHA exact ;
- aucun changement produit et aucun lot V2-10+ inclus.

## V2-10 — Mapping tests par scope — DONE

Chaque scope de `.ai/context-map.yaml` déclare maintenant explicitement ses `test_entries`, y compris une liste vide lorsqu'aucun test direct fiable ne doit être inventé. `tools/agent.py` vérifie dans `doctor` que ces modules existent, les expose via `inspect`, puis les place dans `scope_tests` et en tête de `recommended_tests` dans `impact` avant le fallback générique historique de `tools.ai_context`.

Ce mapping reste une aide au ciblage : il ne modifie ni `DIFF_TARGETS`, ni `tools.atlas_integrity`, ni `tools/atlas_integrity_policy.json`, qui restent les autorités de validation.

Preuve de fermeture :

- commit candidat certifié : `12a8fa7f6f437c9370dcd6381b18909b30823fb2` ;
- tests ciblés ROAD IA, dont `tests/test_agent_scope_tests.py` : PASS ;
- Atlas Integrity FAST : PASS ;
- full application suite : PASS ;
- Public Pull Request CI : PASS ;
- AI Context CI : PASS ;
- Phase Certification / Full Validation : PASS sur le SHA exact ;
- aucun changement produit et aucun lot V2-11+ inclus.

## V2-11 — Hotspots indicatifs — DONE

`tools/agent_hotspots.py` produit un rapport strictement informatif : il réutilise le risque existant de `atlas_integrity.classify_risk()` et la centralité déclarée par les `shared_dependencies` des manifests. Une zone est signalée seulement si le classifieur existant la place en risque `HIGH`/`CRITICAL` ou si une infrastructure partagée est consommée par au moins deux scopes. Aucun score combiné, aucune nouvelle gate et aucun blocage produit ne sont introduits.

Preuve de fermeture :

- commit candidat certifié : `ca4bae4131957dda33131e1a29a6e6415ee5b91e` ;
- test ciblé `tests/test_agent_hotspots.py` : PASS ;
- Atlas Integrity FAST : PASS ;
- full application suite : PASS ;
- Public Pull Request CI : PASS ;
- AI Context CI : PASS ;
- Phase Certification / Full Validation : PASS sur le SHA exact ;
- aucun changement produit et aucun lot V2-12+ inclus.

## V2-12 — Checkpoint global — DONE

`tests/test_agent_checkpoint.py` vérifie transversalement la carte V2 sans ajouter de nouveau routeur : chaque scope actif possède un working set explicite et borné, aucune ancre de working set ne prend une racine globale (`app/`, `data/`, `tests/`, `tools/` ou `.`), chaque scope actif expose au moins une route primaire `OWNED` vers lui, ainsi que ses entrées canoniques et ses tests ciblés. Les scopes `placeholder` restent du contexte uniquement et ne deviennent jamais propriétaires métier.

Le checkpoint s'appuie uniquement sur `tools/agent.py`, `.ai/context-map.yaml` et les manifests existants. Il ne lance pas de scan global supplémentaire et ne crée ni nouvelle autorité de validation, ni nouvelle gate.

Preuve de fermeture :

- commit candidat certifié : `aa9cc8e3445d056d5aabeab0d3b66cde02c4ac89` ;
- test global `tests/test_agent_checkpoint.py` exécuté dans la full application suite : PASS ;
- Atlas Integrity FAST : PASS ;
- full application suite : PASS ;
- Public Pull Request CI : PASS ;
- AI Context CI : PASS ;
- Phase Certification / Full Validation : PASS sur le SHA exact ;
- aucun changement produit, aucun changement de `tools/agent.py` / `atlas_integrity` / policy / `DIFF_TARGETS`, et aucun lot V2-13 inclus.

## V2-13 — Intégration finale `atlas_integrity` — DONE

Aucun changement exécutable n'est requis pour ce lot : l'intégration finale demandée est déjà canonique dans le dépôt courant. `tools/agent.py validate` délègue directement à `tools.atlas_integrity.main` en conservant les arguments et le code retour ; `tests/test_agent_tool.py` couvre explicitement cette délégation. `PHASE_CERTIFICATION.md` définit `tools/atlas_integrity_policy.json` et `tools.atlas_integrity` comme source machine de vérité, et la certification de phase exécute le mode `FULL`. Le workflow ROAD IA réutilise également `tools.atlas_integrity fast` au lieu d'introduire une gate parallèle.

La ROAD IA V2 reste donc un routeur et un outillage de contexte ; elle ne décide jamais elle-même du verdict produit. Aucun validateur, score bloquant, policy parallèle, modification de `DIFF_TARGETS` ou nouvelle autorité de certification n'est ajouté pour fermer la V2.

Preuve de fermeture avant synchronisation documentaire finale :

- état exécutable certifié : `eaf8bec3e50d9f4a5a551b6695c5053eb2a6464f` ;
- test `tests/test_agent_tool.py::AgentToolTests.test_validate_delegates_directly_to_atlas_integrity` : PASS dans la full application suite ;
- Atlas Integrity FAST : PASS ;
- full application suite : PASS ;
- Public Pull Request CI : PASS ;
- AI Context CI : PASS ;
- Phase Certification / Full Validation : PASS sur le SHA exact ;
- aucun changement produit, aucun changement exécutable V2-13 et aucun système parallèle introduit.

ROAD IA V2 est fermée. La reprise de la ROAD V3 doit repartir du dépôt réel et de son premier lot encore ouvert ; elle ne commence pas automatiquement dans ce lot V2-13.

## Atlas Doctor et Graphify — diagnostic unifie

Atlas Doctor est recupere depuis les fichiers propres de la PR #47, sans reprendre sa branche Phase 7E. Le lanceur Windows delegue au module canonique `tools.atlas_doctor` ; les commandes audit, live, perf, compare, issues, verify, report, clean et all restent disponibles. `quick` ne lance ni gate ni Graphify. `graph` consulte le graph ; `--rebuild` et `--install` sont explicites.

Separation permanente : Agent route le contexte et le plan ; Doctor diagnostique le repo/runtime/performance/architecture ; `tools.graphify` reutilise Graphify pinne en mode AST/code-only/no-label ; Atlas Integrity reste la gate canonique. Les travaux structurels utilisent `tools.agent plan --structural`, puis les relations sont confirmees dans les sources, imports, consommateurs, contrats et tests.

Les sorties restent dans `graphify-out/` et `.ai/runtime/atlas_doctor/`, ignores. Le cache Doctor suit HEAD et le contenu du worktree ; la signature du graph, la version et les sorties attendues sont verifies. Aucun hook Graphify, watcher, daemon ou generation au lancement produit n'est ajoute.

`tools.tool_audit` reste une vue derivee de revue. Zero consommateur n'autorise pas une suppression : familles versionnees, wrappers, entrees historiques et mutateurs restent soumis a la preuve des consommateurs et du remplacement canonique. Les facades Guide modernes sont preservees.

La preuve de validation est portee par les tests cibles et les workflows sur le HEAD exact de la PR d'integration ; aucune validation historique de #47 n'est transposee au candidat courant.

# ROAD Doctor — Agent / Doctor / Graph — preuves de cloture : PR #80

Les lots Doctor / Agent / Graph sont implementes. Leur fermeture est controlee par les preuves machine du HEAD exact de la PR #80, et par les scenarios runtime SOFT/MEDIUM/HARD documentes dans cette PR. Atlas Integrity et sa policy restent l'unique autorite de validation ; Agent planifie le contexte, l'ownership, l'impact cible et la profondeur ; Doctor execute les moteurs canoniques, conserve les preuves et compare uniquement des baselines compatibles. Aucun daemon, hook Graphify implicite ou changement produit n'a ete ajoute.

## RD-0 — Execution contracts — VALIDATED

PR #72, HEAD exact `76cd6c08da512e5f242eeb83a5ebb5e380415874` : contrats Doctor/Agent, PASS/FAIL/REVIEW, base explicite, readiness et autorite Atlas Integrity valides.

## RD-1 — Reverse-impact Graphify cible — VALIDATED

PR #73, HEAD exact `ded119e82864b5fae78053591768250a83aca6b5` : reverse-impact borne, cache Doctor courant, confirmation par imports et REVIEW explicite quand la relation n'est pas prouvee. Graphify reel et validations Windows PASS.

## RD-2 — Planner par metadonnees — VALIDATED

Le planner reutilise `tools.tool_catalog.select_tools` et les `TOOL_SPEC`. Les moteurs specialises sont selectionnes par metadata et scopes declares, jamais par heuristique de nom de chemin. Les modes, couts, effets de bord, tests declares et raisons restent exposes.

## RD-3 — Profondeurs de travail — VALIDATED

SOFT/MEDIUM/HARD et les overrides explicites sont implementes sans pouvoir abaisser le plancher d'Atlas Integrity. Les changements structurels/CRITICAL escaladent en HARD ; FULL_SUITE reste deleguee une seule fois a Atlas Integrity.

## RD-4 — Facade verify — VALIDATED

`tools.agent verify` et `tools.atlas_doctor verify <paths...>` partagent l'execution Doctor. AI Context, tests cibles, facades specialisees canoniques et exactement un Atlas Integrity sont executes sans mutateur. Les causes exposees restent limitees aux preuves observables.

Validation RD-2/RD-3/RD-4 : PR #74, HEAD exact `29305f4793e6da8306266e5a83e43c6ddcea97a9` : Targeted Validation PASS, Atlas Integrity FAST PASS, full application suite PASS, Public Pull Request CI PASS, Graphify PASS et Commit Signature PASS. Phase Certification etait skip selon le workflow de ce micro-lot. Merge `main` : `7f275d4eaa632ea7f5adb4bdeb83708f9939c296`.

## RD-5 — Baselines comparables et diagnostics — VALIDATED

La verification resout la baseline demandee en SHA exact et ne compare deux executions que si baseline, cibles, scopes, profondeur de travail et autorite de validation sont compatibles. Les regressions et recuperations sont rapportees comme observations ; commandes reproductibles, failure IDs et diagnostics actionnables sont conserves sans inventer une cause source.

## RD-6 — Cout d'execution, cache et cleanup prouve — VALIDATED

Les durees totales et par check sont mesurees et les checks les plus couteux restent visibles. Le cache planner expose HIT/MISS/BYPASS et reste indexe par HEAD + dirty digest ; les resultats de validation ne sont jamais reutilises depuis un simple cache Git. Le verify Doctor historique sans chemins est conserve parce que son consommateur de compatibilite est teste ; aucune suppression speculative n'est faite.

Validation RD-5/RD-6 : PR #76, HEAD exact `10d15001f8adbdb8a32cfef60c0f513b9e41f91d` : Targeted Validation PASS, Atlas Integrity FAST PASS, full application suite PASS, Public Pull Request CI PASS, Graphify PASS et Commit Signature PASS. Phase Certification etait skip selon le workflow de ce lot. Merge `main` : `2446238987e625e1fd292c8d845f391681f77375`.

## RD-7 — Fix deterministe `--dry-run` — CLOSED / NOT REQUIRED

Ce lot etait explicitement optionnel. Aucune preuve n'a etabli une mutation repository generique, deterministe et suffisamment sure pour meriter une nouvelle facade `fix`. Les commandes de reparation explicites existantes restent separees. Aucun auto-fix n'est invente uniquement pour cocher la ROAD.

## Fermeture

Les merges #74 et #76 valident leurs micro-lots ; leurs checks Phase Certification skipped ne constituent pas une certification de fermeture. La PR #77 a corrige la fausse escalade provoquee par les sorties runtime, sans supprimer les verrous JSON ni affaiblir la policy. Sur l'implementation `8661cfd05974ff3933a6fb81c6644514600a8b0d`, la suite complete compte 1821 tests PASS et Phase Certification run `36851325785` est PASS avec `GUIDE_CERTIFIED`. Les scenarios runtime et leurs couts sont publies dans [PR #80](https://github.com/r9327/Dof-Atlas/pull/80); un FAIL courant n'est jamais accepte comme non-regression.

La fermeture definitive exige les checks termines et verts du HEAD courant de #80, ainsi que la matrice runtime. Une modification documentaire ou d'index change aussi le SHA et impose de nouvelles validations exactes. Avant de reprendre un lot deja implemente, verifier ces preuves GitHub plutot que refaire l'outillage. Doctor/Agent/Graph restent des outils d'assistance et ne remplacent jamais Atlas Integrity ni les contrats produit.

## Reprise pratique avant / apres

```powershell
py -3.13 -m tools.agent plan tools/agent.py --json
py -3.13 -m tools.atlas_doctor verify tools/agent.py --soft --save-baseline before --json
# Modifier le code, puis synchroniser AI Context par son mecanisme canonique.
py -3.13 -m tools.atlas_doctor verify tools/agent.py --baseline before --json
```

Une baseline nommee est un snapshot ignore dans `.ai/runtime/atlas_doctor/`; elle n'est pas ecrasee par les validations suivantes. La comparaison reutilise son SHA de base immuable lorsque `--base-ref` vaut `HEAD` (valeur par defaut). Une baseline absente, invalide ou un nom dangereux produit REVIEW avant les controles. `--save-baseline` et `--baseline` sont exclusifs.

La compatibilite comprend les tests effectivement selectionnes, les commandes des moteurs, les scopes, la profondeur, l'autorite et l'environnement machine/dependances/policy. Des contrats differents produisent UNAVAILABLE, jamais une fausse absence de regression. Les nouveaux failure IDs sont distingues des IDs preexistants; une cause source n'est pas deduite d'un simple statut. Un echec courant reste FAIL meme lorsqu'il etait deja present.

Les durees de la facade incluent planification, reconstruction explicite du graph et execution. Les deltas temporels sont des observations comparables sur la meme machine; une hausse d'au moins 15 % et 1 seconde appelle une revue, sans remplacer une gate.

SOFT cible les consommateurs de tests prouves par Tool Audit; les mentions textuelles restent une aide de revue, pas un consommateur execute automatiquement. Une suppression ou un renommage de module Python detecte par Git impose un preflight structurel et peut escalader en HARD. Un graph requis absent ou perime arrete la verification avant les controles couteux. Aucun graph n'est reconstruit implicitement.

## Revue de consolidation

Aucun outil n'est supprime sur la seule indication zero consumer. Les hooks PowerShell ont des consommateurs Git; `atlas_doctor_io_runner` et `atlas_fault_injection` sont appeles dynamiquement par leurs moteurs. Les facades Guide modernes et leurs tests restent canoniques. Les moteurs Guide v4/v5 conservent des contrats et consommateurs distincts; les mutateurs historiques v2/v3 ne disposent pas d'un remplacement prouve et restent candidats a revue. Cette ROAD ne leur invente pas un remplacement.

Le cycle produit observe entre `guides_view`, `widgets/__init__` et `quest_detail_view` reste une observation hors du perimetre tooling. Il ne justifie pas un refactor produit dans ce chantier.
