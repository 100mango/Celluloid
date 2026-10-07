"""Two exact nonshipping demo PNGs; file preparation and actual PhotoKit proof."""
from pathlib import Path
import hashlib
import json
import os
import struct
import tempfile

from mac_host_transport import load_json

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_SHA = 'b57f68853fae5c8154ca8f79e2a2dc6ff1a253790f28ead9386a611de14a0061'
ASSETS = (
    {'filename': 'demo-coast-sunny.png', 'staged_filename': 'celluloid-fixture-store-coast.png',
     'bytes': 2997725, 'sha256': '505e1348a049a9f88cf86b4fb936702b45323f5d411ebce8f0a3415150fedcda',
     'format': 'PNG', 'width': 1254, 'height': 1254, 'color_mode': 'RGB'},
    {'filename': 'demo-citrus-sunny.png', 'staged_filename': 'celluloid-fixture-store-citrus.png',
     'bytes': 2880485, 'sha256': 'cd4c5178d550003b452b75904caba58a72c6eadc4658a083469c7684b4c00b03',
     'format': 'PNG', 'width': 1254, 'height': 1254, 'color_mode': 'RGB'},
)
MARKER = 'STORE_DISPLAY_TWO_ASSETS_VERIFIED '


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.' + path.name, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def capture_context():
    from original_ios_process_guard import require_clear
    from validation_route import STORE_SCREENSHOTS
    context = require_clear()
    need(context is not None and context.get('validation_route') == STORE_SCREENSHOTS,
         'Demo assets require the actual fixed Store capture context')
    return context


def is_capture():
    from original_ios_process_guard import staged_context
    from validation_route import STORE_SCREENSHOTS
    context = staged_context()
    return context is not None and context.get('validation_route') == STORE_SCREENSHOTS


def verify_sources(root=ROOT):
    folder = Path(root) / 'StoreCaptureAssets'
    need(folder.is_dir() and not folder.is_symlink(), 'Missing fixed demo asset directory')
    need({p.name for p in folder.iterdir()} == {a['filename'] for a in ASSETS} | {'manifest.json', 'README.md'},
         'Unexpected public demo files')
    manifest_path = folder / 'manifest.json'
    need(manifest_path.is_file() and not manifest_path.is_symlink() and manifest_path.stat().st_size <= 10_000,
         'Unsafe demo manifest')
    raw = manifest_path.read_bytes()
    need(sha(raw) == MANIFEST_SHA, 'Changed fixed demo manifest bytes')
    manifest = load_json(raw)
    need(manifest.get('schema') == 'Celluloid.StoreDisplayAssets.1' and manifest.get('assets') == list(ASSETS),
         'Changed fixed demo manifest')
    for asset in ASSETS:
        path = folder / asset['filename']
        need(path.is_file() and not path.is_symlink() and path.stat().st_size == asset['bytes'], 'Wrong demo asset bytes/size')
        data = path.read_bytes()
        need(sha(data) == asset['sha256'], 'Wrong original demo PNG hash')
        need(data.startswith(b'\x89PNG\r\n\x1a\n') and struct.unpack('>IIBBBBB', data[16:29]) == (1254, 1254, 8, 2, 0, 0, 0),
             'Unexpected original demo PNG header')
    return manifest


def no_legacy_files(legacy_root=Path('/tmp')):
    legacy_root = Path(legacy_root)
    paths = [legacy_root / 'celluloid-fixture.png', legacy_root / 'celluloid-fixture-2.png']
    paths += list(legacy_root.glob('celluloid-composition-*.png'))
    need(not any(p.exists() or p.is_symlink() for p in paths), 'Legacy six-fixture paths must not mix with demo capture')


