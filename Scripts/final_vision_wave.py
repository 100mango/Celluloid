#!/usr/bin/env python3
"""One immutable-product Vision UI method; no matrix, retry, archive or signing."""
from pathlib import Path
import argparse,hashlib,json,math,os,re,selectors,signal,stat,struct,subprocess,sys,time,zlib
from qualify_final_vision_wave_source import CONFIG,SOURCE,TREE,UI_METHODS,CONTROL_PATHS
ROOT=Path(__file__).resolve().parents[1]
CLOCK='final-vision-wave-clock.json'
UI_SECONDS=900
MAX_OUTPUT=1048576
from combined_evidence_budget import BUDGETS
MAX_EVIDENCE=BUDGETS['vision']
HOSTED=('testNativeVisionDocumentImportRenderSaveReopenAndExport','testSharedFieldMutationsRetainUnicodeAcrossBothOrdersUndoAndReopen','testPrepareVisionRemainingDocumentFixture','testNativeVisionExecutableAndSceneAreLive')
PRODUCER='testPrepareVisionRemainingDocumentFixture'
SHOTS={UI_METHODS[0]:('native-vision-launch','native-vision-editor-ready'),UI_METHODS[1]:('vision-imported-editable-bubble','vision-png-export-verified','vision-saved-document-reopened'),UI_METHODS[2]:(),UI_METHODS[3]:('vision-zh-Hans-privacy',)}
DEPENDENCIES={UI_METHODS[0]:'ui-created-document',UI_METHODS[1]:'own-generated-png',UI_METHODS[2]:'hosted-producer-package',UI_METHODS[3]:'ui-created-document'}
def need(value,reason):
 if not value:raise ValueError(reason)
check=need
def digest(raw):return hashlib.sha256(raw).hexdigest()
def encoded(value):return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def strict_json(raw):
 def pairs(items):
  out={}
  for k,v in items:need(k not in out,'duplicate-json-key');out[k]=v
  return out
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite-json')))

# Exact no-follow reader copied from the reviewed final-TV control.
def safe_read(path, cap):
    path = Path(path).absolute()
    parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    descriptor = None
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent); parent = child
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        before = os.fstat(descriptor)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 < before.st_size <= cap, 'unsafe-input')
        raw = b''
        while len(raw) < before.st_size:
            part = os.read(descriptor, min(65536, before.st_size - len(raw)))
            need(part, 'truncated-input'); raw += part
        def identity(value):
            return value.st_dev, value.st_ino, value.st_mode, value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns
        need(identity(before) == identity(os.fstat(descriptor)) == identity(os.stat(path.name, dir_fd=parent, follow_symlinks=False)), 'changed-input')
        return raw
    finally:
        if descriptor is not None: os.close(descriptor)
        os.close(parent)


# Owned-session helper reused from the fixed source/final-TV control; only the output ceiling is1MiB for Vision AX logs.
def number(value):
    return (type(value) is int and abs(value) <= 2**53) or (type(value) is float and math.isfinite(value))

