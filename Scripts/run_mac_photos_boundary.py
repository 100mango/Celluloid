#!/usr/bin/env python3
"""One source-admitted synthetic Photos Save; never full lifecycle qualification."""
import datetime,hashlib,json,math,os,plistlib,re,signal,stat,subprocess,sys,time
from pathlib import Path
from final_mac_photos_transport import load_json,parse,attachment_candidates,LABEL,CASE
from mac_host_lifecycle_pixels import read_owned_png,decode,require
from mac_photos_boundary_probe import prepare_lease,bind_context,bound_arm,read_capture,admit_comparison,runtime_record,FIXTURE,TOTAL_CAP as BOUNDARY_NODES_CAP
from final_mac_photos_route import HOST_ONLY as BOUNDARY,current_route,host_clock_profile
from final_mac_photos_source import admit_sources,commit_parents

ROOT=Path(__file__).resolve().parents[1]
BASE='13e9a1ed63c6e7744803419f27e429a759df1209'
MANIFEST='.github/final-mac-boundary-source.json'
WORKFLOW=BOUNDARY['workflow_path']
SELECTION=CASE[0].replace('.','/')+'/'+CASE[1]
RAW_CASE='-['+CASE[0]+' '+CASE[1]+']'
CAP=1_000_000
FINAL_RESERVE=32_000
FIXTURE_PATH='Platforms/MacExtensionTests/Fixtures/lifecycle-source.png'

def run(args,timeout=180,check=True,log_name=None,echo=True):
    """One owned command, original deadline and at most 15s cleanup.

    The product's generic runner has an inactive-guard cleanup path that may
    escalate after a denied signal. Keep this stricter adapter additive: any
    signal/read denial stops immediately, retaining failure without a retry.
    """
    args=list(map(str,args));started=time.monotonic();deadline=started+timeout
    process=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
    stdout=stderr='';failure=None;cleanup=[]
    def decoded(value):return value.decode('utf8','replace') if isinstance(value,bytes) else value or ''
    try:
        remaining=deadline-time.monotonic()
        if remaining<=0:raise subprocess.TimeoutExpired(args,timeout)
        stdout,stderr=process.communicate(timeout=remaining)
        if time.monotonic()>deadline:
            raise subprocess.TimeoutExpired(args,timeout,output=stdout,stderr=stderr)
    except subprocess.TimeoutExpired as original:
        stdout,stderr=decoded(original.output),decoded(original.stderr)
        cleanup_deadline=min(deadline+15,time.monotonic()+15)
        if process.poll() is None:
            for sig,seconds in [(signal.SIGTERM,10),(signal.SIGKILL,5)]:
                remaining=min(seconds,cleanup_deadline-time.monotonic())
                if remaining<=0:
                    cleanup.append('original cleanup deadline exhausted');break
                try:os.killpg(process.pid,sig)
                except ProcessLookupError:
                    cleanup.append('owned process group absent; cleanup unconfirmed');break
                except OSError as error:
                    cleanup.append('owned '+signal.Signals(sig).name+' denied/failed: '+str(error)+'; no further signal or wait')
                    break
                remaining=min(seconds,cleanup_deadline-time.monotonic())
                if remaining<=0:
                    cleanup.append('original cleanup deadline exhausted');break
                try:stdout,stderr=process.communicate(timeout=remaining)
                except subprocess.TimeoutExpired as error:
                    stdout=decoded(error.output or stdout);stderr=decoded(error.stderr or stderr)
                except OSError as error:
                    cleanup.append('owned process read denied/failed: '+str(error)+'; no further signal or wait')
                    break
                else:break
        cleanup.append('native command timed out; cleanup unconfirmed; pure file retention only')
        failure=TimeoutError(str(args[0])+' exceeded '+str(timeout)+'s; '+'; '.join(cleanup))
    except OSError as error:
        # No cleanup signal is permitted after a read/permission failure.
        error.cleanup_unconfirmed=True;failure=error
        cleanup.append('owned process read denied/failed; no further signal or wait; cleanup unconfirmed')
    stderr+='\n'+'\n'.join(cleanup) if cleanup else ''
    if log_name:(Path(os.environ['RUNNER_TEMP'])/log_name).write_text(stdout+'\n'+stderr)
    if echo:print(stdout,flush=True);print(stderr,file=sys.stderr,flush=True)
    if failure is not None:raise failure
    result=subprocess.CompletedProcess(args,process.returncode,stdout,stderr)
    if check and result.returncode:raise RuntimeError(str(args[0])+' exited '+str(result.returncode))
    return result

