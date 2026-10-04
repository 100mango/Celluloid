import base64, hashlib, json, struct, tempfile, unittest, zlib
from pathlib import Path
from native_fixture_handoff import layer_from_log, load_layer_exact, validate_layer, LAYER_FILE, LAYER_COMPONENTS

class LayerFixtureHandoffTests(unittest.TestCase):
    def row(self):
        def chunk(kind,data): return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
        png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',480,640,8,6,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\x20\x40\x80\xff'*480)*640))+chunk(b'IEND',b'')
        archive=b'synthetic structural handoff bytes, not a decoded NSKeyedArchive'
        row={'name':'manufactured-affine','identifier':'Mango.CelluloidPhotoExtension','version':'1.0'}
        for key,sha,data in [('base64','sha256',archive),('sourceBase64','sourceSHA256',png),('renderedBase64','renderedSHA256',png)]: row[key]=base64.b64encode(data).decode();row[sha]=hashlib.sha256(data).hexdigest()
        return row
    def package(self,root):
        (root/'mac.log').write_text('MAC_LAYER_ADJUSTMENT_FIXTURE '+json.dumps(self.row())+'\n')
        data=layer_from_log(root/'mac.log','a'*40);(root/LAYER_FILE).write_bytes(data)
        (root/'manifest.json').write_text(json.dumps({'source_sha':'a'*40,'files':[{'name':LAYER_FILE,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}]}))
        return data
    def test_exact_source_manifest_and_three_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.package(root)
            self.assertEqual(load_layer_exact(root,'a'*40)['fixture'],self.row())
            with self.assertRaisesRegex(ValueError,'exact validation'): load_layer_exact(root,'b'*40)
            (root/LAYER_FILE).write_bytes((root/LAYER_FILE).read_bytes()+b' ')
            with self.assertRaisesRegex(ValueError,'manifest/hash'): load_layer_exact(root,'a'*40)
    def test_missing_duplicate_corrupt_unknown_and_oversize_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.package(root);text=(root/'mac.log').read_text()
            for invalid in ['',text+text,'MAC_LAYER_ADJUSTMENT_FIXTURE '+('x'*500001)]:
                (root/'mac.log').write_text(invalid)
                with self.assertRaises(ValueError):layer_from_log(root/'mac.log','a'*40)
        row=self.row();row['version']='2.0'
        with self.assertRaises(ValueError):validate_layer(row)
        row=self.row();row['renderedSHA256']='0'*64
        with self.assertRaisesRegex(ValueError,'byte/hash'):validate_layer(row)
        row=self.row();row['unbound_extra']='data'
        with self.assertRaises(ValueError):validate_layer(row)
    def test_wrong_dimensions_and_symlink_are_rejected(self):
        row=self.row();png=bytearray(base64.b64decode(row['sourceBase64']));png[16:20]=struct.pack('>I',481);row['sourceBase64']=base64.b64encode(png).decode();row['sourceSHA256']=hashlib.sha256(png).hexdigest()
        with self.assertRaisesRegex(ValueError,'480x640'):validate_layer(row)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);data=self.package(root);(root/LAYER_FILE).unlink();(root/'other.json').write_bytes(data);(root/LAYER_FILE).symlink_to(root/'other.json')
            with self.assertRaisesRegex(ValueError,'bounded'):load_layer_exact(root,'a'*40)
    def test_component_diagnostics_remain_complete_hash_bound_and_bounded(self):
        row=self.row()
        row['components']=[{'name':name,'sha256':row['renderedSHA256'],'base64':row['renderedBase64']} for name in sorted(LAYER_COMPONENTS)]
        self.assertEqual(validate_layer(row),row)
        for mutate,error in [
            (lambda r:r['components'].pop(),'Malformed layer components'),
            (lambda r:r['components'][0].update(name=r['components'][1]['name']),'duplicate'),
            (lambda r:r['components'][0].update(sha256='0'*64),'byte/hash'),
            (lambda r:r['components'][0].update(extra='unbound'),'Malformed layer component'),
            (lambda r:r.update(components='not an array'),'Malformed layer components'),
            (lambda r:r['components'][0].update(base64='x'*500_001),'bounded'),
        ]:
            damaged=json.loads(json.dumps(row));mutate(damaged)
            with self.assertRaisesRegex(ValueError,error):validate_layer(damaged)
        damaged=json.loads(json.dumps(row));png=bytearray(base64.b64decode(damaged['components'][0]['base64']));png[20:24]=struct.pack('>I',641)
        damaged['components'][0].update(base64=base64.b64encode(png).decode(),sha256=hashlib.sha256(png).hexdigest())
        with self.assertRaisesRegex(ValueError,'480x640'):validate_layer(damaged)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'mac.log').write_text('MAC_LAYER_ADJUSTMENT_FIXTURE '+json.dumps(row)+'\n')
            payload=json.loads(layer_from_log(root/'mac.log','a'*40))
            self.assertEqual(payload['fixture'],row)
