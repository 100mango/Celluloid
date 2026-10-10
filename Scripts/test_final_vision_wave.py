#!/usr/bin/env python3
"""Site-free route, fixture, single-case and native ownership regressions."""
import contextlib,io,ast,copy,hashlib,importlib.util,json,os,re,shutil,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
SOURCE_ROOT=Path(os.environ.get('CELLULOID_QUALIFICATION_SOURCE_ROOT',HERE.parent)).resolve()
sys.path.insert(0,str(SOURCE_ROOT/'Scripts'));sys.path.insert(0,str(HERE))
import stat
import final_vision_wave as w
import qualify_final_vision_wave_source as g

def env(method=None):return {'GITHUB_SHA':'a'*40,'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1','VISION_WAVE_METHOD':method or w.UI_METHODS[1],'QUALIFICATION_PLATFORM':'vision'}
def config(method=None):return {'schema':1,'READY':True,'platform':'vision','product_parent_sha':w.SOURCE,'product_parent_tree':w.TREE,'maximum_additional_spend_usd':0,'confirmation':'RUN_ONE_UNSIGNED_PLATFORM_ZERO_USD','selected_method':method or w.UI_METHODS[1]}
def clock():
 e=env();return {'schema':'Celluloid.FinalVisionWaveClock.1','control_sha':e['GITHUB_SHA'],'run_id':'123','run_attempt':'1','selected_method':e['VISION_WAVE_METHOD'],'started_monotonic':time.monotonic(),'started_unix':time.time(),'native_seconds':1560,'final_seconds':1740}
def summary():return {'totalTestCount':1,'passedTests':1,'failedTests':0,'skippedTests':0,'testFailures':[],'expectedFailures':0,'runtimeWarnings':[]}
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

