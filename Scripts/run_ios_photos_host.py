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
from swiftui_photos_gate import validate_owner, phase_budget, fresh_owned_device_observation

ROOT = Path(__file__).resolve().parents[1]
PRODUCT_CONTROL_TREE = 'f2c6d0f38c026957b0b34f22b916eb80ed5b20a8'
PRODUCT_CONTROL_FILES = 424
PRODUCT_CONTROL_SHA256 = '7e2a14bb1d874776638aba24c648c7ec6171a270840fe8660f31eabeb784f4f3'
STEPS = [
    ('prepare', 'CelluloidTests/IOSPhotosHostFixtureTests/testPrepareSingleOwnedPhotosHostAlbum', 45),
    ('save-ui', 'CelluloidUITests/IOSPhotosHostUITests/testActualPhotosExtensionSave', 165),
    ('saved', 'CelluloidTests/IOSPhotosHostFixtureTests/testReadActualPhotosHostSavedEdit', 45),
    ('cancel-ui', 'CelluloidUITests/IOSPhotosHostUITests/testActualPhotosExtensionReopenAndCancel', 165),
    ('cancelled', 'CelluloidTests/IOSPhotosHostFixtureTests/testReadActualPhotosHostCancelledEdit', 45)]

def require(condition, message):
    if not condition: raise ValueError(message)

PRODUCT_SHA = '13e9a1ed63c6e7744803419f27e429a759df1209'
PROBE_BRANCH = 'cell-ios-photos-host-final'
PROBE_CONFIG = '.github/ios-photos-host-final.json'
PROBE_WORKFLOW = '.github/workflows/ios-photos-host-probe.yml'
PROBE_PATHS = frozenset(['Scripts/run_bounded.py','Scripts/test_final_ios_photos_host_admission.py', '.github/ios-photos-host-final.json', '.github/workflows/ios-photos-host-probe.yml', 'Celluloid.xcodeproj/project.pbxproj', 'CelluloidTests/IOSPhotosHostFixtureTests.swift', 'CelluloidUITests/IOSPhotosHostUITests.swift', 'Scripts/run_ios_photos_host.py', 'Scripts/run_ios_photos_host_diagnostic.py', 'Scripts/run_swiftui_photos_gate.sh', 'Scripts/swiftui_photos_gate.py', 'Scripts/test_ios_photos_host.py'])
PROBE_FIXED_FILES = {'Celluloid.xcodeproj/project.pbxproj': '34b764ed594db19cba375cf9e99a5f2e25d28c83718942cbf8b2bb9e21dfa6dc', 'CelluloidTests/IOSPhotosHostFixtureTests.swift': '1342f6435ea770cae23b6889e3ddd85ff1cec929c63b209d5623f13e387eb632', 'CelluloidUITests/IOSPhotosHostUITests.swift': '46661053de21edfedef281385c6325d5ca18e72e908843dfd9c16043d5f10c39'}

