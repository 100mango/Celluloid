#!/usr/bin/env python3
"""Verify an actual shipping iOS bundle's canonical nested Watch producer; no signing."""
from pathlib import Path
import argparse, hashlib, json, os, plistlib, re, shlex, subprocess, tempfile

def inventory(folder):
    folder = Path(folder)
    rows = []
    for path in sorted(folder.rglob('*')):
        relative = path.relative_to(folder).as_posix()
        if path.is_symlink():
            target = os.readlink(path)
            if Path(target).is_absolute() or '..' in Path(target).parts:
                raise ValueError('Watch bundle contains an escaping symlink')
            rows.append([relative, 'symlink', target])
        elif path.is_file():
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''): digest.update(chunk)
            rows.append([relative, 'file', path.stat().st_size, digest.hexdigest()])
        if len(rows) > 10000: raise ValueError('Unexpected Watch bundle inventory size')
    return rows

def hosted_test_contract(phone, mode, build_for_testing):
    phone=Path(phone);found=sorted(phone.rglob('*.xctest'))
    if not build_for_testing:return not found,{'mode':'ordinary product; all XCTest bundles forbidden','found':[str(p.relative_to(phone)) for p in found]}
    if mode!='simulator':raise ValueError('Build-for-testing mode is forbidden for device Release')
    expected=phone/'PlugIns/CelluloidCompanionTests.xctest'
    report={'mode':'explicit shipping companion build-for-testing','expected_path':'PlugIns/CelluloidCompanionTests.xctest','found':[str(p.relative_to(phone)) for p in found]}
    if found!=[expected] or expected.is_symlink() or not expected.resolve().is_relative_to(phone.resolve()):return False,report
    metadata=expected/'Info.plist';executable=expected/'CelluloidCompanionTests'
    if not metadata.is_file() or metadata.is_symlink() or metadata.stat().st_size>100_000 or not executable.is_file() or executable.is_symlink() or executable.stat().st_size==0:return False,report
    info=plistlib.loads(metadata.read_bytes())
    checks={'registered_bundle_identity':info.get('CFBundleIdentifier')=='Mango.Celluloid.CompanionTests',
            'registered_executable':info.get('CFBundleExecutable')=='CelluloidCompanionTests',
            'simulator_test_bundle':info.get('DTPlatformName')=='iphonesimulator' and info.get('CFBundlePackageType')=='BNDL'}
    report.update(checks=checks,executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),bundle_identifier=info.get('CFBundleIdentifier'))
    return all(checks.values()),report

def bundle_checks(phone, producer, mode, build_for_testing=False):
    phone, producer = Path(phone), Path(producer)
    nested = phone / 'Watch/CelluloidWatch.app'
    p = plistlib.loads((phone / 'Info.plist').read_bytes())
    w = plistlib.loads((nested / 'Info.plist').read_bytes())
    actual, expected = inventory(nested), inventory(producer)
    checks = {
        'shipping_phone_identity': p.get('CFBundleIdentifier') == 'Mango.Celluloid' and p.get('CFBundleExecutable') == 'Celluloid',
        'phone_version': (p.get('CFBundleShortVersionString'), p.get('CFBundleVersion')) == ('1.1.1', '3'),
        'watch_version_equals_phone': all(w.get(k) == p.get(k) for k in ['CFBundleShortVersionString', 'CFBundleVersion']),
        'watch_identity': w.get('CFBundleIdentifier') == 'Mango.Celluloid.watchkitapp' and w.get('CFBundleExecutable') == 'CelluloidWatch',
        'watch_companion_binding': w.get('WKApplication') is True and w.get('WKCompanionAppBundleIdentifier') == p.get('CFBundleIdentifier'),
        'phone_platform': p.get('DTPlatformName') == ('iphoneos' if mode == 'device' else 'iphonesimulator'),
        'watch_platform': w.get('DTPlatformName') == ('watchos' if mode == 'device' else 'watchsimulator'),
        'watch_bundle_floor': w.get('MinimumOSVersion') == '9.0',
        'exact_nested_producer_inventory': bool(actual) and actual == expected,
        'only_expected_watch': [x.name for x in (phone / 'Watch').iterdir()] == ['CelluloidWatch.app'],
        'compiled_watch_icon': (nested / 'Assets.car').is_file(),
        'localized_watch': all((nested / (language + '.lproj') / 'Localizable.strings').is_file() for language in ['en', 'zh-Hans']),
    }
    checks['registered_hosted_test_product' if build_for_testing else 'no_test_products']=hosted_test_contract(phone,mode,build_for_testing)[0]
    privacy = []
    for file in sorted(nested.rglob('PrivacyInfo.xcprivacy')):
        value = plistlib.loads(file.read_bytes())
        privacy.append({'path': file.relative_to(nested).as_posix(), 'sha256': hashlib.sha256(file.read_bytes()).hexdigest(), 'declarations': value})
    return checks, nested, actual, privacy

