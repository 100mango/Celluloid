import ast,copy,hashlib,inspect,json,os,pathlib,runpy,subprocess,sys,tempfile,time,unittest,zlib
from unittest.mock import patch
import tv_remaining_cohort as c
ROOT=pathlib.Path(__file__).resolve().parents[1]

class RemainingTVTests(unittest.TestCase):
    def clock(self,temp,start=None):
        value={**c.CLOCK_PROFILE,'source_sha':'a'*40,'started_monotonic':time.monotonic() if start is None else start,'started_unix':time.time()}
        (temp/'tv-remaining-clock.json').write_text(json.dumps(value));return value
    def fixture(self,profile):
        spec=c.PROFILES[profile];n=len(spec['tests'])
        counts={'passedTests':n,'failedTests':0,'skippedTests':0,'expectedFailures':0}
        summary={**counts,'result':'Passed','totalTestCount':n,'testFailures':[],'devicesAndConfigurations':[{**counts,'device':{'deviceId':'owned','platform':'tvOS Simulator','architecture':'arm64','osVersion':'27.0','osBuildNumber':'24J360'}}]}
        evidence={'udid':'owned','selected_tests':spec['tests'],'profile':profile,'test_exit_code':0,
            'cleanup':[{'action':'shutdown','exit_code':0},{'action':'delete','exit_code':0}],
            'product_before':{'sha':'same'},'product_after':{'sha':'same'}}
        text=''
        for name in sorted(spec['tests']):
            raw='-[CelluloidTVUITests.NativeTVUITests '+name.rsplit('/',1)[-1]+']'
            text+="Test Case '"+raw+"' started.\nTest Case '"+raw+"' passed (1 seconds).\n"
        text+='** TEST EXECUTE SUCCEEDED **\n';oracle=''
        if profile=='rich':
            for count in [4,3]:
                text+='TV_NATIVE_KEYBOARD_ASCII actual system keyboard committed TV from two ordinary key events\nTV_NATIVE_KEYBOARD_UNICODE actual system keyboard committed full multilingual text\n'
                text+='TV_NATIVE_COMPOSITION_EXPECTED '+json.dumps({'count':count,'bubbleText':'TV 世界','keyboardExercised':True},ensure_ascii=False)+'\n'
                oracle+='TV_NATIVE_COMPOSITION_ORACLE count='+str(count)+' sourceSamples=['+', '.join(['20']*count)+'] maximumChannelDifference=0 layerChangedSamples=[8, 9] keyboardExercised=1 readbackSHA256='+'a'*64+'\n'
        else:
            for large,trait in [(False,'tv.instruction.ordinary'),(True,'tv.instruction.accessibility5')]:
                mode=str(large).lower()
                text+='TV_PUBLIC_TRAIT_STRESS requestedLargest='+mode+' actualTraitIdentifier='+trait+' frame=observed systemPropagationVerified=false\n'
                text+='TV_PHOTO_LOCALIZED_REACHABILITY requestedLarge='+mode+' identifier=actual selected=已选 1\n'
                text+='TV_ZH_HANS_REOPEN requestedLarge='+mode+' instructionHeight=observed localized filter persisted\n'
                text+='TV_ZH_HANS_PRIVACY_COMPLETE '+json.dumps({'requestedLarge':large,'bodyObserved':True,'dismissed':True,'restoredFilter':'褪色','systemSettingsChanged':False,'systemPropagationVerified':False})+'\n'
        return [summary,text,evidence,{'timed_out':False,'return_code':0,'elapsed_seconds':400},oracle,profile]
    def test_exact_rich_and_chinese_profiles_accept(self):
        for p in c.PROFILES:self.assertEqual(c.validate_execution(*self.fixture(p))['profile'],p)
    def test_two_source_or_hosted_execution_is_not_admitted(self):
        a=self.fixture('rich');a[1]+="Test Case '-[CelluloidTVUITests.NativeTVUITests testRemoteCollageTwoSources]' started.\n"
        with self.assertRaises(ValueError):c.validate_execution(*a)
        a=self.fixture('chinese');a[2]['selected_tests']=['CelluloidTVTests/NativeTVTests/testNativeTVExecutableAndScene']
        with self.assertRaises(ValueError):c.validate_execution(*a)
    def test_unicode_cannot_be_downgraded_to_ascii_or_probe(self):
        for old,new in [('TV 世界','TV'),('"keyboardExercised": true','"keyboardExercised": false'),('TV_NATIVE_KEYBOARD_UNICODE','ONLY_COMPILE_PROBE')]:
            a=self.fixture('rich');a[1]=a[1].replace(old,new)
            with self.assertRaises(ValueError):c.validate_execution(*a)
    def test_oracle_count_samples_pixel_bound_and_layers_are_strict(self):
        for old,new in [('count=4','count=2'),('maximumChannelDifference=0','maximumChannelDifference=3'),('layerChangedSamples=[8, 9]','layerChangedSamples=[0, 9]'),('20, 20, 20]','1, 20, 20]')]:
            a=self.fixture('rich');a[4]=a[4].replace(old,new)
            with self.assertRaises(ValueError):c.validate_execution(*a)
    def test_missing_real_privacy_or_os_setting_misclaim_rejected(self):
        for old,new in [('TV_ZH_HANS_PRIVACY_COMPLETE','NO_PRIVACY'),('"dismissed": true','"dismissed": false'),('"systemSettingsChanged": false','"systemSettingsChanged": true'),('systemPropagationVerified=false','systemPropagationVerified=true')]:
            a=self.fixture('chinese');a[1]=a[1].replace(old,new)
            with self.assertRaises(ValueError):c.validate_execution(*a)
    def test_partial_profile_cannot_pass_full_profile(self):
        a=self.fixture('rich');a[0]['passedTests']=1;a[0]['totalTestCount']=1
        with self.assertRaises(ValueError):c.validate_execution(*a)
        a=self.fixture('chinese');a[1]=a[1].replace('TV_ZH_HANS_REOPEN requestedLarge=true','MISSING_LARGEST')
        with self.assertRaises(ValueError):c.validate_execution(*a)
    def test_wrong_runtime_failure_timeout_or_cleanup_rejected(self):
        for kind in ['device','timeout','failed','cleanup','product','raw']:
            a=self.fixture('rich')
            if kind=='device':a[0]['devicesAndConfigurations'][0]['device']['deviceId']='other'
            elif kind=='timeout':a[3]['timed_out']=True
            elif kind=='failed':a[0]['failedTests']=1
            elif kind=='cleanup':a[2]['cleanup'][1]['exit_code']=1
            elif kind=='product':a[2]['product_after']={}
            else:a[1]+='error: actual failure'
            with self.assertRaises(ValueError):c.validate_execution(*a)
    def test_serial_workflow_has_only_two_fixed_jobs_and_fresh_clocks(self):
        from test_native_workflow_syntax import run_blocks
        s=(ROOT/'.github/workflows/tv-remaining-observation.yml').read_text()
        self.assertEqual(s.count('runs-on: xcode-27'),2);self.assertEqual(s.count('timeout-minutes: 30'),2)
        self.assertIn('CELLULOID_TV_REMAINING_PROFILE: rich',s);self.assertIn('CELLULOID_TV_REMAINING_PROFILE: chinese',s)
        self.assertNotIn('matrix:',s);self.assertIn('needs: tv-rich',s);self.assertIn('always() && !cancelled()',s)
        self.assertNotIn('--two-source-only',s);self.assertIn('--remaining-rich',s);self.assertIn('--remaining-chinese',s)
        self.assertEqual(s.count('Start fixed execution clock before checkout'),2)
        for line,block in run_blocks(s):
            result=subprocess.run(['bash','-n'],input=block,text=True,capture_output=True);self.assertEqual(result.returncode,0,(line,result.stderr))
    def test_clock_gate_and_upload_algorithm_match_proved_v3(self):
        import tv_two_source_cohort as old
        for name in ['require','digest','write','clock_deadlines','budget_admission','upload_admission','require_probe','capture_product']:
            expected=inspect.getsource(getattr(old,name)).replace('TVTwoSource','TVRemaining').replace('tv-two-source','tv-remaining')
            self.assertEqual(inspect.getsource(getattr(c,name)),expected,name)
        self.assertEqual(c.TAIL_PHASES,old.TAIL_PHASES)
    def test_clock_rejects_consumed_tail_after_hashing(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'GITHUB_SHA':'a'*40}):
            temp=pathlib.Path(folder).resolve(strict=True);self.clock(temp,1000);packet=temp/'celluloid-bounded-evidence';packet.mkdir()
            (packet/'p').write_bytes(b'x');(packet/'manifest.json').write_text(json.dumps({'source_sha':'a'*40,'files':[{'name':'p','bytes':1,'sha256':hashlib.sha256(b'x').hexdigest()}]}))
            now=[2484.];original=c.digest
            def charged(path):
                result=original(path)
                if path.name=='p':now[0]+=17
                return result
            with patch.object(c,'digest',side_effect=charged),patch.object(c.time,'monotonic',side_effect=lambda:now[0]):
                with self.assertRaises(ValueError):c.upload_admission(temp)
            self.assertFalse((packet/'tv-remaining-upload-admission.json').exists())
    def test_canonical_ancestor_alias_and_internal_symlink_boundary(self):
        with tempfile.TemporaryDirectory() as folder:
            outer=pathlib.Path(folder).resolve(strict=True);real=outer/'private/var/folders/owned/T';real.mkdir(parents=True);(outer/'var').symlink_to(outer/'private/var',target_is_directory=True)
            root=(outer/'var/folders/owned/T').resolve(strict=True);(root/'a').write_bytes(b'x');(root/'a').chmod(0o644)
            m={'base_commit':c.BASE,'base_tree':c.BASE_TREE,'files':[{'path':'a','mode':'100644','bytes':1,'sha256':hashlib.sha256(b'x').hexdigest()}]}
            c.verify_files(root,m,['a',c.SOURCE]);(root/'alias').symlink_to(root/'a');m['files'][0]['path']='alias'
            with self.assertRaises(ValueError):c.verify_files(root,m,['alias',c.SOURCE])
    def test_actual_source_receipts_905_paths_keep_final_nul_out(self):
        m=json.loads((ROOT/c.SOURCE).read_text());paths=sorted([r['path'] for r in m['files']]+[c.SOURCE]);self.assertEqual(len(paths),905)
        outputs={('rev-parse','HEAD'):'a'*40+'\n',('rev-list','--parents','-n','1','HEAD'):'a'*40+' '+c.BASE+'\n',('status','--porcelain','--untracked-files=all'):'',('ls-files','-z'):'\0'.join(paths)+'\0',('rev-parse','HEAD^{tree}'):'b'*40+'\n'}
        for profile in c.PROFILES:
            with tempfile.TemporaryDirectory() as folder:
                temp=pathlib.Path(folder).resolve(strict=True);self.clock(temp)
                env={'RUNNER_TEMP':str(temp),'GITHUB_SHA':'a'*40,'GITHUB_WORKFLOW_SHA':'a'*40,'GITHUB_REPOSITORY':'100mango/Celluloid','GITHUB_EVENT_NAME':'push','GITHUB_REF':'refs/heads/'+c.BRANCH,'GITHUB_WORKFLOW_REF':'100mango/Celluloid/'+c.WORKFLOW+'@refs/heads/'+c.BRANCH,'GITHUB_JOB':c.PROFILES[profile]['job'],'CELLULOID_TV_REMAINING_PROFILE':profile}
                with patch.dict(os.environ,env),patch.object(c.subprocess,'check_output',side_effect=lambda args,**kw:outputs[tuple(args[1:])]):
                    before=c.source_receipt('before');after=c.source_receipt('after')
                self.assertEqual(before['tracked_files'],905);self.assertEqual(after['tracked_files'],905);self.assertEqual(before['profile'],profile)
    def test_collector_preserves_complete_logs_and_fixed_caps(self):
        for profile in c.PROFILES:
            with tempfile.TemporaryDirectory() as folder:
                temp=pathlib.Path(folder);raw=b'full original log\n'*10000;(temp/'tv-runtime-tests.log').write_bytes(raw)
                env={**os.environ,'RUNNER_TEMP':folder,'GITHUB_SHA':'a'*40,'CELLULOID_EVIDENCE_PLATFORM':'tv','CELLULOID_TV_REMAINING_PROFILE':profile,'PYTHONDONTWRITEBYTECODE':'1'};env.pop('CELLULOID_TV_TWO_SOURCE',None)
                result=subprocess.run([sys.executable,str(ROOT/'Scripts/collect_native_evidence.py')],env=env,text=True,capture_output=True,timeout=10);self.assertEqual(result.returncode,0,result.stderr)
                out=temp/'celluloid-bounded-evidence';m=json.loads((out/'manifest.json').read_text());self.assertEqual(m['limits']['total_bytes'],2750000)
                self.assertEqual(zlib.decompress((out/'tv-remaining-tv-runtime-tests.log.zlib').read_bytes()),raw)
                self.assertEqual(m['fixed_remaining_cohort_allocation']['total_maximum_bytes'],5500000)
    def test_runtime_selectors_are_fixed_and_never_include_two_source(self):
        import native_process
        for profile in c.PROFILES:
            for exit_code in [0,65,"timeout"]:
                with self.subTest(profile=profile,exit_code=exit_code),tempfile.TemporaryDirectory() as folder:
                    temp=pathlib.Path(folder);self.clock(temp);calls=[]
                    (temp/'tv-text-input-probe.json').write_text(json.dumps({'compiled':True,'exit_code':0,'runtime_keyboard_coverage':False}))
                    def fake(args,**kwargs):
                        args=list(map(str,args));calls.append(args);out='';code=0
                        if args[1:4]==['simctl','list','runtimes']:out=json.dumps({'runtimes':[{'name':'tvOS','identifier':'tvos','version':'27.0','buildversion':'24J360','isAvailable':True}]})
                        elif args[1:4]==['simctl','list','devicetypes']:out=json.dumps({'devicetypes':[{'name':'Apple TV 4K','identifier':'tv'}]})
                        elif args[1:3]==['simctl','create']:out='owned'
                        elif args[1:3]==['simctl','launch']:out='Mango.Celluloid: 123'
                        elif args[0]=='ps':out='123 CelluloidTV'
                        elif args[1:3]==['simctl','get_app_container']:out=str(temp/'container')
                        elif args[0]=='xcodebuild':
                            if exit_code=='timeout':raise TimeoutError('synthetic bounded XCTest timeout; no native tool called')
                            code=exit_code
                        return subprocess.CompletedProcess(args,code,out,'')
                    groups=[{'count':3,'files':[]}]+([{'count':4,'files':[]}] if exit_code==0 else [])
                    env={'RUNNER_TEMP':folder,'GITHUB_SHA':'a'*40,'CELLULOID_TV_REMAINING_PROFILE':profile}
                    with patch.dict(os.environ,env),patch.object(sys,'argv',['run_native_tv.py','--remaining-'+profile]),patch.object(native_process,'run',fake),patch.object(native_process,'optional_diagnostic',return_value={'succeeded':True}),patch.object(c,'capture_product',return_value={'sha':'same'}),patch.object(c,'capture_remaining_proofs',return_value={'groups':groups,'errors':[]}),patch('time.sleep'):
                        if exit_code:
                            with self.assertRaises((RuntimeError,TimeoutError)):runpy.run_path(str(ROOT/'Scripts/run_native_tv.py'),run_name='__main__')
                        else:runpy.run_path(str(ROOT/'Scripts/run_native_tv.py'),run_name='__main__')
                    command=next(a for a in calls if a[0]=='xcodebuild')
                    self.assertEqual([a.removeprefix('-only-testing:') for a in command if a.startswith('-only-testing:')],c.PROFILES[profile]['tests'])
                    self.assertFalse(any('testRemoteCollageTwoSources' in a for a in command))
                    oracles=[a for a in calls if any('verify_tv_composition.swift' in v for v in a)]
                    self.assertEqual(len(oracles),1 if profile=='rich' and exit_code==0 else 0)
                    self.assertFalse(any(any('verify_tv_filter_output.swift' in v for v in a) for a in calls))
                    evidence=json.loads((temp/'tv-runtime-evidence.json').read_text())
                    if exit_code=='timeout':self.assertNotIn('test_exit_code',evidence);self.assertIn('timeout',evidence['error'])
                    else:self.assertEqual(evidence['test_exit_code'],exit_code)
                    self.assertEqual(evidence['cleanup'],[{'action':'shutdown','exit_code':0},{'action':'delete','exit_code':0}])
                    if profile=='rich':self.assertEqual(evidence['proof_groups'],groups)
    def test_capture_retains_one_completed_group_without_claiming_both(self):
        with tempfile.TemporaryDirectory() as folder:
            temp=pathlib.Path(folder);source=temp/'source';source.mkdir();ids=['00000000-0000-0000-0000-'+str(i).zfill(12) for i in range(3)]
            group=source/'3';group.mkdir();(group/'kept-recipe.json').write_text(json.dumps({'recipe':{'sources':[{'id':i} for i in ids]}}))
            for name in ['photos-output.json','photos-output.png']+[i+'.image' for i in ids]:(group/name).write_bytes(b'x')
            actual=c.capture_remaining_proofs(source,temp/'kept')
            self.assertEqual([g['count'] for g in actual['groups']],[3]);self.assertEqual(actual['errors'][0]['count'],4)
            self.assertEqual(len(list((temp/'kept/3').iterdir())),6)
    def test_independent_oracle_default_and_old_two_source_scope_are_kept(self):
        s=(ROOT/'Scripts/verify_tv_composition.swift').read_text()
        self.assertIn('expectedRows.count==(focused ? 1:remainingRich ? 2:3)',s)
        self.assertIn('maximum<=2 && verified.allSatisfy {$0>5}',s)
        self.assertIn('remainingRich { try require([3,4].contains(count)',s)
        self.assertIn('expected["bubbleText"] as? String=="TV 世界"',s)

    def test_partial_output_fixture_has_startup_margin_without_native_timeout_change(self):
        source=(ROOT/'Scripts/test_native_process.py').read_text()
        self.assertIn("timeout=.5,echo=False,log_name='timeout.log'",source)
        self.assertIn("self.assertIn('partial'",source)
        self.assertIn('time.sleep(10)',source)
        self.assertIn('own process-group', (ROOT/'Scripts/native_process.py').read_text())
        self.assertIn('timeout=900,check=False', (ROOT/'Scripts/run_native_tv.py').read_text())
    def test_existing_rich_UI_keeps_real_unicode_and_current_safety(self):
        s=(ROOT/'Platforms/TVUITests/NativeTVUITests.swift').read_text()
        self.assertIn('app.typeText("T"); app.typeText("V")',s);self.assertIn('+"TV 世界"',s)
        self.assertIn('revealArtwork("say1", initiallyDown: true',s);self.assertIn('revealArtwork("54", initiallyDown: true',s)
        self.assertIn('TV_ZH_HANS_PRIVACY_COMPLETE',s);self.assertIn('systemSettingsChanged": false',s)
        self.assertIn('return false',s);self.assertNotIn('return true // Report',s)

if __name__=='__main__':unittest.main()
