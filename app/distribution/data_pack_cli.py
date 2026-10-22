"""Trusted local operator CLI for staged Atlas data-pack promotion.

It never edits game saves or runtime catalogues. Installer/certification must
authenticate the manifest and choose the allowed staging directory first.
A new pack stays pending until an independent runtime check acknowledges it.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .data_pack_plan import DataPack, InvalidDataPack
from .data_pack_store import acknowledge_pack, active_pack, install_pack, rollback_pack, recover_pending_packs

_KINDS = ("quests", "successes", "guides", "items", "equipment")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safe staged Atlas data-pack store")
    actions = parser.add_subparsers(dest="command", required=True)
    for action in ("install", "status", "acknowledge", "rollback"):
        sub = actions.add_parser(action)
        sub.add_argument("--root", type=Path, required=True)
        sub.add_argument("--kind", choices=_KINDS, required=True)
        if action == "install":
            sub.add_argument("--staging-root", type=Path, required=True)
            sub.add_argument("--revision", type=int, required=True)
            sub.add_argument("--schema-version", type=int, required=True)
            sub.add_argument("--sha256", required=True)
            sub.add_argument("--artifact-path", required=True)
    recovery = actions.add_parser("recover")
    recovery.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "recover":
            recovered = recover_pending_packs(args.root)
            status = "ROLLED_BACK_PENDING" if recovered else "NO_PENDING"
        elif args.command == "install":
            pack = DataPack(args.kind, args.revision, args.schema_version,
                            args.sha256, args.artifact_path)
            status = install_pack(args.root, args.staging_root, pack)
        elif args.command == "status":
            stored = active_pack(args.root, args.kind)
            status = "ACTIVE_VERIFIED" if stored is not None else "NOT_INSTALLED"
        elif args.command == "acknowledge":
            status = "ACKNOWLEDGED" if acknowledge_pack(args.root, args.kind) else "NOT_PENDING"
        else:
            status = "ROLLED_BACK" if rollback_pack(args.root, args.kind) else "NOT_PENDING"
    except (InvalidDataPack, ValueError, OSError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False),
              file=sys.stderr)
        return 2
    payload = {"status": status}
    if args.command == "recover":
        payload["recovered"] = list(recovered)
    else:
        payload["kind"] = args.kind
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
