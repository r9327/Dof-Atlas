"""Supplemental Windows-only certification of the published installed binaries.

This test driver is kept on a certification branch. It never publishes, patches
the application, or treats the tester's Python environment as the user runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

from app.distribution.install import active_executable, read_state, slot_path, install_release, mark_healthy
from app.distribution.install_location import set_runtime_root, runtime_root
from app.distribution.manifest import ReleaseFile, verify_file, valid_source_sha, parse_manifest
from app.distribution.release_client import latest_release, UpdateError, RemoteRelease, download_archive, _read_limited
from app.distribution.user_data import prepare_user_data
from scripts.windows.probe_public_release import (
    _ci_release_metadata, download_public_setup, verify_frozen_setup,
    verify_published_digests, probe_parts,
)
from scripts.windows.quest_assets import read_lock, RELATIVE_ROOT


def require(condition: bool, message: str) -> None:
    if not condition:
        raise UpdateError(message)


def verify_release_inventory(release, source_root: Path) -> dict:
    """Reject an incomplete public bundle before starting a multi-GB install."""
    lock = read_lock(source_root)
    files = {entry.path: entry for entry in release.manifest.files}
    for name, pin in lock["assets"].items():
        path = (Path("AtlasApp/_internal") / RELATIVE_ROOT / name).as_posix()
        entry = files.get(path)
        require(entry is not None and entry.size == pin["size"]
                and entry.sha256 == pin["sha256"], "Public locked JSON missing/corrupt: " + name)
    require("AtlasApp/_internal/data/bootstrap/craft_seed.sqlite" in files,
            "Public Craft seed is missing")
    return lock


def close_application(executable: Path, env: dict[str, str], *, verify_equipment: bool = False) -> dict:
    """Click the real Quitter button, then require normal process termination."""
    command = r'''
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$processes = @(Get-Process AtlasApp -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -eq $env:ATLAS_E2E_EXECUTABLE -and $_.MainWindowHandle -ne 0
})
if ($processes.Count -ne 1) { throw "Expected exactly one installed AtlasApp process" }
$appProcess = $processes[0]
$null = $appProcess.Handle
$appProcess.Refresh()
$equipmentTested = $false
$root = [System.Windows.Automation.AutomationElement]::RootElement
$processCondition = New-Object System.Windows.Automation.PropertyCondition -ArgumentList @(
    [System.Windows.Automation.AutomationElement]::ProcessIdProperty, $appProcess.Id)
$initialWindows = @($root.FindAll([System.Windows.Automation.TreeScope]::Children, $processCondition) |
    ForEach-Object { @{name=$_.Current.Name; enabled=$_.Current.IsEnabled;
                     handle=$_.Current.NativeWindowHandle; class=$_.Current.ClassName} })
$readyDeadline = [DateTime]::UtcNow.AddSeconds(180)
$readyStarted = [DateTime]::UtcNow
$mainEnabled = $false
while ([DateTime]::UtcNow -lt $readyDeadline) {
    $appProcess.Refresh()
    if ($appProcess.HasExited) { throw 'Atlas exited during startup preparation' }
    $appElement = [System.Windows.Automation.AutomationElement]::FromHandle($appProcess.MainWindowHandle)
    if ($null -ne $appElement -and $appElement.Current.IsEnabled) {
        $mainEnabled = $true; break
    }
    Start-Sleep -Milliseconds 250
}
if (-not $mainEnabled) {
    throw ('Startup main window remained disabled: ' + ($initialWindows | ConvertTo-Json -Compress))
}
$startupWaitSeconds = ([DateTime]::UtcNow - $readyStarted).TotalSeconds
if ($env:ATLAS_E2E_TEST_EQUIPMENT -eq '1') {
    $appElement = [System.Windows.Automation.AutomationElement]::FromHandle($appProcess.MainWindowHandle)
    $stuffsCondition = New-Object System.Windows.Automation.AndCondition -ArgumentList @(
        (New-Object System.Windows.Automation.PropertyCondition -ArgumentList @(
            [System.Windows.Automation.AutomationElement]::NameProperty, 'Stuffs')),
        (New-Object System.Windows.Automation.PropertyCondition -ArgumentList @(
            [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
            [System.Windows.Automation.ControlType]::Button))
    )
    $stuffs = $appElement.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $stuffsCondition)
    if ($null -eq $stuffs) { throw 'Real equipment navigation button missing' }
    $stuffs.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
    $equipmentDeadline = [DateTime]::UtcNow.AddSeconds(60)
    $huzCondition = New-Object System.Windows.Automation.PropertyCondition -ArgumentList @(
        [System.Windows.Automation.AutomationElement]::NameProperty, 'Ouvrir Huzounet dans le navigateur')
    $huz = $null
    while ([DateTime]::UtcNow -lt $equipmentDeadline) {
        $huz = $appElement.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $huzCondition)
        if ($null -ne $huz -and $huz.Current.IsEnabled) { break }
        Start-Sleep -Milliseconds 250
    }
    if ($null -eq $huz -or -not $huz.Current.IsEnabled) { throw 'Actual Equipment page did not become ready' }
    $equipmentTested = $true
}
$closeDeadline = [DateTime]::UtcNow.AddSeconds(30)
$closeRequested = $false
while ([DateTime]::UtcNow -lt $closeDeadline) {
    $appProcess.Refresh()
    if ($appProcess.HasExited) { throw 'Atlas exited before the normal close request' }
    if ($appProcess.CloseMainWindow()) { $closeRequested = $true; break }
    Start-Sleep -Milliseconds 250
}
if (-not $closeRequested) {
    $currentWindows = @($root.FindAll([System.Windows.Automation.TreeScope]::Children, $processCondition) |
        ForEach-Object { @{name=$_.Current.Name; enabled=$_.Current.IsEnabled;
                         handle=$_.Current.NativeWindowHandle; class=$_.Current.ClassName} })
    throw ('Atlas main window cannot be closed. Initial: ' +
        ($initialWindows | ConvertTo-Json -Compress) + '; Current: ' +
        ($currentWindows | ConvertTo-Json -Compress))
}
$quit = $null
$deadline = [DateTime]::UtcNow.AddSeconds(30)
$root = [System.Windows.Automation.AutomationElement]::RootElement
$condition = New-Object System.Windows.Automation.AndCondition -ArgumentList @(
    (New-Object System.Windows.Automation.PropertyCondition -ArgumentList @(
        [System.Windows.Automation.AutomationElement]::NameProperty, 'Quitter')),
    (New-Object System.Windows.Automation.PropertyCondition -ArgumentList @(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        [System.Windows.Automation.ControlType]::Button))
)
while ([DateTime]::UtcNow -lt $deadline) {
    $buttons = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condition)
    foreach ($button in $buttons) {
        if ($button.Current.ProcessId -eq $appProcess.Id) { $quit = $button; break }
    }
    if ($null -ne $quit) { break }
    Start-Sleep -Milliseconds 250
}
if ($null -eq $quit) { throw "Real Atlas Quitter button not found" }
$invoke = $quit.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
$invoke.Invoke()
if (-not $appProcess.WaitForExit(60000)) { throw "Atlas did not terminate normally" }
if ($appProcess.ExitCode -ne 0) { throw "Atlas exit code: $($appProcess.ExitCode)" }
$deadline = [DateTime]::UtcNow.AddSeconds(60)
do {
    $workers = @(Get-Process AtlasApp -ErrorAction SilentlyContinue | Where-Object {
        $_.Path -eq $env:ATLAS_E2E_EXECUTABLE
    })
    if ($workers.Count -eq 0) { break }
    Start-Sleep -Milliseconds 250
} while ([DateTime]::UtcNow -lt $deadline)
if ($workers.Count -ne 0) { throw 'Frozen Atlas workers remained after normal GUI exit' }
@{pid=$appProcess.Id; exit_code=$appProcess.ExitCode; action='Quitter'; remaining_workers=0;
  equipment_entry=$equipmentTested; startup_wait_seconds=$startupWaitSeconds;
  initial_windows=$initialWindows} | ConvertTo-Json -Compress -Depth 4
'''
    child_env = dict(env, ATLAS_E2E_EXECUTABLE=str(executable),
                     ATLAS_E2E_TEST_EQUIPMENT="1" if verify_equipment else "0")
    powershell = Path(env["SYSTEMROOT"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    result = subprocess.run(
        [str(powershell), "-NoProfile", "-NonInteractive", "-Command", command],
        env=child_env, capture_output=True, text=True, errors="replace", timeout=440,
    )
    require(result.returncode == 0, "Normal GUI shutdown failed: " + result.stderr[-1500:])
    return json.loads(result.stdout)


def launch(launcher: Path, env: dict[str, str], *, timeout: int = 2700) -> None:
    # Do not capture pipes inherited by the child GUI: its lifetime outlasts
    # the launcher, and pipe EOF would otherwise wait for the GUI to exit.
    result = subprocess.run(
        [str(launcher), "--atlas-auto-install"], cwd=launcher.parent, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout,
    )
    require(result.returncode == 0, f"Published launcher failed: {result.returncode}")


def interrupt_download(launcher: Path, root: Path, env: dict[str, str]) -> list[dict]:
    process = subprocess.Popen(
        [str(launcher), "--atlas-auto-install"], cwd=launcher.parent, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    stopped = False
    try:
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            partials = [{"name": str(p.relative_to(root)), "size": p.stat().st_size}
                        for p in (root / "downloads").rglob("*.download") if p.is_file()]
            if any(p["size"] >= 1024 * 1024 for p in partials):
                require(not read_state(root).get("active"),
                        "Cannot interrupt after application activation")
                powershell = Path(env["SYSTEMROOT"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
                check = subprocess.run(
                    [str(powershell), "-NoProfile", "-NonInteractive", "-Command", r'''
$ErrorActionPreference = 'Stop'
$windows = @(Get-Process DofusAtlas -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -eq $env:ATLAS_E2E_LAUNCHER -and $_.MainWindowHandle -ne 0 -and
    $_.MainWindowTitle.Contains('Dofus Atlas')
})
if ($windows.Count -ne 1) { throw 'Published launcher UI is missing during real download' }
$windows[0].MainWindowTitle
'''], env=dict(env, ATLAS_E2E_LAUNCHER=str(launcher)),
                    capture_output=True, text=True, errors="replace", timeout=30,
                )
                require(check.returncode == 0, "Public launcher GUI was not visible: " + check.stderr[-500:])
                partials.append({"launcher_window": check.stdout.strip()})
                taskkill = Path(env["SYSTEMROOT"]) / "System32/taskkill.exe"
                result = subprocess.run(
                    [str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True, timeout=30,
                )
                require(result.returncode == 0, "Could not interrupt launcher process tree")
                process.wait(timeout=30)
                stopped = True
                return partials
            require(process.poll() is None, "Launcher exited before download interruption")
            time.sleep(0.25)
        raise UpdateError("No real partial public download observed")
    finally:
        if not stopped and process.poll() is None:
            taskkill = Path(env["SYSTEMROOT"]) / "System32/taskkill.exe"
            subprocess.run([str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                           capture_output=True, timeout=30, check=False)
            process.wait(timeout=30)


def certify(source_sha: str, source_root: Path, report: dict) -> None:
    require(os.name == "nt", "Installed binary certification requires Windows")
    valid_source_sha(source_sha)
    release = latest_release()
    require(release.manifest.source_sha == source_sha, "Public latest SHA differs from target")
    actual_source = subprocess.run(["git", "-C", str(source_root), "rev-parse", "HEAD"],
                                   capture_output=True, text=True, check=True).stdout.strip()
    require(actual_source == source_sha, "Tester lock checkout is not the certified source SHA")
    lock = verify_release_inventory(release, source_root)
    report.update(source_sha=source_sha, release=release.tag,
                  archive_size=release.archive_size, stages={})
    stages = report["stages"]
    metadata = _ci_release_metadata()
    require(metadata.get("tag_name") == release.tag and not metadata.get("draft")
            and not metadata.get("prerelease"), "Stable public metadata mismatch")
    verify_published_digests(metadata, release)
    stages["public_parts"] = probe_parts(release)
    with tempfile.TemporaryDirectory(prefix="atlas-published-setup-") as folder:
        setup = download_public_setup(metadata, release, Path(folder))
        verify_frozen_setup(setup, release)
    stages["public_setup"] = "PASS"

    base = Path(os.environ["RUNNER_TEMP"])
    root = base / "Atlas custom install — espace et accent"
    require(not root.exists(), "Custom installation root must be new")
    root = set_runtime_root(root)
    require(runtime_root() == root, "Custom install location was not persisted")
    local = Path(os.environ["LOCALAPPDATA"])
    launcher = local / "Programs/DofusAtlas/DofusAtlas.exe"
    user = local / "DofusAtlas/user"
    require(not user.exists(), "First installation requires no existing user cache")
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM="windows", QT_ACCESSIBILITY="1",
               QTWEBENGINE_CHROMIUM_FLAGS="--disable-gpu --no-sandbox",
               QTWEBENGINE_DISABLE_SANDBOX="1")
    # Only Windows OS paths are available to the public EXEs, not the runner's Python.
    env["PATH"] = str(Path(env["SYSTEMROOT"]) / "System32") + os.pathsep + env["SYSTEMROOT"]
    stages["interrupted_download"] = interrupt_download(launcher, root, env)
    launch(launcher, env)
    state = read_state(root)
    require(state.get("source_sha") == source_sha and state.get("active")
            and not state.get("pending"), "Installed state is not healthy for exact target SHA")
    executable = active_executable(root)
    require(executable is not None, "Installed executable is absent")
    stages["first_shutdown"] = close_application(executable, env, verify_equipment=True)
    installed = slot_path(root, state["active"])
    for entry in release.manifest.files:
        require(verify_file(installed / entry.path, entry),
                "Installed manifest file invalid: " + entry.path)
    stages["installed_files_verified"] = len(release.manifest.files)
    mandatory = []
    for name, info in lock["assets"].items():
        asset = executable.parent / "_internal" / RELATIVE_ROOT / name
        require(verify_file(asset, ReleaseFile(name, info["size"], info["sha256"])),
                "Installed locked JSON missing/corrupt: " + name)
        mandatory.append({"name": name, "size": info["size"], "sha256": info["sha256"]})
    stages["quest_sources"] = mandatory
    stages["quest_source_tag"] = lock["tag"]

    worker_user = base / "Atlas worker empty user"
    require(not worker_user.exists(), "Worker certification requires an empty user root")
    prepare_user_data(executable, worker_user)
    worker_env = dict(env, DOFUS_ATLAS_USER_ROOT=str(worker_user))
    commands = (
        ("quest_worker", ["-m", "app.quest_catalog_details", "--ensure-cache"]),
        ("quest_index", ["--atlas-quest-smoke"]),
        ("package", ["--atlas-package-smoke"]),
        ("guide", ["--atlas-domain-smoke", "guide"]),
        ("success_worker", ["-m", "app.modules.encyclopedia.providers.memory_bound_achievement_provider",
                            "--ensure-compact-cache"]),
        ("success", ["--atlas-domain-smoke", "success"]),
        ("success_detail", ["--atlas-success-detail-smoke"]),
        ("items_worker", ["-m", "app.modules.encyclopedia.providers.dofus_item_provider",
                          "--ensure-guide-index"]),
        ("craft", ["--atlas-craft-smoke"]),
        ("map_sqlite", ["--atlas-map-state-smoke"]),
    )
    stages["frozen_commands"] = []
    for name, args in commands:
        result = subprocess.run([str(executable), *args], cwd=base, env=worker_env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=360)
        stages["frozen_commands"].append({"name": name, "args": args, "exit_code": result.returncode})
        require(result.returncode == 0, f"Real installed command failed: {name}: {result.returncode}")

    marker = user / "e2e-personal-settings.json"
    marker.write_bytes(b'{"preserve":"personal settings"}')
    downloads_before = {str(p.relative_to(root)): (p.stat().st_size, p.stat().st_mtime_ns)
                        for p in (root / "downloads").rglob("*") if p.is_file()}
    launch(launcher, env, timeout=180)
    require(read_state(root).get("source_sha") == source_sha,
            "Source SHA changed during launcher relaunch")
    stages["second_shutdown"] = close_application(executable, env)
    require(marker.read_bytes() == b'{"preserve":"personal settings"}', "Personal data was changed")
    downloads_after = {str(p.relative_to(root)): (p.stat().st_size, p.stat().st_mtime_ns)
                       for p in (root / "downloads").rglob("*") if p.is_file()}
    require(downloads_before == downloads_after, "Relaunch downloaded or modified archives unnecessarily")
    # Damage only closed files in this disposable runner. Same-length JSON
    # corruption must be found even when the executable itself is intact.
    stages["repairs"] = []
    for name, target in (
        ("executable", executable),
        ("quest_source", executable.parent / "_internal" / RELATIVE_ROOT / "quest_categories.json"),
    ):
        with target.open("r+b") as damaged:
            damaged.write(b"!")
        launch(launcher, env, timeout=900)
        repaired = active_executable(root)
        require(repaired == executable, "Launcher did not repair the selected installation")
        require(read_state(root).get("source_sha") == source_sha and not read_state(root).get("pending"),
                "Repaired installation is not healthy for exact target SHA")
        shutdown = close_application(executable, env)
        for entry in release.manifest.files:
            require(verify_file(installed / entry.path, entry), "Repair left invalid file: " + entry.path)
        require(marker.read_bytes() == b'{"preserve":"personal settings"}',
                "Repair modified personal settings")
        stages["repairs"].append({"damaged_file": name, "shutdown": shutdown, "status": "PASS"})
    repaired_worker_user = base / "Atlas repaired empty worker user"
    require(not repaired_worker_user.exists(), "Post-repair Quest worker requires a new user root")
    prepare_user_data(executable, repaired_worker_user)
    result = subprocess.run(
        [str(executable), "-m", "app.quest_catalog_details", "--ensure-cache"], cwd=base,
        env=dict(env, DOFUS_ATLAS_USER_ROOT=str(repaired_worker_user)),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=360,
    )
    require(result.returncode == 0, "Actual Quest worker failed after JSON repair")
    stages.update(custom_install_path=str(root), relaunch="PASS", personal_data="PASS",
                  post_repair_quest_worker="PASS", no_unnecessary_download="PASS",
                  no_python_in_application_path=True)


def certify_upgrade(source_sha: str, source_root: Path, report: dict) -> None:
    """Restore a verified previous public install, then run the public updater.

    The previous payload is a test fixture of an already installed, closed
    application. Only the new public launcher performs the actual upgrade.
    """
    require(os.name == "nt", "Native public update certification requires Windows")
    valid_source_sha(source_sha)
    actual_source = subprocess.run(["git", "-C", str(source_root), "rev-parse", "HEAD"],
                                   capture_output=True, text=True, check=True).stdout.strip()
    require(actual_source == source_sha, "Tester lock checkout is not the target source SHA")
    release = latest_release()
    require(release.manifest.source_sha == source_sha, "Public latest SHA differs from upgrade target")
    verify_release_inventory(release, source_root)
    metadata = _ci_release_metadata()
    require(metadata.get("tag_name") == release.tag and not metadata.get("draft")
            and not metadata.get("prerelease"), "Stable upgrade metadata mismatch")
    verify_published_digests(metadata, release)
    report.update(source_sha=source_sha, release=release.tag, stages={})
    stages = report["stages"]

    # Immutable historical public fixture, verified live earlier in this mission.
    old_tag = "sha-e8ab23c925cb"
    old_sha = "e8ab23c925cbfe3606d876c79712f20ea09d46f4"
    base_url = "https://github.com/r9327/Dof-Atlas-App/releases/download/" + old_tag + "/"
    payload = _read_limited(base_url + "atlas-manifest.json", 32 * 1024 * 1024)
    require(hashlib.sha256(payload).hexdigest() ==
            "d1fecc4725d465d5ae7d5568e75adf4caed296fe8cdf91c6253fe7cac0d136d6",
            "Historical fixture manifest changed")
    old_manifest = parse_manifest(payload)
    require(old_manifest.source_sha == old_sha and bool(old_manifest.archive_parts),
            "Historical public fixture SHA or multipart layout mismatch")
    old = RemoteRelease(old_tag, "", old_manifest.archive_size, old_manifest,
                        part_urls=tuple(base_url + part.name for part in old_manifest.archive_parts))
    root = Path(os.environ["RUNNER_TEMP"]) / "Atlas native public update — custom folder"
    require(not root.exists(), "Native update fixture root must be new")
    root = set_runtime_root(root)
    local = Path(os.environ["LOCALAPPDATA"])
    user = local / "DofusAtlas/user"
    require(not user.exists(), "Native update fixture requires no preexisting user cache")
    archive = download_archive(old, root / "downloads")
    install_release(root, archive, old_manifest)
    mark_healthy(root)
    old_state = read_state(root)
    previous_executable = active_executable(root)
    require(old_state.get("source_sha") == old_sha and previous_executable is not None,
            "Verified previous public fixture was not installed")
    stages["previous_public_fixture"] = {
        "source_sha": old_sha, "release": old_tag,
        "archive_bytes": old_manifest.archive_size, "archive_sha256": old_manifest.archive_sha256,
        "verified_installed_files": len(old_manifest.files),
        "fixture_method": "canonical installer, all public file hashes verified; previous GUI not rerun",
    }
    # Free only the verified input archive from this disposable fixture.
    # The entire previous installation stays available for real rollback.
    archive.unlink()
    user.mkdir(parents=True)
    marker = user / "e2e-personal-settings.json"
    marker.write_bytes(b'{"previous_user_setting":true}')
    with tempfile.TemporaryDirectory(prefix="atlas-update-public-setup-") as folder:
        setup = download_public_setup(metadata, release, Path(folder))
        verify_frozen_setup(setup, release)
    require(runtime_root() == root, "Setup overwrote the existing custom installation location")
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM="windows", QT_ACCESSIBILITY="1",
               QTWEBENGINE_CHROMIUM_FLAGS="--disable-gpu --no-sandbox", QTWEBENGINE_DISABLE_SANDBOX="1")
    env["PATH"] = str(Path(env["SYSTEMROOT"]) / "System32") + os.pathsep + env["SYSTEMROOT"]
    launcher = local / "Programs/DofusAtlas/DofusAtlas.exe"
    launch(launcher, env)
    state = read_state(root)
    require(state.get("source_sha") == source_sha and not state.get("pending"),
            "Actual public launcher did not activate the exact new source")
    require(state.get("previous") == old_state["active"] and previous_executable.is_file(),
            "Actual update did not retain the previous public version")
    executable = active_executable(root)
    require(executable is not None, "Updated public executable is absent")
    stages["updated_shutdown"] = close_application(executable, env, verify_equipment=True)
    installed = slot_path(root, state["active"])
    for entry in release.manifest.files:
        require(verify_file(installed / entry.path, entry), "Updated file is invalid: " + entry.path)
    require(marker.read_bytes() == b'{"previous_user_setting":true}', "Actual update lost personal settings")
    require(runtime_root() == root, "Actual update changed the selected installation location")
    worker_env = dict(env, DOFUS_ATLAS_USER_ROOT=str(user))
    for name, args in (("quest_worker", ["-m", "app.quest_catalog_details", "--ensure-cache"]),
                       ("quest_index", ["--atlas-quest-smoke"]), ("craft", ["--atlas-craft-smoke"])):
        result = subprocess.run([str(executable), *args], cwd=root.parent, env=worker_env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=360)
        require(result.returncode == 0, f"Updated frozen command failed: {name}: {result.returncode}")
        stages[name] = {"exit_code": result.returncode}
    stages.update(activated_source_sha=state["source_sha"], previous_slot_retained=state["previous"],
                  installed_files_verified=len(release.manifest.files), personal_data="PASS",
                  persisted_custom_path=str(root),
                  update_archives=[{"name": p.name, "size": p.stat().st_size}
                                   for p in (root / "downloads").glob("*.zip")])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--upgrade", action="store_true")
    args = parser.parse_args()
    report = {"schema_version": 1, "status": "FAILED"}
    try:
        action = certify_upgrade if args.upgrade else certify
        action(args.source_sha, args.source_root, report)
        report["status"] = "PASS"
    except (OSError, ValueError, UpdateError, subprocess.SubprocessError) as exc:
        report["error"] = str(exc)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
