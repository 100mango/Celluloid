#!/usr/bin/env python3
"""Fixed, bounded unsigned universal Mac archive proof; never a signing handoff.

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
import xml.etree.ElementTree as ET

import mac_archive_macho as package
from mac_archive_capture import capture, CaptureStopped

ROOT = Path(__file__).resolve().parents[1]
BASE = 'b8b6aa890df8b4f16f5627c965d01585a21fe97b'
BASE_TREE = '8bd5f17720c0b7b8aa6ddf591cf0ec0fc7099735'
BRANCH = 'refs/heads/codex/mac-unsigned-archive'
WORKFLOW = '.github/workflows/mac-unsigned-archive.yml'
NEW_PATHS = (WORKFLOW,'Scripts/mac_unsigned_archive.py','Scripts/test_mac_unsigned_archive.py',
    'Scripts/mac_archive_macho.py','Scripts/mac_archive_capture.py','Scripts/owned_process_group.py','Scripts/fixtures/mac-archive-inputs.json','MAC-UNSIGNED-ARCHIVE.md')
ARCHIVE = Path('build/CelluloidMac.xcarchive')
APP = 'Products/Applications/CelluloidMac.app'
DSYM = 'dSYMs/CelluloidMac.app.dSYM'
DWARF = DSYM + '/Contents/Resources/DWARF/CelluloidMac'
EXECUTABLE = APP + '/Contents/MacOS/CelluloidMac'
EXT = APP + '/Contents/PlugIns/CelluloidMacPhotosExtension.appex'
EXT_EXECUTABLE = EXT + '/Contents/MacOS/CelluloidMacPhotosExtension'
EXT_DSYM = 'dSYMs/CelluloidMacPhotosExtension.appex.dSYM'
EXT_DWARF = EXT_DSYM + '/Contents/Resources/DWARF/CelluloidMacPhotosExtension'
PRODUCTS = ((APP, EXECUTABLE, DSYM, DWARF, 'CelluloidMac', 'Mango.Celluloid', 'APPL', 'macOS'),
            (EXT, EXT_EXECUTABLE, EXT_DSYM, EXT_DWARF, 'CelluloidMacPhotosExtension', 'Mango.Celluloid.CelluloidPhotoExtension', 'XPC!', 'macOSExtension'))
DEBUG_MARKERS = (b'--celluloid-sandbox-diagnostics', b'sandbox.probe', b'CELLULOID_AX_REPORT',
    b'CELLULOID_NATIVE_AUDIT_CONTROL', b'CELLULOID_UNDO_DIAGNOSTICS', b'TextRenderProbe', b'textRenderProbe',
    b'CELLULOID_EXTENSION_SELF_IDENTITY_V1', b'Celluloid.ExtensionSelfIdentity.1', b'photos-extension.self-identity',
    b'MacPhotoSelfIdentity', b'CELLULOID_OWNED_PHOTOS_BOUNDARY_PROBE', b'CELLULOID_MAC_PHOTOS_BOUNDARY',
    b'Celluloid synthetic container readback', b'CelluloidOwnedPhotosBoundary', b'CELLULOID_OWNED_PHOTOS_BOUNDARY_ARM_V1', b'photos-extension.boundary-arm')
MAX_ENTRIES, MAX_BYTES, SCAN_SECONDS = 2048, 1024 ** 3, 30
MAX_INVENTORY = 1024 ** 2
MAX_REPORT = 2 * 1024 ** 2
ARCHIVE_COMMAND = ['xcodebuild','-project','CelluloidNative.xcodeproj','-scheme','CelluloidMac',
    '-configuration','Release','-sdk','macosx','-destination','generic/platform=macOS','-archivePath',str(ARCHIVE),
    '-derivedDataPath','build/MacArchiveDerived','ARCHS=arm64 x86_64','ONLY_ACTIVE_ARCH=NO',
    'CODE_SIGNING_ALLOWED=NO','DEBUG_INFORMATION_FORMAT=dwarf-with-dsym','archive']
PHASE_END = {'prepare':180,'archive':800,'proof':950,'final_source_pack':980,'evidence':1040,'finalization':1060}
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


def command(argv, *, deadline, seconds, cap, receipts, clock=time.monotonic,
            runner=capture, cleanup=2):
    """One command grant with the existing helper's two cleanup phases reserved."""
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
                       cancelled_signal=error.cancelled_signal,
                       stdout=getattr(error, 'stdout_prefix', b'')[:cap].decode('utf-8', 'replace'),
                       stderr=getattr(error, 'stderr_capture', b'')[:cap].decode('utf-8', 'replace'))
        raise Rejected('capture-stopped') from error
    finally:
        receipt['end'] = clock()
    receipt.update(returncode=result.returncode, stdout=result.stdout.decode('utf-8', 'replace'),
                   stderr=result.stderr.decode('utf-8', 'replace'),
                   owned_host_observation='client-reaped-pipes-closed-group-absent-at-return')
    need(len(result.stdout) + len(result.stderr) <= cap, 'command-byte-limit')
    need(receipt['end'] < start + grant and receipt['end'] < deadline, 'command-late-return')
    need(result.returncode == 0, 'command-failed')
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
    need(lineage == [identity['GITHUB_SHA'], BASE], 'source-sole-parent-mismatch')
    identity['parents'] = lineage[1:]
    need(git('status', '--porcelain', '--untracked-files=all') == '', 'source-not-clean')
    differences = git('diff', '--name-status', BASE, 'HEAD', '--').splitlines()
    need(sorted(differences) == sorted('A\t' + p for p in NEW_PATHS), 'source-scope-mismatch')
    identity.update(tree=git('rev-parse', 'HEAD^{tree}'), base=BASE, base_tree=BASE_TREE)
    fixture=json.loads((root/'Scripts/fixtures/mac-archive-inputs.json').read_bytes())
    need(fixture['parent']==BASE and fixture['parent_tree']==BASE_TREE,'input-fixture-base-mismatch')
    for path,expected in fixture['app_inputs'].items():
        need(hashlib.sha256((root/path).read_bytes()).hexdigest()==expected,'app-input-changed: '+path)
    scheme=root/'CelluloidNative.xcodeproj/xcshareddata/xcschemes/CelluloidMac.xcscheme'
    parsed=ET.fromstring(scheme.read_bytes())
    need(parsed.find('ArchiveAction').get('buildConfiguration')=='Release','archive-configuration-mismatch')
    entries=parsed.findall('./BuildAction/BuildActionEntries/BuildActionEntry')
    archived=[e.find('BuildableReference') for e in entries if e.get('buildForArchiving')=='YES']
    need(len(archived)==1 and archived[0].get('BuildableName')=='CelluloidMac.app' and
        archived[0].get('BlueprintName')=='CelluloidMac' and archived[0].get('ReferencedContainer')=='container:CelluloidNative.xcodeproj','archive-scheme-mismatch')
    paths=sorted(set(NEW_PATHS)|set(fixture['app_inputs']))
    identity['files']={path:hashlib.sha256((root/path).read_bytes()).hexdigest() for path in paths}
    identity['app_input_count']=len(fixture['app_inputs'])
    return identity


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
                        h=hashlib.sha256();count=0;prefix=b''
                        with os.fdopen(os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK),'rb') as stream:
                            admit(file_identity(os.fstat(stream.fileno()))==receipt['identity'],'archive-file-changed',key)
                            while chunk:=stream.read(1024*1024):
                                timely(deadline,clock);count+=len(chunk);admit(count<=value.st_size,'archive-file-grew',key)
                                if not prefix:prefix=chunk[:4]
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


