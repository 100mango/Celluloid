"""Synthetic lifecycle/terminal regressions; no Apple command or Photos claim."""
import base64,copy,json,unittest
from pathlib import Path
from unittest.mock import patch
import mac_photos_lifecycle_observation as observe
import mac_host_lifecycle as gate
import mac_host_lifecycle_pixels as pixels
import mac_host_transport as transport
from test_mac_host_lifecycle import fixture
from test_mac_host_lifecycle_pixels import encode
from test_mac_host_self_identity import receipt
from validation_route import LIFECYCLE,FULL,BOUNDARY,host_clock_profile

ROOT=Path(__file__).resolve().parents[1]

def packet(failed=False):
    args=list(copy.deepcopy(fixture()));row,context,photos,ownership,baseline,images,_=args
    context.update(validation_route=dict(LIFECYCLE),host_clock_profile=host_clock_profile(LIFECYCLE),host_entry_contract=transport.HOST_CONTRACT,
        owned_saved_pixel_observation=observe.MODE,seed={'mode':'require-empty-library'},app_path='/owned/CelluloidMac.app',
        app_executable='/owned/CelluloidMac.app/Contents/MacOS/CelluloidMac',app_executable_sha256='d'*64)
    context['runner_environment']={'RUNNER_TEMP':'/owned/runner','GITHUB_RUN_ID':'123456','GITHUB_RUN_ATTEMPT':'1',
        'GITHUB_SHA':'a'*40,'GITHUB_WORKFLOW_SHA':'a'*40,'GITHUB_REF':'refs/heads/'+LIFECYCLE['branch'],
        'GITHUB_REPOSITORY':'100mango/Celluloid','GITHUB_EVENT_NAME':'push','CELLULOID_VALIDATION_SCOPE':LIFECYCLE['scope'],
        'GITHUB_WORKFLOW_REF':'100mango/Celluloid/'+LIFECYCLE['workflow_path']+'@refs/heads/'+LIFECYCLE['branch']}
    images[pixels.NAMES[0]]=(ROOT/'Platforms/MacExtensionTests/Fixtures/lifecycle-source.png').read_bytes();images[pixels.NAMES[4]]=images[pixels.NAMES[0]]
    ownership.update(fixture_sha256=observe.FIXTURE,source_sha=context['source_sha'],app_executable_sha256=context['app_executable_sha256'],
        mode='require-empty-library',initial_count=0,selected_count=1,width=1200,height=800)
    photos.update(bundle='/System/Applications/Photos.app',executable='/System/Applications/Photos.app/Contents/MacOS/Photos')
    if failed:
        rgb=bytearray([150,90,60,255]*1200*800);rgb[2]+=3
        images[pixels.NAMES[2]]=encode(width=1200,height=800,pixels=bytes(rgb));images[pixels.NAMES[3]]=images[pixels.NAMES[2]]
    raw_context=json.dumps(context,sort_keys=True).encode();context_hash=observe.sha(raw_context);args[-1]=context_hash
    row.update(context_sha256=context_hash,fixture_sha256=observe.FIXTURE,complete=not failed,functional_observation_complete=True,deadline_seconds=900)
    row['phases'][0]['details']['fixture_sha256']=observe.FIXTURE;row['phases'][2]['details']['max_channel_delta']=3 if failed else 0
    for name,data in images.items():
        decoded=pixels.decode(data);row['images'][name].update(bytes=len(data),sha256=observe.sha(data),rgba_sha256=decoded['rgba_sha256'],color_type=decoded['color_type'])
    for phase,name in [('saved',pixels.NAMES[2]),('cancelled',pixels.NAMES[3]),('reverted',pixels.NAMES[4]),('original',pixels.NAMES[0])]:
        row['raw_exports'][phase].update(bytes=len(images[name]),sha256=observe.sha(images[name]))
    return args

