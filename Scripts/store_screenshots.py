#!/usr/bin/env python3
"""Fixed two-device PNG capture; no release qualification or Store submission."""
from pathlib import Path
import argparse
import contextlib
import hashlib
import json
import math
import os
import plistlib
import re
import runpy
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import uuid
import zlib

from mac_host_transport import load_json

ROOT = Path(__file__).resolve().parents[1]
BASE_TREE = '517543d6ceefcbce905a0e0d5db06607a270ca0f'
PUBLIC_BASE = '0da1ea8954b45365c4d0379c569d85809c135648'
PRODUCT_SOURCE = 'da9d4abd6484ddaff469677d96caf24362645d7c'
PRODUCT_TREE = '304ee9c0e4197e4a282ae3933c9f510219b2106d'
CONTRACT_SHA = 'cc2c2db6140e4062ac4259092573d2085318d63baf0ce95b92d04e5582f2c481'
UI_PATH = 'CelluloidUITests/CelluloidUITests.swift'
UI_BASE_SHA = '94f9fffbbf2693038fe85867bd31426959bf099af7f05b681182ef6e97361256'
UI_PRIOR_CAPTURE_SHA = '7462b8288c2768fe3ebe76f44c2d5f425b71627d56b6596b66c5f1b3dc7f8f41'
UI_CAPTURE_SHA = '409fe9b478a56a57682d0af4c7f17d64e1eb7c8eb35e40057fea5254fb1e9ff5'
DISPLAY_BLOCK_SHA = '1c32507d42c9e75f97135fe11ef713d8548c6aa6ae30e82b65e38b796ad15796'
INSERTION = '''        if ProcessInfo.processInfo.environment["CELLULOID_STORE_CAPTURE"] == "1" {
            guard ["edited-fixture", "collage-preview"].contains(name),
                  UIScreen.main.traitCollection.userInterfaceStyle == .dark else { return }
            let png = app.screenshot().pngRepresentation
            let attachment = XCTAttachment(data: png, uniformTypeIdentifier: "public.png")
            attachment.name = "celluloid-store-" + name
            attachment.lifetime = .keepAlways
            add(attachment)
            return
        }
'''.encode()
TARGETS = (
    {'row': 'large-phone', 'model': 'iPhone 17 Pro', 'pixels': [1206, 2622],
     'store_category': 'iPhone with Dynamic Island (medium display)'},
    {'row': 'large-ipad', 'model': 'iPad Pro 13-inch (M5)', 'pixels': [2064, 2752],
     'store_category': 'iPad 13-inch display'},
)
CASES = {'edited-fixture': 'testStoreNormalEditorScreenshot',
         'collage-preview': 'testStoreNormalCollageScreenshot'}
SETUP_CASES = ('testPhotosLibraryBootstrapReadiness', 'testReconcileSyntheticPhotosAfterImport')
MAX_FILE = 5_000_000
MAX_SCREENSHOT = 8_000_000
SCREENSHOT_PIXELS = {target['row'] + '-' + label + '.png': target['pixels']
                     for target in TARGETS for label in CASES}
MAX_PACKET = 20_000_000
MAX_ATTACHMENT_MANIFEST = 1_000_000
CAPTURE_CLEANUP_SECONDS = 15
CAPTURE_FINALIZATION_SECONDS = 5
CAPTURE_PATHS = {
    '.github/workflows/store-screenshots.yml',
    'Documentation/store-screenshots.md', UI_PATH,
    'Scripts/store_screenshots.py', 'Scripts/test_store_screenshots.py',
    'Scripts/probe_photos_bootstrap.py', 'Scripts/test_store_screenshots_route.py',
    'Scripts/store_display_assets.py', 'Scripts/test_store_display_assets.py',
    'Scripts/test_store_display_ui_source.py', 'StoreCaptureAssets/README.md',
    'StoreCaptureAssets/manifest.json', 'StoreCaptureAssets/demo-coast-sunny.png',
    'StoreCaptureAssets/demo-citrus-sunny.png',
}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path = Path(path)
    payload = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.' + path.name + '-', dir=path.parent, delete=False) as stream:
            temporary = stream.name
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, timeout=15).decode().strip()


