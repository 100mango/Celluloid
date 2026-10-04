import contextlib,io,json,os,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import run_early_uikit_interop as early

class EarlyUIKitInteropTests(unittest.TestCase):
    def exercise(self, *, pixels=None,statuses=None,cleanup_status=0,cleanup_timeout=False,scales=None,binaries=None):
        pixels=pixels or {};statuses=statuses or {};scales=scales or {};binaries=binaries or {}
        commands=[];devices={};active=[None]
        def invoke(args, **kwargs):
            args=list(map(str,args));commands.append((args,kwargs));result='';status=0
            if args[:4]==['xcrun','simctl','list','runtimes']:
                result=json.dumps({'runtimes':[{'version':'27.0','isAvailable':True,'identifier':'com.apple.CoreSimulator.SimRuntime.iOS-27-0'}]})
            elif args[:4]==['xcrun','simctl','list','devicetypes']:
                result=json.dumps({'devicetypes':[{'name':name,'identifier':'owned-'+profile} for profile,name,_ in early.PROFILES]})
            elif args[:3]==['xcrun','simctl','create']:
                profile=args[3].split()[-1];identifier='12345678-1234-1234-1234-123456789AB'+str(len(devices))
                devices[identifier]=profile;active[0]=profile;result=identifier+'\n'
            elif len(args)>1 and args[1].endswith('stage_uikit_layer_fixture.py'):
                Path(args[-1]).write_text(json.dumps({'binary_sha256':binaries.get(active[0],'a'*64)}))
            elif 'test-without-building' in args:
                profile=active[0];result='MAC_LAYER_UIKIT_COMPOSITOR_DISPLAY scale='+str(scales.get(profile,float(profile[0])))+'\n'
                (Path(os.environ['RUNNER_TEMP'])/kwargs['log_name']).write_text(result);status=statuses.get(profile,0)
            elif args[:3] in [['xcrun','simctl','shutdown'],['xcrun','simctl','delete']]:
                if args[2]=='shutdown' and cleanup_timeout:raise TimeoutError('owned shutdown timed out')
                status=cleanup_status
            return subprocess.CompletedProcess(args,status,result,'')
        def verify(*args):return {'checks':{'one_source_bound_strict_pixel_oracle':pixels.get(active[0],True)}}
        expected=not any(v is False for v in pixels.values()) and not any(statuses.values()) and not cleanup_status and not cleanup_timeout and all(scales.get(p,float(p[0]))==v for p,_,v in early.PROFILES) and len({binaries.get(p,'a'*64) for p,_,_ in early.PROFILES})==1
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,RUNNER_TEMP=folder,GITHUB_SHA='a'*40),patch.object(early,'frozen_uikit_fingerprint',return_value=early.FROZEN_UIKIT_FINGERPRINT),patch.object(early,'layer_from_log',return_value=b'{"fixture":"source-bound-by-producer"}'),patch.object(early,'run',side_effect=invoke),patch.object(early,'verify',side_effect=verify),contextlib.redirect_stdout(io.StringIO()):
            if expected:early.main()
            else:
                with self.assertRaisesRegex(RuntimeError,'full matrix withheld'):early.main()
            report=json.loads((Path(folder)/'early-uikit-interop.json').read_text());self.assertEqual(report['passed'],expected)
            expected_profiles=1 if cleanup_status or cleanup_timeout else 2
            self.assertEqual(len(report['profiles']),expected_profiles)
            for row in report['profiles']:
                self.assertEqual([c['action'] for c in row['cleanup']],['shutdown','delete'])
                if pixels.get(row['profile']) is False or statuses.get(row['profile']):self.assertIn('strict pixel',row['error'])
            self.assertEqual(len([a for a,k in commands if 'build-for-testing' in a]),1)
            tests=[a for a,k in commands if 'test-without-building' in a];self.assertEqual(len(tests),expected_profiles)
            for args in tests:
                self.assertIn('-only-testing:CelluloidTests/MacPhotosManufacturedAdjustmentTests/testManufacturedMacArchiveThroughOriginalUIKitReaderAndCompositor',args)
                self.assertIn('Celluloid.xcodeproj',args)
            self.assertFalse(any('privacy' in a or 'addmedia' in a for a,k in commands))
            self.assertTrue(all(k.get('timeout',180)<=600 for a,k in commands))
            return report
    def test_one_build_two_real_displays_and_cleanup_on_success(self):self.exercise()
    def test_first_pixel_failure_still_runs_other_display_and_never_passes(self):
        self.exercise(pixels={'2x':False});self.exercise(statuses={'3x':65})
    def test_cleanup_failure_stops_next_device_and_preserves_pixel_diagnosis(self):
        self.exercise(cleanup_status=1);self.exercise(cleanup_timeout=True);self.exercise(pixels={'2x':False},cleanup_timeout=True)
    def test_display_or_binary_mismatch_cannot_release_full_matrix(self):
        self.exercise(scales={'3x':2.0});self.exercise(binaries={'3x':'b'*64})
    def test_frozen_production_source_and_active_budget_fail_before_new_device(self):
        for fingerprint,clock in [('0'*64,None),(early.FROZEN_UIKIT_FINGERPRINT,[0,2000])]:
            with self.subTest(fingerprint=fingerprint),tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,RUNNER_TEMP=folder,GITHUB_SHA='a'*40),patch.object(early,'frozen_uikit_fingerprint',return_value=fingerprint),patch.object(early,'layer_from_log',return_value=b'{}'),patch.object(early,'run') as invoke,contextlib.redirect_stdout(io.StringIO()):
                manager=patch.object(early.time,'monotonic',side_effect=clock) if clock else contextlib.nullcontext()
                with manager:
                    with self.assertRaises(RuntimeError):early.main()
                report=json.loads((Path(folder)/'early-uikit-interop.json').read_text());self.assertFalse(report['passed']);self.assertEqual(report['profiles'],[]);invoke.assert_not_called()
        self.assertLessEqual(early.ACTIVE_SECONDS,18*60)
    def test_current_original_production_fingerprint_is_frozen(self):
        self.assertEqual(early.frozen_uikit_fingerprint(),early.FROZEN_UIKIT_FINGERPRINT)
    def test_every_later_runtime_requires_pixel_gate_but_release_builds_continue(self):
        source=(early.ROOT/'.github/workflows/apple-platforms.yml').read_text()
        for name in ['Native Mac UI launch and editing','External sandbox document UI and container runtime']:
            block=source.split('- name: '+name,1)[1].split('- name:',1)[0];self.assertIn("steps.early_interop.outputs.passed == 'true'",block)
        self.assertEqual(source.count("needs.native-mac.outputs.interop_passed == 'true'"),2)
        for name in ['Isolated native Mac Photos extension build','Unsigned native Mac Release packaging']:
            block=source.split('- name: '+name,1)[1].split('- name:',1)[0];self.assertNotIn('early_interop',block)
        self.assertIn('interop_passed: ${{ steps.early_interop.outputs.passed }}',source)
        self.assertEqual(source.count('max-parallel: 1'),2)
        self.assertIn('timeout-minutes: 20',source);self.assertIn('timeout-minutes: 45',source)

if __name__=='__main__':unittest.main()
