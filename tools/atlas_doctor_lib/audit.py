from __future__ import annotations

import ast
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .core import Issue, git_state, milliseconds, severity_counts, tracked_files, utc_now, verdict_from_counts, write_json
from .gates import run_integrity_gate

UI_SCOPES = ('app/ui/', 'app/pages/', 'app/modules/encyclopedia/views/', 'app/modules/encyclopedia/widgets/')
RUNTIME_SUFFIXES = ('.lock', '.sqlite-wal', '.sqlite-shm', '.prof', '.pstats', '.dmp', '.dump')
RUNTIME_PREFIXES = ('artifacts/', 'logs/', '.ai/runtime/')
ENTRYPOINT_NAMES = {'main.py', 'launch.py', '__main__.py', '__init__.py'}
LEGACY_MARKERS = ('legacy', 'deprecated', 'obsolete', 'lightweight', 'placeholder', 'fallback')
THREAD_CALLS = {'QThread', 'Thread', 'threading.Thread', 'threading.Timer', 'ThreadPoolExecutor', 'concurrent.futures.ThreadPoolExecutor'}


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


def _direct_blocking_call(name: str) -> bool:
    blocking_suffixes = (
        'sleep',
        'wait',
        'exec',
        'get',
        'join',
        'acquire',
        'read',
        'readline',
        'read_item',
        'recv',
        'recvfrom',
        'accept',
        'urlopen',
        'select',
    )
    return bool(name) and name.endswith(blocking_suffixes)


def _blocking_function_names(tree: ast.AST) -> set[str]:
    """Return local functions that transitively perform a blocking operation."""

    functions = {
        node.name: node
        for node in getattr(tree, 'body', [])
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    blocking = {
        name
        for name, function in functions.items()
        if any(
            isinstance(child, ast.Call) and _direct_blocking_call(_call_name(child))
            for child in ast.walk(function)
        )
    }
    changed = True
    while changed:
        changed = False
        for name, function in functions.items():
            if name in blocking:
                continue
            if any(
                isinstance(child, ast.Call) and _call_name(child).split('.')[-1] in blocking
                for child in ast.walk(function)
            ):
                blocking.add(name)
                changed = True
    return blocking


def _contains_blocking_call(node: ast.While, blocking_functions: set[str]) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            name = _call_name(child)
            if _direct_blocking_call(name) or name.split('.')[-1] in blocking_functions:
                return True
    return False


def _submitted_function_node_ids(tree: ast.AST) -> set[int]:
    submitted_names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _call_name(node).endswith('.submit') or not node.args:
            continue
        callback = node.args[0]
        if isinstance(callback, ast.Name):
            submitted_names.add(callback.id)
    background_nodes: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in submitted_names:
            background_nodes.update(id(child) for child in ast.walk(node))
    return background_nodes


def _single_load_cached_function_node_ids(tree: ast.AST) -> set[int]:
    """Return nodes in zero-argument functions cached to a single result."""

    cached_nodes: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = node.args
        if args.posonlyargs or args.args or args.kwonlyargs or args.vararg or args.kwarg:
            continue
        bounded = False
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call) and _call_name(decorator).endswith('lru_cache'):
                maxsize = next(
                    (
                        keyword.value.value
                        for keyword in decorator.keywords
                        if keyword.arg == 'maxsize' and isinstance(keyword.value, ast.Constant)
                    ),
                    None,
                )
                bounded = maxsize == 1
            elif isinstance(decorator, ast.Name) and decorator.id == 'cache':
                bounded = True
            elif (
                isinstance(decorator, ast.Attribute)
                and decorator.attr == 'cache'
                and isinstance(decorator.value, ast.Name)
                and decorator.value.id == 'functools'
            ):
                bounded = True
        if bounded:
            cached_nodes.update(id(child) for child in ast.walk(node))
    return cached_nodes


