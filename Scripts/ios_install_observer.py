"""Bounded evidence for one admitted, owned simulator install.

Importing this module does nothing. The admitted driver owns the device identity;
run_bounded owns the install Popen. Neither identity is recovered from disk.
"""
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import tempfile
import threading
import time

CAP = 1024 * 1024
LOG_SECONDS = 120
LOG_TOTAL_SECONDS = 150
LOG_CLEANUP_SECONDS = 10
SAMPLE_AFTER_SECONDS = 45
SAMPLE_SECONDS = 3
SAMPLE_CAPTURE_SECONDS = 8
SAMPLE_CLEANUP_SECONDS = 2
SAMPLE_MARGIN_SECONDS = 1
PREDICATE = '(process == "installd" OR process == "installcoordinationd")'


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _pid(process):
    value = getattr(process, 'pid', None)
    return value if type(value) is int and 0 < value < 2 ** 31 else None


def _error(error):
    return type(error).__name__  # No exception text, environment or host paths.


def _uncertain(receipt, reason):
    if reason not in receipt['uncertainty']:
        receipt['uncertainty'].append(reason)
    receipt['uncertain'] = True
    receipt['native_continuation_allowed'] = False


def _receipt(kind, context):
    identity = {}
    for key in ('source_sha', 'run_id', 'run_attempt'):
        value = context.get(key)
        if type(value) is str and len(value) <= 80:
            identity[key] = value
    return {'schema': 'Celluloid.InstallObserver.1', 'kind': kind, **identity,
            'outcome': 'not_started', 'uncertain': False, 'uncertainty': [],
            'native_continuation_allowed': True, 'natural_exit': False,
            'forced_cleanup': False, 'group_exit_confirmed': False,
            'stdout_retained_bytes': 0, 'stderr_retained_bytes': 0,
            'observed_bytes': 0, 'retained_cap_bytes': CAP,
            'stream_ready': False, 'stream_readiness': 'unconfirmed'}


def _persist(out, stem, receipt, stdout=b'', stderr=b''):
    """Only bounded prefixes reach disk; retention failure is evidence, not exit."""
    try:
        folder = Path(out)
        folder.mkdir(parents=True, exist_ok=True)
        stdout = bytes(stdout[:CAP])
        stderr = bytes(stderr[:CAP - len(stdout)])
        (folder / (stem + '.stdout.log')).write_bytes(stdout)
        (folder / (stem + '.stderr.log')).write_bytes(stderr)
        receipt['stdout_retained_bytes'] = len(stdout)
        receipt['stderr_retained_bytes'] = len(stderr)
        raw = json.dumps(receipt, sort_keys=True, allow_nan=False).encode() + b'\n'
        if len(raw) > 16384:
            raise ValueError('Receipt too large')
        with tempfile.NamedTemporaryFile(dir=folder, prefix=stem + '.', suffix='.tmp', delete=False) as file:
            temporary = file.name
            file.write(raw)
        os.replace(temporary, folder / (stem + '.json'))
    except (OSError, ValueError, TypeError) as error:
        receipt['retention_error'] = _error(error)
    return receipt


def _cleanup(process, deadline, receipt):
    """At most two signals, one shared allowance; denial forbids escalation.

    A reaped host child says nothing about simulator-side termination or group
    extinction. Callers must keep uncertainty after every forced cleanup.
    """
    receipt['forced_cleanup'] = True
    _uncertain(receipt, 'forced_host_cleanup_not_simulator_exit_proof')
    receipt['cleanup_deadline_monotonic'] = deadline
    if _pid(process) is None:
        receipt['cleanup_outcome'] = 'missing_typed_pid'
        return
    for signum in (signal.SIGTERM, signal.SIGKILL):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            receipt['cleanup_outcome'] = 'deadline_expired'
            return
        try:
            code = process.poll()
        except BaseException as error:
            receipt['cleanup_outcome'] = 'poll_failed'
            receipt['cleanup_error'] = _error(error)
            return
        if type(code) is int:
            receipt['host_child_reaped'] = True
            receipt['returncode'] = code
            receipt['cleanup_outcome'] = 'host_child_reaped'
            return
        # Recheck after poll, which can itself return late in an injected fault.
        if time.monotonic() >= deadline:
            receipt['cleanup_outcome'] = 'deadline_expired'
            return
        try:
            os.killpg(process.pid, signum)
            receipt.setdefault('signals', []).append(signal.Signals(signum).name)
        except ProcessLookupError:
            receipt.setdefault('signals', []).append(signal.Signals(signum).name + ':absent')
        except OSError as error:
            receipt['cleanup_outcome'] = 'signal_denied' if isinstance(error, PermissionError) else 'signal_error'
            receipt['cleanup_error'] = _error(error)
            return  # Never change signal or route after a denial/error.
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            receipt['cleanup_outcome'] = 'deadline_expired'
            return
        # TERM receives half the total remaining allowance; KILL gets the rest.
        timeout = remaining / 2 if signum == signal.SIGTERM else remaining
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            continue
        except BaseException as error:
            receipt['cleanup_outcome'] = 'wait_failed'
            receipt['cleanup_error'] = _error(error)
            return
        receipt['returncode'] = code
        receipt['host_child_reaped'] = type(code) is int
        receipt['cleanup_outcome'] = ('host_child_reaped' if time.monotonic() <= deadline
                                      else 'late_host_reap')
        return
    receipt['cleanup_outcome'] = 'deadline_expired'


