import json
import pytest
from automation.controller import benchmark_compare as b
from automation.controller.cli import main
from automation.controller.device import AutomationError

BASE, CAND = "b" * 40, "c" * 40


def iteration(order, p95, commit=BASE, outcome="completed", thermal="nominal", visual=None, **conditions):
    return {"schema_version": 1,
            "conditions": {"device_model": "iPad17,1", "os_version": "26.7", "game": "portal", "scene": "menu",
                           "resolution": "2732x2048", "settings_digest": "s1", "runtime_config_digest": "r1",
                           "capture_policy": "timing_baseline", "cache_phase": "disk_warm", **conditions},
            "source": {"commit": commit, "dirty": False, "binary_sha256": commit[0] * 64},
            "order_index": order, "outcome": outcome, "thermal_state_start": "nominal", "thermal_state_end": thermal,
            "visual_status": visual,
            "metrics": {"submission_interval_p95_ms": p95 if outcome == "completed" else None}}


def paired(base_values, cand_values, **kw):
    # AB/BA interleaving: baseline on even order slots, candidate on odd.
    base = [iteration(2 * i, v) for i, v in enumerate(base_values)]
    cand = [iteration(2 * i + 1, v, CAND, **kw) for i, v in enumerate(cand_values)]
    return base, cand


def metric(report):
    return report["metrics"][0]


def test_clear_regression_and_improvement():
    base, cand = paired([20, 20.2, 19.9, 20.1, 20], [24, 24.3, 23.8, 24.1, 24])
    report = b.compare(base, cand)
    assert report["status"] == "regressed" and metric(report)["verdict"] == "regressed"
    assert report["attribution"] == "not_established" and report["order"] == "interleaved"
    assert b.compare(cand, base)["status"] == "improved"


def test_higher_is_better_metric_direction():
    base, cand = paired([1] * 5, [1] * 5)
    for i, v in zip(base, [60, 60.2, 59.9, 60.1, 60]): i["metrics"] = {"submission_rate_hz": v}
    for i, v in zip(cand, [50, 50.2, 49.9, 50.1, 50]): i["metrics"] = {"submission_rate_hz": v}
    assert b.compare(base, cand)["status"] == "regressed"


def test_equal_runs_have_no_meaningful_difference():
    values = [20, 20.1, 19.9, 20.05, 19.95]
    assert b.compare(*paired(values, values))["status"] == "no_meaningful_difference"


def test_too_few_iterations_inconclusive():
    report = b.compare(*paired([20, 20, 20], [30, 30, 30]))
    assert report["status"] == "inconclusive" and metric(report)["reason"] == "insufficient_iterations"


def test_noisy_data_inconclusive():
    report = b.compare(*paired([10, 30, 15, 25, 20], [12, 32, 17, 27, 22]))
    assert report["status"] == "inconclusive" and metric(report)["reason"] == "too_noisy"


def test_condition_mismatch_refused():
    base, cand = paired([20] * 5, [20] * 5)
    for i in cand: i["conditions"]["cache_phase"] = "cold"
    report = b.compare(base, cand)
    assert report["status"] == "inconclusive" and report["mismatched_conditions"] == ["cache_phase"]
    cand[0]["conditions"]["os_version"] = "26.8"
    assert b.compare(base, cand)["reason"] == "conditions_vary_within_side"


def test_blocked_order_caps_verdict():
    base = [iteration(i, v) for i, v in enumerate([20, 20.2, 19.9, 20.1, 20])]
    cand = [iteration(10 + i, v, CAND) for i, v in enumerate([24, 24.3, 23.8, 24.1, 24])]
    report = b.compare(base, cand)
    assert report["order"] == "blocked" and report["status"] == "inconclusive"
    assert metric(report)["reason"] == "blocked_order"


def test_thermal_iterations_excluded_and_counted():
    base, cand = paired([20, 20.2, 19.9, 20.1, 20, 20], [20, 20.1, 19.9, 20, 20.1, 20])
    cand[0]["thermal_state_end"] = "serious"
    report = b.compare(base, cand)
    assert report["outcomes"]["candidate"]["excluded_thermal"] == 1 and metric(report)["candidate_n"] == 5


def test_more_candidate_crashes_or_visual_reviews_need_review():
    base, cand = paired([20] * 6, [20] * 6)
    cand[-1] = iteration(11, None, CAND, outcome="crashed")
    report = b.compare(base, cand)
    assert report["status"] == "review" and report["outcomes"]["candidate"]["by_outcome"]["crashed"] == 1
    base, cand = paired([20] * 5, [20] * 5)
    cand[0]["visual_status"] = "review"
    assert b.compare(base, cand)["status"] == "review"


