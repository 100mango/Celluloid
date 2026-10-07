"""Local source/projection guards; these never claim native compilation or UI success."""
import hashlib
import json
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
BASE=json.loads((ROOT/'Scripts/fixtures/mac-store-source-baseline.json').read_bytes())
UI='Platforms/UITests/NativeEditorUITests.swift'
PRODUCT='Platforms/macOS/NativeWindowAccessibility.swift'

def digest(raw): return hashlib.sha256(raw).hexdigest()
def strip_capture(text):
    text=re.sub(r'(?ms)^([ \t]*)// BEGIN CELLULOID_MAC_STORE_CAPTURE_([A-Z_]+)\n.*?^\1// END CELLULOID_MAC_STORE_CAPTURE_\2\n','',text)
    return re.sub(r'\n{2,}','\n',text)
def release_projection(text):
    result=[];stack=[]
    for line in text.splitlines(keepends=True):
        value=line.strip()
        if value.startswith('#if '):
            stack.append(value=='#if DEBUG' or (stack[-1] if stack else False))
            if stack[-1]: continue
        elif value=='#endif':
            omitted=stack.pop()
            if omitted: continue
        if not any(stack):result.append(line)
    if stack: raise ValueError('unbalanced conditional')
    return ''.join(result)

class CelluloidMacStoreSourceTests(unittest.TestCase):
    def test_exact_inherited_source_hashes(self):
        self.assertEqual(len(BASE['current_app_inputs']),906)
        for path,expected in BASE['current_app_inputs'].items():
            with self.subTest(path=path):self.assertEqual(digest((ROOT/path).read_bytes()),expected)
    def test_only_marked_capture_additions_to_existing_source(self):
        for path,expected in BASE['original_source_without_capture_sha256'].items():
            self.assertEqual(digest(strip_capture((ROOT/path).read_text()).encode()),expected)
    def test_release_projection_no_capture_seam(self):
        raw=(ROOT/PRODUCT).read_text();release=release_projection(raw)
        for value in ['CELLULOID_MAC_STORE_CAPTURE','storeWindowSized','configureStoreWindowIfRequested','--celluloid-store-capture']:
            self.assertNotIn(value,release)
        self.assertEqual(re.sub(r'\n{2,}','\n',release),release_projection(strip_capture(raw)))
    def test_product_optin_only_sizes_existing_root_window(self):
        raw=(ROOT/PRODUCT).read_text();method=raw.split('// BEGIN CELLULOID_MAC_STORE_CAPTURE_HELPER\n',1)[1].split('// END CELLULOID_MAC_STORE_CAPTURE_HELPER',1)[0]
        for value in ['paneLabel == nil','!storeWindowSized','let window','UUID(uuidString: token)?.uuidString == token','info.arguments.contains("--celluloid-store-capture")','screen.backingScaleFactor == 1','screen.frame.width == 1280, screen.frame.height == 960','window.setFrame(frame, display: true)']:
            self.assertIn(value,method)
        for value in ['NSWindow(', 'NSImage(', 'CGImage', 'NSApp.windows', 'setAccessibilityChildren', 'UserDefaults', 'NSOpenPanel']:
            self.assertNotIn(value,method)
    def test_only_one_fixed_new_case_and_normal_file_import(self):
        raw=(ROOT/UI).read_text().split('// BEGIN CELLULOID_MAC_STORE_CAPTURE_HELPERS\n',1)[1].split('// END CELLULOID_MAC_STORE_CAPTURE_HELPERS',1)[0]
        self.assertEqual(re.findall(r'func (test\w+)\(',raw),['testStoreOriginalDocumentScreenshots'])
        self.assertEqual(raw.count('try launch(app)'),1)
        self.assertIn('importButton.click(); try goTo(source, in: app)',raw)
        self.assertIn('app.windows.buttons["OKButton"]',raw)
        for value in ['makeFixture()', 'performAccessibilityAudit', 'NSPasteboard','PHPhotoLibrary','replaceSources(', 'resize(', 'cropping(', 'draw(in:', 'CGVirtualDisplay','CGDisplaySetDisplayMode']:
            self.assertNotIn(value,raw)
        self.assertIn('defer { app.terminate(); restoreStoreDisplay() }',raw)
        self.assertLess(raw.index('try prepareStoreDisplay(token)'),raw.index('storeStarted = Date()'))
        self.assertLess(raw.index('storeStarted = Date()'),raw.index('try launch(app)'))
    def test_fixed_display_and_native_pixels(self):
        raw=(ROOT/UI).read_text().split('// BEGIN CELLULOID_MAC_STORE_CAPTURE_HELPERS\n',1)[1]
        for value in ['.forAppOnly','mode.width == 1280 && mode.height == 960','scale == 1','window.screenshot().pngRepresentation','XCTAssertEqual(width, 1280','XCTAssertEqual(height, 800','try observeStoreDocument(app, source: source, state: state)','SecCodeCopySigningInformation','errSecCSUnsigned']:
            self.assertIn(value,raw)
        self.assertEqual(raw.count('window.screenshot().pngRepresentation'),1)
        self.assertEqual(raw.count('try observeStoreDocument(app, source: source, state: state)'),2)
    def test_real_editor_controls_and_state(self):
        raw=(ROOT/UI).read_text().split('// BEGIN CELLULOID_MAC_STORE_CAPTURE_HELPERS\n',1)[1]
        for value in ['("editor.import-files", "Import Files")','("editor.filter", "Filter")','("editor.add-sticker", "Sticker")','("editor.add-bubble", "Bubble")','("editor.export", "Export")','XCTAssertTrue(control.isEnabled)','XCTAssertTrue(control.isHittable)','XCTAssertEqual(control.label, title)','window.frame.contains(control.frame)','window.popUpButtons["editor.filter"].value as? String, "Original"','window.progressIndicators.count, 0','XCTAssertEqual(app.sheets.count, 0)','XCTAssertEqual(app.dialogs.count, 0)','XCTAssertEqual(app.popovers.count, 0)']:
            self.assertIn(value,raw)
    def test_exact_reused_art_assets_not_bundled(self):
        provenance=json.loads((ROOT/'StoreCaptureAssets/provenance.json').read_bytes())
        blobs={'demo-citrus-sunny.png':'49c4dfaa7f09c2db9f4853cadbb5baaa47490157','demo-coast-sunny.png':'90b483ba6b398e39e63b15c11725fa6afe1df97c'}
        for row in provenance['assets']:
            raw=(ROOT/'StoreCaptureAssets'/row['filename']).read_bytes()
            self.assertEqual(len(raw),row['bytes']);self.assertEqual(digest(raw),row['sha256'])
            self.assertEqual(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(),blobs[row['filename']])
        project=(ROOT/'CelluloidNative.xcodeproj/project.pbxproj').read_text()
        self.assertNotIn('StoreCaptureAssets',project)
        self.assertNotIn('demo-citrus-sunny',project);self.assertNotIn('demo-coast-sunny',project)
    def test_existing_scheme_expected_path_unchanged(self):
        path='CelluloidNative.xcodeproj/xcshareddata/xcschemes/CelluloidMacUI.xcscheme'
        self.assertEqual(digest((ROOT/path).read_bytes()),BASE['current_app_inputs'][path])
        tree=ET.fromstring((ROOT/path).read_bytes())
        values={x.attrib['key']:x.attrib['value'] for x in tree.findall('.//EnvironmentVariable')}
        self.assertEqual(values['CELLULOID_EXPECTED_APP_PATH'],'$(BUILT_PRODUCTS_DIR)/CelluloidMac.app')

if __name__=='__main__':unittest.main()
