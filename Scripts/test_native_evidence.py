#!/usr/bin/env python3
"""Linux-safe regression test for the outbound evidence budget. No Apple tooling needed."""
from pathlib import Path
from combined_evidence_budget import BUDGETS, WHOLE_RUN
import hashlib,json,os,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
class EvidenceBudgetTests(unittest.TestCase):
    def test_duplicate_audit_screens_do_not_displace_named_checkpoints(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);(folder/'CelluloidMacUI.xcresult').mkdir()
            binary=folder/'bin';binary.mkdir();mock=binary/'xcrun'
            mock.write_text('''#!/usr/bin/env python3
import json,sys
from pathlib import Path
if 'attachments' not in sys.argv:
 print('{}');raise SystemExit(0)
out=Path(sys.argv[sys.argv.index('--output-path')+1]);items=[]
for index in range(54):
 name=f'audit-{index}.png';(out/name).write_bytes(b'\\x89PNG\\r\\n\\x1a\\nidentical-audit-screen')
 items.append({'exportedFileName':name,'suggestedHumanReadableName':f'App-Screenshot-{index}','isAssociatedWithFailure':True})
name='checkpoint.png';(out/name).write_bytes(b'\\x89PNG\\r\\n\\x1a\\nunique-checkpoint')
items.append({'exportedFileName':name,'suggestedHumanReadableName':'native-mac-photos-thumbnail-selected','isAssociatedWithFailure':False})
(out/'manifest.json').write_text(json.dumps([{'attachments':items}]))
''')
            mock.chmod(0o755)
            result=subprocess.run(['python3',str(ROOT/'Scripts/collect_native_evidence.py')],env=dict(os.environ,CELLULOID_VALIDATION_SCOPE='full',RUNNER_TEMP=directory,GITHUB_SHA='synthetic',CELLULOID_EVIDENCE_PLATFORM='local',PATH=str(binary)+os.pathsep+os.environ['PATH']),capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            output=folder/'celluloid-bounded-evidence'
            images=list(output.glob('*.png'))
            self.assertEqual(len(images),2)
            self.assertTrue(any('photos-thumbnail-selected' in p.name for p in images))
            self.assertEqual(len({hashlib.sha256(p.read_bytes()).hexdigest() for p in images}),2)
            self.assertLessEqual(sum(p.stat().st_size for p in output.iterdir()),3_500_000)
    def test_log_tails_markers_and_oversize_image_are_bounded(self):
        # Exercise both the standalone default and the actual Mac job allocation.
        # Child fixtures must not inherit whichever platform owns this test process.
        for platform,total_budget in [('local',3_500_000),('mac',BUDGETS['mac'])]:
            with self.subTest(platform=platform):
                with tempfile.TemporaryDirectory() as directory:
                    folder=Path(directory)
                    with (folder/'domain.log').open('wb') as handle:
                        for _ in range(256):handle.write(b'x'*256_000)
                        handle.write(b'\nTest Case synthetic passed\n')
                    (folder/'native-vision-launch.png').write_bytes(b'\x89PNG\r\n\x1a\n'+b'x'*5_000_000)
                    result=subprocess.run(['python3',str(ROOT/'Scripts/collect_native_evidence.py')],env=dict(os.environ,CELLULOID_VALIDATION_SCOPE='full',RUNNER_TEMP=directory,GITHUB_SHA='synthetic',CELLULOID_EVIDENCE_PLATFORM=platform),capture_output=True,text=True)
                    self.assertEqual(result.returncode,0,result.stderr)
                    output=folder/'celluloid-bounded-evidence'
                    manifest=json.loads((output/'manifest.json').read_text())
                    self.assertEqual(manifest['platform'],platform)
                    self.assertEqual(manifest['limits'],{'per_file_bytes':5_000_000,'total_bytes':total_budget,'retention_days':1})
                    self.assertIn('Test Case synthetic passed',(output/'domain.log.summary.txt').read_text())
                    self.assertLessEqual((output/'domain.log.tail.txt').stat().st_size,200_000)
                    self.assertFalse((output/'native-vision-launch.png').exists())
                    self.assertTrue(any(item['reason']=='evidence byte cap' for item in manifest['omissions']))
                    self.assertLessEqual(sum(p.stat().st_size for p in output.iterdir()),total_budget)
                    for record in manifest['files']:
                        data=(output/record['name']).read_bytes();self.assertEqual(hashlib.sha256(data).hexdigest(),record['sha256']);self.assertLessEqual(len(data),5_000_000)
                    again=subprocess.run(['python3',str(ROOT/'Scripts/collect_native_evidence.py')],env=dict(os.environ,CELLULOID_VALIDATION_SCOPE='full',RUNNER_TEMP=directory,CELLULOID_EVIDENCE_PLATFORM=platform),capture_output=True,text=True)
                    self.assertNotEqual(again.returncode,0,'A nonempty destination must not be merged into an upload')
    def test_mac_reallocation_preserves_runtime_tails_and_marks_compiler_omissions(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            for name in ['early-uikit-build.log','mac-ui.log','sandbox.log']:
                (folder/name).write_text('x'*250_000+'\nTest Case synthetic passed\n')
            result=subprocess.run(['python3',str(ROOT/'Scripts/collect_native_evidence.py')],env=dict(os.environ,CELLULOID_VALIDATION_SCOPE='full',RUNNER_TEMP=directory,GITHUB_SHA='synthetic',CELLULOID_EVIDENCE_PLATFORM='mac'),capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            output=folder/'celluloid-bounded-evidence';manifest=json.loads((output/'manifest.json').read_text())
            self.assertEqual((output/'early-uikit-build.log.tail.txt').stat().st_size,20_000)
            for name in ['mac-ui.log','sandbox.log']:
                self.assertEqual((output/(name+'.tail.txt')).stat().st_size,200_000)
            self.assertTrue(any(row.get('retained_tail_limit')==20_000 for row in manifest['omissions']))
            self.assertEqual(BUDGETS['mac']+BUDGETS['mac-host'],3_000_000)

    def test_child_process_uses_each_reviewed_platform_allocation(self):
        expected={'preflight':500_000,'mac':2_000_000,'mac-host':1_000_000,'tv':2_750_000,'watch':1_750_000,
                  'phone':2_500_000,'vision':2_500_000,'compact-phone':1_500_000,
                  'large-phone':1_500_000,'small-ipad':1_500_000,'large-ipad':1_500_000,'archive':500_000}
        self.assertEqual(BUDGETS,expected)
        for platform,total_budget in expected.items():
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as directory:
                # A fresh child imports the production module after its explicit env is set.
                result=subprocess.run(['python3',str(ROOT/'Scripts/collect_native_evidence.py')],
                    env=dict(os.environ,CELLULOID_VALIDATION_SCOPE='full',RUNNER_TEMP=directory,CELLULOID_EVIDENCE_PLATFORM=platform),capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                output=Path(directory)/'celluloid-bounded-evidence'
                manifest=json.loads((output/'manifest.json').read_text())
                self.assertEqual(manifest['platform'],platform)
                self.assertEqual(manifest['limits'],{'per_file_bytes':5_000_000,'total_bytes':total_budget,'retention_days':1})
                self.assertLessEqual(sum(p.stat().st_size for p in output.iterdir()),total_budget)
    def test_twelve_job_allocations_cannot_exceed_whole_run_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            for platform in ['tv','vision','phone','watch']:
                (folder/f'native-{platform}-launch.jpg').write_bytes(b'\xff\xd8\xff'+b'x'*2_500_000)
            result=subprocess.run(['python3',str(ROOT/'Scripts/collect_native_evidence.py')],env=dict(os.environ,CELLULOID_VALIDATION_SCOPE='full',RUNNER_TEMP=directory,CELLULOID_EVIDENCE_PLATFORM='tv'),capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            output=folder/'celluloid-bounded-evidence';total=sum(p.stat().st_size for p in output.iterdir())
            manifest=json.loads((output/'manifest.json').read_text())
            self.assertLessEqual(total,BUDGETS['tv']);self.assertEqual(manifest['whole_run_allocation'],BUDGETS);self.assertEqual(sum(BUDGETS.values()),19_500_000);self.assertLess(sum(BUDGETS.values()),WHOLE_RUN);self.assertEqual(len(BUDGETS),12)
            self.assertEqual(sum(item['reason']=='evidence byte cap' for item in manifest['omissions']),3)
            self.assertEqual(manifest['platform'],'tv')
        workflow=(ROOT/'.github/workflows/apple-platforms.yml').read_text()
        self.assertIn('needs: [build-preflight, native-mac]',workflow)
        self.assertIn('max-parallel: 1',workflow)
        self.assertIn('platform: [tv, watch, phone, vision]',workflow)
        self.assertEqual(workflow.count('uses: actions/upload-artifact@'),6)
        self.assertEqual(workflow.count('retention-days: 1'),6)
        self.assertIn('cancel-in-progress: false',workflow)
        self.assertNotIn('pull_request:',workflow)
if __name__=='__main__':unittest.main()
