#!/usr/bin/env python3
"""Bounded native iOS companion simulator run; no broad service-dump readiness gate."""
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
possible=[r for r in runtimes if r.get('isAvailable') and ('ios' == r.get('name','').lower().split(' ')[0])]
if not possible:raise RuntimeError('No available native iOS companion runtime was found; SDK build does not establish runtime coverage')
runtime=sorted(possible,key=lambda r:tuple(int(x) for x in r['version'].split('.')),reverse=True)[0]
supported={t['identifier'] for t in runtime.get('supportedDeviceTypes',[])}
compatible=[t for t in types if not supported or t['identifier'] in supported]
device_type=next(t for t in compatible if t['name'].startswith('iPhone'))
udid=run(['xcrun','simctl','create','Celluloid Native Phone Companion Validation',device_type['identifier'],runtime['identifier']]).stdout.strip()
app=temp/'celluloid-phone/Build/Products/Debug-iphonesimulator/CelluloidPhoneCompanion.app'
evidence={'runtime':runtime,'device_type':device_type,'udid':udid,'head':os.environ['GITHUB_SHA']}
try:
    run(['xcrun','simctl','boot',udid]);run(['xcrun','simctl','bootstatus',udid,'-b'],timeout=240)
    run(['xcrun','simctl','install',udid,app],timeout=120)
    launch=run(['xcrun','simctl','launch',udid,'Mango.Celluloid'],timeout=60)
    evidence['launch_output']=launch.stdout
    pid=launch.stdout.strip().rsplit(':',1)[-1].strip(); assert pid.isdigit()
    time.sleep(4)
    proc=run(['ps','-p',pid,'-o','pid=,comm='],timeout=20)
    evidence['process']=proc.stdout;assert 'CelluloidPhoneCompanion' in proc.stdout
    run(['xcrun','simctl','io',udid,'screenshot',temp/'native-phone-launch.png'],timeout=45,check=False)
    result=run(['xcodebuild','-project','CelluloidNative.xcodeproj','-scheme','CelluloidPhoneCompanion','-destination',f'platform=iOS Simulator,id={udid}','-derivedDataPath',temp/'celluloid-phone','-resultBundlePath',temp/'CelluloidPhoneCompanion.xcresult','CODE_SIGNING_ALLOWED=NO','test-without-building'],timeout=600,check=False,log_name='phone-runtime-tests.log')
    evidence['test_exit_code']=result.returncode
    if result.returncode:raise RuntimeError('Native Phone Companion test invocation failed; inspect actual error/attachments, do not equate build or boot with E2E coverage')
except Exception as error:
    evidence['error']=str(error)
    raise
finally:
    (temp/'phone-runtime-evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    evidence['cleanup']=[]
    for action in ['shutdown','delete']:
        try:
            result=run(['xcrun','simctl',action,udid],timeout=45,check=False)
            evidence['cleanup'].append({'action':action,'exit_code':result.returncode})
        except Exception as error:evidence['cleanup'].append({'action':action,'error':str(error)})
    (temp/'phone-runtime-evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
