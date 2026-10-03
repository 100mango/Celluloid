#!/usr/bin/env python3
"""Create isolated test devices only from observed compatible iOS27 types/runtime."""
import json, subprocess

def sim(*args): return subprocess.check_output(['xcrun', 'simctl', *args], text=True)
runtimes = json.loads(sim('list', 'runtimes', '-j'))['runtimes']
runtime = next(r for r in runtimes if r.get('version') == '27.0' and r.get('isAvailable') and r['identifier'].startswith('com.apple.CoreSimulator.SimRuntime.iOS-'))
types = json.loads(sim('list', 'devicetypes', '-j'))['devicetypes']
# simctl rejects incompatible pairs. Each device owns a pristine synthetic
# library; no preceding UI edit or stale predefined simulator can seed its state.
for name in ['iPhone 18 Pro Max', 'iPhone SE (3rd generation)', 'iPad mini (A17 Pro)', 'iPad Pro 13-inch (M5)']:
    device_type = next(t for t in types if t['name'] == name)
    device = sim('create', 'Celluloid iOS27 ' + name, device_type['identifier'], runtime['identifier']).strip()
    print(device, name)
