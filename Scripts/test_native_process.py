#!/usr/bin/env python3
import os,subprocess,sys,tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch,MagicMock
from native_process import run,optional_diagnostic
class NativeProcessTests(unittest.TestCase):
    def test_success_and_actual_bounded_timeout(self):
        self.assertEqual(run([sys.executable,'-c','print("synthetic")'],echo=False).stdout.strip(),'synthetic')
        with self.assertRaisesRegex(TimeoutError,'exceeded'):
            run([sys.executable,'-c','import time; print("partial",flush=True); time.sleep(10)'],timeout=0.05,echo=False)
    def test_retained_runtime_timing_distinguishes_suites_and_timeout(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, RUNNER_TEMP=directory):
            code = "from datetime import datetime; import time; print(\"Test Suite 'All tests' started at \"+datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')+'.'); time.sleep(.01); print(\"Test Suite 'All tests' passed at \"+datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')+'.')"
            run([sys.executable,'-c',code],echo=False,log_name='test.log')
            timing=json.loads((Path(directory)/'test.log.timing.json').read_text())
            self.assertFalse(timing['timed_out']);self.assertEqual(len(timing['xctest_suite_events']),2)
            self.assertGreaterEqual(timing['observed_suite_span_seconds'],.009)
            self.assertGreaterEqual(timing['command_to_first_suite_seconds'],0)
            self.assertGreaterEqual(timing['last_suite_to_command_end_seconds'],0)
            with self.assertRaises(TimeoutError):run([sys.executable,'-c','import time; print("partial",flush=True);time.sleep(10)'],timeout=.05,echo=False,log_name='timeout.log')
            self.assertTrue(json.loads((Path(directory)/'timeout.log.timing.json').read_text())['timed_out'])
            self.assertIn('partial',(Path(directory)/'timeout.log').read_text())
    def test_optional_capture_timeout_does_not_claim_success_or_suppress_required_test(self):
        with patch('native_process.run',side_effect=TimeoutError('capture exceeded 45 seconds')):
            result=optional_diagnostic(['xcrun','simctl','io','owned-id','screenshot'])
        self.assertFalse(result['succeeded']);self.assertIn('capture exceeded',result['error'])
        self.assertIn('actual tests remain required',result['scope'])
    def test_permission_error_does_not_mask_timeout(self):
        process=MagicMock(pid=123,returncode=None)
        process.communicate.side_effect=[subprocess.TimeoutExpired('owned-process',1,output=b'partial',stderr=b''),('partial','')]
        with patch('native_process.subprocess.Popen',return_value=process),patch('native_process.os.killpg',side_effect=PermissionError('synthetic denial')):
            with self.assertRaisesRegex(TimeoutError,'exceeded.*denied'):
                run(['owned-process'],timeout=1,echo=False)
if __name__=='__main__':unittest.main()
