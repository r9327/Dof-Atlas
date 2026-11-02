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


## Création structurée et utilisation commune (PR #363)

La création hors ligne se fait avec `tools.atlas_guide_importer` :
une seule source JSON v1 autorisée, `guides` ordonnés, IDs stables
`guide_id` / `source_step_id` / `action_id`, `rights_verified`,
`reference_verified`, `complete`. **Les drapeaux déclarent un état,
ils ne constituent jamais une preuve indépendante de droits ou de fidélité.**

    py -3.13 -m tools.atlas_guide_importer --source authorized_export.json
    py -3.13 -m tools.atlas_guide_importer --source authorized_export.json --output preview.json

Le mode complet exige exactement **95 guides et 7 705 étapes**.
`--partial` est disponible uniquement pour des lots explicitement incomplets,
sans possibilité de les qualifier de complets/certifiés. L'outil refuse
un fichier de sortie déjà présent, ne touche ni `data/` ni les sauvegardes,
n'installe aucune route et ne scrappe aucune source tierce.

L'adaptateur `guide_shared_route_contract.project_authorized_guide` forme
les cartes compatibles avec `SharedGuideManualCard` existant dans `main` :
IDs stables, positions au format `[x,y]` cliquables, objets/quantités,
PNJ/choix et combats structurés conservés. La **visualisation réellement
branchée à l'application et ses validations par personnage restent à faire**.

Commandes de test ciblé :

    py -3.13 -m unittest tests.test_atlas_guide_importer_preview tests.test_guide_shared_route_contract tests.test_atlas_guide_conformity -v

L'extracteur de source externe, le publieur protégé/transactionnel,
la preuve Graphify exact-SHA et la recette Windows/DOFUS ne sont pas livrés :
**tous les guides restent NOT_CERTIFIED**.
