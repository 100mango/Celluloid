import unittest
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

if __name__ == '__main__': unittest.main()
