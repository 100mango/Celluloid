#!/usr/bin/env python3
"""Fail closed after uncertain owned work in the four original-iOS rows.

These fixed, bounded files are process evidence, not a scheduler. A reservation
survives helper death; only a normally finalized child clears it. Failure evidence
is first-write-only across commands, and no retained failure authorizes cleanup.
"""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import time
import uuid

from validation_route import ORIGINAL_IOS, current_route

MARKER_NAME = 'original-ios-process-failure.json'
INFLIGHT_NAME = 'original-ios-process-inflight.json'
MAX_MARKER_BYTES = 8192
ROWS = {'compact-phone', 'large-phone', 'small-ipad', 'large-ipad'}
SCHEMA = 'Celluloid.OriginalIOSProcessFailure.1'
INFLIGHT_SCHEMA = 'Celluloid.OriginalIOSProcessInflight.1'
CONTEXT_KEYS = {'source_sha', 'run_id', 'run_attempt', 'row'}


class GuardRefusal(RuntimeError):
    """No further native dispatch is safe; pure file retention is still allowed."""


def need(condition, message):
    if not condition:
        raise GuardRefusal(message)


def validate_context(context):
    need(type(context) is dict and set(context) == CONTEXT_KEYS, 'Malformed process guard context')
    for key, pattern in [('source_sha', '[0-9a-f]{40}'), ('run_id', '[1-9][0-9]*'), ('run_attempt', '[1-9][0-9]*')]:
        need(type(context[key]) is str and re.fullmatch(pattern, context[key]) is not None,
             'Malformed process guard ' + key)
    need(type(context['row']) is str and context['row'] in ROWS, 'Unknown process guard row')
    return dict(context)


def staged_context(environment=None):
    env = os.environ if environment is None else environment
    # No-row producer/archive paths stay inactive. Either staged identity hint
    # on a row requires the complete route; mismatches cannot disable the guard.
    if 'CELLULOID_FULL_ROW' not in env:
        return None
    if (env.get('GITHUB_REF') != 'refs/heads/' + ORIGINAL_IOS['branch']
            and env.get('CELLULOID_VALIDATION_SCOPE') != ORIGINAL_IOS['scope']):
        return None
    try:
        need(current_route(env) == ORIGINAL_IOS, 'Wrong process guard route')
        return validate_context({key: env.get(name) for key, name in [
            ('source_sha', 'GITHUB_SHA'), ('run_id', 'GITHUB_RUN_ID'),
            ('run_attempt', 'GITHUB_RUN_ATTEMPT'), ('row', 'CELLULOID_FULL_ROW')]})
    except ValueError as error:
        raise GuardRefusal(str(error)) from error


def active(environment=None):
    return staged_context(environment) is not None


def _root(root=None, environment=None):
    env = os.environ if environment is None else environment
    value = root if root is not None else env.get('RUNNER_TEMP')
    need(value is not None, 'Missing process evidence root')
    path = Path(value)
    need(path.is_dir() and not path.is_symlink(), 'Invalid process evidence root')
    return path


def _unique(pairs):
    value = {}
    for key, item in pairs:
        need(key not in value, 'Duplicate process receipt key')
        value[key] = item
    return value


def _load(root, name):
    path = _root(root) / name
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise GuardRefusal('Unreadable process receipt: ' + name) from error
    try:
        with os.fdopen(descriptor, 'rb') as stream:
            info = os.fstat(stream.fileno())
            need(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= MAX_MARKER_BYTES,
                 'Invalid process receipt type/size: ' + name)
            raw = stream.read(MAX_MARKER_BYTES + 1)
            need(len(raw) == info.st_size, 'Changed process receipt size: ' + name)
            value = json.loads(raw, object_pairs_hook=_unique,
                               parse_constant=lambda _: need(False, 'Nonfinite process receipt'))
            need(type(value) is dict, 'Malformed process receipt object: ' + name)
            return value
    except (OSError, ValueError, UnicodeError, RecursionError) as error:
        raise GuardRefusal('Malformed process receipt: ' + name) from error


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def _error(value):
    need(type(value) is dict and set(value) == {'type', 'message', 'errno'}, 'Malformed original process error')
    need(type(value['type']) is str and 0 < len(value['type']) <= 80
         and type(value['message']) is str and len(value['message']) <= 512,
         'Unbounded original process error')
    need(value['errno'] is None or type(value['errno']) is int, 'Malformed process error errno')


