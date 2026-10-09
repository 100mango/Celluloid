import unittest, tempfile, plistlib, shutil, runpy
from unittest.mock import patch
from pathlib import Path
from verify_embedded_watch import bundle_checks, inventory, copied_inventory, discover_archive_producer,hosted_test_contract

class EmbeddedWatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.phone = self.root / 'Celluloid.app'; self.watch = self.phone / 'Watch/CelluloidWatch.app'; self.watch.mkdir(parents=True)
        self.producer = self.root / 'ProducedWatch.app'
        self.phone_info = {'CFBundleIdentifier':'Mango.Celluloid','CFBundleExecutable':'Celluloid','CFBundleShortVersionString':'1.1.1','CFBundleVersion':'3','DTPlatformName':'iphoneos'}
        self.watch_info = {'CFBundleIdentifier':'Mango.Celluloid.watchkitapp','CFBundleExecutable':'CelluloidWatch','CFBundleShortVersionString':'1.1.1','CFBundleVersion':'3','DTPlatformName':'watchos','MinimumOSVersion':'9.0','WKApplication':True,'WKCompanionAppBundleIdentifier':'Mango.Celluloid'}
        (self.phone/'Info.plist').write_bytes(plistlib.dumps(self.phone_info)); (self.watch/'Info.plist').write_bytes(plistlib.dumps(self.watch_info))
        (self.watch/'CelluloidWatch').write_bytes(b'synthetic executable'); (self.watch/'Assets.car').write_bytes(b'synthetic catalog')
        for language in ['en','zh-Hans']:
            p = self.watch/(language+'.lproj'); p.mkdir(); (p/'Localizable.strings').write_text('"A"="B";')
        shutil.copytree(self.watch,self.producer)
    def tearDown(self): self.temp.cleanup()
    def test_exact_nested_identity_and_bytes(self):
        checks, _, _, privacy = bundle_checks(self.phone,self.producer,'device'); self.assertTrue(all(checks.values())); self.assertEqual(privacy,[])
    def test_version_and_changed_copy_are_rejected(self):
        self.watch_info['CFBundleVersion']='4'; (self.watch/'Info.plist').write_bytes(plistlib.dumps(self.watch_info))
        checks, *_ = bundle_checks(self.phone,self.producer,'device'); self.assertFalse(checks['watch_version_equals_phone']); self.assertFalse(checks['exact_nested_producer_inventory'])
    def test_harness_or_wrong_companion_is_rejected(self):
        self.phone_info['CFBundleExecutable']='CelluloidPhoneCompanion'; (self.phone/'Info.plist').write_bytes(plistlib.dumps(self.phone_info))
        self.watch_info['WKCompanionAppBundleIdentifier']='Other.App'; (self.watch/'Info.plist').write_bytes(plistlib.dumps(self.watch_info))
        checks, *_ = bundle_checks(self.phone,self.producer,'device'); self.assertFalse(checks['shipping_phone_identity']); self.assertFalse(checks['watch_companion_binding'])
    def test_extra_watch_test_bundle_and_escaping_link_are_rejected(self):
        (self.phone/'Watch/Other.app').mkdir(); (self.phone/'Unexpected.xctest').mkdir()
        checks, *_ = bundle_checks(self.phone,self.producer,'device'); self.assertFalse(checks['only_expected_watch']); self.assertFalse(checks['no_test_products'])
        (self.watch/'escape').symlink_to('../outside')
        with self.assertRaises(ValueError): inventory(self.watch)

    def test_only_observed_device_strip_may_transform_executable(self):
        (self.watch/'CelluloidWatch').write_bytes(b'known stripped executable')
        log=self.root/'build.log';tool='/observed/Xcode/strip'
        log.write_text(f'{tool} -D -S -no_atom_info {self.producer}/CelluloidWatch -o {self.watch}/CelluloidWatch\n')
        def strip(command,**kwargs):Path(command[-1]).write_bytes(b'known stripped executable')
        with patch('verify_embedded_watch.subprocess.check_output',return_value=tool+'\n'),patch('verify_embedded_watch.subprocess.run',side_effect=strip):
            ok,receipt=copied_inventory(self.phone,self.producer,'device',log)
            self.assertTrue(ok);self.assertFalse(receipt['raw_inventory_equal']);self.assertTrue(receipt['all_nonexecutable_bytes_equal'])
            self.assertFalse(copied_inventory(self.phone,self.producer,'simulator',log)[0])
            self.assertFalse(copied_inventory(self.phone,self.producer,'device')[0])
            (self.watch/'Assets.car').write_bytes(b'changed resource')
            self.assertFalse(copied_inventory(self.phone,self.producer,'device',log)[0])

    def test_wrong_or_duplicate_strip_command_or_changed_result_is_rejected(self):
        (self.watch/'CelluloidWatch').write_bytes(b'nested')
        tool='/observed/Xcode/strip';line=f'{tool} -D -S -no_atom_info {self.producer}/CelluloidWatch -o {self.watch}/CelluloidWatch\n';log=self.root/'build.log'
        def strip(command,**kwargs):Path(command[-1]).write_bytes(b'wrong result')
        with patch('verify_embedded_watch.subprocess.check_output',return_value=tool+'\n'),patch('verify_embedded_watch.subprocess.run',side_effect=strip):
            for value in [line,line+line,line.replace('-S','-x'),line.replace(str(self.producer),str(self.root/'Other.app'))]:
                log.write_text(value);self.assertFalse(copied_inventory(self.phone,self.producer,'device',log)[0])

    def test_archive_discovery_is_bounded_to_actual_unique_release_producer(self):
        root=self.root/'Derived';a=root/'ArchiveIntermediates/Celluloid/BuildProductsPath/Release-watchos/CelluloidWatch.app';a.mkdir(parents=True)
        # macOS exposes temporary roots through /var -> /private/var. The
        # production discovery canonicalizes its root before enumerating it.
        self.assertEqual(discover_archive_producer(root),a.resolve())
        alias=self.root/'DerivedAlias';alias.symlink_to(root,target_is_directory=True)
        self.assertEqual(discover_archive_producer(alias),a.resolve())
        b=root/'Other/Release-watchos/CelluloidWatch.app';b.mkdir(parents=True)
        with self.assertRaises(ValueError):discover_archive_producer(root)

    def hosted_fixture(self):
        bundle=self.phone/'PlugIns/CelluloidCompanionTests.xctest';bundle.mkdir(parents=True)
        metadata={'CFBundleIdentifier':'Mango.Celluloid.CompanionTests','CFBundleExecutable':'CelluloidCompanionTests','DTPlatformName':'iphonesimulator','CFBundlePackageType':'BNDL'}
        (bundle/'Info.plist').write_bytes(plistlib.dumps(metadata));(bundle/'CelluloidCompanionTests').write_bytes(b'synthetic hosted test executable')
        return bundle,metadata

    def test_explicit_test_build_requires_the_actual_registered_bundle(self):
        self.assertFalse(hosted_test_contract(self.phone,'simulator',True)[0],'Missing test bundle must not count as a validated test build')
        self.hosted_fixture();ok,receipt=hosted_test_contract(self.phone,'simulator',True)
        self.assertTrue(ok);self.assertEqual(receipt['bundle_identifier'],'Mango.Celluloid.CompanionTests');self.assertEqual(len(receipt['executable_sha256']),64)
        self.assertFalse(hosted_test_contract(self.phone,'simulator',False)[0])
        self.assertFalse(hosted_test_contract(self.phone,'device',False)[0])
        with self.assertRaises(ValueError):hosted_test_contract(self.phone,'device',True)

    def test_extra_relocated_and_nested_watch_test_bundles_are_not_allowed(self):
        bundle,_=self.hosted_fixture()
        extra=self.phone/'Watch/CelluloidWatch.app/PlugIns/CelluloidWatchTests.xctest';extra.mkdir(parents=True)
        self.assertFalse(hosted_test_contract(self.phone,'simulator',True)[0]);shutil.rmtree(extra)
        bundle.rename(self.phone/'Other.xctest')
        self.assertFalse(hosted_test_contract(self.phone,'simulator',True)[0])

    def test_wrong_identity_executable_platform_empty_and_symlink_are_rejected(self):
        bundle,info=self.hosted_fixture()
        for key,value in [('CFBundleIdentifier','Other.Tests'),('CFBundleExecutable','OtherExecutable'),('DTPlatformName','iphoneos'),('CFBundlePackageType','APPL')]:
            changed=dict(info);changed[key]=value;(bundle/'Info.plist').write_bytes(plistlib.dumps(changed))
            self.assertFalse(hosted_test_contract(self.phone,'simulator',True)[0],key)
        (bundle/'Info.plist').write_bytes(plistlib.dumps(info));exe=bundle/'CelluloidCompanionTests';exe.write_bytes(b'')
        self.assertFalse(hosted_test_contract(self.phone,'simulator',True)[0]);exe.unlink();other=self.root/'outside';other.write_bytes(b'foreign executable');exe.symlink_to(other)
        self.assertFalse(hosted_test_contract(self.phone,'simulator',True)[0])

    def test_debug_only_application_copy_setting_preserves_all_release_settings(self):
        root=Path(__file__).resolve().parents[1]
        graph=runpy.run_path(str(root/'Scripts/generate_project.py'))
        objects=graph['objects'];configs=[]
        for target in graph['targetids'].values():
            node=objects[target]
            for identifier in objects[node['buildConfigurationList']]['buildConfigurations']:
                config=objects[identifier]
                if 'COPY_PHASE_STRIP' in config['buildSettings']:configs.append((node['name'],config['name'],config['buildSettings']['COPY_PHASE_STRIP']))
        self.assertEqual(configs,[('Celluloid','Debug','NO')])
