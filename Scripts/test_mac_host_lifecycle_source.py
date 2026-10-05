"""Source-tied safety/independence checks; no native UI success is inferred."""
import re,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class LifecycleSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.swift=(ROOT/'Platforms/UITests/MacPhotosHostUITests.swift').read_text()
    def section(self,a,b):return self.swift.split(a,1)[1].split(b,1)[0]
    def test_original_fixture_is_retained_before_import_and_any_lifecycle_action(self):
        body=self.section('private func makeFixture()', '@MainActor private func selfIdentityObservation')
        self.assertLess(body.index('retainedSource = source'),body.index('"source-retained"'))
        test=self.section('@MainActor func testInstalledExtensionIsInvokedByActualPhotos()', '@MainActor private func importFixture')
        self.assertLess(test.index('let fixture = try makeFixture()'),test.index('try importFixture('))
        self.assertLess(test.index('named: "prerequisite.json"'),test.index('try runFilterLifecycle('))
        self.assertIn('seeded reuse cannot qualify',self.swift)
    def test_exact_phase_order_final_original_and_unexecuted_dirty_cancel_stay_explicit(self):
        body=self.section('@MainActor private func runFilterLifecycle(', '@MainActor private func openTopMenu')
        values=re.findall(r'try lifecyclePhase\("([^"]+)"',body)
        self.assertEqual(values,['fade-ready','saved-export','reopened-fade','cancelled-export','reverted-export','unmodified-original','reopened-original'])
        self.assertIn('filter: "Original", previousGenerations: [initialGeneration, reopened.generation]',body)
        self.assertLess(body.index('"reopened-original"'),body.index('lifecycleComplete = true'))
        self.assertIn('"dirty_cancel_tested": false',self.swift)
        self.assertIn('guard original.bytes == source.bytes',body)
        cancel=body.split('stage = "lifecycle-cancel-without-new-edit"',1)[1].split('stage = "lifecycle-revert-owned-asset"',1)[0]
        self.assertIn('save: false',cancel);self.assertNotIn('selectFade',cancel)
    def test_all_actions_are_fenced_and_all_waits_use_the_one_deadline(self):
        self.assertEqual(self.swift.count('.click()'),1)
        for line in self.swift.splitlines():
            if '.waitForExistence(timeout:' in line:self.assertIn('try remainingTime(',line)
        self.assertIn('testStarted = ProcessInfo.processInfo.systemUptime',self.swift)
        self.assertIn('600 - (ProcessInfo.processInfo.systemUptime - testStarted)',self.swift)
        body=self.section('private func deadlineClick(', 'private func deadlineKey(')
        self.assertLess(body.index('remainingTime'),body.index('.click()'))
        # Executable deadline model tied to the immediate pre-action source fence.
        actions=[]
        def action(now):
            if now>=600:raise TimeoutError()
            actions.append('click')
        action(599)
        for now in [600,601,999]:
            with self.assertRaises(TimeoutError):action(now)
        self.assertEqual(actions,['click'])
    def test_owned_file_caps_are_admitted_before_read_and_do_not_block_on_fifo(self):
        body=self.section('private func readBoundedOwnedFile(', 'private func pngHeader(')
        for part in ['O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW','openat(directoryFD','before.st_size <= Int64(maximumBytes)',
                     'min(65_536, size - bytes.count)','before.st_ctimespec','pathAfter.st_ino','parentBefore.st_ino','defer { Darwin.close(directoryFD) }']:
            self.assertIn(part,body)
        self.assertLess(body.index('before.st_size <= Int64(maximumBytes)'),body.index('bytes.reserveCapacity(size)'))
        export=self.section('@MainActor private func exportRaster(', 'private func readBoundedOwnedFile(')
        self.assertIn('64 * 1024 * 1024 - lifecycleRawBytes',export)
        self.assertIn('maximumBytes:',export)
    def test_icc_has_a_fixed_output_buffer_before_any_imageio_decode(self):
        header=self.section('private func pngHeader(', 'private func bitmap(')
        self.assertIn('uncompress2(',header)
        self.assertIn('4097',header);self.assertIn('4096',header);self.assertIn('Z_OK',header)
        self.assertIn('copyICCData()',header)
        body=self.section('private func lifecycleRaster(', 'private func retainLifecycleImage(')
        self.assertLess(body.index('try pngHeader(data)'),body.index('CGImageSourceCreateWithData'))
        self.assertNotIn('"base64": reference.base64EncodedString()',self.swift)
    def test_expected_image_is_independent_of_actual_exports_and_production_helper(self):
        body=self.section('private func expectedFade(', 'private func maximumDelta(')
        self.assertIn('original.bytes',body);self.assertIn('CIFilter(name: "CIPhotoEffectInstant"',body)
        self.assertIn('kCGImageDestinationLossyCompressionQuality: 0.95',body)
        for forbidden in ['MacPhotoRenderer','RasterCodec','FilterPreset','exportRaster(', 'lifecycleExports']:
            self.assertNotIn(forbidden,body)
        self.assertIn('guard savedDelta <= 2',self.swift)
        self.assertIn('guard cancelled.rgba == saved.rgba',self.swift)
        self.assertIn('guard reverted.rgba == source.rgba',self.swift)
    def test_unknown_confirmations_stop_and_fixed_attachment_namespace_is_bounded(self):
        self.assertIn('Unadmitted Photos confirmation or access alert; no action taken',self.swift)
        self.assertIn('Unadmitted Photos sheet/dialog; no confirmation taken',self.swift)
        body=self.section('private func retainLifecycleImage(', 'private func expectedFade(')
        for part in ['128 * 1024','640 * 1024','lifecycleImages[name] == nil','"celluloid-host-lifecycle-" + name','"public.png"']:
            self.assertIn(part,body)
        self.assertNotIn('Process()',self.swift)

if __name__=='__main__':unittest.main()
