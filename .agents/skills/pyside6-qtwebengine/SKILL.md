---
name: pyside6-qtwebengine
description: Develop and verify Windows PySide6 and QtWebEngine interfaces with UI consistency, responsiveness and lifecycle safety.
---

# pyside6 qtwebengine

Use for views, widgets, web content, navigation, resize or UI regressions.

1. Read `AI_ENTRYPOINT.md`, `DEVELOPMENT_GUARDRAILS.md`, `PERFORMANCE_GUARDRAILS.md` and `app/AGENTS.md`.
2. Inspect existing screens, theme, components, navigation and service ownership before changing UI.
3. Check Qt thread affinity, signals, object lifetimes, loading, QWebEngine shutdown and heavy work on the UI thread.
4. Preserve visual consistency and test affected flows, clipping, scrolling, navigation and resizing on Windows when available.
5. Run relevant focused Doctor/Qt tests. A headless or offscreen check does not prove real Windows rendering.
6. Use exact-SHA Graphify when moving shared UI components or changing structural consumers.

Report screenshots or manual interactions only if actually captured or executed.
