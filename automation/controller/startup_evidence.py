"""Classify local XCTest failures without publishing arbitrary diagnostic text."""
import json
from pathlib import Path

from .device import AutomationError, run


def classify_failures(summary):
    known = {
        "Timed out while enabling automation mode": "ui_automation_mode_timeout",
        "Developer Mode is disabled": "developer_mode_disabled",
        "not trusted": "developer_trust_required",
        "No profiles for": "provisioning_profile_missing",
        "device is locked": "device_locked",
    }
    result = set()
    for failure in summary.get("testFailures", []):
        message = failure.get("failureText", "")
        matches = [code for text, code in known.items() if text.lower() in message.lower()]
        result.update(matches or ["unclassified_xctest_failure"])
    return sorted(result)


def wda_startup_evidence(started_at, runner=run):
    logs = Path(__file__).resolve().parents[1] / "derived-data/wda/Logs/Test"
    bundles = [p for p in logs.glob("*.xcresult") if p.stat().st_mtime >= started_at]
    if not bundles:
        return {"available": False, "reason": "no_current_run_xctest_result"}
    bundle = max(bundles, key=lambda p: p.stat().st_mtime)
    try:
        summary = json.loads(runner(["xcrun", "xcresulttool", "get", "test-results", "summary",
                                     "--path", str(bundle)], 30))
        return {"available": True, "local_result_bundle": str(bundle),
                "failure_codes": classify_failures(summary),
                "result": summary.get("result") if summary.get("result") in ("Passed", "Failed", "Skipped") else "unknown"}
    except (AutomationError, OSError, ValueError, TypeError, AttributeError):
        return {"available": False, "reason": "xctest_summary_unavailable"}
