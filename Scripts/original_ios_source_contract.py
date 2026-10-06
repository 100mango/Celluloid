"""Fixed original-iOS package projection; source proof only, never runtime acceptance."""
from pathlib import Path
import ast,copy,hashlib,json,subprocess

ROOT=Path(__file__).resolve().parents[1]
BASE='4c0c6cb3314cd89e41fc9cfc67b833aca7de7d56'
TARGETS={'Celluloid','CelluloidKit','CelluloidPhotoExtension','CelluloidTests','CelluloidUITests'}
REMOVED_SCHEME='Celluloid.xcodeproj/xcshareddata/xcschemes/CelluloidCompanion.xcscheme'
APP='Celluloid/AppDelegate.swift'
ENTRANCE='Celluloid/Controller/EntranceViewController.swift'
PROJECT='Celluloid.xcodeproj/project.pbxproj'

def need(value,message):
    if not value:raise ValueError(message)

def baseline(path,root=ROOT):
    return subprocess.check_output(['git','show',BASE+':'+path],cwd=root)

def graph(source,root=ROOT):
    # Existing deterministic generator, evaluated without its top-level writes.
    # The emitted complete project must still match the actual pinned/project bytes.
    tree=ast.parse(source)
    kept=[]
    for node in tree.body:
        if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Attribute) and node.value.func.attr in {'write_text','mkdir'}:
            continue
        if isinstance(node,ast.If) and isinstance(node.test,ast.Call) and isinstance(node.test.func,ast.Attribute) and isinstance(node.test.func.value,ast.Name) and node.test.func.value.id=='companion_scheme' and node.test.func.attr=='exists':
            need(len(node.body)==1 and isinstance(node.body[0],ast.Expr) and isinstance(node.body[0].value,ast.Call) and isinstance(node.body[0].value.func,ast.Attribute) and node.body[0].value.func.attr=='unlink','Unexpected generator cleanup')
            continue
        kept.append(node)
    namespace={'__file__':str(Path(root)/'Scripts/generate_project.py')}
    exec(compile(ast.Module(body=kept,type_ignores=[]),'fixed-project-generator','exec'),namespace)
    return namespace

def emitted(g):
    return ('// !$*UTF8*$!\n'+g['emit']({'archiveVersion':'1','classes':{},'objectVersion':'56','objects':g['objects'],'rootObject':g['uid']('project')})+'\n').encode()

def compiled_paths(g,target):
    o=g['objects'];node=o[g['targetids'][target]]
    phase=next(o[p] for p in node['buildPhases'] if o[p]['isa']=='PBXSourcesBuildPhase')
    return [o[o[b]['fileRef']]['path'] for b in phase['files']]

def validate_graph(prior,current):
    before=prior['objects'];after=current['objects']
    need(set(current['targetids'])==TARGETS,'Original five target closure changed')
    need({p for p,n in after.items() if n['isa']=='PBXNativeTarget'}==set(current['targetids'].values()),'Unexpected staged target object')
    project=copy.deepcopy(before[prior['uid']('project')])
    removed_targets=set(prior['targetids'].values())-set(current['targetids'].values())
    project['targets']=[p for p in project['targets'] if p not in removed_targets]
    project['attributes']['TargetAttributes']={p:v for p,v in project['attributes']['TargetAttributes'].items() if p not in removed_targets}
    project['packageReferences']=[p for p in project['packageReferences'] if before[p]['isa']=='XCRemoteSwiftPackageReference']
    project.pop('projectReferences')
    need(after[current['uid']('project')]==project,'Staged project root changes exceed new Watch isolation')
    new_packages={'CelluloidDomain','CelluloidRendering'}
    removed_sources=[]
    for name in sorted(TARGETS):
        identifier=prior['targetids'][name]
        need(current['targetids'][name]==identifier,'Original target identity changed')
        expected=copy.deepcopy(before[identifier]);actual=after[identifier]
        if name=='Celluloid':
            expected['dependencies']=[p for p in expected['dependencies'] if before[p].get('name')!='CelluloidWatch']
            expected['buildPhases']=[p for p in expected['buildPhases'] if before[p].get('name')!='Embed Watch Content']
            expected['packageProductDependencies']=[p for p in expected['packageProductDependencies'] if before[p].get('productName') not in new_packages]
        need(actual==expected,'Original target semantics changed: '+name)
        config=actual['buildConfigurationList'];need(after[config]==before[config],'Original configuration list changed')
        for p in after[config]['buildConfigurations']:need(after[p]==before[p],'Original build settings changed: '+name)
        for p in actual['buildPhases']:
            phase=copy.deepcopy(before[p])
            if name=='Celluloid' and phase['isa']=='PBXSourcesBuildPhase':
                removed=[b for b in phase['files'] if before[before[b]['fileRef']]['path'].startswith('Platforms/Companion/')]
                removed_sources=[before[before[b]['fileRef']]['path'] for b in removed]
                need(removed_sources,'Missing original new-companion projection')
                phase['files']=[b for b in phase['files'] if b not in removed]
            if name=='Celluloid' and phase['isa']=='PBXFrameworksBuildPhase':
                phase['files']=[b for b in phase['files'] if before[b].get('productRef') is None or before[before[b]['productRef']].get('productName') not in new_packages]
            need(after[p]==phase,'Original source/resource/link phase changed: '+name)
            for b in phase['files']:
                need(after[b]==before[b],'Original build-file attributes changed')
                if 'fileRef' in after[b]:need(after[after[b]['fileRef']]==before[before[b]['fileRef']],'Original file reference changed')
    node=after[current['targetids']['Celluloid']]
    embeds=[after[p] for p in node['buildPhases'] if after[p]['isa']=='PBXCopyFilesBuildPhase']
    copies={(after[after[p['files'][0]]['fileRef']]['path'],p['dstSubfolderSpec']) for p in embeds}
    need(copies=={('CelluloidKit.framework','10'),('CelluloidPhotoExtension.appex','13')} and len(embeds)==2,'Original framework/Photos extension embedding is not exact')
    need(not any(n.get('isa') in {'PBXReferenceProxy','XCLocalSwiftPackageReference'} for n in after.values()),'New Watch/package reference remains in staged project')
    need(not any(n.get('path','').startswith('Platforms/Companion/') for n in after.values()),'Companion implementation remains compiled/referenced')
    return {'targets':sorted(TARGETS),'removed_new_companion_sources':removed_sources,'original_embedding':sorted([list(x) for x in copies]),
            'original_compiled_sources':{name:compiled_paths(current,name) for name in sorted(TARGETS)}}

