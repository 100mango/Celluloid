"""One current-source Photos host route; historical routes are never relabeled."""
import hashlib,json,os,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REPOSITORY='100mango/Celluloid'
HOST_ONLY={'scope':'photos-boundary-observation','branch':'celluloid-final-mac-photos-boundary-v2','workflow_path':'.github/workflows/final-mac-photos-boundary-v2.yml','diagnostic_only':True}
def require(ok,message):
    if not ok:raise ValueError(message)
def validate_route(value):
    require(type(value) is dict and value==HOST_ONLY and all(type(value[k]) is type(v) for k,v in HOST_ONLY.items()),'Wrong final Mac Photos route')
    return dict(HOST_ONLY)
def current_route(env=None):
    env=os.environ if env is None else env
    ref='refs/heads/'+HOST_ONLY['branch'];source=env.get('GITHUB_SHA')
    require(env.get('GITHUB_REPOSITORY')==REPOSITORY and env.get('GITHUB_EVENT_NAME')=='push' and env.get('GITHUB_REF')==ref,'Wrong final Mac Photos repository/event/ref')
    require(env.get('CELLULOID_VALIDATION_SCOPE')==HOST_ONLY['scope'],'Wrong Photos scope')
    require(env.get('GITHUB_WORKFLOW_REF')==REPOSITORY+'/'+HOST_ONLY['workflow_path']+'@'+ref,'Wrong final Photos workflow')
    require(type(source) is str and re.fullmatch('[0-9a-f]{40}',source) and source==env.get('GITHUB_WORKFLOW_SHA'),'Wrong final Photos source SHA')
    return dict(HOST_ONLY)
def host_only_source_binding(rows):
    contract=json.loads((ROOT/'.github/final-mac-photos-product.json').read_text())
    require(rows==contract['files'] and len(rows)==962,'Wrong complete product graph')
    digest=hashlib.sha256(json.dumps(rows,separators=(',',':')).encode()).hexdigest()
    require(digest==contract['fingerprint'],'Wrong product fingerprint')
    return {'product_sha':contract['product_sha'],'product_tree':contract['product_tree'],'unchanged_protected_files':962,'unchanged_protected_fingerprint':digest,'native_tests_reexecuted':False,'uikit_reexecuted':False,'writer_delivery_observed':False,'photos_internal_storage_observed':False,'actual_host_test_required':'MacPhotosHostUITests/testInstalledExtensionIsInvokedByActualPhotos','layered_guard_unchanged':True,'release_qualified':False}
def host_clock_profile(route):
    validate_route(route)
    return {'name':'photos-export-observation-900-v1','case_seconds':900,'test_seconds':960,
        'process_seconds':1020,'pretest_seconds':240,'tail_seconds':360,'step_margin_seconds':60,
        'step_seconds':1680,'before_prepare_seconds':1980,'before_host_seconds':1740,'evidence_seconds':300}
def context_clock(context):
    expected=host_clock_profile(context['validation_route'])
    require(type(context.get('host_clock_profile')) is dict and context['host_clock_profile']==expected and all(type(context['host_clock_profile'][k]) is type(v) for k,v in expected.items()),'Wrong source-bound host clock profile')
    return expected
