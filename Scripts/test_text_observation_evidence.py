import base64,contextlib,hashlib,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import text_observation_evidence as gate

class TextObservationTests(unittest.TestCase):
    def row(self,key):
        png=b'\x89PNG\r\n\x1a\n'+b'\0\0\0\0IHDR'+(56).to_bytes(4,'big')+(88).to_bytes(4,'big')
        return {'schema':'Celluloid.TextObservation.1','archiveSHA256':'a'*64,'kind':key[0],'scale':key[1],'padding':key[2],'text':'Hello, 世界 🎬','width':56,'height':88,'pngSHA256':hashlib.sha256(png).hexdigest(),'pngBase64':base64.b64encode(png).decode()}
    def exercise(self,mutate=None,source='b'*40):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name,keys in gate.EXPECTED.items():(root/name).write_text(''.join(gate.PREFIX+json.dumps(self.row(k))+'\n' for k in sorted(keys)))
            if mutate:mutate(root)
            with patch.object(gate,'layer_from_log',return_value=json.dumps({'fixture':{'sha256':'a'*64}}).encode()):return json.loads(gate.collect(root,source))
    def test_empty_source_less_smoke_and_source_validation_only_with_records(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'mac.log').write_text('No typography observations were produced.\n')
            self.assertIsNone(gate.collect(root,None))
        for source in [None,True,'synthetic','f'*39]:
            with self.subTest(source=source),self.assertRaisesRegex(ValueError,'source SHA'):
                self.exercise(source=source)
    def test_complete_observations_remain_not_accepted(self):
        report=self.exercise();self.assertTrue(report['complete_observation_set']);self.assertFalse(report['acceptance']);self.assertEqual(len(report['observations']),9)
    def test_missing_consumers_explicitly_incomplete(self):
        report=self.exercise(lambda r:(r/'early-uikit-3x-interop.log').unlink());self.assertFalse(report['complete_observation_set']);self.assertFalse(report['acceptance'])
    def test_wrong_archive_png_dimensions_text_or_duplicate_record_rejected(self):
        def edit(root,key,value):
            p=root/'mac.log';lines=p.read_text().splitlines();row=json.loads(lines[0][len(gate.PREFIX):]);row[key]=value;lines[0]=gate.PREFIX+json.dumps(row);p.write_text('\n'.join(lines)+'\n')
        for key,value in [('archiveSHA256','0'*64),('pngSHA256','0'*64),('width',57),('text','personal text'),('scale',True),('pngBase64','invalid')]:
            with self.subTest(key=key),self.assertRaises((ValueError,TypeError)):self.exercise(lambda r:edit(r,key,value))
        def duplicate(root):
            p=root/'mac.log';p.write_text(p.read_text()*2)
        with self.assertRaises(ValueError):self.exercise(duplicate)
    def test_bounded_lines_missing_png_nested_corruption_and_duplicate_json_keys(self):
        def oversized(root):
            with (root/'mac.log').open('ab') as stream:stream.write(gate.PREFIX.encode()+b'x'*100_001+b'\n')
        with self.assertRaisesRegex(ValueError,'Oversized'):self.exercise(oversized)
        def hidden_midline(root):
            p=root/'mac.log';raw=p.read_bytes();first=raw.splitlines(keepends=True)[0]
            p.write_bytes(b'x'*100_001+first+raw)
        self.assertTrue(self.exercise(hidden_midline)['complete_observation_set'])
        def malformed(root,kind):
            p=root/'mac.log';lines=p.read_text().splitlines();row=json.loads(lines[0][len(gate.PREFIX):])
            if kind=='missing':row.pop('pngBase64')
            if kind=='nested':
                row['publicBacking']={k:row[k] for k in ['pngBase64','pngSHA256','width','height']}
                row['publicBacking']['width']=57
            encoded=json.dumps(row)
            if kind=='duplicate':encoded=encoded[:-1]+',"schema":"Celluloid.TextObservation.1"}'
            lines[0]=gate.PREFIX+encoded;p.write_text('\n'.join(lines)+'\n')
        for kind in ['missing','nested','duplicate']:
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.exercise(lambda r:malformed(r,kind))
    def test_source_instrumentation_is_test_only_public_and_preserves_strict_own_runtime_assertions(self):
        root=Path(__file__).resolve().parents[1]
        native=(root/'Platforms/MacExtensionTests/MacPhotoAdjustmentTests.swift').read_text()
        uikit=(root/'CelluloidTests/MacPhotosManufacturedAdjustmentTests.swift').read_text()
        self.assertIn('super.showCGGlyphs',native);self.assertIn('NSFont.systemFont(ofSize: 10)',native)
        control=native.split('private func diagnoseNativeText',1)[1]
        self.assertNotIn('MacPhotoTextLayout',control);self.assertNotIn('MacPhotoRenderer',control)
        for forbidden in ['value(forKey:', 'setValue(', 'performSelector', 'NSSelectorFromString']:
            self.assertNotIn(forbidden,uikit+control)
        self.assertIn('Public contents does not expose a CGImage; dimensions unavailable',uikit)
        self.assertIn('firstBaselineAnchor',uikit);self.assertIn('lastBaselineAnchor',uikit)
        self.assertIn('CGImage.typeID',uikit);self.assertIn('NSCoder.string(for:',uikit)
        for obsolete in ['CGImageGetTypeID()', 'NSStringFromCGRect(', 'NSStringFromCGPoint(']:
            self.assertNotIn(obsolete,uikit)
        self.assertIn('observedPositiveOrderedAnchors',uikit)
        self.assertIn('boundingRect(forCGGlyph:',control);self.assertIn('contextCTM',control)
        self.assertIn('Fixed 10pt system-font observation',control)
        self.assertIn('XCTAssertLessThanOrEqual(try XCTUnwrap(sameRuntime["full"]), 2,',uikit)
        self.assertIn('XCTAssertLessThanOrEqual(try XCTUnwrap(sameRuntime[component.name]), 2,',uikit)
        self.assertIn('XCTAssertEqual(exact, 0,',uikit)
        self.assertIn('MAC_LAYER_UIKIT_COMPOSITOR archiveSHA256=',uikit)
        self.assertIn('MAC_PLATFORM_RENDERING_CONTRACT ',uikit)
        self.assertIn('internalLineSpans',uikit)

if __name__=='__main__':unittest.main()
