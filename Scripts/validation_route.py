"""Exact source-bound routes; focused diagnostics never qualify a release."""
import hashlib,math,os,re,subprocess,time
from pathlib import Path

REPOSITORY='100mango/Celluloid'
FULL={'scope':'full','branch':'codex/apple-platforms','workflow_path':'.github/workflows/apple-platforms.yml','diagnostic_only':False}
FOCUSED={'scope':'mac-repair','branch':'codex/mac-repair','workflow_path':'.github/workflows/mac-repair.yml','diagnostic_only':True}
UIKIT={'scope':'uikit-interop-diagnostic','branch':'codex/uikit-interop-diagnostic','workflow_path':'.github/workflows/uikit-interop-diagnostic.yml','diagnostic_only':True}
QUALIFIED_SOURCE_SHA='8470141a3fff60c4033d5584a755917d122c196b'
QUALIFIED_SOURCE_TREE='dabf2d635c3d838d611f900032c07276ee25eda1'
PREVIOUS_DRIVER_SHA='5c717edeca62ccd0e728e8f617f366ca8c1c19c6'
PREVIOUS_DRIVER_TREE='87c9721f5bf9afdc4db91d669acc7f9d17b867eb'
ORIGINAL_DRIVER_PATHS=frozenset({UIKIT['workflow_path'],'Scripts/validation_route.py',
    'Scripts/verify_combined_source.py','Scripts/test_uikit_interop_diagnostic.py'})
PARSER_REPAIR_PATHS=frozenset({'Scripts/consumer_runtime_binding.py','Scripts/test_consumer_runtime_binding.py'})
DRIVER_ONLY_PATHS=ORIGINAL_DRIVER_PATHS|PARSER_REPAIR_PATHS
SUCCESSOR_PATHS=(ORIGINAL_DRIVER_PATHS-{'Scripts/verify_combined_source.py'})|PARSER_REPAIR_PATHS
UIKIT_WINDOW_SECONDS=27*60  # Existing20min consumer +2min replay +1min source +3min collect +1min upload.
UIKIT_FINAL_SECONDS=4*60    # The source-after step has already used its own1min allowance.


def require(ok,message):
    if not ok:raise ValueError(message)

def validate_route(value):
    require(type(value) is dict and set(value)==set(FULL) and type(value.get('diagnostic_only')) is bool,'Malformed validation route')
    require(value==FULL or value==FOCUSED or value==UIKIT,'Unknown validation route')
    return dict(value)

def current_route(environment=None):
    env=os.environ if environment is None else environment
    ref=env.get('GITHUB_REF')
    if ref=='refs/heads/'+FULL['branch']:
        # Preserve canonical admission; a caller flag cannot relabel this branch.
        return dict(FULL)
    selected=next((value for value in (FOCUSED,UIKIT) if ref=='refs/heads/'+value['branch']),None)
    require(selected is not None,'Unreviewed validation branch')
    require(env.get('GITHUB_REPOSITORY')==REPOSITORY and env.get('GITHUB_EVENT_NAME')=='push','Wrong focused repository/event')
    require(env.get('CELLULOID_VALIDATION_SCOPE')==selected['scope'],'Missing focused diagnostic scope')
    require(env.get('GITHUB_WORKFLOW_REF')==REPOSITORY+'/'+selected['workflow_path']+'@'+ref,'Wrong focused workflow identity')
    source=env.get('GITHUB_SHA')
    require(type(source) is str and re.fullmatch(r'[0-9a-f]{40}',source) is not None and env.get('GITHUB_WORKFLOW_SHA')==source,'Focused workflow source mismatch')
    return dict(selected)


