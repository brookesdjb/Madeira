import json
from PIL import Image, ImageDraw
import pytest
from automation.controller import capture_evidence as c
from automation.controller.device import AutomationError

COMMIT = "a" * 40


def run(policy="functional", game="portal", run_id="r1"):
    return {"run_id": run_id, "source_commit": COMMIT, "source_dirty": False, "game": game, "capture_policy": policy}


def scene(colour="blue", hud=None):
    def capture(path):
        image = Image.new("RGB", (64, 48), "white")
        ImageDraw.Draw(image).rectangle((16, 12, 47, 35), fill=colour)
        if hud: ImageDraw.Draw(image).rectangle((0, 0, 63, 5), fill=hud)
        image.save(path)
    return capture


class Clock:
    def __init__(self): self.now = 0
    def __call__(self):
        self.now += 1_000_000_000
        return self.now


def log(path, **kw):
    path.mkdir(exist_ok=True)
    return c.CaptureLog(path, kw.pop("run", run()), clock=kw.pop("clock", Clock()), **kw)


def test_capture_is_associated_with_run_and_checkpoint(tmp_path):
    capture_log = log(tmp_path / "base")
    entry = capture_log.record("post_input", "main_menu", scene())
    manifest = c.load_manifest(tmp_path / "base/captures.json")
    assert manifest["run"]["source_commit"] == COMMIT and manifest["run"]["game"] == "portal"
    assert manifest["captures"] == [entry] and entry["checkpoint"] == "main_menu" and (entry["width"], entry["height"]) == (64, 48)
    assert entry["monotonic_ns_before"] < entry["monotonic_ns_after"]
    assert ((tmp_path / "base" / entry["file"]).stat().st_mode & 0o777) == 0o600


def test_private_checkpoint_never_invokes_capture(tmp_path):
    capture_log = log(tmp_path / "r", private_checkpoints=["steam_sign_in"])
    with pytest.raises(AutomationError, match="private_screen"):
        capture_log.record("on_demand", "steam_sign_in", lambda p: pytest.fail("captured private screen"))


def test_periodic_capture_bounded_and_disabled_for_timing(tmp_path):
    clock = Clock()
    capture_log = log(tmp_path / "r", clock=clock, periodic_interval_s=5)
    capture_log.record("periodic", "gameplay", scene())
    with pytest.raises(AutomationError, match="rate_limited"):
        capture_log.record("periodic", "gameplay", scene())
    clock.now += 10_000_000_000
    capture_log.record("periodic", "gameplay", scene())
    timing = log(tmp_path / "t", run=run("timing_baseline"))
    with pytest.raises(AutomationError, match="timing_baseline"):
        timing.record("periodic", "gameplay", lambda p: pytest.fail("captured during timing"))
    timing.record("on_demand", "gameplay", scene())


def test_count_and_storage_limits_keep_earlier_evidence(tmp_path):
    capture_log = log(tmp_path / "r", max_captures=1)
    capture_log.record("on_demand", "menu", scene())
    with pytest.raises(AutomationError, match="capture_limit"):
        capture_log.record("on_demand", "menu", lambda p: pytest.fail("over limit"))
    small = log(tmp_path / "s", max_bytes=10)
    with pytest.raises(AutomationError, match="storage_budget"):
        small.record("on_demand", "menu", scene())
    assert not list((tmp_path / "s").glob("*.png")) and c.load_manifest(tmp_path / "s/captures.json")["captures"] == []


def test_invalid_labels_and_kinds_rejected_before_capture(tmp_path):
    capture_log = log(tmp_path / "r")
    for kind, checkpoint in (("video", "menu"), ("on_demand", "../menu"), ("on_demand", "")):
        with pytest.raises(AutomationError):
            capture_log.record(kind, checkpoint, lambda p: pytest.fail("captured"))
    with pytest.raises(AutomationError, match="policy"):
        c.CaptureLog(tmp_path, run("sometimes"))


