#!/usr/bin/env python3
"""Fixed same-run Mac fixture handoff and one original UIKit row's product proof."""
from pathlib import Path
import argparse,hashlib,json,os,re,stat,subprocess,sys,uuid,zlib,shutil,tempfile
from mac_host_transport import load_json
from native_fixture_handoff import load_layer_exact,load_exact
from platform_rendering_contract import validate_native,validate_archive_fixture
from validation_route import current_route,UIKIT_FULL,UIKIT_FULL_BASE,ORIGINAL_IOS

ROOT=Path(__file__).resolve().parents[1]
SCHEMA='Celluloid.FullShippingProducer.1'

def need(ok,message):
    if not ok:raise ValueError(message)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def same_json(first,second):return json.dumps(first,sort_keys=True,separators=(',',':'),allow_nan=False)==json.dumps(second,sort_keys=True,separators=(',',':'),allow_nan=False)
def read(path,maximum=2_000_000):
    p=Path(path);need(p.is_file() and not p.is_symlink() and 0<p.stat().st_size<=maximum,'Missing/unbounded proof: '+p.name)
    raw=p.read_bytes();need(len(raw)<=maximum,'Proof grew while reading');return load_json(raw)
def write(path,row):
    p=Path(path);need(not p.exists() and not p.is_symlink(),'Duplicate proof: '+p.name)
    p.write_text(json.dumps(row,indent=2,sort_keys=True)+'\n')
def source_profile():
    route=current_route()
    need(route in [UIKIT_FULL,ORIGINAL_IOS],'Wrong full-shipping route')
    if route==UIKIT_FULL:return 547,UIKIT_FULL_BASE['fingerprint']
    contract=read(ROOT/'Scripts/original-ios-source-contract.json')
    need(contract['schema']=='Celluloid.OriginalIOSProtectedSource.1' and len(contract['files'])==546,'Malformed staged source profile')
    need(hashlib.sha256(json.dumps(contract['files'],separators=(',',':')).encode()).hexdigest()==contract['fingerprint'],'Changed staged source fingerprint')
    return 546,contract['fingerprint']
def identity():
    source_profile()
    source=os.environ['GITHUB_SHA'];run=os.environ['GITHUB_RUN_ID'];attempt=os.environ['GITHUB_RUN_ATTEMPT']
    need(re.fullmatch('[0-9a-f]{40}',source) and re.fullmatch('[1-9][0-9]*',run) and re.fullmatch('[1-9][0-9]*',attempt),'Wrong actual execution identity')
    return {'source_sha':source,'run_id':run,'run_attempt':attempt}
def passed_summary(row):
    keys=['totalTestCount','passedTests','failedTests','skippedTests','expectedFailures']
    need(all(type(row.get(k)) is int and row[k]>=0 for k in keys),'Malformed native summary counts')
    need(row.get('result')=='Passed' and row['totalTestCount']==row['passedTests']>0 and row['failedTests']==row['skippedTests']==row['expectedFailures']==0,'Unpassed enclosing Mac execution')

def source_proof(temp,phase='before'):
    row=read(temp/('combined-source-'+phase+'.json'))
    count,fingerprint=source_profile()
    need(row['source_sha']==identity()['source_sha'] and type(row['file_count']) is int and row['file_count']==count and row['source_fingerprint']==fingerprint,'Unqualified shipping source')
    need(row['validation_route']==current_route() and row['phase']==phase,'Wrong source proof phase')
    if current_route()==ORIGINAL_IOS:
        projection=row.get('original_ios_source')
        need(type(projection) is dict and projection.get('source_equivalence') is True and projection.get('unchanged_protected_files')==543 and projection.get('original_total_invocations')==412,'Missing staged feature/source equivalence')
    return row

