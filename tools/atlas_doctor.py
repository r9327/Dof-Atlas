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
    evaluate_ponytail,
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
    if payload.get("status") == "PASS":
        from tools.atlas_doctor_lib.graph_audit import audit_current_graph
        payload["graph_audit"] = audit_current_graph(root, graph_evidence=payload)
    if not args.json:
        print(f"Architecture : {payload['status']}")
        print(payload.get("reason", ""))
        print(f"Graphify : {(payload.get('tool') or {}).get('status', 'see generation')}")
        summary = payload.get("summary") or {}
        if summary:
            print(f"Noeuds : {summary['node_count']} | Relations : {summary['link_count']}")
            for row in summary["most_connected_files"][:5]:
                print(f"  {row['path']} : {row['neighbor_file_count']} fichiers voisins")
        graph_triage = payload.get("graph_audit") or {}
        if graph_triage:
            metrics = graph_triage.get("metrics") or {}
            print(f"Audit des nœuds : {graph_triage.get('status')} | code peu lié : {metrics.get('weak_production_nodes_degree1', 0)}")
            print(f"Couplages à revoir : {metrics.get('high_fanout_app_files', 0)} | inversions confirmées : {metrics.get('confirmed_runtime_to_tools_imports', 0)}")
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


def command_graph_audit(root: Path, args) -> dict[str, Any]:
    from tools.atlas_doctor_lib.graph_audit import audit_current_graph
    result = audit_current_graph(
        root, deep=getattr(args, "deep", False), weak_offset=getattr(args, "offset", 0)
    )
    if not args.json:
        metrics = result.get("metrics") or {}
        print(f"Doctor + Graphify audit : {result['status']}")
        print(f"SHA : {result.get('candidate_sha', 'UNVERIFIED')} | nœuds : {metrics.get('node_count', 0)}")
        print(f"Isolés : {metrics.get('isolated_nodes', 0)} | communautés isolées : {metrics.get('isolated_communities', 0)}")
        print(f"Hubs : {metrics.get('high_fanout_app_files', 0)} | imports app->tools prouvés : {metrics.get('confirmed_runtime_to_tools_imports', 0)}")
        cycles = result.get("import_cycles") or {}
        plan = result.get("remediation_plan") or {}
        print(f"Cycles suspects : {cycles.get('suspected_cycles', 0)} | confirmés : {cycles.get('source_confirmed_cycles', 0)}")
        print(f"Corrections proposées : {plan.get('task_count', 0)}")
        print("Les nœuds isolés et communautés candidates ne prouvent pas du code mort.")
        if result.get("reason"):
            print(result["reason"])
    return result


def command_change_plan(root: Path, args) -> dict[str, Any]:
    from tools.atlas_doctor_lib.change_intelligence import build_change_plan
    result = build_change_plan(root, base_ref=args.base_ref)
    if not args.json:
        print(f"Doctor change-plan: {result['status']} | {len(result['paths'])} chemins")
        print(f"Imports casses confirmes : {len(result.get('structural_findings', []))}")
        print(f"Tests proposes : {len(result.get('targeted_tests', []))} | executes : non")
        print(result.get('reason', ''))
    return result


def command_refactor_preview(root: Path, args) -> dict[str, Any]:
    from tools.atlas_doctor_lib.refactor_simulation import simulate_refactor
    result = simulate_refactor(root, args.paths, action=args.action,
                               replacement=args.to, depth=args.depth)
    if not args.json:
        print(f"Doctor refactor preview: {result['status']}")
        print(f"Consumer files: {len(result.get('consumer_files', []))} | no edits or tests executed")
        print(result.get("reason", ""))
    return result


def command_graph_live(root: Path, args) -> dict[str, Any]:
    from tools.atlas_doctor_lib.live_graph import change_snapshot, serve_graph_live
    if args.once:
        import json
        from tools.atlas_doctor_lib.architecture import graph_status
        graph = graph_status(root)
        if graph.get("status") not in {"PASS", "STALE"}:
            result = {"status": "BLOCKED", "reason": graph.get("reason")}
        else:
            data = json.loads(Path(graph["graph"]).read_text(encoding="utf-8"))
            result = change_snapshot(root, data.get("built_at_commit"))
            result["graph_validation"] = graph["status"]
        if not args.json:
            print(f"Doctor Graphify LIVE status: {result['status']}")
        return result
    return serve_graph_live(root, port=args.port, open_browser=args.open)


