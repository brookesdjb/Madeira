"""Correlated XCTest commands. Acknowledged launch/stop is never game readiness/exit."""
import json
import re
import time
import uuid
from .device import AutomationError

OPERATIONS = {"get_status", "list_installed_games", "launch_game", "stop_game",
              "get_game_status", "get_runtime_status", "get_jit_status", "get_diagnostics"}


def command(device, operation, *, library_id=None, steam_app_id=None, request_id=None, reply_timeout=15):
    request_id = request_id or uuid.uuid4().hex
    if operation not in OPERATIONS or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request_id):
        raise AutomationError("invalid_game_command")
    count = int(library_id is not None) + int(steam_app_id is not None)
    if count != int(operation in {"launch_game", "stop_game"}):
        raise AutomationError("invalid_game_selector")
    request = {"schema_version": 2, "request_id": request_id, "operation": operation}
    if library_id is not None:
        try: request["library_id"] = str(uuid.UUID(library_id))
        except (ValueError, TypeError, AttributeError): raise AutomationError("invalid_game_selector") from None
    if steam_app_id is not None:
        if isinstance(steam_app_id, bool) or not isinstance(steam_app_id, int) or steam_app_id <= 0:
            raise AutomationError("invalid_game_selector")
        request["steam_app_id"] = steam_app_id
    element = device.find("madeira.automation.command")
    device.call("POST", f"/element/{element}/clear", {})
    device.text("madeira.automation.command", json.dumps(request, separators=(",", ":")))
    device.tap_id("madeira.automation.send-command")
    # Launch replaces the library view and may briefly invalidate XCTest's
    # elements. Poll only the correlated reply: never resend a mutation.
    deadline = time.monotonic() + reply_timeout
    while True:
        try:
            reply = json.loads(device.value("madeira.automation.reply"))
            if isinstance(reply, dict) and reply.get("schema_version") == 2 and reply.get("request_id") == request_id:
                if reply.get("status") not in {"accepted", "completed", "rejected"}:
                    raise AutomationError("invalid_game_command_reply")
                return reply
        except AutomationError as exc:
            if str(exc) != "no such element":
                raise
        except (ValueError, TypeError):
            raise AutomationError("invalid_game_command_reply") from None
        if time.monotonic() >= deadline:
            raise AutomationError("game_command_reply_timeout_request_may_have_run")
        time.sleep(0.2)


def wait_for_exit(device, *, seconds=120, clock=time.monotonic, pause=time.sleep):
    """Observe graceful exit; never kill a game or click through a save dialog."""
    deadline = clock() + seconds
    while clock() < deadline:
        reply = command(device, "get_game_status")
        status = reply.get("data")
        if reply.get("status") != "completed" or not isinstance(status, dict):
            raise AutomationError("game_status_unavailable_game_preserved")
        game = status.get("game_status", {})
        phase = game.get("phase")
        if (phase == "EXITED" and status.get("wine_running") is False
                and status.get("wineserver_running") is False
                and game.get("active_library_id") is None
                and isinstance(game.get("sessions_this_process"), int)
                and not isinstance(game["sessions_this_process"], bool)
                and game["sessions_this_process"] > 0):
            return reply
        if phase in {"ERROR", "MANUAL_INTERVENTION_REQUIRED"}:
            raise AutomationError("game_requires_owner_intervention")
        pause(1)
    raise AutomationError("graceful_exit_timeout_game_preserved")