def dwarf_headers(raw):
    """Reuse mature fat-table bounds while checking DWARF's different file type."""
    need(len(raw)>=32,'dwarf-header-truncated')
    if raw[:4] in package.MACH_MAGICS[2:]:
        count=struct.unpack_from('>I',raw,4)[0];width=32 if raw[:4]==package.MACH_MAGICS[3] else 20
        need(0<count<=8 and 8+width*count<=len(raw),'dwarf-fat-table-invalid')
        cpus=set();intervals=[];result={}
        for i in range(count):
            pos=8+i*width;cpu,subtype=struct.unpack_from('>II',raw,pos)
            if width==32:
                offset,size,align,reserved=struct.unpack_from('>QQII',raw,pos+8);need(reserved==0,'dwarf-fat-reserved')
            else:offset,size,align=struct.unpack_from('>III',raw,pos+8)
            need(cpu not in cpus and align<=30 and offset%(1<<align)==0 and offset>=8+width*count and size>=32 and offset+size<=len(raw),'dwarf-fat-slice-invalid')
            need(all(offset+size<=a or offset>=b for a,b in intervals),'dwarf-fat-overlap')
            need(raw[offset:offset+4] in package.MACH_MAGICS[:2],'dwarf-nested-fat')
            found=dwarf_headers(raw[offset:offset+size]);need(found=={cpu:subtype},'dwarf-fat-cpu-mismatch');cpus.add(cpu);result[cpu]=subtype;intervals.append((offset,offset+size))
        return result
    need(raw[:4] in package.MACH_MAGICS[:2],'dwarf-mach-magic')
    endian='<' if raw[:4]==package.MACH_MAGICS[0] else '>'
    _,cpu,subtype,kind,commands,size,flags,reserved=struct.unpack_from(endian+'8I',raw)
    need(kind==10 and reserved==0 and 0<commands<=4096 and 32+size<=len(raw),'dwarf-mach-identity')
    return {cpu:subtype}


