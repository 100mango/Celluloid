#!/usr/bin/env python3
"""Small TV archive adjunct to the unchanged product Release package checker.

The original checker remains the authority for the 15 previously proven TV
package checks. This adjunct observes actual xcarchive placement, final resource
membership, and app/dSYM UUID correspondence. No simulator or Apple account.
"""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import stat
import sys
import time

SOURCE = '13e9a1ed63c6e7744803419f27e429a759df1209'
ARCHIVE = '.build/CelluloidTV.xcarchive'
APP = 'Products/Applications/CelluloidTV.app'
DSYM = 'dSYMs/CelluloidTV.app.dSYM/Contents/Resources/DWARF/CelluloidTV'
CHECKER_SHA256 = '87bc44453808b6eee2c6cc1b36d911cce6a8be994c50858639e541219c663ff0'
EXPECTED_CHECKS = {'bundle_identifier','executable_name','device_sdk_not_simulator','minimum_os_metadata',
    'version_and_build','localized_bundles','license_packaged','no_test_bundles','debug_seams_absent',
    'native_arm_device_slice','linked_minimum_matches','brand_icon_packaged','compiled_icon_renditions',
    'privacy_manifest_exact','permission_prompts_localized'}
PREFIXES = ('Platforms/tvOS','Platforms/Resources','Packages/CelluloidCore','Packages/CelluloidRendering')
EXTRA = ('LICENSE.txt','CelluloidNative.xcodeproj/project.pbxproj',
    'CelluloidNative.xcodeproj/xcshareddata/xcschemes/CelluloidTV.xcscheme',
    'Scripts/materialize_native_icons.swift','Scripts/verify_native_icon_inputs.py',
    'Scripts/verify_native_release.py','Celluloid/Assets.xcassets/AppIcon.appiconset/Icon-Marketing.png')


def need(value, reason):
    if not value: raise ValueError(reason)


def sha(raw): return hashlib.sha256(raw).hexdigest()


def read(path, cap=524288):
    path=Path(path)
    need(not path.is_symlink() and all(not parent.is_symlink() for parent in path.parents), 'symlink-input')
    before=path.stat()
    need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and 0<before.st_size<=cap, 'invalid-input-size-or-kind')
    with path.open('rb') as stream: raw=stream.read(cap+1)
    after=path.stat()
    need((before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns)
         and len(raw)==before.st_size,'input-changed')
    return raw


def source_graph(root):
    root=Path(root);paths=set(EXTRA)
    for prefix in PREFIXES:
        for path in (root/prefix).rglob('*'):
            if path.is_file() and not any(part in ('__pycache__','.build') for part in path.parts) and not path.name.startswith('Generated'):
                paths.add(path.relative_to(root).as_posix())
    need(len(paths)<=250,'source-inventory-cap')
    return {path:sha(read(root/path,16777216)) for path in sorted(paths)}


def source_strings(raw):
    text=raw.decode('utf-8-sig');token=re.compile(r'\s+|/\*.*?\*/|//[^\n]*|"(?:[^"\\]|\\.)*"|[=;]',re.S)
    parts=[];offset=0
    for match in token.finditer(text):
        need(match.start()==offset,'unknown-strings-syntax');offset=match.end();value=match[0]
        if value.isspace() or value.startswith(('/*','//')): continue
        parts.append(value)
    need(offset==len(text) and len(parts)%4==0,'incomplete-strings')
    result={}
    for index in range(0,len(parts),4):
        key,equal,value,semi=parts[index:index+4];need(equal=='=' and semi==';','strings-record')
        key,value=json.loads(key),json.loads(value);need(type(key)is str and type(value)is str and key not in result,'strings-duplicate')
        result[key]=value
    return result


def strings(raw):
    if raw.startswith((b'bplist00',b'<?xml',b'<plist')): return plistlib.loads(raw)
    if raw.startswith((b'\xff\xfe',b'\xfe\xff')):raw=raw.decode('utf16').encode('utf8')
    return source_strings(raw)


def uuids(raw):
    result={}
    for line in raw.decode().strip().splitlines():
        match=re.fullmatch(r'UUID: ([0-9A-Fa-f-]{36}) \(([^)]+)\) .+',line)
        need(match is not None and match[2] not in result,'invalid-uuid-observation')
        result[match[2]]=match[1].upper()
    need(set(result)=={'arm64'},'unexpected-uuid-architecture')
    return result


def archive_metadata(archive):
    value=plistlib.loads(read(archive/'Info.plist'));app=value.get('ApplicationProperties',{})
    need(value.get('ArchiveVersion')==2 and app.get('ApplicationPath')=='Applications/CelluloidTV.app','not-tv-application-xcarchive')
    need(app.get('CFBundleIdentifier')=='Mango.Celluloid' and app.get('CFBundleShortVersionString')=='1.1.1'
         and app.get('CFBundleVersion')=='3','archive-version-or-identity')
    need(sorted(p.name for p in (archive/'Products/Applications').iterdir())==['CelluloidTV.app'],'unexpected-archive-application')
    need(sorted(p.name for p in (archive/'dSYMs').iterdir())==['CelluloidTV.app.dSYM'],'unexpected-dsym-set')
    need(not any(archive.rglob('*.xctest')) and not any(archive.rglob('embedded.mobileprovision')),'tests-or-provisioning-in-archive')
    return value


