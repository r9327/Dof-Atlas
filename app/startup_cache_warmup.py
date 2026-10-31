from __future__ import annotations

import argparse
import json
import os
import sqlite3
from contextlib import closing
import subprocess
import sys
from pathlib import Path
from uuid import uuid4
from time import monotonic, perf_counter, sleep


ROOT = Path(__file__).resolve().parents[1]
CACHE_ROOT = ROOT / ".cache" / "dofus_atlas"
RESULT_PATH = CACHE_ROOT / "startup_cache_warmup_v1.json"
STARTUP_CACHE_MANIFEST = CACHE_ROOT / "startup_cache_manifest_v1.json"
SCHEMA_VERSION = 1
_MANIFEST_SCHEMA_VERSION = 2
_DOMAIN_STAMP_VERSION = 1
# Quest is the Home dependency; Guide and Success may continue after Home paints.
_DOMAIN_ORDER = ("quest", "guide", "success")

_RAW_QUEST_ROOT = ROOT / "data" / "cache" / "dofus_maps" / "raw" / "doduda_cli"
_GUIDES_ROOT = ROOT / "data" / "encyclopedia" / "guides"
_MANUAL_GUIDE_ROOT = ROOT / "data" / "routes" / "guide_ultime_manual"
_QUEST_ENRICHED_SOURCE = ROOT / "data" / "encyclopedia" / "quests" / "quests_enriched.json"

_QUEST_SOURCE_FILES = (
    "languages/fr.json",
    "quests.json",
    "quest_steps.json",
    "quest_objectives.json",
    "quest_step_rewards.json",
    "achievements.json",
    "achievement_objectives.json",
    "achievement_categories.json",
    "quest_categories.json",
    "quest_objective_types.json",
    "items.json",
    "jobs.json",
    "spells.json",
    "titles.json",
    "emoticons.json",
    "monsters.json",
    "npcs.json",
    "areas.json",
    "subareas.json",
    "maps_information.json",
    "char_xp_mappings.json",
)

_SUCCESS_SOURCE_FILES = (
    "achievements.json",
    "achievement_categories.json",
    "achievement_objectives.json",
    "quests.json",
    "monsters.json",
    "dungeons.json",
    "languages/fr.json",
)

_GUIDE_EXTRA_SOURCE_FILES = (
    "item_types.json",
    "effects.json",
)

_DOMAIN_IMPLEMENTATION_FILES = {
    "guide": (
        "app/startup_cache_domain_worker.py",
        "app/modules/encyclopedia/providers/memory_bound_guide_provider.py",
        "app/modules/encyclopedia/providers/dofus_item_provider.py",
        "app/modules/encyclopedia/services/guide_ultime_manual_runtime_core.py",
        "app/modules/encyclopedia/services/guide_ultime_manual_runtime_service.py",
        "app/modules/encyclopedia/services/guide_ultime_manual_route.py",
        "app/modules/encyclopedia/providers/quest_provider.py",
        "app/quest_catalog.py",
        "app/quest_catalog_details.py",
        "app/quest_source_index.py",
    ),
    "quest": (
        "app/startup_cache_domain_worker.py",
        "app/quest_catalog.py",
        "app/quest_catalog_details.py",
        "app/quest_source_index.py",
    ),
    "success": (
        "app/startup_cache_domain_worker.py",
        "app/modules/encyclopedia/providers/memory_bound_achievement_provider.py",
        "app/modules/encyclopedia/providers/achievement_provider.py",
        "app/modules/encyclopedia/services/achievement_index_warmup.py",
        "app/quest_source_index.py",
    ),
}


def _run_module(module: str, *arguments: str) -> str:
    environment = dict(os.environ)
    root = str(ROOT)
    current_pythonpath = str(environment.get("PYTHONPATH") or "")
    environment["PYTHONPATH"] = (
        root if not current_pythonpath else root + os.pathsep + current_pythonpath
    )
    options: dict[str, object] = {
        "cwd": root,
        "env": environment,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "check": False,
        "timeout": 180,
    }
    if os.name == "nt":
        # A hidden Windows console still starts conhost.exe for a console child.
        # This disposable worker has redirected stdio and needs no console;
        # DETACHED_PROCESS avoids that extra resident OS process entirely.
        options["creationflags"] = subprocess.DETACHED_PROCESS

    completed = subprocess.run(
        [sys.executable, "-m", module, *arguments],
        **options,
    )
    if int(completed.returncode) != 0:
        stderr = str(completed.stderr or "").strip()
        raise RuntimeError(
            f"startup cache warmup failed: {module} "
            f"(code {int(completed.returncode)})"
            + (f": {stderr}" if stderr else "")
        )
    return str(completed.stdout or "").strip()


