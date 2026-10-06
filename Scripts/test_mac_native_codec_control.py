"""Portable review contracts for the isolated native control; no Swift/runtime claim."""
from pathlib import Path
import hashlib
import runpy
import unittest
import mac_host_lifecycle_pixels as pixels

ROOT = Path(__file__).resolve().parents[1]
CONTROL = ROOT / 'Platforms/MacExtensionTests/MacPhotoNativeCodecControlTests.swift'
SOURCE = ROOT / 'Platforms/MacExtensionTests/Fixtures/lifecycle-source.png'
SOURCE_SHA = '6138992615dd7d5bd499b80d9f11e39a0815111feccd5d4d3e59a676f4384772'


def method(text, name):
    prefix = '    private ' + ('static ' if name == 'validateInternationalText' else '') + 'func ' + name + '('
    start = text.index(prefix)
    end = text.index('\n    }', start) + len('\n    }')
    return text[start:end]


class NativeCodecControlContracts(unittest.TestCase):
    def test_exact_retained_source_and_existing_independent_png_admission(self):
        raw = SOURCE.read_bytes()
        self.assertEqual(len(raw), 19268)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), SOURCE_SHA)
        value = pixels.decode(raw)
        self.assertEqual((value['width'], value['height'], value['color_type']), (1200, 800, 6))
        self.assertEqual((value['profile'], value['alpha']), ('sRGB', 'opaque'))
        self.assertEqual(value['rgba_sha256'], 'a9424d913bfa4b18a70063fec1e05cdb4d679f5619d12897571e6b5868d22717')

    def test_host_oracle_and_pixel_admission_are_literal_except_declared_capture(self):
        host = (ROOT / 'Platforms/UITests/MacPhotosHostUITests.swift').read_text()
        control = CONTROL.read_text()
        self.assertEqual(hashlib.sha256(host.encode()).hexdigest(),
                         '67bdca402040600b35a2e452a13049b4a44bd55df797596a32e8c460e9eb4fb0')
        for name in ('pngHeader', 'admitInternationalText', 'validateInternationalText', 'admitICC',
                     'bitmap', 'lifecycleRaster', 'expectedFade', 'maximumDelta'):
            expected = method(host, name).replace('        _ = try remainingTime(1)\n', '')
            actual = '\n'.join(line for line in method(control, name).splitlines() if not line.endswith('// CONTROL_CAPTURE'))
            self.assertEqual(actual, expected, name)
        self.assertEqual(sum(line.endswith('// CONTROL_CAPTURE') for line in control.splitlines()), 3)
        reference = method(control, 'expectedFade')
        self.assertNotIn('RasterCodec', reference)
        self.assertNotIn('MacPhotoRender', reference)
        self.assertNotIn('FilterPreset', reference)

    def test_new_source_and_resource_belong_only_to_existing_extension_test_target(self):
        graph = runpy.run_path(str(ROOT / 'Scripts/generate_native_project.py'))
        objects = graph['objects']
        wanted = {CONTROL.relative_to(ROOT).as_posix(), SOURCE.relative_to(ROOT).as_posix()}
        owners = {path: [] for path in wanted}
        for name, identifier in graph['targets'].items():
            for phase_id in objects[identifier]['buildPhases']:
                for build_id in objects[phase_id]['files']:
                    reference = objects[build_id].get('fileRef')
                    path = objects.get(reference, {}).get('path')
                    if path in owners:
                        owners[path].append(name)
        self.assertEqual(owners, {path: ['CelluloidMacPhotosExtensionTests'] for path in wanted})


if __name__ == '__main__':
    unittest.main()
