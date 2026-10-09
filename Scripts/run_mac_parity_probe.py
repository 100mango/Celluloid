#!/usr/bin/env python3
"""Two-test, current-source Mac-to-original-2x diagnostic; never Photos qualification."""
from pathlib import Path
import hashlib,json,os,re,subprocess,sys,time
from native_process import run
from native_fixture_handoff import layer_from_log,validate_layer
from platform_rendering_contract import (control_bytes,validate_archive_fixture,native_from_log,require_case_enclosure)

ROOT=Path(__file__).resolve().parents[1]
BASE='9c85361da5fd26ac63a43c12813171c185928e1f'
BASE_TREE='281e8d7763cb1b36a6d6422a90c735e6c6d712c6'
BRANCH='refs/heads/cell-mac-parity-probe'
ALLOWED={'.github/workflows/mac-parity-probe.yml','Scripts/run_mac_parity_probe.py',
 'Scripts/test_mac_parity_probe.py','Scripts/generate_native_project.py',
 'CelluloidNative.xcodeproj/project.pbxproj','Platforms/MacExtensionTests/MacPhotoAdjustmentTests.swift'}
CASES=['MacPhotoAdjustmentTests.testNewManufacturedValuesKeepUIKitTypesAndAllFields',
 'MacPhotoRendererTests.testProductionTextMatchesIndependentNativeControlAndRejectsPathMutations']
SELECTORS=['CelluloidMacPhotosExtensionTests/'+x.replace('.','/') for x in CASES]
PREFIX='MAC_ORIGINAL_2X_PROBE '
WORK_SECONDS=900

def require(ok,message):
    if not ok:raise ValueError(message)
def sha(data):return hashlib.sha256(data).hexdigest()
def unique(pairs):
    result={}
    for key,value in pairs:
        require(key not in result,'Duplicate JSON key: '+key);result[key]=value
    return result
def save(path,value):path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
def integer(value,maximum):return type(value) is int and 0<=value<=maximum

def admit_identity(source,parent,base_tree,changes,environment):
    require(re.fullmatch('[0-9a-f]{40}',source) is not None,'Invalid current source')
    require(parent==[source,BASE] and base_tree==BASE_TREE,'Not the exact single-parent diagnostic descendant')
    require(set(changes)==ALLOWED and len(changes)==len(ALLOWED),'Unexpected source delta')
    require(environment.get('GITHUB_REPOSITORY')=='100mango/Celluloid' and environment.get('GITHUB_REF')==BRANCH
            and environment.get('GITHUB_EVENT_NAME')=='push' and environment.get('GITHUB_WORKFLOW_SHA')==source
            and environment.get('GITHUB_SHA')==source,'Wrong source-bound workflow route')

def validate_summary(summary,log):
    for key,value in {'totalTestCount':2,'passedTests':2,'failedTests':0,'skippedTests':0,'expectedFailures':0}.items():
        require(type(summary.get(key)) is int and summary[key]==value,'Unexpected official summary: '+key)
    require(summary.get('result')=='Passed' and summary.get('testFailures')==[] and summary.get('runtimeWarnings')==[],
            'Official XCTest result failed or has runtime warnings')
    devices=summary.get('devicesAndConfigurations',[])
    require(len(devices)==1 and devices[0].get('device',{}).get('platform')=='macOS'
            and devices[0]['device'].get('architecture')=='arm64','Wrong actual native execution platform')
    for key,value in {'passedTests':2,'failedTests':0,'skippedTests':0,'expectedFailures':0}.items():
        require(type(devices[0].get(key)) is int and devices[0][key]==value,'Contradictory device summary: '+key)
    expected={'CelluloidMacPhotosExtensionTests.'+case.replace('.', ' ',1) for case in CASES}
    events=re.findall(r"^Test Case '-\[([^\]]+)\]' (started|passed|failed|skipped)\b",log,re.M)
    require(len([line for line in log.splitlines() if line.startswith('Test Case ')])==len(events), 'Malformed raw XCTest outcome')
    require(set(case for case,_ in events)==expected,'Unexpected or missing raw XCTest selector')
    for case in expected:
        require([status for owner,status in events if owner==case]==['started','passed'],'Contradictory/duplicate raw XCTest outcome')
    terminals=re.findall(r'^\*\* TEST(?: EXECUTE)? (SUCCEEDED|FAILED) \*\*$',log,re.M)
    require(terminals==['SUCCEEDED'],'Missing/contradictory successful xcodebuild terminal')
    require(not re.search(r'Publishing changes from within view updates|Modifying state during view update|AddressSanitizer|ThreadSanitizer',log),
            'Native runtime warning or sanitizer failure')

