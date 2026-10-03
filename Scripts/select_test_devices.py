#!/usr/bin/env python3
"""Choose actual installed iOS 27 devices; create the small compatible phone only from observed types."""
import json, subprocess

def sim(*args): return subprocess.check_output(['xcrun', 'simctl', *args], text=True)
runtimes = json.loads(sim('list', 'runtimes', '-j'))['runtimes']
runtime = next(r for r in runtimes if r.get('version') == '27.0' and r.get('isAvailable') and r['identifier'].startswith('com.apple.CoreSimulator.SimRuntime.iOS-'))
types = json.loads(sim('list', 'devicetypes', '-j'))['devicetypes']
small = next(t for t in types if t['name'] == 'iPhone SE (3rd generation)')
# simctl itself rejects incompatible runtime/device pairs. Do not substitute a
# larger device and label it a smallest-screen test.
small_id = sim('create', 'Celluloid iPhone SE3 iOS27', small['identifier'], runtime['identifier']).strip()
devices = json.loads(sim('list', 'devices', 'available', '-j'))['devices'][runtime['identifier']]
print(small_id, 'iPhone SE (3rd generation)')
for name in ['iPhone 18 Pro Max', 'iPad mini (A17 Pro)', 'iPad Pro 13-inch (M5)']:
    matches = [d for d in devices if d['name'] == name and d['isAvailable']]
    assert len(matches) == 1, (name, devices)
    print(matches[0]['udid'], name)
