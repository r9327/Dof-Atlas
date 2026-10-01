# ROAD IA — task profiles, quality/consumption routing and RTK

## Goal

Use a small work card for each AI task so the execution layer can select the lowest-consumption configured model tier that still satisfies the requested output quality and the minimum quality appropriate to the task topology.

This system is completely independent from Atlas Doctor validation levels. Doctor SOFT/MEDIUM/HARD decides how code is checked; task profiles decide how much AI quality/consumption to spend on doing the work. Neither system may infer or weaken the other.

The policy is stored in `.ai/task_profiles.json`. The router is `tools.agent_task_profiles`.

## Quality / consumption offers

- `economy` / **Eco**: low consumption, suitable for reading, navigation, tiny edits and other bounded low-risk work.
- `balanced` / **Standard**: moderate consumption and the default best quality/consumption ratio for normal implementation work.
- `best` / **Premium**: high consumption and maximum configured quality for structural work, certification work or an explicit maximum-quality request.

The user may request a quality level. A task profile may impose a higher minimum when using a lower tier would be unreasonable for that task topology. The selected tier is always the eligible tier with the lowest `consumption_rank`.

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

Automatic task inference from the task topology:

```powershell
py -3.13 -m tools.agent_task_profiles --task auto --quality economy --path app/modules/example.py --json
```

Explicit normal feature, using the default quality/consumption ratio:

```powershell
py -3.13 -m tools.agent_task_profiles --task feature --quality balanced --json
```

Structural work keeps its own task-quality floor even if a lower quality is requested:

```powershell
py -3.13 -m tools.agent_task_profiles --task structural --quality economy --json
```

This escalation concerns only the AI tier used to perform the task. Atlas Doctor remains separate and is run according to its own validation policy.

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
