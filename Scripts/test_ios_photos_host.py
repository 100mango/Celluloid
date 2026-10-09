import copy
import json
import unittest
import tempfile
from pathlib import Path
import run_ios_photos_host as host

class IOSPhotosHostContractTests(unittest.TestCase):
    def setUp(self):
        self.owner = dict(source_sha='a' * 40, device_id='owned-device', run_id='123', run_attempt='1')
        fixtures = [dict(identifier='fixture-' + str(i), filename=('celluloid-fixture-2.png' if i == 1 else 'fixture-' + str(i) + '.png'),
                         width=640, height=480, sha256='b' * 64) for i in range(6)]
        self.manifest = dict(schema='celluloid.swiftui.seeded-library.v1', **self.owner,
            authorization_read_write='authorized', fixture_count=6, fixtures=fixtures,
            baseline_asset_ids=['stock-a', 'stock-b'], added_asset_ids=[f['identifier'] for f in fixtures],
            seeded_asset_ids=['stock-a', 'stock-b'] + [f['identifier'] for f in fixtures],
            baseline_asset_count=2, seeded_asset_count=8)

    def testExactExistingFixtureIsBoundAndStockIsNeverSelected(self):
        context = host.make_context(self.manifest, self.owner)
        self.assertEqual(context['asset_identifier'], 'fixture-1')
        self.assertNotIn(context['asset_identifier'], self.manifest['baseline_asset_ids'])
        self.assertEqual(context['fixture_sha256'], 'b' * 64)
        self.assertTrue(context['album_title'].startswith('Celluloid Host '))

    def testWrongSourceDeviceOrRunFailsBeforeHost(self):
        for key in ['source_sha', 'device_id', 'run_id', 'run_attempt']:
            value = copy.deepcopy(self.manifest); value[key] = 'different'
            with self.assertRaises(ValueError): host.make_context(value, self.owner)

    def testMissingGrantAndWrongSchemaFailBeforeHost(self):
        for key, value in [('authorization_read_write', 'limited'), ('schema', 'unknown')]:
            item = copy.deepcopy(self.manifest); item[key] = value
            with self.assertRaises(ValueError): host.make_context(item, self.owner)

    def testStockDeletionOrUnexpectedAdditionalAssetFails(self):
        for identifiers in [self.manifest['seeded_asset_ids'][1:], self.manifest['seeded_asset_ids'] + ['unexpected']]:
            value = copy.deepcopy(self.manifest); value['seeded_asset_ids'] = identifiers
            with self.assertRaises(ValueError): host.make_context(value, self.owner)

    def testDuplicateTargetFilenameOrWrongHashFails(self):
        value = copy.deepcopy(self.manifest); value['fixtures'][2]['filename'] = 'celluloid-fixture-2.png'
        with self.assertRaises(ValueError): host.make_context(value, self.owner)
        value = copy.deepcopy(self.manifest); value['fixtures'][1]['sha256'] = 'not-a-digest'
        with self.assertRaises(ValueError): host.make_context(value, self.owner)

    def testChangedCountOrFixtureIdentityFails(self):
        value = copy.deepcopy(self.manifest); value['baseline_asset_count'] = 0
        with self.assertRaises(ValueError): host.make_context(value, self.owner)
        value = copy.deepcopy(self.manifest); value['fixtures'][1]['identifier'] = 'stock-a'
        with self.assertRaises(ValueError): host.make_context(value, self.owner)

    def testPhaseContextCannotChangeOriginalOrIdentity(self):
        expected = host.make_context(self.manifest, self.owner)
        host.check_context(dict(expected, before={}), expected)
        for key in ['asset_identifier', 'source_sha', 'context_token', 'fixture_sha256']:
            actual = dict(expected); actual[key] = 'changed'
            with self.assertRaises(ValueError): host.check_context(actual, expected)

    def testMissingOrDuplicateNativeEventCannotPass(self):
        prefix = 'IOS_PHOTOS_HOST_UI '
        self.assertEqual(host.record(prefix + '{"event":"save"}', prefix), {'event': 'save'})
        for log in ['', prefix + '{}\n' + prefix + '{}']:
            with self.assertRaises(ValueError): host.record(log, prefix)

    def testRealSummaryParsingRejectsMissingOrDuplicateResult(self):
        summary = dict(totalTestCount=1, result='Passed')
        self.assertEqual(host.summary_json('preamble\n' + json.dumps(summary, indent=2)), summary)
        for log in ['{}', json.dumps(summary) + '\n' + json.dumps(summary)]:
            with self.assertRaises(ValueError): host.summary_json(log)

    def testFiveExplicitNativeMethodsWithinCommandCeilings(self):
        self.assertEqual(len(host.STEPS), 5)
        self.assertEqual(sum('/IOSPhotosHostUITests/' in row[1] for row in host.STEPS), 2)
        self.assertTrue(all(0 < row[2] <= 180 for row in host.STEPS))
        self.assertLessEqual(sum(row[2] + 15 for row in host.STEPS) + 15, 600)

    def testProductControlBindsBothFileNamesAndExactContents(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'Celluloid').mkdir()
            path = root / 'Celluloid/View.swift'; path.write_text('original')
            before = host.product_control(root)
            path.write_text('changed'); self.assertNotEqual(host.product_control(root), before)
            path.write_text('original'); self.assertEqual(host.product_control(root), before)
            path.rename(root / 'Celluloid/Other.swift'); self.assertNotEqual(host.product_control(root), before)

    def testNativeWatchdogAndOwnedProcessTimeoutBothBlockFurtherSimulatorWork(self):
        for code, log in [(124, ''), (65, 'Test exceeded execution time allowance'),
                          (65, 'Test execution timed out'), (1, 'CLEANUP_UNCONFIRMED')]:
            self.assertTrue(host.native_uncertain(code, log))
        self.assertFalse(host.native_uncertain(65, 'Assertion failed: expected public control missing'))

    def testDedicatedBranchRequiresExplicitOwnerRouteWithoutChangingOldDefault(self):
        from swiftui_photos_gate import validate_owner
        identifier = '12345678-1234-1234-1234-123456789AB0'
        runtime = 'com.apple.CoreSimulator.SimRuntime.iOS-27-0'
        receipt = dict(self.owner, device_id=identifier, schema='celluloid.swiftui.owned-simulator.v1',
            device_name='Celluloid iOS27 test', runtime_id=runtime, created_by_this_job=True, absent_before_create=True)
        environment = dict(GITHUB_SHA=self.owner['source_sha'], GITHUB_WORKFLOW_SHA=self.owner['source_sha'],
            GITHUB_REPOSITORY='100mango/Celluloid', GITHUB_REF='refs/heads/cell-ios-photos-host-final',
            GITHUB_EVENT_NAME='push', GITHUB_RUN_ID='123', GITHUB_RUN_ATTEMPT='1')
        observed = {'devices': {runtime: [dict(udid=identifier, name=receipt['device_name'], state='Booted', isAvailable=True)]}}
        with self.assertRaises(ValueError): validate_owner(receipt, identifier, environment, observed)
        validate_owner(receipt, identifier, environment, observed, expected_ref=environment['GITHUB_REF'])
        for route in ['refs/heads/unknown', 'refs/heads/swiftui-first-native']:
            with self.assertRaises(ValueError): validate_owner(receipt, identifier, environment, observed, expected_ref=route)
        environment['GITHUB_REF'] = 'refs/heads/swiftui-first-native'
        validate_owner(receipt, identifier, environment, observed)


