import copy, hashlib, json, os, pathlib, runpy, subprocess, sys, tempfile, time, unittest
from unittest.mock import patch
from tv_two_source_cohort import (BASE, BASE_TREE, SOURCE, ONLY_TEST, RAW_CASE, require_probe, verify_files, capture_proof, validate_execution)
ROOT=pathlib.Path(__file__).resolve().parents[1]

class TVTwoSourceTests(unittest.TestCase):
    def write_clock(self, temp, start=None):
        from tv_two_source_cohort import CLOCK_PROFILE
        value={**CLOCK_PROFILE,'source_sha':'a'*40,'started_monotonic':time.monotonic() if start is None else start,'started_unix':time.time()}
        (temp/'tv-two-source-clock.json').write_text(json.dumps(value))
        return value
    def test_nested_ancestor_alias_uses_canonical_fixture_root(self):
        with tempfile.TemporaryDirectory() as folder:
            outer=pathlib.Path(folder).resolve(strict=True)
            actual=outer/'private/var/folders/owned/T/fixture';actual.mkdir(parents=True)
            (outer/'var').symlink_to(outer/'private/var',target_is_directory=True)
            supplied=outer/'var/folders/owned/T/fixture';root=supplied.resolve(strict=True)
            p=root/'a';p.write_bytes(b'one');p.chmod(0o644)
            manifest={'base_commit':BASE,'base_tree':BASE_TREE,'files':[{'path':'a','mode':'100644','bytes':3,'sha256':hashlib.sha256(b'one').hexdigest()}]}
            self.assertNotEqual(root,supplied)
            with self.assertRaisesRegex(ValueError,'Symbolic source path'):verify_files(supplied,manifest,['a',SOURCE])
            verify_files(root,manifest,['a',SOURCE])
    def test_canonical_fixture_root_still_rejects_internal_file_and_directory_symlinks(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder).resolve(strict=True);real=root/'real';real.mkdir()
            (real/'a').write_bytes(b'one');(real/'a').chmod(0o644)
            (root/'file-alias').symlink_to(real/'a');(root/'directory-alias').symlink_to(real,target_is_directory=True)
            for name in ['file-alias','directory-alias/a']:
                manifest={'base_commit':BASE,'base_tree':BASE_TREE,'files':[{'path':name,'mode':'100644','bytes':3,'sha256':hashlib.sha256(b'one').hexdigest()}]}
                with self.subTest(name=name),self.assertRaisesRegex(ValueError,'Symbolic source path'):verify_files(root,manifest,[name,SOURCE])
    def test_source_receipt_final_nul_reports_exact_901_before_and_after(self):
        import tv_two_source_cohort as cohort
        manifest=json.loads((ROOT/SOURCE).read_text());paths=sorted([r['path'] for r in manifest['files']]+[SOURCE])
        self.assertEqual(len(paths),901)
        # Exercise the real full reviewed source bytes; only Git identity is synthetic.
        outputs={('rev-parse','HEAD'):'a'*40+'\n',('rev-list','--parents','-n','1','HEAD'):'a'*40+' '+BASE+'\n',
                 ('status','--porcelain','--untracked-files=all'):'',('ls-files','-z'):'\0'.join(paths)+'\0',('rev-parse','HEAD^{tree}'):'b'*40+'\n'}
        def fake_git(args,**kwargs):return outputs[tuple(args[1:])]
        with tempfile.TemporaryDirectory() as folder:
            temp=pathlib.Path(folder).resolve(strict=True);self.write_clock(temp);clock_bytes=(temp/'tv-two-source-clock.json').read_bytes()
            env={'RUNNER_TEMP':str(temp),'GITHUB_SHA':'a'*40,'GITHUB_WORKFLOW_SHA':'a'*40,'GITHUB_REPOSITORY':'100mango/Celluloid',
                 'GITHUB_EVENT_NAME':'push','GITHUB_REF':'refs/heads/'+cohort.BRANCH,
                 'GITHUB_WORKFLOW_REF':'100mango/Celluloid/'+cohort.WORKFLOW+'@refs/heads/'+cohort.BRANCH}
            with patch.dict(os.environ,env),patch.object(cohort.subprocess,'check_output',side_effect=fake_git):
                before=cohort.source_receipt('before');after=cohort.source_receipt('after')
            self.assertEqual(before['tracked_files'],901);self.assertEqual(after['tracked_files'],901)
            self.assertEqual(before['fingerprint'],after['fingerprint']);self.assertEqual(clock_bytes,(temp/'tv-two-source-clock.json').read_bytes())
    def test_first_step_clock_runs_before_checkout_and_has_explicit_job_margin(self):
        from tv_two_source_cohort import CLOCK_PROFILE
        from test_native_workflow_syntax import run_blocks
        source=(ROOT/'.github/workflows/tv-two-source-observation.yml').read_text()
        self.assertLess(source.index('Start fixed execution clock before checkout'),source.index('uses: actions/checkout@'))
        body=next(run_blocks(source))[1];python='\n'.join(body.splitlines()[1:-1])
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'RUNNER_TEMP':folder,'GITHUB_SHA':'a'*40}):
            exec(compile(python,'inline-first-step-clock','exec'),{})
            value=json.loads(pathlib.Path(folder,'tv-two-source-clock.json').read_text())
        for key,value_expected in CLOCK_PROFILE.items():self.assertEqual(value[key],value_expected)
        self.assertEqual(value['work_budget_seconds']+value['reserved_tail_seconds']+value['startup_teardown_margin_seconds'],1800)
        self.assertIn('before-collect',source);self.assertIn('before-upload',source)
        self.assertIn("steps.upload_admission.outcome == 'success'",source)
        self.assertIn('--seconds 75 --label tv-two-source-collect',source)
    def test_clock_charges_checkout_and_checks_and_rejects_invalid_profiles(self):
        from tv_two_source_cohort import clock_deadlines,budget_admission
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'GITHUB_SHA':'a'*40}):
            temp=pathlib.Path(folder);original=self.write_clock(temp,start=1000)
            self.assertEqual(clock_deadlines(temp,1100),(2200,2560))
            with self.assertRaisesRegex(ValueError,'Insufficient'):budget_admission(temp,'before-build',now=1800)
            report=json.loads((temp/'tv-two-source-budget.json').read_text());self.assertEqual(report['events'][0]['execution_remaining_seconds'],760)
            self.assertFalse(report['events'][0]['admitted'])
            for key,value in [('source_sha','c'*40),('work_budget_seconds',1440),('execution_budget_seconds',1800),('started_monotonic',float('nan')),('started_unix',False)]:
                changed={**original,key:value};(temp/'tv-two-source-clock.json').write_text(json.dumps(changed))
                with self.subTest(key=key),self.assertRaises(ValueError):clock_deadlines(temp,1100)
    def test_final_tail_admission_limits_cannot_be_extended(self):
        from tv_two_source_cohort import budget_admission,TAIL_PHASES
        for phase in ['after','before-accept','before-collect','before-upload']:
            for remaining,accepted in [(TAIL_PHASES[phase],True),(TAIL_PHASES[phase]-0.001,False)]:
                with self.subTest(phase=phase,remaining=remaining),tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'GITHUB_SHA':'a'*40}):
                    temp=pathlib.Path(folder);self.write_clock(temp,start=1000)
                    if accepted:self.assertTrue(budget_admission(temp,phase,now=2560-remaining)['admitted'])
                    else:
                        with self.assertRaisesRegex(ValueError,'Insufficient'):budget_admission(temp,phase,now=2560-remaining)
    def test_upload_admission_binds_existing_packet_and_preserves_cap(self):
        import tv_two_source_cohort as cohort
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'GITHUB_SHA':'a'*40}):
            temp=pathlib.Path(folder);self.write_clock(temp);packet=temp/'celluloid-bounded-evidence';packet.mkdir()
            proof=b'{}';(packet/'proof.json').write_bytes(proof)
            m={'source_sha':'a'*40,'files':[{'name':'proof.json','bytes':2,'sha256':hashlib.sha256(proof).hexdigest()}]}
            (packet/'manifest.json').write_text(json.dumps(m));receipt=cohort.upload_admission(temp)
            self.assertTrue(receipt['budget']['admitted']);m=json.loads((packet/'manifest.json').read_text())
            self.assertEqual({r['name'] for r in m['files']},{'proof.json','tv-two-source-upload-admission.json'})
            self.assertLessEqual(sum(p.stat().st_size for p in packet.iterdir()),2750000)
            for r in m['files']:self.assertEqual(hashlib.sha256((packet/r['name']).read_bytes()).hexdigest(),r['sha256'])
            with self.assertRaisesRegex(ValueError,'Repeated'):cohort.upload_admission(temp)

    def test_upload_gate_rechecks_after_packet_verification_consumes_tail(self):
        import tv_two_source_cohort as cohort
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'GITHUB_SHA':'a'*40}):
            temp=pathlib.Path(folder).resolve(strict=True);self.write_clock(temp,start=1000)
            packet=temp/'celluloid-bounded-evidence';packet.mkdir();proof=b'{}'
            (packet/'proof.json').write_bytes(proof)
            manifest={'source_sha':'a'*40,'files':[{'name':'proof.json','bytes':2,'sha256':hashlib.sha256(proof).hexdigest()}]}
            original=json.dumps(manifest);(packet/'manifest.json').write_text(original)
            observed=[2484.0] # Deadline2560: entry has76s; hash verification costs17s.
            original_digest=cohort.digest
            def verify_with_elapsed_time(path):
                value=original_digest(path)
                if path.name=='proof.json':observed[0]+=17
                return value
            with patch.object(cohort.time,'monotonic',side_effect=lambda:observed[0]),patch.object(cohort,'digest',side_effect=verify_with_elapsed_time):
                with self.assertRaisesRegex(ValueError,'Insufficient fixed job budget for before-upload'):
                    cohort.upload_admission(temp)
            budget=json.loads((temp/'tv-two-source-budget.json').read_text())['events'][-1]
            self.assertEqual(budget['execution_remaining_seconds'],59);self.assertFalse(budget['admitted'])
            self.assertFalse((packet/'tv-two-source-upload-admission.json').exists())
            self.assertEqual((packet/'manifest.json').read_text(),original)
    def fixture(self):
        summary={'result':'Passed','totalTestCount':1,'passedTests':1,'failedTests':0,'skippedTests':0,'expectedFailures':0,'testFailures':[],
            'devicesAndConfigurations':[{'passedTests':1,'failedTests':0,'skippedTests':0,'expectedFailures':0,'device':{'deviceId':'owned','platform':'tvOS Simulator','architecture':'arm64','osVersion':'27.0','osBuildNumber':'24J360'}}]}
        evidence={'udid':'owned','only_testing':ONLY_TEST,'test_exit_code':0,
            'cleanup':[{'action':'shutdown','exit_code':0},{'action':'delete','exit_code':0}],
            'product_before':{'executable_sha256':'a'*64},'product_after':{'executable_sha256':'a'*64}}
        timing={'timed_out':False,'return_code':0,'elapsed_seconds':400}
        text="Test Case '%s' started.\nTV_NATIVE_KEYBOARD_ASCII actual system keyboard committed TV from two ordinary key events\nTV_NATIVE_COMPOSITION_EXPECTED " % RAW_CASE
        text+=json.dumps({'count':2,'keyboardExercised':True,'bubbleText':'TV'})+"\nTest Case '%s' passed (100 seconds).\n** TEST EXECUTE SUCCEEDED **\n" % RAW_CASE
        oracle='TV_NATIVE_COMPOSITION_ORACLE count=2 sourceSamples=[200, 200] maximumChannelDifference=0 layerChangedSamples=[8, 7] keyboardExercised=1 readbackSHA256='+'a'*64
        return summary,text,evidence,timing,oracle
    def test_exact_single_case_accepts(self):
        self.assertEqual(validate_execution(*self.fixture())['bubbleText'],'TV')
    def test_old_matrix_cannot_count_as_single(self):
        a=list(self.fixture());a[0]['totalTestCount']=14;a[0]['passedTests']=10;a[0]['failedTests']=4
        with self.assertRaises(ValueError):validate_execution(*a)
    def test_other_case_or_duplicate_case_rejected(self):
        for extra in ["Test Case '-[CelluloidTVTests.NativeTVTests testNativeTVExecutableAndScene]' passed (1 seconds).", "Test Case '%s' passed (1 seconds)."%RAW_CASE]:
            a=list(self.fixture());a[1]+=extra
            with self.assertRaises(ValueError):validate_execution(*a)
    def test_compile_only_or_default_hello_never_qualifies(self):
        for old,new in [('"keyboardExercised": true','"keyboardExercised": false'),('"bubbleText": "TV"','"bubbleText": "Hello"'),('TV_NATIVE_KEYBOARD_ASCII','COMPILE_ONLY')]:
            a=list(self.fixture());a[1]=a[1].replace(old,new)
            with self.assertRaises(ValueError):validate_execution(*a)
    def test_wrong_runtime_or_device_rejected(self):
        for key,value in [('deviceId','other'),('osVersion','28.0'),('osBuildNumber','other'),('architecture','x86_64')]:
            a=list(self.fixture());a[0]['devicesAndConfigurations'][0]['device'][key]=value
            with self.assertRaises(ValueError):validate_execution(*a)
    def test_unfinalized_or_timeout_or_unclean_rejected(self):
        for kind in ['summary','timeout','nan','cleanup','product','error']:
            a=list(self.fixture())
            if kind=='summary':a[0]['result']='Failed'
            elif kind=='timeout':a[3]['timed_out']=True
            elif kind=='nan':a[3]['elapsed_seconds']=float('nan')
            elif kind=='cleanup':a[2]['cleanup'][1]['exit_code']=1
            elif kind=='product':a[2]['product_after']={}
            elif kind=='error':a[1]+='error: unexpected failure'
            with self.assertRaises(ValueError):validate_execution(*a)
    def test_wrong_oracle_or_extra_oracle_rejected(self):
        for old,new in [('count=2','count=3'),('maximumChannelDifference=0','maximumChannelDifference=3'),('keyboardExercised=1','keyboardExercised=0')]:
            a=list(self.fixture());a[4]=a[4].replace(old,new)
            with self.assertRaises(ValueError):validate_execution(*a)
        a=list(self.fixture());a[4]+='\n'+a[4]
        with self.assertRaises(ValueError):validate_execution(*a)
    def test_probe_is_current_compile_not_runtime_claim(self):
        require_probe({'compiled':True,'exit_code':0,'runtime_keyboard_coverage':False})
        for bad in [{'compiled':False,'exit_code':0,'runtime_keyboard_coverage':False},{'compiled':True,'exit_code':0,'runtime_keyboard_coverage':True}]:
            with self.assertRaises(ValueError):require_probe(bad)
    def test_complete_source_membership_and_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder).resolve(strict=True);p=root/'a';p.write_bytes(b'one');p.chmod(0o644)
            manifest={'base_commit':BASE,'base_tree':BASE_TREE,'files':[{'path':'a','mode':'100644','bytes':3,'sha256':hashlib.sha256(b'one').hexdigest()}]}
            verify_files(root,manifest,['a',SOURCE])
            with self.assertRaises(ValueError):verify_files(root,manifest,['a',SOURCE,'extra'])
            p.write_bytes(b'two')
            with self.assertRaises(ValueError):verify_files(root,manifest,['a',SOURCE])
    def test_actual_proof_retained_with_identity_and_bounds(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder);source=root/'source';source.mkdir();target=root/'target'
            ids=['AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA','BBBBBBBB-BBBB-BBBB-BBBB-BBBBBBBBBBBB']
            (source/'kept-recipe.json').write_text(json.dumps({'recipe':{'sources':[{'id':i} for i in ids]}}))
            for name in ['photos-output.json','photos-output.png']+[i+'.image' for i in ids]:(source/name).write_bytes(b'x')
            rows=capture_proof(source,target);self.assertEqual(len(rows),5)
            self.assertEqual(sorted(p.name for p in target.iterdir()),sorted(r['name'] for r in rows))
            with self.assertRaises(ValueError):capture_proof(source,target)
    def test_workflow_shell_syntax_and_scope(self):
        from test_native_workflow_syntax import run_blocks
        source=(ROOT/'.github/workflows/tv-two-source-observation.yml').read_text()
        for line,block in run_blocks(source):
            result=subprocess.run(['bash','-n'],input=block,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,(line,result.stderr))
        self.assertNotIn('matrix:',source);self.assertNotIn('workflow_dispatch',source);self.assertNotIn('CODE_SIGNING_ALLOWED=YES',source)
        self.assertIn('timeout-minutes: 30',source);self.assertIn('retention-days: 1',source)
        self.assertIn('run_native_tv.py --two-source-only',source)
    def test_existing_default_and_real_keyboard_case_are_preserved(self):
        runner=(ROOT/'Scripts/run_native_tv.py').read_text();case=(ROOT/'Platforms/TVUITests/NativeTVUITests.swift').read_text()
        self.assertIn("*(['-only-testing:'+ONLY_TEST] if focused else [])",runner)
        self.assertIn("if not focused:run(['swift'",runner)
        self.assertIn('revealArtwork("say1", initiallyDown: true',case)
        self.assertIn('app.typeText("T"); app.typeText("V")',case)
        self.assertIn('try select(app.buttons["tv.undo"],in:app)',case)
        self.assertIn('keyboardExercised',case)
    def test_focused_runner_uses_exact_existing_case_and_default_is_unchanged(self):
        import native_process, tv_two_source_cohort
        for focused in [False,True]:
            with self.subTest(focused=focused), tempfile.TemporaryDirectory() as folder:
                temp=pathlib.Path(folder);calls=[]
                (temp/'tv-text-input-probe.json').write_text(json.dumps({'compiled':True,'exit_code':0,'runtime_keyboard_coverage':False}))
                self.write_clock(temp)
                def fake_run(args,**kwargs):
                    args=list(map(str,args));calls.append(args);output=''
                    if args[1:4]==['simctl','list','runtimes']:output=json.dumps({'runtimes':[{'name':'tvOS','identifier':'tvos','version':'27.0','buildversion':'24J360','isAvailable':True}]})
                    elif args[1:4]==['simctl','list','devicetypes']:output=json.dumps({'devicetypes':[{'name':'Apple TV 4K','identifier':'tv'}]})
                    elif args[1:3]==['simctl','create']:output='owned'
                    elif args[1:3]==['simctl','launch']:output='Mango.Celluloid: 123'
                    elif args[0]=='ps':output='123 CelluloidTV'
                    elif args[1:3]==['simctl','get_app_container']:output=str(temp/'container')
                    return subprocess.CompletedProcess(args,0,output,'')
                argv=['run_native_tv.py']+(['--two-source-only'] if focused else [])
                with patch.dict(os.environ,{'RUNNER_TEMP':folder,'GITHUB_SHA':'a'*40}), patch.object(sys,'argv',argv), patch.object(native_process,'run',fake_run), patch.object(native_process,'optional_diagnostic',return_value={'succeeded':True}), patch.object(tv_two_source_cohort,'capture_product',return_value={'hash':'same'}), patch.object(tv_two_source_cohort,'capture_proof',return_value=[]), patch('time.sleep'):
                    runpy.run_path(str(ROOT/'Scripts/run_native_tv.py'),run_name='__main__')
                tests=[a for a in calls if a[0]=='xcodebuild'];self.assertEqual(len(tests),1)
                self.assertEqual([a for a in tests[0] if a.startswith('-only-testing:')],['-only-testing:'+ONLY_TEST] if focused else [])
                self.assertEqual(sum(any('verify_tv_filter_output.swift' in v for v in a) for a in calls),0 if focused else 1)
                oracle=next(a for a in calls if any('verify_tv_composition.swift' in v for v in a))
                self.assertEqual(oracle[-1]=='two-source-only',focused)
                report=json.loads((temp/'tv-runtime-evidence.json').read_text());self.assertEqual(report['cleanup'],[{'action':'shutdown','exit_code':0},{'action':'delete','exit_code':0}])
    def test_existing_collector_reserves_focus_receipts_without_duplicate_entries(self):
        with tempfile.TemporaryDirectory() as folder:
            temp=pathlib.Path(folder)
            names=['tv-two-source-before.json','tv-two-source-after.json','tv-two-source-clock.json','tv-two-source-budget.json','tv-two-source-acceptance.json','CelluloidTV.xcresult.summary.json','tv-runtime-evidence.json','tv-runtime-tests.log.timing.json','tv-text-input-probe.json','native-icon-provenance-runtime.json']
            for name in names:(temp/name).write_text('{}')
            (temp/'tv-two-source-proof').mkdir();(temp/'tv-two-source-proof'/'photos-output.png').write_bytes(b'synthetic collector fixture, not a real image')
            env={**os.environ,'RUNNER_TEMP':folder,'GITHUB_SHA':'a'*40,'CELLULOID_EVIDENCE_PLATFORM':'tv','CELLULOID_TV_TWO_SOURCE':'1','PYTHONDONTWRITEBYTECODE':'1'}
            result=subprocess.run([sys.executable,str(ROOT/'Scripts/collect_native_evidence.py')],env=env,capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            m=json.loads((temp/'celluloid-bounded-evidence/manifest.json').read_text());retained=[r['name'] for r in m['files']]
            self.assertEqual(len(retained),len(set(retained)));self.assertTrue(set(names).issubset(retained))
            self.assertEqual(m['limits']['total_bytes'],2750000);self.assertEqual(m['limits']['retention_days'],1)
            self.assertIn('historical hosted/single-photo coverage is not inherited',m['scope'])
    def test_focused_oracle_keeps_legacy_matrix_default(self):
        oracle=(ROOT/'Scripts/verify_tv_composition.swift').read_text()
        self.assertIn('expectedRows.count==(focused ? 1:3)',oracle)
        self.assertIn('maximum<=2 && verified.allSatisfy {$0>5}',oracle)
        self.assertIn('expected["keyboardExercised"] as? Bool==true',oracle)

if __name__=='__main__':unittest.main()
