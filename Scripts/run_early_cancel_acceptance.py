#!/usr/bin/env python3
"""One bounded startup-diagnosis retest under standing free-test authorization.

The original two opportunities and the explicit extra opportunity are consumed.
This route permits one separate retest on a fresh owned device. It never reruns
Photos, relabels previous failures, or qualifies release. No scheduling/retry mode.
"""
from pathlib import Path
from contextlib import contextmanager
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid

import run_swiftui_acceptance as full
import picker_native_receipt as native
from run_ios_photos_host import product_control
from run_picker_acceptance import build_binding as base_build_binding

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/early-cancel-acceptance'
DERIVED = ROOT / '.build/early-cancel-ios'
WORKFLOW = '.github/workflows/swiftui-first-native.yml'
BRANCH = 'cell-ios-early-cancel-startup-20261015'
BASE = '7bd2e23afb0ad0805de6cdb8adb27b0df7153a66'
BASE_TREE = 'acd3c47970657cb3e50be198f0ac640cee29c4be'
UI_PATH = 'CelluloidUITests/CelluloidUITests.swift'
SOURCE_PATHS = {WORKFLOW, UI_PATH, 'Scripts/native_action_binder.py', 'Scripts/early_cancel_receipt.py',
    'Scripts/run_early_cancel_acceptance.py', 'Scripts/test_early_cancel_acceptance.py'}
INSERTION_SHA256 = 'f041f635d2737e929a5096bbcfecb74c0fb71a4d47860c37764a4c67200874d6'
SELECTOR = 'CelluloidUITests/CelluloidUITests/testStockPickerEarlyCancelCompletesWithinOpeningWindow'
MODEL = 'iPhone SE (3rd generation)'
RUNTIME = 'com.apple.CoreSimulator.SimRuntime.iOS-27-0'
UI_PHASE_SECONDS = 480  # Startup/test orchestration only; all input-to-home gates remain 3 seconds.
POST_UI_RESERVE_SECONDS = 330  # Existing collectors/local checks plus admission/I/O margin, inside 2100.
DEBUG_DYLIB_NAME = 'Celluloid.debug.dylib'
QUARANTINED_WORKER = 'e2cd55b4-3f62-4054-9430-6fdb5ac3b4e9'
SETUP_INFO_MAX_BYTES = 65536
PRODUCT = (424, '8fb8b5d2f59884986f823e87256980b10a660bf8396cc40bc475f7036e055926')
require, save, extract_json = full.require, full.save, full.extract_json


