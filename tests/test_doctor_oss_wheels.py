from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from tools import doctor_oss_wheels as wheels


class _Response(io.BytesIO):
    def __init__(self, payload: dict, url: str):
        super().__init__(json.dumps(payload).encode("utf-8"))
        self.url = url

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class DoctorOssWheelsTests(unittest.TestCase):
    def test_import_and_non_windows_do_not_download_or_install(self):
        with (patch.object(wheels, "windows_313_x64", return_value=False),
              patch.object(wheels.subprocess, "run") as run,
              patch.object(wheels, "urlopen") as get):
            with self.assertRaises(RuntimeError):
                wheels.install_approved_wheels()
        run.assert_not_called()
        get.assert_not_called()
        self.assertEqual(wheels.PINS, {"ruff": "0.17.3",
                                       "zizmor": "1.30.1"})

    def test_metadata_must_prove_exact_filename_sha_and_origin(self):
        wheel = "ruff-0.17.3-py3-none-win_amd64.whl"
        url = "https://pypi.org/pypi/ruff/0.17.3/json"
        digest = hashlib.sha256(b"content").hexdigest()
        data = {"info": {"version": "0.17.3"}, "urls": [
            {"filename": wheel, "packagetype": "bdist_wheel",
             "digests": {"sha256": digest}, "yanked": False}]}
        with patch.object(wheels, "urlopen", return_value=_Response(data, url)) as fetch:
            actual = wheels.published_wheel_digest("ruff", "0.17.3", wheel)
        self.assertEqual(actual, digest)
        fetch.assert_called_once_with(url, timeout=15)
        for bad_data, bad_url in (
            ({**data, "info": {"version": "0.17.2"}}, url),
            ({**data, "urls": []}, url),
            ({**data, "urls": data["urls"] * 2}, url),
            ({**data, "urls": [{**data["urls"][0],
                               "digests": {"sha256": "bad"}}]}, url),
            (data, "https://untrusted.example/redirect"),
        ):
            with self.subTest(bad=bad_data, url=bad_url):
                with patch.object(wheels, "urlopen",
                                  return_value=_Response(bad_data, bad_url)):
                    with self.assertRaises(ValueError):
                        wheels.published_wheel_digest("ruff", "0.17.3", wheel)
        with patch.object(wheels, "urlopen") as fetch:
            with self.assertRaises(ValueError):
                wheels.published_wheel_digest("ruff", "0.17.3", "../evil.whl")
        fetch.assert_not_called()

    def test_exact_wheels_are_hash_checked_before_pip_install(self):
        filenames = ["ruff-0.17.3-py3-none-win_amd64.whl",
                     "zizmor-1.30.1-py3-none-win_amd64.whl"]
        data = {"ruff": b"ruff wheel bytes", "zizmor": b"zizmor wheel bytes"}
        digests = {name: hashlib.sha256(payload).hexdigest()
                   for name, payload in data.items()}
        calls = []

        def subprocess_fake(args, **options):
            calls.append((args, options))
            if "download" in args:
                folder = Path(args[args.index("--dest") + 1])
                for filename, name in zip(filenames, data):
                    (folder / filename).write_bytes(data[name])
            elif "install" in args:
                req = Path(args[args.index("-r") + 1])
                text = req.read_text(encoding="ascii")
                for name, version in wheels.PINS.items():
                    self.assertIn(f"{name}=={version} --hash=sha256:{digests[name]}", text)
                self.assertIn("--no-index", args)
                self.assertIn("--require-hashes", args)
                self.assertIn("--no-deps", args)
                self.assertIn("--user", args)
            return subprocess.CompletedProcess(args, 0)

        with (patch.object(wheels, "windows_313_x64", return_value=True),
              patch.object(wheels, "published_wheel_digest",
                           side_effect=lambda name, *_: digests[name]) as hashes,
              patch.object(wheels.subprocess, "run", side_effect=subprocess_fake)):
            report = wheels.install_approved_wheels()
        self.assertEqual(report["status"], "INSTALLED_NOT_QUALIFIED")
        self.assertEqual([x["package"] for x in report["wheels"]],
                         ["ruff", "zizmor"])
        self.assertFalse(report["windows_runtime_verified"])
        self.assertEqual(len(calls), 2)
        self.assertEqual(hashes.call_count, 2)
        for args, kw in calls:
            self.assertIn("--isolated", args)
            self.assertIn("--no-deps", args)
            self.assertTrue(kw["check"])

    def test_bad_download_hash_never_reaches_install(self):
        calls = []
        def download_fake(args, **options):
            calls.append(args)
            folder = Path(args[args.index("--dest") + 1])
            (folder / "ruff-0.17.3-py3-none-win_amd64.whl").write_bytes(b"valid")
            (folder / "zizmor-1.30.1-py3-none-win_amd64.whl").write_bytes(b"tampered")
        with (patch.object(wheels, "windows_313_x64", return_value=True),
              patch.object(wheels, "published_wheel_digest",
                           return_value=hashlib.sha256(b"valid").hexdigest()),
              patch.object(wheels.subprocess, "run", side_effect=download_fake)):
            with self.assertRaises(ValueError):
                wheels.install_approved_wheels()
        self.assertEqual(len(calls), 1)
        self.assertIn("download", calls[0])
        self.assertNotIn("install", calls[0])


if __name__ == "__main__":
    unittest.main()
