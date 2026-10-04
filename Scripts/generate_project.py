#!/usr/bin/env python3
"""Generate the dependency-free project topology, with SnapKit pinned via SwiftPM."""
from pathlib import Path
import hashlib, json
ROOT=Path(__file__).resolve().parents[1]
objects={}
def uid(key):return hashlib.sha1(key.encode()).hexdigest()[:24].upper()
def add(key,isa,**kw):
 i=uid(key);objects[i]={'isa':isa,**kw};return i
def quote(s):return json.dumps(str(s),ensure_ascii=False)
def emit(v,level=0):
 if isinstance(v,dict):return '{\n'+''.join('\t'*(level+1)+quote(k)+' = '+emit(x,level+1)+';\n' for k,x in v.items())+'\t'*level+'}'
 if isinstance(v,list):return '('+', '.join(emit(x,level+1) for x in v)+')'
 return quote(v)
def configlist(key,settings):
 configs=[]
 for name in ['Debug','Release']:
  s=dict(settings)
  s.update({'SWIFT_OPTIMIZATION_LEVEL':'-Onone' if name=='Debug' else '-O','DEBUG_INFORMATION_FORMAT':'dwarf' if name=='Debug' else 'dwarf-with-dsym'})
  if name=='Debug':s.update({'SWIFT_ACTIVE_COMPILATION_CONDITIONS':'DEBUG','ENABLE_TESTABILITY':'YES','ONLY_ACTIVE_ARCH':'YES'})
  configs.append(add(key+name,'XCBuildConfiguration',name=name,buildSettings=s))
 return add(key+'configs','XCConfigurationList',buildConfigurations=configs,defaultConfigurationIsVisible='0',defaultConfigurationName='Release')
children=[]
def file(path,typ=None):
 key='file:'+path
 i=uid(key)
 if i not in objects:
  typ=typ or {'.swift':'sourcecode.swift','.plist':'text.plist.xml','.storyboard':'file.storyboard','.xcassets':'folder.assetcatalog','.json':'text.json','.strings':'text.plist.strings','.h':'sourcecode.c.h','.xcprivacy':'text.xml'}.get(Path(path).suffix,'text')
  add(key,'PBXFileReference',lastKnownFileType=typ,path=path,sourceTree='<group>');children.append(i)
 return i
package=add('snapkit','XCRemoteSwiftPackageReference',repositoryURL='https://github.com/SnapKit/SnapKit.git',requirement={'kind':'exactVersion','version':'5.7.1'})
names=['CelluloidKit','CelluloidPhotoExtension','Celluloid','CelluloidTests','CelluloidUITests']
products={};targetids={n:uid('target:'+n) for n in names}
for n in names:
 ext='framework' if n=='CelluloidKit' else ('appex' if n=='CelluloidPhotoExtension' else 'app' if n=='Celluloid' else 'xctest')
 products[n]=add('product:'+n,'PBXFileReference',explicitFileType={'framework':'wrapper.framework','appex':'wrapper.app-extension','app':'wrapper.application','xctest':'wrapper.cfbundle'}[ext],path=n+'.'+ext,sourceTree='BUILT_PRODUCTS_DIR',includeInIndex='0')
