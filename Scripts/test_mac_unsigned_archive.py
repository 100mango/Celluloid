"""Portable Mac archive structure/failure/clock contracts; no native launch."""
import ast,datetime,hashlib,json,os
from pathlib import Path
import plistlib,struct,subprocess,sys,tempfile,unittest,shutil
from unittest.mock import patch
import mac_unsigned_archive as m
ROOT=Path(__file__).resolve().parents[1]
CPUS=(0x100000c,0x1000007)
UUIDS={'arm64':'11111111-2222-3333-4444-555555555555','x86_64':'66666666-7777-8888-9999-AAAAAAAAAAAA'}
def thin(cpu,kind=2,platform=1,minimum=0x0d0000,sdk=0x1b0000):
 cmd=struct.pack('<6I',0x32,24,platform,minimum,sdk,0)
 return struct.pack('<8I',0xfeedfacf,cpu,0,kind,1,len(cmd),0,0)+cmd

def fat(kind=2,payloads=None):
 payloads=[thin(cpu,kind) for cpu in CPUS] if payloads is None else payloads;offset=8+20*2;table=[]
 for cpu,raw in zip(CPUS,payloads):table.append(struct.pack('>5I',cpu,0,offset,len(raw),0));offset+=len(raw)
 return struct.pack('>2I',0xcafebabe,2)+b''.join(table)+b''.join(payloads)
class Clock:
 def __init__(self,value=100):self.value=value
 def __call__(self):return self.value
 def advance(self,n):self.value+=n

def fixture(root):
 a=root/m.ARCHIVE
 meta={'ArchiveVersion':2,'SchemeName':'CelluloidMac','CreationDate':datetime.datetime(2026,10,7),'ApplicationProperties':{'ApplicationPath':'Applications/CelluloidMac.app','CFBundleIdentifier':'Mango.Celluloid','CFBundleShortVersionString':'1.1','CFBundleVersion':'2'}}
 for bundle,exe,dsym,dwarf,name,identifier,kind,platform in m.PRODUCTS:
  for p in [a/bundle/'Contents/MacOS',a/bundle/'Contents/Resources',(a/dwarf).parent]:p.mkdir(parents=True,exist_ok=True)
  source_info=ROOT/('Platforms/'+platform+'/Info.plist');p=root/source_info.relative_to(ROOT);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(source_info.read_bytes());info=plistlib.loads(p.read_bytes())
  info.update(CFBundleIdentifier=identifier,CFBundleExecutable=name,CFBundleName='Celluloid',CFBundlePackageType=kind,CFBundleShortVersionString='1.1',CFBundleVersion='2',LSMinimumSystemVersion='13.0',DTPlatformName='macosx',DTSDKName='macosx27.0')
  if bundle==m.EXT:info['NSExtension']['NSExtensionPrincipalClass']='CelluloidMacPhotosExtension.MacPhotoEditingController'
  else:info['CFBundleIconFile']='AppIcon'
  (a/bundle/'Contents/Info.plist').write_bytes(plistlib.dumps(info));(a/exe).write_bytes(fat());(a/dwarf).write_bytes(fat(10))
  (a/dsym/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'com.apple.xcode.dsym.'+identifier,'CFBundlePackageType':'dSYM','CFBundleVersion':'1.0'}))
  for rel in [f'Platforms/{platform}/{name}.entitlements','LICENSE.txt','Platforms/Resources/PrivacyPolicy.txt',*[f'Platforms/Resources/{lang}.lproj/Localizable.strings' for lang in ('en','zh-Hans')]]:
   source=ROOT/rel;p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(source.read_bytes())
   if rel.endswith('.entitlements'):continue
   dest=a/bundle/'Contents/Resources'/('/'.join(rel.split('/')[-2:]) if rel.endswith('.strings') else source.name);dest.parent.mkdir(parents=True,exist_ok=True)
   dest.write_bytes(plistlib.dumps(m.package.strings_dictionary(source.read_bytes()),fmt=plistlib.FMT_BINARY) if source.suffix=='.strings' else source.read_bytes())
 (a/'Info.plist').write_bytes(plistlib.dumps(meta))
 for package_name,target in [('CelluloidCore','CelluloidDomain'),('CelluloidRendering','CelluloidRendering')]:
  sources=ROOT/'Packages'/package_name/'Sources'/target/'Resources'
  for product in (m.APP,m.EXT):
   bundle=a/product/'Contents/Resources'/(package_name+'_'+target+'.bundle')
   for source in sources.rglob('*'):
    if source.is_file():
     for p in [root/source.relative_to(ROOT),bundle/source.relative_to(sources)]:p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(source.read_bytes())
 for p in [ROOT/'Platforms/macOS/icon-provenance.json',ROOT/'Celluloid/Assets.xcassets/AppIcon.appiconset/Icon-Marketing.png',*(ROOT/'Platforms/macOS/Assets.xcassets/AppIcon.appiconset').glob('*')]:
  target=root/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p.read_bytes())
 for name in ['Assets.car','AppIcon.icns','AppIcon512x512@2x.png']:(a/m.APP/'Contents/Resources'/name).write_bytes(b'ordinary generated icon')
 return a

