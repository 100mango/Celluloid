"""Bounded, unqualified retention of the fixed two-document native capture.

This is admission of original forensic bytes, never capture/Store qualification.
It deliberately does not compare receipt case names, clocks, PIDs or display
restoration facts. The normal proof validator must still make those decisions.
An injected reader is a trusted bounded byte provider for offline replay; the
default filesystem route pins no-follow directory/file descriptors throughout.
"""
import hashlib
import math
import os
from pathlib import Path
import re
import stat
import struct
import uuid
import zlib

from mac_store_contract import ARGS, CASE, STATES, summary_admission
from mac_store_io import read_file, strict_json
from mac_store_png import SIGNATURE

RAW_LIMITS = {
    'raw-manifest.json': 512 * 1024,
    'raw-proof-citrus.json': 4096,
    'raw-proof-coast.json': 4096,
    'raw-display-setup.json': 16 * 1024,
    'raw-display-restore.json': 16 * 1024,
    'native-citrus.png': 3 * 1024 * 1024,
    'native-coast.png': 3 * 1024 * 1024,
}
PROOF_FIELDS = {
    'v','state','token','pid','test','started','captured','sequential','args','sandbox','bundle','applicationPath',
    'expectedPath','executable','executableSHA256','logicSHA256','imageName','pngSHA256','pngBytes','width','height',
    'windowFrame','sourceFilename','sourceSHA256','sourceBytes','sourceDimensions','documentDimensions','filter',
    'layerCount','backingScale','visibleFrameAX','displaySetupSHA256',
}
SETUP_FIELDS = {
    'v','test','token','runnerPID','display','started','scope','requestedWindowPoints','changed','status',
    'activeDisplays','before','availableModeCount','availableModes','selected','configurationResult','after','finished',
}
RESTORE_FIELDS = {
    'v','test','runnerPID','display','scope','started','finished','setupSHA256','changed',
    'configurationResult','original','after','restored',
}
MODE_FIELDS = {'id','width','height','pixelWidth','pixelHeight','usable'}
SNAPSHOT_FIELDS = {'display','mode','frame','visibleFrame','cgBounds','scale'}
ATTACHMENT_FIELDS = {
    'configurationName','deviceId','deviceName','exportedFileName','isAssociatedWithFailure',
    'suggestedHumanReadableName','timestamp',
}
PRODUCT_FIELDS = {'applicationPath','executable','executableSHA256','logicSHA256'}
GUID = r'[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}'


