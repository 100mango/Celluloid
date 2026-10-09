from validation_route import FULL,host_clock_profile,context_clock
#!/usr/bin/env python3
"""Portable gate contract tests. These cannot execute Apple Photos or Swift/XCUI."""
from pathlib import Path
from unittest import mock
import hashlib
import base64
import struct
import zlib
import importlib.util
import json
import os
import runpy
import subprocess
import sys
import tempfile
import unittest
import re
from validation_route import FULL as FULL_ROUTE, FOCUSED as FOCUSED_ROUTE

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('gate', ROOT / 'Scripts/mac_photos_host_gate.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

def replay_ready_editor_snapshots(swift, snapshots):
    """Source-tied control-flow model, not Swift compilation or Apple execution.

    Inputs represent successive actual count observations, not unseen UI changes.
    One input is consumed per poll/final resample; later clean inputs cannot erase
    an observed contradiction. The explicit traces show exactly what was read.
    """
    body=swift.split('@MainActor private func readyEditorObservation',1)[1].split('@MainActor private func checkpoint',1)[0]
    required=['let editorCount = matches.count','"editor_count": editorCount',
        'guard editorCount == 1 else { return row }','let filterCount = filter.count',
        '"filter_count": filterCount','"filter_enabled": filterCount == 1 && filter.element(boundBy: 0).isEnabled',
        'return row["editor_count"] as? Int == 1','if (row["editor_count"] as? Int ?? 0) > 1',
        'if let contradiction { throw block(contradiction) }','let observed = observations()',
        'guard ready(observed) else {']
    if body.count('matches.count')!=1 or body.count('filter.count')!=1 or any(item not in body for item in required):
        raise AssertionError('Readiness model no longer matches single-count Swift invariants')
    pending=list(snapshots);trace={'editor_counts_observed':[],'filter_counts_observed':[],
        'poll_rows':[],'final_row':None,'failure':None,'accepted':False}
    def observations():
        if not pending:raise AssertionError('Model needs an explicit next observation')
        sample=pending.pop(0);editor_count=sample.get('editor_count',1)
        trace['editor_counts_observed'].append(editor_count);row={'editor_count':editor_count}
        if editor_count!=1:return row
        filter_count=sample.get('filter_count',1);trace['filter_counts_observed'].append(filter_count)
        row.update(preview_count=sample.get('preview_count',1),placeholder_count=sample.get('placeholder_count',0),
            preparing_count=sample.get('preparing_count',0),filter_count=filter_count,
            filter_enabled=filter_count==1 and sample.get('filter_enabled',True),
            read_only_count=sample.get('read_only_count',0),error_count=sample.get('error_count',0))
        return row
    def ready(row):
        return all(row.get(k)==v for k,v in [('editor_count',1),('preview_count',1),('placeholder_count',0),
            ('preparing_count',0),('filter_count',1),('read_only_count',0),('error_count',0)]) and row.get('filter_enabled') is True
    while pending:
        row=observations();trace['poll_rows'].append(row)
        if row['editor_count']>1:trace['failure']='observed duplicate editor';break
        if any(row.get(k,0)>1 for k in ['preview_count','placeholder_count','preparing_count','filter_count']):
            trace['failure']='observed duplicate control';break
        if row.get('read_only_count',0)>0 or row.get('error_count',0)>0:
            trace['failure']='observed read-only/error';break
        if ready(row):
            trace['final_row']=observations()
            trace['accepted']=ready(trace['final_row'])
            if not trace['accepted']:trace['failure']='final resample not ready'
            break
    if not trace['accepted'] and trace['failure'] is None:trace['failure']='readiness timeout'
    trace['unobserved_remaining']=pending
    return trace

class MacPhotosHostGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (ROOT / '.github/workflows/apple-platforms.yml').read_text()
        cls.swift = (ROOT / 'Platforms/UITests/MacPhotosHostUITests.swift').read_text()
        cls.shell = (ROOT / 'Scripts/run_mac_photos_host_gate.sh').read_text()

    def test_production_and_all_existing_test_bytes_remain_frozen(self):
        from staged_test_fixtures import historical_checkout
        with historical_checkout() as root, mock.patch.dict(globals(),ROOT=root):
            self._assert_historical_production_and_test_bytes()

    def _assert_historical_production_and_test_bytes(self):
        contract = json.loads((ROOT / 'Scripts/mac-photos-host-source-base.json').read_text())
        self.assertEqual(len(contract['files']), gate.BASE_FILE_COUNT)
        count = 0
        for path, digest in contract['files']:
            if path in {'CelluloidNative.xcodeproj/project.pbxproj', 'Platforms/UITests/NativeEditorUITests.swift'}: continue
            if path in gate.REVIEWED_CANDIDATE_FILES:
                self.assertEqual(gate.sha(ROOT/path),gate.REVIEWED_CANDIDATE_FILES[path]);continue
            if path in gate.REVIEWED_TEST_FILES:
                self.assertEqual(gate.sha(ROOT/path),gate.REVIEWED_TEST_FILES[path]);continue
            self.assertEqual(gate.sha(ROOT / path), digest, path)
            count += 1
        self.assertEqual(count, gate.UNCHANGED_BASE_FILES)

    def test_generated_project_adds_only_opt_in_ui_source(self):
        previous = (ROOT / 'CelluloidNative.xcodeproj/project.pbxproj').read_bytes()
        graph = runpy.run_path(str(ROOT / 'Scripts/generate_native_project.py'))
        self.assertEqual((ROOT / 'CelluloidNative.xcodeproj/project.pbxproj').read_bytes(), previous)
        objects = graph['objects']
        members = []
        for name, identifier in graph['targets'].items():
            for phase in objects[identifier]['buildPhases']:
                if objects[phase]['isa'] == 'PBXSourcesBuildPhase':
                    paths = [objects[objects[f]['fileRef']]['path'] for f in objects[phase]['files']]
                    if 'Platforms/UITests/MacPhotosHostUITests.swift' in paths: members.append(name)
        self.assertEqual(members, ['CelluloidMacUITests'])

    def test_existing_serial_workflow_and_independent_host_prerequisite(self):
        self.assertIn('    branches: [' + gate.BRANCH + ']', self.workflow)
        self.assertEqual(re.findall(r'^  ([a-z-]+):$',self.workflow.split('jobs:\n',1)[1],re.M), ['build-preflight','native-mac','native-mac-host','native-simulator','uikit-regression','archive'])
        host=self.workflow.split('- name: Actual Photos host discovery',1)[1].split('- name:',1)[0]
        self.assertIn("steps.sandbox_child.outcome == 'success'",host)
        self.assertNotIn('early_interop',host)
        self.assertIn('  cancel-in-progress: false',self.workflow)
        self.assertEqual(self.workflow.count('max-parallel: 1'),2)
    def test_mac_checkout_fetches_immutable_base_without_deepening_current_head(self):
        mac=self.workflow.split('  native-mac-host:',1)[1].split('  native-simulator:',1)[0]
        self.assertEqual(mac.count('fetch-depth: 1'),1)
        fetch=mac.split('- name: Fetch and verify immutable Photos host source base',1)[1].split('- name:',1)[0]
        self.assertIn("base='"+gate.BASE+"'",fetch);self.assertIn("tree='"+gate.BASE_TREE+"'",fetch)
        self.assertIn("run(['git','fetch','--no-tags','--depth=1','origin',base],timeout=60)",fetch)
        self.assertIn("base+'^{commit}'],text=True,timeout=10).strip()==base",fetch)
        self.assertIn("base+'^{tree}'],text=True,timeout=10).strip()==tree",fetch)
        self.assertIn('from native_process import run',fetch)
        for forbidden in ['token','credential','git config','--unshallow']:self.assertNotIn(forbidden,fetch)
        # Fetch one immutable object in a tiny local shallow clone. The checked
        #out head remains unchanged and shallow regardless of ancestor distance.
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();seed=root/'seed';seed.mkdir()
            def git(*args):return subprocess.check_output(['git',*map(str,args)],text=True,stderr=subprocess.STDOUT,timeout=10)
            git('init','--quiet',seed);commits=[]
            for content in ['pinned-base','intermediate','published-parent','test-fix-successor']:
                (seed/'fixture.txt').write_text(content);git('-C',seed,'add','fixture.txt')
                git('-C',seed,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','--quiet','-m',content)
                commits.append(git('-C',seed,'rev-parse','HEAD').strip())
            clone=root/'shallow';git('clone','--quiet','--depth','1',seed.as_uri(),clone)
            absent=subprocess.run(['git','-C',str(clone),'cat-file','-e',commits[0]+'^{commit}'],capture_output=True,text=True,timeout=10)
            self.assertNotEqual(absent.returncode,0)
            git('-C',clone,'fetch','--no-tags','--depth=1','origin',commits[0])
            self.assertEqual(git('-C',clone,'rev-parse',commits[0]+'^{commit}').strip(),commits[0])
            self.assertEqual(git('-C',clone,'rev-parse',commits[0]+'^{tree}'),git('-C',seed,'rev-parse',commits[0]+'^{tree}'))
            self.assertEqual(git('-C',clone,'rev-parse','HEAD').strip(),commits[-1]);self.assertEqual(git('-C',clone,'rev-list','--count','HEAD').strip(),'1')

    def test_fresh_host_row_rebuilds_exact_product_without_pixel_or_seed_dependency(self):
        host=self.workflow.split('  native-mac-host:',1)[1].split('  native-simulator:',1)[0]
        mac=self.workflow.split('  native-mac:',1)[1].split('  native-mac-host:',1)[0]
        sim=self.workflow.split('  native-simulator:',1)[1].split('  uikit-regression:',1)[0]
        self.assertIn('needs: [build-preflight, native-mac]',host)
        self.assertIn("if: always() && needs.build-preflight.result == 'success'",host)
        self.assertNotIn('continuation_safe',host)
        self.assertIn('needs: [build-preflight, native-mac, native-mac-host]',sim)
        self.assertNotIn('needs.native-mac-host.result',sim)
        self.assertNotIn('run_mac_photos_host_gate.sh',mac)
        self.assertNotIn('download-artifact',host)
        self.assertNotIn('TEST_RUNNER_CELLULOID_HOST_SEED_SOURCE_SHA',host)
        self.assertIn('--seconds 600 --label fresh-host-ui-build',host)
        self.assertIn('--seconds 300 --label fresh-host-app-build',host)
        self.assertIn('CODE_SIGN_IDENTITY=-',host)
        self.assertIn("'execution_budget_seconds':41*60",host)
        self.assertEqual(host.count('verify_combined_source.py --phase'),2)
        self.assertLess(host.index('verify_combined_source.py --phase after'),host.index('mac_photos_host_gate.py accept'))
        self.assertEqual(host.count('retention-days: 1'),1)

    def test_existing_runtime_and_caps_reuse_compiled_product(self):
        self.assertIn('    timeout-minutes: 45',self.workflow)
        self.assertIn('        timeout-minutes: 14',self.workflow)
        self.assertIn('process_seconds=720',self.shell)
        self.assertIn('test_seconds=660',self.shell)
        self.assertNotIn('build-for-testing',self.shell)
        self.assertNotIn('CODE_SIGN_IDENTITY',self.shell)
        self.assertIn('celluloid-sandbox',self.shell)
    def test_artifacts_share_existing_mac_allocation(self):
        self.assertEqual(self.workflow.count('uses: actions/upload-artifact@'),6)
        self.assertIn('path: ${{ runner.temp }}/mac-host-evidence/',self.workflow)
        self.assertEqual(gate.CAP,1_000_000)
        collector=(ROOT/'Scripts/collect_native_evidence.py').read_text()
        self.assertIn("record=verify_collected(folder,os.environ['GITHUB_SHA'])",collector)
        self.assertIn('independently replayed host proof manifest',collector)
        budgets=runpy.run_path(str(ROOT/'Scripts/combined_evidence_budget.py'))
        self.assertEqual(budgets['BUDGETS']['mac'],2_000_000)
        self.assertEqual(sum(budgets['BUDGETS'].values()),19_500_000)

    def test_primary_failure_is_recorded_before_optional_confirmed_photos_capture(self):
        body=self.swift.split('@MainActor func testInstalledExtensionIsInvokedByActualPhotos()',1)[1]
        cleanup=body.split('        defer {',1)[1].split('        stage = "launch-exact-installed-containing-app"',1)[0]
        self.assertLess(cleanup.index('named: "outcome.json"'),cleanup.index('checkpoint(photos'))
        self.assertIn('if photosIdentityVerified, (try? remainingTime(1)) != nil {',cleanup)
        self.assertIn('MAC_HOST_DIAGNOSTIC_FAILED',cleanup)
        self.assertLess(body.index('named: "photos-process.json"'),body.index('photosIdentityVerified = true'))
        self.assertIn('if firstBlockedOperation == nil',self.swift)
        self.assertNotIn('p.terminationStatus',self.swift)  # The denied helper is retired, never retried.
        self.assertIn('"reason": String(reason.prefix(2000))',self.swift)
        self.assertIn('outcome["first_blocked_operation"] = firstBlockedOperation',cleanup)
        self.assertIn('print("MAC_HOST_BLOCKED stage=" + stage + " reason=" + reason)',self.swift)
        self.assertNotIn('actual Manage state captured',self.swift)
        self.assertIn('no settings action was taken',self.swift)

    def test_menu_classification_survives_export_failure_in_bounded_stdout_outcome(self):
        self.assertLess(self.swift.index('extensionMenuObservation = ['),self.swift.index('checkpoint(photos, "extensions", screenshot: true)'))
        self.assertIn('outcome["extension_menu_observation"] = extensionMenuObservation',self.swift)
        self.assertIn('let menuCount = celluloid.count',self.swift)
        self.assertEqual(self.swift.count('celluloid.count'),1)
        for state in ['no-matching-item','ambiguous','disabled','not-hittable','selectable']:
            self.assertIn('"'+state+'"',self.swift)
        self.assertIn('menuEnabled.map { $0 as Any } ?? NSNull()',self.swift)
        self.assertIn('menuHittable.map { $0 as Any } ?? NSNull()',self.swift)
        self.assertIn('"schema": "Celluloid.HostMenuObservation.2", "acceptance": false',self.swift)

    def test_menu_is_freshly_revalidated_after_checkpoint_without_mixing_snapshots(self):
        body=self.swift.split('        let editorCountBefore =',1)[1].split('        stage = "invoke-real-photos-extension"',1)[0]
        self.assertEqual(body.count('invocationItems.count'),1)
        self.assertLess(self.swift.index('checkpoint(photos, "extensions", screenshot: true)'),self.swift.index('let invocationMenuCount ='))
        self.assertLess(body.index('try hostObservation('),body.index('let invocationMenuCount ='))
        self.assertLess(body.index('let invocationMenuCount ='),body.index('named: "host-selection.json"'))
        self.assertIn('"menu_count": invocationMenuCount, "menu_enabled": invocationEnabled == true',body)
        self.assertIn('"menu_hittable": invocationHittable == true',body)
        for exact in ['invocationMenuCount == menuCount, invocationMenuCount == 1',
                      'invocationEnabled == menuEnabled, invocationEnabled == true',
                      'invocationHittable == menuHittable, invocationHittable == true']:
            self.assertIn(exact,body)
        # Executable transition model tied to the source conditions above. These
        # are observed states, not a claim about unobserved intervals.
        def permitted(early,fresh):
            return early==(1,True,True) and fresh[0]==early[0]==1 and fresh[1]==early[1] is True and fresh[2]==early[2] is True
        self.assertTrue(permitted((1,True,True),(1,True,True)))
        for fresh in [(0,None,None),(2,None,None),(1,False,True),(1,True,False),(1,False,False)]:
            with self.subTest(fresh=fresh):self.assertFalse(permitted((1,True,True),fresh))
        self.assertFalse(permitted((0,None,None),(1,True,True)))

    def test_exact_title_identifier_and_opened_menu_scope_have_no_label_fallback(self):
        helper=self.swift.split('@MainActor private func openedExtensionItems',1)[1].split('@MainActor private func editorMatches',1)[0]
        for exact in ['.menuButton','"label == %@", "Extensions"','guard buttonCount == 1',
            'children(matching: .menu)','guard menuCount == 1','!menu.frame.isEmpty',
            'menu.children(matching: .menuItem)','"title == %@ AND identifier == %@", "Celluloid", "editWithPlugin:"']:
            self.assertIn(exact,helper)
        self.assertNotIn(' OR ',helper);self.assertNotIn('"label == %@", "Celluloid"',self.swift)
        self.assertEqual(self.swift.count('try openedExtensionItems(in: photos)'),3)  # two initial checks plus exact lifecycle reentry
        # Exact observed title, identifier and parent scope are conjunctive.
        def matches(item):return item['scope']=='Extensions.menuButton/childMenu/directMenuItem' and item['title']=='Celluloid' and item['identifier']=='editWithPlugin:'
        good={'scope':'Extensions.menuButton/childMenu/directMenuItem','title':'Celluloid','identifier':'editWithPlugin:','label':''}
        self.assertTrue(matches(good))
        for fields in [{'title':'Other','label':'Celluloid'},{'identifier':'Other'}, {'scope':'Photos.menuBar/hiddenMenu'}]:
            self.assertFalse(matches(dict(good,**fields)))
        self.assertEqual(sum(matches(item) for item in [good,dict(good)]),2)

    def test_unknown_interruptions_abort_without_alert_action(self):
        handler = self.swift.split('addUIInterruptionMonitor', 1)[1].split('let input', 1)[0]
        self.assertIn('fatalError("MAC_HOST_FAIL_CLOSED_ABORT")', handler)
        for forbidden in ['.click(', '.tap(', 'return true', 'return false', 'XCTFail']:
            self.assertNotIn(forbidden, handler)
        self.assertLess(self.swift.index('addUIInterruptionMonitor'), self.swift.index('app.launch()'))

    def test_no_privacy_registration_or_security_override(self):
        for source in [self.swift, self.shell, (ROOT / 'Scripts/mac_photos_host_gate.py').read_text()]:
            for forbidden in ['tccutil', 'spctl', 'sqlite3', 'killall', 'pluginkit -e', 'pluginkit -a', 'xattr -d',
                              'security add', 'security unlock', 'defaults write', 'PHPhotoLibrary.requestAuthorization']:
                self.assertNotIn(forbidden, source)
        self.assertNotIn('coordinate(', self.swift)
        self.assertNotIn('MacPhotoEditingController(', self.swift)

    def test_production_ids_and_live_path_hash_are_both_required(self):
        self.assertEqual(gate.APP_ID, 'Mango.Celluloid')
        self.assertEqual(gate.EXT_ID, 'Mango.Celluloid.CelluloidPhotoExtension')
        self.assertNotIn('pluginkit',self.swift)
        self.assertIn('host-selection.json',self.swift)
        self.assertIn('host-editor-before-process.json',self.swift)
        self.assertIn('host-editor-after-process.json',self.swift)
        source = (ROOT / 'Scripts/mac_photos_host_gate.py').read_text()
        self.assertNotIn('lib.proc_pidpath(pid', source)
        self.assertIn('actual=validate_self_identity(self_identity,c,photos,ownership)',source)
        self.assertIn("'os_wide_process_uniqueness':False",source)
        self.assertIn("'extension_debug_dylib_sha256'",source)

    def test_v3_source_observes_enabled_selection_and_ready_editor_around_self_identity(self):
        self.assertNotIn('pluginkit',self.swift)
        self.assertNotIn('assertUniqueRegistration',self.swift)
        self.assertIn('menuEnabled != true || menuHittable != true',self.swift)
        self.assertIn('XCTAssertEqual(editorCountBefore, 0',self.swift)
        self.assertLess(self.swift.index('named: "host-selection.json"'),self.swift.index('try deadlineClick(invocationItems.element(boundBy: 0))'))
        self.assertLess(self.swift.index('named: "host-editor-before-process.json"'),self.swift.index('named: "extension-self-identity.json"'))
        self.assertLess(self.swift.index('named: "extension-self-identity.json"'),self.swift.index('named: "host-editor-after-process.json"'))
        for label in ['Celluloid photo editor','Edited photo preview','Current photo from Photos','Preparing photo']:
            self.assertIn(label,self.swift)
        self.assertIn('XCTAssertEqual(host.processIdentifier, expectedPID',self.swift)
        self.assertIn('XCTNSPredicateExpectation',self.swift)
        self.assertIn('if phase == "before-process" {',self.swift)
        self.assertIn('if (row["editor_count"] as? Int ?? 0) > 1 {',self.swift)
        self.assertIn('if let contradiction { throw block(contradiction) }',self.swift)
        self.assertIn('Read-only or error state during host entry',self.swift)
        self.assertIn('Photos identity changed during host-entry readiness',self.swift)
        self.assertIn('guard ready(observed)',self.swift)
        self.assertIn('guard editorCount == 1 else { return row }',self.swift)
        self.assertNotIn('coordinate(',self.swift)

    def test_ready_editor_counts_are_single_snapshots_used_by_every_decision(self):
        body=self.swift.split('@MainActor private func readyEditorObservation',1)[1].split('@MainActor private func checkpoint',1)[0]
        self.assertEqual(body.count('matches.count'),1)
        self.assertEqual(body.count('filter.count'),1)
        self.assertIn('let editorCount = matches.count',body)
        self.assertIn('"editor_count": editorCount',body)
        self.assertIn('guard editorCount == 1 else { return row }',body)
        self.assertIn('let filterCount = filter.count',body)
        self.assertIn('"filter_count": filterCount',body)
        self.assertIn('"filter_enabled": filterCount == 1 && filter.element(boundBy: 0).isEnabled',body)
        self.assertIn('return row["editor_count"] as? Int == 1',body)
        self.assertIn('if (row["editor_count"] as? Int ?? 0) > 1',body)
        self.assertNotIn('return nil',body)

    def test_ready_snapshot_loading_then_ready_has_explicit_single_read_traces(self):
        cases=[
            ([{'editor_count':0},{'preview_count':0,'placeholder_count':1,'preparing_count':1,'filter_enabled':False},{},{}],[0,1,1,1],[1,1,1]),
            ([{'filter_count':0},{},{}],[1,1,1],[0,1,1])]
        for snapshots,editors,filters in cases:
            with self.subTest(snapshots=snapshots):
                trace=replay_ready_editor_snapshots(self.swift,snapshots)
                self.assertTrue(trace['accepted']);self.assertIsNone(trace['failure'])
                self.assertEqual(trace['editor_counts_observed'],editors)
                self.assertEqual(trace['filter_counts_observed'],filters)

    def test_observed_duplicate_cannot_be_erased_by_later_clean_snapshot(self):
        for duplicate,key in [({'editor_count':2},'editor_counts_observed'),({'filter_count':2},'filter_counts_observed')]:
            for loading in [[],[{'preview_count':0,'preparing_count':1}]]:
                with self.subTest(duplicate=duplicate,loading=loading):
                    trace=replay_ready_editor_snapshots(self.swift,loading+[duplicate,{},{}])
                    self.assertFalse(trace['accepted']);self.assertIn('observed duplicate',trace['failure'])
                    self.assertEqual(trace[key][-1],2);self.assertEqual(trace['unobserved_remaining'],[{},{}])
                    self.assertIsNone(trace['final_row'])

    def test_final_snapshot_duplicate_is_fatal_without_recovery_wait(self):
        for duplicate,key in [({'editor_count':2},'editor_counts_observed'),({'filter_count':2},'filter_counts_observed')]:
            with self.subTest(duplicate=duplicate):
                trace=replay_ready_editor_snapshots(self.swift,[{},duplicate,{}])
                self.assertFalse(trace['accepted']);self.assertEqual(trace['failure'],'final resample not ready')
                self.assertEqual(trace[key],[1,2]);self.assertEqual(trace['unobserved_remaining'],[{}])

    def test_snapshot_model_never_invents_an_unobserved_ui_contradiction(self):
        trace=replay_ready_editor_snapshots(self.swift,[{},{},{'editor_count':2}])
        self.assertTrue(trace['accepted']);self.assertEqual(trace['editor_counts_observed'],[1,1])
        self.assertEqual(trace['unobserved_remaining'],[{'editor_count':2}])
        # A mutation back to a second dynamic count read breaks the source tie.
        for old,new in [('"editor_count": editorCount','"editor_count": matches.count'),
                        ('"filter_enabled": filterCount == 1','"filter_enabled": filter.count == 1')]:
            with self.assertRaisesRegex(AssertionError,'single-count Swift invariants'):
                replay_ready_editor_snapshots(self.swift.replace(old,new),[{},{}])

    def test_bundle_manifest_detects_bytes_membership_and_symlinks(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'binary').write_bytes(b'a'); (root / 'alias').symlink_to('binary')
            first = gate.bundle_manifest(root)
            (root / 'binary').write_bytes(b'b')
            self.assertNotEqual(first, gate.bundle_manifest(root))
            self.assertEqual(first[0], ['alias', 'symlink', 'binary'])
            (root / 'extra').write_bytes(b'c')
            self.assertEqual(len(gate.bundle_manifest(root)), 3)

    def test_collection_stays_bounded_and_excludes_raw_payloads(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, {'RUNNER_TEMP': folder, 'GITHUB_SHA': 'a'*40}):
            root = Path(folder); gate.write(root/'mac-host-acceptance.json', {'validation_route':dict(FULL_ROUTE),'host_entry_contract':gate.HOST_CONTRACT,'source_sha':'a'*40,'prerequisite_accepted':False,'complete_host_e2e':False,'error':'AssertionError: discovery failed'}); observed = root / 'mac-host-observed'; observed.mkdir()
            (observed / 'extensions.jpg').write_bytes(b'a' * 600_000)
            (observed / 'last-observed.jpg').write_bytes(b'b' * 600_000)
            for index in range(22): (observed / f'phase-{index:02d}.txt').write_bytes(b'x' * 140_000)
            (observed / 'oversize.txt').write_bytes(b'x' * 200_000)
            (observed / 'raw.xcresult').mkdir()
            (observed / 'credentials.bin').write_bytes(b'do not collect')
            (observed / 'link.txt').symlink_to('phase-00.txt')
            (root / 'mac-host-test.log').write_text('observed discovery failure\n')
            gate.collect()
            result = root / 'mac-host-evidence'; manifest = json.loads((result / 'manifest.json').read_text())
            self.assertLessEqual(sum(p.stat().st_size for p in result.iterdir()), gate.CAP)
            self.assertTrue(manifest['omitted'])
            self.assertFalse(manifest['complete_host_e2e'])
            self.assertFalse((result / 'credentials.bin').exists())
            self.assertFalse((result / 'raw.xcresult').exists())
            self.assertFalse((result / 'link.txt').exists())
            for entry in manifest['files']:
                self.assertEqual(gate.sha(result / entry['path']), entry['sha256'])

    def test_report_does_not_equate_prerequisite_with_full_lifecycle(self):
        self.assertIn('"prerequisite_passed": true, "complete_host_e2e": false', self.swift)
        self.assertIn('save_reopen_cancel_revert', self.swift)
        self.assertIn('PhotosFilterLifecycle.1 incomplete',self.swift)
        self.assertIn('dirty Cancel untested',self.swift)
        self.assertIn('\"dirty_cancel_tested\": false',self.swift)
        self.assertNotIn('settings = XCUIApplication', self.swift)

    def test_optimized_python_rejects_before_any_action_or_acceptance(self):
        script = str(ROOT / 'Scripts/mac_photos_host_gate.py')
        for flags, inherited in [(['-O'], None), (['-OO'], None), ([], '1')]:
            with self.subTest(flags=flags, inherited=inherited), tempfile.TemporaryDirectory() as folder:
                environment = dict(os.environ, RUNNER_TEMP=folder)
                environment.pop('PYTHONOPTIMIZE', None)
                if inherited is not None: environment['PYTHONOPTIMIZE'] = inherited
                result = subprocess.run([sys.executable, *flags, script, 'accept'], env=environment,
                                        capture_output=True, text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('RuntimeError: Mac Photos host gate refuses optimized Python', result.stderr)
                self.assertNotIn('MAC_HOST_ACCEPTANCE', result.stdout + result.stderr)
                self.assertEqual(list(Path(folder).iterdir()), [])

    def test_python_and_shell_syntax(self):
        compile((ROOT / 'Scripts/mac_photos_host_gate.py').read_text(), 'gate.py', 'exec')
        subprocess.run(['/bin/bash', '-n', str(ROOT / 'Scripts/run_mac_photos_host_gate.sh')], check=True)
        syntax = runpy.run_path(str(ROOT / 'Scripts/test_native_workflow_syntax.py'))
        for _, body in syntax['run_blocks'](self.workflow):
            subprocess.run(['/bin/bash', '-n'], input=body, text=True, check=True)

class SeedReceiptTests(unittest.TestCase):
    def packet(self):
        def chunk(kind,data): return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
        png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1200,800,8,6,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\x20\x80\xe0\xff'*1200)*800))+chunk(b'IEND',b'')
        return {'source_sha':'a'*40,'app_executable_sha256':'b'*64,'initial_empty_welcome_verified':True,
                'imported_pixel_samples_passed':True,'initial_count':0,'imported_count':1,
                'fixture_kind':'native-ui-solid-blue','filename':'Synthetic.png','width':1200,'height':800,
                'asset_label':'Oct 4 synthetic asset','fixture_sha256':hashlib.sha256(png).hexdigest(),
                'fixture_base64':base64.b64encode(png).decode(),'imported_source_sha256':'c'*64}
    def log(self,row):
        owner,method=gate.SEED_CASE
        return "Test Case '-["+owner+' '+method+"]' started.\nMAC_HOST_SEED_RECEIPT "+json.dumps(row)+"\nTest Case '-["+owner+' '+method+"]' passed (1.0 seconds).\n"
    def test_exact_source_app_fixture_and_unique_execution_are_required(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'sandbox.log'; row=self.packet();path.write_text(self.log(row))
            receipt=gate.seed_receipt(path,'a'*40,'b'*64)
            self.assertEqual(receipt['mode'],'reuse-exact-sole-seeded-asset')
            self.assertEqual(receipt['fixture_sha256'],row['fixture_sha256'])
            self.assertEqual(receipt['seed_log_sha256'],gate.sha(path))
    def test_unknown_or_unbound_seed_cannot_select_a_photo(self):
        bad=[{'source_sha':'f'*40},{'app_executable_sha256':'f'*64},{'initial_empty_welcome_verified':False},
             {'initial_count':1},{'initial_count':False},{'imported_count':2},{'imported_count':True},
             {'imported_pixel_samples_passed':False},{'asset_label':''},{'fixture_sha256':'0'*64},
             {'width':1199},{'fixture_kind':'guessed'},{'filename':'other.png'}]
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'sandbox.log'
            for values in bad:
                row=self.packet();row.update(values);path.write_text(self.log(row))
                with self.subTest(values=values),self.assertRaises((AssertionError,ValueError)):gate.seed_receipt(path,'a'*40,'b'*64)
            text=self.log(self.packet())
            for value in [text+text,text.replace(' passed ',' failed '),'\n'.join(l for l in text.splitlines() if not l.startswith('MAC_HOST_SEED_RECEIPT '))]:
                path.write_text(value)
                with self.assertRaises(AssertionError):gate.seed_receipt(path,'a'*40,'b'*64)
    def test_absent_prior_execution_only_admits_observed_empty_library_route(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'absent.log'
            self.assertEqual(gate.seed_receipt(path,'a'*40,'b'*64),{'mode':'require-empty-library'})
            source=(ROOT/'Platforms/UITests/MacPhotosHostUITests.swift').read_text()
            self.assertIn('XCTAssertEqual(empty.value as? String, "Welcome to Photos"',source)
            self.assertIn('XCTAssertEqual(assets.count, 0)',source)
            self.assertIn('XCTAssertEqual(assets.firstMatch.label, seed["asset_label"] as? String)',source)
            self.assertIn('"fixture-ownership.json"',source)
    def test_shared_host_evidence_hashes_are_validated_inside_mac_budget(self):
        collector=(ROOT/'Scripts/collect_native_evidence.py').read_text()
        self.assertIn('from mac_photos_host_gate import verify_collected',collector)
        self.assertIn('record=verify_collected(folder',collector)
        self.assertIn('Required host evidence exceeds shared Mac allocation',collector)

class ProductionFrameworkGraphTests(unittest.TestCase):
    def test_only_production_photos_extension_explicitly_links_public_sample_frameworks(self):
        import runpy
        project=ROOT/'CelluloidNative.xcodeproj/project.pbxproj';before=project.read_bytes()
        generated=runpy.run_path(str(ROOT/'Scripts/generate_native_project.py'));objects=generated['objects']
        self.assertEqual(project.read_bytes(),before,'Generated framework graph must be deterministic')
        links=set()
        for name in ['PhotosUI','Photos']:
            ref=generated['uid']('system-framework:'+name);link=generated['uid']('system-link:CelluloidMacPhotosExtension'+name)
            self.assertEqual(objects[ref]['sourceTree'],'SDKROOT')
            self.assertEqual(objects[ref]['path'],'System/Library/Frameworks/'+name+'.framework')
            self.assertEqual(objects[link],{'isa':'PBXBuildFile','fileRef':ref})
            links.add(link)
        for obj in objects.values():
            if obj['isa']!='PBXNativeTarget':continue
            actual={item for phase in obj['buildPhases'] if objects[phase]['isa']=='PBXFrameworksBuildPhase' for item in objects[phase]['files']}
            self.assertEqual(actual&links,links if obj['name']=='CelluloidMacPhotosExtension' else set(),obj['name'])


class SyntheticHostFixtureCase(unittest.TestCase):
    """Keep synthetic source receipts separate from the real invoking CI job."""
    SOURCE = 'a' * 40

    def setUp(self):
        super().setUp()
        source_environment = mock.patch.dict(os.environ, GITHUB_SHA=self.SOURCE)
        source_environment.start()
        self.addCleanup(source_environment.stop)


class RuntimeAcceptanceTests(SyntheticHostFixtureCase):
    """Synthetic verifier fixtures only, never evidence of an Apple runtime pass."""
    SOURCE = 'a' * 40

    def seed(self, root):
        root = Path(root).resolve()  # Match real producer receipts across macOS /var -> /private/var.
        observed = root / 'mac-host-observed'
        observed.mkdir()
        from test_mac_host_lifecycle import fixture as lifecycle_fixture,sample_images
        fixture_sha=hashlib.sha256(sample_images()['lifecycle-source.png']).hexdigest()
        app = str(root / 'Applications/CelluloidHost-test.app')
        extension = app + '/Contents/PlugIns/CelluloidMacPhotosExtension.appex'
        executable = extension + '/Contents/MacOS/CelluloidMacPhotosExtension'
        context = {'host_clock_profile':host_clock_profile(FULL_ROUTE),'validation_route':dict(FULL_ROUTE),'runner_environment':{'GITHUB_REF':'refs/heads/apple-platforms'},'host_entry_contract':gate.HOST_CONTRACT,'source_sha': self.SOURCE, 'base_sha': gate.BASE, 'app_path': app,
                   'extension_path': extension, 'extension_executable': executable,
                   'extension_debug_dylib':executable+'.debug.dylib','extension_debug_dylib_sha256':'9'*64,
                   'app_id': gate.APP_ID, 'extension_id': gate.EXT_ID, 'complete_host_e2e': False,
                   'script_sha256': gate.sha(gate.__file__), 'test_source_sha256': gate.sha(ROOT/'Platforms/UITests/MacPhotosHostUITests.swift'),
                   'app_executable': app+'/Contents/MacOS/CelluloidMac', 'extension_executable_sha256': 'e' * 64,
                   'app_executable_sha256': 'd' * 64, 'seed': {'mode': 'require-empty-library'}}
        summary = {'result': 'Passed', 'totalTestCount': 1, 'passedTests': 1, 'failedTests': 0,
                   'skippedTests': 0, 'expectedFailures': 0, 'startTime': 10, 'finishTime': 20,
                   'testFailures': [], 'devicesAndConfigurations': [
                       {'passedTests': 1, 'failedTests': 0, 'skippedTests': 0, 'expectedFailures': 0,
                        'device': {'platform': 'macOS', 'osVersion': '27.0'}}]}
        source = {'validation_route':dict(FULL_ROUTE),'source_sha': self.SOURCE, 'base_sha': gate.BASE, 'base_tree': gate.BASE_TREE,
                  'unchanged_bound_files': gate.UNCHANGED_BASE_FILES, 'reviewed_diagnostic_test_files': gate.REVIEWED_TEST_FILES, 'reviewed_candidate_files': gate.REVIEWED_CANDIDATE_FILES, 'complete_host_e2e': False, 'tree': 'b' * 40,
                  'workflow_sha256': gate.sha(ROOT/'.github/workflows/apple-platforms.yml')}
        clock={'source_sha':self.SOURCE,'started_monotonic':100.0,'started_unix':10000.0,'execution_budget_seconds':gate.JOB_EXECUTION_SECONDS}
        gate.write(root/'mac-job-clock.json',clock)
        checks=[{'phase':phase,'observed_monotonic':now,'deadline_monotonic':2560.0,'remaining_seconds':2560.0-now,'required_seconds':1020,'admitted':True} for phase,now in [('before-prepare',101.0),('before-host',110.0)]]
        documents = {
            'combined-source-before.json': dict(source,phase='before',file_count=len(json.loads((ROOT/'Scripts/combined-source-contract.json').read_text())['files']),source_fingerprint=json.loads((ROOT/'Scripts/combined-source-contract.json').read_text())['fingerprint']),
            'combined-source-after.json': dict(source,phase='after',file_count=len(json.loads((ROOT/'Scripts/combined-source-contract.json').read_text())['files']),source_fingerprint=json.loads((ROOT/'Scripts/combined-source-contract.json').read_text())['fingerprint']),
            'mac-host-budget.json':{'source_sha':self.SOURCE,'checks':checks,'admitted':True,'clock_sha256':gate.sha(root/'mac-job-clock.json'),'host_process_seconds':720,'host_clock_profile':host_clock_profile(FULL_ROUTE),'evidence_reserve_seconds':300,'complete_host_e2e':False},
            'mac-host-observed/fixture.json': {'source_sha': self.SOURCE, 'sha256': fixture_sha},
            'mac-host-observed/fixture-ownership.json': {'source_sha': self.SOURCE, 'app_executable_sha256': 'd' * 64, 'initial_count': 0, 'selected_count': 1, 'width': 1200, 'height': 800, 'asset_label': 'synthetic sole asset', 'fixture_sha256': fixture_sha, 'mode': 'require-empty-library'},
            'mac-host-context.json': context, 'mac-host-summary.json': summary,
            'mac-host-product-after.json': {'installed_bytes_unchanged': True, 'strict_signatures_unchanged': True,
                'app_executable_sha256': 'd' * 64, 'extension_executable_sha256': 'e' * 64,'extension_debug_dylib_sha256':'9'*64},
            'mac-host-source-before.json': dict(source, phase='before'),
            'mac-host-source-after.json': dict(source, phase='after'),
            'mac-host-observed/prerequisite.json': {'host_entry_contract':gate.HOST_CONTRACT,'source_sha': self.SOURCE, 'prerequisite_passed': True,
                'complete_host_e2e': False, 'production_source_base': gate.BASE},
            'mac-host-observed/outcome.json': {'host_entry_contract':gate.HOST_CONTRACT,'source_sha': self.SOURCE, 'complete_host_e2e': False,
                'last_stage': 'photos-filter-lifecycle-passed', 'save_reopen_cancel_revert': 'PhotosFilterLifecycle.1 complete', 'extension_menu_observation': {'schema':'Celluloid.HostMenuObservation.2','acceptance':False,'menu_title':'Celluloid','menu_identifier':'editWithPlugin:','menu_scope':'Extensions.menuButton/childMenu/directMenuItem','extension_menu_button_count':1,'opened_menu_count':1,'menu_count':1,'menu_enabled':True,'menu_hittable':True,'classification':'selectable'}},
        }
        from test_mac_host_self_identity import receipt
        documents['mac-host-observed/extension-self-identity.json']=receipt(context,{'pid':122},documents['mac-host-observed/fixture-ownership.json'])
        common={'host_entry_contract':gate.HOST_CONTRACT,'source_sha':self.SOURCE,'photos_pid':122,
            'photos_bundle':'/System/Applications/Photos.app','photos_executable':'/System/Applications/Photos.app/Contents/MacOS/Photos',
            'fixture_sha256':fixture_sha,'asset_label':'synthetic sole asset'}
        documents['mac-host-observed/host-selection.json']=dict(common,schema='Celluloid.HostSelection.3',menu_title='Celluloid',menu_identifier='editWithPlugin:',menu_scope='Extensions.menuButton/childMenu/directMenuItem',extension_menu_button_count=1,opened_menu_count=1,menu_count=1,menu_enabled=True,menu_hittable=True,editor_count_before=0)
        for phase in ['before','after']:
            documents['mac-host-observed/host-editor-'+phase+'-process.json']=dict(common,schema='Celluloid.HostEditor.2',phase=phase+'-process',
                editor_label='Celluloid photo editor',editor_count=1,preview_label='Edited photo preview',preview_count=1,placeholder_count=0,preparing_count=0,
                filter_identifier='photos-extension.filter',filter_count=1,filter_enabled=True,read_only_count=0,error_count=0)
        for name, data in documents.items(): gate.write(root / name, data)
        from mac_host_transport import ORDER,expected_transport
        gate.write(observed/'transport.json',expected_transport(context,gate.sha(root/'mac-host-context.json')))
        gate.write(observed/'containing-process.json',{'bundle':app,'executable':context['app_executable'],'pid':121})
        gate.write(observed/'photos-process.json',{'bundle':'/System/Applications/Photos.app','executable':'/System/Applications/Photos.app/Contents/MacOS/Photos','pid':122})
        lifecycle,*_=lifecycle_fixture(context,{'pid':122},documents['mac-host-observed/fixture-ownership.json'],gate.sha(root/'mac-host-context.json'))
        documents['mac-host-observed/lifecycle.json']=lifecycle
        (observed/'lifecycle.json').write_text(json.dumps(lifecycle,sort_keys=True,separators=(',',':'))+'\n')
        for name,data in sample_images().items():(observed/name).write_bytes(data)
        RuntimeAcceptanceTests.write_transport_log(self,root,context)
        return documents

    def write_transport_log(self,root,context=None):
        from mac_host_transport import ORDER,SCHEMA,PREFIX,LABEL,expected_transport
        context=context or gate.read_receipt(root/'mac-host-context.json')
        gate.write(root/'mac-host-observed/transport.json',expected_transport(context,gate.sha(root/'mac-host-context.json')))
        owner,method=gate.EXPECTED_CASE
        command=['xcodebuild','-maximum-test-execution-time-allowance',str(context_clock(context)['test_seconds']),'-only-testing:'+owner.replace('.', '/')+'/'+method,'test-without-building']
        lines=['BOUNDED_COMMAND_BEGIN '+json.dumps({'label':LABEL,'seconds':context_clock(context)['process_seconds'],'command':command}),
            "Test Case '-["+owner+' '+method+"]' started."]
        for index,name in enumerate(ORDER):
            data=(root/'mac-host-observed'/name).read_bytes()
            lines.append(PREFIX+json.dumps({'schema':SCHEMA,'sequence':index,'name':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
                'base64':base64.b64encode(data).decode(),'source_sha':self.SOURCE,'context_sha256':gate.sha(root/'mac-host-context.json'),
                'test_source_sha256':context['test_source_sha256'],'verifier_sha256':context['script_sha256']}))
        lines+=['MAC_HOST_PREREQUISITE_PASSED synthetic verifier fixture','MAC_HOST_FILTER_LIFECYCLE_PASSED synthetic verifier fixture',"Test Case '-["+owner+' '+method+"]' passed (1.0 seconds).",
            '** TEST EXECUTE SUCCEEDED **','BOUNDED_COMMAND_END '+json.dumps({'label':LABEL,'exit_code':0,'elapsed_seconds':1})]
        (root/'mac-host-test.log').write_text('\n'.join(lines)+'\n')
        records=gate.transport_records(root,context,complete=True)
        gate.write(root/'mac-host-transport-replay.json',gate.transport_report(root,context,records))

    def check_mutation_rejected(self, mutation):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); self.seed(root); mutation(root)
            with self.assertRaises((AssertionError, ValueError, KeyError, TypeError)):
                gate.verify_acceptance(root, self.SOURCE)

    def edit(self, path, **updates):
        value = json.loads(path.read_text()); value.update(updates); gate.write(path, value)

    def test_complete_consistent_prerequisite_packet_is_accepted_without_e2e_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); self.seed(root)
            accepted = gate.verify_acceptance(root, self.SOURCE)
            self.assertTrue(accepted['prerequisite_accepted'])
            self.assertTrue(accepted['exactly_one_passed_zero_skipped'])
            self.assertFalse(accepted['complete_host_e2e'])
            self.assertEqual(len(accepted['receipts']), 28)

    def test_rehashed_nonfinite_proof_and_timeout_contradictions_reject_at_transport(self):
        from mac_host_transport import PREFIX
        for literal in ['NaN','Infinity','-Infinity','1e999']:
            with self.subTest(literal=literal),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);self.seed(root);path=root/'mac-host-test.log';lines=path.read_text().splitlines()
                for index,line in enumerate(lines):
                    if not line.startswith(PREFIX):continue
                    row=json.loads(line[len(PREFIX):])
                    if row['name']!='prerequisite.json':continue
                    data=base64.b64decode(row['base64']).rstrip();data=data[:-1]+b',"malformed_nonfinite":'+literal.encode()+b'}'
                    row.update(base64=base64.b64encode(data).decode(),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
                    lines[index]=PREFIX+json.dumps(row);(root/'mac-host-observed/prerequisite.json').write_bytes(data)
                path.write_text('\n'.join(lines)+'\n')
                with self.assertRaisesRegex(ValueError,'Nonfinite JSON'):gate.verify_acceptance(root,self.SOURCE)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.seed(root);path=root/'mac-host-test.log'
            path.write_text(path.read_text().replace('** TEST EXECUTE SUCCEEDED **','BOUNDED_COMMAND_TIMEOUT actual-mac-photos-host-prerequisite\n** TEST EXECUTE SUCCEEDED **'))
            with self.assertRaisesRegex(ValueError,'process timeout'):gate.verify_acceptance(root,self.SOURCE)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'receipt.json';path.write_text('{"nested":{"bad":NaN}}')
            with self.assertRaisesRegex(ValueError,'Nonfinite JSON'):gate.read_receipt(path)

    def test_nonfinite_attachment_export_never_publishes_transport_completion(self):
        for literal in ['NaN','Infinity','-Infinity','1e999']:
            with self.subTest(literal=literal),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);self.seed(root);context=gate.read_receipt(root/'mac-host-context.json')
                (root/'mac-host-transport-replay.json').unlink()
                for path in (root/'mac-host-observed').iterdir():path.unlink()
                def export(command,**kwargs):
                    destination=Path(command[command.index('--output-path')+1])
                    (destination/'manifest.json').write_text('[{"attachments":[],"bad":'+literal+'}]')
                    return subprocess.CompletedProcess(command,0,b'',b'')
                with mock.patch.object(gate,'require_runner'),mock.patch.object(gate,'temp',return_value=root),mock.patch.object(gate,'context',return_value=context),mock.patch.object(gate.subprocess,'run',side_effect=export):
                    with self.assertRaisesRegex(ValueError,'Nonfinite JSON'):gate.extract_transport()
                self.assertFalse((root/'mac-host-transport-replay.json').exists())
                report=gate.read_receipt(root/'mac-host-observed/attachment-export-failure.json')
                self.assertFalse(report['acceptance']);self.assertIn('Nonfinite JSON',report['error'])

    def test_rejected_attachment_metadata_is_bounded_and_never_transport_completion(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.seed(root);context=gate.read_receipt(root/'mac-host-context.json')
            (root/'mac-host-transport-replay.json').unlink()
            for path in (root/'mac-host-observed').iterdir():path.unlink()
            name='celluloid-host-diagnostic-unexpected_0_12345678-1234-1234-1234-123456789ABC.txt'
            manifest=[{'testIdentifier':'MacPhotosHostUITests/testInstalledExtensionIsInvokedByActualPhotos()',
                       'attachments':[{'suggestedHumanReadableName':name,'exportedFileName':'owned.txt'}]}]
            raw=json.dumps(manifest).encode()
            def export(command,**kwargs):
                destination=Path(command[command.index('--output-path')+1])
                (destination/'manifest.json').write_bytes(raw);(destination/'owned.txt').write_text('diagnostic')
                return subprocess.CompletedProcess(command,0,b'',b'')
            with mock.patch.object(gate,'require_runner'),mock.patch.object(gate,'temp',return_value=root),mock.patch.object(gate,'context',return_value=context),mock.patch.object(gate.subprocess,'run',side_effect=export):
                with self.assertRaisesRegex(ValueError,'Unexpected/duplicate named host attachment'):gate.extract_transport()
            self.assertFalse((root/'mac-host-transport-replay.json').exists())
            path=root/'mac-host-observed/attachment-export-failure.json';report=gate.read_receipt(path)
            self.assertFalse(report['acceptance']);self.assertEqual(report['manifest_sha256'],hashlib.sha256(raw).hexdigest())
            self.assertEqual(report['retained_first_items'][0]['suggestedHumanReadableName'],name)
            self.assertLessEqual(path.stat().st_size,16_000)
            self.assertFalse((root/'mac-host-observed/unexpected.txt').exists())
            self.assertEqual(gate.read_receipt(root/'mac-host-observed/outcome.json')['extension_menu_observation']['classification'],'selectable')

    def test_safe_owned_diagnostics_survive_later_inventory_rejection_without_completion(self):
        for malformed in ['ordinary-path','other-record','lifecycle-png']:
            with self.subTest(malformed=malformed),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);self.seed(root);context=gate.read_receipt(root/'mac-host-context.json')
                (root/'mac-host-transport-replay.json').unlink()
                for path in (root/'mac-host-observed').iterdir():path.unlink()
                good={'suggestedHumanReadableName':'celluloid-host-diagnostic-last-observed_0_12345678-1234-1234-1234-123456789ABC.txt','exportedFileName':'owned.txt'}
                manifest=[{'testIdentifier':'MacPhotosHostUITests/testInstalledExtensionIsInvokedByActualPhotos()','attachments':[good]}]
                if malformed=='ordinary-path':manifest[0]['attachments'].append({'suggestedHumanReadableName':'UI Snapshot','exportedFileName':'../outside'})
                if malformed=='other-record':manifest.append({'attachments':None})
                if malformed=='lifecycle-png':manifest[0]['attachments'].append({'suggestedHumanReadableName':'celluloid-host-lifecycle-lifecycle-saved_0_12345678-1234-1234-1234-123456789ABC.png','exportedFileName':'broken.png'})
                def export(command,**kwargs):
                    destination=Path(command[command.index('--output-path')+1])
                    (destination/'manifest.json').write_text(json.dumps(manifest));(destination/'owned.txt').write_bytes(b'bounded actual owned AX')
                    (destination/'broken.png').write_bytes(b'not PNG')
                    return subprocess.CompletedProcess(command,0,b'',b'')
                with mock.patch.object(gate,'require_runner'),mock.patch.object(gate,'temp',return_value=root),mock.patch.object(gate,'context',return_value=context),mock.patch.object(gate.subprocess,'run',side_effect=export):
                    with self.assertRaises(ValueError):gate.extract_transport()
                self.assertEqual((root/'mac-host-observed/last-observed.txt').read_bytes(),b'bounded actual owned AX')
                self.assertFalse((root/'mac-host-transport-replay.json').exists())
                self.assertFalse((root/'mac-host-observed/lifecycle-saved.png').exists())
                rejection=gate.read_receipt(root/'mac-host-observed/attachment-export-failure.json')
                self.assertFalse(rejection['acceptance']);self.assertEqual(rejection['retained_diagnostic_sha256'],{'last-observed.txt':hashlib.sha256(b'bounded actual owned AX').hexdigest()})
                with self.assertRaises((AssertionError,ValueError)):gate.verify_acceptance(root,self.SOURCE)

    def test_seventy_item_export_publishes_completion_only_after_strict_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.seed(root);context=gate.read_receipt(root/'mac-host-context.json')
            (root/'mac-host-transport-replay.json').unlink()
            for path in (root/'mac-host-observed').iterdir():path.unlink()
            def export(command,**kwargs):
                destination=Path(command[command.index('--output-path')+1]);items=[]
                for index in range(70):
                    name='item-'+str(index);(destination/name).write_bytes(b'owned AX' if index==0 else b'ordinary snapshot bytes')
                    human='celluloid-host-diagnostic-last-observed_0_12345678-1234-1234-1234-123456789ABC.txt' if index==0 else 'UI Snapshot'
                    items.append({'suggestedHumanReadableName':human,'exportedFileName':name})
                (destination/'manifest.json').write_text(json.dumps([{'testIdentifier':'MacPhotosHostUITests/testInstalledExtensionIsInvokedByActualPhotos()','attachments':items}]))
                return subprocess.CompletedProcess(command,0,b'',b'')
            with mock.patch.object(gate,'require_runner'),mock.patch.object(gate,'temp',return_value=root),mock.patch.object(gate,'context',return_value=context),mock.patch.object(gate.subprocess,'run',side_effect=export):gate.extract_transport()
            self.assertTrue((root/'mac-host-transport-replay.json').is_file())
            self.assertEqual((root/'mac-host-observed/last-observed.txt').read_bytes(),b'owned AX')
            self.assertFalse((root/'mac-host-observed/attachment-export-failure.json').exists())
            self.assertFalse(any(p.name.startswith('item-') for p in (root/'mac-host-observed').iterdir()))

    def test_changed_second_diagnostic_read_never_publishes_completion(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.seed(root);context=gate.read_receipt(root/'mac-host-context.json')
            (root/'mac-host-transport-replay.json').unlink()
            for path in (root/'mac-host-observed').iterdir():path.unlink()
            def export(command,**kwargs):
                destination=Path(command[command.index('--output-path')+1]);(destination/'owned').write_bytes(b'original AX')
                (destination/'manifest.json').write_text(json.dumps([{'testIdentifier':'MacPhotosHostUITests/testInstalledExtensionIsInvokedByActualPhotos()','attachments':[{'suggestedHumanReadableName':'celluloid-host-diagnostic-last-observed_0_12345678-1234-1234-1234-123456789ABC.txt','exportedFileName':'owned'}]}]))
                return subprocess.CompletedProcess(command,0,b'',b'')
            with mock.patch.object(gate,'require_runner'),mock.patch.object(gate,'temp',return_value=root),mock.patch.object(gate,'context',return_value=context),mock.patch.object(gate.subprocess,'run',side_effect=export),mock.patch('mac_host_transport.attachment_candidates',return_value={'last-observed.txt':b'changed AX!'}):
                with self.assertRaisesRegex(AssertionError,'Retained diagnostic changed'):gate.extract_transport()
            self.assertEqual((root/'mac-host-observed/last-observed.txt').read_bytes(),b'original AX')
            self.assertFalse((root/'mac-host-transport-replay.json').exists())

    def test_attachment_error_metadata_caps_unicode_and_preserves_original_write_failure(self):
        for fail_write in [False,True]:
            with self.subTest(fail_write=fail_write),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);self.seed(root);context=gate.read_receipt(root/'mac-host-context.json')
                (root/'mac-host-transport-replay.json').unlink()
                for path in (root/'mac-host-observed').iterdir():path.unlink()
                manifest=[{'testIdentifier':'界'*160,'attachments':[
                    {'suggestedHumanReadableName':'celluloid-host-diagnostic-'+('界'*160),
                     'exportedFileName':'owned.txt'} for _ in range(40)]}]
                def export(command,**kwargs):
                    destination=Path(command[command.index('--output-path')+1])
                    (destination/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False))
                    return subprocess.CompletedProcess(command,0,b'',b'')
                original_write=Path.write_bytes
                def guarded_write(path,data):
                    if fail_write and path.name=='attachment-export-failure.json':raise OSError('optional retention failed')
                    return original_write(path,data)
                with mock.patch.object(gate,'require_runner'),mock.patch.object(gate,'temp',return_value=root),mock.patch.object(gate,'context',return_value=context),mock.patch.object(gate.subprocess,'run',side_effect=export),mock.patch.object(Path,'write_bytes',guarded_write):
                    with self.assertRaisesRegex(ValueError,'Unowned attachment path'):gate.extract_transport()
                self.assertFalse((root/'mac-host-transport-replay.json').exists())
                path=root/'mac-host-observed/attachment-export-failure.json'
                if fail_write:self.assertFalse(path.exists())
                else:
                    report=gate.read_receipt(path);self.assertFalse(report['acceptance'])
                    self.assertEqual(report['attachment_count'],40);self.assertEqual(report['omitted_items'],40)
                    self.assertEqual(report['retained_first_items'],[]);self.assertLessEqual(path.stat().st_size,16_000)

    def test_explicitly_reviewed_candidate_hashes_cannot_be_removed_or_substituted(self):
        for name in ['mac-host-source-before.json','mac-host-source-after.json']:
            for mapping in [{},{path:'f'*64 for path in gate.REVIEWED_CANDIDATE_FILES}]:
                with self.subTest(name=name,mapping=mapping):
                    self.check_mutation_rejected(lambda root:self.edit(root/name,reviewed_candidate_files=mapping))

    def test_combined_candidate_receipts_cannot_be_stale_or_unbound(self):
        for name in ['combined-source-before.json','combined-source-after.json']:
            for fields in [{'source_sha':'f'*40},{'tree':'f'*40},{'workflow_sha256':'f'*64},{'phase':'wrong'},{'file_count':True},{'file_count':0},{'source_fingerprint':'f'*64}]:
                with self.subTest(name=name,fields=fields):
                    self.check_mutation_rejected(lambda root:self.edit(root/name,**fields))

    def test_synthetic_packet_uses_canonical_paths_through_temporary_directory_alias(self):
        with tempfile.TemporaryDirectory() as folder:
            real=Path(folder)/'real';real.mkdir();alias=Path(folder)/'alias';alias.symlink_to(real,target_is_directory=True)
            self.seed(alias)
            accepted=gate.verify_acceptance(alias,self.SOURCE)
            self.assertTrue(accepted['prerequisite_accepted'])
            containing=gate.read_receipt(alias/'mac-host-observed/containing-process.json')
            expected=str(real.resolve()/'Applications/CelluloidHost-test.app')
            self.assertEqual(containing['bundle'],expected)
            gate.write(alias/'mac-host-acceptance.json',accepted)
            with mock.patch.dict(os.environ,RUNNER_TEMP=str(alias),GITHUB_SHA=self.SOURCE):gate.collect()
            self.assertTrue(gate.verify_collected(alias/'mac-host-evidence',self.SOURCE)['prerequisite_accepted'])
            # Only fixture setup canonicalizes. A claimed noncanonical product
            # path still fails, independently of registry inventory.
            containing['bundle']=str(alias/'Applications/CelluloidHost-test.app')
            gate.write(alias/'mac-host-observed/containing-process.json',containing)
            with self.assertRaises(AssertionError):gate.verify_acceptance(alias,self.SOURCE)

    def test_each_missing_mandatory_record_rejects(self):
        paths = ['combined-source-before.json','combined-source-after.json','mac-job-clock.json', 'mac-host-budget.json', 'mac-host-context.json', 'mac-host-summary.json', 'mac-host-test.log',
                 'mac-host-product-after.json', 'mac-host-source-before.json', 'mac-host-source-after.json',
                 'mac-host-observed/prerequisite.json', 'mac-host-observed/outcome.json',
                 'mac-host-observed/host-selection.json', 'mac-host-observed/host-editor-before-process.json', 'mac-host-observed/host-editor-after-process.json',
                 'mac-host-observed/extension-self-identity.json', 'mac-host-observed/fixture-ownership.json', 'mac-host-observed/fixture.json']
        for name in paths:
            with self.subTest(missing=name):
                self.check_mutation_rejected(lambda root: (root / name).unlink())

    def test_zero_skipped_duplicate_failed_unfinalized_or_contradictory_summary_rejects(self):
        for update in [{'totalTestCount': 0, 'passedTests': 0}, {'skippedTests': 1, 'passedTests': 0},
                       {'totalTestCount': 2, 'passedTests': 2}, {'failedTests': 1}, {'expectedFailures': 1},
                       {'result': 'Skipped'}, {'finishTime': 10}, {'testFailures': ['failure']},
                       {'passedTests': True}, {'devicesAndConfigurations': []}]:
            with self.subTest(update=update):
                self.check_mutation_rejected(lambda root: self.edit(root / 'mac-host-summary.json', **update))
        def contradict(root):
            path = root / 'mac-host-summary.json'; data = json.loads(path.read_text())
            data['devicesAndConfigurations'][0]['skippedTests'] = 1; gate.write(path, data)
        self.check_mutation_rejected(contradict)

    def test_missing_wrong_duplicate_skipped_or_contradictory_case_output_rejects(self):
        for transform in [lambda log: '', lambda log: log.replace('MacPhotosHostUITests', 'WrongTests'),
                          lambda log: log + log, lambda log: log.replace("' passed", "' skipped"),
                          lambda log: log.replace("' passed", "' failed"),
                          lambda log: log.replace("' started.", "' notstarted."),
                          lambda log: log.replace('MAC_HOST_PREREQUISITE_PASSED', 'NO_MARKER'),
                          lambda log: log + 'MAC_HOST_PREREQUISITE_PASSED duplicate\n',
                          lambda log: log + 'MAC_HOST_BLOCKED late failure\n',
                          lambda log: log + 'MAC_HOST_FAIL_CLOSED_ABORT\n']:
            def mutate(root):
                p = root / 'mac-host-test.log'; p.write_text(transform(p.read_text()))
            self.check_mutation_rejected(mutate)

    def test_wrong_candidate_or_duplicate_json_key_in_any_identity_receipt_rejects(self):
        paths = ['mac-host-context.json', 'mac-host-source-before.json', 'mac-host-source-after.json',
                 'mac-host-observed/prerequisite.json', 'mac-host-observed/outcome.json',
                 'mac-host-observed/host-selection.json', 'mac-host-observed/host-editor-before-process.json', 'mac-host-observed/host-editor-after-process.json', 'mac-host-observed/extension-self-identity.json', 'mac-host-observed/fixture-ownership.json', 'mac-host-observed/fixture.json']
        for name in paths:
            with self.subTest(wrong_source=name):
                self.check_mutation_rejected(lambda root: self.edit(root / name, source_sha='f' * 40))
            def duplicate(root):
                path = root / name; raw = path.read_text().strip()
                path.write_text(raw[:-1] + ', "source_sha": "' + self.SOURCE + '"}')
            with self.subTest(duplicate_key=name): self.check_mutation_rejected(duplicate)

    def test_false_skipped_stage_or_complete_e2e_receipt_rejects(self):
        for name, updates in [('prerequisite.json', {'prerequisite_passed': False}),
                              ('prerequisite.json', {'prerequisite_passed': 1}),
                              ('prerequisite.json', {'complete_host_e2e': True}),
                              ('prerequisite.json', {'production_source_base': 'wrong'}),
                              ('outcome.json', {'last_stage': 'observe-extensions-menu'}),
                              ('outcome.json', {'complete_host_e2e': True}),
                              ('outcome.json', {'save_reopen_cancel_revert': 'passed'})]:
            with self.subTest(name=name, updates=updates):
                self.check_mutation_rejected(lambda root: self.edit(root / 'mac-host-observed' / name, **updates))

    def test_rehashed_wrong_title_identifier_scope_and_duplicate_menu_reject(self):
        for fields in [{'menu_title':'Other'},{'menu_identifier':'other:'},{'menu_scope':'Photos.menuBar/hiddenMenu'},
                       {'extension_menu_button_count':2},{'opened_menu_count':0},{'opened_menu_count':True},
                       {'schema':'Celluloid.HostSelection.2'}]:
            with self.subTest(fields=fields),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);self.seed(root);self.edit(root/'mac-host-observed/host-selection.json',**fields);self.write_transport_log(root)
                with self.assertRaises(AssertionError):gate.verify_acceptance(root,self.SOURCE)

    def test_menu_outcome_cannot_contradict_passed_host_selection_after_rehash(self):
        for change in [{'menu_count':0,'menu_enabled':None,'menu_hittable':None,'classification':'absent'},
                       {'menu_count':2,'classification':'ambiguous'},{'menu_enabled':False,'classification':'disabled'},
                       {'menu_hittable':False,'classification':'not-hittable'},{'menu_count':True},{'acceptance':True}]:
            with self.subTest(change=change),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);self.seed(root);path=root/'mac-host-observed/outcome.json'
                row=gate.read_receipt(path);row['extension_menu_observation'].update(change);gate.write(path,row)
                self.write_transport_log(root)
                with self.assertRaises(AssertionError):gate.verify_acceptance(root,self.SOURCE)

    def test_structured_blocked_operation_vetoes_rehashed_success_without_text_marker(self):
        for blocked in [{},{'reason':'denied'},None,False]:
            with self.subTest(blocked=blocked),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);self.seed(root)
                self.edit(root/'mac-host-observed/outcome.json',first_blocked_operation=blocked)
                self.write_transport_log(root)
                self.assertNotIn('MAC_HOST_BLOCKED', (root/'mac-host-test.log').read_text())
                with self.assertRaisesRegex(AssertionError,'blocked operation'):gate.verify_acceptance(root,self.SOURCE)

    def test_wrong_ambiguous_unready_or_replaced_host_ui_rejects_after_rehashing(self):
        variants={
            'host-selection.json':[{'menu_count':0},{'menu_count':2},{'menu_count':True},{'menu_enabled':False},{'menu_hittable':False},{'editor_count_before':1},{'menu_title':'Other'}],
            'host-editor-before-process.json':[{'editor_count':0},{'editor_count':2},{'preview_count':0},{'placeholder_count':1},{'preparing_count':1},{'filter_enabled':False},{'read_only_count':1},{'error_count':1}],
            'host-editor-after-process.json':[{'photos_pid':124},{'phase':'before-process'},{'preview_count':2},{'filter_count':0},{'filter_enabled':1},{'source_sha':'f'*40},{'fixture_sha256':'e'*64},{'asset_label':'other asset'}]}
        for name,mutations in variants.items():
            for update in mutations:
                with self.subTest(name=name,update=update),tempfile.TemporaryDirectory() as folder:
                    root=Path(folder);self.seed(root);self.edit(root/'mac-host-observed'/name,**update)
                    self.write_transport_log(root)
                    with self.assertRaises(AssertionError):gate.verify_acceptance(root,self.SOURCE)

    def test_v3_claim_requires_real_ui_and_self_identity_without_registry_or_os_uniqueness(self):
        from mac_host_transport import ORDER
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.seed(root);record=gate.verify_acceptance(root,self.SOURCE)
            self.assertEqual(record['host_entry_contract'],'Celluloid.PhotosHostEntry.3')
            self.assertFalse(record['complete_host_e2e'])
            self.assertFalse(record['os_wide_process_uniqueness'])
            self.assertEqual(record['identity_kind'],'in-process-self-observation-via-photos-ui')
            self.assertFalse(any('registration' in path for path in gate.PROOF_LIMITS))
            self.assertFalse(any('registration' in name for name in ORDER))
            # A registry-only record cannot stand in for the removed UI receipt.
            (root/'mac-host-observed/host-selection.json').unlink()
            gate.write(root/'mac-host-observed/registration-selected.json',{'registered_paths':['/owned.appex'],'source_sha':self.SOURCE})
            with self.assertRaises(AssertionError):gate.verify_acceptance(root,self.SOURCE)

    def test_ui_receipts_wrong_type_unknown_field_old_version_or_host_identity_reject_after_rehash(self):
        for name in ['host-selection.json','host-editor-before-process.json','host-editor-after-process.json']:
            for change in [{'host_entry_contract':'Celluloid.PhotosHostEntry.1'},{'schema':'legacy'},{'photos_pid':True},
                           {'photos_bundle':'/tmp/Photos.app'},{'photos_executable':'/tmp/Photos'},{'extra':'unbound'}]:
                with self.subTest(name=name,change=change),tempfile.TemporaryDirectory() as folder:
                    root=Path(folder);self.seed(root);self.edit(root/'mac-host-observed'/name,**change);self.write_transport_log(root)
                    with self.assertRaises(AssertionError):gate.verify_acceptance(root,self.SOURCE)

    def test_passed_ready_ui_cannot_hide_wrong_self_identity_after_rehash(self):
        from test_mac_host_self_identity import change_payload
        for fields in [{'pid':0},{'pid':True},{'pid':122},{'executable_path':'/other/extension'},
                       {'executable_sha256':'0'*64},{'debug_dylib_sha256':'0'*64},
                       {'bundle_identifier':'Other.Extension'},{'content_editing_started':False}]:
            with self.subTest(fields=fields),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);self.seed(root);path=root/'mac-host-observed/extension-self-identity.json'
                row=gate.read_receipt(path);change_payload(row,**fields);gate.write(path,row);self.write_transport_log(root)
                with self.assertRaises(ValueError):gate.verify_acceptance(root,self.SOURCE)

    def test_v1_v2_context_and_collected_manifest_are_not_accepted_as_v3(self):
        for version in [1,2]:
            with tempfile.TemporaryDirectory() as folder:
                root=Path(folder);self.seed(root);self.edit(root/'mac-host-context.json',host_entry_contract='Celluloid.PhotosHostEntry.'+str(version))
                with self.assertRaises((AssertionError,ValueError)):gate.verify_acceptance(root,self.SOURCE)
            with tempfile.TemporaryDirectory() as folder,mock.patch.dict(os.environ,RUNNER_TEMP=folder,GITHUB_SHA=self.SOURCE):
                root=Path(folder);self.seed(root);gate.write(root/'mac-host-acceptance.json',gate.verify_acceptance(root,self.SOURCE));gate.collect()
                self.edit(root/'mac-host-evidence/manifest.json',host_entry_contract='Celluloid.PhotosHostEntry.'+str(version))
                with self.assertRaises(AssertionError):gate.verify_collected(root/'mac-host-evidence',self.SOURCE)

    def test_missing_duplicate_stale_or_malformed_raw_observations_reject_after_rehash(self):
        from test_mac_host_self_identity import envelope
        for mutation in ['missing','duplicate','stale','malformed','duplicate-key','nonfinite','legacy-enumeration']:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);self.seed(root);path=root/'mac-host-observed/extension-self-identity.json';row=gate.read_receipt(path)
                if mutation=='missing':row['observations']=[]
                elif mutation=='duplicate':row['identity_element_counts']=[1,2]
                elif mutation=='stale':
                    second=json.loads(row['observations'][1]['raw']);second['generation']='87654321-1234-4321-8123-123456789ABC'
                    row['observations'][1]=envelope(json.dumps(second))
                elif mutation=='legacy-enumeration':row={'source_sha':self.SOURCE,'extension_processes':[]}
                else:
                    raw=row['observations'][0]['raw']
                    raw=raw[:-1] if mutation=='malformed' else raw[:-1]+',"pid":123}' if mutation=='duplicate-key' else raw.replace('"pid":123','"pid":NaN')
                    row['observations']=[envelope(raw),envelope(raw)]
                gate.write(path,row);self.write_transport_log(root)
                with self.assertRaises((AssertionError,ValueError,KeyError)):gate.verify_acceptance(root,self.SOURCE)

    def test_retired_enumeration_always_blocks_without_launching_any_process(self):
        with mock.patch.object(gate.subprocess,'run') as run:
            with self.assertRaisesRegex(RuntimeError,'Cross-process enumeration retired'):gate.process_provenance()
            run.assert_not_called()

    def test_rehashed_lifecycle_failures_and_actual_png_substitution_cannot_grant_host_acceptance(self):
        from test_mac_host_self_identity import envelope
        for change in ['incomplete','missing-final','stale-generation','reverted-is-saved','missing-marker']:
            with self.subTest(change=change),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);self.seed(root);observed=root/'mac-host-observed';path=observed/'lifecycle.json'
                row=gate.read_receipt(path)
                if change=='incomplete':row['complete']=False
                elif change=='missing-final':row['phases'].pop()
                elif change=='stale-generation':
                    baseline=gate.read_receipt(observed/'extension-self-identity.json')['observations']
                    row['phases'][3]['details']['observations']=baseline
                elif change=='reverted-is-saved':
                    saved=(observed/'lifecycle-saved.png').read_bytes();(observed/'lifecycle-reverted.png').write_bytes(saved)
                    row['images']['lifecycle-reverted.png']=dict(row['images']['lifecycle-saved.png'])
                    row['raw_exports']['reverted'].update(bytes=len(saved),sha256=hashlib.sha256(saved).hexdigest())
                path.write_text(json.dumps(row,separators=(',',':'))+'\n');self.write_transport_log(root)
                if change=='missing-marker':
                    log=root/'mac-host-test.log';log.write_text(log.read_text().replace('MAC_HOST_FILTER_LIFECYCLE_PASSED','REMOVED_LIFECYCLE_MARKER'))
                    context=gate.read_receipt(root/'mac-host-context.json');records=gate.transport_records(root,context,complete=True)
                    gate.write(root/'mac-host-transport-replay.json',gate.transport_report(root,context,records))
                with self.assertRaises((AssertionError,ValueError)):gate.verify_acceptance(root,self.SOURCE)

    def test_changed_product_source_or_symlink_receipt_rejects(self):
        for name, updates in [('mac-host-product-after.json', {'installed_bytes_unchanged': False}),
                              ('mac-host-product-after.json', {'strict_signatures_unchanged': False}),
                              ('mac-host-product-after.json', {'extension_executable_sha256': '0' * 64}),
                              ('mac-host-product-after.json', {'extension_debug_dylib_sha256': '0' * 64}),
                              ('mac-host-source-after.json', {'tree': '0' * 40}),
                              ('mac-host-source-after.json', {'workflow_sha256': '0' * 64}),
                              ('mac-host-source-before.json', {'unchanged_bound_files': 531}),
                              ('mac-host-source-before.json', {'reviewed_diagnostic_test_files': {}}),
                              ('mac-host-source-after.json', {'reviewed_diagnostic_test_files': {'unreviewed.swift':'0'*64}})]:
            self.check_mutation_rejected(lambda root: self.edit(root / name, **updates))
        def symlink(root):
            path = root / 'mac-host-observed/prerequisite.json'; target = root / 'copy.json'
            path.rename(target); path.symlink_to(target)
        self.check_mutation_rejected(symlink)

    def test_acceptance_is_mandatory_even_after_failure_and_precedes_evidence(self):
        workflow = (ROOT / '.github/workflows/apple-platforms.yml').read_text()
        step = workflow.split('      - name: Require exact executed case and same-candidate host receipts\n', 1)[1]
        step = step.split('      - name:', 1)[0]
        self.assertIn("        if: always() && steps.sandbox_child.outcome == 'success'\n", step)
        self.assertIn('          python3 Scripts/mac_photos_host_gate.py accept\n', step)
        self.assertNotIn('||', step)
        self.assertNotIn('continue-on-error', workflow)
        self.assertLess(workflow.index('mac_photos_host_gate.py accept'), workflow.index('mac_photos_host_gate.py collect'))


