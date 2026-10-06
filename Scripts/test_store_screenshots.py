"""Portable fixed-capture interface and corruption/failure tests; no native tools."""
import copy
import contextlib
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


def selected_device():
    """File-only evidence tests supply an independently observed synthetic ID."""
    return {**capture.select_devices(*device_catalog())[0], 'id': str(uuid.uuid4()).upper()}


@contextlib.contextmanager
def isolated_runner():
    case = RunnerInterfacesTests()
    case.setUp()
    try:
        yield case
    finally:
        case.doCleanups()


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

    def test_runtime_source_requires_public_parent_commit_even_when_tree_matches(self):
        contract = json.loads((capture.ROOT / 'Scripts/original-ios-source-contract.json').read_text())
        parent = [capture.PUBLIC_BASE]
        def git(root, *args):
            if args[0] == 'ls-files':
                return '\0'.join(name for name, _ in contract['files']) + '\0'
            answers = {('rev-parse', 'HEAD'): 'a' * 40,
                       ('rev-parse', 'HEAD^1'): parent[0],
                       ('rev-parse', 'HEAD^1^{tree}'): capture.BASE_TREE,
                       ('rev-parse', 'HEAD^{tree}'): 'b' * 40,
                       ('status', '--porcelain', '--untracked-files=all'): '',
                       ('diff', '--name-only', capture.BASE_TREE, 'HEAD'): '\n'.join(sorted(capture.CAPTURE_PATHS))}
            self.assertIn(args, answers)
            return answers[args]
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, environment(directory), clear=True), patch.object(capture, 'git', side_effect=git), patch('subprocess.Popen', side_effect=AssertionError('source test must not dispatch')):
            proof = capture.verify_source(runtime=True)
            self.assertEqual(proof['supervision_public_base_sha'], 'ef07f3229517db656b970b136a8071f385185f75')
            self.assertEqual(proof['supervision_base_tree'], 'cdde7dae9e9a2ad92c04dc19990a4df663bdd27a')
            parent[0] = '1d28' + '0' * 36
            with self.assertRaisesRegex(ValueError, 'public capture parent'):
                capture.verify_source(runtime=True)

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

    def test_missing_exact_device_type_has_no_substitute(self):
        values = device_catalog()
        selected = capture.select_devices(*values)
        self.assertEqual([d['model'] for d in selected], ['iPhone 17 Pro', 'iPad Pro 13-inch (M5)'])
        self.assertTrue(all('id' not in item for item in selected))
        self.assertEqual([d['observed_device_type'] for d in selected], values[1]['devicetypes'])
        self.assertTrue(all(d['observed_runtime'] == values[0]['runtimes'][0] for d in selected))
        altered = copy.deepcopy(values)
        altered[1]['devicetypes'][0]['name'] = 'iPhone 18 Pro Max'
        with self.assertRaises(ValueError):
            capture.select_devices(*altered)

    def test_duplicate_exact_type_or_runtime_and_booted_host_fail_closed(self):
        for mode in ('duplicate-type', 'duplicate-runtime', 'booted'):
            values = device_catalog()
            group = next(iter(values[2]['devices'].values()))
            if mode == 'duplicate-type':
                values[1]['devicetypes'].append(copy.deepcopy(values[1]['devicetypes'][0]))
            elif mode == 'duplicate-runtime':
                values[0]['runtimes'].append(copy.deepcopy(values[0]['runtimes'][0]))
            else:
                group[0]['state'] = 'Booted'
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                capture.select_devices(*values)

    def test_absent_or_duplicate_precreated_models_do_not_select_existing_instances(self):
        for mode in ('absent-phone', 'empty-runtime', 'duplicate-precreated'):
            values = device_catalog()
            group = next(iter(values[2]['devices'].values()))
            if mode == 'absent-phone':
                group[:] = [d for d in group if d['name'] != 'iPhone 17 Pro']
            elif mode == 'empty-runtime':
                group.clear()
            else:
                group.append(dict(group[0], udid=str(uuid.uuid4()).upper()))
            with self.subTest(mode=mode):
                selected = capture.select_devices(*values)
                self.assertEqual([d['model'] for d in selected], [t['model'] for t in capture.TARGETS])
                self.assertTrue(all('id' not in d for d in selected))

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
            device = selected_device()
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
                device = selected_device()
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
            device = selected_device()
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
                device = selected_device()
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
            device = selected_device()
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
            device = selected_device()
            (folder / 'manifest.json').write_text('[{"attachments":[],"attachments":[]}]')
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                capture.select_pngs(folder, device, {'source_sha': 'a' * 40}, {'fingerprint': 'b' * 64})

    def test_summary_requires_exact_cases_counts_time_runtime_and_terminal(self):
        device = selected_device()
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
        self.selected_models = capture.select_devices(*self.catalog)
        self.precreated = copy.deepcopy(self.catalog[2])
        self.precreated_ids = {d['udid'] for group in self.precreated['devices'].values() for d in group}
        self.devices = []
        self.confirmed_ids = set()
        self.pending_creation = None
        self.creation_output = None
        self.creation_readback = None
        self.guarded_create_failure = None
        self.calls = []
        self.call_options = []
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
        self.call_options.append({'timeout': timeout, 'capture_deadline': capture_deadline, 'log_name': log_name})
        self.assertIsInstance(capture_deadline, (int, float))
        self.assertGreater(capture_deadline - time.monotonic(), timeout + 19)
        if self.fail_label and self.fail_label in log_name:
            raise PermissionError('unit-test denied command')
        output = ''
        if args == ['xcodebuild', '-version']:
            output = 'Xcode 27.0\nBuild version reviewed\n'
        elif args[:3] == ['xcrun', 'simctl', 'create']:
            self.assertEqual(len(args), 6)
            self.assertEqual(timeout, 60)
            name, device_type, runtime = args[3:]
            spec = next(d for d in self.selected_models if d['device_type'] == device_type)
            self.assertEqual(runtime, spec['runtime'])
            self.assertNotIn(name, [d['name'] for group in self.precreated['devices'].values() for d in group])
            if self.guarded_create_failure:
                process = MagicMock(pid=48123, returncode=None)
                process.poll.return_value = None
                if self.guarded_create_failure == 'nonzero':
                    process.returncode = 1
                    process.communicate.return_value = ('', 'ordinary create rejection')
                else:
                    process.communicate.side_effect = subprocess.TimeoutExpired(args, timeout, output=b'partial owned create')
                denial = PermissionError(errno.EPERM, 'owned signal denied') if self.guarded_create_failure == 'eperm' else None
                with patch('native_process.subprocess.Popen', return_value=process), patch('native_process.os.killpg', side_effect=denial):
                    return REAL_NATIVE_RUN(args, timeout=timeout, check=check, log_name=log_name, echo=echo,
                                           capture_deadline=capture_deadline)
            identifier = str(uuid.uuid4()).upper()
            created = {'name': name, 'udid': identifier, 'isAvailable': True, 'state': 'Shutdown',
                       'deviceTypeIdentifier': device_type}
            self.catalog[2]['devices'].setdefault(runtime, []).append(created)
            self.devices.append({**spec, 'id': identifier, 'name': name})
            self.pending_creation = (runtime, identifier)
            output = identifier + '\n'
            if self.creation_output == 'invalid': output = 'not-a-uuid\n'
            if self.creation_output == 'multiple': output += identifier + '\n'
            if self.creation_output == 'existing': output = next(iter(self.precreated_ids)) + '\n'
            if self.creation_output == 'foreign': output = str(uuid.uuid4()).upper() + '\n'
            if self.creation_output == 'lowercase': output = identifier.lower() + '\n'
        elif args[:3] == ['xcrun', 'simctl', 'list']:
            key = args[3]
            observed = copy.deepcopy(self.catalog[('runtimes', 'devicetypes', 'devices').index(key)])
            if key == 'devices' and self.pending_creation:
                self.assertEqual(args, ['xcrun', 'simctl', 'list', 'devices', 'available', '-j'])
                self.assertEqual(timeout, 30)
                runtime, identifier = self.pending_creation
                group = observed['devices'][runtime]
                row = next(d for d in group if d['udid'] == identifier)
                mutation = self.creation_readback
                if mutation == 'missing': group.remove(row)
                if mutation == 'foreign-uuid': row['udid'] = str(uuid.uuid4()).upper()
                if mutation == 'wrong-type': row['deviceTypeIdentifier'] = 'com.apple.CoreSimulator.SimDeviceType.unrelated'
                if mutation == 'wrong-name': row['name'] = 'Foreign simulator'
                if mutation == 'unavailable': row['isAvailable'] = False
                if mutation == 'truthy-availability': row['isAvailable'] = 1
                if mutation == 'booted': row['state'] = 'Booted'
                if mutation == 'unknown-state': row['state'] = 'Creating'
                if mutation == 'duplicate': group.append(copy.deepcopy(row))
                if mutation == 'wrong-runtime':
                    group.remove(row)
                    observed['devices']['com.apple.CoreSimulator.SimRuntime.iOS-other'] = [row]
                if mutation == 'duplicate-other-runtime':
                    observed['devices']['com.apple.CoreSimulator.SimRuntime.iOS-other'] = [copy.deepcopy(row)]
                if mutation == 'other-booted':
                    next(d for d in group if d['udid'] != identifier)['state'] = 'Booted'
                if mutation is None and self.creation_output not in {'invalid', 'multiple', 'existing', 'foreign'}:
                    self.confirmed_ids.add(identifier)
                self.pending_creation = None
            output = json.dumps(observed)
        elif args[0] == 'xcodebuild' and 'build-for-testing' in args:
            self.make_app()
        elif args[:3] == ['xcrun', 'simctl', 'boot']:
            self.assertIn(args[3], self.confirmed_ids, 'Boot must follow verified create/readback')
            self.assertNotIn(args[3], self.precreated_ids, 'Never boot an initial host instance')
            self.current = next(d for d in self.devices if d['id'] == args[3])
            next(d for d in next(iter(self.catalog[2]['devices'].values())) if d['udid'] == args[3])['state'] = 'Booted'
        elif args[:3] == ['xcrun', 'simctl', 'install']:
            self.assertIn(args[3], self.confirmed_ids)
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
            self.assertIn(args[3], self.confirmed_ids)
            self.assertNotIn(args[3], self.precreated_ids)
            next(d for d in next(iter(self.catalog[2]['devices'].values())) if d['udid'] == args[3])['state'] = 'Shutdown'
        elif args[:3] == ['xcrun', 'simctl', 'delete']:
            self.assertIn(args[3], self.confirmed_ids, 'Never delete an unverified returned UUID')
            self.assertNotIn(args[3], self.precreated_ids, 'Never delete an initial host instance')
            if not self.keep_deleted:
                group = next(iter(self.catalog[2]['devices'].values()))
                group[:] = [d for d in group if d['udid'] != args[3]]
        (Path(os.environ['RUNNER_TEMP']) / log_name).write_text(output)
        return subprocess.CompletedProcess(args, 0, output, '')

    def run_capture(self):
        runner = capture.Capture(self.outer)
        self.runner = runner
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
        create_positions = [i for i, c in enumerate(self.calls) if c[:3] == ['xcrun', 'simctl', 'create']]
        self.assertEqual(len(create_positions), 2)
        self.assertLess(create_positions[0], next(i for i, c in enumerate(self.calls) if 'build-for-testing' in c))
        self.assertLess(delete_positions[0], create_positions[1])
        self.assertLess(delete_positions[0], boot_positions[1])
        for index, position in enumerate(create_positions):
            self.assertEqual(self.calls[position][4:], [self.selected_models[index]['device_type'], self.selected_models[index]['runtime']])
            self.assertEqual(self.call_options[position]['timeout'], 60)
            self.assertEqual(self.calls[position + 1], ['xcrun', 'simctl', 'list', 'devices', 'available', '-j'])
            self.assertEqual(self.call_options[position + 1]['timeout'], 30)
        self.assertEqual(self.catalog[2], self.precreated, 'Every precreated instance must remain untouched')
        self.assertEqual(len({self.calls[i][3] for i in create_positions}), 2)
        clocks = [json.loads((self.outer / ('store-capture-' + d['row']) / 'full-shipping-clock.json').read_text()) for d in self.devices]
        self.assertEqual(clocks[0]['started_monotonic'], clocks[1]['started_monotonic'])
        self.assertEqual(clocks[0]['started_unix'], clocks[1]['started_unix'])
        result = json.loads((runner.packet / 'capture.json').read_text())
        self.assertTrue(result['complete'])
        self.assertEqual(len(result['screenshots']), 4)
        self.assertEqual(len(result['selected_models']), 2)
        self.assertEqual(len(result['creations']), 2)
        self.assertTrue(all(record['confirmed'] is True and record['create_exit_code'] == 0 for record in result['creations']))
        self.assertTrue(all(device['created_in_this_run'] is True and device['id'] not in self.precreated_ids for device in result['devices']))
        self.assertEqual([record['device_id'] for record in result['creations']], [device['id'] for device in result['devices']])
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
        self.assertEqual(sum(c[:3] == ['xcrun', 'simctl', 'create'] for c in self.calls), 1)

    def assert_guarded_failure_stops_second_device(self, kind):
        self.guarded_ui_failure = kind
        with self.assertRaises(TimeoutError):
            self.run_capture()
        self.assertIn('test-without-building', self.calls[-1])
        self.assertEqual(sum(c[:3] == ['xcrun', 'simctl', 'boot'] for c in self.calls), 1)
        self.assertFalse(any(c[:3] == ['xcrun', 'simctl', 'shutdown'] for c in self.calls))
        self.assertEqual(sum(c[:3] == ['xcrun', 'simctl', 'create'] for c in self.calls), 1)
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
        self.assertEqual(sum(c[:3] == ['xcrun', 'simctl', 'create'] for c in self.calls), 1)

    def assert_creation_stopped_before_device_mutation(self):
        self.assertEqual(sum(c[:3] == ['xcrun', 'simctl', 'create'] for c in self.calls), 1)
        self.assertFalse(any(c[:3] in (['xcrun', 'simctl', 'boot'], ['xcrun', 'simctl', 'install'],
                                      ['xcrun', 'simctl', 'shutdown'], ['xcrun', 'simctl', 'delete']) for c in self.calls))
        self.assertFalse(any('build-for-testing' in c for c in self.calls))
        self.assertFalse(self.runner.devices)
        self.assertEqual(len(self.runner.creations), 1)
        self.assertFalse(self.runner.creations[0]['confirmed'])

    def test_precreated_iphone_17_absence_still_completes_with_two_new_owned_devices(self):
        group = next(iter(self.catalog[2]['devices'].values()))
        group[:] = [d for d in group if d['name'] != 'iPhone 17 Pro']
        self.precreated = copy.deepcopy(self.catalog[2])
        self.precreated_ids = {d['udid'] for d in group}
        runner = self.run_capture()
        self.assertEqual([d['model'] for d in runner.devices], ['iPhone 17 Pro', 'iPad Pro 13-inch (M5)'])
        self.assertTrue(all(d['id'] not in self.precreated_ids for d in runner.devices))
        self.assertEqual(self.catalog[2], self.precreated)

    def test_missing_exact_type_fails_before_any_creation_or_build(self):
        self.catalog[1]['devicetypes'] = self.catalog[1]['devicetypes'][1:]
        with self.assertRaises(ValueError):
            self.run_capture()
        self.assertFalse(any(c[:3] == ['xcrun', 'simctl', 'create'] or 'build-for-testing' in c for c in self.calls))
        self.assertFalse(self.runner.devices)

    def test_invalid_multiple_existing_and_foreign_returned_uuid_cannot_be_booted_or_deleted(self):
        for mode in ('invalid', 'multiple', 'existing', 'foreign'):
            with self.subTest(mode=mode), isolated_runner() as case:
                case.creation_output = mode
                with self.assertRaises(ValueError):
                    case.run_capture()
                case.assert_creation_stopped_before_device_mutation()
                if mode != 'foreign':
                    self.assertEqual(case.calls[-1][:3], ['xcrun', 'simctl', 'create'])
                else:
                    self.assertEqual(case.calls[-1], ['xcrun', 'simctl', 'list', 'devices', 'available', '-j'])

    def test_creation_readback_requires_exact_type_runtime_name_uuid_state_and_idle_host(self):
        for mutation in ('missing', 'foreign-uuid', 'wrong-type', 'wrong-name', 'unavailable', 'truthy-availability',
                         'booted', 'unknown-state', 'duplicate', 'wrong-runtime', 'duplicate-other-runtime', 'other-booted'):
            with self.subTest(mutation=mutation), isolated_runner() as case:
                case.creation_readback = mutation
                with self.assertRaises(ValueError):
                    case.run_capture()
                case.assert_creation_stopped_before_device_mutation()
                self.assertEqual(case.calls[-1], ['xcrun', 'simctl', 'list', 'devices', 'available', '-j'])

    def test_failed_create_stops_with_normally_finalized_nonzero_and_no_mutation(self):
        self.guarded_create_failure = 'nonzero'
        with self.assertRaises(RuntimeError):
            self.run_capture()
        self.assert_creation_stopped_before_device_mutation()
        self.assertIsNone(process_guard.read_failure(Path(os.environ['RUNNER_TEMP']), process_guard.staged_context()))
        self.assertIsNone(process_guard.read_inflight(Path(os.environ['RUNNER_TEMP']), process_guard.staged_context()))

    def test_owned_create_timeout_and_signal_denial_never_trigger_readback_cleanup_or_retry(self):
        for mode in ('timeout', 'eperm'):
            with self.subTest(mode=mode), isolated_runner() as case:
                case.guarded_create_failure = mode
                with self.assertRaises(TimeoutError):
                    case.run_capture()
                case.assert_creation_stopped_before_device_mutation()
                self.assertEqual(case.calls[-1][:3], ['xcrun', 'simctl', 'create'])
                failure = process_guard.read_failure(Path(os.environ['RUNNER_TEMP']), process_guard.staged_context())
                self.assertEqual(failure['failure_kind'], 'timeout')
                if mode == 'eperm':
                    self.assertEqual(failure['cleanup']['status'], 'signal_denied')
                    self.assertEqual(len(failure['cleanup']['signals']), 1)

    def test_preexisting_owned_name_is_not_reused_or_deleted(self):
        group = next(iter(self.catalog[2]['devices'].values()))
        group[0]['name'] = 'Celluloid Store Capture 1234567-1-large-phone'
        with self.assertRaisesRegex(ValueError, 'name already exists'):
            self.run_capture()
        self.assertFalse(any(c[:3] in (['xcrun', 'simctl', 'create'], ['xcrun', 'simctl', 'delete']) for c in self.calls))

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
