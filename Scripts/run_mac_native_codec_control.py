#!/usr/bin/env python3
"""One fixed pre-Photos XCTest on a fresh standard Mac runner; never a host gate."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time

from consumer_runtime_binding import validate_raw_execution
from mac_host_lifecycle_pixels import compare, decode, read_owned_png, require
from mac_host_transport import load_json
from native_process import run

ROOT = Path(__file__).resolve().parents[1]
BASE = 'a940bcdf8a92811210bcfacf84141dceb6c3fcd3'
BRANCH = 'refs/heads/codex/mac-native-codec-control'
MANIFEST = 'Scripts/mac-native-codec-control-source.json'
WORKFLOW = '.github/workflows/mac-native-codec-control.yml'
CLASS = 'MacPhotoNativeCodecControlTests'
METHOD = 'testRetainedSourceFadeExportAfterOriginalAndFadePreviews'
TARGET = 'CelluloidMacPhotosExtensionTests'
SELECTION = TARGET + '/' + CLASS + '/' + METHOD
RAW_CASE = '-[' + TARGET + '.' + CLASS + ' ' + METHOD + ']'
SOURCE = 'Platforms/MacExtensionTests/Fixtures/lifecycle-source.png'
SOURCE_SHA = '6138992615dd7d5bd499b80d9f11e39a0815111feccd5d4d3e59a676f4384772'
CAPS = {name: 128 * 1024 for name in (
    'codec-actual.jpg', 'codec-reference.jpg', 'codec-actual-decoded.png',
    'codec-reference-decoded.png', 'codec-reference-prejpeg.png')}
CAPS['codec-control.json'] = 16 * 1024
ATTACHMENT_CAP = 512 * 1024
EVIDENCE_CAP = 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], timeout=10)


def source_snapshot(root, manifest):
    """Every tracked source byte except the manifest's self-reference is pinned."""
    require(manifest.get('schema') == 'Celluloid.NativeCodecSource.1' and manifest.get('parent') == BASE,
            'Wrong source manifest identity')
    rows = manifest.get('files')
    require(type(rows) is list and 0 < len(rows) <= 1000, 'Source inventory size')
    names = []
    for row in rows:
        require(type(row) is dict and set(row) == {'path', 'mode', 'bytes', 'sha256'}, 'Source inventory row')
        rel = row['path']
        require(type(rel) is str and rel != MANIFEST and not Path(rel).is_absolute()
                and '..' not in Path(rel).parts and rel not in names, 'Source inventory path')
        names.append(rel)
        path = root / rel
        require(path.is_file() and not path.is_symlink(), 'Missing/nonregular source: ' + rel)
        data = path.read_bytes()
        mode = '100755' if path.stat().st_mode & stat.S_IXUSR else '100644'
        require(len(data) == row['bytes'] and sha(data) == row['sha256'] and mode == row['mode'],
                'Source bytes/mode changed: ' + rel)
    require(names == sorted(names), 'Source inventory ordering')
    return sha(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode())


def admit_source():
    require(sys.platform == 'darwin' and os.environ.get('GITHUB_ACTIONS') == 'true', 'Fresh Mac Actions runner required')
    require(os.environ.get('GITHUB_REPOSITORY') == '100mango/Celluloid'
            and os.environ.get('GITHUB_REF') == BRANCH and os.environ.get('GITHUB_EVENT_NAME') == 'push',
            'Wrong fixed repository/branch/event')
    run_id = os.environ.get('GITHUB_RUN_ID', '')
    require(re.fullmatch('[1-9][0-9]*', run_id) and os.environ.get('GITHUB_RUN_ATTEMPT') == '1',
            'Missing run identity or non-first attempt')
    head = git('rev-parse', 'HEAD').decode().strip()
    require(re.fullmatch('[0-9a-f]{40}', head) and head == os.environ.get('GITHUB_SHA')
            and head == os.environ.get('GITHUB_WORKFLOW_SHA'), 'Workflow/source SHA disagreement')
    require(git('rev-list', '--parents', '-n', '1', 'HEAD').decode().strip().split() == [head, BASE],
            'Candidate must be one commit directly on the reviewed a940 parent')
    require(not git('status', '--porcelain', '--untracked-files=all').strip(), 'Dirty checkout')
    raw = (ROOT / MANIFEST).read_bytes()
    require(len(raw) <= 256 * 1024, 'Source manifest byte cap')
    manifest = load_json(raw)
    inventory = set(git('ls-files', '-z').decode().rstrip('\0').split('\0'))
    require(inventory == {r['path'] for r in manifest['files']} | {MANIFEST}, 'Tracked inventory mismatch')
    fingerprint = source_snapshot(ROOT, manifest)
    require(sha((ROOT / SOURCE).read_bytes()) == SOURCE_SHA, 'Synthetic fixture changed')
    return manifest, {'schema': 'Celluloid.NativeCodecSourceReceipt.1', 'source_sha': head,
        'tree': git('rev-parse', 'HEAD^{tree}').decode().strip(), 'parent': BASE,
        'file_count_including_manifest': len(inventory), 'source_fingerprint': fingerprint,
        'source_manifest_sha256': sha(raw), 'workflow_sha256': sha((ROOT / WORKFLOW).read_bytes()),
        'fixture_sha256': SOURCE_SHA, 'selected_case': SELECTION, 'scope': 'synthetic-pre-host-only',
        'run_id': run_id, 'run_attempt': 1}


