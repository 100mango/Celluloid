#!/usr/bin/env python3
"""CLOSED, diagnostic-only Vision responder observation. Never release qualification."""
from pathlib import Path
import argparse, hashlib, json, math, os, plistlib, re, subprocess, sys, time, uuid, stat
import final_vision_wave as original

ROOT = Path(__file__).resolve().parents[1]
BASE = 'b9e30f0441b96db23be1e702b93cb97ca6be2831'
BASE_TREE = 'a09eb6f8159069565dc189b8a33e3e848b62437d'
PARENT = 'a25a6676d016c1a8006cd3bc08a878c9dded70f5'
PARENT_TREE = 'a00aae98927d11cdcc0675b47937bb5ecf0ce5fd'
CONFIG = '.github/vision-passive-focus.json'
WORKFLOW = '.github/workflows/vision-passive-focus.yml'
BRANCH = 'celluloid-vision-focus-diagnostic'
MODIFIED = ('Platforms/Shared/EditorInspector.swift', 'Platforms/VisionUITests/NativeVisionUITests.swift')
ADDED = (CONFIG, WORKFLOW, 'Scripts/vision_passive_focus.py', 'Scripts/test_vision_passive_focus.py')
METHODS = ('testVisionPassiveFocus01Target', 'testVisionPassiveFocus02Control')
FLAG = 'CELLULOID_VISION_FOCUS_DIAGNOSTIC'
CLOCK = 'vision-passive-focus-clock.json'
UI_SECONDS = 600
LATEST_UI_START = 780 # Keep 45 s to resolve the current app container before 120 s owned cleanup.
NATIVE_SECONDS = 1560
FINAL_SECONDS = 1740
CAP = 524288
need, read, decode, packed, sha = original.need, original.safe_read, original.strict_json, original.encoded, original.digest


def git(*args):
    return subprocess.run(['git', '-C', str(ROOT), *args], check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=15).stdout


def inverse(raw):
    pattern = rb'(?m)^[ \t]*// VISION_PASSIVE_FOCUS_BEGIN:([a-z-]+)\n.*?^[ \t]*// VISION_PASSIVE_FOCUS_END:\1\n'
    return re.sub(pattern, b'', raw, flags=re.S)


def config(value, enabled=True):
    expected = {'schema': 'Celluloid.VisionPassiveFocusConfig.1', 'READY': enabled,
                'base_sha': BASE, 'base_tree': BASE_TREE, 'maximum_additional_spend_usd': 0,
                'ui_seconds': UI_SECONDS, 'whole_seconds': 1800, 'diagnostic_only': True,
                'qualification_eligible': False, 'automatic_rerun_allowed': False}
    need(type(value) is dict and value == expected and all(type(value[k]) is type(v) for k, v in expected.items()), 'config')
    return value


