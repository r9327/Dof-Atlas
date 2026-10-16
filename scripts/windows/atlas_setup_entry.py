"""Frozen Windows installer entrypoint: bundled launcher and one desktop shortcut."""
from app.distribution.setup import main

if __name__ == "__main__":
    raise SystemExit(main())
