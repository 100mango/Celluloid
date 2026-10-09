"""Portable only. No Apple command runs; process faults use mocks."""
import ast,base64,copy,datetime,hashlib,json,os,plistlib,re,shutil,signal,stat,struct,subprocess,tempfile,unittest,zlib
from pathlib import Path
from xml.etree import ElementTree as ET
from unittest.mock import Mock,patch
import mac_photos_roundtrip as d
import owned_mac_photos_runner as runner
ROOT=Path(__file__).resolve().parents[1]

class ClosedAndSourceTests(unittest.TestCase):
 def test_closed_before_any_process(self):
  with patch.object(d,'owned_read',return_value=b'{"enabled":false}'),patch.object(d,'run') as run,patch.object(d.subprocess,'check_output') as git:
   with self.assertRaisesRegex(ValueError,'CLOSED'):d.main()
   run.assert_not_called();git.assert_not_called()
 def test_source_inventory_and_all962_product_bytes(self):
  product,binding=d.source_snapshot();self.assertEqual(len(product['files']),962);self.assertEqual(binding['files'],962+len(d.ADDITIONS))
 def test_exact_runtime_before_native_work(self):
  self.assertEqual(d.runtime_record('27.0.1','26A434','arm64')['qualification_equivalence'],False)
  for v,b,a in [('27.0','26A428','arm64'),('27.0','26A434','arm64'),('27.0.1','26A428','arm64'),('27.0.2','26A434','arm64'),('27.0.1','26A434','x86_64'),(True,'26A434','arm64')]:
   with self.subTest(v=v,b=b,a=a),self.assertRaises(ValueError):d.runtime_record(v,b,a)
 def test_raw_commit_parent_not_shallow_traversal(self):
  def commit(parents):return 'tree '+'b'*40+'\n'+''.join('parent '+p+'\n' for p in parents)+'author Fixture <fixture@example.invalid> 1 +0000\n\nfixture'
  self.assertEqual(d.commit_parents(commit([d.BASE])),[d.BASE])
  for parents in [[],['a'*40],[d.BASE,'a'*40]]:self.assertNotEqual(d.commit_parents(commit(parents)),[d.BASE])
  for raw in ['','tree bad\n\n','tree '+'b'*40+'\nparent bad\n\n']:
   with self.assertRaises(ValueError):d.commit_parents(raw)
 def test_route_is_exact_push_attempt1(self):
  env={'GITHUB_REPOSITORY':'100mango/Celluloid','GITHUB_EVENT_NAME':'push','GITHUB_REF':'refs/heads/'+d.BRANCH,'CELLULOID_VALIDATION_SCOPE':'photos-writer-roundtrip-observation','GITHUB_WORKFLOW_REF':'100mango/Celluloid/'+d.WORKFLOW+'@refs/heads/'+d.BRANCH,'GITHUB_SHA':'a'*40,'GITHUB_WORKFLOW_SHA':'a'*40,'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1'}
  self.assertEqual(d.validate_route(env),'a'*40)
  for key,value in [('GITHUB_REPOSITORY','other/repo'),('GITHUB_EVENT_NAME','workflow_dispatch'),('GITHUB_REF','refs/heads/apple-platforms'),('GITHUB_REF','refs/heads/celluloid-final-mac-photos-roundtrip'),('GITHUB_REF','refs/heads/celluloid-final-mac-photos-roundtrip-v2'),('GITHUB_REF','refs/heads/celluloid-final-mac-photos-roundtrip-v3'),('GITHUB_REF','refs/heads/celluloid-final-mac-photos-roundtrip-v4'),('GITHUB_RUN_ATTEMPT','2'),('GITHUB_RUN_ID','0'),('GITHUB_WORKFLOW_SHA','b'*40),('CELLULOID_VALIDATION_SCOPE','photos-boundary-observation')]:
   with self.subTest(key=key),self.assertRaises(ValueError):d.validate_route(dict(env,**{key:value}))
 def test_no_runtime_regex_or_retry_argv(self):
  for action in ('build-for-testing','build','test-without-building'):
   args=d.command(Path('/owned'),action)
   self.assertEqual(args[0],'xcodebuild');self.assertEqual(args[-1],action)
   for flag in ('-retry-tests-on-failure','-test-iterations','-allowProvisioningUpdates','--help'):self.assertNotIn(flag,args)
   if action=='test-without-building':
    self.assertEqual(args.count('-only-testing:'+d.SELECTION),1);self.assertEqual(args[args.index('-maximum-test-execution-time-allowance')+1],'960')
 def test_json_duplicate_nonfinite_fail(self):
  for raw in ('{"a":1,"a":2}','{"x":NaN}','{"x":1e999}'):
   with self.assertRaises(ValueError):d.load_json(raw)
 def test_workflow_one_closed_job_and_fixed_cost(self):
  raw=(ROOT/d.WORKFLOW).read_text()
  enabled=d.load_json((ROOT/d.CONFIG).read_bytes())['enabled'];self.assertIs(type(enabled),bool)
  self.assertIn("if: ${{ github.ref == 'refs/heads/"+d.BRANCH+"' && github.run_attempt == 1 }}" if enabled else 'if: ${{ false }}',raw)
  for value in ['runs-on: xcode-27','timeout-minutes: 45','persist-credentials: false','fetch-depth: 1','contents: read','retention-days: 1'] :self.assertIn(value,raw)
  self.assertEqual(raw.count('runs-on:'),1)
  for value in ('workflow_dispatch:','matrix:','-retry-tests-on-failure','-allowProvisioningUpdates'):self.assertNotIn(value,raw)
 def test_overlay_only_diagnostic_membership(self):
  raw=(ROOT/(d.PROJECT+'/project.pbxproj')).read_text();base=(ROOT/'CelluloidNative.xcodeproj/project.pbxproj').read_text()
  self.assertIn('"path" = "Diagnostics/MacPhotosRoundtripTests.swift";',raw)
  self.assertEqual(raw.count('"path" = "CelluloidPhotoExtension/PhotosOutputWrite.swift";'),1)
  self.assertGreater(len(raw),len(base));self.assertEqual(d.sha((ROOT/d.WRITER).read_bytes()),'90927c87289ad4f466654f381ddd92d121fcce1b9294a2a1b20c49bfded57ba5')
 def test_single_swift_case_no_PhotoKit_no_extension_edit(self):
  raw=(ROOT/d.TEST).read_text();self.assertEqual(raw.count('func testOwnedWriterJPEGPhotosRoundtrip()'),1)
  self.assertEqual(raw.count('writer.start(jpeg: jpeg)'),1)
  for forbidden in ['import Photos\n','PHPhotoLibrary','PHAssetResource','finishContentEditing','captureIntended','beforeWriteForTesting =','Save Changes'] :self.assertNotIn(forbidden,raw)
  for required in ['committed == jpeg','original == jpeg && original == committed','delta <= 2','ROUNDTRIP_PNG_PIXEL_GATE','actual_extension_writer_observed','afterPendingWorkForTesting']:self.assertIn(required,raw)