def producer(temp):
    from verify_required_interoperability import verify
    source=source_proof(temp);report=verify('mac',temp/'mac.log',None,source['source_sha'],platform_contract=True)
    need(same_json(report,read(temp/'mac-required-tests.json')) and report['expected_count']==42 and all(v is True for v in report['checks'].values()),'Incomplete same-job Mac producer')
    log=(temp/'mac.log').read_text();ends=[load_json(x.split(' ',1)[1]) for x in log.splitlines() if x.startswith('BOUNDED_COMMAND_END ')]
    need(len(ends)==1 and ends[0]['label']=='same-job-Mac-producer' and type(ends[0]['exit_code']) is int and ends[0]['exit_code']==0,'Mac build/test process did not pass')
    from native_process import run
    from consumer_runtime_binding import validate_raw_execution
    raw_summary=run(['xcrun','xcresulttool','get','test-results','summary','--path',temp/'CelluloidMac.xcresult'],timeout=30,echo=False).stdout
    summary=load_json(raw_summary)
    passed_summary(summary)
    # Same XCTest records. Only the documented xcodebuild action terminal differs.
    lines=log.splitlines();terminals=[x for x in lines if x.startswith('** TEST')]
    need(terminals==['** TEST SUCCEEDED **'],'Wrong Mac test action terminal')
    normalized='\n'.join('** TEST EXECUTE SUCCEEDED **' if x=='** TEST SUCCEEDED **' else x for x in lines)+'\n'
    raw_accounting=validate_raw_execution(normalized,summary)
    need(raw_accounting['aggregate_execution_passed'],'Incomplete enclosing Mac XCTest')
    write(temp/'full-shipping-mac-summary.json',summary)
    write(temp/'full-shipping-mac-accounting.json',{'raw_log_sha256':sha(temp/'mac.log'),'terminal_normalization':'test success to test-without-building success only','accounting':raw_accounting})
    toolchain=(temp/'full-shipping-xcode.txt').read_text()
    need(toolchain.startswith('Xcode 27.0\n'),'Wrong producer Xcode')
    write(temp/'full-shipping-producer.json',{'schema':SCHEMA,**identity(),'tree':source['tree'],'protected_fingerprint':source_profile()[1],
        'mac_summary_sha256':sha(temp/'full-shipping-mac-summary.json'),'mac_accounting_sha256':sha(temp/'full-shipping-mac-accounting.json'),
        'xcode_sha256':sha(temp/'full-shipping-xcode.txt'),'native_required_sha256':sha(temp/'mac-required-tests.json'),'required_mac_cases':42,
        'scope':'Fresh fixture producer only; no Mac Photos host or whole-platform acceptance'})

