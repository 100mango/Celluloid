#!/usr/bin/env python3
"""One ordinary Mac capture case and two native Store views; no release claim."""
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import time

from mac_store_process import capture, CaptureStopped
from mac_store_io import read_file, strict_json
from mac_store_product import base_command, product_identity
from mac_store_contract import CASE, MAX_PACKET, STATES, SOURCE_BLOBS, ProofRejected, summary_admission, validate_capture
from mac_store_raw import RAW_LIMITS, collect_raw

ROOT = Path(__file__).resolve().parents[1]
BASE = 'b8b6aa890df8b4f16f5627c965d01585a21fe97b'
BASE_TREE = '8bd5f17720c0b7b8aa6ddf591cf0ec0fc7099735'
PARENT = '9058bc3b276e67a5bf457aa5b470fbf51a211849'
PARENT_TREE = '1080a185944a5af59ef8b6fb8172ce2c98a719c9'
BRANCH = 'refs/heads/codex/mac-store-display'
WORKFLOW = '.github/workflows/mac-store-display.yml'
RESULT = Path('build/mac-store-capture/capture.xcresult')
EXPORT = Path('build/mac-store-capture/attachments')
PREPARED = Path('build/mac-store-prepared')
OUTPUT = Path('build/mac-store-proof')
MAX_REPORT = 2 * 1024 * 1024
TOOLCHAIN = {'os':'26A428','architecture':'arm64','xcode':'Xcode 27.0\nBuild version 27A266a'}
PHASE_END = {'prepare':180,'build':640,'test':960,'proof':1140,'final_source_pack':1170,'evidence':1230,'finalization':1250}
NEW_PATHS = (WORKFLOW,'MAC-STORE-CAPTURE.md','Scripts/mac_store_capture.py','Scripts/mac_store_contract.py',
    'Scripts/mac_store_display.py','Scripts/mac_store_png.py','Scripts/mac_store_io.py','Scripts/mac_store_product.py',
    'Scripts/mac_store_process.py','Scripts/mac_store_process_group.py',
    'Scripts/test_mac_store_capture.py','Scripts/test_mac_store_display.py','Scripts/test_mac_store_png.py',
    'Scripts/test_mac_store_source_helpers.py','Scripts/fixtures/mac-store-source-baseline.json',
    'StoreCaptureAssets/demo-citrus-sunny.png','StoreCaptureAssets/demo-coast-sunny.png','StoreCaptureAssets/provenance.json',
    'Scripts/mac_store_raw.py','Scripts/test_mac_store_raw.py')
MODIFIED_PATHS = ('Platforms/macOS/NativeWindowAccessibility.swift','Platforms/UITests/NativeEditorUITests.swift')
SUCCESSOR_MODIFIED_PATHS = ('Scripts/mac_store_capture.py','Scripts/mac_store_contract.py',
    'Scripts/test_mac_store_capture.py','Scripts/fixtures/mac-store-source-baseline.json','MAC-STORE-CAPTURE.md')
SUCCESSOR_NEW_PATHS = ('Scripts/mac_store_raw.py','Scripts/test_mac_store_raw.py')
EXPECTED_DIFF = sorted(['M\t'+x for x in SUCCESSOR_MODIFIED_PATHS]+['A\t'+x for x in SUCCESSOR_NEW_PATHS])
IMAGE_NAMES = ('native-citrus.png','native-coast.png','store-citrus.png','store-coast.png')

class Rejected(ValueError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)

def need(ok, reason):
    if not ok:
        raise Rejected(reason)

def timely(deadline, clock=time.monotonic):
    need(math.isfinite(deadline) and clock() < deadline, 'deadline-exceeded')

def file_identity(value):
    return [value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns]

def json_value(value):
    if isinstance(value, datetime.datetime):
        return {'plist_date': value.isoformat()}
    if isinstance(value, bytes):
        return {'plist_data_hex': value.hex()}
    raise TypeError(type(value).__name__)

