import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import plistlib
import threading

import pytest

from automation.controller.appium_controller import AppiumController, ELEMENT
from automation.controller.device import AutomationError, DeviceControl, diagnostic_events
from automation.controller.workflows import Run


def raw_device(udid="tablet", **overrides):
    data = {"identifier": "core-id", "hardwareProperties": {"udid": udid, "deviceType": "iPad",
            "productType": "iPad16,5", "platform": "iOS"},
            "deviceProperties": {"name": "Lab iPad", "osVersionNumber": "26.0", "developerModeStatus": "enabled"},
            "connectionProperties": {"pairingState": "paired", "tunnelState": "connected", "transportType": "wired"}}
    data["connectionProperties"].update(overrides)
    return data


def native_with(devices):
    def runner(argv, timeout):
        path = Path(argv[argv.index("--json-output") + 1])
        path.write_text(json.dumps({"info": {"outcome": "success"}, "result": {"devices": devices}}))
    return DeviceControl(runner)


def test_select_never_guesses_between_two_ipads():
    native = native_with([raw_device("one"), raw_device("two")])
    with pytest.raises(AutomationError, match="select_one"):
        native.select()
    assert native.select("two")["udid"] == "two"


def test_paired_disconnected_device_is_not_connected():
    with pytest.raises(AutomationError, match="disconnected"):
        native_with([raw_device(tunnelState="disconnected")]).select("tablet")


def test_missing_device_fails_without_guessing():
    with pytest.raises(AutomationError, match="select_one_connected"):
        native_with([]).select()


def test_unknown_developer_mode_requires_check():
    raw = raw_device()
    raw["deviceProperties"].pop("developerModeStatus")
    with pytest.raises(AutomationError, match="developer_mode"):
        native_with([raw]).select()


@pytest.mark.parametrize("locked", [False, True, None])
def test_unlock_gate_does_not_confuse_unlocked_since_boot_with_current_lock(locked):
    def runner(argv, timeout):
        result = {"passcodeRequired": locked, "unlockedSinceBoot": True}
        Path(argv[argv.index("--json-output") + 1]).write_text(json.dumps({"info":{"outcome":"success"},"result":result}))
    native = DeviceControl(runner)
    if locked is False:
        native.require_unlocked("tablet")
    else:
        with pytest.raises(AutomationError, match="owner_unlock" if locked else "lock_schema"):
            native.require_unlocked("tablet")


def test_network_device_does_not_pass_USB_preflight():
    native = native_with([raw_device(transportType="localNetwork")])
    with pytest.raises(AutomationError, match="transport_mismatch"):
        native.select("tablet", transport="wired")
    assert native.select("tablet", transport="localNetwork")["transport"] == "localNetwork"


def test_install_checks_bundle_before_calling_device(tmp_path):
    app = tmp_path / "Madeira.app"
    app.mkdir()
    (app / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "wrong"}))
    def unexpected(*args):
        pytest.fail("must not install wrong app")
    with pytest.raises(AutomationError, match="mismatch"):
        DeviceControl(unexpected).install_app("tablet", app, "com.willfaust.madeora")


def test_install_argv_preserves_spaces(tmp_path):
    app = tmp_path / "signed build.app"
    app.mkdir()
    (app / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "test.madeira"}))
    calls = []
    def runner(argv, timeout):
        calls.append(argv)
        Path(argv[argv.index("--json-output") + 1]).write_text('{"info":{"outcome":"success"},"result":{"apps":[]}}')
    DeviceControl(runner).install_app("tablet", app, "test.madeira")
    assert calls[-1][-1] == str(app)
    assert not any("uninstall" in call for call in calls)


def test_install_refuses_running_target_without_stopping_or_replacing_it(tmp_path):
    app = tmp_path / "Madeira.app"
    app.mkdir()
    (app / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "test.madeira"}))
    calls = []
    def runner(argv, timeout):
        calls.append(argv)
        if "apps" in argv:
            result = {"apps": [{"bundleIdentifier": "test.madeira", "url": "file:///private/apps/target/Madeira.app/"}]}
        elif "processes" in argv:
            result = {"runningProcesses": [{"executable": "file:///private/apps/target/Madeira.app/Madeira", "processIdentifier": 12}]}
        else:
            pytest.fail("must not install over a running target")
        Path(argv[argv.index("--json-output") + 1]).write_text(json.dumps({"info":{"outcome":"success"},"result":result}))
    with pytest.raises(AutomationError, match="target_app_stopped"):
        DeviceControl(runner).install_app("tablet", app, "test.madeira")
    assert len(calls) == 2


