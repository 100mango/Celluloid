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
        if key=='CelluloidMacPhotosExtension' and name=='Debug':
            values.update(CELLULOID_MAC_PHOTOS_BOUNDARY_INFO_PLIST='Platforms/macOSExtension/Info.plist',
                INFOPLIST_FILE='$(CELLULOID_MAC_PHOTOS_BOUNDARY_INFO_PLIST)',
                SWIFT_ACTIVE_COMPILATION_CONDITIONS='DEBUG $(CELLULOID_MAC_PHOTOS_BOUNDARY_CONDITION)')
        result.append(add(key+name,'XCBuildConfiguration',name=name,buildSettings=values))
    return add(key+'configs','XCConfigurationList',buildConfigurations=result,defaultConfigurationIsVisible='0',defaultConfigurationName='Release')
def reference(path):
    i=uid(path)
    if i not in objects:
        add(path,'PBXFileReference',lastKnownFileType='sourcecode.swift' if path.endswith('.swift') else 'text.plist.strings' if path.endswith('.strings') else 'folder.assetcatalog' if path.endswith('.xcassets') else 'image.png' if path.endswith('.png') else 'text',path=path,sourceTree='<group>');children.append(i)
    return i
packages={name:add('package:'+name,'XCLocalSwiftPackageReference',relativePath='Packages/'+name) for name in ['CelluloidCore','CelluloidRendering']}
targets={};products={}
settings_by_name={
    'CelluloidWatch':dict(SDKROOT='watchos',SUPPORTED_PLATFORMS='watchos watchsimulator',WATCHOS_DEPLOYMENT_TARGET='9.0',TARGETED_DEVICE_FAMILY='4'),
    'CelluloidWatchTests':dict(SDKROOT='watchos',SUPPORTED_PLATFORMS='watchos watchsimulator',WATCHOS_DEPLOYMENT_TARGET='9.0',TARGETED_DEVICE_FAMILY='4',TEST_HOST='$(BUILT_PRODUCTS_DIR)/CelluloidWatch.app/CelluloidWatch',BUNDLE_LOADER='$(TEST_HOST)',GENERATE_INFOPLIST_FILE='YES'),
    'CelluloidWatchUITests':dict(SDKROOT='watchos',SUPPORTED_PLATFORMS='watchos watchsimulator',WATCHOS_DEPLOYMENT_TARGET='9.0',TARGETED_DEVICE_FAMILY='4',TEST_TARGET_NAME='CelluloidWatch',GENERATE_INFOPLIST_FILE='YES'),
    'CelluloidPhoneCompanion':dict(SDKROOT='iphoneos',SUPPORTED_PLATFORMS='iphoneos iphonesimulator',IPHONEOS_DEPLOYMENT_TARGET='15.0',TARGETED_DEVICE_FAMILY='1,2',SKIP_INSTALL='YES'),
    'CelluloidPhoneCompanionTests':dict(SDKROOT='iphoneos',SUPPORTED_PLATFORMS='iphoneos iphonesimulator',IPHONEOS_DEPLOYMENT_TARGET='15.0',TARGETED_DEVICE_FAMILY='1,2',TEST_HOST='$(BUILT_PRODUCTS_DIR)/CelluloidPhoneCompanion.app/CelluloidPhoneCompanion',BUNDLE_LOADER='$(TEST_HOST)',GENERATE_INFOPLIST_FILE='YES'),
    'CelluloidPhoneCompanionUITests':dict(SDKROOT='iphoneos',SUPPORTED_PLATFORMS='iphoneos iphonesimulator',IPHONEOS_DEPLOYMENT_TARGET='15.0',TARGETED_DEVICE_FAMILY='1,2',TEST_TARGET_NAME='CelluloidPhoneCompanion',GENERATE_INFOPLIST_FILE='YES'),
    'CelluloidTV':dict(SDKROOT='appletvos',SUPPORTED_PLATFORMS='appletvos appletvsimulator',TVOS_DEPLOYMENT_TARGET='17.0',TARGETED_DEVICE_FAMILY='3'),
    'CelluloidTVTests':dict(SDKROOT='appletvos',SUPPORTED_PLATFORMS='appletvos appletvsimulator',TVOS_DEPLOYMENT_TARGET='17.0',TARGETED_DEVICE_FAMILY='3',TEST_HOST='$(BUILT_PRODUCTS_DIR)/CelluloidTV.app/CelluloidTV',BUNDLE_LOADER='$(TEST_HOST)',GENERATE_INFOPLIST_FILE='YES'),
    'CelluloidTVUITests':dict(SDKROOT='appletvos',SUPPORTED_PLATFORMS='appletvos appletvsimulator',TVOS_DEPLOYMENT_TARGET='17.0',TARGETED_DEVICE_FAMILY='3',TEST_TARGET_NAME='CelluloidTV',GENERATE_INFOPLIST_FILE='YES'),
    'CelluloidMacPhotosExtensionTests':dict(SDKROOT='macosx',SUPPORTED_PLATFORMS='macosx',MACOSX_DEPLOYMENT_TARGET='13.0',GENERATE_INFOPLIST_FILE='YES'),
    'CelluloidMacPhotosExtension':dict(SDKROOT='macosx',SUPPORTED_PLATFORMS='macosx',MACOSX_DEPLOYMENT_TARGET='13.0',APPLICATION_EXTENSION_API_ONLY='YES',SKIP_INSTALL='YES'),
    'CelluloidMac':dict(SDKROOT='macosx',SUPPORTED_PLATFORMS='macosx',MACOSX_DEPLOYMENT_TARGET='13.0'),
    'CelluloidVision':dict(SDKROOT='xros',SUPPORTED_PLATFORMS='xros xrsimulator',XROS_DEPLOYMENT_TARGET='1.0',TARGETED_DEVICE_FAMILY='7'),
    'CelluloidVisionTests':dict(SDKROOT='xros',SUPPORTED_PLATFORMS='xros xrsimulator',XROS_DEPLOYMENT_TARGET='1.0',TARGETED_DEVICE_FAMILY='7',TEST_HOST='$(BUILT_PRODUCTS_DIR)/CelluloidVision.app/CelluloidVision',BUNDLE_LOADER='$(TEST_HOST)',GENERATE_INFOPLIST_FILE='YES'),
    'CelluloidVisionUITests':dict(SDKROOT='xros',SUPPORTED_PLATFORMS='xros xrsimulator',XROS_DEPLOYMENT_TARGET='1.0',TARGETED_DEVICE_FAMILY='7',TEST_TARGET_NAME='CelluloidVision',GENERATE_INFOPLIST_FILE='YES'),
    'CelluloidMacUITests':dict(SDKROOT='macosx',SUPPORTED_PLATFORMS='macosx',MACOSX_DEPLOYMENT_TARGET='14.0',TEST_TARGET_NAME='CelluloidMac',GENERATE_INFOPLIST_FILE='YES'),
    'CelluloidMacTests':dict(SDKROOT='macosx',SUPPORTED_PLATFORMS='macosx',MACOSX_DEPLOYMENT_TARGET='14.0',TEST_HOST='$(BUILT_PRODUCTS_DIR)/CelluloidMac.app/Contents/MacOS/CelluloidMac',BUNDLE_LOADER='$(TEST_HOST)',GENERATE_INFOPLIST_FILE='YES')
}
for name in settings_by_name:
    tests=name.endswith('Tests'); ext='xctest' if tests else 'appex' if name=='CelluloidMacPhotosExtension' else 'app'
    products[name]=add('product:'+name,'PBXFileReference',explicitFileType='wrapper.cfbundle' if tests else 'wrapper.app-extension' if name=='CelluloidMacPhotosExtension' else 'wrapper.application',path=name+'.'+ext,sourceTree='BUILT_PRODUCTS_DIR',includeInIndex='0')
    targets[name]=uid('target:'+name)
