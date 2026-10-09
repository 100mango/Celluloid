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
    sequence = 'checkpoint("collections")\n        try dismissObservedWhatsNewIfPresent()\n        try declineObservedPhotosNotificationsIfPresent()\n        try selectObservedCollections()\n        stage = "open-albums"'
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
        process=MagicMock(pid=12345,returncode=None if mode=='denied' or mode.startswith('slow-cleanup') else 0)
        def create(*args,**kwargs):
            if mode=='slow-start':clock[0]=3.0
            return process
        def wait(*args,**kwargs):
            if mode=='slow-cleanup-second-signal' and process.wait.call_count==2:clock[0]+=5.0
            if mode=='denied' or mode.startswith('slow-cleanup'):raise subprocess.TimeoutExpired('owned',1)
            if mode=='late-zero':clock[0]=3.0
            return 0
        process.wait.side_effect=wait;process.poll.return_value=process.returncode
        argv=['run_bounded.py','--seconds','20','--label','photos-unit','--deadline-monotonic','2','owned-fake-command']
        env={'GITHUB_REF':'refs/heads/wrong' if wrong_route else 'refs/heads/cell-ios-photos-host-final','GITHUB_REPOSITORY':'100mango/Celluloid','GITHUB_SHA':'a'*40,'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1'}
        class TimingOutput(io.StringIO):
            def write(self,value):
                if mode=='slow-spawn-receipt' and '"phase": "spawn-begin"' in value:clock[0]=3.0
                if mode=='slow-wait-receipt' and '"phase": "wait-begin"' in value:clock[0]=3.0
                if mode=='slow-cleanup-signal' and '"phase": "cleanup-signal-attempt"' in value:clock[0]=12.0
                if mode=='slow-cleanup-wait' and '"phase": "cleanup-wait-begin"' in value:clock[0]=12.0
                if mode=='slow-cleanup-second-signal' and '"phase": "cleanup-signal-attempt"' in value and '"signal_name": "SIGKILL"' in value:clock[0]=12.0
                return super().write(value)
        out=TimingOutput()
        with patch.dict(os.environ,env),patch.object(sys,'argv',argv),patch('time.monotonic',side_effect=lambda:clock[0]),patch('subprocess.Popen',side_effect=create) as opened,patch('subprocess.run',side_effect=AssertionError('unexpected native query')),patch('os.getpgid',side_effect=AssertionError('unexpected group query')),patch('os.killpg',side_effect=PermissionError('synthetic denial') if mode=='denied' else None) as killed,contextlib.redirect_stdout(out),contextlib.redirect_stderr(io.StringIO()):
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

    def testSplitInstallParentIs210AndStillRejectsLateOrUnfundedWork(self):
        import ast,inspect
        from unittest.mock import patch
        import run_ios_photos_host_diagnostic as diagnostic
        source=inspect.getsource(diagnostic);calls=[n for n in ast.walk(ast.parse(source)) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='command' and n.args and isinstance(n.args[0],ast.Constant) and n.args[0].value=='install-owned-app']
        self.assertEqual(len(calls),1);self.assertEqual(calls[0].args[2].value,210)
        self.assertEqual([x[2] for x in host.STEPS],[45,165,45,165,45])
        for duration in [77.0164555,209.0,210.001]:
            with self.subTest(duration=duration),tempfile.TemporaryDirectory() as folder:
                clock=[100.0];gate=object.__new__(diagnostic.HostDiagnostic);gate.uncertain=False;gate.failures=[];seen=[]
                def invoke(self,*args,**kwargs):seen.append(args);clock[0]+=duration;return 0,'synthetic completion'
                with patch.object(diagnostic,'OUT',Path(folder)),patch.object(diagnostic.time,'monotonic',side_effect=lambda:clock[0]),patch.object(diagnostic.Acceptance,'command',invoke):
                    if duration>210:
                        with self.assertRaisesRegex(ValueError,'deadline exceeded'):gate.command('install-owned-app',['xcrun','simctl','install','owned','app'],210,simulator=True)
                        with self.assertRaisesRegex(ValueError,'blocks further'):gate.command('photos-bootstrap',['must-not-dispatch'],750,simulator=True)
                    else:self.assertEqual(gate.command('install-owned-app',['xcrun','simctl','install','owned','app'],210,simulator=True),(0,'synthetic completion'))
                self.assertEqual(len(seen),1);wrapped=seen[0][1];self.assertEqual(wrapped[wrapped.index('--seconds')+1],'210');self.assertEqual(wrapped[wrapped.index('--deadline-monotonic')+1],'310.0');self.assertIs(gate.uncertain,duration>210)
        with tempfile.TemporaryDirectory() as folder:
            gate=object.__new__(diagnostic.HostDiagnostic);gate.uncertain=False;gate.failures=[];gate.deadline=320.0
            with patch.object(diagnostic,'OUT',Path(folder)),patch.object(diagnostic.time,'monotonic',return_value=100.0),patch.object(diagnostic.subprocess,'call') as called:
                with self.assertRaisesRegex(ValueError,'full phase and cleanup allowance do not fit'):gate.command('install-owned-app',['xcrun','simctl','install','owned','app'],210,simulator=True)
                called.assert_not_called()


    def testPhotosTimingRecordsOnlyExistingStagesAndKeepsTimeoutReapedFailure(self):
        for mode in ['timely','late-zero','slow-start','denied']:
            with self.subTest(mode=mode):
                code,log,opened,process,killed=self.bounded(mode)
                rows=[json.loads(line.split('PHOTOS_BOUNDED_TIMING ',1)[1]) for line in log.splitlines() if line.startswith('PHOTOS_BOUNDED_TIMING ')]
                self.assertTrue(rows);self.assertEqual(rows[0]['phase'],'wrapper-ready');self.assertEqual(rows[-1]['phase'],'wrapper-end')
                self.assertTrue(all(r['schema']=='Celluloid.PhotosBoundedTiming.1' and r['source_sha']=='a'*40 and r['run_id']=='123' and r['run_attempt']=='1' for r in rows))
                self.assertTrue(all(r['wrapper_entry_monotonic']<=r['monotonic'] and r['parent_deadline_monotonic']==2 for r in rows))
                spawn=next(r for r in rows if r['phase']=='spawn-return');self.assertEqual((spawn['child_pid'],spawn['child_pgid'],spawn['start_new_session']),(12345,12345,True))
                if mode=='timely':
                    self.assertEqual(code,0);self.assertEqual(next(r for r in rows if r['phase']=='wait-begin')['remaining_seconds'],1)
                    self.assertFalse(any(r['phase']=='cleanup-result' for r in rows))
                else:
                    self.assertEqual(code,124);cleanup=[r for r in rows if r['phase']=='cleanup-result'];self.assertTrue(cleanup);self.assertTrue(all(r['group_exit_confirmed'] is False for r in cleanup))
                    if mode=='denied':self.assertEqual(cleanup[-1]['status'],'signal_denied');self.assertEqual([r['signal_name'] for r in rows if r['phase']=='cleanup-signal-attempt'],['SIGTERM'])
                    else:self.assertEqual(cleanup[-1]['status'],'child_reaped');self.assertEqual(cleanup[-1]['child_returncode'],0)
        code,log,opened,process,killed=self.bounded('timely',expired=True)
        self.assertEqual(code,124);self.assertIn('"phase": "expired-before-spawn"',log);self.assertNotIn('"phase": "spawn-begin"',log);opened.assert_not_called()

    def testTimingReceiptDelayCannotPermitLateSpawnOrExtendActualWait(self):
        for mode in ['slow-spawn-receipt','slow-wait-receipt']:
            code,log,opened,process,killed=self.bounded(mode)
            self.assertEqual(code,124);process.wait.assert_not_called();killed.assert_not_called()
            if mode=='slow-spawn-receipt':opened.assert_not_called();self.assertIn('"child_started": false',log)
            else:opened.assert_called_once();self.assertIn('"status": "child_reaped"',log)

    def testCleanupReceiptDelayCannotWaitOrEscalatePastFixedTenSeconds(self):
        import signal
        for mode in ['slow-cleanup-signal','slow-cleanup-wait','slow-cleanup-second-signal']:
            with self.subTest(mode=mode):
                code,log,opened,process,killed=self.bounded(mode);self.assertEqual(code,124)
                rows=[json.loads(line.split('PHOTOS_BOUNDED_TIMING ',1)[1]) for line in log.splitlines() if line.startswith('PHOTOS_BOUNDED_TIMING ')]
                timeout=next(r for r in rows if r['phase']=='timeout-observed');self.assertEqual(timeout['cleanup_deadline_monotonic'],timeout['cleanup_started_monotonic']+10)
                cleanup=[r for r in rows if r['phase']=='cleanup-result'];self.assertEqual(cleanup[-1]['status'],'bounded_cleanup_expired');self.assertTrue(all(r['group_exit_confirmed'] is False for r in cleanup))
                if mode=='slow-cleanup-signal':killed.assert_not_called();self.assertEqual(process.wait.call_count,1)
                else:killed.assert_called_once_with(12345,signal.SIGTERM);self.assertEqual(process.wait.call_count,2 if mode=='slow-cleanup-second-signal' else 1)

    def testOtherRoutesDoNotEmitPhotosTimingOrUseNewNativeQueries(self):
        import contextlib,io,os,runpy,sys
        from unittest.mock import MagicMock,patch
        root=Path(__file__).resolve().parents[1];process=MagicMock(pid=12345,returncode=0);process.wait.return_value=0;out=io.StringIO()
        argv=['run_bounded.py','--seconds','20','--label','original-scope','owned-fake-command']
        with patch.dict(os.environ,{'GITHUB_REF':'refs/heads/swiftui-first-native','GITHUB_REPOSITORY':'100mango/Celluloid'},clear=True),patch.object(sys,'argv',argv),patch('subprocess.Popen',return_value=process),patch('subprocess.run',side_effect=AssertionError('new native query')),patch('os.getpgid',side_effect=AssertionError('new group query')),contextlib.redirect_stdout(out),self.assertRaises(SystemExit) as caught:
            runpy.run_path(str(root/'Scripts/run_bounded.py'),run_name='__main__')
        self.assertEqual(caught.exception.code,0);self.assertNotIn('PHOTOS_BOUNDED_TIMING',out.getvalue());process.wait.assert_called_once_with(timeout=20)

    def testOnlyExistingPhotosAbsoluteWrappersUseSiteFreeAndRetainedLogs(self):
        import ast
        root=Path(__file__).resolve().parents[1];count=0
        for name,expected in [('run_ios_photos_host_diagnostic.py',2),('swiftui_photos_gate.py',1),('run_ios_photos_host.py',1)]:
            source=(root/'Scripts'/name).read_text();lists=[n for n in ast.walk(ast.parse(source)) if isinstance(n,ast.List) and n.elts and isinstance(n.elts[0],ast.Attribute) and isinstance(n.elts[0].value,ast.Name) and n.elts[0].value.id=='sys' and n.elts[0].attr=='executable' and any(isinstance(e,ast.Constant) and e.value=='Scripts/run_bounded.py' for e in n.elts)]
            self.assertEqual(len(lists),expected)
            for node in lists:
                self.assertEqual(node.elts[1].value,'-S');self.assertEqual(node.elts[2].value,'Scripts/run_bounded.py');self.assertTrue(any(isinstance(e,ast.Constant) and e.value=='--deadline-monotonic' for e in node.elts))
            count+=len(lists)
        self.assertEqual(count,4)
        gate=(root/'Scripts/swiftui_photos_gate.py').read_text();self.assertIn("if expected_ref == 'refs/heads/cell-ios-photos-host-final':\n        if stage != 'bootstrap':raise ValueError('Dedicated host route may only reuse the fixture bootstrap')\n        observed = fresh_owned_device_observation(output, bootstrap_parent=photos_bootstrap_parent_deadline(receipt_path))\n    else:\n        observed = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', 'available', '-j'], text=True, timeout=20))",gate)
        wrapper=(root/'Scripts/run_bounded.py').read_text();self.assertIn("import time\n_wrapper_entry_monotonic = time.monotonic()\n\nimport argparse",wrapper)
        self.assertLess(wrapper.index("parser.error('Invalid reviewed Photos-host parent deadline')"),wrapper.index("photos_timing('wrapper-ready')"))
        self.assertIn('            build/swiftui-acceptance/',(root/host.PROBE_WORKFLOW).read_text())



