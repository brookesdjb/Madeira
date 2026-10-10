# Visual evidence (issue #13, offline part)

Everything here runs on a host without a device. None of it establishes that
an external screenshot shows current Metal output; that still needs a
physical capture against visibly observed output.

## Capture manifest

`automation.controller.capture_evidence.CaptureLog` owns `captures.json` in one
run directory. Its run fields are `run_id`, `source_commit`, `source_dirty`,
`game` and `capture_policy` (`functional` or `timing_baseline`). Each capture
records `kind` (`on_demand`, `post_input`, `periodic`, `failure`), `checkpoint`,
file name, SHA-256, byte size, PNG dimensions, monotonic clock readings taken
immediately before and after the capture call and the UTC time.

Limits are enforced before the device is touched:

- `max_captures` (default 200) and `max_bytes` (default 256 MiB). A capture that
  would exceed the byte budget is removed; earlier evidence is never deleted.
- Periodic captures are refused under `timing_baseline` and rate-limited to one
  per `periodic_interval_s` (default 5 s, minimum 1 s) otherwise. Capture's
  effect on frame pacing is not yet measured, so timing comparisons should
  keep the policy matched; the comparison report records whether it was.
- Checkpoints listed in `private_checkpoints` (sign-in, account screens) are
  refused without calling the capture function.

The log is not yet wired into `Run`/`workflows.py`. A device workflow passes
`lambda path: device.screenshot(path)` as the capture function.

## Comparing images

`compare-images` accepts repeated `--mask x0 y0 x1 y1` rectangles in full-image
coordinates to ignore dynamic content (clock, FPS counter, animated HUD).
Masks must lie inside the crop. Blank/uniform detection uses only unmasked
pixels, so a mask cannot hide a black scene. If less than 25% of the compared
region is unmasked, the result is `inconclusive`. `--difference-output` writes
a new owner-only PNG: changed pixels red, ignored regions blue, the rest a
dimmed candidate. It refuses to overwrite.

`compare-captures baseline/captures.json candidate/captures.json
[--calibration file.json]` pairs the latest `on_demand`/`post_input` capture per
checkpoint (periodic and failure captures are excluded), verifies each file's
hash, writes a difference image per checkpoint and `visual-report.json` into a
new run directory. Games must match. A checkpoint present in only one run is
`inconclusive`.

Calibration is versioned per game:

```json
{"schema_version": 1, "game": "portal",
 "checkpoints": {"main_menu": {"crop": [0, 0, 2732, 2048], "masks": [[0, 0, 400, 80]],
   "pixel_threshold": 20, "changed_fraction": 0.1,
   "calibrated_from": "two same-scene captures, run ids, device/OS"}}}
```

Without a calibration entry for every compared checkpoint, the overall status
is at most `inconclusive`: default thresholds are a hint, not a rendering gate.
`review` means a person should look at the difference images; it is not a
source regression verdict.

## Still needs a device

- Confirm external captures show current game output rather than stale or
  black surfaces, across rendering paths and orientations.
- Produce real calibration files from repeated same-scene captures; note how
  much dynamic content and GPU/compiler variation each checkpoint tolerates.
- Measure whether capture changes frame pacing.
- Wire `CaptureLog` into the device workflow and retain physical examples.
