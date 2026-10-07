"""Source preservation and ordinary display boundaries; no native visual claim."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import unittest

import store_screenshots as capture

ROOT = Path(__file__).resolve().parents[1]


def display_block():
    source = (ROOT / capture.UI_PATH).read_bytes()
    start = source.index(b'    // BEGIN FIXED STORE DISPLAY METHODS\n')
    end = source.index(b'    private func emitScreenshot(_ name: String) {\n')
    return source, source[start:end], source[:start] + source[end:]


class StoreDisplaySourceTests(unittest.TestCase):
    def test_exact_addition_reverses_to_previous_capture_and_original_106_methods(self):
        source, block, prior = display_block()
        self.assertEqual(capture.sha(source), capture.UI_CAPTURE_SHA)
        self.assertEqual(capture.sha(block), capture.DISPLAY_BLOCK_SHA)
        self.assertEqual(capture.sha(prior), capture.UI_PRIOR_CAPTURE_SHA)
        original = prior.replace(capture.INSERTION, b'')
        self.assertEqual(capture.sha(original), capture.UI_BASE_SHA)
        cases = re.findall(rb'\bfunc (test\w+)\s*\(', block)
        self.assertEqual(cases, [method.encode() for method in capture.CASES.values()])
        original_count = 0
        for folder in ('CelluloidTests', 'CelluloidUITests'):
            for path in (ROOT / folder).glob('*.swift'):
                data = original if path == ROOT / capture.UI_PATH else path.read_bytes()
                original_count += len(re.findall(rb'\bfunc test\w+\s*\(', data))
        self.assertEqual(original_count, 106)
        self.assertIn(b'continueAfterFailure = false', original)
        capture.verify_source()

    def test_two_new_display_cases_use_photos_and_cancel_without_pressure_save_or_decoration_actions(self):
        block = display_block()[1].decode()
        calls = block[:block.index('    private func waitForStoreDiagonalCollage')]
        for forbidden in ('.pinch(', '.rotate(', '.press(', '.swipe', '.typeText(', '.doubleTap(',
                          'XCUIDevice.shared.orientation', 'saveAnd', 'share-done', 'launchArguments.append',
                          'value(forKey', 'setValue(', 'perform('):
            self.assertNotIn(forbidden, calls)
        button_taps = re.findall(r'app.buttons\["([^"]+)"\]\.tap\(\)', calls)
        self.assertEqual(button_taps, ['edit-photo', 'picker-done', 'Cancel', 'make-collage', 'picker-done', 'Cancel'])
        self.assertEqual(calls.count('launch(diagnostics: false, photosAccess: true)'), 2)
        self.assertEqual(calls.count('XCTAssertFalse(app.descendants(matching: .any)["photo-2"].exists)'), 2)
        self.assertEqual(calls.count('CELLULOID_STORE_CAPTURE'), 2)
        self.assertEqual(calls.count('emitScreenshot('), 2)
        editor = calls[:calls.index('    func testStoreNormalCollageScreenshot')]
        self.assertIn('photo-0', editor)
        self.assertIn('attachment-image', editor)
        self.assertNotIn('coordinate(withNormalizedOffset:', editor)

    def test_plain_editor_source_resets_original_and_uses_aspect_fit(self):
        editor = (ROOT / 'CelluloidKit/Controller/BaseEditPhotoController.swift').read_text()
        self.assertIn('preview.contentMode = .scaleAspectFit', editor)
        self.assertIn('var filterType = FilterType.Original', editor)
        self.assertGreaterEqual(editor.count('filterType = .Original'), 2)
        block = display_block()[1].decode()
        self.assertIn('photo-0 is one of the two hash-verified samples, not a promise of coast order.', block)

    def test_selected_existing_layout_has_source_grounded_distinct_geometry(self):
        layouts = json.loads((ROOT / 'Celluloid/collage.json').read_text())['two_pic']
        self.assertEqual(len(layouts), 5)
        selected = layouts[3]
        self.assertEqual(selected['drawable_name'], 'compose_2_4')
        def bounds(points):
            xs, ys = points[::2], points[1::2]
            return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
        left, right = map(bounds, selected['polygons'])
        self.assertAlmostEqual(left[2] / left[3], .6167)
        self.assertAlmostEqual(right[2] / right[3], .5667)
        self.assertAlmostEqual((right[0] - left[0]) / left[3], .4333)
        initial = list(map(bounds, layouts[0]['polygons']))
        self.assertGreater(abs(initial[0][2] / initial[0][3] - .6167), .1)
        panel = (ROOT / 'Celluloid/View/CollageStylePanel.swift').read_text()
        self.assertIn('layout.minimumLineSpacing = 5', panel)
        self.assertIn('UIEdgeInsets(top: 10, left: 10, bottom: 10, right: 5)', panel)
        self.assertIn('collageModels[indexPath.row]', panel)
        self.assertIn('self.height - 20', panel)

    def test_style_tap_uses_source_index_and_safe_visible_portion_without_full_cell_requirement(self):
        block = display_block()[1].decode()
        self.assertIn('XCTAssertEqual(panels.count, 1', block)
        self.assertIn('panelFrame.minX + 10 + CGFloat(index) * 105', block)
        self.assertIn('let target = cells[3]', block)
        self.assertIn('targetFrame.intersection(panelFrame).intersection(app.frame)', block)
        self.assertIn('visible.width >= 20 && visible.height >= 80', block)
        self.assertIn('visible.midX - targetFrame.minX', block)
        self.assertNotIn('contains(targetFrame)', block)
        self.assertLess(block.index('target.coordinate(withNormalizedOffset: point).tap()'),
                        block.index('XCTAssertTrue(waitForStoreDiagonalCollage())'))
        self.assertLess(block.index('XCTAssertTrue(waitForStoreDiagonalCollage())'),
                        block.index('emitScreenshot("collage-preview")'))

    def test_layout_postcondition_uses_one_consistent_public_snapshot_and_stable_observation(self):
        helper = display_block()[1].decode().split('    private func waitForStoreDiagonalCollage()', 1)[1]
        self.assertEqual(helper.count('app.snapshot()'), 1)
        self.assertNotIn('app.frame', helper)
        self.assertNotIn('app.scrollViews', helper)
        self.assertIn('descendants(snapshot)', helper)
        self.assertIn('snapshot.frame.insetBy', helper)
        self.assertIn('.elementType == .scrollView && $0.identifier == "collage-image"', helper)
        self.assertIn('frames.count == 2', helper)
        for value in ('0.6167', '0.5667', '0.4333', '>= 0.4', 'timeout: 15'):
            self.assertIn(value, helper)

    def test_workflow_changes_only_the_new_display_step_label(self):
        path = '.github/workflows/store-screenshots.yml'
        previous = subprocess.check_output(['git', 'show', capture.PUBLIC_BASE + ':' + path], cwd=ROOT, timeout=15)
        old = b'Capture only the two existing UI cases after their original setup'
        new = b'Capture two new normal display checks after the original setup'
        self.assertEqual(previous.count(old), 1)
        self.assertEqual((ROOT / path).read_bytes(), previous.replace(old, new))
        self.assertIn(path, capture.CAPTURE_PATHS)

    def test_original_setup_file_and_shipping_project_exclude_nonshipping_assets(self):
        contract = json.loads((ROOT / 'Scripts/original-ios-source-contract.json').read_text())
        files = dict(contract['files'])
        path = 'CelluloidTests/EditorRegressionTests.swift'
        self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), files[path])
        for project in ('Celluloid.xcodeproj/project.pbxproj', 'CelluloidNative.xcodeproj/project.pbxproj'):
            self.assertNotIn(b'StoreCaptureAssets', (ROOT / project).read_bytes())
        self.assertFalse(any(path.startswith('StoreCaptureAssets/') for path in files))


if __name__ == '__main__':
    unittest.main()
