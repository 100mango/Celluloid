"""Portable source/graph assertions; no runtime or Store qualification."""
from pathlib import Path
import copy,hashlib,json,tempfile,unittest
import xml.etree.ElementTree as ET
import generate_ios_watch_project as g
ROOT=Path(__file__).resolve().parents[1]

def validate(root=ROOT):
    actual=g.generated_project((root/g.PROJECT/'project.pbxproj').read_bytes());expected=g.projection(root)
    g.need(actual==expected,'fixed iOS Watch graph changed')
    for path,text in g.projected_sources(root).items():g.need((root/path).read_text()==text,'fixed integration source changed')
    objects=actual['objects'];app=objects[g.uid('target:Celluloid')]
    sources=[objects[objects[b]['fileRef']]['path'] for b in objects[g.uid('phase:CelluloidSources')]['files']]
    g.need(len(sources)==len(set(sources)),'duplicated shipping source')
    g.need({p for p in sources if p.startswith('Platforms/Companion/')}=={'Platforms/Companion/'+p for p in g.COMPANION},'wrong companion source membership')
    g.need(not any('Harness' in p for p in sources),'validation harness in real parent')
    g.need({objects[x]['productName'] for x in app['packageProductDependencies']}=={'SnapKit','CelluloidDomain','CelluloidRendering'},'shipping package products')
    watch=g.generated_project((root/'CelluloidNative.xcodeproj/project.pbxproj').read_bytes())['objects']
    dep=objects[g.uid('watch-target-dependency')];proxy=objects[dep['targetProxy']]
    target=watch[proxy['remoteGlobalIDString']];g.need(target['name']=='CelluloidWatch','external target not real Watch')
    product=objects[g.uid('watch-product-reference')];g.need(objects[product['remoteRef']]['remoteGlobalIDString']==target['productReference'] and product['path']=='CelluloidWatch.app','external product mismatch')
    phases=[objects[x] for x in app['buildPhases']]
    embeds=[x for x in phases if x['isa']=='PBXCopyFilesBuildPhase']
    g.need({x['name'] for x in embeds}=={'Embed CelluloidKit','Embed CelluloidPhotoExtension','Embed Watch Content'},'original extension/framework lost or extra embed')
    embed=objects[g.uid('embed-native-watch-phase')]
    g.need(embed['dstPath']=='$(CONTENTS_FOLDER_PATH)/Watch' and embed['dstSubfolderSpec']=='16' and len(embed['files'])==1,'Watch embed destination')
    scheme=ET.parse(root/g.PROJECT/'xcshareddata/xcschemes/Celluloid.xcscheme')
    archive=scheme.findall("./BuildAction/BuildActionEntries/BuildActionEntry[@buildForArchiving='YES']")
    g.need(len(archive)==1 and archive[0].find('BuildableReference').get('BlueprintName')=='Celluloid','only real parent archived')
    g.need(all(x.get('ReferencedContainer')=='container:'+g.PROJECT for x in scheme.iter('BuildableReference')),'scheme route mismatch')
    resolved=(root/g.PROJECT/'project.xcworkspace/xcshareddata/swiftpm/Package.resolved').read_bytes()
    g.need(resolved==(root/'Celluloid.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved').read_bytes(),'SnapKit pin changed')
    return {'sources':sources,'targets':sorted(x['name'] for x in objects.values() if x['isa']=='PBXNativeTarget')}

