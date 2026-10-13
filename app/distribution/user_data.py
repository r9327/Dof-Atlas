"""Initialize durable user data once per installed version, without overwrites."""
from __future__ import annotations

import shutil
from pathlib import Path

_USER_PATHS = (
    ("data/local", "data/local"),
    ("data/routes", "data/routes"),
    ("data/client_profiles.json", "data/client_profiles.json"),
    ("data/client_index.json", "data/client_index.json"),
    ("data/client_index.ini", "data/client_index.ini"),
    ("data/bootstrap_status.txt", "data/bootstrap_status.txt"),
    ("config", "config"),
)


def prepare_user_data(executable: Path, user_root: Path,
                      legacy_root: Path | None = None) -> None:
    """Seed missing user files from a legacy source clone, then from the bundle.

    Existing saved profiles/progress always take precedence. Sources are scanned
    only on the first launch of each frozen package; later launches stay fast.
    """
    user_root.mkdir(parents=True, exist_ok=True)
    marker = user_root / ".initialized" / (executable.parent.parent.name + ".ready")
    if marker.is_file():
        return
    sources = [executable.parent / "_internal"]
    if legacy_root is not None and (legacy_root / "DOFUS.bat").is_file():
        sources.insert(0, legacy_root)
    for root in sources:
        for source_rel, dest_rel in _USER_PATHS:
            src = root / source_rel
            dst = user_root / dest_rel
            if src.is_symlink():
                continue
            if src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                if not dst.exists():
                    shutil.copy2(src, dst)
            elif src.is_dir():
                dst.mkdir(parents=True, exist_ok=True)
                for child in src.rglob("*"):
                    if child.is_symlink() or not child.is_file():
                        continue
                    output = dst / child.relative_to(src)
                    output.parent.mkdir(parents=True, exist_ok=True)
                    if not output.exists():
                        shutil.copy2(child, output)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("ready\n", encoding="utf-8")
