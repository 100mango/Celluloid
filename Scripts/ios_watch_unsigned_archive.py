#!/usr/bin/env python3
"""One fixed simulator-free unsigned iOS + Watch archive; not distribution.

Capture/retention/clock/owned-cleanup functions are copied without alteration
from the reviewed QR Vision v2 / successful QR TV collector. Product policy is
specific to the five fixed Celluloid code products and their matching dSYMs.
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
import uuid

from ios_watch_archive_capture import capture, CaptureStopped

ROOT = Path(__file__).resolve().parents[1]
BASE = 'baea0ae3b3c9d9911937e9dd95a9fba6cbdf9d73'
BASE_TREE = 'd4d2445d1f59f69e19e0177ed624926b89d82bae'
BRANCH = 'refs/heads/codex/ios-watch-unsigned-archive'
WORKFLOW = '.github/workflows/ios-watch-unsigned-archive.yml'
PROJECT = 'Celluloid-iOS-Watch.xcodeproj'
ARCHIVE = Path('build/Celluloid-iOS-Watch.xcarchive')
DERIVED = Path('build/iOS-Watch-Archive')
APP = 'Products/Applications/Celluloid.app'
WATCH = APP + '/Watch/CelluloidWatch.app'
KIT = APP + '/Frameworks/CelluloidKit.framework'
EXT = APP + '/PlugIns/CelluloidPhotoExtension.appex'
SNAPKIT_NAME = 'SnapKit_3965163F11347F41_PackageProduct'
SNAPKIT = APP + '/Frameworks/' + SNAPKIT_NAME + '.framework'
SPECS = {
 'phone': {'app':APP,'executable':'Celluloid','bundle':'Mango.Celluloid','kind':2,'package':'APPL','version':'1.1','build':'2','family':[1,2]},
 'watch': {'app':WATCH,'executable':'CelluloidWatch','bundle':'Mango.Celluloid.watchkitapp','kind':2,'package':'APPL','version':'1.1','build':'2','family':[4]},
 'kit': {'app':KIT,'executable':'CelluloidKit','bundle':'Mango.CelluloidKit','kind':6,'package':'FMWK','version':'1.1','build':'2'},
 'extension': {'app':EXT,'executable':'CelluloidPhotoExtension','bundle':'Mango.Celluloid.CelluloidPhotoExtension','kind':2,'package':'XPC!','version':'1.1','build':'2'},
 'snapkit': {'app':SNAPKIT,'executable':SNAPKIT_NAME,'bundle':'snapkit.SnapKit','kind':6,'package':'FMWK','version':'1.0','build':'1'},
}
for role,spec in SPECS.items():
    watch=role=='watch'
    spec.update(platform_name='watchos' if watch else 'iphoneos',platforms=['WatchOS'] if watch else ['iPhoneOS'],floor='9.0' if watch else '15.0',platform=4 if watch else 2,
      arches={0x100000c:('arm64',[26,0,0]),0x200000c:('arm64_32',[9,0,0])} if watch else {0x100000c:('arm64',[15,0,0])},sdk=[15,0,0] if role=='snapkit' else [27,0,0])
    spec['binary']=spec['app']+'/'+spec['executable']
    spec['dsym']='dSYMs/'+Path(spec['app']).name+'.dSYM'
    spec['dwarf']=spec['dsym']+'/Contents/Resources/DWARF/'+spec['executable']
INSTALL_NAMES={KIT:'@rpath/CelluloidKit.framework/CelluloidKit',SNAPKIT:'@rpath/'+SNAPKIT_NAME+'.framework/'+SNAPKIT_NAME}
BUNDLED_DEPENDENCIES={APP:{INSTALL_NAMES[KIT],INSTALL_NAMES[SNAPKIT]},KIT:{INSTALL_NAMES[SNAPKIT]},EXT:{INSTALL_NAMES[KIT]},SNAPKIT:set(),WATCH:set()}
SNAPKIT_RESOURCES={APP+'/SnapKit_SnapKit.bundle',EXT+'/SnapKit_SnapKit.bundle',SNAPKIT+'/SnapKit_SnapKit.bundle'}
PACKAGE_RESOURCES=json.loads((ROOT/'Scripts/ios_watch_resource_contract.json').read_bytes())
RESOURCE_BUNDLES=SNAPKIT_RESOURCES|set(PACKAGE_RESOURCES)
PRIVACY={'NSPrivacyTracking':False,'NSPrivacyAccessedAPITypes':[],'NSPrivacyCollectedDataTypes':[],'NSPrivacyTrackingDomains':[]}
SNAPKIT_REVISION='2842e6e84e82eb9a8dac0100ca90d9444b0307f4'

MAX_ENTRIES, MAX_BYTES, SCAN_SECONDS = 2048, 1024 ** 3, 30
MAX_INVENTORY = 1024 ** 2
MAX_REPORT = 2 * 1024 ** 2
ARCHIVE_RAW_CAP = 16 * 1024 ** 2
ARCHIVE_RETAIN_CAP = 512 * 1024
ARCHIVE_COMMAND = ['xcodebuild','archive','-project',PROJECT,'-scheme','Celluloid',
 '-configuration','Release','-destination','generic/platform=iOS',
 '-derivedDataPath',str(DERIVED),'-clonedSourcePackagesDirPath','build/SourcePackages','-onlyUsePackageVersionsFromResolvedFile','-archivePath',str(ARCHIVE),'-jobs','2',
 'ONLY_ACTIVE_ARCH=NO','DEBUG_INFORMATION_FORMAT=dwarf-with-dsym','CODE_SIGNING_ALLOWED=NO','CODE_SIGNING_REQUIRED=NO',
 'CODE_SIGN_IDENTITY=','DEVELOPMENT_TEAM=','PROVISIONING_PROFILE=',
 'PROVISIONING_PROFILE_SPECIFIER=','OTHER_CODE_SIGN_FLAGS=']
PHASE_END = {'prepare':180,'archive':800,'proof':950,'final_source_pack':980,
             'evidence':1040,'finalization':1060}
MODIFIED_PATHS = ()
NEW_PATHS = ('.github/workflows/ios-watch-unsigned-archive.yml', 'Celluloid-iOS-Watch.xcodeproj/project.pbxproj', 'Celluloid-iOS-Watch.xcodeproj/project.xcworkspace/contents.xcworkspacedata', 'Celluloid-iOS-Watch.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved', 'Celluloid-iOS-Watch.xcodeproj/xcshareddata/xcschemes/Celluloid.xcscheme', 'Platforms/IOSWatchIntegration/AppDelegate.swift', 'Platforms/IOSWatchIntegration/EntranceViewController.swift', 'Documentation/IOS_WATCH_PROFILE.md', 'Documentation/IOS_WATCH_UNSIGNED_ARCHIVE_PLAN.json', 'Scripts/generate_ios_watch_project.py', 'Scripts/test_ios_watch_project.py', 'Scripts/ios_watch_unsigned_archive.py', 'Scripts/ios_watch_archive_capture.py', 'Scripts/owned_process_group.py', 'Scripts/test_ios_watch_unsigned_archive.py', 'Scripts/ios_watch_resource_contract.json')
MACH_MAGICS = (b'\xcf\xfa\xed\xfe',b'\xfe\xed\xfa\xcf',b'\xce\xfa\xed\xfe',
               b'\xfe\xed\xfa\xce',b'\xca\xfe\xba\xbe',b'\xca\xfe\xba\xbf')


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
    receipt['complete'] = True
    return result.stdout

def file_identity(value):
    return [value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns]

def scan(archive, deadline, *, clock=time.monotonic, hash_files=True, progress=None):
    """Complete bounded catalogue before policy; resource names are not a whitelist."""
    deadline=min(deadline,clock()+SCAN_SECONDS)
    progress={} if progress is None else progress
    progress.update(paths={},entries=0,bytes=0,complete=False)
    paths=progress['paths'];pending=[archive];metadata_bytes=0
    def admit(ok,reason,key):need(ok,reason+': '+key)
    root_stat=archive.lstat();admit(stat.S_ISDIR(root_stat.st_mode),'archive-missing-or-linked','.')
    paths['.']={'identity':file_identity(root_stat),'type':'directory'}
    while pending:
        folder=pending.pop();timely(deadline,clock)
        with os.scandir(folder) as entries:
            for entry in entries:
                timely(deadline,clock);path=Path(entry.path);key=path.relative_to(archive).as_posix()
                progress['last_path']=key
                admit(len(paths)<=MAX_ENTRIES,'archive-entry-limit',key);admit(len(key)<=1024,'archive-path-limit',key)
                admit(path.suffix.lower() not in ('.p8','.p12','.pfx','.key','.keychain','.keychain-db','.mobileprovision','.provisionprofile'), 'signing-input-present', key)
                value=path.lstat();mode=value.st_mode
                kind='directory' if stat.S_ISDIR(mode) else 'file' if stat.S_ISREG(mode) else 'symlink' if stat.S_ISLNK(mode) else 'nonregular'
                receipt={'identity':file_identity(value),'type':kind};paths[key]=receipt;progress['entries']+=1
                if kind=='symlink':
                    target=os.readlink(path);receipt['target']=target
                    admit(len(target)<=1024 and not os.path.isabs(target),'unsafe-link-target',key)
                    resolved=path.resolve();admit(resolved.is_relative_to(archive.resolve()),'archive-link-escape',key)
                    receipt['resolved']=resolved.relative_to(archive.resolve()).as_posix()
                elif kind=='directory':pending.append(path)
                elif kind=='file':
                    progress['bytes']+=value.st_size;receipt['bytes']=value.st_size
                    admit(progress['bytes']<=MAX_BYTES,'archive-byte-limit',key)
                    if hash_files:
                        h=hashlib.sha256();count=0;prefix=b'';tail=b''
                        with os.fdopen(os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK),'rb') as stream:
                            admit(file_identity(os.fstat(stream.fileno()))==receipt['identity'],'archive-file-changed',key)
                            while chunk:=stream.read(1024*1024):
                                timely(deadline,clock);count+=len(chunk);admit(count<=value.st_size,'archive-file-grew',key)
                                if not prefix:prefix=chunk[:4]
                                probe=tail+chunk
                                admit(not re.search(rb'-----BEGIN (?:[A-Z0-9 ]* )?PRIVATE KEY-----',probe), 'private-key-material-present', key)
                                tail=probe[-128:]
                                h.update(chunk)
                            admit(file_identity(os.fstat(stream.fileno()))==receipt['identity'],'archive-file-changed',key)
                        admit(count==value.st_size,'archive-file-size-changed',key)
                        receipt.update(sha256=h.hexdigest(),prefix_hex=prefix.hex())
                else:admit(False,'archive-nonregular',key)
                metadata_bytes+=len(json.dumps({key:receipt},sort_keys=True).encode())
                admit(metadata_bytes<=MAX_INVENTORY,'inventory-metadata-limit',key)
    for key,receipt in paths.items():
        timely(deadline,clock);admit(file_identity((archive/key).lstat())==receipt['identity'],'archive-snapshot-changed',key)
    progress['complete']=True;progress.pop('last_path',None);timely(deadline,clock)
    return progress

def json_value(value):
    if isinstance(value, datetime.datetime):
        return {'plist_date': value.isoformat()}
    if isinstance(value, bytes):
        return {'plist_data_hex': value.hex()}
    raise TypeError(type(value).__name__)

def report_bytes(report):
    raw = (json.dumps(report, sort_keys=True, default=json_value, allow_nan=False, separators=(',', ':')) + '\n').encode()
    if len(raw) > MAX_REPORT:
        # Keep the bounded catalogue/source/clock even when another field overflows.
        keep=('schema','scope','signing_qualified','store_qualified','older_os_qualified','ui_qualification_separate',
            'source_before','clock','archive_inventory','owned_output','binary_handoff','upload_qualified')
        compact={k:report[k] for k in keep if k in report}
        compact.update(qualified=False,failure={'type':'Rejected','reason':'report-byte-limit','original_failure':report.get('failure')})
        raw=(json.dumps(compact,sort_keys=True,default=json_value,allow_nan=False,separators=(',',':'))+'\n').encode()
        need(len(raw)<=MAX_REPORT,'bounded-inventory-report-byte-limit')
    return raw

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
        receipt = finish_upload(result, env.get('CELL_ARCHIVE_UPLOAD_OUTCOME', ''), clock=clock)
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


def environment(env):
    expected = {'GITHUB_REPOSITORY': '100mango/Celluloid', 'GITHUB_REF': BRANCH,
        'GITHUB_WORKFLOW_REF': '100mango/Celluloid/' + WORKFLOW + '@' + BRANCH,
        'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_JOB': 'archive',
        'DEVELOPER_DIR': '/Applications/Xcode_27.app/Contents/Developer'}
    need(all(env.get(k) == v for k,v in expected.items()), 'job-identity-mismatch')
    need(env.get('GITHUB_EVENT_NAME') == 'push', 'event-mismatch')
    sha = env.get('GITHUB_SHA', '')
    need(re.fullmatch('[0-9a-f]{40}', sha) and env.get('GITHUB_WORKFLOW_SHA') == sha, 'source-workflow-sha-mismatch')
    need(re.fullmatch('[1-9][0-9]{0,19}', env.get('GITHUB_RUN_ID', '')), 'run-identity-mismatch')
    return {k: env[k] for k in (*expected,'GITHUB_EVENT_NAME','GITHUB_SHA','GITHUB_WORKFLOW_SHA','GITHUB_RUN_ID')}


def source_identity(env, run, root=ROOT):
    identity = environment(env)
    def git(*args): return run(['git',*args],seconds=5,cap=256*1024).decode().strip()
    need(git('rev-parse','HEAD') == identity['GITHUB_SHA'], 'head-mismatch')
    need(git('rev-parse',BASE+'^{tree}') == BASE_TREE, 'base-tree-mismatch')
    need(git('rev-list','--parents','-n','1','HEAD').split() == [identity['GITHUB_SHA'],BASE], 'source-sole-parent-mismatch')
    need(git('status','--porcelain','--untracked-files=all') == '', 'source-not-clean')
    expected = sorted(['M\t'+p for p in MODIFIED_PATHS]+['A\t'+p for p in NEW_PATHS])
    need(sorted(git('diff','--name-status',BASE,'HEAD','--').splitlines()) == expected, 'source-scope-mismatch')
    rows = git('ls-files','-s','-z').rstrip('\0').split('\0'); need(0 < len(rows) <= 1024,'source-count-limit')
    files = {}
    for row in rows:
        head,path = row.split('\t');mode,blob,stage = head.split()
        need(mode in ('100644','100755') and stage == '0' and not Path(path).is_absolute()
             and '..' not in Path(path).parts, 'source-path-invalid')
        p=root/path; value=p.lstat()
        need(stat.S_ISREG(value.st_mode) and value.st_size <= 8*1024*1024,'source-file-invalid')
        raw=p.read_bytes()
        need(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==blob,'source-file-changed')
        files[path]={'mode':mode,'blob':blob,'sha256':hashlib.sha256(raw).hexdigest()}
    identity.update(base=BASE,base_tree=BASE_TREE,tree=git('rev-parse','HEAD^{tree}'),files=files)
    return identity


def mach_slices(raw):
    """Bounded native Mach-O header/load-command proof, including arm64_32.

    Apple's mach-o/loader.h and fat.h define the 28/32-byte headers, LC_UUID,
    LC_BUILD_VERSION and signature commands. No source or binary is executed.
    Actual dwarfdump output is independently compared to these UUIDs below.
    """
    need(len(raw)>=28,'mach-header-truncated')
    magic=raw[:4]
    if magic in MACH_MAGICS[4:]:
        count=struct.unpack_from('>I',raw,4)[0]; width=32 if magic==MACH_MAGICS[5] else 20
        need(0<count<=4 and 8+width*count<=len(raw),'fat-table-invalid')
        rows=[];seen=set();regions=[]
        for i in range(count):
            pos=8+i*width;cpu,subtype=struct.unpack_from('>II',raw,pos)
            if width==32:
                offset,size,align,reserved=struct.unpack_from('>QQII',raw,pos+8);need(reserved==0,'fat-reserved')
            else: offset,size,align=struct.unpack_from('>III',raw,pos+8)
            need(cpu not in seen and align<=30 and offset%(1<<align)==0
                 and offset>=8+width*count and size>=28 and offset+size<=len(raw),'fat-slice-bounds')
            need(all(offset+size<=a or offset>=b for a,b in regions),'fat-slice-overlap')
            need(raw[offset:offset+4] in MACH_MAGICS[:4],'nested-fat-or-unknown-slice')
            items=mach_slices(raw[offset:offset+size]);need(len(items)==1 and items[0]['cpu']==cpu and items[0]['subtype']==subtype,'fat-slice-identity')
            seen.add(cpu);regions.append((offset,offset+size));rows.extend(items)
        return rows
    need(magic in MACH_MAGICS[:4],'mach-magic-invalid')
    little=magic in (MACH_MAGICS[0],MACH_MAGICS[2]);wide=magic in MACH_MAGICS[:2]
    endian='<' if little else '>'; header=32 if wide else 28
    need(len(raw)>=header,'mach-header-truncated')
    _,cpu,subtype,kind,count,size,flags=struct.unpack_from(endian+'7I',raw)
    need(not wide or struct.unpack_from(endian+'I',raw,28)[0]==0,'mach-reserved')
    need(cpu in (0x100000c,0x200000c) and kind in (2,6,10),'mach-cpu-or-type')
    need(0<count<=4096 and count*8<=size<=1024*1024 and header+size<=len(raw),'load-command-bounds')
    cursor=header; uuids=[]; builds=[]; libraries=[]; install_ids=[]
    for _ in range(count):
        need(cursor+8<=header+size,'load-command-truncated')
        cmd,length=struct.unpack_from(endian+'II',raw,cursor)
        need(length>=8 and length%(8 if wide else 4)==0 and cursor+length<=header+size,'load-command-size')
        chunk=raw[cursor:cursor+length]
        if cmd==0x1b:
            need(length==24 and any(chunk[8:]),'uuid-command-invalid');uuids.append(str(uuid.UUID(bytes=chunk[8:])).upper())
        elif cmd==0x32:
            need(length>=24,'build-command-short');platform,minimum,sdk,tools=struct.unpack_from(endian+'4I',chunk,8)
            need(length==24+8*tools,'build-command-tools')
            decode=lambda v:[v>>16,(v>>8)&255,v&255]
            builds.append({'platform':platform,'minimum':decode(minimum),'sdk':decode(sdk)})
        elif cmd==0x1d:
            need(length==16 and struct.unpack_from(endian+'I',chunk,12)[0]==0,'code-signature-present')
        elif cmd in (0x21,0x2c):
            need(length>=(24 if cmd==0x2c else 20) and struct.unpack_from(endian+'I',chunk,16)[0]==0,'encrypted-binary')
        elif cmd in (0xd,0xc,0x80000018,0x8000001f,0x20,0x80000023):
            need(length>=24,'dylib-command-short');off=struct.unpack_from(endian+'I',chunk,8)[0]
            need(24<=off<length and b'\0' in chunk[off:],'dylib-command-string')
            (install_ids if cmd==0xd else libraries).append(chunk[off:].split(b'\0',1)[0].decode('utf-8'))
        cursor+=length
    need(cursor==header+size and len(uuids)==1,'uuid-or-command-completion')
    need(len(builds)==1 if kind in (2,6) else len(builds)<=1,'build-version-count')
    need(len(install_ids)==1 if kind==6 else len(install_ids)==0,'install-id-count')
    return [{'cpu':cpu,'subtype':subtype,'kind':kind,'uuid':uuids[0],
             'build':builds[0] if builds else None,'libraries':libraries,'install_ids':install_ids}]


def strings_dictionary(raw):
    try: value=plistlib.loads(raw)
    except (plistlib.InvalidFileException,ValueError,TypeError):
        text=raw.decode('utf-16' if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig')
        token=re.compile(r'\s*(?:(?://[^\n]*(?:\n|$)|/\*[\s\S]*?\*/)|("(?:[^"\\]|\\.)*")\s*=\s*("(?:[^"\\]|\\.)*")\s*;)')
        value={};offset=0
        while text[offset:].strip():
            match=token.match(text,offset);need(match is not None,'localization-grammar');offset=match.end()
            if match[1] is not None:
                key,item=json.loads(match[1]),json.loads(match[2]);need(key not in value,'localization-duplicate');value[key]=item
    need(isinstance(value,dict) and all(isinstance(k,str) and isinstance(v,str) for k,v in value.items()),'localization-not-dictionary')
    return value


def matching_uuids(raw, expected):
    found={}
    for line in raw.decode('utf-8').splitlines():
        match=re.fullmatch(r'UUID: ([0-9A-Fa-f-]{36}) \((arm64|arm64_32)\) (.+)',line)
        need(match is not None,'native-uuid-output-invalid')
        value,arch,path=match.groups();key=(path,arch)
        need(key not in found and key in expected,'native-uuid-product-mismatch')
        found[key]=str(uuid.UUID(value)).upper()
    need(found==expected,'native-uuid-mismatch')
    return [{'path':p,'architecture':a,'uuid':v} for (p,a),v in sorted(found.items())]


def compiled_assets(raw):
    values=json.loads(raw);need(isinstance(values,list) and 0<len(values)<=2048,'asset-catalog-invalid')
    icons=[]
    for row in values:
        need(isinstance(row,dict),'asset-record-invalid')
        if str(row.get('Name','')).startswith('AppIcon'):
            width,height=row.get('PixelWidth'),row.get('PixelHeight')
            if width is None and height is None:continue
            need(type(width) is int and type(height) is int and 0<width<=4096 and 0<height<=4096,'asset-dimensions')
            icons.append({k:row.get(k) for k in ('Name','PixelWidth','PixelHeight','Scale')})
    need(icons and len(icons)<=64,'compiled-appicon-missing')
    return {'records':len(values),'icons':icons,'raw_sha256':hashlib.sha256(raw).hexdigest()}


def materialize_watch_icon(root):
    source=root/'Celluloid/Assets.xcassets/AppIcon.appiconset/Icon-Marketing.png'
    raw=source.read_bytes();need(hashlib.sha256(raw).hexdigest()=='f4f7ca4326be0a7f017339545367ecfbe1fdae58da36cd3368305b056ce7c614','original-icon-changed')
    destination=root/'Platforms/watchOS/Assets.xcassets/AppIcon.appiconset/Generated-1024.png'
    need(not destination.exists() and not destination.is_symlink(),'watch-icon-output-not-fresh')
    need(destination.parent.resolve().is_relative_to(root.resolve()),'watch-icon-parent-escape')
    with destination.open('xb') as stream:stream.write(raw)

def icon_inputs(root):
    result={}
    for directory in ('Celluloid/Assets.xcassets','Platforms/watchOS/Assets.xcassets'):
        base=directory+'/AppIcon.appiconset';manifest=json.loads((root/base/'Contents.json').read_bytes())
        names=[base+'/'+v['filename'] for v in manifest['images'] if 'filename' in v]
        need(names and all(Path(name).parent.as_posix()==base for name in names),'icon-manifest-path')
        for name in names:
            p=root/name;s=p.lstat();need(stat.S_ISREG(s.st_mode) and s.st_nlink==1 and 33<=s.st_size<=8*1024*1024,'icon-input-missing')
            raw=p.read_bytes();need(raw[:16]==b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR','icon-input-not-png')
            result[name]={'sha256':hashlib.sha256(raw).hexdigest(),'dimensions':list(struct.unpack('>II',raw[16:24]))}
    need(result['Platforms/watchOS/Assets.xcassets/AppIcon.appiconset/Generated-1024.png']['sha256']==result['Celluloid/Assets.xcassets/AppIcon.appiconset/Icon-Marketing.png']['sha256'],'watch-icon-source-mismatch')
    return result

def snapkit_source(root,run):
    checkout=root/'build/SourcePackages/checkouts/SnapKit'
    need(checkout.is_dir() and not checkout.is_symlink(),'pinned-snapkit-checkout-missing')
    need(checkout.resolve().is_relative_to((root/'build/SourcePackages').resolve()),'pinned-snapkit-checkout-escape')
    rev=run(['git','-C',str(checkout),'rev-parse','HEAD'],seconds=5,cap=4096).decode().strip()
    need(rev==SNAPKIT_REVISION,'pinned-snapkit-revision-changed')
    need(run(['git','-C',str(checkout),'status','--porcelain','--untracked-files=all'],seconds=5,cap=65536).strip()==b'','pinned-snapkit-checkout-dirty')
    need({p.name for p in checkout.parent.iterdir()}=={'SnapKit'},'extra-remote-package-checkout')
    return {'revision':rev,'version':'5.7.1','path':'build/SourcePackages/checkouts/SnapKit','working_tree_clean':True}


def verify_archive(archive, run, deadline, *, root=ROOT, clock=time.monotonic, report=None):
    root=root.resolve();archive=Path(archive).parent.resolve()/Path(archive).name
    need(archive==root/ARCHIVE,'archive-path-mismatch');report={} if report is None else report
    catalogue=report.setdefault('archive_inventory',{});before=scan(archive,deadline,clock=clock,progress=catalogue)
    (root/'build/archive-inventory.json').write_text(json.dumps(before,sort_keys=True))
    timely(deadline,clock)
    def require_path(ok,reason,path):
        if not ok:report['offending_path']=str(path.relative_to(archive))
        need(ok,reason+': '+str(path.relative_to(archive)))
    def own(path,cap=64*1024*1024):
        timely(deadline,clock);key=str(path.relative_to(archive));item=before['paths'].get(key,{})
        require_path(item.get('type')=='file' and item.get('bytes',cap+1)<=cap,'unowned-or-large-file',path)
        with os.fdopen(os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK),'rb') as stream:
            require_path(file_identity(os.fstat(stream.fileno()))==item['identity'],'file-identity-changed',path)
            data=stream.read(cap+1)
        require_path(len(data)==item['bytes'] and hashlib.sha256(data).hexdigest()==item['sha256'],'file-content-changed',path)
        timely(deadline,clock);return data
    def metadata(path):
        value=plistlib.loads(own(path,1024*1024));require_path(isinstance(value,dict),'plist-not-dictionary',path);return value
    bundles={spec['app'] for spec in SPECS.values()};apps={APP,WATCH};dsyms={spec['dsym'] for spec in SPECS.values()}
    binaries={spec['binary'] for spec in SPECS.values()};dwarfs={spec['dwarf'] for spec in SPECS.values()}
    for key,item in before['paths'].items():
        p=archive/key
        require_path(item['type']!='symlink','archive-symlink-not-allowed',p)
        require_path(p.name not in ('_CodeSignature','CodeResources','embedded.mobileprovision','embedded.provisionprofile'),'signature-or-profile-present',p)
        require_path(p.suffix.lower() not in ('.xctest','.dylib','.swift','.o','.a') and 'fixture' not in p.name.lower(),'unexpected-code-or-fixture',p)
        if p.suffix in ('.app','.appex','.framework'):require_path(key in bundles and item['type']=='directory','unexpected-code-bundle',p)
        if p.suffix=='.bundle':require_path(key in RESOURCE_BUNDLES and item['type']=='directory','unexpected-resource-bundle',p)
        if p.suffix=='.dSYM':require_path(key in dsyms and item['type']=='directory','unexpected-dsym',p)
        if item['type']=='file':
            is_mach=bytes.fromhex(item.get('prefix_hex','')) in MACH_MAGICS
            require_path(not is_mach or key in binaries|dwarfs,'unexpected-mach-o',p)
            require_path(not item['identity'][2]&0o111 or key in binaries|dwarfs,'unexpected-executable-file',p)
            if p.name=='Info.plist':
                value=metadata(p)
                require_path('CFBundleExecutable' not in value or str(p.parent.relative_to(archive)) in bundles|dsyms,'hidden-code-metadata',p)
    require_path({k for k in before['paths'] if k.endswith(('.app','.appex','.framework'))}==bundles,'code-bundle-inventory-mismatch',archive)
    require_path({k for k in before['paths'] if k.endswith('.bundle')}==RESOURCE_BUNDLES,'resource-bundle-inventory-mismatch',archive)
    require_path({k for k in before['paths'] if k.endswith('.dSYM')}==dsyms,'dsym-inventory-mismatch',archive)
    meta=metadata(archive/'Info.plist');props=meta.get('ApplicationProperties',{})
    need(meta.get('ArchiveVersion')==2 and meta.get('SchemeName')=='Celluloid' and isinstance(meta.get('CreationDate'),datetime.datetime),'archive-metadata')
    need(isinstance(props,dict) and props.get('ApplicationPath')=='Applications/Celluloid.app'
         and props.get('CFBundleIdentifier')=='Mango.Celluloid'
         and str(props.get('CFBundleShortVersionString'))=='1.1' and str(props.get('CFBundleVersion'))=='2'
         and not any(props.get(k) for k in ('SigningIdentity','Team')),'archive-properties')
    proof={};expected_uuids={}
    for role,spec in SPECS.items():
        app=archive/spec['app'];info=metadata(app/'Info.plist')
        expected={'CFBundleIdentifier':spec['bundle'],'CFBundleExecutable':spec['executable'],
          'CFBundlePackageType':spec['package'],'CFBundleShortVersionString':spec['version'],'CFBundleVersion':spec['build'],
          'MinimumOSVersion':spec['floor'],'CFBundleSupportedPlatforms':spec['platforms'],'DTPlatformName':spec['platform_name']}
        if 'family' in spec:expected['UIDeviceFamily']=spec['family']
        require_path(all(info.get(k)==v for k,v in expected.items()),'product-identity',app/'Info.plist')
        if role=='watch':
            require_path(info.get('WKApplication') is True and info.get('WKCompanionAppBundleIdentifier')=='Mango.Celluloid' and 'WKRunsIndependentlyOfCompanionApp' not in info,'watch-companion',app/'Info.plist')
        assets=None
        if role in ('phone','watch'):
            require_path('AppIcon' in json.dumps({k:v for k,v in info.items() if k.startswith('CFBundleIcon')}),'icon-metadata',app/'Info.plist')
            assets=compiled_assets(run(['xcrun','assetutil','--info',str(app/'Assets.car')],seconds=15,cap=256*1024,cleanup=10))
            require_path(len(own(app/'Assets.car'))>64,'compiled-assets-empty',app/'Assets.car')
            require_path(own(app/'PkgInfo')==b'APPL????','package-type',app/'PkgInfo')
        if role in ('phone','watch','kit'):
            local_root=root/('Celluloid' if role=='phone' else 'CelluloidKit/Constant' if role=='kit' else 'Platforms/Resources')
            for language in ('en','zh-Hans'):
                name=language+'.lproj/Localizable.strings'
                require_path(strings_dictionary(own(app/name))==strings_dictionary((local_root/name).read_bytes()),'localization-source-mismatch',app/name)
        executable=archive/spec['binary'];symbol=archive/spec['dwarf'];raw=own(executable);rows=mach_slices(raw);symbols=mach_slices(own(symbol))
        require_path({v['cpu'] for v in rows}==set(spec['arches']) and all(v['kind']==spec['kind'] for v in rows),'binary-architectures',executable)
        require_path({v['cpu'] for v in symbols}==set(spec['arches']) and all(v['kind']==10 for v in symbols),'symbol-architectures',symbol)
        for value in rows:
            arch,minimum=spec['arches'][value['cpu']]
            require_path(value['build']=={'platform':spec['platform'],'minimum':minimum,'sdk':spec['sdk']},'binary-platform-floor-sdk',executable)
            require_path(all(x.startswith(('/System/Library/Frameworks/','/usr/lib/')) and 'XCTest' not in x or x in BUNDLED_DEPENDENCIES[spec['app']] for x in value['libraries']),'unexpected-linked-code',executable)
            require_path({x for x in value['libraries'] if x.startswith('@rpath/')}==BUNDLED_DEPENDENCIES[spec['app']],'bundled-dependency-identity',executable)
            require_path(value['install_ids']==([INSTALL_NAMES[spec['app']]] if spec['app'] in INSTALL_NAMES else []),'framework-install-identity',executable)
            matching=[v for v in symbols if v['cpu']==value['cpu'] and v['subtype']==value['subtype']]
            require_path(len(matching)==1 and matching[0]['uuid']==value['uuid'],'symbol-uuid-binding',symbol)
            for p in (executable,symbol):expected_uuids[(str(p),arch)]=value['uuid']
        require_path(not any(token in raw for token in (b'CELLULOID_PHONE_LAYOUT_FIXTURE',b'WatchProcessingLargeTextUI',b'CELLULOID_PHONE_OUTPUT_PROOF',b'PhoneOutputProof',b'companion.synthetic-seed',b'CELLULOID_EXPORT_FULL_CANVAS_CONTROL',b'CELLULOID_EXPORT_WARMING_ONLY_CONTROL',b'--photos-denied',b'--photos-limited-empty',b'--ui-diagnostics',b'outputWriterPreparedForTesting',b'PHONE_COMPANION_ROW_ACTION')),'release-diagnostic-marker',executable)
        dsym=metadata(archive/spec['dsym']/'Contents/Info.plist')
        require_path(dsym.get('CFBundleIdentifier')=='com.apple.xcode.dsym.'+spec['bundle'] and dsym.get('CFBundlePackageType')=='dSYM','dsym-metadata',symbol)
        require_path(not any('/XCTest.framework/' in x for v in rows for x in v['libraries']),'test-framework',executable)
        if role=='phone':
            require_path(b'PhoneCompanionController' in raw and b'PhoneCompanionEntryController' in raw,'receiver-not-in-parent',executable)
            require_path(all(any('/WatchConnectivity.framework/' in x for x in v['libraries']) for v in rows),'receiver-framework-not-linked',executable)
            original=plistlib.loads((root/'Celluloid/Info.plist').read_bytes())
            for key in ('NSPhotoLibraryUsageDescription','NSPhotoLibraryAddUsageDescription','PHPhotoLibraryPreventAutomaticLimitedAccessAlert','UILaunchStoryboardName','UIRequiredDeviceCapabilities'):
                require_path(info.get(key)==original[key],'phone-source-metadata-mismatch',app/'Info.plist')
        if role=='extension':
            original=plistlib.loads((root/'CelluloidPhotoExtension/Info.plist').read_bytes())
            require_path(info.get('NSExtension')==original['NSExtension'],'photos-extension-metadata',app/'Info.plist')
        proof[role]={'info':info,'assets':assets,'binaries':rows,'symbols':symbols,'dSYM_metadata':dsym}
    # Exact original iOS resources plus the real newly linked package resources.
    for relative,source in [(APP+'/collage.json','Celluloid/collage.json'),(KIT+'/bubble.json','CelluloidKit/bubble.json'),(KIT+'/SnapKit-LICENSE.txt','CelluloidKit/ThirdPartyNotices/SnapKit-LICENSE.txt'),(WATCH+'/LICENSE.txt','LICENSE.txt'),(WATCH+'/PrivacyPolicy.txt','Platforms/Resources/PrivacyPolicy.txt')]:
        require_path(own(archive/relative)==(root/source).read_bytes(),'resource-source-mismatch',archive/relative)
    require_path(len(own(archive/KIT/'Assets.car'))>64,'kit-assets-missing',archive/KIT/'Assets.car')
    for relative in (APP+'/Base.lproj/LaunchScreen.storyboardc',EXT+'/Base.lproj/MainInterface.storyboardc'):
        require_path(before['paths'].get(relative,{}).get('type')=='directory','storyboard-missing',archive/relative)
    rel=APP+'/zh-Hans.lproj/InfoPlist.strings'
    require_path(strings_dictionary(own(archive/rel))==strings_dictionary((root/'Celluloid/zh-Hans.lproj/InfoPlist.strings').read_bytes()),'photos-usage-localization',archive/rel)
    privacy=[]
    for key in before['paths']:
        if key.endswith('.xcprivacy'):
            require_path(key in {p+'/PrivacyInfo.xcprivacy' for p in SNAPKIT_RESOURCES},'unexpected-privacy-location',archive/key)
            require_path(metadata(archive/key)==PRIVACY,'pinned-snapkit-privacy',archive/key);privacy.append(key)
    need(set(privacy)=={p+'/PrivacyInfo.xcprivacy' for p in SNAPKIT_RESOURCES},'missing-snapkit-privacy')
    need(len({before['paths'][p]['sha256'] for p in privacy})==1,'snapkit-privacy-copy-mismatch')
    for bundle in SNAPKIT_RESOURCES:
        actual={p[len(bundle)+1:] for p,v in before['paths'].items() if p.startswith(bundle+'/') and v['type']=='file'}
        need(actual=={'Info.plist','PrivacyInfo.xcprivacy'},'snapkit-resource-inventory-mismatch')
    for bundle in RESOURCE_BUNDLES:
        info=metadata(archive/bundle/'Info.plist')
        require_path(info.get('CFBundlePackageType')=='BNDL' and not info.get('CFBundleExecutable'),'resource-bundle-code',archive/bundle/'Info.plist')
    for bundle,resources in PACKAGE_RESOURCES.items():
        expected=set(resources)|{'Info.plist'}
        actual={p[len(bundle)+1:] for p,v in before['paths'].items() if p.startswith(bundle+'/') and v['type']=='file'}
        need(actual==expected,'package-resource-inventory-mismatch')
        for relative,source in resources.items():
            packed=own(archive/bundle/relative);original=(root/source).read_bytes()
            same=strings_dictionary(packed)==strings_dictionary(original) if relative.endswith('.strings') else packed==original
            require_path(same,'package-resource-source-mismatch',archive/bundle/relative)
    proof['privacy']={'snapkit_manifests':privacy,'phone_application_manifest_present':False,'watch_application_manifest_present':False,'scope':'Observed original declarations only; no Store privacy approval inferred.'}
    paths=[str(archive/spec[key]) for spec in SPECS.values() for key in ('binary','dwarf')]
    proof['native_uuid_readback']=matching_uuids(run(['xcrun','dwarfdump','--uuid',*paths],seconds=15,cap=16384,cleanup=10),expected_uuids)
    proof['watch_copy']=verify_watch_copy(root,archive,run,deadline,clock)
    after=scan(archive,deadline,clock=clock,hash_files=False)
    need({k:v['identity'] for k,v in before['paths'].items()}=={k:v['identity'] for k,v in after['paths'].items()},'archive-changed-during-proof')
    timely(deadline,clock)
    proof.update(unsigned=True,archive_entries=before['entries'],archive_bytes=before['bytes'],distribution_version_ready=False)
    return proof


def verify_watch_copy(root,archive,run,deadline,clock):
    # Xcode's archive BuildProductsPath is a fixed producer link. Resolve only
    # inside this invocation's new DerivedData, never to an external product.
    derived=(root/DERIVED).resolve()
    candidate=derived/'Build/Intermediates.noindex/ArchiveIntermediates/Celluloid/BuildProductsPath/Release-watchos/CelluloidWatch.app'
    producer=candidate.resolve(strict=True)
    need(producer.is_relative_to(derived) and producer.name=='CelluloidWatch.app','watch-producer-outside-derived')
    embedded=archive/WATCH
    left=scan(embedded,deadline,clock=clock);right=scan(producer,deadline,clock=clock)
    def hashes(value): return {k:v['sha256'] for k,v in value['paths'].items() if v['type']=='file'}
    a,b=hashes(left),hashes(right);need(a.keys()==b.keys(),'watch-producer-inventory-mismatch')
    changed=[k for k in a if a[k]!=b[k]];transform='exact'
    if changed:
        need(changed==['CelluloidWatch'],'watch-producer-resource-mismatch')
        normalized=root/'build/normalized-watch-executable'
        need(not normalized.exists() and not normalized.is_symlink(),'watch-normalization-output-exists')
        run(['xcrun','strip','-D','-S','-no_atom_info',str(producer/'CelluloidWatch'),'-o',str(normalized)],seconds=15,cap=16384,cleanup=10)
        s=normalized.lstat();need(stat.S_ISREG(s.st_mode) and s.st_nlink==1 and s.st_size<=64*1024*1024,'watch-normalization-output-invalid')
        need(hashlib.sha256(normalized.read_bytes()).hexdigest()==a['CelluloidWatch'],'watch-copy-transform-mismatch');transform='strip -D -S -no_atom_info'
    # Reobserve the producer, so an executable swap cannot hide behind the copy.
    final=scan(producer,deadline,clock=clock,hash_files=False)
    need({k:v['identity'] for k,v in right['paths'].items()}=={k:v['identity'] for k,v in final['paths'].items()},'watch-producer-changed')
    return {'producer':str(producer.relative_to(root)),'files':len(a),'transform':transform,
            'producer_executable_sha256':b['CelluloidWatch'],'embedded_executable_sha256':a['CelluloidWatch']}


def execute(*,env=None,root=ROOT,clock=time.monotonic,runner=capture):
    env=os.environ if env is None else env;root=root.resolve();began=clock();receipts=[];phase='prepare';phase_deadline=began+180
    report={'schema':1,'scope':'Celluloid-iOS-Watch-unsigned-archive-observation','qualified':False,
      'signing_qualified':False,'store_qualified':False,'upload_qualified':False,'binary_handoff':False,
      'older_os_qualified':False,'ui_qualification_separate':True,'distribution_version_ready':False,
      'commands':receipts,'clock':{'started_monotonic':began,'phase_end_seconds':PHASE_END,
      'report_ready_deadline':began+PHASE_END['final_source_pack']},
      'host_scope':'owned-client-and-process-group-observation; no simulator or independent-daemon lifetime claim'}
    def run(argv,**kw):return command(argv,deadline=phase_deadline,receipts=receipts,clock=clock,runner=runner,**kw)
    try:
        need(not (root/'build').exists() and not (root/'build').is_symlink(),'output-not-fresh');(root/'build').mkdir()
        report['owned_output']=file_identity((root/'build').lstat())[:2]
        report['source_before']=source_identity(env,run,root)
        report['toolchain']={'xcode':run(['xcodebuild','-version'],seconds=10,cap=4096).decode(),
          'sdks':run(['xcodebuild','-showsdks'],seconds=15,cap=16384).decode()}
        need(report['toolchain']['xcode'].strip().splitlines()==['Xcode 27.0','Build version 27A266a'],'toolchain-mismatch')
        need(all(s in report['toolchain']['sdks'] for s in ('iphoneos27.0','watchos27.0')),'sdk-mismatch')
        for optimize in ([],['-O']):
            run([sys.executable,*optimize,'-m','unittest','discover','-s','Scripts','-p','test_ios_watch_*.py'],seconds=40,cap=65536)
        run([sys.executable,'Scripts/generate_ios_watch_project.py'],seconds=10,cap=4096)
        need(source_identity(env,run,root)==report['source_before'],'generated-project-changed')
        materialize_watch_icon(root)
        report['generated_icons']=icon_inputs(root);timely(began+PHASE_END['prepare'],clock)
        phase='archive';phase_deadline=min(began+PHASE_END[phase],clock()+620)
        output=run(ARCHIVE_COMMAND,seconds=600,cap=ARCHIVE_RAW_CAP,cleanup=10,archive_output=True)
        report['archive_success_marker_observed']=b'** ARCHIVE SUCCEEDED **' in output
        need(not receipts[-1]['archive_log']['error_marker_found'],'archive-reported-error')
        phase='proof';phase_deadline=min(began+PHASE_END[phase],clock()+150)
        report['snapkit']=snapkit_source(root,run)
        report['proof']=verify_archive(root/ARCHIVE,run,phase_deadline,root=root,clock=clock,report=report)
        phase='final_source_pack';phase_deadline=min(began+PHASE_END[phase],clock()+30);report['clock']['report_ready_deadline']=phase_deadline
        need(icon_inputs(root)==report['generated_icons'],'icon-input-changed')
        report['source_after']=source_identity(env,run,root)
        need(report['source_after']==report['source_before'],'source-changed');timely(phase_deadline,clock);report['qualified']=True
    except (Exception,KeyboardInterrupt) as error:
        report['clock']['report_ready_deadline']=min(report['clock']['report_ready_deadline'],clock()+30)
        report['failure']={'phase':phase,'type':type(error).__name__,'reason':str(error)[:4096],
                          'offending_path':report.get('offending_path') or report.get('archive_inventory',{}).get('last_path')}
    report['clock']['elapsed_seconds']=clock()-began
    return report
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
