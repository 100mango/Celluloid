#!/usr/bin/env python3
"""Site-free route, fixture, single-case and native ownership regressions."""
import contextlib,io,ast,copy,hashlib,importlib.util,json,os,re,shutil,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
SOURCE_ROOT=Path(os.environ.get('CELLULOID_QUALIFICATION_SOURCE_ROOT',HERE.parent)).resolve()
sys.path.insert(0,str(SOURCE_ROOT/'Scripts'));sys.path.insert(0,str(HERE))
import final_vision_wave as w
import qualify_final_vision_wave_source as g

def env(method=None):return {'GITHUB_SHA':'a'*40,'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1','VISION_WAVE_METHOD':method or w.UI_METHODS[1],'QUALIFICATION_PLATFORM':'vision'}
def config(method=None):return {'schema':1,'READY':True,'platform':'vision','product_parent_sha':w.SOURCE,'product_parent_tree':w.TREE,'maximum_additional_spend_usd':0,'confirmation':'RUN_ONE_UNSIGNED_PLATFORM_ZERO_USD','selected_method':method or w.UI_METHODS[1]}
def clock():
 e=env();return {'schema':'Celluloid.FinalVisionWaveClock.1','control_sha':e['GITHUB_SHA'],'run_id':'123','run_attempt':'1','selected_method':e['VISION_WAVE_METHOD'],'started_monotonic':time.monotonic(),'started_unix':time.time(),'native_seconds':1560,'final_seconds':1740}
def summary():return {'totalTestCount':1,'passedTests':1,'failedTests':0,'skippedTests':0,'testFailures':[],'expectedFailures':0}
def caselog(method,status='passed',kind='ui'):
 owner='CelluloidVisionUITests.NativeVisionUITests' if kind=='ui' else 'CelluloidVisionTests.NativeVisionTests'
 return f"Test Case '-[{owner} {method}]' started.\nTest Case '-[{owner} {method}]' {status} (1.000 seconds).\n"
# Observe only this fixed real process self-test. No output, arguments or env
# are copied; the actual helper, signals, exceptions and deadlines are unchanged.
PROCESS_RESULT_FIELDS=('return_code','bytes_read','pipe_eof','child_reaped','timed_out','overflow','cleanup_error','finalized','elapsed_seconds','command_deadline_monotonic','cleanup_deadline_monotonic')
def selftest_outcome_projection(result):
 w.need(type(result) is dict and set(result)==set(PROCESS_RESULT_FIELDS)|{'output'},'selftest result schema')
 return {k:result[k] for k in PROCESS_RESULT_FIELDS}

# Fixed owned child stays live through TERM under healthy timing; late/denied cleanup still fails.
# The alarm is armed before writing (which may block); it does not renew parent deadlines.
OUTPUT_CAP_CHILD='import signal,time\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\nsignal.signal(signal.SIGALRM,signal.SIG_DFL)\nsignal.pthread_sigmask(signal.SIG_UNBLOCK,{signal.SIGALRM})\nsignal.setitimer(signal.ITIMER_REAL,10.0)\nprint("x"*16384,flush=True)\ntime.sleep(10.0)\n'

