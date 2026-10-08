#!/usr/bin/env python3
"""Exercise execution gates and retention without any Apple tools or publication."""
from pathlib import Path
import hashlib, json, os, subprocess, tempfile, unittest
from verify_required_interoperability import inspect, required, CONSUMER
from combined_evidence_budget import BUDGETS, WHOLE_RUN

ROOT=Path(__file__).resolve().parents[1]

class RequiredExecutionTests(unittest.TestCase):
    def fixture(self):return {'sha256':'a'*64,'sourceSHA256':'b'*64,'renderedSHA256':'c'*64}
    def log(self,status='passed',duplicate=False,delta=2):
        row=f"Test Case '-[CelluloidTests.MacPhotosManufacturedAdjustmentTests {CONSUMER.split('.')[-1]}]' {status} (0.1 seconds).\n"
        return row*(2 if duplicate else 1)+f"MAC_LAYER_UIKIT_COMPOSITOR archiveSHA256={'a'*64} sourceSHA256={'b'*64} nativeSHA256={'c'*64} maximumChannelDifference={delta}\n"
    def inspect(self,contents,fixture=None):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'tests.log';path.write_text(contents)
            return inspect(path,required('uikit'),fixture or self.fixture())
    def test_pass_requires_actual_case_and_exact_strict_pixel_marker(self):
        self.assertTrue(all(self.inspect(self.log())['checks'].values()))
    def test_skipped_missing_failed_duplicate_or_other_module_fail(self):
        for contents in [self.log('skipped'),self.log('failed'),'',self.log(duplicate=True),self.log().replace('CelluloidTests.','StandaloneTests.')]:
            with self.subTest(contents=contents[:50]):self.assertFalse(all(self.inspect(contents)['checks'].values()))
    def test_stale_hash_multiple_or_missing_oracles_and_relaxed_pixels_fail(self):
        for contents in [self.log(delta=3),self.log().replace('a'*64,'d'*64),self.log().split('MAC_LAYER')[0],self.log()+'MAC_LAYER'+self.log().split('MAC_LAYER')[1]]:
            self.assertFalse(all(self.inspect(contents)['checks'].values()))
    def test_exact_declared_required_counts_and_real_shipping_modules(self):
        self.assertEqual({k:len(v) for k,v in required('mac').items()},{'CelluloidMacPhotosExtensionTests':39})
        self.assertEqual({k:len(v) for k,v in required('phone').items()},{'CelluloidCompanionTests':14,'CelluloidCompanionUITests':2})
        self.assertEqual(sum(map(len,required('uikit').values())),1)
    def test_shipping_markers_do_not_substitute_for_missing_ui_case(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'tests.log';path.write_text('SHIPPING_COMPANION_NAVIGATION reached\nSHIPPING_COMPANION_RETURN reached\n')
            report=inspect(path,required('phone'),require_navigation=True)
            self.assertTrue(report['checks']['shipping_entry_and_return_executed'])
            self.assertFalse(report['checks']['every_required_case_executed_once_and_passed'])

class CombinedRetentionTests(unittest.TestCase):
    def test_receipts_and_complete_consumer_markers_precede_optional_log_pressure(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            names=['combined-source-before.json','combined-source-after.json','phone-embedded-watch.json','phone-embedded-watch-release.json','phone-required-tests.json']
            for name in names:(folder/name).write_text(json.dumps({'source_sha':'a'*40,'fixture':'synthetic '+name}))
            lines='SHIPPING_COMPANION_NAVIGATION actual shipping entry\nSHIPPING_COMPANION_RETURN actual return\nMAC_LAYER_UIKIT_COMPOSITOR bound hashes and strict pixels\n'
            (folder/'phone-runtime-tests.log').write_text(lines+('NATIVE_DIAGNOSTIC '+'x'*1990+'\n')*2000)
            (folder/'domain.log').write_text(('Test Case synthetic passed '+'z'*1990+'\n')*2000)
            result=subprocess.run(['python3',str(ROOT/'Scripts/collect_native_evidence.py')],env=dict(os.environ,RUNNER_TEMP=directory,CELLULOID_EVIDENCE_PLATFORM='phone',GITHUB_SHA='a'*40),capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            output=folder/'celluloid-bounded-evidence'
            for name in names:self.assertEqual((output/name).read_bytes(),(folder/name).read_bytes())
            markers=json.loads((output/'shipping-consumer-markers.json').read_text());self.assertEqual(len(markers),3)
            self.assertLessEqual(sum(p.stat().st_size for p in output.iterdir()),BUDGETS['phone'])
            self.assertEqual(sum(BUDGETS.values()),19_500_000);self.assertLess(sum(BUDGETS.values()),WHOLE_RUN)
    def test_workflow_shipping_routes_and_all_twelve_serial_jobs_are_retained(self):
        text=(ROOT/'.github/workflows/apple-platforms.yml').read_text()
        self.assertIn('python3 Scripts/run_native_phone.py --shipping',text)
        self.assertIn('-project Celluloid.xcodeproj -scheme CelluloidCompanion',text)
        self.assertNotIn('-scheme CelluloidPhoneCompanion',text)
        self.assertIn('needs: [build-preflight, native-mac, native-simulator]',text)
        self.assertIn('needs: [build-preflight, native-mac, native-simulator, uikit-regression]',text)
        self.assertEqual(text.count('max-parallel: 1'),2)
        for key in ['compact-phone','large-phone','small-ipad','large-ipad']:self.assertIn('key: '+key,text)
        for scope in ['mac','phone','uikit']:self.assertIn('verify_required_interoperability.py '+scope,text)
        self.assertNotIn('ARCHS=',text);self.assertNotIn('SDKROOT=',text)
        self.assertNotIn('retention-days: 14',text);self.assertEqual(text.count('retention-days: 1'),6)

if __name__=='__main__':unittest.main()
