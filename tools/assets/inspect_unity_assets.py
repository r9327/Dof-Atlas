"""Offline integrity inventory for local DOFUS Unity reference assets.

This is not a licence check or a Qt/Windows visual certification. Read-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import zlib
from collections import defaultdict
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "app/assets/themes/dofus_unity"
BACKGROUND_SHA256 = "3834e92f6432019e2fde2b5f0ccb7f3b2236fda48ea7a6d368c60a660ef5fdeb"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
FONT_MAGIC = {b"\x00\x01\x00\x00", b"OTTO", b"true"}


def png_info(path: Path) -> tuple[int, int, int]:
    """Validate PNG fixed-size IHDR only; avoid decoding all image payloads."""
    with path.open("rb") as stream:
        header = stream.read(33)
    if len(header) != 33 or header[:8] != PNG_MAGIC:
        raise ValueError("missing PNG signature/IHDR")
    if struct.unpack(">I", header[8:12])[0] != 13 or header[12:16] != b"IHDR":
        raise ValueError("invalid PNG IHDR")
    if zlib.crc32(header[12:29]) != struct.unpack(">I", header[29:33])[0]:
        raise ValueError("PNG IHDR CRC mismatch")
    width, height, depth, colour = struct.unpack(">IIBB", header[16:26])
    if not (1 <= width <= 16384 and 1 <= height <= 16384 and depth in (1, 2, 4, 8, 16)):
        raise ValueError("invalid or excessive PNG dimensions/depth")
    if colour not in (0, 2, 3, 4, 6):
        raise ValueError("unknown PNG colour type")
    return width, height, colour


def inventory(root: Path) -> dict:
    root = root.resolve()
    issues: list[str] = []
    images = []
    hashes: dict[str, list[str]] = defaultdict(list)
    sprites = sorted((root / "sprites").glob("*.png"))
    fonts = sorted((root / "fonts").glob("*.ttf"))
    if len(sprites) != 46:
        issues.append(f"expected 46 sprites; found {len(sprites)}")
    if len(fonts) != 10:
        issues.append(f"expected 10 reference TTFs; found {len(fonts)}")
    for path in (
        root / "background_selection_original.png",
        root / "references/logoDofus.png",
        *sprites,
    ):
        name = path.relative_to(root).as_posix()
        if not path.is_file():
            issues.append(f"missing: {name}")
            continue
        try:
            width, height, colour = png_info(path)
        except (OSError, ValueError) as exc:
            issues.append(f"invalid PNG {name}: {exc}")
            continue
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        hashes[digest].append(name)
        images.append({
            "file": name, "width": width, "height": height,
            "colour_type": colour, "sha256": digest,
        })
        if name == "background_selection_original.png" and (
            (width, height) != (1919, 1079) or digest != BACKGROUND_SHA256
        ):
            issues.append("background does not match the source dimensions/SHA-256")
    for path in fonts:
        with path.open("rb") as stream:
            if stream.read(4) not in FONT_MAGIC:
                issues.append(f"invalid TTF signature: {path.name}")
    return {
        "asset_root": str(root),
        "sprites": len(sprites),
        "reference_fonts": len(fonts),
        "images": images,
        "duplicate_png_content": [v for v in hashes.values() if len(v) > 1],
        "issues": issues,
        "integrity_pass": not issues,
        "redistribution_authorized": False,
        "note": "Integrity only; DOFUS references are not cleared for redistribution.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = inventory(args.root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Sprites: {result['sprites']}/46 | TTF references: {result['reference_fonts']}/10")
        print(f"PNG headers checked: {len(result['images'])} | duplicate sets: {len(result['duplicate_png_content'])}")
        for issue in result["issues"]:
            print(f"ERROR: {issue}")
        print("Rights: NOT VERIFIED; reference assets must not be redistributed")
    return 0 if result["integrity_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