def projected_swift(path,data):
    text=data.decode()
    if path==APP:
        line='        if UIDevice.current.userInterfaceIdiom == .phone { PhoneCompanionController.shared.activate() }\n'
        need(text.count(line)==1,'Ambiguous new companion activation')
        return text.replace(line,'').encode()
    need(path==ENTRANCE,'Unknown Swift projection')
    start='    private lazy var watchPhotosButton: UIButton = {'
    end='    private lazy var footer: UIStackView = {'
    need(text.count(start)==text.count(end)==1,'Ambiguous new Watch button')
    a=text.index(start);b=text.index(end,a);text=text[:a]+text[b:]
    old='let buttons = UIDevice.current.userInterfaceIdiom == .phone ? [watchPhotosButton, privacyPolicyButton] : [privacyPolicyButton]'
    need(text.count(old)==1,'Ambiguous new Watch footer entry');text=text.replace(old,'let buttons = [privacyPolicyButton]')
    start='    @objc private func showWatchPhotos() {';end='    @objc private func showPrivacyPolicy()'
    need(text.count(start)==text.count(end)==1,'Ambiguous new Watch navigation')
    a=text.index(start);b=text.index(end,a)
    return (text[:a]+text[b:]).encode()

def audit(root=ROOT):
    root=Path(root)
    frozen=baseline('Scripts/combined-source-contract.json',root)
    need((root/'Scripts/combined-source-contract.json').read_bytes()==frozen,'Historical full-source snapshot changed')
    contract=json.loads(frozen);need(len(contract['files'])==547,'Unexpected baseline membership')
    unchanged=[]
    for path,digest in contract['files']:
        if path==REMOVED_SCHEME:
            need(not (root/path).exists() and not (root/path).is_symlink(),'New shipping-companion scheme remains')
        elif path in {APP,ENTRANCE}:
            need((root/path).read_bytes()==projected_swift(path,baseline(path,root)),'Original app feature changed beyond Watch isolation: '+path)
        elif path!=PROJECT:
            need((root/path).is_file() and not (root/path).is_symlink() and hashlib.sha256((root/path).read_bytes()).hexdigest()==digest,'Original/full-platform source changed: '+path)
            unchanged.append(path)
    prior=graph(baseline('Scripts/generate_project.py',root),root)
    need(emitted(prior)==baseline(PROJECT,root),'Pinned baseline generator/project differ')
    current=graph((root/'Scripts/generate_project.py').read_bytes(),root)
    need(emitted(current)==(root/PROJECT).read_bytes(),'Staged generator is not reproducible')
    report=validate_graph(prior,current)
    # No original XCTest source, method or selection changes are required.
    from uikit_full_shipping_gate import source_inventory,ROW_COUNTS
    cases=source_inventory(root)
    return {'schema':'Celluloid.OriginalIOSSource.1','baseline':BASE,'unchanged_protected_files':len(unchanged),
            'original_unique_test_methods':len(cases),'original_row_invocations':ROW_COUNTS,'original_total_invocations':sum(ROW_COUNTS.values()),
            'project':report,'source_equivalence':True,'native_execution':False,'archive_verified':False,'release_acceptance':False,
            'scope':'Only new Watch/phone-companion integration is removed from the original iOS target; actual staged package still needs full runtime and archive validation'}

if __name__=='__main__':print(json.dumps(audit(),indent=2,sort_keys=True))
