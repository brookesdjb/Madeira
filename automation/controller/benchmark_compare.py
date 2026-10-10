"""Compare independent benchmark iterations offline; never attribute a difference to source alone."""
import json
import math
from pathlib import Path
import random
import statistics

from .device import AutomationError
from .workflows import new_run, save_json

MAX_BYTES = 1024 * 1024
MAX_ITERATIONS = 200
# Direction says which way is better. Submission cadence is not visible FPS (see benchmarks.md).
METRICS = {
    "submission_interval_p50_ms": "lower", "submission_interval_p95_ms": "lower",
    "submission_interval_p99_ms": "lower", "submission_rate_hz": "higher",
    "loading_ms": "lower", "footprint_peak_bytes": "lower", "mean_cpu_cores": "lower",
}
CONDITIONS = {"device_model", "os_version", "game", "scene", "resolution", "settings_digest",
              "runtime_config_digest", "capture_policy", "cache_phase"}
CACHE_PHASES = {"cold", "disk_warm", "process_warm"}
THERMAL = {"nominal", "fair", "serious", "critical"}
OUTCOMES = {"completed", "startup_failed", "jit_failed", "disconnected", "crashed", "timed_out"}
VISUAL = {"within_threshold", "review", "inconclusive", None}
FIELDS = {"schema_version", "conditions", "source", "order_index", "outcome", "thermal_state_start",
          "thermal_state_end", "visual_status", "metrics"}


def _integer(value, minimum=0):
    return type(value) is int and minimum <= value <= 2**63 - 1


def validate_iteration(value):
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise AutomationError("invalid_iteration_fields")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise AutomationError("unsupported_iteration_schema")
    conditions = value["conditions"]
    if (not isinstance(conditions, dict) or set(conditions) != CONDITIONS
            or not all(isinstance(v, str) and 1 <= len(v) <= 128 for v in conditions.values())
            or conditions["cache_phase"] not in CACHE_PHASES):
        raise AutomationError("invalid_iteration_conditions")
    source = value["source"]
    if (not isinstance(source, dict) or set(source) != {"commit", "dirty", "binary_sha256"}
            or not isinstance(source["commit"], str) or len(source["commit"]) != 40
            or type(source["dirty"]) is not bool or not isinstance(source["binary_sha256"], str)
            or len(source["binary_sha256"]) != 64):
        raise AutomationError("invalid_iteration_source")
    if not _integer(value["order_index"]):
        raise AutomationError("invalid_iteration_order")
    if value["outcome"] not in OUTCOMES or value["visual_status"] not in VISUAL:
        raise AutomationError("invalid_iteration_outcome")
    if value["thermal_state_start"] not in THERMAL or value["thermal_state_end"] not in THERMAL:
        raise AutomationError("invalid_iteration_thermal_state")
    metrics = value["metrics"]
    if not isinstance(metrics, dict) or not set(metrics) <= set(METRICS):
        raise AutomationError("invalid_iteration_metrics")
    for metric in metrics.values():
        if metric is not None and (type(metric) not in (int, float) or not math.isfinite(metric) or metric < 0):
            raise AutomationError("invalid_iteration_metric_value")
    if value["outcome"] != "completed" and any(v is not None for v in metrics.values()):
        # A failed run's partial numbers must not enter a distribution.
        raise AutomationError("failed_iteration_has_metrics")
    return value


def load_iteration(path):
    try:
        with Path(path).open("rb") as source:
            raw = source.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError()
        def unique(pairs):
            result = {}
            for key, item in pairs:
                if key in result:
                    raise ValueError()
                result[key] = item
            return result
        value = json.loads(raw, object_pairs_hook=unique)
    except (OSError, ValueError, RecursionError):
        raise AutomationError("unreadable_iteration_json") from None
    return validate_iteration(value)


def _uniform(iterations, key):
    values = {json.dumps(i[key], sort_keys=True) for i in iterations}
    return json.loads(values.pop()) if len(values) == 1 else None


def _median_difference_interval(base, cand, resamples, seed):
    # Independent bootstrap of the relative median difference; iterations, not frames, are the unit.
    rng = random.Random(seed)
    observed = []
    for _ in range(resamples):
        b = statistics.median(rng.choices(base, k=len(base)))
        c = statistics.median(rng.choices(cand, k=len(cand)))
        observed.append(c / b - 1 if b else math.inf)
    observed.sort()
    return observed[int(0.025 * resamples)], observed[math.ceil(0.975 * resamples) - 1]


def _compare_metric(name, base, cand, min_iterations, min_effect, max_cv, resamples, seed):
    result = {"metric": name, "better": METRICS[name], "baseline_n": len(base), "candidate_n": len(cand)}
    if len(base) < min_iterations or len(cand) < min_iterations:
        return {**result, "verdict": "inconclusive", "reason": "insufficient_iterations"}
    result["baseline_median"], result["candidate_median"] = statistics.median(base), statistics.median(cand)
    cv = {}
    for side, values in (("baseline", base), ("candidate", cand)):
        mean = statistics.fmean(values)
        cv[side] = statistics.stdev(values) / mean if mean else math.inf
    result["coefficient_of_variation"] = cv
    if not result["baseline_median"]:
        return {**result, "verdict": "inconclusive", "reason": "zero_baseline"}
    result["relative_median_difference"] = result["candidate_median"] / result["baseline_median"] - 1
    low, high = _median_difference_interval(base, cand, resamples, seed)
    result["bootstrap_95_interval"] = [low, high]
    if max(cv.values()) > max_cv:
        return {**result, "verdict": "inconclusive", "reason": "too_noisy"}
    if -min_effect < low and high < min_effect:
        return {**result, "verdict": "no_meaningful_difference"}
    if low >= min_effect or high <= -min_effect:
        worse = (low > 0) == (METRICS[name] == "lower")
        return {**result, "verdict": "regressed" if worse else "improved"}
    return {**result, "verdict": "inconclusive", "reason": "interval_spans_threshold"}


