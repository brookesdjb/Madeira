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

    def finish(self, terminate=True):
        # No retry/reinstall/reset: a missing session can mean a disconnected device.
        self.diagnostics()
        if terminate:
            try:
                self.step("terminate", lambda: self.device.terminate_app(self.bundle_id))
                self.step("verify_terminated", lambda: self.require_state(1))
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
            if self.device.app_state(self.bundle_id) not in (0, 1):
                raise AutomationError("smoke_requires_Madeira_stopped_to_preserve_active_games")
            self.step("launch", lambda: self.device.launch_app(self.bundle_id))
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
