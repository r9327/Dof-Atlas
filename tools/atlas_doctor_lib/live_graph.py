from __future__ import annotations

"""Opt-in loopback-only status overlay for a fixed Graphify graph snapshot.

Updates tracked/untracked changed-file highlighting, NOT Graphify's AST edges.
No watcher thread, Qt import, rebuild, or full test suite in Atlas itself.
"""
import ast
import json
import re
import subprocess
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

MAX_PATHS = 200
MAX_PYTHON_FILES = 12
MAX_SOURCE_BYTES = 256 * 1024
MAX_IMPORT_ROWS = 32
_SHA = re.compile(r"^[0-9a-f]{7,40}$")


def _git(root: Path, *args: str) -> bytes:
    run = subprocess.run(
        ["git", *args], cwd=root, capture_output=True,
        check=False, timeout=10,
    )
    if run.returncode:
        raise RuntimeError(f"Git status unavailable: {run.returncode}")
    return run.stdout


def _direct_imports(contents: bytes, filename: str) -> dict[str, int]:
    tree = ast.parse(contents.decode("utf-8-sig"), filename=filename)
    found: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.setdefault("import " + alias.name + (" as " + alias.asname if alias.asname else ""), node.lineno)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level + (node.module or "")
            for alias in node.names:
                found.setdefault("from " + prefix + " import " + alias.name +
                                 (" as " + alias.asname if alias.asname else ""), node.lineno)
    return found


def _module_source(parts: list[str], known: set[str]) -> str | None:
    if not parts or not all(part.isidentifier() for part in parts):
        return None
    stem = "/".join(parts)
    return next((target for target in (stem + ".py", stem + "/__init__.py")
                 if target in known), None)