# Source contract for the narrowly observed iOS 27 informational sheet. These
# portable checks reject broadening the test automation; they do not replace
# the pending native Photos-host run or establish XCTest hittability.
NOTICE_TITLE = "What’s New in Photos"
NOTICE_SECTIONS = [
    "Improved Shared Albums, Share photos and videos in their original resolution with all of your friends and family, even if they don’t have an Apple device.",
    "New Ways to Organize, Quickly locate photos with Captured by Me and Identity Documents in Utilities. Use star ratings and keywords to mark your best shots.",
    "New Ways to Enjoy, Play a selection of photos and videos as a slideshow, and save the best frame of a video as a still photo."
]

def validate_observed_notice_source(source):
    begin = source.index('    private func dismissObservedWhatsNewIfPresent() throws {')
    end = source.index('    private func verifyPublicFilename() throws {', begin)
    helper = source[begin:end]
    required = [
        'let title = photos.staticTexts.matching(NSPredicate(format: "label == %@", "' + NOTICE_TITLE + '"))',
        'guard title.count > 0 else { return }',
        'guard photos.alerts.count == 0,',
        'XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts.count == 0 else {',
        '_ = try unique(title)',
        *['"' + section + '"' for section in NOTICE_SECTIONS],
        'let section = photos.otherElements.matching(NSPredicate(format: "label == %@", label))',
        'guard section.count == 1, section.element.isHittable else {',
        'let proceed = try unique(photos.buttons.matching(NSPredicate(format: "label == %@", "Continue")))',
        'checkpoint("observed-photos-whats-new")',
        'proceed.tap()',
        'object: title.element)], timeout: 8) == .completed else {'
    ]
    previous = -1
    for fragment in required:
        if helper.count(fragment) != 1:
            raise ValueError('Missing or repeated observed-page guard: ' + fragment)
        index = helper.index(fragment)
        if index <= previous:
            raise ValueError('An action or check precedes its required guard')
        previous = index
    if helper.count('.tap()') != 1:
        raise ValueError('Unexpected additional introduction action')
    if source.count('        try dismissObservedWhatsNewIfPresent()') != 1:
        raise ValueError('Observed introduction may only be handled after Collections')
    sequence = 'checkpoint("collections")\n        try dismissObservedWhatsNewIfPresent()\n        stage = "open-albums"'
    if sequence not in source:
        raise ValueError('Observed introduction handler moved out of the observed route')
    for required_budget in ['executionTimeAllowance = 120', 'systemUptime - started < 120']:
        if required_budget not in source:
            raise ValueError('Original UI case budget changed')

