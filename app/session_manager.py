from __future__ import annotations

try:
    from session_manager_pyside import main
except ModuleNotFoundError:
    from app.session_manager_pyside import main


if __name__ == "__main__":
    raise SystemExit(main())
