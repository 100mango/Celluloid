#!/usr/bin/env python3
"""Offline-only early-Cancel admission/order/cleanup tests. Never invokes Xcode."""
from contextlib import ExitStack
from pathlib import Path
import copy
import hashlib
import json
import os
import tempfile
import unittest
from unittest.mock import patch, Mock
import run_early_cancel_acceptance as gate
import early_cancel_receipt as receipt_cli

DEVICE = 'AB000000-0000-0000-0000-000000000001'
SOURCE, TREE, HEAD, CLOSED = 'a' * 40, 'b' * 40, 'c' * 40, 'd' * 40
ENV = {'GITHUB_REPOSITORY': '100mango/Celluloid', 'GITHUB_EVENT_NAME': 'push',
    'GITHUB_REF': 'refs/heads/' + gate.BRANCH, 'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_RUN_ID': '12345',
    'GITHUB_WORKFLOW_REF': '100mango/Celluloid/' + gate.WORKFLOW + '@refs/heads/' + gate.BRANCH,
    'DEVELOPER_DIR': '/Applications/Xcode_27.app/Contents/Developer',
    'GITHUB_SHA': HEAD, 'GITHUB_WORKFLOW_SHA': HEAD,
    'CELLULOID_EARLY_CANCEL_SOURCE': SOURCE, 'CELLULOID_EARLY_CANCEL_SOURCE_TREE': TREE,
    'RUNNER_ENVIRONMENT': 'github-hosted'}


class EarlyCancelTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.root = root; self.out = root / 'build/early-cancel-acceptance'; self.derived = root / '.build/early-cancel-ios'
        for key, value in [('ROOT', root), ('OUT', self.out), ('DERIVED', self.derived)]:
            self.stack.enter_context(patch.object(gate, key, value))
        self.stack.enter_context(patch.dict(os.environ, ENV, clear=True))
        self.stack.enter_context(patch.object(gate.sys, 'platform', 'darwin'))
        self.stack.enter_context(patch.object(gate.os, 'chdir'))
        self.stack.enter_context(patch.object(gate.signal, 'signal'))

    def facts(self):
        workflow = '    if: ${{ false }}\n      CELLULOID_EARLY_CANCEL_SOURCE: CLOSED\n      CELLULOID_EARLY_CANCEL_SOURCE_TREE: CLOSED\n'
        closed = workflow.replace('SOURCE: CLOSED', 'SOURCE: ' + SOURCE).replace('SOURCE_TREE: CLOSED', 'SOURCE_TREE: ' + TREE)
        return {'head': HEAD, 'tree': 'e' * 40, 'source': SOURCE, 'source_tree': TREE, 'closed': CLOSED,
            'activation_parents': [CLOSED], 'closed_parents': [SOURCE], 'source_parents': [gate.BASE],
            'base_tree': gate.BASE_TREE, 'source_paths': sorted(gate.SOURCE_PATHS),
            'closed_paths': [gate.WORKFLOW], 'activation_paths': [gate.WORKFLOW],
            'source_workflow': workflow, 'closed_workflow': closed,
            'workflow': closed.replace('    if: ${{ false }}', '    if: ${{ true }}'), 'dirty': '',
            'source_ui': 'old\n    /// OFFLINE CANDIDATE ONLY.fixture\n    func testBeautifyOpensSystemPickerAndCancelsRepeatedly() {}\n',
            'base_ui': 'old\n    func testBeautifyOpensSystemPickerAndCancelsRepeatedly() {}\n'}

    def valid_lineage(self, facts):
        import hashlib
        with patch.object(gate, 'INSERTION_SHA256', hashlib.sha256(b'    /// OFFLINE CANDIDATE ONLY.fixture\n').hexdigest()):
            gate.validate_lineage(ENV, facts)

    def snapshot(self): return {'source_sha': HEAD, 'source_tree': 'e' * 40, 'tracked_files': [['source', 'hash']]}
    def after(self):
        return {'devices': {gate.RUNTIME: [{'udid': DEVICE, 'name': 'Celluloid iOS27 ' + gate.MODEL, 'state': 'Shutdown', 'isAvailable': True}]}}

    def test_context_accepts_exact_once_route(self):
        self.assertEqual(gate.BRANCH, 'cell-ios-early-cancel-startup-20261015')
        gate.validate_context(ENV)

    def test_closed_and_rerun_and_wrong_environment_rejected(self):
        for key, value in [('CELLULOID_EARLY_CANCEL_SOURCE', 'CLOSED'), ('CELLULOID_EARLY_CANCEL_SOURCE_TREE', 'CLOSED'),
            ('GITHUB_RUN_ATTEMPT', '2'), ('GITHUB_REF', 'refs/heads/main'),
            ('GITHUB_REF', 'refs/heads/cell-ios-early-cancel-20261015'), ('GITHUB_REPOSITORY', 'foreign/repo'),
            ('GITHUB_EVENT_NAME', 'workflow_dispatch'), ('GITHUB_WORKFLOW_SHA', 'f' * 40),
            ('GITHUB_WORKFLOW_REF', 'wrong'), ('DEVELOPER_DIR', '/Applications/Xcode.app'), ('GITHUB_RUN_ID', '0')]:
            with self.subTest(key=key), self.assertRaises(ValueError): gate.validate_context({**ENV, key: value})

    def test_every_nonempty_continuation_probe_or_override_rejected(self):
        for key in ['CELLULOID_PREVIEW_CONTINUATION', 'CELLULOID_SYNTHETIC_PROBE', 'CELLULOID_BYPASS',
            'CELLULOID_FULL_ROW', 'TEST_RUNNER_CELLULOID_SYNTHETIC_PROBE', 'CELLULOID_UNKNOWN']:
            with self.subTest(key=key), self.assertRaises(ValueError): gate.validate_context({**ENV, key: '1'})
        gate.validate_context({**ENV, 'CELLULOID_PREVIEW_CONTINUATION': ''})

    def test_lineage_accepts_exact_source_closed_activation(self): self.valid_lineage(self.facts())

    def test_lineage_rejects_mutations_and_merges(self):
        for key, value in [('source', 'f' * 40), ('source_tree', 'f' * 40), ('head', 'f' * 40),
            ('activation_parents', [CLOSED, SOURCE]), ('closed_parents', [SOURCE, gate.BASE]),
            ('source_parents', [gate.BASE, HEAD]),
            ('source_parents', ['9a25054916700f2e69b12a801b7bbfb81f72d5d6']),
            ('base_tree', 'f' * 40), ('source_paths', []),
            ('closed_paths', [gate.WORKFLOW, 'product.swift']), ('activation_paths', []),
            ('source_workflow', 'already open'), ('dirty', ' M product'), ('base_ui', 'changed')]:
            with self.subTest(key=key), self.assertRaises(ValueError): self.valid_lineage({**self.facts(), key: value})
        for key in ['source_workflow', 'closed_workflow', 'workflow', 'source_ui']:
            facts = self.facts(); facts[key] += 'unauthorized change\n'
            with self.subTest(key=key), self.assertRaises(ValueError): self.valid_lineage(facts)

    def test_fresh_output_and_derived_required(self):
        self.out.mkdir(parents=True)
        with self.assertRaises(ValueError): gate.EarlyCancel()
        self.out.rmdir(); self.derived.mkdir(parents=True)
        with self.assertRaises(ValueError): gate.EarlyCancel()

    def test_original_preview_mode_is_not_used(self):
        with patch.object(gate.time, 'monotonic', return_value=100.0): runner = gate.EarlyCancel()
        self.assertFalse(runner.preview_only); self.assertEqual(runner.work_seconds, 2100)
        self.assertEqual(runner.deadline - runner.started, 2100)

    def test_owner_requires_new_shutdown_exact_device(self):
        for before, after in [(self.after(), self.after()), ({'devices': {}}, {'devices': {}})]:
            with self.assertRaises(ValueError): gate.full.owner_receipt(before, after, DEVICE, ENV, HEAD, 1, 2101)
        for key, value in [('state', 'Booted'), ('name', 'foreign'), ('isAvailable', False)]:
            after = self.after(); after['devices'][gate.RUNTIME][0][key] = value
            with self.assertRaises(ValueError): gate.full.owner_receipt({'devices': {}}, after, DEVICE, ENV, HEAD, 1, 2101)

    def run_order(self, ui_code=0, ui_raises=None, create=None):
        runner = gate.EarlyCancel(); calls = []
        responses = {'toolchain': 'Xcode 27.0', 'devices-before': '{"devices": {}}',
            'create-owned-device': create if create is not None else DEVICE + ' ' + gate.MODEL,
            'devices-after-create': json.dumps(self.after())}
        def command(name, argv, seconds, **options):
            calls.append((name, argv, seconds, options))
            if name == 'early-cancel-ui' and ui_raises: raise ui_raises
            return (ui_code if name == 'early-cancel-ui' else 0, responses.get(name, ''))
        def evidence(result, log): calls.append(('evidence', [], None, {})); runner.receipt_passed = True
        runner.command = command; runner.collect_evidence = evidence
        with patch.object(gate, 'source_snapshot', return_value=self.snapshot()), patch.object(gate, 'build_binding', return_value={}), patch.object(gate, 'check_build'), patch.object(gate, 'runner_isolation', return_value={'worker_id': DEVICE}):
            error = None
            try: runner.run()
            except BaseException as failure: error = failure
        return runner, calls, error

    def test_cold_native_command_order_and_only_one_test(self):
        runner, calls, error = self.run_order(); self.assertIsNone(error)
        self.assertEqual([row[0] for row in calls], ['toolchain', 'devices-before', 'create-owned-device',
            'devices-after-create', 'build', 'boot', 'bootstatus', 'early-cancel-ui', 'evidence'])
        ui = next(row for row in calls if row[0] == 'early-cancel-ui')
        argv = ui[1]
        self.assertEqual([x for x in argv if x.startswith('-only-testing:')], ['-only-testing:' + gate.SELECTOR])
        self.assertEqual(argv[-1], 'test-without-building'); self.assertEqual(ui[2], 480)
        self.assertIn('CODE_SIGNING_ALLOWED=NO', argv); self.assertIn('CODE_SIGNING_REQUIRED=NO', argv)
        self.assertEqual(argv[argv.index('-parallel-testing-enabled') + 1], 'NO')
        for name, args, _, _ in calls:
            self.assertFalse(any('retry' in x or 'repetition' in x or 'photos' in x.lower() for x in args))
        self.assertTrue(runner.ui_dispatched)

    def test_assertion_failure_still_collects_evidence_without_retry(self):
        runner, calls, error = self.run_order(ui_code=65)
        self.assertIsInstance(error, ValueError)
        self.assertEqual([row[0] for row in calls].count('early-cancel-ui'), 1)
        self.assertEqual(calls[-1][0], 'evidence')

    def test_ambiguous_create_never_lists_boots_builds_or_cleans_unknown(self):
        runner, calls, error = self.run_order(create='ambiguous')
        self.assertIsInstance(error, ValueError); self.assertTrue(runner.uncertain); self.assertIsNone(runner.device)
        self.assertEqual(calls[-1][0], 'create-owned-device')

    def test_whole_phase_must_fit_deadline(self):
        runner = gate.EarlyCancel(); runner.deadline = 100
        with patch.object(gate.time, 'monotonic', return_value=90), patch.object(gate.subprocess, 'call') as invoked:
            with self.assertRaises(ValueError): runner.command('too-late', ['xcrun', 'simctl'], 10, simulator=True)
            invoked.assert_not_called()

    def test_uncertain_blocks_all_simulator_commands_and_cleanup(self):
        runner = gate.EarlyCancel(); runner.uncertain = True; runner.device = DEVICE
        with patch.object(gate.subprocess, 'call') as invoked:
            with self.assertRaises(ValueError): runner.command('no-more', ['xcrun', 'simctl'], 1, simulator=True)
            runner.cleanup(); invoked.assert_not_called()

    def test_signal_timeout_invalid_exit_and_late_success_are_uncertain(self):
        for code, log, elapsed in [(124, '', 1), (-9, '', 1), (130, '', 1), (None, '', 1), (True, '', 1),
            (0, 'BOUNDED_COMMAND_TIMEOUT', 1), (0, 'CLEANUP_UNCONFIRMED', 1),
            (0, 'test execution timed out', 1), (0, '', 11)]:
            with self.subTest(code=code, log=log): self.assertTrue(gate.native_uncertain(code, log, elapsed, 10))
        self.assertFalse(gate.native_uncertain(65, 'normal assertion failure', 1, 10))

    def test_exact_single_observed_uuid_required(self):
        log = 'PICKER_CANCEL_CYCLE_UI run=' + DEVICE + ' iteration=0 event=run-begin'
        self.assertEqual(gate.unique_run(log), DEVICE.lower())
        for bad in ['', log + '\n' + log, log + '\n' + log.replace(DEVICE, 'AB000000-0000-0000-0000-000000000002')]:
            with self.assertRaises(ValueError): gate.unique_run(bad)

    def evidence_fixture(self):
        runner = gate.EarlyCancel(); runner.device = DEVICE; runner.source_tree = TREE
        runner.binary = self.root / 'app'; runner.binary.write_bytes(b'SYNTHETIC UNIT executable bytes; not a real app')
        dylib = runner.binary.parent / gate.DEBUG_DYLIB_NAME
        dylib.write_bytes(b'SYNTHETIC UNIT main debug dylib bytes; not native evidence')
        runner.binding = {'app_binary_sha256': hashlib.sha256(runner.binary.read_bytes()).hexdigest(),
            'app_debug_dylib_sha256': hashlib.sha256(dylib.read_bytes()).hexdigest(), 'app_bundle_sha256': 'bundle'}
        result = self.out / 'early-cancel.xcresult'; result.mkdir()
        log = 'PICKER_CANCEL_CYCLE_UI run=' + DEVICE + ' iteration=0 event=run-begin'
        return runner, result, log

    def test_strict_identity_has_one_run_three_cancel_zero_selected_actual_ci(self):
        runner, result, log = self.evidence_fixture(); calls = []
        def command(name, argv, cap, **kw):
            calls.append((name, argv, cap))
            if name == 'early-cancel-native-receipt':
                gate.save(self.out / 'early-cancel-native-receipt.json', {'status': 'passed', 'identity_verified': True,
                    'requires_identity_wrapper': False, 'release_qualification': False})
                d = self.out / 'early-cancel-native-diagnostics'; d.mkdir(); (d / 'retained-manifest.json').write_text('{}')
                (self.out / 'official-test-summary.json').write_text('{}')
            return 0, ''
        runner.command = command
        with patch.object(gate, 'check_build'), patch.object(gate.native, 'bundle_digest', return_value='xcresult'):
            runner.collect_evidence(result, log)
        identity = json.loads((self.out / 'early-cancel-identity.json').read_text())
        self.assertEqual(identity['runs'], [{'run_id': DEVICE.lower(), 'expected_cancel_count': 3, 'expected_selected_count': 0}])
        self.assertEqual(identity['device_id'], DEVICE); self.assertEqual(identity['ci_run_id'], '12345')
        self.assertEqual(identity['ci_run_attempt'], '1'); self.assertEqual(identity['source_sha'], HEAD)
        self.assertEqual(identity['app_debug_dylib_sha256'], runner.binding['app_debug_dylib_sha256'])
        self.assertTrue(runner.receipt_passed)
        self.assertEqual(len(calls), 1); self.assertIn('24A434', calls[0][1]); self.assertIn(gate.MODEL, calls[0][1])

    def test_missing_uuid_or_missing_receipt_retains_unbound_diagnostics(self):
        runner, result, log = self.evidence_fixture(); calls = []
        runner.command = lambda name, argv, cap, **kw: (calls.append((name, argv)) or (0, ''))
        with patch.object(gate, 'check_build'), patch.object(gate.native, 'bundle_digest', return_value='xcresult'):
            runner.collect_evidence(result, '')
        self.assertFalse(runner.receipt_passed)
        self.assertEqual([x[0] for x in calls], ['early-cancel-unbound-diagnostics'])
        self.assertNotIn('simctl', ' '.join(calls[0][1]))
        self.assertEqual(json.loads((self.out / 'early-cancel-native-receipt.json').read_text())['status'], 'invalid_evidence')

    def test_source_after_rechecks_all_bytes_and_build_binding(self):
        runner = gate.EarlyCancel(); runner.snapshot = self.snapshot(); runner.binding = {}; runner.binary = self.root / 'bin'
        with patch.object(gate, 'source_snapshot', return_value=runner.snapshot), patch.object(gate, 'check_build') as check:
            runner.verify_after(); check.assert_called_once()
        with patch.object(gate, 'source_snapshot', return_value={**runner.snapshot, 'tracked_files': []}):
            with self.assertRaises(ValueError): runner.verify_after()

    def test_failed_receipt_never_reports_full_or_release_pass(self):
        runner = gate.EarlyCancel()
        with patch.object(gate, 'EarlyCancel', return_value=runner), patch.object(runner, 'run'), \
            patch.object(runner, 'verify_after'), patch.object(runner, 'cleanup'):
            self.assertEqual(gate.main(), 1)
        receipt = json.loads((self.out / 'acceptance.json').read_text())
        self.assertFalse(receipt['current_slice_accepted']); self.assertFalse(receipt['release_qualification'])
        self.assertEqual(receipt['historical_full_38681904126_status'], 'failed')
        self.assertEqual(receipt['validation_scope'], 'early_cancel_supplementary')
        self.assertEqual(receipt['project_execution_ordinal'], 4); self.assertEqual(receipt['automatic_retries'], 0)
        self.assertEqual(receipt['historical_early_cancel_38695192063_status'], 'failed')
        self.assertEqual(receipt['historical_original_attempts_consumed'], 2)
        self.assertEqual(receipt['historical_additional_attempts_consumed'], 1)
        self.assertEqual(receipt['current_retest_attempt'], 1); self.assertEqual(receipt['current_retest_limit'], 1)
        self.assertEqual(receipt['historical_extra_38748681679_status'], 'failed')
        self.assertEqual(receipt['authorization_basis'], 'standing_free_development_test')
        self.assertEqual(receipt['authorized_extra_cost_cny'], 0)
        self.assertEqual(receipt['work_budget_seconds'], 2100)
        self.assertEqual(receipt['maximum_attempt_seconds'], 2700)
        self.assertEqual(receipt['reserved_nonwork_seconds'], 600)

    def test_supplementary_success_still_preserves_failed_full_and_release_false(self):
        runner = gate.EarlyCancel(); runner.receipt_passed = True; runner.cleanup_verified = True
        with patch.object(gate, 'EarlyCancel', return_value=runner), patch.object(runner, 'run'), \
            patch.object(runner, 'verify_after'), patch.object(runner, 'cleanup'):
            self.assertEqual(gate.main(), 0)
        receipt = json.loads((self.out / 'acceptance.json').read_text())
        self.assertTrue(receipt['current_slice_accepted']); self.assertFalse(receipt['all_required_phases_accepted'])
        self.assertFalse(receipt['release_qualification']); self.assertEqual(receipt['historical_full_38681904126_status'], 'failed')
        self.assertEqual(receipt['project_execution_ordinal'], 4); self.assertEqual(receipt['automatic_retries'], 0)
        self.assertEqual(receipt['historical_early_cancel_38695192063_status'], 'failed')
        self.assertEqual(receipt['historical_original_attempts_consumed'], 2)
        self.assertEqual(receipt['historical_additional_attempts_consumed'], 1)
        self.assertEqual(receipt['current_retest_attempt'], 1); self.assertEqual(receipt['current_retest_limit'], 1)
        self.assertEqual(receipt['historical_extra_38748681679_status'], 'failed')
        self.assertEqual(receipt['authorization_basis'], 'standing_free_development_test')
        self.assertEqual(receipt['authorized_extra_cost_cny'], 0)
        self.assertEqual(receipt['work_budget_seconds'], 2100)
        self.assertEqual(receipt['maximum_attempt_seconds'], 2700)
        self.assertEqual(receipt['reserved_nonwork_seconds'], 600)

    def test_interrupt_latches_before_cleanup(self):
        runner = gate.EarlyCancel(); runner.device = DEVICE
        with patch.object(gate, 'EarlyCancel', return_value=runner), patch.object(runner, 'run', side_effect=KeyboardInterrupt('stopped')), \
            patch.object(runner, 'verify_after'), patch.object(gate.subprocess, 'call') as invoked:
            self.assertEqual(gate.main(), 1)
            invoked.assert_not_called()
        self.assertTrue(runner.uncertain)

    def process(self, outcomes):
        process = Mock(pid=24680); process.wait.side_effect = outcomes; process.poll.return_value = None
        return process

    def test_direct_child_owns_new_session_and_has_finite_wait(self):
        runner = gate.EarlyCancel(); process = self.process([0])
        with patch.object(gate.subprocess, 'Popen', return_value=process) as launch:
            code, _ = runner.command('owned-fixture', ['native-fixture'], 20)
        self.assertEqual(code, 0); self.assertTrue(launch.call_args.kwargs['start_new_session'])
        self.assertEqual(launch.call_args.args[0], ['native-fixture'])
        self.assertGreater(process.wait.call_args.kwargs['timeout'], 0)
        self.assertLessEqual(process.wait.call_args.kwargs['timeout'], 10)
        owner = json.loads((self.out / 'owned-process-owned-fixture.json').read_text())
        self.assertEqual((owner['pid'], owner['pgid']), (24680, 24680))
        self.assertFalse(owner['group_exit_confirmed'])

    def test_timeout_signals_only_owned_group_and_every_wait_is_bounded(self):
        runner = gate.EarlyCancel(); runner.device = DEVICE
        timeout = gate.subprocess.TimeoutExpired('fixture', 10)
        process = self.process([timeout, timeout, 0])
        def signal_group(pid, sig):
            self.assertTrue(runner.uncertain)
            self.assertTrue((self.out / 'native-uncertainty.json').is_file())
        with patch.object(gate.subprocess, 'Popen', return_value=process) as launch, patch.object(gate.os, 'killpg', side_effect=signal_group) as kill:
            code, _ = runner.command('timeout-fixture', ['native-fixture'], 20, simulator=True, allow_failure=True)
            self.assertEqual(code, 124); self.assertTrue(runner.uncertain)
            runner.cleanup(); self.assertEqual(launch.call_count, 1)
        self.assertEqual([call.args for call in kill.call_args_list], [(24680, gate.signal.SIGTERM), (24680, gate.signal.SIGKILL)])
        self.assertTrue(all(0 < call.kwargs['timeout'] <= 10 for call in process.wait.call_args_list))
        self.assertFalse(runner.events[-1]['group_exit_confirmed'])

    def test_denied_owned_signal_never_switches_signal_or_cleans_simulator(self):
        runner = gate.EarlyCancel(); runner.device = DEVICE
        process = self.process([gate.subprocess.TimeoutExpired('fixture', 10)])
        with patch.object(gate.subprocess, 'Popen', return_value=process), patch.object(gate.os, 'killpg', side_effect=PermissionError('denied')) as kill:
            runner.command('denied-fixture', ['native-fixture'], 20, simulator=True, allow_failure=True)
            runner.cleanup()
        self.assertEqual(kill.call_count, 1); self.assertEqual(process.wait.call_count, 1)
        self.assertTrue(runner.uncertain)

    def test_popen_failure_latches_uncertainty_without_guessing_pgid(self):
        runner = gate.EarlyCancel(); runner.device = DEVICE
        with patch.object(gate.subprocess, 'Popen', side_effect=OSError('spawn failed')), patch.object(gate.os, 'killpg') as kill:
            with self.assertRaises(OSError): runner.command('spawn-fixture', ['native-fixture'], 20, simulator=True)
            runner.cleanup(); kill.assert_not_called()
        self.assertTrue(runner.uncertain)

    def test_parent_interruption_uses_bounded_owned_cleanup_once(self):
        runner = gate.EarlyCancel(); process = self.process([KeyboardInterrupt('stop'), 0])
        with patch.object(gate.subprocess, 'Popen', return_value=process), patch.object(gate.os, 'killpg') as kill:
            with self.assertRaises(KeyboardInterrupt): runner.command('interrupt-fixture', ['native-fixture'], 20, simulator=True)
        self.assertTrue(runner.uncertain); self.assertEqual(kill.call_count, 1)
        self.assertTrue(all('timeout' in call.kwargs for call in process.wait.call_args_list))

    def test_unknown_or_signal_exit_latches_before_next_native_dispatch(self):
        for code in [-9, None, True]:
            with self.subTest(code=code):
                # A separate fixture label prevents any reuse of a log.
                if not hasattr(self, '_runner'): self._runner = gate.EarlyCancel()
                runner = self._runner; process = self.process([code])
                with patch.object(gate.subprocess, 'Popen', return_value=process):
                    try: runner.command('bad-exit-' + str(code), ['fixture'], 20, allow_failure=True)
                    except ValueError: pass
                self.assertTrue(runner.uncertain)

    def test_uncertain_allows_only_file_diagnostics(self):
        runner = gate.EarlyCancel(); runner.uncertain = True; process = self.process([0])
        with patch.object(gate.subprocess, 'Popen', return_value=process):
            self.assertEqual(runner.command('file-export', ['xcresulttool-fixture'], 20)[0], 0)
        self.assertTrue(runner.uncertain)

    def test_no_owned_cleanup_dispatch_after_absolute_deadline(self):
        process = self.process([0])
        with patch.object(gate.time, 'monotonic', return_value=100), patch.object(gate.os, 'killpg') as kill:
            self.assertEqual(gate.stop_owned(process, 99), []); kill.assert_not_called()
        process.wait.assert_not_called()

    def test_cleanup_keeps_exit_codes_and_verifies_actual_absence(self):
        runner = gate.EarlyCancel(); runner.device = DEVICE; calls = []
        def owned(name, command, seconds, deadline):
            calls.append((name, command)); return 0, '{"devices": {}}', 0.1
        runner.owned_command = owned; runner.cleanup()
        self.assertEqual([x[0] for x in calls], ['cleanup-shutdown', 'cleanup-delete', 'cleanup-verify-absent'])
        self.assertTrue(runner.cleanup_verified); self.assertIsNone(runner.device)
        self.assertEqual([r['exit_code'] for r in runner.cleanup_events], [0, 0, 0])

    def test_cleanup_failure_stops_and_retains_owned_udid(self):
        runner = gate.EarlyCancel(); runner.device = DEVICE
        with patch.object(runner, 'owned_command', return_value=(7, 'failed', 0.1)) as owned:
            runner.cleanup(); self.assertEqual(owned.call_count, 1)
        self.assertTrue(runner.uncertain); self.assertEqual(runner.device, DEVICE)
        self.assertEqual(runner.cleanup_events[0]['exit_code'], 7)

    def test_ui_exception_still_attempts_evidence_once(self):
        runner, calls, error = self.run_order(ui_raises=TimeoutError('native timeout'))
        self.assertIsInstance(error, TimeoutError)
        self.assertEqual([row[0] for row in calls].count('early-cancel-ui'), 1)
        self.assertEqual(calls[-1][0], 'evidence')

    def test_nested_alarm_never_extends_existing_timer(self):
        setters = []
        with patch.object(gate.signal, 'getitimer', return_value=(2.0, 0.0)), \
            patch.object(gate.signal, 'setitimer', side_effect=lambda *args: setters.append(args)), \
            patch.object(gate.time, 'monotonic', side_effect=[100.0, 101.0]):
            with gate.local_bound(10, 'nested'): pass
        self.assertEqual(setters[0][1], 2.0)
        self.assertEqual(setters[-1][1], 1.0)


    def test_owned_receipt_timeout_preserves_teardown_and_retained_timeout(self):
        runner = gate.EarlyCancel(); process = self.process([0]); original_save = gate.save
        def save(path, value):
            if path.name.startswith('owned-process-') and 'cleanup_actions' not in value: raise TimeoutError('slow ownership receipt')
            return original_save(path, value)
        with patch.object(gate, 'save', side_effect=save), patch.object(gate.subprocess, 'Popen', return_value=process), \
            patch.object(gate.os, 'killpg') as kill:
            code, _ = runner.command('slow-owner', ['fixture'], 20, simulator=True, allow_failure=True)
        self.assertEqual(code, 124); self.assertTrue(runner.uncertain)
        self.assertEqual(kill.call_args.args, (24680, gate.signal.SIGTERM))
        self.assertEqual(process.wait.call_count, 1)  # Only bounded cleanup; native wait never starts.
        self.assertLessEqual(process.wait.call_args.kwargs['timeout'], 5)
        self.assertTrue(any(row.get('exit_code') == 124 for row in runner.failures))

    def test_dispatch_and_owned_receipt_use_native_scope_before_cleanup(self):
        from contextlib import contextmanager
        runner = gate.EarlyCancel(); process = self.process([gate.subprocess.TimeoutExpired('fixture', 10), 0])
        active = []; observed = []
        @contextmanager
        def bound(seconds, label):
            active.append(label); observed.append((seconds, label))
            try: yield
            finally: active.pop()
        def create(*args, **kwargs):
            self.assertEqual(active[-1], 'scoped-native'); return process
        def kill(pid, sig):
            self.assertIn('scoped', active); self.assertNotIn('scoped-native', active)
        with patch.object(gate, 'local_bound', side_effect=bound), patch.object(gate.subprocess, 'Popen', side_effect=create), \
            patch.object(gate.os, 'killpg', side_effect=kill):
            runner.command('scoped', ['fixture'], 20, simulator=True, allow_failure=True)
        native_cap = next(seconds for seconds, label in observed if label == 'scoped-native')
        phase_cap = next(seconds for seconds, label in observed if label == 'scoped')
        self.assertLessEqual(native_cap, 10); self.assertGreater(phase_cap - native_cap, 9.9)

    def unbound_command(self, calls, export_error=None, diagnostics_error=None):
        """Execute only the embedded file collector; all official tools mocked."""
        def export(bundle, output=None, deadline=None):
            calls.append(('summary', deadline))
            if export_error: raise export_error
            output.write_text(' { "result": "Failed" }\n')
            return {'result': 'Failed'}
        def diagnostics(bundle, destination, run_tool=None):
            calls.append(('diagnostics', destination))
            if diagnostics_error: raise diagnostics_error
            destination.mkdir(); (destination / 'official-fixture.log').write_text('SYNTHETIC UNIT diagnostics')
            return {'method': 'SYNTHETIC UNIT official exporter'}
        def command(name, argv, cap, **options):
            self.assertEqual(name, 'early-cancel-unbound-diagnostics'); self.assertEqual(cap, 60)
            self.assertNotIn('simctl', ' '.join(argv)); self.assertNotIn('xcodebuild', ' '.join(argv))
            with patch.object(gate.sys, 'argv', ['-c', *argv[3:]]), patch.object(gate.sys, 'path', list(gate.sys.path)), \
                patch.object(receipt_cli, 'export_summary', side_effect=export), \
                patch.object(gate.native, 'export_diagnostics', side_effect=diagnostics):
                try: exec(compile(argv[2], '<mocked-unbound-collector>', 'exec'), {})
                except SystemExit as stop: return stop.code, ''
            return 0, ''
        return command

    def test_missing_uuid_retains_real_copy_summary_and_unbound_diagnostics(self):
        runner, result, _ = self.evidence_fixture(); calls = []
        runner.command = self.unbound_command(calls)
        with patch.object(gate, 'check_build'): runner.collect_evidence(result, '')
        self.assertEqual([row[0] for row in calls], ['summary', 'diagnostics'])
        self.assertEqual((self.out / 'Celluloid-executable').read_bytes(), runner.binary.read_bytes())
        retained = json.loads((self.out / 'retained-app-binary.json').read_text())
        self.assertEqual(gate.native.sha256_file(self.out / retained['file']), retained['sha256'])
        self.assertTrue(retained['app_binary_retention_complete']); self.assertFalse(retained['app_bundle_retained'])
        self.assertEqual(retained['app_bundle_sha256_ci_attestation_only'], 'bundle')
        self.assertFalse(runner.receipt_passed)
        self.assertTrue((self.out / 'official-test-summary.json').is_file())

    def test_unbound_summary_failure_still_retains_diagnostics_and_export_error(self):
        runner, result, _ = self.evidence_fixture(); calls = []
        runner.command = self.unbound_command(calls, export_error=ValueError('summary unavailable'))
        with patch.object(gate, 'check_build'): runner.collect_evidence(result, '')
        self.assertEqual([row[0] for row in calls], ['summary', 'diagnostics'])
        self.assertIn('summary unavailable', (self.out / 'official-test-summary-export-error.json').read_text())
        self.assertTrue((self.out / 'early-cancel-unbound-diagnostics/official-fixture.log').is_file())
        self.assertFalse(runner.receipt_passed)

    def test_unbound_diagnostics_failure_keeps_summary(self):
        runner, result, _ = self.evidence_fixture(); calls = []
        runner.command = self.unbound_command(calls, diagnostics_error=ValueError('diagnostics unavailable'))
        with patch.object(gate, 'check_build'): runner.collect_evidence(result, '')
        self.assertTrue((self.out / 'official-test-summary.json').is_file())
        self.assertTrue((self.out / 'early-cancel-unbound-export-error.json').is_file())
        self.assertFalse(runner.receipt_passed)

    def test_unbound_exports_share_existing_45_second_cap(self):
        runner, result, _ = self.evidence_fixture(); captured = []
        def command(name, argv, cap, **options):
            self.assertEqual(cap, 60)
            def summary(bundle, output=None, deadline=None): captured.append(('summary', deadline))
            def diagnostics(bundle, destination, run_tool=None):
                run_tool(['mocked-file-export'], 999); return {}
            with patch.object(gate.sys, 'argv', ['-c', *argv[3:]]), patch.object(gate.sys, 'path', list(gate.sys.path)), \
                patch.object(receipt_cli, 'export_summary', side_effect=summary), \
                patch.object(gate.native, 'export_diagnostics', side_effect=diagnostics), \
                patch.object(gate.native, '_run_tool', side_effect=lambda command, deadline: captured.append(('diagnostics', deadline))), \
                patch.object(gate.time, 'monotonic', return_value=100):
                exec(compile(argv[2], '<mocked-unbound-collector>', 'exec'), {})
            return 0, ''
        runner.command = command
        with patch.object(gate, 'check_build'): runner.collect_evidence(result, '')
        self.assertEqual(captured, [('summary', 145), ('diagnostics', 145)])

    def test_existing_summary_error_is_preserved_without_export_retry(self):
        runner, result, _ = self.evidence_fixture(); calls = []
        error = self.out / 'official-test-summary-export-error.json'; error.write_text('original summary failure')
        runner.command = self.unbound_command(calls)
        with patch.object(gate, 'check_build'): runner.collect_evidence(result, '')
        self.assertEqual([row[0] for row in calls], ['diagnostics'])
        self.assertEqual(error.read_text(), 'original summary failure')

    def test_executable_copy_mismatch_never_passes_and_still_exports(self):
        runner, result, log = self.evidence_fixture(); calls = []; runner.binding['app_binary_sha256'] = '0' * 64
        runner.command = self.unbound_command(calls)
        with patch.object(gate, 'check_build'): runner.collect_evidence(result, log)
        self.assertFalse(runner.receipt_passed)
        record = json.loads((self.out / 'early-cancel-native-receipt.json').read_text())
        self.assertFalse(record['app_binary_retention_complete']); self.assertIn('hash mismatch', record['error'])
        self.assertFalse((self.out / 'retained-app-binary.json').exists())
        self.assertEqual([row[0] for row in calls], ['summary', 'diagnostics'])

    def test_executable_read_failure_is_explicit_and_still_exports(self):
        runner, result, log = self.evidence_fixture(); calls = []; original_open = Path.open
        runner.command = self.unbound_command(calls)
        def opened(path, *args, **kwargs):
            if path == runner.binary: raise OSError('executable read denied')
            return original_open(path, *args, **kwargs)
        with patch.object(gate, 'check_build'), patch.object(Path, 'open', new=opened): runner.collect_evidence(result, log)
        self.assertFalse(runner.receipt_passed)
        self.assertIn('executable read denied', (self.out / 'retained-app-binary-error.json').read_text())
        self.assertFalse((self.out / 'retained-app-binary.json').exists())
        self.assertEqual([row[0] for row in calls], ['summary', 'diagnostics'])

    def test_actual_collector_and_cli_retain_both_on_binder_failure(self):
        runner, result, log = self.evidence_fixture(); (result / 'Info.plist').write_text('UNIT fixture bundle')
        raw = ' { "UNIT_ONLY": true, "result": "Passed" }\n\n'; calls = []
        original_export = receipt_cli.export_summary
        def tool(command, deadline): return '--path' if 'help' in command else raw
        def command(name, argv, cap, **options):
            calls.append(name); self.assertEqual(name, 'early-cancel-native-receipt'); self.assertEqual(cap, 150)
            return receipt_cli.main(argv[2:]), ''
        runner.command = command
        with patch.object(gate, 'check_build'), \
            patch.object(receipt_cli, 'export_summary', side_effect=lambda bundle, **kw: original_export(bundle, run_tool=tool, **kw)), \
            patch.object(receipt_cli.base, 'export_diagnostics', return_value={'method': 'UNIT'}), \
            patch.object(receipt_cli.base, 'read_diagnostics', return_value={'Session-UNIT.log': 'SYNTHETIC UNIT log'}), \
            patch.object(receipt_cli, 'validate_early_logs', side_effect=receipt_cli.EvidenceError('original binder mismatch')):
            runner.collect_evidence(result, log)
        self.assertEqual(calls, ['early-cancel-native-receipt']); self.assertFalse(runner.receipt_passed)
        self.assertEqual((self.out / 'official-test-summary.json').read_bytes(), raw.encode())
        self.assertEqual((self.out / 'Celluloid-executable').read_bytes(), runner.binary.read_bytes())
        record = json.loads((self.out / 'early-cancel-native-receipt.json').read_text())
        self.assertEqual(record['error'], 'original binder mismatch'); self.assertTrue(record['diagnostics_retention_complete'])
        self.assertFalse(record['release_qualification'])

    def test_retained_executable_mutation_cannot_leave_runner_passed(self):
        runner, result, log = self.evidence_fixture()
        def command(name, argv, cap, **options):
            self.assertEqual(name, 'early-cancel-native-receipt')
            gate.save(self.out / 'early-cancel-native-receipt.json', {'status': 'passed', 'identity_verified': True,
                'requires_identity_wrapper': False, 'release_qualification': False})
            d = self.out / 'early-cancel-native-diagnostics'; d.mkdir(); (d / 'retained-manifest.json').write_text('{}')
            (self.out / 'official-test-summary.json').write_text('{}')
            (self.out / 'Celluloid-executable').write_bytes(b'changed during parsing')
            return 0, ''
        runner.command = command
        with patch.object(gate, 'check_build'), patch.object(gate.native, 'bundle_digest', return_value='xcresult'):
            runner.collect_evidence(result, log)
        self.assertFalse(runner.receipt_passed)
        self.assertFalse(json.loads((self.out / 'retained-app-binary-error.json').read_text())['app_binary_retention_complete'])
        self.assertIn('changed during parsing', runner.failures[-1]['error'])

    def test_executable_copy_failure_and_byte_cap_fail_closed(self):
        runner, result, log = self.evidence_fixture(); calls = []
        runner.command = self.unbound_command(calls)
        with patch.object(gate, 'check_build'), patch.object(gate.native, 'MAX_TOTAL_BYTES', 4):
            runner.collect_evidence(result, log)
        self.assertFalse(runner.receipt_passed)
        self.assertEqual((self.out / 'Celluloid-executable').stat().st_size, 0)
        error = json.loads((self.out / 'retained-app-binary-error.json').read_text())
        self.assertFalse(error['app_binary_retention_complete']); self.assertIn('byte bound', error['error'])
        self.assertTrue((self.out / 'official-test-summary.json').is_file())

    def test_executable_copy_never_overwrites_stale_or_symlink_target(self):
        runner, result, log = self.evidence_fixture(); calls = []
        foreign = self.root / 'foreign'; foreign.write_bytes(b'preserve')
        (self.out / 'Celluloid-executable').symlink_to(foreign)
        runner.command = self.unbound_command(calls)
        with patch.object(gate, 'check_build'): runner.collect_evidence(result, log)
        self.assertEqual(foreign.read_bytes(), b'preserve'); self.assertFalse(runner.receipt_passed)
        self.assertFalse(json.loads((self.out / 'retained-app-binary-error.json').read_text())['app_binary_retention_complete'])

    def test_binary_copy_and_rehash_stay_inside_existing_local_30_second_bound(self):
        from contextlib import contextmanager
        runner, result, _ = self.evidence_fixture(); active = []; bounds = []; original_hash = gate.native.sha256_file
        @contextmanager
        def bound(seconds, label):
            bounds.append((seconds, label)); active.append(label)
            try: yield
            finally: active.pop()
        def hashed(path):
            self.assertEqual(active[-1], 'native-identity'); return original_hash(path)
        runner.command = lambda *args, **kwargs: (0, '')
        with patch.object(gate, 'check_build'), patch.object(gate, 'local_bound', side_effect=bound), \
            patch.object(gate.native, 'sha256_file', side_effect=hashed): runner.collect_evidence(result, '')
        self.assertEqual(len(bounds), 1); self.assertEqual(bounds[0][1], 'native-identity')
        self.assertLessEqual(bounds[0][0], 30)

    def test_deadline_exhaustion_does_not_copy_or_dispatch_fallback(self):
        runner, result, log = self.evidence_fixture(); runner.deadline = 0
        with patch.object(gate.subprocess, 'Popen') as launch:
            runner.collect_evidence(result, log); launch.assert_not_called()
        self.assertFalse((self.out / 'Celluloid-executable').exists()); self.assertFalse(runner.receipt_passed)


    def test_ui_admission_requires_entire_orchestration_and_postprocessing_reserve(self):
        runner = gate.EarlyCancel(); runner.deadline = 1000
        with patch.object(gate.time, 'monotonic', return_value=191), patch.object(runner, 'owned_command') as owned:
            with self.assertRaisesRegex(ValueError, 'evidence reserve'):
                runner.command('early-cancel-ui', ['fixture'], gate.UI_PHASE_SECONDS, simulator=True)
            owned.assert_not_called()
        runner.last_owned = {}
        with patch.object(gate.time, 'monotonic', return_value=190), patch.object(runner, 'owned_command', return_value=(0, '', 1)) as owned:
            runner.command('early-cancel-ui', ['fixture'], gate.UI_PHASE_SECONDS, simulator=True)
            owned.assert_called_once()
        self.assertEqual(gate.POST_UI_RESERVE_SECONDS, 330)
        self.assertEqual(runner.work_seconds, 2100)

    def test_ui_budget_cannot_be_overridden_and_uncertainty_still_blocks(self):
        runner = gate.EarlyCancel()
        with patch.object(runner, 'owned_command') as owned:
            for seconds in [210, 479, 481]:
                with self.assertRaises(ValueError): runner.command('early-cancel-ui', ['fixture'], seconds, simulator=True)
            runner.uncertain = True
            with self.assertRaises(ValueError): runner.command('early-cancel-ui', ['fixture'], 480, simulator=True)
            owned.assert_not_called()

    def test_wait_timeout_precedes_native_alarm_and_cleanup_precedes_outer_alarm(self):
        from contextlib import contextmanager
        runner = gate.EarlyCancel(); process = self.process([])
        now = [100.0]; alarms = []; observed_waits = []
        @contextmanager
        def bound(seconds, label):
            deadline = now[0] + seconds; alarms.append((label, deadline))
            try: yield
            finally: alarms.pop()
        def wait(timeout):
            observed_waits.append((now[0], timeout, tuple(alarms)))
            now[0] += timeout
            raise gate.subprocess.TimeoutExpired('fixture', timeout)
        process.wait.side_effect = wait
        with patch.object(gate.time, 'monotonic', side_effect=lambda: now[0]), \
            patch.object(gate, 'local_bound', side_effect=bound), \
            patch.object(gate.subprocess, 'Popen', return_value=process), patch.object(gate.os, 'killpg') as kill:
            code, _, elapsed = runner.owned_command('deadline-fixture', ['fixture'], 480, 1000)
        self.assertEqual(code, 124); self.assertTrue(runner.uncertain)
        self.assertEqual(observed_waits[0][0] + observed_waits[0][1], 569)
        self.assertEqual(observed_waits[0][2][-1], ('deadline-fixture-native', 570))
        self.assertEqual([row[1] for row in observed_waits[1:]], [5, 4])
        self.assertLessEqual(elapsed, 478)
        self.assertEqual([x.args[1] for x in kill.call_args_list], [gate.signal.SIGTERM, gate.signal.SIGKILL])
        self.assertFalse(runner.last_owned['child_reaped']); self.assertIsNone(runner.last_owned['child_returncode'])
        self.assertFalse(runner.last_owned['group_exit_confirmed'])
        self.assertTrue(all(start + cap <= 578 for start, cap, _ in observed_waits))

    def test_native_alarm_timeout_latches_before_signal_and_keeps_two_second_final_reserve(self):
        from contextlib import contextmanager
        runner = gate.EarlyCancel(); runner.device = DEVICE
        process = self.process([]); now = [100.0]; active = []
        @contextmanager
        def bound(seconds, label):
            active.append(label)
            try: yield
            finally: active.pop()
        def wait(timeout):
            if len(process.wait.call_args_list) == 1:
                now[0] = 570.0
                raise TimeoutError('simulated native SIGALRM')
            now[0] += min(timeout, 0.25)
            process.poll.return_value = -15
            return -15
        def kill(pid, sig):
            self.assertTrue(runner.uncertain)
            self.assertNotIn('alarm-fixture-native', active)
            self.assertLess(now[0], 578)
        process.wait.side_effect = wait
        with patch.object(gate.time, 'monotonic', side_effect=lambda: now[0]), \
            patch.object(gate, 'local_bound', side_effect=bound), \
            patch.object(gate.subprocess, 'Popen', return_value=process), patch.object(gate.os, 'killpg', side_effect=kill):
            code, _, elapsed = runner.owned_command('alarm-fixture', ['fixture'], 480, 1000)
        self.assertEqual(code, 124); self.assertLess(elapsed, 478)
        self.assertTrue(runner.uncertain); self.assertEqual(runner.device, DEVICE)
        final = json.loads((self.out / 'owned-process-alarm-fixture.json').read_text())
        self.assertTrue(final['child_reaped']); self.assertEqual(final['child_returncode'], -15)
        self.assertFalse(final['group_exit_confirmed']); self.assertTrue(final['uncertain'])
        self.assertEqual(final['phase_deadline_monotonic'] - final['cleanup_deadline_monotonic'], 2)

    def test_debug_dylib_is_required_in_initial_build_binding_and_rechecks(self):
        app = self.root / 'Celluloid.app'; app.mkdir()
        binary = app / 'Celluloid'; binary.write_bytes(b'SYNTHETIC UNIT launcher')
        (app / 'Info.plist').write_text('UNIT')
        with self.assertRaises(ValueError): gate.build_binding(binary, SOURCE, TREE)
        dylib = app / gate.DEBUG_DYLIB_NAME; dylib.write_bytes(b'SYNTHETIC UNIT loaded payload')
        binding = gate.build_binding(binary, SOURCE, TREE)
        self.assertEqual(binding['app_debug_dylib_sha256'], hashlib.sha256(dylib.read_bytes()).hexdigest())
        self.assertEqual(binding['app_debug_dylib_path'], str(dylib.resolve()))
        gate.check_build(binding, binary, SOURCE, TREE)
        dylib.write_bytes(b'changed payload')
        with self.assertRaises(ValueError): gate.check_build(binding, binary, SOURCE, TREE)
        dylib.unlink(); foreign = self.root / 'foreign'; foreign.write_bytes(b'foreign')
        dylib.symlink_to(foreign)
        with self.assertRaises(ValueError): gate.build_binding(binary, SOURCE, TREE)

    def test_debug_dylib_bytes_and_independent_hash_retained_even_without_run_uuid(self):
        runner, result, _ = self.evidence_fixture(); calls = []
        runner.command = self.unbound_command(calls)
        with patch.object(gate, 'check_build'): runner.collect_evidence(result, '')
        retained = json.loads((self.out / 'retained-app-binary.json').read_text())
        dylib = retained['app_debug_dylib']
        self.assertEqual((self.out / dylib['file']).read_bytes(), (runner.binary.parent / gate.DEBUG_DYLIB_NAME).read_bytes())
        self.assertEqual(dylib['sha256'], runner.binding['app_debug_dylib_sha256'])
        self.assertEqual(gate.native.sha256_file(self.out / dylib['file']), dylib['sha256'])
        self.assertTrue(retained['app_debug_dylib_retention_complete'])
        self.assertFalse(retained['app_bundle_retained']); self.assertFalse(runner.receipt_passed)

    def test_retained_debug_dylib_mutation_cannot_leave_runner_passed(self):
        runner, result, log = self.evidence_fixture()
        def command(name, argv, cap, **options):
            self.assertEqual(name, 'early-cancel-native-receipt')
            gate.save(self.out / 'early-cancel-native-receipt.json', {'status': 'passed', 'identity_verified': True,
                'requires_identity_wrapper': False, 'release_qualification': False})
            d = self.out / 'early-cancel-native-diagnostics'; d.mkdir(); (d / 'retained-manifest.json').write_text('{}')
            (self.out / 'official-test-summary.json').write_text('{}')
            (self.out / gate.DEBUG_DYLIB_NAME).write_bytes(b'changed during parsing')
            return 0, ''
        runner.command = command
        with patch.object(gate, 'check_build'), patch.object(gate.native, 'bundle_digest', return_value='xcresult'):
            runner.collect_evidence(result, log)
        self.assertFalse(runner.receipt_passed)
        error = json.loads((self.out / 'retained-app-binary-error.json').read_text())
        self.assertTrue(error['app_binary_retention_complete']); self.assertFalse(error['app_debug_dylib_retention_complete'])
        self.assertIn('debug dylib changed during parsing', error['error'])

    def test_combined_launcher_and_dylib_retention_byte_cap_fail_closed(self):
        runner, result, log = self.evidence_fixture(); calls = []
        runner.command = self.unbound_command(calls)
        cap = runner.binary.stat().st_size + 1
        with patch.object(gate, 'check_build'), patch.object(gate.native, 'MAX_TOTAL_BYTES', cap):
            runner.collect_evidence(result, log)
        self.assertFalse(runner.receipt_passed)
        error = json.loads((self.out / 'retained-app-binary-error.json').read_text())
        self.assertFalse(error['app_debug_dylib_retention_complete']); self.assertIn('byte bound', error['error'])

    def test_missing_debug_dylib_copy_fails_and_still_attempts_official_exports(self):
        runner, result, log = self.evidence_fixture(); calls = []
        (runner.binary.parent / gate.DEBUG_DYLIB_NAME).unlink()
        runner.command = self.unbound_command(calls)
        with patch.object(gate, 'check_build'): runner.collect_evidence(result, log)
        self.assertFalse(runner.receipt_passed)
        error = json.loads((self.out / 'retained-app-binary-error.json').read_text())
        self.assertFalse(error['app_debug_dylib_retention_complete'])
        self.assertEqual([row[0] for row in calls], ['summary', 'diagnostics'])

    def test_dylib_copy_never_overwrites_stale_or_symlink_target(self):
        runner, result, log = self.evidence_fixture(); calls = []
        foreign = self.root / 'foreign'; foreign.write_bytes(b'preserve')
        (self.out / gate.DEBUG_DYLIB_NAME).symlink_to(foreign)
        runner.command = self.unbound_command(calls)
        with patch.object(gate, 'check_build'): runner.collect_evidence(result, log)
        self.assertEqual(foreign.read_bytes(), b'preserve'); self.assertFalse(runner.receipt_passed)
        self.assertFalse(json.loads((self.out / 'retained-app-binary-error.json').read_text())['app_debug_dylib_retention_complete'])


    def isolation_fixture(self, rows=None):
        worker = self.root / 'runner/bin/Runner.Worker'; worker.parent.mkdir(parents=True, exist_ok=True)
        worker.write_bytes(b'SYNTHETIC UNIT Runner.Worker, never executed')
        setup = worker.parent.parent / '.setup_info'
        detail = 'Hosted Compute Agent\nVersion: UNIT\nWorker ID: {' + DEVICE + '}\n'
        rows = rows if rows is not None else [
            {'Group': 'Runner Image Provisioner', 'Detail': detail},
            {'Group': '_internal_private', 'Detail': 'PRIVATE UNIT sentinel must never be copied'}]
        setup.write_text(json.dumps(rows))
        return worker, setup, rows

    def test_runner_isolation_accepts_unique_new_public_worker_without_copying_internal_data(self):
        worker, setup, rows = self.isolation_fixture()
        answers = [b'200 /usr/bin/python3\n', ('1 ' + str(worker) + '\n').encode(), b'0 /sbin/launchd\n']
        with patch.object(gate.os, 'getpid', return_value=300), patch.object(gate, 'read_ancestor_ps', side_effect=answers) as ps:
            identity = gate.runner_isolation(ENV, gate.time.monotonic() + 15)
        self.assertEqual(identity['worker_id'], DEVICE.lower()); self.assertEqual(identity['ancestor_count'], 3)
        self.assertNotIn('PRIVATE', json.dumps(identity)); self.assertNotIn('_internal_', json.dumps(identity))
        self.assertNotIn(str(worker), json.dumps(identity))
        for call, pid in zip(ps.call_args_list, [300, 200, 1]):
            self.assertEqual(call.args[0], pid)
            self.assertGreater(call.args[1], gate.time.monotonic())
        setup.write_text(json.dumps([{'group': 'Runner Image Provisioner', 'detail': rows[0]['Detail']}]))
        with patch.object(gate, 'read_ancestor_ps', side_effect=answers):
            self.assertEqual(gate.runner_isolation(ENV, gate.time.monotonic() + 15)['worker_id'], DEVICE.lower())

    def test_runner_isolation_rejects_old_missing_multiple_or_unhosted_identity(self):
        worker, setup, rows = self.isolation_fixture()
        detail = rows[0]['Detail']
        invalid = [[], [rows[1]], [rows[0], rows[0]],
            [{'Group': 'Runner Image Provisioner', 'Detail': detail.replace(DEVICE, gate.QUARANTINED_WORKER)}],
            [{'Group': 'Runner Image Provisioner', 'Detail': 'Hosted Compute Agent'}],
            [{'Group': 'Runner Image Provisioner', 'Detail': detail + 'Worker ID: {' + DEVICE + '}\n'}],
            [{'Group': 'Runner Image Provisioner', 'Detail': detail + 'Extra UUID: ' + SOURCE[:8] + '-0000-0000-0000-000000000003'}],
            [{'Group': 'Runner Image Provisioner', 'Detail': detail.replace('Hosted Compute Agent', 'other provider')}]]
        for value in invalid:
            setup.write_text(json.dumps(value))
            with self.subTest(value=value), patch.object(gate, 'read_ancestor_ps', return_value=('0 ' + str(worker)).encode()):
                with self.assertRaises(ValueError): gate.runner_isolation(ENV, gate.time.monotonic() + 15)
        with patch.object(gate, 'read_ancestor_ps') as ps:
            for environment in [{}, {**ENV, 'RUNNER_ENVIRONMENT': 'self-hosted'}]:
                with self.assertRaises(ValueError): gate.runner_isolation(environment, gate.time.monotonic() + 15)
            ps.assert_not_called()

    def test_runner_isolation_rejects_symlink_oversized_missing_or_ambiguous_setup_file(self):
        worker, setup, rows = self.isolation_fixture()
        for kind in ['symlink', 'oversized', 'missing', 'directory', 'duplicate-keys']:
            if setup.is_symlink() or setup.is_file(): setup.unlink()
            if setup.is_dir(): setup.rmdir()
            if kind == 'symlink':
                other = self.root / 'foreign-setup'; other.write_text(json.dumps(rows)); setup.symlink_to(other)
            elif kind == 'oversized': setup.write_bytes(b' ' * (gate.SETUP_INFO_MAX_BYTES + 1))
            elif kind == 'directory': setup.mkdir()
            elif kind == 'duplicate-keys': setup.write_text('[{"Group":"Runner Image Provisioner","group":"other","Detail":"UNIT"}]')
            with self.subTest(kind=kind), patch.object(gate, 'read_ancestor_ps', return_value=('0 ' + str(worker)).encode()):
                with self.assertRaises(ValueError): gate.runner_isolation(ENV, gate.time.monotonic() + 15)

    def test_runner_isolation_rejects_missing_ambiguous_unsupported_or_timed_out_ancestry(self):
        worker, setup, rows = self.isolation_fixture()
        variants = [b'0 /bin/bash', b'0 Runner.Worker', b'0 /unsupported/Runner.Worker', b'0 /bin/bash\n0 /bin/bash', b'bad',
            ValueError('lookup timed out'), OSError('unavailable')]
        for value in variants:
            with self.subTest(value=value), patch.object(gate, 'read_ancestor_ps', side_effect=value if isinstance(value, Exception) else None, return_value=value):
                with self.assertRaises((ValueError, OSError)): gate.runner_isolation(ENV, gate.time.monotonic() + 15)
        with patch.object(gate, 'read_ancestor_ps', side_effect=[('10 ' + str(worker)).encode(), ('0 ' + str(worker)).encode()]):
            with self.assertRaises(ValueError): gate.runner_isolation(ENV, gate.time.monotonic() + 15)
        with patch.object(gate.subprocess, 'Popen') as ps:
            with self.assertRaises(ValueError): gate.runner_isolation(ENV, gate.time.monotonic() - 1)
            ps.assert_not_called()

    def test_runner_isolation_failure_precedes_every_native_command(self):
        runner = gate.EarlyCancel()
        with patch.object(gate, 'source_snapshot', return_value=self.snapshot()), \
            patch.object(gate, 'runner_isolation', side_effect=ValueError('isolated worker unavailable')), \
            patch.object(runner, 'command') as native:
            with self.assertRaisesRegex(ValueError, 'isolated worker unavailable'): runner.run()
            native.assert_not_called()
        self.assertIsNone(runner.device); self.assertFalse(runner.ui_dispatched)
        self.assertFalse((self.out / 'runner-isolation.json').exists())