def sha(data):return hashlib.sha256(data).hexdigest()
def encoded(value):return json.dumps(value,sort_keys=True,allow_nan=False).encode()
def git(*args):return subprocess.check_output(['git','-C',str(ROOT),*args],timeout=10)
def source_snapshot(root,manifest):
    require(type(manifest) is dict and manifest.get('schema')=='Celluloid.OwnedPhotosBoundarySource.1'
        and manifest.get('parent')==BASE,'wrong boundary source manifest')
    rows=manifest.get('files');require(type(rows) is list and 0<len(rows)<=1000,'source inventory size')
    names=[]
    for row in rows:
        require(type(row) is dict and set(row)=={'path','mode','bytes','sha256'},'source row')
        rel=row['path'];require(type(rel) is str and rel!=MANIFEST and not Path(rel).is_absolute()
            and '..' not in Path(rel).parts and rel not in names,'source path')
        names.append(rel);path=root/rel
        require(path.is_file() and not path.is_symlink(),'nonregular source '+rel)
        raw=path.read_bytes();mode='100755' if path.stat().st_mode&stat.S_IXUSR else '100644'
        require(type(row['bytes']) is int and len(raw)==row['bytes'] and sha(raw)==row['sha256'] and mode==row['mode'],'source bytes/mode '+rel)
    require(names==sorted(names),'source order')
    return sha(json.dumps(rows,sort_keys=True,separators=(',',':')).encode())
def admit_source():
    require(sys.flags.optimize==0 and __debug__,'native driver requires normal Python')
    require(sys.platform=='darwin' and os.environ.get('GITHUB_ACTIONS')=='true','fresh standard Mac runner required')
    require(current_route()==BOUNDARY,'wrong fixed boundary route')
    require(os.environ.get('DEVELOPER_DIR')=='/Applications/Xcode_27.app/Contents/Developer','wrong Xcode installation')
    run_id=os.environ.get('GITHUB_RUN_ID','')
    require(re.fullmatch('[1-9][0-9]*',run_id) is not None and os.environ.get('GITHUB_RUN_ATTEMPT')=='1','wrong run/attempt')
    head=git('rev-parse','HEAD').decode().strip()
    require(head==os.environ.get('GITHUB_SHA')==os.environ.get('GITHUB_WORKFLOW_SHA') and re.fullmatch('[0-9a-f]{40}',head),'wrong source/workflow SHA')
    require(commit_parents(git('cat-file','-p','HEAD').decode())==[BASE],'candidate must have sole current product parent')
    admit_sources()
    require(not git('status','--porcelain','--untracked-files=all').strip(),'dirty source')
    raw=(ROOT/MANIFEST).read_bytes();require(len(raw)<=256*1024,'source manifest cap')
    manifest=load_json(raw)
    inventory=set(git('ls-files','-z').decode().rstrip('\0').split('\0'))
    require(inventory=={r['path'] for r in manifest['files']}|{MANIFEST},'tracked source inventory')
    fingerprint=source_snapshot(ROOT,manifest)
    require(sha((ROOT/FIXTURE_PATH).read_bytes())==FIXTURE,'synthetic fixture bytes changed')
    return manifest,{'schema':'Celluloid.OwnedPhotosBoundarySourceReceipt.1','source_sha':head,
        'tree':git('rev-parse','HEAD^{tree}').decode().strip(),'parent':BASE,'source_fingerprint':fingerprint,
        'source_manifest_sha256':sha(raw),'workflow_sha256':sha((ROOT/WORKFLOW).read_bytes()),
        'fixture_sha256':FIXTURE,'files':len(inventory),'run_id':run_id,'run_attempt':1,
        'scope':BOUNDARY['scope'],'selected_case':SELECTION,'complete_host_e2e':False}