class CommandProjectClosureTests(unittest.TestCase):
 # Parse only the quoted-string/dict/array format of this checked-in generated project.
 # No Xcode process, regeneration, eval, inferred scheme, or optional fallback.
 def project(self,raw=None):
  raw=(ROOT/d.PROJECT/'project.pbxproj').read_text() if raw is None else raw
  self.assertTrue(raw.startswith('// !$*UTF8*$!\n'));raw=raw.split('\n',1)[1]
  tokens=[];at=0;token=re.compile(r'\s*("(?:\\.|[^"\\])*"|[{}()=;,])')
  while raw[at:].strip():
   found=token.match(raw,at);self.assertIsNotNone(found,'unsupported project syntax')
   tokens.append(found[1]);at=found.end()
  index=[0]
  def take():
   self.assertLess(index[0],len(tokens),'truncated project');value=tokens[index[0]];index[0]+=1;return value
  def value():
   item=take()
   if item=='{':
    result={}
    while tokens[index[0]]!='}':
     key=json.loads(take());self.assertIs(type(key),str);self.assertNotIn(key,result,'duplicate project key')
     self.assertEqual(take(),'=');result[key]=value();self.assertEqual(take(),';')
    take();return result
   if item=='(':
    result=[]
    while tokens[index[0]]!=')':
     result.append(value())
     if tokens[index[0]]!=')':self.assertEqual(take(),',')
    take();return result
   self.assertTrue(item.startswith('"'),'unexpected project token');return json.loads(item)
  result=value();self.assertEqual(index[0],len(tokens),'trailing project data');return result
 def closure(self,action,project=None,scheme=None,root=ROOT):
  args=d.command(Path('/owned'),action)
  self.assertEqual(args.count('-project'),1);self.assertEqual(args.count('-scheme'),1)
  project_name=args[args.index('-project')+1];scheme_name=args[args.index('-scheme')+1]
  self.assertEqual(project_name,d.PROJECT);self.assertEqual(scheme_name,'CelluloidMac' if action=='build' else 'CelluloidMacUI')
  file=root/project_name/'xcshareddata/xcschemes'/(scheme_name+'.xcscheme')
  self.assertTrue(file.is_file(),'missing command scheme '+scheme_name)
  scheme=ET.fromstring(file.read_bytes()) if scheme is None else scheme
  project=self.project((root/project_name/'project.pbxproj').read_text()) if project is None else project
  objects=project['objects'];owner=objects[project['rootObject']];self.assertEqual(owner['isa'],'PBXProject')
  self.assertEqual(args[args.index('-configuration')+1],'Debug')
  references=scheme.findall('.//BuildableReference');self.assertGreater(len(references),0)
  for reference in references:
   self.assertEqual(reference.get('ReferencedContainer'),'container:'+project_name)
   self.assertEqual(reference.get('BuildableIdentifier'),'primary')
   target_id=reference.get('BlueprintIdentifier');self.assertIn(target_id,owner['targets'],'scheme target outside project')
   target=objects[target_id];self.assertEqual(target['isa'],'PBXNativeTarget');self.assertEqual(target['name'],reference.get('BlueprintName'))
   product=objects[target['productReference']];self.assertEqual(product['isa'],'PBXFileReference');self.assertEqual(product['path'],reference.get('BuildableName'))
   configs=objects[target['buildConfigurationList']];self.assertEqual(configs['isa'],'XCConfigurationList')
   self.assertEqual(sum(objects[key]['isa']=='XCBuildConfiguration' and objects[key]['name']=='Debug' for key in configs['buildConfigurations']),1,'missing/duplicate Debug configuration')
   for dependency_id in target['dependencies']:
    dependency=objects[dependency_id];self.assertEqual(dependency['isa'],'PBXTargetDependency');self.assertIn(dependency['target'],owner['targets'])
    self.assertEqual(objects[dependency['target']]['isa'],'PBXNativeTarget')
   for phase_id in target['buildPhases']:
    phase=objects[phase_id]
    for build_file in phase.get('files',[]):
     member=objects[build_file];self.assertEqual(member['isa'],'PBXBuildFile')
     links=[member[key] for key in ('fileRef','productRef') if key in member];self.assertEqual(len(links),1);self.assertIn(links[0],objects)
  entries=scheme.findall('./BuildAction/BuildActionEntries/BuildActionEntry')
  self.assertEqual(len(entries),1);self.assertEqual(entries[0].find('BuildableReference').get('BlueprintName'),'CelluloidMac')
  self.assertEqual(entries[0].get('buildForRunning' if action=='build' else 'buildForTesting'),'YES')
  if action!='build':
   test_action=scheme.find('TestAction');self.assertEqual(test_action.get('buildConfiguration'),'Debug')
   tests=test_action.findall('./Testables/TestableReference');self.assertEqual(len(tests),1);self.assertEqual(tests[0].get('skipped'),'NO')
   reference=tests[0].find('BuildableReference');self.assertEqual(reference.get('BlueprintName'),d.SELECTION.split('/')[0])
   target=objects[reference.get('BlueprintIdentifier')];sources=[]
   for phase_id in target['buildPhases']:
    phase=objects[phase_id]
    if phase['isa']=='PBXSourcesBuildPhase':sources.extend(objects[objects[key]['fileRef']]['path'] for key in phase['files'])
   self.assertEqual(sources.count(d.TEST),1);self.assertEqual(sources.count(d.WRITER),1)
   if action=='test-without-building':self.assertEqual([arg for arg in args if arg.startswith('-only-testing:')],['-only-testing:'+d.SELECTION])
  return {'action':action,'project':project_name,'scheme':scheme_name,'scheme_file':file.relative_to(root).as_posix(),'target_ids':sorted({node.get('BlueprintIdentifier') for node in references})}
 def test_every_real_driver_command_resolves_scheme_target_and_source_closure(self):
  self.assertEqual([self.closure(action)['action'] for action in ('build-for-testing','build','test-without-building')],['build-for-testing','build','test-without-building'])
  old=(ROOT/'CelluloidNative.xcodeproj/xcshareddata/xcschemes/CelluloidMac.xcscheme').read_text()
  self.assertEqual((ROOT/d.PROJECT/'xcshareddata/xcschemes/CelluloidMac.xcscheme').read_text(),old.replace('container:CelluloidNative.xcodeproj','container:'+d.PROJECT))
 def test_missing_ordinary_scheme_reproduces_v3_prebuild_failure(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder).resolve(strict=True);shutil.copytree(ROOT/d.PROJECT,root/d.PROJECT)
   (root/d.PROJECT/'xcshareddata/xcschemes/CelluloidMac.xcscheme').unlink()
   with self.assertRaisesRegex(AssertionError,'missing command scheme CelluloidMac'):self.closure('build',root=root)
 def test_wrong_container_target_product_or_configuration_is_rejected(self):
  for mode in ('container','uuid','membership','product','configuration'):
   scheme=ET.fromstring((ROOT/d.PROJECT/'xcshareddata/xcschemes/CelluloidMac.xcscheme').read_bytes());project=self.project();reference=scheme.find('.//BuildableReference');target_id=reference.get('BlueprintIdentifier');target=project['objects'][target_id]
   if mode=='container':reference.set('ReferencedContainer','container:CelluloidNative.xcodeproj')
   elif mode=='uuid':reference.set('BlueprintIdentifier','F'*24)
   elif mode=='membership':project['objects'][project['rootObject']]['targets'].remove(target_id)
   elif mode=='product':project['objects'][target['productReference']]['path']='Wrong.app'
   else:
    configs=project['objects'][target['buildConfigurationList']]['buildConfigurations']
    for key in configs:
     if project['objects'][key]['name']=='Debug':project['objects'][key]['name']='Wrong'
   with self.subTest(mode=mode),self.assertRaises(AssertionError):self.closure('build',project,scheme)
 def test_selected_case_requires_actual_UI_test_target_and_both_sources(self):
  for mode in ('wrong-test-target','missing-test-source','missing-writer'):
   scheme=ET.fromstring((ROOT/d.PROJECT/'xcshareddata/xcschemes/CelluloidMacUI.xcscheme').read_bytes());project=self.project();reference=scheme.find('./TestAction/Testables/TestableReference/BuildableReference')
   if mode=='wrong-test-target':reference.set('BlueprintName','OtherTests')
   else:
    target=project['objects'][reference.get('BlueprintIdentifier')];wanted=d.TEST if mode=='missing-test-source' else d.WRITER
    for phase_id in target['buildPhases']:
     phase=project['objects'][phase_id]
     if phase['isa']=='PBXSourcesBuildPhase':phase['files']=[key for key in phase['files'] if project['objects'][project['objects'][key]['fileRef']]['path']!=wanted]
   with self.subTest(mode=mode),self.assertRaises(AssertionError):self.closure('test-without-building',project,scheme)
 def test_project_parser_rejects_duplicate_or_trailing_input(self):
  for raw in ('// !$*UTF8*$!\n{"a"="x";"a"="y";}','// !$*UTF8*$!\n{} {}','// !$*UTF8*$!\n{ unquoted = "x"; }'):
   with self.assertRaises(AssertionError):self.project(raw)

