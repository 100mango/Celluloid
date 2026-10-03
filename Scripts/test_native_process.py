#!/usr/bin/env python3
import os,subprocess,sys,tempfile,unittest
from unittest.mock import patch,MagicMock
from native_process import run
class NativeProcessTests(unittest.TestCase):
    def test_success_and_actual_bounded_timeout(self):
        self.assertEqual(run([sys.executable,'-c','print("synthetic")'],echo=False).stdout.strip(),'synthetic')
        with self.assertRaisesRegex(TimeoutError,'exceeded'):
            run([sys.executable,'-c','import time; print("partial",flush=True); time.sleep(10)'],timeout=0.05,echo=False)
    def test_permission_error_does_not_mask_timeout(self):
        process=MagicMock(pid=123,returncode=None)
        process.communicate.side_effect=[subprocess.TimeoutExpired('owned-process',1,output=b'partial',stderr=b''),('partial','')]
        with patch('native_process.subprocess.Popen',return_value=process),patch('native_process.os.killpg',side_effect=PermissionError('synthetic denial')):
            with self.assertRaisesRegex(TimeoutError,'exceeded.*denied'):
                run(['owned-process'],timeout=1,echo=False)
if __name__=='__main__':unittest.main()
