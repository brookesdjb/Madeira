import json
from pathlib import Path
import pytest
from automation.controller.device import AutomationError
from automation.controller.jit_probe import snapshot, wait_for, probe
from automation.controller.workflows import Run


class ProbeDevice:
    def __init__(self, fex_result=42):
        self.state = 1
        self.pid = 20
        self.sequence = 0
        self.jit = False
        self.fex = "NOT_RUN"
        self.result = None
        self.test_result = fex_result
        self.terminations = 0
        self.session = True
    def app_state(self, bundle): return self.state
    def launch_app(self, bundle, arguments=None):
        self.state, self.jit, self.fex, self.result = 4, False, "NOT_RUN", None
        self.pid += 1
        assert arguments == ["--madeira-automation"]
    def activate_app(self, bundle): self.state = 4
    def terminate_app(self, bundle):
        self.terminations += 1
        self.state = 1
    def close(self): self.session = False
    def tap_id(self, identifier):
        if identifier.endswith("refresh"): self.sequence += 1
        elif identifier.endswith("enable-jit"): self.jit = True
        elif identifier.endswith("test-fex"):
            self.result = self.test_result
            self.fex = "PASSED" if self.result == 42 else "FAILED"
    def value(self, identifier):
        return json.dumps({"schema_version": 1, "sequence": self.sequence, "pid": self.pid,
                           "jit_ready": self.jit, "debugger_attached": self.jit, "jit_method": "builtIn", "fex_test": self.fex,
                           "fex_result": self.result, "wine_running": False})
    def find(self, identifier, timeout=10):
        raise AutomationError("no such element")
    def screenshot(self, path):
        Path(path).write_bytes(b"fixture")
        return str(path)
    def inspect_ui(self): return []
    def get_logs(self): return []
    def crash_report_count(self): return {"available_reports": 0, "attribution": "unverified"}


class Native:
    def application_log(self, *args): return []


def workflow(tmp_path, device):
    return Run(device, Native(), {"udid": "test"}, "test.madeira", tmp_path)


@pytest.mark.parametrize("result", [42, -1])
def test_probe_only_passes_with_observed_fex_result_and_relaunch(tmp_path, result):
    device = ProbeDevice(result)
    report = probe(workflow(tmp_path, device))
    assert report["status"] == ("passed" if result == 42 else "failed")
    if result == 42:
        assert report["jit_after_relaunch"]["pid"] != report["jit_before"]["pid"]
        assert report["reactivation_required"] is True
        assert report["compatibility"]["detach_survival"] == "not_tested"
        assert "pre_restart_evidence" in report
        assert report["ui_refresh_timings"]
        assert all(t["round_trip_ms"] >= 0 for t in report["ui_refresh_timings"])
    else:
        assert "compatibility" not in report
    assert device.state == 1 and not device.session


def test_probe_does_not_terminate_an_existing_game(tmp_path):
    device = ProbeDevice()
    device.state = 4
    report = probe(workflow(tmp_path, device))
    assert report["status"] == "failed"
    assert device.terminations == 0
    assert device.state == 4


def test_readiness_timeout_is_not_success(tmp_path):
    device = ProbeDevice()
    device.state = 4
    ticks = iter(range(10))
    with pytest.raises(AutomationError, match="timeout"):
        wait_for(workflow(tmp_path, device), lambda s: s["jit_ready"], seconds=3,
                 clock=lambda: next(ticks), pause=lambda _: None)


def test_unexpected_termination_stops_probe(tmp_path):
    with pytest.raises(AutomationError, match="terminated"):
        wait_for(workflow(tmp_path, ProbeDevice()), lambda _: True)


def test_setup_sheet_is_reported_as_provisioning_instead_of_unresponsive_UI():
    class SetupDevice(ProbeDevice):
        def tap_id(self, identifier): raise AutomationError("no such element")
        def find(self, identifier, timeout=10):
            assert identifier == "JIT setup"
            return "setup-sheet-title"
    with pytest.raises(AutomationError, match="jit_setup_required"):
        snapshot(SetupDevice())


def test_foreground_switch_race_preserves_process_and_retries_with_deadline(tmp_path):
    class SwitchingDevice(ProbeDevice):
        def __init__(self):
            super().__init__(); self.state = 4; self.switch = True
        def tap_id(self, identifier):
            if self.switch:
                self.switch = False; self.state = 3
                raise AutomationError("no such element")
            self.jit = True
            super().tap_id(identifier)
    device = SwitchingDevice()
    ticks = iter(range(100))
    r = wait_for(workflow(tmp_path, device), lambda s: s["jit_ready"], seconds=50,
                 clock=lambda: next(ticks), pause=lambda _: None)
    assert r["pid"] == 20 and device.terminations == 0


def test_probe_source_is_double_compile_gated_and_runtime_opt_in():
    # This is a packaging guard, NOT a Swift compile or physical-device test.
    path = Path(__file__).resolve().parents[2] / "app/Madeira/ContentView.swift"
    source = path.read_text()
    marker = "#if DEBUG && MADEIRA_AUTOMATION"
    assert source.count(marker) == 4
    declaration = source[source.rindex(marker):]
    assert 'arguments.contains("--madeira-automation")' in declaration
    assert declaration.rstrip().endswith("#endif")
    assert "run() // Existing ContentView.runFEXTest" in declaration
