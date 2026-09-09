from __future__ import annotations

import ast
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, order=True)
class SourceViolation:
    category: str
    relative_path: str
    line: int
    symbol: str
    reason: str

    @property
    def baseline_key(self) -> str:
        return f"{self.relative_path}:{self.symbol}"

    def diagnostic(self) -> str:
        return (
            f"{self.category}: {self.relative_path} ligne {self.line}: "
            f"{self.symbol} - {self.reason}"
        )


def read_source(path: Path) -> str:
    """Read Python or text sources while accepting an optional UTF-8 BOM."""

    return path.read_text(encoding="utf-8-sig")


def parse_source(path: Path, root: Path) -> ast.Module:
    relative = path.relative_to(root).as_posix()
    return ast.parse(read_source(path), filename=relative)


def runtime_python_files(root: Path) -> tuple[Path, ...]:
    candidates = [root / "main.py", root / "launch.py", *(root / "app").rglob("*.py")]
    return tuple(sorted(path for path in candidates if path.is_file()))


def _module_is_legacy(module: str) -> bool:
    return any(
        part == "legacy" or part.startswith("legacy_") or part.endswith("_legacy")
        for part in module.casefold().split(".")
    )


def legacy_import_violations(root: Path) -> list[SourceViolation]:
    violations: list[SourceViolation] = []
    for path in runtime_python_files(root):
        relative = path.relative_to(root).as_posix()
        tree = parse_source(path, root)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                symbols = [
                    f"import:{alias.name}"
                    + (f":as:{alias.asname}" if alias.asname else "")
                    for alias in node.names
                    if _module_is_legacy(alias.name)
                ]
            elif isinstance(node, ast.ImportFrom) and _module_is_legacy(node.module or ""):
                imported_symbols = ",".join(
                    sorted(
                        alias.name + (f":as:{alias.asname}" if alias.asname else "")
                        for alias in node.names
                    )
                )
                symbols = [f"from:{node.module}:import:{imported_symbols}"]
            else:
                continue
            for symbol in symbols:
                violations.append(
                    SourceViolation(
                        "Nouvel import runtime legacy",
                        relative,
                        node.lineno,
                        symbol,
                        "les dependances applicatives vers *_legacy doivent diminuer",
                    )
                )
    return sorted(violations)


_VERSIONED_FILE = re.compile(r"(?:^optimized_|^new_|_v[2-9][0-9]*(?:_|$))", re.IGNORECASE)
_VERSIONED_CLASS = re.compile(r"V[2-9][0-9]*(?=[A-Z_]|$)")


def runtime_version_violations(root: Path) -> list[SourceViolation]:
    violations: list[SourceViolation] = []
    for path in runtime_python_files(root):
        relative = path.relative_to(root).as_posix()
        if any(part in {"migrations", "styles", "tools"} for part in path.parts):
            continue
        if _VERSIONED_FILE.search(path.stem):
            violations.append(
                SourceViolation(
                    "Nouvelle implementation runtime versionnee",
                    relative,
                    1,
                    f"module:{path.stem}",
                    "les formats de donnees sont exclus, pas les implementations actives",
                )
            )
        tree = parse_source(path, root)
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and _VERSIONED_CLASS.search(node.name):
                violations.append(
                    SourceViolation(
                        "Nouvelle classe runtime versionnee",
                        relative,
                        node.lineno,
                        f"class:{node.name}",
                        "une responsabilite runtime ne doit pas gagner une nouvelle couche Vn",
                    )
                )
    return sorted(violations)


def _qualified_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _qualified_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _root_name(node: ast.AST) -> str:
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else ""


_PATCH_INSTALLER = re.compile(r"install_.*patch(?:es)?$")


def runtime_patch_violations(root: Path) -> list[SourceViolation]:
    violations: list[SourceViolation] = []
    for path in runtime_python_files(root):
        relative = path.relative_to(root).as_posix()
        if "/tools/" in f"/{relative}/":
            continue
        tree = parse_source(path, root)
        imported_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported_names.update(
                    alias.asname or alias.name for alias in node.names if alias.name != "*"
                )

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _PATCH_INSTALLER.fullmatch(node.name):
                violations.append(
                    SourceViolation(
                        "Nouvel installateur de runtime patch",
                        relative,
                        node.lineno,
                        f"installer:{node.name}",
                        "les installateurs historiques sont une baseline temporaire fermee",
                    )
                )
                continue

            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = node.value
                if not isinstance(value, (ast.Name, ast.Attribute, ast.Lambda)):
                    continue
                if isinstance(value, ast.Name) and value.id in {"self", "cls"}:
                    continue
                targets: Iterable[ast.expr] = node.targets if isinstance(node, ast.Assign) else (node.target,)
                for target in targets:
                    if not isinstance(target, ast.Attribute):
                        continue
                    root_name = _root_name(target)
                    if not (
                        root_name in imported_names
                        or root_name.endswith("_class")
                        or (root_name and root_name[0].isupper())
                    ):
                        continue
                    target_name = _qualified_name(target)
                    if target_name == "sys.excepthook":
                        continue
                    violations.append(
                        SourceViolation(
                            "Nouveau rebinding runtime",
                            relative,
                            node.lineno,
                            f"rebind:{target_name}",
                            "une methode ou un symbole importe est remplace apres sa definition",
                        )
                    )
                continue

            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "setattr"
                and len(node.args) >= 2
            ):
                continue
            root_name = _root_name(node.args[0])
            if not (
                root_name in imported_names
                or root_name.endswith("_class")
                or (root_name and root_name[0].isupper())
            ):
                continue
            attribute = (
                repr(node.args[1].value)
                if isinstance(node.args[1], ast.Constant)
                else ast.unparse(node.args[1])
            )
            violations.append(
                SourceViolation(
                    "Nouveau setattr runtime sur classe/module",
                    relative,
                    node.lineno,
                    f"setattr:{_qualified_name(node.args[0])}:{attribute}",
                    "l'augmentation dynamique des classes/modules est interdite hors baseline",
                )
            )
    return sorted(violations)


def format_unexpected(violations: Iterable[SourceViolation]) -> str:
    return "\n".join(violation.diagnostic() for violation in violations)


def baseline_keys(violations: Iterable[SourceViolation]) -> tuple[str, ...]:
    return tuple(sorted(violation.baseline_key for violation in violations))


def string_constants(tree: ast.AST) -> Iterator[tuple[int, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.lineno, node.value
