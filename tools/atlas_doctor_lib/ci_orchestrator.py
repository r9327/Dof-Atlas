from __future__ import annotations

"""Doctor-first GitHub CI selection, without Qt, installs, tests or dispatch APIs.

The existing Phase adaptive gate owns application certification eligibility.
Known CI-only changes run tooling contracts without certifying the application.
This module composes those decisions with UI impact and specialist contracts.
A selected job must actually finish successfully; this plan grants no PASS.
"""
import json
from fnmatch import fnmatchcase
from pathlib import Path
import subprocess
import sys

from tools.atlas_integrity import classify_risk
from tools.ci_scope_gate import changed_paths
from tools.phase_adaptive_gate import critical_changed
from tools.atlas_doctor_lib.doctor_ui_ci import classify_ui
from tools.atlas_doctor_lib.ci_tooling_scope import eligible as tooling_eligible, QT_DETECTOR_PATHS
from tools.atlas_doctor_lib.high_smart_scope import eligible as high_smart_eligible

REGISTRY = Path(__file__).with_name('ci_routes.json')


def select_workflows(paths: list[str], *, event: str, phase_route: dict,
                     ui_plan: dict, deleted=(), tooling_scope=None, domain_plan=None) -> dict:
    if event not in {'pull_request', 'push', 'workflow_dispatch'}:
        raise ValueError('Unsupported Doctor CI event')
    registry = json.loads(REGISTRY.read_text(encoding='utf-8'))
    docs_only = bool(paths) and not deleted and all(
        (p.startswith('docs/') and p.endswith('.md')) or p in {'README.md', '.ai/context_index.json'} for p in paths
    )
    docs_only = docs_only and not critical_changed(paths)
    tooling_only = (tooling_eligible(paths, deleted=deleted) if tooling_scope is None else tooling_scope)
    tooling_only = (tooling_only and phase_route.get('route') in {'FULL', 'SCOPED'}
                    and ui_plan.get('status') != 'REVIEW_REQUIRED' and event != 'workflow_dispatch')
    if any(path in QT_DETECTOR_PATHS for path in paths):
        # A detector can be tooling-only only when both the real Windows
        # Success oracle AND its existing validator are scheduled. No scoped
        # certification is permitted if the UI planner cannot prove this.
        required = {'validator-smoke', 'achievement-detail'}
        tooling_only = (tooling_only and ui_plan.get('status') == 'UI_REQUIRED'
                        and required <= set(ui_plan.get('selected_scenarios', ())))
    risk = classify_risk(paths)["risk"]
    # The independently reviewed HIGH canary is the sole exception to the
    # risk-level FULL trigger, and only after canonical Phase verifies SCOPED.
    # The Phase router already checks test closure; this cannot select SCOPED.
    high_smart = (event == 'pull_request' and risk == "HIGH"
                  and high_smart_eligible(Path(__file__).resolve().parents[2], paths, deleted=deleted)
                  and phase_route.get('route') == 'SCOPED')
    full = event == 'workflow_dispatch' or (not docs_only and not tooling_only and (
        bool(deleted) or bool(critical_changed(paths))
        or (risk in {"HIGH", "CRITICAL"} and not high_smart)
        or phase_route.get('route') != 'SCOPED'
        or ui_plan.get('status') == 'REVIEW_REQUIRED'))
    phase = (not docs_only and not tooling_only) or event == 'workflow_dispatch'
    # FULL is the canonical suite, not an instruction to replay every unrelated
    # specialist. Unknown scope, removals and policy changes retain the broad fallback.
    # An independently covered Qt detector change still requires the canonical
    # FULL when mixed with product code. It does not, on its own, justify
    # running every unrelated provider, JSON and packaging specialist.
    # Unmapped UI impact, unknown policy or non-detector trust changes retain
    # the exhaustive fallback. Never reduce the FULL requirement itself.
    critical = critical_changed(paths)
    covered_qt_detector = (
        bool(critical) and set(critical) <= QT_DETECTOR_PATHS
        and ui_plan.get('status') == 'UI_REQUIRED'
        and {'validator-smoke', 'achievement-detail', 'guides-success', 'guides-lanyel'}
            <= set(ui_plan.get('selected_scenarios', ()))
    )
    specialist_fallback = full and (event == 'workflow_dispatch'
        or (bool(critical) and not covered_qt_detector) or bool(deleted)
        or phase_route.get('route') not in {'SCOPED', 'FULL'}
        or ui_plan.get('status') == 'REVIEW_REQUIRED')
    # Domain planning cannot be a free-standing PR assertion: fail closed if
    # the supplied route disagrees with the closed-world path classification.
    modular_ready = (event == 'pull_request'
        and isinstance(domain_plan, dict)
        and domain_plan.get('status') == 'READY_TO_EXECUTE'
        and not deleted
        and not domain_plan.get('unknown_paths')
        and not domain_plan.get('deleted_paths')
        and bool(domain_plan.get('domains'))
        and set(domain_plan.get('changed_paths', ())) == set(paths))
    if modular_ready:
        from tools.ci_domain_certification import owners_for
        for path in paths:
            owners = owners_for(path)
            if not owners.issubset(set(domain_plan['domains'])):
                modular_ready = False
                break
    if modular_ready:
        # The domain runner checks all closed-world consumers and baseline CI
        # tests. Replaying unrelated providers/package jobs is not equivalent
        # to stronger certification, just duplicated runner work.
        specialist_fallback = False
    decisions = {}
    for name, patterns in registry.items():
        hits = [p for p in paths if any(fnmatchcase(p, pat) for pat in patterns)]
        selected = (bool(hits) and not docs_only) or specialist_fallback
        reasons = ['Changed paths: ' + ', '.join(hits)] if hits else []
        if specialist_fallback:
            reasons.append('FULL_REQUIRED: preserve independent specialist validation')
        if name in {'ai-context-ci', 'signature-report'}:
            selected, reasons = True, ['Repository metadata checked on every candidate']
        elif name == 'app-ci':
            selected = event == 'push' and (bool(hits) or full)
            reasons = ['Main fast application checks; Phase owns the only automatic FULL']
        elif name == 'doctor-certification':
            user_domains = {'quests', 'guides', 'ui', 'startup', 'identity', 'data'}
            selected = event == 'pull_request' and phase and (
                not modular_ready or bool(user_domains & set(domain_plan['domains'])))
            reasons = ['Independent user journeys for selected application consumers']
            if modular_ready and not selected:
                reasons = ['CI contracts executed in exact-SHA domain runner; no user journey owner']
        elif name == 'doctor-ui':
            selected = bool(ui_plan.get('selected_scenarios')) or ui_plan.get('status') == 'REVIEW_REQUIRED'
            reasons = ['Canonical UI impact: ' + ui_plan.get('status', 'UNKNOWN')]
            if ui_plan.get('uncertainty'):
                reasons += ui_plan['uncertainty']
        elif name == 'atlas-windows-distribution':
            # A PR plan may validate packaging but cannot publish a release.
            selected = event == 'pull_request' and (bool(hits) or specialist_fallback)
            reasons = ['PR packaging impact; publication retains independent host attestation']
        decisions[name] = {'selected': selected, 'reasons': reasons or ['No changed consumer']}
    return {
        'phase': phase, 'full': full, 'docs_only': docs_only, 'tooling_only': tooling_only,
        'specialist_fallback': specialist_fallback,
        'workflows': decisions,
        'outputs': {'phase': phase, 'full': full, 'tooling_only': tooling_only, **{
            name.replace('-', '_'): row['selected'] for name, row in decisions.items()
        }},
    }


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(['git', *args], cwd=root, text=True,
                                   encoding='utf-8', timeout=40).strip()