def validate_probe_admission(config, context, facts):
    require(set(config) == {'schema','READY','sourceReady','nativeAuthorization','product_sha','product_tree','maximum_additional_spend_usd'}, 'Unknown final host admission fields')
    require(type(config['schema']) is int and config['schema'] == 1
            and all(config[key] is True for key in ['READY','sourceReady','nativeAuthorization']), 'Final Photos host route is closed')
    require(config['product_sha'] == PRODUCT_SHA and config['product_tree'] == PRODUCT_CONTROL_TREE, 'Wrong final product identity')
    require(type(config['maximum_additional_spend_usd']) is int and config['maximum_additional_spend_usd'] == 0, 'Nonzero spend is not admitted')
    expected={'GITHUB_REPOSITORY':'100mango/Celluloid','GITHUB_EVENT_NAME':'push','GITHUB_REF':'refs/heads/'+PROBE_BRANCH,
              'GITHUB_WORKFLOW_REF':'100mango/Celluloid/'+PROBE_WORKFLOW+'@refs/heads/'+PROBE_BRANCH,'GITHUB_RUN_ATTEMPT':'1'}
    require(all(context.get(key)==value for key,value in expected.items()), 'Wrong final host workflow context or retry')
    require(re.fullmatch('[1-9][0-9]*',context.get('GITHUB_RUN_ID','')) is not None, 'Missing run identity')
    require(re.fullmatch('[0-9a-f]{40}',facts['head']) and re.fullmatch('[0-9a-f]{40}',facts['tree']), 'Malformed control identity')
    require(context.get('GITHUB_SHA')==context.get('GITHUB_WORKFLOW_SHA')==facts['head'], 'Mismatched exact workflow/source')
    require(facts['product_tree']==PRODUCT_CONTROL_TREE and not facts['dirty'], 'Wrong product tree or dirty source')
    require(0 < len(facts['chain']) <= 17, 'Final host control history is not bounded and linear')
    prior=PRODUCT_SHA
    for commit in facts['chain']:
        require(commit['parents']==[prior] and commit['paths'] and set(commit['paths']) <= PROBE_PATHS, 'Product mutation or merge in host control chain')
        prior=commit['sha']
    require(prior==facts['head'] and set(facts['paths'])==PROBE_PATHS, 'Incomplete or unexpected probe closure')
    return {'schema':'Celluloid.FinalPhotosHostAdmission.1','product_sha':PRODUCT_SHA,'product_tree':PRODUCT_CONTROL_TREE,
            'source_sha':facts['head'],'source_tree':facts['tree'],'run_id':context['GITHUB_RUN_ID'],'run_attempt':'1',
            'product_control_sha256':PRODUCT_CONTROL_SHA256,'version':'1.1.1','build':'3','release_qualified':False}

def admit_probe(root=ROOT, environment=None):
    environment=os.environ if environment is None else environment
    path=root/PROBE_CONFIG
    require(path.is_file() and not path.is_symlink() and path.stat().st_size<=8192, 'Missing bounded final host configuration')
    def unique(pairs):
        result={}
        for key,value in pairs:
            require(key not in result, 'Duplicate final host configuration key');result[key]=value
        return result
    config=json.loads(path.read_text(),object_pairs_hook=unique)
    # Closed configuration returns before Git, native work, simulator or permission handling.
    require(all(config.get(key) is True for key in ['READY','sourceReady','nativeAuthorization']), 'Final Photos host route is closed')
    deadline=time.monotonic()+15
    def git(*args):
        remaining=min(5,deadline-time.monotonic());require(remaining>0,'Source admission budget exhausted')
        return subprocess.check_output(['git',*args],cwd=root,text=True,timeout=remaining).strip()
    git('merge-base','--is-ancestor',PRODUCT_SHA,'HEAD')
    chain=[]
    for line in git('rev-list','--reverse','--parents',PRODUCT_SHA+'..HEAD').splitlines():
        values=line.split();require(len(values)==2,'Merge or missing exact parent')
        chain.append({'sha':values[0],'parents':values[1:],'paths':git('diff','--name-only',values[1],values[0]).splitlines()})
    facts={'head':git('rev-parse','HEAD'),'tree':git('rev-parse','HEAD^{tree}'),'product_tree':git('rev-parse',PRODUCT_SHA+'^{tree}'),
           'dirty':git('status','--porcelain','--untracked-files=all'),'chain':chain,'paths':git('diff','--name-only',PRODUCT_SHA,'HEAD').splitlines()}
    receipt=validate_probe_admission(config,environment,facts)
    require(product_control(root)==(PRODUCT_CONTROL_FILES,PRODUCT_CONTROL_SHA256), 'Final corrected product content changed')
    for relative,digest in PROBE_FIXED_FILES.items():
        target=root/relative
        require(target.is_file() and not target.is_symlink() and hashlib.sha256(target.read_bytes()).hexdigest()==digest, 'Reviewed project/test input changed: '+relative)
    receipt['control_fingerprint']=hashlib.sha256(json.dumps([[p,hashlib.sha256((root/p).read_bytes()).hexdigest()] for p in sorted(PROBE_PATHS)],separators=(',',':')).encode()).hexdigest()
    return receipt

