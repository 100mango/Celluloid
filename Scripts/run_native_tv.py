#!/usr/bin/env python3
"""Bounded native tvOS simulator run; no broad service-dump readiness gate."""
import argparse,json,os,signal,subprocess,sys,time,struct,zlib
from pathlib import Path
root=Path(__file__).resolve().parents[1];temp=Path(os.environ['RUNNER_TEMP'])
from native_process import run,optional_diagnostic
parser=argparse.ArgumentParser()
parser.add_argument('--two-source-only',action='store_true')
focused=parser.parse_args().two_source_only
if focused:
    from tv_two_source_cohort import require_probe, ONLY_TEST, capture_product, capture_proof, clock_deadlines
    require_probe(json.loads((temp/'tv-text-input-probe.json').read_text()))
    # Original per-command bounds remain ceilings; preserve six minutes for
    # owned-device cleanup, finalized summary, evidence and upload in the 30m VM.
    require_work_deadline,execution_deadline=clock_deadlines(temp)
    original_run=run
    def run(args,timeout=180,**kwargs):
        cleanup=len(args)>2 and str(args[0])=='xcrun' and str(args[1])=='simctl' and str(args[2]) in ['shutdown','delete']
        if cleanup:
            # Owned cleanup remains mandatory, but cannot consume evidence/upload admission.
            remaining=execution_deadline-time.monotonic()-240-15
            if remaining<=0:raise RuntimeError('Cleanup budget exhausted; owned cleanup remains unverified')
            timeout=min(timeout,remaining)
        else:
            remaining=require_work_deadline-time.monotonic()
            if str(args[0])=='xcodebuild':
                remaining-=180 # Product readback plus the independent Photos oracle.
                if remaining<300:raise RuntimeError('Insufficient reserved budget to admit the single TV case')
            if remaining<=0:raise RuntimeError('Focused work clock exhausted; reserve cleanup/evidence')
            timeout=min(timeout,max(0.001,remaining-15)) # Existing process-group cleanup is also charged.
        return original_run(args,timeout=timeout,**kwargs)

runtimes=json.loads(run(['xcrun','simctl','list','runtimes','--json'],echo=False).stdout)['runtimes']
types=json.loads(run(['xcrun','simctl','list','devicetypes','--json'],echo=False).stdout)['devicetypes']
possible=[r for r in runtimes if r.get('isAvailable') and ('tvos' in r.get('name','').lower() or 'tvos' in r.get('identifier','').lower())]
if not possible:raise RuntimeError('No available native tvOS runtime was found; SDK build does not establish runtime coverage')
runtime=sorted(possible,key=lambda r:tuple(int(x) for x in r['version'].split('.')),reverse=True)[0]
supported={t['identifier'] for t in runtime.get('supportedDeviceTypes',[])}
compatible=[t for t in types if not supported or t['identifier'] in supported]
device_type=next(t for t in compatible if 'Apple TV 4K' in t['name'])
udid=run(['xcrun','simctl','create','Celluloid Native TV Validation',device_type['identifier'],runtime['identifier']]).stdout.strip()
app=temp/'celluloid-tv/Build/Products/Debug-appletvsimulator/CelluloidTV.app'
evidence={'runtime':runtime,'device_type':device_type,'udid':udid,'head':os.environ['GITHUB_SHA']}
if focused:
    evidence['scope']='two-source-only; no hosted, single-photo, 3/4-source, large-text or release acceptance'
    evidence['only_testing']=ONLY_TEST
    if runtime['version']!='27.0' or runtime.get('buildversion')!='24J360':
        # A different runtime is a new observation, not the admitted 485 comparison.
        run(['xcrun','simctl','delete',udid],timeout=45,check=False)
        raise RuntimeError('The two-source cohort requires tvOS 27.0 build24J360')
