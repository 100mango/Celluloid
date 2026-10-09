import ast,copy,hashlib,json,os,re,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import run_ios_install_diagnostic as gate

class AdmissionTests(unittest.TestCase):
    def values(self):
        config=dict(schema=1,mode='install-only',READY=True,sourceReady=True,nativeAuthorization=True,base_sha=gate.BASE_SHA,base_tree=gate.BASE_TREE,maximum_additional_spend_usd=0)
        env=dict(GITHUB_REPOSITORY='100mango/Celluloid',GITHUB_EVENT_NAME='push',GITHUB_REF='refs/heads/'+gate.BRANCH,GITHUB_WORKFLOW_REF='100mango/Celluloid/'+gate.WORKFLOW+'@refs/heads/'+gate.BRANCH,GITHUB_RUN_ATTEMPT='1',GITHUB_RUN_ID='123',GITHUB_SHA='a'*40,GITHUB_WORKFLOW_SHA='a'*40)
        facts=dict(head='a'*40,tree='b'*40,base_tree=gate.BASE_TREE,dirty='',paths=sorted(gate.CONTROL_PATHS),chain=[dict(sha='a'*40,parents=[gate.BASE_SHA],paths=sorted(gate.CONTROL_PATHS))])
        return config,env,facts
    def testExactInstallOnlyAdmissionNeverQualifiesHostOrRelease(self):
        receipt=gate.validate_admission(*self.values());self.assertTrue(receipt['diagnostic_only']);self.assertFalse(receipt['release_qualification']);self.assertEqual(receipt['host_methods_planned'],0)
    def testClosedMissingWrongRouteRetrySpendOrScopeRejects(self):
        changes=[lambda c,e,f:c.update(READY=False),lambda c,e,f:c.update(sourceReady=False),lambda c,e,f:c.update(nativeAuthorization=False),lambda c,e,f:c.update(mode='host'),lambda c,e,f:c.update(base_sha='c'*40),lambda c,e,f:c.update(base_tree='c'*40),lambda c,e,f:c.update(maximum_additional_spend_usd=True),lambda c,e,f:c.update(maximum_additional_spend_usd=1),lambda c,e,f:c.update(extra=True),lambda c,e,f:e.update(GITHUB_REF='refs/heads/cell-ios-photos-host-final'),lambda c,e,f:e.update(GITHUB_EVENT_NAME='workflow_dispatch'),lambda c,e,f:e.update(GITHUB_RUN_ATTEMPT='2'),lambda c,e,f:e.update(GITHUB_WORKFLOW_SHA='c'*40),lambda c,e,f:f.update(dirty='M app'),lambda c,e,f:f['paths'].append('Celluloid/Info.plist'),lambda c,e,f:f['chain'][0]['parents'].append('c'*40),lambda c,e,f:f['chain'][0]['paths'].append('Celluloid/AppDelegate.swift'),lambda c,e,f:f.update(chain=[])]
        for mutate in changes:
            c,e,f=self.values();mutate(c,e,f)
            with self.assertRaises(ValueError):gate.validate_admission(c,e,f)
    def testBoundedConfigurationRejectsDuplicatesSymlinksAndNonfinite(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'config';p.write_text('{"x":1,"x":2}')
            with self.assertRaises(ValueError):gate.strict_json(p)
            p.write_text('{"x":NaN}')
            with self.assertRaises(ValueError):gate.strict_json(p)
            p.write_text('{}');link=Path(d)/'alias';link.symlink_to(p)
            with self.assertRaises(OSError):gate.strict_json(link)
            p.write_text('x'*32769)
            with self.assertRaises(ValueError):gate.strict_json(p)
    def bounded(self,label,command,cap,mutate=None):
        c,e,f=self.values();receipt=gate.validate_admission(c,e,f);receipt['control_fingerprint']='digest';device='12345678-1234-1234-1234-123456789AB0'
        owner=dict(device_id=device,source_sha=e['GITHUB_SHA'],run_id='123',run_attempt='1',created_by_this_job=True,absent_before_create=True,runtime_id='com.apple.CoreSimulator.SimRuntime.iOS-27-0')
        if mutate:mutate(receipt,owner)
        def read(path,*args):return c if path==gate.ROOT/gate.CONFIG else receipt if path==gate.ADMISSION else owner
        with patch.dict(os.environ,e,clear=True),patch.object(gate,'strict_json',side_effect=read),patch.object(gate,'fingerprint',return_value='digest'):
            return gate.bounded_admission(label,command,cap)
    def testExactOwnedInstallCommandOnlyAndOriginalCap(self):
        command=['xcrun','simctl','install','12345678-1234-1234-1234-123456789AB0',str(gate.DERIVED/'Build/Products/Debug-iphonesimulator/Celluloid.app')]
        self.assertEqual(self.bounded('install-owned-app',command,120)['run_id'],'123')
        for argv,cap in [(command,121),(command+['--other'],120),([*command[:3],'OTHER',command[-1]],120),([*command[:-1],'/other.app'],120)]:
            with self.assertRaises(ValueError):self.bounded('install-owned-app',argv,cap)
        for change in [lambda r,o:r.update(run_id='124'),lambda r,o:r.update(control_fingerprint='wrong'),lambda r,o:o.update(created_by_this_job=False),lambda r,o:o.update(absent_before_create=False),lambda r,o:o.update(source_sha='c'*40),lambda r,o:o.update(run_id='124')]:
            with self.assertRaises(ValueError):self.bounded('install-owned-app',command,120,change)
    def testUnknownCommandAndHostExecutionCannotEnterWrapper(self):
        for label,command,cap in [('actual-photos-host',['xcodebuild','test-without-building'],630),('sample',['sample','999','3'],8),('bootstrap',['xcrun','simctl','privacy'],750),('host-memory',['ps','-ax'],5)]:
            with self.assertRaises(ValueError):self.bounded(label,command,cap)

class RouteTests(unittest.TestCase):
    def testOnlyNewBranchOneClosedOrReviewedActiveJobNoOtherMatches(self):
        config=json.loads((gate.ROOT/gate.CONFIG).read_text());flags=[config[k] for k in ['READY','sourceReady','nativeAuthorization']];self.assertTrue(flags==[False]*3 or flags==[True]*3)
        workflow=(gate.ROOT/gate.WORKFLOW).read_text();condition="if: ${{ "+('false && ' if flags==[False]*3 else '')+"github.event_name == 'push' && github.ref == 'refs/heads/"+gate.BRANCH+"' }}";self.assertIn(condition,workflow)
        self.assertEqual(re.findall(r'^  ([a-z][a-z0-9-]*):$',workflow.split('jobs:\n',1)[1],re.M),['install-only']);self.assertIn('timeout-minutes: 45',workflow);self.assertIn('group: celluloid-ios-photos-host-probe',workflow)
        matching=[]
        for p in (gate.ROOT/'.github/workflows').glob('*.yml'):
            if 'branches: ['+gate.BRANCH+']' in p.read_text():matching.append(p.name)
        self.assertEqual(matching,['ios-install-diagnostic.yml'])
        paths=set(re.findall(r'^      - (.+)$',workflow.split('    paths:\n',1)[1].split('permissions:',1)[0],re.M));self.assertEqual(paths,gate.CONTROL_PATHS)
    def testInstallOnlyDriverDoesNotDispatchAnyTestOrBootstrap(self):
        tree=ast.parse((gate.ROOT/'Scripts/run_ios_install_diagnostic.py').read_text());run=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='run')
        labels=[]
        for n in ast.walk(run):
            if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute):
                self.assertNotIn(n.func.attr,['bootstrap','photos','picker'])
                if n.func.attr=='command':labels.append(n.args[0].value)
        self.assertEqual(labels.count('install-owned-app'),1);self.assertNotIn('actual-photos-host',labels);self.assertNotIn('units',labels)
        source=ast.get_source_segment((gate.ROOT/'Scripts/run_ios_install_diagnostic.py').read_text(),run)
        self.assertNotIn("'test-without-building'",source);self.assertIn("'build-for-testing'",source);self.assertIn("'CODE_SIGNING_ALLOWED=NO'",source)
    def testHistoricalPayloadPinsRemainExact(self):
        self.assertEqual(gate.EXPECTED_BINARY,'e8a98ee62ee4df42bfaedc1d1e3b15c284231074237ee3dd1af48648d5439408');self.assertEqual(gate.EXPECTED_BUNDLE,'ac903681326cd5a38786d6942e8dca129302007a95d1373bde2ac4d614537f00')
        self.assertEqual(gate.product_control(gate.ROOT),(424,gate.PRODUCT_CONTROL_SHA256))
    def observation_gate(self):
        obj=object.__new__(gate.InstallDiagnostic);obj.uncertain=False;obj.device='owned';obj.diagnostic_errors=[];obj.source='a'*40;obj.observation=None;obj.install_attempted=True;obj.events=[{'phase':'install-owned-app'}]
        return obj
    def testUncertainLoggerOrMissingSampleBlocksLaterSimulatorCleanup(self):
        rows=[{}, {'schema':'Celluloid.InstallWrapperObservation.1','source_sha':'a'*40,'run_id':'123','run_attempt':'1','prohibit_further_simctl':False,'logger':{'host_pid':12,'uncertain':False,'simulator_stream_settled':False},'sample':{'uncertain':False}}]
        for receipt in rows:
            obj=self.observation_gate()
            with patch.dict(os.environ,{'GITHUB_RUN_ID':'123'}),patch.object(gate,'strict_json',return_value=receipt):obj.finalize_observation()
            self.assertTrue(obj.uncertain)
            with patch('subprocess.call',side_effect=AssertionError('new simulator work')):obj.cleanup()
    def testObservationFailureDoesNotOverwriteActualInstallReceipt(self):
        obj=self.observation_gate();obj.install_result={'returned_exit_code':0,'outcome':'passed'}
        with patch.object(gate,'strict_json',side_effect=PermissionError('retention denied')):obj.finalize_observation()
        self.assertEqual(obj.install_result,{'returned_exit_code':0,'outcome':'passed'});self.assertTrue(obj.uncertain);self.assertEqual(obj.diagnostic_errors,[{'phase':'observation-finalization','error':'PermissionError'}])
    def testMissingPhaseEventAfterDispatchStillFinalizesAndFailsClosed(self):
        obj=self.observation_gate();obj.events=[]
        with patch.object(gate,'strict_json',side_effect=OSError('phase log retention failed')):obj.finalize_observation()
        self.assertTrue(obj.uncertain)
        with patch('subprocess.call',side_effect=AssertionError('new simulator work')):obj.cleanup()
    def settled_observation(self):
        identity={'schema':'Celluloid.InstallObserver.1','source_sha':'a'*40,'run_id':'123','run_attempt':'1','uncertain':False}
        return {'schema':'Celluloid.InstallWrapperObservation.1','source_sha':'a'*40,'run_id':'123','run_attempt':'1','prohibit_further_simctl':False,'logger':dict(identity,kind='device_log',device='owned',host_pid=12,simulator_stream_settled=True),'sample':dict(identity,kind='install_sample')}
    def testPositiveSettledLoggerAndSamplePermitOriginalCleanup(self):
        obj=self.observation_gate();receipt=self.settled_observation()
        with patch.dict(os.environ,{'GITHUB_RUN_ID':'123'}),patch.object(gate,'strict_json',return_value=receipt):obj.finalize_observation()
        self.assertFalse(obj.uncertain)
    def testNestedObserverMissingWrongIdentityOrDeviceCannotAuthorizeCleanup(self):
        for part in ['logger','sample']:
            for key in ['schema','kind','source_sha','run_id','run_attempt']+(['device'] if part=='logger' else []):
                for remove in [False,True]:
                    obj=self.observation_gate();receipt=self.settled_observation()
                    if remove:receipt[part].pop(key)
                    else:receipt[part][key]='wrong'
                    with patch.dict(os.environ,{'GITHUB_RUN_ID':'123'}),patch.object(gate,'strict_json',return_value=receipt):obj.finalize_observation()
                    self.assertTrue(obj.uncertain,(part,key,remove))
                    with patch('subprocess.call',side_effect=AssertionError('new simulator work')):obj.cleanup()
    def testNonObjectWrapperSafetyAlwaysFailsClosed(self):
        for receipt in [[],None,'value',17,True]:
            obj=self.observation_gate()
            with patch.object(gate,'strict_json',return_value=receipt):obj.finalize_observation()
            self.assertTrue(obj.uncertain)
            with patch('subprocess.call',side_effect=AssertionError('new simulator work')):obj.cleanup()
    def testMissingLoggerPidOnlyQualifiesExplicitNoChildOutcome(self):
        for outcome in ['running','completed','command_failed',None]:
            value={'uncertain':False,'outcome':outcome,'simulator_stream_settled':True}
            self.assertFalse(gate.logger_settled(value))
        for outcome in ['spawn_failed','skipped_insufficient_budget']:
            self.assertTrue(gate.logger_settled({'uncertain':False,'outcome':outcome}))
        for pid in [True,False,0,-1,'12']:
            self.assertFalse(gate.logger_settled({'uncertain':False,'host_pid':pid,'simulator_stream_settled':True}))
    def testSameWrapperClampsLogToInstallDeadlineAndRequiresPositiveSettlement(self):
        from unittest.mock import Mock
        import ios_install_observer
        logger=Mock();logger.finish.return_value={'uncertain':False,'host_pid':12,'simulator_stream_settled':False}
        context={'source_sha':'a'*40,'run_id':'123','run_attempt':'1','sample_receipt':{'uncertain':False}}
        with patch.object(ios_install_observer,'DeviceLog',return_value=logger) as created,patch.object(gate,'save') as saved,patch('builtins.print'):
            obs=gate.InstallObservation(context,['xcrun','simctl','install','owned','app'],42,lambda:False)
            self.assertEqual(created.call_args.args[-1],42);self.assertIs(context['device_log'],logger)
            obs.observed(0,20);obs.finish();obs.finish()
        logger.finish.assert_called_once();receipt=saved.call_args.args[1];self.assertTrue(receipt['prohibit_further_simctl']);self.assertEqual(receipt['native_install']['returncode'],0)


