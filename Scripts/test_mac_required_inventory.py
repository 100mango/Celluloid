"""Exact required test inventory and synthetic log checks; no native pass implied."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import verify_required_interoperability as gate

CODEC = 'MacPhotoNativeCodecControlTests.testRetainedSourceFadeExportAfterOriginalAndFadePreviews'


class MacRequiredInventoryTests(unittest.TestCase):
    def test_all_original_42_and_codec_control_are_required(self):
        expected = gate.required('mac')['CelluloidMacPhotosExtensionTests']
        self.assertEqual(len(expected), 43)
        self.assertEqual(len(set(expected)), 43)
        self.assertIn(CODEC, expected)
        self.assertEqual(len([name for name in expected if name != CODEC]), 42)
        self.assertEqual(expected, sorted(gate.MAC_REQUIRED_CASES))

    def test_missing_or_replaced_selector_fails_even_with_43_names(self):
        for missing in gate.MAC_REQUIRED_CASES:
            cases = [name for name in gate.MAC_REQUIRED_CASES if name != missing]
            for candidate in [cases, sorted([*cases, 'UnexpectedTests.testReplacement'])]:
                with self.subTest(missing=missing, replacement=len(candidate) == 43):
                    with mock.patch.object(gate, 'source_cases', return_value=candidate):
                        with self.assertRaisesRegex(ValueError, 'Required Mac test inventory changed'):
                            gate.required('mac')

    def test_unexpected_addition_does_not_silently_expand_the_gate(self):
        with mock.patch.object(gate, 'source_cases', return_value=sorted([*gate.MAC_REQUIRED_CASES, 'UnexpectedTests.testExtra'])):
            with self.assertRaisesRegex(ValueError, 'unexpected='):
                gate.required('mac')

    def test_duplicate_declarations_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / 'Duplicate.swift'
            p.write_text('class DuplicateTests: XCTestCase { func testSame() {} func testSame() {} }')
            with self.assertRaisesRegex(ValueError, 'Duplicate declared required test'):
                gate.source_cases([p])

    def test_missing_failed_skipped_and_duplicate_execution_still_fail(self):
        expected = gate.required('mac')
        def line(case, status='passed'):
            owner, method = case.split('.')
            return f"Test Case '-[CelluloidMacPhotosExtensionTests.{owner} {method}]' {status} (0.001 seconds).\n"
        good = ''.join(line(case) for case in gate.MAC_REQUIRED_CASES)
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / 'synthetic.log'; log.write_text(good)
            self.assertTrue(gate.inspect(log, expected)['checks']['every_required_case_executed_once_and_passed'])
            for case in gate.MAC_REQUIRED_CASES:
                for status in ['missing', 'failed', 'skipped', 'duplicate']:
                    value = good.replace(line(case), '') if status == 'missing' else good + line(case) if status == 'duplicate' else good.replace(line(case), line(case, status))
                    log.write_text(value)
                    with self.subTest(case=case, status=status):
                        report = gate.inspect(log, expected)
                        self.assertFalse(report['checks']['every_required_case_executed_once_and_passed'])
                        self.assertIn('CelluloidMacPhotosExtensionTests/' + case, report['missing_failed_skipped_or_duplicate'])

    def test_existing_phone_inventory_remains_14_hosted_and_2_ui(self):
        expected = gate.required('phone')
        self.assertEqual(len(expected['CelluloidCompanionTests']), 14)
        self.assertEqual(len(expected['CelluloidCompanionUITests']), 2)


if __name__ == '__main__':
    unittest.main()
