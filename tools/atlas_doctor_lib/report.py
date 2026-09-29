from __future__ import annotations

from typing import Any

from .core import load_json, utc_now, write_json


def compare_runs(current: dict[str, Any] | None, previous: dict[str, Any] | None) -> dict[str, Any]:
    if not current or not previous:
        return {'status': 'UNAVAILABLE', 'reason': 'Deux snapshots sont necessaires.'}
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


def build_ai_report(root) -> dict[str, Any]:
    audit = load_json(root, 'latest_audit')
    perf = load_json(root, 'latest_perf')
    previous_audit = load_json(root, 'previous_audit')
    comparison = compare_runs(audit, previous_audit)
    payload = {
        'schema_version': 1,
        'kind': 'ai_report',
        'generated_at': utc_now(),
        'audit_summary': (audit or {}).get('summary'),
        'git': (audit or perf or {}).get('git'),
        'comparison': comparison,
        'issues': (audit or {}).get('issues', []),
        'performance': perf,
        'instructions_for_agent': [
            'Traiter CRITICAL/HIGH confirmes avant les suspects.',
            'Ne jamais supprimer un module marque suspect sans verifier wiring dynamique et consommateurs reels.',
            'Comparer les performances uniquement sur la meme machine/environnement.',
            'Apres correction, relancer audit puis verify/compare.',
        ],
    }
    write_json(root, 'latest_report', payload)
    return payload
