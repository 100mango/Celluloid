"""Portable negative admission tests; no native/display/network operation."""
import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import mac_store_contract as contract
import mac_store_png as png_contract
import mac_store_raw as raw_contract
from test_mac_store_capture import encoded, exported
from test_mac_store_png import png


class RawTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = Path('/virtual/build/mac-tests/Build/Products/Debug/CelluloidMac.app')
        cls.product = {'applicationPath':str(app),'executable':str(app / 'Contents/MacOS/CelluloidMac'),
                       'executableSHA256':'c' * 64,'logicSHA256':'d' * 64}
        cls.original_summary, cls.original_files = exported(100, cls.product)

    def setUp(self):
        for target in ('subprocess.Popen','os.system','socket.create_connection','socket.socket.connect'):
            guard = patch(target, side_effect=AssertionError('native/network operation forbidden'))
            guard.start()
            self.addCleanup(guard.stop)
        self.summary = copy.deepcopy(self.original_summary)
        self.files = dict(self.original_files)
        self.test = {'returncode':0,'started_epoch':100,'finished_epoch':102}

    def collect(self, *, tick=lambda: None, read=None, root=Path('/virtual'), product=None):
        def virtual(path, limit):
            return self.files[path.name]
        return raw_contract.collect_raw(root, encoded(self.summary), product or self.product, self.test,
                                        tick=tick, read=virtual if read is None else read)

    def manifest(self):
        return json.loads(self.files['manifest.json'])

    def update_manifest(self, change):
        value = self.manifest()
        change(value)
        self.files['manifest.json'] = encoded(value)

    def filename(self, prefix):
        return next(x['exportedFileName'] for x in self.manifest()[0]['attachments']
                    if x['suggestedHumanReadableName'].startswith('Native Mac Store ' + prefix + '_'))

    def change_receipt(self, prefix, **changes):
        name = self.filename(prefix)
        row = json.loads(self.files[name])
        row.update(changes)
        self.files[name] = encoded(row)

    def change_png(self, value, state='citrus'):
        name = self.filename('window ' + state)
        self.files[name] = value
        self.change_receipt('proof ' + state, pngBytes=len(value), pngSHA256=contract.digest(value))

    def materialize(self, root):
        root.mkdir(parents=True, exist_ok=True)
        for name, value in self.files.items():
            (root / name).write_bytes(value)

    def physical(self, root, **kwargs):
        return raw_contract.collect_raw(root, encoded(self.summary), self.product, self.test, **kwargs)

    def test_original_bytes_hashes_bounded_metadata_and_offline_replay(self):
        metadata, files = self.collect()
        self.assertEqual(set(metadata), {'status','visual_pending','files','exportedNames'})
        self.assertEqual(metadata['status'], 'unqualified')
        self.assertIs(metadata['visual_pending'], True)
        self.assertEqual(set(files), set(raw_contract.RAW_LIMITS))
        for name, data in files.items():
            self.assertEqual(data, self.files[metadata['exportedNames'][name]])
            self.assertEqual(metadata['files'][name], {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
            self.assertLessEqual(len(data), raw_contract.RAW_LIMITS[name])
        reverse = {source:files[name] for name, source in metadata['exportedNames'].items()}
        replay = self.collect(read=lambda path, limit:reverse[path.name])
        self.assertEqual(replay, (metadata,files))

    def test_fixed_caps_and_no_store_copy(self):
        self.assertEqual(raw_contract.RAW_LIMITS, {
            'raw-manifest.json':512 * 1024,'raw-proof-citrus.json':4096,'raw-proof-coast.json':4096,
            'raw-display-setup.json':16 * 1024,'raw-display-restore.json':16 * 1024,
            'native-citrus.png':3 * 1024 * 1024,'native-coast.png':3 * 1024 * 1024})
        with patch.object(png_contract, 'decode', side_effect=AssertionError('raw admission must not decode')):
            _, files = self.collect()
        self.assertFalse(any(name.startswith('store-') for name in files))

    def test_case_name_and_attachment_clock_discrepancy_retains_exact_bytes(self):
        self.change_receipt('proof citrus', test='-[NativeEditorUITests testStoreOriginalDocumentScreenshots]', captured=104)
        self.change_receipt('display setup', test='-[NativeEditorUITests anotherObservedName]', finished=104)
        self.update_manifest(lambda groups:groups[0]['attachments'][0].update(timestamp=99))
        metadata, files = self.collect()
        self.assertEqual(files['native-citrus.png'], self.files[self.filename('window citrus')])
        self.assertEqual(files['raw-display-setup.json'], self.files[self.filename('display setup')])
        with self.assertRaises(ValueError):
            contract.validate_capture(Path('/virtual'), encoded(self.summary), self.product, self.test,
                                      read=lambda path, limit:self.files[path.name])
        self.assertEqual(metadata['status'], 'unqualified')

    def test_pid_state_clock_and_restore_semantics_do_not_qualify_raw(self):
        self.change_receipt('proof coast', pid=999, started=110, captured=99)
        self.change_receipt('display restore', restored=True, started=90, finished=80, configurationResult=1001,
                            setupSHA256='f' * 64, after={})
        metadata, files = self.collect()
        self.assertEqual(metadata['status'], 'unqualified')
        self.assertEqual(json.loads(files['raw-proof-coast.json'])['pid'], 999)
        self.assertEqual(json.loads(files['raw-display-restore.json'])['after'], {})

    def test_transparent_original_rgba_is_retained_unchanged(self):
        original = png(alpha=31)
        self.change_png(original)
        metadata, files = self.collect()
        self.assertEqual(files['native-citrus.png'], original)
        self.assertEqual(metadata['files']['native-citrus.png']['sha256'], contract.digest(original))
        with self.assertRaisesRegex(ValueError, 'transparent-pixels'):
            png_contract.store_copy(original)

    def test_rgb_and_distinct_safe_suggested_exported_guids(self):
        self.change_png(png(rgba=False))
        self.update_manifest(lambda groups:groups[0]['attachments'][0].update(
            suggestedHumanReadableName='Native Mac Store window citrus_1_AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE.png'))
        self.collect()

    def test_restore_receipt_is_optional_only(self):
        self.update_manifest(lambda groups:groups[0]['attachments'].pop())
        metadata, files = self.collect()
        self.assertNotIn('raw-display-restore.json', files)
        self.assertNotIn('raw-display-restore.json', metadata['exportedNames'])
        self.assertEqual(len(files), 6)

    def test_wrong_case_url_extra_group_or_manifest_fields_rejected(self):
        changes = [lambda g:g[0].update(testIdentifier='Other/testPrivate()'),
                   lambda g:g[0].update(testIdentifierURL=g[0]['testIdentifierURL'].replace('CelluloidNative','PrivateApp')),
                   lambda g:g.append(copy.deepcopy(g[0])), lambda g:g[0].update(private='not allowed')]
        for change in changes:
            self.files = dict(self.original_files)
            self.update_manifest(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.collect()

    def test_wrong_additional_duplicate_or_missing_attachment_rejected(self):
        changes = [lambda a:a.append(copy.deepcopy(a[0])), lambda a:a.pop(0),
                   lambda a:a.__setitem__(1, copy.deepcopy(a[0])),
                   lambda a:a[0].update(suggestedHumanReadableName='My private screenshot_0_00000000-0000-4000-8000-000000000001.png'),
                   lambda a:a[0].update(private='not allowed'),
                   lambda a:a[1].update(exportedFileName=a[4]['exportedFileName']),
                   lambda a:a[0].update(exportedFileName='00000000-0000-4000-8000-000000000001.txt'),
                   lambda a:a[0].update(exportedFileName='../../private.png'),
                   lambda a:a[0].update(exportedFileName='------------------------------------.png'),
                   lambda a:a[0].update(deviceId='another-device'),
                   lambda a:a[0].update(configurationName='Another configuration'),
                   lambda a:a[0].update(isAssociatedWithFailure=True)]
        for change in changes:
            self.files = dict(self.original_files)
            self.update_manifest(lambda g:change(g[0]['attachments']))
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.collect()

    def test_missing_exported_payload_rejected(self):
        for name in self.original_files:
            self.files = dict(self.original_files)
            del self.files[name]
            with self.subTest(name=name), self.assertRaises((KeyError,ValueError)):
                self.collect()

    def test_source_private_filename_hash_dimensions_and_product_mismatch(self):
        changes = [('sourceFilename','private-family-photo.png'),('sourceSHA256','e' * 64),('sourceBytes',3),
                   ('sourceBytes',2880485.0),('sourceDimensions',[1254.0,1254]),('sourceDimensions',[1,1]),
                   ('bundle','Other.Celluloid'),('applicationPath','/private/CelluloidMac.app'),
                   ('expectedPath','/private/CelluloidMac.app'),('executable','/private/CelluloidMac'),
                   ('executableSHA256','e' * 64),('logicSHA256','e' * 64),
                   ('imageName','Native Mac Store window coast'),('pngSHA256','e' * 64),('pngBytes',10)]
        for key, value in changes:
            self.files = dict(self.original_files)
            self.change_receipt('proof citrus', **{key:value})
            with self.subTest(key=key,value=value), self.assertRaises(ValueError):
                self.collect()

    def test_product_argument_cannot_broaden_capture_scope(self):
        for changes in ({'applicationPath':'/private/Celluloid.app'}, {'logicSHA256':'x' * 64}, {'extra':'private'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.collect(product=self.product | changes)

    def test_exact_receipt_schemas_reject_extra_missing_nested_and_duplicate_fields(self):
        for prefix in ('proof citrus','proof coast','display setup','display restore'):
            for mutation in ('extra','missing','duplicate','array','invalid-json'):
                self.files = dict(self.original_files)
                filename = self.filename(prefix)
                row = json.loads(self.files[filename])
                if mutation == 'extra':
                    row['private'] = 'not allowed'
                elif mutation == 'missing':
                    row.pop('test')
                elif mutation == 'array':
                    row = [row]
                self.files[filename] = encoded(row)
                if mutation == 'duplicate':
                    self.files[filename] = self.files[filename][:-1] + b',"v":1}'
                elif mutation == 'invalid-json':
                    self.files[filename] = b'not JSON'
                with self.subTest(prefix=prefix,mutation=mutation), self.assertRaises(ValueError):
                    self.collect()
        for prefix in ('display setup','display restore'):
            self.files = dict(self.original_files)
            name = self.filename(prefix)
            row = json.loads(self.files[name])
            row['after']['private'] = 'not allowed'
            self.files[name] = encoded(row)
            with self.subTest(prefix=prefix), self.assertRaises(ValueError):
                self.collect()

    def test_bounded_scalar_and_array_values_rejected(self):
        for prefix, key, value in [
            ('proof citrus','test','x' * 257),('proof citrus','test','secret\ntext'),
            ('proof citrus','pid',True),('proof citrus','pid',2**40),('proof citrus','token','bad'),
            ('proof citrus','started',-1),('proof citrus','captured',1e100),('proof citrus','captured',float('inf')),
            ('proof citrus','args',contract.ARGS + ['private']),('proof citrus','width',1280.0),
            ('proof citrus','windowFrame',[0,0,1e9,800]),('proof citrus','visibleFrameAX',[0,0,1280]),
            ('proof citrus','filter','x' * 65),('proof citrus','layerCount',2**40),
            ('display setup','activeDisplays',list(range(1,10))),('display setup','availableModes',[{}] * 129),
            ('display setup','availableModeCount',129),('display setup','requestedWindowPoints',[True,800]),
            ('display setup','configurationResult',2**40),('display setup','finished',float('nan')),
            ('display restore','setupSHA256','bad'),('display restore','restored',1)]:
            self.files = dict(self.original_files)
            self.change_receipt(prefix, **{key:value})
            with self.subTest(prefix=prefix,key=key), self.assertRaises(ValueError):
                self.collect()
        for value in (True,-1,2**50,float('inf')):
            self.files = dict(self.original_files)
            self.update_manifest(lambda g:g[0]['attachments'][0].update(timestamp=value))
            with self.subTest(timestamp=value), self.assertRaises(ValueError):
                self.collect()

    def test_receipt_and_manifest_byte_limits_even_with_injected_reader(self):
        for prefix, cap in [('proof citrus',4096),('display setup',16 * 1024),('display restore',16 * 1024)]:
            self.files = dict(self.original_files)
            name = self.filename(prefix)
            self.files[name] += b' ' * (cap + 1)
            with self.subTest(prefix=prefix), self.assertRaisesRegex(ValueError, 'byte-limit'):
                self.collect()
        self.files = dict(self.original_files)
        self.files['manifest.json'] += b' ' * (512 * 1024)
        with self.assertRaisesRegex(ValueError, 'byte-limit'):
            self.collect()

    def test_unpassed_or_foreign_summary_never_retains_bytes(self):
        changes = [{'passedTests':0,'failedTests':1,'result':'Failed'}, {'totalTestCount':2},
                   {'startTime':90}, {'devicesAndConfigurations':[]}]
        for change in changes:
            self.summary = copy.deepcopy(self.original_summary)
            self.summary.update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.collect(read=lambda *a:self.fail('rejected summary must not read exports'))

    def test_png_magic_geometry_color_type_depth_crc_and_size_rejected(self):
        original = self.files[self.filename('window citrus')]
        corrupt = bytearray(original)
        corrupt[20] ^= 1
        def header(width=1280,height=800,depth=8,color=6):
            return (png_contract.SIGNATURE + png_contract.chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,depth,color,0,0,0)) +
                    original[33:])
        for value in [b'private arbitrary text',header(width=1281),header(height=801),header(depth=16),
                      header(color=0),bytes(corrupt),original[:-1],original + b'x',
                      original + b'x' * (3 * 1024 * 1024)]:
            self.files = dict(self.original_files)
            self.change_png(value)
            with self.subTest(size=len(value),start=value[:20]), self.assertRaises(ValueError):
                self.collect()

    def test_png_chunk_types_counts_apng_order_and_sizes_rejected(self):
        original = self.files[self.filename('window citrus')]
        header = original[:33]
        ending = png_contract.chunk(b'IEND',b'')
        values = [header + png_contract.chunk(kind,b'') + original[33:]
                  for kind in (b'acTL',b'fcTL',b'fdAT',b'ABCD',b'12ab',b'aaab')]
        values += [header + png_contract.chunk(b'aaAb',b'') * 256 + original[33:],
                   header + header[8:] + original[33:], header + ending,
                   original[:-12] + png_contract.chunk(b'aaAb',b'') + png_contract.chunk(b'IDAT',b'x') + ending,
                   original[:-12] + png_contract.chunk(b'IEND',b'x'),
                   header + png_contract.chunk(b'PLTE',b'ab') + original[33:],
                   header + png_contract.chunk(b'tRNS',b'123456') + original[33:],
                   header + png_contract.chunk(b'pHYs',b'') + original[33:]]
        for value in values:
            self.files = dict(self.original_files)
            self.change_png(value)
            with self.subTest(size=len(value)), self.assertRaises(ValueError):
                self.collect()

    def test_deadline_subclass_propagates_before_reads_and_inside_png(self):
        class Deadline(ValueError):
            pass
        def expired():
            raise Deadline('original deadline')
        with self.assertRaises(Deadline):
            self.collect(tick=expired, read=lambda *a:self.fail('expired before reads'))
        count = [0]
        def later():
            count[0] += 1
            if count[0] == 29:
                raise Deadline('original deadline')
        with self.assertRaises(Deadline):
            self.collect(tick=later)
        self.assertEqual(count[0], 29)

    def test_default_reader_preserves_bytes_and_rejects_file_symlink_hardlink(self):
        for link in ('symlink','hardlink'):
            with self.subTest(link=link), tempfile.TemporaryDirectory() as directory:
                base = Path(directory).resolve()
                root = base / 'exports'
                self.materialize(root)
                self.assertEqual(self.physical(root), self.collect())
                name = self.filename('window citrus')
                target = base / 'original.png'
                (root / name).rename(target)
                if link == 'symlink':
                    (root / name).symlink_to(target)
                else:
                    os.link(target,root / name)
                with self.assertRaises((ValueError,OSError)):
                    self.physical(root)

    def test_default_reader_rejects_symlinked_ancestor_and_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            self.materialize(base / 'actual' / 'exports')
            (base / 'alias').symlink_to(base / 'actual', target_is_directory=True)
            with self.assertRaises((ValueError,OSError)):
                self.physical(base / 'alias' / 'exports')
            with self.assertRaisesRegex(ValueError, 'unsafe-path'):
                self.physical(base / 'actual' / '..' / 'actual' / 'exports')

    def test_changed_read_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self.materialize(root)
            original_read = os.read
            changed = [False]
            def mutate(fd, size):
                value = original_read(fd, size)
                if value and not changed[0]:
                    changed[0] = True
                    path = root / 'manifest.json'
                    path.write_bytes(path.read_bytes() + b' ')
                return value
            with patch.object(raw_contract.os, 'read', side_effect=mutate), self.assertRaisesRegex(ValueError, 'changed-during-read'):
                self.physical(root)

    def test_ancestor_replacement_during_read_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            root = base / 'exports'
            self.materialize(root)
            original_read = os.read
            changed = [False]
            def mutate(fd, size):
                value = original_read(fd, size)
                if value and not changed[0]:
                    changed[0] = True
                    root.rename(base / 'moved')
                    root.mkdir()
                return value
            with patch.object(raw_contract.os, 'read', side_effect=mutate), self.assertRaisesRegex(ValueError, 'ancestor-changed-during-read'):
                self.physical(root)


if __name__ == '__main__':
    unittest.main()