def command_graph_ui(root: Path, args) -> dict[str, Any]:
    from tools.atlas_doctor_lib.doctor_graph_ui import export_interactive_graph
    payload = export_interactive_graph(root, trace_path=args.trace)
    if payload.get("status") == "PASS" and args.open:
        import webbrowser
        webbrowser.open(Path(payload["path"]).as_uri())
    if not args.json:
        print(f"Doctor interactive Graphify: {payload['status']}")
        print(payload.get("path", payload.get("reason", "")))
    return payload


def command_runtime_trace(root: Path, args) -> dict[str, Any]:
    from tools.atlas_doctor_lib.runtime_observation import run_traced_module
    target = root / ".ai/runtime/atlas_doctor/traces" / (args.module.replace(".", "_") + ".json")
    payload = run_traced_module(root, args.module, target, max_events=args.max_events)
    if not args.json:
        print(f"Doctor runtime trace: {payload['status']} | {payload['events_captured']} events")
        print(f"Trace output: {target}")
    return {"status": payload["status"], "events_captured": payload["events_captured"],
            "truncated": payload["truncated"], "trace_path": str(target)}


def command_code_inspect(root: Path, args) -> dict[str, Any]:
    from tools.atlas_doctor_lib.deep_intelligence import inspect_code
    from tools import atlas_integrity
    paths = list(args.paths)
    if args.base_ref:
        paths.extend(atlas_integrity.changed_files(root, args.base_ref))
    paths = sorted({p for p in paths if p.endswith(".py") and (root / p).is_file()})
    payload = inspect_code(root, paths=paths, entrypoints=args.entrypoint,
                           baseline=args.baseline)
    if not args.json:
        summary = payload.get("source") or {}
        print(f"Doctor code-inspect: {payload['status']} | {len(summary.get('paths_inspected', []))} Python files")
        print(f"Duplicates: {(summary.get('counts') or {}).get('duplicate_groups', 0)} | "
              f"Silent error candidates: {(summary.get('counts') or {}).get('silent_exceptions', 0)}")
        print("No tests executed; Graphify is never rebuilt implicitly.")
    return payload


def command_graph_compare(root: Path, args) -> dict[str, Any]:
    from tools.atlas_doctor_lib.architecture import graph_status
    from tools.atlas_doctor_lib.graph_intelligence import compare_graphs
    evidence = graph_status(root)
    if evidence.get("status") != "PASS":
        return {"status": "BLOCKED", "reason": evidence.get("reason", "Current graph required."),
                "rebuild_command": "python -m tools.atlas_doctor graph --rebuild"}
    try:
        baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
        candidate = json.loads(Path(evidence["graph"]).read_text(encoding="utf-8"))
        result = compare_graphs(baseline, candidate)
        if result["candidate_sha"] != evidence["git"]["head"]:
            raise ValueError("Candidate graph SHA differs from current checkout.")
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        return {"status": "BLOCKED", "reason": str(exc)}
    if not args.json:
        print(f"Graphify {result['baseline_sha']} -> {result['candidate_sha']}")
        print(f"Nouveaux orphelins : {len(result['new_orphan_symbols'])} | nouveaux cycles : {len(result['new_candidate_import_cycles'])}")
        print("Les différences structurelles sont des pistes, pas des défauts confirmés.")
    return result


def command_ponytail(root: Path, args) -> dict[str, Any]:
    payload = evaluate_ponytail(root, base_ref=args.base_ref, required=True)
    if not args.json:
        summary = payload.get('summary') or {}
        print(f"Ponytail : {payload.get('status', 'N/A')} | Base : {payload.get('base_ref', 'N/A')}")
        print(
            f"Findings : {summary.get('findings_total', 0)} | "
            f"Fichiers : {summary.get('changed_files', 0)} | "
            f"Ajouts : {summary.get('added_lines', 0)} lignes"
        )
        for item in payload.get('findings', []):
            line = f":{item['line']}" if item.get('line') else ''
            print(f"[{item['severity']}] {item['rule']} - {item['path']}{line} - {item['title']}")
        graph = payload.get('graph_evidence') or {}
        print(f"Graphify evidence : {graph.get('status', 'N/A')}")
    return payload


