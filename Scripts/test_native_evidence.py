#!/usr/bin/env python3
"""Linux-safe regression test for the outbound evidence budget. No Apple tooling needed."""
from pathlib import Path
import hashlib,json,os,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
class EvidenceBudgetTests(unittest.TestCase):
    def test_log_tails_markers_and_oversize_image_are_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            with (folder/'domain.log').open('wb') as handle:
                for _ in range(256):handle.write(b'x'*256_000)
                handle.write(b'\nTest Case synthetic passed\n')
            (folder/'native-vision-launch.png').write_bytes(b'\x89PNG\r\n\x1a\n'+b'x'*5_000_000)
            result=subprocess.run(['python3',str(ROOT/'Scripts/collect_native_evidence.py')],env=dict(os.environ,RUNNER_TEMP=directory,GITHUB_SHA='synthetic'),capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            output=folder/'celluloid-bounded-evidence'
            manifest=json.loads((output/'manifest.json').read_text())
            self.assertEqual(manifest['limits'],{'per_file_bytes':5_000_000,'total_bytes':20_000_000,'retention_days':1})
            self.assertIn('Test Case synthetic passed',(output/'domain.log.summary.txt').read_text())
            self.assertLessEqual((output/'domain.log.tail.txt').stat().st_size,200_000)
            self.assertFalse((output/'native-vision-launch.png').exists())
            self.assertEqual(manifest['omissions'][0]['reason'],'evidence byte cap')
            self.assertLessEqual(sum(p.stat().st_size for p in output.iterdir()),20_000_000)
            for record in manifest['files']:
                data=(output/record['name']).read_bytes();self.assertEqual(hashlib.sha256(data).hexdigest(),record['sha256']);self.assertLessEqual(len(data),5_000_000)
            again=subprocess.run(['python3',str(ROOT/'Scripts/collect_native_evidence.py')],env=dict(os.environ,RUNNER_TEMP=directory),capture_output=True,text=True)
            self.assertNotEqual(again.returncode,0,'A nonempty destination must not be merged into an upload')
if __name__=='__main__':unittest.main()
