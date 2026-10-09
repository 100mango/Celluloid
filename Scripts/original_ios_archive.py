#!/usr/bin/env python3
"""Fixed original-iOS unsigned archive qualification. Never release acceptance.

Only the three original code bundles and pinned SnapKit framework are admitted. Public Mach-O observations
share one deadline, including owned process cleanup; no outer process wrapper
may kill this verifier while one of those sessions is still owned.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import os
import plistlib
import re
import stat
import struct
import time

from mac_host_transport import load_json
from mac_owned_crash import bounded_optional_process, directory_fd
from combined_evidence_budget import BUDGETS
from uikit_full_shipping_gate import ROWS, ROW_COUNTS

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = '.build/Celluloid.xcarchive'
APP = 'Products/Applications/Celluloid.app'
KIT = APP + '/Frameworks/CelluloidKit.framework'
EXT = APP + '/PlugIns/CelluloidPhotoExtension.appex'
SNAPKIT_NAME = 'SnapKit_3965163F11347F41_PackageProduct'
SNAPKIT = APP + '/Frameworks/' + SNAPKIT_NAME + '.framework'
BUNDLES = {APP: ('Celluloid', 'Mango.Celluloid', 'APPL', 2),
           KIT: ('CelluloidKit', 'Mango.CelluloidKit', 'FMWK', 6),
           EXT: ('CelluloidPhotoExtension', 'Mango.Celluloid.CelluloidPhotoExtension', 'XPC!', 2),
           SNAPKIT: (SNAPKIT_NAME, 'snapkit.SnapKit', 'FMWK', 6)}
EXECUTABLES = {path + '/' + values[0] for path, values in BUNDLES.items()}
# Device archive 111356696316: framework self IDs are install identities, not dependencies.
INSTALL_NAMES = {KIT: '@rpath/CelluloidKit.framework/CelluloidKit',
                 SNAPKIT: '@rpath/' + SNAPKIT_NAME + '.framework/' + SNAPKIT_NAME}
BUNDLED_DEPENDENCIES = {APP: {INSTALL_NAMES[KIT], INSTALL_NAMES[SNAPKIT]},
                        KIT: {INSTALL_NAMES[SNAPKIT]}, EXT: {INSTALL_NAMES[KIT]}, SNAPKIT: set()}
# Actual797 device archive copies the same pinned SwiftPM resource to these three locations.
RESOURCE_BUNDLES = {APP + '/SnapKit_SnapKit.bundle', EXT + '/SnapKit_SnapKit.bundle',
                    SNAPKIT + '/SnapKit_SnapKit.bundle'}
PRIVACY = {'NSPrivacyTracking': False, 'NSPrivacyAccessedAPITypes': [],
           'NSPrivacyCollectedDataTypes': [], 'NSPrivacyTrackingDomains': []}
NOTICE_HASH = '7c0d21cf5314759fd35a22e42a52099d9cad2570db55a78e4eda26c82493b96b'
SNAPKIT_REVISION = '2842e6e84e82eb9a8dac0100ca90d9444b0307f4'
CLOCK = 'original-ios-archive-clock.json'
PACKAGE = 'original-ios-archive-package.json'
OUTPUT = 'original-ios-archive.json'
ROWS_FILE = 'original-ios-rows.json'
EVIDENCE = 'celluloid-original-ios-archive-evidence'
SCHEMA = 'Celluloid.OriginalIOSArchive.1'
CLOCK_SCHEMA = 'Celluloid.OriginalIOSArchiveClock.1'
PHASES = {'setup': (300, 300), 'archive': (900, 1200), 'proof': (180, 1380),
          'source': (60, 1440), 'retention': (60, 1500), 'upload': (60, 1560)}
MAX_ENTRIES, MAX_FILE, MAX_BYTES, MAX_DEPTH = 2048, 256_000_000, 1_000_000_000, 12
METADATA_CAP = 100_000
DEBUG_MARKERS = (b'CELLULOID_PHONE_LAYOUT_FIXTURE', b'WatchProcessingLargeTextUI',
                 b'CELLULOID_PHONE_OUTPUT_PROOF', b'PhoneOutputProof', b'companion.synthetic-seed',
                 b'CELLULOID_EXPORT_FULL_CANVAS_CONTROL', b'CELLULOID_EXPORT_WARMING_ONLY_CONTROL',
                 b'--photos-denied', b'--photos-limited-empty', b'--ui-diagnostics',
                 b'outputWriterPreparedForTesting')
MACHO_MAGICS = {b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf',
                b'\xfe\xed\xfa\xce', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca',
                b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca'}


def need(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def identity():
    from uikit_full_shipping_handoff import identity as current_identity
    return validate_identity(current_identity())


def validate_identity(value):
    need(type(value) is dict and set(value) == {'source_sha', 'run_id', 'run_attempt'}, 'Invalid archive identity')
    for key, pattern in [('source_sha', '[0-9a-f]{40}'), ('run_id', '[1-9][0-9]*'), ('run_attempt', '[1-9][0-9]*')]:
        need(type(value[key]) is str and re.fullmatch(pattern, value[key]), 'Invalid archive ' + key)
    return dict(value)


def clock_status(clock, context, phase=None, now=None):
    context = validate_identity(context)
    need(type(clock) is dict and set(clock) == {'schema', *context, 'started_monotonic', 'started_unix', 'execution_budget_seconds'}, 'Malformed archive clock')
    need(clock['schema'] == CLOCK_SCHEMA and all(clock[k] == v for k, v in context.items()), 'Archive clock identity differs')
    need(type(clock['execution_budget_seconds']) is int and clock['execution_budget_seconds'] == 1560, 'Archive clock budget changed')
    now = time.monotonic() if now is None else now
    for number in (clock['started_monotonic'], clock['started_unix'], now):
        need(type(number) in (int, float) and math.isfinite(number) and number > 0, 'Invalid archive clock time')
    elapsed = now - clock['started_monotonic']
    need(elapsed >= 0 and (phase is None or phase in PHASES), 'Invalid archive clock phase/time')
    ceiling, deadline = PHASES.get(phase, (1560, 1560))
    return {'elapsed_seconds': elapsed, 'remaining_seconds': min(ceiling, deadline - elapsed),
            'deadline_monotonic': clock['started_monotonic'] + deadline,
            'execution_budget_seconds': 1560, 'outside_execution_clock_seconds': 240}


def admit(clock, context, phase, now=None):
    result = math.floor(clock_status(clock, context, phase, now)['remaining_seconds'])
    need(result > 0, 'No allocation remains for archive ' + phase)
    return result


def snapshot(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def read(path, cap=METADATA_CAP):
    path = Path(path).absolute()
    parent = directory_fd(path.parent)
    descriptor = None
    try:
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        before = os.fstat(descriptor)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 < before.st_size <= cap, 'Unsafe/oversized archive input: ' + path.name)
        data = bytearray()
        while len(data) < before.st_size:
            chunk = os.read(descriptor, min(65536, before.st_size - len(data)))
            need(chunk, 'Truncated archive input')
            data.extend(chunk)
        need(snapshot(before) == snapshot(os.fstat(descriptor)) == snapshot(os.stat(path.name, dir_fd=parent, follow_symlinks=False)), 'Archive input changed while reading')
        return bytes(data)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent)


def read_tail(path, cap):
    path = Path(path)
    parent = directory_fd(path.parent)
    descriptor = None
    try:
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        before = os.fstat(descriptor)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, 'Unsafe archive log')
        os.lseek(descriptor, max(0, before.st_size - cap), os.SEEK_SET)
        chunks, remaining = [], min(before.st_size, cap)
        while remaining:
            data = os.read(descriptor, min(65536, remaining))
            need(data, 'Archive log truncated')
            chunks.append(data)
            remaining -= len(data)
        need(snapshot(before) == snapshot(os.fstat(descriptor)) == snapshot(os.stat(path.name, dir_fd=parent, follow_symlinks=False)), 'Archive log changed while reading')
        return b''.join(chunks), max(0, before.st_size - cap)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent)


def write_new(path, value):
    data = encoded(value)
    need(len(data) <= BUDGETS['archive'], 'Archive proof exceeds existing archive evidence allocation')
    path = Path(path)
    parent = directory_fd(path.parent)
    try:
        descriptor = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
    finally:
        os.close(parent)


class UniqueDict(dict):
    def __setitem__(self, key, value):
        need(key not in self, 'Duplicate plist key')
        super().__setitem__(key, value)


def plist(raw):
    need(0 < len(raw) <= METADATA_CAP, 'Plist byte cap')
    value = plistlib.loads(raw, dict_type=UniqueDict)
    count = [0]
    def visit(item, depth=0):
        count[0] += 1
        need(depth <= 16 and count[0] <= 4096, 'Plist complexity cap')
        if isinstance(item, dict):
            for key, child in item.items():
                need(type(key) is str and len(key.encode()) <= 256, 'Malformed plist key')
                visit(child, depth + 1)
        elif type(item) is list:
            for child in item:
                visit(child, depth + 1)
        elif type(item) is str:
            need(len(item.encode()) <= 8192, 'Plist string cap')
        else:
            need(type(item) in (bool, int, float, bytes) or hasattr(item, 'isoformat'), 'Unknown plist value')
            if type(item) is float:
                need(math.isfinite(item), 'Nonfinite plist value')
    visit(value)
    need(isinstance(value, dict), 'Plist root is not a dictionary')
    return value


def check_deadline(deadline):
    need(time.monotonic() < deadline, 'Shared archive proof deadline exhausted')


def macho_header(data, total_size, file_type):
    need(len(data) >= 32 and data[:4] == b'\xcf\xfa\xed\xfe', 'Wrong Mach-O magic')
    _, cpu, _, actual_type, commands, size, _, _ = struct.unpack_from('<IIIIIIII', data)
    need(cpu == 0x100000c and actual_type == file_type, 'Wrong Mach-O identity/type')
    need(0 < commands <= 512 and commands * 8 <= size <= 256000 and 32 + size <= min(total_size, len(data)), 'Malformed/oversized Mach-O load commands')
    offset, signature = 32, {'present': False}
    for _ in range(commands):
        need(offset + 8 <= 32 + size, 'Truncated Mach-O load command')
        command, length = struct.unpack_from('<II', data, offset)
        need(length >= 8 and length % 8 == 0 and offset + length <= 32 + size, 'Invalid Mach-O load command size')
        if command == 0x1d:
            need(length == 16 and signature['present'] is False, 'Malformed/duplicate code-signature load command')
            data_offset, data_size = struct.unpack_from('<II', data, offset + 8)
            need(data_size > 0 and data_offset >= 32 + size and data_offset + data_size <= total_size, 'Code-signature load-command range outside executable')
            signature = {'present': True, 'command': 'LC_CODE_SIGNATURE', 'data_offset': data_offset,
                         'data_size': data_size, 'signature_kind': 'unverified', 'signing_qualified': False}
        offset += length
    need(offset == 32 + size, 'Mach-O load command count/size differs')
    return signature


def source_usage_localization(root):
    values = {}
    for line in read(Path(root) / 'Celluloid/zh-Hans.lproj/InfoPlist.strings').decode('utf8').splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r'\s*("(?:[^"\\]|\\.)*")\s*=\s*("(?:[^"\\]|\\.)*")\s*;\s*', line)
        need(match is not None, 'Unexpected original Photos usage localization source')
        key, value = json.loads(match[1]), json.loads(match[2])
        need(key not in values, 'Duplicate localized usage key')
        values[key] = value
    need(set(values) == {'NSPhotoLibraryUsageDescription', 'NSPhotoLibraryAddUsageDescription'}, 'Original localized usage keys changed')
    return values


def inventory(archive, deadline):
    """Bounded traversal and streamed hashes; every path component uses NOFOLLOW."""
    rows, directories, total, snapshots, signatures = [], set(), [0], {}, {}
    root = directory_fd(archive)
    def scan(folder, prefix='', depth=0):
        check_deadline(deadline)
        need(depth <= MAX_DEPTH, 'Archive depth cap')
        before = os.fstat(folder)
        snapshots[prefix.rstrip('/')] = snapshot(before)
        with os.scandir(folder) as entries:
            for entry in entries:
                check_deadline(deadline)
                relative = prefix + entry.name
                need(len(rows) + len(directories) < MAX_ENTRIES and len(relative.encode()) <= 240, 'Archive entry/path cap')
                need(not any(ord(c) < 32 for c in relative), 'Control character in archive path')
                info = entry.stat(follow_symlinks=False)
                need(not stat.S_ISLNK(info.st_mode), 'Archive symlink forbidden')
                parts = Path(relative).parts
                need(not any(p.lower() in {'watch', 'watchkitsupport', 'watchkitsupport2', '__preview.dylib', 'embedded.mobileprovision', '_codesignature'} or p.lower().endswith(('.xctest', '.xcresult', '.debug.dylib')) for p in parts), 'Forbidden Watch/test/debug/signed payload')
                if stat.S_ISDIR(info.st_mode):
                    directories.add(relative)
                    if entry.name.lower().endswith(('.app', '.appex', '.framework')):
                        need(relative in BUNDLES, 'Extra code bundle: ' + relative)
                    if entry.name.lower().endswith('.bundle'):
                        need(relative in RESOURCE_BUNDLES, 'Extra resource bundle: ' + relative)
                    child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=folder)
                    try:
                        need(snapshot(info) == snapshot(os.fstat(child)), 'Archive directory replaced')
                        scan(child, relative + '/', depth + 1)
                    finally:
                        os.close(child)
                else:
                    need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= MAX_FILE, 'Unsafe/oversized archive file')
                    total[0] += info.st_size
                    need(total[0] <= MAX_BYTES, 'Archive aggregate byte cap')
                    need(not relative.startswith('Products/') or relative.startswith(APP + '/'), 'Extra installed archive payload')
                    need(not entry.name.lower().endswith(('.dylib', '.swift', '.o', '.a')), 'Unexpected code/debug payload')
                    descriptor = os.open(entry.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=folder)
                    digest, size, tail, magic, header = hashlib.sha256(), 0, b'', b'', bytearray()
                    try:
                        need(snapshot(info) == snapshot(os.fstat(descriptor)), 'Archive file replaced')
                        while size < info.st_size:
                            check_deadline(deadline)
                            chunk = os.read(descriptor, min(65536, info.st_size - size))
                            need(chunk, 'Truncated archive file')
                            if size == 0:
                                magic = chunk[:32]
                            if relative in EXECUTABLES:
                                header.extend(chunk[:max(0, 256032 - len(header))])
                                combined = tail + chunk
                                need(not any(marker in combined for marker in DEBUG_MARKERS), 'Debug/test seam in shipping executable')
                                tail = combined[-128:]
                            digest.update(chunk)
                            size += len(chunk)
                        need(snapshot(info) == snapshot(os.fstat(descriptor)) == snapshot(os.stat(entry.name, dir_fd=folder, follow_symlinks=False)), 'Archive file changed while hashing')
                    finally:
                        os.close(descriptor)
                    if magic[:4] in MACHO_MAGICS:
                        dsym = re.fullmatch(r'dSYMs/(Celluloid|CelluloidKit|CelluloidPhotoExtension)\.(app|framework|appex)\.dSYM/Contents/Resources/DWARF/\1', relative)
                        dsym = dsym or relative == 'dSYMs/' + SNAPKIT_NAME + '.framework.dSYM/Contents/Resources/DWARF/' + SNAPKIT_NAME
                        need(relative in EXECUTABLES or dsym, 'Unexpected executable payload')
                    if relative in EXECUTABLES:
                        expected_type = BUNDLES[relative.rsplit('/', 1)[0]][3]
                        signatures[relative] = macho_header(header, size, expected_type)
                    rows.append({'path': relative, 'bytes': size, 'sha256': digest.hexdigest()})
                    snapshots[relative] = snapshot(info)
        need(snapshot(before) == snapshot(os.fstat(folder)), 'Archive directory changed during inventory')
    try:
        scan(root)
    finally:
        os.close(root)
    need(set(BUNDLES) <= directories, 'Missing original app/framework/Photos extension')
    need(all(name in {item['path'] for item in rows} for name in EXECUTABLES), 'Missing original executable')
    return sorted(rows, key=lambda row: row['path']), directories, snapshots, signatures


def unchanged(archive, snapshots, deadline):
    for relative, expected in snapshots.items():
        check_deadline(deadline)
        path = Path(archive) / relative
        parent = directory_fd(path.parent)
        try:
            need(snapshot(os.stat(path.name, dir_fd=parent, follow_symlinks=False)) == expected, 'Archive changed after inventory/observation')
        finally:
            os.close(parent)


def row_binding(value, context, source):
    required = {'schema', *context, 'source_tree', 'scope', 'all_rows_verified', 'original_total_invocations', 'rows'}
    fixed = type(value) is dict and value.get('schema') == 'Celluloid.OriginalIOSRows.3'
    if fixed:required.add('fixed_predecessor_rows')
    need(type(value) is dict and set(value) == required and value['schema'] in {'Celluloid.OriginalIOSRows.1','Celluloid.OriginalIOSRows.3'}, 'Malformed original row replay')
    if fixed:
        from original_ios_fixed_rows import validate_fixed_summary
        validate_fixed_summary(value['fixed_predecessor_rows'],context,source['tree'])
    need(all(value[k] == v and type(value[k]) is str for k, v in context.items()), 'Row replay identity differs')
    need(value['scope'] == 'original-ios-release' and value['source_tree'] == source['tree'] and value['all_rows_verified'] is True, 'Unverified row source')
    need(type(value['original_total_invocations']) is int and value['original_total_invocations'] == 412, 'Incomplete original invocations')
    need(type(value['rows']) is list and len(value['rows']) == 4, 'Incomplete original rows')
    devices = set()
    for actual, row in zip(value['rows'], ROWS):
        keys={'row', 'original_test_invocation_count', 'model', 'device_id', 'row_receipt_sha256', 'artifact_manifest_sha256', 'artifact_name'}
        if fixed:keys.update({'execution_identity','execution_source_tree'})
        need(type(actual) is dict and set(actual) == keys, 'Malformed replayed row')
        need(actual['row'] == row and actual['model'] == ROWS[row] and type(actual['original_test_invocation_count']) is int and actual['original_test_invocation_count'] == ROW_COUNTS[row], 'Original row/model/count changed')
        for key in ('row_receipt_sha256', 'artifact_manifest_sha256'):
            need(type(actual[key]) is str and re.fullmatch('[0-9a-f]{64}', actual[key]), 'Invalid replayed row hash')
        device = actual['device_id']
        need(type(device) is str and re.fullmatch('[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}', device) and device.lower() not in devices, 'Missing/duplicate row device')
        devices.add(device.lower())
        execution=context;tree=source['tree']
        if fixed:
            proof=value['fixed_predecessor_rows'][row];original=proof['original'];artifact=proof['artifact']
            execution={k:original[k] for k in context};tree=original['source_tree']
            need(actual['device_id']==original['device']['id'] and actual['row_receipt_sha256']==artifact['row_receipt_sha256']
                 and actual['artifact_manifest_sha256']==artifact['manifest_sha256'],'Fixed historical row summary differs from replay')
        if fixed:
            need(actual['execution_identity']==execution and actual['execution_source_tree']==tree,'Row execution identity was relabelled')
        need(actual['artifact_name'] == 'celluloid-original-ios-' + row + '-' + execution['source_sha'] + '-' + execution['run_attempt'], 'Wrong original-execution row artifact name')
    return value


def fixed_metadata_binding(temp, context, rows):
    if rows.get('schema') != 'Celluloid.OriginalIOSRows.3':return None
    from original_ios_fixed_rows import METADATA, validate_metadata
    raw=read(Path(temp)/METADATA,16_384)
    validate_metadata(load_json(raw),context)
    return sha(raw)


def require_archive_only_rows(temp, context):
    """The current CLI admits only the four fully replayed historical rows."""
    temp = Path(temp)
    rows = load_json(read(temp / ROWS_FILE))
    need(rows.get('schema') == 'Celluloid.OriginalIOSRows.3',
         'Archive-only qualification requires all four historical rows')
    source = load_json(read(temp / 'combined-source-before.json'))
    row_binding(rows, context, source)
    fixed_metadata_binding(temp, context, rows)


class ObservationFailure(ValueError):
    def __init__(self, message, events, finalized):
        super().__init__(message)
        self.events, self.all_processes_finalized = list(events), finalized


class ProofCommands:
    def __init__(self, deadline):
        self.deadline, self.events, self.blocked = deadline, [], False

    def run(self, tool, executable):
        need(not self.blocked, 'Earlier archive process cleanup uncertain; later commands forbidden')
        need(tool in {'lipo', 'vtool', 'otool'}, 'Unknown fixed archive observation')
        now = time.monotonic()
        need(self.deadline - now > 3, 'Insufficient shared proof/cleanup allocation')
        args = {'lipo': ['-archs'], 'vtool': ['-arch', 'arm64', '-show-build'], 'otool': ['-L']}[tool]
        command = ['/usr/bin/xcrun', tool, *args, str(executable)]
        cleanup_deadline = min(now + 20, self.deadline - 1)
        try:
            result = bounded_optional_process(command, cleanup_deadline - 2, cleanup_deadline, cap=8192, stop_on_signal_error=True)
        except Exception as error:
            self.blocked = True
            raise ObservationFailure('Archive observation raised ' + type(error).__name__ + '; cleanup unknown', self.events, False) from error
        self.events.append({'tool': tool, 'executable': executable.name,
                            **{k: v for k, v in result.items() if k != 'output'}, 'output_sha256': sha(result['output'])})
        self.blocked = not (result.get('finalized') is True and result.get('pipe_eof') is True and result.get('child_reaped') is True and result.get('cleanup_error') is None)
        if self.blocked or result.get('timed_out') is not False or result.get('overflow') is not False or type(result.get('return_code')) is not int or result['return_code'] != 0:
            raise ObservationFailure('Failed/unfinished bounded archive ' + tool, self.events, not self.blocked)
        check_deadline(self.deadline)
        need(type(result['output']) is bytes and len(result['output']) <= 8192, 'Archive tool output cap')
        return result['output'].decode('utf8', errors='strict')


def build_versions(raw, executable):
    lines = raw.splitlines()
    need(lines and lines[0] in {str(executable) + ':', str(executable) + ' (architecture arm64):'}, 'Wrong build-version executable')
    need(re.findall(r'^\s*cmd\s+(\S+)\s*$', raw, re.M) == ['LC_BUILD_VERSION'], 'Missing/extra build-version command')
    need(re.findall(r'^\s*platform\s+(\S+)\s*$', raw, re.M) == ['IOS'] and re.findall(r'^\s*minos\s+(\S+)\s*$', raw, re.M) == ['15.0'], 'Wrong actual platform/minimum OS')
    need(len(re.findall(r'^\s*sdk\s+[0-9.]+\s*$', raw, re.M)) == 1, 'Missing/ambiguous actual SDK')
    return raw


def linked_libraries(raw, executable, owner):
    need(owner in BUNDLES, 'Unknown linked-library owner')
    required = BUNDLED_DEPENDENCIES[owner] | ({INSTALL_NAMES[owner]} if owner in INSTALL_NAMES else set())
    lines = raw.splitlines()
    need(lines and lines[0] == str(executable) + ':' and len(lines) <= 80, 'Wrong linked-library header/count')
    libraries = []
    for line in lines[1:]:
        match = re.fullmatch(r'\s+(\S+) \(compatibility version [0-9.]+, current version [0-9.]+(, weak)?\)', line)
        need(match is not None, 'Malformed linked-library record')
        name = match[1]
        system = re.fullmatch(r'/System/Library/Frameworks/[A-Za-z0-9_]+\.framework/[A-Za-z0-9_]+|/usr/lib/(?:swift/)?[A-Za-z0-9_.+-]+\.dylib', name)
        need(system or name in required, 'Unreviewed/private/host linked library')
        need(not any(marker in name.lower() for marker in ('xctest', 'testingsupport', 'watchkit')) and not any(item['path'] == name for item in libraries), 'Test/Watch/duplicate linked library')
        libraries.append({'path': name, 'weak': match[2] is not None})
    need({item['path'] for item in libraries if item['path'].startswith('@rpath/')} == required, 'Required bundled dependency/install identity missing')
    if owner in INSTALL_NAMES:
        need(libraries[0]['path'] == INSTALL_NAMES[owner], 'Wrong framework install identity')
    return libraries


def verify_package(root, temp, context, clock, source):
    started = time.monotonic()
    deadline = min(started + 180, clock_status(clock, context, 'proof', started)['deadline_monotonic'])
    check_deadline(deadline)
    rows_raw = read(Path(temp) / ROWS_FILE)
    rows=row_binding(load_json(rows_raw), context, source)
    fixed_metadata_sha=fixed_metadata_binding(temp,context,rows)
    archive = Path(root) / ARCHIVE
    files, directories, snapshots, signatures = inventory(archive, deadline)
    hashes = {row['path']: row['sha256'] for row in files}
    metadata = plist(read(archive / 'Info.plist'))
    properties = metadata.get('ApplicationProperties', {})
    need(type(metadata.get('ArchiveVersion')) is int and metadata['ArchiveVersion'] == 2 and metadata.get('SchemeName') == 'Celluloid', 'Wrong archive metadata')
    for key, wanted in {'ApplicationPath': 'Applications/Celluloid.app', 'CFBundleIdentifier': 'Mango.Celluloid', 'CFBundleShortVersionString': '1.1.1', 'CFBundleVersion': '3'}.items():
        need(properties.get(key) == wanted, 'Wrong archive property: ' + key)
    bundle_reports, probes = [], ProofCommands(deadline)
    for path, (name, bundle_id, package_type, _) in BUNDLES.items():
        check_deadline(deadline)
        info = plist(read(archive / path / 'Info.plist'))
        expected = {'CFBundleExecutable': name, 'CFBundleIdentifier': bundle_id,
                    'CFBundlePackageType': package_type, 'CFBundleShortVersionString': '1.0' if path == SNAPKIT else '1.1.1',
                    'CFBundleVersion': '1' if path == SNAPKIT else '3',
                    'DTPlatformName': 'iphoneos', 'CFBundleSupportedPlatforms': ['iPhoneOS'], 'MinimumOSVersion': '15.0'}
        if path != SNAPKIT:
            expected['CFBundleName'] = name
        for key, wanted in expected.items():
            need(info.get(key) == wanted and type(info.get(key)) is type(wanted), 'Wrong original bundle metadata: ' + path + '/' + key)
        if path == APP:
            source_info = plist(read(Path(root) / 'Celluloid/Info.plist'))
            for key in ('NSPhotoLibraryUsageDescription', 'NSPhotoLibraryAddUsageDescription', 'PHPhotoLibraryPreventAutomaticLimitedAccessAlert', 'UILaunchStoryboardName', 'UIRequiredDeviceCapabilities'):
                need(encoded(info.get(key)) == encoded(source_info[key]), 'Original Photos/privacy declaration changed')
            need(encoded(info.get('UIDeviceFamily')) == encoded([1, 2]), 'Original iPhone/iPad family changed')
        if path == EXT:
            need(encoded(info.get('NSExtension')) == encoded(plist(read(Path(root) / 'CelluloidPhotoExtension/Info.plist'))['NSExtension']), 'Original Photos extension declaration changed')
            expected['NSExtension'] = info['NSExtension']
        executable = archive / path / name
        need(probes.run('lipo', executable).strip().split() == ['arm64'], 'Wrong actual archive architecture')
        versions = build_versions(probes.run('vtool', executable), executable)
        libraries = linked_libraries(probes.run('otool', executable), executable, path)
        observed_name = info.get('CFBundleName')
        need(observed_name is None or type(observed_name) is str and 0 < len(observed_name.encode()) <= 256, 'Malformed observed bundle name')
        bundle_reports.append({'path': path, 'metadata': expected, 'executable_sha256': hashes[path + '/' + name],
                               'architectures': ['arm64'], 'build_versions': versions, 'linked_libraries': libraries,
                               'install_name': INSTALL_NAMES.get(path), 'observed_bundle_name': observed_name,
                               'code_signature_load_command': signatures[path + '/' + name]})
    for path, source_name in [(APP + '/collage.json', 'Celluloid/collage.json'), (KIT + '/bubble.json', 'CelluloidKit/bubble.json'),
                              (KIT + '/SnapKit-LICENSE.txt', 'CelluloidKit/ThirdPartyNotices/SnapKit-LICENSE.txt')]:
        need(hashes.get(path) == sha(read(Path(root) / source_name)), 'Missing/changed original bundled resource: ' + path)
    need(hashes[KIT + '/SnapKit-LICENSE.txt'] == NOTICE_HASH, 'Pinned SnapKit notice changed')
    required = [APP + '/Assets.car', KIT + '/Assets.car', APP + '/zh-Hans.lproj/InfoPlist.strings']
    required += [owner + '/' + language + '.lproj/Localizable.strings' for owner in (APP, KIT) for language in ('en', 'zh-Hans')]
    need(all(path in hashes for path in required), 'Missing original assets/localization/privacy resource')
    localized_usage = plist(read(archive / APP / 'zh-Hans.lproj/InfoPlist.strings'))
    need(encoded(localized_usage) == encoded(source_usage_localization(root)), 'Original localized Photos privacy declarations changed')
    need({APP + '/Base.lproj/LaunchScreen.storyboardc', EXT + '/Base.lproj/MainInterface.storyboardc'} <= directories, 'Missing original launch/Photos storyboard')
    privacy = []
    for row in files:
        path = row['path']
        if path.endswith('/Info.plist'):
            info = plist(read(archive / path))
            need('CFBundleExecutable' not in info or path.rsplit('/', 1)[0] in BUNDLES, 'Hidden extra code bundle metadata')
        if path.lower().endswith('.xcprivacy'):
            need(path in {bundle + '/PrivacyInfo.xcprivacy' for bundle in RESOURCE_BUNDLES}, 'Unreviewed privacy manifest location')
            declaration = plist(read(archive / path))
            need(encoded(declaration) == encoded(PRIVACY), 'Pinned SnapKit privacy declarations changed')
            privacy.append({'path': path, 'sha256': row['sha256'], 'declarations': declaration})
    present_resources = RESOURCE_BUNDLES & directories
    need(present_resources == RESOURCE_BUNDLES and len(privacy) == len(RESOURCE_BUNDLES), 'Missing pinned SnapKit privacy resource')
    need(len({item['sha256'] for item in privacy}) == 1, 'SnapKit privacy resource copies differ in exact bytes')
    resolved = load_json(read(Path(root) / 'Celluloid.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved'))
    need(resolved == {'pins': [{'identity': 'snapkit', 'kind': 'remoteSourceControl', 'location': 'https://github.com/SnapKit/SnapKit.git',
                              'state': {'revision': SNAPKIT_REVISION, 'version': '5.7.1'}}], 'version': 2}, 'SnapKit source pin changed')
    unchanged(archive, snapshots, deadline)
    check_deadline(deadline)
    return {'schema': SCHEMA, **context, 'source_tree': source['tree'], 'scope': 'original-ios-release',
            'unsigned_package_verified': True, 'release_acceptance': False, 'signing_qualified': False, 'uploaded': False,
            'all_processes_finalized': True,
            'archive_path': ARCHIVE, 'row_replay_sha256': sha(rows_raw), 'fixed_artifact_metadata_sha256':fixed_metadata_sha, 'source_before_sha256': sha(read(Path(temp) / 'combined-source-before.json')),
            'code_bundles': bundle_reports, 'files': files, 'inventory_sha256': sha(encoded(files)),
            'privacy_manifests': privacy, 'application_privacy_manifest_present': False,
            'photos_usage': {'default': {key: source_info[key] for key in ('NSPhotoLibraryUsageDescription', 'NSPhotoLibraryAddUsageDescription')}, 'zh-Hans': localized_usage},
            'privacy_scope': 'Actual shipped declarations and original Photos usage strings only; no privacy/store acceptance is inferred.',
            'snapkit': {'version': '5.7.1', 'revision': SNAPKIT_REVISION, 'notice_sha256': NOTICE_HASH},
            'processes': probes.events, 'proof_elapsed_seconds': time.monotonic() - started,
            'limits': {'entries': MAX_ENTRIES, 'file_bytes': MAX_FILE, 'total_read_bytes': MAX_BYTES, 'proof_seconds': 180, 'command_output_bytes': 8192},
            'qualification': 'CODE_SIGNING_ALLOWED=NO generic-device package only. An observed signature load command does not establish signature kind, signing identity or distribution acceptance. Signing, installation, upload and App Store acceptance remain separate.'}


def finalize(temp, context, clock):
    from uikit_full_shipping_handoff import source_proof
    require_finalized_processes(temp, context)
    need(admit(clock, context, 'source') > 0, 'Late archive source binding')
    temp = Path(temp)
    before, after = source_proof(temp, 'before'), source_proof(temp, 'after')
    need(encoded({k: v for k, v in before.items() if k != 'phase'}) == encoded({k: v for k, v in after.items() if k != 'phase'}), 'Archive source changed')
    package = load_json(read(temp / PACKAGE, BUDGETS['archive']))
    need(package.get('schema') == SCHEMA and all(package.get(k) == v for k, v in context.items()) and package.get('unsigned_package_verified') is True and package.get('release_acceptance') is False, 'Missing/failed current archive proof')
    need(package['source_before_sha256'] == sha(read(temp / 'combined-source-before.json')) and package['source_tree'] == after['tree'], 'Archive source binding differs')
    rows_raw = read(temp / ROWS_FILE)
    rows=row_binding(load_json(rows_raw), context, before)
    need(package.get('fixed_artifact_metadata_sha256')==fixed_metadata_binding(temp,context,rows),'Fixed artifact metadata changed after archive')
    need(package['row_replay_sha256'] == sha(rows_raw), 'Row replay changed after archive')
    package['source_after_sha256'] = sha(read(temp / 'combined-source-after.json'))
    package['source_unchanged'] = True
    package['clock'] = clock_status(clock, context, 'source')
    need(package['clock']['remaining_seconds'] > 0, 'Late archive final binding')
    return package


def require_finalized_processes(temp, context):
    from original_ios_fixed_rows import METADATA, validate_metadata
    metadata=Path(temp)/METADATA
    if metadata.exists() or metadata.is_symlink():validate_metadata(load_json(read(metadata,16_384)),context)
    path = Path(temp) / PACKAGE
    if path.exists() or path.is_symlink():
        package = load_json(read(path, BUDGETS['archive']))
        need(package.get('schema') == SCHEMA and all(package.get(k) == v for k, v in context.items()), 'Wrong earlier archive process identity')
        need(package.get('all_processes_finalized') is True, 'Earlier archive process cleanup uncertain; later process admission forbidden')


def collect(temp, context, clock):
    """Fixed retained receipts and one log tail, within the existing 500KB cap.

    Incomplete qualification still produces diagnostic files, then the CLI fails.
    Collection launches no commands and never traverses/copies the raw archive.
    """
    temp = Path(temp)
    deadline = min(time.monotonic() + 60, clock_status(clock, context, 'retention')['deadline_monotonic'])
    check_deadline(deadline)
    names = (OUTPUT, ROWS_FILE, 'combined-source-before.json', 'combined-source-after.json', CLOCK)
    from original_ios_fixed_rows import METADATA, validate_metadata
    if (temp/METADATA).exists() or (temp/METADATA).is_symlink():names+=(METADATA,)
    retained, missing, errors = {}, [], []
    manifest = {'schema': 'Celluloid.OriginalIOSArchiveEvidence.1', **context, 'platform': 'archive',
                'unsigned_package_verified': False, 'release_acceptance': False,
                'limits': {'total_bytes': BUDGETS['archive']}, 'files': [], 'omissions': [],
                'scope': 'Bounded unsigned archive qualification/failed diagnostics only; no archive binary upload.'}
    def retain(name, raw):
        need(sum(map(len, retained.values())) + len(raw) + len(encoded(manifest)) + 8192 <= BUDGETS['archive'], 'Required archive evidence exceeds existing 500KB cap')
        retained[name] = raw
        manifest['files'].append({'name': name, 'bytes': len(raw), 'sha256': sha(raw)})
    for name in names:
        check_deadline(deadline)
        try:
            raw = read(temp / name, BUDGETS['archive'] if name == OUTPUT else METADATA_CAP)
            load_json(raw)
            retain(name, raw)
        except (OSError, ValueError) as error:
            missing.append(name)
            errors.append({'name': name, 'reason': str(error)[:256]})
    if not missing:
        try:
            final = load_json(retained[OUTPUT])
            before, after = (load_json(retained['combined-source-' + phase + '.json']) for phase in ('before', 'after'))
            need(all(final.get(key) == value and type(final.get(key)) is str for key, value in context.items()), 'Archive final identity differs')
            need(final.get('schema') == SCHEMA and final.get('unsigned_package_verified') is True and final.get('source_unchanged') is True and final.get('release_acceptance') is False and final.get('all_processes_finalized') is True, 'No complete unsigned archive proof')
            need(final['source_before_sha256'] == sha(retained['combined-source-before.json']) and final['source_after_sha256'] == sha(retained['combined-source-after.json']), 'Retained source hashes differ')
            need(before.get('source_sha') == after.get('source_sha') == context['source_sha'] and before.get('phase') == 'before' and after.get('phase') == 'after', 'Retained source identity differs')
            rows=row_binding(load_json(retained[ROWS_FILE]), context, before)
            if rows['schema']=='Celluloid.OriginalIOSRows.3':
                need(METADATA in retained,'Missing fixed artifact metadata retention')
                validate_metadata(load_json(retained[METADATA]),context)
                need(final.get('fixed_artifact_metadata_sha256')==sha(retained[METADATA]),'Retained fixed metadata hash differs')
            need(final['row_replay_sha256'] == sha(retained[ROWS_FILE]), 'Retained row replay hash differs')
            clock_status(load_json(retained[CLOCK]), context, 'retention')
            manifest['unsigned_package_verified'] = True
        except (ValueError, KeyError, TypeError) as error:
            errors.append({'name': OUTPUT, 'reason': str(error)[:256]})
    if OUTPUT in missing:
        try:
            raw = read(temp / PACKAGE, BUDGETS['archive'])
            load_json(raw)
            retain(PACKAGE, raw)
        except (OSError, ValueError) as error:
            manifest['omissions'].append({'name': PACKAGE, 'reason': str(error)[:256]})
    spare = BUDGETS['archive'] - sum(map(len, retained.values())) - len(encoded(manifest)) - 8192
    if spare > 0:
        try:
            raw, omitted = read_tail(temp / 'archive.log', min(80_000, spare))
            if raw:
                retain('archive.log.tail.txt', raw)
            if omitted:
                manifest['omissions'].append({'name': 'archive.log', 'omitted_prefix_bytes': omitted, 'reason': 'optional bounded log tail'})
        except (OSError, ValueError) as error:
            manifest['omissions'].append({'name': 'archive.log', 'reason': str(error)[:256]})
    manifest['missing_required'], manifest['errors'] = missing, errors
    # Include the manifest itself in the exact byte accounting, to a fixed point.
    manifest['retained_total_bytes'] = 0
    for _ in range(8):
        size = sum(map(len, retained.values())) + len(encoded(manifest))
        if manifest['retained_total_bytes'] == size:
            break
        manifest['retained_total_bytes'] = size
    need(manifest['retained_total_bytes'] == sum(map(len, retained.values())) + len(encoded(manifest)) <= BUDGETS['archive'], 'Archive manifest/total cap')
    check_deadline(deadline)
    parent = directory_fd(temp)
    try:
        os.mkdir(EVIDENCE, 0o700, dir_fd=parent)
    finally:
        os.close(parent)
    destination = temp / EVIDENCE
    for name, raw in retained.items():
        check_deadline(deadline)
        parent = directory_fd(destination)
        try:
            descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(raw)
        finally:
            os.close(parent)
    write_new(destination / 'manifest.json', manifest)
    check_deadline(deadline)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init-clock', 'admit', 'check-clock', 'verify', 'finalize', 'collect'])
    parser.add_argument('--phase', choices=PHASES)
    args = parser.parse_args(argv)
    temp, context = Path(os.environ['RUNNER_TEMP']), identity()
    if args.action == 'init-clock':
        write_new(temp / CLOCK, {'schema': CLOCK_SCHEMA, **context, 'started_monotonic': time.monotonic(), 'started_unix': time.time(), 'execution_budget_seconds': 1560})
        return
    clock = load_json(read(temp / CLOCK, 8192))
    if args.action != 'collect' and args.phase not in {'retention','upload'}:
        require_finalized_processes(temp, context)
    if args.action in {'verify', 'finalize'} or args.phase in {'archive', 'proof', 'source'}:
        require_archive_only_rows(temp, context)
    if args.action in ('admit', 'check-clock'):
        need(args.phase is not None, 'Clock phase required')
        remaining = admit(clock, context, args.phase)
        print(remaining if args.action == 'admit' else json.dumps(clock_status(clock, context, args.phase)))
        return
    from uikit_full_shipping_handoff import source_proof
    if args.action == 'collect':
        manifest = collect(temp, context, clock)
        print(json.dumps({'evidence': EVIDENCE, 'unsigned_package_verified': manifest['unsigned_package_verified'], 'release_acceptance': False}))
        need(manifest['unsigned_package_verified'], 'Archive qualification incomplete; bounded failed diagnostics retained')
        return
    if args.action == 'verify':
        need(not (temp / PACKAGE).exists(), 'Archive proof was already attempted; no later observation dispatch')
        try:
            report = verify_package(ROOT, temp, context, clock, source_proof(temp, 'before'))
        except Exception as error:
            write_new(temp / PACKAGE, {'schema': SCHEMA, **context, 'unsigned_package_verified': False, 'release_acceptance': False,
                                      'all_processes_finalized': getattr(error, 'all_processes_finalized', True),
                                      'processes': getattr(error, 'events', []), 'error': str(error)[:512],
                                      'scope': 'Failed unsigned archive proof; no later observations after uncertain cleanup.'})
            raise
        write_new(temp / PACKAGE, report)
    else:
        report = finalize(temp, context, clock)
        write_new(temp / OUTPUT, report)
    print(json.dumps({'unsigned_package_verified': report['unsigned_package_verified'], 'release_acceptance': False, 'action': args.action}))


if __name__ == '__main__':
    main()