def need(value, reason):
    if not value:
        raise ValueError('raw-' + reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def integer(value, low=0, high=2**32 - 1):
    return type(value) is int and low <= value <= high


def number(value, low=0, high=2**40):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def text(value, limit):
    return isinstance(value, str) and 0 < len(value) <= limit and all(ord(c) >= 32 and ord(c) != 127 for c in value)


def sha(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def token(value):
    return isinstance(value, str) and re.fullmatch(GUID, value) is not None and str(uuid.UUID(value)).upper() == value


def fields(value, expected, reason):
    need(isinstance(value, dict) and set(value) == expected, reason)


def object_json(raw):
    value = strict_json(raw.decode('utf-8'))
    need(isinstance(value, dict), 'receipt-object')
    return value


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _filesystem_read(path, limit, tick):
    """Pin each ancestor and reject replacements, links, and growing reads."""
    path = Path(path)
    need('..' not in path.parts, 'unsafe-path')
    path = path.absolute()
    opened = []
    ancestors = []
    try:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        parent = os.open(path.anchor, flags)
        opened.append(parent)
        for name in path.parts[1:-1]:
            tick()
            child = os.open(name, flags, dir_fd=parent)
            opened.append(child)
            info = os.fstat(child)
            ancestors.append((parent, name, info.st_dev, info.st_ino, info.st_mode))
            parent = child
        tick()
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        opened.append(fd)
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 <= before.st_size <= limit,
             'unsafe-or-oversized-file')
        parts = []
        size = 0
        while True:
            tick()
            part = os.read(fd, min(65536, limit + 1 - size))
            if not part:
                break
            size += len(part)
            need(size <= limit, 'file-byte-limit')
            parts.append(part)
        need(_identity(before) == _identity(os.fstat(fd)) ==
             _identity(os.stat(path.name, dir_fd=parent, follow_symlinks=False)) and size == before.st_size,
             'file-changed-during-read')
        for directory, name, device, inode, mode in ancestors:
            info = os.stat(name, dir_fd=directory, follow_symlinks=False)
            need((info.st_dev, info.st_ino, info.st_mode) == (device, inode, mode), 'ancestor-changed-during-read')
        return b''.join(parts)
    finally:
        for fd in reversed(opened):
            os.close(fd)


def _read(path, limit, read, tick):
    tick()
    raw = _filesystem_read(path, limit, tick) if read is read_file else read(path, limit)
    need(type(raw) is bytes and 0 < len(raw) <= limit, 'file-byte-limit')
    tick()
    return raw


def _rect(value):
    need(isinstance(value, list) and len(value) == 4 and
         all(number(x, -32768, 32768) for x in value) and value[2] > 0 and value[3] > 0,
         'rectangle-fields')


def _mode(value):
    fields(value, MODE_FIELDS, 'mode-fields')
    need(integer(value['id'], -2**31, 2**31 - 1) and
         all(integer(value[k], 1, 32768) for k in ('width','height','pixelWidth','pixelHeight')) and
         type(value['usable']) is bool, 'mode-values')


def _snapshot(value, *, empty=False):
    if empty and value == {}:
        return
    fields(value, SNAPSHOT_FIELDS, 'snapshot-fields')
    need(integer(value['display'], 1) and number(value['scale'], .01, 4), 'snapshot-values')
    _mode(value['mode'])
    for key in ('frame','visibleFrame','cgBounds'):
        _rect(value[key])


def _display(raw, suffix):
    row = object_json(raw)
    fields(row, SETUP_FIELDS if suffix == 'setup' else RESTORE_FIELDS, 'display-fields')
    need(type(row['v']) is int and row['v'] == 1 and text(row['test'], 256) and
         integer(row['runnerPID'], 1, 2**31 - 1) and integer(row['display'], 1) and
         row['scope'] == 'forAppOnly' and type(row['changed']) is bool and
         integer(row['configurationResult'], -2**31, 2**31 - 1) and
         all(number(row[k]) for k in ('started','finished')), 'display-values')
    if suffix == 'setup':
        need(token(row['token']) and row['status'] == 'ready' and row['requestedWindowPoints'] == [1280,800] and
             all(type(x) is int for x in row['requestedWindowPoints']), 'display-setup-values')
        active = row['activeDisplays']
        need(isinstance(active, list) and 1 <= len(active) <= 8 and all(integer(x, 1) for x in active),
             'display-active-bound')
        modes = row['availableModes']
        need(isinstance(modes, list) and 1 <= len(modes) <= 128 and integer(row['availableModeCount'], 1, 128),
             'display-mode-bound')
        for value in modes:
            _mode(value)
        _mode(row['selected'])
        _snapshot(row['before'])
        _snapshot(row['after'])
    else:
        need(sha(row['setupSHA256']) and type(row['restored']) is bool, 'display-restore-values')
        _mode(row['original'])
        _snapshot(row['after'], empty=True)
    return row


def _proof(raw, state, product):
    row = object_json(raw)
    fields(row, PROOF_FIELDS, 'proof-fields')
    need(type(row['v']) is int and row['v'] == 1 and row['state'] == state and token(row['token']) and
         integer(row['pid'], 1, 2**31 - 1) and text(row['test'], 256) and
         type(row['sequential']) is bool and type(row['sandbox']) is bool and row['args'] == ARGS and
         all(number(row[k]) for k in ('started','captured')), 'proof-values')
    need(all(row[k] == product[k] for k in PRODUCT_FIELDS) and row['expectedPath'] == product['applicationPath'] and
         row['bundle'] == 'Mango.Celluloid', 'proof-product')
    source = STATES[state]
    need(all(row[k] == source[k] for k in ('sourceFilename','sourceSHA256','sourceBytes','sourceDimensions')) and
         type(row['sourceBytes']) is int and isinstance(row['sourceDimensions'], list) and
         all(type(x) is int for x in row['sourceDimensions']), 'proof-source')
    need(row['imageName'] == 'Native Mac Store window ' + state and sha(row['pngSHA256']) and
         integer(row['pngBytes'], 1, RAW_LIMITS['native-' + state + '.png']) and
         type(row['width']) is int and type(row['height']) is int and (row['width'],row['height']) == (1280,800),
         'proof-image-fields')
    need(text(row['documentDimensions'], 64) and text(row['filter'], 64) and integer(row['layerCount'], 0, 1000000) and
         number(row['backingScale'], .01, 4) and sha(row['displaySetupSHA256']), 'proof-state-fields')
    _rect(row['windowFrame'])
    _rect(row['visibleFrameAX'])
    return row


def _png(raw, tick):
    """Structural inspection only. No decoding, alpha inspection or mutation."""
    need(raw.startswith(SIGNATURE), 'png-signature')
    offset = len(SIGNATURE)
    count = 0
    seen = set()
    data_bytes = 0
    ended_data = False
    color = None
    while offset < len(raw):
        tick()
        count += 1
        need(count <= 256 and offset + 12 <= len(raw), 'png-chunk-limit-or-truncation')
        size = struct.unpack_from('>I', raw, offset)[0]
        kind = raw[offset + 4:offset + 8]
        end = offset + size + 12
        need(end <= len(raw), 'png-chunk-truncated')
        need(all(65 <= x <= 90 or 97 <= x <= 122 for x in kind) and not kind[2] & 32, 'png-chunk-type')
        data = raw[offset + 8:end - 4]
        need(zlib.crc32(kind + data) == struct.unpack_from('>I', raw, end - 4)[0], 'png-crc')
        need(kind not in (b'acTL',b'fcTL',b'fdAT'), 'png-animated')
        need(kind in (b'IHDR',b'PLTE',b'IDAT',b'IEND') or kind[0] & 32, 'png-unknown-critical')
        need(count != 1 or kind == b'IHDR', 'png-header-order')
        if kind == b'IHDR':
            need(count == 1 and size == 13, 'png-header-order')
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', data)
            need((width,height) == (1280,800) and depth == 8 and color in (2,6) and
                 (compression,filtering,interlace) == (0,0,0), 'png-dimensions-or-format')
        elif kind == b'IDAT':
            need(not ended_data, 'png-data-order')
            data_bytes += size
        elif b'IDAT' in seen:
            ended_data = True
        if kind == b'PLTE':
            need(kind not in seen and b'IDAT' not in seen and 0 < size <= 768 and size % 3 == 0, 'png-palette')
        if kind in (b'cHRM',b'gAMA',b'iCCP',b'sBIT',b'sRGB',b'bKGD',b'pHYs',b'tIME',b'tRNS',b'eXIf'):
            need(kind not in seen, 'png-duplicate-chunk')
        if kind in (b'cHRM',b'gAMA',b'iCCP',b'sBIT',b'sRGB'):
            need(b'PLTE' not in seen and b'IDAT' not in seen, 'png-color-chunk-order')
        if kind in (b'bKGD',b'pHYs',b'tRNS'):
            need(b'IDAT' not in seen, 'png-ancillary-order')
        lengths = {b'cHRM':32,b'gAMA':4,b'sBIT':3 if color == 2 else 4,b'sRGB':1,b'bKGD':6,b'pHYs':9,b'tIME':7,b'tRNS':6}
        if kind in lengths:
            need(size == lengths[kind], 'png-ancillary-size')
        if kind == b'tRNS':
            need(color == 2, 'png-alpha-transparency-chunk')
        if kind == b'IEND':
            need(size == 0 and data_bytes > 0 and end == len(raw), 'png-end')
        seen.add(kind)
        offset = end
    need(b'IEND' in seen, 'png-missing-end')


def collect_raw(root, summary_raw, product, test, *, tick=lambda: None, read=read_file):
    """Return only admitted original bytes and their stable, unqualified identities."""
    tick()
    need(type(summary_raw) is bytes and 0 < len(summary_raw) <= 512 * 1024, 'summary-byte-limit')
    summary = summary_admission(summary_raw, test)
    need(summary['passedTests'] == 1 and test['returncode'] == 0 and
         all(number(summary[k]) for k in ('startTime','finishTime')), 'case-not-passed')
    fields(product, PRODUCT_FIELDS, 'product-fields')
    app = product['applicationPath']
    need(text(app, 2048) and app.startswith('/') and '..' not in Path(app).parts and
         app.endswith('/build/mac-tests/Build/Products/Debug/CelluloidMac.app') and
         product['executable'] == app + '/Contents/MacOS/CelluloidMac' and
         sha(product['executableSHA256']) and sha(product['logicSHA256']), 'product-values')
    root = Path(root)
    need('..' not in root.parts, 'unsafe-path')
    manifest_raw = _read(root / 'manifest.json', RAW_LIMITS['raw-manifest.json'], read, tick)
    groups = strict_json(manifest_raw.decode('utf-8'))
    need(isinstance(groups, list) and len(groups) == 1, 'manifest-group-count')
    group = groups[0]
    fields(group, {'testIdentifier','testIdentifierURL','attachments'}, 'manifest-fields')
    need(group['testIdentifier'] == 'NativeEditorUITests/' + CASE + '()' and
         group['testIdentifierURL'] == 'test://com.apple.xcode/CelluloidNative/CelluloidMacUITests/NativeEditorUITests/' + CASE,
         'manifest-case')
    items = group['attachments']
    need(isinstance(items, list) and 5 <= len(items) <= 6, 'attachment-count')
    known = {}
    for state in STATES:
        known['Native Mac Store window ' + state] = ('native-' + state + '.png', 'png')
        known['Native Mac Store proof ' + state] = ('raw-proof-' + state + '.json', 'txt')
    for suffix in ('setup','restore'):
        known['Native Mac Store display ' + suffix] = ('raw-display-' + suffix + '.json', 'txt')
    selected = {}
    used = set()
    device = summary['devicesAndConfigurations'][0]['device']['deviceId']
    for item in items:
        tick()
        fields(item, ATTACHMENT_FIELDS, 'attachment-fields')
        need(item['deviceId'] == device and item['configurationName'] == 'Test Scheme Action' and
             item['isAssociatedWithFailure'] is False and text(item['deviceName'], 256) and
             number(item['timestamp']), 'attachment-scope')
        human = item['suggestedHumanReadableName']
        need(text(human, 256), 'attachment-name')
        matches = [(name, ext) for prefix, (name, ext) in known.items()
                   if re.fullmatch(re.escape(prefix) + r'_[0-9]{1,20}_' + GUID + r'\.' + ext, human)]
        need(len(matches) == 1, 'attachment-identity')
        name, ext = matches[0]
        filename = item['exportedFileName']
        need(isinstance(filename, str) and re.fullmatch(GUID + r'\.' + ext, filename) is not None,
             'attachment-filename')
        need(name not in selected and filename.lower() not in used, 'duplicate-attachment')
        selected[name] = filename
        used.add(filename.lower())
    required = set(RAW_LIMITS) - {'raw-manifest.json','raw-display-restore.json'}
    need(required <= set(selected) and set(selected) <= required | {'raw-display-restore.json'}, 'missing-attachment')
    files = {'raw-manifest.json':manifest_raw}
    for name, filename in selected.items():
        files[name] = _read(root / filename, RAW_LIMITS[name], read, tick)
    for suffix in ('setup','restore'):
        name = 'raw-display-' + suffix + '.json'
        if name in files:
            _display(files[name], suffix)
    for state in STATES:
        tick()
        row = _proof(files['raw-proof-' + state + '.json'], state, product)
        original = files['native-' + state + '.png']
        need(row['pngBytes'] == len(original) and row['pngSHA256'] == digest(original), 'pixel-binding')
        _png(original, tick)
    tick()
    return {'status':'unqualified','visual_pending':True,
            'files':{name:{'bytes':len(raw),'sha256':digest(raw)} for name, raw in files.items()},
            'exportedNames':{'raw-manifest.json':'manifest.json', **selected}}, files