def transfer(temp,artifact_id,manifest_hash,reported_artifact_digest):
    folder=temp/'mac-fixture-evidence';manifest=read(folder/'manifest.json');ident=identity()
    need(re.fullmatch('[1-9][0-9]*',artifact_id) and re.fullmatch('[0-9a-f]{64}',manifest_hash) and re.fullmatch('[0-9a-f]{64}',reported_artifact_digest),'Malformed exact artifact identity')
    need(sha(folder/'manifest.json')==manifest_hash and manifest['source_sha']==ident['source_sha'] and str(manifest['run_id'])==ident['run_id'],'Wrong producer artifact/source/run')
    need(manifest['platform']=='mac' and type(manifest['limits']['total_bytes']) is int and manifest['limits']['total_bytes']==2_000_000,'Unexpected producer allocation')
    allowed={'combined-source-before.json','combined-source-after.json','mac-required-tests.json','full-shipping-producer.json','full-shipping-mac-summary.json','full-shipping-mac-accounting.json','mac-filter-fixtures.json','mac-layer-fixture.json','native-text-contract-observation.json','text-observations.json','native-glyph-observation.json','mac.log.tail.txt','mac.log.summary.txt','CelluloidMac.xcresult.summary.json','native-icon-provenance-runtime.json'}
    core={'combined-source-before.json','combined-source-after.json','mac-required-tests.json','full-shipping-producer.json','full-shipping-mac-summary.json','full-shipping-mac-accounting.json','mac-filter-fixtures.json','mac-layer-fixture.json'}
    names=set();total=(folder/'manifest.json').stat().st_size
    for row in manifest['files']:
        name=row['name'];need(type(name) is str and Path(name).name==name and name not in {'','.','..','manifest.json'} and name not in names,'Unsafe/duplicate artifact member')
        need(name in allowed or re.fullmatch(r'CelluloidMac-[0-7]-native-text-production-[A-Za-z0-9_-]{1,100}\.(png|jpg)',name),'Unreviewed producer artifact member')
        names.add(name);path=folder/name
        need(path.is_file() and not path.is_symlink() and type(row['bytes']) is int and 0<row['bytes']<=2_000_000,'Invalid artifact member')
        need(path.stat().st_size==row['bytes'] and sha(path)==row['sha256'],'Changed artifact member')
        total+=row['bytes']
    need(total<=2_000_000 and names=={p.name for p in folder.iterdir()}-{'manifest.json'},'Incomplete/oversized producer artifact')
    need(core<=names,'Missing core producer artifact members')
    producer_row=read(folder/'full-shipping-producer.json');source=source_proof(temp)
    need(producer_row['schema']==SCHEMA and all(producer_row[k]==v for k,v in ident.items()),'Producer source/run/attempt differs')
    need(producer_row['tree']==source['tree'] and producer_row['protected_fingerprint']==source_profile()[1],'Producer source tree differs')
    need(producer_row['xcode_sha256']==sha(temp/'full-shipping-xcode.txt'),'Producer/consumer toolchains differ')
    required=read(folder/'mac-required-tests.json')
    need(producer_row['native_required_sha256']==sha(folder/'mac-required-tests.json') and required['source_sha']==ident['source_sha'] and type(required['expected_count']) is int and type(producer_row['required_mac_cases']) is int and required['expected_count']==producer_row['required_mac_cases']==42,'Unbound native producer proof')
    from verify_required_interoperability import required as expected_cases
    expected={module+'/'+case:['passed'] for module,cases in expected_cases('mac').items() for case in cases}
    need(required['results']==expected and required['checks']=={'every_required_case_executed_once_and_passed':True,'independent_native_text_contract':True}
        and all(v is True for v in required['checks'].values()) and required['scope']=='mac' and required['missing_failed_skipped_or_duplicate']=={} and required['manufactured_layer_fixture_count']==1 and required['baked_fallback_fixture_count']==1,'Missing/failed native prerequisite')
    summary=read(folder/'full-shipping-mac-summary.json');accounting=read(folder/'full-shipping-mac-accounting.json')
    need(producer_row['mac_summary_sha256']==sha(folder/'full-shipping-mac-summary.json') and producer_row['mac_accounting_sha256']==sha(folder/'full-shipping-mac-accounting.json'),'Changed enclosing native proof')
    passed_summary(summary)
    need(accounting['accounting']['aggregate_execution_passed'] is True,'Unpassed enclosing Mac result')
    layer=load_layer_exact(folder,ident['source_sha']);filters=load_exact(folder,ident['source_sha'])
    need(required['filter_fixture_count']==len(filters['fixtures']),'Unbound native filter fixture count')
    need(validate_native(required['native_text_contract'],layer['fixture'])==required['native_text_contract'],'Changed native oracle')
    need(validate_archive_fixture(layer['fixture'])==required['archive_graph_proof'],'Changed archive graph')
    write(temp/'full-shipping-transfer.json',{'schema':'Celluloid.FullShippingTransfer.1',**ident,'tree':source['tree'],'artifact_id':artifact_id,
        'artifact_manifest_sha256':manifest_hash,'reported_upload_artifact_digest':reported_artifact_digest,'manifest_and_all_members_verified':True,
        'layer_archive_sha256':layer['fixture']['sha256'],'producer_receipt_sha256':sha(folder/'full-shipping-producer.json'),
        'queue_expiry_applied':False})

