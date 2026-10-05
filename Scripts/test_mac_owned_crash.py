"""Synthetic IPS/collector adversaries; no Apple host acceptance is claimed."""
import copy
import json
from dataclasses import dataclass

EXE='/Users/runner/work/_temp/celluloid-sandbox/Build/Products/Debug/CelluloidMac.app/Contents/PlugIns/CelluloidMacPhotosExtension.appex/Contents/MacOS/CelluloidMacPhotosExtension'
DEBUG=EXE+'.debug.dylib'
MAIN_UUID='11111111-1111-4111-8111-111111111111'
DEBUG_UUID='22222222-2222-4222-8222-222222222222'
INCIDENT='44444444-4444-4444-8444-444444444444'
BUNDLE='Mango.Celluloid.CelluloidPhotoExtension'
BINDING={'source_sha':'a'*40,'context_sha256':'b'*64,'test_source_sha256':'c'*64,
         'expected_executable':EXE,'executable_sha256':'d'*64,'executable_uuid':MAIN_UUID,
         'expected_debug_dylib':DEBUG,'debug_dylib_sha256':'e'*64,'debug_dylib_uuid':DEBUG_UUID,
         'extension_id':BUNDLE,'window_start':1791184628.853,'window_end':1791184758.191}

def report():
    metadata={'app_name':'CelluloidMacPhotosExtension','timestamp':'2026-10-05 07:19:17.63 +0000',
              'slice_uuid':MAIN_UUID,'bundleID':BUNDLE,'bug_type':'309','incident_id':INCIDENT}
    body={'procName':'CelluloidMacPhotosExtension','procPath':EXE,
          'bundleInfo':{'CFBundleIdentifier':BUNDLE},'incident':INCIDENT,'bug_type':'309',
          'pid':101,'captureTime':'2026-10-05 07:19:17.6300 +0000','procLaunch':'2026-10-05 07:18:47.1000 +0000',
          'exception':{'type':'EXC_CRASH','signal':'SIGABRT','codes':'0x0, 0x0','rawCodes':[0,0]},
          'termination':{'namespace':'SIGNAL','code':6,'indicator':'Abort trap: 6'},
          'faultingThread':1,
          'threads':[{'id':100,'frames':[{'imageIndex':0,'imageOffset':20,'symbol':'noncrashed-private-marker'}],
                      'threadState':{'private':'unrelated-thread-state'}},
                     {'id':101,'triggered':True,'frames':[{'imageIndex':0,'imageOffset':16,'symbol':'abort'},
                        {'imageIndex':2,'imageOffset':32,'symbol':'owned_test_symbol'}]}],
          'usedImages':[{'uuid':'33333333-3333-4333-8333-333333333333','path':'/usr/lib/system/libsystem_kernel.dylib','name':'libsystem_kernel.dylib','base':1000,'size':512,'arch':'arm64'},
                        {'uuid':MAIN_UUID,'path':EXE,'name':'CelluloidMacPhotosExtension','base':2000,'size':512,'arch':'arm64'},
                        {'uuid':DEBUG_UUID,'path':DEBUG,'name':'CelluloidMacPhotosExtension.debug.dylib','base':3000,'size':1024,'arch':'arm64'}],
          'crashReporterKey':'private-device-marker','userID':501,'trialInfo':{'private':'unrelated-trial-marker'}}
    return metadata,body

def encoded(metadata,body):
    return (json.dumps(metadata,separators=(',',':'))+'\n'+json.dumps(body,separators=(',',':'))+'\n').encode()

@dataclass(frozen=True)
class Case:
    name:str
    raw:bytes
    expected:str
    reason:str

