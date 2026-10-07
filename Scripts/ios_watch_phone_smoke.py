#!/usr/bin/env python3
"""One fresh unpaired phone, one selected existing/approved XCTest, one attempt.

No signing, transfer, Watch simulator, retries, fixtures, product mutation or
binary upload. All temporary products live outside the clean source checkout.
"""
import sys
sys.dont_write_bytecode = True
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
import uuid
import xml.etree.ElementTree as ET

from ios_watch_archive_capture import CaptureStopped, capture

ROOT = Path(__file__).resolve().parents[1]
BRANCH = 'refs/heads/codex/ios-watch-phone-smoke'
WORKFLOW = '.github/workflows/ios-watch-phone-smoke.yml'
RUNTIME = 'com.apple.CoreSimulator.SimRuntime.iOS-27-0'
DEVICE_TYPE = 'com.apple.CoreSimulator.SimDeviceType.iPhone-SE-3rd-generation'
DEVICE_MODEL = 'iPhone SE (3rd generation)'
RAW_CAP = 16 * 1024 * 1024
RETAIN_CAP = 512 * 1024
SUMMARY_CAP = 256 * 1024
REPORT_CAP = 256 * 1024
PHASE_END = dict(prepare=180, build=480, device=530, test=840, proof=900,
                 cleanup=990, source_after=1020, evidence=1040)
FIXED_FILES = ('report.json', 'phases.jsonl', 'test.stdout.log',
               'test.stderr.log', 'test.errors.log', 'xcresult-summary.json')


class Rejected(ValueError):
    pass


class CommandNonzero(Rejected):
    def __init__(self, result):
        super().__init__('command-nonzero:' + str(result.returncode))
        self.returncode = result.returncode
        self.stdout = result.stdout
        self.stderr = result.stderr


def need(ok, reason):
    if not ok:
        raise Rejected(reason)


def unique(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'duplicate-json-key:' + key)
        result[key] = value
    return result


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, allow_nan=False, separators=(',', ':')) + '\n').encode()


def bounded_text(raw, budget):
    text = raw.decode('utf-8', 'replace').encode()
    if len(text) <= budget:
        return text
    mark = b'\n[TRUNCATED: retained prefix + tail; hashes cover captured original bytes]\n'
    need(budget >= len(mark), 'retention-budget-too-small')
    prefix = (budget - len(mark)) // 2
    tail = budget - len(mark) - prefix
    return text[:prefix].decode('utf-8', 'ignore').encode() + mark + text[-tail:].decode('utf-8', 'ignore').encode()


