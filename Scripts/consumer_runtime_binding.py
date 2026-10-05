"""Bind every UIKit/phone claiming consumer to its actual finalized xcresult device."""
import hashlib,json,math,uuid
from platform_rendering_contract import require,RUNTIME_BUILD
MODEL_SCALES={'iPhone SE (3rd generation)':2,'iPhone 18 Pro Max':3,'iPad mini (A17 Pro)':2,'iPad Pro 13-inch (M5)':2}

def validate(summary,receipt,expected_device):
    require(isinstance(summary,dict) and isinstance(expected_device,dict) and set(expected_device)=={'id','model'},'Missing actual result/device binding')
    uuid.UUID(expected_device['id'])
    require(expected_device['model'] in MODEL_SCALES,'Unqualified actual device model')
    require(receipt['scale']==MODEL_SCALES[expected_device['model']] and receipt['profile']==str(MODEL_SCALES[expected_device['model']])+'x','Model/display profile contradiction')
    require(summary.get('result') in {'Passed','Failed'},'Enclosing XCTest execution is unfinalized/unknown')
    for name in ['totalTestCount','passedTests','failedTests','skippedTests','expectedFailures']:
        require(type(summary.get(name)) is int and summary[name]>=0,'Invalid finalized count: '+name)
    require(summary['expectedFailures']==0 and summary['passedTests']>0 and summary['totalTestCount']==summary['passedTests']+summary['failedTests']+summary['skippedTests'],'Incomplete/contradictory finalized counts')
    require((summary['result']=='Passed')==(summary['failedTests']==0),'Finalized aggregate result/count contradiction')
    require(bool(summary.get('testFailures'))==(summary['failedTests']>0),'Finalized failure details contradict counts')
    for name in ['startTime','finishTime']:
        value=summary.get(name);require(type(value) in (int,float) and math.isfinite(value) and value>0,'Unfinalized result time')
    require(summary['finishTime']>summary['startTime'],'Unfinalized result interval')
    configurations=summary.get('devicesAndConfigurations')
    require(isinstance(configurations,list) and len(configurations)==1,'Missing/ambiguous result configuration')
    conf=configurations[0];dev=conf.get('device')
    require(isinstance(dev,dict),'Missing actual result device')
    require((dev.get('platform'),dev.get('osVersion'),dev.get('osBuildNumber'),dev.get('architecture'))==('iOS Simulator','27.0',RUNTIME_BUILD,'arm64'),'Unqualified actual runtime build/architecture')
    require(dev.get('deviceId')==expected_device['id'] and dev.get('modelName')==expected_device['model'],'Actual result is for another owned device/model')
    for key in ['passedTests','failedTests','skippedTests','expectedFailures']:
        require(type(conf.get(key)) is int and conf[key]==summary[key],'Contradictory actual device counts')
    return {'schema':'Celluloid.ConsumerRuntimeBinding.1','device_id':dev['deviceId'],'model':dev['modelName'],
        'runtime_version':dev['osVersion'],'runtime_build':dev['osBuildNumber'],'architecture':dev['architecture'],
        'profile':receipt['profile'],'scale':receipt['scale'],'aggregate_result':summary['result'],'aggregate_execution_passed':summary['result']=='Passed',
        'summary_sha256':hashlib.sha256(json.dumps(summary,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        'summary_hash_encoding':'canonical sorted compact JSON','source':'Actual finalized xcresult summary; raw named consumer must independently start and pass once'}

def validate_raw_execution(log,summary):
    """Consistent failed aggregates retain passed consumer evidence, never a green row."""
    import re
    lines=log.splitlines();cases={};active={};suites={};totals=[];terminals=[];errors=[];unclassified=[];failure_headers=[];writing_headers=[];result_headers=[];result_paths=[]
    case_re=re.compile(r"Test Case '(.+)' (started\.|(passed|failed|skipped) \([0-9]+(?:\.[0-9]+)? seconds\)\.)")
    suite_re=re.compile(r"Test Suite '([^']+)' (started|passed|failed) at [0-9-]+ [0-9:.]+\.")
    total_re=re.compile(r'Executed (\d+) test(?:s)?, with (?:(\d+) test(?:s)? skipped and )?(\d+) failure(?:s)? \((\d+) unexpected\)(?: in [0-9.]+ \([0-9.]+\) seconds)?')
    authoritative=re.compile(r'^(?:.*\.[A-Za-z]+:\d+(?::\d+)?: )?error:|XCTAssert\w* failed|\bXCTFail\b|Assertion\s+(?:Failure|failed|Error)|AssertionFailure|AssertionError|^fatal error:|^Traceback|^RuntimeError:|^Exception Type:',re.I)
    for index,line in enumerate(lines):
        stripped=line.strip()
        if stripped.lower().startswith('test case '):
            match=case_re.fullmatch(stripped);require(match is not None,'Malformed raw testcase record')
            name=match[1];state='started' if match[2]=='started.' else match[3]
            if state=='started':
                require(name not in cases and name not in active,'Duplicate raw testcase start')
                active[name]=index
            else:
                require(name in active and name not in cases,'Raw case ended without one start')
                cases[name]={'state':state,'start_line':active.pop(name),'end_line':index}
        elif stripped.lower().startswith('test suite '):
            match=suite_re.fullmatch(stripped);require(match is not None,'Malformed raw suite record')
            suites.setdefault(match[1],[]).append((match[2],index))
        elif stripped.lower().startswith('executed '):
            match=total_re.fullmatch(stripped);require(match is not None,'Malformed execution total')
            totals.append((tuple(int(value or 0) for value in match.groups()),index))
        elif re.match(r'^\*\* TEST(?: EXECUTE)?\b',stripped,re.I):terminals.append((stripped,index))
        elif stripped.lower().startswith('failing tests:'):
            require(stripped=='Failing tests:','Malformed failing-tests header');failure_headers.append(index)
        elif stripped.lower().startswith('writing result bundle'):
            require(stripped=='Writing result bundle at path:','Malformed result-bundle header');writing_headers.append(index)
        elif stripped.lower().startswith('test session results'):
            require(stripped=='Test session results, code coverage, and logs:','Malformed result-session header');result_headers.append(index)
        elif stripped.startswith('/') and stripped.endswith('.xcresult'):
            require(re.fullmatch(r'/[^\r\n\x00]{1,1024}\.xcresult',stripped) is not None,'Malformed result-session path');result_paths.append((stripped,index))
        elif authoritative.search(line):errors.append((line,index))
        elif re.search(r'\b(?:failed|failure|error|warning)\b',line,re.I):
            # Non-authoritative console observations are retained, not treated
            # as XCTest failures or declared harmless.
            require(len(unclassified)<256 and len(line)<=4000,'Unbounded console diagnostic volume')
            unclassified.append(line)
    require(not active and cases,'Incomplete raw testcase execution')
    counts={state:sum(row['state']==state for row in cases.values()) for state in ['passed','failed','skipped']}
    require((counts['passed'],counts['failed'],counts['skipped'])==(summary['passedTests'],summary['failedTests'],summary['skippedTests']),'Raw case counts contradict finalized summary')
    require(len(cases)==summary['totalTestCount'],'Raw case inventory contradicts summary')
    outcome=summary['result'];expected='** TEST EXECUTE '+('SUCCEEDED' if outcome=='Passed' else 'FAILED')+' **'
    require(len(terminals)==1 and terminals[0][0]==expected and terminals[0][1]>max(row['end_line'] for row in cases.values()),'Raw terminal contradicts finalized execution')
    end=terminals[0][1]
    require(totals and all(position<end for _,position in totals),'Missing or late raw execution totals')
    if outcome=='Passed':require(all(failed==unexpected==0 for (_,_,failed,unexpected),_ in totals),'Failed raw totals contradict Passed summary')
    else:require(any(failed>0 for (_,_,failed,_),_ in totals),'Failed summary has no raw failure total')
    suite_intervals=[]
    for name,events in suites.items():
        require(len(events)%2==0,'Incomplete raw suite: '+name)
        for first,last in zip(events[::2],events[1::2]):
            require(first[0]=='started' and last[0] in {'passed','failed'} and first[1]<last[1]<end,'Malformed raw suite outcome')
            if outcome=='Passed':require(last[0]=='passed','Failed suite contradicts Passed summary')
            suite_intervals.append({'name':name,'start':first[1],'end':last[1],'state':last[0]})
    failed={name:row for name,row in cases.items() if row['state']=='failed'}
    scoped_errors=[]
    for line,position in errors:
        owner=re.search(r'error: -\[([^\]]+)\] :',line)
        matching=[name for name,row in failed.items() if row['start_line']<position<row['end_line'] and (owner is None or name=='-['+owner[1]+']')]
        require(outcome=='Failed' and len(matching)==1,'Unexplained/contradictory raw compiler or XCTest error')
        scoped_errors.append({'case':matching[0],'line':line})
    # XCTest emits one total after each closed suite. Bind its executed count
    #and issue count to cases/errors inside that precise interval, not merely
    #to a plausible global summary. Synthetic header-free transcripts must
    #instead account for disjoint completed-case intervals between totals.
    def check_total(values,inside):
        executed,skipped,failures,unexpected=values
        require(executed==len(inside),'Executed total contradicts its suite/case interval')
        require(skipped==sum(cases[name]['state']=='skipped' for name in inside),'Skipped total contradicts its suite/case interval')
        failed_inside=[name for name in inside if cases[name]['state']=='failed']
        issue_count=sum(max(1,sum(error['case']==name for error in scoped_errors)) for name in failed_inside)
        require(failures==issue_count and 0<=unexpected<=failures,'Failure total contradicts scoped cases/issues')
    covered=set()
    if suite_intervals:
        for a in suite_intervals:
            for b in suite_intervals:
                require(not (a['start']<b['start']<a['end']<b['end']),'Crossing/inconsistent suite intervals')
        used=set();events=[row['start_line'] for row in cases.values()]+[row['end_line'] for row in cases.values()]+[row['start'] for row in suite_intervals]
        for values,position in totals:
            closed=[row for row in suite_intervals if row['end']<position]
            require(closed,'Premature total before any completed suite')
            owner=max(closed,key=lambda row:row['end'])
            require(owner['end'] not in used and not any(owner['end']<event<position for event in events),'Duplicate or misplaced suite total')
            used.add(owner['end'])
            inside={name for name,row in cases.items() if owner['start']<row['start_line']<row['end_line']<owner['end']}
            check_total(values,inside);covered.update(inside)
        require(used=={row['end'] for row in suite_intervals},'Completed suite lacks its execution total')
    else:
        previous=-1
        for values,position in totals:
            inside={name for name,row in cases.items() if previous<row['start_line']<row['end_line']<position}
            check_total(values,inside);covered.update(inside);previous=position
    require(covered==set(cases),'Execution totals leave raw cases unaccounted')
    metadata_positions=set()
    if writing_headers or result_headers or result_paths:
        # xcodebuild may announce the same bundle before execution and again
        # after all suites/totals. Account for both records, never deduplicate
        # arbitrary paths. Final-only and header-free transcripts stay valid.
        require(len(writing_headers)<=1 and len(result_headers)==1 and len(result_paths)==1+len(writing_headers),'Malformed result-session metadata')
        execution_positions=[row[key] for row in cases.values() for key in ['start_line','end_line']]+[position for events in suites.values() for _,position in events]+[position for _,position in totals]
        final_path,final_position=result_paths[-1]
        require(max(execution_positions)<result_headers[0]<final_position<end,'Malformed result-session metadata')
        metadata_positions={result_headers[0],final_position}
        if writing_headers:
            initial_path,initial_position=result_paths[0]
            require(writing_headers[0]<initial_position<min(execution_positions) and initial_path==final_path,'Malformed result-session metadata')
            require(not any(line.strip() for line in lines[writing_headers[0]+1:initial_position]),'Malformed result-bundle announcement')
            metadata_positions.update({writing_headers[0],initial_position})
    if outcome=='Passed':require(not failure_headers,'Failing-tests block contradicts Passed summary')
    else:
        require(len(failure_headers)==1 and max(row['end_line'] for row in cases.values())<failure_headers[0]<end,'Missing/duplicate/premature failing-tests block')
        entries=[line.strip() for position,line in enumerate(lines) if failure_headers[0]<position<end and position not in metadata_positions and line.strip()]
        known={}
        for name in failed:
            match=re.fullmatch(r'-\[([\w.]+) (test\w+)\]',name)
            require(match is not None,'Unknown failed testcase identity')
            short=match[1].rsplit('.',1)[-1]+'.'+match[2]+'()'
            known.setdefault(short,[]).append(name)
        require(set(entries)==set(known),'Failing-tests entries disagree with failed raw cases')
        for name,owners in known.items():
            limit=max(len(owners),sum(item['case'] in owners for item in scoped_errors))
            require(1<=entries.count(name)<=limit,'Unaccounted duplicate failing-test entry')
    for item in summary.get('testFailures',[]):
        target=item.get('targetName');identifier=item.get('testIdentifierString','')
        match=re.fullmatch(r'([^/]+)/([^/]+)\(\)',identifier)
        require(match is not None and '-['+str(target)+'.'+match[1]+' '+match[2]+']' in failed,'Finalized failure belongs to no failed raw testcase')
    return {'scope':'Complete enclosing XCTest accounting; passed renderer consumer is separate from aggregate failures',
        'aggregate_result':outcome,'aggregate_execution_passed':outcome=='Passed','case_counts':counts,
        'failed_cases':sorted(failed),'scoped_errors':scoped_errors,'terminal':terminals[0][0],
        'result_session_path_observation':result_paths[-1][0] if result_paths else None,
        'unclassified_console_diagnostics':unclassified,'console_diagnostics_classified':False}
