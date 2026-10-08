#!/usr/bin/env python3
"""Default-disabled, one real editor checkpoint. No product edits or Apple upload."""
import sys
_RESOLVER_MODE = __name__ == '__main__' and sys.argv[1:2] == ['--resolve-container']
_RESOLVER_ENTRY = 'VISION_RESOLVER_STAGE {"stage":"script-entry","elapsed_seconds":0}\n'
if _RESOLVER_MODE:
    sys.stderr.write(_RESOLVER_ENTRY); sys.stderr.flush()
import time
_RESOLVER_STARTED = time.monotonic()
_RESOLVER_STAGE_COUNT = 1 if _RESOLVER_MODE else 0
_RESOLVER_STAGE_BYTES = len(_RESOLVER_ENTRY) if _RESOLVER_MODE else 0
import argparse
import hashlib
import json
import math
import os
import plistlib
import re
import stat
import uuid
from pathlib import Path
def load_native_helpers():
    global capture, CaptureStopped, stream_capture, ARCHIVE_RAW_CAP, retain_archive_output
    global built_vision_app, write_synthetic_fixture, snapshot_fixture, test_command
    global verify_cases, synthetic_fixture_bytes, FIXTURE_NAME
    from mac_archive_capture import capture, CaptureStopped
    from vision_store_stream import capture as stream_capture
    from vision_remaining_retention import ARCHIVE_RAW_CAP, retain_archive_output
    from run_vision_remaining import (built_vision_app, write_synthetic_fixture,
        snapshot_fixture, test_command, verify_cases, synthetic_fixture_bytes, FIXTURE_NAME)


# Preserve the imported host-test API. CLI resolver/pack/verdict/default modes
# need only standard libraries and never initialize native helper modules.
if __name__ != '__main__': load_native_helpers()

BASE = '10a022a85b134caa5f20c2fee431967f836e3049'
EDITOR_OPEN_SOURCE = 'abe9fc5560b230edc93b0312ef78b26b3d3dab55'
BASE_TREE = '016cc0d7d64bcbf21c8bd099b0e7178f6c59296f'
BRANCH = 'refs/heads/codex/vision-store-single'
WORKFLOW = '.github/workflows/vision-store-single.yml'
SELECTOR = 'CelluloidVisionUITests/NativeVisionUITests/testStoreSingleHeldEditorCapture'
APP_ID = 'Mango.Celluloid'
RUNNER_ID = 'Mango.Celluloid.CelluloidVisionUITests.xctrunner'
CLOCK = 'vision-store-clock.json'
FOLDER = 'vision-store-evidence'
BARRIER = 'vision-store-device-uncertain.json'
WORK_END, CLEANUP_END, PACK_END, FINISH_END = 1800, 1920, 2160, 2400
FAILURE_TAIL_CAP = 32_768
DIAGNOSTICS = 'vision-store-diagnostics'
DIAGNOSTIC_FILES = {'bootstrap.json': 16_384, 'report.json': 500_000, 'failure-tail.log': FAILURE_TAIL_CAP}
# Parent-approved local bounds only; native admission remains disabled.
ORIGINAL_CAP, STORE_CAP, EVIDENCE_CAP = 16_000_000, 3_000_000, 24_000_000
REPORT_CAP = 500_000
EVIDENCE_FILES = {name: cap for name, cap in (
    ('report.json', REPORT_CAP), ('manifest.json', 32_768),
    ('capture-original.jpeg', ORIGINAL_CAP), ('store-image.jpeg', STORE_CAP),
    ('build.log', 524_298), ('ui.log', 524_298), ('screenshot.log', 524_298),
    ('shutdown.log', 524_298), ('delete.log', 524_298),
    (BARRIER, 32_768), ('native-icon-provenance-runtime.json', 1_000_000))}
ADDED = ()
MODIFIED = (WORKFLOW,
    'Scripts/run_vision_store_capture.py', 'Scripts/test_vision_store_capture.py')
REQUEST_PREFIX = 'CELLULOID_STORE_CAPTURE_REQUEST '
METADATA_NAME = '.com.apple.mobile_container_manager.metadata.plist'
# Conservative resource ceilings, not a claim about unmeasured visionOS counts.
# Reuse the reviewed per-query ceiling; original work/held deadlines still bind.
METADATA_CAP, METADATA_TOTAL_CAP, METADATA_ENTRIES, METADATA_SECONDS = 262_144, 16_777_216, 4096, 180
RESOLVER_STAGE_CAP, RESOLVER_STAGE_LIMIT = 8192, 32
HOST_CONTROL_SECONDS, HOST_CONTROL_CAP = 30, 1024
HOST_CONTROL_PHASES = ('host-control-before-boot','host-control-after-boot')
HOST_CONTROL_SCRIPT = ('import time\n'
    'print("VISION_HOST_CONTROL_ENTRY",time.monotonic(),flush=True)\n'
    'print("VISION_HOST_CONTROL_EXIT",time.monotonic(),flush=True)\n')
RESOLVER_FAILURE_STEPS = frozenset(('root','scan-open','scan-next','entry-limit','entry-stat',
    'entry-type','entry-uuid','entry-open','entry-stat-open','entry-stability','entry-close',
    'metadata-open','metadata-stat','metadata-type','metadata-links','metadata-size','metadata-read',
    'metadata-restat','metadata-stability','metadata-parse','metadata-identifier','metadata-uuid',
    'metadata-receipt','metadata-close','total-limit','target-missing','target-ambiguous'))
RESOLVER_REASONS = {'Noncanonical metadata root':'root-noncanonical',
    'Metadata entry count exceeded':'entry-limit','Metadata directory link rejected':'entry-symlink',
    'Invalid UUID':'invalid-uuid','Container changed during scan':'entry-changed',
    'Unsafe metadata file':'unsafe-metadata','Metadata changed during read':'metadata-changed',
    'Duplicate metadata key':'duplicate-key','Malformed metadata identity':'identity-malformed',
    'Metadata total bytes exceeded':'total-limit',
    'Container identity missing or ambiguous':'target-count'}
RESOLVER_REASON_CODES = frozenset(RESOLVER_REASONS.values()) | frozenset((
    'os-error','plist-invalid','value-rejected','unexpected-exception'))
CONTAINER_PHASES = {'seed-data': (APP_ID, 'Data'), 'capture-data': (APP_ID, 'Data'),
    'capture-runner': (RUNNER_ID, 'Data'), 'after-data': (APP_ID, 'Data'),
    'capture-installed': (APP_ID, 'Bundle'), 'after-installed': (APP_ID, 'Bundle')}


def need(value, message):
    if not value: raise ValueError(message)


