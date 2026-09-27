# App-local agent guidance

The root `AGENTS.md` and project guardrails still apply.

Inside `app/`:

- inspect consumers/imports before replacing a service, provider or source of truth;
- keep the dependency direction simple: core/domain -> services -> UI;
- reuse canonical persistence and identity services instead of writing shared state directly from widgets;
- keep expensive or bulk work off the Qt UI thread when practical;
- preserve startup/lifecycle behavior unless the task explicitly changes it;
- for UI work, reuse `app/ui/theme.py`, `app/ui/components.py` and current shared patterns before adding local styling;
- do not create a second lightweight/placeholder UI that is later replaced by another equivalent final UI unless the product explicitly requires that state.

Use `py -3.13 -m tools.ai_context route <path>` to identify extra context for the files being changed.
