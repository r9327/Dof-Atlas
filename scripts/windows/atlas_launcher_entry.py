"""PyInstaller entry point for the independent lightweight Atlas updater."""
from app.distribution.launcher import main

if __name__ == "__main__":
    raise SystemExit(main())
