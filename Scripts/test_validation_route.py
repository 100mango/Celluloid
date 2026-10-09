"""Focused Mac execution preserves canonical full acceptance and exact route identity."""
import copy,hashlib,json,os,re,tempfile,unittest
from pathlib import Path
import validation_route as route

ROOT=Path(__file__).resolve().parents[1]
CANONICAL_SHA256='40fe18118e1f3996717354e56d55e167dff29b8fbe87455c832386e9a1c36f91'

def focused_environment():
    return {'GITHUB_REF':'refs/heads/codex/mac-repair','GITHUB_REPOSITORY':'100mango/Celluloid',
        'GITHUB_EVENT_NAME':'push','CELLULOID_VALIDATION_SCOPE':'mac-repair',
        'GITHUB_WORKFLOW_REF':'100mango/Celluloid/.github/workflows/mac-repair.yml@refs/heads/codex/mac-repair',
        'GITHUB_SHA':'a'*40,'GITHUB_WORKFLOW_SHA':'a'*40}

class ValidationRouteTests(unittest.TestCase):
    def test_only_exact_focused_branch_workflow_source_and_scope_select(self):
        env=focused_environment();original=dict(env)
        self.assertEqual(route.current_route(env),route.FOCUSED);self.assertEqual(env,original)
        for key,value in [('GITHUB_REF','refs/heads/arbitrary'),('GITHUB_REPOSITORY','someone/Celluloid'),
                          ('GITHUB_EVENT_NAME','pull_request'),('CELLULOID_VALIDATION_SCOPE','full'),
                          ('GITHUB_WORKFLOW_REF','100mango/Celluloid/.github/workflows/apple-platforms.yml@refs/heads/codex/mac-repair'),
                          ('GITHUB_WORKFLOW_SHA','b'*40),('GITHUB_SHA','')]:
            with self.subTest(key=key),self.assertRaises(ValueError):route.current_route(dict(env,**{key:value}))
        for source in [True,1,'x'*40,'a'*39,'A'*40]:
            with self.subTest(source=source),self.assertRaises(ValueError):
                route.current_route(dict(env,GITHUB_SHA=source,GITHUB_WORKFLOW_SHA=source))
        for key in env:
            candidate=dict(env);candidate.pop(key)
            with self.subTest(missing=key),self.assertRaises(ValueError):route.current_route(candidate)

    def test_canonical_route_and_workflow_are_unchanged_and_cannot_be_relabelled(self):
        env=focused_environment();env['GITHUB_REF']='refs/heads/codex/apple-platforms'
        self.assertEqual(route.current_route(env),route.FULL)
        canonical=ROOT/'.github/workflows/apple-platforms.yml'
        self.assertEqual(hashlib.sha256(canonical.read_bytes()).hexdigest(),CANONICAL_SHA256)
        for change in [lambda r:r.update(diagnostic_only=1),lambda r:r.update(scope='full'),
                       lambda r:r.update(workflow_path='../../other'),lambda r:r.update(extra=True)]:
            candidate=dict(route.FOCUSED);change(candidate)
            with self.assertRaises(ValueError):route.validate_route(candidate)

    def test_focused_workflow_is_serial_bounded_and_keeps_real_native_host_gates(self):
        text=(ROOT/route.FOCUSED['workflow_path']).read_text()
        self.assertEqual(re.findall(r'^  ([a-z-]+):$',text.split('jobs:\n',1)[1],re.M),['build-preflight','native-mac','native-mac-host'])
        self.assertIn('branches: [codex/mac-repair]',text)
        self.assertIn('group: celluloid-platforms-refs/heads/codex/apple-platforms',text)
        self.assertIn('cancel-in-progress: false',text)
        self.assertIn('CELLULOID_VALIDATION_SCOPE: mac-repair',text)
        self.assertIn('python3 -m unittest discover',text)
        self.assertIn('python3 Scripts/run_combined_preflight.py --mac-repair',text)
        self.assertIn('verify_required_interoperability.py mac --platform-contract',text)
        self.assertIn('needs: [build-preflight, native-mac]',text)
        self.assertIn('if: always() && needs.build-preflight.result',text)
        self.assertIn('timeout-minutes: 14',text)
        self.assertEqual(text.count('timeout-minutes: 45'),2)
        self.assertEqual(text.count('retention-days: 1'),3)
        for forbidden in ['run_early_uikit_interop.py','early_interop.outputs','native-simulator:', 'uikit-regression:', 'archive:', 'workflow_dispatch:',
                          'name: Native Mac UI launch and editing', 'name: External sandbox document UI and container runtime']:
            self.assertNotIn(forbidden,text)
        inventory=(ROOT/'Scripts/verify_required_interoperability.py').read_text()
        self.assertIn('if cases != list(MAC_REQUIRED_CASES):',inventory)
        from verify_required_interoperability import required, MAC_REQUIRED_CASES
        actual = required('mac')['CelluloidMacPhotosExtensionTests']
        self.assertEqual(actual, list(MAC_REQUIRED_CASES))
        self.assertEqual(len(actual), 43)
        self.assertIn("-scheme CelluloidMac -destination 'platform=macOS'",text)
        scope=(ROOT/'Documentation/mac-photos-host-gate.md').read_text()
        self.assertIn('not full Mac qualification',scope)
        self.assertIn('`Native Mac UI launch and editing`',scope)
        self.assertIn('`External sandbox document UI and container runtime`',scope)
        canonical=(ROOT/route.FULL['workflow_path']).read_text()
        # The complete actual Photos sequence is unchanged except artifact name.
        old=canonical.split('  native-mac-host:',1)[1].split('  native-simulator:',1)[0]
        new=text.split('  native-mac-host:',1)[1]
        self.assertEqual(new.replace('name: celluloid-repair-mac-host-','name: celluloid-mac-host-'),old)

    def seed_focused(self,helper,gate,root):
        helper.seed(root)
        context=gate.read_receipt(root/'mac-host-context.json')
        context.update(validation_route=dict(route.FOCUSED),runner_environment=focused_environment())
        gate.write(root/'mac-host-context.json',context)
        for name in ['mac-host-source-before.json','mac-host-source-after.json','combined-source-before.json','combined-source-after.json']:
            value=gate.read_receipt(root/name);value.update(validation_route=dict(route.FOCUSED),workflow_sha256=gate.sha(ROOT/route.FOCUSED['workflow_path']));gate.write(root/name,value)
        lifecycle_path=root/'mac-host-observed/lifecycle.json'
        lifecycle=gate.read_receipt(lifecycle_path);lifecycle['context_sha256']=gate.sha(root/'mac-host-context.json')
        lifecycle_path.write_text(json.dumps(lifecycle,separators=(',',':'))+'\n')
        helper.write_transport_log(root,context)
        return context

    def test_focused_collected_manifest_cannot_relabel_route_or_claim_full_completion(self):
        import test_mac_photos_host_gate as fixture
        helper=fixture.RuntimeAcceptanceTests();helper.setUp();self.addCleanup(helper.doCleanups);gate=fixture.gate
        collector=fixture.CollectedProofTests()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();self.seed_focused(helper,gate,root)
            gate.write(root/'mac-host-acceptance.json',gate.verify_acceptance(root,helper.SOURCE))
            collected=collector.collect(root);manifest=gate.verify_collected(collected,helper.SOURCE)
            self.assertEqual(manifest['validation_route'],route.FOCUSED)
            self.assertFalse(manifest['complete_host_e2e'])
            for updates in [{'validation_route':dict(route.FULL)},{'complete_host_e2e':True}]:
                gate.write(collected/'manifest.json',dict(manifest,**updates))
                with self.assertRaises(AssertionError):gate.verify_collected(collected,helper.SOURCE)
            gate.write(collected/'manifest.json',manifest)
            collector.update_file(collected,'mac-host-acceptance.json',lambda status:status.update(validation_route=dict(route.FULL)))
            with self.assertRaises(AssertionError):gate.verify_collected(collected,helper.SOURCE)

    def test_focused_host_receipts_replay_as_diagnostic_and_reject_route_laundering(self):
        import test_mac_photos_host_gate as fixture
        helper=fixture.RuntimeAcceptanceTests();helper.setUp();self.addCleanup(helper.doCleanups);gate=fixture.gate
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();context=self.seed_focused(helper,gate,root)
            result=gate.verify_acceptance(root,helper.SOURCE)
            self.assertTrue(result['prerequisite_accepted']);self.assertTrue(result['validation_route']['diagnostic_only']);self.assertFalse(result['complete_host_e2e'])
            for path in ['mac-host-source-before.json','combined-source-after.json']:
                original=gate.read_receipt(root/path);changed=dict(original,validation_route=dict(route.FULL));gate.write(root/path,changed)
                with self.assertRaises(AssertionError):gate.verify_acceptance(root,helper.SOURCE)
                gate.write(root/path,original)
            original=copy.deepcopy(context)
            context['runner_environment'].update(GITHUB_SHA='b'*40,GITHUB_WORKFLOW_SHA='b'*40)
            gate.write(root/'mac-host-context.json',context);helper.write_transport_log(root,context)
            with self.assertRaisesRegex(AssertionError,'Focused runner source differs'):gate.verify_acceptance(root,helper.SOURCE)
            context=copy.deepcopy(original);context['validation_route']=dict(route.FULL);gate.write(root/'mac-host-context.json',context);helper.write_transport_log(root,context)
            with self.assertRaises(AssertionError):gate.verify_acceptance(root,helper.SOURCE)
            gate.write(root/'mac-host-context.json',original);helper.write_transport_log(root,original)
            path=root/'mac-host-source-before.json';value=gate.read_receipt(path);value['workflow_sha256']=CANONICAL_SHA256;gate.write(path,value)
            with self.assertRaises(AssertionError):gate.verify_acceptance(root,helper.SOURCE)

if __name__=='__main__':unittest.main()
