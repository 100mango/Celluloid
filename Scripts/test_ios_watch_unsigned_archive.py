"""Portable synthetic archive and owned-process tests; no native runtime claim."""
import copy, datetime, hashlib, json, os
from pathlib import Path
import plistlib, shutil, struct, subprocess, sys, tempfile, time, unittest, uuid
from unittest.mock import patch
import ios_watch_unsigned_archive as m
ROOT=Path(__file__).resolve().parents[1]
UUIDS={0x100000c:'11111111-2222-3333-4444-555555555555',0x200000c:'66666666-7777-8888-9999-AAAAAAAAAAAA'}


def thin(cpu,kind=2,platform=4,minimum=(9,0,0),identity=None,wide=True,signature=False,sdk=(27,0,0),links=None,install=None):
    packed=lambda v:(v[0]<<16)|(v[1]<<8)|v[2]
    cmds=[struct.pack('<6I',0x32,24,platform,packed(minimum),packed(sdk),0),
          struct.pack('<2I',0x1b,24)+uuid.UUID(identity or UUIDS[cpu]).bytes]
    links=['/System/Library/Frameworks/WatchConnectivity.framework/WatchConnectivity'] if links is None else links
    for command,value in [(0xc,x) for x in links]+([(0xd,install)] if install else []):
        link=value.encode()+b'\0';size=(24+len(link)+7)//8*8
        cmds.append(struct.pack('<6I',command,size,24,0,0,0)+link+b'\0'*(size-24-len(link)))
    if signature:cmds.append(struct.pack('<4I',0x1d,16,100,32))
    body=b''.join(cmds);head=struct.pack('<7I',0xfeedfacf if wide else 0xfeedface,cpu,0,kind,len(cmds),len(body),0)
    return head+(struct.pack('<I',0) if wide else b'')+body


def fat(parts):
    offset=8+20*len(parts);table=[];payload=[]
    for cpu,raw in parts:
        table.append(struct.pack('>5I',cpu,0,offset,len(raw),0));payload.append(raw);offset+=len(raw)
    return struct.pack('>2I',0xcafebabe,len(parts))+b''.join(table)+b''.join(payload)


class Clock:
    def __init__(self,value=100):self.value=value
    def __call__(self):return self.value


