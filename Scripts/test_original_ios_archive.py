"""Bounded synthetic archive adversaries. No Apple build or native pass claim."""
from pathlib import Path
import copy
import json
import os
import plistlib
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

import original_ios_archive as archive
from mac_owned_crash import bounded_optional_process

CONTEXT = {'source_sha': 'a' * 40, 'run_id': '123', 'run_attempt': '2'}
SOURCE = {'source_sha': CONTEXT['source_sha'], 'tree': 'b' * 40, 'phase': 'before', 'source_fingerprint': 'c' * 64}


def put(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def dump(path, value):
    put(path, plistlib.dumps(value))


def clock(start=None):
    return {'schema': archive.CLOCK_SCHEMA, **CONTEXT, 'started_monotonic': time.monotonic() if start is None else start,
            'started_unix': time.time(), 'execution_budget_seconds': 1560}


def row_summary():
    return {'schema': 'Celluloid.OriginalIOSRows.1', **CONTEXT, 'source_tree': SOURCE['tree'],
            'scope': 'original-ios-release', 'all_rows_verified': True, 'original_total_invocations': 412,
            'rows': [{'row': row, 'original_test_invocation_count': archive.ROW_COUNTS[row], 'model': model,
                      'device_id': f'00000000-0000-4000-8000-{i:012d}', 'row_receipt_sha256': 'd' * 64,
                      'artifact_manifest_sha256': 'e' * 64,
                      'artifact_name': 'celluloid-original-ios-' + row + '-' + CONTEXT['source_sha'] + '-2'}
                     for i, (row, model) in enumerate(archive.ROWS.items())]}


def process_result(output, **changes):
    return {'return_code': 0, 'output': output, 'bytes_read': len(output), 'pipe_eof': True,
            'child_reaped': True, 'timed_out': False, 'overflow': False, 'cleanup_error': None,
            'finalized': True, 'elapsed_seconds': 0.01, **changes}


def observation(command, command_deadline, cleanup_deadline, cap):
    tool, executable = command[1], command[-1]
    if tool == 'lipo':
        output = b'arm64\n'
    elif tool == 'vtool':
        output = (executable + ':\nLoad command 1\n      cmd LC_BUILD_VERSION\n  cmdsize 32\n platform IOS\n    minos 15.0\n      sdk 27.0\n   ntools 1\n     tool LD\n  version 123.0\n').encode()
    else:
        kit = '@rpath/CelluloidKit.framework/CelluloidKit'
        snapkit = '@rpath/SnapKit_3965163F11347F41_PackageProduct.framework/SnapKit_3965163F11347F41_PackageProduct'
        links = {'Celluloid': [snapkit, kit], 'CelluloidKit': [kit, snapkit],
                 'CelluloidPhotoExtension': [kit], 'SnapKit_3965163F11347F41_PackageProduct': [snapkit]}[Path(executable).name]
        output = (executable + ':\n' + ''.join('\t' + link + ' (compatibility version 1.0.0, current version 2.0.0)\n'
                                             for link in links + ['/System/Library/Frameworks/UIKit.framework/UIKit'])).encode()
    return process_result(output)


class Package:
    def __init__(self, base):
        base = base.resolve()
        self.root, self.temp = base / 'checkout', base / 'runner'
        self.temp.mkdir()
        self.path = self.root / archive.ARCHIVE
        for name in ('Celluloid/Info.plist', 'CelluloidPhotoExtension/Info.plist', 'CelluloidKit/Info.plist',
                     'Celluloid/zh-Hans.lproj/InfoPlist.strings',
                     'Celluloid/collage.json', 'CelluloidKit/bubble.json', 'CelluloidKit/ThirdPartyNotices/SnapKit-LICENSE.txt',
                     'Celluloid.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved'):
            put(self.root / name, (archive.ROOT / name).read_bytes())
        for path, (name, bundle_id, kind, filetype) in archive.BUNDLES.items():
            info = {} if path == archive.SNAPKIT else plistlib.loads((self.root / name / 'Info.plist').read_bytes())
            info.update(CFBundleIdentifier=bundle_id, CFBundleExecutable=name, CFBundleName=name,
                        CFBundlePackageType=kind, CFBundleVersion='1' if path == archive.SNAPKIT else '2',
                        CFBundleShortVersionString='1.0' if path == archive.SNAPKIT else '1.1', CFBundleSupportedPlatforms=['iPhoneOS'],
                        DTPlatformName='iphoneos', MinimumOSVersion='15.0', UIDeviceFamily=[1, 2])
            dump(self.path / path / 'Info.plist', info)
            # A small synthetic Mach-O header, never offered as actual native evidence.
            put(self.path / path / name, struct.pack('<IIIIIIII', 0xfeedfacf, 0x100000c, 0, filetype, 1, 8, 0, 0) + struct.pack('<II', 0x1b, 8) + b'synthetic-release')
        dump(self.path / 'Info.plist', {'ArchiveVersion': 2, 'SchemeName': 'Celluloid', 'ApplicationProperties': {
            'ApplicationPath': 'Applications/Celluloid.app', 'CFBundleIdentifier': 'Mango.Celluloid',
            'CFBundleShortVersionString': '1.1', 'CFBundleVersion': '2'}})
        for path, source in [(archive.APP + '/collage.json', 'Celluloid/collage.json'),
                             (archive.KIT + '/bubble.json', 'CelluloidKit/bubble.json'),
                             (archive.KIT + '/SnapKit-LICENSE.txt', 'CelluloidKit/ThirdPartyNotices/SnapKit-LICENSE.txt')]:
            put(self.path / path, (self.root / source).read_bytes())
        for owner in (archive.APP, archive.KIT):
            put(self.path / owner / 'Assets.car', b'synthetic-asset-catalog')
            for language in ('en', 'zh-Hans'):
                dump(self.path / owner / (language + '.lproj/Localizable.strings'), {'synthetic': 'resource'})
        dump(self.path / archive.APP / 'zh-Hans.lproj/InfoPlist.strings', archive.source_usage_localization(self.root))
        for path in (archive.APP + '/Base.lproj/LaunchScreen.storyboardc', archive.EXT + '/Base.lproj/MainInterface.storyboardc'):
            put(self.path / path / 'compiled.nib', b'synthetic-storyboard')
        for owner in (archive.APP, archive.EXT):
            dump(self.path / owner / 'SnapKit_SnapKit.bundle/Info.plist', {'CFBundleName': 'SnapKit_SnapKit', 'CFBundlePackageType': 'BNDL'})
            dump(self.path / owner / 'SnapKit_SnapKit.bundle/PrivacyInfo.xcprivacy', archive.PRIVACY)
        put(self.temp / archive.ROWS_FILE, archive.encoded(row_summary()))
        put(self.temp / 'combined-source-before.json', archive.encoded(SOURCE))
        self.clock = clock()

    def verify(self):
        return archive.verify_package(self.root, self.temp, CONTEXT, self.clock, SOURCE)


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.package = Package(Path(self.directory.name))
        self.probes = mock.patch.object(archive, 'bounded_optional_process', side_effect=observation).start()
        self.addCleanup(mock.patch.stopall)

    def mutate_plist(self, path, mutate):
        file = self.package.path / path
        row = plistlib.loads(file.read_bytes())
        mutate(row)
        dump(file, row)

    def test_bounded_original_closure_resource_hashes_and_no_release_claim(self):
        result = self.package.verify()
        self.assertEqual([row['path'] for row in result['code_bundles']], list(archive.BUNDLES))
        self.assertEqual(self.probes.call_count, 12)
        self.assertTrue(result['unsigned_package_verified'])
        self.assertFalse(result['release_acceptance'])
        self.assertFalse(result['signing_qualified'])
        self.assertFalse(result['uploaded'])
        self.assertFalse(result['application_privacy_manifest_present'])
        self.assertEqual({row['path'] for row in result['privacy_manifests']},
                         {owner + '/SnapKit_SnapKit.bundle/PrivacyInfo.xcprivacy' for owner in (archive.APP, archive.EXT)})
        self.assertEqual(result['row_replay_sha256'], archive.sha((self.package.temp / archive.ROWS_FILE).read_bytes()))
        self.assertEqual(result['inventory_sha256'], archive.sha(archive.encoded(result['files'])))
        self.assertLess(len(archive.encoded(result)), archive.BUDGETS['archive'])
        for call in self.probes.call_args_list:
            self.assertEqual(call.args[0][:1], ['/usr/bin/xcrun'])
            self.assertLess(call.args[1], call.args[2])
            self.assertLessEqual(call.args[2], self.package.clock['started_monotonic'] + 1380)
            self.assertEqual(call.kwargs['cap'], 8192)

    def test_missing_each_original_code_bundle_or_executable_is_rejected(self):
        for path in (archive.KIT, archive.EXT, archive.SNAPKIT, archive.KIT + '/CelluloidKit',
                     archive.EXT + '/CelluloidPhotoExtension', archive.SNAPKIT + '/' + archive.SNAPKIT_NAME):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as folder:
                package = Package(Path(folder))
                target = package.path / path
                shutil.rmtree(target) if target.is_dir() else target.unlink()
                with self.assertRaises(ValueError):
                    package.verify()

    def test_extra_watch_validation_host_xctest_debug_and_hidden_code_fail(self):
        extras = {'Products/Applications/CelluloidPhoneCompanion.app': None,
                  archive.APP + '/Watch/CelluloidWatch.app': None,
                  archive.APP + '/PlugIns/CelluloidTests.xctest': None,
                  archive.APP + '/Frameworks/Unreviewed.framework': None,
                  archive.APP + '/Frameworks/SnapKit.framework': None,
                  archive.APP + '/Frameworks/SnapKit_3965163F11347F42_PackageProduct.framework': None,
                  archive.APP + '/Celluloid.debug.dylib': b'debug',
                  archive.APP + '/__preview.dylib': b'debug',
                  archive.APP + '/hidden': struct.pack('<I', 0xfeedfacf) + b'hidden',
                  archive.APP + '/extra.bundle': None,
                  archive.KIT + '/SnapKit_SnapKit.bundle': None,
                  archive.APP + '/embedded.mobileprovision': b'signed'}
        for relative, data in extras.items():
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as folder:
                package = Package(Path(folder))
                if data is None:
                    (package.path / relative).mkdir(parents=True)
                else:
                    put(package.path / relative, data)
                with self.assertRaises(ValueError):
                    package.verify()

    def test_each_identity_version_build_platform_minimum_and_executable_changes_fail(self):
        fields = {'CFBundleIdentifier': 'Mango.Other', 'CFBundleExecutable': '../Celluloid', 'CFBundleName': 'Host',
                  'CFBundleShortVersionString': '1.2', 'CFBundleVersion': 2, 'MinimumOSVersion': '17.0',
                  'DTPlatformName': 'iphonesimulator', 'CFBundleSupportedPlatforms': ['iPhoneSimulator']}
        for bundle in archive.BUNDLES:
            for key, value in fields.items():
                if bundle == archive.SNAPKIT and key == 'CFBundleName':
                    continue  # The historical inventory did not establish SnapKit's display name.
                with self.subTest(bundle=bundle, key=key), tempfile.TemporaryDirectory() as folder:
                    package = Package(Path(folder))
                    path = package.path / bundle / 'Info.plist'
                    info = plistlib.loads(path.read_bytes())
                    info[key] = value
                    dump(path, info)
                    with self.assertRaises(ValueError):
                        package.verify()

    def test_original_photos_declaration_and_usage_strings_preserved(self):
        for field, value in [('NSExtensionPointIdentifier', 'com.apple.share-services'),
                             ('NSExtensionMainStoryboard', 'Wrong')]:
            with self.subTest(field=field):
                path = self.package.path / archive.EXT / 'Info.plist'
                original = path.read_bytes()
                self.mutate_plist(archive.EXT + '/Info.plist', lambda row: row['NSExtension'].__setitem__(field, value))
                with self.assertRaises(ValueError):
                    self.package.verify()
                path.write_bytes(original)
        self.mutate_plist(archive.APP + '/Info.plist', lambda row: row.__setitem__('NSPhotoLibraryUsageDescription', 'changed'))
        with self.assertRaises(ValueError):
            self.package.verify()

    def test_pinned_notice_resources_and_actual_privacy_are_required(self):
        for path in (archive.KIT + '/SnapKit-LICENSE.txt', archive.KIT + '/bubble.json', archive.APP + '/collage.json',
                     archive.APP + '/Assets.car', archive.APP + '/SnapKit_SnapKit.bundle/PrivacyInfo.xcprivacy',
                     archive.EXT + '/SnapKit_SnapKit.bundle/PrivacyInfo.xcprivacy'):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as folder:
                package = Package(Path(folder))
                (package.path / path).unlink()
                with self.assertRaises(ValueError):
                    package.verify()
        for owner in (archive.APP, archive.EXT):
            with self.subTest(owner=owner), tempfile.TemporaryDirectory() as folder:
                package = Package(Path(folder))
                dump(package.path / owner / 'SnapKit_SnapKit.bundle/PrivacyInfo.xcprivacy', dict(archive.PRIVACY, NSPrivacyTracking=True))
                with self.assertRaises(ValueError):
                    package.verify()

    def test_snapkit_exact_identity_and_original_versions_are_distinct(self):
        result = self.package.verify()
        snapkit = result['code_bundles'][-1]
        self.assertEqual(snapkit['path'], archive.APP + '/Frameworks/SnapKit_3965163F11347F41_PackageProduct.framework')
        self.assertEqual(snapkit['metadata']['CFBundleIdentifier'], 'snapkit.SnapKit')
        self.assertEqual(snapkit['metadata']['CFBundleExecutable'], 'SnapKit_3965163F11347F41_PackageProduct')
        self.assertEqual(snapkit['metadata']['CFBundleShortVersionString'], '1.0')
        self.assertEqual(snapkit['metadata']['CFBundleVersion'], '1')
        self.assertNotIn('CFBundleName', snapkit['metadata'])
        for row in result['code_bundles'][:-1]:
            self.assertEqual((row['metadata']['CFBundleShortVersionString'], row['metadata']['CFBundleVersion']), ('1.1', '2'))
        for key, value in [('CFBundleExecutable', 'SnapKit'), ('CFBundleIdentifier', 'Mango.SnapKit'),
                           ('CFBundleShortVersionString', '1.1'), ('CFBundleVersion', '2')]:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as folder:
                package = Package(Path(folder))
                path = package.path / archive.SNAPKIT / 'Info.plist'
                info = plistlib.loads(path.read_bytes())
                info[key] = value
                dump(path, info)
                with self.assertRaises(ValueError):
                    package.verify()
        self.mutate_plist(archive.SNAPKIT + '/Info.plist', lambda row: row.__setitem__('CFBundleName', 'SnapKit'))
        self.assertEqual(self.package.verify()['code_bundles'][-1]['observed_bundle_name'], 'SnapKit')

    def test_snapkit_source_pin_and_license_cannot_be_replaced_together(self):
        resolved_path = self.package.root / 'Celluloid.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved'
        original = json.loads(resolved_path.read_text())
        mutations = [lambda r: r['pins'][0]['state'].__setitem__('revision', 'f' * 40),
                     lambda r: r['pins'][0]['state'].__setitem__('version', '5.7.2'),
                     lambda r: r['pins'][0].__setitem__('location', 'https://github.com/other/SnapKit.git'),
                     lambda r: r['pins'].append(copy.deepcopy(r['pins'][0]))]
        for mutate in mutations:
            row = copy.deepcopy(original)
            mutate(row)
            resolved_path.write_bytes(archive.encoded(row))
            with self.assertRaisesRegex(ValueError, 'source pin'):
                self.package.verify()
        resolved_path.write_bytes(archive.encoded(original))
        for path in (self.package.root / 'CelluloidKit/ThirdPartyNotices/SnapKit-LICENSE.txt',
                     self.package.path / archive.KIT / 'SnapKit-LICENSE.txt'):
            path.write_bytes(b'matching replacement notice')
        with self.assertRaisesRegex(ValueError, 'Pinned SnapKit notice'):
            self.package.verify()

    def test_snapkit_only_exact_observed_dsym_is_admitted(self):
        relative = 'dSYMs/SnapKit_3965163F11347F41_PackageProduct.framework.dSYM/Contents/Resources/DWARF/SnapKit_3965163F11347F41_PackageProduct'
        data = struct.pack('<I', 0xfeedfacf) + b'synthetic-debug-metadata'
        put(self.package.path / relative, data)
        self.assertTrue(self.package.verify()['unsigned_package_verified'])
        for changed in (relative.replace('.framework.dSYM', '.app.dSYM'), relative + '-other'):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as folder:
                package = Package(Path(folder))
                put(package.path / changed, data)
                with self.assertRaisesRegex(ValueError, 'Unexpected executable'):
                    package.verify()

    def test_debug_marker_across_hash_chunk_boundary_fails(self):
        binary = self.package.path / archive.APP / 'Celluloid'
        header = binary.read_bytes()[:40]
        binary.write_bytes(header + b'x' * (65536 - len(header) - 10) + archive.DEBUG_MARKERS[0] + b'end')
        with self.assertRaisesRegex(ValueError, 'Debug/test seam'):
            self.package.verify()
        self.probes.assert_not_called()

    def test_malformed_macho_load_commands_fail(self):
        binary = self.package.path / archive.APP / 'Celluloid'
        original = binary.read_bytes()
        for offset, value in [(32, 0x1d), (36, 4), (16, 513), (20, 256008), (4, 7)]:
            data = bytearray(original)
            struct.pack_into('<I', data, offset, value)
            binary.write_bytes(data)
            with self.subTest(offset=offset, value=value), self.assertRaises(ValueError):
                self.package.verify()
        self.probes.assert_not_called()

    def test_signature_load_command_is_observed_without_signing_qualification_or_mutation(self):
        binary = self.package.path / archive.APP / 'Celluloid'
        data = struct.pack('<IIIIIIII', 0xfeedfacf, 0x100000c, 0, 2, 1, 16, 0, 0) + struct.pack('<IIII', 0x1d, 16, 48, 16) + b'x' * 16
        binary.write_bytes(data)
        report = self.package.verify()
        observed = report['code_bundles'][0]['code_signature_load_command']
        self.assertEqual(observed, {'present': True, 'command': 'LC_CODE_SIGNATURE', 'data_offset': 48,
                                    'data_size': 16, 'signature_kind': 'unverified', 'signing_qualified': False})
        self.assertTrue(report['unsigned_package_verified'])
        self.assertFalse(report['signing_qualified'])
        self.assertFalse(report['release_acceptance'])
        self.assertEqual(binary.read_bytes(), data)

    def test_signature_load_command_duplicate_size_overlap_and_out_of_bounds_fail(self):
        header = struct.pack('<IIIIIIII', 0xfeedfacf, 0x100000c, 0, 2, 1, 16, 0, 0)
        for offset, size in [(0, 16), (48, 0), (48, 17), (1000, 1), (0xffffffff, 0xffffffff)]:
            data = header + struct.pack('<IIII', 0x1d, 16, offset, size) + b'x' * 16
            with self.subTest(offset=offset, size=size), self.assertRaises(ValueError):
                archive.macho_header(data, len(data), 2)
        duplicate = struct.pack('<IIIIIIII', 0xfeedfacf, 0x100000c, 0, 2, 2, 32, 0, 0) + struct.pack('<IIII', 0x1d, 16, 64, 16) * 2 + b'x' * 16
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            archive.macho_header(duplicate, len(duplicate), 2)

    def test_malformed_duplicate_metadata_and_unknown_executable_fail(self):
        path = self.package.path / archive.APP / 'Info.plist'
        path.write_bytes(path.read_bytes().replace(b'<dict>', b'<dict><key>CFBundleVersion</key><string>2</string>', 1))
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.package.verify()
        with self.assertRaises(ValueError):
            archive.plist(plistlib.dumps({'bad': float('nan')}))

    def test_path_symlink_hardlink_fifo_and_archive_parent_escape_fail(self):
        for kind in ('file-link', 'directory-link', 'hardlink', 'fifo', 'parent-link'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as folder:
                package = Package(Path(folder))
                target = package.path / archive.APP / 'attack'
                if kind == 'file-link':
                    target.symlink_to('/etc/passwd')
                elif kind == 'directory-link':
                    target.symlink_to('/tmp', target_is_directory=True)
                elif kind == 'hardlink':
                    os.link(package.path / archive.APP / 'collage.json', target)
                elif kind == 'fifo':
                    os.mkfifo(target)
                else:
                    source = package.root / '.build'
                    moved = package.root / 'moved'
                    source.rename(moved)
                    source.symlink_to(moved, target_is_directory=True)
                with self.assertRaises((ValueError, OSError)):
                    package.verify()

    def test_caps_fail_before_commands_without_reading_oversized_file(self):
        for key, value in [('MAX_ENTRIES', 2), ('MAX_FILE', 64), ('MAX_BYTES', 128), ('MAX_DEPTH', 2)]:
            with self.subTest(key=key), mock.patch.object(archive, key, value):
                with self.assertRaises(ValueError):
                    self.package.verify()
        self.probes.assert_not_called()
        oversized = self.package.path / archive.APP / 'huge'
        with oversized.open('wb') as stream:
            stream.truncate(archive.MAX_FILE + 1)
        with self.assertRaisesRegex(ValueError, 'oversized'):
            self.package.verify()
        self.probes.assert_not_called()

    def test_wrong_rows_source_attempt_count_models_and_complete_membership_fail(self):
        mutations = [lambda r: r.__setitem__('source_sha', 'f' * 40), lambda r: r.__setitem__('run_attempt', '1'),
                     lambda r: r.__setitem__('source_tree', 'f' * 40), lambda r: r.__setitem__('all_rows_verified', 1),
                     lambda r: r.__setitem__('original_total_invocations', 411), lambda r: r['rows'].pop(),
                     lambda r: r['rows'].reverse(), lambda r: r['rows'][0].__setitem__('model', 'Other'),
                     lambda r: r['rows'][0].__setitem__('original_test_invocation_count', True),
                     lambda r: r['rows'][0].__setitem__('artifact_name', 'previous-attempt'),
                     lambda r: r['rows'][0].__setitem__('row_receipt_sha256', 'not-a-hash'),
                     lambda r: r['rows'][0].__setitem__('device_id', r['rows'][1]['device_id'])]
        for mutate in mutations:
            row = row_summary()
            mutate(row)
            with self.assertRaises(ValueError):
                archive.row_binding(row, CONTEXT, SOURCE)
        self.probes.assert_not_called()

    def test_public_observation_architecture_platform_floor_and_private_links_fail(self):
        for tool, old, new in [('lipo', b'arm64', b'arm64 x86_64'), ('vtool', b'platform IOS', b'platform IOSSIMULATOR'),
                               ('vtool', b'minos 15.0', b'minos 17.0'), ('otool', b'/System/Library/Frameworks/', b'/System/Library/PrivateFrameworks/')]:
            def changed(command, *args, **kwargs):
                result = observation(command, *args, **kwargs)
                if command[1] == tool:
                    result['output'] = result['output'].replace(old, new)
                return result
            with self.subTest(tool=tool), mock.patch.object(archive, 'bounded_optional_process', side_effect=changed):
                with self.assertRaises(ValueError):
                    self.package.verify()

    def test_otool_ordinary_and_exact_weak_suffix_preserve_linkage_kind(self):
        executable = Path('/synthetic/CelluloidPhotoExtension')
        framework = '@rpath/CelluloidKit.framework/CelluloidKit'
        system = '/usr/lib/swift/libswiftCore.dylib'
        line = lambda path, suffix: '\t' + path + ' (compatibility version 1.0.0, current version 6.4.0' + suffix + ')\n'
        for suffix, weak in [('', False), (', weak', True)]:
            raw = str(executable) + ':\n' + line(framework, '') + line(system, suffix)
            self.assertEqual(archive.linked_libraries(raw, executable, archive.EXT),
                             [{'path': framework, 'weak': False}, {'path': system, 'weak': weak}])
        for suffix in (', reexport', ', upward', ', lazy', ', weak, reexport', ',weak', ', WEAK'):
            raw = str(executable) + ':\n' + line(framework, '') + line(system, suffix)
            with self.subTest(suffix=suffix), self.assertRaisesRegex(ValueError, 'Malformed'):
                archive.linked_libraries(raw, executable, archive.EXT)
        for path in ('@rpath/libswiftCompatibilitySpan.dylib', '@rpath/Other.framework/Other',
                     '/System/Library/PrivateFrameworks/Other.framework/Other', '/usr/lib/swift/libXCTest.dylib'):
            raw = str(executable) + ':\n' + line(framework, '') + line(path, ', weak')
            with self.subTest(path=path), self.assertRaises(ValueError):
                archive.linked_libraries(raw, executable, archive.EXT)
        duplicate = str(executable) + ':\n' + line(framework, '') + line(system, '') + line(system, ', weak')
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            archive.linked_libraries(duplicate, executable, archive.EXT)

    def test_each_owner_has_exact_bundled_dependencies_and_framework_install_identity(self):
        kit = '@rpath/CelluloidKit.framework/CelluloidKit'
        snapkit = '@rpath/SnapKit_3965163F11347F41_PackageProduct.framework/SnapKit_3965163F11347F41_PackageProduct'
        relationships = {archive.APP: [snapkit, kit], archive.KIT: [kit, snapkit],
                         archive.EXT: [kit], archive.SNAPKIT: [snapkit]}
        for owner, links in relationships.items():
            executable = Path('/synthetic') / archive.BUNDLES[owner][0]
            raw = lambda names: str(executable) + ':\n' + ''.join('\t' + name + ' (compatibility version 0.0.0, current version 0.0.0)\n' for name in names)
            with self.subTest(owner=owner):
                self.assertEqual([row['path'] for row in archive.linked_libraries(raw(links), executable, owner)], links)
                for missing in links:
                    with self.assertRaisesRegex(ValueError, 'missing'):
                        archive.linked_libraries(raw([name for name in links if name != missing]), executable, owner)
                extras = ['@rpath/Other.framework/Other', '@rpath/libswiftCompatibilitySpan.dylib',
                          '/System/Library/PrivateFrameworks/SnapKit.framework/SnapKit',
                          '/tmp/SnapKit.framework/SnapKit', '/usr/local/lib/libOther.dylib']
                extras += [name for name in (kit, snapkit) if name not in links]
                for extra in extras:
                    with self.assertRaisesRegex(ValueError, 'Unreviewed'):
                        archive.linked_libraries(raw(links + [extra]), executable, owner)
        executable = Path('/synthetic/CelluloidKit')
        with self.assertRaisesRegex(ValueError, 'install identity'):
            archive.linked_libraries(raw([snapkit, kit]), executable, archive.KIT)

    def test_snapkit_actual_architecture_platform_and_minimum_are_checked(self):
        for tool, old, new in [('lipo', b'arm64', b'x86_64'), ('vtool', b'platform IOS', b'platform IOSSIMULATOR'),
                               ('vtool', b'minos 15.0', b'minos 12.0')]:
            def changed(command, *args, **kwargs):
                result = observation(command, *args, **kwargs)
                if command[1] == tool and Path(command[-1]).name == archive.SNAPKIT_NAME:
                    result['output'] = result['output'].replace(old, new)
                return result
            with self.subTest(tool=tool), mock.patch.object(archive, 'bounded_optional_process', side_effect=changed):
                with self.assertRaises(ValueError):
                    self.package.verify()

    def test_changed_archive_during_tool_observation_cannot_qualify(self):
        def changed(command, *args, **kwargs):
            result = observation(command, *args, **kwargs)
            path = self.package.path / archive.APP / 'collage.json'
            path.write_bytes(path.read_bytes() + b' ')
            return result
        with mock.patch.object(archive, 'bounded_optional_process', side_effect=changed):
            with self.assertRaises(ValueError):
                self.package.verify()

    def test_fixed_clock_allocations_and_identity_validation(self):
        value = clock(100)
        for phase, (ceiling, deadline) in archive.PHASES.items():
            self.assertEqual(archive.admit(value, CONTEXT, phase, 100), ceiling)
            self.assertEqual(archive.admit(value, CONTEXT, phase, 100 + deadline - 1), 1)
            with self.assertRaises(ValueError):
                archive.admit(value, CONTEXT, phase, 100 + deadline)
        for changes in ({'started_monotonic': float('nan')}, {'started_monotonic': True}, {'execution_budget_seconds': 1800}, {'run_attempt': '1'}):
            with self.assertRaises(ValueError):
                archive.admit(dict(value, **changes), CONTEXT, 'proof', 101)

    def test_proof_deadline_shared_and_late_return_not_accepted(self):
        times = [100.0]
        def run(command, command_deadline, cleanup_deadline, cap):
            self.assertLessEqual(cleanup_deadline, 119)
            times[0] = 121
            return observation(command, command_deadline, cleanup_deadline, cap)
        with mock.patch.object(archive.time, 'monotonic', side_effect=lambda: times[0]), mock.patch.object(archive, 'bounded_optional_process', side_effect=run) as process:
            commands = archive.ProofCommands(120)
            with self.assertRaisesRegex(ValueError, 'deadline'):
                commands.run('lipo', Path('/synthetic/Celluloid'))
            with self.assertRaises(ValueError):
                commands.run('vtool', Path('/synthetic/Celluloid'))
            self.assertEqual(process.call_count, 1)

    def test_timeout_unknown_cleanup_overflow_and_spawn_exception_stop(self):
        for changes in ({'timed_out': True}, {'finalized': False, 'child_reaped': False}, {'overflow': True, 'finalized': False}, {'return_code': None}):
            with self.subTest(changes=changes), mock.patch.object(archive, 'bounded_optional_process', return_value=process_result(b'arm64\n', **changes)) as process:
                with self.assertRaises(ValueError):
                    self.package.verify()
                self.assertEqual(process.call_count, 1)
        with mock.patch.object(archive, 'bounded_optional_process', side_effect=OSError('spawn uncertain')) as process:
            commands = archive.ProofCommands(time.monotonic() + 180)
            with self.assertRaises(archive.ObservationFailure):
                commands.run('lipo', Path('/synthetic/Celluloid'))
            with self.assertRaisesRegex(ValueError, 'uncertain'):
                commands.run('otool', Path('/synthetic/Celluloid'))
            self.assertEqual(process.call_count, 1)

    def test_finalize_binds_actual_before_after_and_rows_then_refuses_changed_source(self):
        result = self.package.verify()
        archive.write_new(self.package.temp / archive.PACKAGE, result)
        after = dict(SOURCE, phase='after')
        put(self.package.temp / 'combined-source-after.json', archive.encoded(after))
        with mock.patch('uikit_full_shipping_handoff.source_proof', side_effect=lambda _, phase: SOURCE if phase == 'before' else after):
            final = archive.finalize(self.package.temp, CONTEXT, self.package.clock)
            self.assertTrue(final['source_unchanged'])
            self.assertFalse(final['release_acceptance'])
            self.assertEqual(final['source_after_sha256'], archive.sha((self.package.temp / 'combined-source-after.json').read_bytes()))
            after['tree'] = 'f' * 40
            with self.assertRaises(ValueError):
                archive.finalize(self.package.temp, CONTEXT, self.package.clock)
        with self.assertRaises(FileExistsError):
            archive.write_new(self.package.temp / archive.PACKAGE, result)

    def test_collect_preserves_mandatory_proof_first_with_500kb_manifest_inclusive_cap(self):
        result = self.package.verify()
        archive.write_new(self.package.temp / archive.PACKAGE, result)
        after = dict(SOURCE, phase='after')
        put(self.package.temp / 'combined-source-after.json', archive.encoded(after))
        put(self.package.temp / archive.CLOCK, archive.encoded(self.package.clock))
        with mock.patch('uikit_full_shipping_handoff.source_proof', side_effect=lambda _, phase: SOURCE if phase == 'before' else after):
            archive.write_new(self.package.temp / archive.OUTPUT, archive.finalize(self.package.temp, CONTEXT, self.package.clock))
        put(self.package.temp / 'archive.log', b'compiler chatter\n' * 100000)
        report = archive.collect(self.package.temp, CONTEXT, self.package.clock)
        self.assertTrue(report['unsigned_package_verified'])
        self.assertFalse(report['release_acceptance'])
        folder = self.package.temp / archive.EVIDENCE
        self.assertEqual(report['retained_total_bytes'], sum(path.stat().st_size for path in folder.iterdir()))
        self.assertLessEqual(report['retained_total_bytes'], 500000)
        self.assertLessEqual((folder / 'archive.log.tail.txt').stat().st_size, 80000)
        self.assertNotIn(archive.PACKAGE, {path.name for path in folder.iterdir()})
        self.assertFalse(any(path.suffix in {'.app', '.xcarchive', '.dSYM'} for path in folder.iterdir()))
        for row in report['files']:
            self.assertEqual(archive.sha((folder / row['name']).read_bytes()), row['sha256'])

    def test_failed_collection_retains_available_diagnostics_without_success(self):
        failure = {'schema': archive.SCHEMA, **CONTEXT, 'unsigned_package_verified': False,
                   'release_acceptance': False, 'all_processes_finalized': False, 'error': 'synthetic unknown cleanup'}
        put(self.package.temp / archive.PACKAGE, archive.encoded(failure))
        put(self.package.temp / archive.CLOCK, archive.encoded(self.package.clock))
        put(self.package.temp / 'archive.log', b'synthetic archive failed\n')
        report = archive.collect(self.package.temp, CONTEXT, self.package.clock)
        self.assertFalse(report['unsigned_package_verified'])
        self.assertIn(archive.OUTPUT, report['missing_required'])
        self.assertTrue((self.package.temp / archive.EVIDENCE / archive.PACKAGE).exists())
        self.assertLessEqual(report['retained_total_bytes'], 500000)
        with self.assertRaisesRegex(ValueError, 'cleanup uncertain'):
            archive.require_finalized_processes(self.package.temp, CONTEXT)

    def test_unknown_fixed_metadata_blocks_native_admission_but_retains_and_uploads_diagnostics(self):
        import contextlib,io
        from original_ios_fixed_rows import METADATA
        pending={'schema':'Celluloid.OriginalIOSFixedMetadata.1',**CONTEXT,'complete':False,'observations':{'producer':{'finalized':False}}}
        put(self.package.temp/METADATA,archive.encoded(pending))
        put(self.package.temp/archive.CLOCK,archive.encoded(self.package.clock))
        with mock.patch.object(archive,'identity',return_value=CONTEXT),mock.patch.dict(os.environ,RUNNER_TEMP=str(self.package.temp)),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(ValueError):archive.main(['admit','--phase','archive'])
            self.assertEqual(self.probes.call_count,0)
            manifest=archive.collect(self.package.temp,CONTEXT,self.package.clock)
            self.assertFalse(manifest['unsigned_package_verified'])
            self.assertEqual((self.package.temp/archive.EVIDENCE/METADATA).read_bytes(),archive.encoded(pending))
            archive.main(['admit','--phase','upload'])
        self.assertEqual(self.probes.call_count,0)

    def test_collector_rejects_symlink_input_and_does_not_overwrite_destination(self):
        output = self.package.temp / archive.OUTPUT
        output.symlink_to(self.package.temp / archive.ROWS_FILE)
        report = archive.collect(self.package.temp, CONTEXT, self.package.clock)
        self.assertFalse(report['unsigned_package_verified'])
        self.assertIn(archive.OUTPUT, report['missing_required'])
        with self.assertRaises(FileExistsError):
            archive.collect(self.package.temp, CONTEXT, self.package.clock)

    def test_real_owned_descendant_pipe_timeout_and_output_cap(self):
        descendant = 'import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);print("owned descendant",flush=True);time.sleep(8)'
        leader = 'import subprocess,sys;subprocess.Popen([sys.executable,"-c",' + repr(descendant) + ']);print("leader",flush=True)'
        started = time.monotonic()
        result = bounded_optional_process([sys.executable, '-c', leader], started + 0.2, started + 2)
        self.assertTrue(result['timed_out'])
        self.assertTrue(result['child_reaped'])
        self.assertLess(time.monotonic() - started, 2.5)
        started = time.monotonic()
        result = bounded_optional_process([sys.executable, '-c', 'import os,time;os.write(1,b"x"*100000);time.sleep(8)'], started + 1, started + 2, cap=1024)
        self.assertTrue(result['overflow'])
        self.assertEqual(len(result['output']), 1024)
        self.assertFalse(result['finalized'])
        self.assertTrue(result['child_reaped'])


if __name__ == '__main__':
    unittest.main()