def command(temp, action):
    require(action in ('build-for-testing', 'test-without-building'), 'Unknown native action')
    args = ['xcodebuild', '-project', 'CelluloidNative.xcodeproj', '-scheme', 'CelluloidMacPhotosExtension',
        '-configuration', 'Debug', '-destination', 'platform=macOS', '-derivedDataPath', str(temp / 'celluloid-codec-derived'),
        '-parallel-testing-enabled', 'NO', '-only-testing:' + SELECTION,
        'CODE_SIGNING_ALLOWED=NO', 'CODE_SIGNING_REQUIRED=NO', 'CODE_SIGN_IDENTITY=']
    if action == 'test-without-building':
        args += ['-resultBundlePath', str(temp / 'CelluloidNativeCodecControl.xcresult'),
            '-test-timeouts-enabled', 'YES',
            '-default-test-execution-time-allowance', '90', '-maximum-test-execution-time-allowance', '90']
    return args + [action]


def attachments(folder, manifest):
    """Reuse owned bounded reads; accept only the six exact-test display names."""
    require(folder.is_dir() and not folder.is_symlink(), 'Unowned attachment directory')
    require(type(manifest) is list and len(manifest) <= 8, 'Attachment record cap')
    result = {}; seen = set(); count = 0
    for record in manifest:
        require(type(record) is dict and type(record.get('attachments')) is list, 'Malformed attachment record')
        for item in record['attachments']:
            count += 1
            require(count <= 64 and type(item) is dict, 'Attachment inventory cap/type')
            human = item.get('suggestedHumanReadableName')
            require(type(human) is str and len(human) <= 256, 'Attachment display-name bound')
            if not human.startswith('codec-'):
                continue  # Ordinary XCTest diagnostics never leave the runner.
            match = re.fullmatch(r'(codec-(?:actual|reference)(?:-decoded|-prejpeg)?|codec-control)'
                r'_0_[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}\.(jpg|png|json)', human)
            require(match is not None, 'Unknown codec attachment naming')
            name = match[1] + '.' + match[2]
            exported = item.get('exportedFileName')
            require(name in CAPS and name not in result and record.get('testIdentifier') == CLASS + '/' + METHOD + '()',
                    'Wrong/duplicate codec attachment or testcase')
            require(type(exported) is str and Path(exported).name == exported and exported not in ('', '.', '..')
                    and exported not in seen, 'Unowned/duplicate attachment file')
            seen.add(exported)
            raw = read_owned_png(folder / exported)  # Fixed 128 KiB no-follow, regular/nlink=1, stable-span reader.
            require(len(raw) <= CAPS[name] and sum(map(len, result.values())) + len(raw) <= ATTACHMENT_CAP,
                    'Codec attachment byte cap')
            if name.endswith('.jpg'):
                require(raw.startswith(b'\xff\xd8\xff') and raw.endswith(b'\xff\xd9'), 'Malformed JPEG envelope')
            elif name.endswith('.png'):
                require(raw.startswith(b'\x89PNG\r\n\x1a\n'), 'Wrong codec PNG type')
            else:
                load_json(raw)
            result[name] = raw
    return result