def command(argv, *, deadline, seconds, cap, receipts, clock=time.monotonic,
            runner=capture, cleanup=2, allowed=(0,), wall=time.time):
    """One command grant with the existing helper's two cleanup phases reserved."""
    start = clock()
    grant = min(seconds, deadline - start - 2 * cleanup)
    need(math.isfinite(grant) and grant > 0, 'command-cleanup-admission-expired')
    receipt = {'command': argv, 'start': start, 'started_epoch': wall(), 'grant_seconds': grant,
               'cleanup_reserve_seconds': 2 * cleanup, 'complete': False}
    receipts.append(receipt)
    try:
        result = runner(argv, seconds=grant, cap=cap, cleanup_grace=cleanup)
    except CaptureStopped as error:
        receipt.update(reason=str(error), owned_cleanup_confirmed=error.cleanup_confirmed,
                       cancelled_signal=error.cancelled_signal,
                       stdout=getattr(error, 'stdout_prefix', b'')[:cap].decode('utf-8', 'replace'),
                       stderr=getattr(error, 'stderr_capture', b'')[:cap].decode('utf-8', 'replace'))
        raise Rejected('capture-stopped') from error
    finally:
        receipt['end'] = clock()
        receipt['finished_epoch'] = wall()
    receipt.update(returncode=result.returncode, stdout=result.stdout.decode('utf-8', 'replace'),
                   stderr=result.stderr.decode('utf-8', 'replace'),
                   owned_host_observation='client-reaped-pipes-closed-group-absent-at-return')
    need(len(result.stdout) + len(result.stderr) <= cap, 'command-byte-limit')
    need(receipt['end'] < start + grant and receipt['end'] < deadline, 'command-late-return')
    need(result.returncode in allowed, 'command-failed')
    receipt['complete'] = True
    return result.stdout

def upload_ceiling(result):
    value = result.get('clock', {})
    began = value.get('started_monotonic')
    need(type(began) in (int, float) and math.isfinite(began) and began >= 0
         and value.get('phase_end_seconds') == PHASE_END, 'upload-clock-identity-mismatch')
    return began, began + PHASE_END['evidence'], began + PHASE_END['finalization']

def admit_upload(result, *, clock=time.monotonic):
    began, evidence_end, global_end = upload_ceiling(result)
    now = clock()
    # Full action timeout plus the original finalization reserve. No fresh clock.
    need(began <= now and now + 60 < evidence_end and now + 80 < global_end,
         'upload-full-admission-expired')
    return {'status': 'admitted', 'admitted_monotonic': now,
        'elapsed_at_admission': now - began, 'evidence_deadline': evidence_end,
        'global_deadline': global_end, 'action_timeout_seconds': 60,
        'finalization_reserve_seconds': 20, 'upload_qualified': False,
        'interval_scope': 'admission-through-post-action-observation-including-step-delays'}

def finish_upload(result, outcome, *, clock=time.monotonic):
    began, evidence_end, global_end = upload_ceiling(result)
    admission = result.get('upload_observation', {})
    started = admission.get('admitted_monotonic')
    now = clock()
    receipt = {'scope': 'post-upload-clock-gate', 'upload_qualified': False,
        'capture_qualified': result.get('qualified') is True,
        'action_outcome': outcome, 'started_monotonic': started,
        'observed_finished_monotonic': now, 'elapsed_since_original_start': now - began,
        'evidence_deadline': evidence_end, 'global_deadline': global_end,
        'interval_scope': 'includes-action-setup-and-inter-step-delay'}
    if (type(started) not in (int, float) or not math.isfinite(started)
            or admission.get('status') != 'admitted' or started < began
            or started + 60 >= evidence_end or started + 80 >= global_end
            or admission.get('evidence_deadline') != evidence_end
            or admission.get('global_deadline') != global_end or not math.isfinite(now) or now < started):
        receipt['failure'] = 'upload-admission-identity-mismatch'
    elif outcome != 'success':
        receipt['failure'] = 'upload-action-not-successful'
    elif now >= global_end:
        receipt['failure'] = 'upload-global-deadline-exceeded'
    elif now >= evidence_end:
        receipt['failure'] = 'upload-evidence-deadline-exceeded'
    elif now >= started + 60:
        receipt['failure'] = 'upload-admitted-phase-exceeded'
    else:
        receipt['upload_qualified'] = True
    return receipt

