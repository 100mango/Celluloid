"""Synthetic parser adversaries, never evidence of native Photos execution."""
import copy,hashlib,json,unittest
from pathlib import Path
import mac_host_self_identity as identity

def envelope(raw):
    data=raw.encode('utf8');return {'raw':raw,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
def payload(context,pid=123):
    return {'schema':identity.SCHEMA,'marker':identity.MARKER,'observation_kind':'extension-self',
        'bundle_identifier':context['extension_id'],'pid':pid,'bundle_path':context['extension_path'],
        'executable_path':context['extension_executable'],'executable_sha256':context['extension_executable_sha256'],
        'debug_dylib_path':context['extension_debug_dylib'],'debug_dylib_sha256':context['extension_debug_dylib_sha256'],
        'generation':'12345678-1234-4321-8123-123456789ABC','content_editing_started':True}
def receipt(context,photos,ownership):
    raw=json.dumps(payload(context),sort_keys=True,separators=(',',':'))
    return {'schema':identity.RECEIPT,'host_entry_contract':identity.HOST_CONTRACT,'source_sha':context['source_sha'],
        'photos_pid':photos['pid'],'fixture_sha256':ownership['fixture_sha256'],'asset_label':ownership['asset_label'],
        'identity_identifier':identity.IDENTIFIER,'identity_element_counts':[1,1],
        'observations':[envelope(raw),envelope(raw)]}
def change_payload(row,**changes):
    for observation in row['observations']:
        value=json.loads(observation['raw']);value.update(changes);observation.update(envelope(json.dumps(value)))

class SelfIdentityTests(unittest.TestCase):
    def setUp(self):
        extension='/Users/runner/Applications/CelluloidMac.app/Contents/PlugIns/CelluloidMacPhotosExtension.appex'
        executable=extension+'/Contents/MacOS/CelluloidMacPhotosExtension'
        self.context={'source_sha':'a'*40,'extension_id':'Mango.Celluloid.CelluloidPhotoExtension','extension_path':extension,
            'extension_executable':executable,'extension_executable_sha256':'e'*64,
            'extension_debug_dylib':executable+'.debug.dylib','extension_debug_dylib_sha256':'9'*64}
        self.photos={'pid':122};self.ownership={'fixture_sha256':'f'*64,'asset_label':'sole synthetic asset'}
        self.row=receipt(self.context,self.photos,self.ownership)
    def validate(self,row=None):return identity.validate(self.row if row is None else row,self.context,self.photos,self.ownership)
    def test_exact_two_actual_raw_observations_match_independent_product_context(self):
        value=self.validate();self.assertEqual(value,payload(self.context));self.assertEqual(len(value),12)
    def test_wrong_source_host_fixture_contract_or_missing_duplicate_leaf_reject(self):
        for key,values in {'source_sha':['b'*40], 'photos_pid':[True,123,0], 'fixture_sha256':['0'*64], 'asset_label':['other'],
            'schema':['other'],'host_entry_contract':['Celluloid.PhotosHostEntry.2'], 'identity_identifier':['other'],
            'identity_element_counts':[[1],[1,1,1],[True,1],[1,0],[1,2],[2,1]]}.items():
            for value in values:
                row=copy.deepcopy(self.row);row[key]=value
                with self.subTest(key=key,value=value),self.assertRaises(ValueError):self.validate(row)
    def test_all_payload_types_values_paths_and_product_hashes_fail_closed(self):
        mutations={'schema':['other'],'marker':['other'],'observation_kind':['process-enumeration'],
            'bundle_identifier':['other'],'pid':[True,0,-1,122,2**31,'123'],
            'bundle_path':['/other','relative','/Users/USER/*/extension','x'*2049],
            'executable_path':['/other','relative'],'debug_dylib_path':['/other'],
            'executable_sha256':['0'*64,'E'*64,True],'debug_dylib_sha256':['0'*64],
            'generation':['',None,True,'0'*36,'00000000-0000-0000-0000-000000000000','1234'],
            'content_editing_started':[False,1,'true']}
        for key,values in mutations.items():
            for value in values:
                row=copy.deepcopy(self.row);change_payload(row,**{key:value})
                with self.subTest(key=key,value=value),self.assertRaises(ValueError):self.validate(row)
    def test_unknown_missing_duplicate_and_nonfinite_raw_json_reject_after_rehash(self):
        original=self.row['observations'][0]['raw'];value=json.loads(original)
        variants=[original[:-1]+',"pid":123}',original[:-1]+',"extra":true}',original[:-1]]
        for key in value:
            missing=dict(value);del missing[key];variants.append(json.dumps(missing))
        for constant in ['NaN','Infinity','-Infinity','1e999']:
            variants.append(original.replace('"pid":123','"pid":'+constant))
        for raw in variants:
            row=copy.deepcopy(self.row);row['observations']=[envelope(raw),envelope(raw)]
            with self.subTest(raw=raw),self.assertRaises(ValueError):self.validate(row)
    def test_missing_extra_truncated_oversize_and_bad_envelope_reject(self):
        for observations in [[],self.row['observations'][:1],self.row['observations']*2]:
            row=copy.deepcopy(self.row);row['observations']=observations
            with self.assertRaises(ValueError):self.validate(row)
        for raw in ['', ' '*8193, '界'*3000]:
            row=copy.deepcopy(self.row);row['observations']=[envelope(raw),envelope(raw)]
            with self.assertRaises(ValueError):self.validate(row)
        for changes in [{'bytes':True},{'bytes':1},{'sha256':'0'*64},{'extra':0},{'raw':3}]:
            row=copy.deepcopy(self.row);row['observations'][0].update(changes)
            with self.assertRaises(ValueError):self.validate(row)
    def test_stale_replaced_generation_pid_or_same_json_changed_raw_reject(self):
        for changes in [{'generation':'87654321-1234-4321-8123-123456789ABC'},{'pid':124},{}]:
            row=copy.deepcopy(self.row);second=json.loads(row['observations'][1]['raw']);second.update(changes)
            row['observations'][1]=envelope(json.dumps(second))
            with self.assertRaisesRegex(ValueError,'Stale/changed'):self.validate(row)
    def test_unknown_receipt_or_context_replay_is_rejected(self):
        row=copy.deepcopy(self.row);row['extra']='unbound'
        with self.assertRaises(ValueError):self.validate(row)
        self.context['extension_executable_sha256']='b'*64
        with self.assertRaises(ValueError):self.validate()
    def test_swift_observes_leaf_without_process_helper_and_keeps_exact_raw_bytes(self):
        source=(Path(__file__).resolve().parents[1]/'Platforms/UITests/MacPhotosHostUITests.swift').read_text()
        self.assertNotIn('try command(',source);self.assertNotIn('let p = Process()',source)
        for text in ['let editorCount = editors.count','let identityCount = identities.count','guard identityCount <= 1',
            'guard editorCount == 1','if let contradiction { throw block(contradiction) }','firstIdentity.raw == secondIdentity.raw',
            '"raw": item.raw','allowWait: true','allowWait: false','"extension_debug_dylib_sha256"']:
            self.assertIn(text,source)
        sample=source.split('func sample() -> Bool {',1)[1].split('if allowWait {',1)[0]
        self.assertEqual(sample.count('editors.count'),1);self.assertEqual(sample.count('identities.count'),1)

    def test_sampled_duplicate_or_disappeared_editor_latches_before_later_clean(self):
        source=(Path(__file__).resolve().parents[1]/'Platforms/UITests/MacPhotosHostUITests.swift').read_text()
        sample=source.split('func sample() -> Bool {',1)[1].split('if allowWait {',1)[0]
        self.assertIn('guard editorCount == 1 else { contradiction =',sample)
        self.assertIn('guard identityCount <= 1 else { contradiction =',sample)
        def replay(rows):
            for editor,count,valid in rows:
                if editor!=1 or count>1:return 'contradiction'
                if count==0:continue
                return 'ready' if valid else 'contradiction'
            return 'missing'
        self.assertEqual(replay([(1,0,False),(1,1,True)]),'ready')
        for first in [(2,1,True),(0,1,True),(1,2,True),(1,1,False)]:
            self.assertEqual(replay([first,(1,1,True)]),'contradiction')
        self.assertEqual(replay([(1,0,False)]),'missing')

if __name__=='__main__':unittest.main()
