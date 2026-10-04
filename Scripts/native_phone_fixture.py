"""Synthetic CI-only inbox seeding. Not bundled or called by any product target."""
from pathlib import Path
import hashlib
import json
import struct
import zlib

REQUEST_IDS = ['58B78AAA-30B8-44DB-BD4F-10762900A001', '58B78AAA-30B8-44DB-BD4F-10762900A002']


def seed(container: Path, temporary: Path, *, namespace=None):
    if namespace not in (None, "large-text"): raise ValueError("Unknown synthetic fixture namespace")
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    width, height = 1200, 800
    colors = [(240, 40, 30, 255), (30, 210, 70, 255), (25, 80, 235, 255)]
    row = b''.join(bytes(colors[min(2, x * 3 // width)]) for x in range(width))
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)) + chunk(b'sRGB', b'\0') + chunk(b'IDAT', zlib.compress((b'\0' + row) * height)) + chunk(b'IEND', b'')
    digest = hashlib.sha256(png).hexdigest()
    root = container / 'Library/Application Support' / ('WatchProcessingLargeTextUI' if namespace == 'large-text' else 'WatchProcessingResults')
    if root.exists() and any(root.iterdir()):
        raise ValueError('Synthetic seeding may not overwrite an existing processing store')
    pending = root / 'Pending'
    pending.mkdir(parents=True, exist_ok=False)
    for index, identifier in enumerate(REQUEST_IDS):
        job = pending / identifier
        job.mkdir()
        request = {'version': 1, 'id': identifier, 'sourceID': f'58B78AAA-30B8-44DB-BD4F-10762900B00{index + 1}',
                   'sourceSHA256': digest, 'sourceBytes': len(png), 'filter': 'Fade'}
        (job / 'request.json').write_text(json.dumps(request, sort_keys=True))
        (job / 'source.image').write_bytes(png)
    fixture = temporary / 'PhoneCompanionSynthetic.png'
    fixture.write_bytes(png)
    return {'scope': 'Synthetic app-owned durable inbox; no WatchConnectivity delivery',
            'namespace': namespace or 'canonical-output', 'request_ids': REQUEST_IDS, 'source_sha256': digest, 'source_bytes': len(png), 'fixture': str(fixture)}
