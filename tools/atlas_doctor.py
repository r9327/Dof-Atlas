from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from atlas_doctor_lib import (
    build_ai_report,
    cache_matches_git,
    compare_performance,
    compare_runs,
    git_state,
    load_json,
    project_root,
    inspect_live,
    run_audit,
    run_performance,
    runtime_dir,
)


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _audit(
    root: Path,
    *,
    force: bool = False,
    integrity_mode: str | None = None,
) -> dict[str, Any]:
    state = git_state(root)
    cached = load_json(root, 'latest_audit')
    if not force and cache_matches_git(cached, state):
        ranks = {None: 0, 'FAST': 1, 'CRITICAL': 2, 'FULL': 3, 'DEEP': 4}
        cached_mode = cached.get('integrity_mode') if cached else None
        requested = integrity_mode.upper() if integrity_mode else None
        if ranks.get(cached_mode, 0) >= ranks.get(requested, 0):
            return cached or {}
    return run_audit(root, integrity_mode=integrity_mode)


def _summary(payload: dict[str, Any]) -> None:
    summary = payload.get('summary') or {}
    severity = summary.get('severity') or {}
    print(f"Verdict : {summary.get('verdict', 'N/A')}")
    print(' | '.join(f'{key} {severity.get(key, 0)}' for key in ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO')))
    print(
        f"Problemes : {summary.get('issues_total', 0)} | "
        f"Observations a revoir : {summary.get('observations_total', 0)} | "
        f"Duree : {payload.get('duration_ms', 0)} ms"
    )


def command_audit(root: Path, args) -> dict[str, Any]:
    payload = _audit(root, force=args.force, integrity_mode=args.gate)
    if not args.json:
        _summary(payload)
        print(f"Snapshot : {root / '.ai/runtime/atlas_doctor/latest_audit.json'}")
    return payload


def command_live(root: Path, args) -> dict[str, Any]:
    _audit(root, force=False, integrity_mode=None)
    payload = inspect_live(
        root,
        sample_seconds=args.sample_seconds,
        trace_io=not args.no_io_trace,
        quiet=args.json,
    )
    if not args.json:
        summary = payload.get('summary') or {}
        print(f"Pic RAM : {summary.get('rss_peak_mb')} MiB | CPU pic : {summary.get('cpu_peak_total_percent')}% | Processus max : {summary.get('max_process_count')}")
        io_trace = payload.get('io_trace') or {}
        io_summary = io_trace.get('summary') or {}
        if io_summary:
            print(f"I/O : {io_summary.get('unique_files', 0)} fichiers | lecture {io_summary.get('read_ms', 0)} ms | JSON {io_summary.get('json_ms', 0)} ms")
    return payload


def command_perf(root: Path, args) -> dict[str, Any]:
    _audit(root, force=False, integrity_mode=None)
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
    audit_comparison = compare_runs(load_json(root, 'latest_audit'), load_json(root, 'previous_audit'))
    perf_comparison = compare_performance(load_json(root, 'latest_perf'), load_json(root, 'previous_perf'))
    payload = {'audit': audit_comparison, 'performance': perf_comparison}
    if not args.json:
        print(
            f"Audit - nouveaux problemes : {len(audit_comparison.get('new_issues', []))} | "
            f"corriges : {len(audit_comparison.get('fixed_issues', []))} | "
            f"inchanges : {audit_comparison.get('unchanged_count', 0)}"
        )
        print(
            f"Observations - nouvelles : {len(audit_comparison.get('new_observations', []))} | "
            f"disparues : {len(audit_comparison.get('resolved_observations', []))} | "
            f"inchangees : {audit_comparison.get('unchanged_observations_count', 0)}"
        )
        regressions = perf_comparison.get('regressions_15pct', [])
        improvements = perf_comparison.get('improvements_15pct', [])
        print(f"Perf - regressions >=15% : {len(regressions)} | ameliorations >=15% : {len(improvements)}")
        for row in regressions[:10]:
            print(f"  WARN {row['metric']}: {row['previous']} -> {row['current']} ({row['delta_percent']}%)")
    return payload


def _filter_findings(rows: list[dict[str, Any]], severity: list[str] | None) -> list[dict[str, Any]]:
    if not severity:
        return rows
    allowed = {item.upper() for item in severity}
    return [item for item in rows if str(item.get('severity') or '').upper() in allowed]


def _print_finding(item: dict[str, Any], *, kind: str) -> None:
    line = f":{item['line']}" if item.get('line') else ''
    print(
        f"[{kind}][{item.get('severity', 'INFO')}] {item.get('rule', '?')} - "
        f"{item.get('path', '?')}{line} - {item.get('title', '')} "
        f"({item.get('confidence', 'suspect')})"
    )


def command_issues(root: Path, args) -> dict[str, Any]:
    """Show the complete Doctor truth: blocking issues AND observations.

    The command name is kept for CLI compatibility, but observations are not
    hidden anymore. A clean actionable count must never make review evidence
    disappear from the human or AI view.
    """

    audit = _audit(root, force=False, integrity_mode=None)
    issues = _filter_findings(list(audit.get('issues', [])), args.severity)
    observations = _filter_findings(list(audit.get('observations', [])), args.severity)
    payload = {
        'issues_count': len(issues),
        'observations_count': len(observations),
        'total_findings': len(issues) + len(observations),
        'issues': issues,
        'observations': observations,
    }
    if not args.json:
        print(f"Problemes : {len(issues)} | Observations : {len(observations)} | Total visible : {len(issues) + len(observations)}")
        if issues:
            print('\n--- PROBLEMES ---')
            for item in issues:
                _print_finding(item, kind='ISSUE')
        if observations:
            print('\n--- OBSERVATIONS A REVOIR ---')
            for item in observations:
                _print_finding(item, kind='OBS')
    return payload


def command_verify(root: Path, args) -> dict[str, Any]:
    before = load_json(root, 'latest_audit')
    current = run_audit(root, integrity_mode='critical')
    comparison = compare_runs(current, before)
    payload = {'audit': current.get('summary'), 'comparison': comparison}
    if not args.json:
        print(
            f"Nouveaux problemes : {len(comparison.get('new_issues', []))} | "
            f"Corriges : {len(comparison.get('fixed_issues', []))} | "
            f"Nouvelles observations : {len(comparison.get('new_observations', []))} | "
            f"Observations disparues : {len(comparison.get('resolved_observations', []))}"
        )
        _summary(current)
    return payload


def command_report(root: Path, args) -> dict[str, Any]:
    _audit(root, force=False, integrity_mode=None)
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
    audit = run_audit(root, integrity_mode='full')
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
    audit.add_argument('--gate', choices=('fast', 'critical', 'full', 'deep'), default='critical')

    live = sub.add_parser('live')
    live.add_argument('--sample-seconds', type=float, default=0.5)
    live.add_argument('--no-io-trace', action='store_true')

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


def _read_choice() -> str:
    if os.name == 'nt':
        import msvcrt

        while True:
            choice = msvcrt.getwch()
            if choice in '0123456789':
                print(choice)
                return choice
    return input('Choix : ').strip()


def menu(root: Path) -> int:
    actions = {
        '1': ('Audit complet', lambda: command_audit(root, argparse.Namespace(force=True, gate='critical', json=False))),
        '2': ('Inspecteur performances LIVE + I/O', lambda: command_live(root, argparse.Namespace(sample_seconds=0.5, no_io_trace=False, json=False))),
        '3': ('Performance Lab automatise', lambda: command_perf(root, argparse.Namespace(files_only=False, json=False))),
        '4': ('Comparer avec le dernier audit', lambda: command_compare(root, argparse.Namespace(json=False))),
        '5': ('Voir TOUS les constats (problemes + observations)', lambda: command_issues(root, argparse.Namespace(severity=None, json=False))),
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
        print('Choix : ', end='', flush=True)
        choice = _read_choice()
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
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    json_requested = '--json' in raw_argv
    raw_argv = [item for item in raw_argv if item != '--json']
    args = parser.parse_args(raw_argv)
    args.json = json_requested
    root = project_root(Path.cwd())
    if not args.command:
        return menu(root)
    handlers = {
        'audit': command_audit,
        'live': command_live,
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
