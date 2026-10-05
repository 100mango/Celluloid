#!/usr/bin/env python3
"""Fail closed on missing, skipped, duplicate or failed required XCTest execution."""
from pathlib import Path
import argparse, hashlib, json, os, re
from native_fixture_handoff import layer_from_log, load_layer_exact, from_log

ROOT = Path(__file__).resolve().parents[1]
RESULT = re.compile(r"^Test Case '-\[([\w.]+) (test\w+)\]' (passed|failed|skipped)\b")
CONSUMER = 'MacPhotosManufacturedAdjustmentTests.testManufacturedMacArchiveThroughOriginalUIKitReaderAndCompositor'
PIXELS = re.compile(r'MAC_LAYER_UIKIT_COMPOSITOR archiveSHA256=([0-9a-f]{64}) sourceSHA256=([0-9a-f]{64}) nativeSHA256=([0-9a-f]{64}) maximumChannelDifference=(\d+)')

def source_cases(paths):
    cases = []
    for path in paths:
        source = path.read_text()
        owner = re.search(r'\bclass (\w+)\s*:\s*XCTestCase', source).group(1)
        cases.extend(owner + '.' + method for method in re.findall(r'\bfunc (test\w+)\(', source))
    if len(cases) != len(set(cases)): raise ValueError('Duplicate declared required test')
    return sorted(cases)

def required(scope):
    if scope == 'mac':
        cases = source_cases(sorted((ROOT/'Platforms/MacExtensionTests').glob('*.swift')) + [ROOT/'CelluloidTests/PhotosOutputWriteTests.swift'])
        assert len(cases) == 39
        return {'CelluloidMacPhotosExtensionTests': cases}
    if scope == 'phone':
        hosted = source_cases(sorted((ROOT/'Platforms/PhoneTests').glob('*.swift'))) + [CONSUMER]
        ui = source_cases(sorted((ROOT/'Platforms/PhoneUITests').glob('*.swift')))
        assert len(hosted) == 14 and len(ui) == 2
        return {'CelluloidCompanionTests': hosted, 'CelluloidCompanionUITests': ui}
    return {'CelluloidTests': [CONSUMER]}

def inspect(log, expected, fixture=None, require_navigation=False, platform_contract=False):
    results = {}; pixels = []; navigation = set(); digest = hashlib.sha256()
    with Path(log).open('rb') as stream:
        for part in iter(lambda: stream.readline(1_000_000), b''):
            digest.update(part)
            line = part.decode('utf8', 'replace').strip()
            if match := RESULT.match(line):
                owner, method, status = match.groups()
                module, _, cls = owner.rpartition('.')
                key = cls + '.' + method
                if module in expected and key in expected[module]:
                    results.setdefault(module + '/' + key, []).append(status)
            if match := PIXELS.search(line): pixels.append(match.groups())
            for name in ['SHIPPING_COMPANION_NAVIGATION', 'SHIPPING_COMPANION_RETURN']:
                if line.startswith(name + ' '): navigation.add(name)
    missing = {module+'/'+name: results.get(module+'/'+name, []) for module, cases in expected.items() for name in cases if results.get(module+'/'+name) != ['passed']}
    checks = {'every_required_case_executed_once_and_passed': not missing}
    if fixture is not None:
        expected_hashes = tuple(fixture[k] for k in ['sha256', 'sourceSHA256', 'renderedSHA256'])
        historical_strict = len(pixels) == 1 and pixels[0][:3] == expected_hashes and int(pixels[0][3]) <= 2
        if platform_contract:
            from platform_rendering_contract import from_log
            contract=from_log(Path(log).read_text(),fixture)
            component_deltas=re.findall(r'^MAC_LAYER_UIKIT_COMPOSITOR_COMPONENT name=([\w-]+) nativeSHA256=([0-9a-f]{64}) maximumChannelDifference=(\d+)$',Path(log).read_text(),re.M)
            historical_strict=historical_strict and len(component_deltas)==4 and all(int(row[2])<=2 for row in component_deltas)
            checks['versioned_per_runtime_platform_contract']=True
            checks['one_bound_historical_diagnostic']=len(pixels)==1 and pixels[0][:3]==expected_hashes and int(pixels[0][3])==contract['historicalFullMaximum']
        else:checks['one_source_bound_strict_pixel_oracle']=historical_strict
    if require_navigation:
        checks['shipping_entry_and_return_executed'] = navigation == {'SHIPPING_COMPANION_NAVIGATION', 'SHIPPING_COMPANION_RETURN'}
    return {'historical_strict_pixel_passed': historical_strict if fixture is not None else None, 'platform_contract': contract if fixture is not None and platform_contract else None, 'checks': checks, 'expected_count': sum(map(len, expected.values())), 'results': results, 'missing_failed_skipped_or_duplicate': missing, 'pixel_markers': pixels, 'shipping_markers': sorted(navigation), 'log_sha256': digest.hexdigest()}

