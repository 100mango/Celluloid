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
        modes=[('frame-default','CTFrameDraw',{}),('frame-position-on','CTFrameDraw',{'positioning':True}),
            ('frame-position-off','CTFrameDraw',{'positioning':False}),
            ('frame-position-on-quant-off','CTFrameDraw',{'positioning':True,'quantization':False}),
            ('frame-position-on-quant-on','CTFrameDraw',{'positioning':True,'quantization':True}),
            ('frame-smoothing-off','CTFrameDraw',{'smoothing':False}),
            ('line-default','CTLineDraw',{}),('run-default','CTRunDraw',{}),('glyph-default','CTFontDrawGlyphs',{}),('glyph-absolute-origin','CTFontDrawGlyphs',{}),('glyph-appkit-transform','CTFontDrawGlyphs',{})]
        ct_lines=[{'frameLineOrigin':[0,y],'runs':[{'glyphs':list(range(n)), 'font':'SyntheticFont', 'size':10,
            'fontMatrix':[1,0,0,1,0,0], 'positionsFromCTRunGetPositions':[[k,0] for k in range(n)]}]} for y,n in [(27,6),(15,4),(3,1)]]
        zero={'premultipliedRGBMaximum':0,'alphaMaximum':0,'premultipliedRGBPixelsAbove2':0,'alphaPixelsAbove2':0}
        experiments=[dict(fields,name=name,api=api,explicitFlagOverrides=flags,plannedCoordinateProof={'glyphCount':11,'maximumDeviceOriginDelta':0,'maximumGlyphLinearDelta':0} if name in {'glyph-absolute-origin','glyph-appkit-transform'} else None,
            initialCTM=[2,0,0,2,0,0] if name=='glyph-absolute-origin' else [2,0,0,-2,0,88] if name=='glyph-appkit-transform' else [2,0,0,2,0,6.48],
            initialTextMatrix=[1,0,0,1,0,0],initialTextPosition=[0,0],
            finalCTM=[2,0,0,2,0,0] if name=='glyph-absolute-origin' else [2,0,0,-2,0,88] if name=='glyph-appkit-transform' else [2,0,0,2,0,6.48],
            finalTextMatrix=[1,0,0,-1,0,0] if name=='glyph-appkit-transform' else [1,0,0,1,0,0],finalTextPosition=[0,0],interpolationQuality=3,
            premultipliedRGBA_SHA256='d'*64,againstProductionReplay=dict(zero),againstExactOracle=dict(zero)) for name,api,flags in modes]
        for experiment in experiments[-2:]:
            draw_inputs=[]
            for i,line in enumerate(ct_lines):
                run=line['runs'][0];y=line['frameLineOrigin'][1]
                positions=[[x,y+3.24] if experiment['name']=='glyph-absolute-origin' else [x,44-(y+3.24)] for x,_ in run['positionsFromCTRunGetPositions']]
                draw_inputs.append({'lineIndex':i,'runIndex':0,'font':run['font'],'size':run['size'],
                    'fontMatrix':[1,0,0,-1,0,0] if experiment['name']=='glyph-appkit-transform' else [1,0,0,1,0,0],
                    'inputCTM':experiment['initialCTM'],'glyphs':run['glyphs'],'positions':positions})
            experiment['plannedCoordinateProof']['drawInputs']=draw_inputs
        return {'schema':'Celluloid.NativeGlyphObservation.4','acceptance':False,'productionBackend':'NSLayoutManager.showCGGlyphs/CoreText-shaped-runs','text':'Hello, 世界 🎬',
            'sourcePNG_SHA256':'a'*64,'actualCompositePNG_SHA256':'b'*64,'actualTextRect':[77.231,26.24,27.875,43.52],
            'frameAllocationHeight':37,'naturalBlockHeight':36,'fontSize':10,'lineHeight':12,'backingScale':2,
            'coreTextLines':ct_lines,
            'oracleLines':[{'text':text,'glyphRuns':[]} for text in ['Hello,',' 世界 ','🎬']],
            'images':[dict(fields,role=role) for role in ['replayed-production-backing','exact-appkit-oracle-backing']],
            'rasterExperiments':experiments,
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
    def test_historical_coretext_difference_is_retained_without_granting_acceptance(self):
        def changed_backend(lines,row):
            row['rasterExperiments'][0]['againstProductionReplay'].update(alphaMaximum=102,alphaPixelsAbove2=241)
            lines[1]=gate.GLYPH_PREFIX+json.dumps(row);return lines
        result=self.exercise(changed_backend)
        self.assertFalse(result['acceptance'])
        self.assertEqual(result['observation']['rasterExperiments'][0]['againstProductionReplay']['alphaMaximum'],102)

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
    def test_raster_experiment_order_flags_geometry_default_control_and_caps_reject(self):
        mutations=[lambda r:r.update(schema='Celluloid.NativeGlyphObservation.1'),
            lambda r:r['rasterExperiments'].pop(),lambda r:r['rasterExperiments'].reverse(),
            lambda r:r['rasterExperiments'][1].update(api='OtherAPI'),
            lambda r:r['rasterExperiments'][1].update(explicitFlagOverrides={'positioning':1}),
            lambda r:r['rasterExperiments'][2].update(initialCTM=[2,0,0,2,0,7.48]),
            lambda r:r.update(productionBackend='CTFrameDraw'),
            lambda r:r['rasterExperiments'][0].update(initialTextPosition=[0,1]),
            lambda r:r['rasterExperiments'][0].update(pngSHA256='f'*64),
            lambda r:r['rasterExperiments'][0].update(width=57),
            lambda r:r['rasterExperiments'][0].update(extra='unbound'),
            lambda r:r['rasterExperiments'][0]['againstExactOracle'].update(alphaMaximum=True),
            lambda r:r['rasterExperiments'][0].update(pngBase64=base64.b64encode(b'x'*6001).decode())]
        for mutate in mutations:
            def change(lines,row):mutate(row);lines[1]=gate.GLYPH_PREFIX+json.dumps(row);return lines
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):self.exercise(change)

    def test_transform_decomposition_proof_and_effective_matrix_must_be_invariant(self):
        mutations=[lambda r:r['rasterExperiments'][-1].update(plannedCoordinateProof=None),
            lambda r:r['rasterExperiments'][-1]['plannedCoordinateProof'].update(glyphCount=10),
            lambda r:r['rasterExperiments'][-1]['plannedCoordinateProof'].update(maximumDeviceOriginDelta=0.01),
            lambda r:r['rasterExperiments'][-1]['plannedCoordinateProof'].update(maximumGlyphLinearDelta=0.01),
            lambda r:r['rasterExperiments'][-2].update(initialCTM=[2,0,0,2,0,1]),
            lambda r:r['rasterExperiments'][0].update(plannedCoordinateProof={})]
        for mutate in mutations:
            def change(lines,row):mutate(row);lines[1]=gate.GLYPH_PREFIX+json.dumps(row);return lines
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):self.exercise(change)
        # Same device glyph origin and linear transform across all decompositions.
        for x,y in [(0,27),(2.9296875,15),(0,3)]:
            shift=3.24;baseline=(2*x,2*(y+shift))
            absolute=(2*x,2*(y+shift));flipped=(2*x,88-2*(44-(y+shift)))
            for observed in [absolute,flipped]:
                self.assertAlmostEqual(observed[0],baseline[0],places=9)
                self.assertAlmostEqual(observed[1],baseline[1],places=9)

    def test_planned_geometry_is_recomputed_from_inputs_not_post_call_state(self):
        for field,value in [('font','WrongFont'),('size',11),('glyphs',[999]),
                            ('inputCTM',[2,0,0,-2,0,87]),('fontMatrix',[1,0,0,1,0,0]),
                            ('positions',[[0,0]]*6)]:
            def change(lines,row):
                row['rasterExperiments'][-1]['plannedCoordinateProof']['drawInputs'][0][field]=value
                lines[1]=gate.GLYPH_PREFIX+json.dumps(row);return lines
            with self.subTest(field=field),self.assertRaises(ValueError):self.exercise(change)
        def changed_post_state(lines,row):
            row['rasterExperiments'][-1].update(finalCTM=[1,0,0,1,0,0],finalTextMatrix=[1,0,0,1,0,0],finalTextPosition=[17,29])
            lines[1]=gate.GLYPH_PREFIX+json.dumps(row);return lines
        retained=self.exercise(changed_post_state)
        self.assertFalse(retained['acceptance'])
        self.assertEqual(retained['observation']['rasterExperiments'][-1]['finalTextPosition'],[17,29])

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
        for api in ['setAllowsFontSubpixelPositioning','setShouldSubpixelPositionFonts','setAllowsFontSubpixelQuantization','setShouldSubpixelQuantizeFonts','setAllowsFontSmoothing','setShouldSmoothFonts','CTLineDraw','CTRunDraw','CTFontDrawGlyphs','CTRunGetPositions','CTRunGetStringIndices','CTRunGetTextMatrix','CTFontGetMatrix','super.showCGGlyphs','firstGlyphLocation','observedOracleBacking = image']:
            self.assertIn(api,swift)
        self.assertIn('XCTAssertLessThanOrEqual(difference, 2,',swift)
        self.assertNotIn('Test-only default frame replay must equal the shipping helper',swift)
        self.assertIn('"productionBackend": "NSLayoutManager.showCGGlyphs/CoreText-shaped-runs"',swift)
        self.assertIn('guard png.count <= 6_000',swift)
        self.assertIn('guard data.count <= 100_000',swift)
        self.assertIn('manager.drawGlyphs(forGlyphRange: glyphRange, at: drawOrigin)',swift)
        self.assertIn('let lineBaseline = firstGlyphLocation.y',swift)
        self.assertIn('"acceptance": false',swift)
        collector=(root/'Scripts/collect_native_evidence.py').read_text()
        self.assertLess(collector.index('glyph_observations=collect_glyphs'),collector.index('Optional exporter time'))