for n in names:
 source=[];resource=[];framework=[];headers=[];phases=[];deps=[];packages=[]
 paths=list((ROOT/n).rglob('*'))
 if n=='CelluloidTests':paths.extend([ROOT/'CelluloidPhotoExtension/PhotoEditingViewController.swift',ROOT/'CelluloidPhotoExtension/PhotosOutputWrite.swift'])
 localized={}
 for p in sorted(paths):
  if p.is_dir() and p.suffix!='.xcassets':continue
  rel=p.relative_to(ROOT).as_posix()
  if any(x.endswith('.xcassets') for x in p.relative_to(ROOT).parts[:-1]):continue
  if p.name=='Info.plist':continue
  if p.suffix=='.h':continue
  if '.lproj/' in rel:
   prefix,sub=rel.split('.lproj/',1);lang=prefix.rsplit('/',1)[-1]
   key=sub.replace('.strings','.storyboard') if sub in ['LaunchScreen.strings','MainInterface.strings'] else sub
   localized.setdefault(key,[]).append((lang,rel));continue
  ref=file(rel)
  build=add('build:'+n+':'+rel,'PBXBuildFile',fileRef=ref)
  (source if p.suffix=='.swift' else resource).append(build)
 for key,entries in localized.items():
  refs=[]
  for lang,rel in entries:
   ref=file(rel);objects[ref]['name']=lang;children.remove(ref);refs.append(ref)
  group=add('variant:'+n+key,'PBXVariantGroup',children=refs,name=key,sourceTree='<group>');children.append(group)
  resource.append(add('build:variant:'+n+key,'PBXBuildFile',fileRef=group))
 if n in ['Celluloid','CelluloidKit']:
  dep=add('package:'+n,'XCSwiftPackageProductDependency',package=package,productName='SnapKit');packages.append(dep)
  framework.append(add('build:package:'+n,'PBXBuildFile',productRef=dep))
 dependent={'Celluloid':['CelluloidKit','CelluloidPhotoExtension'],'CelluloidPhotoExtension':['CelluloidKit'],'CelluloidTests':['Celluloid','CelluloidKit'],'CelluloidUITests':['Celluloid']}.get(n,[])
 for other in dependent:
  proxy=add('proxy:'+n+other,'PBXContainerItemProxy',containerPortal=uid('project'),proxyType='1',remoteGlobalIDString=targetids[other],remoteInfo=other)
  deps.append(add('dependency:'+n+other,'PBXTargetDependency',target=targetids[other],targetProxy=proxy))
  if other=='CelluloidKit':framework.append(add('link:'+n+other,'PBXBuildFile',fileRef=products[other]))
 for kind,files in [('Sources',source),('Frameworks',framework),('Resources',resource)]:
  phases.append(add('phase:'+n+kind,'PBX'+kind+'BuildPhase',buildActionMask='2147483647',files=files,runOnlyForDeploymentPostprocessing='0'))
 if n=='Celluloid':
  for other,dst in [('CelluloidKit','10'),('CelluloidPhotoExtension','13')]:
   embed=add('embed:'+other,'PBXBuildFile',fileRef=products[other],settings={'ATTRIBUTES':['RemoveHeadersOnCopy','CodeSignOnCopy']})
   phases.append(add('embedphase:'+other,'PBXCopyFilesBuildPhase',buildActionMask='2147483647',dstPath='',dstSubfolderSpec=dst,files=[embed],name='Embed '+other,runOnlyForDeploymentPostprocessing='0'))
 ids={'Celluloid':'Mango.Celluloid','CelluloidKit':'Mango.CelluloidKit','CelluloidPhotoExtension':'Mango.Celluloid.CelluloidPhotoExtension','CelluloidTests':'Mango.Celluloid.Tests','CelluloidUITests':'Mango.Celluloid.UITests'}
 settings={'PRODUCT_NAME':'$(TARGET_NAME)','PRODUCT_BUNDLE_IDENTIFIER':ids[n],'SWIFT_VERSION':'5.0','SWIFT_STRICT_CONCURRENCY':'minimal','IPHONEOS_DEPLOYMENT_TARGET':'15.0','TARGETED_DEVICE_FAMILY':'1,2','CODE_SIGN_STYLE':'Automatic','CURRENT_PROJECT_VERSION':'2','LD_RUNPATH_SEARCH_PATHS':['$(inherited)','@executable_path/Frameworks','@loader_path/Frameworks'],'ENABLE_USER_SCRIPT_SANDBOXING':'YES','SUPPORTED_PLATFORMS':'iphoneos iphonesimulator'}
 if n in ['Celluloid','CelluloidKit','CelluloidPhotoExtension']:settings['INFOPLIST_FILE']=n+'/Info.plist'
 else:settings['GENERATE_INFOPLIST_FILE']='YES'
 if n=='Celluloid':settings['ASSETCATALOG_COMPILER_APPICON_NAME']='AppIcon'
 if n=='CelluloidKit':settings.update({'DEFINES_MODULE':'YES','SKIP_INSTALL':'YES','APPLICATION_EXTENSION_API_ONLY':'YES','INSTALL_PATH':'$(LOCAL_LIBRARY_DIR)/Frameworks','DYLIB_INSTALL_NAME_BASE':'@rpath'})
 if n=='CelluloidPhotoExtension':settings.update({'SKIP_INSTALL':'YES','APPLICATION_EXTENSION_API_ONLY':'YES','LD_RUNPATH_SEARCH_PATHS':['$(inherited)','@executable_path/Frameworks','@executable_path/../../Frameworks']})
 if n in ['CelluloidTests','CelluloidUITests']:settings['IPHONEOS_DEPLOYMENT_TARGET']='17.0'
 if n=='CelluloidTests':settings.update({'TEST_HOST':'$(BUILT_PRODUCTS_DIR)/Celluloid.app/Celluloid','BUNDLE_LOADER':'$(TEST_HOST)'})
 if n=='CelluloidUITests':settings['TEST_TARGET_NAME']='Celluloid'
 producttype={'Celluloid':'application','CelluloidKit':'framework','CelluloidPhotoExtension':'app-extension','CelluloidTests':'bundle.unit-test','CelluloidUITests':'bundle.ui-testing'}[n]
 add('target:'+n,'PBXNativeTarget',name=n,productName=n,productReference=products[n],productType='com.apple.product-type.'+producttype,buildConfigurationList=configlist('target:'+n,settings),buildPhases=phases,buildRules=[],dependencies=deps,packageProductDependencies=packages)
