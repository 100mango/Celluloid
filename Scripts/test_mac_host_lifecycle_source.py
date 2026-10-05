"""Source-tied safety/independence checks; no native UI success is inferred."""
import ast,copy,json,math,re,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def replay_single_photo_guard(swift, sample, seen=()):
    """Execute the source guard expressions over synthetic AX observations.

    This restricted expression replay is neither Swift compilation nor a native
    Photos result. Counts/labels are inputs, and absent-parent children are never
    observed. Source ties also require the exact scoped, single-read bindings.
    """
    body=swift.split('@MainActor private func soleAsset(',1)[1].split('@MainActor private func lifecycleControl(',1)[0]
    bindings={
        'windowCount':'windows.count', 'alertCount':'photos.alerts.count',
        'sheetCount':'photos.sheets.count', 'dialogCount':'photos.dialogs.count',
        'editorCount':'editorMatches(in: photos).count',
        'identityCount':'photos.descendants(matching: .any).matching(identifier: "photos-extension.self-identity").count',
        'toolbarCount':'toolbars.count', 'collectionCount':'collections.count',
        'canvasCount':'canvases.count', 'imageCount':'images.count',
        'counterCount':'counters.count', 'editCount':'edits.count',
        'doneCount':'toolbar.children(matching: .button).matching(identifier: "IPXToolbarItemIDToggleDoneEdit").count',
        'assetCount':'assets.count'}
    for name,expression in bindings.items():
        if not (body.count(expression) == 1): raise AssertionError('Dynamic count is not sampled exactly once: ' + name)
        if not ('let ' + name + ' = ' + expression in body): raise AssertionError('Changed count binding: ' + name)
    required=[
        'let windows = photos.windows.matching(identifier: "MainWindow")',
        'let window = windows.element(boundBy: 0)', 'let toolbars = window.toolbars',
        'let collections = window.collectionViews.matching(identifier: "photos_collection_view")',
        'let canvases = window.descendants(matching: .group).matching(identifier: "IPXCanvasItemView")',
        'let toolbar = toolbars.element(boundBy: 0)', 'let images = canvases.element(boundBy: 0).images',
        'let imageLabel = imageCount == 1 ? images.element(boundBy: 0).label : ""',
        'let counters = toolbar.staticTexts.matching(identifier: "_NS:10")',
        'let counterValue = counterCount == 1 ? (counters.element(boundBy: 0).value as? String) ?? "" : ""',
        'let edits = toolbar.children(matching: .button).matching(identifier: "IPXToolbarItemIDToggleEdit")',
        'let editLabel = editCount == 1 ? edits.element(boundBy: 0).label : ""',
        'let editEnabled = editCount == 1 && edits.element(boundBy: 0).isEnabled',
        'let editHittable = editCount == 1 && edits.element(boundBy: 0).isHittable',
        'if collectionCount == 1 {',
        'let assets = collections.element(boundBy: 0).descendants(matching: .any).matching(identifier: "mediaKind_asset")',
        'let observedAssetLabel = assetCount == 1 ? assets.element(boundBy: 0).label : ""',
        'let topology = collectionCount == 1 ? "collection-present" : "collection-absent"',
        'if !singlePhotoTopologies.contains(topology)', 'singlePhotoTopologies.count < 2',
        'singlePhotoTopologies.append(topology)']
    if not (all((value in body for value in required))): raise AssertionError('Changed AX scope, property binding, or topology recording')
    guards=re.findall(r'guard\s+([^{}]+?)\s+else \{\s*throw block\("([^"]+)"',body)
    expected=[
        'windowCount == 1, alertCount == 0, sheetCount == 0, dialogCount == 0, editorCount == 0, identityCount == 0, !assetLabel.isEmpty',
        'toolbarCount == 1, canvasCount == 1, collectionCount == 0 || collectionCount == 1',
        'imageCount == 1, imageLabel == assetLabel, counterCount == 1, counterValue == "1 of 1", editCount == 1, editLabel == "Edit", editEnabled, editHittable, doneCount == 0',
        'assetCount == 1, observedAssetLabel == assetLabel', 'singlePhotoTopologies.count < 2']
    if not ([' '.join(value.split()) for value, _ in guards] == expected): raise AssertionError('Source ownership guard changed')
    allowed=(ast.Expression,ast.BoolOp,ast.And,ast.Or,ast.Compare,ast.Eq,ast.NotEq,ast.Constant,ast.Name,ast.Load)
    def accepts(expression):
        # Parenthesize every Swift comma clause before combining it with AND;
        # the collection OR must not bypass earlier required parent predicates.
        expression=expression.replace('!assetLabel.isEmpty', 'assetLabel != ""').replace('||','or')
        expression=' and '.join('('+clause.strip()+')' for clause in expression.split(','))
        parsed=ast.parse(expression,mode='eval')
        if not (all((isinstance(node, allowed) for node in ast.walk(parsed)))): raise AssertionError('Unmodeled Swift predicate')
        return eval(compile(parsed,'single-photo-source-guard','eval'),{'__builtins__':{}},sample)
    trace={'accepted':False,'topologies':list(seen),'asset_observed':False,'failure':None}
    for expression,reason in guards[:3]:
        if not accepts(expression):trace['failure']=reason;return trace
    if sample['collectionCount']==1:
        trace['asset_observed']=True
        if not accepts(guards[3][0]):trace['failure']=guards[3][1];return trace
    topology='collection-present' if sample['collectionCount']==1 else 'collection-absent'
    if topology not in trace['topologies']:
        if len(trace['topologies'])>=2:trace['failure']='Excessive single-photo topologies';return trace
        trace['topologies'].append(topology)
    trace['accepted']=True
    return trace

