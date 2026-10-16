# Décision pour chaque JSON suivi

SHA main ac07be9b894718f5e68e7c3a91016d7651e3065b. Consumers déclarés/lexicaux ne sont pas une certification runtime. Les données non suivies attendues sont traitées séparément dans le rapport.

| ID | Fichier | Octets | Format racine | Décision | Usage/adaptation |
|---|---|---:|---|---|---|
| JS-001 | `.ai/context_index.json` | 4082 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-002 | `.ai/task_profiles.json` | 1917 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-003 | `.github/rulesets/integration-branch.json` | 1115 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-004 | `.github/rulesets/max-security.json` | 1173 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-005 | `data/cartography/map_views.json` | 53039 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-006 | `data/cartography/sources.json` | 2782 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-007 | `data/cartography/worldmap_catalog.json` | 40384 | list | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-008 | `data/encyclopedia/guides/alignement_bonta.json` | 38297 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-009 | `data/encyclopedia/guides/alignement_brakmar.json` | 38800 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-010 | `data/encyclopedia/guides/catalog.json` | 4132 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-011 | `data/encyclopedia/guides/dofoozbz.json` | 5566 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-012 | `data/encyclopedia/guides/dofus_abyssal.json` | 13518 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-013 | `data/encyclopedia/guides/dofus_argente.json` | 28574 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-014 | `data/encyclopedia/guides/dofus_cawotte.json` | 17465 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-015 | `data/encyclopedia/guides/dofus_des_glaces.json` | 28397 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-016 | `data/encyclopedia/guides/dofus_des_veilleurs.json` | 6286 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-017 | `data/encyclopedia/guides/dofus_dom_de_pin.json` | 109685 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-018 | `data/encyclopedia/guides/dofus_du_cauchemar.json` | 97992 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-019 | `data/encyclopedia/guides/dofus_ebene.json` | 20833 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-020 | `data/encyclopedia/guides/dofus_emeraude.json` | 16241 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-021 | `data/encyclopedia/guides/dofus_forgelave.json` | 10343 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-022 | `data/encyclopedia/guides/dofus_ivoire.json` | 17197 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-023 | `data/encyclopedia/guides/dofus_nebuleux.json` | 42140 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-024 | `data/encyclopedia/guides/dofus_pourpre.json` | 16383 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-025 | `data/encyclopedia/guides/dofus_sylvestre.json` | 114113 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-026 | `data/encyclopedia/guides/dofus_tachete.json` | 20412 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-027 | `data/encyclopedia/guides/dofus_turquoise.json` | 16776 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-028 | `data/encyclopedia/guides/dofus_vulbis.json` | 5136 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-029 | `data/encyclopedia/guides/dokille.json` | 3352 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-030 | `data/encyclopedia/guides/dokoko.json` | 2740 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-031 | `data/encyclopedia/guides/dolmanax.json` | 1495 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-032 | `data/encyclopedia/guides/domakuro.json` | 3763 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-033 | `data/encyclopedia/guides/dorigami.json` | 16766 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-034 | `data/encyclopedia/guides/guide_complet.json` | 338238 | ? | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-035 | `data/encyclopedia/guides/manifest.json` | 72 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-036 | `data/encyclopedia/quests/image_manifest.json` | 28237353 | ? | CONSERVER | Provenance offline, consumer tooling ; pas de découpage runtime sans bénéfice démontré |
| JS-037 | `data/encyclopedia/quests/quests_enriched.json` | 72317050 | ? | CONSERVER | Conserver la source et offsets/SQLite existants ; shards dérivés expérimentaux seulement, pas de bascule UI |
| JS-038 | `data/encyclopedia/quests/source_mapping.json` | 1836299 | ? | CONSERVER | Conserver mapping IDs/URLs de provenance ; relations avec 1976 enrichissements vérifiées |
| JS-039 | `data/large_file_contracts.json` | 1404 | dict | NETTOYER | Contrat byte canonique multiplateforme AT-013 ; garder les deux sources et leur provenance |
| JS-040 | `data/local/zaaps.json` | 22414 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-041 | `data/network/protocol_research/backlog_v1.json` | 5340 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-042 | `data/network/protocol_research/dofus_3.6.10.10_quest_review_2026-08-30.json` | 7141 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-043 | `data/network/protocol_research/dofus_3.6.10.10_v1.json` | 12851 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-044 | `data/routes/guide_ultime_manual/amakna_40_60_v1.json` | 17144 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-045 | `data/routes/guide_ultime_manual/amakna_40_60_v2.json` | 2996 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-046 | `data/routes/guide_ultime_manual/amakna_40_60_v3.json` | 3086 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-047 | `data/routes/guide_ultime_manual/amakna_40_60_v4.json` | 4043 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-048 | `data/routes/guide_ultime_manual/amakna_40_60_v5.json` | 4820 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-049 | `data/routes/guide_ultime_manual/astrub_class_branches_v1.json` | 8194 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-050 | `data/routes/guide_ultime_manual/astrub_v1.json` | 38317 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-051 | `data/routes/guide_ultime_manual/astrub_v2.json` | 20422 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-052 | `data/routes/guide_ultime_manual/astrub_v3.json` | 8788 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-053 | `data/routes/guide_ultime_manual/astrub_v4.json` | 1833 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-054 | `data/routes/guide_ultime_manual/astrub_v5.json` | 12004 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-055 | `data/routes/guide_ultime_manual/astrub_v6.json` | 7040 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-056 | `data/routes/guide_ultime_manual/bonta_1_100_v11.json` | 12321 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-057 | `data/routes/guide_ultime_manual/bonta_1_100_v12.json` | 3577 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-058 | `data/routes/guide_ultime_manual/bonta_1_100_v13.json` | 2091 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-059 | `data/routes/guide_ultime_manual/bonta_1_100_v14.json` | 10072 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-060 | `data/routes/guide_ultime_manual/bonta_1_100_v15.json` | 10914 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-061 | `data/routes/guide_ultime_manual/bonta_1_100_v16.json` | 9809 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-062 | `data/routes/guide_ultime_manual/bonta_1_100_v17.json` | 8234 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-063 | `data/routes/guide_ultime_manual/bonta_1_20_v1.json` | 14256 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-064 | `data/routes/guide_ultime_manual/bonta_1_22_v2.json` | 7752 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-065 | `data/routes/guide_ultime_manual/bonta_1_40_v3.json` | 16430 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-066 | `data/routes/guide_ultime_manual/bonta_1_50_v4.json` | 9252 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-067 | `data/routes/guide_ultime_manual/bonta_1_60_v5.json` | 11087 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-068 | `data/routes/guide_ultime_manual/bonta_1_70_v6.json` | 12229 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-069 | `data/routes/guide_ultime_manual/bonta_1_70_v7.json` | 5178 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-070 | `data/routes/guide_ultime_manual/bonta_1_80_v7.json` | 12847 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-071 | `data/routes/guide_ultime_manual/bonta_1_80_v8.json` | 18599 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-072 | `data/routes/guide_ultime_manual/bonta_1_80_v9.json` | 884 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-073 | `data/routes/guide_ultime_manual/bonta_1_90_v10.json` | 19111 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-074 | `data/routes/guide_ultime_manual/bonta_order_rank100_v1.json` | 7813 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-075 | `data/routes/guide_ultime_manual/bonta_order_rank20_v1.json` | 3179 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-076 | `data/routes/guide_ultime_manual/bonta_order_rank40_v1.json` | 4902 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-077 | `data/routes/guide_ultime_manual/bonta_order_rank60_v1.json` | 4915 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-078 | `data/routes/guide_ultime_manual/bonta_order_rank80_v1.json` | 7992 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-079 | `data/routes/guide_ultime_manual/canonical_lock_v1.json` | 16094 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-080 | `data/routes/guide_ultime_manual/dofus_argente_coverage_v1.json` | 3497 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-081 | `data/routes/guide_ultime_manual/incarnam_v1.json` | 24783 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-082 | `data/routes/guide_ultime_manual/incarnam_v2.json` | 5463 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-083 | `data/routes/guide_ultime_manual/level_100_120_v1.json` | 25003 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-084 | `data/routes/guide_ultime_manual/level_100_120_v2.json` | 3127 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-085 | `data/routes/guide_ultime_manual/level_100_120_v3.json` | 3725 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-086 | `data/routes/guide_ultime_manual/level_100_120_v4.json` | 2422 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-087 | `data/routes/guide_ultime_manual/level_100_120_v5.json` | 2755 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-088 | `data/routes/guide_ultime_manual/level_100_120_v6.json` | 1530 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-089 | `data/routes/guide_ultime_manual/level_100_120_v7.json` | 8673 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-090 | `data/routes/guide_ultime_manual/level_100_120_v8.json` | 15502 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-091 | `data/routes/guide_ultime_manual/level_100_120_v9.json` | 616 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-092 | `data/routes/guide_ultime_manual/level_120_150_v1.json` | 35108 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-093 | `data/routes/guide_ultime_manual/level_120_150_v10.json` | 8844 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-094 | `data/routes/guide_ultime_manual/level_120_150_v11.json` | 4565 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-095 | `data/routes/guide_ultime_manual/level_120_150_v12.json` | 2720 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-096 | `data/routes/guide_ultime_manual/level_120_150_v13.json` | 924 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-097 | `data/routes/guide_ultime_manual/level_120_150_v14.json` | 3164 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-098 | `data/routes/guide_ultime_manual/level_120_150_v15.json` | 5535 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-099 | `data/routes/guide_ultime_manual/level_120_150_v16.json` | 801 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-100 | `data/routes/guide_ultime_manual/level_120_150_v17.json` | 1567 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-101 | `data/routes/guide_ultime_manual/level_120_150_v18.json` | 13337 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-102 | `data/routes/guide_ultime_manual/level_120_150_v19.json` | 25301 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-103 | `data/routes/guide_ultime_manual/level_120_150_v2.json` | 5040 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-104 | `data/routes/guide_ultime_manual/level_120_150_v20.json` | 2341 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-105 | `data/routes/guide_ultime_manual/level_120_150_v21.json` | 2267 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-106 | `data/routes/guide_ultime_manual/level_120_150_v3.json` | 15114 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-107 | `data/routes/guide_ultime_manual/level_120_150_v4.json` | 5330 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-108 | `data/routes/guide_ultime_manual/level_120_150_v5.json` | 5378 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-109 | `data/routes/guide_ultime_manual/level_120_150_v6.json` | 5003 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-110 | `data/routes/guide_ultime_manual/level_120_150_v7.json` | 3417 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-111 | `data/routes/guide_ultime_manual/level_120_150_v8.json` | 13659 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-112 | `data/routes/guide_ultime_manual/level_120_150_v9.json` | 5490 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-113 | `data/routes/guide_ultime_manual/level_150_170_v1.json` | 31286 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-114 | `data/routes/guide_ultime_manual/level_150_170_v10.json` | 5902 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-115 | `data/routes/guide_ultime_manual/level_150_170_v11.json` | 3267 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-116 | `data/routes/guide_ultime_manual/level_150_170_v12.json` | 3868 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-117 | `data/routes/guide_ultime_manual/level_150_170_v13.json` | 2418 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-118 | `data/routes/guide_ultime_manual/level_150_170_v14.json` | 4388 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-119 | `data/routes/guide_ultime_manual/level_150_170_v15.json` | 3107 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-120 | `data/routes/guide_ultime_manual/level_150_170_v16.json` | 730 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-121 | `data/routes/guide_ultime_manual/level_150_170_v17.json` | 719 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-122 | `data/routes/guide_ultime_manual/level_150_170_v18.json` | 2141 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-123 | `data/routes/guide_ultime_manual/level_150_170_v19.json` | 3040 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-124 | `data/routes/guide_ultime_manual/level_150_170_v2.json` | 1875 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-125 | `data/routes/guide_ultime_manual/level_150_170_v20.json` | 42224 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-126 | `data/routes/guide_ultime_manual/level_150_170_v21.json` | 2468 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-127 | `data/routes/guide_ultime_manual/level_150_170_v3.json` | 763 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-128 | `data/routes/guide_ultime_manual/level_150_170_v4.json` | 7509 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-129 | `data/routes/guide_ultime_manual/level_150_170_v5.json` | 4802 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-130 | `data/routes/guide_ultime_manual/level_150_170_v6.json` | 3652 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-131 | `data/routes/guide_ultime_manual/level_150_170_v7.json` | 6837 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-132 | `data/routes/guide_ultime_manual/level_150_170_v8.json` | 5227 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-133 | `data/routes/guide_ultime_manual/level_150_170_v9.json` | 5032 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-134 | `data/routes/guide_ultime_manual/level_171_180_v1.json` | 39914 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-135 | `data/routes/guide_ultime_manual/level_171_180_v10.json` | 742 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-136 | `data/routes/guide_ultime_manual/level_171_180_v11.json` | 5496 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-137 | `data/routes/guide_ultime_manual/level_171_180_v12.json` | 31955 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-138 | `data/routes/guide_ultime_manual/level_171_180_v13.json` | 749 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-139 | `data/routes/guide_ultime_manual/level_171_180_v2.json` | 2824 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-140 | `data/routes/guide_ultime_manual/level_171_180_v3.json` | 9914 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-141 | `data/routes/guide_ultime_manual/level_171_180_v4.json` | 6970 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-142 | `data/routes/guide_ultime_manual/level_171_180_v5.json` | 3163 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-143 | `data/routes/guide_ultime_manual/level_171_180_v6.json` | 2994 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-144 | `data/routes/guide_ultime_manual/level_171_180_v7.json` | 1703 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-145 | `data/routes/guide_ultime_manual/level_171_180_v8.json` | 2234 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-146 | `data/routes/guide_ultime_manual/level_171_180_v9.json` | 787 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-147 | `data/routes/guide_ultime_manual/level_181_190_v1.json` | 24752 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-148 | `data/routes/guide_ultime_manual/level_181_190_v10.json` | 803 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-149 | `data/routes/guide_ultime_manual/level_181_190_v11.json` | 863 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-150 | `data/routes/guide_ultime_manual/level_181_190_v12.json` | 2103 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-151 | `data/routes/guide_ultime_manual/level_181_190_v13.json` | 1424 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-152 | `data/routes/guide_ultime_manual/level_181_190_v14.json` | 33618 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-153 | `data/routes/guide_ultime_manual/level_181_190_v15.json` | 13708 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-154 | `data/routes/guide_ultime_manual/level_181_190_v2.json` | 16178 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-155 | `data/routes/guide_ultime_manual/level_181_190_v3.json` | 795 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-156 | `data/routes/guide_ultime_manual/level_181_190_v4.json` | 1499 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-157 | `data/routes/guide_ultime_manual/level_181_190_v5.json` | 6118 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-158 | `data/routes/guide_ultime_manual/level_181_190_v6.json` | 3959 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-159 | `data/routes/guide_ultime_manual/level_181_190_v7.json` | 6892 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-160 | `data/routes/guide_ultime_manual/level_181_190_v8.json` | 5413 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-161 | `data/routes/guide_ultime_manual/level_181_190_v9.json` | 805 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-162 | `data/routes/guide_ultime_manual/level_191_200_v1.json` | 18276 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-163 | `data/routes/guide_ultime_manual/level_191_200_v10.json` | 5506 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-164 | `data/routes/guide_ultime_manual/level_191_200_v11.json` | 6172 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-165 | `data/routes/guide_ultime_manual/level_191_200_v12.json` | 15478 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-166 | `data/routes/guide_ultime_manual/level_191_200_v15.json` | 10649 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-167 | `data/routes/guide_ultime_manual/level_191_200_v16.json` | 9765 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-168 | `data/routes/guide_ultime_manual/level_191_200_v17.json` | 10430 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-169 | `data/routes/guide_ultime_manual/level_191_200_v18.json` | 2821 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-170 | `data/routes/guide_ultime_manual/level_191_200_v19.json` | 13309 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-171 | `data/routes/guide_ultime_manual/level_191_200_v2.json` | 10737 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-172 | `data/routes/guide_ultime_manual/level_191_200_v20.json` | 42824 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-173 | `data/routes/guide_ultime_manual/level_191_200_v21.json` | 1229 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-174 | `data/routes/guide_ultime_manual/level_191_200_v22.json` | 15449 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-175 | `data/routes/guide_ultime_manual/level_191_200_v3.json` | 12423 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-176 | `data/routes/guide_ultime_manual/level_191_200_v4.json` | 14140 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-177 | `data/routes/guide_ultime_manual/level_191_200_v5.json` | 2129 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-178 | `data/routes/guide_ultime_manual/level_191_200_v6.json` | 11949 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-179 | `data/routes/guide_ultime_manual/level_191_200_v7.json` | 14235 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-180 | `data/routes/guide_ultime_manual/level_191_200_v8.json` | 20310 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-181 | `data/routes/guide_ultime_manual/level_191_200_v9.json` | 876 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-182 | `data/routes/guide_ultime_manual/level_200_plus_v1.json` | 15039 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-183 | `data/routes/guide_ultime_manual/level_200_plus_v10.json` | 783 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-184 | `data/routes/guide_ultime_manual/level_200_plus_v11.json` | 28600 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-185 | `data/routes/guide_ultime_manual/level_200_plus_v2.json` | 22071 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-186 | `data/routes/guide_ultime_manual/level_200_plus_v3.json` | 10341 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-187 | `data/routes/guide_ultime_manual/level_200_plus_v4.json` | 13366 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-188 | `data/routes/guide_ultime_manual/level_200_plus_v5.json` | 3006 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-189 | `data/routes/guide_ultime_manual/level_200_plus_v6.json` | 791 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-190 | `data/routes/guide_ultime_manual/level_200_plus_v7.json` | 2633 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-191 | `data/routes/guide_ultime_manual/level_200_plus_v8.json` | 8832 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-192 | `data/routes/guide_ultime_manual/level_200_plus_v9.json` | 25706 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-193 | `data/routes/guide_ultime_manual/level_51_70_v1.json` | 13710 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-194 | `data/routes/guide_ultime_manual/level_51_70_v2.json` | 3346 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-195 | `data/routes/guide_ultime_manual/level_51_70_v3.json` | 10694 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-196 | `data/routes/guide_ultime_manual/level_51_70_v4.json` | 801 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-197 | `data/routes/guide_ultime_manual/level_70_100_v1.json` | 24359 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-198 | `data/routes/guide_ultime_manual/level_70_100_v10.json` | 10251 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-199 | `data/routes/guide_ultime_manual/level_70_100_v2.json` | 5120 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-200 | `data/routes/guide_ultime_manual/level_70_100_v3.json` | 8125 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-201 | `data/routes/guide_ultime_manual/level_70_100_v4.json` | 2678 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-202 | `data/routes/guide_ultime_manual/level_70_100_v5.json` | 3373 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-203 | `data/routes/guide_ultime_manual/level_70_100_v6.json` | 3585 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-204 | `data/routes/guide_ultime_manual/level_70_100_v7.json` | 1395 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-205 | `data/routes/guide_ultime_manual/level_70_100_v8.json` | 5507 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-206 | `data/routes/guide_ultime_manual/level_70_100_v9.json` | 25542 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-207 | `data/routes/guide_ultime_manual/manifest_v1.json` | 35057 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-208 | `data/routes/guide_ultime_manual/ocre_capture_registry_v1.json` | 4548 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-209 | `data/routes/guide_ultime_manual/ocre_completion_route_v1.json` | 8555 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-210 | `data/routes/guide_ultime_manual/ocre_completion_route_v2.json` | 1878 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-211 | `data/routes/guide_ultime_manual/ocre_final_route_v1.json` | 341 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-212 | `data/routes/guide_ultime_manual/ocre_final_route_v2.json` | 399 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-213 | `data/routes/guide_ultime_manual/pandala_access_v1.json` | 7513 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-214 | `data/routes/guide_ultime_manual/success_contracts_enutrosor_v1.json` | 1757 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-215 | `data/routes/guide_ultime_manual/success_contracts_pandala_v1.json` | 1473 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-216 | `data/routes/guide_ultime_manual/success_contracts_v1.json` | 7457 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-217 | `data/routes/guide_ultime_manual/success_contracts_v2.json` | 10300 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-218 | `data/routes/guide_ultime_manual/temporal_registry_v1.json` | 4850 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-219 | `data/routes/guide_ultime_manual/temporal_registry_v10.json` | 1492 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-220 | `data/routes/guide_ultime_manual/temporal_registry_v11.json` | 1699 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-221 | `data/routes/guide_ultime_manual/temporal_registry_v12.json` | 2607 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-222 | `data/routes/guide_ultime_manual/temporal_registry_v13.json` | 5447 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-223 | `data/routes/guide_ultime_manual/temporal_registry_v14.json` | 2666 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-224 | `data/routes/guide_ultime_manual/temporal_registry_v15.json` | 3943 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-225 | `data/routes/guide_ultime_manual/temporal_registry_v2.json` | 12289 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-226 | `data/routes/guide_ultime_manual/temporal_registry_v3.json` | 2368 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-227 | `data/routes/guide_ultime_manual/temporal_registry_v4.json` | 5251 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-228 | `data/routes/guide_ultime_manual/temporal_registry_v5.json` | 3121 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-229 | `data/routes/guide_ultime_manual/temporal_registry_v6.json` | 4183 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-230 | `data/routes/guide_ultime_manual/temporal_registry_v7.json` | 2387 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-231 | `data/routes/guide_ultime_manual/temporal_registry_v8.json` | 2602 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-232 | `data/routes/guide_ultime_manual/temporal_registry_v9.json` | 3474 | dict | CONSERVER | Conserver la composition manifeste + overlays/registries/canonical_lock ; ne pas supprimer une version sur son suffixe |
| JS-233 | `tests/critical_regression_inventory.json` | 10083 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-234 | `tools/atlas_critical_coverage.json` | 892 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-235 | `tools/atlas_fault_injection.json` | 1908 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-236 | `tools/atlas_integrity_policy.json` | 8749 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-237 | `tools/atlas_performance_budgets.json` | 1494 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-238 | `tools/guide_phase2_baseline.json` | 1303 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-239 | `tools/guide_ultime_master_2026-08-22.json` | 59600 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
| JS-240 | `tools/ponytail_policy.json` | 3303 | dict | CONSERVER | Aucune migration justifiée par les données accessibles |