def upload_gate(mode, *, root=ROOT, env=None, clock=time.monotonic):
    env = os.environ if env is None else env
    identity = environment(env)
    path = root / OUTPUT / 'report.json'
    before = path.lstat()
    need(stat.S_ISREG(before.st_mode) and before.st_size <= MAX_REPORT, 'upload-report-invalid')
    with path.open('rb') as stream:
        payload = stream.read(MAX_REPORT + 1)
    need(len(payload) <= MAX_REPORT and file_identity(path.lstat()) == file_identity(before),
         'upload-report-changed')
    result = json.loads(payload)
    verify_retained_images(result, root/OUTPUT)
    timely(upload_ceiling(result)[2], clock)
    need(all(result.get('source_before', {}).get(k) == v for k, v in identity.items()),
         'upload-source-run-mismatch')
    if mode == 'finish-upload':
        receipt = finish_upload(result, env.get('CELLULOID_STORE_UPLOAD_OUTCOME', ''), clock=clock)
        # The uploaded proof explicitly leaves upload_qualified=false. This
        # final workflow log receipt is the separate retention qualification.
        print(json.dumps(receipt, sort_keys=True))
        _, _, global_end = upload_ceiling(result)
        admitted = result['upload_observation']['admitted_monotonic']
        timely(min(global_end, admitted + 80), clock)
        return 0 if receipt['upload_qualified'] else 1
    need(mode == 'admit-upload', 'unknown-upload-gate')
    result['upload_observation'] = admit_upload(result, clock=clock)
    payload = report_bytes(result)
    need(json.loads(payload).get('upload_observation') == result['upload_observation'], 'upload-report-byte-limit')
    path.write_bytes(payload)
    admit_upload(result, clock=clock)  # Report packing must not consume admission.
    marker = Path(env['GITHUB_OUTPUT']); offset = None
    try:
        with marker.open('a+', encoding='utf-8') as stream:
            stream.seek(0, os.SEEK_END); offset = stream.tell()
            stream.write('upload_admitted=true\n'); stream.flush()
            admit_upload(result, clock=clock)
        admit_upload(result, clock=clock)
        print(json.dumps(result['upload_observation'], sort_keys=True))
        admit_upload(result, clock=clock)
    except Rejected:
        if offset is not None:
            with marker.open('r+', encoding='utf-8') as stream:
                stream.truncate(offset)
        raise
    return 0


def environment(env):
    fixed = {'GITHUB_REPOSITORY':'100mango/Celluloid','GITHUB_REF':BRANCH,
        'GITHUB_WORKFLOW_REF':'100mango/Celluloid/'+WORKFLOW+'@'+BRANCH,
        'GITHUB_RUN_ATTEMPT':'1','GITHUB_JOB':'capture','GITHUB_EVENT_NAME':'push',
        'DEVELOPER_DIR':'/Applications/Xcode_27.app/Contents/Developer'}
    need(all(env.get(k)==v for k,v in fixed.items()),'fixed-capture-job-mismatch')
    need(re.fullmatch('[0-9a-f]{40}',env.get('GITHUB_SHA','')) is not None and
         env.get('GITHUB_WORKFLOW_SHA')==env['GITHUB_SHA'],'source-workflow-mismatch')
    need(re.fullmatch('[1-9][0-9]{0,19}',env.get('GITHUB_RUN_ID','')) is not None,'run-mismatch')
    need(env.get('CELLULOID_EXPECT_SANDBOX') != 'YES','sandbox-capture-not-authorized')
    return {k:env[k] for k in (*fixed,'GITHUB_SHA','GITHUB_WORKFLOW_SHA','GITHUB_RUN_ID')}


