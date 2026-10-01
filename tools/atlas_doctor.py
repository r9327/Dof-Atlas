from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

# Preserve direct-script callers by delegating to the canonical module entry.
if __name__ == "__main__" and not __package__:
    import subprocess
    raise SystemExit(subprocess.call(
        [sys.executable, "-m", "tools.atlas_doctor", *sys.argv[1:]],
        cwd=Path(__file__).resolve().parents[1],
    ))

from tools.atlas_doctor_lib import (
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
    print(f"Problemes : {summary.get('issues_total', 0)} | Duree : {payload.get('duration_ms', 0)} ms")


def command_quick(root: Path, args) -> dict[str, Any]:
    payload = _audit(root, integrity_mode=None)
    if not args.json:
        _summary(payload)
    return payload


def command_graph(root: Path, args) -> dict[str, Any]:
    from tools import graphify
    from tools.atlas_doctor_lib.architecture import architecture
    if args.install:
        result = graphify.install_graphify()
        if result["status"] != "PASS":
            if not args.json:
                print(result.get("reason"))
            return result
    payload = architecture(root, rebuild=args.rebuild or args.install)
    if not args.json:
        print(f"Architecture : {payload['status']}")
        print(payload.get("reason", ""))
        print(f"Graphify : {(payload.get('tool') or {}).get('status', 'see generation')}")
        summary = payload.get("summary") or {}
        if summary:
            print(f"Noeuds : {summary['node_count']} | Relations : {summary['link_count']}")
            for row in summary["most_connected_files"][:5]:
                print(f"  {row['path']} : {row['neighbor_file_count']} fichiers voisins")
        print(f"HTML : {payload.get('html', root / 'graphify-out/graph.html')}")
        print(f"Rapport : {payload.get('report', root / 'graphify-out/GRAPH_REPORT.md')}")
        if payload["status"] != "PASS":
            print("Utiliser Graph > reconstruire (ou --rebuild); installation explicite : --install.")
    if getattr(args, "impact", None):
        from tools.agent import reverse_impact_payload
        payload["impact"] = reverse_impact_payload(root, args.impact, symbol=args.symbol, depth=args.depth)
        if not args.json:
            print(f"Impact : {payload['impact']['status']}")
            print("Fichiers : " + ", ".join(payload["impact"]["impacted_files"]))
        if payload["impact"]["status"] != "PASS" and payload["status"] == "PASS":
            payload["status"] = "REVIEW"
    if args.open and payload["status"] == "PASS":
        import webbrowser
        webbrowser.open(Path(payload["html"]).as_uri())
    return payload


def menu_diagnostics(root: Path) -> dict[str, Any]:
    payload = command_quick(root, argparse.Namespace(json=False))
    choice = input("A : audit avec gate CRITICAL | P : problemes | Entree : retour\n").strip().casefold()
    if choice == "a":
        return command_audit(root, argparse.Namespace(force=True, gate="critical", json=False))
    if choice == "p":
        return command_issues(root, argparse.Namespace(severity=None, json=False))
    return payload


def menu_graph(root: Path) -> dict[str, Any]:
    payload = command_graph(root, argparse.Namespace(json=False, rebuild=False, install=False, open=False))
    choice = input("R : reconstruire | I : installer Graphify puis generer | O : ouvrir HTML | Entree : retour\n").strip().casefold()
    if choice in {"r", "i", "o"}:
        payload = command_graph(root, argparse.Namespace(
            json=False, rebuild=choice == "r", install=choice == "i", open=choice == "o",
        ))
    return payload


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
            f"Audit - nouveaux : {len(audit_comparison.get('new_issues', []))} | "
            f"corriges : {len(audit_comparison.get('fixed_issues', []))} | "
            f"inchanges : {audit_comparison.get('unchanged_count', 0)}"
        )
        regressions = perf_comparison.get('regressions_15pct', [])
        improvements = perf_comparison.get('improvements_15pct', [])
        print(f"Perf - regressions >=15% : {len(regressions)} | ameliorations >=15% : {len(improvements)}")
        for row in regressions[:10]:
            print(f"  WARN {row['metric']}: {row['previous']} -> {row['current']} ({row['delta_percent']}%)")
    return payload