def test_install_stopped_target_with_other_app_running_preserves_app_path(tmp_path):
    app = tmp_path / "signed build.app"
    app.mkdir()
    (app / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "test.madeira"}))
    calls = []
    def runner(argv, timeout):
        calls.append(argv)
        if "apps" in argv:
            result = {"apps": [{"bundleIdentifier": "test.madeira", "url": "file:///private/apps/target/Madeira.app/"}]}
        elif "processes" in argv:
            result = {"runningProcesses": [{"executable": "file:///private/apps/other/Madeira.app/Madeira"}]}
        else:
            result = {}
        Path(argv[argv.index("--json-output") + 1]).write_text(json.dumps({"info":{"outcome":"success"},"result":result}))
    DeviceControl(runner).install_app("tablet", app, "test.madeira")
    assert calls[-1][-1] == str(app)


@pytest.mark.parametrize("actual_pid", [42, 99])
def test_native_probe_cleanup_checks_bundle_and_pid_before_kill(actual_pid):
    calls, stopped = [], False
    def runner(argv, timeout):
        nonlocal stopped
        calls.append(argv)
        if "apps" in argv:
            result = {"apps": [{"bundleIdentifier": "test.madeira", "url": "file:///private/apps/owned/Madeira.app/"}]}
        elif "processes" in argv:
            result = {"runningProcesses": [] if stopped else [
                {"executable": "file:///private/apps/owned/Madeira.app/Madeira", "processIdentifier": actual_pid},
                {"executable": "file:///private/apps/owned/Madeira.app/PlugIns/Helper.appex/Helper", "processIdentifier": 16},
                {"executable": "file:///private/apps/other/Madeira.app/Madeira", "processIdentifier": 15}]}
        elif "terminate" in argv:
            assert argv[argv.index("--pid") + 1] == "42" and "--kill" in argv
            stopped = True; result = {}
        else: pytest.fail("unexpected device command")
        Path(argv[argv.index("--json-output") + 1]).write_text(json.dumps({"info":{"outcome":"success"},"result":result}))
    native = DeviceControl(runner)
    if actual_pid == 42:
        assert native.terminate_probe_process("tablet", "test.madeira", 42)["confirmed_stopped"]
        assert stopped
    else:
        with pytest.raises(AutomationError, match="identity_changed"):
            native.terminate_probe_process("tablet", "test.madeira", 42)
        assert not stopped and not any("terminate" in c for c in calls)


@pytest.mark.parametrize("already_running", [False, True])
def test_native_probe_launch_preserves_existing_process_and_records_new_pid(already_running):
    calls, running = [], already_running
    def runner(argv, timeout):
        nonlocal running
        calls.append(argv)
        if "apps" in argv:
            result = {"apps": [{"bundleIdentifier": "test.madeira", "url": "file:///private/owned/Madeira.app/"}]}
        elif "processes" in argv:
            result = {"runningProcesses": [{"executable": "file:///private/owned/Madeira.app/Madeira", "processIdentifier": 42}] if running else []}
        elif "launch" in argv:
            assert argv[-3:] == ["test.madeira", "--", "--madeira-automation"]
            assert "--terminate-existing" not in argv
            running = True; result = {}
        else: pytest.fail("unexpected command")
        Path(argv[argv.index("--json-output") + 1]).write_text(json.dumps({"info":{"outcome":"success"},"result":result}))
    native = DeviceControl(runner)
    if already_running:
        with pytest.raises(AutomationError, match="requires_Madeira_stopped"):
            native.launch_probe_process("tablet", "test.madeira")
        assert not any("launch" in c for c in calls)
    else:
        assert native.launch_probe_process("tablet", "test.madeira") == 42


@pytest.mark.parametrize("command", [["install", "unused.app"], ["smoke"], ["jit-test"], ["actions", "unused.json"]])
def test_cli_reservation_blocks_all_control_before_install_or_session(tmp_path, monkeypatch, capsys, command):
    from automation.controller import cli
    from automation.controller.reservation import reserve_device
    class Native:
        def select(self, *args): return {"udid": "tablet"}
        def install_app(self, *args): pytest.fail("must not install while reserved")
    monkeypatch.setattr(cli, "DeviceControl", Native)
    monkeypatch.setattr(cli, "AppiumController", lambda *args: pytest.fail("must not connect while reserved"))
    monkeypatch.setenv("MADEIRA_RESERVATION_DIR", str(tmp_path))
    with reserve_device("tablet", "existing-owner"):
        assert cli.main(command) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "device_reserved_by_another_run"


