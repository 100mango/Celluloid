#!/usr/bin/env python3
"""Read/generate project-graph checks only; no Apple runtime or signing claim."""
from pathlib import Path
import base64
import hashlib
import json
import plistlib
import runpy
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]

class MacPhotosExtensionGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph = runpy.run_path(str(ROOT / 'Scripts/generate_native_project.py'))
        cls.objects = cls.graph['objects']
        cls.targets = cls.graph['targets']

    def source_paths(self, target):
        node = self.objects[self.targets[target]]
        sources = next(self.objects[p] for p in node['buildPhases'] if self.objects[p]['isa'] == 'PBXSourcesBuildPhase')
        return [self.objects[self.objects[f]['fileRef']]['path'] for f in sources['files']]

    def test_actual_existing_appex_is_a_dependency_and_embedded_in_plugins(self):
        app = self.objects[self.targets['CelluloidMac']]
        self.assertIn(self.targets['CelluloidMacPhotosExtension'], [self.objects[d]['target'] for d in app['dependencies']])
        phases = [self.objects[p] for p in app['buildPhases'] if self.objects[p]['isa'] == 'PBXCopyFilesBuildPhase']
        self.assertEqual(len(phases), 1)
        self.assertEqual(phases[0]['dstSubfolderSpec'], '13')
        product = self.objects[self.objects[phases[0]['files'][0]]['fileRef']]
        self.assertEqual(product['path'], 'CelluloidMacPhotosExtension.appex')
        self.assertEqual(product['explicitFileType'], 'wrapper.app-extension')

    def test_production_and_logic_tests_compile_the_same_adapter_and_reviewed_writer(self):
        production = self.source_paths('CelluloidMacPhotosExtension')
        tests = self.source_paths('CelluloidMacPhotosExtensionTests')
        self.assertTrue(set(production).issubset(tests))
        self.assertEqual(len(production), len(set(production)))
        self.assertIn('CelluloidPhotoExtension/PhotosOutputWrite.swift', production)
        self.assertIn('CelluloidTests/PhotosOutputWriteTests.swift', tests)
        self.assertNotIn('Platforms/macOS/LegacyFilterAdjustment.swift', production)
        for path in production + tests:
            self.assertTrue((ROOT / path).is_file(), path)

    def test_principal_identity_and_registered_suite_match_real_products(self):
        info = plistlib.loads((ROOT / 'Platforms/macOSExtension/Info.plist').read_bytes())
        self.assertEqual(info['NSExtension']['NSExtensionPointIdentifier'], 'com.apple.photo-editing')
        self.assertEqual(info['NSExtension']['NSExtensionPrincipalClass'], '$(PRODUCT_MODULE_NAME).MacPhotoEditingController')
        for name in ['CelluloidMac', 'CelluloidMacPhotosExtension']:
            scheme = ET.parse(ROOT / f'CelluloidNative.xcodeproj/xcshareddata/xcschemes/{name}.xcscheme')
            testables = scheme.findall('.//TestableReference/BuildableReference')
            self.assertIn('CelluloidMacPhotosExtensionTests', [p.attrib['BlueprintName'] for p in testables])
        ext = ET.parse(ROOT / 'CelluloidNative.xcodeproj/xcshareddata/xcschemes/CelluloidMacPhotosExtension.xcscheme')
        for ref in ext.findall('.//BuildableReference'):
            if ref.attrib['BlueprintName'] == 'CelluloidMacPhotosExtension':
                self.assertEqual(ref.attrib['BuildableName'], 'CelluloidMacPhotosExtension.appex')

    def test_original_uikit_fixture_hashes_and_historical_canvas_absence(self):
        folder = ROOT / 'Packages/CelluloidCore/Tests/CelluloidDomainTests/Fixtures'
        for name in ['legacy-points', 'reference-canvas']:
            data = base64.b64decode((folder / f'{name}.base64').read_bytes())
            expected = json.loads((folder / f'{name}.json').read_text())
            self.assertEqual(hashlib.sha256(data).hexdigest(), expected['sha256'])
            archive = plistlib.loads(data)
            root_index = archive['$top']['root'].data
            root = archive['$objects'][root_index]
            keys = [archive['$objects'][key.data] for key in root['NS.keys']]
            self.assertEqual('referenceCanvasSize' in keys, name == 'reference-canvas')

if __name__ == '__main__':
    unittest.main()
