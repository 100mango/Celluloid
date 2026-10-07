"""Bounded native PNG validation and lossless removal of an opaque alpha plane.

Never resize, crop, composite, or draw. Both the original and RGB output remain
available, with identical decoded RGB bytes and unchanged color-profile chunks.
"""
import hashlib
import struct
import zlib

LIMIT = 3 * 1024 * 1024
SIZES = ((1280, 800),)
SIGNATURE = b'\x89PNG\r\n\x1a\n'


def need(ok, reason):
    if not ok: raise ValueError(reason)


def chunk(kind, payload):
    return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload))


def decode(raw, *, tick=lambda: None):
    need(0 < len(raw) <= LIMIT and raw.startswith(SIGNATURE), 'native-png-byte-limit-or-signature')
    offset = 8; chunks = []; compressed = bytearray(); dimensions = None; seen_data = ended_data = False
    while offset < len(raw):
        tick(); need(len(chunks) < 256 and offset + 12 <= len(raw), 'png-chunk-limit-or-truncation')
        size = struct.unpack_from('>I', raw, offset)[0]; kind = raw[offset + 4:offset + 8]
        end = offset + 12 + size; need(end <= len(raw), 'png-chunk-truncated')
        data = raw[offset + 8:end - 4]
        need(all(65 <= x <= 90 or 97 <= x <= 122 for x in kind), 'png-chunk-type')
        need(zlib.crc32(kind + data) == struct.unpack_from('>I', raw, end - 4)[0], 'png-crc')
        need(kind not in (b'acTL', b'fcTL', b'fdAT', b'tRNS'), 'animated-or-transparent-png')
        need(kind in (b'IHDR', b'PLTE', b'IDAT', b'IEND') or kind[0] & 32, 'unknown-critical-png-chunk')
        if kind == b'IHDR':
            need(not chunks and size == 13, 'png-header-order')
            w, h, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', data)
            need((w, h) in SIZES and depth == 8 and color in (2, 6) and (compression, filtering, interlace) == (0, 0, 0), 'png-dimensions-or-format')
            dimensions = (w, h, color)
        elif kind == b'IDAT':
            need(dimensions is not None and not ended_data, 'png-data-order')
            seen_data = True; compressed.extend(data)
        elif seen_data:
            ended_data = True
        if kind == b'IEND':
            need(size == 0 and seen_data and end == len(raw), 'png-end')
        chunks.append((kind, data)); offset = end
    need(chunks and chunks[-1][0] == b'IEND', 'png-missing-end')
    w, h, color = dimensions; channels = 3 if color == 2 else 4; stride = w * channels
    expected = h * (stride + 1); inflater = zlib.decompressobj()
    decoded = inflater.decompress(bytes(compressed), expected + 1)
    need(len(decoded) == expected and inflater.eof and not inflater.unconsumed_tail and not inflater.unused_data, 'png-inflate-size-or-trailing-data')
    prior = bytearray(stride); rgb = bytearray()
    for y in range(h):
        tick(); start = y * (stride + 1); mode = decoded[start]; need(mode <= 4, 'png-filter')
        row = bytearray(decoded[start + 1:start + 1 + stride])
        if mode:
            for x in range(stride):
                a = row[x - channels] if x >= channels else 0; b = prior[x]; c = prior[x - channels] if x >= channels else 0
                if mode == 1: predictor = a
                elif mode == 2: predictor = b
                elif mode == 3: predictor = (a + b) // 2
                else:
                    p = a + b - c; pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                    predictor = a if pa <= pb and pa <= pc else b if pb <= pc else c
                row[x] = (row[x] + predictor) & 255
        if channels == 4:
            need(all(x == 255 for x in row[3::4]), 'native-png-has-transparent-pixels')
            rgb_row = bytearray(w * 3)
            for plane in range(3): rgb_row[plane::3] = row[plane::4]
            rgb.extend(rgb_row)
        else: rgb.extend(row)
        prior = row
    tick()
    return bytes(rgb), chunks, color


def store_copy(raw, *, tick=lambda: None):
    rgb, chunks, color = decode(raw, tick=tick)
    w, h = struct.unpack('>II', chunks[0][1][:8])
    if color == 2: output = raw
    else:
        payloads = []
        for kind, data in chunks:
            if kind in (b'IHDR', b'IDAT', b'IEND'): continue
            if kind == b'sBIT':
                need(len(data) == 4 and all(0 < x <= 8 for x in data), 'png-significant-bits')
                data = data[:3]
            payloads.append(chunk(kind, data))
        rows = b''.join(b'\0' + rgb[y*w*3:(y+1)*w*3] for y in range(h)); tick()
        output = (SIGNATURE + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) +
                  b''.join(payloads) + chunk(b'IDAT', zlib.compress(rows, 9)) + chunk(b'IEND', b''))
        actual, _, output_color = decode(output, tick=tick)
        need(actual == rgb and output_color == 2, 'rgb-pixels-changed')
    tick()
    return output, {'width': w, 'height': h, 'inputColorType': color, 'outputColorType': 2,
        'opaquePixelsOnly': True, 'rgbBytes': len(rgb), 'rgbSHA256': hashlib.sha256(rgb).hexdigest(),
        'transformation': 'none' if color == 2 else 'remove-fully-opaque-alpha-only',
        'resized': False, 'cropped': False, 'composited': False}
