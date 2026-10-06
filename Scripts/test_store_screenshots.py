"""Portable fixed-capture interface and corruption/failure tests; no native tools."""
import copy
import errno
import io
import json
import os
from pathlib import Path
import plistlib
import shutil
import struct
import subprocess
import tempfile
import time
import unittest
import uuid
import zlib
from unittest.mock import MagicMock, patch

import store_screenshots as capture
import native_process
import original_ios_process_guard as process_guard
from platform_rendering_contract import RUNTIME_BUILD
from test_store_screenshots_route import environment

REAL_NATIVE_RUN = native_process.run


def png(width=2, height=3, alpha=False):
    def chunk(kind, value):
        return struct.pack('>I', len(value)) + kind + value + struct.pack('>I', zlib.crc32(kind + value) & 0xffffffff)
    channels = 4 if alpha else 3
    raster = (b'\0' + b'\x80' * (width * channels)) * height
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6 if alpha else 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raster)) + chunk(b'IEND', b'')


def device_catalog():
    runtime = 'com.apple.CoreSimulator.SimRuntime.iOS-27-0'
    types = [{'name': t['model'], 'identifier': 'com.apple.CoreSimulator.SimDeviceType.test-' + str(i)}
             for i, t in enumerate(capture.TARGETS)]
    devices = [{'name': t['model'], 'udid': str(uuid.uuid4()).upper(), 'isAvailable': True,
                'state': 'Shutdown', 'deviceTypeIdentifier': types[i]['identifier']}
               for i, t in enumerate(capture.TARGETS)]
    return ({'runtimes': [{'identifier': runtime, 'isAvailable': True, 'version': '27.0'}]},
            {'devicetypes': types}, {'devices': {runtime: devices}})


def summary(device, bundle):
    now = time.time()
    counts = {'passedTests': 2, 'failedTests': 0, 'skippedTests': 0, 'expectedFailures': 0}
    data = {'result': 'Passed', 'totalTestCount': 2, **counts, 'testFailures': [],
            'startTime': now - 1, 'finishTime': now,
            'devicesAndConfigurations': [{**counts, 'device': {
                'deviceId': device['id'], 'modelName': device['model'], 'platform': 'iOS Simulator',
                'osVersion': '27.0', 'osBuildNumber': RUNTIME_BUILD, 'architecture': 'arm64'}}]}
    lines = []
    for method in capture.CASES.values():
        name = '-[CelluloidUITests.CelluloidUITests ' + method + ']'
        lines += ["Test Case '" + name + "' started.", "Test Case '" + name + "' passed (1.0 seconds)."]
    lines += ['Executed 2 tests, with 0 failures (0 unexpected) in 2.0 (2.0) seconds',
              'Test session results, code coverage, and logs:', str(bundle), '** TEST EXECUTE SUCCEEDED **']
    return data, '\n'.join(lines)


def exports(folder, device):
    folder.mkdir()
    manifest = []
    for label, method in capture.CASES.items():
        filename = label + '.png'
        (folder / filename).write_bytes(png(*device['pixels']))
        manifest.append({'testIdentifier': 'CelluloidUITests/' + method + '()', 'attachments': [{
            'exportedFileName': filename, 'suggestedHumanReadableName': 'celluloid-store-' + label + '_0_AAAAA.png',
            'deviceId': device['id'], 'deviceName': device['model'], 'configurationName': 'Test Scheme Action'}]})
    capture.write_json(folder / 'manifest.json', manifest)
    return manifest


