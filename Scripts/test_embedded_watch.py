import unittest, tempfile, plistlib, shutil
from unittest.mock import patch
from pathlib import Path
from verify_embedded_watch import bundle_checks, inventory, copied_inventory, discover_archive_producer

class EmbeddedWatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.phone = self.root / 'Celluloid.app'; self.watch = self.phone / 'Watch/CelluloidWatch.app'; self.watch.mkdir(parents=True)
        self.producer = self.root / 'ProducedWatch.app'
        self.phone_info = {'CFBundleIdentifier':'Mango.Celluloid','CFBundleExecutable':'Celluloid','CFBundleShortVersionString':'1.1','CFBundleVersion':'2','DTPlatformName':'iphoneos'}
        self.watch_info = {'CFBundleIdentifier':'Mango.Celluloid.watchkitapp','CFBundleExecutable':'CelluloidWatch','CFBundleShortVersionString':'1.1','CFBundleVersion':'2','DTPlatformName':'watchos','MinimumOSVersion':'9.0','WKApplication':True,'WKCompanionAppBundleIdentifier':'Mango.Celluloid'}
        (self.phone/'Info.plist').write_bytes(plistlib.dumps(self.phone_info)); (self.watch/'Info.plist').write_bytes(plistlib.dumps(self.watch_info))
        (self.watch/'CelluloidWatch').write_bytes(b'synthetic executable'); (self.watch/'Assets.car').write_bytes(b'synthetic catalog')
        for language in ['en','zh-Hans']:
            p = self.watch/(language+'.lproj'); p.mkdir(); (p/'Localizable.strings').write_text('"A"="B";')
        shutil.copytree(self.watch,self.producer)
    def tearDown(self): self.temp.cleanup()
    def test_exact_nested_identity_and_bytes(self):
        checks, _, _, privacy = bundle_checks(self.phone,self.producer,'device'); self.assertTrue(all(checks.values())); self.assertEqual(privacy,[])
    def test_version_and_changed_copy_are_rejected(self):
        self.watch_info['CFBundleVersion']='3'; (self.watch/'Info.plist').write_bytes(plistlib.dumps(self.watch_info))
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
        self.assertEqual(discover_archive_producer(root),a)
        b=root/'Other/Release-watchos/CelluloidWatch.app';b.mkdir(parents=True)
        with self.assertRaises(ValueError):discover_archive_producer(root)
