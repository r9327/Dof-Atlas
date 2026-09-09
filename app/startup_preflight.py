from __future__ import annotations

import importlib.util
import py_compile
import sys
from pathlib import Path
from time import perf_counter


EXIT_OK = 0
EXIT_ENVIRONMENT = 10
EXIT_SYNTAX = 20
EXIT_UNEXPECTED = 30
_REQUIRED_MODULES = (
    "PySide6",
    "win32gui",
    "PySide6.QtWebEngineWidgets",
)


def check_environment() -> tuple[bool, str]:
    """Validate launch-critical modules without importing their runtime stacks.

    The preflight runs in a short-lived Python process immediately before the
    real application process. Importing PySide6/pywin32 here makes Windows load
    the same native modules twice on every launch. ``find_spec`` verifies that
    the configured interpreter can resolve each required module while leaving
    actual initialization to the application process that will keep using it.
    QtWebEngine remains fully lazy for the Equipment page.
    """

    for module_name in _REQUIRED_MODULES:
        try:
            available = importlib.util.find_spec(module_name) is not None
        except Exception as exc:
            return False, f"module probe failed: {module_name}: {type(exc).__name__}: {exc}"
        if not available:
            return False, f"required module unavailable: {module_name}"
    return True, ""


def compile_script(path: str | Path) -> tuple[bool, str]:
    script = Path(path)
    if not script.is_file():
        return False, f"application script missing: {script}"
    try:
        py_compile.compile(str(script), doraise=True)
    except py_compile.PyCompileError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, f"compile failed: {type(exc).__name__}: {exc}"
    return True, ""


def _elapsed_ms(started_at: float) -> str:
    return f"{max(0.0, (perf_counter() - started_at) * 1000.0):.1f}"


def main(argv: list[str] | None = None) -> int:
    started_at = perf_counter()
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print(
            f"startup preflight expects exactly one application script path elapsed_ms={_elapsed_ms(started_at)}",
            file=sys.stderr,
        )
        return EXIT_UNEXPECTED

    environment_ok, environment_error = check_environment()
    if not environment_ok:
        print(f"{environment_error} elapsed_ms={_elapsed_ms(started_at)}", file=sys.stderr)
        return EXIT_ENVIRONMENT

    syntax_ok, syntax_error = compile_script(args[0])
    if not syntax_ok:
        print(f"{syntax_error} elapsed_ms={_elapsed_ms(started_at)}", file=sys.stderr)
        return EXIT_SYNTAX

    print(f"startup preflight OK elapsed_ms={_elapsed_ms(started_at)}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