def command(temp,action,info):
    require(action in {'build-for-testing','build','test-without-building'},'unadmitted native action')
    if action=='test-without-building':
        # Exact already-used original host argv, with a canonical owned path.
        return ['xcodebuild','-project','CelluloidNative.xcodeproj','-scheme','CelluloidMacUI',
            '-destination','platform=macOS','-derivedDataPath',str(temp/'celluloid-sandbox'),
            '-resultBundlePath',str(temp/'MacPhotosHost.xcresult'),'-parallel-testing-enabled','NO',
            '-collect-test-diagnostics','never','-maximum-test-execution-time-allowance','960',
            '-only-testing:'+SELECTION,'CODE_SIGNING_ALLOWED=NO','CELLULOID_EXPECT_SANDBOX=YES','test-without-building']
    args=['xcodebuild','-project','CelluloidNative.xcodeproj','-scheme','CelluloidMacUI' if action=='build-for-testing' else 'CelluloidMac',
        '-configuration','Debug','-destination','platform=macOS','-derivedDataPath',str(temp/'celluloid-sandbox'),
        'CODE_SIGNING_ALLOWED=YES','CODE_SIGNING_REQUIRED=YES','CODE_SIGN_IDENTITY=-','CODE_SIGN_STYLE=Manual',
        'CELLULOID_MAC_PHOTOS_BOUNDARY_CONDITION=CELLULOID_OWNED_PHOTOS_BOUNDARY_PROBE',
        'CELLULOID_MAC_PHOTOS_BOUNDARY_INFO_PLIST='+str(info)]
    args+=['CELLULOID_EXPECT_SANDBOX=YES'] if action=='build-for-testing' else ['ENABLE_TESTABILITY=NO']
    return args+[action]

def merged_command(args):
    # Exec replaces this fixed shell inside the additive run() owned process
    # group. Positional argv avoids interpolation and preserves stdout/stderr order.
    return ['/bin/sh','-c','exec "$@" 2>&1','celluloid-owned-boundary',*map(str,args)]

def native_completion(log,event,bundle):
    require(event.get('returned_without_timeout') is True and event.get('return_code') in (0,65)
        and event.get('elapsed_seconds',math.inf)<=1020,'native command not timely/finalized')
    rows=[line.strip() for line in log.splitlines()]
    cases=[line for line in rows if line.lower().startswith('test case ')]
    state='passed' if event['return_code']==0 else 'failed'
    require(len(cases)==2 and cases[0]=="Test Case '"+RAW_CASE+"' started."
        and re.fullmatch(re.escape("Test Case '"+RAW_CASE+"' "+state)+r' \([0-9]+(?:\.[0-9]+)? seconds\)\.',cases[1]),'missing exact unique host case completion')
    expected='** TEST EXECUTE '+('SUCCEEDED' if event['return_code']==0 else 'FAILED')+' **'
    terminals=[line for line in rows if re.match(r'^\*\* TEST(?: EXECUTE)?\b',line,re.I)]
    require(terminals==[expected] and rows.index(cases[0])<rows.index(cases[1])<rows.index(expected),'native terminal mismatch')
    paths=[line for line in rows if line.startswith('/') and line.endswith('.xcresult')]
    require(paths in ([bundle],[bundle,bundle]),'wrong host result path')

def check_summary_interval(summary,event,before):
    require(event['run_id']==before['run_id'] and event['run_attempt']==before['run_attempt']==1,'wrong native run/attempt')
    require(all(type(summary.get(k)) in (int,float) and math.isfinite(summary[k]) for k in ('startTime','finishTime')),'unknown summary time')
    require(event['started_unix']<=summary['startTime']<summary['finishTime']<=event['finished_unix']
        and summary['finishTime']-summary['startTime']<=event['elapsed_seconds'],'summary outside original native phase')

def capture_capacity(files):
    # Reserve the maximum complete I/J/capture/comparison set, source-after,
    # and the unchanged final run/manifest reserve before opening the container.
    used=sum(row['bytes'] for row in files.values())
    required=BOUNDARY_NODES_CAP+4096+FINAL_RESERVE
    require(used+required<=CAP,'insufficient original 1MB capacity before owned capture')
    return {'retained_before_capture':used,'required_boundary_nodes':BOUNDARY_NODES_CAP,
        'required_source_after':4096,'required_final_reserve':FINAL_RESERVE,'cap_bytes':CAP}