class ProjectionTests(unittest.TestCase):
    def test_real_fixed_graph_has_phone_watch_and_original_extension(self):
        proof=validate();self.assertEqual(proof['targets'],['Celluloid','CelluloidKit','CelluloidPhotoExtension','CelluloidTests','CelluloidUITests'])
    def test_projection_restores_only_fixed_existing_actions(self):
        for path,ops in g.OPERATIONS.items():
            value=g.projected_sources()[g.INTEGRATION+'/'+Path(path).name]
            for old,new,count in reversed(ops):
                self.assertEqual(value.count(new),count);value=value.replace(new,old)
            self.assertEqual(value,(ROOT/path).read_text())
    def test_original_offline_privacy_is_preserved_exactly(self):
        base=(ROOT/'Celluloid/Controller/EntranceViewController.swift').read_text();new=g.projected_sources()[g.INTEGRATION+'/EntranceViewController.swift']
        marker='/// Reading the bundled policy never opens a website.'
        self.assertEqual(base[base.index(marker):],new[new.index(marker):]);self.assertNotIn('import SafariServices',new)
    def test_iphone_only_activation_and_entry_scope_preserved(self):
        sources=g.projected_sources()
        self.assertIn('if UIDevice.current.userInterfaceIdiom == .phone { PhoneCompanionController.shared.activate() }',sources[g.INTEGRATION+'/AppDelegate.swift'])
        self.assertIn('UIDevice.current.userInterfaceIdiom == .phone ? [watchPhotosButton, privacyPolicyButton] : [privacyPolicyButton]',sources[g.INTEGRATION+'/EntranceViewController.swift'])
    def test_real_receiver_validation_cancel_and_explicit_save_paths_retained(self):
        sources='\n'.join((ROOT/'Platforms/Companion'/p).read_text() for p in g.COMPANION)
        for token in ('try request.validate()','Task.checkCancellation()','func saveToPhotos','PHPhotoLibrary.requestAuthorization','request.sourceSHA256','resumePending','discardPending'):
            self.assertIn(token,sources)
    def test_watch_companion_mode_and_versions_are_unmodified(self):
        import plistlib
        info=plistlib.loads((ROOT/'Platforms/watchOS/Info.plist').read_bytes());self.assertNotIn('WKRunsIndependentlyOfCompanionApp',info)
        self.assertEqual(info['WKCompanionAppBundleIdentifier'],'Mango.Celluloid');self.assertTrue(info['WKApplication'])
        native=g.generated_project((ROOT/'CelluloidNative.xcodeproj/project.pbxproj').read_bytes())['objects'];target=next(x for x in native.values() if x.get('isa')=='PBXNativeTarget' and x.get('name')=='CelluloidWatch')
        for key in native[target['buildConfigurationList']]['buildConfigurations']:
            v=native[key]['buildSettings'];self.assertEqual((v['MARKETING_VERSION'],v['CURRENT_PROJECT_VERSION'],v['WATCHOS_DEPLOYMENT_TARGET']),('1.1','2','9.0'))
    def test_reproducible_project_does_not_write_original_graph(self):
        paths=[ROOT/'Celluloid.xcodeproj/project.pbxproj',ROOT/'CelluloidNative.xcodeproj/project.pbxproj',ROOT/g.PROJECT/'project.pbxproj',*[ROOT/p for p in g.projected_sources()]]
        before={str(p):p.read_bytes() for p in paths};g.generate();self.assertEqual(before,{str(p):p.read_bytes() for p in paths})
    def test_unexpected_external_edge_harness_or_destination_is_closed(self):
        expected=g.projection()
        for object_name,key,value in [('watch-target-proxy','remoteGlobalIDString','F'*24),('watch-product-proxy','containerPortal','E'*24),('watch-product-reference','path','CelluloidPhoneCompanion.app'),('embed-native-watch-phase','dstPath','Elsewhere')]:
            wrong=copy.deepcopy(expected);wrong['objects'][g.uid(object_name)][key]=value
            with self.assertRaises(ValueError):g.need(wrong==expected,'fixed iOS Watch graph changed')
    def test_resource_contract_is_exact_source_membership(self):
        import ios_watch_unsigned_archive as m
        for target,rows in m.PACKAGE_RESOURCES.items():
            folder='CelluloidCore/Sources/CelluloidDomain/Resources' if 'CelluloidCore_' in target else 'CelluloidRendering/Sources/CelluloidRendering/Resources'
            expected={p.relative_to(ROOT/'Packages'/folder).as_posix():p.relative_to(ROOT).as_posix() for p in (ROOT/'Packages'/folder).rglob('*') if p.is_file()}
            self.assertEqual(rows,expected)
        self.assertEqual(len(m.PACKAGE_RESOURCES),3)

if __name__=='__main__':unittest.main()
