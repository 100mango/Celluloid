"""Both generic consumer routes must bind actual finalized runtime/model identity."""
from pathlib import Path
import copy,hashlib,json,tempfile,unittest,os,subprocess
import test_platform_rendering_contract as fixtures
from native_fixture_handoff import layer_from_log,LAYER_FILE
from verify_required_interoperability import verify,required,CONSUMER
from consumer_runtime_binding import MODEL_SCALES,validate_raw_execution

class ResultSessionMetadataTests(unittest.TestCase):
    # Structural fixture from run37360765993's retained 2x log. Payload lines
    # are deliberately omitted; this is parser coverage, not native proof.
    PATH='/Users/runner/work/_temp/CelluloidEarlyUIKit2x.xcresult'
    INITIAL='Writing result bundle at path:\n\t'+PATH+'\n\n'
    FINAL='Test session results, code coverage, and logs:\n\t'+PATH+'\n\n'
    CASE='-[CelluloidTests.MacPhotosManufacturedAdjustmentTests testManufacturedMacArchiveThroughOriginalUIKitReaderAndCompositor]'
    TERMINAL='** TEST EXECUTE SUCCEEDED **\n'
    def transcript(self):
        log=self.INITIAL
        for name in ['Selected tests','CelluloidTests.xctest','MacPhotosManufacturedAdjustmentTests']:
            log+=f"Test Suite '{name}' started at 2026-10-05 19:14:34.648.\n"
        log+=f"Test Case '{self.CASE}' started.\nTest Case '{self.CASE}' passed (29.245 seconds).\n"
        for name in ['MacPhotosManufacturedAdjustmentTests','CelluloidTests.xctest','Selected tests']:
            log+=f"Test Suite '{name}' passed at 2026-10-05 19:15:03.898.\n\t Executed 1 test, with 0 failures (0 unexpected) in 29.245 (29.250) seconds\n"
        return log+self.FINAL+self.TERMINAL
    def summary(self):return {'result':'Passed','totalTestCount':1,'passedTests':1,'failedTests':0,'skippedTests':0,'testFailures':[]}
    def test_exact_paired_announcements_preserve_complete_accounting(self):
        report=validate_raw_execution(self.transcript(),self.summary())
        self.assertTrue(report['aggregate_execution_passed'])
        self.assertEqual(report['case_counts'],{'passed':1,'failed':0,'skipped':0})
        self.assertEqual(report['result_session_path_observation'],self.PATH)
    def test_final_only_and_header_free_formats_remain_supported(self):
        final_only=self.transcript().replace(self.INITIAL,'',1)
        self.assertEqual(validate_raw_execution(final_only,self.summary())['result_session_path_observation'],self.PATH)
        self.assertIsNone(validate_raw_execution(final_only.replace(self.FINAL,'',1),self.summary())['result_session_path_observation'])
    def test_missing_duplicate_or_stray_announcements_reject(self):
        log=self.transcript()
        changes={
            'missing initial header':log.replace('Writing result bundle at path:\n','',1),
            'missing final header':log.replace('Test session results, code coverage, and logs:\n','',1),
            'missing initial path':log.replace('\t'+self.PATH+'\n','',1),
            'missing final path':log.replace(self.FINAL,'Test session results, code coverage, and logs:\n'),
            'initial announcement only':log.replace(self.FINAL,''),
            'duplicate initial header':'Writing result bundle at path:\n'+log,
            'duplicate final header':log.replace(self.FINAL,'Test session results, code coverage, and logs:\n'+self.FINAL),
            'duplicate initial pair':self.INITIAL+log,
            'duplicate final pair':log.replace(self.FINAL,self.FINAL+self.FINAL),
            'stray same path before':self.PATH+'\n'+log,
            'stray other path before':'/repo/Other.xcresult\n'+log,
            'stray same path after':log+self.PATH+'\n',
            'stray other path after':log+'/repo/Other.xcresult\n',
        }
        for label,changed in changes.items():
            with self.subTest(mutation=label),self.assertRaises(ValueError):validate_raw_execution(changed,self.summary())
    def test_mismatched_or_malformed_paths_and_headers_reject(self):
        for replacement in ['/repo/Other.xcresult','relative.xcresult','/repo/no-result.txt','/'+'a'*1025+'.xcresult','/repo/invalid\x00.xcresult']:
            for block in [self.INITIAL,self.FINAL]:
                changed=self.transcript().replace(block,block.replace(self.PATH,replacement),1)
                with self.subTest(path=replacement,block=block),self.assertRaises(ValueError):validate_raw_execution(changed,self.summary())
        for header in ['Writing result bundle at path:','Test session results, code coverage, and logs:']:
            for replacement in [header[:-1],header.lower(),header+' extra']:
                with self.subTest(header=replacement),self.assertRaises(ValueError):validate_raw_execution(self.transcript().replace(header,replacement),self.summary())
        for path in ['/'+'a'*1025+'.xcresult','/repo/invalid\x00.xcresult']:
            with self.subTest(stray=path),self.assertRaises(ValueError):validate_raw_execution(self.transcript()+path+'\n',self.summary())
    def test_original_path_bound_remains_exact(self):
        maximum='/'+'a'*1024+'.xcresult'
        self.assertEqual(validate_raw_execution(self.transcript().replace(self.PATH,maximum),self.summary())['result_session_path_observation'],maximum)
    def test_metadata_must_bracket_all_suites_cases_and_totals_before_terminal(self):
        log=self.transcript();without_initial=log.replace(self.INITIAL,'',1);without_final=log.replace(self.FINAL,'',1)
        suite_start="Test Suite 'Selected tests' started at 2026-10-05 19:14:34.648.\n"
        case_end=f"Test Case '{self.CASE}' passed (29.245 seconds).\n"
        total='\t Executed 1 test, with 0 failures (0 unexpected) in 29.245 (29.250) seconds\n'
        changes={
            'initial after suite start':without_initial.replace(suite_start,suite_start+self.INITIAL,1),
            'initial after case end':without_initial.replace(case_end,case_end+self.INITIAL,1),
            'initial after final':without_initial.replace(self.FINAL,self.FINAL+self.INITIAL),
            'initial path before header':log.replace(self.INITIAL,'\t'+self.PATH+'\nWriting result bundle at path:\n'),
            'unpaired intervening content':log.replace(self.INITIAL,'Writing result bundle at path:\nunrelated output\n\t'+self.PATH+'\n'),
            'final before suite ends':without_final.replace(case_end,case_end+self.FINAL),
            'final before last total':without_final.replace(total+self.TERMINAL,self.FINAL+total+self.TERMINAL),
            'final path before header':log.replace(self.FINAL,'\t'+self.PATH+'\nTest session results, code coverage, and logs:\n'),
            'final after terminal':without_final+self.FINAL,
        }
        for label,changed in changes.items():
            self.assertNotEqual(changed,log,label)
            with self.subTest(mutation=label),self.assertRaises(ValueError):validate_raw_execution(changed,self.summary())
    def test_pair_cannot_mask_case_suite_total_terminal_or_error_failure(self):
        log=self.transcript()
        changes=[log.replace(f"Test Case '{self.CASE}' started.\n",''),
            log.replace('passed (29.245 seconds).','failed (29.245 seconds).'),
            log.replace("Test Suite 'Selected tests' passed","Test Suite 'Selected tests' failed"),
            log.replace('Executed 1 test','Executed 2 tests'),
            log.replace(self.TERMINAL,'** TEST EXECUTE FAILED **\n'),
            log+self.TERMINAL,log+'error: unexplained build/runtime failure\n',
            log+'Failing tests:\nUnknown.testUnknown()\n']
        for changed in changes:
            with self.subTest(log=changed),self.assertRaises(ValueError):validate_raw_execution(changed,self.summary())

