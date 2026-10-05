#!/usr/bin/env python3
"""Credential-free, ephemeral actual Photos-host prerequisite evidence.

No Photos database, plugin election, TCC, security preference, or Apple account
mutation. A successful prerequisite is deliberately not a complete E2E result.
"""
from pathlib import Path
import argparse
import base64
import ctypes
import hashlib
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import math
from mac_host_transport import load_json,HOST_CONTRACT

# Mandatory acceptance/source/product assertions must never be optimized away.
# Reject before parsing an action, reading receipts, or creating any evidence.
if not __debug__ or sys.flags.optimize != 0:
    raise RuntimeError('Mac Photos host gate refuses optimized Python; assertions must remain enabled')

ROOT = Path(__file__).resolve().parents[1]
BASE = '9c9e7fc9c12df342c883e8a1e4462f796469842c'
BASE_TREE = 'f53aa262fb56d31cd0b2f03f3836147c26ff2858'
BRANCH = 'codex/apple-platforms'
APP_ID = 'Mango.Celluloid'
EXT_ID = APP_ID + '.CelluloidPhotoExtension'
ALLOWED = {
    '.github/workflows/apple-platforms.yml',
    'CelluloidNative.xcodeproj/project.pbxproj',
    'CelluloidTests/MacPhotosManufacturedAdjustmentTests.swift',
    'Documentation/interop-continuation.md',
    'Documentation/mac-photos-host-gate.md',
    'Documentation/platform-rendering-contract.md',
    'Platforms/MacExtensionTests/MacPhotoAdjustmentTests.swift',
    'Platforms/MacExtensionTests/MacPhotoRendererTests.swift',
    'Platforms/PhoneUITests/PhoneCompanionUITests.swift',
    'Platforms/TVUITests/NativeTVUITests.swift',
    'Platforms/UITests/MacPhotosHostUITests.swift',
    'Platforms/UITests/NativeEditorUITests.swift',
    'Platforms/WatchUITests/NativeWatchUITests.swift',
    'Platforms/macOSExtension/MacPhotoRenderer.swift',
    'Platforms/tvOS/CelluloidTVApp.swift',
    'Scripts/collect_native_evidence.py',
    'Scripts/combined-source-contract.json',
    'Scripts/combined_evidence_budget.py',
    'Scripts/consumer_runtime_binding.py',
    'Scripts/file_open_observation.py',
    'Scripts/fixtures/archive-ordering-witness.json',
    'Scripts/fixtures/native-text-expectations.json',
    'Scripts/fixtures/platform-rendering-controls.json',
    'Scripts/mac-photos-host-source-base.json',
    'Scripts/keyed_archive_graph.py',
    'Scripts/mac_host_transport.py',
    'Scripts/mac_photos_host_gate.py',
    'Scripts/native_text_release_guard.py',
    'Scripts/optional_export_budget.py',
    'Scripts/platform_rendering_contract.py',
    'Scripts/run_early_uikit_interop.py',
    'Scripts/run_mac_photos_host_gate.sh',
    'Scripts/stage_uikit_layer_fixture.py',
    'Scripts/test_combined_preflight.py',
    'Scripts/test_combined_validation.py',
    'Scripts/test_consumer_runtime_binding.py',
    'Scripts/test_early_uikit_interop.py',
    'Scripts/test_file_open_observation.py',
    'Scripts/test_interop_continuation.py',
    'Scripts/test_keyed_archive_graph.py',
    'Scripts/test_mac_host_transport.py',
    'Scripts/test_mac_photos_host_gate.py',
    'Scripts/test_native_evidence.py',
    'Scripts/test_native_phone_fixture.py',
    'Scripts/test_native_watch_profiles.py',
    'Scripts/test_optional_export_budget.py',
    'Scripts/test_platform_rendering_contract.py',
    'Scripts/test_text_observation_evidence.py',
    'Scripts/test_uikit_installed_identity.py',
    'Scripts/text_observation_evidence.py',
    'Scripts/uikit_installed_identity.py',
    'Scripts/verify_interop_continuation.py',
    'Scripts/verify_native_release.py',
    'Scripts/verify_required_interoperability.py',
}

CAP = 1_000_000
BASE_FILE_COUNT = 544
REVIEWED_TEST_FILES = {'CelluloidTests/MacPhotosManufacturedAdjustmentTests.swift': 'f4c7a7a16bf5414e6c2a2716bc146bdc216f7ea966a80207acce8a7667584890', 'Platforms/MacExtensionTests/MacPhotoAdjustmentTests.swift': 'ec2e5f8d1e794ffbfcef4be15f34ed6b3d02bbdeae2b722d8c08ce0a9ccb7034'}
REVIEWED_CANDIDATE_FILES = {'Platforms/MacExtensionTests/MacPhotoRendererTests.swift': '00b65848c3da2486b58c3cf4fd1e4c48e0e45fe9bb543590ecc1475e065e2c36', 'Platforms/PhoneUITests/PhoneCompanionUITests.swift': 'c6bd4a670bc2b84eb8f7f2f69c49b07213b628dcb0779d8147afbf6e483fcdb0', 'Platforms/TVUITests/NativeTVUITests.swift': '80d914d55ebbcba90eea15453036175d40b6130120c5f80ba5e1693e02b09276', 'Platforms/WatchUITests/NativeWatchUITests.swift': '7faddc48f25ad4ae6899d77055f83255dabbd9b7836a7691a57db6e8073b60ca', 'Platforms/macOSExtension/MacPhotoRenderer.swift': 'ba3199901afda2065323e67ba53ad27cd3cd95d047c81508c5045ad177993b58', 'Platforms/tvOS/CelluloidTVApp.swift': '86d7fd7dcfc6f40d256c7b3022c7b02525f0713ae04fffe14b47b5335cc35f3f'}
UNCHANGED_BASE_FILES = BASE_FILE_COUNT - 2 - len(REVIEWED_TEST_FILES) - len(REVIEWED_CANDIDATE_FILES)