class AppPreparationTests(unittest.TestCase):
 RIGHTS={'com.apple.security.app-sandbox':True,'com.apple.security.files.user-selected.read-write':True}
 def test_bounded_observation_keeps_actual_dictionary_without_admission(self):
  actual=dict(self.RIGHTS,**{'com.apple.security.get-task-allow':True})
  raw='Executable=/owned/CelluloidMac.app\n'+plistlib.dumps(actual).decode()
  result=d.app_entitlement_observation(raw,'build-for-testing')
  self.assertEqual(result['entitlements'],actual);self.assertEqual(result['build_action'],'build-for-testing')
  self.assertEqual(result['scheme'],'CelluloidMacUI');self.assertEqual(result['output_sha256'],d.sha(raw.encode()))
  self.assertEqual(result['output_bytes'],len(raw.encode()));self.assertNotIn('accepted',result)
 def test_malformed_ambiguous_oversized_or_nondictionary_entitlements_stop(self):
  valid=plistlib.dumps(self.RIGHTS).decode()
  for raw in ('',valid+valid,'<?xml version="1.0"?><plist><dict>broken</plist>',plistlib.dumps(['not a dictionary']).decode(),'x'*8193):
   with self.subTest(raw=raw[:30]),self.assertRaises((ValueError,plistlib.InvalidFileException)):
    d.app_entitlement_observation(raw,'build')
 def exercise(self,ui=None,ordinary=None,fail_stage=None,exhaust=False):
  original=d.owned_read;binding={'source_fingerprint':'b'*64,'source_manifest_sha256':'c'*64,'files':975}
  before=dict(binding,source_sha='a'*40,run_id='123',run_attempt=1)
  def read(path,cap):
   if Path(path)==ROOT/d.CONFIG:return b'{"enabled":true}'
   return original(path,cap)
  ui=plistlib.dumps(dict(self.RIGHTS,**{'com.apple.security.get-task-allow':True})).decode() if ui is None else ui
  ordinary=plistlib.dumps(self.RIGHTS).decode() if ordinary is None else ordinary
  commands=[];now=[101.0]
  def run(args,**kwargs):
   args=args[4:];commands.append(args)
   if args[:2]==['/usr/bin/codesign','--force']:raise RuntimeError('TEST_STOP_BEFORE_ANY_REAL_RESIGN')
   if args[-1]=='-productVersion':out='27.0.1\n'
   elif args[-1]=='-buildVersion':out='26A434\n'
   elif args==['xcodebuild','-version']:out='Xcode 27.0\nBuild version 27A266a\n'
   elif args==['xcrun','xcresulttool','help','export','attachments']:out=ImportCapabilityTests.HELP
   elif args[:2]==['/usr/bin/codesign','-d']:out=ordinary if any(row[-1]=='build' for row in commands) else ui
   else:out='mock success\n'
   if args[-1]=='build' and exhaust:now[0]=700.0
   return subprocess.CompletedProcess(args,65 if args[-1]==fail_stage else 0,out,'')
  with tempfile.TemporaryDirectory() as folder:
   temp=Path(folder).resolve(strict=True);(temp/'mac-job-clock.json').write_bytes(d.encoded({'source_sha':'a'*40,'execution_budget_seconds':2460,'started_monotonic':100.0,'started_unix':1000.0}))
   cwd=Path.cwd()
   try:
    os.chdir(ROOT)
    with patch.object(d,'owned_read',side_effect=read),patch.object(d,'admit_source',return_value=before),patch.object(d,'source_snapshot',return_value=({},binding)),patch.object(d,'run',side_effect=run),patch.object(d.time,'monotonic',side_effect=lambda:now[0]),patch.object(d.os,'uname',return_value=type('U',(),{'machine':'arm64'})()),patch.dict(os.environ,{'RUNNER_TEMP':str(temp)}),patch('builtins.print'):
     self.assertEqual(d.main(),1)
   finally:os.chdir(cwd)
   out=temp/'celluloid-photos-roundtrip-evidence'
   files={path.name:path.read_bytes() for path in out.iterdir()}
   return commands,d.load_json(files['run.json']),files,temp
 def test_ordinary_app_build_order_both_observations_and_original_rights_gate(self):
  commands,report,files,temp=self.exercise()
  builds=[row for row in commands if row[0]=='xcodebuild' and row[-1] in ('build-for-testing','build')]
  self.assertEqual(builds,[d.command(temp,'build-for-testing'),d.command(temp,'build')])
  self.assertEqual(builds[1],['xcodebuild','-project','CelluloidPhotosRoundtrip.xcodeproj','-scheme','CelluloidMac','-configuration','Debug','-destination','platform=macOS','-derivedDataPath',str(temp/'celluloid-roundtrip'),'CODE_SIGNING_ALLOWED=YES','CODE_SIGNING_REQUIRED=YES','CODE_SIGN_IDENTITY=-','CODE_SIGN_STYLE=Manual','ENABLE_TESTABILITY=NO','build'])
  stages=[row['stage'] for row in report['events']]
  self.assertEqual(stages[-5:],['ui-build','app-entitlements-ui-build','app-build','app-entitlements-app-build','debug-sign-app'])
  self.assertIn('TEST_STOP_BEFORE_ANY_REAL_RESIGN',report['error'])
  first=d.load_json(files['app-entitlements-ui-build.json']);second=d.load_json(files['app-entitlements-app-build.json'])
  self.assertEqual(first['build_action'],'build-for-testing');self.assertEqual(second['build_action'],'build')
  self.assertEqual(first['entitlements'],dict(self.RIGHTS,**{'com.apple.security.get-task-allow':True}))
  self.assertEqual(second['entitlements'],self.RIGHTS);self.assertFalse(report['diagnostic_complete'])
  self.assertEqual(report['budgets']['original_clock_seconds'],2460);self.assertEqual(report['budgets']['artifact_cap_bytes'],1000000)
 def test_changed_ordinary_rights_are_retained_and_rejected_before_resign(self):
  for rights in (dict(self.RIGHTS,**{'com.apple.security.get-task-allow':True}),{'com.apple.security.app-sandbox':True},dict(self.RIGHTS,**{'com.apple.security.network.client':True})):
   with self.subTest(rights=rights):
    commands,report,files,_=self.exercise(ordinary=plistlib.dumps(rights).decode())
    self.assertEqual(report['error'],'ValueError: unexpected app entitlements')
    self.assertEqual(d.load_json(files['app-entitlements-app-build.json'])['entitlements'],rights)
    self.assertEqual(commands[-1][:2],['/usr/bin/codesign','-d']);self.assertFalse(any(row[-1]=='test-without-building' for row in commands))
 def test_either_build_failure_stops_before_further_native_command(self):
  for action,stage in [('build-for-testing','ui-build'),('build','app-build')]:
   with self.subTest(action=action):
    commands,report,files,_=self.exercise(fail_stage=action)
    self.assertEqual(commands[-1][-1],action);self.assertEqual(report['stage'],stage)
    self.assertNotIn('app-entitlements-app-build.json',files);self.assertFalse(report['diagnostic_complete'])
 def test_either_parse_failure_stops_before_further_native_command(self):
  malformed='<?xml version="1.0"?><plist><dict>broken</plist>'
  for kwargs,label in [({'ui':raw},'app-entitlements-ui-build') for raw in ('bad',malformed)]+[({'ordinary':raw},'app-entitlements-app-build') for raw in ('bad',malformed)]:
   with self.subTest(label=label):
    commands,report,files,_=self.exercise(**kwargs)
    self.assertEqual(commands[-1][:2],['/usr/bin/codesign','-d'])
    raw=next(iter(kwargs.values())).encode()
    self.assertEqual(report['events'][-1]['stage'],label);self.assertEqual(report['events'][-1]['output_sha256'],d.sha(raw))
    self.assertNotIn(label+'.json',files);self.assertIn(report['error'],('ValueError: entitlement plist','ValueError: malformed entitlement plist'))
 def test_second_build_consumes_original_reserve_without_reset(self):
  commands,report,files,_=self.exercise(exhaust=True)
  self.assertEqual(commands[-1][-1],'build');self.assertIn('original before-prepare reserve exhausted',report['error'])
  self.assertNotIn('app-entitlements-app-build.json',files);self.assertFalse(report['diagnostic_complete'])
 def test_nonjson_plist_types_preserve_error_and_hash_before_stopping(self):
  for value in (b'fixture bytes',datetime.datetime(2026,10,9)):
   for kind in ('ui','ordinary'):
    raw=plistlib.dumps({'fixture':value}).decode()
    with self.subTest(type=type(value).__name__,build=kind):
     commands,report,files,_=self.exercise(**{kind:raw})
     self.assertEqual(commands[-1][:2],['/usr/bin/codesign','-d'])
     self.assertTrue(report['error'].startswith('TypeError: Object of type '+type(value).__name__))
     self.assertIn('not JSON serializable',report['error'])
     event=report['events'][-1];self.assertEqual(event['output_bytes'],len(raw.encode()));self.assertEqual(event['output_sha256'],d.sha(raw.encode()))
     self.assertNotIn(event['stage']+'.json',files);self.assertIn('manifest.json',files);self.assertFalse(report['diagnostic_complete'])

