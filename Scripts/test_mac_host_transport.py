"""Portable transport adversaries; synthetic data does not qualify Apple host UI."""
import base64,copy,json,tempfile,unittest
from pathlib import Path
import mac_host_transport as t

class HostTransportTests(unittest.TestCase):
    def setUp(self):
        self.context={'host_entry_contract':t.HOST_CONTRACT,'source_sha':'a'*40,'test_source_sha256':'b'*64,'script_sha256':'c'*64,'app_executable_sha256':'d'*64,'extension_executable_sha256':'e'*64}
        self.context_hash='f'*64
        self.rows=[]
        for index,name in enumerate(t.ORDER):
            value=t.expected_transport(self.context,self.context_hash) if index==0 else {'synthetic':name}
            data=json.dumps(value).encode() if name.endswith('.json') else b'/owned/test.appex\n'
            self.rows.append({'schema':t.SCHEMA,'sequence':index,'name':name,'bytes':len(data),'sha256':t.sha(data),'base64':base64.b64encode(data).decode(),
                'source_sha':self.context['source_sha'],'context_sha256':self.context_hash,'test_source_sha256':self.context['test_source_sha256'],'verifier_sha256':self.context['script_sha256']})
    def transcript(self,rows=None):
        owner,method=t.CASE
        command=['xcodebuild','-only-testing:'+owner.replace('.','/')+'/'+method,'test-without-building']
        lines=['BOUNDED_COMMAND_BEGIN '+json.dumps({'label':t.LABEL,'seconds':720,'command':command}),"Test Case '-["+owner+' '+method+"]' started."]
        lines += [t.PREFIX+json.dumps(row) for row in (self.rows if rows is None else rows)]
        lines += ["Test Case '-["+owner+' '+method+"]' passed (1.0 seconds).",'** TEST EXECUTE SUCCEEDED **','BOUNDED_COMMAND_END '+json.dumps({'label':t.LABEL,'exit_code':0,'elapsed_seconds':1})]
        return '\n'.join(lines)+'\n'
    def parse(self,log,complete=True):return t.parse(log,self.context,self.context_hash,complete=complete)
    def test_complete_bound_receipts_require_actual_enclosing_process_and_test(self):
        records=self.parse(self.transcript());self.assertEqual(list(records),t.ORDER)
        self.assertEqual(json.loads(records['transport.json']),t.expected_transport(self.context,self.context_hash))
    def test_duplicate_out_of_order_missing_and_unknown_records_reject(self):
        variants=[self.rows+self.rows[-1:],self.rows[1:],self.rows[:2]+self.rows[3:],list(reversed(self.rows))]
        for rows in variants:
            with self.subTest(rows=rows),self.assertRaises(ValueError):self.parse(self.transcript(rows))
        for key,value in [('sequence',True),('sequence',4),('name','../outcome.json'),('name','unexpected.json'),('schema','other'),('bytes',True),('bytes',-1),('sha256','a'*64),('source_sha','b'*40),('context_sha256','b'*64),('test_source_sha256','f'*64),('verifier_sha256','f'*64),('base64','%%%')]:
            rows=copy.deepcopy(self.rows);rows[0][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):self.parse(self.transcript(rows))
    def test_forged_first_validation_rejects_even_after_rehashing(self):
        for key,value in [('context_sha256','b'*64),('context_validated',False),('context_validated',1),('external_writes',True),('external_writes',0),('app_executable_sha256','c'*64),('extension_executable_sha256','c'*64)]:
            rows=copy.deepcopy(self.rows);payload=json.loads(base64.b64decode(rows[0]['base64']));payload[key]=value
            data=json.dumps(payload).encode();rows[0].update(base64=base64.b64encode(data).decode(),bytes=len(data),sha256=t.sha(data))
            with self.subTest(key=key),self.assertRaises(ValueError):self.parse(self.transcript(rows))
    def test_duplicate_json_unknown_fields_invalid_types_and_truncation_reject(self):
        log=self.transcript()
        for changed in [log.replace('"schema": "'+t.SCHEMA+'"','"schema":"'+t.SCHEMA+'","schema":"'+t.SCHEMA+'"',1),
                        log.replace(t.PREFIX,' '+t.PREFIX,1),log.replace(t.PREFIX,'BAD'+t.PREFIX,1),log[:log.index('BOUNDED_COMMAND_END')],log+'MAC_HOST_PROOF malformed\n']:
            with self.subTest(changed=changed),self.assertRaises(ValueError):self.parse(changed)
        rows=copy.deepcopy(self.rows);rows[1]['unexpected']=True
        with self.assertRaises(ValueError):self.parse(self.transcript(rows))
    def test_process_terminal_failure_timeout_wrong_test_and_records_outside_case_reject(self):
        log=self.transcript()
        for changed in [log.replace('"exit_code": 0','"exit_code": 65'),log.replace('"elapsed_seconds": 1','"elapsed_seconds": 999'),
            log.replace('** TEST EXECUTE SUCCEEDED **','** TEST EXECUTE FAILED **'),log.replace('test-without-building','build'),
            log.replace(t.CASE[1], 'testUnexpected'),log.replace(' passed (1.0 seconds).',' skipped (1.0 seconds).'),
            log.replace('BOUNDED_COMMAND_END','BOUNDED_COMMAND_TIMEOUT'),log.replace('** TEST EXECUTE SUCCEEDED **','** TEST EXECUTE SUCCEEDED **\n** TEST EXECUTE SUCCEEDED **'),
            t.PREFIX+json.dumps(self.rows[0])+'\n'+log,log+t.PREFIX+json.dumps(self.rows[-1])+'\n']:
            with self.subTest(changed=changed),self.assertRaises(ValueError):self.parse(changed)
    def test_timeout_and_malformed_process_markers_cannot_coexist_with_success(self):
        log=self.transcript()
        for marker in ['BOUNDED_COMMAND_TIMEOUT '+t.LABEL,'BOUNDED_COMMAND_TIMEOUT malformed',
                       'BOUNDED_TIMEOUT_PROCESS_IDENTITIES []','BOUNDED_COMMAND_ABORTED '+t.LABEL]:
            for changed in [log.replace('** TEST EXECUTE SUCCEEDED **',marker+'\n** TEST EXECUTE SUCCEEDED **'),log+marker+'\n']:
                with self.subTest(marker=marker),self.assertRaisesRegex(ValueError,'process (?:timeout|record)'):self.parse(changed)
                with self.assertRaises(ValueError):self.parse(changed,complete=False)
    def test_nonfinite_json_is_rejected_at_every_transport_boundary(self):
        for literal in ['NaN','Infinity','-Infinity','1e999','-1e999']:
            with self.subTest(literal=literal):
                rows=copy.deepcopy(self.rows);data=('{"extra":'+literal+'}').encode()
                rows[1].update(base64=base64.b64encode(data).decode(),bytes=len(data),sha256=t.sha(data))
                with self.assertRaisesRegex(ValueError,'Nonfinite JSON'):self.parse(self.transcript(rows))
                for log in [self.transcript().replace('"seconds": 720','"seconds": '+literal),
                            self.transcript().replace('"elapsed_seconds": 1','"elapsed_seconds": '+literal),
                            self.transcript().replace('"sequence": 0','"sequence": '+literal,1)]:
                    with self.assertRaisesRegex(ValueError,'Nonfinite JSON'):self.parse(log)
                with self.assertRaisesRegex(ValueError,'Nonfinite JSON'):t.load_json('{"nested":[{"x":'+literal+'}]}')

    def test_v1_context_transport_and_relabelled_first_payload_reject(self):
        original=self.context['host_entry_contract'];self.context['host_entry_contract']='Celluloid.PhotosHostEntry.1'
        with self.assertRaisesRegex(ValueError,'host-entry contract'):self.parse(self.transcript())
        self.context['host_entry_contract']=original
        rows=copy.deepcopy(self.rows);rows[0]['schema']='Celluloid.MacHostProof.1'
        with self.assertRaises(ValueError):self.parse(self.transcript(rows))
        rows=copy.deepcopy(self.rows);value=json.loads(base64.b64decode(rows[0]['base64']));value['schema']='Celluloid.HostTransport.1'
        data=json.dumps(value).encode();rows[0].update(base64=base64.b64encode(data).decode(),bytes=len(data),sha256=t.sha(data))
        with self.assertRaises(ValueError):self.parse(self.transcript(rows))

    def test_partial_failed_execution_is_diagnostic_only(self):
        rows=copy.deepcopy(self.rows[:2]);outcome=copy.deepcopy(self.rows[-1]);outcome['sequence']=2;rows.append(outcome)
        log=self.transcript(rows).replace(' passed (1.0 seconds).',' failed (1.0 seconds).').replace('"exit_code": 0','"exit_code": 65').replace('** TEST EXECUTE SUCCEEDED **','** TEST EXECUTE FAILED **')
        self.assertEqual(list(self.parse(log,complete=False)),['transport.json','containing-process.json','outcome.json'])
        with self.assertRaises(ValueError):self.parse(log)
    def test_per_record_aggregate_and_transcript_bounds_reject(self):
        def payload(row,data):row.update(base64=base64.b64encode(data).decode(),bytes=len(data),sha256=t.sha(data))
        rows=copy.deepcopy(self.rows);payload(rows[1],b'x'*16001)
        with self.assertRaises(ValueError):self.parse(self.transcript(rows))
        rows=copy.deepcopy(self.rows)
        for row in rows[1:]:
            count=110000 if row['name']=='fixture.json' else 15900
            payload(row,json.dumps({'padding':'x'*count}).encode())
        with self.assertRaisesRegex(ValueError,'total byte'):self.parse(self.transcript(rows))
        with self.assertRaises(ValueError):self.parse(self.transcript()+'x'*20_000_001)
    def attachment(self,folder,name='initial.txt',data=b'actual AX'):
        path=folder/'11111111-2222-3333-4444-555555555555.txt';path.write_bytes(data)
        item={'exportedFileName':path.name,'suggestedHumanReadableName':t.ATTACHMENT_PREFIX+name+'_0_11111111-2222-3333-4444-555555555555.txt'}
        manifest=[{'testIdentifier':'MacPhotosHostUITests/'+t.CASE[1]+'()','attachments':[item]}]
        return manifest,path
    def test_fixed_observed_export_suffix_and_owned_attachment_are_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);manifest,path=self.attachment(folder)
            self.assertEqual(t.attachment_candidates(folder,manifest),{'initial.txt':b'actual AX'})
    def test_unexpected_duplicate_oversized_wrong_test_and_unowned_attachment_reject(self):
        changes=[lambda m:m[0]['attachments'][0].update(exportedFileName='../outside.txt'),
            lambda m:m[0]['attachments'][0].update(exportedFileName='/tmp/outside.txt'),
            lambda m:m[0]['attachments'][0].update(suggestedHumanReadableName=t.ATTACHMENT_PREFIX+'unexpected_0_11111111-2222-3333-4444-555555555555.txt'),
            lambda m:m[0]['attachments'].append(copy.deepcopy(m[0]['attachments'][0])),
            lambda m:m[0].update(testIdentifier='UnexpectedTests/testOther()')]
        for change in changes:
            with self.subTest(change=change),tempfile.TemporaryDirectory() as directory:
                folder=Path(directory);manifest,path=self.attachment(folder);change(manifest)
                with self.assertRaises(ValueError):t.attachment_candidates(folder,manifest)
        for mode in ['symlink','oversized']:
            with tempfile.TemporaryDirectory() as directory:
                folder=Path(directory);manifest,path=self.attachment(folder)
                if mode=='symlink':path.unlink();path.symlink_to('/etc/hosts')
                else:path.write_bytes(b'x'*120001)
                with self.assertRaises(ValueError):t.attachment_candidates(folder,manifest)
    def test_source_routes_never_write_external_evidence_from_sandbox(self):
        root=Path(__file__).resolve().parents[1];swift=(root/'Platforms/UITests/MacPhotosHostUITests.swift').read_text();gate=(root/'Scripts/mac_photos_host_gate.py').read_text();shell=(root/'Scripts/run_mac_photos_host_gate.sh').read_text()
        self.assertNotIn('reportFolder',swift);self.assertNotIn('folder()',swift)
        self.assertNotIn('.write(to:',swift)
        process=gate.split('def process_provenance():',1)[1].split('EXPECTED_CASE',1)[0]
        self.assertNotIn('write(',process);self.assertIn('print(json.dumps(result',process)
        self.assertLess(swift.index('named: "transport.json"'),swift.index('app.launch()'))
        self.assertIn('XCTAttachment(data: bytes',swift)
        self.assertLess(shell.index('mac_photos_host_gate.py transport'),shell.index('mac_photos_host_gate.py product-after'))

if __name__=='__main__':unittest.main()
