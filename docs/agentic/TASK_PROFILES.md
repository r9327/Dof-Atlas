# ROAD IA — task profiles, cost routing and RTK

## Goal

Use a small work card for each AI task so the execution layer can select the cheapest configured model tier that still satisfies the requested quality and the repository risk floor.

The policy is stored in `.ai/task_profiles.json`. The router is `tools.agent_task_profiles`.

## Quality levels

- `economy`: lowest cost for bounded, low-risk work.
- `balanced`: default for normal implementation work.
- `best`: highest quality for structural, certification or explicitly high-quality work.

The requested quality is a preference, not permission to weaken safety. `MEDIUM` work has at least a `balanced` floor and `HARD` work has at least a `best` floor. Structural and certification task profiles also force their own minimum quality.

The selected model tier is the eligible tier with the lowest `cost_rank`. Numeric provider prices are deliberately not embedded in repository policy because they change independently of the codebase.

## Model mapping

Actual model identifiers are injected through environment variables:

```powershell
$env:DOF_AI_MODEL_ECONOMY = "<cheap-model-id>"
$env:DOF_AI_MODEL_BALANCED = "<balanced-model-id>"
$env:DOF_AI_MODEL_PREMIUM = "<premium-model-id>"
```

If those variables are absent, the router still returns the stable tier, quality rank, cost rank and reasoning effort. An external agent/orchestrator can map the tier to its own provider configuration.

## Usage

Automatic task inference from path topology and work depth:

```powershell
py -3.13 -m tools.agent_task_profiles --task auto --quality economy --depth SOFT --path app/modules/example.py --json
```

Explicit feature quality:

```powershell
py -3.13 -m tools.agent_task_profiles --task feature --quality balanced --depth MEDIUM --json
```

Structural work cannot be downgraded even if `economy` is requested:

```powershell
py -3.13 -m tools.agent_task_profiles --task structural --quality economy --depth HARD --json
```

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
