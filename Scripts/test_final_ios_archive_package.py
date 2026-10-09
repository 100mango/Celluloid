"""Synthetic Cell archive adversaries; no native build or package-acceptance claim."""
from pathlib import Path
import copy
import hashlib
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

import final_ios_archive_package as package

# Filled below with the exact already-reviewed source notice bytes, never downloaded.
NOTICE = b'Copyright (c) 2011-Present SnapKit Team - https://github.com/SnapKit\n\nPermission is hereby granted, free of charge, to any person obtaining a copy\nof this software and associated documentation files (the "Software"), to deal\nin the Software without restriction, including without limitation the rights\nto use, copy, modify, merge, publish, distribute, sublicense, and/or sell\ncopies of the Software, and to permit persons to whom the Software is\nfurnished to do so, subject to the following conditions:\n\nThe above copyright notice and this permission notice shall be included in\nall copies or substantial portions of the Software.\n\nTHE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR\nIMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\nFITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE\nAUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER\nLIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,\nOUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN\nTHE SOFTWARE.\n'


def put(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def dump(path, value):
    put(path, plistlib.dumps(value))


def strings(value):
    return ''.join(json.dumps(k, ensure_ascii=False) + ' = ' + json.dumps(v, ensure_ascii=False) + ';\n' for k, v in value.items()).encode()


def project_text(value):
    if isinstance(value, dict): return '{\n' + ''.join(json.dumps(k) + ' = ' + project_text(v) + ';\n' for k, v in value.items()) + '}'
    if isinstance(value, list): return '(' + ', '.join(project_text(v) for v in value) + ')'
    return json.dumps(str(value))


def synthetic_macho(index, kind, *, uuid_bytes=None, extra_commands=(), tail=b'synthetic-release'):
    identifier = bytes([index]) * 16 if uuid_bytes is None else uuid_bytes
    commands = [struct.pack('<II', 0x1b, 24) + identifier, *extra_commands]
    command_bytes = b''.join(commands)
    return struct.pack('<IIIIIIII', 0xfeedfacf, 0x100000c, 0, kind, len(commands), len(command_bytes), 0, 0) + command_bytes + tail


def process_result(output, **changes):
    result = {'return_code': 0, 'output': output, 'bytes_read': len(output), 'pipe_eof': True,
              'child_reaped': True, 'timed_out': False, 'overflow': False, 'cleanup_error': None,
              'finalized': True, 'elapsed_seconds': 0.001}
    result.update(changes); return result


def observation(command, command_deadline, cleanup_deadline, cap, stop_on_signal_error):
    if cap != 8192 or stop_on_signal_error is not True or not time.monotonic() < command_deadline < cleanup_deadline <= time.monotonic() + 20.1:
        raise AssertionError('Probe safety contract changed')
    tool, executable = command[1], command[-1]
    if tool == 'lipo': output = b'arm64\n'
    elif tool == 'vtool':
        output = (executable + ':\nLoad command 1\n      cmd LC_BUILD_VERSION\n  cmdsize 32\n platform IOS\n    minos 15.0\n      sdk 27.0\n   ntools 1\n     tool LD\n  version 123.0\n').encode()
    elif tool == 'otool':
        owner = next(path for path, values in package.BUNDLES.items() if values[0] == Path(executable).name)
        dependencies = sorted(package.BUNDLED_DEPENDENCIES[owner])
        if owner in package.INSTALL_NAMES: dependencies.insert(0, package.INSTALL_NAMES[owner])
        dependencies += ['/System/Library/Frameworks/UIKit.framework/UIKit']
        output = (executable + ':\n' + ''.join('\t' + dep + ' (compatibility version 1.0.0, current version 2.0.0)\n' for dep in dependencies)).encode()
    else: raise AssertionError('Unexpected native probe')
    return process_result(output)


class Fixture:
    def __init__(self, root):
        self.root = Path(root).resolve(); self.archive = self.root / package.ARCHIVE
        self.objects = {}; self.ids = {n: hashlib.sha1(n.encode()).hexdigest()[:24].upper() for n in ['Celluloid', 'CelluloidKit', 'CelluloidPhotoExtension', 'CelluloidTests', 'CelluloidUITests']}
        self.source(); self.product()

    def add(self, key, isa, **values):
        self.objects[key] = {'isa': isa, **values}; return key

    def write_project(self):
        put(self.root / 'Celluloid.xcodeproj/project.pbxproj', ('// !$*UTF8*$!\n' + project_text({'objects': self.objects}) + '\n').encode())

    def source(self):
        self.add('project', 'PBXProject', targets=list(self.ids.values()))
        self.add('snapkit', 'XCRemoteSwiftPackageReference', repositoryURL='https://github.com/SnapKit/SnapKit.git', requirement={'kind': 'exactVersion', 'version': '5.7.1'})
        self.add('domain', 'XCLocalSwiftPackageReference', relativePath='Packages/CelluloidCore')
        for name, identifier in self.ids.items():
            if name.endswith('Tests'):
                self.add(identifier, 'PBXNativeTarget', name=name); continue
            owner = {'Celluloid': package.APP, 'CelluloidKit': package.KIT, 'CelluloidPhotoExtension': package.EXT}[name]
            executable, bundle_id, kind, _ = package.BUNDLES[owner]
            suffix = {'Celluloid': '.app', 'CelluloidKit': '.framework', 'CelluloidPhotoExtension': '.appex'}[name]
            self.add(name + '-product', 'PBXFileReference', path=name + suffix, sourceTree='BUILT_PRODUCTS_DIR')
            info = {'CFBundleExecutable': '$(EXECUTABLE_NAME)', 'CFBundleIdentifier': '$(PRODUCT_BUNDLE_IDENTIFIER)', 'CFBundleName': '$(PRODUCT_NAME)', 'CFBundlePackageType': kind, 'CFBundleShortVersionString': '1.1.1', 'CFBundleVersion': '$(CURRENT_PROJECT_VERSION)' if name == 'CelluloidKit' else '3'}
            if name == 'Celluloid':
                info.update(NSPhotoLibraryUsageDescription='Choose photos.', NSPhotoLibraryAddUsageDescription='Save photos.', PHPhotoLibraryPreventAutomaticLimitedAccessAlert=True, UILaunchStoryboardName='LaunchScreen', UIRequiredDeviceCapabilities=['arm64'], UIApplicationSceneManifest={'UISceneConfigurations': {'UIWindowSceneSessionRoleApplication': [{'UISceneDelegateClassName': '$(PRODUCT_MODULE_NAME).SceneDelegate'}]}})
            if name == 'CelluloidPhotoExtension': info['NSExtension'] = {'NSExtensionAttributes': {'PHSupportedMediaTypes': ['Image']}, 'NSExtensionPointIdentifier': 'com.apple.photo-editing', 'NSExtensionMainStoryboard': 'MainInterface'}
            dump(self.root / name / 'Info.plist', info)
            settings = {'INFOPLIST_FILE': name + '/Info.plist', 'PRODUCT_NAME': '$(TARGET_NAME)', 'CURRENT_PROJECT_VERSION': '3', 'IPHONEOS_DEPLOYMENT_TARGET': '15.0', 'DEBUG_INFORMATION_FORMAT': 'dwarf-with-dsym', 'SWIFT_OPTIMIZATION_LEVEL': '-O', 'PRODUCT_BUNDLE_IDENTIFIER': bundle_id}
            if name == 'Celluloid': settings['ASSETCATALOG_COMPILER_APPICON_NAME'] = 'AppIcon'
            if name != 'Celluloid': settings.update(SKIP_INSTALL='YES', APPLICATION_EXTENSION_API_ONLY='YES')
            config = self.add(name + '-release', 'XCBuildConfiguration', name='Release', buildSettings=settings)
            configs = self.add(name + '-configs', 'XCConfigurationList', buildConfigurations=[config])
            dependencies = []
            for other in {'Celluloid': ['CelluloidKit', 'CelluloidPhotoExtension'], 'CelluloidKit': [], 'CelluloidPhotoExtension': ['CelluloidKit']}[name]:
                proxy = self.add(name + '-' + other + '-proxy', 'PBXContainerItemProxy', containerPortal='project', remoteGlobalIDString=self.ids[other], remoteInfo=other)
                dependencies.append(self.add(name + '-' + other + '-dependency', 'PBXTargetDependency', target=self.ids[other], targetProxy=proxy))
            packages, frameworks = [], []
            for product in {'Celluloid': ['SnapKit'], 'CelluloidKit': ['SnapKit', 'CelluloidDomain'], 'CelluloidPhotoExtension': []}[name]:
                key = self.add(name + '-' + product, 'XCSwiftPackageProductDependency', productName=product, package='snapkit' if product == 'SnapKit' else 'domain')
                packages.append(key); frameworks.append(self.add(key + '-link', 'PBXBuildFile', productRef=key))
            if name != 'CelluloidKit': frameworks.append(self.add(name + '-kit-link', 'PBXBuildFile', fileRef='CelluloidKit-product'))
            resource_entries = []
            for index, path in enumerate(sorted(package.SOURCE_RESOURCES[name])):
                ref = self.add(name + '-resource-' + str(index), 'PBXFileReference', path=path, sourceTree='<group>')
                resource_entries.append(self.add(ref + '-build', 'PBXBuildFile', fileRef=ref))
                raw = b'synthetic-resource'
                if path.endswith('/Localizable.strings'): raw = strings({'one': 'one' if '/en.lproj/' in path else '一'})
                if path.endswith('InfoPlist.strings'): raw = strings({'NSPhotoLibraryUsageDescription': '选择照片。', 'NSPhotoLibraryAddUsageDescription': '保存照片。'})
                if path.endswith('SnapKit-LICENSE.txt'): raw = NOTICE
                if not path.endswith('.xcassets'): put(self.root / path, raw)
            phases = [self.add(name + '-sources', 'PBXSourcesBuildPhase', files=[]), self.add(name + '-frameworks', 'PBXFrameworksBuildPhase', files=frameworks), self.add(name + '-resources', 'PBXResourcesBuildPhase', files=resource_entries)]
            if name == 'Celluloid':
                for other, destination in [('CelluloidKit', '10'), ('CelluloidPhotoExtension', '13')]:
                    build = self.add('embed-' + other, 'PBXBuildFile', fileRef=other + '-product', settings={'ATTRIBUTES': ['RemoveHeadersOnCopy', 'CodeSignOnCopy']})
                    phases.append(self.add('copy-' + other, 'PBXCopyFilesBuildPhase', files=[build], dstSubfolderSpec=destination))
            product_type = {'Celluloid': 'application', 'CelluloidKit': 'framework', 'CelluloidPhotoExtension': 'app-extension'}[name]
            self.add(identifier, 'PBXNativeTarget', name=name, productType='com.apple.product-type.' + product_type, productReference=name + '-product', dependencies=dependencies, packageProductDependencies=packages, buildPhases=phases, buildConfigurationList=configs)
        self.write_project()
        put(self.root / 'Celluloid/Assets.xcassets/AppIcon.appiconset/Contents.json', json.dumps({'images': [{'idiom': 'ios-marketing', 'size': '1024x1024', 'scale': '1x', 'filename': 'marketing.png'}]}).encode())
        scheme = '<Scheme><BuildAction><BuildActionEntries><BuildActionEntry buildForArchiving="YES"><BuildableReference BlueprintIdentifier="' + self.ids['Celluloid'] + '" BlueprintName="Celluloid" BuildableName="Celluloid.app" ReferencedContainer="container:Celluloid.xcodeproj"/></BuildActionEntry></BuildActionEntries></BuildAction><ArchiveAction buildConfiguration="Release"/></Scheme>'
        put(self.root / 'Celluloid.xcodeproj/xcshareddata/xcschemes/Celluloid.xcscheme', scheme.encode())
        put(self.root / 'Packages/CelluloidCore/Package.swift', b'.library(name: "CelluloidDomain", targets: ["CelluloidDomain"])\n.target(name: "CelluloidDomain", resources: [.process("Resources")])\n')
        for language in ['en', 'zh-Hans']:
            put(self.root / package.DOMAIN_SOURCE / (language + '.lproj/Localizable.strings'), strings({'filter.Original': 'Original' if language == 'en' else '原片'}))
        put(self.root / 'Celluloid.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved', json.dumps({'pins': [{'identity': 'snapkit', 'kind': 'remoteSourceControl', 'location': 'https://github.com/SnapKit/SnapKit.git', 'state': {'revision': package.SNAPKIT_REVISION, 'version': '5.7.1'}}], 'version': 2}).encode())

    def product(self):
        graph = package.source_graph(self.root)
        dump(self.archive / 'Info.plist', {'ArchiveVersion': 2, 'SchemeName': 'Celluloid', 'ApplicationProperties': {'ApplicationPath': 'Applications/Celluloid.app', 'CFBundleIdentifier': 'Mango.Celluloid', 'CFBundleShortVersionString': '1.1.1', 'CFBundleVersion': '3'}})
        for index, (owner, (name, identifier, kind, filetype)) in enumerate(package.BUNDLES.items(), 1):
            info = {} if owner == package.SNAPKIT else plistlib.loads((self.root / name / 'Info.plist').read_bytes())
            info.update(CFBundleExecutable=name, CFBundleIdentifier=identifier, CFBundleName=name, CFBundlePackageType=kind, CFBundleShortVersionString='1.0' if owner == package.SNAPKIT else '1.1.1', CFBundleVersion='1' if owner == package.SNAPKIT else '3', DTPlatformName='iphoneos', CFBundleSupportedPlatforms=['iPhoneOS'], MinimumOSVersion='15.0', UIDeviceFamily=[1, 2])
            if owner == package.APP: info['UIApplicationSceneManifest'] = json.loads(json.dumps(info['UIApplicationSceneManifest']).replace('$(PRODUCT_MODULE_NAME)', name))
            dump(self.archive / owner / 'Info.plist', info)
            put(self.archive / owner / name, synthetic_macho(index, filetype))
            put(self.archive / package.DSYMS[owner], synthetic_macho(index, 10))
        for target, source in [(package.APP + '/collage.json', 'Celluloid/collage.json'), (package.KIT + '/bubble.json', 'CelluloidKit/bubble.json'), (package.KIT + '/SnapKit-LICENSE.txt', 'CelluloidKit/ThirdPartyNotices/SnapKit-LICENSE.txt')]: put(self.archive / target, (self.root / source).read_bytes())
        for name, owner in [('Celluloid', package.APP), ('CelluloidKit', package.KIT)]:
            put(self.archive / owner / 'Assets.car', b'synthetic-catalog')
            for language in ['en', 'zh-Hans']:
                source = self.root / graph['localization_sources'][name + '/' + language]
                dump(self.archive / owner / (language + '.lproj/Localizable.strings'), package.source_strings(source.read_bytes()))
        dump(self.archive / package.APP / 'zh-Hans.lproj/InfoPlist.strings', package.source_strings((self.root / 'Celluloid/zh-Hans.lproj/InfoPlist.strings').read_bytes()))
        for directory in [package.APP + '/Base.lproj/LaunchScreen.storyboardc', package.EXT + '/Base.lproj/MainInterface.storyboardc']:
            put(self.archive / directory / 'compiled.nib', b'synthetic-storyboard')
        for owner in package.SNAPKIT_RESOURCES:
            dump(self.archive / owner / 'Info.plist', {'CFBundlePackageType': 'BNDL'})
            dump(self.archive / owner / 'PrivacyInfo.xcprivacy', package.PRIVACY)
        self.domain(package.KIT)

    def domain(self, owner):
        bundle = self.archive / owner / package.DOMAIN_NAME
        dump(bundle / 'Info.plist', {'CFBundleName': 'CelluloidCore_CelluloidDomain', 'CFBundlePackageType': 'BNDL'})
        for language in ['en', 'zh-Hans']:
            dump(bundle / (language + '.lproj/Localizable.strings'), package.source_strings((self.root / package.DOMAIN_SOURCE / (language + '.lproj/Localizable.strings')).read_bytes()))

    def verify(self, probe=observation):
        with mock.patch.object(package, 'bounded_optional_process', side_effect=probe) as mocked:
            result = package.verify_package(self.root, time.monotonic() + 180)
        return result, mocked.call_count


class ArchivePackageTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(); self.addCleanup(self.folder.cleanup)
        self.fixture = Fixture(Path(self.folder.name))

    def mutate_plist(self, relative, transform):
        path = self.fixture.archive / relative
        value = plistlib.loads(path.read_bytes()); transform(value); dump(path, value)

    def test_full_synthetic_package_has_four_matched_uuid_pairs(self):
        result, calls = self.fixture.verify()
        self.assertEqual(calls, 12)
        self.assertTrue(result['unsigned_package_verified'])
        self.assertFalse(result['release_acceptance'])
        self.assertFalse(result['signing_qualified'])
        self.assertEqual(len(result['code_bundles']), 4)
        self.assertTrue(all(row['uuid_match'] for row in result['code_bundles']))
        self.assertEqual([row['path'] for row in result['domain_resource_bundles']], [package.KIT + '/' + package.DOMAIN_NAME])
        self.assertFalse(result['app_icon_observation']['visual_or_rendition_qualification'])

    def test_actual_icon_declarations_and_positive_file_matches_are_recorded(self):
        self.mutate_plist(package.APP + '/Info.plist', lambda value: value.update(CFBundleIcons={'CFBundlePrimaryIcon': {'CFBundleIconName': 'AppIcon', 'CFBundleIconFiles': ['AppIcon60x60']}}))
        put(self.fixture.archive / package.APP / 'AppIcon60x60@2x.png', b'synthetic-icon')
        result, _ = self.fixture.verify()
        observation = result['app_icon_observation']
        self.assertEqual(observation['observed_icon_names'], ['AppIcon'])
        self.assertTrue(observation['all_observed_file_references_matched'])
        self.mutate_plist(package.APP + '/Info.plist', lambda value: value['CFBundleIcons']['CFBundlePrimaryIcon'].update(CFBundleIconName='Wrong'))
        with self.assertRaisesRegex(ValueError, 'icon name'): self.fixture.verify()

    def test_both_hosts_can_supply_domain_when_kit_copy_absent(self):
        shutil.rmtree(self.fixture.archive / package.KIT / package.DOMAIN_NAME)
        self.fixture.domain(package.APP); self.fixture.domain(package.EXT)
        result, _ = self.fixture.verify()
        self.assertEqual({row['path'] for row in result['domain_resource_bundles']}, {package.APP + '/' + package.DOMAIN_NAME, package.EXT + '/' + package.DOMAIN_NAME})

    def test_single_host_domain_cannot_serve_both_products(self):
        shutil.rmtree(self.fixture.archive / package.KIT / package.DOMAIN_NAME)
        self.fixture.domain(package.APP)
        with self.assertRaisesRegex(ValueError, 'reachable'): self.fixture.verify()

    def test_unrelated_domain_owner_rejected(self):
        self.fixture.domain(package.SNAPKIT)
        with self.assertRaisesRegex(ValueError, 'Extra resource bundle'): self.fixture.verify()

    def test_missing_extra_and_altered_domain_localization_fail(self):
        path = self.fixture.archive / package.KIT / package.DOMAIN_NAME / 'en.lproj/Localizable.strings'
        original = path.read_bytes()
        for value in [{}, {'filter.Original': 'changed'}, {'filter.Original': 'Original', 'extra': 'extra'}]:
            with self.subTest(value=value):
                dump(path, value)
                with self.assertRaises(ValueError): self.fixture.verify()
        path.write_bytes(original); path.unlink()
        with self.assertRaises(ValueError): self.fixture.verify()

    def test_extra_domain_resource_file_and_directory_fail(self):
        path = self.fixture.archive / package.KIT / package.DOMAIN_NAME / 'extra.txt'
        put(path, b'extra')
        with self.assertRaisesRegex(ValueError, 'resource bundle content'): self.fixture.verify()
        path.unlink(); path.with_name('extra-directory').mkdir()
        with self.assertRaisesRegex(ValueError, 'resource bundle content'): self.fixture.verify()

    def test_domain_copies_are_byte_identical(self):
        self.fixture.domain(package.APP)
        path = self.fixture.archive / package.APP / package.DOMAIN_NAME / 'en.lproj/Localizable.strings'
        path.write_bytes(path.read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'exact bytes'): self.fixture.verify()

    def test_all_four_dsyms_are_required(self):
        for path in package.DSYMS.values():
            with self.subTest(path=path):
                file = self.fixture.archive / path; raw = file.read_bytes(); file.unlink()
                with self.assertRaisesRegex(ValueError, 'dSYM'): self.fixture.verify()
                file.write_bytes(raw)

    def test_each_binary_dsym_uuid_mismatch_rejected(self):
        for path in package.DSYMS.values():
            with self.subTest(path=path):
                file = self.fixture.archive / path; raw = file.read_bytes(); file.write_bytes(synthetic_macho(9, 10))
                with self.assertRaisesRegex(ValueError, 'UUID'): self.fixture.verify()
                file.write_bytes(raw)

    def test_duplicate_zero_and_missing_uuid_rejected(self):
        for raw in [synthetic_macho(1, 2, uuid_bytes=b'\0' * 16), synthetic_macho(1, 2, extra_commands=[struct.pack('<II', 0x1b, 24) + b'2' * 16]), struct.pack('<IIIIIIII', 0xfeedfacf, 0x100000c, 0, 2, 1, 8, 0, 0) + struct.pack('<II', 1, 8)]:
            with self.subTest(raw=raw[:16]), self.assertRaises(ValueError): package.macho_header(raw, len(raw), 2)

    def test_dwarf_file_type_architecture_and_unknown_bundle_fail(self):
        file = self.fixture.archive / package.DSYMS[package.APP]; raw = file.read_bytes()
        file.write_bytes(synthetic_macho(1, 2))
        with self.assertRaises(ValueError): self.fixture.verify()
        file.write_bytes(raw)
        put(self.fixture.archive / 'dSYMs/Other.app.dSYM/Contents/Resources/DWARF/Other', synthetic_macho(8, 10))
        with self.assertRaisesRegex(ValueError, 'Extra symbol bundle'): self.fixture.verify()

    def test_duplicate_uuid_across_bundles_rejected(self):
        put(self.fixture.archive / package.KIT / 'CelluloidKit', synthetic_macho(1, 6))
        put(self.fixture.archive / package.DSYMS[package.KIT], synthetic_macho(1, 10))
        with self.assertRaisesRegex(ValueError, 'Duplicate UUID'): self.fixture.verify()

    def test_owned_and_snapkit_versions_remain_distinct(self):
        for owner in package.BUNDLES:
            with self.subTest(owner=owner):
                file = self.fixture.archive / owner / 'Info.plist'; raw = file.read_bytes()
                self.mutate_plist(owner + '/Info.plist', lambda value: value.update(CFBundleShortVersionString='1.1.1' if owner == package.SNAPKIT else '1.0'))
                with self.assertRaises(ValueError): self.fixture.verify()
                file.write_bytes(raw)

    def test_photos_privacy_and_extension_metadata_changes_fail(self):
        for owner, key in [(package.APP, 'NSPhotoLibraryUsageDescription'), (package.EXT, 'NSExtension')]:
            file = self.fixture.archive / owner / 'Info.plist'; raw = file.read_bytes()
            self.mutate_plist(owner + '/Info.plist', lambda value: value.pop(key))
            with self.assertRaises(ValueError): self.fixture.verify()
            file.write_bytes(raw)

    def test_snapkit_privacy_alteration_or_extra_app_manifest_fails(self):
        path = self.fixture.archive / sorted(package.SNAPKIT_RESOURCES)[0] / 'PrivacyInfo.xcprivacy'
        raw = path.read_bytes(); dump(path, dict(package.PRIVACY, NSPrivacyTracking=True))
        with self.assertRaises(ValueError): self.fixture.verify()
        path.write_bytes(raw)
        dump(self.fixture.archive / package.APP / 'PrivacyInfo.xcprivacy', package.PRIVACY)
        with self.assertRaisesRegex(ValueError, 'Unreviewed privacy'): self.fixture.verify()

    def test_empty_storyboard_and_changed_current_localizations_fail(self):
        path = self.fixture.archive / package.APP / 'Base.lproj/LaunchScreen.storyboardc/compiled.nib'
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'empty compiled'): self.fixture.verify()
        put(path, b'compiled')
        dump(self.fixture.archive / package.APP / 'en.lproj/Localizable.strings', {'stale': 'localization'})
        with self.assertRaisesRegex(ValueError, 'localization differs'): self.fixture.verify()

    def test_debug_markers_and_hidden_macho_payload_fail(self):
        executable = self.fixture.archive / package.APP / 'Celluloid'; raw = executable.read_bytes()
        executable.write_bytes(raw + b'--picker-seeded-identity')
        with self.assertRaisesRegex(ValueError, 'Debug/test seam'): self.fixture.verify()
        executable.write_bytes(raw)
        put(self.fixture.archive / package.APP / 'harmless.txt', synthetic_macho(7, 2))
        with self.assertRaisesRegex(ValueError, 'Unexpected executable'): self.fixture.verify()

    def test_symlink_and_hardlink_resource_rejected(self):
        target = self.fixture.archive / package.APP / 'extra'
        target.symlink_to('collage.json')
        with self.assertRaisesRegex(ValueError, 'symlink'): self.fixture.verify()
        target.unlink(); os.link(self.fixture.archive / package.APP / 'collage.json', target)
        with self.assertRaisesRegex(ValueError, 'Unsafe'): self.fixture.verify()

    def test_probe_failure_retains_events_and_blocks_later_dispatch(self):
        def failed(*args, **kwargs): return process_result(b'', finalized=False, child_reaped=False, cleanup_error='PermissionError')
        with self.assertRaises(package.ObservationFailure) as caught: self.fixture.verify(failed)
        self.assertEqual(len(caught.exception.events), 1)
        self.assertFalse(caught.exception.all_processes_finalized)

    def test_raised_helper_failure_never_claims_cleanup(self):
        def interrupted(*args, **kwargs): raise KeyboardInterrupt('synthetic interruption')
        with self.assertRaises(package.ObservationFailure) as caught: self.fixture.verify(interrupted)
        self.assertFalse(caught.exception.all_processes_finalized)
        self.assertEqual(caught.exception.events, [])

    def test_later_resource_failure_retains_completed_probe_receipts(self):
        dump(self.fixture.archive / package.KIT / package.DOMAIN_NAME / 'en.lproj/Localizable.strings', {'wrong': 'resource'})
        with self.assertRaises(package.ObservationFailure) as caught: self.fixture.verify()
        self.assertTrue(caught.exception.all_processes_finalized)
        self.assertEqual(len(caught.exception.events), 12)

    def test_probe_private_dependency_and_wrong_platform_fail(self):
        def wrong_platform(command, *args, **kwargs):
            result = observation(command, *args, **kwargs)
            if command[1] == 'vtool': result['output'] = result['output'].replace(b'platform IOS', b'platform IOSSIMULATOR')
            return result
        with self.assertRaisesRegex(ValueError, 'platform'): self.fixture.verify(wrong_platform)
        executable = Path('/synthetic/Celluloid')
        with self.assertRaises(ValueError): package.linked_libraries(str(executable) + ':\n\t/private/secret.dylib (compatibility version 1.0, current version 1.0)\n', executable, package.APP)

    def test_expired_deadline_and_nonstandard_archive_path_fail(self):
        with self.assertRaisesRegex(ValueError, 'deadline'): package.verify_package(self.fixture.root, time.monotonic() - 1)
        with self.assertRaisesRegex(ValueError, 'archive path'): package.verify_package(self.fixture.root, time.monotonic() + 180, archive_relative='../other')

    def test_scheme_target_id_name_and_release_mismatches_fail(self):
        path = self.fixture.root / 'Celluloid.xcodeproj/xcshareddata/xcschemes/Celluloid.xcscheme'; original = path.read_text()
        for before, after in [(self.fixture.ids['Celluloid'], self.fixture.ids['CelluloidTests']), ('BlueprintName="Celluloid"', 'BlueprintName="CelluloidKit"'), ('buildConfiguration="Release"', 'buildConfiguration="Debug"')]:
            path.write_text(original.replace(before, after))
            with self.assertRaises(ValueError): package.source_graph(self.fixture.root)
        path.write_text(original)

    def test_actual_dependencies_copy_phases_and_links_must_reach_products(self):
        original = copy.deepcopy(self.fixture.objects)
        mutations = [lambda o: o[self.fixture.ids['Celluloid']]['dependencies'].pop(),
                     lambda o: o['copy-CelluloidPhotoExtension'].update(dstSubfolderSpec='10'),
                     lambda o: o['CelluloidKit-frameworks']['files'].pop(),
                     lambda o: o['project']['targets'].pop()]
        for mutate in mutations:
            self.fixture.objects = copy.deepcopy(original); mutate(self.fixture.objects); self.fixture.write_project()
            with self.assertRaises(ValueError): package.source_graph(self.fixture.root)

    def test_source_metadata_and_resource_closure_fail_closed(self):
        original = copy.deepcopy(self.fixture.objects)
        for key, value in [('CURRENT_PROJECT_VERSION', '4'), ('DEBUG_INFORMATION_FORMAT', 'dwarf'), ('IPHONEOS_DEPLOYMENT_TARGET', '17.0'), ('SWIFT_ACTIVE_COMPILATION_CONDITIONS', 'DEBUG')]:
            self.fixture.objects = copy.deepcopy(original); self.fixture.objects['CelluloidKit-release']['buildSettings'][key] = value; self.fixture.write_project()
            with self.assertRaises(ValueError): package.source_graph(self.fixture.root)

    def test_source_strings_comments_are_not_stripped_inside_values(self):
        self.assertEqual(package.source_strings(b'/* comment */ "URL" = "https://site/a/*b*/"; // comment\n'), {'URL': 'https://site/a/*b*/'})
        with self.assertRaises(ValueError): package.source_strings(b'"key"="1";"key"="2";')
        self.assertEqual(package.strings_plist('"key"="value";'.encode('utf16')), {'key': 'value'})

    def test_optimized_import_and_rejection_are_dependency_closed(self):
        code = "import final_ios_archive_package as p\ntry: p.verify_package('.', 0)\nexcept ValueError: pass\nelse: raise SystemExit('optimized guard bypass')\n"
        result = subprocess.run([sys.executable, '-B', '-O', '-S', '-c', code], cwd=Path(__file__).parent, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__': unittest.main()
