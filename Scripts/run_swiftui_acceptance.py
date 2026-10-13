#!/usr/bin/env python3
"""One build, one owned simulator, one bounded unsigned acceptance sequence."""
from pathlib import Path
import json, math, os, re, signal, subprocess, sys, time, uuid
from run_picker_acceptance import build_binding, check_build, qualify_summary, runtime_warning_report

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/swiftui-acceptance'
DERIVED = ROOT / '.build/swiftui-ios'
PREVIEW_CONTINUATION = '38409908167:1:7c0c4e01537ab46771875d58f9d0a579a759e932'

def continuation_scope(environment):
    token = environment.get('CELLULOID_PREVIEW_CONTINUATION', '')
    require(token in ['', PREVIEW_CONTINUATION], 'Unreviewed preview continuation identity')
    return bool(token)

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

HOSTED_DEPLOYMENT_SELECTOR = 'CelluloidTests/PhoneEntryDesignTests/testOriginalUIKitStyleMeasurementsAreRetained'

def validate_hosted_deployment(summary, log, device, dispatched_wall, returned_wall):
    qualify_summary(summary, 1, device)
    require(summary.get('runtimeWarnings') == [], 'Hosted deployment runtime warnings')
    events = re.findall(r"^Test Case '-\[([^\]]+)\]' (.+)$", log, re.M)
    identity = 'CelluloidTests.PhoneEntryDesignTests testOriginalUIKitStyleMeasurementsAreRetained'
    event_lines = re.findall(r'^[ \t]*Test [Cc]ase\b.*$', log, re.M)
    require(len(event_lines) == len(events) == 2 and events[0] == (identity, 'started.')
            and events[1][0] == identity
            and re.fullmatch(r'passed \([0-9]+(?:\.[0-9]+)? seconds\)\.', events[1][1]) is not None,
            'Missing, duplicate, failed or different hosted deployment method')
    require(re.findall(r'^\*\* TEST EXECUTE (.+) \*\*$', log, re.M) == ['SUCCEEDED']
            and re.search(r'\b(?:retry|retrying|retries|restart|restarting|rerun|rerunning)\b', log, re.I) is None,
            'Hosted deployment retried or did not finish successfully')
    # Reject explicit tool/compiler diagnostics, not ordinary application words
    # such as historical expected-failure test names or an fopen log message.
    require(re.search(r'^(?:(?:---\s*)?xcodebuild:\s*|[^\n]+:\d+(?::\d+)?:\s*)?'
                      r'(?:warning|error|fatal error):', log, re.M | re.I) is None,
            'Hosted deployment has a tool or compiler warning/error')
    start, finish = summary.get('startTime'), summary.get('finishTime')
    require(all(type(value) in [int, float] and math.isfinite(value)
                for value in [start, finish, dispatched_wall, returned_wall])
            and dispatched_wall <= start <= finish <= returned_wall,
            'Hosted deployment summary is stale or outside this command')