def _expression_key(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return ''


def _managed_worker_call_ids(tree: ast.AST) -> set[int]:
    """Prove common deterministic worker ownership patterns statically."""

    managed: set[int] = set()
    terminal_owners: set[str] = set()
    for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
        if isinstance(call.func, ast.Attribute) and call.func.attr in {
            'join', 'shutdown', 'quit', 'wait', 'cancel'
        }:
            owner = _expression_key(call.func.value)
            if owner:
                terminal_owners.add(owner)
        if _call_name(call) in {'atexit.register', 'register'} and call.args:
            callback = call.args[0]
            if isinstance(callback, ast.Attribute) and callback.attr in {
                'shutdown', 'quit', 'cancel'
            }:
                owner = _expression_key(callback.value)
                if owner:
                    terminal_owners.add(owner)

    assignments: list[tuple[ast.Call, list[str]]] = []
    for statement in ast.walk(tree):
        if isinstance(statement, ast.Assign) and isinstance(statement.value, ast.Call):
            names = [_expression_key(target) for target in statement.targets]
            assignments.append((statement.value, names))
        elif isinstance(statement, ast.AnnAssign) and isinstance(statement.value, ast.Call):
            assignments.append((statement.value, [_expression_key(statement.target)]))
    for call, owners in assignments:
        if _call_name(call) in THREAD_CALLS and any(owner in terminal_owners for owner in owners):
            managed.add(id(call))

    for with_node in (node for node in ast.walk(tree) if isinstance(node, (ast.With, ast.AsyncWith))):
        for item in with_node.items:
            for call in (node for node in ast.walk(item.context_expr) if isinstance(node, ast.Call)):
                if _call_name(call) in THREAD_CALLS:
                    managed.add(id(call))

    bounded_targets: set[str] = set()
    for function in (
        node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ):
        has_unbounded_loop = any(
            isinstance(child, ast.While)
            and isinstance(child.test, ast.Constant)
            and child.test.value is True
            for child in ast.walk(function)
        )
        if not has_unbounded_loop:
            bounded_targets.add(function.name)
    for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
        if _call_name(call) not in THREAD_CALLS:
            continue
        daemon = any(
            keyword.arg == 'daemon'
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is True
            for keyword in call.keywords
        )
        target = next((keyword.value for keyword in call.keywords if keyword.arg == 'target'), None)
        if daemon and isinstance(target, ast.Name) and target.id in bounded_targets:
            managed.add(id(call))

    has_message_hook_stop = any(
        isinstance(node, ast.Call) and _call_name(node).endswith('stop_message_hook')
        for node in ast.walk(tree)
    )
    if has_message_hook_stop:
        for call, owners in assignments:
            if _call_name(call) in THREAD_CALLS and 'self._thread' in owners:
                managed.add(id(call))
    return managed


def _literal_module_targets(value: ast.AST) -> set[str]:
    targets: set[str] = set()
    if not isinstance(value, ast.Dict):
        return targets
    for item in value.values:
        if not isinstance(item, (ast.Tuple, ast.List)) or not item.elts:
            continue
        module = item.elts[0]
        if isinstance(module, ast.Constant) and isinstance(module.value, str) and '.' in module.value:
            targets.add(module.value)
    return targets


def _dynamic_import_targets(tree: ast.AST) -> set[str]:
    """Resolve the canonical mapping.get -> unpack -> import_module pattern."""

    mappings: dict[str, set[str]] = {}
    for statement in getattr(tree, 'body', []):
        if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
            continue
        target = statement.target if isinstance(statement, ast.AnnAssign) else (
            statement.targets[0] if len(statement.targets) == 1 else None
        )
        value = statement.value
        if isinstance(target, ast.Name) and value is not None:
            modules = _literal_module_targets(value)
            if modules:
                mappings[target.id] = modules

    resolved: set[str] = set()
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        imported_names = {
            call.args[0].id
            for call in ast.walk(function)
            if isinstance(call, ast.Call)
            and _call_name(call).split('.')[-1] == 'import_module'
            and call.args
            and isinstance(call.args[0], ast.Name)
        }
        if not imported_names:
            continue
        unpack_sources: dict[str, str] = {}
        mapping_lookups: dict[str, str] = {}
        for statement in ast.walk(function):
            if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
                continue
            target = statement.targets[0]
            if isinstance(target, (ast.Tuple, ast.List)) and isinstance(statement.value, ast.Name):
                for element in target.elts:
                    if isinstance(element, ast.Name):
                        unpack_sources[element.id] = statement.value.id
            if isinstance(target, ast.Name) and isinstance(statement.value, ast.Call):
                call = statement.value
                if (
                    isinstance(call.func, ast.Attribute)
                    and call.func.attr == 'get'
                    and isinstance(call.func.value, ast.Name)
                    and call.func.value.id in mappings
                ):
                    mapping_lookups[target.id] = call.func.value.id
        for imported_name in imported_names:
            source_name = unpack_sources.get(imported_name)
            mapping_name = mapping_lookups.get(source_name or '')
            if mapping_name:
                resolved.update(mappings[mapping_name])
    return resolved


def _controlled_exec_call_ids(tree: ast.AST) -> set[int]:
    """Recognize compile(..., filename, 'exec') in an explicit isolated namespace."""

    controlled: set[int] = set()
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        isolated_namespaces: set[str] = set()
        for statement in ast.walk(function):
            if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
                continue
            target = statement.target if isinstance(statement, ast.AnnAssign) else (
                statement.targets[0] if len(statement.targets) == 1 else None
            )
            if not isinstance(target, ast.Name) or not isinstance(statement.value, ast.Dict):
                continue
            keys = {
                key.value
                for key in statement.value.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            if {'__file__', '__name__'} <= keys and keys <= {
                '__file__', '__name__', '__package__', '__builtins__'
            }:
                isolated_namespaces.add(target.id)
        for call in ast.walk(function):
            if not isinstance(call, ast.Call) or _call_name(call) not in {'exec', 'builtins.exec'}:
                continue
            if len(call.args) != 2 or call.keywords or not isinstance(call.args[1], ast.Name):
                continue
            compiled = call.args[0]
            if (
                call.args[1].id in isolated_namespaces
                and isinstance(compiled, ast.Call)
                and _call_name(compiled) in {'compile', 'builtins.compile'}
                and len(compiled.args) >= 3
                and isinstance(compiled.args[2], ast.Constant)
                and compiled.args[2].value == 'exec'
                and not compiled.keywords
            ):
                controlled.add(id(call))
    return controlled


def _open_writes(node: ast.Call) -> bool:
    if _call_name(node) not in {'open', 'builtins.open', 'Path.open'}:
        return False
    mode = None
    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
        mode = node.args[1].value
    for keyword in node.keywords:
        if keyword.arg == 'mode' and isinstance(keyword.value, ast.Constant):
            mode = keyword.value.value
    return isinstance(mode, str) and any(flag in mode for flag in ('w', 'a', 'x', '+'))


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
    imports.update(_dynamic_import_targets(tree))
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

    blocking_functions = _blocking_function_names(tree)
    background_nodes = _submitted_function_node_ids(tree)
    single_load_cached_nodes = _single_load_cached_function_node_ids(tree)
    managed_worker_calls = _managed_worker_call_ids(tree)
    controlled_execs = _controlled_exec_call_ids(tree)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and any(alias.name == '*' for alias in node.names):
            issues.append(Issue('import_star', 'architecture', 'HIGH', 'confirmed', path, _line(node), 'Import wildcard interdit', ast.unparse(node), 'Remplacer par des imports explicites pour garder les dependances auditables.'))

        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            lowered_name = node.name.casefold()
            marker = next((item for item in LEGACY_MARKERS if item in lowered_name), None)
            if marker:
                issues.append(Issue('legacy_symbol_marker', 'legacy', 'INFO', 'suspect', path, _line(node), 'Symbole potentiellement legacy/obsolet', f'{node.name} contient {marker}', 'Verifier ses consommateurs et le contrat canonique avant toute suppression.'))

        if isinstance(node, ast.While) and isinstance(node.test, ast.Constant) and node.test.value is True:
            if path.startswith('app/') and not _contains_blocking_call(node, blocking_functions):
                issues.append(Issue('busy_loop_risk', 'performance', 'MEDIUM', 'suspect', path, _line(node), 'Boucle infinie sans attente bloquante visible', 'while True sans sleep/wait/get/join/acquire detecte statiquement', 'Verifier que cette boucle ne peut pas tourner a vide et consommer du CPU.'))

        if isinstance(node, ast.ExceptHandler):
            if node.body and all(isinstance(item, ast.Pass) for item in node.body):
                type_name = ast.unparse(node.type) if node.type is not None else 'bare except'
                issues.append(Issue('silent_exception', 'reliability', 'HIGH', 'confirmed', path, _line(node), 'Exception avalee silencieusement', f'{type_name} -> pass', 'Logger/remonter l erreur ou traiter explicitement le cas.'))

        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name in {'sys.path.append', 'sys.path.insert', 'sys.path.extend'}:
                issues.append(Issue('sys_path_hack', 'architecture', 'HIGH', 'confirmed', path, _line(node), 'Mutation de sys.path detectee', name, 'Corriger les imports/package plutot que modifier sys.path au runtime.'))
            if name in {'eval', 'exec', 'builtins.eval', 'builtins.exec'}:
                if id(node) in controlled_execs:
                    issues.append(Issue('controlled_dynamic_exec', 'reliability', 'INFO', 'confirmed', path, _line(node), 'Execution dynamique controlee et isolee', ast.unparse(node), 'Conserver uniquement pour un outil local teste; toute execution ordinaire reste interdite.'))
                else:
                    issues.append(Issue('dynamic_exec', 'reliability', 'HIGH', 'confirmed', path, _line(node), 'Execution dynamique de code', name, 'Verifier si cette execution est indispensable; preferer une API structuree et validee.'))
            if name.endswith('lru_cache'):
                maxsize_none = any(keyword.arg == 'maxsize' and isinstance(keyword.value, ast.Constant) and keyword.value.value is None for keyword in node.keywords)
                if maxsize_none:
                    issues.append(Issue('unbounded_cache', 'performance', 'MEDIUM', 'suspect', path, _line(node), 'Cache potentiellement non borne', ast.unparse(node), 'Verifier la cardinalite reelle; borner le cache si les cles peuvent croitre pendant une longue session.'))
            if (name in THREAD_CALLS or name.endswith('.QThread')) and not path.startswith('tests/'):
                if id(node) in managed_worker_calls:
                    issues.append(Issue('managed_worker_lifecycle', 'lifecycle', 'INFO', 'confirmed', path, _line(node), 'Worker avec terminaison statiquement prouvee', name, 'Conserver le stop/join/shutdown, la borne de concurrence et les tests de non-accumulation.'))
                else:
                    issues.append(Issue('worker_lifecycle_review', 'lifecycle', 'INFO', 'suspect', path, _line(node), 'Worker/thread a verifier', name, 'Verifier etat terminal, stop deterministe, join/quit et absence de worker orphelin.'))
            if name.endswith('QTimer') and not node.args and not node.keywords:
                issues.append(Issue('parentless_qtimer', 'lifecycle', 'LOW', 'suspect', path, _line(node), 'QTimer sans parent visible', name, 'Verifier son proprietaire, son arret et sa destruction a la fermeture de la vue/service.'))
            if path.startswith(UI_SCOPES) and (name.endswith(('write_text', 'write_bytes')) or _open_writes(node)):
                issues.append(Issue('ui_direct_file_write', 'persistence', 'MEDIUM', 'suspect', path, _line(node), 'Ecriture fichier directe depuis une couche UI', name, 'Verifier qu un service canonique de persistence n existe pas et que l ecriture est atomique/coordonneee.'))
            if path.startswith(UI_SCOPES) and id(node) not in background_nodes and name.endswith(('read_text', 'read_bytes')):
                if id(node) in single_load_cached_nodes:
                    issues.append(Issue('single_load_sync_io_ui', 'performance', 'INFO', 'confirmed', path, _line(node), 'I/O UI bornee a un chargement memoise', name, 'Conserver uniquement pour une petite donnee froide avec contrat de taille; les lectures ordinaires restent MEDIUM.'))
                else:
                    issues.append(Issue('sync_io_ui', 'performance', 'MEDIUM', 'suspect', path, _line(node), 'I/O synchrone potentielle dans une vue UI', name, 'Verifier si cet acces disque arrive sur le thread Qt; deplacer/cacher seulement si mesure utile.'))
            if path.startswith(UI_SCOPES) and id(node) not in background_nodes and name in {'open', 'builtins.open', 'json.load'}:
                issues.append(Issue('sync_io_ui', 'performance', 'MEDIUM', 'suspect', path, _line(node), 'I/O synchrone potentielle dans une vue UI', name, 'Verifier si cet acces disque arrive sur le thread Qt; deplacer/cacher seulement si mesure utile.'))
            if name.endswith('setStyleSheet') and path.startswith('app/'):
                issues.append(Issue('local_stylesheet', 'ui', 'LOW', 'suspect', path, _line(node), 'Style local a verifier', name, 'Verifier que ce style ne duplique pas theme.py/components.py; conserver si semantique locale legitime.'))

        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith('PySide6.QtWebEngine'):
            if 'equipment' not in path.lower():
                issues.append(Issue('qtwebengine_import_scope', 'performance', 'MEDIUM', 'suspect', path, _line(node), 'Import QtWebEngine hors zone attendue', node.module, 'Verifier qu il ne provoque pas le chargement de Chromium au demarrage.'))

    return tree, issues


def run_audit(
    root: Path,
    *,
    save: bool = True,
    integrity_mode: str | None = None,
    base_ref: str = 'HEAD',
) -> dict[str, Any]:
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
        path_marker = next((item for item in LEGACY_MARKERS if item in Path(path).stem.casefold()), None)
        if path_marker and path.startswith(('app/', 'local_dofus_data/')):
            issues.append(Issue('legacy_path_marker', 'legacy', 'INFO', 'suspect', path, None, 'Fichier potentiellement legacy/obsolet', f'Nom contient {path_marker}', 'Verifier imports, wiring runtime et tests avant toute suppression.'))
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

    integrity: dict[str, Any] | None = None
    if integrity_mode:
        integrity = run_integrity_gate(root, integrity_mode, base_ref=base_ref)
        integrity_report = integrity.get('report') or {}
        groups = integrity_report.get('groups') or {}
        for group_name, group in groups.items():
            if not isinstance(group, dict) or not group.get('required'):
                continue
            status = str(group.get('status', 'NOT_RUN')).upper()
            if status in {'PASS', 'MEASURED_ONLY'}:
                continue
            blockers = ', '.join(str(item) for item in group.get('blockers', []) if item)
            evidence = blockers or f'Atlas Integrity: {status}'
            issues.append(Issue(
                'integrity_gate_failure',
                'integrity',
                'HIGH',
                'confirmed',
                'tools/atlas_integrity.py',
                None,
                f'Gate {group_name} en echec',
                evidence,
                'Corriger la cause racine signalee par Atlas Integrity; ne pas affaiblir le gate.',
            ))
        if integrity.get('status') == 'TIMEOUT':
            issues.append(Issue(
                'integrity_gate_timeout',
                'integrity',
                'MEDIUM',
                'confirmed',
                'tools/atlas_integrity.py',
                None,
                f'Gate {str(integrity_mode).upper()} interrompu par timeout',
                str(integrity.get('reason', 'timeout')),
                'Relancer le gate seul et identifier le groupe trop lent ou bloque.',
            ))
        elif integrity.get('status') == 'FAIL' and not groups:
            issues.append(Issue(
                'integrity_gate_error',
                'integrity',
                'HIGH',
                'confirmed',
                'tools/atlas_integrity.py',
                None,
                f'Gate {str(integrity_mode).upper()} en echec',
                '\n'.join(integrity.get('stderr_tail', [])[-10:]) or 'Rapport Atlas Integrity indisponible',
                'Executer Atlas Integrity separement et corriger l erreur de configuration/execution.',
            ))

    issue_dicts = [issue.to_dict() for issue in issues]
    issue_dicts.sort(key=lambda item: ({'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3, 'INFO': 4}.get(item['severity'], 9), item['path'], item.get('line') or 0, item['rule']))
    counts = severity_counts(issue_dicts)
    categories = Counter(item['category'] for item in issue_dicts)
    confidence = Counter(item['confidence'] for item in issue_dicts)
    verdict = verdict_from_counts(counts)
    if integrity and integrity.get('status') == 'FAIL':
        verdict = 'FAIL'
    payload: dict[str, Any] = {
        'schema_version': 1,
        'kind': 'audit',
        'generated_at': utc_now(),
        'git': state,
        'integrity_mode': integrity_mode.upper() if integrity_mode else None,
        'integrity_base_ref': base_ref if integrity_mode else None,
        'integrity': integrity,
        'analysis_sources': {
            'static_ast': True,
            'tracked_files': True,
            'graph': False,
            'atlas_integrity': bool(integrity_mode),
        },
        'duration_ms': milliseconds(started),
        'summary': {
            'verdict': verdict,
            'tracked_files': len(files),
            'python_files_parsed': len(trees),
            'issues_total': len(issue_dicts),
            'severity': counts,
            'categories': dict(sorted(categories.items())),
            'confidence': dict(sorted(confidence.items())),
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