class OwnedReadTests(unittest.TestCase):
 def test_exact_regular_file_only(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder).resolve(strict=True);p=root/'owned';p.write_bytes(b'owned');self.assertEqual(d.owned_read(p,5),b'owned')
   with self.assertRaises(ValueError):d.owned_read(p,4)
   alias=root/'alias';alias.symlink_to(p)
   with self.assertRaises(ValueError):d.owned_read(alias,5)
   linked=root/'linked';os.link(p,linked)
   with self.assertRaises(ValueError):d.owned_read(p,5)
 def test_parent_alias_rejected(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder).resolve(strict=True);(root/'dir').mkdir();(root/'dir/f').write_bytes(b'x');(root/'alias').symlink_to(root/'dir',target_is_directory=True)
   with self.assertRaises(ValueError):d.owned_read(root/'alias/f',5)
 def test_owned_temp_root_alias_normalization_keeps_reader_strict(self):
  with tempfile.TemporaryDirectory() as outer:
   root=Path(outer).resolve(strict=True);actual=root/'actual';actual.mkdir();alias=root/'var-alias';alias.symlink_to(actual,target_is_directory=True)
   with tempfile.TemporaryDirectory(dir=alias) as supplied:
    raw_root=Path(supplied);canonical=raw_root.resolve(strict=True);self.assertNotEqual(raw_root,canonical)
    file=canonical/'owned';file.write_bytes(b'owned')
    with self.assertRaisesRegex(ValueError,'owned path alias'):d.owned_read(raw_root/'owned',5)
    self.assertEqual(d.owned_read(file,5),b'owned')
    with patch.object(d.os,'getuid',return_value=os.getuid()+1),self.assertRaisesRegex(ValueError,'foreign owned directory'):d.owned_read(file,5)
    linked=canonical/'link';linked.symlink_to(file)
    with self.assertRaisesRegex(ValueError,'owned path alias'):d.owned_read(linked,5)
 def test_foreign_owner_rejected(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder).resolve(strict=True)/'f';p.write_bytes(b'x')
   with patch.object(d.os,'getuid',return_value=os.getuid()+1),self.assertRaisesRegex(ValueError,'foreign'):d.owned_read(p,5)

class NativeAdmissionTests(unittest.TestCase):
 def fixture(self,passed=False):
  context={'source_sha':'a'*40,'run_id':'123','run_attempt':1,'test_source_sha256':'b'*64,'writer_source_sha256':'c'*64,'script_sha256':'d'*64,'runtime':d.runtime_record('27.0.1','26A434','arm64')};cb=d.encoded(context)
  proof={'schema':'Celluloid.OwnedPhotosRoundtripReceipt.1',**{k:context[k] for k in ('source_sha','run_id','run_attempt','runtime')},'context_sha256':d.sha(cb),'complete':True,'stage':'png-exported','actual_extension_writer_observed':False,'actual_photos_callback_observed':False,'qualification_equivalence':False,'allowed_max_channel_delta':2,'writer_start_count':1,'initial_asset_count':0,'imported_asset_count':1,'inputs_checked':True,'writer_claim_succeeded':True,'writer_reservation_completed':True,'binary_scalar_self_tested':True,'case_elapsed_seconds':10.0,'phases':['reference','writer-committed','imported','original-exported','png-exported'],'source_fixture_sha256':d.INPUTS['source'][2],**{k:d.INPUTS['jpeg'][2] for k in ('jpeg_sha256','writer_committed_sha256','unmodified_original_sha256')},'expected_rgba_sha256':d.EXPECTED_RGBA,'historical_rgba_sha256':d.HISTORICAL_RGBA,'max_channel_delta':0 if passed else 3,'pixel_contract_passed':passed,'historical_rgba_equal':not passed,'failure':None if passed else 'ROUNDTRIP_PNG_PIXEL_GATE','import_selection':{'panel_identifier':'open-panel','panel_label':'Import','full_path_readback':'/owned/Celluloid-Owned-Roundtrip.jpg','filename':'Celluloid-Owned-Roundtrip.jpg','file_cell_count':1,'all_cell_count':1,'total_selected_cell_count':1,'selected':True,'guard_native_reachability_previously_qualified':False},'asset_label':'synthetic','photos_identity':{'pid':123,'bundle':'/System/Applications/Photos.app','executable':'/System/Applications/Photos.app/Contents/MacOS/Photos'},'control_catalog':[['ExportOptions','PopUpButton','id','title','label','PNG',1,True,True]],'export_option_bindings':[['bound']],'binary_states':[['bound']],'single_photo_topologies':['collection-present']}
  device={'platform':'macOS','osVersion':'27.0.1','osBuildNumber':'26A434','architecture':'arm64','deviceId':'owned','deviceName':'My Mac'}
  counts={'passedTests':int(passed),'failedTests':int(not passed),'skippedTests':0,'expectedFailures':0}
  summary={'runtimeWarnings':[],'totalTestCount':1,**counts,'result':'Passed' if passed else 'Failed','startTime':101.0,'finishTime':111.0,'devicesAndConfigurations':[{'device':device,**counts}],'testFailures':[] if passed else [{'targetName':'CelluloidMacUITests','testIdentifierString':'MacPhotosRoundtripTests/testOwnedWriterJPEGPhotosRoundtrip()','failureText':'ROUNDTRIP_PNG_PIXEL_GATE'}]}
  event={'returned_without_timeout':True,'return_code':0 if passed else 65,'elapsed_seconds':12.0,'started_unix':100.0,'finished_unix':112.0}
  return context,cb,proof,summary,event
 def log(self,context,cb,proof,passed):
  raw=d.encoded(proof);env={'schema':'Celluloid.OwnedPhotosRoundtripProof.1',**{k:context[k] for k in ('source_sha','test_source_sha256','writer_source_sha256','script_sha256')},'context_sha256':d.sha(cb),'bytes':len(raw),'sha256':d.sha(raw),'base64':base64.b64encode(raw).decode()}
  return "Test Case '"+d.RAW_CASE+"' started.\n"+("" if passed else "ROUNDTRIP_BLOCKED stage=png-exported reason=ROUNDTRIP_PNG_PIXEL_GATE\n")+d.PREFIX+d.encoded(env).decode()+"\nTest Case '"+d.RAW_CASE+("' passed" if passed else "' failed")+" (10.0 seconds).\n/owned/result.xcresult\n** TEST EXECUTE "+('SUCCEEDED' if passed else 'FAILED')+' **\n'
 def admit(self,proof=None,summary=None,event=None,passed=False):
  c,cb,p,s,e=self.fixture(passed);p=p if proof is None else proof;s=s if summary is None else summary;e=e if event is None else event
  return d.admit_native(self.log(c,cb,p,passed),e,s,c,cb,'/owned/result.xcresult')
 def test_strict_failure_is_completed_diagnostic_not_pass(self):self.assertFalse(self.admit()[1]['pixel_contract_passed'])
 def test_strict_pass_requires_official_pass(self):self.assertTrue(self.admit(passed=True)[1]['pixel_contract_passed'])
 def test_foreign_or_malformed_receipts_stop(self):
  for key,value in [('complete',False),('stage','imported'),('context_sha256','0'*64),('source_sha','e'*40),('run_attempt',True),('actual_extension_writer_observed',True),('qualification_equivalence',True),('allowed_max_channel_delta',3),('writer_start_count',2),('initial_asset_count',1),('imported_asset_count',2),('writer_claim_succeeded',False),('writer_reservation_completed',False),('inputs_checked',False),('case_elapsed_seconds',901),('jpeg_sha256','0'*64),('writer_committed_sha256','0'*64),('unmodified_original_sha256','0'*64),('expected_rgba_sha256','0'*64),('max_channel_delta',True),('pixel_contract_passed',True),('failure','Unknown permission'),('historical_rgba_equal',1),('phases',[]),('control_catalog',[]),('single_photo_topologies',[])]:
   p=self.fixture()[2];p[key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):self.admit(proof=p)
 def test_ui_control_disabled_or_multiple_rejected(self):
  for i,v in [(6,2),(6,True),(7,False),(8,False),(0,1)]:
   p=self.fixture()[2];p['control_catalog'][0][i]=v
   with self.subTest(i=i),self.assertRaises(ValueError):self.admit(proof=p)
 def test_official_summary_exact_pair_and_one_result(self):
  for key,value in [('runtimeWarnings',['warning']),('totalTestCount',0),('failedTests',True),('passedTests',1),('skippedTests',1),('expectedFailures',1),('startTime',99),('finishTime',113),('testFailures',[]),('result','Passed')]:
   s=self.fixture()[3];s[key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):self.admit(summary=s)
  s=self.fixture()[3];s['devicesAndConfigurations'][0]['device']['osBuildNumber']='26A428'
  with self.assertRaises(ValueError):self.admit(summary=s)
 def test_nonzero_non65_late_and_incomplete_process_rejected(self):
  for key,value in [('return_code',64),('elapsed_seconds',1021),('returned_without_timeout',False)]:
   event=self.fixture()[4];event[key]=value
   with self.assertRaises(ValueError):self.admit(event=event)
 def test_wrong_case_missing_duplicate_outside_proof_rejected(self):
  c,cb,p,s,e=self.fixture();log=self.log(c,cb,p,False);line=next(r for r in log.splitlines() if r.startswith(d.PREFIX))
  for wrong in [log.replace(d.RAW_CASE,'-[Other testWrong]'),log.replace(line,''),log.replace(line,line+'\n'+line),line+'\n'+log.replace(line,''),log.replace('/owned/result.xcresult','/foreign/result.xcresult')]:
   with self.assertRaises(ValueError):d.admit_native(wrong,e,s,c,cb,'/owned/result.xcresult')
 def test_pure_pre_summary_admission_rejects_abnormal_terminal_and_unknown_block(self):
  c,cb,p,s,e=self.fixture();log=self.log(c,cb,p,False)
  for altered,event in [(log,dict(e,return_code=70)),(log.replace('** TEST EXECUTE FAILED **',''),e),(log.replace('ROUNDTRIP_BLOCKED stage=png-exported reason=ROUNDTRIP_PNG_PIXEL_GATE','ROUNDTRIP_DENIED_STOP denied'),e),(log.replace('reason=ROUNDTRIP_PNG_PIXEL_GATE','reason=Unknown prompt'),e)]:
   with self.assertRaises(ValueError):d.admit_log(altered,event,c,cb,'/owned/result.xcresult')
 def test_two_selected_files_or_unqualified_import_claim_rejected(self):
  for key,value in [('total_selected_cell_count',2),('file_cell_count',2),('all_cell_count',129),('selected',False),('guard_native_reachability_previously_qualified',True)]:
   p=self.fixture()[2];p['import_selection'][key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):self.admit(proof=p)
 def test_tampered_envelope_bytes_rejected(self):
  c,cb,p,s,e=self.fixture();log=self.log(c,cb,p,False);prefixline=next(r for r in log.splitlines() if r.startswith(d.PREFIX));env=d.load_json(prefixline[len(d.PREFIX):]);env['sha256']='0'*64
  with self.assertRaises(ValueError):d.admit_native(log.replace(prefixline,d.PREFIX+d.encoded(env).decode()),e,s,c,cb,'/owned/result.xcresult')

