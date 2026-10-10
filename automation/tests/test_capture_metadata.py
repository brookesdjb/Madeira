import json
import pytest
from automation.controller.capture_metadata import load_metadata
from automation.controller.device import AutomationError


def fixture():
    return dict(schema_version=1,capture_id='test',scope='whole_app_process',clock='clock_monotonic_ns',wall_ns=100,user_cpu_ns=150,system_cpu_ns=50,footprint_before_bytes=1000,footprint_after_bytes=1100)


def test_cpu_can_exceed_one_core_and_unknown_counters_stay_null(tmp_path):
    p=tmp_path/'metadata';v=fixture();p.write_text(json.dumps(v))
    assert load_metadata(p,'test')['mean_cpu_cores']==2
    v['user_cpu_ns']=None;p.write_text(json.dumps(v))
    assert load_metadata(p,'test')['mean_cpu_cores'] is None


@pytest.mark.parametrize('change',[{'capture_id':'stale'},{'wall_ns':0},{'user_cpu_ns':True},{'system_cpu_ns':-1},{'unknown':42},{'schema_version':True}])
def test_invalid_or_stale_metadata_rejected(tmp_path,change):
    p=tmp_path/'metadata';v=fixture();v.update(change);p.write_text(json.dumps(v))
    with pytest.raises(AutomationError):load_metadata(p,'test')


def test_duplicate_or_oversized_json_rejected(tmp_path):
    p=tmp_path/'metadata'
    for raw in ['{"schema_version":1,"schema_version":1}', ' '*32769]:
        p.write_text(raw)
        with pytest.raises(AutomationError):load_metadata(p,'test')