def command_issues(root: Path, args) -> dict[str, Any]:
    audit = _audit(root, force=False, integrity_mode=None)
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
    if getattr(args, "paths", None):
        if getattr(args, "gate", None):
            raise ValueError("--gate belongs to legacy verify; use --soft/--medium/--hard with paths.")
        from tools.agent import verify_payload, _verification_summary
        payload = verify_payload(root, args.paths, level=args.level, structural=args.structural,
                                 base_ref=args.base_ref or "HEAD", rebuild_graph=args.rebuild_graph)
        if not args.json:
            _verification_summary(payload)
        return payload
    before = load_json(root, 'latest_audit')
    explicit_base = getattr(args, 'base_ref', None)
    baseline_head = ((before or {}).get('git') or {}).get('head')
    base_ref = explicit_base or baseline_head or 'HEAD'
    current = run_audit(root, integrity_mode=getattr(args, 'gate', None) or 'critical', base_ref=base_ref)
    comparison = compare_runs(current, before)
    integrity = current.get('integrity') or {}
    summary = current.get('summary') or {}
    if summary.get('verdict') == 'FAIL' or integrity.get('status') == 'FAIL':
        status = 'FAIL'
    elif (integrity.get('status') != 'PASS' or summary.get('verdict') != 'PASS'
          or comparison.get('status') != 'PASS'):
        status = 'REVIEW'
    else:
        status = 'PASS'
    blockers = (integrity.get('report') or {}).get('blockers') or []
    reason = ', '.join(str(item) for item in blockers) or integrity.get('reason')
    if not reason and status == 'REVIEW':
        reason = comparison.get('reason') or 'Audit findings require review; no regression cause is inferred.'
    if not reason and status == 'FAIL':
        reason = 'Audit failed; inspect the recorded evidence.'
    payload = {
        'schema_version': 1, 'kind': 'verification', 'status': status,
        'base_ref': base_ref, 'audit': summary, 'integrity': integrity,
        'comparison': comparison, 'primary_cause': reason,
        'reproduction_command': integrity.get('command'),
        'next_action': 'Inspect the recorded blockers and reproduction command.' if status != 'PASS' else None,
    }
    if not args.json:
        print(f"Verification : {status} | Base : {base_ref}")
        if reason:
            print(reason)
        print(f"Nouveaux : {len(comparison.get('new_issues', []))} | Corriges : {len(comparison.get('fixed_issues', []))}")
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

    sub.add_parser('quick', help='Diagnostic statique rapide; aucun scan Graphify ni gate.')
    graph = sub.add_parser('graph', help='Architecture Graphify; lecture du graph par defaut.')
    graph.add_argument('--rebuild', action='store_true', help='Generer explicitement le graph AST, clustering et HTML.')
    graph.add_argument('--install', action='store_true', help='Installer explicitement Graphify pinne via uv puis generer.')
    graph.add_argument('--open', action='store_true', help='Ouvrir le HTML du graph courant.')
    graph.add_argument('--impact', nargs='+', help='Consommateurs candidats confirmes par imports; aucune reconstruction implicite.')
    graph.add_argument('--symbol', help='Symbole top-level candidat; precision de liaison a revoir.')
    graph.add_argument('--depth', type=int, choices=(1, 2), default=1)

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
    verify = sub.add_parser('verify')
    verify.add_argument('paths', nargs='*', help='Targeted Agent plan / Doctor execution; omit for legacy audit comparison.')
    verify.add_argument('--gate', choices=('fast', 'critical', 'full', 'deep'), help='Legacy verify without paths; default critical.')
    verify.add_argument('--structural', action='store_true')
    verify.add_argument('--rebuild-graph', action='store_true')
    levels = verify.add_mutually_exclusive_group()
    levels.add_argument('--soft', dest='level', action='store_const', const='SOFT')
    levels.add_argument('--medium', dest='level', action='store_const', const='MEDIUM')
    levels.add_argument('--hard', dest='level', action='store_const', const='HARD')
    verify.add_argument('--base-ref', help='Base du changement; sinon HEAD du snapshot precedent, puis HEAD.')
    sub.add_parser('report')
    sub.add_parser('clean')
    sub.add_parser('all')
    return parser



def menu_verify(root: Path) -> dict[str, Any]:
    import shlex
    paths = shlex.split(input("Chemins relatifs avec / (vide : verification historique) : ").strip())
    if not paths:
        return command_verify(root, argparse.Namespace(json=False))
    return command_verify(root, argparse.Namespace(
        json=False, paths=paths, gate=None, level=None, structural=False,
        base_ref="HEAD", rebuild_graph=False,
    ))


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
        '1': ('Diagnostic rapide / audit / problemes', lambda: menu_diagnostics(root)),
        '2': ('Inspecteur performances LIVE + I/O', lambda: command_live(root, argparse.Namespace(sample_seconds=0.5, no_io_trace=False, json=False))),
        '3': ('Performance Lab automatise', lambda: command_perf(root, argparse.Namespace(files_only=False, json=False))),
        '4': ('Comparer avec le dernier audit', lambda: command_compare(root, argparse.Namespace(json=False))),
        '5': ('Architecture / Graph', lambda: menu_graph(root)),
        '6': ('Validation ciblee / verifier les corrections', lambda: menu_verify(root)),
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
    root = project_root(Path(__file__))
    if not args.command:
        return menu(root)
    handlers = {
        'quick': command_quick,
        'graph': command_graph,
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
    if args.command == 'verify':
        return {'PASS': 0, 'REVIEW': 1, 'FAIL': 2}[payload['status']]
    if args.command == 'graph':
        return 0 if payload['status'] == 'PASS' else 1
    if args.command in {'audit', 'quick'}:
        verdict = (payload.get('summary') or {}).get('verdict')
        return 2 if verdict == 'FAIL' else (1 if verdict == 'WARN' else 0)
    if args.command == 'perf':
        runtime = payload.get('runtime') or {}
        if runtime and runtime.get('status') == 'FAIL':
            return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
