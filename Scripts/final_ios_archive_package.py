#!/usr/bin/env python3
"""Cell-only final unsigned archive inspection. Native results are diagnostic, not release acceptance.

Source admission and the archive process belong to the separate driver. This
module launches only the same three bounded public Mach-O probes. No historical
row or artifact proof, monkeypatch, product import, or third-party dependency.
"""
from pathlib import Path
import hashlib
import json
import math
import os
import plistlib
import re
import selectors
import signal
import stat
import struct
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET

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
DSYMS = {path: 'dSYMs/' + Path(path).name + '.dSYM/Contents/Resources/DWARF/' + data[0]
         for path, data in BUNDLES.items()}
DSYM_ROOTS = {'/'.join(path.split('/')[:2]) for path in DSYMS.values()}
INSTALL_NAMES = {KIT: '@rpath/CelluloidKit.framework/CelluloidKit',
                 SNAPKIT: '@rpath/' + SNAPKIT_NAME + '.framework/' + SNAPKIT_NAME}
BUNDLED_DEPENDENCIES = {APP: {INSTALL_NAMES[KIT], INSTALL_NAMES[SNAPKIT]},
                      KIT: {INSTALL_NAMES[SNAPKIT]}, EXT: {INSTALL_NAMES[KIT]}, SNAPKIT: set()}
SNAPKIT_RESOURCES = {owner + '/SnapKit_SnapKit.bundle' for owner in (APP, EXT, SNAPKIT)}
DOMAIN_NAME = 'CelluloidCore_CelluloidDomain.bundle'
DOMAIN_RESOURCES = {owner + '/' + DOMAIN_NAME for owner in (APP, KIT, EXT)}
RESOURCE_BUNDLES = SNAPKIT_RESOURCES | DOMAIN_RESOURCES
DOMAIN_SOURCE = 'Packages/CelluloidCore/Sources/CelluloidDomain/Resources'
SOURCE_RESOURCES = {
    'Celluloid': {'Celluloid/Assets.xcassets', 'Celluloid/collage.json',
                 'Celluloid/Base.lproj/LaunchScreen.storyboard', 'Celluloid/zh-Hans.lproj/LaunchScreen.strings',
                 'Celluloid/en.lproj/Localizable.strings', 'Celluloid/zh-Hans.lproj/Localizable.strings',
                 'Celluloid/zh-Hans.lproj/InfoPlist.strings'},
    'CelluloidKit': {'CelluloidKit/CelluloidKit.xcassets', 'CelluloidKit/ThirdPartyNotices/SnapKit-LICENSE.txt',
                    'CelluloidKit/bubble.json', 'CelluloidKit/Constant/en.lproj/Localizable.strings',
                    'CelluloidKit/Constant/zh-Hans.lproj/Localizable.strings'},
    'CelluloidPhotoExtension': {'CelluloidPhotoExtension/Base.lproj/MainInterface.storyboard',
                              'CelluloidPhotoExtension/zh-Hans.lproj/MainInterface.strings'},
}
PRIVACY = {'NSPrivacyTracking': False, 'NSPrivacyAccessedAPITypes': [],
           'NSPrivacyCollectedDataTypes': [], 'NSPrivacyTrackingDomains': []}
NOTICE_HASH = '7c0d21cf5314759fd35a22e42a52099d9cad2570db55a78e4eda26c82493b96b'
SNAPKIT_REVISION = '2842e6e84e82eb9a8dac0100ca90d9444b0307f4'
MAX_ENTRIES, MAX_FILE, MAX_BYTES, MAX_DEPTH = 2048, 256_000_000, 1_000_000_000, 12
METADATA_CAP = 100_000
DEBUG_MARKERS = (b'CELLULOID_PHONE_LAYOUT_FIXTURE', b'WatchProcessingLargeTextUI',
                 b'CELLULOID_PHONE_OUTPUT_PROOF', b'PhoneOutputProof', b'companion.synthetic-seed',
                 b'CELLULOID_EXPORT_FULL_CANVAS_CONTROL', b'CELLULOID_EXPORT_WARMING_ONLY_CONTROL',
                 b'--photos-denied', b'--photos-limited-empty', b'--ui-diagnostics',
                 b'outputWriterPreparedForTesting', b'--picker-entry-observation',
                 b'CELLULOID_PICKER_TRACE_RUN', b'--picker-seeded-identity', b'PICKER_APP_TRACE')