def observed_selftest_process(scenario,cap):
 need=w.need;need(scenario in ('success','output-cap'),'selftest scenario')
 start=time.monotonic();operations=[];result=None;exception=None
 mode='optimized' if sys.flags.optimize else 'normal'
 identity={'schema':'Celluloid.VisionControlProcessReceipt.1','mode':mode,'scenario':scenario,'python_version':list(sys.version_info[:3]),'started_monotonic':start,'command_deadline_monotonic':start+3,'cleanup_deadline_monotonic':start+4,'cap':cap}
 # BEGIN is invocation intent, not proof that Popen returned or its child started.
 print('VISION_WAVE_CONTROL_PROCESS '+json.dumps({**identity,'phase':'BEGIN'},sort_keys=True),flush=True)
 original_popen=w.subprocess.Popen;original_signal=w.os.killpg
 with contextlib.ExitStack() as stack:
  def observed_wait(wait,timeout):
   began=time.monotonic();error=None
   try:return wait(timeout=timeout)
   except BaseException as e:error=type(e).__name__;raise
   finally:operations.append({'operation':'wait','started_monotonic':began,'finished_monotonic':time.monotonic(),'timeout':timeout,'exception':error})
  def popen(*args,**kwargs):
   began=time.monotonic();error=None
   try:
    process=original_popen(*args,**kwargs);wait=process.wait
    stack.enter_context(patch.object(process,'wait',side_effect=lambda timeout=None:observed_wait(wait,timeout)))
    return process
   except BaseException as e:error=type(e).__name__;raise
   finally:operations.append({'operation':'Popen','started_monotonic':began,'finished_monotonic':time.monotonic(),'exception':error})
  def signal_group(pid,sig):
   began=time.monotonic();error=None;errno=None
   try:return original_signal(pid,sig)
   except BaseException as e:error=type(e).__name__;errno=getattr(e,'errno',None);raise
   finally:operations.append({'operation':'killpg','signal':'SIGTERM' if sig==w.signal.SIGTERM else 'SIGKILL' if sig==w.signal.SIGKILL else 'unexpected','started_monotonic':began,'finished_monotonic':time.monotonic(),'exception':error,'errno':errno})
  stack.enter_context(patch.object(w.subprocess,'Popen',side_effect=popen));stack.enter_context(patch.object(w.os,'killpg',side_effect=signal_group))
  try:
   code='print("owned")' if scenario=='success' else OUTPUT_CAP_CHILD
   result=w.bounded_optional_process([sys.executable,'-B','-S','-c',code],start+3,start+4,cap=cap,stop_on_signal_error=True)
   return result
  except BaseException as e:exception=type(e).__name__;raise
  finally:
   safe=None if result is None else selftest_outcome_projection(result)
   receipt={**identity,'phase':'END','finished_monotonic':time.monotonic(),'result':safe,'exception':exception,'operations':operations}
   raw=json.dumps(receipt,sort_keys=True,allow_nan=False);need(len(raw.encode())<=4096,'selftest receipt cap')
   print('VISION_WAVE_CONTROL_PROCESS '+raw,flush=True)
   # A fixed, exclusive, small receipt only on the actual workflow runner.
   if os.environ.get('RUNNER_TEMP') and os.environ.get('GITHUB_RUN_ID'):
    receipt.update(control_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],run_attempt=os.environ['GITHUB_RUN_ATTEMPT'])
    raw=(json.dumps(receipt,sort_keys=True,allow_nan=False)+'\n').encode();need(len(raw)<=4096,'selftest retained receipt cap')
    destination=Path(os.environ['RUNNER_TEMP']).resolve(strict=True)/('vision-wave-selftest-'+mode+'-'+scenario+'.json')
    fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as output:output.write(raw)

def safe_selftest_result(result):
 return json.dumps(selftest_outcome_projection(result),sort_keys=True,allow_nan=False)

