"""Portable source/guard regressions; not Swift compilation or hosted AX proof."""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import native_text_release_guard as guard

ROOT = Path(__file__).resolve().parents[1]
SWIFT = {
    'controller': 'Platforms/macOSExtension/MacPhotoEditingController.swift',
    'view': 'Platforms/macOSExtension/MacPhotoEditorView.swift',
    'identity': 'Platforms/macOSExtension/MacPhotoSelfIdentity.swift',
    'tests': 'Platforms/MacExtensionTests/MacPhotoSelfIdentityTests.swift',
}


def release_projection(source):
    """Lexical DEBUG projection only; unexpected conditional syntax fails closed."""
    stack, branches, result = [True], [], []
    for line in source.splitlines(keepends=True):
        directive = line.strip()
        if directive == '#if DEBUG':
            stack.append(False); branches.append(False)
        elif directive == '#else':
            if len(stack) < 2 or branches[-1]:
                raise ValueError('Unpaired or repeated else')
            branches[-1] = True
            stack[-1] = stack[-2] and not stack[-1]
        elif directive == '#endif':
            if len(stack) < 2:
                raise ValueError('Unpaired endif')
            stack.pop(); branches.pop()
        elif directive.startswith(('#if ', '#elseif ')):
            raise ValueError('Unreviewed conditional')
        elif stack[-1]:
            result.append(line)
    if len(stack) != 1:
        raise ValueError('Unclosed conditional')
    return ''.join(result)


class ReleaseBinaryGuardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.app = Path(self.temporary.name) / 'CelluloidMac.app'
        self.directory = self.app.joinpath(*guard.DIRECTORIES)
        self.directory.mkdir(parents=True)
        self.main = self.directory / guard.EXECUTABLE
        self.dylib = self.directory / guard.DEBUG_DYLIB
        self.main.write_bytes(b'clean synthetic Release executable')

    def test_clean_main_and_optional_clean_fixed_dylib_pass(self):
        self.assertTrue(guard.qualified_extension_has_no_hooks(self.app))
        self.dylib.write_bytes(b'clean synthetic optional dylib')
        self.assertTrue(guard.qualified_extension_has_no_hooks(self.app))

    def test_old_and_new_markers_fail_in_each_exact_file(self):
        self.assertEqual(guard.MARKERS[:2], (b'TextRenderProbe', b'textRenderProbe'))
        for file in (self.main, self.dylib):
            for marker in guard.MARKERS:
                with self.subTest(file=file.name, marker=marker):
                    file.write_bytes(b'prefix' + marker + b'suffix')
                    self.assertFalse(guard.qualified_extension_has_no_hooks(self.app))
            file.write_bytes(b'clean')

    def test_markers_split_across_read_boundaries_fail(self):
        for marker in guard.MARKERS:
            self.main.write_bytes(b'x' * (guard.CHUNK_BYTES - 3) + marker + b'end')
            self.assertFalse(guard.qualified_extension_has_no_hooks(self.app), marker)

    def test_missing_empty_oversized_and_nonregular_files_fail(self):
        self.main.unlink()
        self.assertFalse(guard.qualified_extension_has_no_hooks(self.app))
        for file in (self.main, self.dylib):
            self.main.write_bytes(b'clean')
            file.write_bytes(b'')
            self.assertFalse(guard.qualified_extension_has_no_hooks(self.app))
            with file.open('wb') as stream:
                stream.truncate(guard.MAX_BINARY_BYTES + 1)
            self.assertFalse(guard.qualified_extension_has_no_hooks(self.app))
            file.unlink(); file.mkdir()
            self.assertFalse(guard.qualified_extension_has_no_hooks(self.app))
            file.rmdir(); file.write_bytes(b'clean')

    def test_file_and_directory_symlinks_fail_including_dangling_dylib(self):
        for file in (self.main, self.dylib):
            target = self.app / 'clean-target'
            target.write_bytes(b'clean')
            file.unlink(missing_ok=True); file.symlink_to(target)
            self.assertFalse(guard.qualified_extension_has_no_hooks(self.app))
            target.unlink()
            self.assertFalse(guard.qualified_extension_has_no_hooks(self.app))
            file.unlink(); file.write_bytes(b'clean')
        moved = self.directory.with_name('real-MacOS')
        self.directory.rename(moved); self.directory.symlink_to(moved, target_is_directory=True)
        self.assertFalse(guard.qualified_extension_has_no_hooks(self.app))

    def test_symlinked_app_and_hardlinked_binary_fail(self):
        alias = self.app.with_name('alias.app'); alias.symlink_to(self.app, target_is_directory=True)
        self.assertFalse(guard.qualified_extension_has_no_hooks(alias))
        os.link(self.main, self.app / 'other-name')
        self.assertFalse(guard.qualified_extension_has_no_hooks(self.app))

    def test_unrelated_siblings_are_never_scanned(self):
        (self.directory / 'unrelated.debug.dylib').write_bytes(guard.MARKERS[0])
        (self.directory / 'unrelated-symlink').symlink_to('/absent')
        self.assertTrue(guard.qualified_extension_has_no_hooks(self.app))

    def test_truncation_growth_same_size_mutation_and_replacement_fail(self):
        original_read = os.read
        for operation in ('truncate', 'grow', 'same-size', 'replace'):
            self.main.write_bytes(b'clean' * 100)
            changed = False
            def mutate(fd, count):
                nonlocal changed
                data = original_read(fd, count)
                if data and not changed:
                    changed = True
                    if operation == 'truncate': self.main.write_bytes(b'c')
                    elif operation == 'grow': self.main.write_bytes(b'clean' * 101)
                    elif operation == 'same-size': self.main.write_bytes(b'other' * 100)
                    else:
                        replacement = self.directory / 'replacement'
                        replacement.write_bytes(b'clean' * 100); replacement.replace(self.main)
                return data
            with self.subTest(operation=operation), patch.object(guard.os, 'read', side_effect=mutate):
                self.assertFalse(guard.qualified_extension_has_no_hooks(self.app))

    def test_all_open_descriptors_close_even_when_initial_fstat_fails(self):
        original_open, original_close, original_stat = os.open, os.close, os.fstat
        for fail_at in (1, 2):
            opened, closed, count = [], [], 0
            def tracked_open(*args, **kwargs):
                fd = original_open(*args, **kwargs); opened.append(fd); return fd
            def tracked_close(fd):
                closed.append(fd); return original_close(fd)
            def failed_stat(fd):
                nonlocal count
                count += 1
                if count == fail_at: raise OSError('synthetic fstat failure')
                return original_stat(fd)
            with patch.object(guard.os, 'open', side_effect=tracked_open), \
                 patch.object(guard.os, 'close', side_effect=tracked_close), \
                 patch.object(guard.os, 'fstat', side_effect=failed_stat):
                self.assertFalse(guard.qualified_extension_has_no_hooks(self.app))
            self.assertEqual(sorted(opened), sorted(closed))

    def test_optional_dylib_appearing_after_observation_fails(self):
        original_scan = guard._scan_binary
        def changed(directory, name, required, check):
            result = original_scan(directory, name, required, check)
            if name == guard.DEBUG_DYLIB:
                self.dylib.write_bytes(guard.MARKERS[2])
            return result
        with patch.object(guard, '_scan_binary', side_effect=changed):
            self.assertFalse(guard.qualified_extension_has_no_hooks(self.app))

    def test_read_error_and_cooperative_budget_fail_closed(self):
        with patch.object(guard.os, 'read', side_effect=OSError('synthetic read failure')):
            self.assertFalse(guard.qualified_extension_has_no_hooks(self.app))
        with patch.object(guard.time, 'monotonic', side_effect=[0, guard.MAX_SECONDS + 1]):
            self.assertFalse(guard.qualified_extension_has_no_hooks(self.app))


class SelfIdentitySourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = {name: (ROOT / path).read_text() for name, path in SWIFT.items()}

    def test_release_projection_preserves_exact_prechange_controller_and_view(self):
        expected = {'controller': '74bafc3581765aa269fe06aca6f4885d1279b1e64ac071befc252089e70100e1',
                    'view': 'bd592449babea5b244f44944d61ed55e9fa92725a15f4ecf3bcb918b35cd5387'}
        for name, source in self.sources.items():
            projected = release_projection(source)
            if name in expected:
                self.assertEqual(hashlib.sha256(projected.encode()).hexdigest(), expected[name])
            else:
                self.assertEqual(projected.strip(), '')
            for marker in guard.MARKERS[2:]:
                self.assertNotIn(marker.decode(), projected)

    def test_projection_rejects_unreviewed_or_unbalanced_conditionals(self):
        for source in ('#if DEBUG\nmissing end', '#else\n', '#endif\n', '#if RELEASE\n', '#elseif DEBUG\n', '#if DEBUG\n#else\n#else\n#endif\n'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                release_projection(source)

    def test_controller_captures_only_after_start_and_invalidates_finish_cancel(self):
        source = self.sources['controller']
        start = source.split('func startContentEditing(', 1)[1].split('func finishContentEditing(', 1)[0]
        self.assertLess(start.index('cancelContentEditing()'), start.index('session.begin('))
        self.assertLess(start.index('session.begin('), start.index('selfIdentity.contentEditingStarted()'))
        self.assertEqual(source.count('selfIdentity.contentEditingStarted()'), 1)
        finish = source.split('func finishContentEditing(', 1)[1].split('var shouldShowCancelConfirmation', 1)[0]
        cancel = source.split('func cancelContentEditing()', 1)[1]
        for body in (finish, cancel):
            self.assertLess(body.index('selfIdentity.invalidate()'), body.index('generation = UUID()'))

    def test_generation_publication_invalidation_and_live_ready_value_are_guarded(self):
        source = self.sources['identity']
        start = source.split('func contentEditingStarted()', 1)[1].split('func invalidate()', 1)[0]
        self.assertLess(start.index('invalidate()'), start.index('let token = UUID()'))
        self.assertLess(start.index('let observed = await worker.value'), start.index('generation == token'))
        self.assertLess(start.index('generation == token'), start.index('value = observed'))
        self.assertIn('guard !Task.isCancelled, let self,', start)
        invalidation = source.split('func invalidate()', 1)[1].split('func readyValue(', 1)[0]
        self.assertLess(invalidation.index('generation = nil; value = nil'), invalidation.index('captureTask?.cancel()'))
        for token in ('session.editable', 'session.preview != nil', 'session.placeholder == nil',
                      '!session.loading', '!session.rendering', '!session.finishing', '!session.readOnly',
                      'session.error == nil', 'window != nil', '!isHiddenOrHasHiddenAncestor',
                      'override func accessibilityValue() -> Any? { currentValue }'):
            self.assertIn(token, source)
        self.assertIn('identity.readyValue(for: session)', source)
        self.assertIn('MacPhotoSelfIdentityAccessibility(identity: selfIdentity, session: session)', self.sources['view'])

    def test_capture_is_fixed_own_identity_bounded_and_native_guard_tests_remain(self):
        source = self.sources['identity']
        for token in ('let ownBundle = Bundle.main', 'ProcessInfo.processInfo.processIdentifier',
                      'maximumFileBytes = 32 * 1_024 * 1_024', 'count: 64 * 1_024',
                      'maximumNanoseconds: UInt64 = 10_000_000_000', 'maximumJSONBytes = 8_192',
                      'O_NOFOLLOW', 'AT_SYMLINK_NOFOLLOW', 'deinit { close(fd) }',
                      'try Task.checkCancellation()', '"content_editing_started": true'):
            self.assertIn(token, source)
        for forbidden in ('Process()', 'runningApplications', 'proc_pid', 'sysctl(', 'environment[',
                          'CommandLine.', 'source_sha', 'readDataToEndOfFile'):
            self.assertNotIn(forbidden, source)
        self.assertEqual(self.sources['tests'].count('func testSelfIdentity'), 3)
        self.assertIn('XCTAssertThrowsError(try MacPhotoSelfIdentityCapture.observe', self.sources['tests'])
        self.assertIn('XCTAssertNotEqual(identity.generation, first)', self.sources['tests'])
        self.assertIn('XCTAssertFalse(view.isAccessibilityElement())', self.sources['tests'])


if __name__ == '__main__':
    unittest.main()
