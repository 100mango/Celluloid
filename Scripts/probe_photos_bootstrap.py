#!/usr/bin/env python3
"""Read-only PhotoKit readiness then reconciled synthetic import; never retry imports."""
import argparse, datetime, hashlib, json, os, pathlib, re, subprocess, sys, time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('device')
parser.add_argument('--already-prepared', action='store_true')
parser.add_argument('--derived-data-path', default='.build', help='Reuse the caller-owned build; legacy default is unchanged')
parser.add_argument('--deadline-monotonic', type=float, help='Optional shared-job preparation deadline; never extends original command ceilings')
options = parser.parse_args()
device = options.device
bootstrap_deadline = options.deadline_monotonic
errors = []
evidence_root = pathlib.Path(os.environ.get('RUNNER_TEMP', '.build/bootstrap-evidence'))
evidence_root.mkdir(parents=True, exist_ok=True)

# Only the fixed full-shipping route uses this already-owned command adapter.
# Canonical invocations retain their original helper and command ceilings.
full_row = os.environ.get('CELLULOID_VALIDATION_SCOPE') in {'uikit-full-shipping','original-ios-release'}

def row_clock():
    from validation_route import current_route,UIKIT_FULL,ORIGINAL_IOS
    from mac_host_transport import load_json
    from uikit_full_shipping_gate import clock_status
    if current_route() not in [UIKIT_FULL,ORIGINAL_IOS]:raise ValueError('Wrong full-shipping bootstrap route')
    path=evidence_root/'full-shipping-clock.json'
    if path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=10_000:raise ValueError('Invalid fixed row clock')
    clock=load_json(path.read_bytes())
    context={'source_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],
             'run_attempt':os.environ['GITHUB_RUN_ATTEMPT'],'row':os.environ['CELLULOID_FULL_ROW']}
    return clock,context,clock_status(clock,context)

def require_inner_allowance(seconds):
    deadline = globals().get('bootstrap_deadline')
    if deadline is not None and time.monotonic() + seconds + 15 > deadline:
        raise TimeoutError('Shared Photos bootstrap deadline cannot fit command and cleanup; no dispatch')
    from original_ios_process_guard import ensure_native_dispatch
    ensure_native_dispatch()
    if not full_row:return
    _,_,status=row_clock()
    if status['work_remaining_seconds'] < seconds+15:
        raise TimeoutError('Full original bootstrap command and cleanup allowance do not fit; no dispatch')

def check_inner_completion():
    if not full_row:return
    from uikit_full_shipping_gate import check_completion
    clock,context,_=row_clock();check_completion(clock,context,'bootstrap')

def run(label, seconds, *args):
    deadline = globals().get('bootstrap_deadline')
    if deadline is not None:
        remaining = deadline - time.monotonic() - 15
        if remaining <= 0: raise TimeoutError('Shared Photos bootstrap preparation deadline expired; no dispatch')
        seconds = min(seconds, remaining)
    if full_row:
        # Direct owned group: do not kill an outer helper while its actual
        # xcodebuild/simctl command lives in a separate inner process group.
        from native_process import run as owned_run
        require_inner_allowance(seconds)
        try:
            result=owned_run(args,timeout=seconds,check=False,echo=False,log_name='bootstrap-'+label+'.log')
        except (TimeoutError,RuntimeError,OSError):
            path=evidence_root/('bootstrap-'+label+'.log')
            if path.is_file() and not path.is_symlink() and path.stat().st_size<=30_000_000:
                print(path.read_text(),end='',flush=True)
            raise  # No later import/probe after unconfirmed or timed-out work.
        check_inner_completion()
        output=result.stdout+'\n'+result.stderr
        print(output,end='',flush=True)
        return result.returncode,output
    result = subprocess.run([sys.executable, 'Scripts/run_bounded.py', '--seconds', str(seconds), '--label', label, *args],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (evidence_root / ('bootstrap-' + label + '.log')).write_text(result.stdout)
    print(result.stdout, end='', flush=True)
    return result.returncode, result.stdout

def host_command(command):
    from original_ios_process_guard import active,require_clear
    if active():
        from native_process import run as owned_run
        value=owned_run(command,timeout=15,check=False,echo=False)
        require_clear() # Signal termination cannot be treated as ordinary nonzero.
        return value
    return subprocess.run(command,capture_output=True,text=True,timeout=15)

def host(label):
    deadline = globals().get('bootstrap_deadline')
    if deadline is not None and deadline - time.monotonic() < 180:
        print('BOOTSTRAP_OPTIONAL_HOST_WITHHELD preserving shared job preparation and cleanup allowance',flush=True);return
    if full_row and row_clock()[2]['work_remaining_seconds'] < 630:
        print('BOOTSTRAP_OPTIONAL_HOST_WITHHELD preserving next command and cleanup allowance',flush=True);return
    print('BOOTSTRAP_HOST_BEGIN', label, datetime.datetime.now(datetime.timezone.utc).isoformat(), flush=True)
    for command in [['vm_stat'], ['memory_pressure', '-Q'], ['sysctl', 'vm.swapusage'], ['df', '-h', '.']]:
        try:
            require_inner_allowance(15)
            value = host_command(command)
            check_inner_completion()
            print('BOOTSTRAP_HOST', command[0], value.returncode, value.stdout[:4500], value.stderr[:500], flush=True)
        except subprocess.TimeoutExpired: print('BOOTSTRAP_HOST_TIMEOUT', command[0], flush=True)
    try:
        require_inner_allowance(15)
        value = host_command(['ps', '-axo', 'pid=,ppid=,rss=,comm='])
        check_inner_completion()
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

def test(label, method, derived_data_path='.build'):
    code, output = run(label, 360, 'xcodebuild', '-project', 'Celluloid.xcodeproj', '-scheme', 'Celluloid',
        '-configuration', 'Debug', '-destination', 'platform=iOS Simulator,id=' + device, '-derivedDataPath', derived_data_path,
        '-resultBundlePath', str(evidence_root / ('Bootstrap-' + label + '.xcresult')), '-parallel-testing-enabled', 'NO', '-collect-test-diagnostics', 'never',
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
        ('install-before-import', 120, ['xcrun', 'simctl', 'install', device, str(pathlib.Path(options.derived_data_path) / 'Build/Products/Debug-iphonesimulator/Celluloid.app')]),
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
initial = test('readiness-before-import', 'testPhotosLibraryBootstrapReadiness', options.derived_data_path)
assert initial['synthetic'] == [], initial
if bootstrap_deadline is not None and initial.get('asset_count', 65) > 58:
    raise RuntimeError('Observed stock inventory cannot fit six additions within the bounded gate; no import')
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
        reconciled = test('reconcile-timeout-' + str(index), 'testReconcileSyntheticPhotosAfterImport', options.derived_data_path)
        matches = [r for r in reconciled['synthetic'] if r['filename'] == path.name]
        print('BOOTSTRAP_TIMEOUT_RECONCILIATION', json.dumps({'file': path.name, 'matches': matches, 'retry': False}), flush=True)
        # Never blindly re-import an operation that may have committed after timeout.
        if len(matches) != 1 or matches[0].get('sha256') != expected[path.name]:
            raise RuntimeError('Import outcome is absent, duplicated or wrong; preserve state and do not retry')
        print('BOOTSTRAP_RECOVERED_ASSET_OBSERVED original command still counts as diagnostic failure', flush=True)
        if bootstrap_deadline is not None:
            raise RuntimeError('Shared-job bootstrap stops after a failed import; no later simctl mutation is authorized')
final = test('reconcile-all', 'testReconcileSyntheticPhotosAfterImport', options.derived_data_path)
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
