from __future__ import annotations

"""Opt-in advisory OSS diagnostics routed through Atlas Doctor.

The canonical Doctor and tool_catalog remain responsible for planning and
certification. This module never installs, updates or silently runs candidates.
"""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import site
import subprocess
import sys
from typing import Any, Iterable

from tools.tool_catalog import catalog, local_candidate_preflight, select_tools
from tools.atlas_doctor_lib.oss_intelligence import intelligent_plan

MAX_FILES = 16
MAX_TIMEOUT = 60
_ALLOWED = re.compile(r"^[A-Za-z0-9_./-]{1,240}$")
_CODE_ROOTS = frozenset({"app", "tools", "tests", "scripts"})


def _open_source_inventory(root: Path) -> dict[str, Any]:
    """Reflect the 29 candidates from the existing study, not a second registry."""
    study = root / "docs" / "roadmap" / "GITHUB_OPEN_SOURCE_INTEGRATION_2026-10-31.md"
    if not study.is_file():
        return {"status": "NOT_AVAILABLE", "candidates": [], "count": 0}
    candidates: list[dict[str, str]] = []
    supplements: list[dict[str, str]] = []
    seen: set[str] = set()
    lines = study.read_text(encoding="utf-8").splitlines()
    for line in lines:
        if not line.startswith(("| ATOSS-", "| AT-SUP-")):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4 or not re.fullmatch(r"(ATOSS-[0-9]{2}|AT-SUP-[0-9]{2})", cells[0]):
            continue
        candidate_id, source, decision = cells[:3]
        if candidate_id in seen:
            return {"status": "REVIEW", "reason": "Duplicate source candidate",
                    "count": len(candidates), "candidates": candidates,
                    "supplemental": supplements}
        seen.add(candidate_id)
        match = re.search(r"\[([^\]]+)\]\(https://github.com/[^)]+\)", source)
        name = match.group(1) if match else source[:64]
        integration = "NOT_VERIFIED"
        if "REJECT" in decision:
            integration = "REJECTED"
        elif candidate_id in {"ATOSS-06", "ATOSS-10", "AT-SUP-02"}:
            integration = "EXISTING_OWNER_NOT_RETESTED"
        elif candidate_id in {"ATOSS-20", "ATOSS-21"}:
            integration = "DOCTOR_OPT_IN_ONLY"
        row = {"id": candidate_id, "name": name, "study_decision": decision,
               "integration": integration}
        if candidate_id.startswith("ATOSS-"):
            candidates.append(row)
        else:
            supplements.append(row)
    # A count alone can hide a misspelled or substituted ID (29+5 is not
    # sufficient evidence that the contractual 34 projects are all present).
    expected = {f"ATOSS-{number:02d}" for number in range(1, 30)}
    expected.update(f"AT-SUP-{number:02d}" for number in range(1, 6))
    missing = sorted(expected - seen)
    unexpected = sorted(seen - expected)
    # The same canonical Markdown study includes an optional final-decision
    # table. Never maintain a second Python registry or treat decisions as
    # installation/execution witnesses. Missing/inconsistent decisions fail
    # closed only when the final table has actually been declared.
    final_declared = False
    final_rows: dict[str, str] = {}
    decision_errors = []
    allowed = {"ADOPTED", "KEEP_EXISTING", "REJECTED",
               "HOLDING_ONLY", "DEFERRED_WITH_REASON"}
    for line in lines:
        if line.startswith("### Décision de maintenance pour chacun des 34 candidats"):
            if final_declared:
                decision_errors.append("duplicate decision section")
            final_declared = True
            continue
        if final_declared and line.startswith("### "):
            break
        if not final_declared or not line.startswith("| **"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        match = re.fullmatch(r"\*\*(ATOSS-[0-9]{2}|AT-SUP-[0-9]{2})\*\*",
                             cells[0] if cells else "")
        if not match or len(cells) < 4 or cells[1] not in allowed:
            decision_errors.append("malformed final decision row")
            continue
        cid = match.group(1)
        if cid in final_rows:
            decision_errors.append("duplicate final decision")
        final_rows[cid] = cells[1]
    decision_missing = sorted(expected - set(final_rows)) if final_declared else []
    decision_unexpected = sorted(set(final_rows) - expected)
    decision_ok = (not decision_errors and not decision_missing
                   and not decision_unexpected) if final_declared else False
    for row in candidates + supplements:
        row["final_decision"] = final_rows.get(row["id"])
    decision_counts = {name: sum(v == name for v in final_rows.values())
                       for name in sorted(allowed)}
    return {
        "status": ("INVENTORIED_NOT_CERTIFIED"
                   if not missing and not unexpected
                   and (not final_declared or decision_ok) else "REVIEW"),
        "final_decision_status": ("DOCUMENTED_NOT_QUALIFIED" if decision_ok
                                  else "REVIEW" if final_declared
                                  else "NOT_RECORDED"),
        "final_decision_counts": decision_counts,
        "final_decision_missing_ids": decision_missing,
        "final_decision_unexpected_ids": decision_unexpected,
        "final_decision_errors": decision_errors,
        "final_decisions_are_execution_evidence": False,
        "count": len(candidates), "candidates": candidates,
        "supplemental_count": len(supplements), "supplemental": supplements,
        "missing_ids": missing, "unexpected_ids": unexpected,
        "execution_witnesses": 0,
        "note": "Static study decisions; execution requires independent exact-SHA evidence.",
    }


def _safe_files(root: Path, paths: Iterable[str]) -> list[str]:
    """Validate all paths before any discovery or subprocess invocation."""
    given = list(paths)
    if not 1 <= len(given) <= MAX_FILES:
        raise ValueError("Expected 1..16 explicit files")
    clean: list[str] = []
    base = root.resolve()
    for value in given:
        if not isinstance(value, str) or not _ALLOWED.fullmatch(value):
            raise ValueError("Invalid repository-relative file")
        rel = PurePosixPath(value)
        if (value.startswith("/") or "\\" in value
                or any(part in {".", ".."} for part in rel.parts)
                or (len(rel.parts) < 2
                    and value not in {"requirements-pyside.txt", "pyproject.toml"})):
            raise ValueError("Unsafe repository-relative file")
        if rel.parts[0] in _CODE_ROOTS or rel.parts[0] == "data":
            if rel.suffix not in {".py", ".pyi", ".json", ".png", ".jpg",
                                  ".jpeg", ".webp", ".ttf", ".otf"}:
                raise ValueError("Unsupported scoped source or asset file")
        elif rel.parts[:2] == (".github", "workflows"):
            if rel.suffix not in {".yml", ".yaml"}:
                raise ValueError("Only workflow YAML files can be analyzed here")
        elif value not in {"requirements-pyside.txt", "pyproject.toml"}:
            raise ValueError("Scope is not owned by this advisory diagnostic")
        target = base.joinpath(*rel.parts)
        if not target.is_file() or target.is_symlink() or not target.resolve().is_relative_to(base):
            raise ValueError("File is missing, symlinked or outside the checkout")
        if value not in clean:
            clean.append(value)
    return clean



def _zizmor_executable(root: Path | None = None) -> str | None:
    """Resolve a regular absolute executable outside the scanned checkout.

    Windows may search the current directory before PATH; a checkout-local
    impostor, relative entry, symlink or batch script is never trusted.
    """
    from shutil import which
    found = which("zizmor")
    candidates = [Path(found)] if found else []
    if sys.platform == "win32":
        candidates.append(Path(site.getuserbase()) / "Scripts" / "zizmor.exe")
    checkout = root.resolve() if root is not None else None
    for candidate in candidates:
        if (not candidate.is_absolute() or candidate.is_symlink()
                or not candidate.is_file()
                or (sys.platform == "win32" and candidate.suffix.casefold() != ".exe")):
            continue
        resolved = candidate.resolve()
        if checkout is not None and resolved.is_relative_to(checkout):
            continue
        return str(resolved)
    return None


def _execute_zizmor(root: Path, files: list[str], timeout: int,
                    *, binary: str) -> dict[str, Any]:
    """Run an installed workflow scanner, explicitly offline, without changes."""
    if not isinstance(binary, str) or not Path(binary).is_absolute():
        return {"status": "UNAVAILABLE", "tool": "zizmor",
                "reason": "Scanner requires an absolute executable path"}
    # Strictly bound input volume; inputs are pre-validated regular files.
    if any((root / file).stat().st_size > 1024 * 1024 for file in files):
        return {"status": "NOT_APPLICABLE", "tool": "zizmor",
                "reason": "Workflow exceeds bounded scan size"}
    command = [binary, "--offline", "--no-config", "--no-progress",
               "--no-exit-codes", "--format=json", "--", *files]
    # No GitHub token or proxy environment is inherited. --offline is mandatory
    # even if zizmor happens to be configured with credentials elsewhere.
    env = {key: value for key, value in os.environ.items()
           if key in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME"}}
    env.update({"ZIZMOR_OFFLINE": "1", "NO_COLOR": "1"})
    try:
        completed = subprocess.run(command, cwd=root, env=env,
                                   capture_output=True, text=True,
                                   timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "tool": "zizmor"}
    except OSError:
        return {"status": "UNAVAILABLE", "tool": "zizmor"}
    if completed.returncode != 0:
        return {"status": "ERROR", "tool": "zizmor",
                "reason": "Tool failed or incompatible CLI"}
    if len(completed.stdout) > 2_000_000:
        return {"status": "ERROR", "tool": "zizmor",
                "reason": "Bounded report limit exceeded"}
    try:
        findings = json.loads(completed.stdout)
        if not isinstance(findings, list) or not all(
                isinstance(row, dict) for row in findings):
            raise ValueError("unexpected zizmor JSON")
    except (ValueError, TypeError):
        return {"status": "ERROR", "tool": "zizmor",
                "reason": "Invalid scanner response"}
    # Never return excerpts of source, secrets, host paths or arbitrary messages.
    return {"status": "FINDINGS" if findings else "CLEAN", "tool": "zizmor",
            "finding_count": len(findings), "exit_code": completed.returncode,
            "offline_requested": True}


def select_eligible_diagnostics(root: Path, paths: Iterable[str], *,
                                limit: int = MAX_FILES) -> dict[str, Any]:
    """Bound automatic Doctor checks to explicit, existing and safe input files.

    No directory discovery, globbing, automatic imports or opportunistic
    execution of new candidates. Unsupported files stay with canonical owners.
    An invalid candidate is never forwarded to an external scanner.
    """
    if not 1 <= limit <= MAX_FILES:
        raise ValueError("eligible diagnostic limit must be 1..16")
    eligible: list[str] = []
    seen: set[str] = set()
    ignored = 0
    over_limit = 0
    for raw in paths:
        # Only the two audited adapters are automatically executable.
        if not isinstance(raw, str) or not (
                raw.endswith((".py", ".pyi"))
                or (raw.startswith(".github/workflows/")
                    and raw.endswith((".yml", ".yaml")))):
            ignored += 1
            continue
        try:
            safe = _safe_files(root, [raw])[0]
        except ValueError:
            ignored += 1
            continue
        if safe in seen:
            continue
        seen.add(safe)
        if len(eligible) < limit:
            eligible.append(safe)
        else:
            over_limit += 1
    return {
        "schema_version": 1,
        "source": "tools.atlas_doctor_lib.oss_router.select_eligible_diagnostics",
        "files": eligible,
        "selected_count": len(eligible),
        "ignored_count": ignored,
        "truncated_count": over_limit,
        "coverage_complete": over_limit == 0,
        "scope": "Only explicit existing Python files and GitHub Actions workflows",
        "certified": False,
    }



def _file_digests(root: Path, files: list[str]) -> dict[str, str]:
    """Bound input-file integrity evidence; no writes or recursive discovery."""
    digests: dict[str, str] = {}
    for name in files:
        target = root / name
        if target.is_symlink() or not target.is_file() or target.stat().st_size > 2_000_000:
            raise ValueError("Unverifiable or oversized diagnostic input")
        # The earlier stat is only a preflight: the file can grow between
        # stat and read. Stream in bounded chunks so a concurrent writer
        # cannot force an unbounded allocation or smuggle oversized input.
        hasher = hashlib.sha256()
        total = 0
        with target.open("rb") as handle:
            while chunk := handle.read(256 * 1024):
                total += len(chunk)
                if total > 2_000_000:
                    raise ValueError("Unverifiable or oversized diagnostic input")
                hasher.update(chunk)
        if target.is_symlink():
            raise ValueError("Unverifiable or oversized diagnostic input")
        digests[name] = hasher.hexdigest()
    return digests



def _observed_tool_version(root: Path, name: str) -> str | None:
    """Capture an actually running local tool version without leaking stdout."""
    if name not in {"ruff", "zizmor"}:
        return None
    # -P protects against loading a rogue ruff module from the checkout.
    # Unlike -s/PYTHONNOUSERSITE, it keeps pip --user installations visible.
    if name == "zizmor":
        executable = _zizmor_executable(root)
        if executable is None:
            return None
        command = [executable, "--version"]
    else:
        command = [sys.executable, "-P", "-m", "ruff", "--version"]
    env = {key: value for key, value in os.environ.items()
           if key in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME"}}
    env.update({"ZIZMOR_OFFLINE": "1", "PIP_NO_INDEX": "1",
                "PYTHONPATH": "", "NO_COLOR": "1"})
    try:
        result = subprocess.run(command, cwd=root, env=env,
                                capture_output=True, text=True,
                                timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    match = re.fullmatch(
        rf"{name}\s+v?([0-9]+(?:\.[0-9]+){{1,3}}(?:[-+][a-zA-Z0-9.-]+)?)",
        result.stdout.strip(), re.IGNORECASE)
    return match.group(1) if match else None


def qualify_live(root: Path, paths: Iterable[str], *,
                 timeout_seconds: int = 30) -> dict[str, Any]:
    """Attest actual local subprocess execution, never Windows or phase certification.

    This explicit check is separate from mocked unit tests and only speaks about
    the inspected input files on the runner where the command was executed.
    """
    files = _safe_files(root, paths)
    python_files = [name for name in files if name.endswith((".py", ".pyi"))]
    workflows = [name for name in files if name.startswith(".github/workflows/")
                 and name.endswith((".yml", ".yaml"))]
    if not python_files or not workflows:
        return {
            "schema_version": 1, "status": "REVIEW",
            "reason": "Live qualification requires both Python and workflow inputs",
            "requested_tools": ["ruff", "zizmor"],
            "actual_executions": 0, "input_files_unchanged": None,
            "windows_13_qualified": False, "phase_certified": False,
        }
    try:
        before = _file_digests(root, files)
    except (OSError, ValueError):
        return {
            "schema_version": 1, "status": "BLOCKED",
            "reason": "Cannot snapshot explicit inputs",
            "requested_tools": ["ruff", "zizmor"],
            "actual_executions": 0, "input_files_unchanged": None,
            "windows_13_qualified": False, "phase_certified": False,
        }
    diagnostic = route_oss(root, files, run=True, timeout_seconds=timeout_seconds)
    try:
        after = _file_digests(root, files)
        unchanged = before == after
    except (OSError, ValueError):
        unchanged = False
    expected = ("ruff", "zizmor")
    results = diagnostic.get("execution_results", [])
    # Execution counts must match the *named* approved adapters, in order.
    # An arbitrary successful JSON row cannot impersonate another tool.
    statuses = [
        (row.get("status") if isinstance(row, dict) and row.get("tool") == expected[index]
         else "INVALID_TOOL_ID")
        for index, row in enumerate(results[:len(expected)])
    ]
    witnesses = sum(status in {"CLEAN", "FINDINGS"} for status in statuses)
    all_executed = len(results) == len(expected) and witnesses == len(expected)
    # Reuse the approved developer lock, imported only for an explicit live
    # check. Valid output from an arbitrary older/newer tool is not qualified.
    from tools.doctor_oss_wheels import PINS
    versions = ({tool: _observed_tool_version(root, tool) for tool in expected}
                if unchanged and all_executed else {})
    versions_match_lock = bool(
        unchanged and all_executed
        and all(versions.get(tool) == PINS[tool] for tool in expected))
    intact = versions_match_lock
    # A local test on Linux/macOS is not a native Windows qualification.
    windows_13 = sys.platform == "win32" and sys.version_info[:2] == (3, 13)
    return {
        "schema_version": 1,
        "source": "tools.atlas_doctor_lib.oss_router.qualify_live",
        "status": "LIVE_PASS" if intact else "REVIEW" if unchanged else "FAIL",
        "reason": ("Both scanners returned valid results on unchanged inputs with locked versions"
                   if intact else "Input changed, scanner incomplete, or tool version mismatched"),
        "requested_tools": list(expected),
        "actual_executions": witnesses,
        "tool_statuses": [{"tool": name,
                           "status": statuses[index] if index < len(statuses) else "NOT_RUN"}
                          for index, name in enumerate(expected)],
        "input_files_unchanged": unchanged,
        "input_sha256": before if unchanged else {},
        "python_version": ".".join(map(str, sys.version_info[:3])),
        "platform": sys.platform,
        "windows_13_qualified": bool(intact and windows_13),
        "version_claims": {row.get("id"): row.get("version_claim")
                           for row in diagnostic.get("oss_candidates", [])
                           if isinstance(row, dict)},
        "versions_observed": versions,
        "versions_required": {tool: PINS[tool] for tool in expected},
        "versions_match_lock": versions_match_lock,
        "version_proof": "Actual --version matched developer lock; not provenance or license",
        "gaps": diagnostic.get("execution_summary", {}).get("gaps", []),
        "phase_certified": False,
        "network_verified_by_traffic_capture": False,
        "scope_limit": "Source-file hashes only; no proof of unrelated file or network effects",
    }


def trial_fonttools(root: Path, paths: Iterable[str]) -> dict[str, Any]:
    """Explicit, bounded font metadata review; never modifies/repackages Unity fonts.

    Only read 1..16 validated local TTF/OTF sources. Font names and metadata
    are untrusted publisher claims, not proof of font license/redistribution.
    """
    files = _safe_files(root, paths)
    if any(not path.casefold().endswith((".ttf", ".otf")) for path in files):
        raise ValueError("fontTools trial accepts only explicit TTF/OTF sources")
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        return {
            "schema_version": 1, "status": "NOT_AVAILABLE",
            "tool": "fonttools", "requested_files": len(files),
            "execution_count": 0, "phase_certified": False,
            "reason": "fontTools is an optional developer-only dependency",
        }
    try:
        before = _file_digests(root, files)
        rows = []
        for relative in files:
            file = root.resolve() / relative
            font = TTFont(file, lazy=True, recalcBBoxes=False,
                          recalcTimestamp=False)
            try:
                names = font["name"]
                # Reading a name table is not a proof of glyph/Qt compatibility.
                family = names.getDebugName(1)
                style = names.getDebugName(2)
                claim = names.getDebugName(13)
                if not isinstance(family, str) or not family.strip():
                    raise ValueError("Font is missing a display family")
                rows.append({
                    "path": relative,
                    "family": family.strip()[:100],
                    "style": style.strip()[:100] if isinstance(style, str) else None,
                    "license_metadata_present": bool(claim),
                    "license_verified": False,
                    "qt_rendering_verified": False,
                })
            finally:
                font.close()
        if before != _file_digests(root, files):
            raise ValueError("Font inputs changed during inspection")
    except Exception:
        # Parser failures are non-authoritative and must not spill untrusted
        # font strings, paths or exceptions into the Doctor report.
        return {
            "schema_version": 1, "status": "ERROR",
            "tool": "fonttools", "requested_files": len(files),
            "execution_count": 0, "phase_certified": False,
            "reason": "Font metadata could not be verified safely",
        }
    return {
        "schema_version": 1,
        "source": "tools.atlas_doctor_lib.oss_router.trial_fonttools",
        "status": "TRIAL_COMPLETE", "tool": "fonttools",
        "requested_files": len(files), "execution_count": 1,
        "input_integrity_verified": True,
        "fonts": rows,
        "license_verified": False,
        "qt_rendering_verified": False,
        "runtime_consumers_verified": False,
        "no_file_mutations": True,
        "phase_certified": False,
    }


def trial_imagehash(root: Path, paths: Iterable[str], *,
                    max_pixels: int = 2_000_000,
                    max_file_bytes: int = 2_000_000) -> dict[str, Any]:
    """Explicit ImageHash advisory for local assets, never a deletion decision.

    Pixel or image contents never leave memory. ImageHash/Pillow are imported
    only when this trial is requested. Bounded files and dimensions prevent
    accidental whole-asset-tree scans or oversized decompression.
    """
    files = _safe_files(root, paths)
    if not files or any(not path.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
                        for path in files):
        raise ValueError("ImageHash trial requires only explicit image files")
    if not 1 <= max_pixels <= 2_000_000 or not 1 <= max_file_bytes <= 2_000_000:
        raise ValueError("Unbounded ImageHash trial rejected")
    try:
        from PIL import Image
        import imagehash
    except ImportError:
        return {
            "schema_version": 1, "status": "NOT_AVAILABLE",
            "tool": "imagehash", "requested_files": len(files),
            "execution_count": 0, "phase_certified": False,
            "reason": "Pillow/ImageHash unavailable; developer-only optional trial",
        }
    try:
        before = _file_digests(root, files)
        hashes = []
        for relative in files:
            path = root.resolve() / relative
            if path.stat().st_size > max_file_bytes:
                raise ValueError("Image file exceeds trial budget")
            with Image.open(path) as picture:
                if (picture.width < 1 or picture.height < 1 or
                        picture.width * picture.height > max_pixels):
                    raise ValueError("Image dimension exceeds trial budget")
                hashes.append(imagehash.phash(picture))
        intact = before == _file_digests(root, files)
        if not intact:
            raise ValueError("Image input changed during ImageHash trial")
        candidates = [
            {"first": files[i], "second": files[j], "distance": int(hashes[i] - hashes[j])}
            for i in range(len(files)) for j in range(i + 1, len(files))
            if int(hashes[i] - hashes[j]) <= 6
        ]
    except (OSError, ValueError, TypeError, AttributeError,
            RuntimeError, Image.DecompressionBombError):
        return {
            "schema_version": 1, "status": "ERROR",
            "tool": "imagehash", "requested_files": len(files),
            "execution_count": 0, "phase_certified": False,
            "reason": "Image input or trial could not be safely verified",
        }
    return {
        "schema_version": 1, "status": "TRIAL_COMPLETE",
        "source": "tools.atlas_doctor_lib.oss_router.trial_imagehash",
        "tool": "imagehash", "requested_files": len(files),
        "execution_count": 1, "input_integrity_verified": True,
        "max_hamming_distance": 6,
        "possible_visual_duplicates": candidates,
        "automated_deletion_allowed": False,
        "runtime_consumers_verified": False,
        "phase_certified": False, "license_verified": False,
        "limits": "Potential visual overlaps only; Unity variants and actual runtime consumers need human review.",
    }


def route_oss(root: Path, paths: Iterable[str], *, run: bool = False,
              timeout_seconds: int = 20) -> dict[str, Any]:
    """Select useful tools by file type; run only reviewed Ruff on explicit opt-in."""
    if not 1 <= timeout_seconds <= MAX_TIMEOUT:
        raise ValueError("timeout_seconds must be in 1..60")
    files = _safe_files(root, paths)
    python_files = [name for name in files if name.endswith((".py", ".pyi"))]
    workflows = [name for name in files if name.endswith((".yml", ".yaml"))]
    # Snapshot exactly the source files handed to approved external processes.
    # A tool's "read only" flags are not evidence that it left inputs intact.
    approved_files = python_files + workflows
    before_digests = None
    if run and approved_files:
        try:
            before_digests = _file_digests(root, approved_files)
        except (OSError, ValueError):
            pass  # Fail closed below; do not launch a scanner without a snapshot.
    capability = "validation" if python_files else "ci_intelligence"
    # The existing catalog is the only source for native Doctor tool readiness.
    native_report = catalog(root)
    native = select_tools(native_report, capability=capability,
                          safe_only=True, ready_only=True, limit=5)
    study = _open_source_inventory(root)
    selection = intelligent_plan(files, study)
    # Optional package discovery is untrusted local metadata. A broken
    # distribution must not terminate the canonical Doctor command or leak
    # filesystem paths; it also must not silently become NOT_AVAILABLE.
    preflight_error_type = None
    try:
        probe = local_candidate_preflight(
            packages=["ruff"] if python_files else [],
            binaries=["zizmor"] if workflows else [])
        discovered = {((row.get("kind") or "python_distribution"), row["name"].casefold()): row
                      for row in probe["results"]}
        # Optional package metadata is untrusted: a string such as "false"
        # must not be truthy evidence that Ruff is installed. Missing or
        # malformed version metadata must not crash Doctor after preflight.
        detected_ruff = discovered.get(("python_distribution", "ruff"))
        if detected_ruff is not None and (
                not isinstance(detected_ruff.get("available"), bool)
                or "version" not in detected_ruff
                or (detected_ruff["version"] is not None
                    and not isinstance(detected_ruff["version"], str))):
            raise ValueError("Malformed Ruff preflight metadata")
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RuntimeError) as exc:
        discovered = {}
        preflight_error_type = type(exc).__name__
    detected = discovered.get(("python_distribution", "ruff"))
    available = bool(detected and detected["available"])
    # Preflight is discovery metadata, not proof of the executable to launch.
    # Resolve the same absolute file used for subsequent version attestation.
    workflow_executable = (
        _zizmor_executable(root) if workflows and not preflight_error_type else None
    )
    workflow_available = bool(workflow_executable)
    timeout_each = max(1, timeout_seconds // max(1, int(bool(python_files)) + int(bool(workflows))))
    execution: dict[str, Any] = {"status": "NOT_RUN", "reason": "Explicit --run required"}
    if run and approved_files and before_digests is None:
        execution = {"status": "ERROR", "tool": "ruff",
                     "reason": "Cannot snapshot explicit scanner inputs"}
    elif run and preflight_error_type:
        execution = {"status": "ERROR", "tool": "ruff",
                     "reason": "Optional package discovery failed",
                     "error_type": preflight_error_type}
    elif run and not python_files:
        execution = {"status": "NOT_APPLICABLE", "reason": "No approved workflow OSS executor"}
    elif run and not available:
        execution = {"status": "NOT_AVAILABLE", "tool": "ruff",
                     "reason": "Ruff not installed; no auto-install"}
    elif run:
        # Fixed argv and Python interpreter: never evaluate a PATH binary or shell.
        # Ruff's --isolated/--no-cache/--no-fix forbid configuration-driven writes.
        command = [sys.executable, "-P", "-m", "ruff", "check", "--isolated",
                   "--no-cache", "--no-fix", "--output-format", "json",
                   "--target-version", "py313", "--", *python_files]
        env = {key: value for key, value in os.environ.items()
               if key in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME"}}
        env.update({"PYTHONPATH": "",
                    "RUFF_NO_CACHE": "1", "NO_COLOR": "1", "PIP_NO_INDEX": "1"})
        try:
            result = subprocess.run(command, cwd=root, env=env,
                                    capture_output=True, text=True,
                                    timeout=timeout_each, check=False)
        except subprocess.TimeoutExpired:
            execution = {"status": "TIMEOUT", "tool": "ruff",
                         "reason": "Bounded OSS diagnostic timed out"}
        except OSError:
            execution = {"status": "UNAVAILABLE", "tool": "ruff",
                         "reason": "Cannot start local Ruff module"}
        else:
            try:
                if len(result.stdout) > 2_000_000:
                    raise ValueError("Bounded Ruff report limit exceeded")
                findings = json.loads(result.stdout)
                if not isinstance(findings, list) or result.returncode not in (0, 1):
                    raise ValueError("unexpected Ruff output")
                # Ruff exits 0 when clean and 1 when lint findings exist.
                # A contradictory exit code must not be interpreted as CLEAN.
                if bool(findings) != (result.returncode == 1):
                    raise ValueError("Ruff result and exit code disagree")
                counts: dict[str, int] = {}
                for item in findings:
                    if not isinstance(item, dict):
                        raise ValueError("unexpected diagnostic item")
                    code = item.get("code")
                    if isinstance(code, str) and re.fullmatch(r"[A-Z0-9]{1,10}", code):
                        counts[code] = counts.get(code, 0) + 1
                execution = {"status": "FINDINGS" if findings else "CLEAN",
                             "exit_code": result.returncode,
                             "finding_count": len(findings),
                             "rule_counts": counts,
                             "tool": "ruff"}
            except (ValueError, TypeError, json.JSONDecodeError):
                execution = {"status": "ERROR", "tool": "ruff",
                             "reason": "Unexpected Ruff response",
                             "exit_code": result.returncode,
                             "stdout_bytes": len(result.stdout),
                             "stderr_present": bool(result.stderr)}
    workflow_execution = None
    if workflows:
        if not run:
            workflow_execution = {"status": "NOT_RUN", "tool": "zizmor"}
        elif before_digests is None:
            workflow_execution = {"status": "ERROR", "tool": "zizmor",
                                  "reason": "Cannot snapshot explicit scanner inputs"}
        elif preflight_error_type:
            workflow_execution = {"status": "ERROR", "tool": "zizmor",
                                  "reason": "Optional package discovery failed",
                                  "error_type": preflight_error_type}
        elif not workflow_available:
            workflow_execution = {"status": "NOT_AVAILABLE", "tool": "zizmor",
                                  "reason": "Not installed; no installation attempted"}
        else:
            workflow_execution = _execute_zizmor(root, workflows, timeout_each,
                                                 binary=workflow_executable)
        if not python_files:
            execution = workflow_execution
    inputs_modified = None
    if run and before_digests is not None:
        try:
            inputs_modified = before_digests != _file_digests(root, approved_files)
        except (OSError, ValueError):
            inputs_modified = True
    if inputs_modified:
        # No CLEAN/FINDINGS witness survives a source mutation, even if the
        # subprocess returned a valid report. Never disclose changed contents.
        if python_files:
            execution = {"status": "ERROR", "tool": "ruff",
                         "reason": "Explicit scan input changed during execution"}
        if workflows:
            workflow_execution = {"status": "ERROR", "tool": "zizmor",
                                  "reason": "Explicit scan input changed during execution"}
        if not python_files:
            execution = workflow_execution
    results = ([execution] if python_files else []) + (
        [workflow_execution] if workflow_execution is not None else [])
    expected_tools = (["ruff"] if python_files else []) + (
        ["zizmor"] if workflows else [])
    summarized = [
        {"tool": tool, "status": results[index].get("status", "ERROR")}
        for index, tool in enumerate(expected_tools)
    ]
    gaps = [row for row in summarized if row["status"] not in {"CLEAN", "FINDINGS"}]
    execution_summary = {
        "status": ("NOT_RUN" if not run else "NOT_APPLICABLE"
                   if not expected_tools else "COMPLETE" if not gaps else "INCOMPLETE"),
        "expected_tools": expected_tools,
        "confirmed_executions": len(expected_tools) - len(gaps) if run else 0,
        "gaps": gaps,
        "does_not_override_doctor": True,
    }
    return {
        "schema_version": 1,
        "source": "tools.atlas_doctor_lib.oss_router.route_oss",
        "status": "ADVISORY_ONLY",
        "files": files,
        "scope": {"python": len(python_files), "workflows": len(workflows)},
        "native_tools": [{"path": item["path"], "capabilities": item["capabilities"]}
                         for item in native["tools"]],
        "native_tools_executed": False,
        "native_catalog": {
            "source": "tools.tool_catalog.catalog",
            "tool_count": native_report.get("tool_count"),
            "agent_ready_count": native_report.get("agent_ready_count"),
            "automation_ready_count": native_report.get("automation_ready_count"),
            "unguarded_mutator_count": native_report.get("unguarded_mutator_count"),
            "unready_total": sum(not item.get("automation_ready", False)
                                 for item in native_report.get("tools", [])),
            "unready_sample": [
                {"path": item.get("path"), "readiness": item.get("readiness")}
                for item in native_report.get("tools", [])
                if not item.get("automation_ready", False)
            ][:25],
            "execution_witnesses": 0,
        },
        "open_source_inventory": study,
        "intelligent_selection": selection,
        "local_preflight_status": "ERROR" if preflight_error_type else "OBSERVED_NOT_QUALIFIED",
        "local_preflight_error_type": preflight_error_type,
        "oss_candidates": [
            {"id": "ruff", "selected": bool(python_files),
             "available": available, "version_claim": detected["version"] if detected else None,
             "license_verified": False, "platform_verified": False,
             "automation_ready": False},
            {"id": "zizmor", "selected": bool(workflows),
             "available": workflow_available,
             "version_claim": None, "license_verified": False,
             "platform_verified": False, "automation_ready": False},
        ],
        "execution_results": results,
        "execution_summary": execution_summary,
        "execution_count": sum(result["status"] in {"CLEAN", "FINDINGS"}
                               for result in results),
        "execution": execution,
        "network_requested": False,
        "network_used": None if run and (available or workflow_available) else False,
        "dependencies_installed": False,
        "files_modified": inputs_modified,
        "input_integrity_verified": inputs_modified is False,
        "phase_certified": False,
        "benchmark_executed": False,
        "note": "Advisory OSS evidence only; Doctor's canonical gates still apply.",
    }