def transcript(failed=False,mutate=None):
    args=packet(failed);row,context,photos,ownership,baseline,images,context_hash=args
    common=dict(host_entry_contract=transport.HOST_CONTRACT,source_sha=context['source_sha'],photos_pid=photos['pid'],photos_bundle=photos['bundle'],
        photos_executable=photos['executable'],fixture_sha256=observe.FIXTURE,asset_label=ownership['asset_label'])
    selection=dict(common,schema='Celluloid.HostSelection.3',menu_title='Celluloid',menu_identifier='editWithPlugin:',
        menu_scope='Extensions.menuButton/childMenu/directMenuItem',extension_menu_button_count=1,opened_menu_count=1,menu_count=1,
        menu_enabled=True,menu_hittable=True,editor_count_before=0)
    editor=dict(common,schema='Celluloid.HostEditor.2',editor_label='Celluloid photo editor',editor_count=1,preview_label='Edited photo preview',
        preview_count=1,placeholder_count=0,preparing_count=0,filter_identifier='photos-extension.filter',filter_count=1,filter_enabled=True,read_only_count=0,error_count=0)
    outcome=dict(source_sha=context['source_sha'],host_entry_contract=transport.HOST_CONTRACT,complete_host_e2e=False,
        functional_observation_complete=True,last_stage=observe.OBSERVED if failed else 'photos-filter-lifecycle-passed',
        save_reopen_cancel_revert='PhotosFilterLifecycle.1 '+('incomplete' if failed else 'complete'))
    if failed:outcome['first_blocked_operation']={'stage':observe.OBSERVED,'reason':observe.PIXEL_REASON,'operation':{'max_channel_delta':3,'deferred_from':'lifecycle-save-and-export'}}
    values={'transport.json':transport.expected_transport(context,context_hash),'containing-process.json':{'bundle':context['app_path'],'executable':context['app_executable'],'pid':123},
        'photos-process.json':photos,'fixture.json':{'source_sha':context['source_sha'],'sha256':observe.FIXTURE},'fixture-ownership.json':ownership,
        'host-selection.json':selection,'host-editor-before-process.json':dict(editor,phase='before-process'),'host-editor-after-process.json':dict(editor,phase='after-process'),
        'extension-self-identity.json':receipt(context,photos,ownership),'prerequisite.json':{'source_sha':context['source_sha'],'host_entry_contract':transport.HOST_CONTRACT,'prerequisite_passed':True,'complete_host_e2e':False},
        'lifecycle.json':row,'outcome.json':outcome}
    if mutate:mutate(values)
    owner,method=transport.CASE;case='-['+owner+' '+method+']'
    command=['xcodebuild','-maximum-test-execution-time-allowance','960','-only-testing:'+owner.replace('.','/')+'/'+method,'test-without-building']
    lines=['BOUNDED_COMMAND_BEGIN '+json.dumps({'label':transport.LABEL,'seconds':1020,'utc':'2026-10-06T00:00:00+00:00','command':command}),"Test Case '"+case+"' started.",
        'MAC_HOST_PREREQUISITE_PASSED synthetic fixture',observe.MARKER]
    for index,name in enumerate(transport.ORDER):
        data=json.dumps(values[name],sort_keys=True).encode()
        lines.append(transport.PREFIX+json.dumps(dict(schema=transport.SCHEMA,sequence=index,name=name,bytes=len(data),sha256=observe.sha(data),
            base64=base64.b64encode(data).decode(),source_sha=context['source_sha'],context_sha256=context_hash,test_source_sha256=context['test_source_sha256'],verifier_sha256=context['script_sha256'])))
    if failed:lines+=['MAC_HOST_BLOCKED stage='+observe.OBSERVED+' reason='+observe.PIXEL_REASON,'/owned/MacPhotosHostUITests.swift:1: error: '+case+' : '+observe.PIXEL_FAILURE_TEXT]
    else:lines+=['MAC_HOST_FILTER_LIFECYCLE_PASSED synthetic fixture']
    lines+=["Test Case '"+case+"' "+('failed' if failed else 'passed')+' (1.0 seconds).',
        'Executed 1 test, with '+str(int(failed))+' failure (0 unexpected) in 1.0 (1.0) seconds',
        'Test session results, code coverage, and logs:',' /owned/runner/MacPhotosHost.xcresult']
    if failed:lines+=['Failing tests:',' MacPhotosHostUITests.'+method+'()']
    lines+=['** TEST EXECUTE '+('FAILED' if failed else 'SUCCEEDED')+' **',
        'BOUNDED_COMMAND_END '+json.dumps({'label':transport.LABEL,'exit_code':65 if failed else 0,'elapsed_seconds':1})]
    summary=dict(result='Failed' if failed else 'Passed',totalTestCount=1,passedTests=int(not failed),failedTests=int(failed),skippedTests=0,expectedFailures=0,startTime=1791244800.1,finishTime=1791244800.9,
        testFailures=[dict(targetName='CelluloidMacUITests',testIdentifierString='MacPhotosHostUITests/'+method+'()',failureText=observe.PIXEL_FAILURE_TEXT)] if failed else [])
    summary['devicesAndConfigurations']=[dict({k:summary[k] for k in ['passedTests','failedTests','skippedTests','expectedFailures']},device={'platform':'macOS','osVersion':'27.0','osBuildNumber':'26A428','architecture':'arm64'})]
    return json.dumps(context,sort_keys=True).encode(),'\n'.join(lines)+'\n',summary,images,args

