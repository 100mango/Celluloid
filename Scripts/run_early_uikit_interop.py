#!/usr/bin/env python3
"""Run frozen shipping UIKit pixel consumers at real2x/3x before broad fan-out."""
import hashlib,json,os,re,subprocess,sys,time,uuid
from pathlib import Path
from native_process import run
from uikit_installed_identity import readback as readback_installation
from file_open_observation import capture as capture_file_open_observation
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

def corrected_source_admission():
    mode=os.environ.get("CELLULOID_RENDERING_QUALIFICATION", "")
    if not mode:return None
    if mode!="corrected-v2":raise ValueError("Unknown rendering qualification mode")
    from corrected_rendering_admission import admit
    return admit()

def main():
    temp=Path(os.environ['RUNNER_TEMP']); source=os.environ['GITHUB_SHA'];deadline=time.monotonic()+ACTIVE_SECONDS
    report={'source_sha':source,'frozen_uikit_source':FROZEN_UIKIT_SHA,'profiles':[],
            'active_budget_seconds':ACTIVE_SECONDS,'scope':'Two original shipping UIKit consumers at actual2x/3x; not full-platform acceptance.'}
    def bounded(args,timeout=180,**kwargs):
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('Early UIKit active budget exhausted; cleanup reserve retained')
        corrected=os.environ.get('CELLULOID_RENDERING_QUALIFICATION')=='corrected-v2'
        if corrected:
            from corrected_rendering_admission import require_native_clear,mark_native_failure
            require_native_clear()
        try:return run(args,timeout=min(timeout,remaining),**kwargs)
        except BaseException as error:
            if corrected:mark_native_failure(error)
            raise
    def owned_cleanup(args):
        corrected=os.environ.get('CELLULOID_RENDERING_QUALIFICATION')=='corrected-v2'
        if corrected:
            from corrected_rendering_admission import require_native_clear,mark_native_failure
            require_native_clear()
        try:return run(args,timeout=45,check=False)
        except BaseException as error:
            if corrected:mark_native_failure(error)
            raise
    try:
        admission=corrected_source_admission()
        fingerprint=frozen_uikit_fingerprint();report['uikit_production_fingerprint']=fingerprint
        if admission is None:
            if fingerprint!=FROZEN_UIKIT_FINGERPRINT:raise RuntimeError('Frozen original UIKit production bytes changed')
        else:
            if fingerprint!=admission['current_uikit_fingerprint']:raise RuntimeError('Corrected UIKit source fingerprint changed')
            report['scope']='Two corrected-source UIKit consumers against immutable original2x/3x controls; not full-platform acceptance.'
            report.pop('frozen_uikit_source')
            report.update(source_mode='corrected-v2',corrected_source_admission=admission,
                          frozen_control_source=admission['frozen_control_source'])
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
                summary_result=bounded(['xcrun','xcresulttool','get','test-results','summary','--path',temp/('CelluloidEarlyUIKit'+profile+'.xcresult')],timeout=30,echo=False)
                summary=json.loads(summary_result.stdout)
                (temp/('CelluloidEarlyUIKit'+profile+'.xcresult.summary.json')).write_text(json.dumps(summary,indent=2)+'\n')
                row['consumer']=verify('uikit',temp/log,fixtures,source,platform_contract=True,runtime_summary=summary,expected_device={'id':udid,'model':name})
                displays=DISPLAY.findall((temp/log).read_text());row['actual_scales']=displays
                row['actual_scale_verified']=len(displays)==1 and float(displays[0])==scale
                row['pixel_passed']=row['consumer']['historical_strict_pixel_passed'] is True
                row['platform_contract_passed']=result.returncode==0 and all(row['consumer']['checks'].values()) and row['actual_scale_verified']
                if not row['platform_contract_passed']:raise RuntimeError('Early UIKit platform contract/scale consumer failed; full matrix withheld, not accepted')
            except Exception as error:row.setdefault('pixel_passed',False);row['platform_contract_passed']=False;row['error']=str(error)
            finally:
                if udid is not None:
                    if 'staging' in row and 'test_exit_code' in row:
                        try:
                            row['post_test_installation']=readback_installation(bounded,udid,row['staging'])
                        except Exception as error:
                            # Keep the original consumer diagnosis and always
                            # execute the owned shutdown/delete below.
                            row['post_test_installation_error']=type(error).__name__+': '+str(error)
                            row['platform_contract_passed']=False
                    try:
                        if time.monotonic()+40 < deadline and 'staging' in row:
                            observation=capture_file_open_observation(bounded,udid,source,row['staging']['binary_sha256'])
                        else:
                            observation={'source_sha':source,'device_id':udid,'observed_records_available':False,
                                'classified':False,'acceptance':False,'unavailable_reason':'No qualified staging or active time reserve for optional diagnostic'}
                        (temp/('early-uikit-'+profile+'-file-open-observation.json')).write_text(json.dumps(observation,indent=2)+'\n')
                    except Exception as error:
                        # Optional capture/serialization cannot prevent the owned
                        # shutdown/delete or replace the primary pixel failure.
                        row['file_open_observation_error']=type(error).__name__+': '+str(error)
                    for action in ['shutdown','delete']:
                        try:
                            result=owned_cleanup(['xcrun','simctl',action,udid])
                            row['cleanup'].append({'action':action,'exit_code':result.returncode})
                        except Exception as error:row['cleanup'].append({'action':action,'error':str(error)})
                row['cleanup_passed']=len(row['cleanup'])==2 and all(c.get('exit_code')==0 for c in row['cleanup'])
                row['passed']=row.get('platform_contract_passed',False) and row['cleanup_passed']
                (temp/'early-uikit-interop.json').write_text(json.dumps(report,indent=2)+'\n')
            # A pixel mismatch still runs the other genuine display control. An
            # unresolved device teardown must not start another owned device.
            if not row['cleanup_passed'] or 'post_test_installation_error' in row:break
        hashes=[p.get('staging',{}).get('binary_sha256') for p in report['profiles']]
        report['same_built_app_verified']=len(hashes)==2 and None not in hashes and len(set(hashes))==1
    except Exception as error:report['setup_error']=str(error)
    finally:
        report['pixel_passed']=len(report['profiles'])==2 and all(p.get('pixel_passed',False) for p in report['profiles'])
        report['cleanup_passed']=len(report['profiles'])==2 and all(p.get('cleanup_passed',False) for p in report['profiles'])
        report['platform_contract_passed']=report.get('same_built_app_verified',False) and len(report['profiles'])==2 and all(p.get('platform_contract_passed',False) for p in report['profiles'])
        report['passed']=report['platform_contract_passed'] and report['cleanup_passed'] and report.get('same_built_app_verified',False) and 'setup_error' not in report
        (temp/'early-uikit-interop.json').write_text(json.dumps(report,indent=2)+'\n')
        print('REQUIRED_INTEROPERABILITY_EARLY '+json.dumps(report,sort_keys=True))
    if not report['passed']:raise RuntimeError('Early UIKit pixel/scale/binary/cleanup gate failed; full matrix withheld; inspect preserved per-device diagnoses')

if __name__=='__main__':main()
