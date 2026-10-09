#!/usr/bin/env python3
"""Portable localization semantics regression; no Apple compilation claim."""
from pathlib import Path
import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROBE = Path('Platforms/macOSExtension/MacPhotoBoundaryProbe.swift')
SCANNER = Path('Scripts/validate_native_localization.py')
MARKER = 'CELLULOID_OWNED_PHOTOS_BOUNDARY_ARM_V1'


class NativeDiagnosticLocalizationTests(unittest.TestCase):
    def test_probe_is_entirely_explicit_debug_diagnostic(self):
        source = (ROOT / PROBE).read_text()
        self.assertTrue(source.startswith('#if DEBUG && CELLULOID_OWNED_PHOTOS_BOUNDARY_PROBE\n'))
        self.assertTrue(source.rstrip().endswith('#endif'))
        self.assertEqual(source.count('#if'), 1)
        self.assertEqual(source.count('#endif'), 1)

    def test_protocol_marker_keeps_exact_bytes_and_use(self):
        source = (ROOT / PROBE).read_text()
        self.assertEqual(source.count(MARKER), 1)
        self.assertIn('static let armReceiptMarker = "' + MARKER + '"', source)
        self.assertIn('view.setAccessibilityLabel(MacPhotoBoundaryProbe.armReceiptMarker)', source)
        self.assertIn('.setAccessibilityIdentifier("photos-extension.boundary-arm")', source)

    def test_operator_field_is_explicitly_verbatim(self):
        source = (ROOT / PROBE).read_text()
        self.assertIn('TextField(text: $probe.token) {\n                    Text(verbatim: "Owned synthetic diagnostic token")\n                }', source)
        self.assertIn('.accessibilityIdentifier("photos-extension.boundary-token")', source)
        self.assertIn('.onSubmit { probe.arm(session: session, identity: identity) }', source)

    def scan(self, extra=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / 'Platforms', root / 'Platforms')
            (root / 'Scripts').mkdir()
            shutil.copyfile(ROOT / SCANNER, root / SCANNER)
            if extra is not None:
                (root / 'Platforms/macOSExtension/LocalizationNegativeControl.swift').write_text(extra)
            return subprocess.run([sys.executable, str(root / SCANNER)], capture_output=True, text=True)

    def test_exact_all_platform_scanner_passes(self):
        result = self.scan()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"native_literal_catalog_check": "passed"', result.stdout)

    def test_genuine_mac_ui_still_requires_localization(self):
        for expression in ('Text("Unlocalized customer label regression")',
                           'view.setAccessibilityLabel("Unlocalized customer label regression")',
                           'TextField("Unlocalized customer label regression", text: $value)'):
            with self.subTest(expression=expression):
                result = self.scan(expression + '\n')
                self.assertEqual(result.returncode, 1)
                self.assertIn('Unlocalized customer label regression', result.stdout)
                self.assertIn('LocalizationNegativeControl.swift', result.stdout)

    def test_localization_scanner_itself_is_unchanged(self):
        self.assertEqual(hashlib.sha256((ROOT / SCANNER).read_bytes()).hexdigest(),
                         '8b678a4f63f7e2dc3deb203d3ece92568e2fb80704ed3667b91142a72b76b606')


if __name__ == '__main__':
    unittest.main()