class ImportObservationTests(unittest.TestCase):
 def fixture(self,context=None):
  c,cb,p,summary,event=NativeAdmissionTests().fixture(False)
  if context is not None:c=context
  c.setdefault('test_source_path','/owned/Diagnostics/MacPhotosRoundtripTests.swift');cb=d.encoded(c)
  p.update({key:c[key] for key in ('source_sha','run_id','run_attempt','runtime')});p['context_sha256']=d.sha(cb)
  p.update(complete=False,stage='writer-committed',failure=d.IMPORT_FAILURE,phases=['reference','writer-committed'],writer_reservation_completed=False)
  p['import_selection'].update(file_cell_count=0,all_cell_count=23,total_selected_cell_count=1,selected=False,panel_label='review for import')
  p['images']={'writer-committed.jpg':{'bytes':d.INPUTS['jpeg'][1],'sha256':d.INPUTS['jpeg'][2]}}
  ax={'schema':'Celluloid.OwnedImportAX.1','source_sha':c['source_sha'],'context_sha256':d.sha(cb),'photos_pid':123,'initial_asset_count':0,
   'fixture_path':p['import_selection']['full_path_readback'],'fixture_sha256':d.INPUTS['jpeg'][2],'panel_identifier':'open-panel','panel_label':'review for import',
   'columns':['index','parent','role','identifier','label','title','value','selected','frame','truncated_attributes'],
   'nodes':[[0,-1,'sheet','open-panel','review for import','','',False,[0,0,600,400],[False]*4],
    [1,0,'other:18','file-browser','','','',False,[0,0,500,300],[False]*4],
    [2,1,'cell','','','','',True,[0,0,100,20],[False]*4],
    [3,2,'staticText','',p['import_selection']['filename'],'','',False,[0,0,100,20],[False]*4]],
   'selection_guard_unchanged':True,'no_import_confirmation':True}
  def chunk(name,raw):return struct.pack('>I',len(raw))+name+raw+struct.pack('>I',zlib.crc32(name+raw)&0xffffffff)
  png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,6,0,0,0))+chunk(b'sRGB',b'\0')+chunk(b'IDAT',zlib.compress(b'\0\xff\xff\xff\xff'))+chunk(b'IEND',b'')
  raws={'writer-committed.jpg':(ROOT/d.INPUTS['jpeg'][0]).read_bytes(),'import-ax.json':d.encoded(ax),'import-panel.png':png}
  p['import_observation']={'schema':'Celluloid.OwnedImportObservation.1','complete':True,'scope':'owned-open-panel-only',
   'source_sha':c['source_sha'],'context_sha256':d.sha(cb),'photos_pid':123,'initial_asset_count':0,'fixture_sha256':d.INPUTS['jpeg'][2],
   'panel_identifier':'open-panel','panel_label':'review for import','selection_guard_unchanged':True,'no_import_confirmation':True,
   'ax':{'bytes':len(raws['import-ax.json']),'sha256':d.sha(raws['import-ax.json']),'node_count':4},
   'screenshot':{'bytes':len(png),'sha256':d.sha(png),'type':'public.png','width':1,'height':1,'source_width':1,'source_height':1,'srgb_icc_reference':None,'resized_panel_preview':True,'maximum_side':640}}
  summary['testFailures'][0]['failureText']=d.IMPORT_ERROR
  return c,cb,p,summary,event,raws,ax
 def log(self,c,cb,p):
  log=NativeAdmissionTests().log(c,cb,p,False).replace('ROUNDTRIP_BLOCKED stage=png-exported reason=ROUNDTRIP_PNG_PIXEL_GATE','ROUNDTRIP_BLOCKED stage=writer-committed reason='+d.IMPORT_FAILURE)
  return log.replace(d.PREFIX,c['test_source_path']+':1: error: '+d.RAW_CASE+' : '+d.IMPORT_ERROR+'\n'+d.PREFIX)
 def test_known_failed_case_admits_readonly_diagnosis_but_never_success(self):
  c,cb,p,s,e,_,_=self.fixture();log=self.log(c,cb,p)
  self.assertFalse(d.admit_import_observation_log(log,e,c,cb,'/owned/result.xcresult')[1]['complete'])
  self.assertEqual(d.admit_import_observation_summary(s,e,c)['architecture'],'arm64')
  with self.assertRaisesRegex(ValueError,'incomplete diagnostic'):d.admit_log(log,e,c,cb,'/owned/result.xcresult')
 def test_missing_terminal_cancellation_denial_and_extra_errors_stop(self):
  c,cb,p,s,e,_,_=self.fixture();log=self.log(c,cb,p)
  bad=[(log,dict(e,return_code=70)),(log,dict(e,returned_without_timeout=False)),(log,dict(e,cleanup_unconfirmed=True)),(log,dict(e,cancelled=True)),(log,dict(e,timed_out=True)),
   (log.replace('** TEST EXECUTE FAILED **',''),e),(log+'\nROUNDTRIP_DENIED_STOP denied',e),(log+'\n/other: error: -[Other fail] : failed',e)]
  for text,event in bad:
   with self.assertRaises(ValueError):d.admit_import_observation_log(text,event,c,cb,'/owned/result.xcresult')
 def test_foreign_source_case_panel_library_and_claims_stop(self):
  for key,value in [('complete',True),('stage','imported'),('failure','Unknown alert'),('source_sha','f'*40),('initial_asset_count',1),('writer_reservation_completed',True),('writer_start_count',2),('pixel_contract_passed',True),('actual_extension_writer_observed',True),('allowed_max_channel_delta',3),('import_observation',{})]:
   c,cb,p,s,e,_,_=self.fixture();p[key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):d.admit_import_observation_log(self.log(c,cb,p),e,c,cb,'/owned/result.xcresult')
  for key,value in [('scope','application'),('photos_pid',999),('initial_asset_count',1),('panel_identifier','Other'),('no_import_confirmation',False),('selection_guard_unchanged',False)]:
   c,cb,p,s,e,_,_=self.fixture();p['import_observation'][key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):d.admit_import_observation_log(self.log(c,cb,p),e,c,cb,'/owned/result.xcresult')
 def test_wrong_official_runtime_or_additional_failure_blocks_export(self):
  c,cb,p,s,e,_,_=self.fixture()
  for key,value in [('runtimeWarnings',['warning']),('passedTests',1),('failedTests',2),('skippedTests',1),('result','Passed'),('startTime',99),('testFailures',[])]:
   with self.subTest(key=key),self.assertRaises(ValueError):d.admit_import_observation_summary(dict(s,**{key:value}),e,c)
  s['devicesAndConfigurations'][0]['device']['osBuildNumber']='26A428'
  with self.assertRaises(ValueError):d.admit_import_observation_summary(s,e,c)
 def records(self,folder,raws,summary):
  device=summary['devicesAndConfigurations'][0]['device'];rows=[]
  for index,(name,raw) in enumerate(raws.items()):
   file=str(index)+Path(name).suffix;(folder/file).write_bytes(raw)
   rows.append({'suggestedHumanReadableName':'celluloid-roundtrip-'+Path(name).stem+'_0_00000000-0000-0000-0000-000000000000'+Path(name).suffix,'exportedFileName':file,
    'deviceId':device['deviceId'],'deviceName':device['deviceName'],'configurationName':'Test Scheme Action','timestamp':(summary['startTime']+summary['finishTime'])/2})
  return [{'testIdentifier':'MacPhotosRoundtripTests/testOwnedWriterJPEGPhotosRoundtrip()','testIdentifierURL':'test://com.apple.xcode/CelluloidPhotosRoundtrip/'+d.SELECTION,'attachments':rows}]
 def test_exact_named_raw_evidence_and_AX_tree_bound_to_failed_owned_panel(self):
  c,cb,p,s,e,raws,ax=self.fixture()
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder).resolve(strict=True);m=self.records(root,raws,s)
   found,actual=d.import_observation_attachments(root,m,s['devicesAndConfigurations'][0]['device'],s,p,cb)
   self.assertEqual(found,raws);self.assertEqual(actual,ax)
 def test_corrupt_foreign_missing_extra_or_wrong_geometry_attachments_reject(self):
  for mode in ('hash','missing','extra','device','time','path','geometry'):
   c,cb,p,s,e,raws,ax=self.fixture()
   with tempfile.TemporaryDirectory() as folder:
    root=Path(folder).resolve(strict=True);m=self.records(root,raws,s);rows=m[0]['attachments']
    if mode=='hash':(root/rows[0]['exportedFileName']).write_bytes(b'corrupt')
    elif mode=='missing':rows.pop()
    elif mode=='extra':rows.append(dict(rows[0]))
    elif mode=='device':rows[0]['deviceId']='foreign'
    elif mode=='time':rows[0]['timestamp']=1000
    elif mode=='path':rows[0]['exportedFileName']='../foreign'
    else:p['import_observation']['screenshot']['width']=2
    with self.subTest(mode=mode),self.assertRaises(ValueError):d.import_observation_attachments(root,m,s['devicesAndConfigurations'][0]['device'],s,p,cb)
 def test_rehashed_AX_wrong_root_parent_or_fixture_still_rejects(self):
  for mode in ('root','parent','fixture','library'):
   c,cb,p,s,e,raws,ax=self.fixture()
   if mode=='root':ax['nodes'][0][3]='PhotosApplication'
   elif mode=='parent':ax['nodes'][2][1]=2
   elif mode=='fixture':ax['fixture_path']='/other/foreign.jpg'
   else:ax['initial_asset_count']=1
   raws['import-ax.json']=d.encoded(ax);p['import_observation']['ax'].update(bytes=len(raws['import-ax.json']),sha256=d.sha(raws['import-ax.json']))
   with tempfile.TemporaryDirectory() as folder:
    root=Path(folder).resolve(strict=True);m=self.records(root,raws,s)
    with self.subTest(mode=mode),self.assertRaises(ValueError):d.import_observation_attachments(root,m,s['devicesAndConfigurations'][0]['device'],s,p,cb)

 def test_rehashed_truncated_corrupt_or_wrong_scale_preview_rejects(self):
  for mode in ('truncated','crc','scale'):
   c,cb,p,s,e,raws,ax=self.fixture()
   if mode=='truncated':raws['import-panel.png']=raws['import-panel.png'][:33]
   elif mode=='crc':raws['import-panel.png']=raws['import-panel.png'][:-1]+b'1'
   else:p['import_observation']['screenshot']['source_width']=2
   png=raws['import-panel.png'];p['import_observation']['screenshot'].update(bytes=len(png),sha256=d.sha(png))
   with tempfile.TemporaryDirectory() as folder:
    root=Path(folder).resolve(strict=True);m=self.records(root,raws,s)
    with self.subTest(mode=mode),self.assertRaises(ValueError):
     d.admit_import_observation_log(self.log(c,cb,p),e,c,cb,'/owned/result.xcresult')
     d.import_observation_attachments(root,m,s['devicesAndConfigurations'][0]['device'],s,p,cb)
 def test_observed_fopen_noise_is_not_permission_denial(self):
  c,cb,p,s,e,_,_=self.fixture()
  log=self.log(c,cb,p)+'\nfopen failed for data file: errno = 2 (No such file or directory)\n'
  self.assertFalse(d.admit_import_observation_log(log,e,c,cb,'/owned/result.xcresult')[1]['complete'])

