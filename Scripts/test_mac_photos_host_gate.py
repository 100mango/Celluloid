#!/usr/bin/env python3
"""Portable gate contract tests. These cannot execute Apple Photos or Swift/XCUI."""
from pathlib import Path
from unittest import mock
import hashlib
import base64
import struct
import zlib
import importlib.util
import json
import os
import runpy
import subprocess
import sys
import tempfile
import unittest
import re

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('gate', ROOT / 'Scripts/mac_photos_host_gate.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

class MacPhotosHostGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (ROOT / '.github/workflows/apple-platforms.yml').read_text()
        cls.swift = (ROOT / 'Platforms/UITests/MacPhotosHostUITests.swift').read_text()
        cls.shell = (ROOT / 'Scripts/run_mac_photos_host_gate.sh').read_text()

    def test_production_and_all_existing_test_bytes_remain_frozen(self):
        contract = json.loads((ROOT / 'Scripts/mac-photos-host-source-base.json').read_text())
        self.assertEqual(len(contract['files']), gate.BASE_FILE_COUNT)
        count = 0
        for path, digest in contract['files']:
            if path in {'CelluloidNative.xcodeproj/project.pbxproj', 'Platforms/UITests/NativeEditorUITests.swift'}: continue
            if path in gate.REVIEWED_CANDIDATE_FILES:
                self.assertEqual(gate.sha(ROOT/path),gate.REVIEWED_CANDIDATE_FILES[path]);continue
            if path in gate.REVIEWED_TEST_FILES:
                self.assertEqual(gate.sha(ROOT/path),gate.REVIEWED_TEST_FILES[path]);continue
            self.assertEqual(gate.sha(ROOT / path), digest, path)
            count += 1
        self.assertEqual(count, gate.UNCHANGED_BASE_FILES)

    def test_generated_project_adds_only_opt_in_ui_source(self):
        previous = (ROOT / 'CelluloidNative.xcodeproj/project.pbxproj').read_bytes()
        graph = runpy.run_path(str(ROOT / 'Scripts/generate_native_project.py'))
        self.assertEqual((ROOT / 'CelluloidNative.xcodeproj/project.pbxproj').read_bytes(), previous)
        objects = graph['objects']
        members = []
        for name, identifier in graph['targets'].items():
            for phase in objects[identifier]['buildPhases']:
                if objects[phase]['isa'] == 'PBXSourcesBuildPhase':
                    paths = [objects[objects[f]['fileRef']]['path'] for f in objects[phase]['files']]
                    if 'Platforms/UITests/MacPhotosHostUITests.swift' in paths: members.append(name)
        self.assertEqual(members, ['CelluloidMacUITests'])

    def test_existing_serial_workflow_and_independent_host_prerequisite(self):
        self.assertIn('    branches: [' + gate.BRANCH + ']', self.workflow)
        self.assertEqual(re.findall(r'^  ([a-z-]+):$',self.workflow.split('jobs:\n',1)[1],re.M), ['build-preflight','native-mac','native-mac-host','native-simulator','uikit-regression','archive'])
        host=self.workflow.split('- name: Actual Photos host discovery',1)[1].split('- name:',1)[0]
        self.assertIn("steps.sandbox_child.outcome == 'success'",host)
        self.assertNotIn('early_interop',host)
        self.assertIn('  cancel-in-progress: false',self.workflow)
        self.assertEqual(self.workflow.count('max-parallel: 1'),2)
    def test_mac_checkout_fetches_immutable_base_without_deepening_current_head(self):
        mac=self.workflow.split('  native-mac-host:',1)[1].split('  native-simulator:',1)[0]
        self.assertEqual(mac.count('fetch-depth: 1'),1)
        fetch=mac.split('- name: Fetch and verify immutable Photos host source base',1)[1].split('- name:',1)[0]
        self.assertIn("base='"+gate.BASE+"'",fetch);self.assertIn("tree='"+gate.BASE_TREE+"'",fetch)
        self.assertIn("run(['git','fetch','--no-tags','--depth=1','origin',base],timeout=60)",fetch)
        self.assertIn("base+'^{commit}'],text=True,timeout=10).strip()==base",fetch)
        self.assertIn("base+'^{tree}'],text=True,timeout=10).strip()==tree",fetch)
        self.assertIn('from native_process import run',fetch)
        for forbidden in ['token','credential','git config','--unshallow']:self.assertNotIn(forbidden,fetch)
        # Fetch one immutable object in a tiny local shallow clone. The checked
        #out head remains unchanged and shallow regardless of ancestor distance.
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();seed=root/'seed';seed.mkdir()
            def git(*args):return subprocess.check_output(['git',*map(str,args)],text=True,stderr=subprocess.STDOUT,timeout=10)
            git('init','--quiet',seed);commits=[]
            for content in ['pinned-base','intermediate','published-parent','test-fix-successor']:
                (seed/'fixture.txt').write_text(content);git('-C',seed,'add','fixture.txt')
                git('-C',seed,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','--quiet','-m',content)
                commits.append(git('-C',seed,'rev-parse','HEAD').strip())
            clone=root/'shallow';git('clone','--quiet','--depth','1',seed.as_uri(),clone)
            absent=subprocess.run(['git','-C',str(clone),'cat-file','-e',commits[0]+'^{commit}'],capture_output=True,text=True,timeout=10)
            self.assertNotEqual(absent.returncode,0)
            git('-C',clone,'fetch','--no-tags','--depth=1','origin',commits[0])
            self.assertEqual(git('-C',clone,'rev-parse',commits[0]+'^{commit}').strip(),commits[0])
            self.assertEqual(git('-C',clone,'rev-parse',commits[0]+'^{tree}'),git('-C',seed,'rev-parse',commits[0]+'^{tree}'))
            self.assertEqual(git('-C',clone,'rev-parse','HEAD').strip(),commits[-1]);self.assertEqual(git('-C',clone,'rev-list','--count','HEAD').strip(),'1')

    def test_fresh_host_row_rebuilds_exact_product_without_pixel_or_seed_dependency(self):
        host=self.workflow.split('  native-mac-host:',1)[1].split('  native-simulator:',1)[0]
        mac=self.workflow.split('  native-mac:',1)[1].split('  native-mac-host:',1)[0]
        sim=self.workflow.split('  native-simulator:',1)[1].split('  uikit-regression:',1)[0]
        self.assertIn('needs: [build-preflight, native-mac]',host)
        self.assertIn("if: always() && needs.build-preflight.result == 'success'",host)
        self.assertNotIn('continuation_safe',host)
        self.assertIn('needs: [build-preflight, native-mac, native-mac-host]',sim)
        self.assertNotIn('needs.native-mac-host.result',sim)
        self.assertNotIn('run_mac_photos_host_gate.sh',mac)
        self.assertNotIn('download-artifact',host)
        self.assertNotIn('TEST_RUNNER_CELLULOID_HOST_SEED_SOURCE_SHA',host)
        self.assertIn('--seconds 600 --label fresh-host-ui-build',host)
        self.assertIn('--seconds 300 --label fresh-host-app-build',host)
        self.assertIn('CODE_SIGN_IDENTITY=-',host)
        self.assertIn("'execution_budget_seconds':41*60",host)
        self.assertEqual(host.count('verify_combined_source.py --phase'),2)
        self.assertLess(host.index('verify_combined_source.py --phase after'),host.index('mac_photos_host_gate.py accept'))
        self.assertEqual(host.count('retention-days: 1'),1)

    def test_existing_runtime_and_caps_reuse_compiled_product(self):
        self.assertIn('    timeout-minutes: 45',self.workflow)
        self.assertIn('        timeout-minutes: 14',self.workflow)
        self.assertIn('--seconds 720',self.shell)
        self.assertNotIn('build-for-testing',self.shell)
        self.assertNotIn('CODE_SIGN_IDENTITY',self.shell)
        self.assertIn('celluloid-sandbox',self.shell)
    def test_artifacts_share_existing_mac_allocation(self):
        self.assertEqual(self.workflow.count('uses: actions/upload-artifact@'),6)
        self.assertIn('path: ${{ runner.temp }}/mac-host-evidence/',self.workflow)
        self.assertEqual(gate.CAP,1_000_000)
        collector=(ROOT/'Scripts/collect_native_evidence.py').read_text()
        self.assertIn("record=verify_collected(folder,os.environ['GITHUB_SHA'])",collector)
        self.assertIn('independently replayed host proof manifest',collector)
        budgets=runpy.run_path(str(ROOT/'Scripts/combined_evidence_budget.py'))
        self.assertEqual(budgets['BUDGETS']['mac'],2_000_000)
        self.assertEqual(sum(budgets['BUDGETS'].values()),19_500_000)

    def test_unknown_interruptions_abort_without_alert_action(self):
        handler = self.swift.split('addUIInterruptionMonitor', 1)[1].split('let input', 1)[0]
        self.assertIn('fatalError("MAC_HOST_FAIL_CLOSED_ABORT")', handler)
        for forbidden in ['.click(', '.tap(', 'return true', 'return false', 'XCTFail']:
            self.assertNotIn(forbidden, handler)
        self.assertLess(self.swift.index('addUIInterruptionMonitor'), self.swift.index('app.launch()'))

    def test_no_privacy_registration_or_security_override(self):
        for source in [self.swift, self.shell, (ROOT / 'Scripts/mac_photos_host_gate.py').read_text()]:
            for forbidden in ['tccutil', 'spctl', 'sqlite3', 'killall', 'pluginkit -e', 'pluginkit -a', 'xattr -d',
                              'security add', 'security unlock', 'defaults write', 'PHPhotoLibrary.requestAuthorization']:
                self.assertNotIn(forbidden, source)
        self.assertNotIn('coordinate(', self.swift)
        self.assertNotIn('MacPhotoEditingController(', self.swift)

    def test_production_ids_and_live_path_hash_are_both_required(self):
        self.assertEqual(gate.APP_ID, 'Mango.Celluloid')
        self.assertEqual(gate.EXT_ID, 'Mango.Celluloid.CelluloidPhotoExtension')
        self.assertIn('assertUniqueRegistration()', self.swift)
        source = (ROOT / 'Scripts/mac_photos_host_gate.py').read_text()
        self.assertIn('lib.proc_pidpath(pid', source)
        self.assertIn("len(found) == 1 and found[0]['executable'] == expected", source)
        self.assertIn("found[0]['sha256'] == c['extension_executable_sha256']", source)

    def test_bundle_manifest_detects_bytes_membership_and_symlinks(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'binary').write_bytes(b'a'); (root / 'alias').symlink_to('binary')
            first = gate.bundle_manifest(root)
            (root / 'binary').write_bytes(b'b')
            self.assertNotEqual(first, gate.bundle_manifest(root))
            self.assertEqual(first[0], ['alias', 'symlink', 'binary'])
            (root / 'extra').write_bytes(b'c')
            self.assertEqual(len(gate.bundle_manifest(root)), 3)

    def test_collection_stays_bounded_and_excludes_raw_payloads(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, {'RUNNER_TEMP': folder, 'GITHUB_SHA': 'a'*40}):
            root = Path(folder); gate.write(root/'mac-host-acceptance.json', {'source_sha':'a'*40,'prerequisite_accepted':False,'complete_host_e2e':False,'error':'AssertionError: discovery failed'}); observed = root / 'mac-host-observed'; observed.mkdir()
            (observed / 'extensions.jpg').write_bytes(b'a' * 600_000)
            (observed / 'last-observed.jpg').write_bytes(b'b' * 600_000)
            for index in range(22): (observed / f'phase-{index:02d}.txt').write_bytes(b'x' * 140_000)
            (observed / 'oversize.txt').write_bytes(b'x' * 200_000)
            (observed / 'raw.xcresult').mkdir()
            (observed / 'credentials.bin').write_bytes(b'do not collect')
            (observed / 'link.txt').symlink_to('phase-00.txt')
            (root / 'mac-host-test.log').write_text('observed discovery failure\n')
            gate.collect()
            result = root / 'mac-host-evidence'; manifest = json.loads((result / 'manifest.json').read_text())
            self.assertLessEqual(sum(p.stat().st_size for p in result.iterdir()), gate.CAP)
            self.assertTrue(manifest['omitted'])
            self.assertFalse(manifest['complete_host_e2e'])
            self.assertFalse((result / 'credentials.bin').exists())
            self.assertFalse((result / 'raw.xcresult').exists())
            self.assertFalse((result / 'link.txt').exists())
            for entry in manifest['files']:
                self.assertEqual(gate.sha(result / entry['path']), entry['sha256'])

    def test_report_does_not_equate_prerequisite_with_full_lifecycle(self):
        self.assertIn('"prerequisite_passed": true, "complete_host_e2e": false', self.swift)
        self.assertIn('save_reopen_cancel_revert', self.swift)
        self.assertIn('not executed in prerequisite phase', self.swift)
        self.assertIn('try checkpoint(settings, "manage-observed")', self.swift)

    def test_optimized_python_rejects_before_any_action_or_acceptance(self):
        script = str(ROOT / 'Scripts/mac_photos_host_gate.py')
        for flags, inherited in [(['-O'], None), (['-OO'], None), ([], '1')]:
            with self.subTest(flags=flags, inherited=inherited), tempfile.TemporaryDirectory() as folder:
                environment = dict(os.environ, RUNNER_TEMP=folder)
                environment.pop('PYTHONOPTIMIZE', None)
                if inherited is not None: environment['PYTHONOPTIMIZE'] = inherited
                result = subprocess.run([sys.executable, *flags, script, 'accept'], env=environment,
                                        capture_output=True, text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('RuntimeError: Mac Photos host gate refuses optimized Python', result.stderr)
                self.assertNotIn('MAC_HOST_ACCEPTANCE', result.stdout + result.stderr)
                self.assertEqual(list(Path(folder).iterdir()), [])

    def test_python_and_shell_syntax(self):
        compile((ROOT / 'Scripts/mac_photos_host_gate.py').read_text(), 'gate.py', 'exec')
        subprocess.run(['/bin/bash', '-n', str(ROOT / 'Scripts/run_mac_photos_host_gate.sh')], check=True)
        syntax = runpy.run_path(str(ROOT / 'Scripts/test_native_workflow_syntax.py'))
        for _, body in syntax['run_blocks'](self.workflow):
            subprocess.run(['/bin/bash', '-n'], input=body, text=True, check=True)

class SeedReceiptTests(unittest.TestCase):
    def packet(self):
        def chunk(kind,data): return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
        png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1200,800,8,6,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\x20\x80\xe0\xff'*1200)*800))+chunk(b'IEND',b'')
        return {'source_sha':'a'*40,'app_executable_sha256':'b'*64,'initial_empty_welcome_verified':True,
                'imported_pixel_samples_passed':True,'initial_count':0,'imported_count':1,
                'fixture_kind':'native-ui-solid-blue','filename':'Synthetic.png','width':1200,'height':800,
                'asset_label':'Oct 4 synthetic asset','fixture_sha256':hashlib.sha256(png).hexdigest(),
                'fixture_base64':base64.b64encode(png).decode(),'imported_source_sha256':'c'*64}
    def log(self,row):
        owner,method=gate.SEED_CASE
        return "Test Case '-["+owner+' '+method+"]' started.\nMAC_HOST_SEED_RECEIPT "+json.dumps(row)+"\nTest Case '-["+owner+' '+method+"]' passed (1.0 seconds).\n"
    def test_exact_source_app_fixture_and_unique_execution_are_required(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'sandbox.log'; row=self.packet();path.write_text(self.log(row))
            receipt=gate.seed_receipt(path,'a'*40,'b'*64)
            self.assertEqual(receipt['mode'],'reuse-exact-sole-seeded-asset')
            self.assertEqual(receipt['fixture_sha256'],row['fixture_sha256'])
            self.assertEqual(receipt['seed_log_sha256'],gate.sha(path))
    def test_unknown_or_unbound_seed_cannot_select_a_photo(self):
        bad=[{'source_sha':'f'*40},{'app_executable_sha256':'f'*64},{'initial_empty_welcome_verified':False},
             {'initial_count':1},{'initial_count':False},{'imported_count':2},{'imported_count':True},
             {'imported_pixel_samples_passed':False},{'asset_label':''},{'fixture_sha256':'0'*64},
             {'width':1199},{'fixture_kind':'guessed'},{'filename':'other.png'}]
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'sandbox.log'
            for values in bad:
                row=self.packet();row.update(values);path.write_text(self.log(row))
                with self.subTest(values=values),self.assertRaises((AssertionError,ValueError)):gate.seed_receipt(path,'a'*40,'b'*64)
            text=self.log(self.packet())
            for value in [text+text,text.replace(' passed ',' failed '),'\n'.join(l for l in text.splitlines() if not l.startswith('MAC_HOST_SEED_RECEIPT '))]:
                path.write_text(value)
                with self.assertRaises(AssertionError):gate.seed_receipt(path,'a'*40,'b'*64)
    def test_absent_prior_execution_only_admits_observed_empty_library_route(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'absent.log'
            self.assertEqual(gate.seed_receipt(path,'a'*40,'b'*64),{'mode':'require-empty-library'})
            source=(ROOT/'Platforms/UITests/MacPhotosHostUITests.swift').read_text()
            self.assertIn('XCTAssertEqual(empty.value as? String, "Welcome to Photos"',source)
            self.assertIn('XCTAssertEqual(assets.count, 0)',source)
            self.assertIn('XCTAssertEqual(assets.firstMatch.label, seed["asset_label"] as? String)',source)
            self.assertIn('"fixture-ownership.json"',source)
    def test_shared_host_evidence_hashes_are_validated_inside_mac_budget(self):
        collector=(ROOT/'Scripts/collect_native_evidence.py').read_text()
        self.assertIn('from mac_photos_host_gate import verify_collected',collector)
        self.assertIn('record=verify_collected(folder',collector)
        self.assertIn('Required host evidence exceeds shared Mac allocation',collector)

class SyntheticHostFixtureCase(unittest.TestCase):
    """Keep synthetic source receipts separate from the real invoking CI job."""
    SOURCE = 'a' * 40

    def setUp(self):
        super().setUp()
        source_environment = mock.patch.dict(os.environ, GITHUB_SHA=self.SOURCE)
        source_environment.start()
        self.addCleanup(source_environment.stop)


class RuntimeAcceptanceTests(SyntheticHostFixtureCase):
    """Synthetic verifier fixtures only, never evidence of an Apple runtime pass."""
    SOURCE = 'a' * 40

    def seed(self, root):
        root = Path(root).resolve()  # Match real producer receipts across macOS /var -> /private/var.
        observed = root / 'mac-host-observed'
        observed.mkdir()
        app = str(root / 'Applications/CelluloidHost-test.app')
        extension = app + '/Contents/PlugIns/CelluloidMacPhotosExtension.appex'
        executable = extension + '/Contents/MacOS/CelluloidMacPhotosExtension'
        context = {'source_sha': self.SOURCE, 'base_sha': gate.BASE, 'app_path': app,
                   'extension_path': extension, 'extension_executable': executable,
                   'app_id': gate.APP_ID, 'extension_id': gate.EXT_ID, 'complete_host_e2e': False,
                   'script_sha256': gate.sha(gate.__file__), 'test_source_sha256': gate.sha(ROOT/'Platforms/UITests/MacPhotosHostUITests.swift'),
                   'app_executable': app+'/Contents/MacOS/CelluloidMac', 'extension_executable_sha256': 'e' * 64,
                   'app_executable_sha256': 'd' * 64, 'seed': {'mode': 'require-empty-library'}}
        summary = {'result': 'Passed', 'totalTestCount': 1, 'passedTests': 1, 'failedTests': 0,
                   'skippedTests': 0, 'expectedFailures': 0, 'startTime': 10, 'finishTime': 20,
                   'testFailures': [], 'devicesAndConfigurations': [
                       {'passedTests': 1, 'failedTests': 0, 'skippedTests': 0, 'expectedFailures': 0,
                        'device': {'platform': 'macOS', 'osVersion': '27.0'}}]}
        source = {'source_sha': self.SOURCE, 'base_sha': gate.BASE, 'base_tree': gate.BASE_TREE,
                  'unchanged_bound_files': gate.UNCHANGED_BASE_FILES, 'reviewed_diagnostic_test_files': gate.REVIEWED_TEST_FILES, 'reviewed_candidate_files': gate.REVIEWED_CANDIDATE_FILES, 'complete_host_e2e': False, 'tree': 'b' * 40,
                  'workflow_sha256': 'c' * 64}
        clock={'source_sha':self.SOURCE,'started_monotonic':100.0,'started_unix':10000.0,'execution_budget_seconds':gate.JOB_EXECUTION_SECONDS}
        gate.write(root/'mac-job-clock.json',clock)
        checks=[{'phase':phase,'observed_monotonic':now,'deadline_monotonic':2560.0,'remaining_seconds':2560.0-now,'required_seconds':1020,'admitted':True} for phase,now in [('before-prepare',101.0),('before-host',110.0)]]
        documents = {
            'combined-source-before.json': dict(source,phase='before',file_count=len(json.loads((ROOT/'Scripts/combined-source-contract.json').read_text())['files']),source_fingerprint=json.loads((ROOT/'Scripts/combined-source-contract.json').read_text())['fingerprint']),
            'combined-source-after.json': dict(source,phase='after',file_count=len(json.loads((ROOT/'Scripts/combined-source-contract.json').read_text())['files']),source_fingerprint=json.loads((ROOT/'Scripts/combined-source-contract.json').read_text())['fingerprint']),
            'mac-host-budget.json':{'source_sha':self.SOURCE,'checks':checks,'admitted':True,'clock_sha256':gate.sha(root/'mac-job-clock.json'),'host_process_seconds':720,'evidence_reserve_seconds':300,'complete_host_e2e':False},
            'mac-host-observed/fixture.json': {'source_sha': self.SOURCE, 'sha256': 'f' * 64},
            'mac-host-observed/fixture-ownership.json': {'source_sha': self.SOURCE, 'app_executable_sha256': 'd' * 64, 'initial_count': 0, 'selected_count': 1, 'width': 1200, 'height': 800, 'asset_label': 'synthetic sole asset', 'fixture_sha256': 'f' * 64, 'mode': 'require-empty-library'},
            'mac-host-context.json': context, 'mac-host-summary.json': summary,
            'mac-host-product-after.json': {'installed_bytes_unchanged': True, 'strict_signatures_unchanged': True,
                'app_executable_sha256': 'd' * 64, 'extension_executable_sha256': 'e' * 64},
            'mac-host-source-before.json': dict(source, phase='before'),
            'mac-host-source-after.json': dict(source, phase='after'),
            'mac-host-observed/prerequisite.json': {'source_sha': self.SOURCE, 'prerequisite_passed': True,
                'complete_host_e2e': False, 'production_source_base': gate.BASE},
            'mac-host-observed/outcome.json': {'source_sha': self.SOURCE, 'complete_host_e2e': False,
                'last_stage': 'host-entry-prerequisite-passed', 'save_reopen_cancel_revert': 'not executed in prerequisite phase'},
            'mac-host-observed/registration-selected.json': {'source_sha': self.SOURCE, 'extension_id': gate.EXT_ID,
                'expected_extension_path': extension, 'registered_paths': [extension]},
            'mac-host-observed/extension-process.json': {'source_sha': self.SOURCE, 'extension_id': gate.EXT_ID,
                'expected_executable': executable, 'expected_executable_sha256': 'e' * 64,
                'unique_exact_process': True,
                'extension_processes': [{'pid': 123, 'executable': executable, 'sha256': 'e' * 64}]}}
        raw = observed / 'registration-selected.txt'
        raw.write_text('  ' + gate.EXT_ID + '(1.1)\n    ' + extension + '\n')
        documents['mac-host-observed/registration-selected.json']['registration_text_sha256'] = gate.sha(raw)
        for name, data in documents.items(): gate.write(root / name, data)
        from mac_host_transport import ORDER,expected_transport
        gate.write(observed/'transport.json',expected_transport(context,gate.sha(root/'mac-host-context.json')))
        gate.write(observed/'containing-process.json',{'bundle':app,'executable':context['app_executable'],'pid':121})
        gate.write(observed/'photos-process.json',{'bundle':'/System/Applications/Photos.app','executable':'/System/Applications/Photos.app/Contents/MacOS/Photos','pid':122})
        for suffix in ['txt','json']:(observed/('registration-before-invoke.'+suffix)).write_bytes((observed/('registration-selected.'+suffix)).read_bytes())
        RuntimeAcceptanceTests.write_transport_log(self,root,context)
        return documents

    def write_transport_log(self,root,context=None):
        from mac_host_transport import ORDER,SCHEMA,PREFIX,LABEL,expected_transport
        context=context or gate.read_receipt(root/'mac-host-context.json')
        gate.write(root/'mac-host-observed/transport.json',expected_transport(context,gate.sha(root/'mac-host-context.json')))
        owner,method=gate.EXPECTED_CASE
        command=['xcodebuild','-only-testing:'+owner.replace('.', '/')+'/'+method,'test-without-building']
        lines=['BOUNDED_COMMAND_BEGIN '+json.dumps({'label':LABEL,'seconds':720,'command':command}),
            "Test Case '-["+owner+' '+method+"]' started."]
        for index,name in enumerate(ORDER):
            data=(root/'mac-host-observed'/name).read_bytes()
            lines.append(PREFIX+json.dumps({'schema':SCHEMA,'sequence':index,'name':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
                'base64':base64.b64encode(data).decode(),'source_sha':self.SOURCE,'context_sha256':gate.sha(root/'mac-host-context.json'),
                'test_source_sha256':context['test_source_sha256'],'verifier_sha256':context['script_sha256']}))
        lines+=['MAC_HOST_PREREQUISITE_PASSED synthetic verifier fixture',"Test Case '-["+owner+' '+method+"]' passed (1.0 seconds).",
            '** TEST EXECUTE SUCCEEDED **','BOUNDED_COMMAND_END '+json.dumps({'label':LABEL,'exit_code':0,'elapsed_seconds':1})]
        (root/'mac-host-test.log').write_text('\n'.join(lines)+'\n')
        records=gate.transport_records(root,context,complete=True)
        gate.write(root/'mac-host-transport-replay.json',gate.transport_report(root,context,records))

    def check_mutation_rejected(self, mutation):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); self.seed(root); mutation(root)
            with self.assertRaises((AssertionError, ValueError, KeyError, TypeError)):
                gate.verify_acceptance(root, self.SOURCE)

    def edit(self, path, **updates):
        value = json.loads(path.read_text()); value.update(updates); gate.write(path, value)

    def test_complete_consistent_prerequisite_packet_is_accepted_without_e2e_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); self.seed(root)
            accepted = gate.verify_acceptance(root, self.SOURCE)
            self.assertTrue(accepted['prerequisite_accepted'])
            self.assertTrue(accepted['exactly_one_passed_zero_skipped'])
            self.assertFalse(accepted['complete_host_e2e'])
            self.assertEqual(len(accepted['receipts']), 23)

    def test_rehashed_nonfinite_proof_and_timeout_contradictions_reject_at_transport(self):
        from mac_host_transport import PREFIX
        for literal in ['NaN','Infinity','-Infinity','1e999']:
            with self.subTest(literal=literal),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);self.seed(root);path=root/'mac-host-test.log';lines=path.read_text().splitlines()
                for index,line in enumerate(lines):
                    if not line.startswith(PREFIX):continue
                    row=json.loads(line[len(PREFIX):])
                    if row['name']!='prerequisite.json':continue
                    data=base64.b64decode(row['base64']).rstrip();data=data[:-1]+b',"malformed_nonfinite":'+literal.encode()+b'}'
                    row.update(base64=base64.b64encode(data).decode(),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
                    lines[index]=PREFIX+json.dumps(row);(root/'mac-host-observed/prerequisite.json').write_bytes(data)
                path.write_text('\n'.join(lines)+'\n')
                with self.assertRaisesRegex(ValueError,'Nonfinite JSON'):gate.verify_acceptance(root,self.SOURCE)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.seed(root);path=root/'mac-host-test.log'
            path.write_text(path.read_text().replace('** TEST EXECUTE SUCCEEDED **','BOUNDED_COMMAND_TIMEOUT actual-mac-photos-host-prerequisite\n** TEST EXECUTE SUCCEEDED **'))
            with self.assertRaisesRegex(ValueError,'process timeout'):gate.verify_acceptance(root,self.SOURCE)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'receipt.json';path.write_text('{"nested":{"bad":NaN}}')
            with self.assertRaisesRegex(ValueError,'Nonfinite JSON'):gate.read_receipt(path)

    def test_nonfinite_attachment_export_never_publishes_transport_completion(self):
        for literal in ['NaN','Infinity','-Infinity','1e999']:
            with self.subTest(literal=literal),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);self.seed(root);context=gate.read_receipt(root/'mac-host-context.json')
                (root/'mac-host-transport-replay.json').unlink()
                for path in (root/'mac-host-observed').iterdir():path.unlink()
                def export(command,**kwargs):
                    destination=Path(command[command.index('--output-path')+1])
                    (destination/'manifest.json').write_text('[{"attachments":[],"bad":'+literal+'}]')
                    return subprocess.CompletedProcess(command,0,b'',b'')
                with mock.patch.object(gate,'require_runner'),mock.patch.object(gate,'temp',return_value=root),mock.patch.object(gate,'context',return_value=context),mock.patch.object(gate.subprocess,'run',side_effect=export):
                    with self.assertRaisesRegex(ValueError,'Nonfinite JSON'):gate.extract_transport()
                self.assertFalse((root/'mac-host-transport-replay.json').exists())

    def test_explicitly_reviewed_candidate_hashes_cannot_be_removed_or_substituted(self):
        for name in ['mac-host-source-before.json','mac-host-source-after.json']:
            for mapping in [{},{path:'f'*64 for path in gate.REVIEWED_CANDIDATE_FILES}]:
                with self.subTest(name=name,mapping=mapping):
                    self.check_mutation_rejected(lambda root:self.edit(root/name,reviewed_candidate_files=mapping))

    def test_combined_candidate_receipts_cannot_be_stale_or_unbound(self):
        for name in ['combined-source-before.json','combined-source-after.json']:
            for fields in [{'source_sha':'f'*40},{'tree':'f'*40},{'workflow_sha256':'f'*64},{'phase':'wrong'},{'file_count':True},{'file_count':0},{'source_fingerprint':'f'*64}]:
                with self.subTest(name=name,fields=fields):
                    self.check_mutation_rejected(lambda root:self.edit(root/name,**fields))

    def test_synthetic_packet_uses_canonical_paths_through_temporary_directory_alias(self):
        with tempfile.TemporaryDirectory() as folder:
            real=Path(folder)/'real';real.mkdir();alias=Path(folder)/'alias';alias.symlink_to(real,target_is_directory=True)
            self.seed(alias)
            accepted=gate.verify_acceptance(alias,self.SOURCE)
            self.assertTrue(accepted['prerequisite_accepted'])
            registration=gate.read_receipt(alias/'mac-host-observed/registration-selected.json')
            expected=str(real.resolve()/'Applications/CelluloidHost-test.app/Contents/PlugIns/CelluloidMacPhotosExtension.appex')
            self.assertEqual(registration['expected_extension_path'],expected)
            gate.write(alias/'mac-host-acceptance.json',accepted)
            with mock.patch.dict(os.environ,RUNNER_TEMP=str(alias),GITHUB_SHA=self.SOURCE):gate.collect()
            self.assertTrue(gate.verify_collected(alias/'mac-host-evidence',self.SOURCE)['prerequisite_accepted'])
            # Canonicalize only synthetic producer setup; the production verifier
            # must still reject a noncanonical claimed registration receipt.
            registration['expected_extension_path']=str(alias/'Applications/CelluloidHost-test.app/Contents/PlugIns/CelluloidMacPhotosExtension.appex')
            gate.write(alias/'mac-host-observed/registration-selected.json',registration)
            with self.assertRaises(AssertionError):gate.verify_acceptance(alias,self.SOURCE)

    def test_each_missing_mandatory_record_rejects(self):
        paths = ['combined-source-before.json','combined-source-after.json','mac-job-clock.json', 'mac-host-budget.json', 'mac-host-context.json', 'mac-host-summary.json', 'mac-host-test.log',
                 'mac-host-product-after.json', 'mac-host-source-before.json', 'mac-host-source-after.json',
                 'mac-host-observed/prerequisite.json', 'mac-host-observed/outcome.json',
                 'mac-host-observed/registration-selected.json', 'mac-host-observed/registration-selected.txt',
                 'mac-host-observed/extension-process.json', 'mac-host-observed/fixture-ownership.json', 'mac-host-observed/fixture.json']
        for name in paths:
            with self.subTest(missing=name):
                self.check_mutation_rejected(lambda root: (root / name).unlink())

    def test_zero_skipped_duplicate_failed_unfinalized_or_contradictory_summary_rejects(self):
        for update in [{'totalTestCount': 0, 'passedTests': 0}, {'skippedTests': 1, 'passedTests': 0},
                       {'totalTestCount': 2, 'passedTests': 2}, {'failedTests': 1}, {'expectedFailures': 1},
                       {'result': 'Skipped'}, {'finishTime': 10}, {'testFailures': ['failure']},
                       {'passedTests': True}, {'devicesAndConfigurations': []}]:
            with self.subTest(update=update):
                self.check_mutation_rejected(lambda root: self.edit(root / 'mac-host-summary.json', **update))
        def contradict(root):
            path = root / 'mac-host-summary.json'; data = json.loads(path.read_text())
            data['devicesAndConfigurations'][0]['skippedTests'] = 1; gate.write(path, data)
        self.check_mutation_rejected(contradict)

    def test_missing_wrong_duplicate_skipped_or_contradictory_case_output_rejects(self):
        for transform in [lambda log: '', lambda log: log.replace('MacPhotosHostUITests', 'WrongTests'),
                          lambda log: log + log, lambda log: log.replace("' passed", "' skipped"),
                          lambda log: log.replace("' passed", "' failed"),
                          lambda log: log.replace("' started.", "' notstarted."),
                          lambda log: log.replace('MAC_HOST_PREREQUISITE_PASSED', 'NO_MARKER'),
                          lambda log: log + 'MAC_HOST_PREREQUISITE_PASSED duplicate\n',
                          lambda log: log + 'MAC_HOST_BLOCKED late failure\n',
                          lambda log: log + 'MAC_HOST_FAIL_CLOSED_ABORT\n']:
            def mutate(root):
                p = root / 'mac-host-test.log'; p.write_text(transform(p.read_text()))
            self.check_mutation_rejected(mutate)

    def test_wrong_candidate_or_duplicate_json_key_in_any_identity_receipt_rejects(self):
        paths = ['mac-host-context.json', 'mac-host-source-before.json', 'mac-host-source-after.json',
                 'mac-host-observed/prerequisite.json', 'mac-host-observed/outcome.json',
                 'mac-host-observed/registration-selected.json', 'mac-host-observed/extension-process.json', 'mac-host-observed/fixture-ownership.json', 'mac-host-observed/fixture.json']
        for name in paths:
            with self.subTest(wrong_source=name):
                self.check_mutation_rejected(lambda root: self.edit(root / name, source_sha='f' * 40))
            def duplicate(root):
                path = root / name; raw = path.read_text().strip()
                path.write_text(raw[:-1] + ', "source_sha": "' + self.SOURCE + '"}')
            with self.subTest(duplicate_key=name): self.check_mutation_rejected(duplicate)

    def test_false_skipped_stage_or_complete_e2e_receipt_rejects(self):
        for name, updates in [('prerequisite.json', {'prerequisite_passed': False}),
                              ('prerequisite.json', {'prerequisite_passed': 1}),
                              ('prerequisite.json', {'complete_host_e2e': True}),
                              ('prerequisite.json', {'production_source_base': 'wrong'}),
                              ('outcome.json', {'last_stage': 'observe-extensions-menu'}),
                              ('outcome.json', {'complete_host_e2e': True}),
                              ('outcome.json', {'save_reopen_cancel_revert': 'passed'})]:
            with self.subTest(name=name, updates=updates):
                self.check_mutation_rejected(lambda root: self.edit(root / 'mac-host-observed' / name, **updates))

    def test_wrong_missing_duplicate_raw_or_claimed_registration_rejects(self):
        for update in [{'registered_paths': []}, {'registered_paths': ['/wrong.appex']},
                       {'extension_id': 'Other.Extension'}, {'expected_extension_path': '/wrong.appex'},
                       {'registration_text_sha256': '0' * 64}]:
            self.check_mutation_rejected(lambda root: self.edit(root / 'mac-host-observed/registration-selected.json', **update))
        def duplicate_claim(root):
            path = root / 'mac-host-observed/registration-selected.json'; data = json.loads(path.read_text())
            data['registered_paths'] *= 2; gate.write(path, data)
        self.check_mutation_rejected(duplicate_claim)
        def duplicate_raw(root):
            raw = root / 'mac-host-observed/registration-selected.txt'
            raw.write_text(raw.read_text() * 2)
            self.edit(root / 'mac-host-observed/registration-selected.json', registration_text_sha256=gate.sha(raw))
        self.check_mutation_rejected(duplicate_raw)

    def test_wrong_missing_duplicate_or_contradictory_live_process_rejects(self):
        for update in [{'unique_exact_process': False}, {'unique_exact_process': 1}, {'extension_processes': []},
                       {'expected_executable': '/wrong'}, {'expected_executable_sha256': '0' * 64},
                       {'extension_id': 'Other.Extension'}]:
            self.check_mutation_rejected(lambda root: self.edit(root / 'mac-host-observed/extension-process.json', **update))
        for field, value in [('pid', 0), ('pid', True), ('executable', '/wrong'), ('sha256', '0' * 64)]:
            def mutate(root):
                path = root / 'mac-host-observed/extension-process.json'; data = json.loads(path.read_text())
                data['extension_processes'][0][field] = value; gate.write(path, data)
            self.check_mutation_rejected(mutate)
        def duplicate(root):
            path = root / 'mac-host-observed/extension-process.json'; data = json.loads(path.read_text())
            data['extension_processes'] *= 2; gate.write(path, data)
        self.check_mutation_rejected(duplicate)

    def test_changed_product_source_or_symlink_receipt_rejects(self):
        for name, updates in [('mac-host-product-after.json', {'installed_bytes_unchanged': False}),
                              ('mac-host-product-after.json', {'strict_signatures_unchanged': False}),
                              ('mac-host-product-after.json', {'extension_executable_sha256': '0' * 64}),
                              ('mac-host-source-after.json', {'tree': '0' * 40}),
                              ('mac-host-source-after.json', {'workflow_sha256': '0' * 64}),
                              ('mac-host-source-before.json', {'unchanged_bound_files': 531}),
                              ('mac-host-source-before.json', {'reviewed_diagnostic_test_files': {}}),
                              ('mac-host-source-after.json', {'reviewed_diagnostic_test_files': {'unreviewed.swift':'0'*64}})]:
            self.check_mutation_rejected(lambda root: self.edit(root / name, **updates))
        def symlink(root):
            path = root / 'mac-host-observed/prerequisite.json'; target = root / 'copy.json'
            path.rename(target); path.symlink_to(target)
        self.check_mutation_rejected(symlink)

    def test_acceptance_is_mandatory_even_after_failure_and_precedes_evidence(self):
        workflow = (ROOT / '.github/workflows/apple-platforms.yml').read_text()
        step = workflow.split('      - name: Require exact executed case and same-candidate host receipts\n', 1)[1]
        step = step.split('      - name:', 1)[0]
        self.assertIn("        if: always() && steps.sandbox_child.outcome == 'success'\n", step)
        self.assertIn('          python3 Scripts/mac_photos_host_gate.py accept\n', step)
        self.assertNotIn('||', step)
        self.assertNotIn('continue-on-error', workflow)
        self.assertLess(workflow.index('mac_photos_host_gate.py accept'), workflow.index('mac_photos_host_gate.py collect'))


class CollectedProofTests(SyntheticHostFixtureCase):
    """Both collectors replay complete proofs; synthetic packets are not CI proof."""
    SOURCE='a'*40
    seed=RuntimeAcceptanceTests.seed
    def packet(self,root,accepted=True):
        if accepted:
            self.seed(root);status=gate.verify_acceptance(root,self.SOURCE)
        else:
            (root/'mac-host-observed').mkdir()
            gate.write(root/'mac-host-source-before.json',{'source_sha':self.SOURCE,'observed':'source-bound diagnostic'})
            gate.write(root/'mac-host-observed/outcome.json',{'source_sha':self.SOURCE,'last_stage':'discovery failed'})
            status={'source_sha':self.SOURCE,'prerequisite_accepted':False,'complete_host_e2e':False,'error':'AssertionError: extension not registered'}
        gate.write(root/'mac-host-acceptance.json',status)
    def collect(self,root):
        with mock.patch.dict(os.environ,RUNNER_TEMP=str(root),GITHUB_SHA=self.SOURCE):gate.collect()
        return root/'mac-host-evidence'
    def outer(self,root):
        return subprocess.run([sys.executable,str(ROOT/'Scripts/collect_native_evidence.py')],env=dict(os.environ,RUNNER_TEMP=str(root),GITHUB_SHA=self.SOURCE,CELLULOID_EVIDENCE_PLATFORM='mac'),text=True,capture_output=True,timeout=15)
    def mutate_manifest(self,folder,mutate):
        manifest=json.loads((folder/'manifest.json').read_text());mutate(manifest);gate.write(folder/'manifest.json',manifest)
    def update_file(self,folder,name,mutate):
        p=folder/name;record=json.loads(p.read_text());mutate(record);gate.write(p,record)
        def update(manifest):
            row=next(r for r in manifest['files'] if r['path']==name);row['bytes']=p.stat().st_size;row['sha256']=gate.sha(p)
        self.mutate_manifest(folder,update)
    def assert_outer_rejects(self,root):
        result=self.outer(root);self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
    def test_optional_saturation_cannot_displace_any_accepted_proof_in_either_collector(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.packet(root)
            for i in range(12):
                (root/'mac-host-observed'/f'optional-{i}.jpg').write_bytes(b'x'*600_000)
                (root/'mac-host-observed'/f'optional-{i}.txt').write_bytes(b'y'*150_000)
            folder=self.collect(root);record=gate.verify_collected(folder,self.SOURCE)
            self.assertEqual(record['missing_required_proof'],[]);self.assertTrue(record['prerequisite_accepted']);self.assertTrue(record['omitted'])
            self.assertEqual({r['source_relative'] for r in record['files'] if r['kind']=='required-proof'},set(gate.PROOF_LIMITS))
            self.assertLessEqual(sum(p.stat().st_size for p in folder.iterdir()),gate.CAP)
            result=self.outer(root);self.assertEqual(result.returncode,0,result.stderr)
            outer=json.loads((root/'celluloid-bounded-evidence/manifest.json').read_text())
            outer_names={r['name'] for r in outer['files']}
            for row in record['files']:
                name=row['path'];self.assertIn(name if name.startswith('mac-host-') else 'mac-host-'+name,outer_names)
            self.assertLessEqual(sum(p.stat().st_size for p in (root/'celluloid-bounded-evidence').iterdir()),2_000_000)
    def test_missing_accepted_proof_rejected_by_both_collectors(self):
        for missing in gate.PROOF_LIMITS:
            with self.subTest(missing=missing),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.packet(root);(root/missing).unlink()
                with self.assertRaises((AssertionError,KeyError)):self.collect(root)
            with self.subTest(collected_missing=missing),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.packet(root);folder=self.collect(root)
                def remove(m):
                    row=next(r for r in m['files'] if r['source_relative']==missing);m['files'].remove(row);(folder/row['path']).unlink();m['missing_required_proof']=[missing]
                self.mutate_manifest(folder,remove)
                with self.assertRaises(AssertionError):gate.verify_collected(folder,self.SOURCE)
                self.assert_outer_rejects(root)
    def test_oversized_required_proof_rejected_by_both_collectors(self):
        for relative,limit in gate.PROOF_LIMITS.items():
            with self.subTest(relative=relative),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.packet(root);p=root/relative;p.write_bytes(p.read_bytes()+b' '*(limit+1-p.stat().st_size))
                with self.assertRaises((AssertionError,ValueError)):self.collect(root)
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.packet(root);folder=self.collect(root);p=folder/Path(relative).name;p.write_bytes(p.read_bytes()+b' '*(limit+1-p.stat().st_size))
                def update(m):
                    row=next(r for r in m['files'] if r['source_relative']==relative);row.update(bytes=p.stat().st_size,sha256=gate.sha(p))
                self.mutate_manifest(folder,update)
                with self.assertRaises(AssertionError):gate.verify_collected(folder,self.SOURCE)
                self.assert_outer_rejects(root)
    def test_false_diagnostic_keeps_failure_and_available_ownership_source_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.packet(root,False)
            for i in range(3):(root/'mac-host-observed'/f'optional-{i}.jpg').write_bytes(b'x'*600_000)
            folder=self.collect(root);record=gate.verify_collected(folder,self.SOURCE)
            self.assertFalse(record['prerequisite_accepted']);self.assertEqual(record['proof_state'],'diagnostic-only-incomplete');self.assertTrue(record['missing_required_proof'])
            self.assertTrue((folder/'outcome.json').is_file());self.assertTrue((folder/'mac-host-source-before.json').is_file())
            self.assertEqual(json.loads((folder/'mac-host-acceptance.json').read_text())['error'],'AssertionError: extension not registered')
            result=self.outer(root);self.assertEqual(result.returncode,0,result.stderr)
    def test_diagnostic_boolean_flip_cannot_manufacture_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.packet(root,False);folder=self.collect(root)
            self.update_file(folder,'mac-host-acceptance.json',lambda m:m.update(prerequisite_accepted=True))
            self.mutate_manifest(folder,lambda m:m.update(prerequisite_accepted=True,proof_state='complete-accepted-prerequisite',missing_required_proof=[]))
            with self.assertRaises(AssertionError):gate.verify_collected(folder,self.SOURCE)
            self.assert_outer_rejects(root)
    def test_self_consistent_hashes_cannot_hide_bad_runtime_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.packet(root);folder=self.collect(root)
            self.update_file(folder,'prerequisite.json',lambda m:m.update(prerequisite_passed=False))
            with self.assertRaises(AssertionError):gate.verify_collected(folder,self.SOURCE)
            self.assert_outer_rejects(root)
    def test_changed_hash_source_symlink_extra_or_duplicate_files_reject(self):
        mutations=[lambda f:(f/'outcome.json').write_text('{}'),
                   lambda f:(f/'unlisted.txt').write_text('unexpected'),
                   lambda f:self.mutate_manifest(f,lambda m:m.update(source_sha='b'*40)),
                   lambda f:self.mutate_manifest(f,lambda m:m['files'].append(m['files'][0])),
                   lambda f:self.update_file(f,'mac-host-acceptance.json',lambda m:m.update(source_sha='b'*40))]
        for mutate in mutations:
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.packet(root);folder=self.collect(root);mutate(folder)
                with self.assertRaises(AssertionError):gate.verify_collected(folder,self.SOURCE)
                self.assert_outer_rejects(root)
    def test_optional_collision_and_required_total_exhaustion_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.packet(root)
            (root/'mac-host-observed/mac-host-acceptance.json').write_text('{}')
            with self.assertRaisesRegex(AssertionError,'collides'):self.collect(root)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.packet(root)
            for name,size in [('mac-host-context.json',480_000),('mac-host-summary.json',140_000),('mac-host-product-after.json',140_000)]:
                p=root/name;record=json.loads(p.read_text());record['diagnostic_padding']='x'*(size-p.stat().st_size);gate.write(p,record)
            RuntimeAcceptanceTests.write_transport_log(self,root)
            p=root/'mac-host-test.log';p.write_text(p.read_text()+' '*(299_000-p.stat().st_size))
            context=gate.read_receipt(root/'mac-host-context.json');records=gate.transport_records(root,context,complete=True)
            gate.write(root/'mac-host-transport-replay.json',gate.transport_report(root,context,records))
            gate.write(root/'mac-host-acceptance.json',gate.verify_acceptance(root,self.SOURCE))
            with self.assertRaisesRegex(AssertionError,'reserved host allocation'):self.collect(root)
    def test_missing_diagnostic_failure_or_oversized_available_proof_rejects(self):
        for mutate in [lambda r:(r/'mac-host-acceptance.json').unlink(),
                       lambda r:gate.write(r/'mac-host-acceptance.json',{'source_sha':self.SOURCE,'prerequisite_accepted':False,'complete_host_e2e':False,'error':''}),
                       lambda r:(r/'mac-host-source-before.json').write_bytes(b' '*160_001)]:
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.packet(root,False);mutate(root)
                with self.assertRaises(AssertionError):self.collect(root)

class HostTimeBudgetTests(SyntheticHostFixtureCase):
    def prepare(self,root):
        gate.write(root/'mac-job-clock.json',{'source_sha':'a'*40,'started_monotonic':100.0,'started_unix':10000.0,'execution_budget_seconds':2460})
    def test_two_time_checks_reserve_twelve_minute_host_plus_five_minute_proof_tail(self):
        with tempfile.TemporaryDirectory() as folder,mock.patch.dict(os.environ,RUNNER_TEMP=folder,GITHUB_SHA='a'*40),mock.patch.object(gate,'require_runner'),mock.patch.object(gate.time,'monotonic',side_effect=[101.0,1200.0]):
            root=Path(folder);self.prepare(root);gate.budget('before-prepare');gate.budget('before-host')
            record=gate.read_receipt(root/'mac-host-budget.json');self.assertTrue(record['admitted']);self.assertEqual(record['checks'][-1]['required_seconds'],1020)
            self.assertGreaterEqual(record['checks'][-1]['remaining_seconds'],1020)
    def test_preparation_can_exhaust_budget_and_prevent_host_start(self):
        with tempfile.TemporaryDirectory() as folder,mock.patch.dict(os.environ,RUNNER_TEMP=folder,GITHUB_SHA='a'*40),mock.patch.object(gate,'require_runner'),mock.patch.object(gate.time,'monotonic',side_effect=[101.0,1541.0]):
            root=Path(folder);self.prepare(root);gate.budget('before-prepare')
            with self.assertRaisesRegex(RuntimeError,'incomplete'):gate.budget('before-host')
            record=gate.read_receipt(root/'mac-host-budget.json');self.assertFalse(record['admitted']);self.assertEqual(record['checks'][-1]['remaining_seconds'],1019)
            self.assertFalse((root/'mac-host-test.log').exists())
    def test_missing_wrong_or_future_clock_rejected(self):
        for update in [None,{'source_sha':'b'*40},{'execution_budget_seconds':2700},{'started_monotonic':2000.0},{'started_monotonic':True}]:
            with tempfile.TemporaryDirectory() as folder,mock.patch.dict(os.environ,RUNNER_TEMP=folder,GITHUB_SHA='a'*40),mock.patch.object(gate,'require_runner'),mock.patch.object(gate.time,'monotonic',return_value=1000.0):
                root=Path(folder)
                if update is not None:self.prepare(root);value=gate.read_receipt(root/'mac-job-clock.json');value.update(update);gate.write(root/'mac-job-clock.json',value)
                with self.assertRaises(AssertionError):gate.budget('before-host')
                self.assertFalse((root/'mac-host-test.log').exists())
    def test_decreasing_phase_admission_rejected(self):
        with tempfile.TemporaryDirectory() as folder,mock.patch.dict(os.environ,RUNNER_TEMP=folder,GITHUB_SHA='a'*40),mock.patch.object(gate,'require_runner'),mock.patch.object(gate.time,'monotonic',side_effect=[1500.0,1100.0]):
            root=Path(folder);self.prepare(root);gate.budget('before-prepare')
            with self.assertRaisesRegex(AssertionError,'Decreasing'):gate.budget('before-host')
            record=gate.read_receipt(root/'mac-host-budget.json');self.assertEqual(len(record['checks']),1)
    def test_shared_clock_validation_rejects_invalid_admission_and_replay(self):
        for value in [-1000,0,False,True,float('nan'),float('inf')]:
            with self.subTest(value=value),tempfile.TemporaryDirectory() as folder,mock.patch.dict(os.environ,RUNNER_TEMP=folder,GITHUB_SHA='a'*40),mock.patch.object(gate,'require_runner'),mock.patch.object(gate.time,'monotonic',return_value=1000.0):
                root=Path(folder);self.prepare(root);clock=gate.read_receipt(root/'mac-job-clock.json');clock['started_monotonic']=value;gate.write(root/'mac-job-clock.json',clock)
                with self.assertRaises((AssertionError,ValueError)):gate.budget('before-prepare')
                with self.assertRaises(AssertionError):gate.validate_clock(clock,'a'*40)
            with self.subTest(replay=value),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);RuntimeAcceptanceTests().seed(root)
                clock=gate.read_receipt(root/'mac-job-clock.json');clock['started_monotonic']=value;gate.write(root/'mac-job-clock.json',clock)
                report=gate.read_receipt(root/'mac-host-budget.json');report['clock_sha256']=gate.sha(root/'mac-job-clock.json')
                for row in report['checks']:
                    row['deadline_monotonic']=value+gate.JOB_EXECUTION_SECONDS;row['remaining_seconds']=row['deadline_monotonic']-row['observed_monotonic']
                gate.write(root/'mac-host-budget.json',report)
                with self.assertRaises((AssertionError,ValueError)):gate.verify_acceptance(root,'a'*40)
    def test_clock_constants_phase_types_and_replay_order_are_strict(self):
        def mutate_budget(root,key,value):
            p=root/'mac-host-budget.json';r=gate.read_receipt(p);r['checks'][1][key]=value;gate.write(p,r)
        for key,value in [('observed_monotonic',True),('observed_monotonic',float('inf')),('deadline_monotonic',float('nan')),('remaining_seconds',True),('required_seconds',True),('phase','before-prepare'),('admitted',1)]:
            with self.subTest(key=key,value=value),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);RuntimeAcceptanceTests().seed(root);mutate_budget(root,key,value)
                with self.assertRaises((AssertionError,ValueError)):gate.verify_acceptance(root,'a'*40)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);RuntimeAcceptanceTests().seed(root);r=gate.read_receipt(root/'mac-host-budget.json')
            for row,now in zip(r['checks'],[1500.0,1100.0]):row['observed_monotonic']=now;row['remaining_seconds']=2560-now
            gate.write(root/'mac-host-budget.json',r)
            with self.assertRaises((AssertionError,ValueError)):gate.verify_acceptance(root,'a'*40)
    def test_workflow_reserves_first_step_clock_and_finishes_compiles_before_host(self):
        workflow=(ROOT/'.github/workflows/apple-platforms.yml').read_text().split('  native-mac-host:',1)[1].split('  native-simulator:',1)[0]
        self.assertLess(workflow.index('Reserve Mac job collection time'),workflow.index('uses: actions/checkout@'))
        self.assertLess(workflow.index('Verify actual embedded sandbox extension before UI'),workflow.index('Actual Photos host discovery'))
        self.assertLess(workflow.index('Actual Photos host discovery'),workflow.index('Bound and replay the dedicated host proof'))
        shell=(ROOT/'Scripts/run_mac_photos_host_gate.sh').read_text()
        self.assertLess(shell.index('budget-before-prepare'),shell.index('source-before'))
        self.assertLess(shell.index('budget-before-host'),shell.index('TEST_RUNNER_CELLULOID_MAC_PHOTOS_HOST_PREREQUISITE'))
        self.assertIn('timeout-minutes: 45',workflow)

