from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

from .core import Issue, git_state, run_git, severity_counts, tracked_files, utc_now

POLICY_RELATIVE = Path('tools/ponytail_policy.json')


def _load_policy(root: Path) -> tuple[dict[str, Any] | None, str | None]:
    path = root / POLICY_RELATIVE
    if not path.is_file():
        return None, f'Policy missing: {POLICY_RELATIVE.as_posix()}'
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f'Policy unreadable: {exc}'
    if not isinstance(payload, dict) or payload.get('schema_version') != 1:
        return None, 'Unsupported Ponytail policy schema.'
    doctor = payload.get('doctor')
    if not isinstance(doctor, dict) or not isinstance(doctor.get('checks'), dict):
        return None, 'Ponytail policy has no valid doctor.checks mapping.'
    if not isinstance(payload.get('principles'), list):
        return None, 'Ponytail policy has no valid principles list.'
    return payload, None


def _resolve_base_ref(root: Path, requested: str | None) -> str:
    if requested:
        resolved = run_git(root, 'rev-parse', '--verify', f'{requested}^{{commit}}', check=False)
        if not resolved:
            raise ValueError(f'Unknown Ponytail base ref: {requested}')
        return requested
    head = run_git(root, 'rev-parse', 'HEAD')
    origin_main = run_git(root, 'rev-parse', '--verify', 'origin/main^{commit}', check=False)
    if origin_main and origin_main != head:
        merge_base = run_git(root, 'merge-base', 'origin/main', 'HEAD', check=False)
        if merge_base:
            return merge_base
    previous = run_git(root, 'rev-parse', '--verify', 'HEAD~1^{commit}', check=False)
    return previous or 'HEAD'


def _diff_rows(root: Path, base_ref: str) -> list[dict[str, Any]]:
    status_output = run_git(root, 'diff', '--name-status', base_ref, '--', check=False)
    numstat_output = run_git(root, 'diff', '--numstat', base_ref, '--', check=False)
    stats: dict[str, tuple[int, int]] = {}
    for line in numstat_output.splitlines():
        parts = line.split('\t')
        if len(parts) < 3:
            continue
        added_raw, deleted_raw, path = parts[0], parts[1], parts[-1]
        added = int(added_raw) if added_raw.isdigit() else 0
        deleted = int(deleted_raw) if deleted_raw.isdigit() else 0
        stats[path] = (added, deleted)

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in status_output.splitlines():
        parts = line.split('\t')
        if len(parts) < 2:
            continue
        status = parts[0]
        path = parts[-1]
        added, deleted = stats.get(path, (0, 0))
        rows.append({'status': status, 'path': path, 'added': added, 'deleted': deleted})
        seen.add(path)

    untracked = run_git(root, 'ls-files', '--others', '--exclude-standard', '-z', check=False)
    for path in sorted(item for item in untracked.split('\0') if item and item not in seen):
        full = root / path
        try:
            added = len(full.read_text(encoding='utf-8').splitlines()) if full.is_file() else 0
        except (OSError, UnicodeError):
            added = 0
        rows.append({'status': 'A?', 'path': path, 'added': added, 'deleted': 0})
    return rows


def _rule(policy: dict[str, Any], rule_id: str) -> dict[str, Any]:
    return ((policy.get('doctor') or {}).get('checks') or {}).get(rule_id) or {}


def _finding(
    policy: dict[str, Any],
    rule_id: str,
    *,
    path: str,
    evidence: str,
    line: int | None = None,
    confidence: str = 'suspect',
) -> dict[str, Any]:
    rule = _rule(policy, rule_id)
    issue = Issue(
        rule=f'ponytail_{rule_id}',
        category='ponytail',
        severity=str(rule.get('severity', 'INFO')).upper(),
        confidence=confidence,
        path=path,
        line=line,
        title=str(rule.get('title', rule_id)),
        evidence=evidence,
        recommendation=str(rule.get('recommendation', 'Review the change against the shared Ponytail policy.')),
    )
    return issue.to_dict()


