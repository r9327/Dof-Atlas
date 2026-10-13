"""Initialize the durable per-user directories for packaged Atlas builds."""
from __future__ import annotations

import shutil
from pathlib import Path


def prepare_user_data(executable: Path, user_root: Path) -> None:
    """Seed the new durable location without overwriting any existing user file.

    Frozen PyInstaller one-directory layouts store resource data in _internal.
    """
    user_root.mkdir(parents=True, exist_ok=True)
    bundle = executable.parent / "_internal"
    for source_rel, dest_rel in (
        ("data/local", "data/local"),
        ("data/routes", "data/routes"),
        ("data/client_profiles.json", "data/client_profiles.json"),
        ("data/client_index.json", "data/client_index.json"),
        ("data/client_index.ini", "data/client_index.ini"),
        ("data/bootstrap_status.txt", "data/bootstrap_status.txt"),
        ("config", "config"),
    ):
        src = bundle / source_rel
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
                relative = child.relative_to(src)
                output = dst / relative
                output.parent.mkdir(parents=True, exist_ok=True)
                if not output.exists():
                    shutil.copy2(child, output)
