#!/usr/bin/env python3
"""One build, one owned simulator, one bounded unsigned acceptance sequence."""
from pathlib import Path
import json, os, re, signal, subprocess, sys, time, uuid
from run_picker_acceptance import build_binding, qualify_summary

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/swiftui-acceptance'
DERIVED = ROOT / '.build/swiftui-ios'
UNIT_SELECTORS = [
    'CelluloidTests/PhotoSelectionIdentityTests', 'CelluloidTests/PhotoSelectionSessionTests',
    'CelluloidTests/SwiftUIEditorSessionTests', 'CelluloidTests/PhoneEntryDesignTests',
    'CelluloidTests/SwiftUIOriginalDesignTests', 'CelluloidTests/AsyncImagePipelineTests',
    'CelluloidTests/FilterTests', 'CelluloidTests/PhotosOutputWriteTests',
    'CelluloidTests/AdjustmentDataTests/testLegacyArchiveRoundTripsWithoutChangingItsDictionary',
    'CelluloidTests/AdjustmentDataTests/testResourceBoundariesPreserveEveryLegacyLayerAndTextUnit',
    'CelluloidTests/AdjustmentDataTests/testMalformedArchivesAndUnexpectedClassesAreRejected']

def require(value, message):
    if not value: raise ValueError(message)

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

def extract_json(text, key):
    matches = []
    for match in re.finditer(r'^\s*\{', text, re.M):
        try: value, _ = json.JSONDecoder().raw_decode(text[match.start():].lstrip())
        except json.JSONDecodeError: continue
        if isinstance(value, dict) and key in value: matches.append(value)
    require(len(matches) == 1, 'Missing/ambiguous native JSON: ' + key)
    return matches[0]

def owner_receipt(before, after, device, environment, source, started, deadline):
    uuid.UUID(device)
    require(not any(d.get('udid') == device for ds in before['devices'].values() for d in ds), 'Device existed before this job')
    matches = [(runtime, d) for runtime, ds in after['devices'].items() for d in ds if d.get('udid') == device]
    require(len(matches) == 1, 'Created device is missing/ambiguous')
    runtime, item = matches[0]
    require(runtime == 'com.apple.CoreSimulator.SimRuntime.iOS-27-0' and item.get('isAvailable') is True,
            'Wrong created runtime or unavailable device')
    require(item.get('name') == 'Celluloid iOS27 iPhone SE (3rd generation)', 'Wrong owned device name')
    require(item.get('state') == 'Shutdown', 'New simulator was not initially shutdown')
    require(all(re.fullmatch(r'[1-9][0-9]*', environment.get(k, '')) for k in ['GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT']), 'Missing CI ownership identity')
    return {'schema': 'celluloid.swiftui.owned-simulator.v1', 'device_id': device, 'device_name': item['name'],
            'runtime_id': runtime, 'source_sha': source, 'run_id': environment['GITHUB_RUN_ID'],
            'run_attempt': environment['GITHUB_RUN_ATTEMPT'], 'created_by_this_job': True, 'absent_before_create': True,
            'job_started_monotonic': started, 'work_deadline_monotonic': deadline}