def bounded_optional_process(command,command_deadline,cleanup_deadline,cap=8192,*,stop_on_signal_error=False):
    """One owned session; finite reads and absolute deadlines, including pipe EOF.

    Do not poll/reap the leader while a descendant can retain the pipe. Its PID
    stays reserved until group cleanup, so a signal cannot target a reused PID.
    No change is made to the mandatory host command or shared run_bounded helper.
    """
    check(number(command_deadline) and number(cleanup_deadline) and time.monotonic()<command_deadline<cleanup_deadline,'Invalid/expired optional process deadlines')
    check(type(cap) is int and 0<cap<=1048576,'Invalid optional output cap')
    check(type(stop_on_signal_error) is bool,'Invalid signal cleanup policy')
    check(signal.getsignal(signal.SIGCHLD)==signal.SIG_DFL,'Unknown child-reaping policy')
    started=time.monotonic();data=bytearray();eof=False;reaped=False;timed_out=False;overflow=False;cleanup_error=None
    process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True,bufsize=0)
    selector=None;pipe=process.stdout
    class SignalCleanupStopped(Exception):pass
    def drain(until):
        nonlocal eof,overflow
        while not eof and not overflow and time.monotonic()<until:
            if len(data)>=cap:overflow=True;break
            events=selector.select(max(0,min(0.1,until-time.monotonic())))
            for _,_ in events:
                if time.monotonic()>=until:break
                try:part=os.read(pipe.fileno(),min(4096,cap-len(data)))
                except BlockingIOError:continue
                if not part:eof=True;break
                data.extend(part)
    def signal_group(sig):
        nonlocal cleanup_error
        if reaped:return # Never signal after releasing the leader's PID.
        try:os.killpg(process.pid,sig)
        except ProcessLookupError:pass
        except OSError as error:
            cleanup_error=type(error).__name__
            if stop_on_signal_error:raise SignalCleanupStopped() from error
    try:
        selector=selectors.DefaultSelector()
        os.set_blocking(pipe.fileno(),False);selector.register(pipe,selectors.EVENT_READ)
        drain(command_deadline)
        if eof and not overflow:
            try:process.wait(timeout=max(0,command_deadline-time.monotonic()));reaped=True
            except subprocess.TimeoutExpired:timed_out=True
        else:timed_out=not overflow
        if not reaped:
            signal_group(signal.SIGTERM)
            term_deadline=min(cleanup_deadline,time.monotonic()+1)
            if not overflow:drain(term_deadline)
            # A completed leader may leave an ignoring descendant with the pipe.
            # Signal the same owned session before reaping that leader.
            signal_group(signal.SIGKILL)
            if not overflow:drain(cleanup_deadline)
            try:process.wait(timeout=max(0,cleanup_deadline-time.monotonic()));reaped=True
            except subprocess.TimeoutExpired:cleanup_error='direct child unreaped at absolute deadline'
    except SignalCleanupStopped:
        pass # Fixed staged metadata reads never switch signals after denial.
    except (OSError,ValueError) as error:
        cleanup_error=type(error).__name__
        try:signal_group(signal.SIGKILL)
        except SignalCleanupStopped:pass
        else:
            try:process.wait(timeout=max(0,cleanup_deadline-time.monotonic()));reaped=True
            except subprocess.TimeoutExpired:pass
    finally:
        if selector is not None:selector.close()
        pipe.close()
    finished=time.monotonic()
    if finished>command_deadline and not overflow:timed_out=True
    if finished>cleanup_deadline:cleanup_error='completion observed after absolute cleanup deadline'
    return {'return_code':process.returncode,'output':bytes(data),'bytes_read':len(data),'pipe_eof':eof,
        'child_reaped':reaped,'timed_out':timed_out,'overflow':overflow,'cleanup_error':cleanup_error,
        'finalized':eof and reaped and cleanup_error is None,'elapsed_seconds':finished-started,
        'command_deadline_monotonic':command_deadline,'cleanup_deadline_monotonic':cleanup_deadline}

# All time is measured from the first workflow step, before checkout.
NATIVE_SECONDS=1560
FINAL_SECONDS=1740
CLEANUP_RESERVE=120

def validate_config(c,env,enabled=True):
 keys={'schema','READY','platform','product_parent_sha','product_parent_tree','maximum_additional_spend_usd','confirmation','selected_method'}
 need(type(c) is dict and set(c)==keys,'config-fields')
 need(type(c['schema']) is int and c['schema']==1 and c['READY'] is enabled,'closed-or-schema')
 need(c['platform']=='vision' and c['product_parent_sha']==SOURCE and c['product_parent_tree']==TREE,'fixed-product')
 need(type(c['maximum_additional_spend_usd']) is int and c['maximum_additional_spend_usd']==0 and c['confirmation']=='RUN_ONE_UNSIGNED_PLATFORM_ZERO_USD','zero-dollar-confirmation')
 need(c['selected_method'] in UI_METHODS and env.get('VISION_WAVE_METHOD')==c['selected_method'],'single-whole-method')
 need(env.get('QUALIFICATION_PLATFORM')=='vision' and env.get('GITHUB_RUN_ATTEMPT')=='1','platform-or-attempt')
 return c