def fixture(root):
    a=root/m.ARCHIVE;a.mkdir(parents=True)
    (a/'Info.plist').write_bytes(plistlib.dumps({'ArchiveVersion':2,'SchemeName':'Celluloid',
      'CreationDate':datetime.datetime(2026,10,7),'ApplicationProperties':{'ApplicationPath':'Applications/Celluloid.app',
      'CFBundleIdentifier':'Mango.Celluloid','CFBundleShortVersionString':'1.1','CFBundleVersion':'2'}}))
    def copy_source(source,destination):
        sp=root/source;sp.parent.mkdir(parents=True,exist_ok=True);sp.write_bytes((ROOT/source).read_bytes())
        destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(sp.read_bytes())
    for role,spec in m.SPECS.items():
        app=a/spec['app'];app.mkdir(parents=True,exist_ok=True)
        info={'CFBundleIdentifier':spec['bundle'],'CFBundleExecutable':spec['executable'],'CFBundlePackageType':spec['package'],
          'CFBundleShortVersionString':spec['version'],'CFBundleVersion':spec['build'],'MinimumOSVersion':spec['floor'],
          'CFBundleSupportedPlatforms':spec['platforms'],'DTPlatformName':spec['platform_name']}
        if 'family' in spec:info['UIDeviceFamily']=spec['family']
        if role=='watch':info.update(WKApplication=True,WKCompanionAppBundleIdentifier='Mango.Celluloid')
        if role in ('phone','watch'):
            info['CFBundleIconName']='AppIcon';(app/'PkgInfo').write_bytes(b'APPL????');(app/'Assets.car').write_bytes(b'synthetic catalog'*10)
        if role in ('phone','watch','kit'):
            src='Celluloid' if role=='phone' else 'CelluloidKit/Constant' if role=='kit' else 'Platforms/Resources'
            for language in ('en','zh-Hans'):
                path=language+'.lproj/Localizable.strings';copy_source(src+'/'+path,app/path)
        if role=='phone':
            source='Celluloid/Info.plist';sp=root/source;sp.parent.mkdir(parents=True,exist_ok=True);sp.write_bytes((ROOT/source).read_bytes())
            original=plistlib.loads(sp.read_bytes())
            for key in ('NSPhotoLibraryUsageDescription','NSPhotoLibraryAddUsageDescription','PHPhotoLibraryPreventAutomaticLimitedAccessAlert','UILaunchStoryboardName','UIRequiredDeviceCapabilities'):info[key]=original[key]
            copy_source('Celluloid/collage.json',app/'collage.json');copy_source('Celluloid/zh-Hans.lproj/InfoPlist.strings',app/'zh-Hans.lproj/InfoPlist.strings')
            (app/'Base.lproj/LaunchScreen.storyboardc').mkdir(parents=True);(app/'Base.lproj/LaunchScreen.storyboardc/compiled.nib').write_bytes(b'compiled')
        if role=='kit':
            (app/'Assets.car').write_bytes(b'kit catalog'*10);copy_source('CelluloidKit/bubble.json',app/'bubble.json');copy_source('CelluloidKit/ThirdPartyNotices/SnapKit-LICENSE.txt',app/'SnapKit-LICENSE.txt')
        if role=='extension':
            source='CelluloidPhotoExtension/Info.plist';sp=root/source;sp.parent.mkdir(parents=True,exist_ok=True);sp.write_bytes((ROOT/source).read_bytes());info['NSExtension']=plistlib.loads(sp.read_bytes())['NSExtension']
            (app/'Base.lproj/MainInterface.storyboardc').mkdir(parents=True);(app/'Base.lproj/MainInterface.storyboardc/compiled.nib').write_bytes(b'compiled')
        if role=='watch':
            copy_source('LICENSE.txt',app/'LICENSE.txt');copy_source('Platforms/Resources/PrivacyPolicy.txt',app/'PrivacyPolicy.txt')
        (app/'Info.plist').write_bytes(plistlib.dumps(info))
        links=['/System/Library/Frameworks/WatchConnectivity.framework/WatchConnectivity']+sorted(m.BUNDLED_DEPENDENCIES[spec['app']])
        parts=[(cpu,thin(cpu,kind=spec['kind'],platform=spec['platform'],minimum=minimum,sdk=spec['sdk'],links=links,install=m.INSTALL_NAMES.get(spec['app']))) for cpu,(_,minimum) in spec['arches'].items()]
        symbols=[(cpu,thin(cpu,kind=10,platform=spec['platform'],minimum=minimum,sdk=spec['sdk'])) for cpu,(_,minimum) in spec['arches'].items()]
        raw=parts[0][1] if len(parts)==1 else fat(parts)
        if role=='phone':raw+=b'\0PhoneCompanionController\0PhoneCompanionEntryController\0'
        (a/spec['binary']).write_bytes(raw)
        dwarf=a/spec['dwarf'];dwarf.parent.mkdir(parents=True);dwarf.write_bytes(symbols[0][1] if len(symbols)==1 else fat(symbols))
        (a/spec['dsym']/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'com.apple.xcode.dsym.'+spec['bundle'],'CFBundlePackageType':'dSYM'}))
    for bundle in m.RESOURCE_BUNDLES:
        app=a/bundle;app.mkdir(parents=True)
        (app/'Info.plist').write_bytes(plistlib.dumps({'CFBundlePackageType':'BNDL'}))
        if bundle in m.SNAPKIT_RESOURCES:(app/'PrivacyInfo.xcprivacy').write_bytes(plistlib.dumps(m.PRIVACY))
        else:
            for relative,source in m.PACKAGE_RESOURCES[bundle].items():copy_source(source,app/relative)
    producer=root/m.DERIVED/'Build/Intermediates.noindex/ArchiveIntermediates/Celluloid/BuildProductsPath/Release-watchos/CelluloidWatch.app'
    shutil.copytree(a/m.WATCH,producer)
    return a,producer


class ArchiveProofTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.a,self.producer=fixture(self.root);self.clock=Clock();self.report={};self.calls=[]
    def tearDown(self):self.tmp.cleanup()
    def invoke(self,argv,**kwargs):
        self.calls.append(argv)
        if argv[:3]==['xcrun','assetutil','--info']:
            return json.dumps([{'Name':'AppIcon','PixelWidth':1024,'PixelHeight':1024,'Scale':1}]).encode()
        if argv[:3]==['xcrun','dwarfdump','--uuid']:
            return ''.join(f'UUID: {v["uuid"]} ({m.SPECS["watch"]["arches"][v["cpu"]][0]}) {p}\n' for p in argv[3:] for v in m.mach_slices(Path(p).read_bytes())).encode()
        if argv[:5]==['xcrun','strip','-D','-S','-no_atom_info']:
            Path(argv[-1]).write_bytes((self.a/m.SPECS['watch']['binary']).read_bytes());return b''
        raise AssertionError(argv)
    def verify(self):return m.verify_archive(self.a,self.invoke,1000,root=self.root,clock=self.clock,report=self.report)
    def mutate_info(self,role,key,value):
        p=self.a/m.SPECS[role]['app']/'Info.plist';v=plistlib.loads(p.read_bytes());v[key]=value;p.write_bytes(plistlib.dumps(v))
    def test_exact_five_products_six_device_slices_and_five_symbols(self):
        result=self.verify();self.assertTrue(result['unsigned']);self.assertEqual(len(result['native_uuid_readback']),12)
        self.assertFalse(result['distribution_version_ready']);self.assertEqual(result['watch_copy']['transform'],'exact')
        self.assertTrue(self.report['archive_inventory']['complete'])
    def test_fixed_product_identity_negative_matrix(self):
        cases=[('watch','CFBundleIdentifier','foreign'),('watch','WKCompanionAppBundleIdentifier','foreign'),
          ('watch','CFBundleExecutable','Celluloid'),('watch','CFBundleVersion','3'),
          ('watch','MinimumOSVersion','26.0'),('watch','UIDeviceFamily',[1]),
          ('watch','DTPlatformName','watchsimulator'),('watch','WKRunsIndependentlyOfCompanionApp',True),
          ('phone','CFBundleIdentifier','foreign'),('phone','CFBundleVersion','3')]
        for role,key,value in cases:
            p=self.a/m.SPECS[role]['app']/'Info.plist';raw=p.read_bytes()
            with self.subTest(role=role,key=key),self.assertRaises(m.Rejected):self.mutate_info(role,key,value);self.verify()
            p.write_bytes(raw)
    def test_unexpected_code_signature_profile_or_nested_application(self):
        for rel in (m.APP+'/Other.app',m.WATCH+'/Tests.xctest',m.APP+'/Code.framework',
                    m.WATCH+'/_CodeSignature',m.APP+'/PlugIns/Other.appex'):
            p=self.a/rel;p.mkdir(parents=True)
            with self.subTest(rel=rel),self.assertRaises(m.Rejected):self.verify()
            shutil.rmtree(p)
        p=self.a/m.WATCH/'embedded.mobileprovision';p.write_bytes(b'profile')
        with self.assertRaises(m.Rejected):self.verify()
    def test_unknown_macho_and_executable_resource_are_rejected(self):
        p=self.a/m.APP/'extra';p.write_bytes(thin(0x100000c))
        with self.assertRaises(m.Rejected):self.verify()
        p.write_bytes(b'not binary');p.chmod(0o755)
        with self.assertRaises(m.Rejected):self.verify()
    def test_private_key_like_payload_stops_inventory(self):
        p=self.a/m.APP/'private-data';p.write_bytes(b'-----BEGIN PRIVATE KEY-----')
        with self.assertRaises(m.Rejected):self.verify()
    def test_unexpected_watch_slice_and_signed_slice_rejected(self):
        p=self.a/m.SPECS['watch']['binary'];p.write_bytes(thin(0x100000c,minimum=(26,0,0)))
        with self.assertRaises(m.Rejected):self.verify()
        p.write_bytes(fat([(cpu,thin(cpu,minimum=minimum,signature=True)) for cpu,(_,minimum) in m.SPECS['watch']['arches'].items()]))
        with self.assertRaises(m.Rejected):self.verify()
    def test_wrong_platform_in_device_binary_is_not_simulator_acceptance(self):
        p=self.a/m.SPECS['phone']['binary'];p.write_bytes(thin(0x100000c,platform=7,minimum=(15,0,0)))
        with self.assertRaises(m.Rejected):self.verify()
    def test_fake_or_mismatched_dsym_is_rejected_before_native_text(self):
        p=self.a/m.SPECS['phone']['dwarf'];p.write_bytes(thin(0x100000c,kind=2,platform=2,minimum=(15,0,0)))
        with self.assertRaises(m.Rejected):self.verify()
        p.write_bytes(thin(0x100000c,kind=10,platform=2,minimum=(15,0,0),identity='AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE'))
        with self.assertRaises(m.Rejected):self.verify()
    def test_native_uuid_readback_cannot_be_missing_duplicate_or_wrong(self):
        key=(str(self.a/m.SPECS['phone']['binary']),'arm64');expected={key:UUIDS[0x100000c]}
        valid=f'UUID: {UUIDS[0x100000c]} (arm64) {key[0]}\n'.encode()
        for raw in (b'',valid+valid,valid.replace(b'11111111',b'99999999'),valid.replace(b'(arm64)',b'(arm64_32)')):
            with self.subTest(raw=raw[:40]),self.assertRaises(m.Rejected):m.matching_uuids(raw,expected)
    def test_privacy_localization_notices_and_original_resources_are_exact(self):
        for rel in (m.APP+'/SnapKit_SnapKit.bundle/PrivacyInfo.xcprivacy',m.WATCH+'/LICENSE.txt',
                    m.WATCH+'/zh-Hans.lproj/Localizable.strings',m.APP+'/collage.json'):
            p=self.a/rel;raw=p.read_bytes();p.write_bytes(plistlib.dumps({}) if p.suffix in ('.xcprivacy','.strings') else b'')
            with self.subTest(rel=rel),self.assertRaises(m.Rejected):self.verify()
            p.write_bytes(raw)
    def test_native_icon_catalog_must_have_real_dimensions(self):
        for raw in (b'[]',b'[{"Name":"Other","PixelWidth":1024,"PixelHeight":1024}]',b'[{"Name":"AppIcon","PixelWidth":0,"PixelHeight":1024}]'):
            with self.assertRaises(m.Rejected):m.compiled_assets(raw)
    def test_diagnostic_release_marker_rejected(self):
        p=self.a/m.SPECS['phone']['binary'];p.write_bytes(p.read_bytes()+b'CELLULOID_PHONE_LAYOUT_FIXTURE')
        with self.assertRaises(m.Rejected):self.verify()
    def test_receiver_must_be_in_real_parent(self):
        p=self.a/m.SPECS['phone']['binary'];p.write_bytes(p.read_bytes().replace(b'PhoneCompanionController',b'OtherService'))
        with self.assertRaises(m.Rejected):self.verify()
    def test_archive_change_during_native_observation_stops_proof(self):
        original=self.invoke
        def changed(argv,**kwargs):
            raw=original(argv,**kwargs)
            if argv[:3]==['xcrun','dwarfdump','--uuid']:(self.a/m.APP/'late.resource').write_bytes(b'late')
            return raw
        with self.assertRaises(m.Rejected):m.verify_archive(self.a,changed,1000,root=self.root,clock=self.clock)
    def test_watch_producer_escape_and_resource_mismatch_rejected(self):
        p=self.producer/'LICENSE.txt';p.write_bytes(b'changed')
        with self.assertRaises(m.Rejected):self.verify()
    def test_only_witnessed_strip_can_explain_executable_copy(self):
        p=self.producer/'CelluloidWatch';p.write_bytes(p.read_bytes()+b'producer-symbol-table')
        result=self.verify();self.assertEqual(result['watch_copy']['transform'],'strip -D -S -no_atom_info')
    def test_wrong_strip_output_rejected(self):
        p=self.producer/'CelluloidWatch';p.write_bytes(p.read_bytes()+b'changed')
        original=self.invoke
        def wrong(argv,**kwargs):
            if argv[:2]==['xcrun','strip']:Path(argv[-1]).write_bytes(b'wrong');return b''
            return original(argv,**kwargs)
        with self.assertRaises(m.Rejected):m.verify_archive(self.a,wrong,1000,root=self.root,clock=self.clock)
    def test_inventory_bounds_do_not_turn_partial_into_complete(self):
        with patch.object(m,'MAX_ENTRIES',2),self.assertRaises(m.Rejected):self.verify()
        self.assertFalse(self.report['archive_inventory']['complete'])
    def test_archive_root_symlink_cannot_substitute_for_owned_product(self):
        target=self.a.with_name('foreign');self.a.rename(target);self.a.symlink_to(target,target_is_directory=True)
        with self.assertRaises(m.Rejected):self.verify()

    def test_existing_framework_extension_and_watch_inventory_cannot_be_omitted(self):
        for role in ('kit','extension','snapkit','watch'):
            directory=self.a/m.SPECS[role]['app'];renamed=directory.with_name(directory.name+'.held');directory.rename(renamed)
            with self.subTest(role=role),self.assertRaises(m.Rejected):self.verify()
            renamed.rename(directory)
    def test_each_product_has_its_own_matching_symbol_file(self):
        for role,spec in m.SPECS.items():
            p=self.a/spec['dwarf'];original=p.read_bytes();p.write_bytes(b'not symbols')
            with self.subTest(role=role),self.assertRaises(m.Rejected):self.verify()
            p.write_bytes(original)
    def test_framework_runtime_edges_and_install_ids_are_exact(self):
        spec=m.SPECS['kit'];p=self.a/spec['binary'];original=p.read_bytes()
        for links,install in [([],m.INSTALL_NAMES[m.KIT]),(['@rpath/Foreign.framework/Foreign'],m.INSTALL_NAMES[m.KIT]),([m.INSTALL_NAMES[m.SNAPKIT]],'@rpath/Foreign.framework/Foreign')]:
            p.write_bytes(thin(0x100000c,kind=6,platform=2,minimum=(15,0,0),links=links,install=install))
            with self.assertRaises(m.Rejected):self.verify()
        p.write_bytes(original)
    def test_foreign_swift_package_resource_or_executable_metadata_rejected(self):
        for bundle in m.RESOURCE_BUNDLES:
            p=self.a/bundle/'Info.plist';original=p.read_bytes();p.write_bytes(plistlib.dumps({'CFBundlePackageType':'BNDL','CFBundleExecutable':'hidden'}))
            with self.subTest(bundle=bundle),self.assertRaises(m.Rejected):self.verify()
            p.write_bytes(original)
        bundle=next(iter(m.PACKAGE_RESOURCES));p=self.a/bundle/'extra.txt';p.write_text('unreviewed')
        with self.assertRaises(m.Rejected):self.verify()
    def test_missing_or_changed_local_package_resource_is_rejected(self):
        for bundle,rows in m.PACKAGE_RESOURCES.items():
            relative=next(iter(rows));p=self.a/bundle/relative;original=p.read_bytes();p.write_bytes(b'"wrong" = "value";' if relative.endswith('.strings') else b'changed')
            with self.subTest(bundle=bundle),self.assertRaises(m.Rejected):self.verify()
            p.write_bytes(original)
    def test_watch_independence_key_cannot_be_added_even_as_false(self):
        self.mutate_info('watch','WKRunsIndependentlyOfCompanionApp',False)
        with self.assertRaises(m.Rejected):self.verify()
    def test_safe_relative_symlink_and_foreign_watch_producer_are_rejected(self):
        p=self.a/m.APP/'safe-looking';p.symlink_to('Info.plist')
        with self.assertRaises(m.Rejected):self.verify()
        p.unlink();foreign=self.root/'foreign-watch.app';self.producer.rename(foreign);self.producer.symlink_to(foreign,target_is_directory=True)
        with self.assertRaises(m.Rejected):self.verify()
    def test_unreviewed_privacy_location_or_signing_team_rejected(self):
        p=self.a/m.WATCH/'PrivacyInfo.xcprivacy';p.write_bytes(plistlib.dumps(m.PRIVACY))
        with self.assertRaises(m.Rejected):self.verify()
        p.unlink();p=self.a/'Info.plist';value=plistlib.loads(p.read_bytes());value['ApplicationProperties']['Team']='unexpected';p.write_bytes(plistlib.dumps(value))
        with self.assertRaises(m.Rejected):self.verify()