class AncestorPsDeadlineTests(unittest.TestCase):
    def test_explicit_ps_ownership_uses_regular_output_and_bounded_wait(self):
        captured = []; processes = []
        def launch(command, **options):
            captured.append((command, options))
            self.assertTrue(gate.stat.S_ISREG(gate.os.fstat(options['stdout'].fileno()).st_mode))
            options['stdout'].write(b'1 /runner/bin/Runner.Worker\n')
            process = Mock(); process.wait.return_value = 0; processes.append(process)
            return process
        with patch.object(gate.subprocess, 'Popen', side_effect=launch):
            result = gate.read_ancestor_ps(123, gate.time.monotonic() + 15)
        self.assertEqual(result, b'1 /runner/bin/Runner.Worker\n')
        self.assertEqual(captured[0][0], ['/bin/ps', '-p', '123', '-o', 'ppid=', '-o', 'comm='])
        self.assertEqual(captured[0][1]['stderr'], gate.subprocess.DEVNULL)
        self.assertEqual(captured[0][1]['stdin'], gate.subprocess.DEVNULL)
        process = processes[0]
        process.communicate.assert_not_called(); process.kill.assert_not_called()
        self.assertGreater(process.wait.call_args.kwargs['timeout'], 0)
        self.assertLessEqual(process.wait.call_args.kwargs['timeout'], 0.8)

    def test_reviewer_timeout_regression_has_no_context_exit_or_unbounded_wait(self):
        from contextlib import contextmanager
        real_exit = gate.subprocess.Popen.__exit__
        now = [100.0]; calls = []; alarms = []
        @contextmanager
        def bound(seconds, label):
            alarms.append((label, now[0] + seconds))
            try: yield
            finally: alarms.pop()
        class SyntheticPopen:
            stdout = stderr = stdin = None
            __exit__ = real_exit  # The original repro used this hidden unbounded reap.
            def __init__(self, command, **options): self.args = command
            def __enter__(self): calls.append(('context-enter',)); return self
            def communicate(self, input=None, timeout=None):
                calls.append(('communicate', timeout)); raise AssertionError('No pipe drain is allowed')
            def wait(self, timeout=None):
                calls.append(('wait', timeout, now[0], tuple(alarms)))
                if timeout is None:
                    now[0] += 0.15  # Original two hidden waits overran the 0.05 budget.
                    return 0
                now[0] += timeout
                raise gate.subprocess.TimeoutExpired(self.args, timeout)
            def poll(self): return None
            def kill(self): calls.append(('kill', now[0]))
        with patch.object(gate.subprocess, 'Popen', SyntheticPopen), \
            patch.object(gate.time, 'monotonic', side_effect=lambda: now[0]), \
            patch.object(gate, 'local_bound', side_effect=bound):
            with self.assertRaises(ValueError): gate.read_ancestor_ps(123, 100.05)
        waits = [call for call in calls if call[0] == 'wait']
        self.assertEqual(len(waits), 2)
        self.assertTrue(all(call[1] is not None and call[1] > 0 for call in waits))
        self.assertTrue(all(call[2] + call[1] <= 100.03 + 1e-10 for call in waits))
        self.assertLess(now[0], 100.05)
        self.assertFalse(any(call[0] in ['communicate', 'context-enter'] for call in calls))
        self.assertEqual(len([call for call in calls if call[0] == 'kill']), 1)

    def test_alarm_unknown_exit_and_oversized_output_reject_without_unbounded_cleanup(self):
        for kind in ['alarm-before-reap', 'alarm-at-phase-end', 'unknown', 'nonzero', 'oversized', 'spawn-failure']:
            with self.subTest(kind=kind):
                now = [100.0]; process = Mock(); waits = []
                process.poll.return_value = None
                def launch(command, **options):
                    if kind == 'spawn-failure': raise OSError('UNIT failure')
                    options['stdout'].write(b'x' * (8193 if kind == 'oversized' else 1))
                    return process
                def wait(timeout=None):
                    self.assertIsNotNone(timeout); self.assertGreater(timeout, 0); waits.append(timeout)
                    if len(waits) > 1: return -9
                    if kind.startswith('alarm'):
                        now[0] = 100.85 if kind == 'alarm-before-reap' else 101.0
                        raise TimeoutError('UNIT alarm')
                    return None if kind == 'unknown' else (1 if kind == 'nonzero' else 0)
                process.wait.side_effect = wait
                with patch.object(gate.subprocess, 'Popen', side_effect=launch), \
                    patch.object(gate.time, 'monotonic', side_effect=lambda: now[0]):
                    with self.assertRaises(ValueError): gate.read_ancestor_ps(123, 115)
                if kind in ['alarm-at-phase-end', 'spawn-failure']: process.kill.assert_not_called()
                process.communicate.assert_not_called()
                self.assertTrue(all(value <= 1 for value in waits))


class CollectorReceiptTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.bundle = self.root / 'UNIT.xcresult'; self.bundle.mkdir(); (self.bundle / 'Info.plist').write_text('UNIT fixture')
        self.binary = self.root / 'UNIT-executable'; self.binary.write_bytes(b'UNIT fixture executable')
        self.identity = self.root / 'identity.json'; self.output = self.root / 'receipt.json'; self.diagnostics = self.root / 'diagnostics'
        self.identity.write_text(json.dumps({'schema_version': 1, 'source_sha': SOURCE, 'source_tree': TREE,
            'xcresult_sha256': receipt_cli.base.bundle_digest(self.bundle), 'app_binary_sha256': receipt_cli.base.sha256_file(self.binary),
            'device_id': DEVICE, 'ci_run_id': '12345', 'ci_run_attempt': '1',
            'runs': [{'run_id': DEVICE, 'expected_cancel_count': 3, 'expected_selected_count': 0}]}))
        self.argv = ['--xcresult', str(self.bundle), '--identity', str(self.identity), '--app-binary', str(self.binary),
            '--output', str(self.output), '--diagnostics-output', str(self.diagnostics), '--expected-source-sha', SOURCE,
            '--expected-source-tree', TREE, '--expected-run', DEVICE, '--expected-device-id', DEVICE,
            '--expected-ci-run-id', '12345', '--expected-ci-run-attempt', '1', '--expected-device-model', gate.MODEL,
            '--expected-runtime-version', '27.0', '--expected-runtime-build', '24A434', '--runner-log-timezone', 'UTC']
        self.raw = ' { "result": "Passed", "UNIT_ONLY": true }\n\n'
        self.original_export = receipt_cli.export_summary
        self.logs = {'Session-UNIT.log': 'SYNTHETIC UNIT diagnostic log, never native proof'}

    def run_receipt(self, binder_error=None, summary_error=None, diagnostic_error=None, raw=None):
        raw = self.raw if raw is None else raw
        def tool(command, deadline):
            if 'help' in command: return '--path'
            if summary_error: raise summary_error
            return raw
        def export(bundle, **kwargs): return self.original_export(bundle, run_tool=tool, **kwargs)
        validator = Mock(side_effect=binder_error) if binder_error else Mock(return_value={'status': 'passed', 'release_qualification': False})
        with patch.object(receipt_cli, 'export_summary', side_effect=export), \
            patch.object(receipt_cli.base, 'export_diagnostics', side_effect=diagnostic_error, return_value={'method': 'UNIT'}), \
            patch.object(receipt_cli.base, 'read_diagnostics', return_value=self.logs), \
            patch.object(receipt_cli, 'validate_early_logs', validator), \
            patch.object(receipt_cli, 'verify_summary', return_value={'UNIT': True}):
            status = receipt_cli.main(self.argv)
        return status, json.loads(self.output.read_text()), validator

    def test_binder_rejection_retains_exact_raw_summary_and_diagnostics(self):
        status, result, _ = self.run_receipt(binder_error=receipt_cli.EvidenceError('genuine context/title mismatch'))
        self.assertEqual(status, 1); self.assertEqual(result['status'], 'invalid_evidence')
        self.assertIn('context/title mismatch', result['error'])
        self.assertEqual((self.root / 'official-test-summary.json').read_bytes(), self.raw.encode())
        self.assertTrue(result['diagnostics_retention_complete']); self.assertFalse(result['release_qualification'])
        self.assertFalse(result.get('identity_verified', False))

    def test_summary_export_failure_preserves_independent_binder_error(self):
        status, result, validator = self.run_receipt(binder_error=receipt_cli.EvidenceError('binder association rejection'),
            summary_error=receipt_cli.EvidenceError('official summary unavailable'))
        self.assertEqual(status, 1); validator.assert_called_once()
        self.assertEqual(result['error'], 'binder association rejection')
        self.assertEqual(result['summary_export_error'], 'official summary unavailable')
        self.assertTrue(result['diagnostics_retention_complete'])
        self.assertIn('official summary unavailable', (self.root / 'official-test-summary-export-error.json').read_text())

    def test_summary_export_failure_never_turns_valid_binder_into_pass(self):
        status, result, validator = self.run_receipt(summary_error=receipt_cli.EvidenceError('no summary'))
        self.assertEqual(status, 1); self.assertEqual(result['status'], 'invalid_evidence'); validator.assert_called_once()
        self.assertTrue(result['diagnostics_retention_complete']); self.assertFalse(result['release_qualification'])

    def test_summary_raw_is_retained_before_json_parse_failure(self):
        raw = 'official output that is not valid JSON\n'
        status, result, validator = self.run_receipt(raw=raw, binder_error=receipt_cli.EvidenceError('binder also failed'))
        self.assertEqual(status, 1); self.assertEqual((self.root / 'official-test-summary.json').read_text(), raw)
        self.assertIn('summary_export_error', result); self.assertEqual(result['error'], 'binder also failed')
        self.assertTrue(result['diagnostics_retention_complete']); validator.assert_called_once()

    def test_identity_failure_cannot_suppress_raw_summary(self):
        self.binary.write_bytes(b'mutated binary')
        status, result, validator = self.run_receipt()
        self.assertEqual(status, 1); self.assertIn('hash mismatch', result['error']); validator.assert_not_called()
        self.assertEqual((self.root / 'official-test-summary.json').read_text(), self.raw)

    def test_diagnostics_failure_cannot_suppress_raw_summary(self):
        status, result, validator = self.run_receipt(diagnostic_error=receipt_cli.EvidenceError('diagnostics failure'))
        self.assertEqual(status, 1); self.assertEqual(result['error'], 'diagnostics failure'); validator.assert_not_called()
        self.assertEqual((self.root / 'official-test-summary.json').read_text(), self.raw)

    def test_error_sidecar_write_failure_still_keeps_diagnostics_and_binder_error(self):
        original_write = Path.write_text
        def write(path, *args, **kwargs):
            if path.name == 'official-test-summary-export-error.json': raise OSError('cannot retain error sidecar')
            return original_write(path, *args, **kwargs)
        with patch.object(Path, 'write_text', new=write):
            status, result, _ = self.run_receipt(summary_error=ValueError('summary failure'), binder_error=ValueError('binder failure'))
        self.assertEqual(status, 1); self.assertEqual(result['error'], 'binder failure')
        self.assertIn('error sidecar', result['summary_export_error']); self.assertTrue(result['diagnostics_retention_complete'])

    def test_export_helper_has_one_shared_45_second_deadline(self):
        calls = []
        def tool(command, deadline): calls.append(deadline); return '--path' if 'help' in command else '{}'
        with patch.object(receipt_cli.time, 'monotonic', return_value=100):
            self.original_export(self.bundle, run_tool=tool, output=self.root / 'summary.json', deadline=999)
        self.assertEqual(calls, [145, 145])

    def test_export_helper_honors_earlier_parent_deadline(self):
        calls = []
        def tool(command, deadline): calls.append(deadline); return '--path' if 'help' in command else '{}'
        with patch.object(receipt_cli.time, 'monotonic', return_value=100):
            self.original_export(self.bundle, run_tool=tool, deadline=110)
        self.assertEqual(calls, [110, 110])

    def test_export_helper_rejects_stale_or_symlink_destination_before_tool(self):
        target = self.root / 'summary.json'; target.write_text('preserve')
        for path in [target, self.root / 'symlink.json']:
            if path != target: path.symlink_to(target)
            with self.subTest(path=path), patch.object(receipt_cli.base, '_run_tool') as tool:
                with self.assertRaises(receipt_cli.EvidenceError): self.original_export(self.bundle, run_tool=tool, output=path)
                tool.assert_not_called()
        self.assertEqual(target.read_text(), 'preserve')

    def test_cli_never_claims_stale_summary_as_its_retained_export(self):
        target = self.root / 'official-test-summary.json'; target.write_text('stale output')
        status, result, _ = self.run_receipt()
        self.assertEqual(status, 1); self.assertIn('must be fresh', result['summary_export_error'])
        self.assertNotIn('retained_test_summary', result); self.assertEqual(target.read_text(), 'stale output')

    def test_export_helper_unsupported_syntax_never_requests_summary(self):
        tool = Mock(return_value='unsupported')
        with self.assertRaises(receipt_cli.EvidenceError): self.original_export(self.bundle, run_tool=tool, output=self.root / 'summary.json')
        self.assertEqual(tool.call_count, 1); self.assertFalse((self.root / 'summary.json').exists())

    def test_executable_only_can_verify_parser_identity_but_not_bundle_digest(self):
        identity = json.loads(self.identity.read_text())
        retained = self.root / 'isolated-retained'; retained.mkdir()
        copy = retained / 'Celluloid-executable'; copy.write_bytes(self.binary.read_bytes())
        self.assertEqual(receipt_cli.base.verify_identity(identity, self.bundle, copy, SOURCE, TREE,
            {DEVICE.lower(): (3, 0)}), {DEVICE.lower(): (3, 0)})
        with self.assertRaises(receipt_cli.EvidenceError): receipt_cli.base.bundle_digest(retained)


if __name__ == '__main__': unittest.main()
