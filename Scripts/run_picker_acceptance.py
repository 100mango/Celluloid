#!/usr/bin/env python3
"""Run one real picker UI phase and require its source-bound native receipt."""
from pathlib import Path
import argparse, hashlib, json, os, re, subprocess, sys, time, uuid
import picker_native_receipt as receipt

ROOT = Path(__file__).resolve().parents[1]
STOCK = ['CelluloidUITests/CelluloidUITests/testBeautifyOpensSystemPickerAndCancelsRepeatedly',
         'CelluloidUITests/CelluloidUITests/testPrivacyPolicyEntryRemainsAccessibleAndCanClose',
         'CelluloidUITests/PhoneEntryDesignUITests']
SEEDED = ['CelluloidUITests/CelluloidUITests/testSeededBeautifyColdOpenReopenAndOriginalSelection']

def require(value, message):
    if not value: raise ValueError(message)

def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    require(not path.exists(), 'Refusing stale evidence: ' + str(path))
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

def build_binding(binary, source_sha, source_tree):
    binary = Path(binary).resolve()
    return {'schema_version': 1, 'source_sha': source_sha, 'source_tree': source_tree,
            'app_binary_path': str(binary), 'app_binary_sha256': receipt.sha256_file(binary),
            'app_bundle_sha256': receipt.bundle_digest(binary.parent)}

def check_build(binding, binary, source_sha, source_tree):
    require(binding == build_binding(binary, source_sha, source_tree), 'Build product/source binding changed')

def unique_run(log):
    rows = re.findall(r'\bPICKER_AUTOMATION_DIAGNOSTIC run=([0-9A-Fa-f-]{36}) iteration=([123])\b', log)
    require(len(rows) == 3, 'Missing/duplicate picker iteration records')
    runs = {str(uuid.UUID(run)) for run, _ in rows}
    require(len(runs) == 1 and sorted(int(i) for _, i in rows) == [1, 2, 3], 'Ambiguous picker run identity')
    return next(iter(runs))

def runtime_warning_report(summary):
    warnings = summary.get('runtimeWarnings')
    require(isinstance(warnings, list), 'Missing official runtime-warning evidence')
    roots = ['Celluloid', 'CelluloidKit', 'CelluloidPhotoExtension', 'CelluloidTests', 'CelluloidUITests', 'Packages', 'Platforms']
    sources = [p.relative_to(ROOT).as_posix() for folder in roots for p in (ROOT / folder).rglob('*')
               if p.is_file() and p.suffix in ['.swift', '.m', '.mm', '.h']]
    records = []
    for item in warnings:
        require(isinstance(item, dict) and isinstance(item.get('message'), str), 'Malformed official runtime warning')
        raw_source = item.get('sourceURL', '')
        require(isinstance(raw_source, str), 'Malformed runtime-warning source URL')
        from urllib.parse import urlparse, unquote
        path = unquote(urlparse(raw_source).path)
        matches = [source for source in sources if path.endswith('/' + source)]
        require(len(matches) <= 1, 'Ambiguous runtime-warning source')
        if matches:
            origin = 'repository_source'
        elif path.startswith(('/Applications/Xcode', '/System/Library/', '/Library/Developer/CoreSimulator/')):
            origin = 'xcode_or_system_source'
        else:
            origin = 'unresolved_source'
        publishing = 'Publishing changes from within view updates is not allowed' in item['message']
        records.append({'sourceURL': raw_source, 'repository_path': matches[0] if matches else None,
                        'message': item['message'], 'issueType': item.get('issueType'), 'origin': origin,
                        'blocks_notice_fix': bool(matches and publishing),
                        'review_required': not bool(matches and publishing)})
    return {'total': len(records), 'blocking_notice_warning_count': sum(r['blocks_notice_fix'] for r in records),
            'other_warning_review_count': sum(r['review_required'] for r in records), 'warnings': records}

def qualify_runtime_warnings(summary):
    report = runtime_warning_report(summary)
    require(report['blocking_notice_warning_count'] == 0,
            'App-owned publication during view update: ' + json.dumps(report, sort_keys=True))
    return report

