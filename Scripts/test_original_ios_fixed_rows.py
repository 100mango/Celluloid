"""Literal predecessor reuse rejects changed source, metadata, identity and bytes."""
import copy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import original_ios_fixed_rows as fixed
import original_ios_archive as archive
import original_ios_source_contract as projection
import uikit_full_shipping_handoff as handoff
from test_original_ios_route import environment


def put(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def metadata(key):
    value = fixed.artifact_record(key)
    return {'id': int(value['artifact_id']), 'name': value['name'], 'expired': False,
            'digest': 'sha256:' + value['reported_upload_artifact_digest'],
            'workflow_run': {'id': int(value['run_id']), 'head_sha': value['source_sha'],
                             'head_branch': fixed.ORIGINAL_IOS['branch']}}


class FixedRowsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.temp = Path(self.directory.name)
        self.env = patch.dict(os.environ, environment(), clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.identity = handoff.identity()
        self.source = {'source_sha': self.identity['source_sha'], 'tree': 'b' * 40,
                       'phase': 'before', 'file_count': 546, 'source_fingerprint': fixed.FINGERPRINT,
                       'validation_route': fixed.ORIGINAL_IOS, 'original_ios_source': projection.audit()}
        put(self.temp / 'combined-source-before.json', self.source)
        (self.temp / 'full-shipping-xcode.txt').write_text('Xcode 27.0\nBuild version 27A266a\n')
        self.clock = {'schema': archive.CLOCK_SCHEMA, **self.identity, 'started_monotonic': time.monotonic(),
                      'started_unix': time.time(), 'execution_budget_seconds': 1560}
        put(self.temp / archive.CLOCK, self.clock)

    def process(self, command, command_deadline, cleanup_deadline, cap, stop_on_signal_error):
        self.assertTrue(stop_on_signal_error)
        self.assertEqual(cap, 8192)
        self.assertLess(command_deadline, cleanup_deadline)
        self.assertLessEqual(cleanup_deadline, self.clock['started_monotonic'] + 300)
        key = next(k for k, v in fixed.ARTIFACTS.items() if command[-1].endswith('/' + v['artifact_id']))
        self.assertEqual(command, ['gh', 'api', 'repos/100mango/Celluloid/actions/artifacts/' + fixed.ARTIFACTS[key]['artifact_id']])
        raw = json.dumps(metadata(key)).encode()
        return {'return_code': 0, 'output': raw, 'bytes_read': len(raw), 'pipe_eof': True,
                'child_reaped': True, 'timed_out': False, 'overflow': False, 'cleanup_error': None,
                'finalized': True, 'elapsed_seconds': .01,
                'command_deadline_monotonic': command_deadline, 'cleanup_deadline_monotonic': cleanup_deadline}

    def fetch(self):
        with patch('mac_owned_crash.bounded_optional_process', side_effect=self.process) as call:
            result = fixed.fetch_metadata(self.temp)
        self.assertEqual(call.call_count, 4)
        return result

    def test_source_applicability_keeps_both_identities_and_actual_toolchain(self):
        before = dict(os.environ)
        value = fixed.source_applicability(self.temp)
        self.assertEqual(value['current']['source_sha'], self.identity['source_sha'])
        self.assertEqual(value['original']['source_sha'], fixed.FIXED_IDENTITY['source_sha'])
        self.assertEqual(value['protected_files'], 546)
        self.assertEqual(value['actual_xcode_sha256'], fixed.XCODE_SHA256)
        self.assertFalse(value['native_reexecution'])
        self.assertEqual(dict(os.environ), before)

    def test_source_generator_compilation_and_toolchain_changes_reject(self):
        original = fixed._bytes
        paths = ['Celluloid/AppDelegate.swift', 'Scripts/generate_project.py',
                 'Scripts/original-ios-source-contract.json', 'full-shipping-xcode.txt',
                 fixed.ORIGINAL_IOS['workflow_path']]
        for target in paths:
            def changed(path, maximum):
                raw = original(path, maximum)
                if str(path).endswith(target):
                    return raw.replace(b'-configuration Debug', b'-configuration Release', 1) if target.endswith('.yml') else raw + b' '
                return raw
            with self.subTest(target=target), patch.object(fixed, '_bytes', side_effect=changed), self.assertRaises(ValueError):
                fixed.source_applicability(self.temp)

    def test_metadata_reads_only_four_fixed_targets_and_rejects_wrong_records(self):
        value = self.fetch()
        self.assertTrue(value['complete'])
        self.assertEqual(set(value['observations']), set(fixed.ARTIFACTS))
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(fixed.validate_metadata(value, self.identity), value)
            for field, invalid in [('source_sha', 'c' * 40), ('run_id', '7654321'), ('run_attempt', '2')]:
                with self.subTest(binding=field), self.assertRaises(ValueError):
                    fixed.validate_metadata(value, {**self.identity, field: invalid})
        for key in fixed.ARTIFACTS:
            for field, invalid in [('id', 12), ('name', 'other'), ('expired', True), ('digest', 'sha256:' + '0' * 64)]:
                record = metadata(key)
                record[field] = invalid
                with self.subTest(key=key, field=field), self.assertRaises(ValueError):
                    fixed.verify_artifact_metadata(record, key)
            for field, invalid in [('id', 12), ('head_sha', 'a' * 40), ('head_branch', 'other')]:
                record = metadata(key)
                record['workflow_run'][field] = invalid
                with self.subTest(key=key, field=field), self.assertRaises(ValueError):
                    fixed.verify_artifact_metadata(record, key)

    def test_unfinalized_timed_out_failed_or_oversized_metadata_stops_next_child_and_retry(self):
        for mutation in [{'finalized': False}, {'pipe_eof': False}, {'child_reaped': False},
                         {'cleanup_error': 'unreaped'}, {'timed_out': True}, {'return_code': 1},
                         {'return_code': False}, {'overflow': True}]:
            path = self.temp / fixed.METADATA
            if path.exists():
                path.unlink()
            def bad(*args, **kwargs):
                return {**self.process(*args, **kwargs), **mutation}
            with self.subTest(mutation=mutation), patch('mac_owned_crash.bounded_optional_process', side_effect=bad) as call:
                with self.assertRaises(ValueError):
                    fixed.fetch_metadata(self.temp)
                self.assertEqual(call.call_count, 1)
                with self.assertRaises(ValueError):
                    fixed.verified_metadata(self.temp)
                with self.assertRaises(ValueError):
                    fixed.fetch_metadata(self.temp)
                self.assertEqual(call.call_count, 1)

    def test_expired_setup_deadline_starts_no_process(self):
        self.clock['started_monotonic'] = 1000.0
        put(self.temp / archive.CLOCK, self.clock)
        with patch.object(time, 'monotonic', return_value=1301.0), \
                patch('mac_owned_crash.bounded_optional_process') as call, \
                self.assertRaisesRegex(ValueError, 'exceeded archive setup deadline'):
            fixed.fetch_metadata(self.temp)
        call.assert_not_called()

    def test_fixed_handoff_requires_literal_row_and_original_source_without_environment_rewrite(self):
        for row in ['small-ipad', 'unknown']:
            with self.subTest(row=row), self.assertRaises(ValueError):
                handoff.accept_row(self.temp, row=row, recorded_observation={}, fixed_original_replay=True)
        for row in fixed.FIXED_ROWS:
            with self.subTest(row=row), self.assertRaises(ValueError):
                handoff.accept_row(self.temp, row=row, fixed_original_replay=True)
        before = dict(os.environ)
        source = copy.deepcopy(self.source)
        source.update(source_sha=fixed.FIXED_IDENTITY['source_sha'], tree=fixed.FIXED_TREE)
        put(self.temp / 'combined-source-before.json', source)
        self.assertEqual(handoff.source_proof(self.temp, fixed_original_replay=True), source)
        with self.assertRaises(ValueError):
            handoff.source_proof(self.temp)
        self.assertEqual(dict(os.environ), before)

    def test_actual_three_rows_replay_and_mutations_reject(self):
        evidence = fixed.ROOT.parent / 'evidence'
        if not (evidence / '04d18-producer').is_dir():
            self.skipTest('The four previously downloaded fixed artifacts are not in this checkout')
        self.fetch()
        before = dict(os.environ)
        results = {row: fixed.verify_fixed_row(self.temp, row, evidence / ('04d18-' + row), evidence / '04d18-producer')
                   for row in fixed.FIXED_ROWS}
        self.assertEqual(dict(os.environ), before)
        self.assertEqual(fixed.validate_fixed_summary(results, self.identity, self.source['tree']), results)
        packet = {'schema': 'Celluloid.OriginalIOSRows.2', **self.identity,
                  'source_tree': self.source['tree'], 'scope': fixed.ORIGINAL_IOS['scope'],
                  'all_rows_verified': True, 'original_total_invocations': 412,
                  'fixed_predecessor_rows': results, 'rows': []}
        for index, row in enumerate(fixed.ROWS):
            if row in results:
                old = results[row]['original']
                artifact = results[row]['artifact']
                execution = {key: old[key] for key in self.identity}
                tree, device = old['source_tree'], old['device']['id']
                receipt, manifest, name = artifact['row_receipt_sha256'], artifact['manifest_sha256'], artifact['name']
            else:
                execution, tree = dict(self.identity), self.source['tree']
                device = '12345678-1234-1234-1234-123456789AB' + str(index)
                receipt, manifest = '1' * 64, '2' * 64
                name = 'celluloid-original-ios-' + row + '-' + execution['source_sha'] + '-' + execution['run_attempt']
            packet['rows'].append({'row': row, 'original_test_invocation_count': fixed.ROW_COUNTS[row],
                                   'model': fixed.ROWS[row], 'device_id': device,
                                   'row_receipt_sha256': receipt, 'artifact_manifest_sha256': manifest,
                                   'artifact_name': name, 'execution_identity': execution, 'execution_source_tree': tree})
        self.assertEqual(archive.row_binding(packet, self.identity, self.source), packet)
        for field, invalid in [('execution_identity', self.identity), ('execution_source_tree', self.source['tree']),
                               ('artifact_name', 'celluloid-original-ios-large-phone-' + self.identity['source_sha'] + '-1')]:
            mutated = copy.deepcopy(packet)
            mutated['rows'][1][field] = invalid
            with self.subTest(old_row_field=field), self.assertRaises(ValueError):
                archive.row_binding(mutated, self.identity, self.source)
        mutated = copy.deepcopy(packet)
        mutated['rows'][2].update(execution_identity=dict(fixed.FIXED_IDENTITY), execution_source_tree=fixed.FIXED_TREE,
                                  artifact_name='celluloid-original-ios-small-ipad-' + fixed.FIXED_IDENTITY['source_sha'] + '-1')
        with self.assertRaises(ValueError):
            archive.row_binding(mutated, self.identity, self.source)
        mutated = copy.deepcopy(packet)
        mutated['fixed_predecessor_rows']['small-ipad'] = mutated['fixed_predecessor_rows'].pop('large-phone')
        with self.assertRaises(ValueError):
            archive.row_binding(mutated, self.identity, self.source)
        for change in ['source', 'attempt', 'receipt', 'toolchain', 'count', 'raw-producer-claim']:
            mutated = copy.deepcopy(results)
            entry = mutated['large-phone']
            if change == 'source':
                entry['original']['source_sha'] = self.identity['source_sha']
            elif change == 'attempt':
                entry['original']['run_attempt'] = '2'
            elif change == 'receipt':
                entry['artifact']['row_receipt_sha256'] = '0' * 64
            elif change == 'toolchain':
                entry['applicability']['actual_xcode_sha256'] = '0' * 64
            elif change == 'count':
                entry['original']['original_test_invocation_count'] = 101
            else:
                entry['producer']['raw_producer_log_replayed'] = True
            with self.subTest(change=change), self.assertRaises(ValueError):
                fixed.validate_fixed_summary(mutated, self.identity, self.source['tree'])
        import shutil
        folder = self.temp / 'changed-row'
        shutil.copytree(evidence / '04d18-large-phone', folder)
        path = folder / 'full-shipping-row.json'
        path.write_bytes(path.read_bytes() + b' ')
        with self.assertRaises(ValueError):
            fixed.verify_fixed_row(self.temp, 'large-phone', folder, evidence / '04d18-producer')


if __name__ == '__main__':
    unittest.main()