PUBLIC_OWNED_PATHS = ['owned-simulator.json', 'owned-inventory-projection.json', 'owned-runtime.json', 'build-binding.json', 'phases.json', 'install-only-result.json', 'install-result.json', 'install-pressure-before.json', 'install-pressure-after.json', '*-dispatch-timing.json', 'toolchain.log', 'host-memory.log', 'bootstatus.log', 'install-owned-app.log', 'install-observation/install-device-log.json', 'install-observation/install-device-log.stdout.log', 'install-observation/install-device-log.stderr.log', 'install-observation/install-sample.json', 'install-observation/install-sample.stdout.log', 'install-observation/install-sample.stderr.log', 'install-observation/install-wrapper-observation.json']

class PublicEvidenceTests(unittest.TestCase):
    def values(self):
        device='12345678-1234-1234-1234-123456789AB0';runtime='com.apple.CoreSimulator.SimRuntime.iOS-27-0'
        other={'udid':'UNRELATED-PRIVATE-UDID','name':'Private personal simulator','state':'Booted','isAvailable':True,'dataPath':'/private/person/data','logPath':'/private/person/logs'}
        owned={'udid':device,'name':'Celluloid iOS27 iPhone SE (3rd generation)','state':'Shutdown','isAvailable':True,'dataPath':'/owned/data','logPath':'/owned/logs','extra':'private-extra'}
        before={'devices':{runtime:[other]}};after={'devices':{runtime:[other,owned]}};owner={'device_id':device,'runtime_id':runtime,'source_sha':'a'*40,'run_id':'123','run_attempt':'1','created_by_this_job':True,'absent_before_create':True}
        return before,after,owner
    def testProjectionDropsEveryOtherDeviceAndAllUnreviewedFields(self):
        before,after,owner=self.values();value=gate.owned_inventory_projection(before,after,owner);text=json.dumps(value)
        for token in ['UNRELATED','Private personal','/private','/owned','dataPath','logPath','private-extra']:self.assertNotIn(token,text)
        self.assertEqual(value['before_owned_matches'],[]);self.assertEqual(value['after_owned_matches'][0]['udid'],owner['device_id']);self.assertFalse(value['full_inventory_publicly_retained'])
        for name,data in [('before',before),('after',after)]:self.assertEqual(value['local_full_inventory_sha256'][name],hashlib.sha256((json.dumps(data,indent=2,sort_keys=True)+'\n').encode()).hexdigest())
    def testPreexistingDuplicateWrongOwnerStateOrRuntimeFails(self):
        for mutate in [lambda b,a,o:b['devices'][o['runtime_id']].append(a['devices'][o['runtime_id']][-1]),lambda b,a,o:a['devices'][o['runtime_id']].append(a['devices'][o['runtime_id']][-1]),lambda b,a,o:o.update(device_id='wrong'),lambda b,a,o:o.update(runtime_id='wrong'),lambda b,a,o:o.update(absent_before_create=False),lambda b,a,o:a['devices'][o['runtime_id']][-1].update(state='Booted'),lambda b,a,o:a['devices'][o['runtime_id']][-1].update(name='Private personal simulator')]:
            b,a,o=self.values();mutate(b,a,o)
            with self.assertRaises(ValueError):gate.owned_inventory_projection(b,a,o)
    def testRuntimeProjectionCannotRetainMountOrBundlePaths(self):
        _,_,owner=self.values();raw={'identifier':owner['runtime_id'],'name':'iOS27.0','version':'27.0','buildversion':'24A434','isAvailable':True,'bundlePath':'/private/runtime','runtimeRoot':'/private/mount','supportedDeviceTypes':[{'name':'private'}]}
        value=gate.owned_runtime_projection(raw,owner);self.assertEqual(set(value),{'identifier','name','version','buildversion','isAvailable'});self.assertNotIn('/private',json.dumps(value))
        for key,item in [('identifier','other'),('isAvailable',False),('name',['private']),('version','x'*129)]:
            changed=dict(raw);changed[key]=item
            with self.assertRaises(ValueError):gate.owned_runtime_projection(changed,owner)
    def testPublicUploadIsExactOwnedEvidenceAllowlist(self):
        workflow=(gate.ROOT/gate.WORKFLOW).read_text();block=workflow.split('          path: |\n',1)[1].split('          retention-days:',1)[0];paths=[x.strip() for x in block.splitlines() if x.strip()]
        expected=['build/install-diagnostic-source.txt','build/install-diagnostic-source-before.json','build/install-diagnostic-source-after.json']+['build/swiftui-acceptance/'+x for x in PUBLIC_OWNED_PATHS]
        self.assertEqual(paths,expected);self.assertEqual(len(paths),len(set(paths)))
        for forbidden in ['devices-before','devices-after-create','runtime-metadata','create-owned-device.log','build.log','host-portable.log']:
            self.assertFalse(any(forbidden in x for x in paths))
        self.assertNotIn('build/swiftui-acceptance/',paths)
    def testProjectionIsAfterFreshValidationAndRawInputsStayLocal(self):
        source=(gate.ROOT/'Scripts/run_ios_install_diagnostic.py').read_text();tree=ast.parse(source);run=next(x for x in ast.walk(tree) if isinstance(x,ast.FunctionDef) and x.name=='run');text=ast.get_source_segment(source,run)
        self.assertLess(text.index('owner=owner_receipt('),text.index('owned_inventory_projection(before,after,owner)'));self.assertIn("save(OUT/'devices-before.json',before)",text);self.assertIn("save(OUT/'devices-after-create.json',after)",text)
        self.assertIn("save(OUT/'owned-runtime.json',owned_runtime_projection(matches[0],owner))",text)