def test_invalid_records_rejected():
    good = iteration(0, 20)
    for change in ({"metrics": {"fps": 60}}, {"metrics": {"submission_interval_p95_ms": float("nan")}},
                   {"outcome": "crashed"}, {"order_index": -1}, {"extra": 1}, {"thermal_state_end": "hot"}):
        with pytest.raises(AutomationError):
            b.validate_iteration({**good, **change})
    with pytest.raises(AutomationError, match="duplicate_iteration_order"):
        b.compare([iteration(0, 20)] * 5, [iteration(0, 20, CAND)] * 5)


def test_cli_writes_report_and_uses_exit_status(tmp_path, capsys):
    base, cand = paired([20, 20.2, 19.9, 20.1, 20], [24, 24.3, 23.8, 24.1, 24])
    paths = {}
    for side, items in (("base", base), ("cand", cand)):
        paths[side] = []
        for n, item in enumerate(items):
            path = tmp_path / f"{side}-{n}.json"
            path.write_text(json.dumps(item))
            paths[side].append(str(path))
    code = main(["--output", str(tmp_path / "runs"), "benchmark-compare", "--baseline", *paths["base"], "--candidate", *paths["cand"]])
    result = json.loads(capsys.readouterr().out)
    assert code == 1 and result["status"] == "regressed"
    assert json.loads(open(result["report_path"]).read())["metrics"][0]["verdict"] == "regressed"
    (tmp_path / "dup.json").write_text('{"schema_version": 1, "schema_version": 1}')
    assert main(["--output", str(tmp_path / "runs"), "benchmark-compare", "--baseline", str(tmp_path / "dup.json"), "--candidate", *paths["cand"]]) == 2


@pytest.mark.parametrize("visual,status", [("review", "review"), ("inconclusive", "inconclusive")])
@pytest.mark.parametrize("side", ["baseline", "candidate", "both"])
def test_unresolved_visual_checks_never_pass(visual, status, side):
    base, cand = paired([20] * 5, [10] * 5)
    for items in ([base] if side == "baseline" else [cand] if side == "candidate" else [base, cand]):
        for item in items:
            item["visual_status"] = visual
    assert b.compare(base, cand)["status"] == status


def test_equal_failures_do_not_cancel_out():
    base, cand = paired([20] * 6, [10] * 6)
    base[-1] = iteration(10, None, outcome="crashed")
    cand[-1] = iteration(11, None, CAND, outcome="crashed")
    assert b.compare(base, cand)["status"] == "review"


def test_unchecked_visuals_are_explicitly_timing_only():
    report = b.compare(*paired([20] * 5, [10] * 5))
    assert report["status"] == "improved"
    assert "visual_acceptance_not_established" in report["caveats"]


def test_zero_metrics_produce_standard_json():
    for base_values, cand_values in (([0] * 5, [0] * 5), ([20] * 5, [0] * 5), ([0, 0, 20, 20, 20], [10] * 5)):
        json.dumps(b.compare(*paired(base_values, cand_values)), allow_nan=False)


@pytest.mark.parametrize("change", [{"outcome": []}, {"visual_status": {}}, {"thermal_state_end": []},
                                    {"metrics": {"submission_interval_p95_ms": float("nan")}}])
def test_public_compare_validates_records(change):
    base, cand = paired([20] * 5, [10] * 5)
    cand[0].update(change)
    with pytest.raises(AutomationError):
        b.compare(base, cand)


@pytest.mark.parametrize("options", [{"resamples": 0}, {"resamples": True}, {"resamples": 10001},
                                     {"seed": -1}, {"seed": True}])
def test_bootstrap_options_are_bounded(options):
    with pytest.raises(AutomationError):
        b.compare(*paired([20] * 5, [10] * 5), **options)


def test_flag_experiments_remain_fail_closed():
    base, cand = paired([20] * 5, [10] * 5, runtime_config_digest="w1-on")
    report = b.compare(base, cand)
    assert report["status"] == "inconclusive"
    assert report["mismatched_conditions"] == ["runtime_config_digest"]


@pytest.mark.parametrize("key,value", [("commit", "z" * 40), ("binary_sha256", "g" * 64)])
def test_source_hashes_must_be_hex(key, value):
    item = iteration(0, 20)
    item["source"][key] = value
    with pytest.raises(AutomationError, match="invalid_iteration_source"):
        b.validate_iteration(item)
