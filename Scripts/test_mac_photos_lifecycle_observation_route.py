"""Portable route/argv/fault tests; every Apple command is mocked, never executed."""
import contextlib,copy,hashlib,json,os,plistlib,re,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import run_mac_photos_lifecycle as route
from validation_route import LIFECYCLE,HOST_ONLY,FULL,host_clock_profile,current_route

ROOT=Path(__file__).resolve().parents[1]

class LifecycleRouteSourceTests(unittest.TestCase):

    def test_fixed_workflow_one_standard_mac_one_push_without_dispatch_or_matrix(self):
        raw = (ROOT / route.WORKFLOW).read_text()
        self.assertIn('branches: [codex/photos-lifecycle-observation]', raw)
        self.assertEqual(raw.count('runs-on:'), 1)
        self.assertIn('runs-on: xcode-27', raw)
        for value in ['timeout-minutes: 45', "execution_budget_seconds':41*60", 'timeout-minutes: 41', 'timeout-minutes: 5', 'fetch-depth: 2', 'persist-credentials: false', 'contents: read', 'retention-days: 1']:
            self.assertIn(value, raw)
        for value in ['matrix:', 'workflow_dispatch:', 'workflow_run:', 'pull_request:', 'apple-platforms.yml', 'mac-repair.yml']:
            self.assertNotIn(value, raw)
        for path in (ROOT / '.github/workflows').glob('*.yml'):
            if path.name != Path(route.WORKFLOW).name:
                self.assertNotIn('codex/photos-lifecycle-observation', path.read_text())

    def test_new_route_reuses_exact_original_host_clock_and_cannot_relabel_old_branch(self):
        self.assertEqual(host_clock_profile(LIFECYCLE), host_clock_profile(HOST_ONLY))
        env = {'GITHUB_REF': 'refs/heads/' + LIFECYCLE['branch'], 'GITHUB_REPOSITORY': '100mango/Celluloid', 'GITHUB_EVENT_NAME': 'push', 'CELLULOID_VALIDATION_SCOPE': LIFECYCLE['scope'], 'GITHUB_WORKFLOW_REF': '100mango/Celluloid/' + route.WORKFLOW + '@refs/heads/' + LIFECYCLE['branch'], 'GITHUB_SHA': 'a' * 40, 'GITHUB_WORKFLOW_SHA': 'a' * 40}
        self.assertEqual(current_route(env), LIFECYCLE)
        for key, value in [('GITHUB_REF', 'refs/heads/codex/other'), ('GITHUB_EVENT_NAME', 'workflow_dispatch'), ('GITHUB_WORKFLOW_SHA', 'b' * 40), ('CELLULOID_VALIDATION_SCOPE', HOST_ONLY['scope'])]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                current_route(dict(env, **{key: value}))
        self.assertEqual(current_route(dict(env, GITHUB_REF='refs/heads/' + FULL['branch'])), FULL)

    def test_exact_argv_no_repetition_help_probe_or_extra_case(self):
        temp=Path('/private/var/folders/owned')
        for action in ['build-for-testing','build','test-without-building']:
            args=route.command(temp,action)
            self.assertEqual(args.count(action),1)
            for forbidden in ['-test-iterations','-retry-tests-on-failure','-help','compare_owned_photos_boundary.swift','build-for-testing-extra']:
                self.assertNotIn(forbidden,args)
            self.assertFalse(any('BOUNDARY' in arg or 'PROBE' in arg for arg in args))
        native=route.command(temp,'test-without-building')
        self.assertEqual([arg for arg in native if arg.startswith('-only-testing:')],['-only-testing:'+route.SELECTION])
        self.assertEqual(native[native.index('-maximum-test-execution-time-allowance')+1],'960')
        self.assertNotIn('read_capture',Path(route.__file__).read_text())
        self.assertNotIn('compare-build',Path(route.__file__).read_text())

    def test_source_inventory_full_freeze_mutation_symlink_and_self_reference(self):
        actual = json.loads((ROOT / route.MANIFEST).read_text())
        self.assertRegex(route.source_snapshot(ROOT, actual), '^[0-9a-f]{64}$')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / 'one').write_bytes(b'owned')
            row = {'path': 'one', 'mode': '100644', 'bytes': 5, 'sha256': route.sha(b'owned')}
            source = {'schema': 'Celluloid.OwnedPhotosLifecycleSource.1', 'parent': route.BASE, 'files': [row]}
            route.source_snapshot(root, source)
            for key, value in [('path', '../one'), ('path', route.MANIFEST), ('mode', '100755'), ('bytes', True), ('sha256', '0' * 64)]:
                changed = copy.deepcopy(source)
                changed['files'][0][key] = value
                with self.subTest(key=key), self.assertRaises(ValueError):
                    route.source_snapshot(root, changed)
            (root / 'one').unlink()
            (root / 'actual').write_bytes(b'owned')
            (root / 'one').symlink_to('actual')
            with self.assertRaises(ValueError):
                route.source_snapshot(root, source)

    def test_exact_source_admission_parent_inventory_and_attempt_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / 'Scripts').mkdir()
            (root / '.github/workflows').mkdir(parents=True)
            fixture = root / route.FIXTURE_PATH
            fixture.parent.mkdir(parents=True)
            fixture.write_bytes((ROOT / route.FIXTURE_PATH).read_bytes())
            (root / route.WORKFLOW).write_bytes(b'owned workflow fixture')
            paths = [route.FIXTURE_PATH, route.WORKFLOW]
            rows = [{'path': name, 'mode': '100644', 'bytes': (root / name).stat().st_size, 'sha256': route.sha((root / name).read_bytes())} for name in sorted(paths)]
            (root / route.MANIFEST).write_bytes(route.encoded({'schema': 'Celluloid.OwnedPhotosLifecycleSource.1', 'parent': route.BASE, 'files': rows}))
            env = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': '100mango/Celluloid', 'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF': 'refs/heads/' + LIFECYCLE['branch'], 'CELLULOID_VALIDATION_SCOPE': LIFECYCLE['scope'], 'GITHUB_WORKFLOW_REF': '100mango/Celluloid/' + route.WORKFLOW + '@refs/heads/' + LIFECYCLE['branch'], 'GITHUB_SHA': 'a' * 40, 'GITHUB_WORKFLOW_SHA': 'a' * 40, 'GITHUB_RUN_ID': '123456', 'GITHUB_RUN_ATTEMPT': '1', 'DEVELOPER_DIR': '/Applications/Xcode_27.app/Contents/Developer'}
            state = {'parent': route.BASE, 'dirty': b'', 'inventory': paths + [route.MANIFEST]}

            def git(*args):
                if args == ('rev-parse', 'HEAD'):
                    return ('a' * 40).encode()
                if args == ('rev-parse', 'HEAD^{tree}'):
                    return ('b' * 40).encode()
                if args[:1] == ('rev-list',):
                    return ('a' * 40 + ' ' + state['parent']).encode()
                if args[:1] == ('status',):
                    return state['dirty']
                if args == ('ls-files', '-z'):
                    return ('\x00'.join(state['inventory']) + '\x00').encode()
                raise AssertionError('unplanned git call')
            with patch.object(route, 'ROOT', root), patch.object(route.sys, 'platform', 'darwin'), patch.dict(os.environ, env), patch.object(route, 'git', side_effect=git) as calls:
                if not __debug__:
                    with self.assertRaisesRegex(ValueError, 'normal Python'):
                        route.admit_source()
                    calls.assert_not_called()
                    return
                _, proof = route.admit_source()
                self.assertEqual(proof['parent'], route.BASE)
                self.assertEqual(proof['run_attempt'], 1)
                for key, value in [('GITHUB_RUN_ATTEMPT', '2'), ('GITHUB_RUN_ID', '0'), ('GITHUB_WORKFLOW_SHA', 'c' * 40), ('GITHUB_EVENT_NAME', 'workflow_dispatch')]:
                    with patch.dict(os.environ, {key: value}), self.subTest(key=key), self.assertRaises(ValueError):
                        route.admit_source()
                for key, value in [('parent', 'c' * 40), ('parent', route.BASE + ' ' + 'd' * 40), ('dirty', b' M source'), ('inventory', state['inventory'] + ['extra'])]:
                    old = state[key]
                    state[key] = value
                    with self.subTest(key=key), self.assertRaises(ValueError):
                        route.admit_source()
                    state[key] = old

    def test_raw_completion_rejects_cli64_zero_case_wrong_path_unknown_or_late(self):
        bundle = '/owned/MacPhotosHost.xcresult'
        log = f"Test Case '{route.RAW_CASE}' started.\nTest Case '{route.RAW_CASE}' passed (1.0 seconds).\n{bundle}\n** TEST EXECUTE SUCCEEDED **\n"
        event = {'returned_without_timeout': True, 'return_code': 0, 'elapsed_seconds': 1}
        route.native_completion(log, event, bundle)
        for altered, e in [(log, dict(event, return_code=64)), (log, dict(event, elapsed_seconds=1021)), (log, dict(event, returned_without_timeout=False)), (log.replace(route.RAW_CASE, '-[Other testWrong]'), event), (log.replace(' passed (1.0 seconds).', ' skipped (1.0 seconds).'), event), (log.replace(bundle, '/other.xcresult'), event), ('** TEST EXECUTE FAILED **\n', dict(event, return_code=65))]:
            with self.subTest(event=e), self.assertRaises(ValueError):
                route.native_completion(altered, e, bundle)

    def test_summary_original_run_and_wall_interval_are_required(self):
        event = {'run_id': '123', 'run_attempt': 1, 'started_unix': 100, 'finished_unix': 110, 'elapsed_seconds': 10}
        before = {'run_id': '123', 'run_attempt': 1}
        summary = {'startTime': 101, 'finishTime': 109}
        route.check_summary_interval(summary, event, before)
        for changed in [dict(summary, finishTime=111), dict(summary, startTime=99), dict(summary, finishTime=float('nan'))]:
            with self.assertRaises(ValueError):
                route.check_summary_interval(changed, event, before)
        with self.assertRaises(ValueError):
            route.check_summary_interval(summary, dict(event, run_id='124'), before)

