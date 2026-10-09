#!/usr/bin/env python3
"""Separate closed admission for corrected sources; historical UIKit freeze is unchanged."""
from pathlib import Path
import argparse, hashlib, json, os, re, subprocess, time
ROOT=Path(__file__).resolve().parents[1]
BRANCH='celluloid-rendering-qualification'
WORKFLOW='.github/workflows/corrected-rendering-qualification.yml'
CONFIG='.github/corrected-rendering-qualification.json'
DEPENDENCIES='Scripts/fixtures/corrected-rendering-dependencies.json'
DEPENDENCY_SHA256='486229a865355aa312825aef1e36d5a2c2c030ffc2fcd79c37c297c3bd8a70c6'
PRODUCT_SHA='13e9a1ed63c6e7744803419f27e429a759df1209'
PRODUCT_TREE='f2c6d0f38c026957b0b34f22b916eb80ed5b20a8'
CURRENT_UIKIT_FINGERPRINT='f3da35962bd29598de93dacf810bf7d521478d91839e3e1d9cd99e2808548970'
CONSUMER='CelluloidTests/MacPhotosManufacturedAdjustmentTests.swift'
CONSUMER_SHA256='f4c7a7a16bf5414e6c2a2716bc146bdc216f7ea966a80207acce8a7667584890'
CONTROL_SOURCE='52bf7a9c04e2d91880ca4e8fd3418cd94d32bb7e'
UIKIT_ROOTS=('Celluloid','CelluloidKit','CelluloidPhotoExtension','Celluloid.xcodeproj')
CONTROL_PATHS=frozenset((WORKFLOW,CONFIG,DEPENDENCIES,
    'Scripts/corrected_rendering_admission.py','Scripts/run_corrected_rendering_qualification.py',
    'Scripts/test_corrected_rendering_qualification.py','Scripts/run_early_uikit_interop.py',
    'Scripts/verify_interop_continuation.py','Scripts/collect_native_evidence.py'))
def need(value,message):
    if not value:raise ValueError(message)
def sha(data):return hashlib.sha256(data).hexdigest()
def unique(pairs):
    result={}
    for key,value in pairs:
        need(key not in result,'Duplicate JSON key: '+key);result[key]=value
    return result
def read_json(path):
    need(path.is_file() and not path.is_symlink(),'Missing or symbolic input: '+str(path))
    raw=path.read_bytes();need(0<len(raw)<=500_000,'Unbounded JSON input')
    return json.loads(raw,object_pairs_hook=unique)
_ADMISSION_DEADLINE=None
def git(*args,root=ROOT):
    remaining=20 if _ADMISSION_DEADLINE is None else min(20,_ADMISSION_DEADLINE-time.monotonic())
    need(remaining>0,'Source admission90-second budget exhausted')
    return subprocess.check_output(['git',*args],cwd=root,text=True,timeout=remaining).strip()
