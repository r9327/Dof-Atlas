# GUIDE ULTIME — ÉTAT CANONIQUE

Dernière mise à jour : 25 septembre 2026 (Europe/Paris)

## Statut

Le manifeste canonique `data/routes/guide_ultime_manual/manifest_v1.json` déclare actuellement la route Guide Ultime `CERTIFIED`.

Ce document est une carte de reprise, pas un certificat de CI. Pour savoir si un HEAD précis est valide, utiliser les tests et la Phase Certification exécutés sur ce SHA exact. Ne jamais transporter un ancien PASS ou un ancien blocker vers un nouveau HEAD sans preuve machine actuelle.

## Sources de vérité

- manifeste : `data/routes/guide_ultime_manual/manifest_v1.json` ;
- verrou canonique : `data/routes/guide_ultime_manual/canonical_lock_v1.json` ;
- composition/chargement : `app/modules/encyclopedia/services/guide_ultime_manual_route.py` ;
- runtime : `app/modules/encyclopedia/services/guide_ultime_manual_runtime_service.py` ;
- UI : `app/modules/encyclopedia/views/guide_ultime_manual_view.py` ;
- règles de certification : `PHASE_CERTIFICATION.md`.

En cas de contradiction, le dépôt courant, le manifeste courant et les validations du SHA courant priment sur ce document.

## Route canonique courante

Le manifeste contient 13 chapitres et 267 macro-fiches :

- `incarnam_v2.json` — 9 ;
- `astrub_v5.json` — 16 ;
- `pandala_access_v1.json` — 2 ;
- `amakna_40_60_v5.json` — 10 ;
- `level_51_70_v4.json` — 7 ;
- `level_70_100_v10.json` — 17 ;
- `level_100_120_v9.json` — 17 ;
- `level_120_150_v21.json` — 37 ;
- `level_150_170_v21.json` — 24 ;
- `level_171_180_v13.json` — 30 ;
- `level_181_190_v15.json` — 24 ;
- `level_191_200_v22.json` — 62 ;
- `level_200_plus_v11.json` — 12.

Routes transversales/conditionnelles importantes : Bonta `bonta_1_100_v17.json`, Ordres 20/40/60/80/100, `temporal_registry_v15.json`, `ocre_capture_registry_v1.json`, `ocre_final_route_v2.json` et `success_contracts_v2.json`.

Le total de 267 est un état courant, pas une contrainte de conception. Une évolution future peut le modifier si le parcours canonique l’exige et si les audits restent verts.

## Contrats à préserver

- prérequis et ordre causal réellement valides ;
- couverture finale cohérente avec le catalogue courant ;
- aucune quête/succès/progression perdue silencieusement ;
- Guide, Quêtes et Succès synchronisés via leurs services/catalogues canoniques ;
- identité personnage persistée uniquement sous `character:<id_dofus>` ;
- pas de deuxième source de vérité ou de fallback historique pour masquer une erreur ;
- pas de reconstruction globale ou `load_all()` inutile dans le chemin UI.

`GUIDE_PREREQUISITE_DATA` et `GUIDE_FINAL_COVERAGE` sont des noms de contrôles, pas des dettes réputées actives par défaut. Ils ne redeviennent blockers que si une validation du HEAD courant les remonte réellement en échec.

## Reprise d’un chantier Guide

Commencer par l’état Git réel puis :

```text
py -3.13 -m tools.ai_context status
py -3.13 -m tools.ai_context route <fichiers concernés>
```

Exécuter les tests ciblés proposés, puis élargir selon le risque. Toute modification de contenu Guide nécessitant une certification doit être validée avec les fixtures/catalogues officiels et le certificateur canonique, sans affaiblir baseline, audit ou budget pour obtenir du vert.
