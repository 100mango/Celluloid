#!/usr/bin/env python3
"""One fixed staged units-summary window; never changes a native test limit."""
import json
import math
import os
from pathlib import Path
import sys
import time

from original_ios_process_guard import require_clear
from uikit_full_shipping_gate import clock_status, WORK_SECONDS
from uikit_full_shipping_handoff import read, write, need

PHASE_FILE = 'original-ios-units-phase.json'
OBSERVATION_FILE = 'original-ios-first-summary.json'
SCHEMA = 'Celluloid.OriginalIOSUnitsPhase.1'
PHASE_SECONDS = 1020
SUMMARY_SECONDS = 90
CLEANUP_SECONDS = 10
OLD_THRESHOLD_SECONDS = 30


def context_root():
    context = require_clear()
    need(context is not None, 'First summary requires the exact staged row')
    root = Path(os.environ['RUNNER_TEMP'])
    need(root.is_dir() and not root.is_symlink(), 'Invalid fixed summary root')
    return context, root


def start():
    # This is the first workflow command inside the unchanged 17-minute units step.
    now, wall = time.monotonic(), time.time()
    context, root = context_root()
    clock = read(root / 'full-shipping-clock.json', 10_000)
    status = clock_status(clock, context, now, wall)
    need(status['work_remaining_seconds'] >= 900 + SUMMARY_SECONDS + CLEANUP_SECONDS,
         'Full original units, first summary and cleanup do not fit work deadline')
    value = {'schema': SCHEMA, **context, 'started_monotonic': now,
             'started_unix': wall, 'phase_seconds': PHASE_SECONDS}
    write(root / PHASE_FILE, value)
    return value


def admission(command, label, seconds, started):
    context, root = context_root()
    expected = ['/bin/bash', '-c', 'xcrun xcresulttool get test-results summary --path "$1" > "$2"',
                '--', 'TestResults-units.xcresult', str(root / 'units.summary.json')]
    need(command == expected and label == 'units summary' and seconds == SUMMARY_SECONDS,
         'Changed fixed first-summary command')
    phase = read(root / PHASE_FILE, 4096)
    need(set(phase) == {'schema', *context, 'started_monotonic', 'started_unix', 'phase_seconds'}
         and phase['schema'] == SCHEMA and type(phase['phase_seconds']) is int
         and phase['phase_seconds'] == PHASE_SECONDS
         and all(type(phase[k]) is str and phase[k] == v for k, v in context.items()),
         'Changed units phase identity or allocation')
    for value in [phase['started_monotonic'], phase['started_unix'], started]:
        need(type(value) in (int, float) and math.isfinite(value) and value > 0,
             'Invalid fixed summary time')
    clock = read(root / 'full-shipping-clock.json', 10_000)
    clock_status(clock, context, started, time.time())
    need(clock['started_monotonic'] <= phase['started_monotonic'] <= started
         and clock['started_unix'] <= phase['started_unix'] <= time.time(),
         'First summary precedes its current phase or row')
    limit = min(phase['started_monotonic'] + PHASE_SECONDS,
                clock['started_monotonic'] + WORK_SECONDS)
    need(started + SUMMARY_SECONDS + CLEANUP_SECONDS <= limit,
         'Full first summary and cleanup do not fit immutable phase/work deadline')
    need(not (root / OBSERVATION_FILE).exists() and not (root / OBSERVATION_FILE).is_symlink(),
         'Duplicate first-summary dispatch')
    return {'context': context, 'root': root, 'phase_started': phase['started_monotonic'],
            'started': started, 'command_deadline': started + SUMMARY_SECONDS,
            'cleanup_deadline': started + SUMMARY_SECONDS + CLEANUP_SECONDS,
            'enclosing_deadline': limit}


