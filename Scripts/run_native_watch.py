#!/usr/bin/env python3
"""Bounded native watchOS simulator run; no broad service-dump readiness gate."""
import json,os,signal,subprocess,sys,time,struct,zlib,hashlib
from pathlib import Path
root=Path(__file__).resolve().parents[1];temp=Path(os.environ['RUNNER_TEMP'])
from native_process import run,optional_diagnostic
runtimes=json.loads(run(['xcrun','simctl','list','runtimes','--json'],echo=False).stdout)['runtimes']
types=json.loads(run(['xcrun','simctl','list','devicetypes','--json'],echo=False).stdout)['devicetypes']
possible=[r for r in runtimes if r.get('isAvailable') and ('watchos' in r.get('name','').lower() or 'watchos' in r.get('identifier','').lower())]
if not possible:raise RuntimeError('No available native watchOS runtime was found; SDK build does not establish runtime coverage')
runtime=sorted(possible,key=lambda r:tuple(int(x) for x in r['version'].split('.')),reverse=True)[0]
from native_watch_profiles import select_profiles
profiles=select_profiles(runtime,types)
app=temp/'celluloid-watch/Build/Products/Debug-watchsimulator/CelluloidWatch.app'
binary=app/'CelluloidWatch'
binary_sha=hashlib.sha256(binary.read_bytes()).hexdigest()

def validate_profile(profile,device_type):
    prefix='watch' if profile=='baseline' else 'watch-'+profile
    bundle='CelluloidWatch' if profile=='baseline' else 'CelluloidWatch'+profile.title()
    udid=run(['xcrun','simctl','create','Celluloid Native Watch '+profile,device_type['identifier'],runtime['identifier']]).stdout.strip()
    evidence={'runtime':runtime,'device_type':device_type,'profile':profile,'udid':udid,'head':os.environ['GITHUB_SHA'],'executable_sha256':binary_sha,
              'coverage':'hosted and UI' if profile=='baseline' else 'same exact built app and UI bundle; endpoint UI only'}
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
        command=['xcodebuild','-project','CelluloidNative.xcodeproj','-scheme','CelluloidWatch','-destination',f'platform=watchOS Simulator,id={udid}','-derivedDataPath',temp/'celluloid-watch','-resultBundlePath',temp/(bundle+'.xcresult'),'CODE_SIGNING_ALLOWED=NO','-parallel-testing-enabled','NO','-maximum-concurrent-test-simulator-destinations','1','test-without-building']
        if profile != 'baseline': command += ['-only-testing:CelluloidWatchUITests']
        result=run(command,timeout=600 if profile == 'baseline' else 420,check=False,log_name=prefix+'-runtime-tests.log')
        assert hashlib.sha256(binary.read_bytes()).hexdigest()==binary_sha, 'The built executable changed between endpoint tests'
        evidence['test_exit_code']=result.returncode
        print('WATCH_ENDPOINT_RESULT '+json.dumps({'profile':profile,'device':device_type['name'],'exit_code':result.returncode,'coverage':evidence['coverage']}))
        if result.returncode:raise RuntimeError('Native Watch test invocation failed; inspect actual error/attachments, do not equate build or boot with E2E coverage')
    except Exception as error:
        evidence['error']=str(error)
        raise
    finally:
        (temp/(prefix+'-runtime-evidence.json')).write_text(json.dumps(evidence,indent=2)+'\n')
        evidence['cleanup']=[]
        for action in ['shutdown','delete']:
            try:
                result=run(['xcrun','simctl',action,udid],timeout=45,check=False)
                evidence['cleanup'].append({'action':action,'exit_code':result.returncode})
            except Exception as error:evidence['cleanup'].append({'action':action,'error':str(error)})
        (temp/(prefix+'-runtime-evidence.json')).write_text(json.dumps(evidence,indent=2)+'\n')

errors=[]
for profile,device_type in profiles:
    try: validate_profile(profile,device_type)
    except Exception as error:
        errors.append({'profile':profile,'error':str(error)})
        print('WATCH_ENDPOINT_FAILURE '+json.dumps(errors[-1]),flush=True)
if errors: raise RuntimeError('Watch profile failures: '+json.dumps(errors))
