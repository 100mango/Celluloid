#!/usr/bin/env python3
"""Portable full-shipping handoff adversaries; no Apple/runtime acceptance."""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import zlib
from unittest.mock import patch

import native_fixture_handoff as fixture_handoff
import platform_rendering_contract as contract
import uikit_full_shipping_gate as accounting
import uikit_full_shipping_handoff as handoff
import test_platform_rendering_contract as rendering_fixtures
import test_uikit_installed_identity as installed_fixtures
import test_uikit_full_shipping_gate as execution_fixtures
from verify_required_interoperability import required, source_cases, verify


SOURCE = 'a' * 40
TREE = 'b' * 40


def environment():
    route = handoff.UIKIT_FULL
    ref = 'refs/heads/' + route['branch']
    return {'GITHUB_REPOSITORY': '100mango/Celluloid', 'GITHUB_EVENT_NAME': 'push',
            'GITHUB_SHA': SOURCE, 'GITHUB_WORKFLOW_SHA': SOURCE, 'GITHUB_REF': ref,
            'GITHUB_WORKFLOW_REF': '100mango/Celluloid/' + route['workflow_path'] + '@' + ref,
            'CELLULOID_VALIDATION_SCOPE': route['scope'], 'GITHUB_RUN_ID': '1234567',
            'GITHUB_RUN_ATTEMPT': '1', 'CELLULOID_FULL_ROW': 'compact-phone',
            'DEVICE_NAME': accounting.ROWS['compact-phone']}


def put_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True) + '\n')


def run_collector(folder):
    """Run the real collector with native exporters forbidden by the harness."""
    driver = '''
import runpy, sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(sys.argv[1]).parent))
# Match the synthetic row clock; the parent subprocess timeout remains real.
with patch('time.monotonic', return_value=100_300.125), patch('subprocess.run', side_effect=AssertionError('Collector unexpectedly dispatched a native exporter')):
    runpy.run_path(sys.argv[1], run_name='__main__')
'''
    env = dict(environment(), RUNNER_TEMP=str(folder), CELLULOID_EVIDENCE_PLATFORM='compact-phone',
               PYTHONDONTWRITEBYTECODE='1')
    return subprocess.run([sys.executable, '-c', driver, str(accounting.ROOT / 'Scripts/collect_native_evidence.py')],
                          env=env, capture_output=True, text=True, timeout=20)