def cases():
    result=[]
    def add(name,expected,reason,change=None,raw_change=None):
        metadata,body=report()
        if change:change(metadata,body)
        raw=encoded(metadata,body)
        if raw_change:raw=raw_change(raw)
        result.append(Case(name,raw,expected,reason))
    add('exact_owned','retain','Exact product, UUID, window and identifiers')
    def no_debug(m,b):
        b['usedImages'].pop();b['threads'][1]['frames'].pop()
    add('debug_dylib_absent','retain','Absence must remain observable, not reject a loader report',no_debug)
    def loader(m,b):
        b['usedImages']=[];b['threads']=[];b.pop('faultingThread')
        b['termination']={'namespace':'DYLD','code':1,'indicator':'Library missing'}
    add('early_loader_without_loaded_images','retain','Metadata slice UUID still binds the exact executable',loader)
    add('malformed_bundle','reject','Bundle metadata must be an object',lambda m,b:b.update(bundleInfo=[]))
    add('wrong_bundle','reject','Wrong owned identity',lambda m,b:b['bundleInfo'].update(CFBundleIdentifier='Other.Extension'))
    add('wrong_metadata_bundle','reject','Conflicting metadata identity',lambda m,b:m.update(bundleID='Other.Extension'))
    add('wrong_name','reject','Wrong process',lambda m,b:b.update(procName='Other'))
    add('wrong_slice_uuid','reject','Different build',lambda m,b:m.update(slice_uuid=DEBUG_UUID))
    add('missing_slice_uuid','reject','No exact executable UUID binding',lambda m,b:m.pop('slice_uuid'))
    add('wrong_path','reject','Same basename from another product',lambda m,b:b.update(procPath=EXE.replace('celluloid-sandbox','other-build')))
    add('suffix_only_path','reject','Basename/suffix cannot establish product',lambda m,b:b.update(procPath='CelluloidMacPhotosExtension'))
    add('traversal_path','reject','Do not canonicalize report-supplied traversal',lambda m,b:b.update(procPath=EXE.replace('/Contents/MacOS/','/Contents/Other/../MacOS/')))
    add('wildcard_path','reject','No unbounded wildcard matching',lambda m,b:b.update(procPath='*/CelluloidMacPhotosExtension'))
    add('unknown_redaction','reject','Only explicitly reviewed placeholder can be considered',lambda m,b:b.update(procPath=EXE.replace('/Users/runner','/Users/OTHER')))
    add('stale_capture','reject','Outside exact host test',lambda m,b:b.update(captureTime='2026-10-05 07:16:00.000 +0000'))
    add('future_capture','reject','Outside exact host test',lambda m,b:b.update(captureTime='2026-10-05 07:20:00.000 +0000'))
    add('ambiguous_capture_timezone','reject','No implicit timezone',lambda m,b:b.update(captureTime='2026-10-05 07:19:17.6300'))
    add('non_crash_bug_type','reject','IPS is not a crash report',lambda m,b:m.update(bug_type='288'))
    add('conflicting_incident','reject','Two IPS objects disagree',lambda m,b:b.update(incident=MAIN_UUID))
    add('main_image_conflict','reject','Loaded owned image contradicts binding',lambda m,b:b['usedImages'][1].update(uuid=DEBUG_UUID))
    add('debug_image_conflict','reject','If loaded, owned debug image must match',lambda m,b:b['usedImages'][2].update(uuid=MAIN_UUID))
    add('dangling_frame_image','reject','Cannot reconstruct stack image provenance',lambda m,b:b['threads'][1]['frames'][0].update(imageIndex=99))
    add('bool_frame_index','reject','Exact primitive types',lambda m,b:b['threads'][1]['frames'][0].update(imageIndex=True))
    add('negative_frame_index','reject','No Python negative-index fallback',lambda m,b:b['threads'][1]['frames'][0].update(imageIndex=-1))
    add('ambiguous_faulting_thread','reject','Triggered and indexed thread disagree',lambda m,b:b.update(faultingThread=0))
    add('too_many_frames','reject','Do not silently truncate',lambda m,b:b['threads'][1].update(frames=[{'imageIndex':0,'imageOffset':16}]*129))
    add('oversized_report','reject','Input cap',lambda m,b:b.update(unretained_padding='x'*(512*1024)))
    for value,name in [(float('nan'),'nan'),(float('inf'),'infinity'),(-float('inf'),'negative_infinity')]:
        add(name,'reject','Strict JSON even in otherwise unprojected fields',lambda m,b,v=value:b.update(unretained=v))
    add('duplicate_metadata_key','reject','Strict first JSON object',raw_change=lambda raw:raw.replace(b'"bug_type":"309"',b'"bug_type":"309","bug_type":"309"',1))
    add('duplicate_body_key','reject','Strict second JSON object',raw_change=lambda raw:raw.replace(b'"pid":101',b'"pid":101,"pid":101',1))
    add('third_object','reject','No ignored trailing payload',raw_change=lambda raw:raw+b'{}\n')
    add('truncated','reject','No partial payload acceptance',raw_change=lambda raw:raw[:-10])
    add('invalid_utf8','reject','No replacement decoding',raw_change=lambda raw:raw+b'\xff')
    return result

import tempfile,unittest,os,subprocess,sys,time
from pathlib import Path
from unittest import mock
import mac_owned_crash as crash
import test_mac_host_transport as transport_tests

WINDOW={'start':BINDING['window_start'],'end':BINDING['window_end']}

