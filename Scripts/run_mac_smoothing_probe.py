#!/usr/bin/env python3
"""Bounded smoothing experiment. A completed diagnostic is NEVER a parity pass.

The original strict runner and native original-2x assertions are unchanged. This
successor retains their expected failure and always exits nonzero: only the
separate diagnostic_complete field can say the experiment finished correctly.
"""
from pathlib import Path
import base64
import json
import os
import re
import subprocess
import sys
import time

from native_process import run
from native_fixture_handoff import validate_layer
from platform_rendering_contract import control_bytes, validate_archive_fixture, native_from_log
from run_mac_parity_probe import CASES, SELECTORS, unique, integer, require, sha, save

ROOT = Path(__file__).resolve().parents[1]
PARENT = 'a5a7987cc35f8a7eeff7576a38b6f2ec73386d6e'
PARENT_TREE = 'fdf12e57efd2c4f0c5693cbb87b5a6b8b31d523a'
BASE = '9c85361da5fd26ac63a43c12813171c185928e1f'
BASE_TREE = '281e8d7763cb1b36a6d6422a90c735e6c6d712c6'
BRANCH = 'refs/heads/cell-mac-smoothing-probe'
ALLOWED = {
    '.github/workflows/mac-smoothing-probe.yml',
    'Scripts/run_mac_smoothing_probe.py',
    'Scripts/test_mac_smoothing_probe.py',
    'Scripts/generate_native_project.py',
    'CelluloidNative.xcodeproj/project.pbxproj',
    'Platforms/macOSExtension/MacPhotoRenderer.swift',
    'Platforms/MacExtensionTests/MacPhotoAdjustmentTests.swift',
    'Platforms/MacExtensionTests/Fixtures/original-uikit-2x-backing.json',
}
PREFIX = 'MAC_SMOOTHING_PROBE '
ORIGINAL_PREFIX = 'MAC_ORIGINAL_2X_PROBE '
LAYER_PREFIX = 'MAC_LAYER_ADJUSTMENT_FIXTURE '
WORK_SECONDS = 900
TEST_LOG_LIMIT = 2_000_000
EVIDENCE_LIMIT = 4_000_000
COMPONENTS = ['full', 'filtered-base', 'bubble-artwork', 'sticker-artwork', 'all-artwork']
KNOWN_DEFAULT = {
    'full': ([129, 130, 130, 0], 985, [210, 290, 273, 343]),
    'filtered-base': ([0, 0, 0, 0], 0, [480, 640, -1, -1]),
    'bubble-artwork': ([5, 5, 6, 0], 7, [210, 308, 211, 315]),
    'sticker-artwork': ([0, 0, 0, 0], 0, [480, 640, -1, -1]),
    'all-artwork': ([5, 5, 6, 0], 7, [210, 308, 211, 315]),
}


def admit_identity(source, parents, parent_tree, grandparents, base_tree, changes, environment):
    require(isinstance(source, str) and re.fullmatch('[0-9a-f]{40}', source) is not None,
            'Invalid current source')
    require(parents == [source, PARENT] and parent_tree == PARENT_TREE,
            'Not the exact single-parent smoothing successor')
    require(grandparents == [PARENT, BASE] and base_tree == BASE_TREE,
            'Wrong original product-base ancestry')
    require(set(changes) == ALLOWED and len(changes) == len(ALLOWED), 'Unexpected successor source delta')
    require(environment.get('GITHUB_REPOSITORY') == '100mango/Celluloid'
            and environment.get('GITHUB_REF') == BRANCH
            and environment.get('GITHUB_EVENT_NAME') == 'push'
            and environment.get('GITHUB_WORKFLOW_SHA') == source
            and environment.get('GITHUB_SHA') == source,
            'Wrong source-bound workflow route')


def case_events(log):
    events = list(re.finditer(
        r"^Test Case '-\[([^\]]+)\]' (started\.|(?:passed|failed|skipped) \([0-9]+(?:\.[0-9]+)? seconds\)\.)$",
        log, re.M))
    case_lines = [line for line in log.splitlines() if line.lstrip().lower().startswith('test case ')]
    require(len(case_lines) == len(events), 'Malformed or unknown raw XCTest event')
    expected = ['CelluloidMacPhotosExtensionTests.' + case.replace('.', ' ', 1) for case in CASES]
    require([(event[1], event[2].split()[0].rstrip('.')) for event in events] == [
        (expected[0], 'started'), (expected[0], 'failed'),
        (expected[1], 'started'), (expected[1], 'passed')],
        'Required first-failed/second-passed native cases did not run exactly once in order')
    return events