def _collect(process, deadline, cleanup_deadline, receipt, on_stop=None):
    """One owner drains both nonblocking pipes and reaps its own direct child."""
    stdout, stderr = bytearray(), bytearray()
    selector = None
    try:
        selector = selectors.DefaultSelector()
        if time.monotonic() >= deadline:
            receipt['outcome'] = 'late_spawn'
            raise TimeoutError
        if _pid(process) is None:
            receipt['outcome'] = 'missing_typed_pid'
            raise ValueError
        for pipe in (process.stdout, process.stderr):
            os.set_blocking(pipe.fileno(), False)
            selector.register(pipe, selectors.EVENT_READ)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                receipt['outcome'] = 'capture_deadline'
                raise TimeoutError
            code = process.poll()
            if type(code) is int and not selector.get_map():
                if time.monotonic() > deadline:
                    receipt['outcome'] = 'late_exit'
                    raise TimeoutError
                receipt['natural_exit'] = code >= 0
                receipt['returncode'] = code
                receipt['outcome'] = ('abnormal_exit' if code < 0 else
                                      'completed' if code == 0 else 'command_failed')
                # A signalled host child cannot prove either collector settled.
                # A spawned logger additionally needs a successful finite stream
                # exit; a normal nonzero simctl exit is insufficient proof.
                receipt['simulator_stream_settled'] = receipt['kind'] == 'device_log' and code == 0
                if code < 0:
                    _uncertain(receipt, 'abnormal_collector_exit')
                elif receipt['kind'] == 'device_log' and code != 0:
                    _uncertain(receipt, 'logger_exit_without_stream_settlement')
                if receipt['uncertain'] and on_stop is not None:
                    on_stop(receipt)
                return receipt, stdout, stderr
            for key, _ in selector.select(min(remaining, .05)):
                if time.monotonic() >= deadline:
                    receipt['outcome'] = 'capture_deadline'
                    raise TimeoutError
                data = os.read(key.fileobj.fileno(), 4096)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                receipt['observed_bytes'] += len(data)
                target = stdout if key.fileobj is process.stdout else stderr
                target.extend(data[:max(0, CAP - len(stdout) - len(stderr))])
                if receipt['observed_bytes'] > CAP:
                    receipt['outcome'] = 'byte_limit'
                    raise OverflowError
    except BaseException as error:
        if receipt['outcome'] in ('running', 'not_started'):
            receipt['outcome'] = 'capture_failed'
        receipt['capture_error'] = _error(error)
        grace = LOG_CLEANUP_SECONDS if receipt['kind'] == 'device_log' else SAMPLE_CLEANUP_SECONDS
        _uncertain(receipt, 'forced_host_cleanup_not_simulator_exit_proof')
        receipt['forced_cleanup'] = True
        if on_stop is not None:
            on_stop(receipt)  # Publish uncertainty before the bounded cleanup wait.
        try:
            _cleanup(process, min(cleanup_deadline, time.monotonic() + grace), receipt)
        except BaseException as cleanup_error:
            receipt['cleanup_outcome'] = 'cleanup_failed'
            receipt['cleanup_error'] = _error(cleanup_error)
        return receipt, stdout, stderr
    finally:
        if selector is not None:
            try:
                selector.close()
            except BaseException as error:
                _uncertain(receipt, 'selector_close_failed')
                receipt['capture_error'] = _error(error)
        for pipe in (getattr(process, 'stdout', None), getattr(process, 'stderr', None)):
            if pipe is not None:
                try:
                    pipe.close()
                except BaseException as error:
                    _uncertain(receipt, 'pipe_close_failed')
                    receipt['capture_error'] = _error(error)