for name,platform in settings_by_name.items():
    tests=name.endswith('Tests')
    folders={'CelluloidMacPhotosExtensionTests':['MacExtensionTests','macOSExtension'],'CelluloidMacPhotosExtension':['macOSExtension'],'CelluloidMac':['Shared','macOS'],'CelluloidVision':['Shared','visionOS'],'CelluloidTV':['tvOS'],
             'CelluloidWatch':['watchOS'],'CelluloidPhoneCompanion':['Companion','PhoneHarness'],
             'CelluloidMacTests':['Tests'],'CelluloidMacUITests':['UITests'],
             'CelluloidVisionTests':['VisionTests'],'CelluloidVisionUITests':['VisionUITests'],
             'CelluloidTVTests':['TVTests'],'CelluloidTVUITests':['TVUITests'],
             'CelluloidWatchTests':['WatchTests'],'CelluloidWatchUITests':['WatchUITests'],
             'CelluloidPhoneCompanionTests':['PhoneTests'],'CelluloidPhoneCompanionUITests':['PhoneUITests']}
    paths=[path for folder in folders[name] for path in (ROOT/'Platforms'/folder).glob('*.swift')]
    if name in ['CelluloidMacPhotosExtension','CelluloidMacPhotosExtensionTests']:
        paths += [ROOT/path for path in ['Platforms/macOS/PhotosHostFinishCoordinator.swift','Platforms/macOS/NativeChoicePicker.swift','Platforms/Shared/NativeFileAccess.swift','CelluloidPhotoExtension/PhotosOutputWrite.swift']]
    if name=='CelluloidMacPhotosExtensionTests': paths += [ROOT/'CelluloidTests/PhotosOutputWriteTests.swift']
    if name=='CelluloidPhoneCompanion':
        paths += [ROOT/path for path in ['CelluloidKit/Filter/Filter.swift','CelluloidKit/Model/AdjustmentData.swift','CelluloidKit/Extension/JSONCodableExtension.swift','CelluloidKit/Bubble/Model/BubbleModel.swift','CelluloidKit/Sticker/Model/StickerModel.swift','CelluloidKit/Constant/Assets.swift']]
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
        localized.append(add('build:license:'+name,'PBXBuildFile',fileRef=reference('LICENSE.txt')))
    if name=='CelluloidMacPhotosExtensionTests':
        for fixture in ['legacy-points.base64','legacy-points.json','reference-canvas.base64','reference-canvas.json']:
            path='Packages/CelluloidCore/Tests/CelluloidDomainTests/Fixtures/'+fixture
            localized.append(add('build:mac-photos-fixture:'+fixture,'PBXBuildFile',fileRef=reference(path)))
        localized.append(add('build:mac-native-codec-source','PBXBuildFile',fileRef=reference('Platforms/MacExtensionTests/Fixtures/lifecycle-source.png')))
        localized.append(add('build:mac-original-2x-controls','PBXBuildFile',fileRef=reference('Scripts/fixtures/platform-rendering-controls.json')))
    if name=='CelluloidTV':
        localized.append(add('build:tv-privacy-manifest','PBXBuildFile',fileRef=reference('Platforms/tvOS/PrivacyInfo.xcprivacy')))
        refs=[]
        for language in ['en','zh-Hans']:
            item=reference('Platforms/tvOS/'+language+'.lproj/InfoPlist.strings');objects[item]['name']=language
            if item in children:children.remove(item)
            refs.append(item)
        variant=add('variant:tv-info-localizations','PBXVariantGroup',children=refs,name='InfoPlist.strings',sourceTree='<group>');children.append(variant)
        localized.append(add('build:tv-info-localizations','PBXBuildFile',fileRef=variant))
    if name in ['CelluloidWatch','CelluloidVision','CelluloidTV']:
        icon_platform={'CelluloidWatch':'watchOS','CelluloidVision':'visionOS','CelluloidTV':'tvOS'}[name]
        localized.append(add('build:native-icon:'+name,'PBXBuildFile',fileRef=reference('Platforms/'+icon_platform+'/Assets.xcassets')))
    if name=='CelluloidMac':
        localized.append(add('build:mac-icon','PBXBuildFile',fileRef=reference('Platforms/macOS/Assets.xcassets')))
    source=[add('build:'+name+p.relative_to(ROOT).as_posix(),'PBXBuildFile',fileRef=reference(p.relative_to(ROOT).as_posix())) for p in sorted(paths)]
    links=[];deps=[];package_deps=[]
    for package,product in [('CelluloidCore','CelluloidDomain'),('CelluloidRendering','CelluloidRendering')]:
        if name.startswith('CelluloidWatch') and package=='CelluloidRendering':continue
        dep=add('product:'+name+product,'XCSwiftPackageProductDependency',package=packages[package],productName=product)
        package_deps.append(dep);links.append(add('link:'+name+product,'PBXBuildFile',productRef=dep))
    if name=='CelluloidMacPhotosExtension':
        # Match Apple's public Photo Editing sample: the extension context is
        # supplied by PhotosUI; retain standard target linkage explicitly.
        for framework in ['PhotosUI','Photos']:
            ref=add('system-framework:'+framework,'PBXFileReference',lastKnownFileType='wrapper.framework',
                    name=framework+'.framework',path='System/Library/Frameworks/'+framework+'.framework',sourceTree='SDKROOT')
            children.append(ref)
            links.append(add('system-link:'+name+framework,'PBXBuildFile',fileRef=ref))
    if tests:
        host='CelluloidMacPhotosExtension' if name=='CelluloidMacPhotosExtensionTests' else 'CelluloidWatch' if name.startswith('CelluloidWatch') else 'CelluloidPhoneCompanion' if name.startswith('CelluloidPhoneCompanion') else 'CelluloidTV' if name.startswith('CelluloidTV') else 'CelluloidVision' if name.startswith('CelluloidVision') else 'CelluloidMac'
        proxy=add('proxy:'+name,'PBXContainerItemProxy',containerPortal=uid('project'),proxyType='1',remoteGlobalIDString=targets[host],remoteInfo=host)
        deps.append(add('dependency:'+name,'PBXTargetDependency',target=targets[host],targetProxy=proxy))
    if name=='CelluloidMac':
        proxy=add('proxy:mac-photos-extension','PBXContainerItemProxy',containerPortal=uid('project'),proxyType='1',remoteGlobalIDString=targets['CelluloidMacPhotosExtension'],remoteInfo='CelluloidMacPhotosExtension')
        deps.append(add('dependency:mac-photos-extension','PBXTargetDependency',target=targets['CelluloidMacPhotosExtension'],targetProxy=proxy))
    settings=dict(PRODUCT_NAME='$(TARGET_NAME)',PRODUCT_BUNDLE_IDENTIFIER='Mango.Celluloid.'+name if tests else 'Mango.Celluloid',SWIFT_VERSION='5.0',SWIFT_STRICT_CONCURRENCY='minimal',CODE_SIGNING_ALLOWED='NO',CODE_SIGNING_REQUIRED='NO',CODE_SIGN_IDENTITY='',CURRENT_PROJECT_VERSION='2',MARKETING_VERSION='1.1',ENABLE_USER_SCRIPT_SANDBOXING='YES',LD_RUNPATH_SEARCH_PATHS=['$(inherited)','@executable_path/Frameworks','@executable_path/../Frameworks'],**platform)
    if name=='CelluloidMacPhotosExtension':settings.update(PRODUCT_BUNDLE_IDENTIFIER='Mango.Celluloid.CelluloidPhotoExtension',ENABLE_APP_SANDBOX='YES',CODE_SIGN_ENTITLEMENTS='Platforms/macOSExtension/CelluloidMacPhotosExtension.entitlements',CODE_SIGN_INJECT_BASE_ENTITLEMENTS='NO')
    if name=='CelluloidWatch':settings.update(PRODUCT_BUNDLE_IDENTIFIER='Mango.Celluloid.watchkitapp',SKIP_INSTALL='YES')
    if name in ['CelluloidWatch','CelluloidVision','CelluloidTV']:settings['ASSETCATALOG_COMPILER_APPICON_NAME']='AppIcon'
    if name=='CelluloidMac': settings.update(ASSETCATALOG_COMPILER_APPICON_NAME='AppIcon',ENABLE_APP_SANDBOX='YES',CODE_SIGN_ENTITLEMENTS='Platforms/macOS/CelluloidMac.entitlements',CODE_SIGN_INJECT_BASE_ENTITLEMENTS='NO',ENABLE_HARDENED_RUNTIME='NO')
    if not tests: settings['INFOPLIST_FILE']='Platforms/'+('macOSExtension' if name=='CelluloidMacPhotosExtension' else 'watchOS' if name=='CelluloidWatch' else 'PhoneHarness' if name=='CelluloidPhoneCompanion' else 'tvOS' if name=='CelluloidTV' else 'macOS' if name=='CelluloidMac' else 'visionOS')+'/Info.plist'
    phases=[add('phase:'+name+kind,'PBX'+kind+'BuildPhase',buildActionMask='2147483647',files=files,runOnlyForDeploymentPostprocessing='0') for kind,files in [('Sources',source),('Frameworks',links),('Resources',localized)]]
    if name=='CelluloidMac':
        embedded=add('build:embedded-mac-photos-extension','PBXBuildFile',fileRef=products['CelluloidMacPhotosExtension'],settings={'ATTRIBUTES':['RemoveHeadersOnCopy']})
        phases.append(add('phase:embed-mac-photos-extension','PBXCopyFilesBuildPhase',buildActionMask='2147483647',dstPath='',dstSubfolderSpec='13',files=[embedded],name='Embed Photos Extension',runOnlyForDeploymentPostprocessing='0'))
    add('target:'+name,'PBXNativeTarget',name=name,productName=name,productReference=products[name],productType='com.apple.product-type.'+('bundle.ui-testing' if name.endswith('UITests') else 'bundle.unit-test' if tests else 'app-extension' if name=='CelluloidMacPhotosExtension' else 'application'),buildConfigurationList=configs(name,settings),buildPhases=phases,buildRules=[],dependencies=deps,packageProductDependencies=package_deps)
