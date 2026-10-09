"""Narrow owned-synthetic boundary data plane; no native commands or workflow.

Caller must retain the existing host source/product/execution admission. No
function here grants full host acceptance or launches Photos. The reader opens
only this explicit run/generation's fixed files in the known extension container.
"""
import datetime,hashlib,json,math,os,plistlib,re,secrets,stat,time
from pathlib import Path

FIXTURE='6138992615dd7d5bd499b80d9f11e39a0815111feccd5d4d3e59a676f4384772'
BUNDLE='Mango.Celluloid.CelluloidPhotoExtension'
LEASE_KEYS={'schema','source_sha','source_tree','run_id','run_attempt','fixture_sha256','nonce','raw_cap'}
ARM_KEYS={'schema','lease','identity_sha256','generation','input_sha256','recipe_sha256','source_id'}
RUNTIME_KEYS={'schema','platform','osVersion','osBuildNumber','architecture','diagnostic_only','qualification_equivalence'}
RUNTIME_PAIRS=frozenset({('27.0','26A428'),('27.0.1','26A434')})
PREFIX='MAC_PHOTOS_BOUNDARY_ARM '
SAVE_STAGE='lifecycle-save-and-export'
PIXEL_REASON='Stored saved raster disagrees with independent JPEG-aware reference'
PIXEL_FAILURE_TEXT='failed: caught error: "Error Domain=MacPhotosHostPrerequisite Code=1 "'+PIXEL_REASON+'" UserInfo={NSLocalizedDescription='+PIXEL_REASON+'}"'
RAW_CAP=131072
TOTAL_CAP=212992
UUID=r'[0-9A-F]{8}(?:-[0-9A-F]{4}){3}-[0-9A-F]{12}'
def require(ok,message):
    if not ok:raise ValueError(message)