def matching_uuid(raw, executable, dwarf):
    rows=raw.decode('utf-8').splitlines();found={}
    pattern=r'UUID: ([0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}) \((arm64|x86_64)\) (.+)'
    for line in rows:
        match=re.fullmatch(pattern,line);need(match is not None,'uuid-output-invalid')
        uuid,arch,path=match.groups();key=(path,arch)
        need(path in (str(executable),str(dwarf)) and key not in found and uuid.replace('-','').strip('0'),'uuid-product-mismatch')
        found[key]=uuid.upper()
    need(set(found)=={(str(path),arch) for path in (executable,dwarf) for arch in ('arm64','x86_64')},'uuid-architecture-mismatch')
    need(all(found[(str(executable),a)]==found[(str(dwarf),a)] for a in ('arm64','x86_64')),'uuid-mismatch')
    return {a:found[(str(executable),a)] for a in ('arm64','x86_64')}


def read_metadata(path, deadline, clock):
    timely(deadline, clock)
    need(path.lstat().st_size <= 64 * 1024, 'metadata-byte-limit')
    with path.open('rb') as stream:
        raw = stream.read(64 * 1024 + 1)
    need(len(raw) <= 64 * 1024, 'metadata-byte-limit')
    result = plistlib.loads(raw)
    timely(deadline, clock)
    need(isinstance(result, dict), 'metadata-not-dictionary')
    return result


def observe_archive_files(archive, deadline, *, root=ROOT, clock=time.monotonic, report=None):
    report={} if report is None else report
    catalogue=report.setdefault('archive_inventory',{})
    before=scan(archive,deadline,clock=clock,progress=catalogue)
    # Persist the complete bounded names/types/bytes/hash catalogue before policy.
    (root/'build/archive-inventory.json').write_bytes(json.dumps(before,sort_keys=True).encode())
    timely(deadline,clock)
    # Capture all three fixed plist observations before any semantic rejection.
    # Each read keeps the existing 64 KiB and original proof-deadline bounds.
    metadata_paths=('Info.plist', *[path+'/Contents/Info.plist' for product in PRODUCTS for path in (product[0],product[2])])
    observations=report.setdefault('archive_metadata_diagnostics',{})
    values={};read_errors=[]
    for key in metadata_paths:
        report['current_proof_path']=key
        try:
            need(before['paths'].get(key,{}).get('type')=='file','metadata-not-regular-file')
            value=read_metadata(archive/key,deadline,clock)
            observations[key]={'metadata':value};values[key]=value
        except Exception as error:
            observations[key]={'read_error':{'type':type(error).__name__,'reason':str(error)[:4096]}}
            read_errors.append((key,error))
    if read_errors:
        report['current_proof_path'],error=read_errors[0]
        raise error
    report.pop('current_proof_path',None)
    return before,values,metadata_paths


