#!/usr/bin/env python3
import struct, zlib
from pathlib import Path
width,height=640,480
raw=b''.join(b'\0'+b''.join(bytes((x*255//width,y*255//height,128)) for x in range(width)) for y in range(height))
def chunk(t,data):return struct.pack('>I',len(data))+t+data+struct.pack('>I',zlib.crc32(t+data)&0xffffffff)
Path('/tmp/celluloid-fixture.png').write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b''))

Path("/tmp/celluloid-fixture-2.png").write_bytes(b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",width,height,8,2,0,0,0))+chunk(b"IDAT",zlib.compress(b"".join(b"\0"+b"".join(bytes((128,x*255//width,y*255//height)) for x in range(width)) for y in range(height))))+chunk(b"IEND",b""))

# Distinct roles and asymmetric corners for source-identity/composition regression.
# Unique pixel dimensions identify these test assets without relying on date ties.
import hashlib
palette = [(235, 45, 40), (40, 200, 70), (30, 60, 230), (235, 190, 25)]
for role, color in enumerate(palette):
    w, h = 800 + role, 600
    rows = []
    for y in range(h):
        row = bytearray(b'\0')
        for x in range(w):
            pixel = (255, 255, 255) if x < 40 and y < 40 else (0, 0, 0) if x >= w - 30 and y >= h - 30 else color
            row.extend(pixel)
        rows.append(row)
    path = Path(f'/tmp/celluloid-composition-{role}.png')
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(b''.join(rows))) + chunk(b'IEND', b''))
for path in [Path('/tmp/celluloid-fixture.png'), Path('/tmp/celluloid-fixture-2.png')] + sorted(Path('/tmp').glob('celluloid-composition-*.png')):
    print('SYNTHETIC_FIXTURE', path.name, 'PNG_SHA256', hashlib.sha256(path.read_bytes()).hexdigest())
