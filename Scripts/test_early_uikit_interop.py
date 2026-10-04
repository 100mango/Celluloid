import contextlib,io,json,os,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import run_early_uikit_interop as early

class EarlyUIKitInteropTests(unittest.TestCase):
    def exercise(self, *, pixel_pass=True, test_status=0, cleanup_status=0, cleanup_timeout=False):
        commands=[];identifier='12345678-1234-1234-1234-123456789ABC'
        def invoke(args, **kwargs):
            args=list(map(str,args));commands.append((args,kwargs))
            result=''
            if args[:4]==['xcrun','simctl','list','runtimes']:
                result=json.dumps({'runtimes':[{'version':'27.0','isAvailable':True,'identifier':'com.apple.CoreSimulator.SimRuntime.iOS-27-0'}]})
            elif args[:4]==['xcrun','simctl','list','devicetypes']:
                result=json.dumps({'devicetypes':[{'name':'iPhone SE (3rd generation)','identifier':'owned-type'}]})
            elif args[:3]==['xcrun','simctl','create']:result=identifier+'\n'
            if args[:3]==['xcrun','simctl','shutdown'] and cleanup_timeout:raise TimeoutError('owned shutdown timed out')
            status=cleanup_status if args[:3] in [['xcrun','simctl','shutdown'],['xcrun','simctl','delete']] else test_status if 'test-without-building' in args else 0
            return subprocess.CompletedProcess(args,status,result,'')
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,RUNNER_TEMP=folder,GITHUB_SHA='a'*40),patch.object(early,'layer_from_log',return_value=b'{"fixture":"source-bound-by-producer"}'),patch.object(early,'run',side_effect=invoke),patch.object(early,'verify',return_value={'checks':{'one_source_bound_strict_pixel_oracle':pixel_pass}}),contextlib.redirect_stdout(io.StringIO()):
            expected=pixel_pass and test_status==0 and cleanup_status==0 and not cleanup_timeout
            if expected:early.main()
            else:
                with self.assertRaisesRegex(RuntimeError,'full matrix withheld'):early.main()
            report=json.loads((Path(folder)/'early-uikit-interop.json').read_text())
            self.assertEqual(report['passed'],expected)
            self.assertEqual(report['cleanup_passed'],cleanup_status==0 and not cleanup_timeout)
            if not pixel_pass or test_status:self.assertIn('strict pixel consumer failed',report['error'])
            self.assertEqual([row['action'] for row in report['cleanup']],['shutdown','delete'])
            tests=[args for args,kwargs in commands if 'test-without-building' in args]
            self.assertEqual(len(tests),1)
            self.assertIn('-only-testing:CelluloidTests/MacPhotosManufacturedAdjustmentTests/testManufacturedMacArchiveThroughOriginalUIKitReaderAndCompositor',tests[0])
            self.assertIn('Celluloid.xcodeproj',tests[0])
            self.assertFalse(any('privacy' in args or 'addmedia' in args for args,kwargs in commands))
            self.assertTrue(all(kwargs.get('timeout',180)<=600 for args,kwargs in commands))
        return commands
    def test_exact_shipping_consumer_and_cleanup_on_success(self):self.exercise()
    def test_pixel_failure_and_xctest_failure_each_stop_full_acceptance(self):
        self.exercise(pixel_pass=False);self.exercise(test_status=65)
    def test_cleanup_failure_cannot_release_gate_or_replace_pixel_diagnosis(self):
        self.exercise(cleanup_status=1)
        self.exercise(cleanup_timeout=True)
        self.exercise(pixel_pass=False,cleanup_timeout=True)
    def test_every_later_runtime_requires_pixel_gate_but_release_builds_continue(self):
        source=(early.ROOT/'.github/workflows/apple-platforms.yml').read_text()
        for name in ['Native Mac UI launch and editing','External sandbox document UI and container runtime']:
            block=source.split('- name: '+name,1)[1].split('- name:',1)[0]
            self.assertIn("steps.early_interop.outputs.passed == 'true'",block)
        self.assertEqual(source.count("needs.native-mac.outputs.interop_passed == 'true'"),2)
        for name in ['Isolated native Mac Photos extension build','Unsigned native Mac Release packaging']:
            block=source.split('- name: '+name,1)[1].split('- name:',1)[0]
            self.assertNotIn('early_interop',block)
        self.assertIn('interop_passed: ${{ steps.early_interop.outputs.passed }}',source)
        self.assertEqual(source.count('max-parallel: 1'),2)

if __name__=='__main__':unittest.main()
