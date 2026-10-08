#!/usr/bin/env python3
"""Read-only PhotoKit readiness then reconciled synthetic import; never retry imports."""
import argparse, datetime, hashlib, json, os, pathlib, re, subprocess, sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('device')
parser.add_argument('--already-prepared', action='store_true')
options = parser.parse_args()
device = options.device
errors = []

def run(label, seconds, *args):
    result = subprocess.run([sys.executable, 'Scripts/run_bounded.py', '--seconds', str(seconds), '--label', label, *args],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    pathlib.Path('bootstrap-' + label + '.log').write_text(result.stdout)
    print(result.stdout, end='', flush=True)
    return result.returncode, result.stdout

def host(label):
    print('BOOTSTRAP_HOST_BEGIN', label, datetime.datetime.now(datetime.timezone.utc).isoformat(), flush=True)
    for command in [['vm_stat'], ['memory_pressure', '-Q'], ['sysctl', 'vm.swapusage'], ['df', '-h', '.']]:
        try:
            value = subprocess.run(command, capture_output=True, text=True, timeout=15)
            print('BOOTSTRAP_HOST', command[0], value.returncode, value.stdout[:4500], value.stderr[:500], flush=True)
        except subprocess.TimeoutExpired: print('BOOTSTRAP_HOST_TIMEOUT', command[0], flush=True)
    try:
        value = subprocess.run(['ps', '-axo', 'pid=,ppid=,rss=,comm='], capture_output=True, text=True, timeout=15)
        selected = []
        for line in value.stdout.splitlines():
            fields = line.split(None, 3)
            if len(fields) != 4: continue
            name = os.path.basename(fields[3])
            if any(word in name.lower() for word in ['swift', 'clang', 'xcbuild', 'index', 'sourcekit', 'xcodebuild', 'simulator', 'simctl', 'launchd_sim', 'photolibrary', 'assetsd', 'celluloid']):
                selected.append({'pid': int(fields[0]), 'ppid': int(fields[1]), 'rss_kib': int(fields[2]), 'name': name})
        print('BOOTSTRAP_BUILD_AND_SIMULATOR_RSS', json.dumps(sorted(selected, key=lambda p: p['rss_kib'], reverse=True)[:40]), flush=True)
    except subprocess.TimeoutExpired: print('BOOTSTRAP_HOST_TIMEOUT ps', flush=True)
    print('BOOTSTRAP_HOST_END', label, flush=True)

def test(label, method):
    code, output = run(label, 360, 'xcodebuild', '-project', 'Celluloid.xcodeproj', '-scheme', 'Celluloid',
        '-configuration', 'Debug', '-destination', 'platform=iOS Simulator,id=' + device, '-derivedDataPath', '.build',
        '-resultBundlePath', 'Bootstrap-' + label + '.xcresult', '-parallel-testing-enabled', 'NO', '-collect-test-diagnostics', 'never',
        '-only-testing:CelluloidTests/EditorRegressionTests/' + method, 'test-without-building', 'CODE_SIGNING_ALLOWED=NO')
    if code: raise RuntimeError('PhotoKit probe failed: ' + label)
    rows = [json.loads(line.split('PHOTOS_LIBRARY_READINESS ', 1)[1]) for line in output.splitlines() if line.startswith('PHOTOS_LIBRARY_READINESS ')]
    if len(rows) != 1: raise RuntimeError('Missing unambiguous actual PhotoKit readiness result')
    return rows[0]

if options.already_prepared:
    host('prepared-before-readiness')
    if run('verify-prepared-registration', 45, 'xcrun', 'simctl', 'get_app_container', device, 'Mango.Celluloid', 'app')[0]:
        raise RuntimeError('Prepared test app registration could not be verified')
else:
    host('before-boot')
    for label, seconds, command in [
        ('boot', 60, ['xcrun', 'simctl', 'boot', device]),
        ('bootstatus', 600, ['xcrun', 'simctl', 'bootstatus', device, '-b']),
        ('install-before-import', 120, ['xcrun', 'simctl', 'install', device, '.build/Build/Products/Debug-iphonesimulator/Celluloid.app']),
        ('grant-before-import', 60, ['xcrun', 'simctl', 'privacy', device, 'grant', 'photos', 'Mango.Celluloid'])]:
        code, _ = run(label, seconds, *command)
        if label == 'bootstatus': host('after-bootstatus')
        if code:
            host('failed-' + label)
            if label == 'install-before-import':
                inspected, container = run('read-only-install-reconciliation', 45, 'xcrun', 'simctl', 'get_app_container', device, 'Mango.Celluloid', 'app')
                print('BOOTSTRAP_INSTALL_RECONCILIATION', json.dumps({'original_code': code, 'inspection_code': inspected,
                    'registered_app_container_observed': inspected == 0, 'retry': False}), flush=True)
                if inspected == 0:
                    errors.append({'prerequisite': label, 'code': code})
                    print('BOOTSTRAP_RECOVERED_INSTALL original command remains a diagnostic failure', flush=True)
                    continue
            raise RuntimeError('Bootstrap prerequisite failed: ' + label)
host('before-PhotoKit-readiness')
initial = test('readiness-before-import', 'testPhotosLibraryBootstrapReadiness')
assert initial['synthetic'] == [], initial
host('before-import')
paths = [pathlib.Path('/tmp/celluloid-fixture.png'), pathlib.Path('/tmp/celluloid-fixture-2.png')] + sorted(pathlib.Path('/tmp').glob('celluloid-composition-*.png'))
expected = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
for index, path in enumerate(paths):
    print('BOOTSTRAP_INTENDED_FIXTURE', path.name, path.stat().st_size, expected[path.name], flush=True)
    # Cold first-import recovery was observed by365–412s; later imports took<4s.
    # Allow one bounded cold start, without retrying or weakening app-test limits.
    seconds = 480 if index == 0 else 180
    print('BOOTSTRAP_IMPORT_BOUND', json.dumps({'index': index, 'seconds': seconds, 'cold_first_import': index == 0}), flush=True)
    code, _ = run('import-' + str(index), seconds, 'xcrun', 'simctl', 'addmedia', device, str(path))
    if code:
        errors.append({'file': path.name, 'code': code})
        host('import-timeout')
        reconciled = test('reconcile-timeout-' + str(index), 'testReconcileSyntheticPhotosAfterImport')
        matches = [r for r in reconciled['synthetic'] if r['filename'] == path.name]
        print('BOOTSTRAP_TIMEOUT_RECONCILIATION', json.dumps({'file': path.name, 'matches': matches, 'retry': False}), flush=True)
        # Never blindly re-import an operation that may have committed after timeout.
        if len(matches) != 1 or matches[0].get('sha256') != expected[path.name]:
            raise RuntimeError('Import outcome is absent, duplicated or wrong; preserve state and do not retry')
        print('BOOTSTRAP_RECOVERED_ASSET_OBSERVED original command still counts as diagnostic failure', flush=True)
final = test('reconcile-all', 'testReconcileSyntheticPhotosAfterImport')
assert len(final['synthetic']) == len(expected), final
for name, digest in expected.items():
    matches = [r for r in final['synthetic'] if r['filename'] == name]
    assert len(matches) == 1 and matches[0]['sha256'] == digest, (name, matches)
print('BOOTSTRAP_EXACT_SIX_ASSETS_VERIFIED', flush=True)
pathlib.Path('/tmp/celluloid-bootstrap-assets-verified').write_text('verified\n')
host('after-import')
if errors:
    print('BOOTSTRAP_RECOVERED_COMMAND_FAILURES', json.dumps(errors), flush=True)
    sys.exit(1)
