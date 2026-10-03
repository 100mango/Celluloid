#!/usr/bin/env python3
"""Synthetic packaging-checker regression; does not claim an Apple compilation."""
import json,os,plistlib,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class ReleaseCheckerTests(unittest.TestCase):
    def check_watch(self,folder,*,debug=False,icon=True):
        app=folder/'CelluloidWatch.app';app.mkdir()
        info={'CFBundleIdentifier':'Mango.Celluloid.watchkitapp','CFBundleExecutable':'CelluloidWatch',
              'DTPlatformName':'watchos','DTSDKName':'watchos27.0','MinimumOSVersion':'9.0',
              'CFBundleShortVersionString':'2.0','CFBundleVersion':'2','WKApplication':True,'WKCompanionAppBundleIdentifier':'Mango.Celluloid'}
        if icon:info['CFBundleIconName']='AppIcon'
        (app/'Info.plist').write_bytes(plistlib.dumps(info))
        (app/'LICENSE.txt').write_bytes((ROOT/'LICENSE.txt').read_bytes());(app/'Assets.car').write_bytes(b'synthetic catalog')
        (app/'CelluloidWatch').write_bytes(b'synthetic executable'+(b'sandbox.probe' if debug else b''))
        for language in ['en','zh-Hans']:
            p=app/(language+'.lproj');p.mkdir();(p/'Localizable.strings').write_text('"sample"="sample";')
        tool=folder/'xcrun';tool.write_text('#!/bin/sh\nif [ "$1" = "lipo" ]; then echo arm64; else printf "platform WATCHOS\\nminos 9.0\\nsdk 27.0\\n"; fi\n');tool.chmod(0o700)
        return subprocess.run(['python3',str(ROOT/'Scripts/verify_native_release.py'),'watch',str(app)],env=dict(os.environ,PATH=str(folder)+os.pathsep+os.environ['PATH'],RUNNER_TEMP=str(folder),GITHUB_SHA='synthetic'),capture_output=True,text=True)
    def test_expected_watch_metadata_passes(self):
        with tempfile.TemporaryDirectory() as d:
            result=self.check_watch(Path(d));self.assertEqual(result.returncode,0,result.stderr)
            report=json.loads((Path(d)/'watch-release-packaging.json').read_text());self.assertTrue(all(report['checks'].values()))
    def test_missing_icon_and_debug_seam_fail_with_retained_report(self):
        with tempfile.TemporaryDirectory() as d:
            result=self.check_watch(Path(d),debug=True,icon=False);self.assertNotEqual(result.returncode,0)
            report=json.loads((Path(d)/'watch-release-packaging.json').read_text());self.assertFalse(report['checks']['brand_icon_packaged']);self.assertFalse(report['checks']['debug_seams_absent'])
if __name__=='__main__':unittest.main()
