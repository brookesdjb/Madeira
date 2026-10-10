"""Bounded screenshot evidence tied to run, source, game and checkpoint; offline comparison."""
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
import tempfile

from PIL import Image
from .device import AutomationError
from .images import compare_images
from .workflows import new_run, save_json

KINDS = {"on_demand", "post_input", "periodic", "failure"}
POLICIES = {"functional", "timing_baseline"}
MANIFEST = "captures.json"
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
LABEL = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
RUN_FIELDS = {"run_id", "source_commit", "source_dirty", "game", "capture_policy"}
ENTRY_FIELDS = {"index", "kind", "checkpoint", "file", "sha256", "bytes", "width", "height",
                "monotonic_ns_before", "monotonic_ns_after", "captured_at"}


def _label(value, error):
    if not isinstance(value, str) or not LABEL.match(value):
        raise AutomationError(error)
    return value


def _validate_run(run):
    if not isinstance(run, dict) or set(run) != RUN_FIELDS:
        raise AutomationError("invalid_capture_run_fields")
    _label(run["run_id"], "invalid_capture_run_id")
    _label(run["game"], "invalid_capture_game")
    if run["capture_policy"] not in POLICIES:
        raise AutomationError("invalid_capture_policy")
    if run["source_commit"] is not None and not re.fullmatch(r"[0-9a-f]{40}", str(run["source_commit"])):
        raise AutomationError("invalid_capture_source_commit")
    if run["source_dirty"] is not None and type(run["source_dirty"]) is not bool:
        raise AutomationError("invalid_capture_source_dirty")


def _digest(path):
    hasher = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            hasher.update(block)
    return hasher.hexdigest()


class CaptureLog:
    """Owns captures.json in one run directory. Limits are checked before any capture."""

    def __init__(self, run_path, run, max_captures=200, max_bytes=256 * 1024 * 1024,
                 periodic_interval_s=5.0, private_checkpoints=(), clock=time.monotonic_ns):
        _validate_run(run)
        if type(max_captures) is not int or not 1 <= max_captures <= 10_000:
            raise AutomationError("invalid_capture_limit")
        if type(max_bytes) is not int or max_bytes <= 0:
            raise AutomationError("invalid_capture_storage_budget")
        if type(periodic_interval_s) not in (int, float) or not math.isfinite(periodic_interval_s) or periodic_interval_s < 1:
            raise AutomationError("invalid_periodic_interval")
        self.path, self.run, self.clock = Path(run_path), dict(run), clock
        self.max_captures, self.max_bytes = max_captures, max_bytes
        self.periodic_interval_ns = int(periodic_interval_s * 1e9)
        self.private = {_label(c, "invalid_private_checkpoint") for c in private_checkpoints}
        self.entries, self.used_bytes, self.last_periodic = [], 0, None
        # Claim the manifest exclusively before writing; reusing a run must
        # never erase previously collected evidence, even via a second writer.
        try:
            with (self.path / MANIFEST).open('xb') as claim:
                os.fchmod(claim.fileno(), 0o600)
        except FileExistsError:
            raise AutomationError("capture_manifest_exists") from None
        self._save()

    def record(self, kind, checkpoint, capture):
        """capture(path) writes one PNG, e.g. AppiumController.screenshot."""
        if kind not in KINDS:
            raise AutomationError("invalid_capture_kind")
        _label(checkpoint, "invalid_capture_checkpoint")
        # Sign-in and account screens are never captured, so they can't leak via evidence.
        if checkpoint in self.private:
            raise AutomationError("private_screen_not_captured")
        before = self.clock()
        if kind == "periodic":
            if self.run["capture_policy"] == "timing_baseline":
                raise AutomationError("periodic_capture_disabled_for_timing_baseline")
            if self.last_periodic is not None and before - self.last_periodic < self.periodic_interval_ns:
                raise AutomationError("periodic_capture_rate_limited")
        if len(self.entries) >= self.max_captures:
            raise AutomationError("capture_limit_reached")
        if self.used_bytes >= self.max_bytes:
            raise AutomationError("capture_storage_budget_exceeded")
        name = f"capture-{len(self.entries):04}-{kind}-{checkpoint}.png"
        target = self.path / name
        if target.exists():
            raise AutomationError("capture_file_exists")
        capture(target)
        after = self.clock()
        try:
            size = target.stat().st_size
            if self.used_bytes + size > self.max_bytes:
                # Only our own just-written file is removed; earlier evidence is kept.
                target.unlink()
                raise AutomationError("capture_storage_budget_exceeded")
            with Image.open(target) as image:
                if image.format != "PNG":
                    raise AutomationError("capture_not_png")
                width, height = image.size
            os.chmod(target, 0o600)
        except OSError:
            raise AutomationError("capture_unreadable") from None
        if kind == "periodic":
            self.last_periodic = before
        entry = {"index": len(self.entries), "kind": kind, "checkpoint": checkpoint, "file": name,
                 "sha256": _digest(target), "bytes": size, "width": width, "height": height,
                 "monotonic_ns_before": before, "monotonic_ns_after": after,
                 "captured_at": datetime.now(timezone.utc).isoformat()}
        self.entries.append(entry)
        self.used_bytes += size
        self._save()
        return entry

    def _save(self):
        value = {"schema_version": 1, "run": self.run, "limits": {
            "max_captures": self.max_captures, "max_bytes": self.max_bytes,
            "periodic_interval_ns": self.periodic_interval_ns},
            "private_checkpoints": sorted(self.private), "captures": self.entries}
        # A unique private temporary avoids overwriting an earlier .tmp file.
        with tempfile.NamedTemporaryFile(mode='w', dir=self.path, prefix='.captures-', delete=False) as target:
            temporary = Path(target.name)
            try:
                json.dump(value, target, indent=2)
                target.flush()
                os.replace(temporary, self.path / MANIFEST)
            finally:
                temporary.unlink(missing_ok=True)



