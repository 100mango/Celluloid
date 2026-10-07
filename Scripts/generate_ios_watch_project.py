#!/usr/bin/env python3
"""Additive iOS+Watch projection; original iOS sources/projects stay unchanged."""
from pathlib import Path
import hashlib,json,re
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
PROJECT='Celluloid-iOS-Watch.xcodeproj'
INTEGRATION='Platforms/IOSWatchIntegration'
BASE_HASHES={'Celluloid/AppDelegate.swift': '25f1674571e2e5d8974039642491287037ed18ac08eeafce439ebde37efb0e83', 'Celluloid/Controller/EntranceViewController.swift': 'e6b89f9b0bcb065f8d8e0d0bd06c42bd55ce330f2920586a6e058a0537fbbce4'}
OPERATIONS={'Celluloid/AppDelegate.swift': [['        return true', '        if UIDevice.current.userInterfaceIdiom == .phone { PhoneCompanionController.shared.activate() }\n        return true', 1]], 'Celluloid/Controller/EntranceViewController.swift': [['    private lazy var footer: UIStackView = {', '    private lazy var watchPhotosButton: UIButton = {\n        let button = UIButton(type: .system)\n        button.setTitle(NSLocalizedString("Watch Photos", comment: "Local paired Watch processing results"), for: .normal)\n        button.titleLabel?.font = .preferredFont(forTextStyle: .footnote)\n        button.titleLabel?.adjustsFontForContentSizeCategory = true\n        button.titleLabel?.numberOfLines = 0\n        button.titleLabel?.textAlignment = .center\n        button.tintColor = .white\n        button.accessibilityIdentifier = "watch-photos"\n        button.addTarget(self, action: #selector(showWatchPhotos), for: .touchUpInside)\n        return button\n    }()\n    private lazy var footer: UIStackView = {', 1], ['let buttons = [privacyPolicyButton]', 'let buttons = UIDevice.current.userInterfaceIdiom == .phone ? [watchPhotosButton, privacyPolicyButton] : [privacyPolicyButton]', 1], ['    @objc private func showPrivacyPolicy()', '    @objc private func showWatchPhotos() {\n        let results = PhoneCompanionEntryController()\n        results.modalPresentationStyle = .fullScreen\n        present(results, animated: true)\n    }\n\n    @objc private func showPrivacyPolicy()', 1]]}
COMPANION=('CompanionDeliveryGate.swift','PhoneCompanionEntryController.swift','PhoneCompanionInbox.swift','PhoneCompanionProcessor.swift','PhoneCompanionResultsView.swift','PhoneCompanionTransport.swift')
def need(ok,reason):
    if not ok:raise ValueError(reason)
def uid(key):return hashlib.sha1(key.encode()).hexdigest()[:24].upper()
def emit(v,level=0):
    if isinstance(v,dict):return '{\n'+''.join('\t'*(level+1)+json.dumps(k)+' = '+emit(x,level+1)+';\n' for k,x in v.items())+'\t'*level+'}'
    if isinstance(v,list):return '('+', '.join(emit(x,level+1) for x in v)+')'
    return json.dumps(str(v))
def generated_project(raw):
    """Parse only our deterministic quoted-key OpenStep serialization."""
    text = raw.decode('utf-8')
    need(text.startswith('// !$*UTF8*$!\n'), 'Unexpected generated project format')
    text = text.split('\n', 1)[1]
    token = re.compile(r'\s*("(?:\\.|[^"\\])*"|[{}()=;,]|[0-9]+)')
    tokens, at = [], 0
    while at < len(text) and text[at:].strip():
        found = token.match(text, at)
        need(found is not None, 'Invalid generated project token')
        tokens.append(found.group(1)); at = found.end()
    cursor = 0
    def take():
        nonlocal cursor
        need(cursor < len(tokens), 'Truncated generated project')
        item = tokens[cursor]; cursor += 1; return item
    def value(depth=0):
        need(depth < 32, 'Generated project nesting too deep')
        item = take()
        if item == '{':
            result = {}
            while tokens[cursor] != '}':
                key = json.loads(take()); need(key not in result, 'Duplicate project key')
                need(take() == '=', 'Missing project assignment')
                result[key] = value(depth + 1); need(take() == ';', 'Missing project terminator')
            take(); return result
        if item == '(':
            result = []
            while tokens[cursor] != ')':
                result.append(value(depth + 1))
                need(cursor < len(tokens), 'Truncated project array')
                if tokens[cursor] != ')':
                    need(take() == ',', 'Missing project separator')
            take(); return result
        return json.loads(item)
    try:
        result = value()
    except (IndexError, json.JSONDecodeError) as error:
        raise ValueError('Malformed generated project') from error
    need(cursor == len(tokens), 'Trailing generated project tokens')
    return result

