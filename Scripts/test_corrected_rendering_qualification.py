"""Portable control regressions, not native rendering evidence."""
from pathlib import Path
import copy,json,os,subprocess,tempfile,unittest
from unittest.mock import patch
import corrected_rendering_admission as admission
import run_corrected_rendering_qualification as runner
import run_early_uikit_interop as early
import verify_interop_continuation as gate
import test_platform_rendering_contract as parser_fixtures
from verify_required_interoperability import MAC_REQUIRED_CASES

class CorrectedRenderingTests(unittest.TestCase):
    def facts(self):
        cfg={'schema':1,'READY':True,'sourceReady':True,'product_sha':admission.PRODUCT_SHA,'product_tree':admission.PRODUCT_TREE,'maximum_additional_spend_usd':0,'confirmation':'RUN_ONE_CORRECTED_V2_JOB_ZERO_USD'}
        context={'repository':'100mango/Celluloid','event':'push','ref':'refs/heads/'+admission.BRANCH,'workflow_ref':'100mango/Celluloid/'+admission.WORKFLOW+'@refs/heads/'+admission.BRANCH,'attempt':'1','mode':'corrected-v2','sha':'a'*40,'workflow_sha':'a'*40,'run_id':'123'}
        facts={'head':'a'*40,'tree':'b'*40,'parent_tree':admission.PRODUCT_TREE,'dirty':'','changed_paths':sorted(admission.CONTROL_PATHS),'chain':[{'sha':'a'*40,'parents':[admission.PRODUCT_SHA],'changed_paths':sorted(admission.CONTROL_PATHS)}]}
        return cfg,context,facts
    def test_closed_route_stops_before_any_git_or_native_action(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'.github').mkdir();(root/admission.CONFIG).write_text(json.dumps({'READY':False,'sourceReady':False}))
            with patch.object(admission,'git') as git,self.assertRaisesRegex(ValueError,'closed'):admission.admit(root,{})
            git.assert_not_called()
    def test_exact_corrected_source_control_is_distinct_from_original_control(self):
        cfg,context,facts=self.facts();row=admission.validate(cfg,context,facts)
        self.assertEqual(row['product_sha'],admission.PRODUCT_SHA);self.assertEqual(row['source_sha'],'a'*40)
        self.assertNotEqual(row['current_uikit_fingerprint'],early.FROZEN_UIKIT_FINGERPRINT)
        self.assertFalse(row['photos_host_qualified']);self.assertFalse(row['release_qualified'])
    def test_wrong_source_branch_cost_retry_dirty_or_product_changes_fail(self):
        changes=[lambda c,e,f:c.update(READY=False),lambda c,e,f:c.update(sourceReady=False),lambda c,e,f:c.update(product_sha='d'*40),lambda c,e,f:c.update(product_tree='e'*40),lambda c,e,f:c.update(maximum_additional_spend_usd=True),lambda c,e,f:c.update(maximum_additional_spend_usd=1),lambda c,e,f:c.update(extra=True),lambda c,e,f:e.update(attempt='2'),lambda c,e,f:e.update(ref='refs/heads/codex/old'),lambda c,e,f:e.update(event='workflow_dispatch'),lambda c,e,f:e.update(workflow_sha='f'*40),lambda c,e,f:f.update(dirty='M app.swift'),lambda c,e,f:f['changed_paths'].append('Celluloid/AppDelegate.swift'),lambda c,e,f:f['chain'][0]['changed_paths'].append('Celluloid/AppDelegate.swift'),lambda c,e,f:f['chain'][0]['parents'].append('f'*40)]
        for change in changes:
            c,e,f=self.facts();change(c,e,f)
            with self.subTest(change=change),self.assertRaises(ValueError):admission.validate(c,e,f)
    def test_complete_dependency_manifest_matches_actual_current_inputs(self):
        paths=json.loads((admission.ROOT/'Scripts/fixtures/corrected-rendering-dependencies.json').read_text())['files']
        # The same actual file inventory is used in portable snapshots without Git history.
        all_paths=sorted(str(p.relative_to(admission.ROOT)) for p in admission.ROOT.rglob('*') if p.is_file() and '.git' not in p.parts and '__pycache__' not in p.parts)
        with patch.object(admission,'git',return_value='\0'.join(all_paths)):
            result=admission.check_dependencies()
        self.assertEqual(result['file_count'],372);self.assertEqual(len(paths),372)
        self.assertTrue(result['historical_differences'])
    def test_historical_freeze_and_unknown_mode_remain_closed(self):
        self.assertEqual(early.FROZEN_UIKIT_SHA,'d9a9fe00b79b8199877d81ced8abac7bde4784b6')
        self.assertEqual(early.FROZEN_UIKIT_FINGERPRINT,'5b648707e5f204c18007cd1158ccea7622387cbb277c8fe09b42b7587283cc35')
        with patch.dict(os.environ,{'CELLULOID_RENDERING_QUALIFICATION':''}):self.assertIsNone(early.corrected_source_admission())
        with patch.dict(os.environ,{'CELLULOID_RENDERING_QUALIFICATION':'arbitrary'}),self.assertRaises(ValueError):early.corrected_source_admission()
    def corrected_packet(self,mutate=None,platform=True):
        fixture=parser_fixtures.PlatformContractTests();source=fixture.SOURCE
        c,e,f=self.facts();record=admission.validate(c,e,f)
        with tempfile.TemporaryDirectory() as folder:
            temp=Path(folder);packet,summaries=fixture.packet(temp)
            packet.pop('frozen_uikit_source');packet.update(source_mode='corrected-v2',corrected_source_admission=copy.deepcopy(record),frozen_control_source=record['frozen_control_source'],uikit_production_fingerprint=record['current_uikit_fingerprint'])
            if mutate:mutate(packet,temp)
            (temp/'early-uikit-interop.json').write_text(json.dumps(packet))
            def command(args,**kwargs):
                names={'CelluloidEarlyUIKit2x.xcresult':'2x','CelluloidEarlyUIKit3x.xcresult':'3x'}
                value={'devices':{}} if 'simctl' in args else summaries[names[Path(args[-1]).name]]
                return subprocess.CompletedProcess(args,0,json.dumps(value),'')
            with patch.object(gate.subprocess,'check_output',side_effect=[source+'\n','']),patch.object(gate,'frozen_uikit_fingerprint',return_value=record['current_uikit_fingerprint']),patch.object(gate,'corrected_source_admission',return_value=record),patch.object(gate,'run',side_effect=command):
                return gate.verify(temp,source,platform_contract=platform)
    def test_corrected_consumer_still_requires_unchanged_v2_and_keeps_historical_red(self):
        row=self.corrected_packet();self.assertTrue(row['platform_contract_accepted']);self.assertTrue(row['continuation_safe'])
        self.assertFalse(row['strict_pixel_passed']);self.assertFalse(row['final_archive_accepted'])
        self.assertEqual(row['uikit_fingerprint'],admission.CURRENT_UIKIT_FINGERPRINT)
        with self.assertRaises(ValueError):self.corrected_packet(platform=False)
    def test_corrected_receipt_mismatch_and_missing_actual_consumer_reject(self):
        edits=[lambda p,t:p.update(frozen_uikit_source=early.FROZEN_UIKIT_SHA),lambda p,t:p.update(source_mode='historical'),lambda p,t:p.update(frozen_control_source='f'*40),lambda p,t:p['corrected_source_admission'].update(product_sha='f'*40),lambda p,t:p['profiles'].pop(),lambda p,t:p['profiles'][0]['cleanup'][0].update(exit_code=1),lambda p,t:(t/'early-uikit-2x-interop.log').write_text((t/'early-uikit-2x-interop.log').read_text().replace('"full": 0','"full": 3'))]
        for edit in edits:
            with self.subTest(edit=edit),self.assertRaises((ValueError,KeyError)):self.corrected_packet(edit)
    def test_mac_all43_actual_named_outcomes_and_official_summary_are_required(self):
        rows=[]
        for name in MAC_REQUIRED_CASES:
            owner,method=name.split('.');case=f'Test Case \'-[CelluloidMacPhotosExtensionTests.{owner} {method}]\''
            rows.extend([case+' started.',case+' passed (0.1 seconds).'])
        rows+=['Executed 43 tests, with 0 failures (0 unexpected)','** TEST SUCCEEDED **']
        log='\n'.join(rows)+'\n';summary={'result':'Passed','totalTestCount':43,'passedTests':43,'failedTests':0,'skippedTests':0,'expectedFailures':0,'testFailures':[],'runtimeWarnings':[],'startTime':1,'finishTime':2}
        runner.mac_outcome(log,summary,0)
        for mutation in [dict(passedTests=42),dict(runtimeWarnings=[{'message':'warning'}]),dict(expectedFailures=1),dict(finishTime=1),dict(totalTestCount=True)]:
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):runner.mac_outcome(log,dict(summary,**mutation),0)
        with self.assertRaises(ValueError):runner.mac_outcome(log.replace(' passed (0.1 seconds).',' skipped (0.1 seconds).',1),summary,0)
        with self.assertRaises(ValueError):runner.mac_outcome(log,summary,65)
    def test_corrected_timeout_blocks_readback_cleanup_and_next_device(self):
        import contextlib,io
        commands=[];timeout_index=[];device='12345678-1234-1234-1234-123456789AB1'
        def invoke(args,**kwargs):
            args=list(map(str,args));commands.append(args);stdout=''
            if args[:4]==['xcrun','simctl','list','runtimes']:
                stdout=json.dumps({'runtimes':[{'version':'27.0','isAvailable':True,'identifier':'com.apple.CoreSimulator.SimRuntime.iOS-27-0'}]})
            elif args[:4]==['xcrun','simctl','list','devicetypes']:
                stdout=json.dumps({'devicetypes':[{'name':name,'identifier':'owned-'+profile} for profile,name,_ in early.PROFILES]})
            elif args[:3]==['xcrun','simctl','create']:stdout=device
            elif len(args)>1 and args[1].endswith('stage_uikit_layer_fixture.py'):
                Path(args[-1]).write_text(json.dumps({'binary_sha256':'a'*64}))
            elif 'test-without-building' in args:
                timeout_index.append(len(commands));raise TimeoutError('owned process-group termination unconfirmed')
            return subprocess.CompletedProcess(args,0,stdout,'')
        record={'current_uikit_fingerprint':early.FROZEN_UIKIT_FINGERPRINT,'frozen_control_source':admission.CONTROL_SOURCE}
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,RUNNER_TEMP=folder,GITHUB_SHA='a'*40,GITHUB_RUN_ID='123',GITHUB_RUN_ATTEMPT='1',CELLULOID_RENDERING_QUALIFICATION='corrected-v2'),patch.object(admission,'_NATIVE_BLOCKED',False),patch.object(early,'corrected_source_admission',return_value=record),patch.object(early,'frozen_uikit_fingerprint',return_value=early.FROZEN_UIKIT_FINGERPRINT),patch.object(early,'layer_from_log',return_value=b'{}'),patch.object(early,'run',side_effect=invoke),patch.object(early,'readback_installation',side_effect=lambda bound,*args:bound(['xcrun','simctl','get_app_container',device,'Mango.Celluloid'])),patch.object(early,'capture_file_open_observation',side_effect=lambda bound,*args:bound(['xcrun','simctl','spawn',device,'log'])),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeError):early.main()
            self.assertEqual(len(timeout_index),1);self.assertEqual(len(commands),timeout_index[0])
            report=json.loads((Path(folder)/'early-uikit-interop.json').read_text())
            self.assertEqual(len(report['profiles']),1);self.assertFalse(report['cleanup_passed']);self.assertFalse(report['passed'])
            marker=Path(folder)/admission.NATIVE_MARKER;first=marker.read_bytes()
            self.assertIn('termination unconfirmed',first.decode())
            admission.mark_native_failure(ValueError('later failure'))
            self.assertEqual(marker.read_bytes(),first)
            with self.assertRaises(ValueError):admission.require_native_clear()
    def test_corrected_collector_cannot_dispatch_optional_native_exports(self):
        import ast
        source=(admission.ROOT/'Scripts/collect_native_evidence.py').read_text();tree=ast.parse(source)
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='optional_export')
        namespace={'os':os,'OptionalExportError':RuntimeError}
        exec(compile(ast.Module(body=[function],type_ignores=[]),'collector-dispatch-test','exec'),namespace)
        with patch.dict(os.environ,CELLULOID_RENDERING_QUALIFICATION='corrected-v2'),self.assertRaisesRegex(RuntimeError,'not admitted'):
            namespace['optional_export'](['xcrun','xcresulttool','export'],60)
        for name in ['corrected-mac-summary.json','corrected-rendering-result.json','corrected-native-dispatch-failure.json']:
            self.assertIn(name,source)
    def test_source_finalization_has_a_single90_second_git_budget(self):
        with patch.object(admission,'_ADMISSION_DEADLINE',10),patch.object(admission.time,'monotonic',return_value=11),patch.object(admission.subprocess,'check_output') as command,self.assertRaises(ValueError):admission.git('status')
        command.assert_not_called()
    def test_single_closed_job_keeps_runtime_budgets_no_host_or_signing_activation(self):
        import hashlib,re
        path=admission.ROOT/admission.WORKFLOW;source=path.read_text()
        # Pin the complete reviewed workflow first; no general YAML normalization
        # can hide another job, trigger, permission, step, command or timeout.
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),'8ae56984b1cbd7270e969bf5fcf87ca40e6c6467fb68686ad520e39d42ec56c5')
        self.assertEqual(re.findall(r'^  ([a-z][a-z0-9-]*):$',source.split('jobs:\n',1)[1],re.M),['corrected-v2'])
        self.assertIn("    if: ${{ false && github.event_name == 'push' && github.ref == 'refs/heads/"+admission.BRANCH+"' }}",source)
        self.assertEqual(re.findall(r'^    runs-on: (.+)$',source,re.M),['xcode-27'])
        self.assertEqual(re.findall(r'^    timeout-minutes: (.+)$',source,re.M),['45'])
        self.assertIn('    branches: ['+admission.BRANCH+']\n',source)
        self.assertIn('permissions:\n  contents: read\n',source)
        self.assertEqual(early.ACTIVE_SECONDS,18*60);self.assertEqual(runner.WORK_SECONDS,38*60)
        driver=(admission.ROOT/'Scripts/run_corrected_rendering_qualification.py').read_text()
        self.assertNotIn('MacPhotosHostUITests',driver);self.assertIn('CODE_SIGNING_ALLOWED=NO',driver)
        self.assertIn("'mac-deterministic'",driver);self.assertIn("'uikit-two-profiles'",driver)
        self.assertIs(json.loads((admission.ROOT/admission.CONFIG).read_text())['READY'],False)


    def test_final_version_source_cannot_reuse_previous_product_admission(self):
        old_sha='b5dbd3863b931a549d024a22070242ea4d9c9be3'
        old_tree='8d144ec388b72ccf71d67fbec1f284120629e471'
        self.assertNotEqual(admission.PRODUCT_SHA,old_sha)
        self.assertEqual(admission.PRODUCT_TREE,'f2c6d0f38c026957b0b34f22b916eb80ed5b20a8')
        for change in [lambda c,e,f:c.update(product_sha=old_sha),lambda c,e,f:c.update(product_tree=old_tree),lambda c,e,f:f.update(parent_tree=old_tree),lambda c,e,f:f['chain'][0].update(parents=[old_sha])]:
            c,e,f=self.facts();change(c,e,f)
            with self.subTest(change=change),self.assertRaises(ValueError):admission.validate(c,e,f)

    def test_each_rebound_metadata_input_remains_required(self):
        inputs=['Celluloid.xcodeproj/project.pbxproj','Celluloid/Info.plist','CelluloidKit/Info.plist','CelluloidPhotoExtension/Info.plist']
        original=Path.read_bytes
        for relative in inputs:
            target=admission.ROOT/relative
            def changed(path,target=target):return b'unreviewed-or-old-metadata' if path==target else original(path)
            with self.subTest(path=relative),patch.object(Path,'read_bytes',changed),self.assertRaisesRegex(ValueError,'Changed dependency: '+relative):
                admission.check_dependencies()

    def test_final_rebind_keeps_source_and_activation_closed_and_routes_isolated(self):
        import fnmatch,hashlib,re
        config=json.loads((admission.ROOT/admission.CONFIG).read_text())
        self.assertIs(config['READY'],False);self.assertIs(config['sourceReady'],False)
        product_workflows={'.github/workflows/apple-platforms.yml': '7b9cc75504d637d766c0fab1180677736a90121b299f356f405266d7a13216e6', '.github/workflows/ios-cancellation-matrix.yml': '6c89d6f2c65b0c852b997d4c53293113464e05e222b544c69f4dbca2de664a84', '.github/workflows/ios-extension-cancellation.yml': 'ecb8679c6780d01889a448d9146900661fcdecb810108ee493fc55eb73f3aa1d', '.github/workflows/ios.yml': '08f1244d4acdd415e15dbfc1c9a4f54c507323944638b8fbe73a7988a6ff80d9', '.github/workflows/mac-repair.yml': '1f6cf90e7609ed1627df856a4f42d5d3ef83a3a1c1088b1ecf4629dbbc697404', '.github/workflows/original-ios-release.yml': 'c03f507f5064c445aed856b14f919f473c2b60a0b2d1e044277cf876bc1b3045', '.github/workflows/photos-export-observation.yml': '9067e52a2982c0ef1bd97f4f50ea1084af834ac9fdc610484cc0bdf7fc19de1d', '.github/workflows/swiftui-first-native.yml': 'b70f6b8609e9e6d84523bb955a78458430a3ec22eae7ab40ae3d5a21711ff0c1', '.github/workflows/uikit-full-shipping.yml': 'bc272f45eb2c68138efae581eb07ce1f3408acd4101f1c372bcfecb829e12323'}
        files={str(p.relative_to(admission.ROOT)):p for p in (admission.ROOT/'.github/workflows').glob('*.yml')}
        self.assertEqual(set(files),set(product_workflows)|{admission.WORKFLOW})
        matched=[]
        for name,path in sorted(files.items()):
            if name in product_workflows:self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),product_workflows[name])
            else:self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),'8ae56984b1cbd7270e969bf5fcf87ca40e6c6467fb68686ad520e39d42ec56c5')
            # Exact bytes are already pinned above. These are the only two
            # reviewed branch-list spellings in this closed workflow inventory.
            text=path.read_text()
            inline=re.findall(r'^[ ]+branches: \[([^\]\n]+)\][ ]*$',text,re.M)
            block=re.findall(r'^[ ]+branches:[ ]*\n[ ]+-[ ]+([^\s#]+)[ ]*$',text,re.M)
            branches=[item.strip() for line in inline for item in line.split(',')]+block
            self.assertEqual(len(branches),1,name)
            if any(fnmatch.fnmatchcase(admission.BRANCH,pattern) for pattern in branches):matched.append(str(path.relative_to(admission.ROOT)))
            self.assertFalse(any(fnmatch.fnmatchcase('celluloid-release-preparation',pattern) for pattern in branches))
        self.assertEqual(matched,[admission.WORKFLOW])