class WaveTests(unittest.TestCase):
 def test_exact_single_method_config_and_closed_default(self):
  for m in w.UI_METHODS:self.assertEqual(w.validate_config(config(m),env(m))['selected_method'],m)
  c=config();c['READY']=False
  with self.assertRaises(ValueError):w.validate_config(c,env())
 def test_config_mutations_rejected(self):
  for k in config():
   c=config();c[k]='wrong'
   with self.subTest(k=k),self.assertRaises(ValueError):w.validate_config(c,env())
  with self.assertRaises(ValueError):w.validate_config({**config(),'timeout':1800},env())
  with self.assertRaises(ValueError):w.validate_config(config(),{**env(),'GITHUB_RUN_ATTEMPT':'2'})
 def test_no_bool_spend_or_selection_mismatch(self):
  with self.assertRaises(ValueError):w.validate_config({**config(),'maximum_additional_spend_usd':False},env())
  with self.assertRaises(ValueError):w.validate_config(config(),env(w.UI_METHODS[0]))
 def test_only_seeded_ui_requires_hosted_producer(self):
  for m in w.UI_METHODS:
   selections=w.selectors_for(m);self.assertEqual(selections['ui'],['-only-testing:CelluloidVisionUITests/NativeVisionUITests/'+m])
   self.assertEqual(bool(selections['producer']),m==w.UI_METHODS[2])
   if selections['producer']:self.assertEqual(selections['producer'],['-only-testing:CelluloidVisionTests/NativeVisionTests/'+w.PRODUCER])
 def test_clock_identity_and_unchanged_thirty_minute_budget(self):
  c=clock();self.assertEqual(w.validate_clock(c,env()),c);self.assertLess(c['final_seconds'],1800)
  for k in c:
   changed={**c,k:'wrong'}
   with self.subTest(k=k),self.assertRaises((ValueError,TypeError)):w.validate_clock(changed,env())
 def test_full_ui_window_admission_reserves_cleanup_and_tail(self):
  c=clock();s=c['started_monotonic'];last=s+1560-120-w.FIXTURE_READ_SECONDS-915
  self.assertEqual(w.admit_ui(c,last),s+1440-w.FIXTURE_READ_SECONDS)
  with self.assertRaisesRegex(ValueError,'does-not-fit'):w.admit_ui(c,last+.001)
 def test_case_exact_once_pass_and_no_skip(self):
  m=w.UI_METHODS[2];self.assertTrue(w.inspect_case(caselog(m),m,summary())['passed'])
  for text in [caselog(m,'failed'),caselog(m,'skipped'),caselog(m)*2,caselog(m).splitlines()[0],caselog(w.UI_METHODS[0])]:
   with self.subTest(text=text),self.assertRaises(ValueError):w.inspect_case(text,m,summary())
 def test_summary_mismatch_and_unexpected_failures_rejected(self):
  m=w.UI_METHODS[0]
  for k in ['totalTestCount','passedTests','failedTests','skippedTests','expectedFailures','testFailures']:
   s=summary();s[k]=2 if k!='testFailures' else ['failure']
   with self.subTest(k=k),self.assertRaises(ValueError):w.inspect_case(caselog(m),m,s)
 def test_actual_summary_device_binding(self):
  m=w.UI_METHODS[0];s=summary();s['devicesAndConfigurations']=[{'device':{'deviceId':'uuid','osVersion':'27.0','architecture':'arm64','platform':'visionOS Simulator'},'passedTests':1,'failedTests':0,'skippedTests':0}]
  self.assertTrue(w.inspect_case(caselog(m),m,s,udid='uuid',runtime_version='27.0')['passed'])
  with self.assertRaises(ValueError):w.inspect_case(caselog(m),m,s,udid='other',runtime_version='27.0')
 def test_unchanged_declared_eight_cases_and_cold_chinese_capture(self):
  d=w.validate_inventory(SOURCE_ROOT);self.assertEqual(len(d),2)
  source=(SOURCE_ROOT/'Platforms/VisionUITests/NativeVisionUITests.swift').read_text()
  self.assertIn('let capture = XCTAttachment(screenshot: app.screenshot()); capture.name = "native-vision-launch"; capture.lifetime = .keepAlways; add(capture)\n        try openEditor(in:app)',source)
  self.assertIn('["-AppleLanguages", "(zh-Hans)", "-AppleLocale", "zh_CN"]',source)
  self.assertEqual(source.count('performAccessibilityAudit'),3);self.assertIn('fatalError("CELLULOID_NATIVE_UI_FAIL_CLOSED_ABORT',source)
 def test_unique_whole_case_command_no_other_testing(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);m=w.UI_METHODS[3];cmd=w.xctest_command(p,'own-device',p/'unique.xcresult',w.selectors_for(m)['ui'])
   self.assertEqual([s for s in cmd if s.startswith('-only-testing:')],w.selectors_for(m)['ui']);self.assertFalse(any(s.startswith('-skip-testing') for s in cmd));self.assertEqual(cmd[-1],'test-without-building');self.assertIn('CODE_SIGNING_ALLOWED=NO',cmd)
 def test_safe_reader_rejects_parent_symlink_file_link_and_hardlink(self):
  with tempfile.TemporaryDirectory() as t:
   r=Path(t).resolve();p=r/'data';p.write_bytes(b'abc');self.assertEqual(w.safe_read(p,10),b'abc')
   for name,setup in [('symbolic',lambda q:q.symlink_to(p)),('hard',lambda q:os.link(p,q))]:
    q=r/name;setup(q)
    with self.assertRaises((ValueError,OSError)):w.safe_read(q,10)
    q.unlink()
   (r/'alias').symlink_to(r,target_is_directory=True)
   with self.assertRaises((ValueError,OSError)):w.safe_read(r/'alias/data',10)
 def test_png_is_original_algorithm_and_collision_fails(self):
  with tempfile.TemporaryDirectory() as t:
   r=Path(t).resolve();result=w.seed_png(r);b=(r/'Documents/VisionSynthetic.png').read_bytes();self.assertEqual(w.digest(b),result['sha256']);self.assertTrue(b.startswith(b'\x89PNG'));self.assertEqual((result['width'],result['height']),(1200,800))
   with self.assertRaises(FileExistsError):w.seed_png(r)
 def fixture(self,root):
  folder=root/'Documents/VisionRemaining.celluloid';folder.mkdir(parents=True);rows=[]
  for name,b in [('recipe.json',b'{}'),('00000000-0000-0000-0000-000000000001.image',b'fixture')]:
   (folder/name).write_bytes(b);rows.append({'name':name,'bytes':len(b),'sha256':w.digest(b)})
  v={'schema':'Celluloid.VisionFixture.1','bundle_identifier':'Mango.Celluloid','data_home':str(root),'documents_path':str(root/'Documents'),'package_path':str(folder),'package_name':'VisionRemaining.celluloid','pixel_width':120,'pixel_height':80,'initial_overlays':0,'files':rows}
  return v
 def test_producer_exact_current_container_and_file_hashes(self):
  with tempfile.TemporaryDirectory() as t:
   r=Path(t).resolve();v=self.fixture(r);log='VISION_REMAINING_FIXTURE_JSON '+json.dumps(v)
   self.assertEqual(w.verify_producer(log,r),v)
   (r/'Documents/VisionRemaining.celluloid/recipe.json').write_bytes(b'changed')
   with self.assertRaises(ValueError):w.verify_producer(log,r)
 def test_producer_stale_duplicate_and_extra_files_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   r=Path(t).resolve();v=self.fixture(r);log='VISION_REMAINING_FIXTURE_JSON '+json.dumps(v)
   with self.assertRaises(ValueError):w.verify_producer(log+'\n'+log,r)
   changed={**v,'data_home':str(r.parent)}
   with self.assertRaises(ValueError):w.verify_producer('VISION_REMAINING_FIXTURE_JSON '+json.dumps(changed),r)
   (r/'Documents/VisionRemaining.celluloid/extra').write_text('x')
   with self.assertRaises(ValueError):w.verify_producer(log,r)
 def test_attachment_owner_and_named_screenshots_are_exact(self):
  with tempfile.TemporaryDirectory() as t:
   r=Path(t).resolve();(r/'a.png').write_bytes(b'\x89PNG\r\n\x1a\nfixture');m=w.UI_METHODS[0]
   record=[{'testIdentifier':'NativeVisionUITests/'+m+'()','attachments':[{'suggestedHumanReadableName':'native-vision-launch_0_id.png','exportedFileName':'a.png'}]}]
   self.assertEqual(set(w.exported_images(r,record,m)),{'native-vision-launch'})
   record[0]['testIdentifier']='Wrong/test()'
   with self.assertRaises(ValueError):w.exported_images(r,record,m)
 def test_attachment_traversal_duplicate_and_symlink_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   r=Path(t).resolve();(r/'a.png').write_bytes(b'\x89PNG\r\n\x1a\nfixture');m=w.UI_METHODS[0]
   row={'testIdentifier':'NativeVisionUITests/'+m+'()','attachments':[{'suggestedHumanReadableName':'native-vision-launch','exportedFileName':'../a.png'}]}
   with self.assertRaises(ValueError):w.exported_images(r,[row],m)
   row['attachments'][0]['exportedFileName']='a.png';row['attachments']*=2
   with self.assertRaises(ValueError):w.exported_images(r,[row],m)
 def test_process_helper_reuses_reviewed_body_exactly(self):
  original=(SOURCE_ROOT/'Scripts/mac_owned_crash.py').read_text();original=original[original.index('def bounded_optional_process('):original.index('\ndef framework_dependencies(')]
  actual=Path(w.__file__).read_text();actual=actual[actual.index('def bounded_optional_process('):actual.index('\n# All time')]
  self.assertEqual(ast.dump(ast.parse(actual)),ast.dump(ast.parse(original.replace('0<cap<=8192','0<cap<=1048576'))))
 def test_real_owned_process_success_and_output_cap(self):
  r=observed_selftest_process('success',8192);details=safe_selftest_result(r);self.assertTrue(r['finalized'],details);self.assertEqual(r['output'],b'owned\n',details)
  r=observed_selftest_process('output-cap',1024);details=safe_selftest_result(r);self.assertTrue(r['overflow'],details);self.assertLessEqual(r['bytes_read'],1024,details);self.assertTrue(r['output']==b'x'*1024,details);self.assertTrue(r['child_reaped'],details);self.assertIsNone(r['cleanup_error'],details);self.assertEqual(r['return_code'],-w.signal.SIGKILL,details);self.assertFalse(r['finalized'],details)
 def test_uncertain_or_timedout_process_blocks_every_later_native_dispatch(self):
  for result in [{'output':b'partial','finalized':False,'timed_out':True,'overflow':False,'return_code':None},{'output':b'partial','finalized':True,'timed_out':True,'overflow':False,'return_code':-15}]:
   with tempfile.TemporaryDirectory() as t:
    commands=w.VisionCommands(Path(t))
    with patch.object(w,'bounded_optional_process',return_value=result) as run:
     for label in ['first','second']:
      with self.assertRaises(ValueError):commands.run(['fake'],label,deadline=time.monotonic()+30,seconds=20)
     self.assertEqual(run.call_count,1)
 def test_helper_exception_blocks_later_commands(self):
  with tempfile.TemporaryDirectory() as t:
   commands=w.VisionCommands(Path(t))
   with patch.object(w,'bounded_optional_process',side_effect=RuntimeError('unknown')) as run:
    with self.assertRaises(RuntimeError):commands.run(['fake'],'first',deadline=time.monotonic()+30,seconds=20)
    with self.assertRaises(ValueError):commands.run(['fake'],'second',deadline=time.monotonic()+30,seconds=20)
    self.assertEqual(run.call_count,1)
 def test_source_gate_identity_selection_and_history(self):
  c={**config(),'repository':'100mango/Celluloid','event':'push','ref':'refs/heads/'+g.BRANCH,'workflow_ref':'100mango/Celluloid/'+g.WORKFLOW+'@refs/heads/'+g.BRANCH,'workflow_platform':'vision','workflow_selected_method':config()['selected_method'],'run_attempt':'1','github_sha':'a'*40,'workflow_sha':'a'*40}
  f={'head':'a'*40,'tree':'b'*40,'chain':[{'sha':'a'*40,'parents':[g.SOURCE],'changed_paths':sorted(g.QUALIFICATION_PATHS)}],'parent_tree':g.TREE,'changed_paths':sorted(g.QUALIFICATION_PATHS),'dirty':''}
  self.assertEqual(g.validate(c,f,enabled=True)['selected_method'],c['selected_method'])
  for key in ['product_parent_sha','product_parent_tree','selected_method','workflow_selected_method','ref','workflow_sha','run_attempt']:
   with self.subTest(key=key),self.assertRaises(ValueError):g.validate({**c,key:'wrong'},f,enabled=True)
  f['chain'][0]['changed_paths'].append('Platforms/Shared/EditorView.swift')
  with self.assertRaisesRegex(ValueError,'Product mutation'):g.validate(c,f,enabled=True)
 def test_strict_json_duplicate_and_nonfinite_rejected(self):
  for raw in ['{"a":1,"a":2}','{"v":NaN}']:
   with self.assertRaises(ValueError):w.strict_json(raw)
 def test_complete_synthetic_driver_each_method_selects_only_actual_dependency(self):
  original_cwd=Path.cwd()
  for method in w.UI_METHODS:
   with self.subTest(method=method),tempfile.TemporaryDirectory() as t:
    root=Path(t).resolve();repo=root/'repo';repo.mkdir();temp=root/'temp';temp.mkdir();container=root/'container';container.mkdir()
    (repo/'.github').mkdir();(repo/w.CONFIG).write_text(json.dumps(config(method)));e={**env(method),'RUNNER_TEMP':str(temp)}
    c=clock();c['selected_method']=method;(temp/w.CLOCK).write_text(json.dumps(c));called=[];owner=self
    uid='00000000-0000-0000-0000-000000000123'
    class FakeCommands:
     def __init__(self,folder):self.temp=folder;self.events=[];self.blocked=False
     def run(self,argv,label,**kwargs):
      argv=list(map(str,argv));called.append((argv,kwargs));out='';result={'return_code':0,'finalized':True,'timed_out':False,'overflow':False}
      if argv==['xcodebuild','-version']:out='Xcode 27.0\nBuild version 27A266a\n'
      elif argv[:4]==['xcrun','simctl','list','runtimes']:out=json.dumps({'runtimes':[{'isAvailable':True,'version':'27.0','name':'visionOS 27.0','identifier':'xros27'}]})
      elif argv[:4]==['xcrun','simctl','list','devicetypes']:out=json.dumps({'devicetypes':[{'name':'Apple Vision Pro','identifier':'device'}]})
      elif argv[:3]==['xcrun','simctl','create']:out=uid
      elif argv[:3]==['xcrun','simctl','get_app_container']:out=str(container)
      elif argv[:3]==['xcrun','simctl','launch']:out='Mango.Celluloid: 1234'
      elif argv[:2]==['ps','-p']:out='1234 /synthetic/CelluloidVision.app/CelluloidVision'
      elif argv[:3]==['xcrun','simctl','io']:Path(argv[-1]).write_bytes(b'\xff\xd8\xffsynthetic')
      elif 'test-without-building' in argv:
       Path(argv[argv.index('-resultBundlePath')+1]).mkdir()
       if 'producer-tests' in label:
        fixture=owner.fixture(container);out=caselog(w.PRODUCER,kind='producer')+'VISION_REMAINING_FIXTURE_JSON '+json.dumps(fixture)+'\n'
       else:
        out=caselog(method)
        if method==w.FILES_METHOD:
         fixture_marker={'schema':'Celluloid.VisionFilesFixture.1','document_name':'Untitled','layer_identifier':'layer.00000000-0000-0000-0000-000000000001'}
         model_marker={**fixture_marker,'schema':'Celluloid.VisionFilesModel.1','stage':'post-redo','expected_text':'Vision 世界','matched':True,'actual_label':'Select layer: Vision 世界'}
         out+='VISION_FILES_FIXTURE_JSON '+json.dumps(fixture_marker)+'\nVISION_FILES_MODEL_JSON '+json.dumps(model_marker)+'\n'
      elif argv[:5]==['xcrun','xcresulttool','get','test-results','summary']:
       ss=summary();ss['devicesAndConfigurations']=[{'device':{'deviceId':uid,'osVersion':'27.0','architecture':'arm64','platform':'visionOS Simulator'},'passedTests':1,'failedTests':0,'skippedTests':0}];out=json.dumps(ss)
      elif argv[:4]==['xcrun','xcresulttool','export','attachments']:
       folder=Path(argv[-1]);folder.mkdir();items=[]
       for i,name in enumerate(w.SHOTS[method]):
        filename=str(i)+'.png';(folder/filename).write_bytes(b'\x89PNG\r\n\x1a\nfixture');items.append({'suggestedHumanReadableName':name+'_0_id.png','exportedFileName':filename})
       (folder/'manifest.json').write_text(json.dumps([{'testIdentifier':'NativeVisionUITests/'+method+'()','attachments':items}]))
      raw=out.encode();path=self.temp/(label+'.log');path.write_bytes(raw);self.events.append({'label':label,'log':path.name,'log_bytes':len(raw),'log_sha256':w.digest(raw),**result})
      return out,result
    try:
     with contextlib.redirect_stdout(io.StringIO()),patch.object(w,'ROOT',repo),patch.object(w,'VisionCommands',FakeCommands),patch.object(w,'validate_inventory',return_value={'synthetic':'source'}),patch.object(w.time,'sleep'),patch.object(w,'capture_initial_fixture',return_value={'synthetic':True}),patch.object(w,'read_fixture',return_value={'status':'captured','expected_layer_present':True,'expected_text_matches':True,'save_completion_proven':False}):report=w.execute(e)
    finally:os.chdir(original_cwd)
    self.assertTrue(report['wave_qualified'],report['errors']);self.assertFalse(report['all_eight_qualified']);self.assertEqual(report['omitted_ui_methods'],[m for m in w.UI_METHODS if m!=method])
    tests=[(a,k) for a,k in called if 'test-without-building' in a];self.assertEqual(len(tests),2 if method==w.UI_METHODS[2] else 1)
    ui=[(a,k) for a,k in tests if w.selectors_for(method)['ui'][0] in a];self.assertEqual(len(ui),1);self.assertEqual(ui[0][1]['seconds'],915);self.assertTrue(ui[0][1]['full'])
    self.assertEqual((container/'Documents/VisionSynthetic.png').exists(),method==w.UI_METHODS[1]);self.assertEqual('producer_fixture' in report,method==w.UI_METHODS[2])
    self.assertFalse(any('archive' in a for a,k in called))
    binding={'source_sha':e['GITHUB_SHA'],'product_parent_sha':w.SOURCE,'selected_method':method,'file_count':961}
    for phase in ['before','after']:(temp/('combined-source-'+phase+'.json')).write_text(json.dumps({**binding,'phase':phase}))
    e['GITHUB_OUTPUT']=str(temp/'github-output')
    with patch.dict(os.environ,e):retained=w.collect(e)
    self.assertTrue(retained['wave_qualified']);self.assertTrue((temp/'vision-wave-evidence/report.json').is_file());self.assertLessEqual(sum(p.stat().st_size for p in (temp/'vision-wave-evidence').iterdir()),w.MAX_EVIDENCE)
 def test_real_git_shallow_workflow_topology_and_separate_parent_trap(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t).resolve();origin=root/'origin';origin.mkdir()
   def git(where,*args,input=None):return subprocess.check_output(['git',*args],cwd=where,input=input,text=True,stderr=subprocess.STDOUT).strip()
   git(origin,'init','-q');git(origin,'config','user.name','Synthetic test');git(origin,'config','user.email','synthetic@invalid');(origin/'product.txt').write_text('fixed fixture product');original_test=origin/g.DIAGNOSTIC_TEST;original_test.parent.mkdir(parents=True);original_test.write_bytes(g.verify_diagnostic_test((HERE.parent/g.DIAGNOSTIC_TEST).read_bytes()));git(origin,'add','.');tree=git(origin,'write-tree');parent=None
   for n in range(66):
    args=['commit-tree',tree]+(['-p',parent] if parent else []);parent=git(origin,*args,input='synthetic ancestor '+str(n)+'\n')
   product=parent;git(origin,'update-ref','refs/heads/'+g.BRANCH,product);git(origin,'symbolic-ref','HEAD','refs/heads/'+g.BRANCH)
   for rel in g.QUALIFICATION_PATHS:
    dest=origin/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(HERE.parent/rel,dest)
   gatepath=origin/'Scripts/qualify_final_vision_wave_source.py';gatepath.write_text(gatepath.read_text().replace(g.SOURCE,product).replace(g.TREE,tree).replace('UNCHANGED_ORIGINAL_FILE_COUNT = 961','UNCHANGED_ORIGINAL_FILE_COUNT = 1'))
   fixture_config={**config(),'product_parent_sha':product,'product_parent_tree':tree};(origin/g.CONFIG).write_text(json.dumps(fixture_config));git(origin,'add','.');git(origin,'commit','-qm','synthetic control');head=git(origin,'rev-parse','HEAD')
   for depth,expect in [(64,True),(2,True),(1,False)]:
    clone=root/('depth'+str(depth));git(root,'clone','-q','--depth',str(depth),'--branch',g.BRANCH,origin.as_uri(),str(clone));self.assertEqual(git(clone,'rev-parse','--is-shallow-repository'),'true')
    if depth==1:git(clone,'fetch','-q','--depth','1','origin',product)
    temp=root/('temp'+str(depth));temp.mkdir()
    e={**os.environ,**env(),'GITHUB_SHA':head,'GITHUB_WORKFLOW_SHA':head,'GITHUB_REPOSITORY':'100mango/Celluloid','GITHUB_EVENT_NAME':'push','GITHUB_REF':'refs/heads/'+g.BRANCH,'GITHUB_WORKFLOW_REF':'100mango/Celluloid/'+g.WORKFLOW+'@refs/heads/'+g.BRANCH,'RUNNER_TEMP':str(temp),'PYTHONDONTWRITEBYTECODE':'1'}
    command=[sys.executable,'-B','-S',*(['-O'] if sys.flags.optimize else []),str(clone/'Scripts/qualify_final_vision_wave_source.py')]
    result=subprocess.run(command+['--phase','before'],env=e,text=True,capture_output=True);self.assertEqual(result.returncode==0,expect,(depth,result.stdout,result.stderr))
    if expect:
     result=subprocess.run(command+['--phase','after'],env=e,text=True,capture_output=True);self.assertEqual(result.returncode,0,result.stderr)
     receipt=json.loads((temp/'combined-source-after.json').read_text());self.assertEqual(receipt['control_commit_count'],1);self.assertEqual(receipt['product_parent_sha'],product)
    else:self.assertEqual(len(git(clone,'rev-list','--parents','-n','1','HEAD').split()),1)
 def test_collection_preserves_failed_proof_when_required_image_exceeds_cap(self):
  with tempfile.TemporaryDirectory() as t:
   temp=Path(t).resolve();method=w.UI_METHODS[0];e={**env(method),'RUNNER_TEMP':str(temp),'GITHUB_OUTPUT':str(temp/'output')};c=clock();c['selected_method']=method
   folder=temp/'vision-wave-1-123-1-attachments';folder.mkdir();image=folder/'big.png';raw=b'\x89PNG\r\n\x1a\n'+b'x'*2400000;image.write_bytes(raw)
   report={'schema':'Celluloid.FinalVisionSingleMethodWave.1','test_diagnostics':{'path':w.DIAGNOSTIC_TEST,'sha256':w.DIAGNOSTIC_TEST_SHA256,'inverse_original_sha256':w.ORIGINAL_TEST_SHA256,'unchanged_original_files':961,'product_compiled_inputs_unchanged':True},'control_sha':e['GITHUB_SHA'],'product_sha':w.SOURCE,'product_tree':w.TREE,'run_id':'123','run_attempt':'1','selected_method':method,'omitted_ui_methods':[m for m in w.UI_METHODS if m!=method],'original_hosted_inventory':list(w.HOSTED),'original_ui_inventory':list(w.UI_METHODS),'ui_limit_seconds':900,'all_eight_qualified':False,'archive_qualified':False,'clock':c,'screenshots':{'native-vision-launch':{'source':str(image),'bytes':len(raw),'sha256':w.digest(raw),'extension':'.png'}},'commands':[],'selected_method_passed':False,'wave_qualified':False,'errors':['synthetic failed method']}
   (temp/'vision-wave-report.json').write_text(json.dumps(report));binding={'source_sha':e['GITHUB_SHA'],'product_parent_sha':w.SOURCE,'selected_method':method}
   for phase in ['before','after']:(temp/('combined-source-'+phase+'.json')).write_text(json.dumps({**binding,'phase':phase}))
   result=w.collect(e);self.assertFalse(result['wave_qualified']);self.assertTrue(any('byte cap' in x for x in result['errors']));self.assertTrue((temp/'vision-wave-evidence/report.json').is_file());self.assertIn('evidence_ready=true',(temp/'output').read_text())
   self.assertLessEqual(sum(p.stat().st_size for p in (temp/'vision-wave-evidence').iterdir()),w.MAX_EVIDENCE)
 def test_report_identity_and_unsupported_success_fail_closed(self):
  e=env();r={'schema':'Celluloid.FinalVisionSingleMethodWave.1','test_diagnostics':{'path':w.DIAGNOSTIC_TEST,'sha256':w.DIAGNOSTIC_TEST_SHA256,'inverse_original_sha256':w.ORIGINAL_TEST_SHA256,'unchanged_original_files':961,'product_compiled_inputs_unchanged':True},'control_sha':'wrong'}
  with self.assertRaises(ValueError):w.validate_report_identity(r,e)
 def test_command_stdout_begin_end_names_executable_without_environment_or_arguments(self):
  with tempfile.TemporaryDirectory() as t:
   capture=io.StringIO();commands=w.VisionCommands(Path(t));result={'output':b'output-secret','finalized':False,'timed_out':True,'overflow':False,'return_code':None,'elapsed_seconds':20}
   with patch.object(w,'bounded_optional_process',return_value=result),contextlib.redirect_stdout(capture):
    with self.assertRaises(ValueError):commands.run(['/path/xcodebuild','argument-secret'],'vision-wave-2-123-1-build',deadline=time.monotonic()+30,seconds=20)
   lines=capture.getvalue().splitlines();self.assertEqual(len(lines),2)
   receipts=[json.loads(x.split(' ',1)[1]) for x in lines];self.assertEqual([x['phase'] for x in receipts],['BEGIN','END']);self.assertTrue(all(x['executable']=='xcodebuild' for x in receipts));self.assertFalse(receipts[1]['finalized']);self.assertTrue(receipts[1]['timed_out']);self.assertNotIn('secret',capture.getvalue());self.assertTrue(all(len(x.encode())<1100 for x in lines));self.assertIn('begin_monotonic',commands.events[0])
 def test_command_stdout_exception_retained_and_no_later_dispatch(self):
  with tempfile.TemporaryDirectory() as t:
   capture=io.StringIO();commands=w.VisionCommands(Path(t))
   with patch.object(w,'bounded_optional_process',side_effect=PermissionError('secret-detail')) as run,contextlib.redirect_stdout(capture):
    with self.assertRaises(PermissionError):commands.run(['xcrun'],'vision-wave-2-123-1-boot',deadline=time.monotonic()+30,seconds=20)
    with self.assertRaises(ValueError):commands.run(['xcrun'],'vision-wave-2-123-1-delete',deadline=time.monotonic()+30,seconds=20)
   self.assertEqual(run.call_count,1);self.assertIn('PermissionError',capture.getvalue());self.assertNotIn('secret-detail',capture.getvalue());self.assertEqual(len(capture.getvalue().splitlines()),2)
 def test_uncertainty_latches_before_log_or_end_receipt_failure(self):
  scenarios=[{'finalized':False,'timed_out':False,'overflow':False},{'finalized':True,'timed_out':True,'overflow':False},{'finalized':True,'timed_out':False,'overflow':True}]
  for result in scenarios:
   for fault in ('log-write','end-output'):
    with self.subTest(result=result,fault=fault),tempfile.TemporaryDirectory() as t:
     commands=w.VisionCommands(Path(t));receipt=w.print_command_receipt
     def output(phase,*args,**kwargs):
      if phase=='END':raise OSError('synthetic stdout failure')
      return receipt(phase,*args,**kwargs)
     returned={'output':b'bounded diagnostic','return_code':None,'child_reaped':False,'pipe_eof':False,'cleanup_error':'unconfirmed',**result}
     with patch.object(w,'bounded_optional_process',return_value=returned) as dispatch,contextlib.redirect_stdout(io.StringIO()),contextlib.ExitStack() as stack:
      if fault=='log-write':stack.enter_context(patch.object(Path,'write_bytes',side_effect=OSError('synthetic log failure')))
      else:stack.enter_context(patch.object(w,'print_command_receipt',side_effect=output))
      with self.assertRaises(OSError):commands.run(['xcodebuild'],'vision-wave-2-123-1-ui-tests',deadline=time.monotonic()+30,seconds=20)
      self.assertTrue(commands.blocked)
      for later in ('shutdown','delete','ui-summary','attachments'):
       with self.assertRaisesRegex(ValueError,'earlier-process-uncertain-or-timeout'):commands.run(['xcrun'],'vision-wave-2-123-1-'+later,deadline=time.monotonic()+30,seconds=20)
      self.assertEqual(dispatch.call_count,1)
if __name__=='__main__':unittest.main()