class CollectedProofTests(SyntheticHostFixtureCase):
    """Both collectors replay complete proofs; synthetic packets are not CI proof."""
    SOURCE='a'*40
    seed=RuntimeAcceptanceTests.seed
    def packet(self,root,accepted=True):
        if accepted:
            self.seed(root);status=gate.verify_acceptance(root,self.SOURCE)
        else:
            (root/'mac-host-observed').mkdir()
            gate.write(root/'mac-host-source-before.json',{'source_sha':self.SOURCE,'observed':'source-bound diagnostic'})
            gate.write(root/'mac-host-observed/outcome.json',{'source_sha':self.SOURCE,'last_stage':'discovery failed'})
            status={'validation_route':dict(FULL_ROUTE),'host_entry_contract':gate.HOST_CONTRACT,'source_sha':self.SOURCE,'prerequisite_accepted':False,'complete_host_e2e':False,'error':'AssertionError: extension not registered'}
        gate.write(root/'mac-host-acceptance.json',status)
    def collect(self,root):
        with mock.patch.dict(os.environ,RUNNER_TEMP=str(root),GITHUB_SHA=self.SOURCE):gate.collect()
        return root/'mac-host-evidence'
    def outer(self,root):
        # This is a synthetic canonical collector packet, independent of the
        # real route/source identity under which the portable suite executes.
        env=dict(os.environ,RUNNER_TEMP=str(root),GITHUB_SHA=self.SOURCE,GITHUB_WORKFLOW_SHA=self.SOURCE,
            GITHUB_REPOSITORY='100mango/Celluloid',GITHUB_EVENT_NAME='push',
            GITHUB_REF='refs/heads/apple-platforms',CELLULOID_VALIDATION_SCOPE='full',
            GITHUB_WORKFLOW_REF='100mango/Celluloid/.github/workflows/apple-platforms.yml@refs/heads/apple-platforms',
            CELLULOID_EVIDENCE_PLATFORM='mac')
        return subprocess.run([sys.executable,str(ROOT/'Scripts/collect_native_evidence.py')],env=env,text=True,capture_output=True,timeout=15)
    def mutate_manifest(self,folder,mutate):
        manifest=json.loads((folder/'manifest.json').read_text());mutate(manifest);gate.write(folder/'manifest.json',manifest)
    def update_file(self,folder,name,mutate):
        p=folder/name;record=json.loads(p.read_text());mutate(record);gate.write(p,record)
        def update(manifest):
            row=next(r for r in manifest['files'] if r['path']==name);row['bytes']=p.stat().st_size;row['sha256']=gate.sha(p)
        self.mutate_manifest(folder,update)
    def assert_outer_rejects(self,root):
        result=self.outer(root);self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
    def test_optional_saturation_cannot_displace_any_accepted_proof_in_either_collector(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.packet(root)
            for i in range(12):
                (root/'mac-host-observed'/f'optional-{i}.jpg').write_bytes(b'x'*600_000)
                (root/'mac-host-observed'/f'optional-{i}.txt').write_bytes(b'y'*150_000)
            folder=self.collect(root);record=gate.verify_collected(folder,self.SOURCE)
            self.assertEqual(record['missing_required_proof'],[]);self.assertTrue(record['prerequisite_accepted']);self.assertTrue(record['omitted'])
            self.assertEqual({r['source_relative'] for r in record['files'] if r['kind']=='required-proof'},set(gate.PROOF_LIMITS))
            self.assertLessEqual(sum(p.stat().st_size for p in folder.iterdir()),gate.CAP)
            result=self.outer(root);self.assertEqual(result.returncode,0,result.stderr)
            outer=json.loads((root/'celluloid-bounded-evidence/manifest.json').read_text())
            outer_names={r['name'] for r in outer['files']}
            for row in record['files']:
                name=row['path'];self.assertIn(name if name.startswith('mac-host-') else 'mac-host-'+name,outer_names)
            self.assertLessEqual(sum(p.stat().st_size for p in (root/'celluloid-bounded-evidence').iterdir()),2_000_000)
    def test_last_observed_AX_precedes_optional_images_without_displacing_proof(self):
        for accepted in [True,False]:
            with self.subTest(accepted=accepted),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.packet(root)
                if not accepted:
                    status=gate.read_receipt(root/'mac-host-acceptance.json')
                    status.update(prerequisite_accepted=False,error='Synthetic original UI-control failure remains')
                    gate.write(root/'mac-host-acceptance.json',status)
                observed=root/'mac-host-observed'
                (observed/'extensions.jpg').write_bytes(b'\xff\xd8\xff'+b'x'*699997)
                (observed/'last-observed.jpg').write_bytes(b'\xff\xd8\xff'+b'x'*119997)
                (observed/'last-observed.txt').write_bytes(b'A'*120000)
                folder=self.collect(root);record=gate.verify_collected(folder,self.SOURCE)
                self.assertEqual((folder/'last-observed.txt').read_bytes(),b'A'*120000)
                self.assertFalse((folder/'last-observed.jpg').exists())
                omitted=[row for row in record['omitted'] if row['name']=='last-observed.jpg']
                self.assertEqual(len(omitted),1);self.assertIn('cap',omitted[0]['reason']);self.assertEqual(omitted[0]['bytes'],120000)
                self.assertEqual(record['prerequisite_accepted'],accepted);self.assertFalse(record['complete_host_e2e'])
                rows=record['files'];ax=next(i for i,row in enumerate(rows) if row['path']=='last-observed.txt')
                self.assertEqual(rows[ax]['kind'],'optional-diagnostic')
                self.assertTrue(all(i<ax for i,row in enumerate(rows) if row['kind']=='required-proof'))
                self.assertTrue(all(i>ax for i,row in enumerate(rows) if row['path'].endswith('.jpg')))
                self.assertLessEqual(sum(path.stat().st_size for path in folder.iterdir()),gate.CAP)
                self.assertNotIn('mac-host-observed/last-observed.jpg',gate.PROOF_LIMITS)

    def test_missing_accepted_proof_rejected_by_both_collectors(self):
        for missing in gate.PROOF_LIMITS:
            with self.subTest(missing=missing),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.packet(root);(root/missing).unlink()
                with self.assertRaises((AssertionError,KeyError)):self.collect(root)
            with self.subTest(collected_missing=missing),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.packet(root);folder=self.collect(root)
                def remove(m):
                    row=next(r for r in m['files'] if r['source_relative']==missing);m['files'].remove(row);(folder/row['path']).unlink();m['missing_required_proof']=[missing]
                self.mutate_manifest(folder,remove)
                with self.assertRaises(AssertionError):gate.verify_collected(folder,self.SOURCE)
                self.assert_outer_rejects(root)
    def test_oversized_required_proof_rejected_by_both_collectors(self):
        for relative,limit in gate.PROOF_LIMITS.items():
            with self.subTest(relative=relative),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.packet(root);p=root/relative;p.write_bytes(p.read_bytes()+b' '*(limit+1-p.stat().st_size))
                with self.assertRaises((AssertionError,ValueError)):self.collect(root)
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.packet(root);folder=self.collect(root);p=folder/Path(relative).name;p.write_bytes(p.read_bytes()+b' '*(limit+1-p.stat().st_size))
                def update(m):
                    row=next(r for r in m['files'] if r['source_relative']==relative);row.update(bytes=p.stat().st_size,sha256=gate.sha(p))
                self.mutate_manifest(folder,update)
                with self.assertRaises(AssertionError):gate.verify_collected(folder,self.SOURCE)
                self.assert_outer_rejects(root)
    def test_original_mismatch_attachment_is_failure_only_and_survives_collection(self):
        from mac_host_lifecycle_pixels import ORIGINAL_DIAGNOSTIC
        from test_mac_host_lifecycle import sample_images
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.packet(root,False)
            raw=sample_images()['lifecycle-saved.png']
            (root/'mac-host-observed'/ORIGINAL_DIAGNOSTIC).write_bytes(raw)
            folder=self.collect(root);manifest=gate.verify_collected(folder,self.SOURCE)
            self.assertFalse(manifest['prerequisite_accepted'])
            self.assertEqual((folder/ORIGINAL_DIAGNOSTIC).read_bytes(),raw)
            self.assertEqual(next(row['kind'] for row in manifest['files'] if row['path']==ORIGINAL_DIAGNOSTIC),'optional-diagnostic')
            with self.assertRaisesRegex(AssertionError,'Rejected Original'):gate.verify_acceptance(root,self.SOURCE)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.packet(root,True)
            (root/'mac-host-observed'/ORIGINAL_DIAGNOSTIC).write_bytes(raw)
            with self.assertRaisesRegex(AssertionError,'Rejected Original'):self.collect(root)

    def test_owned_crash_diagnostics_precede_screenshots_without_acceptance_effect(self):
        from mac_owned_crash import OUTPUT,encode
        for accepted in [False,True]:
            with self.subTest(accepted=accepted),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.packet(root,accepted)
                row={'schema':'Celluloid.OwnedCrashCollectionError.1','source_sha':self.SOURCE,'acceptance':False,
                    'complete_host_e2e':False,'phase':'capture','state':'incomplete','error':'No matching safely bound incident'}
                (root/OUTPUT).write_bytes(encode(row))
                for i in range(2):(root/'mac-host-observed'/f'optional-{i}.jpg').write_bytes(b'x'*600_000)
                folder=self.collect(root);manifest=gate.verify_collected(folder,self.SOURCE)
                self.assertEqual(manifest['prerequisite_accepted'],accepted)
                self.assertEqual(json.loads((folder/OUTPUT).read_text()),row)
                self.assertLessEqual(sum(p.stat().st_size for p in folder.iterdir()),gate.CAP)
                entries=manifest['files'];crash_index=next(i for i,r in enumerate(entries) if r['path']==OUTPUT)
                self.assertTrue(all(i>crash_index for i,r in enumerate(entries) if r['path'].endswith('.jpg')))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.packet(root,True);row['source_sha']='wrong';(root/OUTPUT).write_bytes(encode(row))
            folder=self.collect(root);manifest=gate.verify_collected(folder,self.SOURCE)
            self.assertTrue(manifest['prerequisite_accepted']);self.assertFalse((folder/OUTPUT).exists())
            self.assertTrue(any(r['name']==OUTPUT and r['reason']=='invalid owned-crash diagnostic' for r in manifest['omitted']))

    def test_false_diagnostic_keeps_failure_and_available_ownership_source_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.packet(root,False)
            for i in range(3):(root/'mac-host-observed'/f'optional-{i}.jpg').write_bytes(b'x'*600_000)
            folder=self.collect(root);record=gate.verify_collected(folder,self.SOURCE)
            self.assertFalse(record['prerequisite_accepted']);self.assertEqual(record['proof_state'],'diagnostic-only-incomplete');self.assertTrue(record['missing_required_proof'])
            self.assertTrue((folder/'outcome.json').is_file());self.assertTrue((folder/'mac-host-source-before.json').is_file())
            self.assertEqual(json.loads((folder/'mac-host-acceptance.json').read_text())['error'],'AssertionError: extension not registered')
            result=self.outer(root);self.assertEqual(result.returncode,0,result.stderr)
    def test_synthetic_outer_collector_isolates_enclosing_route_and_source_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.packet(root,False);self.collect(root)
            for scope in ('uikit-full-shipping','photos-export-observation'):
                inherited={'GITHUB_SHA':'b'*40,'GITHUB_WORKFLOW_SHA':'c'*40,
                    'CELLULOID_VALIDATION_SCOPE':scope,'GITHUB_REF':'refs/heads/'+scope,
                    'GITHUB_WORKFLOW_REF':'100mango/Celluloid/.github/workflows/'+scope+'.yml@refs/heads/'+scope}
                with mock.patch.dict(os.environ,inherited):
                    before=dict(os.environ);result=self.outer(root)
                    self.assertEqual(result.returncode,0,result.stderr)
                    self.assertEqual(dict(os.environ),before)
                __import__('shutil').rmtree(root/'celluloid-bounded-evidence')

    def test_diagnostic_boolean_flip_cannot_manufacture_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.packet(root,False);folder=self.collect(root)
            self.update_file(folder,'mac-host-acceptance.json',lambda m:m.update(prerequisite_accepted=True))
            self.mutate_manifest(folder,lambda m:m.update(prerequisite_accepted=True,proof_state='complete-accepted-prerequisite',missing_required_proof=[]))
            with self.assertRaises(AssertionError):gate.verify_collected(folder,self.SOURCE)
            self.assert_outer_rejects(root)
    def test_self_consistent_hashes_cannot_hide_bad_runtime_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.packet(root);folder=self.collect(root)
            self.update_file(folder,'prerequisite.json',lambda m:m.update(prerequisite_passed=False))
            with self.assertRaises(AssertionError):gate.verify_collected(folder,self.SOURCE)
            self.assert_outer_rejects(root)
    def test_changed_hash_source_symlink_extra_or_duplicate_files_reject(self):
        mutations=[lambda f:(f/'outcome.json').write_text('{}'),
                   lambda f:(f/'unlisted.txt').write_text('unexpected'),
                   lambda f:self.mutate_manifest(f,lambda m:m.update(source_sha='b'*40)),
                   lambda f:self.mutate_manifest(f,lambda m:m['files'].append(m['files'][0])),
                   lambda f:self.update_file(f,'mac-host-acceptance.json',lambda m:m.update(source_sha='b'*40))]
        for mutate in mutations:
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.packet(root);folder=self.collect(root);mutate(folder)
                with self.assertRaises(AssertionError):gate.verify_collected(folder,self.SOURCE)
                self.assert_outer_rejects(root)
    def test_optional_collision_and_required_total_exhaustion_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.packet(root)
            (root/'mac-host-observed/mac-host-acceptance.json').write_text('{}')
            with self.assertRaisesRegex(AssertionError,'collides'):self.collect(root)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.packet(root)
            for name,size in [('mac-host-context.json',480_000),('mac-host-summary.json',140_000),('mac-host-product-after.json',140_000)]:
                p=root/name;record=json.loads(p.read_text());record['diagnostic_padding']='x'*(size-p.stat().st_size);gate.write(p,record)
            lifecycle_path=root/'mac-host-observed/lifecycle.json'
            lifecycle=gate.read_receipt(lifecycle_path);lifecycle['context_sha256']=gate.sha(root/'mac-host-context.json')
            lifecycle_path.write_text(json.dumps(lifecycle,separators=(',',':'))+'\n')
            RuntimeAcceptanceTests.write_transport_log(self,root)
            p=root/'mac-host-test.log';p.write_text(p.read_text()+' '*(299_000-p.stat().st_size))
            context=gate.read_receipt(root/'mac-host-context.json');records=gate.transport_records(root,context,complete=True)
            gate.write(root/'mac-host-transport-replay.json',gate.transport_report(root,context,records))
            gate.write(root/'mac-host-acceptance.json',gate.verify_acceptance(root,self.SOURCE))
            with self.assertRaisesRegex(AssertionError,'reserved host allocation'):self.collect(root)
    def test_missing_diagnostic_failure_or_oversized_available_proof_rejects(self):
        for mutate in [lambda r:(r/'mac-host-acceptance.json').unlink(),
                       lambda r:gate.write(r/'mac-host-acceptance.json',{'validation_route':dict(FULL_ROUTE),'host_entry_contract':gate.HOST_CONTRACT,'source_sha':self.SOURCE,'prerequisite_accepted':False,'complete_host_e2e':False,'error':''}),
                       lambda r:(r/'mac-host-source-before.json').write_bytes(b' '*160_001)]:
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.packet(root,False);mutate(root)
                with self.assertRaises(AssertionError):self.collect(root)

class HostTimeBudgetTests(SyntheticHostFixtureCase):
    def setUp(self):
        super().setUp()
        route_environment=mock.patch.dict(os.environ,GITHUB_REF='refs/heads/apple-platforms')
        route_environment.start();self.addCleanup(route_environment.stop)
    def prepare(self,root):
        gate.write(root/'mac-job-clock.json',{'source_sha':'a'*40,'started_monotonic':100.0,'started_unix':10000.0,'execution_budget_seconds':2460})
    def test_two_time_checks_reserve_twelve_minute_host_plus_five_minute_proof_tail(self):
        with tempfile.TemporaryDirectory() as folder,mock.patch.dict(os.environ,RUNNER_TEMP=folder,GITHUB_SHA='a'*40),mock.patch.object(gate,'require_runner'),mock.patch.object(gate.time,'monotonic',side_effect=[101.0,1200.0]):
            root=Path(folder);self.prepare(root);gate.budget('before-prepare');gate.budget('before-host')
            record=gate.read_receipt(root/'mac-host-budget.json');self.assertTrue(record['admitted']);self.assertEqual(record['checks'][-1]['required_seconds'],1020)
            self.assertGreaterEqual(record['checks'][-1]['remaining_seconds'],1020)
    def test_preparation_can_exhaust_budget_and_prevent_host_start(self):
        with tempfile.TemporaryDirectory() as folder,mock.patch.dict(os.environ,RUNNER_TEMP=folder,GITHUB_SHA='a'*40),mock.patch.object(gate,'require_runner'),mock.patch.object(gate.time,'monotonic',side_effect=[101.0,1541.0]):
            root=Path(folder);self.prepare(root);gate.budget('before-prepare')
            with self.assertRaisesRegex(RuntimeError,'incomplete'):gate.budget('before-host')
            record=gate.read_receipt(root/'mac-host-budget.json');self.assertFalse(record['admitted']);self.assertEqual(record['checks'][-1]['remaining_seconds'],1019)
            self.assertFalse((root/'mac-host-test.log').exists())
    def test_missing_wrong_or_future_clock_rejected(self):
        for update in [None,{'source_sha':'b'*40},{'execution_budget_seconds':2700},{'started_monotonic':2000.0},{'started_monotonic':True}]:
            with tempfile.TemporaryDirectory() as folder,mock.patch.dict(os.environ,RUNNER_TEMP=folder,GITHUB_SHA='a'*40),mock.patch.object(gate,'require_runner'),mock.patch.object(gate.time,'monotonic',return_value=1000.0):
                root=Path(folder)
                if update is not None:self.prepare(root);value=gate.read_receipt(root/'mac-job-clock.json');value.update(update);gate.write(root/'mac-job-clock.json',value)
                with self.assertRaises(AssertionError):gate.budget('before-host')
                self.assertFalse((root/'mac-host-test.log').exists())
    def test_decreasing_phase_admission_rejected(self):
        with tempfile.TemporaryDirectory() as folder,mock.patch.dict(os.environ,RUNNER_TEMP=folder,GITHUB_SHA='a'*40),mock.patch.object(gate,'require_runner'),mock.patch.object(gate.time,'monotonic',side_effect=[1500.0,1100.0]):
            root=Path(folder);self.prepare(root);gate.budget('before-prepare')
            with self.assertRaisesRegex(AssertionError,'Decreasing'):gate.budget('before-host')
            record=gate.read_receipt(root/'mac-host-budget.json');self.assertEqual(len(record['checks']),1)
    def test_shared_clock_validation_rejects_invalid_admission_and_replay(self):
        for value in [-1000,0,False,True,float('nan'),float('inf')]:
            with self.subTest(value=value),tempfile.TemporaryDirectory() as folder,mock.patch.dict(os.environ,RUNNER_TEMP=folder,GITHUB_SHA='a'*40),mock.patch.object(gate,'require_runner'),mock.patch.object(gate.time,'monotonic',return_value=1000.0):
                root=Path(folder);self.prepare(root);clock=gate.read_receipt(root/'mac-job-clock.json');clock['started_monotonic']=value;gate.write(root/'mac-job-clock.json',clock)
                with self.assertRaises((AssertionError,ValueError)):gate.budget('before-prepare')
                with self.assertRaises(AssertionError):gate.validate_clock(clock,'a'*40)
            with self.subTest(replay=value),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);RuntimeAcceptanceTests().seed(root)
                clock=gate.read_receipt(root/'mac-job-clock.json');clock['started_monotonic']=value;gate.write(root/'mac-job-clock.json',clock)
                report=gate.read_receipt(root/'mac-host-budget.json');report['clock_sha256']=gate.sha(root/'mac-job-clock.json')
                for row in report['checks']:
                    row['deadline_monotonic']=value+gate.JOB_EXECUTION_SECONDS;row['remaining_seconds']=row['deadline_monotonic']-row['observed_monotonic']
                gate.write(root/'mac-host-budget.json',report)
                with self.assertRaises((AssertionError,ValueError)):gate.verify_acceptance(root,'a'*40)
    def test_clock_constants_phase_types_and_replay_order_are_strict(self):
        def mutate_budget(root,key,value):
            p=root/'mac-host-budget.json';r=gate.read_receipt(p);r['checks'][1][key]=value;gate.write(p,r)
        for key,value in [('observed_monotonic',True),('observed_monotonic',float('inf')),('deadline_monotonic',float('nan')),('remaining_seconds',True),('required_seconds',True),('phase','before-prepare'),('admitted',1)]:
            with self.subTest(key=key,value=value),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);RuntimeAcceptanceTests().seed(root);mutate_budget(root,key,value)
                with self.assertRaises((AssertionError,ValueError)):gate.verify_acceptance(root,'a'*40)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);RuntimeAcceptanceTests().seed(root);r=gate.read_receipt(root/'mac-host-budget.json')
            for row,now in zip(r['checks'],[1500.0,1100.0]):row['observed_monotonic']=now;row['remaining_seconds']=2560-now
            gate.write(root/'mac-host-budget.json',r)
            with self.assertRaises((AssertionError,ValueError)):gate.verify_acceptance(root,'a'*40)
    def test_workflow_reserves_first_step_clock_and_finishes_compiles_before_host(self):
        workflow=(ROOT/'.github/workflows/apple-platforms.yml').read_text().split('  native-mac-host:',1)[1].split('  native-simulator:',1)[0]
        self.assertLess(workflow.index('Reserve Mac job collection time'),workflow.index('uses: actions/checkout@'))
        self.assertLess(workflow.index('Verify actual embedded sandbox extension before UI'),workflow.index('Actual Photos host discovery'))
        self.assertLess(workflow.index('Actual Photos host discovery'),workflow.index('Bound and replay the dedicated host proof'))
        shell=(ROOT/'Scripts/run_mac_photos_host_gate.sh').read_text()
        predecessor=workflow.split('- name: Prepare verified Photos host context',1)[1].split('- name:',1)[0]
        self.assertLess(predecessor.index('budget-before-prepare'),predecessor.index('source-before'))
        self.assertNotIn('budget-before-prepare',shell)
        self.assertLess(shell.index('budget-before-host'),shell.index('TEST_RUNNER_CELLULOID_MAC_PHOTOS_HOST_PREREQUISITE'))
        self.assertIn('timeout-minutes: 45',workflow)