def enclosed_record(log, prefix, maximum):
    events = case_events(log)
    matches = list(re.finditer('^' + re.escape(prefix) + r'([^\n]*)$', log, re.M))
    candidate_lines = [line for line in log.splitlines() if line.lstrip().startswith(prefix.strip())]
    require(len(matches) == len(candidate_lines) == 1, 'Missing/duplicate/malformed record: ' + prefix.strip())
    match = matches[0]
    require(len(match[0].encode()) <= maximum, 'Oversized record: ' + prefix.strip())
    require(events[0].end() < match.start() < events[1].start(),
            'Diagnostic record was not emitted inside the first selected XCTest')
    return json.loads(match[1], object_pairs_hook=unique)


def validate_metric(maxima, maximum, count, bounds, width=480, height=640):
    require(isinstance(maxima, list) and len(maxima) == 4 and all(integer(x, 255) for x in maxima),
            'Invalid RGBA channel maxima')
    require(integer(maximum, 255) and maximum == max(maxima), 'Inconsistent maximum')
    require(integer(count, width * height), 'Invalid pixel coverage')
    require(isinstance(bounds, list) and len(bounds) == 4 and all(type(x) is int for x in bounds),
            'Invalid difference bounds')
    if count == 0:
        require(bounds == [width, height, -1, -1] and maximum <= 2,
                'Inconsistent empty pixel coverage')
    else:
        x0, y0, x1, y1 = bounds
        require(maximum > 2 and 0 <= x0 <= x1 < width and 0 <= y0 <= y1 < height
                and count <= (x1 - x0 + 1) * (y1 - y0 + 1), 'Inconsistent nonempty pixel coverage')


def validate_original(record, fixture):
    """Validate the retained known failed control; do not call it a parity pass."""
    validate_layer(fixture)
    controls = json.loads(control_bytes(), object_pairs_hook=unique)
    keys = {'schema', 'scope', 'controlFileSHA256', 'controlSourceSHA', 'controlProfile',
            'controlRuntime', 'controlBuild', 'archiveSHA256', 'controlArchiveSHA256',
            'sourcePNG_SHA256', 'actualPNG_SHA256', 'comparisons', 'layeredPhotosOutputQualified'}
    require(isinstance(record, dict) and set(record) == keys, 'Unknown/missing original probe fields')
    expected = {
        'schema': 'Celluloid.MacOriginal2xProbe.1', 'scope': 'synthetic-pre-host-only',
        'controlFileSHA256': sha(control_bytes()), 'controlSourceSHA': controls['sourceSHA'],
        'controlProfile': '2x', 'controlRuntime': '27.0', 'controlBuild': '24A434',
        'archiveSHA256': fixture['sha256'], 'controlArchiveSHA256': controls['archiveSHA256'],
        'sourcePNG_SHA256': fixture['sourceSHA256'], 'actualPNG_SHA256': fixture['renderedSHA256'],
    }
    for key, value in expected.items():
        require(record.get(key) == value, 'Original probe binding mismatch: ' + key)
    require(record['layeredPhotosOutputQualified'] is False, 'Diagnostic cannot qualify Photos output')
    require(fixture['sourceSHA256'] == controls['sourcePNG_SHA256'], 'Wrong original source image')
    graph = validate_archive_fixture(fixture, controls)
    actual = {'full': fixture['renderedSHA256'], **{c['name']: c['sha256'] for c in fixture['components']}}
    rows = record['comparisons']
    require(isinstance(rows, list) and all(isinstance(row, dict) for row in rows)
            and [row.get('name') for row in rows] == COMPONENTS, 'Missing/duplicate/reordered original component')
    for row in rows:
        require(set(row) == {'name', 'actualPNG_SHA256', 'originalPNG_SHA256', 'maximumChannelDifference',
                'allowedMaximum', 'channelMaximumsRGBA', 'pixelsAboveTwo', 'boundsAboveTwo'},
                'Unknown original comparison fields')
        name = row['name']
        original = controls['profiles']['2x']['images'].get(name) or controls['common'][name]
        require(row['actualPNG_SHA256'] == actual[name] and row['originalPNG_SHA256'] == original['sha256'],
                'Wrong original comparison image identity')
        limit = 0 if name in ('filtered-base', 'sticker-artwork') else 2
        require(type(row['allowedMaximum']) is int and row['allowedMaximum'] == limit,
                'Original strict pixel threshold changed')
        validate_metric(row['channelMaximumsRGBA'], row['maximumChannelDifference'],
                        row['pixelsAboveTwo'], row['boundsAboveTwo'])
        maxima, count, bounds = KNOWN_DEFAULT[name]
        require(row['channelMaximumsRGBA'] == maxima and row['pixelsAboveTwo'] == count
                and row['boundsAboveTwo'] == bounds, 'Default control changed beyond the known strict failure: ' + name)
    return graph


