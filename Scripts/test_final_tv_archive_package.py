"""Focused synthetic TV archive adjunct tests. No Apple tool is run here."""
import json
import os
from pathlib import Path
import plistlib
import shutil
import struct
import tempfile
import time
import unittest
from unittest.mock import patch
import final_tv_archive_package as package

ROOT=Path(__file__).resolve().parents[1]
UUID='3C686DFA-9065-4D31-AD75-384CFB878679'


def fixture(folder):
    root=Path(folder);app=root/package.ARCHIVE/package.APP;app.mkdir(parents=True)
    for source in ['Platforms/Resources','Platforms/tvOS','Packages/CelluloidCore/Sources/CelluloidDomain/Resources','Packages/CelluloidRendering/Sources/CelluloidRendering/Resources']:
        shutil.copytree(ROOT/source,root/source)
    shutil.copy2(ROOT/'LICENSE.txt',root/'LICENSE.txt')
    (root/'Scripts').mkdir();shutil.copy2(ROOT/'Scripts/verify_native_release.py',root/'Scripts/verify_native_release.py')
    for name,source in [('LICENSE.txt','LICENSE.txt'),('PrivacyPolicy.txt','Platforms/Resources/PrivacyPolicy.txt'),('PrivacyInfo.xcprivacy','Platforms/tvOS/PrivacyInfo.xcprivacy')]:shutil.copy2(root/source,app/name)
    for lang in ['en','zh-Hans']:
        (app/(lang+'.lproj')).mkdir()
        for name,source in [('Localizable.strings','Platforms/Resources'),('InfoPlist.strings','Platforms/tvOS')]:
            raw=package.source_strings((root/source/(lang+'.lproj')/name).read_bytes())
            (app/(lang+'.lproj')/name).write_bytes(plistlib.dumps(raw,fmt=plistlib.FMT_BINARY))
    for name,source in [('CelluloidCore_CelluloidDomain.bundle','Packages/CelluloidCore/Sources/CelluloidDomain/Resources'),('CelluloidRendering_CelluloidRendering.bundle','Packages/CelluloidRendering/Sources/CelluloidRendering/Resources')]:
        shutil.copytree(root/source,app/name)
    archive=root/package.ARCHIVE
    (archive/'Info.plist').write_bytes(plistlib.dumps({'ArchiveVersion':2,'ApplicationProperties':{'ApplicationPath':'Applications/CelluloidTV.app','CFBundleIdentifier':'Mango.Celluloid','CFBundleShortVersionString':'1.1.1','CFBundleVersion':'3'}}))
    symbol=archive/package.DSYM;symbol.parent.mkdir(parents=True);symbol.write_bytes(b'\xcf\xfa\xed\xfe'+b'synthetic symbol')
    (app/'CelluloidTV').write_bytes(b'synthetic executable')
    return root,archive,app


class PackageTests(unittest.TestCase):
    def test_proven_checker_and_current_source_graph(self):
        self.assertEqual(package.sha((ROOT/'Scripts/verify_native_release.py').read_bytes()),package.CHECKER_SHA256)
        graph=package.source_graph(ROOT)
        self.assertIn('Platforms/tvOS/CelluloidTVApp.swift',graph)
        self.assertFalse(any('Generated' in name for name in graph))
        self.assertGreater(len(graph),100)

    def test_xcarchive_metadata_rejects_build_folder_and_stale_version(self):
        with tempfile.TemporaryDirectory() as temp:
            root,archive,app=fixture(temp);package.archive_metadata(archive)
            path=archive/'Info.plist';value=plistlib.loads(path.read_bytes())
            for key,bad in [('ApplicationPath','CelluloidTV.app'),('CFBundleVersion','2'),('CFBundleShortVersionString','1.1')]:
                changed=json.loads(json.dumps(value));changed['ApplicationProperties'][key]=bad;path.write_bytes(plistlib.dumps(changed))
                with self.assertRaises(ValueError):package.archive_metadata(archive)
            path.write_bytes(plistlib.dumps(value));(archive/'Products/Applications/Unexpected.app').mkdir()
            with self.assertRaises(ValueError):package.archive_metadata(archive)

    def test_exact_resource_membership_and_localization_semantics(self):
        with tempfile.TemporaryDirectory() as temp:
            root,archive,app=fixture(temp);proof=package.resource_inventory(root,app,time.monotonic()+20)
            self.assertGreater(len(proof),50)
            path=app/'zh-Hans.lproj/Localizable.strings';original=path.read_bytes();path.write_bytes(plistlib.dumps({'Celluloid':'Wrong'}))
            with self.assertRaises(ValueError):package.resource_inventory(root,app,time.monotonic()+20)
            path.write_bytes(original)
            extra=app/'CelluloidCore_CelluloidDomain.bundle/unexpected.txt';extra.write_text('unexpected')
            with self.assertRaises(ValueError):package.resource_inventory(root,app,time.monotonic()+20)
            extra.unlink();(app/'CelluloidRendering_CelluloidRendering.bundle/46.png').unlink()
            with self.assertRaises(ValueError):package.resource_inventory(root,app,time.monotonic()+20)

    def test_uuid_observations_require_device_slice_and_unique_rows(self):
        good=f'UUID: {UUID} (arm64) /path with space/CelluloidTV\n'.encode()
        self.assertEqual(package.uuids(good),{'arm64':UUID})
        for raw in (b'',good+good,good.replace(b'arm64',b'x86_64'),good.replace(b'UUID:',b'BAD:')):
            with self.assertRaises(ValueError):package.uuids(raw)

    def test_complete_synthetic_package_and_dsym_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            root,archive,app=fixture(temp);seen=[]
            class Commands:
                blocked=False
                mismatch=False
                def run(self,argv,**kwargs):
                    seen.append(argv)
                    if argv[0]=='xcrun':
                        value='00000000-0000-0000-0000-000000000000' if self.mismatch and 'dSYMs' in argv[-1] else UUID
                        return f'UUID: {value} (arm64) {argv[-1]}\n'.encode()
                    report={'source_sha':package.SOURCE,'platform':'tv','product':str(app),'checks':{key:True for key in package.EXPECTED_CHECKS},'architectures':['arm64'],'binary_sha256':package.sha((app/'CelluloidTV').read_bytes())}
                    (root/'tv-release-packaging.json').write_text(json.dumps(report));return b''
            commands=Commands()
            with patch.dict(os.environ,{'RUNNER_TEMP':str(root),'GITHUB_SHA':'control'}):
                result=package.verify_package(root,time.monotonic()+20,commands=commands)
                self.assertTrue(result['actual_xcarchive']);self.assertTrue(result['unsigned_package_verified'])
                self.assertIs(result['release_acceptance'],False);self.assertEqual(os.environ['GITHUB_SHA'],'control')
                commands.mismatch=True
                with self.assertRaisesRegex(ValueError,'dsym-uuid-mismatch'):package.verify_package(root,time.monotonic()+20,commands=commands)
            self.assertEqual(len(seen),6)

    def test_symlink_and_hardlink_resource_reads_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=root/'real';path.write_bytes(b'real');alias=root/'alias';alias.symlink_to(path)
            with self.assertRaises(ValueError):package.read(alias)
            alias.unlink();os.link(path,alias)
            with self.assertRaises(ValueError):package.read(path)


if __name__=='__main__':unittest.main()
