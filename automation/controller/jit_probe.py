"""A physical compatibility experiment, not a simulated JIT success claim."""
import json
import time
from .device import AutomationError


def snapshot(device):
    try:
        device.tap_id("madeira.automation.refresh")
    except AutomationError as exc:
        if str(exc) != "no such element":
            raise
        # The normal setup sheet hides the probe. Identify this prerequisite
        # without dismissing a dialog or reading potentially private error text.
        try:
            device.find("JIT setup", timeout=0)
        except AutomationError as setup_error:
            if str(setup_error) != "no such element":
                raise
            raise exc
        raise AutomationError("jit_setup_required") from None
    result = json.loads(device.value("madeira.automation.status"))
    if not isinstance(result, dict) or result.get("schema_version") != 1:
        raise AutomationError("unsupported_probe_schema")
    return result


def wait_for(workflow, condition, seconds=100, clock=time.monotonic, pause=time.sleep):
    deadline = clock() + seconds
    background_since = None
    last_sequence = None
    while clock() < deadline:
        state = workflow.device.app_state(workflow.bundle_id)
        if state in (0, 1):
            raise AutomationError("Madeira_terminated_during_JIT_probe")
        if state != 4:
            # StikDebug/Shortcuts can take foreground. Reactivation is an explicit
            # part of this experiment, not a restart (which would discard JIT).
            background_since = background_since or clock()
            if clock() - background_since >= 10:
                workflow.device.activate_app(workflow.bundle_id)
                workflow.report.setdefault("foreground_events", []).append({"action": "activate_existing_process", "observed_state": state})
                background_since = clock()
            pause(1)
            continue
        background_since = None
        started = time.perf_counter()
        try:
            result = snapshot(workflow.device)
        except AutomationError as exc:
            # Opening StikDebug/Shortcuts can race the foreground-state query.
            # Keep the original process and bounded deadline during that switch.
            if str(exc) == "no such element":
                observed = workflow.device.app_state(workflow.bundle_id)
                if observed in (0, 1):
                    raise AutomationError("Madeira_terminated_during_JIT_probe") from None
                if observed != 4:
                    pause(1)
                    continue
            raise
        workflow.report.setdefault("ui_refresh_timings", []).append({
            "sequence": result.get("sequence"),
            "round_trip_ms": round((time.perf_counter() - started) * 1000, 2),
            "debugger_attached": result.get("debugger_attached"),
        })
        if result.get("sequence") == last_sequence:
            raise AutomationError("probe_status_not_refreshing")
        last_sequence = result.get("sequence")
        workflow.report.setdefault("jit_observations", []).append(result)
        if condition(result):
            return result
        if result.get("jit_error") and not result.get("jit_busy"):
            raise AutomationError("jit_failed_requires_local_diagnostics_or_provisioning")
        pause(1)
    raise AutomationError("jit_probe_timeout")


def probe(workflow):
    device, bundle = workflow.device, workflow.bundle_id
    try:
        # Don't terminate a potentially live game just to start the experiment.
        if not workflow.target_stopped():
            raise AutomationError("jit_probe_requires_Madeira_stopped_before_start")
        workflow.probe_pid = workflow.step("launch_test_mode", lambda: workflow.native.launch_probe_process(workflow.info["udid"], bundle))
        workflow.report["launch_backend"] = "devicectl"
        before = workflow.step("read_initial_state", lambda: snapshot(device))
        workflow.report["jit_before"] = before
        if before.get("pid") != workflow.probe_pid:
            raise AutomationError("probe_launch_pid_mismatch")
        if before.get("wine_running") or before.get("fex_test") != "NOT_RUN":
            raise AutomationError("jit_probe_requires_fresh_idle_process")
        workflow.step("request_existing_jit", lambda: device.tap_id("madeira.automation.enable-jit"))
        ready = workflow.step("jit_ready_and_ui_responsive", lambda: wait_for(workflow, lambda s: s.get("jit_ready") is True and s.get("debugger_attached") is True))
        workflow.step("start_existing_fex_test", lambda: device.tap_id("madeira.automation.test-fex"))
        fex = workflow.step("fex_result_and_ui_responsive", lambda: wait_for(workflow, lambda s: s.get("fex_test") in ("PASSED", "FAILED"), seconds=120))
        if fex.get("fex_test") != "PASSED" or fex.get("fex_result") != 42:
            raise AutomationError("fex_test_failed")
        workflow.report["jit_after_fex"] = fex
        workflow.step("jit_screenshot", lambda: device.screenshot(workflow.path / "jit-fex.png"))
        # Evidence before restart: app logs rotate on launch.
        workflow.diagnostics()
        workflow.report["pre_restart_evidence"] = dict(workflow.report["evidence"])
        workflow.step("terminate_for_relaunch_and_verify_native", workflow.stop_owned_probe)
        workflow.probe_pid = workflow.step("relaunch_test_mode", lambda: workflow.native.launch_probe_process(workflow.info["udid"], bundle))
        after = workflow.step("read_after_relaunch", lambda: snapshot(device))
        if after.get("pid") != workflow.probe_pid:
            raise AutomationError("probe_relaunch_pid_mismatch")
        if after.get("pid") == before.get("pid") or after.get("fex_test") != "NOT_RUN":
            raise AutomationError("fresh_process_not_confirmed")
        workflow.report["jit_after_relaunch"] = after
        workflow.report["reactivation_required"] = not after.get("jit_ready", False)
        if not after.get("jit_ready"):
            workflow.step("request_jit_after_relaunch", lambda: device.tap_id("madeira.automation.enable-jit"))
            workflow.step("jit_reactivated_and_ui_responsive", lambda: wait_for(workflow, lambda s: s.get("jit_ready") is True and s.get("debugger_attached") is True))
        workflow.report["compatibility"] = {
            "method": ready.get("jit_method"),
            "wda_and_jit_control": "observed",
            "x86_execution": "observed_return_42",
            "detach_survival": "not_tested",
            "vpn_automation": "existing_workflow_only_not_independently_verified",
            "full_game_automation": "not_tested"}
        workflow.report["status"] = "passed"
    except Exception as exc:
        workflow.report["status"] = "failed"
        workflow.report["error"] = str(exc) if isinstance(exc, AutomationError) else type(exc).__name__
    # Only terminate if this probe actually launched the app, never a preexisting game.
    launched = any(s["name"] == "launch_test_mode" and s["status"] == "passed" for s in workflow.report["steps"])
    return workflow.finish(terminate=launched)
