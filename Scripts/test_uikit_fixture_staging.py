import subprocess, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from stage_uikit_layer_fixture import container_path

class UIKitFixtureStagingTests(unittest.TestCase):
    def test_existing_exact_container_is_read_once_with_a_finite_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('stage_uikit_layer_fixture.run',return_value=subprocess.CompletedProcess([],0,directory+'\n','')) as invoke:
                self.assertEqual(container_path('owned-device','app'),Path(directory))
                invoke.assert_called_once_with(['xcrun','simctl','get_app_container','owned-device','Mango.Celluloid','app'],timeout=120)
    def test_missing_relative_empty_and_unknown_paths_fail_closed(self):
        for value in ['','relative/path','/path/that/does/not/exist']:
            with patch('stage_uikit_layer_fixture.run',return_value=subprocess.CompletedProcess([],0,value,'')):
                with self.assertRaises(ValueError):container_path('owned-device','data')
        with patch('stage_uikit_layer_fixture.run') as invoke:
            with self.assertRaises(ValueError):container_path('owned-device','arbitrary')
            invoke.assert_not_called()
    def test_timeout_cannot_substitute_for_registration(self):
        with patch('stage_uikit_layer_fixture.run',side_effect=TimeoutError('not registered')) as invoke:
            with self.assertRaises(TimeoutError):container_path('owned-device','app')
            self.assertEqual(invoke.call_count,1)
    def test_cold_vision_launch_keeps_bounded_actual_app_and_xctest_checks(self):
        root=Path(__file__).resolve().parents[1]
        source=(root/'Scripts/run_native_vision.py').read_text()
        self.assertIn("timeout=180,log_name='vision-launch.log'",source)
        self.assertIn("assert pid.isdigit()",source)
        self.assertIn("assert 'CelluloidVision' in proc.stdout",source)
        self.assertIn("'test-without-building'",source)
        self.assertIn('timeout=900',source)
        workflow=(root/'.github/workflows/apple-platforms.yml').read_text()
        self.assertIn("python3 -m unittest discover -s Scripts -p 'test_*.py' -v",workflow)

if __name__=='__main__':unittest.main()