def validate_clock(c,env,now=None):
 need(type(c) is dict and set(c)=={'schema','control_sha','run_id','run_attempt','selected_method','started_monotonic','started_unix','native_seconds','final_seconds'},'clock-fields')
 need(c['schema']=='Celluloid.FinalVisionWaveClock.1','clock-schema')
 for field,key in [('control_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('run_attempt','GITHUB_RUN_ATTEMPT'),('selected_method','VISION_WAVE_METHOD')]:need(c[field]==env.get(key),'clock-identity-'+field)
 need(type(c['native_seconds']) is int and c['native_seconds']==NATIVE_SECONDS and type(c['final_seconds']) is int and c['final_seconds']==FINAL_SECONDS,'clock-budget')
 now=time.monotonic() if now is None else now
 for v in [c['started_monotonic'],c['started_unix'],now]:need(type(v) in (int,float) and math.isfinite(v) and v>0,'clock-number')
 need(c['started_monotonic']<=now,'clock-future')
 return c

def selectors_for(method):
 need(method in UI_METHODS,'unknown-ui-method')
 return {'ui':['-only-testing:CelluloidVisionUITests/NativeVisionUITests/'+method],
         'producer':['-only-testing:CelluloidVisionTests/NativeVisionTests/'+PRODUCER] if DEPENDENCIES[method]=='hosted-producer-package' else []}

def admit_ui(clock,now=None):
 now=time.monotonic() if now is None else now
 deadline=clock['started_monotonic']+NATIVE_SECONDS-CLEANUP_RESERVE
 need(now+UI_SECONDS+15<=deadline,'full-900-second-ui-plus-cleanup-does-not-fit')
 return deadline

def inspect_case(log,method,summary,kind='ui',udid=None,runtime_version=None):
 owner='CelluloidVisionUITests.NativeVisionUITests' if kind=='ui' else 'CelluloidVisionTests.NativeVisionTests'
 events=[]
 for line in log.splitlines():
  if line.startswith('Test Case '):
   m=re.fullmatch(r"Test Case '-\[([\w.]+) (\w+)\]' (started\.|(?:passed|failed|skipped) \([0-9.]+ seconds\)\.)",line)
   need(m is not None,'malformed-case-event')
   need((m[1],m[2])==(owner,method),'unexpected-case-executed')
   events.append(m[3].split()[0].rstrip('.'))
 need(events==['started','passed'],'selected-case-missing-failed-skipped-or-duplicate')
 for key,value in [('totalTestCount',1),('passedTests',1),('failedTests',0),('skippedTests',0)]:need(type(summary.get(key)) is int and summary[key]==value,'summary-'+key)
 need(not summary.get('testFailures') and summary.get('expectedFailures',0)==0,'summary-failures')
 if udid is not None:
  rows=summary.get('devicesAndConfigurations');need(type(rows) is list and len(rows)==1,'summary-device-count')
  device=rows[0].get('device',{});need(device.get('deviceId')==udid and device.get('osVersion')==runtime_version and device.get('architecture')=='arm64' and device.get('platform') in {'visionOS Simulator','xrOS Simulator'},'summary-runtime-binding')
  for k,v in [('passedTests',1),('failedTests',0),('skippedTests',0)]:need(type(rows[0].get(k)) is int and rows[0][k]==v,'summary-device-'+k)
 return {'method':method,'kind':kind,'events':events,'passed':True,'summary_counts':{k:summary[k] for k in ['totalTestCount','passedTests','failedTests','skippedTests']}}

def verify_producer(log,container):
 lines=[line.split(' ',1)[1] for line in log.splitlines() if line.startswith('VISION_REMAINING_FIXTURE_JSON ')]
 need(len(lines)==1,'one-producer-marker-required');v=strict_json(lines[0]);container=Path(container).resolve(strict=True)
 need(v.get('schema')=='Celluloid.VisionFixture.1' and v.get('bundle_identifier')=='Mango.Celluloid','producer-identity')
 need(v.get('pixel_width')==120 and v.get('pixel_height')==80 and v.get('initial_overlays')==0 and v.get('package_name')=='VisionRemaining.celluloid','producer-shape')
 need(Path(v.get('data_home','')).resolve(strict=True)==container,'producer-not-current-owned-container')
 docs=container/'Documents';package=docs/'VisionRemaining.celluloid'
 need(Path(v.get('documents_path','')).resolve(strict=True)==docs and Path(v.get('package_path','')).resolve(strict=True)==package,'producer-package-location')
 need(package.is_dir() and not package.is_symlink(),'producer-directory')
 files=v.get('files');need(type(files) is list and len(files)==2,'producer-file-count')
 names=[]
 for f in files:
  need(type(f) is dict and set(f)=={'name','bytes','sha256'},'producer-file-fields');name=f['name']
  need(type(name) is str and Path(name).name==name and (name=='recipe.json' or re.fullmatch(r'[0-9A-Fa-f-]{36}\.image',name)),'producer-file-name')
  need(name not in names and type(f['bytes']) is int and 0<f['bytes']<=1000000 and re.fullmatch('[0-9a-f]{64}',f['sha256']) is not None,'producer-file-identity');names.append(name)
  b=safe_read(package/name,1000000);need(len(b)==f['bytes'] and digest(b)==f['sha256'],'producer-file-hash')
 need('recipe.json' in names and sorted(p.name for p in package.iterdir())==sorted(names),'producer-exact-inventory')
 return v

def seed_png(container):
 documents=Path(container).resolve(strict=True)/'Documents';documents.mkdir(exist_ok=True)
 need(not documents.is_symlink(),'documents-symlink')
 def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
 row=b''.join(bytes((240,40,30,255)) if x<600 else bytes((30,110,240,255)) for x in range(1200))
 png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1200,800,8,6,0,0,0))+chunk(b'sRGB',b'\0')+chunk(b'IDAT',zlib.compress((b'\0'+row)*800))+chunk(b'IEND',b'')
 path=documents/'VisionSynthetic.png'
 with path.open('xb') as f:f.write(png)
 need(safe_read(path,1000000)==png,'png-readback')
 return {'path':str(path),'bytes':len(png),'sha256':digest(png),'width':1200,'height':800,'original_runner_algorithm_unchanged':True}

