"""Two exact source-bound workflows; focused Mac diagnostics never qualify release."""
import os,re

REPOSITORY='100mango/Celluloid'
FULL={'scope':'full','branch':'codex/apple-platforms','workflow_path':'.github/workflows/apple-platforms.yml','diagnostic_only':False}
FOCUSED={'scope':'mac-repair','branch':'codex/mac-repair','workflow_path':'.github/workflows/mac-repair.yml','diagnostic_only':True}

def require(ok,message):
    if not ok:raise ValueError(message)

def validate_route(value):
    require(type(value) is dict and set(value)==set(FULL) and type(value.get('diagnostic_only')) is bool,'Malformed validation route')
    require(value==FULL or value==FOCUSED,'Unknown validation route')
    return dict(value)

def current_route(environment=None):
    env=os.environ if environment is None else environment
    ref=env.get('GITHUB_REF')
    if ref=='refs/heads/'+FULL['branch']:
        # Preserve canonical admission; a caller flag cannot relabel this branch.
        return dict(FULL)
    require(ref=='refs/heads/'+FOCUSED['branch'],'Unreviewed validation branch')
    require(env.get('GITHUB_REPOSITORY')==REPOSITORY and env.get('GITHUB_EVENT_NAME')=='push','Wrong focused repository/event')
    require(env.get('CELLULOID_VALIDATION_SCOPE')=='mac-repair','Missing focused diagnostic scope')
    require(env.get('GITHUB_WORKFLOW_REF')==REPOSITORY+'/'+FOCUSED['workflow_path']+'@'+ref,'Wrong focused workflow identity')
    source=env.get('GITHUB_SHA')
    require(type(source) is str and re.fullmatch(r'[0-9a-f]{40}',source) is not None and env.get('GITHUB_WORKFLOW_SHA')==source,'Focused workflow source mismatch')
    return dict(FOCUSED)
