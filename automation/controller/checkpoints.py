"""Game-specific host observation; menu readiness is not gameplay or benchmark readiness."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import time
from .device import AutomationError, run
from .game_control import command


def recognize_portal_menu(path, runner=run):
    if platform.system() != "Darwin":
        raise AutomationError("portal_checkpoint_requires_macOS_Vision")
    source = Path(__file__).with_name("portal_checkpoint.swift")
    try:
        result = json.loads(runner(["swift", str(source), str(Path(path).resolve())], timeout=30))
    except (AutomationError, ValueError, TypeError):
        raise AutomationError("portal_checkpoint_recognition_failed") from None
    if (not isinstance(result, dict) or result.get("schema_version") != 1
            or result.get("checkpoint") != "portal_first_slice_menu"
            or not isinstance(result.get("matches"), dict)
            or set(result["matches"]) != {"title", "new_game", "options", "quit"}
            or any(type(v) is not bool for v in result["matches"].values())
            or type(result.get("passed")) is not bool
            or result["passed"] != all(result["matches"].values())):
        raise AutomationError("invalid_portal_checkpoint_result")
    return result


def wait_for_portal_menu(device, output, *, seconds=120, recognize=recognize_portal_menu,
                         clock=time.monotonic, pause=time.sleep):
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not 1 <= seconds <= 180:
        raise AutomationError("invalid_checkpoint_timeout")
    games = command(device, "list_installed_games")
    if games.get("status") != "completed" or not isinstance(games.get("data"), list):
        raise AutomationError("installed_games_unavailable")
    targets = [g for g in games["data"] if isinstance(g, dict) and g.get("steam_app_id") == 400]
    if len(targets) != 1 or not isinstance(targets[0].get("library_id"), str):
        raise AutomationError("portal_missing_or_ambiguous")
    library_id = targets[0]["library_id"]
    image = Path(output) / "portal-checkpoint.private.png"
    deadline = clock() + seconds
    previous_pid, consecutive = None, 0
    while clock() < deadline:
        reply = command(device, "get_game_status")
        status = reply.get("data")
        if reply.get("status") != "completed" or not isinstance(status, dict):
            raise AutomationError("game_status_unavailable_game_preserved")
        game = status.get("game_status", {})
        if not isinstance(game, dict): raise AutomationError("invalid_game_status")
        if game.get("phase") in {"ERROR", "MANUAL_INTERVENTION_REQUIRED", "STOP_REQUESTED", "EXITED"}:
            raise AutomationError("checkpoint_session_not_ready_game_preserved")
        pid = status.get("pid")
        if (type(pid) is not int or pid <= 0 or reply.get("pid") != pid or game.get("active_library_id") != library_id
                or game.get("owned_by_automation") is not True):
            raise AutomationError("checkpoint_requires_owned_portal_session")
        # Frames alone never satisfy the checkpoint. The normal startup UI must
        # release input, and two fresh screenshots must show the actual menu.
        device.screenshot(image)
        observed = recognize(image)
        eligible = game.get("launching") is False and status.get("wine_running") is True
        consecutive = consecutive + 1 if eligible and observed["passed"] and pid == previous_pid else int(eligible and observed["passed"])
        previous_pid = pid
        if consecutive >= 2:
            return {"schema_version": 1, "checkpoint": observed["checkpoint"],
                    "readiness": "MENU_OBSERVED", "pid": pid, "active_library_id": library_id,
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                    "matches": observed["matches"], "consecutive_observations": consecutive,
                    "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest()}
        pause(1)
    raise AutomationError("portal_menu_checkpoint_timeout_game_preserved")