def single_photo_sample(collection=True):
    """Synthetic shapes matching the retained pre/post-Done observations."""
    row={'windowCount':1,'alertCount':0,'sheetCount':0,'dialogCount':0,'editorCount':0,'identityCount':0,
         'assetLabel':'Oct 5, 2026 at 7:38\u202fPM','toolbarCount':1,'collectionCount':int(collection),'canvasCount':1,
         'imageCount':1,'imageLabel':'Oct 5, 2026 at 7:38\u202fPM','counterCount':1,'counterValue':'1 of 1',
         'editCount':1,'editLabel':'Edit','editEnabled':True,'editHittable':True,'doneCount':0}
    if collection:row.update(assetCount=1,observedAssetLabel=row['assetLabel'])
    return row

class LifecycleSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.swift=(ROOT/'Platforms/UITests/MacPhotosHostUITests.swift').read_text()
    def section(self,a,b):return self.swift.split(a,1)[1].split(b,1)[0]
    def test_original_fixture_is_retained_before_import_and_any_lifecycle_action(self):
        body=self.section('private func makeFixture()', '@MainActor private func selfIdentityObservation')
        self.assertLess(body.index('retainedSource = source'),body.index('"source-retained"'))
        test=self.section('@MainActor func testInstalledExtensionIsInvokedByActualPhotos()', '@MainActor private func importFixture')
        self.assertLess(test.index('let fixture = try makeFixture()'),test.index('try importFixture('))
        self.assertLess(test.index('named: "prerequisite.json"'),test.index('try runFilterLifecycle('))
        self.assertIn('seeded reuse cannot qualify',self.swift)
    def test_exact_phase_order_final_original_and_unexecuted_dirty_cancel_stay_explicit(self):
        body=self.section('@MainActor private func runFilterLifecycle(', '@MainActor private func openTopMenu')
        values=re.findall(r'try lifecyclePhase\("([^"]+)"',body)
        self.assertEqual(values,['fade-ready','saved-export','reopened-fade','cancelled-export','reverted-export','unmodified-original','reopened-original'])
        self.assertIn('filter: "Original", previousGenerations: [initialGeneration, reopened.generation]',body)
        self.assertLess(body.index('"reopened-original"'),body.index('lifecycleComplete = true'))
        self.assertIn('"dirty_cancel_tested": false',self.swift)
        self.assertIn('guard original.bytes == source.bytes',body)
        cancel=body.split('stage = "lifecycle-cancel-without-new-edit"',1)[1].split('stage = "lifecycle-revert-owned-asset"',1)[0]
        self.assertIn('save: false',cancel);self.assertNotIn('selectFade',cancel)
    def test_all_actions_are_fenced_and_all_waits_use_the_one_deadline(self):
        self.assertEqual(self.swift.count('.click()'),1)
        for line in self.swift.splitlines():
            if '.waitForExistence(timeout:' in line:self.assertIn('try remainingTime(',line)
        self.assertIn('testStarted = ProcessInfo.processInfo.systemUptime',self.swift)
        self.assertIn('600 - (ProcessInfo.processInfo.systemUptime - testStarted)',self.swift)
        body=self.section('private func deadlineClick(', 'private func deadlineKey(')
        self.assertLess(body.index('remainingTime'),body.index('.click()'))
        # Executable deadline model tied to the immediate pre-action source fence.
        actions=[]
        def action(now):
            if now>=600:raise TimeoutError()
            actions.append('click')
        action(599)
        for now in [600,601,999]:
            with self.assertRaises(TimeoutError):action(now)
        self.assertEqual(actions,['click'])
    def test_owned_file_caps_are_admitted_before_read_and_do_not_block_on_fifo(self):
        body=self.section('private func readBoundedOwnedFile(', 'private func pngHeader(')
        for part in ['O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW','openat(directoryFD','before.st_size <= Int64(maximumBytes)',
                     'min(65_536, size - bytes.count)','before.st_ctimespec','pathAfter.st_ino','parentBefore.st_ino','defer { Darwin.close(directoryFD) }']:
            self.assertIn(part,body)
        self.assertLess(body.index('before.st_size <= Int64(maximumBytes)'),body.index('bytes.reserveCapacity(size)'))
        export=self.section('@MainActor private func exportRaster(', 'private func readBoundedOwnedFile(')
        self.assertIn('64 * 1024 * 1024 - lifecycleRawBytes',export)
        self.assertIn('maximumBytes:',export)
    def test_icc_has_a_fixed_output_buffer_before_any_imageio_decode(self):
        header=self.section('private func pngHeader(', 'private func bitmap(')
        self.assertIn('uncompress2(',header)
        self.assertIn('4097',header);self.assertIn('4096',header);self.assertIn('Z_OK',header)
        self.assertIn('copyICCData()',header)
        body=self.section('private func lifecycleRaster(', 'private func retainLifecycleImage(')
        self.assertLess(body.index('try pngHeader(data)'),body.index('CGImageSourceCreateWithData'))
        self.assertNotIn('"base64": reference.base64EncodedString()',self.swift)
    def test_expected_image_is_independent_of_actual_exports_and_production_helper(self):
        body=self.section('private func expectedFade(', 'private func maximumDelta(')
        self.assertIn('original.bytes',body);self.assertIn('CIFilter(name: "CIPhotoEffectInstant"',body)
        self.assertIn('kCGImageDestinationLossyCompressionQuality: 0.95',body)
        for forbidden in ['MacPhotoRenderer','RasterCodec','FilterPreset','exportRaster(', 'lifecycleExports']:
            self.assertNotIn(forbidden,body)
        self.assertIn('guard savedDelta <= 2',self.swift)
        self.assertIn('guard cancelled.rgba == saved.rgba',self.swift)
        self.assertIn('guard reverted.rgba == source.rgba',self.swift)
    def test_unknown_confirmations_stop_and_fixed_attachment_namespace_is_bounded(self):
        self.assertIn('Unadmitted Photos confirmation or access alert; no action taken',self.swift)
        self.assertIn('Unadmitted Photos sheet/dialog; no confirmation taken',self.swift)
        body=self.section('private func retainLifecycleImage(', 'private func expectedFade(')
        for part in ['128 * 1024','640 * 1024','lifecycleImages[name] == nil','"celluloid-host-lifecycle-" + name','"public.png"']:
            self.assertIn(part,body)
        self.assertNotIn('Process()',self.swift)
    def test_single_photo_topologies_keep_exact_owned_image_and_deduplicate_observation(self):
        seen=[]
        for present in [True,False,False,True]:
            result=replay_single_photo_guard(self.swift,single_photo_sample(present),seen)
            self.assertTrue(result['accepted']);self.assertEqual(result['asset_observed'],present)
            seen=result['topologies']
        self.assertEqual(seen,['collection-present','collection-absent'])
        # A canvas container's descriptive label is deliberately not asset identity.
        for label in ['canvas','canvas Oct 5, 2026 at 7:38\u202fPM']:
            row=single_photo_sample(False);row['canvasContainerLabel']=label
            self.assertTrue(replay_single_photo_guard(self.swift,row)['accepted'])
    def test_single_photo_wrong_asset_missing_duplicate_and_stale_state_reject(self):
        for present in [True,False]:
            sample=single_photo_sample(present)
            mutations={name:[0,2] for name in ['windowCount','toolbarCount','canvasCount','imageCount','counterCount','editCount']}
            mutations.update({name:[1,2] for name in ['alertCount','sheetCount','dialogCount','editorCount','identityCount','doneCount']})
            mutations.update(collectionCount=[2],assetLabel=[''],imageLabel=['other',''],counterValue=['1 of 2','2 of 2',''],
                             editLabel=['other',''],editEnabled=[False],editHittable=[False])
            if present:mutations.update(assetCount=[0,2],observedAssetLabel=['other',''])
            for name,values in mutations.items():
                for value in values:
                    with self.subTest(collection=present,field=name,value=value):
                        row=dict(sample);row[name]=value
                        result=replay_single_photo_guard(self.swift,row)
                        self.assertFalse(result['accepted']);self.assertEqual(result['topologies'],[])
    def test_single_photo_source_binding_rejects_weakened_or_resampled_predicates(self):
        for old,new in [('imageLabel == assetLabel','imageLabel != assetLabel'),('imageCount == 1,','imageCount >= 1,'),
                        ('canvasCount == 1,','canvasCount == 0,'),('editorCount == 0,','editorCount >= 0,'),
                        ('observedAssetLabel == assetLabel','observedAssetLabel != assetLabel'),
                        ('let imageCount = images.count','let imageCount = images.count\n        _ = images.count'),
                        ('let toolbars = window.toolbars','let toolbars = photos.toolbars')]:
            with self.subTest(mutation=old),self.assertRaises(AssertionError):
                replay_single_photo_guard(self.swift.replace(old,new),single_photo_sample())
    def test_topology_observation_keeps_identity_checks_and_existing_receipt_caps(self):
        body=self.section('@MainActor private func lifecycleGuard(', '@MainActor private func rejectLifecycleAlert(')
        for value in ['hostObservation(expectedPID: photosPID','"app_executable_sha256"','"extension_executable_sha256"',
                      '"extension_debug_dylib_sha256"','"test_source_sha256"','"script_sha256"',
                      'digest(try readBoundedOwnedFile(retainedFixtureURL)) == digest(retainedSource.bytes)',
                      'digest(retainedSource.bytes) == fixtureHash','if normal { try soleAsset(in: photos, assetLabel: assetLabel) }']:
            self.assertIn(value,body)
        self.assertIn('"single_photo_topologies": singlePhotoTopologies',self.swift)
        self.assertIn('bytes.count <= limit',self.swift);self.assertIn('? 120_000 : 16_000',self.swift)
        self.assertIn('lifecycleReceipt(photosPID: photosPID), options: [.sortedKeys]).count <= 16_000',self.swift)
        from test_mac_host_lifecycle import fixture
        full=fixture()[0];full['single_photo_topologies']=['collection-present','collection-absent']
        self.assertLess(len(json.dumps(full,separators=(',',':'),ensure_ascii=False).encode()),16_000)
        # Partial receipts preserve only successful topologies; they never imply completion.
        for count in range(len(full['phases'])+1):
            partial=dict(full,complete=False,phases=full['phases'][:count])
            self.assertLess(len(json.dumps(partial,separators=(',',':'),ensure_ascii=False).encode()),16_000)

