"""Synthetic receipt/parser adversaries; no Apple runtime acceptance is claimed."""
import base64,copy,hashlib,json,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import platform_rendering_contract as contract
import verify_interop_continuation as gate
import test_interop_continuation as historical
from verify_required_interoperability import verify as required_verify

class PlatformContractTests(unittest.TestCase):
    SOURCE='a'*40
    def fixture(self):
        c=json.loads(contract.control_bytes());p=c['profiles']['2x']['images']
        row={'name':'manufactured-affine','identifier':'Mango.CelluloidPhotoExtension','version':'1.0',
             'sha256':c['inputArchive']['sha256'],'base64':c['inputArchive']['base64'],
             'sourceSHA256':c['inputImage']['sha256'],'sourceBase64':c['inputImage']['base64'],
             'renderedSHA256':p['full']['sha256'],'renderedBase64':p['full']['base64'],'components':[]}
        for name in ['filtered-base','bubble-artwork','sticker-artwork','all-artwork']:
            row['components'].append(dict(name=name,**(c['common'][name] if name in c['common'] else p[name])))
        return row
    def receipt(self,profile='2x'):
        f=self.fixture()
        return {'schema':'Celluloid.PlatformRendering.2','profile':profile,'runtimeVersion':'27.0','scale':int(profile[0]),
            'controlFileSHA256':contract.CONTROL_SHA,'controlSourceSHA':contract.CONTROL_SOURCE,
            'archiveSHA256':f['sha256'],'controlArchiveSHA256':json.loads(contract.control_bytes())['archiveSHA256'],'sourceSHA256':f['sourceSHA256'],'nativeSHA256':f['renderedSHA256'],
            'historicalFullMaximum':202 if profile=='2x' else 132,
            'sameRuntimeMaximums':{'full':0,'bubble-artwork':0,'all-artwork':0},
            'exactComponentMaximums':{'filtered-base':0,'sticker-artwork':0},
            'artworkMetrics':{name:{'outsideMaximum':0,'edgeViolations':0,'envelopeViolations':0,'opacityViolations':0,'controlBandPixels':count} for name,count in contract.BANDS.items()},'rejectedArtworkMutations':6}
    def native(self):
        spec=contract.native_spec();f=self.fixture();row=copy.deepcopy(spec['fixed'])
        row.update(schema=spec['schema'],sourcePNG_SHA256=f['sourceSHA256'],actualPNG_SHA256=f['renderedSHA256'],actualRGBA_SHA256='a'*64,controlRGBA_SHA256='b'*64,maximumChannelDifference=1,differentPixels=0)
        row['mutations']=[dict(name=name,hookCalls=1,rgbaSHA256=str(index+1)*64,maximumDifferenceFromControl=12,maximumDifferenceFromUnmutated=11,differentPixelsFromControl=20,differentPixelsFromUnmutated=19) for index,name in enumerate(spec['mutation_names'])]
        return row
    def test_release_extension_binary_must_exist_without_qualification_hooks(self):
        from native_text_release_guard import qualified_extension_has_no_hooks,MARKERS
        with tempfile.TemporaryDirectory() as temporary:
            app=Path(temporary)/'CelluloidMac.app'
            self.assertFalse(qualified_extension_has_no_hooks(app))
            binary=app/'Contents/PlugIns/CelluloidMacPhotosExtension.appex/Contents/MacOS/CelluloidMacPhotosExtension'
            binary.parent.mkdir(parents=True);binary.write_bytes(b'synthetic Release binary')
            self.assertTrue(qualified_extension_has_no_hooks(app))
            for marker in MARKERS:
                binary.write_bytes(b'synthetic binary '+marker)
                self.assertFalse(qualified_extension_has_no_hooks(app))
            binary.unlink();binary.symlink_to('/not-an-owned-release-binary')
            self.assertFalse(qualified_extension_has_no_hooks(app))

    def test_immutable_two_scale_controls_and_exact_inputs(self):
        c=json.loads(contract.control_bytes());self.assertEqual(c['runtimeBuild'],'24A434')
        self.assertNotEqual(c['profiles']['2x']['images']['full']['sha256'],c['profiles']['3x']['images']['full']['sha256'])
        for profile in ['2x','3x']:contract.validate_receipt(self.receipt(profile),self.fixture(),profile)
        contract.validate_native(self.native(),self.fixture())
    def test_missing_unknown_duplicate_wrong_profile_or_changed_golden_rejects(self):
        changes=[lambda r:r.pop('scale'),lambda r:r.update(extra=True),lambda r:r.update(schema='legacy'),
            lambda r:r.update(profile='4x'),lambda r:r.update(scale=True),lambda r:r.update(scale=3),
            lambda r:r.update(controlFileSHA256='f'*64),lambda r:r.update(controlSourceSHA='f'*40),
            lambda r:r.update(archiveSHA256='f'*64),lambda r:r.update(sourceSHA256='f'*64),lambda r:r.update(nativeSHA256='f'*64),
            lambda r:r['sameRuntimeMaximums'].update(full=3),lambda r:r['sameRuntimeMaximums'].update(full=True),
            lambda r:r['sameRuntimeMaximums'].pop('all-artwork'),lambda r:r['exactComponentMaximums'].update(**{'filtered-base':1}),
            lambda r:r['artworkMetrics']['bubble-artwork'].update(outsideMaximum=1),lambda r:r['artworkMetrics']['bubble-artwork'].update(edgeViolations=1),
            lambda r:r['artworkMetrics']['bubble-artwork'].update(envelopeViolations=1),lambda r:r['artworkMetrics']['bubble-artwork'].update(controlBandPixels=100000),
            lambda r:r.update(rejectedArtworkMutations=5),lambda r:r.update(historicalFullMaximum=float('nan'))]
        for change in changes:
            row=self.receipt();change(row)
            with self.subTest(change=change),self.assertRaises((ValueError,KeyError)):contract.validate_receipt(row,self.fixture(),'2x')
        line=contract.PREFIX+json.dumps(self.receipt())
        for log in [line+'\n'+line,' '+line,line.replace('"scale": 2','"scale":2,"scale":2'),line+'\nMAC_PLATFORM_RENDERING_CONTRACT malformed']:
            with self.assertRaises(ValueError):contract.from_log(log,self.fixture())
    def test_native_fixed_content_geometry_and_real_path_mutations_are_required(self):
        changes=[lambda r:r.pop('mutations'),lambda r:r.update(extra=1),lambda r:r.update(sourcePNG_SHA256='f'*64),
            lambda r:r.update(actualPNG_SHA256='f'*64),lambda r:r.update(maximumChannelDifference=3),
            lambda r:r.update(differentPixels=1),lambda r:r.update(fontSize=True),lambda r:r.update(baselines=[40,52,65]),
            lambda r:r.update(destination=[77.231,26.24,27.875,43.52]),lambda r:r.update(sourceSpans=[[0,7],[7,3],[10,2]]),
            lambda r:r.update(text='Hello,世界 🎬'),lambda r:r['control'].update(fontSize=11),
            lambda r:r['mutations'].pop(),lambda r:r['mutations'][0].update(hookCalls=0),lambda r:r['mutations'][0].update(hookCalls=True),
            lambda r:r['mutations'][0].update(rgbaSHA256='a'*64),lambda r:r['mutations'][0].update(maximumDifferenceFromUnmutated=2),
            lambda r:r['mutations'][0].update(differentPixelsFromControl=0),lambda r:r['mutations'][1].update(name=r['mutations'][0]['name']),
            lambda r:r.update(backingScale=float('inf'))]
        for change in changes:
            row=self.native();change(row)
            with self.subTest(change=change),self.assertRaises((ValueError,KeyError)):contract.validate_native(row,self.fixture())
    def profile(self,profile='2x',failed=False):
        row,log,summary,timing,fixture=historical.ContinuationTests.profile(self,profile,failed=False)
        maximum=202 if profile=='2x' else 132;artwork=6 if profile=='2x' else 38
        log=log.replace('nativeSHA256='+fixture['renderedSHA256']+' maximumChannelDifference=0','nativeSHA256='+fixture['renderedSHA256']+' maximumChannelDifference='+str(maximum))
        for name in ['bubble-artwork','all-artwork']:
            component=next(c for c in fixture['components'] if c['name']==name)
            log=log.replace('name='+name+' nativeSHA256='+component['sha256']+' maximumChannelDifference=0','name='+name+' nativeSHA256='+component['sha256']+' maximumChannelDifference='+str(artwork))
        marker=contract.PREFIX+json.dumps(self.receipt(profile))+'\n'
        final="Test Case '-[CelluloidTests."+gate.OWNER+' '+gate.METHOD+"]' passed"
        log=log.replace(final,marker+final)
        row.update(pixel_passed=False,platform_contract_passed=True,passed=True)
        summary['devicesAndConfigurations'][0]['device'].update(osBuildNumber='24A434',architecture='arm64')
        return row,log,summary,timing,fixture
    def packet(self,temp):
        packet,summaries=historical.ContinuationTests.packet(self,temp)
        native=self.native();test=contract.native_spec()['required_test'];owner,method=test.split('.')
        path=temp/'mac.log';log=path.read_text();final=f"Test Case '-[CelluloidMacPhotosExtensionTests.{owner} {method}]' passed (0.1 seconds)."
        # It is a synthetic harness packet; require exactly the same record
        # enclosure as the real native test, regardless of draft source count.
        log=log.replace(final+'\n','')
        log+=f"Test Case '-[CelluloidMacPhotosExtensionTests.{owner} {method}]' started.\n"+contract.NATIVE_PREFIX+json.dumps(native)+'\n'+final+'\n';path.write_text(log)
        packet.update(platform_contract_passed=True,passed=True,pixel_passed=False)
        for row in packet['profiles']:
            row['staging']['control_file_sha256']=contract.CONTROL_SHA
            row['post_test_installation']={'device_id':row['udid'],'app_path':row['staging']['installed_app'],'binary_sha256':row['staging']['binary_sha256'],
                'identity':{'CFBundleIdentifier':'Mango.Celluloid','CFBundleExecutable':'Celluloid','CFBundleShortVersionString':'1.1','CFBundleVersion':'2','DTPlatformName':'iphonesimulator'},'relocated_since_initial_staging':False,'lookup_count':1,'lookup_timeout_seconds':60}
            (temp/f"early-uikit-{row['profile']}-staging.json").write_text(json.dumps(row['staging']))
            row['consumer']=required_verify('uikit',temp/f"early-uikit-{row['profile']}-interop.log",temp/'early-uikit-fixtures',self.SOURCE,platform_contract=True,runtime_summary=summaries[row['profile']],expected_device={'id':row['udid'],'model':row['device_type']})
        (temp/'early-uikit-interop.json').write_text(json.dumps(packet));return packet,summaries
    def exercise(self,mutate=None,temporary_prefix='tmp'):
        with tempfile.TemporaryDirectory(prefix=temporary_prefix) as folder:
            temp=Path(folder);packet,summaries=self.packet(temp)
            if mutate:mutate(temp,packet,summaries);(temp/'early-uikit-interop.json').write_text(json.dumps(packet))
            def command(args,**kwargs):
                args=list(map(str,args));profiles={'CelluloidEarlyUIKit2x.xcresult':'2x','CelluloidEarlyUIKit3x.xcresult':'3x'}
                value={'devices':{}} if 'simctl' in args else summaries[profiles[Path(args[-1]).name]]
                return subprocess.CompletedProcess(args,0,json.dumps(value),'')
            with patch.object(gate.subprocess,'check_output',side_effect=[self.SOURCE+'\n','']),patch.object(gate,'frozen_uikit_fingerprint',return_value=gate.FROZEN_UIKIT_FINGERPRINT),patch.object(gate,'TEST_SOURCE_SHA',gate.sha(gate.ROOT/gate.TEST_SOURCE)),patch.object(gate,'run',side_effect=command):
                return gate.verify(temp,self.SOURCE)
    def test_3x_summary_is_selected_when_temporary_parent_contains_2x(self):
        result=self.exercise(temporary_prefix='celluloid-parent-2x-')
        self.assertTrue(result['continuation_safe'])
        self.assertEqual([row['profile'] for row in result['profiles']],['2x','3x'])
        self.assertEqual([row['scale'] for row in result['profiles']],[2,3])
        self.assertNotEqual(result['profiles'][0]['device_id'],result['profiles'][1]['device_id'])

    def test_complete_versioned_full_proof_keeps_historical_failure_and_archive_freeze(self):
        result=self.exercise();self.assertTrue(result['continuation_safe']);self.assertTrue(result['platform_contract_accepted']);self.assertFalse(result['strict_pixel_passed']);self.assertFalse(result['final_archive_accepted'])
        self.assertEqual(result['profiles'][0]['deltas']['full'],202)
    def test_new_live_route_never_exempts_unexpected_assertions_outcomes_runtime_or_cleanup(self):
        changes=[lambda log:log+'Assertion Failure: wrong geometry\n',lambda log:log+'** TEST EXECUTE FAILED **\n',
            lambda log:log+" Test Suite 'Selected tests' failed at 2026-10-04 15:00:00.000.\n",
            lambda log:log+'Failing tests:\n\tUnexpectedStructuralTests.testWrongGeometry()\n',
            lambda log:log+' MAC_PLATFORM_RENDERING_CONTRACT malformed\n',
            lambda log:log.replace('"sameRuntimeMaximums": {"full": 0','"sameRuntimeMaximums": {"full": 3')]
        for change in changes:
            def mutate(t,p,s):
                row=p['profiles'][1];path=t/'early-uikit-3x-interop.log';path.write_text(change(path.read_text()))
                row['consumer']=required_verify('uikit',path,t/'early-uikit-fixtures',self.SOURCE,platform_contract=True,runtime_summary=s['3x'],expected_device={'id':row['udid'],'model':row['device_type']})
            with self.subTest(change=change),self.assertRaises(ValueError):self.exercise(mutate)
        edits=[lambda t,p,s:p['profiles'][0].pop('post_test_installation'),lambda t,p,s:p['profiles'][0]['post_test_installation'].update(binary_sha256='f'*64),lambda t,p,s:p['profiles'][0]['cleanup'][0].update(exit_code=1),lambda t,p,s:p.update(platform_contract_passed=False),
            lambda t,p,s:s['3x']['devicesAndConfigurations'][0]['device'].update(osBuildNumber='unqualified'),
            lambda t,p,s:(t/'mac.log').write_text((t/'mac.log').read_text().replace(contract.NATIVE_PREFIX,'MISSING_NATIVE_CONTRACT '))]
        for change in edits:
            with self.subTest(change=change),self.assertRaises(ValueError):self.exercise(change)

if __name__=='__main__':unittest.main()