class ImportCapabilityTests(unittest.TestCase):
 HELP='USAGE: xcresulttool export attachments --path <path> --output-path <output-path> [--test-id <test-id>]\n\nOPTIONS:\n  --path <path>          Path to result bundle.\n  --output-path <output-path> Output folder.\n  --test-id <test-id>    Test identifier URL or string.\n'
 def test_exact_official_help_options_required(self):
  self.assertEqual(d.admit_import_export_help(self.HELP)['verified_options'],['--path','--output-path','--test-id'])
  for text in (self.HELP.replace('--test-id','--unknown'),self.HELP.replace('export attachments','get test-results'),self.HELP+'\nPermission denied',self.HELP+'x'*16384):
   with self.assertRaises(ValueError):d.admit_import_export_help(text)
 def test_temporary_export_inventory_caps_and_ownership(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory).resolve(strict=True);(root/'manifest.json').write_bytes(b'[]')
   self.assertEqual(d.import_export_inventory(root)[0]['bytes'],2)
   (root/'link').symlink_to(root/'manifest.json')
   with self.assertRaisesRegex(ValueError,'type/owner'):d.import_export_inventory(root)
   (root/'link').unlink();(root/'too-big').write_bytes(b'')
   with (root/'too-big').open('r+b') as stream:stream.truncate(16*1024*1024)
   with self.assertRaisesRegex(ValueError,'aggregate cap'):d.import_export_inventory(root)
   (root/'too-big').unlink();(root/'folder').mkdir()
   with self.assertRaisesRegex(ValueError,'type/owner'):d.import_export_inventory(root)