def qualify_summary(value, count, device):
    for key, expected in {'totalTestCount': count, 'passedTests': count, 'failedTests': 0,
                          'skippedTests': 0, 'expectedFailures': 0}.items():
        require(type(value.get(key)) is int and value[key] == expected, 'Unexpected UI summary: ' + key)
    require(value.get('result') == 'Passed' and not value.get('testFailures'), 'UI XCTest failed')
    qualify_runtime_warnings(value)
    rows = value.get('devicesAndConfigurations', [])
    require(len(rows) == 1 and rows[0].get('device', {}).get('deviceId') == device,
            'UI result belongs to a different simulator')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['stock', 'seeded'])
    parser.add_argument('--device', required=True)
    parser.add_argument('--derived', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--owner', required=True, type=Path)
    parser.add_argument('--build-binding', required=True, type=Path)
    parser.add_argument('--fixture-manifest', type=Path)
    args = parser.parse_args(); os.chdir(ROOT)
    owner = json.loads(args.owner.read_text()); binding = json.loads(args.build_binding.read_text())
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    source_tree = subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], text=True).strip()
    require(source == os.environ.get('GITHUB_SHA') == owner['source_sha'], 'Source/owner mismatch')
    require(owner['device_id'] == args.device, 'Wrong owned simulator')
    require(os.environ.get('TZ') == 'UTC', 'Native logging must be UTC')
    binary = args.derived.resolve() / 'Build/Products/Debug-iphonesimulator/Celluloid.app/Celluloid'
    check_build(binding, binary, source, source_tree)
    args.out.mkdir(parents=True, exist_ok=True)
    label = 'picker-' + args.phase; result = args.out / (label + '.xcresult')
    require(not result.exists(), 'Refusing stale xcresult')
    phase_deadline = min(time.monotonic() + 390, owner['work_deadline_monotonic'] - 15)
    statuses = {}; uncertainty = False

    def run(name, command, ceiling, *, simulator=False):
        nonlocal uncertainty
        require(time.monotonic() + ceiling + 10 <= phase_deadline, 'Picker phase lacks command/cleanup allowance')
        target = args.out / (label + '-' + name + '.log')
        environment = dict(os.environ, TZ='UTC', TEST_RUNNER_TZ='UTC')
        environment.pop('TEST_RUNNER_CELLULOID_SYNTHETIC_PROBE', None)
        environment.pop('TEST_RUNNER_CELLULOID_PROBE_SOURCE_SHA', None)
        with target.open('wb') as output:
            code = subprocess.call([sys.executable, 'Scripts/run_bounded.py', '--seconds', str(ceiling),
                                    '--label', label + '-' + name, *command], cwd=ROOT, env=environment,
                                   stdout=output, stderr=subprocess.STDOUT)
        statuses[name] = code
        text = target.read_text(errors='replace')
        if simulator and (code in [124, 137, 143] or 'BOUNDED_COMMAND_TIMEOUT' in text or 'CLEANUP_UNCONFIRMED' in text):
            uncertainty = True
        return code, target

    accepted = False; error = None; primary = 0
    try:
        selectors = STOCK if args.phase == 'stock' else SEEDED
        if args.phase == 'seeded': require(args.fixture_manifest is not None, 'Seeded phase requires verified fixtures')
        command = ['xcodebuild', '-project', 'Celluloid.xcodeproj', '-scheme', 'Celluloid', '-configuration', 'Debug',
                   '-destination', 'platform=iOS Simulator,id=' + args.device, '-derivedDataPath', str(args.derived),
                   '-resultBundlePath', str(result), '-parallel-testing-enabled', 'NO', '-collect-test-diagnostics', 'never',
                   *['-only-testing:' + value for value in selectors], 'test-without-building',
                   'CODE_SIGNING_ALLOWED=NO', 'CODE_SIGNING_REQUIRED=NO', 'COMPILER_INDEX_STORE_ENABLE=NO']
        primary, ui_log = run('ui', command, 240, simulator=True)
        # XCTest failure never skips the mandatory diagnostic attempt or turns green.
        summary_code, summary_log = run('summary', ['xcrun', 'xcresulttool', 'get', 'test-results', 'summary', '--path', str(result)], 30)
        summary = None
        try:
            text = summary_log.read_text(); start = text.index('{\n'); decoder = json.JSONDecoder()
            summary, _ = decoder.raw_decode(text[start:])
            write(args.out / (label + '-summary.json'), summary)
            write(args.out / (label + '-runtime-warnings.json'), runtime_warning_report(summary))
        except (ValueError, json.JSONDecodeError): pass
        native_output = args.out / (label + '-native-receipt.json')
        try:
            run_id = unique_run(ui_log.read_text(errors='replace'))
            check_build(binding, binary, source, source_tree)
            cancel_count, selected_count = (3, 0) if args.phase == 'stock' else (2, 1)
            identity = {'schema_version': 1, 'source_sha': source, 'source_tree': source_tree,
                        'app_binary_sha256': binding['app_binary_sha256'], 'app_bundle_sha256': binding['app_bundle_sha256'], 'xcresult_sha256': receipt.bundle_digest(result),
                        'runs': [{'run_id': run_id, 'expected_cancel_count': cancel_count, 'expected_selected_count': selected_count}]}
            if args.phase == 'seeded':
                identity.update(fixture_manifest_sha256=receipt.sha256_file(args.fixture_manifest), device_id=args.device,
                                ci_run_id=os.environ['GITHUB_RUN_ID'], ci_run_attempt=os.environ['GITHUB_RUN_ATTEMPT'])
            identity_path = args.out / (label + '-identity.json'); write(identity_path, identity)
            validator = [sys.executable, 'Scripts/picker_native_receipt.py', '--xcresult', str(result),
                         '--identity', str(identity_path), '--app-binary', str(binary), '--expected-source-sha', source,
                         '--expected-source-tree', source_tree, '--expected-run', f'{run_id}:{cancel_count}:{selected_count}',
                         '--runner-log-timezone', 'UTC', '--output', str(native_output),
                         '--diagnostics-output', str(args.out / (label + '-native-diagnostics'))]
            if args.fixture_manifest: validator += ['--fixture-manifest', str(args.fixture_manifest)]
            native_status, _ = run('native-receipt', validator, 60)
        except (ValueError, OSError, receipt.EvidenceError) as failure:
            native_status = 1
            if not native_output.exists(): write(native_output, {'status': 'invalid_evidence', 'error': str(failure), 'budget_seconds': 3})
            # Preserve official native diagnostics even when no attested run can be formed.
            try:
                require(time.monotonic() + 45 + 10 <= phase_deadline, 'No remaining allowance for unbound diagnostics export')
                receipt.export_diagnostics(result, args.out / (label + '-unbound-diagnostics'))
            except (ValueError, receipt.EvidenceError, OSError) as export_error:
                write(args.out / (label + '-unbound-export-error.json'), {'error': str(export_error)})
        if primary == 0 and summary_code == 0 and native_status == 0:
            require(summary is not None, 'Missing UI summary')
            qualify_summary(summary, 4 if args.phase == 'stock' else 1, args.device)
            require(json.loads(native_output.read_text()).get('status') == 'passed', 'Native receipt did not pass')
            check_build(binding, binary, source, source_tree)
            accepted = True
    except (ValueError, OSError, receipt.EvidenceError) as failure:
        error = str(failure)
    finally:
        write(args.out / (label + '-acceptance.json'), {'phase': args.phase, 'accepted': accepted,
              'native_receipt_required': True, 'command_statuses': statuses, 'original_xcode_status': primary,
              'prohibit_further_simctl': uncertainty, 'error': error, 'source_sha': source, 'source_tree': source_tree,
              'historical_XCTest_total_is_diagnostic_only': True, 'product_budget_seconds': 3})
    return 0 if accepted else (primary if primary != 0 else 1)

if __name__ == '__main__': raise SystemExit(main())
