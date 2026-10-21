# PR — Cycle de vie Qt et RAM stabilisée après navigation

## Objet
Reproduire, attribuer et corriger uniquement les rétentions réellement
observées lors de passages Home -> Quêtes -> Succès -> Guide -> Craft ->
Équipement -> Home, puis répétitions. Ne pas déclarer une fuite sur simple
absence de baisse immédiate du RSS.

## Contexte vérifié
`docs/audit-remediation/2026-10-14/11-runtime-probes.md` (PC-04) a
observé un wrapper temporairement retenu par un worker Python, puis libéré.
Ce scénario **ne prouve aucune fuite permanente**. L'audit recommande des
mesures natives et de vrais parcours avant de changer workers / Qt.

## Travail ciblé
- Mesures avant correctif : RSS application et process-tree (inclure
  Chromium lorsque lancé), objets Qt vivants, workers, timers, caches et
  temps de stabilisation ; relevés cold/hot, 5 à 10 cycles identiques.
- Cibler `app/modules/encyclopedia/views/encyclopedia_page.py`,
  `app/modules/encyclopedia/views/memory_bound_encyclopedia_page.py`,
  providers et propriétaires réels seulement si la preuve les implique.
- Si rétention anormale reproductible : patch minimal d'ownership /
  désabonnement / fin de worker, avec test de destruction et de navigation.
- Garder l'architecture lazy, la progression, les caches Warm bornés, le
  singleton de l'application, le chargement différé QtWebEngine.

## Critères de sortie
- [ ] Rapport Windows réel avant/après, même environnement et SHA identifié.
- [ ] Distinction explicite : mémoire transitoire, cache voulu, rétention
  anormale ; pas de libération cosmétique ni garbage collect forcé comme
  « solution ».
- [ ] Cycles répétés sans croissance monotone non justifiée.
- [ ] Objectif projet : RSS application stabilisé proche de 100 Mo
  (<100 Mo après retour Home si atteignable sans régression), pic
  process-tree ≤250 Mo pour le parcours normal ; chiffres mesurés, jamais
  inventés. Distinguer test RAM de la certification fonctionnelle.
- [ ] Tests ciblés Qt / processus Windows / Doctor sans affaiblir seuils.
- [ ] Aucun changement non justifié des modules #225/#226, du launcher #228
  ou de l'Organizer #227.

## Dépendances
Relire Graphify exact-SHA et vérifier tous les consommateurs avant tout
refactor structurel. Coordonner la validation finale avec #225/#226. Pas de
nouveau système de monitoring ; réutiliser `benchmark_phase8_memory.py`
et les tests du cycle de vie existants. Draft jusqu'à correctif démontré.
**État initial : spécification uniquement.**