prodgroup=add('products','PBXGroup',name='Products',children=list(products.values()),sourceTree='<group>')
root=add('root','PBXGroup',children=children+[prodgroup],sourceTree='<group>')
add('project','PBXProject',attributes={'LastUpgradeCheck':'2700','BuildIndependentTargetsInParallel':'YES','TargetAttributes':{targets[n]:{'TestTargetID':targets['CelluloidWatch' if n.startswith('CelluloidWatch') else 'CelluloidPhoneCompanion' if n.startswith('CelluloidPhoneCompanion') else 'CelluloidTV' if n.startswith('CelluloidTV') else 'CelluloidVision' if n.startswith('CelluloidVision') else 'CelluloidMac']} for n in targets if n.endswith('Tests') and n!='CelluloidMacPhotosExtensionTests'}},buildConfigurationList=configs('project',{'CLANG_ENABLE_MODULES':'YES','CLANG_ENABLE_OBJC_ARC':'YES','SWIFT_VERSION':'5.0','CELLULOID_EXPECT_SANDBOX':'NO'}),compatibilityVersion='Xcode 14.0',developmentRegion='en',hasScannedForEncodings='0',knownRegions=['en','zh-Hans'],mainGroup=root,productRefGroup=prodgroup,projectDirPath='',projectRoot='',targets=list(targets.values()),packageReferences=list(packages.values()))
project=ROOT/'CelluloidNative.xcodeproj';project.mkdir(exist_ok=True)
(project/'project.pbxproj').write_text('// !$*UTF8*$!\n'+encode({'archiveVersion':'1','classes':{},'objectVersion':'56','objects':objects,'rootObject':uid('project')})+'\n')
for name in ['CelluloidMac','CelluloidVision','CelluloidMacUI','CelluloidTV','CelluloidWatch','CelluloidPhoneCompanion','CelluloidMacPhotosExtension']:
    folder=project/'xcshareddata/xcschemes';folder.mkdir(parents=True,exist_ok=True)
    def ref(n):return f'<BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{targets[n]}" BuildableName="{n}.{"xctest" if n.endswith("Tests") else "appex" if n=="CelluloidMacPhotosExtension" else "app"}" BlueprintName="{n}" ReferencedContainer="container:CelluloidNative.xcodeproj"/>'
    app_name='CelluloidMac' if name=='CelluloidMacUI' else name
    test_name='CelluloidMacUITests' if name=='CelluloidMacUI' else 'CelluloidMacTests'
    tests='<TestableReference skipped="NO">'+ref(test_name)+'</TestableReference>' if name in ['CelluloidMac','CelluloidMacUI'] else ''
    if name in ['CelluloidMac','CelluloidMacPhotosExtension']: tests += '<TestableReference skipped="NO">'+ref('CelluloidMacPhotosExtensionTests')+'</TestableReference>'
    if name=='CelluloidVision': tests=''.join('<TestableReference skipped="NO">'+ref(n)+'</TestableReference>' for n in ['CelluloidVisionTests','CelluloidVisionUITests'])
    if name=='CelluloidTV': tests=''.join('<TestableReference skipped="NO">'+ref(n)+'</TestableReference>' for n in ['CelluloidTVTests','CelluloidTVUITests'])
    if name=='CelluloidWatch': tests=''.join('<TestableReference skipped="NO">'+ref(n)+'</TestableReference>' for n in ['CelluloidWatchTests','CelluloidWatchUITests'])
    if name=='CelluloidPhoneCompanion': tests=''.join('<TestableReference skipped="NO">'+ref(n)+'</TestableReference>' for n in ['CelluloidPhoneCompanionTests','CelluloidPhoneCompanionUITests'])
    environment='<EnvironmentVariables><EnvironmentVariable key="CELLULOID_EXPECTED_APP_PATH" value="$(BUILT_PRODUCTS_DIR)/CelluloidMac.app" isEnabled="YES"/><EnvironmentVariable key="CELLULOID_EXPECT_SANDBOX" value="$(CELLULOID_EXPECT_SANDBOX)" isEnabled="YES"/></EnvironmentVariables>' if name in ['CelluloidMac','CelluloidMacUI'] else ''
    (folder/(name+'.xcscheme')).write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<Scheme LastUpgradeVersion="2700" version="1.3"><BuildAction parallelizeBuildables="YES" buildImplicitDependencies="YES"><BuildActionEntries><BuildActionEntry buildForTesting="YES" buildForRunning="YES" buildForProfiling="YES" buildForArchiving="YES" buildForAnalyzing="YES">{ref(app_name)}</BuildActionEntry></BuildActionEntries></BuildAction><TestAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" shouldUseLaunchSchemeArgsEnv="NO"><MacroExpansion>{ref(app_name)}</MacroExpansion><Testables>{tests}</Testables>{environment}</TestAction><LaunchAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB"><BuildableProductRunnable runnableDebuggingMode="0">{ref(app_name)}</BuildableProductRunnable></LaunchAction><ProfileAction buildConfiguration="Release" shouldUseLaunchSchemeArgsEnv="YES"><BuildableProductRunnable runnableDebuggingMode="0">{ref(app_name)}</BuildableProductRunnable></ProfileAction><AnalyzeAction buildConfiguration="Debug"/><ArchiveAction buildConfiguration="Release" revealArchiveInOrganizer="YES"/></Scheme>\n''')
for platform in ['macOS','visionOS','tvOS','watchOS','PhoneHarness','macOSExtension']:
    info={'CFBundleIdentifier':'$(PRODUCT_BUNDLE_IDENTIFIER)','CFBundleName':'Celluloid','CFBundleDevelopmentRegion':'en','CFBundleLocalizations':['en','zh-Hans'],'CFBundleExecutable':'$(EXECUTABLE_NAME)','CFBundlePackageType':'APPL','CFBundleVersion':'$(CURRENT_PROJECT_VERSION)','CFBundleShortVersionString':'$(MARKETING_VERSION)','NSHumanReadableCopyright':'Copyright © Mango. See bundled LICENSE.txt.','CFBundleDocumentTypes':[{'CFBundleTypeName':'Celluloid Document','CFBundleTypeRole':'Editor','LSHandlerRank':'Owner','LSItemContentTypes':['Mango.Celluloid.document']}],'UTExportedTypeDeclarations':[{'UTTypeIdentifier':'Mango.Celluloid.document','UTTypeDescription':'Celluloid Editable Document','UTTypeConformsTo':['com.apple.package'],'UTTypeTagSpecification':{'public.filename-extension':['celluloid']}}]}
    if platform=='macOS': info.update(LSApplicationCategoryType='public.app-category.utilities',LSMinimumSystemVersion='$(MACOSX_DEPLOYMENT_TARGET)',NSPrincipalClass='NSApplication')
    elif platform=='macOSExtension':
        for key in ['CFBundleDocumentTypes','UTExportedTypeDeclarations']:info.pop(key)
        info.update(CFBundlePackageType='XPC!',CFBundleDisplayName='Celluloid',LSMinimumSystemVersion='$(MACOSX_DEPLOYMENT_TARGET)',NSExtension={'NSExtensionPointIdentifier':'com.apple.photo-editing','NSExtensionPrincipalClass':'$(PRODUCT_MODULE_NAME).MacPhotoEditingController','NSExtensionAttributes':{'PHSupportedMediaTypes':['Image']}})
    elif platform=='watchOS':
        for key in ['CFBundleDocumentTypes','UTExportedTypeDeclarations']:info.pop(key)
        info.update(WKApplication=True,WKCompanionAppBundleIdentifier='Mango.Celluloid')
    elif platform=='PhoneHarness':
        for key in ['CFBundleDocumentTypes','UTExportedTypeDeclarations']:info.pop(key)
        info.update(CFBundleDisplayName='Celluloid Companion Validation',UIApplicationSceneManifest={'UIApplicationSupportsMultipleScenes':False},UILaunchScreen={},NSPhotoLibraryUsageDescription='Save requested Watch processing results and verify the saved photo.')
    elif platform=='tvOS':
        for key in ['CFBundleDocumentTypes','UTExportedTypeDeclarations']:info.pop(key)
        info.update(UIApplicationSceneManifest={'UIApplicationSupportsMultipleScenes':False},UILaunchScreen={},NSPhotoLibraryUsageDescription='Choose photos to edit and verify pictures you save.',NSPhotoLibraryAddUsageDescription='Save your finished Celluloid pictures to Photos.')
    else: info.update(UIApplicationSceneManifest={'UIApplicationSupportsMultipleScenes':True},UILaunchScreen={},UISupportsDocumentBrowser=True,LSSupportsOpeningDocumentsInPlace=True,UIFileSharingEnabled=True)
    with open(ROOT/'Platforms'/platform/'Info.plist','wb') as f: plistlib.dump(info,f,sort_keys=True)
print('Generated CelluloidNative.xcodeproj (unsigned native Mac + visionOS + tvOS + Watch and phone companion validation; original iOS project untouched)')
