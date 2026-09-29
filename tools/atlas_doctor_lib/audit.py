from __future__ import annotations

import ast
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .core import Issue, git_state, milliseconds, severity_counts, tracked_files, utc_now, verdict_from_counts, write_json

UI_SCOPES = ('app/ui/', 'app/pages/', 'app/modules/encyclopedia/views/', 'app/modules/encyclopedia/widgets/')
RUNTIME_SUFFIXES = ('.lock', '.sqlite-wal', '.sqlite-shm', '.prof', '.pstats', '.dmp', '.dump')
RUNTIME_PREFIXES = ('artifacts/', 'logs/', '.ai/runtime/')
ENTRYPOINT_NAMES = {'main.py', 'launch.py', '__main__.py', '__init__.py'}


def _module_name(path: str) -> str:
    return path[:-3].replace('/', '.') if path.endswith('.py') else ''


def _line(node: ast.AST) -> int | None:
    value = getattr(node, 'lineno', None)
    return int(value) if isinstance(value, int) else None


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        parts: list[str] = [func.attr]
        current = func.value
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return '.'.join(reversed(parts))
    return ''


def _has_main_guard(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        try:
            rendered = ast.unparse(node.test)
        except Exception:
            continue
        if '__name__' in rendered and '__main__' in rendered:
            return True
    return False


def _collect_imports(tree: ast.AST, current_module: str) -> set[str]:
    imports: set[str] = set()
    package = current_module.rsplit('.', 1)[0] if '.' in current_module else ''
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ''
            if node.level:
                base_parts = package.split('.') if package else []
                trim = max(0, node.level - 1)
                if trim:
                    base_parts = base_parts[:-trim] if trim <= len(base_parts) else []
                prefix = '.'.join(base_parts)
                module = '.'.join(part for part in (prefix, module) if part)
            if module:
                imports.add(module)
                imports.update(f'{module}.{alias.name}' for alias in node.names if alias.name != '*')
    return imports


def _scan_python(path: str, full: Path) -> tuple[ast.AST | None, list[Issue]]:
    issues: list[Issue] = []
    try:
        source = full.read_text(encoding='utf-8-sig')
    except (OSError, UnicodeError) as exc:
        issues.append(Issue('python_read_error', 'code', 'HIGH', 'confirmed', path, None, 'Fichier Python illisible', str(exc), 'Corriger l encodage ou l acces au fichier.'))
        return None, issues
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        issues.append(Issue('python_syntax_error', 'code', 'CRITICAL', 'confirmed', path, exc.lineno, 'Erreur de syntaxe Python', exc.msg, 'Corriger la syntaxe avant toute autre validation.'))
        return None, issues

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.body and all(isinstance(item, ast.Pass) for item in node.body):
                type_name = ast.unparse(node.type) if node.type is not None else 'bare except'
                issues.append(Issue('silent_exception', 'reliability', 'HIGH', 'confirmed', path, _line(node), 'Exception avalee silencieusement', f'{type_name} -> pass', 'Logger/remonter l erreur ou traiter explicitement le cas.'))

        if isinstance(node, ast.Call):
            name = _call_name(node)
            if path.startswith(UI_SCOPES) and name.endswith(('read_text', 'read_bytes')):
                issues.append(Issue('sync_io_ui', 'performance', 'MEDIUM', 'suspect', path, _line(node), 'I/O synchrone potentielle dans une vue UI', name, 'Verifier si cet acces disque arrive sur le thread Qt; deplacer/cacher seulement si mesure utile.'))
            if path.startswith(UI_SCOPES) and name in {'open', 'builtins.open', 'json.load'}:
                issues.append(Issue('sync_io_ui', 'performance', 'MEDIUM', 'suspect', path, _line(node), 'I/O synchrone potentielle dans une vue UI', name, 'Verifier si cet acces disque arrive sur le thread Qt; deplacer/cacher seulement si mesure utile.'))
            if name.endswith('setStyleSheet') and path.startswith('app/'):
                issues.append(Issue('local_stylesheet', 'ui', 'LOW', 'suspect', path, _line(node), 'Style local a verifier', name, 'Verifier que ce style ne duplique pas theme.py/components.py; conserver si semantique locale legitime.'))

        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith('PySide6.QtWebEngine'):
            if 'equipment' not in path.lower():
                issues.append(Issue('qtwebengine_import_scope', 'performance', 'MEDIUM', 'suspect', path, _line(node), 'Import QtWebEngine hors zone attendue', node.module, 'Verifier qu il ne provoque pas le chargement de Chromium au demarrage.'))

    return tree, issues


def run_audit(root: Path, *, save: bool = True) -> dict[str, Any]:
    started = time.perf_counter()
    state = git_state(root)
    files = tracked_files(root)
    issues: list[Issue] = []
    trees: dict[str, ast.AST] = {}
    imports_by_file: dict[str, set[str]] = {}
    module_to_path: dict[str, str] = {}
    file_sizes: list[tuple[int, str]] = []

    for path in files:
        full = root / path
        if not full.is_file():
            continue
        try:
            size = full.stat().st_size
            file_sizes.append((size, path))
        except OSError:
            size = 0

        lower = path.lower()
        if lower.endswith(RUNTIME_SUFFIXES) or lower.startswith(RUNTIME_PREFIXES):
            issues.append(Issue('tracked_runtime_artifact', 'git', 'HIGH', 'confirmed', path, None, 'Artefact runtime suivi par Git', f'Fichier runtime/transitoire suivi ({size} octets)', 'Retirer du suivi Git et ajouter une regle ignoree si necessaire.'))

        if size >= 20 * 1024 * 1024:
            issues.append(Issue('large_tracked_file', 'git', 'MEDIUM', 'confirmed', path, None, 'Gros fichier suivi par Git', f'{size / 1024 / 1024:.1f} MiB', 'Verifier qu il s agit bien d une source necessaire et non d un artefact regenerable.'))

        if path.endswith('.py'):
            tree, python_issues = _scan_python(path, full)
            issues.extend(python_issues)
            if tree is not None:
                trees[path] = tree
                module = _module_name(path)
                module_to_path[module] = path
                imports_by_file[path] = _collect_imports(tree, module)

    imported: Counter[str] = Counter()
    for names in imports_by_file.values():
        for name in names:
            imported[name] += 1
            parts = name.split('.')
            for index in range(1, len(parts)):
                imported['.'.join(parts[:index])] += 1

    for module, path in module_to_path.items():
        if not path.startswith(('app/', 'local_dofus_data/')):
            continue
        if Path(path).name in ENTRYPOINT_NAMES or path.endswith('/__init__.py'):
            continue
        tree = trees[path]
        if imported.get(module, 0) == 0 and not _has_main_guard(tree):
            issues.append(Issue('unreferenced_module', 'dead_code', 'LOW', 'suspect', path, None, 'Module sans import statique detecte', f'Aucun import statique de {module} dans les fichiers Python suivis.', 'Verifier wiring dynamique, signaux, importlib et usages externes avant toute suppression.'))

    symbols: defaultdict[str, list[str]] = defaultdict(list)
    for path, tree in trees.items():
        if not path.startswith(('app/', 'local_dofus_data/')):
            continue
        for node in getattr(tree, 'body', []):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith('_'):
                symbols[node.name].append(path)
    for symbol, locations in symbols.items():
        unique = sorted(set(locations))
        if len(unique) >= 4:
            issues.append(Issue('repeated_symbol_name', 'architecture', 'INFO', 'suspect', unique[0], None, f'Symbole {symbol} present dans plusieurs modules', ', '.join(unique[:8]), 'Verifier uniquement si ces implementations portent réellement la meme responsabilite.'))

    issue_dicts = [issue.to_dict() for issue in issues]
    issue_dicts.sort(key=lambda item: ({'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3, 'INFO': 4}.get(item['severity'], 9), item['path'], item.get('line') or 0, item['rule']))
    counts = severity_counts(issue_dicts)
    payload: dict[str, Any] = {
        'schema_version': 1,
        'kind': 'audit',
        'generated_at': utc_now(),
        'git': state,
        'duration_ms': milliseconds(started),
        'summary': {
            'verdict': verdict_from_counts(counts),
            'tracked_files': len(files),
            'python_files_parsed': len(trees),
            'issues_total': len(issue_dicts),
            'severity': counts,
        },
        'issues': issue_dicts,
        'largest_tracked_files': [
            {'path': path, 'size_mb': round(size / 1024 / 1024, 3)}
            for size, path in sorted(file_sizes, reverse=True)[:20]
        ],
    }
    if save:
        write_json(root, 'latest_audit', payload, rotate=True)
    return payload