def plan_ci(root: Path, *, base_ref: str, candidate_sha: str, event: str,
            output: Path) -> dict:
    if _git(root, 'rev-parse', 'HEAD') != candidate_sha:
        raise ValueError('Doctor candidate differs from checked-out HEAD')
    if _git(root, 'status', '--porcelain', '--untracked-files=no'):
        raise ValueError('Doctor requires an unmodified candidate')
    base = _git(root, 'rev-parse', '--verify', base_ref + '^{commit}')
    # An absent base/initial push must block rather than turn into an empty diff.
    _git(root, 'merge-base', base, candidate_sha)
    paths, deleted = changed_paths(root, base)
    route_file = output.with_name('phase_route.json')
    route_file.unlink(missing_ok=True)
    command = [sys.executable, '-m', 'tools.phase_adaptive_gate', 'decide',
               '--base-ref', base, '--expected-sha', candidate_sha,
               '--output', str(route_file)]
    if event == 'workflow_dispatch':
        command.append('--force-full')
    try:
        finished = subprocess.run(command, cwd=root, capture_output=True,
                                  text=True, timeout=200, check=False)
        route = json.loads(route_file.read_text(encoding='utf-8')) if finished.returncode == 0 else {}
        if route.get('candidate_sha') != candidate_sha or route.get('base_sha') != base:
            route = {}
    except (OSError, ValueError, subprocess.SubprocessError):
        route = {}  # Missing/unreadable canonical decision mandates a real FULL.
    ui = classify_ui(root, paths, candidate_sha=candidate_sha, base_sha=base, deleted=deleted)
    from tools.ci_domain_certification import plan_domains
    # Legacy Doctor changed_paths lists live paths only while deleted carries
    # removed paths separately. The independent domain router receives the
    # *complete* exact diff so removals stay blocking rather than raising
    # before Doctor can record its fail-closed plan.
    domain_plan = plan_domains(base_sha=base, candidate_sha=candidate_sha,
                               paths=sorted(set(paths) | set(deleted)), deleted=deleted)
    result = select_workflows(paths, event=event, phase_route=route, ui_plan=ui, deleted=deleted,
        tooling_scope=tooling_eligible(paths, deleted=deleted, root=root, base_sha=base),
        domain_plan=domain_plan)
    execution_mode = ('PR_DOMAIN_MODULES' if event == 'pull_request' and result['phase']
                      else 'RELEASE_FULL' if event in {'push', 'workflow_dispatch'}
                      else 'FOCUSED_CONTRACTS')
    return {
        'schema_version': 1, 'status': 'PLANNED', 'candidate_sha': candidate_sha,
        'base_sha': base, 'event': event, 'risk': classify_risk(paths)['risk'],
        'changed_paths': paths, 'deleted_paths': deleted,
        'phase_route': route, 'ui_plan': ui, 'execution_mode': execution_mode,
        'domain_plan': domain_plan, **result,
        'tests_executed': False, 'phase_certified': False, 'merge_authorized': False,
    }


def command_ci(root: Path, args) -> dict:
    report = plan_ci(root, base_ref=args.base_ref, candidate_sha=args.expected_sha,
                     event=args.event, output=args.output)
    report['required_jobs'] = ['certify'] if report['phase'] else ['focused-validation']
    report['required_jobs'] += [name.replace('-', '_') for name, row in report['workflows'].items() if row['selected']]
    if args.event == 'pull_request':
        report['required_jobs'].append('pr-fast-validation')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    if args.github_output:
        with args.github_output.open('a', encoding='utf-8') as stream:
            stream.write('required_jobs=' + json.dumps(report['required_jobs']) + '\n')
            for key, selected in report['outputs'].items():
                stream.write(f'{key}={str(selected).lower()}\n')
    if not args.json:
        print(f"Doctor CI: {report['risk']} — FULL={report['full']}")
    return report
