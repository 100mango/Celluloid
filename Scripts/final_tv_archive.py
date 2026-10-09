#!/usr/bin/env python3
"""One exact Celluloid Release package diagnostic, independent of UI qualification.

The product checkout is immutable and separate from this control checkout. No
signing, Apple upload, native test run, UI replay or release approval occurs.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import time

SOURCE = '13e9a1ed63c6e7744803419f27e429a759df1209'
TREE = 'f2c6d0f38c026957b0b34f22b916eb80ed5b20a8'
CONFIG = '.github/final-tv-archive.json'
WORKFLOW = '.github/workflows/final-tv-archive.yml'
BRANCH = 'refs/heads/celluloid-final-tv-archive'
CONTROL_ROOT = Path(__file__).resolve().parents[1]
PRODUCT_ROOT = CONTROL_ROOT.parent / 'product'
NEW_PATHS = sorted([CONFIG, WORKFLOW, 'Scripts/final_tv_archive.py',
    'Scripts/test_final_tv_archive.py', 'Scripts/final_tv_archive_package.py',
    'Scripts/test_final_tv_archive_package.py'])
PHASES = {'setup': (300, 300), 'archive': (900, 1200), 'proof': (180, 1380),
          'source': (60, 1440), 'retention': (60, 1500), 'upload': (60, 1560)}
CLOCK_NAME = 'cell-final-tv-archive-clock.json'
EVIDENCE = 'cell-final-tv-archive-evidence'
MAX_EVIDENCE = 500_000
ARCHIVE_COMMAND = ['xcodebuild', '-quiet', '-project', 'CelluloidNative.xcodeproj',
    '-scheme', 'CelluloidTV', '-configuration', 'Release', '-destination', 'generic/platform=tvOS',
    '-archivePath', '.build/CelluloidTV.xcarchive', '-derivedDataPath', '.build/ArchiveDerived',
    '-jobs', '2', 'archive', 'CODE_SIGNING_ALLOWED=NO', 'COMPILER_INDEX_STORE_ENABLE=NO',
    'DEBUG_INFORMATION_FORMAT=dwarf-with-dsym']


def need(value, reason):
    if not value:
        raise ValueError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def strict_json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            need(key not in value, 'duplicate-json-key')
            value[key] = item
        return value
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite-json')))


def safe_read(path, cap):
    path = Path(path).absolute()
    parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    descriptor = None
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent); parent = child
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        before = os.fstat(descriptor)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 < before.st_size <= cap, 'unsafe-input')
        raw = b''
        while len(raw) < before.st_size:
            part = os.read(descriptor, min(65536, before.st_size - len(raw)))
            need(part, 'truncated-input'); raw += part
        def identity(value):
            return value.st_dev, value.st_ino, value.st_mode, value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns
        need(identity(before) == identity(os.fstat(descriptor)) == identity(os.stat(path.name, dir_fd=parent, follow_symlinks=False)), 'changed-input')
        return raw
    finally:
        if descriptor is not None: os.close(descriptor)
        os.close(parent)


def validate_config(value, *, enabled=True):
    need(type(value) is dict and set(value) == {'schema', 'enabled', 'scope', 'product', 'qualification'}, 'config-fields')
    need(type(value['schema']) is int and value['schema'] == 1 and value['enabled'] is enabled, 'config-closed-or-schema')
    need(value['scope'] == 'unsigned-package-diagnostic', 'config-scope')
    need(value['product'] == {'commit': SOURCE, 'tree': TREE, 'version': '1.1.1', 'build': '3'}, 'config-product')
    need(type(value['qualification']) is dict and set(value['qualification']) == {'release', 'signing', 'store', 'native_ui', 'ios_photos_host', 'mac'}, 'qualification-fields')
    need(all(item is False for item in value['qualification'].values()), 'diagnostic-cannot-qualify-release')
    return value


def validate_environment(env):
    expected = {'GITHUB_REPOSITORY': '100mango/Celluloid', 'GITHUB_REF': BRANCH,
        'GITHUB_WORKFLOW_REF': '100mango/Celluloid/' + WORKFLOW + '@' + BRANCH,
        'GITHUB_JOB': 'archive', 'GITHUB_RUN_ATTEMPT': '1',
        'DEVELOPER_DIR': '/Applications/Xcode_27.app/Contents/Developer'}
    need(all(env.get(k) == v for k, v in expected.items()), 'job-identity')
    need(env.get('GITHUB_EVENT_NAME') == 'push', 'push-only')
    head = env.get('GITHUB_SHA', '')
    need(re.fullmatch('[0-9a-f]{40}', head) is not None and env.get('GITHUB_WORKFLOW_SHA') == head, 'control-workflow-identity')
    need(re.fullmatch('[1-9][0-9]{0,19}', env.get('GITHUB_RUN_ID', '')) is not None, 'run-identity')
    return head


def admit_sources(config, env, git):
    validate_config(config)
    head = validate_environment(env)
    need(git('control', 'rev-parse', 'HEAD') == head, 'control-head')
    need(git('control', 'rev-list', '--parents', '-n', '1', 'HEAD').split() == [head, SOURCE], 'control-sole-product-parent')
    need(git('control', 'rev-parse', SOURCE + '^{tree}') == TREE, 'control-parent-tree')
    need(sorted(git('control', 'diff', '--name-status', SOURCE, 'HEAD', '--').splitlines()) == ['A\t' + path for path in NEW_PATHS], 'control-scope')
    for label in ('control', 'product'):
        need(git(label, 'status', '--porcelain', '--untracked-files=all') == '', label + '-dirty')
    need(git('product', 'rev-parse', 'HEAD') == SOURCE and git('product', 'rev-parse', 'HEAD^{tree}') == TREE, 'product-head-tree')
    return {'product_sha': SOURCE, 'product_tree': TREE, 'control_sha': head,
        'control_tree': git('control', 'rev-parse', 'HEAD^{tree}'), 'run_id': env['GITHUB_RUN_ID'],
        'run_attempt': env['GITHUB_RUN_ATTEMPT'], 'workflow_ref': env['GITHUB_WORKFLOW_REF']}


def validate_clock(value, env, now=None):
    need(type(value) is dict and set(value) == {'schema', 'control_sha', 'run_id', 'run_attempt', 'started_monotonic', 'started_unix', 'execution_budget_seconds'}, 'clock-fields')
    need(value['schema'] == 'Celluloid.FinalTVArchiveClock.1', 'clock-schema')
    need(value['control_sha'] == env['GITHUB_SHA'] and value['run_id'] == env['GITHUB_RUN_ID'] and value['run_attempt'] == env['GITHUB_RUN_ATTEMPT'], 'clock-identity')
    need(type(value['execution_budget_seconds']) is int and value['execution_budget_seconds'] == 1560, 'clock-budget')
    now = time.monotonic() if now is None else now
    for number in (value['started_monotonic'], value['started_unix'], now):
        need(type(number) in (int, float) and math.isfinite(number) and number > 0, 'clock-number')
    need(now >= value['started_monotonic'], 'clock-future')
    return value


def phase_deadline(clock, phase, now=None):
    now = time.monotonic() if now is None else now
    ceiling, end = PHASES[phase]
    result = min(now + ceiling, clock['started_monotonic'] + end)
    need(result > now, 'phase-expired-' + phase)
    return result


# The process ownership/cleanup body below is copied from the fixed product's
# mac_owned_crash.py. Only its maximum output cap is raised to 512 KiB here for
# archive logs; the product helper and all its callers remain byte-identical.
check = need

def number(value):
    return (type(value) is int and abs(value) <= 2**53) or (type(value) is float and math.isfinite(value))

def bounded_optional_process(command,command_deadline,cleanup_deadline,cap=8192,*,stop_on_signal_error=False):
    """One owned session; finite reads and absolute deadlines, including pipe EOF.

    Do not poll/reap the leader while a descendant can retain the pipe. Its PID
    stays reserved until group cleanup, so a signal cannot target a reused PID.
    No change is made to the mandatory host command or shared run_bounded helper.
    """
    check(number(command_deadline) and number(cleanup_deadline) and time.monotonic()<command_deadline<cleanup_deadline,'Invalid/expired optional process deadlines')
    check(type(cap) is int and 0<cap<=524288,'Invalid optional output cap')
    check(type(stop_on_signal_error) is bool,'Invalid signal cleanup policy')
    check(signal.getsignal(signal.SIGCHLD)==signal.SIG_DFL,'Unknown child-reaping policy')
    started=time.monotonic();data=bytearray();eof=False;reaped=False;timed_out=False;overflow=False;cleanup_error=None
    process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True,bufsize=0)
    selector=None;pipe=process.stdout
    class SignalCleanupStopped(Exception):pass
    def drain(until):
        nonlocal eof,overflow
        while not eof and not overflow and time.monotonic()<until:
            if len(data)>=cap:overflow=True;break
            events=selector.select(max(0,min(0.1,until-time.monotonic())))
            for _,_ in events:
                if time.monotonic()>=until:break
                try:part=os.read(pipe.fileno(),min(4096,cap-len(data)))
                except BlockingIOError:continue
                if not part:eof=True;break
                data.extend(part)
    def signal_group(sig):
        nonlocal cleanup_error
        if reaped:return # Never signal after releasing the leader's PID.
        try:os.killpg(process.pid,sig)
        except ProcessLookupError:pass
        except OSError as error:
            cleanup_error=type(error).__name__
            if stop_on_signal_error:raise SignalCleanupStopped() from error
    try:
        selector=selectors.DefaultSelector()
        os.set_blocking(pipe.fileno(),False);selector.register(pipe,selectors.EVENT_READ)
        drain(command_deadline)
        if eof and not overflow:
            try:process.wait(timeout=max(0,command_deadline-time.monotonic()));reaped=True
            except subprocess.TimeoutExpired:timed_out=True
        else:timed_out=not overflow
        if not reaped:
            signal_group(signal.SIGTERM)
            term_deadline=min(cleanup_deadline,time.monotonic()+1)
            if not overflow:drain(term_deadline)
            # A completed leader may leave an ignoring descendant with the pipe.
            # Signal the same owned session before reaping that leader.
            signal_group(signal.SIGKILL)
            if not overflow:drain(cleanup_deadline)
            try:process.wait(timeout=max(0,cleanup_deadline-time.monotonic()));reaped=True
            except subprocess.TimeoutExpired:cleanup_error='direct child unreaped at absolute deadline'
    except SignalCleanupStopped:
        pass # Fixed staged metadata reads never switch signals after denial.
    except (OSError,ValueError) as error:
        cleanup_error=type(error).__name__
        try:signal_group(signal.SIGKILL)
        except SignalCleanupStopped:pass
        else:
            try:process.wait(timeout=max(0,cleanup_deadline-time.monotonic()));reaped=True
            except subprocess.TimeoutExpired:pass
    finally:
        if selector is not None:selector.close()
        pipe.close()
    finished=time.monotonic()
    if finished>command_deadline and not overflow:timed_out=True
    if finished>cleanup_deadline:cleanup_error='completion observed after absolute cleanup deadline'
    return {'return_code':process.returncode,'output':bytes(data),'bytes_read':len(data),'pipe_eof':eof,
        'child_reaped':reaped,'timed_out':timed_out,'overflow':overflow,'cleanup_error':cleanup_error,
        'finalized':eof and reaped and cleanup_error is None,'elapsed_seconds':finished-started,
        'command_deadline_monotonic':command_deadline,'cleanup_deadline_monotonic':cleanup_deadline}

class Commands:
    def __init__(self):
        self.events = []
        self.blocked = False

    def run(self, argv, *, deadline, seconds, cap=8192, cleanup=3):
        need(not self.blocked, 'earlier-process-cleanup-uncertain')
        now = time.monotonic()
        end = min(deadline, now + seconds)
        need(end - now > cleanup + 0.1, 'command-cleanup-reserve')
        try:
            result = bounded_optional_process(argv, end - cleanup, end, cap=cap, stop_on_signal_error=True)
        except BaseException as error:
            self.blocked = True
            self.events.append({'argv': list(argv), 'exception': type(error).__name__, 'finalized': False,
                                'cleanup_error': 'helper raised; owned cleanup unconfirmed'})
            raise
        output = result.pop('output')
        if not result['finalized']:
            self.blocked = True
        self.events.append({'argv': list(argv), **result, 'output_sha256': digest(output),
            'output_tail': output[-16384:].decode('utf8', 'replace'), 'omitted_output_bytes': max(0, len(output) - 16384)})
        need(result['finalized'], 'command-cleanup-uncertain')
        need(not result['timed_out'] and not result['overflow'] and result['return_code'] == 0,
             'command-failed-timeout-or-output-bound: ' + str(argv[0]))
        return output


def source_binding(control, product, env, commands, deadline):
    raw = safe_read(control / CONFIG, 16384)
    config = strict_json(raw)
    def git(label, *args):
        path = control if label == 'control' else product
        need(path.is_dir() and not path.is_symlink(), 'checkout-directory')
        return commands.run(['git', '--no-pager', '-C', str(path), *args], deadline=deadline,
                            seconds=8, cap=262144).decode().strip()
    result = admit_sources(config, env, git)
    result['control_manifest_sha256'] = digest(raw)
    return result


def execute(env, clock, *, control=CONTROL_ROOT, product=PRODUCT_ROOT, checker=None):
    commands = Commands(); phase = 'setup'
    report = {'schema': 'Celluloid.FinalTVArchiveDiagnostic.1', 'scope': 'unsigned-package-diagnostic',
        'control_sha': env['GITHUB_SHA'], 'product_sha': SOURCE, 'product_tree': TREE,
        'run_id': env['GITHUB_RUN_ID'], 'run_attempt': env['GITHUB_RUN_ATTEMPT'],
        'clock': clock, 'archive_qualified': False, 'release_qualified': False,
        'signing_qualified': False, 'store_qualified': False, 'native_ui_qualified': False,
        'ios_photos_host_qualified': False, 'mac_qualified': False, 'binary_handoff': False,
        'upload_qualified': False, 'commands': commands.events,
        'debug_information_override': 'dwarf-with-dsym (archive invocation only)',
        'scope_note': 'Only this unsigned Release archive package is observed. Prior TV runtime evidence is unchanged. Final TV runtime, other platforms, signing and store qualification are separate. No archive binary is retained.'}
    try:
        deadline = phase_deadline(clock, phase)
        report['source_before'] = source_binding(control, product, env, commands, deadline)
        # Only after both exact Git checkouts and control scope are admitted do we
        # load the independently reviewed control-side package checker.
        if checker is None:
            import final_tv_archive_package as checker
            need(Path(checker.__file__).resolve() == (control / 'Scripts/final_tv_archive_package.py').resolve(), 'checker-origin')
        report['graph_before'] = checker.source_graph(product)
        need(not (product / '.build').exists() and not (product / '.build').is_symlink(), 'archive-output-not-fresh')
        (product / '.build').mkdir()
        old_cwd = Path.cwd()
        os.chdir(product)
        try:
            version = commands.run(['xcodebuild', '-version'], deadline=deadline, seconds=15).decode().strip().splitlines()
            need(version == ['Xcode 27.0', 'Build version 27A266a'], 'exact-xcode-version')
            report['xcode'] = version
            for flags in ([], ['-O']):
                for name in ('test_final_tv_archive.py', 'test_final_tv_archive_package.py'):
                    commands.run([sys.executable, '-B', *flags, '-S', str(control / 'Scripts' / name)], deadline=deadline, seconds=45, cap=65536)
            commands.run([sys.executable, '-B', '-S', 'Scripts/validate_native_sources.py'], deadline=deadline, seconds=20)
            commands.run([sys.executable, '-B', '-S', 'Scripts/validate_native_localization.py'], deadline=deadline, seconds=20)
            need(source_binding(control, product, env, commands, deadline) == report['source_before'], 'generator-source-drift')
            need(checker.source_graph(product) == report['graph_before'], 'generator-graph-drift')
            commands.run(['swift', '-swift-version', '5', 'Scripts/materialize_native_icons.swift'], deadline=deadline, seconds=90, cap=65536)
            commands.run([sys.executable, '-B', '-S', 'Scripts/verify_native_icon_inputs.py'], deadline=deadline, seconds=15)
            phase = 'archive'; deadline = phase_deadline(clock, phase)
            # 900 seconds includes the 10-second owned cleanup reserve.
            commands.run(ARCHIVE_COMMAND, deadline=deadline, seconds=900, cap=524288, cleanup=10)
            phase = 'proof'; deadline = phase_deadline(clock, phase)
            report['package'] = checker.verify_package(product, deadline, commands=commands)
            need(report['package'].get('unsigned_package_verified') is True
                 and report['package'].get('all_processes_finalized') is True
                 and report['package'].get('release_acceptance') is False
                 and report['package'].get('signing_qualified') is False, 'incomplete-package-proof')
            phase = 'source'; deadline = phase_deadline(clock, phase)
            commands.run([sys.executable, '-B', '-S', 'Scripts/verify_native_icon_inputs.py'], deadline=deadline, seconds=15)
            report['source_after'] = source_binding(control, product, env, commands, deadline)
            report['graph_after'] = checker.source_graph(product)
            need(report['source_after'] == report['source_before'] and report['graph_after'] == report['graph_before'], 'source-or-graph-changed')
            need(time.monotonic() < deadline, 'late-source-proof')
            report['archive_qualified'] = True
        finally:
            os.chdir(old_cwd)
    except (Exception, KeyboardInterrupt) as error:
        report['failure'] = {'phase': phase, 'type': type(error).__name__, 'reason': str(error)[:2048]}
        if phase == 'proof' and hasattr(error, 'events'):
            report['failed_package_processes'] = error.events
            report['package_process_cleanup_confirmed'] = error.all_processes_finalized is True
    report['driver_process_cleanup_confirmed'] = not commands.blocked
    report['finished_monotonic'] = time.monotonic()
    report['elapsed_seconds'] = report['finished_monotonic'] - clock['started_monotonic']
    return report


def retain_report(report, env, temp):
    deadline = phase_deadline(report['clock'], 'retention')
    need(time.monotonic() < deadline, 'retention-expired')
    folder = temp / EVIDENCE
    folder.mkdir(mode=0o700)
    raw = encoded(report)
    if len(raw) > MAX_EVIDENCE:
        for command in report['commands']:
            command.pop('output_tail', None)
        report['command_text_omitted_for_evidence_cap'] = True
        raw = encoded(report)
    need(len(raw) <= MAX_EVIDENCE, 'evidence-over-existing-500KB-cap')
    target = folder / 'report.json'
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream: stream.write(raw)
    need(safe_read(target, MAX_EVIDENCE) == raw and time.monotonic() < deadline, 'retention-readback')
    with open(env['GITHUB_OUTPUT'], 'a') as stream:
        stream.write('evidence_ready=true\n')
    return target


def upload_gate(mode, env, temp):
    validate_environment(env)
    report = strict_json(safe_read(temp / EVIDENCE / 'report.json', MAX_EVIDENCE))
    clock = validate_clock(report['clock'], env)
    need(report.get('schema') == 'Celluloid.FinalTVArchiveDiagnostic.1' and report.get('control_sha') == env['GITHUB_SHA']
         and report.get('product_sha') == SOURCE and report.get('product_tree') == TREE
         and report.get('run_id') == env['GITHUB_RUN_ID'] and report.get('run_attempt') == env['GITHUB_RUN_ATTEMPT'], 'upload-evidence-identity')
    need(all(report.get(key) is False for key in ('release_qualified', 'signing_qualified', 'store_qualified', 'native_ui_qualified', 'ios_photos_host_qualified', 'mac_qualified', 'binary_handoff')), 'upload-invalid-qualification')
    end = clock['started_monotonic'] + PHASES['upload'][1]
    if mode == 'admit-upload':
        need(time.monotonic() + 65 < end, 'upload-and-finalization-reserve')
        with open(env['GITHUB_OUTPUT'], 'a') as stream: stream.write('upload_admitted=true\n')
    else:
        need(env.get('CELL_ARCHIVE_UPLOAD_OUTCOME') == 'success' and time.monotonic() < end, 'upload-or-original-clock-failed')
    print(json.dumps({'action': mode, 'archive_qualified': report['archive_qualified'], 'release_qualified': False}))


def main():
    env = dict(os.environ)
    temp = Path(env['RUNNER_TEMP']).resolve(strict=True)
    clock = validate_clock(strict_json(safe_read(temp / CLOCK_NAME, 16384)), env)
    if len(sys.argv) == 2 and sys.argv[1] in ('admit-upload', 'finish-upload'):
        # No subprocess follows a potentially uncertain native cleanup. Only the
        # bounded, identity-bound JSON report is uploaded, never archive bytes.
        validate_config(strict_json(safe_read(CONTROL_ROOT / CONFIG, 16384)))
        upload_gate(sys.argv[1], env, temp); return 0
    need(len(sys.argv) == 1, 'no-user-selected-source-or-scheme')
    report = execute(env, clock)
    retain_report(report, env, temp)
    print(json.dumps({'archive_qualified': report['archive_qualified'], 'release_qualified': False, 'failure': report.get('failure')}))
    return 0 if report['archive_qualified'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
