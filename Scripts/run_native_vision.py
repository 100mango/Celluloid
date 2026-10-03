#!/usr/bin/env python3
"""Bounded native visionOS simulator run; no broad service-dump readiness gate."""
import json,os,signal,subprocess,sys,time,struct,zlib,plistlib
from pathlib import Path
root=Path(__file__).resolve().parents[1];temp=Path(os.environ['RUNNER_TEMP'])
from native_process import run
runtimes=json.loads(run(['xcrun','simctl','list','runtimes','--json'],echo=False).stdout)['runtimes']
types=json.loads(run(['xcrun','simctl','list','devicetypes','--json'],echo=False).stdout)['devicetypes']
possible=[r for r in runtimes if r.get('isAvailable') and ('vision' in r.get('name','').lower() or 'xros' in r.get('identifier','').lower())]
if not possible:raise RuntimeError('No available native visionOS runtime was found; SDK build does not establish runtime coverage')
runtime=sorted(possible,key=lambda r:tuple(int(x) for x in r['version'].split('.')),reverse=True)[0]
supported={t['identifier'] for t in runtime.get('supportedDeviceTypes',[])}
compatible=[t for t in types if not supported or t['identifier'] in supported]
device_type=next(t for t in compatible if 'Apple Vision Pro' in t['name'])
udid=run(['xcrun','simctl','create','Celluloid Native Vision Validation',device_type['identifier'],runtime['identifier']]).stdout.strip()
app=temp/'celluloid-vision/Build/Products/Debug-xrsimulator/CelluloidVision.app'
evidence={'runtime':runtime,'device_type':device_type,'udid':udid,'head':os.environ['GITHUB_SHA']}
try:
    run(['xcrun','simctl','boot',udid]);run(['xcrun','simctl','bootstatus',udid,'-b'],timeout=240)
    # Optional visual frontend is discovered and bundle/signature-checked. It
    # never becomes a prerequisite for the hosted document/decoder test lane.
    developer=Path(os.environ['DEVELOPER_DIR']).resolve()
    candidates=[developer/'Applications/Simulator.app',developer.parent/'Applications/Simulator.app',Path('/Applications/Simulator.app')]
    evidence['visual_window']={'candidates':[],'launched':False}
    try:
        discovery=run(['mdfind',"kMDItemCFBundleIdentifier == 'com.apple.iphonesimulator'"],timeout=15,check=False,echo=False)
        candidates += [Path(line) for line in discovery.stdout.splitlines()[:20]]
    except Exception as error:evidence['visual_window']['discovery_error']=str(error)
    seen=set()
    for candidate in candidates[:23]:
        candidate=candidate.resolve()
        if str(candidate) in seen:continue
        seen.add(str(candidate));record={'path':str(candidate),'exists':candidate.is_dir()}
        evidence['visual_window']['candidates'].append(record)
        if not candidate.is_dir() or not (candidate.is_relative_to(developer.parent) or candidate==Path('/Applications/Simulator.app')):continue
        try:
            info_path=candidate/'Contents/Info.plist'
            if info_path.stat().st_size>1_000_000:continue
            info=plistlib.loads(info_path.read_bytes());record['bundle_id']=info.get('CFBundleIdentifier');record['version']=info.get('CFBundleShortVersionString')
            if info.get('CFBundleIdentifier')!='com.apple.iphonesimulator' or info.get('CFBundleExecutable')!='Simulator':continue
            verified=run(['codesign','--verify','--strict','-R','anchor apple',candidate],timeout=20,check=False)
            record['apple_signature_exit_code']=verified.returncode
            if verified.returncode:continue
            opened=run(['open','-a',candidate,'--args','-CurrentDeviceUDID',udid],timeout=30,check=False)
            record['open_exit_code']=opened.returncode;evidence['visual_window']['launched']=opened.returncode==0
            if opened.returncode==0:break
        except Exception as error:record['error']=str(error)
    run(['xcrun','simctl','install',udid,app],timeout=300)
    # Seed a generated PNG in our own disposable app's Documents for real Files-picker traversal.
    container=Path(run(['xcrun','simctl','get_app_container',udid,'Mango.Celluloid','data']).stdout.strip())
    documents=container/'Documents';documents.mkdir(exist_ok=True)
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    row=b''.join(bytes((240,40,30,255)) if x<600 else bytes((30,110,240,255)) for x in range(1200))
    png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1200,800,8,6,0,0,0))+chunk(b'sRGB',b'\0')+chunk(b'IDAT',zlib.compress((b'\0'+row)*800))+chunk(b'IEND',b'')
    (documents/'VisionSynthetic.png').write_bytes(png)
    evidence['fixture']='Own app Documents/VisionSynthetic.png, generated1200x800 sRGB; real user-selected Files import remains under XCTest'
    launch=run(['xcrun','simctl','launch',udid,'Mango.Celluloid'],timeout=60)
    evidence['launch_output']=launch.stdout
    pid=launch.stdout.strip().rsplit(':',1)[-1].strip(); assert pid.isdigit()
    time.sleep(4)
    proc=run(['ps','-p',pid,'-o','pid=,comm='],timeout=20)
    evidence['process']=proc.stdout;assert 'CelluloidVision' in proc.stdout
    run(['xcrun','simctl','io',udid,'screenshot','--type=jpeg',temp/'native-vision-launch.jpg'],timeout=45,check=False)
    result=run(['xcodebuild','-project','CelluloidNative.xcodeproj','-scheme','CelluloidVision','-destination',f'platform=visionOS Simulator,id={udid}','-derivedDataPath',temp/'celluloid-vision','-resultBundlePath',temp/'CelluloidVision.xcresult','CODE_SIGNING_ALLOWED=NO','-parallel-testing-enabled','NO','-maximum-concurrent-test-simulator-destinations','1','test-without-building'],timeout=600,check=False,log_name='vision-runtime-tests.log')
    evidence['test_exit_code']=result.returncode
    if result.returncode:raise RuntimeError('Native Vision test invocation failed; inspect actual error/attachments, do not equate build or boot with E2E coverage')
except Exception as error:
    evidence['error']=str(error)
    raise
finally:
    (temp/'vision-runtime-evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    evidence['cleanup']=[]
    for action in ['shutdown','delete']:
        try:
            result=run(['xcrun','simctl',action,udid],timeout=45,check=False)
            evidence['cleanup'].append({'action':action,'exit_code':result.returncode})
        except Exception as error:evidence['cleanup'].append({'action':action,'error':str(error)})
    (temp/'vision-runtime-evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