def error_record(error):
    number = getattr(error, 'errno', None)
    message = str(error)
    return {'type': type(error).__name__[:80], 'message': message if len(message) <= 512 else message[:500] + '[truncated]',
            'errno': number if type(number) is int else None}


def _validate_common(value, context):
    need(type(value) is dict and all(type(value.get(k)) is str and value[k] == v for k, v in validate_context(context).items()),
         'Stale or mismatched process receipt binding')
    need(value.get('validation_route') == ORIGINAL_IOS and type(value.get('validation_route')) is dict
         and type(value['validation_route'].get('diagnostic_only')) is bool, 'Wrong process receipt route')
    need(type(value.get('receipt_id')) is str and re.fullmatch('[0-9a-f]{32}', value['receipt_id']) is not None,
         'Malformed process receipt identity')
    need(type(value.get('command')) is str and 0 < len(value['command']) <= 160
         and type(value.get('label')) is str and 0 < len(value['label']) <= 160, 'Unbounded process identity')
    need(_number(value.get('timeout_seconds')), 'Malformed process timeout')
    need(type(value.get('owner_pid')) is int and value['owner_pid'] > 0, 'Malformed process owner')
    pid, pgid = value.get('child_pid'), value.get('child_pgid')
    need((pid is None and pgid is None) or (type(pid) is int and pid > 0 and type(pgid) is int and pgid == pid),
         'Malformed owned child PID/PGID')
    need(type(value.get('recorded_utc')) is str and len(value['recorded_utc']) <= 64, 'Malformed process receipt time')
    try:
        stamp = datetime.fromisoformat(value['recorded_utc'])
        need(stamp.tzinfo is not None, 'Unzoned process receipt time')
    except ValueError as error:
        raise GuardRefusal('Malformed process receipt time') from error


COMMON_KEYS = {'schema', 'validation_route', *CONTEXT_KEYS, 'receipt_id', 'command', 'label',
               'timeout_seconds', 'owner_pid', 'child_pid', 'child_pgid', 'recorded_utc'}


def read_failure(root, context):
    """Read only: None means absent; malformed/stale evidence always raises."""
    value = _load(root, MARKER_NAME)
    if value is None:
        return None
    _validate_common(value, context)
    need(set(value) == COMMON_KEYS | {'failure_kind', 'original_error', 'cleanup', 'blocked_native_dispatch'}
         and value['schema'] == SCHEMA, 'Malformed first process failure')
    need(value['blocked_native_dispatch'] is True and type(value['failure_kind']) is str and value['failure_kind'] in {'timeout', 'unknown_termination'},
         'Process failure cannot permit dispatch')
    _error(value['original_error'])
    cleanup = value['cleanup']
    need(type(cleanup) is dict and set(cleanup) == {'status', 'signals', 'child_returncode', 'group_exit_confirmed'},
         'Malformed cleanup evidence')
    need(type(cleanup['status']) is str and cleanup['status'] in {'unconfirmed', 'child_reaped', 'signal_denied', 'signal_error', 'wait_failed', 'bounded_cleanup_expired'}
         and cleanup['group_exit_confirmed'] is False, 'Unsupported cleanup claim')
    need(cleanup['child_returncode'] is None or type(cleanup['child_returncode']) is int, 'Malformed child return code')
    signals = cleanup['signals']
    need(type(signals) is list and len(signals) <= 2, 'Unbounded cleanup attempts')
    for index, attempt in enumerate(signals):
        need(type(attempt) is dict and set(attempt) == {'signal', 'outcome', 'error'}
             and attempt['signal'] == ['SIGTERM', 'SIGKILL'][index]
             and type(attempt['outcome']) is str and attempt['outcome'] in {'sent', 'absent', 'denied', 'error'}, 'Malformed cleanup signal')
        if attempt['outcome'] in {'denied', 'error'}:
            _error(attempt['error'])
            need(index == len(signals) - 1, 'Cleanup continued after denied/failed signal')
        else:
            need(attempt['error'] is None, 'Unexpected cleanup signal error')
    return value


