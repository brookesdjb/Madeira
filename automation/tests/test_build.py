from pathlib import Path
import plistlib
from types import SimpleNamespace

import pytest

from automation.controller.build import build_app, inspect_app
from automation.controller.device import AutomationError


def app_fixture(tmp_path, probe=False):
    app = tmp_path / "Madeira.app"
    app.mkdir()
    (app / "Info.plist").write_bytes(plistlib.dumps({"CFBundleExecutable": "Madeira", "CFBundleIdentifier": "test.madeira"}))
    (app / "Madeira").write_bytes(b"main stub")
    (app / "Madeira.debug.dylib").write_bytes(b"madeira.automation.status fex_automation_test_execute madeira.automation.command winios_automation_set_presentation_window" if probe else b"ordinary binary")
    return app


def test_compiled_probe_in_debug_dylib_is_detected(tmp_path):
    app = app_fixture(tmp_path, probe=True)
    result = inspect_app(app, automation=True, signed=False)
    assert result["automation_surface"] is True
    assert len(result["binary_sha256"]["Madeira.debug.dylib"]) == 64
    with pytest.raises(AutomationError, match="surface_mismatch"):
        inspect_app(app, automation=False, signed=False)


def test_missing_probe_does_not_pass_as_automation_build(tmp_path):
    app = app_fixture(tmp_path)
    with pytest.raises(AutomationError, match="surface_mismatch"):
        inspect_app(app, automation=True, signed=False)


def test_native_anchor_must_match_build_opt_in(tmp_path):
    app = app_fixture(tmp_path)
    (app / "Madeira").write_bytes(b"winios_automation_set_presentation_window")
    with pytest.raises(AutomationError, match="presentation_anchor_mismatch"):
        inspect_app(app, automation=False, signed=False)


def test_release_cannot_enable_probe_before_invoking_build(tmp_path):
    with pytest.raises(AutomationError, match="Debug_configuration"):
        build_app(tmp_path, "test.madeira", configuration="Release", automation=True, unsigned=True)
    assert not (tmp_path / "automation").exists()


def test_failed_build_retains_private_log_without_exporting_its_contents(tmp_path, monkeypatch):
    def failed_command(arguments, **kwargs):
        kwargs["stdout"].write("private signing error token=DO_NOT_EXPORT\n")
        return SimpleNamespace(returncode=65)
    monkeypatch.setattr("automation.controller.build.subprocess.run", failed_command)
    monkeypatch.setattr("automation.controller.build.subprocess.check_output", lambda *a, **kw: "")
    with pytest.raises(AutomationError) as error:
        build_app(tmp_path, "test.madeira", unsigned=True)
    assert "DO_NOT_EXPORT" not in str(error.value)
    log = next(tmp_path.glob("automation/runs/builds/*/xcodebuild.private.log"))
    assert "DO_NOT_EXPORT" in log.read_text()
    assert log.stat().st_mode & 0o077 == 0
    report = next(tmp_path.glob("automation/runs/builds/*/report.json"))
    assert '"status": "failed"' in report.read_text()
    assert "DO_NOT_EXPORT" not in report.read_text()