class HandoffFixtures(unittest.TestCase):
    def setUp(self):
        # Synthetic runs must not inherit an enclosing real CI identity.
        self.env = patch.dict(os.environ, environment(), clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        # These fixtures mock every native command. Keep their replay clock
        # independent of VM uptime; real process-timeout tests live elsewhere.
        observation = patch.object(accounting.time, 'monotonic', return_value=100_300.125)
        observation.start()
        self.addCleanup(observation.stop)
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.temp = Path(self.folder.name)
        self.artifact = self.temp / 'mac-fixture-evidence'
        self.artifact.mkdir()
        self.synthetic = rendering_fixtures.PlatformContractTests()
        self.make_producer_inputs()
        self.summary = {'result': 'Passed', 'totalTestCount': 67, 'passedTests': 67, 'failedTests': 0,
                        'skippedTests': 0, 'expectedFailures': 0, 'testFailures': [],
                        'startTime': 100_000.0, 'finishTime': 100_100.0}
        def native_summary(args, **kwargs):
            self.assertEqual(list(map(str, args)), ['xcrun', 'xcresulttool', 'get', 'test-results', 'summary',
                                                  '--path', str(self.temp / 'CelluloidMac.xcresult')])
            self.assertEqual(kwargs['timeout'], 30)
            return subprocess.CompletedProcess(args, 0, json.dumps(self.summary), '')
        self.native = patch('native_process.run', side_effect=native_summary)
        self.native.start()
        self.addCleanup(self.native.stop)

    def make_producer_inputs(self):
        put_json(self.temp / 'combined-source-before.json', {
            'source_sha': SOURCE, 'file_count': 547, 'source_fingerprint': handoff.UIKIT_FULL_BASE['fingerprint'],
            'validation_route': handoff.UIKIT_FULL, 'phase': 'before', 'tree': TREE})
        after = handoff.read(self.temp / 'combined-source-before.json')
        after['phase'] = 'after'
        put_json(self.temp / 'combined-source-after.json', after)
        (self.temp / 'full-shipping-xcode.txt').write_text('Xcode 27.0\nBuild version synthetic-portable-test\n')
        native = self.synthetic.native()
        log = []
        cases = dict(required('mac'))
        cases['CelluloidMacTests'] = source_cases(sorted((handoff.ROOT / 'Platforms/Tests').glob('*.swift')))
        self.assertEqual(sum(map(len, cases.values())), 67)
        for module, methods in cases.items():
            for case in methods:
                owner, method = case.split('.')
                name = '-[' + module + '.' + owner + ' ' + method + ']'
                log.append("Test Case '" + name + "' started.")
                if case == contract.native_spec()['required_test']:
                    log.append(contract.NATIVE_PREFIX + json.dumps(native))
                log.append("Test Case '" + name + "' passed (0.1 seconds).")
        self.assertEqual(len(required('mac')['CelluloidMacPhotosExtensionTests']), 42)
        payload = b'synthetic filter archive bytes, not an Apple runtime fixture'
        encoded = base64.b64encode(payload).decode()
        digest = hashlib.sha256(payload).hexdigest()
        for name in sorted(fixture_handoff.FILTERS):
            log.append(f'MAC_FILTER_ONLY_FIXTURE filter={name} sha256={digest} base64={encoded}')
        log.append('MAC_BAKED_BASE_FIXTURE ' + json.dumps({'identifier': 'Mango.CelluloidPhotoExtension',
            'version': '2.0-baked-base', 'sha256': digest, 'base64': encoded}))
        log.append('MAC_LAYER_ADJUSTMENT_FIXTURE ' + json.dumps(self.synthetic.fixture()))
        log.extend(['Executed 67 tests, with 0 failures (0 unexpected)', '** TEST SUCCEEDED **',
                    'BOUNDED_COMMAND_END ' + json.dumps({'label': 'same-job-Mac-producer', 'exit_code': 0})])
        (self.temp / 'mac.log').write_text('\n'.join(log) + '\n')
        self.refresh_native_report()

    def refresh_native_report(self):
        report = verify('mac', self.temp / 'mac.log', None, SOURCE, platform_contract=True)
        put_json(self.temp / 'mac-required-tests.json', report)
        return report

    def package(self):
        handoff.producer(self.temp)
        for name in ('full-shipping-producer.json', 'mac-required-tests.json', 'combined-source-before.json',
                     'combined-source-after.json', 'full-shipping-mac-summary.json', 'full-shipping-mac-accounting.json'):
            shutil.copyfile(self.temp / name, self.artifact / name)
        (self.artifact / 'mac-layer-fixture.json').write_bytes(fixture_handoff.layer_from_log(self.temp / 'mac.log', SOURCE))
        (self.artifact / 'mac-filter-fixtures.json').write_bytes(fixture_handoff.from_log(self.temp / 'mac.log', SOURCE))
        put_json(self.artifact / 'manifest.json', {'source_sha': SOURCE, 'run_id': '1234567', 'platform': 'mac',
            'limits': {'total_bytes': 2_000_000}, 'files': []})
        self.rehash()

    def rehash(self, required_report=False):
        if required_report:
            producer = handoff.read(self.artifact / 'full-shipping-producer.json')
            producer['native_required_sha256'] = handoff.sha(self.artifact / 'mac-required-tests.json')
            put_json(self.artifact / 'full-shipping-producer.json', producer)
        manifest = handoff.read(self.artifact / 'manifest.json')
        manifest['files'] = [{'name': path.name, 'bytes': path.stat().st_size, 'sha256': handoff.sha(path)}
                             for path in sorted(self.artifact.iterdir()) if path.name != 'manifest.json' and path.is_file()]
        put_json(self.artifact / 'manifest.json', manifest)

    def transfer(self, **kwargs):
        return handoff.transfer(self.temp, kwargs.get('artifact_id', '987654'),
                                kwargs.get('manifest_hash', handoff.sha(self.artifact / 'manifest.json')),
                                kwargs.get('reported_artifact_digest', 'c' * 64))

    def change_member(self, name, change, rehash_report=False):
        value = handoff.read(self.artifact / name)
        change(value)
        put_json(self.artifact / name, value)
        self.rehash(required_report=rehash_report)


class ProducerTests(HandoffFixtures):
    def test_fresh_native_42_producer_binds_replayed_proof_and_toolchain(self):
        handoff.producer(self.temp)
        proof = handoff.read(self.temp / 'full-shipping-producer.json')
        self.assertEqual(proof['required_mac_cases'], 42)
        self.assertEqual(proof['source_sha'], SOURCE)
        self.assertEqual(proof['run_id'], '1234567')
        self.assertEqual(proof['run_attempt'], '1')
        self.assertEqual(proof['native_required_sha256'], handoff.sha(self.temp / 'mac-required-tests.json'))
        self.assertEqual(proof['xcode_sha256'], handoff.sha(self.temp / 'full-shipping-xcode.txt'))

    def test_failed_duplicate_missing_or_changed_producer_command_end_rejects(self):
        original = (self.temp / 'mac.log').read_text()
        suffix = original.splitlines()[-1]
        for changed in (original.replace('"exit_code": 0', '"exit_code": 65'), original + suffix + '\n',
                        original.replace(suffix, ''), original.replace('same-job-Mac-producer', 'different-command')):
            (self.temp / 'mac.log').write_text(changed)
            self.refresh_native_report()
            with self.subTest(suffix=changed[-120:]), self.assertRaises(ValueError):
                handoff.producer(self.temp)

    def test_missing_failed_skipped_or_duplicate_required_native_case_rejects(self):
        original = (self.temp / 'mac.log').read_text()
        line = next(line for line in original.splitlines() if "' passed (0.1 seconds)." in line)
        for changed in (original.replace(line, ''), original.replace(line, line.replace('passed', 'failed')),
                        original.replace(line, line.replace('passed', 'skipped')), original + line + '\n'):
            (self.temp / 'mac.log').write_text(changed)
            self.refresh_native_report()
            with self.subTest(change=changed[-100:]), self.assertRaises(ValueError):
                handoff.producer(self.temp)

    def test_source_and_saved_required_report_must_match_same_execution(self):
        for field, value in (('source_sha', 'd' * 40), ('file_count', 546),
                             ('source_fingerprint', 'd' * 64), ('phase', 'after')):
            original = handoff.read(self.temp / 'combined-source-before.json')
            changed = copy.deepcopy(original)
            changed[field] = value
            put_json(self.temp / 'combined-source-before.json', changed)
            with self.subTest(field=field), self.assertRaises(ValueError):
                handoff.producer(self.temp)
            put_json(self.temp / 'combined-source-before.json', original)
        report = handoff.read(self.temp / 'mac-required-tests.json')
        report['expected_count'] = 41
        put_json(self.temp / 'mac-required-tests.json', report)
        with self.assertRaises(ValueError): handoff.producer(self.temp)

    def test_wrong_route_source_workflow_run_or_attempt_identity_rejects(self):
        for key, value in (('GITHUB_REF', 'refs/heads/apple-platforms'), ('GITHUB_WORKFLOW_SHA', 'd' * 40),
                           ('GITHUB_EVENT_NAME', 'workflow_dispatch'), ('GITHUB_RUN_ID', '0'), ('GITHUB_RUN_ATTEMPT', '01')):
            with self.subTest(key=key), patch.dict(os.environ, {key: value}), self.assertRaises(ValueError):
                handoff.identity()

    def test_replayed_receipt_cannot_be_overwritten(self):
        handoff.producer(self.temp)
        with self.assertRaisesRegex(ValueError, 'Duplicate proof'):
            handoff.producer(self.temp)

    def test_mac_test_terminal_normalization_is_exact_and_never_masks_failure(self):
        original = (self.temp / 'mac.log').read_text()
        for terminal in ('** TEST FAILED **', '** TEST EXECUTE SUCCEEDED **', '** TEST SUCCEEDED **\n** TEST SUCCEEDED **'):
            (self.temp / 'mac.log').write_text(original.replace('** TEST SUCCEEDED **', terminal))
            self.refresh_native_report()
            with self.subTest(terminal=terminal), self.assertRaises(ValueError):
                handoff.producer(self.temp)

    def test_native_summary_must_account_for_every_enclosing_case(self):
        for changes in ({'totalTestCount': 66}, {'passedTests': 66}, {'result': 'Failed'}, {'skippedTests': 1},
                        {'failedTests': 1}, {'expectedFailures': 1}, {'failedTests': False},
                        {'skippedTests': False}, {'expectedFailures': False}, {'totalTestCount': 67.0}):
            original = copy.deepcopy(self.summary)
            self.summary.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError): handoff.producer(self.temp)
            self.summary = original


