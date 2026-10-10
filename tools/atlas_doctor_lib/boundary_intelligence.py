from __future__ import annotations

"""Source-confirmed, advisory Python layering evidence for Doctor Atlas."""
import ast
from pathlib import Path
from typing import Any

MAX_SOURCES = 150
MAX_BYTES = 512 * 1024
MAX_ROWS = 80


def _layer(path: str) -> str:
    if path.startswith("app/core/"):
        return "core"
    if path.startswith("app/services/") or (
        path.startswith("app/modules/") and "/services/" in path
    ):
        return "service"
    if path.startswith("app/pages/") or path.startswith("app/ui/") or (
        path.startswith("app/modules/") and
        ("/views/" in path or "/widgets/" in path)
    ):
        return "ui"
    if path.startswith("app/"):
        return "app_other"
    if path.startswith("tools/"):
        return "tools"
    return "other"


def layer_boundary_review(root: Path, paths: list[str]) -> dict[str, Any]:
    """Check actual imports, not graph edge speculation.

    For core/services -> UI, report architectural review leads. A source
    import is proven but that does not by itself prove the design is wrong.
    """
    root = root.resolve()
    requested = sorted(set(paths))
    issues: list[dict[str, Any]] = []
    errors: list[str] = []
    checked = 0
    for relative in requested[:MAX_SOURCES]:
        path = Path(relative)
        if (path.is_absolute() or ".." in path.parts or "\\" in relative
                or not relative.endswith(".py")):
            errors.append(f"{relative}: invalid path")
            continue
        candidate = root / path
        if (candidate.is_symlink() or not candidate.is_file()
                or not candidate.resolve().is_relative_to(root)):
            errors.append(f"{relative}: missing or symlink")
            continue
        try:
            if candidate.stat().st_size > MAX_BYTES:
                raise ValueError("SOURCE_SIZE_LIMIT")
            tree = ast.parse(candidate.read_text(encoding="utf-8-sig"),
                             filename=relative)
        except (OSError, UnicodeError, SyntaxError, ValueError) as exc:
            errors.append(f"{relative}: {type(exc).__name__}")
            continue
        checked += 1
        current = _layer(relative)
        if current not in {"core", "service", "app_other", "ui"}:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                # Resolve explicit relative imports with Python package rules.
                # A submodule imported as "from . import item" is checked only
                # if the matching Python file actually exists in this tree.
                if node.level:
                    package = relative.removesuffix(".py").split("/")[:-1]
                    if node.level > len(package):
                        continue
                    parts = package[:len(package) - node.level + 1]
                else:
                    parts = []
                if node.module:
                    parts += node.module.split(".")
                if not parts or not all(part.isidentifier() for part in parts):
                    continue
                modules = [".".join(parts)]
                modules.extend(
                    ".".join([*parts, alias.name])
                    for alias in node.names if alias.name != "*"
                    and alias.name.isidentifier()
                )
            else:
                continue
            for module in dict.fromkeys(modules):
                parts = module.split(".")
                if not parts or not all(part.isidentifier() for part in parts):
                    continue
                target = root.joinpath(*parts)
                available = [target.with_suffix(".py"), target / "__init__.py"]
                resolved_modules = [item for item in available if item.is_file()
                                    and not item.is_symlink()
                                    and item.resolve().is_relative_to(root)]
                if not resolved_modules:
                    # An unproven imported symbol is not automatically a module.
                    continue
                destination = _layer(resolved_modules[0].relative_to(root).as_posix())
                target_relative = resolved_modules[0].relative_to(root).as_posix()
                rule = None
                if current in {"core", "service"} and destination == "ui":
                    rule = "LOWER_LAYER_IMPORTS_UI"
                elif current in {"app_other", "core", "service", "ui"} and destination == "tools":
                    rule = "APP_IMPORTS_TOOLS"
                # Cross-domain dependencies on private UI widgets are review leads.
                source_parts = relative.split("/")
                target_parts = target_relative.split("/")
                if (len(source_parts) > 3 and len(target_parts) > 3
                        and source_parts[:2] == ["app", "modules"]
                        and target_parts[:2] == ["app", "modules"]
                        and source_parts[2] != target_parts[2]
                        and ("views" in target_parts[3:]
                             or "widgets" in target_parts[3:])):
                    issues.append({
                        "source": relative, "line": node.lineno,
                        "target_file": target_relative,
                        "source_domain": source_parts[2],
                        "target_domain": target_parts[2],
                        "rule": "CROSS_DOMAIN_PRIVATE_UI_IMPORT",
                        "confidence": "CURRENT_SOURCE_STATIC_IMPORT",
                        "review_only": True,
                    })
                if not rule:
                    continue
                issues.append({"source": relative, "line": node.lineno,
                               "imported_module": module, "source_layer": current,
                               "target_layer": destination, "rule": rule,
                               "confidence": "CURRENT_SOURCE_STATIC_IMPORT",
                               "review_only": True})
    truncated = len(requested) > MAX_SOURCES or len(issues) > MAX_ROWS or bool(errors)
    return {
        "kind": "doctor_layer_boundary_review",
        "status": "REVIEW" if issues or truncated else "PASS",
        "findings": issues[:MAX_ROWS], "total_findings": len(issues),
        "files_inspected": checked, "errors": errors[:MAX_ROWS],
        "truncated": truncated, "safe_to_refactor": False,
        "tests_executed": False,
        "limits": "Up to 150 source files, 512 KiB each and 80 findings. Confirmed import syntax is an advisory boundary lead, not proof of a bug.",
    }
