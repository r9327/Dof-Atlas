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


def _is_runtime_code(path: str) -> bool:
    return path == 'main.py' or path.startswith('app/')


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


def _contains_blocking_call(node: ast.While) -> bool:
    blocking_suffixes = ('sleep', 'wait', 'exec', 'get', 'join', 'acquire')
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            name = _call_name(child)
            if name.endswith(blocking_suffixes):
                return True
    return False


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
    return imports


def _append_observation(
    observations: list[Issue],
    rule: str,
    category: str,
    severity: str,
    confidence: str,
    path: str,
    line: int | None,
    title: str,
    evidence: str,
    recommendation: str,
) -> None:
    observations.append(
        Issue(rule, category, severity, confidence, path, line, title, evidence, recommendation)
    )


def _scan_python(path: str, full: Path) -> tuple[ast.AST | None, list[Issue], list[Issue]]:
    issues: list[Issue] = []
    observations: list[Issue] = []
    try:
        source = full.read_text(encoding='utf-8-sig')
    except (OSError, UnicodeError) as exc:
        issues.append(Issue('python_read_error', 'code', 'HIGH', 'confirmed', path, None, 'Fichier Python illisible', str(exc), 'Corriger l encodage ou l acces au fichier.'))
        return None, issues, observations
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        issues.append(Issue('python_syntax_error', 'code', 'CRITICAL', 'confirmed', path, exc.lineno, 'Erreur de syntaxe Python', exc.msg, 'Corriger la syntaxe avant toute autre validation.'))
        return None, issues, observations

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and any(alias.name == '*' for alias in node.names):
            issues.append(Issue('import_star', 'architecture', 'HIGH', 'confirmed', path, _line(node), 'Import wildcard interdit', ast.unparse(node), 'Remplacer par des imports explicites pour garder les dependances auditables.'))

        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            lowered_name = node.name.casefold()
            marker = next((item for item in LEGACY_MARKERS if item in lowered_name), None)
            if marker:
                _append_observation(
                    observations,
                    'legacy_symbol_marker',
                    'legacy',
                    'INFO',
                    'suspect',
                    path,
                    _line(node),
                    'Symbole potentiellement legacy/obsolet',
                    f'{node.name} contient {marker}',
                    'Verifier ses consommateurs et le contrat canonique avant toute suppression.',
                )

        if isinstance(node, ast.While) and isinstance(node.test, ast.Constant) and node.test.value is True:
            if path.startswith('app/') and not _contains_blocking_call(node):
                _append_observation(
                    observations,
                    'busy_loop_risk',
                    'performance',
                    'MEDIUM',
                    'suspect',
                    path,
                    _line(node),
                    'Boucle infinie sans attente bloquante visible',
                    'while True sans sleep/wait/get/join/acquire detecte statiquement',
                    'Verifier que cette boucle ne peut pas tourner a vide et consommer du CPU.',
                )

        if isinstance(node, ast.ExceptHandler):
            if node.body and all(isinstance(item, ast.Pass) for item in node.body):
                type_name = ast.unparse(node.type) if node.type is not None else 'bare except'
                broad = node.type is None or type_name in {'Exception', 'BaseException'}
                finding = Issue(
                    'silent_exception',
                    'reliability',
                    'HIGH' if broad and _is_runtime_code(path) else 'MEDIUM',
                    'confirmed' if broad and _is_runtime_code(path) else 'suspect',
                    path,
                    _line(node),
                    'Exception avalee silencieusement',
                    f'{type_name} -> pass',
                    'Logger/remonter l erreur ou rendre explicite le cas volontairement ignore.',
                )
                if broad and _is_runtime_code(path):
                    issues.append(finding)
                else:
                    observations.append(finding)

        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name in {'sys.path.append', 'sys.path.insert', 'sys.path.extend'}:
                finding = Issue(
                    'sys_path_hack',
                    'architecture',
                    'HIGH' if _is_runtime_code(path) else 'INFO',
                    'confirmed' if _is_runtime_code(path) else 'suspect',
                    path,
                    _line(node),
                    'Mutation de sys.path detectee',
                    name,
                    'Corriger les imports/package plutot que modifier sys.path au runtime.',
                )
                if _is_runtime_code(path):
                    issues.append(finding)
                else:
                    observations.append(finding)
            if name in {'eval', 'exec', 'builtins.eval', 'builtins.exec'}:
                finding = Issue(
                    'dynamic_exec',
                    'reliability',
                    'HIGH' if _is_runtime_code(path) else 'INFO',
                    'confirmed' if _is_runtime_code(path) else 'suspect',
                    path,
                    _line(node),
                    'Execution dynamique de code',
                    name,
                    'Verifier si cette execution est indispensable; preferer une API structuree et validee.',
                )
                if _is_runtime_code(path):
                    issues.append(finding)
                else:
                    observations.append(finding)
            if name.endswith('lru_cache'):
                maxsize_none = any(keyword.arg == 'maxsize' and isinstance(keyword.value, ast.Constant) and keyword.value.value is None for keyword in node.keywords)
                if maxsize_none:
                    _append_observation(observations, 'unbounded_cache', 'performance', 'MEDIUM', 'suspect', path, _line(node), 'Cache potentiellement non borne', ast.unparse(node), 'Verifier la cardinalite reelle; borner le cache si les cles peuvent croitre pendant une longue session.')
            if name in THREAD_CALLS or name.endswith('.QThread'):
                _append_observation(observations, 'worker_lifecycle_review', 'lifecycle', 'INFO', 'suspect', path, _line(node), 'Worker/thread a verifier', name, 'Verifier etat terminal, stop deterministe, join/quit et absence de worker orphelin.')
            if name.endswith('QTimer') and not node.args and not node.keywords:
                _append_observation(observations, 'parentless_qtimer', 'lifecycle', 'LOW', 'suspect', path, _line(node), 'QTimer sans parent visible', name, 'Verifier son proprietaire, son arret et sa destruction a la fermeture de la vue/service.')
            if path.startswith(UI_SCOPES) and (name.endswith(('write_text', 'write_bytes')) or _open_writes(node)):
                _append_observation(observations, 'ui_direct_file_write', 'persistence', 'MEDIUM', 'suspect', path, _line(node), 'Ecriture fichier directe depuis une couche UI', name, 'Verifier qu un service canonique de persistence n existe pas et que l ecriture est atomique/coordonneee.')
            if path.startswith(UI_SCOPES) and name.endswith(('read_text', 'read_bytes')):
                _append_observation(observations, 'sync_io_ui', 'performance', 'MEDIUM', 'suspect', path, _line(node), 'I/O synchrone potentielle dans une vue UI', name, 'Verifier si cet acces disque arrive sur le thread Qt; deplacer/cacher seulement si mesure utile.')
            if path.startswith(UI_SCOPES) and name in {'open', 'builtins.open', 'json.load'}:
                _append_observation(observations, 'sync_io_ui', 'performance', 'MEDIUM', 'suspect', path, _line(node), 'I/O synchrone potentielle dans une vue UI', name, 'Verifier si cet acces disque arrive sur le thread Qt; deplacer/cacher seulement si mesure utile.')
            if name.endswith('setStyleSheet') and path.startswith('app/'):
                _append_observation(observations, 'local_stylesheet', 'ui', 'LOW', 'suspect', path, _line(node), 'Style local a verifier', name, 'Verifier que ce style ne duplique pas theme.py/components.py; conserver si semantique locale legitime.')

        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith('PySide6.QtWebEngine'):
            if 'equipment' not in path.lower():
                _append_observation(observations, 'qtwebengine_import_scope', 'performance', 'MEDIUM', 'suspect', path, _line(node), 'Import QtWebEngine hors zone attendue', node.module, 'Verifier qu il ne provoque pas le chargement de Chromium au demarrage.')

    return tree, issues, observations