def check_owned_versions(app):
    paths=[app/'Info.plist',app/'Frameworks/CelluloidKit.framework/Info.plist',app/'PlugIns/CelluloidPhotoExtension.appex/Info.plist']
    for path in paths:
        info=plistlib.loads(path.read_bytes())
        require((info.get('CFBundleShortVersionString'),info.get('CFBundleVersion'))==('1.1.1','3'), 'Wrong final owned bundle version: '+str(path))


def product_control(root):
    paths = sorted(path for name in ['Celluloid', 'CelluloidKit', 'CelluloidPhotoExtension', 'Packages']
                   for path in (root / name).rglob('*') if path.is_file())
    rows = [(path.relative_to(root).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()) for path in paths]
    return len(rows), hashlib.sha256(''.join(path + '\0' + digest + '\n' for path, digest in rows).encode()).hexdigest()

def check_product_control():
    require(product_control(ROOT) == (PRODUCT_CONTROL_FILES, PRODUCT_CONTROL_SHA256), 'Final corrected iOS product source differs from the pinned product tree')

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
    admit_probe()
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
    observed = fresh_owned_device_observation(output)
    validate_owner(owner, args.device, os.environ, observed, expected_ref='refs/heads/cell-ios-photos-host-final')
    context = make_context(manifest, owner)
    binary = derived / 'Build/Products/Debug-iphonesimulator/Celluloid.app/Celluloid'
    check_build(binding, binary, source, tree)
    check_owned_versions(binary.parent)
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
        require(not uncertain, 'Uncertain Photos host state blocks further native dispatch')
        require(time.monotonic() + seconds + 10 <= deadline, 'Shared host deadline cannot admit ' + label)
        environment = dict(os.environ, TZ='UTC', TEST_RUNNER_TZ='UTC',
            TEST_RUNNER_CELLULOID_IOS_PHOTOS_HOST='1', TEST_RUNNER_CELLULOID_EXPECTED_SOURCE_SHA=source,
            TEST_RUNNER_CELLULOID_FIXTURE_MANIFEST_JSON=json.dumps(manifest, separators=(',', ':')),
            TEST_RUNNER_CELLULOID_IOS_PHOTOS_HOST_CONTEXT=json.dumps(context, separators=(',', ':')))
        for key in ['TEST_RUNNER_CELLULOID_SYNTHETIC_PROBE', 'TEST_RUNNER_CELLULOID_PROBE_SOURCE_SHA']:
            environment.pop(key, None)
        path = output / (label + '.log')
        dispatched=time.monotonic()
        with path.open('wb') as stream:
            code = subprocess.call([sys.executable, '-S', 'Scripts/run_bounded.py', '--seconds', str(seconds),
                '--label', 'ios-photos-host-' + label, '--deadline-monotonic', str(dispatched+seconds), *command], env=environment, stdout=stream, stderr=subprocess.STDOUT)
        log = path.read_text(errors='replace');elapsed=time.monotonic()-dispatched
        late=elapsed>seconds
        save(output/(label+'-dispatch-timing.json'),{'phase':label,'dispatch_started_monotonic':dispatched,
             'deadline_monotonic':dispatched+seconds,'elapsed_seconds':elapsed,'limit_seconds':seconds,
             'returned_exit_code':code,'late_completion':late})
        if late:uncertain=True;code=124
        statuses[label] = code
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

if __name__ == '__main__':
    if sys.argv[1:] == ['--admit-only']: print(json.dumps(admit_probe(),sort_keys=True))
    else: raise SystemExit(main())