def uuid_output(a,executable=m.EXECUTABLE,dwarf=m.DWARF):
 return ''.join(f'UUID: {UUIDS[arch]} ({arch}) {a/path}\n' for path in [executable,dwarf] for arch in ['arm64','x86_64']).encode()

def native_output(argv,a):
 for _,exe,_,dwarf,*_ in m.PRODUCTS:
  if argv==['xcrun','nm','-u',str(a/exe)]:return b' U _swift_retain\n'
  if argv==['xcrun','dwarfdump','--uuid',str(a/exe),str(a/dwarf)]:return uuid_output(a,exe,dwarf)
 if argv==['xcrun','assetutil','--info',str(a/m.APP/'Contents/Resources/Assets.car')]:
  slots=json.loads((ROOT/'Platforms/macOS/Assets.xcassets/AppIcon.appiconset/Contents.json').read_bytes())['images']
  return json.dumps([{'Name':'AppIcon','AssetType':'Icon Image','PixelWidth':int(float(r['size'].split('x')[0]))*int(r['scale'][0]),'PixelHeight':int(float(r['size'].split('x')[0]))*int(r['scale'][0]),'Scale':int(r['scale'][0])} for r in slots]).encode()
 raise AssertionError('Unmocked native boundary: '+repr(argv))

class PortableTestCase(unittest.TestCase):
 def setUp(self):
  guard=patch.object(subprocess,'Popen',side_effect=AssertionError('Portable archive tests must not spawn a process'))
  guard.start();self.addCleanup(guard.stop)