def validate_test_only_pause_source(source):
    """Exact reversible edit: preserve all native method bodies except reviewed pauses."""
    import hashlib
    helper='''    // The production writer runs at User-initiated QoS. Give its test-only
    // semaphore signal the same explicit QoS instead of inheriting XCTest's
    // potentially Utility test-thread priority. Cancellation/replacement still
    // happens on the test thread before this asynchronous release is submitted.
    private func releasePrewriteBarrier(_ release: DispatchSemaphore) {
        DispatchQueue.global(qos: .userInitiated).async(qos: .userInitiated, flags: .enforceQoS) {
            release.signal()
        }
    }
'''
    paused='''{
            entered.fulfill()
            XCTAssertEqual(release.wait(timeout: .now() + 5), .success, "Pre-write test barrier timed out")
        }'''
    if source.count(helper)!=1 or source.count(paused)!=2:
        raise ValueError('Changed matched-QoS helper or bounded asserted pause')
    source=source.replace(helper,'',1).replace(paused,'{ entered.fulfill(); _ = release.wait(timeout: .now() + 5) }')
    pairs=[('operation.cancel(); releasePrewriteBarrier(release)','operation.cancel(); release.signal()'),
           ('        releasePrewriteBarrier(release)\n        wait(for: [oldDone, newDone]','        release.signal()\n        wait(for: [oldDone, newDone]')]
    for current,original in pairs:
        if source.count(current)!=1:raise ValueError('Changed release placement or race ordering')
        source=source.replace(current,original,1)
    if hashlib.sha256(source.encode()).hexdigest()!=admission.TEST_OVERLAY_BASE_SHA256:
        raise ValueError('Unexpected native test change outside the two exact pauses')

