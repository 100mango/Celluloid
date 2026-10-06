"""Exact original-iOS preservation and approved privacy delta, never runtime proof."""
from pathlib import Path
import ast,copy,hashlib,json,re,subprocess

ROOT=Path(__file__).resolve().parents[1]
BASE='4c0c6cb3314cd89e41fc9cfc67b833aca7de7d56'
TARGETS={'Celluloid','CelluloidKit','CelluloidPhotoExtension','CelluloidTests','CelluloidUITests'}
REMOVED_SCHEME='Celluloid.xcodeproj/xcshareddata/xcschemes/CelluloidCompanion.xcscheme'
APP='Celluloid/AppDelegate.swift'
ENTRANCE='Celluloid/Controller/EntranceViewController.swift'
PROJECT='Celluloid.xcodeproj/project.pbxproj'
PRIVACY_TESTS={
    'CelluloidTests/EditorRegressionTests.swift':('testPrivacyPolicyUsesApprovedHTTPSDestinationAndAccessibleControl','testHomeLayoutDoesNotCollapseOrOverlapAcrossPhoneAndPadSizes'),
    'CelluloidUITests/CelluloidUITests.swift':('testPrivacyPolicyEntryRemainsAccessibleAndCanClose','testDeniedPhotosShowsRecoveryAndCanCancelRepeatedly'),
}
PRIVACY_LOCALIZATIONS={'Celluloid/en.lproj/Localizable.strings','Celluloid/zh-Hans.lproj/Localizable.strings'}
PRIVACY_PATHS={ENTRANCE,*PRIVACY_TESTS,*PRIVACY_LOCALIZATIONS}
PRIVACY_KEYS=['Close','Shows the privacy policy offline.','Open in External Browser',
              'Opens GitHub Pages, which logs your IP address.','privacy-policy.offline-body']
PRIVACY_SCHEMA='Celluloid.OfflinePrivacyChange.1'
# This is one approved change, not an allowlist for future privacy-file edits.
REVIEWED_PRIVACY_SHA256={
    ENTRANCE:'e6b89f9b0bcb065f8d8e0d0bd06c42bd55ce330f2920586a6e058a0537fbbce4',
    'Celluloid/en.lproj/Localizable.strings':'a8c3996e6247440cfb225d5a225a03839c80d147e3105edbb0f77c15148344ed',
    'Celluloid/zh-Hans.lproj/Localizable.strings':'1070e225ed1ccad4e591d95be8133cf489b86679999557fe5e82da7cb2d54c55',
    'CelluloidTests/EditorRegressionTests.swift':'558db7be201497c738a30aeab15922a33d61495f041ff9b964845c6c7af7ee24',
    'CelluloidUITests/CelluloidUITests.swift':'94f9fffbbf2693038fe85867bd31426959bf099af7f05b681182ef6e97361256',
}

def need(value,message):
    if not value:raise ValueError(message)

def baseline(path,root=ROOT):
    return subprocess.check_output(['git','show',BASE+':'+path],cwd=root)

def digest(data):return hashlib.sha256(data).hexdigest()

def exact_replace(data,old,new):
    need(data.count(old)==1,'Ambiguous reviewed privacy replacement')
    return data.replace(old,new)

def outside_section(data,start,end):
    need(data.count(start)==data.count(end)==1,'Ambiguous reviewed privacy section')
    a=data.index(start);b=data.index(end,a)
    return data[:a]+b'/* fixed reviewed privacy section */\n'+data[b:]

def privacy_preservation(path,before,after):
    """Prove exact original bytes outside these five bounded, reviewed edits."""
    if path==ENTRANCE:
        old=exact_replace(before,b'import SafariServices\n',b'')
        old=exact_replace(old,b'        button.accessibilityHint = NSLocalizedString("Opens the app privacy policy.", comment: "Privacy link accessibility hint")\n',b'')
        new=exact_replace(after,b'        button.accessibilityHint = NSLocalizedString("Shows the privacy policy offline.", comment: "Privacy entry accessibility hint")\n',b'')
        old=exact_replace(old,b'    @objc private func showPrivacyPolicy() {\n        let policy = SFSafariViewController(url: AppLinks.privacyPolicyURL)\n        policy.dismissButtonStyle = .close\n        present(policy, animated: true)\n    }\n',b'')
        new=exact_replace(new,b'    @objc private func showPrivacyPolicy() {\n        let navigation = UINavigationController(rootViewController: PrivacyPolicyViewController())\n        navigation.modalPresentationStyle = .fullScreen\n        present(navigation, animated: true)\n    }\n',b'')
        start=b'/// Reading the bundled policy never opens a website.'
        end=b'//MARK: Action\nprivate extension Selector'
        need(new.count(start)==new.count(end)==1,'Ambiguous offline privacy controller')
        a=new.index(start);b=new.index(end,a);new=new[:a]+new[b:]
        need(old==new,'Nonprivacy entrance source changed')
        return digest(old)
    if path in PRIVACY_LOCALIZATIONS:
        need(after.startswith(before),'Existing localization bytes changed: '+path)
        suffix=after[len(before):].decode('utf8')
        prefix='\n/* Original iOS offline privacy screen. */\n'
        need(suffix.startswith(prefix),'Unexpected localization append: '+path)
        lines=suffix[len(prefix):].splitlines()
        matches=[re.fullmatch(r'"([^"\\]+)" = "(?:[^"\\]|\\.)*";',line) for line in lines]
        need(all(matches) and [m[1] for m in matches]==PRIVACY_KEYS,'Unexpected offline privacy localization keys: '+path)
        prior_keys=re.findall(rb'^"([^"\\]+)"\s*=',before,re.M)
        need(not set(key.encode() for key in PRIVACY_KEYS)&set(prior_keys),'Duplicate existing localization key')
        return digest(before)
    need(path in PRIVACY_TESTS,'Unreviewed privacy file')
    method,next_method=PRIVACY_TESTS[path]
    start=('    func '+method+'(').encode();end=('    func '+next_method+'(').encode()
    old=outside_section(before,start,end);new=outside_section(after,start,end)
    need(old==new,'Nonprivacy test source changed: '+path)
    methods=lambda data:re.findall(rb'^    func (test\w+)\s*\(',data,re.M)
    need(methods(before)==methods(after),'Original privacy test method inventory changed: '+path)
    return digest(old)