class IOSPhotosObservedNoticeSourceTests(unittest.TestCase):
    def setUp(self):
        self.source = (Path(__file__).resolve().parents[1] / 'CelluloidUITests/IOSPhotosHostUITests.swift').read_text()

    def testExactObservedNoticeIsTheOnlyAllowedIntroduction(self):
        validate_observed_notice_source(self.source)

    def testTitleEveryBodySectionOrContinueMismatchCannotAuthorizeTap(self):
        for label in [NOTICE_TITLE, *NOTICE_SECTIONS, 'Continue']:
            with self.subTest(label=label):
                changed = self.source.replace('"' + label + '"', '"unrecognized page content"')
                with self.assertRaises(ValueError): validate_observed_notice_source(changed)

    def testPhotosOrSpringBoardAlertCannotAuthorizeTap(self):
        for guard in ['guard photos.alerts.count == 0,',
                      'XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts.count == 0 else {']:
            with self.subTest(guard=guard):
                with self.assertRaises(ValueError):
                    validate_observed_notice_source(self.source.replace(guard, guard.replace('== 0', '>= 0')))

    def testTapCannotPrecedeIdentityChecksOrAcceptAmbiguousControls(self):
        mutants = [
            self.source.replace('        proceed.tap()\n', '').replace('        let observedSections = [', '        proceed.tap()\n        let observedSections = ['),
            self.source.replace('guard section.count == 1,', 'guard section.count > 0,'),
            self.source.replace('let proceed = try unique(photos.buttons.matching', 'let proceed = photos.buttons.matching'),
            self.source.replace('        proceed.tap()\n', '        proceed.tap()\n        proceed.tap()\n')
        ]
        for changed in mutants:
            with self.assertRaises(ValueError): validate_observed_notice_source(changed)

if __name__ == '__main__': unittest.main()