def mach_security(raw):
    """Read already-validated Mach-O slices; observe entitlements without signing."""
    package.mach_info(raw)
    if raw[:4] in package.MACH_MAGICS[2:]:
        count=struct.unpack_from('>I',raw,4)[0];width=32 if raw[:4]==package.MACH_MAGICS[3] else 20
        output=[]
        for i in range(count):
            pos=8+i*width
            offset,size=struct.unpack_from('>QQ' if width==32 else '>II',raw,pos+8)
            output.extend(mach_security(raw[offset:offset+size]))
        return output
    endian='<' if raw[:4]==package.MACH_MAGICS[0] else '>'
    cpu=struct.unpack_from(endian+'I',raw,4)[0];count=struct.unpack_from(endian+'I',raw,16)[0]
    position=32;result={'cpu':cpu,'linked_entitlements':[],'signature_entitlements':[],
        'code_signature_present':False,'cms_signature_present':False,'der_entitlement_present':False}
    for _ in range(count):
        cmd,size=struct.unpack_from(endian+'II',raw,position)
        if cmd==0x19:  # LC_SEGMENT_64
            need(size>=72,'security-segment-truncated');n=struct.unpack_from(endian+'I',raw,position+64)[0]
            need(72+80*n==size,'security-section-table-invalid')
            for i in range(n):
                pos=position+72+i*80;name=raw[pos:pos+16].split(b'\0')[0]
                if name in (b'__entitlements',b'__info_plist'):
                    length=struct.unpack_from(endian+'Q',raw,pos+40)[0];offset=struct.unpack_from(endian+'I',raw,pos+48)[0]
                    need(0<length<=65536 and offset+length<=len(raw),'security-section-bounds')
                    value=plistlib.loads(raw[offset:offset+length].rstrip(b'\0'))
                    need(isinstance(value,dict),'security-section-not-dictionary')
                    result.setdefault('linked_info_plists' if name==b'__info_plist' else 'linked_entitlements',[]).append(value)
        if cmd==0x1d:  # LC_CODE_SIGNATURE, linker ad-hoc blobs may exist when signing is disabled.
            need(size==16 and not result['code_signature_present'],'signature-command-invalid')
            offset,length=struct.unpack_from(endian+'II',raw,position+8)
            need(12<=length<=1024*1024 and offset+length<=len(raw),'signature-blob-bounds')
            blob=raw[offset:offset+length];magic,total,n=struct.unpack_from('>III',blob)
            need(magic==0xfade0cc0 and 12<=total<=length and n<=64 and 12+8*n<=total,'signature-superblob-invalid')
            result['code_signature_present']=True;slots=set()
            for i in range(n):
                slot,start=struct.unpack_from('>II',blob,12+i*8)
                need(slot not in slots and 12+8*n<=start and start+8<=total,'signature-slot-invalid');slots.add(slot)
                kind,amount=struct.unpack_from('>II',blob,start)
                need(amount>=8 and start+amount<=total,'signature-slot-bounds')
                payload=blob[start+8:start+amount]
                if slot==5:
                    need(kind==0xfade7171 and len(payload)<=65536,'signature-entitlements-invalid')
                    value=plistlib.loads(payload.rstrip(b'\0'));need(isinstance(value,dict),'signature-entitlements-not-dictionary');result['signature_entitlements'].append(value)
                if slot==7:result['der_entitlement_present']=bool(payload)
                if slot==0x10000:result['cms_signature_present']=bool(payload)
        position+=size
    return [result]


def verify_icon_inputs(root=ROOT):
    provenance=json.loads((root/'Platforms/macOS/icon-provenance.json').read_bytes())
    need(hashlib.sha256((root/provenance['source']).read_bytes()).hexdigest()==provenance['source_sha256'],'original-icon-source-mismatch')
    folder=root/'Platforms/macOS/Assets.xcassets/AppIcon.appiconset'
    slots=json.loads((folder/'Contents.json').read_bytes())['images']
    rows=provenance['renditions'];need(len(rows)==10 and {x['file'] for x in rows}=={x['filename'] for x in slots},'icon-slot-mismatch')
    for row in rows:
        raw=(folder/row['file']).read_bytes()
        need(raw[:8]==b'\x89PNG\r\n\x1a\n' and len(raw)>24 and hashlib.sha256(raw).hexdigest()==row['sha256'] and
             list(struct.unpack_from('>II',raw,16))==[row['pixels']]*2,'icon-byte-identity-mismatch')
    return provenance


