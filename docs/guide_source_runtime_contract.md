# Imported Guide runtime contract — PR #363 / Phase 0

Status: **architecture and synthetic proof only**. No source guide is
automatically installed, registered or certified. This document defines the
runtime boundary for the eventual one-by-one certified import.

## Ownership and memory

- `tools.atlas_guide_pipeline` stages source documents **outside** the app.
  A candidate is SHA-pinned, read-only, `NOT_CERTIFIED`, and non-active.
  The staging pipeline cannot write into user Guide progress.
- `app/modules/encyclopedia/services/guide_shared_route_contract.py`
  projects one authored source guide into canonical card sections, preserving
  source action/step IDs. No runtime app module imports a `tools` module.
- `ImportedSourceManualRuntimeService` consumes **one explicitly supplied**
  already-projected route without opening the V5 generated artifacts or
  `guide_ultime_manual` manifest. It copies that one route into its own
  memory; **do not construct this service for all 95 guides at startup**.
- `ManualRouteGuidesView` accepts an optional map of explicitly supplied
  source services and a trusted per-route approval callback. The default map
  is empty, and without a callback, construction or selection fails closed.
  Existing `guide_complet` and `dofus_sylvestre` routing is unchanged.
- `SharedGuideManualView` remains the only renderer. It uses the same
  preparation, copy/travel, NPC, combat and navigation components as the two
  optimized guides; no second reader is allowed.

## Source progress and validation

- One Guide identity: `source_guide:<guide_id>`.
- One stable stage identity: `source:<guide_id>:<source_step_id>`.
- One character identity: `character:<id_dofus>`.
- `GuideProgressService` alone owns atomic persistence and multi-character
  compare-and-swap. The source service **never** writes under
  `guide_ultime_v5` or `catalog_manual:dofus_sylvestre`.
- A quest mentioned by an authored step is **not** sufficient automatic proof
  that the step is finished. Source automatic completion is disabled until
  guide-specific, independently verified evidence becomes available.
- A step with `hard_runtime_gates` is blocked unless its **own guide-specific
  evaluator** explicitly approves it for that particular character.
  A missing, failing or unqualified evaluator is not success.
- Both the manual progress setter and the shared multi-character validation
  button recheck runtime authorization on each write. Revocation must not
  leave a stale clickable page able to mutate progress.
- Locked progress navigation, preparation status and other manual states
  remain scoped to the source Guide's own progress identity.

## Exact trust boundary

The authorizer is injected by **trusted application composition**, not by a
candidate's `certified` field, a source JSON file, an exported URL or the
end-user Guide catalogue. Its future implementation must verify independent
certificate evidence against the exact packaged route bytes and block
withdrawn/invalid attestations.

A callback returning `True` in synthetic tests is **test scaffolding**, not
a production certificate. Until the verification/publishing owner exists,
do not wire `imported_source_services` into the production `EncyclopediaPage`
composition and do not expose unverified source routes on the Home catalogue.

Opening an authorized route by ID is implemented. **Home listing of certified
source entries, section ordering (Dofus, Alignment, Islands, Dimensions,
Events) and the public certificate loader are NOT implemented.** Do not mark
that scope complete based on synthetic navigation tests.

## Repeatable evidence

Targeted, source-only tests (Python 3.13):

```powershell
py -3.13 -m unittest -v tests.test_guide_imported_manual_runtime_service
py -3.13 -m unittest -v tests.test_guide_imported_manual_runtime_ui.ImportedSourceRouterQtTests
py -3.13 -m unittest -v tests.test_guide_manual_selected_validation.ImportedSourceSharedManualUiTests
```

The first suite belongs to the lightweight Scoped PR Feedback owner. Both
Qt suites run on Windows in the reused focused Doctor UI proof. Run
`tools.atlas_doctor agent plan/check/validate` on changed paths, consult
Graphify for the **exact final HEAD**, and carry out the complete
Phase Certification/Windows/DOFUS evidence only when the architecture and the
first pilot Guide are ready. Neither a successful stdlib suite nor an offscreen
Qt proof is final Guide certification.

## Pilot and scaling gates

1. Finish trusted certificate loader and Home catalogue mapping, with no
   global startup hydration.
2. Validate the source reader with one **fictional** projected route, including
   team validation/undo, prerequisites, and disabled authorization.
3. Only when the entire toolchain is ready, take one small real pilot guide
   (Cawotte or Dokoko), compare authored actions and displayed Guide against
   the source line-by-line, and refine the independent certificate until it
   verifies the actual in-app content at 100%.
4. Import each remaining authorized route **one by one**. No next guide until
   extraction, projection, display and per-guide certification are all 100%.
5. Preserve the two optimized existing routes and the Phase 8 RAM requirements;
   measure RAM only after the Guide is functionally complete.

## P0 GIMP-019 — coordinate copy versus opt-in Zaap

The shared Guide row has two independent actions. Clicking the bold `[x,y]`
always copies `/travel x,y` to the clipboard, whether or not Organizer's
travel callback is configured. It must never dispatch the character macro.

A compact cached local Zaap pictogram sits beside the displayed coordinate.
Only that icon tries an optimized route. On click, the shared UI asks the
trusted current Guide service for an optional
`plan_verified_zaap_travel((x, y), selected_character_keys)`. The result
must be the existing `GuideTravelPlan` with `ZAAP_THEN_TRAVEL`, an exact
matching destination, and exactly the connected selected characters. The
existing two-command Travel macro callback is invoked **only** when those
conditions hold. Missing route evidence, unavailable planner, unconnected
participants, a non-Zaap/direct plan or mismatched destination always
copies the classical `/travel x,y` instead; no fictitious Zaap is chosen.

The plan provider is an **optional, explicitly trusted composition input**:
this PR has not established any live verified Zaap/character-position
registry for imported guides. Do not treat the Qt icon or a synthetic test
callback as proof that an optimized route can be used in production.
Route planning is on-demand at click time and is never run while rendering
the Guide. The original optimized guides retain their shared renderer.

Focused contract tests:
`tests.test_guide_manual_selected_validation.ImportedSourceSharedManualUiTests`
(clipboard-only classic click, independent icon/fallback, verified synthetic
`GuideTravelPlan`, no planning during render). Run with Doctor
`agent plan/check/validate` and include Windows/DOFUS interaction proof
before marking GIMP-019 PASS. Status until then: **PENDING / NOT_RUN**.
