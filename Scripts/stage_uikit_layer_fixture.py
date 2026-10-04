#!/usr/bin/env python3
"""Install the exact built app and stage a verified fixture in its owned container only."""
from pathlib import Path
import argparse, hashlib, json, os, plistlib, subprocess
from native_fixture_handoff import load_layer_exact
from native_process import run

def container_path(udid, kind):
    if kind not in ('app', 'data'):
        raise ValueError('Only the owned app and data containers may be queried')
    # Cold iOS27 registration exceeded the previous 45-second lookup after a
    # successful install. One bounded read keeps readiness distinct from install.
    result = run(['xcrun','simctl','get_app_container',udid,'Mango.Celluloid',kind],timeout=120)
    path = Path(result.stdout.strip())
    if not path.is_absolute() or not path.is_dir():
        raise ValueError('The simulator did not return an existing absolute app container')
    return path

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('udid'); parser.add_argument('app',type=Path); parser.add_argument('fixtures',type=Path); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); payload=load_layer_exact(args.fixtures,os.environ['GITHUB_SHA'])
    info=plistlib.loads((args.app/'Info.plist').read_bytes())
    assert (info['CFBundleIdentifier'],info['CFBundleExecutable'],info['CFBundleShortVersionString'],info['CFBundleVersion'],info['DTPlatformName']) == ('Mango.Celluloid','Celluloid','1.1','2','iphonesimulator')
    subprocess.run(['xcrun','simctl','install',args.udid,str(args.app)],check=True,timeout=300)
    installed=container_path(args.udid,'app'); digest=hashlib.sha256((args.app/'Celluloid').read_bytes()).hexdigest()
    assert hashlib.sha256((installed/'Celluloid').read_bytes()).hexdigest()==digest
    documents=container_path(args.udid,'data')/'Documents'; documents.mkdir(exist_ok=True)
    target=documents/'mac-layer-fixture.json'; assert not target.exists() and not target.is_symlink()
    target.write_text(json.dumps(payload['fixture']))
    report={'source_sha':os.environ['GITHUB_SHA'],'built_app':str(args.app),'installed_app':str(installed),'binary_sha256':digest,'layer_archive_sha256':payload['fixture']['sha256'],'owned_fixture_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'scope':'File-only test setup. No app launch, picker, Photos import, permission, or database mutation.'}
    args.output.write_text(json.dumps(report,indent=2)+'\n');print('UIKIT_LAYER_FIXTURE_STAGED '+json.dumps(report))
if __name__=='__main__':main()
