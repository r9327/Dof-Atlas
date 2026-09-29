from __future__ import annotations

from typing import Any

from .core import load_json, utc_now, write_json


def compare_runs(current: dict[str, Any] | None, previous: dict[str, Any] | None) -> dict[str, Any]:
    if not current or not previous:
        return {'status': 'UNAVAILABLE', 'reason': 'Deux snapshots sont necessaires.'}
    current_mode = current.get('integrity_mode')
    previous_mode = previous.get('integrity_mode')
    if current_mode != previous_mode:
        return {
            'status': 'UNAVAILABLE',
            'reason': f'Modes audit differents: {previous_mode or "STATIC"} -> {current_mode or "STATIC"}.',
        }
    current_issues = {item['id']: item for item in current.get('issues', [])}
    previous_issues = {item['id']: item for item in previous.get('issues', [])}
    new_ids = sorted(current_issues.keys() - previous_issues.keys())
    fixed_ids = sorted(previous_issues.keys() - current_issues.keys())
    return {
        'status': 'PASS',
        'new_issues': [current_issues[item] for item in new_ids],
        'fixed_issues': [previous_issues[item] for item in fixed_ids],
        'unchanged_count': len(current_issues.keys() & previous_issues.keys()),
    }


def _flatten_numeric(payload: Any, prefix: str = '') -> dict[str, float]:
    values: dict[str, float] = {}
    if isinstance(payload, dict):
        for key, value in payload.items():
            child = f'{prefix}.{key}' if prefix else str(key)
            values.update(_flatten_numeric(value, child))
    elif isinstance(payload, (int, float)) and not isinstance(payload, bool):
        values[prefix] = float(payload)
    return values


def _is_cost_metric(metric: str) -> bool:
    leaf = metric.rsplit('.', 1)[-1]
    return (
        leaf.endswith('_ms')
        or leaf.endswith('_mb')
        or leaf.endswith('_percent')
        or leaf.endswith('_percent_one_core')
    )


def compare_performance(current: dict[str, Any] | None, previous: dict[str, Any] | None) -> dict[str, Any]:
    if not current or not previous:
        return {'status': 'UNAVAILABLE', 'reason': 'Deux mesures performance sont necessaires.'}

    current_clean = (((current.get('runtime') or {}).get('benchmark') or {}).get('after') or {})
    previous_clean = (((previous.get('runtime') or {}).get('benchmark') or {}).get('after') or {})
    current_values = _flatten_numeric(current_clean)
    previous_values = _flatten_numeric(previous_clean)

    rows: list[dict[str, Any]] = []
    for metric in sorted(current_values.keys() & previous_values.keys()):
        if not _is_cost_metric(metric):
            continue
        before = previous_values[metric]
        after = current_values[metric]
        delta = after - before
        percent = None if before == 0 else round((delta / before) * 100.0, 2)
        rows.append({
            'metric': metric,
            'previous': round(before, 3),
            'current': round(after, 3),
            'delta': round(delta, 3),
            'delta_percent': percent,
        })

    current_file = current.get('file_profile') or {}
    previous_file = previous.get('file_profile') or {}
    for metric in ('total_read_ms', 'total_json_parse_ms', 'p95_file_total_ms'):
        if isinstance(current_file.get(metric), (int, float)) and isinstance(previous_file.get(metric), (int, float)):
            before = float(previous_file[metric])
            after = float(current_file[metric])
            delta = after - before
            rows.append({
                'metric': f'file_profile.{metric}',
                'previous': round(before, 3),
                'current': round(after, 3),
                'delta': round(delta, 3),
                'delta_percent': None if before == 0 else round((delta / before) * 100.0, 2),
            })

    regressions = [
        row for row in rows
        if row['delta_percent'] is not None
        and row['delta_percent'] >= 15.0
        and (row['current'] - row['previous']) > 1.0
    ]
    improvements = [
        row for row in rows
        if row['delta_percent'] is not None
        and row['delta_percent'] <= -15.0
        and (row['previous'] - row['current']) > 1.0
    ]
    return {
        'status': 'WARN' if regressions else 'PASS',
        'metrics': rows,
        'regressions_15pct': regressions,
        'improvements_15pct': improvements,
    }


def _compact_io_trace(trace: dict[str, Any] | None, *, limit: int = 20) -> dict[str, Any] | None:
    if not trace:
        return None
    return {
        'summary': trace.get('summary'),
        'slowest': list(trace.get('slowest') or [])[:limit],
    }