class TestOnlyPauseOverlayTests(unittest.TestCase):
    def source(self):return (admission.ROOT/admission.TEST_OVERLAY).read_text()
    def test_exact_reversible_overlay_preserves_nine_methods_and_all_race_assertions(self):
        import re
        validate_test_only_pause_source(self.source())
        actual=re.findall(r'^    func (test[A-Za-z0-9_]+)\(',self.source(),re.M)
        self.assertEqual(len(actual),9)
        expected={x.split('.',1)[1] for x in MAC_REQUIRED_CASES if x.startswith('PhotosOutputWriteTests.')}
        self.assertEqual(set(actual),expected)
    def test_wrong_qos_unenforced_direct_or_ignored_timeout_mutations_fail(self):
        source=self.source()
        mutations=[source.replace('qos: .userInitiated','qos: .utility',1),
                   source.replace(', flags: .enforceQoS','',1),
                   source.replace('operation.cancel(); releasePrewriteBarrier(release)','operation.cancel(); release.signal()',1),
                   source.replace('XCTAssertEqual(release.wait(timeout: .now() + 5), .success, "Pre-write test barrier timed out")','_ = release.wait(timeout: .now() + 5)',1),
                   source.replace('timeout: .now() + 5','timeout: .now() + 50',1),
                   source.replace('operation.cancel(); releasePrewriteBarrier(release)','releasePrewriteBarrier(release); operation.cancel()',1),
                   source.replace('        old.cancel()\n','',1),
                   source.replace('Data("new".utf8)','Data("old".utf8)',1)]
        for changed in mutations:
            with self.subTest(change=changed),self.assertRaises(ValueError):validate_test_only_pause_source(changed)
    def test_native_dependency_rejects_unpinned_test_bytes_and_keeps_product_identity(self):
        original=Path.read_bytes;target=admission.ROOT/admission.TEST_OVERLAY
        def changed(path):return b'unreviewed test pause' if path==target else original(path)
        with patch.object(Path,'read_bytes',changed),self.assertRaisesRegex(ValueError,'Unreviewed test-only'):
            admission.check_dependencies()
        self.assertEqual(admission.PRODUCT_SHA,'13e9a1ed63c6e7744803419f27e429a759df1209')
        self.assertEqual(admission.CURRENT_UIKIT_FINGERPRINT,'f3da35962bd29598de93dacf810bf7d521478d91839e3e1d9cd99e2808548970')
        self.assertEqual(len(admission.CONTROL_PATHS),10)
        self.assertIn(admission.TEST_OVERLAY,admission.CONTROL_PATHS)
        self.assertNotIn('CelluloidPhotoExtension/PhotosOutputWrite.swift',admission.CONTROL_PATHS)
    def test_receipt_discloses_exact_test_override_and_requires_it_in_control_closure(self):
        cfg,env,facts=CorrectedRenderingTests().facts()
        result=admission.validate(cfg,env,facts)
        self.assertEqual(result['test_control_overlay'],{'path':admission.TEST_OVERLAY,'base_product_sha256':admission.TEST_OVERLAY_BASE_SHA256,'control_sha256':admission.TEST_OVERLAY_SHA256})
        facts['changed_paths'].remove(admission.TEST_OVERLAY)
        with self.assertRaises(ValueError):admission.validate(cfg,env,facts)

if __name__=='__main__':unittest.main()