MACHO_MAGICS = {b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf',
                b'\xfe\xed\xfa\xce', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca',
                b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca'}

# Explicit copies from Scripts/original_ios_archive.py; source SHA256 fad791573cbfd5fd8ba523448d9346e3ddb09afe611e480a9e56b1e5cbc88f57.
def need(value, message):
    if not value:
        raise ValueError(message)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()

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

def unchanged(archive, snapshots, deadline):
    for relative, expected in snapshots.items():
        check_deadline(deadline)
        path = Path(archive) / relative
        parent = directory_fd(path.parent)
        try:
            need(snapshot(os.stat(path.name, dir_fd=parent, follow_symlinks=False)) == expected, 'Archive changed after inventory/observation')
        finally:
            os.close(parent)

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
        except BaseException as error:
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

# Explicit copies from Scripts/mac_owned_crash.py; source SHA256 96e0c607e574f97611041338a76e0757808ae6171ed6658dd5d9f418c0aacc77.
def number(value):return (type(value) is int and abs(value)<=2**53) or (type(value) is float and math.isfinite(value))

def directory_fd(path):
    path=Path(path).absolute()
    need(all(part not in {'.','..'} for part in path.parts[1:]),'Unsafe directory component')
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            try:child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            except OSError as error:raise ValueError('Symlink or unavailable owned directory') from error
            os.close(fd);fd=child
        return fd
    except BaseException:
        os.close(fd);raise

def bounded_optional_process(command,command_deadline,cleanup_deadline,cap=8192,*,stop_on_signal_error=False):
    """One owned session; finite reads and absolute deadlines, including pipe EOF.

    Do not poll/reap the leader while a descendant can retain the pipe. Its PID
    stays reserved until group cleanup, so a signal cannot target a reused PID.
    No change is made to the mandatory host command or shared run_bounded helper.
    """
    need(number(command_deadline) and number(cleanup_deadline) and time.monotonic()<command_deadline<cleanup_deadline,'Invalid/expired optional process deadlines')
    need(type(cap) is int and 0<cap<=8192,'Invalid optional output cap')
    need(type(stop_on_signal_error) is bool,'Invalid signal cleanup policy')
    need(signal.getsignal(signal.SIGCHLD)==signal.SIG_DFL,'Unknown child-reaping policy')
    started=time.monotonic();data=bytearray();eof=False;reaped=False;timed_out=False;overflow=False;cleanup_error=None
    process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True,bufsize=0)
    selector=None;pipe=process.stdout
    class SignalCleanupStopped(Exception):pass
    def drain(until):
        nonlocal eof,overflow
        while not eof and not overflow and time.monotonic()<until:
            if len(data)>=cap:overflow=True;break
            events=selector.select(max(0,min(0.1,until-time.monotonic())))
            for _,_ in events:
                if time.monotonic()>=until:break
                try:part=os.read(pipe.fileno(),min(4096,cap-len(data)))
                except BlockingIOError:continue
                if not part:eof=True;break
                data.extend(part)
    def signal_group(sig):
        nonlocal cleanup_error
        if reaped:return # Never signal after releasing the leader's PID.
        try:os.killpg(process.pid,sig)
        except ProcessLookupError:pass
        except OSError as error:
            cleanup_error=type(error).__name__
            if stop_on_signal_error:raise SignalCleanupStopped() from error
    try:
        selector=selectors.DefaultSelector()
        os.set_blocking(pipe.fileno(),False);selector.register(pipe,selectors.EVENT_READ)
        drain(command_deadline)
        if eof and not overflow:
            try:process.wait(timeout=max(0,command_deadline-time.monotonic()));reaped=True
            except subprocess.TimeoutExpired:timed_out=True
        else:timed_out=not overflow
        if not reaped:
            signal_group(signal.SIGTERM)
            term_deadline=min(cleanup_deadline,time.monotonic()+1)
            if not overflow:drain(term_deadline)
            # A completed leader may leave an ignoring descendant with the pipe.
            # Signal the same owned session before reaping that leader.
            signal_group(signal.SIGKILL)
            if not overflow:drain(cleanup_deadline)
            try:process.wait(timeout=max(0,cleanup_deadline-time.monotonic()));reaped=True
            except subprocess.TimeoutExpired:cleanup_error='direct child unreaped at absolute deadline'
    except SignalCleanupStopped:
        pass # Fixed staged metadata reads never switch signals after denial.
    except (OSError,ValueError) as error:
        cleanup_error=type(error).__name__
        try:signal_group(signal.SIGKILL)
        except SignalCleanupStopped:pass
        else:
            try:process.wait(timeout=max(0,cleanup_deadline-time.monotonic()));reaped=True
            except subprocess.TimeoutExpired:pass
    finally:
        if selector is not None:selector.close()
        pipe.close()
    finished=time.monotonic()
    if finished>command_deadline and not overflow:timed_out=True
    if finished>cleanup_deadline:cleanup_error='completion observed after absolute cleanup deadline'
    return {'return_code':process.returncode,'output':bytes(data),'bytes_read':len(data),'pipe_eof':eof,
        'child_reaped':reaped,'timed_out':timed_out,'overflow':overflow,'cleanup_error':cleanup_error,
        'finalized':eof and reaped and cleanup_error is None,'elapsed_seconds':finished-started,
        'command_deadline_monotonic':command_deadline,'cleanup_deadline_monotonic':cleanup_deadline}


def source_strings(raw):
    """The checked source uses quoted UTF-8 strings; comments are tokenized, not stripped inside values."""
    need(type(raw) is bytes and len(raw) <= METADATA_CAP, 'Source strings byte cap')
    text = raw.decode('utf-8-sig')
    token = re.compile(r'\s+|/\*.*?\*/|//[^\n]*|"(?:[^"\\]|\\.)*"|[=;]', re.S)
    parts, offset = [], 0
    for match in token.finditer(text):
        need(match.start() == offset, 'Unknown source strings syntax')
        offset = match.end(); value = match[0]
        if value.isspace() or value.startswith(('/*', '//')): continue
        parts.append(value)
    need(offset == len(text) and len(parts) % 4 == 0, 'Incomplete source strings')
    result = {}
    for index in range(0, len(parts), 4):
        key, equal, value, semi = parts[index:index + 4]
        need(equal == '=' and semi == ';', 'Malformed source strings record')
        key, value = json.loads(key), json.loads(value)
        need(type(key) is str and type(value) is str and key not in result, 'Duplicate/invalid source string')
        result[key] = value
    return result


def strings_plist(raw):
    # Xcode can preserve strings text or compile it to binary/XML plist.
    if raw.startswith((b'bplist00', b'<?xml', b'<plist')):
        result = plist(raw)
    elif raw.startswith((b'\xff\xfe', b'\xfe\xff')):
        result = source_strings(raw.decode('utf16').encode('utf8'))
    else:
        result = source_strings(raw)
    need(all(type(k) is str and type(v) is str for k, v in result.items()), 'Non-string localized resource')
    return result


