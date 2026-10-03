#!/usr/bin/env python3
"""Generate isolated, unsigned native targets. Never edits the shipping iOS project."""
from pathlib import Path
import hashlib,json,plistlib
ROOT=Path(__file__).resolve().parents[1]
objects={};children=[]
def uid(key): return hashlib.sha1(('celluloid-native:'+key).encode()).hexdigest()[:24].upper()
def add(key,isa,**values):
    i=uid(key); objects[i]={'isa':isa,**values}; return i
def encode(v,level=0):
    if isinstance(v,dict): return '{\n'+''.join('\t'*(level+1)+json.dumps(k)+' = '+encode(x,level+1)+';\n' for k,x in v.items())+'\t'*level+'}'
    if isinstance(v,list): return '('+', '.join(encode(x,level+1) for x in v)+')'
    return json.dumps(str(v))
def configs(key,settings):
    result=[]
    for name in ['Debug','Release']:
        values=dict(settings,SWIFT_OPTIMIZATION_LEVEL='-Onone' if name=='Debug' else '-O')
        if name=='Debug': values.update(ENABLE_TESTABILITY='YES',SWIFT_ACTIVE_COMPILATION_CONDITIONS='DEBUG',ONLY_ACTIVE_ARCH='YES')
        result.append(add(key+name,'XCBuildConfiguration',name=name,buildSettings=values))
    return add(key+'configs','XCConfigurationList',buildConfigurations=result,defaultConfigurationIsVisible='0',defaultConfigurationName='Release')
def reference(path):
    i=uid(path)
    if i not in objects:
        add(path,'PBXFileReference',lastKnownFileType='sourcecode.swift' if path.endswith('.swift') else 'text.plist.xml',path=path,sourceTree='<group>');children.append(i)
    return i
packages={name:add('package:'+name,'XCLocalSwiftPackageReference',relativePath='Packages/'+name) for name in ['CelluloidCore','CelluloidRendering']}
targets={};products={}
settings_by_name={
    'CelluloidMac':dict(SDKROOT='macosx',SUPPORTED_PLATFORMS='macosx',MACOSX_DEPLOYMENT_TARGET='13.0'),
    'CelluloidVision':dict(SDKROOT='xros',SUPPORTED_PLATFORMS='xros xrsimulator',XROS_DEPLOYMENT_TARGET='1.0',TARGETED_DEVICE_FAMILY='7'),
    'CelluloidMacUITests':dict(SDKROOT='macosx',SUPPORTED_PLATFORMS='macosx',MACOSX_DEPLOYMENT_TARGET='14.0',TEST_TARGET_NAME='CelluloidMac',GENERATE_INFOPLIST_FILE='YES'),
    'CelluloidMacTests':dict(SDKROOT='macosx',SUPPORTED_PLATFORMS='macosx',MACOSX_DEPLOYMENT_TARGET='14.0',TEST_HOST='$(BUILT_PRODUCTS_DIR)/CelluloidMac.app/Contents/MacOS/CelluloidMac',BUNDLE_LOADER='$(TEST_HOST)',GENERATE_INFOPLIST_FILE='YES')
}
for name in settings_by_name:
    tests=name.endswith('Tests'); ext='xctest' if tests else 'app'
    products[name]=add('product:'+name,'PBXFileReference',explicitFileType='wrapper.cfbundle' if tests else 'wrapper.application',path=name+'.'+ext,sourceTree='BUILT_PRODUCTS_DIR',includeInIndex='0')
    targets[name]=uid('target:'+name)
