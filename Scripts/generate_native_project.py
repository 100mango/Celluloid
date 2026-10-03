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
        add(path,'PBXFileReference',lastKnownFileType='sourcecode.swift' if path.endswith('.swift') else 'text.plist.strings' if path.endswith('.strings') else 'folder.assetcatalog' if path.endswith('.xcassets') else 'text',path=path,sourceTree='<group>');children.append(i)
    return i
packages={name:add('package:'+name,'XCLocalSwiftPackageReference',relativePath='Packages/'+name) for name in ['CelluloidCore','CelluloidRendering']}
targets={};products={}
settings_by_name={
    'CelluloidWatch':dict(SDKROOT='watchos',SUPPORTED_PLATFORMS='watchos watchsimulator',WATCHOS_DEPLOYMENT_TARGET='9.0',TARGETED_DEVICE_FAMILY='4'),
    'CelluloidWatchTests':dict(SDKROOT='watchos',SUPPORTED_PLATFORMS='watchos watchsimulator',WATCHOS_DEPLOYMENT_TARGET='9.0',TARGETED_DEVICE_FAMILY='4',TEST_HOST='$(BUILT_PRODUCTS_DIR)/CelluloidWatch.app/CelluloidWatch',BUNDLE_LOADER='$(TEST_HOST)',GENERATE_INFOPLIST_FILE='YES'),
    'CelluloidWatchUITests':dict(SDKROOT='watchos',SUPPORTED_PLATFORMS='watchos watchsimulator',WATCHOS_DEPLOYMENT_TARGET='9.0',TARGETED_DEVICE_FAMILY='4',TEST_TARGET_NAME='CelluloidWatch',GENERATE_INFOPLIST_FILE='YES'),
    'CelluloidPhoneCompanion':dict(SDKROOT='iphoneos',SUPPORTED_PLATFORMS='iphoneos iphonesimulator',IPHONEOS_DEPLOYMENT_TARGET='15.0',TARGETED_DEVICE_FAMILY='1,2',SKIP_INSTALL='YES'),
    'CelluloidPhoneCompanionTests':dict(SDKROOT='iphoneos',SUPPORTED_PLATFORMS='iphoneos iphonesimulator',IPHONEOS_DEPLOYMENT_TARGET='15.0',TARGETED_DEVICE_FAMILY='1,2',TEST_HOST='$(BUILT_PRODUCTS_DIR)/CelluloidPhoneCompanion.app/CelluloidPhoneCompanion',BUNDLE_LOADER='$(TEST_HOST)',GENERATE_INFOPLIST_FILE='YES'),
    'CelluloidTV':dict(SDKROOT='appletvos',SUPPORTED_PLATFORMS='appletvos appletvsimulator',TVOS_DEPLOYMENT_TARGET='17.0',TARGETED_DEVICE_FAMILY='3'),
    'CelluloidTVTests':dict(SDKROOT='appletvos',SUPPORTED_PLATFORMS='appletvos appletvsimulator',TVOS_DEPLOYMENT_TARGET='17.0',TARGETED_DEVICE_FAMILY='3',TEST_HOST='$(BUILT_PRODUCTS_DIR)/CelluloidTV.app/CelluloidTV',BUNDLE_LOADER='$(TEST_HOST)',GENERATE_INFOPLIST_FILE='YES'),
    'CelluloidTVUITests':dict(SDKROOT='appletvos',SUPPORTED_PLATFORMS='appletvos appletvsimulator',TVOS_DEPLOYMENT_TARGET='17.0',TARGETED_DEVICE_FAMILY='3',TEST_TARGET_NAME='CelluloidTV',GENERATE_INFOPLIST_FILE='YES'),
    'CelluloidMac':dict(SDKROOT='macosx',SUPPORTED_PLATFORMS='macosx',MACOSX_DEPLOYMENT_TARGET='13.0'),
    'CelluloidVision':dict(SDKROOT='xros',SUPPORTED_PLATFORMS='xros xrsimulator',XROS_DEPLOYMENT_TARGET='1.0',TARGETED_DEVICE_FAMILY='7'),
    'CelluloidVisionTests':dict(SDKROOT='xros',SUPPORTED_PLATFORMS='xros xrsimulator',XROS_DEPLOYMENT_TARGET='1.0',TARGETED_DEVICE_FAMILY='7',TEST_HOST='$(BUILT_PRODUCTS_DIR)/CelluloidVision.app/CelluloidVision',BUNDLE_LOADER='$(TEST_HOST)',GENERATE_INFOPLIST_FILE='YES'),
    'CelluloidVisionUITests':dict(SDKROOT='xros',SUPPORTED_PLATFORMS='xros xrsimulator',XROS_DEPLOYMENT_TARGET='1.0',TARGETED_DEVICE_FAMILY='7',TEST_TARGET_NAME='CelluloidVision',GENERATE_INFOPLIST_FILE='YES'),
    'CelluloidMacUITests':dict(SDKROOT='macosx',SUPPORTED_PLATFORMS='macosx',MACOSX_DEPLOYMENT_TARGET='14.0',TEST_TARGET_NAME='CelluloidMac',GENERATE_INFOPLIST_FILE='YES'),
    'CelluloidMacTests':dict(SDKROOT='macosx',SUPPORTED_PLATFORMS='macosx',MACOSX_DEPLOYMENT_TARGET='14.0',TEST_HOST='$(BUILT_PRODUCTS_DIR)/CelluloidMac.app/Contents/MacOS/CelluloidMac',BUNDLE_LOADER='$(TEST_HOST)',GENERATE_INFOPLIST_FILE='YES')
}
for name in settings_by_name:
    tests=name.endswith('Tests'); ext='xctest' if tests else 'app'
    products[name]=add('product:'+name,'PBXFileReference',explicitFileType='wrapper.cfbundle' if tests else 'wrapper.application',path=name+'.'+ext,sourceTree='BUILT_PRODUCTS_DIR',includeInIndex='0')
    targets[name]=uid('target:'+name)
