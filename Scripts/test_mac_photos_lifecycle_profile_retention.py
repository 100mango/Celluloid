"""Portable exact owned-file failure retention; never reads a Photos container."""
import copy,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import mac_photos_reverted_profile as retain
import mac_host_transport as transport
import test_mac_host_transport as transport_fixtures
from validation_route import LIFECYCLE,host_clock_profile,context_clock
from test_mac_photos_lifecycle_observation import packet

ROOT=Path(__file__).resolve().parents[1]
class OwnedRevertedRetentionTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.temp=Path(self.directory.name).resolve();self.folder=self.temp/'mac-host-observed'/retain.DIRECTORY;self.folder.mkdir(parents=True)
        row,context,photos,ownership,baseline,images,_=packet()
        context.update(owned_reverted_profile_observation=retain.MODE,evidence_path=str(self.temp/'mac-host-observed'))
        raw_context=json.dumps(context,sort_keys=True).encode();context_hash=retain.sha(raw_context);row['context_sha256']=context_hash
        row['phases']=row['phases'][:5];row['complete']=False;row['functional_observation_complete']=False
        raw=images['lifecycle-source.png']
        self.receipt=dict(schema='Celluloid.OwnedRevertedProfile.1',source_sha=context['source_sha'],context_sha256=context_hash,
            run_id=context['runner_environment']['GITHUB_RUN_ID'],run_attempt=1,phase='reverted',raw_file=retain.RAW,
            raw_bytes=len(raw),raw_sha256=retain.sha(raw),canonical_file=None,profile=None,declaration=None,qualification=False)
        outcome=dict(source_sha=context['source_sha'],host_entry_contract='Celluloid.PhotosHostEntry.3',complete_host_e2e=False,
            export_png_diagnostics=[dict(phase='reverted',bytes=len(raw),sha256=retain.sha(raw),owned_profile_receipt=self.receipt)])
        self.records={'lifecycle.json':json.dumps(row).encode(),'outcome.json':json.dumps(outcome).encode()}
        self.context=context;self.args=(context,context_hash,self.records,baseline,photos,ownership);self.raw=raw
        (self.folder/retain.RAW).write_bytes(raw);self.write_receipt()
    def write_receipt(self):
        (self.folder/retain.RECEIPT_FILE).write_text(json.dumps(self.receipt))
    def test_incomplete_revert_can_retain_only_bound_original_without_qualifying(self):
        observed=retain.admit_profile_receipt(*self.args)
        nodes,canonical=retain.read_profile(self.temp,self.context,observed,lambda:None)
        self.assertEqual(set(nodes),{'reverted-profile.json','reverted-profile-input.png'})
        self.assertEqual(nodes['reverted-profile-input.png'],self.raw);self.assertIsNone(canonical)
        self.assertFalse(observed['qualification'])
    def test_wrong_run_hash_name_or_missing_safe_prefix_stops_before_open(self):
        for key,value in [('run_id','999'),('run_attempt',2),('source_sha','b'*40),('context_sha256','0'*64),
            ('raw_file','../outside.png'),('raw_sha256','0'*64),('raw_bytes',131073),('qualification',True)]:
            args=list(copy.deepcopy(self.args));outcome=json.loads(args[2]['outcome.json']);outcome['export_png_diagnostics'][0]['owned_profile_receipt'][key]=value
            args[2]['outcome.json']=json.dumps(outcome).encode()
            with self.subTest(key=key),patch.object(retain.os,'open') as opened:
                with self.assertRaises(ValueError):retain.admit_profile_receipt(*args)
                opened.assert_not_called()
        args=list(copy.deepcopy(self.args));row=json.loads(args[2]['lifecycle.json']);row['phases'].pop();args[2]['lifecycle.json']=json.dumps(row).encode()
        with self.assertRaises(ValueError):retain.admit_profile_receipt(*args)
    def test_disk_receipt_bytes_symlink_hardlink_and_foreign_root_reject(self):
        observed=retain.admit_profile_receipt(*self.args)
        (self.folder/retain.RAW).write_bytes(self.raw+b'x')
        with self.assertRaises(ValueError):retain.read_profile(self.temp,self.context,observed,lambda:None)
        (self.folder/retain.RAW).write_bytes(self.raw)
        outside=self.temp/'outside';outside.write_bytes(self.raw);(self.folder/retain.RAW).unlink();(self.folder/retain.RAW).symlink_to(outside)
        with self.assertRaises((OSError,ValueError)):retain.read_profile(self.temp,self.context,observed,lambda:None)
        (self.folder/retain.RAW).unlink();os.link(outside,self.folder/retain.RAW)
        with self.assertRaises(ValueError):retain.read_profile(self.temp,self.context,observed,lambda:None)
        (self.folder/retain.RAW).unlink();(self.folder/retain.RAW).write_bytes(self.raw)
        self.receipt['run_id']='different';self.write_receipt()
        with self.assertRaises(ValueError):retain.read_profile(self.temp,self.context,observed,lambda:None)
        with self.assertRaises(ValueError):retain.read_profile(self.temp,dict(self.context,evidence_path='/other'),observed,lambda:None)
    def test_deadline_and_metadata_mismatch_never_get_reinterpreted_as_success(self):
        observed=retain.admit_profile_receipt(*self.args)
        def expired():raise ValueError('original tail expired')
        with self.assertRaisesRegex(ValueError,'original tail'):retain.read_profile(self.temp,self.context,observed,expired)
        self.receipt.update(canonical_file=retain.CANONICAL,profile=dict(raw_sha256=retain.sha(self.raw),raw_bytes=len(self.raw),
            canonical_sha256='0'*64,canonical_bytes=len(self.raw)))
        self.write_receipt();(self.folder/retain.CANONICAL).write_bytes(self.raw)
        with self.assertRaisesRegex(ValueError,'canonical bytes'):retain.read_profile(self.temp,self.context,self.receipt,lambda:None)
    def test_native_source_keeps_original_color_and_functional_checks(self):
        source=(ROOT/'Platforms/UITests/MacPhotosHostUITests.swift').read_text()
        self.assertLess(source.index('retainRevertedProfileInput(bytes)'),source.index('let raster = try lifecycleRaster(bytes'))
        for text in ['gamma > 0, gamma <= Int(Int32.max)','chromaticities.count == 8','area != 0',
            'allowCalibratedRGB && srgb == 0 && icc == 0','context.interpolationQuality = .none',
            'guard reverted.rgba == source.rgba','guard original.bytes == source.bytes',
            'previousGenerations: [initialGeneration, reopened.generation]','O_EXCL | O_CLOEXEC | O_NOFOLLOW']:
            self.assertIn(text,source)
        helper=(ROOT/'Scripts/mac_photos_reverted_profile.py').read_text()
        self.assertNotIn('listdir(',helper);self.assertNotIn('glob(',helper);self.assertNotIn('Containers',helper)