def project_objects(raw):
    """Parse the actual deterministic quoted OpenStep project, without executing its generator."""
    need(type(raw) is bytes and len(raw) <= 500_000, 'Project byte cap')
    source = raw.decode('utf8')
    need(source.startswith('// !$*UTF8*$!\n'), 'Unexpected project header')
    source = source.split('\n', 1)[1]
    tokens, offset = [], 0
    token = re.compile(r'\s*("(?:[^"\\]|\\.)*"|[{}();=,])')
    while offset < len(source.rstrip()):
        match = token.match(source, offset)
        need(match is not None, 'Unknown quoted project syntax')
        tokens.append(match[1]); offset = match.end()
        need(len(tokens) <= 80_000, 'Project token cap')
    cursor = [0]
    def take(expected=None):
        need(cursor[0] < len(tokens), 'Truncated project')
        result = tokens[cursor[0]]; cursor[0] += 1
        need(expected is None or result == expected, 'Unexpected project token')
        return result
    def value(depth=0):
        need(depth <= 24, 'Project nesting cap')
        item = take()
        if item == '{':
            result = {}
            while cursor[0] < len(tokens) and tokens[cursor[0]] != '}':
                key = json.loads(take()); take('=')
                need(type(key) is str and key not in result, 'Duplicate/invalid project key')
                result[key] = value(depth + 1); take(';')
            take('}'); return result
        if item == '(':
            result = []
            while cursor[0] < len(tokens) and tokens[cursor[0]] != ')':
                result.append(value(depth + 1))
                need(cursor[0] < len(tokens), 'Truncated project array')
                if tokens[cursor[0]] == ',': take(',')
                else: need(tokens[cursor[0]] == ')', 'Unexpected project array separator')
            take(')'); return result
        result = json.loads(item)
        need(type(result) is str, 'Unexpected unquoted project scalar')
        return result
    result = value()
    need(cursor[0] == len(tokens) and type(result) is dict and type(result.get('objects')) is dict, 'Invalid project root')
    objects = result['objects']
    need(0 < len(objects) <= 4096 and all(type(v) is dict and type(v.get('isa')) is str for v in objects.values()), 'Invalid project objects')
    return objects