def _resolved_file_imports(contents: bytes, path: str,
                           known: set[str]) -> dict[str, int]:
    """AST-confirmed file targets in this checkout, never dynamic callbacks."""
    tree = ast.parse(contents.decode("utf-8-sig"), filename=path)
    resolved: dict[str, int] = {}
    package = path.removesuffix(".py").split("/")[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            groups = [alias.name.split(".") for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                if node.level > len(package):
                    continue
                origin = package[:len(package) - node.level + 1]
            else:
                origin = []
            if node.module:
                origin += node.module.split(".")
            # Prefer actual imported submodules when resolvable. Treat a
            # package __init__ as the target only for imported attributes
            # that have no matching local module; do not invent a second
            # parent-package edge for "from . import helper".
            groups = []
            for alias in node.names:
                if alias.name == "*" or not alias.name.isidentifier():
                    groups.append(origin)
                    continue
                child = [*origin, alias.name]
                groups.append(child if _module_source(child, known) else origin)
            if not groups:
                groups = [origin]
        else:
            continue
        for group in groups:
            target = _module_source(group, known)
            if target is not None and target != path:
                resolved.setdefault(target, node.lineno)
    return resolved


def changed_imports(root: Path, commit_sha: str, paths: list[str],
                    *, tracked_sources: set[str] | None = None) -> dict[str, Any]:
    """Read only small changed Python sources and their Git baseline versions."""
    candidates = [path for path in paths if path.endswith(".py")]
    inventory_unavailable = False
    try:
        inventory = set(tracked_sources) if tracked_sources is not None else {
            item.decode("utf-8", "replace").replace("\\", "/")
            for item in _git(root, "ls-files", "-z", "--", "*.py").split(b"\0")
            if item
        }
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        inventory, inventory_unavailable = set(), True
    # Include safe untracked changed sources so a newly created local module
    # can be represented as an import target before the first git add.
    for name in candidates:
        relative = Path(name)
        candidate = root / relative
        if (not relative.is_absolute() and ".." not in relative.parts
                and "\\" not in name and candidate.is_file()
                and not candidate.is_symlink()
                and candidate.resolve().is_relative_to(root)):
            inventory.add(name)
    out: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for path in candidates[:MAX_PYTHON_FILES]:
        relative = Path(path)
        original = root / relative
        target = original.resolve()
        if (relative.is_absolute() or ".." in relative.parts or "\\" in path or
                not target.is_relative_to(root) or not target.is_file() or original.is_symlink()):
            errors.append({"path": path, "reason": "Deleted, missing or unsafe Python source."})
            continue
        try:
            if target.stat().st_size > MAX_SOURCE_BYTES:
                errors.append({"path": path, "reason": "Source exceeds local scan budget."})
                continue
            contents = target.read_bytes()
            current = _direct_imports(contents, path)
            linked_now = _resolved_file_imports(contents, path, inventory)
        except (OSError, UnicodeError, SyntaxError, ValueError) as exc:
            errors.append({"path": path, "reason": f"Current source could not be parsed: {type(exc).__name__}"})
            continue
        try:
            old = subprocess.run(
                ["git", "show", f"{commit_sha}:{path}"],
                cwd=root, capture_output=True, timeout=8, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            errors.append({"path": path, "reason": "Baseline Git source could not be read."})
            continue
        if old.returncode == 0:
            if len(old.stdout) > MAX_SOURCE_BYTES:
                errors.append({"path": path, "reason": "Baseline source exceeds scan budget."})
                continue
            try:
                previous = _direct_imports(old.stdout, path)
                linked_before = _resolved_file_imports(old.stdout, path, inventory)
            except (UnicodeError, SyntaxError, ValueError) as exc:
                errors.append({"path": path, "reason": f"Baseline source could not be parsed: {type(exc).__name__}"})
                continue
            baseline_absent = False
        else:
            previous = {}
            linked_before = {}
            baseline_absent = True
        added = sorted(set(current) - set(previous))
        removed = sorted(set(previous) - set(current))
        linked_added = sorted(set(linked_now) - set(linked_before))
        linked_removed = sorted(set(linked_before) - set(linked_now))
        if added or removed or linked_added or linked_removed or baseline_absent:
            out.append({
                "path": path,
                "baseline_absent": baseline_absent,
                "added_imports": [{"statement": key, "line": current[key]}
                                  for key in added[:MAX_IMPORT_ROWS]],
                "removed_imports": [{"statement": key, "baseline_line": previous[key]}
                                    for key in removed[:MAX_IMPORT_ROWS]],
                "added_dependency_links": [{"target": value, "line": linked_now[value]}
                                           for value in linked_added[:MAX_IMPORT_ROWS]],
                "removed_dependency_links": [{"target": value, "baseline_line": linked_before[value]}
                                             for value in linked_removed[:MAX_IMPORT_ROWS]],
                "imports_truncated": (len(added) > MAX_IMPORT_ROWS or len(removed) > MAX_IMPORT_ROWS
                                      or len(linked_added) > MAX_IMPORT_ROWS or len(linked_removed) > MAX_IMPORT_ROWS),
                "evidence": "CURRENT_AST_VS_BASELINE_AST",
            })
    return {
        "status": "PARTIAL" if inventory_unavailable or len(candidates) > MAX_PYTHON_FILES or errors or
        any(row["imports_truncated"] for row in out) else "COMPLETE",
        "inspected_count": min(len(candidates), MAX_PYTHON_FILES),
        "python_file_count": len(candidates),
        "changes": out,
        "errors": errors[:MAX_PYTHON_FILES],
        "source_inventory_available": not inventory_unavailable,
        "truncated": len(candidates) > MAX_PYTHON_FILES,
        "limits": "Current-source AST import file links are an ephemeral review overlay (12 changed Python files, max 32 link additions/removals per file). No graph rebuild, runtime callbacks, Qt/reflective or complete coverage proof.",
    }


def change_snapshot(root: Path, graph_sha: str) -> dict[str, Any]:
    """Current tracked and untracked Git paths since Graphify's source commit."""
    root = root.resolve()
    if not isinstance(graph_sha, str) or not _SHA.fullmatch(graph_sha):
        return {"status": "BLOCKED", "reason": "Invalid Graphify commit identifier"}
    try:
        baseline = _git(root, "rev-parse", "--verify", graph_sha + "^{commit}").decode().strip()
        head = _git(root, "rev-parse", "--verify", "HEAD").decode().strip()
        # Git diff BASE compares the *current worktree* to that commit, including
        # later commits, staged files and unstaged tracked changes.
        changed = _git(root, "diff", "--name-only", "-z", baseline, "--").split(b"\0")
        untracked = _git(root, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0")
    except (OSError, subprocess.TimeoutExpired, RuntimeError, UnicodeError) as exc:
        return {"status": "BLOCKED", "reason": str(exc)}
    paths = sorted({
        raw.decode("utf-8", errors="replace").replace("\\", "/")
        for raw in [*changed, *untracked] if raw
    })
    # Compare direct source imports only for a bounded number of changed Python files.
    imports = changed_imports(root, baseline, paths)
    # Always disclose how many files are not displayed. No false absence claim.
    return {
        "status": "CHANGED" if paths else "CLEAN",
        "source_import_delta": imports,
        "graph_commit": baseline,
        "current_commit": head,
        "graph_stale": bool(paths),
        "changed_files": paths[:MAX_PATHS],
        "changed_count": len(paths),
        "truncated": len(paths) > MAX_PATHS,
        "reason": "Graphify edges are a snapshot; rebuild explicitly to update structural relationships."
        if paths else "No changed repository files since the Graphify snapshot.",
        "graph_rebuilt": False,
        "tests_executed": False,
    }


def handler_factory(html: str, provider: Callable[[], dict[str, Any]], touch: Callable[[], None] | None = None):
    """No arbitrary file serving or external interface exposure."""
    encoded = html.encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            host = self.headers.get("Host", "").split(":")[0].lower()
            if host not in {"localhost", "127.0.0.1"}:
                self.send_error(403, "Loopback host only")
                return
            path = self.path.split("?", 1)[0]
            if touch is not None and path in {"/", "/api/live", "/api/ping"}:
                touch()
            if path == "/":
                body, media, status = encoded, "text/html; charset=utf-8", 200
            elif path == "/api/ping":
                body, media, status = b'{"status":"ALIVE"}', "application/json; charset=utf-8", 200
            elif path == "/api/live":
                try:
                    snapshot = provider()
                    body = json.dumps(snapshot, ensure_ascii=False).encode("utf-8")
                    status = 200 if snapshot.get("status") != "BLOCKED" else 503
                except Exception:
                    body, status = b'{"status":"BLOCKED","reason":"Snapshot temporarily unavailable."}', 503
                media = "application/json; charset=utf-8"
            else:
                self.send_error(404, "Unknown endpoint")
                return
            self.send_response(status)
            self.send_header("Content-Type", media)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy",
                             "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                             "connect-src 'self'; img-src 'none'; base-uri 'none'; form-action 'none'")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    return Handler


def serve_graph_live(root: Path, *, port: int = 8765,
                     open_browser: bool = False) -> dict[str, Any]:
    from .doctor_graph_ui import export_interactive_graph

    if not 0 <= port <= 65535:
        raise ValueError("Invalid port")
    root = root.resolve()
    graph = export_interactive_graph(root, allow_stale=True)
    if graph.get("status") not in {"PASS", "REVIEW"}:
        return graph
    candidate = graph["candidate_sha"]
    html = Path(graph["path"]).read_text(encoding="utf-8")
    provider = lambda: change_snapshot(root, candidate)
    last_seen = [time.monotonic()]
    def touch() -> None:
        last_seen[0] = time.monotonic()

    with ThreadingHTTPServer(("127.0.0.1", port), handler_factory(html, provider, touch)) as server:
        server.daemon_threads = True
        server.timeout = 10
        url = f"http://127.0.0.1:{server.server_port}/"
        print(f"Doctor Graphify LIVE (on-focus): {url} (Ctrl+C or 180s idle to stop)", flush=True)
        if open_browser:
            webbrowser.open(url)
        try:
            while time.monotonic() - last_seen[0] < 180:
                server.handle_request()
        except KeyboardInterrupt:
            pass
    return {"status": "STOPPED", "graph_commit": candidate, "graph_rebuilt": False}
