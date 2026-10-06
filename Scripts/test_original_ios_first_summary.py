"""Executable boundaries for the one staged first-summary allocation."""
import contextlib
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
from unittest.mock import patch

import original_ios_first_summary as first
import original_ios_process_guard as guard
from test_original_ios_process_guard import environment

ROOT = Path(__file__).resolve().parents[1]


class FirstSummaryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(); self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.env = patch.dict(os.environ, environment(self.root), clear=True)
        self.env.start(); self.addCleanup(self.env.stop)
        self.context = guard.staged_context()
        self.clock = {'schema': 'Celluloid.UIKitFullShippingClock.1', **self.context,
                      'started_monotonic': 1000., 'started_unix': 100000., 'execution_budget_seconds': 3360}
        (self.root / 'full-shipping-clock.json').write_text(json.dumps(self.clock))
        self.command = ['/bin/bash', '-c', 'xcrun xcresulttool get test-results summary --path "$1" > "$2"',
                        '--', 'TestResults-units.xcresult', str(self.root / 'units.summary.json')]
        with patch.object(first.time, 'monotonic', return_value=1100.), patch.object(first.time, 'time', return_value=100100.):
            first.start()

    def bound(self, started=1200.):
        with patch.object(first.time, 'time', return_value=101000.):
            return first.admission(self.command, 'units summary', 90., started)

    def test_original_units_and_later_summary_limits_and_finite_full_reserve(self):
        from uikit_full_shipping_gate import WORK_CEILINGS
        self.assertEqual(WORK_CEILINGS['units'], 900); self.assertEqual(WORK_CEILINGS['summary'], 30)
        bound = self.bound(2020.)
        self.assertEqual(bound['command_deadline'], 2110.)
        self.assertEqual(bound['cleanup_deadline'], 2120.)
        self.assertEqual(bound['enclosing_deadline'], 2120.)
        with self.assertRaises(ValueError): self.bound(2020.001)
        phase = json.loads((self.root / first.PHASE_FILE).read_text()); phase['started_monotonic'] = 3000.
        (self.root / first.PHASE_FILE).write_text(json.dumps(phase))
        self.assertEqual(self.bound(3600.)['cleanup_deadline'], 3700.)
        with self.assertRaises(ValueError): self.bound(3600.001)

    def test_wrong_source_duplicate_malformed_and_command_are_not_dispatched(self):
        path = self.root / first.PHASE_FILE; original = path.read_text()
        for key, value in [('source_sha', 'b'*40), ('row', 'large-ipad'), ('phase_seconds', True),
                           ('started_monotonic', float('nan')), ('started_unix', float('inf'))]:
            changed = json.loads(original); changed[key] = value; path.write_text(json.dumps(changed))
            with self.subTest(key=key), self.assertRaises((ValueError, guard.GuardRefusal)): self.bound()
        path.write_text(original)
        with patch.object(first.time, 'time', return_value=101000.):
            for changed in [self.command[:-1]+['/tmp/foreign'], ['xcrun', 'simctl', 'list']]:
                with self.assertRaises(ValueError): first.admission(changed, 'units summary', 90., 1200.)
        (self.root / first.OBSERVATION_FILE).write_text('{}')
        with self.assertRaises(ValueError): self.bound()

    def test_original_thirty_second_metric_is_retained_without_relabelling(self):
        bound = self.bound()
        with contextlib.redirect_stdout(io.StringIO()): row = first.record(bound, 0, 1240.)
        self.assertTrue(row['original_threshold_exceeded']); self.assertEqual(row['original_threshold_seconds'], 30)
        self.assertFalse(row['acceptance']); self.assertEqual(row['exit_code'], 0)
        self.assertEqual(first.verify(self.root, self.context, self.clock), row)
        for key, value in [('exit_code', 124), ('source_sha', 'b'*40), ('original_threshold_exceeded', False),
                           ('cleanup_deadline_monotonic', 1290.), ('ended_monotonic', 1291.),
                           ('elapsed_seconds_including_cleanup', float('nan'))]:
            changed = dict(row, **{key: value})
            (self.root/first.OBSERVATION_FILE).write_text(json.dumps(changed))
            with self.subTest(key=key), self.assertRaises(ValueError): first.verify(self.root,self.context,self.clock)

    def execute(self, *, late_spawn=False, denied=False, late_cleanup=False, late_success=False):
        now = [1200.]; calls = []
        class Child:
            pid = 31415
            returncode = None
            def poll(self): return self.returncode
            def wait(self, timeout):
                calls.append(('wait', timeout))
                if len([x for x in calls if x[0] == 'wait']) == 1:
                    now[0] = 1291.
                    if late_success:
                        self.returncode = 0; return 0
                    raise subprocess.TimeoutExpired('owned-summary', timeout)
                now[0] = 1301. if late_cleanup else 1292.
                self.returncode = -15; return -15
        child = Child()
        def spawn(*args, **kwargs):
            calls.append(('spawn', kwargs)); self.assertTrue(kwargs['start_new_session'])
            if late_spawn: now[0] = 1301.
            return child
        def killpg(pid, sig):
            calls.append(('signal', sig)); self.assertEqual(pid, 31415)
            if denied: raise PermissionError(1, 'owned group denied')
        argv = ['run_bounded.py', '--original-ios-first-summary', '--seconds', '90', '--label', 'units summary', *self.command]
        with patch.object(sys, 'argv', argv), patch('time.monotonic', side_effect=lambda: now[0]), patch('time.time', return_value=101000.), patch('subprocess.Popen', side_effect=spawn), patch('os.killpg', side_effect=killpg), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as raised: runpy.run_path(str(ROOT/'Scripts/run_bounded.py'), run_name='__main__')
        self.assertEqual(raised.exception.code, 124)
        failure = guard.read_failure(self.root, self.context)
        self.assertEqual(failure['failure_kind'], 'timeout'); self.assertFalse(failure['cleanup']['group_exit_confirmed'])
        with self.assertRaises(guard.GuardRefusal): guard.require_clear(self.root, self.context)
        return calls, failure

    def test_timeout_keeps_guard_and_cleanup_within_absolute_reserve(self):
        calls, failure = self.execute()
        self.assertEqual(failure['cleanup']['status'], 'child_reaped')
        self.assertEqual([x[1] for x in calls if x[0]=='signal'], [signal.SIGTERM])
        self.assertTrue(all(0 < x[1] <= 5 for x in calls if x[0]=='wait' and x[1] <= 5))

    def test_denial_never_tries_second_signal(self):
        calls, failure = self.execute(denied=True)
        self.assertEqual(failure['cleanup']['status'], 'signal_denied')
        self.assertEqual([x[1] for x in calls if x[0]=='signal'], [signal.SIGTERM])

    def test_late_spawn_does_not_begin_wait_or_extend_cleanup(self):
        calls, failure = self.execute(late_spawn=True)
        self.assertEqual([x[0] for x in calls], ['spawn'])
        self.assertEqual(failure['cleanup']['status'], 'bounded_cleanup_expired')

    def test_late_successful_command_wait_is_timeout_not_success(self):
        calls, failure = self.execute(late_success=True)
        self.assertEqual(failure['cleanup']['child_returncode'], 0)
        self.assertEqual([x[0] for x in calls], ['spawn', 'wait'])

    def test_owner_setup_cannot_move_command_deadline_or_start_late_child(self):
        now=[1200.]; original=guard.OwnedCommand
        def slow_owner(*args,**kwargs):
            owner=original(*args,**kwargs);now[0]=1291.;return owner
        argv=['run_bounded.py','--original-ios-first-summary','--seconds','90','--label','units summary',*self.command]
        with patch.object(sys,'argv',argv),patch('time.monotonic',side_effect=lambda:now[0]),patch('time.time',return_value=101000.),patch.object(guard,'OwnedCommand',side_effect=slow_owner),patch('subprocess.Popen',side_effect=AssertionError('late child forbidden')) as spawn,contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(subprocess.TimeoutExpired):runpy.run_path(str(ROOT/'Scripts/run_bounded.py'),run_name='__main__')
        spawn.assert_not_called()
        self.assertEqual(guard.read_failure(self.root,self.context)['failure_kind'],'timeout')

    def test_late_successful_cleanup_wait_remains_unconfirmed(self):
        calls, failure = self.execute(late_cleanup=True)
        self.assertEqual(failure['cleanup']['status'], 'bounded_cleanup_expired')
        self.assertFalse(json.loads((self.root/first.OBSERVATION_FILE).read_text())['within_cleanup_deadline'])


if __name__ == '__main__': unittest.main()