def _compact_performance(perf: dict[str, Any] | None) -> dict[str, Any] | None:
    if not perf:
        return None
    file_profile = perf.get('file_profile') or {}
    runtime = perf.get('runtime') or {}
    benchmark = runtime.get('benchmark') or {}
    return {
        'generated_at': perf.get('generated_at'),
        'git': perf.get('git'),
        'file_profile': {
            'files_measured': file_profile.get('files_measured'),
            'files_skipped': file_profile.get('files_skipped'),
            'total_read_ms': file_profile.get('total_read_ms'),
            'total_json_parse_ms': file_profile.get('total_json_parse_ms'),
            'p50_file_total_ms': file_profile.get('p50_file_total_ms'),
            'p95_file_total_ms': file_profile.get('p95_file_total_ms'),
            'slowest': list(file_profile.get('slowest') or [])[:20],
        },
        'runtime': {
            'status': runtime.get('status'),
            'io_trace_status': runtime.get('io_trace_status'),
            'clean_duration_ms': runtime.get('clean_duration_ms'),
            'trace_duration_ms': runtime.get('trace_duration_ms'),
            'benchmark_after': benchmark.get('after'),
            'io_trace': _compact_io_trace(runtime.get('io_trace')),
        },
    }


def _compact_live(live: dict[str, Any] | None) -> dict[str, Any] | None:
    if not live:
        return None
    return {
        'generated_at': live.get('generated_at'),
        'git': live.get('git'),
        'duration_ms': live.get('duration_ms'),
        'summary': live.get('summary'),
        'io_trace': _compact_io_trace(live.get('io_trace')),
    }


def _compact_integrity(integrity: dict[str, Any] | None) -> dict[str, Any] | None:
    if not integrity:
        return None
    report = integrity.get('report') or {}
    groups = report.get('groups') or {}
    required_groups = {
        name: {
            'status': group.get('status'),
            'blockers': group.get('blockers', []),
            'tests': group.get('tests'),
        }
        for name, group in groups.items()
        if isinstance(group, dict) and group.get('required')
    }
    return {
        'status': integrity.get('status'),
        'mode': integrity.get('mode'),
        'duration_ms': integrity.get('duration_ms'),
        'returncode': integrity.get('returncode'),
        'verdict': report.get('verdict'),
        'risk': report.get('risk'),
        'blockers': report.get('blockers', []),
        'counts': report.get('counts'),
        'required_groups': required_groups,
    }


def build_ai_report(root) -> dict[str, Any]:
    audit = load_json(root, 'latest_audit')
    perf = load_json(root, 'latest_perf')
    live = load_json(root, 'latest_live_perf')
    previous_audit = load_json(root, 'previous_audit')
    previous_perf = load_json(root, 'previous_perf')
    comparison = compare_runs(audit, previous_audit)
    perf_comparison = compare_performance(perf, previous_perf)
    issues = list((audit or {}).get('issues', []))
    observations = list((audit or {}).get('observations', []))
    actionable = [
        item for item in issues
        if item.get('severity') in {'CRITICAL', 'HIGH', 'MEDIUM'}
        or item.get('confidence') == 'confirmed'
    ]
    payload = {
        'schema_version': 1,
        'kind': 'ai_report',
        'generated_at': utc_now(),
        'audit_summary': (audit or {}).get('summary'),
        'git': (audit or perf or live or {}).get('git'),
        'integrity': _compact_integrity((audit or {}).get('integrity')),
        'audit_comparison': comparison,
        'performance_comparison': perf_comparison,
        'issues_actionable': actionable,
        'issues_total': len(issues),
        'observations_review': observations,
        'observations_total': len(observations),
        'performance': _compact_performance(perf),
        'live_performance': _compact_live(live),
        'full_snapshots': {
            'audit': '.ai/runtime/atlas_doctor/latest_audit.json',
            'performance': '.ai/runtime/atlas_doctor/latest_perf.json',
            'live_performance': '.ai/runtime/atlas_doctor/latest_live_perf.json',
        },
        'instructions_for_agent': [
            'Traiter CRITICAL/HIGH confirmes avant les suspects.',
            'Ne jamais supprimer un module marque suspect sans verifier wiring dynamique et consommateurs reels.',
            'Comparer les performances uniquement sur la meme machine/environnement.',
            'Une hausse >=15% est un signal de regression a verifier, pas une preuve absolue entre environnements differents.',
            'Consulter les snapshots complets seulement si le rapport compact ne suffit pas.',
            'Apres correction, relancer audit puis verify/compare.',
        ],
    }
    write_json(root, 'latest_report', payload)
    return payload