class LifecycleObservationTests(unittest.TestCase):
    def test_success_qualifies_functional_component_and_keeps_limited_claim(self):
        context,log,summary,images,args=transcript()
        result=observe.admit_images(context,log,summary,images)
        self.assertTrue(result['functional_lifecycle_qualified']);self.assertTrue(result['strict_saved_pixel_passed']);self.assertFalse(result['complete_host_e2e'])
    def test_known_pixel_failure_keeps_failed_strict_result_after_full_functional_proof(self):
        context,log,summary,images,args=transcript(True)
        # The pixel arrays here are synthetic. Patch only the two known-image
        # addresses to exercise the same exact-address branch, never the <=2 limit.
        with patch.object(gate,'KNOWN_SAVED_RGBA',args[0]['images'][pixels.NAMES[2]]['rgba_sha256']),patch.object(gate,'KNOWN_REFERENCE_RGBA',args[0]['images'][pixels.NAMES[1]]['rgba_sha256']):
            result=observe.admit_images(context,log,summary,images)
        self.assertTrue(result['functional_lifecycle_qualified']);self.assertFalse(result['filter_lifecycle_accepted']);self.assertFalse(result['strict_saved_pixel_passed']);self.assertEqual(result['strict_saved_pixel_limit'],2)
        self.assertEqual(summary['result'],'Failed')
    def test_switch_is_default_closed_and_unknown_difference_is_never_deferred(self):
        args=packet(True)
        with self.assertRaises(ValueError):gate.validate(*args)
        with self.assertRaisesRegex(ValueError,'Unobserved saved pixel discrepancy'):gate.validate(*args,observe_saved_pixel_difference=True)
        for key,val in [('validation_route',BOUNDARY),('owned_saved_pixel_observation','other'),('boundary_probe',{})]:
            bad=copy.deepcopy(args);bad[1][key]=val
            with self.assertRaises(ValueError):gate.validate(*bad,observe_saved_pixel_difference=True)
    def test_new_functional_failure_missing_phase_or_permission_outcome_never_exports(self):
        mutations=[lambda v:v['outcome.json'].update(functional_observation_complete=False),lambda v:v['outcome.json'].pop('last_stage'),
            lambda v:v['outcome.json']['first_blocked_operation'].update(reason='Unadmitted Photos confirmation or access alert; no action taken'),
            lambda v:v['lifecycle.json']['phases'].pop(),lambda v:v['lifecycle.json']['phases'].reverse(),
            lambda v:v['host-editor-after-process.json'].update(error_count=1),lambda v:v['fixture-ownership.json'].update(selected_count=2)]
        for change in mutations:
            c,l,s,_,_=transcript(True,change)
            with self.subTest(change=change),self.assertRaises((ValueError,KeyError)):observe.admit_outcome(c,l,s)
    def test_identity_cancel_revert_original_and_deadline_relations_stay_strict(self):
        mutations=[lambda a:a[0]['phases'][3]['details'].update(filter='Original'),
            lambda a:a[0]['phases'][6]['details'].update(bytes_equal_source=False),
            lambda a:a[0]['phases'][7].update(elapsed_ms=900000),
            lambda a:a[0]['phases'][4]['details'].update(new_edit_made=True),
            lambda a:a[5].update({'lifecycle-cancelled.png':a[5]['lifecycle-source.png']}),
            lambda a:a[5].update({'lifecycle-reverted.png':a[5]['lifecycle-saved.png']})]
        for change in mutations:
            args=packet();change(args)
            with self.subTest(change=change),self.assertRaises(ValueError):gate.validate(*args,observe_saved_pixel_difference=True)
    def test_extra_case_error_wrong_result_path_and_native_terminal_reject(self):
        c,l,s,_,_=transcript(True)
        for text,summary in [(l.replace('** TEST EXECUTE FAILED **','** TEST EXECUTE SUCCEEDED **'),s),
            (l.replace('/owned/runner/MacPhotosHost.xcresult','/wrong.xcresult'),s),
            (l,s|{'totalTestCount':0}),(l,s|{'finishTime':s['finishTime']+10}),
            (l.replace(observe.MARKER,observe.MARKER+'\n/owned/test.swift:1: error: unexpected true failure'),s),
            (l.replace('MacPhotosHostUITests','OtherTests'),s)]:
            with self.subTest(text=text[-120:]),self.assertRaises(ValueError):observe.admit_outcome(c,text,summary)
    def test_original_cap_reserves_declared_five_images_manifest_and_finish(self):
        row=packet()[0];need=sum(v['bytes'] for v in row['images'].values())+128000+4096+32000
        self.assertEqual(observe.attachment_capacity({'prior':{'bytes':1000000-need}},row)['cap_bytes'],1000000)
        with self.assertRaises(ValueError):observe.attachment_capacity({'prior':{'bytes':1000001-need}},row)
    def test_swift_has_one_default_off_exception_and_preserves_real_functional_guards(self):
        source=(ROOT/'Platforms/UITests/MacPhotosHostUITests.swift').read_text()
        self.assertIn('private var observeSavedPixelDifference = false',source)
        self.assertIn('guard savedDelta <= 2',source);self.assertIn('guard savedDelta == 3',source)
        self.assertLess(source.index('try lifecyclePhase("reopened-original"'),source.index('functionalObservationComplete = true'))
        self.assertLess(source.index('functionalObservationComplete = true'),source.index('if let deferredSavedPixelDelta'))
        for required in ['guard cancelled.rgba == saved.rgba','guard reverted.rgba == source.rgba','guard original.bytes == source.bytes',
            'previousGenerations: [initialGeneration, reopened.generation]','try requireNoSheet(photos)']:
            self.assertIn(required,source)
        self.assertEqual((ROOT/'Platforms/macOSExtension/MacPhotoSelfIdentity.swift').read_text().count('class MacPhotoSelfIdentity:'),1)

if __name__=='__main__':unittest.main()
