#!/usr/bin/env python3
"""Bounded native iOS companion simulator run; no broad service-dump readiness gate."""
import json,os,signal,subprocess,sys,time,re,base64,hashlib,shutil,plistlib
from pathlib import Path
root=Path(__file__).resolve().parents[1];temp=Path(os.environ['RUNNER_TEMP'])
if sys.argv[1:] not in [[],['--shipping']]:raise SystemExit('Usage: run_native_phone.py [--shipping]')
shipping=sys.argv[1:]==['--shipping']
product='Celluloid' if shipping else 'CelluloidPhoneCompanion'
project='Celluloid.xcodeproj' if shipping else 'CelluloidNative.xcodeproj'
scheme='CelluloidCompanion' if shipping else 'CelluloidPhoneCompanion'
from native_process import run,optional_diagnostic
runtimes=json.loads(run(['xcrun','simctl','list','runtimes','--json'],echo=False).stdout)['runtimes']
types=json.loads(run(['xcrun','simctl','list','devicetypes','--json'],echo=False).stdout)['devicetypes']
possible=[r for r in runtimes if r.get('isAvailable') and ('ios' == r.get('name','').lower().split(' ')[0])]
if not possible:raise RuntimeError('No available native iOS companion runtime was found; SDK build does not establish runtime coverage')
runtime=sorted(possible,key=lambda r:tuple(int(x) for x in r['version'].split('.')),reverse=True)[0]
supported={t['identifier'] for t in runtime.get('supportedDeviceTypes',[])}
compatible=[t for t in types if not supported or t['identifier'] in supported]
device_type=next(t for t in compatible if t['name']=='iPhone SE (3rd generation)')
udid=run(['xcrun','simctl','create','Celluloid Native Phone Companion Validation',device_type['identifier'],runtime['identifier']]).stdout.strip()
app=temp/'celluloid-phone/Build/Products/Debug-iphonesimulator'/(product+'.app')
info=plistlib.loads((app/'Info.plist').read_bytes())
assert info.get('CFBundleIdentifier')=='Mango.Celluloid' and info.get('CFBundleExecutable')==product
assert (info.get('CFBundleShortVersionString'),info.get('CFBundleVersion'))==('1.1','2')
evidence={'runtime':runtime,'device_type':device_type,'udid':udid,'head':os.environ['GITHUB_SHA'],'shipping_entry':shipping,'project':project,'scheme':scheme,'built_app':str(app),'bundle_version':info.get('CFBundleShortVersionString'),'bundle_build':info.get('CFBundleVersion')}
try:
    run(['xcrun','simctl','boot',udid]);run(['xcrun','simctl','bootstatus',udid,'-b'],timeout=240)
    if shipping:
        from verify_embedded_watch import verify
        embedded=verify(app,app.parent.parent/'Debug-watchsimulator/CelluloidWatch.app','simulator')
        (temp/'phone-embedded-watch.json').write_text(json.dumps(embedded,indent=2)+'\n')
        assert all(embedded['checks'].values()), 'Built shipping app must contain the exact Watch producer'
        evidence['embedded_watch']=embedded
    run(['xcrun','simctl','install',udid,app],timeout=300)
    installed=Path(run(['xcrun','simctl','get_app_container',udid,'Mango.Celluloid','app']).stdout.strip())
    installed_info=plistlib.loads((installed/'Info.plist').read_bytes())
    assert all(installed_info.get(k)==info.get(k) for k in ['CFBundleIdentifier','CFBundleExecutable','CFBundleShortVersionString','CFBundleVersion'])
    built_hash=hashlib.sha256((app/product).read_bytes()).hexdigest()
    assert hashlib.sha256((installed/product).read_bytes()).hexdigest()==built_hash
    evidence['installed_product']={'path':str(installed),'executable':product,'sha256':built_hash,'version':installed_info['CFBundleShortVersionString'],'build':installed_info['CFBundleVersion']}
    if shipping:
        from verify_embedded_watch import inventory
        assert inventory(installed/'Watch/CelluloidWatch.app')==inventory(app/'Watch/CelluloidWatch.app'), 'Installed nested Watch must preserve the verified product'
    if shipping:
        # This disposable shipping-companion lane starts from an explicitly
        # synthetic full-access prerequisite, separate from real prompt/denied/
        # limited coverage in the retained UIKit matrix. No TCC database edits.
        grant=run(['xcrun','simctl','privacy',udid,'grant','photos','Mango.Celluloid'],timeout=30)
        evidence['photos_prerequisite']={'scope':'synthetic shipping companion only; not consent-dialog E2E','method':'simctl privacy grant photos','exit_code':grant.returncode,'actual_authorization_required_by_hosted_test':True}
    # Forward only newly generated synthetic Mac filter archives, with verified hashes.
    from native_fixture_handoff import load_exact
    fixtures=load_exact(temp/'mac-fixture-evidence',os.environ['GITHUB_SHA'])
    container=Path(run(['xcrun','simctl','get_app_container',udid,'Mango.Celluloid','data']).stdout.strip())
    documents=container/'Documents';documents.mkdir(exist_ok=True)
    assert app.parent.name=='Debug-iphonesimulator' and app.name==product+'.app'
    from native_phone_fixture import seed
    evidence['synthetic_inbox']=seed(container,temp)
    evidence['synthetic_layout_inbox']=seed(container,temp,namespace='large-text')
    (documents/'mac-filter-fixtures.json').write_text(json.dumps(fixtures["fixtures"]))
    (documents/'mac-baked-filter-fixture.json').write_text(json.dumps(fixtures["fallback"]))
    layer_error=None
    if shipping:
        from native_fixture_handoff import load_layer_exact
        try:
            layer=load_layer_exact(temp/'mac-fixture-evidence',os.environ['GITHUB_SHA'])
            (documents/'mac-layer-fixture.json').write_text(json.dumps(layer['fixture']))
            evidence['layer_fixture_handoff']='exact source/manifest/hash verified'
        except (ValueError,KeyError,OSError) as error:
            layer_error=str(error);evidence['layer_fixture_handoff_error']=layer_error
            # Do not fabricate bytes or suppress the other real phone flows.
            # The layer case explicitly skips, then this required gate fails.

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
    evidence['process']=proc.stdout;assert str(installed/product) in proc.stdout
    evidence['launch_screenshot']=optional_diagnostic(['xcrun','simctl','io',udid,'screenshot','--type=jpeg',temp/'native-phone-launch.jpg'],timeout=45)
    # End only our manually launched probe instance before XCTest owns its host.
    # This is a bounded lifecycle diagnostic; it does not presume the cause of
    # the prior completed-test/session-teardown timeout.
    stopped=run(['xcrun','simctl','terminate',udid,'Mango.Celluloid'],timeout=30,check=False)
    evidence['pretest_terminate_exit_code']=stopped.returncode
    test_error=None;result=None
    try:
        result=run(['xcodebuild','-project',project,'-scheme',scheme,'-destination',f'platform=iOS Simulator,id={udid}','-derivedDataPath',temp/'celluloid-phone','-resultBundlePath',temp/'CelluloidPhoneCompanion.xcresult','CODE_SIGNING_ALLOWED=NO','-parallel-testing-enabled','NO','-collect-test-diagnostics','never','-maximum-concurrent-test-simulator-destinations','1','test-without-building'],timeout=900,check=False,log_name='phone-runtime-tests.log')
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
    if shipping and layer_error is not None:raise RuntimeError('Required actual Mac layer interoperability handoff unavailable: '+layer_error)

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