prodgroup=add('products','PBXGroup',name='Products',children=list(products.values()),sourceTree='<group>')
rootgroup=add('rootgroup','PBXGroup',children=children+[prodgroup],sourceTree='<group>')
add('project','PBXProject',attributes={'LastUpgradeCheck':'2700','BuildIndependentTargetsInParallel':'YES','TargetAttributes':{targetids['CelluloidTests']:{'TestTargetID':targetids['Celluloid']},targetids['CelluloidUITests']:{'TestTargetID':targetids['Celluloid']}}},buildConfigurationList=configlist('project',{'SDKROOT':'iphoneos','CLANG_ENABLE_MODULES':'YES','CLANG_ENABLE_OBJC_ARC':'YES','GCC_C_LANGUAGE_STANDARD':'gnu17','IPHONEOS_DEPLOYMENT_TARGET':'15.0','SWIFT_VERSION':'5.0','ENABLE_BITCODE':'NO'}),compatibilityVersion='Xcode 14.0',developmentRegion='en',hasScannedForEncodings='0',knownRegions=['en','Base','zh-Hans'],mainGroup=rootgroup,productRefGroup=prodgroup,projectDirPath='',projectRoot='',targets=list(targetids.values()),packageReferences=[package])
(ROOT/'Celluloid.xcodeproj/project.pbxproj').write_text('// !$*UTF8*$!\n'+emit({'archiveVersion':'1','classes':{},'objectVersion':'56','objects':objects,'rootObject':uid('project')})+'\n')
# One shared scheme builds the shipping extension with the app and both regression suites.
scheme=ROOT/'Celluloid.xcodeproj/xcshareddata/xcschemes/Celluloid.xcscheme';scheme.parent.mkdir(parents=True,exist_ok=True)
def ref(n):return f'<BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{targetids[n]}" BuildableName="{n}.app" BlueprintName="{n}" ReferencedContainer="container:Celluloid.xcodeproj"/>'
scheme.write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<Scheme LastUpgradeVersion="2700" version="1.3"><BuildAction parallelizeBuildables="YES" buildImplicitDependencies="YES"><BuildActionEntries><BuildActionEntry buildForTesting="YES" buildForRunning="YES" buildForProfiling="YES" buildForArchiving="YES" buildForAnalyzing="YES">{ref('Celluloid')}</BuildActionEntry></BuildActionEntries></BuildAction><TestAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" shouldUseLaunchSchemeArgsEnv="YES"><Testables>{''.join('<TestableReference skipped="NO">'+ref(n).replace(n+'.app',n+'.xctest')+'</TestableReference>' for n in ['CelluloidTests','CelluloidUITests'])}</Testables></TestAction><LaunchAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" launchStyle="0" useCustomWorkingDirectory="NO" ignoresPersistentStateOnLaunch="NO" debugDocumentVersioning="YES" debugServiceExtension="internal" allowLocationSimulation="YES"><BuildableProductRunnable runnableDebuggingMode="0">{ref('Celluloid')}</BuildableProductRunnable></LaunchAction><ProfileAction buildConfiguration="Release" shouldUseLaunchSchemeArgsEnv="YES" savedToolIdentifier="" useCustomWorkingDirectory="NO" debugDocumentVersioning="YES"><BuildableProductRunnable runnableDebuggingMode="0">{ref('Celluloid')}</BuildableProductRunnable></ProfileAction><AnalyzeAction buildConfiguration="Debug"/><ArchiveAction buildConfiguration="Release" revealArchiveInOrganizer="YES"/></Scheme>''')
(ROOT/'Celluloid.xcworkspace/contents.xcworkspacedata').write_text('<?xml version="1.0" encoding="UTF-8"?><Workspace version="1.0"><FileRef location="group:Celluloid.xcodeproj"/></Workspace>\n')