def product_after(temp):
    from uikit_installed_identity import readback
    from uikit_full_shipping_gate import admit_phase,check_completion
    from native_process import run
    row=os.environ['CELLULOID_FULL_ROW'];clock=read(temp/'full-shipping-clock.json')
    staging=read(temp/'uikit-layer-staging.json');udid=Path('/tmp/current-celluloid-simulator').read_text().strip();uuid.UUID(udid)
    device=read(temp/'full-shipping-device.json');transfer_row=read(temp/'full-shipping-transfer.json');ident=identity()
    need(device.get('schema')=='Celluloid.FullShippingDevice.1' and transfer_row.get('schema')=='Celluloid.FullShippingTransfer.1','Wrong device/transfer schema')
    need(staging['source_sha']==ident['source_sha'] and all(device[k]==transfer_row[k]==v for k,v in ident.items()),'Changed prepared/staged source/run/attempt')
    need(device['row']==row and device['device']['id']==udid and device['device']['model']==os.environ['DEVICE_NAME'],'Changed owned device')
    need(staging['layer_archive_sha256']==transfer_row['layer_archive_sha256'],'Staged archive differs from fresh producer')
    built=ROOT/'.build/Build/Products/Debug-iphonesimulator/Celluloid.app/Celluloid'
    need(built.is_file() and not built.is_symlink() and 0<built.stat().st_size<=200_000_000 and sha(built)==staging['binary_sha256'],'Built shipping app changed')
    context={**identity(),'row':row}
    def bounded(args,timeout=60,**kwargs):
        need(admit_phase(clock,context,'product-readbacks')>=timeout+15,'Owned product lookup and cleanup allowance do not fit; no dispatch')
        result=run(args,timeout=timeout,**kwargs)
        check_completion(clock,context,'product-readbacks')
        return result
    actual=readback(bounded,udid,staging)
    check_completion(clock,context,'product-readbacks')
    write(temp/'full-shipping-product-after.json',{'schema':'Celluloid.FullShippingProduct.1',**identity(),'row':row,'staging_sha256':sha(temp/'uikit-layer-staging.json'),'actual':actual})