class VisionCommands:
 def __init__(self,temp):self.temp=temp;self.events=[];self.blocked=False
 def run(self,argv,label,*,deadline,seconds,cleanup=15,check_code=True,full=False):
  need(not self.blocked,'earlier-process-uncertain-or-timeout')
  now=time.monotonic();end=min(deadline,now+seconds)
  if full:need(now+seconds<=deadline,'full-command-window-does-not-fit')
  need(end-now>cleanup+0.1,'command-cleanup-reserve')
  need(re.fullmatch('[a-zA-Z0-9_.-]+',label) is not None,'log-label')
  log=self.temp/(label+'.log');need(not log.exists(),'duplicate-invocation-log')
  try:result=bounded_optional_process(list(map(str,argv)),end-cleanup,end,cap=MAX_OUTPUT,stop_on_signal_error=True)
  except BaseException as e:
   self.blocked=True;self.events.append({'label':label,'argv':list(map(str,argv)),'exception':type(e).__name__,'finalized':False});raise
  output=result.pop('output');log.write_bytes(output)
  event={'label':label,'argv':list(map(str,argv)),**result,'log':log.name,'log_bytes':len(output),'log_sha256':digest(output)};self.events.append(event)
  if not result['finalized'] or result['timed_out'] or result['overflow']:self.blocked=True
  need(result['finalized'],'process-cleanup-unconfirmed')
  need(not result['timed_out'] and not result['overflow'],'process-timeout-or-output-bound')
  if check_code:need(result['return_code']==0,'command-exit-'+str(result['return_code'])+'-'+label)
  return output.decode('utf8','replace'),result


def xctest_command(temp,udid,bundle,selection):
 return ['xcodebuild','-project','CelluloidNative.xcodeproj','-scheme','CelluloidVision','-destination','platform=visionOS Simulator,id='+udid,'-derivedDataPath',str(temp/'vision-wave-build'),'-resultBundlePath',str(bundle),'CODE_SIGNING_ALLOWED=NO','-parallel-testing-enabled','NO','-collect-test-diagnostics','never','-maximum-concurrent-test-simulator-destinations','1',*selection,'test-without-building']

def validate_inventory(root=ROOT):
 expected={'Platforms/VisionTests/NativeVisionTests.swift':HOSTED,'Platforms/VisionUITests/NativeVisionUITests.swift':UI_METHODS}
 out={}
 for rel,methods in expected.items():
  raw=safe_read(root/rel,200000);text=raw.decode();need(set(re.findall(r'\bfunc\s+(test\w+)\s*\(',text))==set(methods),'declared-original-inventory')
  need('XCTSkip' not in text,'source-skip');out[rel]=digest(raw)
 return out

def exported_images(folder,manifest,method):
 need(type(manifest) is list and len(manifest)<=16,'attachment-record-cap')
 need(all(type(r) is dict and type(r.get('attachments')) is list for r in manifest),'attachment-record')
 need(sum(len(r['attachments']) for r in manifest)<=1024,'attachment-item-cap')
 allowed=SHOTS[method];found={};seen=set()
 for record in manifest:
  for item in record['attachments']:
   need(type(item) is dict,'attachment-item');name=item.get('suggestedHumanReadableName','');path=item.get('exportedFileName')
   need(type(path) is str and Path(path).name==path and path not in {'','.','..'} and path not in seen,'attachment-path');seen.add(path)
   matches=[n for n in allowed if name==n or (type(name) is str and name.startswith(n+'_'))]
   if not matches:continue
   need(len(matches)==1,'ambiguous-shot-name');key=matches[0]
   need(record.get('testIdentifier')=='NativeVisionUITests/'+method+'()' and key not in found,'wrong-or-duplicate-shot-owner')
   raw=safe_read(folder/path,5000000);need(raw.startswith(b'\x89PNG\r\n\x1a\n') or raw.startswith(b'\xff\xd8\xff'),'shot-magic')
   found[key]={'source':str(folder/path),'bytes':len(raw),'sha256':digest(raw),'extension':'.png' if raw.startswith(b'\x89PNG') else '.jpg'}
 return found