def source(phase, env, closed=False):
    c = config(decode(read(ROOT / CONFIG, 16384)), not closed)
    gate = 'false' if closed else 'true'
    need(('if: ${{ ' + gate + " && github.event_name == 'push' && github.ref == 'refs/heads/" + BRANCH
          + "' && github.run_attempt == 1 }}") in read(ROOT / WORKFLOW, 16384).decode(), 'workflow-closed-state')
    head = git('rev-parse', 'HEAD').decode().strip()
    need(head == env['GITHUB_SHA'] and env['GITHUB_RUN_ATTEMPT'] == '1', 'source-run-identity')
    need(git('rev-parse', BASE + '^{tree}').decode().strip() == BASE_TREE, 'base-tree')
    need(git('show', '-s', '--format=%P', head).decode().strip() == PARENT, 'actual-sole-parent')
    need(git('rev-parse', PARENT + '^{tree}').decode().strip() == PARENT_TREE, 'actual-parent-tree')
    need(not git('status', '--porcelain', '--untracked-files=all'), 'worktree-not-clean')
    changes = git('diff', '--name-only', BASE, head).decode().splitlines()
    need(set(changes) == set(MODIFIED + ADDED), 'exact-diagnostic-paths')
    def entries(ref):
        out = {}
        for entry in git('ls-tree', '-r', '-z', ref).split(b'\0'):
            if not entry: continue
            fields, name = entry.split(b'\t', 1); mode, kind, obj = fields.decode().split()
            need(kind == 'blob', 'baseline-git-kind'); out[name.decode()] = (mode, obj)
        return out
    baseline_tree, current_tree = entries(BASE), entries(head)
    need(set(current_tree) == set(baseline_tree) | set(ADDED), 'exact-tree-inventory')
    fingerprints = []
    for rel, (mode, obj) in sorted(baseline_tree.items()):
        if rel in MODIFIED:
            baseline = git('cat-file', 'blob', obj)
            need(current_tree[rel][0] == mode and inverse(read(ROOT / rel, 262144)) == baseline, 'baseline-inverse-' + rel)
        else: need(current_tree[rel] == (mode, obj), 'unchanged-baseline-object-' + rel)
        fingerprints.append([rel, mode, obj])
    for rel in ADDED + MODIFIED:
        need(git('ls-tree', head, '--', rel).split(b' ')[0] == b'100644', 'diagnostic-regular-mode')
    row = {'schema': 'Celluloid.VisionPassiveFocusSource.1', 'phase': phase, 'control_sha': head,
           'tree': git('rev-parse', 'HEAD^{tree}').decode().strip(), 'base_sha': BASE, 'base_tree': BASE_TREE,
           'parent_sha': PARENT, 'parent_tree': PARENT_TREE,
           'run_id': env['GITHUB_RUN_ID'], 'run_attempt': '1', 'diagnostic_only': True,
           'qualification_eligible': False, 'shipping_binary_unchanged': False,
           'baseline_paths': len(fingerprints), 'baseline_fingerprint': sha(packed(fingerprints)),
           'changed_paths': {rel: sha(read(ROOT / rel, 1048576)) for rel in MODIFIED + ADDED}, 'config': c}
    temp = Path(env['RUNNER_TEMP']).resolve(strict=True)
    if phase == 'after':
        before = decode(read(temp / 'focus-source-before.json', 65536)); before.pop('phase')
        check = dict(row); check.pop('phase'); need(before == check, 'source-after-mismatch')
    (temp / ('focus-source-' + phase + '.json')).write_bytes(packed(row))
    return row


def clock(value, env, now=None):
    now = time.monotonic() if now is None else now
    need(type(value) is dict and set(value) == {'schema', 'control_sha', 'run_id', 'run_attempt', 'started_monotonic', 'started_unix'}, 'clock-schema')
    for key, expected in [('schema', 'Celluloid.VisionPassiveFocusClock.1'), ('control_sha', env['GITHUB_SHA']),
                          ('run_id', env['GITHUB_RUN_ID']), ('run_attempt', '1')]:
        need(value[key] == expected, 'clock-' + key)
    for key in ('started_monotonic', 'started_unix'):
        need(original.number(value[key]) and value[key] > 0, 'clock-number')
    need(value['started_monotonic'] <= now < value['started_monotonic'] + FINAL_SECONDS, 'clock-expired')
    return value


def admit_ui(start, now):
    need(original.number(start) and original.number(now) and start > 0 and now >= start, 'ui-clock')
    deadline = start + NATIVE_SECONDS - 165
    # Replay actual scheduler operation order; do not reassociate float arithmetic.
    need(now <= start + LATEST_UI_START and now + UI_SECONDS + 15 <= deadline, 'ui-full-window')
    return deadline


def copy_fixtures(producer, container):
    docs = Path(container) / 'Documents'; initial = docs / 'VisionRemaining.celluloid'
    recipe = decode(read(initial / 'recipe.json', 1048576))
    need(recipe.get('overlays') == [], 'fixture-not-zero-overlays')
    result = {}
    for arm, name in [('target', 'VisionFocusTarget.celluloid'), ('control', 'VisionFocusControl.celluloid')]:
        directory = docs / name; directory.mkdir()
        copied = []
        for item in producer['files']:
            raw = read(initial / item['name'], 1048576)
            need(sha(raw) == item['sha256'] and len(raw) == item['bytes'], 'fixture-source-changed')
            with (directory / item['name']).open('xb') as handle: handle.write(raw)
            need(read(directory / item['name'], 1048576) == raw, 'fixture-copy-readback')
            copied.append(dict(item))
        result[arm] = {'package_name': name, 'initial_overlays': 0, 'files': copied}
    return result


