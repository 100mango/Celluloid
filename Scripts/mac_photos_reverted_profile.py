"""Only the current owned reverted PNG and its bound canonical representation."""
import os,stat,re
from pathlib import Path
from mac_host_transport import load_json,HOST_CONTRACT
from mac_host_self_identity import validate as identity_validate,RECEIPT,IDENTIFIER
from mac_host_lifecycle import PHASES
from mac_host_lifecycle_pixels import sha,require

MODE='gama-chrm-canonical-srgb-v1'
DIRECTORY='owned-reverted-profile'
RAW='reverted-input.png'
CANONICAL='reverted-canonical.png'
RECEIPT_FILE='profile.json'
MAX_BYTES=131072+131072+8192
FIELDS={'schema','source_sha','context_sha256','run_id','run_attempt','phase','raw_file','raw_bytes','raw_sha256','canonical_file','profile','declaration','qualification'}

def admit_profile_receipt(context,context_hash,records,baseline,photos,ownership):
    require(context.get('owned_reverted_profile_observation')==MODE and 'boundary_probe' not in context,'wrong reverted profile mode')
    outcome=load_json(records['outcome.json']);row=load_json(records['lifecycle.json'])
    require(outcome.get('source_sha')==context['source_sha'] and outcome.get('host_entry_contract')==HOST_CONTRACT
        and outcome.get('complete_host_e2e') is False,'unbound profile outcome')
    require(row.get('schema')=='Celluloid.PhotosFilterLifecycle.1' and row.get('source_sha')==context['source_sha']
        and row.get('context_sha256')==context_hash and row.get('fixture_sha256')==ownership['fixture_sha256']
        and row.get('dirty_cancel_tested') is False,'unbound profile lifecycle')
    phases=row.get('phases');require(type(phases) is list and 5<=len(phases)<=8,'reverted profile lacks safe prefix')
    previous=-1
    for index,phase in enumerate(phases):
        require(type(phase) is dict and type(phase.get('index')) is int and phase['index']==index
            and phase.get('name')==PHASES[index] and type(phase.get('elapsed_ms')) is int
            and previous<=phase['elapsed_ms']<900000,'invalid profile phase prefix')
        previous=phase['elapsed_ms']
    require(phases[0]['details'].get('fixture_sha256')==ownership['fixture_sha256']
        and phases[0]['details'].get('retained_before_import') is True
        and phases[1]['details'].get('filter')=='Fade','profile source/filter prefix')
    save=phases[2]['details'];cancel=phases[4]['details'];reopened=phases[3]['details']
    require(type(save.get('max_channel_delta')) is int and 0<=save['max_channel_delta']<=3
        and save.get('limit')==2 and type(save.get('sole_asset_count')) is int and save['sole_asset_count']==1,'profile save prefix')
    require(cancel=={'rgba_equal_saved':True,'new_edit_made':False,'sole_asset_count':1}
        and cancel['rgba_equal_saved'] is True and cancel['new_edit_made'] is False
        and type(cancel['sole_asset_count']) is int,'profile Cancel prefix')
    require(reopened.get('filter')=='Fade' and type(reopened.get('editor_count_before')) is int and reopened['editor_count_before']==0
        and type(reopened.get('editor_count_after')) is int and reopened['editor_count_after']==1,'profile reentry prefix')
    bound={'schema':RECEIPT,'host_entry_contract':HOST_CONTRACT,'source_sha':context['source_sha'],'photos_pid':photos['pid'],
        'fixture_sha256':ownership['fixture_sha256'],'asset_label':ownership['asset_label'],'identity_identifier':IDENTIFIER,
        'identity_element_counts':reopened['identity_element_counts'],'observations':reopened['observations']}
    actual=identity_validate(bound,context,photos,ownership);require(actual['generation']!=baseline['generation'],'stale profile reentry')
    saved=row['images']['lifecycle-saved.png'];cancelled=row['images']['lifecycle-cancelled.png']
    require(saved['rgba_sha256']==cancelled['rgba_sha256'],'profile Cancel raster mismatch')
    if save['max_channel_delta']==3:
        require(saved['rgba_sha256']=='744dfa09d6ab997552cdb11393a53761c8e098ffd37e6a8c3a9febdfd0972c99'
            and row['images']['lifecycle-expected-save.png']['rgba_sha256']=='eacc2ada4af742470b52d2ed14996d07e71db7c2b68b2da4f7947efcc7f9855a','unknown deferred profile prefix')
    for phase,name in [('saved','lifecycle-saved.png'),('cancelled','lifecycle-cancelled.png')]:
        export=row['raw_exports'][phase];meta=row['images'][name]
        require(export.get('image')==name and export.get('relative_path')==phase+'/Celluloid-Owned-Host.png'
            and export.get('bytes')==meta['bytes'] and export.get('sha256')==meta['sha256'],'profile export prefix binding')
    diagnostics=outcome.get('export_png_diagnostics');require(type(diagnostics) is list and len(diagnostics)<=4 and all(type(item) is dict for item in diagnostics),'profile diagnostic volume')
    matches=[item for item in diagnostics if item.get('phase')=='reverted'];require(len(matches)==1,'missing/ambiguous reverted diagnostic')
    diagnostic=matches[0];receipt=diagnostic.get('owned_profile_receipt')
    require(type(receipt) is dict and set(receipt)==FIELDS and receipt['schema']=='Celluloid.OwnedRevertedProfile.1','profile receipt shape')
    env=context['runner_environment']
    require(receipt['source_sha']==context['source_sha'] and receipt['context_sha256']==context_hash
        and receipt['run_id']==env['GITHUB_RUN_ID'] and type(receipt['run_attempt']) is int
        and receipt['run_attempt']==1 and env['GITHUB_RUN_ATTEMPT']=='1','profile receipt run/source')
    require(receipt['phase']=='reverted' and receipt['raw_file']==RAW and receipt['qualification'] is False
        and type(receipt['raw_bytes']) is int and 0<receipt['raw_bytes']<=131072
        and type(receipt['raw_sha256']) is str and re.fullmatch('[0-9a-f]{64}',receipt['raw_sha256']) is not None
        and receipt['raw_bytes']==diagnostic.get('bytes') and receipt['raw_sha256']==diagnostic.get('sha256'),'profile raw binding')
    require(receipt['canonical_file'] in (None,CANONICAL),'profile canonical path')
    require((receipt['canonical_file'] is None and receipt['profile'] is None)
        or (receipt['canonical_file']==CANONICAL and type(receipt['profile']) is dict),'profile canonical pairing')
    return receipt

