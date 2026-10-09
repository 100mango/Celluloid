"""Local stdlib-only evidence-helper tests; never invokes simctl or sample."""
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

import ios_install_observer as observer

REAL_POPEN = subprocess.Popen
DEVICE = '12345678-1234-1234-1234-123456789ABC'
COMMAND = ['xcrun', 'simctl', 'install', DEVICE, '/owned/Celluloid.app']


class Clock:
    def __init__(self, value=100.):
        self.value = value
    def __call__(self):
        return self.value


class Child:
    def __init__(self, clock, waits=(), pid=12345):
        self.clock = clock
        self.pid = pid
        self.waits = list(waits)
        self.calls = []
        self.returncode = None
        self.stdout = io.BytesIO()
        self.stderr = io.BytesIO()
    def poll(self):
        self.calls.append(('poll',))
        return self.returncode
    def wait(self, timeout):
        self.calls.append(('wait', timeout))
        elapsed, result = self.waits.pop(0)
        self.clock.value += elapsed
        if result == 'timeout':
            raise subprocess.TimeoutExpired(COMMAND, timeout)
        self.returncode = result
        return result


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.out = Path(self.folder.name)
        self.context = {'source_sha': 'a' * 40, 'run_id': '123', 'run_attempt': '1'}
        self.clock = Clock()

    def sample_receipt(self):
        value = json.loads((self.out / 'install-sample.json').read_text())
        self.assertEqual(value, self.context['sample_receipt'])
        self.assertFalse(value['group_exit_confirmed'])
        return value

    def wait(self, child, deadline=220):
        return observer.wait_with_one_sample(child, deadline, COMMAND, self.out, self.context)

    def test_early_success_and_error_keep_actual_install_code_without_sample(self):
        for code in (0, 7):
            with self.subTest(code=code), patch.object(observer.time, 'monotonic', self.clock), patch.object(observer.subprocess, 'Popen') as popen:
                child = Child(self.clock, [(2, code)])
                self.assertEqual(self.wait(child), code)
                popen.assert_not_called()
                receipt = self.sample_receipt()
                self.assertEqual(receipt['skip_reason'], 'install_exited_before_sample')
                self.assertEqual(receipt['install_returncode'], code)
                self.assertFalse(receipt['uncertain'])

    def test_late_zero_never_replaces_install_timeout(self):
        with patch.object(observer.time, 'monotonic', self.clock), patch.object(observer.subprocess, 'Popen') as popen:
            child = Child(self.clock, [(121, 0)])
            with self.assertRaises(subprocess.TimeoutExpired):
                self.wait(child)
            popen.assert_not_called()
            self.assertEqual(self.sample_receipt()['skip_reason'], 'late_install_exit')
            self.assertEqual(self.sample_receipt()['install_returncode'], 0)

    def test_install_deadline_expired_before_entry_has_no_wait_or_sample(self):
        with patch.object(observer.time, 'monotonic', self.clock), patch.object(observer.subprocess, 'Popen') as popen:
            child = Child(self.clock)
            with self.assertRaises(subprocess.TimeoutExpired):
                self.wait(child, deadline=100)
            self.assertEqual(child.calls, [])
            popen.assert_not_called()
            self.assertEqual(self.sample_receipt()['skip_reason'], 'install_deadline_expired')

    def test_timeout_before_sample_keeps_original_install_deadline(self):
        with patch.object(observer.time, 'monotonic', self.clock), patch.object(observer.subprocess, 'Popen') as popen:
            child = Child(self.clock, [(30, 'timeout')])
            with self.assertRaises(subprocess.TimeoutExpired):
                self.wait(child, deadline=130)
            popen.assert_not_called()
            self.assertEqual(child.calls, [('wait', 30)])
            self.assertEqual(self.sample_receipt()['skip_reason'], 'install_deadline_expired')

    def test_missing_or_untyped_pid_skips_sample_but_waits_for_install(self):
        for pid in (None, '12345', True, 0, -1, 2 ** 31):
            self.clock.value = 100
            with self.subTest(pid=pid), patch.object(observer.time, 'monotonic', self.clock), patch.object(observer.subprocess, 'Popen') as popen:
                child = Child(self.clock, [(4, 0)], pid=pid)
                self.assertEqual(self.wait(child), 0)
                popen.assert_not_called()
                self.assertEqual(self.sample_receipt()['skip_reason'], 'missing_typed_pid')

    def test_insufficient_budget_skips_sample_and_preserves_install_result(self):
        with patch.object(observer.time, 'monotonic', self.clock), patch.object(observer.subprocess, 'Popen') as popen:
            child = Child(self.clock, [(45, 'timeout'), (2, 0)])
            self.assertEqual(self.wait(child, deadline=156), 0)
            popen.assert_not_called()
            self.assertEqual(self.sample_receipt()['skip_reason'], 'insufficient_budget')
            self.assertEqual(child.calls[-1], ('wait', 11))

    def test_exact_live_child_sampled_once_without_concurrent_install_reap(self):
        child = Child(self.clock, [(45, 'timeout'), (5, 0)])
        sampler = Child(self.clock, pid=54321)
        def collect(process, deadline, cleanup_deadline, receipt):
            self.assertIs(process, sampler)
            self.assertEqual(deadline, 153)
            self.assertEqual(cleanup_deadline, 155)
            self.assertEqual(child.calls, [('wait', 45), ('poll',)])
            self.clock.value += 3
            receipt.update(outcome='completed', natural_exit=True, returncode=0)
            return receipt, b'owned stack', b'status'
        with patch.object(observer.time, 'monotonic', self.clock), patch.object(observer.subprocess, 'Popen', return_value=sampler) as popen, patch.object(observer, '_collect', side_effect=collect):
            self.assertEqual(self.wait(child), 0)
            popen.assert_called_once_with(['/usr/bin/sample', '12345', '3', '-file', '/dev/stdout'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            self.assertEqual(self.sample_receipt()['sample_attempts'], 1)
            self.assertEqual(child.calls[-1], ('wait', 72))
            self.assertEqual((self.out / 'install-sample.stdout.log').read_bytes(), b'owned stack')

    def test_install_exits_between_wait_and_live_check_without_sampling(self):
        child = Child(self.clock, [(45, 'timeout')])
        def poll():
            child.returncode = 6
            return 6
        child.poll = poll
        with patch.object(observer.time, 'monotonic', self.clock), patch.object(observer.subprocess, 'Popen') as popen:
            self.assertEqual(self.wait(child), 6)
            popen.assert_not_called()

    def test_sampler_spawn_error_does_not_erase_install_success(self):
        with patch.object(observer.time, 'monotonic', self.clock), patch.object(observer.subprocess, 'Popen', side_effect=FileNotFoundError):
            child = Child(self.clock, [(45, 'timeout'), (2, 0)])
            self.assertEqual(self.wait(child), 0)
            receipt = self.sample_receipt()
            self.assertEqual(receipt['outcome'], 'spawn_failed')
            self.assertFalse(receipt['uncertain'])
            self.assertEqual(receipt['install_returncode'], 0)

    def test_sampler_unexpected_spawn_failure_does_not_abandon_install(self):
        with patch.object(observer.time, 'monotonic', self.clock), patch.object(observer.subprocess, 'Popen', side_effect=RuntimeError):
            child = Child(self.clock, [(45, 'timeout'), (2, 9)])
            self.assertEqual(self.wait(child), 9)
            self.assertTrue(self.sample_receipt()['uncertain'])

    def test_collector_initialization_failure_keeps_install_wait(self):
        sampler = Child(self.clock, [(0, -15)], pid=54321)
        with patch.object(observer.time, 'monotonic', self.clock), patch.object(observer.subprocess, 'Popen', return_value=sampler), patch.object(observer, '_collect', side_effect=OSError), patch.object(observer.os, 'killpg') as kill:
            child = Child(self.clock, [(45, 'timeout'), (2, 0)])
            self.assertEqual(self.wait(child), 0)
            self.assertTrue(self.sample_receipt()['uncertain'])
            kill.assert_called_once_with(54321, signal.SIGTERM)

    def test_late_sampler_popen_gives_no_new_diagnostic_time(self):
        sampler = Child(self.clock, pid=54321)
        def spawn(*args, **kwargs):
            self.clock.value = 221
            return sampler
        with patch.object(observer.time, 'monotonic', self.clock), patch.object(observer.subprocess, 'Popen', side_effect=spawn) as popen, patch.object(observer.os, 'killpg') as kill:
            child = Child(self.clock, [(45, 'timeout')])
            with self.assertRaises(subprocess.TimeoutExpired):
                self.wait(child)
            self.assertEqual(len([call for call in child.calls if call[0] == 'wait']), 1)
            popen.assert_called_once()
            kill.assert_not_called()
            receipt = self.sample_receipt()
            self.assertEqual(receipt['outcome'], 'late_spawn')
            self.assertTrue(receipt['uncertain'])
            self.assertEqual(sampler.calls, [])

    def test_sample_completion_after_install_deadline_is_still_failed(self):
        def collect(process, deadline, cleanup_deadline, receipt):
            self.clock.value = 221
            receipt.update(outcome='completed', returncode=0)
            return receipt, b'', b''
        with patch.object(observer.time, 'monotonic', self.clock), patch.object(observer.subprocess, 'Popen', return_value=Child(self.clock)), patch.object(observer, '_collect', side_effect=collect):
            child = Child(self.clock, [(45, 'timeout')])
            with self.assertRaises(subprocess.TimeoutExpired):
                self.wait(child)

    def test_denied_sigterm_does_not_escalate_or_change_routes(self):
        child = Child(self.clock)
        receipt = observer._receipt('device_log', {})
        with patch.object(observer.time, 'monotonic', self.clock), patch.object(observer.os, 'killpg', side_effect=PermissionError) as kill, patch.object(observer.subprocess, 'Popen') as popen:
            observer._cleanup(child, 110, receipt)
            kill.assert_called_once_with(12345, signal.SIGTERM)
            popen.assert_not_called()
            self.assertEqual(receipt['cleanup_outcome'], 'signal_denied')
            self.assertTrue(receipt['uncertain'])
            self.assertFalse(receipt['native_continuation_allowed'])
            self.assertEqual(child.calls, [('poll',)])

    def test_host_only_reap_does_not_prove_group_or_simulator_exit(self):
        child = Child(self.clock, [(1, -15)])
        receipt = observer._receipt('device_log', {})
        with patch.object(observer.time, 'monotonic', self.clock), patch.object(observer.os, 'killpg'):
            observer._cleanup(child, 110, receipt)
        self.assertTrue(receipt['host_child_reaped'])
        self.assertTrue(receipt['uncertain'])
        self.assertFalse(receipt['natural_exit'])
        self.assertFalse(receipt['group_exit_confirmed'])
        self.assertFalse(receipt['native_continuation_allowed'])

    def test_cleanup_uses_one_total_deadline_and_no_unbounded_wait(self):
        child = Child(self.clock, [(5, 'timeout'), (5, 'timeout')])
        receipt = observer._receipt('device_log', {})
        with patch.object(observer.time, 'monotonic', self.clock), patch.object(observer.os, 'killpg') as kill:
            observer._cleanup(child, 110, receipt)
        self.assertEqual(kill.call_count, 2)
        self.assertEqual([call[1] for call in child.calls if call[0] == 'wait'], [5, 5])
        self.assertEqual(self.clock.value, 110)

    def test_capture_error_has_at_most_its_own_cleanup_reserve(self):
        for kind, expected in (('device_log', 110), ('install_sample', 102)):
            receipt = observer._receipt(kind, {})
            child = Child(self.clock)
            with self.subTest(kind=kind), patch.object(observer.time, 'monotonic', self.clock), patch.object(observer, '_cleanup') as cleanup:
                observer._collect(child, 140, 150, receipt)
                self.assertEqual(cleanup.call_args.args[1], expected)

    def python_child(self, code, commands):
        def spawn(command, **kwargs):
            commands.append(command)
            return REAL_POPEN([sys.executable, '-S', '-c', code], **kwargs)
        return spawn

    def test_device_log_drains_both_pipes_while_driver_is_blocked(self):
        commands = []
        code = 'import os,time; os.write(1,b"A"*600000); os.write(2,b"B"*300000); time.sleep(.05)'
        log = observer.DeviceLog(self.out, DEVICE, 'a' * 40, '123', '1', time.monotonic() + 200)
        with patch.object(observer.subprocess, 'Popen', side_effect=self.python_child(code, commands)):
            started = log.start()
            self.assertFalse(started['stream_ready'])
            time.sleep(.15)  # Represents the outer driver blocked in install.
            receipt = log.finish()
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0], ['xcrun', 'simctl', 'spawn', DEVICE, 'log', 'stream', '--style', 'compact', '--level', 'debug', '--timeout', '120', '--predicate', observer.PREDICATE])
        self.assertEqual(receipt['outcome'], 'completed')
        self.assertTrue(receipt['natural_exit'])
        self.assertFalse(receipt['uncertain'])
        self.assertFalse(receipt['stream_ready'])
        self.assertEqual(receipt['stdout_retained_bytes'], 600000)
        self.assertEqual(receipt['stderr_retained_bytes'], 300000)
        with self.assertRaises(RuntimeError):
            log.start()

    def test_output_cap_keeps_partial_evidence_and_stops_native_continuation(self):
        commands = []
        code = 'import os,time; os.write(2,b"prefix\\n"); os.write(1,b"A"*2000000); time.sleep(30)'
        log = observer.DeviceLog(self.out, DEVICE, 'a' * 40, '123', '1', time.monotonic() + 20)
        with patch.object(observer.subprocess, 'Popen', side_effect=self.python_child(code, commands)) as popen:
            log.start()
            receipt = log.finish()
            after_finish = popen.call_count
            log.finish()
            self.assertEqual(popen.call_count, after_finish)
        self.assertEqual(receipt['outcome'], 'byte_limit')
        self.assertTrue(receipt['forced_cleanup'])
        self.assertTrue(receipt['uncertain'])
        self.assertFalse(receipt['native_continuation_allowed'])
        self.assertFalse(receipt['group_exit_confirmed'])
        self.assertEqual(receipt['stdout_retained_bytes'] + receipt['stderr_retained_bytes'], observer.CAP)
        self.assertGreater(receipt['observed_bytes'], observer.CAP)
        self.assertEqual(sum(path.stat().st_size for path in self.out.glob('*.log')), observer.CAP)

    def test_nonzero_spawned_logger_never_authorizes_later_simctl(self):
        commands = []
        log = observer.DeviceLog(self.out, DEVICE, 'a' * 40, '123', '1', time.monotonic() + 20)
        with patch.object(observer.subprocess, 'Popen', side_effect=self.python_child('raise SystemExit(1)', commands)):
            log.start()
            receipt = log.finish()
        self.assertEqual(receipt['outcome'], 'command_failed')
        self.assertEqual(receipt['returncode'], 1)
        self.assertTrue(receipt['natural_exit'])
        self.assertTrue(receipt['uncertain'])
        self.assertFalse(receipt['native_continuation_allowed'])
        self.assertFalse(receipt['simulator_stream_settled'])
        self.assertFalse(receipt['stream_ready'])

    def test_signalled_logger_and_sampler_exits_are_abnormal_and_uncertain(self):
        for kind in ('device_log', 'install_sample'):
            for code in (-15, -9):
                with self.subTest(kind=kind, code=code):
                    child = REAL_POPEN([sys.executable, '-S', '-c',
                                        'import os; os.kill(os.getpid(), ' + str(-code) + ')'],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       start_new_session=True)
                    receipt = observer._receipt(kind, {})
                    receipt['outcome'] = 'running'
                    stopped = []
                    deadline = time.monotonic() + 2
                    receipt, _, _ = observer._collect(child, deadline, deadline + 2, receipt,
                                                      on_stop=lambda value: stopped.append(dict(value)))
                    self.assertEqual(receipt['returncode'], code)
                    self.assertEqual(receipt['outcome'], 'abnormal_exit')
                    self.assertFalse(receipt['natural_exit'])
                    self.assertTrue(receipt['uncertain'])
                    self.assertFalse(receipt['native_continuation_allowed'])
                    self.assertFalse(receipt['simulator_stream_settled'])
                    self.assertFalse(receipt['forced_cleanup'])
                    self.assertEqual(len(stopped), 1)
                    self.assertTrue(stopped[0]['uncertain'])

    def test_nonnegative_sampler_error_is_settled_evidence_failure(self):
        child = REAL_POPEN([sys.executable, '-S', '-c', 'raise SystemExit(1)'],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           start_new_session=True)
        receipt = observer._receipt('install_sample', {})
        receipt['outcome'] = 'running'
        deadline = time.monotonic() + 2
        receipt, _, _ = observer._collect(child, deadline, deadline + 2, receipt)
        self.assertEqual(receipt['returncode'], 1)
        self.assertEqual(receipt['outcome'], 'command_failed')
        self.assertTrue(receipt['natural_exit'])
        self.assertFalse(receipt['uncertain'])
        self.assertTrue(receipt['native_continuation_allowed'])

    def test_capture_preserves_partial_bytes_even_when_cleanup_is_denied(self):
        child = Child(self.clock)
        child.stdout = Mock()
        child.stderr = Mock()
        child.stdout.fileno.return_value = 71
        child.stderr.fileno.return_value = 72
        selector = Mock()
        selector.get_map.return_value = {71: True, 72: True}
        selector.select.return_value = [(Mock(fileobj=child.stdout), 1)]
        receipt = observer._receipt('device_log', {})
        receipt['outcome'] = 'running'
        with patch.object(observer.time, 'monotonic', self.clock), patch.object(observer.selectors, 'DefaultSelector', return_value=selector), patch.object(observer.os, 'set_blocking'), patch.object(observer.os, 'read', side_effect=[b'useful partial bytes', OSError]), patch.object(observer.os, 'killpg', side_effect=PermissionError) as kill, patch.object(observer.subprocess, 'Popen') as popen:
            receipt, stdout, stderr = observer._collect(child, 140, 150, receipt)
            observer._persist(self.out, 'install-device-log', receipt, stdout, stderr)
        self.assertEqual((self.out / 'install-device-log.stdout.log').read_bytes(), b'useful partial bytes')
        self.assertEqual(receipt['cleanup_outcome'], 'signal_denied')
        self.assertTrue(receipt['uncertain'])
        kill.assert_called_once_with(12345, signal.SIGTERM)
        popen.assert_not_called()

    def test_device_log_spawn_failure_is_explicit_without_retry(self):
        log = observer.DeviceLog(self.out, DEVICE, 'a' * 40, '123', '1', time.monotonic() + 200)
        with patch.object(observer.subprocess, 'Popen', side_effect=FileNotFoundError) as popen:
            self.assertEqual(log.start()['outcome'], 'spawn_failed')
            self.assertEqual(log.finish()['outcome'], 'spawn_failed')
            popen.assert_called_once()

    def test_expired_log_budget_never_dispatches(self):
        log = observer.DeviceLog(self.out, DEVICE, 'a' * 40, '123', '1', time.monotonic() - 1)
        with patch.object(observer.subprocess, 'Popen') as popen:
            self.assertEqual(log.start()['outcome'], 'skipped_insufficient_budget')
            log.finish()
            popen.assert_not_called()

    def test_late_log_spawn_is_uncertain_and_has_no_second_native_command(self):
        child = Child(self.clock)
        def spawn(*args, **kwargs):
            self.clock.value = 251
            return child
        with patch.object(observer.time, 'monotonic', self.clock), patch.object(observer.subprocess, 'Popen', side_effect=spawn) as popen, patch.object(observer.os, 'killpg') as kill:
            log = observer.DeviceLog(self.out, DEVICE, 'a' * 40, '123', '1', 300)
            log.start()
            log._thread.join(timeout=1)
            receipt = log.finish()
            popen.assert_called_once()
            kill.assert_not_called()
            self.assertTrue(receipt['uncertain'])
            self.assertEqual(receipt['outcome'], 'late_spawn')
            self.assertEqual(receipt['overall_deadline_monotonic'], 250)

    def test_retention_failure_cannot_erase_install_result(self):
        with patch.object(observer.time, 'monotonic', self.clock), patch.object(Path, 'write_bytes', side_effect=PermissionError):
            child = Child(self.clock, [(1, 0)])
            self.assertEqual(self.wait(child), 0)
            self.assertEqual(self.context['sample_receipt']['retention_error'], 'PermissionError')

    def test_unexpected_retention_exception_cannot_replace_install_success(self):
        with patch.object(observer.time, 'monotonic', self.clock), patch.object(observer, '_persist', side_effect=RuntimeError):
            child = Child(self.clock, [(1, 0)])
            self.assertEqual(self.wait(child), 0)
            self.assertEqual(self.context['sample_receipt']['retention_error'], 'RuntimeError')

    def test_stalled_log_retention_never_holds_finish_lock_past_deadline(self):
        entered = threading.Event()
        release = threading.Event()
        def persist(*args, **kwargs):
            entered.set()
            release.wait(timeout=2)
            return args[2]
        def collect(process, deadline, cleanup_deadline, receipt, **kwargs):
            receipt.update(outcome='completed', natural_exit=True, returncode=0)
            return receipt, b'partial', b''
        with patch.object(observer.time, 'monotonic', self.clock), patch.object(observer.subprocess, 'Popen', return_value=Child(self.clock)), patch.object(observer, '_collect', side_effect=collect), patch.object(observer, '_persist', side_effect=persist):
            log = observer.DeviceLog(self.out, DEVICE, 'a' * 40, '123', '1', 300)
            log.start()
            self.assertTrue(entered.wait(timeout=1))
            self.clock.value = 251
            before = time.perf_counter()
            receipt = log.finish()
            duration = time.perf_counter() - before
            release.set()
            log._thread.join(timeout=1)
        self.assertLess(duration, .2)
        self.assertTrue(receipt['uncertain'])
        self.assertEqual(receipt['outcome'], 'owner_unsettled')
        self.assertTrue(log.uncertain)  # The late writer cannot clear uncertainty.

    def test_log_owner_failure_finalizes_receipt_and_marks_uncertainty(self):
        child = Child(self.clock, [(1, -15)])
        with patch.object(observer.time, 'monotonic', self.clock), patch.object(observer.subprocess, 'Popen', return_value=child) as popen, patch.object(observer, '_collect', side_effect=RuntimeError), patch.object(observer.os, 'killpg') as kill:
            log = observer.DeviceLog(self.out, DEVICE, 'a' * 40, '123', '1', 300)
            log.start()
            receipt = log.finish()
            self.assertTrue(log._done.is_set())
            self.assertTrue(receipt['uncertain'])
            self.assertEqual(receipt['outcome'], 'owner_failed')
            kill.assert_called_once_with(12345, signal.SIGTERM)
            popen.assert_called_once()

    def test_logger_late_spawn_is_flagged_before_drainer_can_run(self):
        class DeferredThread:
            def __init__(self, **kwargs):
                pass
            def start(self):
                pass
        def spawn(*args, **kwargs):
            self.clock.value = 245
            return Child(self.clock)
        with patch.object(observer.time, 'monotonic', self.clock), patch.object(observer.subprocess, 'Popen', side_effect=spawn), patch.object(observer.threading, 'Thread', DeferredThread):
            log = observer.DeviceLog(self.out, DEVICE, 'a' * 40, '123', '1', 300)
            receipt = log.start()
            self.assertTrue(receipt['uncertain'])
            self.assertEqual(receipt['outcome'], 'late_spawn')

    def test_log_uncertainty_is_published_before_cleanup_wait(self):
        entered = threading.Event()
        release = threading.Event()
        def cleanup(process, deadline, receipt):
            entered.set()
            release.wait(timeout=2)
            receipt['cleanup_outcome'] = 'signal_denied'
        child = Child(self.clock)
        with patch.object(observer.time, 'monotonic', self.clock), patch.object(observer.subprocess, 'Popen', return_value=child), patch.object(observer, '_cleanup', side_effect=cleanup):
            log = observer.DeviceLog(self.out, DEVICE, 'a' * 40, '123', '1', 300)
            log.start()  # BytesIO has no fileno; capture stops before cleanup.
            self.assertTrue(entered.wait(timeout=1))
            self.assertTrue(log.uncertain)
            release.set()
            receipt = log.finish()
            self.assertFalse(receipt['native_continuation_allowed'])

    def fence_log(self):
        log = observer.DeviceLog(self.out, DEVICE, 'a' * 40, '123', '1', 300)
        log._started = True
        log._end = 250
        log._receipt['outcome'] = 'running'
        return log

    def test_uncertainty_published_before_dispatch_refuses_callback(self):
        log = self.fence_log()
        receipt = log._snapshot()
        observer._uncertain(receipt, 'test_collector_failed')
        log._publish(receipt)
        callback = Mock()
        with patch.object(observer.time, 'monotonic', self.clock):
            with self.assertRaises(observer.ObserverDispatchRefused) as error:
                log.spawn_if_certain(callback, 220, lambda: False)
        self.assertEqual(error.exception.reason, 'observer_uncertain')
        callback.assert_not_called()

    def test_later_uncertainty_does_not_block_publication_behind_started_popen(self):
        log = self.fence_log()
        entered = threading.Event()
        release = threading.Event()
        completed = []
        def callback():
            entered.set()
            release.wait(timeout=2)
            return 'already_dispatched'
        def run():
            completed.append(log.spawn_if_certain(callback, time.monotonic() + 2, lambda: False))
        thread = threading.Thread(target=run)
        thread.start()
        self.assertTrue(entered.wait(timeout=1))
        receipt = log._snapshot()
        observer._uncertain(receipt, 'test_collector_failed')
        before = time.perf_counter()
        log._publish(receipt)
        self.assertTrue(log.uncertain)
        self.assertTrue(log._pending_stop.is_set())
        self.assertFalse(log._uncertainty.is_set())
        log._done.set()
        self.assertTrue(log.finish()['uncertain'])
        self.assertLess(time.perf_counter() - before, .2)
        release.set()
        thread.join(timeout=1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(completed, ['already_dispatched'])
        later = Mock()
        with self.assertRaises(observer.ObserverDispatchRefused):
            log.spawn_if_certain(later, time.monotonic() + 2, lambda: False)
        later.assert_not_called()

    def test_uncertainty_publication_takes_shared_transition_lock_when_free(self):
        log = self.fence_log()
        receipt = log._snapshot()
        observer._uncertain(receipt, 'test_collector_failed')
        original_set = log._uncertainty.set
        checked = []
        def set_while_locked():
            checked.append(log._dispatch_lock.locked())
            original_set()
        with patch.object(log._uncertainty, 'set', side_effect=set_while_locked):
            log._publish(receipt)
        self.assertEqual(checked, [True])
        self.assertFalse(log._dispatch_lock.locked())
        self.assertTrue(log._uncertainty.is_set())
        self.assertFalse(log._pending_stop.is_set())

    def test_busy_transition_lock_publishes_pending_stop_before_cleanup(self):
        log = self.fence_log()
        log._dispatch_lock.acquire()
        child = Child(self.clock)
        receipt = observer._receipt('device_log', {})
        receipt['outcome'] = 'running'
        seen = []
        def cleanup(process, deadline, value):
            seen.append((log.uncertain, log._pending_stop.is_set(), log._uncertainty.is_set()))
        before = time.perf_counter()
        try:
            with patch.object(observer.time, 'monotonic', self.clock), patch.object(observer, '_cleanup', side_effect=cleanup):
                observer._collect(child, 140, 150, receipt, on_stop=log._publish)
            self.assertLess(time.perf_counter() - before, .2)
            self.assertEqual(seen, [(True, True, False)])
            self.assertTrue(log._snapshot()['uncertain'])
        finally:
            log._dispatch_lock.release()
        callback = Mock()
        with patch.object(observer.time, 'monotonic', self.clock):
            with self.assertRaises(observer.ObserverDispatchRefused) as error:
                log.spawn_if_certain(callback, 220, lambda: False)
        self.assertEqual(error.exception.reason, 'observer_uncertain')
        self.assertTrue(log._pending_stop.is_set())
        callback.assert_not_called()

    def test_dispatch_lock_acquisition_is_bounded_by_original_deadline(self):
        log = self.fence_log()
        log._dispatch_lock.acquire()
        callback = Mock()
        started = time.monotonic()
        try:
            with self.assertRaises(observer.ObserverDispatchRefused) as error:
                log.spawn_if_certain(callback, started + .02, lambda: False)
        finally:
            log._dispatch_lock.release()
        self.assertEqual(error.exception.reason, 'deadline_expired')
        self.assertLess(time.monotonic() - started, .2)
        callback.assert_not_called()

    def test_expired_and_cancelled_dispatch_never_calls_popen(self):
        for deadline, cancelled, reason in ((100, False, 'deadline_expired'),
                                            (220, True, 'cancelled')):
            log = self.fence_log()
            callback = Mock()
            with self.subTest(reason=reason), patch.object(observer.time, 'monotonic', self.clock):
                with self.assertRaises(observer.ObserverDispatchRefused) as error:
                    log.spawn_if_certain(callback, deadline, lambda: cancelled)
            self.assertEqual(error.exception.reason, reason)
            callback.assert_not_called()

    def test_sample_after_logger_uncertainty_is_skipped_but_install_zero_survives(self):
        log = self.fence_log()
        receipt = log._snapshot()
        observer._uncertain(receipt, 'test_logger_failed_after_install_dispatch')
        log._publish(receipt)
        self.context.update(device_log=log, cancelled=lambda: False)
        child = Child(self.clock, [(45, 'timeout'), (2, 0)])
        with patch.object(observer.time, 'monotonic', self.clock), patch.object(observer.subprocess, 'Popen') as popen:
            self.assertEqual(self.wait(child), 0)
        popen.assert_not_called()
        receipt = self.sample_receipt()
        self.assertEqual(receipt['outcome'], 'skipped_uncertain')
        self.assertEqual(receipt['sample_attempts'], 0)
        self.assertTrue(receipt['uncertain'])
        self.assertEqual(receipt['install_returncode'], 0)
        self.assertEqual(receipt['install_return_monotonic'], 147)

    def test_sample_after_cancellation_is_skipped_without_fake_install_timeout(self):
        self.context.update(device_log=self.fence_log(), cancelled=lambda: True)
        child = Child(self.clock, [(45, 'timeout'), (2, 0)])
        with patch.object(observer.time, 'monotonic', self.clock), patch.object(observer.subprocess, 'Popen') as popen:
            self.assertEqual(self.wait(child), 0)
        popen.assert_not_called()
        receipt = self.sample_receipt()
        self.assertEqual(receipt['outcome'], 'skipped_cancelled')
        self.assertEqual(receipt['sample_attempts'], 0)
        self.assertEqual(receipt['install_returncode'], 0)
        self.assertEqual(receipt['install_return_monotonic'], 147)

    def test_log_timeout_fits_remaining_install_deadline_and_cleanup(self):
        for deadline, expected_timeout in ((220, 105), (400, 120), (115.9, None), (116, 1)):
            with self.subTest(deadline=deadline), patch.object(observer.time, 'monotonic', self.clock), patch.object(observer.subprocess, 'Popen', side_effect=FileNotFoundError) as popen:
                log = observer.DeviceLog(self.out, DEVICE, 'a' * 40, '123', '1', deadline)
                receipt = log.start()
                if expected_timeout is None:
                    self.assertEqual(receipt['outcome'], 'skipped_insufficient_budget')
                    popen.assert_not_called()
                else:
                    command = popen.call_args.args[0]
                    self.assertEqual(command[command.index('--timeout') + 1], str(expected_timeout))
                    self.assertEqual(receipt['stream_timeout_seconds'], expected_timeout)
                    self.assertLessEqual(receipt['overall_deadline_monotonic'], deadline)
                    self.assertLessEqual(100 + expected_timeout + 5 + observer.LOG_CLEANUP_SECONDS,
                                         receipt['overall_deadline_monotonic'])

    def test_install_observation_time_precedes_late_receipt_io(self):
        def persist(out, stem, receipt, *args):
            self.clock.value = 300
            return receipt
        with patch.object(observer.time, 'monotonic', self.clock), patch.object(observer, '_persist', side_effect=persist):
            self.assertEqual(self.wait(Child(self.clock, [(2, 0)])), 0)
        receipt = self.context['sample_receipt']
        self.assertEqual(receipt['install_return_monotonic'], 102)
        self.assertEqual(receipt['install_returncode'], 0)
        self.assertEqual(self.clock.value, 300)

    def test_import_is_safe_without_native_or_subprocess_dispatch(self):
        import importlib
        with patch.object(observer.subprocess, 'Popen') as popen:
            importlib.reload(observer)
            popen.assert_not_called()

    def test_no_process_inventory_pid_recovery_or_crash_roots(self):
        source = Path(observer.__file__).read_text()
        for forbidden in ('pgrep', "['ps'", 'DiagnosticReports', '--pid-input', 'os.system', 'shell=True'):
            self.assertNotIn(forbidden, source)


if __name__ == '__main__':
    unittest.main()