class MachTests(unittest.TestCase):
    def test_arm64_32_uses_explicit_cpu_and_both_supported_header_layouts(self):
        for wide in (True,False):
            rows=m.mach_slices(thin(0x200000c,wide=wide));self.assertEqual(rows[0]['cpu'],0x200000c)
    def test_overlapping_or_duplicate_fat_slices_fail(self):
        p=thin(0x100000c,minimum=(26,0,0))
        with self.assertRaises(m.Rejected):m.mach_slices(fat([(0x100000c,p),(0x100000c,p)]))
        raw=bytearray(fat([(0x100000c,p),(0x200000c,thin(0x200000c))]));raw[36:40]=raw[16:20]
        with self.assertRaisesRegex(m.Rejected,'fat-slice-overlap'):m.mach_slices(bytes(raw))
    def test_unsupported_cpu_short_uuid_and_non_macho_fail(self):
        for raw in (b'not a MachO'*5,thin(0x100000c)[:40],thin(0x100000c).replace(struct.pack('<I',0x100000c),struct.pack('<I',7),1)):
            with self.assertRaises(m.Rejected):m.mach_slices(raw)


class CaptureAndClockTests(unittest.TestCase):
    def test_full_capture_scans_middle_error_before_512k_retention(self):
        for stream in ('stdout','stderr'):
            raw=b'a'*(1024*1024)+b'\nfatal error: actual middle failure\n'+b'z'*(1024*1024);r={}
            m.retain_archive_output(r,raw if stream=='stdout' else b'',raw if stream=='stderr' else b'',capture_complete=True)
            self.assertTrue(r['archive_log']['error_marker_found']);self.assertTrue(r['archive_log']['error_scan_complete'])
            self.assertEqual(r['archive_log']['full_total_bytes'],len(raw));self.assertLessEqual(r['archive_log']['retained_utf8_bytes'],512*1024)
            self.assertNotIn('actual middle failure',r[stream]);self.assertEqual(r['archive_log']['streams'][stream]['full_sha256'],hashlib.sha256(raw).hexdigest())
    def test_stopped_capture_never_claims_full_log(self):
        r={};m.retain_archive_output(r,b'partial',b'error:',capture_complete=False)
        self.assertIsNone(r['archive_log']['full_sha256']);self.assertFalse(r['archive_log']['error_scan_complete'])
    def test_real_bounded_python_producer_and_overflow_cleanup(self):
        r=m.capture([sys.executable,'-c','import sys;sys.stdout.write("a"*200000)'],seconds=5,cap=300000)
        self.assertEqual(len(r.stdout),200000)
        with self.assertRaises(m.CaptureStopped) as c:m.capture([sys.executable,'-c','print("a"*300000)'],seconds=5,cap=1024)
        self.assertTrue(c.exception.cleanup_confirmed);self.assertLessEqual(len(c.exception.stdout_prefix)+len(c.exception.stderr_capture),1024)
    def test_command_late_and_failed_results_remain_failures(self):
        for code,advance in ((1,0),(0,20)):
            c=Clock();receipts=[]
            def run(argv,**kwargs):c.value+=advance;return subprocess.CompletedProcess(argv,code,b'out',b'')
            with self.assertRaises(m.Rejected):m.command(['fixture'],deadline=120,seconds=10,cap=100,receipts=receipts,clock=c,runner=run)
            self.assertFalse(receipts[0]['complete'])
    def test_exact_archive_only_receives_large_capture(self):
        with self.assertRaises(m.Rejected):m.command(['other'],deadline=120,seconds=10,cap=m.ARCHIVE_RAW_CAP,receipts=[],clock=Clock(),archive_output=True)
    def test_source_event_attempt_branch_and_credentialed_command_are_closed(self):
        e={'GITHUB_REPOSITORY':'100mango/Celluloid','GITHUB_REF':m.BRANCH,'GITHUB_WORKFLOW_REF':'100mango/Celluloid/'+m.WORKFLOW+'@'+m.BRANCH,
           'GITHUB_RUN_ATTEMPT':'1','GITHUB_JOB':'archive','DEVELOPER_DIR':'/Applications/Xcode_27.app/Contents/Developer','GITHUB_EVENT_NAME':'push',
           'GITHUB_SHA':'a'*40,'GITHUB_WORKFLOW_SHA':'a'*40,'GITHUB_RUN_ID':'1'}
        m.environment(e)
        for key,value in [('GITHUB_RUN_ATTEMPT','2'),('GITHUB_EVENT_NAME','workflow_dispatch'),('GITHUB_REF','refs/heads/main')]:
            with self.assertRaises(m.Rejected):m.environment({**e,key:value})
        self.assertFalse(any('Simulator' in x or 'simctl' in x or 'allowProvisioning' in x or x.startswith('ARCHS=') for x in m.ARCHIVE_COMMAND))
        self.assertIn('CODE_SIGNING_ALLOWED=NO',m.ARCHIVE_COMMAND);self.assertNotIn('-quiet',m.ARCHIVE_COMMAND)
    def test_original_clock_upload_reservation_rejects_late_and_wrong_outcome(self):
        r={'qualified':True,'clock':{'started_monotonic':100,'phase_end_seconds':m.PHASE_END}};c=Clock(200)
        r['upload_observation']=m.admit_upload(r,clock=c);c.value=220
        self.assertTrue(m.finish_upload(r,'success',clock=c)['upload_qualified'])
        self.assertFalse(m.finish_upload(r,'failure',clock=c)['upload_qualified'])
        c.value=1200
        with self.assertRaises(m.Rejected):m.admit_upload(r,clock=c)
    def test_native_plan_and_driver_commands_match_exactly(self):
        value=json.loads((ROOT/'Documentation/IOS_WATCH_UNSIGNED_ARCHIVE_PLAN.json').read_text());self.assertEqual(value['archive_command'],m.ARCHIVE_COMMAND)
        self.assertFalse(value['signing_authorized']);self.assertFalse(value['upload_authorized'])
    def test_original_files_unchanged_and_only_two_projected_swift_inputs(self):
        self.assertEqual(m.MODIFIED_PATHS,())
        self.assertEqual(sorted(p for p in m.NEW_PATHS if p.endswith(('.m','.swift','.h'))),['Platforms/IOSWatchIntegration/AppDelegate.swift','Platforms/IOSWatchIntegration/EntranceViewController.swift'])


class ExecuteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.clock=Clock();self.calls=[]
        self.identity={'GITHUB_SHA':'a'*40,'base':m.BASE};self.mode='pass'
    def tearDown(self):self.tmp.cleanup()
    def run(self, result=None):
        # Keep unittest.TestCase.run, rather than naming the command double run.
        return super().run(result)
    def runner(self,argv,**kw):
        self.calls.append(argv);self.clock.value+=0.01
        if argv==['xcodebuild','-version']:out=b'Xcode 27.0\nBuild version 27A266a\n'
        elif argv==['xcodebuild','-showsdks']:out=b'iphoneos27.0 watchos27.0'
        elif argv==m.ARCHIVE_COMMAND:
            if self.mode=='timeout':
                error=m.CaptureStopped('duration-limit',False);error.stdout_prefix=b'archiver started';error.stderr_capture=b'';raise error
            if self.mode=='error-zero':out=b'error: actual compiler error\n'
            elif self.mode=='nonzero':return subprocess.CompletedProcess(argv,65,b'actual failure',b'')
            else:fixture(self.root);out=b'** ARCHIVE SUCCEEDED **\n'
        elif argv[:3]==['xcrun','assetutil','--info']:out=b'[{"Name":"AppIcon","PixelWidth":1024,"PixelHeight":1024}]'
        elif argv[:3]==['xcrun','dwarfdump','--uuid']:
            out=''.join(f'UUID: {v["uuid"]} ({m.SPECS["watch"]["arches"][v["cpu"]][0]}) {p}\n' for p in argv[3:] for v in m.mach_slices(Path(p).read_bytes())).encode()
        else:out=b''
        return subprocess.CompletedProcess(argv,0,out,b'')
    def execute(self):
        with patch.object(m,'source_identity',return_value=self.identity),patch.object(m,'icon_inputs',return_value={'fixture':'icon'}),patch.object(m,'materialize_watch_icon'),patch.object(m,'snapkit_source',return_value={'revision':m.SNAPKIT_REVISION}):
            return m.execute(root=self.root,env={},clock=self.clock,runner=self.runner)
    def test_full_command_double_runs_exactly_one_archive_and_no_simulator(self):
        result=self.execute();self.assertTrue(result['qualified']);self.assertFalse(result['store_qualified'])
        self.assertEqual(self.calls.count(m.ARCHIVE_COMMAND),1);self.assertFalse(any('simctl' in c for c in self.calls))
        self.assertFalse(result['distribution_version_ready']);self.assertEqual(result['source_before'],result['source_after'])
    def test_failed_zero_error_and_uncertain_capture_never_reach_product_proof(self):
        for mode in ('nonzero','error-zero','timeout'):
            with tempfile.TemporaryDirectory() as name:
                self.root=Path(name).resolve();self.mode=mode;self.calls=[];result=self.execute()
                self.assertFalse(result['qualified']);self.assertEqual(result['failure']['phase'],'archive')
                self.assertEqual(self.calls.count(m.ARCHIVE_COMMAND),1)
                self.assertFalse(any(c[:3]==['xcrun','assetutil','--info'] for c in self.calls))
                if mode=='timeout':self.assertFalse(result['commands'][-1]['owned_cleanup_confirmed'])
    def test_old_output_is_not_reused_or_removed(self):
        (self.root/'build').mkdir();(self.root/'build/keep').write_text('keep');result=self.execute()
        self.assertFalse(result['qualified']);self.assertEqual(self.calls,[]);self.assertEqual((self.root/'build/keep').read_text(),'keep')
    def test_source_failure_stops_before_xcode(self):
        with patch.object(m,'source_identity',side_effect=m.Rejected('source-not-clean')):
            result=m.execute(root=self.root,env={},clock=self.clock,runner=self.runner)
        self.assertFalse(result['qualified']);self.assertEqual(self.calls,[])
    def test_same_original_clock_report_and_artifact_are_bounded(self):
        result=self.execute();output=self.root/'build/archive-proof';marker=self.root/'output.txt';marker.write_text('old=true\n')
        decoded=m.retain_report(result,output,marker,clock=self.clock)
        self.assertTrue(decoded['qualified']);self.assertLessEqual((output/'report.json').stat().st_size,m.MAX_REPORT)
        self.assertEqual(marker.read_text(),'old=true\nevidence_ready=true\n')