def read_profile(temp,context,receipt,check):
    """No directory listing, container read, reported path, fallback or subprocess."""
    require(Path(temp).resolve()==Path(temp) and context['evidence_path']==str(Path(temp)/'mac-host-observed'),'profile root binding')
    descriptors=[];directories=[]
    def snapshot(s):return s.st_dev,s.st_ino,s.st_mode,s.st_nlink,s.st_size,s.st_uid,s.st_mtime_ns,s.st_ctime_ns
    try:
        check();parent=os.open(temp,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW);descriptors.append(parent)
        for part in ['mac-host-observed',DIRECTORY]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=parent);descriptors.append(child)
            value=os.fstat(child);require(stat.S_ISDIR(value.st_mode) and value.st_uid==os.getuid(),'unowned profile directory')
            directories.append((parent,part,child,snapshot(value)));parent=child;check()
        def read(name,cap):
            fd=os.open(name,os.O_RDONLY|os.O_NONBLOCK|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=parent)
            try:
                before=os.fstat(fd);require(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_uid==os.getuid()
                    and 0<before.st_size<=cap,'profile file type/size/owner')
                data=os.read(fd,cap+1);check()
                require(len(data)==before.st_size and not os.read(fd,1),'short/growing profile file')
                require(snapshot(before)==snapshot(os.fstat(fd))==snapshot(os.stat(name,dir_fd=parent,follow_symlinks=False)),'changed profile file')
                return data
            finally:os.close(fd)
        record=read(RECEIPT_FILE,8192);require(load_json(record)==receipt,'disk/log profile receipt mismatch')
        raw=read(RAW,131072);require(len(raw)==receipt['raw_bytes'] and sha(raw)==receipt['raw_sha256'],'profile raw bytes changed')
        files={'reverted-profile.json':record,'reverted-profile-input.png':raw};canonical=None
        if receipt['canonical_file'] is not None:
            png=read(CANONICAL,131072);profile=receipt['profile']
            require(profile.get('raw_sha256')==sha(raw) and profile.get('raw_bytes')==len(raw)
                and profile.get('canonical_sha256')==sha(png) and profile.get('canonical_bytes')==len(png),'profile canonical bytes changed')
            files['reverted-profile-canonical.png']=png;canonical={'png':png,'profile':profile}
        for owner,name,fd,before in directories:
            check();require(before==snapshot(os.fstat(fd))==snapshot(os.stat(name,dir_fd=owner,follow_symlinks=False)),'changed profile directory')
        require(sum(map(len,files.values()))<=MAX_BYTES,'profile aggregate cap')
        return files,canonical
    finally:
        for fd in reversed(descriptors):os.close(fd)