def resolver_stage(stage, entries=0, metadata_bytes=0, matches=0, failure=None):
    """Fixed vocabulary and aggregate counters only; never identity or paths."""
    global _RESOLVER_STAGE_COUNT, _RESOLVER_STAGE_BYTES
    if not _RESOLVER_MODE: return
    need(stage in ('stdlib-ready','binding-start','binding-ready','root-open','root-ready',
        'scan-count','match-complete','lookup-failed','failed'), 'Invalid resolver stage')
    need(all(type(v) is int and v >= 0 for v in (entries,metadata_bytes,matches)), 'Invalid resolver counters')
    elapsed = time.monotonic()-_RESOLVER_STARTED
    need(math.isfinite(elapsed) and elapsed >= 0, 'Invalid resolver stage clock')
    row = {'stage':stage,'elapsed_seconds':round(elapsed,6),'entries_seen':entries,
        'metadata_bytes':metadata_bytes,'matches':matches}
    if failure is not None:
        need(stage == 'lookup-failed' and type(failure) is dict
            and set(failure) == {'failure_step','reason','errno'}, 'Invalid resolver failure fields')
        need(failure['failure_step'] in RESOLVER_FAILURE_STEPS
            and failure['reason'] in RESOLVER_REASON_CODES, 'Invalid resolver failure enum')
        code = failure['errno']
        need(code is None or (type(code) is int and 0 < code <= 4095), 'Invalid resolver errno')
        row.update(failure)
    line = 'VISION_RESOLVER_STAGE '+json.dumps(row,separators=(',',':'))+'\n'
    size = len(line.encode())
    need(_RESOLVER_STAGE_COUNT < RESOLVER_STAGE_LIMIT and _RESOLVER_STAGE_BYTES+size <= RESOLVER_STAGE_CAP,
        'Resolver diagnostic cap')
    _RESOLVER_STAGE_COUNT += 1; _RESOLVER_STAGE_BYTES += size
    sys.stderr.write(line); sys.stderr.flush()


def resolver_failure(step, error):
    """Return only fixed diagnostic tokens; never exception text or paths."""
    need(step in RESOLVER_FAILURE_STEPS, 'Invalid resolver failure step')
    reason, code = 'unexpected-exception', None
    if isinstance(error, OSError):
        reason = 'os-error'
        if type(error.errno) is int and 0 < error.errno <= 4095: code = error.errno
    elif isinstance(error, ValueError):
        reason = RESOLVER_REASONS.get(str(error), 'value-rejected')
        if step in ('entry-uuid','metadata-uuid') and reason == 'value-rejected': reason = 'invalid-uuid'
    if step == 'metadata-parse' and reason in ('value-rejected','unexpected-exception'): reason = 'plist-invalid'
    return {'failure_step':step,'reason':reason,'errno':code}


def host_loadavg():
    try:
        load = os.getloadavg()
        if len(load) == 3 and all(type(v) in (int,float) and math.isfinite(v) and v >= 0 for v in load):
            return list(load)
    except (AttributeError,OSError): pass
    return None


def host_snapshot():
    """Bounded aggregate OS counters only; no process, path or environment data."""
    def positive(read, cap, zero=False):
        try:
            value = read()
            return value if type(value) is int and (0 <= value if zero else 0 < value) and value <= cap else None
        except (AttributeError,OSError,ValueError): return None
    cpu = positive(lambda: os.cpu_count(),4096)
    page = positive(lambda: os.sysconf('SC_PAGE_SIZE'),1_048_576)
    pages = positive(lambda: os.sysconf('SC_PHYS_PAGES'),1<<48)
    available = positive(lambda: os.sysconf('SC_AVPHYS_PAGES'),1<<48,zero=True)
    memory = page*pages if page is not None and pages is not None else None
    free = page*available if page is not None and available is not None else None
    return {'logical_cpu_capacity':cpu,'physical_memory_capacity_bytes':memory,
        'available_physical_memory_bytes':free if free is not None and memory is not None and free <= memory else None,
        'load_average':host_loadavg()}


if _RESOLVER_MODE: resolver_stage('stdlib-ready')


def json_file(path, cap):
    path = Path(path)
    need(not path.is_symlink() and path.is_file() and path.stat().st_size <= cap, 'Unsafe or oversized JSON')
    return json.loads(path.read_bytes())


def file_record(path, cap):
    path = Path(path)
    need(not path.is_symlink() and path.is_file(), 'Missing or unsafe evidence file')
    size = path.stat().st_size
    need(0 < size <= cap, 'Evidence file byte cap exceeded')
    data = path.read_bytes()
    need(len(data) == size, 'Evidence changed during read')
    return {'name': path.name, 'bytes': size, 'sha256': hashlib.sha256(data).hexdigest()}



def write_ack(ack, outcome, check_active=lambda: None):
    # XCTest waits for file existence. Publish only complete JSON with an atomic
    # exclusive hard link; opening the final path before writing would race it.
    ack = Path(ack); staged = ack.with_suffix('.ack-staged')
    need(not ack.exists() and not ack.is_symlink(), 'Stale acknowledgement')
    payload = json.dumps(outcome).encode()
    need(len(payload) <= 16_384, 'Acknowledgement byte cap')
    check_active()
    try:
        with staged.open('xb') as stream:
            stream.write(payload); stream.flush(); os.fsync(stream.fileno())
        # Cancellation can arrive during staging/fsync. Check immediately before
        # the atomic publication that XCTest treats as the acknowledgement.
        check_active()
        os.link(staged, ack, follow_symlinks=False)
    finally:
        if staged.exists(): staged.unlink()


def fixed_uuid(value):
    need(isinstance(value, str) and str(uuid.UUID(value)).upper() == value.upper(), 'Invalid UUID')
    return value


def safe_container(path, devices_root, device, kind='Data'):
    path, devices_root = Path(path), Path(devices_root)
    fixed_uuid(device); fixed_uuid(path.name)
    expected = devices_root / device / 'data' / 'Containers' / kind / 'Application'
    need(path.is_absolute() and path.parent == expected, 'Container outside exact owned device')
    # Reject symlink ancestors, not merely the leaf; inspect no sibling data.
    for node in (path, *path.parents):
        need(not node.is_symlink(), 'Symlink in owned container path')
    need(path.is_dir(), 'Missing owned container')
    return path


class UniqueMetadata(dict):
    def __setitem__(self, key, value):
        need(key not in self, 'Duplicate metadata key')
        super().__setitem__(key, value)


def open_directory(path):
    """Open each absolute ancestor without following symlinks."""
    path = Path(path)
    need(path.is_absolute() and '..' not in path.parts, 'Noncanonical metadata root')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open('/', flags)
    try:
        for part in path.parts[1:]:
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd); fd = child
        return fd
    except BaseException:
        os.close(fd); raise


