#!/usr/bin/env python3
"""Admit independent diagnostics after fully witnessed, pixel-only red consumers.

This never grants renderer/Photos/archive acceptance and never changes an oracle.
"""
from collections import Counter
from datetime import datetime
from pathlib import Path
import argparse, hashlib, json, math, os, plistlib, re, subprocess, sys, uuid
from native_fixture_handoff import load_layer_exact, layer_from_log, LAYER_FILE, LAYER_COMPONENTS
from native_process import run
from run_early_uikit_interop import (ROOT, PROFILES, FROZEN_UIKIT_SHA,
    FROZEN_UIKIT_FINGERPRINT, frozen_uikit_fingerprint)
from verify_required_interoperability import CONSUMER, PIXELS, verify as verify_required

TEST_SOURCE='CelluloidTests/MacPhotosManufacturedAdjustmentTests.swift'
TEST_SOURCE_SHA='54357d35157e7b792c04cda3e3cb3d778419a9dedf279210b66540cf243ed4c8'
OWNER,METHOD=CONSUMER.split('.')
CASE=re.compile(r"^Test Case '-\[([\w.]+) (test\w+)\]' (started|passed|failed|skipped)\b",re.M)
COMPONENT=re.compile(r'^MAC_LAYER_UIKIT_COMPOSITOR_COMPONENT name=([\w-]+) nativeSHA256=([0-9a-f]{64}) maximumChannelDifference=(\d+)$',re.M)
FULL_MESSAGE='Original UIKit compositor is independent of the new Mac renderer; geometry/text differences must be fixed, not hidden by archive roundtrips'
FAILURE=re.compile(r'^XCTAssertLessThanOrEqual failed: \("(\d+)"\) is greater than \("2"\) - (.+)$')
ERROR=re.compile(r'^.+/CelluloidTests/MacPhotosManufacturedAdjustmentTests\.swift:\d+: error: -\[CelluloidTests\.'+OWNER+' '+METHOD+r'\] : (.+)$')
SUSPECT=re.compile(r'XCTAssert|XCTFail|\bassert(?:ion)?(?:Failure|Failed|Error)?\b|assert failed|\b(?:error|errors|failed|failure|failures|failing)\b|fatal|timed?\s*out|timeout|permission|authorization|denied|unauthorized|crash|SIG(?:ABRT|SEGV|BUS|ILL|KILL)|EXC_BAD_ACCESS|termination reason|failed to|lost connection|FAIL_CLOSED|interruption|abort|exception',re.I)
# These two observed CoreAnalytics delivery warnings are not test/process errors.
ANALYTICS=re.compile(r'^\d{4}-\d\d-\d\d .+ Celluloid\[\d+:\d+\] \[General\] Failed to send CA Event for app launch measurements for ca_event_type: (?:0 event_name: com\.apple\.app_launch_measurement\.FirstFramePresentationMetric|1 event_name: com\.apple\.app_launch_measurement\.ExtendedLaunchMetrics)$')
UNCLASSIFIED_FOPEN=re.compile(r'^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+[+-]\d{4} Celluloid\[\d+:\d+\] fopen failed for data file: errno = 2 \(No such file or directory\)$')
STRICT_ERROR='Early UIKit strict pixel/scale consumer failed; full matrix withheld, not accepted'

def require(value,message):
    if not value:raise ValueError(message)

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def unique(pairs):
    result={}
    for key,value in pairs:
        require(key not in result,'Duplicate JSON key: '+key);result[key]=value
    return result

def read(path,limit=2_000_000):
    path=Path(path);require(path.is_file() and not path.is_symlink() and 0<path.stat().st_size<=limit,'Missing/oversized proof: '+path.name)
    return json.loads(path.read_text(),object_pairs_hook=unique)

def failure_key(text):
    match=FAILURE.fullmatch(text);require(match is not None,'Unrecognized XCTest failure: '+text)
    value,message=match.groups();name='full' if message==FULL_MESSAGE else message.removeprefix('Independent UIKit component: ')
    require(name in {'full','bubble-artwork','all-artwork'} and int(value)>2 and int(value)<=255,'Non-historical pixel assertion')
    require(message==FULL_MESSAGE or message=='Independent UIKit component: '+name,'Unexpected assertion message')
    return name,int(value)