def validate_probe(record,fixture):
    validate_layer(fixture);controls=json.loads(control_bytes(),object_pairs_hook=unique)
    keys={'schema','scope','controlFileSHA256','controlSourceSHA','controlProfile','controlRuntime','controlBuild',
          'archiveSHA256','controlArchiveSHA256','sourcePNG_SHA256','actualPNG_SHA256','comparisons','layeredPhotosOutputQualified'}
    require(isinstance(record,dict) and set(record)==keys,'Unknown/missing probe fields')
    for key,value in {'schema':'Celluloid.MacOriginal2xProbe.1','scope':'synthetic-pre-host-only',
        'controlFileSHA256':sha(control_bytes()),'controlSourceSHA':controls['sourceSHA'],'controlProfile':'2x',
        'controlRuntime':'27.0','controlBuild':'24A434','archiveSHA256':fixture['sha256'],
        'controlArchiveSHA256':controls['archiveSHA256'],'sourcePNG_SHA256':fixture['sourceSHA256'],
        'actualPNG_SHA256':fixture['renderedSHA256']}.items():
        require(record.get(key)==value,'Probe binding mismatch: '+key)
    require(record['layeredPhotosOutputQualified'] is False,'A diagnostic cannot qualify Photos output')
    graph=validate_archive_fixture(fixture,controls)
    actual={'full':fixture['renderedSHA256'],**{c['name']:c['sha256'] for c in fixture['components']}}
    names=['full','filtered-base','bubble-artwork','sticker-artwork','all-artwork']
    rows=record['comparisons'];require(isinstance(rows,list) and [r.get('name') for r in rows]==names,'Missing/duplicate/reordered components')
    for row in rows:
        require(set(row)=={'name','actualPNG_SHA256','originalPNG_SHA256','maximumChannelDifference','allowedMaximum',
                         'channelMaximumsRGBA','pixelsAboveTwo','boundsAboveTwo'},'Unknown component fields')
        name=row['name'];original=controls['profiles']['2x']['images'].get(name) or controls['common'][name]
        require(row['actualPNG_SHA256']==actual[name] and row['originalPNG_SHA256']==original['sha256'],'Wrong component identity')
        limit=0 if name in ('filtered-base','sticker-artwork') else 2
        require(type(row['allowedMaximum']) is int and row['allowedMaximum']==limit,'Changed pixel threshold')
        maxima=row['channelMaximumsRGBA']
        require(isinstance(maxima,list) and len(maxima)==4 and all(integer(x,limit) for x in maxima),'Strict RGBA mismatch')
        require(integer(row['maximumChannelDifference'],limit) and row['maximumChannelDifference']==max(maxima),'Inconsistent maximum')
        require(type(row['pixelsAboveTwo']) is int and row['pixelsAboveTwo']==0 and row['boundsAboveTwo']==[480,640,-1,-1]
                and all(type(x) is int for x in row['boundsAboveTwo']),
                'Nonzero/inconsistent failed pixel coverage')
    return graph

def probe_from_log(log,fixture):
    owner,method=CASES[0].split('.')
    require_case_enclosure(log,PREFIX,owner,method,{'CelluloidMacPhotosExtensionTests'})
    lines=[line for line in log.splitlines() if line.startswith(PREFIX)]
    require(len(lines)==1 and len(lines[0])<=16_384,'Missing/duplicate/oversized strict 2x record')
    record=json.loads(lines[0][len(PREFIX):],object_pairs_hook=unique)
    return record,validate_probe(record,fixture)

