"""Read one owned simulator's post-test app installation; never install or retry."""
from pathlib import Path
import hashlib,plistlib,re

def readback(bounded,udid,staging):
    if not re.fullmatch('[0-9A-Fa-f-]{36}',udid):raise ValueError('Invalid owned simulator identity')
    result=bounded(['xcrun','simctl','get_app_container',udid,'Mango.Celluloid','app'],timeout=60,echo=False)
    raw=result.stdout.strip();path=Path(raw)
    if not path.is_absolute() or not path.is_dir():raise ValueError('Post-test app container unavailable')
    path=path.resolve()
    if '/Devices/'+udid+'/data/Containers/Bundle/Application/' not in str(path) or path.name!='Celluloid.app':raise ValueError('Post-test container belongs to another device/app')
    info=plistlib.loads((path/'Info.plist').read_bytes())
    identity={key:info.get(key) for key in ['CFBundleIdentifier','CFBundleExecutable','CFBundleShortVersionString','CFBundleVersion','DTPlatformName']}
    if identity!={'CFBundleIdentifier':'Mango.Celluloid','CFBundleExecutable':'Celluloid','CFBundleShortVersionString':'1.1.1','CFBundleVersion':'3','DTPlatformName':'iphonesimulator'}:raise ValueError('Post-test app metadata differs')
    binary=path/'Celluloid'
    if not binary.is_file() or binary.is_symlink() or not 0<binary.stat().st_size<=200_000_000:raise ValueError('Post-test executable missing/unbounded')
    digest=hashlib.sha256(binary.read_bytes()).hexdigest()
    if digest!=staging['binary_sha256']:raise ValueError('Post-test actual executable differs from the exact built/staged binary')
    return {'device_id':udid,'app_path':str(path),'binary_sha256':digest,'identity':identity,
            'relocated_since_initial_staging':path!=Path(staging['installed_app']).resolve(),'lookup_count':1,'lookup_timeout_seconds':60}

def validate(record,udid,staging):
    expected={'device_id','app_path','binary_sha256','identity','relocated_since_initial_staging','lookup_count','lookup_timeout_seconds'}
    if not isinstance(record,dict) or set(record)!=expected:raise ValueError('Incomplete post-test installation receipt')
    path=Path(record['app_path'])
    if not path.is_absolute() or str(path)!=str(path.resolve()) or '/Devices/'+udid+'/data/Containers/Bundle/Application/' not in str(path) or path.name!='Celluloid.app':raise ValueError('Post-test installation is unowned')
    if record['device_id']!=udid or record['binary_sha256']!=staging['binary_sha256']:raise ValueError('Post-test device/binary mismatch')
    if record['identity']!={'CFBundleIdentifier':'Mango.Celluloid','CFBundleExecutable':'Celluloid','CFBundleShortVersionString':'1.1.1','CFBundleVersion':'3','DTPlatformName':'iphonesimulator'}:raise ValueError('Wrong post-test product identity')
    if type(record['lookup_count']) is not int or record['lookup_count']!=1 or type(record['lookup_timeout_seconds']) is not int or record['lookup_timeout_seconds']!=60:raise ValueError('Unexpected lookup/retry budget')
    if type(record['relocated_since_initial_staging']) is not bool or record['relocated_since_initial_staging']!=(str(path)!=str(Path(staging['installed_app']).resolve())):raise ValueError('Contradictory post-test relocation')
