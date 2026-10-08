#!/usr/bin/env python3
"""Bounded grouped compile/package gate before fresh-VM functional validation."""
from pathlib import Path
import hashlib,json,os,plistlib,subprocess,sys,time
from native_process import run
from native_watch_profiles import select_profiles

ROOT=Path(__file__).resolve().parents[1]
DEBUG_PLANS=[
    ('phone','Celluloid.xcodeproj','CelluloidCompanion','iOS Simulator',['CelluloidCompanionTests','CelluloidCompanionUITests']),
    ('mac','CelluloidNative.xcodeproj','CelluloidMac','macOS',['CelluloidMacTests','CelluloidMacPhotosExtensionTests']),
    ('mac-ui','CelluloidNative.xcodeproj','CelluloidMacUI','macOS',['CelluloidMacUITests']),
    ('uikit','Celluloid.xcodeproj','Celluloid','iOS Simulator',['CelluloidTests','CelluloidUITests']),
    ('tv','CelluloidNative.xcodeproj','CelluloidTV','tvOS Simulator',['CelluloidTVTests','CelluloidTVUITests']),
    ('watch','CelluloidNative.xcodeproj','CelluloidWatch','watchOS Simulator',['CelluloidWatchTests','CelluloidWatchUITests']),
    ('vision','CelluloidNative.xcodeproj','CelluloidVision','visionOS Simulator',['CelluloidVisionTests','CelluloidVisionUITests']),
]
RELEASE_PLANS=[('phone','Celluloid.xcodeproj','Celluloid','iOS','Release-iphoneos'),
               ('mac','CelluloidNative.xcodeproj','CelluloidMac','macOS','Release'),
               ('tv','CelluloidNative.xcodeproj','CelluloidTV','tvOS','Release-appletvos'),
               ('watch','CelluloidNative.xcodeproj','CelluloidWatch','watchOS','Release-watchos'),
               ('vision','CelluloidNative.xcodeproj','CelluloidVision','visionOS','Release-xros')]

def available_setup(runtimes,device_types):
    chosen={}
    for label,prefix in [('ios','iOS '),('tv','tvOS '),('watch','watchOS '),('vision','visionOS ')]:
        rows=[r for r in runtimes if r.get('isAvailable') and r.get('name','').startswith(prefix) and r.get('version','').split('.')[0]=='27']
        if not rows:raise ValueError('Missing required SDK27 simulator runtime: '+label)
        chosen[label]=sorted(rows,key=lambda r:tuple(map(int,r['version'].split('.'))))[-1]
    supported=lambda kind:{r['identifier'] for r in chosen[kind].get('supportedDeviceTypes',[])}
    names={r['name']:r['identifier'] for r in device_types}
    for name in ['iPhone SE (3rd generation)','iPhone 18 Pro Max','iPad mini (A17 Pro)','iPad Pro 13-inch (M5)']:
        if names.get(name) not in supported('ios'):raise ValueError('Missing required UIKit profile: '+name)
    watch=select_profiles(chosen['watch'],device_types)
    for kind,needle in [('tv','Apple TV 4K'),('vision','Apple Vision Pro')]:
        if not any(needle in r['name'] and r['identifier'] in supported(kind) for r in device_types):raise ValueError('Missing required native profile: '+kind)
    return {'runtimes':{k:{x:r.get(x) for x in ['identifier','name','version','buildversion']} for k,r in chosen.items()},'watch_profiles':[{'profile':key,'name':r['name'],'identifier':r['identifier']} for key,r in watch],'scope':'Available compatible runtime/device inventory only. Each fresh VM must still boot/install/run its own actual tests.'}

def verify_test_products(products,expected):
    found={}
    for name in expected:
        paths=sorted(p for p in products.rglob(name+'.xctest') if p.is_dir())
        if not paths:raise ValueError('Missing compiled test bundle: '+name)
        rows=[]
        for path in paths:
            base=path/'Contents' if (path/'Contents/Info.plist').is_file() else path
            info=plistlib.loads((base/'Info.plist').read_bytes())
            executable=base/('MacOS' if base.name=='Contents' else '')/info['CFBundleExecutable']
            if not executable.is_file():raise ValueError('Test bundle executable is missing: '+name)
            rows.append({'path':str(path),'bundle_identifier':info.get('CFBundleIdentifier'),'executable_sha256':hashlib.sha256(executable.read_bytes()).hexdigest()})
        found[name]=rows
    return found

