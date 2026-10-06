#!/usr/bin/env python3
"""Original shipping UIKit accounting: identities, failures, and real deadlines."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

import uikit_full_shipping_gate as gate
from platform_rendering_contract import RUNTIME_BUILD


SOURCE = 'a' * 40
DEVICE = '11111111-2222-3333-4444-555555555555'


def context(row='compact-phone'):
    return {'source_sha': SOURCE, 'run_id': '1234567', 'run_attempt': '1', 'row': row}


def clock(row='compact-phone'):
    return {'schema': gate.CLOCK_SCHEMA, **context(row), 'started_monotonic': 10_000.0,
            'started_unix': 100_000.0, 'execution_budget_seconds': 3360}


def manifest(row='compact-phone'):
    return {'schema': gate.EXECUTION_SCHEMA, **context(row),
            'device': {'id': DEVICE, 'model': gate.ROWS[row]},
            'phases': [{'name': name, 'exit_code': 0} for name in gate.expected_phases(row)],
            'prerequisites': {key: 'success' for key in gate.expected_prerequisites(row)}}


def execution(cases, row='compact-phone', start=100_010.0):
    raw = ''.join(f"Test Case '{name}' started.\nTest Case '{name}' passed (0.1 seconds).\n" for name in cases)
    raw += f'Executed {len(cases)} tests, with 0 failures (0 unexpected)\n** TEST EXECUTE SUCCEEDED **\n'
    counts = {'passedTests': len(cases), 'failedTests': 0, 'skippedTests': 0, 'expectedFailures': 0}
    summary = {'result': 'Passed', 'totalTestCount': len(cases), **counts, 'testFailures': [],
               'startTime': start, 'finishTime': start + 1.0,
               'devicesAndConfigurations': [{'device': {'deviceId': DEVICE, 'modelName': gate.ROWS[row],
                   'platform': 'iOS Simulator', 'osVersion': '27.0', 'osBuildNumber': RUNTIME_BUILD,
                   'architecture': 'arm64'}, **counts}]}
    return raw, summary


def write_execution(root, row='compact-phone'):
    for index, (phase, cases) in enumerate(gate.expected_cases(row).items()):
        raw, summary = execution(cases, row, 100_010.0 + index * 10)
        raw_name, summary_name = gate.phase_files(phase)
        (root / raw_name).write_text(raw)
        (root / summary_name).write_text(json.dumps(summary))


def verify(root, value=None, row='compact-phone', **kwargs):
    return gate.verify_manifest(value or manifest(row), root, context(row), clock(row),
                                now_monotonic=13_000.0, now_unix=103_000.0, **kwargs)


class SourceInventoryTests(unittest.TestCase):
    def test_fixed_named_inventory_and_all_four_original_rows(self):
        self.assertEqual(len(gate.source_inventory()), 106)
        for row, count in gate.ROW_COUNTS.items():
            with self.subTest(row=row):
                phases = gate.expected_cases(row)
                self.assertEqual(sum(map(len, phases.values())), count)
                self.assertEqual(len(phases['units']), 86)
                self.assertEqual(len(phases['photos-integration']), 4)
                self.assertEqual(len(phases['ui']), 8)
                self.assertIn('-[CelluloidTests.FilterTests testExifOrientationIsAppliedExactlyOnce]', phases['units'])
                self.assertNotIn('-[CelluloidTests.AdjustmentDataTests testExifOrientationIsAppliedExactlyOnce]', phases['units'])
                self.assertIn('-[CelluloidTests.MacPhotosManufacturedAdjustmentTests testManufacturedMacArchiveThroughOriginalUIKitReaderAndCompositor]', phases['units'])
        self.assertEqual(gate.expected_phases('small-ipad'),
                         ['units', 'bootstrap-readiness', 'bootstrap-reconcile', 'photos-integration', 'ui'])
        self.assertEqual(gate.phase_files('bootstrap-readiness'),
                         ('bootstrap-readiness-before-import.log', 'bootstrap-readiness-before-import.summary.json'))

    def test_same_count_substitution_owner_change_or_extra_file_rejects(self):
        for mutation in ('rename-method', 'rename-owner', 'add-file', 'delete-file', 'symlink'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                for name in gate.SOURCE_HASHES:
                    dest = root / name
                    dest.parent.mkdir(exist_ok=True)
                    shutil.copyfile(gate.ROOT / name, dest)
                path = root / 'CelluloidTests/AdjustmentDataTests.swift'
                if mutation == 'rename-method':
                    path.write_text(path.read_text().replace('testExifOrientationIsAppliedExactlyOnce', 'testReplacementSameCount'))
                elif mutation == 'rename-owner':
                    path.write_text(path.read_text().replace('class FilterTests:', 'class DifferentTests:'))
                elif mutation == 'add-file':
                    (root / 'CelluloidTests/Unexpected.swift').write_text('import XCTest\n')
                elif mutation == 'delete-file':
                    path.unlink()
                else:
                    path.unlink()
                    path.symlink_to(gate.ROOT / 'CelluloidTests/AdjustmentDataTests.swift')
                with self.assertRaises(ValueError):
                    gate.source_inventory(root)


class PhaseAccountingTests(unittest.TestCase):
    def phase(self, cases=None):
        inventory = gate.expected_cases('compact-phone')['ui']
        return execution(cases if cases is not None else inventory)

    def validate(self, raw, summary):
        return gate.validate_phase('compact-phone', 'ui', raw, summary, manifest()['device'])

    def test_one_original_ui_execution_passes(self):
        result = self.validate(*self.phase())
        self.assertEqual(result['case_count'], 8)
        self.assertTrue(result['runtime_binding']['aggregate_execution_passed'])
        self.assertEqual(result['raw_execution_accounting']['case_counts'], {'passed': 8, 'failed': 0, 'skipped': 0})

    def test_same_count_wrong_method_wrong_module_or_duplicate_rejects(self):
        original = gate.expected_cases('compact-phone')['ui']
        changes = [original[:-1] + ['-[CelluloidUITests.CelluloidUITests testUnexpected]'],
                   [name.replace('CelluloidUITests.', 'AnotherTarget.') for name in original],
                   original[:-1] + [original[0]], original[:-1],
                   original + ['-[CelluloidUITests.CelluloidUITests testUnexpected]']]
        for cases in changes:
            with self.subTest(cases=cases), self.assertRaises(ValueError):
                self.validate(*self.phase(cases))

    def test_actual_device_runtime_and_summary_fail_closed(self):
        changes = [lambda s: s['devicesAndConfigurations'][0]['device'].update(deviceId='AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE'),
                   lambda s: s['devicesAndConfigurations'][0]['device'].update(modelName='iPhone 18 Pro Max'),
                   lambda s: s['devicesAndConfigurations'][0]['device'].update(osBuildNumber='wrong'),
                   lambda s: s['devicesAndConfigurations'][0]['device'].update(architecture='x86_64'),
                   lambda s: s.update(result='Unknown'), lambda s: s.update(passedTests=True),
                   lambda s: s.update(finishTime=float('nan')),
                   lambda s: s['devicesAndConfigurations'].append(copy.deepcopy(s['devicesAndConfigurations'][0]))]
        for change in changes:
            raw, summary = self.phase()
            change(summary)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.validate(raw, summary)

    def test_consistent_failed_or_skipped_execution_cannot_qualify(self):
        for state in ('failed', 'skipped'):
            raw, summary = self.phase()
            name = gate.expected_cases('compact-phone')['ui'][0]
            raw = raw.replace(f"Test Case '{name}' passed", f"Test Case '{name}' {state}")
            key = state + 'Tests'
            summary[key] = 1
            summary['passedTests'] -= 1
            summary['devicesAndConfigurations'][0].update({key: 1, 'passedTests': 7})
            if state == 'failed':
                method = name.split(' ')[1][:-1]
                summary.update(result='Failed', testFailures=[{'targetName': 'CelluloidUITests',
                    'testIdentifierString': 'CelluloidUITests/' + method + '()'}])
                raw = raw.replace('with 0 failures', 'with 1 failure').replace('** TEST EXECUTE SUCCEEDED **',
                    'Failing tests:\nCelluloidUITests.' + method + '()\n** TEST EXECUTE FAILED **')
            else:
                raw = raw.replace('with 0 failures', 'with 1 test skipped and 0 failures')
            with self.subTest(state=state), self.assertRaises(ValueError):
                self.validate(raw, summary)

    def test_incomplete_terminal_suite_error_or_timeout_rejects(self):
        raw, summary = self.phase()
        changes = [raw.replace('** TEST EXECUTE SUCCEEDED **', ''), raw + '** TEST EXECUTE SUCCEEDED **\n',
                   raw + 'error: unowned compiler error\n', raw + 'BOUNDED_COMMAND_TIMEOUT ui\n',
                   raw + 'BOOTSTRAP_RECOVERED_COMMAND_FAILURES []\n',
                   raw + 'BOUNDED_COMMAND_END {"exit_code": 124}\n',
                   raw.replace('Executed 8 tests', 'Executed 7 tests'),
                   raw.replace("Test Case '", "Test Case '", 1) + "Test Suite 'Selected tests' started at 2026-10-06 01:00:00.000.\n"]
        for changed in changes:
            with self.subTest(raw=changed[-100:]), self.assertRaises(ValueError):
                self.validate(changed, summary)

    def test_runtime_binding_never_accepts_another_row_device(self):
        raw, summary = self.phase()
        wrong = {'id': DEVICE, 'model': gate.ROWS['large-phone']}
        with self.assertRaises(ValueError):
            gate.validate_phase('compact-phone', 'ui', raw, summary, wrong)

    def test_bounded_marker_rejects_nonfinite_unused_fields_before_status_checks(self):
        raw, summary = self.phase()
        for token in ('NaN', 'Infinity', '-Infinity', '1e999'):
            marker = 'BOUNDED_COMMAND_END {"exit_code":0,"extra":{"samples":[' + token + ']}}\n'
            with self.subTest(token=token), self.assertRaisesRegex(ValueError, 'Nonfinite JSON number'):
                self.validate(raw + marker, summary)


class ManifestAccountingTests(unittest.TestCase):
    def test_each_complete_original_row_has_exact_invocation_total(self):
        for row, expected in gate.ROW_COUNTS.items():
            with self.subTest(row=row), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                write_execution(root, row)
                result = verify(root, row=row)
                self.assertTrue(result['row_execution_passed'])
                self.assertEqual(result['original_test_invocation_count'], expected)
                self.assertFalse(result['release_acceptance'])

    def test_missing_duplicate_extra_and_reordered_phase_reject(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_execution(root)
            for mutation in ('missing', 'duplicate', 'extra', 'reorder', 'caller-path', 'nonzero', 'bool-code', 'unknown-code'):
                value = manifest()
                if mutation == 'missing': value['phases'].pop()
                elif mutation == 'duplicate': value['phases'].append(copy.deepcopy(value['phases'][0]))
                elif mutation == 'extra': value['phases'].append({'name': 'preflight', 'exit_code': 0})
                elif mutation == 'reorder': value['phases'].reverse()
                elif mutation == 'caller-path': value['phases'][0]['raw_log'] = '/tmp/substitute.log'
                elif mutation == 'nonzero': value['phases'][0]['exit_code'] = 65
                elif mutation == 'bool-code': value['phases'][0]['exit_code'] = False
                else: value['phases'][0]['exit_code'] = None
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    verify(root, value)

    def test_every_prerequisite_including_cleanup_and_bootstrap_must_succeed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_execution(root)
            for key in gate.expected_prerequisites('compact-phone'):
                for state in ('failure', 'skipped', 'cancelled', '', True, None):
                    value = manifest()
                    value['prerequisites'][key] = state
                    with self.subTest(key=key, state=state), self.assertRaises(ValueError):
                        verify(root, value)
            for key in gate.expected_prerequisites('compact-phone'):
                value = manifest()
                del value['prerequisites'][key]
                with self.subTest(missing=key), self.assertRaises(ValueError):
                    verify(root, value)

    def test_source_run_attempt_row_and_manifest_schema_are_exact(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_execution(root)
            for key, replacement in (('source_sha', 'b' * 40), ('run_id', '7654321'), ('run_attempt', '2'),
                                     ('row', 'large-phone'), ('schema', 'Other.1'), ('run_id', 1234567)):
                value = manifest()
                value[key] = replacement
                with self.subTest(key=key, replacement=replacement), self.assertRaises(ValueError):
                    verify(root, value)

    def test_missing_symlink_and_duplicate_json_input_reject(self):
        for mutation in ('missing', 'symlink', 'duplicate-json'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                write_execution(root)
                target = root / 'units.summary.json'
                if mutation == 'missing': target.unlink()
                elif mutation == 'symlink':
                    target.rename(root / 'other-summary.json')
                    target.symlink_to(root / 'other-summary.json')
                else:
                    target.write_text(target.read_text().replace('{', '{"result":"Passed",', 1))
                with self.assertRaises(ValueError):
                    verify(root)

    def test_recovery_probes_cannot_hide_successful_normal_bootstrap_cases(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_execution(root)
            (root / 'bootstrap-reconcile-timeout-0.log').write_text('retained failed import diagnostic')
            with self.assertRaisesRegex(ValueError, 'timeout reconciliation'):
                verify(root)

    def test_stale_overlapping_future_and_late_result_times_reject(self):
        for start, finish in ((99_000, 99_001), (100_001, 100_002), (103_001, 103_002), (102_699, 102_701)):
            with self.subTest(start=start), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                write_execution(root)
                target = root / 'preservation.summary.json'
                value = json.loads(target.read_text())
                value.update(startTime=start, finishTime=finish)
                target.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    verify(root)

    def test_actual_final_overrun_is_red_even_when_every_case_passed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_execution(root)
            with self.assertRaisesRegex(ValueError, 'exceeded'):
                gate.verify_manifest(manifest(), root, context(), clock(), now_monotonic=13_361, now_unix=103_361)

    def test_actual_summary_parser_rejects_nonfinite_extra_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_execution(root)
            path = root / 'units.summary.json'
            original = path.read_text()
            for token in ('NaN', 'Infinity', '-Infinity', '1e999'):
                path.write_text(original[:-1] + ',"extra":{"samples":[' + token + ']}}')
                with self.subTest(token=token), self.assertRaisesRegex(ValueError, 'Nonfinite JSON number'):
                    verify(root)


class ClockAdmissionTests(unittest.TestCase):
    def admit(self, phase, elapsed, row='compact-phone'):
        return gate.admit_phase(clock(row), context(row), phase, 10_000 + elapsed, 100_000 + elapsed)

    def test_original_caps_and_exact_660_second_tail(self):
        self.assertEqual(gate.TAIL_SECONDS, 660)
        self.assertEqual(gate.WORK_SECONDS, 2700)
        self.assertEqual(sum(value[0] for value in gate.TAIL_PHASES.values()), 660)
        self.assertEqual(self.admit('release-build', 0), 600)
        self.assertEqual(self.admit('build', 0), 900)
        self.assertEqual(self.admit('boot', 0), 60)
        self.assertEqual(self.admit('bootstatus', 0), 600)
        self.assertEqual(self.admit('fixture-stage', 0), 600)
        self.assertEqual(self.admit('privacy', 0), 60)
        self.assertEqual(self.admit('summary', 0), 30)
        self.assertEqual(self.admit('evidence-screens', 0), 180)
        self.assertEqual(self.admit('diagnostics', 2600), 100)
        self.assertEqual(self.admit('bootstrap', 100), 2600)
        status = gate.clock_status(clock(), context(), 10_001, 100_001)
        self.assertEqual(status['outside_execution_clock_seconds'], 240)

    def test_admission_clips_without_rounding_up_or_borrowing_tail(self):
        self.assertEqual(self.admit('units', 2600.1), 99)
        for elapsed in (2699.01, 2700, 3300):
            with self.subTest(elapsed=elapsed), self.assertRaises(ValueError):
                self.admit('units', elapsed)
        for phase, (ceiling, deadline) in gate.TAIL_PHASES.items():
            with self.subTest(phase=phase):
                self.assertEqual(self.admit(phase, deadline - ceiling), ceiling)
                self.assertEqual(self.admit(phase, deadline - 1.1), 1)
                with self.assertRaises(ValueError): self.admit(phase, deadline)

    def test_completion_must_meet_real_phase_and_final_deadlines(self):
        gate.check_completion(clock(), context(), 'units', 12_700, 102_700)
        with self.assertRaises(ValueError): gate.check_completion(clock(), context(), 'units', 12_700.01, 102_700.01)
        for phase, (_, deadline) in gate.TAIL_PHASES.items():
            gate.check_completion(clock(), context(), phase, 10_000 + deadline, 100_000 + deadline)
            with self.subTest(phase=phase), self.assertRaises(ValueError):
                gate.check_completion(clock(), context(), phase, 10_000 + deadline + .01, 100_000 + deadline + .01)
        gate.check_completion(clock(), context(), None, 13_360, 103_360)
        with self.assertRaises(ValueError): gate.check_completion(clock(), context(), None, 13_361, 103_361)

    def test_fixed_phase_names_reject_other_rows_or_arbitrary_commands(self):
        for phase, row in (('permission-granted', 'small-ipad'), ('preflight', 'compact-phone'),
                           ('release-build', 'large-phone'), ('preservation', 'large-ipad'), ('rm -rf /', 'compact-phone')):
            with self.subTest(phase=phase, row=row), self.assertRaises(ValueError):
                self.admit(phase, 1, row)

    def test_changed_context_clock_bounds_types_and_nan_reject(self):
        for key, value in (('source_sha', 'b' * 40), ('run_id', '2'), ('run_attempt', '2'),
                           ('row', 'large-phone'), ('schema', 'unknown'), ('execution_budget_seconds', 3600),
                           ('execution_budget_seconds', 3360.0), ('started_monotonic', True),
                           ('started_monotonic', float('nan')), ('started_unix', float('inf'))):
            changed = clock()
            changed[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                gate.clock_status(changed, context(), 10_001, 100_001)
        for now_monotonic, now_unix in ((9999, 100_001), (10_001, 99_999), (float('nan'), 100_001)):
            with self.assertRaises(ValueError): gate.clock_status(clock(), context(), now_monotonic, now_unix)

    def test_queue_delay_has_no_cross_job_expiry(self):
        # Queue delay precedes this row's first-step clock, however long it is.
        # No producer-age field or six-hour lease can be supplied to this gate.
        delayed = clock()
        delayed['started_unix'] += 48 * 60 * 60
        self.assertEqual(gate.admit_phase(delayed, context(), 'units', 10_001, delayed['started_unix'] + 1), 900)
        delayed['producer_expires_unix'] = delayed['started_unix'] + 6 * 60 * 60
        with self.assertRaises(ValueError):
            gate.clock_status(delayed, context(), 10_001, delayed['started_unix'] + 1)


class CommandLineTests(unittest.TestCase):
    def env(self):
        # Never inherit a live CI source, run, attempt, or row into synthetic data.
        return {'PATH': os.environ.get('PATH', ''), 'GITHUB_SHA': SOURCE, 'GITHUB_RUN_ID': '1234567',
                'GITHUB_RUN_ATTEMPT': '1', 'PYTHONDONTWRITEBYTECODE': '1'}

    def test_cli_admission_and_optimized_python_keep_checks_active(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'clock.json'
            value = clock()
            value.update(started_monotonic=time.monotonic(), started_unix=time.time())
            path.write_text(json.dumps(value))
            command = [sys.executable, '-O', str(gate.ROOT / 'Scripts/uikit_full_shipping_gate.py'),
                       'admit', '--row', 'compact-phone', '--clock', str(path), '--phase', 'units']
            result = subprocess.run(command, capture_output=True, text=True, env=self.env(), timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), '900')
            changed_env = dict(self.env(), GITHUB_RUN_ATTEMPT='2')
            result = subprocess.run(command, capture_output=True, text=True, env=changed_env, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('identity differs', result.stderr)

    def test_cli_verify_writes_red_report_for_missing_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            value = clock()
            value.update(started_monotonic=time.monotonic(), started_unix=time.time())
            (root / 'clock.json').write_text(json.dumps(value))
            (root / 'manifest.json').write_text(json.dumps(manifest()))
            output = root / 'accounting.json'
            result = subprocess.run([sys.executable, str(gate.ROOT / 'Scripts/uikit_full_shipping_gate.py'),
                'verify', '--row', 'compact-phone', '--root', str(root), '--manifest', str(root / 'manifest.json'),
                '--clock', str(root / 'clock.json'), '--output', str(output)],
                capture_output=True, text=True, env=self.env(), timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(json.loads(output.read_text())['row_execution_passed'])

    def test_actual_clock_and_manifest_parsers_reject_nonfinite_extra_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            value = clock()
            value.update(started_monotonic=time.monotonic(), started_unix=time.time())
            clock_json = json.dumps(value)
            manifest_json = json.dumps(manifest())
            for boundary in ('clock', 'manifest'):
                for token in ('NaN', 'Infinity', '-Infinity', '1e999'):
                    (root / 'clock.json').write_text(clock_json)
                    (root / 'manifest.json').write_text(manifest_json)
                    target = root / (boundary + '.json')
                    target.write_text(target.read_text()[:-1] + ',"extra":{"samples":[' + token + ']}}')
                    output = root / 'accounting.json'
                    result = subprocess.run([sys.executable, str(gate.ROOT / 'Scripts/uikit_full_shipping_gate.py'),
                        'verify', '--row', 'compact-phone', '--root', str(root), '--manifest', str(root / 'manifest.json'),
                        '--clock', str(root / 'clock.json'), '--output', str(output)],
                        capture_output=True, text=True, env=self.env(), timeout=10)
                    with self.subTest(boundary=boundary, token=token):
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn('Nonfinite JSON number', result.stderr)
                        self.assertFalse(json.loads(output.read_text())['row_execution_passed'])


if __name__ == '__main__':
    unittest.main()
