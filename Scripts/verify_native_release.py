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
markers=[b'--celluloid-sandbox-diagnostics',b'sandbox.probe',b'CELLULOID_AX_REPORT',b'TV_PHOTOS_BUTTON_ACTION',b'TV_PHOTOS_AUTH',b'Celluloid synthetic container readback']
check('debug_seams_absent',not any(marker in bytes_ for marker in markers))
archs=subprocess.check_output(['xcrun','lipo','-archs',str(executable)],text=True).strip().split()
check('native_arm_device_slice',any(arch.startswith('arm64') for arch in archs))
load_commands=subprocess.check_output(['xcrun','vtool','-show-build',str(executable)],text=True)
minima=re.findall(r'\bminos\s+(\S+)',load_commands)
check('linked_minimum_matches',bool(minima) and all((x+'.0').split('.')[:2]==(floor+'.0').split('.')[:2] for x in minima))
icons=info.get('CFBundleIcons',{}).get('CFBundlePrimaryIcon',{})
check('brand_icon_packaged',bool(icons.get('CFBundleIconName') or info.get('CFBundleIconName') or info.get('CFBundleIconFile')) and (resources/'Assets.car').is_file())
if platform=='watch':
    check('watch_companion_binding',info.get('WKApplication') is True and info.get('WKCompanionAppBundleIdentifier')=='Mango.Celluloid')
if platform=='tv':
    actual=plistlib.loads((base/'PrivacyInfo.xcprivacy').read_bytes())
    expected=plistlib.loads((ROOT/'Platforms/tvOS/PrivacyInfo.xcprivacy').read_bytes())
    check('privacy_manifest_exact',actual==expected)
    check('permission_prompts_localized',all((base/(lang+'.lproj')/'InfoPlist.strings').is_file() for lang in ['en','zh-Hans']))
report={'source_sha':os.environ['GITHUB_SHA'],'platform':platform,'product':str(app),'build_mode':'generic-device Release CODE_SIGNING_ALLOWED=NO',
        'checks':checks,'architectures':archs,'binary_sha256':hashlib.sha256(bytes_).hexdigest(),'linked_build_versions':load_commands,
        'bundle_info':{k:info.get(k) for k in ['CFBundleIdentifier','CFBundleShortVersionString','CFBundleVersion','DTPlatformName','DTSDKName','DTXcode','DTXcodeBuild','MinimumOSVersion','LSMinimumSystemVersion','CFBundleIcons','CFBundleIconName','CFBundleIconFile']},
        'scope':'Compile/link and packaged metadata only. Oldest-OS runtime, physical hardware, Store signatures and final combined iOS integration remain separate gates.'}
out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n');print(json.dumps({'packaging_report':str(out),'checks':checks}))
if not all(checks.values()):raise SystemExit('Release packaging gate failed: '+', '.join(k for k,v in checks.items() if not v))