for name,platform in settings_by_name.items():
    tests=name.endswith('Tests')
    paths=list((ROOT/'Platforms'/('UITests' if name.endswith('UITests') else 'Tests' if tests else 'Shared')).glob('*.swift'))
    if not tests: paths+=list((ROOT/'Platforms'/('macOS' if name=='CelluloidMac' else 'visionOS')).glob('*.swift'))
    localized=[]
    if not tests:
        language_refs=[]
        for language in ['en','zh-Hans']:
            path='Platforms/Resources/'+language+'.lproj/Localizable.strings'
            language_ref=reference(path);objects[language_ref]['name']=language
            if language_ref in children:children.remove(language_ref)
            language_refs.append(language_ref)
        variant=add('variant:'+name,'PBXVariantGroup',children=language_refs,name='Localizable.strings',sourceTree='<group>');children.append(variant)
        localized.append(add('build:localization:'+name,'PBXBuildFile',fileRef=variant))
    source=[add('build:'+name+p.relative_to(ROOT).as_posix(),'PBXBuildFile',fileRef=reference(p.relative_to(ROOT).as_posix())) for p in sorted(paths)]
    links=[];deps=[];package_deps=[]
    for package,product in [('CelluloidCore','CelluloidDomain'),('CelluloidRendering','CelluloidRendering')]:
        dep=add('product:'+name+product,'XCSwiftPackageProductDependency',package=packages[package],productName=product)
        package_deps.append(dep);links.append(add('link:'+name+product,'PBXBuildFile',productRef=dep))
    if tests:
        proxy=add('proxy:'+name,'PBXContainerItemProxy',containerPortal=uid('project'),proxyType='1',remoteGlobalIDString=targets['CelluloidMac'],remoteInfo='CelluloidMac')
        deps.append(add('dependency:'+name,'PBXTargetDependency',target=targets['CelluloidMac'],targetProxy=proxy))
    settings=dict(PRODUCT_NAME='$(TARGET_NAME)',PRODUCT_BUNDLE_IDENTIFIER='Mango.Celluloid.'+name if tests else 'Mango.Celluloid',SWIFT_VERSION='5.0',SWIFT_STRICT_CONCURRENCY='minimal',CODE_SIGNING_ALLOWED='NO',CODE_SIGNING_REQUIRED='NO',CODE_SIGN_IDENTITY='',CURRENT_PROJECT_VERSION='2',MARKETING_VERSION='2.0',ENABLE_USER_SCRIPT_SANDBOXING='YES',LD_RUNPATH_SEARCH_PATHS=['$(inherited)','@executable_path/Frameworks','@executable_path/../Frameworks'],**platform)
    if not tests: settings['INFOPLIST_FILE']='Platforms/'+('macOS' if name=='CelluloidMac' else 'visionOS')+'/Info.plist'
    phases=[add('phase:'+name+kind,'PBX'+kind+'BuildPhase',buildActionMask='2147483647',files=files,runOnlyForDeploymentPostprocessing='0') for kind,files in [('Sources',source),('Frameworks',links),('Resources',localized)]]
    add('target:'+name,'PBXNativeTarget',name=name,productName=name,productReference=products[name],productType='com.apple.product-type.'+('bundle.ui-testing' if name.endswith('UITests') else 'bundle.unit-test' if tests else 'application'),buildConfigurationList=configs(name,settings),buildPhases=phases,buildRules=[],dependencies=deps,packageProductDependencies=package_deps)