def validate(config,context,facts):
    need(set(config)=={'schema','READY','sourceReady','product_sha','product_tree','maximum_additional_spend_usd','confirmation'},'Unknown admission fields')
    need(type(config['schema']) is int and config['schema']==1 and config['READY'] is True and config['sourceReady'] is True,'Corrected v2 route is closed')
    need(config['product_sha']==PRODUCT_SHA and config['product_tree']==PRODUCT_TREE,'Wrong reviewed corrected product')
    need(type(config['maximum_additional_spend_usd']) is int and config['maximum_additional_spend_usd']==0,'Nonzero cost is not admitted')
    need(config['confirmation']=='RUN_ONE_CORRECTED_V2_JOB_ZERO_USD','Wrong bounded qualification confirmation')
    expected={'repository':'100mango/Celluloid','event':'push','ref':'refs/heads/'+BRANCH,
              'workflow_ref':'100mango/Celluloid/'+WORKFLOW+'@refs/heads/'+BRANCH,'attempt':'1','mode':'corrected-v2'}
    need(all(context.get(k)==v for k,v in expected.items()),'Wrong corrected workflow context or retry')
    need(context.get('sha')==context.get('workflow_sha')==facts['head'],'Control SHA mismatch')
    need(re.fullmatch('[1-9][0-9]*',context.get('run_id','')) is not None,'Invalid run identity')
    need(re.fullmatch('[0-9a-f]{40}',facts['head']) and re.fullmatch('[0-9a-f]{40}',facts['tree']),'Invalid actual control identity')
    need(facts['parent_tree']==PRODUCT_TREE and not facts['dirty'],'Product tree changed or dirty checkout')
    need(0<len(facts['chain'])<=32,'Control history must contain1–32 linear commits')
    prior=PRODUCT_SHA
    for row in facts['chain']:
        need(row['parents']==[prior] and row['changed_paths'] and set(row['changed_paths'])<=CONTROL_PATHS,'Product edit or merge in control history')
        prior=row['sha']
    need(prior==facts['head'] and set(facts['changed_paths'])==CONTROL_PATHS,'Incomplete or unexpected control closure')
    return {'schema':'Celluloid.CorrectedRenderingAdmission.1','product_sha':PRODUCT_SHA,'product_tree':PRODUCT_TREE,
            'source_sha':facts['head'],'source_tree':facts['tree'],'control_sha':facts['head'],'control_tree':facts['tree'],
            'current_uikit_fingerprint':CURRENT_UIKIT_FINGERPRINT,'frozen_control_source':CONTROL_SOURCE,
            'consumer_sha256':CONSUMER_SHA256,'dependency_manifest_sha256':DEPENDENCY_SHA256,
            'run_id':context.get('run_id'),'run_attempt':'1',
            'scope':'Existing PlatformRendering.2 fixture qualification; current controller dependencies are explicitly pinned, not all historical bytes.',
            'layered_photos_guard_unchanged':True,'photos_host_qualified':False,'release_qualified':False}
def check_dependencies(root=ROOT):
    path=root/DEPENDENCIES;raw=path.read_bytes();need(sha(raw)==DEPENDENCY_SHA256,'Dependency manifest identity changed')
    manifest=read_json(path);need(manifest['product_sha']==PRODUCT_SHA and manifest['product_tree']==PRODUCT_TREE,'Dependency product identity changed')
    rows=manifest['files'];need(isinstance(rows,list) and rows,'Missing dependency inventory')
    paths=[]
    for row in rows:
        rel=row['path'];need(isinstance(rel,str) and not Path(rel).is_absolute() and '..' not in Path(rel).parts,'Unsafe dependency path')
        p=root/rel;need(p.is_file() and not p.is_symlink() and sha(p.read_bytes())==row['sha256'],'Changed dependency: '+rel);paths.append(rel)
    need(len(paths)==len(set(paths)),'Duplicate dependency path')
    current=[p for p in git('ls-files','-z',root=root).split('\0') if p]
    protected=manifest['protected_roots'];explicit=set(manifest['explicit_paths'])
    actual_envelope={p for p in current if p in explicit or any(p==prefix or p.startswith(prefix+'/') for prefix in protected)}
    need(actual_envelope==set(paths),'Compiled dependency envelope changed')
    compiled_roots={'Celluloid','CelluloidKit','CelluloidPhotoExtension','Celluloid.xcodeproj'}
    need({p for p in current if p.split('/')[0] in compiled_roots}=={p for p in paths if p.split('/')[0] in compiled_roots},'Compiled UIKit root inventory changed')
    fingerprint_rows=[[p,sha((root/p).read_bytes())] for p in current if p.split('/')[0] in compiled_roots]
    need(sha(json.dumps(fingerprint_rows,separators=(',',':')).encode())==CURRENT_UIKIT_FINGERPRINT,'Corrected full UIKit/project fingerprint changed')
    need(sha((root/CONSUMER).read_bytes())==CONSUMER_SHA256,'Original consumer changed')
    from platform_rendering_contract import control_bytes,native_spec
    control_bytes();native_spec()
    return manifest

