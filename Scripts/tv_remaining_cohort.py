#!/usr/bin/env python3
"""Fixed remaining TV UI profiles using the proved clock and proof machinery."""
import argparse, hashlib, json, math, os, re, shutil, subprocess, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = '863848cec5ec18132b8b6a3daa012029b7fb9de1'
BASE_TREE = '1005c84bdd2c5226e1bb0d210112a637a5906cf0'
SOURCE = 'Scripts/tv-remaining-source.json'
WORKFLOW = '.github/workflows/tv-remaining-observation.yml'
BRANCH = 'codex/tv-remaining-observation'
PREFIX = 'CelluloidTVUITests/NativeTVUITests/'
PROFILES = {
    'rich': {'job': 'tv-rich', 'tests': [PREFIX+'testRemoteCollageThreeSources', PREFIX+'testRemoteCollageFourSources'], 'counts': [3, 4]},
    'chinese': {'job': 'tv-chinese', 'tests': [PREFIX+'testSimplifiedChinesePhotoFilterReopenAndLargeText'], 'counts': []}
}
def profile_spec():
    name=os.environ.get('CELLULOID_TV_REMAINING_PROFILE')
    require(name in PROFILES, 'Unreviewed remaining TV profile')
    return name,PROFILES[name]


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
CLOCK_PROFILE={'schema':'Celluloid.TVRemainingClock.2','execution_budget_seconds':1560,
               'work_budget_seconds':1200,'reserved_tail_seconds':360,
               'job_seconds':1800,'startup_teardown_margin_seconds':240}
TAIL_PHASES={'before':360,'before-build':795,'after':240,
             'before-accept':225,'before-collect':165,'before-upload':75}

