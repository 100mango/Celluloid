import unittest
from pathlib import Path
from native_watch_profiles import PROFILES, select_profiles

class WatchProfileTests(unittest.TestCase):
    def test_exact_installed_compatible_profiles_in_order(self):
        devices = [dict(name=name, identifier=key) for key, name in PROFILES]
        runtime = dict(supportedDeviceTypes=devices)
        self.assertEqual([key for key, _ in select_profiles(runtime, list(reversed(devices)))], ['baseline','small','large'])
        self.assertEqual([item['name'] for _, item in select_profiles(runtime, devices)], [name for _, name in PROFILES])
    def test_missing_incompatible_or_ambiguous_endpoint_is_not_replaced(self):
        devices = [dict(name=name, identifier=key) for key, name in PROFILES]
        for runtime, candidates in [(dict(supportedDeviceTypes=devices), devices[:-1]),
                                    (dict(supportedDeviceTypes=devices[:-1]), devices),
                                    (dict(supportedDeviceTypes=[]), devices),
                                    (dict(supportedDeviceTypes=devices), devices + [devices[-1]])]:
            with self.assertRaises(ValueError): select_profiles(runtime, candidates)

class WatchConfirmationRevealTests(unittest.TestCase):
    def test_explicit_confirmation_requires_containment_before_early_return(self):
        source=(Path(__file__).resolve().parents[1]/'Platforms/WatchUITests/NativeWatchUITests.swift').read_text()
        reveal=source.split('private func reveal(',1)[1].split('func testSystemPhotosPicker',1)[0]
        self.assertIn('let contained = scrollContainer.map { $0.frame.contains(element.frame) } ?? true',reveal)
        self.assertIn('if element.isHittable && contained { return }',reveal)
        self.assertNotIn('if element.isHittable { return }',reveal)
        self.assertIn('for step in 0..<12',reveal)
        self.assertIn('start.press(forDuration: 0.05, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.2)',reveal)
        self.assertIn('try reveal(confirm, in: app, scrollContainer: reopenedConfirmation)',source)
        self.assertIn('XCTAssertTrue(reopenedConfirmation.frame.contains(confirm.frame))',source)
        self.assertIn('Cancel must preserve the offline copy across relaunch',source)
    def test_observed_small_watch_partial_row_is_not_full_containment(self):
        # Geometry receipt from actual52bf40mm AX tree; this is a portable
        # boundary regression, not a replacement for the existing real UI case.
        def contains(view,rect):
            x,y,w,h=view;a,b,c,d=rect
            return x<=a and y<=b and a+c<=x+w and b+d<=y+h
        viewport=(0,0,162,197);partial=(30,187.5,102,41)
        self.assertFalse(contains(viewport,partial))
        self.assertTrue(contains(viewport,(30,146,102,41)))

if __name__ == '__main__': unittest.main()