def metadata_identity(container_fd, container_uuid, byte_budget=METADATA_CAP, failure=lambda *args: None):
    """Read only the standard identity plist, with finite bytes and no links."""
    fixed_uuid(container_uuid)
    fd = None; step = 'metadata-open'
    try:
        fd = os.open(METADATA_NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            dir_fd=container_fd)
        step = 'metadata-stat'
        before = os.fstat(fd)
        step = 'metadata-type'
        need(stat.S_ISREG(before.st_mode), 'Unsafe metadata file')
        step = 'metadata-links'
        need(before.st_nlink == 1, 'Unsafe metadata file')
        step = 'metadata-size'
        need(0 < before.st_size <= min(METADATA_CAP, byte_budget), 'Unsafe metadata file')
        data = bytearray()
        step = 'metadata-read'
        while len(data) < before.st_size:
            chunk = os.read(fd, min(4096, before.st_size-len(data)))
            if not chunk: break
            data.extend(chunk)
        step = 'metadata-restat'
        after = os.fstat(fd)
        step = 'metadata-stability'
        need((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
            and len(data) == before.st_size, 'Metadata changed during read')
        step = 'metadata-parse'
        row = plistlib.loads(data, dict_type=UniqueMetadata)
        step = 'metadata-identifier'
        need(isinstance(row, dict) and type(row.get('MCMMetadataIdentifier')) is str
            and 0 < len(row['MCMMetadataIdentifier']) <= 255, 'Malformed metadata identity')
        step = 'metadata-uuid'
        # Validate both UUIDs separately; do not assume their meanings coincide.
        metadata_uuid = fixed_uuid(row.get('MCMMetadataUUID'))
        step = 'metadata-receipt'
        return row['MCMMetadataIdentifier'], {'uuid':metadata_uuid, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
            'device': before.st_dev, 'inode': before.st_ino,
            'mtime_ns': before.st_mtime_ns, 'ctime_ns': before.st_ctime_ns}
    except Exception as error:
        failure(step,error); raise
    finally:
        if fd is not None:
            try: os.close(fd)
            except Exception as error:
                failure('metadata-close',error); raise


def resolve_container_metadata(devices_root, device, bundle, kind, progress=lambda *args: None):
    """One bounded scan of this cohort's device; no app-data or CLI fallback."""
    fixed_uuid(device)
    need((bundle, kind) in set(CONTAINER_PHASES.values()), 'Unexpected container target')
    root = Path(devices_root)/device/'data/Containers'/kind/'Application'
    root_fd = None; matches = []; entries = total = 0; stage = 'root'
    detail = {}
    def remember_failure(step, error):
        detail.update(resolver_failure(step,error))
    try:
        progress('root-open',entries,total,len(matches))
        root_fd = open_directory(root)
        progress('root-ready',entries,total,len(matches))
        stage = 'scan-open'
        with os.scandir(root_fd) as scan:
            stage = 'scan-next'
            for entry in scan:
                stage = 'entry-limit'
                entries += 1; need(entries <= METADATA_ENTRIES, 'Metadata entry count exceeded')
                if entries == 1 or entries % 256 == 0: progress('scan-count',entries,total,len(matches))
                stage = 'entry-stat'
                info = entry.stat(follow_symlinks=False)
                stage = 'entry-type'
                need(not stat.S_ISLNK(info.st_mode), 'Metadata directory link rejected')
                # A regular file at the root is not an application container.
                if not stat.S_ISDIR(info.st_mode):
                    stage = 'scan-next'; continue
                stage = 'entry-uuid'
                container_uuid = fixed_uuid(entry.name)
                stage = 'entry-open'
                fd = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                    dir_fd=root_fd)
                try:
                    stage = 'entry-stat-open'
                    current = os.fstat(fd)
                    stage = 'entry-stability'
                    need((info.st_dev, info.st_ino) == (current.st_dev, current.st_ino), 'Container changed during scan')
                    identifier, metadata = metadata_identity(fd, container_uuid, METADATA_TOTAL_CAP-total, remember_failure)
                    stage = 'total-limit'
                    total += metadata['bytes']; need(total <= METADATA_TOTAL_CAP, 'Metadata total bytes exceeded')
                    if identifier == bundle:
                        matches.append({'path': str(root/container_uuid), 'container_uuid': container_uuid,
                            'container_device': current.st_dev, 'container_inode': current.st_ino,
                            'metadata': metadata})
                finally:
                    try: os.close(fd)
                    except Exception as error:
                        remember_failure('entry-close',error); raise
                stage = 'scan-next'
        stage = 'target-missing' if not matches else 'target-ambiguous'
        need(len(matches) == 1, 'Container identity missing or ambiguous')
        progress('match-complete',entries,total,len(matches))
        return {'schema': 'Celluloid.ContainerMetadata.1', 'device': device,
            'bundle_identifier': bundle, 'kind': kind, 'entries_examined': entries,
            'metadata_bytes_examined': total, **matches[0]}
    except Exception as error:
        # Do not expose unrelated app names, UUIDs, plist values or paths.
        # metadata_bytes totals successful identity receipts, not all bytes read.
        progress('lookup-failed',entries,total,len(matches),detail or resolver_failure(stage,error))
        raise ValueError('Owned-device container metadata lookup rejected: '+stage) from None
    finally:
        if root_fd is not None: os.close(root_fd)


def validate_container_receipt(row, devices_root, device, bundle, kind):
    expected = {'schema','device','bundle_identifier','kind','entries_examined','metadata_bytes_examined',
        'path','container_uuid','container_device','container_inode','metadata'}
    need(type(row) is dict and set(row) == expected and row['schema'] == 'Celluloid.ContainerMetadata.1', 'Malformed container receipt')
    need((row['device'], row['bundle_identifier'], row['kind']) == (device,bundle,kind), 'Wrong container receipt target')
    path = safe_container(row['path'], devices_root, device, kind)
    need(path.name == row['container_uuid'], 'Wrong container receipt UUID')
    need(type(row['entries_examined']) is int and 0 < row['entries_examined'] <= METADATA_ENTRIES
        and type(row['metadata_bytes_examined']) is int and 0 < row['metadata_bytes_examined'] <= METADATA_TOTAL_CAP, 'Wrong metadata scan bounds')
    fd = open_directory(path)
    try:
        info = os.fstat(fd)
        need((info.st_dev, info.st_ino) == (row['container_device'],row['container_inode']), 'Resolved container changed')
        identifier, metadata = metadata_identity(fd, path.name)
        need(identifier == bundle and metadata == row['metadata'], 'Resolved metadata changed')
    finally:
        os.close(fd)
    return path


def validate_metadata_operation(temp, binding, started, device, bundle, kind):
    """Host helper can run only for a persisted, fresh owned-device operation."""
    fixed_uuid(device)
    need(not (temp/BARRIER).exists() and not (temp/BARRIER).is_symlink(), 'Existing uncertainty barrier')
    report = json_file(temp/FOLDER/'report.json', REPORT_CAP)
    need(report.get('binding') == binding and report.get('started_monotonic') == started
        and report.get('device') == device and not report.get('device_uncertain')
        and not report.get('error'), 'Wrong metadata operation binding')
    need(report.get('source-before', {}).get('base') == BASE
        and report.get('source-before', {}).get('unchanged_product_scope') is True, 'Fresh source identity missing')
    operations = report.get('operations', [])
    need(operations and not any(row.get('uncertain') or row.get('error') for row in operations), 'Uncertain metadata operation')
    for phase in ('create',*HOST_CONTROL_PHASES,'boot','bootstatus','install'):
        rows = [row for row in operations if row.get('phase') == phase]
        need(len(rows) == 1 and rows[0].get('complete') is True
            and type(rows[0].get('return_code')) is int and rows[0]['return_code'] == 0, 'Fresh device operation missing')
    current = operations[-1]
    need(CONTAINER_PHASES.get(current.get('phase')) == (bundle,kind) and current.get('complete') is False
        and current.get('seconds') == METADATA_SECONDS, 'Unbound metadata operation')
    need(current.get('command') == [sys.executable,str(Path(__file__).resolve()),'--resolve-container',device,bundle,kind], 'Wrong metadata operation command')


def pristine_snapshot(container, metadata):
    # XCTest may migrate a data container. Re-query by owned device + bundle;
    # accept changed UUID only after every actual sample byte matches again.
    snapshot = snapshot_fixture(container, metadata, after_ui=True)
    need(snapshot['files'] == metadata['files'], 'Sample input bytes changed')
    need(snapshot['overlay_texts'] == [] and (snapshot['source_width'], snapshot['source_height']) == (120, 80), 'Sample no longer pristine')
    return snapshot


