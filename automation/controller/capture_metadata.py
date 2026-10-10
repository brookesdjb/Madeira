"""Whole-app boundary counters; never infer per-frame CPU or GPU execution."""
import json
from pathlib import Path
from .device import AutomationError


def load_metadata(path, capture_id):
    try:
        with Path(path).open('rb') as f: raw=f.read(32769)
        if len(raw)>32768: raise ValueError()
        def unique(pairs):
            result={}
            for k,v in pairs:
                if k in result: raise ValueError()
                result[k]=v
            return result
        value=json.loads(raw,object_pairs_hook=unique)
    except (OSError,ValueError,RecursionError):
        raise AutomationError('invalid_capture_metadata') from None
    fields={'schema_version','capture_id','scope','clock','wall_ns','user_cpu_ns','system_cpu_ns','footprint_before_bytes','footprint_after_bytes'}
    if not isinstance(value,dict) or set(value)!=fields or type(value['schema_version']) is not int or value['schema_version']!=1 or value['capture_id']!=capture_id or value['scope']!='whole_app_process' or value['clock']!='clock_monotonic_ns':
        raise AutomationError('capture_metadata_contract_mismatch')
    for k in fields-{'schema_version','capture_id','scope','clock'}:
        x=value[k]
        if x is not None and (type(x) is not int or not 0<=x<2**63):raise AutomationError('invalid_capture_metadata_counter')
    if value['wall_ns'] is not None and value['wall_ns']==0:raise AutomationError('invalid_capture_metadata_counter')
    wall,user,system=(value[k] for k in ('wall_ns','user_cpu_ns','system_cpu_ns'))
    value['mean_cpu_cores']=(user+system)/wall if all(x is not None for x in (wall,user,system)) else None
    return value