def replay_export_association(swift, snapshot):
    """Bounded synthetic public-attribute replay; not native Photos execution."""
    body=swift.split('@MainActor private func exportPopup(',1)[1].split('private func exportBindingSignature(',1)[0]
    required=['sheet.identifier == "sheetWindow_export"','["Color Profile", "Size"].contains(title)',
        'let directCount = direct.count','guard directCount <= 1','if directCount == 1',
        'let labelCount = labels.count','guard labelCount == 1','label.isHittable',
        'let groupCount = groups.count','groupCount > 0, groupCount <= 8 else',
        'group.children(matching: .staticText).matching(labelPredicate).count','guard childCount <= 1',
        'guard parents.count == 1','parentFrame.contains(labelFrame)',
        'let popups = parent.children(matching: .popUpButton)','let popupCount = popups.count',
        'popupCount > 0, popupCount <= 6 else','frame.minX >= labelFrame.maxX',
        'frame.minX - labelFrame.maxX <= 24','abs(frame.midY - labelFrame.midY) <= 6',
        'aligned.append((candidate, frame))','guard aligned.count == 1',
        '!identifier.isEmpty, control.isEnabled, control.isHittable',
        'let query = popups.matching(identifier: identifier)','guard query.count == 1',
        '["label-row", sheet.identifier, parent.identifier, label.identifier, texts[0]']
    if not all(value in body for value in required):raise AssertionError('Source export association no longer matches replay')
    selection=body.split('var aligned:',1)[1].split('guard aligned.count == 1',1)[0]
    if 'isEnabled' in selection or 'isHittable' in selection:raise AssertionError('Usability hides aligned duplicates')
    for expression in ['direct.count','labels.count','groups.count','popups.count']:
        if body.count(expression)!=1:raise AssertionError('Repeated dynamic association count')
    def need(value):
        if not value:raise ValueError('Ambiguous, stale or invalid export association')
    def rect(value):
        need(len(value)==4 and all(type(v) in (int,float) and math.isfinite(v) and abs(v)<=32768 for v in value) and value[2]>0 and value[3]>0)
        return value
    def contains(a,b):return a[0]<=b[0] and a[1]<=b[1] and b[0]+b[2]<=a[0]+a[2] and b[1]+b[3]<=a[1]+a[3]
    field=snapshot['field'];names=(field,field+':');sheet=rect(snapshot['frame']);groups=snapshot['groups']
    need(snapshot['sheet']=='sheetWindow_export' and field in ('Color Profile','Size'))
    direct=[p for g in groups for p in g['popups'] if p['label'] in names or p['title'] in names]
    need(len(direct)<=1)
    if direct:
        control=direct[0];frame=rect(control['frame']);texts=[control[k] for k in ('label','title') if control[k]]
        need(all(t in names for t in texts) and contains(sheet,frame) and control['enabled'] and control['hittable'])
        return [control['id'],['direct',snapshot['sheet'],'','',texts[0],[],frame,sheet,sheet]],control['value']
    labels=[label for g in groups for label in g['labels'] if any(t in names for t in label['texts'])]
    need(len(labels)==1);label=labels[0];lf=rect(label['frame'])
    need(label['hittable'] and all(t in names for t in label['texts']) and contains(sheet,lf))
    need(0<len(groups)<=8)
    parents=[g for g in groups if any(any(t in names for t in label['texts']) for label in g['labels'])]
    need(len(parents)==1);parent=parents[0];pf=rect(parent['frame'])
    need(contains(sheet,pf) and contains(pf,lf));popups=parent['popups'];need(0<len(popups)<=6)
    aligned=[]
    for control in popups:
        frame=rect(control['frame'])
        if contains(pf,frame) and 0<=frame[0]-(lf[0]+lf[2])<=24 and abs(frame[1]+frame[3]/2-(lf[1]+lf[3]/2))<=6:aligned.append(control)
    need(len(aligned)==1);control=aligned[0]
    need(control['id']!='' and control['enabled'] and control['hittable'] and all(control[k]=='' or control[k] in names for k in ('label','title')))
    need(sum(p['id']==control['id'] for p in popups)==1)
    return [control['id'],['label-row',snapshot['sheet'],parent['id'],label['id'],label['texts'][0],lf,control['frame'],pf,sheet]],control['value']

