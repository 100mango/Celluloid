"""Portable only. No Apple command runs; process faults use mocks."""
import ast,base64,copy,hashlib,json,os,shutil,signal,stat,subprocess,tempfile,unittest
from pathlib import Path
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
  for key,value in [('GITHUB_REPOSITORY','other/repo'),('GITHUB_EVENT_NAME','workflow_dispatch'),('GITHUB_REF','refs/heads/apple-platforms'),('GITHUB_RUN_ATTEMPT','2'),('GITHUB_RUN_ID','0'),('GITHUB_WORKFLOW_SHA','b'*40),('CELLULOID_VALIDATION_SCOPE','photos-boundary-observation')]:
   with self.subTest(key=key),self.assertRaises(ValueError):d.validate_route(dict(env,**{key:value}))
 def test_no_runtime_regex_or_retry_argv(self):
  for action in ('build-for-testing','test-without-building'):
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

class OwnedReadTests(unittest.TestCase):
 def test_exact_regular_file_only(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);p=root/'owned';p.write_bytes(b'owned');self.assertEqual(d.owned_read(p,5),b'owned')
   with self.assertRaises(ValueError):d.owned_read(p,4)
   alias=root/'alias';alias.symlink_to(p)
   with self.assertRaises(ValueError):d.owned_read(alias,5)
   linked=root/'linked';os.link(p,linked)
   with self.assertRaises(ValueError):d.owned_read(p,5)
 def test_parent_alias_rejected(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);(root/'dir').mkdir();(root/'dir/f').write_bytes(b'x');(root/'alias').symlink_to(root/'dir',target_is_directory=True)
   with self.assertRaises(ValueError):d.owned_read(root/'alias/f',5)
 def test_foreign_owner_rejected(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'f';p.write_bytes(b'x')
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
   temp=Path(folder);(temp/'mac-job-clock.json').write_bytes(d.encoded({'source_sha':'a'*40,'execution_budget_seconds':2460,'started_monotonic':100.0,'started_unix':1000.0}))
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
   folder=Path(path);manifest,device,summary=self.fixture(folder);self.assertEqual(set(d.attachments(folder,manifest,device,summary)),set(d.NAMES))
 def test_stale_wrong_case_device_path_duplicate_timestamp_rejected(self):
  for field,value in [('testIdentifier','Other/testWrong()'),('deviceId','other'),('timestamp',201),('exportedFileName','../foreign'),('suggestedHumanReadableName','celluloid-roundtrip-other_0_00000000-0000-0000-0000-000000000000.jpg')]:
   with tempfile.TemporaryDirectory() as path:
    folder=Path(path);manifest,device,summary=self.fixture(folder)
    if field=='testIdentifier':manifest[0][field]=value
    else:manifest[0]['attachments'][0][field]=value
    with self.subTest(field=field),self.assertRaises(ValueError):d.attachments(folder,manifest,device,summary)
  with tempfile.TemporaryDirectory() as path:
   folder=Path(path);manifest,device,summary=self.fixture(folder);manifest[0]['attachments'].append(manifest[0]['attachments'][0])
   with self.assertRaises(ValueError):d.attachments(folder,manifest,device,summary)
 def test_symlink_and_extra_named_attachment_rejected(self):
  with tempfile.TemporaryDirectory() as path:
   folder=Path(path);manifest,device,summary=self.fixture(folder);(folder/'0.jpg').unlink();(folder/'0.jpg').symlink_to(folder/'1.jpg')
   with self.assertRaises(ValueError):d.attachments(folder,manifest,device,summary)

if __name__=='__main__':unittest.main()