def source_graph(root):
    root = Path(root)
    project_path = root / 'Celluloid.xcodeproj/project.pbxproj'
    scheme_path = root / 'Celluloid.xcodeproj/xcshareddata/xcschemes/Celluloid.xcscheme'
    project_raw, scheme_raw = read(project_path, 500_000), read(scheme_path)
    objects = project_objects(project_raw)
    need(b'<!DOCTYPE' not in scheme_raw and b'<!ENTITY' not in scheme_raw, 'Scheme entity declaration forbidden')
    scheme = ET.fromstring(scheme_raw)
    targets = {key: obj for key, obj in objects.items() if obj['isa'] == 'PBXNativeTarget'}
    names = {obj['name']: key for key, obj in targets.items()}
    need(len(names) == len(targets) and set(names) == {'Celluloid', 'CelluloidKit', 'CelluloidPhotoExtension', 'CelluloidTests', 'CelluloidUITests'}, 'Unexpected/duplicate iOS target set')
    projects = [(key, obj) for key, obj in objects.items() if obj['isa'] == 'PBXProject']
    need(len(projects) == 1 and len(projects[0][1]['targets']) == len(targets)
         and set(projects[0][1]['targets']) == set(targets), 'Project target root mismatch')
    entries = scheme.findall('./BuildAction/BuildActionEntries/BuildActionEntry')
    need(len(entries) == 1 and entries[0].get('buildForArchiving') == 'YES', 'Archive scheme must select one enabled app entry')
    refs = entries[0].findall('BuildableReference')
    need(len(refs) == 1, 'Missing/duplicate archive reference')
    ref = refs[0].attrib
    need(ref.get('BlueprintIdentifier') == names['Celluloid'] and ref.get('BlueprintName') == 'Celluloid'
         and ref.get('BuildableName') == 'Celluloid.app' and ref.get('ReferencedContainer') == 'container:Celluloid.xcodeproj', 'Archive scheme target identity mismatch')
    actions = scheme.findall('ArchiveAction')
    need(len(actions) == 1 and actions[0].get('buildConfiguration') == 'Release', 'Archive scheme is not Release')
    expected_dependencies = {'Celluloid': {'CelluloidKit', 'CelluloidPhotoExtension'}, 'CelluloidKit': set(), 'CelluloidPhotoExtension': {'CelluloidKit'}}
    expected_packages = {'Celluloid': {'SnapKit'}, 'CelluloidKit': {'SnapKit', 'CelluloidDomain'}, 'CelluloidPhotoExtension': set()}
    expected_types = {'Celluloid': 'application', 'CelluloidKit': 'framework', 'CelluloidPhotoExtension': 'app-extension'}
    result, localization_sources = {}, {}
    for name in expected_dependencies:
        target = targets[names[name]]
        dependencies = []
        for key in target['dependencies']:
            dep = objects[key]
            need(dep['isa'] == 'PBXTargetDependency' and dep['target'] in targets, 'Broken target dependency')
            other = targets[dep['target']]['name']; dependencies.append(other)
            proxy = objects[dep['targetProxy']]
            need(proxy['isa'] == 'PBXContainerItemProxy' and proxy['remoteGlobalIDString'] == dep['target']
                 and proxy['remoteInfo'] == other and proxy.get('containerPortal') == projects[0][0], 'Dependency proxy identity mismatch')
        need(len(dependencies) == len(set(dependencies)) and set(dependencies) == expected_dependencies[name], 'Archive target dependency closure mismatch')
        need(target['productType'] == 'com.apple.product-type.' + expected_types[name], 'Archive target product type mismatch')
        product = objects[target['productReference']]
        suffix = {'Celluloid': '.app', 'CelluloidKit': '.framework', 'CelluloidPhotoExtension': '.appex'}[name]
        need(product.get('path') == name + suffix and product.get('sourceTree') == 'BUILT_PRODUCTS_DIR', 'Archive target product reference mismatch')
        config_refs = objects[target['buildConfigurationList']]['buildConfigurations']
        configs = [objects[key] for key in config_refs if objects[key].get('name') == 'Release']
        need(len(configs) == 1, 'Missing/duplicate Release settings')
        settings = configs[0]['buildSettings']
        info_relative = name + '/Info.plist'
        need(settings.get('INFOPLIST_FILE') == info_relative and settings.get('PRODUCT_NAME') == '$(TARGET_NAME)', 'Unexpected owned plist/product setting')
        info = plist(read(root / info_relative))
        build = info.get('CFBundleVersion')
        if build == '$(CURRENT_PROJECT_VERSION)': build = settings.get('CURRENT_PROJECT_VERSION')
        need(info.get('CFBundleShortVersionString') == '1.1.1' and build == '3' and settings.get('CURRENT_PROJECT_VERSION') == '3', 'Owned Release version/build mismatch')
        need(settings.get('IPHONEOS_DEPLOYMENT_TARGET') == '15.0' and settings.get('DEBUG_INFORMATION_FORMAT') == 'dwarf-with-dsym', 'Owned Release minimum OS/symbol settings mismatch')
        need(settings.get('SWIFT_OPTIMIZATION_LEVEL') == '-O' and 'DEBUG' not in settings.get('SWIFT_ACTIVE_COMPILATION_CONDITIONS', '').split() and settings.get('ENABLE_TESTABILITY') != 'YES', 'Debug/testability Release settings')
        wanted_id = BUNDLES[{'Celluloid': APP, 'CelluloidKit': KIT, 'CelluloidPhotoExtension': EXT}[name]][1]
        need(settings.get('PRODUCT_BUNDLE_IDENTIFIER') == wanted_id, 'Owned source bundle identifier mismatch')
        if name == 'Celluloid':
            need(settings.get('ASSETCATALOG_COMPILER_APPICON_NAME') == 'AppIcon', 'Source AppIcon build setting changed')
        if name != 'Celluloid':
            need(settings.get('SKIP_INSTALL') == 'YES' and settings.get('APPLICATION_EXTENSION_API_ONLY') == 'YES', 'Embedded target installation/extension settings mismatch')
        packages = []
        for key in target['packageProductDependencies']:
            product = objects[key]; package = objects[product['package']]
            need(product['isa'] == 'XCSwiftPackageProductDependency', 'Invalid package product reference')
            package_name = product['productName']; packages.append(package_name)
            if package_name == 'SnapKit':
                need(package['isa'] == 'XCRemoteSwiftPackageReference' and package.get('repositoryURL') == 'https://github.com/SnapKit/SnapKit.git' and package.get('requirement') == {'kind': 'exactVersion', 'version': '5.7.1'}, 'SnapKit graph pin changed')
            elif package_name == 'CelluloidDomain':
                need(package['isa'] == 'XCLocalSwiftPackageReference' and package.get('relativePath') == 'Packages/CelluloidCore', 'Domain source package changed')
        need(len(packages) == len(set(packages)) and set(packages) == expected_packages[name], 'Archive package product closure mismatch')
        phases = [objects[key] for key in target['buildPhases']]
        need(all(phase['isa'] in {'PBXSourcesBuildPhase', 'PBXResourcesBuildPhase', 'PBXFrameworksBuildPhase', 'PBXCopyFilesBuildPhase'} for phase in phases), 'Unexpected archive build phase')
        for kind in ('PBXSourcesBuildPhase', 'PBXResourcesBuildPhase', 'PBXFrameworksBuildPhase'):
            need(sum(phase['isa'] == kind for phase in phases) == 1, 'Missing/duplicate archive phase')
        linked = []
        for phase in phases:
            if phase['isa'] != 'PBXFrameworksBuildPhase': continue
            for build in phase['files']:
                item = objects[build]
                need(('productRef' in item) != ('fileRef' in item), 'Ambiguous framework link')
                if 'productRef' in item:
                    need(item['productRef'] in target['packageProductDependencies'], 'Unbound linked package product')
                    linked.append(objects[item['productRef']]['productName'])
                else:
                    product = objects[item['fileRef']]
                    need(product.get('sourceTree') == 'BUILT_PRODUCTS_DIR', 'Unexpected linked framework root')
                    linked.append(product['path'])
        expected_linked = expected_packages[name] | ({'CelluloidKit.framework'} if name in {'Celluloid', 'CelluloidPhotoExtension'} else set())
        need(len(linked) == len(set(linked)) and set(linked) == expected_linked, 'Actual framework link closure mismatch')
        copies = []
        resources = []
        def file_paths(key):
            obj = objects[key]
            if obj['isa'] == 'PBXVariantGroup': return [path for child in obj['children'] for path in file_paths(child)]
            need(obj.get('sourceTree') == '<group>', 'Unexpected resource root')
            return [obj['path']]
        for phase in phases:
            if phase['isa'] == 'PBXCopyFilesBuildPhase':
                for build in phase['files']:
                    item = objects[build]; copied = objects[item['fileRef']]
                    copies.append([phase['dstSubfolderSpec'], copied['path']])
                    need(copied.get('sourceTree') == 'BUILT_PRODUCTS_DIR' and item.get('settings', {}).get('ATTRIBUTES') == ['RemoveHeadersOnCopy', 'CodeSignOnCopy'], 'Unexpected embedded product attributes')
            if phase['isa'] == 'PBXResourcesBuildPhase':
                resources.extend(path for build in phase['files'] for path in file_paths(objects[build]['fileRef']))
        need(sorted(copies) == ([['10', 'CelluloidKit.framework'], ['13', 'CelluloidPhotoExtension.appex']] if name == 'Celluloid' else []), 'Actual copy phases do not embed exact Kit/Photos products')
        need(len(resources) == len(set(resources)) and set(resources) == SOURCE_RESOURCES[name], 'Source resource membership changed')
        for language in ('en', 'zh-Hans'):
            if name == 'CelluloidPhotoExtension': continue
            choices = [p for p in resources if p.endswith('/' + language + '.lproj/Localizable.strings')]
            need(len(choices) == 1, 'Missing/duplicate source localized resource')
            localization_sources[name + '/' + language] = choices[0]
        result[name] = {'target_id': names[name], 'dependencies': sorted(dependencies), 'package_products': sorted(packages), 'copy_phases': sorted(copies), 'version': '1.1.1', 'build': '3', 'minimum_ios': '15.0', 'debug_information_format': 'dwarf-with-dsym', 'resources': sorted(resources)}
    core_raw = read(root / 'Packages/CelluloidCore/Package.swift')
    # The source admission binds all bytes; these declarations independently bind the resource/product graph.
    core = core_raw.decode('utf8')
    need(re.search(r'\.library\(name:\s*"CelluloidDomain",\s*targets:\s*\["CelluloidDomain"\]\)', core)
         and re.search(r'\.target\(name:\s*"CelluloidDomain",\s*resources:\s*\[\.process\("Resources"\)\]\)', core), 'Domain resource/product declaration changed')
    domain_root = root / DOMAIN_SOURCE
    fd = directory_fd(domain_root); os.close(fd)
    domain_files = sorted(str(p.relative_to(domain_root)) for p in domain_root.rglob('*') if p.is_file())
    need(domain_files == ['en.lproj/Localizable.strings', 'zh-Hans.lproj/Localizable.strings'], 'Domain resource source closure changed')
    domain = {}
    for path in domain_files:
        raw = read(domain_root / path)
        domain[path] = {'sha256': sha(raw), 'strings': source_strings(raw)}
        need(domain[path]['strings'], 'Empty Domain localization')
    need(set(domain['en.lproj/Localizable.strings']['strings']) == set(domain['zh-Hans.lproj/Localizable.strings']['strings']), 'Domain localization key sets differ')
    icons_raw = read(root / 'Celluloid/Assets.xcassets/AppIcon.appiconset/Contents.json')
    icons = json.loads(icons_raw)
    need(type(icons) is dict and type(icons.get('images')) is list and icons['images'], 'Missing source app icon catalog')
    need(any(item.get('idiom') == 'ios-marketing' and item.get('size') == '1024x1024' for item in icons['images']), 'Missing marketing icon source slot')
    return {'scheme': 'Celluloid', 'configuration': 'Release', 'archive_targets': sorted(result), 'project_sha256': sha(project_raw), 'scheme_sha256': sha(scheme_raw), 'targets': result, 'localization_sources': localization_sources, 'domain_manifest_sha256': sha(core_raw), 'domain_resources': domain,
            'app_icon_source': {'asset_name': 'AppIcon', 'catalog_sha256': sha(icons_raw), 'source_slots': len(icons['images'])},
            'ui_tests_selected': False, 'producer_selected': False}