def main():
    os.chdir(ROOT);started=time.monotonic();deadline=started+WORK_SECONDS
    temp=Path(os.environ['RUNNER_TEMP']);out=temp/'cell-mac-parity-evidence';out.mkdir(exist_ok=False)
    derived=temp/'cell-mac-parity-derived';result=temp/'CelluloidMacParity.xcresult'
    require(not derived.exists() and not result.exists(),'Refusing reused native outputs')
    source=os.environ.get('GITHUB_SHA','');report={'schema':'celluloid.mac-parity-run.v1','source_sha':source,'base_sha':BASE,
        'selectors':SELECTORS,'work_budget_seconds':WORK_SECONDS,'accepted':False,'release_qualification':False,
        'photos_host_qualification':False,'signing':False,'simulators_used':False,'events':[]}
    failure=None;source_hashes=None
    def git(*args):return subprocess.check_output(['git',*args],text=True,timeout=15).strip()
    def clean():require(git('diff','--name-only','HEAD','--')=='','Tracked source changed during probe')
    def command(name,args,cap,check=True):
        require(time.monotonic()+cap+30<=deadline,'Insufficient bounded work allowance: '+name)
        before=time.monotonic()
        try:r=run(args,timeout=cap,check=False,log_name='cell-mac-parity-evidence/'+name+'.log',echo=False)
        except BaseException:
            report['events'].append({'phase':name,'completed':False,'elapsed_seconds':time.monotonic()-before})
            raise  # No later native process/diagnostic after uncertain timeout.
        report['events'].append({'phase':name,'completed':True,'exit_code':r.returncode,'elapsed_seconds':time.monotonic()-before})
        require(not check or r.returncode==0,name+' failed');return r
    try:
        require(sys.platform=='darwin','Requires approved Xcode 27 cloud executor')
        require(os.environ.get('DEVELOPER_DIR')=='/Applications/Xcode_27.app/Contents/Developer','Wrong toolchain route')
        require(git('rev-parse','HEAD')==source,'Checkout source mismatch')
        admit_identity(source,git('rev-list','--parents','-n','1','HEAD').split(),git('rev-parse',BASE+'^{tree}'),
                       git('diff','--name-only',BASE,'HEAD','--').splitlines(),os.environ)
        clean();report['source_tree']=git('rev-parse','HEAD^{tree}')
        source_hashes={path:sha((ROOT/path).read_bytes()) for path in git('ls-files','-z').split('\0') if path}
        report['tracked_source_fingerprint']=sha(json.dumps(source_hashes,sort_keys=True,separators=(',',':')).encode())
        report['run_id']=os.environ.get('GITHUB_RUN_ID');report['run_attempt']=os.environ.get('GITHUB_RUN_ATTEMPT')
        require(all(re.fullmatch('[1-9][0-9]*',report[k] or '') for k in ['run_id','run_attempt']),'Missing workflow identity')
        save(out/'source-binding.json',report)
        version=command('toolchain',['xcodebuild','-version'],20).stdout
        require('Xcode 27.0' in version.splitlines(),'Wrong stable Xcode version')
        command('os-version',['sw_vers'],10)
        common=['xcodebuild','-project','CelluloidNative.xcodeproj','-scheme','CelluloidMacPhotosExtension',
                '-configuration','Debug','-destination','platform=macOS,arch=arm64','-derivedDataPath',str(derived),
                'CODE_SIGNING_ALLOWED=NO','CODE_SIGNING_REQUIRED=NO','CODE_SIGN_IDENTITY=',
                'COMPILER_INDEX_STORE_ENABLE=NO']
        command('build',[*common,'-jobs','2','build-for-testing'],600)
        binary=derived/'Build/Products/Debug/CelluloidMacPhotosExtensionTests.xctest/Contents/MacOS/CelluloidMacPhotosExtensionTests'
        require(binary.is_file() and not binary.is_symlink(),'Missing exact test product')
        report['test_binary_sha256']=sha(binary.read_bytes());save(out/'build-binding.json',report)
        tested=command('tests',[*common,'-parallel-testing-enabled','NO','-collect-test-diagnostics','never',
             '-resultBundlePath',str(result),*['-only-testing:'+s for s in SELECTORS],'test-without-building'],180,False)
        summary_result=command('summary',['xcrun','xcresulttool','get','test-results','summary','--path',str(result)],30)
        summary=json.loads(summary_result.stdout,object_pairs_hook=unique);save(out/'summary.json',summary)
        report['native_test_exit_code']=tested.returncode
        log=(out/'tests.log').read_text();payload=layer_from_log(out/'tests.log',source)
        (out/'mac-layer-fixture.json').write_bytes(payload);fixture=json.loads(payload)['fixture']
        # Retain raw diagnostic data even on a failed strict comparison.
        raw=[line[len(PREFIX):] for line in log.splitlines() if line.startswith(PREFIX)]
        if len(raw)==1:save(out/'original-2x-probe.json',json.loads(raw[0],object_pairs_hook=unique))
        require(tested.returncode==0,'Selected native XCTest failed; diagnostic evidence retained')
        validate_summary(summary,log)
        strict,graph=probe_from_log(log,fixture);save(out/'archive-graph-proof.json',graph)
        save(out/'native-text-contract.json',native_from_log(log,fixture))
        owner,method=CASES[0].split('.')
        require_case_enclosure(log,'MAC_LAYER_ADJUSTMENT_FIXTURE ',owner,method,{'CelluloidMacPhotosExtensionTests'})
        require(sha(binary.read_bytes())==report['test_binary_sha256'],'Test product changed during execution')
        clean();report['accepted']=True
    except BaseException as error:failure=type(error).__name__+': '+str(error)
    finally:
        report['error']=failure;report['elapsed_seconds']=time.monotonic()-started
        if source_hashes is not None:
            report['tracked_source_unchanged']=all((ROOT/path).is_file() and sha((ROOT/path).read_bytes())==digest for path,digest in source_hashes.items())
            if not report['tracked_source_unchanged']:
                report['accepted']=False;report['error']='Tracked source changed during native execution'
        # Pure local evidence handling only: no post-timeout native command.
        for path in out.glob('*.log'):
            cap=2_000_000 if path.name=='tests.log' else 300_000
            if path.stat().st_size>cap:
                data=path.read_bytes();path.write_bytes(data[-cap:]);report.setdefault('truncated_logs',[]).append(path.name)
                if path.name=='tests.log':report['accepted']=False;report['error']='Required test log exceeded evidence budget'
        save(out/'result.json',report)
        files=[{'name':p.name,'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())} for p in sorted(out.iterdir()) if p.is_file()]
        require(sum(p['bytes'] for p in files)<=4_000_000,'Evidence exceeds fixed 4MB budget')
        save(out/'manifest.json',{'source_sha':source,'files':files,'maximum_bytes':4_000_000,'scope':'diagnostic-only'})
    print(json.dumps(report,sort_keys=True));return 0 if report['accepted'] else 1
if __name__=='__main__':raise SystemExit(main())