def validate_request(row, request_id):
    expected = {'schema': 'Celluloid.StoreRequest.1', 'id': request_id,
        'bundle_identifier': APP_ID, 'document': FIXTURE_NAME, 'locale': 'en_US',
        'language': 'en', 'sample_width': 120, 'sample_height': 80, 'preview_count': 1,
        'controls': ['editor.import-files', 'editor.add-bubble', 'editor.export'],
        'ready': True, 'alerts': 0, 'sheets': 0, 'keyboards': 0, 'progress': 0}
    need(type(row) is dict and row == expected, 'Unqualified held UI request')
    # Python bool == 1 must not admit malformed numeric evidence.
    for key in ('sample_width', 'sample_height', 'preview_count', 'alerts', 'sheets', 'keyboards', 'progress'):
        need(type(row[key]) is int, 'Malformed UI observation type')
    need(type(row['ready']) is bool, 'Malformed ready flag')
    return row


def validate_image(row):
    need(type(row) is dict and row.get('format') == 'JPEG' and row.get('mode') == 'RGB'
        and row.get('width') == 3840 and row.get('height') == 2160
        and row.get('alpha') is False and row.get('decoded') is True,
        'Image must decode to native 3840 x 2160 RGB JPEG without alpha')
    return row


def environment(env):
    fixed = {'GITHUB_REPOSITORY': '100mango/Celluloid', 'GITHUB_REF': BRANCH,
        'GITHUB_WORKFLOW_REF': '100mango/Celluloid/' + WORKFLOW + '@' + BRANCH,
        'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_JOB': 'vision', 'GITHUB_EVENT_NAME': 'push',
        'DEVELOPER_DIR': '/Applications/Xcode_27.app/Contents/Developer'}
    need(all(env.get(k) == v for k, v in fixed.items()), 'Wrong exact native cohort')
    sha = env.get('GITHUB_SHA', '')
    need(re.fullmatch('[0-9a-f]{40}', sha) and env.get('GITHUB_WORKFLOW_SHA') == sha, 'Wrong source/workflow SHA')
    need(re.fullmatch('[1-9][0-9]{0,19}', env.get('GITHUB_RUN_ID', '')), 'Invalid run ID')
    return {key: env[key] for key in (*fixed, 'GITHUB_SHA', 'GITHUB_WORKFLOW_SHA', 'GITHUB_RUN_ID')}


def admission(root, env, binding):
    row = json_file(Path(root) / 'Scripts/vision_store_admission.json', 16_384)
    need(row.get('schema') == 'Celluloid.StoreAdmission.1' and row.get('enabled') is True,
         'Native execution is disabled; editor-open evidence, independent review and root GO are pending')
    evidence = row.get('editor_open_evidence')
    need(type(evidence) is dict and evidence.get('editor_open_verified') is True, 'Verified editor-open evidence missing')
    for key in ('run_id', 'artifact_id'):
        need(type(evidence.get(key)) is int and evidence[key] > 0, 'Invalid editor-open provenance')
    for key, count in (('source_sha', 40), ('artifact_sha256', 64)):
        need(re.fullmatch('[0-9a-f]{'+str(count)+'}', evidence.get(key, '')), 'Missing editor-open source/hash')
    need(evidence['source_sha'] == EDITOR_OPEN_SOURCE, 'Editor-open evidence must qualify the byte-equivalent reviewed helper source')
    need(env.get('CELLULOID_STORE_ROOT_GO_SHA') == binding['GITHUB_SHA'], 'Exact-source root GO missing')
    return row


def capture_test_command(temp, device):
    # Only this one selected screenshot case gets a finite XCTest allowance.
    # Other editing tests keep the unmodified shared helper and configuration.
    command = test_command(temp, device, [SELECTOR], 'VisionStoreSingle')
    command[-1:-1] = ['-test-timeouts-enabled', 'YES',
        '-maximum-test-execution-time-allowance', '1200']
    return command


class RequestLines:
    def __init__(self, callback):
        self.callback, self.pending, self.ids = callback, {'stdout': b'', 'stderr': b''}, []
    def __call__(self, stream, data):
        self.pending[stream] += data
        while b'\n' in self.pending[stream]:
            line, self.pending[stream] = self.pending[stream].split(b'\n', 1)
            if REQUEST_PREFIX.encode() not in line: continue
            need(stream == 'stdout', 'Checkpoint marker must be on stdout')
            text = line.decode('utf-8', 'strict').strip()
            match = re.fullmatch(re.escape(REQUEST_PREFIX)+r'([0-9A-F-]{36})', text)
            need(match is not None, 'Malformed checkpoint marker')
            request_id = fixed_uuid(match[1]); need(not self.ids, 'Only one capture request is allowed')
            self.ids.append(request_id); self.callback(request_id)
        need(len(self.pending[stream]) <= 131_072, 'Unbounded UI output line')
    def finish(self):
        for stream, data in list(self.pending.items()):
            need(REQUEST_PREFIX.encode() not in data, 'Unterminated checkpoint marker after producer exit')
        need(len(self.ids) == 1, 'Exactly one real held checkpoint is required')