def read_ancestor_ps(pid, deadline):
    """One fixed read-only ps query, with no implicit pipe/context-manager reap."""
    began = time.monotonic(); span = min(1.0, deadline - began)
    require(span > 0, 'Runner ancestor lookup deadline exhausted')
    slack = min(0.1, span / 5)
    phase_deadline = min(began + span, deadline - slack)
    wait_deadline = phase_deadline - 2 * slack; reap_deadline = phase_deadline - slack
    process = None
    with local_bound(phase_deadline - time.monotonic(), 'runner-ancestor-ps'):
        # Unbuffered regular storage avoids communicate()/PIPE drain and never
        # publishes process metadata. Only <=8192-byte responses are accepted.
        with tempfile.TemporaryFile(mode='w+b', buffering=0) as output:
            require(stat.S_ISREG(os.fstat(output.fileno()).st_mode), 'Runner ancestor output is not regular')
            try:
                require(time.monotonic() < wait_deadline, 'Expired before runner ancestor lookup')
                process = subprocess.Popen(['/bin/ps', '-p', str(pid), '-o', 'ppid=', '-o', 'comm='],
                    stdout=output, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
                remaining = wait_deadline - time.monotonic()
                require(remaining > 0, 'Expired before runner ancestor wait')
                code = process.wait(timeout=remaining)
                require(type(code) is int and code == 0, 'Runner ancestor lookup failed')
                require(os.fstat(output.fileno()).st_size <= 8192, 'Oversized runner ancestor response')
                output.seek(0); raw = output.read(8193)
                require(len(raw) <= 8192 and time.monotonic() < phase_deadline, 'Runner ancestor output exceeded its bound')
                return raw
            except BaseException as failure:
                # No Popen __exit__, communicate, or timeout=None wait exists.
                # An alarm/unknown exit always rejects identity and native work.
                remaining = reap_deadline - time.monotonic()
                if process is not None and remaining > 0:
                    try:
                        with local_bound(remaining, 'runner-ancestor-ps-reap'):
                            if process.poll() is None:
                                process.kill()
                                remaining = reap_deadline - time.monotonic()
                                if remaining > 0: process.wait(timeout=remaining)
                    except BaseException: pass  # Cleanup uncertainty cannot authorize native work.
                if isinstance(failure, (KeyboardInterrupt, SystemExit)): raise
                raise ValueError('Runner ancestor lookup unavailable, timed out, or cleanup unconfirmed') from None


def runner_isolation(environment, deadline):
    """Read only our ancestor worker's public setup identity; never credentials.

    actions/runner v2.337.0 HostContext.cs: Bin is the entry assembly directory,
    Root is its parent, SetupInfo is Root/.setup_info. JobExtension.cs exposes
    non-_internal_ Group/Detail records in Set up job. Unsupported layouts fail.
    The caller supplies a 15-second local bound inside the existing work budget.
    """
    require(environment.get('RUNNER_ENVIRONMENT') == 'github-hosted', 'Runner isolation requires github-hosted')
    pid = os.getpid(); seen = set(); workers = []
    for _ in range(24):
        require(pid > 0 and pid not in seen, 'Unverifiable runner ancestor chain')
        seen.add(pid)
        raw = read_ancestor_ps(pid, deadline)
        require(len(raw) <= 8192, 'Oversized runner ancestor response')
        try: rows = raw.decode('utf-8').strip().splitlines()
        except UnicodeError: raise ValueError('Invalid runner ancestor response') from None
        require(len(rows) == 1, 'Ambiguous runner ancestor response')
        fields = rows[0].strip().split(None, 1)
        require(len(fields) == 2 and re.fullmatch(r'[0-9]+', fields[0]), 'Malformed runner ancestor response')
        comm = fields[1]; path = Path(comm)
        if path.name == 'Runner.Worker': workers.append(path)
        pid = int(fields[0])
        if pid == 0: break
    else: raise ValueError('Runner ancestor chain exceeded its bound')
    require(len(workers) == 1, 'Missing or ambiguous actual Runner.Worker ancestor')
    worker = workers[0]
    require(worker.is_absolute() and worker.parent.name == 'bin' and worker.resolve(strict=True) == worker
            and worker.is_file() and not worker.is_symlink(), 'Unsupported actual Runner.Worker path')
    setup = worker.parent.parent / '.setup_info'
    try:
        with os.fdopen(os.open(setup, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
            before = os.fstat(stream.fileno())
            require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= SETUP_INFO_MAX_BYTES,
                    'Runner setup identity is not a bounded regular file')
            raw = stream.read(SETUP_INFO_MAX_BYTES + 1); after = os.fstat(stream.fileno())
        require(len(raw) == before.st_size and len(raw) <= SETUP_INFO_MAX_BYTES
                and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
                    (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'Runner setup identity changed while reading')
        def unique_keys(pairs):
            value = {}
            for key, item in pairs:
                key = key.casefold()
                require(key not in value, 'Ambiguous runner setup identity keys')
                value[key] = item
            return value
        records = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=unique_keys)
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ValueError('Runner setup identity unreadable or unsupported') from None
    require(isinstance(records, list) and all(isinstance(row, dict) for row in records), 'Malformed runner setup identity')
    public = [row for row in records if isinstance(row.get('group'), str)
              and row['group'].casefold() == 'runner image provisioner']
    require(len(public) == 1 and public[0]['group'] == 'Runner Image Provisioner', 'Missing or ambiguous public runner provisioner group')
    detail = public[0].get('detail')
    require(isinstance(detail, str), 'Missing public runner provisioner detail')
    lines = detail.replace('\r\n', '\n').strip().splitlines()
    require(lines.count('Hosted Compute Agent') == 1, 'Runner provisioner is not Hosted Compute Agent')
    pattern = r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
    ids = re.findall(pattern, detail)
    worker_lines = [line for line in lines if line.startswith('Worker ID:')]
    require(len(ids) == 1 and len(worker_lines) == 1 and
            re.fullmatch(r'Worker ID: (?:' + pattern + r'|\{' + pattern + r'\})', worker_lines[0]),
            'Missing or ambiguous public Worker ID')
    worker_id = str(uuid.UUID(ids[0]))
    require(worker_id != QUARANTINED_WORKER and uuid.UUID(worker_id).int != 0, 'Quarantined or invalid worker is forbidden')
    require(time.monotonic() < deadline, 'Runner isolation deadline exhausted')
    public_hash = hashlib.sha256(json.dumps({'Group': public[0]['group'], 'Detail': detail},
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'schema': 'celluloid.runner-isolation.v1', 'worker_id': worker_id,
        'different_from_quarantined_worker': True, 'runner_environment': 'github-hosted',
        'provisioner': 'Hosted Compute Agent', 'public_setup_group_sha256': public_hash,
        'ancestor_count': len(seen), 'source': 'actual Runner.Worker ancestor root/.setup_info',
        'setup_other_groups_retained': False, 'process_arguments_or_environment_dumped': False}


def build_binding(binary, source_sha, source_tree):
    """This fixed Debug target has a launcher plus its required main dylib."""
    binding = base_build_binding(binary, source_sha, source_tree)
    dylib = Path(binary).parent / DEBUG_DYLIB_NAME
    binding.update(app_debug_dylib_sha256=native.sha256_file(dylib),
                   app_debug_dylib_path=str(dylib.resolve()))
    return binding


def check_build(binding, binary, source_sha, source_tree):
    require(binding == build_binding(binary, source_sha, source_tree), 'Build product/source binding changed')


@contextmanager
def local_bound(seconds, label):
    """POSIX interruption for local Git/hash/receipt work; never grants time."""
    require(seconds > 0, label + ': no time remains')
    previous = signal.getsignal(signal.SIGALRM)
    timer, interval = signal.getitimer(signal.ITIMER_REAL); began = time.monotonic()
    effective = min(seconds, timer) if timer > 0 else seconds
    def expired(signum, frame): raise TimeoutError(label + ': local deadline exceeded')
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, effective)
    try: yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        if timer > 0: signal.setitimer(signal.ITIMER_REAL, max(0.000001, timer - (time.monotonic() - began)), interval)


def stop_owned(process, deadline):
    """Same owned-group TERM/KILL pattern; every wait is inside a fixed cap."""
    actions = []
    if process.poll() is not None: return actions
    for sig in [signal.SIGTERM, signal.SIGKILL]:
        if time.monotonic() >= deadline: break
        try: os.killpg(process.pid, sig)
        except ProcessLookupError:
            actions.append({'signal': sig.name, 'outcome': 'absent'}); break
        except OSError as error:
            actions.append({'signal': sig.name, 'outcome': 'denied_or_error', 'error': str(error)}); break
        actions.append({'signal': sig.name, 'outcome': 'sent'})
        remaining = min(5, deadline - time.monotonic())
        if remaining <= 0: break
        try: process.wait(timeout=remaining)
        except subprocess.TimeoutExpired: continue
        else: break
    return actions


def validate_context(environment):
    expected = {'GITHUB_REPOSITORY': '100mango/Celluloid', 'GITHUB_EVENT_NAME': 'push',
        'GITHUB_REF': 'refs/heads/' + BRANCH, 'GITHUB_RUN_ATTEMPT': '1',
        'GITHUB_WORKFLOW_REF': '100mango/Celluloid/' + WORKFLOW + '@refs/heads/' + BRANCH,
        'DEVELOPER_DIR': '/Applications/Xcode_27.app/Contents/Developer'}
    require(all(environment.get(key) == value for key, value in expected.items()),
            'Wrong early-Cancel route, toolchain, or workflow rerun')
    require(re.fullmatch(r'[1-9][0-9]*', environment.get('GITHUB_RUN_ID', '')), 'Missing CI run identity')
    for key in ['GITHUB_SHA', 'GITHUB_WORKFLOW_SHA', 'CELLULOID_EARLY_CANCEL_SOURCE', 'CELLULOID_EARLY_CANCEL_SOURCE_TREE']:
        require(re.fullmatch(r'[0-9a-f]{40}', environment.get(key, '')), 'Closed or malformed exact source pin: ' + key)
    require(environment['GITHUB_SHA'] == environment['GITHUB_WORKFLOW_SHA'], 'Workflow source mismatch')
    allowed = {'CELLULOID_EARLY_CANCEL_SOURCE', 'CELLULOID_EARLY_CANCEL_SOURCE_TREE'}
    require(not any(value and (key.startswith('CELLULOID_') or key.startswith('TEST_RUNNER_CELLULOID_'))
                    and key not in allowed for key, value in environment.items()),
            'Continuation, probe, or unreviewed Celluloid override is forbidden')


def validate_lineage(environment, facts):
    """Pure validator: source -> pin-only CLOSED commit -> guard-only activation."""
    validate_context(environment)
    source, tree = environment['CELLULOID_EARLY_CANCEL_SOURCE'], environment['CELLULOID_EARLY_CANCEL_SOURCE_TREE']
    require(facts['head'] == environment['GITHUB_SHA'] and facts['source'] == source
            and facts['source_tree'] == tree, 'Exact reviewed source/checkout identity differs')
    require(facts['activation_parents'] == [facts['closed']] and facts['closed_parents'] == [source],
            'Expected only source, CLOSED control, and activation; merges are forbidden')
    require(facts['source_parents'] == [BASE] and facts['base_tree'] == BASE_TREE
            and set(facts['source_paths']) == SOURCE_PATHS, 'Source differs from the reviewed six-path Full successor')
    ui = facts['source_ui']; start = ui.find('    /// OFFLINE CANDIDATE ONLY.')
    end = ui.find('    func testBeautifyOpensSystemPickerAndCancelsRepeatedly()', start)
    require(start >= 0 and end > start and hashlib.sha256(ui[start:end].encode()).hexdigest() == INSERTION_SHA256
            and ui[:start] + ui[end:] == facts['base_ui'], 'Original UI tests changed or insertion differs')
    require(facts['closed_paths'] == [WORKFLOW] and facts['activation_paths'] == [WORKFLOW],
            'Control commits changed more than the workflow')
    original = facts['source_workflow']
    before = ['CELLULOID_EARLY_CANCEL_SOURCE: CLOSED', 'CELLULOID_EARLY_CANCEL_SOURCE_TREE: CLOSED']
    after = ['CELLULOID_EARLY_CANCEL_SOURCE: ' + source, 'CELLULOID_EARLY_CANCEL_SOURCE_TREE: ' + tree]
    require(all(original.count(token) == 1 for token in before), 'Source workflow pins were not exactly CLOSED')
    pinned = original
    for old, new in zip(before, after): pinned = pinned.replace(old, new, 1)
    require(facts['closed_workflow'] == pinned, 'CLOSED commit changed bytes beyond the two source pins')
    guard = '    if: ${{ false }}'
    require(pinned.count(guard) == 1 and facts['workflow'] == pinned.replace(guard, '    if: ${{ true }}', 1),
            'Activation changed bytes beyond the single CLOSED guard')
    require(not facts['dirty'], 'Checkout has tracked or untracked changes')


def source_snapshot(environment):
    """Bounded existing Git checks plus a full tracked-byte/product fingerprint."""
    validate_context(environment)
    deadline = time.monotonic() + 30
    def git(*arguments, strip=True):
        remaining = min(5, deadline - time.monotonic())
        require(remaining > 0, 'Source check deadline exhausted')
        result = subprocess.check_output(['git', *arguments], cwd=ROOT, text=True, timeout=remaining)
        return result.strip() if strip else result
    head = git('rev-parse', 'HEAD')
    closed = git('rev-parse', 'HEAD^')
    source = git('rev-parse', 'HEAD^^')
    facts = {'head': head, 'tree': git('rev-parse', 'HEAD^{tree}'), 'closed': closed, 'source': source,
        'source_tree': git('rev-parse', source + '^{tree}'), 'base_tree': git('rev-parse', BASE + '^{tree}'),
        'source_parents': git('rev-list', '--parents', '-n', '1', source).split()[1:],
        'source_paths': git('diff', '--name-only', BASE, source).splitlines(),
        'source_ui': git('show', source + ':' + UI_PATH, strip=False),
        'base_ui': git('show', BASE + ':' + UI_PATH, strip=False),
        'activation_parents': git('rev-list', '--parents', '-n', '1', head).split()[1:],
        'closed_parents': git('rev-list', '--parents', '-n', '1', closed).split()[1:],
        'closed_paths': git('diff', '--name-only', source, closed).splitlines(),
        'activation_paths': git('diff', '--name-only', closed, head).splitlines(),
        'source_workflow': git('show', source + ':' + WORKFLOW, strip=False),
        'closed_workflow': git('show', closed + ':' + WORKFLOW, strip=False),
        'workflow': git('show', head + ':' + WORKFLOW, strip=False),
        'dirty': git('status', '--porcelain', '--untracked-files=all')}
    validate_lineage(environment, facts)
    rows = []
    for name in git('ls-files', '-z', strip=False).split('\0'):
        if not name: continue
        path = ROOT / name
        require(path.is_file() and not path.is_symlink(), 'Missing or symlinked tracked source: ' + name)
        rows.append([name, hashlib.sha256(path.read_bytes()).hexdigest()])
    require(time.monotonic() <= deadline, 'Tracked-byte source check exceeded its bound')
    product = product_control(ROOT)
    require(product == PRODUCT, 'Frozen product bytes or membership changed')
    require(time.monotonic() <= deadline, 'Product source check exceeded its bound')
    return {'schema': 'celluloid.early-cancel.source.v1', 'source_sha': head, 'source_tree': facts['tree'],
        'reviewed_source_sha': source, 'reviewed_source_tree': facts['source_tree'], 'closed_control_sha': closed,
        'product_files': product[0], 'product_sha256': product[1], 'tracked_files': rows,
        'tracked_sha256': hashlib.sha256(json.dumps(rows, separators=(',', ':')).encode()).hexdigest()}


def unique_run(log):
    rows = re.findall(r'\bPICKER_CANCEL_CYCLE_UI run=([0-9A-Fa-f-]{36}) iteration=([0-3]) event=([a-z-]+)\b', log)
    require(rows, 'No observed early-Cancel run UUID')
    runs = {str(uuid.UUID(run)) for run, _, _ in rows}
    require(len(runs) == 1 and sum(iteration == '0' and event == 'run-begin' for _, iteration, event in rows) == 1,
            'Missing, duplicate, or ambiguous actual early-Cancel run')
    # Completion/count/timing must come from the strict official native binder,
    # not this identifier extraction or a successful XCTest exit code.
    return next(iter(runs))


def native_uncertain(code, log, elapsed, maximum):
    return (type(code) is not int or code < 0 or code == 124 or 128 <= code <= 255
        or elapsed > maximum or 'BOUNDED_COMMAND_TIMEOUT' in log or 'CLEANUP_UNCONFIRMED' in log
        or re.search(r'(?:exceeded (?:the )?execution time allowance|test(?: execution)? timed out)', log, re.I) is not None)


class EarlyCancel(full.Acceptance):
    def __init__(self):
        validate_context(os.environ)
        self.preview_only = False  # This route never borrows preview authorization or semantics.
        self.work_seconds = 2100
        self.started = time.monotonic(); self.deadline = self.started + self.work_seconds
        self.device = None; self.uncertain = False; self.events = []; self.failures = []
        self.source = os.environ['GITHUB_SHA']; self.source_tree = ''; self.snapshot = None
        self.binding = None; self.binary = None; self.receipt_passed = False
        self.cleanup_events = []; self.cleanup_verified = False; self.ui_dispatched = False
        require(not OUT.exists() and not OUT.is_symlink(), 'Refusing existing early-Cancel evidence directory')
        require(not DERIVED.exists() and not DERIVED.is_symlink(), 'Refusing existing early-Cancel build products')
        OUT.mkdir(parents=True)

    def mark_uncertain(self, reason, deadline=None):
        self.uncertain = True  # Latch before every attempted receipt write.
        remaining = 1 if deadline is None else min(1, deadline - time.monotonic())
        if remaining <= 0: return
        path = OUT / 'native-uncertainty.json'
        try:
            if not path.exists():
                with local_bound(remaining, 'uncertainty-receipt'):
                    save(path, {'uncertain': True, 'reason': reason, 'prohibit_further_simctl': True,
                        'group_exit_confirmed': False, 'source_sha': self.source})
        except OSError: pass  # A failed disk write cannot authorize more native work.

    def owned_command(self, name, command, seconds, deadline):
        """Direct child ownership avoids the old fallback's unbounded final wait.

        Only this new route uses this narrow copy of the reviewed group cleanup
        pattern. Ten seconds of the phase maximum are reserved for teardown.
        Reaping the child never claims that simulator descendants are stopped.
        """
        target = OUT / (name + '.log'); began = time.monotonic()
        deadline = min(deadline, began + seconds); native_deadline = deadline - 10
        # The ordinary wait returns one second before the native SIGALRM.
        # Cleanup ends two seconds before the outer alarm for log/receipt I/O.
        # Neither slack extends the phase or its original ten-second teardown.
        wait_deadline = native_deadline - 1; cleanup_deadline = deadline - 2
        require(wait_deadline > began, 'Insufficient owned-command teardown reserve')
        require(not target.exists(), 'No repeated phase or stale log: ' + name)
        process = None; cleanup = []; code = None; cleanup_attempted = False
        try:
            with local_bound(deadline - time.monotonic(), name):
                try:
                    # Opening the log, Popen and ownership-receipt I/O must all
                    # leave the same ten-second owned teardown reserve intact.
                    with local_bound(native_deadline - time.monotonic(), name + '-native'):
                        with target.open('wb') as output:
                            require(time.monotonic() < native_deadline, 'Expired before native dispatch')
                            process = subprocess.Popen(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                start_new_session=True, env=dict(os.environ, TZ='UTC', TEST_RUNNER_TZ='UTC'))
                            save(OUT / ('owned-process-' + name + '.json'), {'pid': process.pid, 'pgid': process.pid,
                                'start_new_session': True, 'phase_deadline_monotonic': deadline,
                                'native_deadline_monotonic': native_deadline, 'wait_deadline_monotonic': wait_deadline,
                                'cleanup_deadline_monotonic': cleanup_deadline, 'source_sha': self.source,
                                'run_id': os.environ['GITHUB_RUN_ID'], 'group_exit_confirmed': False})
                            remaining = wait_deadline - time.monotonic()
                            if remaining <= 0: raise subprocess.TimeoutExpired(command, seconds)
                            code = process.wait(timeout=remaining)
                except BaseException as failure:
                    self.mark_uncertain(type(failure).__name__ + ': ' + name, deadline)
                    timed_out = isinstance(failure, (subprocess.TimeoutExpired, TimeoutError))
                    self.failures.append({'phase': name, 'exit_code': 124 if timed_out else None,
                        'error': type(failure).__name__, 'group_exit_confirmed': False})
                    cleanup_attempted = True
                    if process is not None: cleanup = stop_owned(process, min(cleanup_deadline, time.monotonic() + 10))
                    if timed_out: code = 124
                    else: raise
                if native_uncertain(code, '', time.monotonic() - began, seconds): self.mark_uncertain('Untrusted native exit: ' + name, deadline)
            elapsed = time.monotonic() - began
            if native_uncertain(code, '', elapsed, seconds): self.mark_uncertain('Late/untrusted native exit: ' + name, deadline)
            with local_bound(min(5, deadline - time.monotonic()), name + '-log'):
                log = target.read_text(errors='replace')
            if native_uncertain(code, log, elapsed, seconds): self.mark_uncertain('Native uncertainty marker: ' + name, deadline)
            with local_bound(min(2, deadline - time.monotonic()), name + '-final-owner'):
                child_code = process.poll()
                self.last_owned = {'pid': process.pid, 'pgid': process.pid, 'start_new_session': True,
                    'phase_deadline_monotonic': deadline, 'native_deadline_monotonic': native_deadline,
                    'wait_deadline_monotonic': wait_deadline, 'cleanup_deadline_monotonic': cleanup_deadline,
                    'cleanup_actions': cleanup, 'child_reaped': type(child_code) is int,
                    'child_returncode': child_code if type(child_code) is int else None,
                    'group_exit_confirmed': False}
                save(OUT / ('owned-process-' + name + '.json'), {**self.last_owned,
                    'source_sha': self.source, 'run_id': os.environ['GITHUB_RUN_ID'], 'uncertain': self.uncertain})
        except BaseException:
            self.mark_uncertain('Interrupted owned command: ' + name, deadline)
            if process is not None and not cleanup_attempted and time.monotonic() < cleanup_deadline:
                with local_bound(cleanup_deadline - time.monotonic(), name + '-abort'):
                    stop_owned(process, min(cleanup_deadline, time.monotonic() + 10))
            raise
        return code, log, time.monotonic() - began

    def command(self, name, command, seconds, simulator=False, allow_failure=False, nested_owned=False):
        require(not nested_owned, 'No nested simulator runner in the cold sequence')
        if name == 'early-cancel-ui':
            require(seconds == UI_PHASE_SECONDS, 'Unexpected UI orchestration budget')
            require(self.deadline - time.monotonic() >= seconds + POST_UI_RESERVE_SECONDS,
                    'UI orchestration and existing evidence reserve do not fit; no dispatch')
        self.admit(name, seconds, simulator)
        code, log, elapsed = self.owned_command(name, command, seconds, self.deadline)
        self.events.append({'phase': name, 'exit_code': code, 'elapsed_seconds': elapsed,
            'maximum_seconds': seconds, 'simulator': simulator, 'uncertain': self.uncertain, **self.last_owned})
        with local_bound(min(5, self.deadline - time.monotonic()), name + '-receipt'):
            save(OUT / 'phases.json', self.events)
        print('ACCEPTANCE_PHASE_END', json.dumps(self.events[-1]), flush=True)
        if code != 0 or elapsed > seconds: self.failures.append({'phase': name, 'exit_code': code, 'deadline_exceeded': elapsed > seconds})
        require(type(code) is int, 'Untrusted child exit status')
        require(elapsed <= seconds, name + ': parent dispatch deadline exceeded')
        require(time.monotonic() <= self.deadline, name + ': shared work deadline exceeded')
        require(allow_failure or code == 0, name + ' failed')
        return code, log

    def run(self):
        require(sys.platform == 'darwin', 'Native early-Cancel requires xcode-27')
        with local_bound(min(30, self.deadline - time.monotonic()), 'source-before'):
            self.snapshot = source_snapshot(os.environ)
            self.source_tree = self.snapshot['source_tree']; save(OUT / 'source-before.json', self.snapshot)
        with local_bound(min(15, self.deadline - time.monotonic()), 'runner-isolation'):
            isolation = runner_isolation(os.environ, min(self.deadline, time.monotonic() + 15))
            save(OUT / 'runner-isolation.json', isolation)
        _, version = self.command('toolchain', ['xcodebuild', '-version'], 30)
        require('Xcode 27.0' in version.splitlines(), 'Wrong stable Xcode')
        _, before_text = self.command('devices-before', ['xcrun', 'simctl', 'list', 'devices', 'available', '-j'], 20, simulator=True)
        before = extract_json(before_text, 'devices'); save(OUT / 'devices-before.json', before)
        _, created = self.command('create-owned-device', [sys.executable, 'Scripts/select_test_devices.py', MODEL], 60, simulator=True)
        try:
            matches = re.findall(r'^([0-9A-Fa-f-]{36}) iPhone SE \(3rd generation\)$', created, re.M)
            require(len(matches) == 1, 'Missing/ambiguous create receipt; no replacement is allowed')
            device = matches[0]
            _, after_text = self.command('devices-after-create', ['xcrun', 'simctl', 'list', 'devices', 'available', '-j'], 20, simulator=True)
            after = extract_json(after_text, 'devices'); save(OUT / 'devices-after-create.json', after)
            owner = full.owner_receipt(before, after, device, os.environ, self.source, self.started, self.deadline)
            self.device = device; save(OUT / 'owned-simulator.json', owner)
        except BaseException:
            self.uncertain = True
            raise
        base = ['xcodebuild', '-project', 'Celluloid.xcodeproj', '-scheme', 'Celluloid', '-configuration', 'Debug',
            '-destination', 'platform=iOS Simulator,id=' + device, '-derivedDataPath', str(DERIVED),
            'CODE_SIGNING_ALLOWED=NO', 'CODE_SIGNING_REQUIRED=NO', 'COMPILER_INDEX_STORE_ENABLE=NO']
        # No unit/package test, Photos permission/grant/seed, install helper or
        # earlier UI launch. Build only; the sole UI method is the first test.
        self.command('build', [*base, '-jobs', '2', 'build-for-testing'], 720, simulator=True)
        self.binary = DERIVED / 'Build/Products/Debug-iphonesimulator/Celluloid.app/Celluloid'
        with local_bound(min(30, self.deadline - time.monotonic()), 'build-binding'):
            self.binding = build_binding(self.binary, self.source, self.source_tree)
            save(OUT / 'build-binding.json', self.binding)
        self.command('boot', ['xcrun', 'simctl', 'boot', device], 60, simulator=True)
        self.command('bootstatus', ['xcrun', 'simctl', 'bootstatus', device, '-b'], 300, simulator=True)
        with local_bound(min(30, self.deadline - time.monotonic()), 'pre-UI-build-check'):
            check_build(self.binding, self.binary, self.source, self.source_tree)
        result = OUT / 'early-cancel.xcresult'
        require(not result.exists() and not result.is_symlink() and not self.ui_dispatched, 'Refusing repeated UI execution')
        self.ui_dispatched = True
        code, log, primary_error = None, '', None
        try:
            code, log = self.command('early-cancel-ui', [*base, '-parallel-testing-enabled', 'NO',
                '-only-testing:' + SELECTOR, '-resultBundlePath', str(result), 'test-without-building'],
                UI_PHASE_SECONDS, simulator=True, allow_failure=True)
        except BaseException as failure:
            primary_error = failure
        finally:
            # A failed assertion, wrapper interruption or timeout still attempts
            # bounded file-only diagnostics. No native rerun or simulator action.
            try:
                if not log and (OUT / 'early-cancel-ui.log').is_file():
                    with local_bound(min(5, self.deadline - time.monotonic()), 'retained-UI-log'):
                        log = (OUT / 'early-cancel-ui.log').read_text(errors='replace')
                self.collect_evidence(result, log)
            except BaseException as failure:
                primary_error = primary_error or failure
        if primary_error is not None: raise primary_error
        require(code == 0 and self.receipt_passed and not self.uncertain, 'Cold early-Cancel did not obtain strict passing evidence')

    def collect_evidence(self, result, log):
        receipt_path = OUT / 'early-cancel-native-receipt.json'
        diagnostics = OUT / 'early-cancel-native-diagnostics'
        retained_binary = OUT / 'Celluloid-executable'; binary_retained = False
        retained_dylib = OUT / DEBUG_DYLIB_NAME; dylib_retained = False
        summary = OUT / 'official-test-summary.json'
        summary_error = OUT / 'official-test-summary-export-error.json'
        try:
            with local_bound(min(30, self.deadline - time.monotonic()), 'native-identity'):
                # Retain the launcher AND main Debug payload with independent
                # hashes inside the same local bound. The rest of the .app,
                # including embedded code/resources, remains CI attestation.
                check_build(self.binding, self.binary, self.source, self.source_tree)
                records = {}; combined_bytes = 0
                for original, retained, key in [(self.binary, retained_binary, 'app_binary_sha256'),
                        (self.binary.parent / DEBUG_DYLIB_NAME, retained_dylib, 'app_debug_dylib_sha256')]:
                    total = 0
                    with original.open('rb') as source, retained.open('xb') as target:
                        for block in iter(lambda: source.read(1024 * 1024), b''):
                            total += len(block); combined_bytes += len(block)
                            require(combined_bytes <= native.MAX_TOTAL_BYTES, 'Retained executable/dylib exceeds existing byte bound')
                            target.write(block)
                    require(native.sha256_file(retained) == self.binding[key], 'Retained executable/dylib hash mismatch')
                    records[key] = {'file': retained.name, 'bytes': total, 'sha256': self.binding[key]}
                check_build(self.binding, self.binary, self.source, self.source_tree)
                binary_retained = dylib_retained = True
                save(OUT / 'retained-app-binary.json', {**records['app_binary_sha256'],
                    'app_debug_dylib': records['app_debug_dylib_sha256'],
                    'source_sha': self.source, 'source_tree': self.source_tree,
                    'app_binary_retention_complete': True, 'app_debug_dylib_retention_complete': True,
                    'app_bundle_retained': False,
                    'app_bundle_sha256_ci_attestation_only': self.binding['app_bundle_sha256'],
                    'receipt_acceptance': 'not implied by retention'})
                require(result.is_dir() and not result.is_symlink(), 'Missing/foreign xcresult')
                run = unique_run(log)
                identity = {'schema_version': 1, 'source_sha': self.source, 'source_tree': self.source_tree,
                    'app_binary_sha256': self.binding['app_binary_sha256'],
                    'app_debug_dylib_sha256': self.binding['app_debug_dylib_sha256'], 'app_bundle_sha256': self.binding['app_bundle_sha256'],
                    'xcresult_sha256': native.bundle_digest(result), 'device_id': self.device,
                    'ci_run_id': os.environ['GITHUB_RUN_ID'], 'ci_run_attempt': os.environ['GITHUB_RUN_ATTEMPT'],
                    'runs': [{'run_id': run, 'expected_cancel_count': 3, 'expected_selected_count': 0}]}
                identity_path = OUT / 'early-cancel-identity.json'; save(identity_path, identity)
            command = [sys.executable, 'Scripts/early_cancel_receipt.py', '--xcresult', str(result),
                '--identity', str(identity_path), '--app-binary', str(self.binary), '--output', str(receipt_path),
                '--diagnostics-output', str(diagnostics), '--expected-source-sha', self.source,
                '--expected-source-tree', self.source_tree, '--expected-run', run, '--expected-device-id', self.device,
                '--expected-ci-run-id', os.environ['GITHUB_RUN_ID'], '--expected-ci-run-attempt', '1',
                '--expected-device-model', MODEL, '--expected-runtime-version', '27.0', '--expected-runtime-build', '24A434',
                '--runner-log-timezone', 'UTC']
            status, _ = self.command('early-cancel-native-receipt', command, 150, allow_failure=True)
            with local_bound(min(30, self.deadline - time.monotonic()), 'native-receipt-check'):
                receipt = json.loads(receipt_path.read_text())
                check_build(self.binding, self.binary, self.source, self.source_tree)
                binary_retained = dylib_retained = False
                binary_retained = native.sha256_file(retained_binary) == self.binding['app_binary_sha256']
                require(binary_retained, 'Retained executable changed during parsing')
                dylib_retained = native.sha256_file(retained_dylib) == self.binding['app_debug_dylib_sha256']
                require(dylib_retained, 'Retained debug dylib changed during parsing')
                self.receipt_passed = status == 0 and receipt.get('status') == 'passed' and receipt.get('identity_verified') is True \
                    and receipt.get('requires_identity_wrapper') is False and receipt.get('release_qualification') is False
        except (ValueError, OSError, native.EvidenceError) as failure:
            self.receipt_passed = False
            if not (binary_retained and dylib_retained):
                save(OUT / 'retained-app-binary-error.json', {'app_binary_retention_complete': binary_retained,
                    'app_debug_dylib_retention_complete': dylib_retained, 'error': str(failure)})
            if not receipt_path.exists(): save(receipt_path, {'status': 'invalid_evidence', 'error': str(failure),
                'app_binary_retention_complete': binary_retained, 'app_debug_dylib_retention_complete': dylib_retained,
                'release_qualification': False})
            self.failures.append({'phase': 'native-evidence-binding', 'error': str(failure)})
        # Missing UUID/failed assertion/parser errors must retain official exports.
        # Never claim unbound logs as acceptance or retry the test itself.
        if not (diagnostics / 'retained-manifest.json').is_file() or not (summary.is_file() or summary_error.is_file()):
            try:
                code, _ = self.command('early-cancel-unbound-diagnostics', [sys.executable, '-c',
                    'import json,sys,time; from pathlib import Path; sys.path.insert(0,"Scripts"); '
                    'import picker_native_receipt as r; import early_cancel_receipt as e\n'
                    'deadline=time.monotonic()+45; errors={}; summary=Path(sys.argv[3]); error=Path(sys.argv[4])\n'
                    'if not (summary.exists() or error.exists()):\n'
                    ' try: e.export_summary(Path(sys.argv[1]),output=summary,deadline=deadline)\n'
                    ' except (ValueError,OSError,UnicodeError) as failure:\n'
                    '  errors["summary"]=str(failure)\n'
                    '  try: error.write_text(json.dumps({"error":str(failure),"receipt_acceptance":False}))\n'
                    '  except OSError as failure: errors["summary_error_retention"]=str(failure)\n'
                    'if not Path(sys.argv[5]).is_file():\n'
                    ' try: print(json.dumps(r.export_diagnostics(Path(sys.argv[1]),Path(sys.argv[2]),run_tool=lambda command,cap:r._run_tool(command,min(cap,deadline)))))\n'
                    ' except (ValueError,OSError,UnicodeError) as failure: errors["diagnostics"]=str(failure)\n'
                    'if errors: print(json.dumps(errors)); raise SystemExit(1)\n',
                    str(result), str(OUT / 'early-cancel-unbound-diagnostics'), str(summary), str(summary_error),
                    str(diagnostics / 'retained-manifest.json')], 60, allow_failure=True)
                if code: raise ValueError('Official unbound diagnostics export failed: ' + str(code))
            except (ValueError, OSError) as failure:
                save(OUT / 'early-cancel-unbound-export-error.json', {'error': str(failure)})

    def verify_after(self):
        if self.snapshot is None: return
        after = source_snapshot(os.environ); save(OUT / 'source-after.json', after)
        require(after == self.snapshot, 'Checkout/source/product bytes changed during native work')
        if self.binding is not None: check_build(self.binding, self.binary, self.source, self.source_tree)

    def cleanup(self):
        if not self.device or self.uncertain: return
        deadline = min(self.deadline + 120, time.monotonic() + 90)
        for action in ['shutdown', 'delete', 'verify-absent']:
            if deadline - time.monotonic() < 25:
                self.failures.append({'phase': 'cleanup-' + action, 'error': 'Cleanup deadline exhausted'})
                return
            command = ['xcrun', 'simctl', action, self.device] if action != 'verify-absent' else ['xcrun', 'simctl', 'list', 'devices', '-j']
            try:
                code, log, elapsed = self.owned_command('cleanup-' + action, command, 20, deadline)
                if code != 0: self.uncertain = True
            except BaseException:
                self.uncertain = True
                raise
            self.cleanup_events.append({'phase': action, 'exit_code': code, 'elapsed_seconds': elapsed, 'uncertain': self.uncertain})
            save(OUT / 'cleanup.json', self.cleanup_events)
            if self.uncertain: return
            if action == 'verify-absent':
                devices = extract_json(log, 'devices')
                require(not any(d.get('udid') == self.device for group in devices['devices'].values() for d in group),
                        'Owned device still exists after deletion')
        self.cleanup_verified = True; self.device = None


def main():
    os.chdir(ROOT); os.environ['TZ'] = 'UTC'
    if hasattr(time, 'tzset'): time.tzset()
    gate = EarlyCancel(); error = None
    def stop(signum, frame): raise KeyboardInterrupt('Early-Cancel acceptance interrupted')
    signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
    try:
        with local_bound(gate.deadline - time.monotonic(), 'shared-work-deadline'): gate.run()
    except BaseException as failure:
        error = str(failure)
        if isinstance(failure, (KeyboardInterrupt, SystemExit)): gate.uncertain = True
    finally:
        final_local_started = time.monotonic()
        try:
            with local_bound(28, 'source-after-and-build-check'): gate.verify_after()
        except BaseException as failure:
            error = error or str(failure)
            if isinstance(failure, (KeyboardInterrupt, SystemExit)): gate.uncertain = True
        final_local_remaining = 30 - (time.monotonic() - final_local_started)
        try:
            with local_bound(min(90, gate.deadline + 118 - time.monotonic()), 'owned-cleanup'): gate.cleanup()
        except BaseException as failure:
            gate.uncertain = True; error = error or str(failure)
        accepted = error is None and gate.receipt_passed and not gate.failures and gate.cleanup_verified and not gate.device and not gate.uncertain
        with local_bound(min(final_local_remaining, gate.deadline + 120 - time.monotonic()), 'final-receipt'):
            save(OUT / 'acceptance.json', {'status': 'early_cancel_observation_passed' if accepted else 'failed',
            'validation_scope': 'early_cancel_supplementary', 'current_slice_accepted': accepted,
            'all_required_phases_accepted': False, 'historical_full_38681904126_status': 'failed',
            'historical_early_cancel_38695192063_status': 'failed',
            'historical_extra_38748681679_status': 'failed',
            'historical_photos_38681898894_status': 'passed', 'release_qualification': False,
            'project_execution_ordinal': 4, 'historical_original_attempts_consumed': 2,
            'historical_additional_attempts_consumed': 1, 'current_retest_attempt': 1, 'current_retest_limit': 1,
            'authorization_basis': 'standing_free_development_test', 'authorized_extra_cost_cny': 0,
            'workflow_run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
            'automatic_retries': 0, 'work_budget_seconds': gate.work_seconds, 'maximum_attempt_seconds': 2700,
            'reserved_nonwork_seconds': 600, 'elapsed_seconds': time.monotonic() - gate.started,
            'source_sha': gate.source, 'source_tree': gate.source_tree, 'error': error, 'failed_phases': gate.failures,
            'pending_owned_device': gate.device, 'simulator_uncertain': gate.uncertain,
            'cleanup_verified': gate.cleanup_verified, 'cleanup_commands': gate.cleanup_events,
            'not_executed_in_this_slice': ['Full rerun', 'Photos rerun', 'unit suite', 'Core and Rendering', 'seeded UUID/pixel selection', 'preservation']})
    return 0 if accepted else 1


if __name__ == '__main__': raise SystemExit(main())