def source_identity(env, run, root=ROOT):
    identity=environment(env)
    def git(*args): return run(['git',*args],seconds=5,cap=256*1024).decode().strip()
    need(git('rev-parse','HEAD')==identity['GITHUB_SHA'],'head-mismatch')
    need(git('rev-parse',PARENT+'^{tree}')==PARENT_TREE,'parent-tree-mismatch')
    need(git('rev-list','--parents','-n','1','HEAD').split()==[identity['GITHUB_SHA'],PARENT],'sole-parent-mismatch')
    need(git('status','--porcelain','--untracked-files=all')=='','source-not-clean')
    expected=EXPECTED_DIFF
    need(sorted(git('diff','--name-status',PARENT,'HEAD','--').splitlines())==sorted(expected),'capture-source-scope')
    identity.update(tree=git('rev-parse','HEAD^{tree}'),parents=[PARENT],parent_tree=PARENT_TREE,base_tree=BASE_TREE)
    fixture=strict_json(read_file(root/'Scripts/fixtures/mac-store-source-baseline.json',128*1024))
    need(fixture['parent']==BASE and fixture['parent_tree']==BASE_TREE,'capture-fixture-parent')
    for path,value in {**fixture['current_app_inputs'],**fixture['current_support_inputs']}.items():
        need(hashlib.sha256(read_file(root/path,5_000_000)).hexdigest()==value,'capture-input-changed: '+path)
    for state,row in STATES.items():
        raw=read_file(root/'StoreCaptureAssets'/row['sourceFilename'],5_000_000)
        need(len(raw)==row['sourceBytes'] and hashlib.sha256(raw).hexdigest()==row['sourceSHA256'] and
            hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==SOURCE_BLOBS[state], 'capture-original-source-image')
    paths=sorted(set(NEW_PATHS)|set(MODIFIED_PATHS)|set(fixture['current_app_inputs'])|set(fixture['current_support_inputs']))
    identity['files']={p:hashlib.sha256(read_file(root/p,5_000_000)).hexdigest() for p in paths}
    return identity


def test_command():
    return base_command()+['-resultBundlePath',str(RESULT),'-parallel-testing-enabled','NO',
        '-collect-test-diagnostics','never','-test-timeouts-enabled','YES',
        '-maximum-test-execution-time-allowance','120',
        '-only-testing:CelluloidMacUITests/NativeEditorUITests/'+CASE,'test-without-building']