def owned_container(raw, udid, home=None):
    """Validate only the queried bundle's current container on our exact simulator."""
    need(type(raw) is str and str(uuid.UUID(udid)).upper() == udid.upper(), 'owned-device')
    path = Path(raw.strip()).resolve(strict=True)
    expected = (Path.home() if home is None else Path(home)) / 'Library/Developer/CoreSimulator/Devices' / udid / 'data/Containers/Data/Application'
    need(path.parent == expected.resolve(strict=True) and str(uuid.UUID(path.name)), 'owned-container-path')
    return path


def empty_command_log(path, receipt):
    """Verify an owned zero-byte stdout file without changing the generic nonempty reader."""
    need(type(receipt.get('log_bytes')) is int and receipt['log_bytes'] == 0
         and type(receipt.get('bytes_read')) is int and receipt['bytes_read'] == 0
         and receipt.get('log_sha256') == sha(b''), 'empty-command-receipt')
    need(all(receipt.get(k) is True for k in ('finalized', 'child_reaped', 'pipe_eof'))
         and all(receipt.get(k) is False for k in ('timed_out', 'overflow'))
         and receipt.get('cleanup_error') is None and type(receipt.get('return_code')) is int
         and receipt['return_code'] == 0, 'empty-command-finalization')
    path = Path(path).absolute(); need(path.name == receipt.get('log'), 'empty-command-path')
    parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY); descriptor = None
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent); parent = child
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        before = os.fstat(descriptor)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size == 0, 'unsafe-empty-command-log')
        def identity(value):
            return value.st_dev, value.st_ino, value.st_mode, value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns
        need(identity(before) == identity(os.fstat(descriptor)) == identity(os.stat(path.name, dir_fd=parent, follow_symlinks=False)), 'changed-empty-command-log')
        return b''
    finally:
        if descriptor is not None: os.close(descriptor)
        os.close(parent)


