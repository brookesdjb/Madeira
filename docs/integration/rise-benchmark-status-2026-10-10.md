# Rise wake-coalescing benchmark results, 10 October 2026

Ten fresh-process benchmark samples completed on the physical iPad: five with W1 off and five with W1 on. Overall median game-reported FPS increased from 36.55 to 38.14 (+4.35%), but the bootstrap 95% interval is -2.28% to +7.93%. The predefined comparison is **inconclusive**, not a confirmed speedup. Keep W1 opt-in.

| Scene | Off median FPS | On median FPS | Difference | 95% interval |
| --- | ---: | ---: | ---: | --- |
| Overall | 36.55 | 38.14 | +4.35% | -2.28% to +7.93% |
| Mountain Peak | 52.98 | 55.98 | +5.66% | -5.88% to +19.41% |
| Syria | 23.08 | 22.68 | -1.73% | -9.96% to +7.28% |
| Geothermal Valley | 31.94 | 32.74 | +2.50% | -3.51% to +5.92% |

Every scene comparison is inconclusive at the 3% meaningful-effect threshold. These are exploratory per-scene results; no multiplicity-adjusted significance claim is made.

## Conditions and evidence

Same installed dirty Debug binary in both arms, with no rebuild or install between them. Its provenance and binary hashes are in [the installed manifest](tomb-raider-transport-2026-10-10.json). Controller code is integration `830169f`, including focused topic `5251828`. 217 host tests passed, two physical wrappers skipped; [all three CI jobs passed](https://github.com/brookesdjb/Madeira/actions/runs/38055415363). This campaign separately supplies physical end-to-end evidence.

Order was A B B A A B B A A B. Each sample used a fresh Madeira process and its first benchmark, retained disk caches, a fixed 5-second warmup/10-second menu probe, approximately 10-second screenshots and 1.5-second socket snapshots. The native probe verified actual wake mode; requested and applied environments matched. CPU count 4, 1160x800, the 60 FPS option, monitor-identity setting and all other library-entry fields except lastPlayed matched. All three diagnostic profilers were explicitly disabled in both arms. Graphics were preserved but not re-read from the guest registry each run.

All thermal observations were nominal. Recorded battery start/end readings ranged from 27.59 to 30.29 C while charging; this is battery temperature, not CPU/GPU temperature. Before fresh launch, the runner waited for battery temperature at or below 30.2 C. Each completed sample ended using the normal upload-saves-and-close flow, with process absence verified.

## Reliability and interpretation

The ten timing outcomes are not a claim of ten uninterrupted automated launches. Two prelaunch interruptions found a preexisting idle app, including one reappearance during cooldown. Order 7 stopped at a Steam Cloud sync prompt; Wait and sync completed, and the same process resumed before its first benchmark. A duplicate recovery input-reservation request was rejected and removed. No timed sample was discarded or replaced. Order 7 consequently had a longer startup; startup duration was not matched. The temporary campaign scripts and private screenshots are retained locally with the raw evidence.

The public [JSON report](rise-w1-results-2026-10-10.json) includes all ten scores, thermal and battery readings, source/configuration digests, comparison thresholds and interruptions. Private raw evidence is under `automation/runs/rise-w1-campaign/20261010T132852.851007Z-a46d8c62`, plus the first two `rise-w1-0/20261010T131551.368595Z-a9a67c2c` and `rise-w1-1/20261010T132107.298633Z-a2f1bd7c` directories.

This measures game-reported benchmark FPS, not verified visible frame cadence. It does not measure the benefit of disabling diagnostics, benchmark CPU/energy use, sustained-session performance, or complete visual correctness. Networking/deadline/stop-under-load acceptance for W1 remains pending. Earlier uncontrolled 34.30/33.85 scores are not used as baselines.

The next useful work is reusable startup recovery plus repeated blocked comparisons with CPU/energy and sustained-session evidence. Do not enable W1 by default or close its acceptance issue on these FPS results alone. No new native performance code, upstream submission, issue closure or branch deletion was performed during this campaign.