def accept_row(temp, *, row=None, recorded_observation=None):
    from uikit_full_shipping_gate import verify_manifest,clock_status,ROW_COUNTS
    from uikit_installed_identity import validate as validate_installation
    from verify_required_interoperability import verify
    ident=identity();row=os.environ['CELLULOID_FULL_ROW'] if row is None else row;context={**ident,'row':row}
    clock=read(temp/'full-shipping-clock.json');manifest=read(temp/'full-shipping-execution.json')
    observed=read(temp/'full-shipping-accounting.json')
    # Fixed archive replay uses the recorded execution interval; live row callers
    # always retain the actual current monotonic/wall clock defaults.
    observation={} if recorded_observation is None else recorded_observation
    need(not observation or current_route()==ORIGINAL_IOS,'Historical replay is confined to staged package qualification')
    need(not observation or set(observation)=={'now_monotonic','now_unix'},'Malformed recorded observation')
    replayed=verify_manifest(manifest,temp,context,clock,**observation)
    need(same_json({k:v for k,v in observed.items() if k!='clock'},{k:v for k,v in replayed.items() if k!='clock'}),'Changed full-row execution accounting')
    prior=observed['clock'];current=replayed['clock']
    need(prior==clock_status(clock,context,clock['started_monotonic']+prior['elapsed_seconds'],clock['started_unix']+prior['wall_elapsed_seconds'])
        and 0<=prior['elapsed_seconds']<=current['elapsed_seconds'] and 0<=prior['wall_elapsed_seconds']<=current['wall_elapsed_seconds'],'Changed/future accounting clock')
    stages=read(temp/'full-shipping-stage-outcomes.json')
    required_stages={'source_before','environment','reproducible','transfer','device_selection','prepare','stage_fixture','units','consumer_contract','bootstrap','photos_integration','ui','screens','product_after','shutdown','delete','source_after'}
    if row=='compact-phone':required_stages.update({'release_build','permissions','dark','preservation'})
    if row=='large-phone':required_stages.add('preflight')
    if row=='large-ipad':required_stages.add('dark')
    for name in required_stages:
        need(type(stages.get(name)) is dict and stages[name].get('outcome')=='success' and stages[name].get('conclusion')=='success','Unpassed original workflow stage: '+name)
    if 'diagnostics' in stages:need(stages['diagnostics'].get('outcome') in {'success','skipped'},'Failed original diagnostics stage')
    before=source_proof(temp);after=source_proof(temp,'after')
    need(before['tree']==after['tree'],'Source tree changed during row')
    transfer_row=read(temp/'full-shipping-transfer.json');product=read(temp/'full-shipping-product-after.json');device=read(temp/'full-shipping-device.json');cleanup=read(temp/'full-shipping-cleanup.json')
    need(transfer_row['schema']=='Celluloid.FullShippingTransfer.1' and transfer_row['queue_expiry_applied'] is False and product['schema']=='Celluloid.FullShippingProduct.1','Wrong producer/product receipt schema')
    need(set(device)=={'schema',*ident,'row','device'} and device['schema']=='Celluloid.FullShippingDevice.1','Wrong prepared-device schema')
    for item in [transfer_row,product,device,cleanup]:need(all(item[k]==v and type(item[k]) is str for k,v in ident.items()),'Wrong row prerequisite identity')
    need(product['row']==device['row']==cleanup['row']==row and device['device']==manifest['device'],'Wrong prepared product/device row')
    need(transfer_row['tree']==before['tree'] and transfer_row['manifest_and_all_members_verified'] is True,'Unverified current producer handoff')
    need(set(cleanup)=={*ident,'row','device_id','actions'} and cleanup['device_id']==device['device']['id'],'Wrong cleanup owner')
    actions=cleanup['actions'];need(type(actions) is list and len(actions)==2,'Incomplete cleanup')
    for action,name in zip(actions,['shutdown','delete']):
        need(type(action) is dict and set(action)=={'action','exit_code'} and action['action']==name and type(action['exit_code']) is int and action['exit_code']==0,'Failed/unconfirmed owned cleanup')
    staging=read(temp/'uikit-layer-staging.json')
    need(staging['source_sha']==ident['source_sha'] and staging['layer_archive_sha256']==transfer_row['layer_archive_sha256'] and product['staging_sha256']==sha(temp/'uikit-layer-staging.json'),'Changed actual staging/product binding')
    validate_installation(product['actual'],device['device']['id'],staging)
    consumer=read(temp/'uikit-required-tests.json');summary=read(temp/'units.summary.json')
    actual=verify('uikit',temp/'units.log',temp/'mac-fixture-evidence',ident['source_sha'],platform_contract=True,runtime_summary=summary,expected_device=device['device'])
    need(same_json(consumer,actual) and actual['aggregate_execution_passed'] is True and all(v is True for v in actual['checks'].values()),'Original shipping UIKit consumer/source/product proof differs')
    outer=temp/'bootstrap.log'
    need(outer.is_file() and not outer.is_symlink() and 0<outer.stat().st_size<=30_000_000,'Missing/unbounded bootstrap driver log')
    names=['bootstrap.log','full-shipping-stage-outcomes.json','full-shipping-execution.json','full-shipping-accounting.json','full-shipping-clock.json','full-shipping-device.json','full-shipping-transfer.json','full-shipping-product-after.json','full-shipping-cleanup.json','uikit-layer-staging.json','uikit-required-tests.json','combined-source-before.json','combined-source-after.json']
    return {'schema':'Celluloid.UIKitFullShippingRow.1',**context,'device':device['device'],'row_checks_passed':True,
        'original_test_invocation_count':ROW_COUNTS[row],'source_tree':before['tree'],'protected_fingerprint':source_profile()[1],
        'proof_sha256':{name:sha(temp/name) for name in names},'workflow_completion_required':True,'release_acceptance':False,
        'scope':'One complete original UIKit row; all four rows and later release gates remain separate'}

LOG_INDEX='full-shipping-logs.json'
RAW_LOG_LIMIT=30_000_000

def phase_log_inventory(row):
    from uikit_full_shipping_gate import expected_phases,phase_files
    return [(phase,phase_files(phase)[0]) for phase in expected_phases(row)]+[('bootstrap-driver','bootstrap.log')]