class ObserverDispatchRefused(RuntimeError):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class DeviceLog:
    """Pre-arm exactly one device-scoped finite stream, with a live pipe owner."""
    def __init__(self, out, device, source, run_id, run_attempt, work_deadline):
        if (type(device) is not str or re.fullmatch(r'[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}', device) is None
                or not _finite(work_deadline)):
            raise ValueError('An exact owned device and finite deadline are required')
        self.out = out
        self.device = device
        self.work_deadline = work_deadline
        self.process = None
        self._thread = None
        self._done = threading.Event()
        self._lock = threading.Lock()
        self._dispatch_lock = threading.Lock()
        self._uncertainty = threading.Event()
        self._pending_stop = threading.Event()
        self._started = False
        self._receipt = _receipt('device_log', {'source_sha': source, 'run_id': run_id, 'run_attempt': run_attempt})
        self._receipt['device'] = device

    @property
    def uncertain(self):
        return self._uncertainty.is_set() or self._pending_stop.is_set()

    def _mark_stop(self):
        # Publish under the shared transition lock when it is free. An already
        # admitted Popen may be stalled while holding that lock; a separate
        # sticky pending stop lets cleanup proceed without waiting for it.
        if self._dispatch_lock.acquire(blocking=False):
            try:
                self._uncertainty.set()
            finally:
                self._dispatch_lock.release()
        else:
            self._pending_stop.set()

    def _snapshot(self):
        with self._lock:
            receipt = dict(self._receipt, uncertainty=list(self._receipt['uncertainty']))
            if self.uncertain and not receipt['uncertain']:
                _uncertain(receipt, 'uncertainty_publication_pending')
            return receipt

    def spawn_if_certain(self, callback, deadline, cancelled=None):
        """Linearize one Popen initiation; never hold the receipt lock for it.

        Uncertainty is sticky and publication never waits for this dispatch lock,
        so a stalled Popen cannot delay the logger's own bounded cleanup.
        """
        if not _finite(deadline):
            raise ObserverDispatchRefused('invalid_deadline')
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not self._dispatch_lock.acquire(timeout=remaining):
            raise ObserverDispatchRefused('deadline_expired')
        try:
            if not self._started:
                raise ObserverDispatchRefused('observer_not_started')
            if cancelled is not None:
                if not callable(cancelled):
                    raise ObserverDispatchRefused('invalid_cancellation_hook')
                if cancelled():
                    raise ObserverDispatchRefused('cancelled')
            if time.monotonic() >= deadline:
                raise ObserverDispatchRefused('deadline_expired')
            if self.uncertain:
                raise ObserverDispatchRefused('observer_uncertain')
            # This final check is dispatch's linearization point. Later logger
            # uncertainty cannot undo this Popen, but forbids the next one.
            return callback()
        finally:
            self._dispatch_lock.release()

    def start(self):
        if self._started:
            raise RuntimeError('Device log may be dispatched only once')
        self._started = True
        dispatch = time.monotonic()
        self._end = min(dispatch + LOG_TOTAL_SECONDS, self.work_deadline)
        self._deadline = self._end - LOG_CLEANUP_SECONDS
        self._receipt.update(dispatch_monotonic=dispatch, capture_deadline_monotonic=self._deadline,
                             overall_deadline_monotonic=self._end)
        stream_seconds = math.floor(min(LOG_SECONDS, self._deadline - time.monotonic() - 5))
        self._receipt['stream_timeout_seconds'] = max(0, stream_seconds)
        if stream_seconds < 1:
            self._receipt['outcome'] = 'skipped_insufficient_budget'
            self._done.set()
            return _persist(self.out, 'install-device-log', self._snapshot())
        command = ['xcrun', 'simctl', 'spawn', self.device, 'log', 'stream', '--style', 'compact',
                   '--level', 'debug', '--timeout', str(stream_seconds), '--predicate', PREDICATE]
        try:
            self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            start_new_session=True)
        except BaseException as error:
            self._receipt.update(outcome='spawn_failed', spawn_error=_error(error))
            if not isinstance(error, OSError):
                self._mark_stop()
                _uncertain(self._receipt, 'logger_spawn_ownership_unconfirmed')
            self._done.set()
            return _persist(self.out, 'install-device-log', self._snapshot())
        self._receipt.update(outcome='running', host_pid=_pid(self.process))
        if time.monotonic() >= self._deadline:
            self._receipt['outcome'] = 'late_spawn'
            self._mark_stop()
            _uncertain(self._receipt, 'logger_spawn_returned_after_capture_deadline')
        if _pid(self.process) is None:
            self._mark_stop()
            _uncertain(self._receipt, 'logger_missing_typed_pid')
        # Popen returning is dispatch evidence only, never readiness evidence.
        # Start the drainer before any receipt I/O can stall a pipe producer.
        try:
            self._thread = threading.Thread(target=self._run, name='owned-install-device-log', daemon=True)
            self._thread.start()
        except BaseException as error:
            self._receipt.update(outcome='owner_start_failed', capture_error=_error(error))
            self._mark_stop()
            _uncertain(self._receipt, 'owner_start_failed')
            _cleanup(self.process, min(self._end, time.monotonic() + LOG_CLEANUP_SECONDS), self._receipt)
            _persist(self.out, 'install-device-log', self._receipt)
            self._done.set()
        return self._snapshot()

    def _publish(self, receipt):
        # Shared-lock publication, or sticky pending stop, never waits for Popen.
        if receipt['uncertain']:
            self._mark_stop()
        # Only in-memory copies under the lock; disk I/O must not trap finish().
        with self._lock:
            for reason in self._receipt['uncertainty']:
                _uncertain(receipt, reason)
            self._receipt = dict(receipt, uncertainty=list(receipt['uncertainty']))

    def _run(self):
        receipt = self._snapshot()
        stdout = stderr = b''
        try:
            receipt, stdout, stderr = _collect(self.process, self._deadline, self._end, receipt,
                                               on_stop=self._publish)
        except BaseException as error:
            receipt.update(outcome='owner_failed', capture_error=_error(error))
            _uncertain(receipt, 'owner_failed_before_finalization')
            self._publish(receipt)
            if not receipt['forced_cleanup']:
                try:
                    _cleanup(self.process, min(self._end, time.monotonic() + LOG_CLEANUP_SECONDS), receipt)
                except BaseException as cleanup_error:
                    receipt.update(cleanup_outcome='cleanup_failed', cleanup_error=_error(cleanup_error))
        finally:
            self._publish(receipt)
            try:
                _persist(self.out, 'install-device-log', receipt, stdout, stderr)
            except BaseException as error:
                receipt['retention_error'] = _error(error)
            finally:
                self._publish(receipt)
                self._done.set()

    def finish(self):
        if not self._started:
            raise RuntimeError('Device log was not started')
        # No new Popen, simctl, inventory, or simulator cleanup in this method.
        if not self._done.wait(timeout=max(0, self._end - time.monotonic())):
            self._mark_stop()
            with self._lock:
                _uncertain(self._receipt, 'owner_not_settled_by_overall_deadline')
                self._receipt['outcome'] = 'owner_unsettled'
        return self._snapshot()