def validate_timeline(raw, nonce, mode):
    need(type(raw) is bytes and 0 < len(raw) <= CAP and raw.endswith(b'\n'), 'timeline-bound')
    rows = [decode(line) for line in raw.splitlines()]
    need(1 <= len(rows) <= 2048, 'timeline-record-count')
    last_seq = None; last_uptime = None; pids = set()
    events = {'start', 'mapping_pending', 'mapping_resolved', 'mapping_unresolved', 'snapshot', 'text_did_begin', 'text_did_end', 'text_did_change', 'stop'}
    for row in rows:
        need(type(row) is dict and row.get('schema') == 'Celluloid.VisionFocusPassive.1', 'timeline-schema')
        need(row.get('nonce') == nonce and row.get('mode') == mode and row.get('event') in events, 'timeline-identity')
        seq = row.get('seq'); uptime = row.get('system_uptime'); wall = row.get('unix_seconds'); pid = row.get('pid')
        need(type(seq) is int and seq >= 0 and (last_seq is None or seq == last_seq + 1), 'timeline-sequence')
        need(original.number(uptime) and uptime > 0 and (last_uptime is None or uptime >= last_uptime), 'timeline-uptime')
        need(original.number(wall) and wall > 0 and type(pid) is int and pid > 0, 'timeline-clock-pid')
        pids.add(pid); last_seq = seq; last_uptime = uptime
        if 'text_synthetic' in row:
            text = row['text_synthetic']
            need(type(text) is str and (text == 'Hello' or len(text) == 6 and text.count('A') == 1 and text.replace('A', '') == 'Hello'
                 or text == 'redacted' and row.get('text_is_synthetic') is False), 'non-synthetic-text')
    need(len(pids) == 1 and rows[0]['event'] == 'start', 'timeline-lifetime')
    need(type(rows[0].get('initial_source_count')) is int and rows[0]['initial_source_count'] == 1
         and type(rows[0].get('initial_overlay_count')) is int and rows[0]['initial_overlay_count'] == 0, 'fresh-fixture-observer-admission')
    resolved = [r for r in rows if r['event'] == 'mapping_resolved']
    for row in resolved:
        need(row.get('candidate_count') == 1 and type(row.get('candidate_count')) is int, 'mapping-candidate-count')
        need(row.get('mapping_source') in {'exact_native_identifier', 'exact_ancestor_identifier_sole_text_view'}, 'mapping-source')
        need(type(row.get('exact_identifier_node_count')) is int and row['exact_identifier_node_count'] >= 1, 'mapping-identifier-count')
        need(row.get('matched_identifier') == 'editor.bubble-text' and row.get('mapped_node_text_view_count') == 1
             and type(row.get('mapped_node_text_view_count')) is int, 'mapping-identifier-proof')
    generation = None
    for row in rows:
        if row['event'] == 'mapping_resolved':
            generation = row.get('view_lifetime'); need(type(generation) is int and generation > 0, 'mapping-lifetime')
        if 'is_first_responder' in row:
            need(generation is not None and row.get('view_lifetime') == generation, 'snapshot-unmapped-lifetime')
            need(row.get('candidate_count') == 1 and type(row['candidate_count']) is int, 'snapshot-candidate-count')
            need(row.get('mapping_source') in {'exact_native_identifier', 'exact_ancestor_identifier_sole_text_view'}, 'snapshot-mapping')
            for key in ('is_first_responder', 'can_become_first_responder', 'is_editable', 'is_selectable', 'has_window',
                        'window_is_key', 'ancestor_visible', 'ancestor_interactable', 'ancestor_visibility_complete'):
                need(type(row.get(key)) is bool, 'snapshot-boolean-' + key)
            for key in ('window_lifetime', 'scene_lifetime'):
                need(type(row.get(key)) is int and row[key] > 0, 'snapshot-identity-' + key)
    return rows


def ui_markers(log, nonce):
    prefix = 'VISION_PASSIVE_FOCUS_UI_JSON '
    rows = [decode(line[len(prefix):]) for line in log.splitlines() if line.startswith(prefix)]
    need(len(rows) <= 14, 'ui-marker-cap')
    stages = ['before_launch', 'before_tap', 'after_tap', 'before_A', 'after_A', 'observed_after_A', 'before_terminate']
    out = {'target': [], 'control': []}; seen_control = False; last = None; pids = set()
    for row in rows:
        need(type(row) is dict and row.get('schema') == 'Celluloid.VisionFocusUI.1' and row.get('nonce') == nonce, 'ui-marker-identity')
        arm = row.get('mode'); need(arm in out and row.get('stage') in stages, 'ui-marker-arm-stage')
        need(row.get('fixture') == ('VisionFocusTarget' if arm == 'target' else 'VisionFocusControl'), 'ui-marker-fixture')
        need(row.get('native_mapping_gate') == 'posthoc_only', 'no-prekey-IPC')
        need(not (seen_control and arm == 'target'), 'target-must-precede-control'); seen_control |= arm == 'control'
        for key in ('system_uptime', 'unix_seconds'): need(original.number(row.get(key)) and row[key] > 0, 'ui-marker-clock')
        need(last is None or row['system_uptime'] >= last, 'ui-marker-order'); last = row['system_uptime']
        need(type(row.get('runner_pid')) is int and row['runner_pid'] > 0, 'ui-runner-pid'); pids.add(row['runner_pid'])
        old = out[arm]
        need(not old or stages.index(row['stage']) > stages.index(old[-1]['stage']), 'ui-marker-duplicate-or-reversed-stage')
        if row['stage'] != 'before_terminate': need(stages.index(row['stage']) == len(old), 'ui-marker-missing-prerequisite-stage')
        if row['stage'] != 'before_launch': need(old and old[0]['stage'] == 'before_launch', 'ui-marker-missing-launch')
        if row['stage'] in {'before_tap', 'after_tap', 'before_A', 'after_A', 'observed_after_A'}:
            layer = row.get('layer_identifier', ''); need(type(layer) is str and layer.startswith('layer.'), 'ui-layer')
            uuid.UUID(layer[6:])
            previous_layers = {m['layer_identifier'] for m in old if 'layer_identifier' in m}
            need(not previous_layers or previous_layers == {layer}, 'ui-layer-changed')
        old.append(row)
    need(len(pids) <= 1, 'ui-runner-replaced')
    return out