def pack_phase_logs(temp,retain,available):
    """Lossless fixed test logs only; compression never creates completeness."""
    from uikit_full_shipping_gate import expected_phases,phase_files
    row=os.environ['CELLULOID_FULL_ROW'];index={'schema':'Celluloid.UIKitFullShippingLogs.1',**identity(),'row':row,
        'raw_aggregate_limit':RAW_LOG_LIMIT,'producer_complete':False,'files':[],'omissions':[]}
    status_path=temp/'full-shipping-row.json'
    accepted=status_path.is_file() and read(status_path).get('row_checks_passed') is True
    if accepted:need(same_json(read(status_path),accept_row(temp)),'Unverified complete log producer')
    accounting=read(temp/'full-shipping-accounting.json') if accepted else None
    expected_hashes={r['phase']:r['raw_log_sha256'] for r in accounting['phases']} if accounting else {}
    if accepted:expected_hashes['bootstrap-driver']=read(status_path)['proof_sha256']['bootstrap.log']
    raw_read=0;compressed_used=0;compressed_limit=max(0,available-16_000)
    inventory=phase_log_inventory(row)
    for phase,name in inventory:
        path=temp/name;packed='full-shipping-'+phase+'.log.zlib'
        if not path.exists():index['omissions'].append({'phase':phase,'reason':'producer did not emit log'});continue
        fd=os.open(path,os.O_RDONLY|os.O_NONBLOCK|os.O_CLOEXEC|os.O_NOFOLLOW)
        try:
            before=os.fstat(fd)
            need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and 0<before.st_size<=RAW_LOG_LIMIT-raw_read,'Raw log aggregate admission failed before read')
            remaining=before.st_size;digest=hashlib.sha256();encoder=zlib.compressobj(6);parts=[]
            def append(part):
                nonlocal compressed_used
                need(compressed_used+len(part)<=compressed_limit,'Required full logs exceed remaining artifact cap')
                parts.append(part);compressed_used+=len(part)
            while remaining:
                data=os.read(fd,min(65_536,remaining));need(bool(data),'Truncated raw phase log')
                remaining-=len(data);raw_read+=len(data);digest.update(data);append(encoder.compress(data))
            append(encoder.flush())
            snapshot=lambda a:(a.st_dev,a.st_ino,a.st_mode,a.st_nlink,a.st_size,a.st_mtime_ns,a.st_ctime_ns)
            need(snapshot(before)==snapshot(os.fstat(fd))==snapshot(os.stat(path,follow_symlinks=False)),'Phase log changed during compression')
        finally:os.close(fd)
        raw_hash=digest.hexdigest();data=b''.join(parts)
        if accepted:need(expected_hashes.get(phase)==raw_hash,'Accepted phase log changed')
        need(retain(packed,data,'lossless original UIKit phase log; completeness requires actual execution accounting'),'Required compressed phase log was omitted')
        index['files'].append({'phase':phase,'raw_name':name,'name':packed,'raw_bytes':before.st_size,'raw_sha256':raw_hash,
            'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    index['producer_complete']=accepted and not index['omissions'] and len(index['files'])==len(inventory)
    need(not accepted or index['producer_complete'],'Accepted row lacks complete raw phase logs')
    encoded=(json.dumps(index,sort_keys=True,separators=(',',':'))+'\n').encode()
    need(len(encoded)<=16_000 and retain(LOG_INDEX,encoded,'fixed lossless phase-log index; no acceptance by compression'),'Required log index exceeded cap')
    return index

def unpack_phase_logs(folder,index,context):
    """Reconstruct exact fixed logs with pre-admitted incremental decompression."""
    from uikit_full_shipping_gate import expected_phases,phase_files,validate_context
    validate_context(context)
    need(type(index) is dict and set(index)=={'schema',*context,'raw_aggregate_limit','producer_complete','files','omissions'},'Malformed log index')
    need(index['schema']=='Celluloid.UIKitFullShippingLogs.1' and all(index[k]==v for k,v in context.items()),'Wrong log source/run/attempt/row')
    need(type(index['raw_aggregate_limit']) is int and index['raw_aggregate_limit']==RAW_LOG_LIMIT and type(index['producer_complete']) is bool,'Wrong log limits/completeness')
    inventory=dict(phase_log_inventory(context['row']));phases=list(inventory);rows=index['files'];omissions=index['omissions']
    need(type(rows) is list and len(rows)<=len(phases) and type(omissions) is list and len(omissions)<=len(phases),'Oversized phase-log inventory')
    seen=set();raw_total=0;compressed_total=0
    for r in rows:
        need(type(r) is dict and set(r)=={'phase','raw_name','name','raw_bytes','raw_sha256','bytes','sha256'},'Malformed compressed log member')
        phase=r['phase'];need(phase in phases and phase not in seen,'Unexpected/duplicate log phase');seen.add(phase)
        need(r['raw_name']==inventory[phase] and r['name']=='full-shipping-'+phase+'.log.zlib','Unowned compressed log name')
        for k in ['raw_bytes','bytes']:need(type(r[k]) is int and 0<r[k]<=RAW_LOG_LIMIT,'Invalid log byte count')
        for k in ['raw_sha256','sha256']:need(type(r[k]) is str and re.fullmatch('[0-9a-f]{64}',r[k]),'Invalid log hash')
        raw_total+=r['raw_bytes'];compressed_total+=r['bytes']
    need(raw_total<=RAW_LOG_LIMIT and compressed_total<=1_500_000,'Log aggregate exceeds admission')
    omitted=set()
    for r in omissions:
        need(type(r) is dict and set(r)=={'phase','reason'} and r['phase'] in phases and r['phase'] not in seen|omitted and r['reason']=='producer did not emit log','Malformed log omission');omitted.add(r['phase'])
    need(seen|omitted==set(phases) and (not index['producer_complete'] or not omissions),'Incomplete/contradictory log index')
    result={}
    for r in rows:
        path=Path(folder)/r['name'];need(path.is_file() and not path.is_symlink() and path.stat().st_size==r['bytes'],'Missing/unsafe compressed phase log')
        decoder=zlib.decompressobj();out=bytearray();compressed_hash=hashlib.sha256()
        fd=os.open(path,os.O_RDONLY|os.O_NONBLOCK|os.O_CLOEXEC|os.O_NOFOLLOW)
        with os.fdopen(fd,'rb') as stream:
            before=os.fstat(stream.fileno());need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size==r['bytes'],'Unsafe compressed phase file')
            remaining=r['bytes']
            while remaining:
                chunk=stream.read(min(65_536,remaining));need(bool(chunk),'Truncated compressed phase log');remaining-=len(chunk);compressed_hash.update(chunk)
                pending=chunk
                while True:
                    allowance=min(65_536,r['raw_bytes']-len(out)+1)
                    prior_pending=len(pending)
                    part=decoder.decompress(pending,allowance);out.extend(part)
                    need(len(out)<=r['raw_bytes'] and not decoder.unused_data,'Oversized/trailing compressed phase log')
                    pending=decoder.unconsumed_tail
                    need(not pending or len(pending)<prior_pending or bool(part),'Stalled compressed phase stream')
                    if not pending and len(part)<allowance:break
                    if not pending and decoder.eof:break
            snapshot=lambda a:(a.st_dev,a.st_ino,a.st_mode,a.st_nlink,a.st_size,a.st_mtime_ns,a.st_ctime_ns)
            need(snapshot(before)==snapshot(os.fstat(stream.fileno()))==snapshot(os.stat(path,follow_symlinks=False)),'Compressed phase log changed')
        need(decoder.eof and len(out)==r['raw_bytes'] and compressed_hash.hexdigest()==r['sha256'] and hashlib.sha256(out).hexdigest()==r['raw_sha256'],'Compressed/raw phase log identity failed')
        result[r['raw_name']]=bytes(out)
    return result

def manifest_output(temp):
    manifest=temp/'celluloid-bounded-evidence/manifest.json';read(manifest)
    with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('manifest_sha256='+sha(manifest)+'\n')

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['producer','transfer','product-after','manifest-output','accept-row']);p.add_argument('--artifact-id');p.add_argument('--manifest-sha256');p.add_argument('--reported-artifact-digest');a=p.parse_args();temp=Path(os.environ['RUNNER_TEMP']).resolve();identity()
    if a.action=='producer':producer(temp)
    elif a.action=='transfer':transfer(temp,a.artifact_id or '',a.manifest_sha256 or '',a.reported_artifact_digest or '')
    elif a.action=='product-after':product_after(temp)
    elif a.action=='accept-row':
        try:result=accept_row(temp)
        except Exception as error:
            result={'schema':'Celluloid.UIKitFullShippingRow.1',**identity(),'row':os.environ['CELLULOID_FULL_ROW'],'row_checks_passed':False,'workflow_completion_required':True,'release_acceptance':False,'error':type(error).__name__+': '+str(error)}
        write(temp/'full-shipping-row.json',result)
        print(json.dumps(result,sort_keys=True))
        if result['row_checks_passed'] is not True:raise SystemExit('Full original UIKit row remains incomplete/failed')
    else:manifest_output(temp)
if __name__=='__main__':main()