BACKLIGHT_SAMPLE='2026-10-09 16:30:11.620905+0000 CelluloidVision[5650:24578] [assertions] failed to observe with mask <BLSXPCBacklightProxyObserverMask: 0x105784950; didUpdateToState: YES; eventsArray: YES> error:<XPC error received on message reply handler (3:BSServiceConnectionErrorDomain) "The operation couldn’t be completed. XPC error received on message reply handler">'

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
  c=clock();s=c['started_monotonic'];last=s+1560-120-w.FIXTURE_READ_SECONDS-735
  self.assertEqual(w.admit_ui(c,last),s+1440-w.FIXTURE_READ_SECONDS)
  with self.assertRaisesRegex(ValueError,'does-not-fit'):w.admit_ui(c,last+.001)
 def test_admission_receipt_rechecks_after_slow_output_without_renewing_deadline(self):
  c={'started_monotonic':1000};now=[1694.0];report={}
  with tempfile.TemporaryDirectory() as t:
   commands=w.VisionCommands(Path(t))
   def slow(*args,**kwargs):now[0]=1696.0
   with patch.object(w.time,'monotonic',side_effect=lambda:now[0]),patch('builtins.print',side_effect=slow):
    with self.assertRaisesRegex(ValueError,'full-720-second'):w.record_ui_admission(report,c,commands)
   self.assertTrue(report['ui_admission']['sampled_admissible']);self.assertFalse(report['ui_admission_recheck']['sampled_admissible']);self.assertFalse(report['ui_admission']['dispatch_proven']);self.assertEqual(report['ui_admission_recheck']['latest_setup_seconds'],695);self.assertFalse(commands.blocked);self.assertEqual(commands.events,[])
 def test_admission_receipt_io_and_cancel_fail_closed_before_any_later_dispatch(self):
  for error in (OSError('controlled receipt I/O'),KeyboardInterrupt(),SystemExit()):
   with self.subTest(error=type(error).__name__),tempfile.TemporaryDirectory() as t:
    commands=w.VisionCommands(Path(t));report={};c={'started_monotonic':time.monotonic()}
    with patch('builtins.print',side_effect=error):
     with self.assertRaises(type(error)):w.record_ui_admission(report,c,commands)
    self.assertTrue(commands.blocked);self.assertFalse(report['ui_admission']['dispatch_proven'])
    with patch.object(w,'bounded_optional_process') as run:
     with self.assertRaises(ValueError):commands.run(['fake'],'later',deadline=time.monotonic()+30,seconds=20)
     run.assert_not_called()
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
    container=root/'Library/Developer/CoreSimulator/Devices'/uid/'data/Containers/Data/Application/00000000-0000-0000-0000-000000000002';container.mkdir(parents=True)
    class FakeCommands:
     def __init__(self,folder):self.temp=folder;self.events=[];self.blocked=False
     def run(self,argv,label,**kwargs):
      began=time.monotonic();end=min(kwargs['deadline'],began+kwargs['seconds'])
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
       self.deploy_start=time.time()
       Path(argv[argv.index('-resultBundlePath')+1]).mkdir()
       if 'deployment-tests' in label:
        marker='VISION_NATIVE_RUNTIME bundle='+str(Path.home()/'Library/Developer/CoreSimulator/Devices'/uid/'data/Containers/Bundle/Application/00000000-0000-0000-0000-000000000001/CelluloidVision.app')+' scenes=1 platform=xrsimulator\n'
        data={'schema':'Celluloid.VisionOwnedData.1','bundle_identifier':'Mango.Celluloid','data_home':str(container),'device':container.stat().st_dev,'inode':container.stat().st_ino}
        out=caselog(w.DEPLOYMENT_METHOD,kind='deployment').replace('\nTest Case','\n'+marker+'VISION_NATIVE_DATA_JSON '+json.dumps(data)+'\nTest Case',1)
       elif 'producer-tests' in label:
        fixture=owner.fixture(container);out=caselog(w.PRODUCER,kind='producer')+'VISION_REMAINING_FIXTURE_JSON '+json.dumps(fixture)+'\n'
       else:
        out=caselog(method)
        if method==w.FILES_METHOD:
         fixture_marker={'schema':'Celluloid.VisionFilesFixture.1','document_name':'Untitled','layer_identifier':'layer.00000000-0000-0000-0000-000000000001'}
         model_marker={**fixture_marker,'schema':'Celluloid.VisionFilesModel.1','stage':'post-redo','expected_text':'Vision 世界','matched':True,'actual_label':'Select layer: Vision 世界'}
         out+='VISION_FILES_FIXTURE_JSON '+json.dumps(fixture_marker)+'\nVISION_FILES_MODEL_JSON '+json.dumps(model_marker)+'\n'
      elif argv[:5]==['xcrun','xcresulttool','get','test-results','summary']:
       ss=summary();ss['devicesAndConfigurations']=[{'device':{'deviceId':uid,'osVersion':'27.0','architecture':'arm64','platform':'visionOS Simulator'},'passedTests':1,'failedTests':0,'skippedTests':0}]
       if 'deployment-summary' in label:ss.update(result='Passed',startTime=self.deploy_start,finishTime=self.deploy_finish)
       out=json.dumps(ss)
      elif argv[:4]==['xcrun','xcresulttool','export','attachments']:
       folder=Path(argv[-1]);folder.mkdir();items=[]
       for i,name in enumerate(w.SHOTS[method]):
        filename=str(i)+'.png';(folder/filename).write_bytes(b'\x89PNG\r\n\x1a\nfixture');items.append({'suggestedHumanReadableName':name+'_0_id.png','exportedFileName':filename})
       (folder/'manifest.json').write_text(json.dumps([{'testIdentifier':'NativeVisionUITests/'+method+'()','attachments':items}]))
      if 'deployment-tests' in label:self.deploy_finish=time.time()
      raw=out.encode();path=self.temp/(label+'.log');path.write_bytes(raw);self.events.append({'label':label,'argv':argv,'log':path.name,'log_bytes':len(raw),'log_sha256':w.digest(raw),'begin_monotonic':began,'command_deadline_monotonic':end-15,'cleanup_deadline_monotonic':end,'elapsed_seconds':time.monotonic()-began,**result})
      return out,result
    try:
     with patch.object(Path,'home',return_value=root),contextlib.redirect_stdout(io.StringIO()),patch.object(w,'ROOT',repo),patch.object(w,'VisionCommands',FakeCommands),patch.object(w,'validate_inventory',return_value={'synthetic':'source'}),patch.object(w.time,'sleep'),patch.object(w,'capture_initial_fixture',return_value={'synthetic':True}),patch.object(w,'read_fixture',return_value={'status':'captured','expected_layer_present':True,'expected_text_matches':True,'save_completion_proven':False}):report=w.execute(e)
    finally:os.chdir(original_cwd)
    self.assertTrue(report['wave_qualified'],report['errors']);self.assertFalse(report['all_eight_qualified']);self.assertEqual(report['omitted_ui_methods'],[m for m in w.UI_METHODS if m!=method])
    tests=[(a,k) for a,k in called if 'test-without-building' in a];self.assertEqual(len(tests),2 if method in (w.UI_METHODS[2],w.FILES_METHOD) else 1)
    ui=[(a,k) for a,k in tests if w.selectors_for(method)['ui'][0] in a];self.assertEqual(len(ui),1);self.assertEqual(ui[0][1]['seconds'],735);self.assertTrue(ui[0][1]['full'])
    self.assertEqual((container/'Documents/VisionSynthetic.png').exists(),method==w.UI_METHODS[1]);self.assertEqual('producer_fixture' in report,method==w.UI_METHODS[2])
    self.assertFalse(any('archive' in a for a,k in called))
    binding={'source_sha':e['GITHUB_SHA'],'product_parent_sha':w.SOURCE,'selected_method':method,'file_count':960}
    for phase in ['before','after']:(temp/('combined-source-'+phase+'.json')).write_text(json.dumps({**binding,'phase':phase}))
    e['GITHUB_OUTPUT']=str(temp/'github-output')
    with patch.object(Path,'home',return_value=root),patch.dict(os.environ,e):retained=w.collect(e)
    self.assertTrue(retained['wave_qualified']);self.assertTrue((temp/'vision-wave-evidence/report.json').is_file());self.assertLessEqual(sum(p.stat().st_size for p in (temp/'vision-wave-evidence').iterdir()),w.MAX_EVIDENCE)
 def test_real_git_shallow_workflow_topology_and_separate_parent_trap(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t).resolve();origin=root/'origin';origin.mkdir()
   def git(where,*args,input=None):return subprocess.check_output(['git',*args],cwd=where,input=input,text=True,stderr=subprocess.STDOUT).strip()
   git(origin,'init','-q');git(origin,'config','user.name','Synthetic test');git(origin,'config','user.email','synthetic@invalid');(origin/'product.txt').write_text('fixed fixture product');original_test=origin/g.DIAGNOSTIC_TEST;original_test.parent.mkdir(parents=True);original_test.write_bytes(g.verify_diagnostic_test((HERE.parent/g.DIAGNOSTIC_TEST).read_bytes()));original_hosted=origin/g.HOSTED_DIAGNOSTIC_TEST;original_hosted.parent.mkdir(parents=True);original_hosted.write_bytes(g.verify_hosted_diagnostic_test((HERE.parent/g.HOSTED_DIAGNOSTIC_TEST).read_bytes()));git(origin,'add','.');tree=git(origin,'write-tree');parent=None
   for n in range(66):
    args=['commit-tree',tree]+(['-p',parent] if parent else []);parent=git(origin,*args,input='synthetic ancestor '+str(n)+'\n')
   product=parent;git(origin,'update-ref','refs/heads/'+g.BRANCH,product);git(origin,'symbolic-ref','HEAD','refs/heads/'+g.BRANCH)
   for rel in g.QUALIFICATION_PATHS:
    dest=origin/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(HERE.parent/rel,dest)
   gatepath=origin/'Scripts/qualify_final_vision_wave_source.py';gatepath.write_text(gatepath.read_text().replace(g.SOURCE,product).replace(g.TREE,tree).replace('UNCHANGED_ORIGINAL_FILE_COUNT = 960','UNCHANGED_ORIGINAL_FILE_COUNT = 1'))
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
   report={'schema':'Celluloid.FinalVisionSingleMethodWave.1','test_diagnostics':{'path':w.DIAGNOSTIC_TEST,'sha256':w.DIAGNOSTIC_TEST_SHA256,'inverse_original_sha256':w.ORIGINAL_TEST_SHA256,'unchanged_original_files':960,'hosted_path':w.HOSTED_DIAGNOSTIC_TEST,'hosted_sha256':w.HOSTED_DIAGNOSTIC_TEST_SHA256,'hosted_inverse_original_sha256':w.HOSTED_ORIGINAL_TEST_SHA256,'product_compiled_inputs_unchanged':True},'control_sha':e['GITHUB_SHA'],'product_sha':w.SOURCE,'product_tree':w.TREE,'run_id':'123','run_attempt':'1','selected_method':method,'omitted_ui_methods':[m for m in w.UI_METHODS if m!=method],'original_hosted_inventory':list(w.HOSTED),'original_ui_inventory':list(w.UI_METHODS),'ui_limit_seconds':720,'all_eight_qualified':False,'archive_qualified':False,'clock':c,'screenshots':{'native-vision-launch':{'source':str(image),'bytes':len(raw),'sha256':w.digest(raw),'extension':'.png'}},'commands':[],'selected_method_passed':False,'wave_qualified':False,'errors':['synthetic failed method']}
   (temp/'vision-wave-report.json').write_text(json.dumps(report));binding={'source_sha':e['GITHUB_SHA'],'product_parent_sha':w.SOURCE,'selected_method':method}
   for phase in ['before','after']:(temp/('combined-source-'+phase+'.json')).write_text(json.dumps({**binding,'phase':phase}))
   result=w.collect(e);self.assertFalse(result['wave_qualified']);self.assertTrue(any('byte cap' in x for x in result['errors']));self.assertTrue((temp/'vision-wave-evidence/report.json').is_file());self.assertIn('evidence_ready=true',(temp/'output').read_text())
   self.assertLessEqual(sum(p.stat().st_size for p in (temp/'vision-wave-evidence').iterdir()),w.MAX_EVIDENCE)
 def test_report_identity_and_unsupported_success_fail_closed(self):
  e=env();r={'schema':'Celluloid.FinalVisionSingleMethodWave.1','test_diagnostics':{'path':w.DIAGNOSTIC_TEST,'sha256':w.DIAGNOSTIC_TEST_SHA256,'inverse_original_sha256':w.ORIGINAL_TEST_SHA256,'unchanged_original_files':960,'hosted_path':w.HOSTED_DIAGNOSTIC_TEST,'hosted_sha256':w.HOSTED_DIAGNOSTIC_TEST_SHA256,'hosted_inverse_original_sha256':w.HOSTED_ORIGINAL_TEST_SHA256,'product_compiled_inputs_unchanged':True},'control_sha':'wrong'}
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
 def deployment_receipts(self):
  uid='00000000-0000-0000-0000-000000000123';runtime={'version':'27.0','buildversion':'24M362'}
  marker='VISION_NATIVE_RUNTIME bundle='+str(Path.home()/'Library/Developer/CoreSimulator/Devices'/uid/'data/Containers/Bundle/Application/00000000-0000-0000-0000-000000000001/CelluloidVision.app')+' scenes=1 platform=xrsimulator'
  data={'schema':'Celluloid.VisionOwnedData.1','bundle_identifier':'Mango.Celluloid','data_home':str(Path.home()/'Library/Developer/CoreSimulator/Devices'/uid/'data/Containers/Data/Application/00000000-0000-0000-0000-000000000002'),'device':1,'inode':2}
  log=caselog(w.DEPLOYMENT_METHOD,kind='deployment').replace('\nTest Case','\n'+marker+'\nVISION_NATIVE_DATA_JSON '+json.dumps(data)+'\nTest Case',1)
  ss=summary();ss.update(result='Passed',startTime=11220.5,finishTime=11221.5,devicesAndConfigurations=[{'device':{'deviceId':uid,'osVersion':'27.0','osBuildNumber':'24M362','architecture':'arm64','platform':'visionOS Simulator'},'passedTests':1,'failedTests':0,'skippedTests':0}])
  return uid,runtime,log,ss
 def test_managed_host_marker_belongs_inside_exact_single_case_and_owned_device(self):
  uid,runtime,log,ss=self.deployment_receipts();self.assertEqual(w.inspect_deployment_transcript(log,uid)['scenes'],1)
  lines=log.splitlines()
  for bad in ['\n'.join([lines[1],lines[0],lines[2]]),'\n'.join([lines[0],lines[2],lines[1]]),log+lines[1],log+caselog('unexpected'),log.replace(uid,'11111111-1111-1111-1111-111111111111'),log.replace('scenes=1','scenes=0'),log.replace('platform=xrsimulator','platform=iphoneos'),log.replace('CelluloidVision.app','Other.app'),log.replace('passed (','skipped (')]:
   with self.subTest(bad=bad[:55]),self.assertRaises(ValueError):w.inspect_deployment_transcript(bad,uid)
 def test_managed_explicit_error_denial_timeout_never_admits_summary(self):
  uid,runtime,log,ss=self.deployment_receipts()
  for bad in ['error: xcode failed','Testing failed: synthetic','** TEST EXECUTE FAILED **','PermissionError','Operation not permitted','permission denied','Timed out waiting for launch','timeout from host','** TEST EXECUTE CANCELLED **','** TEST EXECUTE CANCELED **','Testing cancelled: synthetic','Testing cancellation: synthetic']:
   with self.subTest(bad=bad),self.assertRaises(ValueError):w.inspect_deployment_transcript(log+'\n'+bad,uid)
 def test_managed_summary_requires_passed_zero_warning_build_and_current_times(self):
  uid,runtime,log,ss=self.deployment_receipts();window={'started_unix':11220,'finished_unix':11222};self.assertTrue(w.verify_managed_deployment(log,ss,uid,runtime,window)['passed'])
  mutations=[lambda x:x.update(result='Failed'),lambda x:x.pop('runtimeWarnings'),lambda x:x.update(runtimeWarnings=None),lambda x:x.update(runtimeWarnings=[{'message':'actual warning'}]),lambda x:x.update(startTime=11219),lambda x:x.update(finishTime=11223),lambda x:x.update(finishTime=x['startTime']),lambda x:x.update(startTime=True),lambda x:x['devicesAndConfigurations'][0]['device'].update(osBuildNumber='wrong'),lambda x:x['devicesAndConfigurations'][0]['device'].update(deviceId='wrong'),lambda x:x.update(skippedTests=1)]
  for mutation in mutations:
   bad=copy.deepcopy(ss);mutation(bad)
   with self.assertRaises(ValueError):w.verify_managed_deployment(log,bad,uid,runtime,window)
 def run_managed_fixture(self,mode='healthy',now_start=1220):
  uid,runtime,log,ss=self.deployment_receipts();now=[float(now_start)];calls=[];report={};error=None;original_helper=w.bounded_optional_process
  with tempfile.TemporaryDirectory() as t:
   commands=w.VisionCommands(Path(t))
   def helper(argv,work,end,**kwargs):
    calls.append({'argv':argv,'work':work,'end':end});deployment='test-without-building' in argv
    if mode=='summary-begin-expired' and not deployment:return original_helper(argv,work,end,**kwargs)
    if mode=='cancel':raise KeyboardInterrupt()
    if mode=='permission-exception':raise PermissionError('controlled')
    if deployment:
     now[0]+=404 if mode in ('slow-parse','last-summary-start') else 2
     output=log.encode()
     if mode=='wrong-host':output=log.replace(uid,'11111111-1111-1111-1111-111111111111').encode()
    else:
     now[0]+=1
     if mode=='warning':ss['runtimeWarnings']=[{'message':'actual warning'}]
     output=json.dumps(ss).encode()
    r={'output':output,'return_code':0,'bytes_read':len(output),'pipe_eof':True,'child_reaped':True,'timed_out':False,'overflow':False,'cleanup_error':None,'finalized':True,'elapsed_seconds':2 if deployment else 1,'command_deadline_monotonic':work,'cleanup_deadline_monotonic':end}
    if mode=='uncertain':r.update(finalized=False,child_reaped=False,cleanup_error='PermissionError')
    if mode=='exit65':r['return_code']=65
    if not deployment and mode=='summary-timeout':r.update(timed_out=True,elapsed_seconds=45.001)
    if not deployment and mode=='summary-denial':r.update(finalized=False,child_reaped=False,cleanup_error='PermissionError')
    return r
   original=w.inspect_deployment_transcript
   def inspect(*a):
    out=original(*a)
    if mode=='old-last-summary-start':now[0]=1655.0
    if mode=='slow-parse':now[0]+=1.001
    if mode=='last-summary-start':now[0]+=1
    return out
   original_verify=w.verify_managed_deployment
   def verify(*a):
    out=original_verify(*a)
    if mode=='late-verification':now[0]=1685.0
    return out
   def receipt(phase,label,*a):
    if phase=='BEGIN' and label=='deployment-summary' and mode=='summary-begin-delay':now[0]+=1
    if phase=='BEGIN' and label=='deployment-summary' and mode=='summary-begin-expired':now[0]+=46
   def call(argv,label,seconds,**kwargs):return commands.run(argv,label,seconds=seconds,**kwargs)
   with contextlib.redirect_stdout(io.StringIO()),patch.object(w.time,'monotonic',side_effect=lambda:now[0]),patch.object(w.time,'time',side_effect=lambda:10000+now[0]),patch.object(w,'bounded_optional_process',side_effect=helper),patch.object(w,'inspect_deployment_transcript',side_effect=inspect),patch.object(w,'verify_managed_deployment',side_effect=verify),patch.object(w,'print_command_receipt',side_effect=receipt):
    try:w.run_managed_deployment(commands,call,{'started_monotonic':1000,'control_sha':'a'*40},Path(t),uid,runtime,'vision-wave-2-123-1',report)
    except BaseException as e:error=e
   blocked=commands.blocked
   if blocked:
    with patch.object(w,'bounded_optional_process') as later,contextlib.redirect_stdout(io.StringIO()):
     with self.assertRaises(ValueError):commands.run(['fake'],'later',deadline=2000,seconds=60)
    later.assert_not_called()
  return report,calls,blocked,error
 def test_managed_deadlines_use_first_wave_clock_and_full_summary_without_renewal(self):
  report,calls,blocked,error=self.run_managed_fixture();self.assertIsNone(error);self.assertFalse(blocked);self.assertEqual(len(calls),2);self.assertEqual(calls[0]['work'],1610);self.assertEqual(calls[0]['end'],1625);self.assertEqual(calls[1]['work'],1267);self.assertEqual(calls[1]['end'],1282);self.assertEqual(calls[1]['end']-calls[1]['work'],15);self.assertEqual(report['deployment_budget']['summary_deadline_monotonic'],1685);self.assertEqual(report['deployment_budget']['completed_monotonic'],1223);self.assertTrue(report['managed_deployment']['passed']);self.assertFalse(report['deployment_budget']['dispatch_proven'])
  self.assertEqual((w.DEPLOYMENT_SUMMARY_SECONDS,w.FILES_PREPARATION_SECONDS,w.UI_SECONDS,w.NATIVE_SECONDS,w.FINAL_SECONDS),(60,10,720,1560,1740));self.assertEqual(report['deployment_budget']['process_cleanup_seconds'],15)
  selected=[v for v in calls[0]['argv'] if v.startswith('-only-testing:')];self.assertEqual(selected,['-only-testing:CelluloidVisionTests/NativeVisionTests/'+w.DEPLOYMENT_METHOD]);self.assertNotIn('-skip-testing',str(calls[0]['argv']))
 def test_managed_slow_transcript_parse_refuses_summary_and_latches(self):
  report,calls,blocked,error=self.run_managed_fixture('slow-parse');self.assertIsInstance(error,ValueError);self.assertIn('full-command-window',str(error));self.assertTrue(blocked);self.assertEqual(len(calls),1);self.assertNotIn('managed_deployment',report)
 def test_managed_work_budget_rejects_exhaustion_before_any_command(self):
  report,calls,blocked,error=self.run_managed_fixture(now_start=1609.91);self.assertIsInstance(error,ValueError);self.assertIn('managed-deployment-work-budget-exhausted',str(error));self.assertTrue(blocked);self.assertEqual(calls,[])
 def test_managed_failure_cancel_denial_and_warning_block_all_later_dispatch(self):
  for mode,count in [('uncertain',1),('exit65',1),('wrong-host',1),('cancel',1),('permission-exception',1),('warning',2)]:
   with self.subTest(mode=mode):
    report,calls,blocked,error=self.run_managed_fixture(mode);self.assertIsNotNone(error);self.assertTrue(blocked);self.assertEqual(len(calls),count);self.assertNotIn('managed_deployment',report)

 def test_managed_summary_last_full_60_fits_only_first_wave_absolute_end(self):
  report,calls,blocked,error=self.run_managed_fixture('last-summary-start');self.assertIsNone(error);self.assertFalse(blocked);self.assertEqual(len(calls),2);self.assertEqual(calls[1]['work'],1670);self.assertEqual(calls[1]['end'],1685);self.assertEqual(report['deployment_budget']['completed_monotonic'],1627)
 def test_managed_summary_begin_output_consumes_work_without_new_deadline(self):
  report,calls,blocked,error=self.run_managed_fixture('summary-begin-delay');self.assertIsNone(error);self.assertFalse(blocked);self.assertEqual(calls[1]['work'],1267);self.assertEqual(calls[1]['end'],1282);self.assertEqual(report['deployment_budget']['completed_monotonic'],1224)
 def test_managed_summary_timeout_or_denial_stays_failed_and_blocked(self):
  for mode in ('summary-timeout','summary-denial'):
   with self.subTest(mode=mode):
    report,calls,blocked,error=self.run_managed_fixture(mode);self.assertIsInstance(error,ValueError);self.assertTrue(blocked);self.assertEqual(len(calls),2);self.assertNotIn('managed_deployment',report)
 def test_managed_verification_at_first_wave_absolute_end_never_qualifies(self):
  report,calls,blocked,error=self.run_managed_fixture('late-verification');self.assertIsInstance(error,ValueError);self.assertIn('deployment-verification-after-absolute-summary-deadline',str(error));self.assertTrue(blocked);self.assertEqual(len(calls),2);self.assertNotIn('managed_deployment',report)

 def test_summary_restored_full_window_rejects_old_30_second_remainder(self):
  report,calls,blocked,error=self.run_managed_fixture('old-last-summary-start');self.assertIsInstance(error,ValueError);self.assertIn('full-command-window',str(error));self.assertTrue(blocked);self.assertEqual(len(calls),1);self.assertNotIn('managed_deployment',report)
 def test_summary_delayed_BEGIN_never_resets_deadline_or_starts_child(self):
  with patch.object(w.subprocess,'Popen') as child:
   report,calls,blocked,error=self.run_managed_fixture('summary-begin-expired')
  child.assert_not_called();self.assertIsInstance(error,ValueError);self.assertIn('Invalid/expired optional process deadlines',str(error));self.assertTrue(blocked);self.assertEqual(len(calls),2);self.assertEqual(calls[1]['work'],1267);self.assertEqual(calls[1]['end'],1282);self.assertNotIn('managed_deployment',report)

 def test_exact_backlight_record_is_observed_and_original_log_identity_kept(self):
  uid,runtime,log,ss=self.deployment_receipts();raw=BACKLIGHT_SAMPLE+'\n'+log;out=w.inspect_deployment_transcript(raw,uid);obs=out['system_log_observations']
  self.assertEqual(obs['backlight_xpc_records'],1);self.assertEqual(obs['decoded_transcript_sha256'],w.digest(raw.encode()));self.assertIn('not proven harmless',obs['classification'])
  duplicate=BACKLIGHT_SAMPLE+'\n'+raw;self.assertEqual(w.inspect_deployment_transcript(duplicate,uid)['system_log_observations']['backlight_xpc_records'],2)
 def test_backlight_variants_denial_timeout_cancel_domain_and_observer_stay_rejected(self):
  uid,runtime,log,ss=self.deployment_receipts()
  for line in [BACKLIGHT_SAMPLE.replace('BSServiceConnectionErrorDomain','DifferentDomain'),BACKLIGHT_SAMPLE.replace('BLSXPCBacklightProxyObserverMask','DifferentObserver'),BACKLIGHT_SAMPLE.replace('message reply handler (3:', 'Permission denied (3:'),BACKLIGHT_SAMPLE.replace('The operation couldn’t be completed.','timeout'),BACKLIGHT_SAMPLE.replace('The operation couldn’t be completed.','cancelled'),BACKLIGHT_SAMPLE+' PermissionError',BACKLIGHT_SAMPLE+' ** TEST EXECUTE CANCELLED **',BACKLIGHT_SAMPLE.replace('[assertions]','[product]'),BACKLIGHT_SAMPLE.replace('didUpdateToState: YES','didUpdateToState: NO')]:
   with self.subTest(line=line[-70:]),self.assertRaises(ValueError):w.inspect_deployment_transcript(line+'\n'+log,uid)
 def test_backlight_classification_never_suppresses_other_tool_errors_or_terminals(self):
  uid,runtime,log,ss=self.deployment_receipts()
  for error in ['xcodebuild: error: failed destination','/owned/File.swift:12:3: error: genuine compile error','error: unknown tool failure','CelluloidVision[1:2] [unknown] error: unknown record','Testing failed: unexpected','** TEST EXECUTE FAILED **','** TEST EXECUTE CANCELLED **','Permission denied','timeout during launch']:
   with self.subTest(error=error),self.assertRaises(ValueError):w.inspect_deployment_transcript(BACKLIGHT_SAMPLE+'\n'+log+'\n'+error,uid)
 def test_backlight_record_does_not_supply_or_relax_official_runtime_warning_evidence(self):
  uid,runtime,log,ss=self.deployment_receipts();raw=BACKLIGHT_SAMPLE+'\n'+log;window={'started_unix':11220,'finished_unix':11222}
  self.assertTrue(w.verify_managed_deployment(raw,ss,uid,runtime,window)['passed'])
  for value in [None,False,{},[{'message':'Publishing changes from within view updates is not allowed'}],[{'message':BACKLIGHT_SAMPLE}]]:
   bad=copy.deepcopy(ss);bad['runtimeWarnings']=value
   with self.assertRaises(ValueError):w.verify_managed_deployment(raw,bad,uid,runtime,window)

 def test_owned_data_marker_requires_exact_case_position_path_identity_and_schema(self):
  uid,runtime,log,ss=self.deployment_receipts();valid=w.inspect_deployment_transcript(log,uid)['data_home_receipt'];self.assertEqual(valid['inode'],2)
  mutations=[{**valid,'data_home':valid['data_home'].replace(uid,'11111111-1111-1111-1111-111111111111')},{**valid,'data_home':valid['data_home']+'/..'},{**valid,'data_home':'/tmp/unrelated'},{**valid,'bundle_identifier':'Other'},{**valid,'device':True},{**valid,'inode':0},{**valid,'inode':2**64},{**valid,'extra':'secret'}]
  for value in mutations:
   with self.subTest(value=value),self.assertRaises(ValueError):w.validate_managed_data_identity(value,uid)
  line=next(x for x in log.splitlines() if x.startswith('VISION_NATIVE_DATA_JSON '));without='\n'.join(x for x in log.splitlines() if x!=line)
  for bad in (without,line+'\n'+without,without+'\n'+line,log+'\n'+line,log.replace(line,line+'x'),log.replace(line,'VISION_NATIVE_DATA_JSON '+('x'*4097))):
   with self.assertRaises(ValueError):w.inspect_deployment_transcript(bad,uid)
 def owned_setup(self,root):
  uid='00000000-0000-0000-0000-000000000123';container=root/'Library/Developer/CoreSimulator/Devices'/uid/'data/Containers/Data/Application/00000000-0000-0000-0000-000000000002';container.mkdir(parents=True)
  st=container.stat();data={'schema':'Celluloid.VisionOwnedData.1','bundle_identifier':'Mango.Celluloid','data_home':str(container),'device':st.st_dev,'inode':st.st_ino}
  report={'managed_deployment':{'passed':True,'control_sha':'a'*40,'hosted_test_sha256':w.HOSTED_DIAGNOSTIC_TEST_SHA256,'host':{'data_home_receipt':data}}};c={'started_monotonic':1000,'control_sha':'a'*40};commands=w.VisionCommands(root)
  return uid,container,report,c,commands
 def test_owned_seed_matches_original_bytes_and_original_reader_initial_contract(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t).resolve();uid,container,r,c,commands=self.owned_setup(root);original=root/'original';original.mkdir();legacy=w.seed_png(str(original))
   with patch.object(Path,'home',return_value=root),patch.object(w.time,'monotonic',return_value=1001):
    initial=w.prepare_managed_files(commands,c,r,uid)
    replay=w.prepare_fixture_receipt(devices_root=str(root/'Library/Developer/CoreSimulator/Devices'),owned_udid=uid,container_path=str(container),png_fixture=r['png_fixture'],deadline=1011)
   self.assertEqual(initial,replay);self.assertEqual((container/'Documents/VisionSynthetic.png').read_bytes(),(original/'Documents/VisionSynthetic.png').read_bytes());self.assertEqual(r['png_fixture']['sha256'],legacy['sha256']);self.assertEqual(r['png_fixture']['bytes'],8305);self.assertFalse(commands.blocked);self.assertEqual(commands.events,[]);self.assertEqual(r['files_preparation_budget']['deadline_monotonic'],1011)
 def test_owned_seed_requires_finalized_managed_proof_before_any_filesystem_open(self):
  for mutation in ('passed','source','blocked'):
   with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as t:
    root=Path(t).resolve();uid,container,r,c,commands=self.owned_setup(root)
    if mutation=='passed':r['managed_deployment']['passed']=False
    elif mutation=='source':r['managed_deployment']['hosted_test_sha256']='0'*64
    else:commands.blocked=True
    with patch.object(w.os,'open') as opened,self.assertRaises(ValueError):w.prepare_managed_files(commands,c,r,uid)
    opened.assert_not_called();self.assertTrue(commands.blocked);self.assertFalse((container/'Documents').exists())
 def test_owned_seed_identity_nonpristine_and_symlink_negatives_never_write_elsewhere(self):
  for mode in ('inode','device','docs-symlink','container-symlink','nonpristine'):
   with self.subTest(mode=mode),tempfile.TemporaryDirectory() as t:
    root=Path(t).resolve();uid,container,r,c,commands=self.owned_setup(root);outside=root/'unrelated';outside.mkdir();(outside/'sentinel').write_text('unchanged')
    if mode in ('inode','device'):r['managed_deployment']['host']['data_home_receipt'][mode]+=1
    elif mode=='docs-symlink':(container/'Documents').symlink_to(outside,target_is_directory=True)
    elif mode=='container-symlink':container.rmdir();container.symlink_to(outside,target_is_directory=True)
    elif mode=='nonpristine':(container/'Documents').mkdir();(container/'Documents/existing').write_text('unchanged')
    with patch.object(Path,'home',return_value=root),patch.object(w.time,'monotonic',return_value=1001),self.assertRaises((ValueError,OSError)):w.prepare_managed_files(commands,c,r,uid)
    self.assertTrue(commands.blocked);self.assertNotIn('fixture_initial_receipt',r);self.assertFalse((outside/'VisionSynthetic.png').exists());self.assertEqual((outside/'sentinel').read_text(),'unchanged')
 def test_owned_seed_10_second_window_covers_write_read_and_denial_cancel(self):
  for mode in ('late-write','denial','cancel','system-exit','no-window'):
   with self.subTest(mode=mode),tempfile.TemporaryDirectory() as t:
    root=Path(t).resolve();uid,container,r,c,commands=self.owned_setup(root);now=[1685.001 if mode=='no-window' else 1001.0];write=w.os.write
    def action(fd,data):
     if mode=='denial':raise PermissionError('controlled')
     if mode=='cancel':raise KeyboardInterrupt()
     if mode=='system-exit':raise SystemExit()
     n=write(fd,data);now[0]+=10.001;return n
    with patch.object(Path,'home',return_value=root),patch.object(w.time,'monotonic',side_effect=lambda:now[0]),patch.object(w.os,'write',side_effect=action) as writes,self.assertRaises((ValueError,OSError,KeyboardInterrupt,SystemExit)):w.prepare_managed_files(commands,c,r,uid)
    self.assertTrue(commands.blocked);self.assertNotIn('fixture_initial_receipt',r);self.assertNotIn('managed_files_preparation',r)
    if mode=='no-window':writes.assert_not_called()
    with patch.object(w,'bounded_optional_process') as native,self.assertRaises(ValueError):commands.run(['fake'],'later',deadline=3000,seconds=20)
    native.assert_not_called()
 def test_owned_seed_anchored_write_detects_replaced_documents_without_touching_replacement(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t).resolve();uid,container,r,c,commands=self.owned_setup(root);write=w.os.write;swapped=[]
   def action(fd,data):
    n=write(fd,data)
    if not swapped:
     (container/'Documents').rename(container/'owned-original');(container/'Documents').mkdir();(container/'Documents/sentinel').write_text('replacement untouched');swapped.append(True)
    return n
   with patch.object(Path,'home',return_value=root),patch.object(w.time,'monotonic',return_value=1001),patch.object(w.os,'write',side_effect=action),self.assertRaises(ValueError):w.prepare_managed_files(commands,c,r,uid)
   self.assertTrue(commands.blocked);self.assertFalse((container/'Documents/VisionSynthetic.png').exists());self.assertEqual((container/'Documents/sentinel').read_text(),'replacement untouched');self.assertNotIn('fixture_initial_receipt',r)
 def test_hosted_test_narrow_inverse_preserves_original_assertions_and_history(self):
  raw=(HERE.parent/g.HOSTED_DIAGNOSTIC_TEST).read_bytes();original=g.verify_hosted_diagnostic_test(raw);self.assertEqual(w.digest(original),g.HOSTED_ORIGINAL_TEST_SHA256)
  self.assertEqual(raw.count(b'func test'),original.count(b'func test'));self.assertIn(b'NSHomeDirectory()',raw)
  for bad in (raw+b'\n',raw.replace(b'XCTAssertFalse(scenes.isEmpty)',b'XCTAssertTrue(true)'),raw.replace(g.HOSTED_DIAGNOSTIC_ADDITION.encode(),b'')):
   with self.assertRaises(ValueError):g.verify_hosted_diagnostic_test(bad)
  chain=[{'sha':'new','parents':['old'],'changed_paths':[g.HOSTED_DIAGNOSTIC_TEST]}]
  self.assertEqual(g.verify_hosted_diagnostic_history(chain,lambda revision,path:original if revision=='old' else raw),'new')
  for bad in (original+b'changed',raw):
   with self.assertRaises(ValueError):g.verify_hosted_diagnostic_history(chain,lambda revision,path:bad if revision=='old' else raw)
  with self.assertRaises(ValueError):g.verify_hosted_diagnostic_history([],lambda *a:raw)

 def test_owned_writer_rejects_foreign_uid_even_with_same_device_inode(self):
  for mode in ('container','documents','new-png','after-write'):
   with self.subTest(mode=mode),tempfile.TemporaryDirectory() as t:
    root=Path(t).resolve();uid,container,r,c,commands=self.owned_setup(root);docs=container/'Documents';docs.mkdir();ci=container.stat().st_ino;di=docs.stat().st_ino;statcall=w.os.stat;fstatcall=w.os.fstat;write=w.os.write;wrote=[]
    class Foreign:
     def __init__(self,st):self.st=st;self.st_uid=st.st_uid+1
     def __getattr__(self,key):return getattr(self.st,key)
    def adjust(st):
     change=(mode=='container' and st.st_ino==ci) or (mode=='documents' and st.st_ino==di) or (mode=='new-png' and stat.S_ISREG(st.st_mode)) or (mode=='after-write' and wrote and stat.S_ISREG(st.st_mode))
     return Foreign(st) if change else st
    def output(fd,data):n=write(fd,data);wrote.append(True);return n
    with patch.object(Path,'home',return_value=root),patch.object(w.time,'monotonic',return_value=1001),patch.object(w.os,'stat',side_effect=lambda *a,**k:adjust(statcall(*a,**k))),patch.object(w.os,'fstat',side_effect=lambda *a,**k:adjust(fstatcall(*a,**k))),patch.object(w.os,'write',side_effect=output),self.assertRaises(ValueError):w.prepare_managed_files(commands,c,r,uid)
    self.assertTrue(commands.blocked);self.assertNotIn('fixture_initial_receipt',r)
    if mode!='after-write':self.assertEqual(wrote,[])
 def test_owned_writer_at_exact_deadline_performs_no_next_mutation(self):
  for mode in ('mkdir','create-png','write-png'):
   with self.subTest(mode=mode),tempfile.TemporaryDirectory() as t:
    root=Path(t).resolve();uid,container,r,c,commands=self.owned_setup(root);now=[1001.0];mkdir=w.os.mkdir;opener=w.os.open;inventory=w._inventory;deadline=w._deadline;writes=[];mutations=[]
    def check(end):
     if mode=='mkdir':now[0]=end
     deadline(end)
    def names(*a):
     result=inventory(*a)
     if mode=='create-png':now[0]=1011.0
     return result
    def create(name,*a,**k):
     flags=a[0] if a else k.get('flags',0)
     fd=opener(name,*a,**k)
     if flags&w.os.O_CREAT:
      mutations.append('create-png')
      if mode=='write-png':now[0]=1011.0
     return fd
    def make(*a,**k):mutations.append('mkdir');return mkdir(*a,**k)
    with patch.object(Path,'home',return_value=root),patch.object(w.time,'monotonic',side_effect=lambda:now[0]),patch.object(w,'_deadline',side_effect=check),patch.object(w,'_inventory',side_effect=names),patch.object(w.os,'open',side_effect=create),patch.object(w.os,'mkdir',side_effect=make),patch.object(w.os,'write',side_effect=lambda *a:writes.append(a)),self.assertRaises(ValueError):w.prepare_managed_files(commands,c,r,uid)
    self.assertTrue(commands.blocked);self.assertEqual(writes,[])
    self.assertEqual(mutations,[] if mode=='mkdir' else ['mkdir'] if mode=='create-png' else ['mkdir','create-png'])

 def test_owned_preparation_replay_binds_report_to_actual_command_deadlines(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t).resolve();uid,container,r,c,commands=self.owned_setup(root)
   with patch.object(Path,'home',return_value=root),patch.object(w.time,'monotonic',return_value=1001):w.prepare_managed_files(commands,c,r,uid)
   r.update(clock=c,udid=uid,deployment_budget={'started_monotonic':1100,'work_deadline_monotonic':1610,'cleanup_deadline_monotonic':1625,'summary_deadline_monotonic':1685,'latest_ui_start_monotonic':1695,'available_work_seconds':510,'process_cleanup_seconds':15,'summary_total_seconds':60,'files_preparation_seconds':10,'dispatch_proven':False,'completed_monotonic':1131},commands=[{'label':'vision-wave-2-123-1-deployment-tests','begin_monotonic':1100,'command_deadline_monotonic':1610,'cleanup_deadline_monotonic':1625,'elapsed_seconds':1},{'label':'vision-wave-2-123-1-deployment-summary','begin_monotonic':1101,'command_deadline_monotonic':1146,'cleanup_deadline_monotonic':1161,'elapsed_seconds':1}])
   r['files_preparation_budget'].update(started_monotonic=1132,deadline_monotonic=1142,completed_monotonic=1133)
   with patch.object(Path,'home',return_value=root):self.assertTrue(w.validate_managed_files_claim(r))
   mutations=[lambda x:x['commands'][0].update(command_deadline_monotonic=1611),lambda x:x['commands'][0].update(cleanup_deadline_monotonic=1626),lambda x:x['commands'][1].update(command_deadline_monotonic=1147),lambda x:x['commands'][1].update(cleanup_deadline_monotonic=1162),lambda x:x['commands'][1].update(begin_monotonic=1670,command_deadline_monotonic=1685,cleanup_deadline_monotonic=1700),lambda x:x['commands'][1].update(begin_monotonic=1099),lambda x:x['deployment_budget'].update(completed_monotonic=1101),lambda x:x['files_preparation_budget'].update(deadline_monotonic=1143),lambda x:x['files_preparation_budget'].update(completed_monotonic=1142),lambda x:x['fixture_initial_receipt']['path_identity'][str(container)].update(inode=0),lambda x:x.update(pretest_launch_image={'fake':True})]
   for mutation in mutations:
    bad=copy.deepcopy(r);mutation(bad)
    with patch.object(Path,'home',return_value=root),self.assertRaises(ValueError):w.validate_managed_files_claim(bad)

if __name__=='__main__':unittest.main()
