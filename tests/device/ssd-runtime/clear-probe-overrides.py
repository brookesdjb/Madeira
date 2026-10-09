#!/usr/bin/env python3
"""Remove only the controlled SSD fixture's launch override in the test app.

No game, account, bookmark or unrelated config fields are read or changed.
The app must be restarted after this succeeds. Never targets working Madeira.
"""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile

BUNDLE = 'com.brookes.madeira.ssdprobe'
SOURCE = 'Documents/madeira.cfg'


def clean(text):
    lines = text.splitlines(keepends=True)
    exe = [i for i, line in enumerate(lines) if re.match(r'^\s*env\.MADEIRA_EXE\s*=', line)]
    args = [i for i, line in enumerate(lines) if re.match(r'^\s*env\.MADEIRA_ARGS\s*=', line)]
    if not exe:
        return text
    if len(exe) != 1 or len(args) != 1:
        raise ValueError('Ambiguous launch settings; no changes made.')
    if not re.fullmatch(r'\s*env\.MADEIRA_EXE\s*=\s*E:\\\.madeira-execution-[0-9A-Fa-f-]{36}\\ssd_probe\.exe\s*', lines[exe[0]]):
        raise ValueError('Launch target is not the controlled fixture; no changes made.')
    if not re.fullmatch(r'\s*env\.MADEIRA_ARGS\s*=\s*', lines[args[0]]):
        raise ValueError('Arguments are not the controlled fixture setting; no changes made.')
    return ''.join(line for i, line in enumerate(lines) if i not in (exe[0], args[0]))


def self_test():
    fixture = 'env.MADEIRA_EXE = E:\\.madeira-execution-00000000-0000-0000-0000-000000000000\\ssd_probe.exe\nenv.MADEIRA_ARGS = \n'
    other = '# keep comment\nother.setting = unchanged\n'
    assert clean(fixture + other) == other
    assert clean(other) == other
    for invalid in [fixture + fixture, fixture.replace('ssd_probe.exe', 'game.exe'), fixture.replace('ARGS = ', 'ARGS = custom')]:
        try:
            clean(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError('Unexpected override was modified')
    print('PASS: exact fixture cleanup, unrelated settings preserved, custom/duplicate overrides refused')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device')
    parser.add_argument('--self-test', action='store_true')
    options = parser.parse_args()
    if options.self_test:
        self_test()
        return
    if not options.device:
        parser.error('--device is required')
    with tempfile.TemporaryDirectory(prefix='madeira-probe-config-') as directory:
        path = Path(directory) / 'config'
        def copy(direction, source, destination):
            result = subprocess.run(['xcrun', 'devicectl', 'device', 'copy', direction,
                '--device', options.device, '--source', str(source), '--destination', str(destination),
                '--domain-type', 'appDataContainer', '--domain-identifier', BUNDLE, '--quiet'], capture_output=True)
            if result.returncode:
                raise RuntimeError('Test-app config transfer failed; no config contents logged.')
        copy('from', SOURCE, path)
        original = path.read_bytes().decode('utf-8')
        updated = clean(original)
        if updated == original:
            print('No fixture override remains.')
            return
        path.write_bytes(updated.encode('utf-8'))
        copy('to', path, SOURCE)
        copy('from', SOURCE, path)
        if path.read_bytes() != updated.encode('utf-8'):
            raise RuntimeError('Config verification failed.')
        print('Removed and verified the two fixture launch overrides in the disposable app. Restart it before Play.')


if __name__ == '__main__':
    main()
