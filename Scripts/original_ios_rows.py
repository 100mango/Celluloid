#!/usr/bin/env python3
"""Replay four original UIKit artifacts, including three literal qualified rows before unsigned iOS archive admission.

Only data is reconstructed. A later queue wait does not change the recorded
native execution interval or extend any producing job's clock.
"""
from pathlib import Path
import argparse,hashlib,json,os,shutil,tempfile
import uikit_full_shipping_handoff as handoff
from uikit_full_shipping_gate import ROWS,ROW_COUNTS,clock_status
from validation_route import current_route,ORIGINAL_IOS

MAX_ARTIFACT=1_500_000
MAX_FILES=160

def checked_artifact(folder,context):
    need=handoff.need
    need(folder.is_dir() and not folder.is_symlink(),'Missing fixed row artifact')
    manifest=handoff.read(folder/'manifest.json',100_000)
    need(manifest.get('source_sha')==context['source_sha'] and str(manifest.get('run_id'))==context['run_id'] and manifest.get('platform')==context['row'],'Wrong row artifact source/run/profile')
    limit=manifest.get('limits',{}).get('total_bytes')
    need(type(limit) is int and limit==MAX_ARTIFACT,'Wrong row artifact allocation')
    rows=manifest.get('files');need(type(rows) is list and 0<len(rows)<=MAX_FILES,'Oversized row inventory')
    names=set();total=(folder/'manifest.json').stat().st_size
    for record in rows:
        need(type(record) is dict,'Malformed row member')
        name=record.get('name');count=record.get('bytes');digest=record.get('sha256')
        need(type(name) is str and Path(name).name==name and name not in {'','.','..','manifest.json'} and name not in names,'Unsafe/duplicate row member')
        names.add(name);path=folder/name
        need(type(count) is int and 0<count<=MAX_ARTIFACT-total,'Row artifact admission exceeds cap')
        need(path.is_file() and not path.is_symlink() and path.stat().st_nlink==1 and path.stat().st_size==count,'Unsafe/truncated row member')
        need(handoff.sha(path)==digest,'Changed row artifact bytes');total+=count
    need({p.name for p in folder.iterdir()}==names|{'manifest.json'},'Unlisted row artifact member')
    return manifest

def verify_four(temp, *, fixed_04d18_rows=False):
    need=handoff.need
    need(current_route()==ORIGINAL_IOS,'Wrong staged archive row replay route')
    ident=handoff.identity();source=handoff.source_proof(temp)
    transfer=handoff.read(temp/'full-shipping-transfer.json')
    need(transfer.get('schema')=='Celluloid.FullShippingTransfer.1' and all(transfer.get(k)==v for k,v in ident.items()) and transfer.get('tree')==source['tree'] and transfer.get('manifest_and_all_members_verified') is True,'Missing current exact producer handoff')
    producer=temp/'mac-fixture-evidence'
    result=[];fixed={}
    for row,model in ROWS.items():
        context={**ident,'row':row};folder=temp/'original-ios-rows'/row
        if fixed_04d18_rows and row in {'compact-phone','large-phone','large-ipad'}:
            from original_ios_fixed_rows import verify_fixed_row
            proof=verify_fixed_row(temp,row,folder,temp/'original-ios-fixed-producer')
            actual=proof['original'];artifact=proof['artifact'];fixed[row]=proof
            result.append({'row':row,'original_test_invocation_count':ROW_COUNTS[row],'model':model,'device_id':actual['device']['id'],
                'row_receipt_sha256':handoff.sha(folder/'full-shipping-row.json'),'artifact_manifest_sha256':handoff.sha(folder/'manifest.json'),
                'artifact_name':artifact['name'],'execution_identity':{k:actual[k] for k in ident},'execution_source_tree':actual['source_tree']})
            continue
        checked_artifact(folder,context)
        stored=handoff.read(folder/'full-shipping-row.json')
        need(stored.get('row_checks_passed') is True,'Incomplete original UIKit row')
        index=handoff.read(folder/handoff.LOG_INDEX,16_000)
        need(index.get('producer_complete') is True,'Interrupted/truncated row log producer')
        logs=handoff.unpack_phase_logs(folder,index,context)
        need((folder/'consumer-mac-layer-fixture.json').read_bytes()==(producer/'mac-layer-fixture.json').read_bytes() and (folder/'consumer-mac-layer-manifest.json').read_bytes()==(producer/'manifest.json').read_bytes(),'Row used a different native producer')
        clock=handoff.read(folder/'full-shipping-clock.json');accounting=handoff.read(folder/'full-shipping-accounting.json')
        recorded=accounting['clock']
        # clock_status revalidates exact types, finite values and native budget.
        observation={'now_monotonic':clock['started_monotonic']+recorded['elapsed_seconds'],'now_unix':clock['started_unix']+recorded['wall_elapsed_seconds']}
        need(recorded==clock_status(clock,context,**observation) and recorded['within_execution_clock'] is True,'Invalid original execution interval')
        with tempfile.TemporaryDirectory(prefix='original-ios-row-replay-',dir=temp) as scratch:
            replay=Path(scratch)
            for path in folder.iterdir():shutil.copyfile(path,replay/path.name)
            for name,data in logs.items():
                need(not (replay/name).exists(),'Raw log collides with retained member')
                (replay/name).write_bytes(data)
            shutil.copytree(producer,replay/'mac-fixture-evidence')
            actual=handoff.accept_row(replay,row=row,recorded_observation=observation)
        need(handoff.same_json(stored,actual) and actual['source_tree']==source['tree'] and actual['device']['model']==model and actual['original_test_invocation_count']==ROW_COUNTS[row],'Changed row/native acceptance')
        result.append({'row':row,'original_test_invocation_count':ROW_COUNTS[row],'model':model,'device_id':actual['device']['id'],
            'row_receipt_sha256':handoff.sha(folder/'full-shipping-row.json'),'artifact_manifest_sha256':handoff.sha(folder/'manifest.json'),
            'artifact_name':'celluloid-original-ios-'+row+'-'+ident['source_sha']+'-'+ident['run_attempt']})
        if fixed_04d18_rows:result[-1].update(execution_identity=dict(ident),execution_source_tree=source['tree'])
    need(len({r['device_id'] for r in result})==4,'Reused device identity across independent rows')
    packet={'schema':'Celluloid.OriginalIOSRows.1',**ident,'source_tree':source['tree'],'scope':ORIGINAL_IOS['scope'],
        'all_rows_verified':True,'original_total_invocations':412,'rows':result}
    if fixed_04d18_rows:
        from original_ios_fixed_rows import validate_fixed_summary
        validate_fixed_summary(fixed,ident,source['tree'])
        packet.update(schema='Celluloid.OriginalIOSRows.2',fixed_predecessor_rows=fixed)
    handoff.write(temp/'original-ios-rows.json',packet)
    return packet

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--fixed-04d18-rows',action='store_true');args=parser.parse_args()
    print(json.dumps(verify_four(Path(os.environ['RUNNER_TEMP']).resolve(),fixed_04d18_rows=args.fixed_04d18_rows),sort_keys=True))
