"""Capture a single owned session with on-device warmup/measurement boundaries."""
import json
import time
from .device import AutomationError
from .game_control import command
from .jit_probe import snapshot
from .replay import validate_plan
from .telemetry import load_trace, summarize
from .capture_metadata import load_metadata
from .workflows import save_json


def capture(workflow, plan, warmup=60, seconds=180, *, clock=time.monotonic, pause=time.sleep):
    validate_plan(plan)
    if type(warmup) is not int or type(seconds) is not int or not 0 <= warmup <= 900 or not 1 <= seconds <= 900 or plan['duration_ms'] != (warmup + seconds) * 1000:
        raise AutomationError('invalid_benchmark_window')
    workflow.require_state(4)
    before = snapshot(workflow.device)
    game = before.get('game_status', {})
    if not before.get('wine_running') or not game.get('owned_by_automation') or game.get('phase') != 'SESSION_OBSERVED':
        raise AutomationError('benchmark_requires_owned_session')
    pid = before.get('pid')
    reply = command(workflow.device, 'start_benchmark', replay=plan, warmup_ms=warmup*1000, capture_ms=seconds*1000)
    if reply.get('status') != 'accepted':
        raise AutomationError('benchmark_start_rejected')
    observations = []
    deadline = clock() + warmup + seconds + 30
    try:
        while clock() < deadline:
            pause(2)
            if workflow.device.app_state(workflow.bundle_id) != 4:
                raise AutomationError('benchmark_foreground_lost')
            state = snapshot(workflow.device)  # Refresh button is the explicit heartbeat.
            if state.get('pid') != pid or not state.get('wine_running'):
                raise AutomationError('benchmark_process_changed')
            replay = state.get('replay_status', {})
            observations.append({'host_monotonic_s':clock(), 'thermal_state':state.get('thermal_state'),
                                 'present_count':state.get('present_count'), 'state':replay.get('state')})
            if replay.get('state') == 'COMPLETED' and replay.get('capture_state') == 'EXPORTED':
                break
            if replay.get('state') != 'RUNNING':
                raise AutomationError('benchmark_replay_interrupted')
        else:
            raise AutomationError('benchmark_timeout')
        # Capture/export stopped natively before this copy. No UI command editor
        # interaction is needed during the measured interval.
        destination = workflow.path/'submission-trace.json'
        workflow.native.command(['device','copy','from','--device',workflow.info['udid'],
            '--domain-type','appDataContainer','--domain-identifier',workflow.bundle_id,
            '--source','Documents/automation-submission-trace.json','--destination',str(destination)], 120)
        destination.chmod(0o600)
        trace=load_trace(destination); metrics=summarize(trace)
        metadata_path=workflow.path/'capture-metadata.json'
        workflow.native.command(['device','copy','from','--device',workflow.info['udid'],
            '--domain-type','appDataContainer','--domain-identifier',workflow.bundle_id,
            '--source','Documents/automation-capture-metadata.json','--destination',str(metadata_path)],120)
        metadata_path.chmod(0o600)
        metadata=load_metadata(metadata_path,metrics['capture_id'])
        result={'schema_version':1, 'scope':'present_submission', 'warmup_seconds':warmup,
                'requested_measure_seconds':seconds, 'replay':replay, 'observations':observations,
                'metrics':metrics, 'scene_readiness':'NOT_ESTABLISHED_BY_CAPTURE',
                'process_capture':metadata, 'cpu_gpu_attribution':'PER_ROLE_AND_GPU_NOT_AVAILABLE', 'status':'captured'}
        save_json(workflow.path/'benchmark-capture.json',result)
        return result
    except Exception:
        # Release only our virtual input. Never kill a saving/uncertain game.
        try: command(workflow.device,'stop_replay')
        except AutomationError: pass  # Native heartbeat watchdog still releases.
        raise
