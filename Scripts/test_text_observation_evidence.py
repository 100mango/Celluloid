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

class NativeGlyphObservationTests(unittest.TestCase):
    def row(self):
        image=TextObservationTests().row(('actual-native-coretext-backing',2,0))
        fields={k:image[k] for k in ['width','height','pngBase64','pngSHA256']}
        return {'schema':'Celluloid.NativeGlyphObservation.1','acceptance':False,'text':'Hello, 世界 🎬',
            'sourcePNG_SHA256':'a'*64,'actualCompositePNG_SHA256':'b'*64,'actualTextRect':[77.231,26.24,27.875,43.52],
            'frameAllocationHeight':37,'naturalBlockHeight':36,'fontSize':10,'lineHeight':12,'backingScale':2,
            'coreTextLines':[{'frameLineOrigin':[0,y],'runs':[]} for y in [27,15,3]],
            'oracleLines':[{'text':text,'glyphRuns':[]} for text in ['Hello,',' 世界 ','🎬']],
            'images':[dict(fields,role=role) for role in ['replayed-production-backing','exact-appkit-oracle-backing']],
            'isolatedMetrics':{'premultipliedRGBMaximum':60,'alphaMaximum':102,'premultipliedRGBPixelsAbove2':284,'alphaPixelsAbove2':275},'scope':'Synthetic diagnostic test data'}
    def exercise(self,change=None,result='failed'):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);owner,method=gate.GLYPH_CASE
            row=self.row();contract={'schema':'Celluloid.NativeTextContract.1','case':'manufactured-affine','sourcePNG_SHA256':'a'*64,'actualPNG_SHA256':'b'*64}
            lines=[f"Test Case '-[{owner} {method}]' started.",gate.GLYPH_PREFIX+json.dumps(row),
                   'MAC_NATIVE_TEXT_CONTRACT '+json.dumps(contract),f"Test Case '-[{owner} {method}]' {result} (1.0 seconds)."]
            if change:lines=change(lines,row)
            (root/'mac.log').write_text('\n'.join(lines)+'\n')
            return json.loads(gate.collect_glyphs(root,'c'*40))
    def test_failed_and_passed_case_observations_never_grant_acceptance(self):
        for result in ['failed','passed']:
            report=self.exercise(result=result);self.assertFalse(report['acceptance']);self.assertEqual(report['case_result'],result)
    def test_duplicate_missing_outside_case_and_oversized_lines_reject(self):
        for change in [lambda lines,row:lines[:2]+lines[1:],lambda lines,row:lines[:2]+lines[3:],
                       lambda lines,row:[lines[1]]+lines[:1]+lines[2:],
                       lambda lines,row:[lines[0],gate.GLYPH_PREFIX+'x'*100001]+lines[2:],
                       lambda lines,row:[lines[0],' '+lines[1]]+lines[2:]]:
            with self.subTest(change=change),self.assertRaises(ValueError):self.exercise(change)
        with self.assertRaises(ValueError):self.exercise(result='skipped')
    def test_png_hash_dimensions_source_and_nonfinite_data_reject(self):
        mutations=[lambda r:r.update(acceptance=True),lambda r:r.update(sourcePNG_SHA256='f'*64),
            lambda r:r.update(actualCompositePNG_SHA256='f'*64),lambda r:r['images'][0].update(pngSHA256='f'*64),
            lambda r:r['images'][0].update(width=57),lambda r:r['images'].reverse(),
            lambda r:r.update(frameAllocationHeight=float('nan')),lambda r:r['coreTextLines'].pop(),
            lambda r:r['isolatedMetrics'].update(alphaMaximum=True),lambda r:r['oracleLines'][2].update(text='other')]
        for mutate in mutations:
            def change(lines,row):mutate(row);lines[1]=gate.GLYPH_PREFIX+json.dumps(row);return lines
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):self.exercise(change)
    def test_collector_retains_diagnostic_before_optional_pressure_and_rejects_corruption(self):
        import os,subprocess
        root=Path(__file__).resolve().parents[1]
        for mutation in ['valid','hash','duplicate','oversized']:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as folder:
                temp=Path(folder);owner,method=gate.GLYPH_CASE;row=self.row()
                if mutation=='hash':row['images'][1]['pngSHA256']='f'*64
                line=gate.GLYPH_PREFIX+json.dumps(row)
                if mutation=='oversized':line=gate.GLYPH_PREFIX+'x'*100001
                lines=[f"Test Case '-[{owner} {method}]' started.",line]
                if mutation=='duplicate':lines.append(line)
                lines+=['MAC_NATIVE_TEXT_CONTRACT '+json.dumps({'schema':'Celluloid.NativeTextContract.1','case':'manufactured-affine','sourcePNG_SHA256':'a'*64,'actualPNG_SHA256':'b'*64}),
                        f"Test Case '-[{owner} {method}]' failed (1.0 seconds)."]
                (temp/'mac.log').write_text('\n'.join(lines)+'\n')
                (temp/'domain.log').write_text('optional pressure\n'*200000)
                result=subprocess.run(['python3',str(root/'Scripts/collect_native_evidence.py')],env=dict(os.environ,RUNNER_TEMP=str(temp),GITHUB_SHA='c'*40,CELLULOID_EVIDENCE_PLATFORM='mac'),capture_output=True,text=True,timeout=15)
                self.assertEqual(result.returncode==0,mutation=='valid',result.stderr)
                output=temp/'celluloid-bounded-evidence'/'native-glyph-observation.json'
                if mutation=='valid':
                    self.assertTrue(output.is_file());self.assertFalse(json.loads(output.read_text())['acceptance'])
                    self.assertLessEqual(sum(p.stat().st_size for p in output.parent.iterdir()),2000000)
                else:self.assertFalse(output.exists())

    def test_new_observation_uses_public_glyph_hooks_without_renderer_or_oracle_relaxation(self):
        root=Path(__file__).resolve().parents[1];swift=(root/'Platforms/MacExtensionTests/MacPhotoRendererTests.swift').read_text()
        for api in ['CTRunGetPositions','CTRunGetStringIndices','CTRunGetTextMatrix','CTFontGetMatrix','super.showCGGlyphs','firstGlyphLocation','observedOracleBacking = image']:
            self.assertIn(api,swift)
        self.assertIn('XCTAssertLessThanOrEqual(difference, 2,',swift)
        self.assertIn('manager.drawGlyphs(forGlyphRange: glyphRange, at: drawOrigin)',swift)
        self.assertIn('let lineBaseline = firstGlyphLocation.y',swift)
        self.assertIn('"acceptance": false',swift)
        collector=(root/'Scripts/collect_native_evidence.py').read_text()
        self.assertLess(collector.index('glyph_observations=collect_glyphs'),collector.index('Optional exporter time'))

if __name__=='__main__':unittest.main()
