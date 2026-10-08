---
name: find-docs
description: Retrieve up-to-date, version-specific public library documentation via Context7 CLI when the Context7 MCP connection is unavailable. Useful for PySide6, QtWebEngine and other external dependencies.
---

# Context7 library docs (Codex project skill)

Use the Context7 MCP tools first when connected. Use this CLI fallback only when MCP is unavailable; never duplicate the same documentation lookup through both.

Prerequisite: Node.js 18+ and npm/npx on the developer machine. Nothing is installed into the Dofus Atlas Python environment. `npx` downloads the CLI on demand and may ask for confirmation.

1. Resolve the exact library ID for the current question:

   ```powershell
   npx --yes ctx7@latest library "PySide6" "QWebEngineView signals and cleanup"
   ```

2. Use an ID returned by the previous command to query one specific documentation topic:

   ```powershell
   npx --yes ctx7@latest docs /ORG/PROJECT "QWebEngineView signal lifetime and cleanup"
   ```

   Replace `/ORG/PROJECT` with the actual result; never assume a library ID. Include a version when the task requires one. Keep requests short, public and specific. Never send private code, user data, credentials or API keys in a query.

3. Verify the answer against the repository's current sources, tests and guardrails. Context7 is external documentation, never an Atlas architecture policy or source of Dofus game data.

If Node/npx, Context7 or the quota is unavailable, use official library documentation and say so. Do not add npm packages to Atlas, change CI, or block a task solely because this optional lookup is inaccessible.

Optional authentication for higher limits (developer machine only, no committed keys):

```powershell
npx --yes ctx7@latest login
```

Official documentation: https://context7.com/docs/clients/cli