def run_audit(
    root: Path,
    *,
    save: bool = True,
    integrity_mode: str | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    state = git_state(root)
    files = tracked_files(root)
    issues: list[Issue] = []
    observations: list[Issue] = []
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
            _append_observation(observations, 'legacy_path_marker', 'legacy', 'INFO', 'suspect', path, None, 'Fichier potentiellement legacy/obsolet', f'Nom contient {path_marker}', 'Verifier imports, wiring runtime et tests avant toute suppression.')
        if lower.endswith(RUNTIME_SUFFIXES) or lower.startswith(RUNTIME_PREFIXES):
            issues.append(Issue('tracked_runtime_artifact', 'git', 'HIGH', 'confirmed', path, None, 'Artefact runtime suivi par Git', f'Fichier runtime/transitoire suivi ({size} octets)', 'Retirer du suivi Git et ajouter une regle ignoree si necessaire.'))

        if size >= 20 * 1024 * 1024:
            _append_observation(observations, 'large_tracked_file', 'git', 'MEDIUM', 'confirmed', path, None, 'Gros fichier suivi par Git', f'{size / 1024 / 1024:.1f} MiB', 'Verifier qu il s agit bien d une source necessaire et non d un artefact regenerable.')

        if path.endswith('.py'):
            tree, python_issues, python_observations = _scan_python(path, full)
            issues.extend(python_issues)
            observations.extend(python_observations)
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
            _append_observation(observations, 'unreferenced_module', 'dead_code', 'LOW', 'suspect', path, None, 'Module sans import statique detecte', f'Aucun import statique de {module} dans les fichiers Python suivis.', 'Verifier wiring dynamique, signaux, importlib et usages externes avant toute suppression.')

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
            _append_observation(observations, 'repeated_symbol_name', 'architecture', 'INFO', 'suspect', unique[0], None, f'Symbole {symbol} present dans plusieurs modules', ', '.join(unique[:8]), 'Verifier uniquement si ces implementations portent réellement la meme responsabilite.')

    integrity: dict[str, Any] | None = None
    if integrity_mode:
        integrity = run_integrity_gate(root, integrity_mode)
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

    severity_order = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3, 'INFO': 4}
    issue_dicts = [issue.to_dict() for issue in issues]
    observation_dicts = [item.to_dict() for item in observations]
    issue_dicts.sort(key=lambda item: (severity_order.get(item['severity'], 9), item['path'], item.get('line') or 0, item['rule']))
    observation_dicts.sort(key=lambda item: (severity_order.get(item['severity'], 9), item['path'], item.get('line') or 0, item['rule']))

    counts = severity_counts(issue_dicts)
    observation_counts = severity_counts(observation_dicts)
    categories = Counter(item['category'] for item in issue_dicts)
    observation_categories = Counter(item['category'] for item in observation_dicts)
    confidence = Counter(item['confidence'] for item in issue_dicts)
    observation_confidence = Counter(item['confidence'] for item in observation_dicts)
    verdict = verdict_from_counts(counts)
    if integrity and integrity.get('status') == 'FAIL':
        verdict = 'FAIL'
    payload: dict[str, Any] = {
        'schema_version': 2,
        'kind': 'audit',
        'generated_at': utc_now(),
        'git': state,
        'integrity_mode': integrity_mode.upper() if integrity_mode else None,
        'integrity': integrity,
        'duration_ms': milliseconds(started),
        'summary': {
            'verdict': verdict,
            'tracked_files': len(files),
            'python_files_parsed': len(trees),
            'issues_total': len(issue_dicts),
            'severity': counts,
            'categories': dict(sorted(categories.items())),
            'confidence': dict(sorted(confidence.items())),
            'observations_total': len(observation_dicts),
            'observation_severity': observation_counts,
            'observation_categories': dict(sorted(observation_categories.items())),
            'observation_confidence': dict(sorted(observation_confidence.items())),
        },
        'issues': issue_dicts,
        'observations': observation_dicts,
        'largest_tracked_files': [
            {'path': path, 'size_mb': round(size / 1024 / 1024, 3)}
            for size, path in sorted(file_sizes, reverse=True)[:20]
        ],
    }
    if save:
        write_json(root, 'latest_audit', payload, rotate=True)
    return payload
