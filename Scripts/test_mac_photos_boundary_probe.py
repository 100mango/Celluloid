"""Portable fault tests only; never native Photos execution or compilation."""
import base64,copy,json,os,plistlib,tempfile,unittest
from pathlib import Path
from unittest import mock
import mac_photos_boundary_probe as p
import test_mac_host_transport as host_fixtures
from test_mac_host_self_identity import payload,receipt
import final_mac_photos_transport as transport
from final_mac_photos_route import HOST_ONLY,host_clock_profile
ROOT=Path(__file__).resolve().parents[1]

class BoundaryProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name).resolve()
        self.lease=dict(schema='Celluloid.OwnedPhotosBoundaryLease.1',source_sha='a'*40,source_tree='b'*40,
            run_id='123456',run_attempt='1',fixture_sha256=p.FIXTURE,nonce='c'*64,raw_cap='131072')
        extension='/Users/runner/app/Contents/PlugIns/CelluloidMacPhotosExtension.appex'
        executable=extension+'/Contents/MacOS/CelluloidMacPhotosExtension'
        self.context={'source_sha':'a'*40,'extension_id':p.BUNDLE,'extension_path':extension,
            'extension_executable':executable,'extension_debug_dylib':executable+'.debug.dylib',
            'extension_executable_sha256':'e'*64,'extension_debug_dylib_sha256':'f'*64,
            'boundary_probe':{'lease':self.lease}}
        self.identity=payload(self.context)
        self.identity_raw=p.json_bytes(self.identity).decode()
        self.source=b'actual input is intentionally different from F';self.jpeg=b'\xff\xd8\xffsame production Data'
        self.arm={'schema':'Celluloid.OwnedPhotosBoundaryArm.1','lease':self.lease,
            'identity_sha256':p.sha(self.identity_raw.encode()),'generation':self.identity['generation'],
            'input_sha256':p.sha(self.source),'recipe_sha256':'1'*64,'source_id':'12345678-1234-4321-8123-123456789ABC'}
        self.row=dict(self.arm,schema='Celluloid.OwnedPhotosBoundaryCapture.1',identity_raw=self.identity_raw,
            capture_stage='before-writer-start-intended-same-jpeg',writer_claim_observed=False,
            photos_acceptance_observed=False,performance_acceptance=False,orientation=1,
            input_bytes=len(self.source),intended_jpeg_bytes=len(self.jpeg),intended_jpeg_sha256=p.sha(self.jpeg),
            checked_budget_ms=500,hard_realtime_bound=False,elapsed_before_receipt_ms=1.0)
        self.folder=self.home/'Library'/'Containers'/p.BUNDLE/'Data'/'Library'/'Caches'/'CelluloidOwnedPhotosBoundary'/self.lease['nonce']/self.arm['generation']
        self.folder.mkdir(parents=True);self.write()
    def write(self):
        (self.folder/'input.bytes').write_bytes(self.source);(self.folder/'intended.jpg').write_bytes(self.jpeg)
        (self.folder/'capture.json').write_bytes(p.json_bytes(self.row))
    def read(self):return p.read_capture(self.context,self.arm,self.identity_raw,self.home)
    def test_exact_three_nodes_and_actual_input_not_fixture(self):
        result=self.read();self.assertEqual(set(result),{'input.bytes','intended.jpg','capture.json'})
        self.assertEqual(result['input.bytes'],self.source);self.assertNotEqual(p.sha(self.source),p.FIXTURE)
    def test_lease_types_keys_attempt_fixture_nonce_run_caps(self):
        for key,value in [('run_attempt','2'),('run_id','0'),('run_id',123),('nonce','../elsewhere'),
            ('fixture_sha256','0'*64),('source_tree','z'*40),('raw_cap','262144'),('extra','x')]:
            row=dict(self.lease);row[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):p.lease_valid(row)
    def test_prepare_only_copies_original_and_bind_exact_processed_product(self):
        original=(ROOT/'Platforms/macOSExtension/Info.plist').read_bytes()
        with mock.patch.object(p.secrets,'token_hex',return_value='c'*64):
            lease,derived=p.prepare_lease(original,'a'*40,'b'*40,'123456','1')
        self.assertEqual(lease,self.lease)
        value=plistlib.loads(derived);value.pop('CelluloidOwnedPhotosBoundaryLease')
        self.assertEqual(value,plistlib.loads(original))
        context={k:v for k,v in self.context.items() if k!='boundary_probe'}
        context['runner_environment']={'GITHUB_SHA':'a'*40,'GITHUB_WORKFLOW_SHA':'a'*40,'GITHUB_ACTIONS':'true',
            'GITHUB_REPOSITORY':'100mango/Celluloid','GITHUB_EVENT_NAME':'push','GITHUB_RUN_ID':'123456','GITHUB_RUN_ATTEMPT':'1'}
        info=plistlib.loads(derived);info['CFBundleIdentifier']=p.BUNDLE
        self.assertEqual(p.bind_context(context,lease,plistlib.dumps(info))['boundary_probe']['lease'],lease)
        for key,value in [('GITHUB_RUN_ID','123457'),('GITHUB_RUN_ATTEMPT','2'),('GITHUB_WORKFLOW_SHA','b'*40)]:
            changed=copy.deepcopy(context);changed['runner_environment'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):p.bind_context(changed,lease,plistlib.dumps(info))
        info['CelluloidOwnedPhotosBoundaryLease']['nonce']='d'*64
        with self.assertRaises(ValueError):p.bind_context(context,lease,plistlib.dumps(info))
    def test_missing_receipt_never_authorizes_partial_raw_files(self):
        (self.folder/'capture.json').unlink()
        with self.assertRaises(FileNotFoundError):self.read()
    def test_permission_denial_propagates_without_fallback(self):
        with mock.patch.object(p.os,'open',side_effect=PermissionError('owned synthetic capture denied')) as opened:
            with self.assertRaises(PermissionError):self.read()
            self.assertEqual(opened.call_count,1)
    def test_symlink_file_and_directory_reject(self):
        path=self.folder/'input.bytes';path.unlink();path.symlink_to(self.folder/'intended.jpg')
        with self.assertRaises(OSError):self.read()
        path.unlink();self.write()
        self.folder.rename(self.folder.with_name('moved'));self.folder.symlink_to(self.folder.with_name('moved'),target_is_directory=True)
        with self.assertRaises(OSError):self.read()
    def test_hardlinks_oversize_and_changed_input_reject(self):
        path=self.folder/'input.bytes';os.link(path,self.folder/'other')
        with self.assertRaises(ValueError):self.read()
        (self.folder/'other').unlink();path.write_bytes(b'x'*65537)
        with self.assertRaises(ValueError):self.read()
        path.write_bytes(b'other input')
        with self.assertRaises(ValueError):self.read()
    def test_wrong_run_generation_arm_and_truth_boundary_reject(self):
        for key,value in [('generation','AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA'),('input_sha256','0'*64),
            ('identity_raw',self.identity_raw+' '),('writer_claim_observed',True),('photos_acceptance_observed',True),
            ('performance_acceptance',True),('hard_realtime_bound',True),('capture_stage','after-Photos-save'),
            ('orientation',True),('input_bytes',True),('elapsed_before_receipt_ms',501),('extra',False)]:
            original=self.row;self.row=dict(original);self.row[key]=value;self.write()
            with self.subTest(key=key),self.assertRaises(ValueError):self.read()
            self.row=original
        self.write();self.row['lease']=dict(self.lease,run_id='123457');self.write()
        with self.assertRaises(ValueError):self.read()
    def test_partial_write_hash_and_jpeg_header_reject(self):
        (self.folder/'intended.jpg').write_bytes(self.jpeg[:-1])
        with self.assertRaises(ValueError):self.read()
        self.jpeg=b'not jpeg';self.row.update(intended_jpeg_bytes=len(self.jpeg),intended_jpeg_sha256=p.sha(self.jpeg));self.write()
        with self.assertRaises(ValueError):self.read()
    def test_reader_deadline_not_restarted(self):
        with mock.patch.object(p.time,'monotonic',side_effect=[10,10.1,12.1]):
            with self.assertRaisesRegex(ValueError,'budget'):self.read()
    def test_duplicate_json_and_nonfinite_reject(self):
        for raw in ['{"x":1,"x":2}','{"x":NaN}','{"x":Infinity}']:
            with self.subTest(raw=raw),self.assertRaises(ValueError):p.decode(raw)
    def transcript(self,result='Passed',outcome_override=None,omit_outcome=False,denial=False,omit_saved=False):
        base=host_fixtures.HostTransportTests();base.setUp()
        base.context.update(self.context)
        # Bind the current diagnostic route before hashing any context or proof.
        # The reused helper supplies only synthetic proof rows, not its old clock.
        base.context['validation_route']=dict(HOST_ONLY)
        base.context['host_clock_profile']=host_clock_profile(HOST_ONLY)
        base.context['runner_environment']={'RUNNER_TEMP':'/Users/runner/temp','GITHUB_RUN_ID':'123456','GITHUB_RUN_ATTEMPT':'1','GITHUB_SHA':'a'*40,'GITHUB_WORKFLOW_SHA':'a'*40}
        self.context=base.context
        raw_context=p.json_bytes(self.context);base.context_hash=p.sha(raw_context)
        photos={'pid':122};ownership={'fixture_sha256':p.FIXTURE,'asset_label':'owned synthetic','initial_count':0,'selected_count':1}
        identity_receipt=receipt(self.context,photos,ownership)
        identity_receipt['observations']=[{'raw':self.identity_raw,'bytes':len(self.identity_raw),'sha256':p.sha(self.identity_raw.encode())}]*2
        values={'transport.json':transport.expected_transport(self.context,base.context_hash),'photos-process.json':photos,
            'fixture-ownership.json':ownership,'extension-self-identity.json':identity_receipt}
        outcome={'source_sha':self.context['source_sha'],'host_entry_contract':'Celluloid.PhotosHostEntry.3',
            'last_stage':p.SAVE_STAGE,'complete_host_e2e':False,'save_reopen_cancel_revert':'PhotosFilterLifecycle.1 incomplete'}
        reason='Unadmitted Photos confirmation or access alert; no action taken' if denial else p.PIXEL_REASON
        failure_text='failed: caught error: "Error Domain=MacPhotosHostPrerequisite Code=1 "'+reason+'" UserInfo={NSLocalizedDescription='+reason+'}"'
        if result=='Failed':outcome['first_blocked_operation']={'stage':p.SAVE_STAGE,'reason':reason,
            'operation':{'alert_count':1} if denial else {'max_channel_delta':3}}
        if outcome_override is not None:outcome=outcome_override
        saved={'image':'lifecycle-saved.png','relative_path':'saved/Celluloid-Owned-Host.png','bytes':100,'sha256':'4'*64}
        phases=[{'index':0,'name':'source-retained'},{'index':1,'name':'fade-ready'}]
        if result=='Passed':phases.append({'index':2,'name':'saved-export','details':{'max_channel_delta':0,'limit':2,'sole_asset_count':1}})
        lifecycle={'schema':'Celluloid.PhotosFilterLifecycle.1','source_sha':self.context['source_sha'],
            'context_sha256':base.context_hash,'fixture_sha256':p.FIXTURE,'complete':False,'phases':phases,
            'raw_exports':{} if omit_saved else {'saved':saved},'images':{'lifecycle-source.png':{},
            'lifecycle-expected-save.png':{},'lifecycle-saved.png':{'bytes':100,'sha256':'4'*64}}}
        values.update({'outcome.json':outcome,'lifecycle.json':lifecycle})
        if omit_outcome:base.rows=[row for row in base.rows if row['name']!='outcome.json']
        for row in base.rows:
            row.update(source_sha=self.context['source_sha'],context_sha256=base.context_hash)
            if row['name'] in values:
                data=p.json_bytes(values[row['name']]);row.update(bytes=len(data),sha256=p.sha(data),base64=base64.b64encode(data).decode())
        profile=host_clock_profile(HOST_ONLY);owner,method=transport.CASE
        command=['xcodebuild','-maximum-test-execution-time-allowance',str(profile['test_seconds']),
            '-only-testing:'+owner.replace('.','/')+'/'+method,'test-without-building']
        lines=['BOUNDED_COMMAND_BEGIN '+json.dumps({'utc':'2026-10-06T00:00:00+00:00',
            'label':transport.LABEL,'seconds':profile['process_seconds'],'command':command}),
            "Test Case '-["+owner+' '+method+"]' started."]
        lines += [transport.PREFIX+json.dumps(row) for row in base.rows]
        lines += ["Test Case '-["+owner+' '+method+"]' passed (1.0 seconds).",'** TEST EXECUTE SUCCEEDED **',
            'BOUNDED_COMMAND_END '+json.dumps({'label':transport.LABEL,'exit_code':0,'elapsed_seconds':1})]
        log='\n'.join(lines)+'\n'
        binding={'schema':'Celluloid.OwnedPhotosBoundaryHostArm.1','context_sha256':base.context_hash,
            'source_sha':self.context['source_sha'],'arm':self.arm}
        owner,method=transport.CASE
        end="Test Case '-["+owner+' '+method+"]' passed (1.0 seconds)."
        extra=[]
        if result=='Failed':extra=['MAC_HOST_BLOCKED stage='+p.SAVE_STAGE+' reason='+reason,
            '/owned/MacPhotosHostUITests.swift:800: error: -['+owner+' '+method+'] : '+failure_text]
        log=log.replace(end,p.PREFIX+p.json_bytes(binding).decode()+'\n'+'\n'.join(extra)+'\n'+end)
        if result=='Failed':
            log=log.replace(' passed (1.0 seconds).',' failed (1.0 seconds).').replace('"exit_code": 0','"exit_code": 65')
            log=log.replace('** TEST EXECUTE SUCCEEDED **','Executed 1 test, with 1 failure (0 unexpected) in 1.0 (1.0) seconds\nTest session results, code coverage, and logs:\n /Users/runner/temp/MacPhotosHost.xcresult\nFailing tests:\n MacPhotosHostUITests.'+method+'()\n** TEST EXECUTE FAILED **')
        else:
            log=log.replace('** TEST EXECUTE SUCCEEDED **','Executed 1 test, with 0 failures (0 unexpected) in 1.0 (1.0) seconds\nTest session results, code coverage, and logs:\n /Users/runner/temp/MacPhotosHost.xcresult\n** TEST EXECUTE SUCCEEDED **')
        summary={'result':result,'totalTestCount':1,'passedTests':int(result=='Passed'),'failedTests':int(result=='Failed'),
            'skippedTests':0,'expectedFailures':0,'startTime':1791244800.1,'finishTime':1791244800.9,
            'testFailures':[] if result=='Passed' else [{'targetName':'CelluloidMacUITests','testIdentifierString':'MacPhotosHostUITests/'+method+'()','failureText':failure_text}]}
        summary['devicesAndConfigurations']=[{k:summary[k] for k in ['passedTests','failedTests','skippedTests','expectedFailures']}]
        summary['devicesAndConfigurations'][0]['device']={'platform':'macOS','osVersion':'27.0','osBuildNumber':'26A428','architecture':'arm64'}
        return raw_context,log,summary
    def test_complete_real_host_proofs_bind_arm_for_pass_and_pixel_failure(self):
        for result in ['Passed','Failed']:
            context,log,summary=self.transcript(result)
            actual=p.bound_arm(context,log,summary)
            self.assertEqual(actual[1],self.arm);self.assertEqual(actual[2],self.identity_raw)
    def test_positive_transcript_uses_current_route_and_original_host_clock(self):
        for result in ['Passed','Failed']:
            context,log,summary=self.transcript(result)
            decoded=p.decode(context)
            self.assertEqual(decoded['validation_route'],HOST_ONLY)
            self.assertEqual(decoded['host_clock_profile'],host_clock_profile(HOST_ONLY))
            begin=p.decode(next(line.split(' ',1)[1] for line in log.splitlines() if line.startswith('BOUNDED_COMMAND_BEGIN ')))
            self.assertEqual(begin['seconds'],1020)
            self.assertEqual(begin['command'][begin['command'].index('-maximum-test-execution-time-allowance')+1],'960')
            self.assertEqual(transport.parse(log,decoded,p.sha(context),complete=False)['transport.json'],
                p.json_bytes(transport.expected_transport(decoded,p.sha(context))))
            p.bound_arm(context,log,summary)
    def test_former_framework_diagnostic_is_strictly_rejected_before_container(self):
        line='2026-10-07 02:55:04.344038+0000 CelluloidMacUITests-Runner[82900:189741] [general] *** Assertion failure in -[XCUIApplication commonInitWithApplicationSpecifier:device:], XCUIApplication.m:226'
        for result in ['Passed','Failed']:
            context,log,summary=self.transcript(result)
            start=next(value for value in log.splitlines() if value.startswith('Test Case ') and value.endswith('started.'))
            log=log.replace(start,start+'\nMAC_HOST_STAGE photos-first-use-and-synthetic-import snapshot=initial\n'+line+
                '\nMAC_HOST_STAGE photos-first-use-and-synthetic-import snapshot=imported',1)
            with self.subTest(result=result),mock.patch.object(p.os,'open',side_effect=AssertionError('container must not open')) as opened:
                with self.assertRaises(ValueError):
                    c,a,i=p.bound_arm(context,log,summary)
                    p.read_capture(c,a,i,self.home)
                opened.assert_not_called()
    def test_unknown_timeout_zero_case_wrong_result_and_late_summary_no_reader(self):
        context,log,summary=self.transcript('Failed')
        variants=[(log.replace(' failed (1.0 seconds).',' skipped (1.0 seconds).'),summary),
            (log+'BOUNDED_COMMAND_TIMEOUT synthetic\n',summary),
            (log.replace('"exit_code": 65','"exit_code": 0'),summary),
            (log.replace('/Users/runner/temp/MacPhotosHost.xcresult','/other.xcresult'),summary),
            (log,dict(summary,totalTestCount=0)),(log,dict(summary,finishTime=summary['finishTime']+10)),
            (log,dict(summary,result='Unknown'))]
        for text,report in variants:
            with self.subTest(text=text[-120:],report=report),self.assertRaises(ValueError):p.bound_arm(context,text,report)
    def test_missing_synthetic_unknown_and_permission_outcomes_stop_before_container(self):
        for options in [dict(omit_outcome=True),dict(outcome_override={'synthetic':'outcome.json'}),
                        dict(denial=True),dict(omit_saved=True)]:
            context,log,summary=self.transcript('Failed',**options)
            with self.subTest(options=options),mock.patch.object(p.os,'open',side_effect=AssertionError('container must not open')) as opened:
                with self.assertRaises(ValueError):
                    c,a,i=p.bound_arm(context,log,summary)
                    p.read_capture(c,a,i,self.home)
                opened.assert_not_called()
    def test_success_needs_saved_stage_prefix_and_no_blocked_operation(self):
        base={'source_sha':'a'*40,'host_entry_contract':'Celluloid.PhotosHostEntry.3','last_stage':p.SAVE_STAGE,
            'complete_host_e2e':False,'save_reopen_cancel_revert':'PhotosFilterLifecycle.1 incomplete'}
        variants=[dict(base,last_stage='host-entry-prerequisite-passed'),dict(base,complete_host_e2e=True),
            dict(base,first_blocked_operation=None),dict(base,first_blocked_operation={'reason':'denied'}),
            {k:v for k,v in base.items() if k!='last_stage'}]
        for outcome in variants:
            args=self.transcript('Passed',outcome_override=outcome)
            with self.subTest(outcome=outcome),self.assertRaises(ValueError):p.bound_arm(*args)
        with self.assertRaises(ValueError):p.bound_arm(*self.transcript('Passed',omit_saved=True))
    def test_pixel_failure_rejects_missing_duplicate_unknown_raw_and_summary_failures(self):
        context,log,summary=self.transcript('Failed')
        blocked='MAC_HOST_BLOCKED stage='+p.SAVE_STAGE+' reason='+p.PIXEL_REASON
        error=next(line for line in log.splitlines() if ': error: -[' in line)
        variants=[(log.replace(blocked+'\n',''),summary),
            (log.replace(blocked,blocked+'\n'+blocked),summary),
            (log.replace(blocked,blocked+'\nMAC_HOST_BLOCKED stage=other reason=permission denied'),summary),
            (log.replace(error+'\n',''),summary),
            (log,dict(summary,testFailures=[dict(summary['testFailures'][0],failureText='permission denied')]))]
        for text,report in variants:
            with self.subTest(text=text[-100:]),self.assertRaises(ValueError):p.bound_arm(context,text,report)
    def test_pending_receipt_postwrite_failures_leave_no_admissible_final_file(self):
        # Source-tied portable publication model; not Swift execution. The source
        # assertions below bind the model's order to the actual fixed-name path.
        swift=(ROOT/'Platforms/macOSExtension/MacPhotoBoundaryProbe.swift').read_text()
        publish=swift.split('        func publishReceipt(',1)[1].split('        func write(',1)[0]
        self.assertLess(publish.index('try write("capture.pending.json"'),publish.index('try check()'))
        self.assertLess(publish.index('try check()'),publish.index('renameatx_np('))
        self.assertIn('UInt32(RENAME_EXCL)',publish)
        self.assertNotIn('try check()',publish.split('renameatx_np(',1)[1])
        self.assertIn('try folder.publishReceipt(receipt, check: check)',swift)
        data=p.json_bytes(self.row)
        for failure in ['postwrite-fstat','postwrite-budget','final-budget','publish']:
            (self.folder/'capture.json').unlink(missing_ok=True)
            (self.folder/'capture.pending.json').unlink(missing_ok=True)
            events=[]
            def step(name):
                events.append(name)
                if name==failure:raise OSError('injected '+name)
            with self.assertRaises(OSError):
                (self.folder/'capture.pending.json').write_bytes(data);step('postwrite-fstat')
                step('postwrite-budget');step('final-budget');step('publish')
                (self.folder/'capture.pending.json').rename(self.folder/'capture.json')
            self.assertEqual((self.folder/'capture.pending.json').read_bytes(),data)
            self.assertFalse((self.folder/'capture.json').exists())
            with self.assertRaises(FileNotFoundError):self.read()
        # Once exclusive native publication succeeds it is terminal; no later
        # budget/metadata action can retroactively mark this completed record bad.
        (self.folder/'capture.pending.json').rename(self.folder/'capture.json')
        self.assertEqual(self.read()['capture.json'],data)

    def test_arm_duplicate_and_outside_case_reject(self):
        context,log,summary=self.transcript()
        line=next(x for x in log.splitlines() if x.startswith(p.PREFIX))
        for changed in [log+line+'\n',line+'\n'+log,log.replace(line,line+'\n'+line)]:
            with self.assertRaises(ValueError):p.bound_arm(context,changed,summary)

class BoundaryComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import mac_host_lifecycle_pixels as pixels
        from test_mac_host_lifecycle_pixels import encode
        cls.original=(ROOT/'Platforms/MacExtensionTests/Fixtures/lifecycle-source.png').read_bytes()
        cls.base=pixels.decode(cls.original)
        rgba=bytearray(cls.base['rgba']);rgba[2]=252 if rgba[2]==255 else 3
        cls.changed=encode(width=1200,height=800,pixels=bytes(rgba))
        cls.changed_raster=pixels.decode(cls.changed)
    def setUp(self):
        original=self.original;original_meta={'bytes':len(original),'sha256':p.sha(original),'rgba_sha256':self.base['rgba_sha256']}
        jpeg=b'\xff\xd8\xffsynthetic admission test only'
        intended_meta=dict(original_meta,bytes=len(jpeg),sha256=p.sha(jpeg))
        changed_meta={'bytes':len(self.changed),'sha256':p.sha(self.changed),'rgba_sha256':self.changed_raster['rgba_sha256']}
        self.old={'lifecycle-source.png':original,'lifecycle-expected-save.png':original,'lifecycle-saved.png':self.changed}
        self.capture={'input.bytes':original,'intended.jpg':jpeg,'capture.json':p.json_bytes({'input_sha256':p.sha(original),'intended_jpeg_sha256':p.sha(jpeg)})}
        zero={'allowed_max_channel_delta':2,'max_channel_delta':0,'changed_pixels':0}
        three={'allowed_max_channel_delta':2,'max_channel_delta':3,'changed_pixels':1}
        self.row={'schema':'Celluloid.OwnedPhotosBoundaryComparison.1','acceptance':False,'complete_host_e2e':False,
            'photos_internal_storage_observed':False,'performance_acceptance':False,'input':original_meta,'intended':intended_meta,
            'saved':changed_meta,'fixture':original_meta,'historical_reference':original_meta,'input_reference':original_meta,
            'intended_jpeg_sha256':p.sha(jpeg),'intended_vs_input_reference':zero,
            'saved_vs_intended':three,'saved_vs_historical_fixture_reference':three}
        self.outputs={'intended-decoded.png':original,'input-reference.png':original,'boundary-comparison.json':p.json_bytes(self.row)}
    def test_independent_png_replay_preserves_failed_old_gate(self):
        result=p.admit_comparison(self.capture,self.outputs,self.old,None)
        self.assertFalse(result['historical_gate_passed']);self.assertFalse(result['acceptance'])
        self.assertEqual(result['saved_vs_intended'],3);self.assertFalse(result['writer_or_photos_acceptance_from_capture'])
    def test_missing_node_oversize_tolerance_or_metric_forgery_reject(self):
        for key,value in [('allowed_max_channel_delta',3),('max_channel_delta',2),('changed_pixels',0)]:
            row=copy.deepcopy(self.row);row['saved_vs_intended'][key]=value
            outputs=dict(self.outputs,**{'boundary-comparison.json':p.json_bytes(row)})
            with self.subTest(key=key),self.assertRaises(ValueError):p.admit_comparison(self.capture,outputs,self.old,None)
        outputs=dict(self.outputs);outputs.pop('input-reference.png')
        with self.assertRaises(ValueError):p.admit_comparison(self.capture,outputs,self.old,None)
        outputs=dict(self.outputs,**{'input-reference.png':b'x'*32769})
        with self.assertRaises(ValueError):p.admit_comparison(self.capture,outputs,self.old,None)