@pytest.mark.parametrize("url", ["http://0.0.0.0:4723", "http://example.com", "https://localhost", "http://a:b@localhost"])
def test_remote_or_credential_bearing_server_rejected(url):
    with pytest.raises(AutomationError):
        AppiumController(url)


@pytest.fixture
def appium_server():
    state = {"calls": [], "app": 1, "fail_settings": False, "session": False,
             "fail_command": None, "launch_stays_stopped": False, "displayed": True, "orientation": "LANDSCAPE"}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self): self.handle_request()
        def do_POST(self): self.handle_request()
        def do_DELETE(self): self.handle_request()
        def handle_request(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"null")
            state["calls"].append((self.command, self.path, body))
            value, status = None, 200
            if self.path == "/session":
                state["session"] = True
                value = {"sessionId": "test-session", "capabilities": {}}
            elif self.path.endswith("/execute/sync"):
                command = body["script"]
                if command == state["fail_command"]:
                    value, status = {"error": "invalid session id", "message": "PRIVATE_DIAGNOSTIC"}, 404
                else:
                    if command == "mobile: launchApp" and not state["launch_stays_stopped"]: state["app"] = 4
                    if command == "mobile: terminateApp": state["app"] = 1
                    if command == "mobile: queryAppState": value = state["app"]
            elif self.path.endswith("/element"):
                value = {ELEMENT: body["value"]}
            elif self.path.endswith("madeira.tab.settings/click") and state["fail_settings"]:
                value, status = {"error": "unknown error", "message": "password=DO_NOT_EXPORT"}, 500
            elif self.path.endswith("/attribute/selected"):
                value = "true"
            elif self.path.endswith("/displayed"):
                value = state["displayed"]
            elif self.path.endswith("/orientation"):
                if self.command == "POST": state["orientation"] = body["orientation"]
                value = state["orientation"]
            elif self.path.endswith("/screenshot"):
                value = base64.b64encode(b"\x89PNG\r\n\x1a\nfixture").decode()
            elif self.path.endswith("/source"):
                value = '<App><Button type="Button" name="madeira.tab.library" value="DO_NOT_EXPORT"/><Text type="Text" name="secret-account" label="secret-token"/></App>'
            elif self.path.endswith("/log"):
                value = []
            elif self.command == "DELETE":
                state["session"] = False
                if state.get("expired"):
                    value, status = {"error": "invalid session id"}, 404
            data = json.dumps({"value": value}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", state
    server.shutdown()
    server.server_close()
    thread.join()


class NativeLog:
    def application_log(self, *args): return []


@pytest.mark.parametrize("failure", [False, True])
def test_smoke_real_http_protocol_and_failure_cleanup(appium_server, tmp_path, failure):
    url, state = appium_server
    state["fail_settings"] = failure
    client = AppiumController(url)
    client.connect("tablet", "test.madeira")
    workflow = Run(client, NativeLog(), {"udid": "tablet"}, "test.madeira", tmp_path)
    report = workflow.smoke()
    assert report["status"] == ("failed" if failure else "passed")
    assert state["app"] == 1 and state["session"] is False
    assert client.session is None
    assert (tmp_path / "report.json").exists()
    serialized = (tmp_path / "report.json").read_text()
    assert "DO_NOT_EXPORT" not in serialized and "secret-token" not in serialized
    assert "secret-account" not in serialized
    calls = state["calls"]
    caps = calls[0][2]["capabilities"]["alwaysMatch"]
    assert caps["appium:noReset"] and not caps["appium:fullReset"]
    termination = next(i for i, c in enumerate(calls) if c[2] and c[2].get("script") == "mobile: terminateApp")
    assert any(c[1].endswith("/source") for c in calls[:termination])
    assert not any("uninstall" in str(c) for c in calls)


def test_input_constraints_fail_before_network():
    client = AppiumController()
    with pytest.raises(AutomationError, match="invalid_coordinate"):
        client.tap(float("nan"), 1)
    with pytest.raises(AutomationError, match="invalid_swipe_duration"):
        client.swipe((0, 0), (1, 1), 50)


def test_hidden_control_is_not_accepted_as_visible_page(appium_server):
    url, state = appium_server
    state["displayed"] = False
    client = AppiumController(url)
    client.connect("tablet", "test.madeira")
    with pytest.raises(AutomationError, match="no such element"):
        client.find("madeira.tab.library", timeout=0)
    assert not any(c[1].endswith("/click") for c in state["calls"])
    client.close()


def test_developer_smoke_selects_process_frontend_without_settings_changes(appium_server, tmp_path):
    url, state = appium_server
    client = AppiumController(url)
    client.connect("tablet", "test.madeira")
    report = Run(client, NativeLog(), {"udid": "tablet"}, "test.madeira", tmp_path).smoke("developer")
    assert report["status"] == "passed"
    launch = next(c[2] for c in state["calls"] if c[2] and c[2].get("script") == "mobile: launchApp")
    assert launch["args"][0]["arguments"] == ["-madeiraFrontend", "old"]
    assert state["orientation"] == "LANDSCAPE"


def test_log_export_is_fixed_vocabulary_only():
    events = diagnostic_events("password=hunter2\nFEX-Emu test PASSED: x86-64 code returned 42! token=SECRET\n")
    assert events == [{"event": "fex_test_passed"}]


def test_smoke_preserves_preexisting_running_app(appium_server, tmp_path):
    url, state = appium_server
    state["app"] = 4
    client = AppiumController(url)
    client.connect("tablet", "test.madeira")
    report = Run(client, NativeLog(), {"udid": "tablet"}, "test.madeira", tmp_path).smoke()
    assert report["status"] == "failed"
    assert state["app"] == 4
    assert not any(c[2] and c[2].get("script") == "mobile: terminateApp" for c in state["calls"])


@pytest.mark.parametrize("main_pids", [[], [42]])
def test_background_extension_does_not_hide_a_suspended_main_process(appium_server, tmp_path, main_pids):
    url, state = appium_server
    state["app"] = 2
    class Native(NativeLog):
        def app_process_ids(self, udid, bundle): return main_pids
    client = AppiumController(url)
    client.connect("tablet", "test.madeira")
    report = Run(client, Native(), {"udid": "tablet"}, "test.madeira", tmp_path).smoke()
    assert report["status"] == ("failed" if main_pids else "passed")
    if main_pids:
        assert state["app"] == 2
        assert not any(c[2] and c[2].get("script") in ("mobile: launchApp", "mobile: terminateApp") for c in state["calls"])


@pytest.mark.parametrize("failure,failed_step", [
    ("mobile: launchApp", "launch"),
    ("stopped", "verify_foreground"),
    ("mobile: terminateApp", "terminate"),
    ("mobile: queryAppState", None),
])
def test_lifecycle_failure_retains_report_and_closes_session(appium_server, tmp_path, failure, failed_step):
    url, state = appium_server
    state["launch_stays_stopped"] = failure == "stopped"
    state["fail_command"] = None if failure == "stopped" else failure
    client = AppiumController(url)
    client.connect("tablet", "test.madeira")
    report = Run(client, NativeLog(), {"udid": "tablet"}, "test.madeira", tmp_path).smoke()
    assert report["status"] == "failed"
    if failed_step:
        assert any(s["name"] == failed_step and s["status"] == "failed" for s in report["steps"])
    assert state["session"] is False and client.session is None
    assert "PRIVATE_DIAGNOSTIC" not in (tmp_path / "report.json").read_text()
    if failure in ("mobile: launchApp", "mobile: queryAppState"):
        assert not any(c[2] and c[2].get("script") == "mobile: terminateApp" for c in state["calls"])


def test_socket_idle_budget_and_expired_session_cleanup(appium_server):
    url, state = appium_server
    client = AppiumController(url)
    client.connect("tablet", "test.madeira", idle_timeout=2100)
    assert state["calls"][0][2]["capabilities"]["alwaysMatch"]["appium:newCommandTimeout"] == 2100
    state["app"] = 4
    state["expired"] = True
    client.close()
    assert client.session is None and state["app"] == 4
    assert not any(c[2] and c[2].get("script") == "mobile: terminateApp" for c in state["calls"])


@pytest.mark.parametrize("timeout", [0, -1, 3601, True, 1.5])
def test_invalid_session_idle_budget_refused_before_connect(timeout):
    with pytest.raises(AutomationError, match="invalid_appium_idle_timeout"):
        AppiumController().connect("tablet", "test.madeira", idle_timeout=timeout)
