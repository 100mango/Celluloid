"""Offline synthetic retention adversaries; never an Apple build or UI test."""
import copy
import hashlib
import os
from pathlib import Path
import tarfile
import tempfile
import time
import unittest
import sys
from unittest.mock import patch

import final_ios_archive as gate
import final_ios_archive_package as package
import final_ios_archive_delivery as delivery
from test_final_ios_archive_package import Fixture, observation
from test_final_ios_archive import env, clock


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.product = self.root / 'product'
        self.product.mkdir()
        self.fixture = Fixture(self.product)
        for relative in package.EXECUTABLES:
            (self.fixture.archive / relative).chmod(0o755)
        with patch.object(package, 'bounded_optional_process', side_effect=observation):
            proof = package.verify_package(self.product, time.monotonic() + 20)
        source = {'product_sha': gate.SOURCE, 'product_tree': gate.TREE,
                  'control_sha': 'a' * 40, 'control_tree': 'b' * 40,
                  'run_id': '123', 'run_attempt': '1',
                  'workflow_ref': '100mango/Celluloid/' + gate.WORKFLOW + '@' + gate.BRANCH,
                  'control_manifest_sha256': 'c' * 64}
        self.report = {'archive_qualified': True, 'driver_process_cleanup_confirmed': True,
                       'product_sha': gate.SOURCE, 'product_tree': gate.TREE,
                       'control_sha': source['control_sha'], 'run_id': '123', 'run_attempt': '1',
                       'source_before': copy.deepcopy(source), 'source_after': copy.deepcopy(source),
                       'graph_before': proof['source_graph'], 'graph_after': proof['source_graph'],
                       'package': proof, 'xcode': ['Xcode 27.0', 'Build version 27A266a'],
                       'binary_handoff': False, **{key: False for key in delivery.FALSE_FLAGS}}
        self.folder = self.root / 'evidence'

    def tearDown(self):
        self.temp.cleanup()

    def retain(self):
        receipt = delivery.retain(self.report, self.product, self.folder, time.monotonic() + 10)
        self.report['archive_delivery'] = receipt
        self.report['binary_handoff'] = True
        (self.folder / 'report.json').write_bytes(gate.encoded(self.report))
        return receipt

    def test_complete_archive_manifest_and_executable_modes_round_trip(self):
        receipt = self.retain()
        delivery.verify_retained(self.report, self.folder, time.monotonic() + 10)
        manifest = gate.strict_json((self.folder / delivery.MANIFEST_NAME).read_bytes())
        archive = self.folder / delivery.TAR_NAME
        self.assertEqual(receipt['archive']['sha256'], hashlib.sha256(archive.read_bytes()).hexdigest())
        self.assertEqual(manifest['source'], self.report['source_after'])
        self.assertFalse(manifest['installable'])
        self.assertTrue(all(value is False for value in manifest['qualification'].values()))
        with tarfile.open(archive, 'r:') as stream:
            actual = {item.name: item for item in stream}
            for relative in package.EXECUTABLES:
                member = actual[delivery.ARCHIVE_ROOT + '/' + relative]
                self.assertEqual(member.mode, 0o755)
            self.assertEqual(len(actual), len(manifest['members']))
        self.assertEqual(set(p.name for p in self.folder.iterdir()),
                         {'report.json', delivery.MANIFEST_NAME, delivery.TAR_NAME})

    def test_every_qualification_flag_stays_false(self):
        for key in delivery.FALSE_FLAGS:
            report = copy.deepcopy(self.report); report[key] = True
            with self.subTest(key=key), self.assertRaises(ValueError):
                delivery.admissible(report)

    def test_cleanup_and_success_are_required(self):
        for key in ('archive_qualified', 'driver_process_cleanup_confirmed'):
            report = copy.deepcopy(self.report); report[key] = False
            with self.subTest(key=key), self.assertRaises(ValueError):
                delivery.admissible(report)
        for key in ('all_processes_finalized', 'unsigned_package_verified'):
            report = copy.deepcopy(self.report); report['package'][key] = False
            with self.subTest(key=key), self.assertRaises(ValueError):
                delivery.admissible(report)
        report = copy.deepcopy(self.report); report['failure'] = {'reason': 'synthetic'}
        with self.assertRaises(ValueError): delivery.admissible(report)

    def test_source_or_inventory_substitution_rejected(self):
        for key in ('product_sha', 'product_tree', 'control_sha', 'run_id', 'run_attempt'):
            report = copy.deepcopy(self.report); report[key] = 'wrong'
            with self.subTest(key=key), self.assertRaises(ValueError):
                delivery.admissible(report)
        report = copy.deepcopy(self.report); report['source_after']['control_tree'] = 'd' * 40
        with self.assertRaises(ValueError): delivery.admissible(report)
        report = copy.deepcopy(self.report); report['package']['inventory_sha256'] = 'd' * 64
        with self.assertRaises(ValueError): delivery.admissible(report)

    def test_changed_file_after_proof_rejected(self):
        (self.fixture.archive / package.APP / 'collage.json').write_bytes(b'changed')
        with self.assertRaises(ValueError): self.retain()
        self.assertFalse((self.folder / delivery.TAR_NAME).exists())

    def test_added_file_after_proof_rejected(self):
        (self.fixture.archive / 'unexpected.txt').write_bytes(b'extra')
        with self.assertRaises(ValueError): self.retain()

    def test_removed_file_after_proof_rejected(self):
        (self.fixture.archive / package.APP / 'collage.json').unlink()
        with self.assertRaises(ValueError): self.retain()

    def test_symlink_and_hardlink_rejected(self):
        target = self.fixture.archive / package.APP / 'collage.json'
        raw = target.read_bytes(); target.unlink()
        outside = self.root / 'outside'; outside.write_bytes(raw)
        target.symlink_to(outside)
        with self.assertRaises(ValueError): self.retain()
        target.unlink(); os.link(outside, target)
        with self.assertRaises(ValueError): self.retain()

    def test_signing_payload_rejected(self):
        (self.fixture.archive / package.APP / 'embedded.mobileprovision').write_bytes(b'synthetic')
        with self.assertRaises(ValueError): self.retain()

    def test_special_mode_rejected(self):
        (self.fixture.archive / package.APP / 'collage.json').chmod(0o4755)
        with self.assertRaisesRegex(ValueError, 'special-permissions'): self.retain()

    def test_expired_deadline_rejected(self):
        with self.assertRaises(ValueError):
            delivery.retain(self.report, self.product, self.folder, time.monotonic() - 1)

    def test_tar_write_cap_cleans_partial_payload(self):
        with patch.object(delivery, 'MAX_TAR', 100):
            with self.assertRaises(ValueError): self.retain()
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_manifest_write_failure_cleans_archive(self):
        with patch.object(delivery, 'MAX_MANIFEST', 100):
            with self.assertRaises(ValueError): self.retain()
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_tar_tampering_rejected_at_upload(self):
        self.retain()
        path = self.folder / delivery.TAR_NAME
        raw = bytearray(path.read_bytes()); raw[-1] ^= 1; path.write_bytes(raw)
        with self.assertRaises(ValueError):
            delivery.verify_retained(self.report, self.folder, time.monotonic() + 10)

    def test_manifest_tampering_rejected_at_upload(self):
        self.retain()
        path = self.folder / delivery.MANIFEST_NAME
        path.write_bytes(path.read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'manifest-checksum'):
            delivery.verify_retained(self.report, self.folder, time.monotonic() + 10)

    def test_extra_upload_payload_rejected(self):
        self.retain(); (self.folder / 'extra.txt').write_text('not admitted')
        with self.assertRaisesRegex(ValueError, 'evidence-members'):
            delivery.verify_retained(self.report, self.folder, time.monotonic() + 10)

    def test_binary_receipt_required(self):
        self.retain(); self.report['binary_handoff'] = False
        with self.assertRaisesRegex(ValueError, 'missing-receipt'):
            delivery.verify_retained(self.report, self.folder, time.monotonic() + 10)

    def test_no_subprocess_or_extraction_in_delivery(self):
        source = Path(delivery.__file__).read_text()
        self.assertNotIn('import subprocess', source)
        self.assertNotIn('extractall(', source)
        self.assertNotIn('-exportArchive', source)
        self.assertNotIn('codesign', source)

    def prepare_main(self):
        environment = env()
        environment.update(RUNNER_TEMP=str(self.root), GITHUB_OUTPUT=str(self.root / 'output'))
        value = clock()
        (self.root / gate.CLOCK_NAME).write_bytes(gate.encoded(value))
        self.report.update(schema='Celluloid.FinalIOSArchiveDiagnostic.1', clock=value,
                           commands=[], upload_qualified=False)
        return environment

    def test_main_and_both_upload_gates_preserve_source_and_clock(self):
        environment = self.prepare_main()
        with patch.dict(os.environ, environment, clear=True), patch.object(sys, 'argv', ['driver']), \
             patch.object(gate, 'PRODUCT_ROOT', self.product), patch.object(gate, 'execute', return_value=self.report):
            self.assertEqual(gate.main(), 0)
        gate.upload_gate('admit-upload', environment, self.root)
        with self.assertRaises(ValueError): gate.upload_gate('finish-upload', environment, self.root)
        gate.upload_gate('finish-upload', {**environment, 'CELL_ARCHIVE_UPLOAD_OUTCOME': 'success'}, self.root)
        saved = gate.strict_json((self.root / gate.EVIDENCE / 'report.json').read_bytes())
        self.assertTrue(saved['binary_handoff'])
        self.assertFalse(saved['release_qualified'])
        self.assertEqual(saved['clock']['execution_budget_seconds'], 1560)

    def test_retention_failure_fails_main_but_preserves_diagnostic_report(self):
        environment = self.prepare_main()
        with patch.dict(os.environ, environment, clear=True), patch.object(sys, 'argv', ['driver']), \
             patch.object(gate, 'execute', return_value=self.report), \
             patch.object(delivery, 'retain', side_effect=ValueError('synthetic retention failure')):
            self.assertEqual(gate.main(), 1)
        gate.upload_gate('admit-upload', environment, self.root)
        saved = gate.strict_json((self.root / gate.EVIDENCE / 'report.json').read_bytes())
        self.assertTrue(saved['archive_qualified'])
        self.assertFalse(saved['binary_handoff'])
        self.assertIn('delivery_failure', saved)
        self.assertEqual([p.name for p in (self.root / gate.EVIDENCE).iterdir()], ['report.json'])

    def test_archive_failure_never_attempts_binary_retention(self):
        environment = self.prepare_main(); self.report['archive_qualified'] = False
        with patch.dict(os.environ, environment, clear=True), patch.object(sys, 'argv', ['driver']), \
             patch.object(gate, 'execute', return_value=self.report), patch.object(delivery, 'retain') as retain:
            self.assertEqual(gate.main(), 1)
            retain.assert_not_called()

    def test_existing_destination_is_never_overwritten_or_cleaned(self):
        self.folder.mkdir(); target = self.folder / delivery.TAR_NAME
        target.write_bytes(b'existing-owned-by-someone-else')
        with self.assertRaises(FileExistsError): self.retain()
        self.assertEqual(target.read_bytes(), b'existing-owned-by-someone-else')


if __name__ == '__main__':
    unittest.main()