def sha(data):return hashlib.sha256(data).hexdigest()
def json_bytes(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def decode(data):
    def unique(pairs):
        result={}
        for key,value in pairs:
            require(key not in result,'duplicate JSON key');result[key]=value
        return result
    return json.loads(data,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite JSON')))
def validate_runtime_record(row):
    """Exact diagnostic allowlist only; never establishes qualification equivalence."""
    require(type(row) is dict and set(row)==RUNTIME_KEYS,'boundary runtime schema/keys')
    require(all(type(row[key]) is str for key in ['schema','platform','osVersion','osBuildNumber','architecture']),
        'boundary runtime types')
    require(row['schema']=='Celluloid.OwnedPhotosBoundaryRuntime.1'
        and row['platform']=='macOS' and row['architecture']=='arm64'
        and (row['osVersion'],row['osBuildNumber']) in RUNTIME_PAIRS,'boundary runtime not allowed')
    require(row['diagnostic_only'] is True and row['qualification_equivalence'] is False,
        'boundary runtime diagnostic truth boundary')
    return dict(row)

def runtime_record(version,build,architecture):
    """Pure record of the driver's early native runtime observations."""
    return validate_runtime_record(dict(schema='Celluloid.OwnedPhotosBoundaryRuntime.1',platform='macOS',
        osVersion=version,osBuildNumber=build,architecture=architecture,
        diagnostic_only=True,qualification_equivalence=False))

def lease_valid(row):
    require(type(row) is dict and set(row)==LEASE_KEYS and all(type(v) is str for v in row.values()),'lease schema/types')
    require(row['schema']=='Celluloid.OwnedPhotosBoundaryLease.1' and row['fixture_sha256']==FIXTURE
            and row['run_attempt']=='1' and row['raw_cap']=='131072','lease contract')
    for key,width in [('source_sha',40),('source_tree',40),('nonce',64)]:
        require(re.fullmatch('[0-9a-f]{'+str(width)+'}',row[key]) is not None,'lease '+key)
    require(re.fullmatch('[1-9][0-9]{0,19}',row['run_id']) is not None,'lease run')
    return row

def prepare_lease(original_plist,source_sha,source_tree,run_id,run_attempt):
    """Pure preparation. Caller writes returned plist outside tracked source.

    Enable only the extension Debug target's two build variables. Pass these
    same bytes to bind_context after the ordinary verified product/context step.
    This does not replace either existing before/after source gate.
    """
    lease=lease_valid(dict(schema='Celluloid.OwnedPhotosBoundaryLease.1',source_sha=source_sha,
        source_tree=source_tree,run_id=run_id,run_attempt=run_attempt,fixture_sha256=FIXTURE,
        nonce=secrets.token_hex(32),raw_cap='131072'))
    info=plistlib.loads(original_plist)
    require(type(info) is dict and 'CelluloidOwnedPhotosBoundaryLease' not in info,'preexisting lease')
    require(info.get('NSExtension',{}).get('NSExtensionPointIdentifier')=='com.apple.photo-editing','wrong original plist')
    info['CelluloidOwnedPhotosBoundaryLease']=lease
    return lease,plistlib.dumps(info,sort_keys=True)

def bind_context(context,lease,processed_extension_plist):
    lease_valid(lease)
    runtime=validate_runtime_record(context.get('boundary_runtime'))
    require('boundary_probe' not in context,'context already bound')
    require(context['source_sha']==lease['source_sha'] and context['extension_id']==BUNDLE,'wrong context source/bundle')
    env=context['runner_environment']
    require(env['GITHUB_SHA']==env['GITHUB_WORKFLOW_SHA']==lease['source_sha'],'wrong workflow source')
    require(env['GITHUB_ACTIONS']=='true' and env['GITHUB_REPOSITORY']=='100mango/Celluloid'
        and env['GITHUB_EVENT_NAME']=='push','wrong workflow identity')
    require(env['GITHUB_RUN_ID']==lease['run_id'] and env['GITHUB_RUN_ATTEMPT']=='1','wrong run/attempt')
    info=plistlib.loads(processed_extension_plist)
    require(info.get('CFBundleIdentifier')==BUNDLE and info.get('CelluloidOwnedPhotosBoundaryLease')==lease,'wrong built lease')
    result=dict(context)
    result['boundary_runtime']=runtime
    result['boundary_probe']={'lease':lease,'extension_info_sha256':sha(processed_extension_plist),
        'scope':'owned-synthetic-input-intended-jpeg-saved-export','full_lifecycle_acceptance':False,
        'performance_acceptance':False}
    return result

def validate_arm(arm,context,identity):
    lease=context['boundary_probe']['lease'];lease_valid(lease)
    require(type(arm) is dict and set(arm)==ARM_KEYS,'arm schema/keys')
    require(arm['schema']=='Celluloid.OwnedPhotosBoundaryArm.1' and arm['lease']==lease,'arm lease')
    require(arm['generation']==identity['generation'] and re.fullmatch(UUID,arm['generation']) is not None,'arm generation')
    for key in ['input_sha256','recipe_sha256','identity_sha256']:
        require(type(arm[key]) is str and re.fullmatch('[0-9a-f]{64}',arm[key]) is not None,'arm '+key)
    require(type(arm['source_id']) is str and re.fullmatch(UUID,arm['source_id']) is not None,'arm source id')
    return arm

def admit_saved_outcome(records,context,context_hash,raw_log,summary,accounting):
    """Admit only the one owned Save/export, before ANY container open.

    A finalized Failed case alone is insufficient. Unknown/denied UI branches,
    missing outcomes and contradictory raw failures never authorize this read.
    """
    outcome=decode(records.get('outcome.json',b'null'))
    required={'source_sha','host_entry_contract','last_stage','complete_host_e2e','save_reopen_cancel_revert'}
    allowed=required|{'first_blocked_operation','export_png_diagnostics','extension_menu_observation'}
    require(type(outcome) is dict and required<=set(outcome)<=allowed,'missing/unknown outcome')
    require(outcome['source_sha']==context['source_sha'] and outcome['host_entry_contract']=='Celluloid.PhotosHostEntry.3'
        and outcome['last_stage']==SAVE_STAGE and outcome['complete_host_e2e'] is False
        and outcome['save_reopen_cancel_revert']=='PhotosFilterLifecycle.1 incomplete','wrong final saved outcome')
    passed=summary['result']=='Passed'
    blocked=[line for line in raw_log.splitlines() if 'MAC_HOST_BLOCKED' in line]
    if passed:
        require('first_blocked_operation' not in outcome and not blocked and not accounting['scoped_errors'],
            'blocked operation contradicts saved success')
    else:
        operation=outcome.get('first_blocked_operation')
        require(type(operation) is dict and set(operation)=={'stage','reason','operation'}
            and operation['stage']==SAVE_STAGE and operation['reason']==PIXEL_REASON,'non-pixel/unknown blocked operation')
        detail=operation['operation']
        require(type(detail) is dict and set(detail)=={'max_channel_delta'}
            and type(detail['max_channel_delta']) is int and 2<detail['max_channel_delta']<=255,'invalid failed pixel delta')
        require(blocked==['MAC_HOST_BLOCKED stage='+SAVE_STAGE+' reason='+PIXEL_REASON],
            'unknown/missing/duplicate raw blocked operation')
        failures=summary.get('testFailures')
        require(type(failures) is list and len(failures)==1 and failures[0].get('failureText')==PIXEL_FAILURE_TEXT,
            'non-pixel/unknown summary failure')
        errors=accounting['scoped_errors']
        require(len(errors)==1 and errors[0]['line'].endswith(' : '+PIXEL_FAILURE_TEXT),
            'additional/non-pixel raw failure')
    # Require the actual retained saved-export prefix, not a bare stage string.
    lifecycle=decode(records.get('lifecycle.json',b'null'))
    require(type(lifecycle) is dict and lifecycle.get('schema')=='Celluloid.PhotosFilterLifecycle.1'
        and lifecycle.get('source_sha')==context['source_sha'] and lifecycle.get('context_sha256')==context_hash
        and lifecycle.get('fixture_sha256')==FIXTURE and lifecycle.get('complete') is False,'missing/wrong saved lifecycle')
    phases=lifecycle.get('phases');names=['source-retained','fade-ready']+(['saved-export'] if passed else [])
    require(type(phases) is list and len(phases)==len(names)
        and all(type(row) is dict and type(row.get('index')) is int and row['index']==i and row.get('name')==name
            for i,(row,name) in enumerate(zip(phases,names))),'wrong saved lifecycle prefix')
    if passed:
        detail=phases[-1].get('details')
        require(type(detail) is dict and set(detail)=={'max_channel_delta','limit','sole_asset_count'}
            and type(detail['max_channel_delta']) is int and 0<=detail['max_channel_delta']<=2
            and type(detail['limit']) is int and detail['limit']==2
            and type(detail['sole_asset_count']) is int and detail['sole_asset_count']==1,'wrong saved pixel success')
    exports=lifecycle.get('raw_exports');images=lifecycle.get('images')
    require(type(exports) is dict and set(exports)=={'saved'} and type(images) is dict
        and set(images)=={'lifecycle-source.png','lifecycle-expected-save.png','lifecycle-saved.png'},'missing/extra saved image evidence')
    saved=exports['saved']
    require(type(saved) is dict and set(saved)=={'bytes','sha256','image','relative_path'}
        and saved['image']=='lifecycle-saved.png' and saved['relative_path']=='saved/Celluloid-Owned-Host.png'
        and type(saved['bytes']) is int and 0<saved['bytes']<=131072
        and type(saved['sha256']) is str and re.fullmatch('[0-9a-f]{64}',saved['sha256']) is not None,
        'wrong saved export identity')
    require(type(images['lifecycle-saved.png']) is dict and images['lifecycle-saved.png'].get('sha256')==saved['sha256']
        and images['lifecycle-saved.png'].get('bytes')==saved['bytes'],'saved export/image contradiction')
    return outcome

def bound_arm(context_bytes,raw_log,summary):
    """Require original finalized exact case, then its existing actual-host proofs.

    A legitimate finalized failed pixel assertion may preserve boundary evidence.
    Unknown, skipped, interrupted or timed-out cases cannot reach the reader.
    """
    from final_mac_photos_transport import parse,CASE
    from mac_host_self_identity import validate
    from consumer_runtime_binding import validate_raw_execution
    context=decode(context_bytes)
    runtime=validate_runtime_record(context.get('boundary_runtime'))
    records=parse(raw_log,context,sha(context_bytes),complete=False)
    require(type(summary) is dict and summary.get('result') in {'Passed','Failed'},'unknown summary')
    wanted={'totalTestCount':1,'passedTests':int(summary['result']=='Passed'),
        'failedTests':int(summary['result']=='Failed'),'skippedTests':0,'expectedFailures':0}
    require(all(type(summary.get(k)) is int and summary[k]==v for k,v in wanted.items()),'summary counts')
    require(bool(summary.get('testFailures'))==(summary['result']=='Failed'),'summary failure details')
    configs=summary.get('devicesAndConfigurations')
    require(type(configs) is list and len(configs)==1,'ambiguous summary device')
    config=configs[0]
    require(type(config) is dict and type(config.get('device')) is dict,'wrong actual Mac runtime/counts')
    device=config['device']
    require(all(type(config.get(k)) is int and config[k]==wanted[k] for k in ['passedTests','failedTests','skippedTests','expectedFailures'])
        and (device.get('platform'),device.get('osVersion'),device.get('osBuildNumber'),device.get('architecture'))
        ==tuple(runtime[k] for k in ['platform','osVersion','osBuildNumber','architecture']),
        'wrong actual Mac runtime/counts')
    lease=lease_valid(context['boundary_probe']['lease']);env=context['runner_environment']
    require(env.get('GITHUB_RUN_ID')==lease['run_id'] and env.get('GITHUB_RUN_ATTEMPT')=='1'
        and env.get('GITHUB_SHA')==env.get('GITHUB_WORKFLOW_SHA')==context['source_sha']==lease['source_sha'],'wrong original run/source')
    accounting=validate_raw_execution(raw_log,summary)
    bundle=str(Path(context['runner_environment']['RUNNER_TEMP'])/'MacPhotosHost.xcresult')
    require(accounting['result_session_path_observation']==bundle,'wrong finalized result path')
    begin=decode(next(line[len('BOUNDED_COMMAND_BEGIN '):] for line in raw_log.splitlines() if line.startswith('BOUNDED_COMMAND_BEGIN ')))
    end=decode(next(line[len('BOUNDED_COMMAND_END '):] for line in raw_log.splitlines() if line.startswith('BOUNDED_COMMAND_END ')))
    require(end['exit_code']==(0 if summary['result']=='Passed' else 65),'native/summary terminal contradiction')
    started=datetime.datetime.fromisoformat(begin['utc']).timestamp()
    require(all(type(summary.get(k)) in (int,float) and math.isfinite(summary[k]) for k in ['startTime','finishTime'])
        and started<=summary['startTime']<summary['finishTime']<=started+end['elapsed_seconds'],'summary outside original host command')
    require('BOUNDED_COMMAND_TIMEOUT' not in raw_log and 'BOUNDED_TIMEOUT_' not in raw_log,'timed-out host')
    events=[];active=False;found=[]
    for line in raw_log.splitlines():
        if line.startswith("Test Case '-["):
            if line.endswith(' started.') or line.endswith("started."):
                active=True;events.append('started')
            elif ' passed (' in line: active=False;events.append('passed')
            elif ' failed (' in line: active=False;events.append('failed')
            elif ' skipped (' in line: active=False;events.append('skipped')
        if PREFIX.strip() in line:
            require(line.startswith(PREFIX) and active and len(line.encode())<=8192,'arm outside active exact case')
            found.append(decode(line[len(PREFIX):]))
    require(events in [['started','passed'],['started','failed']] and len(found)==1,'unknown/repeated arm case')
    photos=decode(records['photos-process.json']);ownership=decode(records['fixture-ownership.json'])
    identity_row=decode(records['extension-self-identity.json'])
    identity=validate(identity_row,context,photos,ownership)
    require(ownership['fixture_sha256']==FIXTURE and ownership['initial_count']==0 and ownership['selected_count']==1,'non-owned fixture')
    row=found[0]
    require(type(row) is dict and set(row)=={'schema','context_sha256','source_sha','arm'}
        and row['schema']=='Celluloid.OwnedPhotosBoundaryHostArm.1'
        and row['source_sha']==context['source_sha'] and row['context_sha256']==sha(context_bytes),'wrong host arm binding')
    arm=validate_arm(row['arm'],context,identity)
    identity_raw=identity_row['observations'][0]['raw']
    require(arm['identity_sha256']==sha(identity_raw.encode()),'wrong raw identity')
    require(lease_valid(context['boundary_probe']['lease'])['source_sha']==context['source_sha'],'lease source')
    admit_saved_outcome(records,context,sha(context_bytes),raw_log,summary,accounting)
    return context,arm,identity_raw

def read_capture(context,arm,identity_raw,home):
    """No enumeration, discovery, reported path or fallback. Denial propagates.

    `home` is the trusted runner home, never a path taken from extension output.
    Caller must first admit its original host execution with bound_arm().
    """
    identity=decode(identity_raw);validate_arm(arm,context,identity)
    require(arm['identity_sha256']==sha(identity_raw.encode()),'identity digest')
    require(identity['bundle_identifier']==BUNDLE,'identity bundle')
    started=time.monotonic()
    def check():require(time.monotonic()-started<=2,'capture reader checked budget')
    parts=['Library','Containers',BUNDLE,'Data','Library','Caches','CelluloidOwnedPhotosBoundary',
        arm['lease']['nonce'],arm['generation']]
    descriptors=[];snapshots=[]
    def snap(s):return (s.st_dev,s.st_ino,s.st_mode,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    try:
        check();parent=os.open(home,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW);descriptors.append(parent)
        for part in parts:
            check();child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=parent)
            descriptors.append(child);before=os.fstat(child)
            require(stat.S_ISDIR(before.st_mode) and before.st_uid==os.getuid(),'unowned capture directory')
            snapshots.append((parent,part,child,snap(before)));parent=child
        def read(name,limit):
            check();fd=os.open(name,os.O_RDONLY|os.O_NONBLOCK|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=parent)
            try:
                before=os.fstat(fd)
                require(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_uid==os.getuid()
                        and 0<before.st_size<=limit,'capture file type/size/owner')
                data=os.read(fd,limit+1);check()
                require(len(data)==before.st_size and not os.read(fd,1),'short/growing capture file')
                require(snap(before)==snap(os.fstat(fd))==snap(os.stat(name,dir_fd=parent,follow_symlinks=False)),'changed capture file')
                return data
            finally:os.close(fd)
        receipt=read('capture.json',8192);row=decode(receipt)
        expected=set(ARM_KEYS)|{'identity_raw','capture_stage','writer_claim_observed','photos_acceptance_observed',
            'performance_acceptance','orientation','input_bytes','intended_jpeg_bytes','intended_jpeg_sha256',
            'checked_budget_ms','hard_realtime_bound','elapsed_before_receipt_ms'}
        require(type(row) is dict and set(row)==expected,'capture schema/keys')
        require(row['schema']=='Celluloid.OwnedPhotosBoundaryCapture.1','capture schema')
        require(all(row[k]==v for k,v in arm.items() if k!='schema') and row['identity_raw']==identity_raw,'capture arm/identity')
        require(row['capture_stage']=='before-writer-start-intended-same-jpeg'
            and row['writer_claim_observed'] is False and row['photos_acceptance_observed'] is False
            and row['performance_acceptance'] is False and row['hard_realtime_bound'] is False,'capture truth boundary')
        require(type(row['orientation']) is int and row['orientation']==1
            and type(row['checked_budget_ms']) is int and row['checked_budget_ms']==500
            and type(row['elapsed_before_receipt_ms']) in (int,float) and 0<=row['elapsed_before_receipt_ms']<=500,'capture geometry/time')
        source=read('input.bytes',65536);jpeg=read('intended.jpg',65536)
        require(type(row['input_bytes']) is int and row['input_bytes']==len(source)
            and type(row['intended_jpeg_bytes']) is int and row['intended_jpeg_bytes']==len(jpeg),'capture byte counts')
        require(sha(source)==row['input_sha256'] and sha(jpeg)==row['intended_jpeg_sha256']
            and jpeg.startswith(b'\xff\xd8\xff'),'capture hashes/JPEG')
        require(len(source)+len(jpeg)<=RAW_CAP,'raw aggregate')
        for parent,name,fd,before in snapshots:
            check();require(before==snap(os.fstat(fd))==snap(os.stat(name,dir_fd=parent,follow_symlinks=False)),'changed capture directory')
        return {'input.bytes':source,'intended.jpg':jpeg,'capture.json':receipt}
    finally:
        for fd in reversed(descriptors):os.close(fd)

def admit_comparison(capture,outputs,old_images,icc):
    """Independent PNG replay. Always diagnostic, including when old <=2 fails.

    The unchanged full-host validator still owns acceptance. Required originals
    and these bytes must fit its existing 1,000,000-byte packet before optional
    screenshots; the route must not drop nodes or raise that outer cap.
    """
    from mac_host_lifecycle_pixels import decode as decode_png,compare
    require(set(capture)=={'input.bytes','intended.jpg','capture.json'},'missing capture nodes')
    caps={'input.bytes':65536,'intended.jpg':65536,'capture.json':8192,
        'intended-decoded.png':32768,'input-reference.png':32768,'boundary-comparison.json':8192}
    require(set(outputs)=={'intended-decoded.png','input-reference.png','boundary-comparison.json'},'missing comparison nodes')
    joined={**capture,**outputs}
    require(all(type(data) is bytes and 0<len(data)<=caps[name] for name,data in joined.items())
        and sum(map(len,joined.values()))<=TOTAL_CAP,'boundary artifact caps')
    require(set(old_images)=={'lifecycle-source.png','lifecycle-expected-save.png','lifecycle-saved.png'},'missing original nodes')
    require(sha(old_images['lifecycle-source.png'])==FIXTURE,'wrong original fixture')
    row=decode(outputs['boundary-comparison.json'])
    require(row.get('schema')=='Celluloid.OwnedPhotosBoundaryComparison.1'
        and all(row.get(k) is False for k in ['acceptance','complete_host_e2e','photos_internal_storage_observed','performance_acceptance']),
        'comparison truth boundary')
    for key,data in [('input',capture['input.bytes']),('intended',capture['intended.jpg']),
        ('saved',old_images['lifecycle-saved.png']),('fixture',old_images['lifecycle-source.png']),
        ('historical_reference',old_images['lifecycle-expected-save.png']),('input_reference',outputs['input-reference.png'])]:
        require(row.get(key,{}).get('sha256')==sha(data) and row[key].get('bytes')==len(data),'wrong compared '+key)
    receipt=decode(capture['capture.json'])
    require(receipt['input_sha256']==sha(capture['input.bytes'])
        and receipt['intended_jpeg_sha256']==row.get('intended_jpeg_sha256')==sha(capture['intended.jpg']),'comparison/capture contradiction')
    decoded={name:decode_png(data,icc) for name,data in {**old_images,
        'intended-decoded.png':outputs['intended-decoded.png'],'input-reference.png':outputs['input-reference.png']}.items()}
    require(decoded['intended-decoded.png']['rgba_sha256']==row['intended'].get('rgba_sha256'),'intended decode digest')
    require(decoded['input-reference.png']['rgba_sha256']==row['input_reference'].get('rgba_sha256'),'input reference digest')
    for key,a,b in [('intended_vs_input_reference','intended-decoded.png','input-reference.png'),
        ('saved_vs_intended','lifecycle-saved.png','intended-decoded.png'),
        ('saved_vs_historical_fixture_reference','lifecycle-saved.png','lifecycle-expected-save.png')]:
        metric=compare(decoded[a],decoded[b]);observed=row.get(key,{})
        require(type(observed.get('allowed_max_channel_delta')) is int and observed['allowed_max_channel_delta']==2
            and type(observed.get('max_channel_delta')) is int and observed['max_channel_delta']==metric['maximum_channel_difference']
            and type(observed.get('changed_pixels')) is int and observed['changed_pixels']==metric['different_pixels'],
            'PNG replay metric contradiction '+key)
    return {'schema':'Celluloid.OwnedPhotosBoundaryReplay.1','acceptance':False,
        'historical_gate_passed':row['saved_vs_historical_fixture_reference']['max_channel_delta']<=2,
        'input_boundary_raw_equal':capture['input.bytes']==old_images['lifecycle-source.png'],
        'intended_vs_actual_input_reference':row['intended_vs_input_reference']['max_channel_delta'],
        'saved_vs_intended':row['saved_vs_intended']['max_channel_delta'],
        'boundary_bytes':sum(map(len,joined.values())), 'writer_or_photos_acceptance_from_capture':False}