verify_source_graph = source_graph


def macho_header(data, total_size, file_type):
    """Thin arm64 header and complete LC_UUID, also for MH_DSYM DWARF objects."""
    need(len(data) >= 32 and data[:4] == b'\xcf\xfa\xed\xfe', 'Wrong Mach-O magic')
    _, cpu, subtype, actual_type, commands, size, _, _ = struct.unpack_from('<IIIIIIII', data)
    need(cpu == 0x100000c and actual_type == file_type, 'Wrong Mach-O architecture/file type')
    need(0 < commands <= 512 and commands * 8 <= size <= 256000 and 32 + size <= min(total_size, len(data)), 'Malformed/oversized Mach-O load commands')
    offset, signature, identifiers = 32, {'present': False}, []
    for _ in range(commands):
        need(offset + 8 <= 32 + size, 'Truncated Mach-O load command')
        command, length = struct.unpack_from('<II', data, offset)
        need(length >= 8 and length % 8 == 0 and offset + length <= 32 + size, 'Invalid Mach-O load command size')
        if command == 0x1b:
            need(length == 24, 'Invalid LC_UUID command length')
            identifier = bytes(data[offset + 8:offset + 24])
            need(identifier != b'\0' * 16, 'Zero Mach-O UUID')
            identifiers.append(str(uuid.UUID(bytes=identifier)))
        if command == 0x1d:
            need(file_type != 10 and length == 16 and signature['present'] is False, 'Malformed/duplicate code-signature load command')
            data_offset, data_size = struct.unpack_from('<II', data, offset + 8)
            need(data_size > 0 and data_offset >= 32 + size and data_offset + data_size <= total_size, 'Code-signature load-command range outside executable')
            signature = {'present': True, 'command': 'LC_CODE_SIGNATURE', 'data_offset': data_offset,
                         'data_size': data_size, 'signature_kind': 'unverified', 'signing_qualified': False}
        offset += length
    need(offset == 32 + size, 'Mach-O load command count/size differs')
    need(len(identifiers) == 1, 'Missing/duplicate Mach-O LC_UUID')
    return {'architecture': 'arm64', 'cpu_subtype': subtype, 'file_type': file_type, 'uuid': identifiers[0], 'code_signature_load_command': signature}



