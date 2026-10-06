#!/usr/bin/env python3
"""Portable fixed-route bootstrap admission and real owned-process cleanup."""
import ast
import contextlib
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
from unittest.mock import patch

import uikit_full_shipping_gate as gate


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'Scripts/probe_photos_bootstrap.py'
DEVICE = '12345678-1234-1234-1234-123456789AB0'


def load_functions(folder, full_row=True):
    """Never import bootstrap's top-level simulator/Photos program."""
    parsed = ast.parse(SOURCE.read_text(), filename=str(SOURCE))
    definitions = ast.Module(body=[node for node in parsed.body if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef))], type_ignores=[])
    namespace = {'__file__': str(SOURCE), 'full_row': full_row,
                 'evidence_root': Path(folder), 'device': DEVICE}
    exec(compile(definitions, str(SOURCE), 'exec'), namespace)
    return namespace


def environment(folder):
    branch = 'refs/heads/codex/uikit-full-shipping'
    return {'PATH': os.environ.get('PATH', ''), 'PYTHONPATH': str(ROOT / 'Scripts'),
            'PYTHONDONTWRITEBYTECODE': '1', 'RUNNER_TEMP': str(folder),
            'GITHUB_REPOSITORY': '100mango/Celluloid', 'GITHUB_EVENT_NAME': 'push',
            'GITHUB_REF': branch,
            'GITHUB_WORKFLOW_REF': '100mango/Celluloid/.github/workflows/uikit-full-shipping.yml@' + branch,
            'GITHUB_SHA': 'a' * 40, 'GITHUB_WORKFLOW_SHA': 'a' * 40,
            'GITHUB_RUN_ID': '1234567', 'GITHUB_RUN_ATTEMPT': '1',
            'CELLULOID_VALIDATION_SCOPE': 'uikit-full-shipping', 'CELLULOID_FULL_ROW': 'compact-phone'}


def write_clock(folder):
    clock = {'schema': gate.CLOCK_SCHEMA, 'source_sha': 'a' * 40, 'run_id': '1234567',
             'run_attempt': '1', 'row': 'compact-phone', 'started_monotonic': time.monotonic(),
             'started_unix': time.time(), 'execution_budget_seconds': gate.EXECUTION_SECONDS}
    (Path(folder) / 'full-shipping-clock.json').write_text(json.dumps(clock))


class BootstrapAdapterTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.temp = Path(temporary.name)
        self.functions = load_functions(self.temp)

    def test_ast_loading_never_dispatches_top_level_work(self):
        with patch('subprocess.run', side_effect=AssertionError('top-level dispatch')):
            functions = load_functions(self.temp)
        self.assertIn('run', functions)
        self.assertNotIn('options', functions)
        self.assertFalse((self.temp / 'bootstrap-evidence').exists())

    def test_full_route_preserves_argv_and_original_ceiling_without_outer_wrapper(self):
        args = ('xcrun', 'simctl', 'addmedia', DEVICE, '/tmp/celluloid-fixture.png')
        events = []
        self.functions['require_inner_allowance'] = lambda seconds: events.append(('allowance', seconds))
        self.functions['check_inner_completion'] = lambda: events.append(('completion',))
        def owned_run(command, **kwargs):
            events.append(('dispatch',))
            self.assertEqual(command, args)
            self.assertEqual(kwargs, {'timeout': 480, 'check': False, 'echo': False, 'log_name': 'bootstrap-import-0.log'})
            return subprocess.CompletedProcess(command, 0, 'actual stdout', 'actual stderr')
        with patch('native_process.run', side_effect=owned_run), patch('subprocess.run', side_effect=AssertionError('outer wrapper dispatched')), contextlib.redirect_stdout(io.StringIO()):
            result = self.functions['run']('import-0', 480, *args)
        self.assertEqual(result, (0, 'actual stdout\nactual stderr'))
        self.assertEqual(events, [('allowance', 480), ('dispatch',), ('completion',)])

    def test_original_full_row_false_retains_exact_run_bounded_invocation(self):
        functions = load_functions(self.temp, full_row=False)
        args = ('xcrun', 'simctl', 'addmedia', DEVICE, '/tmp/celluloid-fixture.png')
        with patch('subprocess.run', return_value=subprocess.CompletedProcess([], 124, 'original output')) as run, patch('native_process.run', side_effect=AssertionError('new adapter used for canonical route')), contextlib.redirect_stdout(io.StringIO()):
            code, output = functions['run']('import-0', 480, *args)
        run.assert_called_once_with([sys.executable, 'Scripts/run_bounded.py', '--seconds', '480', '--label', 'import-0', *args],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.assertEqual((code, output), (124, 'original output'))
        self.assertEqual((self.temp / 'bootstrap-import-0.log').read_text(), 'original output')

    def test_original_allowance_plus_fifteen_seconds_must_fit_before_dispatch(self):
        for remaining in (494.99, 480, 15, 0, -1):
            self.functions['row_clock'] = lambda: ({}, {}, {'work_remaining_seconds': remaining})
            with self.subTest(remaining=remaining), patch('native_process.run') as dispatch, self.assertRaisesRegex(TimeoutError, 'no dispatch'):
                self.functions['run']('import-0', 480, 'xcrun', 'simctl', 'addmedia', DEVICE, 'fixture.png')
            dispatch.assert_not_called()
        self.functions['row_clock'] = lambda: ({}, {}, {'work_remaining_seconds': 495})
        self.functions['require_inner_allowance'](480)

    def test_successful_command_finishing_late_is_rejected(self):
        write_clock(self.temp)
        context = {'source_sha': 'a' * 40, 'run_id': '1234567', 'run_attempt': '1', 'row': 'compact-phone'}
        clock = json.loads((self.temp / 'full-shipping-clock.json').read_text())
        clock['started_monotonic'] = time.monotonic() - gate.WORK_SECONDS - 1
        self.functions['require_inner_allowance'] = lambda seconds: None
        self.functions['row_clock'] = lambda: (clock, context, {'work_remaining_seconds': -1})
        with patch('native_process.run', return_value=subprocess.CompletedProcess([], 0, 'late success', '')), self.assertRaisesRegex(ValueError, 'Late UIKit phase completion'):
            self.functions['run']('readiness-before-import', 360, 'xcodebuild')

    def test_timeout_raises_immediately_preserving_partial_log_and_no_later_dispatch(self):
        self.functions['require_inner_allowance'] = lambda seconds: None
        self.functions['check_inner_completion'] = lambda: self.fail('completion check ran after timeout')
        (self.temp / 'bootstrap-import-0.log').write_text('retained partial operation output\n')
        output = io.StringIO()
        with patch('native_process.run', side_effect=TimeoutError('owned group timeout')) as dispatch, contextlib.redirect_stdout(output):
            with self.assertRaises(TimeoutError):
                for index in range(2):
                    self.functions['run']('import-' + str(index), 480, 'xcrun', 'simctl', 'addmedia', DEVICE, 'fixture.png')
        self.assertEqual(dispatch.call_count, 1)
        self.assertIn('retained partial operation output', output.getvalue())

    def test_optional_host_probes_are_withheld_below_630_seconds(self):
        for remaining in (629.99, 30, 0, -1):
            self.functions['row_clock'] = lambda: ({}, {}, {'work_remaining_seconds': remaining})
            output = io.StringIO()
            with self.subTest(remaining=remaining), patch('subprocess.run') as run, contextlib.redirect_stdout(output):
                self.functions['host']('before-import')
            run.assert_not_called()
            self.assertIn('BOOTSTRAP_OPTIONAL_HOST_WITHHELD', output.getvalue())

    def test_host_probes_at_boundary_retain_individual_allowance_and_postchecks(self):
        self.functions['row_clock'] = lambda: ({}, {}, {'work_remaining_seconds': 630})
        allowances = []
        completions = []
        self.functions['require_inner_allowance'] = allowances.append
        self.functions['check_inner_completion'] = lambda: completions.append(True)
        with patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0, '', '')) as run, contextlib.redirect_stdout(io.StringIO()):
            self.functions['host']('before-import')
        self.assertEqual(allowances, [15] * 5)
        self.assertEqual(len(completions), 5)
        self.assertEqual([call.args[0] for call in run.call_args_list],
                         [['vm_stat'], ['memory_pressure', '-Q'], ['sysctl', 'vm.swapusage'], ['df', '-h', '.'], ['ps', '-axo', 'pid=,ppid=,rss=,comm=']])
        self.assertTrue(all(call.kwargs['timeout'] == 15 for call in run.call_args_list))

    def test_readiness_probe_keeps_original_method_destination_and_360_second_cap(self):
        calls = []
        def run(*args):
            calls.append(args)
            return 0, 'PHOTOS_LIBRARY_READINESS {"synthetic": []}\n'
        self.functions['run'] = run
        self.assertEqual(self.functions['test']('readiness-before-import', 'testPhotosLibraryBootstrapReadiness'), {'synthetic': []})
        self.assertEqual(calls, [('readiness-before-import', 360, 'xcodebuild', '-project', 'Celluloid.xcodeproj',
            '-scheme', 'Celluloid', '-configuration', 'Debug', '-destination', 'platform=iOS Simulator,id=' + DEVICE,
            '-derivedDataPath', '.build', '-resultBundlePath', str(self.temp / 'Bootstrap-readiness-before-import.xcresult'),
            '-parallel-testing-enabled', 'NO', '-collect-test-diagnostics', 'never',
            '-only-testing:CelluloidTests/EditorRegressionTests/testPhotosLibraryBootstrapReadiness',
            'test-without-building', 'CODE_SIGNING_ALLOWED=NO')])