def qualified_uikit_source(root,source):
    """Bind this one repaired driver through exact5c71 to immutable8470 bytes."""
    root=Path(root)
    def git(*args):return subprocess.check_output(['git',*args],cwd=root,text=True,timeout=15).strip()
    require(git('rev-parse','HEAD')==source,'Wrong diagnostic driver checkout')
    require(git('rev-list','--parents','-n','1','HEAD').split()==[source,PREVIOUS_DRIVER_SHA],
            'Diagnostic must be a direct single-parent successor of exact5c71')
    require(git('rev-parse',PREVIOUS_DRIVER_SHA+'^{tree}')==PREVIOUS_DRIVER_TREE,'Previous5c71 driver tree changed')
    require(git('rev-list','--parents','-n','1',PREVIOUS_DRIVER_SHA).split()==[PREVIOUS_DRIVER_SHA,QUALIFIED_SOURCE_SHA],
            'Previous5c71 driver must have sole qualified8470 parent')
    require(git('rev-parse',QUALIFIED_SOURCE_SHA+'^{tree}')==QUALIFIED_SOURCE_TREE,'Qualified8470 tree changed')
    require(not git('status','--porcelain','--untracked-files=all'),'Dirty diagnostic checkout')
    def entries(ref):
        rows={}
        for record in git('ls-tree','-r','-z',ref).split('\0'):
            if record:
                identity,path=record.split('\t',1);rows[path]=identity
        return rows
    base=entries(QUALIFIED_SOURCE_SHA);previous=entries(PREVIOUS_DRIVER_SHA);driver=entries('HEAD')
    changed={path for path in base.keys()|driver.keys() if base.get(path)!=driver.get(path)}
    require(changed==DRIVER_ONLY_PATHS,'Changes outside the exact admitted diagnostic driver delta')
    repaired={path for path in previous.keys()|driver.keys() if previous.get(path)!=driver.get(path)}
    require(repaired==SUCCESSOR_PATHS,'Changes outside the exact admitted five-file parser successor')
    require(all(driver[path].startswith('100644 blob ') for path in DRIVER_ONLY_PATHS),'Driver file type/mode changed')
    # Full tree comparison above covers every renderer, original42 tests,
    # UIKit product/consumer, immutable control, and existing workflow byte.
    return {'qualified_source_commit':QUALIFIED_SOURCE_SHA,'qualified_source_tree':QUALIFIED_SOURCE_TREE,
        'previous_driver_commit':PREVIOUS_DRIVER_SHA,'previous_driver_tree':PREVIOUS_DRIVER_TREE,
        'driver_commit':source,'driver_tree':git('rev-parse','HEAD^{tree}'),
        'repair_files':sorted(SUCCESSOR_PATHS),
        'driver_files':[{ 'path':p,'sha256':hashlib.sha256((root/p).read_bytes()).hexdigest()} for p in sorted(DRIVER_ONLY_PATHS)],
        'qualification':'Identical8470 tracked bytes except four enumerated diagnostic driver files and two result-session parser files; exact5c71 successor with real new execution identity.',
        'diagnostic_only':True,'full_release_accepted':False}


def uikit_diagnostic_budget(clock,source,phase,now=None):
    """One admission threshold, not a scheduler or a new runtime allowance."""
    require(phase in {'before','after'},'Unknown diagnostic budget phase')
    require(clock.get('source_sha')==source,'Wrong diagnostic job clock source')
    require(type(clock.get('execution_budget_seconds')) is int and clock['execution_budget_seconds']==41*60,'Changed45min job allocation')
    def positive(value):return type(value) in (int,float) and math.isfinite(value) and value>0
    require(positive(clock.get('started_monotonic')) and positive(clock.get('started_unix')),'Invalid diagnostic job clock')
    observed=time.monotonic() if now is None else now
    require(positive(observed) and observed>=clock['started_monotonic'],'Invalid diagnostic observation time')
    remaining=clock['started_monotonic']+clock['execution_budget_seconds']-observed
    required=UIKIT_WINDOW_SECONDS if phase=='before' else UIKIT_FINAL_SECONDS
    require(remaining>=required,'Insufficient existing job budget; consumers withheld rather than increasing caps')
    return {'phase':phase,'clock':dict(clock),'observed_monotonic':observed,
        'remaining_seconds':remaining,'required_seconds':required,'admitted':True}
