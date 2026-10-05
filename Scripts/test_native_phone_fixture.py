from pathlib import Path
import hashlib
import json
import tempfile
import shutil
import unittest
from native_phone_fixture import seed, REQUEST_IDS


class NativePhoneFixtureTests(unittest.TestCase):
    def test_lazy_reveal_logging_never_resolves_a_missing_element(self):
        source=(Path(__file__).resolve().parents[1]/'Platforms/PhoneUITests/PhoneCompanionUITests.swift').read_text()
        reveal=source.split('private func reveal(',1)[1].split('private func audit(',1)[0]
        self.assertIn('if element.exists && element.isHittable { return }',reveal)
        self.assertIn('if element.exists {\n                    print("PHONE_COMPANION_REVEAL target=',reveal)
        absent=reveal.split('} else {',1)[1].split('                }',1)[0]
        self.assertIn('target=not-yet-materialized',absent)
        for attribute in ['identifier','frame','label']:
            self.assertNotIn('element.'+attribute,absent)
        self.assertIn('for down in [false, true]',reveal);self.assertIn('for step in 0..<6',reveal)
        self.assertIn('if down { app.swipeDown() } else { app.swipeUp() }',reveal)
        failure=reveal.split('XCTFail(',1)[1]
        self.assertNotIn('element.',failure)
        self.assertIn('try app.performAccessibilityAudit(for: .all)',source)

    def test_seeds_only_two_bounded_hash_bound_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); container = root / 'container'; container.mkdir()
            report = seed(container, root)
            source = Path(report['fixture']).read_bytes()
            self.assertLess(len(source), 8 * 1024 * 1024)
            folder = container / 'Library/Application Support/WatchProcessingResults/Pending'
            self.assertEqual(sorted(p.name for p in folder.iterdir()), REQUEST_IDS)
            for identifier in REQUEST_IDS:
                request = json.loads((folder / identifier / 'request.json').read_text())
                self.assertEqual(request['id'], identifier)
                self.assertEqual(request['sourceBytes'], len(source))
                self.assertEqual(request['sourceSHA256'], hashlib.sha256(source).hexdigest())
                self.assertEqual((folder / identifier / 'source.image').read_bytes(), source)
                self.assertEqual(request['filter'], 'Fade')
            with self.assertRaises(ValueError): seed(container, root)
            self.assertEqual((folder / REQUEST_IDS[0] / 'source.image').read_bytes(), source)


    def test_layout_namespace_cannot_consume_canonical_output_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); container = root / 'container'; container.mkdir()
            canonical = seed(container, root)
            layout = seed(container, root, namespace='large-text')
            self.assertEqual(canonical['namespace'], 'canonical-output')
            self.assertEqual(layout['namespace'], 'large-text')
            base = container / 'Library/Application Support'
            isolated = base / 'WatchProcessingLargeTextUI/Pending'
            before = {p.relative_to(isolated).as_posix(): p.read_bytes() for p in isolated.rglob('*') if p.is_file()}
            shutil.rmtree(base / 'WatchProcessingResults/Pending' / REQUEST_IDS[0])
            self.assertEqual(before, {p.relative_to(isolated).as_posix(): p.read_bytes() for p in isolated.rglob('*') if p.is_file()})
            with self.assertRaises(ValueError): seed(container, root, namespace='../outside')


if __name__ == '__main__': unittest.main()
