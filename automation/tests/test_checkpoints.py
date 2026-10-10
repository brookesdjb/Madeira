import json
from pathlib import Path
import pytest
from automation.controller.device import AutomationError
from automation.controller import checkpoints as c


def recognized(passed=True):
    return {"schema_version": 1, "checkpoint": "portal_first_slice_menu", "passed": passed,
            "matches": {k: passed for k in ("title", "new_game", "options", "quit")}}


class Device:
    def __init__(self): self.photos = 0
    def screenshot(self, path): self.photos += 1; Path(path).write_bytes(b"fixture")


def install_commands(monkeypatch, *, phase="SESSION_OBSERVED", owned=True, pids=(42, 42, 42)):
    ids = iter(pids)
    def command(device, operation):
        if operation == "list_installed_games":
            return {"status": "completed", "data": [{"steam_app_id": 400, "library_id": "fixture"}]}
        pid = next(ids)
        return {"status": "completed", "pid": pid, "data": {"pid": pid, "wine_running": True,
            "game_status": {"phase": phase, "owned_by_automation": owned,
                            "active_library_id": "fixture", "launching": False}}}
    monkeypatch.setattr(c, "command", command)


def test_menu_requires_two_fresh_observations_of_same_process(monkeypatch, tmp_path):
    install_commands(monkeypatch, pids=(42, 43, 43))
    d = Device()
    result = c.wait_for_portal_menu(d, tmp_path, recognize=lambda _: recognized(), pause=lambda _: None)
    assert d.photos == 3 and result["pid"] == 43 and result["readiness"] == "MENU_OBSERVED"
    assert result["consecutive_observations"] == 2


@pytest.mark.parametrize("kwargs", [{"phase": "STOP_REQUESTED"}, {"owned": False}])
def test_non_owned_or_stopping_session_cannot_pass(monkeypatch, tmp_path, kwargs):
    install_commands(monkeypatch, **kwargs); d = Device()
    with pytest.raises(AutomationError): c.wait_for_portal_menu(d, tmp_path)
    assert d.photos == 0


def test_frames_without_menu_timeout_preserves_game(monkeypatch, tmp_path):
    install_commands(monkeypatch); d = Device(); ticks = iter((0, 0, 1, 2))
    with pytest.raises(AutomationError, match="timeout_game_preserved"):
        c.wait_for_portal_menu(d, tmp_path, seconds=2, clock=lambda: next(ticks),
                              recognize=lambda _: recognized(False), pause=lambda _: None)
    assert d.photos == 2


def test_inconsistent_ocr_result_cannot_claim_readiness(monkeypatch, tmp_path):
    monkeypatch.setattr(c.platform, "system", lambda: "Darwin")
    result = recognized(False); result["passed"] = True
    with pytest.raises(AutomationError, match="invalid_portal_checkpoint_result"):
        c.recognize_portal_menu(tmp_path / "image.png", runner=lambda *a, **k: json.dumps(result))
