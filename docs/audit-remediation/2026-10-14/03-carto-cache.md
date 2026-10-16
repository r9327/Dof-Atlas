# [PLAN 03] Cartographie transactionnelle et caches récupérables (AT-008/009/011/021)

> PLAN PRÉPARATOIRE — aucun correctif applicatif implémenté ici. PR DRAFT à compléter en code et tests ciblés avant revue/fusion.

Audit source : PR #160, SHA audité `ac07be9b894718f5e68e7c3a91016d7651e3065b`. Branche de base : `main` ; éviter de mélanger les modifications de PR #159 et #138.

## Objectif
Sécuriser les imports de cartes et fiabiliser la réparation des caches invalides sans effacer d’état joueur.

## Dépendances et ordre
Indépendant du lot Doctor ; terminer AT-008/009 avant de raccorder import_manifest à une UI.

## Constat et preuves détaillées
### AT-008 — L’import explicite de cartographie efface les états des maps
- Priorité / état : P1 / CONFIRMÉ / main.
- Localisation : app/cartography/map_view_manifest.py:92 import_map_view_manifest; app/cartography/map_view_manifest.py:126 replace_view_children; app/cartography/world_db.py:370 replace_view_children; app/cartography/world_db.py:318 upsert_map; app/ui/world_scan_panel.py:237 import_manifest.
- Cause : L’import supprime maps/map_links puis réinsère les seeds ; status, scan_count, last_seen_at sont perdus. Les nombreuses connexions_scope indépendantes rendent aussi l’ensemble non transactionnel en cas d’erreur intermédiaire. Aucun import automatique au démarrage ni bouton connecté à import_manifest n’a été démontré : le risque actuel est sur l’API/outil d’import explicite.
- Preuve audit : reproductions.json/world_reimport : current/scan_count=1 devient unverified/0/last_seen_at=null sans erreur. Lecture des DELETE et des transactions séparées. Une perte sur démarrage ordinaire serait un diagnostic inventé.
- Correction du registre : Importer la géométrie et les liens dans une seule transaction ; préserver les colonnes de progression des maps existantes. Suppression des maps disparues seulement sous une politique explicite avec backup. Ne pas reconnecter cette méthode à l’UI avant correction.

### AT-009 — Le validateur cartographique ne vérifie pas les références
- Priorité / état : P2 / CONFIRMÉ / main.
- Localisation : app/cartography/map_view_manifest.py:35 validate_manifest; app/cartography/world_db.py:135 schéma maps/map_links.
- Cause : Il exige un target_view_key non vide mais accepte une cible inexistante, des parents absents et n’écarte pas les coordonnées dupliquées. PRAGMA foreign_keys est activé sans contraintes de références dans ce schéma.
- Preuve audit : reproductions.json/world_reference_validator retourne [] pour un lien vers missing_target. Les JSON actuels contrôlés ne contiennent aucun parent/cible manquant, doublon de coordonnées ou map hors bornes : lacune de validation confirmée, corruption actuelle non confirmée.
- Correction du registre : Validation en deux passes des clés de vues et des liens/parents ; détection des doublons (view,x,y), cycles parent et coordonnées invalides. Les liens externes autorisés doivent être déclarés explicitement, pas refusés arbitrairement.

### AT-011 — Les caches JSON valides mais de mauvais schéma ne se reconstruisent pas
- Priorité / état : P2 / CONFIRMÉ / main.
- Localisation : app/modules/encyclopedia/providers/dofus_item_provider.py:78 _read_guide_items_index; app/modules/encyclopedia/providers/memory_bound_guide_provider.py:47 _guide_compact_cache_valid; app/modules/encyclopedia/providers/memory_bound_achievement_provider.py:68 _achievement_compact_cache_valid; app/modules/encyclopedia/services/guide_ultime_manual_runtime_core.py:228 restore_manual_runtime_compact_cache; app/startup_cache_warmup.py:161 _load_manifest.
- Cause : Les try/except protègent le parsing JSON, puis int(schema_version) est appelé hors du bloc protégé. Un cache reconstruisible avec schema_version="broken" provoque ValueError plutôt qu’un miss/fallback.
- Preuve audit : reproductions.json/guide_item_cache_recovery et cache-recovery-probes.json : exception réelle dans les cinq lecteurs. Le fichier source canonique n’est pas corrompu ; seul le cache isolé l’est.
- Correction du registre : Valider type et version sans conversion risquée, considérer un mauvais cache comme miss et reconstruire une seule fois. Conserver le refus strict des documents persistants utilisateur : ne pas généraliser ce fallback à leur progression.