def run(*args):
    return subprocess.check_output(args, cwd=ROOT, text=True, stderr=subprocess.STDOUT, timeout=20).strip()

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write(path, data):
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')

def temp():
    p = Path(os.environ['RUNNER_TEMP']).resolve()
    assert p.is_dir() and str(p) != '/'
    return p

def require_runner():
    assert sys.platform == 'darwin'
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    assert os.environ['GITHUB_REPOSITORY'] == '100mango/Celluloid'
    assert os.environ['GITHUB_REF'] == 'refs/heads/' + BRANCH
    assert os.environ['GITHUB_EVENT_NAME'] == 'push'
    assert os.environ['DEVELOPER_DIR'] == '/Applications/Xcode_27.app/Contents/Developer'

def verify_source(phase):
    expected = os.environ['GITHUB_SHA']
    assert run('git', 'rev-parse', 'HEAD') == expected == os.environ['GITHUB_WORKFLOW_SHA']
    assert not run('git', 'status', '--porcelain', '--untracked-files=all'), 'Changed checkout'
    assert run('git', 'rev-parse', BASE + '^{tree}') == BASE_TREE
    changed = set(run('git', 'diff', '--name-only', BASE, 'HEAD').splitlines())
    assert changed <= ALLOWED, sorted(changed - ALLOWED)
    frozen = ROOT / 'Scripts/mac-photos-host-source-base.json'
    assert frozen.read_bytes() == subprocess.check_output(['git', 'show', BASE + ':Scripts/combined-source-contract.json'], cwd=ROOT, timeout=20), 'Frozen base snapshot differs from the actual base commit'
    contract = load_json(frozen.read_text())
    checked = []
    for path, digest in contract['files']:
        if path in {'CelluloidNative.xcodeproj/project.pbxproj', 'Platforms/UITests/NativeEditorUITests.swift'}:
            continue
        if path in REVIEWED_CANDIDATE_FILES:
            assert sha(ROOT/path)==REVIEWED_CANDIDATE_FILES[path], 'Reviewed candidate source changed: '+path
            continue
        if path in REVIEWED_TEST_FILES:
            assert sha(ROOT/path)==REVIEWED_TEST_FILES[path], 'Reviewed diagnostic test changed: '+path
            continue
        assert sha(ROOT / path) == digest, 'Base source changed: ' + path
        checked.append([path, digest])
    report = {'phase': phase, 'source_sha': expected, 'tree': run('git', 'rev-parse', 'HEAD^{tree}'),
              'base_sha': BASE, 'base_tree': BASE_TREE, 'unchanged_bound_files': len(checked), 'reviewed_diagnostic_test_files': REVIEWED_TEST_FILES, 'reviewed_candidate_files': REVIEWED_CANDIDATE_FILES,
              'allowed_changed_paths': sorted(changed), 'workflow_sha256': sha(ROOT / '.github/workflows/apple-platforms.yml'),
              'complete_host_e2e': False}
    write(temp() / ('mac-host-source-' + phase + '.json'), report)
    print(json.dumps(report, sort_keys=True))

def entitlement(path):
    data = subprocess.run(['/usr/bin/codesign', '-d', '--entitlements', ':-', str(path)], check=True,
                          capture_output=True, timeout=20).stdout
    return plistlib.loads(data)

def bundle_manifest(path):
    result = []
    for p in sorted(path.rglob('*')):
        if p.is_symlink():
            result.append([str(p.relative_to(path)), 'symlink', os.readlink(p)])
        elif p.is_file():
            result.append([str(p.relative_to(path)), p.stat().st_size, sha(p)])
    return result

SEED_CASE = ('CelluloidMacUITests.NativeEditorUITests', 'testRealPhotosLibraryImportAndSystemPicker')

def seed_receipt(path, source_sha, app_hash):
    path = Path(path)
    if not path.exists(): return {'mode': 'require-empty-library'}
    assert not path.is_symlink() and path.stat().st_size <= 20_000_000
    text = path.read_text()
    rows = [load_json(line.split('MAC_HOST_SEED_RECEIPT ', 1)[1]) for line in text.splitlines() if line.startswith('MAC_HOST_SEED_RECEIPT ')]
    events = [row for row in CASE_RESULT.findall(text) if row[:2] == SEED_CASE]
    if not events and not rows: return {'mode': 'require-empty-library'}
    assert events == [(*SEED_CASE, 'started'), (*SEED_CASE, 'passed')], 'Seed test did not pass exactly once'
    assert len(rows) == 1, 'Missing/duplicate source-bound seed receipt'
    row = rows[0]
    assert row['source_sha'] == source_sha and row['app_executable_sha256'] == app_hash
    assert row['initial_empty_welcome_verified'] is True and row['imported_pixel_samples_passed'] is True
    assert type(row['initial_count']) is int and row['initial_count'] == 0
    assert type(row['imported_count']) is int and row['imported_count'] == 1
    assert row['fixture_kind'] == 'native-ui-solid-blue' and row['filename'] == 'Synthetic.png'
    assert (row['width'], row['height']) == (1200, 800)
    assert isinstance(row['asset_label'], str) and 0 < len(row['asset_label']) <= 300
    data = base64.b64decode(row['fixture_base64'], validate=True)
    assert 0 < len(data) <= 150_000 and hashlib.sha256(data).hexdigest() == row['fixture_sha256']
    assert data[:8] == b'\x89PNG\r\n\x1a\n' and data[12:16] == b'IHDR'
    assert int.from_bytes(data[16:20], 'big') == 1200 and int.from_bytes(data[20:24], 'big') == 800
    assert re.fullmatch(r'[0-9a-f]{64}', row['imported_source_sha256'])
    return dict(row, mode='reuse-exact-sole-seeded-asset', seed_log_sha256=sha(path))