def execute(env):
 os.chdir(ROOT);temp=Path(env['RUNNER_TEMP']).resolve(strict=True)
 config=validate_config(strict_json(safe_read(ROOT/CONFIG,16384)),env);clock=validate_clock(strict_json(safe_read(temp/CLOCK,16384)),env)
 method=config['selected_method'];key=str(UI_METHODS.index(method)+1);prefix='vision-wave-'+key+'-'+env['GITHUB_RUN_ID']+'-'+env['GITHUB_RUN_ATTEMPT']
 commands=VisionCommands(temp);work=clock['started_monotonic']+NATIVE_SECONDS;final=clock['started_monotonic']+FINAL_SECONDS
 report={'schema':'Celluloid.FinalVisionSingleMethodWave.1','control_sha':env['GITHUB_SHA'],'product_sha':SOURCE,'product_tree':TREE,'run_id':env['GITHUB_RUN_ID'],'run_attempt':env['GITHUB_RUN_ATTEMPT'],'selected_method':method,'omitted_ui_methods':[m for m in UI_METHODS if m!=method],'original_hosted_inventory':list(HOSTED),'original_ui_inventory':list(UI_METHODS),'retained_hosted_evidence':{'run_id':37909497562,'control_sha':'46fc7a5a41efea647dc27099ab9883187b8814ec','passed_methods':list(HOSTED),'new_execution_claim':False},'retained_release_evidence':{'run_id':37909497562,'binary_sha256':'a03d12bfb39b98a372bf9ea2f7bab01ecef13996fd8ef316e628cb1fcaf21e85','fresh_release_build':False},'fixture_dependency':DEPENDENCIES[method],'fixture_producer_selected':bool(selectors_for(method)['producer']),'clock':clock,'ui_limit_seconds':UI_SECONDS,'selected_method_passed':False,'wave_qualified':False,'all_eight_qualified':False,'archive_qualified':False,'required_screenshots':list(SHOTS[method]),'screenshots':{},'commands':commands.events,'errors':[],'omissions':[]}
 udid=None;bundle=temp/(prefix+'-ui.xcresult');ui_log=None;ui_result=None;summary=None
 def call(args,label,seconds,**kwargs):return commands.run(args,prefix+'-'+label,deadline=kwargs.pop('deadline',work-CLEANUP_RESERVE),seconds=seconds,**kwargs)
 try:
  report['source_inventory']=validate_inventory()
  v,_=call(['xcodebuild','-version'],'xcode',30);need(v.splitlines()[0]=='Xcode 27.0','xcode-version')
  for script in ['validate_native_sources.py','validate_native_localization.py','test_native_process.py','test_native_evidence.py','test_native_release.py']:
   call([sys.executable,'-B','-S','Scripts/'+script],script.replace('.py',''),90)
  call(['swift','-swift-version','5','Scripts/materialize_native_icons.swift'],'icons',105)
  call([sys.executable,'-B','-S','Scripts/verify_native_icon_inputs.py'],'icon-proof',30)
  call(['xcodebuild','-quiet','-project','CelluloidNative.xcodeproj','-scheme','CelluloidVision','-destination','generic/platform=visionOS Simulator','-derivedDataPath',temp/'vision-wave-build','CODE_SIGNING_ALLOWED=NO','build-for-testing'],'build',315)
  raw,_=call(['xcrun','simctl','list','runtimes','--json'],'runtimes',45);runtimes=strict_json(raw)['runtimes']
  raw,_=call(['xcrun','simctl','list','devicetypes','--json'],'device-types',45);types=strict_json(raw)['devicetypes']
  possible=[r for r in runtimes if r.get('isAvailable') and ('vision' in r.get('name','').lower() or 'xros' in r.get('identifier','').lower())];need(possible,'no-vision-runtime')
  runtime=sorted(possible,key=lambda r:tuple(int(x) for x in r['version'].split('.')),reverse=True)[0];supported={t['identifier'] for t in runtime.get('supportedDeviceTypes',[])}
  device=next(t for t in types if (not supported or t['identifier'] in supported) and 'Apple Vision Pro' in t['name']);report.update(runtime=runtime,device_type=device)
  raw,_=call(['xcrun','simctl','create',prefix,device['identifier'],runtime['identifier']],'create',45);udid=raw.strip();need(re.fullmatch(r'[0-9A-Fa-f-]{36}',udid),'invalid-device-id');report['udid']=udid
  call(['xcrun','simctl','boot',udid],'boot',195)
  call(['xcrun','simctl','bootstatus',udid,'-b'],'bootstatus',255)
  app=temp/'vision-wave-build/Build/Products/Debug-xrsimulator/CelluloidVision.app'
  call(['xcrun','simctl','install',udid,app],'install',315)
  # Preserve the existing separate pretest launch/PID/simctl capture. No
  # Chinese XCTest screenshot is removed, replaced, suppressed or deduplicated.
  raw,_=call(['xcrun','simctl','launch',udid,'Mango.Celluloid'],'pretest-launch',195)
  pid=raw.strip().rsplit(':',1)[-1].strip();need(pid.isdigit(),'pretest-launch-pid');time.sleep(4)
  raw,_=call(['ps','-p',pid,'-o','pid=,comm='],'pretest-process',35)
  need('CelluloidVision.app/CelluloidVision' in raw and raw.strip().startswith(pid+' '),'pretest-process-identity');report['pretest_process']=raw
  shot=temp/(prefix+'-native-vision-launch.jpg')
  _,capture_result=call(['xcrun','simctl','io',udid,'screenshot','--type=jpeg',shot],'pretest-screenshot',60,check_code=False)
  if capture_result['return_code']==0:
   raw_image=safe_read(shot,5000000);need(raw_image.startswith(b'\xff\xd8\xff'),'pretest-image-type')
   report['pretest_launch_image']={'path':str(shot),'sha256':digest(raw_image),'bytes':len(raw_image),'scope':'English pretest launch, never a substitute for the unchanged Chinese XCTest launch image'}
  else:report['omissions'].append('Optional pretest simctl launch screenshot exited '+str(capture_result['return_code']))
  call(['xcrun','simctl','terminate',udid,'Mango.Celluloid'],'pretest-terminate',45,check_code=False)
  selection=selectors_for(method)
  if selection['producer']:
   producer_bundle=temp/(prefix+'-producer.xcresult')
   producer_log,_=call(xctest_command(temp,udid,producer_bundle,selection['producer']),'producer-tests',195,full=True)
   raw,_=call(['xcrun','xcresulttool','get','test-results','summary','--path',producer_bundle],'producer-summary',60)
   report['producer_case']=inspect_case(producer_log,PRODUCER,strict_json(raw),'producer',udid,runtime['version'])
   raw,_=call(['xcrun','simctl','get_app_container',udid,'Mango.Celluloid','data'],'producer-container',195)
   report['producer_fixture']=verify_producer(producer_log,raw.strip())
  elif DEPENDENCIES[method]=='own-generated-png':
   raw,_=call(['xcrun','simctl','get_app_container',udid,'Mango.Celluloid','data'],'png-container',195);report['png_fixture']=seed_png(raw.strip())
  deadline=admit_ui(clock)
  ui_log,ui_result=call(xctest_command(temp,udid,bundle,selection['ui']),'ui-tests',UI_SECONDS+15,deadline=deadline,full=True,check_code=False)
 except BaseException as e:report['errors'].append(type(e).__name__+': '+str(e))
 finally:
  if udid and not commands.blocked:
   for action in ['shutdown','delete']:
    try:call(['xcrun','simctl',action,udid],action,60,deadline=work)
    except BaseException as e:
     report['errors'].append('cleanup '+action+': '+str(e))
     if commands.blocked:break
  elif udid:report['omissions'].append('No further native cleanup/exports after uncertain or timed-out command; disposable runner teardown remains required.')
 # Export only after known process completion. Required screenshots remain mandatory.
 if bundle.is_dir() and not commands.blocked:
  try:
   raw,_=call(['xcrun','xcresulttool','get','test-results','summary','--path',bundle],'ui-summary',60,deadline=final-60)
   summary=strict_json(raw);report['ui_summary']=summary
   need(ui_result is not None and ui_result['return_code']==0,'ui-process-not-successful')
   report['ui_case']=inspect_case(ui_log,method,summary,udid=udid,runtime_version=runtime['version']);report['selected_method_passed']=True
  except BaseException as e:report['errors'].append('case summary: '+str(e))
  if SHOTS[method] and not commands.blocked:
   try:
    folder=temp/(prefix+'-attachments');need(not folder.exists(),'attachment-dir-exists')
    call(['xcrun','xcresulttool','export','attachments','--path',bundle,'--output-path',folder],'attachments',75,deadline=final-45)
    report['screenshots']=exported_images(folder,strict_json(safe_read(folder/'manifest.json',262144)),method)
    need(set(report['screenshots'])==set(SHOTS[method]),'required-screenshot-missing')
   except BaseException as e:report['errors'].append('screenshots: '+str(e))
 report['process_blocked']=commands.blocked
 report['elapsed_seconds']=time.monotonic()-clock['started_monotonic']
 report['wave_qualified']=report['selected_method_passed'] and not report['errors'] and set(report['screenshots'])==set(SHOTS[method]) and not commands.blocked
 (temp/'vision-wave-report.json').write_bytes(encoded(report))
 print(json.dumps({'selected_method':method,'passed':report['selected_method_passed'],'wave_qualified':report['wave_qualified'],'errors':report['errors']}))
 return report


