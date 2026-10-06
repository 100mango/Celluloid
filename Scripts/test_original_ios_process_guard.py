#!/usr/bin/env python3
"""Executable host-only failure injection; never launches Xcode or a simulator."""
import contextlib
import errno
import io
import json
import os
from pathlib import Path
import runpy
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import native_process
import original_ios_process_guard as guard
from validation_route import ORIGINAL_IOS, FULL, UIKIT_FULL, REPOSITORY

SCRIPTS = Path(__file__).resolve().parent


def environment(root):
    return {'GITHUB_REF': 'refs/heads/' + ORIGINAL_IOS['branch'], 'GITHUB_REPOSITORY': REPOSITORY,
            'GITHUB_EVENT_NAME': 'push', 'CELLULOID_VALIDATION_SCOPE': ORIGINAL_IOS['scope'],
            'GITHUB_WORKFLOW_REF': REPOSITORY + '/' + ORIGINAL_IOS['workflow_path'] + '@refs/heads/' + ORIGINAL_IOS['branch'],
            'GITHUB_SHA': 'a' * 40, 'GITHUB_WORKFLOW_SHA': 'a' * 40, 'GITHUB_RUN_ID': '37418420393',
            'GITHUB_RUN_ATTEMPT': '1', 'CELLULOID_FULL_ROW': 'compact-phone', 'RUNNER_TEMP': str(root)}


class ProcessGuardTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.env = environment(self.root)
        self.patch = patch.dict(os.environ, self.env, clear=True)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.context = guard.staged_context()

    def quiet_run(self, args, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return native_process.run(args, echo=False, **kwargs)

    def bounded(self, command, seconds=0.05):
        arguments = ['run_bounded.py', '--seconds', str(seconds), '--label', 'units summary', *command]
        with patch.object(sys, 'argv', arguments), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as exit_result:
            runpy.run_path(str(SCRIPTS / 'run_bounded.py'), run_name='__main__')
        return exit_result.exception.code

    def first_failure(self):
        owner = guard.OwnedCommand('xcrun', 'units summary', 30)
        owner.started(MagicMock(pid=1234))
        owner.failed(subprocess.TimeoutExpired('xcrun', 30), timed_out=True)
        return owner

    def test_completed_nonzero_native_does_not_block_independent_case(self):
        result = self.quiet_run([sys.executable, '-c', 'raise SystemExit(65)'], check=False)
        self.assertEqual(result.returncode, 65)
        self.assertFalse((self.root / guard.MARKER_NAME).exists())
        self.assertFalse((self.root / guard.INFLIGHT_NAME).exists())
        self.assertEqual(self.quiet_run([sys.executable, '-c', 'print("independent")']).stdout.strip(), 'independent')

    def test_completed_nonzero_bounded_does_not_block_independent_case(self):
        self.assertEqual(self.bounded([sys.executable, '-c', 'raise SystemExit(65)'], seconds=5), 65)
        self.assertIsNone(guard.read_failure(self.root, self.context))
        self.assertEqual(self.bounded([sys.executable, '-c', 'pass'], seconds=5), 0)

    def test_native_eperm_retains_original_and_prevents_real_successor(self):
        process = MagicMock(pid=43123, returncode=None)
        original = subprocess.TimeoutExpired('xcrun', 120, output=b'partial readiness', stderr=b'original stderr')
        process.communicate.side_effect = original
        denied = PermissionError(errno.EPERM, 'Operation not permitted')
        with patch('native_process.subprocess.Popen', return_value=process) as launch, patch('native_process.os.killpg', side_effect=denied) as kill:
            with self.assertRaisesRegex(TimeoutError, 'exceeded 120s.*denied') as raised:
                self.quiet_run(['xcrun', 'simctl', 'get_app_container', 'owned', 'Mango.Celluloid', 'app'], timeout=120, log_name='query.log')
            self.assertIs(raised.exception.__cause__, original)
            launch.assert_called_once()
            kill.assert_called_once_with(43123, signal.SIGTERM)
            process.communicate.assert_called_once()
            self.assertTrue(0 < process.communicate.call_args.kwargs['timeout'] <= 120)
        failure = guard.read_failure(self.root, self.context)
        self.assertEqual(failure['original_error']['type'], 'TimeoutExpired')
        self.assertEqual(failure['child_pid'], 43123)
        self.assertEqual(failure['child_pgid'], 43123)
        self.assertEqual(failure['cleanup']['status'], 'signal_denied')
        self.assertEqual(failure['cleanup']['signals'][0]['error']['errno'], errno.EPERM)
        self.assertFalse(failure['cleanup']['group_exit_confirmed'])
        timing = json.loads((self.root / 'query.log.timing.json').read_text())
        self.assertTrue(timing['timed_out'])
        self.assertEqual(timing['timeout_seconds'], 120)
        self.assertIsNone(timing['return_code'])
        self.assertIn('partial readiness', (self.root / 'query.log').read_text())
        self.assertNotIn('signals completed', (self.root / 'query.log').read_text())
        successor = self.root / 'successor-launched'
        with self.assertRaises(guard.GuardRefusal):
            self.quiet_run([sys.executable, '-c', 'from pathlib import Path; Path(' + repr(str(successor)) + ').touch()'])
        self.assertFalse(successor.exists())
        self.assertEqual(guard.read_failure(self.root, self.context), failure)

    def test_bounded_eperm_has_end_and_no_diagnostic_or_alternate_signal(self):
        process = MagicMock(pid=54123, returncode=None)
        process.wait.side_effect = subprocess.TimeoutExpired('xcresulttool summary', 30)
        output = io.StringIO()
        with patch('subprocess.Popen', return_value=process), patch('os.killpg', side_effect=PermissionError(errno.EPERM, 'Operation not permitted')) as kill, patch('subprocess.run', side_effect=AssertionError('diagnostic launched')):
            arguments = ['run_bounded.py', '--seconds', '30', '--label', 'units summary', 'xcrun', 'xcresulttool']
            with patch.object(sys, 'argv', arguments), contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as exited:
                runpy.run_path(str(SCRIPTS / 'run_bounded.py'), run_name='__main__')
            self.assertEqual(exited.exception.code, 124)
            kill.assert_called_once_with(54123, signal.SIGTERM)
            process.wait.assert_called_once()
            self.assertTrue(0 < process.wait.call_args.kwargs['timeout'] <= 30)
        self.assertIn('BOUNDED_COMMAND_END', output.getvalue())
        failure = guard.read_failure(self.root, self.context)
        self.assertEqual(failure['cleanup']['status'], 'signal_denied')
        self.assertEqual(failure['original_error']['type'], 'TimeoutExpired')
        self.assertEqual(failure['child_pid'], 54123)
        successor = self.root / 'bounded-successor-launched'
        result = subprocess.run([sys.executable, str(SCRIPTS / 'run_bounded.py'), '--seconds', '5', '--label', 'forbidden successor', sys.executable, '-c', 'from pathlib import Path; Path(' + repr(str(successor)) + ').touch()'], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(successor.exists())
        self.assertNotIn('BOUNDED_COMMAND_BEGIN', result.stdout)

    def test_all_staged_cleanup_waits_are_finite(self):
        for adapter in ['native', 'bounded']:
            with self.subTest(adapter=adapter):
                for name in [guard.MARKER_NAME, guard.INFLIGHT_NAME]:
                    (self.root / name).unlink(missing_ok=True)
                process = MagicMock(pid=65432, returncode=None)
                process.communicate.side_effect = subprocess.TimeoutExpired('original', 1)
                process.wait.side_effect = subprocess.TimeoutExpired('original', 1)
                with patch('subprocess.Popen', return_value=process), patch('os.killpg') as kill:
                    if adapter == 'native':
                        with self.assertRaises(TimeoutError):
                            self.quiet_run(['original'], timeout=1)
                        waits = process.communicate.call_args_list
                        self.assertTrue(0 < waits[0].kwargs['timeout'] <= 1)
                        self.assertEqual([call.kwargs['timeout'] for call in waits[1:]], [10, 5])
                    else:
                        self.assertEqual(self.bounded(['original'], seconds=1), 124)
                        waits = process.wait.call_args_list
                        self.assertTrue(0 < waits[0].kwargs['timeout'] <= 1)
                        self.assertEqual([call.kwargs['timeout'] for call in waits[1:]], [5, 5])
                    self.assertEqual([call.args[1] for call in kill.call_args_list], [signal.SIGTERM, signal.SIGKILL])
                self.assertEqual(guard.read_failure(self.root, self.context)['cleanup']['status'], 'bounded_cleanup_expired')

    def test_denied_final_signal_also_stops_without_wait_or_fallback(self):
        process = MagicMock(pid=43123, returncode=None)
        process.communicate.side_effect = subprocess.TimeoutExpired('original', 1, output=b'partial')
        with patch('native_process.subprocess.Popen', return_value=process), patch('native_process.os.killpg', side_effect=[None, PermissionError(errno.EPERM, 'denied')]) as kill:
            with self.assertRaises(TimeoutError):
                self.quiet_run(['original'], timeout=1)
            self.assertEqual([call.args[1] for call in kill.call_args_list], [signal.SIGTERM, signal.SIGKILL])
            waits = process.communicate.call_args_list
            self.assertTrue(0 < waits[0].kwargs['timeout'] <= 1)
            self.assertEqual([call.kwargs['timeout'] for call in waits[1:]], [10])
        failure = guard.read_failure(self.root, self.context)
        self.assertEqual(failure['cleanup']['status'], 'signal_denied')
        self.assertEqual(failure['original_error']['type'], 'TimeoutExpired')

    def test_late_spawn_or_successful_wait_never_clears_or_signals_reaped_child(self):
        for adapter in ['native', 'bounded']:
            for late_stage in ['spawn', 'wait']:
                with self.subTest(adapter=adapter, late_stage=late_stage):
                    for name in [guard.MARKER_NAME, guard.INFLIGHT_NAME]:
                        (self.root / name).unlink(missing_ok=True)
                    clock = [0]
                    process = MagicMock(pid=54321, returncode=None)
                    process.poll.side_effect = lambda: process.returncode
                    def launch(*args, **kwargs):
                        clock[0] = 121 if late_stage == 'spawn' else 10
                        if late_stage == 'spawn': process.returncode = 0
                        return process
                    def finish(*args, **kwargs):
                        clock[0] = 121
                        process.returncode = 0
                        return ('completed output', '') if adapter == 'native' else 0
                    process.communicate.side_effect = finish
                    process.wait.side_effect = finish
                    with patch('time.monotonic', side_effect=lambda: clock[0]), patch('subprocess.Popen', side_effect=launch), patch('os.killpg') as kill:
                        if adapter == 'native':
                            with self.assertRaises(TimeoutError):
                                self.quiet_run(['original'], timeout=120)
                            waits = process.communicate
                        else:
                            self.assertEqual(self.bounded(['original'], seconds=120), 124)
                            waits = process.wait
                        kill.assert_not_called()
                        if late_stage == 'spawn':
                            waits.assert_not_called()
                        else:
                            waits.assert_called_once_with(timeout=110)
                    failure = guard.read_failure(self.root, self.context)
                    self.assertEqual(failure['failure_kind'], 'timeout')
                    self.assertEqual(failure['timeout_seconds'], 120)
                    self.assertEqual(failure['cleanup']['status'], 'child_reaped')
                    self.assertEqual(failure['cleanup']['child_returncode'], 0)
                    self.assertEqual(failure['cleanup']['signals'], [])
                    with self.assertRaises(guard.GuardRefusal):
                        guard.require_clear()

    def test_spawn_consumes_initial_allowance_but_in_time_nonzero_stays_allowed(self):
        for adapter in ['native', 'bounded']:
            with self.subTest(adapter=adapter):
                clock = [0]
                process = MagicMock(pid=54321, returncode=None)
                def launch(*args, **kwargs):
                    clock[0] = 10
                    return process
                def finish(*args, **kwargs):
                    clock[0] = 119
                    process.returncode = 65
                    return ('failed test output', '') if adapter == 'native' else 65
                process.communicate.side_effect = finish
                process.wait.side_effect = finish
                with patch('time.monotonic', side_effect=lambda: clock[0]), patch('subprocess.Popen', side_effect=launch), patch('os.killpg') as kill:
                    if adapter == 'native':
                        self.assertEqual(self.quiet_run(['original'], timeout=120, check=False).returncode, 65)
                        process.communicate.assert_called_once_with(timeout=110)
                    else:
                        self.assertEqual(self.bounded(['original'], seconds=120), 65)
                        process.wait.assert_called_once_with(timeout=110)
                    kill.assert_not_called()
                self.assertIsNone(guard.read_failure(self.root, self.context))
                self.assertIsNone(guard.read_inflight(self.root, self.context))

    def test_actual_timeout_blocks_even_after_child_reaped(self):
        actual=[];launch=subprocess.Popen
        def started(*args,**kwargs):
            process=launch(*args,**kwargs)
            actual.append((process.pid,os.getpgid(process.pid)))
            return process
        with patch('subprocess.Popen',side_effect=started),self.assertRaises(TimeoutError):
            self.quiet_run([sys.executable, '-c', 'import time; time.sleep(10)'], timeout=0.05, log_name='actual.log')
        failure = guard.read_failure(self.root, self.context)
        self.assertEqual(failure['cleanup']['status'], 'child_reaped')
        self.assertGreater(failure['child_pid'], 0)
        self.assertEqual(len(actual),1)
        self.assertEqual((failure['child_pid'], failure['child_pgid']),actual[0])
        with self.assertRaises(guard.GuardRefusal):
            guard.require_clear()

    def test_external_helper_death_leaves_durable_inflight(self):
        code = 'import os,sys,subprocess; from original_ios_process_guard import OwnedCommand; owner=OwnedCommand(sys.executable,"interrupted owner",5); p=subprocess.Popen([sys.executable,"-c","pass"],start_new_session=True); owner.started(p); p.wait(timeout=5); os._exit(0)'
        result = subprocess.run([sys.executable, '-c', code], cwd=SCRIPTS, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        record = guard.read_inflight(self.root, self.context)
        self.assertEqual(record['state'], 'running')
        self.assertGreater(record['child_pid'], 0)
        with self.assertRaisesRegex(guard.GuardRefusal, 'finalization is unknown'):
            guard.require_clear()
        with patch('native_process.subprocess.Popen') as launch, self.assertRaises(guard.GuardRefusal):
            self.quiet_run(['must-not-launch'])
        launch.assert_not_called()

    def test_reservation_before_popen_and_abnormal_signal_are_fail_closed(self):
        owner = guard.OwnedCommand('synthetic', 'reserved', 1)
        self.assertIsNone(guard.read_inflight(self.root, self.context)['child_pid'])
        with self.assertRaises(guard.GuardRefusal):
            guard.require_clear()
        owner.started(MagicMock(pid=87654))
        owner.completed(-9)
        failure = guard.read_failure(self.root, self.context)
        self.assertEqual(failure['failure_kind'], 'unknown_termination')
        self.assertEqual(failure['cleanup']['child_returncode'], -9)

    def test_explicit_offline_context_is_enforced_without_row_environment(self):
        self.first_failure()
        os.environ.pop('CELLULOID_FULL_ROW')
        self.assertFalse(guard.active())
        self.assertIsNone(guard.require_clear())
        with self.assertRaises(guard.GuardRefusal):
            guard.require_clear(self.root, self.context)

    def test_four_rows_only_and_other_routes_unchanged(self):
        for row in guard.ROWS:
            with patch.dict(os.environ, CELLULOID_FULL_ROW=row):
                self.assertTrue(guard.active())
        for row in ['', 'phone', 'unreviewed']:
            with patch.dict(os.environ, CELLULOID_FULL_ROW=row), self.assertRaises(guard.GuardRefusal):
                guard.active()
        for route in [FULL, UIKIT_FULL]:
            with patch.dict(os.environ, GITHUB_REF='refs/heads/' + route['branch'], CELLULOID_VALIDATION_SCOPE=route['scope']):
                self.assertFalse(guard.active())
                self.assertEqual(self.quiet_run([sys.executable, '-c', 'pass']).returncode, 0)
        with patch.dict(os.environ, GITHUB_WORKFLOW_SHA='b' * 40), self.assertRaises(guard.GuardRefusal):
            guard.active()

    def test_either_staged_hint_requires_complete_exact_route_identity(self):
        for key, value in [('GITHUB_REF', 'refs/heads/' + FULL['branch']),
                           ('GITHUB_REF', 'refs/heads/' + UIKIT_FULL['branch']),
                           ('GITHUB_REF', 'refs/heads/unreviewed'), ('GITHUB_REF', None),
                           ('GITHUB_REF', False), ('CELLULOID_VALIDATION_SCOPE', 'full'),
                           ('CELLULOID_VALIDATION_SCOPE', None), ('CELLULOID_VALIDATION_SCOPE', []),
                           ('GITHUB_REPOSITORY', 'other/repository'), ('GITHUB_EVENT_NAME', 'pull_request'),
                           ('GITHUB_WORKFLOW_REF', 'wrong'), ('GITHUB_WORKFLOW_SHA', 'b' * 40),
                           ('GITHUB_SHA', 123), ('CELLULOID_FULL_ROW', None),
                           ('CELLULOID_FULL_ROW', []), ('GITHUB_RUN_ID', 123)]:
            changed = dict(self.env); changed[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(guard.GuardRefusal):
                guard.staged_context(changed)
        for key in ['GITHUB_REF', 'CELLULOID_VALIDATION_SCOPE', 'GITHUB_REPOSITORY', 'GITHUB_EVENT_NAME',
                    'GITHUB_WORKFLOW_REF', 'GITHUB_WORKFLOW_SHA', 'GITHUB_SHA', 'GITHUB_RUN_ATTEMPT']:
            changed = dict(self.env); changed.pop(key)
            with self.subTest(missing=key), self.assertRaises(guard.GuardRefusal):
                guard.staged_context(changed)
        no_row = dict(self.env); no_row.pop('CELLULOID_FULL_ROW'); no_row['GITHUB_REF'] = 'unreviewed'
        self.assertIsNone(guard.staged_context(no_row))
        with patch.dict(os.environ, GITHUB_REF='refs/heads/' + FULL['branch']), patch('native_process.subprocess.Popen') as launch, self.assertRaises(guard.GuardRefusal):
            self.quiet_run(['must-not-launch'])
        launch.assert_not_called()

    def test_malformed_stale_type_size_and_symlink_markers_block_launch(self):
        self.first_failure()
        path = self.root / guard.MARKER_NAME
        good = json.loads(path.read_text())
        variants = []
        for key, value in [('source_sha', 'b' * 40), ('run_id', '37418420394'), ('run_attempt', '2'), ('row', 'large-phone'), ('child_pid', True), ('timeout_seconds', True), ('blocked_native_dispatch', 1), ('schema', 'unreviewed'), ('failure_kind', [])]:
            changed = dict(good); changed[key] = value; variants.append(json.dumps(changed))
        variants += ['null', '[]', '{}', '{"a":1,"a":2}', '{broken', 'x' * (guard.MAX_MARKER_BYTES + 1), json.dumps(good).replace('30,', 'NaN,')]
        for raw in variants:
            with self.subTest(raw=raw[:100]):
                path.write_text(raw)
                with patch('native_process.subprocess.Popen') as launch, self.assertRaises(guard.GuardRefusal):
                    self.quiet_run(['must-not-launch'])
                launch.assert_not_called()
        path.unlink(); path.symlink_to(self.root / 'missing')
        with self.assertRaises(guard.GuardRefusal):
            guard.require_clear()
        path.unlink(); path.mkdir()
        with self.assertRaises(guard.GuardRefusal):
            guard.require_clear()
        path.rmdir(); os.mkfifo(path)
        with self.assertRaises(guard.GuardRefusal):
            guard.require_clear()

    def test_inner_timeout_is_retained_before_ordinary_outer_nonzero_exit(self):
        code = 'import sys; sys.path.insert(0,' + repr(str(SCRIPTS)) + '); from original_ios_process_guard import record_inflight_failure; import subprocess; record_inflight_failure(subprocess.TimeoutExpired("inner summary",30),timed_out=True); raise SystemExit(1)'
        self.assertEqual(self.bounded([sys.executable, '-c', code], seconds=5), 1)
        failure = guard.read_failure(self.root, self.context)
        self.assertEqual(failure['failure_kind'], 'timeout')
        self.assertEqual(failure['original_error']['type'], 'TimeoutExpired')
        self.assertIn('inner summary', failure['original_error']['message'])
        self.assertEqual(failure['child_pid'], guard.read_inflight(self.root, self.context)['child_pid'])
        with self.assertRaises(guard.GuardRefusal):
            self.quiet_run(['must-not-launch'])

    def test_inner_dispatch_requires_existing_running_group_and_no_failure(self):
        with self.assertRaises(guard.GuardRefusal):
            guard.ensure_inflight_dispatch()
        owner = guard.OwnedCommand('outer', 'outer', 5)
        with self.assertRaises(guard.GuardRefusal):
            guard.ensure_inflight_dispatch()
        owner.started(MagicMock(pid=os.getpgrp() + 100000))
        with self.assertRaises(guard.GuardRefusal):
            guard.ensure_inflight_dispatch()
        owner.started(MagicMock(pid=os.getpgrp()))
        with patch('subprocess.Popen') as launch, patch('os.killpg') as kill:
            self.assertEqual(guard.ensure_inflight_dispatch(), self.context)
            launch.assert_not_called()
            kill.assert_not_called()
        owner.failed(subprocess.TimeoutExpired('inner', 5), timed_out=True)
        with self.assertRaises(guard.GuardRefusal):
            guard.ensure_inflight_dispatch()
        with patch.dict(os.environ, GITHUB_REF='refs/heads/' + FULL['branch'], CELLULOID_VALIDATION_SCOPE=FULL['scope']):
            self.assertIsNone(guard.ensure_inflight_dispatch())

    def test_inner_failure_cannot_claim_unrelated_process_group(self):
        owner = guard.OwnedCommand('outer', 'outer', 5)
        owner.started(MagicMock(pid=os.getpgrp() + 100000))
        with self.assertRaises(guard.GuardRefusal):
            guard.record_inflight_failure(TimeoutError('unrelated'), timed_out=True)
        self.assertIsNone(guard.read_failure(self.root, self.context))

    def test_first_failure_is_bounded_and_never_replaced(self):
        owner = self.first_failure()
        before = (self.root / guard.MARKER_NAME).read_bytes()
        owner.failed(RuntimeError('later failure'))
        self.assertEqual((self.root / guard.MARKER_NAME).read_bytes(), before)
        self.assertLessEqual(len(before), guard.MAX_MARKER_BYTES)
        broken = dict(guard.read_inflight(self.root, self.context)); broken['state'] = False
        (self.root / guard.INFLIGHT_NAME).write_text(json.dumps(broken))
        with self.assertRaises(guard.GuardRefusal):
            guard.read_inflight(self.root, self.context)


if __name__ == '__main__':
    unittest.main()
