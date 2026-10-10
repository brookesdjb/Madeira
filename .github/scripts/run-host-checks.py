#!/usr/bin/env python3
"""Run every tests/host/check-*.py and report one line per check.

CI runs this on Linux. A check listed in NEEDS is skipped, with its reason,
because it needs something a Linux runner does not have; every other check
must pass. Run it locally from the repository root with the submodules
checked out:  python3 .github/scripts/run-host-checks.py
"""
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Checks that cannot run on a Linux runner, and why.
NEEDS = {
    'check-wma-decoder.py': 'a configured Wine build tree (MADEIRA_WINE_BUILD)',
    'check-wine-mono.py': 'xcrun (macOS)',
    'check-steam-cloud.py': 'CryptoKit (Apple platforms only)',
    'check-jit-network.py': 'the Darwin module (Apple platforms only)',
}


def main():
    only = set(sys.argv[1:])
    checks = sorted((ROOT / 'tests/host').glob('check-*.py'))
    failed, skipped, passed = [], [], 0
    for path in checks:
        name = path.name
        if only and name not in only:
            continue
        if name in NEEDS:
            skipped.append(name)
            print(f'SKIP {name}: needs {NEEDS[name]}')
            continue
        start = time.monotonic()
        try:
            r = subprocess.run([sys.executable, str(path)], cwd=ROOT, capture_output=True,
                               text=True, timeout=600, env=os.environ)
            rc, out = r.returncode, r.stdout + r.stderr
        except subprocess.TimeoutExpired as e:
            rc, out = 124, f'timed out after {e.timeout}s'
        took = time.monotonic() - start
        if rc == 0:
            passed += 1
            print(f'PASS {name} ({took:.1f}s)')
        else:
            failed.append(name)
            tail = out.rstrip().splitlines()[-40:]
            print(f'FAIL {name} (exit {rc}, {took:.1f}s)')
            print('\n'.join('    ' + line for line in tail))
            if os.environ.get('GITHUB_ACTIONS'):
                # An annotation shows the failure on the PR without opening the log.
                msg = '%0A'.join(line.replace('%', '%25') for line in tail[-12:])
                print(f'::error title={name} failed::{msg}')
    print(f'\n{passed} passed, {len(failed)} failed, {len(skipped)} skipped')
    if failed:
        print('failed: ' + ' '.join(failed))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
