"""Focused Mac execution preserves canonical full acceptance and exact route identity."""
import copy,hashlib,json,os,re,tempfile,unittest
from pathlib import Path
import validation_route as route

ROOT=Path(__file__).resolve().parents[1]
CANONICAL_SHA256='40fe18118e1f3996717354e56d55e167dff29b8fbe87455c832386e9a1c36f91'

# Exact reviewed live-branch naming delta. These historical hashes still identify
# their original workflow bytes; only the pinned renamed files may project back.
REVIEWED_NAMING_WORKFLOWS = {'.github/workflows/apple-platforms.yml': {'current_sha256': '7b9cc75504d637d766c0fab1180677736a90121b299f356f405266d7a13216e6',
                                           'historical_sha256': '40fe18118e1f3996717354e56d55e167dff29b8fbe87455c832386e9a1c36f91',
                                           'line_replacements': [['    branches: '
                                                                  '[codex/apple-platforms]\n',
                                                                  '    branches: '
                                                                  '[apple-platforms]\n',
                                                                  1],
                                                                 ['        test "$GITHUB_REF" = '
                                                                  'refs/heads/codex/apple-platforms\n',
                                                                  '        test "$GITHUB_REF" = '
                                                                  'refs/heads/apple-platforms\n',
                                                                  2]]},
 '.github/workflows/ios-cancellation-matrix.yml': {'current_sha256': '6c89d6f2c65b0c852b997d4c53293113464e05e222b544c69f4dbca2de664a84',
                                                   'historical_sha256': '15235d24c052df4f29f282d5221f6c49d306f97e3a6fc917138bd58a75e00ec9',
                                                   'line_replacements': [['    - '
                                                                          'codex/ios-preservation-qualified\n',
                                                                          '    - '
                                                                          'ios-preservation-qualified\n',
                                                                          1],
                                                                         ['        test '
                                                                          '"$GITHUB_REF" = '
                                                                          'refs/heads/codex/ios-preservation-qualified\n',
                                                                          '        test '
                                                                          '"$GITHUB_REF" = '
                                                                          'refs/heads/ios-preservation-qualified\n',
                                                                          2]]},
 '.github/workflows/ios-extension-cancellation.yml': {'current_sha256': 'ecb8679c6780d01889a448d9146900661fcdecb810108ee493fc55eb73f3aa1d',
                                                      'historical_sha256': '00cb57905f2383f9670c8b428b1f6dfee95a37dfc319b91e097e4c78a83ef034',
                                                      'line_replacements': [['    - '
                                                                             'codex/ios-extension-cancellation\n',
                                                                             '    - '
                                                                             'ios-extension-cancellation\n',
                                                                             1],
                                                                            ['        test '
                                                                             '"$GITHUB_REF" = '
                                                                             'refs/heads/codex/ios-extension-cancellation\n',
                                                                             '        test '
                                                                             '"$GITHUB_REF" = '
                                                                             'refs/heads/ios-extension-cancellation\n',
                                                                             1]]},
 '.github/workflows/ios.yml': {'current_sha256': '08f1244d4acdd415e15dbfc1c9a4f54c507323944638b8fbe73a7988a6ff80d9',
                               'historical_sha256': '98efe168aded6a08e65efffbac0101d03dcb50b016dfa53f34e17a075d681aaa',
                               'line_replacements': [['    - codex/ios-modernization\n',
                                                      '    - ios-modernization\n',
                                                      1],
                                                     ['        test "$GITHUB_REF" = '
                                                      'refs/heads/codex/ios-modernization\n',
                                                      '        test "$GITHUB_REF" = '
                                                      'refs/heads/ios-modernization\n',
                                                      2]]},
 '.github/workflows/mac-repair.yml': {'current_sha256': '1f6cf90e7609ed1627df856a4f42d5d3ef83a3a1c1088b1ecf4629dbbc697404',
                                      'historical_sha256': '20b2fa6763be3b0014fb598a68088d9927c65790f30904cc04061a902b751daa',
                                      'line_replacements': [['    branches: [codex/mac-repair]\n',
                                                             '    branches: [mac-repair]\n',
                                                             1],
                                                            ['  group: '
                                                             'celluloid-platforms-refs/heads/codex/apple-platforms\n',
                                                             '  group: '
                                                             'celluloid-platforms-refs/heads/apple-platforms\n',
                                                             1]]},
 '.github/workflows/original-ios-release.yml': {'current_sha256': 'c03f507f5064c445aed856b14f919f473c2b60a0b2d1e044277cf876bc1b3045',
                                                'historical_sha256': 'af4699ba3214d2cb3a10ab62c116b45a171644cae49f332b1c170cbe98a508e4',
                                                'line_replacements': [['    - '
                                                                       'codex/original-ios-release\n',
                                                                       '    - '
                                                                       'original-ios-release\n',
                                                                       1],
                                                                      ['  group: '
                                                                       'celluloid-platforms-refs/heads/codex/apple-platforms\n',
                                                                       '  group: '
                                                                       'celluloid-platforms-refs/heads/apple-platforms\n',
                                                                       1]]},
 '.github/workflows/photos-export-observation.yml': {'current_sha256': '9067e52a2982c0ef1bd97f4f50ea1084af834ac9fdc610484cc0bdf7fc19de1d',
                                                     'historical_sha256': 'c2305c118f4cfc2551df7c1e4ef36f41298706a94667d24683f1d2c7c252ea12',
                                                     'line_replacements': [['    branches: '
                                                                            '[codex/photos-export-observation]\n',
                                                                            '    branches: '
                                                                            '[photos-export-observation]\n',
                                                                            1],
                                                                           ['  group: '
                                                                            'celluloid-platforms-refs/heads/codex/apple-platforms\n',
                                                                            '  group: '
                                                                            'celluloid-platforms-refs/heads/apple-platforms\n',
                                                                            1]]},
 '.github/workflows/uikit-full-shipping.yml': {'current_sha256': 'bc272f45eb2c68138efae581eb07ce1f3408acd4101f1c372bcfecb829e12323',
                                               'historical_sha256': 'b79b143e6f9944acfbf4539d2b10a385d1fe52e1f27233a7be7d8c32eb1ace00',
                                               'line_replacements': [['    - '
                                                                      'codex/uikit-full-shipping\n',
                                                                      '    - uikit-full-shipping\n',
                                                                      1],
                                                                     ['  group: '
                                                                      'celluloid-platforms-refs/heads/codex/apple-platforms\n',
                                                                      '  group: '
                                                                      'celluloid-platforms-refs/heads/apple-platforms\n',
                                                                      1],
                                                                     ['        test "$GITHUB_REF" '
                                                                      '= '
                                                                      'refs/heads/codex/uikit-full-shipping\n',
                                                                      '        test "$GITHUB_REF" '
                                                                      '= '
                                                                      'refs/heads/uikit-full-shipping\n',
                                                                      1]]}}

