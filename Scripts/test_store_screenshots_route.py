"""Portable capture-route admission, owned-failure fencing, and bootstrap clocks."""
import ast
import contextlib
import copy
import errno
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import original_ios_process_guard as guard
import uikit_full_shipping_gate as gate
import validation_route as routes
import store_display_assets as assets
from test_uikit_full_shipping_bootstrap import load_functions, SOURCE, DEVICE

HOST_COMMANDS = [['vm_stat'], ['memory_pressure', '-Q'], ['sysctl', 'vm.swapusage'],
                 ['df', '-h', '.'], ['ps', '-axo', 'pid=,ppid=,rss=,comm=']]
HOST_OMISSION = 'BOOTSTRAP_HOST_DIAGNOSTICS_NOT_COLLECTED '


def environment(root, row='large-phone'):
    route = routes.STORE_SCREENSHOTS
    ref = 'refs/heads/' + route['branch']
    return {'GITHUB_REF': ref, 'GITHUB_REPOSITORY': routes.REPOSITORY,
            'GITHUB_EVENT_NAME': 'push', 'CELLULOID_VALIDATION_SCOPE': route['scope'],
            'GITHUB_WORKFLOW_REF': routes.REPOSITORY + '/' + route['workflow_path'] + '@' + ref,
            'GITHUB_SHA': 'a' * 40, 'GITHUB_WORKFLOW_SHA': 'a' * 40,
            'GITHUB_RUN_ID': '1234567', 'GITHUB_RUN_ATTEMPT': '1',
            'CELLULOID_FULL_ROW': row, 'RUNNER_TEMP': str(root)}


def clock(context, monotonic=10_000, unix=100_000):
    return {'schema': gate.CLOCK_SCHEMA, **context, 'started_monotonic': monotonic,
            'started_unix': unix, 'execution_budget_seconds': gate.EXECUTION_SECONDS}


class StoreRouteTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.env = environment(self.root)
        scope = patch.dict(os.environ, self.env, clear=True)
        scope.start()
        self.addCleanup(scope.stop)
        self.context = guard.staged_context()

    def test_exact_route_is_separate_diagnostic_identity_without_environment_rewrite(self):
        before = dict(self.env)
        self.assertEqual(routes.current_route(self.env), routes.STORE_SCREENSHOTS)
        self.assertEqual(routes.validate_route(routes.STORE_SCREENSHOTS), routes.STORE_SCREENSHOTS)
        self.assertIs(routes.STORE_SCREENSHOTS['diagnostic_only'], True)
        self.assertEqual(self.env, before)
        for route in (routes.FULL, routes.ORIGINAL_IOS, routes.UIKIT_FULL):
            self.assertNotEqual(route, routes.STORE_SCREENSHOTS)

    def test_wrong_or_missing_actual_identity_cannot_admit_capture(self):
        changes = [('GITHUB_REF', 'refs/heads/' + routes.ORIGINAL_IOS['branch']),
                   ('GITHUB_REPOSITORY', 'unreviewed/Celluloid'),
                   ('GITHUB_EVENT_NAME', 'workflow_dispatch'),
                   ('CELLULOID_VALIDATION_SCOPE', routes.ORIGINAL_IOS['scope']),
                   ('GITHUB_WORKFLOW_REF', routes.REPOSITORY + '/' + routes.ORIGINAL_IOS['workflow_path'] + '@' + self.env['GITHUB_REF']),
                   ('GITHUB_WORKFLOW_SHA', 'b' * 40), ('GITHUB_SHA', True)]
        for key, value in changes:
            changed = dict(self.env, **{key: value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                routes.current_route(changed)
            with self.subTest(guard=key), self.assertRaises(guard.GuardRefusal):
                guard.staged_context(changed)
        for key in ('GITHUB_REF', 'GITHUB_REPOSITORY', 'GITHUB_EVENT_NAME',
                    'CELLULOID_VALIDATION_SCOPE', 'GITHUB_WORKFLOW_REF', 'GITHUB_SHA',
                    'GITHUB_WORKFLOW_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'):
            changed = dict(self.env)
            changed.pop(key)
            with self.subTest(missing=key), self.assertRaises(guard.GuardRefusal):
                guard.staged_context(changed)

    def test_only_two_capture_accounting_rows_have_explicit_route_context(self):
        for row in ('large-phone', 'large-ipad'):
            context = guard.staged_context(environment(self.root, row))
            self.assertEqual(set(context), guard.CONTEXT_KEYS | {'validation_route'})
            self.assertEqual(context['validation_route'], routes.STORE_SCREENSHOTS)
            self.assertEqual(guard.context_route(context), routes.STORE_SCREENSHOTS)
        for row in ('compact-phone', 'small-ipad', 'iPhone 17 Pro', '', None):
            with self.subTest(row=row), self.assertRaises(guard.GuardRefusal):
                guard.staged_context(environment(self.root, row))
        for route in (routes.ORIGINAL_IOS, dict(routes.STORE_SCREENSHOTS, diagnostic_only=1)):
            with self.subTest(route=route), self.assertRaises(guard.GuardRefusal):
                guard.validate_context(dict(self.context, validation_route=route))

    def failure(self):
        owner = guard.OwnedCommand('xcodebuild', 'capture-ui', 900)
        owner.started(MagicMock(pid=12345))
        owner.failed(subprocess.TimeoutExpired('xcodebuild', 900), timed_out=True)
        return owner

    def test_retained_receipts_bind_capture_offline_and_reject_original_relabel(self):
        self.failure()
        with patch.dict(os.environ, {}, clear=True):
            for read in (guard.read_failure, guard.read_inflight):
                receipt = read(self.root, self.context)
                self.assertEqual(receipt['validation_route'], routes.STORE_SCREENSHOTS)
                original_context = {key: self.context[key] for key in guard.CONTEXT_KEYS}
                with self.assertRaises(guard.GuardRefusal):
                    read(self.root, original_context)
            with self.assertRaises(guard.GuardRefusal):
                guard.require_clear(self.root, self.context)
        for name, read in ((guard.MARKER_NAME, guard.read_failure), (guard.INFLIGHT_NAME, guard.read_inflight)):
            path = self.root / name
            receipt = json.loads(path.read_text())
            receipt['validation_route'] = dict(routes.ORIGINAL_IOS)
            path.write_text(json.dumps(receipt))
            with self.assertRaises(guard.GuardRefusal):
                read(self.root, self.context)

    def test_retained_failure_blocks_native_successors_and_leaves_source_retention(self):
        self.failure()
        value = clock(self.context)
        before = (self.root / guard.MARKER_NAME).read_bytes()
        with patch('native_process.subprocess.Popen') as dispatch:
            import native_process
            with self.assertRaises(guard.GuardRefusal):
                native_process.run(['xcrun', 'simctl', 'shutdown', 'owned'])
            for phase in ('ui', 'bootstrap', 'summary', 'shutdown', 'delete', 'product-readbacks'):
                with self.subTest(phase=phase), self.assertRaises(guard.GuardRefusal):
                    gate.admit_phase(value, self.context, phase, 10_001, 100_001)
            dispatch.assert_not_called()
        for phase in ('source-before', 'source-after', 'collection', 'upload'):
            self.assertGreater(gate.admit_phase(value, self.context, phase, 10_001, 100_001), 0)
        self.assertEqual((self.root / guard.MARKER_NAME).read_bytes(), before)

    def test_inflight_context_keeps_actual_capture_route_on_inner_failure(self):
        owner = guard.OwnedCommand('python3', 'owned helper', 60)
        owner.started(MagicMock(pid=os.getpgrp()))
        self.assertEqual(guard.ensure_inflight_dispatch(), self.context)
        guard.record_inflight_failure(TimeoutError('inner timeout'), timed_out=True)
        self.assertEqual(guard.read_failure(self.root, self.context)['validation_route'], routes.STORE_SCREENSHOTS)
        with self.assertRaises(guard.GuardRefusal):
            guard.ensure_inflight_dispatch()

    def test_capture_adapter_preserves_original_timeout_and_stops_after_denied_signal(self):
        import native_process
        process = MagicMock(pid=12345, returncode=None)
        original = subprocess.TimeoutExpired('xcodebuild', 900, output=b'partial capture output')
        process.communicate.side_effect = original
        process.poll.return_value = None
        with patch('native_process.subprocess.Popen', return_value=process) as launch, patch('native_process.os.killpg', side_effect=PermissionError(errno.EPERM, 'denied')) as signal, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(TimeoutError) as caught:
                native_process.run(['xcodebuild'], timeout=900, echo=False, log_name='capture.log')
            self.assertIs(caught.exception.__cause__, original)
            launch.assert_called_once()
            signal.assert_called_once()
            process.communicate.assert_called_once()
        receipt = guard.read_failure(self.root, self.context)
        self.assertEqual(receipt['validation_route'], routes.STORE_SCREENSHOTS)
        self.assertEqual(receipt['original_error']['type'], 'TimeoutExpired')
        self.assertEqual(receipt['cleanup']['status'], 'signal_denied')
        self.assertEqual(receipt['cleanup']['signals'][0]['error']['errno'], errno.EPERM)
        self.assertIn('partial capture output', (self.root / 'capture.log').read_text())
        with patch('native_process.subprocess.Popen') as launch, self.assertRaises(guard.GuardRefusal):
            native_process.run(['xcrun', 'simctl', 'delete', 'owned'])
        launch.assert_not_called()

    def test_same_first_step_start_and_global_3360_2700_660_budgets_for_both_rows(self):
        self.assertEqual((gate.OUTER_JOB_SECONDS, gate.EXECUTION_SECONDS, gate.WORK_SECONDS, gate.TAIL_SECONDS),
                         (3600, 3360, 2700, 660))
        for row in ('large-phone', 'large-ipad'):
            with patch.dict(os.environ, CELLULOID_FULL_ROW=row):
                context = guard.staged_context()
                value = clock(context)
                self.assertEqual(gate.admit_phase(value, context, 'ui', 12_600, 102_600), 100)
                gate.check_completion(value, context, 'ui', 12_700, 102_700)
                with self.assertRaises(ValueError):
                    gate.check_completion(value, context, 'ui', 12_700.1, 102_700.1)
                with self.assertRaises(ValueError):
                    gate.admit_phase(value, context, 'ui', 12_700, 102_700)
                status = gate.clock_status(value, context, 12_700, 102_700)
                self.assertEqual(status['remaining_seconds'], 660)
                self.assertEqual(status['outside_execution_clock_seconds'], 240)
                for phase, (_, deadline) in gate.TAIL_PHASES.items():
                    gate.check_completion(value, context, phase, 10_000 + deadline, 100_000 + deadline)
                    with self.assertRaises(ValueError):
                        gate.check_completion(value, context, phase, 10_000 + deadline + .1, 100_000 + deadline + .1)

    def test_capture_uses_ui_after_appearance_and_never_original_full_inventory(self):
        for row in ('large-phone', 'large-ipad'):
            with patch.dict(os.environ, CELLULOID_FULL_ROW=row):
                context = guard.staged_context()
                value = clock(context)
                self.assertEqual(gate.admit_phase(value, context, 'appearance', 10_000, 100_000), 60)
                self.assertEqual(gate.admit_phase(value, context, 'ui', 10_000, 100_000), 900)
                for phase in ('dark', 'units', 'preflight', 'photos-integration', 'release-build', 'preservation'):
                    with self.subTest(row=row, phase=phase), self.assertRaises(ValueError):
                        gate.admit_phase(value, context, phase, 10_000, 100_000)
                    with self.assertRaises(ValueError):
                        gate.check_completion(value, context, phase, 10_000, 100_000)
                with self.assertRaisesRegex(ValueError, 'cannot qualify original UIKit'):
                    gate.verify_manifest({}, self.root, context, value)

    def test_clock_cannot_launder_route_or_run_or_row_for_dispatch(self):
        value = clock(self.context)
        for key, replacement in [('run_id', '1234568'), ('row', 'large-ipad'), ('source_sha', 'b' * 40)]:
            context = dict(self.context, **{key: replacement})
            with self.subTest(key=key), self.assertRaises(ValueError):
                gate.admit_phase(clock(context), context, 'ui', 10_000, 100_000)
        original = {key: self.context[key] for key in guard.CONTEXT_KEYS}
        with self.assertRaises(ValueError):
            gate.admit_phase(clock(original), original, 'ui', 10_000, 100_000)
        for key, replacement in [('execution_budget_seconds', 3600), ('started_monotonic', float('nan')),
                                 ('validation_route', routes.ORIGINAL_IOS),
                                 ('validation_route', dict(routes.STORE_SCREENSHOTS, diagnostic_only=1))]:
            changed = dict(value, **{key: replacement})
            with self.subTest(key=key), self.assertRaises(ValueError):
                gate.clock_status(changed, self.context, 10_000, 100_000)
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError):
            gate.admit_phase(value, self.context, 'ui', 10_000, 100_000)

    def test_bootstrap_executes_unchanged_two_methods_and_two_exact_owned_imports(self):
        """Run actual host/clock checks and the real sequence; fake native work."""
        legacy = self.root / 'legacy'
        legacy.mkdir()
        assets.prepare(legacy_root=legacy)
        names = [a['staged_filename'] for a in assets.ASSETS]
        value = clock(self.context, time.monotonic(), time.time())
        (self.root / 'full-shipping-clock.json').write_text(json.dumps(value))
        functions = load_functions(self.root)
        body = ast.Module(body=[node for node in ast.parse(SOURCE.read_text()).body
                                if not isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef))], type_ignores=[])
        calls, imported = [], []

        def native(command, **kwargs):
            calls.append((command, kwargs))
            owner = guard.OwnedCommand(command[0], kwargs['log_name'], kwargs['timeout'])
            owner.started(MagicMock(pid=12345))
            self.assertEqual(guard.read_inflight(self.root, self.context)['validation_route'], routes.STORE_SCREENSHOTS)
            output = ''
            if command[:3] == ('xcrun', 'simctl', 'addmedia'):
                path = Path(command[-1])
                imported.append({'filename': path.name, 'sha256': functions['hashlib'].sha256(path.read_bytes()).hexdigest(),
                                 'bytes': path.stat().st_size, 'width': 1254, 'height': 1254, 'identifier': 'owned-' + path.name})
            if command[0] == 'xcodebuild':
                output = 'PHOTOS_LIBRARY_READINESS ' + json.dumps({'synthetic': copy.deepcopy(imported),
                    'asset_count': len(imported), 'authorization': 3, 'library_mutation': False,
                    'hash_resources': any('testReconcileSyntheticPhotosAfterImport' in arg for arg in command)}) + '\n'
            owner.completed(0)
            return subprocess.CompletedProcess(command, 0, output, '')

        output = io.StringIO()
        with patch.object(sys, 'argv', [str(SOURCE), DEVICE, '--already-prepared']), patch('native_process.run', side_effect=native), patch('subprocess.run', side_effect=AssertionError('unowned dispatch')), contextlib.redirect_stdout(output):
            exec(compile(body, str(SOURCE), 'exec'), functions)
        self.assertEqual(len(calls), 5)
        self.assertFalse(any(command[0] in {cmd[0] for cmd in HOST_COMMANDS} for command, _ in calls))
        self.assertTrue(all(kwargs['capture_deadline'] == value['started_monotonic'] + gate.WORK_SECONDS for _, kwargs in calls))
        omissions = [json.loads(line[len(HOST_OMISSION):]) for line in output.getvalue().splitlines() if line.startswith(HOST_OMISSION)]
        self.assertEqual([item['label'] for item in omissions],
                         ['prepared-before-readiness', 'before-PhotoKit-readiness', 'before-import', 'after-import'])
        for item in omissions:
            self.assert_host_omission(item, item['label'])
        tests = [(command, kwargs) for command, kwargs in calls if command[0] == 'xcodebuild']
        self.assertEqual([[arg for arg in command if arg.startswith('-only-testing:')] for command, _ in tests],
                         [['-only-testing:CelluloidTests/EditorRegressionTests/testPhotosLibraryBootstrapReadiness'],
                          ['-only-testing:CelluloidTests/EditorRegressionTests/testReconcileSyntheticPhotosAfterImport']])
        self.assertEqual([kwargs['timeout'] for _, kwargs in tests], [360, 360])
        imports = [(command, kwargs) for command, kwargs in calls if command[:3] == ('xcrun', 'simctl', 'addmedia')]
        self.assertEqual(len(imports), 2)
        self.assertEqual([kwargs['timeout'] for _, kwargs in imports], [480, 180])
        self.assertEqual({item['filename'] for item in imported}, set(names))
        self.assertIn(assets.MARKER, output.getvalue())
        self.assertNotIn('BOOTSTRAP_EXACT_SIX_ASSETS_VERIFIED', output.getvalue())
        receipt = json.loads((self.root / 'store-display-photos.json').read_text())
        self.assertEqual(receipt['verified_asset_count'], 2)
        self.assertEqual(receipt['initial']['asset_count'], 0)
        self.assertEqual(receipt['final']['asset_count'], 2)
        self.assertIsNone(guard.read_inflight(self.root, self.context))
        self.assertEqual(json.loads((self.root / 'full-shipping-clock.json').read_text()), value)

    def test_original_and_uikit_bootstrap_keep_six_imports_and_original_marker(self):
        fixtures = self.root / 'original-fixtures'
        fixtures.mkdir()
        names = ['celluloid-fixture.png', 'celluloid-fixture-2.png'] + ['celluloid-composition-' + str(i) + '.png' for i in range(4)]
        for name in names:
            (fixtures / name).write_bytes(name.encode())
        body = ast.Module(body=[node for node in ast.parse(SOURCE.read_text()).body
                               if not isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef))], type_ignores=[])
        for route in (routes.ORIGINAL_IOS, routes.UIKIT_FULL):
            env = dict(self.env, GITHUB_REF='refs/heads/' + route['branch'],
                       CELLULOID_VALIDATION_SCOPE=route['scope'],
                       GITHUB_WORKFLOW_REF=routes.REPOSITORY + '/' + route['workflow_path'] + '@refs/heads/' + route['branch'])
            context = {key: self.context[key] for key in guard.CONTEXT_KEYS}
            value = clock(context, time.monotonic(), time.time())
            (self.root / 'full-shipping-clock.json').write_text(json.dumps(value))
            functions = load_functions(self.root)
            functions['pathlib'] = SimpleNamespace(Path=lambda raw: fixtures / str(raw)[5:] if str(raw).startswith('/tmp/celluloid-') else fixtures if str(raw) == '/tmp' else Path(raw))
            # Host behavior is independently exercised for all three old routes below.
            functions['host'] = lambda label: None
            calls, imported = [], []
            def native(command, **kwargs):
                calls.append((command, kwargs))
                output = ''
                if command[:3] == ('xcrun', 'simctl', 'addmedia'):
                    path = Path(command[-1])
                    imported.append({'filename': path.name, 'sha256': functions['hashlib'].sha256(path.read_bytes()).hexdigest()})
                if command[0] == 'xcodebuild':
                    output = 'PHOTOS_LIBRARY_READINESS ' + json.dumps({'synthetic': copy.deepcopy(imported)}) + '\n'
                return subprocess.CompletedProcess(command, 0, output, '')
            output = io.StringIO()
            with self.subTest(route=route['scope']), patch.dict(os.environ, env, clear=True), patch.object(sys, 'argv', [str(SOURCE), DEVICE, '--already-prepared']), patch('native_process.run', side_effect=native), patch('store_display_assets.staged_assets', side_effect=AssertionError('display preparation on legacy route')), patch('subprocess.run', side_effect=AssertionError('unowned dispatch')), contextlib.redirect_stdout(output):
                exec(compile(body, str(SOURCE), 'exec'), functions)
            imports = [(command, kwargs) for command, kwargs in calls if command[:3] == ('xcrun', 'simctl', 'addmedia')]
            self.assertEqual(len(calls), 9)
            self.assertEqual([kwargs['timeout'] for _, kwargs in imports], [480, 180, 180, 180, 180, 180])
            self.assertTrue(all('capture_deadline' not in kwargs for _, kwargs in calls))
            self.assertEqual({item['filename'] for item in imported}, set(names))
            self.assertIn('BOOTSTRAP_EXACT_SIX_ASSETS_VERIFIED', output.getvalue())
            self.assertNotIn(assets.MARKER, output.getvalue())
            self.assertEqual((fixtures / 'celluloid-bootstrap-assets-verified').read_text(), 'verified\n')

    def host_functions(self):
        value = clock(self.context, time.monotonic(), time.time())
        (self.root / 'full-shipping-clock.json').write_text(json.dumps(value))
        return load_functions(self.root)

    def assert_host_omission(self, receipt, label):
        self.assertEqual(set(receipt), {*self.context, 'schema', 'label', 'diagnostics_not_collected', 'omitted_commands', 'reason'})
        self.assertEqual(receipt['schema'], 'Celluloid.StoreCaptureHostDiagnostics.1')
        self.assertEqual({key: receipt[key] for key in self.context}, self.context)
        self.assertEqual(receipt['label'], label)
        self.assertIs(receipt['diagnostics_not_collected'], True)
        self.assertEqual(receipt['omitted_commands'], HOST_COMMANDS)
        self.assertTrue(receipt['reason'])

    def test_capture_host_emits_exact_omission_without_host_or_native_dispatch(self):
        functions = self.host_functions()
        output = io.StringIO()
        with patch('native_process.run') as native, patch('subprocess.run') as direct, patch('subprocess.Popen') as spawn, contextlib.redirect_stdout(output):
            functions['host']('before-import')
        native.assert_not_called()
        direct.assert_not_called()
        spawn.assert_not_called()
        lines = output.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith(HOST_OMISSION))
        self.assert_host_omission(json.loads(lines[0][len(HOST_OMISSION):]), 'before-import')
        self.assertIsNone(guard.read_failure(self.root, self.context))
        self.assertIsNone(guard.read_inflight(self.root, self.context))

    def test_capture_host_spoofed_or_missing_identity_cannot_emit_omission_or_dispatch(self):
        functions = self.host_functions()
        changes = [('GITHUB_REF', 'refs/heads/' + routes.FULL['branch']),
                   ('GITHUB_WORKFLOW_REF', 'unreviewed'), ('GITHUB_WORKFLOW_SHA', 'b' * 40),
                   ('GITHUB_EVENT_NAME', 'workflow_dispatch'), ('CELLULOID_FULL_ROW', 'compact-phone')]
        environments = [dict(self.env, **{key: value}) for key, value in changes]
        for key in ('CELLULOID_FULL_ROW', 'GITHUB_REF', 'GITHUB_REPOSITORY', 'GITHUB_RUN_ID',
                    'CELLULOID_VALIDATION_SCOPE', 'GITHUB_RUN_ATTEMPT'):
            changed = dict(self.env)
            changed.pop(key)
            environments.append(changed)
        for index, env in enumerate(environments):
            output = io.StringIO()
            with self.subTest(index=index), patch.dict(os.environ, env, clear=True), patch('native_process.run') as native, patch('subprocess.run') as direct, contextlib.redirect_stdout(output):
                with self.assertRaises((guard.GuardRefusal, ValueError, KeyError)):
                    functions['host']('before-import')
                native.assert_not_called()
                direct.assert_not_called()
                self.assertNotIn(HOST_OMISSION, output.getvalue())

    def test_capture_host_requires_actual_clock_binding_and_work_completion(self):
        functions = self.host_functions()
        original = json.loads((self.root / 'full-shipping-clock.json').read_text())
        for key, value in (('source_sha', 'b' * 40), ('run_id', '7654321'), ('run_attempt', '2'), ('row', 'large-ipad'),
                           ('validation_route', routes.ORIGINAL_IOS)):
            (self.root / 'full-shipping-clock.json').write_text(json.dumps(dict(original, **{key: value})))
            output = io.StringIO()
            with self.subTest(key=key), patch('native_process.run') as native, patch('subprocess.run') as direct, contextlib.redirect_stdout(output):
                with self.assertRaises((guard.GuardRefusal, ValueError)):
                    functions['host']('before-import')
                native.assert_not_called()
                direct.assert_not_called()
                self.assertNotIn(HOST_OMISSION, output.getvalue())
        value = clock(self.context)
        (self.root / 'full-shipping-clock.json').write_text(json.dumps(value))
        output = io.StringIO()
        with patch('time.monotonic', return_value=12_701), patch('time.time', return_value=102_701), patch('native_process.run') as native, patch('subprocess.run') as direct, contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(ValueError, 'Late UIKit phase completion'):
                functions['host']('after-import')
            native.assert_not_called()
            direct.assert_not_called()
            self.assertNotIn(HOST_OMISSION, output.getvalue())

    def test_capture_host_rechecks_staged_context_against_row_clock_context(self):
        functions = self.host_functions()
        original_clock = functions['row_clock']
        def other_row():
            value, context, status = original_clock()
            return value, dict(context, row='large-ipad'), status
        functions['row_clock'] = other_row
        output = io.StringIO()
        with patch('native_process.run') as native, patch('subprocess.run') as direct, contextlib.redirect_stdout(output):
            with self.assertRaises(ValueError):
                functions['host']('before-import')
        native.assert_not_called()
        direct.assert_not_called()
        self.assertNotIn(HOST_OMISSION, output.getvalue())

    def test_existing_unknown_or_timed_out_ps_receipt_still_blocks_host_and_required_commands(self):
        functions = self.host_functions()
        owner = guard.OwnedCommand('ps', 'ps', 15)
        owner.started(MagicMock(pid=12345))
        for state in ('unknown', 'timeout'):
            if state == 'timeout':
                owner.failed(subprocess.TimeoutExpired(HOST_COMMANDS[-1], 15), timed_out=True)
            receipts = {name: (self.root / name).read_bytes() for name in (guard.MARKER_NAME, guard.INFLIGHT_NAME)
                        if (self.root / name).exists()}
            output = io.StringIO()
            with self.subTest(state=state), patch('native_process.run') as native, patch('subprocess.run') as direct, contextlib.redirect_stdout(output):
                with self.assertRaises(guard.GuardRefusal):
                    functions['host']('before-import')
                with self.assertRaises(guard.GuardRefusal):
                    functions['run']('readiness-before-import', 360, 'xcodebuild')
                with self.assertRaises(guard.GuardRefusal):
                    functions['run']('import-0', 480, 'xcrun', 'simctl', 'addmedia', DEVICE, 'fixture.png')
                native.assert_not_called()
                direct.assert_not_called()
                self.assertNotIn(HOST_OMISSION, output.getvalue())
            self.assertEqual({name: (self.root / name).read_bytes() for name in receipts}, receipts)

    def test_original_uikit_and_canonical_host_keep_all_five_fifteen_second_probes(self):
        for route in (routes.ORIGINAL_IOS, routes.UIKIT_FULL, routes.FULL):
            env = dict(self.env, GITHUB_REF='refs/heads/' + route['branch'],
                       CELLULOID_VALIDATION_SCOPE=route['scope'],
                       GITHUB_WORKFLOW_REF=routes.REPOSITORY + '/' + route['workflow_path'] + '@refs/heads/' + route['branch'])
            context = {key: self.context[key] for key in guard.CONTEXT_KEYS}
            value = clock(context, time.monotonic(), time.time())
            (self.root / 'full-shipping-clock.json').write_text(json.dumps(value))
            functions = load_functions(self.root, full_row=route != routes.FULL)
            output = io.StringIO()
            result = subprocess.CompletedProcess([], 0, '', '')
            with self.subTest(route=route['scope']), patch.dict(os.environ, env, clear=True), patch('native_process.run', return_value=result) as native, patch('subprocess.run', return_value=result) as direct, contextlib.redirect_stdout(output):
                functions['host']('compatibility')
            called, unused = (native, direct) if route == routes.ORIGINAL_IOS else (direct, native)
            self.assertEqual([call.args[0] for call in called.call_args_list], HOST_COMMANDS)
            self.assertTrue(all(call.kwargs['timeout'] == 15 and 'capture_deadline' not in call.kwargs for call in called.call_args_list))
            unused.assert_not_called()
            self.assertNotIn(HOST_OMISSION, output.getvalue())
            self.assertIn('BOOTSTRAP_HOST_BEGIN compatibility', output.getvalue())
            self.assertIn('BOOTSTRAP_HOST_END compatibility', output.getvalue())

    def test_bootstrap_admission_checks_capture_work_window_before_inner_owned_command(self):
        value = clock(self.context)
        (self.root / 'full-shipping-clock.json').write_text(json.dumps(value))
        functions = load_functions(self.root)
        with patch.object(gate.time, 'monotonic', return_value=12_206), patch.object(gate.time, 'time', return_value=102_206), patch('native_process.run') as dispatch:
            with self.assertRaises(TimeoutError):
                functions['run']('import-0', 480, 'xcrun', 'simctl', 'addmedia', DEVICE, 'fixture.png')
            dispatch.assert_not_called()
        with patch.dict(os.environ, GITHUB_WORKFLOW_SHA='b' * 40), patch('native_process.run') as dispatch:
            with self.assertRaises(guard.GuardRefusal):
                functions['run']('import-0', 480, 'xcrun', 'simctl', 'addmedia', DEVICE, 'fixture.png')
            dispatch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