def inspect_execution(log, summary, return_code):
    require(type(summary) is dict, 'Missing native summary')
    counts = {k: summary.get(k) for k in ('totalTestCount', 'passedTests', 'failedTests', 'skippedTests', 'expectedFailures')}
    require(all(type(v) is int for v in counts.values()) and counts['totalTestCount'] == 1
            and counts['passedTests'] + counts['failedTests'] == 1
            and counts['skippedTests'] == counts['expectedFailures'] == 0, 'Not exactly one executed native testcase')
    require(summary.get('result') in ('Passed', 'Failed') and (summary['result'] == 'Passed') == (return_code == 0),
            'Native process/summary disagreement')
    configurations = summary.get('devicesAndConfigurations')
    require(type(configurations) is list and len(configurations) == 1, 'Ambiguous native configuration')
    conf = configurations[0]; dev = conf.get('device', {})
    require((dev.get('platform'), dev.get('osVersion'), dev.get('architecture')) == ('macOS', '27.0', 'arm64'),
            'Unexpected native runtime')
    require(all(type(conf.get(k)) is int and conf[k] == counts[k] for k in counts if k != 'totalTestCount'), 'Native device/count disagreement')
    cases = re.findall(r"^Test Case '([^']+)' (?:started\.|(?:passed|failed|skipped) \([0-9.]+ seconds\)\.)$", log, re.M)
    require(cases == [RAW_CASE, RAW_CASE], 'Wrong/repeated native testcase identity')
    accounting = validate_raw_execution(log, summary)
    require(type(accounting['result_session_path_observation']) is str
            and accounting['result_session_path_observation'].endswith('/CelluloidNativeCodecControl.xcresult'),
            'Missing/wrong native result-session path')
    return {'runtime': dev, 'accounting': accounting, 'native_passed': summary['result'] == 'Passed'}


def admit_native_completion(log, event, bundle):
    """No summary/export subprocess follows an unknown or unclean native return."""
    require(event.get('stage') == 'single-native-case' and event.get('returned_without_timeout') is True
            and event.get('limit_seconds') == 120 and type(event.get('return_code')) is int
            and event['return_code'] in (0, 65), 'Unknown native completion or return code')
    for key in ('started_unix', 'finished_unix', 'elapsed_seconds'):
        require(type(event.get(key)) in (int, float) and math.isfinite(event[key]), 'Missing native command interval')
    require(0 < event['elapsed_seconds'] <= event['limit_seconds']
            and event['started_unix'] < event['finished_unix'], 'Native command exceeded original phase budget')
    state, terminal = ('passed', 'SUCCEEDED') if event['return_code'] == 0 else ('failed', 'FAILED')
    lines = [line.strip() for line in log.splitlines()]
    cases = [line for line in lines if line.lower().startswith('test case ')]
    require(len(cases) == 2 and cases[0] == "Test Case '" + RAW_CASE + "' started."
            and re.fullmatch(re.escape("Test Case '" + RAW_CASE + "' " + state) + r' \([0-9]+(?:\.[0-9]+)? seconds\)\.', cases[1]),
            'Native case has no unique matching start/terminal')
    terminals = [line for line in lines if re.match(r'^\*\* TEST(?: EXECUTE)?\b', line, re.I)]
    require(terminals == ['** TEST EXECUTE ' + terminal + ' **']
            and lines.index(cases[0]) < lines.index(cases[1]) < lines.index(terminals[0]), 'Native command terminal mismatch')
    paths = [line for line in lines if line.startswith('/') and line.endswith('.xcresult')]
    require(paths in ([bundle], [bundle, bundle]), 'Native transcript names a different result bundle')


def admit_export(log, summary, event, bundle, source):
    admit_native_completion(log, event, bundle)
    require(type(source.get('run_id')) is str and re.fullmatch('[1-9][0-9]*', source['run_id'])
            and type(source.get('run_attempt')) is int and source['run_attempt'] == 1
            and event.get('run_id') == source['run_id'] and event.get('run_attempt') == source['run_attempt'],
            'Native command belongs to another run/attempt')
    execution = inspect_execution(log, summary, event['return_code'])
    require(execution['accounting']['result_session_path_observation'] == bundle, 'Wrong finalized result bundle')
    for key in ('startTime', 'finishTime'):
        require(type(summary.get(key)) in (int, float) and math.isfinite(summary[key]), 'Unfinalized summary time')
    require(event['started_unix'] <= summary['startTime'] < summary['finishTime'] <= event['finished_unix']
            and summary['finishTime'] - summary['startTime'] <= event['elapsed_seconds'],
            'Summary is outside this original native command interval')
    return execution