def export_association_sample():
    return {'field':'Color Profile','sheet':'sheetWindow_export','frame':[240,200,542,450],
        'groups':[{'id':'observed_group','frame':[260,220,502,400],
            'labels':[{'id':'observed_label','texts':['Color Profile:'],'frame':[300,304,104,18],'hittable':True}],
            'popups':[{'id':'observed_popup','label':'','title':'','value':'sRGB',
                       'frame':[410,300,302,26],'enabled':True,'hittable':True}]}]}

class ExportAssociationSourceTests(unittest.TestCase):
    def test_exact_observed_profile_wording_keeps_final_value_and_byte_oracle(self):
        source=(ROOT/'Platforms/UITests/MacPhotosHostUITests.swift').read_text()
        self.assertIn('popup("Color Profile", choose: "sRGB", in: options)',source)
        self.assertIn('("Color Profile", "sRGB")',source)
        self.assertNotIn('sRGB IEC61966-2.1',source)
        self.assertIn('fresh.query.element(boundBy: 0).value as? String == value',source)
        self.assertIn('fresh.query.element(boundBy: 0).value as? String == wanted',source)
        self.assertIn('copyICCData()',source)
        self.assertIn('CGColorSpace(name: CGColorSpace.sRGB)',source)

    @classmethod
    def setUpClass(cls):cls.swift=(ROOT/'Platforms/UITests/MacPhotosHostUITests.swift').read_text()
    def test_actual_visible_label_row_and_direct_semantics_are_distinct(self):
        row=export_association_sample();signature,value=replay_export_association(self.swift,row)
        self.assertEqual(signature[0],'observed_popup');self.assertEqual(signature[1][0],'label-row')
        self.assertEqual(signature[1][4],'Color Profile:');self.assertEqual(value,'sRGB')
        row['groups'][0]['popups'][0]['label']='Color Profile'
        self.assertEqual(replay_export_association(self.swift,row)[0][1][0],'direct')
    def test_duplicate_disabled_and_ambiguous_candidates_never_disappear(self):
        variants=[]
        for enabled in [True,False]:
            row=export_association_sample();other=copy.deepcopy(row['groups'][0]['popups'][0]);other.update(id='another',enabled=enabled)
            row['groups'][0]['popups'].append(other);variants.append(row)
        row=export_association_sample();row['groups'][0]['labels']*=2;variants.append(row)
        row=export_association_sample();row['groups']*=2;variants.append(row)
        row=export_association_sample();other=copy.deepcopy(row['groups'][0]['popups'][0]);other['frame']=[410,360,302,26]
        row['groups'][0]['popups'].append(other);variants.append(row)
        row=export_association_sample();row['groups'][0]['popups']*=7;variants.append(row)
        row=export_association_sample();row['groups'] += [{'id':'other','frame':[260,220,502,400],'labels':[],'popups':[]}]*8;variants.append(row)
        row=export_association_sample();row['groups'][0]['popups'][0]['label']='Color Profile';row['groups'][0]['popups']*=2;variants.append(row)
        for row in variants:
            with self.subTest(row=row),self.assertRaises(ValueError):replay_export_association(self.swift,row)
    def test_wrong_sheet_label_parent_row_visibility_and_nonfinite_frames_reject(self):
        mutations=[lambda r:r.update(sheet='other'),lambda r:r.update(field='unrequested'),
            lambda r:r['groups'][0]['labels'][0].update(texts=['Size:']),
            lambda r:r['groups'][0]['labels'][0].update(texts=['Color Profile:','different']),
            lambda r:r['groups'][0]['labels'][0].update(hittable=False),
            lambda r:r['groups'][0]['labels'][0].update(frame=[300,360,104,18]),
            lambda r:r['groups'][0]['labels'][0].update(frame=[300,304,80,18]),
            lambda r:r['groups'][0]['labels'][0].update(frame=[300,float('inf'),104,18]),
            lambda r:r['groups'][0].update(frame=[260,220,502,20]),
            lambda r:r['groups'][0]['popups'][0].update(frame=[410,300,0,26]),
            lambda r:r['groups'][0]['popups'][0].update(enabled=False),
            lambda r:r['groups'][0]['popups'][0].update(hittable=False),
            lambda r:r['groups'][0]['popups'][0].update(id=''),
            lambda r:r['groups'][0]['popups'][0].update(label='unrelated')]
        for mutate in mutations:
            row=export_association_sample();mutate(row)
            with self.subTest(row=row),self.assertRaises(ValueError):replay_export_association(self.swift,row)
    def test_stale_observed_binding_and_value_are_checked_before_click_and_export(self):
        initial=export_association_sample();signature,value=replay_export_association(self.swift,initial)
        for mutate in [lambda r:r['groups'][0].update(id='replacement'),
                       lambda r:r['groups'][0]['labels'][0].update(id='replacement'),
                       lambda r:r['groups'][0]['popups'][0].update(id='replacement'),
                       lambda r:r['groups'][0]['popups'][0].update(frame=[411,300,302,26])]:
            row=copy.deepcopy(initial);mutate(row)
            self.assertNotEqual(replay_export_association(self.swift,row)[0],signature)
        row=copy.deepcopy(initial);row['groups'][0]['popups'][0]['value']='Display P3'
        self.assertNotEqual(replay_export_association(self.swift,row)[1],value)
        body=self.swift.split('@MainActor private func popup(',1)[1].split('@MainActor private func chooseOwnedExportDirectory(',1)[0]
        self.assertLess(body.index('retainExportBinding('),body.index('deadlineClick('))
        self.assertLess(body.index('Stale export option binding before action'),body.index('deadlineClick('))
        self.assertIn('fresh.query.element(boundBy: 0).value as? String == value',body)
        export=self.swift.split('@MainActor private func exportRaster(',1)[1].split('private func readBoundedOwnedFile(',1)[0]
        self.assertLess(export.index('Export option changed before Export'),export.index('"button_export", "Export"'))
    def test_source_ties_reject_weakening_and_disclosure_is_observed_closed_then_expanded(self):
        for old,new in [('groupCount <= 8','groupCount <= 80'),('popupCount <= 6','popupCount <= 60'),
            ('guard aligned.count == 1','guard aligned.count >= 1'),('frame.minX - labelFrame.maxX <= 24','frame.minX - labelFrame.maxX <= 1000'),
            ('aligned.append((candidate, frame))','if candidate.isEnabled { aligned.append((candidate, frame)) }'),
            ('let labelCount = labels.count','let labelCount = labels.count\n        _ = labels.count')]:
            with self.subTest(old=old),self.assertRaises(AssertionError):replay_export_association(self.swift.replace(old,new),export_association_sample())
        for required in ['"Photo Kind": "popup_photoKind"','"File Name": "popup_useFileName"',
            '"Subfolder Format": "popup_subfolderFormat"','"button_disclosure", "customize"',
            'role: "DisclosureTriangle", desired: 1, photos: photos','final.scalar.state == desired',
            'prospective.count <= 6','withJSONObject: receipt).count <= 16_000']:
            self.assertIn(required,self.swift)
        self.assertNotIn('coordinate(',self.swift)