class Job:
    def __init__(self, root, temp, binding, started, execute=None, clock=time.monotonic):
        self.root, self.temp, self.binding = Path(root), Path(temp), binding
        self.execute, self.clock, self.started = capture if execute is None else execute, clock, started
        self.device = None; self.blocked = False; self.capture_count = 0
        self.checkpoint_deadline = None
        self.observer_guard = None
        self.devices_root = Path.home() / 'Library/Developer/CoreSimulator/Devices'
        need(not (self.temp / BARRIER).exists(), 'Existing uncertainty barrier')
        self.folder = self.temp / FOLDER; self.folder.mkdir(exist_ok=False)
        self.diagnostics = self.temp / DIAGNOSTICS
        need(not self.diagnostics.is_symlink(), 'Unsafe diagnostics directory')
        self.diagnostics.mkdir(exist_ok=True)
        need(self.diagnostics.is_dir(), 'Missing diagnostics directory')
        self.report = {'schema': 'Celluloid.StoreCapture.1', 'binding': binding,
            'started_monotonic': started, 'scope': 'One real held editor image; synthetic INPUT only; no functionality or store-acceptance claim',
            'complete': False, 'visual_review_status': 'pending', 'store_ready': False,
            'host_diagnostic_scope': 'CPU count and physical memory are capacity, not utilization or pressure. '
                'Control timings separate host child delay from readiness only; they do not establish a CPU or memory cause.',
            'signed': False, 'apple_upload': False, 'operations': []}
        self.persist()
    def persist(self):
        data = (json.dumps(self.report, indent=2)+'\n').encode()
        need(len(data) <= REPORT_CAP, 'Report retention cap')
        (self.folder/'report.json').write_bytes(data)
        # Independent small artifact survives strict image-pack rejection.
        destination = self.diagnostics/'report.json'
        need(not destination.is_symlink() and (not destination.exists() or destination.is_file()), 'Unsafe diagnostics report')
        destination.write_bytes(data)
    def barrier(self, row):
        self.blocked = True
        data = (json.dumps(row, indent=2)+'\n').encode()
        need(len(data) <= EVIDENCE_FILES[BARRIER], 'Uncertainty marker cap')
        (self.temp/BARRIER).write_bytes(data); (self.folder/BARRIER).write_bytes(data)
    def bind_observer_guard(self, guard):
        self.observer_guard = guard
    def check_active(self, reserve=0, *, cleanup=False):
        need(not self.blocked, 'Device/process uncertainty blocks further side effects')
        try:
            if self.observer_guard is not None:
                self.observer_guard(reserve, require_running=self.checkpoint_deadline is not None)
            boundary = self.started + (CLEANUP_END if cleanup else WORK_END)
            if self.checkpoint_deadline is not None: boundary = min(boundary, self.checkpoint_deadline)
            need(self.clock()+reserve < boundary, 'Original/held wall-time reserve unavailable')
        except BaseException as error:
            # While an observer is executing, the producer is still owned and
            # running. Fail closed immediately; only its bounded stop path and
            # host evidence finalization may follow.
            if self.observer_guard is not None or self.checkpoint_deadline is not None:
                self.barrier({'phase': 'held-checkpoint-control', 'error': str(error), 'uncertain': True})
            raise
    def call(self, phase, command, seconds, *, cleanup=False, observer=None):
        self.check_active(seconds+20, cleanup=cleanup)
        need(not self.blocked, 'Device/process uncertainty blocks further commands')
        need(not any(row['phase'] == phase for row in self.report['operations']), 'Duplicate operation')
        boundary = self.started + (CLEANUP_END if cleanup else WORK_END)
        if self.checkpoint_deadline is not None: boundary = min(boundary, self.checkpoint_deadline)
        need(self.clock()+seconds+20 <= boundary, 'Original wall-time reserve unavailable: '+phase)
        row = {'phase': phase, 'command': list(map(str, command)), 'seconds': seconds, 'complete': False,
            'started_monotonic': self.clock(), 'host_load_before': host_loadavg()}
        self.report['operations'].append(row)
        print('VISION_PHASE_START '+json.dumps({'phase':phase,'timeout_seconds':seconds,'elapsed_seconds':self.clock()-self.started,
            'barrier':self.blocked,'host_load_before':row['host_load_before']}),flush=True)
        self.persist()
        stdout = stderr = b''; complete = False
        try:
            executor = stream_capture if observer is not None else self.execute
            options = {'observer': observer, 'control': self.bind_observer_guard} if observer is not None else {}
            self.check_active(seconds+20, cleanup=cleanup)
            capture_cap = HOST_CONTROL_CAP if phase in HOST_CONTROL_PHASES else ARCHIVE_RAW_CAP
            result = executor(command, seconds=seconds, cap=capture_cap, cleanup_grace=10, **options)
            stdout, stderr, complete = result.stdout, result.stderr, True
            row['return_code'] = result.returncode
            if result.returncode is None or result.returncode < 0 or self.clock() > row['started_monotonic']+seconds:
                raise TimeoutError('Late/signalled/unfinalized command')
            self.check_active(cleanup=cleanup)
            need(result.returncode == 0, 'Known completed command failed: '+phase)
            if phase in ('build', 'compile-image-helper'):
                need(not re.search(rb'(?im)(?:^|[ :])(?:fatal )?error:', stdout+b'\n'+stderr), 'Build error despite zero exit')
            row['complete'] = True
            return stdout.decode('utf-8', 'replace') + ('\n'+stderr.decode('utf-8', 'replace') if phase == 'ui' else '')
        except (CaptureStopped, TimeoutError, OSError, KeyboardInterrupt) as error:
            row['error'] = str(error); row['uncertain'] = True
            if isinstance(error, CaptureStopped):
                stdout, stderr = getattr(error, 'stdout_prefix', b''), getattr(error, 'stderr_capture', b'')
                row['owned_cleanup_confirmed'] = error.cleanup_confirmed
                row['cancelled_signal'] = error.cancelled_signal
            self.barrier(row); raise
        except BaseException as error:
            row['error'] = str(error); raise
        finally:
            if observer is not None: self.observer_guard = None
            row['finished_monotonic'] = self.clock()
            retain_archive_output(row, stdout, stderr, capture_complete=complete)
            if phase in HOST_CONTROL_PHASES: row['archive_log']['raw_capture_limit_bytes'] = HOST_CONTROL_CAP
            text = row.pop('stdout')+'\n[stderr]\n'+row.pop('stderr')
            # Same flushed, bounded phase/tail reporting used by successful base83.
            print('VISION_PHASE_END '+json.dumps({'phase':phase,'complete':row['complete'],'return_code':row.get('return_code'),
                'error':row.get('error'),'barrier':self.blocked,'capture_complete':complete,
                'elapsed_seconds':row['finished_monotonic']-row['started_monotonic']}),flush=True)
            if not row['complete']:
                tail=(stdout+b'\n[stderr]\n'+stderr)[-FAILURE_TAIL_CAP:]
                print('VISION_FAILURE_TAIL '+json.dumps({'phase':phase,'retained_bytes':len(tail),'tail_only':True})+'\n'+tail.decode('utf-8','replace'),flush=True)
                destination = self.diagnostics/'failure-tail.log'
                need(not destination.is_symlink(), 'Unsafe diagnostics tail')
                # Keep the first failure rather than replacing it with cleanup output.
                if not destination.exists():
                    with destination.open('xb') as stream: stream.write(tail)
            if phase+'.log' in EVIDENCE_FILES:
                path = self.folder/(phase+'.log'); path.write_text(text)
                row['retained_log'] = file_record(path, EVIDENCE_FILES[path.name])
            self.persist()
    def host_control(self, phase):
        need(phase in HOST_CONTROL_PHASES, 'Unexpected host control phase')
        need(not any(row['phase'] == phase for row in self.report.get('host_controls',[])), 'Duplicate host control')
        self.check_active(HOST_CONTROL_SECONDS+20)
        row = {'phase':phase,'host_before':host_snapshot(),'complete':False}
        self.report.setdefault('host_controls',[]).append(row); self.persist()
        try:
            value = self.call(phase,[sys.executable,'-c',HOST_CONTROL_SCRIPT],HOST_CONTROL_SECONDS)
            operation = self.report['operations'][-1]
            matched = re.fullmatch(r'VISION_HOST_CONTROL_ENTRY ([0-9]+(?:\.[0-9]+)?)\n'
                r'VISION_HOST_CONTROL_EXIT ([0-9]+(?:\.[0-9]+)?)\n',value)
            need(matched is not None, 'Malformed host control receipt')
            entry, end = map(float,matched.groups())
            start, finished = operation['started_monotonic'], self.clock()
            need(all(math.isfinite(v) for v in (entry,end)) and start <= entry <= end <= finished
                and finished <= start+HOST_CONTROL_SECONDS, 'Late or invalid host control clock')
            need(operation['archive_log']['streams']['stderr']['full_bytes'] == 0, 'Unexpected host control stderr')
            row.update(complete=True,entry_delay_seconds=entry-start,
                child_interval_seconds=end-entry,observed_total_seconds=finished-start)
        except BaseException:
            if not self.blocked: self.barrier({'phase':phase,'error':'Host control qualification failed','uncertain':True})
            raise
        finally:
            row['host_after'] = host_snapshot(); self.persist()
    def container(self, phase, bundle, kind='Data'):
        need(CONTAINER_PHASES.get(phase) == (bundle,kind), 'Wrong metadata resolution phase')
        value = self.call(phase, [sys.executable,str(Path(__file__).resolve()),'--resolve-container',
            self.device,bundle,kind], METADATA_SECONDS)
        self.check_active()
        receipt = json.loads(value)
        path = validate_container_receipt(receipt, self.devices_root, self.device, bundle, kind)
        self.check_active()
        self.report.setdefault('container_resolutions', []).append({'phase':phase, **receipt})
        self.persist()
        if kind == 'Bundle':
            app = path/'CelluloidVision.app'
            safe_container(app.parent, self.devices_root, self.device, kind)
            need(app.name == 'CelluloidVision.app' and not app.is_symlink() and app.is_dir(), 'Wrong installed app path')
            info = json_or_plist(app/'Info.plist')
            need((info.get('CFBundleIdentifier'), info.get('CFBundleExecutable'), info.get('DTPlatformName')) == (APP_ID, 'CelluloidVision', 'xrsimulator'), 'Wrong installed app identity')
            binary = file_record(app/'CelluloidVision', 200_000_000)
            need(binary['sha256'] == self.report['built_app']['binary_sha256'], 'Installed binary differs from exact build')
            return {'path': str(app), 'binary_sha256': binary['sha256']}
        return path
    def source_identity(self, stage):
        def git(label, *args): return self.call(stage+'-'+label, ['git', *args], 10).strip()
        sha = self.binding['GITHUB_SHA']
        need(git('head', 'rev-parse', 'HEAD') == sha, 'Wrong source HEAD')
        need(git('base', 'rev-parse', BASE+'^{tree}') == BASE_TREE, 'Wrong helper base tree')
        need(git('parent', 'rev-list', '--parents', '-n', '1', 'HEAD').split() == [sha, BASE], 'Wrong sole parent')
        need(not git('status', 'status', '--porcelain', '--untracked-files=all'), 'Dirty candidate')
        expected = ['A\t'+p for p in ADDED]+['M\t'+p for p in MODIFIED]
        need(sorted(git('scope', 'diff', '--name-status', BASE, 'HEAD', '--').splitlines()) == sorted(expected), 'Unexpected product/source scope')
        self.report[stage] = {'tree': git('tree', 'rev-parse', 'HEAD^{tree}'), 'base': BASE, 'unchanged_product_scope': True}
        self.persist()
    def checkpoint(self, request_id):
        self.check_active()
        need(self.capture_count == 0, 'Second capture forbidden'); self.capture_count += 1
        self.checkpoint_deadline = self.clock()+600
        ack = None; outcome = {'id': request_id, 'success': False}
        try:
            self.report['installed_at_checkpoint'] = self.container('capture-installed', APP_ID, 'Bundle')
            data = self.container('capture-data', APP_ID)
            self.report['sample_at_checkpoint'] = pristine_snapshot(data, self.report['sample_input'])
            runner = self.container('capture-runner', RUNNER_ID)
            scratch = runner/'tmp'
            need(scratch.is_dir() and not scratch.is_symlink(), 'Unsafe runner temporary directory')
            request = scratch/('Celluloid-store-'+request_id+'.json')
            candidate_ack = scratch/('Celluloid-store-'+request_id+'.ack')
            need(not candidate_ack.exists() and not candidate_ack.is_symlink(), 'Stale checkpoint acknowledgement')
            ack = candidate_ack
            row = validate_request(json_file(request, 16_384), request_id)
            self.report['ui_observations'] = row; self.persist()
            original = self.temp/'capture-original.jpeg'
            need(not original.exists() and not original.is_symlink(), 'Do not overwrite capture')
            self.call('screenshot', ['xcrun', 'simctl', 'io', self.device, 'screenshot', '--type=jpeg', str(original)], 15)
            raw = file_record(original, ORIGINAL_CAP)
            # Preserve raw bytes before image acceptance. A rejected resolution or
            # decode remains failure evidence; never relabel it a Store asset.
            self.check_active()
            retained = self.folder/'capture-original.jpeg'; retained.write_bytes(original.read_bytes())
            need(file_record(retained, ORIGINAL_CAP) == raw, 'Original byte copy changed')
            self.report['original'] = raw; self.persist()
            raw['validation'] = validate_image(json.loads(self.call('inspect-original', [str(self.image_helper), '--inspect', str(original)], 10)))
            raw['source'] = 'simctl full-display JPEG at held XCTest checkpoint'
            self.report['original'] = raw
            self.check_active()
            outcome.update(success=True, original_sha256=raw['sha256'], width=3840, height=2160, mode='RGB')
            self.report['capture'] = outcome; self.persist()
            need(file_record(original, ORIGINAL_CAP)['sha256'] == raw['sha256'] and file_record(retained, ORIGINAL_CAP)['sha256'] == raw['sha256'], 'Original changed before acknowledgement')
        except BaseException as error:
            outcome.update(success=False, error=str(error)); self.report['capture'] = outcome; self.persist(); raise
        finally:
            # Never touch a device-owned path after uncertainty. A rejected
            # known request gets failure ack; every UI failure stays failed.
            if ack is not None and not self.blocked:
                try:
                    def check_ack():
                        self.check_active()
                        if outcome['success']:
                            for path in (self.temp/'capture-original.jpeg', self.folder/'capture-original.jpeg'):
                                need(file_record(path, ORIGINAL_CAP)['sha256'] == outcome['original_sha256'], 'Original changed before acknowledgement')
                        self.check_active()
                    write_ack(ack, outcome, check_ack)
                except BaseException as error:
                    outcome.update(success=False, error=str(error))
                    self.report['capture'] = outcome; self.persist()
                    raise
                finally:
                    self.checkpoint_deadline = None
            else:
                self.checkpoint_deadline = None
    def select_delivery(self):
        self.check_active()
        validate_image_bindings(self.folder, self.report)
        original = self.folder/'capture-original.jpeg'; raw = self.report['original']
        if raw['bytes'] <= STORE_CAP:
            self.report['delivery_image'] = {**raw, 'kind': 'unchanged native original'}
            validate_image_bindings(self.folder, self.report, require_delivery=True); return
        attempts = []
        for quality in (65, 45, 30):
            output = self.temp/('capture-q'+str(quality)+'.jpeg')
            need(not output.exists() and not output.is_symlink(), 'Do not overwrite JPEG derivative')
            row = validate_image(json.loads(self.call('encode-'+str(quality), [str(self.image_helper), '--encode', str(original), str(output), str(quality)], 15)))
            record = file_record(output, ORIGINAL_CAP); attempts.append({**record, 'quality': quality, **row})
            need(file_record(original, ORIGINAL_CAP)['sha256'] == raw['sha256'], 'Encoding mutated original')
            if record['bytes'] <= STORE_CAP:
                self.check_active()
                destination = self.folder/'store-image.jpeg'; destination.write_bytes(output.read_bytes())
                need(file_record(destination, STORE_CAP)['sha256'] == record['sha256'], 'Derivative byte copy changed')
                self.report['encoding_attempts'] = attempts
                self.report['delivery_image'] = {**file_record(destination, STORE_CAP), **row,
                    'kind': 'same-size lossy derivative', 'original_sha256': raw['sha256']}
                validate_image_bindings(self.folder, self.report, require_delivery=True)
                return
        self.report['encoding_attempts'] = attempts
        raise ValueError('All same-size qualities exceed 3 MB; original preserved; no resize or second capture')
    def work(self):
        self.source_identity('source-before')
        version = self.call('toolchain', ['xcodebuild', '-version'], 30)
        need(version.splitlines()[:1] == ['Xcode 27.0'], 'Wrong Xcode toolchain')
        self.report['toolchain'] = version
        self.image_helper = self.temp/'celluloid-store-image'
        self.call('compile-image-helper', ['swiftc', '-swift-version', '5', 'Scripts/vision_store_image.swift', '-o', str(self.image_helper)], 180)
        self.call('icons', ['swift', '-swift-version', '5', 'Scripts/materialize_native_icons.swift'], 180)
        self.call('icon-inputs', [sys.executable, 'Scripts/verify_native_icon_inputs.py'], 30)
        self.call('build', ['xcodebuild', '-project', 'CelluloidNative.xcodeproj', '-scheme', 'CelluloidVision', '-destination', 'generic/platform=visionOS Simulator', '-derivedDataPath', str(self.temp/'celluloid-vision'), 'CODE_SIGNING_ALLOWED=NO', 'build-for-testing'], 600)
        app, binary = built_vision_app(self.temp)
        runner = app.parent/'CelluloidVisionUITests-Runner.app'
        need(not runner.is_symlink() and runner.is_dir(), 'Missing built runner')
        info = json_or_plist(runner/'Info.plist'); need(info.get('CFBundleIdentifier') == RUNNER_ID, 'Wrong built UI runner')
        self.report['built_app'] = {'path': str(app), 'bundle_identifier': APP_ID, 'binary_sha256': binary, 'configuration': 'Debug-xrsimulator'}
        runner_executable = info.get('CFBundleExecutable')
        need(type(runner_executable) is str and re.fullmatch('[A-Za-z0-9_.-]+', runner_executable), 'Unsafe runner executable name')
        self.report['runner'] = {'path': str(runner), 'bundle_identifier': info['CFBundleIdentifier'],
            'binary': file_record(runner/runner_executable, 200_000_000), 'info_plist': file_record(runner/'Info.plist', 1_000_000)}
        runtimes = json.loads(self.call('runtimes', ['xcrun', 'simctl', 'list', 'runtimes', '--json'], 30))['runtimes']
        wanted_runtime = 'com.apple.CoreSimulator.SimRuntime.xrOS-27-0'
        runtime = [r for r in runtimes if r.get('isAvailable') and r.get('identifier') == wanted_runtime]
        need(len(runtime) == 1, 'Expected exact available visionOS runtime')
        wanted_type = 'com.apple.CoreSimulator.SimDeviceType.Apple-Vision-Pro-4K'
        types = json.loads(self.call('types', ['xcrun', 'simctl', 'list', 'devicetypes', '--json'], 30))['devicetypes']
        need(sum(r.get('identifier') == wanted_type for r in types) == 1 and wanted_type in {r['identifier'] for r in runtime[0]['supportedDeviceTypes']}, 'Expected compatible 4K Vision device type')
        self.device = fixed_uuid(self.call('create', ['xcrun', 'simctl', 'create', 'Celluloid Store '+self.binding['GITHUB_SHA'][:12], wanted_type, wanted_runtime], 30).strip())
        self.report.update(device=self.device, runtime=runtime[0], device_type=wanted_type)
        try:
            self.report['readiness'] = {'complete':False,'device':self.device}; self.persist()
            self.host_control('host-control-before-boot')
            self.call('boot', ['xcrun', 'simctl', 'boot', self.device], 45)
            self.host_control('host-control-after-boot')
            self.call('bootstatus', ['xcrun', 'simctl', 'bootstatus', self.device, '-b'], 240)
            self.report['readiness']['complete'] = True; self.persist()
        except BaseException:
            if not self.blocked: self.barrier({'phase':'pre-install-readiness',
                'error':'Readiness qualification failed','uncertain':True})
            raise
        # Readiness gates admission, not success: actual install and held UI remain mandatory.
        self.call('install', ['xcrun', 'simctl', 'install', self.device, str(app)], 360)
        container = self.container('seed-data', APP_ID)
        self.check_active()
        self.report['sample_input'] = write_synthetic_fixture(container)
        self.report['sample_before'] = pristine_snapshot(container, self.report['sample_input']); self.persist()
        lines = RequestLines(self.checkpoint)
        ui = self.call('ui', capture_test_command(self.temp, self.device), 1200, observer=lines)
        lines.finish(); self.report['xctest'] = verify_cases(ui, [SELECTOR])
        need(self.capture_count == 1 and self.report.get('capture', {}).get('success') is True, 'Missing single successful capture')
        expected_ack = 'CELLULOID_STORE_CAPTURE_ACK '+lines.ids[0]+' sha256='+self.report['original']['sha256']
        need(ui.splitlines().count(expected_ack) == 1, 'Exact success acknowledgement missing or duplicated')
        self.report['sample_after'] = pristine_snapshot(self.container('after-data', APP_ID), self.report['sample_input'])
        self.report['installed_after'] = self.container('after-installed', APP_ID, 'Bundle')
        self.select_delivery()
        self.call('icons-after', [sys.executable, 'Scripts/verify_native_icon_inputs.py'], 30)
        self.source_identity('source-after')
        self.report['capture_qualified'] = True
    def finish(self):
        self.report['cleanup'] = []
        if self.device and not self.blocked:
            for action in ('shutdown', 'delete'):
                try:
                    self.call(action, ['xcrun', 'simctl', action, self.device], 40, cleanup=True)
                    self.report['cleanup'].append({'action': action, 'success': True})
                except BaseException as error:
                    self.report['cleanup'].append({'action': action, 'success': False, 'error': str(error)}); break
        self.report['device_uncertain'] = self.blocked
        self.report['complete'] = bool(self.report.get('capture_qualified') and not self.blocked and len(self.report['cleanup']) == 2 and all(r['success'] for r in self.report['cleanup']))
        self.report['elapsed_seconds'] = self.clock()-self.started
        print('VISION_JOB_END '+json.dumps({k:self.report.get(k) for k in ('complete','device_uncertain','error','elapsed_seconds')}),flush=True)
        self.persist()


