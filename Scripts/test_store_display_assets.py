"""Portable fixed input byte, PhotoKit receipt, route and corruption checks."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import store_display_assets as assets
import original_ios_process_guard as guard
from test_store_screenshots_route import environment


def observed_library():
    initial = {'asset_count': 0, 'synthetic': [], 'authorization': 3,
               'hash_resources': False, 'library_mutation': False}
    rows = [{'filename': item['staged_filename'], 'identifier': 'actual-' + str(index),
             'bytes': item['bytes'], 'sha256': item['sha256'], 'width': 1254, 'height': 1254}
            for index, item in enumerate(assets.ASSETS)]
    final = dict(initial, asset_count=2, synthetic=rows, hash_resources=True)
    return initial, final


class StoreDisplayAssetsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.legacy = self.root / 'legacy'
        self.legacy.mkdir()
        self.env = environment(self.root)
        scope = patch.dict(os.environ, self.env, clear=True)
        scope.start()
        self.addCleanup(scope.stop)

    def prepare(self):
        return assets.prepare(legacy_root=self.legacy)

    def test_actual_approved_sources_have_exact_bytes_and_public_provenance(self):
        manifest = assets.verify_sources()
        self.assertEqual(manifest['assets'], list(assets.ASSETS))
        self.assertEqual(sum(a['bytes'] for a in assets.ASSETS), 5_878_210)
        public = (assets.ROOT / 'StoreCaptureAssets/README.md').read_text() + json.dumps(manifest)
        for private in ('/workspace/', '/tmp/', 'prompt-', 'scratch/'):
            self.assertNotIn(private, public)
        self.assertIn('synthetic', public)

    def test_prepare_and_staged_readback_preserve_original_bytes_and_exact_context(self):
        receipt = self.prepare()
        paths = assets.staged_assets(self.legacy)
        self.assertEqual(receipt['assets'], list(assets.ASSETS))
        self.assertEqual({key: receipt[key] for key in guard.staged_context()}, guard.staged_context())
        self.assertIs(receipt['picker_order_promised'], False)
        for path, item in zip(paths, assets.ASSETS):
            self.assertEqual(path.name, item['staged_filename'])
            self.assertEqual(path.read_bytes(), (assets.ROOT / 'StoreCaptureAssets' / item['filename']).read_bytes())
        with self.assertRaises(FileExistsError):
            self.prepare()

    def test_legacy_six_paths_block_before_any_staging(self):
        for name in ('celluloid-fixture.png', 'celluloid-fixture-2.png', 'celluloid-composition-unexpected.png'):
            path = self.legacy / name
            path.write_bytes(b'old fixture')
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Legacy'):
                self.prepare()
            self.assertFalse((self.root / 'store-display-assets').exists())
            path.unlink()
        (self.legacy / 'celluloid-fixture.png').symlink_to(self.legacy / 'missing')
        with self.assertRaisesRegex(ValueError, 'Legacy'):
            self.prepare()

    def test_source_extra_files_wrong_hash_and_symlink_are_rejected(self):
        checkout = self.root / 'checkout'
        folder = checkout / 'StoreCaptureAssets'
        shutil.copytree(assets.ROOT / 'StoreCaptureAssets', folder)
        asset = folder / assets.ASSETS[0]['filename']
        original = asset.read_bytes()
        extra = folder / 'private-notes.txt'
        extra.write_text('excluded')
        with self.assertRaisesRegex(ValueError, 'Unexpected public'):
            assets.verify_sources(checkout)
        extra.unlink()
        asset.write_bytes(bytes([original[0] ^ 1]) + original[1:])
        with self.assertRaisesRegex(ValueError, 'hash'):
            assets.verify_sources(checkout)
        asset.unlink()
        asset.symlink_to(assets.ROOT / 'StoreCaptureAssets' / assets.ASSETS[0]['filename'])
        with self.assertRaisesRegex(ValueError, 'size'):
            assets.verify_sources(checkout)

    def test_staged_membership_hash_size_symlink_and_receipt_context_are_checked(self):
        self.prepare()
        folder = self.root / 'store-display-assets'
        source = folder / assets.ASSETS[0]['staged_filename']
        original = source.read_bytes()
        extra = folder / 'celluloid-fixture-old.png'
        extra.write_bytes(b'extra')
        with self.assertRaisesRegex(ValueError, 'membership'):
            assets.staged_assets(self.legacy)
        extra.unlink()
        for raw in (original[:-1], bytes([original[0] ^ 1]) + original[1:]):
            source.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, 'changed'):
                assets.staged_assets(self.legacy)
        source.unlink()
        source.symlink_to(assets.ROOT / 'StoreCaptureAssets' / assets.ASSETS[0]['filename'])
        with self.assertRaisesRegex(ValueError, 'changed'):
            assets.staged_assets(self.legacy)
        source.unlink()
        source.write_bytes(original)
        receipt_path = self.root / 'store-display-preparation.json'
        receipt = json.loads(receipt_path.read_text())
        for key, value in (('row', 'large-ipad'), ('source_sha', 'b' * 40), ('directory', str(self.legacy)),
                           ('original_bytes_preserved', 1), ('picker_order_promised', True)):
            receipt_path.write_text(json.dumps(dict(receipt, **{key: value})))
            with self.subTest(key=key), self.assertRaises(ValueError):
                assets.staged_assets(self.legacy)

    def test_untrusted_receipt_uses_strict_duplicate_and_nonfinite_json(self):
        self.prepare()
        path = self.root / 'store-display-preparation.json'
        for raw in ('{"source_sha":"a","source_sha":"b"}', '{"elapsed":NaN}', '{"elapsed":Infinity}'):
            path.write_text(raw)
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                assets.staged_assets(self.legacy)

    def test_actual_zero_to_two_resource_receipt_includes_full_original_sha_and_bytes(self):
        initial, final = observed_library()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            receipt = assets.verify_library(initial, final)
        self.assertEqual(receipt['initial'], initial)
        self.assertEqual(receipt['final'], final)
        self.assertEqual(receipt['verified_asset_count'], 2)
        self.assertIs(receipt['old_six_fixture_claim'], False)
        self.assertEqual(json.loads((self.root / 'store-display-photos.json').read_text()), receipt)
        self.assertEqual(len(output.getvalue().splitlines()), 1)
        self.assertTrue(output.getvalue().startswith(assets.MARKER))
        self.assertNotIn('EXACT_SIX', output.getvalue())

    def test_readiness_requires_actually_empty_authorized_unmutated_library(self):
        initial, _ = observed_library()
        for key, value in (('asset_count', 1), ('asset_count', False), ('synthetic', [{}]),
                           ('authorization', 2), ('hash_resources', True), ('library_mutation', True)):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                assets.verify_initial(dict(initial, **{key: value}))

    def test_reconcile_rejects_foreign_unlisted_resource_or_wrong_count_and_flags(self):
        initial, final = observed_library()
        for key, value in (('asset_count', 3), ('asset_count', True), ('authorization', 2),
                           ('hash_resources', False), ('library_mutation', True),
                           ('synthetic', final['synthetic'][:1]), ('synthetic', final['synthetic'] + [{}])):
            with self.subTest(key=key), self.assertRaises(ValueError):
                assets.verify_library(initial, dict(final, **{key: value}))
        self.assertFalse((self.root / 'store-display-photos.json').exists())

    def test_each_actual_resource_requires_exact_filename_hash_bytes_size_and_unique_identifier(self):
        initial, final = observed_library()
        for key, value in (('filename', 'celluloid-fixture.png'), ('sha256', '0' * 64), ('bytes', 1),
                           ('bytes', True), ('width', 1206), ('height', 1206), ('identifier', ''),
                           ('identifier', final['synthetic'][1]['identifier']), ('identifier', 'x' * 201)):
            changed = copy.deepcopy(final)
            changed['synthetic'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                assets.verify_library(initial, changed)
        self.assertFalse((self.root / 'store-display-photos.json').exists())

    def test_spoofed_or_other_route_cannot_prepare_demo_assets(self):
        for changed in (dict(self.env, GITHUB_WORKFLOW_SHA='b' * 40), {},
                        dict(self.env, CELLULOID_VALIDATION_SCOPE='original-ios-release')):
            with self.subTest(environment=changed), patch.dict(os.environ, changed, clear=True), self.assertRaises((ValueError, guard.GuardRefusal)):
                self.prepare()
        self.assertFalse((self.root / 'store-display-assets').exists())

    def test_existing_failure_receipt_blocks_file_preparation(self):
        owner = guard.OwnedCommand('xcodebuild', 'test fence', 360)
        owner.started(MagicMock(pid=12345))
        owner.failed(TimeoutError('unconfirmed actual test command'), timed_out=True)
        with self.assertRaises(guard.GuardRefusal):
            self.prepare()
        self.assertFalse((self.root / 'store-display-assets').exists())


if __name__ == '__main__':
    unittest.main()
