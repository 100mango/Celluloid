#!/usr/bin/env python3
"""Bounded native iOS companion simulator run; no broad service-dump readiness gate."""
import json,os,signal,subprocess,sys,time,re,base64,hashlib,shutil
from pathlib import Path
root=Path(__file__).resolve().parents[1];temp=Path(os.environ['RUNNER_TEMP'])
from native_process import run
runtimes=json.loads(run(['xcrun','simctl','list','runtimes','--json'],echo=False).stdout)['runtimes']
types=json.loads(run(['xcrun','simctl','list','devicetypes','--json'],echo=False).stdout)['devicetypes']
possible=[r for r in runtimes if r.get('isAvailable') and ('ios' == r.get('name','').lower().split(' ')[0])]
if not possible:raise RuntimeError('No available native iOS companion runtime was found; SDK build does not establish runtime coverage')
runtime=sorted(possible,key=lambda r:tuple(int(x) for x in r['version'].split('.')),reverse=True)[0]
supported={t['identifier'] for t in runtime.get('supportedDeviceTypes',[])}
compatible=[t for t in types if not supported or t['identifier'] in supported]
device_type=next(t for t in compatible if t['name']=='iPhone SE (3rd generation)')
udid=run(['xcrun','simctl','create','Celluloid Native Phone Companion Validation',device_type['identifier'],runtime['identifier']]).stdout.strip()
app=temp/'celluloid-phone/Build/Products/Debug-iphonesimulator/CelluloidPhoneCompanion.app'
evidence={'runtime':runtime,'device_type':device_type,'udid':udid,'head':os.environ['GITHUB_SHA']}
try:
    run(['xcrun','simctl','boot',udid]);run(['xcrun','simctl','bootstatus',udid,'-b'],timeout=240)
    run(['xcrun','simctl','install',udid,app],timeout=300)
    # Forward only newly generated synthetic Mac filter archives, with verified hashes.
    from native_fixture_handoff import load_exact
    fixtures=load_exact(temp/'mac-fixture-evidence',os.environ['GITHUB_SHA'])
    container=Path(run(['xcrun','simctl','get_app_container',udid,'Mango.Celluloid','data']).stdout.strip())
    documents=container/'Documents';documents.mkdir(exist_ok=True)
    assert app.parent.name=='Debug-iphonesimulator' and app.name=='CelluloidPhoneCompanion.app'
    from native_phone_fixture import seed
    evidence['synthetic_inbox']=seed(container,temp)
    (documents/'mac-filter-fixtures.json').write_text(json.dumps(fixtures["fixtures"]))
    (documents/'mac-baked-filter-fixture.json').write_text(json.dumps(fixtures["fallback"]))
    face=root/'CelluloidKit/CelluloidKit.xcassets/filter/OriginalFilter.imageset/OriginalFilter.png'
    assert hashlib.sha256(face.read_bytes()).hexdigest()=='378e569e25716ffc36c3e7622708ae1fab41ce99c870ae02f5874bb8aec45bfb'
    # Xcode copypng strips XMP even with compression disabled. Stage the existing
    # public source bytes unchanged as test input; never upload another portrait.
    shutil.copyfile(face,documents/'PublicFaceFixture.original')
    assert hashlib.sha256((documents/'PublicFaceFixture.original').read_bytes()).hexdigest()=='378e569e25716ffc36c3e7622708ae1fab41ce99c870ae02f5874bb8aec45bfb'
    launch=run(['xcrun','simctl','launch',udid,'Mango.Celluloid'],timeout=60)
    evidence['launch_output']=launch.stdout
    pid=launch.stdout.strip().rsplit(':',1)[-1].strip(); assert pid.isdigit()
    time.sleep(4)
    proc=run(['ps','-p',pid,'-o','pid=,comm='],timeout=20)
    evidence['process']=proc.stdout;assert 'CelluloidPhoneCompanion' in proc.stdout
    run(['xcrun','simctl','io',udid,'screenshot','--type=jpeg',temp/'native-phone-launch.jpg'],timeout=45,check=False)
    # End only our manually launched probe instance before XCTest owns its host.
    # This is a bounded lifecycle diagnostic; it does not presume the cause of
    # the prior completed-test/session-teardown timeout.
    stopped=run(['xcrun','simctl','terminate',udid,'Mango.Celluloid'],timeout=30,check=False)
    evidence['pretest_terminate_exit_code']=stopped.returncode
    test_error=None;result=None
    try:
        result=run(['xcodebuild','-project','CelluloidNative.xcodeproj','-scheme','CelluloidPhoneCompanion','-destination',f'platform=iOS Simulator,id={udid}','-derivedDataPath',temp/'celluloid-phone','-resultBundlePath',temp/'CelluloidPhoneCompanion.xcresult','CODE_SIGNING_ALLOWED=NO','-parallel-testing-enabled','NO','-maximum-concurrent-test-simulator-destinations','1','test-without-building'],timeout=900,check=False,log_name='phone-runtime-tests.log')
    except Exception as error:test_error=error;evidence['test_invocation_error']=str(error)
    if result is not None:evidence['test_exit_code']=result.returncode
    proof=container/'Library/Caches/PhoneOutputProof/photos-output.json'
    if proof.is_file():
        try:
            run(['swift','-swift-version','5',root/'Scripts/verify_phone_output.swift',temp/'PhoneCompanionSynthetic.png',container],timeout=120,log_name='phone-output-oracle.log')
            evidence['independent_output_oracle']='passed'
        except Exception as error:
            evidence['independent_output_oracle_error']=str(error)
            if test_error is None:test_error=error
    else:evidence['independent_output_oracle']='no completed Photos output proof'
    if test_error is not None:raise test_error
    if result is None or result.returncode:raise RuntimeError('Native Phone Companion tests failed; completed UI proof is separate from the actual failed cases')
    if not proof.is_file():raise RuntimeError('The real companion Photos UI did not produce readback proof')

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