def record(bound, code, ended):
    elapsed = ended - bound['started']
    need(math.isfinite(elapsed) and elapsed >= 0, 'Invalid first-summary elapsed time')
    value = {'schema': 'Celluloid.OriginalIOSFirstSummary.1', **bound['context'],
             'command_limit_seconds': SUMMARY_SECONDS, 'cleanup_reserve_seconds': CLEANUP_SECONDS,
             'original_threshold_seconds': OLD_THRESHOLD_SECONDS,
             'original_threshold_exceeded': elapsed > OLD_THRESHOLD_SECONDS,
             'started_monotonic': bound['started'], 'ended_monotonic': ended,
             'elapsed_seconds_including_cleanup': elapsed, 'exit_code': code,
             'phase_elapsed_seconds': ended - bound['phase_started'],
             'command_deadline_monotonic': bound['command_deadline'],
             'cleanup_deadline_monotonic': bound['cleanup_deadline'],
             'enclosing_deadline_monotonic': bound['enclosing_deadline'],
             'within_cleanup_deadline': ended <= bound['cleanup_deadline'],
             'native_test_limit_changed': False, 'acceptance': False}
    write(bound['root'] / OBSERVATION_FILE, value)
    print('ORIGINAL_IOS_FIRST_SUMMARY', json.dumps(value, sort_keys=True), flush=True)
    return value


def verify(root, context, clock):
    """Replay the current command's actual fixed timing, never an old row's SHA."""
    root = Path(root)
    phase = read(root / PHASE_FILE, 4096)
    observed = read(root / OBSERVATION_FILE, 4096)
    need(set(phase) == {'schema', *context, 'started_monotonic', 'started_unix', 'phase_seconds'}
         and phase['schema'] == SCHEMA and type(phase['phase_seconds']) is int
         and phase['phase_seconds'] == PHASE_SECONDS, 'Changed retained units phase')
    numeric = ['started_monotonic', 'ended_monotonic', 'elapsed_seconds_including_cleanup',
               'phase_elapsed_seconds', 'command_deadline_monotonic',
               'cleanup_deadline_monotonic', 'enclosing_deadline_monotonic']
    keys = {'schema', *context, *numeric, 'command_limit_seconds', 'cleanup_reserve_seconds',
            'original_threshold_seconds', 'original_threshold_exceeded', 'exit_code',
            'within_cleanup_deadline', 'native_test_limit_changed', 'acceptance'}
    need(set(observed) == keys and observed['schema'] == 'Celluloid.OriginalIOSFirstSummary.1',
         'Changed retained first-summary structure')
    for item in [phase, observed]:
        need(all(type(item.get(k)) is str and item[k] == v for k, v in context.items()),
             'Wrong retained first-summary identity')
    for value in [phase['started_monotonic'], phase['started_unix'], *[observed[k] for k in numeric]]:
        need(type(value) in (int, float) and math.isfinite(value) and value > 0,
             'Invalid retained first-summary time')
    for key, expected in [('command_limit_seconds', 90), ('cleanup_reserve_seconds', 10),
                          ('original_threshold_seconds', 30), ('exit_code', 0)]:
        need(type(observed[key]) is int and observed[key] == expected, 'Unpassed first-summary limit or result')
    began, ended = observed['started_monotonic'], observed['ended_monotonic']
    need(clock['started_monotonic'] <= phase['started_monotonic'] <= began <= ended
         <= observed['command_deadline_monotonic'] == began + SUMMARY_SECONDS,
         'First summary exceeded its command window')
    need(observed['cleanup_deadline_monotonic'] == began + SUMMARY_SECONDS + CLEANUP_SECONDS
         <= observed['enclosing_deadline_monotonic'] == min(phase['started_monotonic'] + PHASE_SECONDS,
                                                           clock['started_monotonic'] + WORK_SECONDS),
         'First summary consumed reserved cleanup or tail')
    elapsed = ended - began
    need(observed['elapsed_seconds_including_cleanup'] == elapsed
         and observed['phase_elapsed_seconds'] == ended - phase['started_monotonic']
         and type(observed['original_threshold_exceeded']) is bool
         and observed['original_threshold_exceeded'] == (elapsed > OLD_THRESHOLD_SECONDS)
         and observed['within_cleanup_deadline'] is True
         and observed['native_test_limit_changed'] is False and observed['acceptance'] is False,
         'Changed first-summary timing observation')
    return observed


if __name__ == '__main__':
    need(sys.argv[1:] == ['start'], 'Only the fixed units phase start is supported')
    print(json.dumps(start(), sort_keys=True))