def prepare(root=ROOT, legacy_root=Path('/tmp')):
    context = capture_context()
    verify_sources(root)
    no_legacy_files(legacy_root)
    row_root = Path(os.environ['RUNNER_TEMP'])
    need(row_root.is_dir() and not row_root.is_symlink(), 'Unsafe capture row directory')
    folder = row_root / 'store-display-assets'
    folder.mkdir()
    for asset in ASSETS:
        data = (Path(root) / 'StoreCaptureAssets' / asset['filename']).read_bytes()
        with (folder / asset['staged_filename']).open('xb') as target:
            target.write(data)
        need(sha((folder / asset['staged_filename']).read_bytes()) == asset['sha256'], 'Staged sample differs from original')
    receipt = {'schema': 'Celluloid.StoreDisplayPreparation.1', **context,
               'assets': list(ASSETS), 'directory': str(folder.resolve()), 'original_bytes_preserved': True,
               'picker_order_promised': False}
    write_json(row_root / 'store-display-preparation.json', receipt)
    return receipt


def staged_assets(legacy_root=Path('/tmp')):
    context = capture_context()
    no_legacy_files(legacy_root)
    row_root = Path(os.environ['RUNNER_TEMP'])
    path = row_root / 'store-display-preparation.json'
    need(path.is_file() and not path.is_symlink() and path.stat().st_size <= 20_000, 'Missing bounded demo preparation receipt')
    receipt = load_json(path.read_bytes())
    need(receipt.get('schema') == 'Celluloid.StoreDisplayPreparation.1'
         and all(receipt.get(k) == v for k, v in context.items()) and receipt.get('assets') == list(ASSETS)
         and receipt.get('original_bytes_preserved') is True and receipt.get('picker_order_promised') is False,
         'Demo preparation context/assets changed')
    folder = row_root / 'store-display-assets'
    need(folder.is_dir() and not folder.is_symlink() and receipt.get('directory') == str(folder.resolve()),
         'Unowned staged demo directory')
    need({p.name for p in folder.iterdir()} == {a['staged_filename'] for a in ASSETS}, 'Unexpected staged image membership')
    paths = []
    for asset in ASSETS:
        path = folder / asset['staged_filename']
        need(path.is_file() and not path.is_symlink() and path.stat().st_size == asset['bytes']
             and sha(path.read_bytes()) == asset['sha256'], 'Staged original image changed')
        paths.append(path)
    return paths


def verify_initial(initial):
    need(type(initial.get('asset_count')) is int and initial['asset_count'] == 0
         and initial.get('synthetic') == [] and initial.get('authorization') == 3
         and initial.get('hash_resources') is False and initial.get('library_mutation') is False,
         'Store display requires an actually empty, authorized Photos library')


def verify_library(initial, final):
    context = capture_context()
    verify_initial(initial)
    need(type(final.get('asset_count')) is int and final['asset_count'] == 2
         and final.get('authorization') == 3 and final.get('hash_resources') is True
         and final.get('library_mutation') is False, 'Store display must contain only two actual approved Photos resources')
    rows = final.get('synthetic')
    need(type(rows) is list and len(rows) == 2 and all(type(r) is dict for r in rows), 'Missing actual sample resource records')
    need({r.get('filename') for r in rows} == {a['staged_filename'] for a in ASSETS}, 'Foreign/missing sample filename')
    identifiers = []
    for asset in ASSETS:
        matches = [r for r in rows if r.get('filename') == asset['staged_filename']]
        need(len(matches) == 1, 'Ambiguous actual sample resource')
        row = matches[0]
        need(row.get('sha256') == asset['sha256'] and type(row.get('bytes')) is int and row['bytes'] == asset['bytes']
             and type(row.get('width')) is int and row['width'] == 1254
             and type(row.get('height')) is int and row['height'] == 1254, 'Actual PhotoKit resource differs from approved original PNG')
        need(type(row.get('identifier')) is str and 0 < len(row['identifier']) <= 200, 'Missing bounded actual Photos identity')
        identifiers.append(row['identifier'])
    need(len(set(identifiers)) == 2, 'Reused Photos identity')
    receipt = {'schema': 'Celluloid.StoreDisplayPhotos.1', **context, 'initial': initial, 'final': final,
               'verified_asset_count': 2, 'picker_order_promised': False,
               'source_assets': list(ASSETS), 'old_six_fixture_claim': False}
    write_json(Path(os.environ['RUNNER_TEMP']) / 'store-display-photos.json', receipt)
    print(MARKER + json.dumps(receipt, sort_keys=True, allow_nan=False), flush=True)
    return receipt