class TransferTests(HandoffFixtures):
    def setUp(self):
        super().setUp()
        self.package()

    def test_exact_manifest_all_members_native_oracle_and_graph_pass(self):
        self.transfer()
        row = handoff.read(self.temp / 'full-shipping-transfer.json')
        self.assertEqual(row['artifact_manifest_sha256'], handoff.sha(self.artifact / 'manifest.json'))
        self.assertEqual(row['layer_archive_sha256'], self.synthetic.fixture()['sha256'])
        self.assertTrue(row['manifest_and_all_members_verified'])
        self.assertFalse(row['queue_expiry_applied'])
        self.assertEqual(row['run_attempt'], '1')

    def test_long_queue_delay_does_not_expire_same_run_fixture(self):
        old = time.time() - 3 * 24 * 60 * 60
        for path in self.artifact.iterdir(): os.utime(path, (old, old))
        self.transfer()
        self.assertFalse(handoff.read(self.temp / 'full-shipping-transfer.json')['queue_expiry_applied'])

    def test_wrong_artifact_hash_id_and_reported_digest_reject(self):
        for changes in ({'artifact_id': '0'}, {'artifact_id': '../987654'}, {'manifest_hash': 'd' * 64},
                        {'manifest_hash': 'bad'}, {'reported_artifact_digest': 'unknown'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.transfer(**changes)

    def test_wrong_source_run_attempt_or_tree_reject_after_rehash(self):
        for member, field, changed in (('full-shipping-producer.json', 'source_sha', 'd' * 40),
                                      ('full-shipping-producer.json', 'run_id', '2'),
                                      ('full-shipping-producer.json', 'run_attempt', '2'),
                                      ('full-shipping-producer.json', 'tree', 'd' * 40),
                                      ('full-shipping-producer.json', 'protected_fingerprint', 'd' * 64),
                                      ('full-shipping-producer.json', 'required_mac_cases', 41)):
            path = self.artifact / member
            original = path.read_bytes()
            self.change_member(member, lambda row: row.update({field: changed}))
            with self.subTest(field=field), self.assertRaises(ValueError): self.transfer()
            path.write_bytes(original)
            self.rehash()
        for field, changed in (('source_sha', 'd' * 40), ('run_id', '2'), ('platform', 'small-ipad')):
            path = self.artifact / 'manifest.json'
            original = path.read_bytes()
            value = handoff.read(path)
            value[field] = changed
            put_json(path, value)
            with self.subTest(manifest_field=field), self.assertRaises(ValueError): self.transfer()
            path.write_bytes(original)

    def test_changed_member_bytes_or_native_report_receipt_hash_rejects(self):
        path = self.artifact / 'mac-required-tests.json'
        original = path.read_bytes()
        path.write_bytes(original + b' ')
        with self.assertRaisesRegex(ValueError, 'Changed artifact member'): self.transfer()
        self.rehash()
        with self.assertRaisesRegex(ValueError, 'Unbound native producer'): self.transfer()

    def test_changed_toolchain_rejects(self):
        (self.temp / 'full-shipping-xcode.txt').write_text('Xcode 27.0\nBuild version different\n')
        with self.assertRaisesRegex(ValueError, 'toolchains differ'): self.transfer()

    def test_arbitrary_listed_member_is_rejected_even_when_hash_bound(self):
        (self.artifact / 'unreviewed-data.txt').write_text('not an admitted producer diagnostic')
        self.rehash()
        with self.assertRaises(ValueError): self.transfer()

    def test_native_checks_scope_failure_inventory_and_fixture_counts_are_exact(self):
        path = self.artifact / 'mac-required-tests.json'
        original = path.read_bytes()
        mutations = [lambda value: value.update(checks={}),
                     lambda value: value['checks'].pop('independent_native_text_contract'),
                     lambda value: value['checks'].update(unreviewed_extra=True),
                     lambda value: value['checks'].update(independent_native_text_contract=1),
                     lambda value: value.update(scope='uikit'),
                     lambda value: value.update(missing_failed_skipped_or_duplicate={'other': ['failed']}),
                     lambda value: value.update(filter_fixture_count=9),
                     lambda value: value.update(manufactured_layer_fixture_count=0),
                     lambda value: value.update(baked_fallback_fixture_count=0)]
        for mutation in mutations:
            value = json.loads(original)
            mutation(value)
            put_json(path, value)
            self.rehash(required_report=True)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): self.transfer()
            proof = self.temp / 'full-shipping-transfer.json'
            if proof.exists(): proof.unlink()
        path.write_bytes(original)

    def test_missing_extra_unlisted_symlink_directory_and_unsafe_members_reject(self):
        target = self.artifact / 'mac-filter-fixtures.json'
        original = target.read_bytes()
        target.unlink()
        with self.assertRaises(ValueError): self.transfer()
        target.write_bytes(original)
        extra = self.artifact / 'unlisted.txt'
        extra.write_text('unexpected')
        with self.assertRaises(ValueError): self.transfer()
        extra.unlink()
        extra.mkdir()
        with self.assertRaises(ValueError): self.transfer()
        extra.rmdir()
        outside = self.temp / 'outside.json'
        outside.write_bytes(original)
        target.unlink()
        target.symlink_to(outside)
        with self.assertRaises(ValueError): self.transfer()
        target.unlink()
        target.write_bytes(original)
        path = self.artifact / 'manifest.json'
        original_manifest = path.read_bytes()
        for name in ('../outside.json', '/tmp/outside.json', '', '.', '..', 'manifest.json'):
            value = json.loads(original_manifest)
            value['files'][0]['name'] = name
            put_json(path, value)
            with self.subTest(name=name), self.assertRaises(ValueError): self.transfer()
        path.write_bytes(original_manifest)
        value = handoff.read(path)
        value['files'].append(copy.deepcopy(value['files'][0]))
        put_json(path, value)
        with self.assertRaises(ValueError): self.transfer()

    def test_report_native42_results_must_be_exact_even_after_rehash(self):
        path = self.artifact / 'mac-required-tests.json'
        original = path.read_bytes()
        for mutation in ('missing', 'duplicate', 'failed', 'skipped', 'unexpected', 'count'):
            value = json.loads(original)
            first = next(iter(value['results']))
            if mutation == 'missing': del value['results'][first]
            elif mutation == 'duplicate': value['results'][first].append('passed')
            elif mutation in ('failed', 'skipped'): value['results'][first] = [mutation]
            elif mutation == 'unexpected': value['results']['Unexpected/testCase'] = ['passed']
            else: value['expected_count'] = 41
            put_json(path, value)
            self.rehash(required_report=True)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): self.transfer()
        path.write_bytes(original)

    def test_native_oracle_and_archive_graph_are_replayed_after_all_hashes_change(self):
        path = self.artifact / 'mac-required-tests.json'
        original = path.read_bytes()
        mutations = [lambda value: value['native_text_contract'].update(maximumChannelDifference=3),
                     lambda value: value['native_text_contract'].update(sourcePNG_SHA256='d' * 64),
                     lambda value: value['archive_graph_proof'].update(canonical_graph_sha256='d' * 64)]
        for mutation in mutations:
            value = json.loads(original)
            mutation(value)
            put_json(path, value)
            self.rehash(required_report=True)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): self.transfer()
        path.write_bytes(original)

    def test_changed_archive_graph_cannot_be_authorized_by_rehashing_transport(self):
        path = self.artifact / 'mac-layer-fixture.json'
        payload = handoff.read(path)
        archive = plistlib.loads(base64.b64decode(payload['fixture']['base64']))
        transform = next(row for row in archive['$objects'] if isinstance(row, dict) and 'NS.atval.tx' in row)
        transform['NS.atval.tx'] = 123.0
        raw = plistlib.dumps(archive, fmt=plistlib.FMT_BINARY)
        payload['fixture'].update(base64=base64.b64encode(raw).decode(), sha256=hashlib.sha256(raw).hexdigest())
        put_json(path, payload)
        self.rehash()
        with self.assertRaisesRegex(ValueError, 'semantic graph'): self.transfer()