def privacy_binding(root=ROOT):
    rows=[]
    for path in sorted(PRIVACY_PATHS):
        original=baseline(path,root)
        before=projected_swift(path,original) if path==ENTRANCE else original
        after=(Path(root)/path).read_bytes()
        need(digest(after)==REVIEWED_PRIVACY_SHA256[path],'Changed reviewed offline privacy source: '+path)
        rows.append({'path':path,'baseline_sha256':digest(original),'pre_privacy_sha256':digest(before),
                     'approved_sha256':digest(after),'unchanged_nonprivacy_sha256':privacy_preservation(path,before,after)})
    return {'schema':PRIVACY_SCHEMA,'baseline':BASE,'files':rows,
            'updated_existing_test_methods':{path:names[0] for path,names in PRIVACY_TESTS.items()},
            'appended_localization_keys':PRIVACY_KEYS,
            'scope':'Bundled offline privacy policy with an explicit external-browser action; no other original feature or test-method change'}

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
    staged=json.loads((root/'Scripts/original-ios-source-contract.json').read_bytes())
    need(staged['schema']=='Celluloid.OriginalIOSProtectedSource.1' and staged['roots']==contract['roots'],'Unexpected staged source profile')
    need([p for p,_ in staged['files']]==[p for p,_ in contract['files'] if p!=REMOVED_SCHEME],'Unexpected staged protected membership')
    need(len(staged['files'])==546 and digest(json.dumps(staged['files'],separators=(',',':')).encode())==staged['fingerprint'],'Changed staged source fingerprint')
    privacy=privacy_binding(root)
    need(staged.get('offline_privacy_change')==privacy,'Missing or changed exact approved offline privacy binding')
    unchanged=[];actual=[]
    for path,expected_digest in contract['files']:
        if path==REMOVED_SCHEME:
            need(not (root/path).exists() and not (root/path).is_symlink(),'New shipping-companion scheme remains')
            continue
        need((root/path).is_file() and not (root/path).is_symlink(),'Missing or symlinked protected source: '+path)
        data=(root/path).read_bytes();actual.append([path,hashlib.sha256(data).hexdigest()])
        if path==APP:
            need(data==projected_swift(path,baseline(path,root)),'Original app feature changed beyond Watch isolation: '+path)
        elif path not in PRIVACY_PATHS|{PROJECT}:
            need(actual[-1][1]==expected_digest,'Original/full-platform source changed: '+path)
            unchanged.append(path)
    need(actual==staged['files'],'Current protected bytes differ from approved staged snapshot')
    need(len(unchanged)==539,'Unexpected unchanged original source count')
    prior=graph(baseline('Scripts/generate_project.py',root),root)
    need(emitted(prior)==baseline(PROJECT,root),'Pinned baseline generator/project differ')
    current=graph((root/'Scripts/generate_project.py').read_bytes(),root)
    need(emitted(current)==(root/PROJECT).read_bytes(),'Staged generator is not reproducible')
    report=validate_graph(prior,current)
    # Exactly two existing privacy test bodies change; every method and row remains.
    from uikit_full_shipping_gate import source_inventory,ROW_COUNTS
    cases=source_inventory(root)
    need(len(cases)==106 and sum(ROW_COUNTS.values())==412,'Original XCTest coverage changed')
    return {'schema':'Celluloid.OriginalIOSSource.2','baseline':BASE,'unchanged_protected_files':len(unchanged),
            'protected_file_count':len(actual),'protected_source_fingerprint':staged['fingerprint'],'approved_offline_privacy':privacy,
            'original_unique_test_methods':len(cases),'original_row_invocations':ROW_COUNTS,'original_total_invocations':sum(ROW_COUNTS.values()),
            'test_method_inventory_sha256':hashlib.sha256(json.dumps(cases,separators=(',',':')).encode()).hexdigest(),
            'project':report,'source_equivalence':False,'original_features_preserved':True,
            'native_execution':False,'archive_verified':False,'release_acceptance':False,
            'scope':'Original features are preserved at source level except the approved offline privacy replacement; new Watch integration is isolated. Fresh full four-row runtime and unsigned archive validation remain mandatory'}

if __name__=='__main__':print(json.dumps(audit(),indent=2,sort_keys=True))