def validate_report_identity(report,env):
 need(type(report) is dict and report.get('schema')=='Celluloid.FinalVisionSingleMethodWave.1','report-schema')
 for key,value in [('control_sha',env['GITHUB_SHA']),('product_sha',SOURCE),('product_tree',TREE),('run_id',env['GITHUB_RUN_ID']),('run_attempt',env['GITHUB_RUN_ATTEMPT']),('selected_method',env['VISION_WAVE_METHOD'])]:need(report.get(key)==value,'report-identity-'+key)
 method=report['selected_method'];need(method in UI_METHODS and report.get('omitted_ui_methods')==[m for m in UI_METHODS if m!=method],'report-scope')
 need(report.get('original_hosted_inventory')==list(HOSTED) and report.get('original_ui_inventory')==list(UI_METHODS),'report-inventory')
 need(report.get('ui_limit_seconds')==UI_SECONDS and report.get('all_eight_qualified') is False and report.get('archive_qualified') is False,'report-claim')
 need(type(report.get('screenshots')) is dict and set(report['screenshots'])<=set(SHOTS[method]),'report-images')
 need(type(report.get('selected_method_passed')) is bool and type(report.get('wave_qualified')) is bool and type(report.get('errors')) is list,'report-status')
 if report['wave_qualified']:need(report['selected_method_passed'] and not report['errors'] and set(report['screenshots'])==set(SHOTS[method]),'unsupported-wave-success')
 return validate_clock(report['clock'],env)