class BootstrapQueryBudgetTests(unittest.TestCase):
    def context(self, root):
        source='a'*40
        env={'GITHUB_REPOSITORY':'100mango/Celluloid','GITHUB_EVENT_NAME':'push','GITHUB_REF':'refs/heads/cell-ios-photos-host-final',
             'GITHUB_WORKFLOW_REF':'100mango/Celluloid/.github/workflows/ios-photos-host-probe.yml@refs/heads/cell-ios-photos-host-final',
             'GITHUB_SHA':source,'GITHUB_WORKFLOW_SHA':source,'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1'}
        owner={'schema':'celluloid.swiftui.owned-simulator.v1','source_sha':source,'run_id':'123','run_attempt':'1',
               'device_id':'12345678-1234-1234-1234-123456789AB0','device_name':'Celluloid iOS27 iPhone SE (3rd generation)',
               'runtime_id':'com.apple.CoreSimulator.SimRuntime.iOS-27-0','created_by_this_job':True,'absent_before_create':True,
               'job_started_monotonic':100.0,'work_deadline_monotonic':2380.0}
        parent={'phase':'photos-bootstrap','dispatch_started_monotonic':100.0,'deadline_monotonic':850.0,'limit_seconds':750,
                **{key:owner[key] for key in ['source_sha','run_id','run_attempt','device_id']},'state':'dispatched'}
        path=root/'build/owned-simulator.json';path.parent.mkdir(parents=True);path.write_text(json.dumps(owner))
        timing=path.parent/'photos-bootstrap-dispatch-timing.json';timing.write_text(json.dumps(parent))
        return env,owner,parent,path,timing

    def testOnlyAdmittedBootstrapGetsSixtyAndHostDefaultStaysTwenty(self):
        import os
        from unittest.mock import patch
        import swiftui_photos_gate as gate
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);env,owner,parent,path,timing=self.context(root);calls=[];clock=[110.0]
            observed={'devices':{owner['runtime_id']:[{'udid':owner['device_id'],'name':owner['device_name'],'state':'Booted','isAvailable':True}]}}
            def invoke(command,stdout,stderr):calls.append(command);stdout.write(json.dumps(observed).encode());clock[0]+=1;return 0
            with patch.dict(os.environ,env),patch.object(gate.Path,'cwd',return_value=root),patch.object(gate.time,'monotonic',side_effect=lambda:clock[0]),patch.object(gate.subprocess,'check_output',return_value=owner['source_sha']),patch.object(gate.subprocess,'run'),patch.object(gate.subprocess,'call',side_effect=invoke):
                gate.admission('bootstrap',owner['device_id'],root/'.build/ios',root/'build/photos',path,env['GITHUB_REF'])
                self.assertEqual(calls[-1][calls[-1].index('--seconds')+1],'60')
                self.assertEqual(calls[-1][calls[-1].index('--deadline-monotonic')+1],'170.0')
                for stage in ['legacy','pristine','preservation']:
                    with self.subTest(stage=stage),self.assertRaisesRegex(ValueError,'only reuse'):gate.admission(stage,owner['device_id'],root/'.build/ios',root/'build/photos',path,env['GITHUB_REF'])
                self.assertEqual(len(calls),1)
                gate.fresh_owned_device_observation(root/'build/actual-host')
                self.assertEqual(calls[-1][calls[-1].index('--seconds')+1],'20')
                self.assertEqual(calls[-1][-6:],['xcrun','simctl','list','devices','available','-j'])
            self.assertEqual(json.loads((root/'build/photos/owned-device-observation.json').read_text())['limit_seconds'],60)
            self.assertEqual(json.loads((root/'build/actual-host/owned-device-observation.json').read_text())['limit_seconds'],20)

    def testQueryAndInterpreterDelayConsumeOriginalParentWithoutExtending720(self):
        import contextlib,io,os,sys
        from unittest.mock import patch
        import swiftui_photos_gate as gate
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);env,owner,parent,path,timing=self.context(root)
            for now,expected in [(110.0,830.0),(170.0,850.0),(230.0,850.0)]:
                with self.subTest(now=now),patch.dict(os.environ,env),patch.object(gate.time,'monotonic',return_value=now),patch.object(sys,'argv',['swiftui_photos_gate.py','budget','bootstrap',str(path),'deadline']),contextlib.redirect_stdout(io.StringIO()) as output:gate.main()
                deadline=float(output.getvalue());self.assertEqual(deadline,expected);self.assertLessEqual(deadline-now,720);self.assertLessEqual(deadline,parent['deadline_monotonic'])
            # The historical route still uses its original independently started720.
            with patch.dict(os.environ,dict(env,GITHUB_REF='refs/heads/swiftui-first-native')),patch.object(gate.time,'monotonic',return_value=170.0),patch.object(sys,'argv',['swiftui_photos_gate.py','budget','bootstrap',str(path),'deadline']),contextlib.redirect_stdout(io.StringIO()) as output:gate.main()
            self.assertEqual(float(output.getvalue()),890.0)

    def testMissingForgedExpiredOrCompletedParentRejectsBeforeFreshQuery(self):
        import os
        from unittest.mock import patch
        import swiftui_photos_gate as gate
        changes=[None,{'source_sha':'b'*40},{'run_id':'124'},{'run_attempt':'2'},{'device_id':'other'},
                 {'deadline_monotonic':851.0},{'limit_seconds':751},{'limit_seconds':True},{'dispatch_started_monotonic':111.0},
                 {'deadline_monotonic':float('nan')},{'state':'completed'},{'extra':1}]
        for changed in changes:
            with self.subTest(changed=changed),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);env,owner,parent,path,timing=self.context(root)
                if changed is None:timing.unlink()
                else:timing.write_text(json.dumps(dict(parent,**changed)))
                with patch.dict(os.environ,env),patch.object(gate.Path,'cwd',return_value=root),patch.object(gate.time,'monotonic',return_value=110.0),patch.object(gate.subprocess,'check_output',return_value=owner['source_sha']),patch.object(gate.subprocess,'run'),patch.object(gate.subprocess,'call') as native:
                    with self.assertRaises(ValueError):gate.admission('bootstrap',owner['device_id'],root/'.build/ios',root/'build/photos',path,env['GITHUB_REF'])
                    native.assert_not_called()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);env,owner,parent,path,timing=self.context(root)
            for now in [850.0,851.0]:
                with patch.dict(os.environ,env),self.assertRaises(ValueError):gate.photos_bootstrap_parent_deadline(path,now=now)
            for key,value in [('GITHUB_REF','refs/heads/swiftui-first-native'),('GITHUB_WORKFLOW_SHA','b'*40),('GITHUB_RUN_ATTEMPT','2')]:
                with patch.dict(os.environ,dict(env,**{key:value})),self.assertRaises(ValueError):gate.photos_bootstrap_parent_deadline(path,now=110.0)
            with patch.dict(os.environ,env),patch.object(gate.time,'monotonic',return_value=781.0),patch.object(gate.subprocess,'call') as native,self.assertRaisesRegex(ValueError,'cannot fit'):gate.fresh_owned_device_observation(root/'build/photos',bootstrap_parent=850.0)
            native.assert_not_called()

    def testSixtySecondLateZeroStillRejectsOneFreshQueryWithoutRetry(self):
        from unittest.mock import patch
        import swiftui_photos_gate as gate
        for duration in [59.0,61.0]:
            with self.subTest(duration=duration),tempfile.TemporaryDirectory() as folder:
                clock=[100.0];calls=[]
                def invoke(command,stdout,stderr):calls.append(command);stdout.write(b'{"devices":{}}');clock[0]+=duration;return 0
                with patch.object(gate.time,'monotonic',side_effect=lambda:clock[0]),patch.object(gate.subprocess,'call',side_effect=invoke):
                    if duration>60:
                        with self.assertRaisesRegex(ValueError,'parent deadline'):gate.fresh_owned_device_observation(Path(folder),bootstrap_parent=850.0)
                    else:self.assertEqual(gate.fresh_owned_device_observation(Path(folder),bootstrap_parent=850.0),{'devices':{}})
                self.assertEqual(len(calls),1);receipt=json.loads((Path(folder)/'owned-device-observation.json').read_text());self.assertEqual(receipt['limit_seconds'],60);self.assertIs(receipt['prohibit_further_native'],duration>60)

    def testDriverPublishesBoundParentBeforeNestedDispatchAtIdenticalClock(self):
        import os
        from unittest.mock import patch
        import run_ios_photos_host_diagnostic as driver
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);env,owner,parent,path,timing=self.context(root);timing.unlink();clock=[100.0]
            diagnostic=object.__new__(driver.HostDiagnostic);diagnostic.source=owner['source_sha'];diagnostic.device=owner['device_id'];diagnostic.uncertain=False;diagnostic.failures=[]
            def invoke(self,*args,**kwargs):
                receipt=json.loads(timing.read_text());self_test.assertEqual(receipt,parent);clock[0]=111.0;return 0,'ok'
            self_test=self
            with patch.dict(os.environ,env),patch.object(driver,'OUT',path.parent),patch.object(driver.time,'monotonic',side_effect=lambda:clock[0]),patch.object(driver.Acceptance,'command',invoke):
                self.assertEqual(diagnostic.command('photos-bootstrap',['owned-nested-command'],750,simulator=True,nested_owned=True),(0,'ok'))
                final=json.loads(timing.read_text());self.assertEqual(final['deadline_monotonic'],850.0);self.assertEqual(final['elapsed_seconds'],11.0)
                with self.assertRaisesRegex(ValueError,'stale'):diagnostic.command('photos-bootstrap',['must-not-run'],750,simulator=True,nested_owned=True)


    def testSetupCommandDeadlinesRemainInsideParentAndHistoricalArgvIsUnchanged(self):
        import contextlib,io,re,sys,subprocess,time
        from unittest.mock import patch
        root=Path(__file__).resolve().parents[1];shell=(root/'Scripts/run_swiftui_photos_gate.sh').read_text()
        code=re.search(r"command_deadline=\$\(python3 -S -c '(.*?)' \"\$seconds\" \"\$bootstrap_deadline\"\)",shell,re.S).group(1)
        for seconds in [45,60]:
            for now,ok in [(110.0,True),(850.0-seconds-10,True),(851.0-seconds-10,False),(851.0,False)]:
                with self.subTest(seconds=seconds,now=now),patch.object(sys,'argv',['-c',str(seconds),'850.0']),patch.object(time,'monotonic',return_value=now),contextlib.redirect_stdout(io.StringIO()) as out:
                    if ok:exec(compile(code,'exact-setup-deadline','exec'),{})
                    else:
                        with self.assertRaisesRegex(SystemExit,'no dispatch'):exec(compile(code,'exact-setup-deadline','exec'),{})
                if ok:self.assertEqual(float(out.getvalue()),now+seconds);self.assertLessEqual(float(out.getvalue())+10,850.0)
        calls=re.findall(r'^  bootstrap_setup (\d+) ([a-z-]+) \\$',shell,re.M)
        self.assertEqual(calls,[('45','seeded-fixture-generation'),('45','seeded-owned-registration'),('60','seeded-owned-photos-grant')])
        body=shell[shell.index('  bootstrap_setup() {'):shell.index('  bootstrap_setup 45 seeded-fixture-generation')]
        for ref in ['refs/heads/swiftui-first-native','refs/heads/other']:
            # Execute only the exact extracted shell function with a harmless
            # python3 recorder; no native tool or real wrapper is dispatched.
            script='set -euo pipefail\nsource_ref='+ref+'\nbootstrap_deadline=850\npython3() { printf "<%s>\\n" "$@"; }\n'+body+'\nbootstrap_setup 45 old-label owned-command arg\n'
            result=subprocess.run(['/bin/bash','-c',script],text=True,capture_output=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.splitlines(),['<Scripts/run_bounded.py>','<--seconds>','<45>','<--label>','<old-label>','<owned-command>','<arg>'])
        self.assertIn('if [[ "$source_ref" = refs/heads/cell-ios-photos-host-final ]]; then',body)
        self.assertIn('--deadline-monotonic "$command_deadline" "$@"',body)
        self.assertIn('|| return $?',body)
        for status in [0,9]:
            # A refused/expired deadline calculation must not reach the wrapper.
            fake='python3() { if [[ "$1" = -S ]]; then '
            fake+=('printf "155.0\\n"; return 0;' if status==0 else 'return 9;')
            fake+=' fi; printf "<%s>\\n" "$@"; }\n'
            script='set -euo pipefail\nsource_ref=refs/heads/cell-ios-photos-host-final\nbootstrap_deadline=850\n'+fake+body+'\nbootstrap_setup 45 current-label owned-command arg\n'
            result=subprocess.run(['/bin/bash','-c',script],text=True,capture_output=True,timeout=5)
            self.assertEqual(result.returncode,status,result.stderr)
            self.assertEqual(result.stdout.splitlines(),['<Scripts/run_bounded.py>','<--seconds>','<45>','<--label>','<current-label>','<--deadline-monotonic>','<155.0>','<owned-command>','<arg>'] if status==0 else [])


