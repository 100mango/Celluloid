#!/usr/bin/env python3
"""Bound a simulator setup command; terminate only the command's own process group."""
import time
_wrapper_entry_monotonic = time.monotonic()

import argparse
import datetime
import json
import math
import os
import signal
import subprocess
import sys

from original_ios_process_guard import OwnedCommand, error_record

parser = argparse.ArgumentParser()
parser.add_argument('--seconds', required=True, type=float)
parser.add_argument('--label', required=True)
parser.add_argument('--original-ios-first-summary', action='store_true')
parser.add_argument('--deadline-monotonic', type=float, help='Exact reviewed Photos-host parent dispatch deadline')
parser.add_argument('command', nargs=argparse.REMAINDER)
args = parser.parse_args()
if not args.command or args.seconds <= 0:
    parser.error('A positive time bound and command are required')
absolute_deadline = args.deadline_monotonic is not None
if absolute_deadline:
    if (args.original_ios_first_summary or os.environ.get('GITHUB_REF') != 'refs/heads/cell-ios-photos-host-final'
            or os.environ.get('GITHUB_REPOSITORY') != '100mango/Celluloid'
            or not math.isfinite(args.seconds) or not math.isfinite(args.deadline_monotonic) or args.deadline_monotonic <= 0
            or args.deadline_monotonic > time.monotonic() + args.seconds):
        parser.error('Invalid reviewed Photos-host parent deadline')
# Only the exact final Photos install command gets the split phase budget.
# Source/owner/build admission remains in the unchanged parent host controller.
photos_install_split = (os.environ.get('GITHUB_REF') == 'refs/heads/cell-ios-photos-host-final'
                        and args.label == 'install-owned-app')
if photos_install_split:
    import re
    expected_app = os.path.join(os.getcwd(), '.build/swiftui-ios/Build/Products/Debug-iphonesimulator/Celluloid.app')
    if (not absolute_deadline or args.seconds != 210 or len(args.command) != 5
            or args.command[:3] != ['xcrun', 'simctl', 'install']
            or re.fullmatch(r'[0-9A-F]{8}(?:-[0-9A-F]{4}){3}-[0-9A-F]{12}', args.command[3]) is None
            or args.command[4] != expected_app):
        parser.error('Invalid exact Photos install preparation/native split')
def photos_timing(phase, **values):
    # Only the already-admitted Photos absolute-deadline route emits this
    # receipt. Entry was sampled with time alone, before other module imports.
    if not absolute_deadline:
        return
    print('PHOTOS_BOUNDED_TIMING', json.dumps({
        'schema': 'Celluloid.PhotosBoundedTiming.1', 'phase': phase, 'label': args.label,
        'source_sha': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID'),
        'run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT'), 'wrapper_pid': os.getpid(),
        'wrapper_entry_monotonic': _wrapper_entry_monotonic, 'monotonic': time.monotonic(),
        'parent_deadline_monotonic': args.deadline_monotonic,
        **values}), flush=True)


def cleanup_result(status, returncode=None, **values):
    # Retain the original guard's semantics. A reaped direct child never proves
    # that every inherited process-group member or simulator service exited.
    owner.cleanup_result(status, returncode, **values)
    if absolute_deadline:
        details = dict(values)
        if details.get('error') is not None:
            details['error'] = error_record(details['error'])
        photos_timing('cleanup-result', status=status, child_returncode=returncode,
                      cleanup_deadline_monotonic=photos_cleanup_deadline,
                      group_exit_confirmed=False, **details)


photos_timing('wrapper-ready')
started = time.monotonic() if args.original_ios_first_summary else None
first_summary = None
if args.original_ios_first_summary:
    from original_ios_first_summary import admission, record
    first_summary = admission(args.command, args.label, args.seconds, started)
    deadline = first_summary['command_deadline']
owner = OwnedCommand(args.command[0], args.label, args.seconds)
if first_summary is None:
    started = time.monotonic()
    deadline = min(started + args.seconds, args.deadline_monotonic) if absolute_deadline else started + args.seconds
