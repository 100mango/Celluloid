#!/usr/bin/env python3
"""Bounded native watchOS simulator run; no broad service-dump readiness gate."""
import json,os,signal,subprocess,sys,time,struct,zlib,hashlib
from pathlib import Path
root=Path(__file__).resolve().parents[1];temp=Path(os.environ['RUNNER_TEMP'])
from ios_watch_archive_capture import capture
# Reuse the qualified bounded collector; no new process framework or fixture path.
focused_stopped=False
focused_cleaning=False
focused_clock=json.loads((temp/'watch-focused-evidence/report.json').read_bytes())['started_monotonic']
if type(focused_clock) not in (int,float) or not 0 <= time.monotonic()-focused_clock < 2200:
    raise RuntimeError('Missing or expired original Watch job clock')
def run(args,timeout=180,check=True,log_name=None,echo=True):
    global focused_stopped
    if focused_stopped: raise RuntimeError('Owned command completion unknown; further commands forbidden')
    deadline=focused_clock+(2350 if focused_cleaning else 2200)
    if time.monotonic()+timeout+20 > deadline:
        raise RuntimeError('Original Watch clock cannot admit the complete command and owned-cleanup allowance')
    args=list(map(str,args))
    print('+ '+' '.join(args),flush=True)
    try:
        value=capture(args,seconds=timeout,cap=16*1024*1024,cleanup_grace=10)
    except BaseException as error:
        focused_stopped=True
        prefix=getattr(error,'stdout_prefix',b'');errors=getattr(error,'stderr_capture',b'')
        if echo:print(prefix.decode('utf8','replace'),flush=True);print(errors.decode('utf8','replace'),file=sys.stderr,flush=True)
        if log_name:(temp/log_name).write_bytes(prefix+b'\n'+errors)
        raise
    result=subprocess.CompletedProcess(args,value.returncode,value.stdout.decode('utf8','replace'),value.stderr.decode('utf8','replace'))
    if echo:print(result.stdout,flush=True);print(result.stderr,file=sys.stderr,flush=True)
    if log_name:(temp/log_name).write_text(result.stdout+'\n'+result.stderr)
    if result.returncode < 0:
        focused_stopped=True
        raise RuntimeError('Owned command terminated by signal; no later native command admitted')
    if check and result.returncode:raise RuntimeError(f'{args[0]} exited {result.returncode}')
    return result
def optional_diagnostic(args,timeout=45):
    # Nonzero terminal screenshots remain optional. Timeout/uncertainty cannot
    # be swallowed and followed by another native command.
    result=run(args,timeout=timeout,check=False)
    return {'exit_code':result.returncode,'succeeded':result.returncode==0}
runtimes=json.loads(run(['xcrun','simctl','list','runtimes','--json'],echo=False).stdout)['runtimes']
types=json.loads(run(['xcrun','simctl','list','devicetypes','--json'],echo=False).stdout)['devicetypes']
possible=[r for r in runtimes if r.get('isAvailable') and ('watchos' in r.get('name','').lower() or 'watchos' in r.get('identifier','').lower())]
if not possible:raise RuntimeError('No available native watchOS runtime was found; SDK build does not establish runtime coverage')
runtime=sorted(possible,key=lambda r:tuple(int(x) for x in r['version'].split('.')),reverse=True)[0]
if runtime.get('version') != '27.0': raise RuntimeError('Focused case requires the observed watchOS 27.0 runtime')
from native_watch_profiles import select_profiles
profiles=[item for item in select_profiles(runtime,types) if item[0]=='small']
if len(profiles)!=1: raise RuntimeError('Expected exactly one observed 40mm Watch profile')
FOCUSED_CASE='CelluloidWatchUITests/NativeWatchUITests/testOfflinePhotoCompanionUnavailableCancelRelaunchDeleteAndPrivacy'
app=temp/'celluloid-watch/Build/Products/Debug-watchsimulator/CelluloidWatch.app'
binary=app/'CelluloidWatch'
binary_sha=hashlib.sha256(binary.read_bytes()).hexdigest()

