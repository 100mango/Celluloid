#!/usr/bin/env python3
"""Fixed, bounded unsigned CelluloidTV archive proof; never a signing handoff.

The retained JSON describes this observation interval. Host capture/owned-group
cleanup does not establish the lifetime of Xcode's independent system daemons.
"""
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import plistlib
import re
import stat
import struct
import sys
import time
import zlib
import xml.etree.ElementTree as ET

import tv_release_package as package
import tv_archive_diagnostics as diagnostics
from tv_archive_capture import capture, CaptureStopped

ROOT = Path(__file__).resolve().parents[1]
BASE = 'da446a1bb869baf95499c2a057bb627d3d73d3b0'
BASE_TREE = '6325ef9470ffbb03dce3ebd82b104a0b2e1eb82c'
PARENT = BASE
BRANCH = 'refs/heads/codex/tv-unsigned-archive'
WORKFLOW = '.github/workflows/tv-unsigned-archive.yml'
CATALOG = 'Platforms/tvOS/Assets.xcassets/AppIcon.brandassets/'
SCALED = ('TopShelf.imageset/', 'TopShelfWide.imageset/')
MODIFIED_PATHS = ()
NEW_PATHS = (WORKFLOW, 'Scripts/tv_release_archive.py', 'Scripts/tv_release_package.py', 'Scripts/tv_archive_capture.py', 'Scripts/tv_archive_diagnostics.py', 'Scripts/test_tv_archive_capture.py', 'Scripts/test_tv_archive_diagnostics.py', 'Scripts/test_tv_release_archive.py', 'Scripts/owned_process_group.py', 'Scripts/tv_release_contract.json', 'Scripts/materialize_tv_archive_assets.swift', 'TV-UNSIGNED-ARCHIVE.md')
ARCHIVE = Path('build/CelluloidTV.xcarchive')
APP = 'Products/Applications/CelluloidTV.app'
DSYM = 'dSYMs/CelluloidTV.app.dSYM'
DWARF = DSYM + '/Contents/Resources/DWARF/CelluloidTV'
APP_FILES = package.APP_FILES
MAX_ENTRIES, MAX_BYTES, SCAN_SECONDS = 8192, 1024 ** 3, 30
MAX_REPORT = 2 * 1024 ** 2
ARCHIVE_RAW_CAP = 16 * 1024 ** 2
ARCHIVE_RETAIN_CAP = 512 * 1024
PRODUCT_ICON = 'Assets/ProductIcon.png'
MAX_PRODUCT_ICON_BYTES = 1024 * 1024
ARCHIVE_COMMAND = ['xcodebuild', '-project', 'CelluloidNative.xcodeproj',
    '-scheme', 'CelluloidTV', '-configuration', 'Release', '-destination',
    'generic/platform=tvOS', '-archivePath', str(ARCHIVE), '-derivedDataPath',
    'build/ArchiveDerived', 'ARCHS=arm64', 'ONLY_ACTIVE_ARCH=NO', 'CODE_SIGNING_ALLOWED=NO',
    'CODE_SIGNING_REQUIRED=NO', 'DEBUG_INFORMATION_FORMAT=dwarf-with-dsym',
    'COMPRESS_PNG_FILES=NO', 'archive']
PHASE_END = {'prepare': 180, 'archive': 800, 'proof': 910, 'final_source_pack': 940,
             'evidence': 1000, 'finalization': 1020}
MACH_MAGICS = package.MACH_MAGICS + (b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xce',
                                     b'\xbe\xba\xfe\xca', b'\xbf\xba\xfe\xca')