# Adapted exact bounded traversal from original_ios_archive.inventory; current bundle/UUID closure.
def inventory(archive, deadline):
    """Bounded traversal and streamed hashes; every path component uses NOFOLLOW."""
    rows, directories, total, snapshots, machos = [], set(), [0], {}, {}
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
                    if entry.name.lower().endswith('.dsym'):
                        need(relative in DSYM_ROOTS, 'Extra symbol bundle: ' + relative)
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
                            if relative in EXECUTABLES or relative in DSYMS.values():
                                header.extend(chunk[:max(0, 256032 - len(header))])
                            if relative in EXECUTABLES:
                                combined = tail + chunk
                                need(not any(marker in combined for marker in DEBUG_MARKERS), 'Debug/test seam in shipping executable')
                                tail = combined[-128:]
                            digest.update(chunk)
                            size += len(chunk)
                        need(snapshot(info) == snapshot(os.fstat(descriptor)) == snapshot(os.stat(entry.name, dir_fd=folder, follow_symlinks=False)), 'Archive file changed while hashing')
                    finally:
                        os.close(descriptor)
                    if magic[:4] in MACHO_MAGICS:
                        need(relative in EXECUTABLES or relative in DSYMS.values(), 'Unexpected executable payload')
                    if relative in EXECUTABLES or relative in DSYMS.values():
                        expected_type = BUNDLES[relative.rsplit('/', 1)[0]][3] if relative in EXECUTABLES else 10
                        machos[relative] = macho_header(header, size, expected_type)
                    rows.append({'path': relative, 'bytes': size, 'sha256': digest.hexdigest()})
                    snapshots[relative] = snapshot(info)
        need(snapshot(before) == snapshot(os.fstat(folder)), 'Archive directory changed during inventory')
    try:
        scan(root)
    finally:
        os.close(root)
    need(set(BUNDLES) <= directories, 'Missing original app/framework/Photos extension')
    need(all(name in {item['path'] for item in rows} for name in EXECUTABLES), 'Missing original executable')
    need(set(DSYMS.values()) <= {item['path'] for item in rows}, 'Missing required archived dSYM')
    return sorted(rows, key=lambda row: row['path']), directories, snapshots, machos


def verify_resources(root, archive, files, directories, graph, deadline):
    hashes = {row['path']: row['sha256'] for row in files}
    sizes = {row['path']: row['bytes'] for row in files}
    for path, source_name in [(APP + '/collage.json', 'Celluloid/collage.json'),
                              (KIT + '/bubble.json', 'CelluloidKit/bubble.json'),
                              (KIT + '/SnapKit-LICENSE.txt', 'CelluloidKit/ThirdPartyNotices/SnapKit-LICENSE.txt')]:
        check_deadline(deadline)
        need(hashes.get(path) == sha(read(root / source_name)), 'Missing/changed original bundled resource: ' + path)
    need(hashes[KIT + '/SnapKit-LICENSE.txt'] == NOTICE_HASH, 'Pinned SnapKit notice changed')
    localization = []
    for name, owner in [('Celluloid', APP), ('CelluloidKit', KIT)]:
        need(sizes.get(owner + '/Assets.car', 0) > 0, 'Missing/empty compiled asset catalog')
        for language in ('en', 'zh-Hans'):
            relative = owner + '/' + language + '.lproj/Localizable.strings'
            expected = source_strings(read(root / graph['localization_sources'][name + '/' + language]))
            actual = strings_plist(read(archive / relative))
            need(actual == expected, 'Compiled localization differs from current source: ' + relative)
            localization.append({'path': relative, 'sha256': hashes[relative], 'source_keys': len(expected)})
    usage_path = APP + '/zh-Hans.lproj/InfoPlist.strings'
    expected_usage = source_strings(read(root / 'Celluloid/zh-Hans.lproj/InfoPlist.strings'))
    need(set(expected_usage) == {'NSPhotoLibraryUsageDescription', 'NSPhotoLibraryAddUsageDescription'}, 'Source Photos usage keys changed')
    localized_usage = strings_plist(read(archive / usage_path))
    need(localized_usage == expected_usage, 'Localized Photos privacy declarations changed')
    for directory in (APP + '/Base.lproj/LaunchScreen.storyboardc', EXT + '/Base.lproj/MainInterface.storyboardc'):
        need(directory in directories and any(row['path'].startswith(directory + '/') and row['bytes'] > 0 for row in files), 'Missing/empty compiled launch/Photos storyboard')
    privacy = []
    for row in files:
        check_deadline(deadline)
        path = row['path']
        if path.endswith('/Info.plist'):
            info = plist(read(archive / path))
            need('CFBundleExecutable' not in info or path.rsplit('/', 1)[0] in BUNDLES, 'Hidden extra code bundle metadata')
        if path.lower().endswith('.xcprivacy'):
            need(path in {bundle + '/PrivacyInfo.xcprivacy' for bundle in SNAPKIT_RESOURCES}, 'Unreviewed privacy manifest location')
            declaration = plist(read(archive / path))
            need(encoded(declaration) == encoded(PRIVACY), 'Pinned SnapKit privacy declarations changed')
            privacy.append({'path': path, 'sha256': row['sha256'], 'declarations': declaration})
    need(SNAPKIT_RESOURCES <= directories and len(privacy) == 3, 'Missing pinned SnapKit privacy resource')
    need(len({item['sha256'] for item in privacy}) == 1, 'SnapKit privacy resource copies differ in exact bytes')
    present_domain = DOMAIN_RESOURCES & directories
    need(KIT + '/' + DOMAIN_NAME in present_domain or {APP + '/' + DOMAIN_NAME, EXT + '/' + DOMAIN_NAME} <= present_domain,
         'Domain resource is not reachable by both app and Photos extension')
    domain = []
    domain_hashes = {language: set() for language in ('en', 'zh-Hans')}
    for bundle in sorted(SNAPKIT_RESOURCES | present_domain):
        check_deadline(deadline)
        expected_files = {'Info.plist', 'PrivacyInfo.xcprivacy'} if bundle in SNAPKIT_RESOURCES else {'Info.plist', 'en.lproj/Localizable.strings', 'zh-Hans.lproj/Localizable.strings'}
        actual_files = {row['path'][len(bundle) + 1:] for row in files if row['path'].startswith(bundle + '/')}
        expected_dirs = set() if bundle in SNAPKIT_RESOURCES else {'en.lproj', 'zh-Hans.lproj'}
        actual_dirs = {path[len(bundle) + 1:] for path in directories if path.startswith(bundle + '/')}
        need(actual_files == expected_files and actual_dirs == expected_dirs, 'Missing/extra resource bundle content: ' + bundle)
        info = plist(read(archive / bundle / 'Info.plist'))
        need(info.get('CFBundlePackageType') == 'BNDL' and 'CFBundleExecutable' not in info, 'Invalid resource bundle metadata')
        if bundle in SNAPKIT_RESOURCES: continue
        records = []
        for language in ('en', 'zh-Hans'):
            relative = language + '.lproj/Localizable.strings'
            raw = read(archive / bundle / relative)
            actual = strings_plist(raw)
            need(actual == graph['domain_resources'][relative]['strings'], 'Domain localization differs from exact current source')
            domain_hashes[language].add(sha(raw))
            records.append({'path': relative, 'sha256': sha(raw), 'source_sha256': graph['domain_resources'][relative]['sha256'], 'keys': len(actual)})
        domain.append({'path': bundle, 'metadata': dict(info), 'localizations': records})
    need(all(len(values) == 1 for values in domain_hashes.values()), 'Domain localization copies differ in exact bytes')
    return {'localizations': localization, 'localized_photos_usage': localized_usage, 'privacy_manifests': privacy,
            'domain_resource_bundles': domain, 'domain_placement_policy': 'Only app, Kit, and Photos owners in current graph; require Kit copy or both host copies; actual placements observed.',
            'application_privacy_manifest_present': False,
            'privacy_scope': 'Observed shipped declarations and Photos usage strings only; no privacy or Store acceptance inferred.'}