for name,platform in settings_by_name.items():
    tests=name.endswith('Tests')
    folders={'CelluloidMac':['Shared','macOS'],'CelluloidVision':['Shared','visionOS'],'CelluloidTV':['tvOS'],
             'CelluloidWatch':['watchOS'],'CelluloidPhoneCompanion':['Companion','PhoneHarness'],
             'CelluloidMacTests':['Tests'],'CelluloidMacUITests':['UITests'],
             'CelluloidVisionTests':['VisionTests'],'CelluloidVisionUITests':['VisionUITests'],
             'CelluloidTVTests':['TVTests'],'CelluloidTVUITests':['TVUITests'],
             'CelluloidWatchTests':['WatchTests'],'CelluloidWatchUITests':['WatchUITests'],
             'CelluloidPhoneCompanionTests':['PhoneTests']}
    paths=[path for folder in folders[name] for path in (ROOT/'Platforms'/folder).glob('*.swift')]
    localized=[]
    if not tests:
        if uid('variant:shared-localizations') not in objects:
            language_refs=[]
            for language in ['en','zh-Hans']:
                path='Platforms/Resources/'+language+'.lproj/Localizable.strings'
                language_ref=reference(path);objects[language_ref]['name']=language
                if language_ref in children:children.remove(language_ref)
                language_refs.append(language_ref)
            variant=add('variant:shared-localizations','PBXVariantGroup',children=language_refs,name='Localizable.strings',sourceTree='<group>');children.append(variant)
        localized.append(add('build:localization:'+name,'PBXBuildFile',fileRef=uid('variant:shared-localizations')))
        localized.append(add('build:privacy:'+name,'PBXBuildFile',fileRef=reference('Platforms/Resources/PrivacyPolicy.txt')))
    if name=='CelluloidMac':
        localized.append(add('build:mac-icon','PBXBuildFile',fileRef=reference('Platforms/macOS/Assets.xcassets')))
    source=[add('build:'+name+p.relative_to(ROOT).as_posix(),'PBXBuildFile',fileRef=reference(p.relative_to(ROOT).as_posix())) for p in sorted(paths)]
    links=[];deps=[];package_deps=[]
    for package,product in [('CelluloidCore','CelluloidDomain'),('CelluloidRendering','CelluloidRendering')]:
        if name.startswith('CelluloidWatch') and package=='CelluloidRendering':continue
        dep=add('product:'+name+product,'XCSwiftPackageProductDependency',package=packages[package],productName=product)
        package_deps.append(dep);links.append(add('link:'+name+product,'PBXBuildFile',productRef=dep))
    if tests:
        host='CelluloidWatch' if name.startswith('CelluloidWatch') else 'CelluloidPhoneCompanion' if name.startswith('CelluloidPhoneCompanion') else 'CelluloidTV' if name.startswith('CelluloidTV') else 'CelluloidVision' if name.startswith('CelluloidVision') else 'CelluloidMac'
        proxy=add('proxy:'+name,'PBXContainerItemProxy',containerPortal=uid('project'),proxyType='1',remoteGlobalIDString=targets[host],remoteInfo=host)
        deps.append(add('dependency:'+name,'PBXTargetDependency',target=targets[host],targetProxy=proxy))
    settings=dict(PRODUCT_NAME='$(TARGET_NAME)',PRODUCT_BUNDLE_IDENTIFIER='Mango.Celluloid.'+name if tests else 'Mango.Celluloid',SWIFT_VERSION='5.0',SWIFT_STRICT_CONCURRENCY='minimal',CODE_SIGNING_ALLOWED='NO',CODE_SIGNING_REQUIRED='NO',CODE_SIGN_IDENTITY='',CURRENT_PROJECT_VERSION='2',MARKETING_VERSION='2.0',ENABLE_USER_SCRIPT_SANDBOXING='YES',LD_RUNPATH_SEARCH_PATHS=['$(inherited)','@executable_path/Frameworks','@executable_path/../Frameworks'],**platform)
    if name=='CelluloidWatch':settings['PRODUCT_BUNDLE_IDENTIFIER']='Mango.Celluloid.watchkitapp'
    if name=='CelluloidMac': settings.update(ASSETCATALOG_COMPILER_APPICON_NAME='AppIcon',ENABLE_APP_SANDBOX='YES',CODE_SIGN_ENTITLEMENTS='Platforms/macOS/CelluloidMac.entitlements',CODE_SIGN_INJECT_BASE_ENTITLEMENTS='NO',ENABLE_HARDENED_RUNTIME='NO')
    if not tests: settings['INFOPLIST_FILE']='Platforms/'+('watchOS' if name=='CelluloidWatch' else 'PhoneHarness' if name=='CelluloidPhoneCompanion' else 'tvOS' if name=='CelluloidTV' else 'macOS' if name=='CelluloidMac' else 'visionOS')+'/Info.plist'
    phases=[add('phase:'+name+kind,'PBX'+kind+'BuildPhase',buildActionMask='2147483647',files=files,runOnlyForDeploymentPostprocessing='0') for kind,files in [('Sources',source),('Frameworks',links),('Resources',localized)]]
    add('target:'+name,'PBXNativeTarget',name=name,productName=name,productReference=products[name],productType='com.apple.product-type.'+('bundle.ui-testing' if name.endswith('UITests') else 'bundle.unit-test' if tests else 'application'),buildConfigurationList=configs(name,settings),buildPhases=phases,buildRules=[],dependencies=deps,packageProductDependencies=package_deps)
