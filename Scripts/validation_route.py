"""Exact source-bound workflows; focused diagnostics never qualify release."""
import hashlib,json,os,re

REPOSITORY='100mango/Celluloid'
FULL={'scope':'full','branch':'codex/apple-platforms','workflow_path':'.github/workflows/apple-platforms.yml','diagnostic_only':False}
FOCUSED={'scope':'mac-repair','branch':'codex/mac-repair','workflow_path':'.github/workflows/mac-repair.yml','diagnostic_only':True}

UIKIT_FULL={'scope':'uikit-full-shipping','branch':'codex/uikit-full-shipping','workflow_path':'.github/workflows/uikit-full-shipping.yml','diagnostic_only':True}
UIKIT_FULL_BASE={'commit':'a940bcdf8a92811210bcfacf84141dceb6c3fcd3','tree':'c68526b6228dffb891825e000caf50ea7a53fc45','fingerprint':'d1eaa8c2612fd92c66c0089ea8f6dc9026caff49aac8b00c6c62e2e9ff64c886'}
UIKIT_FULL_PREDECESSOR={'commit':'a79d359ea605320e37750057adf1a053c13a5fee','tree':'945455872f5a153fdc5a6754f9355c928526883d'}
UIKIT_FULL_REPAIR_PATHS={'.github/workflows/uikit-full-shipping.yml','Scripts/validation_route.py','Scripts/verify_combined_source.py','Scripts/test_uikit_full_shipping_bootstrap.py','Scripts/test_uikit_full_shipping_route.py','Scripts/test_uikit_full_shipping_workflow.py'}
UIKIT_FULL_DRIVER_PATHS={'.github/workflows/uikit-full-shipping.yml','Scripts/validation_route.py','Scripts/verify_combined_source.py','Scripts/mac_photos_host_gate.py','Scripts/collect_native_evidence.py','Scripts/uikit_full_shipping_gate.py','Scripts/test_uikit_full_shipping_gate.py','Scripts/uikit_full_shipping_handoff.py','Scripts/probe_photos_bootstrap.py','Scripts/test_uikit_full_shipping_route.py','Scripts/test_uikit_full_shipping_workflow.py','Scripts/test_uikit_full_shipping_bootstrap.py','Scripts/test_mac_photos_host_gate.py','Scripts/test_combined_preflight.py','Scripts/test_combined_validation.py','Scripts/test_consumer_runtime_binding.py','Scripts/test_native_evidence.py','Scripts/test_text_observation_evidence.py','Documentation/uikit-full-shipping.md'}


ORIGINAL_IOS={'scope':'original-ios-release','branch':'codex/original-ios-release','workflow_path':'.github/workflows/original-ios-release.yml','diagnostic_only':True}
ORIGINAL_IOS_BASE={'commit':'4c0c6cb3314cd89e41fc9cfc67b833aca7de7d56','tree':'67ee79704e23936ba451173ce8aa68614b1ec1da'}
ORIGINAL_IOS_PREDECESSOR={'commit':'588fa917cbe62e60c6b3502d47aae70b1db3ff55','tree':'2f410ba817e274a2236513b37b3917ad6420fbc1'}
ORIGINAL_IOS_QUALIFIED_PREDECESSOR={'commit':'04d18a496b019f54706ff42128605cda1d7dea83','tree':'ea20b3393c2ec6f65bc19b4a7a523ce59de6003d'}
ORIGINAL_IOS_ARCHIVE_PREDECESSOR={'commit':'da9d4abd6484ddaff469677d96caf24362645d7c','tree':'304ee9c0e4197e4a282ae3933c9f510219b2106d'}
ORIGINAL_IOS_ARCHIVE_ONLY_PATHS={
    '.github/workflows/original-ios-release.yml',
    'Documentation/original-ios-release.md',
    'Scripts/mac_owned_crash.py',
    'Scripts/original_ios_archive.py',
    'Scripts/original_ios_fixed_rows.py',
    'Scripts/original_ios_rows.py',
    'Scripts/staged_test_fixtures.py',
    'Scripts/test_original_ios_archive.py',
    'Scripts/test_original_ios_diagnostic_ownership.py',
    'Scripts/test_original_ios_fixed_rows.py',
    'Scripts/test_original_ios_optional_process_contract.py',
    'Scripts/test_original_ios_route.py',
    'Scripts/test_original_ios_supervision_integration.py',
    'Scripts/uikit_full_shipping_handoff.py',
    'Scripts/validation_route.py',
    'Scripts/verify_combined_source.py',
}
ORIGINAL_IOS_FIRST_SUMMARY_PATHS={
    '.github/workflows/original-ios-release.yml',
    'Documentation/original-ios-release.md',
    'Scripts/collect_native_evidence.py',
    'Scripts/original_ios_archive.py',
    'Scripts/original_ios_first_summary.py',
    'Scripts/original_ios_fixed_rows.py',
    'Scripts/original_ios_rows.py',
    'Scripts/run_bounded.py',
    'Scripts/test_original_ios_archive.py',
    'Scripts/test_original_ios_first_summary.py',
    'Scripts/test_original_ios_rows.py',
    'Scripts/test_original_ios_fixed_rows.py',
    'Scripts/test_original_ios_route.py',
    'Scripts/uikit_full_shipping_handoff.py',
    'Scripts/validation_route.py',
    'Scripts/verify_combined_source.py',
}
ORIGINAL_IOS_REPAIR_PATHS={
    '.github/workflows/original-ios-release.yml',
    'Celluloid/Controller/EntranceViewController.swift',
    'Celluloid/en.lproj/Localizable.strings',
    'Celluloid/zh-Hans.lproj/Localizable.strings',
    'CelluloidTests/EditorRegressionTests.swift',
    'CelluloidUITests/CelluloidUITests.swift',
    'Documentation/original-ios-release.md',
    'Scripts/collect_native_evidence.py',
    'Scripts/collect_simulator_diagnostics.py',
    'Scripts/export_permission_screenshot.py',
    'Scripts/native_process.py',
    'Scripts/original-ios-source-contract.json',
    'Scripts/original_ios_process_guard.py',
    'Scripts/original_ios_source_contract.py',
    'Scripts/probe_photos_bootstrap.py',
    'Scripts/run_bounded.py',
    'Scripts/stage_uikit_layer_fixture.py',
    'Scripts/test_original_ios_diagnostic_ownership.py',
    'Scripts/test_original_ios_process_guard.py',
    'Scripts/test_original_ios_route.py',
    'Scripts/test_original_ios_source_contract.py',
    'Scripts/test_original_ios_supervision_integration.py',
    'Scripts/uikit_full_shipping_gate.py',
    'Scripts/uikit_full_shipping_handoff.py',
    'Scripts/validation_route.py',
    'Scripts/verify_combined_source.py',
}
# Explicit final reviewed path inventory is frozen with this candidate.
ORIGINAL_IOS_PATHS={
    '.github/workflows/original-ios-release.yml',
    'Celluloid.xcodeproj/project.pbxproj',
    'Celluloid.xcodeproj/xcshareddata/xcschemes/CelluloidCompanion.xcscheme',
    'Celluloid/AppDelegate.swift',
    'Celluloid/Controller/EntranceViewController.swift',
    'Documentation/original-ios-release.md',
    'Scripts/collect_native_evidence.py',
    'Scripts/generate_project.py',
    'Scripts/original-ios-source-contract.json',
    'Scripts/original_ios_archive.py',
    'Scripts/original_ios_rows.py',
    'Scripts/original_ios_source_contract.py',
    'Scripts/probe_photos_bootstrap.py',
    'Scripts/staged_test_fixtures.py',
    'Scripts/test_early_uikit_interop.py',
    'Scripts/test_mac_photos_host_gate.py',
    'Scripts/test_original_ios_archive.py',
    'Scripts/test_original_ios_route.py',
    'Scripts/test_original_ios_rows.py',
    'Scripts/test_original_ios_source_contract.py',
    'Scripts/test_photos_export_observation.py',
    'Scripts/test_uikit_full_shipping_workflow.py',
    'Scripts/uikit_full_shipping_handoff.py',
    'Scripts/validation_route.py',
    'Scripts/verify_combined_source.py',
}

