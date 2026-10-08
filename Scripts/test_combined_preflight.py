#!/usr/bin/env python3
from pathlib import Path
import json,os,plistlib,subprocess,tempfile,unittest
from run_combined_preflight import DEBUG_PLANS,RELEASE_PLANS,available_setup,verify_test_products
from combined_evidence_budget import BUDGETS,WHOLE_RUN

ROOT=Path(__file__).resolve().parents[1]

class CombinedPreflightTests(unittest.TestCase):
    def setup_inventory(self):
        names={'iOS':['iPhone SE (3rd generation)','iPhone 18 Pro Max','iPad mini (A17 Pro)','iPad Pro 13-inch (M5)'],
               'tvOS':['Apple TV 4K (3rd generation)'],
               'watchOS':['Apple Watch Series 12 (46mm)','Apple Watch SE 3 (40mm)','Apple Watch Ultra 4 (49mm)'],
               'visionOS':['Apple Vision Pro']}
        runtimes=[];types=[]
        for platform,rows in names.items():
            devices=[{'name':name,'identifier':platform+'-'+str(i)} for i,name in enumerate(rows)];types+=devices
            runtimes.append({'isAvailable':True,'name':platform+' 27.0','version':'27.0','identifier':platform+'27','supportedDeviceTypes':devices})
        return runtimes,types
    def test_requires_all_actual_runtime_profiles_without_boot_or_photo_setup(self):
        runtimes,types=self.setup_inventory();report=available_setup(runtimes,types)
        self.assertEqual(set(report['runtimes']),{'ios','tv','watch','vision'});self.assertEqual(len(report['watch_profiles']),3)
        for invalid in [types[:-1],[r for r in types if r['name']!='Apple Watch SE 3 (40mm)'],[r for r in types if r['name']!='iPad mini (A17 Pro)']]:
            with self.assertRaises(ValueError):available_setup(runtimes,invalid)
        runtimes[0]['version']='26.0'
        with self.assertRaises(ValueError):available_setup(runtimes,types)
    def test_all_shipping_and_original_test_schemes_and_release_products_are_planned(self):
        self.assertEqual(len(DEBUG_PLANS),7);self.assertEqual(len(RELEASE_PLANS),5)
        schemes={row[2] for row in DEBUG_PLANS}
        self.assertEqual(schemes,{'CelluloidMac','CelluloidMacUI','Celluloid','CelluloidCompanion','CelluloidTV','CelluloidWatch','CelluloidVision'})
        self.assertIn('CelluloidMacPhotosExtensionTests',next(r[4] for r in DEBUG_PLANS if r[0]=='mac'))
        self.assertEqual({r[0] for r in RELEASE_PLANS},{'phone','mac','tv','watch','vision'})
    def test_missing_or_unexecutable_xctest_is_not_compile_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);bundle=root/'Debug/TestRunner.app/PlugIns/ExampleTests.xctest';bundle.mkdir(parents=True)
            (bundle/'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'Synthetic.Tests','CFBundleExecutable':'ExampleTests'}))
            with self.assertRaises(ValueError):verify_test_products(root,['ExampleTests'])
            (bundle/'ExampleTests').write_bytes(b'synthetic compiled test executable')
            self.assertEqual(list(verify_test_products(root,['ExampleTests'])),['ExampleTests'])
            with self.assertRaises(ValueError):verify_test_products(root,['MissingTests'])
    def test_every_long_job_is_gated_on_preflight_and_allocation_stays_bounded(self):
        source=(ROOT/'.github/workflows/apple-platforms.yml').read_text()
        self.assertIn('needs: build-preflight',source)
        self.assertEqual(source.count("if: always() && needs.build-preflight.result == 'success'"),3)
        self.assertIn('needs: [build-preflight, native-mac, native-simulator, uikit-regression]',source)
        self.assertEqual(BUDGETS['preflight'],500_000);self.assertEqual(len(BUDGETS),12)
        self.assertEqual(sum(BUDGETS.values()),19_500_000);self.assertLess(sum(BUDGETS.values()),WHOLE_RUN)
        self.assertNotIn('COPY_PHASE_STRIP=',source)
    def test_preflight_failure_receipts_and_strip_diagnostics_survive_export(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ['combined-source-before.json','combined-source-after.json','combined-preflight.json','preflight-phone-embedded-watch.json','preflight-phone-embedded-watch-release.json']:
                (root/name).write_text(json.dumps({'source_sha':'a'*40,'checks':{'synthetic_expected_failure':False}}))
            (root/'preflight-phone-debug.log').write_text('irrelevant\n'*10000+'error: synthetic compile problem\n/observed/strip -D -S -no_atom_info source -o destination\n')
            result=subprocess.run(['python3',str(ROOT/'Scripts/collect_native_evidence.py')],env=dict(os.environ,RUNNER_TEMP=directory,GITHUB_SHA='a'*40,CELLULOID_EVIDENCE_PLATFORM='preflight'),capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            out=root/'celluloid-bounded-evidence';diagnostics=json.loads((out/'preflight-diagnostics.json').read_text())
            self.assertTrue(any('synthetic compile problem'in line for item in diagnostics for line in item['issues']))
            self.assertTrue(any('strip -D -S'in line for item in diagnostics for line in item['issues']))
            self.assertTrue((out/'preflight-phone-embedded-watch.json').is_file())
            self.assertLessEqual(sum(p.stat().st_size for p in out.iterdir()),500_000)

if __name__=='__main__':unittest.main()