try:
    run(['xcrun','simctl','boot',udid]);run(['xcrun','simctl','bootstatus',udid,'-b'],timeout=240)
    # Seed only this disposable simulator through the supported public simctl route.
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    fixtures=[]
    for index in range(4):
        path=temp/f'CelluloidSource-{index+1}.png';width=1200+index*16;height=800+index*8
        colors=[(255,0,0,255),(0,255,0,255),(0,0,255,255)] if index==0 else [(40+index*45,40,220,255),(230,60+index*35,30,255),(30,220,40+index*35,255)]
        row=b''.join(bytes(colors[min(2,x*3//width)]) for x in range(width))
        lower=b''.join(bytes(tuple(c//2 for c in colors[min(2,x*3//width)][:3])+(255,)) for x in range(width))
        scanlines=(b'\0'+bytes((9,19,29,255))*width)+(b'\0'+row)*(height//2-1)+(b'\0'+lower)*(height-height//2-1)+(b'\0'+bytes((201,211,221,255))*width)
        path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,6,0,0,0))+chunk(b'sRGB',b'\0')+chunk(b'IDAT',zlib.compress(scanlines))+chunk(b'IEND',b''))
        fixtures.append(path)
    fixture=fixtures[0]
    run(['xcrun','simctl','addmedia',udid,*fixtures],timeout=60)
    evidence['synthetic_fixtures']=[{'name':p.name,'sha256':__import__('hashlib').sha256(p.read_bytes()).hexdigest()} for p in fixtures]
    run(['xcrun','simctl','install',udid,app],timeout=120)
    launch=run(['xcrun','simctl','launch',udid,'Mango.Celluloid'],timeout=60)
    evidence['launch_output']=launch.stdout
    pid=launch.stdout.strip().rsplit(':',1)[-1].strip(); assert pid.isdigit()
    time.sleep(4)
    proc=run(['ps','-p',pid,'-o','pid=,comm='],timeout=20)
    evidence['process']=proc.stdout;assert 'CelluloidTV' in proc.stdout
    evidence['launch_screenshot']=optional_diagnostic(['xcrun','simctl','io',udid,'screenshot','--type=jpeg',temp/'native-tv-launch.jpg'],timeout=45)
    if focused:evidence['product_before']=capture_product(app,udid,run)
    # Four real Photos UI flows now include three independent collage/relaunch
    # cases; keep one finite 15-minute runtime budget inside the same 30-minute VM.
    result=run(['xcodebuild','-project','CelluloidNative.xcodeproj','-scheme','CelluloidTV','-destination',f'platform=tvOS Simulator,id={udid}','-derivedDataPath',temp/'celluloid-tv','-resultBundlePath',temp/'CelluloidTV.xcresult','CODE_SIGNING_ALLOWED=NO','-parallel-testing-enabled','NO','-collect-test-diagnostics','never','-maximum-concurrent-test-simulator-destinations','1',*(['-only-testing:'+ONLY_TEST] if focused else []),'test-without-building'],timeout=900,check=False,log_name='tv-runtime-tests.log')
    evidence['test_exit_code']=result.returncode
    if focused:evidence['product_after']=capture_product(app,udid,run)
    if result.returncode:raise RuntimeError('Native TV test invocation failed; inspect actual error/attachments, do not equate build or boot with E2E coverage')
    container=Path(run(['xcrun','simctl','get_app_container',udid,'Mango.Celluloid','data']).stdout.strip())
    if not focused:run(['swift','-swift-version','5',root/'Scripts/verify_tv_filter_output.swift',fixture,container/'Library/Caches/TVOutputProof'],timeout=120,log_name='tv-filter-oracle.log')
    run(['swift','-swift-version','5',root/'Scripts/verify_tv_composition.swift',temp,container/'Library/Caches/TVCompositionProof',temp/'tv-runtime-tests.log',root/'Celluloid/collage.json',*(['two-source-only'] if focused else [])],timeout=120,log_name='tv-composition-oracle.log')
    if focused:evidence['proof_files']=capture_proof(container/'Library/Caches/TVCompositionProof/2',temp/'tv-two-source-proof')
except Exception as error:
    evidence['error']=str(error)
    raise
finally:
    (temp/'tv-runtime-evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    evidence['cleanup']=[]
    for action in ['shutdown','delete']:
        try:
            result=run(['xcrun','simctl',action,udid],timeout=45,check=False)
            evidence['cleanup'].append({'action':action,'exit_code':result.returncode})
        except Exception as error:evidence['cleanup'].append({'action':action,'error':str(error)})
    (temp/'tv-runtime-evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