def inspect_result(log, summary, retained, return_code):
    execution = inspect_execution(log, summary, return_code)
    require(set(retained) == set(CAPS), 'Incomplete six-artifact codec control')
    report = load_json(retained['codec-control.json'])
    require(report.get('schema') == 'Celluloid.NativeCodecControl.1' and report.get('scope') == 'synthetic-pre-host-only'
            and report.get('public_parent') == BASE and report.get('source_sha256') == SOURCE_SHA
            and report.get('allowed_max_channel_delta') == 2
            and report.get('sequence') == ['Original preview', 'Fade preview', 'Fade export'], 'Control identity/contract mismatch')
    require(all(report.get(k) is False for k in ('photos_input_observed', 'photos_submitted_jpeg_observed', 'actual_export_prejpeg_observed')),
            'Unsupported host/export claim')
    entries = report.get('artifacts')
    require(type(entries) is dict and set(entries) == set(CAPS) - {'codec-control.json'}, 'Control artifact inventory mismatch')
    for name, expected in entries.items():
        require(expected == {'bytes': len(retained[name]), 'sha256': sha(retained[name])}, 'Artifact hash/length disagreement')
    for key, name in [('actual_jpeg_sha256', 'codec-actual.jpg'), ('reference_jpeg_sha256', 'codec-reference.jpg')]:
        require(report.get(key) == sha(retained[name]), 'JPEG hash disagreement')
    decoded = {name: decode(raw, report.get('srgb_icc_reference')) for name, raw in retained.items() if name.endswith('.png')}
    a = decoded['codec-actual-decoded.png']; b = decoded['codec-reference-decoded.png']
    for key, image in [('actual', a), ('reference', b)]:
        metadata = report.get(key, {})
        require(metadata.get('rgba_sha256') == image['rgba_sha256'] and metadata.get('sha256') == image['png_sha256'],
                'Native/outer PNG hash disagreement')
    comparison = compare(a, b)
    require(report.get('max_channel_delta') == comparison['maximum_channel_difference']
            and report.get('changed_pixels') == comparison['different_pixels']
            and report.get('pixel_contract_passed') is (comparison['maximum_channel_difference'] <= 2), 'Pixel replay disagreement')
    source = decode((ROOT / SOURCE).read_bytes())
    require(report.get('source', {}).get('rgba_sha256') == source['rgba_sha256']
            and report.get('source', {}).get('sha256') == SOURCE_SHA, 'Source metadata/hash disagreement')
    require(compare(source, b)['maximum_channel_difference'] > 2, 'Reference did not change original')
    channels = [0, 0, 0, 0]; over_two = 0; square = 0
    for offset in range(0, len(a['rgba']), 4):
        pixel_over = False
        for channel in range(4):
            difference = abs(a['rgba'][offset + channel] - b['rgba'][offset + channel])
            if difference > 2:
                channels[channel] += 1; pixel_over = True
            if channel < 3:
                square += difference * difference
        over_two += pixel_over
    rmse = math.sqrt(square / (1200 * 800 * 3))
    require(report.get('channels_above_two_rgba') == channels and report.get('pixels_above_two') == over_two
            and type(report.get('rgb_rmse')) in (int, float) and math.isclose(report['rgb_rmse'], rmse, abs_tol=1e-12),
            'Replayed error metrics disagree')
    return {**execution, 'comparison': comparison,
            'pixel_contract_passed': comparison['maximum_channel_difference'] <= 2}


