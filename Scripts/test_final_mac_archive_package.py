"""Focused synthetic Mac archive adjunct tests. No Apple tool is run here."""
import copy
import json
import os
from pathlib import Path
import plistlib
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch
import final_mac_archive_package as package

ROOT=Path(__file__).resolve().parents[1]
UUIDS={'arm64':'3C686DFA-9065-4D31-AD75-384CFB878679','x86_64':'721711AD-2D89-49E4-B3EC-6324E3200F52'}


def fixture(folder):
    # macOS /var -> /private/var and similar trusted temporary-root aliases are
    # normalized here only. The production reader still rejects member aliases.
    root=Path(folder).resolve(strict=True);archive=root/package.ARCHIVE;app=archive/package.APP
    app.mkdir(parents=True);extension=app/package.EXTENSION;extension.mkdir(parents=True)
    for source in ['Platforms/Resources','Platforms/macOS','Platforms/macOSExtension',*package.BUNDLES.values()]:
        shutil.copytree(ROOT/source,root/source)
    shutil.copy2(ROOT/'LICENSE.txt',root/'LICENSE.txt')
    (root/'Scripts').mkdir()
    shutil.copy2(ROOT/'Scripts/verify_native_release.py',root/'Scripts/verify_native_release.py')
    for label,bundle in [('app',app),('extension',extension)]:
        name,dsym=package.PRODUCTS[label];base=bundle/'Contents';resources=base/'Resources';resources.mkdir(parents=True)
        for name_,source in [('LICENSE.txt','LICENSE.txt'),('PrivacyPolicy.txt','Platforms/Resources/PrivacyPolicy.txt')]:shutil.copy2(root/source,resources/name_)
        for lang in ['en','zh-Hans']:
            (resources/(lang+'.lproj')).mkdir()
            raw=package.source_strings((root/'Platforms/Resources'/(lang+'.lproj')/'Localizable.strings').read_bytes())
            (resources/(lang+'.lproj')/'Localizable.strings').write_bytes(plistlib.dumps(raw,fmt=plistlib.FMT_BINARY))
        for name_,source in package.BUNDLES.items():
            location=resources/name_/'Contents';shutil.copytree(root/source,location/'Resources')
            (location/'Info.plist').write_bytes(plistlib.dumps({'CFBundlePackageType':'BNDL'}))
        source=root/('Platforms/macOS' if label=='app' else 'Platforms/macOSExtension')/'Info.plist'
        info=plistlib.loads(source.read_bytes())
        info.update(CFBundleIdentifier='Mango.Celluloid'+('.CelluloidPhotoExtension' if label=='extension' else ''),CFBundleExecutable=name,
            CFBundleShortVersionString='1.1.1',CFBundleVersion='3',DTPlatformName='macosx',DTSDKName='macosx27.0',LSMinimumSystemVersion='13.0')
        if label=='extension':info['NSExtension']['NSExtensionPrincipalClass']='CelluloidMacPhotosExtension.MacPhotoEditingController'
        (base/'Info.plist').write_bytes(plistlib.dumps(info))
        (base/'MacOS').mkdir();(base/'MacOS'/name).write_bytes(b'\xca\xfe\xba\xbe'+b'synthetic universal executable '+label.encode())
        symbol=archive/'dSYMs'/dsym/'Contents/Resources/DWARF'/name
        symbol.parent.mkdir(parents=True);symbol.write_bytes(b'\xca\xfe\xba\xbe'+b'synthetic universal symbol '+label.encode())
    (archive/'Info.plist').write_bytes(plistlib.dumps({'ArchiveVersion':2,'ApplicationProperties':{'ApplicationPath':'Applications/CelluloidMac.app','CFBundleIdentifier':'Mango.Celluloid','CFBundleShortVersionString':'1.1.1','CFBundleVersion':'3'}}))
    return root,archive,app,extension


class Commands:
    blocked=False
    mismatch=False
    ext_archs=None
    fail_check=False
    linked_floor='13.0'
    def __init__(self,root,app):self.root=root;self.app=app;self.seen=[]
    def run(self,argv,**kwargs):
        self.seen.append(argv)
        if argv[0]=='xcrun':
            if argv[1]=='lipo':return (' '.join(self.ext_archs if self.ext_archs and 'Extension' in argv[-1] else UUIDS)+'\n').encode()
            if argv[1]=='dwarfdump':
                return ''.join(f'UUID: {"00000000-0000-0000-0000-000000000000" if self.mismatch and "dSYMs" in argv[-1] else value} ({arch}) {argv[-1]}\n' for arch,value in UUIDS.items()).encode()
            if argv[1]=='vtool':return f'{argv[-1]}:\nLoad command 1\n cmd LC_BUILD_VERSION\n platform MACOS\n minos {self.linked_floor}\n sdk 27.0\n'.encode()
            if argv[1]=='otool':return b'Load command 1\n cmd LC_CODE_SIGNATURE\n'
            raise ValueError('unexpected fixture command')
        report={'source_sha':package.SOURCE,'platform':'mac','product':str(self.app),'checks':{key:True for key in package.EXPECTED_CHECKS},
            'architectures':list(UUIDS),'binary_sha256':package.sha((self.app/'Contents/MacOS/CelluloidMac').read_bytes())}
        if self.fail_check:report['checks']['native_text_hooks_absent_from_extension']=False
        (self.root/'mac-release-packaging.json').write_text(json.dumps(report));return b''