def icon_observation(info, files, expected_name):
    """Record actual compiled declarations without guessing an unobserved Xcode rendition schema."""
    declarations = {key: info.get(key) for key in ('CFBundleIcons', 'CFBundleIcons~ipad', 'CFBundleIconName', 'CFBundleIconFiles')}
    names, references = [], []
    def visit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == 'CFBundleIconName':
                    need(type(item) is str and item == expected_name, 'Compiled app icon name differs from source asset setting')
                    names.append(item)
                elif key == 'CFBundleIconFiles':
                    need(type(item) is list and all(type(name) is str and re.fullmatch(r'[A-Za-z0-9_.@~-]{1,128}', name) for name in item), 'Malformed compiled icon file references')
                    references.extend(item)
                else: visit(item)
        elif type(value) is list:
            for item in value: visit(item)
    visit({key: value for key, value in declarations.items() if value is not None})
    root_files = {row['path'][len(APP) + 1:]: row for row in files if row['path'].startswith(APP + '/') and '/' not in row['path'][len(APP) + 1:]}
    observed = []
    for reference in sorted(set(references)):
        base = reference[:-4] if reference.lower().endswith('.png') else reference
        pattern = re.compile(re.escape(base) + r'(?:@[1-3]x)?(?:~(?:iphone|ipad))?\.png')
        matches = [row for name, row in sorted(root_files.items()) if pattern.fullmatch(name) and row['bytes'] > 0]
        observed.append({'reference': reference, 'positive_file_matches': matches})
    catalog = root_files.get('Assets.car')
    need(catalog is not None and catalog['bytes'] > 0, 'Missing/empty compiled app asset catalog')
    return {'source_asset_name': expected_name, 'compiled_declarations': declarations, 'observed_icon_names': sorted(set(names)),
            'file_references': observed, 'all_observed_file_references_matched': bool(observed) and all(item['positive_file_matches'] for item in observed),
            'asset_catalog': catalog, 'visual_or_rendition_qualification': False,
            'scope': 'Observed plist declarations, positive standalone PNG matches where present, and nonempty Assets.car hash only. No assumed Xcode icon layout or asset rendition/visual acceptance.'}


