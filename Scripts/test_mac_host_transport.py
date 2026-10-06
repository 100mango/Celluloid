"""Portable transport adversaries; synthetic data does not qualify Apple host UI."""
from validation_route import FULL,host_clock_profile,context_clock
import base64,copy,json,tempfile,unittest
from unittest import mock
from pathlib import Path
import mac_host_transport as t

class HostTransportTests(unittest.TestCase):
    def setUp(self):
        self.context={'validation_route':dict(FULL),'host_clock_profile':host_clock_profile(FULL),'host_entry_contract':t.HOST_CONTRACT,'source_sha':'a'*40,'test_source_sha256':'b'*64,'script_sha256':'c'*64,'app_executable_sha256':'d'*64,'extension_executable_sha256':'e'*64,'extension_debug_dylib_sha256':'9'*64}
        self.context_hash='f'*64
        self.rows=[]
        for index,name in enumerate(t.ORDER):
            value=t.expected_transport(self.context,self.context_hash) if index==0 else {'synthetic':name}
            data=json.dumps(value).encode() if name.endswith('.json') else b'/owned/test.appex\n'
            self.rows.append({'schema':t.SCHEMA,'sequence':index,'name':name,'bytes':len(data),'sha256':t.sha(data),'base64':base64.b64encode(data).decode(),
                'source_sha':self.context['source_sha'],'context_sha256':self.context_hash,'test_source_sha256':self.context['test_source_sha256'],'verifier_sha256':self.context['script_sha256']})
    def transcript(self,rows=None):
        owner,method=t.CASE
        command=['xcodebuild','-maximum-test-execution-time-allowance',str(context_clock(self.context)['test_seconds']),'-only-testing:'+owner.replace('.','/')+'/'+method,'test-without-building']
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
        for key,value in [('context_sha256','b'*64),('context_validated',False),('context_validated',1),('external_writes',True),('external_writes',0),('app_executable_sha256','c'*64),('extension_executable_sha256','c'*64),('extension_debug_dylib_sha256','c'*64)]:
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
        item={'exportedFileName':path.name,'suggestedHumanReadableName':t.ATTACHMENT_PREFIX+Path(name).stem+'_0_11111111-2222-3333-4444-555555555555.txt'}
        manifest=[{'testIdentifier':'MacPhotosHostUITests/'+t.CASE[1]+'()','attachments':[item]}]
        return manifest,path
    def test_fixed_observed_export_suffix_and_owned_attachment_are_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);manifest,path=self.attachment(folder)
            self.assertEqual(t.attachment_candidates(folder,manifest),{'initial.txt':b'actual AX'})
    def test_exact_2980_runtime_stems_preserve_distinct_text_and_image_names(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            observed=[('870C6B2F-9522-4C46-92BC-6499B8CC2210.jpeg',
                'celluloid-host-diagnostic-last-observed_0_112B70D7-DE5F-43D6-AD63-64E93EF4CB09.jpg',b'\xff\xd8\xffsynthetic'),
                ('90046EAE-F73E-4C63-AFB0-E092FA4AF112',
                'celluloid-host-diagnostic-last-observed_0_C8DCFD3A-9D66-40F7-84AF-4481B072090D.txt',b'actual AX')]
            items=[]
            for exported,human,data in observed:
                (folder/exported).write_bytes(data)
                items.append({'exportedFileName':exported,'suggestedHumanReadableName':human})
            manifest=[{'testIdentifier':'MacPhotosHostUITests/'+t.CASE[1]+'()','attachments':items}]
            self.assertEqual(t.attachment_candidates(folder,manifest),{'last-observed.jpg':b'\xff\xd8\xffsynthetic','last-observed.txt':b'actual AX'})
            # The old, unobserved doubled-extension spelling is not a fallback.
            items[1]['suggestedHumanReadableName']=items[1]['suggestedHumanReadableName'].replace('last-observed_0','last-observed.txt_0')
            with self.assertRaisesRegex(ValueError,'Unexpected/duplicate named'):t.attachment_candidates(folder,manifest)

    def test_failed_predecode_png_is_retained_with_no_semantic_acceptance(self):
        from test_mac_host_lifecycle_pixels import encode,chunk
        from mac_host_lifecycle_pixels import decode,ORIGINAL_DIAGNOSTIC,NAMES,PNG_LIMIT
        malformed=encode(extra=[chunk(b'iTXt',b'invalid envelope')])
        with self.assertRaises(ValueError):decode(malformed,dimensions=(3,2))
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);items=[]
            def add(name,data,index):
                exported=str(index)+'.png';(folder/exported).write_bytes(data)
                items.append({'exportedFileName':exported,'suggestedHumanReadableName':t.LIFECYCLE_PREFIX+Path(name).stem+'_0_11111111-2222-3333-4444-555555555555.png'})
            add('lifecycle-saved.png',malformed,0)
            manifest=[{'testIdentifier':'MacPhotosHostUITests/'+t.CASE[1]+'()','attachments':items}]
            self.assertEqual(t.attachment_candidates(folder,manifest),{'lifecycle-saved.png':malformed})
            add(ORIGINAL_DIAGNOSTIC,malformed,1)
            self.assertEqual(t.attachment_candidates(folder,manifest)[ORIGINAL_DIAGNOSTIC],malformed)
            self.assertNotIn(ORIGINAL_DIAGNOSTIC,NAMES)
            manifest[0]['testIdentifier']='Other/test()'
            with self.assertRaises(ValueError):t.attachment_candidates(folder,manifest)
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);items=[]
            for index,name in enumerate((*NAMES,ORIGINAL_DIAGNOSTIC)):
                add(name,b'\x89PNG\r\n\x1a\n'+b'x'*(PNG_LIMIT-8),index)
            manifest=[{'testIdentifier':'MacPhotosHostUITests/'+t.CASE[1]+'()','attachments':items}]
            with self.assertRaisesRegex(ValueError,'aggregate'):t.attachment_candidates(folder,manifest)

    def test_process_clock_profile_and_actual_xctest_allowance_are_bound(self):
        good=self.transcript()
        self.parse(good.replace('"seconds": 720','"seconds": 720.0'))  # Actual run_bounded argparse float.
        for change in [good.replace('"660"','"960"'),good.replace('"seconds": 720','"seconds": 1020'),
                       good.replace('"-maximum-test-execution-time-allowance", "660", ',''),
                       good.replace('"660"','"660", "-maximum-test-execution-time-allowance", "660"')]:
            with self.assertRaises(ValueError):self.parse(change)
        from validation_route import HOST_ONLY,host_clock_profile
        self.context['validation_route']=dict(HOST_ONLY)
        with self.assertRaises(ValueError):self.parse(good)
        self.context['host_clock_profile']=host_clock_profile(HOST_ONLY)
        self.parse(self.transcript().replace('"seconds": 720','"seconds": 1020.0'))

    def test_same_fixed_name_with_distinct_export_paths_still_rejects(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);manifest,path=self.attachment(folder)
            duplicate=copy.deepcopy(manifest[0]['attachments'][0]);duplicate['exportedFileName']='other.txt'
            (folder/'other.txt').write_bytes(b'other AX');manifest[0]['attachments'].append(duplicate)
            with self.assertRaisesRegex(ValueError,'Unexpected/duplicate named'):t.attachment_candidates(folder,manifest)

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
    def test_observed_seventy_item_single_record_keeps_existing_total_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);manifest,path=self.attachment(folder,'last-observed.txt')
            for index in range(69):
                name='ordinary-'+str(index);(folder/name).write_bytes(b'not ingested UI snapshot')
                manifest[0]['attachments'].append({'exportedFileName':name,'suggestedHumanReadableName':'UI Snapshot or Synthesized Event'})
            self.assertEqual(len(manifest[0]['attachments']),70)
            with mock.patch.object(Path,'read_bytes',side_effect=AssertionError('ordinary bytes must not be read')):
                self.assertEqual(t.safe_diagnostic_candidates(folder,manifest),{'last-observed.txt':b'actual AX'})
                self.assertEqual(t.attachment_candidates(folder,manifest),{'last-observed.txt':b'actual AX'})
            self.assertEqual(t.MAX_ATTACHMENT_RECORDS,16);self.assertEqual(t.MAX_ATTACHMENT_ITEMS,16*64)
            manifest[0]['attachments']=[{}]*1025
            with mock.patch.object(t.os,'open') as opened:
                for parser in [t.safe_diagnostic_candidates,t.attachment_candidates]:
                    with self.assertRaisesRegex(ValueError,'inventory'):parser(folder,manifest)
                opened.assert_not_called()

    def test_early_retention_never_accepts_or_reads_lifecycle_or_ordinary_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);manifest,path=self.attachment(folder,'last-observed.txt')
            (folder/'broken.png').write_bytes(b'not png')
            manifest[0]['attachments'].append({'exportedFileName':'broken.png','suggestedHumanReadableName':t.LIFECYCLE_PREFIX+'lifecycle-saved_0_11111111-2222-3333-4444-555555555555.png'})
            self.assertEqual(t.safe_diagnostic_candidates(folder,manifest),{'last-observed.txt':b'actual AX'})
            with self.assertRaisesRegex(ValueError,'PNG'):t.attachment_candidates(folder,manifest)
            manifest[0]['attachments'][-1]={'exportedFileName':'../outside','suggestedHumanReadableName':'UI Snapshot'}
            self.assertEqual(t.safe_diagnostic_candidates(folder,manifest),{'last-observed.txt':b'actual AX'})
            with self.assertRaisesRegex(ValueError,'path'):t.attachment_candidates(folder,manifest)
            manifest.append({'attachments':None})
            self.assertEqual(t.safe_diagnostic_candidates(folder,manifest),{'last-observed.txt':b'actual AX'})
            with self.assertRaisesRegex(ValueError,'record'):t.attachment_candidates(folder,manifest)

    def test_early_diagnostics_exclude_ambiguous_wrong_owner_and_unsafe_files(self):
        for mutation in ['duplicate-path','duplicate-name','wrong-test','traversal','symlink','oversized','invalid-text']:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as directory:
                folder=Path(directory);manifest,path=self.attachment(folder,'last-observed.txt')
                item=manifest[0]['attachments'][0]
                if mutation=='duplicate-path':manifest[0]['attachments'].append(dict(item,suggestedHumanReadableName='UI Snapshot'))
                if mutation=='duplicate-name':
                    (folder/'other').write_bytes(b'other');manifest[0]['attachments'].append(dict(item,exportedFileName='other'))
                if mutation=='wrong-test':manifest[0]['testIdentifier']='OtherTests/testOther()'
                if mutation=='traversal':item['exportedFileName']='../outside'
                if mutation=='symlink':path.unlink();path.symlink_to('/etc/hosts')
                if mutation=='oversized':path.write_bytes(b'x'*120001)
                if mutation=='invalid-text':path.write_bytes(b'\xff')
                self.assertEqual(t.safe_diagnostic_candidates(folder,manifest),{})
                with self.assertRaises((ValueError,UnicodeError)):t.attachment_candidates(folder,manifest)

    def test_diagnostic_read_is_bounded_and_rejects_a_changed_file(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);manifest,path=self.attachment(folder,'last-observed.txt',b'x'*120000)
            original=t.os.read;read_count=0;changed=False
            def mutate(fd,size):
                nonlocal read_count,changed
                value=original(fd,size);read_count+=len(value)
                if not changed:
                    changed=True
                    with path.open('ab') as stream:stream.write(b'extra')
                return value
            with mock.patch.object(t.os,'read',side_effect=mutate):
                self.assertEqual(t.safe_diagnostic_candidates(folder,manifest),{})
            self.assertEqual(read_count,120000)
            with self.assertRaises(ValueError):t.attachment_candidates(folder,manifest)

    def test_source_routes_never_write_external_evidence_from_sandbox(self):
        root=Path(__file__).resolve().parents[1];swift=(root/'Platforms/UITests/MacPhotosHostUITests.swift').read_text();gate=(root/'Scripts/mac_photos_host_gate.py').read_text();shell=(root/'Scripts/run_mac_photos_host_gate.sh').read_text()
        self.assertNotIn('reportFolder',swift);self.assertNotIn('folder()',swift)
        self.assertNotIn('.write(to:',swift)
        process=gate.split('def process_provenance():',1)[1].split('EXPECTED_CASE',1)[0]
        self.assertNotIn('write(',process);self.assertIn('raise RuntimeError',process)
        for forbidden in ['subprocess.', 'proc_pidpath', '/bin/ps']:self.assertNotIn(forbidden,process)
        self.assertLess(swift.index('named: "transport.json"'),swift.index('app.launch()'))
        self.assertIn('XCTAttachment(data: bytes',swift)
        self.assertLess(shell.index('mac_photos_host_gate.py transport'),shell.index('mac_photos_host_gate.py product-after'))

if __name__=='__main__':unittest.main()