class PackageTests(unittest.TestCase):
    def test_proven_checker_and_current_source_graph(self):
        self.assertEqual(package.sha((ROOT/'Scripts/verify_native_release.py').read_bytes()),package.CHECKER_SHA256)
        graph=package.source_graph(ROOT)
        for path in ['Platforms/macOS/CelluloidMacApp.swift','Platforms/macOSExtension/MacPhotoEditingController.swift',
                     'Platforms/macOS/CelluloidMac.entitlements','Scripts/native_text_release_guard.py']:
            self.assertIn(path,graph)
        self.assertFalse(any('Generated' in name for name in graph));self.assertGreater(len(graph),100)

    def test_xcarchive_metadata_rejects_generic_build_and_stale_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root,archive,app,extension=fixture(temp);package.archive_metadata(archive)
            path=archive/'Info.plist';value=plistlib.loads(path.read_bytes())
            for key,bad in [('ApplicationPath','CelluloidMac.app'),('CFBundleIdentifier','wrong'),('CFBundleVersion','2'),('CFBundleShortVersionString','1.1')]:
                changed=copy.deepcopy(value);changed['ApplicationProperties'][key]=bad;path.write_bytes(plistlib.dumps(changed))
                with self.assertRaises(ValueError):package.archive_metadata(archive)
            path.write_bytes(plistlib.dumps(value));(archive/'Products/Applications/Unexpected.app').mkdir()
            with self.assertRaises(ValueError):package.archive_metadata(archive)

    def test_archive_rejects_missing_symbols_extra_extensions_tests_and_provisioning(self):
        with tempfile.TemporaryDirectory() as temp:
            root,archive,app,extension=fixture(temp)
            for relative in ['Products/Applications/CelluloidMac.app/Contents/PlugIns/Unexpected.appex',
                'unexpected.appex','extra.xctest','embedded.provisionprofile','embedded.mobileprovision','extra.debug.dylib','dSYMs/extra.dSYM']:
                path=archive/relative;path.mkdir(parents=True)
                with self.assertRaises(ValueError):package.archive_metadata(archive)
                path.rmdir()
            symbol=archive/'dSYMs/CelluloidMacPhotosExtension.appex.dSYM';shutil.rmtree(symbol)
            with self.assertRaises(ValueError):package.archive_metadata(archive)

    def test_embedded_extension_identity_version_and_photos_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            root,archive,app,extension=fixture(temp);package.product_metadata(app,extension)
            path=extension/'Contents/Info.plist';original=path.read_bytes();info=plistlib.loads(original)
            for key,bad in [('CFBundleVersion','2'),('CFBundleIdentifier','wrong'),('CFBundleExecutable','wrong'),
                ('DTPlatformName','iphonesimulator'),('DTSDKName','macosxsimulator27.0'),('LSMinimumSystemVersion','14.0'),
                ('CFBundleLocalizations',['en']),('NSExtension',{'NSExtensionPointIdentifier':'wrong'})]:
                value=copy.deepcopy(info);value[key]=bad;path.write_bytes(plistlib.dumps(value))
                with self.assertRaises(ValueError):package.product_metadata(app,extension)
            path.write_bytes(original)

    def test_resources_both_hosts_semantic_strings_exact_membership(self):
        with tempfile.TemporaryDirectory() as temp:
            root,archive,app,extension=fixture(temp)
            for host in (app,extension):
                proof=package.resource_inventory(root,host,time.monotonic()+20);self.assertGreater(len(proof),50)
                resources=host/'Contents/Resources';path=resources/'zh-Hans.lproj/Localizable.strings';original=path.read_bytes()
                path.write_bytes(plistlib.dumps({'Celluloid':'Wrong'}))
                with self.assertRaises(ValueError):package.resource_inventory(root,host,time.monotonic()+20)
                path.write_bytes(original)
                extra=resources/'CelluloidCore_CelluloidDomain.bundle/Contents/Resources/unexpected.txt';extra.write_text('unexpected')
                with self.assertRaises(ValueError):package.resource_inventory(root,host,time.monotonic()+20)
                extra.unlink();path=resources/'CelluloidRendering_CelluloidRendering.bundle/Contents/Resources/46.png';original=path.read_bytes();path.unlink()
                with self.assertRaises(ValueError):package.resource_inventory(root,host,time.monotonic()+20)
                path.write_bytes(original)

    def test_uuid_rows_require_native_arm_and_unique_valid_architectures(self):
        good=''.join(f'UUID: {value} ({arch}) /path with space/CelluloidMac\n' for arch,value in UUIDS.items()).encode()
        self.assertEqual(package.uuids(good),UUIDS)
        self.assertEqual(package.uuids(good.splitlines(keepends=True)[0]),{'arm64':UUIDS['arm64']})
        for raw in (b'',good+good,good.replace(b'arm64',b'i386'),good.replace(b'UUID:',b'BAD:'),good.splitlines(keepends=True)[1]):
            with self.assertRaises(ValueError):package.uuids(raw)

    def test_linked_platform_floor_and_extension_architecture_must_match(self):
        for raw in (b'platform IOS\n minos 13.0',b'platform MACOS\n minos 14.0',b'platform MACOS\n minos 13.0\n minos 13.0'):
            with self.assertRaises(ValueError):package.linked_slice(raw)
        with tempfile.TemporaryDirectory() as temp:
            root,archive,app,extension=fixture(temp);commands=Commands(root,app);commands.ext_archs=['arm64']
            with patch.dict(os.environ,{'RUNNER_TEMP':str(root),'GITHUB_SHA':'control'}),self.assertRaisesRegex(ValueError,'architecture-mismatch'):
                package.verify_package(root,time.monotonic()+20,commands=commands)

    def test_complete_package_records_both_dsyms_and_never_claims_runtime_signing(self):
        with tempfile.TemporaryDirectory() as temp:
            root,archive,app,extension=fixture(temp);commands=Commands(root,app)
            with patch.dict(os.environ,{'RUNNER_TEMP':str(root),'GITHUB_SHA':'control'}):
                result=package.verify_package(root,time.monotonic()+20,commands=commands)
                self.assertTrue(result['actual_xcarchive']);self.assertTrue(result['unsigned_package_verified'])
                self.assertEqual(set(result['binaries']),{'app','extension'});self.assertEqual(set(result['resource_inventory']),{'app','extension'})
                for key in ('release_acceptance','signing_qualified','mac_photos_host_qualified','mac_layered_guard_qualified','signed_sandbox_qualified'):
                    self.assertIs(result[key],False)
                self.assertEqual(os.environ['GITHUB_SHA'],'control')
                self.assertTrue(result['binaries']['app']['code_signature_load_command_present'])
            self.assertEqual(len(commands.seen),13)

    def test_dsym_mismatch_native_checker_failure_and_modified_checker_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root,archive,app,extension=fixture(temp);commands=Commands(root,app)
            with patch.dict(os.environ,{'RUNNER_TEMP':str(root),'GITHUB_SHA':'control'}):
                commands.mismatch=True
                with self.assertRaisesRegex(ValueError,'dsym-uuid-mismatch'):package.verify_package(root,time.monotonic()+20,commands=commands)
                commands.mismatch=False;commands.fail_check=True
                with self.assertRaisesRegex(ValueError,'original-package-checks'):package.verify_package(root,time.monotonic()+20,commands=commands)
                commands.fail_check=False;(root/'Scripts/verify_native_release.py').write_text('changed')
                with self.assertRaisesRegex(ValueError,'proven-checker-drift'):package.verify_package(root,time.monotonic()+20,commands=commands)

    def test_fixture_parent_alias_normalizes_but_product_aliases_and_hardlinks_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            parent=Path(temp).resolve(strict=True);real=parent/'real';real.mkdir();alias=parent/'alias';alias.symlink_to(real,target_is_directory=True)
            root,archive,app,extension=fixture(alias);self.assertEqual(root,real);self.assertEqual(archive.resolve(strict=True),archive)
            package.archive_metadata(archive);package.resource_inventory(root,extension,time.monotonic()+20)
            leaf=app/'leaf-alias';leaf.symlink_to(archive/'Info.plist')
            with self.assertRaises(ValueError):package.read(leaf)
            resources=extension/'Contents/Resources';inner=resources/'internal-alias';inner.symlink_to(resources/'en.lproj',target_is_directory=True)
            with self.assertRaises(ValueError):package.read(inner/'Localizable.strings')
            normal=resources/'LICENSE.txt';package.read(normal);os.link(normal,resources/'hardlinked-license')
            with self.assertRaises(ValueError):package.read(normal)


if __name__=='__main__':unittest.main()