def _dependency_findings(policy: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    manifests = set((policy.get('doctor') or {}).get('dependency_manifests') or [])
    findings: list[dict[str, Any]] = []
    for row in rows:
        path = str(row['path'])
        if Path(path).name not in manifests or not row.get('added'):
            continue
        findings.append(_finding(
            policy,
            'dependency_manifest_change',
            path=path,
            confidence='confirmed',
            evidence=f"Dependency manifest diff: +{row.get('added', 0)}/-{row.get('deleted', 0)} lines.",
        ))
    return findings


def _classes(source: str) -> dict[str, int]:
    if not source.strip():
        return {}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    return {
        node.name: int(getattr(node, 'lineno', 0) or 0)
        for node in getattr(tree, 'body', [])
        if isinstance(node, ast.ClassDef)
    }


def _baseline_text(root: Path, base_ref: str, path: str) -> str:
    return run_git(root, 'show', f'{base_ref}:{path}', check=False)


def _python_sources(root: Path) -> dict[str, str]:
    paths = tracked_files(root)
    untracked = run_git(root, 'ls-files', '--others', '--exclude-standard', '-z', check=False)
    paths.extend(item for item in untracked.split('\0') if item)
    sources: dict[str, str] = {}
    for path in dict.fromkeys(paths):
        if not path.endswith('.py'):
            continue
        try:
            sources[path] = (root / path).read_text(encoding='utf-8-sig')
        except (OSError, UnicodeError):
            continue
    return sources


def _new_abstraction_findings(
    root: Path,
    policy: dict[str, Any],
    base_ref: str,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    suffixes = tuple((policy.get('doctor') or {}).get('abstraction_suffixes') or [])
    if not suffixes:
        return []
    sources = _python_sources(root)
    findings: list[dict[str, Any]] = []
    for row in rows:
        path = str(row['path'])
        if not path.endswith('.py') or str(row.get('status', '')).startswith('D'):
            continue
        current = sources.get(path, '')
        current_classes = _classes(current)
        baseline_classes = _classes(_baseline_text(root, base_ref, path))
        for name, line in current_classes.items():
            if name in baseline_classes or not name.endswith(suffixes):
                continue
            pattern = re.compile(rf'\b{re.escape(name)}\b')
            occurrences = sum(len(pattern.findall(source)) for source in sources.values())
            references = max(0, occurrences - 1)
            if references > 1:
                continue
            findings.append(_finding(
                policy,
                'low_fanin_abstraction',
                path=path,
                line=line or None,
                evidence=f'New class {name} has {references} static reference(s) outside its definition.',
            ))
    return findings


def _parallel_path_findings(policy: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    markers = set((policy.get('doctor') or {}).get('parallel_path_markers') or [])
    findings: list[dict[str, Any]] = []
    for row in rows:
        status = str(row.get('status', ''))
        if not status.startswith('A'):
            continue
        path = str(row['path'])
        tokens = set(re.split(r'[^a-z0-9]+', Path(path).stem.casefold()))
        matched = sorted(tokens & markers)
        if not matched:
            continue
        findings.append(_finding(
            policy,
            'parallel_path_marker',
            path=path,
            evidence=f"New path contains review marker(s): {', '.join(matched)}.",
        ))
    return findings


def _broad_diff_findings(policy: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    thresholds = (policy.get('doctor') or {}).get('review_thresholds') or {}
    changed_limit = int(thresholds.get('changed_files', 24))
    added_limit = int(thresholds.get('added_lines', 1000))
    changed_files = len(rows)
    added_lines = sum(int(row.get('added') or 0) for row in rows)
    if changed_files < changed_limit and added_lines < added_limit:
        return []
    return [_finding(
        policy,
        'broad_diff',
        path='.',
        confidence='confirmed',
        evidence=f'Diff touches {changed_files} file(s) with {added_lines} added line(s); thresholds are {changed_limit} files / {added_limit} added lines.',
    )]


def evaluate_ponytail(
    root: Path,
    *,
    base_ref: str | None = None,
    required: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    policy, error = _load_policy(root)
    if policy is None:
        return {
            'schema_version': 1,
            'kind': 'ponytail_policy',
            'status': 'FAIL' if required else 'UNAVAILABLE',
            'generated_at': utc_now(),
            'policy_path': POLICY_RELATIVE.as_posix(),
            'reason': error,
            'findings': [],
        }

    resolved_base = _resolve_base_ref(root, base_ref)
    rows = _diff_rows(root, resolved_base)
    findings: list[dict[str, Any]] = []
    findings.extend(_dependency_findings(policy, rows))
    findings.extend(_new_abstraction_findings(root, policy, resolved_base, rows))
    findings.extend(_parallel_path_findings(policy, rows))
    findings.extend(_broad_diff_findings(policy, rows))
    findings.sort(key=lambda item: (item['path'], item.get('line') or 0, item['rule']))
    counts = severity_counts(findings)

    try:
        from .architecture import graph_status
        graph = graph_status(root)
        graph_evidence = {
            'status': graph.get('status'),
            'reason': graph.get('reason'),
            'graph': graph.get('graph'),
        }
    except Exception as exc:  # graph evidence is optional and must not break policy evaluation
        graph_evidence = {'status': 'UNAVAILABLE', 'reason': str(exc)}

    status = 'REVIEW' if findings else 'PASS'
    return {
        'schema_version': 1,
        'kind': 'ponytail_policy',
        'policy_id': policy.get('policy_id'),
        'policy_path': POLICY_RELATIVE.as_posix(),
        'mode': policy.get('mode', 'advisory'),
        'status': status,
        'generated_at': utc_now(),
        'git': git_state(root),
        'base_ref': resolved_base,
        'graph_evidence': graph_evidence,
        'summary': {
            'findings_total': len(findings),
            'severity': counts,
            'changed_files': len(rows),
            'added_lines': sum(int(row.get('added') or 0) for row in rows),
            'deleted_lines': sum(int(row.get('deleted') or 0) for row in rows),
        },
        'manual_principles': policy.get('principles', []),
        'findings': findings,
        'interpretation': 'REVIEW is advisory evidence, not proof that complexity is unnecessary. Atlas guardrails take precedence.',
    }