class ImportDriverDispatchTests(unittest.TestCase):
 def exercise(self,mode):
  original=d.owned_read;binding={'source_fingerprint':'b'*64,'source_manifest_sha256':'c'*64,'files':976}
  before=dict(binding,source_sha='a'*40,tree='d'*40,parent=d.BASE,run_id='123',run_attempt=1)
  def read(path,cap):
   if Path(path)==ROOT/d.CONFIG:return b'{"enabled":true}'
   return original(path,cap)
  helper=ImportObservationTests();commands=[];mono=[101.0];wall=[1000.0];pending={}
  def tick(clock):clock[0]+=.01;return clock[0]
  with tempfile.TemporaryDirectory() as folder:
   temp=Path(folder).resolve(strict=True);(temp/'mac-job-clock.json').write_bytes(d.encoded({'source_sha':'a'*40,'execution_budget_seconds':2460,'started_monotonic':100.0,'started_unix':1000.0}))
   def run(args,**kwargs):
    args=args[4:];commands.append(args);code=0
    if args[-1]=='-productVersion':out='27.0.1\n'
    elif args[-1]=='-buildVersion':out='26A434\n'
    elif args==['xcodebuild','-version']:out='Xcode 27.0\nBuild version 27A266a\n'
    elif args==['xcrun','xcresulttool','help','export','attachments']:out=ImportCapabilityTests.HELP if mode!='help-missing' else 'USAGE: xcresulttool export attachments\n'
    elif args[:2]==['/usr/bin/codesign','-d']:out=plistlib.dumps(AppPreparationTests.RIGHTS).decode()
    elif args[-1]=='test-without-building':
     if mode=='timeout':raise TimeoutError('mock native timeout')
     if mode=='cancelled':raise runner.OwnedCommandCancelled('mock cancellation')
     c=d.load_json((temp/'roundtrip-context.json').read_bytes());c,cb,p,s,e,raws,ax=helper.fixture(c)
     s['startTime']=wall[0]+1;s['finishTime']=wall[0]+11;mono[0]+=12;wall[0]+=12
     if mode=='wrong-failure':p['failure']='Unknown permission prompt'
     out=helper.log(c,cb,p).replace('/owned/result.xcresult',str(temp/'MacPhotosRoundtrip.xcresult'))
     if mode=='missing-terminal':out=out.replace('** TEST EXECUTE FAILED **','')
     if mode=='denied':out+='\nROUNDTRIP_DENIED_STOP unknown access\n'
     extras={'top-error':'xcodebuild: error: unrelated transport failure','permission-error':'error: Permission denied reading result bundle','proof-error':'ROUNDTRIP_PROOF_FAILED unexpected','cancel-log':'xcodebuild cancelled unexpectedly','timeout-log':'operation timed out','wrong-nserror':'unknown'}
     if mode in extras:out=out.replace(d.IMPORT_ERROR,d.IMPORT_ERROR+' unrelated') if mode=='wrong-nserror' else out+'\n'+extras[mode]+'\n'
     if mode=='summary-mismatch':s['devicesAndConfigurations'][0]['device']['osBuildNumber']='26A428'
     pending.update(summary=s,raws=raws);code=None if mode=='unfinalized' else 65
    elif args[:4]==['xcrun','xcresulttool','get','test-results']:out=json.dumps(pending['summary'])
    elif args[:4]==['xcrun','xcresulttool','export','attachments']:
     output=Path(args[-1]);output.mkdir();manifest=helper.records(output,pending['raws'],pending['summary']);(output/'manifest.json').write_bytes(d.encoded(manifest));out='mock exported only fixture attachments'
    else:out='mock success\n'
    return subprocess.CompletedProcess(args,code,out,'')
   cwd=Path.cwd()
   try:
    os.chdir(ROOT)
    with patch.object(d,'owned_read',side_effect=read),patch.object(d,'admit_source',return_value=before),patch.object(d,'source_snapshot',return_value=({},binding)),patch.object(d,'build_identity',return_value={'app':{'path':'/owned/app','bytes':1,'sha256':'e'*64}}),patch.object(d,'run',side_effect=run),patch.object(d.time,'monotonic',side_effect=lambda:tick(mono)),patch.object(d.time,'time',side_effect=lambda:tick(wall)),patch.object(d.os,'uname',return_value=type('U',(),{'machine':'arm64'})()),patch.dict(os.environ,{'RUNNER_TEMP':str(temp)}),patch('builtins.print'):
     self.assertEqual(d.main(),1)
   finally:os.chdir(cwd)
   output=temp/'celluloid-photos-roundtrip-evidence';files={path.name:path.read_bytes() for path in output.iterdir()}
   return commands,d.load_json(files['run.json']),files
 def test_finalized_exact_failure_exports_only_readonly_evidence_and_stays_failed(self):
  commands,report,files=self.exercise('known')
  self.assertEqual([event['stage'] for event in report['events']][-3:],['single-case','import-summary','import-attachments'])
  self.assertEqual(report['stage'],'completed-import-selection-observation-failed');self.assertTrue(report['import_observation_complete'])
  self.assertFalse(report['diagnostic_complete']);self.assertFalse(report['pixel_contract_passed']);self.assertFalse(report['import_action_performed'])
  self.assertEqual({name for name in files if name in d.IMPORT_NAMES},set(d.IMPORT_NAMES))
  self.assertNotIn('photos-original.jpg',files);self.assertNotIn('photos-roundtrip.png',files)
  export=commands[-1];self.assertEqual(export[export.index('--test-id')+1],'test://com.apple.xcode/CelluloidPhotosRoundtrip/'+d.SELECTION)
  self.assertFalse(report['temporary_export_admission']['during_export_hard_quota'])
 def test_unfinalized_timeout_cancel_denial_unknown_failure_never_dispatches_summary(self):
  for mode in ('unfinalized','timeout','cancelled','denied','wrong-failure','missing-terminal','top-error','permission-error','proof-error','cancel-log','timeout-log','wrong-nserror'):
   with self.subTest(mode=mode):
    commands,report,files=self.exercise(mode)
    self.assertEqual(commands[-1][-1],'test-without-building');self.assertFalse(any(row[:4] in (['xcrun','xcresulttool','get','test-results'],['xcrun','xcresulttool','export','attachments']) for row in commands))
    self.assertFalse(report['diagnostic_complete']);self.assertNotIn('import_observation_complete',report);self.assertIn('manifest.json',files)
 def test_missing_tool_capability_stops_before_build(self):
  commands,report,files=self.exercise('help-missing')
  self.assertEqual(commands[-1],['xcrun','xcresulttool','help','export','attachments'])
  self.assertFalse(any(row[0]=='xcodebuild' and '-project' in row for row in commands))
  self.assertFalse(report['diagnostic_complete'])
 def test_official_runtime_mismatch_stops_before_attachment_export(self):
  commands,report,files=self.exercise('summary-mismatch')
  self.assertEqual([event['stage'] for event in report['events']][-1],'import-summary')
  self.assertFalse(any(row[:4]==['xcrun','xcresulttool','export','attachments'] for row in commands))
  self.assertIn('runtime mismatch',report['error']);self.assertNotIn('import-panel.png',files)

class RawReplayTests(unittest.TestCase):
 def fixture(self):
  j=(ROOT/d.INPUTS['jpeg'][0]).read_bytes();p=(ROOT/d.INPUTS['historical'][0]).read_bytes();raw={'writer-committed.jpg':j,'photos-original.jpg':j,'photos-roundtrip.png':p}
  proof={'images':{n:{'bytes':len(b),'sha256':d.sha(b)} for n,b in raw.items()},'srgb_icc_reference':None,'png_rgba_sha256':d.HISTORICAL_RGBA,'max_channel_delta':3,'pixel_contract_passed':False,'historical_rgba_equal':True}
  proof['images']['photos-roundtrip.png']['rgba_sha256']=d.HISTORICAL_RGBA;return raw,proof
 def test_actual_historical_pixels_replay_four_above_two_and_strict_fail(self):
  result=d.replay(*self.fixture());self.assertFalse(result['pixel_contract_passed']);self.assertEqual(result['max_channel_histogram'],{0:518417,1:441162,2:417,3:4});self.assertTrue(result['historical_rgba_equal'])
 def test_corrupt_writer_or_original_rejected_even_rehashed(self):
  for name in ('writer-committed.jpg','photos-original.jpg'):
   raw,p=self.fixture();raw[name]=b'wrong';p['images'][name]={'bytes':5,'sha256':d.sha(b'wrong')}
   with self.assertRaisesRegex(ValueError,'exact byte'):d.replay(raw,p)
 def test_native_expected_substitution_rejected(self):
  raw,p=self.fixture();raw['photos-roundtrip.png']=(ROOT/d.INPUTS['expected'][0]).read_bytes();p['images']['photos-roundtrip.png'].update(bytes=len(raw['photos-roundtrip.png']),sha256=d.sha(raw['photos-roundtrip.png']))
  with self.assertRaises(ValueError):d.replay(raw,p)
 def test_missing_extra_oversized_or_bad_hash_rejected(self):
  for kind in ('missing','extra','large','hash'):
   raw,p=self.fixture()
   if kind=='missing':del raw['photos-original.jpg']
   elif kind=='extra':raw['other']=b'x'
   elif kind=='large':raw['writer-committed.jpg']=b'x'*131073
   else:p['images']['writer-committed.jpg']['sha256']='0'*64
   with self.subTest(kind=kind),self.assertRaises(ValueError):d.replay(raw,p)

