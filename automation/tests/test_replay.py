import copy
import pytest
from automation.controller.replay import validate_plan
from automation.controller.game_control import command
from automation.controller.device import AutomationError


def plan(): return {'duration_ms': 2000, 'events': [{'at_ms':0,'keys':[87],'ly':32767}, {'at_ms':1000,'keys':[]}]}


def test_plan_validates_before_touching_ui():
    assert validate_plan(plan()) == plan()
    class Device:
        def find(self, name): raise AssertionError('invalid plan touched UI')
    with pytest.raises(AutomationError): command(Device(),'start_replay',replay={'duration_ms':0,'events':[]})


@pytest.mark.parametrize('change', [
    lambda p:p.update(duration_ms=True),lambda p:p.update(duration_ms=900001),
    lambda p:p.update(path='/private'),lambda p:p['events'][0].update(at_ms=-1),
    lambda p:p['events'][1].update(at_ms=0),lambda p:p['events'][0].update(keys=[True]),
    lambda p:p['events'][0].update(keys=[87,87]),lambda p:p['events'][0].update(dx=1001),
    lambda p:p['events'][0].update(lx=-32769),lambda p:p['events'][0].update(token='private')])
def test_invalid_plan_rejected(change):
    p=plan(); change(p)
    with pytest.raises(AutomationError):validate_plan(p)


def test_actual_swift_replay_plan_validation(tmp_path):
    import subprocess
    from pathlib import Path
    source = Path(__file__).resolve().parents[2]/'app/Madeira/AutomationCommand.swift'
    main=tmp_path/'main.swift'; exe=tmp_path/'replay'
    main.write_text('''import Foundation
func parse(_ p: String) -> Bool { (try? AutomationCommand.parse(p)) != nil }
assert(parse(#"{"schema_version":2,"request_id":"r","operation":"start_replay","replay":{"duration_ms":2000,"events":[{"at_ms":0,"keys":[87],"ly":32767},{"at_ms":1000,"keys":[]}]}}"#))
for bad in [
 #"{"schema_version":2,"request_id":"r","operation":"start_replay"}"#,
 #"{"schema_version":2,"request_id":"r","operation":"start_replay","replay":{"duration_ms":2000,"events":[{"at_ms":0,"keys":[true]}]}}"#,
 #"{"schema_version":2,"request_id":"r","operation":"start_replay","replay":{"duration_ms":2000,"events":[{"at_ms":0,"keys":[87],"lx":32768}]}}"#,
 #"{"schema_version":2,"request_id":"r","operation":"start_replay","replay":{"duration_ms":2000,"events":[{"at_ms":0,"keys":[87],"path":"x"}]}}"#,
 #"{"schema_version":2,"request_id":"r","operation":"get_status","replay":{"duration_ms":2000,"events":[{"at_ms":0,"keys":[]}]}}"#
] { assert(!parse(bad)) }
''')
    subprocess.run(['swiftc','-D','DEBUG','-D','MADEIRA_AUTOMATION',str(source),str(main),'-o',str(exe)],check=True,capture_output=True)
    subprocess.run([str(exe)],check=True)
