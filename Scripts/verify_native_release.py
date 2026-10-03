#!/usr/bin/env python3
"""Inspect an unsigned generic-device Release build; never signs or contacts an account."""
import hashlib,json,os,plistlib,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
platform=sys.argv[1];app=Path(sys.argv[2]);out=Path(os.environ['RUNNER_TEMP'])/(platform+'-release-packaging.json')
contracts={'mac':('macosx','13.0','Mango.Celluloid','CelluloidMac'),
           'tv':('appletvos','17.0','Mango.Celluloid','CelluloidTV'),
           'watch':('watchos','9.0','Mango.Celluloid.watchkitapp','CelluloidWatch'),
           'vision':('xros','1.0','Mango.Celluloid','CelluloidVision')}
sdk,floor,bundle,product=contracts[platform]
base=app/'Contents' if platform=='mac' else app
info=plistlib.loads((base/'Info.plist').read_bytes())
executable=base/'MacOS'/product if platform=='mac' else base/product
checks={}
def check(name,value):checks[name]=bool(value)
check('bundle_identifier',info.get('CFBundleIdentifier')==bundle)
check('executable_name',info.get('CFBundleExecutable')==product and executable.is_file())
check('device_sdk_not_simulator',info.get('DTPlatformName')==sdk and 'simulator' not in info.get('DTSDKName',''))
check('minimum_os_metadata',info.get('LSMinimumSystemVersion' if platform=='mac' else 'MinimumOSVersion')==floor)
check('version_and_build',info.get('CFBundleShortVersionString')=='2.0' and info.get('CFBundleVersion')=='2')
check('localized_bundles',all((base/('Resources' if platform=='mac' else '')/(lang+'.lproj')/'Localizable.strings').is_file() for lang in ['en','zh-Hans']))
resources=base/'Resources' if platform=='mac' else base
check('license_packaged', (resources/'LICENSE.txt').is_file() and (resources/'LICENSE.txt').read_bytes()==(ROOT/'LICENSE.txt').read_bytes())
check('no_test_bundles',not any(app.rglob('*.xctest')))
bytes_=executable.read_bytes()
markers=[b'--celluloid-sandbox-diagnostics',b'sandbox.probe',b'CELLULOID_AX_REPORT',b'TV_PHOTOS_BUTTON_ACTION',b'TV_PHOTOS_AUTH',b'CELLULOID_TV_OUTPUT_PROOF',b'CELLULOID_TV_COMPOSITION_PROOF',b'Celluloid synthetic container readback']
check('debug_seams_absent',not any(marker in bytes_ for marker in markers))
archs=subprocess.check_output(['xcrun','lipo','-archs',str(executable)],text=True).strip().split()
check('native_arm_device_slice',any(arch.startswith('arm64') for arch in archs))
# arm64 watchOS was introduced with watchOS26; legacy arm64_32 retains
# the declared Watch9 floor. Require both standard slices, rather than allowing
# an arbitrary higher floor to hide a compatibility regression.
# Apple: https://developer.apple.com/news/?id=zt8rydnt
loads={arch:subprocess.check_output(['xcrun','vtool','-arch',arch,'-show-build',str(executable)],text=True) for arch in archs}
linked_minima={arch:re.findall(r'\bminos\s+(\S+)',value) for arch,value in loads.items()}
expected_minima={arch:('26.0' if platform=='watch' and arch=='arm64' else floor) for arch in archs}
check('linked_minimum_matches',bool(archs) and all(values and all((x+'.0').split('.')[:2]==(expected_minima[arch]+'.0').split('.')[:2] for x in values) for arch,values in linked_minima.items()))
if platform=='watch':check('watch_standard_architectures',set(archs)=={'arm64','arm64_32'})
load_commands='\n'.join(arch+'\n'+value for arch,value in loads.items())
icon_dictionary=info.get('CFBundleIcons',{})
primary=icon_dictionary.get('CFBundlePrimaryIcon') if isinstance(icon_dictionary,dict) else None
# tvOS uses a named primary image stack string (Small); iOS-style dictionaries
# and top-level macOS/Watch icon keys are separate legitimate platform schemas.
if platform=='tv':
    icon_named=primary=='Small'
elif platform=='vision':
    icon_named=primary=='AppIcon' or (isinstance(primary,dict) and primary.get('CFBundleIconName')=='AppIcon')
else:
    icon_named=(isinstance(primary,dict) and primary.get('CFBundleIconName')=='AppIcon') or info.get('CFBundleIconName')=='AppIcon' or info.get('CFBundleIconFile')=='AppIcon'
check('brand_icon_packaged',icon_named and (resources/'Assets.car').is_file() and (resources/'Assets.car').stat().st_size>0)
catalog_entries=[]
if (resources/'Assets.car').is_file():
    catalog=json.loads(subprocess.check_output(['xcrun','assetutil','--info',str(resources/'Assets.car')],text=True,timeout=30))
    expected_icon='Small' if platform=='tv' else 'AppIcon'
    catalog_entries=[{key:entry[key] for key in ['Name','AssetType','PixelWidth','PixelHeight','Scale','Idiom'] if key in entry} for entry in catalog if isinstance(entry,dict) and (str(entry.get('Name',''))==expected_icon or str(entry.get('Name','')).startswith(expected_icon+'/'))][:50]
check('compiled_icon_renditions',bool(catalog_entries))
if platform=='watch':
    check('watch_companion_binding' ,info.get('WKApplication') is True and info.get('WKCompanionAppBundleIdentifier')=='Mango.Celluloid')
if platform=='tv':
    actual=plistlib.loads((base/'PrivacyInfo.xcprivacy').read_bytes())
    expected=plistlib.loads((ROOT/'Platforms/tvOS/PrivacyInfo.xcprivacy').read_bytes())
    check('privacy_manifest_exact',actual==expected)
    check('permission_prompts_localized',all((base/(lang+'.lproj')/'InfoPlist.strings').is_file() for lang in ['en','zh-Hans']))
report={'source_sha':os.environ['GITHUB_SHA'],'platform':platform,'product':str(app),'build_mode':'generic-device Release CODE_SIGNING_ALLOWED=NO',
        'checks':checks,'architectures':archs,'binary_sha256':hashlib.sha256(bytes_).hexdigest(),'linked_build_versions':load_commands,'linked_minima_by_architecture':linked_minima,'expected_minima_by_architecture':expected_minima,
        'icon_catalog_entries':catalog_entries,
        'bundle_info':{k:info.get(k) for k in ['CFBundleIdentifier','CFBundleShortVersionString','CFBundleVersion','DTPlatformName','DTSDKName','DTXcode','DTXcodeBuild','MinimumOSVersion','LSMinimumSystemVersion','CFBundleIcons','CFBundleIconName','CFBundleIconFile']},
        'scope':'Compile/link and packaged metadata only. Oldest-OS runtime, physical hardware, Store signatures and final combined iOS integration remain separate gates.'}
out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n');print(json.dumps({'packaging_report':str(out),'checks':checks}))
if not all(checks.values()):raise SystemExit('Release packaging gate failed: '+', '.join(k for k,v in checks.items() if not v))
