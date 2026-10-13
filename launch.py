from __future__ import annotations


def main() -> int:
    import sys

    # A frozen executable is not a Python interpreter. It must explicitly
    # dispatch trusted workers instead of interpreting "-m module" as GUI args.
    if getattr(sys, "frozen", False) and sys.argv[1:2] == ["-m"]:
        import runpy

        worker = sys.argv[2] if len(sys.argv) >= 3 else ""
        permitted = {
            "app.craft_preload",
            "app.quest_catalog_details",
            "app.startup_cache_warmup",
            "app.startup_cache_domain_worker",
        }
        if worker not in permitted:
            print("Unsupported Atlas worker", file=sys.stderr)
            return 2
        sys.argv = [worker, *sys.argv[3:]]
        runpy.run_module(worker, run_name="__main__", alter_sys=True)
        return 0

    import main as app_main
    return int(app_main.main())


if __name__ == "__main__":
    raise SystemExit(main())