class OwnedCrashTests(unittest.TestCase):
    def test_report_vectors_require_exact_owned_product_and_strict_json(self):
        for case in cases():
            with self.subTest(case=case.name):
                if case.expected=='retain':self.assertEqual(crash.projection(case.raw,BINDING,WINDOW)['executable_uuid'],MAIN_UUID)
                else:
                    with self.assertRaises((ValueError,KeyError,TypeError,UnicodeError)):crash.projection(case.raw,BINDING,WINDOW)

    def test_only_literal_username_privacy_substitution_is_supported(self):
        m,b=report();b['procPath']=EXE.replace('/Users/runner/','/Users/USER/')
        for image in b['usedImages']:
            if image['path'].startswith('/Users/runner/'):image['path']=image['path'].replace('/Users/runner/','/Users/USER/')
        self.assertEqual(crash.projection(encoded(m,b),BINDING,WINDOW)['procPath'],b['procPath'])
        for path in [EXE.replace('/Users/runner/work/_temp','/Users/USER/*'),EXE.replace('/work/','/WORK/'),EXE+'/',EXE.replace('/runner/','/USER2/')]:
            with self.subTest(path=path):self.assertFalse(crash.same_path(path,EXE))

    def test_rejected_path_metadata_requires_exact_identity_incident_and_window(self):
        m,b=report();b['procPath']=EXE.replace('/Users/runner/work/_temp','/Users/USER/*')
        with self.assertRaises(crash.OwnedCandidatePathMismatch) as caught:crash.projection(encoded(m,b),BINDING,WINDOW)
        observed=caught.exception.observation
        self.assertFalse(observed['acceptance']);self.assertFalse(observed['path_match'])
        self.assertEqual(observed['observed_procPath'],b['procPath']);self.assertEqual(observed['expected_procPath'],EXE)
        self.assertNotIn('diagnostic',observed);self.assertNotIn('threads',observed)
        for change in [lambda m,b:m.update(slice_uuid=DEBUG_UUID),lambda m,b:b.update(incident=MAIN_UUID),
                       lambda m,b:b['bundleInfo'].update(CFBundleIdentifier='other'),
                       lambda m,b:b.update(procName='other'),lambda m,b:b.update(captureTime='2026-10-05 07:20:00.000 +0000'),
                       lambda m,b:b.update(procLaunch='2026-10-05 07:00:00.000 +0000'),lambda m,b:b.update(pid=True),
                       lambda m,b:b.update(procPath='/'+'x'*2048),lambda m,b:b.update(procPath='/bad\npath'),
                       lambda m,b:b.update(procPath=[]),lambda m,b:b.update(procPath='relative/path')]:
            metadata,body=copy.deepcopy(m),copy.deepcopy(b);change(metadata,body)
            try:crash.projection(encoded(metadata,body),BINDING,WINDOW)
            except crash.OwnedCandidatePathMismatch:self.fail('Unqualified/malformed candidate leaked path observation')
            except (ValueError,TypeError,KeyError):pass
            else:self.fail('Malformed candidate accepted')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();(root/f'{crash.NAME}-owned.ips').write_bytes(encoded(m,b))
            row=crash.collect_reports(root,BINDING,WINDOW)
            self.assertEqual(row['matched_count'],0);self.assertEqual(row['incidents'],[])
            self.assertEqual(row['state'],'incomplete-rejected-candidates')
            self.assertEqual(row['rejected'][0]['owned_path_mismatch'],observed)

    def rejected_detail(self,metadata,body):
        body['procPath']=EXE.replace('/Users/runner/work/_temp','/Users/USER/*')
        with self.assertRaises(crash.OwnedCandidatePathMismatch) as caught:
            crash.projection(encoded(metadata,body),BINDING,WINDOW)
        return caught.exception.observation

    def test_uuid_bound_path_unverified_projection_retains_cause_but_stays_rejected(self):
        metadata,body=report();body['asi']={'CelluloidMacPhotosExtension':['Synthetic fatal assertion']}
        for image in body['usedImages']:
            if image['path'].startswith('/Users/runner/'):
                image['path']=image['path'].replace('/Users/runner/work/_temp','/Users/USER/*')
        body['usedImages'].append({'uuid':'55555555-5555-4555-8555-555555555555','path':'/unrelated/private-marker'})
        observation=self.rejected_detail(metadata,body);detail=observation['uuid_bound_diagnostic']
        self.assertEqual(observation['schema'],'Celluloid.OwnedPathMismatch.2')
        self.assertEqual(detail['schema'],'Celluloid.UUIDBoundPathUnverifiedCrash.1')
        self.assertFalse(detail['acceptance']);self.assertFalse(detail['executable_path_verified'])
        self.assertEqual(detail['diagnostic']['exception']['signal'],'SIGABRT')
        self.assertEqual(detail['application_specific'],body['asi'])
        self.assertEqual(detail['uuid_bound_image_path_matches'],{'executable':False,'debug_dylib':False})
        self.assertEqual(detail['uuid_bound_image_indexes'],{'executable':1,'debug_dylib':2})
        self.assertTrue(detail['uuid_bound_debug_dylib_loaded'])
        raw=json.dumps(observation)
        for forbidden in ['private-device-marker','unrelated-thread-state','unrelated-trial-marker','noncrashed-private-marker','/unrelated/private-marker','owned_image_indexes','"debug_dylib_loaded"']:
            self.assertNotIn(forbidden,raw)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();(root/f'{crash.NAME}-owned.ips').write_bytes(encoded(metadata,body))
            result=crash.collect_reports(root,BINDING,WINDOW)
            self.assertEqual(result['matched_count'],0);self.assertEqual(result['incidents'],[])
            self.assertEqual(result['state'],'incomplete-rejected-candidates')
            self.assertEqual(result['rejected'][0]['owned_path_mismatch'],observation)
        # The same redacted loaded-image paths are still rejected if the process
        # path passes: diagnostics cannot broaden the accepted projection path.
        body['procPath']=EXE
        with self.assertRaisesRegex(ValueError,'Conflicting/duplicate owned image'):
            crash.projection(encoded(metadata,body),BINDING,WINDOW)

    def test_unverified_loader_diagnostic_does_not_require_debug_dylib_presence(self):
        metadata,body=report();body['usedImages']=[];body['threads']=[];body.pop('faultingThread')
        body['termination']={'namespace':'DYLD','code':1,'indicator':'Library missing'}
        detail=self.rejected_detail(metadata,body)['uuid_bound_diagnostic']
        self.assertEqual(detail['diagnostic']['termination']['namespace'],'DYLD')
        self.assertEqual(detail['images'],[]);self.assertFalse(detail['uuid_bound_debug_dylib_loaded'])

    def test_unverified_projection_keeps_all_uuid_type_frame_image_and_payload_caps(self):
        changes=[lambda b:b['usedImages'][1].update(uuid=DEBUG_UUID),
                 lambda b:b['usedImages'][2].update(uuid=MAIN_UUID),
                 lambda b:b['usedImages'][1].update(path='/bad\npath'),
                 lambda b:b['usedImages'][1].update(path='/'+'x'*2048),
                 lambda b:b['usedImages'].append(dict(b['usedImages'][1])),
                 lambda b:b['threads'][1]['frames'][0].update(imageIndex=99),
                 lambda b:b['threads'][1]['frames'][0].update(imageIndex=True),
                 lambda b:b['threads'][1].update(frames=[{'imageIndex':0,'imageOffset':0}]*129),
                 lambda b:b.update(faultingThread=0),lambda b:b.update(usedImages=[{}]*1025),
                 lambda b:b.update(threads=[{}]*257),lambda b:b.update(reportNotes=['x']*17),
                 lambda b:b.update(asi={'module':['x'*4097]}),lambda b:b.update(asi={'module':['x']*9}),
                 lambda b:b.update(asi={str(i):[] for i in range(9)}),
                 lambda b:b.update(exception={'message':{'unexpected':'object'}},termination={})]
        for change in changes:
            metadata,body=report();change(body)
            with self.subTest(change=changes.index(change)):
                observation=self.rejected_detail(metadata,body)
                self.assertNotIn('uuid_bound_diagnostic',observation)
                self.assertTrue(observation['projection_error']);self.assertFalse(observation['acceptance'])

    def test_unverified_and_accepted_incidents_share_count_duplicate_and_output_caps(self):
        for count,expected in [(4,None),(5,'incident count cap')]:
            with tempfile.TemporaryDirectory() as folder:
                root=self.populate(folder,count)
                for index,path in enumerate(sorted(root.iterdir())):
                    if index%2:
                        first,second=path.read_text().split('\n',1);metadata=json.loads(first);body=json.loads(second)
                        body['procPath']=EXE.replace('/Users/runner/work/_temp','/Users/USER/*');path.write_bytes(encoded(metadata,body))
                if expected:
                    with self.assertRaisesRegex(ValueError,expected):crash.collect_reports(root,BINDING,WINDOW)
                else:
                    result=crash.collect_reports(root,BINDING,WINDOW)
                    self.assertEqual(result['matched_count'],2);self.assertEqual(len(result['rejected']),2)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();metadata,body=report();body['procPath']=EXE+'/other'
            for index in range(2):(root/f'{crash.NAME}-{index}.ips').write_bytes(encoded(metadata,body))
            with self.assertRaisesRegex(ValueError,'Duplicate incident'):crash.collect_reports(root,BINDING,WINDOW)
        with tempfile.TemporaryDirectory() as folder,mock.patch.object(crash,'MAX_OUTPUT',8200):
            root=Path(folder).resolve();metadata,body=report();body['procPath']=EXE+'/other'
            (root/f'{crash.NAME}-owned.ips').write_bytes(encoded(metadata,body))
            with self.assertRaisesRegex(ValueError,'Projection byte cap'):crash.collect_reports(root,BINDING,WINDOW)

    def test_projection_drops_unrelated_fields_and_remaps_only_needed_images(self):
        m,b=report();b['usedImages'].insert(0,{'uuid':'55555555-5555-4555-8555-555555555555','path':'/unrelated/private-marker'})
        for thread in b['threads']:
            for frame in thread['frames']:frame['imageIndex']+=1
        row=crash.projection(encoded(m,b),BINDING,WINDOW);raw=json.dumps(row)
        for forbidden in ['private-device-marker','unrelated-thread-state','unrelated-trial-marker','noncrashed-private-marker','/unrelated/private-marker']:
            self.assertNotIn(forbidden,raw)
        self.assertEqual([i['originalIndex'] for i in row['images']],[1,2,3])
        self.assertEqual([f['imageIndex'] for f in row['crashed_threads'][0]['frames']],[0,2])
        self.assertEqual(row['owned_image_indexes'],{'executable':1,'debug_dylib':2})

    def populate(self,folder,count=1):
        root=Path(folder).resolve();root.mkdir(exist_ok=True)
        for i in range(count):
            m,b=report();incident=f'{i:08x}-4444-4444-8444-444444444444';m['incident_id']=b['incident']=incident
            (root/f'{crash.NAME}-2026-10-05-{i}.ips').write_bytes(encoded(m,b))
        return root

    def test_all_matching_incidents_and_empty_scan_are_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            root=self.populate(folder,4);(root/'unrelated.ips').write_bytes(b'not opened')
            actual_read=crash.safe_read;seen=[]
            def read(path,cap):seen.append(Path(path).name);return actual_read(path,cap)
            with mock.patch.object(crash,'safe_read',side_effect=read):row=crash.collect_reports(root,BINDING,WINDOW)
            self.assertEqual(row['matched_count'],4);self.assertEqual(row['state'],'complete');self.assertEqual(len(seen),4)
            self.assertNotIn('unrelated.ips',seen)
        with tempfile.TemporaryDirectory() as folder:self.assertEqual(crash.collect_reports(Path(folder).resolve(),BINDING,WINDOW)['incidents'],[])

    def test_count_directory_candidate_input_and_output_caps_fail_explicitly(self):
        for count,limit in [(5,'Matching incident'),(17,'Candidate scan')]:
            with tempfile.TemporaryDirectory() as folder:
                with self.assertRaisesRegex(ValueError,limit):crash.collect_reports(self.populate(folder,count),BINDING,WINDOW)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve()
            for i in range(257):(root/f'unrelated-{i}').write_text('x')
            with self.assertRaisesRegex(ValueError,'Directory scan'):crash.collect_reports(root,BINDING,WINDOW)
        for name,value,error in [('MAX_TOTAL_INPUT',10,'Invalid/oversized input'),('MAX_OUTPUT',8200,'Projection byte')]:
            with tempfile.TemporaryDirectory() as folder,mock.patch.object(crash,name,value):
                with self.assertRaisesRegex(ValueError,error):crash.collect_reports(self.populate(folder),BINDING,WINDOW)
        with tempfile.TemporaryDirectory() as folder:
            root=self.populate(folder,2);files=sorted(root.iterdir());files[1].write_bytes(files[0].read_bytes())
            with self.assertRaisesRegex(ValueError,'Duplicate incident'):crash.collect_reports(root,BINDING,WINDOW)

    def test_aggregate_cap_is_admitted_before_reads_including_rejected_candidates(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();raw=b'{}\n{}\n'+b' '*(crash.MAX_INPUT-6)
            for i in range(5):(root/f'{crash.NAME}-{i}.ips').write_bytes(raw)
            real_read=os.read;bytes_read=0
            def read(fd,count):
                nonlocal bytes_read
                data=real_read(fd,count);bytes_read+=len(data);return data
            with mock.patch.object(crash.os,'read',side_effect=read):
                with self.assertRaisesRegex(ValueError,'Aggregate input cap before read'):crash.collect_reports(root,BINDING,WINDOW)
            self.assertEqual(bytes_read,crash.MAX_TOTAL_INPUT)
            bytes_read=0
            with mock.patch.object(crash,'MAX_TOTAL_INPUT',crash.MAX_INPUT+127),mock.patch.object(crash.os,'read',side_effect=read):
                with self.assertRaisesRegex(ValueError,'Invalid/oversized input'):crash.collect_reports(root,BINDING,WINDOW)
            self.assertEqual(bytes_read,crash.MAX_INPUT,'Stat rejects the next file before reading beyond remaining allowance')

    def test_unmatched_or_malformed_fixed_prefix_candidates_are_explicit_incomplete(self):
        with tempfile.TemporaryDirectory() as folder:
            root=self.populate(folder);(root/f'{crash.NAME}-bad.ips').write_bytes(b'not JSON\n{}')
            row=crash.collect_reports(root,BINDING,WINDOW)
            self.assertEqual(row['state'],'incomplete-rejected-candidates');self.assertEqual(row['matched_count'],1)
            self.assertEqual(len(row['rejected']),1);self.assertNotIn('not JSON',json.dumps(row))

    def test_no_follow_nonregular_and_replaced_during_read(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();owned=root/'owned';owned.write_bytes(b'owned');link=root/'link';link.symlink_to(owned)
            with self.assertRaisesRegex(ValueError,'Symlink'):crash.safe_read(link,100)
            directory=root/'directory';directory.mkdir()
            with self.assertRaisesRegex(ValueError,'regular|Invalid'):crash.safe_read(directory,100)
            real_read=os.read;changed=False
            def read(fd,count):
                nonlocal changed
                data=real_read(fd,count)
                if not changed:owned.write_bytes(b'other');changed=True
                return data
            with mock.patch.object(crash.os,'read',side_effect=read):
                with self.assertRaisesRegex(ValueError,'changed during'):crash.safe_read(owned,100)
            link.unlink();link.symlink_to(directory,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'Symlink'):crash.collect_reports(link,BINDING,WINDOW)

    def host_log(self):
        fixture=transport_tests.HostTransportTests();fixture.setUp();log=fixture.transcript()
        lines=log.splitlines();begin=json.loads(lines[0].split(' ',1)[1]);begin['utc']='2026-10-05T07:17:00+00:00';lines[0]='BOUNDED_COMMAND_BEGIN '+json.dumps(begin)
        log='\n'.join(lines)+'\n'
        log=log.replace("Test Case '","2026-10-05 07:17:07.000000+0000 CelluloidMacUITests-Runner[1:2] Running tests...\nTest Case '",1)
        log=log.replace(" started.\n"," started.\n    t =     0.00s Start Test at 2026-10-05 07:17:08.834\n")
        log=log.replace('passed (1.0 seconds).','failed (129.195 seconds).\nTest Suite \'MacPhotosHostUITests\' failed at 2026-10-05 07:19:18.029.')
        log=log.replace('** TEST EXECUTE SUCCEEDED **','** TEST EXECUTE FAILED **').replace('"exit_code": 0','"exit_code": 65').replace('"elapsed_seconds": 1','"elapsed_seconds": 140')
        summary={'totalTestCount':1,'passedTests':0,'failedTests':1,'skippedTests':0,'startTime':1791184623.288,'finishTime':1791184758.752}
        return fixture,log,summary

    def test_case_window_is_exact_and_reconciled_with_summary_and_process(self):
        f,log,summary=self.host_log();row=crash.test_window(log,summary,f.context,f.context_hash)
        self.assertAlmostEqual(row['start'],1791184628.834,places=5);self.assertAlmostEqual(row['end'],1791184758.029,places=5)
        for change in [lambda s:s.update(totalTestCount=True),lambda s:s.update(startTime=10**1000),lambda s:s.update(startTime=1791184640),lambda s:s.update(finishTime=1791184750),lambda s:s.update(failedTests=True),lambda s:s.update(skippedTests=1)]:
            edited=copy.deepcopy(summary);change(edited)
            with self.assertRaises(ValueError):crash.test_window(log,edited,f.context,f.context_hash)
        for edited in [log.replace('+0000 Celluloid',' Celluloid'),log.replace('Start Test at','Start Test maybe'),log.replace('129.195 seconds','129.995 seconds'),log.replace('"utc": "2026-10-05T07:17:00+00:00"','"utc": "2026-10-05T07:17:00"')]:
            with self.assertRaises((ValueError,KeyError)):crash.test_window(edited,summary,f.context,f.context_hash)

    def test_built_main_and_debug_uuids_are_separate_and_only_exact_files_read(self):
        bound={k:v for k,v in BINDING.items() if k.startswith(('expected_','executable_','debug_dylib_'))}
        bound.update(executable_bytes=10,debug_dylib_bytes=20);bound.pop('executable_uuid');bound.pop('debug_dylib_uuid')
        context={'source_sha':'a'*40,'test_source_sha256':'c'*64,'script_sha256':'f'*64}
        def command(args,**kwargs):
            self.assertEqual(args[:3],['/usr/bin/xcrun','dwarfdump','--uuid']);self.assertEqual(kwargs['timeout'],8)
            return f"UUID: {MAIN_UUID if args[3]==EXE else DEBUG_UUID} (arm64) {args[3]}\n"
        with mock.patch.object(crash,'bound_product',return_value=bound),mock.patch.object(crash.subprocess,'check_output',side_effect=command) as called:
            row=crash.prepare(Path('/synthetic'),context,'b'*64)
        self.assertEqual(called.call_count,2);self.assertEqual(row['executable_uuid'],MAIN_UUID);self.assertEqual(row['debug_dylib_uuid'],DEBUG_UUID)
        with mock.patch.object(crash,'bound_product',return_value=bound),mock.patch.object(crash.subprocess,'check_output',return_value='ambiguous UUID'):
            with self.assertRaisesRegex(ValueError,'Mach-O UUID'):crash.prepare(Path('/synthetic'),context,'b'*64)

    def test_bound_product_recomputes_both_current_files_from_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();app=root/'CelluloidMac.app';exe=app/'Contents/PlugIns'/f'{crash.NAME}.appex/Contents/MacOS'/crash.NAME
            exe.parent.mkdir(parents=True);exe.write_bytes(b'main');debug=Path(str(exe)+'.debug.dylib');debug.write_bytes(b'debug')
            context={'app_path':str(app),'extension_executable':str(exe),'extension_executable_sha256':crash.digest(b'main'),
                'bundle_manifest':[[str(p.relative_to(app)),p.stat().st_size,crash.digest(p.read_bytes())] for p in [exe,debug]]}
            result=crash.bound_product(root,context)
            self.assertEqual(result['debug_dylib_sha256'],crash.digest(b'debug'))
            debug.write_bytes(b'other')
            with self.assertRaisesRegex(ValueError,'Changed built'):crash.bound_product(root,context)
            debug.unlink();debug.symlink_to(exe)
            with self.assertRaisesRegex(ValueError,'Symlink'):crash.bound_product(root,context)

    def test_capture_replays_source_product_and_window_bindings(self):
        fixture,log,summary=self.host_log()
        bound={k:v for k,v in BINDING.items() if k.startswith(('expected_','executable_','debug_dylib_'))}
        bound.update(executable_bytes=10,debug_dylib_bytes=20)
        product={k:v for k,v in bound.items() if not k.endswith('_uuid')}
        identity={'schema':'Celluloid.OwnedCrashIdentity.1','acceptance':False,'complete_host_e2e':False,'source_sha':fixture.context['source_sha'],
            'context_sha256':fixture.context_hash,'test_source_sha256':fixture.context['test_source_sha256'],
            'verifier_sha256':fixture.context['script_sha256'],'collector_sha256':crash.digest(Path(crash.__file__).read_bytes()),
            'extension_id':BUNDLE,**bound}
        with tempfile.TemporaryDirectory() as folder,mock.patch.object(crash,'bound_product',return_value=product):
            root=Path(folder).resolve();directory=self.populate(root/'reports')
            (root/crash.IDENTITY).write_bytes(crash.encode(identity));(root/'mac-host-test.log').write_text(log)
            (root/'mac-host-summary.json').write_bytes(crash.encode(summary))
            row=crash.capture(root,fixture.context,fixture.context_hash,directory)
            self.assertEqual(row['state'],'complete');self.assertEqual(row['matched_count'],1)
            self.assertFalse(row['acceptance']);self.assertFalse(row['complete_host_e2e'])
            self.assertEqual(row['window']['result'],'failed')
            for key in ['source_sha','context_sha256','test_source_sha256','verifier_sha256','collector_sha256','extension_id','executable_sha256','debug_dylib_sha256']:
                changed=dict(identity);changed[key]='wrong';(root/crash.IDENTITY).write_bytes(crash.encode(changed))
                with self.subTest(key=key),self.assertRaises(ValueError):crash.capture(root,fixture.context,fixture.context_hash,directory)
            (root/crash.IDENTITY).write_bytes(crash.encode(identity));(root/'mac-host-summary.json').write_text('{}')
            with self.assertRaises(ValueError):crash.capture(root,fixture.context,fixture.context_hash,directory)

    def test_necessary_image_and_nested_payload_caps_reject_without_truncation(self):
        m,b=report();b['usedImages'] += [dict(b['usedImages'][0],uuid=f'{i:08x}-3333-4333-8333-333333333333') for i in range(64)]
        b['threads'][1]['frames']=[{'imageIndex':i,'imageOffset':1} for i in range(len(b['usedImages']))]
        with self.assertRaisesRegex(ValueError,'Necessary image cap'):crash.projection(encoded(m,b),BINDING,WINDOW)
        m,b=report();b['termination']['reasons']=['x']*17
        with self.assertRaisesRegex(ValueError,'array cap'):crash.projection(encoded(m,b),BINDING,WINDOW)

    def test_diagnostic_output_never_clobbers_and_malformed_records_are_not_collected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'fixed.json';crash.write_new(path,b'first')
            with self.assertRaises(FileExistsError):crash.write_new(path,b'changed')
            self.assertEqual(path.read_bytes(),b'first')
        valid={'schema':'Celluloid.OwnedCrashCollectionError.1','source_sha':'a'*40,'acceptance':False,
            'complete_host_e2e':False,'state':'incomplete','phase':'capture','error':'bounded failure'}
        crash.validate_diagnostic(crash.encode(valid),'a'*40,crash.OUTPUT)
        for key,value in [('source_sha','b'*40),('acceptance',True),('complete_host_e2e',True),('schema','other'),('phase','prepare')]:
            changed=dict(valid);changed[key]=value
            with self.assertRaises(ValueError):crash.validate_diagnostic(crash.encode(changed),'a'*40,crash.OUTPUT)

    def test_application_specific_messages_are_bounded_data_only(self):
        m,b=report();b['asi']={'libswiftCore.dylib':['Fatal error: synthetic assertion','Untrusted diagnostic text is data only']}
        row=crash.projection(encoded(m,b),BINDING,WINDOW)
        self.assertEqual(row['application_specific'],b['asi']);self.assertNotIn('crashReporterKey',row)
        for asi in [[],{'module':True},{'module':['x']*9},{'module':['x'*4097]},
                    {str(i):['x'] for i in range(9)},{'module':['x'*4096]*5}]:
            b['asi']=asi
            with self.subTest(asi_type=type(asi).__name__),self.assertRaises(ValueError):crash.projection(encoded(m,b),BINDING,WINDOW)

    def test_shared_deadline_preserves_mandatory_reserves_and_clips_only_optional_time(self):
        clock={'source_sha':'a'*40,'started_monotonic':100.0,'execution_budget_seconds':2460}
        for action,reserve in [('prepare',1020),('capture',300)]:
            for spare,wanted in [(40,20),(17.25,5.25),(12.5,0),(12,0),(0,0),(-10,0)]:
                now=2560-reserve-spare;row=crash.optional_budget(clock,'a'*40,action,now)
                self.assertEqual(row['mandatory_reserve_seconds'],reserve);self.assertEqual(row['command_seconds'],wanted)
                self.assertEqual(row['admitted'],wanted>0)
                if wanted:self.assertGreaterEqual(2560-now-wanted-12,reserve)
        for changes in [{'source_sha':'b'*40},{'execution_budget_seconds':2700},{'started_monotonic':float('nan')},{'started_monotonic':True},{'started_monotonic':9999}]:
            with self.assertRaises(ValueError):crash.optional_budget(dict(clock,**changes),'a'*40,'prepare',200)

    def test_optional_execution_requires_confirmed_child_end_and_records_skips(self):
        context={'source_sha':'a'*40};clock={'source_sha':'a'*40,'started_monotonic':100.0,'execution_budget_seconds':2460}
        for outcome in ['success','no-end','wrong-exit','oversize','timeout','skip']:
            with self.subTest(outcome=outcome),tempfile.TemporaryDirectory() as folder:
                root=Path(folder).resolve();(root/'mac-job-clock.json').write_bytes(crash.encode(clock))
                (root/'mac-host-budget.json').write_bytes(crash.encode({'source_sha':'a'*40,'clock_sha256':crash.digest(crash.encode(clock))}))
                def command(args,command_deadline,cleanup_deadline):
                    self.assertEqual(command_deadline,220);self.assertEqual(cleanup_deadline,230)
                    self.assertEqual(args[-1],'prepare')
                    row={'schema':'Celluloid.OwnedCrashIdentity.1','source_sha':'a'*40,'acceptance':False,'complete_host_e2e':False}
                    (root/crash.IDENTITY).write_bytes(crash.encode(row))
                    return {'finalized':outcome in {'success','wrong-exit','timeout'},'output':b'bounded','return_code':1 if outcome=='wrong-exit' else 0,
                        'timed_out':outcome=='timeout','overflow':outcome=='oversize'}
                with mock.patch.object(crash.time,'monotonic',return_value=1530 if outcome=='skip' else 200),mock.patch.object(crash,'bounded_optional_process',side_effect=command) as called:
                    row=crash.optional_execute(root,context,'b'*64,'prepare')
                self.assertEqual(called.call_count,0 if outcome=='skip' else 1)
                self.assertEqual(row['optional_execution']['finalized'],outcome in {'success','wrong-exit','timeout'})
                if outcome!='success':self.assertEqual(row['state'],'incomplete')
                self.assertFalse(row['acceptance'])

    def test_no_capture_child_after_unknown_host_or_prior_child_or_mandatory_work(self):
        fixture,log,summary=self.host_log()
        for mode in ['success','identity-unfinalized','host-unfinalized','product-unfinalized','source-unfinalized']:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as folder:
                root=Path(folder).resolve();identity={'schema':'Celluloid.OwnedCrashIdentity.1','source_sha':fixture.context['source_sha'],
                    'acceptance':False,'complete_host_e2e':False,'optional_execution':{'finalized':mode!='identity-unfinalized'}}
                (root/crash.IDENTITY).write_bytes(crash.encode(identity))
                (root/'mac-host-test.log').write_text(log if mode!='host-unfinalized' else log.split('BOUNDED_COMMAND_END')[0])
                (root/'mac-host-summary.json').write_bytes(crash.encode(summary))
                product={key:fixture.context[key] for key in ['app_executable_sha256','extension_executable_sha256']}
                product.update(installed_bytes_unchanged=True,strict_signatures_unchanged=mode!='product-unfinalized')
                (root/'mac-host-product-after.json').write_bytes(crash.encode(product))
                (root/'mac-host-source-after.json').write_bytes(crash.encode({'phase':'before' if mode=='source-unfinalized' else 'after','source_sha':fixture.context['source_sha']}))
                clock={'source_sha':fixture.context['source_sha'],'started_monotonic':100.0,'execution_budget_seconds':2460}
                (root/'mac-job-clock.json').write_bytes(crash.encode(clock))
                (root/'mac-host-budget.json').write_bytes(crash.encode({'source_sha':fixture.context['source_sha'],'clock_sha256':crash.digest(crash.encode(clock))}))
                def command(args,command_deadline,cleanup_deadline):
                    output={'schema':'Celluloid.OwnedCrashProjection.1','source_sha':fixture.context['source_sha'],
                        'acceptance':False,'complete_host_e2e':False,'identity':identity,'state':'complete','incidents':[],'matched_count':0}
                    (root/crash.OUTPUT).write_bytes(crash.encode(output))
                    return {'finalized':True,'output':b'bounded','return_code':0,'timed_out':False,'overflow':False}
                with mock.patch.object(crash.time,'monotonic',return_value=200),mock.patch.object(crash,'bounded_optional_process',side_effect=command) as called:
                    row=crash.optional_execute(root,fixture.context,fixture.context_hash,'capture')
                self.assertEqual(called.call_count,1 if mode=='success' else 0)
                self.assertEqual(row['state'],'complete' if mode=='success' else 'incomplete')

    def test_real_optional_process_requires_pipe_eof_and_direct_child_completion(self):
        start=time.monotonic()
        row=crash.bounded_optional_process([sys.executable,'-c','print("owned", flush=True)'],start+2,start+3)
        self.assertTrue(row['finalized']);self.assertTrue(row['pipe_eof']);self.assertTrue(row['child_reaped'])
        self.assertEqual(row['output'],b'owned\n');self.assertEqual(row['return_code'],0)
        self.assertFalse(row['timed_out']);self.assertFalse(row['overflow'])

    def test_real_descendant_retaining_stdout_cannot_extend_outer_deadline(self):
        descendant='import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print("descendant",flush=True); time.sleep(14)'
        child='import subprocess,sys; subprocess.Popen([sys.executable,"-c",'+repr(descendant)+']); print("leader exiting",flush=True)'
        start=time.monotonic();row=crash.bounded_optional_process([sys.executable,'-c',child],start+0.3,start+2.5)
        self.assertLess(time.monotonic()-start,3.0)
        self.assertTrue(row['timed_out']);self.assertTrue(row['child_reaped']);self.assertTrue(row['pipe_eof'])
        self.assertIn(b'descendant',row['output']);self.assertLessEqual(row['bytes_read'],8192)

    def test_real_output_flood_is_stopped_at_read_cap_not_posthoc(self):
        child='import os,time; os.write(1,b"x"*1000000); time.sleep(14)'
        start=time.monotonic();row=crash.bounded_optional_process([sys.executable,'-c',child],start+2,start+3,cap=1024)
        self.assertLess(time.monotonic()-start,3.5);self.assertTrue(row['overflow'])
        self.assertEqual(row['bytes_read'],1024);self.assertEqual(len(row['output']),1024)
        self.assertFalse(row['finalized'],'Unread pipe completion is explicitly unconfirmed')
        self.assertTrue(row['child_reaped'])

    def test_spawn_delay_does_not_renew_deadline_and_expired_admission_never_spawns(self):
        real_popen=crash.subprocess.Popen
        def slow_spawn(*args,**kwargs):time.sleep(0.15);return real_popen(*args,**kwargs)
        start=time.monotonic()
        with mock.patch.object(crash.subprocess,'Popen',side_effect=slow_spawn):
            row=crash.bounded_optional_process([sys.executable,'-c','import time;time.sleep(14)'],start+0.1,start+1)
        self.assertTrue(row['timed_out']);self.assertLess(time.monotonic()-start,1.5)
        with mock.patch.object(crash.subprocess,'Popen') as called:
            with self.assertRaises(ValueError):crash.bounded_optional_process(['unused'],start-1,start)
            called.assert_not_called()

    def test_late_successful_wait_is_not_mislabeled_timely(self):
        from types import SimpleNamespace
        for observed,finalized in [(101.5,True),(104.0,False)]:
            reader,writer=os.pipe();os.write(writer,b'owned');os.close(writer);clock=[100.0]
            def wait(timeout):clock[0]=observed;return 0
            process=SimpleNamespace(stdout=os.fdopen(reader,'rb',buffering=0),pid=12345,returncode=0,wait=wait)
            with mock.patch.object(crash.time,'monotonic',side_effect=lambda:clock[0]),mock.patch.object(crash.subprocess,'Popen',return_value=process),mock.patch.object(crash.os,'killpg') as signalled:
                row=crash.bounded_optional_process(['synthetic'],101.0,103.0)
            signalled.assert_not_called();self.assertTrue(row['timed_out']);self.assertEqual(row['finalized'],finalized)
            self.assertEqual(row['elapsed_seconds'],observed-100.0)

    def test_late_eof_read_is_classified_by_actual_final_clock(self):
        from types import SimpleNamespace
        for observed,finalized in [(101.5,True),(104.0,False)]:
            reader,writer=os.pipe();os.write(writer,b'owned');os.close(writer);clock=[100.0];real_read=os.read
            def read(fd,count):
                data=real_read(fd,count)
                if not data:clock[0]=observed
                return data
            process=SimpleNamespace(stdout=os.fdopen(reader,'rb',buffering=0),pid=12345,returncode=0,wait=lambda timeout:0)
            with mock.patch.object(crash.time,'monotonic',side_effect=lambda:clock[0]),mock.patch.object(crash.os,'read',side_effect=read),mock.patch.object(crash.subprocess,'Popen',return_value=process),mock.patch.object(crash.os,'killpg') as signalled:
                row=crash.bounded_optional_process(['synthetic'],101.0,103.0)
            signalled.assert_not_called();self.assertTrue(row['pipe_eof']);self.assertTrue(row['timed_out'])
            self.assertEqual(row['finalized'],finalized)

    def test_source_relocates_optional_work_outside_unchanged_host_step(self):
        root=Path(__file__).resolve().parents[1];shell=(root/'Scripts/run_mac_photos_host_gate.sh').read_text()
        workflow=(root/'.github/workflows/apple-platforms.yml').read_text().split('  native-mac-host:',1)[1].split('  native-simulator:',1)[0]
        before=workflow.split('- name: Prepare verified Photos host context',1)[1].split('- name:',1)[0]
        host=workflow.split('- name: Actual Photos host discovery',1)[1].split('- name:',1)[0]
        evidence=workflow.split('- name: Bound and replay the dedicated host proof',1)[1].split('- name:',1)[0]
        self.assertNotIn('mac_owned_crash.py',shell+host)
        self.assertIn('timeout-minutes: 14',host);self.assertIn('--seconds 720',shell);self.assertIn('-maximum-test-execution-time-allowance 660',shell)
        self.assertIn("steps.host_context.outcome == 'success'",host)
        for action,block in [('prepare',before),('capture',evidence)]:
            line=next(l for l in block.splitlines() if f'mac_owned_crash.py optional-{action}' in l)
            self.assertTrue(line.endswith(' || true'))
        self.assertLess(before.index('budget-before-prepare'),before.index('source-before'))
        self.assertLess(before.index('source-before'),before.index('mac_photos_host_gate.py prepare'))
        self.assertLess(before.index('mac_photos_host_gate.py prepare'),before.index('optional-prepare'))
        self.assertLess(evidence.index('optional-capture'),evidence.index('mac_photos_host_gate.py collect'))
        self.assertIn('exit "$status"',shell)
        code=(root/'Scripts/mac_owned_crash.py').read_text()
        for forbidden in ['pluginkit','kill(','chmod(','TCC','sudo ','os.walk','rglob(']:self.assertNotIn(forbidden,code)
        self.assertIn("Path.home()/'Library/Logs/DiagnosticReports'",code)
        host_gate=(root/'Scripts/mac_photos_host_gate.py').read_text();proof=host_gate.split('PROOF_LIMITS = {',1)[1].split('\n}',1)[0]
        self.assertNotIn(crash.OUTPUT,proof);self.assertNotIn(crash.IDENTITY,proof)
        self.assertLess(host_gate.index('optional=[root/name for name in crash_limits'),host_gate.index('optional += [p'))

if __name__=='__main__':unittest.main()