def projected_sources(root=ROOT):
    result={}
    for path,operations in OPERATIONS.items():
        raw=(root/path).read_bytes();need(hashlib.sha256(raw).hexdigest()==BASE_HASHES[path],'qualified original changed: '+path)
        text=raw.decode()
        for old,new,count in operations:
            need(text.count(old)==count,'integration anchor mismatch: '+path);text=text.replace(old,new)
        result[INTEGRATION+'/'+Path(path).name]=text
    return result

def projection(root=ROOT):
    project=generated_project((root/'Celluloid.xcodeproj/project.pbxproj').read_bytes());o=project['objects']
    def add(key,isa,**fields):
        ident=uid(key);need(ident not in o,'duplicate projection object: '+key);o[ident]=dict(isa=isa,**fields);return ident
    main=o[o[project['rootObject']]['mainGroup']];app=o[uid('target:Celluloid')]
    source=o[uid('phase:CelluloidSources')];frameworks=o[uid('phase:CelluloidFrameworks')]
    for path in OPERATIONS:o[uid('file:'+path)]['path']=INTEGRATION+'/'+Path(path).name
    for name in COMPANION:
        path='Platforms/Companion/'+name;ref=add('file:'+path,'PBXFileReference',lastKnownFileType='sourcecode.swift',path=path,sourceTree='<group>');main['children'].append(ref)
        source['files'].append(add('build:Celluloid:'+path,'PBXBuildFile',fileRef=ref))
    for package_name,product_name in [('CelluloidCore','CelluloidDomain'),('CelluloidRendering','CelluloidRendering')]:
        ref=add('native-package:'+package_name,'XCLocalSwiftPackageReference',relativePath='Packages/'+package_name)
        o[project['rootObject']]['packageReferences'].append(ref)
        dep=add('native-package-product:Celluloid:'+product_name,'XCSwiftPackageProductDependency',package=ref,productName=product_name)
        app['packageProductDependencies'].append(dep)
        frameworks['files'].append(add('native-package-link:Celluloid:'+product_name,'PBXBuildFile',productRef=dep))
    native=add('file:CelluloidNative.xcodeproj','PBXFileReference',lastKnownFileType='wrapper.pb-project',path='CelluloidNative.xcodeproj',sourceTree='<group>');main['children'].append(native)
    nu=lambda key:hashlib.sha1(('celluloid-native:'+key).encode()).hexdigest()[:24].upper()
    proxy=add('watch-product-proxy','PBXContainerItemProxy',containerPortal=native,proxyType='2',remoteGlobalIDString=nu('product:CelluloidWatch'),remoteInfo='CelluloidWatch')
    product=add('watch-product-reference','PBXReferenceProxy',fileType='wrapper.application',path='CelluloidWatch.app',remoteRef=proxy,sourceTree='BUILT_PRODUCTS_DIR')
    products=add('native-products','PBXGroup',name='Products',children=[product],sourceTree='<group>')
    target=add('watch-target-proxy','PBXContainerItemProxy',containerPortal=native,proxyType='1',remoteGlobalIDString=nu('target:CelluloidWatch'),remoteInfo='CelluloidWatch')
    app['dependencies'].insert(0,add('watch-target-dependency','PBXTargetDependency',name='CelluloidWatch',targetProxy=target))
    build=add('embed-native-watch','PBXBuildFile',fileRef=product,settings=dict(ATTRIBUTES=['RemoveHeadersOnCopy']))
    app['buildPhases'].append(add('embed-native-watch-phase','PBXCopyFilesBuildPhase',buildActionMask='2147483647',dstPath='$(CONTENTS_FOLDER_PATH)/Watch',dstSubfolderSpec='16',files=[build],name='Embed Watch Content',runOnlyForDeploymentPostprocessing='0'))
    o[project['rootObject']]['projectReferences']=[dict(ProductGroup=products,ProjectRef=native)]
    return project

def generate(root=ROOT):
    target=root/PROJECT;(target/'xcshareddata/xcschemes').mkdir(parents=True,exist_ok=True)
    for path,text in projected_sources(root).items():
        p=root/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
    (target/'project.pbxproj').write_text('// !$*UTF8*$!\n'+emit(projection(root))+'\n')
    scheme=ET.parse(root/'Celluloid.xcodeproj/xcshareddata/xcschemes/Celluloid.xcscheme')
    for ref in scheme.iter('BuildableReference'):ref.set('ReferencedContainer','container:'+PROJECT)
    ET.indent(scheme);scheme.write(target/'xcshareddata/xcschemes/Celluloid.xcscheme',encoding='UTF-8',xml_declaration=True)
    workspace=target/'project.xcworkspace';workspace.mkdir(exist_ok=True)
    (workspace/'contents.xcworkspacedata').write_text('<?xml version="1.0" encoding="UTF-8"?><Workspace version="1.0"><FileRef location="self:"/></Workspace>\n')
    resolved=workspace/'xcshareddata/swiftpm/Package.resolved';resolved.parent.mkdir(parents=True,exist_ok=True)
    resolved.write_bytes((root/'Celluloid.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved').read_bytes())

if __name__=='__main__':generate()
