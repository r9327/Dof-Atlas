from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .core import (
    git_state,
    load_json,
    milliseconds,
    runtime_dir,
    tracked_files,
    utc_now,
    write_json,
)

DATA_EXTENSIONS = {'.json', '.jsonl', '.csv', '.txt', '.yaml', '.yml'}
DATA_PREFIXES = ('data/', 'config/', 'local_dofus_data/')
DEFAULT_RUNTIME_SAMPLES = 3
RUNTIME_ARTIFACT = Path('artifacts/doctor/perf/runtime.json')


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
    return round(ordered[index], 3)


def profile_data_files(root: Path, *, max_file_mb: float = 64.0) -> dict[str, Any]:
    started = time.perf_counter()
    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    limit = int(max_file_mb * 1024 * 1024)
    for relative in tracked_files(root):
        if not relative.startswith(DATA_PREFIXES):
            continue
        path = root / relative
        if path.suffix.lower() not in DATA_EXTENSIONS or not path.is_file():
            continue
        try:
            size = path.stat().st_size
        except OSError as exc:
            skipped.append({'path': relative, 'reason': str(exc)})
            continue
        if size > limit:
            skipped.append({'path': relative, 'reason': f'>{max_file_mb:.0f} MiB', 'size_bytes': size})
            continue

        read_started = time.perf_counter()
        try:
            raw = path.read_bytes()
        except OSError as exc:
            skipped.append({'path': relative, 'reason': str(exc)})
            continue
        read_ms = milliseconds(read_started)
        parse_ms = 0.0
        parse_error = ''
        if path.suffix.lower() == '.json':
            parse_started = time.perf_counter()
            try:
                json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                parse_error = str(exc)
            parse_ms = milliseconds(parse_started)
        total_ms = round(read_ms + parse_ms, 3)
        rows.append({
            'path': relative,
            'size_bytes': size,
            'read_ms': read_ms,
            'json_parse_ms': parse_ms,
            'total_ms': total_ms,
            'parse_error': parse_error,
            'throughput_mb_s': round((size / 1024 / 1024) / max(read_ms / 1000.0, 1e-9), 2),
        })

    rows.sort(key=lambda item: item['total_ms'], reverse=True)
    totals = [float(item['total_ms']) for item in rows]
    return {
        'generated_at': utc_now(),
        'duration_ms': milliseconds(started),
        'files_measured': len(rows),
        'files_skipped': len(skipped),
        'total_read_ms': round(sum(float(item['read_ms']) for item in rows), 3),
        'total_json_parse_ms': round(sum(float(item['json_parse_ms']) for item in rows), 3),
        'p50_file_total_ms': _percentile(totals, 0.50),
        'p95_file_total_ms': _percentile(totals, 0.95),
        'slowest': rows[:50],
        'skipped': skipped[:100],
    }


def _previous_runtime_benchmark(root: Path) -> dict[str, Any] | None:
    previous = load_json(root, 'latest_perf') or {}
    benchmark = ((previous.get('runtime') or {}).get('benchmark') or {})
    return benchmark if isinstance(benchmark, dict) and benchmark else None


