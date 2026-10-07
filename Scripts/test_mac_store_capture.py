"""Portable source, failure and retention contracts. Native capture remains unrun."""
import copy
import hashlib
import json
import os
import plistlib
import socket
import sys
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

import mac_store_capture as m
import mac_store_contract as contract
import mac_store_product as product_contract
from test_mac_store_png import png
from test_mac_store_display import display_records

CHECKOUT=Path(__file__).resolve().parents[1]
SHA='a'*40;TREE='b'*40;TOKEN='AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE'


class Clock:
    def __init__(self):self.value=100.
    def __call__(self):return self.value
    def advance(self,value):self.value+=value


def env():
    return {'GITHUB_REPOSITORY':'100mango/Celluloid','GITHUB_REF':m.BRANCH,
        'GITHUB_WORKFLOW_REF':'100mango/Celluloid/'+m.WORKFLOW+'@'+m.BRANCH,
        'GITHUB_RUN_ATTEMPT':'1','GITHUB_JOB':'capture','GITHUB_EVENT_NAME':'push',
        'GITHUB_SHA':SHA,'GITHUB_WORKFLOW_SHA':SHA,'GITHUB_RUN_ID':'123',
        'DEVELOPER_DIR':'/Applications/Xcode_27.app/Contents/Developer'}


def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()


def exported(start,product,failed=False,scale=1):
    counts={'passedTests':0 if failed else 1,'failedTests':1 if failed else 0,'skippedTests':0,'expectedFailures':0}
    identity='NativeEditorUITests/'+m.CASE+'()'
    url='test://com.apple.xcode/CelluloidNative/CelluloidMacUITests/NativeEditorUITests/'+m.CASE
    summary={**counts,'totalTestCount':1,'result':'Failed' if failed else 'Passed','startTime':start+.1,'finishTime':start+1.8,
        'devicesAndConfigurations':[{**counts,'device':{'deviceId':'owned-Mac','platform':'macOS','architecture':'arm64','osVersion':'27.0'},
            'testPlanConfiguration':{'configurationName':'Test Scheme Action'}}],
        'testFailures':[{'testIdentifierString':identity,'testIdentifierURL':url}] if failed else []}
    items=[];files={}
    setup_raw,restore_raw=display_records(start,scale)
    display_digest=contract.digest(setup_raw)
    for index,(state,visible) in enumerate(contract.STATES.items()):
        raw=png(1280*scale,800*scale,color=(35+index,90,170));captured=start+.4+index*.6
        row={'v':1,'state':state,'token':TOKEN,'pid':456,'test':'-[CelluloidMacUITests.NativeEditorUITests '+m.CASE+']',
            'started':start+.2,'captured':captured,'sequential':True,'args':contract.ARGS,'sandbox':False,
            'bundle':'Mango.Celluloid',**product,'expectedPath':product['applicationPath'],
            'imageName':'Native Mac Store window '+state,'pngSHA256':contract.digest(raw),'pngBytes':len(raw),
            'width':1280*scale,'height':800*scale,'windowFrame':[0.,40.,1280.,800.],
            'backingScale':scale,'visibleFrameAX':[0,31,1280,869],'displaySetupSHA256':display_digest,
            **visible}
        for offset,(kind,ext,data) in enumerate([('window','png',raw),('proof','txt',encoded(row))]):
            uid='00000000-0000-4000-8000-'+str(index*2+offset+1).zfill(12);filename=uid+'.'+ext;files[filename]=data
            items.append({'configurationName':'Test Scheme Action','deviceId':'owned-Mac','deviceName':'My Mac',
                'exportedFileName':filename,'isAssociatedWithFailure':False,
                'suggestedHumanReadableName':'Native Mac Store '+kind+' '+state+'_0_'+uid+'.'+ext,'timestamp':captured+.01+offset*.01})
    for index,(suffix,raw) in enumerate([('setup',setup_raw),('restore',restore_raw)]):
        uid='00000000-0000-4000-8000-'+str(index+5).zfill(12);filename=uid+'.txt';files[filename]=raw
        items.append({'configurationName':'Test Scheme Action','deviceId':'owned-Mac','deviceName':'My Mac',
            'exportedFileName':filename,'isAssociatedWithFailure':False,
            'suggestedHumanReadableName':'Native Mac Store display '+suffix+'_0_'+uid+'.txt',
            'timestamp':start+(.19 if suffix=='setup' else 1.61)})
    files['manifest.json']=encoded([{'testIdentifier':identity,'testIdentifierURL':url,'attachments':items}])
    return summary,files


def release_projection(text):
    active=[True];out=[]
    for line in text.splitlines(keepends=True):
        directive=line.strip()
        if directive=='#if DEBUG':active.append(False)
        elif directive=='#else':active[-1]=active[-2] and not active[-1]
        elif directive=='#endif':active.pop()
        elif directive.startswith('#if '):raise ValueError('unknown conditional')
        elif active[-1]:out.append(line)
    if len(active)!=1:raise ValueError('unbalanced DEBUG')
    return ''.join(out)


class PortableTests(unittest.TestCase):
    def setUp(self):
        # Every OS/tool operation in these regressions is a local fake. An
        # accidental subprocess or network fallback must fail before it starts.
        for target in ('subprocess.Popen','os.system','socket.create_connection','socket.socket.connect'):
            guard = patch(target, side_effect=AssertionError('native/network operation forbidden in portable tests'))
            guard.start();self.addCleanup(guard.stop)


