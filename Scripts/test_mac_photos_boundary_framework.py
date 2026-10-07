"""Exact observed XCTest framework diagnostic; synthetic accounting fixtures only."""
import copy,json,unittest
import consumer_runtime_binding as raw
import mac_photos_boundary_probe as boundary
import test_mac_photos_boundary_probe as fixtures

LINE='2026-10-07 02:55:04.344038+0000 CelluloidMacUITests-Runner[82900:189741] [general] *** Assertion failure in -[XCUIApplication commonInitWithApplicationSpecifier:device:], XCUIApplication.m:226'
INITIAL='MAC_HOST_STAGE photos-first-use-and-synthetic-import snapshot=initial'
IMPORTED='MAC_HOST_STAGE photos-first-use-and-synthetic-import snapshot=imported'
class PhotosFrameworkTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.BoundaryProbeTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
    def transcript(self,result='Failed',line=LINE):
        context,log,summary=self.fixture.transcript(result)
        start=next(x for x in log.splitlines() if x.startswith('Test Case ') and x.endswith('started.'))
        log=log.replace(start,start+'\n'+INITIAL+'\n'+line+'\n'+IMPORTED,1)
        return context,log,summary
    def classify(self,log,summary):return raw.validate_raw_execution(log,summary,photos_import_snapshot_diagnostic=True)
    def test_known_exact_message_is_retained_for_pass_and_real_pixel_failure(self):
        for outcome in ['Passed','Failed']:
            context,log,summary=self.transcript(outcome)
            result=self.classify(log,summary)
            self.assertEqual(result['aggregate_result'],outcome)
            self.assertEqual(len(result['scoped_errors']),int(outcome=='Failed'))
            self.assertEqual(result['non_case_framework_diagnostics'][0]['raw'],LINE)
            self.assertEqual(len(result['non_case_framework_diagnostics']),1)
            boundary.bound_arm(context,log,summary)
    def test_default_all_other_consumers_remain_strict(self):
        for outcome in ['Passed','Failed']:
            _,log,summary=self.transcript(outcome)
            with self.assertRaises(ValueError):raw.validate_raw_execution(log,summary)
    def test_changed_origin_message_line_suffix_or_extra_assertion_still_rejects(self):
        for changed in [LINE.replace('CelluloidMacUITests-Runner','Other-Runner'),LINE.replace('[general]','[app]'),
            LINE.replace('XCUIApplication.m:226','XCUIApplication.m:227'),LINE.replace('commonInitWithApplicationSpecifier:device:','otherMethod:'),
            LINE+' extra',LINE+'\n'+LINE,LINE+'\n*** Assertion failure in unknown component']:
            _,log,summary=self.transcript(line=changed)
            with self.subTest(line=changed),self.assertRaises(ValueError):self.classify(log,summary)
    def test_scope_runtime_phase_and_summary_issue_attribution_cannot_be_forged(self):
        _,log,summary=self.transcript()
        changes=[log.replace(INITIAL,''),log.replace(IMPORTED,''),log.replace(INITIAL,IMPORTED).replace(IMPORTED,INITIAL),
            log.replace('MacPhotosHostUITests','OtherHostUITests')]
        for changed in changes:
            with self.subTest(log=changed[-120:]),self.assertRaises(ValueError):self.classify(changed,summary)
        for device in [{'platform':'iOS Simulator'},dict(summary['devicesAndConfigurations'][0]['device'],osBuildNumber='other')]:
            value=copy.deepcopy(summary);value['devicesAndConfigurations'][0]['device']=device
            with self.assertRaises(ValueError):self.classify(log,value)
        value=copy.deepcopy(summary);value['testFailures'][0]['failureText']=LINE
        with self.assertRaisesRegex(ValueError,'real XCTest issue'):self.classify(log,value)
    def test_passed_summary_with_actual_extra_case_failure_still_rejects(self):
        _,log,summary=self.transcript('Passed')
        extra="Test Case '-[CelluloidMacUITests.OtherTests testActualFailure]' started.\nTest Case '-[CelluloidMacUITests.OtherTests testActualFailure]' failed (1.0 seconds).\n"
        changed=log.replace('Executed 1 test',extra+'Executed 1 test')
        with self.assertRaises(ValueError):self.classify(changed,summary)
        error='/owned/test.swift:1: error: -[CelluloidMacUITests.MacPhotosHostUITests testInstalledExtensionIsInvokedByActualPhotos] : XCTAssertTrue failed'
        changed=log.replace(IMPORTED,IMPORTED+'\n'+error)
        with self.assertRaises(ValueError):self.classify(changed,summary)
    def test_additional_real_issue_or_wrong_terminal_never_grants_boundary_access(self):
        context,log,summary=self.transcript('Failed')
        error='/owned/test.swift:1: error: -[CelluloidMacUITests.MacPhotosHostUITests testInstalledExtensionIsInvokedByActualPhotos] : XCTAssertTrue failed'
        changed=log.replace(IMPORTED,IMPORTED+'\n'+error).replace('with 1 failure (0 unexpected)','with 2 failures (0 unexpected)')
        value=copy.deepcopy(summary);value['testFailures'].append(dict(value['testFailures'][0],failureText='XCTAssertTrue failed'))
        # Consistent real case issues remain visible; the pixel-only boundary
        # stage then rejects the extra actual failure instead of ignoring it.
        self.assertEqual(len(self.classify(changed,value)['scoped_errors']),2)
        with self.assertRaises(ValueError):boundary.bound_arm(context,changed,value)
        with self.assertRaises(ValueError):self.classify(log.replace('** TEST EXECUTE FAILED **','** TEST EXECUTE SUCCEEDED **'),summary)

if __name__=='__main__':unittest.main()