def _runtime_environment(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    current_pythonpath = env.get('PYTHONPATH', '')
    env['PYTHONPATH'] = str(root) + (
        os.pathsep + current_pythonpath if current_pythonpath else ''
    )
    env.setdefault('QT_QPA_PLATFORM', 'offscreen')
    env.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--disable-gpu --no-sandbox')
    env.setdefault('QTWEBENGINE_DISABLE_SANDBOX', '1')
    env.setdefault('PYTHONUNBUFFERED', '1')
    env.setdefault('PYTHONUTF8', '1')
    return env


def run_runtime_benchmark(
    root: Path,
    *,
    timeout: int = 180,
    samples: int = DEFAULT_RUNTIME_SAMPLES,
) -> dict[str, Any]:
    """Run canonical UI/RAM samples in isolated processes and aggregate medians."""

    from .runtime_benchmark import aggregate_samples, attach_baseline_comparison

    sample_count = max(1, int(samples))
    sample_dir = runtime_dir(root) / 'perf_samples'
    sample_dir.mkdir(parents=True, exist_ok=True)
    for stale in sample_dir.glob('sample-*.json'):
        stale.unlink(missing_ok=True)

    env = _runtime_environment(root)
    collected: list[dict[str, Any]] = []
    executions: list[dict[str, Any]] = []
    started = time.perf_counter()
    worker = (
        'import sys; from pathlib import Path; '
        'from tools.atlas_doctor_lib.runtime_benchmark import write_sample; '
        'write_sample(Path(sys.argv[1]), Path(sys.argv[2]))'
    )

    for index in range(1, sample_count + 1):
        output_path = sample_dir / f'sample-{index}.json'
        command = [
            sys.executable,
            '-c',
            worker,
            str(root),
            str(output_path),
        ]
        sample_started = time.perf_counter()
        try:
            completed = subprocess.run(
                command,
                cwd=root,
                env=env,
                text=True,
                encoding='utf-8',
                errors='replace',
                capture_output=True,
                check=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            return {
                'status': 'FAIL',
                'reason': f'Runtime sample {index}/{sample_count} timed out after {timeout}s.',
                'duration_ms': milliseconds(started),
                'sample_count': len(collected),
                'command': command,
                'stdout_tail': (exc.stdout or '').splitlines()[-20:] if isinstance(exc.stdout, str) else [],
                'stderr_tail': (exc.stderr or '').splitlines()[-40:] if isinstance(exc.stderr, str) else [],
            }

        execution = {
            'sample': index,
            'returncode': completed.returncode,
            'duration_ms': milliseconds(sample_started),
            'stdout_tail': completed.stdout.splitlines()[-10:],
            'stderr_tail': completed.stderr.splitlines()[-20:],
        }
        executions.append(execution)
        if completed.returncode != 0 or not output_path.is_file():
            return {
                'status': 'FAIL',
                'reason': f'Runtime sample {index}/{sample_count} failed.',
                'duration_ms': milliseconds(started),
                'sample_count': len(collected),
                'executions': executions,
                'command': command,
            }
        try:
            sample_payload = json.loads(output_path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            return {
                'status': 'FAIL',
                'reason': f'Runtime sample {index}/{sample_count} produced invalid JSON: {exc}',
                'duration_ms': milliseconds(started),
                'sample_count': len(collected),
                'executions': executions,
            }
        collected.append(sample_payload)

    benchmark = aggregate_samples(collected)
    benchmark = attach_baseline_comparison(
        benchmark,
        _previous_runtime_benchmark(root),
    )
    artifact = root / RUNTIME_ARTIFACT
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        json.dumps(benchmark, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    total_duration_ms = milliseconds(started)
    return {
        'status': 'PASS',
        'duration_ms': total_duration_ms,
        'clean_duration_ms': total_duration_ms,
        'trace_duration_ms': 0.0,
        'sample_count': sample_count,
        'executions': executions,
        'benchmark': benchmark,
        'artifact': str(RUNTIME_ARTIFACT).replace('\\', '/'),
        'io_trace_status': 'NOT_RUN',
        'io_trace_reason': 'Runtime performance uses isolated clean samples; use Doctor live for I/O tracing.',
        'io_trace': None,
    }


_COMPARABLE_SUCCESS_METRICS = (
    "achievements_open_ms", "achievements_open_max_ui_block_ms",
    "rss_after_achievements_mb",
)
_PAIRED_INPUT_LOCKS = (
    "requirements-pyside.txt",
    "scripts/windows/quest_assets_lock.json",
    "scripts/windows/craft_assets_lock.json",
)


def _on_demand_baseline_sha(root: Path) -> str | None:
    """Only the explicit, existing remote Windows benchmark requests a pair."""
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("MODE") != "bench-runtime":
        return None
    base, head = os.environ.get("BASE_SHA", ""), os.environ.get("HEAD_SHA", "")
    if (not re.fullmatch(r"[0-9a-f]{40}", base)
            or not re.fullmatch(r"[0-9a-f]{40}", head)
            or base == head or git_state(root)["head"] != head):
        return None
    return base


def _paired_success_comparison(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    from .runtime_benchmark import aggregate_samples, compare_to_baseline

    # The old detail probe did not await actual asynchronous detail rendering.
    # Compare only the unchanged first-view timing and its associated costs.
    # Never claim a detail speedup from different measurement semantics.
    before = aggregate_samples(baseline["samples"])
    after = aggregate_samples(current["samples"])
    def comparable(report):
        return {
            "environment": report["environment"],
            "medians": {key: report["medians"][key] for key in _COMPARABLE_SUCCESS_METRICS
                        if key in report["medians"]},
        }
    comparison = compare_to_baseline(comparable(after), comparable(before))
    if len(comparison.get("metrics", [])) != len(_COMPARABLE_SUCCESS_METRICS):
        comparison["status"] = "UNAVAILABLE"
        comparison["reason"] = "Missing comparable Success first-view metrics"
    return {
        "scope": "SUCCESS_FIRST_VIEW_ONLY",
        "run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        "same_runner": True,
        "baseline_sha": before["environment"]["git_head"],
        "candidate_sha": after["environment"]["git_head"],
        "baseline_sample_count": before["sample_count"],
        "candidate_sample_count": after["sample_count"],
        "baseline_distributions": before["distributions"],
        "candidate_distributions": after["distributions"],
        "comparison": comparison,
    }


def _baseline_failure_detail(exc: BaseException) -> str:
    detail = getattr(exc, "stderr", None)
    if isinstance(detail, bytes):
        detail = detail.decode("utf-8", errors="replace")
    if isinstance(detail, str) and detail.strip():
        return f"{exc}: {detail.strip()[-2000:]}"
    return str(exc)


def _remove_baseline_worktree(root: Path, base_root: Path, env: dict[str, str]) -> None:
    """Allow transient Windows file locks to settle, without certifying a leak."""
    failure: BaseException | None = None
    for delay in (0.0, 0.25, 1.0, 2.0, 4.0):
        if delay:
            time.sleep(delay)
        try:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(base_root)],
                cwd=root, env=env, check=True, capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=120,
            )
            return
        except (OSError, subprocess.SubprocessError) as exc:
            failure = exc
    assert failure is not None
    raise ValueError(
        f"Baseline worktree cleanup failed: {_baseline_failure_detail(failure)}"
    ) from failure


def _same_runner_baseline(root: Path, base_sha: str) -> dict[str, Any]:
    """Use a disposable exact-SHA checkout and the same pinned inputs/Qt."""
    env = _runtime_environment(root)
    env["GIT_LFS_SKIP_SMUDGE"] = "1"
    # The base subprocess must not import candidate modules via PYTHONPATH.
    env.pop("PYTHONPATH", None)
    env.pop("DOFUS_ATLAS_USER_ROOT", None)
    # Git owns worktree removal. Python's final best-effort temp cleanup must
    # not replace the actual baseline/cleanup error with an unrelated WinError.
    with tempfile.TemporaryDirectory(prefix="atlas-perf-", ignore_cleanup_errors=True) as temp:
        base_root = Path(temp) / "base"
        subprocess.run(["git", "worktree", "add", "--detach", str(base_root), base_sha],
                       cwd=root, env=env, check=True, capture_output=True, timeout=180)
        try:
            for relative in _PAIRED_INPUT_LOCKS:
                if (root / relative).read_bytes() != (base_root / relative).read_bytes():
                    raise ValueError(f"Paired benchmark input lock differs: {relative}")
            # Reuse only the already materialized, pinned files. No unverified
            # alternative downloads; the baseline's canonical commands verify
            # the exact source inventory and rebuild its own Craft seed.
            raw = Path("data/cache/dofus_maps/raw/doduda_cli")
            names = set()
            for lock in _PAIRED_INPUT_LOCKS[1:]:
                names.update(json.loads((root / lock).read_text(encoding="utf-8"))["assets"])
            for name in sorted(names):
                target = base_root / raw / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(root / raw / name, target)
            env["PYTHONPATH"] = str(base_root)
            def run(*args: str, timeout: int = 120):
                return subprocess.run(
                    [sys.executable, *args], cwd=base_root, env=env,
                    check=True, capture_output=True, text=True, encoding="utf-8",
                    errors="replace", timeout=timeout,
                )
            run("-m", "scripts.windows.quest_assets")
            run("-m", "scripts.windows.craft_seed")
            run("-c", "from pathlib import Path; from shutil import copy2; "
                "from scripts.windows.craft_seed import validate_seed; "
                "from local_dofus_data.config import DEFAULT_CONFIG; "
                "from app.craft_preload import build_compact_craft_preload; "
                "from app.quest_catalog import QuestCatalog; "
                "seed=Path('data/bootstrap/craft_seed.sqlite'); validate_seed(seed); "
                "target=DEFAULT_CONFIG.sqlite_path; target.parent.mkdir(parents=True, exist_ok=True); "
                "copy2(seed,target); validate_seed(target); craft=build_compact_craft_preload(); "
                "assert craft.get('_prepared') is True and not craft.get('errors'); "
                "assert len(QuestCatalog.load().quests) >= 1900")
            output = run("-c", "import json; from pathlib import Path; "
                         "from tools.atlas_doctor_lib.perf import run_runtime_benchmark; "
                         "print(json.dumps(run_runtime_benchmark(Path.cwd())))", timeout=420)
            result = json.loads(output.stdout.strip().splitlines()[-1])
            benchmark = result.get("benchmark") or {}
            if result.get("status") != "PASS" or benchmark.get("environment", {}).get("git_head") != base_sha:
                raise ValueError("Baseline runtime failed or returned a different SHA")
        except (OSError, ValueError, subprocess.SubprocessError) as original:
            try:
                _remove_baseline_worktree(root, base_root, env)
            except (OSError, ValueError, subprocess.SubprocessError) as cleanup:
                raise ValueError(
                    f"Baseline failed: {_baseline_failure_detail(original)}; "
                    f"cleanup: {_baseline_failure_detail(cleanup)}"
                ) from original
            raise
        else:
            _remove_baseline_worktree(root, base_root, env)
            return benchmark


def _local_quest_coverage(root: Path) -> dict[str, Any]:
    """The full local enrichment is too large for API reads; use its canonical audit."""
    with tempfile.TemporaryDirectory(prefix="atlas-quest-coverage-") as temp:
        output = Path(temp) / "coverage.json"
        subprocess.run(
            [sys.executable, "-m", "app.modules.encyclopedia.tools.audit_quests_guides_semantic",
             "--local-coverage-only", "--json-output", str(output)],
            cwd=root, env=_runtime_environment(root), check=True, capture_output=True, timeout=90,
        )
        return json.loads(output.read_text(encoding="utf-8"))


def collect_quest_coverage_evidence(root: Path, expected_sha: str) -> dict[str, Any]:
    """Run the canonical local audit separately from any timed UI/RAM sample."""
    try:
        if git_state(root)["head"] != expected_sha:
            raise ValueError("Quest coverage checkout differs from measured candidate")
        coverage = _local_quest_coverage(root)
        if git_state(root)["head"] != expected_sha:
            raise ValueError("Quest coverage checkout changed during audit")
        native = coverage.get("native_start_coverage")
        count = coverage.get("quests_considered")
        if (type(count) is not int or count <= 0 or not isinstance(native, dict)
                or native.get("quests_considered") != count):
            raise ValueError("Quest coverage inventory missing or inconsistent")
        return {"status": "MEASURED", "git_head": expected_sha, "coverage": coverage}
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return {"status": "UNAVAILABLE", "git_head": expected_sha,
                "reason": _baseline_failure_detail(exc)}


def run_performance(root: Path, *, include_runtime: bool = True, save: bool = True) -> dict[str, Any]:
    started = time.perf_counter()
    payload: dict[str, Any] = {
        'schema_version': 2,
        'kind': 'performance',
        'generated_at': utc_now(),
        'git': git_state(root),
        'file_profile': profile_data_files(root),
    }
    if include_runtime:
        base_sha = _on_demand_baseline_sha(root)
        baseline = None
        if base_sha:
            try:
                baseline = _same_runner_baseline(root, base_sha)
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                payload["same_runner_success"] = {
                    "status": "UNAVAILABLE", "baseline_sha": base_sha,
                    "reason": _baseline_failure_detail(exc),
                }
        payload['runtime'] = run_runtime_benchmark(root)
        if base_sha:
            if baseline and payload["runtime"].get("status") == "PASS":
                payload["same_runner_success"] = _paired_success_comparison(
                    payload["runtime"]["benchmark"], baseline,
                )
            elif baseline:
                payload["same_runner_success"] = {"status": "UNAVAILABLE", "reason": "Candidate runtime failed"}
            # Coverage runs AFTER measurement so its 80 MB source reads never
            # pollute the timed sample or retained runtime memory figures.
            coverage_evidence = collect_quest_coverage_evidence(root, payload["git"]["head"])
            payload["quest_local_coverage"] = (
                coverage_evidence["coverage"] if coverage_evidence["status"] == "MEASURED"
                else coverage_evidence
            )
    payload['duration_ms'] = milliseconds(started)
    if save:
        write_json(root, 'latest_perf', payload, rotate=True)
    return payload
