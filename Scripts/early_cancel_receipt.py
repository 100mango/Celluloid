#!/usr/bin/env python3
"""Offline-reviewed candidate CLI. Uses actual identity/files and official export.

Running this receipt parser is not authorization to run a native test. A passed
receipt covers only the early-Cancel method, never changes the old Full result.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import re
import time
import tempfile
from native_action_binder import base,require,validate_early_logs,EvidenceError


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('xcresult','identity','app-binary','output','diagnostics-output'):
        p.add_argument('--'+name,type=Path,required=True)
    for name in ('expected-source-sha','expected-source-tree','expected-run','expected-device-id','expected-ci-run-id','expected-ci-run-attempt','expected-device-model','expected-runtime-version','expected-runtime-build'):
        p.add_argument('--'+name,required=True)
    p.add_argument('--runner-log-timezone',choices=['UTC'],required=True)
    a=p.parse_args(argv);result={'status':'invalid_evidence','budget_seconds':3.0,'release_qualification':False}
    try:
        run=base.identifier(a.expected_run,'expected run')
        identity=json.loads(a.identity.read_text())
        base.verify_identity(identity,a.xcresult,a.app_binary,a.expected_source_sha,a.expected_source_tree,{run:(3,0)})
        for key,expected in [('device_id',a.expected_device_id),('ci_run_id',a.expected_ci_run_id),('ci_run_attempt',a.expected_ci_run_attempt)]:
            require(str(identity.get(key))==expected,'Native device/CI identity mismatch: '+key)
        with tempfile.TemporaryDirectory(prefix='early-cancel-diagnostics-') as temporary:
            destination=Path(temporary)/'diagnostics'
            exported=base.export_diagnostics(a.xcresult,destination)
            logs=base.read_diagnostics(destination)
            base.retain_diagnostics(logs,a.diagnostics_output,exported,identity)
            result=validate_early_logs(logs,run)
            summary=export_summary(a.xcresult)
            summary_binding=verify_summary(summary,logs,result,a.expected_device_id,a.expected_device_model,a.expected_runtime_version,a.expected_runtime_build)
            (a.diagnostics_output/'official-test-summary.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
            result.update(identity=identity,export=exported,
                log_sha256={k:hashlib.sha256(v.encode()).hexdigest() for k,v in logs.items()},
                requires_identity_wrapper=False,identity_verified=True,test_summary_binding=summary_binding,
                historical_full_38681904126_status='failed',native_candidate_result='new evidence only')
        require(base.bundle_digest(a.xcresult)==identity['xcresult_sha256'],'xcresult changed during parsing')
        require(base.sha256_file(a.app_binary)==identity['app_binary_sha256'],'app binary changed during parsing')
    except (EvidenceError,OSError,UnicodeError,json.JSONDecodeError,ValueError) as e:
        result={'status':'invalid_evidence','budget_seconds':3.0,'release_qualification':False,'error':str(e)}
    if a.diagnostics_output.exists():
        result['retained_diagnostics']=str(a.diagnostics_output)
        result['diagnostics_retention_complete']=(a.diagnostics_output/'retained-manifest.json').is_file()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':result['status'],'receipt':str(a.output),'error':result.get('error')}))
    return 0 if result['status']=='passed' else 1

def export_summary(bundle,run_tool=base._run_tool):
    deadline=time.monotonic()+45
    help_text=run_tool(['xcrun','xcresulttool','help','get','test-results','summary'],deadline)
    require('--path' in help_text,'Unsupported official test summary syntax')
    return json.loads(run_tool(['xcrun','xcresulttool','get','test-results','summary','--path',str(bundle)],deadline))


def verify_summary(summary,logs,receipt,device,model,version,build):
    wanted={'totalTestCount':1,'passedTests':1,'failedTests':0,'skippedTests':0,'expectedFailures':0}
    require(isinstance(summary,dict) and summary.get('result')=='Passed','Official XCTest result not Passed')
    for k,v in wanted.items():require(type(summary.get(k)) is int and summary[k]==v,'Official XCTest count mismatch: '+k)
    require(summary.get('testFailures')==[] and summary.get('runtimeWarnings')==[],'Unqualified XCTest failure/runtime warning')
    conf=one_item(summary.get('devicesAndConfigurations'),'actual device configuration');dev=conf.get('device',{})
    require((dev.get('deviceId'),dev.get('modelName'),dev.get('osVersion'),dev.get('osBuildNumber'),dev.get('platform'),dev.get('architecture'))==(device,model,version,build,'iOS Simulator','arm64'),'Actual test device/runtime mismatch')
    for k,v in wanted.items():
        if k!='totalTestCount':require(type(conf.get(k)) is int and conf[k]==v,'Device count mismatch')
    start=base.number(summary.get('startTime'),'official start');end=base.number(summary.get('finishTime'),'official finish')
    require(start<receipt['run_bounds']['start_wall']<receipt['run_bounds']['end_wall']<end,'Run clocks outside actual test summary')
    sessions=[text for path,text in logs.items() if path.split('/')[-1].startswith('Session')]
    text=one_item(sessions,'official test Session')
    cases=[line for line in text.splitlines() if line.startswith('Test Case ')]
    name='-[CelluloidUITests.CelluloidUITests testStockPickerEarlyCancelCompletesWithinOpeningWindow]'
    require(sum(line==f"Test Case '{name}' started." for line in cases)==1,'Missing/retried actual early-Cancel test start')
    endings={line for line in cases if line!=f"Test Case '{name}' started."}
    terminal=one_item(list(endings),'unique actual test terminal (exact duplicate mirrors allowed)')
    require(re.fullmatch(re.escape(f"Test Case '{name}' passed (")+r'[0-9]+(?:\.[0-9]+)? seconds\)\.',terminal),'Unexpected/failed/skipped/extra test terminal')
    return {'test':name,'executed_once':True,'device_id':device,'summary_sha256':hashlib.sha256(json.dumps(summary,sort_keys=True,separators=(',',':')).encode()).hexdigest()}


def one_item(items,name):
    require(isinstance(items,list) and len(items)==1,'Expected exactly one '+name)
    return items[0]

if __name__=='__main__':sys.exit(main())
