"""Source/project equivalence only; actual archive and device tests remain mandatory."""
import copy,unittest
import original_ios_source_contract as contract

class OriginalIOSSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prior=contract.graph(contract.baseline('Scripts/generate_project.py'))
        cls.current=contract.graph((contract.ROOT/'Scripts/generate_project.py').read_bytes())

    def test_original_features_resources_tests_and_embedding_are_preserved(self):
        report=contract.audit()
        self.assertEqual(report['unchanged_protected_files'],543)
        self.assertEqual(report['original_unique_test_methods'],106)
        self.assertEqual(report['original_total_invocations'],412)
        self.assertEqual(report['project']['original_embedding'],[['CelluloidKit.framework','10'],['CelluloidPhotoExtension.appex','13']])
        self.assertFalse(report['native_execution']);self.assertFalse(report['archive_verified']);self.assertFalse(report['release_acceptance'])
        self.assertTrue(report['project']['removed_new_companion_sources'])
        self.assertTrue(all(p.startswith('Platforms/Companion/') for p in report['project']['removed_new_companion_sources']))

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
