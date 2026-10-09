#!/usr/bin/env python3
"""Bounded, actual iOS Photos host diagnostic, reusing the owned build/library."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys
import time
import uuid
from run_picker_acceptance import check_build, qualify_summary
from swiftui_photos_gate import validate_owner, phase_budget

ROOT = Path(__file__).resolve().parents[1]
PRODUCT_CONTROL_TREE = '33ddc8c371e3480b6a65da7b4064daabae8a1b17'
PRODUCT_CONTROL_FILES = 424
PRODUCT_CONTROL_SHA256 = '3e9d32d63d73f57813ae1a2674faea5d20995714d6d21be2f336f31a249ad3af'
STEPS = [
    ('prepare', 'CelluloidTests/IOSPhotosHostFixtureTests/testPrepareSingleOwnedPhotosHostAlbum', 45),
    ('save-ui', 'CelluloidUITests/IOSPhotosHostUITests/testActualPhotosExtensionSave', 165),
    ('saved', 'CelluloidTests/IOSPhotosHostFixtureTests/testReadActualPhotosHostSavedEdit', 45),
    ('cancel-ui', 'CelluloidUITests/IOSPhotosHostUITests/testActualPhotosExtensionReopenAndCancel', 165),
    ('cancelled', 'CelluloidTests/IOSPhotosHostFixtureTests/testReadActualPhotosHostCancelledEdit', 45)]

def require(condition, message):
    if not condition: raise ValueError(message)

def product_control(root):
    paths = sorted(path for name in ['Celluloid', 'CelluloidKit', 'CelluloidPhotoExtension', 'Packages']
                   for path in (root / name).rglob('*') if path.is_file())
    rows = [(path.relative_to(root).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()) for path in paths]
    return len(rows), hashlib.sha256(''.join(path + '\0' + digest + '\n' for path, digest in rows).encode()).hexdigest()

def check_product_control():
    require(product_control(ROOT) == (PRODUCT_CONTROL_FILES, PRODUCT_CONTROL_SHA256), 'Corrected iOS product source differs from the passed control tree')

def save(path, value):
    require(not path.exists(), 'Refusing stale host evidence: ' + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')

def record(log, prefix):
    rows = [json.loads(line[len(prefix):]) for line in log.splitlines() if line.startswith(prefix)]
    require(len(rows) == 1 and isinstance(rows[0], dict), 'Missing/ambiguous host evidence: ' + prefix)
    return rows[0]

def summary_json(log):
    rows = []
    for match in re.finditer(r'^\s*\{', log, re.M):
        try: value, _ = json.JSONDecoder().raw_decode(log[match.start():].lstrip())
        except json.JSONDecodeError: continue
        if isinstance(value, dict) and 'totalTestCount' in value: rows.append(value)
    require(len(rows) == 1, 'Missing/ambiguous real XCTest summary')
    return rows[0]

def make_context(manifest, owner):
    require(manifest.get('schema') == 'celluloid.swiftui.seeded-library.v1', 'Wrong fixture manifest schema')
    for key in ['source_sha', 'device_id', 'run_id', 'run_attempt']:
        require(manifest.get(key) == owner.get(key), 'Fixture ownership differs: ' + key)
    require(manifest.get('authorization_read_write') == 'authorized', 'Real existing Photos grant absent')
    rows = manifest.get('fixtures', [])
    require(len(rows) == 6 and manifest.get('fixture_count') == 6, 'Expected exactly six verified imports')
    baseline, seeded, added = [set(manifest.get(key, [])) for key in ['baseline_asset_ids', 'seeded_asset_ids', 'added_asset_ids']]
    require(baseline <= seeded and seeded - baseline == added and len(added) == 6, 'Fixture ID delta is invalid')
    require({row['identifier'] for row in rows} == added, 'Controlled fixture IDs differ from actual additions')
    require(len(baseline) == manifest.get('baseline_asset_count') and len(seeded) == manifest.get('seeded_asset_count'), 'Actual inventory counts differ')
    found = [row for row in rows if row.get('filename') == 'celluloid-fixture-2.png']
    require(len(found) == 1 and (found[0].get('width'), found[0].get('height')) == (640, 480), 'Owned host fixture is absent/ambiguous')
    fixture = found[0]
    require(re.fullmatch(r'[0-9a-f]{64}', fixture.get('sha256', '')), 'Fixture digest is malformed')
    token = str(uuid.uuid4())
    return {'schema': 'celluloid.ios.photos-host.v1',
        **{key: owner[key] for key in ['source_sha', 'device_id', 'run_id', 'run_attempt']},
        'context_token': token, 'album_title': 'Celluloid Host ' + token,
        'asset_identifier': fixture['identifier'], 'fixture_filename': fixture['filename'],
        'fixture_sha256': fixture['sha256'], 'saved_caption': 'Host ' + token[:8]}

def check_context(actual, expected):
    for key, value in expected.items():
        require(actual.get(key) == value, 'Host context changed: ' + key)

def native_uncertain(code, log):
    return (code in [124, 137, 143] or 'BOUNDED_COMMAND_TIMEOUT' in log or 'CLEANUP_UNCONFIRMED' in log
            or bool(re.search(r'(?:exceeded (?:the )?execution time allowance|test(?: execution)? timed out)', log, re.I)))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['device', 'derived', 'out', 'owner', 'build-binding', 'fixture-manifest']:
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args(); os.chdir(ROOT)
    output = Path(args.out).resolve(); derived = Path(args.derived).resolve()
    output.relative_to(ROOT / 'build'); derived.relative_to(ROOT / '.build')
    require(sys.platform == 'darwin' and os.environ.get('DEVELOPER_DIR') == '/Applications/Xcode_27.app/Contents/Developer', 'Wrong owned native route')
    require(not output.exists(), 'Host evidence directory must be new')
    output.mkdir(parents=True)
    owner = json.loads(Path(args.owner).read_text())
    manifest_bytes = Path(args.fixture_manifest).read_bytes(); manifest = json.loads(manifest_bytes)
    binding = json.loads(Path(args.build_binding).read_text())
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True, timeout=15).strip()
    tree = subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], text=True, timeout=15).strip()
    require(source == os.environ.get('GITHUB_SHA'), 'Checkout source differs')
    subprocess.run(['git', 'diff', '--exit-code', 'HEAD', '--'], check=True, timeout=15)
    check_product_control()
    require(phase_budget('pristine', owner) == 600, 'Full 600-second host diagnostic plus cleanup does not fit')
    observed = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', 'available', '-j'], text=True, timeout=20))
    validate_owner(owner, args.device, os.environ, observed, expected_ref='refs/heads/cell-ios-photos-host-probe')
    context = make_context(manifest, owner)
    binary = derived / 'Build/Products/Debug-iphonesimulator/Celluloid.app/Celluloid'
    check_build(binding, binary, source, tree)
    extension = binary.parent / 'PlugIns/CelluloidPhotoExtension.appex'
    info = plistlib.loads((extension / 'Info.plist').read_bytes())
    require(info['CFBundleIdentifier'] == 'Mango.Celluloid.CelluloidPhotoExtension'
            and info['NSExtension']['NSExtensionPointIdentifier'] == 'com.apple.photo-editing', 'Actual embedded Photos extension absent')
    extension_binary = extension / info['CFBundleExecutable']
    save(output / 'binding.json', {'source_sha': source, 'source_tree': tree, 'device_id': args.device,
         'product_control_tree': PRODUCT_CONTROL_TREE, 'product_control_sha256': PRODUCT_CONTROL_SHA256,
         'app_bundle_sha256': binding['app_bundle_sha256'],
         'extension_executable_sha256': hashlib.sha256(extension_binary.read_bytes()).hexdigest(),
         'fixture_manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(), 'context': context})
    deadline = min(time.monotonic() + 600, owner['work_deadline_monotonic'] - 15)
    statuses = {}; uncertain = False; accepted = False; error = None

    def run(label, command, seconds, simulator=False):
        nonlocal uncertain
        require(time.monotonic() + seconds + 10 <= deadline, 'Shared host deadline cannot admit ' + label)
        environment = dict(os.environ, TZ='UTC', TEST_RUNNER_TZ='UTC',
            TEST_RUNNER_CELLULOID_IOS_PHOTOS_HOST='1', TEST_RUNNER_CELLULOID_EXPECTED_SOURCE_SHA=source,
            TEST_RUNNER_CELLULOID_FIXTURE_MANIFEST_JSON=json.dumps(manifest, separators=(',', ':')),
            TEST_RUNNER_CELLULOID_IOS_PHOTOS_HOST_CONTEXT=json.dumps(context, separators=(',', ':')))
        for key in ['TEST_RUNNER_CELLULOID_SYNTHETIC_PROBE', 'TEST_RUNNER_CELLULOID_PROBE_SOURCE_SHA']:
            environment.pop(key, None)
        path = output / (label + '.log')
        with path.open('wb') as stream:
            code = subprocess.call([sys.executable, 'Scripts/run_bounded.py', '--seconds', str(seconds),
                '--label', 'ios-photos-host-' + label, *command], env=environment, stdout=stream, stderr=subprocess.STDOUT)
        log = path.read_text(errors='replace'); statuses[label] = code
        if simulator and native_uncertain(code, log): uncertain = True
        return code, log

    try:
        for stage, selector, seconds in STEPS:
            result = output / (stage + '.xcresult')
            command = ['xcodebuild', '-project', 'Celluloid.xcodeproj', '-scheme', 'Celluloid', '-configuration', 'Debug',
                '-destination', 'platform=iOS Simulator,id=' + args.device, '-derivedDataPath', str(derived),
                '-resultBundlePath', str(result), '-parallel-testing-enabled', 'NO', '-collect-test-diagnostics', 'never',
                '-test-timeouts-enabled', 'YES', '-maximum-test-execution-time-allowance', '120',
                '-only-testing:' + selector, 'test-without-building', 'CODE_SIGNING_ALLOWED=NO', 'CODE_SIGNING_REQUIRED=NO']
            code, log = run(stage, command, seconds, simulator=True)
            summary_code, raw = run(stage + '-summary', ['xcrun', 'xcresulttool', 'get', 'test-results', 'summary', '--path', str(result)], 15)
            require(code == 0 and summary_code == 0, 'Actual host stage failed: ' + stage)
            summary = summary_json(raw); save(output / (stage + '-summary.json'), summary)
            qualify_summary(summary, 1, args.device)
            require(summary.get('runtimeWarnings') == [], 'Host stage runtime warnings require review')
            module, suite, method = selector.split('/')
            require(len(re.findall(re.escape("Test Case '-[" + module + '.' + suite + ' ' + method + "]' passed"), log)) == 1,
                    'Exact actual host test method did not pass')
            if stage == 'prepare':
                prepared = record(log, 'IOS_PHOTOS_HOST_STORAGE prepared '); check_context(prepared, context)
                require(prepared.get('library_asset_ids') == sorted(manifest['seeded_asset_ids']), 'Photos library changed before host UI')
                require(isinstance(prepared.get('album_identifier'), str), 'Missing real owned album identifier')
                require(prepared.get('public_filename_unique_asset_id') == context['asset_identifier'], 'Missing whole-library public filename uniqueness proof')
                context = prepared
            elif stage in ['save-ui', 'cancel-ui']:
                event = record(log, 'IOS_PHOTOS_HOST_UI ')
                check_context(event, {key: context[key] for key in ['source_sha', 'context_token', 'album_identifier', 'asset_identifier']})
                require(event.get('host_bundle') == 'com.apple.mobileslideshow', 'Real Photos host differs')
                require(event.get('event') == ('save' if stage == 'save-ui' else 'reopen-cancel'), 'Host event differs')
            elif stage == 'saved':
                saved = record(log, 'IOS_PHOTOS_HOST_STORAGE saved '); check_context(saved, context)
                require(isinstance(saved.get('saved'), dict), 'Missing saved resource receipt'); context = saved
            else:
                cancelled = record(log, 'IOS_PHOTOS_HOST_STORAGE cancelled ')
                check_context(cancelled, {key: context[key] for key in ['source_sha', 'device_id', 'context_token', 'asset_identifier']})
                require(cancelled.get('unchanged_saved_integrity') == context['saved'], 'Cancelled save changed storage')
            save(output / (stage + '-evidence.json'), context if stage not in ['save-ui', 'cancel-ui', 'cancelled'] else (event if stage.endswith('-ui') else cancelled))
        check_build(binding, binary, source, tree)
        check_product_control()
        accepted = True
    except BaseException as failure:
        error = str(failure)
        if isinstance(failure, (KeyboardInterrupt, SystemExit)): uncertain = True
    finally:
        save(output / 'acceptance.json', {'schema': 'celluloid.ios.photos-host-result.v1', 'source_sha': source,
            'device_id': args.device, 'all_five_stages_passed': accepted, 'phase_statuses': statuses, 'error': error,
            'prohibit_further_simctl': uncertain or time.monotonic() >= deadline,
            'release_qualification': False, 'scope': 'Actual Photos UI save/reopen/cancel for one owned fixture; not every format/legacy host scenario'})
    return 0 if accepted else 1

if __name__ == '__main__': raise SystemExit(main())
