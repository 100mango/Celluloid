"""Synthetic continuation proofs cannot qualify rendering or real Photos hosts."""
import base64,contextlib,copy,hashlib,io,json,os,plistlib,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import verify_interop_continuation as gate
from native_fixture_handoff import FILTERS,LAYER_FILE
from verify_required_interoperability import required,verify as required_verify

class ContinuationTests(unittest.TestCase):
    SOURCE='a'*40
    def fixture(self):
        def item(data):return hashlib.sha256(data).hexdigest(),base64.b64encode(data).decode()
        png=b'\x89PNG\r\n\x1a\n'+b'\0\0\0\0IHDR'+(480).to_bytes(4,'big')+(640).to_bytes(4,'big')
        row={'name':'manufactured-affine','identifier':'Mango.CelluloidPhotoExtension','version':'1.0'}
        for data,h,b in [(b'archive','sha256','base64'),(png+b'source','sourceSHA256','sourceBase64'),(png+b'full','renderedSHA256','renderedBase64')]:row[h],row[b]=item(data)
        row['components']=[]
        for name in ['filtered-base','bubble-artwork','sticker-artwork','all-artwork']:
            h,b=item(png+name.encode());row['components'].append({'name':name,'sha256':h,'base64':b})
        return row
    def profile(self,profile='2x',failed=True):
        p,name,scale=next(r for r in gate.PROFILES if r[0]==profile);fixture=self.fixture()
        uid='12345678-1234-1234-1234-123456789AB'+('0' if profile=='2x' else '1')
        status='failed' if failed else 'passed';deltas={'full':202 if failed else 0,'filtered-base':0,'bubble-artwork':6 if failed else 0,'sticker-artwork':0,'all-artwork':6 if failed else 0}
        messages=[];lines=[f"Test Case '-[CelluloidTests.{gate.OWNER} {gate.METHOD}]' started.",f'MAC_LAYER_UIKIT_COMPOSITOR_DISPLAY scale={scale}']
        lines += ['MAC_LAYER_UIKIT_COMPOSITOR '+f"archiveSHA256={fixture['sha256']} sourceSHA256={fixture['sourceSHA256']} nativeSHA256={fixture['renderedSHA256']} maximumChannelDifference={deltas['full']}"]
        def error(name):
            message=f'XCTAssertLessThanOrEqual failed: ("{deltas[name]}") is greater than ("2") - '+(gate.FULL_MESSAGE if name=='full' else 'Independent UIKit component: '+name)
            messages.append(message);lines.append(f'/repo/{gate.TEST_SOURCE}:56: error: -[CelluloidTests.{gate.OWNER} {gate.METHOD}] : '+message)
        if failed:error('full')
        for row in fixture['components']:
            name=row['name'];lines.append(f"MAC_LAYER_UIKIT_COMPOSITOR_COMPONENT name={name} nativeSHA256={row['sha256']} maximumChannelDifference={deltas[name]}")
            if deltas[name]>2:error(name)
        lines += [f"Test Case '-[CelluloidTests.{gate.OWNER} {gate.METHOD}]' {status} (4.0 seconds).",f'Executed 1 test, with {len(messages)} failures (0 unexpected)']
        if failed:lines += ['Failing tests:']+['\t'+gate.CONSUMER+'()']*len(messages)
        lines += ['** TEST EXECUTE '+('FAILED' if failed else 'SUCCEEDED')+' **']
        row={'profile':p,'device_type':next(r[1] for r in gate.PROFILES if r[0]==p),'expected_scale':scale,'runtime':'com.apple.CoreSimulator.SimRuntime.iOS-27-0','udid':uid,'cleanup':[{'action':'shutdown','exit_code':0},{'action':'delete','exit_code':0}],'cleanup_passed':True,'actual_scales':[str(scale)],'actual_scale_verified':True,'test_exit_code':65 if failed else 0,'pixel_passed':not failed,'passed':not failed}
        if failed:row['error']=gate.STRICT_ERROR
        offset=100 if profile=='3x' else 0
        timing={'command':'xcodebuild','timed_out':False,'return_code':row['test_exit_code'],'started':f'2026-10-04T15:{2 if offset else 0:02}:00+00:00','finished':f'2026-10-04T15:{2 if offset else 0:02}:30+00:00','elapsed_seconds':30,'timeout_seconds':300}
        start=gate.datetime.fromisoformat(timing['started']).timestamp()
        counts={'passedTests':int(not failed),'failedTests':int(failed),'skippedTests':0,'expectedFailures':0}
        dev={'platform':'iOS Simulator','osVersion':'27.0','deviceId':uid,'modelName':row['device_type'],'deviceName':'Celluloid Early UIKit '+profile}
        summary={**counts,'totalTestCount':1,'result':'Failed' if failed else 'Passed','startTime':start+2,'finishTime':start+25,'runtimeWarnings':[],'devicesAndConfigurations':[{**counts,'device':dev}],'testFailures':[{'targetName':'CelluloidTests','testIdentifierString':gate.OWNER+'/'+gate.METHOD+'()','testName':gate.METHOD+'()','failureText':messages[0]}] if failed else []}
        return row,'\n'.join(lines)+'\n',summary,timing,fixture
    def test_known_pixel_failures_are_continuation_only_and_true_pass_stays_distinct(self):
        for p in ['2x','3x']:
            for failed in [True,False]:
                result=gate.inspect_profile(*self.profile(p,failed));self.assertIs(result['strict_pixel_passed'],not failed)
    def test_wrong_binding_cleanup_or_outcome_rejects(self):
        edits=[('device_type','wrong'),('runtime','old'),('udid','not-uuid'),('actual_scales',['3.0']),('actual_scale_verified',False),('test_exit_code',0),('test_exit_code',True),('pixel_passed',True),('passed',True),('error','process timeout'),('cleanup_passed',False),('cleanup',[{'action':'shutdown','exit_code':False},{'action':'delete','exit_code':0}]),('cleanup',[{'action':'shutdown','exit_code':0},{'action':'delete','exit_code':1}])]
        for key,value in edits:
            args=list(self.profile());args[0][key]=value
            with self.subTest(key=key,value=value),self.assertRaises((ValueError,StopIteration)):gate.inspect_profile(*args)
    def test_missing_duplicate_skipped_markers_or_extra_assertions_reject(self):
        changes=[lambda s:s.replace("' failed (", "' skipped ("),lambda s:s+s,
                 lambda s:s.replace('MAC_LAYER_UIKIT_COMPOSITOR_DISPLAY','MISSING_DISPLAY'),
                 lambda s:s.replace('name=sticker-artwork','name=filtered-base'),
                 lambda s:s.replace('name=filtered-base nativeSHA256=','name=filtered-base nativeSHA256=0'),
                 lambda s:s.replace('maximumChannelDifference=0','maximumChannelDifference=1',1),
                 lambda s:s.replace('with 3 failures','with 2 failures'),
                 lambda s:s.replace('(0 unexpected)','(1 unexpected)'),
                 lambda s:s+'error: unknown compiler failure\n',
                 lambda s:s+'permission denied\n',lambda s:s+'fatal error: crash\n',
                 lambda s:s+'MAC_HOST_FAIL_CLOSED_ABORT\n',
                 lambda s:s.replace('Independent UIKit component: bubble-artwork','Unknown component'),
                 lambda s:'MAC_LAYER_UIKIT_COMPOSITOR_DISPLAY scale=2.0\n'+s.replace('MAC_LAYER_UIKIT_COMPOSITOR_DISPLAY scale=2.0\n',''),
                 lambda s:s.replace('** TEST EXECUTE FAILED **','no terminal result')]
        for change in changes:
            args=list(self.profile());args[1]=change(args[1])
            with self.subTest(change=change),self.assertRaises(ValueError):gate.inspect_profile(*args)
    def test_structural_xctest_error_is_not_65_pixel_exception(self):
        args=list(self.profile());args[1]+=(f'/repo/{gate.TEST_SOURCE}:40: error: -[CelluloidTests.{gate.OWNER} {gate.METHOD}] : XCTAssertEqual failed: expected geometry\n')
        with self.assertRaises(ValueError):gate.inspect_profile(*args)
    def test_incomplete_wrong_device_or_unknown_summary_failures_reject(self):
        edits=[lambda s:s.update(totalTestCount=0),lambda s:s.update(skippedTests=1),lambda s:s.update(expectedFailures=1),lambda s:s.update(result='Passed'),lambda s:s.update(finishTime=s['startTime']),lambda s:s.update(testFailures=[]),lambda s:s.update(runtimeWarnings=['unexpected warning']),lambda s:s['testFailures'][0].update(failureText='XCTAssertEqual failed'),lambda s:s['devicesAndConfigurations'][0]['device'].update(deviceId='wrong'),lambda s:s['devicesAndConfigurations'][0]['device'].update(modelName='wrong'),lambda s:s['devicesAndConfigurations'][0].update(failedTests=0)]
        for edit in edits:
            args=list(self.profile());edit(args[2])
            with self.subTest(edit=edit),self.assertRaises(ValueError):gate.inspect_profile(*args)
    def test_process_timeout_or_unknown_failure_cannot_continue(self):
        for update in [{'timed_out':True},{'return_code':0},{'return_code':True},{'elapsed_seconds':400},{'finished':'2026-10-04T14:00:00+00:00'}]:
            args=list(self.profile());args[3].update(update)
            with self.subTest(update=update),self.assertRaises(ValueError):gate.inspect_profile(*args)
    def packet(self,temp):
        def write(name,value):p=temp/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value));return p
        fixture=self.fixture();mac=['MAC_LAYER_ADJUSTMENT_FIXTURE '+json.dumps(fixture)]
        h=hashlib.sha256(b'filter').hexdigest();b=base64.b64encode(b'filter').decode()
        mac.extend(f'MAC_FILTER_ONLY_FIXTURE filter={f} sha256={h} base64={b}' for f in FILTERS)
        mac.append('MAC_BAKED_BASE_FIXTURE '+json.dumps({'identifier':'Mango.CelluloidPhotoExtension','version':'2.0-baked-base','sha256':h,'base64':b}))
        for module,cases in required('mac').items():
            for case in cases:
                owner,method=case.split('.');mac.append(f"Test Case '-[{module}.{owner} {method}]' passed (0.1 seconds).")
        (temp/'mac.log').write_text('\n'.join(mac)+'\n');payload=gate.layer_from_log(temp/'mac.log',self.SOURCE);fixture=json.loads(payload)['fixture']
        directory=temp/'early-uikit-fixtures';directory.mkdir();(directory/LAYER_FILE).write_bytes(payload)
        write('early-uikit-fixtures/manifest.json',{'source_sha':self.SOURCE,'files':[{'name':LAYER_FILE,'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}]})
        app=temp/'celluloid-early-uikit/Build/Products/Debug-iphonesimulator/Celluloid.app';app.mkdir(parents=True);(app/'Celluloid').write_bytes(b'built binary')
        (app/'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'Mango.Celluloid','CFBundleExecutable':'Celluloid','DTPlatformName':'iphonesimulator'}))
        packet={'source_sha':self.SOURCE,'frozen_uikit_source':gate.FROZEN_UIKIT_SHA,'uikit_production_fingerprint':gate.FROZEN_UIKIT_FINGERPRINT,'same_built_app_verified':True,'cleanup_passed':True,'pixel_passed':False,'passed':False,'profiles':[]};summaries={}
        for p in ['2x','3x']:
            row,log,summary,timing,_=self.profile(p);name=f'early-uikit-{p}-interop.log';(temp/name).write_text(log);write(name+'.timing.json',timing)
            staging={'source_sha':self.SOURCE,'built_app':str(app),'installed_app':f"/Sim/Devices/{row['udid']}/data/Containers/Bundle/Application/UUID/Celluloid.app",'binary_sha256':gate.sha(app/'Celluloid'),'layer_archive_sha256':fixture['sha256'],'owned_fixture_sha256':hashlib.sha256(json.dumps(fixture).encode()).hexdigest()}
            write(f'early-uikit-{p}-staging.json',staging);row['staging']=staging;row['consumer']=required_verify('uikit',temp/name,directory,self.SOURCE);packet['profiles'].append(row);summaries[p]=summary
        write('early-uikit-interop.json',packet);return packet,summaries
    def exercise_packet(self,mutate=None,devices=None,source_mismatch=False,dirty=False,fingerprint=None):
        with tempfile.TemporaryDirectory() as folder:
            temp=Path(folder);packet,summaries=self.packet(temp)
            if mutate:mutate(temp,packet,summaries);(temp/'early-uikit-interop.json').write_text(json.dumps(packet))
            def command(args,**kwargs):
                args=list(map(str,args))
                value={'devices':devices or {}} if 'simctl' in args else summaries['2x' if '2x' in args[-1] else '3x']
                return subprocess.CompletedProcess(args,0,json.dumps(value),'')
            with patch.object(gate.subprocess,'check_output',side_effect=[('b'*40 if source_mismatch else self.SOURCE)+'\n','dirty' if dirty else '']),patch.object(gate,'frozen_uikit_fingerprint',return_value=fingerprint or gate.FROZEN_UIKIT_FINGERPRINT),patch.object(gate,'run',side_effect=command):return gate.verify(temp,self.SOURCE)
    def test_full_source_binary_fixture_result_and_cleanup_proof_continues_but_blocks_archive(self):
        report=self.exercise_packet();self.assertTrue(report['continuation_safe']);self.assertFalse(report['strict_pixel_passed']);self.assertFalse(report['final_archive_accepted'])
    def test_checkout_fingerprint_setup_or_live_device_blocks(self):
        for kwargs in [{'source_mismatch':True},{'dirty':True},{'fingerprint':'0'*64},{'devices':{'runtime':[{'udid':'12345678-1234-1234-1234-123456789AB0'}]}},{'mutate':lambda t,p,s:p.update(setup_error='timeout')}]:
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):self.exercise_packet(**kwargs)
    def test_staging_source_hash_binary_and_fixture_tampering_blocks(self):
        edits=[lambda t,p,s:p['profiles'].pop(),lambda t,p,s:p['profiles'][1].update(udid=p['profiles'][0]['udid']),lambda t,p,s:p['profiles'][0]['staging'].update(binary_sha256='0'*64),lambda t,p,s:p['profiles'][0]['staging'].update(owned_fixture_sha256='0'*64),lambda t,p,s:p['profiles'][0]['consumer'].update(log_sha256='0'*64),lambda t,p,s:(t/'celluloid-early-uikit/Build/Products/Debug-iphonesimulator/Celluloid.app/Celluloid').write_bytes(b'changed'),lambda t,p,s:(t/'early-uikit-fixtures/mac-layer-fixture.json').write_text('{}')]
        for mutate in edits:
            with self.subTest(mutate=mutate),self.assertRaises((ValueError,KeyError)):self.exercise_packet(mutate=mutate)
    def test_self_consistent_forged_staging_still_rejects_actual_binary_fixture_device(self):
        for field,value in [('binary_sha256','0'*64),('owned_fixture_sha256','0'*64),('source_sha','b'*40),('installed_app','/wrong/Celluloid.app'),('built_app','/wrong/Celluloid.app')]:
            def mutate(temp,packet,summaries):
                packet['profiles'][0]['staging'][field]=value
                (temp/'early-uikit-2x-staging.json').write_text(json.dumps(packet['profiles'][0]['staging']))
            with self.subTest(field=field),self.assertRaises(ValueError):self.exercise_packet(mutate=mutate)
    def test_duplicate_json_keys_and_oversized_receipts_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'proof.json';path.write_text('{"source":1,"source":2}')
            with self.assertRaises(ValueError):gate.read(path)
            path.write_text(' '*100)
            with self.assertRaises(ValueError):gate.read(path,99)
    def rewrite_log_and_receipt(self,temp,packet,index,change):
        row=packet['profiles'][index];path=temp/('early-uikit-'+row['profile']+'-interop.log')
        path.write_text(change(path.read_text()))
        row['consumer']=required_verify('uikit',path,temp/'early-uikit-fixtures',self.SOURCE)
    def test_adversarial_terminal_records_reject_end_to_end_even_with_recomputed_receipt(self):
        changes=[lambda s:s+'** TEST EXECUTE SUCCEEDED **\n',
                 lambda s:s+' ** TEST EXECUTE SUCCEEDED **\n',
                 lambda s:'** TEST EXECUTE FAILED **\n'+s.replace('** TEST EXECUTE FAILED **\n',''),
                 lambda s:s+'** TEST EXECUTE CANCELLED **\n',
                 lambda s:s+'** TEST EXECUTE FAILED **\n']
        for change in changes:
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'terminal'):
                self.exercise_packet(mutate=lambda t,p,s:self.rewrite_log_and_receipt(t,p,1,change))
        def passed_with_failure(temp,packet,summaries):
            for index,profile in enumerate(['2x','3x']):
                fresh,log,summary,timing,_=self.profile(profile,False)
                row=packet['profiles'][index];staging=row['staging'];row.clear();row.update(fresh,staging=staging)
                path=temp/('early-uikit-'+profile+'-interop.log');path.write_text(log+('** TEST EXECUTE FAILED **\n' if profile=='3x' else ''))
                (temp/(path.name+'.timing.json')).write_text(json.dumps(timing));summaries[profile]=summary
                row['consumer']=required_verify('uikit',path,temp/'early-uikit-fixtures',self.SOURCE)
            packet['pixel_passed']=packet['passed']=True
        with self.assertRaisesRegex(ValueError,'terminal'):self.exercise_packet(mutate=passed_with_failure)
    def test_canonical_suites_and_entire_failing_blocks_reject_unknown_entries(self):
        changes=[lambda s:s+" Test Suite 'Selected tests' passed at 2026-10-04 15:00:00.000.\n",
                 lambda s:s+" test suite 'Selected tests' passed at 2026-10-04 15:00:00.000.\n",
                 lambda s:s+'Failing tests:\n\tUnexpectedStructuralTests.testWrongGeometry()\n',
                 lambda s:s.replace(gate.CONSUMER+'()','UnexpectedStructuralTests.testWrongGeometry()',1),
                 lambda s:s.replace('Failing tests:','Failing tests:\nFailing tests:'),
                 lambda s:s.replace('Failing tests:','Missing header:'),
                 lambda s:s.replace('** TEST EXECUTE FAILED **','\t'+gate.CONSUMER+'()\n** TEST EXECUTE FAILED **')]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ValueError):self.exercise_packet(mutate=lambda t,p,s:self.rewrite_log_and_receipt(t,p,1,change))
    def test_adversarial_timing_types_and_durations_reject_end_to_end(self):
        changes=[{'finished':'2026-10-04T16:02:30+00:00'}, {'timeout_seconds':float('inf')},
                 {'timeout_seconds':float('nan')}, {'elapsed_seconds':True}, {'timeout_seconds':True},
                 {'elapsed_seconds':float('inf')}, {'elapsed_seconds':float('nan')},
                 {'timeout_seconds':301}, {'elapsed_seconds':29-0.01}, {'started':'2026-10-04T15:02:00'}]
        for update in changes:
            def mutate(temp,packet,summaries):
                path=temp/'early-uikit-3x-interop.log.timing.json';r=json.loads(path.read_text());r.update(update);path.write_text(json.dumps(r))
            with self.subTest(update=update),self.assertRaises(ValueError):self.exercise_packet(mutate=mutate)
    def test_adversarial_malformed_duplicate_proofs_and_assertions_reject_end_to_end(self):
        changes=[lambda s:s.replace('MAC_LAYER_UIKIT_COMPOSITOR_DISPLAY scale=3.0','MAC_LAYER_UIKIT_COMPOSITOR_DISPLAY scale=3.0\nMAC_LAYER_UIKIT_COMPOSITOR_DISPLAY scale=garbage'),
                 lambda s:s.replace('MAC_LAYER_UIKIT_COMPOSITOR_DISPLAY scale=3.0','MAC_LAYER_UIKIT_COMPOSITOR_DISPLAY scale=3.0\nMAC_LAYER_UIKIT_COMPOSITOR_DISPLAY scale=NaN'),
                 lambda s:s.replace('MAC_LAYER_UIKIT_COMPOSITOR_DISPLAY scale=3.0','MAC_LAYER_UIKIT_COMPOSITOR_DISPLAY scale=3.0\nMAC_LAYER_UIKIT_COMPOSITOR_DISPLAY malformed'),
                 lambda s:s+' MAC_LAYER_UIKIT_COMPOSITOR_DISPLAY scale=invalid\n',
                 lambda s:s+'Assertion Failure: required structural condition was false\n',
                 lambda s:s+'XCTFail: missing structural condition\n',
                 lambda s:s+'AssertionFailure: invalid geometry\n',
                 lambda s:s+'Exception Type: EXC_BAD_ACCESS (SIGSEGV)\n',
                 lambda s:s+'2026-10-04 15:00:41.000000+0000 Celluloid[1:2] fopen failed for another file: errno = 2 (No such file or directory)\n',
                 lambda s:s+'Unclassified process failure\n',
                 lambda s:s+'Error Domain=Unclassified Code=2\n',
                 lambda s:s+"Test Suite 'Selected tests' passed at 2026-10-04 15:00:00.000.\n",
                 lambda s:s.replace('maximumChannelDifference=202','maximumChannelDifference=202 trailing garbage'),
                 lambda s:s.replace('MAC_LAYER_UIKIT_COMPOSITOR_DISPLAY scale=3.0','MAC_LAYER_UIKIT_COMPOSITOR_DISPLAY scale=3.0\nMAC_LAYER_UIKIT_COMPOSITOR_UNKNOWN bypass')]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ValueError):self.exercise_packet(mutate=lambda t,p,s:self.rewrite_log_and_receipt(t,p,1,change))
    def test_exact_unclassified_fopen_can_schedule_but_never_accept_or_excuse_failures(self):
        diagnostic='2026-10-04 15:00:41.000000+0000 Celluloid[1:2] fopen failed for data file: errno = 2 (No such file or directory)'
        def mutate(temp,packet,summaries):
            self.rewrite_log_and_receipt(temp,packet,1,lambda log:log+diagnostic+'\n')
        report=self.exercise_packet(mutate=mutate)
        self.assertTrue(report['continuation_safe']);self.assertFalse(report['strict_pixel_passed']);self.assertFalse(report['final_archive_accepted'])
        row=report['profiles'][1];self.assertEqual(row['unclassified_console_diagnostics'],[diagnostic]);self.assertEqual(row['unclassified_console_count'],1);self.assertFalse(row['console_diagnostics_classified'])
        for extra in ['Assertion Failure: invalid geometry','Exception Type: EXC_BAD_ACCESS (SIGSEGV)']:
            def failure(temp,packet,summaries):
                self.rewrite_log_and_receipt(temp,packet,1,lambda log:log+diagnostic+'\n'+extra+'\n')
            with self.subTest(extra=extra),self.assertRaises(ValueError):self.exercise_packet(mutate=failure)
        def bad_cleanup(temp,packet,summaries):
            mutate(temp,packet,summaries);packet['profiles'][1]['cleanup'][0]['exit_code']=1
        with self.assertRaises(ValueError):self.exercise_packet(mutate=bad_cleanup)
    def test_false_result_is_written_on_verifier_failure(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,RUNNER_TEMP=folder,GITHUB_SHA=self.SOURCE),patch.object(gate.sys,'argv',['gate','--github-output',folder+'/output']),patch.object(gate,'verify',side_effect=ValueError('unexpected process failure')),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit):gate.main()
            result=json.loads((Path(folder)/'interop-continuation.json').read_text());self.assertFalse(result['continuation_safe']);self.assertFalse(result['final_archive_accepted']);self.assertEqual((Path(folder)/'output').read_text(),'continuation_safe=false\n')

if __name__=='__main__':unittest.main()