def replay_binary_transition(swift, samples, role='DisclosureTriangle'):
    """Tagged public-value model. Actual Foundation bridging runs in the host case."""
    normalize=swift.split('private static func binaryScalar(',1)[1].split('private func verifyBinaryScalarContract(',1)[0]
    required=['guard let raw else { return nil }','text == "0" || text == "1"','raw as? NSNumber',
        'CFGetTypeID(number) == CFBooleanGetTypeID()','["c", "B"].contains(encoding)',
        '["c", "C", "s", "S", "i", "I", "l", "L", "q", "Q", "f", "d"].contains(encoding)',
        'number.doubleValue.isFinite','number.compare(NSNumber(value: 0)) == .orderedSame, number.decimalValue == Decimal(0)',
        'number.compare(NSNumber(value: 1)) == .orderedSame, number.decimalValue == Decimal(1)']
    observe=swift.split('@MainActor private func observeExportBinary(',1)[1].split('private func retainExportBinary(',1)[0]
    observe_required=['let count = query.count','guard count == 1','identifier == "button_disclosure" && label == "customize"',
        'element.elementType == .disclosureTriangle','element.elementType == .checkBox','xmpLabels.allSatisfy',
        'guard disclosure || sidecar','guard enabled, hittable','let raw = element.value','Self.binaryScalar(raw)']
    transition=swift.split('@MainActor private func setExportBinary(',1)[1].split('private func exportFrame(',1)[0]
    transition_required=['initial.scalar.state != desired','fresh.scalar.state == initial.scalar.state',
        'try retainExportBinary(fresh)','try deadlineClick(fresh.element)','observed.scalar.state == desired',
        'catch { observationFailure = error; return true }','if let observationFailure { throw observationFailure }',
        'final.scalar.state == desired','try retainExportBinary(final)']
    if not all(part in normalize for part in required) or not all(part in observe for part in observe_required) or not all(part in transition for part in transition_required):
        raise AssertionError('Binary scalar/transition source no longer matches model')
    if observe.count('query.count')!=1 or observe.count('element.value')!=1:raise AssertionError('Binary observation resamples state/count')
    if transition.index('try retainExportBinary(fresh)')>transition.index('try deadlineClick(fresh.element)'):raise AssertionError('Binary click precedes bounded evidence')
    pending=copy.deepcopy(samples);trace={'clicks':0,'recorded':[],'failure':None,'accepted':False}
    def need(value):
        if not value:raise ValueError('Invalid binary target/state')
    def read():
        need(bool(pending));row=pending.pop(0)
        need(row['count']==1 and row['enabled'] is True and row['hittable'] is True and row['role']==role)
        if role=='DisclosureTriangle':need(row['id']=='button_disclosure' and row['label']=='customize')
        else:need(role=='CheckBox' and row['label']=='Export IPTC as XMP')
        kind,encoding,raw=row['kind'],row['encoding'],row['raw']
        if kind=='string':need(encoding=='' and type(raw) is str and raw in ('0','1'));state=int(raw)
        elif kind=='boolean':need(encoding in ('c','B') and type(raw) is bool);state=int(raw)
        else:
            need(kind=='number' and encoding in ('c','C','s','S','i','I','l','L','q','Q','f','d') and type(raw) in (int,float)
                 and raw in (0,1) and math.isfinite(raw));state=int(raw)
        return (row['role'],row['id'],row['label']),state
    try:
        need(role in ('DisclosureTriangle','CheckBox'));wanted=1 if role=='DisclosureTriangle' else 0
        identity,initial=read();trace['recorded'].append(initial)
        if initial!=wanted:
            fresh,state=read();need(fresh==identity and state==initial);trace['recorded'].append(state);trace['clicks']+=1
            while True:
                fresh,state=read();need(fresh==identity)
                if state==wanted:break
        fresh,state=read();need(fresh==identity and state==wanted);trace['recorded'].append(state);trace['accepted']=True
    except ValueError as error:trace['failure']=str(error)
    trace['unobserved']=pending
    return trace

