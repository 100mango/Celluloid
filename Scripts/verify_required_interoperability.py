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
        assert len(cases) == 33
        return {'CelluloidMacPhotosExtensionTests': cases}
    if scope == 'phone':
        hosted = source_cases(sorted((ROOT/'Platforms/PhoneTests').glob('*.swift'))) + [CONSUMER]
        ui = source_cases(sorted((ROOT/'Platforms/PhoneUITests').glob('*.swift')))
        assert len(hosted) == 14 and len(ui) == 2
        return {'CelluloidCompanionTests': hosted, 'CelluloidCompanionUITests': ui}
    return {'CelluloidTests': [CONSUMER]}

def inspect(log, expected, fixture=None, require_navigation=False):
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
        checks['one_source_bound_strict_pixel_oracle'] = len(pixels) == 1 and pixels[0][:3] == expected_hashes and int(pixels[0][3]) <= 2
    if require_navigation:
        checks['shipping_entry_and_return_executed'] = navigation == {'SHIPPING_COMPANION_NAVIGATION', 'SHIPPING_COMPANION_RETURN'}
    return {'checks': checks, 'expected_count': sum(map(len, expected.values())), 'results': results, 'missing_failed_skipped_or_duplicate': missing, 'pixel_markers': pixels, 'shipping_markers': sorted(navigation), 'log_sha256': digest.hexdigest()}

def verify(scope, log, fixtures, source_sha):
    fixture = None
    if scope == 'mac':
        # Counts and archive/source/rendered hashes are checked before handing off.
        filters = json.loads(from_log(log, source_sha))
        layer = json.loads(layer_from_log(log, source_sha))
    else:
        layer = load_layer_exact(fixtures, source_sha)
        fixture = layer['fixture']
    report = inspect(log, required(scope), fixture, scope == 'phone')
    report.update(source_sha=source_sha, scope=scope, required_consumer_skip_is_failure=True,
                  layer_archive_sha256=layer['fixture']['sha256'], manufactured_layer_fixture_count=1)
    if scope == 'mac': report.update(filter_fixture_count=len(filters['fixtures']), baked_fallback_fixture_count=1)
    return report

def main():
    parser = argparse.ArgumentParser(); parser.add_argument('scope', choices=['mac', 'phone', 'uikit']); parser.add_argument('--log', type=Path, required=True); parser.add_argument('--fixtures', type=Path); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try: report = verify(args.scope, args.log, args.fixtures, os.environ['GITHUB_SHA'])
    except Exception as error:
        report = {'source_sha': os.environ.get('GITHUB_SHA'), 'scope': args.scope, 'checks': {'required_interoperability': False}, 'error': str(error)}
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print('REQUIRED_INTEROPERABILITY ' + json.dumps(report, sort_keys=True))
    if not all(report['checks'].values()): raise SystemExit('Required producer/consumer execution failed; a skipped consumer is not parity')

if __name__ == '__main__': main()
