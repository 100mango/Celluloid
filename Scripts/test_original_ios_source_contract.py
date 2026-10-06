"""Exact approved source delta only; fresh archive and device tests remain mandatory."""
import copy,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import original_ios_source_contract as contract

class OriginalIOSSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prior=contract.graph(contract.baseline('Scripts/generate_project.py'))
        cls.current=contract.graph((contract.ROOT/'Scripts/generate_project.py').read_bytes())

    def test_original_features_resources_tests_and_embedding_are_preserved(self):
        report=contract.audit()
        self.assertEqual(report['schema'],'Celluloid.OriginalIOSSource.2')
        self.assertEqual(report['unchanged_protected_files'],539)
        self.assertEqual(report['protected_file_count'],546)
        self.assertEqual(report['original_unique_test_methods'],106)
        self.assertEqual(report['original_total_invocations'],412)
        self.assertFalse(report['source_equivalence'])
        self.assertTrue(report['original_features_preserved'])
        self.assertEqual(report['test_method_inventory_sha256'],'1ff1b56f440663dc23f1bb38937252a00ee362ec082dadeaa4b1406fa398f634')
        privacy=report['approved_offline_privacy']
        self.assertEqual({r['path']:r['approved_sha256'] for r in privacy['files']},contract.REVIEWED_PRIVACY_SHA256)
        self.assertEqual(set(privacy['updated_existing_test_methods']),set(contract.PRIVACY_TESTS))
        self.assertEqual(report['project']['original_embedding'],[['CelluloidKit.framework','10'],['CelluloidPhotoExtension.appex','13']])
        self.assertFalse(report['native_execution']);self.assertFalse(report['archive_verified']);self.assertFalse(report['release_acceptance'])
        self.assertTrue(report['project']['removed_new_companion_sources'])
        self.assertTrue(all(p.startswith('Platforms/Companion/') for p in report['project']['removed_new_companion_sources']))

    def test_unrelated_source_and_every_reviewed_privacy_file_are_still_exact(self):
        original_read=Path.read_bytes
        for name in [contract.APP,'CelluloidKit/Info.plist',*sorted(contract.PRIVACY_PATHS)]:
            target=contract.ROOT/name
            replacement=target.read_bytes()+b'\n// unreviewed change\n'
            def read(path):return replacement if path==target else original_read(path)
            with self.subTest(path=name),patch.object(Path,'read_bytes',read),self.assertRaises(ValueError):
                contract.audit()

    def test_nonprivacy_sections_of_all_five_files_are_byte_preserved(self):
        for name in sorted(contract.PRIVACY_PATHS):
            before=contract.baseline(name)
            if name==contract.ENTRANCE:before=contract.projected_swift(name,before)
            after=(contract.ROOT/name).read_bytes()
            contract.privacy_preservation(name,before,after)
            # Even if a new whole-file hash were proposed, unrelated bytes reject.
            with self.subTest(path=name),self.assertRaises(ValueError):
                contract.privacy_preservation(name,before,b'// unrelated change\n'+after)
        name='CelluloidTests/EditorRegressionTests.swift'
        before=contract.baseline(name);after=(contract.ROOT/name).read_bytes()
        changed=after.replace(b'    func testPrivacyPolicyUsesApprovedHTTPSDestinationAndAccessibleControl(',
                              b'    func testUnreviewedPrivacyMethod() {}\n    func testPrivacyPolicyUsesApprovedHTTPSDestinationAndAccessibleControl(')
        with self.assertRaises(ValueError):contract.privacy_preservation(name,before,changed)

    def test_missing_extra_or_changed_privacy_bindings_and_snapshot_hashes_reject(self):
        target=contract.ROOT/'Scripts/original-ios-source-contract.json'
        original_read=Path.read_bytes;original=json.loads(target.read_bytes())
        mutations=[
            lambda value:value.pop('offline_privacy_change'),
            lambda value:value['offline_privacy_change']['files'].pop(),
            lambda value:value['offline_privacy_change']['files'].append(copy.deepcopy(value['offline_privacy_change']['files'][0])),
            lambda value:value['offline_privacy_change']['files'][0].update(approved_sha256='a'*64),
            lambda value:value['offline_privacy_change']['files'][0].update(baseline_sha256='a'*64),
            lambda value:value['offline_privacy_change']['files'][0].update(unchanged_nonprivacy_sha256='a'*64),
            lambda value:value['offline_privacy_change']['updated_existing_test_methods'].clear(),
            lambda value:value.update(fingerprint='a'*64),
        ]
        for mutation in mutations:
            value=copy.deepcopy(original);mutation(value);replacement=json.dumps(value).encode()
            def read(path):return replacement if path==target else original_read(path)
            with self.subTest(mutation=mutations.index(mutation)),patch.object(Path,'read_bytes',read),self.assertRaises(ValueError):
                contract.audit()

    def test_false_equivalence_or_omitted_privacy_report_cannot_enter_handoff(self):
        import uikit_full_shipping_handoff as handoff
        from test_original_ios_route import environment
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,environment(),clear=True):
            root=Path(folder);count,fingerprint=handoff.source_profile()
            projection=contract.audit()
            row={'source_sha':'a'*40,'file_count':count,'source_fingerprint':fingerprint,
                 'validation_route':handoff.ORIGINAL_IOS,'phase':'before','original_ios_source':projection}
            path=root/'combined-source-before.json';path.write_text(json.dumps(row))
            self.assertEqual(handoff.source_proof(root),row)
            for key,value in [('source_equivalence',True),('original_features_preserved',False),
                              ('unchanged_protected_files',543),('schema','Celluloid.OriginalIOSSource.1'),
                              ('approved_offline_privacy',{}),('original_unique_test_methods',105),
                              ('test_method_inventory_sha256','a'*64),('native_execution',True),('archive_verified',True)]:
                changed=copy.deepcopy(row);changed['original_ios_source'][key]=value;path.write_text(json.dumps(changed))
                with self.subTest(key=key),self.assertRaises(ValueError):handoff.source_proof(root)

    def test_original_source_resource_extension_settings_or_targets_cannot_be_removed(self):
        for kind in ['source','resource','extension-copy','framework-copy','setting','target','extra-target','project-ref']:
            current=dict(self.current,objects=copy.deepcopy(self.current['objects']),targetids=dict(self.current['targetids']))
            objects=current['objects'];app=objects[current['targetids']['Celluloid']]
            if kind in ['source','resource']:
                isa='PBXSourcesBuildPhase' if kind=='source' else 'PBXResourcesBuildPhase'
                phase=next(objects[p] for p in app['buildPhases'] if objects[p]['isa']==isa);phase['files'].pop()
            elif kind in ['extension-copy','framework-copy']:
                name='Embed CelluloidPhotoExtension' if kind=='extension-copy' else 'Embed CelluloidKit'
                app['buildPhases']=[p for p in app['buildPhases'] if objects[p].get('name')!=name]
            elif kind=='setting':
                config=objects[app['buildConfigurationList']]['buildConfigurations'][0];objects[config]['buildSettings']['IPHONEOS_DEPLOYMENT_TARGET']='27.0'
            elif kind=='target':current['targetids'].pop('CelluloidPhotoExtension')
            elif kind=='extra-target':objects['unexpected']={'isa':'PBXNativeTarget','name':'CelluloidWatch'}
            else:objects[current['uid']('project')]['projectReferences']=self.prior['objects'][self.prior['uid']('project')]['projectReferences']
            with self.subTest(kind=kind),self.assertRaises(ValueError):contract.validate_graph(self.prior,current)

    def test_watch_source_link_dependency_or_embedding_cannot_reenter(self):
        before=self.prior['objects'];old_app=before[self.prior['targetids']['Celluloid']]
        for kind in ['source','package','dependency','embedding']:
            current=dict(self.current,objects=copy.deepcopy(self.current['objects']))
            objects=current['objects'];app=objects[current['targetids']['Celluloid']]
            if kind=='source':
                phase=next(p for p in app['buildPhases'] if objects[p]['isa']=='PBXSourcesBuildPhase')
                objects[phase]=copy.deepcopy(before[phase])
            elif kind=='package':app['packageProductDependencies']=old_app['packageProductDependencies']
            elif kind=='dependency':app['dependencies']=old_app['dependencies']
            else:app['buildPhases']=old_app['buildPhases']
            with self.subTest(kind=kind),self.assertRaises(ValueError):contract.validate_graph(self.prior,current)

if __name__=='__main__':unittest.main()