NOTIFICATION_TITLE = '“Photos” Would Like to Send You Notifications'
NOTIFICATION_BODY = 'Notifications may include alerts, sounds, and icon badges. These can be configured in Settings.'

def validate_observed_notification_navigation_source(source):
    import hashlib
    start=source.index('    private func declineObservedPhotosNotificationsIfPresent() throws {')
    middle=source.index('    private func selectObservedCollections() throws {',start)
    end=source.index('    private func openCelluloidExtension() throws {',middle)
    denial=source[start:middle];navigation=source[middle:end]
    required=[
        'let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")',
        'let alerts = springboard.alerts',
        'guard alerts.firstMatch.waitForExistence(timeout: 2) else {',
        'guard photos.alerts.count == 0 else { throw failure("Unknown Photos alert; no action taken") }',
        'try withinBudget()',
        'guard alerts.count == 1, photos.alerts.count == 0 else {',
        'let observed = alerts.containing(.staticText, identifier: "'+NOTIFICATION_TITLE+'")',
        '.containing(.staticText, identifier: "'+NOTIFICATION_BODY+'")',
        'guard observed.count == 1 else {',
        'let alert = observed.element',
        'let title = alert.staticTexts.matching(NSPredicate(format: "label == %@", "'+NOTIFICATION_TITLE+'"))',
        'let body = alert.staticTexts.matching(NSPredicate(format: "label == %@", "'+NOTIFICATION_BODY+'"))',
        'let deny = alert.buttons.matching(NSPredicate(format: "label == %@", "Don’t Allow"))',
        'let allow = alert.buttons.matching(NSPredicate(format: "label == %@", "Allow"))',
        'guard title.count == 1, body.count == 1, deny.count == 1, allow.count == 1,',
        'alert.buttons.count == 2, title.element.isHittable, body.element.isHittable else {',
        'let decline = try unique(deny)', '_ = try unique(allow)', 'decline.tap()',
        'object: alert)], timeout: 8) == .completed,',
        'springboard.alerts.count == 0, photos.alerts.count == 0 else {'
    ]
    previous=-1
    for fragment in required:
        if denial.count(fragment)!=1 or denial.index(fragment)<=previous:raise ValueError('Missing/changed/out-of-order notification guard: '+fragment)
        previous=denial.index(fragment)
    if denial.count('.tap()')!=1:raise ValueError('Only one explicit notification denial may be tapped')
    if denial.count('.debugDescription')!=1 or denial.count('photos.screenshot()')!=1 or 'photos.debugDescription' in denial:raise ValueError('Prompt evidence must stay bounded without duplicate Photos AX traversal')
    ordered=['try withinBudget()', 'guard photos.alerts.count == 0,',
        'XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts.count == 0 else {',
        'let query = photos.buttons.matching(identifier: "CollectionsTab").matching(NSPredicate(format: "label == %@", "Collections"))',
        'let library = photos.buttons.matching(identifier: "LibraryTab").matching(NSPredicate(format: "label == %@", "Library"))',
        'guard query.count == 1, library.count == 1 else {', 'let collections = try unique(query)',
        'if !collections.isSelected {', 'guard try unique(library).isSelected else {', 'collections.tap()',
        'XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in collections.isSelected },',
        'object: nil)], timeout: 8) == .completed else {', 'checkpoint("observed-collections-selected")']
    previous=-1
    for fragment in ordered:
        if navigation.count(fragment)!=1 or navigation.index(fragment)<=previous:raise ValueError('Missing/changed/out-of-order Collections guard: '+fragment)
        previous=navigation.index(fragment)
    if navigation.count('.tap()')!=1:raise ValueError('Only one observed Collections reselection is permitted')
    calls='        try declineObservedPhotosNotificationsIfPresent()\n        try selectObservedCollections()\n'
    if source.count(calls)!=1 or ('try dismissObservedWhatsNewIfPresent()\n'+calls+'        stage = "open-albums"') not in source:raise ValueError('Notification denial must precede observed reselection and original Albums route')
    restored=restore_observed_album_delta((source[:start]+source[end:]).replace(calls,''))
    if hashlib.sha256(restored.encode()).hexdigest()!='1bc8de8517c0e522f42322d98861e557c010b82531a46991f9242b13f92ce1c1':raise ValueError('Original host assertions, introduction, unknown-alert monitor or budgets changed')