def inspect_profile(row,log,summary,timing,fixture):
    profile,name,scale=next((p,n,s) for p,n,s in PROFILES if p==row['profile'])
    require(row['device_type']==name and row['expected_scale']==scale,'Wrong intended device')
    uuid.UUID(row['udid']);require(row['runtime']=='com.apple.CoreSimulator.SimRuntime.iOS-27-0','Wrong intended runtime')
    require(all(type(c.get('exit_code')) is int for c in row['cleanup']),'Invalid cleanup status type')
    require(row['cleanup']==[{'action':'shutdown','exit_code':0},{'action':'delete','exit_code':0}] and row['cleanup_passed'] is True,'Unverified cleanup')
    require(row.get('error') in (None,STRICT_ERROR),'Unexpected setup/process failure')
    case_lines=[line for line in log.splitlines() if line.lstrip().lower().startswith('test case ')]
    for line in case_lines:
        require(re.fullmatch(r"Test Case '-\[[\w.]+ test\w+\]' (?:started\.|(?:passed|failed|skipped) \([0-9]+(?:\.[0-9]+)? seconds\)\.)",line) is not None,'Malformed testcase execution record')
    cases=CASE.findall(log);expected='CelluloidTests.'+OWNER
    require(len(case_lines)==len(cases),'Malformed/duplicate testcase execution record')
    require(cases in [[(expected,METHOD,'started'),(expected,METHOD,'failed')],[(expected,METHOD,'started'),(expected,METHOD,'passed')]],'Wrong/skipped/duplicate consumer execution')
    case_positions=list(CASE.finditer(log));begin,end=case_positions[0].end(),case_positions[1].start()
    require(all(begin<m.start()<end for m in re.finditer(r'^MAC_LAYER_UIKIT_COMPOSITOR',log,re.M)),'Consumer markers outside actual execution')
    require(all(line==line.strip() for line in log.splitlines() if line.lstrip().startswith('MAC_LAYER_UIKIT_COMPOSITOR')),'Malformed whitespace in consumer proof record')
    display_records=[line for line in log.splitlines() if line.startswith('MAC_LAYER_UIKIT_COMPOSITOR_DISPLAY')]
    require(len(display_records)==1 and re.fullmatch(r'MAC_LAYER_UIKIT_COMPOSITOR_DISPLAY scale=[0-9]+(?:\.[0-9]+)?',display_records[0]) is not None,'Malformed/duplicate display proof')
    scales=re.findall(r'^MAC_LAYER_UIKIT_COMPOSITOR_DISPLAY scale=([0-9.]+)$',log,re.M)
    require(len(scales)==1 and float(scales[0])==scale and row['actual_scales']==scales and row['actual_scale_verified'] is True,'Actual display binding failed')
    full_records=[line for line in log.splitlines() if line.startswith('MAC_LAYER_UIKIT_COMPOSITOR ')]
    require(len(full_records)==1 and PIXELS.fullmatch(full_records[0]) is not None,'Malformed/duplicate full oracle')
    full=PIXELS.findall(log);require(len(full)==1,'Missing/duplicate full oracle')
    require(full[0][:3]==tuple(fixture[k] for k in ['sha256','sourceSHA256','renderedSHA256']),'Wrong full fixture hash')
    require(0<=int(full[0][3])<=255,'Invalid full delta')
    component_records=[line for line in log.splitlines() if line.startswith('MAC_LAYER_UIKIT_COMPOSITOR_COMPONENT')]
    require(len(component_records)==4 and all(COMPONENT.fullmatch(line) for line in component_records),'Malformed/duplicate component proof')
    known_prefixes=('MAC_LAYER_UIKIT_COMPOSITOR ', 'MAC_LAYER_UIKIT_COMPOSITOR_DISPLAY ', 'MAC_LAYER_UIKIT_COMPOSITOR_COMPONENT ', 'MAC_LAYER_UIKIT_COMPOSITOR_DIAGNOSTIC ', 'MAC_LAYER_UIKIT_COMPOSITOR_UIKIT_LAYOUT ', 'MAC_LAYER_UIKIT_COMPOSITOR_TEXT_CONTRIBUTION ')
    require(all(line.startswith(known_prefixes) for line in log.splitlines() if line.startswith('MAC_LAYER_UIKIT_COMPOSITOR')),'Unknown/malformed consumer proof record')
    components=COMPONENT.findall(log);require(len(components)==4 and {r[0] for r in components}==LAYER_COMPONENTS,'Missing/duplicate component consumers')
    expected_hash={r['name']:r['sha256'] for r in fixture['components']}
    deltas={'full':int(full[0][3])}
    for component,digest,delta in components:
        require(digest==expected_hash[component] and 0<=int(delta)<=255,'Wrong component fixture binding');deltas[component]=int(delta)
    require(deltas['filtered-base']==deltas['sticker-artwork']==0,'Previously exact base/sticker changed')
    wanted=Counter((k,v) for k,v in deltas.items() if v>2)
    # One canonical parser owns every suite line, including whitespace variants.
    suites={};suite_positions=[];failure_headers=[]
    suite_pattern=re.compile(r"Test Suite '(Selected tests|CelluloidTests.xctest|MacPhotosManufacturedAdjustmentTests)' (started|passed|failed) at [0-9-]+ [0-9:.]+\.")
    for raw in re.finditer(r'^.*$',log,re.M):
        canonical=raw[0].strip()
        if canonical.lower().startswith('test suite '):
            match=suite_pattern.fullmatch(canonical);require(match is not None,'Unknown/malformed suite execution record')
            suites.setdefault(match[1],[]).append(match[2]);suite_positions.append((match[2],raw.start()))
        if canonical.lower().startswith('failing tests:'):
            require(canonical=='Failing tests:','Malformed failing-tests header');failure_headers.append(raw)
    errors=[];unclassified=[]
    for line in log.splitlines():
        if UNCLASSIFIED_FOPEN.fullmatch(line):
            # Console diagnostic alone is not an authoritative XCTest/process
            # failure. Preserve it without asserting origin or harmlessness.
            require(len(unclassified)<16,'Unexpected unclassified diagnostic volume')
            unclassified.append(line)
        elif 'error:' in line:
            match=ERROR.fullmatch(line);require(match is not None,'Unexpected raw test/compiler error');errors.append(failure_key(match[1]))
        elif SUSPECT.search(line):
            stripped=line.strip()
            suite=suite_pattern.fullmatch(stripped)
            total=re.fullmatch(r'Executed \d+ test(?:s)?, with \d+ failure(?:s)? \(\d+ unexpected\)(?: in [0-9.]+ \([0-9.]+\) seconds)?',stripped)
            if suite:pass
            elif line in case_lines or total or stripped=='Failing tests:' or stripped.startswith('** TEST EXECUTE'):pass
            else:require(ANALYTICS.fullmatch(line) is not None,'Unclassified process/permission/assertion diagnostic: '+line)
    require(Counter(errors)==wanted,'Raw failure list does not exactly explain pixel deltas')
    failed=bool(wanted);status='failed' if failed else 'passed';exit_code=65 if failed else 0
    require(all(events==['started',status] for events in suites.values()),'Duplicate/incomplete/contradictory suite outcome')
    require(cases[-1][2]==status and type(row['test_exit_code']) is int and row['test_exit_code']==exit_code,'Exit/test outcome inconsistent')
    require(row['pixel_passed'] is (not failed) and row['passed'] is (not failed),'Pixel diagnostic flags inconsistent')
    require((row.get('error')==STRICT_ERROR) is failed,'Unexpected absent/present primary error')
    totals=re.findall(r'Executed (\d+) test(?:s)?, with (\d+) failure(?:s)? \((\d+) unexpected\)',log)
    require(totals and all(r==('1',str(len(errors)),'0') for r in totals),'Unexplained XCTest failure counts')
    terminals=list(re.finditer(r'^[ \t]*\*\* TEST EXECUTE\b.*$',log,re.M|re.I))
    expected_terminal='** TEST EXECUTE '+('FAILED' if failed else 'SUCCEEDED')+' **'
    require(len(terminals)==1 and terminals[0][0]==expected_terminal and terminals[0].start()>case_positions[-1].end(),'Missing/duplicate/contradictory or premature terminal outcome')
    total_positions=list(re.finditer(r'Executed \d+ test(?:s)?, with \d+ failure(?:s)? \(\d+ unexpected\)',log))
    require(all(case_positions[-1].end()<m.start()<terminals[0].start() for m in total_positions),'Execution totals outside finalized case/terminal interval')
    require(all((position<case_positions[0].start() if state=='started' else case_positions[-1].end()<position<terminals[0].start()) for state,position in suite_positions),'Suite event outside actual execution interval')
    require(len(failure_headers)==int(failed),'Missing/duplicate/contradictory failing-tests block')
    if failed:
        header=failure_headers[0]
        require(case_positions[-1].end()<header.start()<terminals[0].start(),'Failing-tests block outside completed execution/terminal interval')
        entries=[line.strip() for line in log[header.end():terminals[0].start()].splitlines() if line.strip()]
        require(entries==[CONSUMER+'()']*len(errors),'Unknown/duplicate/unaccounted failing-tests entries')
    require(timing['command']=='xcodebuild' and timing['timed_out'] is False and type(timing['return_code']) is int and timing['return_code']==exit_code,'Process timeout/exit mismatch')
    elapsed=timing['elapsed_seconds'];timeout=timing['timeout_seconds']
    require(type(elapsed) in (int,float) and type(timeout) in (int,float) and math.isfinite(elapsed) and math.isfinite(timeout),'Nonfinite/boolean process timing')
    require(0<timeout<=300 and 0<elapsed<=timeout+2,'Process interval exceeds actual300-second command bound')
    dates=[datetime.fromisoformat(timing[k]) for k in ['started','finished']]
    require(all(d.tzinfo is not None and d.utcoffset() is not None for d in dates),'Naive process timestamps')
    start,finish=[d.timestamp() for d in dates]
    require(finish>start and abs((finish-start)-elapsed)<=1.0,'Wall/monotonic process duration contradiction')
    counts={'totalTestCount':1,'passedTests':int(not failed),'failedTests':int(failed),'skippedTests':0,'expectedFailures':0}
    require(summary['result']==('Failed' if failed else 'Passed'),'Finalized outcome mismatch')
    for key,value in counts.items():require(type(summary[key]) is int and summary[key]==value,'Finalized count '+key)
    require(start<=summary['startTime']<summary['finishTime']<=finish,'Unfinalized/out-of-process XCTest result')
    require(not summary.get('runtimeWarnings'),'Unexpected runtime warnings')
    configurations=summary['devicesAndConfigurations'];require(len(configurations)==1,'Wrong/duplicate result device')
    conf=configurations[0]
    for key in ['passedTests','failedTests','skippedTests','expectedFailures']:require(type(conf[key]) is int and conf[key]==counts[key],'Device count mismatch')
    dev=conf['device'];require((dev['platform'],dev['osVersion'],dev['deviceId'],dev['modelName'],dev['deviceName'])==('iOS Simulator','27.0',row['udid'],name,'Celluloid Early UIKit '+profile),'Actual result device binding failed')
    failures=summary['testFailures'];require(bool(failures)==failed,'Finalized failure details missing/contradictory')
    seen=set()
    for item in failures:
        require(item['targetName']=='CelluloidTests' and item['testIdentifierString']==OWNER+'/'+METHOD+'()' and item['testName']==METHOD+'()','Unknown finalized failure owner')
        key=failure_key(item['failureText']);require(key in wanted and key not in seen,'Unknown/duplicate finalized failure');seen.add(key)
    return {'profile':profile,'device_id':row['udid'],'scale':scale,'strict_pixel_passed':not failed,'deltas':deltas,'known_pixel_failures':errors,'unclassified_console_diagnostics':unclassified,'unclassified_console_count':len(unclassified),'console_diagnostics_classified':False,'process_start':start,'process_finish':finish}

