# Atlas Guide Conformity — clean candidate

Status: prototype under development. No certification is claimed.
Clean branch: feat/atlas-guide-importer-clean-20261102, created at main@060803282269098dfc6919e6e85f24309d2c485f.
No commit, file, module or runtime code from abandoned PR #337 was imported.
The original PR #363 has not yet been moved to this branch.

## Scope

tools.atlas_guide_conformity compares an independently collected, authorized guide reference
with two successive Atlas representations. Offline, read-only and no Qt/runtime imports.
It reports missing and extra guides/steps/actions/fields, mismatched values or types,
order changes and duplicated stable IDs. Each discrepancy carries guide/step/action IDs,
field path, expected/actual values, source evidence reference and proposed correction.

The CLI writes before.json, after.json and before_after.json, with resolved, persistent
and introduced differences. A blocked comparison exits 1.

An exact JSON comparison is never gameplay or author-rights certification:
all reports explicitly contain certified=false.

## Data contract

Reference and Atlas snapshots contain a guides array. Stable identifiers are
guide_id, source_step_id and action_id. The reference also declares
reference_verified=true, rights_verified=true and complete=true. These flags
are input claims, NOT independent evidence; validate underlying permissions
and source parity separately. Evidence refs should identify source material
the user is authorized to consult. Do not publish protected source text in logs.

## Reproducible commands (full repository checkout)

    py -3.13 -m unittest tests.test_atlas_guide_conformity -v
    py -3.13 -m tools.atlas_guide_conformity --reference reference_authorized.json --before before_atlas.json --after after_atlas.json --output-dir artifacts/guide_conformity

## Remaining mandatory checks (not done)

- Build an authorized real-source extractor for all 95 guides and every step.
- Validate independence and completeness of each source, then per-guide compliance.
- Add one secure transactional publisher with crash recovery, no bypass.
- Attach only to already-existing main UI services without copying PR #337.
- Run Doctor/Graphify at exact SHA before any structural or destructive changes.
- Run repository tests, Qt/Windows/DOFUS manual verification, benchmarks and CI.
- Complete GIMP-001 through GIMP-011 and exact-SHA delivery evidence.

Current proof: GitHub clean branch creation and ancestry review only.
Local Doctor, Graphify and automated tests remain NOT_RUN in this session.