WRAPPER_PREFIX = "install_diagnostic_route = absolute_deadline and os.environ.get('GITHUB_REF') == 'refs/heads/cell-ios-install-diagnostic'\ninstall_observer_context = None\ninstall_observer_wait = None\ninstall_observation = None\ninstall_cancelled = [None]\nif install_diagnostic_route:\n    # Only this exact new route defers cancellation while it owns children.\n    import atexit\n    from run_ios_install_diagnostic import bounded_admission, OBSERVATIONS, InstallObservation, defer_cancellation\n    install_cancelled = defer_cancellation()\n    install_observer_context = bounded_admission(args.label, args.command, args.seconds)\n    if args.label == 'install-owned-app':\n        from ios_install_observer import wait_with_one_sample\n        install_observer_wait = wait_with_one_sample\n"
WRAPPER_SPAWN = "    if install_diagnostic_route and install_cancelled[0] is not None:\n        raise RuntimeError('Cancelled before native dispatch')\n    if install_observer_wait is None:\n        process = subprocess.Popen(args.command, start_new_session=True)\n    else:\n        install_observation = InstallObservation(install_observer_context,args.command,deadline,lambda: install_cancelled[0] is not None)\n        atexit.register(install_observation.finish)\n        install_observation.start()\n        process = install_observation.spawn(lambda: subprocess.Popen(args.command, start_new_session=True))\n"
WRAPPER_WAIT = "        if install_observer_wait is None:\n            code = process.wait(timeout=remaining)\n        else:\n            try:\n                code = install_observer_wait(process, deadline, args.command, OBSERVATIONS, install_observer_context)\n            except subprocess.TimeoutExpired:\n                raise\n            except BaseException as observation_error:\n                # Keep the same owned native waiter and original deadline. An\n                # observer failure is not evidence that install itself timed out.\n                install_observation.control_errors.append({'phase':'sample','error':type(observation_error).__name__})\n                print('BOUNDED_COMMAND_CLEANUP_UNCONFIRMED', json.dumps(error_record(observation_error)), flush=True)\n                remaining = deadline - time.monotonic()\n                if remaining <= 0:\n                    raise subprocess.TimeoutExpired(args.command, args.seconds) from observation_error\n                code = process.wait(timeout=remaining)\n            install_observation.observed(code)\n"
WRAPPER_END = "if install_observation is not None:\n    install_observation.finish()\n    atexit.unregister(install_observation.finish)\nif install_diagnostic_route and install_cancelled[0] is not None:\n    print('BOUNDED_COMMAND_CLEANUP_UNCONFIRMED deferred cancellation', flush=True)\n    code = 128 + install_cancelled[0]\n"