def verify(temp,source):
    temp=Path(temp);require(re.fullmatch(r'[0-9a-f]{40}',source),'Invalid source')
    require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==source,'Wrong checkout source')
    require(not subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=ROOT,text=True).strip(),'Dirty source checkout')
    require(frozen_uikit_fingerprint()==FROZEN_UIKIT_FINGERPRINT and sha(ROOT/TEST_SOURCE)==TEST_SOURCE_SHA,'Original UIKit/consumer source changed')
    packet=read(temp/'early-uikit-interop.json');require(packet['source_sha']==source and 'setup_error' not in packet,'Wrong source or setup error')
    require(packet['frozen_uikit_source']==FROZEN_UIKIT_SHA and packet['uikit_production_fingerprint']==FROZEN_UIKIT_FINGERPRINT,'Frozen UIKit identity mismatch')
    require(packet['same_built_app_verified'] is True and packet['cleanup_passed'] is True,'Binary/cleanup guard failed')
    rows=packet['profiles'];require([r['profile'] for r in rows]==['2x','3x'],'Both actual displays required')
    require(len({r['udid'] for r in rows})==2,'Same device reused as another display')
    directory=temp/'early-uikit-fixtures';payload=load_layer_exact(directory,source);fixture=payload['fixture']
    require((directory/LAYER_FILE).read_bytes()==layer_from_log(temp/'mac.log',source),'Fixture differs from actual native producer')
    producer=verify_required('mac',temp/'mac.log',None,source);require(all(producer['checks'].values()),'Native producer cases incomplete')
    app=(temp/'celluloid-early-uikit/Build/Products/Debug-iphonesimulator/Celluloid.app').resolve()
    info=plistlib.loads((app/'Info.plist').read_bytes());require((info['CFBundleIdentifier'],info['CFBundleExecutable'],info['DTPlatformName'])==('Mango.Celluloid','Celluloid','iphonesimulator'),'Built product identity')
    digest=sha(app/'Celluloid');owned_digest=hashlib.sha256(json.dumps(fixture).encode()).hexdigest();result=[]
    for row in rows:
        profile=row['profile'];staging=read(temp/('early-uikit-'+profile+'-staging.json'))
        require(staging==row['staging'],'Staging/report contradiction')
        require(staging['source_sha']==source and Path(staging['built_app']).resolve()==app and staging['binary_sha256']==digest,'Exact built/installed binary binding')
        installed=Path(staging['installed_app']);require(installed.is_absolute() and tuple(installed.parts[-4:-2])==('Bundle','Application') and installed.name=='Celluloid.app','Unexpected installed app path')
        require('/Devices/'+row['udid']+'/data/Containers/Bundle/Application/' in str(installed),'Installed app belongs to another device')
        require(staging['layer_archive_sha256']==fixture['sha256'] and staging['owned_fixture_sha256']==owned_digest,'Owned fixture bytes mismatch')
        logpath=temp/('early-uikit-'+profile+'-interop.log');log=logpath.read_text()
        require(json.loads(json.dumps(verify_required('uikit',logpath,directory,source)))==row['consumer'],'Raw consumer receipt mismatch')
        timing=read(temp/(logpath.name+'.timing.json'))
        bundle=temp/('CelluloidEarlyUIKit'+profile+'.xcresult')
        exported=run(['xcrun','xcresulttool','get','test-results','summary','--path',bundle],timeout=30,echo=False)
        summary=json.loads(exported.stdout,object_pairs_hook=unique);summarypath=temp/(bundle.name+'.summary.json');summarypath.write_text(json.dumps(summary,indent=2)+'\n')
        proof=inspect_profile(row,log,summary,timing,fixture);proof.update(log_sha256=sha(logpath),summary_sha256=sha(summarypath),staging_sha256=sha(temp/('early-uikit-'+profile+'-staging.json')));result.append(proof)
    require(result[0]['process_finish']<result[1]['process_start'],'Concurrent/contradictory consumer processes')
    devices=json.loads(run(['xcrun','simctl','list','devices','-j'],timeout=30,echo=False).stdout)['devices']
    remaining={d['udid'] for entries in devices.values() for d in entries}
    require(not remaining.intersection(r['udid'] for r in rows),'Owned simulator remains after cleanup')
    strict=all(r['strict_pixel_passed'] for r in result);require(packet['pixel_passed'] is strict and packet['passed'] is strict,'Aggregate strict result mismatch')
    return {'source_sha':source,'continuation_safe':True,'strict_pixel_passed':strict,'final_archive_accepted':False,'binary_sha256':digest,'fixture_sha256':sha(directory/LAYER_FILE),'uikit_fingerprint':FROZEN_UIKIT_FINGERPRINT,'consumer_source_sha256':TEST_SOURCE_SHA,'profiles':result,'scope':'Independent functional coverage only. Historical pixel failures remain red; renderer and final archive remain unqualified.'}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--github-output',type=Path,required=True);args=parser.parse_args()
    try:report=verify(Path(os.environ['RUNNER_TEMP']),os.environ['GITHUB_SHA'])
    except Exception as error:report={'source_sha':os.environ.get('GITHUB_SHA'),'continuation_safe':False,'final_archive_accepted':False,'error':type(error).__name__+': '+str(error)}
    (Path(os.environ['RUNNER_TEMP'])/'interop-continuation.json').write_text(json.dumps(report,indent=2)+'\n')
    print('INTEROP_CONTINUATION '+json.dumps(report,sort_keys=True))
    with args.github_output.open('a') as output:output.write('continuation_safe='+str(report['continuation_safe']).lower()+'\n')
    if not report['continuation_safe']:raise SystemExit('Unexplained or incomplete early consumer evidence; independent runtime continuation blocked')

if __name__=='__main__':main()