def retain_logs(output, stdout, stderr, complete):
    """Retain logs independently, before any proof or report serialization."""
    need(len(stdout) + len(stderr) <= RAW_CAP, 'raw-log-cap')
    error_lines = []
    error_bytes = 0
    errors_truncated = False
    pattern = re.compile(rb'error:|fatal error|Test Case .* (?:failed|skipped)|TEST.*FAILED|Testing failed:|timed? out|crash', re.I)
    for name, raw in [('stdout', stdout), ('stderr', stderr)]:
        for line in raw.splitlines():
            if not pattern.search(line):
                continue
            piece = name.encode() + b': ' + line[:4096] + b'\n'
            if error_bytes + len(piece) > 64 * 1024:
                errors_truncated = True
                continue
            error_lines.append(piece)
            error_bytes += len(piece)
    errors = b''.join(error_lines).decode('utf-8', 'replace').encode()[:64 * 1024]
    budget = RETAIN_CAP - len(errors)
    err_budget = min(len(stderr.decode('utf-8', 'replace').encode()), budget // 2)
    out_budget = budget - err_budget
    # Reserve enough for the truncation marker if stderr needs truncating.
    kept = {'test.stdout.log': bounded_text(stdout, out_budget),
            'test.stderr.log': bounded_text(stderr, err_budget) if stderr else b'',
            'test.errors.log': errors}
    for name, data in kept.items():
        (output / name).write_bytes(data)
    return {'capture_complete': complete, 'raw_cap': RAW_CAP, 'retention_cap': RETAIN_CAP,
            'raw_captured_bytes': len(stdout) + len(stderr),
            'stdout_sha256': hashlib.sha256(stdout).hexdigest(),
            'stderr_sha256': hashlib.sha256(stderr).hexdigest(),
            'hash_scope': 'complete original streams' if complete else 'captured prefixes only',
            'errors_truncated': errors_truncated,
            'retained': {name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                         for name, data in kept.items()}}


def verify_raw(stdout, stderr, case):
    """Reject empty/filtered/multiple/skipped/failed/duplicate raw executions."""
    target, cls, method = case.split('/')
    names = {'-[' + cls + ' ' + method + ']', '-[' + target + '.' + cls + ' ' + method + ']'}
    records = []
    text = (stdout + b'\n' + stderr).decode('utf-8', 'replace')
    pattern = re.compile(r"Test Case '([^']+)' (started\.|(passed|failed|skipped) \([0-9]+(?:\.[0-9]+)? seconds\)\.)")
    totals = []
    terminals = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('Test Case '):
            match = pattern.fullmatch(line)
            need(match is not None, 'unrecognized-testcase-record')
            records.append((match[1], 'started' if match[2] == 'started.' else match[3]))
        if line.startswith('Executed '):
            match = re.fullmatch(r'Executed (\d+) tests?, with (?:(\d+) tests? skipped and )?(\d+) failures? \((\d+) unexpected\)(?: in [0-9.]+ \([0-9.]+\) seconds)?', line)
            need(match is not None, 'unrecognized-execution-total')
            totals.append(tuple(int(value or 0) for value in match.groups()))
        if re.match(r'^\*\* TEST(?: EXECUTE)?\b', line):
            terminals.append(line)
    need(len(records) == 2 and records[0][0] in names and records[1][0] == records[0][0]
         and [row[1] for row in records] == ['started', 'passed'], 'selected-case-not-executed-once-and-passed')
    need(totals and all(value == (1, 0, 0, 0) for value in totals), 'test-total-not-exactly-one-pass')
    need(terminals == ['** TEST EXECUTE SUCCEEDED **'], 'test-terminal-not-one-success')
    need(not re.search(r'(?im)(?:^|[ :])(?:fatal )?error:|XCTAssert\w* failed|\bXCTFail\b|^Testing failed:', text), 'raw-authoritative-error')
    return {'case': case, 'case_record': records[0][0], 'executions': 1, 'passed': 1,
            'total_records': len(totals), 'terminal': terminals[0]}


def verify_summary(summary, device):
    need(isinstance(summary, dict) and summary.get('result') == 'Passed', 'summary-not-passed')
    counts = dict(totalTestCount=1, passedTests=1, failedTests=0, skippedTests=0, expectedFailures=0)
    for key, value in counts.items():
        need(type(summary.get(key)) is int and summary[key] == value, 'summary-count:' + key)
    need(summary.get('testFailures') == [], 'summary-failures-not-empty')
    for key in ('startTime', 'finishTime'):
        value = summary.get(key)
        need(type(value) in (int, float) and math.isfinite(value) and value > 0, 'summary-unfinalized-time')
    need(summary['finishTime'] > summary['startTime'], 'summary-invalid-interval')
    configs = summary.get('devicesAndConfigurations')
    need(isinstance(configs, list) and len(configs) == 1, 'summary-not-one-device')
    config = configs[0]
    actual = config.get('device', {})
    need(actual.get('deviceId', '').upper() == device.upper(), 'summary-wrong-owned-device')
    need(actual.get('modelName') == DEVICE_MODEL and actual.get('platform') == 'iOS Simulator'
         and actual.get('osVersion') == '27.0', 'summary-wrong-phone-runtime')
    for key in ('passedTests', 'failedTests', 'skippedTests', 'expectedFailures'):
        need(type(config.get(key)) is int and config[key] == counts[key], 'summary-device-count:' + key)
    return {'device': actual, 'counts': counts, 'summary_sha256': hashlib.sha256(json_bytes(summary)).hexdigest()}


def scheme_scope(root, config):
    scheme = root / config['project'] / 'xcshareddata/xcschemes' / (config['scheme'] + '.xcscheme')
    xml = ET.fromstring(scheme.read_bytes())
    target = config['case'].split('/')[0]
    testables = xml.findall('./TestAction/Testables/TestableReference/BuildableReference')
    need(sum(item.get('BlueprintName') == target for item in testables) == 1, 'missing-selected-phone-test-target')
    need(all('watch' not in item.get('BlueprintName', '').lower() for item in testables), 'watch-test-action-forbidden')
    launches = xml.findall('./LaunchAction/BuildableProductRunnable/BuildableReference')
    need(len(launches) == 1 and launches[0].get('BlueprintName') == config['scheme'], 'scheme-not-phone-launch')
    need(not xml.findall('.//PreActions') and not xml.findall('.//PostActions'), 'scheme-execution-actions-forbidden')


def build_command(config, work):
    # Generic destination builds test products without creating or booting a
    # simulator. Build completion is never evidence of a case execution.
    return ['xcodebuild', 'build-for-testing', '-project', config['project'], '-scheme', config['scheme'],
            '-configuration', 'Debug', '-destination', 'generic/platform=iOS Simulator',
            '-derivedDataPath', str(work / 'DerivedData'),
            '-clonedSourcePackagesDirPath', str(work / 'SourcePackages'),
            '-onlyUsePackageVersionsFromResolvedFile', '-only-testing:' + config['case'],
            '-jobs', '2', 'CODE_SIGNING_ALLOWED=NO', 'CODE_SIGNING_REQUIRED=NO',
            'CODE_SIGN_IDENTITY=', 'DEVELOPMENT_TEAM=', 'PROVISIONING_PROFILE=',
            'PROVISIONING_PROFILE_SPECIFIER=', 'OTHER_CODE_SIGN_FLAGS=']


def test_command(config, work, device):
    return ['xcodebuild', 'test-without-building', '-project', config['project'], '-scheme', config['scheme'],
            '-configuration', 'Debug', '-destination', 'platform=iOS Simulator,id=' + device,
            '-destination-timeout', '20', '-derivedDataPath', str(work / 'DerivedData'),
            '-clonedSourcePackagesDirPath', str(work / 'SourcePackages'),
            '-onlyUsePackageVersionsFromResolvedFile', '-resultBundlePath', str(work / 'Phone.xcresult'),
            '-only-testing:' + config['case'], '-parallel-testing-enabled', 'NO',
            '-maximum-concurrent-test-simulator-destinations', '1', '-parallel-testing-worker-count', '1',
            '-maximum-parallel-testing-workers', '1',
            '-test-timeouts-enabled', 'YES', '-default-test-execution-time-allowance', '120',
            '-maximum-test-execution-time-allowance', '150', '-collect-test-diagnostics', 'never',
            '-jobs', '2', 'CODE_SIGNING_ALLOWED=NO', 'CODE_SIGNING_REQUIRED=NO',
            'CODE_SIGN_IDENTITY=', 'DEVELOPMENT_TEAM=', 'PROVISIONING_PROFILE=',
            'PROVISIONING_PROFILE_SPECIFIER=', 'OTHER_CODE_SIGN_FLAGS=']


def source_identity(config, env, run):
    need(env.get('GITHUB_EVENT_NAME') == 'push', 'push-only')
    need(env.get('GITHUB_REPOSITORY') == config['repository'], 'repository-mismatch')
    need(env.get('GITHUB_REF') == BRANCH, 'branch-mismatch')
    need(env.get('GITHUB_RUN_ATTEMPT') == '1', 'first-attempt-only')
    sha = env.get('GITHUB_SHA', '')
    need(re.fullmatch('[0-9a-f]{40}', sha) is not None, 'invalid-source-sha')
    need(env.get('GITHUB_WORKFLOW_SHA') == sha, 'workflow-source-mismatch')
    need(env.get('GITHUB_WORKFLOW_REF') == config['repository'] + '/' + WORKFLOW + '@' + BRANCH,
         'workflow-ref-mismatch')
    head = run(['git', 'rev-parse', 'HEAD']).decode().strip()
    need(head == sha, 'checkout-head-mismatch')
    parents = run(['git', 'rev-list', '--parents', '-n', '1', 'HEAD']).decode().split()
    need(parents == [sha, config['base']], 'candidate-not-single-child-of-reviewed-base')
    need(run(['git', 'status', '--porcelain=v1', '--untracked-files=all']) == b'', 'source-dirty')
    changes = run(['git', 'diff', '--name-status', '--no-renames', config['base'], 'HEAD', '--']).decode().splitlines()
    expected = sorted(config['expected_changes'])
    need(sorted(changes) == expected, 'candidate-changed-paths-mismatch')
    tree = run(['git', 'rev-parse', 'HEAD^{tree}']).decode().strip()
    need(re.fullmatch('[0-9a-f]{40}', tree) is not None, 'invalid-source-tree')
    return {'repository': config['repository'], 'head': head, 'tree': tree, 'base': config['base'],
            'branch': BRANCH, 'attempt': 1, 'changes': changes, 'clean': True}


def verify_shutdown_state(raw, device):
    """Require fresh independent JSON evidence for the one owned UUID."""
    def finite_number(value):
        number = float(value)
        need(math.isfinite(number), 'shutdown-list-nonfinite-number')
        return number
    data = json.loads(raw, object_pairs_hook=unique, parse_constant=finite_number, parse_float=finite_number)
    need(isinstance(data, dict) and isinstance(data.get('devices'), dict), 'shutdown-list-invalid-devices')
    matches = []
    for runtime, rows in data['devices'].items():
        need(isinstance(rows, list), 'shutdown-list-invalid-runtime')
        for row in rows:
            need(isinstance(row, dict) and isinstance(row.get('udid'), str), 'shutdown-list-invalid-device')
            if row['udid'].upper() == device.upper():
                matches.append((runtime, row))
    need(len(matches) == 1, 'shutdown-list-owned-device-not-unique')
    runtime, row = matches[0]
    need(runtime == RUNTIME and row.get('state') == 'Shutdown', 'shutdown-list-owned-device-not-shutdown')
    return dict(device=device, runtime=runtime, state='Shutdown',
                evidence='independent-simctl-list', stdout_sha256=hashlib.sha256(raw).hexdigest())


def execute(config, *, env=None, root=ROOT, runner=capture, clock=time.monotonic):
    env = os.environ if env is None else env
    temp = Path(env['RUNNER_TEMP']).resolve()
    output = temp / 'ios-watch-phone-smoke-evidence'
    work = temp / 'ios-watch-phone-smoke-work'
    need(output.is_dir() and not output.is_symlink(), 'bootstrap-evidence-missing')
    initial = json.loads((output / 'report.json').read_bytes(), object_pairs_hook=unique)
    start = initial['started_monotonic']
    need(type(start) in (int, float) and math.isfinite(start) and 0 <= clock() - start < 120,
         'bootstrap-clock-invalid-or-expired')
    report = dict(schema=1, qualified=False, scope='single-unpaired-phone-navigation-only',
                  started_monotonic=start, phase_end_seconds=PHASE_END, commands=[], failures=[],
                  watch_runtime_qualified=False, paired_transfer_qualified=False,
                  signing_qualified=False, distribution_qualified=False, upload_state='required-by-final-workflow-step')
    phase = 'prepare'
    deadline = start + PHASE_END[phase]
    device = None
    native_started = False
    tested_stdout = tested_stderr = b''
    test_complete = False

    def event(kind, **values):
        item = dict(event=kind, phase=phase, elapsed_seconds=round(clock() - start, 3), **values)
        raw = json_bytes(item)
        print('PHONE_SMOKE ' + raw.decode().strip(), flush=True)
        with (output / 'phases.jsonl').open('ab') as stream:
            need(stream.tell() + len(raw) <= 64 * 1024, 'phase-log-byte-cap')
            stream.write(raw)
            stream.flush()

    def failure(error):
        report['failures'].append(dict(phase=phase, type=type(error).__name__, reason=str(error)[:2000]))
        event('failure', reason=str(error)[:2000])

    def enter(name):
        nonlocal phase, deadline
        phase = name
        deadline = start + PHASE_END[name]
        event('phase-start')

    def run(argv, *, seconds=10, cap=65536, native=False, test=False):
        nonlocal tested_stdout, tested_stderr, test_complete
        cleanup = 10 if native else 2
        grant = min(seconds, deadline - clock() - cleanup * 2)
        need(math.isfinite(grant) and grant > 0, 'command-cleanup-reserve-expired')
        receipt = dict(command=argv, phase=phase, grant_seconds=grant, cleanup_reserve_seconds=2 * cleanup, complete=False)
        # Build diagnostics stay in the fixed report, separate from test logs.
        # At most 48 KiB after worst-case JSON escaping of both 4 KiB excerpts.
        diagnostic_budget = 4096 if phase == 'build' else 8192

        def retain_diagnostics(stdout, stderr, complete):
            receipt.update(stdout=bounded_text(stdout, diagnostic_budget).decode(),
                           stderr=bounded_text(stderr, diagnostic_budget).decode())
            if phase == 'build':
                receipt.update(stdout_sha256=hashlib.sha256(stdout).hexdigest(),
                               stderr_sha256=hashlib.sha256(stderr).hexdigest(),
                               hash_scope='complete original streams' if complete else 'captured prefixes only')

        report['commands'].append(receipt)
        event('command-start', command=argv)
        began = clock()
        try:
            result = runner(argv, seconds=grant, cap=cap, cleanup_grace=cleanup)
        except CaptureStopped as error:
            receipt.update(reason=str(error), owned_cleanup_confirmed=error.cleanup_confirmed,
                           cancelled_signal=error.cancelled_signal)
            stdout = getattr(error, 'stdout_prefix', b'')
            stderr = getattr(error, 'stderr_capture', b'')
            if test:
                tested_stdout, tested_stderr = stdout, stderr
                report['test_log'] = retain_logs(output, stdout, stderr, False)
            else:
                retain_diagnostics(stdout, stderr, False)
            raise
        else:
            receipt.update(returncode=result.returncode, owned_cleanup_confirmed=True)
            if test:
                tested_stdout, tested_stderr = result.stdout, result.stderr
                test_complete = True
                report['test_log'] = retain_logs(output, result.stdout, result.stderr, True)
            else:
                retain_diagnostics(result.stdout, result.stderr, True)
            need(clock() < began + grant and clock() < deadline, 'command-late-return')
            if result.returncode != 0:
                raise CommandNonzero(result)
            receipt['complete'] = True
            return result.stdout
        finally:
            receipt['elapsed_seconds'] = round(clock() - began, 3)
            event('command-end', complete=receipt['complete'], returncode=receipt.get('returncode'), reason=receipt.get('reason'))

    try:
        enter('prepare')
        need(not work.exists() and not work.is_symlink(), 'work-directory-not-fresh')
        need(not temp.is_relative_to(root.resolve()), 'temporary-output-inside-source')
        work.mkdir()
        report['source_before'] = source_identity(config, env, run)
        scheme_scope(root, config)
        need(env.get('DEVELOPER_DIR') == '/Applications/Xcode_27.app/Contents/Developer', 'developer-directory-mismatch')
        report['toolchain'] = run(['xcodebuild', '-version']).decode().strip()
        need(report['toolchain'].splitlines() == ['Xcode 27.0', 'Build version 27A266a'], 'xcode-build-mismatch')
        enter('build')
        run(build_command(config, work), seconds=300, cap=RAW_CAP, native=True)
        report['build_for_testing_complete'] = True
        enter('device')
        native_started = True
        created = run(['xcrun', 'simctl', 'create', 'Phone smoke ' + env['GITHUB_RUN_ID'], DEVICE_TYPE, RUNTIME],
                      seconds=30, native=True).decode().strip()
        device = str(uuid.UUID(created)).upper()
        need(created.upper() == device, 'unexpected-create-response')
        report['device'] = dict(id=device, type=DEVICE_TYPE, runtime=RUNTIME, fresh=True, pairing_requested=False)
        enter('test')
        run(test_command(config, work, device), seconds=600, cap=RAW_CAP, native=True, test=True)
    except (Exception, KeyboardInterrupt) as error:
        # A create interrupted after emitting its one UUID can still be cleaned
        # up without discovery or a second candidate. Never guess an identity.
        if device is None and native_started:
            for receipt in report['commands']:
                if receipt['command'][:3] == ['xcrun', 'simctl', 'create']:
                    value = receipt.get('stdout', '').strip()
                    if re.fullmatch(r'[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}', value):
                        device = str(uuid.UUID(value)).upper()
                        report['device'] = dict(id=device, type=DEVICE_TYPE, runtime=RUNTIME,
                                                fresh=True, pairing_requested=False, recovered_create_output=True)
        failure(error)
    # Diagnostics are attempted once even after a failing xcodebuild exit. Their
    # failure cannot delete the fixed raw-log excerpts retained above.
    if device and (work / 'Phone.xcresult').is_dir() and test_complete:
        try:
            enter('proof')
            raw = run(['xcrun', 'xcresulttool', 'get', 'test-results', 'summary', '--path', str(work / 'Phone.xcresult')],
                      seconds=35, cap=SUMMARY_CAP, native=True)
            (output / 'xcresult-summary.json').write_bytes(raw)
            summary = json.loads(raw, object_pairs_hook=unique)
            report['summary_proof'] = verify_summary(summary, device)
            report['raw_proof'] = verify_raw(tested_stdout, tested_stderr, config['case'])
        except (Exception, KeyboardInterrupt) as error:
            failure(error)
    else:
        report['failures'].append(dict(phase='proof', reason='complete-test-capture-and-result-required'))
    try:
        enter('cleanup')
        if device:
            report['simulator_cleanup'] = []
            for action in ('shutdown', 'delete'):
                try:
                    state_proof = None
                    try:
                        run(['xcrun', 'simctl', action, device], seconds=25, native=True)
                    except CommandNonzero as error:
                        # Only the observed already-Shutdown error is eligible.
                        # Neither stderr alone nor process exit proves device state.
                        expected = (b'An error was encountered processing the command (domain=com.apple.CoreSimulator.SimError, code=405):\n'
                                    b'Unable to shutdown device in current state: Shutdown\n')
                        if action != 'shutdown' or error.returncode != 149 or error.stdout != b'' or error.stderr != expected:
                            raise
                        listed = run(['xcrun', 'simctl', 'list', 'devices', '--json'],
                                     seconds=15, cap=SUMMARY_CAP, native=True)
                        state_proof = verify_shutdown_state(listed, device)
                    row = dict(action=action, confirmed=True)
                    if state_proof is not None:
                        row.update(already_shutdown=True, shutdown_returncode=149, state_proof=state_proof)
                    report['simulator_cleanup'].append(row)
                except (Exception, KeyboardInterrupt) as error:
                    report['simulator_cleanup'].append(dict(action=action, confirmed=False, reason=str(error)))
                    failure(error)
            need(all(row['confirmed'] for row in report['simulator_cleanup']), 'owned-simulator-cleanup-not-confirmed')
        else:
            need(not native_started, 'simulator-creation-ownership-not-confirmed')
    except (Exception, KeyboardInterrupt) as error:
        failure(error)
    try:
        enter('source_after')
        report['source_after'] = source_identity(config, env, run)
        need(report.get('source_before') == report['source_after'], 'source-changed-during-run')
    except (Exception, KeyboardInterrupt) as error:
        failure(error)
    enter('evidence')
    report['elapsed_seconds'] = clock() - start
    report['qualified'] = not report['failures'] and bool(report.get('raw_proof')) and bool(report.get('summary_proof'))
    if clock() >= deadline:
        report['qualified'] = False
        report['failures'].append(dict(phase=phase, reason='evidence-deadline-exceeded'))
    # Fixed logs and phase events have already been persisted. No packing gate
    # or evidence_ready marker controls the workflow's unconditional upload.
    try:
        raw = json_bytes(report)
        need(len(raw) <= REPORT_CAP, 'report-byte-cap')
        (output / 'report.json').write_bytes(raw)
    except Exception as error:
        report = dict(schema=1, qualified=False, packing_failure=str(error),
                      logs_retained_separately=True, started_monotonic=start)
        (output / 'report.json').write_bytes(json_bytes(report))
    event('finished', qualified=report['qualified'])
    return report


def main():
    need(len(sys.argv) == 1, 'no-user-selectors-or-retries')
    os.chdir(ROOT)
    config = json.loads((Path(__file__).resolve().parent / 'ios_watch_phone_smoke_config.json').read_bytes(), object_pairs_hook=unique)
    try:
        result = execute(config)
    except (Exception, KeyboardInterrupt) as error:
        # Bootstrap report/log files remain available even if initialization
        # or evidence writing itself is impossible. Never replace failure green.
        print('PHONE_SMOKE_FATAL ' + type(error).__name__ + ': ' + str(error), flush=True)
        return 1
    return 0 if result['qualified'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