class HostFixtureEnvironmentTests(unittest.TestCase):
    CI_SOURCE = '0995214f6a7a0a88c94aebe28fcb1b507d7ad4eb'

    def test_fixture_cases_override_only_their_source_and_restore_ci_environment(self):
        for owner in [RuntimeAcceptanceTests, CollectedProofTests, HostTimeBudgetTests]:
            with self.subTest(owner=owner.__name__), mock.patch.dict(os.environ, GITHUB_SHA=self.CI_SOURCE, GITHUB_WORKFLOW_SHA=self.CI_SOURCE, GITHUB_ACTIONS='true'):
                original = dict(os.environ)
                case = owner()
                case.setUp()
                try:
                    self.assertEqual(os.environ['GITHUB_SHA'], case.SOURCE)
                    self.assertEqual(os.environ['GITHUB_WORKFLOW_SHA'], self.CI_SOURCE)
                    with tempfile.TemporaryDirectory() as folder:
                        root = Path(folder)
                        RuntimeAcceptanceTests.seed(case, root)
                        self.assertTrue(gate.verify_acceptance(root, case.SOURCE)['prerequisite_accepted'])
                finally:
                    case.doCleanups()
                self.assertEqual(dict(os.environ), original)

    def test_source_environment_restores_after_failure_and_when_initially_absent(self):
        class DeliberateFailure(SyntheticHostFixtureCase):
            def runTest(self):
                self.assertEqual(os.environ['GITHUB_SHA'], self.SOURCE)
                self.fail('Synthetic cleanup regression probe')
        for initial in [None, self.CI_SOURCE]:
            with self.subTest(initial=initial), mock.patch.dict(os.environ):
                if initial is None: os.environ.pop('GITHUB_SHA', None)
                else: os.environ['GITHUB_SHA'] = initial
                original = dict(os.environ)
                result = unittest.TestResult()
                DeliberateFailure().run(result)
                self.assertEqual(result.testsRun, 1)
                self.assertEqual(len(result.failures), 1)
                self.assertEqual(len(result.errors), 0)
                self.assertEqual(dict(os.environ), original)

    def test_real_transport_source_guard_still_rejects_foreign_ci_source(self):
        with mock.patch.dict(os.environ, GITHUB_SHA=self.CI_SOURCE), tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fixture = RuntimeAcceptanceTests()
            fixture.setUp()
            try:
                fixture.seed(root)
                context = gate.read_receipt(root/'mac-host-context.json')
                self.assertTrue(gate.transport_records(root, context, complete=True))
            finally:
                fixture.doCleanups()
            self.assertEqual(os.environ['GITHUB_SHA'], self.CI_SOURCE)
            with self.assertRaises(AssertionError):
                gate.transport_records(root, context, complete=True)


if __name__ == '__main__': unittest.main()
