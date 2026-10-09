#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 125hz
# Madeira Converter Exception: see LICENSE-EXCEPTION.md
"""Isolated binary-reuse experiment; never writes the supplied runtime bundle.

SOURCE_APP, TEAM_ID, BUNDLE_ID are required. OUTPUT_DIR defaults to a new temp
folder. Uses the same Xcode signing-stub workflow as the existing installation.
No pairing file or Steam credentials are read or copied by this script.
"""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[3]
source = Path(os.environ['SOURCE_APP']).resolve()
team = os.environ['TEAM_ID']
bundle = os.environ['BUNDLE_ID']
source_info = plistlib.loads((source / 'Info.plist').read_bytes())
assert bundle != source_info['CFBundleIdentifier'], 'Use a distinct bundle ID'
expected = 'd942617b44d57bb23b3e97dce87cf5272265e239dc5d6434dac11030341d6446'
assert hashlib.sha256((source / 'Madeira.debug.dylib').read_bytes()).hexdigest() == expected, 'Unverified runtime input'
work = Path(os.environ.get('OUTPUT_DIR') or tempfile.mkdtemp(prefix='madeira-ssd-runtime-')).resolve()
work.mkdir(parents=True, exist_ok=True)
app = work / 'MadeiraSSDRuntime.app'
assert not app.exists(), 'Output bundle already exists; choose a new OUTPUT_DIR'

def run(args, **kw):
    subprocess.run(list(map(str, args)), check=True, **kw)

signing = work / 'Signing'
signing.mkdir()
(signing / 'App.swift').write_text('import SwiftUI\n@main struct Signing: App { var body: some Scene { WindowGroup { Text("Signing") } } }\n')
(signing / 'Helper.swift').write_text('import Foundation\n@objc(SigningHelper) final class SigningHelper: NSObject, NSExtensionRequestHandling { func beginRequest(with context: NSExtensionContext) { context.completeRequest(returningItems: nil) } }\n')
(signing / 'App.entitlements').write_bytes(plistlib.dumps({'com.apple.developer.kernel.increased-memory-limit': True}))
spec = {
 'name': 'SSDRuntimeSigning', 'options': {'deploymentTarget': {'iOS': '26.0'}},
 'settings': {'base': {'DEVELOPMENT_TEAM': team, 'CODE_SIGN_STYLE': 'Automatic', 'SWIFT_VERSION': '5.0'}},
 'targets': {
  'SSDRuntimeSigning': {'type': 'application', 'platform': 'iOS', 'sources': ['App.swift'],
   'settings': {'base': {'PRODUCT_BUNDLE_IDENTIFIER': bundle, 'CODE_SIGN_ENTITLEMENTS': 'App.entitlements', 'GENERATE_INFOPLIST_FILE': True}},
   'dependencies': [{'target': 'MadeiraJITHelper'}]},
  'MadeiraJITHelper': {'type': 'app-extension', 'platform': 'iOS', 'sources': ['Helper.swift'],
   'settings': {'base': {'PRODUCT_BUNDLE_IDENTIFIER': bundle + '.JITHelper', 'GENERATE_INFOPLIST_FILE': True}},
   'info': {'path': 'Helper-Info.plist', 'properties': {'NSExtension': {'NSExtensionPointIdentifier': 'com.apple.ar.viewer', 'NSExtensionPrincipalClass': 'SigningHelper', 'NSExtensionAttributes': {'NSExtensionActivationRule': 'FALSEPREDICATE'}}}}}
 }, 'schemes': {'SSDRuntimeSigning': {'build': {'targets': {'SSDRuntimeSigning': 'all'}}}}
}
(signing / 'project.json').write_text(json.dumps(spec))
run(['xcodegen', 'generate', '--spec', signing / 'project.json'])
with (work / 'signing-build.log').open('w') as log:
    run(['xcodebuild', '-project', signing / 'SSDRuntimeSigning.xcodeproj', '-scheme', 'SSDRuntimeSigning', '-configuration', 'Debug', '-destination', 'generic/platform=iOS', '-derivedDataPath', work / 'DerivedData', '-allowProvisioningUpdates', 'build'], stdout=log, stderr=subprocess.STDOUT)

sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
shutil.copytree(source, app, symlinks=True)
run(['bash', root / 'tests/device/ssd-runtime/fixture/build.sh'], stdout=subprocess.DEVNULL)
fixture = root / 'tests/device/ssd-runtime/fixture/out'
(app / 'ssd-fixture').mkdir()
for item in ['ssd_probe.exe', 'ssd_probe.dll', 'assets']:
    src = fixture / item
    if src.is_dir(): shutil.copytree(src, app / 'ssd-fixture' / item)
    else: shutil.copy2(src, app / 'ssd-fixture' / item)
