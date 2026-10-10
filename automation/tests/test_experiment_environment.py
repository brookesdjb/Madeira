import json
import pytest
from automation.controller.device import DeviceControl,AutomationError


def test_environment_rejected_before_device_effects():
    control=DeviceControl(runner=lambda *a,**k: (_ for _ in ()).throw(AssertionError('device touched')))
    for env in ({'HOME':'bad'},{'MADEIRA_SRV_COALESCE':'yes'},{'FEX_MAXINST':500},['bad']):
        with pytest.raises(AutomationError,match='experiment_environment'):
            control.launch_probe_process('test','test.app',environment=env)


def test_environment_is_an_argv_json_value_and_running_app_stays_protected():
    class Control(DeviceControl):
        calls=[]
        running=False
        def app_process_ids(self,*args):return [42] if self.running else []
        def command(self,args,timeout): self.calls.append(args);self.running=True
    c=Control();assert c.launch_probe_process('test','test.app',environment={'MADEIRA_SRV_COALESCE':'1'})==42
    args=c.calls[0];assert json.loads(args[args.index('--environment-variables')+1])=={'MADEIRA_SRV_COALESCE':'1'}
    with pytest.raises(AutomationError,match='stopped_before_start'):c.launch_probe_process('test','test.app')
    assert len(c.calls)==1