def resource_inventory(root,app,deadline):
    mappings={
        'CelluloidCore_CelluloidDomain.bundle':'Packages/CelluloidCore/Sources/CelluloidDomain/Resources',
        'CelluloidRendering_CelluloidRendering.bundle':'Packages/CelluloidRendering/Sources/CelluloidRendering/Resources'}
    need({p.name for p in app.glob('*.bundle')}==set(mappings),'resource-bundle-membership')
    proof={}
    for relative,source in [('LICENSE.txt','LICENSE.txt'),('PrivacyPolicy.txt','Platforms/Resources/PrivacyPolicy.txt'),('PrivacyInfo.xcprivacy','Platforms/tvOS/PrivacyInfo.xcprivacy')]:
        built=read(app/relative);expected=read(root/source)
        need((plistlib.loads(built)==plistlib.loads(expected)) if relative.endswith('.xcprivacy') else built==expected,'root-resource-'+relative)
        proof[relative]={'sha256':sha(built),'source_equal':True}
    for lang in ('en','zh-Hans'):
        for name,source in [('Localizable.strings','Platforms/Resources'),('InfoPlist.strings','Platforms/tvOS')]:
            relative=lang+'.lproj/'+name;built=read(app/relative)
            need(strings(built)==source_strings(read(root/source/relative)),'localized-resource-'+relative)
            proof[relative]={'sha256':sha(built),'keys':len(strings(built)),'source_semantics_equal':True}
    for bundle,source in mappings.items():
        expected={p.relative_to(root/source).as_posix():p for p in (root/source).rglob('*') if p.is_file()}
        actual={p.relative_to(app/bundle).as_posix() for p in (app/bundle).rglob('*') if p.is_file()}
        # Xcode may additionally generate Info.plist. Every actual source resource
        # must be present; no unexpected runtime resource may replace membership.
        need(actual-set(expected)<={'Info.plist'} and set(expected)<=actual,'package-resource-membership-'+bundle)
        for relative,path in sorted(expected.items()):
            need(time.monotonic()<deadline,'resource-deadline')
            built=read(app/bundle/relative,16777216);original=read(path,16777216)
            row={'sha256':sha(built),'bytes':len(built)}
            if relative.endswith('.strings'):
                need(strings(built)==source_strings(original),'package-localization-'+relative);row['source_semantics_equal']=True
            elif relative.endswith('.png'):
                # Asset pipelines can recompress PNG bytes; this is package
                # membership and dimensions only, never a new pixel oracle.
                need(built[:8]==original[:8]==b'\x89PNG\r\n\x1a\n' and built[16:24]==original[16:24],'package-png-dimensions-'+relative)
                row['source_dimensions_equal']=True
            else:
                need(built==original,'package-resource-bytes-'+relative);row['source_equal']=True
            proof[bundle+'/'+relative]=row
    return proof


def verify_package(root,deadline,*,commands):
    root=Path(root);archive=root/ARCHIVE;app=archive/APP
    checker=root/'Scripts/verify_native_release.py'
    need(sha(read(checker))==CHECKER_SHA256,'proven-checker-drift')
    metadata=archive_metadata(archive)
    # The reused checker writes its existing 15-check report. Its product SHA is
    # fixed explicitly while the enclosing control/run identity stays separate.
    before=os.environ.get('GITHUB_SHA');os.environ['GITHUB_SHA']=SOURCE
    try:
        commands.run([sys.executable,'-B','-S',str(checker),'tv',str(app)],deadline=deadline,seconds=60,cap=65536)
    finally:
        if before is None:os.environ.pop('GITHUB_SHA',None)
        else:os.environ['GITHUB_SHA']=before
    report=json.loads(read(Path(os.environ['RUNNER_TEMP'])/'tv-release-packaging.json'))
    need(report.get('source_sha')==SOURCE and report.get('platform')=='tv' and report.get('product')==str(app),'package-report-identity')
    need(set(report.get('checks',{}))==EXPECTED_CHECKS and all(v is True for v in report['checks'].values()),'original-package-checks')
    need(report.get('architectures')==['arm64'],'tv-device-architecture')
    executable=app/'CelluloidTV';symbols=archive/DSYM
    symbol_bytes=read(symbols,134217728);need(symbol_bytes[:4]==b'\xcf\xfa\xed\xfe','dsym-mach-o')
    binary_uuid=uuids(commands.run(['xcrun','dwarfdump','--uuid',str(executable)],deadline=deadline,seconds=20))
    dsym_uuid=uuids(commands.run(['xcrun','dwarfdump','--uuid',str(symbols)],deadline=deadline,seconds=20))
    need(binary_uuid==dsym_uuid,'dsym-uuid-mismatch')
    resources=resource_inventory(root,app,deadline)
    need(sha(read(executable,134217728))==report['binary_sha256'],'binary-changed-after-check')
    need(archive_metadata(archive)==metadata and time.monotonic()<deadline,'archive-changed-or-proof-late')
    return {'unsigned_package_verified':True,'all_processes_finalized':not commands.blocked,
        'release_acceptance':False,'signing_qualified':False,'actual_xcarchive':True,
        'build_action':'archive','archive_path':ARCHIVE,'inherited_checker_report':report,
        'archive_application':metadata['ApplicationProperties'],'binary_uuid_by_architecture':binary_uuid,
        'dsym_uuid_by_architecture':dsym_uuid,'dsym_sha256':sha(symbol_bytes),
        'resource_inventory':resources,'resource_scope':'Membership, metadata, localization values and PNG dimensions; no new pixel/runtime oracle.'}
