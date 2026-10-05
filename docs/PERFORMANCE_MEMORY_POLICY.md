# Dofus Atlas — Memory policy

Phase 8 establishes memory as an architectural contract, not a late optimization pass.

## Product target

- Keep the application close to 100 MB RSS in normal stabilized use.
- Preload only compact data that removes latency without retaining heavy UI objects.
- Heavy views must not make memory grow monotonically across navigation cycles.
- Future modules (Bestiaire, native equipment rooms, additional encyclopedia domains) must follow the same lifecycle and cache rules.

## Runtime model

Atlas separates three states:

1. **Resident** — shell, navigation, user state, compact indexes and progress metadata.
2. **Warm** — prepared lookup/index data that avoids reparsing or rebuilding full catalogues.
3. **Active** — visible widgets, decoded images and detail models needed by the current screen.

Leaving a heavy screen must release or bound its Active resources while keeping compact Warm data reusable. A page must not rebuild its complete catalogue simply because the user comes back to it.

## Required rules

- Large catalogues expose compact indexes and detail-by-id access instead of retaining every full detail object for UI convenience.
- Lists render visible or bounded batches instead of creating one QWidget per catalogue entry.
- Decoded image caches are byte-bounded and item-bounded. Image policy is tuned only from measured evidence.
- WebEngine is not a default platform dependency for future modules. Any embedded browser must justify its process-tree memory cost against a native or external-browser alternative.
- Timers, workers, signal owners and temporary detail widgets must not keep inactive screens alive accidentally.
- New persistent caches require an explicit byte/item budget.

## Measurement contract

The Phase 8 staged memory benchmark records application RSS and complete descendant-process RSS at these checkpoints:

- startup stabilized;
- preload complete;
- Quests active and after return Home;
- Achievements active and after return Home;
- Guide active and after return Home;
- Craft active and after return Home;
- Equipment active and after return Home/stabilization.

This separates core application retention from QtWebEngine/Chromium child-process cost.

The benchmark evidence is the source of truth for future hard gates. Budgets must not be weakened to make regressions pass; the implementation must be optimized instead.