def verify_archive(archive, run, deadline, *, root=ROOT, clock=time.monotonic, report=None):
    started=clock();report={} if report is None else report
    before,values,metadata_paths=observe_archive_files(archive,deadline,root=root,clock=clock,report=report)
    def need_path(ok,reason,path):
        if not ok:report['offending_path']=str(path.relative_to(archive))
        need(ok,reason+': '+str(path.relative_to(archive)))
    def regular(key):return before['paths'].get(key,{}).get('type')=='file'
    for key,item in before['paths'].items():
        path=archive/key
        need_path(path.name not in ('embedded.mobileprovision','embedded.provisionprofile','_CodeSignature') and
            path.suffix!='.xctest','unexpected-test-or-provisioning-payload',path)
        if path.suffix in ('.app','.appex','.dSYM'):
            need_path(key in (APP,EXT,DSYM,EXT_DSYM),'unexpected-nested-product',path)
    metadata=values['Info.plist']
    need_path(type(metadata.get('ArchiveVersion')) is int and metadata['ArchiveVersion']==2 and metadata.get('SchemeName')=='CelluloidMac','archive-metadata-mismatch',archive/'Info.plist')
    need_path(isinstance(metadata.get('CreationDate'),datetime.datetime),'archive-creation-date-missing',archive/'Info.plist')
    properties=metadata.get('ApplicationProperties',{})
    need_path(isinstance(properties,dict),'archive-application-properties-type',archive/'Info.plist')
    need_path(not any(properties.get(k) for k in ('SigningIdentity','Team')),'distribution-signing-identity-present',archive/'Info.plist')
    product_proofs={};binaries={};security={};dwarfs=set()
    for key,item in before['paths'].items():
        if item['type']!='file' or bytes.fromhex(item.get('prefix_hex','')) not in MACH_MAGICS:continue
        path=archive/key;need_path(item['bytes']<=64*1024*1024,'Mach-O-byte-cap',path)
        report['current_proof_path']=key;raw=path.read_bytes();timely(deadline,clock)
        if key in (DWARF,EXT_DWARF):
            need_path(set(dwarf_headers(raw))=={0x100000c,0x1000007},'dwarf-architecture-mismatch',path);dwarfs.add(key);continue
        rows=package.mach_info(raw)
        need_path(key in (EXECUTABLE,EXT_EXECUTABLE) and set(x['cpu'] for x in rows)=={0x100000c,0x1000007},'binary-product-or-architecture-mismatch',path)
        need_path(all(x['platform']==1 and x['minimum']==[13,0,0] and x['sdk']==[27,0,0] for x in rows),'binary-platform-version-mismatch',path)
        need_path(all(x['kind']==2 for x in rows),'binary-kind-mismatch',path)
        need_path(not any(bad in raw for bad in DEBUG_MARKERS),'debug-test-seam-present',path)
        need_path(all(link.startswith(('/System/Library/Frameworks/','/usr/lib/')) for row in rows for link in row['libraries']),'non-system-runtime-linked',path)
        binaries[key]=rows;security[key]=mach_security(raw)
        need_path(not any(row['cms_signature_present'] for row in security[key]),'distribution-signature-present',path)
    need_path(set(binaries)=={EXECUTABLE,EXT_EXECUTABLE} and dwarfs=={DWARF,EXT_DWARF},'required-or-unexpected-binary',archive/EXECUTABLE)
    for bundle,executable,dsym,dwarf,name,identifier,kind,platform in PRODUCTS:
        info_path=bundle+'/Contents/Info.plist';info=values[info_path]
        expected={'CFBundleIdentifier':identifier,'CFBundleExecutable':name,'CFBundleName':'Celluloid','CFBundlePackageType':kind,
            'CFBundleShortVersionString':'1.1','CFBundleVersion':'2','LSMinimumSystemVersion':'13.0','DTPlatformName':'macosx','DTSDKName':'macosx27.0'}
        need_path(all(info.get(k)==v for k,v in expected.items()),'application-identity-mismatch',archive/info_path)
        source_info=read_metadata(root/('Platforms/'+platform+'/Info.plist'),deadline,clock)
        for k in ('CFBundleDocumentTypes','UTExportedTypeDeclarations','CFBundleLocalizations'):
            need_path(info.get(k)==source_info.get(k),'document-or-localization-metadata-mismatch',archive/info_path)
        need_path({k:v for k,v in info.items() if k.endswith('UsageDescription')}=={k:v for k,v in source_info.items() if k.endswith('UsageDescription')},'permission-purpose-source-mismatch',archive/info_path)
        if bundle==APP:
            need_path(properties.get('ApplicationPath')=='Applications/CelluloidMac.app' and all(properties.get(k)==info[k] for k in ('CFBundleIdentifier','CFBundleShortVersionString','CFBundleVersion')),'archive-application-properties-mismatch',archive/'Info.plist')
        else:
            need_path('CelluloidOwnedPhotosBoundaryLease' not in info,'boundary-test-info-key-present',archive/info_path)
            expected_extension=dict(source_info['NSExtension']);expected_extension['NSExtensionPrincipalClass']='CelluloidMacPhotosExtension.MacPhotoEditingController'
            need_path(info.get('NSExtension')==expected_extension,'photos-extension-contract-mismatch',archive/info_path)
        resources=bundle+'/Contents/Resources/'
        for locale in ('en','zh-Hans'):
            key=resources+locale+'.lproj/Localizable.strings';path=archive/key
            need_path(regular(key) and 0<path.stat().st_size<=65536,'localized-resource-missing-or-oversized',path)
            need_path(package.strings_dictionary(path.read_bytes())==package.strings_dictionary((root/('Platforms/Resources/'+locale+'.lproj/Localizable.strings')).read_bytes()),'localized-resource-source-mismatch',path)
        for name_,source in [('LICENSE.txt','LICENSE.txt'),('PrivacyPolicy.txt','Platforms/Resources/PrivacyPolicy.txt')]:
            key=resources+name_;need_path(regular(key) and (archive/key).read_bytes()==(root/source).read_bytes(),'notice-resource-source-mismatch',archive/key)
        entitlements=read_metadata(root/('Platforms/'+platform+'/'+name+'.entitlements'),deadline,clock)
        expected_entitlements={'com.apple.security.app-sandbox':True}
        if bundle==APP:expected_entitlements['com.apple.security.files.user-selected.read-write']=True
        need(entitlements==expected_entitlements,'source-entitlements-contract-mismatch')
        for row in security[executable]:
            for actual in (*row['linked_entitlements'],*row['signature_entitlements']):
                need_path(actual==entitlements,'product-entitlements-source-mismatch',archive/executable)
        dmeta=values[dsym+'/Contents/Info.plist']
        need_path(dmeta.get('CFBundleIdentifier')=='com.apple.xcode.dsym.'+identifier and dmeta.get('CFBundlePackageType')=='dSYM','dSYM-metadata-mismatch',archive/dsym/'Contents/Info.plist')
        versions={k:{'observed':dmeta.get(k),'comparison':'missing' if k not in dmeta else 'same' if dmeta[k]==info[k] else 'different'} for k in ('CFBundleVersion','CFBundleShortVersionString')}
        report['current_proof_path']=dwarf
        uuids=matching_uuid(run(['xcrun','dwarfdump','--uuid',str(archive/executable),str(archive/dwarf)],seconds=10,cap=8192,cleanup=10),archive/executable,archive/dwarf)
        symbols=run(['xcrun','nm','-u',str(archive/executable)],seconds=15,cap=256*1024).decode('utf-8','replace')
        candidates=sorted({line.strip() for line in symbols.splitlines() if re.search(r'UserDefaults|CFPreferences|(?:^|_)f?stat(?:64|at|fs)?(?:$|\s)|getattrlist|systemUptime|mach_absolute_time|volumeAvailableCapacity|activeInputModes',line)})
        product_proofs[bundle]={'required_reason_linked_symbol_candidates':candidates,'linked_symbol_scope':'Undefined imports are evidence for review, not standalone proof of runtime use or a reason declaration.', 'info':info,'source_entitlements':entitlements,'product_security_observation':security[executable],
            'dSYM_metadata':dmeta,'dSYM_version_observations':versions,'uuids':uuids,
            'effective_sandbox_qualified':False,'signing_qualified':False,
            'unsigned_entitlement_scope':'Source declaration checked; actual linked/signature XML recorded if present. Absence is explicit, not sandbox enforcement.'}
    # Each runnable product resolves Bundle.module from its own Resources root.
    # A same-named package elsewhere in the archive cannot satisfy that closure.
    package_proofs={}
    for package_name,target in [('CelluloidCore','CelluloidDomain'),('CelluloidRendering','CelluloidRendering')]:
        bundle_name=package_name+'_'+target+'.bundle'
        sources=root/'Packages'/package_name/'Sources'/target/'Resources'
        for product in (APP,EXT):
            base=product+'/Contents/Resources/'+bundle_name
            need_path(before['paths'].get(base,{}).get('type')=='directory','package-resource-bundle-missing',archive/base)
            prefix=base+'/Contents/Resources/' if regular(base+'/Contents/Info.plist') else base+'/'
            count=0
            for source in sources.rglob('*'):
                if not source.is_file():continue
                relative=source.relative_to(sources).as_posix();key=prefix+relative;path=archive/key
                need_path(regular(key),'package-resource-missing',path)
                if source.suffix=='.strings':same=package.strings_dictionary(path.read_bytes())==package.strings_dictionary(source.read_bytes())
                elif source.suffix=='.png':
                    # Xcode may optimize PNG bytes; validate PNG dimensions and retain both hashes.
                    raw=path.read_bytes();original=source.read_bytes();same=raw[:8]==original[:8]==b'\x89PNG\r\n\x1a\n' and raw[16:24]==original[16:24]
                else:same=path.read_bytes()==source.read_bytes()
                need_path(same,'package-resource-source-mismatch',path);count+=1
            package_proofs[base]={'owner_product':product,'verified_resources':count}
    icon_inputs=verify_icon_inputs(root)
    resources=APP+'/Contents/Resources/'
    for name in ('Assets.car','AppIcon.icns'):
        key=resources+name;need_path(regular(key) and (archive/key).stat().st_size>0,'required-compiled-resource-missing',archive/key)
    need_path(values[APP+'/Contents/Info.plist'].get('CFBundleIconFile') in ('AppIcon','AppIcon.icns'),'compiled-icon-identity-mismatch',archive/APP/'Contents/Info.plist')
    catalog=json.loads(run(['xcrun','assetutil','--info',str(archive/resources/'Assets.car')],seconds=30,cap=128*1024))
    entries=[row for row in catalog if isinstance(row,dict) and row.get('Name')=='AppIcon']
    dimensions={(r.get('PixelWidth'),r.get('PixelHeight'),r.get('Scale')) for r in entries if r.get('AssetType')=='Icon Image'}
    slots=json.loads((root/'Platforms/macOS/Assets.xcassets/AppIcon.appiconset/Contents.json').read_bytes())['images']
    expected_dimensions={(int(float(r['size'].split('x')[0])*int(r['scale'][0])),int(float(r['size'].split('x')[0])*int(r['scale'][0])),int(r['scale'][0])) for r in slots}
    need_path(expected_dimensions<=dimensions,'compiled-icon-renditions-missing',archive/resources/'Assets.car')
    privacy_paths=[k for k,v in before['paths'].items() if v['type']=='file' and k.endswith('.xcprivacy')]
    # The exact source fixture determines whether a manifest is currently required.
    need(not privacy_paths,'unexpected-privacy-manifest-outside-pinned-source')
    privacy={'manifest_paths':privacy_paths,'source_declares_mac_manifest':False,'privacy_policy_exact':True,'store_privacy_qualified':False}
    after=scan(archive,deadline,clock=clock,hash_files=False)
    need(before['entries']==after['entries'] and before['bytes']==after['bytes'] and
        {k:v['identity'] for k,v in before['paths'].items()}=={k:v['identity'] for k,v in after['paths'].items()},'archive-changed-during-proof')
    timely(deadline,clock);report.pop('current_proof_path',None)
    return {'metadata':metadata,'products':product_proofs,'binaries':binaries,'package_resources':package_proofs,
        'privacy':privacy,'icon_inputs':icon_inputs,'compiled_icon_renditions':entries,
        'archive_entries':before['entries'],'archive_bytes':before['bytes'],'elapsed_seconds':clock()-started,
        'observation':'Complete bounded catalogue, metadata and stable identity interval; unsigned only',
        'resource_policy':'Normal generated names accepted; unexpected executable products rejected'}