class ProductBindingTests(HandoffFixtures):
    def make_product(self):
        app, staging = installed_fixtures.InstalledIdentityTests().fixture(self.temp)
        staging['source_sha'] = SOURCE
        staging['layer_archive_sha256'] = self.synthetic.fixture()['sha256']
        put_json(self.temp / 'uikit-layer-staging.json', staging)
        put_json(self.temp / 'full-shipping-device.json', {'schema': 'Celluloid.FullShippingDevice.1',
            **handoff.identity(), 'row': 'compact-phone',
            'device': {'id': installed_fixtures.InstalledIdentityTests.UDID, 'model': accounting.ROWS['compact-phone']}})
        put_json(self.temp / 'full-shipping-transfer.json', {'schema': 'Celluloid.FullShippingTransfer.1',
            **handoff.identity(), 'layer_archive_sha256': staging['layer_archive_sha256']})
        built = self.temp / '.build/Build/Products/Debug-iphonesimulator/Celluloid.app/Celluloid'
        built.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(app / 'Celluloid', built)
        value = {'schema': accounting.CLOCK_SCHEMA, **handoff.identity(), 'row': 'compact-phone',
                 'started_monotonic': time.monotonic(), 'started_unix': time.time(),
                 'execution_budget_seconds': accounting.EXECUTION_SECONDS}
        put_json(self.temp / 'full-shipping-clock.json', value)
        return app, staging

    def run_product(self, app, error=None, calls=None):
        original = Path.read_text
        calls = [] if calls is None else calls
        def read_text(path, *args, **kwargs):
            if str(path) == '/tmp/current-celluloid-simulator': return installed_fixtures.InstalledIdentityTests.UDID + '\n'
            return original(path, *args, **kwargs)
        def run(args, **kwargs):
            calls.append((args, kwargs))
            if error: raise error
            return subprocess.CompletedProcess(args, 0, str(app) + '\n', '')
        with patch.object(Path, 'read_text', read_text), patch('native_process.run', side_effect=run), patch.object(handoff, 'ROOT', self.temp):
            handoff.product_after(self.temp)
        return calls

    def test_actual_installed_product_is_read_once_and_source_run_attempt_bound(self):
        app, staging = self.make_product()
        calls = self.run_product(app)
        row = handoff.read(self.temp / 'full-shipping-product-after.json')
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], ['xcrun', 'simctl', 'get_app_container', installed_fixtures.InstalledIdentityTests.UDID, 'Mango.Celluloid', 'app'])
        self.assertEqual(calls[0][1]['timeout'], 60)
        self.assertEqual(row['actual']['binary_sha256'], staging['binary_sha256'])
        self.assertEqual(row['actual']['device_id'], installed_fixtures.InstalledIdentityTests.UDID)
        self.assertEqual(row['staging_sha256'], handoff.sha(self.temp / 'uikit-layer-staging.json'))
        self.assertEqual(row['source_sha'], SOURCE)
        self.assertEqual(row['run_id'], '1234567')
        self.assertEqual(row['run_attempt'], '1')

    def test_changed_source_binary_product_or_device_cannot_make_receipt(self):
        for mutation in ('source', 'binary', 'identity', 'device'):
            app, staging = self.make_product()
            if mutation == 'source':
                staging['source_sha'] = 'd' * 40
                put_json(self.temp / 'uikit-layer-staging.json', staging)
            elif mutation == 'binary': (app / 'Celluloid').write_bytes(b'substituted binary')
            elif mutation == 'identity': (app / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': 'Wrong.App'}))
            else: app = Path(str(app).replace(installed_fixtures.InstalledIdentityTests.UDID, 'FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF'))
            with self.subTest(mutation=mutation), self.assertRaises((ValueError, FileNotFoundError)):
                self.run_product(app)
            self.assertFalse((self.temp / 'full-shipping-product-after.json').exists())
            shutil.rmtree(self.temp / 'Devices')

    def test_product_lookup_timeout_does_not_retry_or_write_success(self):
        app, _ = self.make_product()
        with self.assertRaises(TimeoutError): self.run_product(app, TimeoutError('synthetic bounded lookup timeout'))
        self.assertFalse((self.temp / 'full-shipping-product-after.json').exists())

    def test_product_lookup_requires_full_sixty_seconds_plus_cleanup_before_dispatch(self):
        app, _ = self.make_product()
        clock = handoff.read(self.temp / 'full-shipping-clock.json')
        # Exact arithmetic avoids platform monotonic float cancellation at the floor boundary.
        clock['started_monotonic'] = 100_000.0
        put_json(self.temp / 'full-shipping-clock.json', clock)
        deadline = accounting.TAIL_PHASES['product-readbacks'][1]
        for remaining in (74, 60, 15, 1):
            calls = []
            observed = clock['started_monotonic'] + deadline - remaining
            with self.subTest(remaining=remaining), patch.object(accounting.time, 'monotonic', return_value=observed), self.assertRaisesRegex(ValueError, 'no dispatch'):
                self.run_product(app, calls=calls)
            self.assertEqual(calls, [])
            self.assertFalse((self.temp / 'full-shipping-product-after.json').exists())
        observed = clock['started_monotonic'] + deadline - 75
        with patch.object(accounting.time, 'monotonic', return_value=observed):
            calls = self.run_product(app)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1]['timeout'], 60)

    def test_late_owned_return_or_post_readback_never_writes_success(self):
        app, _ = self.make_product()
        clock = handoff.read(self.temp / 'full-shipping-clock.json')
        start = clock['started_monotonic']
        deadline = accounting.TAIL_PHASES['product-readbacks'][1]
        for observations in ([start + deadline - 80, start + deadline + 1],
                             [start + deadline - 80, start + deadline - 20, start + deadline + 1]):
            calls = []
            with self.subTest(observations=observations), patch.object(accounting.time, 'monotonic', side_effect=observations), self.assertRaisesRegex(ValueError, 'Late UIKit phase completion'):
                self.run_product(app, calls=calls)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][1]['timeout'], 60)
            self.assertFalse((self.temp / 'full-shipping-product-after.json').exists())

    def test_device_and_transfer_bind_source_run_attempt_row_and_owned_simulator(self):
        mutations = [('full-shipping-device.json', lambda value: value.update(source_sha='d' * 40)),
                     ('full-shipping-device.json', lambda value: value.update(run_id='2')),
                     ('full-shipping-device.json', lambda value: value.update(run_attempt='2')),
                     ('full-shipping-device.json', lambda value: value.update(row='large-phone')),
                     ('full-shipping-device.json', lambda value: value['device'].update(id='FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF')),
                     ('full-shipping-device.json', lambda value: value['device'].update(model=accounting.ROWS['large-phone'])),
                     ('full-shipping-transfer.json', lambda value: value.update(source_sha='d' * 40)),
                     ('full-shipping-transfer.json', lambda value: value.update(run_id='2')),
                     ('full-shipping-transfer.json', lambda value: value.update(run_attempt='2')),
                     ('full-shipping-transfer.json', lambda value: value.update(layer_archive_sha256='d' * 64))]
        for filename, change in mutations:
            app, _ = self.make_product()
            path = self.temp / filename
            value = handoff.read(path)
            change(value)
            put_json(path, value)
            with self.subTest(filename=filename, change=change), self.assertRaises(ValueError):
                self.run_product(app)
            self.assertFalse((self.temp / 'full-shipping-product-after.json').exists())
            shutil.rmtree(self.temp / 'Devices')

    def test_fixed_built_executable_cannot_be_missing_changed_or_symlinked(self):
        for change in ('missing', 'changed', 'symlink'):
            app, _ = self.make_product()
            built = self.temp / '.build/Build/Products/Debug-iphonesimulator/Celluloid.app/Celluloid'
            if change == 'changed': built.write_bytes(b'changed after execution')
            else:
                built.unlink()
                if change == 'symlink': built.symlink_to(app / 'Celluloid')
            with self.subTest(change=change), self.assertRaises(ValueError): self.run_product(app)
            self.assertFalse((self.temp / 'full-shipping-product-after.json').exists())
            if built.is_symlink(): built.unlink()
            shutil.rmtree(self.temp / 'Devices')

    def test_product_clock_cannot_be_from_another_attempt_or_exhausted(self):
        for change, error in (({'run_attempt': '2'}, 'identity differs'),
                              ({'started_monotonic': 97_300.125}, 'No remaining allocation')):
            app, _ = self.make_product()
            path = self.temp / 'full-shipping-clock.json'
            value = handoff.read(path)
            value.update(change)
            put_json(path, value)
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, error): self.run_product(app)
            self.assertFalse((self.temp / 'full-shipping-product-after.json').exists())
            shutil.rmtree(self.temp / 'Devices')


