#!/usr/bin/env python3
"""Bound a simulator setup command; terminate only the command's own process group."""
import argparse
import datetime
import json
import os
import signal
import subprocess
import sys
import time

from original_ios_process_guard import OwnedCommand, error_record

parser = argparse.ArgumentParser()
parser.add_argument('--seconds', required=True, type=float)
parser.add_argument('--label', required=True)
parser.add_argument('command', nargs=argparse.REMAINDER)
args = parser.parse_args()
if not args.command or args.seconds <= 0:
    parser.error('A positive time bound and command are required')
owner = OwnedCommand(args.command[0], args.label, args.seconds)
started = time.monotonic()
deadline = started + args.seconds
print('BOUNDED_COMMAND_BEGIN', json.dumps({'label': args.label, 'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'seconds': args.seconds, 'command': args.command}), flush=True)
try:
    process = subprocess.Popen(args.command, start_new_session=True)
    owner.started(process)
except BaseException as original:
    owner.failed(original)
    raise
try:
    if owner.enabled:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(args.command, args.seconds)
        code = process.wait(timeout=remaining)
        if time.monotonic() > deadline:
            raise subprocess.TimeoutExpired(args.command, args.seconds)
    else:
        code = process.wait(timeout=args.seconds)
except subprocess.TimeoutExpired as original:
    print('BOUNDED_COMMAND_TIMEOUT', args.label, flush=True)
    if owner.enabled:
        # Persist before cleanup. No diagnostics can consume cleanup allowance.
        owner.failed(original, timed_out=True)
        reaped = process.poll()
        if type(reaped) is int:
            owner.cleanup_result('child_reaped', reaped)
        else:
            for sig, seconds in [(signal.SIGTERM, 5), (signal.SIGKILL, 5)]:
                name = signal.Signals(sig).name
                try:
                    os.killpg(process.pid, sig)
                    owner.cleanup_result('unconfirmed', signal_name=name, outcome='sent')
                except ProcessLookupError:
                    owner.cleanup_result('unconfirmed', signal_name=name, outcome='absent')
                except OSError as error:
                    state = 'signal_denied' if isinstance(error, PermissionError) else 'signal_error'
                    owner.cleanup_result(state, signal_name=name, outcome='denied' if state == 'signal_denied' else 'error', error=error)
                    print('BOUNDED_COMMAND_CLEANUP_UNCONFIRMED', json.dumps(error_record(error)), flush=True)
                    break  # Never switch signals or routes after denied cleanup.
                try:
                    process.wait(timeout=seconds)
                except subprocess.TimeoutExpired:
                    owner.cleanup_result('bounded_cleanup_expired')
                except BaseException as error:
                    owner.cleanup_result('wait_failed')
                    print('BOUNDED_COMMAND_CLEANUP_UNCONFIRMED', json.dumps(error_record(error)), flush=True)
                    break
                else:
                    owner.cleanup_result('child_reaped', process.returncode)
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
print('BOUNDED_COMMAND_END', json.dumps({'label': args.label, 'exit_code': code, 'elapsed_seconds': round(time.monotonic() - started, 3)}), flush=True)
sys.exit(code if code >= 0 else 128 - code)
