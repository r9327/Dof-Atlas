from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from atlas_doctor_lib import (
    build_ai_report,
    cache_matches_git,
    compare_runs,
    git_state,
    load_json,
    project_root,
    run_audit,
    run_performance,
    runtime_dir,
)


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _audit(root: Path, *, force: bool = False) -> dict[str, Any]:
    state = git_state(root)
    cached = load_json(root, 'latest_audit')
    if not force and cache_matches_git(cached, state):
        return cached or {}
    return run_audit(root)


def _summary(payload: dict[str, Any]) -> None:
    summary = payload.get('summary') or {}
    severity = summary.get('severity') or {}
    print(f"Verdict : {summary.get('verdict', 'N/A')}")
    print(' | '.join(f'{key} {severity.get(key, 0)}' for key in ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO')))
    print(f"Problemes : {summary.get('issues_total', 0)} | Duree : {payload.get('duration_ms', 0)} ms")


def command_audit(root: Path, args) -> dict[str, Any]:
    payload = _audit(root, force=args.force)
    if not args.json:
        _summary(payload)
        print(f"Snapshot : {root / '.ai/runtime/atlas_doctor/latest_audit.json'}")
    return payload


def command_perf(root: Path, args) -> dict[str, Any]:
    _audit(root, force=False)
    payload = run_performance(root, include_runtime=not args.files_only)
    if not args.json:
        profile = payload.get('file_profile') or {}
        print(f"Fichiers mesures : {profile.get('files_measured', 0)}")
        print(f"Lecture cumulee : {profile.get('total_read_ms', 0)} ms | JSON parse : {profile.get('total_json_parse_ms', 0)} ms")
        runtime = payload.get('runtime') or {}
        if runtime:
            print(f"Benchmark runtime : {runtime.get('status', 'N/A')} ({runtime.get('duration_ms', 0)} ms)")
    return payload


def command_compare(root: Path, args) -> dict[str, Any]:
    payload = compare_runs(load_json(root, 'latest_audit'), load_json(root, 'previous_audit'))
    if not args.json:
        print(f"Nouveaux : {len(payload.get('new_issues', []))} | Corriges : {len(payload.get('fixed_issues', []))} | Inchanges : {payload.get('unchanged_count', 0)}")
    return payload


def command_issues(root: Path, args) -> dict[str, Any]:
    audit = _audit(root, force=False)
    issues = audit.get('issues', [])
    if args.severity:
        allowed = {item.upper() for item in args.severity}
        issues = [item for item in issues if item.get('severity') in allowed]
    payload = {'count': len(issues), 'issues': issues}
    if not args.json:
        for item in issues:
            line = f":{item['line']}" if item.get('line') else ''
            print(f"[{item['severity']}] {item['rule']} - {item['path']}{line} - {item['title']} ({item['confidence']})")
    return payload


def command_verify(root: Path, args) -> dict[str, Any]:
    before = load_json(root, 'latest_audit')
    current = run_audit(root)
    comparison = compare_runs(current, before)
    payload = {'audit': current.get('summary'), 'comparison': comparison}
    if not args.json:
        print(f"Nouveaux : {len(comparison.get('new_issues', []))} | Corriges : {len(comparison.get('fixed_issues', []))}")
        _summary(current)
    return payload


def command_report(root: Path, args) -> dict[str, Any]:
    _audit(root, force=False)
    payload = build_ai_report(root)
    if not args.json:
        print(f"Rapport IA : {root / '.ai/runtime/atlas_doctor/latest_report.json'}")
    return payload


def command_clean(root: Path, args) -> dict[str, Any]:
    path = runtime_dir(root)
    removed = 0
    for child in list(path.iterdir()):
        if child.is_file():
            child.unlink(missing_ok=True)
            removed += 1
        elif child.is_dir():
            shutil.rmtree(child)
            removed += 1
    payload = {'status': 'PASS', 'removed_entries': removed, 'path': str(path)}
    if not args.json:
        print(f'{removed} entree(s) temporaire(s) supprimee(s).')
    return payload


def command_all(root: Path, args) -> dict[str, Any]:
    audit = run_audit(root)
    perf = run_performance(root, include_runtime=True)
    report = build_ai_report(root)
    payload = {'audit': audit.get('summary'), 'performance_status': (perf.get('runtime') or {}).get('status'), 'report': report}
    if not args.json:
        _summary(audit)
        print(f"Performance runtime : {payload['performance_status']}")
        print(f"Rapport : {root / '.ai/runtime/atlas_doctor/latest_report.json'}")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Dofus Atlas Doctor - audit, performance et rapport IA.')
    parser.add_argument('--json', action='store_true', help='Sortie JSON machine-readable.')
    sub = parser.add_subparsers(dest='command')

    audit = sub.add_parser('audit')
    audit.add_argument('--force', action='store_true')

    perf = sub.add_parser('perf')
    perf.add_argument('--files-only', action='store_true', help='Ne pas lancer le benchmark Qt runtime.')

    sub.add_parser('compare')
    issues = sub.add_parser('issues')
    issues.add_argument('--severity', nargs='*')
    sub.add_parser('verify')
    sub.add_parser('report')
    sub.add_parser('clean')
    sub.add_parser('all')
    return parser


def menu(root: Path) -> int:
    actions = {
        '1': ('Audit complet', lambda: command_audit(root, argparse.Namespace(force=True, json=False))),
        '2': ('Inspecteur performances + I/O runtime', lambda: command_perf(root, argparse.Namespace(files_only=False, json=False))),
        '3': ('Performance Lab (fichiers + benchmark app)', lambda: command_perf(root, argparse.Namespace(files_only=False, json=False))),
        '4': ('Comparer avec le dernier audit', lambda: command_compare(root, argparse.Namespace(json=False))),
        '5': ('Voir les problemes detectes', lambda: command_issues(root, argparse.Namespace(severity=None, json=False))),
        '6': ('Verifier les corrections', lambda: command_verify(root, argparse.Namespace(json=False))),
        '7': ('Exporter le rapport IA', lambda: command_report(root, argparse.Namespace(json=False))),
        '8': ('Nettoyer les fichiers temporaires Doctor', lambda: command_clean(root, argparse.Namespace(json=False))),
        '9': ('TOUT LANCER', lambda: command_all(root, argparse.Namespace(json=False))),
    }
    while True:
        print('\n=== DOFUS ATLAS - DEV DOCTOR ===')
        for key, (label, _) in actions.items():
            print(f'[{key}] {label}')
        print('[0] Quitter')
        choice = input('Choix : ').strip()
        if choice == '0':
            return 0
        action = actions.get(choice)
        if not action:
            print('Choix invalide.')
            continue
        print(f'\n--- {action[0]} ---')
        try:
            action[1]()
        except KeyboardInterrupt:
            print('\nOperation interrompue.')
        except Exception as exc:
            print(f'ERREUR: {exc}', file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = project_root(Path.cwd())
    if not args.command:
        return menu(root)
    handlers = {
        'audit': command_audit,
        'perf': command_perf,
        'compare': command_compare,
        'issues': command_issues,
        'verify': command_verify,
        'report': command_report,
        'clean': command_clean,
        'all': command_all,
    }
    payload = handlers[args.command](root, args)
    if args.json:
        _print_json(payload)
    if args.command == 'audit':
        verdict = (payload.get('summary') or {}).get('verdict')
        return 2 if verdict == 'FAIL' else (1 if verdict == 'WARN' else 0)
    if args.command == 'perf':
        runtime = payload.get('runtime') or {}
        if runtime and runtime.get('status') == 'FAIL':
            return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