def verify_source(root=ROOT, runtime=False):
    """545 exact prior inputs plus one precisely reversible UI instrumentation file."""
    root = Path(root)
    raw = (root / 'Scripts/original-ios-source-contract.json').read_bytes()
    need(sha(raw) == CONTRACT_SHA, 'Changed qualified source contract')
    contract = load_json(raw)
    expected = contract['files']
    need(len(expected) == 546, 'Changed protected membership')
    tracked = git(root, 'ls-files', '-z', '--', *contract['roots']).split('\0')
    tracked = [p for p in tracked if p]
    need(tracked == [p for p, _ in expected], 'Changed product/test/project membership')
    unchanged = []
    for path, digest in expected:
        source = root / path
        need(source.is_file() and not source.is_symlink(), 'Unsafe protected source: ' + path)
        actual = sha(source.read_bytes())
        if path == UI_PATH:
            need(digest == UI_BASE_SHA and actual == UI_CAPTURE_SHA, 'Unreviewed UI instrumentation')
            data = source.read_bytes()
            start = b'    // BEGIN FIXED STORE DISPLAY METHODS\n'
            end = b'    private func emitScreenshot(_ name: String) {\n'
            need(data.count(start) == data.count(end) == 1, 'Ambiguous display method block')
            a, b = data.index(start), data.index(end)
            need(a < b and sha(data[a:b]) == DISPLAY_BLOCK_SHA, 'Changed fixed display methods')
            prior = data[:a] + data[b:]
            need(sha(prior) == UI_PRIOR_CAPTURE_SHA and prior.count(INSERTION) == 1
                 and sha(prior.replace(INSERTION, b'')) == UI_BASE_SHA,
                 'Changes exceed the exact display additions and inherited screenshot insertion')
        else:
            need(actual == digest, 'Changed protected source: ' + path)
            unchanged.append([path, actual])
    need(len(unchanged) == 545, 'Changed unchanged-source count')
    result = {'schema': 'Celluloid.StoreCaptureSource.1', 'product_source_sha': PRODUCT_SOURCE,
              'product_source_tree': PRODUCT_TREE, 'supervision_base_tree': BASE_TREE,
              'supervision_public_base_sha': PUBLIC_BASE, 'unchanged_protected_files': 545,
              'unchanged_protected_fingerprint': sha(json.dumps(unchanged, separators=(',', ':')).encode()),
              'ui_test_instrumentation': {'path': UI_PATH, 'prior_sha256': UI_BASE_SHA,
                                         'prior_capture_sha256': UI_PRIOR_CAPTURE_SHA,
                                         'capture_sha256': UI_CAPTURE_SHA, 'insert_sha256': sha(INSERTION),
                                         'display_block_sha256': DISPLAY_BLOCK_SHA},
              'existing_test_bodies_and_assertions_unchanged': True,
              'new_display_methods': list(CASES.values()), 'original_qualification_methods': 106,
              'release_qualification': False, 'source_equivalence': False}
    from store_display_assets import verify_sources
    result['approved_demo_asset_manifest'] = verify_sources(root)
    if runtime:
        from validation_route import current_route, STORE_SCREENSHOTS
        need(current_route() == STORE_SCREENSHOTS, 'Wrong capture route')
        head = git(root, 'rev-parse', 'HEAD')
        need(head == os.environ['GITHUB_SHA'] == os.environ['GITHUB_WORKFLOW_SHA'], 'Wrong capture source')
        need(not git(root, 'status', '--porcelain', '--untracked-files=all'), 'Capture checkout changed')
        need(git(root, 'rev-parse', 'HEAD^1') == PUBLIC_BASE
             and git(root, 'rev-parse', 'HEAD^1^{tree}') == BASE_TREE, 'Wrong exact public capture parent identity/tree')
        changed = set(git(root, 'diff', '--name-only', BASE_TREE, 'HEAD').splitlines())
        need(changed == CAPTURE_PATHS, 'Unreviewed capture path delta')
        result.update(source_sha=head, source_tree=git(root, 'rev-parse', 'HEAD^{tree}'),
                      validation_route=STORE_SCREENSHOTS, capture_paths=sorted(changed),
                      workflow_sha256=sha((root / STORE_SCREENSHOTS['workflow_path']).read_bytes()))
    return result


def product_manifest(app):
    """Hash the actual built/installed bundle, including original framework/extension."""
    app = Path(app).resolve()
    info = plistlib.loads((app / 'Info.plist').read_bytes())
    need(info.get('CFBundleIdentifier') == 'Mango.Celluloid', 'Unexpected app identifier')
    need(info.get('DTPlatformName') == 'iphonesimulator', 'Capture requires simulator product')
    need((app / 'Frameworks/CelluloidKit.framework/CelluloidKit').is_file(), 'Missing original framework')
    need((app / 'PlugIns/CelluloidPhotoExtension.appex/CelluloidPhotoExtension').is_file(), 'Missing Photos extension')
    rows = []
    for path in sorted(app.rglob('*')):
        if path.is_symlink():
            need(path.resolve().is_relative_to(app), 'Bundle symlink escapes product')
            rows.append([str(path.relative_to(app)), 'symlink', os.readlink(path)])
        elif path.is_file():
            rows.append([str(path.relative_to(app)), path.stat().st_size, sha(path.read_bytes())])
    need(rows, 'Empty built app')
    return {'files': rows, 'fingerprint': sha(json.dumps(rows, separators=(',', ':')).encode()),
            'bundle_identifier': info['CFBundleIdentifier'], 'platform': info['DTPlatformName'],
            'version': info.get('CFBundleShortVersionString'), 'build': info.get('CFBundleVersion')}


def select_devices(runtimes, types, devices):
    available = [r for r in runtimes['runtimes'] if r.get('isAvailable') and r.get('version') == '27.0'
                 and r.get('identifier', '').startswith('com.apple.CoreSimulator.SimRuntime.iOS-')]
    need(len(available) == 1, 'Exactly one observed available iOS27.0 runtime required')
    runtime = available[0]
    need(not any(d.get('state') == 'Booted' for group in devices['devices'].values() for d in group),
         'Capture requires a fresh idle Mac simulator host')
    output = []
    for target in TARGETS:
        model_types = [d for d in types['devicetypes'] if d.get('name') == target['model']]
        need(len(model_types) == 1, 'Required exact model unavailable: ' + target['model'])
        need(type(model_types[0].get('identifier')) is str
             and model_types[0]['identifier'].startswith('com.apple.CoreSimulator.SimDeviceType.'), 'Invalid observed device type')
        output.append({**target, 'device_type': model_types[0]['identifier'],
                       'runtime': runtime['identifier'], 'runtime_version': runtime['version'],
                       'observed_runtime': runtime, 'observed_device_type': model_types[0]})
    return output