def baseline_and_candidate(tmp_path, candidate_scene):
    log(tmp_path / "base").record("on_demand", "menu", scene(hud="black"))
    log(tmp_path / "cand", run=run(run_id="r2")).record("on_demand", "menu", candidate_scene)
    return tmp_path / "base/captures.json", tmp_path / "cand/captures.json"


def calibration(tmp_path, **settings):
    path = tmp_path / "calibration.json"
    path.write_text(json.dumps({"schema_version": 1, "game": "portal", "checkpoints": {
        "menu": {"masks": [[0, 0, 64, 6]], "calibrated_from": "synthetic test", **settings}}}))
    return c.load_calibration(path)


def test_calibrated_comparison_writes_report_and_differences(tmp_path):
    base, cand = baseline_and_candidate(tmp_path, scene(hud="red"))
    result = c.compare_captures(base, cand, tmp_path / "out", calibration(tmp_path))
    assert result["status"] == "within_threshold"
    report = json.loads(open(result["report_path"]).read())
    assert report["checkpoints"][0]["calibrated"] and report["capture_policy_matched"]
    assert report["hardware_validation"] == "not_established_by_offline_comparison"
    assert len(list((tmp_path / "out").glob("*/difference-menu.png"))) == 1


def test_uncalibrated_comparison_is_only_inconclusive(tmp_path):
    base, cand = baseline_and_candidate(tmp_path, scene(hud="black"))
    assert c.compare_captures(base, cand, tmp_path / "out")["status"] == "inconclusive"


def test_rendering_change_needs_review(tmp_path):
    base, cand = baseline_and_candidate(tmp_path, scene("red", hud="black"))
    assert c.compare_captures(base, cand, tmp_path / "out", calibration(tmp_path))["status"] == "review"


def test_missing_checkpoint_and_game_mismatch(tmp_path):
    log(tmp_path / "base").record("on_demand", "menu", scene())
    capture_log = log(tmp_path / "cand", run=run(run_id="r2"))
    capture_log.record("on_demand", "menu", scene())
    capture_log.record("on_demand", "level_one", scene())
    result = c.compare_captures(tmp_path / "base/captures.json", tmp_path / "cand/captures.json", tmp_path / "out", calibration(tmp_path))
    assert result["status"] == "inconclusive"
    log(tmp_path / "other", run=run(game="borderlands")).record("on_demand", "menu", scene())
    with pytest.raises(AutomationError, match="game_mismatch"):
        c.compare_captures(tmp_path / "base/captures.json", tmp_path / "other/captures.json", tmp_path / "out")


def test_tampered_capture_and_manifest_rejected(tmp_path):
    base, cand = baseline_and_candidate(tmp_path, scene())
    entry = c.load_manifest(cand)["captures"][0]
    scene("red")(tmp_path / "cand" / entry["file"])
    with pytest.raises(AutomationError, match="hash_mismatch"):
        c.compare_captures(base, cand, tmp_path / "out")
    manifest = json.loads(cand.read_text())
    manifest["captures"][0]["file"] = "../base/" + entry["file"]
    cand.write_text(json.dumps(manifest))
    with pytest.raises(AutomationError, match="invalid_capture_entry"):
        c.load_manifest(cand)
    cand.write_text('{"schema_version": 1, "schema_version": 1}')
    with pytest.raises(AutomationError, match="invalid_capture_manifest"):
        c.load_manifest(cand)


def test_reopening_run_preserves_existing_manifest_and_images(tmp_path):
    folder = tmp_path / "run"
    first = log(folder)
    first.record("on_demand", "menu", scene())
    original = {p.name: p.read_bytes() for p in folder.iterdir()}
    with pytest.raises(AutomationError, match="manifest_exists"):
        log(folder)
    assert original == {p.name: p.read_bytes() for p in folder.iterdir()}


def test_different_capture_policies_cannot_pass_visual_gate(tmp_path):
    base, cand = baseline_and_candidate(tmp_path, scene(hud="black"))
    manifest = json.loads(cand.read_text())
    manifest["run"]["capture_policy"] = "timing_baseline"
    cand.write_text(json.dumps(manifest))
    assert c.compare_captures(base, cand, tmp_path / "out", calibration(tmp_path))["status"] == "inconclusive"