def prepare():
    require_runner()
    source = temp() / 'celluloid-sandbox/Build/Products/Debug/CelluloidMac.app'
    child = source / 'Contents/PlugIns/CelluloidMacPhotosExtension.appex'
    app_permissions = {'com.apple.security.app-sandbox': True,
                       'com.apple.security.files.user-selected.read-write': True,
                       'com.apple.security.get-task-allow': True}
    ext_permissions = {'com.apple.security.app-sandbox': True}
    for bundle, identity, permissions in [(source, APP_ID, app_permissions), (child, EXT_ID, ext_permissions)]:
        info = plistlib.loads((bundle / 'Contents/Info.plist').read_bytes())
        assert info['CFBundleIdentifier'] == identity
        assert entitlement(bundle) == permissions, (identity, entitlement(bundle))
        run('/usr/bin/codesign', '--verify', '--strict', '--deep', str(bundle))
    # Reuse the exact already signed same-job app. Copying a second same-ID
    # app after ordinary UI launch would make runtime product identity ambiguous.
    debug_permissions = app_permissions
    installed = source
    embedded = installed / 'Contents/PlugIns/CelluloidMacPhotosExtension.appex'
    for bundle, permissions in [(installed, debug_permissions), (embedded, ext_permissions)]:
        run('/usr/bin/codesign', '--verify', '--strict', '--deep', str(bundle))
        assert entitlement(bundle) == permissions
    evidence = temp() / 'mac-host-observed'
    evidence.mkdir(exist_ok=False)
    context = {'host_entry_contract':HOST_CONTRACT, 'source_sha': os.environ['GITHUB_SHA'], 'base_sha': BASE, 'app_path': str(installed),
               'extension_path': str(embedded), 'app_executable': str(installed / 'Contents/MacOS/CelluloidMac'),
               'extension_executable': str(embedded / 'Contents/MacOS/CelluloidMacPhotosExtension'),
               'app_id': APP_ID, 'extension_id': EXT_ID, 'evidence_path': str(evidence),
               'script_path': str(Path(__file__).resolve()), 'script_sha256': sha(__file__),
               'test_source_path': str(ROOT/'Platforms/UITests/MacPhotosHostUITests.swift'),
               'test_source_sha256': sha(ROOT/'Platforms/UITests/MacPhotosHostUITests.swift'),
               'app_entitlements': debug_permissions, 'extension_entitlements': ext_permissions,
               'bundle_manifest': bundle_manifest(installed), 'complete_host_e2e': False,
               'installation_method': 'reuse exact same-job sandbox product without copy or re-sign',
               'runner_environment': {key: os.environ[key] for key in ['RUNNER_TEMP', 'GITHUB_SHA', 'GITHUB_WORKFLOW_SHA',
                   'GITHUB_ACTIONS', 'GITHUB_REPOSITORY', 'GITHUB_REF', 'GITHUB_EVENT_NAME', 'DEVELOPER_DIR']}}
    context['app_executable_sha256'] = sha(context['app_executable'])
    context['seed'] = seed_receipt(temp() / 'sandbox.log', context['source_sha'], context['app_executable_sha256'])
    context['extension_executable_sha256'] = sha(context['extension_executable'])
    write(temp() / 'mac-host-context.json', context)
    print('MAC_HOST_INSTALLED ' + json.dumps({k: v for k, v in context.items() if k != 'bundle_manifest'}, sort_keys=True))

def context():
    p = temp() / 'mac-host-context.json'
    c = load_json(p.read_text())
    assert c['host_entry_contract']==HOST_CONTRACT
    assert c['source_sha'] == os.environ['GITHUB_SHA']
    assert c['app_id'] == APP_ID and c['extension_id'] == EXT_ID
    assert c['script_sha256'] == sha(__file__)
    return c

def verify_product():
    require_runner()
    c = context()
    app = Path(c['app_path'])
    assert bundle_manifest(app) == c['bundle_manifest'], 'Installed bytes changed'
    for key in ['app', 'extension']:
        bundle = Path(c[key + '_path'])
        run('/usr/bin/codesign', '--verify', '--strict', '--deep', str(bundle))
        assert entitlement(bundle) == c[key + '_entitlements']
    result = {'installed_bytes_unchanged': True, 'strict_signatures_unchanged': True,
              'app_executable_sha256': sha(c['app_executable']),
              'extension_executable_sha256': sha(c['extension_executable'])}
    write(temp() / 'mac-host-product-after.json', result)
    print(json.dumps(result, sort_keys=True))

def process_provenance():
    # Called read-only while Photos has its real editor open. Match actual process
    # executable paths, never process display name or the extension menu label.
    require_runner()
    c = context()
    lib = ctypes.CDLL('/usr/lib/libproc.dylib')
    lib.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    lib.proc_pidpath.restype = ctypes.c_int
    found = []
    for token in run('/bin/ps', '-axo', 'pid=').split():
        pid = int(token)
        buffer = ctypes.create_string_buffer(4096)
        if lib.proc_pidpath(pid, buffer, len(buffer)) <= 0:
            continue
        path = buffer.value.decode('utf-8', errors='strict')
        if Path(path).name == 'CelluloidMacPhotosExtension':
            actual = str(Path(path).resolve())
            found.append({'pid': pid, 'executable': actual, 'sha256': sha(actual)})
    expected = str(Path(c['extension_executable']).resolve())
    result = {'source_sha': c['source_sha'], 'extension_id': EXT_ID,
              'extension_processes': found, 'expected_executable': expected,
              'expected_executable_sha256': c['extension_executable_sha256'],
              'unique_exact_process': len(found) == 1 and found[0]['executable'] == expected
              and found[0]['sha256'] == c['extension_executable_sha256']}
    # This process inherits the XCTest sandbox. Return the actual live-process
    # receipt through stdout; only the outer runner may materialize evidence.
    print(json.dumps(result, sort_keys=True))
    assert result['unique_exact_process'], 'Missing or ambiguous actual extension executable'

EXPECTED_CASE = ('CelluloidMacUITests.MacPhotosHostUITests', 'testInstalledExtensionIsInvokedByActualPhotos')
CASE_RESULT = re.compile(r"^Test Case '-\[([\w.]+) (\w+)\]' (started|passed|failed|skipped)\b", re.M)

def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key: ' + key)
        result[key] = value
    return result

