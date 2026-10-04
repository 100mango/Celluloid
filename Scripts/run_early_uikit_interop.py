#!/usr/bin/env python3
"""Run frozen shipping UIKit pixel consumers at real2x/3x before broad fan-out."""
import hashlib,json,os,re,subprocess,sys,time,uuid
from pathlib import Path
from native_process import run
from native_fixture_handoff import layer_from_log,LAYER_FILE
from verify_required_interoperability import verify,CONSUMER

ROOT=Path(__file__).resolve().parents[1]
PROFILES=[('2x','iPhone SE (3rd generation)',2.0),('3x','iPhone 18 Pro Max',3.0)]
ACTIVE_SECONDS=18*60  # Existing20min step retains at least2min for owned-device cleanup.
FROZEN_UIKIT_ROOTS=['Celluloid','CelluloidKit','CelluloidPhotoExtension','Celluloid.xcodeproj']
FROZEN_UIKIT_SHA='d9a9fe00b79b8199877d81ced8abac7bde4784b6'
FROZEN_UIKIT_FINGERPRINT='5b648707e5f204c18007cd1158ccea7622387cbb277c8fe09b42b7587283cc35'
DISPLAY=re.compile(r'^MAC_LAYER_UIKIT_COMPOSITOR_DISPLAY scale=([0-9.]+)$',re.MULTILINE)

def frozen_uikit_fingerprint():
    paths=subprocess.check_output(['git','ls-files','-z','--',*FROZEN_UIKIT_ROOTS],cwd=ROOT,text=True).split('\0')
    rows=[[p,hashlib.sha256((ROOT/p).read_bytes()).hexdigest()] for p in paths if p]
    return hashlib.sha256(json.dumps(rows,separators=(',',':')).encode()).hexdigest()