def verify(scope, log, fixtures, source_sha, platform_contract=False, runtime_summary=None, expected_device=None):
    fixture = None
    if scope == 'mac':
        # Counts and archive/source/rendered hashes are checked before handing off.
        filters = json.loads(from_log(log, source_sha))
        layer = json.loads(layer_from_log(log, source_sha))
    else:
        layer = load_layer_exact(fixtures, source_sha)
        fixture = layer['fixture']
    report = inspect(log, required(scope), fixture, scope == 'phone', platform_contract)
    if platform_contract and scope!='mac':
        from consumer_runtime_binding import validate as validate_runtime,validate_raw_execution
        report['runtime_binding']=validate_runtime(runtime_summary,report['platform_contract'],expected_device)
        report['raw_execution_accounting']=validate_raw_execution(Path(log).read_text(),runtime_summary)
        report['renderer_consumer_passed']=True
        report['aggregate_execution_passed']=report['runtime_binding']['aggregate_execution_passed']
        report['checks']['actual_finalized_runtime_profile_bound']=True
    report.update(source_sha=source_sha, scope=scope, required_consumer_skip_is_failure=True,
                  layer_archive_sha256=layer['fixture']['sha256'], manufactured_layer_fixture_count=1)
    if scope == 'mac':
        report.update(filter_fixture_count=len(filters['fixtures']), baked_fallback_fixture_count=1)
        if platform_contract:
            from platform_rendering_contract import native_from_log
            report['native_text_contract']=native_from_log(Path(log).read_text(),layer['fixture'])
            report['checks']['independent_native_text_contract']=True
    return report

def main():
    parser = argparse.ArgumentParser(); parser.add_argument('scope', choices=['mac', 'phone', 'uikit']); parser.add_argument('--platform-contract',action='store_true'); parser.add_argument('--log', type=Path, required=True); parser.add_argument('--fixtures', type=Path); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--result-bundle',type=Path)
    parser.add_argument('--runtime-evidence',type=Path)
    parser.add_argument('--device-id-file',type=Path)
    parser.add_argument('--expected-model')
    args = parser.parse_args()
    try:
        summary=None;expected_device=None
        if args.platform_contract and args.scope!='mac':
            from native_process import run
            from platform_rendering_contract import require,unique
            require(args.result_bundle is not None and args.result_bundle.is_dir() and not args.result_bundle.is_symlink(),'Missing actual result bundle')
            actual=run(['xcrun','xcresulttool','get','test-results','summary','--path',args.result_bundle],timeout=30,echo=False)
            summary=json.loads(actual.stdout,object_pairs_hook=unique)
            args.output.with_name(args.output.stem+'.runtime-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
            if args.runtime_evidence is not None:
                require(args.device_id_file is None and args.expected_model is None,'Ambiguous owned-device source')
                require(args.scope=='phone' and args.runtime_evidence.is_file() and not args.runtime_evidence.is_symlink() and args.runtime_evidence.stat().st_size<=2_000_000,'Invalid phone ownership evidence')
                owned=json.loads(args.runtime_evidence.read_text(),object_pairs_hook=unique)
                require(owned['head']==os.environ['GITHUB_SHA'] and owned['shipping_entry'] is True,'Wrong phone source/product ownership')
                expected_device={'id':owned['udid'],'model':owned['device_type']['name']}
            else:
                require(args.scope=='uikit' and args.device_id_file is not None and args.device_id_file.is_file() and not args.device_id_file.is_symlink() and args.device_id_file.stat().st_size<=100,'Missing owned UIKit simulator ID')
                expected_device={'id':args.device_id_file.read_text().strip(),'model':args.expected_model}
        report=verify(args.scope,args.log,args.fixtures,os.environ['GITHUB_SHA'],args.platform_contract,runtime_summary=summary,expected_device=expected_device)
    except Exception as error:
        report = {'source_sha': os.environ.get('GITHUB_SHA'), 'scope': args.scope, 'checks': {'required_interoperability': False}, 'error': str(error)}
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print('REQUIRED_INTEROPERABILITY ' + json.dumps(report, sort_keys=True))
    if not all(report['checks'].values()) or report.get('aggregate_execution_passed') is False: raise SystemExit('Required or enclosing execution failed; scoped renderer evidence never makes a failed aggregate green')

if __name__ == '__main__': main()