def interpret(rows, markers):
    """Only retain observations. No automatic product/Apple cause or acceptance."""
    resolved = [r for r in rows if r['event'] == 'mapping_resolved']
    unresolved = [r for r in rows if r['event'] == 'mapping_unresolved']
    snapshots = [r for r in rows if type(r.get('is_first_responder')) is bool]
    by_stage = {m['stage']: m for m in markers}
    before = by_stage.get('before_A'); after = by_stage.get('after_A')
    pre = [r for r in snapshots if before and 0 <= before['system_uptime'] - r['system_uptime'] <= 2.5]
    during = [r for r in snapshots if before and after and before['system_uptime'] <= r['system_uptime'] <= after['system_uptime']]
    post = [r for r in snapshots if after and 0 <= r['system_uptime'] - after['system_uptime'] <= 2.5]
    incomplete_stop = any(r['event'] == 'stop' and (after is None or r['system_uptime'] <= after['system_uptime']) for r in rows)
    coverage = ([pre[-1]] + during + [post[0]]) if pre and post else []
    max_gap = max((b['system_uptime'] - a['system_uptime'] for a, b in zip(coverage, coverage[1:])), default=None)
    stable_identity = len({(r.get('view_lifetime'), r.get('window_lifetime'), r.get('scene_lifetime')) for r in coverage}) == 1 if coverage else False
    live_scope = bool(coverage) and all(r.get('has_window') is True and r.get('view_is_hidden') is False
                                     and original.number(r.get('view_alpha')) and r['view_alpha'] > 0
                                     and r.get('view_is_user_interaction_enabled') is True
                                     and r.get('ancestor_visibility_complete') is True
                                     and r.get('ancestor_visible') is True and r.get('ancestor_interactable') is True
                                     and r.get('is_editable') is True for r in coverage)
    usable = bool(resolved and not unresolved and coverage and max_gap is not None and max_gap <= 2.5
                  and stable_identity and live_scope and not incomplete_stop)
    return {'mapping_proven': bool(resolved) and not unresolved, 'mapping_unresolved_records': len(unresolved),
            'direct_snapshot_count': len(snapshots), 'first_responder_true_samples': sum(r['is_first_responder'] for r in snapshots),
            'first_responder_false_samples': sum(not r['is_first_responder'] for r in snapshots),
            'pre_key_snapshot': pre[-1] if pre else None, 'during_key_sample_count': len(during),
            'post_key_snapshot': post[0] if post else None, 'maximum_critical_sample_gap_seconds': max_gap,
            'stable_native_identity_through_key': stable_identity,
            'live_visible_interactable_scope_through_key': live_scope,
            'during_key_first_responder_true_samples': sum(r['is_first_responder'] for r in during),
            'critical_window_capped_or_stopped': incomplete_stop, 'direct_evidence_usable': usable,
            'interpretation': 'review retained samples against real key markers; sub-sample races remain possible' if usable else 'inconclusive',
            'key_markers': markers, 'visual_state': 'unknown', 'product_cause_proven': False, 'qualification_eligible': False}


