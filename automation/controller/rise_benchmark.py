"""Rise's built-in benchmark: bounded socket input and fresh result recognition.

Caller owns the shared device reservation and paired transport. Start on a
verified benchmark result screen. Enter dismisses it, returning to the selected
Start Benchmark item. No arbitrary navigation, launch, install or settings edits.
"""
import json
import math
import subprocess
import time
from pathlib import Path

from .device import AutomationError
from .game_control import command
from .workflows import save_json


def recognize(executable, screenshot):
    try:
        result = subprocess.run([str(executable), str(screenshot)], capture_output=True,
                                text=True, timeout=10, check=True)
        value = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        raise AutomationError('rise_checkpoint_unavailable') from None
    if (not isinstance(value, dict) or value.get('schema_version') != 1
            or value.get('game') != 'rise_of_the_tomb_raider'
            or type(value.get('result_ready')) is not bool or type(value.get('menu_ready')) is not bool):
        raise AutomationError('invalid_rise_checkpoint')
    scores = value.get('scores')
    if not isinstance(scores, dict):
        raise AutomationError('invalid_rise_scores')
    if value['result_ready']:
        scenes = {'mountain_peak', 'syria', 'geothermal_valley'}
        if set(scores) != scenes | {'overall_fps'}:
            raise AutomationError('incomplete_rise_scores')
        def number(n):
            return type(n) in (int, float) and math.isfinite(n) and 0 <= n <= 1000
        if not number(scores['overall_fps']) or scores['overall_fps'] == 0:
            raise AutomationError('invalid_rise_scores')
        for scene in scenes:
            values = scores[scene]
            if (not isinstance(values, dict) or set(values) != {'average_fps', 'minimum_fps', 'maximum_fps'}
                    or not all(number(v) for v in values.values())
                    or not values['minimum_fps'] <= values['average_fps'] <= values['maximum_fps']):
                raise AutomationError('invalid_rise_scores')
    return value


def enter(device, transport, *, clock=time.monotonic, pause=time.sleep):
    reply = command(device, 'start_replay', replay={'duration_ms': 1000, 'events': [
        {'at_ms': 0, 'keys': [13]}, {'at_ms': 150, 'keys': []}]})
    if reply.get('status') != 'accepted':
        raise AutomationError('rise_input_rejected')
    deadline = clock() + 10
    while clock() < deadline:
        state = transport.snapshot().get('replay_status', {}).get('state')
        if state == 'COMPLETED':
            return
        if state != 'RUNNING':
            raise AutomationError('rise_input_interrupted')
        pause(0.5)
    raise AutomationError('rise_input_timeout')


def run_from_result(workflow, executable, *, selected_menu=False, timeout=360, clock=time.monotonic, pause=time.sleep):
    # For a fresh process, the caller may explicitly attest that Start Benchmark
    # is selected on a visually checked main menu. Never guess its selection.
    if type(selected_menu) is not bool:
        raise AutomationError('invalid_rise_start_checkpoint')
    if type(timeout) is not int or not 180 <= timeout <= 600:
        raise AutomationError('invalid_rise_timeout')
    a = workflow.device
    t = getattr(a, 'command_transport', None)
    if t is None:
        raise AutomationError('rise_requires_paired_transport')
    workflow.require_state(4)
    initial = t.snapshot()
    game = initial.get('game_status', {})
    if not initial.get('wine_running') or not game.get('owned_by_automation') or game.get('phase') != 'SESSION_OBSERVED':
        raise AutomationError('rise_requires_owned_session')
    games = command(a, 'list_installed_games')
    if games.get('status') != 'completed' or not isinstance(games.get('data'), list):
        raise AutomationError('installed_games_unavailable')
    targets = [g for g in games['data'] if isinstance(g, dict) and g.get('steam_app_id') == 391220]
    if len(targets) != 1 or targets[0].get('library_id') != game.get('active_library_id'):
        raise AutomationError('rise_missing_ambiguous_or_not_active')
    evidence = {'schema_version': 1, 'scope': 'game_reported_builtin_benchmark',
                'status': 'running', 'observations': [], 'pid': initial.get('pid')}
    screenshot = Path(workflow.path) / 'checkpoint.png'

    def observe():
        s = t.snapshot()
        if s.get('pid') != initial.get('pid') or not s.get('wine_running') or s.get('game_status', {}).get('active_library_id') != game.get('active_library_id'):
            raise AutomationError('rise_process_changed')
        evidence['observations'].append({'elapsed_s': clock() - started,
                                         'thermal_state': s.get('thermal_state')})
        return s

    def screen(name):
        workflow.require_state(4)
        a.screenshot(screenshot)
        value = recognize(executable, screenshot)
        save_json(Path(workflow.path) / (name + '.json'), value)
        return value

    started = clock()
    try:
        if not screen('initial')['menu_ready' if selected_menu else 'result_ready']:
            raise AutomationError('rise_requires_selected_menu' if selected_menu else 'rise_requires_result_screen')
        if not selected_menu:
            enter(a, t, clock=clock, pause=pause)
        deadline = clock() + 90
        while clock() < deadline:
            observe()
            if screen('menu')['menu_ready']:
                break
            pause(2)
        else:
            raise AutomationError('rise_menu_timeout')
        evidence['thermal_state_start'] = observe().get('thermal_state')
        if evidence['thermal_state_start'] in {'serious', 'critical'}:
            raise AutomationError('rise_device_too_hot')
        enter(a, t, clock=clock, pause=pause)
        evidence['benchmark_started_s'] = clock() - started
        deadline = clock() + timeout
        departed = False
        consecutive = 0
        previous_scores = None
        next_screen = clock()
        while clock() < deadline:
            state = observe()
            if clock() >= next_screen:
                checkpoint = screen('latest')
                next_screen = clock() + 10
                if not checkpoint['result_ready'] and not checkpoint['menu_ready']:
                    departed = True
                if checkpoint['result_ready'] and departed:
                    scores = checkpoint['scores']
                    consecutive = consecutive + 1 if scores == previous_scores else 1
                    previous_scores = scores
                    if consecutive >= 2:
                        evidence.update(status='completed', scores=scores,
                            thermal_state_end=state.get('thermal_state'),
                            result_observed_s=clock() - started, visual_acceptance='not_established')
                        screenshot.replace(Path(workflow.path) / 'result.png')
                        return evidence
                else:
                    consecutive = 0
            pause(1.5)
        raise AutomationError('rise_benchmark_timeout')
    except Exception as exc:
        evidence.update(status='failed', reason=str(exc) if isinstance(exc, AutomationError) else type(exc).__name__)
        raise
    finally:
        save_json(Path(workflow.path) / 'rise-benchmark.json', evidence)
