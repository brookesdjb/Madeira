import json
from types import SimpleNamespace
import pytest
from automation.controller import rise_benchmark as r
from automation.controller.device import AutomationError


def checkpoint(result=False, menu=False):
    return {'schema_version':1, 'game':'rise_of_the_tomb_raider', 'result_ready':result, 'menu_ready':menu,
            'scores': {'overall_fps':30, **{s:{'average_fps':30, 'minimum_fps':20, 'maximum_fps':40}
                for s in ('mountain_peak','syria','geothermal_valley')}} if result else {}}


def test_recognizer_rejects_partial_and_impossible_results(monkeypatch):
    value=checkpoint(True)
    monkeypatch.setattr(r.subprocess,'run',lambda *a,**kw: SimpleNamespace(stdout=json.dumps(value)))
    assert r.recognize('reader','image')['scores']['overall_fps']==30
    value['scores']['syria']['minimum_fps']=45
    with pytest.raises(AutomationError,match='invalid_rise_scores'):r.recognize('reader','image')
    del value['scores']['syria']
    with pytest.raises(AutomationError,match='incomplete_rise_scores'):r.recognize('reader','image')


def setup(monkeypatch,tmp_path,frames,thermal='nominal'):
    state={'pid':123,'wine_running':True,'thermal_state':thermal,'game_status':{
        'owned_by_automation':True,'phase':'SESSION_OBSERVED','active_library_id':'rise'}}
    device=SimpleNamespace(command_transport=SimpleNamespace(snapshot=lambda:state),
        screenshot=lambda p:p.write_bytes(b'fixture'))
    workflow=SimpleNamespace(device=device,path=tmp_path,require_state=lambda _:None)
    calls=[]
    monkeypatch.setattr(r,'command',lambda *a,**kw:{'status':'completed','data':[{'steam_app_id':391220,'library_id':'rise'}]})
    monkeypatch.setattr(r,'enter',lambda *a,**kw:calls.append('enter'))
    frames=iter(frames)
    monkeypatch.setattr(r,'recognize',lambda *a:next(frames,checkpoint(True)))
    now=[0]
    return workflow,calls,lambda:now[0],lambda seconds:now.__setitem__(0,now[0]+seconds)


def test_requires_departure_and_two_matching_results(monkeypatch,tmp_path):
    w,calls,clock,pause=setup(monkeypatch,tmp_path,[checkpoint(True),checkpoint(menu=True),checkpoint(),checkpoint(True),checkpoint(True)])
    result=r.run_from_result(w,'reader',clock=clock,pause=pause)
    assert result['status']=='completed' and calls==['enter','enter']
    assert (tmp_path/'result.png').exists()
    assert result['visual_acceptance']=='not_established'


def test_stale_result_never_becomes_new_measurement(monkeypatch,tmp_path):
    w,calls,clock,pause=setup(monkeypatch,tmp_path,[checkpoint(True),checkpoint(menu=True)])
    with pytest.raises(AutomationError,match='rise_benchmark_timeout'):
        r.run_from_result(w,'reader',timeout=180,clock=clock,pause=pause)
    assert json.loads((tmp_path/'rise-benchmark.json').read_text())['status']=='failed'


def test_hot_device_does_not_start_benchmark(monkeypatch,tmp_path):
    w,calls,clock,pause=setup(monkeypatch,tmp_path,[checkpoint(True),checkpoint(menu=True)],'serious')
    with pytest.raises(AutomationError,match='rise_device_too_hot'):
        r.run_from_result(w,'reader',clock=clock,pause=pause)
    assert calls==['enter']
