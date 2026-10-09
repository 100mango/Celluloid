import json,unittest,tempfile
from pathlib import Path
import run_ios_photos_host as host

class FinalPhotosHostAdmissionTests(unittest.TestCase):
    def values(self):
        config=json.loads((host.ROOT/host.PROBE_CONFIG).read_text())
        config.update(READY=True,sourceReady=True,nativeAuthorization=True)
        context={'GITHUB_REPOSITORY':'100mango/Celluloid','GITHUB_EVENT_NAME':'push','GITHUB_REF':'refs/heads/'+host.PROBE_BRANCH,
                 'GITHUB_WORKFLOW_REF':'100mango/Celluloid/'+host.PROBE_WORKFLOW+'@refs/heads/'+host.PROBE_BRANCH,
                 'GITHUB_SHA':'a'*40,'GITHUB_WORKFLOW_SHA':'a'*40,'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1'}
        facts={'head':'a'*40,'tree':'b'*40,'product_tree':host.PRODUCT_CONTROL_TREE,'dirty':'','paths':sorted(host.PROBE_PATHS),
               'chain':[{'sha':'a'*40,'parents':[host.PRODUCT_SHA],'paths':sorted(host.PROBE_PATHS)}]}
        return config,context,facts

    def testClosedFlagsStopBeforeGitOrNativeAndRuntimeEntryCannotBypass(self):
        from unittest.mock import patch
        config=json.loads((host.ROOT/host.PROBE_CONFIG).read_text())
        for key in ['READY','sourceReady','nativeAuthorization']:self.assertIs(config[key],False)
        with patch.object(host.subprocess,'check_output') as native,self.assertRaisesRegex(ValueError,'closed'):host.admit_probe()
        native.assert_not_called()
        with patch.object(host.subprocess,'check_output') as native,self.assertRaisesRegex(ValueError,'closed'):host.main()
        native.assert_not_called()
        import run_ios_photos_host_diagnostic as driver
        with patch.object(driver,'HostDiagnostic') as gate,self.assertRaisesRegex(ValueError,'closed'):driver.main()
        gate.assert_not_called()

    def testOnlyExactFinalSourceLinearControlAndExplicitAuthorityAdmit(self):
        c,e,f=self.values();result=host.validate_probe_admission(c,e,f)
        self.assertEqual(result['product_sha'],'13e9a1ed63c6e7744803419f27e429a759df1209');self.assertFalse(result['release_qualified'])
        mutations=[lambda c,e,f:c.update(READY=False),lambda c,e,f:c.update(sourceReady=False),lambda c,e,f:c.update(nativeAuthorization=False),
            lambda c,e,f:c.update(product_sha='16970bd1dcb4fd01fcfa5b1a1cf117c24f21b562'),lambda c,e,f:c.update(product_tree='8d144ec388b72ccf71d67fbec1f284120629e471'),
            lambda c,e,f:c.update(maximum_additional_spend_usd=True),lambda c,e,f:c.update(schema=True),lambda c,e,f:c.update(extra=1),
            lambda c,e,f:e.update(GITHUB_REF='refs/heads/cell-ios-photos-host-probe'),lambda c,e,f:e.update(GITHUB_RUN_ATTEMPT='2'),
            lambda c,e,f:e.update(GITHUB_WORKFLOW_SHA='c'*40),lambda c,e,f:f.update(dirty='M product'),
            lambda c,e,f:f['paths'].append('Celluloid/AppDelegate.swift'),lambda c,e,f:f['chain'][0]['paths'].append('Celluloid/AppDelegate.swift'),
            lambda c,e,f:f['chain'][0]['parents'].append('c'*40)]
        for mutate in mutations:
            c,e,f=self.values();mutate(c,e,f)
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):host.validate_probe_admission(c,e,f)

    def testExactProductAndReviewedProjectAndFiveNativeMethodsRemainPinned(self):
        import hashlib,re
        self.assertEqual(host.product_control(host.ROOT),(424,'7e2a14bb1d874776638aba24c648c7ec6171a270840fe8660f31eabeb784f4f3'))
        for path,digest in host.PROBE_FIXED_FILES.items():self.assertEqual(hashlib.sha256((host.ROOT/path).read_bytes()).hexdigest(),digest)
        swift=[host.ROOT/'CelluloidTests/IOSPhotosHostFixtureTests.swift',host.ROOT/'CelluloidUITests/IOSPhotosHostUITests.swift']
        self.assertEqual([len(re.findall(r'func (test\w+)\(',p.read_text())) for p in swift],[3,2])
        self.assertEqual([x[2] for x in host.STEPS],[45,165,45,165,45])

    def testAllOwnedVersionsAreCurrentAndOldNumericSplitMissingMetadataRejects(self):
        import plistlib
        with tempfile.TemporaryDirectory() as folder:
            app=Path(folder)/'Celluloid.app'
            paths=[app/'Info.plist',app/'Frameworks/CelluloidKit.framework/Info.plist',app/'PlugIns/CelluloidPhotoExtension.appex/Info.plist']
            good={'CFBundleShortVersionString':'1.1.1','CFBundleVersion':'3'}
            for path in paths:path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(plistlib.dumps(good))
            host.check_owned_versions(app)
            for path in paths:
                for wrong in [{'CFBundleShortVersionString':'1.1','CFBundleVersion':'2'},{**good,'CFBundleVersion':3},{**good,'CFBundleVersion':'2'},{'CFBundleVersion':'3'}]:
                    path.write_bytes(plistlib.dumps(wrong))
                    with self.subTest(path=path,value=wrong),self.assertRaises(ValueError):host.check_owned_versions(app)
                path.write_bytes(plistlib.dumps(good))
            host.check_owned_versions(app)

    def testWorkflowIsClosedSingleJobAndRealPortableEntryIsSiteFree(self):
        import hashlib,re
        text=(host.ROOT/host.PROBE_WORKFLOW).read_text()
        self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),'69f207e7a82e625b4a5bf14eb0af563228d0884ea5928865aef7342c6b3897bb')
        self.assertEqual(re.findall(r'^  ([a-z][a-z0-9-]*):$',text.split('jobs:\n',1)[1],re.M),['actual-photos-host'])
        self.assertIn('    if: ${{ false &&',text);self.assertIn('    runs-on: xcode-27\n    timeout-minutes: 45\n',text)
        self.assertIn('    branches: [cell-ios-photos-host-final]',text)
        self.assertIn('python3 -S Scripts/run_ios_photos_host.py --admit-only',text)
        driver=(host.ROOT/'Scripts/run_ios_photos_host_diagnostic.py').read_text()
        self.assertIn("[sys.executable, '-S', 'Scripts/test_ios_photos_host.py']",driver)
        self.assertIn("self.command('actual-photos-host', command, 630",driver)
        self.assertIn("'work_budget_seconds': 2280",driver)


if __name__ == '__main__': unittest.main()