class AcceptRowTests(HandoffFixtures):
    def setUp(self):
        super().setUp()
        self.package()
        self.transfer()
        transfer_proof = handoff.read(self.temp / 'full-shipping-transfer.json')
        app, staging = ProductBindingTests.make_product(self)
        put_json(self.temp / 'full-shipping-transfer.json', transfer_proof)
        ProductBindingTests.run_product(self, app)
        self.device_id = installed_fixtures.InstalledIdentityTests.UDID
        row_clock = handoff.read(self.temp / 'full-shipping-clock.json')
        row_clock.update(started_monotonic=100_000.125, started_unix=time.time() - 300)
        put_json(self.temp / 'full-shipping-clock.json', row_clock)
        execution_fixtures.write_execution(self.temp)
        for index, phase in enumerate(accounting.expected_phases('compact-phone')):
            path = self.temp / accounting.phase_files(phase)[1]
            summary = handoff.read(path)
            summary['devicesAndConfigurations'][0]['device']['deviceId'] = self.device_id
            summary.update(startTime=row_clock['started_unix'] + 10 + index * 10,
                           finishTime=row_clock['started_unix'] + 11 + index * 10)
            put_json(path, summary)
        (self.temp / 'bootstrap.log').write_text('Synthetic bootstrap driver observation for source-bound portable replay\n')
        _, consumer_log, _, _, _ = self.synthetic.profile('2x')
        consumer_log = '\n'.join(line for line in consumer_log.splitlines()
                                 if not line.startswith(('Executed ', '** TEST'))).strip() + '\n'
        units = self.temp / 'units.log'
        consumer_case = '-[CelluloidTests.MacPhotosManufacturedAdjustmentTests testManufacturedMacArchiveThroughOriginalUIKitReaderAndCompositor]'
        original_case = f"Test Case '{consumer_case}' started.\nTest Case '{consumer_case}' passed (0.1 seconds).\n"
        self.assertEqual(units.read_text().count(original_case), 1)
        units.write_text(units.read_text().replace(original_case, consumer_log))
        value = execution_fixtures.manifest()
        value['device']['id'] = self.device_id
        put_json(self.temp / 'full-shipping-execution.json', value)
        report = accounting.verify_manifest(value, self.temp, execution_fixtures.context(), row_clock)
        put_json(self.temp / 'full-shipping-accounting.json', report)
        put_json(self.temp / 'full-shipping-cleanup.json', {
            **handoff.identity(), 'row': 'compact-phone', 'device_id': self.device_id,
            'actions': [{'action': 'shutdown', 'exit_code': 0}, {'action': 'delete', 'exit_code': 0}]})
        stages = ['source_before', 'environment', 'reproducible', 'transfer', 'device_selection',
                  'prepare', 'stage_fixture', 'units', 'consumer_contract', 'bootstrap', 'photos_integration',
                  'ui', 'screens', 'product_after', 'shutdown', 'delete', 'source_after',
                  'release_build', 'permissions', 'dark', 'preservation']
        put_json(self.temp / 'full-shipping-stage-outcomes.json',
                 {name: {'outcome': 'success', 'conclusion': 'success'} for name in stages})
        consumer = verify('uikit', units, self.artifact, SOURCE, platform_contract=True,
                          runtime_summary=handoff.read(self.temp / 'units.summary.json'),
                          expected_device=value['device'])
        put_json(self.temp / 'uikit-required-tests.json', consumer)

    def test_complete_row_replays_every_named_case_consumer_source_product_and_cleanup(self):
        row = handoff.accept_row(self.temp)
        self.assertTrue(row['row_checks_passed'])
        self.assertEqual(row['original_test_invocation_count'], 108)
        self.assertEqual(row['device']['id'], self.device_id)
        self.assertTrue(row['workflow_completion_required'])
        self.assertFalse(row['release_acceptance'])
        for name, digest in row['proof_sha256'].items():
            self.assertEqual(digest, handoff.sha(self.temp / name))

    def test_accepted_row_retains_full_logs_losslessly_under_unchanged_artifact_cap(self):
        row = handoff.accept_row(self.temp)
        put_json(self.temp / 'full-shipping-row.json', row)
        output = self.temp / 'packed-accepted'
        output.mkdir()
        retained = {}
        def retain(name, data, source):
            retained[name] = data
            (output / name).write_bytes(data)
            return True
        index = handoff.pack_phase_logs(self.temp, retain, 1_500_000)
        self.assertTrue(index['producer_complete'])
        self.assertEqual(index['omissions'], [])
        self.assertLessEqual(sum(map(len, retained.values())), 1_500_000)
        context = {**handoff.identity(), 'row': 'compact-phone'}
        unpacked = handoff.unpack_phase_logs(output, handoff.read(output / handoff.LOG_INDEX), context)
        self.assertEqual(unpacked, {name: (self.temp / name).read_bytes()
                                    for _, name in handoff.phase_log_inventory('compact-phone')})
        with (self.temp / 'bootstrap.log').open('a') as stream:
            stream.write('changed after accepted row proof\n')
        with self.assertRaisesRegex(ValueError, 'Unverified complete log producer'):
            handoff.pack_phase_logs(self.temp, retain, 1_500_000)

    def test_collector_keeps_core_proofs_before_full_logs_and_optional_pressure_without_duplicate_timings(self):
        summary = handoff.read(self.temp / 'units.summary.json')
        put_json(self.temp / 'uikit-required-tests.runtime-summary.json', summary)
        put_json(self.temp / 'full-shipping-phase-outcomes.json',
                 [{'name': phase, 'exit_code': 0} for phase in accounting.expected_phases('compact-phone')])
        timings = []
        for phase in ('bootstrap-readiness', 'bootstrap-reconcile'):
            name = accounting.phase_files(phase)[0] + '.timing.json'
            put_json(self.temp / name, {'command': 'xcodebuild', 'return_code': 0, 'timed_out': False,
                                      'timeout_seconds': 360, 'elapsed_seconds': 1})
            timings.append(name)
        put_json(self.temp / 'full-shipping-row.json', handoff.accept_row(self.temp))
        # Optional old log tails compete for the same unchanged row budget.
        for name in ('domain.log', 'rendering.log', 'mac-ui.log', 'sandbox.log', 'uikit-diagnostics.log',
                     'mac-release.log', 'vision-build.log', 'tv-build.log'):
            (self.temp / name).write_text('optional diagnostic detail\n' * 25_000)
        result = run_collector(self.temp)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = self.temp / 'celluloid-bounded-evidence'
        manifest = handoff.read(output / 'manifest.json')
        names = [row['name'] for row in manifest['files']]
        self.assertEqual(len(names), len(set(names)), 'Collector emitted duplicate manifest names')
        for name in timings:
            self.assertEqual(names.count(name), 1)
            self.assertEqual((output / name).read_bytes(), (self.temp / name).read_bytes())
        index = handoff.read(output / handoff.LOG_INDEX)
        self.assertTrue(index['producer_complete'])
        first_log = min(names.index(row['name']) for row in index['files'])
        for name in ('consumer-mac-layer-fixture.json', 'uikit-required-tests.json', 'full-shipping-row.json',
                     'full-shipping-accounting.json', 'shipping-consumer-markers.json', *timings):
            self.assertLess(names.index(name), first_log, name)
        self.assertLess(names.index(handoff.LOG_INDEX), names.index('domain.log.tail.txt'))
        self.assertEqual(handoff.unpack_phase_logs(output, index, {**handoff.identity(), 'row': 'compact-phone'}),
                         {name: (self.temp / name).read_bytes() for _, name in handoff.phase_log_inventory('compact-phone')})
        self.assertEqual(manifest['limits']['total_bytes'], 1_500_000)
        self.assertLessEqual(sum(path.stat().st_size for path in output.iterdir()), 1_500_000)
        self.assertTrue(any(row.get('reason') == 'evidence byte cap' for row in manifest['omissions']))

    def test_saved_positive_status_cannot_hide_changed_execution_or_clock(self):
        path = self.temp / 'full-shipping-accounting.json'
        original = path.read_bytes()
        mutations = [lambda value: value.update(original_test_invocation_count=107),
                     lambda value: value['phases'][0].update(case_count=85),
                     lambda value: value['clock'].update(elapsed_seconds=value['clock']['elapsed_seconds'] + 10_000),
                     lambda value: value['clock'].update(reserved_tail_seconds=0)]
        for mutation in mutations:
            value = json.loads(original)
            mutation(value)
            put_json(path, value)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                handoff.accept_row(self.temp)
        path.write_bytes(original)

    def test_changed_source_transfer_product_device_and_consumer_links_reject(self):
        mutations = [('combined-source-after.json', lambda value: value.update(tree='d' * 40)),
                     ('full-shipping-transfer.json', lambda value: value.update(schema='Unreviewed.Transfer')),
                     ('full-shipping-transfer.json', lambda value: value.update(queue_expiry_applied=True)),
                     ('full-shipping-transfer.json', lambda value: value.update(run_attempt='2')),
                     ('full-shipping-transfer.json', lambda value: value.update(manifest_and_all_members_verified=False)),
                     ('full-shipping-transfer.json', lambda value: value.update(layer_archive_sha256='d' * 64)),
                     ('full-shipping-device.json', lambda value: value['device'].update(id='FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF')),
                     ('full-shipping-device.json', lambda value: value.update(schema='Unreviewed.Device')),
                     ('full-shipping-product-after.json', lambda value: value.update(schema='Unreviewed.Product')),
                     ('full-shipping-product-after.json', lambda value: value.update(staging_sha256='d' * 64)),
                     ('full-shipping-product-after.json', lambda value: value['actual'].update(binary_sha256='d' * 64)),
                     ('uikit-layer-staging.json', lambda value: value.update(binary_sha256='d' * 64)),
                     ('uikit-required-tests.json', lambda value: value.update(aggregate_execution_passed=False)),
                     ('uikit-required-tests.json', lambda value: value['platform_contract'].update(profile='3x'))]
        for filename, change in mutations:
            path = self.temp / filename
            original = path.read_bytes()
            value = json.loads(original)
            change(value)
            put_json(path, value)
            with self.subTest(filename=filename, change=change), self.assertRaises(ValueError):
                handoff.accept_row(self.temp)
            path.write_bytes(original)

    def test_owned_cleanup_requires_exact_successful_shutdown_and_delete(self):
        path = self.temp / 'full-shipping-cleanup.json'
        original = path.read_bytes()
        mutations = [lambda value: value.update(device_id='FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF'),
                     lambda value: value.update(run_id='2'),
                     lambda value: value['actions'].pop(),
                     lambda value: value['actions'].reverse(),
                     lambda value: value['actions'][0].update(exit_code=1),
                     lambda value: value['actions'][1].update(exit_code=False),
                     lambda value: value['actions'][1].update(exit_code=None)]
        for mutation in mutations:
            value = json.loads(original)
            mutation(value)
            put_json(path, value)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                handoff.accept_row(self.temp)
        path.write_bytes(original)

    def test_missing_proof_cannot_be_replaced_by_successful_prerequisite_strings(self):
        names = ['full-shipping-accounting.json', 'combined-source-after.json', 'full-shipping-device.json',
                 'full-shipping-transfer.json', 'full-shipping-product-after.json', 'full-shipping-cleanup.json',
                 'uikit-required-tests.json', 'units.summary.json', 'full-shipping-stage-outcomes.json', 'bootstrap.log']
        for name in names:
            path = self.temp / name
            original = path.read_bytes()
            path.unlink()
            with self.subTest(name=name), self.assertRaises(ValueError): handoff.accept_row(self.temp)
            path.write_bytes(original)

    def test_same_count_case_substitution_and_unexplained_raw_error_are_rejected_on_replay(self):
        path = self.temp / 'units.log'
        original = path.read_text()
        for changed in (original.replace('testExifOrientationIsAppliedExactlyOnce', 'testUnexpectedSameCount'),
                        original + 'error: unaccounted XCTest error\n'):
            path.write_text(changed)
            with self.subTest(changed=changed[-100:]), self.assertRaises(ValueError):
                handoff.accept_row(self.temp)

    def test_passing_tests_cannot_hide_failed_skipped_or_missing_workflow_stage(self):
        path = self.temp / 'full-shipping-stage-outcomes.json'
        original = path.read_bytes()
        for stage in ('environment', 'reproducible', 'units', 'bootstrap', 'permissions', 'screens',
                      'product_after', 'shutdown', 'delete', 'source_after', 'release_build'):
            for status in ('failure', 'skipped', 'cancelled', 'missing'):
                value = json.loads(original)
                if status == 'missing': del value[stage]
                else: value[stage]['outcome'] = status
                put_json(path, value)
                with self.subTest(stage=stage, status=status), self.assertRaisesRegex(ValueError, 'workflow stage'):
                    handoff.accept_row(self.temp)
        value = json.loads(original)
        value['diagnostics'] = {'outcome': 'failure', 'conclusion': 'failure'}
        put_json(path, value)
        with self.assertRaisesRegex(ValueError, 'diagnostics stage'): handoff.accept_row(self.temp)