def binary_sample(value=0,kind='number',role='DisclosureTriangle'):
    return {'count':1,'enabled':True,'hittable':True,'role':role,'id':'button_disclosure' if role=='DisclosureTriangle' else 'synthetic_xmp',
            'label':'customize' if role=='DisclosureTriangle' else 'Export IPTC as XMP','kind':kind,
            'encoding':'' if kind=='string' else 'c' if kind=='boolean' else 'i','raw':value}

class BinaryScalarSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.swift=(ROOT/'Platforms/UITests/MacPhotosHostUITests.swift').read_text()
    def test_typed_transition_and_already_correct_state_do_not_toggle_blindly(self):
        for kind,convert in [('string',str),('boolean',bool),('number',int),('number',float)]:
            for role,wanted in [('DisclosureTriangle',1),('CheckBox',0)]:
                rows=[binary_sample(convert(v),kind,role) for v in [1-wanted,1-wanted,wanted,wanted]]
                result=replay_binary_transition(self.swift,rows,role)
                self.assertTrue(result['accepted']);self.assertEqual(result['clicks'],1)
                self.assertEqual(result['recorded'],[1-wanted,1-wanted,wanted])
                result=replay_binary_transition(self.swift,[binary_sample(convert(wanted),kind,role)]*2,role)
                self.assertTrue(result['accepted']);self.assertEqual(result['clicks'],0)
    def test_missing_mixed_fractional_nonfinite_and_arbitrary_values_stop_without_click(self):
        for kind,values in [('string',[None,'','mixed',' 0','01','+1','1.0','true','false','2',0]),
            ('number',[None,[],{},False,-1,2,10**400,.5,float('nan'),float('inf'),float('-inf')]),('boolean',[None,0,1,'false']),('unknown',[0])]:
            for value in values:
                with self.subTest(kind=kind,value=value):
                    result=replay_binary_transition(self.swift,[binary_sample(value,kind)])
                    self.assertFalse(result['accepted']);self.assertEqual(result['clicks'],0)
    def test_stale_duplicate_or_unusable_preclick_state_cannot_be_resampled_away(self):
        for mutation in [dict(count=0),dict(count=2),dict(enabled=False),dict(hittable=False),dict(raw=1),dict(raw=None),dict(id='replacement'),dict(label='other')]:
            fresh=binary_sample();fresh.update(mutation)
            result=replay_binary_transition(self.swift,[binary_sample(),fresh,binary_sample(),binary_sample(1),binary_sample(1)])
            self.assertFalse(result['accepted']);self.assertEqual(result['clicks'],0);self.assertEqual(len(result['unobserved']),3)
    def test_postclick_invalid_snapshot_latches_and_final_state_must_still_match(self):
        for mutation in [dict(count=2),dict(raw='mixed'),dict(raw=None),dict(enabled=False),dict(id='replacement')]:
            bad=binary_sample();bad.update(mutation)
            result=replay_binary_transition(self.swift,[binary_sample(),binary_sample(),bad,binary_sample(1),binary_sample(1)])
            self.assertFalse(result['accepted']);self.assertEqual(result['clicks'],1);self.assertEqual(len(result['unobserved']),2)
        result=replay_binary_transition(self.swift,[binary_sample(),binary_sample(),binary_sample(1),binary_sample(0)])
        self.assertFalse(result['accepted']);self.assertEqual(result['clicks'],1)
    def test_native_foundation_adversaries_precede_ui_and_only_two_paths_are_normalized(self):
        body=self.swift.split('@MainActor func testInstalledExtensionIsInvokedByActualPhotos()',1)[1]
        self.assertLess(body.index('try verifyBinaryScalarContract()'),body.index('app.launch()'))
        tests=self.swift.split('private func verifyBinaryScalarContract()',1)[1].split('@MainActor private func observeExportBinary(',1)[0]
        for value in ['NSString(string: "0")','NSNumber(value: false)','NSNumber(value: true)','NSNumber(value: Int64(0))',
            'NSNumber(value: UInt64(1))','NSNumber(value: Float(1))','NSNumber(value: Double.nan)',
            'NSNumber(value: Double.infinity)','NSDecimalNumber(string: "1.00000000000000000001")','NSDecimalNumber.notANumber','Data([0])']:
            self.assertIn(value,tests)
        self.assertIn('binaryScalarSelfTested = true',tests)
        export=self.swift.split('@MainActor private func exportRaster(',1)[1].split('private func readBoundedOwnedFile(',1)[0]
        self.assertEqual(export.count('try setExportBinary('),2)
        self.assertNotIn('sidecar.value as? String',export);self.assertNotIn('disclosure.value as? String',export)
        self.assertIn('fresh.query.element(boundBy: 0).value as? String == wanted',export)
        normalize=self.swift.split('private static func binaryScalar(',1)[1].split('private func verifyBinaryScalarContract(',1)[0]
        for forbidden in ['debugDescription','intValue','String(describing:','?? 0']:self.assertNotIn(forbidden,normalize)
        self.assertIn('prospective.count <= 12',self.swift);self.assertIn('encoded.count <= 256',self.swift)
    def test_source_ties_reject_scalar_weakening_and_resampled_value(self):
        for old,new in [('number.doubleValue.isFinite','true'),('text == "0" || text == "1"','!text.isEmpty'),
            ('number.decimalValue == Decimal(1)','true'),('guard count == 1 else { throw block("Missing/ambiguous export binary control"','guard count >= 1 else { throw block("Missing/ambiguous export binary control"'),
            ('let raw = element.value','let raw = element.value\n        _ = element.value'),
            ('fresh.scalar.state == initial.scalar.state','true'),('if let observationFailure { throw observationFailure }','if let observationFailure { print(observationFailure) }')]:
            with self.subTest(old=old),self.assertRaises(AssertionError):replay_binary_transition(self.swift.replace(old,new),[binary_sample(1)]*2)

if __name__=='__main__':unittest.main()
