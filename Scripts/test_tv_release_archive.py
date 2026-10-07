"""Synthetic archive/clock regressions only. No native archive or upload is run."""
import copy
import datetime
import json
import os
from pathlib import Path
import plistlib
import shutil
import struct
import subprocess
import tempfile
import time
import sys
import unittest
import zlib
from unittest.mock import patch

import tv_release_archive as archive


UUID = '12345678-1234-1234-1234-123456789ABC'


# Representative system framework and Swift-overlay paths; synthetic, not QR native link proof.
SYNTHETIC_SYSTEM_LIBRARIES = ('/System/Library/Frameworks/Photos.framework/Photos', '/System/Library/Frameworks/CoreImage.framework/CoreImage', '/usr/lib/swift/libswiftCore.dylib', '/usr/lib/libSystem.B.dylib')


def environment():
    return {'GITHUB_REPOSITORY': '100mango/Celluloid', 'GITHUB_REF': archive.BRANCH,
        'GITHUB_WORKFLOW_REF': '100mango/Celluloid/' + archive.WORKFLOW + '@' + archive.BRANCH,
        'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_JOB': 'archive', 'GITHUB_EVENT_NAME': 'push',
        'GITHUB_RUN_ID': '12345', 'GITHUB_SHA': 'a' * 40, 'GITHUB_WORKFLOW_SHA': 'a' * 40,
        'DEVELOPER_DIR': '/Applications/Xcode_27.app/Contents/Developer'}


def macho(platform=3, minimum=17, kind=2, cpu=0x100000c, payload=b'TVMainView', links=()):
    commands=[struct.pack('<6I',0x32,24,platform,minimum<<16,27<<16,0)]
    for link in links:
        text=link.encode()+b'\0';size=(24+len(text)+7)//8*8
        commands.append(struct.pack('<6I',0xc,size,24,0,0,0)+text+b'\0'*(size-24-len(text)))
    commands=b''.join(commands)
    return struct.pack('<8I',0xfeedfacf,cpu,0,kind,1+len(links),len(commands),0,0)+commands+payload

def png_icon(width=32, height=24, *, cgbi=False):
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    raw=b'\x89PNG\r\n\x1a\n'
    if cgbi:raw+=chunk(b'CgBI',b'\x00'*4)
    raw+=chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))
    # Valid ordinary fixtures encode every row; oversized/invalid-dimension cases
    # remain tiny because dimension validation must reject before pixel decoding.
    w,h=(width,height) if 0 < width <= 1280 and 0 < height <= 768 else (1,1)
    raw+=chunk(b'IDAT',zlib.compress((b'\x00'+b'\xff\xff\xff'*w)*h))
    return raw+chunk(b'IEND',b'')


class Fixture:
    def __init__(self,parent):
        self.root=parent/'source';self.root.mkdir()
        self.app=parent/'products/CelluloidTV.app';self.app.mkdir(parents=True)
        contract=archive.package.contract()
        paths=set(contract['unchanged_inputs'])|set(contract['asset_catalog_files'])|{'Scripts/tv_release_contract.json'}
        for name in paths:
            target=self.root/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(archive.ROOT/name,target)
        self.metadata={'CFBundleIdentifier':'Mango.Celluloid','CFBundleExecutable':'CelluloidTV',
            'CFBundleName':'Celluloid','CFBundlePackageType':'APPL',
            'CFBundleVersion':'2','CFBundleShortVersionString':'1.1','MinimumOSVersion':'17.0',
            'CFBundleSupportedPlatforms':['AppleTVOS'],'UIDeviceFamily':[3],
            'CFBundleIcons':{'CFBundlePrimaryIcon':'Small'},'DTSDKName':'appletvos27.0','DTPlatformName':'appletvos',
            'TVTopShelfImage':{'TVTopShelfPrimaryImage':'TopShelf','TVTopShelfPrimaryImageWide':'TopShelfWide'},
            'NSPhotoLibraryUsageDescription':'Choose photos to edit and verify pictures you save.',
            'NSPhotoLibraryAddUsageDescription':'Save your finished Celluloid pictures to Photos.'}
        self.write_info()
        (self.app/'Assets.car').write_bytes(b'synthetic compiled assets; not native CAR proof'*4)
        (self.app/'PkgInfo').write_bytes(b'APPL????')
        (self.app/'PrivacyInfo.xcprivacy').write_bytes((self.root/'Platforms/tvOS/PrivacyInfo.xcprivacy').read_bytes())
        for locale in ('en','zh-Hans'):
            for name,folder in [('Localizable.strings','Platforms/Resources'),('InfoPlist.strings','Platforms/tvOS')]:
                target=self.app/locale.__add__('.lproj')/name;target.parent.mkdir(exist_ok=True)
                raw=(self.root/folder/locale.__add__('.lproj')/name).read_bytes()
                target.write_bytes(plistlib.dumps(archive.package.strings_dictionary(raw),fmt=plistlib.FMT_BINARY))
        for name,source in [('LICENSE.txt','LICENSE.txt'),('PrivacyPolicy.txt','Platforms/Resources/PrivacyPolicy.txt')]:
            (self.app/name).write_bytes((self.root/source).read_bytes())
        for bundle,resources in contract['package_resources'].items():
            for relative,source in resources.items():
                target=self.app/bundle/relative;target.parent.mkdir(parents=True,exist_ok=True)
                raw=(self.root/source).read_bytes()
                target.write_bytes(plistlib.dumps(archive.package.strings_dictionary(raw)) if relative.endswith('.strings') else raw)
            (self.app/bundle/'Info.plist').write_bytes(plistlib.dumps({'CFBundlePackageType':'BNDL'}))
        (self.app/'CelluloidTV').write_bytes(macho())
    def write_info(self):
        (self.app/'Info.plist').write_bytes(plistlib.dumps(self.metadata))