def restore_install_wrapper(source):
    for fragment in [WRAPPER_PREFIX,WRAPPER_SPAWN,WRAPPER_WAIT,WRAPPER_END]:
        if source.count(fragment)!=1:raise ValueError('Install wrapper hook changed or repeated')
    return source.replace(WRAPPER_PREFIX,'').replace(WRAPPER_SPAWN,'    process = subprocess.Popen(args.command, start_new_session=True)\n').replace(WRAPPER_WAIT,'        code = process.wait(timeout=remaining)\n').replace(WRAPPER_END,'').replace("(os.environ.get('GITHUB_REF') != 'refs/heads/cell-ios-photos-host-final' and not install_diagnostic_route)","os.environ.get('GITHUB_REF') != 'refs/heads/cell-ios-photos-host-final'")

class WrapperTests(unittest.TestCase):
    def testRemovingExactHookRestoresOriginalWrapperBytes(self):
        source=(gate.ROOT/'Scripts/run_bounded.py').read_text();restored=restore_install_wrapper(source)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),'798a18065939c9787dcf27d42ab1917ee8d7dd4835d9ff48ef6b52e8b4cf1acd')
        for old,new in [('os.killpg(process.pid, sig)','os.killpg(1, sig)'),('photos_cleanup_started + 10','photos_cleanup_started + 20'),("break  # Never switch signals or routes after denied cleanup.","pass  # ignore denial")]:
            changed=source.replace(old,new)
            self.assertNotEqual(hashlib.sha256(restore_install_wrapper(changed).encode()).hexdigest(),hashlib.sha256(restored.encode()).hexdigest())
    def exercise(self,uncertain=False,closed=False,hook_error=False):
        import contextlib,io,runpy,subprocess
        from unittest.mock import Mock
        import ios_install_observer
        proc=Mock(pid=4321,returncode=0);proc.poll.return_value=0;proc.wait.return_value=0;context={'source_sha':'a'*40,'run_id':'123','run_attempt':'1'}
        logger=Mock();logger.start.return_value={'uncertain':False};logger.finish.return_value={'uncertain':False,'host_pid':987,'simulator_stream_settled':True};logger.spawn_if_certain.side_effect=lambda callback,deadline,cancelled:callback()
        def hook(process,deadline,command,out,values):
            self.assertIs(process,proc);self.assertEqual(deadline,20);self.assertIs(values,context)
            if hook_error:raise ValueError('unexpected observer error')
            values['sample_receipt']={'uncertain':uncertain,'install_returncode':0,'install_return_monotonic':1};return 0
        env={'GITHUB_REF':'refs/heads/'+gate.BRANCH,'GITHUB_REPOSITORY':'100mango/Celluloid','GITHUB_SHA':'a'*40,'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1'}
        output=io.StringIO()
        with patch.dict(os.environ,env,clear=True),patch.object(sys,'argv',['run_bounded.py','--seconds','120','--label','install-owned-app','--deadline-monotonic','20','xcrun','simctl','install','owned','owned.app']),patch('time.monotonic',return_value=1),patch('signal.signal'),patch.object(gate,'save'),patch.object(gate,'bounded_admission',side_effect=ValueError('closed') if closed else None,return_value=context),patch.object(ios_install_observer,'DeviceLog',return_value=logger),patch.object(ios_install_observer,'wait_with_one_sample',side_effect=hook) as sampled,patch('subprocess.Popen',return_value=proc) as spawned,patch('os.killpg') as killed,contextlib.redirect_stdout(output):
            if closed:
                with self.assertRaises(ValueError):runpy.run_path(str(gate.ROOT/'Scripts/run_bounded.py'),run_name='__main__')
                spawned.assert_not_called();sampled.assert_not_called();return None,output.getvalue()
            with self.assertRaises(SystemExit) as stopped:runpy.run_path(str(gate.ROOT/'Scripts/run_bounded.py'),run_name='__main__')
        sampled.assert_called_once();killed.assert_not_called();return stopped.exception.code,output.getvalue()
    def testClosedRouteNeverSpawnsAndExactOwnerIsHandedToHook(self):
        self.exercise(closed=True);code,text=self.exercise();self.assertEqual(code,0);self.assertNotIn('CLEANUP_UNCONFIRMED',text)
    def testObservationUncertaintyRetainsActualExitAndUnexpectedErrorKeepsOriginalWaiter(self):
        code,text=self.exercise(uncertain=True);self.assertEqual(code,0);self.assertIn('CLEANUP_UNCONFIRMED',text)
        code,text=self.exercise(hook_error=True);self.assertEqual(code,0);self.assertNotIn('BOUNDED_COMMAND_TIMEOUT',text);self.assertIn('CLEANUP_UNCONFIRMED',text)
        records=[json.loads(line.split(' ',1)[1]) for line in text.splitlines() if line.startswith('INSTALL_WRAPPER_OBSERVATION ')];self.assertEqual(records[0]['native_install']['returncode'],0);self.assertTrue(records[0]['native_install']['within_deadline']);self.assertEqual(records[0]['control_errors'],[{'phase':'sample','error':'ValueError'}])