class ArchiveTests(PortableTestCase):
 def setUp(self):super().setUp();self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.a=fixture(self.root);self.clock=Clock();self.report={};self.calls=[]
 def tearDown(self):self.temp.cleanup()
 def invoke(self,argv,**kwargs):self.calls.append(argv);return native_output(argv,self.a)
 def verify(self):return m.verify_archive(self.a,self.invoke,1000,root=self.root,clock=self.clock,report=self.report)
 def change_info(self,key,field,value):
  p=self.a/key;v=plistlib.loads(p.read_bytes());v[field]=value;p.write_bytes(plistlib.dumps(v))
 def test_full_app_and_extension_archive(self):
  r=self.verify();self.assertEqual(set(r['products']),{m.APP,m.EXT});self.assertEqual(len(self.calls),5);self.assertEqual(len(self.report['archive_metadata_diagnostics']),5)
  for p in r['products'].values():
   self.assertFalse(p['effective_sandbox_qualified']);self.assertEqual(set(p['uuids']),{'arm64','x86_64'});self.assertEqual(p['dSYM_version_observations']['CFBundleVersion']['comparison'],'different')
  self.assertEqual(set(r['package_resources']),{product+'/Contents/Resources/'+package for product in (m.APP,m.EXT) for package in ('CelluloidCore_CelluloidDomain.bundle','CelluloidRendering_CelluloidRendering.bundle')})
  for key,value in r['package_resources'].items():self.assertTrue(key.startswith(value['owner_product']+'/Contents/Resources/'));self.assertGreater(value['verified_resources'],0)
  self.assertFalse(r['privacy']['source_declares_mac_manifest']);self.assertTrue(r['privacy']['privacy_policy_exact']);self.assertEqual(r['privacy']['manifest_paths'],[])
 def test_ordinary_generated_resources_are_not_rejected_by_name(self):
  (self.a/m.APP/'Contents/Resources/new.icon.png').write_bytes(b'ordinary');self.verify()
 def test_absent_extension_is_not_qualified(self):
  (self.a/m.EXT_EXECUTABLE).unlink()
  with self.assertRaisesRegex(m.Rejected,'required-or-unexpected-binary'):self.verify()
 def test_extension_floor_checked_independently(self):
  (self.a/m.EXT_EXECUTABLE).write_bytes(fat(payloads=[thin(CPUS[0]),thin(CPUS[1],minimum=0x0e0000)]))
  with self.assertRaisesRegex(m.Rejected,'binary-platform-version-mismatch'):self.verify()
 def test_extension_must_be_universal(self):
  (self.a/m.EXT_EXECUTABLE).write_bytes(thin(CPUS[0]))
  with self.assertRaisesRegex(m.Rejected,'binary-product-or-architecture-mismatch'):self.verify()
 def test_app_must_be_universal(self):
  (self.a/m.EXECUTABLE).write_bytes(thin(CPUS[0]))
  with self.assertRaises(m.Rejected):self.verify()
 def test_extension_identity_and_host_contract(self):
  self.change_info(m.EXT+'/Contents/Info.plist','NSExtension',{})
  with self.assertRaisesRegex(m.Rejected,'photos-extension-contract-mismatch'):self.verify()
 def test_extension_build_matches(self):
  self.change_info(m.EXT+'/Contents/Info.plist','CFBundleVersion','99')
  with self.assertRaisesRegex(m.Rejected,'application-identity-mismatch'):self.verify()
 def test_permission_purpose_cannot_appear_silently(self):
  self.change_info(m.APP+'/Contents/Info.plist','NSCameraUsageDescription','Unexpected')
  with self.assertRaisesRegex(m.Rejected,'permission-purpose-source-mismatch'):self.verify()
 def test_each_product_localization_is_source_equal(self):
  for bundle in [m.APP,m.EXT]:
   for lang in ['en','zh-Hans']:
    with self.subTest(bundle=bundle,lang=lang):
     p=self.a/bundle/'Contents/Resources'/f'{lang}.lproj/Localizable.strings';old=p.read_bytes();p.write_bytes(plistlib.dumps({'x':'bad'}))
     with self.assertRaisesRegex(m.Rejected,'localized-resource-source-mismatch'):self.verify()
     p.write_bytes(old)
 def test_privacy_text_and_license_source_equal(self):
  for bundle in [m.APP,m.EXT]:
   for name in ['PrivacyPolicy.txt','LICENSE.txt']:
    with self.subTest(bundle=bundle,name=name):
     p=self.a/bundle/'Contents/Resources'/name;old=p.read_bytes();p.write_bytes(b'bad')
     with self.assertRaisesRegex(m.Rejected,'notice-resource-source-mismatch'):self.verify()
     p.write_bytes(old)
 def test_no_debug_markers_in_either_product(self):
  for exe in [m.EXECUTABLE,m.EXT_EXECUTABLE]:
   for marker in m.DEBUG_MARKERS:
    p=self.a/exe;old=p.read_bytes();p.write_bytes(old+marker)
    with self.assertRaisesRegex(m.Rejected,'debug-test-seam-present'):self.verify()
    p.write_bytes(old)
 def test_test_nested_products_rejected(self):
  p=self.a/m.APP/'Contents/PlugIns/Other.appex';p.mkdir()
  with self.assertRaisesRegex(m.Rejected,'unexpected-nested-product'):self.verify()
 def test_provisioning_rejected(self):
  (self.a/m.APP/'Contents/embedded.provisionprofile').write_bytes(b'bad')
  with self.assertRaisesRegex(m.Rejected,'unexpected-test-or-provisioning'):self.verify()
 def test_escaping_symlink_rejected_with_inventory(self):
  p=self.a/m.APP/'Contents/Resources/escape';p.symlink_to('/etc/passwd')
  with self.assertRaises(m.Rejected):self.verify()
  self.assertFalse(self.report['archive_inventory']['complete'])
 def test_internal_resource_symlink_catalogued(self):
  p=self.a/m.APP/'Contents/Resources/icon-alias';p.symlink_to('AppIcon.icns');self.verify()
 def test_entry_cap(self):
  with patch.object(m,'MAX_ENTRIES',2),self.assertRaises(m.Rejected):self.verify()
 def test_byte_cap(self):
  with patch.object(m,'MAX_BYTES',1),self.assertRaises(m.Rejected):self.verify()
 def test_inventory_cap(self):
  with patch.object(m,'MAX_INVENTORY',64),self.assertRaises(m.Rejected):self.verify()
 def test_bad_plist_keeps_all_five_observations(self):
  (self.a/'Info.plist').write_bytes(b'bad')
  with self.assertRaises(plistlib.InvalidFileException):self.verify()
  self.assertEqual(len(self.report['archive_metadata_diagnostics']),5);self.assertEqual(self.calls,[])
 def test_package_resource_mutation_rejected(self):
  p=self.a/m.APP/'Contents/Resources/CelluloidRendering_CelluloidRendering.bundle/bubble.json';p.write_bytes(b'wrong')
  with self.assertRaisesRegex(m.Rejected,'package-resource-source-mismatch'):self.verify()
 def assert_package_missing(self,key):
  with self.assertRaisesRegex(m.Rejected,'package-resource-bundle-missing'):self.verify()
  self.assertEqual(self.report['offending_path'],key)
 def test_missing_app_package_copy_rejected(self):
  for package in ('CelluloidCore_CelluloidDomain.bundle','CelluloidRendering_CelluloidRendering.bundle'):
   with self.subTest(package=package):
    key=m.APP+'/Contents/Resources/'+package;p=self.a/key;hold=self.root/'held';p.rename(hold)
    self.assert_package_missing(key);hold.rename(p)
 def test_missing_extension_package_copy_rejected(self):
  for package in ('CelluloidCore_CelluloidDomain.bundle','CelluloidRendering_CelluloidRendering.bundle'):
   with self.subTest(package=package):
    key=m.EXT+'/Contents/Resources/'+package;p=self.a/key;hold=self.root/'held';p.rename(hold)
    self.assert_package_missing(key);hold.rename(p)
 def test_all_package_copies_only_in_dsyms_rejected(self):
  for index,product in enumerate((m.APP,m.EXT)):
   destination=self.a/'dSYMs'/('misplaced-'+str(index));destination.mkdir()
   for package in ('CelluloidCore_CelluloidDomain.bundle','CelluloidRendering_CelluloidRendering.bundle'):
    (self.a/product/'Contents/Resources'/package).rename(destination/package)
  self.assert_package_missing(m.APP+'/Contents/Resources/CelluloidCore_CelluloidDomain.bundle')
 def test_each_moved_package_copy_cannot_use_other_three(self):
  for product in (m.APP,m.EXT):
   for package in ('CelluloidCore_CelluloidDomain.bundle','CelluloidRendering_CelluloidRendering.bundle'):
    with self.subTest(product=product,package=package):
     key=product+'/Contents/Resources/'+package;p=self.a/key;destination=self.a/'dSYMs'/package;p.rename(destination)
     self.assert_package_missing(key);destination.rename(p)
 def test_each_of_four_package_copies_validates_own_bytes(self):
  for product in (m.APP,m.EXT):
   for package,resource in [('CelluloidCore_CelluloidDomain.bundle','en.lproj/Localizable.strings'),('CelluloidRendering_CelluloidRendering.bundle','bubble.json')]:
    with self.subTest(product=product,package=package):
     key=product+'/Contents/Resources/'+package+'/'+resource;p=self.a/key;original=p.read_bytes()
     p.write_bytes(b'"changed" = "changed";' if resource.endswith('.strings') else b'wrong')
     with self.assertRaisesRegex(m.Rejected,'package-resource-source-mismatch'):self.verify()
     self.assertEqual(self.report['offending_path'],key);p.write_bytes(original)
 def test_catalog_needs_all_icon_slots(self):
  def invoke(argv,**kw):return b'[]' if 'assetutil' in argv else native_output(argv,self.a)
  with self.assertRaisesRegex(m.Rejected,'compiled-icon-renditions-missing'):m.verify_archive(self.a,invoke,1000,root=self.root,clock=self.clock)
 def test_source_icon_byte_mutation_rejected(self):
  p=self.root/'Platforms/macOS/Assets.xcassets/AppIcon.appiconset/icon-16@1x.png';p.write_bytes(b'bad')
  with self.assertRaisesRegex(m.Rejected,'icon-byte-identity-mismatch'):self.verify()
 def test_dsym_content_not_trusted_from_uuid_text(self):
  (self.a/m.EXT_DWARF).write_bytes(fat(2))
  with self.assertRaises(m.Rejected):self.verify()
 def test_uuid_mismatch_rejected(self):
  raw=uuid_output(self.a).replace(UUIDS['arm64'].encode(),b'FFFFFFFF-2222-3333-4444-555555555555',1)
  with self.assertRaises(m.Rejected):m.matching_uuid(raw,self.a/m.EXECUTABLE,self.a/m.DWARF)
 def test_archive_mutation_during_native_query_rejected(self):
  def invoke(argv,**kw):
   raw=native_output(argv,self.a)
   if 'assetutil' in argv:(self.a/m.APP/'Contents/Resources/late').write_bytes(b'late')
   return raw
  with self.assertRaisesRegex(m.Rejected,'archive-changed-during-proof'):m.verify_archive(self.a,invoke,1000,root=self.root,clock=self.clock)
 def test_unsigned_security_observation_is_explicit_absence(self):
  rows=m.mach_security(fat());self.assertEqual(len(rows),2)
  for row in rows:self.assertFalse(row['code_signature_present']);self.assertEqual(row['linked_entitlements'],[])
 def test_bad_security_section_table_rejected(self):
  cmd=struct.pack('<II',0x19,72)+b'\0'*56+struct.pack('<II',99,0)
  raw=struct.pack('<8I',0xfeedfacf,CPUS[0],0,2,2,len(cmd)+24,0,0)+cmd+struct.pack('<6I',0x32,24,1,0x0d0000,0x1b0000,0)
  with self.assertRaisesRegex(m.Rejected,'security-section-table-invalid'):m.mach_security(raw)