class FreshUptimeFixtureTests(unittest.TestCase):
    def test_complete_row_fixture_remains_valid_at_fresh_or_fractional_host_uptime(self):
        for uptime in (0, .125, 29.5, 299.5, 2700, 2701):
            with self.subTest(uptime=uptime), patch.object(time, 'monotonic', return_value=uptime):
                fixture = AcceptRowTests('test_complete_row_replays_every_named_case_consumer_source_product_and_cleanup')
                try:
                    fixture.setUp()
                    fixture.test_complete_row_replays_every_named_case_consumer_source_product_and_cleanup()
                finally:
                    fixture.doCleanups()


class LosslessPhaseLogTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, environment(), clear=True)
        env.start()
        self.addCleanup(env.stop)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.temp = Path(temporary.name)
        self.output = self.temp / 'packed'
        self.output.mkdir()
        self.context = {**handoff.identity(), 'row': 'compact-phone'}
        self.original = {}
        for index, (phase, name) in enumerate(handoff.phase_log_inventory('compact-phone')):
            # Includes every byte value, line endings, and multiple read chunks.
            data = (phase + '\r\n').encode() + bytes(range(256)) * (300 + index) + b'\x00\nlast line\r\n'
            self.original[name] = data
            (self.temp / name).write_bytes(data)
        self.retained = {}

    def retain(self, name, data, source):
        self.retained[name] = data
        (self.output / name).write_bytes(data)
        return True

    def pack(self, available=1_500_000):
        return handoff.pack_phase_logs(self.temp, self.retain, available)

    def unpack(self, index):
        return handoff.unpack_phase_logs(self.output, index, self.context)

    def rewrite_stream(self, index, data):
        row = index['files'][0]
        (self.output / row['name']).write_bytes(data)
        row.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())

    def test_full_byte_roundtrip_does_not_create_test_completeness(self):
        index = self.pack()
        self.assertFalse(index['producer_complete'])
        self.assertEqual(index['omissions'], [])
        self.assertEqual(self.unpack(index), self.original)
        self.assertLessEqual(sum(map(len, self.retained.values())), 1_500_000)
        self.assertEqual(handoff.read(self.output / handoff.LOG_INDEX), index)
        driver = [row for row in index['files'] if row['phase'] == 'bootstrap-driver']
        self.assertEqual(len(driver), 1)
        self.assertEqual(driver[0]['raw_name'], 'bootstrap.log')
        self.assertNotIn('bootstrap-driver', accounting.expected_phases('compact-phone'))
        self.assertEqual(len(index['files']), len(accounting.expected_phases('compact-phone')) + 1)

    def test_failed_and_partial_rows_remain_incomplete(self):
        put_json(self.temp / 'full-shipping-row.json', {'row_checks_passed': False, 'error': 'original failed phase'})
        complete_logs = self.pack()
        self.assertFalse(complete_logs['producer_complete'])
        self.assertEqual(complete_logs['omissions'], [])
        missing = accounting.phase_files('preservation')[0]
        (self.temp / missing).unlink()
        index = self.pack()
        self.assertFalse(index['producer_complete'])
        self.assertEqual(index['omissions'], [{'phase': 'preservation', 'reason': 'producer did not emit log'}])
        self.assertEqual(self.unpack(index), {name: data for name, data in self.original.items() if name != missing})

    def test_collector_preserves_failed_partial_logs_without_claiming_completion(self):
        row = {'schema': 'Celluloid.UIKitFullShippingRow.1', **self.context,
               'row_checks_passed': False, 'release_acceptance': False, 'error': 'original bootstrap did not finish'}
        put_json(self.temp / 'full-shipping-row.json', row)
        missing = accounting.phase_files('bootstrap-reconcile')[0]
        (self.temp / missing).unlink()
        failed = b"Test Case '-[CelluloidTests.EditorRegressionTests testPhotosLibraryBootstrapReadiness]' started.\npartial process output\n"
        first = accounting.phase_files('bootstrap-readiness')[0]
        (self.temp / first).write_bytes(failed)
        self.original[first] = failed
        result = run_collector(self.temp)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = self.temp / 'celluloid-bounded-evidence'
        retained_row = handoff.read(output / 'full-shipping-row.json')
        self.assertFalse(retained_row['row_checks_passed'])
        index = handoff.read(output / handoff.LOG_INDEX)
        self.assertFalse(index['producer_complete'])
        self.assertEqual(index['omissions'], [{'phase': 'bootstrap-reconcile', 'reason': 'producer did not emit log'}])
        self.assertEqual(handoff.unpack_phase_logs(output, index, self.context),
                         {name: data for name, data in self.original.items() if name != missing})
        manifest = handoff.read(output / 'manifest.json')
        self.assertTrue(any(row['name'] == 'full-shipping-accounting.json' for row in manifest['omissions']))
        self.assertLessEqual(sum(path.stat().st_size for path in output.iterdir()), 1_500_000)

    def test_row_boolean_and_matching_log_hashes_cannot_forge_complete_producer(self):
        put_json(self.temp / 'full-shipping-row.json', {'row_checks_passed': True})
        put_json(self.temp / 'full-shipping-accounting.json', {'phases': [
            {'phase': phase, 'raw_log_sha256': hashlib.sha256(self.original[accounting.phase_files(phase)[0]]).hexdigest()}
            for phase in accounting.expected_phases('compact-phone')]})
        with self.assertRaises((ValueError, KeyError)): self.pack()

    def test_unknown_duplicate_traversal_and_contradictory_inventories_reject(self):
        original = self.pack()
        mutations = [lambda value: value['files'][0].update(phase='preflight'),
                     lambda value: value['files'][0].update(raw_name='../units.log'),
                     lambda value: value['files'][0].update(name='../full-shipping-units.log.zlib'),
                     lambda value: value['files'][0].update(name='/tmp/full-shipping-units.log.zlib'),
                     lambda value: value['files'][0].update(name='unexpected.log.zlib'),
                     lambda value: value['files'].append(copy.deepcopy(value['files'][0])),
                     lambda value: value['files'].pop(),
                     lambda value: value['omissions'].append({'phase': 'units', 'reason': 'producer did not emit log'}),
                     lambda value: value.update(unused='not an index field')]
        for change in mutations:
            value = copy.deepcopy(original)
            change(value)
            with self.subTest(change=change), self.assertRaises((ValueError, TypeError)):
                self.unpack(value)
        incomplete = copy.deepcopy(original)
        phase = incomplete['files'].pop()['phase']
        incomplete['omissions'] = [{'phase': phase, 'reason': 'producer did not emit log'}]
        incomplete['producer_complete'] = True
        with self.assertRaises(ValueError): self.unpack(incomplete)
        incomplete['producer_complete'] = False
        incomplete['omissions'].append(copy.deepcopy(incomplete['omissions'][0]))
        with self.assertRaises(ValueError): self.unpack(incomplete)

    def test_source_run_attempt_row_and_primitive_types_are_exact(self):
        original = self.pack()
        for key, value in (('source_sha', 'd' * 40), ('run_id', '2'), ('run_attempt', '2'),
                           ('row', 'large-phone'), ('producer_complete', 1), ('raw_aggregate_limit', 30_000_000.0)):
            changed = copy.deepcopy(original)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.unpack(changed)
        for key, value in (('raw_bytes', True), ('bytes', 1.0), ('raw_sha256', 'bad'), ('sha256', 'bad')):
            changed = copy.deepcopy(original)
            changed['files'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.unpack(changed)

    def test_changed_compressed_and_raw_hashes_or_counts_reject(self):
        original = self.pack()
        for key, value in (('sha256', 'd' * 64), ('raw_sha256', 'd' * 64),
                           ('raw_bytes', original['files'][0]['raw_bytes'] - 1),
                           ('raw_bytes', original['files'][0]['raw_bytes'] + 1)):
            changed = copy.deepcopy(original)
            changed['files'][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises((ValueError, zlib.error)):
                self.unpack(changed)
        path = self.output / original['files'][0]['name']
        data = bytearray(path.read_bytes())
        data[len(data) // 2] ^= 1
        path.write_bytes(data)
        with self.assertRaises((ValueError, zlib.error)): self.unpack(original)

    def test_missing_symlink_truncated_trailing_and_concatenated_streams_reject(self):
        original = self.pack()
        first = original['files'][0]
        path = self.output / first['name']
        data = path.read_bytes()
        path.unlink()
        with self.assertRaises(ValueError): self.unpack(original)
        outside = self.temp / 'outside.zlib'
        outside.write_bytes(data)
        path.symlink_to(outside)
        with self.assertRaises(ValueError): self.unpack(original)
        path.unlink()
        os.link(outside, path)
        with self.assertRaises(ValueError): self.unpack(original)
        path.unlink()
        for changed in (data[:-2], data + b'trailing bytes', data + zlib.compress(b'concatenated second stream')):
            index = copy.deepcopy(original)
            self.rewrite_stream(index, changed)
            with self.subTest(size=len(changed)), self.assertRaises((ValueError, zlib.error)):
                self.unpack(index)

    def test_declared_output_bomb_is_rejected_with_bounded_chunks(self):
        index = self.pack()
        bomb = zlib.compress(b'x' * 2_000_000)
        self.rewrite_stream(index, bomb)
        index['files'][0].update(raw_bytes=100, raw_sha256=hashlib.sha256(b'x' * 100).hexdigest())
        original_factory = zlib.decompressobj
        requested = []
        class BoundedDecoder:
            def __init__(self): self.actual = original_factory()
            def decompress(self, data, maximum):
                requested.append(maximum)
                if not 0 < maximum <= 65_536:
                    raise AssertionError('Unbounded decompression allocation')
                return self.actual.decompress(data, maximum)
            def __getattr__(self, name): return getattr(self.actual, name)
        with patch.object(handoff.zlib, 'decompressobj', side_effect=BoundedDecoder), self.assertRaises(ValueError):
            self.unpack(index)
        self.assertTrue(requested)

    def test_valid_high_compression_stream_also_uses_incremental_output(self):
        name = accounting.phase_files('units')[0]
        self.original[name] = b'x' * 2_000_000
        (self.temp / name).write_bytes(self.original[name])
        index = self.pack()
        original_factory = zlib.decompressobj
        requested = []
        class BoundedDecoder:
            def __init__(self): self.actual = original_factory()
            def decompress(self, data, maximum):
                requested.append(maximum)
                if not 0 < maximum <= 65_536:
                    raise AssertionError('Unbounded decompression allocation')
                return self.actual.decompress(data, maximum)
            def __getattr__(self, name): return getattr(self.actual, name)
        with patch.object(handoff.zlib, 'decompressobj', side_effect=BoundedDecoder):
            self.assertEqual(self.unpack(index), self.original)
        self.assertGreater(len(requested), 30)

    def test_unpack_aggregate_caps_are_checked_before_any_stream_is_opened(self):
        original = self.pack()
        for key, value in (('raw_bytes', 30_000_000), ('bytes', 1_500_001)):
            changed = copy.deepcopy(original)
            changed['files'][0][key] = value
            with self.subTest(key=key), patch.object(handoff.os, 'open', side_effect=AssertionError('unadmitted stream open')), self.assertRaisesRegex(ValueError, 'aggregate'):
                self.unpack(changed)

    def test_pack_admits_raw_aggregate_before_reading_the_excess_file(self):
        phases = accounting.expected_phases('compact-phone')
        first = self.temp / accounting.phase_files(phases[0])[0]
        with first.open('wb') as stream: stream.truncate(30_000_001)
        with patch.object(handoff.os, 'read', side_effect=AssertionError('unadmitted raw read')), self.assertRaisesRegex(ValueError, 'before read'):
            self.pack()
        second = self.temp / accounting.phase_files(phases[1])[0]
        for path in (first, second):
            with path.open('wb') as stream: stream.truncate(16_000_000)
        actual_read = os.read
        read_bytes = []
        def observed_read(fd, limit):
            data = actual_read(fd, limit)
            read_bytes.append(len(data))
            return data
        with patch.object(handoff.os, 'read', side_effect=observed_read), self.assertRaisesRegex(ValueError, 'before read'):
            self.pack()
        self.assertEqual(sum(read_bytes), 16_000_000)

    def test_pack_rejects_unsafe_raw_file_or_insufficient_remaining_artifact_space(self):
        first = self.temp / 'units.log'
        original = first.read_bytes()
        first.unlink()
        outside = self.temp / 'outside.log'
        outside.write_bytes(original)
        first.symlink_to(outside)
        with self.assertRaises((ValueError, OSError)): self.pack()
        first.unlink()
        os.link(outside, first)
        with self.assertRaisesRegex(ValueError, 'before read'): self.pack()
        first.unlink()
        first.write_bytes(original)
        with self.assertRaisesRegex(ValueError, 'artifact cap'): self.pack(16_000)
        with self.assertRaisesRegex(ValueError, 'omitted'):
            handoff.pack_phase_logs(self.temp, lambda *args: False, 1_500_000)

    def test_unused_nonfinite_json_index_fields_are_rejected_before_unpack(self):
        index = self.pack()
        original = json.dumps(index)
        path = self.output / handoff.LOG_INDEX
        for token in ('NaN', 'Infinity', '-Infinity', '1e999'):
            path.write_text(original[:-1] + ',"unused":{"samples":[' + token + ']}}')
            with self.subTest(token=token), self.assertRaisesRegex(ValueError, 'Nonfinite JSON number'):
                handoff.read(path)


if __name__ == '__main__':
    unittest.main()