def read_receipt(path):
    path = Path(path)
    assert path.is_file() and not path.is_symlink(), 'Missing/invalid receipt: ' + path.name
    assert 0 < path.stat().st_size <= 2_000_000, 'Receipt size: ' + path.name
    result = load_json(path.read_text())
    assert isinstance(result, dict), 'Receipt must be an object: ' + path.name
    return result

def transport_records(root, c, complete=False):
    from mac_host_transport import parse
    root=Path(root)
    assert c['source_sha']==os.environ.get('GITHUB_SHA',c['source_sha'])
    assert c['script_sha256']==sha(__file__)
    assert c['test_source_sha256']==sha(ROOT/'Platforms/UITests/MacPhotosHostUITests.swift'), 'Changed actual host test source'
    path=root/'mac-host-test.log'
    assert path.is_file() and not path.is_symlink() and path.stat().st_size<=20_000_000
    return parse(path.read_text(),c,sha(root/'mac-host-context.json'),complete=complete)

def transport_report(root, c, records):
    return {'schema':'Celluloid.HostTransportReplay.2','host_entry_contract':HOST_CONTRACT,'source_sha':c['source_sha'],
        'context_sha256':sha(Path(root)/'mac-host-context.json'), 'test_source_sha256':c['test_source_sha256'],
        'transcript_sha256':sha(Path(root)/'mac-host-test.log'),
        'records':[{'name':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()} for name,data in records.items()],
        'complete_host_e2e':False}

def extract_transport():
    require_runner()
    root=temp();c=context();records=transport_records(root,c)
    observed=root/'mac-host-observed'
    assert observed.is_dir() and not observed.is_symlink()
    # The allowlisted parser returns names, never reported output paths.
    for name,data in records.items():
        target=observed/name
        assert not target.exists() and not target.is_symlink(), 'Duplicate materialized host proof'
        target.write_bytes(data)
    # Attachments are diagnostic only, but their namespace and export ownership
    # are strict. A malformed selected attachment is never silently accepted.
    from mac_host_transport import attachment_candidates
    with tempfile.TemporaryDirectory(prefix='celluloid-host-attachments-',dir=root) as folder:
        folder=Path(folder)
        exported=subprocess.run(['xcrun','xcresulttool','export','attachments','--path',str(root/'MacPhotosHost.xcresult'),'--output-path',str(folder)],capture_output=True,timeout=60)
        assert exported.returncode==0, 'Required bounded host attachment export failed'
        manifest=folder/'manifest.json'
        assert manifest.is_file() and not manifest.is_symlink() and manifest.stat().st_size<=200_000
        raw=manifest.read_bytes(); parsed=None
        try:
            parsed=load_json(raw)
            diagnostics=attachment_candidates(folder,parsed)
        except (AssertionError,ValueError,UnicodeError) as error:
            # Metadata only, never an alternate attachment-matching path. Keep
            # the original error and raw manifest identity under the same cap.
            rows=[]; count=0
            for record in parsed if type(parsed) is list else []:
                if type(record) is not dict:continue
                for item in record.get('attachments',[]) if type(record.get('attachments')) is list else []:
                    count+=1
                    if len(rows)<16 and type(item) is dict:
                        rows.append({key:str(value)[:160] for key,value in {
                            'testIdentifier':record.get('testIdentifier'),
                            'suggestedHumanReadableName':item.get('suggestedHumanReadableName'),
                            'exportedFileName':item.get('exportedFileName')}.items()})
            failure={'schema':'Celluloid.HostAttachmentFailure.1','acceptance':False,
                'source_sha':c['source_sha'],'context_sha256':sha(root/'mac-host-context.json'),
                'manifest_sha256':hashlib.sha256(raw).hexdigest(),
                'error':type(error).__name__+': '+str(error)[:1000],
                'metadata_field_limit':160,'attachment_count':count,'retained_first_items':rows,
                'omitted_items':count-len(rows)}
            target=observed/'attachment-export-failure.json'
            if not target.exists() and not target.is_symlink():
                data=(json.dumps(failure,sort_keys=True)+'\n').encode()
                if len(data)>16_000:
                    failure.update(retained_first_items=[],omitted_items=count)
                    data=(json.dumps(failure,sort_keys=True)+'\n').encode()
                try:
                    if len(data)<=16_000:target.write_bytes(data)
                except OSError:pass  # Optional retention cannot replace the original failure.
            raise
        for name,data in diagnostics.items():
            target=observed/name
            assert not target.exists() and not target.is_symlink(), 'Attachment collides with a host receipt'
            target.write_bytes(data)
    # Publish the mandatory transport completion only after the actual export
    # finished and every selected name/path/type/size was validated.
    write(root/'mac-host-transport-replay.json',transport_report(root,c,records))

def validate_host_ui(selection,before,after,photos,ownership,source_sha):
    common={'schema','host_entry_contract','source_sha','photos_pid','photos_bundle','photos_executable','fixture_sha256','asset_label'}
    selection_keys={'menu_title','menu_identifier','menu_scope','extension_menu_button_count','opened_menu_count','menu_count','menu_enabled','menu_hittable','editor_count_before'}
    editor_keys={'phase','editor_label','editor_count','preview_label','preview_count','placeholder_count','preparing_count','filter_identifier','filter_count','filter_enabled','read_only_count','error_count'}
    for name,row,keys,schema in [('selection',selection,selection_keys,'Celluloid.HostSelection.3'),('before',before,editor_keys,'Celluloid.HostEditor.2'),('after',after,editor_keys,'Celluloid.HostEditor.2')]:
        assert type(row) is dict and set(row)==common|keys, 'Unknown/missing host UI receipt: '+name
        assert row['schema']==schema and row['host_entry_contract']==HOST_CONTRACT
        assert row['source_sha']==source_sha
        assert type(row['photos_pid']) is int and row['photos_pid']==photos['pid'] and row['photos_pid']>0
        assert row['photos_bundle']==photos['bundle']=='/System/Applications/Photos.app'
        assert row['photos_executable']==photos['executable']=='/System/Applications/Photos.app/Contents/MacOS/Photos'
        assert row['fixture_sha256']==ownership['fixture_sha256'] and row['asset_label']==ownership['asset_label']
    assert selection['menu_title']=='Celluloid' and selection['menu_identifier']=='editWithPlugin:'
    assert selection['menu_scope']=='Extensions.menuButton/childMenu/directMenuItem'
    for key,wanted in [('menu_count',1),('editor_count_before',0),('extension_menu_button_count',1),('opened_menu_count',1)]:assert type(selection[key]) is int and selection[key]==wanted
    assert selection['menu_enabled'] is True and selection['menu_hittable'] is True
    for phase,row in [('before-process',before),('after-process',after)]:
        assert row['phase']==phase and row['editor_label']=='Celluloid photo editor' and row['preview_label']=='Edited photo preview'
        assert row['filter_identifier']=='photos-extension.filter' and row['filter_enabled'] is True
        for key,wanted in [('editor_count',1),('preview_count',1),('placeholder_count',0),('preparing_count',0),('filter_count',1),('read_only_count',0),('error_count',0)]:
            assert type(row[key]) is int and row[key]==wanted, 'Unready/ambiguous host editor: '+key