def copied_inventory(phone, producer, mode, build_log=None, archive_root=None):
    """All bytes must match; only a witnessed Release strip may transform the executable."""
    nested=Path(phone)/'Watch/CelluloidWatch.app'
    actual,expected=inventory(nested),inventory(producer)
    report={'raw_inventory_equal':actual==expected,'transformation':'none'}
    if actual==expected:return True,report
    if mode!='device' or build_log is None:return False,report
    other=lambda rows:[r for r in rows if r[0]!='CelluloidWatch']
    if other(actual)!=other(expected):return False,report
    source=Path(producer)/'CelluloidWatch'; target=nested/'CelluloidWatch'
    target_paths={target.resolve()}
    if archive_root is not None:
        root=Path(archive_root).resolve()
        for candidate in root.rglob('CelluloidWatch.app'):
            if tuple(candidate.parts[-3:])!=('Celluloid.app','Watch','CelluloidWatch.app'):continue
            if not candidate.resolve().is_relative_to(root):raise ValueError('Archive copy product escapes derived data')
            if inventory(candidate)==actual:target_paths.add((candidate/'CelluloidWatch').resolve())
            if len(target_paths)>4:raise ValueError('Unexpected archive copy targets')
    strip=Path(subprocess.check_output(['xcrun','--find','strip'],text=True).strip())
    expected_command=[str(strip),'-D','-S','-no_atom_info',str(source.resolve()),'-o',str(target.resolve())]
    witnessed=[]
    with Path(build_log).open('r',encoding='utf8',errors='replace') as handle:
        for line in handle:
            try:parts=shlex.split(line.strip())
            except ValueError:continue
            if len(parts)==7 and parts[:4]==expected_command[:4] and parts[5]=='-o':
                if Path(parts[4]).resolve()==source.resolve() and Path(parts[6]).resolve() in target_paths:witnessed.append(parts)
    if len(witnessed)!=1:return False,dict(report,error='Expected exactly one observed Release strip command for this producer and nested executable')
    with tempfile.TemporaryDirectory(prefix='celluloid-watch-copy-') as folder:
        output=Path(folder)/'stripped-watch'
        subprocess.run([str(strip),'-D','-S','-no_atom_info',str(source),'-o',str(output)],check=True,timeout=60)
        transformed=hashlib.sha256(output.read_bytes()).hexdigest()
    actual_hash=hashlib.sha256(target.read_bytes()).hexdigest()
    report.update(transformation='observed Xcode Release strip -D -S -no_atom_info',command=witnessed[0],producer_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),transformed_sha256=transformed,nested_sha256=actual_hash,all_nonexecutable_bytes_equal=True)
    return transformed==actual_hash,report

def discover_archive_producer(root):
    root=Path(root).resolve(); candidates={}
    for path in root.rglob('CelluloidWatch.app'):
        # Xcode's ArchiveIntermediates/BuildProductsPath may be a symlink to its
        # own installation product. Only bounded same-derived-data producers.
        if path.parent.name!='Release-watchos':continue
        actual=path.resolve()
        if not actual.is_relative_to(root):raise ValueError('Archive producer escapes its derived data')
        candidates[str(actual)]=path
        if len(candidates)>4:raise ValueError('Unexpected archive Watch producer count')
    if len(candidates)!=1:raise ValueError('Expected one actual Release-watchos archive producer')
    return next(iter(candidates.values()))

