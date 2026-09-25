# Data-local agent guidance

The root `AGENTS.md` and project guardrails still apply.

Inside `data/`:

- never fabricate Dofus facts, identifiers, coordinates or prerequisites;
- identify whether a file is canonical content, user persistence, cache/runtime output or compatibility data before editing it;
- preserve user data and migration compatibility for persistent formats;
- do not turn generated/runtime state into committed source data;
- Guide Ultime route data must follow the canonical manifest/chapter rules in `DEVELOPMENT_GUARDRAILS.md`;
- prefer a targeted data correction with evidence over broad regeneration when only a few records are wrong.