class Acceptance:
    def __init__(self):
        self.preview_only = continuation_scope(os.environ)
        self.work_seconds = 2280
        self.started = time.monotonic(); self.deadline = self.started + self.work_seconds
        self.device = None; self.uncertain = False; self.events = []; self.failures = []
        self.source = os.environ.get('GITHUB_SHA', ''); self.source_tree = ''
        OUT.mkdir(parents=True, exist_ok=True)
        require(not (OUT / 'acceptance.json').exists(), 'Refusing to reuse an earlier run')

    def admit(self, name, seconds, simulator=False):
        require(not (self.uncertain and (simulator or getattr(self, 'preview_only', False))), 'Uncertain native state blocks further simulator work')
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
                if self.preview_only and (type(code) is not int or code < 0 or 128 <= code <= 255 or code == 124):
                    self.uncertain = True  # Latch before log/receipt I/O or any next command.
        except BaseException:
            # An interrupted wrapper cannot attest that its native descendants stopped.
            if simulator or self.preview_only: self.uncertain = True
            raise
        elapsed = time.monotonic() - began
        late = self.preview_only and elapsed > seconds
        if late:
            self.uncertain = True
            self.failures.append({'phase': name, 'exit_code': 124})
        if self.preview_only: require(type(code) is int, 'Untrusted wrapper exit status')
        log = target.read_text(errors='replace')
        if simulator and (code in [124, 137, 143] or 'BOUNDED_COMMAND_TIMEOUT' in log or 'CLEANUP_UNCONFIRMED' in log): self.uncertain = True
        self.events.append({'phase': name, 'exit_code': code, 'elapsed_seconds': elapsed,
                            'maximum_seconds': seconds, 'simulator': simulator, 'uncertain': self.uncertain})
        save(OUT / 'phases.json', self.events)
        print('ACCEPTANCE_PHASE_END', json.dumps(self.events[-1]), flush=True)
        if code: self.failures.append({'phase': name, 'exit_code': code})
        require(not late, name + ': parent dispatch deadline exceeded')
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

    def deploy_hosted_app(self, base, binary):
        # An existing permission-independent hosted XCTest makes Xcode deploy
        # this same built App, embedded extension and test bundle. No second
        # simctl install is issued. Registration/grant/readiness remain below.
        binding = json.loads((OUT / 'build-binding.json').read_text())
        check_build(binding, binary, self.source, self.source_tree)
        run_id, attempt = os.environ.get('GITHUB_RUN_ID', ''), os.environ.get('GITHUB_RUN_ATTEMPT', '')
        require(re.fullmatch(r'[1-9][0-9]*', run_id) and attempt == '1', 'Wrong hosted deployment run identity')
        result = OUT / ('hosted-deployment-' + run_id + '-' + attempt + '.xcresult')
        require(not result.exists() and not result.is_symlink(), 'Refuse stale hosted deployment result')
        selector = HOSTED_DEPLOYMENT_SELECTOR
        dispatched_wall = time.time(); dispatched = time.monotonic()
        code, log = self.command('deploy-hosted-app', [*base,
            '-resultBundlePath', str(result), '-parallel-testing-enabled', 'NO',
            '-collect-test-diagnostics', 'never', '-only-testing:' + selector,
            'test-without-building'], 210, simulator=True, allow_failure=True)
        returned_wall = time.time()
        if time.monotonic() - dispatched > 210: self.uncertain = True
        require(code == 0 and not self.uncertain, 'Uncertain hosted deployment forbids summary and bootstrap')
        require(result.is_dir() and not result.is_symlink() and result.resolve().parent == OUT.resolve(),
                'Missing or foreign hosted deployment xcresult')
        _, raw = self.command('deploy-hosted-app-summary', ['xcrun', 'xcresulttool', 'get',
            'test-results', 'summary', '--path', str(result)], 30)
        summary = extract_json(raw, 'totalTestCount')
        save(OUT / 'hosted-deployment-summary.json', summary)
        validate_hosted_deployment(summary, log, self.device, dispatched_wall, returned_wall)
        check_build(binding, binary, self.source, self.source_tree)
        save(OUT / 'hosted-deployment.json', {'schema': 'Celluloid.PreviewHostedDeployment.1',
             'source_sha': self.source, 'source_tree': self.source_tree,
             'run_id': run_id, 'run_attempt': attempt, 'result_bundle_path': str(result),
             'dispatch_wall': dispatched_wall, 'return_wall': returned_wall,
             'device_id': self.device, 'selector': selector, 'passed': 1,
             'skipped': 0, 'runtime_warnings': 0, 'build_binding': binding,
             'deployment_phase_seconds': 210, 'summary_phase_seconds': 30,
             'manual_simctl_install': False, 'photos_host_methods_executed': 0})

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
        for name in ([] if self.preview_only else ['Core', 'Rendering']):
            self.command('package-' + name.lower(), ['swift', 'test', '--package-path', 'Packages/Celluloid' + name,
                         '--scratch-path', '.build/swiftui-' + name.lower(), '--jobs', '2'], 300)
        self.command('boot', ['xcrun', 'simctl', 'boot', device], 60, simulator=True)
        self.command('bootstatus', ['xcrun', 'simctl', 'bootstatus', device, '-b'], 300, simulator=True)
        if self.preview_only:
            self.deploy_hosted_app(base, binary)
        if not self.preview_only:
            code, _ = self.command('units', [*base, '-resultBundlePath', str(OUT / 'units.xcresult'),
                     '-parallel-testing-enabled', 'NO', '-collect-test-diagnostics', 'never',
                     *['-only-testing:' + s for s in UNIT_SELECTORS],
                     '-skip-testing:CelluloidTests/PhotoSelectionSessionTests/testRealSelectedLookupPreservesOrderAndIdentity', 'test-without-building'],
                     420, simulator=True, allow_failure=True)
            summary_code, raw = self.command('units-summary', ['xcrun', 'xcresulttool', 'get', 'test-results', 'summary',
                                            '--path', str(OUT / 'units.xcresult')], 30, allow_failure=True)
            if summary_code == 0:
                summary = extract_json(raw, 'totalTestCount'); save(OUT / 'units-summary.json', summary)
                save(OUT / 'units-runtime-warnings.json', runtime_warning_report(summary))
                if code == 0: qualify_summary(summary, 67, device)
            # A completed failed assertion stays failed, while independent evidence may continue.
            # A timeout/uncertain simulator state blocks all subsequent native work.
            self.picker('stock')
            self.photos('legacy', 660)
        if self.photos('bootstrap', 750) == 0 and not self.uncertain:
            if self.photos('pristine', 660) == 0 and not self.uncertain:
                self.picker('seeded')
                if not self.preview_only: self.photos('preservation', 660)
        self.command('clean-end', ['git', 'diff', '--exit-code', 'HEAD', '--'], 15)

    def cleanup(self):
        if not self.device or self.uncertain: return
        deadline = min(self.deadline + 90, time.monotonic() + 90)
        for action in ['shutdown', 'delete']:
            if deadline - time.monotonic() < 35: return
            dispatched = time.monotonic()
            try:
                with (OUT / ('cleanup-' + action + '.log')).open('wb') as output:
                    code = subprocess.call([sys.executable, 'Scripts/run_bounded.py', '--seconds', '30', '--label', 'cleanup-' + action,
                                            'xcrun', 'simctl', action, self.device], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
            except BaseException:
                if self.preview_only: self.uncertain = True
                raise
            if code or (self.preview_only and (type(code) is not int or time.monotonic() - dispatched > 30)):
                self.uncertain = True; return
        self.device = None

def main():
    os.chdir(ROOT); os.environ['TZ'] = 'UTC'
    if hasattr(time, 'tzset'): time.tzset()
    gate = Acceptance(); error = None
    def stop(signum, frame): raise KeyboardInterrupt('Native acceptance interrupted')
    signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
    try: gate.run()
    except BaseException as failure:
        error = str(failure)
        if gate.preview_only and isinstance(failure, (KeyboardInterrupt, SystemExit)): gate.uncertain = True
    finally:
        if gate.preview_only:
            try: gate.cleanup()
            except BaseException as failure:
                gate.uncertain = True; error = error or str(failure)
        else: gate.cleanup()
        accepted = error is None and not gate.failures and not gate.device and not gate.uncertain
        warning_paths = ['units-runtime-warnings.json', 'picker-stock-runtime-warnings.json', 'picker-seeded-runtime-warnings.json']
        warning_paths += ['photos/' + phase + '-runtime-warnings.json' for phase in ['legacy', 'pristine', 'preservation']]
        warning_reports = {path: json.loads((OUT / path).read_text()) for path in warning_paths if (OUT / path).is_file()}
        review_count = sum(report['other_warning_review_count'] for report in warning_reports.values())
        status = 'failed' if not accepted else ('review_required' if review_count else ('preview_observation_passed' if gate.preview_only else 'passed'))
        save(OUT / 'acceptance.json', {'status': status, 'all_required_phases_accepted': accepted and not gate.preview_only, 'current_slice_accepted': accepted,
             'validation_scope': 'seeded_preview_continuation' if gate.preview_only else 'full_acceptance',
             'historical_reference': PREVIEW_CONTINUATION if gate.preview_only else None,
             'historical_reference_is_current_source_acceptance': False,
             'not_executed_in_this_slice': ['67-unit suite', 'stock picker', 'legacy48', 'preservation6', 'Core and Rendering packages'] if gate.preview_only else [], 'error': error,
             'runtime_warning_review_required': review_count > 0, 'runtime_warning_review_count': review_count,
             'runtime_warning_reports': warning_reports,
             'failed_phases': gate.failures, 'source_sha': gate.source, 'source_tree': gate.source_tree,
             'pending_owned_device': gate.device, 'simulator_uncertain': gate.uncertain,
             'work_budget_seconds': gate.work_seconds, 'elapsed_seconds': time.monotonic() - gate.started,
             'visual_acceptance': 'requires actual screenshot review', 'release_qualification': False})
    return 0 if accepted else 1

if __name__ == '__main__': raise SystemExit(main())
