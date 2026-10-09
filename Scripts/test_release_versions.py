"""Current owned release metadata only; synthetic checks are not native/package proof."""
from pathlib import Path
import ast,contextlib,copy,hashlib,io,json,plistlib,runpy,shutil,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
VERSION,BUILD='1.1.1','3'

def require_pair(version,build):
    if type(version) is not str or type(build) is not str or (version,build)!=(VERSION,BUILD):
        raise ValueError('Wrong current owned version/build')
def resolved_pair(info,settings):
    def resolve(value):
        if value=='$(CURRENT_PROJECT_VERSION)':return settings['CURRENT_PROJECT_VERSION']
        if value=='$(MARKETING_VERSION)':return settings['MARKETING_VERSION']
        return value
    return resolve(info['CFBundleShortVersionString']),resolve(info['CFBundleVersion'])

def project_pairs(graph,root,native=False):
    result=[];objects=graph['objects']
    for target in [n for n in objects.values() if n.get('isa')=='PBXNativeTarget']:
        if not native and target['name'] not in {'Celluloid','CelluloidKit','CelluloidPhotoExtension'}:continue
        for identifier in objects[target['buildConfigurationList']]['buildConfigurations']:
            config=objects[identifier];settings=config['buildSettings']
            if native:
                pair=(settings['MARKETING_VERSION'],settings['CURRENT_PROJECT_VERSION']);require_pair(*pair)
            else:
                require_pair(VERSION,settings['CURRENT_PROJECT_VERSION'])
                info=plistlib.loads((root/settings['INFOPLIST_FILE']).read_bytes());pair=resolved_pair(info,settings);require_pair(*pair)
            result.append((target['name'],config['name'],*pair))
    if not result:raise ValueError('No owned target versions')
    return result

class ReleaseVersionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory();cls.copy=Path(cls.temporary.name)/'source'
        shutil.copytree(ROOT,cls.copy,ignore=shutil.ignore_patterns('.git','__pycache__'))
        before={str(p.relative_to(cls.copy)):p.read_bytes() for p in cls.copy.rglob('*') if p.is_file()}
        with contextlib.redirect_stdout(io.StringIO()):
            cls.ios=runpy.run_path(str(cls.copy/'Scripts/generate_project.py'))
            cls.native=runpy.run_path(str(cls.copy/'Scripts/generate_native_project.py'))
        after={str(p.relative_to(cls.copy)):p.read_bytes() for p in cls.copy.rglob('*') if p.is_file()}
        cls.reproduces=before==after
    @classmethod
    def tearDownClass(cls):cls.temporary.cleanup()
    def test_all_owned_debug_release_targets_have_exact_current_versions(self):
        ios=project_pairs(self.ios,self.copy);native=project_pairs(self.native,self.copy,True)
        self.assertEqual({x[0] for x in ios},{'Celluloid','CelluloidKit','CelluloidPhotoExtension'})
        self.assertTrue({'CelluloidMac','CelluloidMacPhotosExtension','CelluloidTV','CelluloidVision','CelluloidWatch','CelluloidPhoneCompanion'}.issubset({x[0] for x in native}))
        for name in {x[0] for x in ios+native}:
            self.assertEqual({x[1] for x in ios+native if x[0]==name},{'Debug','Release'})
    def test_generators_reproduce_without_extra_file_or_byte_changes(self):self.assertTrue(self.reproduces)
    def test_previous_partial_missing_numeric_and_foreign_versions_reject(self):
        require_pair(VERSION,BUILD)
        for version,build in [('1.1','2'),('1.1',BUILD),(VERSION,'2'),(VERSION,'4'),(None,BUILD),(VERSION,3),(1.1,BUILD),('1.0','1'),(VERSION,None)]:
            with self.subTest(version=version,build=build),self.assertRaises(ValueError):require_pair(version,build)
        for graph,native in [(self.ios,False),(self.native,True)]:
            changed=copy.deepcopy(graph['objects'])
            config=next(n for n in changed.values() if n.get('isa')=='XCBuildConfiguration' and n.get('buildSettings',{}).get('CURRENT_PROJECT_VERSION')==BUILD)
            config['buildSettings']['CURRENT_PROJECT_VERSION']='2'
            with self.assertRaises(ValueError):project_pairs({'objects':changed},self.copy,native)
    def test_staging_and_phone_version_rejections_survive_python_optimization(self):
        for name in ['stage_uikit_layer_fixture.py','run_native_phone.py']:
            tree=ast.parse((ROOT/'Scripts'/name).read_text())
            guards=[n for n in ast.walk(tree) if isinstance(n,ast.If) and 'CFBundleShortVersionString' in ast.unparse(n.test) and VERSION in ast.unparse(n.test)]
            self.assertEqual(len(guards),1,name)
            for optimized in [0,2]:
                program=compile(ast.Module(body=guards,type_ignores=[]),name,'exec',optimize=optimized)
                info={'CFBundleIdentifier':'Mango.Celluloid','CFBundleExecutable':'Celluloid','CFBundleShortVersionString':VERSION,'CFBundleVersion':BUILD,'DTPlatformName':'iphonesimulator'}
                exec(program,{'info':info})
                for key,value in [('CFBundleShortVersionString','1.1'),('CFBundleVersion','2'),('CFBundleVersion',3),('CFBundleShortVersionString',None)]:
                    changed=dict(info);changed[key]=value
                    with self.subTest(name=name,optimized=optimized,key=key,value=value),self.assertRaises(ValueError):exec(program,{'info':changed})
    def test_actual_installed_identity_rejects_old_or_split_current_metadata(self):
        import uikit_installed_identity as identity
        owner='12345678-1234-1234-1234-123456789ABC';expected={'CFBundleIdentifier':'Mango.Celluloid','CFBundleExecutable':'Celluloid','CFBundleShortVersionString':VERSION,'CFBundleVersion':BUILD,'DTPlatformName':'iphonesimulator'}
        staging={'binary_sha256':'a'*64}
        row={'device_id':owner,'app_path':'/owned/Devices/'+owner+'/data/Containers/Bundle/Application/owned/Celluloid.app','binary_sha256':'a'*64,'identity':expected,'relocated_since_initial_staging':False,'lookup_count':1,'lookup_timeout_seconds':60}
        staging['installed_app']=row['app_path']
        identity.validate(row,owner,staging)
        for key,value in [('CFBundleShortVersionString','1.1'),('CFBundleVersion','2'),('CFBundleVersion',3),('CFBundleShortVersionString','1.0')]:
            changed=copy.deepcopy(row);changed['identity'][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):identity.validate(changed,owner,staging)
    def test_snapkit_pin_license_and_adjustment_format_are_independent(self):
        locks=[ROOT/'Celluloid.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved',ROOT/'Celluloid.xcworkspace/xcshareddata/swiftpm/Package.resolved']
        for path in locks:
            pins=json.loads(path.read_text())['pins'];snapkit=next(r for r in pins if r['identity']=='snapkit')
            self.assertEqual(snapkit['state'],{'revision':'2842e6e84e82eb9a8dac0100ca90d9444b0307f4','version':'5.7.1'})
        self.assertEqual(hashlib.sha256((ROOT/'CelluloidKit/ThirdPartyNotices/SnapKit-LICENSE.txt').read_bytes()).hexdigest(),'7c0d21cf5314759fd35a22e42a52099d9cad2570db55a78e4eda26c82493b96b')
        archive=(ROOT/'Scripts/original_ios_archive.py').read_text()
        self.assertIn("'1.0' if path == SNAPKIT else '1.1.1'",archive);self.assertIn("'1' if path == SNAPKIT else '3'",archive)
        for name in ['Scripts/fixtures/platform-rendering-controls.json','Scripts/fixtures/native-text-expectations.json']:
            # Existing independent validators retain their exact immutable digest.
            self.assertTrue((ROOT/name).is_file())
        from platform_rendering_contract import control_bytes,native_spec
        control_bytes();native_spec()
    def test_watch_mismatch_negative_control_remains_distinct(self):
        source=(ROOT/'Scripts/test_embedded_watch.py').read_text()
        self.assertIn("self.watch_info['CFBundleVersion']='4'",source)
        self.assertNotIn("self.watch_info['CFBundleVersion']='3'",source)
        native=(ROOT/'Platforms/PhoneTests/PhoneCompanionTests.swift').read_text()
        self.assertIn('forInfoDictionaryKey: "CFBundleShortVersionString") as? String, "1.1.1"',native)
        self.assertIn('forInfoDictionaryKey: "CFBundleVersion") as? String, "3"',native)

if __name__=='__main__':unittest.main()
