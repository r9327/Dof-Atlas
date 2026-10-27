---
name: persistence-safety
description: Protect Dofus Atlas progress, SQLite, JSON, character identity and compatibility during storage changes.
---

# persistence safety

Use for persisted state, shared progress, configuration, JSON/SQLite data, migrations and identity.

1. Read `AI_ENTRYPOINT.md`, `DEVELOPMENT_GUARDRAILS.md` and `ZERO_TRUST_RULES.md`.
2. Identify the canonical writer, on-disk schema, readers, compatibility paths and user-owned data. Never test against live user saves.
3. Keep new character-scoped writes keyed by `character:<id_dofus>` and shared mutations consistent with `lock -> reload current -> mutate -> atomic write -> publish/invalidate -> unlock`.
4. For a migration, specify idempotence, backwards reads, version handling, crash recovery and a rollback or safe failure strategy.
5. For changed storage interfaces, inspect consumers with exact-SHA Graphify and current source.
6. Validate with disposable fixtures, scoped persistence/concurrency tests and the risk-appropriate Integrity Gate.

Do not claim data migration safety from JSON parsing alone or silently overwrite progress, config or WAL/SHM.
