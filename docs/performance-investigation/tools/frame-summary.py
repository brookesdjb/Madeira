#!/usr/bin/env python3
"""Summarize exported per-frame CSV; does not collect device measurements.

Required: frame_ms. Optional: cpu_ms, gpu_ms. One row per *rendered* frame.
Percentiles use nearest rank. CPU/GPU values must already be correlated to frames.
"""
import argparse
import csv
import json
import math
from pathlib import Path


def percentile(values, q):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)]


def summarize(path, budget):
    columns = {key: [] for key in ("frame_ms", "cpu_ms", "gpu_ms")}
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or "frame_ms" not in reader.fieldnames:
            raise ValueError("CSV requires frame_ms")
        for line, row in enumerate(reader, 2):
            if None in row:
                raise ValueError(f"line {line}: extra CSV fields")
            for key, values in columns.items():
                raw = row.get(key)
                if raw is None or not raw.strip():
                    if key == "frame_ms":
                        raise ValueError(f"line {line}: missing frame_ms")
                    continue
                value = float(raw)
                if not math.isfinite(value) or value < 0 or (key == "frame_ms" and value == 0):
                    raise ValueError(f"line {line}: invalid {key}")
                values.append(value)
    if not columns["frame_ms"]:
        raise ValueError("CSV contains no frames")
    result = {"input": str(path), "percentile_method": "nearest rank", "metrics": {}}
    for key, values in columns.items():
        if values:
            result["metrics"][key] = {
                "samples": len(values), "mean": math.fsum(values) / len(values),
                "p50": percentile(values, .50), "p95": percentile(values, .95),
                "p99": percentile(values, .99), "max": max(values),
            }
    frames = columns["frame_ms"]
    result.update(frames=len(frames), elapsed_ms=math.fsum(frames),
                  throughput_fps=1000 * len(frames) / math.fsum(frames),
                  budget_ms=budget, over_budget_frames=sum(x > budget for x in frames))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--budget-ms", type=float, default=1000 / 60)
    args = parser.parse_args()
    try:
        if not math.isfinite(args.budget_ms) or args.budget_ms <= 0:
            raise ValueError("budget must be positive and finite")
        print(json.dumps(summarize(args.csv, args.budget_ms), indent=2, allow_nan=False))
    except (ValueError, OSError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