def load_manifest(path):
    path = Path(path)
    try:
        with path.open("rb") as source:
            raw = source.read(MAX_MANIFEST_BYTES + 1)
        if len(raw) > MAX_MANIFEST_BYTES:
            raise ValueError()
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError()
                result[key] = value
            return result
        value = json.loads(raw, object_pairs_hook=unique)
    except (OSError, ValueError, RecursionError):
        raise AutomationError("invalid_capture_manifest") from None
    if (not isinstance(value, dict) or set(value) != {"schema_version", "run", "limits", "private_checkpoints", "captures"}
            or type(value["schema_version"]) is not int or value["schema_version"] != 1
            or not isinstance(value["captures"], list)):
        raise AutomationError("capture_manifest_contract_mismatch")
    _validate_run(value["run"])
    for entry in value["captures"]:
        if not isinstance(entry, dict) or set(entry) != ENTRY_FIELDS or entry["kind"] not in KINDS:
            raise AutomationError("invalid_capture_entry")
        _label(entry["checkpoint"], "invalid_capture_entry")
        # Files must be siblings of the manifest; reject any traversal.
        if not isinstance(entry["file"], str) or not re.fullmatch(r"capture-[0-9]{4}-[a-z_]+-[A-Za-z0-9_-]{1,64}\.png", entry["file"]):
            raise AutomationError("invalid_capture_entry")
    return value


def _verified(manifest_path, entry):
    file = Path(manifest_path).parent / entry["file"]
    try:
        if _digest(file) != entry["sha256"]:
            raise AutomationError("capture_hash_mismatch")
    except OSError:
        raise AutomationError("capture_missing") from None
    return file


def load_calibration(path):
    try:
        value = json.loads(Path(path).read_text())
    except (OSError, ValueError, RecursionError):
        raise AutomationError("invalid_visual_calibration") from None
    if (not isinstance(value, dict) or set(value) != {"schema_version", "game", "checkpoints"} or value["schema_version"] != 1
            or not isinstance(value["checkpoints"], dict)):
        raise AutomationError("visual_calibration_contract_mismatch")
    _label(value["game"], "invalid_visual_calibration")
    allowed = {"crop", "masks", "pixel_threshold", "changed_fraction", "calibrated_from"}
    for name, item in value["checkpoints"].items():
        _label(name, "invalid_visual_calibration")
        if not isinstance(item, dict) or not set(item) <= allowed or not isinstance(item.get("calibrated_from"), str):
            raise AutomationError("invalid_visual_calibration")
    return value


def compare_captures(baseline_manifest, candidate_manifest, output, calibration=None):
    """Pairs the latest on-demand/post-input capture per checkpoint; never a source regression verdict."""
    base, cand = load_manifest(baseline_manifest), load_manifest(candidate_manifest)
    if base["run"]["game"] != cand["run"]["game"]:
        raise AutomationError("capture_game_mismatch")
    if calibration is not None and calibration["game"] != base["run"]["game"]:
        raise AutomationError("visual_calibration_game_mismatch")
    def latest(manifest):
        result = {}
        for entry in manifest["captures"]:
            if entry["kind"] in ("on_demand", "post_input"):
                result[entry["checkpoint"]] = entry
        return result
    left, right = latest(base), latest(cand)
    destination = new_run(output)
    results = []
    for checkpoint in sorted(left.keys() | right.keys()):
        if checkpoint not in left or checkpoint not in right:
            results.append({"checkpoint": checkpoint, "status": "inconclusive", "reason": "checkpoint_missing",
                            "baseline": checkpoint in left, "candidate": checkpoint in right})
            continue
        settings = (calibration or {"checkpoints": {}})["checkpoints"].get(checkpoint)
        options = {k: v for k, v in (settings or {}).items() if k != "calibrated_from"}
        compared = compare_images(_verified(baseline_manifest, left[checkpoint]), _verified(candidate_manifest, right[checkpoint]),
                                  difference_output=destination / f"difference-{checkpoint}.png", **options)
        compared.update({"checkpoint": checkpoint, "calibrated": settings is not None,
                         "baseline_file": left[checkpoint]["file"], "candidate_file": right[checkpoint]["file"]})
        results.append(compared)
    statuses = [r["status"] for r in results]
    if not results:
        overall = "inconclusive"
    elif "review" in statuses:
        overall = "review"
    elif (base["run"]["capture_policy"] != cand["run"]["capture_policy"]
          or "inconclusive" in statuses or not all(r.get("calibrated") for r in results)):
        # Uncalibrated thresholds are a hint, not a rendering gate.
        overall = "inconclusive"
    else:
        overall = "within_threshold"
    report = {"schema_version": 1, "status": overall, "game": base["run"]["game"],
              "baseline_run": base["run"], "candidate_run": cand["run"],
              "capture_policy_matched": base["run"]["capture_policy"] == cand["run"]["capture_policy"],
              "checkpoints": results, "hardware_validation": "not_established_by_offline_comparison"}
    save_json(destination / "visual-report.json", report)
    return {"status": overall, "report_path": str(destination / "visual-report.json")}