def clock_deadlines(temp, now=None):
    path=temp/'tv-remaining-clock.json'
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
    path=temp/'tv-remaining-budget.json'; clock_sha=digest(temp/'tv-remaining-clock.json')
    report=json.loads(path.read_text()) if path.exists() else {'schema':'Celluloid.TVRemainingBudget.2',
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
    name='tv-remaining-upload-admission.json'
    require(name not in expected,'Upload receipt already exists')
    receipt={'source_sha':os.environ['GITHUB_SHA'],'clock_sha256':digest(temp/'tv-remaining-clock.json'),'budget':row,
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
    profile,spec=profile_spec();require(env.get('GITHUB_JOB')==spec['job'],'Wrong fixed remaining job')
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
    receipt={'schema':'Celluloid.TVRemainingSource.1','phase':phase,'profile':profile,'source_sha':sha,'tree':git('rev-parse','HEAD^{tree}'),
             'base_commit':BASE,'base_tree':BASE_TREE,'tracked_files':len(paths),'fingerprint':fingerprint,
             'manifest_sha256':digest(ROOT/SOURCE),'workflow_sha256':digest(ROOT/WORKFLOW),'clock_sha256':digest(temp/'tv-remaining-clock.json'),'release_acceptance':False}
    temp=Path(env['RUNNER_TEMP'])
    if phase=='after':
        before=json.loads((temp/'tv-remaining-before.json').read_text())
        require({k:v for k,v in before.items() if k!='phase'}=={k:v for k,v in receipt.items() if k!='phase'}, 'Source drift across execution')
    write(temp/('tv-remaining-'+phase+'.json'),receipt)
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

def capture_proof(source, destination, count):
    require(not destination.exists(), 'Proof destination already exists')
    recipe=json.loads((source/'kept-recipe.json').read_text())
    ids=[r['id'] for r in recipe['recipe']['sources']]
    require(count in [3,4] and len(ids)==count and len(set(ids))==count and all(re.fullmatch(r'[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}',i) for i in ids),'Wrong proof sources')
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

def capture_remaining_proofs(source, destination):
    # Retain completed output groups even if the other case or final audit fails.
    # Presence of a packet never grants the two-case acceptance below.
    destination.mkdir()
    groups=[];errors=[]
    for count in [3,4]:
        try:groups.append({'count':count,'files':capture_proof(source/str(count),destination/str(count),count)})
        except (ValueError,OSError,KeyError,TypeError,json.JSONDecodeError) as error:
            errors.append({'count':count,'error':str(error)[:1000]})
    require(sum(r['bytes'] for group in groups for r in group['files'])<=1_400_000,'Combined rich proof packet exceeds original retention cap')
    return {'groups':groups,'errors':errors}

def validate_execution(summary, text, evidence, timing, oracle, profile):
    require(profile in PROFILES,'Unknown fixed remaining profile');spec=PROFILES[profile];count=len(spec['tests'])
    require(summary.get('result')=='Passed' and all(type(summary.get(k)) is int and summary[k]==v for k,v in
            [('totalTestCount',count),('passedTests',count),('failedTests',0),('skippedTests',0),('expectedFailures',0)]),'Final summary does not match the exact remaining cases')
    require(not summary.get('testFailures'),'Final summary records failures')
    configurations=summary.get('devicesAndConfigurations',[]);require(len(configurations)==1,'Unexpected destinations')
    config=configurations[0];require(all(type(config.get(k)) is int and config[k]==v for k,v in [('passedTests',count),('failedTests',0),('skippedTests',0),('expectedFailures',0)]),'Per-device counts disagree')
    device=config['device']
    require(device['deviceId']==evidence['udid'] and device.get('platform')=='tvOS Simulator' and device.get('architecture')=='arm64'
            and device.get('osVersion')=='27.0' and device.get('osBuildNumber')=='24J360','Wrong actual runtime/device')
    require(type(evidence.get('test_exit_code')) is int and evidence['test_exit_code']==0 and evidence.get('selected_tests')==spec['tests']
            and evidence.get('profile')==profile and not evidence.get('error'),'Runtime scope or completion mismatch')
    require(type(timing.get('elapsed_seconds')) in [int,float] and math.isfinite(timing['elapsed_seconds']) and
            0<timing['elapsed_seconds']<=900 and timing.get('timed_out') is False and timing.get('return_code')==0,'Runtime process did not terminate within its original bound')
    require(evidence.get('cleanup')==[{'action':'shutdown','exit_code':0},{'action':'delete','exit_code':0}],'Owned simulator cleanup missing')
    require(evidence.get('product_before') and evidence['product_before']==evidence.get('product_after'),'Actual product changed')
    allowed={'-[CelluloidTVUITests.NativeTVUITests '+name.rsplit('/',1)[-1]+']' for name in spec['tests']}
    events=re.findall(r"Test Case '([^']+)' (started|passed|failed|skipped)(?:[ .(])",text)
    require(len(events)==2*count,'Raw exact-case count mismatch');seen=set()
    for index in range(0,len(events),2):
        first,last=events[index:index+2]
        require(first[0] in allowed and first[0] not in seen and first[1]=='started' and last==(first[0],'passed'),'Raw sequential case accounting mismatch')
        seen.add(first[0])
    require(seen==allowed and text.count('** TEST EXECUTE SUCCEEDED **')==1 and
            not re.search(r"error:|Test Suite '[^']+' failed|\*\* TEST EXECUTE FAILED|CELLULOID_NATIVE_UI_FAIL_CLOSED_ABORT",text),'Raw terminal contradicts complete execution')
    if profile=='rich':
        require(text.count('TV_NATIVE_KEYBOARD_ASCII actual system keyboard committed TV from two ordinary key events')==2,
                'Each rich case needs the real sequential ASCII keyboard path')
        require(text.count('TV_NATIVE_KEYBOARD_UNICODE actual system keyboard committed full multilingual text')==2,
                'Do not replace actual TV 世界 entry with ASCII or a compile probe')
        rows=[json.loads(line.split(' ',1)[1]) for line in text.splitlines() if line.startswith('TV_NATIVE_COMPOSITION_EXPECTED ')]
        require(len(rows)==2 and {r.get('count') for r in rows}=={3,4} and
                all(r.get('keyboardExercised') is True and r.get('bubbleText')=='TV 世界' for r in rows),'Exact three/four-source Unicode UI intent missing')
        lines=[line for line in oracle.splitlines() if line.startswith('TV_NATIVE_COMPOSITION_ORACLE ')]
        require(len(lines)==2,'Both independent Photos output oracles are required');counts=set()
        for line in lines:
            match=re.fullmatch(r'TV_NATIVE_COMPOSITION_ORACLE count=([34]) sourceSamples=\[([0-9, ]+)\] maximumChannelDifference=([012]) layerChangedSamples=\[([0-9, ]+)\] keyboardExercised=(?:1|true) readbackSHA256=([0-9a-f]{64})',line)
            require(match is not None,'Invalid independent rich output result')
            n=int(match[1]);samples=[int(x) for x in match[2].split(',')];layers=[int(x) for x in match[4].split(',')]
            require(n not in counts and len(samples)==n and min(samples)>5 and len(layers)==2 and min(layers)>0,'Incomplete independent source/layer coverage');counts.add(n)
        require(counts=={3,4},'Wrong independent output cases')
        return {'profile':profile,'expected_compositions':sorted(rows,key=lambda r:r['count']),'keyboard_text':'TV 世界'}
    require('TV_NATIVE_COMPOSITION_EXPECTED ' not in text and not oracle,'Chinese job must not inherit composition results')
    for mode,trait in [('false','tv.instruction.ordinary'),('true','tv.instruction.accessibility5')]:
        require(len(re.findall(r'TV_PUBLIC_TRAIT_STRESS requestedLargest='+mode+r' actualTraitIdentifier='+re.escape(trait)+r'.*systemPropagationVerified=false',text))==1,'Actual public-trait observation missing')
        require(len(re.findall(r'TV_PHOTO_LOCALIZED_REACHABILITY requestedLarge='+mode+r'.*selected=已选 1',text))==1,'Actual localized picker reachability missing')
        require(len(re.findall(r'TV_ZH_HANS_REOPEN requestedLarge='+mode+r'.*localized filter persisted',text))==1,'Localized actual reopen missing')
    privacy=[json.loads(line.split(' ',1)[1]) for line in text.splitlines() if line.startswith('TV_ZH_HANS_PRIVACY_COMPLETE ')]
    require(len(privacy)==2 and {r.get('requestedLarge') for r in privacy}=={False,True},'Both real privacy entry/exit states are required')
    require(all(type(r.get('requestedLarge')) is bool and r.get('bodyObserved') is True and r.get('dismissed') is True
                and r.get('restoredFilter')=='褪色' and r.get('systemSettingsChanged') is False and r.get('systemPropagationVerified') is False for r in privacy),
            'Privacy or honest system-setting boundary missing')
    return {'profile':profile,'privacy_states':privacy,'system_settings_propagation_verified':False,
            'scope':'Actual normal/public-largest-app-trait UI, not a claimed OS Settings change'}

def acceptance(temp):
    from native_process import run
    profile,spec=profile_spec()
    report={'schema':'Celluloid.TVRemainingObservation.1','source_sha':os.environ['GITHUB_SHA'],'profile':profile,'accepted':False,
            'release_acceptance':False,'scope':'Only the fixed remaining TV UI cases; previous two-source/hosted/filter results are separate evidence'}
    try:
        budget_admission(temp,'before-accept')
        before=json.loads((temp/'tv-remaining-before.json').read_text());after=json.loads((temp/'tv-remaining-after.json').read_text())
        require(before['source_sha']==after['source_sha']==report['source_sha'] and before['fingerprint']==after['fingerprint']
                and before['profile']==after['profile']==profile,'Same-source/profile closure missing')
        require_probe(json.loads((temp/'tv-text-input-probe.json').read_text()))
        result=run(['xcrun','xcresulttool','get','test-results','summary','--path',temp/'CelluloidTV.xcresult'],timeout=45,echo=False)
        require(len(result.stdout.encode())<=200_000,'Oversized finalized summary')
        summary=json.loads(result.stdout);write(temp/'CelluloidTV.xcresult.summary.json',summary)
        evidence=json.loads((temp/'tv-runtime-evidence.json').read_text());require(evidence['head']==report['source_sha'],'Wrong runtime head')
        oracle=(temp/'tv-composition-oracle.log').read_text() if profile=='rich' else ''
        expected=validate_execution(summary,(temp/'tv-runtime-tests.log').read_text(),evidence,
                                    json.loads((temp/'tv-runtime-tests.log.timing.json').read_text()),oracle,profile)
        if profile=='rich':
            groups=evidence.get('proof_groups',[]);require([g['count'] for g in groups]==[3,4],'Actual rich proof groups missing')
            require(sum(r['bytes'] for g in groups for r in g['files'])<=1_400_000,'Combined retained proof overflow')
            for group in groups:
                folder=temp/'tv-remaining-proof'/str(group['count']);rows=group['files']
                require(len(rows)==group['count']+3 and sorted(r['name'] for r in rows)==sorted(p.name for p in folder.iterdir()),'Proof membership changed')
                for row in rows:
                    require(Path(row['name']).name==row['name'],'Unsafe proof name');path=folder/row['name']
                    require(path.stat().st_size==row['bytes'] and digest(path)==row['sha256'],'Actual proof changed')
            report['proof_groups']=groups
        report.update(accepted=True,components=expected,source_fingerprint=before['fingerprint'],
                      summary_sha256=digest(temp/'CelluloidTV.xcresult.summary.json'),raw_log_sha256=digest(temp/'tv-runtime-tests.log'),
                      runtime_evidence_sha256=digest(temp/'tv-runtime-evidence.json'))
        if profile=='rich':report['oracle_log_sha256']=digest(temp/'tv-composition-oracle.log')
    except Exception as error:report['error']=str(error)
    write(temp/'tv-remaining-acceptance.json',report)
    require(report['accepted'],report.get('error','Remaining profile acceptance failed'))
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