def main():
    started = time.monotonic(); deadline = started + 870
    temp = Path(os.environ['RUNNER_TEMP'])
    require(temp.is_dir() and not temp.is_symlink(), 'Invalid runner temp')
    output = temp / 'celluloid-codec-evidence'
    require(not output.exists(), 'Refusing stale evidence directory')
    output.mkdir()
    report = {'schema': 'Celluloid.NativeCodecRun.1', 'scope': 'synthetic-pre-host-only',
        'source_sha': os.environ.get('GITHUB_SHA'), 'selected_case': SELECTION, 'passed': False,
        'run_id': os.environ.get('GITHUB_RUN_ID'), 'run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
        'native_execution_started': False, 'photos_host_executed': False, 'stage': 'source-admission', 'events': []}
    files = {}; manifest = None; before = None

    def retain(name, raw, limit):
        require(name not in files and len(raw) <= limit, 'Evidence name/individual cap')
        require(sum(v['bytes'] for v in files.values()) + len(raw) <= EVIDENCE_CAP - 32 * 1024, 'Evidence aggregate cap')
        (output / name).write_bytes(raw)
        files[name] = {'bytes': len(raw), 'sha256': sha(raw)}

    def invoke(args, seconds, label):
        require(deadline - time.monotonic() >= seconds + 15 + 30, 'Fixed phase/finalization budget exhausted')
        phase_started = time.monotonic()
        event = {'stage': label, 'limit_seconds': seconds, 'started_unix': time.time(),
            'run_id': before['run_id'], 'run_attempt': before['run_attempt']}; report['events'].append(event)
        result = run(args, timeout=seconds, check=False, echo=False, log_name='codec-' + label + '.log')
        event.update(return_code=result.returncode, finished_unix=time.time(),
            elapsed_seconds=time.monotonic() - phase_started, returned_without_timeout=True)
        return result

    try:
        require(Path.cwd().resolve() == ROOT, 'Driver must run from reviewed repository root')
        manifest, before = admit_source()
        report.update(run_id=before['run_id'], run_attempt=before['run_attempt'])
        retain('source-before.json', json.dumps(before, sort_keys=True).encode(), 4096)
        for path in ('celluloid-codec-derived', 'CelluloidNativeCodecControl.xcresult', 'celluloid-codec-attachments'):
            require(not (temp / path).exists() and not (temp / path).is_symlink(), 'Refusing stale native path')
        for label in ('toolchain', 'portable-contracts', 'build-only', 'single-native-case', 'summary', 'attachment-export'):
            for suffix in ('.log', '.log.timing.json'):
                path = temp / ('codec-' + label + suffix)
                require(not path.exists() and not path.is_symlink(), 'Refusing stale process log')
        report['stage'] = 'toolchain'
        version = invoke(['xcodebuild', '-version'], 10, 'toolchain')
        require(version.returncode == 0 and 'Xcode 27.0' in version.stdout.splitlines(), 'Stable Xcode 27.0 required')
        report['toolchain'] = version.stdout[:1024]
        report['stage'] = 'portable-contracts'
        check = invoke([sys.executable, '-m', 'unittest', 'discover', '-s', 'Scripts', '-p', 'test_mac_native_codec*.py', '-v'], 60, 'portable-contracts')
        retain('portable.log', (check.stdout + check.stderr).encode(), 16 * 1024)
        require(check.returncode == 0, 'Portable codec contracts failed')
        require(source_snapshot(ROOT, manifest) == before['source_fingerprint'], 'Portable checks changed source')
        report['stage'] = 'build-only'
        build = invoke(command(temp, 'build-for-testing'), 480, 'build-only')
        build_bytes = (build.stdout + build.stderr).encode()
        retain('build.tail.txt', build_bytes[-32 * 1024:], 32 * 1024)
        report['build_log'] = {'bytes': len(build_bytes), 'sha256': sha(build_bytes), 'tail_only': True}
        require(build.returncode == 0, 'Isolated build failed; native case not started')
        report['stage'] = 'single-native-case'; report['native_execution_started'] = True
        native = invoke(command(temp, 'test-without-building'), 120, 'single-native-case')
        log = native.stdout + '\n' + native.stderr
        require(len(log.encode()) <= 128 * 1024, 'Native transcript exceeds fixed evidence cap')
        retain('native.log', log.encode(), 128 * 1024)
        bundle = str(temp / 'CelluloidNativeCodecControl.xcresult')
        native_event = report['events'][-1]
        report['stage'] = 'native-completion-admission'
        admit_native_completion(log, native_event, bundle)
        report['stage'] = 'summary'
        summary_result = invoke(['xcrun', 'xcresulttool', 'get', 'test-results', 'summary', '--path', bundle], 30, 'summary')
        require(summary_result.returncode == 0, 'Native result summary unavailable')
        raw_summary = summary_result.stdout.encode()
        retain('summary.json', raw_summary, 32 * 1024)
        summary = load_json(raw_summary)
        report['stage'] = 'pre-export-admission'
        report['execution_admission'] = admit_export(log, summary, native_event, bundle, before)
        report['stage'] = 'attachment-export'
        folder = temp / 'celluloid-codec-attachments'
        export = invoke(['xcrun', 'xcresulttool', 'export', 'attachments', '--path', bundle, '--output-path', str(folder)], 60, 'attachment-export')
        require(export.returncode == 0, 'Native attachment export unavailable')
        raw_inventory = read_owned_png(folder / 'manifest.json')
        retain('attachment-manifest.json', raw_inventory, 32 * 1024)
        selected = attachments(folder, load_json(raw_inventory))
        for name, data in selected.items():
            retain(name, data, CAPS[name])
        report['stage'] = 'independent-replay'
        report['result'] = inspect_result(log, summary, selected, native.returncode)
        require(report['result']['accounting']['result_session_path_observation'] == bundle,
                'Native transcript names a different result bundle')
        report['passed'] = report['result']['native_passed'] and report['result']['pixel_contract_passed']
        require(report['passed'], 'Single native control failed; host lifecycle remains unqualified')
        report['stage'] = 'completed'
    except (OSError, ValueError, RuntimeError, TimeoutError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report['error'] = type(error).__name__ + ': ' + str(error)[:2000]
        if isinstance(error, TimeoutError):
            report['cleanup_unconfirmed'] = True  # No subsequent subprocess/export attempt.
    finally:
        # The existing process helper writes partial logs even on a timeout.
        # Keep a bounded diagnostic tail without treating it as complete proof.
        for label in ('build-only', 'single-native-case'):
            path = temp / ('codec-' + label + '.log')
            name = label + '.partial-tail.txt'
            attempted = {event['stage'] for event in report['events']}
            if report.get('error') and label in attempted and path.is_file() and not path.is_symlink():
                try:
                    with path.open('rb') as stream:
                        stream.seek(max(0, path.stat().st_size - 16 * 1024))
                        retain(name, stream.read(16 * 1024), 16 * 1024)
                except (OSError, ValueError) as error:
                    report['partial_log_error'] = str(error)[:1000]
        if manifest is not None and before is not None:
            try:
                after = dict(before, source_fingerprint=source_snapshot(ROOT, manifest))
                require(after['source_fingerprint'] == before['source_fingerprint'], 'Source changed after native work')
                require(sha((ROOT / MANIFEST).read_bytes()) == before['source_manifest_sha256'], 'Source manifest changed')
                after['clean_git_rechecked'] = False
                if report['passed']:
                    require(git('rev-parse', 'HEAD').decode().strip() == before['source_sha']
                            and not git('status', '--porcelain', '--untracked-files=all').strip(),
                            'Git identity/inventory changed after native work')
                    after['clean_git_rechecked'] = True
                retain('source-after.json', json.dumps(after, sort_keys=True).encode(), 4096)
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                report['passed'] = False; report['stage'] = 'source-after-failed'; report['source_after_error'] = str(error)[:1000]
        report['elapsed_seconds'] = round(time.monotonic() - started, 3)
        raw = json.dumps(report, sort_keys=True).encode()
        require(len(raw) <= 16 * 1024, 'Run receipt cap')
        retain('run.json', raw, 16 * 1024)
        envelope = json.dumps({'schema': 'Celluloid.NativeCodecEvidence.1', 'source_sha': os.environ.get('GITHUB_SHA'),
            'run_id': report['run_id'], 'run_attempt': report['run_attempt'],
            'cap_bytes': EVIDENCE_CAP, 'attachment_cap_bytes': ATTACHMENT_CAP, 'files': files,
            'diagnostic_only': True, 'complete_host_e2e': False}, sort_keys=True).encode()
        require(len(envelope) <= 16 * 1024 and sum(v['bytes'] for v in files.values()) + len(envelope) <= EVIDENCE_CAP,
                'Final evidence manifest cap')
        (output / 'manifest.json').write_bytes(envelope)
    print(json.dumps({'stage': report['stage'], 'passed': report['passed'], 'error': report.get('error')}, sort_keys=True))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
