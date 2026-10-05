"""Strict self-observation binding; never enumerate, launch or inspect another process."""
import hashlib,re
from mac_host_transport import load_json,HOST_CONTRACT

SCHEMA='Celluloid.ExtensionSelfIdentity.1'
RECEIPT='Celluloid.HostSelfIdentity.1'
MARKER='CELLULOID_EXTENSION_SELF_IDENTITY_V1'
IDENTIFIER='photos-extension.self-identity'
LIMIT=8192
FIELDS={'schema','marker','observation_kind','bundle_identifier','pid','bundle_path','executable_path',
        'executable_sha256','debug_dylib_path','debug_dylib_sha256','generation','content_editing_started'}

def require(value,message):
    if not value:raise ValueError(message)

def validate(receipt,context,photos,ownership):
    require(type(receipt) is dict and set(receipt)=={'schema','host_entry_contract','source_sha','photos_pid',
        'fixture_sha256','asset_label','identity_identifier','identity_element_counts','observations'},'Malformed self-identity receipt')
    require(receipt['schema']==RECEIPT and receipt['host_entry_contract']==HOST_CONTRACT,'Wrong self-identity contract')
    require(receipt['source_sha']==context['source_sha'],'Wrong self-identity source')
    require(type(receipt['photos_pid']) is int and receipt['photos_pid']==photos['pid']>0,'Wrong surrounding Photos PID')
    require(receipt['fixture_sha256']==ownership['fixture_sha256'] and receipt['asset_label']==ownership['asset_label'],'Wrong self-identity fixture')
    require(receipt['identity_identifier']==IDENTIFIER,'Wrong self-identity UI identifier')
    counts=receipt['identity_element_counts']
    require(type(counts) is list and len(counts)==2 and all(type(value) is int and value==1 for value in counts),'Missing/duplicate self-identity element')
    observations=receipt['observations']
    require(type(observations) is list and len(observations)==2,'Missing/duplicate self-identity observation')
    values=[];raws=[]
    for observation in observations:
        require(type(observation) is dict and set(observation)=={'raw','bytes','sha256'},'Malformed self-identity observation envelope')
        raw=observation['raw'];require(type(raw) is str,'Self-identity observation is not text')
        data=raw.encode('utf8');require(type(observation['bytes']) is int and 0<len(data)==observation['bytes']<=LIMIT,'Self-identity byte cap')
        require(observation['sha256']==hashlib.sha256(data).hexdigest(),'Self-identity observation hash mismatch')
        value=load_json(raw);require(type(value) is dict and set(value)==FIELDS,'Unknown/missing self-identity field')
        require(value['schema']==SCHEMA and value['marker']==MARKER and value['observation_kind']=='extension-self','Wrong self-observation kind')
        require(value['bundle_identifier']==context['extension_id'],'Wrong self-observed bundle')
        require(value['content_editing_started'] is True,'Self-identity preceded content editing')
        require(type(value['pid']) is int and 0<value['pid']<2**31 and value['pid']!=photos['pid'],'Invalid self-observed PID')
        generation=value['generation'];require(type(generation) is str and re.fullmatch(r'[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}',generation) is not None and generation.replace('-','')!='0'*32,'Invalid editing generation')
        for key,expected in [('bundle_path',context['extension_path']),('executable_path',context['extension_executable']),
                             ('debug_dylib_path',context['extension_debug_dylib'])]:
            path=value[key];require(type(path) is str and len(path.encode())<=2048 and path==expected and path.startswith('/') and not any(ord(c)<32 or ord(c)==127 for c in path),'Wrong self-observed own-bundle path')
        require(value['debug_dylib_path']==value['executable_path']+'.debug.dylib','Wrong own debug-dylib location')
        for key,expected in [('executable_sha256',context['extension_executable_sha256']),('debug_dylib_sha256',context['extension_debug_dylib_sha256'])]:
            require(type(value[key]) is str and re.fullmatch('[0-9a-f]{64}',value[key]) is not None and value[key]==expected,'Wrong self-observed product hash')
        values.append(value);raws.append(raw)
    require(raws[0]==raws[1] and values[0]==values[1],'Stale/changed editing identity between UI observations')
    return values[0]