def reviewed_workflow_projection(name, raw):
    specification = REVIEWED_NAMING_WORKFLOWS.get(name)
    if specification is None:
        return raw
    if hashlib.sha256(raw).hexdigest() != specification['current_sha256']:
        raise ValueError('Unreviewed workflow bytes outside exact naming delta: ' + name)
    projected = raw
    for old, new, count in specification['line_replacements']:
        old, new = old.encode(), new.encode()
        if projected.count(new) != count:
            raise ValueError('Changed exact naming replacement count: ' + name)
        projected = projected.replace(new, old)
    if hashlib.sha256(projected).hexdigest() != specification['historical_sha256']:
        raise ValueError('Naming projection changed original workflow meaning: ' + name)
    return projected


def focused_environment():
    return {'GITHUB_REF':'refs/heads/mac-repair','GITHUB_REPOSITORY':'100mango/Celluloid',
        'GITHUB_EVENT_NAME':'push','CELLULOID_VALIDATION_SCOPE':'mac-repair',
        'GITHUB_WORKFLOW_REF':'100mango/Celluloid/.github/workflows/mac-repair.yml@refs/heads/mac-repair',
        'GITHUB_SHA':'a'*40,'GITHUB_WORKFLOW_SHA':'a'*40}

class ValidationRouteTests(unittest.TestCase):
    def test_exact_naming_projection_keeps_historical_hashes_and_rejects_other_edits(self):
        for name, specification in REVIEWED_NAMING_WORKFLOWS.items():
            current = (ROOT / name).read_bytes()
            original = reviewed_workflow_projection(name, current)
            self.assertEqual(hashlib.sha256(original).hexdigest(), specification['historical_sha256'])
            self.assertNotEqual(current, original)
            for changed in [current + b'\n', current.replace(b'timeout-minutes:', b'timeout-minutes: 999 #', 1), original]:
                with self.subTest(name=name), self.assertRaises(ValueError):
                    reviewed_workflow_projection(name, changed)

    def test_exact_renamed_triggers_keep_dedicated_qualification_branches_isolated(self):
        import yaml
        expected = {'apple-platforms':'apple-platforms', 'ios-cancellation-matrix':'ios-preservation-qualified',
                    'ios-extension-cancellation':'ios-extension-cancellation', 'ios':'ios-modernization',
                    'mac-repair':'mac-repair', 'original-ios-release':'original-ios-release',
                    'photos-export-observation':'photos-export-observation', 'uikit-full-shipping':'uikit-full-shipping'}
        excluded = {'celluloid-release-preparation', 'celluloid-rendering-qualification',
                    'celluloid-platform-qualification', 'celluloid-platform-qualification-coherent'}
        groups = {}
        for workflow, branch in expected.items():
            value = yaml.safe_load((ROOT / ('.github/workflows/' + workflow + '.yml')).read_text())
            events = value.get('on', value.get(True))
            self.assertEqual(events['push']['branches'], [branch])
            self.assertTrue(excluded.isdisjoint(events['push']['branches']))
            self.assertFalse(value['concurrency']['cancel-in-progress'])
            groups[workflow] = value['concurrency']['group'].replace('${{ github.ref }}', 'refs/heads/' + branch)
        shared = {'apple-platforms','mac-repair','photos-export-observation','uikit-full-shipping','original-ios-release'}
        self.assertEqual({groups[name] for name in shared}, {'celluloid-platforms-refs/heads/apple-platforms'})

    def test_live_routes_reject_stale_prefix_and_historical_route_laundering(self):
        for selected in [route.FULL, route.FOCUSED, route.HOST_ONLY, route.UIKIT_FULL, route.ORIGINAL_IOS]:
            ref = 'refs/heads/' + selected['branch']
            env = {'GITHUB_REF':ref, 'GITHUB_REPOSITORY':route.REPOSITORY, 'GITHUB_EVENT_NAME':'push',
                   'CELLULOID_VALIDATION_SCOPE':selected['scope'], 'GITHUB_SHA':'a'*40, 'GITHUB_WORKFLOW_SHA':'a'*40,
                   'GITHUB_WORKFLOW_REF':route.REPOSITORY+'/'+selected['workflow_path']+'@'+ref}
            self.assertEqual(route.current_route(env), selected)
            old = dict(env, GITHUB_REF='refs/heads/codex/'+selected['branch'])
            old['GITHUB_WORKFLOW_REF'] = route.REPOSITORY+'/'+selected['workflow_path']+'@'+old['GITHUB_REF']
            with self.assertRaises(ValueError):route.current_route(old)
            with self.assertRaises(ValueError):route.validate_route(dict(selected, branch='codex/'+selected['branch']))

    def test_only_exact_focused_branch_workflow_source_and_scope_select(self):
        env=focused_environment();original=dict(env)
        self.assertEqual(route.current_route(env),route.FOCUSED);self.assertEqual(env,original)
        for key,value in [('GITHUB_REF','refs/heads/arbitrary'),('GITHUB_REPOSITORY','someone/Celluloid'),
                          ('GITHUB_EVENT_NAME','pull_request'),('CELLULOID_VALIDATION_SCOPE','full'),
                          ('GITHUB_WORKFLOW_REF','100mango/Celluloid/.github/workflows/apple-platforms.yml@refs/heads/mac-repair'),
                          ('GITHUB_WORKFLOW_SHA','b'*40),('GITHUB_SHA','')]:
            with self.subTest(key=key),self.assertRaises(ValueError):route.current_route(dict(env,**{key:value}))
        for source in [True,1,'x'*40,'a'*39,'A'*40]:
            with self.subTest(source=source),self.assertRaises(ValueError):
                route.current_route(dict(env,GITHUB_SHA=source,GITHUB_WORKFLOW_SHA=source))
        for key in env:
            candidate=dict(env);candidate.pop(key)
            with self.subTest(missing=key),self.assertRaises(ValueError):route.current_route(candidate)

    def test_canonical_route_and_workflow_are_unchanged_and_cannot_be_relabelled(self):
        env=focused_environment();env['GITHUB_REF']='refs/heads/apple-platforms'
        self.assertEqual(route.current_route(env),route.FULL)
        canonical=ROOT/'.github/workflows/apple-platforms.yml'
        self.assertEqual(hashlib.sha256(reviewed_workflow_projection(".github/workflows/apple-platforms.yml",canonical.read_bytes())).hexdigest(),CANONICAL_SHA256)
        for change in [lambda r:r.update(diagnostic_only=1),lambda r:r.update(scope='full'),
                       lambda r:r.update(workflow_path='../../other'),lambda r:r.update(extra=True)]:
            candidate=dict(route.FOCUSED);change(candidate)
            with self.assertRaises(ValueError):route.validate_route(candidate)

    def test_focused_workflow_is_serial_bounded_and_keeps_real_native_host_gates(self):
        text=(ROOT/route.FOCUSED['workflow_path']).read_text()
        self.assertEqual(re.findall(r'^  ([a-z-]+):$',text.split('jobs:\n',1)[1],re.M),['build-preflight','native-mac','native-mac-host'])
        self.assertIn('branches: [mac-repair]',text)
        self.assertIn('group: celluloid-platforms-refs/heads/apple-platforms',text)
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
