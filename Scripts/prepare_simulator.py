#!/usr/bin/env python3
"""Bounded synthetic simulator setup probe; no credentials or personal media."""
import datetime, hashlib, json, os, pathlib, struct, subprocess, sys, time

def command(label, seconds, *args):
    return subprocess.run([sys.executable, 'Scripts/run_bounded.py', '--label', label,
                           '--seconds', str(seconds), *args], check=False).returncode

def evidence(label):
    print('SETUP_EVIDENCE_BEGIN', label, datetime.datetime.now(datetime.timezone.utc).isoformat(), flush=True)
    for args in [['vm_stat'], ['sysctl', 'vm.swapusage'], ['xcrun', 'simctl', 'list', 'devices', '-j']]:
        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=20)
            if args[0] == 'xcrun':
                devices = json.loads(r.stdout)['devices']
                print('BOOTED_SIMULATORS', json.dumps([{'runtime': runtime, 'name': d['name'], 'udid': d['udid'], 'state': d['state']} for runtime, group in devices.items() for d in group if d['state'] == 'Booted']), flush=True)
            else: print('HOST_MEMORY', args[0], r.returncode, r.stdout[:4000], flush=True)
        except (subprocess.TimeoutExpired, ValueError, KeyError) as error:
            print('SETUP_EVIDENCE_UNAVAILABLE', args[0], type(error).__name__, flush=True)
    # Public process identities/RSS only. Do not emit full arguments or environment.
    try:
        r = subprocess.run(['ps', '-axo', 'pid=,ppid=,rss=,comm='], capture_output=True, text=True, timeout=20)
        entries = []
        for line in r.stdout.splitlines():
            parts = line.split(None, 3)
            if len(parts) != 4: continue
            name = os.path.basename(parts[3])
            if any(token in name.lower() for token in ['simulator', 'simctl', 'launchd_sim', 'photolibrary', 'assetsd', 'xcodebuild', 'celluloid']):
                entries.append({'pid': int(parts[0]), 'ppid': int(parts[1]), 'rss_kib': int(parts[2]), 'name': name})
        print('SETUP_PROCESS_IDENTITIES', json.dumps(entries[:80]), flush=True)
    except (subprocess.TimeoutExpired, ValueError) as error:
        print('SETUP_PROCESS_IDENTITIES_UNAVAILABLE', type(error).__name__, flush=True)
    print('SETUP_EVIDENCE_END', label, flush=True)

if __name__ == '__main__':
    device, name = sys.argv[1:3]
    evidence(name + ' before-boot')
    if command(name + ' boot', 60, 'xcrun', 'simctl', 'boot', device): sys.exit(1)
    if command(name + ' bootstatus', 600, 'xcrun', 'simctl', 'bootstatus', device, '-b'): sys.exit(1)
    evidence(name + ' after-boot')
    # Boot completion does not establish that the Photos service has initialized.
    # Launch only the built-in Photos app; do not accept account/privacy dialogs.
    if command(name + ' Photos-warm-up', 600, 'xcrun', 'simctl', 'launch', device, 'com.apple.mobileslideshow'): sys.exit(1)
    evidence(name + ' after-Photos-launch')
    paths = [pathlib.Path('/tmp/celluloid-fixture.png'), pathlib.Path('/tmp/celluloid-fixture-2.png')] + sorted(pathlib.Path('/tmp').glob('celluloid-composition-*.png'))
    for index, path in enumerate(paths):
        data = path.read_bytes()
        print('IMPORT_FIXTURE', json.dumps({'index': index, 'file': path.name, 'bytes': len(data), 'dimensions': struct.unpack('>II', data[16:24]), 'sha256': hashlib.sha256(data).hexdigest()}), flush=True)
        # The old bound applied to six files together. Keep the same per-command
        # bound while isolating first library initialization from each tiny import.
        code = command(name + ' import-' + str(index), 180, 'xcrun', 'simctl', 'addmedia', device, str(path))
        if code:
            evidence(name + ' failed-import-' + str(index))
            sys.exit(code)
    evidence(name + ' imported')
    sys.exit(0)
