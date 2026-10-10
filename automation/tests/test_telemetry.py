import json
import math
from pathlib import Path
import stat
import pytest
from automation.controller.device import AutomationError
from automation.controller import telemetry as t
from automation.controller import cli


def trace():
    return {"schema_version": 1, "clock": "clock_monotonic_ns", "scope": "present_submission",
            "capture_id": "fixture-1", "complete": True, "dropped_samples": 0,
            "samples": [{"sequence": n + 1, "timestamp_ns": ts} for n, ts in enumerate((0, 10_000_000, 30_000_000, 60_000_000))]}


def test_submission_units_percentiles_and_missing_gpu():
    result = t.summarize(trace(), 20)
    assert result['elapsed_ms'] == 60 and result['submission_rate_hz'] == 50
    assert result['intervals'] == 3 and result['over_budget_submission_intervals'] == 1
    assert result['submission_interval_ms'] == dict(mean=20, p50=20, p95=30, p99=30, max=30)
    for field in ('visible_frame_interval_ms', 'cpu_encode_ms', 'cpu_submit_ms', 'gpu_execution_ms', 'per_role_cpu'):
        assert result[field] is None


@pytest.mark.parametrize('field,value', [
    ('schema_version', True), ('scope', 'rendered_frame'), ('clock', 'wall_clock'),
    ('capture_id', 'private/token'), ('complete', False), ('complete', 1), ('dropped_samples', 1),
    ('dropped_samples', True), ('samples', []), ('samples', [{}]), ('samples', [{}, {}])])
def test_bad_contract_or_loss_never_produces_metrics(field, value):
    data = trace(); data[field] = value
    with pytest.raises(AutomationError): t.summarize(data)


@pytest.mark.parametrize('value', [0, -1, math.nan, math.inf, True])
def test_bad_budget(value):
    with pytest.raises(AutomationError): t.summarize(trace(), value)


@pytest.mark.parametrize('field,value', [('sequence', 5), ('sequence', True), ('timestamp_ns', 0), ('timestamp_ns', 2**63), ('timestamp_ns', 1.5)])
def test_counter_gaps_reset_and_invalid_clock_rejected(field, value):
    data = trace(); data['samples'][1][field] = value
    with pytest.raises(AutomationError): t.summarize(data)


def test_bounded_input_unknown_fields_and_duplicate_keys(tmp_path, monkeypatch):
    path = tmp_path / 'raw.json'
    data = trace(); data['token'] = 'must-never-export'
    path.write_text(json.dumps(data))
    with pytest.raises(AutomationError): t.export_trace(path, tmp_path / 'reports')
    assert not (tmp_path / 'reports').exists()
    path.write_text('{"schema_version":1,"schema_version":1}')
    with pytest.raises(AutomationError, match='duplicate'): t.load_trace(path)
    monkeypatch.setattr(t, 'MAX_BYTES', 8)
    with pytest.raises(AutomationError, match='too_large'): t.load_trace(path)


def test_sample_bound(monkeypatch):
    monkeypatch.setattr(t, 'MAX_SAMPLES', 3)
    with pytest.raises(AutomationError): t.summarize(trace())


def test_cli_is_offline_and_exports_private_files(tmp_path, monkeypatch, capsys):
    path = tmp_path / 'raw.json'; path.write_text(json.dumps(trace()))
    def forbidden(): raise AssertionError('offline import must not discover/connect to device')
    monkeypatch.setattr(cli, 'DeviceControl', forbidden)
    assert cli.main(['--output', str(tmp_path / 'reports'), 'summarize-telemetry', str(path)]) == 0
    result = json.loads(capsys.readouterr().out)
    report = Path(result['report_path'])
    assert stat.S_IMODE(report.stat().st_mode) == 0o600
    assert stat.S_IMODE(report.parent.stat().st_mode) == 0o700
    assert json.loads(report.read_text())['gpu_execution_ms'] is None
    assert 'raw.json' not in report.read_text()
