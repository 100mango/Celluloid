"""Exact source-bound workflows; focused diagnostics never qualify release."""
import hashlib,json,os,re

REPOSITORY='100mango/Celluloid'
FULL={'scope':'full','branch':'codex/apple-platforms','workflow_path':'.github/workflows/apple-platforms.yml','diagnostic_only':False}
FOCUSED={'scope':'mac-repair','branch':'codex/mac-repair','workflow_path':'.github/workflows/mac-repair.yml','diagnostic_only':True}

HOST_ONLY={'scope':'photos-export-observation','branch':'codex/photos-export-observation','workflow_path':'.github/workflows/photos-export-observation.yml','diagnostic_only':True}
HOST_ONLY_BASE={'commit':'25b8edc92c3f53cf13208ffa0065746b87ae20e0','tree':'7622774f3291c7b32f46966bebffddd645e57326','fingerprint':'d395f03291d06dc09f0d561b2096fd0bfe32b63f08764753c9d1b31a1069c88b'}
HOST_ONLY_PROTECTED_FINGERPRINT='c1d88b1bafe0ef55c838e28eccb606d0b7e4701d792d88399f8b03ecc40f984b'
HOST_ONLY_UI_TEST={'path':'Platforms/UITests/MacPhotosHostUITests.swift','sha256':'be6aad78bfd6e4599aa2de79dd4111d3fd424c15148bf10464f35ba4ac3221e9'}

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


def host_only_source_binding(rows):
    """One reviewed UI-test change; every other qualified source byte is fixed."""
    require(type(rows) is list and len(rows)==547,'Host-only source membership changed')
    require(all(type(row) is list and len(row)==2 and all(type(item) is str for item in row) for row in rows),'Malformed host-only source rows')
    reviewed=[row for row in rows if row[0]==HOST_ONLY_UI_TEST['path']]
    protected=[row for row in rows if row[0]!=HOST_ONLY_UI_TEST['path']]
    require(reviewed==[[HOST_ONLY_UI_TEST['path'],HOST_ONLY_UI_TEST['sha256']]],'Unreviewed host UI-test bytes')
    fingerprint=hashlib.sha256(json.dumps(protected,separators=(',',':')).encode()).hexdigest()
    require(len(protected)==546 and fingerprint==HOST_ONLY_PROTECTED_FINGERPRINT,'Host-only protected production/test/project bytes changed')
    return {'prior_source':dict(HOST_ONLY_BASE),'unchanged_protected_files':546,
        'unchanged_protected_fingerprint':fingerprint,'reviewed_host_ui_test':dict(HOST_ONLY_UI_TEST),
        'native_42_reexecuted':False,'uikit_reexecuted':False,
        'actual_host_test_required':'MacPhotosHostUITests/testInstalledExtensionIsInvokedByActualPhotos'}