class SecurityStructureTests(PortableTestCase):
 def linked(self,value):
  payload=plistlib.dumps(value);offset=32+24+152
  segment=struct.pack('<II16sQQQQiiII',0x19,152,b'__TEXT',0,offset+len(payload),0,offset+len(payload),7,5,1,0)
  section=struct.pack('<16s16sQQIIIIIIII',b'__entitlements',b'__TEXT',0,len(payload),offset,0,0,0,0,0,0,0)
  command=struct.pack('<6I',0x32,24,1,0x0d0000,0x1b0000,0)+segment+section
  return struct.pack('<8I',0xfeedfacf,CPUS[0],0,2,2,len(command),0,0)+command+payload
 def signature(self,slot,magic,payload):
  sub=struct.pack('>II',magic,len(payload)+8)+payload;blob=struct.pack('>III',0xfade0cc0,20+len(sub),1)+struct.pack('>II',slot,20)+sub
  commands=struct.pack('<6I',0x32,24,1,0x0d0000,0x1b0000,0)+struct.pack('<4I',0x1d,16,72,len(blob))
  return struct.pack('<8I',0xfeedfacf,CPUS[0],0,2,2,40,0,0)+commands+blob
 def test_linked_entitlements_observed_as_dictionary(self):
  v={'com.apple.security.app-sandbox':True};r=m.mach_security(self.linked(v))[0];self.assertEqual(r['linked_entitlements'],[v]);self.assertFalse(r['code_signature_present'])
 def test_signature_entitlements_observed_without_signature_claim(self):
  v={'com.apple.security.app-sandbox':True};r=m.mach_security(self.signature(5,0xfade7171,plistlib.dumps(v)))[0];self.assertEqual(r['signature_entitlements'],[v]);self.assertFalse(r['cms_signature_present'])
 def test_nonempty_cms_detected(self):
  self.assertTrue(m.mach_security(self.signature(0x10000,0xfade0b01,b'cms'))[0]['cms_signature_present'])
 def test_der_observation_is_not_silently_xml(self):
  r=m.mach_security(self.signature(7,0xfade7172,b'der'))[0];self.assertTrue(r['der_entitlement_present']);self.assertEqual(r['signature_entitlements'],[])
 def test_wrong_entitlement_magic_rejected(self):
  with self.assertRaisesRegex(m.Rejected,'signature-entitlements-invalid'):m.mach_security(self.signature(5,1,plistlib.dumps({})))
 def test_signature_bounds_rejected(self):
  raw=bytearray(self.signature(5,0xfade7171,plistlib.dumps({})));struct.pack_into('<I',raw,64,999999)
  with self.assertRaisesRegex(m.Rejected,'signature-blob-bounds'):m.mach_security(raw)
 def test_section_bounds_rejected(self):
  raw=bytearray(self.linked({}));struct.pack_into('<I',raw,32+24+72+48,999999)
  with self.assertRaisesRegex(m.Rejected,'security-section-bounds'):m.mach_security(raw)
 def test_array_entitlement_rejected(self):
  with self.assertRaisesRegex(m.Rejected,'security-section-not-dictionary'):m.mach_security(self.linked([]))

