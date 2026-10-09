#!/usr/bin/env python3
"""Small Mac archive adjunct to the unchanged final native package checker.

Observe app, embedded Photos extension, resources and dSYM correspondence from
one real Release xcarchive. Declared entitlements are not sandbox execution.
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
ARCHIVE = '.build/CelluloidMac.xcarchive'
APP = 'Products/Applications/CelluloidMac.app'
EXTENSION = 'Contents/PlugIns/CelluloidMacPhotosExtension.appex'
CHECKER_SHA256 = '87bc44453808b6eee2c6cc1b36d911cce6a8be994c50858639e541219c663ff0'
EXPECTED_CHECKS = {'bundle_identifier','executable_name','device_sdk_not_simulator','minimum_os_metadata',
    'version_and_build','localized_bundles','license_packaged','no_test_bundles','debug_seams_absent',
    'native_arm_device_slice','linked_minimum_matches','brand_icon_packaged','compiled_icon_renditions',
    'native_text_hooks_absent_from_extension'}
PREFIXES = ('Platforms/macOS','Platforms/macOSExtension','Platforms/Shared','Platforms/Resources',
    'Packages/CelluloidCore','Packages/CelluloidRendering')
EXTRA = ('LICENSE.txt','CelluloidNative.xcodeproj/project.pbxproj',
    'CelluloidNative.xcodeproj/xcshareddata/xcschemes/CelluloidMac.xcscheme',
    'Scripts/verify_native_release.py','Scripts/native_text_release_guard.py','CelluloidPhotoExtension/PhotosOutputWrite.swift')
BUNDLES = {'CelluloidCore_CelluloidDomain.bundle':'Packages/CelluloidCore/Sources/CelluloidDomain/Resources',
    'CelluloidRendering_CelluloidRendering.bundle':'Packages/CelluloidRendering/Sources/CelluloidRendering/Resources'}
PRODUCTS = {'app':('CelluloidMac','CelluloidMac.app.dSYM'),
    'extension':('CelluloidMacPhotosExtension','CelluloidMacPhotosExtension.appex.dSYM')}


def need(value, reason):
    if not value: raise ValueError(reason)


def sha(raw): return hashlib.sha256(raw).hexdigest()


def read(path, cap=524288):
    # Identical strict reader to the proven TV adjunct. Callers and fixtures
    # canonicalize only their trusted root, never a package member or alias.
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
    need(len(paths)<=300,'source-inventory-cap')
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


def architectures(values):
    need(type(values)is list and len(values)==len(set(values)) and 'arm64' in values
         and set(values)<={'arm64','x86_64'},'unexpected-mac-architectures')
    return set(values)


def uuids(raw):
    result={}
    for line in raw.decode().strip().splitlines():
        match=re.fullmatch(r'UUID: ([0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}) \(([^)]+)\) .+',line)
        need(match is not None and match[2] not in result,'invalid-uuid-observation')
        result[match[2]]=match[1].upper()
    architectures(list(result))
    return result


def archive_metadata(archive):
    value=plistlib.loads(read(archive/'Info.plist'));app=value.get('ApplicationProperties',{})
    need(value.get('ArchiveVersion')==2 and app.get('ApplicationPath')=='Applications/CelluloidMac.app','not-mac-application-xcarchive')
    need(app.get('CFBundleIdentifier')=='Mango.Celluloid' and app.get('CFBundleShortVersionString')=='1.1.1'
         and app.get('CFBundleVersion')=='3','archive-version-or-identity')
    need(sorted(p.name for p in (archive/'Products/Applications').iterdir())==['CelluloidMac.app'],'unexpected-archive-application')
    need(sorted(p.name for p in (archive/'dSYMs').iterdir())==sorted(v[1] for v in PRODUCTS.values()),'unexpected-dsym-set')
    need(not any(archive.rglob('*.xctest')) and not any(archive.rglob('*.debug.dylib'))
         and not any(archive.rglob('embedded.mobileprovision')) and not any(archive.rglob('embedded.provisionprofile')),'tests-debug-or-provisioning-in-archive')
    actual=archive/APP
    need(sorted(p.name for p in (actual/'Contents/PlugIns').iterdir())==['CelluloidMacPhotosExtension.appex'],'unexpected-embedded-extension-set')
    need(sorted(p.relative_to(archive).as_posix() for p in archive.rglob('*.appex'))==[APP+'/'+EXTENSION],'extension-outside-fixed-embed-path')
    return value


def product_metadata(app,extension):
    output={}
    for label,bundle in [('app',app),('extension',extension)]:
        value=plistlib.loads(read(bundle/'Contents/Info.plist'))
        expected={'CFBundleIdentifier':'Mango.Celluloid'+('.CelluloidPhotoExtension' if label=='extension' else ''),
            'CFBundleExecutable':PRODUCTS[label][0],'CFBundlePackageType':'XPC!' if label=='extension' else 'APPL',
            'CFBundleShortVersionString':'1.1.1','CFBundleVersion':'3','DTPlatformName':'macosx','LSMinimumSystemVersion':'13.0'}
        need(all(value.get(k)==v for k,v in expected.items()) and re.fullmatch(r'macosx[0-9]+(?:\.[0-9]+)*',value.get('DTSDKName','')) is not None,'bundle-identity-version-sdk-'+label)
        need(value.get('CFBundleLocalizations')==['en','zh-Hans'],'bundle-localizations-'+label)
        if label=='extension':
            need(value.get('NSExtension')=={'NSExtensionPointIdentifier':'com.apple.photo-editing',
                'NSExtensionPrincipalClass':'CelluloidMacPhotosExtension.MacPhotoEditingController',
                'NSExtensionAttributes':{'PHSupportedMediaTypes':['Image']}},'photos-extension-contract')
        output[label]={key:value.get(key) for key in [*expected,'DTSDKName','DTXcode','DTXcodeBuild','CFBundleLocalizations','NSExtension']}
    return output


def resource_inventory(root,app,deadline):
    resources=app/'Contents/Resources'
    need({p.name for p in resources.glob('*.bundle')}==set(BUNDLES),'resource-bundle-membership')
    proof={}
    for relative,source in [('LICENSE.txt','LICENSE.txt'),('PrivacyPolicy.txt','Platforms/Resources/PrivacyPolicy.txt')]:
        built=read(resources/relative);need(built==read(root/source),'root-resource-'+relative)
        proof[relative]={'sha256':sha(built),'source_equal':True}
    for lang in ('en','zh-Hans'):
        relative=lang+'.lproj/Localizable.strings';built=read(resources/relative)
        need(strings(built)==source_strings(read(root/'Platforms/Resources'/relative)),'localized-resource-'+relative)
        proof[relative]={'sha256':sha(built),'keys':len(strings(built)),'source_semantics_equal':True}
    for bundle,source in BUNDLES.items():
        builtroot=resources/bundle/'Contents/Resources'
        expected={p.relative_to(root/source).as_posix():p for p in (root/source).rglob('*') if p.is_file()}
        actual={p.relative_to(builtroot).as_posix() for p in builtroot.rglob('*') if p.is_file()}
        need(set(expected)==actual,'package-resource-membership-'+bundle)
        info=plistlib.loads(read(resources/bundle/'Contents/Info.plist'))
        need(info.get('CFBundlePackageType')=='BNDL','resource-bundle-type')
        for relative,path in sorted(expected.items()):
            need(time.monotonic()<deadline,'resource-deadline')
            built=read(builtroot/relative,16777216);original=read(path,16777216)
            row={'sha256':sha(built),'bytes':len(built)}
            if relative.endswith('.strings'):
                need(strings(built)==source_strings(original),'package-localization-'+relative);row['source_semantics_equal']=True
            elif relative.endswith('.png'):
                need(built[:8]==original[:8]==b'\x89PNG\r\n\x1a\n' and built[16:24]==original[16:24],'package-png-dimensions-'+relative)
                row['source_dimensions_equal']=True
            else:
                need(built==original,'package-resource-bytes-'+relative);row['source_equal']=True
            proof[bundle+'/Contents/Resources/'+relative]=row
    return proof


def linked_slice(raw):
    text=raw.decode();platforms=re.findall(r'\bplatform\s+(\S+)',text);minima=re.findall(r'\bminos\s+(\S+)',text)
    need(platforms==['MACOS'] and len(minima)==1 and minima[0] in ('13.0','13.0.0'),'mac-linked-platform-or-floor')
    return {'platform':'MACOS','minimum_os':minima[0],'sha256':sha(raw)}


def verify_package(root,deadline,*,commands):
    root=Path(root);archive=root/ARCHIVE;app=archive/APP;extension=app/EXTENSION
    checker=root/'Scripts/verify_native_release.py'
    need(sha(read(checker))==CHECKER_SHA256,'proven-checker-drift')
    metadata=archive_metadata(archive);infos=product_metadata(app,extension)
    before=os.environ.get('GITHUB_SHA');os.environ['GITHUB_SHA']=SOURCE
    try:
        commands.run([sys.executable,'-B','-S',str(checker),'mac',str(app)],deadline=deadline,seconds=60,cap=65536)
    finally:
        if before is None:os.environ.pop('GITHUB_SHA',None)
        else:os.environ['GITHUB_SHA']=before
    report=json.loads(read(Path(os.environ['RUNNER_TEMP']).resolve(strict=True)/'mac-release-packaging.json'))
    need(report.get('source_sha')==SOURCE and report.get('platform')=='mac' and report.get('product')==str(app),'package-report-identity')
    need(set(report.get('checks',{}))==EXPECTED_CHECKS and all(v is True for v in report['checks'].values()),'original-package-checks')
    app_archs=architectures(report.get('architectures'));binary_proof={};resources={}
    for label,bundle in [('app',app),('extension',extension)]:
        name,dsym=PRODUCTS[label];executable=bundle/'Contents/MacOS'/name
        binary=read(executable,134217728);symbols=archive/'dSYMs'/dsym/'Contents/Resources/DWARF'/name
        symbol_bytes=read(symbols,134217728)
        magics=(b'\xcf\xfa\xed\xfe',b'\xfe\xed\xfa\xcf',b'\xca\xfe\xba\xbe',b'\xbe\xba\xfe\xca',b'\xca\xfe\xba\xbf',b'\xbf\xba\xfe\xca')
        need(binary[:4] in magics and symbol_bytes[:4] in magics,'binary-or-dsym-not-mach-o')
        observed=commands.run(['xcrun','lipo','-archs',str(executable)],deadline=deadline,seconds=15).decode().strip().split()
        need(architectures(observed)==app_archs,'app-extension-architecture-mismatch')
        binary_uuid=uuids(commands.run(['xcrun','dwarfdump','--uuid',str(executable)],deadline=deadline,seconds=20))
        dsym_uuid=uuids(commands.run(['xcrun','dwarfdump','--uuid',str(symbols)],deadline=deadline,seconds=20))
        need(set(binary_uuid)==app_archs and binary_uuid==dsym_uuid,'dsym-uuid-mismatch')
        slices={}
        for arch in sorted(app_archs):
            slices[arch]=linked_slice(commands.run(['xcrun','vtool','-arch',arch,'-show-build',str(executable)],deadline=deadline,seconds=15))
        loads=commands.run(['xcrun','otool','-l',str(executable)],deadline=deadline,seconds=15,cap=65536)
        # arm64 linkers may emit an ad hoc code-signature load command even with
        # CODE_SIGNING_ALLOWED=NO. Record it; never infer a trusted signature.
        binary_proof[label]={'sha256':sha(binary),'architectures':sorted(app_archs),'binary_uuid_by_architecture':binary_uuid,
            'dsym_uuid_by_architecture':dsym_uuid,'dsym_sha256':sha(symbol_bytes),'linked_slices':slices,
            'code_signature_load_command_present':b'LC_CODE_SIGNATURE' in loads,'load_commands_sha256':sha(loads)}
        resources[label]=resource_inventory(root,bundle,deadline)
        need(sha(read(executable,134217728))==sha(binary) and sha(read(symbols,134217728))==sha(symbol_bytes),'binary-or-symbol-changed')
    need(binary_proof['app']['sha256']==report['binary_sha256'],'binary-changed-after-check')
    need(archive_metadata(archive)==metadata and product_metadata(app,extension)==infos and time.monotonic()<deadline,'archive-changed-or-proof-late')
    entitlements={relative:plistlib.loads(read(root/relative)) for relative in ('Platforms/macOS/CelluloidMac.entitlements','Platforms/macOSExtension/CelluloidMacPhotosExtension.entitlements')}
    return {'unsigned_package_verified':True,'all_processes_finalized':not commands.blocked,
        'release_acceptance':False,'signing_qualified':False,'mac_photos_host_qualified':False,
        'mac_layered_guard_qualified':False,'signed_sandbox_qualified':False,'actual_xcarchive':True,
        'build_action':'archive','archive_path':ARCHIVE,'inherited_checker_report':report,
        'archive_application':metadata['ApplicationProperties'],'bundle_metadata':infos,'binaries':binary_proof,
        'resource_inventory':resources,'declared_source_entitlements':entitlements,
        'resource_scope':'App and embedded extension membership, metadata, localization values and PNG dimensions; no new pixel/runtime oracle.',
        'signature_scope':'Unsigned archive invocation; code-signature load command presence is observed only. No signing, entitlement enforcement, Photos-host, layered guard or sandbox execution qualification.'}
