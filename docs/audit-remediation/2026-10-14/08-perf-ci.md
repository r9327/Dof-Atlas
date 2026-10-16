# [PLAN 08] Lectures de préfixes bornées et fixtures FULL mesurées (AT-012/018)

**AT-012 implémenté et AT-018 optimisé de façon ciblée ; mesures CI exact-SHA en attente.**

Source : audit [PR #160](https://github.com/r9327/Dof-Atlas/pull/160), SHA audité `ac07be9b894718f5e68e7c3a91016d7651e3065b`, anomalies **AT-012, AT-018**.

## Objectif
Supprimer les allocations de fichiers entiers pour des en-têtes de quelques octets et optimiser les fixtures coûteuses sans affaiblir la FULL.

## Fichiers et frontières à vérifier
- `tools/atlas_doctor_lib/audit.py`
- `tools/atlas_json_inventory.py`
- `tests/test_quests_guides_audit.py`
- `tests/test_lanyel_home_route_map_count.py`
- `tests/test_lanyel_shared_manual_ui.py`
- `tests/test_encyclopedia_final_mission.py`

## Implémentation prévue
1. Traiter AT-012 avant AT-018 : open('rb').read(N) et lecture limitée des SVG/BOM/LFS, pas read_bytes()[:N] qui alloue tout.
2. Conserver détection des pointers LFS malformés, et image signature ≠ preuve de décodage complet.
3. Mesurer phases de setUpClass : référence 226,708 s pour test_quests_guides_audit, ~45 s sur des fixtures Lanyel.
4. Réutiliser les fixtures immuables et artefacts exact-SHA ; jamais de singleton Qt mutable global.
5. Préserver les 2 555 tests FULL historiques, labels/tests/métier, random-order ciblé ; ne pas relancer une FULL jusqu’à stabilisation.

## Tests ciblés obligatoires
- [x] Test `test_bounded_prefix_io` avec fichier sparse de 72 317 050 octets, read(N) spy, BOM, SVG, LFS (validation CI à vérifier)
- [ ] tests.test_quests_guides_audit : timings de setUpClass désormais émis ; gate CI à vérifier
- [ ] tests Lanyel ciblés et ordre aléatoire : gate CI à vérifier
- [ ] timings avant/après sur mêmes données et SHA exact

## Dépendances
Après/avec PR #166 pour fiabilité des contrats ; une seule certification complète finale si justifiée.

## Critères de sortie
- [ ] Reproduction/contrat de départ documenté et corrigé par modification réelle du code.
- [ ] Aucun consumer ou scénario métier cassé ; différences revues précisément.
- [ ] Résultats avec niveau de preuve, provenance, limites de couverture et SHA exact.
- [ ] AI Context synchronisé via son générateur après changement de code.
- [ ] Tests ciblés verts ; FULL seulement à certification selon policy, pas en boucle.
- [ ] Pas de fusion automatique ni de renommage/découpage JSON arbitraire.

[Rapport intégral](https://github.com/r9327/Dof-Atlas/blob/docs/audit-integral-2026-10-14/docs/audits/AUDIT_INTEGRAL_DOFUS_ATLAS_2026-10-14.md) — [Registre de preuves](https://github.com/r9327/Dof-Atlas/blob/docs/audit-integral-2026-10-14/docs/audits/2026-10-14-ac07be9b/registres/anomalies.json).

## Correctifs réalisés et limites de preuve

- `local_dofus_data/utils.py` : `detect_encoding` passe de `read_bytes()[:4]` à `open('rb').read(4)`, compatible BOM UTF-8, UTF-16 et fichier court.
- `app/modules/encyclopedia/tools/audit_quests_guides.py` : détection SVG limitée à 512 octets et signatures PNG/JPEG/WebP/ICO limitées à 16 octets ; le dédoublonnage par SHA-256 est calculé en flux via `hashlib.file_digest`, sans allocation de l’image complète.
- `tests/test_quests_guides_audit.py` : la détection LFS lit au maximum 513 octets, vérifie **le pointeur entier** si la signature Git LFS est présente, refuse le pointeur malformé, et délègue l'image réelle au validateur existant. Une signature de format n'est pas une preuve de décodage complet.
- `tests/test_lanyel_home_route_map_count.py` et `tests/test_lanyel_shared_manual_ui.py` : `AchievementProvider.load_retained()` remplace `load_all()` dans le setup ; le détail Succès reste lazy et aucun singleton mutable Qt n'est partagé entre suites.
- Quatre classes `setUpClass` journalisent la durée totale (`AT018 fixture=... setup_ms=...`) sur le runner réel ; la référence historique de l'audit est de 226,708 s pour Quêtes/Guides et environ 45 s pour certaines fixtures Lanyel, **sur un autre run non comparable directement**. Les gains en secondes et les variations de RAM globales ne sont pas revendiqués sans baseline de même environnement/SHA.
- Aucun fichier métier JSON, parcours UI, contrôle d'intégrité ou règle FULL modifié. FULL uniquement lors de la certification finale si la politique la demande.
