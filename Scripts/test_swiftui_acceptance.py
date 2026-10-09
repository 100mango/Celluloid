#!/usr/bin/env python3
"""Portable admission checks; these never dispatch Xcode or a simulator."""
from pathlib import Path
import json, tempfile, unittest
from unittest.mock import patch
import run_picker_acceptance as picker
import run_swiftui_acceptance as main

DEVICE = 'AB000000-0000-0000-0000-000000000001'
RUNTIME = 'com.apple.CoreSimulator.SimRuntime.iOS-27-0'
ENV = {'GITHUB_RUN_ID': '1', 'GITHUB_RUN_ATTEMPT': '1'}

class AcceptanceTests(unittest.TestCase):
    def summary(self):
        return dict(totalTestCount=4, passedTests=4, failedTests=0, skippedTests=0, expectedFailures=0,
                    result='Passed', testFailures=[], runtimeWarnings=[], devicesAndConfigurations=[{'device': {'deviceId': DEVICE}}])
    def after(self):
        return {'devices': {RUNTIME: [{'udid': DEVICE, 'name': 'Celluloid iOS27 iPhone SE (3rd generation)', 'isAvailable': True, 'state': 'Shutdown'}]}}
    def test_unique_run_requires_three_iterations(self):
        rows = [f'PICKER_AUTOMATION_DIAGNOSTIC run={DEVICE} iteration={i}' for i in [1,2,3]]
        self.assertEqual(picker.unique_run('\n'.join(rows)), DEVICE.lower())
        for bad in [rows[:2], rows + [rows[0]], [rows[0]] * 3]:
            with self.assertRaises(ValueError): picker.unique_run('\n'.join(bad))
    def test_unique_run_rejects_mixed_runs(self):
        rows = [f'PICKER_AUTOMATION_DIAGNOSTIC run={DEVICE} iteration={i}' for i in [1,2,3]]
        rows[-1] = rows[-1].replace(DEVICE, 'AB000000-0000-0000-0000-000000000002')
        with self.assertRaises(ValueError): picker.unique_run('\n'.join(rows))
    def test_summary_accepts_exact_facts(self):
        picker.qualify_summary(self.summary(), 4, DEVICE)
    def test_summary_rejects_skips_wrong_device_and_boolean(self):
        for key, value in [('skippedTests', 1), ('passedTests', True), ('result', 'Failed')]:
            result = self.summary(); result[key] = value
            with self.assertRaises(ValueError): picker.qualify_summary(result, 4, DEVICE)
        with self.assertRaises(ValueError): picker.qualify_summary(self.summary(), 4, 'foreign')
    def test_runtime_warnings_or_missing_warning_evidence_reject_green_counts(self):
        for warnings in [None, False, {}, [{'sourceURL': 'file:///fixture/CelluloidKit/SwiftUI/CelluloidEditorContent.swift', 'message': 'Publishing changes from within view updates is not allowed'}]]:
            with self.assertRaises(ValueError): picker.qualify_summary({**self.summary(), 'runtimeWarnings': warnings}, 4, DEVICE)
        summary = self.summary(); del summary['runtimeWarnings']
        with self.assertRaises(ValueError): picker.qualify_summary(summary, 4, DEVICE)
    def test_system_and_unresolved_warnings_are_classified_and_retained(self):
        warnings = [
            {'sourceURL': 'file:///Applications/Xcode_27.app/Frameworks/XCTest.framework/XCTest.m', 'message': 'Known runner diagnostic'},
            {'sourceURL': '', 'message': 'Needs source review'}]
        summary = {**self.summary(), 'runtimeWarnings': warnings}
        picker.qualify_summary(summary, 4, DEVICE)
        report = picker.runtime_warning_report(summary)
        self.assertEqual(report['total'], 2)
        self.assertEqual(report['blocking_notice_warning_count'], 0)
        self.assertEqual(report['other_warning_review_count'], 2)
        self.assertEqual([r['origin'] for r in report['warnings']], ['xcode_or_system_source', 'unresolved_source'])
        self.assertEqual([r['message'] for r in report['warnings']], [r['message'] for r in warnings])
    def test_json_extraction_ignores_command_markers(self):
        source = 'bounded {"meta":1}\n' + json.dumps({'devices': {}}) + '\nEND'
        self.assertEqual(main.extract_json(source, 'devices'), {'devices': {}})
    def test_json_extraction_rejects_ambiguous_evidence(self):
        for source in ['', '{"devices":{}}\n{"devices":{}}']:
            with self.assertRaises(ValueError): main.extract_json(source, 'devices')
    def test_owner_requires_absent_before_and_exact_created_device(self):
        got = main.owner_receipt({'devices': {}}, self.after(), DEVICE, ENV, 'a'*40, 1, 2281)
        self.assertTrue(got['absent_before_create']); self.assertEqual(got['work_deadline_monotonic'], 2281)
        with self.assertRaises(ValueError): main.owner_receipt(self.after(), self.after(), DEVICE, ENV, 'a'*40, 1, 2281)
    def test_owner_rejects_wrong_runtime_name_or_identity(self):
        for key, value in [('name', 'foreign'), ('state', 'Booted'), ('isAvailable', False)]:
            after = self.after(); after['devices'][RUNTIME][0][key] = value
            with self.assertRaises(ValueError): main.owner_receipt({'devices': {}}, after, DEVICE, ENV, 'a'*40, 1, 2281)
        with self.assertRaises(ValueError): main.owner_receipt({'devices': {}}, self.after(), DEVICE, {}, 'a'*40, 1, 2281)
    def test_whole_bundle_binding_includes_debug_dylib_and_resources(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp).resolve()/'App.app'; app.mkdir()
            (app/'Info.plist').write_text('fixture'); binary = app/'Celluloid'; binary.write_bytes(b'bin')
            dylib = app/'Celluloid.debug.dylib'; dylib.write_bytes(b'v1')
            binding = picker.build_binding(binary, 'a'*40, 'b'*40)
            picker.check_build(binding, binary, 'a'*40, 'b'*40)
            dylib.write_bytes(b'v2')
            with self.assertRaises(ValueError): picker.check_build(binding, binary, 'a'*40, 'b'*40)
    def test_phase_admission_reserves_deadline_and_uncertainty(self):
        gate = main.Acceptance.__new__(main.Acceptance); gate.deadline = 100; gate.uncertain = False
        with patch.object(main.time, 'monotonic', return_value=90):
            with self.assertRaises(ValueError): gate.admit('test', 1)
        gate.uncertain = True
        with patch.object(main.time, 'monotonic', return_value=1):
            with self.assertRaises(ValueError): gate.admit('test', 1, True)
    def test_interrupted_native_command_blocks_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(main, 'OUT', Path(tmp)), patch.object(main.subprocess, 'call', side_effect=KeyboardInterrupt):
            gate = main.Acceptance(); gate.deadline += 1000
            with self.assertRaises(KeyboardInterrupt): gate.command('fixture', ['false'], 1, simulator=True)
            self.assertTrue(gate.uncertain)
    def test_stale_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'receipt.json'; picker.write(path, {'status':'fixture'})
            with self.assertRaises(ValueError): picker.write(path, {'status':'passed'})

if __name__ == '__main__': unittest.main()