def run(env):
    os.chdir(ROOT); temp = Path(env['RUNNER_TEMP']).resolve(strict=True)
    config(decode(read(ROOT / CONFIG, 16384)))
    c = clock(decode(read(temp / CLOCK, 16384)), env); start = c['started_monotonic']; native_end = start + NATIVE_SECONDS
    need(env.get('GITHUB_REF') == 'refs/heads/' + BRANCH and env.get('GITHUB_EVENT_NAME') == 'push', 'diagnostic-route')
    commands = original.VisionCommands(temp); prefix = 'focus-' + env['GITHUB_RUN_ID'] + '-1'
    nonce = str(uuid.uuid4()).upper(); udid = None; container = None; ui_result = None; ui_log = ''
    report = {'schema': 'Celluloid.VisionPassiveFocusReport.1', 'control_sha': env['GITHUB_SHA'], 'base_sha': BASE,
              'run_id': env['GITHUB_RUN_ID'], 'run_attempt': '1', 'nonce': nonce, 'clock': c, 'diagnostic_only': True,
              'qualification_eligible': False, 'wave_qualified': False, 'all_eight_qualified': False,
              'archive_qualified': False, 'shipping_binary_unchanged': False, 'commands': commands.events,
              'errors': [], 'arms': {}, 'visual_state': 'unknown', 'screenshot_attempts': 0,
              'visual_reason': 'No existing synchronized pre-key host capture route; no new protocol or screenshot gate.'}
    def call(args, label, seconds, **kwargs):
        return commands.run(args, prefix + '-' + label, deadline=kwargs.pop('deadline', start + LATEST_UI_START), seconds=seconds, **kwargs)
    ui_bundle = temp / (prefix + '-ui.xcresult')
    try:
        version, _ = call(['xcodebuild', '-version'], 'xcode', 30)
        need(version.splitlines() == ['Xcode 27.0', 'Build version 27A266a'], 'exact-toolchain')
        call(['swift', '-swift-version', '5', 'Scripts/materialize_native_icons.swift'], 'icons', 105)
        call([sys.executable, '-B', '-S', 'Scripts/verify_native_icon_inputs.py'], 'icon-proof', 30)
        flags = 'SWIFT_ACTIVE_COMPILATION_CONDITIONS=DEBUG ' + FLAG
        call(['xcodebuild', '-quiet', '-project', 'CelluloidNative.xcodeproj', '-scheme', 'CelluloidVision',
              '-destination', 'generic/platform=visionOS Simulator', '-derivedDataPath', temp / 'vision-wave-build',
              'CODE_SIGNING_ALLOWED=NO', flags, 'build-for-testing'], 'build', 315)
        app = temp / 'vision-wave-build/Build/Products/Debug-xrsimulator/CelluloidVision.app'
        info = plistlib.loads(read(app / 'Info.plist', 1048576)); executable = info.get('CFBundleExecutable')
        need(info.get('CFBundleIdentifier') == 'Mango.Celluloid' and info.get('DTPlatformName') == 'xrsimulator'
             and type(executable) is str and Path(executable).name == executable, 'binary-identity')
        report['diagnostic_binary'] = {'sha256': sha(read(app / executable, 67108864)), 'compiler_condition': flags,
                                        'bundle_identifier': info['CFBundleIdentifier'], 'qualification_eligible': False}
        raw, _ = call(['xcrun', 'simctl', 'list', 'runtimes', '--json'], 'runtimes', 45)
        runtimes = [r for r in decode(raw)['runtimes'] if r.get('isAvailable') and r.get('version') == '27.0'
                    and r.get('buildversion') == '24M362' and 'xrOS' in r.get('identifier', '')]
        need(len(runtimes) == 1, 'exact-vision-runtime'); runtime = runtimes[0]
        raw, _ = call(['xcrun', 'simctl', 'list', 'devicetypes', '--json'], 'device-types', 45)
        supported = {t['identifier'] for t in runtime.get('supportedDeviceTypes', [])}
        types = [t for t in decode(raw)['devicetypes'] if (not supported or t['identifier'] in supported)
                 and t['identifier'] == 'com.apple.CoreSimulator.SimDeviceType.Apple-Vision-Pro-4K']
        need(len(types) == 1, 'unique-compatible-type')
        report['runtime'] = {k: runtime[k] for k in ('name', 'version', 'identifier', 'buildversion')}
        raw, _ = call(['xcrun', 'simctl', 'create', prefix, types[0]['identifier'], runtime['identifier']], 'create', 45)
        udid = raw.strip(); need(str(uuid.UUID(udid)).upper() == udid.upper(), 'owned-device'); report['udid'] = udid
        call(['xcrun', 'simctl', 'boot', udid], 'boot', 195)
        call(['xcrun', 'simctl', 'bootstatus', udid, '-b'], 'bootstatus', 255)
        producer_bundle = temp / (prefix + '-producer.xcresult')
        selection = ['-only-testing:CelluloidVisionTests/NativeVisionTests/' + original.PRODUCER]
        producer_log, _ = call(original.xctest_command(temp, udid, producer_bundle, selection), 'producer-tests', 315)
        raw, _ = call(['xcrun', 'xcresulttool', 'get', 'test-results', 'summary', '--path', producer_bundle], 'producer-summary', 60)
        report['producer_case'] = original.inspect_case(producer_log, original.PRODUCER, decode(raw), 'producer', udid, '27.0')
        raw, _ = call(['xcrun', 'simctl', 'get_app_container', udid, 'Mango.Celluloid', 'data'], 'container', 45)
        container = owned_container(raw, udid)
        producer = original.verify_producer(producer_log, container)
        report['fixture_packages'] = copy_fixtures(producer, container)
        report['owned_container'] = str(container)
        deadline = admit_ui(start, time.monotonic()); report['ui_admitted_monotonic'] = time.monotonic()
        original_env = os.environ.get('TEST_RUNNER_CELLULOID_VISION_FOCUS_NONCE')
        os.environ['TEST_RUNNER_CELLULOID_VISION_FOCUS_NONCE'] = nonce
        try:
            ui_log, ui_result = call(original.xctest_command(temp, udid, ui_bundle,
                ['-only-testing:CelluloidVisionUITests/NativeVisionUITests/' + method for method in METHODS]), 'ui-tests',
                UI_SECONDS + 15, deadline=deadline, full=True, check_code=False)
        finally:
            if original_env is None: os.environ.pop('TEST_RUNNER_CELLULOID_VISION_FOCUS_NONCE', None)
            else: os.environ['TEST_RUNNER_CELLULOID_VISION_FOCUS_NONCE'] = original_env
        report['ui_exit_code'] = ui_result['return_code']
        try: marker_rows = ui_markers(ui_log, nonce)
        except (ValueError, TypeError, KeyError) as error:
            marker_rows = {'target': [], 'control': []}; report['errors'].append('UI markers: ' + str(error))
        report['ui_markers'] = marker_rows
        # XCTest installation may replace the producer's app container. Query the
        # exact owned UDID/bundle once after UI completion, before device cleanup.
        raw, _ = call(['xcrun', 'simctl', 'get_app_container', udid, 'Mango.Celluloid', 'data'],
                      'current-container', 45, deadline=native_end - 120)
        current_container = owned_container(raw, udid)
        report['current_owned_container'] = str(current_container)
        report['container_changed_during_ui'] = current_container != container
        # Only current owned files and this run's UUID nonce; no scan or live IPC.
        for arm in ('target', 'control'):
            try:
                path = current_container / 'Library/Caches/CelluloidVisionFocus' / nonce / (arm + '.ndjson')
                raw = read(path, CAP)
                output = temp / (prefix + '-' + arm + '.ndjson'); output.write_bytes(raw)
                report['arms'][arm] = {'retained_file': output.name, 'bytes': len(raw), 'sha256': sha(raw),
                                      'interpretation': 'inconclusive', 'qualification_eligible': False}
                rows = validate_timeline(raw, nonce, arm)
                report['arms'][arm].update(records=len(rows), observation=interpret(rows, marker_rows[arm]))
            except (OSError, ValueError, TypeError, KeyError) as error:
                report['arms'].setdefault(arm, {}).update(interpretation='inconclusive', error=str(error), qualification_eligible=False)
    except BaseException as error:
        if isinstance(error, (KeyboardInterrupt, SystemExit)): commands.blocked = True
        report['errors'].append(type(error).__name__ + ': ' + str(error))
    finally:
        if udid and not commands.blocked:
            for action in ('shutdown', 'delete'):
                try: call(['xcrun', 'simctl', action, udid], action, 60, deadline=native_end)
                except BaseException as error:
                    report['errors'].append('cleanup ' + action + ': ' + str(error))
                    if commands.blocked: break
        elif udid:
            report['errors'].append('Uncertain process ownership: no further native commands; disposable-runner teardown required.')
        report['process_blocked'] = commands.blocked
        report['elapsed_seconds'] = time.monotonic() - start
        (temp / 'focus-report.json').write_bytes(packed(report))
    if ui_bundle.is_dir() and not commands.blocked:
        try:
            raw, _ = call(['xcrun', 'xcresulttool', 'get', 'test-results', 'summary', '--path', ui_bundle], 'ui-summary', 60, deadline=start + FINAL_SECONDS - 60)
            report['ui_summary'] = decode(raw)
        except BaseException as error: report['errors'].append('summary: ' + str(error))
    report['elapsed_seconds'] = time.monotonic() - start
    report['diagnostic_observations_complete'] = all(
        report['arms'].get(arm, {}).get('observation', {}).get('direct_evidence_usable') is True
        for arm in ('target', 'control'))
    report['diagnostic_status'] = ('observations_retained_for_review' if report['diagnostic_observations_complete']
                                   else 'inconclusive')
    (temp / 'focus-report.json').write_bytes(packed(report))
    return report


