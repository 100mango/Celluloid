"""Four-row source-bound replay with original semantic, pixel and clock adversaries."""
import copy,json,os,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import original_ios_rows as replay
import original_ios_source_contract as projection
import uikit_full_shipping_handoff as handoff
import uikit_full_shipping_gate as gate
import test_uikit_full_shipping_gate as cases
import test_uikit_full_shipping_route as fixture
from test_uikit_full_shipping_route import put_json
from test_original_ios_route import environment
from verify_required_interoperability import verify

class OriginalIOSRowsTests(unittest.TestCase):
    def setUp(self):
        self.base=fixture.AcceptRowTests('test_complete_row_replays_every_named_case_consumer_source_product_and_cleanup')
        self.base.setUp();self.addCleanup(self.base.doCleanups)
        self.env=patch.dict(os.environ,environment(),clear=True);self.env.start();self.addCleanup(self.env.stop)
        self.temp=self.base.temp
        fingerprint=handoff.source_profile()[1]
        for folder in [self.temp,self.base.artifact]:
            for phase in ['before','after']:
                path=folder/('combined-source-'+phase+'.json');value=handoff.read(path)
                value.update(file_count=546,source_fingerprint=fingerprint,validation_route=handoff.ORIGINAL_IOS,original_ios_source=projection.audit())
                put_json(path,value)
        path=self.base.artifact/'full-shipping-producer.json';value=handoff.read(path);value['protected_fingerprint']=fingerprint;put_json(path,value)
        self.base.rehash();(self.temp/'full-shipping-transfer.json').unlink();self.base.transfer()
        self.folders={}
        for index,row in enumerate(gate.ROWS):self.make_row(index,row)

    def make_row(self,index,row):
        folder=self.temp/('generate-'+row);folder.mkdir();device=f'12345678-1234-1234-1234-123456789AB{index}'
        for path in self.temp.iterdir():
            if path.is_file():shutil.copyfile(path,folder/path.name)
        shutil.copytree(self.base.artifact,folder/'mac-fixture-evidence')
        clock=handoff.read(folder/'full-shipping-clock.json');clock['row']=row;put_json(folder/'full-shipping-clock.json',clock)
        for name in ['full-shipping-device.json','full-shipping-product-after.json','full-shipping-cleanup.json']:
            path=folder/name;value=handoff.read(path);value['row']=row
            if name=='full-shipping-device.json':value['device']={'id':device,'model':gate.ROWS[row]}
            if name=='full-shipping-cleanup.json':value['device_id']=device
            if name=='full-shipping-product-after.json':
                actual=value['actual'];actual['device_id']=device;actual['app_path']=actual['app_path'].replace(self.base.device_id,device)
            put_json(path,value)
        staging=handoff.read(folder/'uikit-layer-staging.json');staging['installed_app']=staging['installed_app'].replace(self.base.device_id,device);put_json(folder/'uikit-layer-staging.json',staging)
        product=handoff.read(folder/'full-shipping-product-after.json');product['staging_sha256']=handoff.sha(folder/'uikit-layer-staging.json');put_json(folder/'full-shipping-product-after.json',product)
        cases.write_execution(folder,row)
        for count,phase in enumerate(gate.expected_phases(row)):
            path=folder/gate.phase_files(phase)[1];summary=handoff.read(path)
            summary['devicesAndConfigurations'][0]['device']['deviceId']=device
            summary.update(startTime=clock['started_unix']+10+count*10,finishTime=clock['started_unix']+11+count*10);put_json(path,summary)
        _,consumer_log,_,_,_=self.base.synthetic.profile('3x' if row=='large-phone' else '2x')
        consumer_log='\n'.join(line for line in consumer_log.splitlines() if not line.startswith(('Executed ','** TEST'))).strip()+'\n'
        case='-[CelluloidTests.MacPhotosManufacturedAdjustmentTests testManufacturedMacArchiveThroughOriginalUIKitReaderAndCompositor]'
        original=f"Test Case '{case}' started.\nTest Case '{case}' passed (0.1 seconds).\n"
        path=folder/'units.log';self.assertEqual(path.read_text().count(original),1);path.write_text(path.read_text().replace(original,consumer_log))
        manifest=cases.manifest(row);manifest['device']['id']=device;put_json(folder/'full-shipping-execution.json',manifest)
        put_json(folder/'full-shipping-accounting.json',gate.verify_manifest(manifest,folder,cases.context(row),clock))
        stages=handoff.read(folder/'full-shipping-stage-outcomes.json');stages['preflight']={'outcome':'success','conclusion':'success'};put_json(folder/'full-shipping-stage-outcomes.json',stages)
        put_json(folder/'uikit-required-tests.json',verify('uikit',path,folder/'mac-fixture-evidence','a'*40,platform_contract=True,runtime_summary=handoff.read(folder/'units.summary.json'),expected_device=manifest['device']))
        from original_ios_first_summary import PHASE_FILE,SCHEMA,record
        started=clock['started_monotonic']
        put_json(folder/PHASE_FILE,{'schema':SCHEMA,**cases.context(row),'started_monotonic':started+1.,'started_unix':clock['started_unix']+1.,'phase_seconds':1020})
        import contextlib,io
        with contextlib.redirect_stdout(io.StringIO()):
            record({'context':cases.context(row),'root':folder,'phase_started':started+1.,'started':started+12.,'command_deadline':started+102.,'cleanup_deadline':started+112.,'enclosing_deadline':started+1021.},0,started+14.)
        with patch.dict(os.environ,CELLULOID_FULL_ROW=row):
            proof=handoff.accept_row(folder);put_json(folder/'full-shipping-row.json',proof)
            out=self.temp/'original-ios-rows'/row;out.mkdir(parents=True)
            for p in folder.iterdir():
                if p.is_file() and p.suffix=='.json':shutil.copyfile(p,out/p.name)
            for source,target in [('mac-layer-fixture.json','consumer-mac-layer-fixture.json'),('manifest.json','consumer-mac-layer-manifest.json')]:shutil.copyfile(self.base.artifact/source,out/target)
            def retain(name,data,source):(out/name).write_bytes(data);return True
            handoff.pack_phase_logs(folder,retain,1_500_000)
        self.folders[row]=out;self.rehash(row)

    def rehash(self,row):
        folder=self.folders[row]
        put_json(folder/'manifest.json',{'source_sha':'a'*40,'run_id':'1234567','platform':row,'limits':{'total_bytes':1_500_000},
            'files':[{'name':p.name,'bytes':p.stat().st_size,'sha256':handoff.sha(p)} for p in sorted(folder.iterdir()) if p.name!='manifest.json']})

    def test_all_four_original_rows_replay_after_queue_delay_without_extending_original_clocks(self):
        with patch.object(gate.time,'monotonic',return_value=9_000_000.0),patch.object(gate.time,'time',return_value=9_000_000_000.0):
            value=replay.verify_four(self.temp)
        self.assertEqual(value['original_total_invocations'],412);self.assertEqual([r['original_test_invocation_count'] for r in value['rows']],[108,102,100,102])
        self.assertEqual([r['row'] for r in value['rows']],list(gate.ROWS));self.assertTrue(value['all_rows_verified'])

    def test_missing_failed_wrong_source_attempt_model_or_cleanup_reject_even_rehashed(self):
        for filename,mutation in [('full-shipping-row.json',lambda r:r.update(row_checks_passed=False)),('full-shipping-row.json',lambda r:r.update(source_sha='b'*40)),('full-shipping-row.json',lambda r:r.update(run_attempt='2')),('full-shipping-device.json',lambda r:r['device'].update(model='other')),('full-shipping-cleanup.json',lambda r:r['actions'][0].update(exit_code=1)),('full-shipping-logs.json',lambda r:r.update(producer_complete=False)),('combined-source-before.json',lambda r:r.update(source_fingerprint=handoff.UIKIT_FULL_BASE['fingerprint']))]:
            path=self.folders['small-ipad']/filename;original=path.read_bytes();value=json.loads(original);mutation(value);put_json(path,value);self.rehash('small-ipad')
            with self.subTest(filename=filename),self.assertRaises((ValueError,KeyError)):replay.verify_four(self.temp)
            path.write_bytes(original);self.rehash('small-ipad')

    def test_extra_unsafe_duplicate_symlink_or_oversize_artifact_is_rejected_before_replay(self):
        folder=self.folders['large-ipad'];path=folder/'manifest.json';original=path.read_bytes()
        for name in ['../outside.json','/tmp/outside','manifest.json','']:
            value=json.loads(original);value['files'][0]['name']=name;put_json(path,value)
            with self.subTest(name=name),self.assertRaises(ValueError):replay.verify_four(self.temp)
        value=json.loads(original);value['files'].append(copy.deepcopy(value['files'][0]));put_json(path,value)
        with self.assertRaises(ValueError):replay.verify_four(self.temp)
        value=json.loads(original);value['files'][0]['bytes']=1_500_001;put_json(path,value)
        with self.assertRaises(ValueError):replay.verify_four(self.temp)
        path.write_bytes(original);(folder/'unlisted').write_text('unexpected')
        with self.assertRaises(ValueError):replay.verify_four(self.temp)
        (folder/'unlisted').unlink()
        target=folder/json.loads(original)['files'][0]['name'];data=target.read_bytes()
        outside=self.temp/'outside-row-member';outside.write_bytes(data);target.unlink();target.symlink_to(outside)
        with self.assertRaises(ValueError):replay.verify_four(self.temp)
        target.unlink();target.write_bytes(data)
        value=json.loads(original);value['limits']['total_bytes']=1_500_000.0;put_json(path,value)
        with self.assertRaises(ValueError):replay.verify_four(self.temp)

if __name__=='__main__':unittest.main()
