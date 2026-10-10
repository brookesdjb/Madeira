"""Compile with isolated outputs and retain private, useful failure evidence."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess

from .device import AutomationError
from .workflows import new_run, save_json


def inspect_app(app, automation, signed):
    app = Path(app)
    with (app / "Info.plist").open("rb") as handle:
        info = plistlib.load(handle)
    binaries = [app / info["CFBundleExecutable"]]
    if (app / "Madeira.debug.dylib").is_file():
        binaries.append(app / "Madeira.debug.dylib")
    contents = [p.read_bytes() for p in binaries]
    probe = any(b"madeira.automation.status" in b for b in contents)
    native_fixture = any(b"fex_automation_test_execute" in b for b in contents)
    # Check actual compiled app binaries, not just source #if declarations.
    if probe != automation:
        raise AutomationError("compiled_automation_surface_mismatch")
    if native_fixture != automation:
        raise AutomationError("compiled_automation_native_fixture_mismatch")
    if signed:
        verified = subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)],
                                  capture_output=True)
        if verified.returncode:
            raise AutomationError("app_signature_verification_failed")
    return {"bundle_id": info["CFBundleIdentifier"], "automation_surface": probe, "automation_native_fixture": native_fixture,
            "signature_verified": signed,
            "binary_sha256": {p.name: hashlib.sha256(b).hexdigest() for p, b in zip(binaries, contents)}}


def build_app(root, bundle_id, team=None, configuration="Debug", automation=False,
              unsigned=False, derived_data=None, settings=()):
    root = Path(root)
    if automation and configuration != "Debug":
        raise AutomationError("automation_requires_Debug_configuration")
    if not unsigned and not team:
        raise AutomationError("signed_build_requires_--team")
    for setting in settings:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\[sdk=[A-Za-z0-9*]+\])?=.*", setting):
            raise AutomationError("invalid_build_setting")
        if setting.split("=", 1)[0] in ("SWIFT_ACTIVE_COMPILATION_CONDITIONS", "CODE_SIGNING_ALLOWED"):
            raise AutomationError("use_automation_and_unsigned_flags_for_guard_settings")
    variant = "automation-debug" if automation else configuration.lower()
    derived = Path(derived_data).resolve() if derived_data else root / "automation/derived-data" / variant
    evidence = new_run(root / "automation/runs/builds")
    log = evidence / "xcodebuild.private.log"
    arguments = ["xcodebuild", "-project", str(root / "app/Madeira.xcodeproj"),
                 "-scheme", "Madeira", "-configuration", configuration,
                 "-destination", "generic/platform=iOS", "-derivedDataPath", str(derived),
                 f"MADEIRA_BUNDLE_IDENTIFIER={bundle_id}"]
    if team:
        arguments.append(f"DEVELOPMENT_TEAM={team}")
    if unsigned:
        arguments.append("CODE_SIGNING_ALLOWED=NO")
    if automation:
        arguments.append("SWIFT_ACTIVE_COMPILATION_CONDITIONS=$(inherited) DEBUG MADEIRA_AUTOMATION")
        arguments.append("OTHER_CPLUSPLUSFLAGS=$(inherited) -DMADEIRA_AUTOMATION=1")
    arguments.extend(settings)
    report = {"schema_version": 1, "configuration": configuration, "automation": automation,
              "signed": not unsigned, "hardware_validation": "NOT_PERFORMED",
              "clean_signed_build": not unsigned,
              "started_at": datetime.now(timezone.utc).isoformat(), "status": "running",
              "private_build_log": str(log)}
    try:
        report["source_commit"] = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
        report["source_dirty"] = bool(subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"], text=True))
        with log.open("w") as output:
            os.chmod(log, 0o600)
            # Existing bundle phases rewrite/re-sign nested resources every
            # build. Xcode can skip the outer CodeSign on an incremental run,
            # leaving an invalid resource seal despite BUILD SUCCEEDED. Clean
            # this variant's isolated products before signed builds so the
            # outer bundle is freshly sealed; never clean shared inputs.
            actions = ["clean", "build"] if not unsigned else ["build"]
            result = subprocess.run([*arguments, *actions], stdout=output, stderr=subprocess.STDOUT,
                                    timeout=1800, cwd=root)
        if result.returncode:
            raise AutomationError(f"xcodebuild_failed:exit_{result.returncode}:private_log:{log}")
        app = derived / "Build/Products" / (configuration + "-iphoneos") / "Madeira.app"
        report.update(inspect_app(app, automation, not unsigned))
        report.update({"status": "built", "app": str(app)})
        return report
    except subprocess.TimeoutExpired:
        report["error"] = "xcodebuild_timeout"
        raise AutomationError(f"xcodebuild_timeout:private_log:{log}") from None
    except Exception as exc:
        report["error"] = str(exc) if isinstance(exc, AutomationError) else type(exc).__name__
        raise
    finally:
        if "error" in report:
            report["status"] = "failed"
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        save_json(evidence / "report.json", report)
