import base64, importlib.util, json, os, pathlib, re, stat, subprocess, sys, tempfile, unittest

from unittest import mock

BASE = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('private_workspace', BASE/'scripts/private_workspace.py')
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name).resolve()
    def tearDown(self):
        self.temp.cleanup()
    def test_requires_all_hosted_environment_values(self):
        allowed = {'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted','RUNNER_OS':'macOS'}
        w.require_hosted_runner(allowed)
        for key in allowed:
            wrong = dict(allowed); wrong[key] = 'wrong'
            with self.assertRaises(ValueError): w.require_hosted_runner(wrong)
        with self.assertRaises(ValueError): w.require_hosted_runner({})
    def test_only_new_owned_workspace_is_removed(self):
        profile = self.root/'HOME/Library/MobileDevice/Provisioning Profiles/keep.mobileprovision'
        profile.parent.mkdir(parents=True); profile.write_text('synthetic-existing-profile')
        other = self.root/'unrelated'; other.mkdir(); (other/'keep.txt').write_text('keep')
        folder = w.create(self.root)
        self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((folder/w.MARKER).stat().st_mode), 0o600)
        (folder/'generated-private-placeholder').write_text('not-a-credential')
        w.cleanup(self.root,folder)
        self.assertFalse(folder.exists()); self.assertTrue(profile.exists()); self.assertTrue(other.exists())
        w.cleanup(self.root,folder)  # repeated cleanup is harmless
    def test_symlink_root_rejected(self):
        link = self.root/'link'; link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError): w.create(link)
    def test_outside_or_parent_workspace_rejected(self):
        with self.assertRaises(ValueError): w.cleanup(self.root,self.root)
        with self.assertRaises(ValueError): w.cleanup(self.root,self.root.parent/'cloud-signing.abcdefgh')
    def test_arbitrary_existing_prefixed_directory_kept(self):
        folder = self.root/'cloud-signing.abcdefgh'; folder.mkdir(mode=0o700)
        with self.assertRaises(FileNotFoundError): w.cleanup(self.root,folder)
        self.assertTrue(folder.exists())
    def test_workspace_symlink_is_never_followed(self):
        other = self.root/'other'; other.mkdir(); (other/'keep').write_text('keep')
        link = self.root/'cloud-signing.abcdefgh'; link.symlink_to(other,target_is_directory=True)
        with self.assertRaises(ValueError): w.cleanup(self.root,link)
        self.assertTrue((other/'keep').exists())
    def test_nested_symlink_target_kept(self):
        other = self.root/'other'; other.mkdir(); (other/'keep').write_text('keep')
        folder = w.create(self.root); (folder/'linked-output').symlink_to(other,target_is_directory=True)
        w.cleanup(self.root,folder)
        self.assertTrue((other/'keep').exists())
    def test_invalid_marker_or_modes_fail_closed(self):
        folder = w.create(self.root); (folder/w.MARKER).write_text('{}')
        with self.assertRaises(ValueError): w.cleanup(self.root,folder)
        (folder/w.MARKER).write_text(json.dumps(w.MARKER_VALUE)); folder.chmod(0o755)
        with self.assertRaises(ValueError): w.cleanup(self.root,folder)
        self.assertTrue(folder.exists())
    def test_marker_symlink_rejected_without_target_read(self):
        folder = w.create(self.root); (folder/w.MARKER).unlink()
        target = self.root/'do-not-read'; target.write_text('synthetic')
        (folder/w.MARKER).symlink_to(target)
        with self.assertRaises((ValueError, OSError)): w.cleanup(self.root,folder)
        self.assertTrue(target.exists())
    def test_swap_to_symlink_at_removal_does_not_touch_target(self):
        folder = w.create(self.root)
        target = self.root/'existing-profiles'; target.mkdir(); (target/'keep').write_text('keep')
        original = w.shutil.rmtree
        def raced(path, **kwargs):
            folder.rename(self.root/'moved-owned-workspace')
            folder.symlink_to(target, target_is_directory=True)
            return original(path, **kwargs)
        raced.avoids_symlink_attacks = True
        with mock.patch.object(w.shutil, 'rmtree', raced):
            with self.assertRaises(OSError): w.cleanup(self.root,folder)
        self.assertTrue((target/'keep').exists())
    def test_requires_descriptor_safe_removal(self):
        folder = w.create(self.root)
        with mock.patch.object(w.shutil.rmtree, 'avoids_symlink_attacks', False):
            with self.assertRaises(ValueError): w.cleanup(self.root,folder)
        self.assertTrue(folder.exists())
    def test_cli_rejection_is_fixed_and_does_not_echo_environment(self):
        env={'PATH':os.environ.get('PATH',''),'GITHUB_ACTIONS':'wrong-CANARY','RUNNER_ENVIRONMENT':'self-hosted','RUNNER_OS':'Linux'}
        result=subprocess.run([sys.executable,str(BASE/'scripts/private_workspace.py'),'check-runner'],env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,1); self.assertEqual(result.stdout,'')
        self.assertEqual(result.stderr,'SIGNING_WORKSPACE_GUARD_FAILED\n')
    def test_signer_guard_before_secret_and_no_broad_deletion(self):
        source=(BASE/'scripts/sign_export.sh').read_text()
        self.assertLess(source.index('private_workspace.py" check-runner'),source.index('${ASC_PRIVATE_KEY_P8'))
        self.assertNotIn('rm -rf',source)
        self.assertIn('private_workspace.py" cleanup',source)
        self.assertNotIn('set -x',source)
    def test_no_embedded_private_key_like_pem_payload_in_controller(self):
        # Do not print matched bytes. Delimiter validation and clearly invalid
        # CANARY test strings are distinct from a serialized PEM payload.
        pattern=re.compile(rb'-----BEGIN (?:EC |RSA )?PRIVATE KEY-----\r?\n[A-Za-z0-9+/=\r\n]{64,}-----END (?:EC |RSA )?PRIVATE KEY-----')
        matches=[]
        for path in BASE.rglob('*'):
            if path.is_file() and path.suffix in {'.py','.sh','.json','.md','.yml'}:
                if pattern.search(path.read_bytes()): matches.append(str(path.relative_to(BASE)))
        self.assertEqual(matches,[],'Unexpected PEM-like payload in controller source')
        begin='-----BEGIN PRIVATE KEY-----'; end='-----END PRIVATE KEY-----'
        synthetic=(begin+'\n'+base64.b64encode(b'synthetic regression fixture, not key material'*3).decode()+'\n'+end).encode()
        self.assertIsNotNone(pattern.search(synthetic))

if __name__ == '__main__': unittest.main(verbosity=2)
