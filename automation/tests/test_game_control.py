import json
import pytest
from automation.controller.device import AutomationError
from automation.controller.game_control import command, wait_for_exit


class Device:
    def __init__(self): self.effects = []; self.request = None; self.phase = "SESSION_OBSERVED"
    def find(self, name): return "editor"
    def call(self, *args): self.effects.append(args)
    def text(self, name, text): self.request = json.loads(text)
    def tap_id(self, name): self.effects.append(name)
    def value(self, name):
        return json.dumps({"schema_version": 2, "request_id": self.request["request_id"],
                           "status": "completed", "data": {"game_status": {"phase": self.phase,
                           "active_library_id": None, "sessions_this_process": 1},
                           "wine_running": self.phase != "EXITED", "wineserver_running": False}})


@pytest.mark.parametrize("kwargs", [{"operation": "launch_game"},
    {"operation": "purchase_game"}, {"operation": "stop_game", "steam_app_id": True},
    {"operation": "get_status", "library_id": "not-a-uuid"}])
def test_invalid_command_does_not_touch_UI(kwargs):
    d = Device()
    with pytest.raises(AutomationError): command(d, **kwargs)
    assert d.effects == [] and d.request is None


def test_wrong_correlation_is_never_accepted():
    class Wrong(Device):
        def value(self, name): return '{"schema_version":2,"request_id":"old","status":"accepted"}'
    with pytest.raises(AutomationError, match="request_may_have_run"):
        command(Wrong(), "launch_game", steam_app_id=400, reply_timeout=0)


def test_launch_transition_retries_read_without_resending(monkeypatch):
    class Transition(Device):
        reads = 0
        def value(self, name):
            self.reads += 1
            if self.reads == 1: raise AutomationError("no such element")
            if self.reads == 2: return '{"schema_version":2,"request_id":"old","status":"accepted"}'
            return super().value(name)
    monkeypatch.setattr("automation.controller.game_control.time.sleep", lambda _: None)
    d = Transition()
    assert command(d, "launch_game", steam_app_id=400)["status"] == "completed"
    assert d.reads == 3
    assert d.effects.count("madeira.automation.send-command") == 1


def test_lost_reply_preserves_uncertain_mutation():
    class Missing(Device):
        def value(self, name): raise AutomationError("no such element")
    d = Missing()
    with pytest.raises(AutomationError, match="request_may_have_run"):
        command(d, "stop_game", steam_app_id=400, reply_timeout=0)
    assert d.effects.count("madeira.automation.send-command") == 1


def test_accepted_request_is_distinct_from_exit():
    d = Device(); ticks = iter(range(5))
    with pytest.raises(AutomationError, match="game_preserved"):
        wait_for_exit(d, seconds=2, clock=lambda: next(ticks), pause=lambda _: None)
    assert all("terminate" not in str(x) for x in d.effects)
    d.phase = "EXITED"
    assert wait_for_exit(d)["data"]["game_status"]["phase"] == "EXITED"


def test_save_or_cloud_confirmation_is_reported_without_bypass():
    d = Device(); d.phase = "MANUAL_INTERVENTION_REQUIRED"
    with pytest.raises(AutomationError, match="owner_intervention"): wait_for_exit(d)


def test_rejected_status_cannot_satisfy_exit():
    class Rejected(Device):
        def value(self, name):
            return json.dumps({"schema_version": 2, "request_id": self.request["request_id"],
                               "status": "rejected", "data": None})
    with pytest.raises(AutomationError, match="unavailable_game_preserved"):
        wait_for_exit(Rejected())