def _last_json_line(output: str) -> dict[str, object]:
    for line in reversed(output.splitlines()):
        value = line.strip()
        if not value:
            continue
        try:
            payload = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Independent Atlas processes can warm the same shared cache concurrently.
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _write_result(payload: dict[str, object]) -> None:
    _write_json_atomic(RESULT_PATH, payload)


def _load_manifest() -> dict[str, object]:
    try:
        payload = json.loads(STARTUP_CACHE_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return {
            "schema_version": _MANIFEST_SCHEMA_VERSION,
            "domains": {},
        }
    if (
        not isinstance(payload, dict)
        or type(payload.get("schema_version")) is not int
        or payload["schema_version"] != _MANIFEST_SCHEMA_VERSION
        or not isinstance(payload.get("domains"), dict)
    ):
        return {
            "schema_version": _MANIFEST_SCHEMA_VERSION,
            "domains": {},
        }
    return payload


def _write_manifest(payload: dict[str, object]) -> None:
    _write_json_atomic(STARTUP_CACHE_MANIFEST, payload)


def _source_paths(domain: str) -> list[Path]:
    name = str(domain)
    paths: list[Path] = [
        ROOT / relative
        for relative in _DOMAIN_IMPLEMENTATION_FILES.get(name, ())
    ]
    if name == "guide":
        paths.extend(_RAW_QUEST_ROOT / relative for relative in _QUEST_SOURCE_FILES)
        paths.extend(_RAW_QUEST_ROOT / relative for relative in _GUIDE_EXTRA_SOURCE_FILES)
        paths.extend((_GUIDES_ROOT, _MANUAL_GUIDE_ROOT, _QUEST_ENRICHED_SOURCE))
    elif name == "quest":
        paths.extend(_RAW_QUEST_ROOT / relative for relative in _QUEST_SOURCE_FILES)
        paths.append(_QUEST_ENRICHED_SOURCE)
    elif name == "success":
        paths.extend(_RAW_QUEST_ROOT / relative for relative in _SUCCESS_SOURCE_FILES)
    return paths


def _expanded_source_files(domain: str) -> list[Path]:
    expanded: dict[str, Path] = {}
    for path in _source_paths(domain):
        if path.is_dir():
            try:
                children = tuple(
                    candidate
                    for candidate in path.rglob("*")
                    if candidate.is_file()
                )
            except OSError:
                children = ()
            if not children:
                expanded[str(path)] = path
                continue
            for child in children:
                expanded[str(child)] = child
        else:
            expanded[str(path)] = path
    return sorted(expanded.values(), key=lambda value: str(value).casefold())


def _path_label(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except (OSError, ValueError):
        return str(path).replace("\\", "/")


def _source_stamp(domain: str) -> list[list[object]]:
    rows: list[list[object]] = [["stamp_version", _DOMAIN_STAMP_VERSION, 0]]
    for path in _expanded_source_files(domain):
        label = _path_label(path)
        try:
            stat = path.stat()
        except OSError:
            rows.append([label, -1, -1])
            continue
        rows.append([label, int(stat.st_size), int(stat.st_mtime_ns)])
    return rows


def _safe_artifact_path(raw_path: object) -> Path | None:
    value = str(raw_path or "").strip()
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    try:
        resolved = path.resolve()
        resolved.relative_to(ROOT.resolve())
    except (OSError, ValueError):
        return None
    return resolved


def _quest_artifact_stamp(path: Path) -> list[object]:
    label = _path_label(path)
    try:
        if not path.is_file() or path.stat().st_size <= 0:
            return [label, -1, 0]
        connection = sqlite3.connect(path, timeout=1)
        try:
            ready = connection.execute(
                "SELECT value FROM metadata WHERE key='ready'"
            ).fetchone()
            count_row = connection.execute("SELECT COUNT(*) FROM quests").fetchone()
        finally:
            connection.close()
    except (OSError, sqlite3.Error):
        return [label, -1, 0]
    count = max(0, int(count_row[0] if count_row else 0))
    return [label, count, 1 if ready is not None else 0]


def _quest_offset_artifact_stamp(path: Path) -> list[object]:
    """Check an indexed source exists *and* contains a readable offsets table.

    A non-empty .sqlite3 filename is not evidence of a usable disk-backed
    Quest index. Keep validation bounded to a single indexed row; full
    integrity/offset scanning belongs to explicit Doctor forensics.
    """
    label = _path_label(path)
    try:
        stat = path.stat()
        if not path.is_file() or stat.st_size <= 0:
            return [label, -1, -1]
        # mode=ro prevents a missing SQLite file from being created during
        # a cache-hit check (including with multiple Atlas processes).
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=1)) as connection:
            row = connection.execute(
                "SELECT start, end FROM offsets LIMIT 1"
            ).fetchone()
        if row is not None and not (
            type(row[0]) is int and type(row[1]) is int and 0 <= row[0] < row[1]
        ):
            return [label, -1, -1]
        return [label, int(stat.st_size), int(stat.st_mtime_ns)]
    except (OSError, sqlite3.Error, ValueError):
        return [label, -1, -1]


