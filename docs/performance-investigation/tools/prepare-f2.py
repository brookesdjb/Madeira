#!/usr/bin/env python3
# Copyright 2026 125hz. GPL-3.0-or-later with the Madeira Converter Exception.
"""Print a bounded FEX_MAXINST experiment plan; never edits app configuration.

Output is a plan, not telemetry or execution evidence. Feed it to the accepted
harness only after agreeing its input format and physical correctness gates.
"""
import argparse
import json
import random

VALUES = (500, 1000, 5000)


def make_plan(game_id, scene, pairs, seed):
    for label, value in (("game identifier", game_id), ("scene", scene)):
        if not value.strip() or len(value) > 256 or any(ord(c) < 32 for c in value):
            raise ValueError(f"invalid {label}")
    if not 5 <= pairs <= 50:
        raise ValueError("pairs must be between 5 and 50")
    rng = random.Random(seed)
    trials = []
    for candidate in VALUES[:-1]:
        for phase in ("cold", "disk-warm"):
            orders = ["AB"] * ((pairs + 1) // 2) + ["BA"] * (pairs // 2)
            rng.shuffle(orders)
            for pair, order in enumerate(orders, 1):
                trials.append({"candidate_maxinst": candidate, "phase": phase,
                               "pair": pair, "order": order,
                               "maxinst_sequence": [5000 if arm == "A" else candidate for arm in order],
                               "fresh_app_process_each_arm": True,
                               "settle_seconds": 60, "measure_seconds": 180})
    return {"plan_version": 1, "status": "planned_not_executed", "game_id": game_id,
            "scene": scene, "seed": seed, "pairs_per_candidate_phase": pairs,
            "baseline_maxinst": 5000, "allowed_maxinst": list(VALUES),
            "config_fragments": {str(value): f"env.FEX_MAXINST = {value}\n" for value in VALUES},
            "correctness_each_value": ["instruction conformance", "floating point conformance",
                                        "exception/setjmp seam", "representative Mono game"],
            "requirements": ["same source/binary/game/settings and multiblock policy",
                             "effective MaxInst log plus raw frame/compile attribution",
                             "observed ready and graceful exit; shared reservation",
                             "matched starting thermal state and capture/sampler policy",
                             "restore original per-game config; preserve saves and baseline caches"],
            "paired_trials": trials,
            "sustained_trials": [{"maxinst": value, "seconds": 900, "fresh_app_process": True}
                                 for value in VALUES],
            "missing_until_execution": ["installed binary identity", "device/OS identity",
                                        "effective configuration", "readiness evidence",
                                        "correctness results", "raw measurements"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", required=True)
    parser.add_argument("--scene", required=True)
    parser.add_argument("--pairs", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20261010)
    args = parser.parse_args()
    try:
        plan = make_plan(args.game_id, args.scene, args.pairs, args.seed)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(plan, indent=2))


if __name__ == "__main__":
    main()