def wait_with_one_sample(process, deadline, command, out, context):
    """Wait for this exact install owner; never sample a PID read from evidence.

    Diagnostic failures cannot replace an install result. The caller receives
    the evidence receipt through context['sample_receipt'] as well as disk.
    A successful return observed after the original deadline is still timeout.
    """
    if not _finite(deadline) or type(context) is not dict:
        raise ValueError('A finite install deadline and context are required')
    receipt = _receipt('install_sample', context)
    receipt.update(outcome='skipped', skip_reason='not_reached', sample_attempts=0,
                   install_deadline_monotonic=deadline, owned_install_pid=_pid(process))
    stdout = stderr = b''
    started = time.monotonic()
    receipt['wait_entry_monotonic'] = started

    def check_deadline():
        if time.monotonic() >= deadline:
            raise subprocess.TimeoutExpired(command, max(0, deadline - started))

    def wait_install():
        check_deadline()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            check_deadline()
        code = process.wait(timeout=remaining)
        receipt['install_return_monotonic'] = time.monotonic()
        receipt['install_returncode'] = code
        if receipt['install_return_monotonic'] > deadline:
            raise subprocess.TimeoutExpired(command, max(0, deadline - started))
        return code

    try:
        if started >= deadline:
            receipt['skip_reason'] = 'install_deadline_expired'
            check_deadline()
        if _pid(process) is None:
            receipt['skip_reason'] = 'missing_typed_pid'
            return wait_install()
        try:
            code = process.wait(timeout=min(SAMPLE_AFTER_SECONDS, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            if time.monotonic() >= deadline:
                receipt['skip_reason'] = 'install_deadline_expired'
                raise
        else:
            receipt['install_return_monotonic'] = time.monotonic()
            receipt['skip_reason'] = 'install_exited_before_sample'
            receipt['install_returncode'] = code
            if receipt['install_return_monotonic'] > deadline:
                receipt['skip_reason'] = 'late_install_exit'
                raise subprocess.TimeoutExpired(command, max(0, deadline - started))
            return code
        # Only this thread ever reaps the install. Keep it unreaped throughout
        # sample collection, preventing PID reuse after a concurrent waiter.
        check_deadline()
        code = process.poll()
        observed = time.monotonic()
        if type(code) is int:
            receipt['install_return_monotonic'] = observed
            receipt['install_returncode'] = code
            receipt['skip_reason'] = 'install_exited_before_sample'
            if observed > deadline:
                receipt['skip_reason'] = 'late_install_exit'
                raise subprocess.TimeoutExpired(command, max(0, deadline - started))
            return code
        if observed >= deadline:
            receipt['skip_reason'] = 'install_deadline_expired'
            check_deadline()
        now = time.monotonic()
        reserve = SAMPLE_CAPTURE_SECONDS + SAMPLE_CLEANUP_SECONDS + SAMPLE_MARGIN_SECONDS
        if now - started < SAMPLE_AFTER_SECONDS:
            receipt['skip_reason'] = 'early_wait_timeout'
            return wait_install()
        if deadline - now <= reserve:
            receipt['skip_reason'] = 'insufficient_budget'
            return wait_install()
        capture_deadline = now + SAMPLE_CAPTURE_SECONDS
        cleanup_deadline = capture_deadline + SAMPLE_CLEANUP_SECONDS
        receipt.update(outcome='running', skip_reason=None,
                       dispatch_monotonic=now, capture_deadline_monotonic=capture_deadline,
                       overall_deadline_monotonic=cleanup_deadline)
        sampler = None
        def spawn_sampler():
            receipt['sample_attempts'] = 1
            # /dev/stdout routes the report to the capped pipe, not a disk file.
            return subprocess.Popen(['/usr/bin/sample', str(receipt['owned_install_pid']), str(SAMPLE_SECONDS),
                                    '-file', '/dev/stdout'], stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, start_new_session=True)
        try:
            device_log = context.get('device_log')
            cancelled = context.get('cancelled')
            if device_log is not None:
                sampler = device_log.spawn_if_certain(spawn_sampler, capture_deadline, cancelled)
            else:
                if cancelled is not None and cancelled():
                    raise ObserverDispatchRefused('cancelled')
                if time.monotonic() >= capture_deadline:
                    raise ObserverDispatchRefused('deadline_expired')
                sampler = spawn_sampler()
        except ObserverDispatchRefused as error:
            receipt.update(outcome='skipped_' + ('uncertain' if error.reason == 'observer_uncertain'
                                                else 'cancelled' if error.reason == 'cancelled' else 'dispatch_refused'),
                           skip_reason=error.reason)
            if error.reason == 'observer_uncertain':
                _uncertain(receipt, 'device_log_uncertain_before_sample')
        except BaseException as error:
            receipt.update(outcome='spawn_failed', spawn_error=_error(error))
            if not isinstance(error, OSError):
                _uncertain(receipt, 'sampler_spawn_ownership_unconfirmed')
        if sampler is not None:
            receipt['host_pid'] = _pid(sampler)
            # Late spawn cannot earn new budget or move cleanup past the
            # original install deadline. _collect will only close local pipes
            # after an expired cleanup deadline; it dispatches no new command.
            try:
                receipt, stdout, stderr = _collect(sampler, capture_deadline, cleanup_deadline, receipt)
            except BaseException as error:
                # Even collector initialization/teardown failure cannot leave
                # the original install without its bounded waiter.
                receipt.update(outcome='capture_failed', capture_error=_error(error))
                try:
                    _cleanup(sampler, min(cleanup_deadline, time.monotonic() + SAMPLE_CLEANUP_SECONDS), receipt)
                except BaseException as cleanup_error:
                    _uncertain(receipt, 'sampler_cleanup_failed')
                    receipt.update(cleanup_outcome='cleanup_failed', cleanup_error=_error(cleanup_error))
        return wait_install()
    finally:
        receipt['ended_monotonic'] = time.monotonic()
        try:
            _persist(out, 'install-sample', receipt, stdout, stderr)
        except BaseException as error:
            receipt['retention_error'] = _error(error)
        context['sample_receipt'] = receipt