def verify_acceptance(root, source_sha):
    """Require finalized XCTest execution plus same-candidate live-host receipts.

    This is pure read-only validation and returns no complete-E2E claim. A log
    marker or a successful source/product check alone can never admit this gate.
    """
    root = Path(root)
    observed = root / 'mac-host-observed'
    budget_report=read_receipt(root/'mac-host-budget.json')
    clock=read_receipt(root/'mac-job-clock.json')
    validate_budget(budget_report,clock,source_sha,complete=True)
    assert budget_report['clock_sha256']==sha(root/'mac-job-clock.json')
    c = read_receipt(root / 'mac-host-context.json')
    assert re.fullmatch(r'[0-9a-f]{40}', source_sha), 'Invalid candidate identity'
    assert c['host_entry_contract']==HOST_CONTRACT
    assert c['source_sha'] == source_sha and c['base_sha'] == BASE
    assert c['app_id'] == APP_ID and c['extension_id'] == EXT_ID
    assert c['complete_host_e2e'] is False
    assert c['script_sha256'] == sha(__file__), 'Wrong verifier/product context'
    records=transport_records(root,c,complete=True)
    assert read_receipt(root/'mac-host-transport-replay.json')==transport_report(root,c,records), 'Transport replay receipt changed'
    for name,data in records.items():
        path=observed/name
        assert path.is_file() and not path.is_symlink() and path.read_bytes()==data, 'Materialized host receipt differs from actual XCTest stdout: '+name
    expected_extension = str(Path(c['extension_path']).resolve())
    expected_executable = str(Path(c['extension_executable']).resolve())
    assert expected_extension == str(Path(c['app_path']).resolve() / 'Contents/PlugIns/CelluloidMacPhotosExtension.appex')
    assert expected_executable == str(Path(expected_extension) / 'Contents/MacOS/CelluloidMacPhotosExtension')
    assert re.fullmatch(r'[0-9a-f]{64}', c['extension_executable_sha256'])

    summary = read_receipt(root / 'mac-host-summary.json')
    assert summary['result'] == 'Passed', 'Finalized XCTest result is not Passed'
    counts = {'totalTestCount': 1, 'passedTests': 1, 'failedTests': 0, 'skippedTests': 0, 'expectedFailures': 0}
    for key, expected in counts.items():
        assert type(summary[key]) is int and summary[key] == expected, 'Finalized XCTest count: ' + key
    assert summary['finishTime'] > summary['startTime'] > 0, 'Result is not finalized'
    assert not summary.get('testFailures'), 'Contradictory XCTest failure detail'
    configurations = summary['devicesAndConfigurations']
    assert isinstance(configurations, list) and len(configurations) == 1, 'Duplicate/wrong test configurations'
    configuration = configurations[0]
    for key in ['passedTests', 'failedTests', 'skippedTests', 'expectedFailures']:
        assert type(configuration[key]) is int and configuration[key] == counts[key], 'Contradictory device count: ' + key
    assert configuration['device']['platform'] == 'macOS'
    assert configuration['device']['osVersion'].startswith('27.')
    log_path = root / 'mac-host-test.log'
    assert log_path.is_file() and not log_path.is_symlink() and log_path.stat().st_size <= 20_000_000
    log = log_path.read_text(errors='strict')
    executions = CASE_RESULT.findall(log)
    assert executions == [(*EXPECTED_CASE, 'started'), (*EXPECTED_CASE, 'passed')], 'Missing/wrong/duplicate/skipped testcase: ' + repr(executions)
    assert sum(line.startswith('MAC_HOST_PREREQUISITE_PASSED ') for line in log.splitlines()) == 1, 'Missing/duplicate host-entry completion marker'
    assert 'MAC_HOST_BLOCKED' not in log and 'MAC_HOST_FAIL_CLOSED_ABORT' not in log, 'Contradictory host interruption/failure'

    containing=read_receipt(observed/'containing-process.json')
    assert containing['bundle']==str(Path(c['app_path']).resolve()) and containing['executable']==c['app_executable']
    assert type(containing['pid']) is int and containing['pid']>0
    photos=read_receipt(observed/'photos-process.json')
    assert photos['bundle']=='/System/Applications/Photos.app'
    assert photos['executable']=='/System/Applications/Photos.app/Contents/MacOS/Photos'
    assert type(photos['pid']) is int and photos['pid']>0

    ownership = read_receipt(observed / 'fixture-ownership.json')
    assert ownership['source_sha'] == source_sha
    assert ownership['app_executable_sha256'] == c['app_executable_sha256']
    assert type(ownership['initial_count']) is int and ownership['initial_count'] == 0
    assert type(ownership['selected_count']) is int and ownership['selected_count'] == 1
    assert (ownership['width'], ownership['height']) == (1200, 800)
    assert isinstance(ownership['asset_label'], str) and bool(ownership['asset_label'])
    assert re.fullmatch(r'[0-9a-f]{64}', ownership['fixture_sha256'])
    fixture = read_receipt(observed / 'fixture.json')
    assert fixture['source_sha'] == source_sha
    assert ownership['mode'] == c['seed']['mode']
    if c['seed']['mode'] == 'reuse-exact-sole-seeded-asset':
        assert ownership['fixture_sha256'] == c['seed']['fixture_sha256']
        assert ownership['asset_label'] == c['seed']['asset_label']
    else:
        assert c['seed']['mode'] == 'require-empty-library'
        fixture = read_receipt(observed / 'fixture.json')
        assert ownership['fixture_sha256'] == fixture['sha256']
    prerequisite = read_receipt(observed / 'prerequisite.json')
    outcome = read_receipt(observed / 'outcome.json')
    selection=read_receipt(observed/'host-selection.json')
    editor_before=read_receipt(observed/'host-editor-before-process.json')
    editor_after=read_receipt(observed/'host-editor-after-process.json')
    validate_host_ui(selection,editor_before,editor_after,photos,ownership,source_sha)
    menu=outcome.get('extension_menu_observation')
    assert type(menu) is dict and set(menu)=={'schema','acceptance','menu_title','menu_identifier','menu_scope','extension_menu_button_count','opened_menu_count','menu_count','menu_enabled','menu_hittable','classification'}, 'Missing/malformed outcome menu observation'
    assert menu['schema']=='Celluloid.HostMenuObservation.2' and menu['acceptance'] is False
    assert type(menu['menu_count']) is int and menu['menu_count']==selection['menu_count']==1
    assert menu['menu_enabled'] is True and menu['menu_hittable'] is True
    assert menu['menu_identifier']==selection['menu_identifier']=='editWithPlugin:' and menu['menu_scope']==selection['menu_scope']=='Extensions.menuButton/childMenu/directMenuItem'
    for key in ['extension_menu_button_count','opened_menu_count']:assert type(menu[key]) is int and menu[key]==selection[key]==1
    assert menu['menu_title']==selection['menu_title']=='Celluloid' and menu['classification']=='selectable', 'Contradictory outcome menu observation'
    process = read_receipt(observed / 'extension-process.json')
    for name, receipt in [('prerequisite', prerequisite), ('outcome', outcome), ('process', process)]:
        assert receipt['source_sha'] == source_sha, 'Wrong candidate: ' + name
    assert prerequisite['host_entry_contract']==outcome['host_entry_contract']==HOST_CONTRACT
    assert prerequisite['prerequisite_passed'] is True
    assert prerequisite['complete_host_e2e'] is False
    assert prerequisite['production_source_base'] == BASE
    assert outcome['complete_host_e2e'] is False
    assert 'first_blocked_operation' not in outcome, 'A blocked operation cannot grant host-entry acceptance'
    assert outcome['last_stage'] == 'host-entry-prerequisite-passed', 'Host did not reach final prerequisite stage'
    assert outcome['save_reopen_cancel_revert'] == 'not executed in prerequisite phase'
    assert process['extension_id']==EXT_ID
    assert process['unique_exact_process'] is True
    assert process['expected_executable'] == expected_executable
    assert process['expected_executable_sha256'] == c['extension_executable_sha256']
    processes = process['extension_processes']
    assert isinstance(processes, list) and len(processes) == 1, 'Missing/duplicate running extension'
    actual = processes[0]
    assert type(actual['pid']) is int and actual['pid'] > 0
    assert actual['executable'] == expected_executable and actual['sha256'] == c['extension_executable_sha256'], 'Wrong actual executable/path/hash'
    product = read_receipt(root / 'mac-host-product-after.json')
    assert product['installed_bytes_unchanged'] is True and product['strict_signatures_unchanged'] is True
    for key in ['app_executable_sha256', 'extension_executable_sha256']:
        assert product[key] == c[key], 'Post-host product differs: ' + key
    before = read_receipt(root / 'mac-host-source-before.json')
    after = read_receipt(root / 'mac-host-source-after.json')
    for phase, receipt in [('before', before), ('after', after)]:
        assert receipt['source_sha'] == source_sha and receipt['phase'] == phase
        assert receipt['base_sha'] == BASE and receipt['base_tree'] == BASE_TREE
        assert receipt['unchanged_bound_files'] == UNCHANGED_BASE_FILES and receipt['reviewed_diagnostic_test_files']==REVIEWED_TEST_FILES and receipt['reviewed_candidate_files']==REVIEWED_CANDIDATE_FILES and receipt['complete_host_e2e'] is False
    assert before['tree'] == after['tree'] and before['workflow_sha256'] == after['workflow_sha256']
    contract=load_json((ROOT/'Scripts/combined-source-contract.json').read_text())
    for phase in ['before','after']:
        combined=read_receipt(root/('combined-source-'+phase+'.json'))
        assert combined['source_sha']==source_sha and combined['phase']==phase
        assert combined['tree']==before['tree'] and combined['workflow_sha256']==before['workflow_sha256']
        assert type(combined['file_count']) is int and combined['file_count']==len(contract['files'])
        assert combined['source_fingerprint']==contract['fingerprint']
    receipts = [root / name for name in ['combined-source-before.json','combined-source-after.json','mac-job-clock.json', 'mac-host-budget.json', 'mac-host-context.json', 'mac-host-summary.json', 'mac-host-test.log',
                'mac-host-product-after.json', 'mac-host-source-before.json', 'mac-host-source-after.json', 'mac-host-transport-replay.json']]
    receipts += [observed / name for name in ['prerequisite.json', 'outcome.json', 'host-selection.json', 'host-editor-before-process.json', 'host-editor-after-process.json', 'extension-process.json', 'fixture-ownership.json', 'fixture.json']]
    receipts += [observed/name for name in ['transport.json','containing-process.json','photos-process.json']]
    return {'host_entry_contract':HOST_CONTRACT,'source_sha': source_sha, 'prerequisite_accepted': True, 'complete_host_e2e': False,
            'proof_claim':'Real Photos UI entry with contemporaneously observed exact extension executable; registry inventory, audit-token view attribution, exact delivered-byte equality and full lifecycle are not claimed',
            'expected_testcase': '/'.join(EXPECTED_CASE), 'exactly_one_passed_zero_skipped': True,
            'last_stage': outcome['last_stage'], 'extension_executable': expected_executable,
            'extension_executable_sha256': actual['sha256'], 'extension_pid': actual['pid'],
            'receipts': [{'name': p.name, 'sha256': sha(p)} for p in receipts]}