def main():
    temp=Path(os.environ['RUNNER_TEMP']);out=temp/'combined-preflight.json'
    report={'source_sha':os.environ['GITHUB_SHA'],'scope':'Grouped unsigned build-for-testing, test-bundle setup and Release package prerequisite; not runtime or feature qualification','stages':[],'checks':{}}
    deadline=time.monotonic()+2400
    def stage(name,operation):
        record={'stage':name,'started_unix':time.time()};report['stages'].append(record)
        try:
            if deadline-time.monotonic()<60:raise TimeoutError('Grouped 2400-second preflight budget exhausted before this stage')
            record['proof']=operation();record['passed']=True
        except Exception as error:record['passed']=False;record['error']=str(error)
        record['elapsed_seconds']=round(time.time()-record['started_unix'],3)
        report['checks'][name]=record['passed'];out.write_text(json.dumps(report,indent=2)+'\n')
        print('COMBINED_PREFLIGHT_STAGE '+json.dumps(record),flush=True)
    def command(args,name,seconds=600):
        return run(args,timeout=min(seconds,max(1,int(deadline-time.monotonic()))),log_name='preflight-'+name+'.log')
    def inventory():
        a=json.loads(command(['xcrun','simctl','list','runtimes','--json'],'runtimes',60).stdout)['runtimes']
        b=json.loads(command(['xcrun','simctl','list','devicetypes','--json'],'devices',60).stdout)['devicetypes']
        return available_setup(a,b)
    stage('available-runtime-setup',inventory)
    stage('tv-test-input-capability',lambda:{'return_code':command([sys.executable,ROOT/'Scripts/probe_tv_text_input.py'],'tv-capability',120).returncode})
    debug=temp/'preflight-debug'
    for key,project,scheme,destination,tests in DEBUG_PLANS:
        def build(key=key,project=project,scheme=scheme,destination=destination,tests=tests):
            args=['xcodebuild','-project',project,'-scheme',scheme,'-configuration','Debug','-destination','platform=macOS' if destination=='macOS' else 'generic/platform='+destination,'-derivedDataPath',debug,'-jobs','2','CODE_SIGNING_ALLOWED=NO','COMPILER_INDEX_STORE_ENABLE=NO','build-for-testing']
            if key=='tv':args+=['SWIFT_ACTIVE_COMPILATION_CONDITIONS=DEBUG CELLULOID_TV_TYPETEXT_SUPPORTED' if (temp/'tv-typetext-supported').is_file() else 'SWIFT_ACTIVE_COMPILATION_CONDITIONS=DEBUG']
            command(args,key+'-debug')
            proof={'project':project,'scheme':scheme,'compiled_tests':verify_test_products(debug/'Build/Products',tests)}
            if key=='phone':
                from verify_embedded_watch import verify,inventory
                receipt=verify(debug/'Build/Products/Debug-iphonesimulator/Celluloid.app',debug/'Build/Products/Debug-watchsimulator/CelluloidWatch.app','simulator',build_for_testing=True)
                actual={r[0]:r for r in inventory(debug/'Build/Products/Debug-iphonesimulator/Celluloid.app/Watch/CelluloidWatch.app')}
                expected={r[0]:r for r in inventory(debug/'Build/Products/Debug-watchsimulator/CelluloidWatch.app')}
                receipt['observed_debug_copy_differences']=[{'path':name,'nested':actual.get(name),'producer':expected.get(name)} for name in sorted(actual.keys()|expected.keys()) if actual.get(name)!=expected.get(name)][:20]
                (temp/'preflight-phone-embedded-watch.json').write_text(json.dumps(receipt,indent=2)+'\n')
                if not all(receipt['checks'].values()):raise ValueError('Actual Debug Watch embedding prerequisite failed: '+json.dumps(receipt['checks']))
                proof['watch_embedding']=receipt
            return proof
        stage(key+'-build-for-testing',build)
    release=temp/'preflight-release'
    for key,project,scheme,destination,product_dir in RELEASE_PLANS:
        def build(key=key,project=project,scheme=scheme,destination=destination,product_dir=product_dir):
            command(['xcodebuild','-project',project,'-scheme',scheme,'-configuration','Release','-destination','generic/platform='+destination,'-derivedDataPath',release,'-jobs','2','CODE_SIGNING_ALLOWED=NO','COMPILER_INDEX_STORE_ENABLE=NO','build'],key+'-release')
            app=release/'Build/Products'/product_dir/(scheme+'.app')
            if key=='phone':
                command([sys.executable,ROOT/'Scripts/verify_embedded_watch.py',app,release/'Build/Products/Release-watchos/CelluloidWatch.app','--mode','device','--output',temp/'preflight-phone-embedded-watch-release.json','--build-log',temp/'preflight-phone-release.log'],key+'-package',120)
                return {'package_receipt':'preflight-phone-embedded-watch-release.json'}
            command([sys.executable,ROOT/'Scripts/verify_native_release.py',key,app],key+'-package',120)
            return {'package_receipt':key+'-release-packaging.json'}
        stage(key+'-release-package',build)
    report['all_prerequisites_passed']=len(report['checks'])==14 and all(report['checks'].values())
    report['long_matrix_allowed']=report['all_prerequisites_passed'];out.write_text(json.dumps(report,indent=2)+'\n')
    print('COMBINED_PREFLIGHT_RESULT '+json.dumps({'source_sha':report['source_sha'],'checks':report['checks'],'long_matrix_allowed':report['long_matrix_allowed']}),flush=True)
    if not report['long_matrix_allowed']:raise SystemExit('Grouped prerequisites failed; long functional matrix must remain gated')

if __name__=='__main__':main()