def png_metadata(data):
    need(0 < len(data) <= MAX_SCREENSHOT and data.startswith(b'\x89PNG\r\n\x1a\n'), 'Invalid or oversized original PNG')
    offset = 8
    chunks = []
    compressed = []
    header = None
    while offset < len(data):
        need(offset + 12 <= len(data), 'Truncated PNG chunk')
        size = struct.unpack('>I', data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        end = offset + 12 + size
        need(end <= len(data), 'PNG chunk outside file')
        payload = data[offset + 8:offset + 8 + size]
        need(zlib.crc32(kind + payload) & 0xffffffff == struct.unpack('>I', data[end - 4:end])[0], 'PNG CRC mismatch')
        if not chunks:
            need(kind == b'IHDR' and size == 13, 'PNG missing first IHDR')
            header = struct.unpack('>IIBBBBB', payload)
        else:
            need(kind != b'IHDR', 'Duplicate PNG IHDR')
        chunks.append(kind)
        if kind == b'IDAT':
            compressed.append(payload)
        offset = end
        if kind == b'IEND':
            need(size == 0 and offset == len(data), 'Data after PNG IEND')
            break
    need(header is not None and chunks[-1] == b'IEND' and b'IDAT' in chunks, 'Incomplete PNG')
    width, height, depth, color, compression, filtering, interlace = header
    depths = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
    need(0 < width <= 2064 and 0 < height <= 2752 and color in depths and depth in depths[color]
         and compression == filtering == interlace == 0, 'Unsupported native PNG header')
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
    stride = (width * channels * depth + 7) // 8 + 1
    decoder = zlib.decompressobj()
    raster = decoder.decompress(b''.join(compressed), stride * height + 1)
    need(decoder.eof and not decoder.unused_data and len(raster) == stride * height,
         'Invalid bounded PNG raster')
    need(all(raster[offset] <= 4 for offset in range(0, len(raster), stride)), 'Invalid PNG filter')
    return {'format': 'PNG', 'width': width, 'height': height, 'bit_depth': depth, 'color_type': color,
            'has_alpha_channel_or_transparency': color in {4, 6} or b'tRNS' in chunks,
            'bytes': len(data), 'sha256': sha(data), 'resized': False, 'reencoded': False}


def attachment_records(value):
    """Xcode27's observed flat manifest: test row owns each attachment."""
    need(type(value) is list and len(value) <= 32, 'Invalid or unbounded attachment rows')
    total = 0
    for row in value:
        need(type(row) is dict, 'Invalid attachment test row')
        attachments = row.get('attachments', [])
        need(type(attachments) is list and len(attachments) <= 256, 'Invalid or unbounded row attachments')
        total += len(attachments)
        need(total <= 512, 'Unbounded total attachment records')
        for item in attachments:
            need(type(item) is dict, 'Invalid attachment item')
            yield row.get('testIdentifier'), item


def select_pngs(folder, device, source, product):
    folder = Path(folder).resolve()
    manifest_path = folder / 'manifest.json'
    need(manifest_path.is_file() and not manifest_path.is_symlink() and manifest_path.stat().st_size <= MAX_ATTACHMENT_MANIFEST,
         'Missing/bounded attachment manifest')
    selected = {}
    for test, attachment in attachment_records(load_json(manifest_path.read_text())):
        human = attachment.get('suggestedHumanReadableName', '')
        match = re.fullmatch(r'celluloid-store-(edited-fixture|collage-preview)(?:_[A-Za-z0-9_-]+)?(?:\.png)?', human)
        if not match:
            continue
        label = match[1]
        need(label not in selected, 'Duplicate named capture')
        need(isinstance(test, str) and test.removesuffix('()') in {
            'CelluloidUITests/' + CASES[label], 'CelluloidUITests/CelluloidUITests/' + CASES[label]},
            'Screenshot is not bound to its exact existing test')
        # Actual retained Xcode27 evidence proves this UUID is a direct string
        # value on the item, but did not preserve that field's spelling. Bind
        # the exact scalar UUID and retain the observed key, never a substring,
        # case/configuration name, child dict, or guessed polymorphic schema.
        device_keys = sorted(key for key, value in attachment.items() if type(value) is str and value == device['id'])
        need(device_keys and ('deviceId' not in attachment or attachment['deviceId'] == device['id']),
             'Attachment lacks exact owned device UUID or contradicts deviceId')
        filename = attachment.get('exportedFileName')
        need(isinstance(filename, str) and filename == Path(filename).name, 'Unsafe attachment filename')
        path = folder / filename
        need(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(folder), 'Unsafe attachment path')
        need(path.stat().st_size <= MAX_SCREENSHOT, 'Original PNG exceeds8MB; resizing forbidden')
        data = path.read_bytes()
        metadata = png_metadata(data)
        need([metadata['width'], metadata['height']] == device['pixels'], 'Wrong native screenshot dimensions; no fallback')
        selected[label] = (data, {**metadata, 'checkpoint': label, 'test_identifier': test,
                                 'export_attachment': attachment, 'attachment_device_uuid_keys': device_keys,
                                 'attachment_device_uuid_fields': {key: attachment[key] for key in device_keys},
                                 'source_sha': source['source_sha'],
                                 'product_source_sha': PRODUCT_SOURCE, 'product_fingerprint': product['fingerprint'],
                                 'device': device, 'visual_approval': 'pending', 'store_submission_approved': False})
    need(set(selected) == set(CASES), 'Exactly two original named PNGs required per device')
    return selected


def verify_summary(summary, device, raw_log, started_unix, now_unix, bundle_path):
    from consumer_runtime_binding import validate_raw_execution
    from platform_rendering_contract import RUNTIME_BUILD
    for key in ('passedTests', 'totalTestCount', 'failedTests', 'skippedTests', 'expectedFailures'):
        need(type(summary.get(key)) is int, 'Invalid finalized counter: ' + key)
    need(summary.get('result') == 'Passed' and summary.get('passedTests') == summary.get('totalTestCount') == 2,
         'Capture did not pass exactly two UI cases')
    need(all(summary.get(k) == 0 for k in ('failedTests', 'skippedTests', 'expectedFailures')), 'Incomplete UI capture cases')
    need(summary.get('testFailures') == [], 'Contradictory XCTest failures')
    for key in ('startTime', 'finishTime'):
        need(type(summary.get(key)) in (int, float) and math.isfinite(summary[key]), 'Invalid finalized result time')
    need(started_unix <= summary['startTime'] < summary['finishTime'] <= now_unix,
         'Stale or unfinalized capture interval')
    configurations = summary.get('devicesAndConfigurations', [])
    need(len(configurations) == 1, 'Ambiguous test destination')
    actual = configurations[0].get('device', {})
    need(actual.get('deviceId') == device['id'] and actual.get('modelName') == device['model']
         and actual.get('osVersion') == device['runtime_version'] and actual.get('platform') == 'iOS Simulator',
         'Actual XCTest device differs from requested capture model')
    need(actual.get('architecture') == 'arm64' and actual.get('osBuildNumber') == RUNTIME_BUILD,
         'Wrong actual runtime build/architecture')
    for key in ('passedTests', 'failedTests', 'skippedTests', 'expectedFailures'):
        need(type(configurations[0].get(key)) is int and configurations[0][key] == summary[key],
             'Contradictory device test counter')
    execution = validate_raw_execution(raw_log, summary)
    passed = re.findall(r"^\s*Test Case '([^']+)' passed \([0-9]+(?:\.[0-9]+)? seconds\)\.\s*$", raw_log, re.M)
    expected = {'-[CelluloidUITests.CelluloidUITests ' + method + ']' for method in CASES.values()}
    need(len(passed) == 2 and set(passed) == expected, 'Unexpected or missing actual UI invocation')
    result_paths = re.findall(r'^\s*(/[^\r\n]+\.xcresult)\s*$', raw_log, re.M)
    need(result_paths and set(result_paths) == {str(bundle_path)}, 'Raw result path differs from capture bundle')
    return execution


class Capture:
    def __init__(self, outer):
        self.outer = Path(outer).resolve()
        self.first = load_json((self.outer / 'store-capture-clock.json').read_text())
        need(self.first.get('schema') == 'Celluloid.StoreCaptureClock.1'
             and self.first['source_sha'] == os.environ['GITHUB_SHA']
             and self.first['run_id'] == os.environ['GITHUB_RUN_ID']
             and self.first['run_attempt'] == os.environ['GITHUB_RUN_ATTEMPT']
             and self.first['execution_budget_seconds'] == 3360, 'Wrong first-step capture clock')
        self.packet = self.outer / 'store-capture-evidence'
        self.packet.mkdir()
        self.devices = []
        self.selected_models = []
        self.creations = []
        self.preexisting_device_ids = set()
        self.preexisting_device_names = set()
        self.images = []
        self.commands = []
        self.cleanup = []
        self.counter = 0
        self.row = None
        self.fixtures = []
        self.installations = []

    def persist(self):
        write_json(self.outer / 'store-capture-progress.json', {
            'source': getattr(self, 'source', None), 'product': getattr(self, 'product', None),
            'fixtures': self.fixtures, 'installations': self.installations,
            'devices': self.devices, 'selected_models': self.selected_models,
            'creations': self.creations, 'screenshots': self.images,
            'commands': self.commands, 'cleanup': self.cleanup})

    def enter_row(self, row):
        from original_ios_process_guard import staged_context, require_clear
        from uikit_full_shipping_gate import CLOCK_SCHEMA, clock_status
        if self.row is not None:
            require_clear()
            need(self.cleanup and self.cleanup[-1]['row'] == self.row and self.cleanup[-1]['confirmed'],
                 'First owned simulator cleanup not confirmed; no second device')
        self.row = row
        self.row_root = self.outer / ('store-capture-' + row)
        self.row_root.mkdir()
        os.environ['RUNNER_TEMP'] = str(self.row_root)
        os.environ['CELLULOID_FULL_ROW'] = row
        self.context = staged_context()
        need(self.context is not None, 'Capture owned guard must be active')
        self.clock = {'schema': CLOCK_SCHEMA, **self.context,
                      **{k: self.first[k] for k in ('started_monotonic', 'started_unix', 'execution_budget_seconds')}}
        clock_status(self.clock, self.context)
        write_json(self.row_root / 'full-shipping-clock.json', self.clock)

    def command(self, phase, label, args, ceiling=None):
        from native_process import run
        from original_ios_process_guard import require_clear
        from uikit_full_shipping_gate import admit_phase, check_completion, WORK_CEILINGS, TAIL_PHASES, WORK_SECONDS
        admit_phase(self.clock, self.context, phase)
        seconds, phase_end = TAIL_PHASES.get(phase, (WORK_CEILINGS.get(phase), WORK_SECONDS))
        if ceiling is not None:
            seconds = min(seconds, ceiling)
        enclosing_deadline = self.clock['started_monotonic'] + phase_end
        reserve = CAPTURE_CLEANUP_SECONDS + CAPTURE_FINALIZATION_SECONDS
        need(seconds > 0 and time.monotonic() + seconds + reserve <= enclosing_deadline,
             'Full fixed command, cleanup and finalization do not fit phase/work deadline')
        self.counter += 1
        log_name = '%02d-%s.log' % (self.counter, label)
        record = {'row': self.row, 'phase': phase, 'label': label, 'command': list(map(str, args)),
                  'exit_code': None, 'state': 'admitted', 'log': log_name, 'timeout_seconds': seconds,
                  'enclosing_deadline_monotonic': enclosing_deadline,
                  'cleanup_reserve_seconds': CAPTURE_CLEANUP_SECONDS,
                  'finalization_reserve_seconds': CAPTURE_FINALIZATION_SECONDS}
        self.commands.append(record)
        self.persist()
        try:
            need(time.monotonic() + seconds + reserve <= enclosing_deadline,
                 'Late persistence consumed fixed command/cleanup/finalization allowance')
            result = run(args, timeout=seconds, check=True, log_name=log_name, echo=False,
                         capture_deadline=enclosing_deadline)
        except BaseException as error:
            record.update(state='failed-or-unconfirmed', error={'type': type(error).__name__, 'message': str(error)[:1000]})
            self.persist()
            raise
        require_clear()
        check_completion(self.clock, self.context, phase)
        record.update(state='completed', exit_code=result.returncode)
        self.persist()
        check_completion(self.clock, self.context, phase)
        return result

    def bootstrap(self, device):
        from original_ios_process_guard import require_clear
        from uikit_full_shipping_gate import admit_phase, check_completion
        admit_phase(self.clock, self.context, 'bootstrap')
        before = list(sys.argv)
        try:
            sys.argv = ['probe_photos_bootstrap.py', device['id'], '--already-prepared']
            # No outer child owner around nested owned native commands.
            with (self.row_root / 'bootstrap.log').open('w') as log, contextlib.redirect_stdout(log):
                runpy.run_path(str(ROOT / 'Scripts/probe_photos_bootstrap.py'), run_name='__main__')
        finally:
            sys.argv = before
        require_clear()
        check_completion(self.clock, self.context, 'bootstrap')
        log = (self.row_root / 'bootstrap.log').read_text()
        from store_display_assets import MARKER
        need(log.count(MARKER) == 1 and 'BOOTSTRAP_EXACT_SIX_ASSETS_VERIFIED' not in log
             and 'BOOTSTRAP_RECOVERED_' not in log, 'Two-image display bootstrap did not complete cleanly')

    def create_device(self, specification):
        """Create once from exact observed type/runtime, then confirm ownership."""
        need(specification in self.selected_models and specification['row'] == self.row,
             'Unreviewed selected model or capture row')
        need(not any(record['row'] == self.row for record in self.creations), 'Duplicate owned create attempt forbidden')
        name = 'Celluloid Store Capture ' + self.context['run_id'] + '-' + self.context['run_attempt'] + '-' + self.row
        need(name not in self.preexisting_device_names, 'Owned capture name already exists')
        receipt = {'row': self.row, 'name': name, 'device_type': specification['device_type'],
                   'runtime': specification['runtime'], 'source_sha': self.context['source_sha'],
                   'run_id': self.context['run_id'], 'run_attempt': self.context['run_attempt'],
                   'create_exit_code': None, 'confirmed': False}
        self.creations.append(receipt)
        self.persist()
        created = self.command('boot', 'create-owned', ['xcrun', 'simctl', 'create', name,
                               specification['device_type'], specification['runtime']], 60)
        receipt.update(create_exit_code=created.returncode, stdout=created.stdout[:1000],
                       stdout_bytes=len(created.stdout.encode()), stdout_sha256=sha(created.stdout.encode()))
        self.persist()
        udid = created.stdout.strip()
        need(created.returncode == 0 and len(udid) == 36 and str(uuid.UUID(udid)).upper() == udid.upper(),
             'Create did not return exactly one canonical owned UUID')
        need(udid.upper() not in self.preexisting_device_ids
             and not any(d['id'].upper() == udid.upper() for d in self.devices), 'Create returned preexisting/foreign device UUID')
        receipt['device_id'] = udid
        self.persist()
        listing = load_json(self.command('boot', 'confirm-created',
                            ['xcrun', 'simctl', 'list', 'devices', 'available', '-j'], 30).stdout)
        matches = [(runtime, item) for runtime, group in listing['devices'].items() for item in group
                   if item.get('udid') == udid]
        need(len(matches) == 1, 'Created device readback missing/ambiguous')
        runtime, actual = matches[0]
        receipt['observed_readback'] = {'runtime': runtime, 'device': actual}
        self.persist()
        need(runtime == specification['runtime'] and actual.get('deviceTypeIdentifier') == specification['device_type']
             and actual.get('name') == name and actual.get('isAvailable') is True and actual.get('state') == 'Shutdown',
             'Created device identity/runtime/type/Shutdown state mismatch')
        need(not any(item.get('state') == 'Booted' for group in listing['devices'].values() for item in group),
             'Host is not idle after owned creation')
        receipt['confirmed'] = True
        device = {**specification, 'id': udid, 'owned_name': name, 'created_in_this_run': True}
        self.devices.append(device)
        self.persist()
        return device

    def require_owned_device(self, device):
        need(device in self.devices and device['row'] == self.row and any(
            record['row'] == self.row and record.get('device_id') == device['id'] and record['confirmed'] is True
            and record['create_exit_code'] == 0 for record in self.creations),
            'Native device mutation requires successful owned creation and exact readback')

    def run(self):
        self.enter_row('large-phone')
        self.source = verify_source(runtime=True)
        version = self.command('source-before', 'xcode-version', ['xcodebuild', '-version'], 30)
        need('Xcode 27.0' in version.stdout.splitlines(), 'Wrong exact Xcode toolchain')
        observed = [load_json(self.command('source-before', 'list-' + kind,
                    ['xcrun', 'simctl', 'list', kind, *(['available'] if kind == 'devices' else []), '-j'], 30).stdout)
                    for kind in ('runtimes', 'devicetypes', 'devices')]
        self.selected_models = select_devices(*observed)
        self.preexisting_device_ids = {str(item['udid']).upper() for group in observed[2]['devices'].values() for item in group}
        self.preexisting_device_names = {item.get('name') for group in observed[2]['devices'].values() for item in group}
        self.persist()
        from store_display_assets import ASSETS, no_legacy_files, prepare
        no_legacy_files()
        self.fixtures = list(ASSETS)
        self.persist()
        first_device = self.create_device(self.selected_models[0])
        first_id = first_device['id']
        self.command('build', 'build', ['xcodebuild', '-project', 'Celluloid.xcodeproj', '-scheme', 'Celluloid',
                     '-configuration', 'Debug', '-destination', 'platform=iOS Simulator,id=' + first_id,
                     '-derivedDataPath', '.build', '-jobs', '2', 'build-for-testing',
                     'CODE_SIGNING_ALLOWED=NO', 'COMPILER_INDEX_STORE_ENABLE=NO'])
        app = ROOT / '.build/Build/Products/Debug-iphonesimulator/Celluloid.app'
        self.product = product_manifest(app)
        self.persist()
        for index, specification in enumerate(self.selected_models):
            if index:
                self.enter_row(specification['row'])
                device = self.create_device(specification)
            else:
                device = first_device
            self.require_owned_device(device)
            udid = device['id']
            self.command('boot', 'boot', ['xcrun', 'simctl', 'boot', udid])
            self.command('bootstatus', 'bootstatus', ['xcrun', 'simctl', 'bootstatus', udid, '-b'])
            self.command('fixture-stage', 'install', ['xcrun', 'simctl', 'install', udid, str(app)], 600)
            installed = self.command('fixture-stage', 'installed-container',
                         ['xcrun', 'simctl', 'get_app_container', udid, 'Mango.Celluloid', 'app'], 120).stdout.strip()
            installed_path = Path(installed)
            need(installed_path.is_absolute() and installed_path.is_dir(), 'Installed app container unavailable')
            installed_path = installed_path.resolve()
            need('/Devices/' + udid + '/data/Containers/Bundle/Application/' in str(installed_path)
                 and installed_path.name == 'Celluloid.app', 'Installed container belongs to another simulator/app')
            need(product_manifest(installed_path) == self.product, 'Installed product differs from built app')
            staging = {'installed_app': str(installed_path), 'binary_sha256': sha((app / 'Celluloid').read_bytes())}
            self.command('privacy', 'photos-grant', ['xcrun', 'simctl', 'privacy', udid, 'grant', 'photos', 'Mango.Celluloid'])
            prepare(ROOT)
            self.bootstrap(device)
            self.command('appearance', 'dark-appearance', ['xcrun', 'simctl', 'ui', udid, 'appearance', 'dark'])
            bundle = self.row_root / 'StoreCapture.xcresult'
            command = ['xcodebuild', '-project', 'Celluloid.xcodeproj', '-scheme', 'Celluloid', '-configuration', 'Debug',
                       '-destination', 'platform=iOS Simulator,id=' + udid, '-derivedDataPath', '.build',
                       '-resultBundlePath', str(bundle), '-parallel-testing-enabled', 'NO', '-collect-test-diagnostics', 'never']
            command += ['-only-testing:CelluloidUITests/CelluloidUITests/' + method for method in CASES.values()]
            command += ['test-without-building', 'CODE_SIGNING_ALLOWED=NO']
            need('TEST_RUNNER_CELLULOID_STORE_CAPTURE' not in os.environ, 'Unexpected ambient capture opt-in')
            os.environ['TEST_RUNNER_CELLULOID_STORE_CAPTURE'] = '1'
            try:
                actual = self.command('ui', 'capture-ui', command)
            finally:
                os.environ.pop('TEST_RUNNER_CELLULOID_STORE_CAPTURE', None)
            summary = load_json(self.command('product-readbacks', 'capture-summary',
                         ['xcrun', 'xcresulttool', 'get', 'test-results', 'summary', '--path', str(bundle)], 45).stdout)
            execution = verify_summary(summary, device, actual.stdout + '\n' + actual.stderr,
                                       self.first['started_unix'], time.time(), bundle)
            write_json(self.row_root / 'capture-summary.json', summary)
            write_json(self.row_root / 'capture-execution.json', execution)
            exports = self.row_root / 'attachments'
            self.command('product-readbacks', 'capture-attachments', ['xcrun', 'xcresulttool', 'export', 'attachments',
                         '--path', str(bundle), '--output-path', str(exports)], 45)
            for label, (data, receipt) in select_pngs(exports, device, self.source, self.product).items():
                filename = device['row'] + '-' + label + '.png'
                (self.packet / filename).write_bytes(data)
                self.images.append({'name': filename, **receipt})
                self.persist()
            from uikit_installed_identity import readback, validate as validate_installed
            def installed_readback(args, timeout, echo):
                return self.command('product-readbacks', 'installed-after-tests', args, timeout)
            after_installation = readback(installed_readback, udid, staging)
            validate_installed(after_installation, udid, staging)
            need(product_manifest(app) == self.product and product_manifest(after_installation['app_path']) == self.product,
                 'Built/installed product changed during capture')
            self.installations.append({'row': self.row, 'before': staging, 'after': after_installation})
            self.persist()
            self.require_owned_device(device)
            self.command('shutdown', 'shutdown', ['xcrun', 'simctl', 'shutdown', udid], 45)
            state = load_json(self.command('shutdown', 'confirm-shutdown', ['xcrun', 'simctl', 'list', 'devices', 'available', '-j'], 15).stdout)
            matches = [d for group in state['devices'].values() for d in group if d.get('udid') == udid]
            need(len(matches) == 1 and matches[0].get('state') == 'Shutdown', 'Owned shutdown unconfirmed')
            self.require_owned_device(device)
            self.command('delete', 'delete', ['xcrun', 'simctl', 'delete', udid], 45)
            state = load_json(self.command('delete', 'confirm-delete', ['xcrun', 'simctl', 'list', 'devices', 'available', '-j'], 15).stdout)
            need(not any(d.get('udid') == udid for group in state['devices'].values() for d in group), 'Owned deletion unconfirmed')
            self.cleanup.append({'row': self.row, 'device_id': udid, 'shutdown_exit': 0, 'delete_exit': 0, 'confirmed': True})
            self.persist()
        need(verify_source(runtime=True) == self.source, 'Capture source changed')
        need(len(self.images) == 4 and len(self.cleanup) == 2, 'Capture packet incomplete')
        self.finish(True)

    def finish(self, completed, error=None):
        """Pure file retention only; safe even after an unknown process termination."""
        report = {'schema': 'Celluloid.StoreCapturePacket.1', 'complete': completed,
                  'source': getattr(self, 'source', None), 'product': getattr(self, 'product', None),
                  'fixtures': self.fixtures,
                  'installations': self.installations,
                  'first_step_clock': self.first, 'devices': self.devices, 'screenshots': self.images,
                  'selected_models': self.selected_models, 'creations': self.creations,
                  'commands': self.commands, 'cleanup': self.cleanup, 'error': error,
                  'ui_cases_per_device': list(CASES.values()), 'setup_cases_per_device': list(SETUP_CASES),
                  'ui_cases_are_new_display_checks': True, 'original_ui_qualification_methods_rerun': False,
                  'full412_reexecuted': False, 'release_qualification': False,
                  'visual_approval': 'pending', 'store_submission_approved': False}
        for row in ('large-phone', 'large-ipad'):
            folder = self.outer / ('store-capture-' + row)
            if not folder.is_dir():
                continue
            for name in ('original-ios-process-failure.json', 'original-ios-process-inflight.json',
                         'full-shipping-clock.json', 'capture-summary.json', 'capture-execution.json',
                         'store-display-preparation.json', 'store-display-photos.json'):
                path = folder / name
                if path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_FILE:
                    shutil.copyfile(path, self.packet / (row + '-' + name))
            attachment_manifest = folder / 'attachments/manifest.json'
            if attachment_manifest.is_file() and not attachment_manifest.is_symlink():
                need(attachment_manifest.stat().st_size <= MAX_FILE, 'Raw attachment manifest exceeds5MB')
                shutil.copyfile(attachment_manifest, self.packet / (row + '-attachment-manifest.json'))
            for timing in sorted(folder.glob('*.log.timing.json')):
                if timing.is_file() and not timing.is_symlink():
                    need(timing.stat().st_size <= 100_000, 'Unbounded owned command timing receipt')
                    shutil.copyfile(timing, self.packet / (row + '-' + timing.name))
            for path in sorted(folder.glob('*.log')):
                if path.is_file() and not path.is_symlink():
                    if path.name.endswith('-capture-ui.log') or path.name in {
                            'bootstrap.log', 'bootstrap-readiness-before-import.log', 'bootstrap-reconcile-all.log'}:
                        need(path.stat().st_size <= MAX_FILE, 'Required actual case log exceeds5MB')
                        shutil.copyfile(path, self.packet / (row + '-' + path.name))
                        continue
                    with path.open('rb') as stream:
                        stream.seek(max(0, path.stat().st_size - 20_000))
                        (self.packet / (row + '-' + path.name + '.tail.txt')).write_bytes(stream.read(20_000))
        report['elapsed_seconds'] = time.monotonic() - self.first['started_monotonic']
        if report['elapsed_seconds'] > 3300:
            report['complete'] = False
            report['error'] = 'Capture/collection exceeded55minutes; upload reserve preserved'
        write_json(self.packet / 'capture.json', report)
        write_json(self.packet / 'manifest.json', {'schema': 'Celluloid.StoreCaptureFiles.1',
                   'files': [{'name': p.name, 'bytes': p.stat().st_size, 'sha256': sha(p.read_bytes())}
                             for p in sorted(self.packet.iterdir()) if p.is_file() and not p.is_symlink()
                             and p.name != 'manifest.json']})
        files = list(self.packet.iterdir())
        validate_packet_files(files)
        print('STORE_CAPTURE_PACKET', json.dumps({'directory': str(self.packet), 'complete': report['complete'],
                                                'files': len(files), 'bytes': sum(p.stat().st_size for p in files)}))
        need(report['complete'] or not completed, report['error'])


def validate_packet_files(files):
    """Only the four fixed native screenshot names receive the 8MB allowance."""
    need(files, 'Empty capture packet')
    for path in files:
        need(path.is_file() and not path.is_symlink(), 'Unsafe capture packet file')
        pixels = SCREENSHOT_PIXELS.get(path.name)
        if pixels is not None:
            need(path.stat().st_size <= MAX_SCREENSHOT, 'Fixed screenshot exceeds8MB')
            metadata = png_metadata(path.read_bytes())
            need([metadata['width'], metadata['height']] == pixels, 'Fixed screenshot has wrong native dimensions')
        else:
            need(path.suffix.lower() != '.png', 'Unexpected screenshot filename')
            need(path.stat().st_size <= MAX_FILE, 'Metadata/log exceeds5MB')
    need(sum(path.stat().st_size for path in files) <= MAX_PACKET,
         'Capture packet20MB cap; no image conversion allowed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['verify-source', 'run', 'retain-failure', 'upload-admission'])
    args = parser.parse_args()
    if args.action == 'verify-source':
        print(json.dumps(verify_source(), indent=2))
        return
    outer = Path(os.environ['RUNNER_TEMP'])
    if args.action == 'retain-failure':
        # A killed outer runner may never reach its exception handler. This path
        # performs no subprocess/native operation and preserves that uncertainty.
        capture = Capture.__new__(Capture)
        capture.outer = outer.resolve()
        capture.first = load_json((outer / 'store-capture-clock.json').read_text())
        capture.packet = outer / 'store-capture-evidence'
        need(not capture.packet.is_symlink(), 'Unsafe capture evidence destination')
        capture.packet.mkdir(exist_ok=True)
        progress_path = outer / 'store-capture-progress.json'
        warnings = []
        def optional_object(path):
            if not path.exists() and not path.is_symlink():
                return {}
            try:
                need(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_FILE,
                     'Unsafe or unbounded optional progress/report')
                value = load_json(path.read_text())
                need(type(value) is dict, 'Optional progress/report is not an object')
                return value
            except (OSError, ValueError, UnicodeError) as error:
                warnings.append({'file': path.name, 'error': type(error).__name__, 'message': str(error)[:300]})
                return {}
        progress = optional_object(progress_path)
        capture.source = progress.get('source') if type(progress.get('source')) is dict else None
        capture.product = progress.get('product') if type(progress.get('product')) is dict else None
        for attribute, key in (('fixtures', 'fixtures'), ('installations', 'installations'),
                               ('selected_models', 'selected_models'), ('creations', 'creations'),
                               ('devices', 'devices'), ('images', 'screenshots'),
                               ('commands', 'commands'), ('cleanup', 'cleanup')):
            value = progress.get(key, [])
            if type(value) is not list:
                warnings.append({'file': progress_path.name, 'error': 'InvalidFieldType', 'field': key})
                value = []
            setattr(capture, attribute, value)
        prior = capture.packet / 'capture.json'
        error = {'type': 'CaptureDidNotSucceed', 'message': 'Native outcome remains unsuccessful or unconfirmed; no automatic cleanup/retry'}
        prior_error = optional_object(prior).get('error')
        if type(prior_error) in (str, dict):
            error = prior_error
        if warnings:
            error = {'original_capture_error': error, 'optional_report_read_errors': warnings}
        capture.finish(False, error)
        return
    if args.action == 'upload-admission':
        first = load_json((outer / 'store-capture-clock.json').read_text())
        need(0 <= time.monotonic() - first['started_monotonic'] <= 3300, 'No fixed upload allocation remains')
        files = list((outer / 'store-capture-evidence').iterdir())
        validate_packet_files(files)
        return
    capture = Capture(outer)
    try:
        capture.run()
    except BaseException as error:
        capture.finish(False, {'type': type(error).__name__, 'message': str(error)[:1000]})
        raise
    finally:
        os.environ['RUNNER_TEMP'] = str(outer)


if __name__ == '__main__':
    main()
