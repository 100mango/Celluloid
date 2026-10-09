#!/usr/bin/env python3
"""Portable contract tests; importing these helpers never invokes Apple tools."""
import ast
import copy
import json
from pathlib import Path
import tempfile
import unittest
import swiftui_photos_gate as gate


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.binding = {'source_sha': 'a' * 40, 'device_id': '12345678-1234-1234-1234-123456789AB0', 'run_id': '123', 'run_attempt': '1'}
        self.hashes = {name: str(index) * 64 for index, name in enumerate(gate.FIXTURES)}
        self.before = {'authorization': 3, 'asset_count': 2, 'asset_identifiers': ['stock-a', 'stock-b'], 'synthetic': []}
        self.fixtures = [{'identifier': f'fixture-{index}', 'filename': name, 'sha256': self.hashes[name],
                          'width': size[0], 'height': size[1], 'creation_date_utc': '2026-10-09T00:00:00Z'}
                         for index, (name, size) in enumerate(gate.FIXTURES.items())]
        self.after = {'authorization': 3, 'asset_count': 8,
                      'asset_identifiers': ['stock-a', 'stock-b'] + [r['identifier'] for r in self.fixtures], 'synthetic': self.fixtures}

    def test_observed_nonempty_baseline_and_exact_controlled_increment(self):
        value = gate.reconcile_library(self.before, self.after, self.hashes, self.binding)
        self.assertEqual((value['baseline_asset_count'], value['seeded_asset_count']), (2, 8))
        self.assertEqual(value['baseline_asset_ids'], ['stock-a', 'stock-b'])
        self.assertEqual(len(value['added_asset_ids']), 6)
        self.assertEqual(value['authorization_read_write'], 'authorized')

    def test_deleted_stock_or_extra_assets_fail_closed(self):
        for ids in [self.after['asset_identifiers'][1:], self.after['asset_identifiers'] + ['extra']]:
            changed = {**self.after, 'asset_identifiers': ids, 'asset_count': len(ids)}
            with self.assertRaises(ValueError): gate.reconcile_library(self.before, changed, self.hashes, self.binding)

    def test_wrong_bytes_duplicate_identity_or_permission_fail(self):
        changed = copy.deepcopy(self.after); changed['synthetic'][0]['sha256'] = 'f' * 64
        with self.assertRaises(ValueError): gate.reconcile_library(self.before, changed, self.hashes, self.binding)
        changed = copy.deepcopy(self.after); changed['asset_identifiers'][-1] = changed['asset_identifiers'][-2]
        with self.assertRaises(ValueError): gate.reconcile_library(self.before, changed, self.hashes, self.binding)
        with self.assertRaises(ValueError): gate.reconcile_library({**self.before, 'authorization': 4}, self.after, self.hashes, self.binding)

    def test_existing_fixtures_do_not_authorize_reimport(self):
        with self.assertRaises(ValueError): gate.reconcile_library({**self.before, 'synthetic': [self.fixtures[0]]}, self.after, self.hashes, self.binding)

    def test_exact_stage_counts_and_no_skip_acceptance(self):
        self.assertEqual({key: len(gate.methods(key)) for key in gate.STAGES}, {'legacy': 48, 'pristine': 5, 'preservation': 6})
        for stage in gate.STAGES:
            expected = gate.methods(stage)
            summary = {'totalTestCount': len(expected), 'passedTests': len(expected), 'failedTests': 0,
                       'skippedTests': 0, 'expectedFailures': 0, 'result': 'Passed', 'testFailures': [], 'runtimeWarnings': []}
            log = '\n'.join("Test Case '-[{}.{} {}]' passed (0.001 seconds).".format(*item.split('/')) for item in expected)
            gate.verify_summary(stage, summary, log)
            with self.assertRaises(ValueError): gate.verify_summary(stage, {**summary, 'skippedTests': 1}, log)
            with self.assertRaises(ValueError): gate.verify_summary(stage, summary, log.replace(expected[0].split('/')[-1], 'testWrongMethod', 1))

    def test_runtime_warnings_or_missing_warning_evidence_reject_green_counts(self):
        stage = 'pristine'; expected = gate.methods(stage)
        summary = {'totalTestCount': len(expected), 'passedTests': len(expected), 'failedTests': 0,
                   'skippedTests': 0, 'expectedFailures': 0, 'result': 'Passed', 'testFailures': [], 'runtimeWarnings': []}
        log = '\n'.join("Test Case '-[{}.{} {}]' passed (0.001 seconds).".format(*item.split('/')) for item in expected)
        gate.verify_summary(stage, summary, log)
        for warnings in [None, False, {}, [{'sourceURL': 'file:///fixture/CelluloidKit/SwiftUI/CelluloidEditorContent.swift', 'message': 'Publishing changes from within view updates is not allowed'}]]:
            with self.assertRaises(ValueError): gate.verify_summary(stage, {**summary, 'runtimeWarnings': warnings}, log)
        del summary['runtimeWarnings']
        with self.assertRaises(ValueError): gate.verify_summary(stage, summary, log)

    def test_pristine_recheck_preserves_controlled_bytes_and_stock_ids(self):
        manifest = gate.reconcile_library(self.before, self.after, self.hashes, self.binding)
        gate.verify_pristine(manifest, self.after)
        with self.assertRaises(ValueError): gate.verify_pristine(manifest, {**self.after, 'asset_count': 9})

    def test_owner_receipt_does_not_authorize_other_or_preexisting_simulator(self):
        receipt = {'schema': 'celluloid.swiftui.owned-simulator.v1', **self.binding,
                   'device_name': 'Celluloid iOS27 iPhone SE (3rd generation)',
                   'runtime_id': 'com.apple.CoreSimulator.SimRuntime.iOS-27-0', 'created_by_this_job': True, 'absent_before_create': True}
        environment = {'GITHUB_SHA': self.binding['source_sha'], 'GITHUB_WORKFLOW_SHA': self.binding['source_sha'],
                       'GITHUB_REPOSITORY': '100mango/Celluloid', 'GITHUB_REF': 'refs/heads/swiftui-first-native',
                       'GITHUB_EVENT_NAME': 'push', 'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1'}
        observed = {'devices': {receipt['runtime_id']: [{'udid': receipt['device_id'], 'name': receipt['device_name'], 'state': 'Booted', 'isAvailable': True}]}}
        self.assertEqual(gate.validate_owner(receipt, receipt['device_id'], environment, observed), self.binding)
        for changed in [{**receipt, 'absent_before_create': False}, {**receipt, 'created_by_this_job': 1}, {**receipt, 'source_sha': 'b' * 40}]:
            with self.assertRaises(ValueError): gate.validate_owner(changed, receipt['device_id'], environment, observed)

    def test_shared_deadline_never_expands_job_or_phase_budget(self):
        receipt = {'job_started_monotonic': 100, 'work_deadline_monotonic': 2380}
        self.assertEqual(gate.phase_budget('bootstrap', receipt, now=100), 720)
        self.assertEqual(gate.phase_budget('legacy', receipt, now=2200), 165)
        with self.assertRaises(ValueError): gate.phase_budget('legacy', receipt, now=2380)
        with self.assertRaises(ValueError): gate.phase_budget('legacy', {**receipt, 'work_deadline_monotonic': 3000}, now=100)

    def test_timeout_or_uncertain_cleanup_stops_following_simctl(self):
        for phase, status, log in [('legacy', 124, ''), ('pristine', 1, 'BOUNDED_COMMAND_CLEANUP_UNCONFIRMED'), ('bootstrap', 1, 'failure')]:
            self.assertTrue(gate.safety_record(phase, status, log)['prohibit_further_simctl'])
        self.assertFalse(gate.safety_record('legacy', 65, 'ordinary XCTest assertion failure')['prohibit_further_simctl'])

    def test_legacy_bootstrap_default_and_explicit_build_path(self):
        source = Path(__file__).with_name('probe_photos_bootstrap.py')
        parsed = ast.parse(source.read_text())
        definitions = ast.Module(body=[n for n in parsed.body if isinstance(n, (ast.Import, ast.ImportFrom, ast.FunctionDef))], type_ignores=[])
        namespace = {'device': 'owned', 'evidence_root': Path('/tmp/unused-fixture-evidence')}
        exec(compile(definitions, str(source), 'exec'), namespace)
        calls = []
        namespace['run'] = lambda *args: (calls.append(args) or (0, 'PHOTOS_LIBRARY_READINESS {"synthetic": []}\n'))
        namespace['test']('before', 'testPhotosLibraryBootstrapReadiness')
        namespace['test']('before', 'testPhotosLibraryBootstrapReadiness', '.build/swiftui-ios')
        self.assertEqual(calls[0][calls[0].index('-derivedDataPath') + 1], '.build')
        self.assertEqual(calls[1][calls[1].index('-derivedDataPath') + 1], '.build/swiftui-ios')
        self.assertEqual(calls[0][1], 360)


if __name__ == '__main__': unittest.main()
