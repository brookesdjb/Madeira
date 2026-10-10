#!/usr/bin/env python3
"""Compile unchanged FEX pool headers on Apple Silicon and run bounded tests."""
import argparse
import datetime
import hashlib
import json
import platform
import statistics
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def command(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, text=True,
                          capture_output=True, **kwargs)


def git(root, *args):
    return command(['git', '-C', root, *args]).stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fex-root', type=Path, default=ROOT / 'FEX')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--pressure-experiment', action='store_true',
                        help='Alternate unchanged production and host-only pressure candidate')
    parser.add_argument('--compare', type=Path, help='Compare against a previous report.json')
    args = parser.parse_args()
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        parser.error('This proof of concept targets native Apple Silicon macOS.')
    if not 1 <= args.repeats <= 20:
        parser.error('--repeats must be between 1 and 20')
    if args.pressure_experiment and args.compare:
        parser.error('--pressure-experiment produces its own paired comparison')
    fex = args.fex_root.resolve()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    output = HERE / 'runs' / stamp
    output.mkdir(parents=True)
    started = time.monotonic()
    source_paths = [HERE / 'bench.cpp', HERE / 'run.py', HERE / 'pressure_pool.h',
                    *sorted((fex / 'FEXCore/include').rglob('*.h')),
                    *sorted((fex / 'External/fmt/include').rglob('*.h'))]
    fingerprints = {str(p.relative_to(fex)) if p.is_relative_to(fex) else p.name:
                    hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    common = ['xcrun', 'clang++', '-std=c++20', '-pthread', '-Wall', '-Wextra',
              '-Wno-unused-parameter', '-DFMT_HEADER_ONLY', '-DASSERTIONS_ENABLED=1',
              '-I', fex / 'FEXCore/include', '-I', fex / 'External/fmt/include', HERE / 'bench.cpp']
    report = {'schema_version': 2, 'kind': 'mac_fex_pool_component_poc',
              'timestamp_utc': stamp, 'host': platform.platform(),
              'hardware': command(['sysctl', '-n', 'hw.model']).stdout.strip(),
              'compiler': command(['xcrun', 'clang++', '--version']).stdout.splitlines()[0],
              'app_commit': git(ROOT, 'rev-parse', 'HEAD'),
              'fex_commit': git(fex, 'rev-parse', 'HEAD'),
              'fex_status': git(fex, 'status', '--porcelain'),
              'source_sha256': fingerprints,
              'limits': {'arena_mib': 8192, 'scratch_buffer_mib': 16,
                         'physical_memory_cap': False, 'wine_va_scanner': False,
                         'game_execution': False, 'fex_x86_execution': False,
                         'ipad_performance_evidence': False},
              'runs': []}
    variants = ['production', 'pressure'] if args.pressure_experiment else ['production']
    for mode, flags in [('sanitized', ['-O1', '-g', '-fsanitize=address,undefined',
                                      '-fno-omit-frame-pointer', '-fno-sanitize-recover=all']),
                        ('release', ['-O2'])]:
        binaries = {}
        for variant in variants:
            binary = output / (variant + '-' + mode)
            build_start = time.monotonic()
            definitions = ['-DPRESSURE_EXPERIMENT=1'] if variant == 'pressure' else []
            result = command(common + flags + definitions + ['-o', binary], timeout=120)
            (output / (variant + '-' + mode + '-build.log')).write_text(result.stdout + result.stderr)
            print(f'{variant} {mode}: compiled in {time.monotonic()-build_start:.2f}s', flush=True)
            binaries[variant] = binary
        for trial in range(1 if mode == 'sanitized' else args.repeats):
            # AB then BA order controls simple warm-up/order bias. Both binaries
            # use the same host adapters and compile flags, apart from selection.
            for variant in variants if trial % 2 == 0 else variants[::-1]:
                begin = time.monotonic()
                result = command([binaries[variant]], timeout=60)
                cases = [json.loads(line) for line in result.stdout.splitlines()]
                assert len(cases) == 11 and all(x['checks_passed'] for x in cases)
                (output / f'{variant}-{mode}-{trial}.stderr.log').write_text(result.stderr)
                report['runs'].append({'mode': mode, 'variant': variant, 'trial': trial,
                                       'elapsed_seconds': time.monotonic()-begin, 'cases': cases})
                print(f'{variant} {mode} trial {trial+1}: 11 cases passed in {time.monotonic()-begin:.3f}s', flush=True)
    summaries = {}
    for variant in variants:
        summary = []
        for workers in [4, 9, 84]:
            values = [case['claim_p95_us'] for run in report['runs']
                      if run['mode'] == 'release' and run['variant'] == variant
                      for case in run['cases'] if case['workers'] == workers]
            summary.append({'workers': workers, 'median_run_p95_claim_us': statistics.median(values),
                            'min_run_p95_claim_us': min(values), 'max_run_p95_claim_us': max(values)})
        summaries[variant] = summary
    report['release_summary'] = summaries['production']
    if args.pressure_experiment:
        report['experiment'] = {'name': 'release_idle_buffers_after_failed_allocation',
                                'variant_summaries': summaries,
                                'execution_order': 'AB then BA, alternating by trial',
                                'production_source_modified': False,
                                'unrecoverable_null_claim_fixed': False}
        report['paired_comparison'] = [
            {'workers': old['workers'], 'production_p95_us': old['median_run_p95_claim_us'],
             'pressure_p95_us': new['median_run_p95_claim_us']}
            for old, new in zip(summaries['production'], summaries['pressure'])]
    report['elapsed_seconds'] = time.monotonic()-started
    report['status'] = 'PASS_KNOWN_NULL_CLAIM_BEHAVIOR_REPRODUCED'
    if args.compare:
        before = json.loads(args.compare.read_text())
        # Comparisons only make sense with the same harness, machine and compiler.
        for key in ['hardware', 'compiler']:
            if before[key] != report[key]: raise ValueError('Incompatible baseline: ' + key)
        if before['source_sha256']['bench.cpp'] != fingerprints['bench.cpp']:
            raise ValueError('Incompatible baseline: harness changed')
        report['comparison'] = [{'workers': new['workers'],
                                'baseline_p95_us': old['median_run_p95_claim_us'],
                                'candidate_p95_us': new['median_run_p95_claim_us']}
                               for old, new in zip(before['release_summary'], report['release_summary'])]
    path = output / 'report.json'
    path.write_text(json.dumps(report, indent=2) + '\n')
    print('Report:', path)
    print('PASS: production pool exercised; this is not a full Wine/FEX or GPU benchmark.')


if __name__ == '__main__':
    main()
