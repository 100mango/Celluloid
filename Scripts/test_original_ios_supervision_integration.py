"""Executable staged dispatch fences and pure failed-evidence retention."""
import contextlib,io,json,os,pathlib,runpy,shlex,shutil,subprocess,sys,tempfile,time,unittest
from unittest.mock import MagicMock,patch
import original_ios_process_guard as guard
import uikit_full_shipping_gate as gate
import uikit_full_shipping_handoff as handoff
from test_original_ios_process_guard import environment
from test_uikit_full_shipping_workflow import body
ROOT=pathlib.Path(__file__).resolve().parents[1]

class SupervisionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup);self.root=pathlib.Path(self.directory.name)
        env=environment(self.root);env['PATH']=os.environ.get('PATH',os.defpath)
        self.environment=patch.dict(os.environ,env,clear=True);self.environment.start();self.addCleanup(self.environment.stop)
        self.context=guard.staged_context();self.clock={'schema':gate.CLOCK_SCHEMA,**self.context,'started_monotonic':time.monotonic(),'started_unix':time.time(),'execution_budget_seconds':3360}
        (self.root/'full-shipping-clock.json').write_text(json.dumps(self.clock))

    def mark_failure(self):
        owner=guard.OwnedCommand('xcrun','units summary',30);owner.started(MagicMock(pid=12345));owner.failed(subprocess.TimeoutExpired('summary',30),timed_out=True);return owner

    def shell_functions(self):
        text=body((ROOT/'.github/workflows/original-ios-release.yml').read_text(),'Start the fixed row clock')
        return text.split("<<'SHFUNCTIONS'\n",1)[1].split('\nSHFUNCTIONS',1)[0]

    def test_failure_blocks_every_native_phase_but_host_retention_can_be_admitted(self):
        self.mark_failure()
        allowed={'source-before','source-after','collection','upload'}
        for phase in set(gate.WORK_CEILINGS)|set(gate.TAIL_PHASES):
            if phase in {'preflight'}:continue
            with self.subTest(phase=phase):
                if phase in allowed:self.assertGreater(gate.admit_phase(self.clock,self.context,phase),0)
                else:
                    with self.assertRaises(guard.GuardRefusal):gate.admit_phase(self.clock,self.context,phase)

    def test_actual_workflow_adapter_never_launches_successor_after_uncertainty(self):
        self.mark_failure();sentinel=self.root/'forbidden-successor'
        code='from pathlib import Path;Path('+repr(str(sentinel))+').touch()'
        script=self.shell_functions()+'\nbounded units forbidden '+shlex.quote(sys.executable)+' -c '+shlex.quote(code)+'\n'
        result=subprocess.run(['bash','-c',script],cwd=ROOT,env=dict(os.environ),capture_output=True,text=True,timeout=10)
        self.assertNotEqual(result.returncode,0);self.assertFalse(sentinel.exists());self.assertNotIn('BOUNDED_COMMAND_BEGIN',result.stdout)

    def test_normally_finalized_nonzero_workflow_command_allows_independent_case(self):
        sentinel=self.root/'independent';code='from pathlib import Path;Path('+repr(str(sentinel))+').touch()'
        command=shlex.quote(sys.executable)
        script=self.shell_functions()+'\nstatus=0\nbounded units expected-failure '+command+' -c '+shlex.quote('raise SystemExit(65)')+' || status=$?\ntest "$status" -eq 65 || exit 1\nbounded units independent '+command+' -c '+shlex.quote(code)+'\n'
        result=subprocess.run(['bash','-c',script],cwd=ROOT,env=dict(os.environ),capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr);self.assertTrue(sentinel.exists());self.assertIsNone(guard.read_failure(self.root,self.context))

    def diagnostic(self,error=None,prior_failure=False):
        if prior_failure:self.mark_failure()
        calls=[];original_exists=pathlib.Path.exists;original_read=pathlib.Path.read_text
        def exists(path):return True if str(path)=='/tmp/current-celluloid-simulator' else original_exists(path)
        def read(path,*a,**kw):return 'owned-device' if str(path)=='/tmp/current-celluloid-simulator' else original_read(path,*a,**kw)
        def invoke(args,**kw):
            calls.append((args,kw))
            if error:
                owner=guard.OwnedCommand('xcrun','diagnostics',45);owner.started(MagicMock(pid=12345));owner.failed(error,timed_out=True)
                raise error
            return subprocess.CompletedProcess(args,0,'owned app diagnostic','')
        with patch.object(pathlib.Path,'exists',exists),patch.object(pathlib.Path,'read_text',read),patch.object(pathlib.Path,'glob',return_value=[]),patch('native_process.run',side_effect=invoke),contextlib.redirect_stdout(io.StringIO()):
            try:runpy.run_path(str(ROOT/'Scripts/collect_simulator_diagnostics.py'),run_name='__main__')
            except BaseException as caught:return calls,caught
        return calls,None

    def test_diagnostics_read_owned_log_without_premature_shutdown(self):
        calls,error=self.diagnostic();self.assertIsNone(error)
        self.assertEqual(len(calls),1);self.assertEqual(calls[0][0][:3],['xcrun','simctl','spawn']);self.assertNotIn('shutdown',calls[0][0])
        workflow=(ROOT/'.github/workflows/original-ios-release.yml').read_text()
        self.assertLess(workflow.index('- name: Verify installed shipping product after all tests'),workflow.index('- name: Shut down owned simulator'))

    def test_inner_diagnostic_timeout_marks_owner_and_old_failure_dispatches_nothing(self):
        error=TimeoutError('owned diagnostic timeout');calls,caught=self.diagnostic(error)
        self.assertIs(caught,error);self.assertEqual(len(calls),1);failure=guard.read_failure(self.root,self.context);self.assertEqual(failure['original_error']['type'],'TimeoutError')
        with patch('subprocess.Popen',side_effect=AssertionError('forbidden successor')):
            with self.assertRaises(guard.GuardRefusal):guard.ensure_native_dispatch()

    def test_diagnostics_do_not_dispatch_after_existing_owner_failure(self):
        calls,error=self.diagnostic(prior_failure=True);self.assertIsInstance(error,guard.GuardRefusal);self.assertEqual(calls,[])

    def test_screenshot_export_uses_direct_owner_and_stops_after_timeout(self):
        (self.root/'TestResults-owned.xcresult').mkdir();prior=os.getcwd();os.chdir(self.root);self.addCleanup(os.chdir,prior)
        failure=TimeoutError('owned screenshot exporter timeout')
        def invoke(*args,**kwargs):
            owner=guard.OwnedCommand('xcrun','screenshot',45);owner.started(MagicMock(pid=12345));owner.failed(failure,timed_out=True)
            raise failure
        with patch('native_process.run',side_effect=invoke) as call,self.assertRaises(TimeoutError):runpy.run_path(str(ROOT/'Scripts/export_permission_screenshot.py'),run_name='__main__')
        self.assertEqual(call.call_count,1);self.assertEqual(guard.read_failure(self.root,self.context)['original_error']['type'],'TimeoutError')

    def test_failed_evidence_retains_guard_and_raw_logs_without_any_native_export(self):
        self.mark_failure();failure=(self.root/guard.MARKER_NAME).read_bytes();inflight=(self.root/guard.INFLIGHT_NAME).read_bytes()
        script_root=self.root/'source';(script_root/'Scripts').mkdir(parents=True)
        script=script_root/'Scripts/collect_native_evidence.py';shutil.copyfile(ROOT/'Scripts/collect_native_evidence.py',script)
        (script_root/'TestResults-failed.xcresult').mkdir();(self.root/'units.log').write_text('Actual failure observation retained without acceptance\n')
        # A positive receipt created before a later failure cannot override it.
        (self.root/'full-shipping-row.json').write_text(json.dumps({'row_checks_passed':True}))
        with patch.dict(os.environ,CELLULOID_EVIDENCE_PLATFORM='compact-phone'),patch('subprocess.run',side_effect=AssertionError('native exporter dispatched')),patch('native_process.run',side_effect=AssertionError('owned exporter dispatched')),contextlib.redirect_stdout(io.StringIO()):
            runpy.run_path(str(script),run_name='__main__')
        out=self.root/'celluloid-bounded-evidence';manifest=json.loads((out/'manifest.json').read_text())
        self.assertEqual((out/guard.MARKER_NAME).read_bytes(),failure);self.assertEqual((out/guard.INFLIGHT_NAME).read_bytes(),inflight)
        self.assertFalse(manifest['original_ios_process_guard']['native_dispatch_clear']);self.assertFalse(json.loads((out/handoff.LOG_INDEX).read_text())['producer_complete'])
        self.assertLessEqual(sum(p.stat().st_size for p in out.iterdir()),1_500_000)
        with self.assertRaises(guard.GuardRefusal):handoff.accept_row(out)

    def test_staged_collection_has_inner_budget_and_source_after_stays_bounded(self):
        workflow=(ROOT/'.github/workflows/original-ios-release.yml').read_text()
        source=body(workflow,'Verify tested source stayed unchanged');self.assertIn('bounded source-after source-after',source)
        collection=body(workflow,'Export bounded combined evidence');self.assertNotIn('bounded collection',collection)
        for name in ['Export bounded synthetic UI evidence','Collect targeted failure diagnostics']:
            step=body(workflow,name);self.assertNotIn('bounded ',step);self.assertIn('full_gate admit --phase',step);self.assertIn('full_gate check-clock --phase',step)
        self.assertIn('full_gate admit --phase collection',collection);self.assertIn('full_gate check-clock --phase collection',collection)
        collector=(ROOT/'Scripts/collect_native_evidence.py').read_text();self.assertIn('timeout+15+30',collector);self.assertIn('STAGED_COLLECTION_DEADLINE',collector)

if __name__=='__main__':unittest.main()
