"""Native macOS discovery/install. Commands are argv arrays, never shell strings."""
from __future__ import annotations
import json
import platform
import plistlib
import shutil
import subprocess
import tempfile
import urllib.parse
from pathlib import Path


class AutomationError(RuntimeError):
    pass


def run(argv, timeout=120, cwd=None):
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False, cwd=cwd)
    except FileNotFoundError as exc:
        raise AutomationError(f"missing_tool:{Path(argv[0]).name}") from exc
    except subprocess.TimeoutExpired as exc:
        raise AutomationError(f"command_timeout:{Path(argv[0]).name}") from exc
    if result.returncode:
        # Tool stderr can contain paths, account information or signing material.
        raise AutomationError(f"command_failed:{Path(argv[0]).name}:exit_{result.returncode}")
    return result.stdout


def doctor():
    names = ["xcodebuild", "xcrun", "python3", "node", "npm", "appium", "pymobiledevice3"]
    local_appium = Path(__file__).resolve().parents[1] / "node_modules/.bin/appium"
    versions = {"python": platform.python_version(), "host": platform.platform()}
    executables = {name: shutil.which(name) for name in names}
    if local_appium.is_file():
        executables["appium"] = str(local_appium)
    for name, args in [("xcodebuild", ["-version"]), ("node", ["--version"]), ("appium", ["--version"])]:
        if executables[name]:
            try:
                versions[name] = run([executables[name], *args], 30).strip()
            except AutomationError as exc:
                versions[name] = str(exc)
    driver = None
    if executables["appium"]:
        try:
            # Appium discovers npm-managed drivers from this package directory.
            data = json.loads(run([executables["appium"], "driver", "list", "--installed", "--json"],
                                  30, cwd=local_appium.parents[2]))
            driver = data.get("xcuitest", {}).get("version")
        except (AutomationError, ValueError):
            pass
    blockers = []
    if platform.system() != "Darwin" or not shutil.which("xcrun") or not shutil.which("xcodebuild"):
        blockers.append("macOS_with_Xcode_required")
    if not driver:
        blockers.append("local_Appium_XCUITest_driver_required")
    return {"platform": platform.system(), "versions": versions,
            "tools": {name: bool(executables[name]) for name in names},
            "xcuitest_version": driver, "physical_validation": "NOT_PERFORMED",
            "blockers": blockers}


