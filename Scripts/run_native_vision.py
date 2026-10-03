#!/usr/bin/env python3
"""Bounded native visionOS simulator run; no broad service-dump readiness gate."""
import json,os,signal,subprocess,sys,time
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
possible=[r for r in runtimes if r.get('isAvailable') and ('vision' in r.get('name','').lower() or 'xros' in r.get('identifier','').lower())]
if not possible:raise RuntimeError('No available native visionOS runtime was found; SDK build does not establish runtime coverage')
runtime=sorted(possible,key=lambda r:tuple(int(x) for x in r['version'].split('.')),reverse=True)[0]
device_type=next(t for t in types if 'Apple Vision Pro' in t['name'])
udid=run(['xcrun','simctl','create','Celluloid Native Vision Validation',device_type['identifier'],runtime['identifier']]).stdout.strip()
app=temp/'celluloid-vision/Build/Products/Debug-xrsimulator/CelluloidVision.app'
evidence={'runtime':runtime,'device_type':device_type,'udid':udid,'head':os.environ['GITHUB_SHA']}
try:
    run(['xcrun','simctl','boot',udid]);run(['xcrun','simctl','bootstatus',udid,'-b'],timeout=240)
    run(['xcrun','simctl','install',udid,app],timeout=120)
    launch=run(['xcrun','simctl','launch',udid,'Mango.Celluloid'],timeout=60)
    evidence['launch_output']=launch.stdout
    pid=launch.stdout.strip().rsplit(':',1)[-1].strip(); assert pid.isdigit()
    time.sleep(4)
    proc=run(['ps','-p',pid,'-o','pid=,comm='],timeout=20)
    evidence['process']=proc.stdout;assert 'CelluloidVision' in proc.stdout
    run(['xcrun','simctl','io',udid,'screenshot',temp/'native-vision-launch.png'],timeout=45,check=False)
    result=run(['xcodebuild','-project','CelluloidNative.xcodeproj','-scheme','CelluloidVision','-destination',f'platform=visionOS Simulator,id={udid}','-derivedDataPath',temp/'celluloid-vision','-resultBundlePath',temp/'CelluloidVision.xcresult','CODE_SIGNING_ALLOWED=NO','test-without-building'],timeout=600,check=False,log_name='vision-runtime-tests.log')
    evidence['test_exit_code']=result.returncode
    if result.returncode:raise RuntimeError('Native Vision test invocation failed; inspect actual error/attachments, do not equate build or boot with E2E coverage')
except Exception as error:
    evidence['error']=str(error)
    raise
finally:
    (temp/'vision-runtime-evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    run(['xcrun','simctl','shutdown',udid],timeout=45,check=False)
    run(['xcrun','simctl','delete',udid],timeout=45,check=False)