def known_failure_texts():
    return [f'XCTAssertLessThanOrEqual failed: ("{max(KNOWN_DEFAULT[name][0])}") is greater than ("2") - '
            f'Current Mac output differs from immutable original UIKit 2x: {name}'
            for name in ['full', 'bubble-artwork', 'all-artwork']]


def validate_summary(summary, log, native_exit_code):
    require(type(native_exit_code) is int and native_exit_code == 65,
            'The selected native run did not retain its expected strict XCTest failure exit')
    expected_counts = {'totalTestCount': 2, 'passedTests': 1, 'failedTests': 1, 'skippedTests': 0, 'expectedFailures': 0}
    for key, value in expected_counts.items():
        require(type(summary.get(key)) is int and summary[key] == value, 'Unexpected official summary: ' + key)
    require(summary.get('result') == 'Failed' and summary.get('runtimeWarnings') == [],
            'Unexpected official outcome or runtime warnings')
    devices = summary.get('devicesAndConfigurations')
    require(isinstance(devices, list) and len(devices) == 1 and isinstance(devices[0], dict),
            'Missing/duplicate native device summary')
    device = devices[0].get('device', {})
    require(device.get('platform') == 'macOS' and device.get('architecture') == 'arm64',
            'Wrong actual native execution platform')
    for key, value in expected_counts.items():
        if key != 'totalTestCount':
            require(type(devices[0].get(key)) is int and devices[0][key] == value,
                    'Contradictory device summary: ' + key)
    known = known_failure_texts()
    failures = summary.get('testFailures')
    require(isinstance(failures, list) and 1 <= len(failures) <= len(known)
            and all(isinstance(f, dict) for f in failures), 'Missing/extra official failure')
    texts = []
    for failure in failures:
        require(failure.get('targetName') == 'CelluloidMacPhotosExtensionTests'
                and failure.get('testIdentifierString') == CASES[0].replace('.', '/') + '()'
                and failure.get('testName') == CASES[0].split('.')[1] + '()'
                and failure.get('failureText') in known, 'Unknown official XCTest failure')
        texts.append(failure['failureText'])
    require(known[0] in texts and len(texts) == len(set(texts)), 'Duplicate/missing known official full failure')
    events = case_events(log)
    owner = 'CelluloidMacPhotosExtensionTests.' + CASES[0].replace('.', ' ', 1)
    errors = []
    pattern = re.compile(r'^.*/Platforms/MacExtensionTests/MacPhotoAdjustmentTests\.swift:[1-9][0-9]*: error: -\['
                         + re.escape(owner) + r'\] : (.*)$')
    for line in log.splitlines():
        if re.search(r'error:|XCTAssert\w* failed|caught error|failed - |Test Failure|unexpected exception', line, re.I):
            match = pattern.fullmatch(line)
            require(match is not None and match[1] in known, 'Additional/unrecognized raw native failure')
            offset = log.find(line)
            require(events[0].end() < offset < events[1].start(), 'Strict failure outside first selected case')
            errors.append(match[1])
    require(errors == known, 'Missing/duplicate/reordered strict control assertions')
    terminals = re.findall(r'^\*\* TEST(?: EXECUTE)? (SUCCEEDED|FAILED) \*\*$', log, re.M)
    require(terminals == ['FAILED'], 'Missing/contradictory failed xcodebuild terminal')
    require(not re.search(r'Publishing changes from within view updates|Modifying state during view update|'
                          r'AddressSanitizer|ThreadSanitizer|runtime warning|warning:', log, re.I),
            'Native runtime warning or sanitizer failure')

BACKING_PATH = ROOT / 'Platforms/MacExtensionTests/Fixtures/original-uikit-2x-backing.json'
BACKING_FILE_SHA = 'e2f7b7c4fa0cee8d866c7a3475b052fa5ab6328c31b95465ae5c170a31fc0bdf'
BACKING_PNG_SHA = 'f867ce60c648fde2e504a0d7afd181ada660a2fcc3e4e3327b7cc9a5077d4958'
RECTS = {'full': [0, 0, 480, 640], 'backing-all': [0, 0, 56, 88],
         'latin': [0, 0, 56, 34], 'cjk': [0, 34, 56, 21], 'emoji': [0, 55, 56, 33]}