def execute(*, env=None, root=ROOT, clock=time.monotonic, wall=time.time, runner=capture):
    env=os.environ if env is None else env; began=clock(); receipts=[]; phase='prepare'; deadline=began+180
    report={'schema':1,'scope':'two-native-Mac-Store-window-captures','qualified':False,'store_qualified':False,
        'signing_qualified':False,'visual_acceptance':'pending-human-review','binary_handoff':False,
        'commands':receipts,'image_files':{},'diagnostic_files':{},'upload_qualified':False,
        'runner_cleanup':'not-observed',
        'clock':{'started_monotonic':began,'phase_end_seconds':PHASE_END,'report_ready_deadline':began+PHASE_END['final_source_pack']},
        'host_scope':'owned-client-and-process-group-observation; no independent-daemon lifetime claim'}
    def run(argv,**kwargs):return command(argv,deadline=deadline,receipts=receipts,clock=clock,wall=wall,runner=runner,**kwargs)
    try:
        need(not (root/'build').exists() and not (root/'build').is_symlink(),'output-not-fresh')
        (root/'build').mkdir(); report['owned_output']=file_identity((root/'build').lstat())[:2]
        report['source_before']=source_identity(env,run,root)
        report['toolchain']={'os':run(['sw_vers','-buildVersion'],seconds=5,cap=4096).decode().strip(),
            'architecture':run(['uname','-m'],seconds=5,cap=4096).decode().strip(),
            'xcode':run(['xcodebuild','-version'],seconds=10,cap=4096).decode().strip()}
        need(report['toolchain']==TOOLCHAIN,'toolchain-mismatch')
        for optimize in ([],['-O']):
            run([sys.executable,*optimize,'-m','unittest','discover','-s','Scripts','-p','test_mac_store*.py'],seconds=40,cap=65536)
        timely(deadline,clock)
        phase='build';deadline=min(began+PHASE_END[phase],clock()+440)
        output=run(base_command()+['build-for-testing'],seconds=420,cleanup=10,cap=512*1024)
        need(re.search(rb'(?im)(?:^|[ :])(?:fatal )?error:',output+b'\n'+receipts[-1]['stderr'].encode()) is None,'build-reported-error')
        report['product']=product_identity();timely(deadline,clock)
        phase='test';deadline=min(began+PHASE_END[phase],clock()+320)
        run(test_command(),seconds=300,cleanup=10,cap=512*1024,allowed=(0,65)); test=receipts[-1]
        report['test_outcome']='passed' if test['returncode']==0 else 'failed'
        phase='proof';deadline=min(began+PHASE_END[phase],clock()+180)
        summary=run(['xcrun','xcresulttool','get','test-results','summary','--path',str(RESULT)],seconds=20,cleanup=10,cap=512*1024)
        report['test_summary']=strict_json(summary)
        admitted=summary_admission(summary,test)
        need(admitted['passedTests']==1,'capture-case-failed')
        run(['xcrun','xcresulttool','export','attachments','--path',str(RESULT),'--output-path',str(EXPORT)],seconds=20,cleanup=10,cap=512*1024)
        # Preserve only this fixed demo case's safely admitted raw bytes before
        # any proof qualification. An integrity-rejected export is never retained.
        try:
            raw_evidence,raw_files=collect_raw(root/EXPORT,summary,report['product'],test,
                tick=lambda:timely(deadline,clock))
            (root/PREPARED).mkdir()
            for name,data in raw_files.items():
                timely(deadline,clock);(root/PREPARED/name).write_bytes(data)
            report['raw_evidence']=raw_evidence
            report['raw_context']={'test':{k:test[k] for k in ('command','returncode','started_epoch','finished_epoch')},
                'summaryText':summary.decode('utf-8')}
            report['image_files']={name:raw_evidence['files'][name] for name in raw_files if name in IMAGE_NAMES}
            report['diagnostic_files']={name:raw_evidence['files'][name] for name in raw_files if name not in IMAGE_NAMES}
        except (ValueError,OSError) as error:
            if isinstance(error,Rejected): raise
            report['raw_retention_failure']={'type':type(error).__name__,'reason':str(error)[:256]}
        proof,images=validate_capture(root/EXPORT,summary,report['product'],test,tick=lambda:timely(deadline,clock))
        need({'native-citrus.png','native-coast.png'}<=set(images)<=set(IMAGE_NAMES),'capture-image-list')
        need(product_identity()==report['product'],'product-changed-during-capture')
        (root/PREPARED).mkdir(exist_ok=True)
        need(not (root/PREPARED).is_symlink(),'unsafe-prepared-directory')
        for name,data in images.items():
            timely(deadline,clock);(root/PREPARED/name).write_bytes(data)
            report['image_files'][name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
        report['proof']=proof;report['runner_cleanup']=proof['display']['cleanupStatus'];timely(deadline,clock)
        phase='final_source_pack';deadline=min(began+PHASE_END[phase],clock()+30)
        report['clock']['report_ready_deadline']=deadline
        report['source_after']=source_identity(env,run,root)
        need(report['source_after']==report['source_before'],'source-changed')
        timely(deadline,clock);need(not proof['formatFailures'],'store-image-format-failed');report['qualified']=True
    except (Exception,KeyboardInterrupt) as error:
        report['clock']['report_ready_deadline']=min(report['clock']['report_ready_deadline'],clock()+30)
        report['failure']={'phase':phase,'type':type(error).__name__,'reason':str(error)[:4096]}
        if isinstance(error,ProofRejected): report['failure']['observations']=error.observations
        if 'proof' not in report or report.get('source_after')!=report.get('source_before'):
            # Raw retention is not proof qualification. Preserve the two admitted
            # native originals even when a later gate rejects case/clock/source.
            report['image_files']={name:row for name,row in report.get('raw_evidence',{}).get('files',{}).items()
                if name in ('native-citrus.png','native-coast.png')}
    report['clock']['elapsed_seconds']=clock()-began
    return report


def report_bytes(report):
    raw=(json.dumps(report,sort_keys=True,default=json_value,allow_nan=False,ensure_ascii=False,separators=(',',':'))+'\n').encode('utf-8','backslashreplace')
    if len(raw)>MAX_REPORT:
        keep=('schema','scope','source_before','source_after','clock','owned_output','toolchain','product','test_outcome','test_summary',
              'store_qualified','signing_qualified','visual_acceptance','binary_handoff','runner_cleanup','raw_evidence','raw_context','diagnostic_files','raw_retention_failure')
        compact={k:report[k] for k in keep if k in report}
        native={name:row for name,row in report.get('raw_evidence',{}).get('files',{}).items()
            if name in ('native-citrus.png','native-coast.png')}
        compact.update(qualified=False,image_files=native,upload_qualified=False,
            failure={'type':'Rejected','reason':'report-byte-limit','original_failure':report.get('failure')})
        raw=(json.dumps(compact,sort_keys=True,default=json_value,allow_nan=False,ensure_ascii=False,separators=(',',':'))+'\n').encode('utf-8','backslashreplace')
        need(len(raw)<=MAX_REPORT,'capture-report-fallback-byte-limit')
    return raw


def verify_retained_images(report, output):
    files=report.get('image_files');need(isinstance(files,dict) and set(files)<=set(IMAGE_NAMES),'retained-image-list')
    diagnostic=report.get('diagnostic_files',{})
    need(isinstance(diagnostic,dict) and set(diagnostic)<=set(RAW_LIMITS)-set(IMAGE_NAMES),'retained-diagnostic-list')
    need(set(p.name for p in output.iterdir())==set(files)|set(diagnostic)|{'report.json'},'unlisted-retained-file')
    if report['qualified']:need(set(files)==set(IMAGE_NAMES),'missing-native-or-store-image')
    total=len(read_file(output/'report.json',MAX_REPORT))
    for name,expected in {**files,**diagnostic}.items():
        raw=read_file(output/name,RAW_LIMITS[name] if name in RAW_LIMITS else 3*1024*1024);total+=len(raw)
        need(expected=={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()},'changed-retained-image')
    if 'raw_evidence' in report:
        evidence=report['raw_evidence'];expected={**diagnostic,**{k:v for k,v in files.items() if k.startswith('native-')}}
        need(evidence.get('status')=='unqualified' and evidence.get('visual_pending') is True and
            evidence.get('files')==expected,'raw-evidence-status-or-files')
        _replay_raw_files(report,output)
    else: need(not diagnostic,'unbound-raw-diagnostics')
    need(total<=MAX_PACKET,'capture-packet-byte-limit')


def _replay_raw_files(report, output):
    evidence=report['raw_evidence'];mapping=evidence.get('exportedNames')
    need(isinstance(mapping,dict) and set(mapping)==set(evidence['files']),'raw-export-map')
    virtual=Path('/retained-raw-capture');files={}
    for name,exported in mapping.items():
        need(name in RAW_LIMITS and isinstance(exported,str) and
            (exported=='manifest.json' if name=='raw-manifest.json' else re.fullmatch(r'[0-9A-Fa-f-]{36}\.(png|txt)',exported)),
            'raw-export-path')
        need(virtual/exported not in files,'raw-export-alias')
        files[virtual/exported]=read_file(output/name,RAW_LIMITS[name])
    def read(path,limit):
        need(path in files and len(files[path])<=limit,'raw-export-missing-or-large');return files[path]
    context=report.get('raw_context',{});test=context.get('test')
    need(isinstance(test,dict) and test.get('command')==test_command(),'raw-test-command-missing')
    text=context.get('summaryText')
    need(isinstance(text,str) and len(text.encode())<=512*1024,'raw-summary-text-bound')
    summary=text.encode('utf-8')
    need(strict_json(summary)==report['test_summary'],'raw-summary-mismatch')
    reproduced,_=collect_raw(virtual,summary,report['product'],test,read=read)
    need(reproduced==evidence,'raw-retention-integrity-mismatch')
    return virtual,summary,test,read


def inspect_raw_packet(output, *, sha, tree, run_id, source_root=ROOT):
    """Offline diagnosis of preserved originals; never changes their qualification."""
    report=strict_json(read_file(output/'report.json',MAX_REPORT));verify_retained_images(report,output)
    source=report.get('source_before',{});environment(source)
    need(source.get('GITHUB_SHA')==sha and source.get('tree')==tree and source.get('GITHUB_RUN_ID')==str(run_id) and
        source.get('parents')==[PARENT] and source.get('parent_tree')==PARENT_TREE and source.get('base_tree')==BASE_TREE,
        'raw-source-run-mismatch')
    fixture=strict_json(read_file(source_root/'Scripts/fixtures/mac-store-source-baseline.json',128*1024))
    names=set(NEW_PATHS)|set(MODIFIED_PATHS)|set(fixture['current_app_inputs'])|set(fixture['current_support_inputs'])
    need(source.get('files')=={p:hashlib.sha256(read_file(source_root/p,5_000_000)).hexdigest() for p in names},'raw-source-files-mismatch')
    virtual,summary,test,read=_replay_raw_files(report,output)
    result={'status':'unqualified','visual_pending':True,'raw_integrity':True,'proof_replay_passed':False}
    try:
        proof,_=validate_capture(virtual,summary,report['product'],test,read=read)
        result.update(proof_replay_passed=not proof['formatFailures'],format_failures=proof['formatFailures'],
            observed_runner_cleanup=proof['display']['cleanupStatus'])
    except ValueError as error:
        result['proof_failure']={'reason':str(error)[:4096],'type':type(error).__name__}
        if isinstance(error,ProofRejected):result['proof_failure']['observations']=error.observations
    return result


def validate_packet(output, *, sha, tree, run_id, source_root=ROOT):
    """Offline replay of retained assertions; never launches or queries an app."""
    report=strict_json(read_file(output/'report.json',MAX_REPORT));verify_retained_images(report,output)
    need(report['qualified'] is True and report['store_qualified'] is False and report['signing_qualified'] is False and
        report['binary_handoff'] is False and report['visual_acceptance']=='pending-human-review','capture-not-qualified')
    source=report['source_before'];environment(source)
    need(source['GITHUB_SHA']==sha and source['tree']==tree and source['GITHUB_RUN_ID']==str(run_id) and source==report['source_after'] and
        source['parents']==[PARENT] and source['parent_tree']==PARENT_TREE and source['base_tree']==BASE_TREE,'retained-source-run-mismatch')
    fixture=strict_json(read_file(source_root/'Scripts/fixtures/mac-store-source-baseline.json',128*1024))
    names=set(NEW_PATHS)|set(MODIFIED_PATHS)|set(fixture['current_app_inputs'])|set(fixture['current_support_inputs'])
    need(source['files']=={p:hashlib.sha256(read_file(source_root/p,5_000_000)).hexdigest() for p in names},'retained-source-files-mismatch')
    prefix=[['git','rev-parse','HEAD'],['git','rev-parse',PARENT+'^{tree}'],['git','rev-list','--parents','-n','1','HEAD'],
        ['git','status','--porcelain','--untracked-files=all'],['git','diff','--name-status',PARENT,'HEAD','--'],['git','rev-parse','HEAD^{tree}']]
    commands=report['commands'];need(len(commands)==21,'capture-command-count')
    executable=commands[9]['command'][0]
    middle=[['sw_vers','-buildVersion'],['uname','-m'],['xcodebuild','-version'],
        [executable,'-m','unittest','discover','-s','Scripts','-p','test_mac_store*.py'],
        [executable,'-O','-m','unittest','discover','-s','Scripts','-p','test_mac_store*.py'],
        base_command()+['build-for-testing'],test_command(),
        ['xcrun','xcresulttool','get','test-results','summary','--path',str(RESULT)],
        ['xcrun','xcresulttool','export','attachments','--path',str(RESULT),'--output-path',str(EXPORT)]]
    need([x['command'] for x in commands]==prefix+middle+prefix,'capture-command-plan')
    need(report.get('toolchain')==TOOLCHAIN and
        [commands[i]['stdout'].strip() for i in (6,7,8)]==[TOOLCHAIN[k] for k in ('os','architecture','xcode')],
        'retained-toolchain-mismatch')
    expected_output=[sha+'\n',PARENT_TREE+'\n',sha+' '+PARENT+'\n','',
        '\n'.join(EXPECTED_DIFF)+'\n',tree+'\n']
    for offset in (0,15):
        for index,expected in enumerate(expected_output):
            actual=commands[offset+index]['stdout']
            need(sorted(actual.splitlines())==sorted(expected.splitlines()) if index==4 else actual==expected,'capture-source-query-mismatch')
    need(report['clock']['phase_end_seconds']==PHASE_END,'capture-clock-source')
    began=report['clock']['started_monotonic'];prior=began
    for index,row in enumerate(commands):
        need(row['returncode']==0 and row['complete'] is True and prior<=row['start']<=row['end']<row['start']+row['grant_seconds'] and
            row['owned_host_observation']=='client-reaped-pipes-closed-group-absent-at-return','capture-command-not-closed')
        phase='prepare' if index<11 else 'build' if index==11 else 'test' if index==12 else 'proof' if index<15 else 'final_source_pack'
        need(row['end']<began+PHASE_END[phase] and row['started_epoch']<=row['finished_epoch'],'capture-command-clock')
        prior=row['end']
    need(prior<report['clock']['report_ready_deadline']<=began+PHASE_END['final_source_pack'],'capture-retention-clock')
    summary_raw=commands[13]['stdout'].encode('utf-8')
    need(strict_json(summary_raw)==report['test_summary'],'retained-summary-mismatch')
    proof=report['proof'];virtual=Path('/retained-capture');files={virtual/'manifest.json':proof['manifestText'].encode('utf-8')}
    for suffix in ('setup','restore'):
        if proof['display'][suffix+'Attachment'] is not None:
            files[virtual/proof['display'][suffix+'Attachment']['exportedFileName']]=proof['display'][suffix+'Text'].encode('utf-8')
    for state,row in proof['states'].items():
        need(state in ('citrus','coast'),'retained-state')
        files[virtual/row['receiptAttachment']['exportedFileName']]=row['receiptText'].encode('utf-8')
        files[virtual/row['imageAttachment']['exportedFileName']]=read_file(output/('native-'+state+'.png'),3*1024*1024)
    def read(path,limit):
        need(path in files and len(files[path])<=limit,'retained-attachment-missing-or-large');return files[path]
    reproduced,_=validate_capture(virtual,summary_raw,report['product'],commands[12],read=read)
    from mac_store_png import decode
    for state,row in reproduced['states'].items():
        original=proof['states'][state]
        need({k:v for k,v in row.items() if k!='storePNG'}=={k:v for k,v in original.items() if k!='storePNG'},'retained-capture-proof-mismatch')
        raw=read_file(output/('store-'+state+'.png'),3*1024*1024);rgb,_,color=decode(raw)
        need(color==2 and hashlib.sha256(rgb).hexdigest()==row['conversion']['rgbSHA256'] and
            original['storePNG']=={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()},'retained-store-pixels-mismatch')
    need({k:v for k,v in reproduced.items() if k!='states'}=={k:v for k,v in proof.items() if k!='states'},'retained-proof-summary-mismatch')
    need(report['runner_cleanup']==proof['display']['cleanupStatus'],'retained-cleanup-observation-mismatch')
    return report


def retain_report(result, output, marker, *, root=ROOT, clock=time.monotonic):
    deadline=result['clock']['report_ready_deadline'];offset=None
    try:
        timely(deadline,clock);payload=report_bytes(result);decoded=strict_json(payload)
        identities={**decoded['image_files'],**decoded.get('diagnostic_files',{})}
        images={name:read_file(root/PREPARED/name,RAW_LIMITS[name] if name in RAW_LIMITS else 3*1024*1024) for name in identities}
        for name,raw in images.items():need(identities[name]=={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()},'prepared-image-changed')
        need(len(payload)+sum(map(len,images.values()))<=MAX_PACKET,'capture-packet-byte-limit')
        timely(deadline,clock);output.mkdir(exist_ok=False)
        for name,raw in images.items():timely(deadline,clock);(output/name).write_bytes(raw)
        (output/'report.json').write_bytes(payload);verify_retained_images(decoded,output);timely(deadline,clock)
        with marker.open('a+',encoding='utf-8') as stream:
            stream.seek(0,os.SEEK_END);offset=stream.tell();stream.write('evidence_ready=true\n');stream.flush()
            if clock()>=deadline:
                stream.truncate(offset);raise Rejected('deadline-exceeded')
        timely(deadline,clock);return decoded
    except Rejected:
        if offset is not None:
            with marker.open('r+',encoding='utf-8') as stream:stream.truncate(offset)
        raise


def main():
    os.chdir(ROOT)
    if len(sys.argv)==2 and sys.argv[1] in ('admit-upload','finish-upload'):return upload_gate(sys.argv[1])
    need(len(sys.argv)==1,'no-input-selectors');result=execute()
    if 'owned_output' not in result:print(json.dumps(result,default=json_value));return 1
    need(stat.S_ISDIR((ROOT/'build').lstat().st_mode) and file_identity((ROOT/'build').lstat())[:2]==result['owned_output'],'output-ownership-changed')
    result=retain_report(result,ROOT/OUTPUT,Path(os.environ['GITHUB_OUTPUT']))
    print(json.dumps({'capture_qualified':result['qualified'],'store_qualified':False,'visual_acceptance':'pending-human-review',
        'runner_cleanup':result.get('runner_cleanup'),'failure':result.get('failure')}))
    return 0 if result['qualified'] and result.get('runner_cleanup')=='restored' else 1


if __name__=='__main__':raise SystemExit(main())
