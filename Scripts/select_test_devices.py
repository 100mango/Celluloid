#!/usr/bin/env python3
"""Create isolated test devices only from observed compatible iOS27 types/runtime."""
import argparse, json, subprocess

def sim(*args): return subprocess.check_output(['xcrun', 'simctl', *args], text=True)
runtimes = json.loads(sim('list', 'runtimes', '-j'))['runtimes']
runtime = next(r for r in runtimes if r.get('version') == '27.0' and r.get('isAvailable') and r['identifier'].startswith('com.apple.CoreSimulator.SimRuntime.iOS-'))
types = json.loads(sim('list', 'devicetypes', '-j'))['devicetypes']
# simctl rejects incompatible pairs. Each device owns a pristine synthetic
# library; no preceding UI edit or stale predefined simulator can seed its state.
supported = ['iPhone 18 Pro Max', 'iPhone SE (3rd generation)', 'iPad mini (A17 Pro)', 'iPad Pro 13-inch (M5)']
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('device', choices=supported, help='Exactly one device per fresh CI host')
parser.add_argument('--pre-provisioned', action='store_true', help='Use exactly one observed shutdown device on this fresh host')
args = parser.parse_args()
for name in [args.device]:
    device_type = next(t for t in types if t['name'] == name)
    if args.pre_provisioned:
        all_devices = json.loads(sim('list', 'devices', 'available', '-j'))['devices']
        assert not [d for group in all_devices.values() for d in group if d['state'] == 'Booted'], 'Expected one fresh idle host'
        matches = [d for d in all_devices[runtime['identifier']] if d['name'] == name and d.get('isAvailable') and d['state'] == 'Shutdown']
        assert len(matches) == 1, matches
        device = matches[0]['udid']
    else:
        device = sim('create', 'Celluloid iOS27 ' + name, device_type['identifier'], runtime['identifier']).strip()
    print(device, name)
