"""Run as python -m automation.controller.cli from the repository root."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
from .appium_controller import AppiumController
from .device import AutomationError, DeviceControl, doctor, run
from .workflows import Run, new_run, save_json
from .reservation import reserve_device

DEFAULT_BUNDLE = "com.willfaust.madeora"
ROOT = Path(__file__).resolve().parents[2]


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--udid", default=os.getenv("MADEIRA_DEVICE_UDID"))
    p.add_argument("--bundle-id", default=os.getenv("MADEIRA_BUNDLE_ID", DEFAULT_BUNDLE))
    p.add_argument("--team", default=os.getenv("MADEIRA_TEAM_ID"))
    p.add_argument("--wda-bundle", default=os.getenv("MADEIRA_WDA_BUNDLE_ID"))
    p.add_argument("--transport", choices=["wired", "localNetwork"],
                   default=os.getenv("MADEIRA_DEVICE_TRANSPORT", "wired"))
    p.add_argument("--server", default="http://127.0.0.1:4723")
    p.add_argument("--output", default=str(ROOT / "automation/runs"))
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    sub.add_parser("devices")
    sub.add_parser("device-check")
    build = sub.add_parser("build")
    build.add_argument("--automation", action="store_true")
    build.add_argument("--configuration", choices=["Debug", "Release"], default="Debug")
    build.add_argument("--unsigned", action="store_true", help="Compile/inspect without signing or installing")
    build.add_argument("--derived-data", help="Dedicated output directory; defaults to one per build variant")
    build.add_argument("--setting", action="append", default=[], metavar="NAME=VALUE")
    install = sub.add_parser("install")
    install.add_argument("app", help="Signed .app directory; no uninstall or data reset")
    smoke = sub.add_parser("smoke")
    smoke.add_argument("--frontend", choices=["library", "developer"], default="library")
    actions = sub.add_parser("actions")
    actions.add_argument("file", help="JSON array of UI actions; one persistent Appium session")
    from .game_control import OPERATIONS
    game = sub.add_parser("game-command", help="Opted-in running app; never auto-launch, reset or force-stop a game")
    game.add_argument("operation", choices=sorted(OPERATIONS))
    game.add_argument("--library-id")
    game.add_argument("--steam-app-id", type=int)
    game.add_argument("--request-id")
    checkpoint = sub.add_parser("game-checkpoint", help="Observe the owned Portal menu; never launch or stop a game")
    checkpoint.add_argument("--seconds", type=int, default=120)
    telemetry = sub.add_parser("summarize-telemetry", help="Offline raw native submission trace; no device mutation")
    telemetry.add_argument("trace")
    telemetry.add_argument("--budget-ms", type=float, default=1000 / 60)
    sub.add_parser("jit-test")
    visual = sub.add_parser("compare-images")
    visual.add_argument("baseline")
    visual.add_argument("candidate")
    visual.add_argument("--pixel-threshold", type=int, default=20)
    visual.add_argument("--changed-fraction", type=float, default=0.1)
    visual.add_argument("--crop", type=int, nargs=4)
    return p


def execute_actions(workflow, actions):
    if not isinstance(actions, list) or not 1 <= len(actions) <= 100:
        raise AutomationError("actions_must_be_array_of_1_to_100_items")
    allowed = {"launch", "terminate", "state", "screenshot", "inspect", "tap", "tap_id", "swipe", "scroll", "text"}
    # Validate the whole list before any side effect.
    if any(not isinstance(a, dict) or a.get("action") not in allowed for a in actions):
        raise AutomationError("unknown_action")
    device, bundle = workflow.device, workflow.bundle_id
    for i, item in enumerate(actions):
        name = item["action"]
        def action():
            if name == "launch": return device.launch_app(bundle)
            if name == "terminate": return device.terminate_app(bundle)
            if name == "state": return device.app_state(bundle)
            if name == "screenshot": return device.screenshot(workflow.path / f"action-{i:03}.png")
            if name == "inspect": return device.inspect_ui()
            if name == "tap": return device.tap(item["x"], item["y"])
            if name == "tap_id": return device.tap_id(item["id"])
            if name == "swipe": return device.swipe(item["start"], item["end"], item.get("duration", 0.5))
            if name == "scroll": return device.scroll(item["direction"])
            if name == "text": return device.text(item["id"], item["text"])
        result = workflow.step(f"action_{i}_{name}", action)
        if name in ("inspect", "state", "screenshot"):
            save_json(workflow.path / f"action-{i:03}.json", result)


def main(argv=None):
    args = parser().parse_args(argv)
    os.umask(0o077)
    try:
        if args.command == "doctor":
            result = doctor()
            print(json.dumps(result))
            return 2 if result["blockers"] else 0
        if args.command == "compare-images":
            from .images import compare_images
            result = compare_images(args.baseline, args.candidate, args.pixel_threshold, args.changed_fraction, args.crop)
            print(json.dumps(result))
            return 0 if result["status"] == "within_threshold" else 1
        if args.command == "summarize-telemetry":
            from .telemetry import export_trace
            result = export_trace(args.trace, args.output, args.budget_ms)
            print(json.dumps(result))
            return 0
        native = DeviceControl()
        if args.command == "devices":
            print(json.dumps({"devices": native.devices()}))
            return 0
        if args.command == "build":
            from .build import build_app
            result = build_app(ROOT, args.bundle_id, args.team, args.configuration,
                               args.automation, args.unsigned, args.derived_data, args.setting)
            print(json.dumps(result))
            return 0
        info = native.select(args.udid, args.transport)
        if args.command == "device-check":
            print(json.dumps({"status": "connected", "device": info}))
            return 0
        with reserve_device(info["udid"], "cli:" + args.command) as lease:
            native.require_unlocked(info["udid"])
            if args.command == "install":
                print(json.dumps(native.install_app(info["udid"], args.app, args.bundle_id)))
                return 0
            path = new_run(args.output)
            device = AppiumController(args.server)
            workflow = Run(device, native, info, args.bundle_id, path)
            workflow.report["reservation"] = lease
            connection_started = time.time()
            try:
                workflow.step("connect", lambda: device.connect(info["udid"], args.bundle_id, args.team, args.wda_bundle))
                if args.command == "smoke":
                    result = workflow.smoke(args.frontend)
                elif args.command == "jit-test":
                    from .jit_probe import probe
                    result = probe(workflow)
                elif args.command == "game-checkpoint":
                    from .checkpoints import wait_for_portal_menu
                    workflow.require_state(4)
                    workflow.report["game_checkpoint"] = workflow.step("portal_menu_checkpoint",
                        lambda: wait_for_portal_menu(device, path, seconds=args.seconds))
                    workflow.report["status"] = "passed"
                    result = workflow.finish(terminate=False)
                elif args.command == "game-command":
                    from .game_control import command
                    workflow.require_state(4)
                    reply = workflow.step("game_command", lambda: command(device, args.operation,
                        library_id=args.library_id, steam_app_id=args.steam_app_id, request_id=args.request_id))
                    workflow.report["game_command"] = reply
                    workflow.report["status"] = "failed" if reply["status"] == "rejected" else "passed"
                    if reply["status"] == "rejected": workflow.report["error"] = reply.get("code")
                    result = workflow.finish(terminate=False)
                else:
                    try:
                        execute_actions(workflow, json.loads(Path(args.file).read_text()))
                        workflow.report["status"] = "passed"
                    except Exception:
                        workflow.report["status"] = "failed"
                        raise
                    finally:
                        result = workflow.finish(terminate=False)
            except Exception as exc:
                workflow.report["status"] = "failed"
                workflow.report["error"] = str(exc) if isinstance(exc, AutomationError) else type(exc).__name__
                # A session may not exist, so don't try a second install or guessed device.
                if device.session:
                    result = workflow.finish(terminate=False)
                else:
                    from .startup_evidence import wda_startup_evidence
                    workflow.report["evidence"]["wda_startup"] = wda_startup_evidence(connection_started)
                    result = workflow.report
                    save_json(path / "report.json", result)
            print(json.dumps({"status": result["status"], "report": str(path / "report.json"),
                              "steps": result["steps"]}))
            return 0 if result["status"] == "passed" else 1
    except (AutomationError, OSError, ValueError) as exc:
        error = str(exc) if isinstance(exc, AutomationError) else type(exc).__name__
        print(json.dumps({"status": "blocked", "error": error}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