run(['xcrun', '--sdk', 'iphoneos', 'swiftc', '-emit-library', '-swift-version', '5', '-module-name', 'MadeiraSSDOverlay', '-target', 'arm64-apple-ios17.0', '-sdk', sdk,
     *[root / 'app/Madeira' / x for x in ['SteamStorage.swift', 'SteamStorageProbe.swift', 'SteamStorageProbeView.swift']],
     root / 'tests/device/ssd-runtime/Overlay.swift', '-o', app / 'MadeiraSSDOverlay.dylib',
     '-Xlinker', '-install_name', '-Xlinker', '@executable_path/MadeiraSSDOverlay.dylib'])
run(['xcrun', '--sdk', 'iphoneos', 'clang', '-arch', 'arm64', '-miphoneos-version-min=17.0', '-isysroot', sdk,
     '-fobjc-arc', root / 'tests/device/ssd-runtime/main.m', '-framework', 'Foundation',
     app / 'MadeiraSSDOverlay.dylib', '-Wl,-rpath,@executable_path', '-Wl,-rpath,@executable_path/Frameworks',
     '-o', app / 'MadeiraSSDWrapper'])

def rewrite(value):
    if isinstance(value, str): return value.replace(source_info['CFBundleIdentifier'], bundle)
    if isinstance(value, list): return [rewrite(x) for x in value]
    if isinstance(value, dict): return {k: rewrite(v) for k,v in value.items()}
    return value

stub = work / 'DerivedData/Build/Products/Debug-iphoneos/SSDRuntimeSigning.app'
identity_output = subprocess.check_output(['security', 'find-identity', '-v', '-p', 'codesigning'], text=True)
signed_details = subprocess.run(['codesign', '-dvv', str(stub)], capture_output=True, text=True, check=True).stderr
authority = next(line.removeprefix('Authority=') for line in signed_details.splitlines() if line.startswith('Authority=Apple Development:'))
identities = [line for line in identity_output.splitlines() if '"' + authority + '"' in line]
assert len(identities) == 1, 'Set up one matching signing identity for this team'
identity = re.search(r'\b[A-F0-9]{40}\b', identities[0]).group()
for target, signed, name in [(app, stub, 'App'), (app / 'PlugIns/MadeiraJITHelper.appex', stub / 'PlugIns/MadeiraJITHelper.appex', 'Helper')]:
    info = rewrite(plistlib.loads((target / 'Info.plist').read_bytes()))
    if name == 'App':
        info.update(CFBundleExecutable='MadeiraSSDWrapper', CFBundleDisplayName='Madeira SSD Runtime', MadeiraBuild='SSD runtime binary-reuse experiment')
    (target / 'Info.plist').write_bytes(plistlib.dumps(info))
    shutil.copy2(signed / 'embedded.mobileprovision', target / 'embedded.mobileprovision')
    entitlement = subprocess.run(['codesign', '-d', '--entitlements', ':-', str(signed)], capture_output=True, check=True).stdout
    (work / (name + '.entitlements')).write_bytes(entitlement)
for target in sorted([x for x in app.rglob('*') if x.suffix in ('.dylib', '.framework')], key=lambda p: len(p.parts), reverse=True):
    run(['codesign', '--force', '--sign', identity, '--timestamp=none', target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
for target, name in [(app / 'PlugIns/MadeiraJITHelper.appex', 'Helper'), (app, 'App')]:
    run(['codesign', '--force', '--sign', identity, '--timestamp=none', '--generate-entitlement-der', '--entitlements', work / (name + '.entitlements'), target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
run(['codesign', '--verify', '--deep', '--strict', app])
source_files = [root / 'tests/device/ssd-runtime' / x for x in ['build.py', 'main.m', 'Overlay.swift', 'fixture/build.sh', 'fixture/probe.c', 'fixture/probe_dll.c']]
source_files += [root / 'app/Madeira' / x for x in ['SteamStorage.swift', 'SteamStorageProbe.swift', 'SteamStorageProbeView.swift']]
provenance = {
    'runtime_input_sha256': expected,
    'runtime_source_build': False,
    'wrapper_source_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
    'wrapper_sources_uncommitted': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=root)),
    'bundle_id': bundle,
    'fixture_toolchain': 'llvm-mingw 20260421 ucrt macos universal',
    'fixture_toolchain_archive_sha256': 'bd85a3975723815cef28dbbd2ca2cb0c926f6b348a12a0453f39f7af273cb3f7',
    'sources': {str(f.relative_to(root)): hashlib.sha256(f.read_bytes()).hexdigest() for f in source_files},
    'outputs': {name: hashlib.sha256((app / name).read_bytes()).hexdigest()
                for name in ['MadeiraSSDWrapper', 'MadeiraSSDOverlay.dylib', 'ssd-fixture/ssd_probe.exe', 'ssd-fixture/ssd_probe.dll']}
}
(work / 'provenance.json').write_text(json.dumps(provenance, indent=2))

print(app)