def _artifact_stamp(domain: str, cache_files: object) -> list[list[object]]:
    if not isinstance(cache_files, list) or not cache_files:
        return []
    rows: list[list[object]] = []
    for index, raw_path in enumerate(cache_files):
        path = _safe_artifact_path(raw_path)
        if path is None:
            return []
        if domain == "quest" and index == 0:
            rows.append(_quest_artifact_stamp(path))
            continue
        if domain == "quest":
            rows.append(_quest_offset_artifact_stamp(path))
            continue
        label = _path_label(path)
        try:
            stat = path.stat()
        except OSError:
            rows.append([label, -1, -1])
            continue
        rows.append([label, int(stat.st_size), int(stat.st_mtime_ns)])
    return rows


def _cached_domain_result(
    domain: str,
    manifest: dict[str, object],
    source_stamp: list[list[object]],
) -> dict[str, object] | None:
    domains = manifest.get("domains")
    if not isinstance(domains, dict):
        return None
    entry = domains.get(domain)
    if not isinstance(entry, dict):
        return None
    result = entry.get("result")
    expected_artifacts = entry.get("artifact_stamp")
    if not isinstance(result, dict) or result.get("domain") != domain:
        return None
    if entry.get("source_stamp") != source_stamp:
        return None
    if domain == "quest":
        # Old manifests validated the catalogue alone. Require the source
        # indexes too, or first detail silently rebuilds them on demand.
        expected_count = result.get("detail_source_index_count")
        actual_index_count = result.get("detail_index_artifact_count")
        files = result.get("cache_files")
        if (
            type(expected_count) is not int or expected_count <= 0
            or type(actual_index_count) is not int or actual_index_count <= 0
            or actual_index_count > expected_count
            or not isinstance(files, list) or len(files) != actual_index_count + 1
        ):
            return None
    current_artifacts = _artifact_stamp(domain, result.get("cache_files"))
    if not current_artifacts or current_artifacts != expected_artifacts:
        return None
    if any(int(row[1]) <= 0 for row in current_artifacts):
        return None
    return dict(result)


def _run_domain(domain: str) -> dict[str, object]:
    payload = _last_json_line(
        _run_module(
            "app.startup_cache_domain_worker",
            "--domain",
            domain,
        )
    )
    if not payload or str(payload.get("domain") or "") != domain:
        raise RuntimeError(f"startup cache domain worker returned invalid payload: {domain}")
    cache_files = payload.get("cache_files")
    if not isinstance(cache_files, list) or not cache_files:
        raise RuntimeError(f"startup cache domain worker returned no artifacts: {domain}")
    return payload


def _run_or_reuse_domain(
    domain: str,
    manifest: dict[str, object],
) -> tuple[dict[str, object], str, float]:
    started = perf_counter()
    source_stamp = _source_stamp(domain)
    cached = _cached_domain_result(domain, manifest, source_stamp)
    if cached is not None:
        return cached, "reused", round((perf_counter() - started) * 1000.0, 2)

    payload = _run_domain(domain)
    artifact_stamp = _artifact_stamp(domain, payload.get("cache_files"))
    if not artifact_stamp or any(int(row[1]) <= 0 for row in artifact_stamp):
        raise RuntimeError(f"startup cache domain artifacts invalid: {domain}")

    domains = manifest.setdefault("domains", {})
    if not isinstance(domains, dict):
        domains = {}
        manifest["domains"] = domains
    domains[domain] = {
        "source_stamp": source_stamp,
        "artifact_stamp": artifact_stamp,
        "result": payload,
    }
    manifest["schema_version"] = _MANIFEST_SCHEMA_VERSION
    _write_manifest(manifest)
    return payload, "rebuilt", round((perf_counter() - started) * 1000.0, 2)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Disposable Dofus Atlas cache warmup")
    parser.add_argument("--token", default="")
    return parser.parse_args(argv)