class DeviceControl:
    def __init__(self, runner=run):
        self.runner = runner

    def command(self, args, timeout=120):
        with tempfile.TemporaryDirectory(prefix="madeira-devicectl-") as directory:
            output = Path(directory) / "result.json"
            self.runner(["xcrun", "devicectl", "--timeout", str(timeout),
                         "--json-output", str(output), *args], timeout + 10)
            try:
                data = json.loads(output.read_text())
            except (OSError, ValueError) as exc:
                raise AutomationError("invalid_devicectl_response") from exc
            if data.get("info", {}).get("outcome") != "success":
                raise AutomationError("devicectl_unsuccessful")
            return data.get("result", {})

    def devices(self):
        data = self.command(["list", "devices"], 30)
        if not isinstance(data.get("devices"), list):
            raise AutomationError("unsupported_device_schema")
        devices = []
        for raw in data["devices"]:
            hw, props, conn = (raw.get(k, {}) for k in
                               ("hardwareProperties", "deviceProperties", "connectionProperties"))
            devices.append({"identifier": raw.get("identifier"), "udid": hw.get("udid"),
                            "name": props.get("name"), "os_version": props.get("osVersionNumber"),
                            "model": hw.get("marketingName") or hw.get("productType"),
                            "device_type": hw.get("deviceType"), "platform": hw.get("platform"),
                            "transport": conn.get("transportType"), "tunnel": conn.get("tunnelState"),
                            "pairing": conn.get("pairingState"),
                            "developer_mode": props.get("developerModeStatus")})
        return devices

    def select(self, udid=None, transport=None):
        devices = self.devices()
        candidates = [d for d in devices if d["device_type"] == "iPad"
                      or str(d["model"]).startswith("iPad")]
        if udid:
            candidates = [d for d in candidates if udid in (d["udid"], d["identifier"])]
        else:
            candidates = [d for d in candidates if d["tunnel"] == "connected"]
        if len(candidates) != 1:
            raise AutomationError("select_one_connected_iPad_with_--udid")
        device = candidates[0]
        if not device["udid"]:
            raise AutomationError("device_missing_hardware_udid")
        if device["pairing"] not in ("paired",):
            raise AutomationError("device_pairing_requires_manual_check")
        if device["developer_mode"] != "enabled":
            raise AutomationError("developer_mode_requires_manual_check")
        if device["tunnel"] != "connected":
            raise AutomationError("device_disconnected_or_locked")
        if transport and device["transport"] != transport:
            raise AutomationError("device_transport_mismatch:requires_" + transport)
        return device

    def install_app(self, udid, app_path, bundle_id):
        path = Path(app_path).resolve()
        if path.suffix != ".app" or not path.is_dir():
            raise AutomationError("native_install_requires_signed_app_directory")
        try:
            with (path / "Info.plist").open("rb") as handle:
                actual = plistlib.load(handle).get("CFBundleIdentifier")
        except (OSError, plistlib.InvalidFileException) as exc:
            raise AutomationError("invalid_app_plist") from exc
        if actual != bundle_id:
            raise AutomationError("bundle_identifier_mismatch")
        # Check the installed bundle's actual URL, rather than guessing from
        # the executable name shared by multiple Madeira development apps.
        apps = self.command(["device", "info", "apps", "--device", udid,
                             "--bundle-id", bundle_id], 30)
        if not isinstance(apps.get("apps"), list):
            raise AutomationError("unsupported_installed_apps_schema")
        for installed in apps["apps"]:
            if installed.get("bundleIdentifier") != bundle_id:
                raise AutomationError("installed_app_identity_mismatch")
            url = installed.get("url")
            if not isinstance(url, str) or not url:
                raise AutomationError("installed_app_url_unavailable")
            processes = self.command(["device", "info", "processes", "--device", udid], 30)
            if not isinstance(processes.get("runningProcesses"), list):
                raise AutomationError("unsupported_process_schema")
            prefix = urllib.parse.unquote(urllib.parse.urlparse(url).path).rstrip("/") + "/"
            for process in processes["runningProcesses"]:
                executable = process.get("executable")
                if not isinstance(executable, str):
                    raise AutomationError("unsupported_process_executable_schema")
                executable_path = urllib.parse.unquote(urllib.parse.urlparse(executable).path)
                if executable_path.startswith(prefix):
                    raise AutomationError("install_requires_target_app_stopped_to_preserve_active_games")
        self.command(["device", "install", "app", "--device", udid, str(path)], 300)
        return {"installed": True, "bundle_id": bundle_id}

    def require_unlocked(self, udid):
        data = self.command(["device", "info", "lockState", "--device", udid], 30)
        if not isinstance(data.get("passcodeRequired"), bool):
            raise AutomationError("unsupported_device_lock_schema")
        if data["passcodeRequired"]:
            raise AutomationError("device_locked_requires_owner_unlock")

    def application_log(self, udid, bundle_id):
        # Pull exactly the app log, never a whole Documents directory or Steam data.
        with tempfile.TemporaryDirectory(prefix="madeira-log-") as directory:
            target = Path(directory) / "app.log"
            self.command(["device", "copy", "from", "--device", udid,
                          "--domain-type", "appDataContainer", "--domain-identifier", bundle_id,
                          "--source", "Documents/madeira-log.txt", "--destination", str(target)], 30)
            if not target.is_file():
                raise AutomationError("app_log_unavailable")
            with target.open("rb") as handle:
                handle.seek(0, 2)
                handle.seek(max(0, handle.tell() - 2_000_000))
                return diagnostic_events(handle.read().decode("utf-8", errors="replace"))

    def app_process_ids(self, udid, bundle_id):
        """Main-app processes only; its PlugIns contain separately running helpers."""
        apps = self.command(["device", "info", "apps", "--device", udid, "--bundle-id", bundle_id], 30)
        if not isinstance(apps.get("apps"), list) or len(apps["apps"]) != 1:
            raise AutomationError("probe_app_identity_unavailable")
        app = apps["apps"][0]
        if app.get("bundleIdentifier") != bundle_id or not isinstance(app.get("url"), str):
            raise AutomationError("probe_app_identity_mismatch")
        prefix = urllib.parse.unquote(urllib.parse.urlparse(app["url"]).path).rstrip("/") + "/"
        data = self.command(["device", "info", "processes", "--device", udid], 30)
        if not isinstance(data.get("runningProcesses"), list):
            raise AutomationError("unsupported_process_schema")
        found = []
        for p in data["runningProcesses"]:
            if not isinstance(p.get("executable"), str):
                raise AutomationError("unsupported_process_executable_schema")
            path = urllib.parse.unquote(urllib.parse.urlparse(p["executable"]).path)
            if Path(path).parent == Path(prefix):
                pid = p.get("processIdentifier")
                if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
                    raise AutomationError("unsupported_process_identifier")
                found.append(pid)
        return found

    def terminate_probe_process(self, udid, bundle_id, pid):
        """Stop only a fresh standalone probe whose PID came from its status.

        An attached debugger can make XCTest termination stall. Never use this
        for normal games, guessed PIDs or a preexisting process.
        """
        if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
            raise AutomationError("invalid_probe_process_identity")
        pids = self.app_process_ids(udid, bundle_id)
        if pids and pids != [pid]:
            raise AutomationError("probe_process_identity_changed")
        if pids:
            self.command(["device", "process", "terminate", "--device", udid, "--pid", str(pid), "--kill"], 30)
        if self.app_process_ids(udid, bundle_id):
            raise AutomationError("probe_process_still_running")
        return {"backend": "devicectl", "confirmed_stopped": True}

    def launch_probe_process(self, udid, bundle_id, *, environment=None):
        # A bounded experiment surface, never arbitrary credentials/loader vars.
        allowed = {key: {'0','1'} for key in ('MADEIRA_SRV_COALESCE','MADEIRA_PROFILE_THREADS','MADEIRA_PROFILE_XP','MADEIRA_PROFILE_STACKS','DXMT_IOS_CACHE_DIR')}
        allowed['FEX_MAXINST'] = {'500','1000','5000'}
        if environment is not None and (not isinstance(environment,dict) or any(k not in allowed or not isinstance(v,str) or v not in allowed[k] for k,v in environment.items())):
            raise AutomationError('invalid_experiment_environment')
        if self.app_process_ids(udid, bundle_id):
            raise AutomationError("jit_probe_requires_Madeira_stopped_before_start")
        args = ["device", "process", "launch", "--device", udid]
        if environment: args.extend(["--environment-variables", json.dumps(environment,separators=(',',':'))])
        self.command([*args, bundle_id, "--", "--madeira-automation"], 30)
        pids = self.app_process_ids(udid, bundle_id)
        if len(pids) != 1:
            raise AutomationError("probe_launch_process_identity_unavailable")
        return pids[0]


def diagnostic_events(text):
    """Export only fixed events; no free text, paths, tokens, or account identifiers."""
    markers = {
        "FEX-Emu test PASSED: x86-64 code returned 42!": "fex_test_passed",
        "FEX-Emu test PASSED: x86-64 ELF exited with code 42": "fex_test_passed",
        "FEX-Emu test FAILED": "fex_test_failed",
        "JIT enabled and debugger attached.": "jit_attached",
        "[jit-debugger] attached=1": "jit_debugger_present",
        "[jit-debugger] attached=0": "jit_debugger_absent",
        "[frontend] graceful close requested": "game_close_requested",
    }
    return [{"event": name} for line in text.splitlines()
            for marker, name in markers.items() if marker in line]