HOST_SECONDS = 720
HOST_EVIDENCE_RESERVE_SECONDS = 300
JOB_EXECUTION_SECONDS = 41 * 60

def numeric(value, positive=False):
    return type(value) in (int,float) and math.isfinite(value) and (not positive or value>0)

def validate_clock(clock, source_sha):
    assert clock['source_sha']==source_sha
    assert type(clock['execution_budget_seconds']) is int and clock['execution_budget_seconds']==JOB_EXECUTION_SECONDS
    assert numeric(clock['started_monotonic'],positive=True) and numeric(clock['started_unix'],positive=True), 'Invalid job clock'
    return clock['started_monotonic']+JOB_EXECUTION_SECONDS

def validate_budget(report, clock, source_sha, complete=False):
    deadline=validate_clock(clock,source_sha)
    assert report['source_sha']==source_sha and report['complete_host_e2e'] is False
    for key,value in [('host_process_seconds',HOST_SECONDS),('evidence_reserve_seconds',HOST_EVIDENCE_RESERVE_SECONDS)]:
        assert type(report[key]) is int and report[key]==value
    checks=report['checks'];assert isinstance(checks,list) and len(checks)<=2
    phases=['before-prepare','before-host']
    assert [row['phase'] for row in checks]==phases[:len(checks)], 'Wrong/duplicate budget phase'
    previous=clock['started_monotonic']
    for row in checks:
        assert numeric(row['observed_monotonic'],positive=True) and row['observed_monotonic']>=previous, 'Decreasing or invalid phase clock'
        assert numeric(row['deadline_monotonic'],positive=True) and row['deadline_monotonic']==deadline
        assert numeric(row['remaining_seconds']) and row['remaining_seconds']==deadline-row['observed_monotonic']
        assert type(row['required_seconds']) is int and row['required_seconds']==HOST_SECONDS+HOST_EVIDENCE_RESERVE_SECONDS
        assert type(row['admitted']) is bool and row['admitted']==(row['remaining_seconds']>=row['required_seconds'])
        previous=row['observed_monotonic']
    if checks:assert report['admitted'] is checks[-1]['admitted']
    if complete:assert len(checks)==2 and all(row['admitted'] is True for row in checks)
    return deadline

