"""Small W3C/Appium client: keeps one session for a sequence of agent actions."""
from __future__ import annotations
import base64
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from .device import AutomationError, diagnostic_events

ELEMENT = "element-6066-11e4-a52e-4f735466cecf"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise AutomationError("appium_redirect_rejected")


class AppiumController:
    def __init__(self, url="http://127.0.0.1:4723", timeout=45):
        parsed = urllib.parse.urlparse(url)
        if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1")
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise AutomationError("appium_must_use_unauthenticated_loopback_HTTP")
        self.url, self.timeout, self.session = url.rstrip("/"), timeout, None
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, method, path, body=None, timeout=None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.url + path, data=data, method=method,
                                         headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=timeout or self.timeout) as response:
                result = json.load(response)
        except urllib.error.HTTPError as exc:
            # Only retain protocol error codes, never the server's arbitrary message.
            try:
                code = json.load(exc).get("value", {}).get("error", "webdriver_error")
            except (ValueError, AttributeError):
                code = "webdriver_error"
            allowed = {"no such element", "invalid session id", "timeout", "unknown command",
                       "invalid argument", "unknown error", "session not created"}
            raise AutomationError(code if code in allowed else "webdriver_error") from None
        except (OSError, ValueError) as exc:
            raise AutomationError("appium_unreachable_or_invalid_response") from exc
        if not isinstance(result, dict) or "value" not in result:
            raise AutomationError("invalid_webdriver_response")
        value = result["value"]
        if isinstance(value, dict) and "error" in value:
            raise AutomationError("webdriver_error")
        return value

    def connect(self, udid, bundle_id, team=None, wda_bundle=None):
        caps = {"platformName": "iOS", "appium:automationName": "XCUITest", "appium:udid": udid,
                "appium:bundleId": bundle_id, "appium:noReset": True, "appium:fullReset": False,
                "appium:autoLaunch": False, "appium:shouldTerminateApp": False,
                "appium:useNewWDA": False, "appium:newCommandTimeout": 180,
                "appium:waitForIdleTimeout": 1, "appium:showXcodeLog": False,
                "appium:printPageSourceOnFindFailure": False,
                "appium:derivedDataPath": str(Path(__file__).resolve().parents[1] / "derived-data/wda"),
                "appium:wdaLaunchTimeout": 120000, "appium:wdaConnectionTimeout": 45000,
                "appium:wdaStartupRetries": 1}
        if team:
            caps.update({"appium:xcodeOrgId": team, "appium:xcodeSigningId": "Apple Development"})
        if wda_bundle:
            caps["appium:updatedWDABundleId"] = wda_bundle
        result = self.request("POST", "/session", {"capabilities": {"alwaysMatch": caps}}, timeout=180)
        if not isinstance(result, dict) or not result.get("sessionId"):
            raise AutomationError("missing_session_id")
        self.session = urllib.parse.quote(result["sessionId"], safe="")

    def call(self, method, suffix, body=None):
        if not self.session:
            raise AutomationError("no_session")
        return self.request(method, f"/session/{self.session}{suffix}", body)

    def mobile(self, name, args):
        return self.call("POST", "/execute/sync", {"script": "mobile: " + name, "args": [args]})

    def close(self):
        if self.session:
            try:
                self.call("DELETE", "")
            finally:
                self.session = None

    def launch_app(self, bundle_id, arguments=None):
        return self.mobile("launchApp", {"bundleId": bundle_id, "arguments": arguments or []})

    def activate_app(self, bundle_id):
        return self.mobile("activateApp", {"bundleId": bundle_id})

    def terminate_app(self, bundle_id):
        return self.mobile("terminateApp", {"bundleId": bundle_id})

    def app_state(self, bundle_id):
        return self.mobile("queryAppState", {"bundleId": bundle_id})

    def find(self, identifier, timeout=10):
        deadline = time.monotonic() + timeout
        while True:
            try:
                item = self.call("POST", "/element", {"using": "accessibility id", "value": identifier})
                element = item[ELEMENT]
                # XCTest can return controls behind an onboarding sheet. Their
                # presence is not evidence that the requested page is usable.
                displayed = self.call("GET", f"/element/{element}/displayed")
                if displayed in (True, "true", "1", 1):
                    return element
                raise AutomationError("no such element")
            except AutomationError as exc:
                if str(exc) != "no such element" or time.monotonic() >= deadline:
                    raise
                time.sleep(0.2)

    def tap_id(self, identifier):
        return self.call("POST", f"/element/{self.find(identifier)}/click", {})

    def value(self, identifier):
        return self.call("GET", f"/element/{self.find(identifier)}/attribute/value")

    def text(self, identifier, text):
        return self.call("POST", f"/element/{self.find(identifier)}/value", {"text": text})

    @staticmethod
    def coordinate(value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise AutomationError("invalid_coordinate")
        return value

    def tap(self, x, y):
        return self.mobile("tap", {"x": self.coordinate(x), "y": self.coordinate(y)})

    def swipe(self, start, end, duration=0.5):
        if not isinstance(duration, (int, float)) or not math.isfinite(duration) or not 0.1 <= duration <= 10:
            raise AutomationError("invalid_swipe_duration")
        return self.mobile("dragFromToForDuration", {"fromX": self.coordinate(start[0]),
                            "fromY": self.coordinate(start[1]), "toX": self.coordinate(end[0]),
                            "toY": self.coordinate(end[1]), "duration": duration})

    def scroll(self, direction):
        if direction not in ("up", "down", "left", "right"):
            raise AutomationError("invalid_scroll_direction")
        return self.mobile("scroll", {"direction": direction})

    def screenshot(self, destination):
        data = base64.b64decode(self.call("GET", "/screenshot"), validate=True)
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise AutomationError("invalid_screenshot")
        Path(destination).write_bytes(data)
        return str(destination)

    def inspect_ui(self):
        # Never serialize text/password values or arbitrary labels from Steam UI.
        root = ET.fromstring(self.call("GET", "/source"))
        result = []
        for node in root.iter():
            attrs = {key: node.attrib[key] for key in ("type", "x", "y", "width", "height", "enabled", "visible")
                     if key in node.attrib}
            name = node.get("name", "")
            if name.startswith("madeira."):
                attrs["identifier"] = name
            if attrs:
                result.append(attrs)
        return result

    def get_logs(self):
        return diagnostic_events(json.dumps(self.call("POST", "/log", {"type": "syslog"})))

    def crash_report_count(self):
        # Device-wide historical reports are NOT attributable crash evidence.
        reports = self.call("POST", "/log", {"type": "crashlog"})
        return {"available_reports": len(reports), "attribution": "unverified"}
