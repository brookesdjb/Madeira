"""Bounded smoke workflow, evidence first and cleanup even on failure."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import uuid
import subprocess
from .device import AutomationError


def new_run(root):
    path = Path(root) / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid.uuid4().hex[:8])
    path.mkdir(parents=True, mode=0o700)
    return path


def save_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n")
    os.chmod(path, 0o600)


class Run:
    def __init__(self, device, native, info, bundle_id, path):
        self.device, self.native, self.info = device, native, info
        self.bundle_id, self.path = bundle_id, Path(path)
        self.restore_orientation = None
        self.probe_pid = None
        root = Path(__file__).resolve().parents[2]
        try:
            commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
            dirty = bool(subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"], text=True))
        except (OSError, subprocess.CalledProcessError):
            commit, dirty = None, None
        self.report = {"source_commit": commit, "source_dirty": dirty, "schema_version": 1, "device": info, "bundle_id": bundle_id,
                       "started_at": datetime.now(timezone.utc).isoformat(), "steps": [],
                       "status": "running", "evidence": {}, "hardware_validation": "attempted"}

    def step(self, name, action):
        try:
            value = action()
            self.report["steps"].append({"name": name, "status": "passed"})
            return value
        except Exception as exc:
            # Only our sanitized errors, not arbitrary server text or input payloads.
            reason = str(exc) if isinstance(exc, AutomationError) else type(exc).__name__
            self.report["steps"].append({"name": name, "status": "failed", "reason": reason})
            raise

    def diagnostics(self):
        actions = {
            "screenshot": lambda: self.device.screenshot(self.path / "diagnostic.png"),
            "ui": lambda: self.device.inspect_ui(),
            "app_state": lambda: self.device.app_state(self.bundle_id),
            "device_events": lambda: self.device.get_logs(),
            "app_events": lambda: self.native.application_log(self.info["udid"], self.bundle_id),
            "crash_reports": lambda: self.device.crash_report_count(),
        }
        for name, action in actions.items():
            try:
                self.report["evidence"][name] = action()
            except Exception as exc:
                self.report["evidence"][name] = {"unavailable": type(exc).__name__}

    def require_state(self, expected):
        state = self.device.app_state(self.bundle_id)
        if state != expected:
            raise AutomationError(f"unexpected_app_state:{state}:expected_{expected}")

    def target_stopped(self):
        state = self.device.app_state(self.bundle_id)
        if state in (0, 1): return True
        # XCTest can report background state for a running app extension even
        # after the main app exits. A real suspended main process still blocks.
        if state in (2, 3):
            return not self.native.app_process_ids(self.info["udid"], self.bundle_id)
        return False

    def finish(self, terminate=True):
        # No retry/reinstall/reset: a missing session can mean a disconnected device.
        self.diagnostics()
        if terminate:
            try:
                if self.probe_pid is not None:
                    self.step("terminate_owned_probe_and_verify_native", lambda: self.native.terminate_probe_process(self.info["udid"], self.bundle_id, self.probe_pid))
                else:
                    self.step("terminate", lambda: self.device.terminate_app(self.bundle_id))
                    self.step("verify_terminated", lambda: self.require_state(1))
            except Exception:
                self.report["status"] = "failed"
        if self.restore_orientation:
            try:
                self.step("restore_orientation", lambda: self.device.call("POST", "/orientation", {"orientation": self.restore_orientation}))
            except Exception:
                self.report["status"] = "failed"
        try:
            self.step("close_session", self.device.close)
        except Exception:
            self.report["status"] = "failed"
        self.report["finished_at"] = datetime.now(timezone.utc).isoformat()
        save_json(self.path / "report.json", self.report)
        return self.report

    def smoke(self, frontend="library"):
        launched = False
        try:
            if not self.target_stopped():
                raise AutomationError("smoke_requires_Madeira_stopped_to_preserve_active_games")
            if frontend == "developer":
                # Existing developer tooling is portrait-only; landscape is
                # the game surface. Restore the owner's orientation at cleanup.
                self.restore_orientation = self.step("read_orientation", lambda: self.device.call("GET", "/orientation"))
                self.step("portrait_tooling", lambda: self.device.call("POST", "/orientation", {"orientation": "PORTRAIT"}))
            # Foundation's argument domain selects this process's UI without
            # rewriting the user's persistent frontend preference.
            arguments = ["-madeiraFrontend", "old" if frontend == "developer" else "new"]
            self.step("launch", lambda: self.device.launch_app(self.bundle_id, arguments))
            launched = True
            self.step("verify_foreground", lambda: self.require_state(4))
            if frontend == "library":
                self.step("initial_library", lambda: self.device.tap_id("madeira.tab.library"))
                self.step("screenshot", lambda: self.device.screenshot(self.path / "initial.png"))
                self.step("open_settings", lambda: self.device.tap_id("madeira.tab.settings"))
                self.step("verify_settings", lambda: self.device.find("madeira.jit.setup"))
                self.step("return_to_library", lambda: self.device.tap_id("madeira.tab.library"))
                # Selected is a tab state, not just existence of an always-visible tab.
                self.step("verify_library", lambda: self.require_selected("madeira.tab.library"))
            else:
                self.step("screenshot", lambda: self.device.screenshot(self.path / "initial.png"))
                self.step("open_settings", lambda: self.device.tap_id("madeira.settings.open"))
                self.step("verify_settings", lambda: self.device.find("madeira.settings.done"))
                self.step("return_to_developer", lambda: self.device.tap_id("madeira.settings.done"))
                self.step("verify_developer", lambda: self.device.find("madeira.settings.open"))
            self.step("returned_screenshot", lambda: self.device.screenshot(self.path / "returned.png"))
            self.report["status"] = "passed"
        except Exception as exc:
            self.report["status"] = "failed"
            self.report["error"] = str(exc) if isinstance(exc, AutomationError) else type(exc).__name__
        return self.finish(terminate=launched)

    def require_selected(self, identifier):
        element = self.device.find(identifier)
        selected = self.device.call("GET", f"/element/{element}/attribute/selected")
        if selected not in (True, "true", "1", 1):
            raise AutomationError("initial_tab_not_selected")
