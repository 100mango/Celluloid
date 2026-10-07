"""Real local Python subprocess regressions only; never Xcode, simulator or CI."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import tv_archive_capture as local
import tv_release_archive as archive


class CapturePrefixTests(unittest.TestCase):
    def stopped_command(self, code, *, seconds=.20, cap=256, **kwargs):
        receipts=[]
        with self.assertRaisesRegex(archive.Rejected,'capture-stopped'):
            archive.command([sys.executable,'-c',code],deadline=time.monotonic()+8,
                            seconds=seconds,cap=cap,receipts=receipts,**kwargs)
        self.assertEqual(len(receipts),1)
        self.assertFalse(receipts[0]['complete'])
        self.assertLessEqual(len(receipts[0].get('stdout','').encode())+
                             len(receipts[0].get('stderr','').encode()),cap)
        return receipts[0]

    def test_real_timeout_retains_both_streams_and_confirmed_cleanup(self):
        code="import os,time;os.write(1,b'TV_OUT_PREFIX\\n');os.write(2,b'TV_ERR_PREFIX\\n');time.sleep(30)"
        value=self.stopped_command(code)
        self.assertEqual(value['reason'],'duration-limit')
        self.assertEqual(value['stdout'],'TV_OUT_PREFIX\n')
        self.assertEqual(value['stderr'],'TV_ERR_PREFIX\n')
        self.assertTrue(value['owned_cleanup_confirmed'])
        self.assertIsNone(value['cancelled_signal'])

    def test_real_byte_overflow_retains_the_crossing_chunk_only_to_shared_cap(self):
        value=self.stopped_command("import os,time;os.write(1,b'A'*100000);time.sleep(30)",cap=257,seconds=2)
        self.assertEqual(value['reason'],'byte-limit')
        self.assertEqual(value['stdout'],'A'*257)
        self.assertEqual(value['stderr'],'')
        self.assertTrue(value['owned_cleanup_confirmed'])

    def test_real_mixed_stream_overflow_retains_combined_budget(self):
        code="import os,time;os.write(2,b'E'*7);time.sleep(.05);os.write(1,b'O'*10000);time.sleep(30)"
        value=self.stopped_command(code,cap=31,seconds=2)
        self.assertEqual(value['reason'],'byte-limit')
        self.assertEqual(value['stderr'],'E'*7)
        self.assertEqual(value['stdout'],'O'*24)
        self.assertTrue(value['owned_cleanup_confirmed'])

    def test_real_signal_cancellation_keeps_prefixes_and_never_qualifies(self):
        # Isolate the signal-handler test in a subprocess, not the unittest host.
        producer="import os,time,signal;os.write(1,b'CANCEL_OUT\\n');os.write(2,b'CANCEL_ERR\\n');time.sleep(.15);os.kill(os.getppid(),signal.SIGTERM);time.sleep(30)"
        harness="""import json,sys,time
import tv_release_archive as a
receipts=[]
try:
 a.command([sys.executable,'-c',sys.argv[1]],deadline=time.monotonic()+8,seconds=3,cap=128,receipts=receipts)
except a.Rejected:
 pass
print(json.dumps(receipts))
"""
        env=dict(os.environ);env['PYTHONPATH']=str(Path(__file__).resolve().parent)
        result=subprocess.run([sys.executable,'-c',harness,producer],env=env,capture_output=True,timeout=8,check=True)
        values=json.loads(result.stdout);self.assertEqual(len(values),1);value=values[0]
        self.assertFalse(value['complete'])
        self.assertEqual(value['cancelled_signal'],signal.SIGTERM)
        self.assertEqual(value['reason'],'interrupted-by-signal-'+str(signal.SIGTERM))
        self.assertEqual(value['stdout'],'CANCEL_OUT\n')
        self.assertEqual(value['stderr'],'CANCEL_ERR\n')
        self.assertTrue(value['owned_cleanup_confirmed'])

    def test_prefix_survives_unconfirmed_cleanup_without_becoming_success(self):
        # Real producer and real cleanup; only its reported certainty is lowered.
        original=local.stop_group
        def uncertain(process,*,grace):
            original(process,grace=grace)
            return False
        with patch.object(local,'stop_group',uncertain):
            value=self.stopped_command("import os,time;os.write(1,b'UNCERTAIN\\n');time.sleep(30)")
        self.assertEqual(value['stdout'],'UNCERTAIN\n')
        self.assertFalse(value['owned_cleanup_confirmed'])
        self.assertFalse(value['complete'])

    def test_success_and_nonzero_outputs_keep_existing_capture_semantics(self):
        code="import os,sys;os.write(1,b'OUT');os.write(2,b'ERR');sys.exit(3)"
        a=local.capture([sys.executable,'-c',code],seconds=2,cap=32)
        b=subprocess.run([sys.executable,'-c',code],capture_output=True,timeout=2)
        self.assertEqual((a.returncode,a.stdout,a.stderr),(b.returncode,b.stdout,b.stderr))
        receipts=[]
        with self.assertRaisesRegex(archive.Rejected,'command-failed'):
            archive.command([sys.executable,'-c',code],deadline=time.monotonic()+8,seconds=2,cap=32,receipts=receipts)
        self.assertFalse(receipts[0]['complete'])
        self.assertEqual((receipts[0]['stdout'],receipts[0]['stderr']),('OUT','ERR'))

    def test_signal_handlers_are_restored_after_failure(self):
        before={s:signal.getsignal(s) for s in (signal.SIGTERM,signal.SIGINT)}
        self.stopped_command("import time;time.sleep(30)")
        self.assertEqual({s:signal.getsignal(s) for s in before},before)


if __name__=='__main__':unittest.main()
