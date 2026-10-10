"""Validate a bounded native submission trace; never infer GPU/display timing."""
import json
import math
from pathlib import Path

from .device import AutomationError
from .workflows import new_run, save_json

MAX_BYTES = 32 * 1024 * 1024
MAX_SAMPLES = 250_000  # 15 minutes at 240 submissions/sec, with headroom.
FIELDS = {"schema_version", "clock", "scope", "capture_id", "complete", "dropped_samples", "samples"}


def _integer(value, minimum=0):
    return type(value) is int and minimum <= value <= 2**63 - 1


def summarize(trace, budget_ms=1000 / 60):
    # Contract intentionally covers only the existing native Present boundary.
    # CPU roles, GPU command buffers and visible frames need separate producers.
    if not isinstance(trace, dict) or set(trace) != FIELDS:
        raise AutomationError("invalid_telemetry_fields")
    if type(trace["schema_version"]) is not int or trace["schema_version"] != 1:
        raise AutomationError("unsupported_telemetry_schema")
    if trace["clock"] != "clock_monotonic_ns" or trace["scope"] != "present_submission":
        raise AutomationError("unsupported_telemetry_clock_or_scope")
    capture = trace["capture_id"]
    if not isinstance(capture, str) or not 1 <= len(capture) <= 64 or not all(c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in capture):
        raise AutomationError("invalid_telemetry_capture_id")
    if type(trace["complete"]) is not bool or not _integer(trace["dropped_samples"]):
        raise AutomationError("invalid_telemetry_capture_state")
    samples = trace["samples"]
    if not isinstance(samples, list) or not 2 <= len(samples) <= MAX_SAMPLES:
        raise AutomationError("invalid_telemetry_sample_count")
    if type(budget_ms) not in (int, float) or not math.isfinite(budget_ms) or budget_ms <= 0:
        raise AutomationError("invalid_telemetry_budget")
    previous = None
    intervals = []
    for sample in samples:
        if not isinstance(sample, dict) or set(sample) != {"sequence", "timestamp_ns"} or not _integer(sample["sequence"], 1) or not _integer(sample["timestamp_ns"]):
            raise AutomationError("invalid_telemetry_sample")
        if previous is not None:
            if sample["sequence"] != previous["sequence"] + 1:
                raise AutomationError("noncontiguous_telemetry_sequence")
            delta = sample["timestamp_ns"] - previous["timestamp_ns"]
            if delta <= 0:
                raise AutomationError("nonmonotonic_telemetry_clock")
            intervals.append(delta / 1_000_000)
        previous = sample
    if not trace["complete"] or trace["dropped_samples"]:
        raise AutomationError("incomplete_telemetry_no_percentiles")
    ordered = sorted(intervals)
    def percentile(q):
        return ordered[math.ceil(q * len(ordered)) - 1]
    elapsed_ms = math.fsum(intervals)
    return {"schema_version": 1, "capture_id": capture, "clock": trace["clock"], "scope": trace["scope"],
            "samples": len(samples), "intervals": len(intervals), "elapsed_ms": elapsed_ms,
            "submission_rate_hz": len(intervals) * 1000 / elapsed_ms,
            "submission_interval_ms": {"mean": elapsed_ms / len(intervals), "p50": percentile(.5),
                "p95": percentile(.95), "p99": percentile(.99), "max": ordered[-1]},
            "percentile_method": "nearest_rank", "budget_ms": budget_ms,
            "over_budget_submission_intervals": sum(x > budget_ms for x in intervals),
            "visible_frame_interval_ms": None, "cpu_encode_ms": None, "cpu_submit_ms": None,
            "gpu_execution_ms": None, "per_role_cpu": None,
            "hardware_validation": "not_established_by_import"}


def load_trace(path):
    # A bounded read handles files growing after stat and avoids loading huge JSON.
    try:
        with Path(path).open("rb") as source:
            data = source.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise AutomationError("telemetry_file_too_large")
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise AutomationError("duplicate_telemetry_field")
                result[key] = value
            return result
        return json.loads(data, object_pairs_hook=unique)
    except (OSError, ValueError, RecursionError):
        raise AutomationError("unreadable_telemetry_json") from None


def export_trace(path, output, budget_ms=1000 / 60):
    trace = load_trace(path)
    result = summarize(trace, budget_ms)
    destination = new_run(output)
    # Export validated fields only, never arbitrary input paths or runtime logs.
    save_json(destination / "submission-trace.json", trace)
    save_json(destination / "telemetry-summary.json", result)
    return {"status": "exported", "report_path": str(destination / "telemetry-summary.json"),
            "scope": result["scope"], "hardware_validation": result["hardware_validation"]}