def main():
    temp=Path(os.environ['RUNNER_TEMP']); source=os.environ['GITHUB_SHA'];deadline=time.monotonic()+ACTIVE_SECONDS
    report={'source_sha':source,'frozen_uikit_source':FROZEN_UIKIT_SHA,'profiles':[],
            'active_budget_seconds':ACTIVE_SECONDS,'scope':'Two original shipping UIKit consumers at actual2x/3x; not full-platform acceptance.'}
    def bounded(args,timeout=180,**kwargs):
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('Early UIKit active budget exhausted; cleanup reserve retained')
        return run(args,timeout=min(timeout,remaining),**kwargs)
    try:
        fingerprint=frozen_uikit_fingerprint();report['uikit_production_fingerprint']=fingerprint
        if fingerprint!=FROZEN_UIKIT_FINGERPRINT:raise RuntimeError('Frozen original UIKit production bytes changed')
        fixtures=temp/'early-uikit-fixtures';fixtures.mkdir(exist_ok=False)
        payload=layer_from_log(temp/'mac.log',source)
        (fixtures/LAYER_FILE).write_bytes(payload)
        (fixtures/'manifest.json').write_text(json.dumps({'source_sha':source,'files':[{'name':LAYER_FILE,'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}]}))
        runtimes=json.loads(bounded(['xcrun','simctl','list','runtimes','-j'],echo=False).stdout)['runtimes']
        runtime=next(r for r in runtimes if r.get('version')=='27.0' and r.get('isAvailable') and r['identifier'].startswith('com.apple.CoreSimulator.SimRuntime.iOS-'))
        types=json.loads(bounded(['xcrun','simctl','list','devicetypes','-j'],echo=False).stdout)['devicetypes']
        derived=temp/'celluloid-early-uikit'
        common=['xcodebuild','-project','Celluloid.xcodeproj','-scheme','Celluloid','-configuration','Debug','-derivedDataPath',derived,'CODE_SIGNING_ALLOWED=NO','COMPILER_INDEX_STORE_ENABLE=NO']
        # Build once. Each real device installs the same producer and the staging
        # receipt verifies its exact executable hash before running XCTest.
        bounded(common+['-destination','generic/platform=iOS Simulator','-jobs','2','build-for-testing'],timeout=600,log_name='early-uikit-build.log')
        for profile,name,scale in PROFILES:
            row={'profile':profile,'device_type':name,'expected_scale':scale,'runtime':runtime['identifier'],'cleanup':[]};report['profiles'].append(row)
            udid=None
            try:
                if deadline-time.monotonic()<120:raise TimeoutError('Insufficient active budget for another owned device')
                kind=next(t for t in types if t['name']==name)
                response=bounded(['xcrun','simctl','create','Celluloid Early UIKit '+profile,kind['identifier'],runtime['identifier']]).stdout.strip()
                uuid.UUID(response);udid=response;row['udid']=udid
                bounded(['xcrun','simctl','boot',udid],timeout=60)
                bounded(['xcrun','simctl','bootstatus',udid,'-b'],timeout=240)
                staging=temp/('early-uikit-'+profile+'-staging.json')
                bounded([sys.executable,ROOT/'Scripts/stage_uikit_layer_fixture.py',udid,derived/'Build/Products/Debug-iphonesimulator/Celluloid.app',fixtures,'--output',staging],timeout=600)
                row['staging']=json.loads(staging.read_text())
                log='early-uikit-'+profile+'-interop.log'
                result=bounded(common+['-destination',f'platform=iOS Simulator,id={udid}','-resultBundlePath',temp/('CelluloidEarlyUIKit'+profile+'.xcresult'),'-parallel-testing-enabled','NO','-collect-test-diagnostics','never','-only-testing:CelluloidTests/'+CONSUMER.replace('.','/'),'test-without-building'],timeout=300,check=False,log_name=log)
                row['test_exit_code']=result.returncode
                row['consumer']=verify('uikit',temp/log,fixtures,source)
                displays=DISPLAY.findall((temp/log).read_text());row['actual_scales']=displays
                row['actual_scale_verified']=len(displays)==1 and float(displays[0])==scale
                row['pixel_passed']=result.returncode==0 and all(row['consumer']['checks'].values()) and row['actual_scale_verified']
                if not row['pixel_passed']:raise RuntimeError('Early UIKit strict pixel/scale consumer failed; full matrix withheld, not accepted')
            except Exception as error:row['pixel_passed']=False;row['error']=str(error)
            finally:
                if udid is not None:
                    for action in ['shutdown','delete']:
                        try:
                            result=run(['xcrun','simctl',action,udid],timeout=45,check=False)
                            row['cleanup'].append({'action':action,'exit_code':result.returncode})
                        except Exception as error:row['cleanup'].append({'action':action,'error':str(error)})
                row['cleanup_passed']=len(row['cleanup'])==2 and all(c.get('exit_code')==0 for c in row['cleanup'])
                row['passed']=row.get('pixel_passed',False) and row['cleanup_passed']
                (temp/'early-uikit-interop.json').write_text(json.dumps(report,indent=2)+'\n')
            # A pixel mismatch still runs the other genuine display control. An
            # unresolved device teardown must not start another owned device.
            if not row['cleanup_passed']:break
        hashes=[p.get('staging',{}).get('binary_sha256') for p in report['profiles']]
        report['same_built_app_verified']=len(hashes)==2 and None not in hashes and len(set(hashes))==1
    except Exception as error:report['setup_error']=str(error)
    finally:
        report['pixel_passed']=len(report['profiles'])==2 and all(p.get('pixel_passed',False) for p in report['profiles'])
        report['cleanup_passed']=len(report['profiles'])==2 and all(p.get('cleanup_passed',False) for p in report['profiles'])
        report['passed']=report['pixel_passed'] and report['cleanup_passed'] and report.get('same_built_app_verified',False) and 'setup_error' not in report
        (temp/'early-uikit-interop.json').write_text(json.dumps(report,indent=2)+'\n')
        print('REQUIRED_INTEROPERABILITY_EARLY '+json.dumps(report,sort_keys=True))
    if not report['passed']:raise RuntimeError('Early UIKit pixel/scale/binary/cleanup gate failed; full matrix withheld; inspect preserved per-device diagnoses')

if __name__=='__main__':main()
