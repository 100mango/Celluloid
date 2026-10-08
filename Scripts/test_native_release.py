#!/usr/bin/env python3
"""Synthetic packaging-checker regression; does not claim an Apple compilation."""
import json,os,plistlib,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class ReleaseCheckerTests(unittest.TestCase):
    def check_watch(self,folder,*,debug=False,icon=True, legacy_floor="9.0", modern_floor="26.0", archs="arm64 arm64_32", platform="watch", primary=None, marker=b'sandbox.probe'):
        app=folder/'CelluloidWatch.app';app.mkdir()
        info={'CFBundleIdentifier':'Mango.Celluloid.watchkitapp','CFBundleExecutable':'CelluloidWatch',
              'DTPlatformName':'watchos','DTSDKName':'watchos27.0','MinimumOSVersion':'9.0',
              'CFBundleShortVersionString':'1.1','CFBundleVersion':'2','WKApplication':True,'WKCompanionAppBundleIdentifier':'Mango.Celluloid'}
        if icon:info['CFBundleIconName']='AppIcon'
        if platform=='tv':
            info.update(CFBundleIdentifier='Mango.Celluloid',CFBundleExecutable='CelluloidTV',DTPlatformName='appletvos',DTSDKName='appletvos27.0',MinimumOSVersion='17.0')
            info.pop('CFBundleIconName',None);info['CFBundleIcons']={'CFBundlePrimaryIcon':primary}
            (app/'PrivacyInfo.xcprivacy').write_bytes((ROOT/'Platforms/tvOS/PrivacyInfo.xcprivacy').read_bytes())
        (app/'Info.plist').write_bytes(plistlib.dumps(info))
        (app/'LICENSE.txt').write_bytes((ROOT/'LICENSE.txt').read_bytes());(app/'Assets.car').write_bytes(b'synthetic catalog')
        (app/info['CFBundleExecutable']).write_bytes(b'synthetic executable'+(marker if debug else b''))
        for language in ['en','zh-Hans']:
            p=app/(language+'.lproj');p.mkdir();(p/'Localizable.strings').write_text('"sample"="sample";')
        if platform=='tv':
            for language in ['en','zh-Hans']:(app/(language+'.lproj')/'InfoPlist.strings').write_text('"NSPhotoLibraryUsageDescription"="Synthetic";')
        tool=folder/'xcrun'
        catalog=json.dumps([{'Name':'Small' if platform=='tv' else 'AppIcon','AssetType':'Icon Image','PixelWidth':1024}])
        tool.write_text('#!/bin/sh\nif [ "$1" = "assetutil" ]; then echo \''+catalog+'\'; elif [ "$1" = "lipo" ]; then echo '+archs+'; elif [ "$3" = "arm64_32" ]; then echo "minos '+legacy_floor+'"; else echo "minos '+modern_floor+'"; fi\n');tool.chmod(0o700)
        return subprocess.run(['python3',str(ROOT/'Scripts/verify_native_release.py'),platform,str(app)],env=dict(os.environ,PATH=str(folder)+os.pathsep+os.environ['PATH'],RUNNER_TEMP=str(folder),GITHUB_SHA='synthetic'),capture_output=True,text=True)
    def test_expected_watch_metadata_passes(self):
        with tempfile.TemporaryDirectory() as d:
            result=self.check_watch(Path(d));self.assertEqual(result.returncode,0,result.stderr)
            report=json.loads((Path(d)/'watch-release-packaging.json').read_text());self.assertTrue(all(report['checks'].values()))
    def test_missing_icon_and_debug_seam_fail_with_retained_report(self):
        with tempfile.TemporaryDirectory() as d:
            result=self.check_watch(Path(d),debug=True,icon=False);self.assertNotEqual(result.returncode,0)
            report=json.loads((Path(d)/'watch-release-packaging.json').read_text());self.assertFalse(report['checks']['brand_icon_packaged']);self.assertFalse(report['checks']['debug_seams_absent'])
    def test_watch_rejects_raised_legacy_floor_and_missing_legacy_slice(self):
        for changes in [dict(legacy_floor='10.0'),dict(modern_floor='27.0'),dict(archs='arm64')]:
            with self.subTest(changes=changes),tempfile.TemporaryDirectory() as d:
                result=self.check_watch(Path(d),**changes);self.assertNotEqual(result.returncode,0)
                report=json.loads((Path(d)/'watch-release-packaging.json').read_text());self.assertFalse(all(report['checks'].values()))
    def test_tv_string_icon_schema_and_invalid_names_always_report(self):
        for icon,success in [('Small',True),('Unrelated',False),({'CFBundleIconName':'Small'},False)]:
            with self.subTest(icon=icon),tempfile.TemporaryDirectory() as d:
                result=self.check_watch(Path(d),platform='tv',primary=icon,archs='arm64',modern_floor='17.0')
                report=json.loads((Path(d)/'tv-release-packaging.json').read_text())
                self.assertEqual(result.returncode==0,success,result.stderr);self.assertEqual(report['checks']['brand_icon_packaged'],success)
    def test_tv_largest_trait_test_seam_is_rejected_from_release(self):
        for marker in [b'CELLULOID_TV_LARGEST_TRAIT_STRESS',b'tv.instruction.accessibility5',b'tv.instruction.ordinary']:
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as d:
                result=self.check_watch(Path(d),platform='tv',primary='Small',archs='arm64',modern_floor='17.0',debug=True,marker=marker)
                report=json.loads((Path(d)/'tv-release-packaging.json').read_text())
                self.assertNotEqual(result.returncode,0);self.assertFalse(report['checks']['debug_seams_absent'])
if __name__=='__main__':unittest.main()
