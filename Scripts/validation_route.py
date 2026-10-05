"""Exact source-bound workflows; focused diagnostics never qualify release."""
import os,re

REPOSITORY='100mango/Celluloid'
FULL={'scope':'full','branch':'codex/apple-platforms','workflow_path':'.github/workflows/apple-platforms.yml','diagnostic_only':False}
FOCUSED={'scope':'mac-repair','branch':'codex/mac-repair','workflow_path':'.github/workflows/mac-repair.yml','diagnostic_only':True}

HOST_ONLY={'scope':'photos-export-observation','branch':'codex/photos-export-observation','workflow_path':'.github/workflows/photos-export-observation.yml','diagnostic_only':True}
HOST_ONLY_BASE={'commit':'25b8edc92c3f53cf13208ffa0065746b87ae20e0','tree':'7622774f3291c7b32f46966bebffddd645e57326','fingerprint':'d395f03291d06dc09f0d561b2096fd0bfe32b63f08764753c9d1b31a1069c88b'}

def require(ok,message):
    if not ok:raise ValueError(message)

def validate_route(value):
    require(type(value) is dict and set(value)==set(FULL) and type(value.get('diagnostic_only')) is bool,'Malformed validation route')
    require(value==FULL or value==FOCUSED or value==HOST_ONLY,'Unknown validation route')
    return dict(value)

def current_route(environment=None):
    env=os.environ if environment is None else environment
    ref=env.get('GITHUB_REF')
    if ref=='refs/heads/'+FULL['branch']:
        # Preserve canonical admission; a caller flag cannot relabel this branch.
        return dict(FULL)
    selected=next((value for value in (FOCUSED,HOST_ONLY) if ref=='refs/heads/'+value['branch']),None)
    require(selected is not None,'Unreviewed validation branch')
    require(env.get('GITHUB_REPOSITORY')==REPOSITORY and env.get('GITHUB_EVENT_NAME')=='push','Wrong focused repository/event')
    require(env.get('CELLULOID_VALIDATION_SCOPE')==selected['scope'],'Missing focused diagnostic scope')
    require(env.get('GITHUB_WORKFLOW_REF')==REPOSITORY+'/'+selected['workflow_path']+'@'+ref,'Wrong focused workflow identity')
    source=env.get('GITHUB_SHA')
    require(type(source) is str and re.fullmatch(r'[0-9a-f]{40}',source) is not None and env.get('GITHUB_WORKFLOW_SHA')==source,'Focused workflow source mismatch')
    return dict(selected)