class SourceAndClock(PortableTestCase):
 def test_pure_macho_functions_match_reviewed_mature_parser(self):
  f=json.loads((ROOT/'Scripts/fixtures/mac-archive-inputs.json').read_bytes());raw=(ROOT/'Scripts/mac_archive_macho.py').read_text();tree=ast.parse(raw)
  for n in tree.body:
   if isinstance(n,ast.FunctionDef):self.assertEqual(hashlib.sha256(ast.get_source_segment(raw,n).encode()).hexdigest(),f['mature_functions'][n.name])
 def test_product_and_support_input_closure_unchanged(self):
  f=json.loads((ROOT/'Scripts/fixtures/mac-archive-inputs.json').read_bytes());self.assertEqual(len(f['app_inputs']),906)
  for path,h in f['app_inputs'].items():self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),h,path)
  self.assertEqual(hashlib.sha256((ROOT/'Scripts/mac_archive_capture.py').read_bytes()).hexdigest(),f['collector_sha256'])
 def test_fixed_archive_has_no_signing_launch_or_test(self):
  a=m.ARCHIVE_COMMAND;self.assertNotIn('-quiet',a);self.assertEqual(a[-1],'archive');self.assertIn('CODE_SIGNING_ALLOWED=NO',a);self.assertIn('ARCHS=arm64 x86_64',a);self.assertIn('generic/platform=macOS',a)
  self.assertEqual(a[a.index('-project')+1],'CelluloidNative.xcodeproj');self.assertEqual(a[a.index('-scheme')+1],'CelluloidMac')
  for bad in ['test','test-without-building','allowProvisioning','exportArchive','codesign']:self.assertFalse(any(bad==x or bad in x.lstrip('-') for x in a if x.startswith('-')),bad)
 def test_workflow_uploads_only_proof_and_is_push_once(self):
  w=(ROOT/m.WORKFLOW).read_text();self.assertIn('path: build/archive-proof/report.json',w);self.assertIn('timeout-minutes: 20',w);self.assertEqual(w.count('runs-on: xcode-27'),1)
  for bad in ['workflow_dispatch','matrix:','retry','*.xcarchive','*.app']:self.assertNotIn(bad,w)
 def test_command_cleanup_has_separate_reserve(self):
  c=Clock();receipts=[]
  def runner(argv,**kw):self.assertEqual(kw['seconds'],20);c.advance(1);return subprocess.CompletedProcess(argv,0,b'ok',b'')
  self.assertEqual(m.command(['safe'],deadline=124,seconds=30,cap=20,receipts=receipts,clock=c,runner=runner,cleanup=2),b'ok');self.assertEqual(receipts[0]['cleanup_reserve_seconds'],4)
 def test_late_return_never_qualifies(self):
  c=Clock()
  def runner(argv,**kw):c.advance(kw['seconds']+1);return subprocess.CompletedProcess(argv,0,b'',b'')
  with self.assertRaises(m.Rejected):m.command(['safe'],deadline=130,seconds=10,cap=20,receipts=[],clock=c,runner=runner)
 def test_unconfirmed_capture_stops_without_followup(self):
  def runner(*a,**k):raise m.CaptureStopped('uncertain',False)
  rows=[]
  with self.assertRaises(m.Rejected):m.command(['safe'],deadline=130,seconds=10,cap=20,receipts=rows,clock=Clock(),runner=runner)
  self.assertEqual(len(rows),1);self.assertFalse(rows[0]['owned_cleanup_confirmed'])
 def test_report_overflow_preserves_bounded_catalogue_and_identity(self):
  report={'schema':1,'qualified':True,'clock':{'report_ready_deadline':200},'source_before':{'GITHUB_SHA':'a'*40},'archive_inventory':{'complete':True,'paths':{'Assets.car':{'bytes':4}}},'archive_metadata_diagnostics':{'Info.plist':{'read_error':{'type':'InvalidFileException','reason':'Invalid file'}}},'commands':['x'*(m.MAX_REPORT+1)]}
  v=json.loads(m.report_bytes(report));self.assertFalse(v['qualified']);self.assertEqual(v['archive_inventory'],report['archive_inventory']);self.assertEqual(v['source_before'],report['source_before']);self.assertEqual(v['archive_metadata_diagnostics'],report['archive_metadata_diagnostics'])
 def test_uuid_missing_or_duplicate_slice_rejected(self):
  with self.assertRaises(m.Rejected):m.matching_uuid(b'',Path('app'),Path('dwarf'))
 def test_dwarf_overlap_or_wrong_kind_rejected(self):
  raw=bytearray(fat(10));struct.pack_into('>I',raw,8+20+8,48)
  with self.assertRaises(m.Rejected):m.dwarf_headers(bytes(raw))
  with self.assertRaises(m.Rejected):m.dwarf_headers(thin(CPUS[0],2))

