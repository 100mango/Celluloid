#!/usr/bin/env python3
"""Run the exact shipping UIKit pixel consumer before broad platform fan-out."""
import hashlib,json,os,sys,uuid
from pathlib import Path
from native_process import run
from native_fixture_handoff import layer_from_log,LAYER_FILE
from verify_required_interoperability import verify,CONSUMER

ROOT=Path(__file__).resolve().parents[1]

def main():
    temp=Path(os.environ['RUNNER_TEMP']); source=os.environ['GITHUB_SHA']
    fixtures=temp/'early-uikit-fixtures';fixtures.mkdir(exist_ok=False)
    payload=layer_from_log(temp/'mac.log',source)
    (fixtures/LAYER_FILE).write_bytes(payload)
    (fixtures/'manifest.json').write_text(json.dumps({'source_sha':source,'files':[{'name':LAYER_FILE,'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}]}))
    runtimes=json.loads(run(['xcrun','simctl','list','runtimes','-j'],echo=False).stdout)['runtimes']
    runtime=next(r for r in runtimes if r.get('version')=='27.0' and r.get('isAvailable') and r['identifier'].startswith('com.apple.CoreSimulator.SimRuntime.iOS-'))
    types=json.loads(run(['xcrun','simctl','list','devicetypes','-j'],echo=False).stdout)['devicetypes']
    kind=next(t for t in types if t['name']=='iPhone SE (3rd generation)')
    udid=run(['xcrun','simctl','create','Celluloid Early UIKit Interoperability',kind['identifier'],runtime['identifier']]).stdout.strip()
    uuid.UUID(udid)  # Never operate on an unverified create response.
    derived=temp/'celluloid-early-uikit'; report={'source_sha':source,'udid':udid,'scope':'One original shipping UIKit consumer only; not full-platform acceptance.'}
    failure=None
    try:
        common=['xcodebuild','-project','Celluloid.xcodeproj','-scheme','Celluloid','-configuration','Debug','-destination',f'platform=iOS Simulator,id={udid}','-derivedDataPath',derived,'CODE_SIGNING_ALLOWED=NO','COMPILER_INDEX_STORE_ENABLE=NO']
        run(common+['-jobs','2','build-for-testing'],timeout=600,log_name='early-uikit-build.log')
        run(['xcrun','simctl','boot',udid],timeout=60)
        run(['xcrun','simctl','bootstatus',udid,'-b'],timeout=240)
        run([sys.executable,ROOT/'Scripts/stage_uikit_layer_fixture.py',udid,derived/'Build/Products/Debug-iphonesimulator/Celluloid.app',fixtures,'--output',temp/'early-uikit-staging.json'],timeout=600)
        result=run(common+['-resultBundlePath',temp/'CelluloidEarlyUIKit.xcresult','-parallel-testing-enabled','NO','-collect-test-diagnostics','never','-only-testing:CelluloidTests/'+CONSUMER.replace('.','/'),'test-without-building'],timeout=300,check=False,log_name='early-uikit-interop.log')
        report['test_exit_code']=result.returncode
        report['consumer']=verify('uikit',temp/'early-uikit-interop.log',fixtures,source)
        if result.returncode or not all(report['consumer']['checks'].values()):
            raise RuntimeError('Early UIKit strict pixel consumer failed; full matrix withheld, not accepted')
        report['pixel_passed']=True
    except Exception as error:
        failure=error;report['pixel_passed']=False;report['error']=str(error)
    finally:
        report['cleanup']=[]
        for action in ['shutdown','delete']:
            try:
                result=run(['xcrun','simctl',action,udid],timeout=45,check=False)
                report['cleanup'].append({'action':action,'exit_code':result.returncode})
            except Exception as error:report['cleanup'].append({'action':action,'error':str(error)})
        report['cleanup_passed']=len(report['cleanup'])==2 and all(row.get('exit_code')==0 for row in report['cleanup'])
        report['passed']=report.get('pixel_passed',False) and report['cleanup_passed']
        (temp/'early-uikit-interop.json').write_text(json.dumps(report,indent=2)+'\n')
        print('REQUIRED_INTEROPERABILITY_EARLY '+json.dumps(report,sort_keys=True))
    if failure is not None:raise failure
    if not report['cleanup_passed']:raise RuntimeError('Owned early UIKit simulator cleanup is unresolved; full matrix withheld')

if __name__=='__main__':main()