class HostFixtureEnvironmentTests(unittest.TestCase):
    CI_SOURCE = '0995214f6a7a0a88c94aebe28fcb1b507d7ad4eb'

    def test_fixture_cases_override_only_their_source_and_restore_ci_environment(self):
        for owner in [RuntimeAcceptanceTests, CollectedProofTests, HostTimeBudgetTests]:
            with self.subTest(owner=owner.__name__), mock.patch.dict(os.environ, GITHUB_SHA=self.CI_SOURCE, GITHUB_WORKFLOW_SHA=self.CI_SOURCE, GITHUB_ACTIONS='true'):
                original = dict(os.environ)
                case = owner()
                case.setUp()
                try:
                    self.assertEqual(os.environ['GITHUB_SHA'], case.SOURCE)
                    self.assertEqual(os.environ['GITHUB_WORKFLOW_SHA'], self.CI_SOURCE)
                    with tempfile.TemporaryDirectory() as folder:
                        root = Path(folder)
                        RuntimeAcceptanceTests.seed(case, root)
                        self.assertTrue(gate.verify_acceptance(root, case.SOURCE)['prerequisite_accepted'])
                finally:
                    case.doCleanups()
                self.assertEqual(dict(os.environ), original)

    def test_source_environment_restores_after_failure_and_when_initially_absent(self):
        class DeliberateFailure(SyntheticHostFixtureCase):
            def runTest(self):
                self.assertEqual(os.environ['GITHUB_SHA'], self.SOURCE)
                self.fail('Synthetic cleanup regression probe')
        for initial in [None, self.CI_SOURCE]:
            with self.subTest(initial=initial), mock.patch.dict(os.environ):
                if initial is None: os.environ.pop('GITHUB_SHA', None)
                else: os.environ['GITHUB_SHA'] = initial
                original = dict(os.environ)
                result = unittest.TestResult()
                DeliberateFailure().run(result)
                self.assertEqual(result.testsRun, 1)
                self.assertEqual(len(result.failures), 1)
                self.assertEqual(len(result.errors), 0)
                self.assertEqual(dict(os.environ), original)

    def test_real_transport_source_guard_still_rejects_foreign_ci_source(self):
        with mock.patch.dict(os.environ, GITHUB_SHA=self.CI_SOURCE), tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fixture = RuntimeAcceptanceTests()
            fixture.setUp()
            try:
                fixture.seed(root)
                context = gate.read_receipt(root/'mac-host-context.json')
                self.assertTrue(gate.transport_records(root, context, complete=True))
            finally:
                fixture.doCleanups()
            self.assertEqual(os.environ['GITHUB_SHA'], self.CI_SOURCE)
            with self.assertRaises(AssertionError):
                gate.transport_records(root, context, complete=True)


if __name__ == '__main__': unittest.main()
