#!/usr/bin/env python3
"""One source-bound TV UI observation. No release or whole-platform acceptance."""
import argparse, hashlib, json, math, os, re, shutil, subprocess, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = '87450ac79129f3d5a0ee211b0681236512acfe37'
BASE_TREE = '418b2b8cd64844e4028a3d045ff5ce525eec0c1e'
SOURCE = 'Scripts/tv-two-source-source.json'
WORKFLOW = '.github/workflows/tv-two-source-observation.yml'
BRANCH = 'codex/tv-two-source-observation'
ONLY_TEST = 'CelluloidTVUITests/NativeTVUITests/testRemoteCollageTwoSources'
RAW_CASE = '-[CelluloidTVUITests.NativeTVUITests testRemoteCollageTwoSources]'

def require(value, reason):
    if not value: raise ValueError(reason)

def digest(path):
    require(path.is_file() and not path.is_symlink(), 'Missing or symbolic-link input: '+str(path))
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n')

# Match the established first-step clock pattern: a 26-minute execution
# window inside the unchanged 30-minute job, leaving four minutes outside
# that window for runner/action startup and job teardown. Checkout, source
# checks, SDK probes and builds all consume this execution window.
CLOCK_PROFILE={'schema':'Celluloid.TVTwoSourceClock.2','execution_budget_seconds':1560,
               'work_budget_seconds':1200,'reserved_tail_seconds':360,
               'job_seconds':1800,'startup_teardown_margin_seconds':240}
TAIL_PHASES={'before':360,'before-build':795,'after':240,
             'before-accept':225,'before-collect':165,'before-upload':75}

def clock_deadlines(temp, now=None):
    path=temp/'tv-two-source-clock.json'
    require(path.is_file() and not path.is_symlink(), 'Missing or symbolic job clock')
    value=json.loads(path.read_text()); now=time.monotonic() if now is None else now
    require(set(value)==set(CLOCK_PROFILE)|{'source_sha','started_monotonic','started_unix'}, 'Unexpected clock fields')
    require(all(type(value[k]) is type(v) and value[k]==v for k,v in CLOCK_PROFILE.items()), 'Unreviewed fixed clock profile')
    require(value['source_sha']==os.environ.get('GITHUB_SHA') and re.fullmatch('[0-9a-f]{40}',value['source_sha']) is not None, 'Clock source mismatch')
    require(all(type(value[k]) in (int,float) and math.isfinite(value[k]) and value[k]>0 for k in ['started_monotonic','started_unix']), 'Invalid clock origin')
    require(type(now) in (int,float) and math.isfinite(now) and value['started_monotonic']<=now, 'Future or invalid monotonic observation')
    return value['started_monotonic']+1200,value['started_monotonic']+1560

def budget_admission(temp, phase, now=None):
    require(phase in TAIL_PHASES, 'Unknown budget admission')
    now=time.monotonic() if now is None else now
    work,deadline=clock_deadlines(temp,now); required=TAIL_PHASES[phase]
    path=temp/'tv-two-source-budget.json'; clock_sha=digest(temp/'tv-two-source-clock.json')
    report=json.loads(path.read_text()) if path.exists() else {'schema':'Celluloid.TVTwoSourceBudget.2',
        'source_sha':os.environ['GITHUB_SHA'],'clock_sha256':clock_sha,'events':[]}
    require(report.get('source_sha')==os.environ['GITHUB_SHA'] and report.get('clock_sha256')==clock_sha, 'Budget source/clock changed')
    require(len(report['events'])<12 and all(e['phase']!=phase for e in report['events']), 'Repeated budget phase')
    require(not report['events'] or report['events'][-1]['observed_monotonic']<=now, 'Budget observations went backward')
    row={'phase':phase,'observed_monotonic':now,'execution_remaining_seconds':deadline-now,
         'work_remaining_seconds':work-now,'required_seconds':required,'admitted':deadline-now>=required}
    report['events'].append(row); write(path,report)
    require(row['admitted'],'Insufficient fixed job budget for '+phase)
    return row