def compare(baseline, candidate, min_iterations=5, min_effect=0.03, max_cv=0.15, resamples=2000, seed=1):
    if type(min_iterations) is not int or not 3 <= min_iterations <= MAX_ITERATIONS:
        raise AutomationError("invalid_min_iterations")
    for value, upper in ((min_effect, 1), (max_cv, 10)):
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= upper:
            raise AutomationError("invalid_comparison_threshold")
    if not 1 <= len(baseline) <= MAX_ITERATIONS or not 1 <= len(candidate) <= MAX_ITERATIONS:
        raise AutomationError("invalid_iteration_count")
    report = {"schema_version": 1, "attribution": "not_established",
              "note": "Differences can come from device, thermal, cache or scene variation as well as source changes.",
              "caveats": []}
    # Conditions must be identical everywhere, otherwise nothing is comparable.
    sides = {"baseline": baseline, "candidate": candidate}
    conditions = {side: _uniform(items, "conditions") for side, items in sides.items()}
    if None in conditions.values():
        return {**report, "status": "inconclusive", "reason": "conditions_vary_within_side"}
    mismatched = sorted(k for k in CONDITIONS if conditions["baseline"][k] != conditions["candidate"][k])
    report["conditions"] = conditions["baseline"]
    if mismatched:
        return {**report, "status": "inconclusive", "reason": "conditions_mismatch", "mismatched_conditions": mismatched}
    for side, items in sides.items():
        source = _uniform(items, "source")
        if source is None:
            return {**report, "status": "inconclusive", "reason": f"{side}_source_varies"}
        report[f"{side}_source"] = source
        if source["dirty"]:
            report["caveats"].append(f"{side}_source_dirty")
    orders = [i["order_index"] for i in baseline + candidate]
    if len(set(orders)) != len(orders):
        raise AutomationError("duplicate_iteration_order")
    # Blocked AAA..BBB order lets thermal or cache drift masquerade as a source effect.
    first_candidate = min(i["order_index"] for i in candidate)
    last_baseline = max(i["order_index"] for i in baseline)
    first_baseline = min(i["order_index"] for i in baseline)
    last_candidate = max(i["order_index"] for i in candidate)
    report["order"] = "blocked" if last_baseline < first_candidate or last_candidate < first_baseline else "interleaved"
    usable, outcomes = {}, {}
    for side, items in sides.items():
        hot = [i for i in items if {i["thermal_state_start"], i["thermal_state_end"]} & {"serious", "critical"}]
        outcomes[side] = {"iterations": len(items),
                          "by_outcome": {o: sum(i["outcome"] == o for i in items) for o in sorted(OUTCOMES)},
                          "visual_review": sum(i["visual_status"] == "review" for i in items),
                          "excluded_thermal": len(hot)}
        usable[side] = [i for i in items if i["outcome"] == "completed" and i not in hot]
    report["outcomes"] = outcomes
    failures = {side: len(items) - outcomes[side]["by_outcome"]["completed"] for side, items in sides.items()}
    results = []
    for name in METRICS:
        base = [i["metrics"][name] for i in usable["baseline"] if i["metrics"].get(name) is not None]
        cand = [i["metrics"][name] for i in usable["candidate"] if i["metrics"].get(name) is not None]
        if base or cand:
            results.append(_compare_metric(name, base, cand, min_iterations, min_effect, max_cv, resamples, seed))
    report["metrics"] = results
    verdicts = {r["verdict"] for r in results}
    if report["order"] == "blocked":
        report["caveats"].append("blocked_order_verdicts_capped")
        for r in results:
            if r["verdict"] in ("improved", "regressed"):
                r["verdict"], r["reason"] = "inconclusive", "blocked_order"
        verdicts = {r["verdict"] for r in results}
    if failures["candidate"] > failures["baseline"] or outcomes["candidate"]["visual_review"] > outcomes["baseline"]["visual_review"]:
        status = "review"
    elif "regressed" in verdicts:
        status = "regressed"
    elif not results or "inconclusive" in verdicts:
        status = "inconclusive"
    elif "improved" in verdicts:
        status = "improved"
    else:
        status = "no_meaningful_difference"
    return {**report, "status": status,
            "thresholds": {"min_iterations": min_iterations, "min_effect": min_effect, "max_cv": max_cv,
                           "resamples": resamples, "seed": seed}}


def export_comparison(baseline_paths, candidate_paths, output, **options):
    result = compare([load_iteration(p) for p in baseline_paths], [load_iteration(p) for p in candidate_paths], **options)
    destination = new_run(output)
    save_json(destination / "benchmark-comparison.json", result)
    return {"status": result["status"], "report_path": str(destination / "benchmark-comparison.json")}