class ExecuteAndRetention(PortableTestCase):
 def setUp(self):
  super().setUp()
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.clock=Clock();self.calls=[];self.fail_archive=False
  self.identity={'GITHUB_REPOSITORY':'100mango/Celluloid','GITHUB_REF':m.BRANCH,'GITHUB_WORKFLOW_REF':'100mango/Celluloid/'+m.WORKFLOW+'@'+m.BRANCH,'GITHUB_RUN_ATTEMPT':'1','GITHUB_JOB':'archive','DEVELOPER_DIR':'/Applications/Xcode_27.app/Contents/Developer','GITHUB_EVENT_NAME':'push','GITHUB_SHA':'a'*40,'GITHUB_WORKFLOW_SHA':'a'*40,'GITHUB_RUN_ID':'1'}
 def tearDown(self):self.temp.cleanup()
 def runner(self,argv,**kwargs):
  self.calls.append(argv);raw=b'';code=0
  if argv==['xcodebuild','-version']:raw=b'Xcode 27.0\nBuild version 27A266a\n'
  elif argv==['xcodebuild','-showsdks']:raw=b'macosx27.0\n'
  elif argv==['sw_vers']:raw=b'ProductVersion: 27.0\nBuildVersion: 26A428\n'
  elif argv==m.ARCHIVE_COMMAND:
   if self.fail_archive:code=65;raw=b'Archive failed, bounded compiler details'
   else:fixture(self.root);raw=b'** ARCHIVE SUCCEEDED **\n'
  elif argv[0]=='xcrun':raw=native_output(argv,self.root/m.ARCHIVE)
  elif argv in [[sys.executable,*optimize,'-m','unittest','discover','-s','Scripts','-p','test_mac_unsigned_archive.py'] for optimize in ([],['-O'])]:pass
  else:raise AssertionError('Unmocked pipeline boundary: '+repr(argv))
  self.clock.advance(.1);return subprocess.CompletedProcess(argv,code,raw,b'')
 def execute(self):
  with patch.object(m,'source_identity',return_value=dict(self.identity)), patch.object(m,'verify_icon_inputs',return_value={}):
   return m.execute(env=self.identity,root=self.root,clock=self.clock,runner=self.runner)
 def test_full_fixed_pipeline_qualifies_proof_only(self):
  r=self.execute();self.assertTrue(r['qualified'],r.get('failure'));self.assertFalse(r['binary_handoff']);self.assertFalse(r['signing_qualified']);self.assertFalse(r['store_qualified']);self.assertEqual(self.calls.count(m.ARCHIVE_COMMAND),1)
  output=self.root/'build/archive-proof';marker=self.root/'step-output';marker.write_text('');decoded=m.retain_report(r,output,marker,clock=self.clock)
  self.assertTrue(decoded['qualified']);self.assertTrue(decoded['archive_inventory']['complete']);self.assertEqual(set(x.name for x in output.iterdir()),{'report.json'});self.assertEqual(marker.read_text(),'evidence_ready=true\n')
 def test_archive_failure_keeps_native_diagnostic_and_never_proves_or_retries(self):
  self.fail_archive=True;r=self.execute();self.assertFalse(r['qualified']);self.assertEqual(r['failure']['phase'],'archive');self.assertEqual(self.calls.count(m.ARCHIVE_COMMAND),1);self.assertEqual(self.calls[-1],m.ARCHIVE_COMMAND)
  self.assertIn('bounded compiler details',r['commands'][-1]['stdout']);self.assertNotIn('proof',r);self.assertNotIn('archive_inventory',r)
 def archive_reported_error(self,*,stderr=False,create_archive=True):
  original=self.runner
  def runner(argv,**kwargs):
   if argv!=m.ARCHIVE_COMMAND:return original(argv,**kwargs)
   self.calls.append(argv)
   if create_archive:fixture(self.root)
   self.clock.advance(.1);error=b'error: archive exporter reported a bounded failure\n'
   return subprocess.CompletedProcess(argv,0,b'** ARCHIVE SUCCEEDED **\n'+(b'' if stderr else error),error if stderr else b'')
  with patch.object(self,'runner',side_effect=runner):r=self.execute()
  self.assertFalse(r['qualified']);self.assertEqual(r['failure']['phase'],'archive');self.assertEqual(r['failure']['reason'],'archive-reported-error')
  self.assertEqual(self.calls.count(m.ARCHIVE_COMMAND),1);self.assertEqual(self.calls[-1],m.ARCHIVE_COMMAND)
  self.assertNotIn('proof',r);self.assertNotIn('source_after',r);self.assertTrue(r['commands'][-1]['complete']);self.assertEqual(r['commands'][-1]['returncode'],0)
  self.assertEqual(r['archive_file_observation_scope'],'after-known-zero-exit-with-error; pure files only')
  return r
 def test_zero_exit_stdout_error_keeps_files_without_second_native_call(self):
  r=self.archive_reported_error();self.assertTrue(r['archive_inventory']['complete']);self.assertEqual(len(r['archive_metadata_diagnostics']),5)
  output=self.root/'build/archive-proof';marker=self.root/'step-output';retained=m.retain_report(r,output,marker,clock=self.clock)
  self.assertFalse(retained['qualified']);self.assertTrue(retained['archive_inventory']['complete']);self.assertEqual(len(retained['archive_metadata_diagnostics']),5)
  self.assertEqual(set(x.name for x in output.iterdir()),{'report.json'})
 def test_zero_exit_stderr_error_keeps_files_without_second_native_call(self):
  r=self.archive_reported_error(stderr=True);self.assertTrue(r['archive_inventory']['complete']);self.assertEqual(len(r['archive_metadata_diagnostics']),5)
 def test_zero_exit_error_without_archive_keeps_original_failure(self):
  r=self.archive_reported_error(create_archive=False);self.assertEqual(r['archive_file_observation_error']['type'],'FileNotFoundError');self.assertFalse(r['archive_inventory']['complete'])
 def test_unconfirmed_archive_exit_starts_no_file_or_native_proof(self):
  original=self.runner
  def runner(argv,**kwargs):
   if argv!=m.ARCHIVE_COMMAND:return original(argv,**kwargs)
   self.calls.append(argv);fixture(self.root)
   error=m.CaptureStopped('descendant-exit-unconfirmed',False);error.stdout_prefix=b'error: retained uncertain archive';error.stderr_capture=b'bounded stderr';raise error
  with patch.object(self,'runner',side_effect=runner):r=self.execute()
  self.assertFalse(r['qualified']);self.assertEqual(r['failure']['reason'],'capture-stopped');self.assertEqual(self.calls[-1],m.ARCHIVE_COMMAND)
  self.assertNotIn('proof',r);self.assertNotIn('archive_inventory',r);self.assertNotIn('archive_file_observation_scope',r)
  self.assertFalse(r['commands'][-1]['owned_cleanup_confirmed']);self.assertIn('retained uncertain archive',r['commands'][-1]['stdout'])
 def check_metadata_failure(self,path,key,value,reason):
  original=self.runner
  def mutate(argv,**kwargs):
   result=original(argv,**kwargs)
   if argv==m.ARCHIVE_COMMAND:
    p=self.root/m.ARCHIVE/path;v=plistlib.loads(p.read_bytes());v[key]=value;p.write_bytes(plistlib.dumps(v))
   return result
  with patch.object(self,'runner',side_effect=mutate):r=self.execute()
  self.assertFalse(r['qualified']);self.assertNotIn('proof',r);self.assertEqual(r['failure']['phase'],'proof');self.assertIn(reason,r['failure']['reason']);self.assertEqual(r['failure']['offending_path'],path)
  self.assertTrue(r['archive_inventory']['complete']);self.assertEqual(self.calls.count(m.ARCHIVE_COMMAND),1)
  rows=r['archive_metadata_diagnostics'];self.assertEqual(set(rows),{'Info.plist',*[x+'/Contents/Info.plist' for p in m.PRODUCTS for x in (p[0],p[2])]})
  for name,row in rows.items():self.assertEqual(row['metadata'],plistlib.loads((self.root/m.ARCHIVE/name).read_bytes()))
  self.assertEqual(rows[path]['metadata'][key],value)
  output=self.root/'build/archive-proof';marker=self.root/'step-output';marker.write_text('')
  retained=m.retain_report(r,output,marker,clock=self.clock);self.assertEqual(retained['archive_metadata_diagnostics'][path]['metadata'][key],value)
  overflow=json.loads(m.report_bytes(r|{'commands':['x'*(m.MAX_REPORT+1)]}))
  self.assertEqual(overflow['archive_metadata_diagnostics'],retained['archive_metadata_diagnostics']);self.assertEqual(overflow['failure']['original_failure'],r['failure']);self.assertFalse(overflow['qualified'])
 def test_archive_version_failure_retains_all_five_plists(self):
  self.check_metadata_failure('Info.plist','ArchiveVersion',999,'archive-metadata-mismatch')
 def test_application_version_failure_retains_all_five_plists(self):
  self.check_metadata_failure(m.APP+'/Contents/Info.plist','CFBundleVersion','unexpected-build','application-identity-mismatch')
 def test_dsym_identity_failure_retains_all_five_plists(self):
  self.check_metadata_failure(m.DSYM+'/Contents/Info.plist','CFBundleIdentifier','unexpected.dsym','dSYM-metadata-mismatch')
 def test_source_failure_starts_no_command(self):
  with patch.object(m,'source_identity',side_effect=m.Rejected('source mismatch')):r=m.execute(env=self.identity,root=self.root,clock=self.clock,runner=self.runner)
  self.assertFalse(r['qualified']);self.assertEqual(self.calls,[])
 def test_late_report_cannot_emit_upload_marker(self):
  r=self.execute();r['clock']['report_ready_deadline']=self.clock();marker=self.root/'output';marker.write_text('prior\n')
  result=m.retain_report(r,self.root/'build/proof',marker,clock=self.clock);self.assertFalse(result['qualified']);self.assertEqual(marker.read_text(),'prior\n')
 def test_full_upload_reserve_is_required_and_failed_action_stays_failed(self):
  r=self.execute();r['upload_observation']=m.admit_upload(r,clock=self.clock)
  self.assertFalse(m.finish_upload(r,'failure',clock=self.clock)['upload_qualified']);self.assertTrue(m.finish_upload(r,'success',clock=self.clock)['upload_qualified'])
  self.clock.value=r['clock']['started_monotonic']+m.PHASE_END['evidence']-59
  with self.assertRaises(m.Rejected):m.admit_upload(r,clock=self.clock)
 def test_late_upload_does_not_reset_deadline(self):
  r=self.execute();r['upload_observation']=m.admit_upload(r,clock=self.clock);self.clock.advance(61);self.assertFalse(m.finish_upload(r,'success',clock=self.clock)['upload_qualified'])
 def test_retry_and_dispatch_identity_rejected(self):
  self.assertEqual(m.environment(self.identity),self.identity)
  for key,value in [('GITHUB_RUN_ATTEMPT','2'),('GITHUB_EVENT_NAME','workflow_dispatch'),('GITHUB_REF','refs/heads/main')]:
   with self.subTest(key=key),self.assertRaises(m.Rejected):m.environment(self.identity|{key:value})

if __name__=='__main__':unittest.main()
