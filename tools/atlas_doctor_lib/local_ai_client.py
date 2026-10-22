"""Optional LOCAL Ollama diagnostic client for Doctor; advisory results only.

Model text is never evidence of passing tests or certification. No shell tools,
filesystem writes, Git privileges or remote model endpoints are exposed here.
"""
from __future__ import annotations

import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .local_ai_evidence import (
    DiagnosticEnvelope, DiagnosticSuggestion, InvalidDiagnostic, parse_local_suggestion,
)

_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_MAX_OUTPUT = 256 * 1024


class LocalDoctorModelError(RuntimeError):
    pass


def _endpoint(base_url: str) -> str:
    if not isinstance(base_url, str):
        raise LocalDoctorModelError("invalid local model endpoint")
    parsed = urlsplit(base_url)
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}
            or parsed.username or parsed.password or parsed.path not in ("", "/")
            or parsed.query or parsed.fragment):
        raise LocalDoctorModelError("only a local Ollama endpoint is allowed")
    try:
        port = parsed.port
    except ValueError as exc:
        raise LocalDoctorModelError("invalid endpoint port") from exc
    if port is None or not 1 <= port <= 65535:
        raise LocalDoctorModelError("a local model port is required")
    return base_url.rstrip("/") + "/api/chat"


def diagnose_local(
    evidence: DiagnosticEnvelope,
    *,
    model: str,
    base_url: str = "http://127.0.0.1:11434",
    timeout: float = 30.0,
) -> DiagnosticSuggestion:
    """Request hypotheses/test IDs from Ollama without any privileged operation."""
    if not isinstance(evidence, DiagnosticEnvelope) or evidence.status != "ADVISORY_ONLY":
        raise LocalDoctorModelError("invalid advisory input")
    if not isinstance(model, str) or not _MODEL.fullmatch(model):
        raise LocalDoctorModelError("invalid local model name")
    if not isinstance(timeout, (int, float)) or not 0 < timeout <= 120:
        raise LocalDoctorModelError("invalid timeout")
    endpoint = _endpoint(base_url)
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "keep_alive": 0,
        "options": {"temperature": 0, "num_predict": 256},
        "messages": [
            {"role": "system", "content": (
                "Analyze bounded technical evidence, suggest possible root causes and "
                "relevant test identifiers. Never claim PASS, FAIL or certification. "
                "Reply JSON object with only hypothesis (text) and "
                "recommended_test_ids (array of test IDs)."
            )},
            {"role": "user", "content": json.dumps(evidence.to_payload(), sort_keys=True)},
        ],
    }
    request = Request(endpoint, data=json.dumps(payload).encode("utf-8"), method="POST",
                      headers={"Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urlopen(request, timeout=float(timeout)) as response:
            if response.status != 200:
                raise LocalDoctorModelError("local model request failed")
            # Redirects must never change this from a local-only request.
            if _endpoint(response.geturl().removesuffix("/api/chat")) != endpoint:
                raise LocalDoctorModelError("local model response redirected")
            raw = response.read(_MAX_OUTPUT + 1)
        if len(raw) > _MAX_OUTPUT:
            raise LocalDoctorModelError("local model response too large")
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise LocalDoctorModelError("malformed Ollama response")
        message = result.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise LocalDoctorModelError("missing Ollama message")
        suggestion = json.loads(message["content"])
        return parse_local_suggestion(suggestion)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, InvalidDiagnostic) as exc:
        raise LocalDoctorModelError("local model unavailable or invalid advisory response") from exc
