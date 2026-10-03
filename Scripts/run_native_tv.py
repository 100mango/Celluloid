#!/usr/bin/env python3
"""Bounded native tvOS simulator run; no broad service-dump readiness gate."""
import json,os,signal,subprocess,sys,time,struct,zlib
from pathlib import Path
root=Path(__file__).resolve().parents[1];temp=Path(os.environ['RUNNER_TEMP'])
def run(args,timeout=180,check=True,log_name=None):
    print('+ '+' '.join(map(str,args)),flush=True)
    process=subprocess.Popen(list(map(str,args)),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
    timed_out=False
    try:
        stdout,stderr=process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out=True
        os.killpg(process.pid,signal.SIGTERM)
        try: stdout,stderr=process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL);stdout,stderr=process.communicate()
    print(stdout,flush=True);print(stderr,file=sys.stderr,flush=True)
    if log_name:(temp/log_name).write_text(stdout+'\n'+stderr)
    if timed_out:raise TimeoutError(f'{args[0]} exceeded {timeout}s; process group stopped and partial output retained')
    result=subprocess.CompletedProcess(args,process.returncode,stdout,stderr)
    if check and result.returncode:raise RuntimeError(f'{args[0]} exited {result.returncode}')
    return result
runtimes=json.loads(run(['xcrun','simctl','list','runtimes','--json']).stdout)['runtimes']
types=json.loads(run(['xcrun','simctl','list','devicetypes','--json']).stdout)['devicetypes']
possible=[r for r in runtimes if r.get('isAvailable') and ('tvos' in r.get('name','').lower() or 'tvos' in r.get('identifier','').lower())]
if not possible:raise RuntimeError('No available native tvOS runtime was found; SDK build does not establish runtime coverage')
runtime=sorted(possible,key=lambda r:tuple(int(x) for x in r['version'].split('.')),reverse=True)[0]
device_type=next(t for t in types if 'Apple TV 4K' in t['name'])
udid=run(['xcrun','simctl','create','Celluloid Native TV Validation',device_type['identifier'],runtime['identifier']]).stdout.strip()
app=temp/'celluloid-tv/Build/Products/Debug-appletvsimulator/CelluloidTV.app'
evidence={'runtime':runtime,'device_type':device_type,'udid':udid,'head':os.environ['GITHUB_SHA']}
try:
    run(['xcrun','simctl','boot',udid]);run(['xcrun','simctl','bootstatus',udid,'-b'],timeout=240)
    # Seed only this disposable simulator through the supported public simctl route.
    fixture=temp/'celluloid-tv-synthetic.png'
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    row=b''.join(bytes((255,0,0,255)) if x<400 else bytes((0,255,0,255)) if x<800 else bytes((0,0,255,255)) for x in range(1200))
    fixture.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1200,800,8,6,0,0,0))+chunk(b'sRGB',b'\0')+chunk(b'IDAT',zlib.compress((b'\0'+row)*800))+chunk(b'IEND',b''))
    run(['xcrun','simctl','addmedia',udid,fixture],timeout=60)
    evidence['synthetic_fixture']='1200x800 explicit sRGB red/green/blue PNG added with simctl addmedia'
    run(['xcrun','simctl','install',udid,app],timeout=120)
    launch=run(['xcrun','simctl','launch',udid,'Mango.Celluloid'],timeout=60)
    evidence['launch_output']=launch.stdout
    pid=launch.stdout.strip().rsplit(':',1)[-1].strip(); assert pid.isdigit()
    time.sleep(4)
    proc=run(['ps','-p',pid,'-o','pid=,comm='],timeout=20)
    evidence['process']=proc.stdout;assert 'CelluloidTV' in proc.stdout
    run(['xcrun','simctl','io',udid,'screenshot',temp/'native-tv-launch.png'],timeout=45,check=False)
    result=run(['xcodebuild','-project','CelluloidNative.xcodeproj','-scheme','CelluloidTV','-destination',f'platform=tvOS Simulator,id={udid}','-derivedDataPath',temp/'celluloid-tv','-resultBundlePath',temp/'CelluloidTV.xcresult','CODE_SIGNING_ALLOWED=NO','test-without-building'],timeout=600,check=False,log_name='tv-runtime-tests.log')
    evidence['test_exit_code']=result.returncode
    if result.returncode:raise RuntimeError('Native TV test invocation failed; inspect actual error/attachments, do not equate build or boot with E2E coverage')
except Exception as error:
    evidence['error']=str(error)
    raise
finally:
    (temp/'tv-runtime-evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    run(['xcrun','simctl','shutdown',udid],timeout=45,check=False)
    run(['xcrun','simctl','delete',udid],timeout=45,check=False)
