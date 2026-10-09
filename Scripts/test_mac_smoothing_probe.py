#!/usr/bin/env python3
"""Portable fail-closed contract tests; synthetic records are never native evidence."""
import base64
import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock
import zlib

import run_mac_smoothing_probe as probe
import test_mac_parity_probe as parity_tests
from test_native_text_release_guard import release_projection


class MacSmoothingProbeTests(unittest.TestCase):
    def fixture(self):
        original, fixture = parity_tests.MacParityProbeTests().fixture()
        # These are parser-unit-test records, not a claim about the PNG pixels.
        for row in original['comparisons']:
            maxima, count, bounds = probe.KNOWN_DEFAULT[row['name']]
            row.update(channelMaximumsRGBA=list(maxima), maximumChannelDifference=max(maxima),
                       pixelsAboveTwo=count, boundsAboveTwo=list(bounds))
        return original, fixture

    def record(self):
        original, fixture = self.fixture()
        # A valid tiny transparent PNG tests shape/hash validation without dependencies.
        def chunk(kind, data):
            return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data))
        data = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!IIBBBBB', 56, 88, 8, 6, 0, 0, 0))
                + chunk(b'IDAT', zlib.compress((b'\0' + b'\0' * 56 * 4) * 88)) + chunk(b'IEND', b''))
        backing = {'sha256': probe.sha(data), 'base64': base64.b64encode(data).decode()}
        full = {'sha256': fixture['renderedSHA256'], 'base64': fixture['renderedBase64']}
        rows = []
        for name, rect in probe.RECTS.items():
            maxima, count, bounds = probe.KNOWN_DEFAULT['full'] if name == 'full' else ([0, 0, 0, 0], 0, [56, 88, -1, -1])
            rows.append({'name': name, 'rect': list(rect), 'channelMaximumsRGBA': list(maxima),
                         'maximumChannelDifference': max(maxima), 'pixelsAboveTwo': count, 'boundsAboveTwo': list(bounds)})
        record = {
            'schema': 'Celluloid.MacSmoothingProbe.1', 'scope': 'synthetic-pre-host-only',
            'archiveSHA256': fixture['sha256'], 'sourcePNG_SHA256': fixture['sourceSHA256'],
            'controlFileSHA256': probe.sha(probe.control_bytes()), 'originalBackingFixtureSHA256': probe.BACKING_FILE_SHA,
            'originalBackingPNG_SHA256': probe.BACKING_PNG_SHA, 'layout': copy.deepcopy(probe.LAYOUT),
            'fonts': [{'font': '.SFNS-Regular', 'size': 10, 'version': 'unavailable', 'glyphs': [112],
                       'positions': [[0, 13.76]], 'sourceRange': [0, 1], 'textMatrix': [1, 0, 0, -1, 0, 0]}],
            'variants': [{'name': name, 'full': copy.deepcopy(full), 'backing': copy.deepcopy(backing),
                          'comparisons': copy.deepcopy(rows)} for name in ['default', 'smoothing-disabled']],
            'defaultRestoredPNG_SHA256': fixture['renderedSHA256'], 'diagnosticScopeRestored': True,
            'layeredPhotosOutputQualified': False,
        }
        return record, fixture, original

    def validate_record(self, record, fixture, original):
        # Immutable on-disk fixture validation has its own unmocked test below.
        with mock.patch.object(probe, 'backing_control', return_value={}):
            return probe.validate_smoothing(record, fixture, original)

    def summary(self):
        failure = {'failureText': probe.known_failure_texts()[0], 'targetName': 'CelluloidMacPhotosExtensionTests',
                   'testIdentifierString': probe.CASES[0].replace('.', '/') + '()',
                   'testName': probe.CASES[0].split('.')[1] + '()'}
        return {'totalTestCount': 2, 'passedTests': 1, 'failedTests': 1, 'skippedTests': 0, 'expectedFailures': 0,
                'result': 'Failed', 'testFailures': [failure], 'runtimeWarnings': [],
                'devicesAndConfigurations': [{'device': {'platform': 'macOS', 'architecture': 'arm64'},
                                             'passedTests': 1, 'failedTests': 1, 'skippedTests': 0, 'expectedFailures': 0}]}

    def log(self, record=None):
        owners = ['CelluloidMacPhotosExtensionTests.' + case.replace('.', ' ', 1) for case in probe.CASES]
        lines = [f"Test Case '-[{owners[0]}]' started."]
        if record is not None:
            lines.append(probe.PREFIX + json.dumps(record, separators=(',', ':')))
        lines += [f'/checkout/Platforms/MacExtensionTests/MacPhotoAdjustmentTests.swift:310: error: -[{owners[0]}] : {text}'
                  for text in probe.known_failure_texts()]
        lines += [f"Test Case '-[{owners[0]}]' failed (0.1 seconds).",
                  f"Test Case '-[{owners[1]}]' started.", f"Test Case '-[{owners[1]}]' passed (0.2 seconds).",
                  '** TEST EXECUTE FAILED **']
        return '\n'.join(lines)

    def test_known_failure_remains_failure_and_completed_diagnostic_is_valid(self):
        probe.validate_summary(self.summary(), self.log(), 65)
        original, fixture = self.fixture()
        self.assertTrue(probe.validate_original(original, fixture))
        record, fixture, original = self.record()
        self.assertEqual(self.validate_record(record, fixture, original), record)

    def test_exact_parent_tree_grandparent_and_eight_file_delta(self):
        source = 'a' * 40
        environment = {'GITHUB_REPOSITORY': '100mango/Celluloid', 'GITHUB_REF': probe.BRANCH,
                       'GITHUB_EVENT_NAME': 'push', 'GITHUB_WORKFLOW_SHA': source, 'GITHUB_SHA': source}
        args = [source, [source, probe.PARENT], probe.PARENT_TREE, [probe.PARENT, probe.BASE],
                probe.BASE_TREE, sorted(probe.ALLOWED), environment]
        probe.admit_identity(*args)
        for index, bad in [(1, [source, probe.BASE]), (1, [source, probe.PARENT, probe.BASE]),
                           (2, '0' * 40), (3, [probe.PARENT, '0' * 40]), (4, '0' * 40),
                           (5, sorted(probe.ALLOWED)[:-1]), (5, sorted(probe.ALLOWED) + ['unexpected.swift']),
                           (5, sorted(probe.ALLOWED) + [sorted(probe.ALLOWED)[0]])]:
            changed = copy.deepcopy(args); changed[index] = bad
            with self.subTest(index=index, bad=bad), self.assertRaises(ValueError):
                probe.admit_identity(*changed)
        for key in environment:
            changed = copy.deepcopy(args); changed[6][key] = 'invalid'
            with self.subTest(environment=key), self.assertRaises(ValueError):
                probe.admit_identity(*changed)

    def test_rejects_unexpected_official_outcome(self):
        for key, bad in [('totalTestCount', 3), ('passedTests', 2), ('failedTests', 0), ('skippedTests', 1),
                         ('expectedFailures', 1), ('result', 'Passed'), ('runtimeWarnings', [{'message': 'warning'}]),
                         ('passedTests', True), ('testFailures', [])]:
            summary = self.summary(); summary[key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError):
                probe.validate_summary(summary, self.log(), 65)
        for code in [0, 1, 66, -9, True]:
            with self.subTest(code=code), self.assertRaises(ValueError):
                probe.validate_summary(self.summary(), self.log(), code)

    def test_rejects_extra_or_misattributed_official_failure(self):
        for key, bad in [('failureText', 'Something else failed'), ('targetName', 'OtherTests'),
                         ('testIdentifierString', probe.CASES[1].replace('.', '/') + '()'), ('testName', 'other()')]:
            summary = self.summary(); summary['testFailures'][0][key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError):
                probe.validate_summary(summary, self.log(), 65)
        summary = self.summary(); summary['testFailures'] *= 2
        with self.assertRaises(ValueError): probe.validate_summary(summary, self.log(), 65)

    def test_all_three_official_known_assertions_may_be_reported(self):
        summary = self.summary()
        summary['testFailures'] = [dict(summary['testFailures'][0], failureText=text) for text in probe.known_failure_texts()]
        probe.validate_summary(summary, self.log(), 65)

    def test_rejects_wrong_platform_and_contradictory_device_totals(self):
        for key, bad in [('platform', 'iOS Simulator'), ('architecture', 'x86_64')]:
            summary = self.summary(); summary['devicesAndConfigurations'][0]['device'][key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError):
                probe.validate_summary(summary, self.log(), 65)
        summary = self.summary(); summary['devicesAndConfigurations'][0]['passedTests'] = 2
        with self.assertRaises(ValueError): probe.validate_summary(summary, self.log(), 65)

    def test_rejects_missing_duplicate_or_extra_raw_failures(self):
        log = self.log()
        for bad in [log.replace(probe.known_failure_texts()[1], 'Additional native assertion failed'),
                    log.replace('("130")', '("131")'),
                    '\n'.join(line for line in log.splitlines() if 'all-artwork' not in line),
                    log + '\n' + next(line for line in log.splitlines() if 'error:' in line),
                    log + '\nerror: unrelated runtime exception',
                    log + '\nXCTAssertTrue failed', log + '\nPublishing changes from within view updates',
                    log + '\nThreadSanitizer warning', log + '\nwarning: runtime failure']:
            with self.subTest(log=bad[-120:]), self.assertRaises(ValueError):
                probe.validate_summary(self.summary(), bad, 65)

    def test_rejects_missing_duplicate_reordered_raw_tests_or_terminal(self):
        log = self.log()
        for bad in [log + '\n' + log, log.replace(' failed (', ' passed ('),
                    log.replace(' passed (', ' skipped ('), log.replace('** TEST EXECUTE FAILED **', ''),
                    log + '\n** TEST SUCCEEDED **', log.replace('Test Case ', ' Test Case ', 1),
                    '\n'.join(reversed(log.splitlines()))]:
            with self.subTest(log=bad[-100:]), self.assertRaises(ValueError):
                probe.validate_summary(self.summary(), bad, 65)

    def test_diagnostic_must_be_enclosed_in_failed_first_case(self):
        record, _, _ = self.record()
        log = self.log(record)
        self.assertEqual(probe.enclosed_record(log, probe.PREFIX, 100_030), record)
        line = next(line for line in log.splitlines() if line.startswith(probe.PREFIX))
        for bad in [log + '\n' + line, log.replace(line, '') + '\n' + line,
                    log.replace(line, ' ' + line), log.replace(line, probe.PREFIX + '{"a":1,"a":2}')]:
            with self.subTest(log=bad[-80:]), self.assertRaises(ValueError):
                probe.enclosed_record(bad, probe.PREFIX, 100_030)
        with self.assertRaises(ValueError): probe.enclosed_record(log, probe.PREFIX, 10)

    def test_default_backing_is_bound_to_existing_actual_observation(self):
        record, fixture, _ = self.record()
        backing = record['variants'][0]['backing']
        observation = {'schema': 'Celluloid.TextObservation.1', 'kind': 'actual-native-coretext-backing',
                       'archiveSHA256': fixture['sha256'], 'scale': 2, 'padding': 0, 'width': 56, 'height': 88,
                       'logicalBounds': '{27.874999999999996, 43.520000000000003}', 'text': 'Hello, 世界 🎬',
                       'pngSHA256': backing['sha256'], 'pngBase64': backing['base64'],
                       'scope': 'Actual candidate backing before affine mapping; not independent expected output'}
        line = 'CELLULOID_TEXT_OBSERVATION ' + json.dumps(observation)
        log = self.log(record).replace(probe.PREFIX, line + '\n' + probe.PREFIX, 1)
        self.assertEqual(probe.validate_backing_observation(log, fixture, record), observation)
        for bad in [log + '\n' + line, log.replace(line, '') + '\n' + line,
                    log.replace(line, line.replace(backing['sha256'], '0' * 64)),
                    log.replace(line, line.replace('"width": 56', '"width": 55'))]:
            with self.assertRaises(ValueError): probe.validate_backing_observation(bad, fixture, record)
        changed = copy.deepcopy(record); changed['variants'][0]['backing']['sha256'] = '0' * 64
        with self.assertRaises(ValueError): probe.validate_backing_observation(log, fixture, changed)

    def test_original_control_thresholds_and_baseline_metrics_cannot_change(self):
        for field, value in [('allowedMaximum', 130), ('maximumChannelDifference', 131),
                             ('channelMaximumsRGBA', [129, 130, 131, 0]), ('pixelsAboveTwo', 986),
                             ('boundsAboveTwo', [210, 290, 274, 343]), ('actualPNG_SHA256', '0' * 64)]:
            original, fixture = self.fixture(); original['comparisons'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): probe.validate_original(original, fixture)
        original, fixture = self.fixture(); original['comparisons'][1]['allowedMaximum'] = 2
        with self.assertRaises(ValueError): probe.validate_original(original, fixture)

    def test_immutable_backing_file_and_png_are_bound(self):
        control = probe.backing_control()
        self.assertEqual(control['image']['pngSHA256'], probe.BACKING_PNG_SHA)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'backing.json'; path.write_text('{}')
            with mock.patch.object(probe, 'BACKING_PATH', path), self.assertRaises(ValueError): probe.backing_control()

    def test_smoothing_provenance_restore_and_qualification_fail_closed(self):
        for field, value in [('archiveSHA256', '0' * 64), ('sourcePNG_SHA256', '0' * 64),
                             ('controlFileSHA256', '0' * 64), ('originalBackingFixtureSHA256', '0' * 64),
                             ('originalBackingPNG_SHA256', '0' * 64), ('defaultRestoredPNG_SHA256', '0' * 64),
                             ('diagnosticScopeRestored', False), ('diagnosticScopeRestored', 1),
                             ('layeredPhotosOutputQualified', True), ('layeredPhotosOutputQualified', 0),
                             ('schema', 'Other.1'), ('extra', False)]:
            record, fixture, original = self.record(); record[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): self.validate_record(record, fixture, original)

    def test_same_font_layout_is_required_and_finite(self):
        for field, value in [('fontSize', 11), ('backingScale', 3), ('lineHeight', 11.9),
                             ('textRect', [77.231, 26.24, 28, 44]), ('naturalBlockHeight', float('nan'))]:
            record, fixture, original = self.record(); record['layout'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): self.validate_record(record, fixture, original)
        for field, value in [('size', 11), ('glyphs', [True]), ('positions', [[float('inf'), 0]]),
                             ('sourceRange', [0, 0]), ('textMatrix', [1] * 5), ('font', ''), ('version', '')]:
            record, fixture, original = self.record(); record['fonts'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): self.validate_record(record, fixture, original)

    def test_variant_images_are_hash_size_and_order_bound(self):
        for field, value in [('sha256', '0' * 64), ('base64', 'malformed')]:
            record, fixture, original = self.record(); record['variants'][1]['full'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): self.validate_record(record, fixture, original)
        record, fixture, original = self.record(); record['variants'][1]['backing'] = record['variants'][1]['full']
        with self.assertRaises(ValueError): self.validate_record(record, fixture, original)
        for mutation in [lambda variants: variants.reverse(), lambda variants: variants.pop(),
                         lambda variants: variants.append(copy.deepcopy(variants[0]))]:
            record, fixture, original = self.record(); mutation(record['variants'])
            with self.assertRaises(ValueError): self.validate_record(record, fixture, original)

    def test_metrics_bounds_counts_and_partitions_are_consistent(self):
        for field, value in [('maximumChannelDifference', 256), ('channelMaximumsRGBA', [1, 2, 3]),
                             ('pixelsAboveTwo', True), ('boundsAboveTwo', [0, 0, 0, 0]),
                             ('rect', [0, 0, 56, 88]), ('extra', 1)]:
            record, fixture, original = self.record(); record['variants'][1]['comparisons'][2][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): self.validate_record(record, fixture, original)
        record, fixture, original = self.record()
        row = record['variants'][1]['comparisons'][2]
        row.update(maximumChannelDifference=4, channelMaximumsRGBA=[4, 0, 0, 0], pixelsAboveTwo=1, boundsAboveTwo=[1, 1, 1, 1])
        with self.assertRaises(ValueError): self.validate_record(record, fixture, original)

    def test_disabled_metrics_need_not_pass_strict_original_control(self):
        record, fixture, original = self.record()
        row = record['variants'][1]['comparisons'][0]
        row.update(maximumChannelDifference=255, channelMaximumsRGBA=[255, 0, 0, 0], pixelsAboveTwo=1, boundsAboveTwo=[1, 1, 1, 1])
        # Even a worse disabled result completes the experiment, never qualifies parity.
        self.validate_record(record, fixture, original)

    def test_renderer_release_projection_is_exact_parent(self):
        source = (probe.ROOT / 'Platforms/macOSExtension/MacPhotoRenderer.swift').read_text()
        projected = release_projection(source)
        self.assertEqual(probe.sha(projected.encode()), '77278ad4cfaef4e7ee5dd8cd17d8a6ccc55bc5d9753aff9c4c687ac6a0e30e34')
        self.assertIn('@TaskLocal static var diagnosticDisableFontSmoothing = false', source)
        self.assertNotIn('diagnosticDisableFontSmoothing', projected)
        self.assertNotIn('setAllowsFontSmoothing', projected)
        self.assertNotIn('setShouldSmoothFonts', projected)

    def test_workflow_route_and_fixed_resource_budgets(self):
        workflow = (probe.ROOT / '.github/workflows/mac-smoothing-probe.yml').read_text()
        for value in ['branches: [cell-mac-smoothing-probe]', 'contents: read', 'runs-on: xcode-27',
                      'timeout-minutes: 20', 'fetch-depth: 3', 'persist-credentials: false', 'if: always()',
                      'actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1',
                      'actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a']:
            self.assertIn(value, workflow)
        self.assertNotIn('continue-on-error', workflow)
        self.assertEqual(probe.WORK_SECONDS, 900)
        self.assertEqual(probe.TEST_LOG_LIMIT, 2_000_000)
        self.assertEqual(probe.EVIDENCE_LIMIT, 4_000_000)
        self.assertEqual(len(probe.SELECTORS), 2)

    def test_evidence_manifest_counts_its_own_bytes_and_clips_test_log_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            report = {'source_sha': 'a' * 40, 'diagnostic_complete': True, 'error': None}
            (out / 'tests.log').write_bytes(b'x' * (probe.TEST_LOG_LIMIT + 1))
            probe.finish_evidence(out, report)
            self.assertFalse(report['diagnostic_complete'])
            self.assertEqual((out / 'tests.log').stat().st_size, probe.TEST_LOG_LIMIT)
            self.assertLessEqual(sum(path.stat().st_size for path in out.iterdir()), probe.EVIDENCE_LIMIT)
            manifest = json.loads((out / 'manifest.json').read_text())
            self.assertIs(manifest['parity_passed'], False)
            self.assertIs(manifest['release_qualification'], False)
            self.assertIs(manifest['photos_host_qualification'], False)


    def test_total_artifact_overflow_discards_evidence_and_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            report = {'source_sha': 'a' * 40, 'diagnostic_complete': True, 'error': None}
            (out / 'excess.json').write_bytes(b'x' * (probe.EVIDENCE_LIMIT + 1))
            probe.finish_evidence(out, report)
            self.assertFalse(report['diagnostic_complete'])
            self.assertIn('excess.json', report['discarded_evidence_files'])
            self.assertFalse((out / 'excess.json').exists())
            self.assertLessEqual(sum(path.stat().st_size for path in out.iterdir()), probe.EVIDENCE_LIMIT)
            manifest = json.loads((out / 'manifest.json').read_text())
            self.assertNotIn('excess.json', [entry['name'] for entry in manifest['files']])


if __name__ == '__main__':
    unittest.main()