def verify(phone, producer, mode, build_log=None, archive_root=None, build_for_testing=False):
    checks, nested, rows, privacy = bundle_checks(phone, producer, mode,build_for_testing)
    checks.pop('exact_nested_producer_inventory')
    checks['verified_nested_producer_inventory'],copy_receipt=copied_inventory(phone,producer,mode,build_log,archive_root)
    executable = nested / 'CelluloidWatch'
    archs = subprocess.check_output(['xcrun', 'lipo', '-archs', str(executable)], text=True).strip().split()
    loads = {a: subprocess.check_output(['xcrun', 'vtool', '-arch', a, '-show-build', str(executable)], text=True) for a in archs}
    if mode == 'device':
        checks['dual_physical_watch_slices'] = set(archs) == {'arm64', 'arm64_32'}
        checks['actual_watch_minima'] = all(re.search(r'\bplatform\s+WATCHOS\b', loads.get(a, '')) and re.findall(r'\bminos\s+(\S+)', loads.get(a, '')) == [floor] for a, floor in [('arm64', '26.0'), ('arm64_32', '9.0')])
    else:
        checks['actual_watch_simulator_platform'] = bool(loads) and all(re.search(r'\bplatform\s+WATCHOSSIMULATOR\b', value) for value in loads.values())
    phone_binary=(Path(phone)/'Celluloid').read_bytes()
    phone_loads=subprocess.check_output(['xcrun','vtool','-show-build',str(Path(phone)/'Celluloid')],text=True)
    phone_info=plistlib.loads((Path(phone)/'Info.plist').read_bytes())
    checks['actual_shipping_phone_floor']=phone_info.get('MinimumOSVersion')=='15.0' and bool(re.findall(r'\bminos\s+(\S+)',phone_loads)) and set(re.findall(r'\bminos\s+(\S+)',phone_loads))=={'15.0'}
    checks['shipping_phone_debug_seams_absent']=not any(marker in phone_binary for marker in [b'CELLULOID_PHONE_LAYOUT_FIXTURE',b'WatchProcessingLargeTextUI',b'CELLULOID_PHONE_OUTPUT_PROOF',b'PhoneOutputProof']) if mode=='device' else True
    binary = executable.read_bytes()
    checks['watch_debug_fixture_markers_absent'] = not any(marker in binary for marker in [b'companion.synthetic-seed', b'A2E0E7B0-0A3B-47D3-94E5-309F3614E54A']) if mode == 'device' else True
    return {'source_sha': os.environ.get('GITHUB_SHA'), 'mode': mode, 'phone': str(phone), 'nested_watch': str(nested), 'watch_producer': str(producer),
            'checks': checks, 'build_for_testing':build_for_testing,'test_product_receipt':hosted_test_contract(phone,mode,build_for_testing)[1],'architectures': archs, 'linked_build_versions': loads, 'phone_build_versions':phone_loads,'copy_receipt':copy_receipt,'nested_inventory_sha256': hashlib.sha256(json.dumps(rows, separators=(',', ':')).encode()).hexdigest(),
            'privacy_manifests': privacy, 'privacy_note': 'Actual nested declarations are recorded; absence is not a claim of an embedded empty manifest. All nonexecutable bytes equal the producer; any device Release executable transform requires the exact observed strip command and reproduced hash.',
            'scope': 'Actual unsigned package identity/embedding proof. This does not establish paired WatchConnectivity file delivery or oldest-runtime coverage.'}

def main():
    parser = argparse.ArgumentParser(); parser.add_argument('phone'); parser.add_argument('producer'); parser.add_argument('--mode', choices=['device', 'simulator'], required=True); parser.add_argument('--output', required=True);parser.add_argument('--build-log');parser.add_argument('--archive-producer-root',action='store_true');parser.add_argument('--build-for-testing',action='store_true')
    args = parser.parse_args()
    try:
        producer=discover_archive_producer(args.producer) if args.archive_producer_root else args.producer
        report = verify(args.phone, producer, args.mode,args.build_log,args.producer if args.archive_producer_root else None,args.build_for_testing)
    except Exception as error:
        report={'source_sha':os.environ.get('GITHUB_SHA'),'mode':args.mode,'phone':args.phone,'producer':args.producer,'checks':{'embedded_watch_verification':False},'error':str(error)}
    Path(args.output).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'report': args.output, 'checks': report['checks']}))
    if not all(report['checks'].values()): raise SystemExit('Embedded Watch package checks failed')
if __name__ == '__main__': main()