class ObservedNotificationNavigationTests(unittest.TestCase):
    def setUp(self):self.source=(Path(__file__).resolve().parents[1]/'CelluloidUITests/IOSPhotosHostUITests.swift').read_text()
    def testObservedDenialAndSelectionPreserveAllOriginalHostBytes(self):
        validate_observed_notification_navigation_source(self.source)
        self.assertEqual([x[2] for x in host.STEPS],[45,165,45,165,45]);self.assertEqual(len(host.STEPS),5)
    def testChangedPromptAmbiguousButtonsOrGrantCannotAuthorizeAction(self):
        mutations=[self.source.replace('"'+text+'"','"Unknown"') for text in [NOTIFICATION_TITLE,NOTIFICATION_BODY,'Don’t Allow','Allow']]
        for token in ['alerts.count == 1','observed.count == 1','photos.alerts.count == 0','title.count == 1','body.count == 1','deny.count == 1','allow.count == 1','alert.buttons.count == 2','title.element.isHittable','body.element.isHittable']:
            mutations.append(self.source.replace(token,'true'))
        mutations += [self.source.replace('decline.tap()','allow.element.tap()'),self.source.replace('decline.tap()','decline.tap()\n        decline.tap()'),self.source.replace('let decline = try unique(deny)','let decline = deny.element')]
        for value in mutations:
            with self.assertRaises(ValueError):validate_observed_notification_navigation_source(value)
    def testUnknownTabUnselectedOutcomeOrActionBeforeDenialRejects(self):
        for old,new in [('"CollectionsTab"','"GuessedTab"'),('"LibraryTab"','"GuessedTab"'),('query.count == 1','query.count > 0'),('library.count == 1','library.count > 0'),('guard try unique(library).isSelected else','guard true else'),('collections.isSelected },','true },'),('collections.tap()','collections.tap()\n            collections.tap()')]:
            with self.subTest(old=old),self.assertRaises(ValueError):validate_observed_notification_navigation_source(self.source.replace(old,new))
        calls='        try declineObservedPhotosNotificationsIfPresent()\n        try selectObservedCollections()\n'
        with self.assertRaises(ValueError):validate_observed_notification_navigation_source(self.source.replace(calls,'        try selectObservedCollections()\n        try declineObservedPhotosNotificationsIfPresent()\n'))
    def testOwnedAlbumFilenameAndFunctionalAssertionsCannotBeRelaxed(self):
        for old,new in [('let titleNode = try unique(','let titleNode = '),('let cell = try observedOwnedAlbumItem(title: title)','let cell = photos.images.firstMatch'),('try verifyPublicFilename()','try withinBudget()'),('"filter-Sepia"','"filter-None"'),('changed != original','changed == original'),('executionTimeAllowance = 120','executionTimeAllowance = 180'),('fatalError("IOS_PHOTOS_HOST_UNKNOWN_ALERT no action taken")','return true')]:
            with self.subTest(old=old),self.assertRaises(ValueError):validate_observed_notification_navigation_source(self.source.replace(old,new))