prodgroup=add('products','PBXGroup',name='Products',children=list(products.values()),sourceTree='<group>')
root=add('root','PBXGroup',children=children+[prodgroup],sourceTree='<group>')
add('project','PBXProject',attributes={'LastUpgradeCheck':'2700','BuildIndependentTargetsInParallel':'YES','TargetAttributes':{targets['CelluloidMacTests']:{'TestTargetID':targets['CelluloidMac']},targets['CelluloidMacUITests']:{'TestTargetID':targets['CelluloidMac']}}},buildConfigurationList=configs('project',{'CLANG_ENABLE_MODULES':'YES','CLANG_ENABLE_OBJC_ARC':'YES','SWIFT_VERSION':'5.0'}),compatibilityVersion='Xcode 14.0',developmentRegion='en',hasScannedForEncodings='0',knownRegions=['en','zh-Hans'],mainGroup=root,productRefGroup=prodgroup,projectDirPath='',projectRoot='',targets=list(targets.values()),packageReferences=list(packages.values()))
project=ROOT/'CelluloidNative.xcodeproj';project.mkdir(exist_ok=True)
(project/'project.pbxproj').write_text('// !$*UTF8*$!\n'+encode({'archiveVersion':'1','classes':{},'objectVersion':'56','objects':objects,'rootObject':uid('project')})+'\n')
for name in ['CelluloidMac','CelluloidVision','CelluloidMacUI']:
    folder=project/'xcshareddata/xcschemes';folder.mkdir(parents=True,exist_ok=True)
    def ref(n):return f'<BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{targets[n]}" BuildableName="{n}.{"xctest" if n.endswith("Tests") else "app"}" BlueprintName="{n}" ReferencedContainer="container:CelluloidNative.xcodeproj"/>'
    app_name='CelluloidMac' if name=='CelluloidMacUI' else name
    test_name='CelluloidMacUITests' if name=='CelluloidMacUI' else 'CelluloidMacTests'
    tests='<TestableReference skipped="NO">'+ref(test_name)+'</TestableReference>' if name in ['CelluloidMac','CelluloidMacUI'] else ''
    environment='<EnvironmentVariables><EnvironmentVariable key="CELLULOID_EXPECTED_APP_PATH" value="$(BUILT_PRODUCTS_DIR)/CelluloidMac.app" isEnabled="YES"/></EnvironmentVariables>' if name in ['CelluloidMac','CelluloidMacUI'] else ''
    (folder/(name+'.xcscheme')).write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<Scheme LastUpgradeVersion="2700" version="1.3"><BuildAction parallelizeBuildables="YES" buildImplicitDependencies="YES"><BuildActionEntries><BuildActionEntry buildForTesting="YES" buildForRunning="YES" buildForProfiling="YES" buildForArchiving="YES" buildForAnalyzing="YES">{ref(app_name)}</BuildActionEntry></BuildActionEntries></BuildAction><TestAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" shouldUseLaunchSchemeArgsEnv="NO"><MacroExpansion>{ref(app_name)}</MacroExpansion><Testables>{tests}</Testables>{environment}</TestAction><LaunchAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB"><BuildableProductRunnable runnableDebuggingMode="0">{ref(app_name)}</BuildableProductRunnable></LaunchAction><ProfileAction buildConfiguration="Release" shouldUseLaunchSchemeArgsEnv="YES"><BuildableProductRunnable runnableDebuggingMode="0">{ref(app_name)}</BuildableProductRunnable></ProfileAction><AnalyzeAction buildConfiguration="Debug"/><ArchiveAction buildConfiguration="Release" revealArchiveInOrganizer="YES"/></Scheme>\n''')
for platform in ['macOS','visionOS']:
    info={'CFBundleIdentifier':'$(PRODUCT_BUNDLE_IDENTIFIER)','CFBundleName':'Celluloid','CFBundleExecutable':'$(EXECUTABLE_NAME)','CFBundlePackageType':'APPL','CFBundleVersion':'$(CURRENT_PROJECT_VERSION)','CFBundleShortVersionString':'$(MARKETING_VERSION)','NSHumanReadableCopyright':'Copyright © Mango. See bundled LICENSE.txt.','CFBundleDocumentTypes':[{'CFBundleTypeName':'Celluloid Document','CFBundleTypeRole':'Editor','LSHandlerRank':'Owner','LSItemContentTypes':['Mango.Celluloid.document']}],'UTExportedTypeDeclarations':[{'UTTypeIdentifier':'Mango.Celluloid.document','UTTypeDescription':'Celluloid Editable Document','UTTypeConformsTo':['com.apple.package'],'UTTypeTagSpecification':{'public.filename-extension':['celluloid']}}]}
    if platform=='macOS': info.update(LSMinimumSystemVersion='$(MACOSX_DEPLOYMENT_TARGET)',NSPrincipalClass='NSApplication')
    else: info.update(UIApplicationSceneManifest={'UIApplicationSupportsMultipleScenes':True},UILaunchScreen={})
    with open(ROOT/'Platforms'/platform/'Info.plist','wb') as f: plistlib.dump(info,f,sort_keys=True)
print('Generated CelluloidNative.xcodeproj (unsigned native Mac + visionOS; original iOS project untouched)')