prodgroup=add('products','PBXGroup',name='Products',children=list(products.values()),sourceTree='<group>')
root=add('root','PBXGroup',children=children+[prodgroup],sourceTree='<group>')
add('project','PBXProject',attributes={'LastUpgradeCheck':'2700','BuildIndependentTargetsInParallel':'YES','TargetAttributes':{targets[n]:{'TestTargetID':targets['CelluloidWatch' if n.startswith('CelluloidWatch') else 'CelluloidPhoneCompanion' if n.startswith('CelluloidPhoneCompanion') else 'CelluloidTV' if n.startswith('CelluloidTV') else 'CelluloidVision' if n.startswith('CelluloidVision') else 'CelluloidMac']} for n in targets if n.endswith('Tests')}},buildConfigurationList=configs('project',{'CLANG_ENABLE_MODULES':'YES','CLANG_ENABLE_OBJC_ARC':'YES','SWIFT_VERSION':'5.0','CELLULOID_EXPECT_SANDBOX':'NO'}),compatibilityVersion='Xcode 14.0',developmentRegion='en',hasScannedForEncodings='0',knownRegions=['en','zh-Hans'],mainGroup=root,productRefGroup=prodgroup,projectDirPath='',projectRoot='',targets=list(targets.values()),packageReferences=list(packages.values()))
project=ROOT/'CelluloidNative.xcodeproj';project.mkdir(exist_ok=True)
(project/'project.pbxproj').write_text('// !$*UTF8*$!\n'+encode({'archiveVersion':'1','classes':{},'objectVersion':'56','objects':objects,'rootObject':uid('project')})+'\n')
for name in ['CelluloidMac','CelluloidVision','CelluloidMacUI','CelluloidTV','CelluloidWatch','CelluloidPhoneCompanion']:
    folder=project/'xcshareddata/xcschemes';folder.mkdir(parents=True,exist_ok=True)
    def ref(n):return f'<BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{targets[n]}" BuildableName="{n}.{"xctest" if n.endswith("Tests") else "app"}" BlueprintName="{n}" ReferencedContainer="container:CelluloidNative.xcodeproj"/>'
    app_name='CelluloidMac' if name=='CelluloidMacUI' else name
    test_name='CelluloidMacUITests' if name=='CelluloidMacUI' else 'CelluloidMacTests'
    tests='<TestableReference skipped="NO">'+ref(test_name)+'</TestableReference>' if name in ['CelluloidMac','CelluloidMacUI'] else ''
    if name=='CelluloidVision': tests=''.join('<TestableReference skipped="NO">'+ref(n)+'</TestableReference>' for n in ['CelluloidVisionTests','CelluloidVisionUITests'])
    if name=='CelluloidTV': tests=''.join('<TestableReference skipped="NO">'+ref(n)+'</TestableReference>' for n in ['CelluloidTVTests','CelluloidTVUITests'])
    if name=='CelluloidWatch': tests=''.join('<TestableReference skipped="NO">'+ref(n)+'</TestableReference>' for n in ['CelluloidWatchTests','CelluloidWatchUITests'])
    if name=='CelluloidPhoneCompanion': tests='<TestableReference skipped="NO">'+ref('CelluloidPhoneCompanionTests')+'</TestableReference>'
    environment='<EnvironmentVariables><EnvironmentVariable key="CELLULOID_EXPECTED_APP_PATH" value="$(BUILT_PRODUCTS_DIR)/CelluloidMac.app" isEnabled="YES"/><EnvironmentVariable key="CELLULOID_EXPECT_SANDBOX" value="$(CELLULOID_EXPECT_SANDBOX)" isEnabled="YES"/></EnvironmentVariables>' if name in ['CelluloidMac','CelluloidMacUI'] else ''
    (folder/(name+'.xcscheme')).write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<Scheme LastUpgradeVersion="2700" version="1.3"><BuildAction parallelizeBuildables="YES" buildImplicitDependencies="YES"><BuildActionEntries><BuildActionEntry buildForTesting="YES" buildForRunning="YES" buildForProfiling="YES" buildForArchiving="YES" buildForAnalyzing="YES">{ref(app_name)}</BuildActionEntry></BuildActionEntries></BuildAction><TestAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" shouldUseLaunchSchemeArgsEnv="NO"><MacroExpansion>{ref(app_name)}</MacroExpansion><Testables>{tests}</Testables>{environment}</TestAction><LaunchAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB"><BuildableProductRunnable runnableDebuggingMode="0">{ref(app_name)}</BuildableProductRunnable></LaunchAction><ProfileAction buildConfiguration="Release" shouldUseLaunchSchemeArgsEnv="YES"><BuildableProductRunnable runnableDebuggingMode="0">{ref(app_name)}</BuildableProductRunnable></ProfileAction><AnalyzeAction buildConfiguration="Debug"/><ArchiveAction buildConfiguration="Release" revealArchiveInOrganizer="YES"/></Scheme>\n''')
for platform in ['macOS','visionOS','tvOS','watchOS','PhoneHarness']:
    info={'CFBundleIdentifier':'$(PRODUCT_BUNDLE_IDENTIFIER)','CFBundleName':'Celluloid','CFBundleDevelopmentRegion':'en','CFBundleLocalizations':['en','zh-Hans'],'CFBundleExecutable':'$(EXECUTABLE_NAME)','CFBundlePackageType':'APPL','CFBundleVersion':'$(CURRENT_PROJECT_VERSION)','CFBundleShortVersionString':'$(MARKETING_VERSION)','NSHumanReadableCopyright':'Copyright © Mango. See bundled LICENSE.txt.','CFBundleDocumentTypes':[{'CFBundleTypeName':'Celluloid Document','CFBundleTypeRole':'Editor','LSHandlerRank':'Owner','LSItemContentTypes':['Mango.Celluloid.document']}],'UTExportedTypeDeclarations':[{'UTTypeIdentifier':'Mango.Celluloid.document','UTTypeDescription':'Celluloid Editable Document','UTTypeConformsTo':['com.apple.package'],'UTTypeTagSpecification':{'public.filename-extension':['celluloid']}}]}
    if platform=='macOS': info.update(LSMinimumSystemVersion='$(MACOSX_DEPLOYMENT_TARGET)',NSPrincipalClass='NSApplication')
    elif platform=='watchOS':
        for key in ['CFBundleDocumentTypes','UTExportedTypeDeclarations']:info.pop(key)
        info.update(WKApplication=True,WKCompanionAppBundleIdentifier='Mango.Celluloid')
    elif platform=='PhoneHarness':
        for key in ['CFBundleDocumentTypes','UTExportedTypeDeclarations']:info.pop(key)
        info.update(CFBundleDisplayName='Celluloid Companion Validation',UIApplicationSceneManifest={'UIApplicationSupportsMultipleScenes':False},UILaunchScreen={},NSPhotoLibraryUsageDescription='Save requested Watch processing results and verify the saved photo.')
    elif platform=='tvOS':
        for key in ['CFBundleDocumentTypes','UTExportedTypeDeclarations']:info.pop(key)
        info.update(UIApplicationSceneManifest={'UIApplicationSupportsMultipleScenes':False},UILaunchScreen={},NSPhotoLibraryUsageDescription='Choose photos to edit and verify pictures you save.',NSPhotoLibraryAddUsageDescription='Save your finished Celluloid pictures to Photos.')
    else: info.update(UIApplicationSceneManifest={'UIApplicationSupportsMultipleScenes':True},UILaunchScreen={},UISupportsDocumentBrowser=True,LSSupportsOpeningDocumentsInPlace=True)
    with open(ROOT/'Platforms'/platform/'Info.plist','wb') as f: plistlib.dump(info,f,sort_keys=True)
print('Generated CelluloidNative.xcodeproj (unsigned native Mac + visionOS + tvOS + Watch and phone companion validation; original iOS project untouched)')
