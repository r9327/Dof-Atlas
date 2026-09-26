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

## V2-7 — Index symboles AST léger — TODO

Indexer seulement les symboles Python utiles au routage, sans base lourde ni analyse globale permanente.

## V2-8 — Dépendances imports — TODO

Dériver un graphe d'imports léger pour enrichir le working set sans scanner tout le dépôt à chaque demande.

## V2-9 — Maintenance minimale de la carte — TODO

Détecter les chemins `UNOWNED` ou réellement `AMBIGUOUS` et permettre une mise à jour simple lors de l'évolution du dépôt.

## V2-10 — Mapping tests par scope — TODO

Associer les validations ciblées existantes aux scopes sans remplacer `DIFF_TARGETS` ni la policy d'intégrité.

## V2-11 — Hotspots indicatifs — TODO

Signaler uniquement les zones à forte centralité/risque utiles à l'agent ; aucun score ne doit devenir une nouvelle gate produit sans besoin démontré.

## V2-12 — Checkpoint global — TODO

Vérifier qu'une demande peut être routée vers un petit working set exploitable et que les principaux domaines sont couverts sans scan global.

## V2-13 — Intégration finale `atlas_integrity` — TODO

Fermer la V2 avec `atlas_integrity` comme autorité de validation, sans système parallèle, puis reprendre la ROAD V3 exactement où elle était arrêtée.
