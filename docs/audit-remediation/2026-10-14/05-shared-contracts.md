# [PLAN 05] Mutualiser validateurs SHA et règles réellement dupliquées (AT-010/019/020)

> PLAN PRÉPARATOIRE — aucun correctif applicatif implémenté ici. PR DRAFT à compléter en code et tests ciblés avant revue/fusion.

Audit source : PR #160, SHA audité `ac07be9b894718f5e68e7c3a91016d7651e3065b`. Branche de base : `main` ; éviter de mélanger les modifications de PR #159 et #138.

## Objectif
Consolider uniquement les duplications prouvées, sans changer les frontières lazy/Qt.

## Dépendances et ordre
Indépendant, après fixes métier prioritaires ; pas de refactor global.

## Constat et preuves détaillées
### AT-010 — Seize validateurs SHA-256 acceptent des empreintes de deux octets
- Priorité / état : P2 / CONFIRMÉ / main.
- Localisation : app/network/mapping_manifest.py:493 _is_sha256; app/network/mapping_registry.py:84 _is_sha256; app/network/bootstrap.py:273 _is_sha256; app/network/current_protocol_profile.py:210 _is_sha256; app/network/quest_snapshot_decoder.py:260 _is_sha256.
- Cause : len(value)==64 + bytes.fromhex(value) ne garantit pas 32 octets hexadécimaux : fromhex ignore les espaces internes. La même fonction est dupliquée dans seize modules ; la liste complète des chemins/lignes est dans reproductions.json/sha256_validators.
- Preuve audit : «aa» + 60 espaces + «bb» a longueur 64 et décode 2 octets. Les seize helpers l’acceptent. sha-parser-reproduction.json : parse_protocol_mapping accepte le manifeste et ProtocolMappingRegistry.select retourne usable=true/exact_match pour cette fausse empreinte. Aucun contournement avec une vraie empreinte Unity n’a été démontré.
- Correction du registre : Valider exactement 64 caractères ASCII hexadécimaux et/ou exactement 32 octets sans whitespace. Réutiliser une unique fonction légère dans app/network/contracts.py ; garder les règles de normalisation aux frontières et les types stricts.

### AT-019 — Les primitives de profil ont deux propriétaires identiques
- Priorité / état : P2 / CONFIRMÉ / main.
- Localisation : app/storage.py:622 default_profiles; app/storage.py:638 profile_bool; app/storage.py:645 parse_zaap_click_position; app/core/profile_settings.py:27 default_profiles; app/core/profile_settings.py:43 profile_bool; app/core/profile_settings.py:50 parse_zaap_click_position; app/core/profile_settings.py:64 parse_unit_ratio; app/core/zaap_shortcuts.py:12 parse_unit_ratio.
- Cause : Les corps AST sont identiques pour les defaults, conversion bool, coordonnées et ratio. Le découplage léger du core est utile ; conserver deux implémentations métier n’est pas nécessaire.
- Preuve audit : exact-duplicates.json et code relu ; source-impact-storage.out liste les chemins consommateurs. storage utilise déjà le parseur ratio canonique Zaap.
- Correction du registre : Importer/re-exporter les trois primitives depuis core/profile_settings dans storage, puis faire utiliser le parseur ratio existant de core/zaap_shortcuts par profile_settings. Conserver les noms publics et ne jamais faire importer storage/Qt par le core.

### AT-020 — Le runtime manuel surcharge inutilement trois méthodes du core
- Priorité / état : P2 / CONFIRMÉ / main.
- Localisation : app/modules/encyclopedia/services/guide_ultime_manual_runtime_service.py:18 _structured_rows_from_fields; app/modules/encyclopedia/services/guide_ultime_manual_runtime_service.py:28 _link_next_cards; app/modules/encyclopedia/services/guide_ultime_manual_runtime_service.py:44 _stage_to_card; app/modules/encyclopedia/services/guide_ultime_manual_runtime_core.py:1604 _link_next_cards.
- Cause : Deux overrides se contentent d’appeler super avec les mêmes arguments ; _link_next_cards recopie exactement le corps du core. Les vraies adaptations _stage_lines/manual_sections_for_card sont utiles et doivent rester.
- Preuve audit : AST exact du corps _link_next_cards et lecture des deux forwarding overrides. La séparation policy/core n’est pas déclarée inutile.
- Correction du registre : Supprimer uniquement les overrides neutres dans un lot ciblé ; garder la classe, la façade de compatibilité et les transformations Phase 7E.

## Implémentation attendue
1. Définir un _is_sha256 strict dans app/network/contracts.py : exactement 64 caractères ASCII hex, aucun espace, 32 octets réels.
2. Remplacer les 16 validateurs réseau duplicatifs après inventaire des imports et signatures ; conserver les APIs de compatibilité si requises.
3. Déplacer une seule source de vérité pour default_profiles/profile_bool/parse_zaap_click_position ; re-export ciblé depuis storage sans importer Qt dans core.
4. Réutiliser parse_unit_ratio du propriétaire core/zaap_shortcuts, après parité des comportements.
5. Supprimer uniquement les overrides forwards neutres du runtime manuel dont l’héritage maintient le comportement ; préserver le renderer partagé.

## Validations ciblées
- [ ] tests SHA strict / registres / mappings réseau
- [ ] tests profil/storage/Zaap et imports sans Qt
- [ ] tests route manuelle, héritage et signatures publiques
- [ ] Doctor Graphify comparatif pour nouveaux cycles

## Critères de sortie
- [ ] Les empreintes hex malformées précédemment acceptées sont rejetées.
- [ ] Aucun consumer ou point d’entrée cassé.
- [ ] Aucune nouvelle dépendance circulaire import-time.
- [ ] Pas de fusion de fichiers entiers ni migration des JSON.

## Garde-fous communs
- Conserver toutes les fonctionnalités, les sources JSON et le comportement lazy sauf correction justifiée.
- Vérifier HEAD réel, git status et diff avant de coder. Aucun refactor de masse fondé sur le seul degré Graphify.
- Faire tests ciblés pendant le développement ; FULL uniquement à la certification si la policy l'exige.
- Recouper les observations avec les preuves de PR #160 ; distinguer CONFIRMÉ, PROBABLE, NON CONFIRMÉ.
- Mettre à jour AI Context avec son générateur après code, puis preuve exacte-SHA.
- Pas de merge automatique de cette PR préparatoire.

Sources : [rapport intégral](https://github.com/r9327/Dof-Atlas/blob/docs/audit-integral-2026-10-14/docs/audits/AUDIT_INTEGRAL_DOFUS_ATLAS_2026-10-14.md) ; [registre anomalies](https://github.com/r9327/Dof-Atlas/blob/docs/audit-integral-2026-10-14/docs/audits/2026-10-14-ac07be9b/registres/anomalies.json).
