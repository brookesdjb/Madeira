"""Timed on-device gameplay input; heartbeat failure releases all virtual input."""
from .device import AutomationError


def validate_plan(plan):
    if not isinstance(plan, dict) or set(plan) != {'duration_ms', 'events'}:
        raise AutomationError('invalid_replay_plan')
    duration, events = plan['duration_ms'], plan['events']
    if type(duration) is not int or not 1 <= duration <= 900000 or not isinstance(events, list) or not 1 <= len(events) <= 64:
        raise AutomationError('invalid_replay_bounds')
    keys = set([13,27,16,17,32,37,38,39,40]) | set(range(48,91))
    previous = -1
    for event in events:
        if not isinstance(event, dict) or not {'at_ms','keys'} <= set(event) or not set(event) <= {'at_ms','keys','dx','dy','buttons','lx','ly','rx','ry'}:
            raise AutomationError('invalid_replay_event')
        at = event['at_ms']; held = event['keys']
        if type(at) is not int or not previous < at < duration or not isinstance(held,list) or len(held)>16 or any(type(x) is not int or x not in keys for x in held) or len(set(held)) != len(held):
            raise AutomationError('invalid_replay_event')
        for key, lo, hi in [('dx',-1000,1000),('dy',-1000,1000),('buttons',0,65535),*[(k,-32768,32767) for k in ('lx','ly','rx','ry')]]:
            if key in event and (type(event[key]) is not int or not lo <= event[key] <= hi):
                raise AutomationError('invalid_replay_event')
        previous = at
    return plan