def budget(phase):
    require_runner()
    root=temp(); path=root/'mac-host-budget.json'
    report=read_receipt(path) if path.exists() else {'source_sha':os.environ['GITHUB_SHA'], 'checks':[], 'host_process_seconds':HOST_SECONDS, 'evidence_reserve_seconds':HOST_EVIDENCE_RESERVE_SECONDS, 'complete_host_e2e':False}
    clock=read_receipt(root/'mac-job-clock.json'); now=time.monotonic()
    deadline=validate_budget(report,clock,os.environ['GITHUB_SHA'])
    assert numeric(now,positive=True)
    row={'phase':phase,'observed_monotonic':now,'deadline_monotonic':deadline,
         'remaining_seconds':deadline-now,'required_seconds':HOST_SECONDS+HOST_EVIDENCE_RESERVE_SECONDS,
         'admitted':deadline-now>=HOST_SECONDS+HOST_EVIDENCE_RESERVE_SECONDS}
    report['checks'].append(row);report['clock_sha256']=sha(root/'mac-job-clock.json')
    report['admitted']=row['admitted']
    # Same validation runs at admission and replay; malformed or decreasing
    # observations cannot become accepted simply through a JSON boolean.
    validate_budget(report,clock,os.environ['GITHUB_SHA'])
    write(path,report)
    if not row['admitted']:raise RuntimeError('Host prerequisite incomplete: insufficient job time for actual host plus proof collection/upload reserve')


def accept():
    require_runner()
    try:
        result = verify_acceptance(temp(), os.environ['GITHUB_SHA'])
    except Exception as error:
        result = {'host_entry_contract':HOST_CONTRACT,'source_sha': os.environ.get('GITHUB_SHA'), 'prerequisite_accepted': False,
                  'complete_host_e2e': False, 'error': type(error).__name__ + ': ' + str(error)}
    write(temp() / 'mac-host-acceptance.json', result)
    print('MAC_HOST_ACCEPTANCE ' + json.dumps(result, sort_keys=True))
    if not result['prerequisite_accepted']:
        raise SystemExit('Required actual Mac Photos host prerequisite proof failed')


PROOF_LIMITS = {
    'combined-source-before.json':160_000, 'combined-source-after.json':160_000,
    'mac-job-clock.json':160_000, 'mac-host-budget.json':160_000,
    'mac-host-acceptance.json':160_000,
    'mac-host-source-before.json':160_000, 'mac-host-source-after.json':160_000,
    'mac-host-product-after.json':160_000, 'mac-host-context.json':500_000,
    'mac-host-summary.json':160_000, 'mac-host-test.log':300_000,
    'mac-host-transport-replay.json':16_000, 'mac-host-observed/transport.json':16_000,
    'mac-host-observed/containing-process.json':16_000, 'mac-host-observed/photos-process.json':16_000,
    'mac-host-observed/host-selection.json':16_000, 'mac-host-observed/host-editor-before-process.json':16_000,
    'mac-host-observed/host-editor-after-process.json':16_000,
    'mac-host-observed/outcome.json':160_000, 'mac-host-observed/prerequisite.json':160_000,
    'mac-host-observed/extension-process.json':160_000,
    'mac-host-observed/fixture-ownership.json':160_000,
    'mac-host-observed/fixture.json':250_000,
}