class Rejected(ValueError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def need(ok, reason):
    if not ok:
        raise Rejected(reason)


def timely(deadline, clock=time.monotonic):
    need(math.isfinite(deadline) and clock() < deadline, 'deadline-exceeded')


def retain_archive_output(receipt, stdout, stderr, *, capture_complete):
    """Scan the full bounded capture before retaining only labelled prefix/tail text.

    A stopped producer has only captured-prefix hashes, never a claimed full log.
    Full hashes use original bytes. Retention is bounded after UTF-8 replacement.
    """
    encoded=[raw.decode('utf-8','replace').encode('utf-8') for raw in (stdout,stderr)]
    first=min(len(encoded[0]),ARCHIVE_RETAIN_CAP//2)
    second=min(len(encoded[1]),ARCHIVE_RETAIN_CAP-first)
    budgets=[min(len(encoded[0]),ARCHIVE_RETAIN_CAP-second),second]
    marker=b'\n[... ARCHIVE LOG TRUNCATED: PREFIX + TAIL ...]\n'
    streams={}
    for name,raw,text,budget in zip(('stdout','stderr'),(stdout,stderr),encoded,budgets):
        truncated=len(text)>budget
        if not truncated:retained=text.decode('utf-8');prefix_bytes=len(text);tail_bytes=0
        elif budget<len(marker):retained='';prefix_bytes=tail_bytes=0
        else:
            prefix=(budget-len(marker))//2;tail=budget-len(marker)-prefix
            start=text[:prefix].decode('utf-8','ignore');end=text[-tail:].decode('utf-8','ignore') if tail else ''
            retained=start+marker.decode()+end;prefix_bytes=len(start.encode());tail_bytes=len(end.encode())
        receipt[name]=retained
        streams[name]={'captured_bytes':len(raw),'full_bytes':len(raw) if capture_complete else None,
            'full_sha256':hashlib.sha256(raw).hexdigest() if capture_complete else None,
            'captured_sha256':hashlib.sha256(raw).hexdigest(),'truncated':truncated,
            'retained_utf8_bytes':len(retained.encode()),'prefix_utf8_bytes':prefix_bytes,'tail_utf8_bytes':tail_bytes}
    complete=stdout+b'\n'+stderr
    error_found=re.search(rb'(?im)(?:^|[ :])(?:fatal )?error:',complete) is not None
    digest=hashlib.sha256();digest.update(stdout);digest.update(stderr)
    receipt['archive_log']={'capture_complete':capture_complete,'raw_capture_limit_bytes':ARCHIVE_RAW_CAP,
        'retention_limit_bytes':ARCHIVE_RETAIN_CAP,'captured_total_bytes':len(stdout)+len(stderr),
        'full_total_bytes':len(stdout)+len(stderr) if capture_complete else None,
        'full_sha256':digest.hexdigest() if capture_complete else None,'hash_order':'stdout bytes followed by stderr bytes; individual lengths and hashes retained',
        'retained_utf8_bytes':sum(row['retained_utf8_bytes'] for row in streams.values()),
        'truncated':any(row['truncated'] for row in streams.values()),'streams':streams,
        'error_marker_found':error_found,'error_scan_complete':capture_complete,
        'error_scan_scope':'all captured original stdout and stderr bytes, before retention truncation'}
    need(receipt['archive_log']['retained_utf8_bytes']<=ARCHIVE_RETAIN_CAP,'archive-retention-byte-limit')


def command(argv, *, deadline, seconds, cap, receipts, clock=time.monotonic,
            runner=capture, cleanup=2, archive_output=False):
    """One command grant with the existing helper's two cleanup phases reserved."""
    need(not archive_output or (argv==ARCHIVE_COMMAND and cap==ARCHIVE_RAW_CAP), 'archive-capture-scope-mismatch')
    start = clock()
    grant = min(seconds, deadline - start - 2 * cleanup)
    need(math.isfinite(grant) and grant > 0, 'command-cleanup-admission-expired')
    receipt = {'command': argv, 'start': start, 'grant_seconds': grant,
               'cleanup_reserve_seconds': 2 * cleanup, 'complete': False}
    receipts.append(receipt)
    try:
        result = runner(argv, seconds=grant, cap=cap, cleanup_grace=cleanup)
    except CaptureStopped as error:
        receipt.update(reason=str(error), owned_cleanup_confirmed=error.cleanup_confirmed,
                       cancelled_signal=error.cancelled_signal)
        stdout=getattr(error, 'stdout_prefix', b'')[:cap];stderr=getattr(error, 'stderr_capture', b'')[:cap]
        if archive_output:retain_archive_output(receipt,stdout,stderr,capture_complete=False)
        else:receipt.update(stdout=stdout.decode('utf-8','replace'),stderr=stderr.decode('utf-8','replace'))
        raise Rejected('capture-stopped') from error
    finally:
        receipt['end'] = clock()
    receipt.update(returncode=result.returncode, owned_host_observation='client-reaped-pipes-closed-group-absent-at-return')
    if archive_output:retain_archive_output(receipt,result.stdout,result.stderr,capture_complete=True)
    else:receipt.update(stdout=result.stdout.decode('utf-8','replace'),stderr=result.stderr.decode('utf-8','replace'))
    need(len(result.stdout) + len(result.stderr) <= cap, 'command-byte-limit')
    need(receipt['end'] < start + grant and receipt['end'] < deadline, 'command-late-return')
    need(result.returncode == 0, 'command-failed')
    if archive_output:need(clock()<start+grant and clock()<deadline,'command-late-return')
    if argv == ARCHIVE_COMMAND:
        need(re.search(rb'(?im)(?:^|[ :])(?:fatal )?error:', result.stdout + b'\n' + result.stderr) is None, 'archive-reported-error')
    receipt['complete'] = True
    return result.stdout


def environment(env):
    expected = {'GITHUB_REPOSITORY': '100mango/Celluloid', 'GITHUB_REF': BRANCH,
        'GITHUB_WORKFLOW_REF': '100mango/Celluloid/' + WORKFLOW + '@' + BRANCH,
        'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_JOB': 'archive',
        'DEVELOPER_DIR': '/Applications/Xcode_27.app/Contents/Developer'}
    need(all(env.get(k) == v for k, v in expected.items()), 'job-identity-mismatch')
    need(env.get('GITHUB_EVENT_NAME') == 'push', 'event-mismatch')
    sha = env.get('GITHUB_SHA', '')
    need(re.fullmatch('[0-9a-f]{40}', sha) is not None and env.get('GITHUB_WORKFLOW_SHA') == sha,
         'source-workflow-sha-mismatch')
    need(re.fullmatch('[1-9][0-9]{0,19}', env.get('GITHUB_RUN_ID', '')) is not None, 'run-identity-mismatch')
    return {k: env[k] for k in (*expected, 'GITHUB_EVENT_NAME', 'GITHUB_SHA',
                               'GITHUB_WORKFLOW_SHA', 'GITHUB_RUN_ID')}


def source_identity(env, run, root=ROOT):
    identity = environment(env)
    def git(*args):
        return run(['git', *args], seconds=5, cap=256 * 1024).decode().strip()
    need(git('rev-parse', 'HEAD') == identity['GITHUB_SHA'], 'head-mismatch')
    need(git('rev-parse', BASE + '^{tree}') == BASE_TREE, 'base-tree-mismatch')
    lineage = git('rev-list', '--parents', '-n', '1', 'HEAD').split()
    need(lineage == [identity['GITHUB_SHA'], PARENT], 'source-sole-parent-mismatch')
    identity['parents'] = lineage[1:]
    need(git('status', '--porcelain', '--untracked-files=all') == '', 'source-not-clean')
    differences = git('diff', '--name-status', BASE, 'HEAD', '--').splitlines()
    need(sorted(differences) == sorted(['A\t' + p for p in NEW_PATHS] + ['M\t' + p for p in MODIFIED_PATHS]), 'source-scope-mismatch')
    identity.update(tree=git('rev-parse', 'HEAD^{tree}'), base=BASE, base_tree=BASE_TREE)
    graph = package.source_graph(root)
    scheme = root / 'CelluloidNative.xcodeproj/xcshareddata/xcschemes/CelluloidTV.xcscheme'
    parsed = ET.fromstring(scheme.read_bytes())
    need(parsed.find('ArchiveAction').get('buildConfiguration') == 'Release', 'archive-configuration-mismatch')
    entries = parsed.findall('./BuildAction/BuildActionEntries/BuildActionEntry')
    archived = [e.find('BuildableReference') for e in entries if e.get('buildForArchiving') == 'YES']
    need(len(archived) == 1 and archived[0].get('BuildableName') == 'CelluloidTV.app'
         and archived[0].get('BlueprintName') == 'CelluloidTV'
         and archived[0].get('ReferencedContainer') == 'container:CelluloidNative.xcodeproj', 'archive-scheme-mismatch')
    paths = sorted(set(NEW_PATHS) | set(MODIFIED_PATHS) | set(package.contract(root)['unchanged_inputs']) | set(graph['resource_files']) | {
        'CelluloidNative.xcodeproj/project.pbxproj', scheme.relative_to(root).as_posix()})
    identity['files'] = {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths}
    identity['app_graph'] = graph
    return identity


def file_identity(value):
    return [value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns]


def product_icon_png(raw, deadline, *, clock=time.monotonic):
    """Bounded PNG container proof for Xcode's archive display icon; no pixel oracle."""
    observation = {'bytes': len(raw), 'prefix_hex': raw[:64].hex(), 'decoded_pixels_qualified': False}
    try:
        timely(deadline, clock)
        need(0 < len(raw) <= MAX_PRODUCT_ICON_BYTES, 'archive-icon-byte-limit')
        need(raw[:8] == b'\x89PNG\r\n\x1a\n', 'archive-icon-png-signature')
        offset, count, ihdr, idat, ended, cgbi = 8, 0, None, 0, False, False
        while offset < len(raw):
            timely(deadline, clock); count += 1
            need(count <= 4096 and offset + 12 <= len(raw), 'archive-icon-chunk-bounds')
            length = struct.unpack_from('>I', raw, offset)[0]
            kind = raw[offset+4:offset+8]; end = offset + 12 + length
            need(end <= len(raw) and all(65 <= x <= 90 or 97 <= x <= 122 for x in kind), 'archive-icon-chunk-bounds')
            data = raw[offset+8:offset+8+length]
            crc = struct.unpack_from('>I', raw, offset+8+length)[0]
            need(zlib.crc32(kind + data) & 0xffffffff == crc, 'archive-icon-chunk-crc')
            if kind == b'CgBI':
                need(count == 1 and not cgbi and ihdr is None, 'archive-icon-cgbi-order'); cgbi = True
            elif kind == b'IHDR':
                need(ihdr is None and length == 13 and count == (2 if cgbi else 1), 'archive-icon-ihdr')
                width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', data)
                need(0 < width <= 8192 and 0 < height <= 8192 and width * height <= 16 * 1024 * 1024, 'archive-icon-dimensions')
                need(depth in {0:(1,2,4,8,16),2:(8,16),3:(1,2,4,8),4:(8,16),6:(8,16)}.get(color,()), 'archive-icon-pixel-format')
                need(compression == filtering == 0 and interlace in (0,1), 'archive-icon-png-method')
                ihdr = {'width':width,'height':height,'bit_depth':depth,'color_type':color,'interlace':interlace}
                observation.update(ihdr)
            elif kind == b'IDAT':
                need(ihdr is not None and not ended, 'archive-icon-idat-order'); idat += length
            elif kind == b'IEND':
                need(length == 0 and ihdr is not None and idat > 0 and end == len(raw), 'archive-icon-terminal-boundary')
                ended = True
            else:
                need(ihdr is not None and not ended, 'archive-icon-chunk-order')
            offset = end
        need(ihdr is not None and ended, 'archive-icon-incomplete-png')
        timely(deadline, clock)
        observation.update(chunks=count, cgbi=cgbi, container_qualified=True)
        return observation
    except Rejected as error:
        error.icon_observation = observation
        raise


def scan(archive, deadline, *, clock=time.monotonic, hash_files=True):
    """Original strict predicates, with explicit context for the first rejection."""
    current = {'path': '.', 'type': 'unread'}
    try:
        deadline = min(deadline, clock() + SCAN_SECONDS)
        root_stat = archive.lstat()
        current = diagnostics.record('.', root_stat)
        need(stat.S_ISDIR(root_stat.st_mode), 'archive-missing-or-linked')
        paths, pending, total = {'.': {'identity': file_identity(root_stat)}}, [archive], 0
        while pending:
            folder = pending.pop()
            timely(deadline, clock)
            with os.scandir(folder) as entries:
                for entry in entries:
                    path = Path(entry.path); key = path.relative_to(archive).as_posix()
                    current = {'path': key[:1024], 'type': 'unread', 'path_truncated': len(key)>1024}
                    timely(deadline, clock)
                    need(len(paths) <= MAX_ENTRIES, 'archive-entry-limit')
                    need(len(key) <= 1024, 'archive-path-limit')
                    value = path.lstat(); mode = value.st_mode
                    current = diagnostics.record(key, value)
                    need(stat.S_ISDIR(mode) or stat.S_ISREG(mode), 'archive-linked-or-nonregular')
                    need(not stat.S_ISREG(mode) or value.st_nlink == 1, 'archive-hardlink')
                    need(path.name not in ('Watch', '_CodeSignature', 'CodeResources', 'embedded.mobileprovision')
                         and path.suffix.lower() not in ('.appex', '.framework', '.xctest', '.dylib', '.mobileprovision')
                         and 'Fixtures' not in key, 'unexpected-code-or-signature')
                    need(path.suffix not in ('.app', '.dSYM') or key in (APP, DSYM), 'unexpected-product')
                    allowed = key in ('Info.plist', 'Products', 'Products/Applications', APP, 'dSYMs', DSYM, 'Assets', PRODUCT_ICON)
                    allowed = allowed or key.startswith(APP + '/') or key.startswith(DSYM + '/')
                    need(allowed, 'unexpected-archive-entry')
                    if key == 'Assets':
                        need(stat.S_ISDIR(mode), 'archive-assets-not-directory')
                    if key == PRODUCT_ICON:
                        need(stat.S_ISREG(mode) and value.st_size <= MAX_PRODUCT_ICON_BYTES, 'archive-icon-not-bounded-regular-file')
                    receipt = {'identity': file_identity(value)}; paths[key] = receipt
                    if stat.S_ISDIR(mode):
                        pending.append(path); continue
                    total += value.st_size
                    need(total <= MAX_BYTES, 'archive-byte-limit')
                    need(key in (APP + '/CelluloidTV', DWARF) or not mode & 0o111, 'unexpected-executable')
                    if hash_files:
                        h = hashlib.sha256(); count = 0; prefix = b''
                        icon_raw = bytearray() if key == PRODUCT_ICON else None
                        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                        with os.fdopen(os.open(path, flags), 'rb') as stream:
                            need(file_identity(os.fstat(stream.fileno())) == receipt['identity'], 'archive-file-changed')
                            while chunk := stream.read(1024 * 1024):
                                timely(deadline, clock); count += len(chunk)
                                need(count <= value.st_size, 'archive-file-grew')
                                if not prefix: prefix = chunk[:4]
                                h.update(chunk)
                                if icon_raw is not None: icon_raw.extend(chunk)
                            need(file_identity(os.fstat(stream.fileno())) == receipt['identity'], 'archive-file-changed')
                        need(count == value.st_size, 'archive-file-changed')
                        need(prefix not in MACH_MAGICS or key in (APP + '/CelluloidTV', DWARF), 'unexpected-mach-o')
                        receipt.update(bytes=count, sha256=h.hexdigest())
                        if icon_raw is not None:
                            receipt['png'] = product_icon_png(bytes(icon_raw), deadline, clock=clock)
        for key, receipt in paths.items():
            current = {'path': key, 'type': 'snapshot-recheck'}
            timely(deadline, clock)
            need(file_identity((archive / key).lstat()) == receipt['identity'], 'archive-snapshot-changed')
        timely(deadline, clock)
        return {'paths': paths, 'entries': len(paths) - 1, 'bytes': total}
    except (Exception, KeyboardInterrupt) as error:
        error.offending_entry = current
        raise


def matching_uuid(raw, executable, dwarf):
    rows = raw.decode('utf-8').splitlines(); found = {}
    pattern = r'UUID: ([0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}) \(arm64\) (.+)'
    for line in rows:
        match = re.fullmatch(pattern, line)
        need(match is not None, 'uuid-output-invalid')
        uuid, path = match.groups()
        need(path in (str(executable), str(dwarf)) and path not in found, 'uuid-product-mismatch')
        need(uuid.replace('-', '').strip('0'), 'uuid-zero')
        found[path] = uuid.upper()
    need(len(found) == 2 and len(set(found.values())) == 1, 'uuid-mismatch')
    return next(iter(found.values()))


def read_metadata(path, deadline, clock):
    timely(deadline, clock)
    need(path.lstat().st_size <= 1024 * 1024, 'metadata-byte-limit')
    with path.open('rb') as stream:
        raw = stream.read(1024 * 1024 + 1)
    need(len(raw) <= 1024 * 1024, 'metadata-byte-limit')
    result = plistlib.loads(raw)
    timely(deadline, clock)
    need(isinstance(result, dict), 'metadata-not-dictionary')
    return result


def compiled_asset_dimensions(raw):
    """Use Apple's native CAR decoder, rather than treating any nonempty file as assets."""
    values = json.loads(raw)
    need(isinstance(values, list) and 0 < len(values) <= 2048, 'compiled-asset-inventory-invalid')
    observed = []
    for value in values:
        need(isinstance(value, dict), 'compiled-asset-record-invalid')
        width, height = value.get('PixelWidth'), value.get('PixelHeight')
        if width is not None or height is not None:
            need(type(width) is int and type(height) is int and width > 0 and height > 0,
                 'compiled-asset-dimensions-invalid')
            observed.append({'name': value.get('Name'), 'rendition': value.get('RenditionName'),
                             'width': width, 'height': height, 'scale': value.get('Scale')})
    sizes = {(x['width'], x['height']) for x in observed}
    required = {(400, 240), (800, 480), (1280, 768), (1920, 720), (2320, 720)}
    need(required <= sizes, 'compiled-asset-scale-coverage-missing')
    # Bind the existing top-shelf slots to their real catalog role, not an unrelated image.
    named={(x['name'],x['width'],x['height'],x['scale']) for x in observed}
    need({('Small',400,240,1),('Small',800,480,2),('Large/Back/Content',1280,768,1)} <= named, 'compiled-brand-role-scale-mismatch')
    needed={('TopShelf',1920,720,1),
            ('TopShelfWide',2320,720,1)}
    need(needed <= named, 'compiled-top-shelf-role-scale-mismatch')
    return {'required_dimensions': [list(v) for v in sorted(required)], 'observed': observed,
            'raw_sha256': hashlib.sha256(raw).hexdigest(), 'raw_bytes': len(raw)}


def verify_archive(archive, run, deadline, *, root=ROOT, clock=time.monotonic):
    started = clock()
    before = scan(archive, deadline, clock=clock)
    app = archive / APP; executable = app / 'CelluloidTV'; dwarf = archive / DWARF
    need({k[len(APP)+1:] for k,v in before['paths'].items() if k.startswith(APP+'/') and 'sha256' in v} == APP_FILES, 'app-resource-inventory-mismatch')
    metadata = read_metadata(archive / 'Info.plist', deadline, clock)
    need(type(metadata.get('ArchiveVersion')) is int and metadata['ArchiveVersion'] == 2
         and metadata.get('SchemeName') == 'CelluloidTV', 'archive-metadata-mismatch')
    need(isinstance(metadata.get('CreationDate'), datetime.datetime), 'archive-creation-metadata-missing')
    result = package.verify(app, 'device', True, root=root, clock=clock)
    timely(deadline, clock)
    compiled_assets = compiled_asset_dimensions(run(['xcrun', 'assetutil', '--info', str(app/'Assets.car')], seconds=15, cap=256*1024, cleanup=10))
    timely(deadline, clock)
    need(set(result['files']) == {'app/' + p for p in APP_FILES}, 'app-resource-inventory-mismatch')
    need(set(result['binaries']) == {'app/CelluloidTV'}, 'app-code-inventory-mismatch')
    properties = metadata.get('ApplicationProperties', {})
    need(properties.get('ApplicationPath') == 'Applications/CelluloidTV.app', 'archive-application-path-mismatch')
    for key in ('CFBundleIdentifier', 'CFBundleShortVersionString', 'CFBundleVersion'):
        need(properties.get(key) == result['metadata'][key], 'archive-application-identity-mismatch')
    need(not any(properties.get(k) for k in ('SigningIdentity', 'Team')), 'archive-signing-identity-present')
    dsym_info = read_metadata(archive / DSYM / 'Contents/Info.plist', deadline, clock)
    need(dsym_info.get('CFBundleIdentifier') == 'com.apple.xcode.dsym.Mango.Celluloid'
         and dsym_info.get('CFBundlePackageType') == 'dSYM', 'dsym-metadata-mismatch')
    # dsymutil may emit default or missing versions. Preserve and compare the
    # observed values without treating them as a qualification gate.
    dsym_versions = {key: {'observed': dsym_info.get(key),
        'comparison': ('missing' if key not in dsym_info else
                       'same' if dsym_info[key] == result['metadata'][key] else 'different')}
        for key in ('CFBundleVersion', 'CFBundleShortVersionString')}
    # UUID matching alone must not turn an arbitrary file into a DWARF object.
    with dwarf.open('rb') as stream:
        header = stream.read(32)
    need(len(header) == 32 and header[:4] == b'\xcf\xfa\xed\xfe', 'dsym-mach-o-missing')
    values = struct.unpack('<8I', header)
    need(values[1] == 0x100000c and values[3] == 10 and values[7] == 0, 'dsym-mach-o-identity-mismatch')
    uuid = matching_uuid(run(['xcrun', 'dwarfdump', '--uuid', str(executable), str(dwarf)],
        seconds=10, cap=8192, cleanup=10), executable, dwarf)
    after = scan(archive, deadline, clock=clock, hash_files=False)
    need(before['entries'] == after['entries'] and before['bytes'] == after['bytes']
         and {k: v['identity'] for k, v in before['paths'].items()} ==
             {k: v['identity'] for k, v in after['paths'].items()}, 'archive-changed-during-proof')
    for key, receipt in result['files'].items():
        observed = before['paths'][APP + '/' + key[4:]]
        need(receipt == {k: observed[k] for k in ('bytes', 'sha256')}, 'app-snapshot-mismatch')
    timely(deadline, clock)
    return {'archive': before, 'metadata': metadata, 'dsym_metadata': dsym_info,
            'app': result, 'compiled_assets': compiled_assets, 'dsym_version_observations': dsym_versions,
            'arm64_uuid': uuid, 'elapsed_seconds': clock() - started,
            'limits': {'entries': MAX_ENTRIES, 'bytes': MAX_BYTES, 'scan_seconds': SCAN_SECONDS},
            'observation': 'stable-file-identities-around-package-and-uuid-inspection'}


def json_value(value):
    if isinstance(value, datetime.datetime):
        return {'plist_date': value.isoformat()}
    if isinstance(value, bytes):
        return {'plist_data_hex': value.hex()}
    raise TypeError(type(value).__name__)


def report_bytes(report):
    raw = (json.dumps(report, sort_keys=True, default=json_value, allow_nan=False, separators=(',', ':')) + '\n').encode()
    if len(raw) > MAX_REPORT:
        report = {k: report[k] for k in ('schema', 'qualified', 'signing_qualified', 'store_qualified',
                    'older_os_qualified', 'ui_qualification_separate', 'failure', 'archive_diagnostic') if k in report}
        report['qualified'] = False
        report.setdefault('failure', {'type': 'Rejected', 'reason': 'report-byte-limit'})
        report['retention_failure'] = {'reason': 'report-byte-limit', 'preserved': 'original failure and bounded archive diagnostic'}
        raw = (json.dumps(report, sort_keys=True, default=json_value, allow_nan=False) + '\n').encode()
        need(len(raw) <= MAX_REPORT, 'bounded-diagnostic-report-byte-limit')
    return raw


def execute(*, env=None, root=ROOT, clock=time.monotonic, runner=capture):
    env = os.environ if env is None else env
    began = clock(); receipts = []; phase = 'prepare'; phase_deadline = began + 180
    report = {'schema': 1, 'scope': 'tv-release-unsigned-archive-observation', 'qualified': False,
        'signing_qualified': False, 'store_qualified': False, 'older_os_qualified': False,
        'ui_qualification_separate': True, 'binary_handoff': False, 'commands': receipts,
        'functional_evidence_reused': {'source': BASE, 'two_source_run':37584551671, 'remaining_run':37596611181, 'product_code_unchanged':True, 'native_ui_rerun':False, 'system_settings_text_size_propagation':False},
        'upload_qualified': False, 'qualification_scope': 'archive-observation-before-retention',
        'clock': {'started_monotonic': began, 'phase_end_seconds': PHASE_END,
                  'report_ready_deadline': began + PHASE_END['final_source_pack']},
        'host_scope': 'owned-client-and-process-group-observation; no independent-daemon lifetime claim'}
    def run(argv, **kwargs):
        return command(argv, deadline=phase_deadline, receipts=receipts,
                       clock=clock, runner=runner, **kwargs)
    try:
        need(not (root / 'build').exists() and not (root / 'build').is_symlink(), 'output-not-fresh')
        (root / 'build').mkdir()
        report['owned_output'] = file_identity((root / 'build').lstat())[:2]
        report['source_before'] = source_identity(env, run, root)
        report['toolchain'] = {
            'os': run(['sw_vers'], seconds=5, cap=4096).decode(),
            'xcode': run(['xcodebuild', '-version'], seconds=10, cap=4096).decode(),
            'sdks': run(['xcodebuild', '-showsdks'], seconds=15, cap=16384).decode()}
        need(report['toolchain']['xcode'].strip().splitlines() == ['Xcode 27.0', 'Build version 27A266a'], 'toolchain-mismatch')
        need('appletvos27.0' in report['toolchain']['sdks'], 'sdk-mismatch')
        for optimize in ([], ['-O']):
            for test_file in ('test_tv_archive_capture.py', 'test_tv_archive_diagnostics.py', 'test_tv_release_archive.py'):
                run([sys.executable, *optimize, '-m', 'unittest', 'discover', '-s', 'Scripts',
                     '-p', test_file], seconds=40, cap=65536)
        report['native_icon_materialization'] = run(['swift', 'Scripts/materialize_tv_archive_assets.swift'], seconds=40, cap=16384).decode()
        report['icon_inputs_before'] = package.verify_generated_icons(root, env)
        timely(began + PHASE_END['prepare'], clock)
        phase = 'archive'; phase_deadline = min(began + PHASE_END[phase], clock() + 620)
        run(ARCHIVE_COMMAND, seconds=600, cap=ARCHIVE_RAW_CAP, cleanup=10, archive_output=True)
        phase = 'proof'; phase_deadline = min(began + PHASE_END[phase], clock() + 110)
        report['archive_diagnostic'] = diagnostics.collect(root / ARCHIVE, phase_deadline, clock=clock)
        report['proof'] = verify_archive(root / ARCHIVE, run, phase_deadline, root=root, clock=clock)
        phase = 'final_source_pack'; phase_deadline = min(began + PHASE_END[phase], clock() + 30)
        report['clock']['report_ready_deadline'] = phase_deadline
        report['source_after'] = source_identity(env, run, root)
        report['icon_inputs_after'] = package.verify_generated_icons(root, env)
        need(report['icon_inputs_before'] == report['icon_inputs_after'], 'generated-icons-changed')
        need(report['source_after'] == report['source_before'], 'source-changed')
        timely(phase_deadline, clock)
        report['qualified'] = True
    except (Exception, KeyboardInterrupt) as error:
        report['failure'] = {'phase': phase, 'type': type(error).__name__,
                             'reason': str(error)[:4096]}
        # A timely, fully reaped exit-zero client can still print a compiler
        # error. Preserve that failed gate and observe only files already left
        # by this one archive command; never run native validators or retry it.
        receipt = receipts[-1] if receipts else {}
        returned = (phase == 'archive' and type(error) is Rejected
            and error.reason == 'archive-reported-error'
            and receipt.get('command') == ARCHIVE_COMMAND
            and receipt.get('returncode') == 0 and receipt.get('complete') is False
            and receipt.get('owned_host_observation') == 'client-reaped-pipes-closed-group-absent-at-return'
            and receipt.get('end', float('inf')) < phase_deadline
            and receipt.get('end', float('inf')) < receipt.get('start', 0) + receipt.get('grant_seconds', 0))
        if returned:
            observed_at = clock()
            deadline = min(began + PHASE_END['proof'],
                           began + PHASE_END['final_source_pack'] - 30,
                           observed_at + diagnostics.MAX_SECONDS)
            if observed_at < deadline:
                try:
                    report['archive_diagnostic'] = diagnostics.collect(root / ARCHIVE, deadline, clock=clock)
                except (Exception, KeyboardInterrupt) as observation_error:
                    report['archive_diagnostic'] = {'qualifying': False,
                        'failure': {'type': type(observation_error).__name__,
                                    'reason': str(observation_error)[:1024]}}
                report['archive_diagnostic']['trigger'] = 'timely-exit-zero-with-error-output; original failure retained'
            else:
                report['archive_diagnostic'] = {'qualifying': False,
                    'stopped': 'original-diagnostic-clock-exhausted'}
        report['clock']['report_ready_deadline'] = min(report['clock']['report_ready_deadline'], clock() + 30)
        if hasattr(error, 'offending_entry'):
            report['failure']['offending_entry'] = error.offending_entry
        if hasattr(error, 'icon_observation'):
            report['failure']['icon_observation'] = error.icon_observation
    report['clock']['elapsed_seconds'] = clock() - began
    return report


def retain_report(result, output, marker, *, clock=time.monotonic):
    """Finish every report/marker write against the original final phase clock."""
    deadline = result['clock']['report_ready_deadline']
    offset = None
    try:
        timely(deadline, clock)
        output.mkdir(exist_ok=False)
        payload = report_bytes(result)
        timely(deadline, clock)
        (output / 'report.json').write_bytes(payload)
        timely(deadline, clock)
        # This is the current step's owned output file. Roll back this append if
        # it returns late, so a late artifact cannot gain upload admission.
        with marker.open('a+', encoding='utf-8') as stream:
            stream.seek(0, os.SEEK_END); offset = stream.tell()
            stream.write('evidence_ready=true\n'); stream.flush()
            if clock() >= deadline:
                stream.truncate(offset)
                raise Rejected('deadline-exceeded')
        timely(deadline, clock)
        return json.loads(payload)
    except Rejected as error:
        if offset is not None:
            with marker.open('r+', encoding='utf-8') as stream:
                stream.truncate(offset)
        result['qualified'] = False
        result['failure'] = {'phase': 'final_source_pack', 'type': type(error).__name__, 'reason': str(error)}
        # Local typed failure only: no new command and no upload admission.
        if output.is_dir() and not output.is_symlink():
            (output / 'report.json').write_bytes(report_bytes(result))
        return result


def upload_ceiling(result):
    value = result.get('clock', {})
    began = value.get('started_monotonic')
    need(type(began) in (int, float) and math.isfinite(began) and began >= 0
         and value.get('phase_end_seconds') == PHASE_END, 'upload-clock-identity-mismatch')
    return began, began + PHASE_END['evidence'], began + PHASE_END['finalization']


def admit_upload(result, *, clock=time.monotonic):
    began, evidence_end, global_end = upload_ceiling(result)
    now = clock()
    # Full action timeout plus the original finalization reserve. No fresh clock.
    need(began <= now and now + 60 < evidence_end and now + 80 < global_end,
         'upload-full-admission-expired')
    return {'status': 'admitted', 'admitted_monotonic': now,
        'elapsed_at_admission': now - began, 'evidence_deadline': evidence_end,
        'global_deadline': global_end, 'action_timeout_seconds': 60,
        'finalization_reserve_seconds': 20, 'upload_qualified': False,
        'interval_scope': 'admission-through-post-action-observation-including-step-delays'}


def finish_upload(result, outcome, *, clock=time.monotonic):
    began, evidence_end, global_end = upload_ceiling(result)
    admission = result.get('upload_observation', {})
    started = admission.get('admitted_monotonic')
    now = clock()
    receipt = {'scope': 'post-upload-clock-gate', 'upload_qualified': False,
        'archive_qualified': result.get('qualified') is True,
        'action_outcome': outcome, 'started_monotonic': started,
        'observed_finished_monotonic': now, 'elapsed_since_original_start': now - began,
        'evidence_deadline': evidence_end, 'global_deadline': global_end,
        'interval_scope': 'includes-action-setup-and-inter-step-delay'}
    if (type(started) not in (int, float) or not math.isfinite(started)
            or admission.get('status') != 'admitted' or started < began
            or started + 60 >= evidence_end or started + 80 >= global_end
            or admission.get('evidence_deadline') != evidence_end
            or admission.get('global_deadline') != global_end or not math.isfinite(now) or now < started):
        receipt['failure'] = 'upload-admission-identity-mismatch'
    elif outcome != 'success':
        receipt['failure'] = 'upload-action-not-successful'
    elif now >= global_end:
        receipt['failure'] = 'upload-global-deadline-exceeded'
    elif now >= evidence_end:
        receipt['failure'] = 'upload-evidence-deadline-exceeded'
    elif now >= started + 60:
        receipt['failure'] = 'upload-admitted-phase-exceeded'
    else:
        receipt['upload_qualified'] = True
    return receipt


def upload_gate(mode, *, root=ROOT, env=None, clock=time.monotonic):
    env = os.environ if env is None else env
    identity = environment(env)
    path = root / 'build/archive-proof/report.json'
    before = path.lstat()
    need(stat.S_ISREG(before.st_mode) and before.st_size <= MAX_REPORT, 'upload-report-invalid')
    with path.open('rb') as stream:
        payload = stream.read(MAX_REPORT + 1)
    need(len(payload) <= MAX_REPORT and file_identity(path.lstat()) == file_identity(before),
         'upload-report-changed')
    result = json.loads(payload)
    need(all(result.get('source_before', {}).get(k) == v for k, v in identity.items()),
         'upload-source-run-mismatch')
    if mode == 'finish-upload':
        receipt = finish_upload(result, env.get('CELLULOID_ARCHIVE_UPLOAD_OUTCOME', ''), clock=clock)
        # The uploaded proof explicitly leaves upload_qualified=false. This
        # final workflow log receipt is the separate retention qualification.
        print(json.dumps(receipt, sort_keys=True))
        _, _, global_end = upload_ceiling(result)
        admitted = result['upload_observation']['admitted_monotonic']
        timely(min(global_end, admitted + 80), clock)
        return 0 if receipt['upload_qualified'] else 1
    need(mode == 'admit-upload', 'unknown-upload-gate')
    result['upload_observation'] = admit_upload(result, clock=clock)
    payload = report_bytes(result)
    need(json.loads(payload).get('upload_observation') == result['upload_observation'], 'upload-report-byte-limit')
    path.write_bytes(payload)
    admit_upload(result, clock=clock)  # Report packing must not consume admission.
    marker = Path(env['GITHUB_OUTPUT']); offset = None
    try:
        with marker.open('a+', encoding='utf-8') as stream:
            stream.seek(0, os.SEEK_END); offset = stream.tell()
            stream.write('upload_admitted=true\n'); stream.flush()
            admit_upload(result, clock=clock)
        admit_upload(result, clock=clock)
        print(json.dumps(result['upload_observation'], sort_keys=True))
        admit_upload(result, clock=clock)
    except Rejected:
        if offset is not None:
            with marker.open('r+', encoding='utf-8') as stream:
                stream.truncate(offset)
        raise
    return 0


def main():
    os.chdir(ROOT)
    if len(sys.argv) == 2 and sys.argv[1] in ('admit-upload', 'finish-upload'):
        return upload_gate(sys.argv[1])
    need(len(sys.argv) == 1, 'no-input-selectors')
    result = execute()
    output = ROOT / 'build/archive-proof'
    # Never follow an existing output path after a failed freshness check.
    if 'owned_output' not in result:
        print(json.dumps(result, default=json_value)); return 1
    need(stat.S_ISDIR((ROOT / 'build').lstat().st_mode) and
         file_identity((ROOT / 'build').lstat())[:2] == result['owned_output'], 'output-ownership-changed')
    decoded = retain_report(result, output, Path(os.environ['GITHUB_OUTPUT']))
    print(json.dumps({'qualified': decoded['qualified'], 'failure': decoded.get('failure')}))
    return 0 if decoded['qualified'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