ALBUM_PAGE = 'PhotosUICore.PhotosPageContainerView_AX'
ALBUM_OLD_BLOCK = '        _ = try unique(photos.navigationBars.matching(identifier: title))\n        let cells = photos.collectionViews.cells\n        let cell = try unique(cells)\n'
ALBUM_NEW_BLOCK = '        let cell = try observedOwnedAlbumItem(title: title)\n'

def restore_observed_album_delta(source):
    source=restore_observed_filename_delta(source)
    start=source.index('    private func observedOwnedAlbumItem(title: String) throws -> XCUIElement {')
    end=source.index('    private func ',start+len('    private func '))
    helper=source[start:end]
    required=['try withinBudget()',
        'let pages = photos.otherElements.matching(identifier: "'+ALBUM_PAGE+'")',
        'pages.count == 1 && pages.element.exists',
        'guard XCTWaiter.wait(for: [ready], timeout: 8) == .completed else {',
        'let page = pages.element',
        'let heading = page.staticTexts.matching(identifier: "collectionTitle")',
        'let count = page.staticTexts.matching(identifier: "collectionAssetCount")',
        'let items = page.images.matching(identifier: "PXGGridLayout-Info")',
        'guard heading.count == 1, count.count == 1, items.count == 1,',
        'heading.element.label == title, count.element.label == "1 Item" else {',
        '_ = try unique(heading)', '_ = try unique(count)', 'return try unique(items)']
    previous=-1
    for fragment in required:
        if helper.count(fragment)!=1 or helper.index(fragment)<=previous:raise ValueError('Missing/changed/out-of-order owned album guard: '+fragment)
        previous=helper.index(fragment)
    if any(token in helper for token in ['.firstMatch','.element(boundBy:','.tap()','PhotosGridAddButton','BEGINSWITH','CONTAINS','label IN','coordinate(']):raise ValueError('Unreviewed album selection fallback')
    if source.count(ALBUM_NEW_BLOCK)!=1:raise ValueError('Missing/duplicate observed album selection')
    sequence='        titleNode.tap()\n'+ALBUM_NEW_BLOCK+'        checkpoint("single-owned-album-item")\n        stage = "open-single-owned-photo"\n        cell.tap()\n        _ = try unique(photos.buttons.matching(identifier: "Edit"))\n        try verifyPublicFilename()'
    if sequence not in source:raise ValueError('Owned album/photo identity or exact filename validation moved')
    return (source[:start]+source[end:]).replace(ALBUM_NEW_BLOCK,ALBUM_OLD_BLOCK)

class ObservedOwnedAlbumSourceTests(unittest.TestCase):
    def setUp(self):self.source=(Path(__file__).resolve().parents[1]/'CelluloidUITests/IOSPhotosHostUITests.swift').read_text()
    def testObservedContainerIdentityAndSingleGridPhotoRestoreExactPriorSource(self):
        import hashlib
        restored=restore_observed_album_delta(self.source)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),'2ed6da31ecbf86d82d79167d04051c06ab4b6c585661272b7694601a7b9a5d50')
        validate_observed_notification_navigation_source(self.source)
    def testMissingDuplicateContainerHeadingCountOrPhotoCannotAuthorizeSelection(self):
        for guard in ['pages.count == 1 && pages.element.exists','heading.count == 1','count.count == 1','items.count == 1']:
            for changed in ['true',guard.replace('== 1','> 0')]:
                with self.subTest(guard=guard,changed=changed),self.assertRaises(ValueError):restore_observed_album_delta(self.source.replace(guard,changed))
        for identifier in [ALBUM_PAGE,'collectionTitle','collectionAssetCount','PXGGridLayout-Info']:
            with self.subTest(identifier=identifier),self.assertRaises(ValueError):restore_observed_album_delta(self.source.replace('"'+identifier+'"','"Missing"'))
    def testWrongOwnerCountOrAddTileAndIndexFallbackReject(self):
        mutants=[self.source.replace('heading.element.label == title','heading.element.label.hasPrefix(title)'),
            self.source.replace('heading.element.label == title','heading.element.label == "Other album"'),
            self.source.replace('"1 Item"','"2 Items"'),self.source.replace('page.images.matching(identifier: "PXGGridLayout-Info")','page.buttons.matching(identifier: "PhotosGridAddButton")'),
            self.source.replace('return try unique(items)','return items.firstMatch'),self.source.replace('return try unique(items)','return items.element(boundBy: 0)'),
            self.source.replace('_ = try unique(heading)','_ = heading.element'),self.source.replace('_ = try unique(count)','_ = count.element'),
            self.source.replace('try verifyPublicFilename()','try withinBudget()')]
        for source in mutants:
            with self.assertRaises(ValueError):restore_observed_album_delta(source)



# Preserve the already allowed exact filename-or-basename identity. Only the
# observed AX attribute changes from label to this unique field's String value.
FILENAME_OLD_BLOCK = '        _ = try unique(photos.staticTexts.matching(NSPredicate(format: "label IN %@", [filename, basename])))\n'
FILENAME_NEW_BLOCK = '        // Run37918693951: Photos exposes the public filename as this field\'s\n        // String value. Its label is "Filename", never the filename itself.\n        let fields = photos.staticTexts.matching(identifier: "com.apple.photos.infoPanel.filename")\n        let field = try unique(fields)\n        guard fields.count == 1, field.label == "Filename",\n              let publicFilename = field.value as? String,\n              [filename, basename].contains(publicFilename) else {\n            throw failure("Observed public filename differs from the exact owned fixture")\n        }\n'

def restore_observed_filename_delta(source):
    if source.count(FILENAME_NEW_BLOCK)!=1:raise ValueError('Missing/changed/duplicate observed filename value contract')
    return source.replace(FILENAME_NEW_BLOCK,FILENAME_OLD_BLOCK)