def menu_diagnostics(root: Path) -> dict[str, Any]:
    payload = command_quick(root, argparse.Namespace(json=False))
    choice = input("A : audit avec gate CRITICAL | P : problemes | T : Ponytail | Entree : retour\n").strip().casefold()
    if choice == "a":
        return command_audit(root, argparse.Namespace(force=True, gate="critical", json=False))
    if choice == "p":
        return command_issues(root, argparse.Namespace(severity=None, json=False))
    if choice == "t":
        return command_ponytail(root, argparse.Namespace(base_ref=None, json=False))
    return payload


def menu_graph(root: Path) -> dict[str, Any]:
    payload = command_graph(root, argparse.Namespace(json=False, rebuild=False, install=False, open=False))
    choice = input("R : reconstruire | I : installer Graphify puis generer | A : auditer graphe | O : ouvrir HTML | Entree : retour\n").strip().casefold()
    if choice == "a":
        return command_graph_audit(root, argparse.Namespace(json=False))
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
                                 base_ref=args.base_ref or "HEAD", rebuild_graph=args.rebuild_graph,
                                 baseline_name=getattr(args, "baseline", None),
                                 save_baseline=getattr(args, "save_baseline", None))
        if not args.json:
            _verification_summary(payload)
        return payload
    if getattr(args, "baseline", None) or getattr(args, "save_baseline", None):
        raise ValueError("Named baselines require targeted verify paths.")
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
    ponytail = evaluate_ponytail(root, required=True)
    perf = run_performance(root, include_runtime=True)
    report = build_ai_report(root)
    payload = {
        'audit': audit.get('summary'),
        'ponytail': ponytail,
        'performance_status': (perf.get('runtime') or {}).get('status'),
        'report': report,
    }
    if not args.json:
        _summary(audit)
        print(f"Ponytail : {ponytail.get('status', 'N/A')}")
        print(f"Performance runtime : {payload['performance_status']}")
        print(f"Rapport : {root / '.ai/runtime/atlas_doctor/latest_report.json'}")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Dofus Atlas Doctor - audit, performance et rapport IA.')
    parser.add_argument('--json', action='store_true', help='Sortie JSON machine-readable.')
    sub = parser.add_subparsers(dest='command')

    sub.add_parser('quick', help='Diagnostic statique rapide; aucun scan Graphify ni gate.')
    ch = sub.add_parser('change-plan', help='Plan diff Git + consommateurs Graphify + tests cibles; aucun test execute.')
    ch.add_argument('--base-ref', required=True, help='Ref Git explicite pour la comparaison.')
    ga = sub.add_parser('graph-audit', help='Audit Graphify : cycles, communautés, consommateurs, plan et RAM.')
    ga.add_argument('--deep', action='store_true', help='Rechercher les consommateurs dans les sources suivies.')
    ga.add_argument('--offset', type=int, default=0, help='Décalage parmi les candidats faiblement connectés (pages de 30).')
    rp = sub.add_parser('refactor-preview', help='Simuler impact et tests requis sans modifier le code.')
    rp.add_argument('paths', nargs='+')
    rp.add_argument('--action', choices=('remove', 'move', 'consolidate'), default='remove')
    rp.add_argument('--to', help='Chemin relatif cible pour move/consolidate.')
    rp.add_argument('--depth', type=int, choices=(1, 2), default=2)
    gl = sub.add_parser('graph-live', help='Suivi Git temps reel dans Graphify Web local, sans rebuilder.')
    gl.add_argument('--port', type=int, default=8765)
    gl.add_argument('--open', action='store_true')
    gl.add_argument('--once', action='store_true', help='Retourner seulement les changements courants.')
    gu = sub.add_parser('graph-ui', help='Exporter Graphify interactif local avec diagnostics Doctor.')
    gu.add_argument('--open', action='store_true', help='Ouvrir le rapport HTML dans le navigateur.')
    gu.add_argument('--trace', type=Path, help='Trace runtime JSON dans .ai/runtime pour enrichir les liens.')
    rt = sub.add_parser('runtime-trace', help='Tracer explicitement les appels Python d un module (mode instrumente).')
    rt.add_argument('--module', required=True, help='Module de scenario de test a executer.')
    rt.add_argument('--max-events', type=int, default=5000)
    ci = sub.add_parser('code-inspect', help='Inspecter AST, doublons, accessibilite et gardes architectures, sans tests.')
    ci.add_argument('paths', nargs='*', help='Fichiers Python explicitement cibles.')
    ci.add_argument('--base-ref', help='Inclure les fichiers modifies depuis la reference.')
    ci.add_argument('--entrypoint', action='append', help='Point entree connu (plusieurs possibles).')
    ci.add_argument('--baseline', type=Path, help='Ancien Graphify graph.json pour comparaison.')
    gc = sub.add_parser('graph-compare', help='Comparer l’ancien graph.json à celui du HEAD actuel.')
    gc.add_argument('--baseline', required=True, type=Path)
    graph = sub.add_parser('graph', help='Architecture Graphify; lecture du graph par defaut.')
    graph.add_argument('--rebuild', action='store_true', help='Generer explicitement le graph AST, clustering et HTML.')
    graph.add_argument('--install', action='store_true', help='Installer explicitement Graphify pinne via uv puis generer.')
    graph.add_argument('--open', action='store_true', help='Ouvrir le HTML du graph courant.')
    graph.add_argument('--impact', nargs='+', help='Consommateurs candidats confirmes par imports; aucune reconstruction implicite.')
    graph.add_argument('--symbol', help='Symbole top-level candidat; precision de liaison a revoir.')
    graph.add_argument('--depth', type=int, choices=(1, 2), default=1)

    ponytail = sub.add_parser('ponytail', help='Evaluer le diff avec la policy Ponytail partagee du depot.')
    ponytail.add_argument('--base-ref', help='Base Git explicite; sinon merge-base origin/main, puis HEAD~1.')

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
    baselines = verify.add_mutually_exclusive_group()
    baselines.add_argument('--baseline', help='Comparer une baseline nommee et sa base SHA immuable.')
    baselines.add_argument('--save-baseline', help='Enregistrer une baseline avant modification; aucun ecrasement.')
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
        'graph-audit': command_graph_audit,
        'change-plan': command_change_plan,
        'code-inspect': command_code_inspect,
        'runtime-trace': command_runtime_trace,
        'graph-ui': command_graph_ui,
        'graph-live': command_graph_live,
        'refactor-preview': command_refactor_preview,
        'graph-compare': command_graph_compare,
        'ponytail': command_ponytail,
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
    if args.command == 'ponytail':
        return {'PASS': 0, 'REVIEW': 1, 'FAIL': 2, 'UNAVAILABLE': 2}.get(payload.get('status'), 2)
    if args.command == 'graph':
        if payload.get("status") != "PASS":
            return 1
        # The graph visualization passing does not override a failed Doctor
        # architectural audit (e.g. a source-confirmed app -> tools inversion).
        graph_audit = payload.get("graph_audit") or {}
        return 0 if graph_audit.get("status") in {"PASS", "REVIEW"} else 2
    if args.command == 'refactor-preview':
        return 2 if payload['status'] == 'BLOCKED' else 1
    if args.command == 'graph-live':
        return 2 if payload['status'] == 'BLOCKED' else 0
    if args.command == 'graph-ui':
        return 0 if payload['status'] == 'PASS' else 2
    if args.command == 'runtime-trace':
        return 0 if payload['status'] == 'RECORDED' else 1
    if args.command == 'code-inspect':
        return {'PASS': 0, 'REVIEW': 1, 'BLOCKED': 2}[payload['status']]
    if args.command == 'change-plan':
        return {'READY': 0, 'REVIEW': 1, 'BLOCKED': 2}[payload['status']]
    if args.command in {'graph-audit', 'graph-compare'}:
        return 0 if payload['status'] in {'PASS', 'REVIEW'} else 2
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