class BoundarySourceTests(unittest.TestCase):
    def test_probe_is_absent_without_both_compile_flags_and_writer_critical_span_is_unchanged(self):
        helper=(ROOT/'Platforms/macOSExtension/MacPhotoBoundaryProbe.swift').read_text()
        self.assertTrue(helper.startswith('#if DEBUG && CELLULOID_OWNED_PHOTOS_BOUNDARY_PROBE\n'))
        self.assertTrue(helper.endswith('#endif\n'))
        controller=(ROOT/'Platforms/macOSExtension/MacPhotoEditingController.swift').read_text()
        capture=controller.index('boundaryArm?.captureIntended')
        self.assertLess(controller.index('let jpeg = try await'),capture)
        self.assertLess(capture,controller.index('writer.start(jpeg: jpeg)'))
        span=controller[controller.index('            guard pendingWrite ==='):controller.index('\n        })',controller.index('            guard pendingWrite ==='))]
        self.assertEqual(span,'''            guard pendingWrite === prepared.writer, prepared.writer.claimForDelivery() else {
                prepared.writer.cancel(); pendingWrite = nil; completionHandler(nil); return
            }
            pendingWrite = nil
            completionHandler(prepared.output)
            prepared.writer.completeDelivery()''')
        self.assertIn('recipeObservation = session.$adjustment.dropFirst()',helper)
        self.assertIn('defer { armed = nil; receipt = ""; recipeObservation = nil }',helper)
        self.assertIn('used = true',helper)
        catch=helper[helper.index('            } catch {'):helper.index('        private static func probeHash')]
        self.assertNotIn('session.report(',catch);self.assertNotIn('throw ',catch);self.assertNotIn('completionHandler(',catch)
    def test_original_saved_gate_executes_before_boundary_only_return(self):
        source=(ROOT/'Platforms/UITests/MacPhotosHostUITests.swift').read_text()
        self.assertLess(source.index('guard savedDelta <= 2'),source.index('if context["boundary_probe"] != nil { return }'))
        self.assertNotIn('lifecycleComplete = true',source[source.index('try armOwnedBoundary'):source.index('stage = "lifecycle-reopen-fade"')])
    def test_default_and_release_build_settings_do_not_enable_probe(self):
        source=(ROOT/'Scripts/generate_native_project.py').read_text()
        self.assertIn("if key=='CelluloidMacPhotosExtension' and name=='Debug':",source)
        self.assertNotIn("CELLULOID_MAC_PHOTOS_BOUNDARY_CONDITION='CELLULOID",source)
        info=plistlib.loads((ROOT/'Platforms/macOSExtension/Info.plist').read_bytes())
        self.assertNotIn('CelluloidOwnedPhotosBoundaryLease',info)
    def test_receipt_uses_live_appkit_value_without_input_interception(self):
        source=(ROOT/'Platforms/macOSExtension/MacPhotoBoundaryProbe.swift').read_text()
        self.assertIn('static let armReceiptMarker = "CELLULOID_OWNED_PHOTOS_BOUNDARY_ARM_V1"',source)
        view=source.split('struct MacPhotoBoundaryReceiptAccessibility: NSViewRepresentable',1)[1]
        for text in ['view.probe = probe','view.probe = nil','view.setAccessibilityRole(.staticText)',
            'view.setAccessibilityIdentifier("photos-extension.boundary-arm")',
            'view.setAccessibilityLabel(MacPhotoBoundaryProbe.armReceiptMarker)',
            'weak var probe: MacPhotoBoundaryProbe?', 'override func hitTest(_ point: NSPoint) -> NSView? { nil }',
            'override var acceptsFirstResponder: Bool { false }',
            'override func accessibilityValue() -> Any? { currentValue }',
            'guard window != nil, !isHiddenOrHasHiddenAncestor, let probe, !probe.receipt.isEmpty else { return nil }',
            'return probe.receipt']:
            self.assertIn(text,view)
        self.assertNotIn('Text(probe.receipt)',source)
        current=view.split('    private var currentValue: String? {',1)[1]
        self.assertNotIn('lastNotifiedValue',current)
        # Live-value semantics: replacing or clearing the receipt is visible
        # without updateNSView, and detached/hidden/dismantled views expose none.
        state={'receipt':'first'}
        def value(probe,window=True,hidden=False):
            return probe['receipt'] if window and not hidden and probe and probe['receipt'] else None
        self.assertEqual(value(state),'first');state['receipt']='second';self.assertEqual(value(state),'second')
        state['receipt']='';self.assertIsNone(value(state))
        state['receipt']='second'
        self.assertIsNone(value(state,window=False));self.assertIsNone(value(state,hidden=True));self.assertIsNone(value(None))

    def test_value_consumer_failure_causes_and_bounded_owned_observation(self):
        # Portable source-tied consumer/diagnostic model, never an AppKit run.
        swift=(ROOT/'Platforms/UITests/MacPhotosHostUITests.swift').read_text()
        body=swift.split('    @MainActor private func armOwnedBoundary(',1)[1].split('    @MainActor private func importFixture(',1)[0]
        self.assertEqual(body.count('let observedValue = leaf.value'),1)
        self.assertIn('let observedLabel = leaf.label',body)
        self.assertIn('guard let raw = observedValue as? String',body)
        for cause in ['marker','type','empty','oversize','parse','dictionary','schema','lease','identity_sha256','generation']:
            self.assertIn('"'+cause+'"',body)
        self.assertIn('raw.utf8.prefix(4096)',body);self.assertIn('raw.utf8.prefix(1024)',body)
        self.assertIn('data.count <= 12_000',body);self.assertIn('"observation_incomplete": true',body)
        for forbidden in ['while ', 'waitForExistence', 'debugDescription', 'let raw = leaf.label']:
            self.assertNotIn(forbidden,body)
        marker='CELLULOID_OWNED_PHOTOS_BOUNDARY_ARM_V1'
        lease=dict(schema='Celluloid.OwnedPhotosBoundaryLease.1',source_sha='a'*40,source_tree='b'*40,
            run_id='123',run_attempt='1',fixture_sha256=p.FIXTURE,nonce='c'*64,raw_cap='131072')
        original=dict(schema='Celluloid.OwnedPhotosBoundaryArm.1',lease=lease,identity_sha256='d'*64,generation='GENERATION')
        def observe(label,value,cause,checks):
            result=dict(failure=cause,count=1,checks=checks,label_bytes=len(label.encode()),
                label_content=label.encode()[:128].decode(errors='replace'),value_type=type(value).__name__)
            if isinstance(value,str):
                raw=value.encode();result.update(value_bytes=len(raw),value_content=raw[:4096].decode(errors='replace'),value_truncated=len(raw)>4096)
                if len(json.dumps(result).encode())>12000:result.update(value_content=raw[:1024].decode(errors='replace'),value_truncated=len(raw)>1024)
            if len(json.dumps(result).encode())>12000:return dict(failure=cause,observation_incomplete=True)
            return result
        def consume(label,value):
            checks={}
            def bad(cause):return observe(label,value,cause,checks)
            if label!=marker:return bad('marker')
            if value is None:return bad('missing')
            if not isinstance(value,str):return bad('type')
            if not value:return bad('empty')
            if len(value.encode())>4096:return bad('oversize')
            try:arm=json.loads(value)
            except ValueError:return bad('parse')
            if not isinstance(arm,dict):return bad('dictionary')
            observed=arm.get('lease');typed=isinstance(observed,dict) and all(isinstance(k,str) and isinstance(v,str) for k,v in observed.items())
            checks.update(schema=arm.get('schema')==original['schema'],lease_type=typed,
                lease_keys=typed and set(observed)==set(lease),lease=typed and observed==lease,
                identity_sha256=arm.get('identity_sha256')==original['identity_sha256'],generation=arm.get('generation')==original['generation'])
            checks.update({'lease_'+key:typed and observed.get(key)==val for key,val in lease.items()})
            for key in ['schema','lease','identity_sha256','generation']:
                if not checks[key]:return bad(key)
            return arm
        raw=json.dumps(original);self.assertEqual(consume(marker,raw),original)
        for value,cause in [(None,'missing'),(True,'type'),(1,'type'),({},'type'),('','empty'),('x'*4097,'oversize'),
            (' ','parse'),('{','parse'),('[]','dictionary'),('null','dictionary'),('"text"','dictionary')]:
            result=consume(marker,value);self.assertEqual(result['failure'],cause)
            self.assertLessEqual(len(json.dumps(result).encode()),12000)
        self.assertEqual(consume(raw,raw)['failure'],'marker') # JSON in label never admits value.
        for key,value in [('schema','wrong'),('lease',dict(lease,nonce='e'*64)),('identity_sha256','0'*64),('generation','stale')]:
            result=consume(marker,json.dumps(dict(original,**{key:value})));self.assertEqual(result['failure'],key)
        result=consume(marker,json.dumps(dict(original,lease=dict(lease,unknown='x'))))
        self.assertEqual(result['failure'],'lease');self.assertFalse(result['checks']['lease_keys'])
        result=consume(marker,'\0'*4096);self.assertEqual(result['failure'],'parse')
        self.assertTrue(result['value_truncated']);self.assertLessEqual(len(json.dumps(result).encode()),12000)
        result=consume(marker,'界'*2000);self.assertEqual(result['failure'],'oversize')
        self.assertEqual(result['value_bytes'],6000);self.assertLessEqual(len(json.dumps(result).encode()),12000)

    def test_reference_uses_actual_input_and_retains_all_three_differentials(self):
        source=(ROOT/'Scripts/compare_owned_photos_boundary.swift').read_text()
        self.assertIn('try expectedFade(input)',source)
        for value in ['try metrics(input, fixture)','try metrics(intended, reference)','try metrics(saved, intended)',
                      'try metrics(saved, historical)','"allowed_max_channel_delta": 2']:
            self.assertIn(value,source)
        self.assertNotIn('import Photos',source);self.assertNotIn('MacPhotoRenderer',source)

if __name__=='__main__':unittest.main()