class ObservedFilenameValueTests(unittest.TestCase):
    def setUp(self):self.source=(Path(__file__).resolve().parents[1]/'CelluloidUITests/IOSPhotosHostUITests.swift').read_text()
    def testObservedValueRestoresExactPublishedParentAndAllFunctionalChecks(self):
        import hashlib
        self.assertEqual(hashlib.sha256(restore_observed_filename_delta(self.source).encode()).hexdigest(),'76d1c73a4103e9748d40a3599b90238a34e044d23e27e3ff34af1049d73cccf0')
        validate_observed_notification_navigation_source(self.source)
    def testMissingNonStringOrDefaultFilenameValueCannotPass(self):
        for old,new in [('let publicFilename = field.value as? String','let publicFilename = field.value'),('let publicFilename = field.value as? String','let publicFilename = String(describing: field.value)'),('let publicFilename = field.value as? String','let publicFilename = (field.value as? String) ?? basename'),('[filename, basename].contains(publicFilename)','publicFilename.hasPrefix(basename)'),('[filename, basename].contains(publicFilename)','true')]:
            with self.subTest(old=old,new=new),self.assertRaises(ValueError):restore_observed_filename_delta(self.source.replace(old,new))
    def testDuplicateIdentifierWrongLabelOrWrongCompleteNameCannotPass(self):
        for old,new in [('fields.count == 1','fields.count > 0'),('fields.count == 1','true'),('field.label == "Filename"','true'),('"com.apple.photos.infoPanel.filename"','"Unknown"'),('[filename, basename].contains(publicFilename)','["other.png", basename].contains(publicFilename)'),('let field = try unique(fields)','let field = fields.firstMatch'),('let field = try unique(fields)','let field = fields.element(boundBy: 0)'),('try tap(photos.buttons.matching(identifier: "Info"))','try withinBudget()')]:
            with self.subTest(old=old,new=new),self.assertRaises(ValueError):validate_observed_notification_navigation_source(self.source.replace(old,new))



PHOTOS_INSTALL_SPLIT_PREFIX = "# Only the exact final Photos install command gets the split phase budget.\n# Source/owner/build admission remains in the unchanged parent host controller.\nphotos_install_split = (os.environ.get('GITHUB_REF') == 'refs/heads/cell-ios-photos-host-final'\n                        and args.label == 'install-owned-app')\nif photos_install_split:\n    import re\n    expected_app = os.path.join(os.getcwd(), '.build/swiftui-ios/Build/Products/Debug-iphonesimulator/Celluloid.app')\n    if (not absolute_deadline or args.seconds != 210 or len(args.command) != 5\n            or args.command[:3] != ['xcrun', 'simctl', 'install']\n            or re.fullmatch(r'[0-9A-F]{8}(?:-[0-9A-F]{4}){3}-[0-9A-F]{12}', args.command[3]) is None\n            or args.command[4] != expected_app):\n        parser.error('Invalid exact Photos install preparation/native split')\n"
PHOTOS_INSTALL_SPLIT_HELPER = "def refuse_expired_install_preparation():\n    if time.monotonic() >= args.deadline_monotonic - 120:\n        photos_timing('install-preparation-expired', child_started=False, preparation_limit_seconds=90)\n        print('BOUNDED_COMMAND_TIMEOUT', args.label, 'preparation deadline expired; no install dispatch', flush=True)\n        photos_timing('wrapper-end', exit_code=124, child_started=False)\n        sys.exit(124)\n\n\n"
PHOTOS_INSTALL_SPLIT_NATIVE = "refuse_expired_parent()\nif photos_install_split:\n    refuse_expired_install_preparation()\n    # Sample before receipt I/O and Popen. Neither can earn a new120s window.\n    native_dispatch_started = time.monotonic()\n    deadline = min(native_dispatch_started + 120, args.deadline_monotonic)\n    photos_timing('install-native-dispatch', native_dispatch_started_monotonic=native_dispatch_started,\n                  native_deadline_monotonic=deadline, native_limit_seconds=120,\n                  preparation_deadline_monotonic=args.deadline_monotonic - 120,\n                  preparation_limit_seconds=90, phase_limit_seconds=210)\n    refuse_expired_install_preparation()\n    refuse_expired_parent()\ntry:\n"

