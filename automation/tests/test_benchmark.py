import pytest
from automation.controller import benchmark as b
from automation.controller.device import AutomationError


def plan(): return {'duration_ms':1000,'events':[{'at_ms':0,'keys':[]}]}


def test_unowned_game_cannot_be_measured(monkeypatch):
    class Workflow:
        device=object()
        def require_state(self,value): assert value==4
    monkeypatch.setattr(b,'snapshot',lambda _: {'wine_running':True,'game_status':{'owned_by_automation':False}})
    with pytest.raises(AutomationError,match='owned_session'):b.capture(Workflow(),plan(),0,1)


def test_window_validated_before_any_device_effect():
    class Workflow:
        def require_state(self,value):raise AssertionError('invalid window touched device')
    with pytest.raises(AutomationError,match='window'):b.capture(Workflow(),plan(),0,2)