class SourceTests(PortableTests):
    def test_fixed_product_and_ordinary_unsigned_route(self):
        command=m.base_command()
        self.assertEqual(command[command.index('-project')+1],'CelluloidNative.xcodeproj')
        self.assertEqual(command[command.index('-scheme')+1],'CelluloidMacUI')
        self.assertEqual(command[command.index('-configuration')+1],'Debug')
        self.assertIn('CODE_SIGNING_ALLOWED=NO',command)
        for forbidden in ('-quiet','CODE_SIGNING_ALLOWED=YES','CODE_SIGN_IDENTITY=-','ENABLE_APP_SANDBOX=NO'):
            self.assertNotIn(forbidden,command)
        scheme=ET.parse(CHECKOUT/'CelluloidNative.xcodeproj/xcshareddata/xcschemes/CelluloidMacUI.xcscheme').getroot()
        self.assertEqual([x.find('BuildableReference').get('BlueprintName') for x in scheme.find('TestAction/Testables')],['CelluloidMacUITests'])
        variables={x.get('key'):x.get('value') for x in scheme.find('TestAction/EnvironmentVariables')}
        self.assertEqual(variables['CELLULOID_EXPECTED_APP_PATH'],'$(BUILT_PRODUCTS_DIR)/CelluloidMac.app')
    def test_exact_reviewed_parent_and_two_modified_sources(self):
        self.assertEqual(m.PARENT,'9058bc3b276e67a5bf457aa5b470fbf51a211849')
        self.assertEqual(m.PARENT_TREE,'1080a185944a5af59ef8b6fb8172ce2c98a719c9')
        self.assertEqual(m.MODIFIED_PATHS,('Platforms/macOS/NativeWindowAccessibility.swift','Platforms/UITests/NativeEditorUITests.swift'))
        self.assertEqual(m.EXPECTED_DIFF,sorted(['A\t'+x for x in m.SUCCESSOR_NEW_PATHS]+['M\t'+x for x in m.SUCCESSOR_MODIFIED_PATHS]))
    def test_frozen_current_application_and_support_inputs(self):
        f=json.loads((CHECKOUT/'Scripts/fixtures/mac-store-source-baseline.json').read_bytes())
        self.assertEqual((f['parent'],f['parent_tree']),(m.BASE,m.BASE_TREE))
        for path,value in {**f['current_app_inputs'],**f['current_support_inputs']}.items():
            self.assertEqual(hashlib.sha256((CHECKOUT/path).read_bytes()).hexdigest(),value,path)
    def test_existing_original_imports_bound_to_both_digests(self):
        for state,row in contract.STATES.items():
            raw=(CHECKOUT/'StoreCaptureAssets'/row['sourceFilename']).read_bytes()
            self.assertEqual((len(raw),hashlib.sha256(raw).hexdigest()),(row['sourceBytes'],row['sourceSHA256']))
            self.assertEqual(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(),contract.SOURCE_BLOBS[state])
        self.assertEqual(list(contract.STATES),['citrus','coast'])
    def test_single_build_test_and_fixed_push_workflow(self):
        argv=m.test_command();self.assertEqual(argv[-1],'test-without-building')
        self.assertEqual([x for x in argv if x.startswith('-only-testing:')],['-only-testing:CelluloidMacUITests/NativeEditorUITests/'+m.CASE])
        self.assertNotIn('-test-iterations',argv);self.assertIn('120',argv)
        text=(CHECKOUT/m.WORKFLOW).read_text();self.assertIn('timeout-minutes: 25',text)
        self.assertEqual(text.count('runs-on: xcode-27'),1)
        for bad in ['matrix:','workflow_dispatch','retry','continue-on-error','*.xcarchive','allowProvisioning']:
            self.assertNotIn(bad,text)
        self.assertIn('path: build/mac-store-proof/',text)
    def test_fixed_environment_excludes_retries_dispatch_other_branches_and_sandbox(self):
        self.assertEqual(m.environment(env()),env())
        for key,value in [('GITHUB_RUN_ATTEMPT','2'),('GITHUB_EVENT_NAME','workflow_dispatch'),
                ('GITHUB_REF','refs/heads/main'),('CELLULOID_EXPECT_SANDBOX','YES')]:
            with self.subTest(key=key),self.assertRaises(m.Rejected):m.environment(env()|{key:value})
    def test_cohort_and_packet_caps(self):
        self.assertEqual(m.PHASE_END['finalization']+60,1310)
        self.assertEqual(contract.MAX_PACKET,14*1024*1024);self.assertEqual(m.MAX_REPORT,2*1024*1024)


class SourceGateTests(PortableTests):
    def test_source_identity_rejects_dirty_foreign_parent_or_unbounded_change(self):
        values={('rev-parse','HEAD'):SHA,('rev-parse',m.PARENT+'^{tree}'):m.PARENT_TREE,
            ('rev-list','--parents','-n','1','HEAD'):SHA+' '+m.PARENT,
            ('status','--porcelain','--untracked-files=all'):'',
            ('diff','--name-status',m.PARENT,'HEAD','--'):'\n'.join(m.EXPECTED_DIFF),
            ('rev-parse','HEAD^{tree}'):TREE}
        changes=[(('rev-parse','HEAD'),'f'*40), (('rev-parse',m.PARENT+'^{tree}'),'f'*40),
            (('rev-list','--parents','-n','1','HEAD'),SHA+' '+m.PARENT+' '+'f'*40),
            (('status','--porcelain','--untracked-files=all'),'?? unreviewed.png'),
            (('diff','--name-status',m.PARENT,'HEAD','--'),'\n'.join(m.EXPECTED_DIFF+['M\tPlatforms/Shared/NativeEditorView.swift']))]
        for key,value in changes:
            changed=values|{key:value}
            def run(argv,**kwargs):return (changed[tuple(argv[1:])]+'\n').encode()
            with self.subTest(key=key),self.assertRaises(m.Rejected):m.source_identity(env(),run,CHECKOUT)
    def test_command_reserves_both_cleanup_phases_before_spawn(self):
        called=[];receipts=[]
        def runner(*a,**kw):called.append(kw);raise AssertionError('should not spawn')
        with self.assertRaisesRegex(m.Rejected,'cleanup-admission'):
            m.command(['unreachable'],deadline=120,seconds=100,cleanup=10,cap=256,
                receipts=receipts,clock=lambda:100,runner=runner)
        self.assertEqual(called,[]);self.assertEqual(receipts,[])
    def test_unknown_cleanup_and_cancellation_never_become_success(self):
        clock=Clock();receipts=[]
        def runner(*a,**kw):
            clock.advance(1);error=m.CaptureStopped('synthetic cancellation',False,15)
            error.stdout_prefix=b'bounded prefix';raise error
        with self.assertRaisesRegex(m.Rejected,'capture-stopped'):
            m.command(['unreachable'],deadline=120,seconds=10,cap=256,receipts=receipts,clock=clock,runner=runner)
        self.assertFalse(receipts[0]['complete']);self.assertFalse(receipts[0]['owned_cleanup_confirmed'])
        self.assertEqual(receipts[0]['cancelled_signal'],15);self.assertEqual(receipts[0]['stdout'],'bounded prefix')