class GenericRuntimeTests(unittest.TestCase):
    SOURCE='a'*40
    def exercise(self,scope,model='iPhone SE (3rd generation)',change=None,missing=None,log_change=None):
        helper=fixtures.PlatformContractTests();profile=str(MODEL_SCALES[model])+'x'
        row,log,summary,timing,fixture=helper.profile(profile)
        if scope=='phone':
            log=log.replace('CelluloidTests.','CelluloidCompanionTests.')
            for module,cases in required(scope).items():
                for case in cases:
                    if case==CONSUMER:continue
                    owner,method=case.split('.');log=log.replace('** TEST EXECUTE SUCCEEDED **\n','')
                    log+=f"Test Case '-[{module}.{owner} {method}]' started.\nTest Case '-[{module}.{owner} {method}]' passed (0.1 seconds).\n"
            log+=f"Executed {sum(map(len,required(scope).values()))-1} tests, with 0 failures (0 unexpected)\n"
            log+='SHIPPING_COMPANION_NAVIGATION actual test entry\nSHIPPING_COMPANION_RETURN actual test return\n** TEST EXECUTE SUCCEEDED **\n'
            count=sum(map(len,required(scope).values()));summary.update(totalTestCount=count,passedTests=count)
            summary['devicesAndConfigurations'][0]['passedTests']=count
        summary['devicesAndConfigurations'][0]['device']['modelName']=model
        expected={'id':row['udid'],'model':model}
        if change:change(summary,expected)
        if log_change:log=log_change(log,summary)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);native=root/'native.log';native.write_text('MAC_LAYER_ADJUSTMENT_FIXTURE '+json.dumps(fixture)+'\n')
            data=layer_from_log(native,self.SOURCE);(root/LAYER_FILE).write_bytes(data)
            (root/'manifest.json').write_text(json.dumps({'source_sha':self.SOURCE,'files':[{'name':LAYER_FILE,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}]}))
            path=root/'consumer.log';path.write_text(log)
            return verify(scope,path,root,self.SOURCE,platform_contract=True,runtime_summary=None if missing=='summary' else summary,expected_device=None if missing=='device' else expected)
    def test_each_later_route_requires_the_real_summary_and_owned_device(self):
        for scope in ['uikit','phone']:
            report=self.exercise(scope);self.assertTrue(all(report['checks'].values()));self.assertEqual(report['runtime_binding']['runtime_build'],'24A434')
            for missing in ['summary','device']:
                with self.subTest(scope=scope,missing=missing),self.assertRaises(ValueError):self.exercise(scope,missing=missing)
    def test_additional_reviewed_models_use_their_actual_scale_profile(self):
        for model,scale in MODEL_SCALES.items():
            report=self.exercise('uikit',model);self.assertEqual(report['runtime_binding']['model'],model);self.assertEqual(report['runtime_binding']['scale'],scale)
    def test_wrong_build_arch_device_profile_or_failed_enclosing_execution_rejects_both_routes(self):
        changes=[lambda s,d:s['devicesAndConfigurations'][0]['device'].update(osBuildNumber='24Z999'),
            lambda s,d:s['devicesAndConfigurations'][0]['device'].update(architecture='x86_64'),
            lambda s,d:s['devicesAndConfigurations'][0]['device'].update(osVersion='27.1'),
            lambda s,d:s['devicesAndConfigurations'][0]['device'].update(deviceId='FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF'),
            lambda s,d:s['devicesAndConfigurations'][0]['device'].update(modelName='iPhone 18 Pro Max'),
            lambda s,d:d.update(model='Unreviewed phone'),lambda s,d:s.update(result='Failed'),
            lambda s,d:s.update(failedTests=1),lambda s,d:s.update(passedTests=True),
            lambda s,d:s.update(startTime=float('nan')),lambda s,d:s.update(finishTime=s['startTime']),
            lambda s,d:s.update(testFailures=[{'failureText':'Unexpected geometry assertion'}]),
            lambda s,d:s['devicesAndConfigurations'].append(copy.deepcopy(s['devicesAndConfigurations'][0]))]
        for scope in ['uikit','phone']:
            for change in changes:
                with self.subTest(scope=scope,change=change),self.assertRaises(ValueError):self.exercise(scope,change=change)
    def test_passed_summary_cannot_hide_failed_raw_case_terminal_or_error(self):
        changes=[lambda log,s:log+"Test Case '-[CelluloidTests.UnrelatedTests testUnrelated]' failed (0.1 seconds).\n",
                 lambda log,s:log+'** TEST EXECUTE FAILED **\n',lambda log,s:log+'error: unrelated build/runtime failure\n',
                 lambda log,s:log+'Failing tests:\n\tUnrelatedTests.testUnrelated()\n',
                 lambda log,s:log+'AssertionFailure: unrelated structural failure\n',
                 lambda log,s:log+" Test Suite 'Selected tests' failed at 2026-10-04 15:00:00.000.\n"]
        for scope in ['uikit','phone']:
            for change in changes:
                with self.subTest(scope=scope,change=change),self.assertRaises(ValueError):self.exercise(scope,log_change=change)
    def test_impossible_or_premature_totals_reject_both_routes(self):
        changes=[lambda log,s:log.replace('Executed 1 test, with 0 failures','Executed 999 tests, with 0 failures'),
            lambda log,s:'Executed 999 tests, with 0 failures (0 unexpected)\n'+log,
            lambda log,s:'Executed 1 test, with 0 failures (0 unexpected)\n'+log]
        for scope in ['uikit','phone']:
            for change in changes:
                with self.subTest(scope=scope,change=change),self.assertRaises(ValueError):self.exercise(scope,log_change=change)
    def test_legitimate_nested_suite_totals_are_preserved(self):
        def nested(log,summary):
            start="Test Suite 'Selected tests' started at 2026-10-04 15:00:00.000.\nTest Suite 'MacPhotosManufacturedAdjustmentTests' started at 2026-10-04 15:00:00.001.\n"
            end="Test Suite 'MacPhotosManufacturedAdjustmentTests' passed at 2026-10-04 15:00:20.000.\nExecuted 1 test, with 0 failures (0 unexpected)\nTest Suite 'Selected tests' passed at 2026-10-04 15:00:20.001.\nExecuted 1 test, with 0 failures (0 unexpected)"
            return start+log.replace('Executed 1 test, with 0 failures (0 unexpected)',end)
        self.assertTrue(self.exercise('uikit',log_change=nested)['renderer_consumer_passed'])
        def premature(log,summary):
            return nested(log,summary).replace("Test Case '-[", "Executed 999 tests, with 0 failures (0 unexpected)\nTest Case '-[",1)
        with self.assertRaises(ValueError):self.exercise('uikit',log_change=premature)

    def test_consistent_unrelated_failure_keeps_consumer_proof_but_aggregate_red(self):
        def unrelated(log,summary):
            summary.update(result='Failed',failedTests=1,totalTestCount=summary['totalTestCount']+1,
                testFailures=[{'targetName':'CelluloidTests','testIdentifierString':'UnrelatedTests/testUnrelated()','failureText':'XCTAssertTrue failed'}])
            summary['devicesAndConfigurations'][0]['failedTests']=1
            extra="Test Case '-[CelluloidTests.UnrelatedTests testUnrelated]' started.\n/repo/Other.swift:1: error: -[CelluloidTests.UnrelatedTests testUnrelated] : XCTAssertTrue failed\nTest Case '-[CelluloidTests.UnrelatedTests testUnrelated]' failed (0.1 seconds).\nExecuted 1 test, with 1 failure (0 unexpected)\nFailing tests:\nUnrelatedTests.testUnrelated()\n** TEST EXECUTE FAILED **"
            return log.replace('** TEST EXECUTE SUCCEEDED **',extra)
        for scope in ['uikit','phone']:
            report=self.exercise(scope,log_change=unrelated)
            self.assertTrue(report['renderer_consumer_passed']);self.assertTrue(all(report['checks'].values()))
            self.assertFalse(report['aggregate_execution_passed']);self.assertEqual(report['runtime_binding']['aggregate_result'],'Failed')
            self.assertEqual(len(report['raw_execution_accounting']['failed_cases']),1)
            self.assertEqual(len(report['raw_execution_accounting']['scoped_errors']),1)
        source=(Path(__file__).resolve().parent/'verify_required_interoperability.py').read_text()
        self.assertIn("or report.get('aggregate_execution_passed') is False",source)

    def test_real_interleaved_session_metadata_preserves_failed_aggregate(self):
        def failed(log,summary):
            summary.update(result='Failed',failedTests=1,totalTestCount=summary['totalTestCount']+1,
                testFailures=[{'targetName':'CelluloidTests','testIdentifierString':'UnrelatedTests/testUnrelated()','failureText':'XCTAssertTrue failed'}])
            summary['devicesAndConfigurations'][0]['failedTests']=1
            extra="Test Case '-[CelluloidTests.UnrelatedTests testUnrelated]' started.\n/repo/Other.swift:1: error: -[CelluloidTests.UnrelatedTests testUnrelated] : XCTAssertTrue failed\nTest Case '-[CelluloidTests.UnrelatedTests testUnrelated]' failed (0.1 seconds).\nExecuted 1 test, with 1 failure (0 unexpected)\nFailing tests:\nTest session results, code coverage, and logs:\nUnrelatedTests.testUnrelated()\n/repo/TestResults-units.xcresult\n** TEST EXECUTE FAILED **"
            return log.replace('** TEST EXECUTE SUCCEEDED **',extra)
        for scope in ['uikit','phone']:
            report=self.exercise(scope,log_change=failed)
            self.assertTrue(report['renderer_consumer_passed']);self.assertFalse(report['aggregate_execution_passed'])
            self.assertEqual(report['raw_execution_accounting']['result_session_path_observation'],'/repo/TestResults-units.xcresult')
            for old,new in [('UnrelatedTests.testUnrelated()','WrongTests.testUnknown()'),('/repo/TestResults-units.xcresult','/repo/no-result.txt'),('Test session results, code coverage, and logs:','Test session results, code coverage, and logs:\nTest session results, code coverage, and logs:'),('/repo/TestResults-units.xcresult','/repo/TestResults-units.xcresult\nerror: unexplained')]:
                with self.subTest(scope=scope,mutation=new),self.assertRaises(ValueError):self.exercise(scope,log_change=lambda log,summary:failed(log,summary).replace(old,new))
            def paired(log,summary):return 'Writing result bundle at path:\n/repo/TestResults-units.xcresult\n\n'+failed(log,summary)
            report=self.exercise(scope,log_change=paired)
            self.assertTrue(report['renderer_consumer_passed']);self.assertFalse(report['aggregate_execution_passed'])
            self.assertEqual(report['raw_execution_accounting']['result_session_path_observation'],'/repo/TestResults-units.xcresult')
            for old,new in [('UnrelatedTests.testUnrelated()','WrongTests.testUnknown()'),('with 1 failure','with 0 failures'),('** TEST EXECUTE FAILED **','** TEST EXECUTE SUCCEEDED **')]:
                with self.subTest(scope=scope,paired_mutation=new),self.assertRaises(ValueError):self.exercise(scope,log_change=lambda log,summary:paired(log,summary).replace(old,new))

    def test_both_consumer_routes_accept_one_exact_paired_result_announcement(self):
        def paired(log,summary):return ResultSessionMetadataTests.INITIAL+log.replace('** TEST EXECUTE SUCCEEDED **',ResultSessionMetadataTests.FINAL+'** TEST EXECUTE SUCCEEDED **')
        for scope in ['uikit','phone']:
            report=self.exercise(scope,log_change=paired)
            self.assertTrue(report['renderer_consumer_passed']);self.assertTrue(report['aggregate_execution_passed'])
            self.assertEqual(report['raw_execution_accounting']['result_session_path_observation'],ResultSessionMetadataTests.PATH)

    def test_standard_unrelated_skipped_totals_and_count_mutations(self):
        def skipped(log,summary,count):
            summary.update(skippedTests=count,totalTestCount=summary['totalTestCount']+count)
            summary['devicesAndConfigurations'][0]['skippedTests']=count
            extra=''
            for n in range(count):extra+=f"Test Case '-[CelluloidTests.OptionalTests testSkipped{n}]' started.\nTest Case '-[CelluloidTests.OptionalTests testSkipped{n}]' skipped (0.1 seconds).\n"
            extra+=f"Executed {count} tests, with {count} test{'s' if count>1 else ''} skipped and 0 failures (0 unexpected)\n** TEST EXECUTE SUCCEEDED **"
            return log.replace('** TEST EXECUTE SUCCEEDED **',extra)
        for scope in ['uikit','phone']:
            for count in [1,2]:
                change=lambda log,summary:skipped(log,summary,count)
                self.assertTrue(self.exercise(scope,log_change=change)['renderer_consumer_passed'])
                with self.assertRaises(ValueError):self.exercise(scope,log_change=lambda log,summary:change(log,summary).replace(f'{count} test'+('s' if count>1 else '')+' skipped','999 tests skipped'))
            with self.assertRaises(ValueError):self.exercise(scope,log_change=lambda log,summary:log.replace("testManufacturedMacArchiveThroughOriginalUIKitReaderAndCompositor]' passed", "testManufacturedMacArchiveThroughOriginalUIKitReaderAndCompositor]' skipped"))

    def test_accepted_runtime_summary_is_mandatory_and_replayed_before_optional_pressure(self):
        import consumer_runtime_binding as runtime
        helper=fixtures.PlatformContractTests();row,log,summary,timing,fixture=helper.profile('2x')
        receipt=fixtures.contract.validate_receipt(helper.receipt('2x'),fixture)
        binding=runtime.validate(summary,receipt,{'id':row['udid'],'model':row['device_type']})
        root=Path(__file__).resolve().parents[1]
        for platform,stem in [('phone','phone-required-tests'),('compact-phone','uikit-required-tests')]:
            for mutation in ['valid','missing','changed','oversized','missing-archive','changed-archive','forged-graph']:
                with self.subTest(platform=platform,mutation=mutation),tempfile.TemporaryDirectory() as folder:
                    temp=Path(folder);packet={'source_sha':self.SOURCE,'checks':{'runtime_and_consumer_passed':True},'platform_contract':receipt,'runtime_binding':binding}
                    (temp/(stem+'.json')).write_text(json.dumps(packet));path=temp/(stem+'.runtime-summary.json')
                    native=temp/'native.log';native.write_text('MAC_LAYER_ADJUSTMENT_FIXTURE '+json.dumps(fixture)+'\n')
                    data=layer_from_log(native,self.SOURCE);directory=temp/'mac-fixture-evidence';directory.mkdir()
                    if mutation!='missing-archive':(directory/LAYER_FILE).write_bytes(data)
                    (directory/'manifest.json').write_text(json.dumps({'source_sha':self.SOURCE,'files':[{'name':LAYER_FILE,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}]}))
                    if mutation=='changed-archive':
                        import base64,plistlib
                        payload=json.loads(data);archive=plistlib.loads(base64.b64decode(payload['fixture']['base64']))
                        transform=next(x for x in archive['$objects'] if isinstance(x,dict) and 'NS.atval.tx' in x);transform['NS.atval.tx']=123.0
                        raw=plistlib.dumps(archive,fmt=plistlib.FMT_BINARY);digest=hashlib.sha256(raw).hexdigest()
                        payload['fixture'].update(base64=base64.b64encode(raw).decode(),sha256=digest)
                        data=json.dumps(payload).encode();(directory/LAYER_FILE).write_bytes(data)
                        (directory/'manifest.json').write_text(json.dumps({'source_sha':self.SOURCE,'files':[{'name':LAYER_FILE,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}]}))
                        packet=copy.deepcopy(packet);packet['platform_contract']['archiveSHA256']=digest
                        packet['platform_contract']['archiveGraphProof']['candidate_raw_sha256']=digest
                        (temp/(stem+'.json')).write_text(json.dumps(packet))
                    if mutation=='forged-graph':
                        packet=copy.deepcopy(packet);packet['platform_contract']['archiveGraphProof']['canonical_graph_sha256']='f'*64
                        (temp/(stem+'.json')).write_text(json.dumps(packet))
                    if mutation!='missing':path.write_text(json.dumps(summary))
                    if mutation=='changed':
                        bad=copy.deepcopy(summary);bad['devicesAndConfigurations'][0]['device']['osBuildNumber']='24Z999';path.write_text(json.dumps(bad))
                    if mutation=='oversized':path.write_bytes(b' '*5_000_001)
                    (temp/'domain.log').write_text('optional pressure\n'*150_000)
                    result=subprocess.run(['python3',str(root/'Scripts/collect_native_evidence.py')],env=dict(os.environ,RUNNER_TEMP=str(temp),GITHUB_SHA=self.SOURCE,CELLULOID_EVIDENCE_PLATFORM=platform),text=True,capture_output=True,timeout=15)
                    self.assertEqual(result.returncode==0,mutation=='valid',result.stderr)
                    if mutation=='valid':
                        self.assertEqual((temp/'celluloid-bounded-evidence'/path.name).read_bytes(),path.read_bytes())
                        self.assertEqual((temp/'celluloid-bounded-evidence'/'consumer-mac-layer-fixture.json').read_bytes(),data)

    def test_both_routes_replay_complete_archive_graph_with_distinct_raw_hashes(self):
        import base64,plistlib
        from unittest.mock import patch
        helper=fixtures.PlatformContractTests();original=helper.fixture()
        witness=json.loads((Path(__file__).resolve().parent/'fixtures/archive-ordering-witness.json').read_text())
        current=base64.b64decode(witness['base64'])
        for scope in ['uikit','phone']:
            for changed in [False,True]:
                archive=plistlib.loads(current)
                if changed:
                    transform=next(x for x in archive['$objects'] if isinstance(x,dict) and 'NS.atval.tx' in x)
                    transform['NS.atval.tx']=int(transform['NS.atval.tx']) # Same numeric value, wrong archived type.
                raw=plistlib.dumps(archive,fmt=plistlib.FMT_BINARY,sort_keys=False) if changed else current
                fixture=copy.deepcopy(original);fixture.update(base64=base64.b64encode(raw).decode(),sha256=hashlib.sha256(raw).hexdigest())
                with self.subTest(scope=scope,changed=changed),patch.object(fixtures.PlatformContractTests,'fixture',return_value=fixture):
                    if changed:
                        with self.assertRaisesRegex(ValueError,'semantic graph'):self.exercise(scope)
                    else:
                        report=self.exercise(scope);proof=report['platform_contract']['archiveGraphProof']
                        self.assertTrue(report['renderer_consumer_passed']);self.assertFalse(proof['raw_bytes_equal'])
                        self.assertEqual(proof['candidate_raw_sha256'],witness['sha256'])
                        self.assertEqual(proof['control_raw_sha256'],original['sha256'])

    def test_cli_routes_supply_exact_result_bundle_and_owned_identity(self):
        text=(Path(__file__).resolve().parents[1]/'.github/workflows/apple-platforms.yml').read_text()
        self.assertIn('--result-bundle "$RUNNER_TEMP/CelluloidPhoneCompanion.xcresult" --runtime-evidence "$RUNNER_TEMP/phone-runtime-evidence.json"',text)
        self.assertIn('--result-bundle TestResults-units.xcresult --device-id-file /tmp/current-celluloid-simulator --expected-model "$DEVICE_NAME"',text)
if __name__=='__main__':unittest.main()