class Acceptance:
    def __init__(self):
        self.started = time.monotonic(); self.deadline = self.started + 2280
        self.device = None; self.uncertain = False; self.events = []; self.failures = []
        self.source = os.environ.get('GITHUB_SHA', ''); self.source_tree = ''
        OUT.mkdir(parents=True, exist_ok=True)
        require(not (OUT / 'acceptance.json').exists(), 'Refusing to reuse an earlier run')

    def admit(self, name, seconds, simulator=False):
        require(not simulator or not self.uncertain, 'Uncertain native state blocks further simulator work')
        remaining = self.deadline - time.monotonic()
        require(remaining >= seconds + 15, name + ': full phase and cleanup allowance do not fit; no dispatch')
        print('ACCEPTANCE_PHASE_BEGIN', json.dumps({'phase': name, 'maximum_seconds': seconds,
              'remaining_work_seconds': remaining, 'wall_seconds': time.time(), 'monotonic': time.monotonic()}), flush=True)

    def command(self, name, command, seconds, simulator=False, allow_failure=False, nested_owned=False):
        self.admit(name, seconds, simulator)
        target = OUT / (name + '.log'); began = time.monotonic()
        argv = command if nested_owned else [sys.executable, 'Scripts/run_bounded.py', '--seconds', str(seconds), '--label', name, *command]
        try:
            with target.open('wb') as output:
                code = subprocess.call(argv, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                       env=dict(os.environ, TZ='UTC', TEST_RUNNER_TZ='UTC'))
        except BaseException:
            # An interrupted wrapper cannot attest that its native descendants stopped.
            if simulator: self.uncertain = True
            raise
        elapsed = time.monotonic() - began
        log = target.read_text(errors='replace')
        if simulator and (code in [124, 137, 143] or 'BOUNDED_COMMAND_TIMEOUT' in log or 'CLEANUP_UNCONFIRMED' in log): self.uncertain = True
        self.events.append({'phase': name, 'exit_code': code, 'elapsed_seconds': elapsed,
                            'maximum_seconds': seconds, 'simulator': simulator, 'uncertain': self.uncertain})
        save(OUT / 'phases.json', self.events)
        print('ACCEPTANCE_PHASE_END', json.dumps(self.events[-1]), flush=True)
        if code: self.failures.append({'phase': name, 'exit_code': code})
        require(time.monotonic() <= self.deadline, name + ': shared work deadline exceeded')
        require(allow_failure or code == 0, name + ' failed')
        return code, log

    def photos(self, stage, cap):
        code, _ = self.command('photos-' + stage, ['/bin/bash', 'Scripts/run_swiftui_photos_gate.sh', stage,
              self.device, str(DERIVED), str(OUT / 'photos'), str(OUT / 'owned-simulator.json')], cap,
              simulator=True, allow_failure=True, nested_owned=True)
        safety = OUT / 'photos' / (stage + '-safety.json')
        record = json.loads(safety.read_text()) if safety.is_file() else {}
        if (record.get('phase') != stage or record.get('exit_code') != code
                or any(type(record.get(k)) is not bool for k in ['timeout_observed', 'cleanup_uncertain_observed',
                            'shared_deadline_exhausted', 'prohibit_further_simctl'])
                or record.get('prohibit_further_simctl') is not False):
            self.uncertain = True
        return code

    def picker(self, stage):
        command = [sys.executable, 'Scripts/run_picker_acceptance.py', stage, '--device', self.device,
                   '--derived', str(DERIVED), '--out', str(OUT), '--owner', str(OUT / 'owned-simulator.json'),
                   '--build-binding', str(OUT / 'build-binding.json')]
        if stage == 'seeded': command += ['--fixture-manifest', str(OUT / 'photos/verified-library.json')]
        code, _ = self.command('picker-' + stage + '-gate', command, 405, simulator=True, allow_failure=True, nested_owned=True)
        result = OUT / ('picker-' + stage + '-acceptance.json')
        record = json.loads(result.read_text()) if result.is_file() else {}
        if (record.get('phase') != stage or record.get('source_sha') != self.source
                or record.get('source_tree') != self.source_tree or record.get('prohibit_further_simctl') is not False):
            self.uncertain = True
        return code

    def run(self):
        require(sys.platform == 'darwin', 'Native gate requires xcode-27')
        require(os.environ.get('DEVELOPER_DIR') == '/Applications/Xcode_27.app/Contents/Developer', 'Wrong Xcode route')
        require(os.environ.get('GITHUB_REPOSITORY') == '100mango/Celluloid' and os.environ.get('GITHUB_REF') == 'refs/heads/swiftui-first-native'
                and os.environ.get('GITHUB_EVENT_NAME') == 'push' and os.environ.get('GITHUB_WORKFLOW_SHA') == self.source, 'Wrong source workflow route')
        require(re.fullmatch(r'[0-9a-f]{40}', self.source), 'Missing exact source SHA')
        checked = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True, timeout=15).strip()
        require(checked == self.source, 'Checked-out source mismatch')
        self.source_tree = subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], cwd=ROOT, text=True, timeout=15).strip()
        self.command('clean-start', ['git', 'diff', '--exit-code', 'HEAD', '--'], 15)
        _, version = self.command('toolchain', ['xcodebuild', '-version'], 30)
        require('Xcode 27.0' in version.splitlines(), 'Wrong stable Xcode')
        (ROOT / 'build/swiftui-xcode-version.txt').write_text(version)
        _, topology = self.command('topology', [sys.executable, 'Scripts/verify_swiftui_integration.py'], 30)
        save(ROOT / 'build/swiftui-topology.json', extract_json(topology, 'checks'))
        for filename in ['test_picker_native_receipt.py', 'test_swiftui_photos_gate.py', 'test_swiftui_acceptance.py']:
            self.command(filename.removesuffix('.py'), [sys.executable, 'Scripts/' + filename], 30)
        _, before_text = self.command('devices-before', ['xcrun', 'simctl', 'list', 'devices', 'available', '-j'], 20, simulator=True)
        before = extract_json(before_text, 'devices'); save(OUT / 'devices-before.json', before)
        _, created = self.command('create-owned-device', [sys.executable, 'Scripts/select_test_devices.py', 'iPhone SE (3rd generation)'], 60, simulator=True)
        matches = re.findall(r'^([0-9A-Fa-f-]{36}) iPhone SE \(3rd generation\)$', created, re.M)
        require(len(matches) == 1, 'Missing/ambiguous create receipt')
        device = matches[0]
        _, after_text = self.command('devices-after-create', ['xcrun', 'simctl', 'list', 'devices', 'available', '-j'], 20, simulator=True)
        after = extract_json(after_text, 'devices'); save(OUT / 'devices-after-create.json', after)
        owner = owner_receipt(before, after, device, os.environ, self.source, self.started, self.deadline)
        self.device = device; save(OUT / 'owned-simulator.json', owner)
        base = ['xcodebuild', '-project', 'Celluloid.xcodeproj', '-scheme', 'Celluloid', '-configuration', 'Debug',
                '-destination', 'platform=iOS Simulator,id=' + device, '-derivedDataPath', str(DERIVED),
                'CODE_SIGNING_ALLOWED=NO', 'CODE_SIGNING_REQUIRED=NO', 'COMPILER_INDEX_STORE_ENABLE=NO']
        self.command('build', [*base, '-jobs', '2', 'build-for-testing'], 720)
        binary = DERIVED / 'Build/Products/Debug-iphonesimulator/Celluloid.app/Celluloid'
        save(OUT / 'build-binding.json', build_binding(binary, self.source, self.source_tree))
        for name in ['Core', 'Rendering']:
            self.command('package-' + name.lower(), ['swift', 'test', '--package-path', 'Packages/Celluloid' + name,
                         '--scratch-path', '.build/swiftui-' + name.lower(), '--jobs', '2'], 300)
        self.command('boot', ['xcrun', 'simctl', 'boot', device], 60, simulator=True)
        self.command('bootstatus', ['xcrun', 'simctl', 'bootstatus', device, '-b'], 300, simulator=True)
        code, _ = self.command('units', [*base, '-resultBundlePath', str(OUT / 'units.xcresult'),
                 '-parallel-testing-enabled', 'NO', '-collect-test-diagnostics', 'never',
                 *['-only-testing:' + s for s in UNIT_SELECTORS],
                 '-skip-testing:CelluloidTests/PhotoSelectionSessionTests/testRealSelectedLookupPreservesOrderAndIdentity', 'test-without-building'],
                 420, simulator=True, allow_failure=True)
        summary_code, raw = self.command('units-summary', ['xcrun', 'xcresulttool', 'get', 'test-results', 'summary',
                                        '--path', str(OUT / 'units.xcresult')], 30, allow_failure=True)
        if summary_code == 0:
            summary = extract_json(raw, 'totalTestCount'); save(OUT / 'units-summary.json', summary)
            if code == 0: qualify_summary(summary, 57, device)
        # A completed failed assertion stays failed, while independent evidence may continue.
        # A timeout/uncertain simulator state blocks all subsequent native work.
        self.picker('stock')
        self.photos('legacy', 660)
        if self.photos('bootstrap', 750) == 0 and not self.uncertain:
            if self.photos('pristine', 660) == 0 and not self.uncertain:
                self.picker('seeded')
                self.photos('preservation', 660)
        self.command('clean-end', ['git', 'diff', '--exit-code', 'HEAD', '--'], 15)

    def cleanup(self):
        if not self.device or self.uncertain: return
        deadline = min(self.started + 2370, time.monotonic() + 90)
        for action in ['shutdown', 'delete']:
            if deadline - time.monotonic() < 35: return
            with (OUT / ('cleanup-' + action + '.log')).open('wb') as output:
                code = subprocess.call([sys.executable, 'Scripts/run_bounded.py', '--seconds', '30', '--label', 'cleanup-' + action,
                                        'xcrun', 'simctl', action, self.device], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
            if code: self.uncertain = True; return
        self.device = None

def main():
    os.chdir(ROOT); os.environ['TZ'] = 'UTC'
    if hasattr(time, 'tzset'): time.tzset()
    gate = Acceptance(); error = None
    def stop(signum, frame): raise KeyboardInterrupt('Native acceptance interrupted')
    signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
    try: gate.run()
    except BaseException as failure: error = str(failure)
    finally:
        gate.cleanup()
        accepted = error is None and not gate.failures and not gate.device and not gate.uncertain
        save(OUT / 'acceptance.json', {'all_required_phases_accepted': accepted, 'error': error,
             'failed_phases': gate.failures, 'source_sha': gate.source, 'source_tree': gate.source_tree,
             'pending_owned_device': gate.device, 'simulator_uncertain': gate.uncertain,
             'work_budget_seconds': 2280, 'elapsed_seconds': time.monotonic() - gate.started,
             'visual_acceptance': 'requires actual screenshot review', 'release_qualification': False})
    return 0 if accepted else 1

if __name__ == '__main__': raise SystemExit(main())