class FileProofTests(unittest.TestCase):
    def test_actual_protected_inputs_and_exact_helper_reversal(self):
        result = capture.verify_source()
        self.assertEqual(result['unchanged_protected_files'], 545)
        self.assertEqual(result['unchanged_protected_fingerprint'], '7b88400237920b2dedd6371d88577eec3c8916ff99a165d199bcb61948acdbe5')
        self.assertFalse(result['source_equivalence'])
        self.assertFalse(result['release_qualification'])

    def test_source_hash_wont_silently_accept_another_helper(self):
        with patch.object(capture, 'UI_CAPTURE_SHA', '0' * 64), self.assertRaisesRegex(ValueError, 'instrumentation'):
            capture.verify_source()

    def test_png_keeps_native_bytes_and_reports_alpha_without_stripping(self):
        for alpha in (False, True):
            raw = png(alpha=alpha)
            result = capture.png_metadata(raw)
            self.assertEqual((result['width'], result['height']), (2, 3))
            self.assertEqual(result['sha256'], capture.sha(raw))
            self.assertEqual(result['has_alpha_channel_or_transparency'], alpha)
            self.assertFalse(result['resized'])
            self.assertFalse(result['reencoded'])

    def test_png_rejects_corrupt_truncated_appended_and_oversized_data(self):
        good = png()
        corrupt = bytearray(good)
        corrupt[25] ^= 1
        for raw in (b'jpeg', good[:-1], good + b'x', bytes(corrupt), b'x' * (capture.MAX_FILE + 1)):
            with self.subTest(size=len(raw)), self.assertRaises(ValueError):
                capture.png_metadata(raw)

    def test_png_rejects_plausible_header_with_invalid_raster(self):
        raw = bytearray(png())
        raw[16:20] = struct.pack('>I', 4)
        raw[29:33] = struct.pack('>I', zlib.crc32(raw[12:29]) & 0xffffffff)
        with self.assertRaisesRegex(ValueError, 'raster'):
            capture.png_metadata(bytes(raw))

    def test_missing_exact_model_has_no_substitute(self):
        values = device_catalog()
        selected = capture.select_devices(*values)
        self.assertEqual([d['model'] for d in selected], ['iPhone 17 Pro', 'iPad Pro 13-inch (M5)'])
        altered = copy.deepcopy(values)
        altered[2]['devices'][next(iter(altered[2]['devices']))][0]['name'] = 'iPhone 18 Pro Max'
        with self.assertRaisesRegex(ValueError, 'missing/ambiguous'):
            capture.select_devices(*altered)

    def test_duplicate_or_booted_device_fails_closed(self):
        for mode in ('duplicate', 'booted'):
            values = device_catalog()
            group = next(iter(values[2]['devices'].values()))
            if mode == 'duplicate':
                group.append(copy.deepcopy(group[0]))
            else:
                group[0]['state'] = 'Booted'
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                capture.select_devices(*values)

    def test_stale_seventh_fixture_is_rejected_before_import(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            for filename in capture.FIXTURE_NAMES:
                (root / filename).write_bytes(png())
            self.assertEqual(len(capture.fixture_files(root)), 6)
            (root / 'celluloid-composition-extra.png').write_bytes(png())
            with self.assertRaisesRegex(ValueError, 'membership'):
                capture.fixture_files(root)

    def test_exact_attachment_test_device_dimensions_and_bytes(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name) / 'exports'
            device = capture.select_devices(*device_catalog())[0]
            exports(folder, device)
            result = capture.select_pngs(folder, device, {'source_sha': 'a' * 40}, {'fingerprint': 'b' * 64})
            self.assertEqual(set(result), set(capture.CASES))
            for label, (raw, receipt) in result.items():
                self.assertEqual(raw, (folder / (label + '.png')).read_bytes())
                self.assertEqual(receipt['source_sha'], 'a' * 40)
                self.assertEqual(receipt['product_source_sha'], capture.PRODUCT_SOURCE)
                self.assertEqual(receipt['visual_approval'], 'pending')

    def test_attachment_rejects_wrong_test_device_size_and_duplicates(self):
        for mutation in ('test', 'device', 'size', 'duplicate', 'traversal'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as name:
                folder = Path(name) / 'exports'
                device = capture.select_devices(*device_catalog())[0]
                records = exports(folder, device)
                if mutation == 'test': records[0]['testIdentifier'] = 'CelluloidUITests/testOther()'
                if mutation == 'device': records[0]['attachments'][0]['deviceId'] = str(uuid.uuid4())
                if mutation == 'size': (folder / 'edited-fixture.png').write_bytes(png())
                if mutation == 'duplicate': records.append(copy.deepcopy(records[0]))
                if mutation == 'traversal': records[0]['attachments'][0]['exportedFileName'] = '../outside.png'
                capture.write_json(folder / 'manifest.json', records)
                with self.assertRaises(ValueError):
                    capture.select_pngs(folder, device, {'source_sha': 'a' * 40}, {'fingerprint': 'b' * 64})

    def test_attachment_identity_uses_exact_observed_uuid_without_guessing_key(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name) / 'exports'
            device = capture.select_devices(*device_catalog())[0]
            records = exports(folder, device)
            for row in records:
                item = row['attachments'][0]
                item['actualDeviceUUID'] = item.pop('deviceId')
                item['testIdentifier'] = 'Test Scheme Action'
            capture.write_json(folder / 'manifest.json', records)
            selected = capture.select_pngs(folder, device, {'source_sha': 'a' * 40}, {'fingerprint': 'b' * 64})
            self.assertEqual(selected['edited-fixture'][1]['attachment_device_uuid_keys'], ['actualDeviceUUID'])
            self.assertEqual(selected['edited-fixture'][1]['attachment_device_uuid_fields'], {'actualDeviceUUID': device['id']})
            records[0]['attachments'][0]['deviceId'] = str(uuid.uuid4())
            capture.write_json(folder / 'manifest.json', records)
            with self.assertRaisesRegex(ValueError, 'contradicts'):
                capture.select_pngs(folder, device, {'source_sha': 'a' * 40}, {'fingerprint': 'b' * 64})

    def test_attachment_nested_only_or_substring_uuid_cannot_bind_device(self):
        for mode in ('nested', 'substring'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as name:
                folder = Path(name) / 'exports'
                device = capture.select_devices(*device_catalog())[0]
                records = exports(folder, device)
                item = records[0]['attachments'][0]
                value = item.pop('deviceId')
                item['device'] = {'uuid': value} if mode == 'nested' else 'device-' + value
                capture.write_json(folder / 'manifest.json', records)
                with self.assertRaisesRegex(ValueError, 'exact owned device UUID'):
                    capture.select_pngs(folder, device, {'source_sha': 'a' * 40}, {'fingerprint': 'b' * 64})

    def test_attachment_child_cannot_override_parent_test_and_records_are_bounded(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name) / 'exports'
            device = capture.select_devices(*device_catalog())[0]
            records = exports(folder, device)
            records[0]['attachments'][0]['testIdentifier'] = records[0]['testIdentifier']
            records[0]['testIdentifier'] = 'CelluloidUITests/testUnrelated()'
            capture.write_json(folder / 'manifest.json', records)
            with self.assertRaisesRegex(ValueError, 'exact existing test'):
                capture.select_pngs(folder, device, {'source_sha': 'a' * 40}, {'fingerprint': 'b' * 64})
        for manifest in ({'nested': []}, [{}] * 33, [{'attachments': [{}] * 257}], [{'attachments': [{}] * 200}] * 3):
            with self.subTest(shape=type(manifest)), self.assertRaises(ValueError):
                list(capture.attachment_records(manifest))

    def test_all_incoming_json_uses_strict_duplicate_and_nonfinite_rejection(self):
        for raw in ('{"devices":[],"devices":[]}', '{"value":NaN}', '{"value":Infinity}', '{"value":1e9999}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                capture.load_json(raw)
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / 'report.json'
            with self.assertRaises(ValueError):
                capture.write_json(path, {'value': float('nan')})
            self.assertFalse(path.exists())
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            device = capture.select_devices(*device_catalog())[0]
            (folder / 'manifest.json').write_text('[{"attachments":[],"attachments":[]}]')
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                capture.select_pngs(folder, device, {'source_sha': 'a' * 40}, {'fingerprint': 'b' * 64})

    def test_summary_requires_exact_cases_counts_time_runtime_and_terminal(self):
        device = capture.select_devices(*device_catalog())[0]
        bundle = Path('/tmp/test-StoreCapture.xcresult')
        good, log = summary(device, bundle)
        self.assertTrue(capture.verify_summary(good, device, log, time.time() - 10, time.time() + 1, bundle)['aggregate_execution_passed'])
        for mutation in ('counter', 'device-count', 'failure', 'time', 'runtime', 'terminal', 'start', 'bundle'):
            value, text = copy.deepcopy(good), log
            if mutation == 'counter': value['passedTests'] = 2.0
            if mutation == 'device-count': value['devicesAndConfigurations'][0]['passedTests'] = 1
            if mutation == 'failure': value['testFailures'] = [{'failure': 'unexpected'}]
            if mutation == 'time': value['startTime'] = 1000
            if mutation == 'runtime': value['devicesAndConfigurations'][0]['device']['osBuildNumber'] = 'unknown'
            if mutation == 'terminal': text = text.replace('SUCCEEDED', 'FAILED')
            if mutation == 'start': text = text.replace(' started.', ' absent.')
            if mutation == 'bundle': text = text.replace(str(bundle), '/tmp/wrong.xcresult')
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                capture.verify_summary(value, device, text, time.time() - 10, time.time() + 1, bundle)


class RunnerInterfacesTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.base = Path(self.folder.name)
        self.root = self.base / 'checkout'
        self.root.mkdir()
        self.outer = self.base / 'runner'
        self.outer.mkdir()
        env = environment(self.outer)
        env.pop('CELLULOID_FULL_ROW')
        scope = patch.dict(os.environ, env, clear=True)
        scope.start()
        self.addCleanup(scope.stop)
        capture.write_json(self.outer / 'store-capture-clock.json', {
            'schema': 'Celluloid.StoreCaptureClock.1', 'source_sha': env['GITHUB_SHA'],
            'run_id': env['GITHUB_RUN_ID'], 'run_attempt': env['GITHUB_RUN_ATTEMPT'],
            'started_monotonic': time.monotonic() - 3, 'started_unix': time.time() - 3,
            'execution_budget_seconds': 3360})
        self.catalog = device_catalog()
        self.devices = capture.select_devices(*self.catalog)
        self.calls = []
        self.bootstrap_calls = []
        self.source = {'source_sha': env['GITHUB_SHA'], 'release_qualification': False}
        self.current = None
        self.fail_label = None
        self.keep_deleted = False
        self.foreign_container = False
        self.guarded_ui_failure = None
        self.app = self.root / '.build/Build/Products/Debug-iphonesimulator/Celluloid.app'

    def make_app(self):
        for path in ('Frameworks/CelluloidKit.framework/CelluloidKit', 'PlugIns/CelluloidPhotoExtension.appex/CelluloidPhotoExtension', 'Celluloid'):
            out = self.app / path
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b'unit-test-only product bytes')
        (self.app / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': 'Mango.Celluloid', 'CFBundleExecutable': 'Celluloid',
                    'DTPlatformName': 'iphonesimulator', 'CFBundleShortVersionString': '1.1', 'CFBundleVersion': '2'}))

    def native(self, args, timeout, check, log_name, echo, capture_deadline=None):
        args = list(map(str, args))
        self.calls.append(args)
        self.assertIsInstance(capture_deadline, (int, float))
        self.assertGreater(capture_deadline - time.monotonic(), timeout + 19)
        if self.fail_label and self.fail_label in log_name:
            raise PermissionError('unit-test denied command')
        output = ''
        if args == ['xcodebuild', '-version']:
            output = 'Xcode 27.0\nBuild version reviewed\n'
        elif args[:3] == ['xcrun', 'simctl', 'list']:
            key = args[3]
            output = json.dumps(self.catalog[('runtimes', 'devicetypes', 'devices').index(key)])
        elif args[0] == 'xcodebuild' and 'build-for-testing' in args:
            self.make_app()
        elif args[:3] == ['xcrun', 'simctl', 'boot']:
            self.current = next(d for d in self.devices if d['id'] == args[3])
            next(d for d in next(iter(self.catalog[2]['devices'].values())) if d['udid'] == args[3])['state'] = 'Booted'
        elif args[:3] == ['xcrun', 'simctl', 'install']:
            self.installed = self.base / 'Library/Developer/CoreSimulator/Devices' / self.current['id'] / 'data/Containers/Bundle/Application' / str(uuid.uuid4()) / 'Celluloid.app'
            shutil.copytree(self.app, self.installed)
        elif args[:3] == ['xcrun', 'simctl', 'get_app_container']:
            if self.foreign_container:
                foreign = self.base / 'foreign-readable/Celluloid.app'
                shutil.copytree(self.app, foreign)
                output = str(foreign)
            else:
                output = str(self.installed)
        elif args[0] == 'xcodebuild' and 'test-without-building' in args:
            if self.guarded_ui_failure:
                process = MagicMock(pid=48123, returncode=None)
                process.poll.return_value = None
                process.communicate.side_effect = subprocess.TimeoutExpired(args, timeout, output=b'partial owned capture')
                denial = PermissionError(errno.EPERM, 'owned signal denied') if self.guarded_ui_failure == 'eperm' else None
                with patch('native_process.subprocess.Popen', return_value=process), patch('native_process.os.killpg', side_effect=denial):
                    return REAL_NATIVE_RUN(args, timeout=timeout, check=check, log_name=log_name, echo=echo,
                                           capture_deadline=capture_deadline)
            self.assertEqual(os.environ.get('TEST_RUNNER_CELLULOID_STORE_CAPTURE'), '1')
            self.assertEqual([a for a in args if a.startswith('-only-testing:')],
                             ['-only-testing:CelluloidUITests/CelluloidUITests/' + m for m in capture.CASES.values()])
            self.bundle = Path(args[args.index('-resultBundlePath') + 1])
            self.bundle.mkdir()
            self.result_summary, output = summary(self.current, self.bundle)
        elif args[:4] == ['xcrun', 'xcresulttool', 'get', 'test-results']:
            output = json.dumps(self.result_summary)
        elif args[:4] == ['xcrun', 'xcresulttool', 'export', 'attachments']:
            exports(Path(args[args.index('--output-path') + 1]), self.current)
        elif args[:3] == ['xcrun', 'simctl', 'shutdown']:
            next(d for d in next(iter(self.catalog[2]['devices'].values())) if d['udid'] == args[3])['state'] = 'Shutdown'
        elif args[:3] == ['xcrun', 'simctl', 'delete'] and not self.keep_deleted:
            group = next(iter(self.catalog[2]['devices'].values()))
            group[:] = [d for d in group if d['udid'] != args[3]]
        (Path(os.environ['RUNNER_TEMP']) / log_name).write_text(output)
        return subprocess.CompletedProcess(args, 0, output, '')

    def run_capture(self):
        runner = capture.Capture(self.outer)
        def bootstrap(instance, device):
            self.bootstrap_calls.append(device['id'])
        with patch.object(capture, 'ROOT', self.root), patch.object(capture, 'verify_source', return_value=self.source), \
             patch.object(capture, 'fixture_files', return_value=[{'name': name, 'sha256': 'f' * 64} for name in capture.FIXTURE_NAMES]), \
             patch.object(capture.runpy, 'run_path', return_value={}), patch.object(capture.Capture, 'bootstrap', bootstrap), \
             patch('native_process.run', side_effect=self.native), patch('sys.stdout', io.StringIO()):
            runner.run()
        return runner

    def test_complete_fixed_command_interfaces_share_clock_and_require_cleanup(self):
        runner = self.run_capture()
        self.assertEqual(len(self.bootstrap_calls), 2)
        self.assertEqual(sum('build-for-testing' in c for c in self.calls), 1)
        self.assertEqual(sum('test-without-building' in c for c in self.calls), 2)
        boot_positions = [i for i, c in enumerate(self.calls) if c[:3] == ['xcrun', 'simctl', 'boot']]
        delete_positions = [i for i, c in enumerate(self.calls) if c[:3] == ['xcrun', 'simctl', 'delete']]
        self.assertLess(delete_positions[0], boot_positions[1])
        clocks = [json.loads((self.outer / ('store-capture-' + d['row']) / 'full-shipping-clock.json').read_text()) for d in self.devices]
        self.assertEqual(clocks[0]['started_monotonic'], clocks[1]['started_monotonic'])
        self.assertEqual(clocks[0]['started_unix'], clocks[1]['started_unix'])
        result = json.loads((runner.packet / 'capture.json').read_text())
        self.assertTrue(result['complete'])
        self.assertEqual(len(result['screenshots']), 4)
        self.assertFalse(result['release_qualification'])
        self.assertFalse(result['store_submission_approved'])
        self.assertEqual(result['visual_approval'], 'pending')
        for image in result['screenshots']:
            self.assertEqual(capture.sha((runner.packet / image['name']).read_bytes()), image['sha256'])

    def test_denial_stops_every_later_native_command_and_second_device(self):
        self.fail_label = 'capture-ui'
        with self.assertRaises(PermissionError):
            self.run_capture()
        self.assertIn('test-without-building', self.calls[-1])
        self.assertEqual(sum(c[:3] == ['xcrun', 'simctl', 'boot'] for c in self.calls), 1)
        self.assertFalse(any(c[:3] == ['xcrun', 'simctl', 'shutdown'] for c in self.calls))

    def assert_guarded_failure_stops_second_device(self, kind):
        self.guarded_ui_failure = kind
        with self.assertRaises(TimeoutError):
            self.run_capture()
        self.assertIn('test-without-building', self.calls[-1])
        self.assertEqual(sum(c[:3] == ['xcrun', 'simctl', 'boot'] for c in self.calls), 1)
        self.assertFalse(any(c[:3] == ['xcrun', 'simctl', 'shutdown'] for c in self.calls))
        failure = process_guard.read_failure(Path(os.environ['RUNNER_TEMP']), process_guard.staged_context())
        self.assertEqual(failure['failure_kind'], 'timeout')
        if kind == 'eperm':
            self.assertEqual(failure['cleanup']['status'], 'signal_denied')
            self.assertEqual(len(failure['cleanup']['signals']), 1)

    def test_actual_owned_timeout_blocks_second_device_and_export_cleanup(self):
        self.assert_guarded_failure_stops_second_device('timeout')

    def test_actual_owned_eperm_blocks_second_device_and_export_cleanup(self):
        self.assert_guarded_failure_stops_second_device('eperm')

    def test_unconfirmed_first_deletion_blocks_second_device(self):
        self.keep_deleted = True
        with self.assertRaisesRegex(ValueError, 'deletion unconfirmed'):
            self.run_capture()
        self.assertEqual(sum(c[:3] == ['xcrun', 'simctl', 'boot'] for c in self.calls), 1)

    def test_readable_identical_bundle_outside_owned_container_is_rejected(self):
        self.foreign_container = True
        with self.assertRaisesRegex(ValueError, 'another simulator/app'):
            self.run_capture()
        self.assertFalse(self.bootstrap_calls)
        self.assertEqual(self.calls[-1][:3], ['xcrun', 'simctl', 'get_app_container'])

    def test_command_does_not_shrink_full_allowance_to_remaining_work_time(self):
        runner = capture.Capture(self.outer)
        runner.enter_row('large-phone')
        start = runner.clock['started_monotonic']
        with patch('time.monotonic', return_value=start + 1781), patch('native_process.run') as run:
            with self.assertRaisesRegex(ValueError, 'Full fixed command'):
                runner.command('ui', 'capture-ui', ['xcodebuild'])
            run.assert_not_called()
        self.assertFalse(runner.commands)

    def test_late_progress_persistence_refuses_before_native_owner(self):
        runner = capture.Capture(self.outer)
        runner.enter_row('large-phone')
        now = [runner.clock['started_monotonic'] + 1770]
        def slow_persist():
            now[0] = runner.clock['started_monotonic'] + 1781
        with patch('time.monotonic', side_effect=lambda: now[0]), patch.object(runner, 'persist', side_effect=slow_persist), patch('native_process.run') as run:
            with self.assertRaisesRegex(ValueError, 'Late persistence'):
                runner.command('ui', 'capture-ui', ['xcodebuild'])
            run.assert_not_called()
        self.assertEqual(runner.commands[-1]['state'], 'failed-or-unconfirmed')

    def test_file_only_failure_retention_does_not_dispatch_subprocess(self):
        marker = self.outer / 'store-capture-large-phone'
        marker.mkdir()
        (marker / 'original-ios-process-inflight.json').write_text('{"state":"running"}')
        (marker / 'attachments').mkdir()
        (marker / 'attachments/manifest.json').write_text('[{"unrecognizedNativeSchema":true}]')
        with patch('sys.argv', ['store_screenshots.py', 'retain-failure']), patch('subprocess.Popen', side_effect=AssertionError('native dispatch forbidden')), patch('sys.stdout', io.StringIO()):
            capture.main()
        packet = self.outer / 'store-capture-evidence'
        self.assertFalse(json.loads((packet / 'capture.json').read_text())['complete'])
        self.assertEqual((packet / 'large-phone-original-ios-process-inflight.json').read_text(), '{"state":"running"}')
        self.assertEqual((packet / 'large-phone-attachment-manifest.json').read_text(), '[{"unrecognizedNativeSchema":true}]')

    def test_truncated_optional_progress_cannot_suppress_guard_retention(self):
        row = self.outer / 'store-capture-large-phone'
        row.mkdir()
        (row / 'original-ios-process-failure.json').write_text('{"preserve":"exact failure"}')
        (self.outer / 'store-capture-progress.json').write_text('{"devices":[')
        packet = self.outer / 'store-capture-evidence'
        packet.mkdir()
        (packet / 'capture.json').write_text('{"complete":')
        with patch('sys.argv', ['store_screenshots.py', 'retain-failure']), patch('subprocess.Popen', side_effect=AssertionError('native dispatch forbidden')), patch('sys.stdout', io.StringIO()):
            capture.main()
        result = json.loads((packet / 'capture.json').read_text())
        self.assertFalse(result['complete'])
        self.assertEqual(len(result['error']['optional_report_read_errors']), 2)
        self.assertEqual((packet / 'large-phone-original-ios-process-failure.json').read_text(), '{"preserve":"exact failure"}')


if __name__ == '__main__':
    unittest.main()
