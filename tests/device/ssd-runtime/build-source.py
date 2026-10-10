#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 125hz
# Madeira Converter Exception: see LICENSE-EXCEPTION.md
"""Compile the checkout's Swift frontend against the pinned published runtime.

This is a mixed-source diagnostic build, not a full native source build. The
three hidden native entry points are forwarded to their existing implementations;
no replacement graphics/diagnostic behavior or runtime instructions are supplied.
Usage: build-source.py SOURCE_APP OUTPUT_EXECUTABLE
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[3]
source = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2]).resolve()
runtime = source / 'Madeira.debug.dylib'
expected = 'd942617b44d57bb23b3e97dce87cf5272265e239dc5d6434dac11030341d6446'
assert hashlib.sha256(runtime.read_bytes()).hexdigest() == expected, 'Unverified runtime input'
output.parent.mkdir(parents=True, exist_ok=True)
symbols = subprocess.check_output(['nm', str(runtime)], text=True)
entries = {}
for line in symbols.splitlines():
    parts = line.split()
    if len(parts) == 3 and parts[2] in ('_madeira_get_eco', '_madeira_set_eco', '_madeira_set_diag_enabled'):
        entries[parts[2]] = int(parts[0], 16)
assert entries == {'_madeira_get_eco': 0xa10668, '_madeira_set_eco': 0xa10554,
                   '_madeira_set_diag_enabled': 0xa28f48}, 'Native entry points differ'
load_commands = subprocess.check_output(['otool', '-l', str(runtime)], text=True)
assert 'segname __TEXT\n   vmaddr 0x0000000000000000' in load_commands

forwarder = output.with_suffix('.forward.c')
forwarder.write_text('''#include <dlfcn.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
extern int wine_process_is_running(void);
static void *entry(uintptr_t offset) {
    Dl_info image;
    if (!dladdr((void *)&wine_process_is_running, &image) || !image.dli_fbase ||
        !strstr(image.dli_fname, "/Madeira.debug.dylib")) abort();
    return (void *)((uintptr_t)image.dli_fbase + offset);
}
int madeira_get_eco(void) { return ((int (*)(void))entry(0xa10668))(); }
void madeira_set_eco(int value) { ((void (*)(int))entry(0xa10554))(value); }
void madeira_set_diag_enabled(int value) { ((void (*)(int))entry(0xa28f48))(value); }
''')
sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
obj = output.with_suffix('.forward.o')
subprocess.run(['xcrun', 'clang', '-c', '-arch', 'arm64', '-miphoneos-version-min=17.0',
                '-isysroot', sdk, str(forwarder), '-o', str(obj)], check=True)
project = root / 'app/Madeira.xcodeproj/project.pbxproj'
objects = json.loads(subprocess.check_output(['plutil', '-convert', 'json', '-o', '-', str(project)]))['objects']
target = next(v for v in objects.values() if v.get('isa') == 'PBXNativeTarget' and v.get('name') == 'Madeira')
phase = next(objects[i] for i in target['buildPhases'] if objects[i]['isa'] == 'PBXSourcesBuildPhase')
files = [root / 'app/Madeira' / objects[objects[i]['fileRef']]['path']
         for i in phase['files'] if objects[objects[i]['fileRef']].get('path', '').endswith('.swift')]
subprocess.run(['xcrun', '--sdk', 'iphoneos', 'swiftc', '-emit-executable', '-parse-as-library', '-swift-version', '5', '-D', 'DEBUG',
                '-module-name', 'MadeiraSSDSource', '-sdk', sdk, '-target', 'arm64-apple-ios17.0',
                '-import-objc-header', str(root / 'app/Madeira/Madeira-Bridging-Header.h'),
                *map(str, files), str(obj), str(runtime), '-o', str(output),
                '-Xlinker', '-rpath', '-Xlinker', '@executable_path',
                '-Xlinker', '-rpath', '-Xlinker', '@executable_path/Frameworks'], check=True)
output.with_suffix('.source-provenance.json').write_text(json.dumps({
    'runtime_input_sha256': expected, 'runtime_source_build': False,
    'module': 'MadeiraSSDSource', 'hidden_forwarders': entries,
    'sources': {str(f.relative_to(root)): hashlib.sha256(f.read_bytes()).hexdigest() for f in files},
    'executable_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
}, indent=2))
print(f'Linked {len(files)} current Swift sources against preserved runtime: {output}')