### AT-021 — Les signatures de caches ne couvrent pas tous leurs inputs
- Priorité / état : P2 / PROBABLE / main.
- Localisation : app/startup_cache_warmup.py:185 _source_paths; app/startup_cache_warmup.py:62 _DOMAIN_IMPLEMENTATION_FILES; app/modules/encyclopedia/providers/memory_bound_guide_provider.py:32 _guide_compact_source_signature; app/modules/encyclopedia/services/guide_ultime_manual_runtime_core.py:160 _manual_runtime_source_signature; app/modules/encyclopedia/services/guide_ultime_manual_runtime_core.py:104 _manual_runtime_quest_signature.
- Cause : Le stamp warmup omet quests_enriched et la policy joueur ; le cache de résumés Guide valide seulement les JSON guides ; le cache manuel valide les JSON et un CRC noms→IDs. Un changement de raw data/enrichissement/implémentation peut ne pas invalider certains artefacts. Certaines couches en aval ont leur propre signature : une stale lecture de production n’a pas été reproduite.
- Preuve audit : Listes source et helpers relus, comparés aux imports/appels. QuestCatalog inclut correctement enrichment dans sa propre signature : ne pas présenter tous les caches comme défectueux.
- Correction du registre : Avant patch, test de changement d’un input pertinent sur copie temporaire et observation du cache réellement consommé. Compléter la signature ciblée ou version de schéma du seul artefact démontré stale ; ne pas hasher tous les gros fichiers à chaque lookup.

## Implémentation attendue
1. Import map_views : géométrie et liens en une transaction SQLite, sans supprimer status/scan_count/last_seen_at des maps existantes.
2. Valider en deux passes les références de vues/parents/liens, les cycles et coordonnées ; autoriser explicitement les liens externes légitimes.
3. Pour les caches JSON valides syntaxiquement mais invalides structurellement, invalider et reconstruire au plus une fois sans perdre de données canoniques.
4. Pour AT-021 classé PROBABLE, établir d’abord une reproduction de stale cache avant changement des signatures ; ne pas invalider massivement sans nécessité.
5. Prendre en compte journal WAL, backup et interruption ; distinguer seed reconstructible et état utilisateur.

## Validations ciblées
- [ ] tests.test_world_db
- [ ] tests ciblés map_view_manifest/cache recovery
- [ ] probe réimport et rollback par injection d’exception
- [ ] tests de corruption, ref absente, duplication et cache stale

## Critères de sortie
- [ ] Réimport idempotent conserve les scans existants.
- [ ] Échec d’import = transaction complètement annulée.
- [ ] Manifeste actuel reste accepté, manifeste corrompu explicitement refusé.
- [ ] Caches régénérables reconstruits sans boucle.
- [ ] Aucun bug non confirmé présenté comme prouvé.

## Garde-fous communs
- Conserver toutes les fonctionnalités, les sources JSON et le comportement lazy sauf correction justifiée.
- Vérifier HEAD réel, git status et diff avant de coder. Aucun refactor de masse fondé sur le seul degré Graphify.
- Faire tests ciblés pendant le développement ; FULL uniquement à la certification si la policy l'exige.
- Recouper les observations avec les preuves de PR #160 ; distinguer CONFIRMÉ, PROBABLE, NON CONFIRMÉ.
- Mettre à jour AI Context avec son générateur après code, puis preuve exacte-SHA.
- Pas de merge automatique de cette PR préparatoire.

Sources : [rapport intégral](https://github.com/r9327/Dof-Atlas/blob/docs/audit-integral-2026-10-14/docs/audits/AUDIT_INTEGRAL_DOFUS_ATLAS_2026-10-14.md) ; [registre anomalies](https://github.com/r9327/Dof-Atlas/blob/docs/audit-integral-2026-10-14/docs/audits/2026-10-14-ac07be9b/registres/anomalies.json).