HOST_ONLY={'scope':'photos-export-observation','branch':'codex/photos-export-observation','workflow_path':'.github/workflows/photos-export-observation.yml','diagnostic_only':True}
HOST_ONLY_BASE={'commit':'25b8edc92c3f53cf13208ffa0065746b87ae20e0','tree':'7622774f3291c7b32f46966bebffddd645e57326','fingerprint':'d395f03291d06dc09f0d561b2096fd0bfe32b63f08764753c9d1b31a1069c88b'}
HOST_ONLY_PROTECTED_FINGERPRINT='c1d88b1bafe0ef55c838e28eccb606d0b7e4701d792d88399f8b03ecc40f984b'
HOST_ONLY_UI_TEST={'path':'Platforms/UITests/MacPhotosHostUITests.swift','sha256':'67bdca402040600b35a2e452a13049b4a44bd55df797596a32e8c460e9eb4fb0'}

def require(ok,message):
    if not ok:raise ValueError(message)

def validate_route(value):
    require(type(value) is dict and set(value)==set(FULL) and type(value.get('diagnostic_only')) is bool,'Malformed validation route')
    require(value==FULL or value==FOCUSED or value==HOST_ONLY or value==UIKIT_FULL or value==ORIGINAL_IOS,'Unknown validation route')
    return dict(value)

def current_route(environment=None):
    env=os.environ if environment is None else environment
    ref=env.get('GITHUB_REF')
    if ref=='refs/heads/'+FULL['branch']:
        # Preserve canonical admission; a caller flag cannot relabel this branch.
        return dict(FULL)
    selected=next((value for value in (FOCUSED,HOST_ONLY,UIKIT_FULL,ORIGINAL_IOS) if ref=='refs/heads/'+value['branch']),None)
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


def host_clock_profile(route):
    """Two fixed reviewed allocations, not caller-selectable timeout values."""
    if validate_route(route)==HOST_ONLY:
        return {'name':'photos-export-observation-900-v1','case_seconds':900,'test_seconds':960,
            'process_seconds':1020,'pretest_seconds':240,'tail_seconds':360,'step_margin_seconds':60,
            'step_seconds':1680,'before_prepare_seconds':1980,'before_host_seconds':1740,'evidence_seconds':300}
    return {'name':'canonical-600-v1','case_seconds':600,'test_seconds':660,
        'process_seconds':720,'pretest_seconds':0,'tail_seconds':0,'step_margin_seconds':0,
        'step_seconds':840,'before_prepare_seconds':1020,'before_host_seconds':1020,'evidence_seconds':300}

def context_clock(context):
    expected=host_clock_profile(context['validation_route'])
    require(context.get('host_clock_profile')==expected and type(context.get('host_clock_profile')) is dict
            and all(type(context['host_clock_profile'][k]) is type(v) for k,v in expected.items()),'Wrong source-bound host clock profile')
    return expected