def read_inflight(root, context):
    value = _load(root, INFLIGHT_NAME)
    if value is None:
        return None
    _validate_common(value, context)
    need(set(value) == COMMON_KEYS | {'state'} and value['schema'] == INFLIGHT_SCHEMA,
         'Malformed in-flight process receipt')
    need((value['state'] == 'reserved' and value['child_pid'] is None)
         or (value['state'] == 'running' and value['child_pid'] is not None), 'Malformed in-flight child state')
    return value


def require_clear(root=None, context=None, environment=None):
    """Explicit row context also guards file-only archive acceptance replay."""
    context = staged_context(environment) if context is None else validate_context(context)
    if context is None:
        return None
    root = _root(root, environment)
    failure = read_failure(root, context)
    need(failure is None, 'Original iOS process failure retained; no further native dispatch')
    inflight = read_inflight(root, context)
    need(inflight is None, 'Original iOS process finalization is unknown; no further native dispatch')
    return context


ensure_native_dispatch = require_clear


def _write(path, value, *, exclusive=False):
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode()
    need(0 < len(raw) <= MAX_MARKER_BYTES, 'Process evidence exceeds fixed byte cap')
    temporary = None
    try:
        if exclusive:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        else:
            descriptor, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if temporary is not None:
            os.replace(temporary, path)
    except OSError as error:
        raise GuardRefusal('Cannot retain process evidence: ' + path.name) from error
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)


class OwnedCommand:
    """One existing direct child owner. No process creation or signaling here."""
    def __init__(self, command, label, timeout, root=None, environment=None):
        self.context = require_clear(root, environment=environment)
        self.root = _root(root, environment) if self.context is not None else None
        self.failure = None
        if self.context is None:
            return
        need(_number(timeout), 'Invalid owned command timeout')
        self.receipt = {'schema': INFLIGHT_SCHEMA, 'validation_route': dict(ORIGINAL_IOS), **self.context,
                        'receipt_id': uuid.uuid4().hex, 'command': str(command)[:160], 'label': str(label)[:160],
                        'timeout_seconds': timeout, 'owner_pid': os.getpid(), 'child_pid': None, 'child_pgid': None,
                        'recorded_utc': datetime.now(timezone.utc).isoformat(), 'state': 'reserved'}
        _write(self.root / INFLIGHT_NAME, self.receipt, exclusive=True)

    @property
    def enabled(self):
        return self.context is not None

    def started(self, process):
        if not self.enabled:
            return
        need(type(process.pid) is int and process.pid > 0, 'Missing actual created child PID')
        # Both adapters create this direct child with start_new_session=True:
        # successful Popen guarantees setsid() made its actual PID its PGID.
        self.receipt.update(state='running', child_pid=process.pid, child_pgid=process.pid)
        _write(self.root / INFLIGHT_NAME, self.receipt)

    def failed(self, original, *, timed_out=False):
        if not self.enabled:
            return
        existing = read_failure(self.root, self.context)
        if existing is not None:
            return  # Never replace an earlier command's first failure.
        self.failure = {k: v for k, v in self.receipt.items() if k != 'state'}
        self.failure.update(schema=SCHEMA, failure_kind='timeout' if timed_out else 'unknown_termination',
                            original_error=error_record(original), blocked_native_dispatch=True,
                            cleanup={'status': 'unconfirmed', 'signals': [], 'child_returncode': None,
                                     'group_exit_confirmed': False})
        _write(self.root / MARKER_NAME, self.failure, exclusive=True)

    def cleanup_result(self, status, returncode=None, *, signal_name=None, outcome=None, error=None):
        if not self.enabled or self.failure is None:
            return
        current = read_failure(self.root, self.context)
        need(current is not None and current['receipt_id'] == self.receipt['receipt_id'], 'First failure ownership changed')
        self.failure['cleanup'].update(status=status, child_returncode=returncode)
        if signal_name is not None:
            self.failure['cleanup']['signals'].append({'signal': signal_name, 'outcome': outcome,
                                                       'error': error_record(error) if error is not None else None})
        _write(self.root / MARKER_NAME, self.failure)

    def completed(self, returncode):
        if not self.enabled:
            return
        need(type(returncode) is int, 'Unconfirmed child completion')
        if self.failure is not None:
            return  # Timeout stays fatal even if the direct child was reaped.
        if returncode < 0:
            self.failed(RuntimeError('Owned child terminated by signal ' + str(-returncode)))
            self.cleanup_result('child_reaped', returncode)
            return
        current = read_inflight(self.root, self.context)
        need(current is not None and current['receipt_id'] == self.receipt['receipt_id'], 'Process reservation changed')
        if read_failure(self.root, self.context) is not None:
            return  # An owned inner command already reported its timeout.
        (self.root / INFLIGHT_NAME).unlink()


