"""One fixed source-bound Photos observation job; no new native42 qualification."""
import hashlib,json,os,re,subprocess,tempfile,unittest
from pathlib import Path
from unittest import mock
import validation_route as route
from test_native_workflow_syntax import run_blocks
ROOT=Path(__file__).resolve().parents[1]

def environment(source='a'*40):
    selected=route.HOST_ONLY
    return {'GITHUB_REF':'refs/heads/'+selected['branch'],'GITHUB_REPOSITORY':route.REPOSITORY,
        'GITHUB_EVENT_NAME':'push','CELLULOID_VALIDATION_SCOPE':selected['scope'],
        'GITHUB_WORKFLOW_REF':route.REPOSITORY+'/'+selected['workflow_path']+'@refs/heads/'+selected['branch'],
        'GITHUB_SHA':source,'GITHUB_WORKFLOW_SHA':source}

class PhotosObservationRouteTests(unittest.TestCase):
    def test_exact_route_and_real_source_identity(self):
        env=environment();before=dict(env)
        self.assertEqual(route.current_route(env),route.HOST_ONLY);self.assertEqual(env,before)
        self.assertEqual(route.validate_route(route.HOST_ONLY),route.HOST_ONLY)
        for key,value in [('GITHUB_REF','refs/heads/arbitrary'),('GITHUB_REPOSITORY','other/Celluloid'),
                          ('GITHUB_EVENT_NAME','workflow_dispatch'),('CELLULOID_VALIDATION_SCOPE','mac-repair'),
                          ('GITHUB_WORKFLOW_REF',route.REPOSITORY+'/'+route.FOCUSED['workflow_path']+'@'+env['GITHUB_REF']),
                          ('GITHUB_WORKFLOW_SHA',route.HOST_ONLY_BASE['commit']),('GITHUB_SHA','')]:
            with self.subTest(key=key),self.assertRaises(ValueError):route.current_route(dict(env,**{key:value}))
        for key in env:
            bad=dict(env);bad.pop(key)
            with self.subTest(missing=key),self.assertRaises(ValueError):route.current_route(bad)

    def test_single_fresh_host_job_is_byte_identical_except_trigger_identity(self):
        original=(ROOT/route.FOCUSED['workflow_path']).read_text().split('  native-mac-host:',1)[1]
        source=(ROOT/route.HOST_ONLY['workflow_path']).read_text()
        self.assertEqual(re.findall(r'^  ([a-z-]+):$',source.split('jobs:\n',1)[1],re.M),['native-mac-host'])
        expected=original.replace('    # A new ephemeral VM, serialized behind Mac diagnostics. Host registration is\n    # independent of cross-display pixels; neither result grants release acceptance.\n    needs: [build-preflight, native-mac]\n    if: always() && needs.build-preflight.result == \'success\'\n','    # Fresh actual host build and observation only; no42-case or UIKit execution.\n')
        expected=expected.replace('name: celluloid-repair-mac-host-','name: celluloid-photos-export-observation-')
        expected=expected.replace('timeout-minutes: 14','timeout-minutes: 28').replace('python3 Scripts/test_mac_photos_host_gate.py','python3 Scripts/run_bounded.py --seconds 240 --label photos-host-portable-pretest python3 Scripts/test_mac_photos_host_gate.py')
        self.assertEqual(source.split('  native-mac-host:',1)[1],expected)
        self.assertIn('branches: [codex/photos-export-observation]',source)
        self.assertIn('CELLULOID_VALIDATION_SCOPE: photos-export-observation',source)
        self.assertIn('group: celluloid-platforms-refs/heads/codex/apple-platforms',source)
        self.assertIn('cancel-in-progress: false',source)
        self.assertEqual(source.count('runs-on: xcode-27'),1)
        self.assertEqual(source.count('timeout-minutes: 45'),1)
        self.assertEqual(source.count('timeout-minutes: 28'),1)
        self.assertIn("'execution_budget_seconds':41*60",source)
        self.assertIn('retention-days: 1',source)
        for forbidden in ['workflow_dispatch:', 'strategy:', 'matrix:', 'run_early_uikit_interop.py','verify_required_interoperability.py','download-artifact','GITHUB_SHA=', 'GITHUB_WORKFLOW_SHA=']:
            self.assertNotIn(forbidden,source)
        for path,digest in [('.github/workflows/apple-platforms.yml','40fe18118e1f3996717354e56d55e167dff29b8fbe87455c832386e9a1c36f91'),('.github/workflows/mac-repair.yml','20b2fa6763be3b0014fb598a68088d9927c65790f30904cc04061a902b751daa')]:
            self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),digest)

    def test_exact_clock_profiles_nest_and_cannot_cross_routes(self):
        import copy
        canonical=route.host_clock_profile(route.FULL);focused=route.host_clock_profile(route.HOST_ONLY)
        self.assertEqual([canonical[k] for k in ('case_seconds','test_seconds','process_seconds')],[600,660,720])
        self.assertEqual(route.host_clock_profile(route.FOCUSED),canonical)
        self.assertEqual([focused[k] for k in ('case_seconds','test_seconds','process_seconds')],[900,960,1020])
        self.assertEqual(focused['step_seconds'],sum(focused[k] for k in ('pretest_seconds','process_seconds','tail_seconds','step_margin_seconds')))
        self.assertEqual(focused['before_prepare_seconds'],focused['step_seconds']+300)
        self.assertEqual(focused['before_host_seconds'],focused['step_seconds']-240+300)
        self.assertEqual(focused['tail_seconds'],30+60+4*20+6*20+70)
        self.assertLess(270+focused['before_prepare_seconds'],41*60)
        for selected,profile in [(route.FULL,canonical),(route.HOST_ONLY,focused)]:
            context={'validation_route':dict(selected),'host_clock_profile':profile}
            self.assertEqual(route.context_clock(context),profile)
            for key in profile:
                bad=copy.deepcopy(context);bad['host_clock_profile'][key]=True
                with self.assertRaises(ValueError):route.context_clock(bad)
            bad=copy.deepcopy(context);bad['host_clock_profile']=focused if selected==route.FULL else canonical
            with self.assertRaises(ValueError):route.context_clock(bad)

    def test_host_only_admission_preserves_all_phases_and_optional_reserve(self):
        import mac_photos_host_gate as gate,mac_owned_crash as crash
        from test_mac_photos_host_gate import HostTimeBudgetTests
        for phase,now,passed in [('before-prepare',580.0,True),('before-prepare',581.0,False),('before-host',820.0,True),('before-host',821.0,False)]:
            with tempfile.TemporaryDirectory() as folder,mock.patch.dict(os.environ,dict(environment(),RUNNER_TEMP=folder)),mock.patch.object(gate,'require_runner'):
                root=Path(folder);HostTimeBudgetTests().prepare(root)
                if phase=='before-host':
                    with mock.patch.object(gate.time,'monotonic',return_value=101):gate.budget('before-prepare')
                with mock.patch.object(gate.time,'monotonic',return_value=now):
                    if passed:gate.budget(phase)
                    else:
                        with self.assertRaises(RuntimeError):gate.budget(phase)
                report=gate.read_receipt(root/'mac-host-budget.json');self.assertEqual(report['admitted'],passed)
                if passed and phase=='before-host':gate.validate_budget(report,gate.read_receipt(root/'mac-job-clock.json'),'a'*40,True,route.HOST_ONLY)
                clock=gate.read_receipt(root/'mac-job-clock.json')
                self.assertEqual(crash.optional_budget(clock,'a'*40,'prepare',560,route.HOST_ONLY)['mandatory_reserve_seconds'],1980)
                self.assertFalse(crash.optional_budget(clock,'a'*40,'prepare',569,route.HOST_ONLY)['admitted'])

    def test_every_literal_job_command_parses(self):
        blocks=list(run_blocks((ROOT/route.HOST_ONLY['workflow_path']).read_text()));self.assertGreaterEqual(len(blocks),10)
        for line,body in blocks:
            with self.subTest(line=line):
                result=subprocess.run(['bash','-n'],input=body,text=True,capture_output=True,timeout=5)
                self.assertEqual(result.returncode,0,result.stderr)

    def test_protected_bytes_and_report_distinguish_prior_proof_from_new_execution(self):
        import verify_combined_source as verify
        from staged_test_fixtures import historical_checkout
        with historical_checkout() as root,mock.patch.dict(globals(),ROOT=root),mock.patch.object(verify,'ROOT',root):
            self._assert_historical_protected_bytes_and_report()

    def _assert_historical_protected_bytes_and_report(self):
        import verify_combined_source as verify
        contract=json.loads((ROOT/'Scripts/combined-source-contract.json').read_text())
        self.assertEqual(len(contract['files']),547)
        for path,digest in contract['files']:self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),digest)
        source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        with tempfile.TemporaryDirectory() as folder,mock.patch.dict(os.environ,dict(environment(source),RUNNER_TEMP=folder)),mock.patch('sys.argv',['verify_combined_source.py','--phase','before']):
            verify.main();report=json.loads((Path(folder)/'combined-source-before.json').read_text())
            self.assertEqual(report['source_sha'],source)
            self.assertFalse(report['host_only_diagnostic']['native_42_reexecuted'])
            self.assertFalse(report['host_only_diagnostic']['uikit_reexecuted'])
            self.assertEqual(report['host_only_diagnostic']['prior_source'],route.HOST_ONLY_BASE)
            self.assertEqual(report['host_only_diagnostic'],route.host_only_source_binding(contract['files']))
            with mock.patch.object(route,'HOST_ONLY_PROTECTED_FINGERPRINT','0'*64),self.assertRaises(ValueError):verify.main()

    def test_only_exact_reviewed_ui_test_can_differ_from_qualified_source(self):
        rows=json.loads((ROOT/'Scripts/combined-source-contract.json').read_text())['files']
        result=route.host_only_source_binding(rows)
        self.assertEqual(result['unchanged_protected_files'],546)
        self.assertEqual(result['reviewed_host_ui_test'],route.HOST_ONLY_UI_TEST)
        protected=[row for row in rows if row[0]!=route.HOST_ONLY_UI_TEST['path']]
        self.assertEqual(hashlib.sha256(json.dumps(protected,separators=(',',':')).encode()).hexdigest(),route.HOST_ONLY_PROTECTED_FINGERPRINT)
        cases=[]
        import copy
        for target in [0,next(i for i,row in enumerate(rows) if row[0]==route.HOST_ONLY_UI_TEST['path'])]:
            bad=copy.deepcopy(rows);bad[target][1]='0'*64;cases.append(bad)
        cases.extend([rows[:-1],rows+[rows[0]],list(reversed(rows))])
        bad=copy.deepcopy(rows);bad[0][0]='Platforms/UITests/Unreviewed.swift';cases.append(bad)
        bad=copy.deepcopy(rows);bad[0]=list(next(row for row in rows if row[0]==route.HOST_ONLY_UI_TEST['path']));cases.append(bad)
        for bad in cases:
            with self.subTest(change=bad[:1]),self.assertRaises(ValueError):route.host_only_source_binding(bad)

    def test_actual_host_receipts_and_collected_replay_bind_the_new_route(self):
        import test_mac_photos_host_gate as fixture
        helper=fixture.RuntimeAcceptanceTests();helper.setUp();self.addCleanup(helper.doCleanups);gate=fixture.gate
        collector=fixture.CollectedProofTests()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();helper.seed(root)
            context=gate.read_receipt(root/'mac-host-context.json');context.update(validation_route=dict(route.HOST_ONLY),host_clock_profile=route.host_clock_profile(route.HOST_ONLY),runner_environment=environment(helper.SOURCE));gate.write(root/'mac-host-context.json',context)
            for name in ['mac-host-source-before.json','mac-host-source-after.json','combined-source-before.json','combined-source-after.json']:
                value=gate.read_receipt(root/name);value.update(validation_route=dict(route.HOST_ONLY),workflow_sha256=gate.sha(ROOT/route.HOST_ONLY['workflow_path']))
                if name.startswith('combined-source-'):
                    value['host_only_diagnostic']=route.host_only_source_binding(json.loads((ROOT/'Scripts/combined-source-contract.json').read_text())['files'])
                gate.write(root/name,value)
            path=root/'mac-host-observed/lifecycle.json';value=gate.read_receipt(path);value['context_sha256']=gate.sha(root/'mac-host-context.json');value['deadline_seconds']=900;path.write_text(json.dumps(value,separators=(',',':'))+'\n')
            budget=gate.read_receipt(root/'mac-host-budget.json');profile=route.host_clock_profile(route.HOST_ONLY)
            budget.update(host_clock_profile=profile,host_process_seconds=1020)
            for row in budget['checks']:row['required_seconds']=profile['before_prepare_seconds' if row['phase']=='before-prepare' else 'before_host_seconds']
            gate.write(root/'mac-host-budget.json',budget)
            helper.write_transport_log(root,context)
            result=gate.verify_acceptance(root,helper.SOURCE);self.assertTrue(result['prerequisite_accepted']);self.assertFalse(result['complete_host_e2e'])
            self.assertEqual(result['validation_route'],route.HOST_ONLY)
            for phase in ['before','after']:
                path=root/('combined-source-'+phase+'.json');original=path.read_bytes();value=gate.read_receipt(path)
                value['host_only_diagnostic']['native_42_reexecuted']=True;gate.write(path,value)
                with self.assertRaises(AssertionError):gate.verify_acceptance(root,helper.SOURCE)
                path.write_bytes(original)
            gate.write(root/'mac-host-acceptance.json',result)
            collected=collector.collect(root);manifest=gate.verify_collected(collected,helper.SOURCE);self.assertEqual(manifest['validation_route'],route.HOST_ONLY)
            gate.write(collected/'manifest.json',dict(manifest,validation_route=dict(route.FULL)))
            with self.assertRaises(AssertionError):gate.verify_collected(collected,helper.SOURCE)

if __name__=='__main__':unittest.main()