class LifecycleRouteFaultTests(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        base = Path(self.directory.name).resolve()
        parent = base / 'actual'
        parent.mkdir()
        self.root = parent / 'repo'
        self.root.mkdir()
        self.temp = parent / 'runner'
        self.temp.mkdir()
        self.alias = base / 'parent-alias'
        self.alias.symlink_to(parent, target_is_directory=True)
        (self.root / 'Platforms/macOSExtension').mkdir(parents=True)
        (self.root / 'Scripts').mkdir()
        (self.root / 'Platforms/macOSExtension/Info.plist').write_bytes((ROOT / 'Platforms/macOSExtension/Info.plist').read_bytes())
        (self.root / route.MANIFEST).write_bytes(b'{}')
        self.before = {'schema': 'source-fixture-only', 'source_sha': 'a' * 40, 'tree': 'b' * 40, 'parent': route.BASE, 'run_id': '123456', 'run_attempt': 1, 'source_fingerprint': 'f' * 64, 'source_manifest_sha256': route.sha(b'{}')}
        self.clock = 10000.0
        self.wall = 1791244800.0
        self.called = []
        self.safe = False
        self.result = 'Passed'
        self.phase_fail = None
        self.timeout = None
        self.denied = False
        self.bad_native = False
        self.case_elapsed = 0.1
        self.late_replay = False
        self.late_source_after = False
        self.late_final_serialization = False
        self.late_final_move = False
        self.capacity_pressure = False
        self.native_finished = 0.0
        self.replay_finished = False
        self.late_once = False
        self.fixture = (ROOT / route.FIXTURE_PATH).read_bytes()
        self.old = {name: self.fixture for name in route.NAMES}
        self.summary = {}
        self.parsed_context = None
        self.env = {'RUNNER_TEMP': str(self.temp), 'GITHUB_SHA': 'a' * 40, 'GITHUB_WORKFLOW_SHA': 'a' * 40, 'GITHUB_RUN_ID': '123456', 'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': '100mango/Celluloid', 'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF': 'refs/heads/' + LIFECYCLE['branch'], 'CELLULOID_VALIDATION_SCOPE': LIFECYCLE['scope']}
        self.env['GITHUB_WORKFLOW_REF']='100mango/Celluloid/'+route.WORKFLOW+'@refs/heads/'+LIFECYCLE['branch']
        (self.temp / 'mac-job-clock.json').write_bytes(route.encoded({'source_sha': 'a' * 40, 'execution_budget_seconds': 2460, 'started_monotonic': 9999.0, 'started_unix': self.wall - 1}))

    def fake_run(self, args, **kwargs):
        self.assertEqual(args[:4], route.merged_command([]))
        logical = args[4:]
        label = kwargs['log_name'][len('lifecycle-observation-'):-4]
        self.called.append(label)
        if label == self.timeout:
            (self.temp / kwargs['log_name']).write_text('partial timeout fixture')
            raise TimeoutError('injected timeout')
        self.clock += self.case_elapsed if label == 'single-photos-case' else 0.1
        start = self.wall
        self.wall += 0.1
        code = 1 if label == self.phase_fail else 0
        out = 'fixture ' + label + '\n'
        if label == 'toolchain':
            out = 'Xcode 27.0\nBuild version 27A266a\n'
        if label == 'app-entitlements':
            out = plistlib.dumps({'com.apple.security.app-sandbox': True, 'com.apple.security.files.user-selected.read-write': True}).decode()
        if label == 'prepare':
            app = self.temp / 'celluloid-sandbox/Build/Products/Debug/CelluloidMac.app'
            extension = app / 'Contents/PlugIns/CelluloidMacPhotosExtension.appex'
            (extension / 'Contents').mkdir(parents=True)
            info = plistlib.loads((self.root / 'Platforms/macOSExtension/Info.plist').read_bytes())
            info['CFBundleIdentifier'] = 'Mango.Celluloid.CelluloidPhotoExtension'
            (extension / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))
            context = {'source_sha': 'a' * 40, 'app_id': 'Mango.Celluloid', 'extension_id': 'Mango.Celluloid.CelluloidPhotoExtension', 'app_path': str(app), 'extension_path': str(extension), 'runner_environment': dict(self.env), 'seed': {'mode': 'require-empty-library'}, 'validation_route': LIFECYCLE, 'host_clock_profile': host_clock_profile(LIFECYCLE)}
            (self.temp / 'mac-host-context.json').write_bytes(route.encoded(context))
        if label == 'budget-host':
            (self.temp / 'mac-host-budget.json').write_bytes(b'{"fixture_only":true}')
        if label == 'single-photos-case':
            self.native_finished = self.clock
            code = 0 if self.result == 'Passed' else 65
            state = 'passed' if code == 0 else 'failed'
            terminal = 'SUCCEEDED' if code == 0 else 'FAILED'
            out = f"Test Case '{route.RAW_CASE}' started.\nTest Case '{route.RAW_CASE}' {state} (1.0 seconds).\n{self.temp}/MacPhotosHost.xcresult\n** TEST EXECUTE {terminal} **\n"
            if self.bad_native:
                code = 64
                out = 'xcodebuild: error: CLI fixture rejection\n'
            self.summary = {'result': self.result, 'startTime': start + 0.01, 'finishTime': start + 0.09}
        if label == 'summary':
            out = json.dumps(self.summary)
        if label == 'product-after':
            (self.temp / 'mac-host-product-after.json').write_bytes(b'{"fixture_only":true}')
        if label == 'attachments':
            self.assertTrue(self.safe)
            folder = self.temp / 'lifecycle-observation-attachments'
            folder.mkdir()
            (folder / 'manifest.json').write_bytes(b'[]')
        return subprocess.CompletedProcess(args, code, out, '')

    def bound(self, context_bytes, log, summary):
        if self.denied:
            raise ValueError('Unadmitted Photos confirmation or access alert; no action taken')
        self.safe = True
        self.parsed_context = json.loads(context_bytes)
        return (self.parsed_context, self.records, {}, {}, {})

    def replay(self, *args):
        self.replay_finished = True
        if self.late_replay:
            self.clock = self.native_finished + 361.4
        return {'functional_lifecycle_qualified':True,'strict_saved_pixel_passed':self.result=='Passed','filter_lifecycle_accepted':self.result=='Passed'}

    def snapshot(self, *args):
        if self.replay_finished and self.late_source_after:
            self.clock = self.native_finished + 361.4
        return 'f' * 64

    def execute(self, alias=False, wrong_cwd=False):
        env = dict(self.env)
        if alias:
            env['RUNNER_TEMP'] = str(self.alias / 'runner')
        original = Path.cwd()
        os.chdir(self.root.parent if wrong_cwd else self.alias / 'repo' if alias else self.root)
        try:
            records = {'lifecycle.json': route.encoded({'images': {name: {'sha256': route.sha(raw), 'rgba_sha256': 'd' * 64, 'bytes':len(raw)} for name, raw in self.old.items()}, 'srgb_icc_reference': None}), 'outcome.json': b'{"fixture_only":true}'}
            self.records=records
            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.dict(os.environ, env))
                stack.enter_context(patch.object(route, 'ROOT', self.root.resolve()))
                self.admission = stack.enter_context(patch.object(route, 'admit_source', return_value=({}, self.before)))
                stack.enter_context(patch.object(route, 'source_snapshot', side_effect=self.snapshot))
                stack.enter_context(patch.object(route.time, 'monotonic', side_effect=lambda: self.clock))
                stack.enter_context(patch.object(route.time, 'time', side_effect=lambda: self.wall))
                stack.enter_context(patch.object(route, 'run', side_effect=self.fake_run))
                stack.enter_context(patch.object(route, 'admit_outcome', side_effect=self.bound))
                stack.enter_context(patch.object(route, 'parse', return_value=records))
                stack.enter_context(patch.object(route, 'attachment_candidates', return_value=self.old))
                stack.enter_context(patch.object(route, 'decode', return_value={'rgba_sha256': 'd' * 64}))
                stack.enter_context(patch.object(route, 'admit_images', side_effect=self.replay))
                real_capacity=route.attachment_capacity
                def capacity(files,lifecycle):
                    if self.capacity_pressure:
                        needed=sum(row['bytes'] for row in lifecycle['images'].values())+128000+4096+route.FINAL_RESERVE
                        return real_capacity({'pressure':{'bytes':route.CAP-needed+1}},lifecycle)
                    return real_capacity(files,lifecycle)
                stack.enter_context(patch.object(route,'attachment_capacity',side_effect=capacity))
                real_encoded = route.encoded

                def encoded(value):
                    raw = real_encoded(value)
                    if self.late_final_serialization and value.get('schema') == 'Celluloid.OwnedPhotosLifecycleRun.1' and (not self.late_once):
                        self.late_once = True
                        self.clock = self.native_finished + 361.4
                    return raw
                stack.enter_context(patch.object(route, 'encoded', side_effect=encoded))
                real_replace = Path.replace

                def replace(path, target):
                    result = real_replace(path, target)
                    if self.late_final_move and path.name == 'lifecycle-observation-final-run.pending.json' and (not self.late_once):
                        self.late_once = True
                        self.clock = self.native_finished + 361.4
                    return result
                stack.enter_context(patch.object(Path, 'replace', replace))
                self.git = stack.enter_context(patch.object(route, 'git', side_effect=lambda *a: ('a' * 40).encode() if a[0] == 'rev-parse' else b''))
                code = route.main()
        finally:
            os.chdir(original)
        evidence = self.temp / 'celluloid-photos-lifecycle-observation-evidence'
        report = json.loads((evidence / 'run.json').read_text())
        manifest = json.loads((evidence / 'manifest.json').read_text())
        self.assertLessEqual(sum((x.stat().st_size for x in evidence.iterdir())), 1000000)
        for name, row in manifest['files'].items():
            raw = (evidence / name).read_bytes()
            self.assertEqual(row, {'bytes': len(raw), 'sha256': route.sha(raw)})
        return (code, report)

    def test_one_case_success_full_packet_and_precise_stage_order(self):
        code, report = self.execute()
        self.assertEqual(code, 0)
        self.assertTrue(report['diagnostic_complete'])
        self.assertFalse(report['complete_host_e2e'])
        self.assertFalse(report['old_full_host_admission_granted'])
        self.assertEqual(self.called.count('single-photos-case'), 1)
        self.assertLess(self.called.index('summary'), self.called.index('product-after'))
        self.assertLess(self.called.index('product-after'), self.called.index('attachments'))
        self.assertTrue(report['functional_lifecycle_qualified'])
        self.assertNotIn('comparison',self.called);self.assertNotIn('compare-build',self.called)
        self.assertEqual(self.git.call_count, 2)

    def test_mac_ancestor_temp_alias_normalizes_paths_without_relaxing_root(self):
        code, report = self.execute(alias=True)
        self.assertEqual(code, 0)
        self.assertEqual(self.parsed_context['runner_environment']['RUNNER_TEMP'], str(self.temp.resolve()))
        event = next((x for x in report['events'] if x['stage'] == 'single-photos-case'))
        self.assertIn(str(self.temp.resolve() / 'MacPhotosHost.xcresult'), event['command'])

    def test_foreign_cwd_stops_before_source_admission_or_process(self):
        code, report = self.execute(wrong_cwd=True)
        self.assertEqual(code, 1)
        self.assertEqual(self.called, [])
        self.admission.assert_not_called()
        self.assertEqual(report['stage'], 'source-admission')

    def test_legacy_pixel_failure_can_retain_diagnostic_but_remains_failed(self):
        self.result = 'Failed'
        code, report = self.execute()
        self.assertEqual(code, 1)
        self.assertTrue(report['diagnostic_complete'])
        self.assertFalse(report['saved_gate_passed'])
        self.assertEqual(report['stage'], 'functional-complete-original-pixel-gate-failed')

    def test_cli64_no_case_never_runs_summary_export(self):
        self.bad_native = True
        code, report = self.execute()
        self.assertEqual(code, 1)
        self.assertEqual(self.called[-1], 'single-photos-case')
        self.assertEqual(report['stage'], 'native-completion')
        self.git.assert_not_called()

    def test_native_timeout_never_starts_any_followup_process(self):
        self.timeout = 'single-photos-case'
        code, report = self.execute()
        self.assertEqual(code, 1)
        self.assertEqual(self.called[-1], 'single-photos-case')
        self.assertTrue(report['cleanup_unconfirmed'])
        self.git.assert_not_called()

    def test_case_late_even_with_exit_zero_stops_before_summary(self):
        self.case_elapsed = 1021
        code, report = self.execute()
        self.assertEqual(code, 1)
        self.assertEqual(self.called[-1], 'single-photos-case')

    def test_denied_outcome_no_product_export_or_later_native(self):
        self.denied = True
        code, report = self.execute()
        self.assertEqual(code, 1)
        self.assertEqual(self.called[-1], 'summary')
        self.assertFalse(report['safe_outcome_admitted'])
        self.git.assert_not_called()

    def test_product_failure_never_exports(self):
        self.phase_fail = 'product-after'
        code, report = self.execute()
        self.assertEqual(code, 1)
        self.assertEqual(self.called[-1], 'product-after')
        self.git.assert_not_called()

    def test_build_failure_never_enters_host_case(self):
        self.phase_fail = 'ui-build'
        code, report = self.execute()
        self.assertEqual(code, 1)
        self.assertEqual(self.called[-1], 'ui-build')
        self.assertFalse(report['native_case_started'])
        self.git.assert_not_called()

    def test_in_process_replay_over_original_tail_is_incomplete_not_green(self):
        self.late_replay = True
        code, report = self.execute()
        self.assertEqual(code, 1)
        self.assertFalse(report['diagnostic_complete'])
        self.assertFalse(report['functional_lifecycle_qualified'])
        self.assertFalse(report['saved_gate_passed'])
        self.assertIn('after-complete-lifecycle-replay', report['error'])
        self.assertEqual(self.called[-1], 'attachments')
        self.git.assert_not_called()

    def test_source_after_over_original_tail_downgrades_before_git(self):
        self.late_source_after = True
        code, report = self.execute()
        self.assertEqual(code, 1)
        self.assertFalse(report['diagnostic_complete'])
        self.assertFalse(report['functional_lifecycle_qualified'])
        self.assertFalse(report['saved_gate_passed'])
        self.assertIn('after-source-after-hashes', report['source_after_error'])
        self.git.assert_not_called()

    def test_final_serialization_over_original_tail_publishes_only_incomplete(self):
        self.late_final_serialization = True
        code, report = self.execute()
        self.assertEqual(code, 1)
        self.assertFalse(report['diagnostic_complete'])
        self.assertFalse(report['functional_lifecycle_qualified'])
        self.assertFalse(report['saved_gate_passed'])
        self.assertIn('after-final-receipt-staging', report['publication_error'])
        self.assertEqual(self.git.call_count, 2)
        self.assertFalse((self.temp / 'lifecycle-observation-final-run.pending.json').exists())
        self.assertFalse((self.temp / 'lifecycle-observation-final-manifest.pending.json').exists())

    def test_final_run_move_over_tail_cannot_publish_a_success_manifest(self):
        self.late_final_move = True
        code, report = self.execute()
        self.assertEqual(code, 1)
        self.assertFalse(report['diagnostic_complete'])
        self.assertFalse(report['functional_lifecycle_qualified'])
        self.assertFalse(report['saved_gate_passed'])
        self.assertIn('before-success-publication', report['publication_error'])

    def test_insufficient_1mb_reserved_capacity_stops_before_export(self):
        self.capacity_pressure = True
        code, report = self.execute()
        self.assertEqual(code, 1)
        self.assertEqual(self.called[-1], 'product-after')
        self.assertEqual(report['stage'], 'unchanged-product')
        self.assertIn('1MB capacity', report['error'])
        self.git.assert_not_called()

    def test_original_clock_has_no_reset_when_time_is_insufficient(self):
        self.clock = 12200
        code, report = self.execute()
        self.assertEqual(code, 1)
        self.assertEqual(self.called, [])

if __name__=='__main__':unittest.main()