class ProductTests(PortableTests):
    def setUp(self):
        super().setUp()
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.old=Path.cwd();os.chdir(self.root);self.addCleanup(os.chdir,self.old)
        self.app=self.root/'build/mac-tests/Build/Products/Debug/CelluloidMac.app'
        (self.app/'Contents/MacOS').mkdir(parents=True)
        self.metadata={'CFBundleIdentifier':'Mango.Celluloid','CFBundleExecutable':'CelluloidMac'}
        self.write_metadata()
        (self.app/'Contents/MacOS/CelluloidMac').write_bytes(b'fake Mac launcher')
        (self.app/'Contents/MacOS/CelluloidMac.debug.dylib').write_bytes(b'fake Mac logic')
    def write_metadata(self):
        (self.app/'Contents/Info.plist').write_bytes(plistlib.dumps(self.metadata))
    def test_fixed_mac_product_hashes_launcher_and_debug_logic(self):
        row=product_contract.product_identity()
        self.assertEqual(row,{'applicationPath':str(self.app),'executable':str(self.app/'Contents/MacOS/CelluloidMac'),
            'executableSHA256':contract.digest(b'fake Mac launcher'),'logicSHA256':contract.digest(b'fake Mac logic')})
    def test_same_bundle_ios_and_tv_executables_are_rejected(self):
        for executable in ('Celluloid','CelluloidTV'):
            self.metadata['CFBundleExecutable']=executable;self.write_metadata()
            (self.app/'Contents/MacOS'/executable).write_bytes(b'same bundle, wrong platform executable')
            with self.subTest(executable=executable),self.assertRaisesRegex(ValueError,'wrong-product'):
                product_contract.product_identity()
    def test_missing_debug_logic_and_linked_products_are_rejected(self):
        logic=self.app/'Contents/MacOS/CelluloidMac.debug.dylib';logic.unlink()
        with self.assertRaises(FileNotFoundError):product_contract.product_identity()
        foreign=self.root/'foreign.dylib';foreign.write_bytes(b'foreign');logic.symlink_to(foreign)
        with self.assertRaisesRegex(ValueError,'linked-product'):product_contract.product_identity()


class ProductAliasTests(ProductTests):
    """Run actual product-binding assertions with a macOS-like temp-name alias."""
    def setUp(self):
        outer=tempfile.TemporaryDirectory();self.addCleanup(outer.cleanup)
        parent=Path(outer.name).resolve();alias=parent/'temporary-root-alias'
        alias.symlink_to(parent,target_is_directory=True)
        factory=tempfile.TemporaryDirectory
        with patch.object(tempfile,'TemporaryDirectory',side_effect=lambda:factory(dir=alias)):
            super().setUp()
        self.assertNotEqual(Path(self.temp.name),Path(self.temp.name).resolve())


class ReceiptTests(PortableTests):
    def setUp(self):
        super().setUp()
        app=Path('/virtual/build/mac-tests/Build/Products/Debug/CelluloidMac.app')
        self.product={'applicationPath':str(app),'executable':str(app/'Contents/MacOS/CelluloidMac'),
            'executableSHA256':'c'*64,'logicSHA256':'d'*64}
    def validate(self,summary,files):
        def read(path,limit):
            self.assertLessEqual(len(files[path.name]),limit)
            return files[path.name]
        return contract.validate_capture(Path('/virtual'),encoded(summary),self.product,
            {'returncode':0,'started_epoch':100,'finished_epoch':102},read=read)
    def test_exact_original_document_receipts(self):
        summary,files=exported(100,self.product);proof,images=self.validate(summary,files)
        self.assertEqual(set(images),set(m.IMAGE_NAMES))
        for state,expected in contract.STATES.items():
            row=proof['states'][state]['receipt']
            self.assertEqual({key:row[key] for key in expected},expected)
    def test_module_qualified_runtime_name_required(self):
        # Actual Celluloid 485 native logs identify this Swift XCTestCase with
        # its module, unlike the QR class whose name equals its test module.
        summary,files=exported(100,self.product)
        proof,images=self.validate(summary,files)
        self.assertEqual(proof['states']['citrus']['receipt']['test'],
            '-[CelluloidMacUITests.NativeEditorUITests testStoreOriginalDocumentScreenshots]')
        for filename in ['00000000-0000-4000-8000-000000000002.txt',
                         '00000000-0000-4000-8000-000000000005.txt']:
            changed=dict(files);row=json.loads(changed[filename])
            row['test']='-[NativeEditorUITests '+m.CASE+']';changed[filename]=encoded(row)
            with self.subTest(filename=filename),self.assertRaises(ValueError):self.validate(summary,changed)
    def test_wrong_source_or_document_state_is_rejected(self):
        changes=[('citrus','sourceFilename','flat-test-fixture.png'),('coast','sourceSHA256','f'*64),
            ('citrus','sourceBytes',True),('citrus','sourceBytes',0),('coast','sourceBytes',2997725.0),
            ('citrus','sourceDimensions',[1254.0,1254]),('coast','sourceDimensions',[1200,800]),
            ('coast','documentDimensions','1200 × 800 px'),('citrus','filter','Sepia'),
            ('coast','layerCount',True),('citrus','layerCount',0.0),('coast','layerCount',1)]
        for state,key,value in changes:
            summary,files=exported(100,self.product)
            name='00000000-0000-4000-8000-00000000000'+('2' if state=='citrus' else '4')+'.txt'
            row=json.loads(files[name]);row[key]=value;files[name]=encoded(row)
            with self.subTest(state=state,key=key,value=value),self.assertRaisesRegex(ValueError,'capture-visible-state'):
                self.validate(summary,files)
    def test_missing_and_foreign_receipt_fields_are_rejected(self):
        for key in contract.STATES['citrus']:
            summary,files=exported(100,self.product);name='00000000-0000-4000-8000-000000000002.txt'
            row=json.loads(files[name]);del row[key];files[name]=encoded(row)
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'capture-receipt-fields'):self.validate(summary,files)
        summary,files=exported(100,self.product);name='00000000-0000-4000-8000-000000000002.txt'
        row=json.loads(files[name]);row['historyCount']=1;files[name]=encoded(row)
        with self.assertRaisesRegex(ValueError,'capture-receipt-fields'):self.validate(summary,files)
    def test_same_bundle_ios_tv_or_release_receipts_are_rejected(self):
        for folder,app,executable in [('Debug-iphoneos','Celluloid','Celluloid'),('Debug-appletvos','CelluloidTV','CelluloidTV'),('Release','CelluloidMac','CelluloidMac')]:
            summary,files=exported(100,self.product);name='00000000-0000-4000-8000-000000000002.txt'
            row=json.loads(files[name]);foreign='/virtual/build/mac-tests/Build/Products/'+folder+'/'+app+'.app'
            row.update(applicationPath=foreign,expectedPath=foreign,executable=foreign+'/Contents/MacOS/'+executable)
            files[name]=encoded(row)
            self.assertEqual(row['bundle'],'Mango.Celluloid')
            with self.subTest(product=app,folder=folder),self.assertRaisesRegex(ValueError,'capture-product'):
                self.validate(summary,files)
    def test_wrong_project_identifier_url_is_rejected(self):
        summary,files=exported(100,self.product);groups=json.loads(files['manifest.json'])
        groups[0]['testIdentifierURL']=groups[0]['testIdentifierURL'].replace('/CelluloidNative/','/CelluloidMac/')
        files['manifest.json']=encoded(groups)
        with self.assertRaisesRegex(ValueError,'capture-foreign-exported-case'):self.validate(summary,files)


