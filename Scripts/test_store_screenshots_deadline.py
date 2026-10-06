"""Synthetic-only capture deadline admission and owned cleanup boundaries."""
import contextlib
import errno
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

import native_process as native
import original_ios_process_guard as guard
import uikit_full_shipping_gate as gate
from test_store_screenshots_route import environment
from test_uikit_full_shipping_bootstrap import load_functions
from validation_route import FULL, ORIGINAL_IOS


class CaptureDeadlineTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        env = patch.dict(os.environ, environment(self.root), clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.context = guard.staged_context()
        self.clock = {'schema': gate.CLOCK_SCHEMA, **self.context,
                      'started_monotonic': 100.0, 'started_unix': 100.0,
                      'execution_budget_seconds': 3360}
        (self.root / 'full-shipping-clock.json').write_text(json.dumps(self.clock))
        self.enclosing = self.clock['started_monotonic'] + gate.WORK_SECONDS
        self.now = 1000.0
        monotonic = patch('native_process.time.monotonic', side_effect=lambda: self.now)
        monotonic.start()
        self.addCleanup(monotonic.stop)

    def run_command(self, timeout=60, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return native.run(['synthetic-command'], timeout=timeout, echo=False,
                              capture_deadline=self.enclosing, **kwargs)

    def process(self):
        process = MagicMock(pid=12345, returncode=None)
        process.poll.side_effect = lambda: process.returncode
        return process

    def test_expired_or_insufficient_full_allowance_refuses_before_ownership_or_spawn(self):
        for now in (self.enclosing + 1, self.enclosing, self.enclosing - 60, self.enclosing - 79.99):
            self.now = now
            with self.subTest(now=now), patch('native_process.OwnedCommand') as owner, patch('native_process.subprocess.Popen') as spawn:
                with self.assertRaisesRegex(TimeoutError, 'no dispatch'):
                    self.run_command()
                owner.assert_not_called()
                spawn.assert_not_called()

    def test_exact_command_cleanup_and_finalization_allowance_is_admitted(self):
        self.now = self.enclosing - 60 - 15 - 5
        process = self.process()
        process.returncode = 0
        process.communicate.return_value = ('completed', '')
        with patch('native_process.subprocess.Popen', return_value=process) as spawn:
            self.assertEqual(self.run_command().returncode, 0)
        spawn.assert_called_once()
        process.communicate.assert_called_once_with(timeout=60)
        self.assertIsNone(guard.read_inflight(self.root, self.context))

    def test_slow_owner_setup_invalidates_pre_spawn_admission(self):
        create_owner = guard.OwnedCommand
        def slow_owner(*args, **kwargs):
            owner = create_owner(*args, **kwargs)
            self.now = self.enclosing - 79
            return owner
        with patch('native_process.OwnedCommand', side_effect=slow_owner), patch('native_process.subprocess.Popen') as spawn:
            with self.assertRaisesRegex(TimeoutError, 'no dispatch'):
                self.run_command()
            spawn.assert_not_called()
        self.assertIsNone(guard.read_inflight(self.root, self.context)['child_pid'])
        self.assertEqual(guard.read_failure(self.root, self.context)['original_error']['type'], 'TimeoutError')

    def test_slow_print_before_spawn_cannot_keep_stale_allowance(self):
        def slow_print(*args, **kwargs):
            self.now = self.enclosing - 79
        with patch('builtins.print', side_effect=slow_print), patch('native_process.subprocess.Popen') as spawn:
            with self.assertRaisesRegex(TimeoutError, 'no dispatch'):
                self.run_command()
            spawn.assert_not_called()

    def test_spawn_and_started_receipt_consume_immutable_command_deadline(self):
        process = self.process()
        create_owner = guard.OwnedCommand
        def owner_with_slow_started(*args, **kwargs):
            owner = create_owner(*args, **kwargs)
            started = owner.started
            def slow_started(child):
                started(child)
                self.now += 10
            owner.started = slow_started
            return owner
        def spawn(*args, **kwargs):
            self.now += 30
            return process
        def communicate(timeout):
            self.assertEqual(timeout, 20)
            self.now += 19
            process.returncode = 0
            return 'completed', ''
        process.communicate.side_effect = communicate
        with patch('native_process.OwnedCommand', side_effect=owner_with_slow_started), patch('native_process.subprocess.Popen', side_effect=spawn):
            self.assertEqual(self.run_command(log_name='capture.log').returncode, 0)
        timing = json.loads((self.root / 'capture.log.timing.json').read_text())
        self.assertEqual(timing['capture_command_deadline_monotonic'], 1060)
        self.assertEqual(timing['capture_cleanup_deadline_monotonic'], 1075)
        self.assertEqual(timing['capture_enclosing_deadline_monotonic'], 2800)
        self.assertEqual(timing['capture_finalization_seconds'], 5)

    def test_late_spawn_does_not_start_wait_or_cleanup_after_immutable_deadlines(self):
        process = self.process()
        def spawn(*args, **kwargs):
            self.now = 1076
            return process
        with patch('native_process.subprocess.Popen', side_effect=spawn), patch('native_process.os.killpg') as kill:
            with self.assertRaises(TimeoutError):
                self.run_command()
            kill.assert_not_called()
            process.communicate.assert_not_called()
        self.assertEqual(guard.read_failure(self.root, self.context)['cleanup']['status'], 'bounded_cleanup_expired')

    def test_term_and_kill_waits_are_clipped_after_signal_and_receipt_overhead(self):
        process = self.process()
        waits = []
        def communicate(timeout):
            waits.append(timeout)
            self.now += timeout
            raise subprocess.TimeoutExpired('synthetic-command', timeout, output=b'partial')
        def kill(pid, which):
            self.now += 3 if which == signal.SIGTERM else 1
        process.communicate.side_effect = communicate
        with patch('native_process.subprocess.Popen', return_value=process), patch('native_process.os.killpg', side_effect=kill) as signals:
            with self.assertRaises(TimeoutError):
                self.run_command()
        self.assertEqual(waits, [60, 10, 1])
        self.assertEqual([call.args[1] for call in signals.call_args_list], [signal.SIGTERM, signal.SIGKILL])
        self.assertEqual(self.now, 1075)
        self.assertEqual(guard.read_failure(self.root, self.context)['cleanup']['status'], 'bounded_cleanup_expired')

    def test_slow_first_cleanup_receipt_does_not_dispatch_a_wait_after_deadline(self):
        process = self.process()
        create_owner = guard.OwnedCommand
        def owner_with_slow_receipt(*args, **kwargs):
            owner = create_owner(*args, **kwargs)
            cleanup_result = owner.cleanup_result
            def slow_cleanup(*args, **kwargs):
                cleanup_result(*args, **kwargs)
                if kwargs.get('signal_name'):
                    self.now = 1076
            owner.cleanup_result = slow_cleanup
            return owner
        def timeout(seconds):
            self.now = 1060
            raise subprocess.TimeoutExpired('synthetic-command', seconds)
        process.communicate.side_effect = lambda **kwargs: timeout(kwargs['timeout'])
        with patch('native_process.OwnedCommand', side_effect=owner_with_slow_receipt), patch('native_process.subprocess.Popen', return_value=process), patch('native_process.os.killpg') as signals:
            with self.assertRaises(TimeoutError):
                self.run_command()
        process.communicate.assert_called_once_with(timeout=60)
        signals.assert_called_once_with(12345, signal.SIGTERM)

    def test_denied_signal_keeps_original_failure_and_never_waits_or_signals_again(self):
        process = self.process()
        original = subprocess.TimeoutExpired('synthetic-command', 60, output=b'original partial')
        def timeout(**kwargs):
            self.now = 1060
            raise original
        process.communicate.side_effect = timeout
        with patch('native_process.subprocess.Popen', return_value=process), patch('native_process.os.killpg', side_effect=PermissionError(errno.EPERM, 'denied')) as signals:
            with self.assertRaises(TimeoutError) as caught:
                self.run_command()
        self.assertIs(caught.exception.__cause__, original)
        process.communicate.assert_called_once_with(timeout=60)
        signals.assert_called_once_with(12345, signal.SIGTERM)
        self.assertEqual(guard.read_failure(self.root, self.context)['cleanup']['status'], 'signal_denied')

    def test_bound_route_clock_and_numeric_deadline_cannot_be_laundered(self):
        for deadline in (True, float('nan'), float('inf'), self.enclosing + 1, self.enclosing + 6000):
            with self.subTest(deadline=deadline), patch('native_process.subprocess.Popen') as spawn:
                with self.assertRaises((guard.GuardRefusal, ValueError)):
                    with contextlib.redirect_stdout(io.StringIO()):
                        native.run(['synthetic-command'], timeout=60, capture_deadline=deadline)
                spawn.assert_not_called()
        for key, value in (('source_sha', 'b' * 40), ('run_id', '7654321'), ('run_attempt', '2'), ('row', 'large-ipad'), ('validation_route', ORIGINAL_IOS)):
            (self.root / 'full-shipping-clock.json').write_text(json.dumps(dict(self.clock, **{key: value})))
            with self.subTest(key=key), patch('native_process.subprocess.Popen') as spawn:
                with self.assertRaises((guard.GuardRefusal, ValueError)):
                    self.run_command()
                spawn.assert_not_called()
        (self.root / 'full-shipping-clock.json').write_text(json.dumps(self.clock))
        with patch.dict(os.environ, GITHUB_REF='refs/heads/' + FULL['branch'], CELLULOID_VALIDATION_SCOPE=FULL['scope']), patch('native_process.subprocess.Popen') as spawn:
            with self.assertRaises(guard.GuardRefusal):
                self.run_command()
            spawn.assert_not_called()

    def test_clock_cannot_reset_during_owner_setup(self):
        create_owner = guard.OwnedCommand
        def changed_clock(*args, **kwargs):
            owner = create_owner(*args, **kwargs)
            value = dict(self.clock, started_unix=self.clock['started_unix'] + 1)
            (self.root / 'full-shipping-clock.json').write_text(json.dumps(value))
            return owner
        with patch('native_process.OwnedCommand', side_effect=changed_clock), patch('native_process.subprocess.Popen') as spawn:
            with self.assertRaisesRegex(guard.GuardRefusal, 'binding changed'):
                self.run_command()
            spawn.assert_not_called()

    def test_default_canonical_path_does_not_use_capture_clock_or_bridge(self):
        process = self.process()
        process.returncode = 0
        process.communicate.return_value = ('unchanged canonical', '')
        with patch.dict(os.environ, GITHUB_REF='refs/heads/' + FULL['branch'], CELLULOID_VALIDATION_SCOPE=FULL['scope']), patch('native_process._capture_admission', side_effect=AssertionError('capture bridge called')), patch('native_process.subprocess.Popen', return_value=process), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(native.run(['synthetic-command'], timeout=60, echo=False).returncode, 0)
        process.communicate.assert_called_once_with(timeout=60)

    def test_capture_bootstrap_passes_same_absolute_work_deadline_to_both_owned_paths(self):
        functions = load_functions(self.root)
        result = subprocess.CompletedProcess([], 0, 'completed', '')
        with patch('native_process.run', return_value=result) as run, contextlib.redirect_stdout(io.StringIO()):
            functions['run']('import-0', 480, 'xcrun', 'simctl', 'addmedia', 'owned', 'fixture.png')
            functions['host_command'](['vm_stat'])
        self.assertEqual(len(run.call_args_list), 2)
        self.assertTrue(all(call.kwargs['capture_deadline'] == self.enclosing for call in run.call_args_list))
        self.assertEqual([call.kwargs['timeout'] for call in run.call_args_list], [480, 15])
        self.now = self.enclosing - 499
        with self.assertRaises(TimeoutError):
            functions['require_inner_allowance'](480)
        self.now = self.enclosing - 500
        functions['require_inner_allowance'](480)


@unittest.skipUnless(os.name == 'posix', 'Owned process groups require POSIX')
class ActualPythonProcessTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        env = patch.dict(os.environ, environment(self.root), clear=True)
        env.start()
        self.addCleanup(env.stop)

    def test_actual_python_child_uses_capture_deadline_and_finalizes_owned_group(self):
        context = guard.staged_context()
        clock = {'schema': gate.CLOCK_SCHEMA, **context,
                 'started_monotonic': time.monotonic(), 'started_unix': time.time(),
                 'execution_budget_seconds': gate.EXECUTION_SECONDS}
        (self.root / 'full-shipping-clock.json').write_text(json.dumps(clock))
        enclosing = clock['started_monotonic'] + gate.WORK_SECONDS
        code = 'import json, os; print(json.dumps({"pid": os.getpid(), "pgid": os.getpgrp(), "result": "actual capture child"}))'
        with contextlib.redirect_stdout(io.StringIO()):
            result = native.run([sys.executable, '-c', code], timeout=5, echo=False,
                                log_name='actual-capture.log', capture_deadline=enclosing)
        self.assertEqual(result.returncode, 0)
        observed = json.loads(result.stdout)
        self.assertEqual(observed['result'], 'actual capture child')
        self.assertEqual(observed['pid'], observed['pgid'])
        self.assertNotEqual(observed['pgid'], os.getpgrp())
        self.assertIsNone(guard.read_inflight(self.root, context))
        self.assertIsNone(guard.read_failure(self.root, context))
        timing = json.loads((self.root / 'actual-capture.log.timing.json').read_text())
        self.assertEqual(timing['capture_enclosing_deadline_monotonic'], enclosing)
        self.assertEqual(timing['capture_cleanup_deadline_monotonic'], timing['capture_command_deadline_monotonic'] + 15)
        self.assertLessEqual(timing['capture_cleanup_deadline_monotonic'] + 5, enclosing)
        self.assertFalse(timing['timed_out'])

    def test_actual_default_python_caller_needs_no_capture_clock(self):
        self.assertFalse((self.root / 'full-shipping-clock.json').exists())
        with patch.dict(os.environ, GITHUB_REF='refs/heads/' + FULL['branch'], CELLULOID_VALIDATION_SCOPE=FULL['scope']), contextlib.redirect_stdout(io.StringIO()):
            result = native.run([sys.executable, '-c', 'print("actual default child")'], timeout=5,
                                echo=False, log_name='actual-default.log')
            nonzero = native.run([sys.executable, '-c', 'raise SystemExit(7)'], timeout=5,
                                 echo=False, check=False)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), 'actual default child')
        self.assertEqual(nonzero.returncode, 7)
        self.assertFalse((self.root / guard.INFLIGHT_NAME).exists())
        self.assertFalse((self.root / guard.MARKER_NAME).exists())
        timing = json.loads((self.root / 'actual-default.log.timing.json').read_text())
        self.assertFalse(any(key.startswith('capture_') for key in timing))


if __name__ == '__main__':
    unittest.main()