def main():
    supplied=Path(os.environ['RUNNER_TEMP'])
    require(supplied.is_dir() and not supplied.is_symlink(),'invalid runner temp')
    temp=supplied.resolve(strict=True) # macOS ancestor /var alias, never weaken ROOT admission.
    output=temp/'celluloid-photos-boundary-evidence';require(not output.exists(),'stale evidence');output.mkdir()
    files={};before=None;manifest=None;safe_case=False;host_event=None;work_deadline=None;tail_deadline=None
    report={'schema':'Celluloid.OwnedPhotosBoundaryRun.1','scope':BOUNDARY['scope'],'source_sha':os.environ.get('GITHUB_SHA'),
        'stage':'source-admission','diagnostic_complete':False,'saved_gate_passed':False,'complete_host_e2e':False,
        'old_full_host_admission_granted':False,'performance_acceptance':False,'writer_delivery_observed':False,'photos_storage_acceptance_observed':False,'native_case_started':False,'events':[]}
    def check_time(phase,reserve=0):
        if work_deadline is None:return
        limit=min(work_deadline,tail_deadline if tail_deadline is not None else work_deadline)
        require(time.monotonic()+reserve<limit,'original tail/work deadline exhausted: '+phase)
    def incomplete(error,field='error'):
        report['diagnostic_complete']=False;report['saved_gate_passed']=False
        report[field]=type(error).__name__+': '+str(error)[:1800]
    def retain(name,data,limit):
        require(name not in files and '/' not in name and 0<len(data)<=limit,'artifact name/cap '+name)
        require(sum(r['bytes'] for r in files.values())+len(data)<=CAP-FINAL_RESERVE,'required artifact total')
        (output/name).write_bytes(data);files[name]={'bytes':len(data),'sha256':sha(data)}
    def invoke(args,seconds,label,phase_deadline=None):
        available=min(work_deadline,phase_deadline if phase_deadline is not None else work_deadline)-time.monotonic()
        require(available>=seconds+15,'original phase/collection reserve exhausted: '+label)
        event={'stage':label,'command':list(map(str,args)),'executor_command':merged_command(args),
            'limit_seconds':seconds,'started_unix':time.time(),'started_monotonic':time.monotonic(),
            'run_id':before['run_id'],'run_attempt':before['run_attempt']};report['events'].append(event)
        result=run(merged_command(args),timeout=seconds,check=False,echo=False,log_name='boundary-'+label+'.log')
        event.update(return_code=result.returncode,finished_unix=time.time(),finished_monotonic=time.monotonic(),
            elapsed_seconds=time.monotonic()-event['started_monotonic'],returned_without_timeout=True)
        return result,event
    def required(args,seconds,label,phase_deadline=None):
        result,event=invoke(args,seconds,label,phase_deadline)
        raw=(result.stdout+result.stderr).encode()
        if label in {'portable','ui-build','app-build','compare-build'}:
            retain(label+'.tail.txt',raw[-24_000:] or b'(empty)',24_000)
            event['log_identity']={'bytes':len(raw),'sha256':sha(raw),'tail_only':True}
        require(result.returncode==0,'required phase failed: '+label)
        return result,event
    try:
        require(Path.cwd().resolve()==ROOT,'driver must run from reviewed repository root')
        manifest,before=admit_source();report.update(run_id=before['run_id'],run_attempt=1)
        retain('source-before.json',encoded(before),4096)
        clock_bytes=(temp/'mac-job-clock.json').read_bytes();clock=load_json(clock_bytes)
        require(clock.get('source_sha')==before['source_sha'] and type(clock.get('execution_budget_seconds')) is int
            and clock['execution_budget_seconds']==2460,'wrong original job clock')
        require(all(type(clock.get(k)) in (int,float) and math.isfinite(clock[k]) and clock[k]>0 for k in ('started_monotonic','started_unix')),'invalid original clock')
        require(clock['started_monotonic']<=time.monotonic(),'future job clock')
        deadline=clock['started_monotonic']+2460;work_deadline=deadline-300
        retain('mac-job-clock.json',clock_bytes,4096)
        report['budgets']={'job_minutes':45,'original_first_step_clock_seconds':2460,'final_evidence_upload_reserve_seconds':300,
            'case_seconds':900,'xctest_allowance_seconds':960,'native_process_seconds':1020,'native_cleanup_seconds':15,
            'before_prepare_reserve_seconds':1980,'before_host_reserve_seconds':1740,'post_host_tail_seconds':360}
        for name in ['celluloid-sandbox','MacPhotosHost.xcresult','boundary-attachments','boundary-compare',
                     'boundary-compare-bin','boundary-debug-info.plist','mac-host-context.json','mac-host-observed']:
            require(not (temp/name).exists() and not (temp/name).is_symlink(),'stale owned path '+name)
        require(not (temp/'sandbox.log').exists(),'unadmitted seeded Photos path')
        # Observe and admit the actual host before any native build, signing or Photos.
        # These commands use this driver's denial-stopping owned runner and the
        # original first-step clock. No new deadline or cleanup allowance.
        report['stage']='runtime-preflight'
        product_version,_=required(['/usr/bin/sw_vers','-productVersion'],10,'runtime-version')
        product_build,_=required(['/usr/bin/sw_vers','-buildVersion'],10,'runtime-build')
        observed={'platform':'macOS','osVersion':product_version.stdout.strip(),
            'osBuildNumber':product_build.stdout.strip(),'architecture':os.uname().machine}
        report['runtime_observation']={key:value[:128] for key,value in observed.items()}
        runtime_before=runtime_record(observed['osVersion'],observed['osBuildNumber'],observed['architecture'])
        report['runtime_before']=runtime_before
        retain('runtime-before.json',encoded({'schema':'Celluloid.OwnedPhotosBoundaryRuntimeObservation.1',
            'source_sha':before['source_sha'],'run_id':before['run_id'],'run_attempt':1,
            'runtime':runtime_before}),2048)
        report['stage']='toolchain'
        version,_=required(['xcodebuild','-version'],20,'toolchain')
        require('Xcode 27.0' in version.stdout.splitlines(),'stable Xcode 27 required');report['toolchain']=version.stdout[:1024]
        report['stage']='portable'
        required([sys.executable,'-m','unittest','discover','-s','Scripts','-p','test_mac_photos_boundary*.py','-v'],240,'portable')
        require(source_snapshot(ROOT,manifest)==before['source_fingerprint'],'portable checks changed source')
        lease,info_bytes=prepare_lease((ROOT/'Platforms/macOSExtension/Info.plist').read_bytes(),before['source_sha'],before['tree'],before['run_id'],'1')
        info=temp/'boundary-debug-info.plist';info.write_bytes(info_bytes)
        report['stage']='icon-inputs';icon_deadline=min(work_deadline,time.monotonic()+60)
        required(['swift','-swift-version','5','Scripts/materialize_native_icons.swift'],30,'icons',icon_deadline)
        required([sys.executable,'Scripts/verify_native_icon_inputs.py'],10,'icon-check',icon_deadline)
        report['stage']='ui-build';build_deadline=min(work_deadline,time.monotonic()+600)
        required(command(temp,'build-for-testing',info),480,'ui-build',build_deadline)
        required(['xcrun','--sdk','macosx','swiftc','-swift-version','5','-O','Scripts/compare_owned_photos_boundary.swift',
            '-o',str(temp/'boundary-compare-bin')],60,'compare-build',build_deadline)
        comparison_bin=temp/'boundary-compare-bin'
        require(comparison_bin.is_file() and not comparison_bin.is_symlink()
            and comparison_bin.stat().st_nlink==1 and 0<comparison_bin.stat().st_size<=16*1024*1024,'invalid compiled comparison helper')
        comparison_hash=sha(comparison_bin.read_bytes());report['comparison_binary_sha256']=comparison_hash
        report['stage']='app-build';required(command(temp,'build',info),300,'app-build')
        # Existing 1980/1740 source-bound reservations, same original first clock.
        report['stage']='before-prepare';required([sys.executable,'Scripts/final_mac_photos_gate.py','budget-before-prepare'],20,'budget-prepare')
        preparation_deadline=min(work_deadline,time.monotonic()+240)
        app=temp/'celluloid-sandbox/Build/Products/Debug/CelluloidMac.app'
        result,_=required(['/usr/bin/codesign','-d','--entitlements',':-',str(app)],20,'app-entitlements',preparation_deadline)
        # codesign -d emits its non-plist diagnostics on stderr, now merged. Read
        # only the single complete XML plist envelope and validate exact keys.
        text=result.stdout;start=text.find('<?xml');end=text.find('</plist>',start)
        require(start>=0 and end>=start and text.count('<?xml')==text.count('</plist>')==1,'missing/ambiguous app entitlement plist')
        app_rights=plistlib.loads(text[start:end+8].encode())
        require(app_rights=={'com.apple.security.app-sandbox':True,'com.apple.security.files.user-selected.read-write':True},'unexpected app entitlements')
        debug_rights=dict(app_rights,**{'com.apple.security.get-task-allow':True})
        rights=temp/'boundary-app-debug-entitlements.plist';require(not rights.exists(),'stale debug entitlement file');rights.write_bytes(plistlib.dumps(debug_rights))
        required(['/usr/bin/codesign','--force','--sign','-','--entitlements',str(rights),'--timestamp=none',str(app)],20,'debug-sign-app',preparation_deadline)
        required([sys.executable,'Scripts/final_mac_photos_gate.py','prepare'],120,'prepare',preparation_deadline)
        context_path=temp/'mac-host-context.json';context=load_json(context_path.read_bytes())
        require(context['seed']=={'mode':'require-empty-library'},'only fresh owned fixture mode')
        require(context['validation_route']==BOUNDARY and context['host_clock_profile']==host_clock_profile(BOUNDARY),'wrong prepared route/clock')
        context['runner_environment'].update(GITHUB_RUN_ID=before['run_id'],GITHUB_RUN_ATTEMPT='1',RUNNER_TEMP=str(temp))
        context['boundary_runtime']=dict(runtime_before) # Included in the context hash printed by this exact host case.
        processed=(Path(context['extension_path'])/'Contents/Info.plist').read_bytes()
        context=bind_context(context,lease,processed);context_path.write_bytes(encoded(context))
        context_bytes=context_path.read_bytes();retain('mac-host-context.json',context_bytes,128_000)
        require(source_snapshot(ROOT,manifest)==before['source_fingerprint'],'pre-host source changed')
        report['stage']='before-host';required([sys.executable,'Scripts/final_mac_photos_gate.py','budget-before-host'],20,'budget-host')
        retain('mac-host-budget.json',(temp/'mac-host-budget.json').read_bytes(),8192)
        args=command(temp,'test-without-building',info)
        # Only this source-bound test runner receives the original prerequisite/context.
        os.environ['TEST_RUNNER_CELLULOID_MAC_PHOTOS_HOST_PREREQUISITE']='1'
        os.environ['TEST_RUNNER_CELLULOID_MAC_HOST_CONTEXT']=str(context_path)
        report['stage']='single-photos-case';report['native_case_started']=True
        native,host_event=invoke(args,1020,'single-photos-case')
        begin={'label':LABEL,'utc':datetime.datetime.fromtimestamp(host_event['started_unix'],datetime.timezone.utc).isoformat(),'seconds':1020,'command':args}
        end={'label':LABEL,'exit_code':native.returncode,'elapsed_seconds':host_event['elapsed_seconds']}
        log='BOUNDED_COMMAND_BEGIN '+json.dumps(begin)+'\n'+native.stdout+native.stderr+'\nBOUNDED_COMMAND_END '+json.dumps(end)+'\n'
        retain('mac-host-test.log',log.encode(),256_000)
        bundle=str(temp/'MacPhotosHost.xcresult');report['stage']='native-completion'
        native_completion(log,host_event,bundle)
        tail_deadline=min(work_deadline,host_event['finished_monotonic']+360,host_event['started_monotonic']+1020+360)
        report['stage']='summary';result,_=required(['xcrun','xcresulttool','get','test-results','summary','--path',bundle],30,'summary',tail_deadline)
        summary=load_json(result.stdout);retain('mac-host-summary.json',result.stdout.encode(),32_000)
        check_summary_interval(summary,host_event,before)
        report['stage']='safe-outcome-before-container-and-export'
        admitted,arm,identity=bound_arm(context_bytes,log,summary);safe_case=True
        records=parse(log,admitted,sha(context_bytes),complete=False)
        check_time('after-safe-outcome-replay')
        for name,data in records.items():retain(name,data,120_000 if name=='fixture.json' else 16_000)
        report['stage']='unchanged-product';required([sys.executable,'Scripts/final_mac_photos_gate.py','product-after'],60,'product-after',tail_deadline)
        retain('mac-host-product-after.json',(temp/'mac-host-product-after.json').read_bytes(),8192)
        require(sha((Path(context['extension_path'])/'Contents/Info.plist').read_bytes())==context['boundary_probe']['extension_info_sha256'],'processed extension lease changed')
        require(source_snapshot(ROOT,manifest)==before['source_fingerprint'],'source changed before owned reads')
        check_time('after-product-and-source-recheck')
        report['stage']='attachment-export';folder=temp/'boundary-attachments'
        required(['xcrun','xcresulttool','export','attachments','--path',bundle,'--output-path',str(folder)],60,'attachments',tail_deadline)
        inventory=read_owned_png(folder/'manifest.json');require(len(inventory)<=128_000,'attachment manifest cap')
        retain('attachment-manifest.json',inventory,128_000)
        selected=attachment_candidates(folder,load_json(inventory))
        names={'lifecycle-source.png','lifecycle-expected-save.png','lifecycle-saved.png'}
        require({k for k in selected if k.startswith('lifecycle-')}==names,'wrong owned Save raster set')
        old_images={k:selected[k] for k in sorted(names)}
        lifecycle=load_json(records['lifecycle.json']);icc=lifecycle.get('srgb_icc_reference')
        for name,data in old_images.items():
            image=decode(data,icc);meta=lifecycle['images'][name]
            require(meta['sha256']==sha(data) and meta['rgba_sha256']==image['rgba_sha256'],'host image receipt mismatch')
            retain(name,data,131_072)
        require(sha(old_images['lifecycle-source.png'])==FIXTURE,'owned fixture changed')
        report['stage']='before-owned-capture-budget'
        check_time('after-original-PNG-replay')
        # Same existing reader2 + comparison30 + owned-cleanup15 costs; no new window.
        check_time('before-owned-read',reserve=2+30+15)
        report['capture_capacity_admission']=capture_capacity(files)
        report['stage']='owned-synthetic-container-read'
        captured=read_capture(admitted,arm,identity,Path.home().resolve(strict=True))
        for name,data in captured.items():retain(name,data,8192 if name=='capture.json' else 65_536)
        check_time('after-owned-read-and-retention')
        report['stage']='actual-input-independent-comparison';comparison=temp/'boundary-compare';comparison.mkdir()
        for name,data in {**captured,**old_images}.items():(comparison/name).write_bytes(data)
        require(comparison_bin.is_file() and not comparison_bin.is_symlink()
            and comparison_bin.stat().st_nlink==1 and sha(comparison_bin.read_bytes())==comparison_hash,'compiled comparison helper changed')
        required([str(comparison_bin),str(comparison)],30,'comparison',tail_deadline)
        outputs={name:read_owned_png(comparison/name) for name in ('intended-decoded.png','input-reference.png','boundary-comparison.json')}
        replay=admit_comparison(captured,outputs,old_images,icc)
        check_time('after-independent-comparison-replay')
        for name,data in outputs.items():retain(name,data,8192 if name.endswith('.json') else 32_768)
        check_time('after-comparison-retention')
        report['comparison']=replay;report['diagnostic_complete']=True
        report['static_data_flow_evidence']={'kind':'source-bound immutable local passed from renderer to captureIntended and writer.start',
            'runtime_writer_argument_observed':False,'writer_commit_observed':False,'photos_storage_acceptance_observed':False}
        report['saved_gate_passed']=summary['result']=='Passed' and replay['historical_gate_passed']
        require((summary['result']=='Passed')==replay['historical_gate_passed'],'native/replayed original <=2 gate contradiction')
        report['stage']='completed' if report['saved_gate_passed'] else 'completed-original-pixel-gate-failed'
    except (OSError,ValueError,RuntimeError,TimeoutError,KeyError,TypeError,subprocess.SubprocessError) as error:
        incomplete(error)
        if isinstance(error,TimeoutError) or getattr(error,'cleanup_unconfirmed',False):report['cleanup_unconfirmed']=True
        # No more subprocess, export, container attempt, or fallback after failure.
    finally:
        if manifest is not None and before is not None:
            try:
                check_time('before-source-after')
                after=dict(before,source_fingerprint=source_snapshot(ROOT,manifest),clean_git_rechecked=False)
                require(after['source_fingerprint']==before['source_fingerprint'] and sha((ROOT/MANIFEST).read_bytes())==before['source_manifest_sha256'],'source changed after run')
                check_time('after-source-after-hashes')
                if report['diagnostic_complete']:
                    check_time('before-final-HEAD',reserve=10)
                    head=git('rev-parse','HEAD').decode().strip();check_time('after-final-HEAD')
                    require(head==before['source_sha'],'changed final Git identity')
                    check_time('before-final-status',reserve=10)
                    dirty=git('status','--porcelain','--untracked-files=all').strip();check_time('after-final-status')
                    require(not dirty,'changed final Git status')
                    after['clean_git_rechecked']=True
                retain('source-after.json',encoded(after),4096)
                check_time('after-source-after-retention')
            except (OSError,ValueError,subprocess.SubprocessError) as error:
                incomplete(error,'source_after_error')
        if report.get('error') and report['native_case_started']:
            path=temp/'boundary-single-photos-case.log'
            if path.is_file() and not path.is_symlink():
                with path.open('rb') as stream:
                    stream.seek(max(0,path.stat().st_size-16_000))
                    try:retain('native.partial-tail.txt',stream.read(16_000) or b'(empty)',16_000)
                    except ValueError:pass
        report['safe_outcome_admitted']=safe_case
        # Stage final bytes outside the upload directory. Only the final
        # manifest rename publishes a complete packet. Late CPU/serialization or
        # staging IO downgrades once to incomplete; it cannot extend either clock.
        pending_run=temp/'boundary-final-run.pending.json'
        pending_manifest=temp/'boundary-final-manifest.pending.json'
        require(not pending_run.exists() and not pending_manifest.exists(),'stale final staging path')
        def stage_final():
            raw=encoded(report);require(len(raw)<=24_000,'run receipt cap')
            pending_run.write_bytes(raw);files['run.json']={'bytes':len(raw),'sha256':sha(raw)}
            envelope=encoded({'schema':'Celluloid.OwnedPhotosBoundaryEvidence.1','source_sha':report['source_sha'],
                'run_id':report.get('run_id'),'run_attempt':report.get('run_attempt'),'cap_bytes':CAP,'files':files,
                'diagnostic_only':True,'complete_host_e2e':False})
            require(len(envelope)<=8192 and sum(v['bytes'] for v in files.values())+len(envelope)<=CAP,'final fixed 1MB cap')
            pending_manifest.write_bytes(envelope)
        stage_final()
        if report['diagnostic_complete']:
            try:check_time('after-final-receipt-staging')
            except ValueError as error:
                incomplete(error,'publication_error');stage_final()
        pending_run.replace(output/'run.json')
        if report['diagnostic_complete']:
            try:check_time('before-success-publication')
            except ValueError as error:
                incomplete(error,'publication_error');stage_final();pending_run.replace(output/'run.json')
        # Atomic manifest publication is the endpoint; no recursive confirmation
        # is added and filesystem rename is not claimed to be hard real time.
        pending_manifest.replace(output/'manifest.json')
    return 0 if report['diagnostic_complete'] and report['saved_gate_passed'] else 1

if __name__=='__main__':sys.exit(main())
