# ROAD IA — task profiles, quality/consumption routing and RTK

## Goal

Use a small work card for each AI task so the execution layer can propose a sensible quality/consumption level for that task topology, then select the lowest-consumption configured model tier that satisfies the quality actually chosen.

This system is completely independent from Atlas Doctor validation levels. Doctor SOFT/MEDIUM/HARD decides how code is checked; task profiles decide how much AI quality/consumption to spend on doing the work. Neither system may infer or weaken the other.

The policy is stored in `.ai/task_profiles.json`. The router is `tools.agent_task_profiles`.

## Quality / consumption offers

- `economy` / **Eco**: low consumption, suitable for reading, navigation, tiny edits and other bounded work.
- `balanced` / **Standard**: moderate consumption and the default best quality/consumption ratio for normal implementation work.
- `best` / **Premium**: high consumption and maximum configured quality when the task or the user benefits from deeper reasoning.

Each task topology only provides a recommendation. If the user explicitly chooses another quality, that choice wins. The selected tier is then the eligible tier with the lowest `consumption_rank` that satisfies the chosen quality.

Provider prices are deliberately not embedded in repository policy because prices and model availability change independently of the codebase.

## Model mapping

Actual model identifiers are injected through environment variables:

```powershell
$env:DOF_AI_MODEL_ECONOMY = "<cheap-model-id>"
$env:DOF_AI_MODEL_BALANCED = "<balanced-model-id>"
$env:DOF_AI_MODEL_PREMIUM = "<premium-model-id>"
```

If those variables are absent, the router still returns the stable tier, quality rank, consumption rank, consumption label and reasoning effort. An external agent/orchestrator can map the tier to its own provider configuration.

## Usage

Automatic task inference from the task topology, accepting the recommended quality:

```powershell
py -3.13 -m tools.agent_task_profiles --task auto --path app/modules/example.py --json
```

Explicit normal feature with Standard quality:

```powershell
py -3.13 -m tools.agent_task_profiles --task feature --quality balanced --json
```

A structural task recommends Premium, but an explicit Eco choice is still honored:

```powershell
py -3.13 -m tools.agent_task_profiles --task structural --quality economy --json
```

Atlas Doctor remains separate and is run according to its own validation policy regardless of the AI quality/consumption tier selected here.

## RTK on Windows / Codex

RTK is development tooling only; it is not an application runtime dependency.

Run once from PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/install_rtk.ps1
```

The installer uses the official Winget package `rtk-ai.rtk`, verifies the binary with `rtk --version` and `rtk gain`, installs `ripgrep` when missing, then configures the global Codex integration with `rtk init -g --codex`.

Use `-Project` if a repository-scoped Codex integration is preferred:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/install_rtk.ps1 -Project
```

Restart Codex after initialization so its hook is reloaded.