def json_or_plist(path):
    path = Path(path)
    file_record(path, 1_000_000)
    return plistlib.loads(path.read_bytes())


def validate_image_bindings(folder, report, *, require_delivery=False, records=None):
    """Bind every retained image to the immutable checkpoint/encoding receipt."""
    folder = Path(folder)
    actual = records if records is not None else {
        name: file_record(folder/name, cap)
        for name, cap in (('capture-original.jpeg', ORIGINAL_CAP), ('store-image.jpeg', STORE_CAP))
        if (folder/name).exists() or (folder/name).is_symlink()}
    def match(record, name):
        need(type(record) is dict and record.get('name') == name, 'Missing image provenance: '+name)
        need(actual.get(name) == {key: record.get(key) for key in ('name', 'bytes', 'sha256')},
             'Checkpoint/encoding image hash or size changed: '+name)
    raw, delivery = report.get('original'), report.get('delivery_image')
    if raw is not None or 'capture-original.jpeg' in actual:
        match(raw, 'capture-original.jpeg')
    if report.get('capture', {}).get('success') is True:
        need(raw is not None and report['capture'].get('original_sha256') == raw['sha256'], 'Capture checkpoint hash mismatch')
        validate_image(raw.get('validation'))
    need(not require_delivery or delivery is not None, 'Missing delivery image')
    if delivery is not None:
        need(raw is not None, 'Delivery has no checkpoint original')
        need(type(delivery.get('bytes')) is int and 0 < delivery['bytes'] <= STORE_CAP, 'Delivery byte cap')
        if delivery.get('kind') == 'unchanged native original':
            match(delivery, 'capture-original.jpeg')
            need(delivery['sha256'] == raw['sha256'], 'Original delivery checkpoint hash mismatch')
        else:
            need(delivery.get('kind') == 'same-size lossy derivative', 'Unknown delivery provenance')
            match(delivery, 'store-image.jpeg'); validate_image(delivery)
            need(delivery.get('original_sha256') == raw['sha256'], 'Derivative checkpoint hash mismatch')
    if 'store-image.jpeg' in actual:
        need(delivery is not None and delivery.get('name') == 'store-image.jpeg', 'Unbound derivative')