def verify_collected(folder, source_sha):
    folder=Path(folder); index=folder/'manifest.json'
    manifest=read_receipt(index)
    assert index.stat().st_size<=50_000
    assert manifest['source_sha']==source_sha and manifest['cap_bytes']==CAP and manifest['retention_days']==1
    assert manifest['host_entry_contract']==HOST_CONTRACT
    assert manifest['complete_host_e2e'] is False
    assert type(manifest['prerequisite_accepted']) is bool
    names=set(); sources={}; total=index.stat().st_size
    for row in manifest['files']:
        name=row['path']; relative=row['source_relative']
        assert Path(name).name==name and name not in {'','.', '..'} and name not in names
        names.add(name); path=folder/name
        assert path.is_file() and not path.is_symlink() and type(row['bytes']) is int
        assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
        total+=row['bytes']
        if row['kind']=='required-proof':
            assert relative in PROOF_LIMITS and relative not in sources
            assert 0<row['bytes']<=PROOF_LIMITS[relative]
            sources[relative]=path
        else:assert row['kind']=='optional-diagnostic'
    assert total<=CAP and names=={p.name for p in folder.iterdir() if p.name!='manifest.json'}
    assert 'mac-host-acceptance.json' in sources
    status=read_receipt(sources['mac-host-acceptance.json'])
    assert status['host_entry_contract']==HOST_CONTRACT
    assert status['source_sha']==source_sha and status['complete_host_e2e'] is False
    assert status['prerequisite_accepted'] is manifest['prerequisite_accepted']
    missing=sorted(set(PROOF_LIMITS)-set(sources))
    assert manifest['missing_required_proof']==missing
    if manifest['prerequisite_accepted']:
        assert not missing and manifest['proof_state']=='complete-accepted-prerequisite'
        with tempfile.TemporaryDirectory(prefix='verify-celluloid-host-proof-') as temporary:
            root=Path(temporary)
            for relative,path in sources.items():
                target=root/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
            # Re-execute all finalized-test/source/product/host-UI/live-PID/
            # fixture rules. A JSON acceptance boolean never grants acceptance.
            actual=verify_acceptance(root,source_sha)
            assert actual==status, 'Collected acceptance differs from independently replayed proof'
    else:
        assert manifest['proof_state']=='diagnostic-only-incomplete'
        assert isinstance(status.get('error'),str) and status['error'].strip()
    return manifest

def collect():
    root=temp(); source_sha=os.environ['GITHUB_SHA'];destination=root/'mac-host-evidence'
    destination.mkdir(exist_ok=False)
    status=read_receipt(root/'mac-host-acceptance.json')
    assert status['host_entry_contract']==HOST_CONTRACT
    assert status['source_sha']==source_sha and status['complete_host_e2e'] is False
    assert type(status['prerequisite_accepted']) is bool
    accepted=status['prerequisite_accepted']
    if accepted:assert verify_acceptance(root,source_sha)==status
    else:assert isinstance(status.get('error'),str) and status['error'].strip()
    entries=[]; omitted=[]; used=0
    # Reserve complete mandatory proof before any AX dump, optional tail or PNG.
    for relative,limit in PROOF_LIMITS.items():
        path=root/relative
        if not path.exists():
            if accepted:raise AssertionError('Missing accepted proof: '+relative)
            continue
        assert path.is_file() and not path.is_symlink(), 'Invalid required proof: '+relative
        count=path.stat().st_size
        assert 0<count<=limit, 'Oversized required proof: '+relative
        assert used+count<=CAP-50_000, 'Required proof exceeds reserved host allocation'
        name=path.name;assert not (destination/name).exists()
        shutil.copyfile(path,destination/name);used+=count
        entries.append({'path':name,'source_relative':relative,'kind':'required-proof','bytes':count,'sha256':sha(path)})
    missing=sorted(set(PROOF_LIMITS)-{e['source_relative'] for e in entries})
    optional=[]; observed=root/'mac-host-observed'
    if observed.is_dir():
        optional=[p for p in sorted(observed.iterdir(),key=lambda p:(p.suffix!='.jpg',p.name))
                  if p.is_file() and p.suffix in ['.json','.txt','.jpg'] and str(p.relative_to(root)) not in PROOF_LIMITS]
    for path in optional:
        count=path.stat().st_size;limit=700_000 if path.suffix=='.jpg' else 160_000
        if path.is_symlink() or count>limit or used+count>CAP-50_000:
            omitted.append({'name':path.name,'reason':'optional diagnostic cap or symlink','bytes':count});continue
        assert not (destination/path.name).exists(), 'Optional diagnostic collides with required proof'
        shutil.copyfile(path,destination/path.name);used+=count
        entries.append({'path':path.name,'source_relative':str(path.relative_to(root)), 'kind':'optional-diagnostic','bytes':count,'sha256':sha(path)})
    write(destination/'manifest.json',{'host_entry_contract':HOST_CONTRACT,'source_sha':source_sha,'cap_bytes':CAP,'retention_days':1,'files':entries,
          'omitted':omitted,'missing_required_proof':missing,'prerequisite_accepted':accepted,
          'proof_state':'complete-accepted-prerequisite' if accepted else 'diagnostic-only-incomplete',
          'complete_host_e2e':False})
    verify_collected(destination,source_sha)
    print(json.dumps({'retained_bytes':sum(p.stat().st_size for p in destination.iterdir()),
                      'files':len(entries)+1,'prerequisite_accepted':accepted,'complete_host_e2e':False}))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['budget-before-prepare', 'budget-before-host', 'source-before', 'source-after', 'prepare', 'transport', 'product-after', 'processes', 'accept', 'collect'])
    args = parser.parse_args()
    if args.action.startswith('budget-'):
        budget(args.action.removeprefix('budget-'))
    elif args.action.startswith('source-'):
        require_runner(); verify_source(args.action.removeprefix('source-'))
    else:
        {'prepare': prepare, 'transport': extract_transport, 'product-after': verify_product, 'processes': process_provenance, 'accept': accept, 'collect': collect}[args.action]()

if __name__ == '__main__': main()