def collect(env):
 temp=Path(env['RUNNER_TEMP']).resolve(strict=True);report=strict_json(safe_read(temp/'vision-wave-report.json',200000));clock=validate_report_identity(report,env)
 need(time.monotonic()<clock['started_monotonic']+FINAL_SECONDS-30,'collection-clock')
 before=strict_json(safe_read(temp/'combined-source-before.json',16384));after=strict_json(safe_read(temp/'combined-source-after.json',16384))
 need(before.get('phase')=='before' and after.get('phase')=='after','source-phases')
 before.pop('phase');after.pop('phase');need(before==after,'source-after-mismatch');need(after['source_sha']==env['GITHUB_SHA'] and after['product_parent_sha']==SOURCE and after['selected_method']==env['VISION_WAVE_METHOD'],'source-report-binding')
 out=temp/'vision-wave-evidence';out.mkdir();manifest={'source_sha':env['GITHUB_SHA'],'run_id':env['GITHUB_RUN_ID'],'selected_method':env['VISION_WAVE_METHOD'],'limit_bytes':MAX_EVIDENCE,'files':[],'omissions':[]};size=0
 def retain(name,raw,required=True):
  nonlocal size
  need(Path(name).name==name and name not in {'.','..'},'retention-name')
  if len(raw)>5000000 or size+len(raw)>MAX_EVIDENCE-150000:
   if required:raise ValueError('required-evidence-byte-cap-'+name)
   manifest['omissions'].append({'name':name,'reason':'byte-cap'});return
  (out/name).write_bytes(raw);size+=len(raw);manifest['files'].append({'name':name,'bytes':len(raw),'sha256':digest(raw)})
 for name in ['combined-source-before.json','combined-source-after.json']:retain(name,safe_read(temp/name,16384))
 for event in report['commands']:
  if 'log' in event and ('ui-tests' in event['label'] or 'producer-tests' in event['label'] or 'summary' in event['label']):
   need(Path(event['log']).name==event['log'],'log-path')
   if event['log_bytes']==0:manifest['omissions'].append({'name':event['log'],'reason':'empty captured output'});continue
   p=temp/event['log'];raw=safe_read(p,MAX_OUTPUT);need(len(raw)==event['log_bytes'] and digest(raw)==event['log_sha256'],'log-identity');retain(p.name,raw)
 if report.get('selected_method_passed') is True:
  try:
   tests=[e for e in report['commands'] if e.get('label','').endswith('-ui-tests')];summaries=[e for e in report['commands'] if e.get('label','').endswith('-ui-summary')]
   need(len(tests)==len(summaries)==1,'one-current-case-and-summary-required')
   for event in tests+summaries:
    need(event.get('finalized') is True and event.get('return_code')==0 and not event.get('timed_out') and not event.get('overflow'),'proof-command-not-passed')
   actual_summary=strict_json(safe_read(temp/summaries[0]['log'],MAX_OUTPUT));need(actual_summary==report['ui_summary'],'summary-replay-mismatch')
   replay=inspect_case(safe_read(temp/tests[0]['log'],MAX_OUTPUT).decode(),report['selected_method'],actual_summary,udid=report['udid'],runtime_version=report['runtime']['version'])
   need(replay==report['ui_case'],'case-replay-mismatch')
  except (ValueError,OSError,KeyError) as error:
   report['wave_qualified']=False;report['selected_method_passed']=False;report['errors'].append('retained proof replay: '+str(error))
 for name,row in report['screenshots'].items():
  expected_folder=temp/('vision-wave-'+str(UI_METHODS.index(env['VISION_WAVE_METHOD'])+1)+'-'+env['GITHUB_RUN_ID']+'-'+env['GITHUB_RUN_ATTEMPT']+'-attachments')
  need(Path(row['source']).parent==expected_folder,'image-not-owned-export')
  raw=safe_read(row['source'],5000000);need(len(raw)==row['bytes'] and digest(raw)==row['sha256'],'image-identity')
  if size+len(raw)>MAX_EVIDENCE-150000:
   report['wave_qualified']=False;report['errors'].append('required retained screenshot exceeds fixed byte cap: '+name);manifest['omissions'].append({'name':name,'reason':'required-image-byte-cap'})
  else:retain(name+row['extension'],raw)
 retain('report.json',encoded(report))
 for event in report['commands']:
  if 'log' in event and not (out/event['log']).exists():
   need(Path(event['log']).name==event['log'],'log-path')
   if event['log_bytes']==0:continue
   p=temp/event['log'];raw=safe_read(p,MAX_OUTPUT);need(len(raw)==event['log_bytes'] and digest(raw)==event['log_sha256'],'optional-log-identity');retain(p.name,raw[-24000:],False)
 if 'pretest_launch_image' in report:
  row=report['pretest_launch_image'];p=Path(row['path']);need(p.parent==temp and p.name.endswith('-native-vision-launch.jpg'),'pretest-image-path');raw=safe_read(p,5000000);need(len(raw)==row['bytes'] and digest(raw)==row['sha256'],'pretest-image-identity');retain(p.name,raw,False)
 retain('manifest.json',encoded(manifest));need(sum(p.stat().st_size for p in out.iterdir())<=MAX_EVIDENCE,'total-evidence-cap')
 with open(env['GITHUB_OUTPUT'],'a') as f:f.write('evidence_ready=true\n')
 return report


def main():
 parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['run','collect','admit-upload','finish-upload']);a=parser.parse_args();env=os.environ
 if a.phase=='run':raise SystemExit(0 if execute(env)['wave_qualified'] else 1)
 if a.phase=='collect':raise SystemExit(0 if collect(env)['wave_qualified'] else 1)
 else:
  temp=Path(env['RUNNER_TEMP']).resolve(strict=True);clock=validate_clock(strict_json(safe_read(temp/CLOCK,16384)),env)
  need(time.monotonic()<clock['started_monotonic']+FINAL_SECONDS,'upload-clock')
  if a.phase=='admit-upload':
   need(time.monotonic()+60<=clock['started_monotonic']+FINAL_SECONDS,'full-one-minute-upload-reserve')
   need((temp/'vision-wave-evidence/manifest.json').is_file(),'evidence-missing')
   with open(env['GITHUB_OUTPUT'],'a') as f:f.write('upload_admitted=true\n')
  else:need(env.get('VISION_WAVE_UPLOAD_OUTCOME')=='success','upload-failed')
if __name__=='__main__':main()