def pack(temp, binding, started, now):
    temp = Path(temp); folder = temp/FOLDER
    need(now <= started+PACK_END, 'Original pack deadline exceeded')
    need(folder.is_dir() and not folder.is_symlink(), 'Missing evidence directory')
    children = list(folder.iterdir())
    need({p.name for p in children} <= set(EVIDENCE_FILES), 'Unexpected evidence path')
    need(all(not p.is_symlink() and p.is_file() for p in children), 'Unsafe evidence member')
    source = temp/'native-icon-provenance-runtime.json'
    if source.exists() or source.is_symlink():
        source_record = file_record(source, 1_000_000)
        destination = folder/source.name
        need(not destination.exists() and not destination.is_symlink(), 'Do not overwrite icon receipt')
        with destination.open('xb') as stream: stream.write(source.read_bytes())
        need(file_record(destination, 1_000_000) == source_record, 'Icon receipt changed during copy')
    children = list(folder.iterdir())
    need({p.name for p in children} <= set(EVIDENCE_FILES), 'Unexpected evidence path')
    need(all(not p.is_symlink() and p.is_file() for p in children), 'Unsafe evidence member')
    need(not (folder/'manifest.json').exists(), 'Do not overwrite a packed manifest')
    members = [file_record(folder/name, cap) for name, cap in sorted(EVIDENCE_FILES.items()) if name != 'manifest.json' and (folder/name).exists()]
    report = json_file(folder/'report.json', REPORT_CAP)
    validate_image_bindings(folder, report, require_delivery=report.get('complete') is True,
        records={item['name']: item for item in members})
    row = {'binding': binding, 'started_monotonic': started, 'packed_monotonic': now, 'members': members,
        'max_bytes': EVIDENCE_CAP, 'visual_review_status': 'pending', 'store_ready': False}
    data = (json.dumps(row, indent=2)+'\n').encode()
    need(len(data) <= EVIDENCE_FILES['manifest.json'] and len(data)+sum(r['bytes'] for r in members) <= EVIDENCE_CAP, 'Aggregate evidence cap')
    (folder/'manifest.json').write_bytes(data); return row