class InputMaterializationTests(unittest.TestCase):
    def test_only_watch_icon_is_copied_from_hash_pinned_brand(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);source='Celluloid/Assets.xcassets/AppIcon.appiconset/Icon-Marketing.png';dest='Platforms/watchOS/Assets.xcassets/AppIcon.appiconset/Generated-1024.png'
            (root/source).parent.mkdir(parents=True);(root/source).write_bytes((ROOT/source).read_bytes());(root/dest).parent.mkdir(parents=True)
            m.materialize_watch_icon(root);self.assertEqual((root/source).read_bytes(),(root/dest).read_bytes())
            self.assertEqual(len([x for x in root.rglob('*') if x.is_file()]),2)
            with self.assertRaises(m.Rejected):m.materialize_watch_icon(root)
    def test_existing_icon_symlink_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);source='Celluloid/Assets.xcassets/AppIcon.appiconset/Icon-Marketing.png';dest='Platforms/watchOS/Assets.xcassets/AppIcon.appiconset/Generated-1024.png'
            (root/source).parent.mkdir(parents=True);(root/source).write_bytes((ROOT/source).read_bytes());(root/dest).parent.mkdir(parents=True);(root/dest).symlink_to(root/source)
            with self.assertRaises(m.Rejected):m.materialize_watch_icon(root)
    def test_pinned_remote_checkout_revision_and_cleanliness_are_closed(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);checkout=root/'build/SourcePackages/checkouts/SnapKit';checkout.mkdir(parents=True)
            def good(argv,**kwargs):return (m.SNAPKIT_REVISION+'\n').encode() if argv[-2:]==['rev-parse','HEAD'] else b''
            self.assertEqual(m.snapkit_source(root,good)['revision'],m.SNAPKIT_REVISION)
            def wrong(argv,**kwargs):return b'wrong\n'
            with self.assertRaises(m.Rejected):m.snapkit_source(root,wrong)
            (checkout.parent/'Unknown').mkdir()
            with self.assertRaises(m.Rejected):m.snapkit_source(root,good)


if __name__=='__main__':unittest.main()