def _admit(root=ROOT,env=None):
    env=os.environ if env is None else env
    config=read_json(root/CONFIG)
    # Closed configuration stops before Git/runtime/build/simulator activity.
    need(config.get('READY') is True and config.get('sourceReady') is True,'Corrected v2 route is closed')
    context={key:env.get(name,'') for key,name in {'repository':'GITHUB_REPOSITORY','event':'GITHUB_EVENT_NAME','ref':'GITHUB_REF','workflow_ref':'GITHUB_WORKFLOW_REF','sha':'GITHUB_SHA','workflow_sha':'GITHUB_WORKFLOW_SHA','attempt':'GITHUB_RUN_ATTEMPT','run_id':'GITHUB_RUN_ID','mode':'CELLULOID_RENDERING_QUALIFICATION'}.items()}
    git('merge-base','--is-ancestor',PRODUCT_SHA,'HEAD',root=root)
    chain=[]
    for row in git('rev-list','--reverse','--parents',PRODUCT_SHA+'..HEAD',root=root).splitlines():
        parts=row.split();need(len(parts)==2,'Merge or missing parent')
        chain.append({'sha':parts[0],'parents':parts[1:],'changed_paths':git('diff','--name-only',parts[1],parts[0],root=root).splitlines()})
    facts={'head':git('rev-parse','HEAD',root=root),'tree':git('rev-parse','HEAD^{tree}',root=root),
           'parent_tree':git('rev-parse',PRODUCT_SHA+'^{tree}',root=root),'chain':chain,
           'changed_paths':git('diff','--name-only',PRODUCT_SHA,'HEAD',root=root).splitlines(),
           'dirty':git('status','--porcelain','--untracked-files=all',root=root)}
    result=validate(config,context,facts);check_dependencies(root)
    paths=[p for p in git('ls-files','-z',root=root).split('\0') if p and p not in CONTROL_PATHS]
    result['product_file_count']=len(paths)
    result['product_fingerprint']=sha(json.dumps([[p,sha((root/p).read_bytes())] for p in paths],separators=(',',':')).encode())
    result['control_fingerprint']=sha(json.dumps([[p,sha((root/p).read_bytes())] for p in sorted(CONTROL_PATHS)],separators=(',',':')).encode())
    return result



def admit(root=ROOT,env=None):
    global _ADMISSION_DEADLINE
    previous=_ADMISSION_DEADLINE;_ADMISSION_DEADLINE=time.monotonic()+90
    try:return _admit(root,env)
    finally:_ADMISSION_DEADLINE=previous

# A failed bounded dispatch closes only this corrected route. It does not assert
# that a child exit proves process-group cleanup, and never authorizes cleanup.
NATIVE_MARKER='corrected-native-dispatch-failure.json'
_NATIVE_BLOCKED=False

def native_context():
    context={k:os.environ.get(v,'') for k,v in [('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('run_attempt','GITHUB_RUN_ATTEMPT')]}
    need(re.fullmatch('[0-9a-f]{40}',context['source_sha']) is not None and re.fullmatch('[1-9][0-9]*',context['run_id']) is not None and context['run_attempt']=='1','Malformed native fence identity')
    return context

def require_native_clear(root=None):
    need(not _NATIVE_BLOCKED,'Corrected native work stopped after failed or interrupted dispatch')
    path=Path(os.environ['RUNNER_TEMP'] if root is None else root)/NATIVE_MARKER
    if path.exists() or path.is_symlink():
        need(path.is_file() and not path.is_symlink() and path.stat().st_size<=8192,'Invalid native fence receipt')
        value=read_json(path);need(value.get('context')==native_context(),'Stale native fence receipt')
        raise ValueError('Corrected native work stopped; retained dispatch failure does not authorize cleanup')

def mark_native_failure(error):
    global _NATIVE_BLOCKED
    _NATIVE_BLOCKED=True
    path=Path(os.environ['RUNNER_TEMP'])/NATIVE_MARKER
    value={'schema':'Celluloid.CorrectedNativeDispatchFailure.1','context':native_context(),
           'error_type':type(error).__name__[:80],'error':str(error)[:600],
           'native_dispatch_blocked':True,'process_group_cleanup_confirmed':False,
           'scope':'Conservative stop after failed/interrupted bounded dispatch; pure-file evidence only.'}
    try:descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except FileExistsError:return
    with os.fdopen(descriptor,'w') as handle:handle.write(json.dumps(value,indent=2)+'\n')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=['before','after'],required=True);args=parser.parse_args()
    result=admit();temp=Path(os.environ['RUNNER_TEMP'])
    if args.phase=='after':need(read_json(temp/'combined-source-before.json')==result,'Source/control identity changed during run')
    (temp/('combined-source-'+args.phase+'.json')).write_text(json.dumps(result,indent=2)+'\n')
    print('CORRECTED_RENDERING_SOURCE '+json.dumps(result,sort_keys=True))
if __name__=='__main__':main()