def verify_packed_images(temp, binding, started):
    folder = Path(temp)/FOLDER
    manifest = json_file(folder/'manifest.json', EVIDENCE_FILES['manifest.json'])
    need(manifest.get('binding') == binding and manifest.get('started_monotonic') == started, 'Packed binding mismatch')
    expected = manifest.get('members')
    need(type(expected) is list and all(type(row) is dict for row in expected), 'Invalid packed members')
    names = [row.get('name') for row in expected]
    need(len(names) == len(set(names)) and set(names) <= set(EVIDENCE_FILES)-{'manifest.json'}, 'Invalid packed paths')
    actual = [file_record(folder/name, EVIDENCE_FILES[name]) for name in names]
    need(actual == expected, 'Packed evidence hash or size changed')
    need({path.name for path in folder.iterdir()} == set(names)|{'manifest.json'}, 'Packed member set changed')
    report = json_file(folder/'report.json', REPORT_CAP)
    validate_image_bindings(folder, report, require_delivery=report.get('complete') is True,
        records={row['name']: row for row in actual})
    return report


def main():
    parser = argparse.ArgumentParser(); mode = parser.add_mutually_exclusive_group()
    for option in ('execute', 'pack', 'finish-upload'): mode.add_argument('--'+option, action='store_true')
    mode.add_argument('--resolve-container', nargs=3, metavar=('DEVICE','BUNDLE','KIND'))
    args = parser.parse_args()
    if not any((args.execute, args.pack, args.finish_upload, args.resolve_container)):
        print(json.dumps({'candidate_only': True, 'native_execution_enabled': False, 'case': SELECTOR,
            'scope': 'One held real editor capture; no native run by default', 'visual_review_required': True}, indent=2)); return 0
    root = Path(__file__).resolve().parents[1]
    need(Path.cwd().resolve() == root, 'Run from exact candidate root')
    if args.resolve_container: resolver_stage('binding-start')
    binding = environment(os.environ)
    authorization = admission(root, os.environ, binding)
    temp = Path(os.environ['RUNNER_TEMP'])
    clock = json_file(temp/CLOCK, 16_384)
    need(clock.get('binding') == binding, 'Original clock binding mismatch')
    started, now = clock.get('started_monotonic'), time.monotonic()
    need(type(started) in (int, float) and math.isfinite(started) and 0 < started <= now, 'Invalid original clock')
    if args.resolve_container:
        device, bundle, kind = args.resolve_container
        need(now+METADATA_SECONDS <= started+WORK_END, 'Metadata resolution original deadline missing')
        validate_metadata_operation(temp, binding, started, device, bundle, kind)
        resolver_stage('binding-ready')
        row = resolve_container_metadata(Path.home()/'Library/Developer/CoreSimulator/Devices', device, bundle, kind,
            progress=resolver_stage)
        payload = json.dumps(row)
        need(len(payload.encode()) <= 16_384, 'Metadata receipt cap')
        print(payload, flush=True)
        return 0
    if args.pack:
        print('VISION_PACK_START '+json.dumps({'elapsed_seconds':now-started}),flush=True)
        try:
            pack(temp, binding, started, now)
            need(time.monotonic() <= started+PACK_END and time.monotonic()+240 <= started+FINISH_END, 'Pack/upload/verdict reserve missing')
            print('VISION_PACK_END '+json.dumps({'complete':True,'elapsed_seconds':time.monotonic()-started}),flush=True)
        except BaseException as error:
            print('VISION_PACK_FAILURE '+json.dumps({'error':str(error),'elapsed_seconds':time.monotonic()-started}),flush=True)
            raise
        return 0
    if args.finish_upload:
        need(now <= started+FINISH_END and os.environ.get('VISION_UPLOAD_OUTCOME') == 'success', 'Upload/deadline failed')
        return 0 if verify_packed_images(temp, binding, started).get('complete') is True else 1
    load_native_helpers()
    job = Job(root, temp, binding, started); job.report['admission'] = authorization
    try: job.work()
    except BaseException as error:
        job.report['error'] = str(error)
        print('VISION_JOB_FAILURE '+json.dumps({'error':str(error),'barrier':job.blocked}),flush=True)
    finally: job.finish()
    return 0 if job.report['complete'] else 1


if __name__ == '__main__':
    try: verdict = main()
    except BaseException as error:
        if _RESOLVER_MODE:
            try: resolver_stage('failed')
            except Exception: pass  # Diagnostic failure must not bypass its cap.
            raise SystemExit(1) from None
        print('VISION_DRIVER_FAILURE '+json.dumps({'type':type(error).__name__,'error':str(error)}),flush=True)
        raise
    raise SystemExit(verdict)
