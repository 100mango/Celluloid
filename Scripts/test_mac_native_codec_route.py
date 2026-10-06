"""Portable fixed-route and failure-injection contracts; no Apple command executes."""
import copy
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import time
import unittest
import zlib
from unittest.mock import patch

import run_mac_native_codec_control as route
from mac_host_lifecycle_pixels import require

ROOT = Path(__file__).resolve().parents[1]
UUID = '12345678-1234-1234-1234-123456789ABC'


class CodecRouteTests(unittest.TestCase):
    def test_workflow_is_one_fixed_branch_one_standard_mac_no_host_or_matrix(self):
        raw = (ROOT / route.WORKFLOW).read_text()
        self.assertIn('branches: [codex/mac-native-codec-control]', raw)
        self.assertEqual(raw.count('runs-on:'), 1)
        self.assertIn('runs-on: xcode-27', raw)
        self.assertIn('timeout-minutes: 20', raw)
        self.assertIn('timeout-minutes: 15', raw)
        self.assertIn('timeout-minutes: 3', raw)
        self.assertIn('persist-credentials: false', raw)
        self.assertIn('fetch-depth: 2', raw)
        self.assertIn('retention-days: 1', raw)
        self.assertIn('contents: read', raw)
        for forbidden in ('matrix:', 'workflow_dispatch:', 'pull_request:', 'workflow_run:',
                          'mac_photos_host_gate', 'mac-repair.yml', 'apple-platforms.yml', 'CODE_SIGNING_ALLOWED=YES'):
            self.assertNotIn(forbidden, raw)
        self.assertEqual(re.findall(r'^\s+run: (.+)$', raw, re.M), ['python3 Scripts/run_mac_native_codec_control.py'])
        for path in (ROOT / '.github/workflows').glob('*.yml'):
            if path.name != Path(route.WORKFLOW).name:
                self.assertNotIn('codex/mac-native-codec-control', path.read_text())

    def test_commands_select_exact_case_unsigned_once_and_never_host(self):
        for action in ('build-for-testing', 'test-without-building'):
            args = route.command(Path('/tmp/test-owned'), action)
            self.assertEqual(args.count('-only-testing:' + route.SELECTION), 1)
            self.assertEqual(args[args.index('-scheme') + 1], 'CelluloidMacPhotosExtension')
            self.assertEqual(args[args.index('-destination') + 1], 'platform=macOS')
            self.assertIn('CODE_SIGNING_ALLOWED=NO', args)
            self.assertIn('CODE_SIGNING_REQUIRED=NO', args)
            self.assertEqual(args[-1], action)
            self.assertFalse(any(x in ('archive', '-allowProvisioningUpdates', '-test-iterations',
                '-retry-tests-on-failure', '-run-tests-until-failure') for x in args))
            if action == 'test-without-building':
                # Xcode rejects '-test-iterations 1'. Omit repetition options:
                # default single execution, never a >1/retry workaround.
                self.assertEqual(args[args.index('-maximum-test-execution-time-allowance') + 1], '90')
        with self.assertRaises(ValueError):
            route.command(Path('/tmp/test-owned'), 'test')

    def test_complete_source_manifest_hashes_and_rejects_mutation_or_symlink(self):
        manifest = json.loads((ROOT / route.MANIFEST).read_text())
        self.assertRegex(route.source_snapshot(ROOT, manifest), '^[0-9a-f]{64}$')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'owned').write_bytes(b'owned')
            row = {'path': 'owned', 'mode': '100644', 'bytes': 5, 'sha256': hashlib.sha256(b'owned').hexdigest()}
            source = {'schema': 'Celluloid.NativeCodecSource.1', 'parent': route.BASE, 'files': [row]}
            route.source_snapshot(root, source)
            (root / 'owned').write_bytes(b'wrong')
            with self.assertRaises(ValueError): route.source_snapshot(root, source)
            (root / 'owned').unlink(); (root / 'actual').write_bytes(b'owned'); (root / 'owned').symlink_to('actual')
            with self.assertRaises(ValueError): route.source_snapshot(root, source)
            for rel in ('../owned', '/owned', route.MANIFEST):
                changed = copy.deepcopy(source); changed['files'][0]['path'] = rel
                with self.assertRaises(ValueError): route.source_snapshot(root, changed)

    def records(self, name='codec-control.json', exported='owned'):
        stem, extension = name.rsplit('.', 1)
        return [{'testIdentifier': route.CLASS + '/' + route.METHOD + '()', 'attachments': [{
            'suggestedHumanReadableName': stem + '_0_' + UUID + '.' + extension, 'exportedFileName': exported}]}]

    def test_attachment_namespace_identity_duplicate_paths_caps_and_partial_retention(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'owned').write_bytes(b'{}')
            valid = self.records()
            self.assertEqual(route.attachments(root, valid), {'codec-control.json': b'{}'})
            mutations = [lambda x: x[0].update(testIdentifier='Other/test()'),
                lambda x: x[0]['attachments'].append(copy.deepcopy(x[0]['attachments'][0])),
                lambda x: x[0]['attachments'][0].update(exportedFileName='../owned'),
                lambda x: x[0]['attachments'][0].update(suggestedHumanReadableName='codec-control_1_' + UUID + '.json')]
            for mutation in mutations:
                value = copy.deepcopy(valid); mutation(value)
                with self.assertRaises(ValueError): route.attachments(root, value)
            (root / 'owned').write_bytes(b' ' * (16 * 1024) + b'{}')
            with self.assertRaises(ValueError): route.attachments(root, valid)
            (root / 'owned').unlink(); (root / 'actual').write_bytes(b'{}'); (root / 'owned').symlink_to('actual')
            with self.assertRaises(OSError): route.attachments(root, valid)
            (root / 'owned').unlink(); os.link(root / 'actual', root / 'owned')
            with self.assertRaises(ValueError): route.attachments(root, valid)

    def test_attachment_aggregate_remains_512_kib_and_does_not_accept_unknown_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); records = []
            for index, name in enumerate(n for n in route.CAPS if n != 'codec-control.json'):
                data = b'\xff\xd8\xff' + b'x' * (128 * 1024 - 5) + b'\xff\xd9' if name.endswith('.jpg') else b'\x89PNG\r\n\x1a\n' + b'x' * (128 * 1024 - 8)
                (root / str(index)).write_bytes(data); records += self.records(name, str(index))
            with self.assertRaises(ValueError): route.attachments(root, records)
            unknown = self.records('codec-actual.json', '0')
            with self.assertRaises(ValueError): route.attachments(root, unknown)

    def summary(self):
        return {'result': 'Passed', 'totalTestCount': 1, 'passedTests': 1, 'failedTests': 0,
            'skippedTests': 0, 'expectedFailures': 0, 'testFailures': [], 'startTime': 1001.0, 'finishTime': 1009.0,
            'devicesAndConfigurations': [{'passedTests': 1, 'failedTests': 0, 'skippedTests': 0,
                'expectedFailures': 0, 'device': {'platform': 'macOS', 'osVersion': '27.0', 'architecture': 'arm64'}}]}

    def transcript(self):
        return (f"Test Case '{route.RAW_CASE}' started.\nTest Case '{route.RAW_CASE}' passed (1.0 seconds).\n"
            'Executed 1 test, with 0 failures (0 unexpected) in 1.0 (1.0) seconds\n'
            'Test session results, code coverage, and logs:\n/tmp/CelluloidNativeCodecControl.xcresult\n\n** TEST EXECUTE SUCCEEDED **\n')

    def failed_case(self):
        summary = self.summary()
        summary.update(result='Failed', passedTests=0, failedTests=1, testFailures=[{
            'targetName': route.TARGET, 'testIdentifierString': route.CLASS + '/' + route.METHOD + '()',
            'testName': route.METHOD + '()', 'failureText': 'XCTAssertLessThanOrEqual failed: 3 > 2'}])
        summary['devicesAndConfigurations'][0].update(passedTests=0, failedTests=1)
        log = (f"Test Case '{route.RAW_CASE}' started.\n"
            f"/tmp/Control.swift:80: error: {route.RAW_CASE} : XCTAssertLessThanOrEqual failed: 3 > 2\n"
            f"Test Case '{route.RAW_CASE}' failed (1.0 seconds).\n"
            'Executed 1 test, with 1 failure (0 unexpected) in 1.0 (1.0) seconds\n'
            f'Failing tests:\n{route.CLASS}.{route.METHOD}()\n'
            'Test session results, code coverage, and logs:\n/tmp/CelluloidNativeCodecControl.xcresult\n\n** TEST EXECUTE FAILED **\n')
        return log, summary

    def native_event(self, return_code=0):
        return {'stage': 'single-native-case', 'returned_without_timeout': True, 'limit_seconds': 120,
            'return_code': return_code, 'started_unix': 1000.0, 'finished_unix': 1010.0, 'elapsed_seconds': 10.0,
            'run_id': '123', 'run_attempt': 1}

    def test_preexport_admission_binds_original_case_command_interval_run_and_first_attempt(self):
        bundle = '/tmp/CelluloidNativeCodecControl.xcresult'; source = {'run_id': '123', 'run_attempt': 1}
        route.admit_export(self.transcript(), self.summary(), self.native_event(), bundle, source)
        log, summary = self.failed_case()
        self.assertFalse(route.admit_export(log, summary, self.native_event(65), bundle, source)['native_passed'])
        for mutation in ({'return_code': None}, {'return_code': -9}, {'return_code': 1},
                         {'returned_without_timeout': False}, {'elapsed_seconds': 121.0},
                         {'run_id': '124'}, {'run_attempt': 2}, {'started_unix': 1002.0}, {'finished_unix': 1008.0}):
            event = self.native_event(); event.update(mutation)
            with self.assertRaises(ValueError): route.admit_export(self.transcript(), self.summary(), event, bundle, source)
        for mutation in ({'startTime': 999.0}, {'finishTime': 1011.0}, {'startTime': float('nan')}, {'finishTime': 1000.0}):
            changed = self.summary(); changed.update(mutation)
            with self.assertRaises(ValueError): route.admit_export(self.transcript(), changed, self.native_event(), bundle, source)
        with self.assertRaises(ValueError): route.admit_export(self.transcript(), self.summary(), self.native_event(), '/tmp/other.xcresult', source)

    def test_native_result_fails_closed_for_wrong_zero_duplicate_skipped_or_missing_artifacts(self):
        for changed in ({}, {'totalTestCount': 0}, {'totalTestCount': 2}, {'skippedTests': 1},
                        {'devicesAndConfigurations': []}, {'expectedFailures': 1}, {'result': 'Unknown'}):
            summary = self.summary(); summary.update(changed)
            with self.assertRaises(ValueError): route.inspect_result(self.transcript(), summary, {}, 0)
        for log in (self.transcript().replace(route.METHOD, 'testOther'), self.transcript() * 2):
            with self.assertRaises(ValueError): route.inspect_result(log, self.summary(), {}, 0)
        with self.assertRaises(ValueError): route.inspect_result(self.transcript(), self.summary(), {}, 65)

    def result_fixture(self, delta=0):
        # Generated structural data, never substituted for native evidence.
        def chunk(name, raw):
            return struct.pack('>I', len(raw)) + name + raw + struct.pack('>I', zlib.crc32(name + raw) & 0xffffffff)
        header = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1200, 800, 8, 2, 0, 0, 0)) + chunk(b'sRGB', b'\0')
        png = header + chunk(b'IDAT', zlib.compress((b'\0' + b'\xff' * 3600) * 800)) + chunk(b'IEND', b'')
        actual_png = header + chunk(b'IDAT', zlib.compress(b'\0\xff\xff' + bytes([255 - delta]) + b'\xff' * 3597
            + (b'\0' + b'\xff' * 3600) * 799)) + chunk(b'IEND', b'')
        image = route.decode(png)
        actual = route.decode(actual_png)
        source = route.decode((ROOT / route.SOURCE).read_bytes())
        retained = {name: b'\xff\xd8\xff\xd9' if name.endswith('.jpg') else png for name in route.CAPS if name != 'codec-control.json'}
        retained['codec-actual-decoded.png'] = actual_png
        metadata = {'rgba_sha256': image['rgba_sha256'], 'sha256': image['png_sha256']}
        report = {'schema': 'Celluloid.NativeCodecControl.1', 'scope': 'synthetic-pre-host-only',
            'public_parent': route.BASE, 'source_sha256': route.SOURCE_SHA, 'allowed_max_channel_delta': 2,
            'sequence': ['Original preview', 'Fade preview', 'Fade export'],
            'photos_input_observed': False, 'photos_submitted_jpeg_observed': False, 'actual_export_prejpeg_observed': False,
            'artifacts': {name: {'bytes': len(raw), 'sha256': route.sha(raw)} for name, raw in retained.items()},
            'actual_jpeg_sha256': route.sha(retained['codec-actual.jpg']),
            'reference_jpeg_sha256': route.sha(retained['codec-reference.jpg']),
            'actual': {'rgba_sha256': actual['rgba_sha256'], 'sha256': actual['png_sha256']}, 'reference': metadata,
            'source': {'sha256': route.SOURCE_SHA, 'rgba_sha256': source['rgba_sha256']},
            'max_channel_delta': delta, 'changed_pixels': int(delta > 0), 'pixel_contract_passed': delta <= 2,
            'pixels_above_two': int(delta > 2), 'channels_above_two_rgba': [0, 0, int(delta > 2), 0],
            'rgb_rmse': (delta * delta / (1200 * 800 * 3)) ** 0.5}
        retained['codec-control.json'] = json.dumps(report).encode()
        return retained

    def test_independent_replay_passes_consistent_structure_rejects_hash_metric_and_scope_lies(self):
        retained = self.result_fixture()
        report = route.inspect_result(self.transcript(), self.summary(), retained, 0)
        self.assertTrue(report['native_passed'])
        self.assertTrue(report['pixel_contract_passed'])
        for mutation in ({'max_channel_delta': 3}, {'allowed_max_channel_delta': 3}, {'photos_input_observed': True},
                         {'actual_jpeg_sha256': '0' * 64}, {'source_sha256': '0' * 64}, {'changed_pixels': 1},
                         {'pixels_above_two': 1}, {'rgb_rmse': 1}):
            changed = dict(retained); metrics = json.loads(changed['codec-control.json']); metrics.update(mutation)
            changed['codec-control.json'] = json.dumps(metrics).encode()
            with self.assertRaises(ValueError): route.inspect_result(self.transcript(), self.summary(), changed, 0)

    def test_source_gate_rejects_off_runner_without_any_native_process(self):
        with patch.object(route.sys, 'platform', 'linux'), patch.object(route, 'git') as git:
            with self.assertRaises(ValueError): route.admit_source()
            git.assert_not_called()
        for mutation in ({'GITHUB_RUN_ID': ''}, {'GITHUB_RUN_ID': '0'}, {'GITHUB_RUN_ATTEMPT': '2'}):
            env = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': '100mango/Celluloid',
                'GITHUB_REF': route.BRANCH, 'GITHUB_EVENT_NAME': 'push', 'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1'}
            env.update(mutation)
            with patch.object(route.sys, 'platform', 'darwin'), patch.dict(os.environ, env), patch.object(route, 'git') as git:
                with self.assertRaises(ValueError): route.admit_source()
                git.assert_not_called()

    def test_build_failure_or_native_timeout_never_starts_later_native_or_export_work(self):
        for failure in ('build', 'native-timeout'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve(); (root / 'Scripts').mkdir()
                (root / route.MANIFEST).write_bytes(b'{}')
                before = {'source_fingerprint': 'pinned', 'source_manifest_sha256': route.sha(b'{}'), 'run_id': '123', 'run_attempt': 1}
                calls = []
                def fake_run(args, **kwargs):
                    calls.append(args)
                    if args == ['xcodebuild', '-version']:
                        return subprocess.CompletedProcess(args, 0, 'Xcode 27.0\nBuild version test\n', '')
                    if args[-1] == 'build-for-testing' and failure == 'build':
                        return subprocess.CompletedProcess(args, 65, 'controlled build failure', '')
                    if args[-1] == 'test-without-building':
                        (root / 'codec-single-native-case.log').write_text('controlled partial native output')
                        raise TimeoutError('controlled native timeout')
                    return subprocess.CompletedProcess(args, 0, '', '')
                old_cwd = Path.cwd()
                try:
                    os.chdir(root)
                    with patch.dict(os.environ, {'RUNNER_TEMP': str(root), 'GITHUB_SHA': 'a' * 40}), \
                            patch.object(route, 'ROOT', root), patch.object(route, 'admit_source', return_value=({}, before)), \
                            patch.object(route, 'source_snapshot', return_value='pinned'), patch.object(route, 'run', side_effect=fake_run):
                        self.assertEqual(route.main(), 1)
                finally:
                    os.chdir(old_cwd)
                self.assertFalse(any(args[0] == 'xcrun' for args in calls))
                if failure == 'build':
                    self.assertFalse(any(args[-1] == 'test-without-building' for args in calls))
                evidence = root / 'celluloid-codec-evidence'
                receipt = json.loads((evidence / 'run.json').read_text())
                self.assertFalse(receipt['passed'])
                self.assertFalse(receipt['photos_host_executed'])
                self.assertEqual(receipt['stage'], 'build-only' if failure == 'build' else 'single-native-case')
                self.assertTrue((evidence / 'manifest.json').is_file())
                if failure == 'native-timeout':
                    self.assertTrue(receipt['cleanup_unconfirmed'])
                    self.assertEqual((evidence / 'single-native-case.partial-tail.txt').read_text(), 'controlled partial native output')

    def test_unknown_zero_case_stale_summary_never_exports_but_valid_failed_case_retains_six_artifacts(self):
        retained = self.result_fixture(delta=3)
        for failure in ('no-terminal', 'zero-case-summary', 'stale-summary', 'valid-pixel-failure'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve(); (root / 'Scripts').mkdir(); (root / route.MANIFEST).write_bytes(b'{}')
                (root / route.SOURCE).parent.mkdir(parents=True)
                (root / route.SOURCE).write_bytes((ROOT / route.SOURCE).read_bytes())
                before = {'source_fingerprint': 'pinned', 'source_manifest_sha256': route.sha(b'{}'), 'run_id': '123', 'run_attempt': 1}
                log, summary = self.failed_case(); log = log.replace('/tmp/CelluloidNativeCodecControl.xcresult', str(root / 'CelluloidNativeCodecControl.xcresult'))
                calls = []
                def fake_run(args, **kwargs):
                    calls.append(args)
                    if args == ['xcodebuild', '-version']:
                        return subprocess.CompletedProcess(args, 0, 'Xcode 27.0\nBuild version test\n', '')
                    if args[-1] == 'test-without-building':
                        summary['startTime'] = time.time(); time.sleep(0.001); summary['finishTime'] = time.time()
                        return subprocess.CompletedProcess(args, 65, 'incomplete native output' if failure == 'no-terminal' else log, '')
                    if args[:5] == ['xcrun', 'xcresulttool', 'get', 'test-results', 'summary']:
                        if failure == 'zero-case-summary': summary.update(totalTestCount=0, passedTests=0, failedTests=0)
                        if failure == 'stale-summary': summary.update(startTime=1000.0, finishTime=1001.0)
                        return subprocess.CompletedProcess(args, 0, json.dumps(summary), '')
                    if args[:4] == ['xcrun', 'xcresulttool', 'export', 'attachments']:
                        folder = Path(args[-1]); folder.mkdir(); records = []
                        for index, (name, raw) in enumerate(retained.items()):
                            filename = str(index); (folder / filename).write_bytes(raw); records += self.records(name, filename)
                        (folder / 'manifest.json').write_text(json.dumps(records))
                    return subprocess.CompletedProcess(args, 0, '', '')
                old_cwd = Path.cwd()
                try:
                    os.chdir(root)
                    with patch.dict(os.environ, {'RUNNER_TEMP': str(root), 'GITHUB_SHA': 'a' * 40}), \
                            patch.object(route, 'ROOT', root), patch.object(route, 'admit_source', return_value=({}, before)), \
                            patch.object(route, 'source_snapshot', return_value='pinned'), patch.object(route, 'run', side_effect=fake_run):
                        self.assertEqual(route.main(), 1)
                finally: os.chdir(old_cwd)
                exports = [args for args in calls if args[:4] == ['xcrun', 'xcresulttool', 'export', 'attachments']]
                self.assertEqual(len(exports), int(failure == 'valid-pixel-failure'))
                if failure == 'no-terminal': self.assertFalse(any(args[0] == 'xcrun' for args in calls))
                evidence = root / 'celluloid-codec-evidence'; receipt = json.loads((evidence / 'run.json').read_text())
                self.assertFalse(receipt['passed'])
                self.assertEqual((receipt['run_id'], receipt['run_attempt']), ('123', 1))
                self.assertEqual(receipt['stage'], {'no-terminal': 'native-completion-admission',
                    'zero-case-summary': 'pre-export-admission', 'stale-summary': 'pre-export-admission',
                    'valid-pixel-failure': 'independent-replay'}[failure])
                if failure == 'valid-pixel-failure':
                    self.assertTrue(all((evidence / name).is_file() for name in route.CAPS))
                    self.assertFalse(receipt['result']['pixel_contract_passed'])
                    self.assertFalse(receipt['result']['native_passed'])

    def test_fault_fixtures_canonicalize_ancestor_symlink_aliases(self):
        # macOS TMPDIR can contain an ancestor alias (for example /var), while
        # the leaf itself is a regular directory. Keep the real driver strict;
        # canonicalize only the two mocked ROOT fixtures before invoking it.
        original = tempfile.TemporaryDirectory
        @contextlib.contextmanager
        def aliased_temporary_directory(*args, **kwargs):
            with original(*args, **kwargs) as directory:
                root = Path(directory).resolve(); actual = root / 'actual'; actual.mkdir()
                alias = root / 'alias'; alias.symlink_to(actual, target_is_directory=True)
                (actual / 'case').mkdir(); leaf = alias / 'case'
                self.assertFalse(leaf.is_symlink())
                self.assertNotEqual(leaf, leaf.resolve())
                yield str(leaf)
        with patch.object(tempfile, 'TemporaryDirectory', aliased_temporary_directory):
            self.test_build_failure_or_native_timeout_never_starts_later_native_or_export_work()
            self.test_unknown_zero_case_stale_summary_never_exports_but_valid_failed_case_retains_six_artifacts()

    def test_no_assert_guards_disappear_under_optimized_python(self):
        import ast
        tree = ast.parse((ROOT / 'Scripts/run_mac_native_codec_control.py').read_text())
        self.assertFalse(any(isinstance(node, ast.Assert) for node in ast.walk(tree)))
        self.assertEqual(route.ATTACHMENT_CAP, 512 * 1024)
        self.assertEqual(route.EVIDENCE_CAP, 1024 * 1024)
        with self.assertRaises(ValueError): require(False, 'still rejects under -O')


if __name__ == '__main__':
    unittest.main()
