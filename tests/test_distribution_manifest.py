"""Update protocol contract tests; no Qt, network or Windows dependencies."""
import hashlib
import json
from pathlib import Path

import pytest

from app.distribution.manifest import ManifestError, parse_manifest, verify_file


def payload(**changes):
    doc = dict(app_version="1.2.3", data_version="2026.10", schema_version=1,
               source_sha="a" * 64,
               files=[dict(path="app/atlas.exe", size=3, sha256=hashlib.sha256(b"abc").hexdigest())])
    doc.update(changes)
    return json.dumps(doc).encode()


def test_valid_manifest_and_file(tmp_path: Path):
    manifest = parse_manifest(payload())
    target = tmp_path / "atlas.exe"
    target.write_bytes(b"abc")
    assert verify_file(target, manifest.files[0])
    target.write_bytes(b"abd")
    assert not verify_file(target, manifest.files[0])


@pytest.mark.parametrize("path", ["../escape", "/absolute", "C:/drive", "app/../escape",
                                   "app//double", "app\\\\windows", "profiles/save.json",
                                   "logs/debug.txt", ".cache/cache.json"])
def test_reject_unsafe_paths(path):
    with pytest.raises(ManifestError):
        parse_manifest(payload(files=[dict(path=path, size=0, sha256="a" * 64)]))


def test_reject_case_insensitive_duplicate():
    with pytest.raises(ManifestError):
        parse_manifest(payload(files=[dict(path=p, size=0, sha256="a" * 64)
                                      for p in ("App/A.exe", "app/a.exe")]))


@pytest.mark.parametrize("changes", [{"schema_version": True}, {"source_sha": "x"},
                                      {"files": [{"path": "app/a", "size": -1, "sha256": "a" * 64}]},
                                      {"app_version": "../../bad"}])
def test_reject_invalid_contract(changes):
    with pytest.raises(ManifestError):
        parse_manifest(payload(**changes))
