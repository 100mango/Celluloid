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


class PhotosParentDeadlineTests(unittest.TestCase):
    def bounded(self, mode, expired=False, wrong_route=False):
        import contextlib,io,os,runpy,subprocess,sys
        from unittest.mock import MagicMock,patch
        root=Path(__file__).resolve().parents[1];clock=[3.0 if expired else 1.0]
        process=MagicMock(pid=12345,returncode=None if mode=='denied' else 0)
        def create(*args,**kwargs):
            if mode=='slow-start':clock[0]=3.0
            return process
        def wait(*args,**kwargs):
            if mode=='denied':raise subprocess.TimeoutExpired('owned',1)
            if mode=='late-zero':clock[0]=3.0
            return 0
        process.wait.side_effect=wait;process.poll.return_value=process.returncode
        argv=['run_bounded.py','--seconds','20','--label','photos-unit','--deadline-monotonic','2','owned-fake-command']
        env={'GITHUB_REF':'refs/heads/wrong' if wrong_route else 'refs/heads/cell-ios-photos-host-final','GITHUB_REPOSITORY':'100mango/Celluloid'}
        out=io.StringIO()
        with patch.dict(os.environ,env),patch.object(sys,'argv',argv),patch('time.monotonic',side_effect=lambda:clock[0]),patch('subprocess.Popen',side_effect=create) as opened,patch('os.killpg',side_effect=PermissionError('synthetic denial') if mode=='denied' else None) as killed,contextlib.redirect_stdout(out),contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:runpy.run_path(str(root/'Scripts/run_bounded.py'),run_name='__main__')
        return caught.exception.code,out.getvalue(),opened,process,killed
    def testTimelyOwnedChildSucceedsWithRemainingParentBudget(self):
        code,log,opened,process,killed=self.bounded('timely')
        self.assertEqual(code,0);self.assertEqual(process.wait.call_args.kwargs['timeout'],1)
        self.assertTrue(opened.call_args.kwargs['start_new_session']);killed.assert_not_called()
    def testExpiredParentNeverStartsChildAndWrongRouteCannotUseFlag(self):
        for expired,wrong in [(True,False),(False,True)]:
            code,log,opened,process,killed=self.bounded('timely',expired=expired,wrong_route=wrong)
            self.assertEqual(code,2 if wrong else 124);opened.assert_not_called();killed.assert_not_called()
    def testProcessCreationDelayAndLateExitZeroBothRemainTimeout(self):
        for mode in ['slow-start','late-zero']:
            code,log,opened,process,killed=self.bounded(mode)
            self.assertEqual(code,124);self.assertIn('BOUNDED_COMMAND_TIMEOUT',log)
            self.assertIn('"exit_code": 124',log);killed.assert_not_called()
            if mode=='slow-start':process.wait.assert_not_called()
    def testDeniedOwnedCleanupNeverEscalatesSignalsOrWaitsAgain(self):
        import signal
        code,log,opened,process,killed=self.bounded('denied')
        self.assertEqual(code,124);killed.assert_called_once_with(12345,signal.SIGTERM)
        self.assertEqual(process.wait.call_count,1);self.assertIn('CLEANUP_UNCONFIRMED',log)
    def testFreshQueryKeepsExactCommandAndRejectsLateZeroWithoutRetry(self):
        import os
        from unittest.mock import patch
        import swiftui_photos_gate as gate
        for late in [False,True]:
            with tempfile.TemporaryDirectory() as folder:
                clock=[100.0];calls=[]
                def invoke(command,stdout,stderr):
                    calls.append(command);stdout.write(b'BOUNDED_COMMAND_BEGIN {}\n{"devices": {}}\nBOUNDED_COMMAND_END {}\n');clock[0]+=21 if late else 1;return 0
                with patch.object(gate.time,'monotonic',side_effect=lambda:clock[0]),patch.object(gate.subprocess,'call',side_effect=invoke):
                    if late:
                        with self.assertRaises(ValueError):gate.fresh_owned_device_observation(Path(folder))
                    else:self.assertEqual(gate.fresh_owned_device_observation(Path(folder)),{'devices':{}})
                self.assertEqual(len(calls),1);self.assertEqual(calls[0][-6:],['xcrun','simctl','list','devices','available','-j'])
                self.assertIn('--deadline-monotonic',calls[0]);self.assertEqual(calls[0][calls[0].index('--seconds')+1],'20')
                receipt=json.loads((Path(folder)/'owned-device-observation.json').read_text());self.assertIs(receipt['late_completion'],late);self.assertIs(receipt['prohibit_further_native'],late)
                with self.assertRaisesRegex(ValueError,'stale'):gate.fresh_owned_device_observation(Path(folder))
    def testMissingDuplicateOrFailedFreshQueryCannotSupplyState(self):
        from unittest.mock import patch
        import swiftui_photos_gate as gate
        for raw,code in [(b'{"wrong":{}}',0),(b'{"devices":{}}\n{"devices":{}}',0),(b'BOUNDED_COMMAND_TIMEOUT query',124),(b'BOUNDED_COMMAND_CLEANUP_UNCONFIRMED',0)]:
            with tempfile.TemporaryDirectory() as folder:
                def invoke(command,stdout,stderr):stdout.write(raw);return code
                with patch.object(gate.subprocess,'call',side_effect=invoke) as called,self.assertRaises(ValueError):gate.fresh_owned_device_observation(Path(folder))
                self.assertEqual(called.call_count,1)
    def testLateParentPhaseBlocksEveryFollowingDispatch(self):
        from unittest.mock import patch
        import run_ios_photos_host_diagnostic as diagnostic
        with tempfile.TemporaryDirectory() as folder:
            clock=[100.0];gate=object.__new__(diagnostic.HostDiagnostic);gate.uncertain=False;gate.failures=[];calls=[]
            def invoke(self,*args,**kwargs):calls.append((args,kwargs));clock[0]=177.0164555;return 0,'inner exited0 after60.268 seconds'
            with patch.object(diagnostic,'OUT',Path(folder)),patch.object(diagnostic.time,'monotonic',side_effect=lambda:clock[0]),patch.object(diagnostic.Acceptance,'command',invoke):
                with self.assertRaisesRegex(ValueError,'deadline exceeded'):gate.command('install-owned-app',['xcrun','simctl','install','owned','app'],60,simulator=True)
                self.assertTrue(gate.uncertain)
                with self.assertRaisesRegex(ValueError,'blocks further'):gate.command('photos-bootstrap',['unsafe-following-command'],750,simulator=True)
            self.assertEqual(len(calls),1);self.assertEqual(gate.failures,[{'phase':'install-owned-app','exit_code':124}])
            wrapped=calls[0][0][1];self.assertEqual(wrapped[wrapped.index('--deadline-monotonic')+1],'160.0')
            record=json.loads((Path(folder)/'install-owned-app-dispatch-timing.json').read_text());self.assertEqual(record['returned_exit_code'],0);self.assertTrue(record['late_completion']);self.assertTrue(record['prohibit_further_native'])
    def testOriginalHostStagesAndBudgetsRemainWhileChildHasPreDispatchFence(self):
        root=Path(__file__).resolve().parents[1];source=(root/'Scripts/run_ios_photos_host.py').read_text();driver=(root/'Scripts/run_ios_photos_host_diagnostic.py').read_text()
        self.assertEqual([x[2] for x in host.STEPS],[45,165,45,165,45]);self.assertEqual(len(host.STEPS),5)
        self.assertIn("'photos-bootstrap', command, 750",driver);self.assertIn("'work_budget_seconds': 2280",driver)
        start=source.index('    def run(label, command, seconds, simulator=False):');end=source.index('    try:\n        for stage, selector, seconds in STEPS:',start);body=source[start:end]
        self.assertLess(body.index('require(not uncertain'),body.index('subprocess.call('))
        self.assertIn("'--deadline-monotonic', str(dispatched+seconds)",body);self.assertIn('if late:uncertain=True;code=124',body)
        self.assertIn('observed = fresh_owned_device_observation(output)',source)
        self.assertIn("validate_owner(owner, args.device, os.environ, observed, expected_ref='refs/heads/cell-ios-photos-host-final')",source)

    def testLateCleanupZeroDoesNotDispatchDeleteOrClaimDeviceGone(self):
        from unittest.mock import patch
        import run_ios_photos_host_diagnostic as diagnostic
        with tempfile.TemporaryDirectory() as folder:
            clock=[100.0];gate=object.__new__(diagnostic.HostDiagnostic);gate.started=0;gate.device='owned-device';gate.uncertain=False
            def invoke(command,**kwargs):clock[0]=131.0;return 0
            with patch.object(diagnostic,'OUT',Path(folder)),patch.object(diagnostic.time,'monotonic',side_effect=lambda:clock[0]),patch.object(diagnostic.subprocess,'call',side_effect=invoke) as called:
                gate.cleanup();self.assertEqual(called.call_count,1);self.assertTrue(gate.uncertain);self.assertEqual(gate.device,'owned-device')
                gate.cleanup();self.assertEqual(called.call_count,1)


if __name__ == '__main__': unittest.main()