class OwnedStagingTransportTests(unittest.TestCase):
    def fixture(self,profile=False):
        result=transport_fixtures.HostTransportTests();result.setUp()
        if profile:
            context=result.context
            context.update(validation_route=dict(LIFECYCLE),host_clock_profile=host_clock_profile(LIFECYCLE),
                owned_saved_pixel_observation='defer-known-saved-pixel-assertion-v1',
                owned_reverted_profile_observation=retain.MODE,evidence_path='/owned/runner/mac-host-observed')
            context['runner_environment']={'RUNNER_TEMP':'/owned/runner','GITHUB_RUN_ID':'123456','GITHUB_RUN_ATTEMPT':'1',
                'GITHUB_SHA':context['source_sha'],'GITHUB_WORKFLOW_SHA':context['source_sha'],
                'GITHUB_REF':'refs/heads/'+LIFECYCLE['branch'],'GITHUB_REPOSITORY':'100mango/Celluloid',
                'GITHUB_EVENT_NAME':'push','CELLULOID_VALIDATION_SCOPE':LIFECYCLE['scope'],
                'GITHUB_WORKFLOW_REF':'100mango/Celluloid/'+LIFECYCLE['workflow_path']+'@refs/heads/'+LIFECYCLE['branch']}
            self.payload(result,transport.expected_transport(context,result.context_hash))
        return result
    def transcript(self,fixture):
        return fixture.transcript().replace('"seconds": 720','"seconds": '+str(context_clock(fixture.context)['process_seconds']),1)
    def payload(self,fixture,value):
        import base64
        raw=json.dumps(value).encode();fixture.rows[0].update(bytes=len(raw),sha256=transport.sha(raw),base64=base64.b64encode(raw).decode())
    def test_default_transport_remains_original_false_and_rejects_staging_exception(self):
        old=self.fixture();expected=transport.expected_transport(old.context,old.context_hash)
        self.assertIs(expected['external_writes'],False);self.assertNotIn('owned_staging',expected)
        self.assertEqual(json.loads(old.parse(self.transcript(old))['transport.json']),expected)
        for changed in [dict(expected,external_writes='bounded-owned-staging-permitted'),dict(expected,owned_staging={}),dict(expected,external_writes=0)]:
            self.payload(old,changed)
            with self.assertRaises(ValueError):old.parse(self.transcript(old))
    def test_permission_is_bound_but_does_not_claim_or_trigger_actual_writes(self):
        fixture=self.fixture(True);expected=transport.expected_transport(fixture.context,fixture.context_hash)
        self.assertEqual(expected['external_writes'],'bounded-owned-staging-permitted')
        policy=expected['owned_staging'];self.assertEqual(policy['directory'],'/owned/runner/mac-host-observed/owned-reverted-profile')
        self.assertEqual(policy['files'],{retain.RAW:131072,retain.CANONICAL:131072,'profile.json':8192,'profile.pending.json':8192})
        self.assertEqual(policy['actual_write_evidence'],'owned_profile_receipt-and-fixed-file-readback')
        self.assertNotIn('writes_observed',expected);self.assertNotIn('writes_observed',policy)
        with patch.object(os,'open') as opened:
            self.assertEqual(json.loads(fixture.parse(self.transcript(fixture))['transport.json']),expected)
            opened.assert_not_called()
    def test_unknown_mode_or_wrong_route_run_and_source_never_fall_back_to_false(self):
        fixture=self.fixture(True);base=fixture.context
        variants=[]
        for key,value in [('owned_reverted_profile_observation','unknown'),('owned_reverted_profile_observation',None),
            ('owned_saved_pixel_observation','unknown'),('boundary_probe',{}),('evidence_path','/other')]:
            variants.append(dict(base,**{key:value}))
        for key,value in [('GITHUB_RUN_ID','0'),('GITHUB_RUN_ATTEMPT','2'),('GITHUB_SHA','b'*40),
            ('GITHUB_REF','refs/heads/codex/apple-platforms'),('RUNNER_TEMP','/owned/../runner')]:
            changed=copy.deepcopy(base);changed['runner_environment'][key]=value;variants.append(changed)
        for context in variants:
            with self.subTest(context=context),self.assertRaises(ValueError):transport.expected_transport(context,fixture.context_hash)
    def test_rehashed_capability_bool_path_name_limit_source_run_or_occurrence_forgery_rejects(self):
        fixture=self.fixture(True);base=transport.expected_transport(fixture.context,fixture.context_hash);variants=[]
        for value in [False,True,None,1]:variants.append(dict(base,external_writes=value))
        for key,value in [('directory','/outside'),('source_sha','b'*40),('context_sha256','0'*64),
            ('run_id','999'),('run_attempt',True),('actual_write_evidence','already-written')]:
            row=copy.deepcopy(base);row['owned_staging'][key]=value;variants.append(row)
        for name,value in [(retain.RAW,131073),('profile.pending.json',8193),('unexpected.png',1)]:
            row=copy.deepcopy(base);row['owned_staging']['files'][name]=value;variants.append(row)
        row=copy.deepcopy(base);row['owned_staging']['files'].pop('profile.pending.json');variants.append(row)
        for row in variants:
            self.payload(fixture,row)
            with self.subTest(row=row),self.assertRaises(ValueError):fixture.parse(self.transcript(fixture))

if __name__=='__main__':unittest.main()
