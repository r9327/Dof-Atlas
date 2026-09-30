from __future__ import annotations

import argparse
import json

from tools.guide_tools_doctor import doctor


def main() -> int:
    parser = argparse.ArgumentParser(prog="guide-tools")
    parser.add_argument("command", choices=("doctor",))
    args = parser.parse_args()
    if args.command == "doctor":
        payload = doctor()
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload["ok"] else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
