from __future__ import annotations

"""Opt-in loopback-only status overlay for a fixed Graphify graph snapshot.

Updates tracked/untracked changed-file highlighting, NOT Graphify's AST edges.
No watcher thread, Qt import, rebuild, or full test suite in Atlas itself.
"""
import json
import re
import subprocess
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

MAX_PATHS = 200
_SHA = re.compile(r"^[0-9a-f]{7,40}$")


def _git(root: Path, *args: str) -> bytes:
    run = subprocess.run(
        ["git", *args], cwd=root, capture_output=True,
        check=False, timeout=10,
    )
    if run.returncode:
        raise RuntimeError(f"Git status unavailable: {run.returncode}")
    return run.stdout


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
    # Always disclose how many files are not displayed. No false absence claim.
    return {
        "status": "CHANGED" if paths else "CLEAN",
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


def handler_factory(html: str, provider: Callable[[], dict[str, Any]]):
    """No arbitrary file serving or external interface exposure."""
    encoded = html.encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            host = self.headers.get("Host", "").split(":")[0].lower()
            if host not in {"localhost", "127.0.0.1"}:
                self.send_error(403, "Loopback host only")
                return
            path = self.path.split("?", 1)[0]
            if path == "/":
                body, media, status = encoded, "text/html; charset=utf-8", 200
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
    graph = export_interactive_graph(root)
    if graph.get("status") != "PASS":
        return graph
    candidate = graph["candidate_sha"]
    html = Path(graph["path"]).read_text(encoding="utf-8")
    provider = lambda: change_snapshot(root, candidate)
    with ThreadingHTTPServer(("127.0.0.1", port), handler_factory(html, provider)) as server:
        server.daemon_threads = True
        url = f"http://127.0.0.1:{server.server_port}/"
        print(f"Doctor Graphify LIVE: {url}  (Ctrl+C to stop)", flush=True)
        if open_browser:
            webbrowser.open(url)
        try:
            server.serve_forever(poll_interval=0.5)
        except KeyboardInterrupt:
            pass
    return {"status": "STOPPED", "graph_commit": candidate, "graph_rebuilt": False}
