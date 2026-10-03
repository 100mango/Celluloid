"""Synthetic checker regression only; not Apple compilation or packaging proof."""
from pathlib import Path
import json
import os
import plistlib
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PhoneReleaseGuardTests(unittest.TestCase):
    def check(self, marker=False, floor='15.0'):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);app=root/'CelluloidPhoneCompanion.app';app.mkdir()
            info={'CFBundleIdentifier':'Mango.Celluloid','CFBundleExecutable':'CelluloidPhoneCompanion',
                  'CFBundleDisplayName':'Celluloid Companion Validation','DTPlatformName':'iphoneos',
                  'MinimumOSVersion':floor,'CFBundleShortVersionString':'2.0','CFBundleVersion':'2'}
            (app/'Info.plist').write_bytes(plistlib.dumps(info))
            (app/'CelluloidPhoneCompanion').write_bytes(b'CI checker synthetic placeholder'+(b'CELLULOID_PHONE_OUTPUT_PROOF' if marker else b''))
            tools=root/'bin';tools.mkdir();mock=tools/'xcrun'
            mock.write_text('#!/bin/sh\nif test "$1" = lipo; then echo arm64; else printf "platform IOS\\nminos 15.0\\n"; fi\n');mock.chmod(0o755)
            result=subprocess.run(['python3',str(ROOT/'Scripts/verify_phone_harness_release.py'),str(app)],capture_output=True,text=True,env=dict(os.environ,RUNNER_TEMP=directory,GITHUB_SHA='synthetic',PATH=str(tools)+os.pathsep+os.environ['PATH']))
            return result,json.loads((root/'phone-harness-release.json').read_text())

    def test_debug_marker_and_minimum_are_enforced(self):
        valid,report=self.check();self.assertEqual(valid.returncode,0,valid.stderr)
        self.assertTrue(all(report['checks'].values()))
        marked,report=self.check(marker=True);self.assertNotEqual(marked.returncode,0)
        self.assertFalse(report['checks']['debug_proof_and_seed_absent'])
        wrong,report=self.check(floor='16.0');self.assertNotEqual(wrong.returncode,0)
        self.assertFalse(report['checks']['minimum_os'])


if __name__=='__main__':unittest.main()