class ArchiveFixture:
    def __init__(self, parent):
        self.package = Fixture(parent)
        self.root = self.package.root
        self.archive = parent / 'CelluloidTV.xcarchive'
        self.app = self.archive / archive.APP
        self.app.parent.mkdir(parents=True)
        shutil.move(str(self.package.app), self.app)
        self.package.app = self.app
        self.dwarf = self.archive / archive.DWARF
        self.dwarf.parent.mkdir(parents=True)
        self.dwarf.write_bytes(struct.pack('<8I', 0xfeedfacf, 0x100000c, 0, 10, 1, 24, 0, 0) + b'synthetic DWARF')
        self.dsym_info = {'CFBundleIdentifier': 'com.apple.xcode.dsym.Mango.Celluloid',
                          'CFBundlePackageType': 'dSYM', 'CFBundleVersion': '2'}
        self.write_dsym()
        self.metadata = {'ArchiveVersion': 2, 'SchemeName': 'CelluloidTV',
            'CreationDate': datetime.datetime(2026, 10, 6, 12),
            'ApplicationProperties': {'ApplicationPath': 'Applications/CelluloidTV.app',
                'CFBundleIdentifier': 'Mango.Celluloid', 'CFBundleShortVersionString': '1.1',
                'CFBundleVersion': '2'}}
        self.write_metadata()
        self.calls = []

    def write_dsym(self):
        (self.archive / archive.DSYM / 'Contents/Info.plist').write_bytes(plistlib.dumps(self.dsym_info))

    def write_metadata(self):
        (self.archive / 'Info.plist').write_bytes(plistlib.dumps(self.metadata))

    def run(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if command[:3] == ['xcrun', 'assetutil', '--info']:
            return json.dumps([{'Name':name, 'PixelWidth':w, 'PixelHeight':h, 'Scale':scale} for name,w,h,scale in (('Small',400,240,1),('Small',800,480,2),('Large/Back/Content',1280,768,1),('TopShelf',1920,720,1),('TopShelfWide',2320,720,1))]).encode()
        return ''.join(f'UUID: {UUID} (arm64) {path}\n' for path in command[-2:]).encode()

    def verify(self, **kwargs):
        return archive.verify_archive(self.archive, kwargs.pop('run', self.run), 100,
            root=self.root, clock=kwargs.pop('clock', lambda: 0), **kwargs)


SYNTHETIC_QR_ARCHIVE_PATHS = ['Assets', 'Assets/ProductIcon.png', 'Info.plist', 'Products', 'Products/Applications', 'Products/Applications/CelluloidTV.app', 'Products/Applications/CelluloidTV.app/Assets.car', 'Products/Applications/CelluloidTV.app/Info.plist', 'Products/Applications/CelluloidTV.app/PkgInfo', 'Products/Applications/CelluloidTV.app/PrivacyInfo.xcprivacy', 'Products/Applications/CelluloidTV.app/CelluloidTV', 'Products/Applications/CelluloidTV.app/zh-Hans.lproj', 'Products/Applications/CelluloidTV.app/zh-Hans.lproj/Localizable.strings', 'dSYMs', 'dSYMs/CelluloidTV.app.dSYM', 'dSYMs/CelluloidTV.app.dSYM/Contents', 'dSYMs/CelluloidTV.app.dSYM/Contents/Info.plist', 'dSYMs/CelluloidTV.app.dSYM/Contents/Resources', 'dSYMs/CelluloidTV.app.dSYM/Contents/Resources/DWARF', 'dSYMs/CelluloidTV.app.dSYM/Contents/Resources/DWARF/CelluloidTV', 'dSYMs/CelluloidTV.app.dSYM/Contents/Resources/Relocations', 'dSYMs/CelluloidTV.app.dSYM/Contents/Resources/Relocations/aarch64', 'dSYMs/CelluloidTV.app.dSYM/Contents/Resources/Relocations/aarch64/CelluloidTV.yml']

class ArchiveTests(unittest.TestCase):
    def fixture(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        return ArchiveFixture(Path(temp.name))

    def test_synthetic_archive_uses_qr_source_resource_and_app_validator(self):
        f = self.fixture(); result = f.verify()
        self.assertEqual(result['arm64_uuid'], UUID)
        self.assertEqual(set(result['app']['files']), {'app/' + p for p in archive.APP_FILES})
        self.assertEqual(len(result['app']['files']), 65)
        self.assertEqual(result['app']['entries'], 67)
        self.assertEqual(set(result['app']['binaries']), {'app/CelluloidTV'})
        self.assertEqual(result['app']['metadata']['CFBundleIdentifier'], 'Mango.Celluloid')
        self.assertEqual(result['app']['source']['source_paths'], archive.package.source_graph()['source_paths'])
        self.assertEqual(len(f.calls), 2)
        self.assertEqual(f.calls[0][0][:3], ['xcrun', 'assetutil', '--info'])
        self.assertEqual(f.calls[1][0][:3], ['xcrun', 'dwarfdump', '--uuid'])
        self.assertEqual(f.calls[0][1]['cleanup'], 10)
        self.assertTrue(all(not Path(k).is_absolute() for k in result['archive']['paths']))
        for key, value in result['archive']['paths'].items():
            if 'sha256' in value: self.assertEqual(len(value['sha256']), 64)

    def test_archive_metadata_identity_and_product_path_reject(self):
        for key, value in [('ArchiveVersion', True), ('ArchiveVersion', 1), ('SchemeName', 'Other'),
                           ('CreationDate', '2026-10-06')]:
            f = self.fixture(); f.metadata[key] = value; f.write_metadata()
            with self.subTest(key=key), self.assertRaises(archive.Rejected): f.verify()
        for key, value in [('ApplicationPath', '../CelluloidTV.app'), ('CFBundleIdentifier', 'foreign'),
            ('CFBundleShortVersionString', '1.0'), ('CFBundleVersion', '1'), ('SigningIdentity', 'signed'), ('Team', 'foreign')]:
            f = self.fixture(); f.metadata['ApplicationProperties'][key] = value; f.write_metadata()
            with self.subTest(key=key), self.assertRaises(archive.Rejected): f.verify()

    def test_real_app_validation_rejects_identity_platform_minimum_and_resources(self):
        for key, value in [('CFBundleName', 'Other'), ('CFBundleVersion', '1'),
                           ('CFBundleSupportedPlatforms', ['iPhoneSimulator']), ('MinimumOSVersion', '15.0')]:
            f = self.fixture(); f.package.metadata[key] = value; f.package.write_info()
            with self.subTest(key=key), self.assertRaises(ValueError): f.verify()
        for change in ({'platform': 7}, {'minimum': 15}, {'kind': 6}, {'cpu': 0x1000007}):
            f = self.fixture(); (f.app / 'CelluloidTV').write_bytes(macho(**change))
            with self.subTest(change=change), self.assertRaises(ValueError): f.verify()
        for filename in ('Assets.car', 'PrivacyInfo.xcprivacy', 'zh-Hans.lproj/Localizable.strings'):
            f = self.fixture(); (f.app / filename).unlink()
            with self.subTest(filename=filename), self.assertRaises((ValueError,FileNotFoundError)): f.verify()
        f = self.fixture(); (f.app / 'extra.txt').write_bytes(b'extra')
        with self.assertRaisesRegex(archive.Rejected, 'resource-inventory'): f.verify()

    def test_extra_products_code_signatures_and_nonregular_entries_reject(self):
        for name in ('Products/Applications/Other.app', 'Products/Watch', 'Other',
            archive.APP + '/PlugIns/Other.appex', archive.APP + '/Frameworks/Other.framework',
            archive.APP + '/Tests.xctest', archive.APP + '/_CodeSignature',
            'dSYMs/Foreign.app.dSYM', archive.APP + '/QRFixtures.bundle'):
            f = self.fixture(); (f.archive / name).mkdir(parents=True)
            with self.subTest(name=name), self.assertRaises(archive.Rejected): f.verify()
        for name, raw in [('embedded.mobileprovision', b'profile'), ('CodeResources', b'signature'),
                          ('renamed', macho()), ('old32', b'\xce\xfa\xed\xfe' + b'\0' * 50)]:
            f = self.fixture(); (f.app / name).write_bytes(raw)
            with self.subTest(name=name), self.assertRaises(archive.Rejected): f.verify()
        f = self.fixture(); (f.app / 'linked').symlink_to(f.app / 'CelluloidTV')
        with self.assertRaisesRegex(archive.Rejected, 'linked-or-nonregular'): f.verify()
        f = self.fixture(); os.mkfifo(f.app / 'pipe')
        with self.assertRaisesRegex(archive.Rejected, 'linked-or-nonregular'): f.verify()
        f = self.fixture(); os.link(f.app / 'CelluloidTV', f.app / 'hardlink')
        with self.assertRaisesRegex(archive.Rejected, 'hardlink'): f.verify()
        f = self.fixture(); (f.archive / 'dSYMs').rename(f.archive / 'saved')
        (f.archive / 'dSYMs').symlink_to(f.archive / 'saved')
        with self.assertRaises(archive.Rejected): f.verify()

    def test_missing_foreign_or_non_dwarf_symbols_reject(self):
        f = self.fixture(); f.dwarf.unlink()
        with self.assertRaises(FileNotFoundError): f.verify()
        for key, value in [('CFBundleIdentifier', 'com.apple.xcode.dsym.foreign'), ('CFBundlePackageType', 'APPL')]:
            f = self.fixture(); f.dsym_info[key] = value; f.write_dsym()
            with self.subTest(key=key), self.assertRaisesRegex(archive.Rejected, 'dsym-metadata'): f.verify()
        for raw in (b'fake', macho(), struct.pack('<8I', 0xfeedfacf, 0x1000007, 0, 10, 1, 24, 0, 0)):
            f = self.fixture(); f.dwarf.write_bytes(raw)
            with self.assertRaises(archive.Rejected): f.verify()

    def test_dsym_versions_are_observed_comparisons_without_new_hard_gate(self):
        cases = [({}, 'missing', 'missing'),
            ({'CFBundleVersion': '2', 'CFBundleShortVersionString': '1.1'}, 'same', 'same'),
            ({'CFBundleVersion': '1', 'CFBundleShortVersionString': '1.0'}, 'different', 'different'),
            ({'CFBundleVersion': '1'}, 'different', 'missing')]
        for values, version_status, short_status in cases:
            f = self.fixture()
            f.dsym_info.pop('CFBundleVersion', None)
            f.dsym_info.update(values); f.write_dsym()
            with self.subTest(values=values):
                result = f.verify()
                observations = result['dsym_version_observations']
                self.assertEqual(observations['CFBundleVersion'],
                    {'observed': values.get('CFBundleVersion'), 'comparison': version_status})
                self.assertEqual(observations['CFBundleShortVersionString'],
                    {'observed': values.get('CFBundleShortVersionString'), 'comparison': short_status})
                self.assertEqual(result['dsym_metadata'], f.dsym_info)
                self.assertEqual(result['arm64_uuid'], UUID)

    def test_uuid_wrong_architecture_path_uuid_count_and_trailing_text_reject(self):
        f = self.fixture(); command = ['xcrun', 'dwarfdump', '--uuid', str(f.app / 'CelluloidTV'), str(f.dwarf)]
        valid = f.run(command)
        for raw in (valid.replace(b'arm64', b'x86_64', 1), valid.replace(UUID.encode(), b'0' * 36, 1),
            valid.replace(UUID.encode(), b'FFFFFFFF-1234-1234-1234-123456789ABC', 1),
            valid.splitlines()[0] + b'\n', valid + valid, valid + b'warning\n',
            valid.replace(str(f.dwarf).encode(), b'/foreign/file')):
            with self.subTest(raw=raw), self.assertRaises(archive.Rejected):
                archive.matching_uuid(raw, f.app / 'CelluloidTV', f.dwarf)

    def test_snapshot_detects_mutation_replacement_and_new_entry_during_uuid_read(self):
        for change in ('append', 'replace', 'add', 'directory', 'unlink'):
            f = self.fixture()
            def run(command, **kwargs):
                output = f.run(command, **kwargs)
                if command[:3] != ['xcrun','dwarfdump','--uuid']:
                    return output
                if change == 'append':
                    with f.dwarf.open('ab') as stream: stream.write(b'changed')
                elif change == 'replace':
                    raw = f.dwarf.read_bytes(); f.dwarf.unlink(); f.dwarf.write_bytes(raw)
                elif change == 'add': (f.app / 'later.txt').write_text('late')
                elif change == 'directory': (f.archive / archive.DSYM / 'empty').mkdir()
                else: f.dwarf.unlink()
                return output
            with self.subTest(change=change), self.assertRaises(archive.Rejected): f.verify(run=run)

    def test_entry_byte_deadline_and_late_read_limits_reject(self):
        for constant in ('MAX_BYTES', 'MAX_ENTRIES'):
            f = self.fixture()
            with patch.object(archive, constant, 1), self.assertRaises(archive.Rejected): f.verify()
        f = self.fixture(); ticks = iter([0, 0, 31])
        with self.assertRaises(archive.Rejected): f.verify(clock=lambda: next(ticks))
        f = self.fixture(); tick = [0]
        def run(command, **kwargs):
            tick[0] = 101
            return f.run(command, **kwargs)
        with self.assertRaises(archive.Rejected): f.verify(run=run, clock=lambda: tick[0])

    def test_capture_full_cleanup_admission_late_return_and_cleanup_unknown(self):
        receipts = []; calls = []
        def runner(argv, **kwargs):
            calls.append(kwargs)
            return subprocess.CompletedProcess(argv, 0, b'ok', b'')
        with self.assertRaisesRegex(archive.Rejected, 'admission-expired'):
            archive.command(['synthetic'], deadline=20, seconds=600, cap=1024,
                            receipts=receipts, clock=lambda: 0, runner=runner, cleanup=10)
        self.assertEqual(calls, [])
        archive.command(['synthetic'], deadline=25, seconds=600, cap=1024,
                        receipts=receipts, clock=lambda: 0, runner=runner, cleanup=10)
        self.assertEqual(calls[0]['seconds'], 5)
        tick = iter([0, 6])
        with self.assertRaisesRegex(archive.Rejected, 'late-return'):
            archive.command(['synthetic'], deadline=25, seconds=600, cap=1024,
                            receipts=[], clock=lambda: next(tick), runner=runner, cleanup=10)
        def stopped(*args, **kwargs): raise archive.CaptureStopped('descendant-exit-unconfirmed', False)
        receipts = []
        with self.assertRaisesRegex(archive.Rejected, 'capture-stopped'):
            archive.command(['synthetic'], deadline=25, seconds=600, cap=1024,
                            receipts=receipts, clock=lambda: 0, runner=stopped, cleanup=10)
        self.assertFalse(receipts[0]['owned_cleanup_confirmed'])
        self.assertFalse(receipts[0]['complete'])

    def test_capture_failure_byte_overflow_and_nonzero_cannot_complete(self):
        for result in (subprocess.CompletedProcess([], 1, b'', b'failure'),
                       subprocess.CompletedProcess([], 0, b'oversized', b'')):
            receipts = []
            with self.assertRaises(archive.Rejected):
                archive.command(['synthetic'], deadline=25, seconds=10, cap=5,
                    receipts=receipts, clock=lambda: 0, runner=lambda *a, **k: result)
            self.assertFalse(receipts[0]['complete'])

    def test_real_owned_python_capture_and_byte_failure_remain_bounded(self):
        receipts = []
        value = archive.command([sys.executable, '-c', 'print("synthetic")'],
            deadline=time.monotonic() + 8, seconds=2, cap=1024, receipts=receipts)
        self.assertEqual(value, b'synthetic\n'); self.assertTrue(receipts[0]['complete'])
        receipts = []
        with self.assertRaisesRegex(archive.Rejected, 'capture-stopped'):
            archive.command([sys.executable, '-c', 'print("synthetic overflow")'],
                deadline=time.monotonic() + 8, seconds=2, cap=5, receipts=receipts)
        self.assertTrue(receipts[0]['owned_cleanup_confirmed'])
        self.assertFalse(receipts[0]['complete'])

    def test_source_ref_attempt_sha_job_and_scope_mismatch(self):
        valid = environment(); archive.environment(valid)
        for key, value in [('GITHUB_REPOSITORY', 'foreign/repo'), ('GITHUB_REF', 'refs/heads/main'),
            ('GITHUB_WORKFLOW_SHA', 'b' * 40), ('GITHUB_RUN_ID', '0'), ('GITHUB_RUN_ATTEMPT', '2'),
            ('GITHUB_JOB', 'other'), ('GITHUB_EVENT_NAME', 'pull_request'), ('DEVELOPER_DIR', 'foreign')]:
            env = dict(valid); env[key] = value
            with self.subTest(key=key), self.assertRaises(archive.Rejected): archive.environment(env)
        def run(argv, **kwargs):
            args = argv[1:]
            if args == ['rev-parse', 'HEAD']: return (valid['GITHUB_SHA'] + '\n').encode()
            if args == ['rev-parse', archive.BASE + '^{tree}']: return (archive.BASE_TREE + '\n').encode()
            if args == ['rev-list', '--parents', '-n', '1', 'HEAD']: return (valid['GITHUB_SHA'] + ' ' + archive.PARENT + '\n').encode()
            if args == ['rev-parse', 'HEAD^{tree}']: return ('b' * 40 + '\n').encode()
            if args[:2] == ['diff', '--name-status']: return (''.join('A\t' + p + '\n' for p in archive.NEW_PATHS)+''.join('M\t' + p + '\n' for p in archive.MODIFIED_PATHS)).encode()
            return b''
        identity = archive.source_identity(valid, run)
        self.assertEqual(identity['base_tree'], archive.BASE_TREE)
        self.assertEqual(identity['parents'], [archive.PARENT])
        for target, value in [('HEAD', b'bad\n'), ('status', b' M Celluloid/main.m\n'),
                              ('diff', b'M\tCelluloid/main.m\n')]:
            def wrong(argv, **kwargs):
                return value if (target == 'HEAD' and argv == ['git', 'rev-parse', 'HEAD']) or argv[1] == target else run(argv, **kwargs)
            with self.subTest(target=target), self.assertRaises(archive.Rejected): archive.source_identity(valid, wrong)

    def test_source_descendant_merge_and_parentless_heads_reject(self):
        valid = environment()
        for parents in (['b' * 40], [archive.PARENT, 'b' * 40], ['b' * 40, archive.PARENT], []):
            calls = []
            def run(argv, **kwargs):
                calls.append(argv)
                if argv == ['git', 'rev-parse', 'HEAD']: return valid['GITHUB_SHA'].encode()
                if argv == ['git', 'rev-parse', archive.BASE + '^{tree}']: return archive.BASE_TREE.encode()
                if argv == ['git', 'rev-list', '--parents', '-n', '1', 'HEAD']:
                    return ' '.join([valid['GITHUB_SHA'], *parents]).encode()
                raise AssertionError('Source rejection must precede subsequent commands')
            with self.subTest(parents=parents), self.assertRaisesRegex(archive.Rejected, 'sole-parent'):
                archive.source_identity(valid, run)
            self.assertEqual(len(calls), 3)
            self.assertFalse(any('merge-base' in call for call in calls))

    @patch.object(archive.package, 'verify_generated_icons', return_value={'synthetic_icons':True})
    def test_failure_never_runs_archive_again_or_qualifies_partial_proof(self, _icons):
        f = self.fixture(); commands = []
        def run(argv, **kwargs):
            commands.append(argv)
            if argv == archive.ARCHIVE_COMMAND: raise archive.CaptureStopped('duration-limit', False)
            output = b'Xcode 27.0\nBuild version 27A266a\n' if argv == ['xcodebuild', '-version'] else b'appletvos27.0\n'
            return subprocess.CompletedProcess(argv, 0, output, b'')
        with patch.object(archive, 'source_identity', return_value={'source': 'synthetic'}), patch.object(archive, 'verify_archive') as proof:
            result = archive.execute(env=environment(), root=f.root, clock=lambda: 0, runner=run)
        self.assertFalse(result['qualified']); self.assertFalse(result['signing_qualified'])
        self.assertFalse(result['store_qualified']); self.assertFalse(result['older_os_qualified'])
        self.assertTrue(result['ui_qualification_separate']); self.assertFalse(result['binary_handoff'])
        self.assertEqual(commands.count(archive.ARCHIVE_COMMAND), 1)
        proof.assert_not_called()
        self.assertEqual(result['failure']['phase'], 'archive')

    @patch.object(archive.package, 'verify_generated_icons', return_value={'synthetic_icons':True})
    def test_late_source_and_changed_source_cannot_qualify(self, _icons):
        for late in (False, True):
            f = self.fixture(); tick = [0]; calls = []
            def source(*args):
                calls.append(1)
                if len(calls) == 2:
                    if late: tick[0] = 31
                    return {'source': 'synthetic' if late else 'changed'}
                return {'source': 'synthetic'}
            def run(argv, **kwargs):
                output = b'Xcode 27.0\nBuild version 27A266a\n' if argv == ['xcodebuild', '-version'] else b'appletvos27.0\n'
                return subprocess.CompletedProcess(argv, 0, output, b'')
            with patch.object(archive, 'source_identity', side_effect=source), patch.object(archive, 'verify_archive', return_value={'synthetic': True}):
                result = archive.execute(env=environment(), root=f.root, clock=lambda: tick[0], runner=run)
            self.assertFalse(result['qualified']); self.assertEqual(result['failure']['phase'], 'final_source_pack')

    def test_report_cap_downgrades_qualification_and_never_contains_archive_bytes(self):
        report = {'schema': 1, 'qualified': True, 'signing_qualified': False, 'store_qualified': False,
            'older_os_qualified': False, 'ui_qualification_separate': True, 'oversized': 'x' * archive.MAX_REPORT}
        raw = archive.report_bytes(report); decoded = json.loads(raw)
        self.assertLessEqual(len(raw), archive.MAX_REPORT)
        self.assertFalse(decoded['qualified']); self.assertEqual(decoded['failure']['reason'], 'report-byte-limit')

    def test_system_framework_and_swift_overlay_paths_pass_package_validation(self):
        f = self.fixture()
        (f.app / 'CelluloidTV').write_bytes(macho(links=SYNTHETIC_SYSTEM_LIBRARIES))
        result = f.verify()
        observed = result['app']['binaries']['app/CelluloidTV']['slices'][0]['libraries']
        self.assertEqual(observed, list(SYNTHETIC_SYSTEM_LIBRARIES))
        self.assertEqual(len(observed), 4)
        self.assertIn('/System/Library/Frameworks/Photos.framework/Photos', observed)
        # Preserve only the existing package checker's known forbidden links.
        for framework in ('WatchKit', 'WatchConnectivity'):
            f = self.fixture()
            link = '/System/Library/Frameworks/' + framework + '.framework/' + framework
            (f.app / 'CelluloidTV').write_bytes(macho(links=[*SYNTHETIC_SYSTEM_LIBRARIES, link]))
            with self.subTest(framework=framework), self.assertRaises(ValueError):
                f.verify()

    def test_packing_and_file_write_cannot_reset_deadline_or_qualify_late_report(self):
        for late in (False, True):
            f = self.fixture(); tick = [0]; output = f.root / 'proof'; marker = f.root / 'step-output'
            result = {'schema': 1, 'qualified': True, 'signing_qualified': False, 'store_qualified': False,
                'older_os_qualified': False, 'ui_qualification_separate': True,
                'clock': {'report_ready_deadline': 30}}
            original = Path.write_bytes
            def write(path, raw):
                value = original(path, raw)
                if late: tick[0] = 31
                return value
            with patch.object(Path, 'write_bytes', write):
                decoded = archive.retain_report(result, output, marker, clock=lambda: tick[0])
            self.assertEqual(decoded['qualified'], not late)
            self.assertEqual(json.loads((output / 'report.json').read_bytes())['qualified'], not late)
            self.assertEqual(marker.exists(), not late)

    def upload_report(self):
        return {'schema': 1, 'qualified': True, 'signing_qualified': False, 'store_qualified': False,
            'older_os_qualified': False, 'ui_qualification_separate': True, 'upload_qualified': False,
            'source_before': environment(),
            'clock': {'started_monotonic': 100, 'phase_end_seconds': dict(archive.PHASE_END)}}

    def test_upload_full_sixty_plus_twenty_admission_uses_original_clock(self):
        report = self.upload_report()
        result = archive.admit_upload(report, clock=lambda: 1039)
        self.assertEqual(result['evidence_deadline'], 1100)
        self.assertEqual(result['global_deadline'], 1120)
        self.assertEqual(result['action_timeout_seconds'], 60)
        self.assertEqual(result['finalization_reserve_seconds'], 20)
        for now in (1040, 1041, 1100, 1120, 99, float('nan')):
            with self.subTest(now=now), self.assertRaises(archive.Rejected):
                archive.admit_upload(report, clock=lambda: now)
        report['clock']['phase_end_seconds']['evidence'] += 60
        with self.assertRaisesRegex(archive.Rejected, 'clock-identity'):
            archive.admit_upload(report, clock=lambda: 1039)

    def test_upload_late_return_step_delay_and_action_failure_do_not_qualify(self):
        report = self.upload_report()
        report['upload_observation'] = archive.admit_upload(report, clock=lambda: 1030)
        valid = archive.finish_upload(report, 'success', clock=lambda: 1089)
        self.assertTrue(valid['upload_qualified'])
        self.assertEqual(valid['started_monotonic'], 1030)
        self.assertEqual(valid['observed_finished_monotonic'], 1089)
        for now, outcome in ((1090, 'success'), (1099, 'success'), (float('nan'), 'success'), (1100, 'success'), (1101, 'success'), (1120, 'success'),
            (1090, 'failure'), (1090, 'cancelled'), (1090, 'skipped'), (1029, 'success')):
            with self.subTest(now=now, outcome=outcome):
                receipt = archive.finish_upload(report, outcome, clock=lambda: now)
                self.assertFalse(receipt['upload_qualified'])
        report['upload_observation']['admitted_monotonic'] = 1041
        self.assertFalse(archive.finish_upload(report, 'success', clock=lambda: 1099)['upload_qualified'])

    def test_upload_gate_rechecks_admission_after_report_and_marker_writes(self):
        for boundary in ('report', 'marker', 'log'):
            f = self.fixture(); report = self.upload_report()
            path = f.root / 'build/archive-proof/report.json'; path.parent.mkdir(parents=True)
            path.write_bytes(archive.report_bytes(report))
            marker = f.root / 'output'; env = environment(); env['GITHUB_OUTPUT'] = str(marker)
            ticks = iter({'report': [1030, 1040], 'marker': [1030, 1031, 1040],
                          'log': [1030, 1031, 1032, 1033, 1040]}[boundary])
            with patch('builtins.print'), self.subTest(boundary=boundary), self.assertRaises(archive.Rejected):
                archive.upload_gate('admit-upload', root=f.root, env=env, clock=lambda: next(ticks))
            self.assertTrue(not marker.exists() or 'upload_admitted=true' not in marker.read_text())

    def test_upload_gate_binds_source_attempt_and_checks_after_action_log(self):
        f = self.fixture(); report = self.upload_report()
        report['upload_observation'] = archive.admit_upload(report, clock=lambda: 1030)
        path = f.root / 'build/archive-proof/report.json'; path.parent.mkdir(parents=True)
        path.write_bytes(archive.report_bytes(report))
        env = environment(); env['CELLULOID_ARCHIVE_UPLOAD_OUTCOME'] = 'success'
        with patch('builtins.print'):
            self.assertEqual(archive.upload_gate('finish-upload', root=f.root, env=env, clock=lambda: 1089), 0)
            for late in (1110, 1120):
                ticks = iter([1089, late])
                with self.subTest(late=late), self.assertRaisesRegex(archive.Rejected, 'deadline'):
                    archive.upload_gate('finish-upload', root=f.root, env=env, clock=lambda: next(ticks))
        report['source_before']['GITHUB_RUN_ATTEMPT'] = '2'
        path.write_bytes(archive.report_bytes(report))
        with self.assertRaisesRegex(archive.Rejected, 'source-run-mismatch'):
            archive.upload_gate('finish-upload', root=f.root, env=env, clock=lambda: 1099)

    def test_compiled_car_requires_all_actual_scale_dimensions(self):
        f=self.fixture()
        raw=f.run(['xcrun','assetutil','--info','synthetic'])
        value=archive.compiled_asset_dimensions(raw)
        self.assertEqual(len(value['required_dimensions']),5)
        entries=json.loads(raw)
        for i in range(len(entries)):
            with self.subTest(i=i),self.assertRaisesRegex(archive.Rejected,'scale-coverage'):
                archive.compiled_asset_dimensions(json.dumps(entries[:i]+entries[i+1:]).encode())
        for key,value in [('Name','unrelated'),('Scale',2)]:
            changed=json.loads(raw);changed[4][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(archive.Rejected,'role-scale'):
                archive.compiled_asset_dimensions(json.dumps(changed).encode())
        for raw in (b'{}',b'[]',b'[null]',b'[{"PixelWidth":true,"PixelHeight":480}]'):
            with self.subTest(raw=raw),self.assertRaises(archive.Rejected):archive.compiled_asset_dimensions(raw)

    def test_tv_source_and_resource_contract_cannot_be_bypassed(self):
        for name in ('Platforms/tvOS/TVPhotoLibrary.swift','Platforms/Resources/zh-Hans.lproj/Localizable.strings','Packages/CelluloidRendering/Package.swift','Platforms/tvOS/Assets.xcassets/AppIcon.brandassets/TopShelfWide.imageset/Contents.json'):
            f=self.fixture();path=f.root/name;path.write_bytes(path.read_bytes()+b'changed')
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'Reviewed source/resource changed'):
                f.verify()

    def test_tv_metadata_photo_policy_icon_and_sdk_mismatch_reject(self):
        for key,value in [('UIDeviceFamily',[1,2]),('DTSDKName','appletvsimulator27.0'),
                          ('CFBundleIcons',{'CFBundlePrimaryIcon':'Other'}),('NSPhotoLibraryUsageDescription','altered')]:
            f=self.fixture();f.package.metadata[key]=value;f.package.write_info()
            with self.subTest(key=key),self.assertRaises(ValueError):f.verify()

    def test_tv_bundled_localization_and_privacy_values_must_match_source(self):
        for name in ('zh-Hans.lproj/Localizable.strings','zh-Hans.lproj/Localizable.strings','PrivacyInfo.xcprivacy'):
            f=self.fixture();(f.app/name).write_bytes(plistlib.dumps({'changed':'value'}))
            with self.subTest(name=name),self.assertRaises(ValueError):f.verify()
        f=self.fixture();(f.app/'Assets.car').write_bytes(b'')
        with self.assertRaisesRegex(ValueError,'asset catalog'):f.verify()

    def test_tv_release_debug_markers_and_non_system_libraries_reject(self):
        for marker in archive.package.SEAMS:
            f=self.fixture();(f.app/'CelluloidTV').write_bytes(macho(payload=marker))
            with self.subTest(marker=marker),self.assertRaisesRegex(ValueError,'Debug test helper'):f.verify()
        f=self.fixture();(f.app/'CelluloidTV').write_bytes(macho(links=['@rpath/Foreign.framework/Foreign']))
        with self.assertRaisesRegex(ValueError,'Non-system'):f.verify()

    def test_populated_mach_code_signature_rejects_even_without_bundle_signature_directory(self):
        f=self.fixture();raw=macho();head=list(struct.unpack('<8I',raw[:32]));head[4]+=1;head[5]+=16
        changed=struct.pack('<8I',*head)+raw[32:56]+struct.pack('<4I',0x1d,16,72,16)+raw[56:]+b'signature payload'
        (f.app/'CelluloidTV').write_bytes(changed)
        with self.assertRaisesRegex(ValueError,'Code signature load command'):f.verify()

    def test_archive_zero_exit_compiler_error_is_not_success(self):
        for message in (b'error: invalid asset',b'file.swift:12:4: error: broken',b'fatal error: compiler failed'):
            result=subprocess.CompletedProcess(archive.ARCHIVE_COMMAND,0,message,b'')
            receipts=[]
            with self.subTest(message=message),self.assertRaisesRegex(archive.Rejected,'archive-reported-error'):
                archive.command(archive.ARCHIVE_COMMAND,deadline=30,seconds=10,cap=1024,receipts=receipts,
                    clock=lambda:0,runner=lambda *a,**k:result)
            self.assertFalse(receipts[0]['complete'])

    def test_exact_observed_xcode_archive_icon_is_optional_bounded_metadata(self):
        for dimensions,cgbi in [((32,24),False),((400,240),False),((1280,768),True)]:
            f=self.fixture();directory=f.archive/'Assets';directory.mkdir()
            (directory/'ProductIcon.png').write_bytes(png_icon(*dimensions,cgbi=cgbi))
            result=f.verify();observed=result['archive']['paths']['Assets/ProductIcon.png']['png']
            with self.subTest(dimensions=dimensions,cgbi=cgbi):
                self.assertEqual((observed['width'],observed['height']),dimensions)
                self.assertTrue(observed['container_qualified'])
                self.assertFalse(observed['decoded_pixels_qualified'])
                self.assertEqual(observed['cgbi'],cgbi)
            self.assertEqual(set(result['app']['files']),{'app/'+p for p in archive.APP_FILES})
        f=self.fixture();self.assertIn('app',f.verify())

    def test_archive_assets_allowlist_does_not_expand_to_siblings_links_or_executable_icons(self):
        for kind in ('extra','nested','directory','symlink','hardlink','executable','assets-file'):
            f=self.fixture();directory=f.archive/'Assets'
            if kind=='assets-file':directory.write_bytes(b'not a directory')
            else:
                directory.mkdir();icon=directory/'ProductIcon.png'
                if kind=='directory':icon.mkdir()
                elif kind=='symlink':icon.symlink_to(f.app/'CelluloidTV')
                elif kind=='hardlink':os.link(f.app/'CelluloidTV',icon)
                else:
                    icon.write_bytes(png_icon())
                    if kind=='extra':(directory/'other.png').write_bytes(png_icon())
                    if kind=='nested':(directory/'Other').mkdir()
                    if kind=='executable':icon.chmod(0o755)
            with self.subTest(kind=kind),self.assertRaises(archive.Rejected):f.verify()

    def test_archive_icon_png_signature_dimensions_crc_limits_and_terminal_boundary_reject(self):
        valid=png_icon()
        bad_crc=bytearray(valid);bad_crc[29]^=1
        cases=(b'not a PNG',valid[:20],bytes(bad_crc),png_icon(0,24),png_icon(8193,24),
               png_icon(8192,8192),valid+b'trailer',valid[:-12],b'x'*(archive.MAX_PRODUCT_ICON_BYTES+1))
        for data in cases:
            with self.subTest(length=len(data)),self.assertRaises(archive.Rejected) as caught:
                archive.product_icon_png(data,100,clock=lambda:0)
            self.assertEqual(caught.exception.icon_observation['bytes'],len(data))
            self.assertLessEqual(len(caught.exception.icon_observation['prefix_hex']),128)
        f=self.fixture();(f.archive/'Assets').mkdir();(f.archive/archive.PRODUCT_ICON).write_bytes(b'bad')
        with self.assertRaisesRegex(archive.Rejected,'png-signature') as caught:f.verify()
        self.assertEqual(caught.exception.offending_entry['path'],archive.PRODUCT_ICON)

    def test_qr_resource_graph_plus_standard_archive_icon_and_relocations(self):
        # QR source-derived resources plus standard Xcode archive icon/relocation structure.
        # This fixture is synthetic; actual QR archive layout remains unobserved.
        expected=None  # Fixed Celluloid inventory is the full 65-resource closure, below.
        f=self.fixture();(f.archive/'Assets').mkdir();(f.archive/archive.PRODUCT_ICON).write_bytes(png_icon())
        relocation=f.archive/archive.DSYM/'Contents/Resources/Relocations/aarch64/CelluloidTV.yml'
        relocation.parent.mkdir(parents=True);relocation.write_text('triple: arm64-apple-tvos17.0\n')
        result=f.verify()
        self.assertEqual({k[len(archive.APP)+1:] for k,v in result['archive']['paths'].items() if k.startswith(archive.APP+'/') and 'sha256' in v},archive.APP_FILES)
        self.assertGreater(result['archive']['entries'],65)
        self.assertEqual(result['app']['metadata']['CFBundleSupportedPlatforms'],['AppleTVOS'])

    def test_fixed_workflow_source_and_budget(self):
        raw = (archive.ROOT / archive.WORKFLOW).read_text()
        self.assertIn('timeout-minutes: 20', raw)
        self.assertIn('runs-on: xcode-27', raw)
        self.assertIn('group: celluloid-tv-unsigned-archive', raw)
        self.assertIn('cancel-in-progress: false', raw)
        self.assertIn('retention-days: 1', raw)
        self.assertIn('tv_release_archive.py admit-upload', raw)
        self.assertIn('tv_release_archive.py finish-upload', raw)
        self.assertIn('CELLULOID_ARCHIVE_UPLOAD_OUTCOME: ${{ steps.upload.outcome }}', raw)
        self.assertLess(raw.index('tv_release_archive.py admit-upload'), raw.index('uses: actions/upload-artifact@'))
        self.assertLess(raw.index('uses: actions/upload-artifact@'), raw.index('tv_release_archive.py finish-upload'))
        self.assertIn('path: build/archive-proof/report.json', raw)
        for forbidden in ('matrix:', 'inputs:', 'secrets.', 'large', '.xcarchive\n'):
            self.assertNotIn(forbidden, raw)
        self.assertEqual(archive.ARCHIVE_COMMAND[-1], 'archive')
        self.assertEqual(archive.PHASE_END['finalization'], 1020)
        self.assertEqual(sum((180, 600, 20, 90, 20, 30, 60, 20)), 1020)


class CelluloidPackagingRegressions(unittest.TestCase):
    def fixture(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        return ArchiveFixture(Path(temp.name))

    def test_all_52_package_resources_and_four_localized_tables_are_required(self):
        contract=archive.package.contract()
        self.assertEqual(sum(map(len,contract['package_resources'].values())),52)
        for name in ['LICENSE.txt','PrivacyPolicy.txt','en.lproj/Localizable.strings','en.lproj/InfoPlist.strings','zh-Hans.lproj/InfoPlist.strings',
                     'CelluloidCore_CelluloidDomain.bundle/en.lproj/Localizable.strings','CelluloidRendering_CelluloidRendering.bundle/bubble.json','CelluloidRendering_CelluloidRendering.bundle/37.png']:
            f=self.fixture();(f.app/name).write_bytes(b'changed')
            with self.subTest(name=name),self.assertRaises((ValueError,plistlib.InvalidFileException)):f.verify()

    def test_package_metadata_cannot_introduce_code(self):
        for metadata in ({'CFBundlePackageType':'APPL'},{'CFBundlePackageType':'BNDL','CFBundleExecutable':'rogue'}):
            f=self.fixture();(f.app/'CelluloidCore_CelluloidDomain.bundle/Info.plist').write_bytes(plistlib.dumps(metadata))
            with self.assertRaisesRegex(ValueError,'Package bundle metadata'):f.verify()

    def test_compiled_top_shelf_and_device_platform_are_bound(self):
        for key,value in [('DTPlatformName','appletvsimulator'),('TVTopShelfImage',{'TVTopShelfPrimaryImage':'Foreign'})]:
            f=self.fixture();f.package.metadata[key]=value;f.package.write_info()
            with self.assertRaises(ValueError):f.verify()

    def icon_fixture(self):
        f=self.fixture();root=f.root;temp=root/'icon-provenance';temp.mkdir()
        source='Celluloid/Assets.xcassets/AppIcon.appiconset/Icon-Marketing.png'
        data={'source_path':source,'source_commit':'a'*40,'source_sha256':archive.hashlib.sha256((root/source).read_bytes()).hexdigest(),'files':[]}
        for catalog in (root/'Platforms/tvOS/Assets.xcassets/AppIcon.brandassets').rglob('Contents.json'):
            for row in json.loads(catalog.read_bytes()).get('images',[]):
                path=catalog.parent/row['filename'];scale=int(row['scale'][0]);relative=path.relative_to(root).as_posix()
                dims=(400,240) if '/Small.' in relative else (1280,768) if '/Large.' in relative else (2320,720) if '/TopShelfWide.' in relative else (1920,720)
                dims=tuple(x*scale for x in dims);raw=png_icon(*dims);path.write_bytes(raw)
                data['files'].append({'path':relative,'width':dims[0],'height':dims[1],'bytes':len(raw),'sha256':archive.hashlib.sha256(raw).hexdigest(),'derivation':'explicit synthetic PNG container only'})
        report=temp/'tv-archive-icon-provenance-runtime.json';report.write_text(json.dumps(data))
        return f,{'GITHUB_SHA':'a'*40,'RUNNER_TEMP':str(temp)},data,report

    def test_generated_icon_source_slots_dimensions_and_hashes_bind_before_after(self):
        f,env,data,report=self.icon_fixture()
        self.assertEqual(archive.package.verify_generated_icons(f.root,env),data)
        self.assertEqual(len(data['files']),8)
        for mutation in ('source','duplicate','dimension','bytes','hash','linked'):
            f,env,data,report=self.icon_fixture();row=data['files'][0];path=f.root/row['path']
            if mutation=='source':env['GITHUB_SHA']='b'*40
            elif mutation=='duplicate':data['files'][-1]=row
            elif mutation=='dimension':row['width']+=1
            elif mutation=='bytes':row['bytes']+=1
            elif mutation=='hash':path.write_bytes(path.read_bytes()+b'change')
            elif mutation=='linked':
                original=path.read_bytes();path.unlink();other=f.root/'outside.png';other.write_bytes(original);path.symlink_to(other)
            report.write_text(json.dumps(data))
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):archive.package.verify_generated_icons(f.root,env)

    def test_complete_capture_over_512k_retains_compact_utf8_and_full_hash(self):
        raw=b'BEGIN\n'+b'A'*(2*1024*1024)+b'\nEND\n';rows=[]
        result=subprocess.CompletedProcess(archive.ARCHIVE_COMMAND,0,raw,b'')
        actual=archive.command(archive.ARCHIVE_COMMAND,deadline=100,seconds=90,cap=archive.ARCHIVE_RAW_CAP,
            receipts=rows,clock=lambda:0,runner=lambda *a,**k:result,archive_output=True)
        log=rows[0]['archive_log'];self.assertEqual(actual,raw);self.assertTrue(rows[0]['complete'])
        self.assertTrue(log['capture_complete']);self.assertEqual(log['full_total_bytes'],len(raw))
        self.assertEqual(log['full_sha256'],archive.hashlib.sha256(raw).hexdigest())
        self.assertTrue(log['truncated']);self.assertLessEqual(log['retained_utf8_bytes'],512*1024)
        self.assertIn('BEGIN',rows[0]['stdout']);self.assertIn('END',rows[0]['stdout'])
        row={};archive.retain_archive_output(row,b'\xff'*400000,b'\xfe'*400000,capture_complete=True)
        self.assertLessEqual(row['archive_log']['retained_utf8_bytes'],512*1024)

    def test_hidden_middle_error_scanned_before_retention_and_remains_failure(self):
        for stream in ('stdout','stderr'):
            raw=b'A'*(600*1024)+b'\nerror: middle-only failure\n'+b'B'*(600*1024)
            result=subprocess.CompletedProcess(archive.ARCHIVE_COMMAND,0,raw if stream=='stdout' else b'',raw if stream=='stderr' else b'')
            rows=[]
            with self.assertRaisesRegex(archive.Rejected,'archive-reported-error'):
                archive.command(archive.ARCHIVE_COMMAND,deadline=100,seconds=90,cap=archive.ARCHIVE_RAW_CAP,
                    receipts=rows,clock=lambda:0,runner=lambda *a,**k:result,archive_output=True)
            self.assertNotIn('middle-only failure',rows[0][stream]);self.assertFalse(rows[0]['complete'])
            self.assertTrue(rows[0]['archive_log']['error_scan_complete']);self.assertTrue(rows[0]['archive_log']['error_marker_found'])

    def test_stopped_capture_never_claims_full_log_or_complete_error_scan(self):
        error=archive.CaptureStopped('byte-limit',True);error.stdout_prefix=b'A'*archive.ARCHIVE_RAW_CAP;error.stderr_capture=b''
        rows=[]
        def runner(*a,**k):raise error
        with self.assertRaisesRegex(archive.Rejected,'capture-stopped'):
            archive.command(archive.ARCHIVE_COMMAND,deadline=100,seconds=90,cap=archive.ARCHIVE_RAW_CAP,
                receipts=rows,clock=lambda:0,runner=runner,archive_output=True)
        log=rows[0]['archive_log'];self.assertFalse(log['capture_complete']);self.assertIsNone(log['full_sha256']);self.assertIsNone(log['full_total_bytes']);self.assertFalse(log['error_scan_complete']);self.assertLessEqual(log['retained_utf8_bytes'],512*1024)

    def test_real_python_capture_over_512k_without_xcode(self):
        expected=b'P'*1048576+b'\nlast-line\n';rows=[]
        def runner(argv,**kwargs):
            self.assertEqual(argv,archive.ARCHIVE_COMMAND)
            return archive.capture([sys.executable,'-c',"import os;os.write(1,b'P'*1048576+b'\\nlast-line\\n')"],**kwargs)
        raw=archive.command(archive.ARCHIVE_COMMAND,deadline=time.monotonic()+20,seconds=10,cap=archive.ARCHIVE_RAW_CAP,receipts=rows,runner=runner,archive_output=True)
        self.assertEqual(raw,expected);self.assertTrue(rows[0]['complete']);self.assertTrue(rows[0]['archive_log']['capture_complete'])

    def test_route_has_only_one_archive_no_ui_and_explicit_resource_overrides(self):
        self.assertIn('ARCHS=arm64',archive.ARCHIVE_COMMAND)
        self.assertIn('DEBUG_INFORMATION_FORMAT=dwarf-with-dsym',archive.ARCHIVE_COMMAND)
        self.assertIn('COMPRESS_PNG_FILES=NO',archive.ARCHIVE_COMMAND)
        self.assertEqual(archive.ARCHIVE_COMMAND.count('archive'),1)
        self.assertNotIn('workflow_dispatch:',(archive.ROOT/archive.WORKFLOW).read_text())
        self.assertEqual(archive.PARENT,'da446a1bb869baf95499c2a057bb627d3d73d3b0')
        self.assertEqual(archive.BASE_TREE,'6325ef9470ffbb03dce3ebd82b104a0b2e1eb82c')


if __name__ == '__main__':
    unittest.main()