def validate_profile(profile,device_type):
    prefix='watch' if profile=='baseline' else 'watch-'+profile
    bundle='CelluloidWatch' if profile=='baseline' else 'CelluloidWatch'+profile.title()
    udid=run(['xcrun','simctl','create','Celluloid Native Watch '+profile,device_type['identifier'],runtime['identifier']]).stdout.strip()
    evidence={'runtime':runtime,'device_type':device_type,'profile':profile,'udid':udid,'head':os.environ['GITHUB_SHA'],'executable_sha256':binary_sha,
              'coverage':'single 40mm deletion/cancel/relaunch UI regression only; unchanged app-owned fixture; no hosted test or transfer execution'}
    try:
        run(['xcrun','simctl','boot',udid]);run(['xcrun','simctl','bootstatus',udid,'-b'],timeout=240)
        run(['xcrun','simctl','install',udid,app],timeout=120)
        # Seed only our disposable app container, not the system Photos database.
        container=Path(run(['xcrun','simctl','get_app_container',udid,'Mango.Celluloid.watchkitapp','data']).stdout.strip())
        gallery=container/'Library/Application Support/SelectedPhotos';gallery.mkdir(parents=True,exist_ok=True)
        photo_id='A2E0E7B0-0A3B-47D3-94E5-309F3614E54A'
        def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
        row=bytes((40,120,220,255))*128
        png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',128,80,8,6,0,0,0))+chunk(b'sRGB',b'\0')+chunk(b'IDAT',zlib.compress((b'\0'+row)*80))+chunk(b'IEND',b'')
        records=[]
        for identity,name in [(photo_id,'Synthetic Offline Photo'),('B2E0E7B0-0A3B-47D3-94E5-309F3614E54B','Synthetic Removal Photo')]:
            (gallery/(identity+'.source')).write_bytes(png);(gallery/(identity+'.preview')).write_bytes(png)
            records.append({'id':identity,'name':name,'width':128,'height':80,'sourceSHA256':hashlib.sha256(png).hexdigest()})
        (gallery/'index.json').write_text(json.dumps(records))
        evidence['fixture']='Seeded synthetic app-owned offline gallery; not a system Photos import or paired transfer'
        launch=run(['xcrun','simctl','launch',udid,'Mango.Celluloid.watchkitapp'],timeout=60)
        evidence['launch_output']=launch.stdout
        pid=launch.stdout.strip().rsplit(':',1)[-1].strip(); assert pid.isdigit()
        time.sleep(4)
        proc=run(['ps','-p',pid,'-o','pid=,comm='],timeout=20)
        evidence['process']=proc.stdout;assert 'CelluloidWatch' in proc.stdout
        evidence['launch_screenshot']=optional_diagnostic(['xcrun','simctl','io',udid,'screenshot','--type=jpeg',temp/(prefix+'-launch.jpg')],timeout=45)
        command=['xcodebuild','-project','CelluloidNative.xcodeproj','-scheme','CelluloidWatch','-destination',f'platform=watchOS Simulator,id={udid}','-derivedDataPath',temp/'celluloid-watch','-resultBundlePath',temp/(bundle+'.xcresult'),'CODE_SIGNING_ALLOWED=NO','-parallel-testing-enabled','NO','-collect-test-diagnostics','never','-maximum-concurrent-test-simulator-destinations','1','test-without-building']
        command += ['-only-testing:'+FOCUSED_CASE, '-test-iterations','1']
        result=run(command,timeout=600 if profile == 'baseline' else 420,check=False,log_name=prefix+'-runtime-tests.log')
        assert hashlib.sha256(binary.read_bytes()).hexdigest()==binary_sha, 'The built executable changed between endpoint tests'
        evidence['test_exit_code']=result.returncode
        print('WATCH_ENDPOINT_RESULT '+json.dumps({'profile':profile,'device':device_type['name'],'exit_code':result.returncode,'coverage':evidence['coverage']}))
        if result.returncode:raise RuntimeError('Native Watch test invocation failed; inspect actual error/attachments, do not equate build or boot with E2E coverage')
    except Exception as error:
        evidence['error']=str(error)
        raise
    finally:
        global focused_cleaning
        focused_cleaning=True
        evidence['owned_process_completion_confirmed']=not focused_stopped
        evidence['cleanup_unconfirmed']=focused_stopped
        (temp/(prefix+'-runtime-evidence.json')).write_text(json.dumps(evidence,indent=2)+'\n')
        evidence['cleanup']=[]
        for action in ([] if focused_stopped else ['shutdown','delete']):
            try:
                result=run(['xcrun','simctl',action,udid],timeout=45,check=False)
                evidence['cleanup'].append({'action':action,'exit_code':result.returncode})
            except Exception as error:
                evidence['cleanup'].append({'action':action,'error':str(error)})
                break # No second cleanup command after a failed/unknown first one.
        evidence['owned_process_completion_confirmed']=not focused_stopped
        evidence['cleanup_unconfirmed']=focused_stopped
        (temp/(prefix+'-runtime-evidence.json')).write_text(json.dumps(evidence,indent=2)+'\n')
        if focused_stopped or evidence['cleanup'] != [{'action':'shutdown','exit_code':0},{'action':'delete','exit_code':0}]:
            raise RuntimeError(evidence.get('error','Native Watch cleanup incomplete')+'; original runtime result retained; no later native command')

errors=[]
for profile,device_type in profiles:
    try: validate_profile(profile,device_type)
    except Exception as error:
        errors.append({'profile':profile,'error':str(error)})
        print('WATCH_ENDPOINT_FAILURE '+json.dumps(errors[-1]),flush=True)
if errors: raise RuntimeError('Watch profile failures: '+json.dumps(errors))