print('BOUNDED_COMMAND_BEGIN', json.dumps({'label': args.label, 'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'seconds': args.seconds, 'command': args.command}), flush=True)
def refuse_expired_parent():
    if absolute_deadline and time.monotonic() >= deadline:
        photos_timing('expired-before-spawn', child_started=False)
        print('BOUNDED_COMMAND_TIMEOUT', args.label, 'parent deadline expired before child dispatch', flush=True)
        photos_timing('wrapper-end', exit_code=124, child_started=False)
        print('BOUNDED_COMMAND_END', json.dumps({'label': args.label, 'exit_code': 124, 'elapsed_seconds': round(time.monotonic() - started, 3), 'child_started': False}), flush=True)
        sys.exit(124)


def refuse_expired_install_preparation():
    if time.monotonic() >= args.deadline_monotonic - 120:
        photos_timing('install-preparation-expired', child_started=False, preparation_limit_seconds=90)
        print('BOUNDED_COMMAND_TIMEOUT', args.label, 'preparation deadline expired; no install dispatch', flush=True)
        photos_timing('wrapper-end', exit_code=124, child_started=False)
        sys.exit(124)


refuse_expired_parent()
photos_timing('spawn-begin')
# Receipt I/O must not authorize a child after the parent deadline.
refuse_expired_parent()
if photos_install_split:
    refuse_expired_install_preparation()
    # Sample before receipt I/O and Popen. Neither can earn a new120s window.
    native_dispatch_started = time.monotonic()
    deadline = min(native_dispatch_started + 120, args.deadline_monotonic)
    photos_timing('install-native-dispatch', native_dispatch_started_monotonic=native_dispatch_started,
                  native_deadline_monotonic=deadline, native_limit_seconds=120,
                  preparation_deadline_monotonic=args.deadline_monotonic - 120,
                  preparation_limit_seconds=90, phase_limit_seconds=210)
    refuse_expired_install_preparation()
    refuse_expired_parent()
try:
    if first_summary is not None and time.monotonic() >= deadline:
        raise subprocess.TimeoutExpired(args.command, args.seconds)
    process = subprocess.Popen(args.command, start_new_session=True)
    owner.started(process)
    photos_timing('spawn-return', child_pid=process.pid, child_pgid=process.pid, start_new_session=True)
except BaseException as original:
    owner.failed(original, timed_out=isinstance(original, subprocess.TimeoutExpired))
    photos_timing('spawn-failed', error=error_record(original))
    raise
wait_budget_seconds = None
try:
    if owner.enabled or absolute_deadline:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(args.command, args.seconds)
        photos_timing('wait-begin', child_pid=process.pid, remaining_seconds=remaining)
        if absolute_deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(args.command, args.seconds)
        wait_budget_seconds = remaining
        code = process.wait(timeout=remaining)
        photos_timing('wait-return', child_pid=process.pid, child_returncode=code, wait_budget_seconds=remaining)
        if time.monotonic() > deadline:
            raise subprocess.TimeoutExpired(args.command, args.seconds)
    else:
        code = process.wait(timeout=args.seconds)
except subprocess.TimeoutExpired as original:
    photos_cleanup_started = time.monotonic() if absolute_deadline else None
    photos_cleanup_deadline = photos_cleanup_started + 10 if absolute_deadline else None
    print('BOUNDED_COMMAND_TIMEOUT', args.label, flush=True)
    photos_timing('timeout-observed', child_pid=process.pid, cleanup_started_monotonic=photos_cleanup_started,
                  cleanup_deadline_monotonic=photos_cleanup_deadline, wait_budget_seconds=wait_budget_seconds)
    if owner.enabled or absolute_deadline:
        # Persist before cleanup. No diagnostics can consume cleanup allowance.
        owner.failed(original, timed_out=True)
        if absolute_deadline and time.monotonic() >= photos_cleanup_deadline:
            cleanup_result('bounded_cleanup_expired')
        else:
            reaped = process.poll()
            photos_timing('poll-after-timeout', child_pid=process.pid, child_returncode=reaped)
            if type(reaped) is int:
                cleanup_result('child_reaped', reaped)
            else:
                for sig, seconds in [(signal.SIGTERM, 5), (signal.SIGKILL, 5)]:
                    if first_summary is not None:
                        seconds = min(seconds, first_summary['cleanup_deadline'] - time.monotonic())
                        if seconds <= 0:
                            cleanup_result('bounded_cleanup_expired')
                            break
                    if absolute_deadline:
                        seconds = min(seconds, photos_cleanup_deadline - time.monotonic())
                        if seconds <= 0:
                            cleanup_result('bounded_cleanup_expired')
                            break
                    name = signal.Signals(sig).name
                    try:
                        photos_timing('cleanup-signal-attempt', child_pid=process.pid, signal_name=name)
                        if absolute_deadline and time.monotonic() >= photos_cleanup_deadline:
                            cleanup_result('bounded_cleanup_expired')
                            break
                        os.killpg(process.pid, sig)
                        cleanup_result('unconfirmed', signal_name=name, outcome='sent')
                    except ProcessLookupError:
                        cleanup_result('unconfirmed', signal_name=name, outcome='absent')
                    except OSError as error:
                        state = 'signal_denied' if isinstance(error, PermissionError) else 'signal_error'
                        cleanup_result(state, signal_name=name, outcome='denied' if state == 'signal_denied' else 'error', error=error)
                        print('BOUNDED_COMMAND_CLEANUP_UNCONFIRMED', json.dumps(error_record(error)), flush=True)
                        break  # Never switch signals or routes after denied cleanup.
                    try:
                        if first_summary is not None:
                            seconds = min(seconds, first_summary['cleanup_deadline'] - time.monotonic())
                            if seconds <= 0:
                                cleanup_result('bounded_cleanup_expired')
                                break
                        photos_timing('cleanup-wait-begin', child_pid=process.pid, maximum_seconds=seconds)
                        if absolute_deadline:
                            seconds = min(seconds, photos_cleanup_deadline - time.monotonic())
                            if seconds <= 0:
                                cleanup_result('bounded_cleanup_expired')
                                break
                        process.wait(timeout=seconds)
                    except subprocess.TimeoutExpired:
                        cleanup_result('bounded_cleanup_expired')
                    except BaseException as error:
                        cleanup_result('wait_failed')
                        print('BOUNDED_COMMAND_CLEANUP_UNCONFIRMED', json.dumps(error_record(error)), flush=True)
                        break
                    else:
                        if ((first_summary is not None and time.monotonic() > first_summary['cleanup_deadline'])
                                or (absolute_deadline and time.monotonic() > photos_cleanup_deadline)):
                            cleanup_result('bounded_cleanup_expired')
                        else:
                            cleanup_result('child_reaped', process.returncode)
                        break
        code = 124
    else:
        # Only safe process identity diagnostics, never full arguments or environment.
        try:
            listing = subprocess.run(['ps', '-axo', 'pid=,ppid=,comm='], capture_output=True, text=True, timeout=5)
            selected = []
            for line in listing.stdout.splitlines():
                parts = line.split(None, 2)
                if len(parts) != 3:
                    continue
                name = os.path.basename(parts[2])
                if any(token in name.lower() for token in ['xcodebuild', 'simulator', 'simctl', 'launchd_sim', 'photolibrary', 'assetsd', 'celluloid']):
                    selected.append({'pid': int(parts[0]), 'ppid': int(parts[1]), 'name': name})
            print('BOUNDED_TIMEOUT_PROCESS_IDENTITIES', json.dumps(selected[:80]), flush=True)
        except (subprocess.TimeoutExpired, ValueError, OSError) as error:
            print('BOUNDED_TIMEOUT_DIAGNOSTICS_UNAVAILABLE', type(error).__name__, flush=True)
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        code = 124
except BaseException as original:
    owner.failed(original)
    raise
else:
    owner.completed(code)
if first_summary is not None:
    record(first_summary, code, time.monotonic())
photos_timing('wrapper-end', exit_code=code)
print('BOUNDED_COMMAND_END', json.dumps({'label': args.label, 'exit_code': code, 'elapsed_seconds': round(time.monotonic() - started, 3)}), flush=True)
sys.exit(code if code >= 0 else 128 - code)
