#!/usr/bin/env python3
"""Unsigned validation-host Release check. This is not the shipping iPhone package."""
from pathlib import Path
import hashlib
import json
import os
import plistlib
import re
import subprocess
import sys

app = Path(sys.argv[1])
info = plistlib.loads((app / 'Info.plist').read_bytes())
binary = app / 'CelluloidPhoneCompanion'
data = binary.read_bytes()
architectures = subprocess.check_output(['xcrun', 'lipo', '-archs', str(binary)], text=True).split()
loads = subprocess.check_output(['xcrun', 'vtool', '-show-build', str(binary)], text=True)
markers = [b'CELLULOID_PHONE_LAYOUT_FIXTURE',b'WatchProcessingLargeTextUI',b'CELLULOID_PHONE_OUTPUT_PROOF', b'PhoneOutputProof', b'companion.synthetic-seed', b'58B78AAA-30B8-44DB-BD4F-10762900A001']
checks = {
    'validation_host_identity': info.get('CFBundleIdentifier') == 'Mango.Celluloid' and info.get('CFBundleExecutable') == 'CelluloidPhoneCompanion' and info.get('CFBundleDisplayName') == 'Celluloid Companion Validation',
    'device_sdk': info.get('DTPlatformName') == 'iphoneos',
    'native_arm64': architectures == ['arm64'],
    'minimum_os': info.get('MinimumOSVersion') == '15.0' and re.findall(r'\bminos\s+(\S+)', loads) == ['15.0'],
    'version_and_build': info.get('CFBundleShortVersionString') == '1.1' and info.get('CFBundleVersion') == '2',
    'debug_proof_and_seed_absent': not any(marker in data for marker in markers),
    'no_test_bundle': not any(app.rglob('*.xctest')),
}
report = {'source_sha': os.environ['GITHUB_SHA'], 'checks': checks, 'product': str(app), 'binary_sha256': hashlib.sha256(data).hexdigest(), 'load_commands': loads,
          'scope': 'Unsigned generic-device Release of SKIP_INSTALL validation host only. Shipping UIKit entry, Watch embedding/version equality and paired hardware remain unqualified.'}
out = Path(os.environ['RUNNER_TEMP']) / 'phone-harness-release.json'
out.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'phone_validation_host_release': str(out), 'checks': checks}))
if not all(checks.values()): raise SystemExit('Phone validation-host Release exclusion gate failed')