LAYOUT = {'textRect': [77.231, 26.24, 27.875, 43.52], 'fontSize': 10,
          'lineHeight': 12, 'naturalBlockHeight': 36, 'frameAllocationHeight': 37, 'backingScale': 2}


def png_blob(blob, width, height, maximum_bytes=150_000):
    require(isinstance(blob, dict) and set(blob) == {'sha256', 'base64'}, 'Unknown/missing image fields')
    require(all(isinstance(value, str) for value in blob.values()), 'Wrong image field types')
    require(re.fullmatch('[0-9a-f]{64}', blob['sha256']) is not None
            and len(blob['base64']) <= ((maximum_bytes + 2) // 3) * 4, 'Invalid/oversized image encoding')
    data = base64.b64decode(blob['base64'], validate=True)
    require(0 < len(data) <= maximum_bytes and sha(data) == blob['sha256'], 'Image byte/hash mismatch')
    require(len(data) >= 33 and data[:8] == b'\x89PNG\r\n\x1a\n' and data[12:16] == b'IHDR'
            and (int.from_bytes(data[16:20], 'big'), int.from_bytes(data[20:24], 'big')) == (width, height),
            'Wrong diagnostic PNG dimensions or type')
    return data


def backing_control():
    require(BACKING_PATH.is_file() and not BACKING_PATH.is_symlink(), 'Missing immutable UIKit backing fixture')
    raw = BACKING_PATH.read_bytes()
    require(0 < len(raw) <= 50_000 and sha(raw) == BACKING_FILE_SHA, 'Original UIKit backing fixture changed')
    record = json.loads(raw, object_pairs_hook=unique)
    require(record.get('schema') == 'Celluloid.OriginalUIKitTextBacking.1', 'Wrong backing fixture schema')
    image = record.get('image', {})
    require(set(image) == {'width', 'height', 'scale', 'padding', 'pngSHA256', 'pngBase64'}
            and [image.get(key) for key in ['width', 'height', 'scale', 'padding']] == [56, 88, 2, 0]
            and image['pngSHA256'] == BACKING_PNG_SHA, 'Wrong original backing identity')
    png_blob({'sha256': image['pngSHA256'], 'base64': image['pngBase64']}, 56, 88, 50_000)
    controls = json.loads(control_bytes(), object_pairs_hook=unique)
    require(record.get('archiveSHA256') == controls['archiveSHA256']
            and record.get('provenance', {}).get('sourceSHA') == controls['sourceSHA']
            and record['provenance'].get('originalControlPacketSHA256') == sha(control_bytes()),
            'Original backing is not bound to the frozen original control')
    return record


def finite_number(value, minimum=-10000, maximum=10000):
    import math
    return type(value) in (int, float) and math.isfinite(value) and minimum <= value <= maximum


def validate_fonts(fonts):
    require(isinstance(fonts, list) and 1 <= len(fonts) <= 64, 'Missing/excessive font runs')
    for row in fonts:
        require(isinstance(row, dict) and set(row) == {'font', 'size', 'version', 'glyphs', 'positions',
                                                      'sourceRange', 'textMatrix'}, 'Unknown/missing actual-font metadata')
        require(isinstance(row['font'], str) and 0 < len(row['font']) <= 256
                and isinstance(row['version'], str) and 0 < len(row['version']) <= 512,
                'Missing/oversized font identity')
        require(finite_number(row['size'], 10, 10), 'Diagnostic changed the fixed 10-point font size')
        glyphs = row['glyphs']
        require(isinstance(glyphs, list) and 1 <= len(glyphs) <= 128
                and all(integer(glyph, 65535) for glyph in glyphs), 'Invalid font glyph run')
        positions = row['positions']
        require(isinstance(positions, list) and len(positions) == len(glyphs)
                and all(isinstance(p, list) and len(p) == 2 and all(finite_number(v) for v in p) for p in positions),
                'Invalid font glyph positions')
        source_range = row['sourceRange']
        require(isinstance(source_range, list) and len(source_range) == 2
                and all(integer(v, 128) for v in source_range) and source_range[1] > 0,
                'Invalid font source range')
        require(isinstance(row['textMatrix'], list) and len(row['textMatrix']) == 6
                and all(finite_number(v) for v in row['textMatrix']), 'Invalid font text matrix')


def validate_smoothing(record, fixture, original):
    keys = {'schema', 'scope', 'archiveSHA256', 'sourcePNG_SHA256', 'controlFileSHA256',
            'originalBackingFixtureSHA256', 'originalBackingPNG_SHA256', 'layout', 'fonts', 'variants',
            'defaultRestoredPNG_SHA256', 'diagnosticScopeRestored', 'layeredPhotosOutputQualified'}
    require(isinstance(record, dict) and set(record) == keys, 'Unknown/missing smoothing probe fields')
    for key, expected in {
        'schema': 'Celluloid.MacSmoothingProbe.1', 'scope': 'synthetic-pre-host-only',
        'archiveSHA256': fixture['sha256'], 'sourcePNG_SHA256': fixture['sourceSHA256'],
        'controlFileSHA256': sha(control_bytes()), 'originalBackingFixtureSHA256': BACKING_FILE_SHA,
        'originalBackingPNG_SHA256': BACKING_PNG_SHA,
        'defaultRestoredPNG_SHA256': fixture['renderedSHA256'],
    }.items():
        require(record.get(key) == expected, 'Smoothing probe binding mismatch: ' + key)
    backing_control()  # Hash binds the complete original observation and its provenance.
    require(record['diagnosticScopeRestored'] is True and record['layeredPhotosOutputQualified'] is False,
            'Smoothing scope was not restored or diagnostic claims Photos qualification')
    layout = record['layout']
    require(isinstance(layout, dict) and set(layout) == set(LAYOUT), 'Unknown/missing fixed text layout')
    for key, expected in LAYOUT.items():
        actual = layout[key]
        if isinstance(expected, list):
            require(isinstance(actual, list) and len(actual) == len(expected)
                    and all(finite_number(a) and abs(a - b) <= 1e-6 for a, b in zip(actual, expected)),
                    'Fixed text geometry changed: ' + key)
        else:
            require(finite_number(actual) and abs(actual - expected) <= 1e-6, 'Fixed text layout changed: ' + key)
    validate_fonts(record['fonts'])
    variants = record['variants']
    require(isinstance(variants, list) and len(variants) == 2
            and all(isinstance(v, dict) for v in variants)
            and [v.get('name') for v in variants] == ['default', 'smoothing-disabled'],
            'Missing/duplicate/reordered smoothing variants')
    for variant in variants:
        require(set(variant) == {'name', 'full', 'backing', 'comparisons'}, 'Unknown variant fields')
        png_blob(variant['full'], 480, 640)
        png_blob(variant['backing'], 56, 88, 50_000)
        if variant['name'] == 'default':
            require(variant['full']['sha256'] == fixture['renderedSHA256']
                    and variant['full']['base64'] == fixture['renderedBase64'], 'Default full image changed')
        rows = variant['comparisons']
        require(isinstance(rows, list) and all(isinstance(row, dict) for row in rows)
                and [row.get('name') for row in rows] == list(RECTS), 'Missing/duplicate/reordered comparison regions')
        for row in rows:
            require(set(row) == {'name', 'rect', 'maximumChannelDifference', 'channelMaximumsRGBA',
                                'pixelsAboveTwo', 'boundsAboveTwo'}, 'Unknown comparison region fields')
            name = row['name']
            require(row['rect'] == RECTS[name] and all(type(x) is int for x in row['rect']), 'Changed comparison region')
            width, height = (480, 640) if name == 'full' else (56, 88)
            validate_metric(row['channelMaximumsRGBA'], row['maximumChannelDifference'],
                            row['pixelsAboveTwo'], row['boundsAboveTwo'], width, height)
            x, y, w, h = row['rect']
            require(row['pixelsAboveTwo'] <= w * h, 'Region count exceeds region area')
            if row['pixelsAboveTwo']:
                x0, y0, x1, y1 = row['boundsAboveTwo']
                require(x <= x0 <= x1 < x + w and y <= y0 <= y1 < y + h, 'Bounds escape comparison region')
            if variant['name'] == 'default' and name == 'full':
                control = original['comparisons'][0]
                for key in ['maximumChannelDifference', 'channelMaximumsRGBA', 'pixelsAboveTwo', 'boundsAboveTwo']:
                    require(row[key] == control[key], 'Default full comparison differs from strict original probe: ' + key)
        whole = rows[1]
        parts = rows[2:]
        require(whole['pixelsAboveTwo'] == sum(part['pixelsAboveTwo'] for part in parts),
                'Text region counts do not reconstruct whole backing')
        require(whole['channelMaximumsRGBA'] == [max(part['channelMaximumsRGBA'][i] for part in parts) for i in range(4)],
                'Text region maxima do not reconstruct whole backing')
        nonempty = [part['boundsAboveTwo'] for part in parts if part['pixelsAboveTwo']]
        union = ([min(b[0] for b in nonempty), min(b[1] for b in nonempty),
                  max(b[2] for b in nonempty), max(b[3] for b in nonempty)] if nonempty else [56, 88, -1, -1])
        require(whole['boundsAboveTwo'] == union, 'Text region bounds do not reconstruct whole backing')
    return record


def validate_backing_observation(log, fixture, smoothing):
    """Bind the default variant to the pre-existing actual-backing observation."""
    prefix = 'CELLULOID_TEXT_OBSERVATION '
    candidates = []
    for match in re.finditer('^' + re.escape(prefix) + r'([^\n]*)$', log, re.M):
        require(len(match[0].encode()) <= 100_000, 'Oversized text observation')
        record = json.loads(match[1], object_pairs_hook=unique)
        require(isinstance(record, dict), 'Malformed text observation')
        if record.get('kind') == 'actual-native-coretext-backing':
            candidates.append((match, record))
    require(len(candidates) == 1, 'Missing/duplicate actual default backing observation')
    match, record = candidates[0]
    events = case_events(log)
    require(events[0].end() < match.start() < events[1].start(), 'Actual backing observation outside first selected test')
    require(set(record) == {'schema', 'kind', 'archiveSHA256', 'scale', 'padding', 'width', 'height',
                           'logicalBounds', 'text', 'pngSHA256', 'pngBase64', 'scope'},
            'Unknown/missing actual backing observation fields')
    require(record['schema'] == 'Celluloid.TextObservation.1' and record['archiveSHA256'] == fixture['sha256']
            and record['text'] == 'Hello, 世界 🎬', 'Actual backing observation source mismatch')
    for key, expected in [('scale', 2), ('padding', 0), ('width', 56), ('height', 88)]:
        require(type(record[key]) is int and record[key] == expected, 'Actual backing observation geometry changed')
    bounds = re.fullmatch(r'\{([0-9.]+), ([0-9.]+)\}', record['logicalBounds']) if isinstance(record['logicalBounds'], str) else None
    require(bounds is not None and abs(float(bounds[1]) - 27.875) <= 1e-6
            and abs(float(bounds[2]) - 43.52) <= 1e-6, 'Actual backing logical bounds changed')
    observed = {'sha256': record['pngSHA256'], 'base64': record['pngBase64']}
    png_blob(observed, 56, 88, 50_000)
    require(observed == smoothing['variants'][0]['backing'], 'Default variant is not the actual pre-existing production backing')
    return record


def retain_diagnostic_records(out, log, source):
    """Retain independently parsed evidence even if another record is invalid."""
    records = {}
    errors = []
    for key, prefix, limit, filename in [
        ('fixture', LAYER_PREFIX, 500_000, 'mac-layer-fixture.json'),
        ('original', ORIGINAL_PREFIX, 16_384, 'original-2x-probe.json'),
        ('smoothing', PREFIX, 100_030, 'smoothing-probe.json'),
    ]:
        try:
            record = enclosed_record(log, prefix, limit)
            if key == 'fixture':
                validate_layer(record)
                save(out / filename, {'schema': 'Celluloid.SyntheticMacLayerFixture.1',
                                      'source_sha': source, 'fixture': record})
            else:
                save(out / filename, record)
            records[key] = record
        except (ValueError, TypeError, KeyError) as error:
            errors.append(prefix.strip() + ': ' + str(error))
    require(not errors, '; '.join(errors))
    return records


def finish_evidence(out, report):
    # File handling only: callers may reach this after an uncertain native timeout.
    for path in out.glob('*.log'):
        cap = TEST_LOG_LIMIT if path.name == 'tests.log' else 300_000
        if path.stat().st_size > cap:
            data = path.read_bytes()
            path.write_bytes(data[-cap:])
            report.setdefault('truncated_logs', []).append(path.name)
            if path.name == 'tests.log':
                report['diagnostic_complete'] = False
                report['error'] = 'Required test log exceeded evidence budget'
    def write_inventory():
        save(out / 'result.json', report)
        files = [{'name': p.name, 'bytes': p.stat().st_size, 'sha256': sha(p.read_bytes())}
                 for p in sorted(out.iterdir()) if p.is_file() and p.name != 'manifest.json']
        save(out / 'manifest.json', {
            'source_sha': report['source_sha'], 'files': files, 'maximum_bytes': EVIDENCE_LIMIT,
            'scope': 'diagnostic-only', 'parity_passed': False, 'release_qualification': False,
            'photos_host_qualification': False,
        })

    write_inventory()
    total = lambda: sum(p.stat().st_size for p in out.iterdir() if p.is_file())
    if total() > EVIDENCE_LIMIT:
        report['diagnostic_complete'] = False
        report['error'] = 'Evidence exceeded fixed 4MB budget; incomplete evidence was discarded'
        # Preserve test log and source identity where possible. The uploaded directory,
        # including its manifest, must obey the budget even on a fail-closed error.
        candidates = sorted((p for p in out.iterdir() if p.is_file()
                             and p.name not in {'result.json', 'manifest.json', 'source-binding.json', 'build-binding.json', 'summary.json'}),
                            key=lambda p: (p.name == 'tests.log', p.suffix != '.log', -p.stat().st_size))
        for path in candidates:
            if total() <= EVIDENCE_LIMIT - 16_384:
                break
            report.setdefault('discarded_evidence_files', []).append(path.name)
            path.unlink()
        write_inventory()
    require(total() <= EVIDENCE_LIMIT, 'Source identity and result exceed fixed 4MB evidence budget')


def main():
    os.chdir(ROOT)
    started = time.monotonic()
    deadline = started + WORK_SECONDS
    temp = Path(os.environ['RUNNER_TEMP'])
    out = temp / 'cell-mac-smoothing-evidence'
    out.mkdir(exist_ok=False)
    derived = temp / 'cell-mac-smoothing-derived'
    result = temp / 'CelluloidMacSmoothing.xcresult'
    source = os.environ.get('GITHUB_SHA', '')
    report = {
        'schema': 'celluloid.mac-smoothing-run.v1', 'source_sha': source, 'parent_sha': PARENT,
        'parent_tree': PARENT_TREE, 'base_sha': BASE, 'base_tree': BASE_TREE,
        'selectors': SELECTORS, 'work_budget_seconds': WORK_SECONDS, 'diagnostic_complete': False,
        'parity_passed': False, 'accepted': False, 'release_qualification': False,
        'photos_host_qualification': False, 'signing': False, 'simulators_used': False, 'events': [],
    }
    failure = None
    source_hashes = None

    def git(*args):
        remaining = deadline - time.monotonic()
        require(remaining > 1, 'Internal work allowance exhausted')
        return subprocess.check_output(['git', *args], text=True, timeout=min(15, remaining)).strip()

    def clean():
        require(git('diff', '--name-only', 'HEAD', '--') == '', 'Tracked source changed during diagnostic')

    def command(name, args, cap, check=True):
        require(time.monotonic() + cap + 30 <= deadline, 'Insufficient bounded work allowance: ' + name)
        before = time.monotonic()
        try:
            completed = run(args, timeout=cap, check=False,
                            log_name='cell-mac-smoothing-evidence/' + name + '.log', echo=False)
        except BaseException:
            report['events'].append({'phase': name, 'completed': False, 'elapsed_seconds': time.monotonic() - before})
            raise  # No more processes after uncertain native timeout or interruption.
        report['events'].append({'phase': name, 'completed': True, 'exit_code': completed.returncode,
                                 'elapsed_seconds': time.monotonic() - before})
        require(not check or completed.returncode == 0, name + ' failed')
        return completed

    try:
        require(sys.platform == 'darwin', 'Requires approved Xcode 27 cloud executor')
        require(os.environ.get('DEVELOPER_DIR') == '/Applications/Xcode_27.app/Contents/Developer', 'Wrong toolchain route')
        require(not derived.exists() and not result.exists(), 'Refusing reused native outputs')
        require(git('rev-parse', 'HEAD') == source, 'Checkout source mismatch')
        admit_identity(source, git('rev-list', '--parents', '-n', '1', 'HEAD').split(),
                       git('rev-parse', PARENT + '^{tree}'), git('rev-list', '--parents', '-n', '1', PARENT).split(),
                       git('rev-parse', BASE + '^{tree}'), git('diff', '--name-only', PARENT, 'HEAD', '--').splitlines(), os.environ)
        clean()
        report['source_tree'] = git('rev-parse', 'HEAD^{tree}')
        source_hashes = {path: sha((ROOT / path).read_bytes()) for path in git('ls-files', '-z').split('\0') if path}
        report['tracked_source_fingerprint'] = sha(json.dumps(source_hashes, sort_keys=True, separators=(',', ':')).encode())
        report['run_id'] = os.environ.get('GITHUB_RUN_ID')
        report['run_attempt'] = os.environ.get('GITHUB_RUN_ATTEMPT')
        require(all(re.fullmatch('[1-9][0-9]*', report[k] or '') for k in ['run_id', 'run_attempt']), 'Missing workflow identity')
        backing_control()
        save(out / 'source-binding.json', report)
        version = command('toolchain', ['xcodebuild', '-version'], 20).stdout
        require('Xcode 27.0' in version.splitlines(), 'Wrong stable Xcode version')
        command('os-version', ['sw_vers'], 10)
        common = ['xcodebuild', '-project', 'CelluloidNative.xcodeproj', '-scheme', 'CelluloidMacPhotosExtension',
                  '-configuration', 'Debug', '-destination', 'platform=macOS,arch=arm64', '-derivedDataPath', str(derived),
                  'CODE_SIGNING_ALLOWED=NO', 'CODE_SIGNING_REQUIRED=NO', 'CODE_SIGN_IDENTITY=', 'COMPILER_INDEX_STORE_ENABLE=NO']
        command('build', [*common, '-jobs', '2', 'build-for-testing'], 600)
        binary = derived / 'Build/Products/Debug/CelluloidMacPhotosExtensionTests.xctest/Contents/MacOS/CelluloidMacPhotosExtensionTests'
        require(binary.is_file() and not binary.is_symlink(), 'Missing exact test product')
        report['test_binary_sha256'] = sha(binary.read_bytes())
        save(out / 'build-binding.json', report)
        tested = command('tests', [*common, '-parallel-testing-enabled', 'NO', '-collect-test-diagnostics', 'never',
                                  '-resultBundlePath', str(result), *['-only-testing:' + s for s in SELECTORS],
                                  'test-without-building'], 180, False)
        report['native_test_exit_code'] = tested.returncode
        # Failed native execution does not prevent retaining its diagnostic JSON.
        # Summary is the final native command; no extra Photos/simulator/host work.
        summary_result = command('summary', ['xcrun', 'xcresulttool', 'get', 'test-results', 'summary', '--path', str(result)], 30)
        require(len(summary_result.stdout.encode()) <= 300_000, 'Oversized official XCTest summary')
        summary = json.loads(summary_result.stdout, object_pairs_hook=unique)
        save(out / 'summary.json', summary)
        require((out / 'tests.log').stat().st_size <= TEST_LOG_LIMIT, 'Required test log exceeds 2MB budget')
        log = (out / 'tests.log').read_text()
        records = retain_diagnostic_records(out, log, source)
        validate_summary(summary, log, tested.returncode)
        graph = validate_original(records['original'], records['fixture'])
        save(out / 'archive-graph-proof.json', graph)
        validate_smoothing(records['smoothing'], records['fixture'], records['original'])
        save(out / 'default-backing-observation.json', validate_backing_observation(log, records['fixture'], records['smoothing']))
        save(out / 'native-text-contract.json', native_from_log(log, records['fixture']))
        require(sha(binary.read_bytes()) == report['test_binary_sha256'], 'Test product changed during execution')
        clean()
        require(time.monotonic() <= deadline, 'Internal diagnostic allowance exhausted')
        report['diagnostic_complete'] = True
        report['expected_strict_default_failure_only'] = True
        report['outcome'] = 'diagnostic_complete_strict_default_parity_failed'
    except BaseException as error:
        failure = type(error).__name__ + ': ' + str(error)
    finally:
        report['error'] = failure
        report['elapsed_seconds'] = time.monotonic() - started
        if source_hashes is not None:
            report['tracked_source_unchanged'] = all((ROOT / path).is_file() and not (ROOT / path).is_symlink()
                                                    and sha((ROOT / path).read_bytes()) == digest
                                                    for path, digest in source_hashes.items())
            if not report['tracked_source_unchanged']:
                report['diagnostic_complete'] = False
                report['error'] = 'Tracked source changed during native execution'
        finish_evidence(out, report)
    print(json.dumps(report, sort_keys=True))
    return 1  # Deliberate: diagnostic completion cannot turn known strict parity failure green.


if __name__ == '__main__':
    raise SystemExit(main())