class StagedDiagnosticCommands:
    """Only the two fixed staged diagnostic phases, each within its existing180s."""
    def __init__(self, phase):
        need(phase in {'evidence-screens','diagnostics'},'Unknown staged diagnostic phase')
        self.context=require_clear();need(self.context is not None,'Staged diagnostic context required')
        from uikit_full_shipping_handoff import read
        from uikit_full_shipping_gate import admit_phase
        self.root=_root();self.phase=phase;self.clock=read(self.root/'full-shipping-clock.json')
        self.deadline=time.monotonic()+admit_phase(self.clock,self.context,phase)

    def run(self, command):
        from native_process import run
        require_clear(self.root,self.context)
        need(self.deadline-time.monotonic()>=45+15+15,'Diagnostic command/cleanup/finalization does not fit; no dispatch')
        result=run(command,timeout=45,check=False,echo=False)
        require_clear(self.root,self.context) # A negative signal return remains uncertainty.
        self.finish()
        return result

    def finish(self):
        from uikit_full_shipping_gate import check_completion
        require_clear(self.root,self.context)
        need(time.monotonic()<=self.deadline,'Staged diagnostic exceeded its existing phase deadline')
        check_completion(self.clock,self.context,self.phase)


def ensure_inflight_dispatch(root=None, environment=None):
    """Check a raw inner command inside its existing owned child group."""
    context = staged_context(environment)
    if context is None:
        return None
    root = _root(root, environment)
    need(read_failure(root, context) is None, 'First process failure retained; no inner native dispatch')
    inflight = read_inflight(root, context)
    need(inflight is not None and inflight['state'] == 'running'
         and inflight['child_pgid'] == os.getpgrp(), 'Caller is outside the owned in-flight child group')
    return context


def record_inflight_failure(original, *, timed_out=False, root=None, environment=None):
    """An existing owned script reports an inner failure, without a new owner.

    Raw inner subprocesses inherit the outer child group. Propagation alone
    would turn a timeout into an ordinary Python exit1, so retain it first.
    """
    context = staged_context(environment)
    if context is None:
        return
    root = _root(root, environment)
    inflight = read_inflight(root, context)
    need(inflight is not None and inflight['state'] == 'running'
         and inflight['child_pgid'] == os.getpgrp(), 'Caller is outside the owned in-flight child group')
    owner = OwnedCommand.__new__(OwnedCommand)
    owner.context, owner.root, owner.receipt, owner.failure = context, root, inflight, None
    owner.failed(original, timed_out=timed_out)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['require-clear'])
    parser.parse_args()
    require_clear()
