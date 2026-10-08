#!/usr/bin/env python3
import base64,hashlib,json,tempfile,unittest
from pathlib import Path
from native_fixture_handoff import FILTERS,from_log,load_exact
class FixtureHandoffTests(unittest.TestCase):
    def build(self,folder):
        data=b'synthetic archive test bytes';encoded=base64.b64encode(data).decode();sha=hashlib.sha256(data).hexdigest()
        log=folder/'mac.log';log.write_text('\n'.join(f'MAC_FILTER_ONLY_FIXTURE filter={name} sha256={sha} base64={encoded}' for name in sorted(FILTERS)))
        with log.open('a') as f:f.write('\nMAC_BAKED_BASE_FIXTURE '+json.dumps({'identifier':'Mango.CelluloidPhotoExtension','version':'2.0-baked-base','sha256':sha,'base64':encoded}))
        blob=from_log(log,'exact-test-head');(folder/'mac-filter-fixtures.json').write_bytes(blob)
        manifest={'source_sha':'exact-test-head','files':[{'name':'mac-filter-fixtures.json','bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest()}]}
        (folder/'manifest.json').write_text(json.dumps(manifest));return blob
    def test_exact_head_all_filters_and_hashes(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);self.build(folder)
            self.assertEqual({x['filter'] for x in load_exact(folder,'exact-test-head')['fixtures']},FILTERS)
            with self.assertRaisesRegex(ValueError,'exact validation commit'):load_exact(folder,'other-head')
            p=folder/'mac-filter-fixtures.json';p.write_bytes(p.read_bytes()+b' ')
            with self.assertRaisesRegex(ValueError,'manifest/hash'):load_exact(folder,'exact-test-head')
    def test_missing_duplicate_bad_hash_and_oversized_handoff_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);self.build(folder);p=folder/'mac.log';original=p.read_text()
            p.write_text(original+'\n'+original.splitlines()[0])
            with self.assertRaisesRegex(ValueError,'ten synthetic'):from_log(p,'head')
            p.write_text('\n'.join(original.splitlines()[1:]))
            with self.assertRaisesRegex(ValueError,'ten synthetic'):from_log(p,'head')
            p.write_text(original.replace('sha256=','sha256='+('0'*64)+' ignored=',1))
            with self.assertRaises(ValueError):from_log(p,'head')
            (folder/'mac-filter-fixtures.json').write_bytes(b'x'*100001)
            with self.assertRaisesRegex(ValueError,'bounded'):load_exact(folder,'exact-test-head')
if __name__=='__main__':unittest.main()