def json_value(value):
    if isinstance(value, datetime.datetime):
        return {'plist_date': value.isoformat()}
    if isinstance(value, bytes):
        return {'plist_data_hex': value.hex()}
    raise TypeError(type(value).__name__)


def report_bytes(report):
    raw = (json.dumps(report, sort_keys=True, default=json_value, allow_nan=False, separators=(',', ':')) + '\n').encode()
    if len(raw) > MAX_REPORT:
        # Keep the bounded catalogue/plist observations/source/clock on overflow.
        keep=('schema','scope','signing_qualified','store_qualified','older_os_qualified','ui_qualification_separate',
            'source_before','clock','archive_inventory','archive_metadata_diagnostics',
            'owned_output','binary_handoff','upload_qualified','archive_file_observation_scope','archive_file_observation_error','core_data_resource_observation')
        compact={k:report[k] for k in keep if k in report}
        compact.update(qualified=False,failure={'type':'Rejected','reason':'report-byte-limit','original_failure':report.get('failure')})
        raw=(json.dumps(compact,sort_keys=True,default=json_value,allow_nan=False,separators=(',',':'))+'\n').encode()
        need(len(raw)<=MAX_REPORT,'bounded-inventory-report-byte-limit')
    return raw


def execute(*, env=None, root=ROOT, clock=time.monotonic, runner=capture):
    env = os.environ if env is None else env
    began = clock(); receipts = []; phase = 'prepare'; phase_deadline = began + 180
    report = {'schema': 1, 'scope': 'Mac-universal-unsigned-archive-observation', 'qualified': False,
        'signing_qualified': False, 'store_qualified': False, 'older_os_qualified': False,
        'ui_qualification_separate': True, 'binary_handoff': False, 'commands': receipts,
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
        report['icon_source_provenance'] = verify_icon_inputs(root)
        report['toolchain'] = {
            'os': run(['sw_vers'], seconds=5, cap=4096).decode(),
            'xcode': run(['xcodebuild', '-version'], seconds=10, cap=4096).decode(),
            'sdks': run(['xcodebuild', '-showsdks'], seconds=15, cap=16384).decode()}
        need(report['toolchain']['xcode'].strip().splitlines() == ['Xcode 27.0', 'Build version 27A266a'], 'toolchain-mismatch')
        need('macosx27.0' in report['toolchain']['sdks'], 'sdk-mismatch')
        for optimize in ([], ['-O']):
            run([sys.executable, *optimize, '-m', 'unittest', 'discover', '-s', 'Scripts',
                 '-p', 'test_mac_unsigned_archive.py'], seconds=40, cap=65536)
        timely(began + PHASE_END['prepare'], clock)
        phase = 'archive'; phase_deadline = min(began + PHASE_END[phase], clock() + 620)
        output=run(ARCHIVE_COMMAND, seconds=600, cap=512 * 1024, cleanup=10)
        report['archive_success_marker_observed']=b'** ARCHIVE SUCCEEDED **' in output
        if re.search(rb'(?im)(?:^|[ :])(?:fatal )?error:',output+b'\n'+receipts[-1]['stderr'].encode()):
            # Only after timely zero return and confirmed host-group completion.
            # Preserve bounded pure-file evidence; do not run any native proof.
            report['archive_file_observation_scope']='after-known-zero-exit-with-error; pure files only'
            try:
                observe_archive_files(root/ARCHIVE,min(began+PHASE_END['proof'],clock()+150),root=root,clock=clock,report=report)
            except Exception as diagnostic_error:
                report['archive_file_observation_error']={'type':type(diagnostic_error).__name__,'reason':str(diagnostic_error)[:4096]}
            raise Rejected('archive-reported-error')
        phase = 'proof'; phase_deadline = min(began + PHASE_END[phase], clock() + 150)
        report['proof'] = verify_archive(root / ARCHIVE, run, phase_deadline, root=root, clock=clock, report=report)
        phase = 'final_source_pack'; phase_deadline = min(began + PHASE_END[phase], clock() + 30)
        report['clock']['report_ready_deadline'] = phase_deadline
        report['source_after'] = source_identity(env, run, root)
        need(report['source_after'] == report['source_before'], 'source-changed')
        timely(phase_deadline, clock)
        report['qualified'] = True
    except (Exception, KeyboardInterrupt) as error:
        report['clock']['report_ready_deadline'] = min(report['clock']['report_ready_deadline'], clock() + 30)
        report['failure'] = {'phase': phase, 'type': type(error).__name__,
                             'reason': str(error)[:4096], 'offending_path':report.get('offending_path') or report.get('current_proof_path') or report.get('archive_inventory',{}).get('last_path')}
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