class AppKitShapedRunSourceTests(unittest.TestCase):
    def source(self):
        root=Path(__file__).resolve().parents[1]
        return ((root/'Platforms/macOSExtension/MacPhotoRenderer.swift').read_text(),
                (root/'Platforms/MacExtensionTests/MacPhotoRendererTests.swift').read_text())

    def test_independent_fixed_geometry_oracle_is_byte_identical(self):
        _,swift=self.source()
        oracle=swift[swift.index('    private func independentLegacyTextBacking()'):swift.index('    func testProductionTextMatchesIndependentNativeControlAndRejectsPathMutations()')]
        self.assertEqual(hashlib.sha256(oracle.encode()).hexdigest(),'d41f8e7ecb75ebfa690e3d3161085631747daa4714fdb10d428663f521b96045')
        for token in ['XCTAssertLessThanOrEqual(difference, 2,','remove-wrapped-space','shift-down-one-point','squeeze-to-logical-bounds','clip-right-half']:
            self.assertIn(token,swift)

    def test_renderer_uses_only_original_shaped_stream_and_per_call_appkit_objects(self):
        source,_=self.source();raster=source.split('enum MacPhotoTextRaster {',1)[1]
        for token in ['CTFrameGetLines','CTFrameGetLineOrigins','CTLineGetGlyphRuns','CTRunGetGlyphs',
                      'CTRunGetPositions','CTRunGetStringIndices','CTRunGetStringRange','CTRunGetTextMatrix',
                      'attributes[kCTFontAttributeName] as? NSFont','manager.showCGGlyphs',
                      'let manager = NSLayoutManager(); manager.backgroundLayoutEnabled = false',
                      'NSGraphicsContext.saveGraphicsState()', 'defer { NSGraphicsContext.restoreGraphicsState() }',
                      'bitmap.saveGState(); defer { bitmap.restoreGState() }','try Task.checkCancellation()',
                      'return try autoreleasepool']:
            self.assertIn(token,raster)
        for token in ['NSTextStorage','NSTextContainer','NSTextView','substring','drawGlyphs(',
                      'CTFontCreate','NSFont(name:', 'MainActor','DispatchQueue.main', 'static let manager',
                      'await ', 'CTFrameDraw(']:
            self.assertNotIn(token,raster)
        self.assertIn('guard adjustment.layers.isEmpty else { throw MacPhotoRenderQualificationError.layeredPhotosOutput }',source)

    def test_generic_and_background_runtime_invariants_remain_explicit(self):
        _,swift=self.source()
        for token in ['assertUnchangedShapedRuns','candidate.font === font','candidate.glyphs, glyphs',
                      'candidate.stringIndices, indices','candidate.sourceRange.location',
                      'pixelHeight - 2 * actual.y','No extra, missing, reordered or reshaped runs',
                      'العربية','שלום','नमस्ते','✈︎ ✈️','🇯🇵 🇺🇸','👩🏽‍💻',
                      'Task.detached','withUnsafeCurrentTask { $0?.cancel() }',
                      'NSGraphicsContext.current === sentinel','catch is CancellationError',
                      'padding: 65']:
            self.assertIn(token,swift)

    def test_backing_repair_preserves_fitting_shaping_and_raw_draw_bytes(self):
        source,_=self.source()
        slices=[('struct MacPhotoTextLayout {','enum MacPhotoTextRaster {','6d169c8f788a4713168bd40749a2429602988f8cbf45a8a58e98198913aca2bf'),
                ('    static func make(_ layout:','    struct GlyphRun {','bd473229a0c5ffcf4833f2ab592062508f865c249cb6b3cfc975faf34dd5aa5c'),
                ('    static func glyphRuns(',None,'f7e25db901dcc84084b9506528518170f9369330a3afab98ba21e5202843db0f')]
        for start,end,digest in slices:
            body=source[source.index(start):source.index(end,source.index(start))] if end else source[source.index(start):]
            self.assertEqual(hashlib.sha256(body.encode()).hexdigest(),digest)

    def test_backing_expansion_is_ink_based_pixel_aligned_and_origin_compensated(self):
        source,swift=self.source()
        backing=source[source.index('    struct Backing {'):source.index('    static func make(_ layout:')]
        for token in ['font.boundingRectForFont','font.boundingRect(forCGGlyph: glyph)',
                      'ceil(overhang * scale + 2) / scale','padding <= 64','<= 4_194_304',
                      'let ink = try inkPixelBounds(expanded)','full.insetBy(dx: 1, dy: 1).contains(ink)',
                      'logical.union(ink.isNull ? ink : ink.insetBy(dx: -1, dy: -1))',
                      'expanded.cropping(to: retained)','(retained.minX - logical.minX) / scale',
                      '(retained.minY - logical.minY) / scale','origin.x + backing.origin.x',
                      'origin.y + backing.origin.y','column * 4 + 3] != 0']:
            self.assertIn(token,backing)
        for token in ['scaleBy(', 'CTFramesetter', 'fontSize:', 'substring', 'drawGlyphs(']:
            self.assertNotIn(token,backing)
        self.assertIn('let text = try MacPhotoTextRaster.makeBacking(layout, bounds: textRect.size)',source)
        for token in ['assertInkBoundsUseTopLeftPixelCoordinatesAndRetainFaintEdgeInk',
                      'Expansion must preserve every original interior pixel',
                      'Backing must contain all padded-path glyph ink',
                      'Keep one transparent edge pixel for transformed sampling']:
            self.assertIn(token,swift)

    def test_only_crlf_control_interiors_relax_line_boundary_assertions(self):
        _,swift=self.source()
        helper=swift[swift.index('    private func isCRLFControlBoundary('):swift.index('    private func permitsLineBoundary(')]
        self.assertIn('offset > 0 && offset < units.count && units[offset - 1] == 0x000D && units[offset] == 0x000A',helper)
        for token in ['[2, 4, 7]', 'Allowed controls must paint no pixels',
                      'Painting cluster must stay indivisible','boundaries.contains(offset) || controlBoundary',
                      'XCTAssertEqual(replay, text, diagnostic)', 'utf16=\\(units) ranges=\\(ranges)',
                      '"a\\u{0301}"', '"🎬"', '"👩🏽‍💻"', '"👨‍👩‍👧‍👦"', '"✈️"', '"🇯🇵"']:
            self.assertIn(token,swift)


if __name__=='__main__':unittest.main()