class PhotosInstallSplitClockTests(unittest.TestCase):
    def exercise(self,mode='timely',cap=210,parent=211,absolute=True,command_change=None,route='cell-ios-photos-host-final'):
        import contextlib,io,os,runpy,signal,subprocess,sys
        from unittest.mock import MagicMock,patch
        root=Path(__file__).resolve().parents[1];clock=[50.0]
        process=MagicMock(pid=12345,returncode=0);process.poll.return_value=0
        command=['xcrun','simctl','install','12345678-1234-1234-1234-123456789AB0',str(root/'.build/swiftui-ios/Build/Products/Debug-iphonesimulator/Celluloid.app')]
        if command_change:command_change(command)
        argv=['run_bounded.py','--seconds',str(cap),'--label','install-owned-app']
        if absolute:argv+=['--deadline-monotonic',str(parent)]
        argv+=command;output=io.StringIO();real_print=print
        if mode=='expired-preparation':clock[0]=92
        if mode=='expired-parent':clock[0]=212
        def emitted(*args,**kwargs):
            real_print(*args,**kwargs)
            if mode=='slow-native-receipt' and args and args[0]=='PHOTOS_BOUNDED_TIMING' and '"phase": "install-native-dispatch"' in args[1]:clock[0]=92
        def popen(*args,**kwargs):
            self.assertTrue(kwargs['start_new_session'])
            if mode=='slow-popen':clock[0]+=6
            elif mode=='late-popen':clock[0]=171
            return process
        def wait(timeout):
            if mode=='late-zero':clock[0]=171;return 0
            if mode=='denied':clock[0]=171;raise subprocess.TimeoutExpired(command,timeout)
            clock[0]+=20;return 0
        process.wait.side_effect=wait
        if mode=='denied':process.poll.return_value=None
        env={'GITHUB_REF':'refs/heads/'+route,'GITHUB_REPOSITORY':'100mango/Celluloid','GITHUB_SHA':'a'*40,'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1'}
        with patch.dict(os.environ,env,clear=True),patch.object(os,'getcwd',return_value=str(root)),patch.object(sys,'argv',argv),patch('time.monotonic',side_effect=lambda:clock[0]),patch('builtins.print',side_effect=emitted),patch('subprocess.Popen',side_effect=popen) as opened,patch('subprocess.run',side_effect=AssertionError('new query')),patch('os.killpg',side_effect=PermissionError('denied') if mode=='denied' else None) as killed,contextlib.redirect_stdout(output),contextlib.redirect_stderr(output),self.assertRaises(SystemExit) as caught:
            runpy.run_path(str(root/'Scripts/run_bounded.py'),run_name='__main__')
        events=[json.loads(x.split(' ',1)[1]) for x in output.getvalue().splitlines() if x.startswith('PHOTOS_BOUNDED_TIMING ')]
        return caught.exception.code,events,opened,process,killed,output.getvalue()
    def testPreparationAndNativeClocksKeepOriginalParentAbsoluteOrigin(self):
        code,events,opened,process,killed,text=self.exercise();self.assertEqual(code,0);opened.assert_called_once();killed.assert_not_called()
        native=next(x for x in events if x['phase']=='install-native-dispatch')
        self.assertEqual((native['preparation_deadline_monotonic'],native['native_dispatch_started_monotonic'],native['native_deadline_monotonic'],native['parent_deadline_monotonic']),(91,50,170,211))
        self.assertEqual((native['preparation_limit_seconds'],native['native_limit_seconds'],native['phase_limit_seconds']),(90,120,210));process.wait.assert_called_once_with(timeout=120)
    def testSlowPopenConsumesNative120RatherThanReceivingFreshWait(self):
        code,events,opened,process,killed,text=self.exercise('slow-popen');self.assertEqual(code,0);process.wait.assert_called_once_with(timeout=114)
        self.assertEqual(next(x for x in events if x['phase']=='install-native-dispatch')['native_deadline_monotonic'],170)
        code,events,opened,process,killed,text=self.exercise('late-popen');self.assertEqual(code,124);opened.assert_called_once();process.wait.assert_not_called()
    def testPreparationExpiryAndSlowDispatchReceiptNeverStartInstall(self):
        for mode in ['expired-preparation','slow-native-receipt','expired-parent']:
            with self.subTest(mode=mode):
                code,events,opened,process,killed,text=self.exercise(mode);self.assertEqual(code,124);opened.assert_not_called();process.wait.assert_not_called();killed.assert_not_called()
    def testNativeLateZeroFailsEvenWithFortySecondsLeftInParentPhase(self):
        code,events,opened,process,killed,text=self.exercise('late-zero');self.assertEqual(code,124);self.assertIn('BOUNDED_COMMAND_TIMEOUT',text);killed.assert_not_called()
        self.assertEqual(next(x for x in events if x['phase']=='timeout-observed')['monotonic'],171)
        self.assertTrue(any(x['phase']=='cleanup-result' and x['status']=='child_reaped' and x['child_returncode']==0 and x['group_exit_confirmed'] is False for x in events))
    def testMissingWrongNonfiniteParentCapAndWrongExactArgumentsReject(self):
        variants=[dict(absolute=False),dict(cap=120),dict(cap=211),dict(parent=999),dict(parent=float('nan')),dict(parent=float('inf')),dict(command_change=lambda c:c.__setitem__(2,'uninstall')),dict(command_change=lambda c:c.__setitem__(3,'unowned')),dict(command_change=lambda c:c.__setitem__(4,'/other.app')),dict(command_change=lambda c:c.append('--extra')),dict(route='cell-ios-install-diagnostic')]
        for kwargs in variants:
            with self.subTest(kwargs=kwargs):
                code,events,opened,process,killed,text=self.exercise(**kwargs);self.assertEqual(code,2);opened.assert_not_called();killed.assert_not_called()
    def testOriginalSignalDenialStopsEscalationAndKeepsTenSecondCleanup(self):
        import signal
        code,events,opened,process,killed,text=self.exercise('denied');self.assertEqual(code,124);killed.assert_called_once_with(12345,signal.SIGTERM);self.assertEqual(process.wait.call_count,1)
        timeout=next(x for x in events if x['phase']=='timeout-observed');self.assertEqual(timeout['cleanup_deadline_monotonic']-timeout['cleanup_started_monotonic'],10)
        self.assertTrue(any(x['phase']=='cleanup-result' and x['status']=='signal_denied' for x in events))
    def testParentCancellationMarksUncertainAndBlocksBootstrapAndCleanup(self):
        from unittest.mock import patch
        import run_ios_photos_host_diagnostic as diagnostic
        with tempfile.TemporaryDirectory() as folder:
            gate=object.__new__(diagnostic.HostDiagnostic);gate.started=0;gate.deadline=2280
            gate.device='owned';gate.uncertain=False;gate.failures=[];gate.events=[]
            with patch.object(diagnostic,'OUT',Path(folder)),patch('run_swiftui_acceptance.OUT',Path(folder)),patch('time.monotonic',return_value=100),patch('subprocess.call',side_effect=KeyboardInterrupt('cancelled')) as called:
                with self.assertRaises(KeyboardInterrupt):gate.command('install-owned-app',['xcrun','simctl','install','owned','app'],210,simulator=True)
                self.assertTrue(gate.uncertain);self.assertEqual(called.call_count,1)
                with self.assertRaisesRegex(ValueError,'blocks further'):gate.bootstrap()
                gate.cleanup();self.assertEqual(called.call_count,1);self.assertEqual(gate.device,'owned')

    def testSignalledWrapperExitBlocksAllFurtherNativeForBothFailureModes(self):
        from unittest.mock import patch
        import run_ios_photos_host_diagnostic as diagnostic
        for code in [-15,-2,-9,128,129,130,134,137,139,143,255]:
            for allow_failure in [False,True]:
                with self.subTest(code=code,allow_failure=allow_failure),tempfile.TemporaryDirectory() as folder:
                    gate=object.__new__(diagnostic.HostDiagnostic);gate.started=0;gate.deadline=2280
                    gate.device='owned';gate.uncertain=False;gate.failures=[];gate.events=[]
                    with patch.object(diagnostic,'OUT',Path(folder)),patch('run_swiftui_acceptance.OUT',Path(folder)),patch('time.monotonic',return_value=100),patch('subprocess.call',return_value=code) as called:
                        if allow_failure:self.assertEqual(gate.command('install-owned-app',['owned-command'],210,simulator=True,allow_failure=True)[0],code)
                        else:
                            with self.assertRaises(ValueError):gate.command('install-owned-app',['owned-command'],210,simulator=True)
                        self.assertTrue(gate.uncertain);self.assertEqual(called.call_count,1)
                        with self.assertRaisesRegex(ValueError,'blocks further'):gate.bootstrap()
                        gate.cleanup();self.assertEqual(called.call_count,1);self.assertEqual(gate.device,'owned')
    def testKilledBuildWrapperAlsoBlocksOwnedDeviceCleanup(self):
        from unittest.mock import patch
        import run_ios_photos_host_diagnostic as diagnostic
        for code in [-15,-9,128,130,134,137,139,143,255]:
            with self.subTest(code=code),tempfile.TemporaryDirectory() as folder:
                gate=object.__new__(diagnostic.HostDiagnostic);gate.started=0;gate.deadline=2280
                gate.device='owned';gate.uncertain=False;gate.failures=[];gate.events=[]
                with patch.object(diagnostic,'OUT',Path(folder)),patch('run_swiftui_acceptance.OUT',Path(folder)),patch('time.monotonic',return_value=100),patch('subprocess.call',return_value=code) as called:
                    with self.assertRaises(ValueError):gate.command('build',['owned-build-command'],720,simulator=False)
                    self.assertTrue(gate.uncertain);gate.cleanup();self.assertEqual(called.call_count,1)
                    with self.assertRaisesRegex(ValueError,'blocks further'):gate.command('boot',['must-not-dispatch'],60,simulator=True)

    def testSignalUncertaintyPrecedesReceiptFailureAndOrdinaryCodeIsNotReclassified(self):
        from unittest.mock import patch
        import run_ios_photos_host_diagnostic as diagnostic
        for code in [-15,130,1]:
            with self.subTest(code=code),tempfile.TemporaryDirectory() as folder:
                gate=object.__new__(diagnostic.HostDiagnostic);gate.started=0;gate.deadline=2280
                gate.device='owned';gate.uncertain=False;gate.failures=[];gate.events=[]
                def retain(path,value):
                    self.assertEqual(gate.uncertain,code in [-15,130]);raise OSError('timing retention failure')
                with patch.object(diagnostic,'OUT',Path(folder)),patch('run_swiftui_acceptance.OUT',Path(folder)),patch('time.monotonic',return_value=100),patch('subprocess.call',return_value=code) as called,patch.object(diagnostic,'save',side_effect=retain):
                    with self.assertRaises(OSError):gate.command('install-owned-app',['owned-command'],210,simulator=True,allow_failure=True)
                    self.assertEqual(gate.uncertain,code in [-15,130])
                    if code in [-15,130]:gate.cleanup();self.assertEqual(called.call_count,1)

    def testUnknownWrapperOutcomeFromLogReadFailureOrBuildInterruptionStopsCleanup(self):
        from unittest.mock import patch
        import run_ios_photos_host_diagnostic as diagnostic
        real_read=Path.read_text
        def unreadable(path,*args,**kwargs):
            if path.name=='build.log':raise OSError('owned wrapper log unreadable')
            return real_read(path,*args,**kwargs)
        for code in [0,-15,139]:
            with self.subTest(code=code),tempfile.TemporaryDirectory() as folder:
                gate=object.__new__(diagnostic.HostDiagnostic);gate.started=0;gate.deadline=2280
                gate.device='owned';gate.uncertain=False;gate.failures=[];gate.events=[]
                with patch.object(diagnostic,'OUT',Path(folder)),patch('run_swiftui_acceptance.OUT',Path(folder)),patch('time.monotonic',return_value=100),patch('subprocess.call',return_value=code) as called,patch.object(Path,'read_text',unreadable):
                    with self.assertRaises(OSError):gate.command('build',['owned-build'],720,simulator=False)
                    self.assertEqual(gate.events,[]);self.assertTrue(gate.uncertain);gate.cleanup();self.assertEqual(called.call_count,1)
                    with self.assertRaisesRegex(ValueError,'blocks further'):gate.bootstrap()
        with tempfile.TemporaryDirectory() as folder:
            gate=object.__new__(diagnostic.HostDiagnostic);gate.started=0;gate.deadline=2280
            gate.device='owned';gate.uncertain=False;gate.failures=[];gate.events=[]
            with patch.object(diagnostic,'OUT',Path(folder)),patch('run_swiftui_acceptance.OUT',Path(folder)),patch('time.monotonic',return_value=100),patch('subprocess.call',side_effect=KeyboardInterrupt('build cancelled')) as called:
                with self.assertRaises(KeyboardInterrupt):gate.command('build',['owned-build'],720,simulator=False)
                self.assertTrue(gate.uncertain);gate.cleanup();self.assertEqual(called.call_count,1)

    def testCancellationAfterKnownChildExitStillPreventsNewCleanupDispatch(self):
        from unittest.mock import patch
        import run_ios_photos_host_diagnostic as diagnostic
        for exception in [KeyboardInterrupt('cancelled after exit'),SystemExit(130)]:
            with self.subTest(exception=type(exception).__name__),tempfile.TemporaryDirectory() as folder:
                gate=object.__new__(diagnostic.HostDiagnostic);gate.started=0;gate.deadline=2280
                gate.device='owned';gate.uncertain=False;gate.failures=[];gate.events=[]
                with patch.object(diagnostic,'OUT',Path(folder)),patch('run_swiftui_acceptance.OUT',Path(folder)),patch('time.monotonic',return_value=100),patch('subprocess.call',return_value=0) as called,patch('run_swiftui_acceptance.save',side_effect=exception):
                    with self.assertRaises(type(exception)):gate.command('build',['owned-build'],720,simulator=False)
                    self.assertEqual(gate.events[0]['exit_code'],0);self.assertTrue(gate.uncertain)
                    gate.cleanup();self.assertEqual(called.call_count,1)

    def testActualMainCancellationInFinalReceiptOrBetweenCommandsNeverDispatchesCleanup(self):
        import os
        from unittest.mock import patch
        import run_ios_photos_host_diagnostic as diagnostic
        real_read=Path.read_text;admission={'product_sha':host.PRODUCT_SHA}
        def read(path,*args,**kwargs):
            if path==diagnostic.ROOT/'build/final-photos-host-source-before.json':return json.dumps(admission)
            return real_read(path,*args,**kwargs)
        for where in ['dispatch-timing','between-commands']:
            for failure in [KeyboardInterrupt('cancelled'),SystemExit(130)]:
                with self.subTest(where=where,failure=type(failure).__name__),tempfile.TemporaryDirectory() as folder:
                    gate=object.__new__(diagnostic.HostDiagnostic);gate.started=0;gate.deadline=2280
                    gate.source='a'*40;gate.source_tree='b'*40;gate.device='owned';gate.uncertain=False;gate.failures=[];gate.events=[];final=[]
                    def run():
                        if where=='between-commands':raise failure
                        gate.command('install-owned-app',['owned-command'],210,simulator=True)
                    gate.run=run
                    def save(path,value):
                        if path.name=='install-owned-app-dispatch-timing.json':raise failure
                        if path.name=='acceptance.json':final.append(value)
                    with patch.object(diagnostic,'admit_probe',return_value=admission),patch.object(diagnostic,'HostDiagnostic',return_value=gate),patch.object(diagnostic,'OUT',Path(folder)),patch('run_swiftui_acceptance.OUT',Path(folder)),patch.object(Path,'read_text',read),patch.object(diagnostic,'save',side_effect=save),patch('time.monotonic',return_value=100),patch('subprocess.call',return_value=0) as called,patch.object(diagnostic.signal,'signal'),patch.object(diagnostic.os,'chdir'):
                        self.assertEqual(diagnostic.main(),1)
                    self.assertTrue(gate.uncertain);self.assertEqual(gate.device,'owned');self.assertEqual(called.call_count,1 if where=='dispatch-timing' else 0)
                    self.assertEqual(len(final),1);self.assertTrue(final[0]['simulator_uncertain']);self.assertFalse(final[0]['actual_host_diagnostic_passed'])

    def testExactSplitRemovalRestoresAllHistoricalWrapperBytes(self):
        import hashlib
        source=(Path(__file__).resolve().parents[1]/'Scripts/run_bounded.py').read_text()
        def restore(value):
            for fragment in [PHOTOS_INSTALL_SPLIT_PREFIX,PHOTOS_INSTALL_SPLIT_HELPER,PHOTOS_INSTALL_SPLIT_NATIVE]:
                if value.count(fragment)!=1:raise ValueError('Split fragment changed/duplicated')
            return value.replace(PHOTOS_INSTALL_SPLIT_PREFIX,'').replace(PHOTOS_INSTALL_SPLIT_HELPER,'').replace(PHOTOS_INSTALL_SPLIT_NATIVE,'refuse_expired_parent()\ntry:\n')
        self.assertEqual(hashlib.sha256(restore(source).encode()).hexdigest(),'798a18065939c9787dcf27d42ab1917ee8d7dd4835d9ff48ef6b52e8b4cf1acd')
        changed=source.replace('photos_cleanup_started + 10','photos_cleanup_started + 20');self.assertNotEqual(hashlib.sha256(restore(changed).encode()).hexdigest(),hashlib.sha256(restore(source).encode()).hexdigest())
    def testNoDiagnosticCollectorsOrAppChangeAndFiveStrictStagesRemain(self):
        import hashlib
        root=Path(__file__).resolve().parents[1];driver=(root/'Scripts/run_ios_photos_host_diagnostic.py').read_text();wrapper=(root/'Scripts/run_bounded.py').read_text()
        for token in ['ios_install_observer','InstallObservation','sample_receipt','install-device-log','install-only']:self.assertNotIn(token,driver+wrapper)
        for name in ['ios_install_observer.py','run_ios_install_diagnostic.py','test_ios_install_observer.py','test_ios_install_diagnostic.py']:self.assertFalse((root/'Scripts'/name).exists())
        self.assertEqual(host.product_control(root),(424,host.PRODUCT_CONTROL_SHA256))
        for path,digest in host.PROBE_FIXED_FILES.items():self.assertEqual(hashlib.sha256((root/path).read_bytes()).hexdigest(),digest)
        self.assertEqual([x[2] for x in host.STEPS],[45,165,45,165,45]);self.assertIn("self.command('actual-photos-host', command, 630",driver);self.assertIn("command, 750, simulator=True",driver);self.assertIn("'work_budget_seconds': 2280",driver)


if __name__ == '__main__': unittest.main()