@unittest.skipUnless(os.name == 'posix', 'Owned process groups require POSIX')
class ActualOwnedCleanupTests(unittest.TestCase):
    def test_term_ignoring_descendant_with_open_stdout_is_killed_before_timeout_raises(self):
        with tempfile.TemporaryDirectory() as folder:
            temp = Path(folder)
            processes = temp / 'owned-processes.json'
            driver = r'''
import json, os, pathlib, sys
from test_uikit_full_shipping_bootstrap import load_functions, write_clock
root = pathlib.Path(sys.argv[1])
write_clock(root)
functions = load_functions(root)
descendant = "import os, signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('DESCENDANT_READY', os.getpid(), flush=True); time.sleep(60)"
child = "import json, os, pathlib, subprocess, sys, time; p=subprocess.Popen([sys.executable,'-u','-c'," + repr(descendant) + "]); pathlib.Path(" + repr(str(root/'owned-processes.json')) + ").write_text(json.dumps({'parent':os.getpid(),'descendant':p.pid,'group':os.getpgrp()})); print('OWNED_CHILD_READY',os.getpid(),flush=True); time.sleep(60)"
try:
    functions['run']('owned-tree', .5, sys.executable, '-u', '-c', child)
    (root/'forbidden-next-command').write_text('timeout unexpectedly returned')
    functions['run']('unexpected-next', .5, sys.executable, '-c', 'print("unexpected next command")')
except TimeoutError:
    print('OWNED_TIMEOUT_RAISED', flush=True)
else:
    raise RuntimeError('Owned process timeout did not raise')
'''
            started = time.monotonic()
            try:
                # This supervisor only bounds the portable test itself. The
                # route adapter directly owns its command and process group.
                result = subprocess.run([sys.executable, '-u', '-c', driver, str(temp)],
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                        env=environment(temp), timeout=20)
                elapsed = time.monotonic() - started
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertLess(elapsed, 20)
                self.assertGreaterEqual(elapsed, 10)
                self.assertIn('OWNED_TIMEOUT_RAISED', result.stdout)
                self.assertFalse((temp / 'forbidden-next-command').exists())
                partial = (temp / 'bootstrap-owned-tree.log').read_text()
                self.assertIn('OWNED_CHILD_READY', partial)
                self.assertIn('DESCENDANT_READY', partial)
                timing = json.loads((temp / 'bootstrap-owned-tree.log.timing.json').read_text())
                self.assertIs(timing['timed_out'], True)
                self.assertEqual(timing['timeout_seconds'], .5)
                self.assertGreaterEqual(timing['elapsed_seconds'], 10)
                self.assertLess(timing['elapsed_seconds'], 16)
                owned = json.loads(processes.read_text())
                self.assertEqual(owned['group'], owned['parent'])
                # A killed orphan may briefly remain a zombie until its new
                # parent reaps it; a live process would still retain the pipe.
                for pid in (owned['parent'], owned['descendant']):
                    state = subprocess.run(['ps', '-o', 'stat=', '-p', str(pid)], capture_output=True, text=True, timeout=1)
                    self.assertTrue(state.returncode != 0 or not state.stdout.strip() or state.stdout.strip().startswith('Z'), state.stdout)
            finally:
                # Only the process group recorded by this test is eligible for
                # emergency cleanup after a failing outer test-harness bound.
                if processes.is_file():
                    owned = json.loads(processes.read_text())
                    if owned['group'] == owned['parent'] and owned['group'] != os.getpgrp():
                        try: os.killpg(owned['group'], signal.SIGKILL)
                        except ProcessLookupError: pass


if __name__ == '__main__':
    unittest.main()