class Pipeline(PortableTests):
    def setUp(self):
        super().setUp()
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.old=Path.cwd();os.chdir(self.root)
        self.clock=Clock();self.calls=[];self.failed=False;self.zero=False;self.late=False;self.mutate=None;self.late_summary=False;self.cleanup_unknown=False;self.scale=1;self.build_error=None
        app=self.root/'build/mac-tests/Build/Products/Debug/CelluloidMac.app'
        self.product={'applicationPath':str(app),'executable':str(app/'Contents/MacOS/CelluloidMac'),'executableSHA256':'c'*64,'logicSHA256':'d'*64}
        source=m.source_identity
        self.source_patch=patch.object(m,'source_identity',side_effect=lambda e,run,root:source(e,run,CHECKOUT));self.source_patch.start()
        self.product_patch=patch.object(m,'product_identity',side_effect=lambda:dict(self.product));self.product_patch.start()
    def tearDown(self):
        self.product_patch.stop();self.source_patch.stop();os.chdir(self.old);self.temp.cleanup()
    def runner(self,argv,**kwargs):
        self.calls.append(argv);raw=b'';stderr=b'';code=0
        if argv[0]=='git':
            if argv[1:]==['rev-parse','HEAD']:raw=(SHA+'\n').encode()
            elif argv[1:]==['rev-parse',m.PARENT+'^{tree}']:raw=(m.PARENT_TREE+'\n').encode()
            elif argv[1:]==['rev-parse','HEAD^{tree}']:raw=(TREE+'\n').encode()
            elif argv[1]=='rev-list':raw=(SHA+' '+m.PARENT+'\n').encode()
            elif argv[1]=='diff':raw=('\n'.join(m.EXPECTED_DIFF)+'\n').encode()
            else:self.assertEqual(argv[1],'status')
        elif argv==['sw_vers','-buildVersion']:raw=b'26A428\n'
        elif argv==['uname','-m']:raw=b'arm64\n'
        elif argv==['xcodebuild','-version']:raw=b'Xcode 27.0\nBuild version 27A266a\n'
        elif argv==m.base_command()+['build-for-testing']:
            if self.build_error=='stdout':raw=b'CelluloidMac.swift:4:7: error: synthetic failed compilation\n'
            if self.build_error=='stderr':stderr=b'fatal error: synthetic failed compilation\n'
            if self.build_error=='zero-wrapper':raw=b'error: the following command failed with exit code 0 but produced no further output\nSwiftCompile normal arm64 (in target \'CelluloidMacTests\' from project \'Celluloid\')\n'
        elif argv==m.test_command():
            if self.cleanup_unknown:raise m.CaptureStopped('unconfirmed owned capture',False)
            self.summary,self.files=exported(self.clock(),self.product,self.failed,self.scale)
            if self.zero:self.summary.update(totalTestCount=0,passedTests=0,failedTests=0)
            if self.late_summary:self.summary['finishTime']+=300
            self.clock.advance(301 if self.late else 2);code=65 if self.failed else 0
        elif argv[:5]==['xcrun','xcresulttool','get','test-results','summary']:raw=encoded(self.summary)
        elif argv[:3]==['xcrun','xcresulttool','export']:
            folder=self.root/m.EXPORT;folder.mkdir(parents=True)
            if self.mutate:self.mutate(self.files)
            for name,data in self.files.items():(folder/name).write_bytes(data)
        else:self.assertIn('unittest',argv)
        self.clock.advance(.1);return subprocess.CompletedProcess(argv,code,raw,stderr)
    def execute(self):return m.execute(env=env(),root=self.root,clock=self.clock,wall=self.clock,runner=self.runner)
    def retained(self):
        result=self.execute();self.assertTrue(result['qualified'],result.get('failure'));marker=self.root/'output';marker.write_text('')
        value=m.retain_report(result,self.root/m.OUTPUT,marker,root=self.root,clock=self.clock)
        m.validate_packet(self.root/m.OUTPUT,sha=SHA,tree=TREE,run_id=123,source_root=CHECKOUT)
        return value,marker
    def test_success_retains_two_native_and_two_rgb_files_pending_visual_review(self):
        value,marker=self.retained();self.assertEqual(len(value['commands']),21);self.assertEqual(set(value['image_files']),set(m.IMAGE_NAMES))
        self.assertFalse(value['store_qualified']);self.assertEqual(value['visual_acceptance'],'pending-human-review');self.assertEqual(marker.read_text(),'evidence_ready=true\n')
        self.assertEqual(self.calls.count(m.base_command()+['build-for-testing']),1);self.assertEqual(self.calls.count(m.test_command()),1)
    def test_fixed_preparation_and_original_clock_cover_all_twenty_one_commands(self):
        value,_=self.retained();commands=value['commands']
        self.assertEqual(commands[11]['command'],m.base_command()+['build-for-testing'])
        self.assertEqual(commands[12]['command'],m.test_command())
        self.assertEqual([row['command'] for row in commands[:6]],[row['command'] for row in commands[15:]])
        began=value['clock']['started_monotonic'];self.assertEqual(began,100.)
        self.assertTrue(all(began<=row['start']<=row['end'] for row in commands))
        self.assertEqual(commands[12]['cleanup_reserve_seconds'],20)
        self.assertLess(commands[-1]['end'],value['clock']['report_ready_deadline'])
    def test_offline_replay_rejects_forged_command_clock_and_cleanup(self):
        self.retained();path=self.root/m.OUTPUT/'report.json';original=json.loads(path.read_bytes())
        changes=[(11,'end',100+m.PHASE_END['build']), (12,'start',99.),
            (12,'grant_seconds',0.), (12,'owned_host_observation','unconfirmed')]
        for index,key,new in changes:
            value=copy.deepcopy(original);value['commands'][index][key]=new;path.write_bytes(m.report_bytes(value))
            with self.subTest(index=index,key=key),self.assertRaises(m.Rejected):
                m.validate_packet(self.root/m.OUTPUT,sha=SHA,tree=TREE,run_id=123,source_root=CHECKOUT)
    def test_hidpi_mode_rejected_in_exact_one_x_cohort(self):
        self.scale=2;value=self.execute();self.assertFalse(value['qualified'])
        self.assertIn('no-supported-mode',value['failure']['reason'])
    def test_failed_explicit_restore_preserves_qualified_capture_components(self):
        def mutate(files):
            name='00000000-0000-4000-8000-000000000006.txt';row=json.loads(files[name]);row['restored']=False;row['configurationResult']=1000;files[name]=encoded(row)
        self.mutate=mutate;value,_=self.retained();self.assertTrue(value['qualified']);self.assertEqual(value['runner_cleanup'],'unconfirmed')
        self.assertEqual(set(value['image_files']),set(m.IMAGE_NAMES));self.assertFalse(value['store_qualified'])
    def test_main_fails_unconfirmed_restore_while_retaining_qualified_capture(self):
        def mutate(files):
            name='00000000-0000-4000-8000-000000000006.txt'
            row=json.loads(files[name]);row['restored']=False;row['configurationResult']=1000;files[name]=encoded(row)
        self.mutate=mutate;result=self.execute();self.assertTrue(result['qualified'],result.get('failure'))
        marker=self.root/'output';marker.write_text('');retain=m.retain_report
        with patch.object(m,'ROOT',self.root),patch.object(m,'execute',return_value=result), \
                patch.object(m,'retain_report',side_effect=lambda *a,**kw:retain(*a,root=self.root,clock=self.clock,**kw)), \
                patch.dict(os.environ,{'GITHUB_OUTPUT':str(marker)}),patch.object(sys,'argv',['mac_store_capture.py']),patch('builtins.print'):
            self.assertEqual(m.main(),1)
        retained=m.validate_packet(self.root/m.OUTPUT,sha=SHA,tree=TREE,run_id=123,source_root=CHECKOUT)
        self.assertTrue(retained['qualified']);self.assertEqual(retained['runner_cleanup'],'unconfirmed')
        self.assertFalse(retained['store_qualified']);self.assertEqual(set(retained['image_files']),set(m.IMAGE_NAMES))
        self.assertEqual(marker.read_text(),'evidence_ready=true\n')
    def test_asynchronous_restore_screen_keeps_images_and_offline_validation(self):
        def mutate(files):
            name='00000000-0000-4000-8000-000000000006.txt';row=json.loads(files[name]);row['restored']=False
            row['after']['frame']=[0,0,1440,900];row['after']['cgBounds']=[0,0,1440,900]
            row['after']['visibleFrame']=[0,60,1440,809];files[name]=encoded(row)
        self.mutate=mutate;value,_=self.retained()
        self.assertTrue(value['qualified']);self.assertEqual(value['runner_cleanup'],'unconfirmed')
        self.assertEqual(set(value['image_files']),set(m.IMAGE_NAMES));self.assertEqual(len(value['commands']),21)
        restore=value['proof']['display']['restore'];self.assertEqual(restore['configurationResult'],0)
        self.assertEqual(restore['after']['mode']['width'],1024);self.assertEqual(restore['after']['frame'][2],1440)
        self.assertFalse(value['store_qualified'])
    def test_missing_restore_receipt_preserves_bound_capture_components(self):
        def mutate(files):
            groups=json.loads(files['manifest.json']);groups[0]['attachments']=[x for x in groups[0]['attachments'] if not x['suggestedHumanReadableName'].startswith('Native Mac Store display restore')];files['manifest.json']=encoded(groups)
        self.mutate=mutate;value,_=self.retained();self.assertTrue(value['qualified']);self.assertEqual(value['runner_cleanup'],'unconfirmed')
        self.assertEqual(set(value['image_files']),set(m.IMAGE_NAMES))
    def test_wrong_scale_or_offscreen_window_is_rejected(self):
        for key,value in [('backingScale',2),('windowFrame',[500,35,1280,800])]:
            summary,files=exported(100,self.product)
            name='00000000-0000-4000-8000-000000000002.txt';row=json.loads(files[name]);row[key]=value;files[name]=encoded(row)
            def read(path,limit):return files[path.name]
            with self.subTest(key=key),self.assertRaises(ValueError):contract.validate_capture(Path('/virtual'),encoded(summary),self.product,
                {'returncode':0,'started_epoch':100,'finished_epoch':102},read=read)
    def test_build_zero_exit_with_reported_error_prevents_test_launch(self):
        self.build_error='stdout';value=self.execute()
        self.assertFalse(value['qualified']);self.assertEqual(value['failure']['reason'],'build-reported-error')
        self.assertEqual(value['failure']['phase'],'build');self.assertEqual(len(self.calls),12)
        self.assertNotIn(m.test_command(),self.calls);self.assertEqual(value['image_files'],{})
    def test_build_zero_exit_with_stderr_fatal_error_prevents_test_launch(self):
        self.build_error='stderr';value=self.execute()
        self.assertFalse(value['qualified']);self.assertEqual(value['failure']['reason'],'build-reported-error')
        self.assertEqual(value['failure']['phase'],'build');self.assertEqual(len(self.calls),12)
        self.assertNotIn(m.test_command(),self.calls);self.assertEqual(value['image_files'],{})
    def test_observed_zero_exit_wrapper_error_still_stops_before_product_or_ui(self):
        self.build_error='zero-wrapper';value=self.execute()
        self.assertFalse(value['qualified']);self.assertEqual(value['failure']['reason'],'build-reported-error')
        self.assertEqual(value['failure']['phase'],'build');self.assertEqual(len(self.calls),12)
        m.product_identity.assert_not_called()
        self.assertNotIn(m.test_command(),self.calls);self.assertEqual(value['image_files'],{})
    def test_original_failed_case_stays_failed_and_no_export(self):
        self.failed=True;value=self.execute();self.assertFalse(value['qualified']);self.assertEqual(value['test_outcome'],'failed');self.assertEqual(value['image_files'],{})
        self.assertEqual(len(self.calls),14);self.assertNotIn('export',self.calls[-1])
    def test_zero_case_fails_before_export(self):
        self.zero=True;value=self.execute();self.assertFalse(value['qualified']);self.assertEqual(len(self.calls),14)
    def test_late_summary_fails_before_export(self):
        self.late_summary=True;value=self.execute();self.assertFalse(value['qualified']);self.assertEqual(len(self.calls),14)
    def test_native_test_late_return_stops_before_evidence(self):
        self.late=True;value=self.execute();self.assertFalse(value['qualified']);self.assertEqual(len(self.calls),13)
    def test_uncertain_cleanup_never_starts_evidence_or_retries(self):
        self.cleanup_unknown=True;value=self.execute();self.assertFalse(value['qualified']);self.assertFalse(value['commands'][-1]['owned_cleanup_confirmed']);self.assertEqual(len(self.calls),13)
    def test_wrong_pid_on_second_capture_rejects_packet(self):
        def mutate(files):
            name='00000000-0000-4000-8000-000000000004.txt';r=json.loads(files[name]);r['pid']+=1;files[name]=encoded(r)
        self.mutate=mutate;value=self.execute();self.assertFalse(value['qualified']);self.assertIn('second-launch',value['failure']['reason'])
    def test_wrong_product_hash_rejects_packet(self):
        def mutate(files):
            name=next(x for x in files if x.endswith('.txt'));r=json.loads(files[name]);r['logicSHA256']='f'*64;files[name]=encoded(r)
        self.mutate=mutate;value=self.execute();self.assertFalse(value['qualified']);self.assertIn('capture-product',value['failure']['reason'])
    def test_image_digest_mismatch_rejects_packet(self):
        def mutate(files):
            name=next(x for x in files if x.endswith('.txt'));r=json.loads(files[name]);r['pngSHA256']='f'*64;files[name]=encoded(r)
        self.mutate=mutate;value=self.execute();self.assertFalse(value['qualified']);self.assertIn('pixel-binding',value['failure']['reason'])
    def test_transparency_keeps_bound_originals_but_fails_store_format(self):
        def mutate(files):
            groups=json.loads(files['manifest.json']);image=groups[0]['attachments'][0]['exportedFileName'];record=groups[0]['attachments'][1]['exportedFileName']
            files[image]=png(alpha=254);row=json.loads(files[record]);row['pngSHA256']=contract.digest(files[image]);row['pngBytes']=len(files[image]);files[record]=encoded(row)
        self.mutate=mutate;value=self.execute();self.assertFalse(value['qualified']);self.assertEqual(value['source_after'],value['source_before'])
        self.assertIn('native-citrus.png',value['image_files']);self.assertNotIn('store-citrus.png',value['image_files']);self.assertIn('citrus',value['proof']['formatFailures'])
        marker=self.root/'output';marker.write_text('');retained=m.retain_report(value,self.root/m.OUTPUT,marker,root=self.root,clock=self.clock)
        self.assertFalse(retained['qualified']);self.assertTrue((self.root/m.OUTPUT/'native-citrus.png').is_file())
    def test_exported_foreign_case_rejects_packet(self):
        def mutate(files):
            groups=json.loads(files['manifest.json']);groups[0]['testIdentifier']='Another/test()';files['manifest.json']=encoded(groups)
        self.mutate=mutate;value=self.execute();self.assertFalse(value['qualified']);self.assertIn('foreign-exported',value['failure']['reason'])
    def test_unsafe_exported_name_rejects_packet(self):
        def mutate(files):
            groups=json.loads(files['manifest.json']);groups[0]['attachments'][0]['exportedFileName']='../other.png';files['manifest.json']=encoded(groups)
        self.mutate=mutate;value=self.execute();self.assertFalse(value['qualified']);self.assertIn('file-name',value['failure']['reason'])
    def test_wrong_frame_rejects_packet(self):
        def mutate(files):
            name=next(x for x in files if x.endswith('.txt'));r=json.loads(files[name]);r['windowFrame'][2]=1024;files[name]=encoded(r)
        self.mutate=mutate;value=self.execute();self.assertFalse(value['qualified']);self.assertIn('window-size',value['failure']['reason'])
    def test_retained_image_tampering_is_rejected(self):
        self.retained();p=self.root/m.OUTPUT/'store-citrus.png';p.write_bytes(p.read_bytes()+b'x')
        with self.assertRaises(m.Rejected):m.validate_packet(self.root/m.OUTPUT,sha=SHA,tree=TREE,run_id=123,source_root=CHECKOUT)
    def test_forged_source_or_visual_acceptance_is_rejected(self):
        self.retained();p=self.root/m.OUTPUT/'report.json';original=json.loads(p.read_bytes())
        for key,value in [('store_qualified',True),('visual_acceptance','approved')]:
            changed=copy.deepcopy(original);changed[key]=value;p.write_bytes(m.report_bytes(changed))
            with self.subTest(key=key),self.assertRaises(m.Rejected):m.validate_packet(self.root/m.OUTPUT,sha=SHA,tree=TREE,run_id=123,source_root=CHECKOUT)
        p.write_bytes(m.report_bytes(original))
        with self.assertRaises(m.Rejected):m.validate_packet(self.root/m.OUTPUT,sha='e'*40,tree=TREE,run_id=123,source_root=CHECKOUT)
    def test_replay_rejects_changed_toolchain_report_or_command_output(self):
        self.retained();path=self.root/m.OUTPUT/'report.json';original=json.loads(path.read_bytes())
        for target in ('report','command'):
            changed=copy.deepcopy(original)
            if target=='report':changed['toolchain']['os']='different-build'
            else:changed['commands'][6]['stdout']='different-build\n'
            path.write_bytes(m.report_bytes(changed))
            with self.subTest(target=target),self.assertRaisesRegex(m.Rejected,'toolchain'):
                m.validate_packet(self.root/m.OUTPUT,sha=SHA,tree=TREE,run_id=123,source_root=CHECKOUT)
    def test_upload_full_reserve_and_original_clock_are_required(self):
        value,_=self.retained();value['upload_observation']=m.admit_upload(value,clock=self.clock)
        self.assertTrue(m.finish_upload(value,'success',clock=self.clock)['upload_qualified']);self.assertFalse(m.finish_upload(value,'failure',clock=self.clock)['upload_qualified'])
        self.clock.advance(61);self.assertFalse(m.finish_upload(value,'success',clock=self.clock)['upload_qualified'])
    def test_upload_admission_cannot_reset_original_clock_or_shorten_reserves(self):
        value,_=self.retained();began=value['clock']['started_monotonic']
        for now in (began-1,began+m.PHASE_END['evidence']-60,began+m.PHASE_END['finalization']-80):
            with self.subTest(now=now),self.assertRaises(m.Rejected):m.admit_upload(value,clock=lambda:now)
        value['upload_observation']=m.admit_upload(value,clock=self.clock)
        value['upload_observation']['evidence_deadline']+=1
        receipt=m.finish_upload(value,'success',clock=self.clock)
        self.assertFalse(receipt['upload_qualified']);self.assertEqual(receipt['failure'],'upload-admission-identity-mismatch')
    def test_retention_lateness_never_emits_upload_marker(self):
        value=self.execute();self.assertTrue(value['qualified']);value['clock']['report_ready_deadline']=self.clock();marker=self.root/'output';marker.write_text('previous\n')
        with self.assertRaises(m.Rejected):m.retain_report(value,self.root/m.OUTPUT,marker,root=self.root,clock=self.clock)
        self.assertEqual(marker.read_text(),'previous\n')
    def test_oversized_report_does_not_publish_images_as_qualified(self):
        value=self.execute();value['commands']=['x'*(m.MAX_REPORT+1)];decoded=json.loads(m.report_bytes(value));self.assertFalse(decoded['qualified']);self.assertEqual(set(decoded['image_files']),{'native-citrus.png','native-coast.png'});self.assertTrue(decoded['diagnostic_files'])

    def mutate_display_case(self,files):
        for suffix in ('5','6'):
            name='00000000-0000-4000-8000-00000000000'+suffix+'.txt'
            row=json.loads(files[name]);row['test']='-[NativeEditorUITests '+m.CASE+']';files[name]=encoded(row)
        self.rehash_setup(files)
    def rehash_setup(self,files):
        setup='00000000-0000-4000-8000-000000000005.txt';restore='00000000-0000-4000-8000-000000000006.txt'
        row=json.loads(files[restore]);row['setupSHA256']=contract.digest(files[setup]);files[restore]=encoded(row)
        for suffix in ('2','4'):
            name='00000000-0000-4000-8000-00000000000'+suffix+'.txt';row=json.loads(files[name]);row['displaySetupSHA256']=contract.digest(files[setup]);files[name]=encoded(row)
    def failed_with_raw(self):
        value=self.execute();self.assertFalse(value['qualified']);self.assertTrue(value['raw_evidence'])
        self.assertEqual(set(value['image_files']),{'native-citrus.png','native-coast.png'})
        self.assertEqual(value['raw_evidence']['status'],'unqualified');self.assertTrue(value['raw_evidence']['visual_pending'])
        marker=self.root/'output';marker.write_text('');retained=m.retain_report(value,self.root/m.OUTPUT,marker,root=self.root,clock=self.clock)
        observed=m.inspect_raw_packet(self.root/m.OUTPUT,sha=SHA,tree=TREE,run_id=123,source_root=CHECKOUT)
        self.assertTrue(observed['raw_integrity']);self.assertFalse(observed['proof_replay_passed']);self.assertEqual(observed['status'],'unqualified')
        self.assertEqual(len(self.calls),15);self.assertEqual(marker.read_text(),'evidence_ready=true\n')
        for name,exported in retained['raw_evidence']['exportedNames'].items():
            self.assertEqual((self.root/m.OUTPUT/name).read_bytes(),self.files[exported])
        with self.assertRaisesRegex(m.Rejected,'capture-not-qualified'):
            m.validate_packet(self.root/m.OUTPUT,sha=SHA,tree=TREE,run_id=123,source_root=CHECKOUT)
        return retained,observed
    def test_proof_case_rejection_retains_both_originals_and_bounded_raw_receipts(self):
        self.mutate=self.mutate_display_case;value,observed=self.failed_with_raw()
        self.assertEqual(value['failure']['reason'],'display-case-name')
        self.assertEqual(observed['proof_failure']['observations'],value['failure']['observations'])
        self.assertEqual(value['failure']['observations']['observed_case'],'-[NativeEditorUITests '+m.CASE+']')
        self.assertEqual(value['failure']['observations']['expected_case'],'-[CelluloidMacUITests.NativeEditorUITests '+m.CASE+']')
        self.assertEqual(len(value['diagnostic_files']),5)
    def test_attachment_clock_rejection_retains_raw_times_without_relaxing_gate(self):
        def mutate(files):
            name='00000000-0000-4000-8000-000000000005.txt';row=json.loads(files[name])
            manifest=json.loads(files['manifest.json']);stamp=manifest[0]['attachments'][4]['timestamp']
            row['finished']=stamp+.005;files[name]=encoded(row);self.rehash_setup(files)
        self.mutate=mutate;value,observed=self.failed_with_raw()
        self.assertEqual(value['failure']['reason'],'display-attachment-clock')
        seen=value['failure']['observations'];self.assertEqual(seen['receipt'],'setup');self.assertEqual(seen['tolerance_seconds'],.001)
        self.assertGreater(seen['difference_seconds'],.001)
        self.assertEqual(observed['proof_failure']['observations'],seen)
    def test_raw_receipt_tamper_and_unlisted_file_are_rejected(self):
        self.mutate=self.mutate_display_case;value,_=self.failed_with_raw();output=self.root/m.OUTPUT
        target=output/'raw-proof-citrus.json';raw=target.read_bytes();target.write_bytes(raw+b' ')
        with self.assertRaisesRegex(m.Rejected,'changed-retained-image'):m.verify_retained_images(value,output)
        target.write_bytes(raw);(output/'arbitrary.txt').write_bytes(b'not part of cohort')
        with self.assertRaisesRegex(m.Rejected,'unlisted-retained-file'):m.verify_retained_images(value,output)
    def test_unsafe_raw_export_does_not_gain_forensic_or_qualified_images(self):
        def mutate(files):
            value=json.loads(files['manifest.json']);value[0]['attachments'][0]['exportedFileName']='../private.png';files['manifest.json']=encoded(value)
        self.mutate=mutate;value=self.execute();self.assertFalse(value['qualified']);self.assertEqual(value['image_files'],{})
        self.assertEqual(value['diagnostic_files'],{});self.assertNotIn('raw_evidence',value)
    def test_report_overflow_preserves_raw_context_and_native_bytes_unqualified(self):
        value=self.execute();self.assertTrue(value['qualified'])
        value['oversized_diagnostic']='x'*(m.MAX_REPORT+1);decoded=json.loads(m.report_bytes(value))
        self.assertFalse(decoded['qualified']);self.assertEqual(decoded['failure']['reason'],'report-byte-limit')
        marker=self.root/'output';marker.write_text('');result=m.retain_report(value,self.root/m.OUTPUT,marker,root=self.root,clock=self.clock)
        self.assertEqual(set(result['image_files']),{'native-citrus.png','native-coast.png'})
        self.assertEqual(len(result['diagnostic_files']),5);self.assertEqual(result['raw_evidence']['status'],'unqualified')
        observation=m.inspect_raw_packet(self.root/m.OUTPUT,sha=SHA,tree=TREE,run_id=123,source_root=CHECKOUT)
        self.assertTrue(observation['raw_integrity']);self.assertTrue(observation['proof_replay_passed'])
        self.assertEqual(observation['status'],'unqualified')
    def test_near_limit_unicode_summary_and_proof_rejection_still_retains_originals(self):
        self.mutate=self.mutate_display_case;runner=self.runner
        def unicode_summary(argv,**kwargs):
            result=runner(argv,**kwargs)
            if argv[:5]==['xcrun','xcresulttool','get','test-results','summary']:
                self.summary['testPlanName']='界'*174000
                result.stdout=json.dumps(self.summary,ensure_ascii=False,separators=(',', ':')).encode('utf-8')
                self.assertLessEqual(len(result.stdout),512*1024)
            return result
        with patch.object(self,'runner',side_effect=unicode_summary):value=self.execute()
        self.assertFalse(value['qualified']);self.assertEqual(value['failure']['reason'],'display-case-name')
        self.assertEqual(len(value['raw_evidence']['files']),7)
        marker=self.root/'output';marker.write_text('')
        retained=m.retain_report(value,self.root/m.OUTPUT,marker,root=self.root,clock=self.clock)
        self.assertEqual(set(retained['image_files']),{'native-citrus.png','native-coast.png'})
        self.assertEqual(marker.read_text(),'evidence_ready=true\n')
        self.assertLessEqual((self.root/m.OUTPUT/'report.json').stat().st_size,m.MAX_REPORT)
        observation=m.inspect_raw_packet(self.root/m.OUTPUT,sha=SHA,tree=TREE,run_id=123,source_root=CHECKOUT)
        self.assertEqual(observation['proof_failure']['reason'],'display-case-name')
        self.assertFalse(observation['proof_replay_passed'])
    def test_lone_surrogate_in_admitted_summary_is_losslessly_escaped_for_retention(self):
        self.mutate=self.mutate_display_case;runner=self.runner
        def surrogate_summary(argv,**kwargs):
            result=runner(argv,**kwargs)
            if argv[:5]==['xcrun','xcresulttool','get','test-results','summary']:
                self.summary['testPlanName']='\ud800'
                result.stdout=json.dumps(self.summary,separators=(',', ':')).encode('utf-8')
            return result
        with patch.object(self,'runner',side_effect=surrogate_summary):value=self.execute()
        self.assertEqual(value['failure']['reason'],'display-case-name')
        marker=self.root/'output';marker.write_text('')
        retained=m.retain_report(value,self.root/m.OUTPUT,marker,root=self.root,clock=self.clock)
        self.assertEqual(retained['test_summary']['testPlanName'],'\ud800')
        self.assertEqual(set(retained['image_files']),{'native-citrus.png','native-coast.png'})
        self.assertEqual(marker.read_text(),'evidence_ready=true\n')
        observed=m.inspect_raw_packet(self.root/m.OUTPUT,sha=SHA,tree=TREE,run_id=123,source_root=CHECKOUT)
        self.assertTrue(observed['raw_integrity']);self.assertEqual(observed['proof_failure']['reason'],'display-case-name')
    def test_final_source_failure_keeps_originals_unqualified(self):
        source=m.source_identity;count=0
        def changed(*a,**kw):
            nonlocal count
            value=source(*a,**kw);count+=1
            if count==2:value=dict(value,tree='f'*40)
            return value
        with patch.object(m,'source_identity',side_effect=changed):value=self.execute()
        self.assertFalse(value['qualified']);self.assertEqual(value['failure']['reason'],'source-changed')
        self.assertEqual(set(value['image_files']),{'native-citrus.png','native-coast.png'})
        self.assertEqual(value['raw_evidence']['status'],'unqualified')
    def test_original_clock_abort_in_raw_retention_never_enters_proof_or_final_commands(self):
        with patch.object(m,'collect_raw',side_effect=m.Rejected('deadline-exceeded')),patch.object(m,'validate_capture') as proof:
            value=self.execute()
        self.assertFalse(value['qualified']);self.assertEqual(value['failure']['reason'],'deadline-exceeded')
        proof.assert_not_called();self.assertEqual(len(self.calls),15);self.assertEqual(value['image_files'],{})
    def test_raw_diagnostic_bytes_share_existing_packet_ceiling(self):
        value=self.execute();marker=self.root/'output';marker.write_text('previous\n')
        with patch.object(m,'MAX_PACKET',1024),self.assertRaisesRegex(m.Rejected,'packet-byte-limit'):
            m.retain_report(value,self.root/m.OUTPUT,marker,root=self.root,clock=self.clock)
        self.assertEqual(marker.read_text(),'previous\n')


if __name__=='__main__':unittest.main()