class RunnerDenialTests(unittest.TestCase):
 def run_fault(self,actions,signal_effect=None):
  p=Mock(pid=12345,returncode=None);p.poll.return_value=None;p.communicate.side_effect=actions
  with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'RUNNER_TEMP':directory}),patch.object(runner.time,'monotonic',return_value=100),patch.object(runner.subprocess,'Popen',return_value=p),patch.object(runner.os,'killpg',side_effect=signal_effect) as signal:
   try:runner.run(['owned'],timeout=20,check=False,echo=False,log_name='out')
   except BaseException as error:return error,p,signal,list(p.communicate.call_args_list)
   raise AssertionError('Expected failure')
 def test_denied_initial_read_sends_no_signal(self):
  error,p,signal,calls=self.run_fault([PermissionError('denied')]);self.assertIsInstance(error,PermissionError);self.assertTrue(error.cleanup_unconfirmed);signal.assert_not_called();self.assertEqual(len(calls),1)
 def test_denied_term_has_no_kill_or_second_read(self):
  error,p,signal,calls=self.run_fault([subprocess.TimeoutExpired('owned',20)],PermissionError('denied'));self.assertIsInstance(error,TimeoutError);self.assertEqual(signal.call_count,1);self.assertEqual(len(calls),1)
 def test_denied_cleanup_read_has_no_kill(self):
  error,p,signal,calls=self.run_fault([subprocess.TimeoutExpired('owned',20),PermissionError('read denied')]);self.assertIsInstance(error,TimeoutError);self.assertEqual(signal.call_count,1);self.assertEqual(len(calls),2)
 def test_permitted_timeout_never_becomes_success_and_ten_plus_five(self):
  error,p,signal,calls=self.run_fault([subprocess.TimeoutExpired('owned',20),subprocess.TimeoutExpired('owned',10),('done','')]);self.assertIsInstance(error,TimeoutError);self.assertEqual([c.kwargs['timeout'] for c in calls],[20,10,5]);self.assertEqual(signal.call_count,2)

class CancellationTests(unittest.TestCase):
 def exercise(self,mode,deny=False):
  previous={sig:signal.getsignal(sig) for sig in (signal.SIGINT,signal.SIGTERM)}
  proc=Mock(pid=54321,returncode=None);proc.poll.return_value=None
  number=signal.SIGINT if mode=='sigint' else signal.SIGTERM
  def interrupt(*args,**kwargs):
   if mode=='keyboard':raise KeyboardInterrupt('caller cancelled')
   signal.getsignal(number)(number,None)
  if mode=='launch':proc.communicate.return_value=('stopped','')
  else:proc.communicate.side_effect=[interrupt,('stopped','')]
  # Mock side_effect iterators return callables, so dispatch explicitly.
  calls=[0]
  def communicate(*args,**kwargs):
   calls[0]+=1
   if calls[0]==1 and mode!='launch':interrupt()
   return ('stopped','')
  proc.communicate.side_effect=communicate
  def popen(*args,**kwargs):
   if mode=='launch':signal.getsignal(signal.SIGTERM)(signal.SIGTERM,None)
   return proc
  with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'RUNNER_TEMP':directory}),patch.object(runner.time,'monotonic',return_value=100),patch.object(runner.subprocess,'Popen',side_effect=popen),patch.object(runner.os,'killpg',side_effect=PermissionError('denied') if deny else None) as kill:
   with self.assertRaises(runner.OwnedCommandCancelled):runner.run(['owned'],timeout=20,check=False,echo=False,log_name='out')
   self.assertEqual(kill.call_count,1)
   self.assertEqual(proc.communicate.call_count,0 if mode=='launch' and deny else 1 if deny or mode=='launch' else 2)
  self.assertEqual({sig:signal.getsignal(sig) for sig in previous},previous)
 def test_sigterm_owned_cleanup_and_handler_restoration(self):self.exercise('sigterm')
 def test_sigint_owned_cleanup_and_handler_restoration(self):self.exercise('sigint')
 def test_keyboard_interrupt_owned_cleanup(self):self.exercise('keyboard')
 def test_cancel_during_popen_waits_for_owned_handle_then_stops(self):self.exercise('launch')
 def test_cancel_denied_term_never_kills_or_waits_again(self):self.exercise('sigterm',True)
 def test_launch_cancel_denied_term_never_waits(self):self.exercise('launch',True)

class DriverEarlyRuntimeTests(unittest.TestCase):
 def test_mismatch_records_actual_pair_and_stops_before_build_or_Photos(self):
  original=d.owned_read;before={'source_sha':'a'*40,'run_id':'123','run_attempt':1}
  def read(path,cap):
   if Path(path)==ROOT/d.CONFIG:return b'{"enabled":true}'
   return original(path,cap)
  commands=[]
  def run(args,**kwargs):
   commands.append(args[4:]);value='27.0\n' if args[-1]=='-productVersion' else '26A428\n'
   return subprocess.CompletedProcess(args,0,value,'')
  with tempfile.TemporaryDirectory() as folder:
   temp=Path(folder).resolve(strict=True);(temp/'mac-job-clock.json').write_bytes(d.encoded({'source_sha':'a'*40,'execution_budget_seconds':2460,'started_monotonic':100.0,'started_unix':1000.0}))
   cwd=Path.cwd()
   try:
    os.chdir(ROOT)
    with patch.object(d,'owned_read',side_effect=read),patch.object(d,'admit_source',return_value=before),patch.object(d,'run',side_effect=run),patch.object(d.time,'monotonic',return_value=101.0),patch.object(d.os,'uname',return_value=type('U',(),{'machine':'arm64'})()),patch.dict(os.environ,{'RUNNER_TEMP':str(temp)}),patch('builtins.print'):
     self.assertEqual(d.main(),1)
   finally:os.chdir(cwd)
   self.assertEqual(commands,[['/usr/bin/sw_vers','-productVersion'],['/usr/bin/sw_vers','-buildVersion']])
   report=d.load_json((temp/'celluloid-photos-roundtrip-evidence/run.json').read_bytes())
   self.assertEqual(report['runtime_observation']['osBuildNumber'],'26A428');self.assertFalse(report['diagnostic_complete']);self.assertEqual(report['stage'],'runtime-preflight')

class AttachmentTests(unittest.TestCase):
 def fixture(self,folder):
  device={'deviceId':'owned','deviceName':'My Mac'};summary={'startTime':100,'finishTime':200};rows=[]
  for i,name in enumerate(d.NAMES):
   ext=Path(name).suffix;exported=str(i)+ext;(folder/exported).write_bytes(b'owned'+bytes([i]))
   rows.append({'suggestedHumanReadableName':'celluloid-roundtrip-'+Path(name).stem+'_0_00000000-0000-0000-0000-000000000000'+ext,'exportedFileName':exported,'deviceId':'owned','deviceName':'My Mac','configurationName':'Test Scheme Action','timestamp':150})
  record={'testIdentifier':'MacPhotosRoundtripTests/testOwnedWriterJPEGPhotosRoundtrip()','testIdentifierURL':'test://com.apple.xcode/CelluloidPhotosRoundtrip/'+d.SELECTION,'attachments':rows}
  return [record],device,summary
 def test_fixed_three_observed_attachments(self):
  with tempfile.TemporaryDirectory() as path:
   folder=Path(path).resolve(strict=True);manifest,device,summary=self.fixture(folder);self.assertEqual(set(d.attachments(folder,manifest,device,summary)),set(d.NAMES))
 def test_stale_wrong_case_device_path_duplicate_timestamp_rejected(self):
  for field,value in [('testIdentifier','Other/testWrong()'),('deviceId','other'),('timestamp',201),('exportedFileName','../foreign'),('suggestedHumanReadableName','celluloid-roundtrip-other_0_00000000-0000-0000-0000-000000000000.jpg')]:
   with tempfile.TemporaryDirectory() as path:
    folder=Path(path).resolve(strict=True);manifest,device,summary=self.fixture(folder)
    if field=='testIdentifier':manifest[0][field]=value
    else:manifest[0]['attachments'][0][field]=value
    with self.subTest(field=field),self.assertRaises(ValueError):d.attachments(folder,manifest,device,summary)
  with tempfile.TemporaryDirectory() as path:
   folder=Path(path).resolve(strict=True);manifest,device,summary=self.fixture(folder);manifest[0]['attachments'].append(manifest[0]['attachments'][0])
   with self.assertRaises(ValueError):d.attachments(folder,manifest,device,summary)
 def test_symlink_and_extra_named_attachment_rejected(self):
  with tempfile.TemporaryDirectory() as path:
   folder=Path(path).resolve(strict=True);manifest,device,summary=self.fixture(folder);(folder/'0.jpg').unlink();(folder/'0.jpg').symlink_to(folder/'1.jpg')
   with self.assertRaises(ValueError):d.attachments(folder,manifest,device,summary)

if __name__=='__main__':unittest.main()
