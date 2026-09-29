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
        if isinstance(node, ast.ImportFrom) and any(alias.name == '*' for alias in node.names):
            issues.append(Issue('import_star', 'architecture', 'HIGH', 'confirmed', path, _line(node), 'Import wildcard interdit', ast.unparse(node), 'Remplacer par des imports explicites pour garder les dependances auditables.'))

        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            lowered_name = node.name.casefold()
            marker = next((item for item in LEGACY_MARKERS if item in lowered_name), None)
            if marker:
                issues.append(Issue('legacy_symbol_marker', 'legacy', 'INFO', 'suspect', path, _line(node), 'Symbole potentiellement legacy/obsolet', f'{node.name} contient {marker}', 'Verifier ses consommateurs et le contrat canonique avant toute suppression.'))

        if isinstance(node, ast.While) and isinstance(node.test, ast.Constant) and node.test.value is True:
            if path.startswith('app/') and not _contains_blocking_call(node):
                issues.append(Issue('busy_loop_risk', 'performance', 'MEDIUM', 'suspect', path, _line(node), 'Boucle infinie sans attente bloquante visible', 'while True sans sleep/wait/get/join/acquire detecte statiquement', 'Verifier que cette boucle ne peut pas tourner a vide et consommer du CPU.'))

        if isinstance(node, (ast.ExceptHandler,)):
            if node.body and all(isinstance(item, ast.Pass) for item in node.body):
                type_name = ast.unparse(node.type) if node.type is not None else 'bare except'
                issues.append(Issue('silent_exception', 'reliability', 'HIGH', 'confirmed', path, _line(node), 'Exception avalee silencieusement', f'{type_name} -> pass', 'Logger/remonter l erreur ou traiter explicitement le cas.'))

        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name in {'sys.path.append', 'sys.path.insert', 'sys.path.extend'}:
                issues.append(Issue('sys_path_hack', 'architecture', 'HIGH', 'confirmed', path, _line(node), 'Mutation de sys.path detectee', name, 'Corriger les imports/package plutot que modifier sys.path au runtime.'))
            if name in {'eval', 'exec', 'builtins.eval', 'builtins.exec'}:
                issues.append(Issue('dynamic_exec', 'reliability', 'HIGH', 'confirmed', path, _line(node), 'Execution dynamique de code', name, 'Verifier si cette execution est indispensable; preferer une API structuree et validee.'))
            if name.endswith(('lru_cache',)):
                maxsize_none = any(keyword.arg == 'maxsize' and isinstance(keyword.value, ast.Constant) and keyword.value.value is None for keyword in node.keywords)
                if maxsize_none:
                    issues.append(Issue('unbounded_cache', 'performance', 'MEDIUM', 'suspect', path, _line(node), 'Cache potentiellement non borne', ast.unparse(node), 'Verifier la cardinalite reelle; borner le cache si les cles peuvent croitre²È="25ÍÑÈğ9½¹”€ô9½¹”°(¤€´ø‘¥ÑmÍÑÈ°¹åtè(€€€ÍÑ…ÉÑ•€ôÑ¥µ”¹Á•É™}½Õ¹Ñ•È ¤(€€€ÍÑ…Ñ”€ô¥Ñ}ÍÑ…Ñ”¡É½½Ğ¤(€€€™¥±•Ì€ôÑÉ…­•‘}™¥±•Ì¡É½½Ğ¤(€€€¥ÍÍÕ•Ìè±¥ÍÑm%ÍÍÕ•t€ômt(€€€ÑÉ••Ìè‘¥ÑmÍÑÈ°…ÍĞ¹MQt€ôíô(€€€¥µÁ½ÉÑÍ}‰å}™¥±”è‘¥ÑmÍÑÈ°Í•ÑmÍÑÉut€ôíô(€€€µ½‘Õ±•}Ñ½}Á…Ñ è‘¥ÑmÍÑÈ°ÍÑÉt€ôíô(€€€™¥±•}Í¥é•Ìè±¥ÍÑmÑÕÁ±•m¥¹Ğ°ÍÑÉut€ômt((€€€™½ÈÁ…Ñ ¥¸™¥±•Ìè(€€€€€€€™Õ±°€ôÉ½½Ğ€¼Á…Ñ (€€€€€€€¥˜¹½Ğ™Õ±°¹¥Í}™¥±” ¤è(€€€€€€€€€€€½¹Ñ¥¹Õ”(€€€€€€€ÑÉäè(€€€€€€€€€€€Í¥é”€ô™Õ±°¹ÍÑ…Ğ ¤¹ÍÑ}Í¥é”(€€€€€€€€€€€™¥±•}Í¥é•Ì¹…ÁÁ•¹ ¡Í¥é”°Á…Ñ ¤¤(€€€€€€€•á•ÁĞ=MÉÉ½Èè(€€€€€€€€€€€Í¥é”€ô€À((€€€€€€€±½İ•È€ôÁ…Ñ ¹±½İ•È ¤(€€€€€€€Á…Ñ¡}µ…É­•È€ô¹•áĞ ¡¥Ñ•´™½È¥Ñ•´¥¸1e}5I-IL¥˜¥Ñ•´¥¸A…Ñ ¡Á…Ñ ¤¹ÍÑ•´¹…Í•™½± ¤¤°9½¹”¤(€€€€€€€¥˜Á…Ñ¡}µ…É­•È…¹Á…Ñ ¹ÍÑ…ÉÑÍİ¥Ñ   …ÁÀ¼œ°€±½…±}‘½™ÕÍ}‘…Ñ„¼œ¤¤è(€€€€€€€€€€€¥ÍÍÕ•Ì¹…ÁÁ•¹¡%ÍÍÕ” ±•…å}Á…Ñ¡}µ…É­•Èœ°€±•…äœ°€%9<œ°€ÍÕÍÁ•Ğœ°Á…Ñ °9½¹”°€¥¡¥•ÈÁ½Ñ•¹Ñ¥•±±•µ•¹Ğ±•…ä½½‰Í½±•Ğœ°˜9½´½¹Ñ¥•¹ĞíÁ…Ñ¡}µ…É­•Éôœ°€Y•É¥™¥•È¥µÁ½ÉÑÌ°İ¥É¥¹œÉÕ¹Ñ¥µ”•ĞÑ•ÍÑÌ…Ù…¹ĞÑ½ÕÑ”ÍÕÁÁÉ•ÍÍ¥½¸¸œ¤¤(€€€€€€€¥˜±½İ•È¹•¹‘Íİ¥Ñ ¡IU9Q%5}MU%aL¤½È±½İ•È¹ÍÑ…ÉÑÍİ¥Ñ ¡IU9Q%5}AI%aL¤è(€€€€€€€€€€€¥ÍÍÕ•Ì¹…ÁÁ•¹¡%ÍÍÕ” ÑÉ…­•‘}ÉÕ¹Ñ¥µ•}…ÉÑ¥™…Ğœ°€¥Ğœ°€!% œ°€½¹™¥Éµ•œ°Á…Ñ °9½¹”°€ÉÑ•™…ĞÉÕ¹Ñ¥µ”ÍÕ¥Ù¤Á…È¥Ğœ°˜¥¡¥•ÈÉÕ¹Ñ¥µ”½ÑÉ…¹Í¥Ñ½¥É”ÍÕ¥Ù¤€¡íÍ¥é•ô½Ñ•ÑÌ¤œ°€I•Ñ¥É•È‘ÔÍÕ¥Ù¤¥Ğ•Ğ…©½ÕÑ•ÈÕ¹”É•±”¥¹½É•”Í¤¹••ÍÍ…¥É”¸œ¤¤((€€€€€€€¥˜Í¥é”€øô€ÈÀ€¨€ÄÀÈĞ€¨€ÄÀÈĞè(€€€€€€€€€€€¥ÍÍÕ•Ì¹…ÁÁ•¹¡%ÍÍÕ” ±…É•}ÑÉ…­•‘}™¥±”œ°€¥Ğœ°€5%U4œ°€½¹™¥Éµ•œ°Á…Ñ °9½¹”°€É½Ì™¥¡¥•ÈÍÕ¥Ù¤Á…È¥Ğœ°˜íÍ¥é”€¼€ÄÀÈĞ€¼€ÄÀÈĞè¸Å™ô5¥œ°€Y•É¥™¥•ÈÅÔ¥°Ì…¥Ğ‰¥•¸Õ¹”Í½ÕÉ”¹••ÍÍ…¥É”•Ğ¹½¸Õ¸…ÉÑ•™…ĞÉ••¹•É…‰±”¸œ¤¤((€€€€€€€¥˜Á…Ñ ¹•¹‘Íİ¥Ñ  œ¹Áäœ¤è(€€€€€€€€€€€ÑÉ•”°ÁåÑ¡½¹}¥ÍÍÕ•Ì€ô}Í…¹}ÁåÑ¡½¸¡Á…Ñ °™Õ±°¤(€€€€€€€€€€€¥ÍÍÕ•Ì¹•áÑ•¹¡ÁåÑ¡½¹}¥ÍÍÕ•Ì¤(€€€€€€€€€€€¥˜ÑÉ•”¥Ì¹½Ğ9½¹”è(€€€€€€€€€€€€€€€ÑÉ••ÍmÁ…Ñ¡t€ôÑÉ•”(€€€€€€€€€€€€€€€µ½‘Õ±”€ô}µ½‘Õ±•}¹…µ”¡Á…Ñ ¤(€€€€€€€€€€€€€€€µ½‘Õ±•}Ñ½}Á…Ñ¡mµ½‘Õ±•t€ôÁ…Ñ (€€€€€€€€€€€€€€€¥µÁ½ÉÑÍ}‰å}™¥±•mÁ…Ñ¡t€ô}½±±•Ñ}¥µÁ½ÉÑÌ¡ÑÉ•”°µ½‘Õ±”¤((€€€¥µÁ½ÉÑ•è½Õ¹Ñ•ÉmÍÑÉt€ô½Õ¹Ñ•È ¤(€€€™½È¹…µ•Ì¥¸¥µÁ½ÉÑÍ}‰å}™¥±”¹Ù…±Õ•Ì ¤è(€€€€€€€™½È¹…µ”¥¸¹…µ•Ìè(€€€€€€€€€€€¥µÁ½ÉÑ•‘m¹…µ•t€¬ô€Ä(€€€€€€€€€€€Á…ÉÑÌ€ô¹…µ”¹ÍÁ±¥Ğ œ¸œ¤(€€€€€€€€€€€™½È¥¹‘•à¥¸É…¹” Ä°±•¸¡Á…ÉÑÌ¤¤è(€€€€€€€€€€€€€€€¥µÁ½ÉÑ•‘lœ¸œ¹©½¥¸¡Á…ÉÑÍlé¥¹‘•át¥t€¬ô€Ä((€€€™½Èµ½‘Õ±”°Á…Ñ ¥¸µ½‘Õ±•}Ñ½}Á…Ñ ¹¥Ñ•µÌ ¤è(€€€€€€€¥˜¹½ĞÁ…Ñ ¹ÍÑ…ÉÑÍİ¥Ñ   …ÁÀ¼œ°€±½…±}‘½™ÕÍ}‘…Ñ„¼œ¤¤è(€€€€€€€€€€€½¹Ñ¥¹Õ”(€€€€€€€¥˜A…Ñ ¡Á…Ñ ¤¹¹…µ”¥¸9QIeA=%9Q}95L½ÈÁ…Ñ ¹•¹‘Íİ¥Ñ  œ½}}¥¹¥Ñ}|¹Áäœ¤è(€€€€€€€€€€€½¹Ñ¥¹Õ”(€€€€€€€ÑÉ•”€ôÑÉ••ÍmÁ…Ñ¡t(€€€€€€€¥˜¥µÁ½ÉÑ•¹•Ğ¡µ½‘Õ±”°€À¤€ôô€À…¹¹½Ğ}¡…Í}µ…¥¹}Õ…É¡ÑÉ•”¤è(€€€€€€€€€€€¥ÍÍÕ•Ì¹…ÁÁ•¹¡%ÍÍÕ” Õ¹É•™•É•¹•‘}µ½‘Õ±”œ°€‘•…‘}½‘”œ°€1=\œ°€ÍÕÍÁ•Ğœ°Á…Ñ °9½¹”°€5½‘Õ±”Í…¹Ì¥µÁ½ÉĞÍÑ…Ñ¥ÅÕ”‘•Ñ•Ñ”œ°˜ÕÕ¸¥µÁ½ÉĞÍÑ…Ñ¥ÅÕ”‘”íµ½‘Õ±•ô‘…¹Ì±•Ì™¥¡¥•ÉÌAåÑ¡½¸ÍÕ¥Ù¥Ì¸œ°€Y•É¥™¥•Èİ¥É¥¹œ‘å¹…µ¥ÅÕ”°Í¥¹…Õà°¥µÁ½ÉÑ±¥ˆ•ĞÕÍ…•Ì•áÑ•É¹•Ì…Ù…¹ĞÑ½ÕÑ”ÍÕÁÁÉ•ÍÍ¥½¸¸œ¤¤((€€€€Œ•Ñ•Ğ‘ÕÁ±¥…Ñ”Ñ½Àµ±•Ù•°±…ÍÌ½™Õ¹Ñ¥½¸¹…µ•Ì½¹±ä…Ì¹…Ù¥…Ñ¥½¸…¥°¹½Ğ…ÌÁÉ½½˜½˜‘ÕÁ±¥…Ñ¥½¸¸(€€€Íåµ‰½±Ìè‘•™…Õ±Ñ‘¥ÑmÍÑÈ°±¥ÍÑmÍÑÉut€ô‘•™…Õ±Ñ‘¥Ğ¡±¥ÍĞ¤(€€€™½ÈÁ…Ñ °ÑÉ•”¥¸ÑÉ••Ì¹¥Ñ•µÌ ¤è(€€€€€€€¥˜¹½ĞÁ…Ñ ¹ÍÑ…ÉÑÍİ¥Ñ   …ÁÀ¼œ°€±½…±}‘½™ÕÍ}‘…Ñ„¼œ¤¤è(€€€€€€€€€€€½¹Ñ¥¹Õ”(€€€€€€€™½È¹½‘”¥¸•Ñ…ÑÑÈ¡ÑÉ•”°€‰½‘äœ°mt¤è(€€€€€€€€€€€¥˜¥Í¥¹ÍÑ…¹”¡¹½‘”°€¡…ÍĞ¹±…ÍÍ•˜°…ÍĞ¹Õ¹Ñ¥½¹•˜°…ÍĞ¹Íå¹Õ¹Ñ¥½¹•˜¤¤…¹¹½Ğ¹½‘”¹¹…µ”¹ÍÑ…ÉÑÍİ¥Ñ  |œ¤è(€€€€€€€€€€€€€€€Íåµ‰½±Ím¹½‘”¹¹…µ•t¹…ÁÁ•¹¡Á…Ñ ¤(€€€™½ÈÍåµ‰½°°±½…Ñ¥½¹Ì¥¸Íåµ‰½±Ì¹¥Ñ•µÌ ¤è(€€€€€€€Õ¹¥ÅÕ”€ôÍ½ÉÑ•¡Í•Ğ¡±½…Ñ¥½¹Ì¤¤(€€€€€€€¥˜±•¸¡Õ¹¥ÅÕ”¤€øô€Ğè(€€€€€€€€€€€¥ÍÍÕ•Ì¹…ÁÁ•¹¡%ÍÍÕ” É•Á•…Ñ•‘}Íåµ‰½±}¹…µ”œ°€…É¡¥Ñ•ÑÕÉ”œ°€%9<œ°€ÍÕÍÁ•Ğœ°Õ¹¥ÅÕ•lÁt°9½¹”°˜Måµ‰½±”íÍåµ‰½±ôÁÉ•Í•¹Ğ‘…¹ÌÁ±ÕÍ¥•ÕÉÌµ½‘Õ±•Ìœ°€œ°€œ¹©½¥¸¡Õ¹¥ÅÕ•lèát¤°€Y•É¥™¥•ÈÕ¹¥ÅÕ•µ•¹ĞÍ¤•Ì¥µÁ±•µ•¹Ñ…Ñ¥½¹ÌÁ½ÉÑ•¹ĞË¥•±±•µ•¹Ğ±„µ•µ”É•ÍÁ½¹Í…‰¥±¥Ñ”¸œ¤¤((€€€¥¹Ñ•É¥Ñäè‘¥ÑmÍÑÈ°¹åtğ9½¹”€ô9½¹”(€€€¥˜¥¹Ñ•É¥Ñå}µ½‘”è(€€€€€€€¥¹Ñ•É¥Ñä€ôÉÕ¹}¥¹Ñ•É¥Ñå}…Ñ”¡É½½Ğ°¥¹Ñ•É¥Ñå}µ½‘”¤(€€€€€€€¥¹Ñ•É¥Ñå}É•Á½ÉĞ€ô¥¹Ñ•É¥Ñä¹•Ğ É•Á½ÉĞœ¤½Èíô(€€€€€€€É½ÕÁÌ€ô¥¹Ñ•É¥Ñå}É•Á½ÉĞ¹•Ğ É½ÕÁÌœ¤½Èíô(€€€€€€€™½ÈÉ½ÕÁ}¹…µ”°É½ÕÀ¥¸É½ÕÁÌ¹¥Ñ•µÌ ¤è(€€€€€€€€€€€¥˜¹½Ğ¥Í¥¹ÍÑ…¹”¡É½ÕÀ°‘¥Ğ¤½È¹½ĞÉ½ÕÀ¹•Ğ É•ÅÕ¥É•œ¤è(€€€€€€€€€€€€€€€½¹Ñ¥¹Õ”(€€€€€€€€€€€ÍÑ…ÑÕÌ€ôÍÑÈ¡É½ÕÀ¹•Ğ ÍÑ…ÑÕÌœ°€9=Q}IU8œ¤¤¹ÕÁÁ•È ¤(€€€€€€€€€€€¥˜ÍÑ…ÑÕÌ¥¸ìAMLœ°€5MUI}=91dôè(€€€€€€€€€€€€€€€½¹Ñ¥¹Õ”(€€€€€€€€€€€‰±½­•ÉÌ€ô€œ°€œ¹©½¥¸¡ÍÑÈ¡¥Ñ•´¤™½È¥Ñ•´¥¸É½ÕÀ¹•Ğ ‰±½­•ÉÌœ°mt¤¥˜¥Ñ•´¤(€€€€€€€€€€€•Ù¥‘•¹”€ô‰±½­•ÉÌ½È˜Ñ±…Ì%¹Ñ•É¥ÑäèíÍÑ…ÑÕÍôœ(€€€€€€€€€€€¥ÍÍÕ•Ì¹…ÁÁ•¹¡%ÍÍÕ” (€€€€€€€€€€€€€€€€¥¹Ñ•É¥Ñå}…Ñ•}™…¥±ÕÉ”œ°(€€€€€€€€€€€€€€€€¥¹Ñ•É¥Ñäœ°(€€€€€€€€€€€€€€€€!% œ°(€€€€€€€€€€€€€€€€½¹™¥Éµ•œ°(€€€€€€€€€€€€€€€€Ñ½½±Ì½…Ñ±…Í}¥¹Ñ•É¥Ñä¹Áäœ°(€€€€€€€€€€€€€€€9½¹”°(€€€€€€€€€€€€€€€˜…Ñ”íÉ½ÕÁ}¹…µ•ô•¸•¡•Œœ°(€€€€€€€€€€€€€€€•Ù¥‘•¹”°(€€€€€€€€€€€€€€€€½ÉÉ¥•È±„…ÕÍ”É…¥¹”Í¥¹…±•”Á…ÈÑ±…Ì%¹Ñ•É¥Ñäì¹”Á…Ì…™™…¥‰±¥È±”…Ñ”¸œ°(€€€€€€€€€€€€¤¤(€€€€€€€¥˜¥¹Ñ•É¥Ñä¹•Ğ ÍÑ…ÑÕÌœ¤€ôô€Q%5=UPœè(€€€€€€€€€€€¥ÍÍÕ•Ì¹…ÁÁ•¹¡%ÍÍÕ” (€€€€€€€€€€€€€€€€¥¹Ñ•É¥Ñå}…Ñ•}Ñ¥µ•½ÕĞœ°(€€€€€€€€€€€€€€€€¥¹Ñ•É¥Ñäœ°(€€€€€€€€€€€€€€€€5%U4œ°(€€€€€€€€€€€€€€€€½¹™¥Éµ•œ°(€€€€€€€€€€€€€€€€Ñ½½±Ì½…Ñ±…Í}¥¹Ñ•É¥Ñä¹Áäœ°(€€€€€€€€€€€€€€€9½¹”°(€€€€€€€€€€€€€€€˜…Ñ”íÍÑÈ¡¥¹Ñ•É¥Ñå}µ½‘”¤¹ÕÁÁ•È ¥ô¥¹Ñ•ÉÉ½µÁÔÁ…ÈÑ¥µ•½ÕĞœ°(€€€€€€€€€€€€€€€ÍÑÈ¡¥¹Ñ•É¥Ñä¹•Ğ É•…Í½¸œ°€Ñ¥µ•½ÕĞœ¤¤°(€€€€€€€€€€€€€€€€I•±…¹•È±”…Ñ”Í•Õ°•Ğ¥‘•¹Ñ¥™¥•È±”É½ÕÁ”ÑÉ½À±•¹Ğ½Ô‰±½ÅÕ”¸œ°(€€€€€€€€€€€€¤¤(€€€€€€€•±¥˜¥¹Ñ•É¥Ñä¹•Ğ ÍÑ…ÑÕÌœ¤€ôô€%0œ…¹¹½ĞÉ½ÕÁÌè(€€€€€€€€€€€¥ÍÍÕ•Ì¹…ÁÁ•¹¡%ÍÍÕ” (€€€€€€€€€€€€€€€€¥¹Ñ•É¥Ñå}…Ñ•}•ÉÉ½Èœ°(€€€€€€€€€€€€€€€€¥¹Ñ•É¥Ñäœ°(€€€€€€€€€€€€€€€€!% œ°(€€€€€€€€€€€€€€€€½¹™¥Éµ•œ°(€€€€€€€€€€€€€€€€Ñ½½±Ì½…Ñ±…Í}¥¹Ñ•É¥Ñä¹Áäœ°(€€€€€€€€€€€€€€€9½¹”°(€€€€€€€€€€€€€€€˜…Ñ”íÍÑÈ¡¥¹Ñ•É¥Ñå}µ½‘”¤¹ÕÁÁ•È ¥ô•¸•¡•Œœ°(€€€€€€€€€€€€€€€€q¸œ¹©½¥¸¡¥¹Ñ•É¥Ñä¹•Ğ ÍÑ‘•ÉÉ}Ñ…¥°œ°mt¥l´ÄÀét¤½È€I…ÁÁ½ÉĞÑ±…Ì%¹Ñ•É¥Ñä¥¹‘¥ÍÁ½¹¥‰±”œ°(€€€€€€€€€€€€€€€€á•ÕÑ•ÈÑ±…Ì%¹Ñ•É¥ÑäÍ•Á…É•µ•¹Ğ•Ğ½ÉÉ¥•È°•ÉÉ•ÕÈ‘”½¹™¥ÕÉ…Ñ¥½¸½•á•ÕÑ¥½¸¸œ°(€€€€€€€€€€€€¤¤((€€€¥ÍÍÕ•}‘¥ÑÌ€ôm¥ÍÍÕ”¹Ñ½}‘¥Ğ ¤™½È¥ÍÍÕ”¥¸¥ÍÍÕ•Ít(€€€¥ÍÍÕ•}‘¥ÑÌ¹Í½ÉĞ¡­•äõ±…µ‰‘„¥Ñ•´è€¡ìI%Q%0œè€À°€!% œè€Ä°€5%U4œè€È°€1=\œè€Ì°€%9<œè€Ñô¹•Ğ¡¥Ñ•µlÍ•Ù•É¥Ñät°€ä¤°¥Ñ•µlÁ…Ñ t°¥Ñ•´¹•Ğ ±¥¹”œ¤½È€À°¥Ñ•µlÉÕ±”t¤¤(€€€½Õ¹ÑÌ€ôÍ•Ù•É¥Ñå}½Õ¹ÑÌ¡¥ÍÍÕ•}‘¥ÑÌ¤(€€€…Ñ•½É¥•Ì€ô½Õ¹Ñ•È¡¥Ñ•µl…Ñ•½Éät™½È¥Ñ•´¥¸¥ÍÍÕ•}‘¥ÑÌ¤(€€€½¹™¥‘•¹”€ô½Õ¹Ñ•È¡¥Ñ•µl½¹™¥‘•¹”t™½È¥Ñ•´¥¸¥ÍÍÕ•}‘¥ÑÌ¤(€€€Ù•É‘¥Ğ€ôÙ•É‘¥Ñ}™É½µ}½Õ¹ÑÌ¡½Õ¹ÑÌ¤(€€€¥˜¥¹Ñ•É¥Ñä…¹¥¹Ñ•É¥Ñä¹•Ğ ÍÑ…ÑÕÌœ¤€ôô€%0œè(€€€€€€€Ù•É‘¥Ğ€ô€%0œ(€€€Á…å±½…è‘¥ÑmÍÑÈ°¹åt€ôì(€€€€€€€€Í¡•µ…}Ù•ÉÍ¥½¸œè€Ä°(€€€€€€€€­¥¹œè€…Õ‘¥Ğœ°(€€€€€€€€•¹•É…Ñ•‘}…ĞœèÕÑ}¹½Ü ¤°(€€€€€€€€¥ĞœèÍÑ…Ñ”°(€€€€€€€€¥¹Ñ•É¥Ñå}µ½‘”œè¥¹Ñ•É¥Ñå}µ½‘”¹ÕÁÁ•È ¤¥˜¥¹Ñ•É¥Ñå}µ½‘”•±Í”9½¹”°(€€€€€€€€¥¹Ñ•É¥Ñäœè¥¹Ñ•É¥Ñä°(€€€€€€€€‘ÕÉ…Ñ¥½¹}µÌœèµ¥±±¥Í•½¹‘Ì¡ÍÑ…ÉÑ•¤°(€€€€€€€€ÍÕµµ…Éäœèì(€€€€€€€€€€€€Ù•É‘¥ĞœèÙ•É‘¥Ğ°(€€€€€€€€€€€€ÑÉ…­•‘}™¥±•Ìœè±•¸¡™¥±•Ì¤°(€€€€€€€€€€€€ÁåÑ¡½¹}™¥±•Í}Á…ÉÍ•œè±•¸¡ÑÉ••Ì¤°(€€€€€€€€€€€€¥ÍÍÕ•Í}Ñ½Ñ…°œè±•¸¡¥ÍÍÕ•}‘¥ÑÌ¤°(€€€€€€€€€€€€Í•Ù•É¥Ñäœè½Õ¹ÑÌ°(€€€€€€€€€€€€…Ñ•½É¥•Ìœè‘¥Ğ¡Í½ÉÑ•¡…Ñ•½É¥•Ì¹¥Ñ•µÌ ¤¤¤°(€€€€€€€€€€€€½¹™¥‘•¹”œè‘¥Ğ¡Í½ÉÑ•¡½¹™¥‘•¹”¹¥Ñ•µÌ ¤¤¤°(€€€€€€€ô°(€€€€€€€€¥ÍÍÕ•Ìœè¥ÍÍÕ•}‘¥ÑÌ°(€€€€€€€€±…É•ÍÑ}ÑÉ…­•‘}™¥±•Ìœèl(€€€€€€€€€€€ìÁ…Ñ œèÁ…Ñ °€Í¥é•}µˆœèÉ½Õ¹¡Í¥é”€¼€ÄÀÈĞ€¼€ÄÀÈĞ°€Ì¥ô(€€€€€€€€€€€™½ÈÍ¥é”°Á…Ñ ¥¸Í½ÉÑ•¡™¥±•}Í¥é•Ì°É•Ù•ÉÍ”õQÉÕ”¥lèÈÁt(€€€€€€€t°(€€€ô(€€€¥˜Í…Ù”è(€€€€€€€İÉ¥Ñ•}©Í½¸¡É½½Ğ°€±…Ñ•ÍÑ}…Õ‘¥Ğœ°Á…å±½…°É½Ñ…Ñ”õQÉÕ”¤(€€€É•ÑÕÉ¸Á…å±½…