def _verify_package(root, deadline, archive_relative, probes):
    started = time.monotonic()
    need(number(deadline) and deadline > started, 'Missing/expired absolute proof deadline')
    deadline = min(started + 180, deadline)
    need(archive_relative == ARCHIVE, 'Unexpected archive path')
    root = Path(root).absolute(); archive = root / archive_relative
    graph = source_graph(root)
    check_deadline(deadline)
    files, directories, snapshots, machos = inventory(archive, deadline)
    hashes = {row['path']: row['sha256'] for row in files}
    metadata = plist(read(archive / 'Info.plist'))
    properties = metadata.get('ApplicationProperties', {})
    need(type(metadata.get('ArchiveVersion')) is int and metadata['ArchiveVersion'] == 2 and metadata.get('SchemeName') == 'Celluloid', 'Wrong archive metadata')
    for key, wanted in {'ApplicationPath': 'Applications/Celluloid.app', 'CFBundleIdentifier': 'Mango.Celluloid', 'CFBundleShortVersionString': '1.1.1', 'CFBundleVersion': '3'}.items():
        need(properties.get(key) == wanted and type(properties.get(key)) is type(wanted), 'Wrong archive property: ' + key)
    source_info = plist(read(root / 'Celluloid/Info.plist'))
    icons = None
    bundle_reports, all_uuids = [], set()
    for path, (name, bundle_id, package_type, _) in BUNDLES.items():
        check_deadline(deadline)
        info = plist(read(archive / path / 'Info.plist'))
        expected = {'CFBundleExecutable': name, 'CFBundleIdentifier': bundle_id,
                    'CFBundlePackageType': package_type, 'CFBundleShortVersionString': '1.0' if path == SNAPKIT else '1.1.1',
                    'CFBundleVersion': '1' if path == SNAPKIT else '3',
                    'DTPlatformName': 'iphoneos', 'CFBundleSupportedPlatforms': ['iPhoneOS'], 'MinimumOSVersion': '15.0'}
        if path != SNAPKIT: expected['CFBundleName'] = name
        for key, wanted in expected.items():
            need(info.get(key) == wanted and type(info.get(key)) is type(wanted), 'Wrong final bundle metadata: ' + path + '/' + key)
        if path == APP:
            for key in ('NSPhotoLibraryUsageDescription', 'NSPhotoLibraryAddUsageDescription', 'PHPhotoLibraryPreventAutomaticLimitedAccessAlert', 'UILaunchStoryboardName', 'UIRequiredDeviceCapabilities', 'UIApplicationSceneManifest'):
                wanted = source_info[key]
                if key == 'UIApplicationSceneManifest':
                    wanted = json.loads(json.dumps(wanted).replace('$(PRODUCT_MODULE_NAME)', name))
                need(encoded(info.get(key)) == encoded(wanted), 'Final Photos/privacy/scene declaration changed: ' + key)
            need(encoded(info.get('UIDeviceFamily')) == encoded([1, 2]), 'Original iPhone/iPad family changed')
            icons = icon_observation(info, files, graph['app_icon_source']['asset_name'])
        if path == EXT:
            need(encoded(info.get('NSExtension')) == encoded(plist(read(root / 'CelluloidPhotoExtension/Info.plist'))['NSExtension']), 'Original Photos extension declaration changed')
            expected['NSExtension'] = info['NSExtension']
        binary = path + '/' + name
        actual, dwarf = machos[binary], machos[DSYMS[path]]
        need(actual['uuid'] == dwarf['uuid'] and actual['cpu_subtype'] == dwarf['cpu_subtype'], 'Executable/DWARF UUID or CPU subtype mismatch')
        need(actual['uuid'] not in all_uuids, 'Duplicate UUID across independent code bundles')
        all_uuids.add(actual['uuid'])
        executable = archive / binary
        need(probes.run('lipo', executable).strip().split() == ['arm64'], 'Wrong actual archive architecture')
        versions = build_versions(probes.run('vtool', executable), executable)
        libraries = linked_libraries(probes.run('otool', executable), executable, path)
        observed_name = info.get('CFBundleName')
        need(observed_name is None or type(observed_name) is str and 0 < len(observed_name.encode()) <= 256, 'Malformed observed bundle name')
        bundle_reports.append({'path': path, 'metadata': expected, 'executable_sha256': hashes[binary],
                               'architectures': ['arm64'], 'build_versions': versions, 'linked_libraries': libraries,
                               'install_name': INSTALL_NAMES.get(path), 'observed_bundle_name': observed_name,
                               'code_signature_load_command': actual['code_signature_load_command'],
                               'uuid': actual['uuid'], 'dsym_path': DSYMS[path], 'dsym_sha256': hashes[DSYMS[path]],
                               'dsym_uuid': dwarf['uuid'], 'uuid_match': True})
    resources = verify_resources(root, archive, files, directories, graph, deadline)
    resolved = json.loads(read(root / 'Celluloid.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved'))
    need(resolved == {'pins': [{'identity': 'snapkit', 'kind': 'remoteSourceControl', 'location': 'https://github.com/SnapKit/SnapKit.git',
                              'state': {'revision': SNAPKIT_REVISION, 'version': '5.7.1'}}], 'version': 2}, 'SnapKit source pin changed')
    unchanged(archive, snapshots, deadline)
    check_deadline(deadline)
    return {'schema': 'Celluloid.FinalIOSArchivePackage.1', 'unsigned_package_verified': True,
            'release_acceptance': False, 'signing_qualified': False, 'uploaded': False,
            'all_processes_finalized': True, 'archive_path': ARCHIVE, 'source_graph': graph,
            'code_bundles': bundle_reports, 'files': files, 'inventory_sha256': sha(encoded(files)),
            **resources, 'app_icon_observation': icons,
            'photos_usage': {'default': {key: source_info[key] for key in ('NSPhotoLibraryUsageDescription', 'NSPhotoLibraryAddUsageDescription')}, 'zh-Hans': resources['localized_photos_usage']},
            'snapkit': {'version': '5.7.1', 'revision': SNAPKIT_REVISION, 'notice_sha256': NOTICE_HASH},
            'processes': probes.events, 'proof_elapsed_seconds': time.monotonic() - started,
            'limits': {'entries': MAX_ENTRIES, 'file_bytes': MAX_FILE, 'total_read_bytes': MAX_BYTES, 'proof_seconds': 180, 'command_seconds_including_cleanup': 20, 'command_output_bytes': 8192},
            'qualification': 'Unsigned generic-device Release archive diagnostic only; not UI, producer compatibility, signing, installation, distribution, privacy, or Store acceptance.'}


def verify_package(root, deadline, *, archive_relative=ARCHIVE):
    """Return complete proof or retain completed/uncertain probe receipts on every failure."""
    now = time.monotonic()
    need(number(deadline) and deadline > now, 'Missing/expired absolute proof deadline')
    deadline = min(now + 180, deadline)
    probes = ProofCommands(deadline)
    try:
        return _verify_package(root, deadline, archive_relative, probes)
    except ObservationFailure:
        raise
    except BaseException as error:
        raise ObservationFailure(str(error)[:2048], probes.events, not probes.blocked) from error