def _wait_for_memory_sampler(start_file: str, *, timeout: float = 120.0) -> None:
    """Do not allocate the Guide worker before its concurrent RAM sampler exists."""
    file_path = Path(start_file)
    deadline = monotonic() + max(0.0, timeout)
    while not file_path.is_file():
        if monotonic() >= deadline:
            raise TimeoutError("Atlas memory sampler did not signal warmup start")
        sleep(0.02)


def run_warmup(token: str = "") -> dict[str, object]:
    started = perf_counter()
    token = str(token or "").strip()
    _write_result(
        {
            "schema_version": SCHEMA_VERSION,
            "token": token,
            "status": "running",
        }
    )

    # Benchmark-only barrier: short cold warmups previously finished during
    # Python/Qt benchmark import, making a real 220+ MB peak disappear.
    go_file = os.environ.get("DOFUS_ATLAS_WARMUP_GO_FILE", "").strip()
    if go_file:
        _wait_for_memory_sampler(go_file)

    manifest = _load_manifest()
    domain_results: dict[str, dict[str, object]] = {}
    domain_timings: dict[str, dict[str, object]] = {}

    # Priority is deterministic: the largest user-facing path is ready first.
    for domain in _DOMAIN_ORDER:
        payload, mode, elapsed_ms = _run_or_reuse_domain(domain, manifest)
        domain_results[domain] = payload
        domain_timings[domain] = {
            "mode": mode,
            "elapsed_ms": elapsed_ms,
            "worker_elapsed_ms": float(payload.get("elapsed_ms") or 0.0),
            "timings_ms": dict(payload.get("timings_ms") or {})
            if isinstance(payload.get("timings_ms"), dict)
            else {},
        }
        # Each domain's atomic, validated cache generation is independently
        # usable. Publish its readiness immediately instead of making the
        # Quest UI wait for all unrelated background workers to exit.
        completed = tuple(name for name in _DOMAIN_ORDER if name in domain_results)
        partial_tasks = {
            str(label): dict(task)
            for name in ("guide", "success")
            for label, task in (
                (domain_results.get(name, {}).get("tasks") or {}).items()
                if isinstance(domain_results.get(name, {}).get("tasks"), dict)
                else ()
            )
            if isinstance(task, dict)
        }
        _write_result({
            "schema_version": SCHEMA_VERSION,
            "token": token,
            "status": "running",
            "completed_domains": list(completed),
            "quest_count": max(0, int(domain_results.get("quest", {}).get("quest_count") or 0)),
            "encyclopedia_ready": all(
                key in partial_tasks
                for key in ("guide", "guide_items", "success", "success_names")
            ),
            "domains": dict(domain_timings),
        })

    tasks: dict[str, dict[str, object]] = {}
    for domain in ("guide", "success"):
        domain_tasks = domain_results[domain].get("tasks")
        if isinstance(domain_tasks, dict):
            for label, task in domain_tasks.items():
                if isinstance(task, dict):
                    tasks[str(label)] = dict(task)

    quest_count = max(0, int(domain_results["quest"].get("quest_count") or 0))
    encyclopedia_ready = all(
        label in tasks
        for label in ("guide", "guide_items", "success", "success_names")
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "token": token,
        "status": "ready",
        "completed_domains": list(_DOMAIN_ORDER),
        "quest_count": quest_count,
        "encyclopedia_ready": encyclopedia_ready,
        "tasks": tasks,
        "domains": domain_timings,
        "elapsed_ms": round((perf_counter() - started) * 1000.0, 2),
    }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    token = str(args.token or "").strip()
    started = perf_counter()
    try:
        payload = run_warmup(token)
    except Exception as exc:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "token": token,
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_ms": round((perf_counter() - started) * 1000.0, 2),
        }
        _write_result(payload)
        print(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            file=sys.stderr,
        )
        return 1

    _write_result(payload)
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
