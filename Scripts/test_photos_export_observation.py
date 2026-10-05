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
        self.assertEqual(source.split('  native-mac-host:',1)[1],expected)
        self.assertIn('branches: [codex/photos-export-observation]',source)
        self.assertIn('CELLULOID_VALIDATION_SCOPE: photos-export-observation',source)
        self.assertIn('group: celluloid-platforms-refs/heads/codex/apple-platforms',source)
        self.assertIn('cancel-in-progress: false',source)
        self.assertEqual(source.count('runs-on: xcode-27'),1)
        self.assertEqual(source.count('timeout-minutes: 45'),1)
        self.assertEqual(source.count('timeout-minutes: 14'),1)
        self.assertIn("'execution_budget_seconds':41*60",source)
        self.assertIn('retention-days: 1',source)
        for forbidden in ['workflow_dispatch:', 'strategy:', 'matrix:', 'run_early_uikit_interop.py','verify_required_interoperability.py','download-artifact','GITHUB_SHA=', 'GITHUB_WORKFLOW_SHA=']:
            self.assertNotIn(forbidden,source)
        for path,digest in [('.github/workflows/apple-platforms.yml','40fe18118e1f3996717354e56d55e167dff29b8fbe87455c832386e9a1c36f91'),('.github/workflows/mac-repair.yml','20b2fa6763be3b0014fb598a68088d9927c65790f30904cc04061a902b751daa')]:
            self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),digest)

    def test_every_literal_job_command_parses(self):
        blocks=list(run_blocks((ROOT/route.HOST_ONLY['workflow_path']).read_text()));self.assertGreaterEqual(len(blocks),10)
        for line,body in blocks:
            with self.subTest(line=line):
                result=subprocess.run(['bash','-n'],input=body,text=True,capture_output=True,timeout=5)
                self.assertEqual(result.returncode,0,result.stderr)

    def test_protected_bytes_and_report_distinguish_prior_proof_from_new_execution(self):
        import verify_combined_source as verify
        contract=json.loads((ROOT/'Scripts/combined-source-contract.json').read_text())
        self.assertEqual(contract['fingerprint'],route.HOST_ONLY_BASE['fingerprint'])
        self.assertEqual(len(contract['files']),547)
        for path,digest in contract['files']:self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),digest)
        source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        with tempfile.TemporaryDirectory() as folder,mock.patch.dict(os.environ,dict(environment(source),RUNNER_TEMP=folder)),mock.patch('sys.argv',['verify_combined_source.py','--phase','before']):
            verify.main();report=json.loads((Path(folder)/'combined-source-before.json').read_text())
            self.assertEqual(report['source_sha'],source)
            self.assertFalse(report['host_only_diagnostic']['native_42_reexecuted'])
            self.assertFalse(report['host_only_diagnostic']['uikit_reexecuted'])
            self.assertEqual(report['host_only_diagnostic']['prior_source'],route.HOST_ONLY_BASE)
            with mock.patch.dict(verify.HOST_ONLY_BASE,{'fingerprint':'0'*64}),self.assertRaises(ValueError):verify.main()

    def test_actual_host_receipts_and_collected_replay_bind_the_new_route(self):
        import test_mac_photos_host_gate as fixture
        helper=fixture.RuntimeAcceptanceTests();helper.setUp();self.addCleanup(helper.doCleanups);gate=fixture.gate
        collector=fixture.CollectedProofTests()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();helper.seed(root)
            context=gate.read_receipt(root/'mac-host-context.json');context.update(validation_route=dict(route.HOST_ONLY),runner_environment=environment(helper.SOURCE));gate.write(root/'mac-host-context.json',context)
            for name in ['mac-host-source-before.json','mac-host-source-after.json','combined-source-before.json','combined-source-after.json']:
                value=gate.read_receipt(root/name);value.update(validation_route=dict(route.HOST_ONLY),workflow_sha256=gate.sha(ROOT/route.HOST_ONLY['workflow_path']));gate.write(root/name,value)
            path=root/'mac-host-observed/lifecycle.json';value=gate.read_receipt(path);value['context_sha256']=gate.sha(root/'mac-host-context.json');path.write_text(json.dumps(value,separators=(',',':'))+'\n')
            helper.write_transport_log(root,context)
            result=gate.verify_acceptance(root,helper.SOURCE);self.assertTrue(result['prerequisite_accepted']);self.assertFalse(result['complete_host_e2e'])
            self.assertEqual(result['validation_route'],route.HOST_ONLY);gate.write(root/'mac-host-acceptance.json',result)
            collected=collector.collect(root);manifest=gate.verify_collected(collected,helper.SOURCE);self.assertEqual(manifest['validation_route'],route.HOST_ONLY)
            gate.write(collected/'manifest.json',dict(manifest,validation_route=dict(route.FULL)))
            with self.assertRaises(AssertionError):gate.verify_collected(collected,helper.SOURCE)

if __name__=='__main__':unittest.main()
