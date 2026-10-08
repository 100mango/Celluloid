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

parser = argparse.ArgumentParser()
parser.add_argument('--seconds', required=True, type=float)
parser.add_argument('--label', required=True)
parser.add_argument('command', nargs=argparse.REMAINDER)
args = parser.parse_args()
if not args.command or args.seconds <= 0:
    parser.error('A positive time bound and command are required')
started = time.monotonic()
print('BOUNDED_COMMAND_BEGIN', json.dumps({'label': args.label, 'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'seconds': args.seconds, 'command': args.command}), flush=True)
process = subprocess.Popen(args.command, start_new_session=True)
try:
    code = process.wait(timeout=args.seconds)
except subprocess.TimeoutExpired:
    print('BOUNDED_COMMAND_TIMEOUT', args.label, flush=True)
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
print('BOUNDED_COMMAND_END', json.dumps({'label': args.label, 'exit_code': code, 'elapsed_seconds': round(time.monotonic() - started, 3)}), flush=True)
sys.exit(code if code >= 0 else 128 - code)