class RealCancellationTests(unittest.TestCase):
    def checkpoint(self,output,cleanup):
        lines=output.split(b'\n')[:-1]  # Ignore an unfinished pipe frame until its newline.
        if not cleanup:return b'REAL_CHILD_READY' in lines
        for line in lines:
            if line.startswith(b'PHOTOS_BOUNDED_TIMING '):
                if json.loads(line.split(b' ',1)[1]).get('phase')=='cleanup-wait-begin':return True
        return False
    def testCommandEchoCannotImpersonateActualSignalCheckpoint(self):
        echo=b'BOUNDED_COMMAND_BEGIN '+json.dumps({'command':['print("REAL_CHILD_READY");print("REAL_CHILD_COMPLETED")']}).encode()
        self.assertFalse(self.checkpoint(echo,False));self.assertTrue(self.checkpoint(echo+b'\nREAL_CHILD_READY\n',False))
        self.assertFalse(self.checkpoint(b'PHOTOS_BOUNDED_TIMING {"phase":"wrapper-ready","label":"cleanup-wait-begin"}',True))
        self.assertTrue(self.checkpoint(b'PHOTOS_BOUNDED_TIMING {"phase":"cleanup-wait-begin"}\n',True))
        partial=b'PHOTOS_BOUNDED_TIMING {"phase":"cleanup-wait-beg'
        self.assertFalse(self.checkpoint(partial,True));self.assertTrue(self.checkpoint(partial+b'in"}\n',True))
        self.assertFalse(self.checkpoint(b'REAL_CHILD_READY',False))
    def wrapper_signal(self,cleanup=False):
        import subprocess,signal,selectors,time
        # Admission is stubbed only in this Linux harness. The actual wrapper,
        # Popen session owner, signal handler, absolute deadline and cleanup run.
        script="""
import sys,os,time,runpy,json
sys.path.insert(0,sys.argv[1])
import run_ios_install_diagnostic as gate,ios_install_observer as observer
context={'source_sha':'a'*40,'run_id':'123','run_attempt':'1'}
gate.bounded_admission=lambda *a:context
class Observation:
 def __init__(self,*a):self.control_errors=[]
 def start(self):pass
 def spawn(self,callback):return callback()
 def observed(self,code,when=None):print('REAL_NATIVE_EXIT',code,flush=True)
 def finish(self):pass
gate.InstallObservation=Observation
observer.wait_with_one_sample=lambda process,deadline,*a:process.wait(timeout=deadline-time.monotonic())
cleanup=sys.argv[2]=='yes'
release=sys.argv[3]
child="import os,time,signal\\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\\nprint('REAL_CHILD_READY',flush=True)\\nend=time.monotonic()+6\\nwhile not os.path.exists("+repr(release)+") and time.monotonic()<end:time.sleep(.01)\\nif not os.path.exists("+repr(release)+"):raise RuntimeError('test release deadline')\\nprint('REAL_CHILD_COMPLETED',flush=True)"
cap=1 if cleanup else 3
sys.argv=['run_bounded.py','--seconds',str(cap),'--label','install-owned-app','--deadline-monotonic',str(time.monotonic()+cap),sys.executable,'-S','-c',child]
runpy.run_path(gate.ROOT/'Scripts/run_bounded.py',run_name='__main__')
"""
        env=dict(os.environ,GITHUB_REF='refs/heads/'+gate.BRANCH,GITHUB_REPOSITORY='100mango/Celluloid',GITHUB_SHA='a'*40,GITHUB_RUN_ID='123',GITHUB_RUN_ATTEMPT='1')
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup);release=Path(directory.name)/'release'
        proc=subprocess.Popen([sys.executable,'-S','-c',script,str(gate.ROOT/'Scripts'),'yes' if cleanup else 'no',str(release)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=env,start_new_session=True)
        output=bytearray();selector=selectors.DefaultSelector();selector.register(proc.stdout,selectors.EVENT_READ);sent=False;deadline=time.monotonic()+8
        try:
            while time.monotonic()<deadline:
                for key,_ in selector.select(.05):
                    data=os.read(key.fileobj.fileno(),65536)
                    if not data:selector.unregister(key.fileobj);break
                    output.extend(data)
                if not sent and self.checkpoint(bytes(output),cleanup):
                    proc.send_signal(signal.SIGTERM);proc.send_signal(signal.SIGINT);sent=True
                    release.write_text('signals dispatched')
                if proc.poll() is not None and not selector.get_map():break
            self.assertIsNotNone(proc.poll(),'Owned harness must finish within original deadline and cleanup');self.assertTrue(sent)
            text=output.decode();self.assertIn('REAL_CHILD_COMPLETED',text.splitlines());self.assertIn('deferred cancellation',text);self.assertIn(proc.returncode,[130,143])
            if cleanup:self.assertIn('child_reaped',text);self.assertIn('BOUNDED_COMMAND_TIMEOUT',text)
            else:self.assertIn('REAL_NATIVE_EXIT 0',text.splitlines())
        finally:
            selector.close();proc.stdout.close()
            if proc.poll() is None:proc.kill();proc.wait(timeout=2)
    def testActualTermIntDuringInstallKeepOwnerUntilChildReturns(self):self.wrapper_signal()
    def testRepeatedActualSignalsDuringTimeoutCleanupDoNotAbandonReap(self):self.wrapper_signal(cleanup=True)
    def testParentRecordOnlyCancellationCannotStartFollowingCommand(self):
        import subprocess
        script="""
import os,sys,signal,subprocess
sys.path.insert(0,sys.argv[1]);import run_ios_install_diagnostic as gate
obj=object.__new__(gate.InstallDiagnostic);obj.uncertain=False;obj.cancel_signal=None
gate.defer_cancellation(obj.cancel)
os.kill(os.getpid(),signal.SIGTERM);os.kill(os.getpid(),signal.SIGINT)
if not (obj.uncertain and obj.cancel_signal in (signal.SIGTERM,signal.SIGINT)):raise RuntimeError('cancellation not retained')
try:obj.command('next',['xcrun','simctl','list'],20)
except ValueError:print('CANCELLED_NO_DISPATCH')
else:raise RuntimeError('continued after cancellation')
"""
        result=subprocess.run([sys.executable,'-S','-c',script,str(gate.ROOT/'Scripts')],capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn('CANCELLED_NO_DISPATCH',result.stdout)

if __name__=='__main__':
    # Actual native preflight executes both new control suites plus the unchanged
    # Photos source/functional guards; no site-package dependency.
    import test_ios_install_observer,test_ios_photos_host
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(m) for m in [sys.modules[__name__],test_ios_install_observer,test_ios_photos_host])
    raise SystemExit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)