def upload_admission(temp):
    folder=temp/'celluloid-bounded-evidence'; path=folder/'manifest.json'; manifest=json.loads(path.read_text())
    require(manifest.get('source_sha')==os.environ['GITHUB_SHA'], 'Wrong collected packet source')
    expected={r['name'] for r in manifest['files']}
    require(len(expected)==len(manifest['files']) and expected|{'manifest.json'}=={p.name for p in folder.iterdir()}, 'Collected packet membership changed')
    for r in manifest['files']:
        require(Path(r['name']).name==r['name'], 'Unsafe collected member')
        p=folder/r['name']; require(p.stat().st_size==r['bytes'] and digest(p)==r['sha256'], 'Collected packet changed')
    row=budget_admission(temp,'before-upload')
    name='tv-two-source-upload-admission.json'
    require(name not in expected,'Upload receipt already exists')
    receipt={'source_sha':os.environ['GITHUB_SHA'],'clock_sha256':digest(temp/'tv-two-source-clock.json'),'budget':row,
             'pre_admission_manifest_sha256':digest(path),'scope':'Final upload admission only; delivery is not yet proved'}
    data=(json.dumps(receipt,indent=2)+'\n').encode();require(len(data)<=4096,'Oversized upload receipt')
    manifest['files'].append({'name':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'source':'final source-bound clock admission'})
    manifest['retained_bytes_before_manifest']=sum(r['bytes'] for r in manifest['files'])
    payload=(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n').encode()
    require(len(payload)<=100000 and len(payload)+manifest['retained_bytes_before_manifest']<=2750000,'Final packet exceeds unchanged TV cap')
    (folder/name).write_bytes(data);path.write_bytes(payload)
    return receipt

def require_probe(value):
    require(value.get('compiled') is True and type(value.get('exit_code')) is int and value['exit_code']==0,
            'Actual current SDK typeText compilation is required')
    require(value.get('runtime_keyboard_coverage') is False, 'SDK compile must not claim runtime keyboard coverage')

def verify_files(root, manifest, membership):
    require(manifest.get('base_commit')==BASE and manifest.get('base_tree')==BASE_TREE, 'Wrong frozen base')
    rows=manifest['files']; paths=[r['path'] for r in rows]
    require(paths==sorted(set(paths)) and SOURCE not in paths, 'Duplicate, unsorted or self-referential source paths')
    require(set(membership)==set(paths)|{SOURCE} and len(membership)==len(paths)+1, 'Complete tracked-source membership changed')
    for row in rows:
        name=row['path']; parts=Path(name).parts
        require(not Path(name).is_absolute() and '..' not in parts, 'Unsafe source path')
        path=root/name
        require(all(not parent.is_symlink() for parent in [path,*path.parents] if parent!=root.parent), 'Symbolic source path')
        require(path.stat().st_size==row['bytes'] and digest(path)==row['sha256'], 'Changed source: '+name)
        mode='100755' if path.stat().st_mode & 0o111 else '100644'
        require(mode==row['mode'], 'Changed source mode: '+name)
    return hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def source_receipt(phase):
    def git(*args): return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
    env=os.environ; sha=env.get('GITHUB_SHA','')
    temp=Path(env['RUNNER_TEMP']);budget_admission(temp,phase)
    require(re.fullmatch('[0-9a-f]{40}',sha) is not None, 'Missing exact candidate SHA')
    require(env.get('GITHUB_REPOSITORY')=='100mango/Celluloid' and env.get('GITHUB_EVENT_NAME')=='push', 'Wrong repository/event')
    require(env.get('GITHUB_REF')=='refs/heads/'+BRANCH, 'Wrong cohort branch')
    require(env.get('GITHUB_WORKFLOW_REF')=='100mango/Celluloid/'+WORKFLOW+'@refs/heads/'+BRANCH and env.get('GITHUB_WORKFLOW_SHA')==sha, 'Wrong workflow source')
    require(git('rev-parse','HEAD')==sha and git('rev-list','--parents','-n','1','HEAD').split()==[sha,BASE], 'Candidate must have sole frozen parent')
    require(not git('status','--porcelain','--untracked-files=all'), 'Dirty execution checkout')
    manifest=json.loads((ROOT/SOURCE).read_text())
    paths=[p for p in git('ls-files','-z').split('\0') if p]
    fingerprint=verify_files(ROOT,manifest,paths)
    receipt={'schema':'Celluloid.TVTwoSourceSource.1','phase':phase,'source_sha':sha,'tree':git('rev-parse','HEAD^{tree}'),
             'base_commit':BASE,'base_tree':BASE_TREE,'tracked_files':len(paths),'fingerprint':fingerprint,
             'manifest_sha256':digest(ROOT/SOURCE),'workflow_sha256':digest(ROOT/WORKFLOW),'clock_sha256':digest(temp/'tv-two-source-clock.json'),'release_acceptance':False}
    temp=Path(env['RUNNER_TEMP'])
    if phase=='after':
        before=json.loads((temp/'tv-two-source-before.json').read_text())
        require({k:v for k,v in before.items() if k!='phase'}=={k:v for k,v in receipt.items() if k!='phase'}, 'Source drift across execution')
    write(temp/('tv-two-source-'+phase+'.json'),receipt)
    return receipt

def capture_product(built, udid, run):
    import plistlib
    installed=Path(run(['xcrun','simctl','get_app_container',udid,'Mango.Celluloid','app'],timeout=45).stdout.strip())
    records=[]
    for app in [built,installed]:
        require(app.name=='CelluloidTV.app' and app.is_dir() and not app.is_symlink(), 'Wrong actual TV product')
        info=plistlib.loads((app/'Info.plist').read_bytes())
        require(info.get('CFBundleIdentifier')=='Mango.Celluloid' and info.get('CFBundleExecutable')=='CelluloidTV', 'Wrong actual executable identity')
        records.append({'bundle_id':info['CFBundleIdentifier'],'executable_sha256':digest(app/'CelluloidTV')})
    require(records[0]==records[1], 'Installed/built TV executable differs')
    return records[0]

def capture_proof(source, destination):
    require(not destination.exists(), 'Proof destination already exists')
    recipe=json.loads((source/'kept-recipe.json').read_text())
    ids=[r['id'] for r in recipe['recipe']['sources']]
    require(len(ids)==2 and len(set(ids))==2 and all(re.fullmatch(r'[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}',i) for i in ids),'Wrong proof sources')
    names=sorted(['kept-recipe.json','photos-output.json','photos-output.png']+[i+'.image' for i in ids])
    rows=[]
    for name in names:
        path=source/name; sha=digest(path); size=path.stat().st_size
        require(size<=1_400_000, 'Proof member exceeds bounded retention')
        rows.append({'name':name,'bytes':size,'sha256':sha})
    require(sum(r['bytes'] for r in rows)<=1_400_000, 'Proof packet exceeds bounded retention')
    destination.mkdir()
    for row in rows: shutil.copyfile(source/row['name'],destination/row['name'])
    return rows

def validate_execution(summary, text, evidence, timing, oracle):
    require(summary.get('result')=='Passed' and all(type(summary.get(k)) is int and summary[k]==v for k,v in
            [('totalTestCount',1),('passedTests',1),('failedTests',0),('skippedTests',0),('expectedFailures',0)]),'Actual finalized summary is not exactly one passed case')
    require(not summary.get('testFailures'), 'Final summary records failures')
    configurations=summary.get('devicesAndConfigurations',[])
    require(len(configurations)==1, 'Unexpected test destinations')
    require(all(type(configurations[0].get(k)) is int and configurations[0][k]==v for k,v in [('passedTests',1),('failedTests',0),('skippedTests',0),('expectedFailures',0)]), 'Per-device counts contradict one passed case')
    device=configurations[0]['device']
    require(device['deviceId']==evidence['udid'] and device.get('platform')=='tvOS Simulator' and device.get('architecture')=='arm64'
            and device.get('osVersion')=='27.0' and device.get('osBuildNumber')=='24J360', 'Wrong actual runtime/device')
    require(type(evidence.get('test_exit_code')) is int and evidence['test_exit_code']==0 and evidence.get('only_testing')==ONLY_TEST and not evidence.get('error'), 'Runtime did not complete the focused case')
    require(type(timing.get('elapsed_seconds')) in [int,float] and math.isfinite(timing['elapsed_seconds']), 'Nonfinite timing')
    require(timing.get('timed_out') is False and timing.get('return_code')==0 and 0<timing.get('elapsed_seconds',0)<=900,'Test process did not terminate successfully inside its original bound')
    require(evidence.get('cleanup')==[{'action':'shutdown','exit_code':0},{'action':'delete','exit_code':0}], 'Owned simulator cleanup unverified')
    require(evidence.get('product_before') and evidence['product_before']==evidence.get('product_after'), 'Product changed or readback missing')
    events=re.findall(r"Test Case '([^']+)' (started|passed|failed|skipped)(?:[ .(])",text)
    require(events==[(RAW_CASE,'started'),(RAW_CASE,'passed')], 'Raw testcase accounting differs from the sole admitted case')
    require(text.count('** TEST EXECUTE SUCCEEDED **')==1 and not re.search(r"error:|Test Suite '[^']+' failed|\*\* TEST EXECUTE FAILED|CELLULOID_NATIVE_UI_FAIL_CLOSED_ABORT",text),'Raw terminal contradicts pass or contains error')
    marker='TV_NATIVE_KEYBOARD_ASCII actual system keyboard committed TV from two ordinary key events'
    require(text.count(marker)==1, 'Actual system keyboard input marker missing or duplicated')
    rows=[json.loads(line.split(' ',1)[1]) for line in text.splitlines() if line.startswith('TV_NATIVE_COMPOSITION_EXPECTED ')]
    require(len(rows)==1 and rows[0].get('count')==2 and rows[0].get('keyboardExercised') is True and rows[0].get('bubbleText')=='TV','Hello, compile-only or extra-composition result cannot qualify')
    require(len([l for l in oracle.splitlines() if l.startswith('TV_NATIVE_COMPOSITION_ORACLE ')])==1 and
            re.search(r'TV_NATIVE_COMPOSITION_ORACLE count=2 sourceSamples=\[[1-9][0-9]*, [1-9][0-9]*\] maximumChannelDifference=[012] layerChangedSamples=\[[1-9][0-9]*, [1-9][0-9]*\] keyboardExercised=(?:1|true) readbackSHA256=[0-9a-f]{64}',oracle),
            'Independent actual Photos composition oracle did not pass exactly count2')
    return rows[0]

def acceptance(temp):
    from native_process import run
    report={'schema':'Celluloid.TVTwoSourceObservation.1','source_sha':os.environ['GITHUB_SHA'],'accepted':False,
            'release_acceptance':False,'scope':'One actual two-source ASCII keyboard/Undo/reopen/Photos-output UI case; no wider platform claim'}
    try:
        budget_admission(temp,'before-accept')
        before=json.loads((temp/'tv-two-source-before.json').read_text()); after=json.loads((temp/'tv-two-source-after.json').read_text())
        require(before['source_sha']==after['source_sha']==report['source_sha'] and before['fingerprint']==after['fingerprint'],'Same-source closure missing')
        require_probe(json.loads((temp/'tv-text-input-probe.json').read_text()))
        result=run(['xcrun','xcresulttool','get','test-results','summary','--path',temp/'CelluloidTV.xcresult'],timeout=45,echo=False)
        require(len(result.stdout.encode())<=200_000,'Oversized finalized summary')
        summary=json.loads(result.stdout); write(temp/'CelluloidTV.xcresult.summary.json',summary)
        evidence=json.loads((temp/'tv-runtime-evidence.json').read_text())
        require(evidence['head']==report['source_sha'],'Wrong runtime head')
        expected=validate_execution(summary,(temp/'tv-runtime-tests.log').read_text(),evidence,
                                   json.loads((temp/'tv-runtime-tests.log.timing.json').read_text()),(temp/'tv-composition-oracle.log').read_text())
        rows=evidence.get('proof_files',[]);require(len(rows)==5,'Actual Photos proof packet missing')
        require(sorted(r['name'] for r in rows)==sorted(p.name for p in (temp/'tv-two-source-proof').iterdir()),'Proof membership changed')
        for row in rows:
            require(Path(row['name']).name==row['name'],'Unsafe retained proof name')
            path=temp/'tv-two-source-proof'/row['name']
            require(path.stat().st_size==row['bytes'] and digest(path)==row['sha256'],'Retained actual proof changed')
        report.update(accepted=True,expected=expected,proof_files=rows,source_fingerprint=before['fingerprint'],
                      summary_sha256=digest(temp/'CelluloidTV.xcresult.summary.json'),raw_log_sha256=digest(temp/'tv-runtime-tests.log'),
                      oracle_log_sha256=digest(temp/'tv-composition-oracle.log'),runtime_evidence_sha256=digest(temp/'tv-runtime-evidence.json'))
    except Exception as error:
        report['error']=str(error)
    write(temp/'tv-two-source-acceptance.json',report)
    require(report['accepted'],report.get('error','Focused acceptance failed'))
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['before','after','require-probe','accept','before-build','before-collect','before-upload']);args=parser.parse_args()
    temp=Path(os.environ['RUNNER_TEMP'])
    if args.action in ['before','after']: result=source_receipt(args.action)
    elif args.action in ['before-build','before-collect']:result=budget_admission(temp,args.action)
    elif args.action=='before-upload':result=upload_admission(temp)
    elif args.action=='require-probe': result=require_probe(json.loads((temp/'tv-text-input-probe.json').read_text()))
    else: result=acceptance(temp)
    print(json.dumps(result,sort_keys=True))