def collect(env):
    temp = Path(env['RUNNER_TEMP']).resolve(strict=True)
    c = clock(decode(read(temp / CLOCK, 16384)), env)
    need(time.monotonic() + 60 <= c['started_monotonic'] + FINAL_SECONDS, 'collection-upload-reserve')
    output = temp / 'focus-evidence'; output.mkdir()
    names = [CLOCK, 'focus-source-before.json', 'focus-source-after.json', 'focus-report.json']; command_logs = {}
    report = decode(read(temp / 'focus-report.json', 200000)) if (temp / 'focus-report.json').exists() else None
    if report:
        need(report.get('control_sha') == env['GITHUB_SHA'] and report.get('qualification_eligible') is False, 'report-identity')
        for event in report['commands']:
            if 'log' in event and not event['label'].endswith(('runtimes', 'device-types')):
                need(event['log'] not in command_logs, 'duplicate-command-log')
                command_logs[event['log']] = event; names.append(event['log'])
        names += [value['retained_file'] for value in report['arms'].values() if 'retained_file' in value]
    manifest = {'schema': 'Celluloid.VisionPassiveFocusManifest.1', 'diagnostic_only': True,
                'qualification_eligible': False, 'files': [], 'omissions': []}; total = 0
    for name in names:
        need(type(name) is str and Path(name).name == name, 'retained-path')
        receipt = command_logs.get(name)
        empty = receipt is not None and type(receipt.get('log_bytes')) is int and receipt['log_bytes'] == 0
        try: raw = empty_command_log(temp / name, receipt) if empty else read(temp / name, 1048576)
        except FileNotFoundError:
            manifest['omissions'].append({'name': name, 'reason': 'not-created'}); continue
        need(total + len(raw) <= original.MAX_EVIDENCE - 65536, 'evidence-cap')
        (output / name).write_bytes(raw); total += len(raw)
        entry = {'name': name, 'bytes': len(raw), 'sha256': sha(raw)}
        if empty: entry['kind'] = 'verified-empty-command-output'
        manifest['files'].append(entry)
    (output / 'manifest.json').write_bytes(packed(manifest))
    return manifest


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('phase', choices=['before', 'after', 'run', 'collect'])
    parser.add_argument('--closed', action='store_true'); args = parser.parse_args(); env = os.environ
    if args.phase in ('before', 'after'): result = source(args.phase, env, args.closed)
    elif args.phase == 'collect': result = collect(env)
    else:
        result = run(env); print(json.dumps(result, sort_keys=True))
        return 0 if not result['errors'] and result.get('ui_exit_code') == 0 and result['diagnostic_observations_complete'] else 1
    print(json.dumps(result, sort_keys=True)); return 0

if __name__ == '__main__': raise SystemExit(main())
