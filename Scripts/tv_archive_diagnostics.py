"""Bounded, nonqualifying archive observations. No external commands or symlink traversal."""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import stat
import struct
import time
import uuid

MAX_ENTRIES = 8192
MAX_RECORD_BYTES = 768 * 1024
MAX_FILE_BYTES = 1024 * 1024
MAX_SECONDS = 20
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK
APP = 'Products/Applications/CelluloidTV.app'
DSYM = 'dSYMs/CelluloidTV.app.dSYM'
FIXED_FILES = ('Info.plist', APP+'/Info.plist', APP+'/PrivacyInfo.xcprivacy',
               APP+'/PkgInfo', APP+'/CelluloidTV', APP+'/Assets.car',
               APP+'/zh-Hans.lproj/Localizable.strings',
               DSYM+'/Contents/Info.plist', DSYM+'/Contents/Resources/DWARF/CelluloidTV')


class DiagnosticStopped(ValueError):
    pass


def need(ok, reason):
    if not ok:raise DiagnosticStopped(reason)


def identity(value):
    return (value.st_dev,value.st_ino,value.st_mode,value.st_nlink,value.st_size,value.st_mtime_ns,value.st_ctime_ns)


def record(path, value):
    kind = ('directory' if stat.S_ISDIR(value.st_mode) else 'file' if stat.S_ISREG(value.st_mode)
            else 'symlink' if stat.S_ISLNK(value.st_mode) else 'other')
    return {'path':path,'type':kind,'size':value.st_size,'mode':oct(stat.S_IMODE(value.st_mode)),
            'links':value.st_nlink}


def open_root(archive):
    before=archive.lstat()
    need(stat.S_ISDIR(before.st_mode),'archive-root-not-directory')
    fd=os.open(archive,DIRECTORY_FLAGS)
    if identity(os.fstat(fd))!=identity(before):
        os.close(fd);raise DiagnosticStopped('archive-root-changed')
    return fd


def inventory(archive, deadline, *, clock=time.monotonic):
    """Enumerate metadata inside owned directory FDs. Never read regular file contents."""
    result={'complete':False,'qualifying':False,'entries':[],'bytes_observed':0,
            'limits':{'entries':MAX_ENTRIES,'record_bytes':MAX_RECORD_BYTES,'path_bytes':1024,'seconds':MAX_SECONDS},
            'content_read':False,'symlink_targets_followed':False}
    retained=0;root_fd=None
    def timely():need(clock()<deadline,'diagnostic-deadline')
    def walk(fd, prefix):
        nonlocal retained
        timely();before=identity(os.fstat(fd))
        with os.scandir(fd) as stream:
            for entry in stream:
                timely();path=prefix+entry.name
                need(len(path.encode())<=1024,'diagnostic-path-limit')
                value=entry.stat(follow_symlinks=False);row=record(path,value)
                size=len(json.dumps(row,separators=(',',':')).encode())
                need(len(result['entries'])<MAX_ENTRIES and retained+size<=MAX_RECORD_BYTES,'diagnostic-inventory-limit')
                result['entries'].append(row);retained+=size
                result['bytes_observed']+=value.st_size if stat.S_ISREG(value.st_mode) else 0
                if stat.S_ISDIR(value.st_mode):
                    child=None
                    try:
                        child=os.open(entry.name,DIRECTORY_FLAGS,dir_fd=fd)
                        need(identity(os.fstat(child))==identity(value),'diagnostic-directory-changed')
                        walk(child,path+'/')
                    finally:
                        if child is not None:os.close(child)
        timely();need(identity(os.fstat(fd))==before,'diagnostic-directory-changed')
    try:
        timely();root_fd=open_root(Path(archive));walk(root_fd,'');result['complete']=True
    except (Exception,KeyboardInterrupt) as error:
        result['failure']={'type':type(error).__name__,'reason':str(error)[:1024]}
    finally:
        if root_fd is not None:os.close(root_fd)
    result['record_bytes']=retained
    return result


def safe_read(archive, name, deadline, *, clock=time.monotonic, header_only=False):
    """Read only an exact allowlisted path through no-follow directory handles."""
    need(name in FIXED_FILES,'diagnostic-path-not-allowed')
    need(clock()<deadline,'diagnostic-deadline')
    root_fd=open_root(Path(archive));fds=[root_fd];file_fd=None
    try:
        pieces=name.split('/')
        for piece in pieces[:-1]:
            need(clock()<deadline,'diagnostic-deadline')
            child=os.open(piece,DIRECTORY_FLAGS,dir_fd=fds[-1]);fds.append(child)
        file_fd=os.open(pieces[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fds[-1])
        before=os.fstat(file_fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink==1,'diagnostic-file-not-regular-single-link')
        need(header_only or before.st_size<=MAX_FILE_BYTES,'diagnostic-file-byte-limit')
        limit=min(before.st_size,MAX_FILE_BYTES) if header_only else before.st_size
        data=bytearray()
        while len(data)<limit:
            need(clock()<deadline,'diagnostic-deadline')
            chunk=os.read(file_fd,min(65536,limit-len(data)))
            if not chunk:break
            data.extend(chunk)
        need(clock()<deadline and len(data)==limit,'diagnostic-short-or-late-read')
        need(identity(os.fstat(file_fd))==identity(before),'diagnostic-file-changed')
        return bytes(data),record(name,before)
    finally:
        if file_fd is not None:os.close(file_fd)
        for fd in reversed(fds):os.close(fd)


def mach_header(raw):
    need(len(raw)>=32 and raw[:4]==b'\xcf\xfa\xed\xfe','diagnostic-mach-header-invalid')
    _,cpu,subtype,kind,count,size,flags,reserved=struct.unpack_from('<8I',raw)
    need(reserved==0 and count<=4096 and size<=MAX_FILE_BYTES-32 and 32+size<=len(raw),'diagnostic-load-command-bounds')
    value={'cpu':cpu,'subtype':subtype,'kind':kind,'uuid':[],'build':[],'code_signature_bytes':[]}
    pos=32
    for _ in range(count):
        need(pos+8<=32+size,'diagnostic-load-command-short')
        command,length=struct.unpack_from('<II',raw,pos)
        need(length>=8 and length%8==0 and pos+length<=32+size,'diagnostic-load-command-size')
        if command==0x1b:
            need(length==24,'diagnostic-uuid-size');value['uuid'].append(str(uuid.UUID(bytes=raw[pos+8:pos+24])).upper())
        if command==0x32:
            need(length>=24,'diagnostic-build-size')
            platform,minimum,sdk,tools=struct.unpack_from('<4I',raw,pos+8)
            value['build'].append({'platform':platform,'minimum':[minimum>>16,(minimum>>8)&255,minimum&255],
                                   'sdk':[sdk>>16,(sdk>>8)&255,sdk&255]})
        if command==0x1d:
            need(length==16,'diagnostic-signature-size');value['code_signature_bytes'].append(struct.unpack_from('<I',raw,pos+12)[0])
        pos+=length
    need(pos==32+size,'diagnostic-command-table-incomplete')
    return value


def bounded_metadata(value):
    raw=json.dumps(value,default=lambda x: '<'+type(x).__name__+'>',ensure_ascii=True,allow_nan=False)
    if len(raw.encode())<=32768:return value
    return {'metadata_omitted':'diagnostic-metadata-byte-limit','keys':list(value)[:32] if isinstance(value,dict) else [],'encoded_bytes':len(raw.encode())}


def fixed_file_observations(archive, deadline, *, clock=time.monotonic):
    result={'qualifying':False,'external_commands':False,'files':{},'raw_file_contents_retained':False}
    for name in FIXED_FILES:
        if clock()>=deadline:
            result['stopped']='diagnostic-deadline';break
        try:
            binary=name in (APP+'/CelluloidTV',DSYM+'/Contents/Resources/DWARF/CelluloidTV')
            raw,row=safe_read(archive,name,deadline,clock=clock,header_only=binary or name.endswith('/Assets.car'))
            value={'status':'observed',**row,'bytes_read':len(raw),'read_sha256':hashlib.sha256(raw).hexdigest()}
            if binary:value['mach_header']=mach_header(raw)
            elif name.endswith('.plist') or name.endswith('.xcprivacy'):
                data=plistlib.loads(raw);need(isinstance(data,dict),'diagnostic-plist-not-dictionary')
                if name=='Info.plist':
                    value['metadata']={k:data.get(k) for k in ('ArchiveVersion','SchemeName','ApplicationProperties')}
                elif name.endswith('/PrivacyInfo.xcprivacy'):
                    value['metadata']=data
                else:
                    keys=('CFBundleIdentifier','CFBundleName','CFBundleDisplayName','CFBundleExecutable','CFBundlePackageType',
                          'CFBundleShortVersionString','CFBundleVersion','CFBundleSupportedPlatforms','MinimumOSVersion',
                          'UIDeviceFamily','CFBundleIcons','DTSDKName','NSPhotoLibraryUsageDescription',
                          'NSPhotoLibraryAddUsageDescription')
                    value['metadata']={k:data[k] for k in keys if k in data}
            elif name.endswith('/PkgInfo'):value['hex']=raw.hex()
            if 'metadata' in value:value['metadata']=bounded_metadata(value['metadata'])
            result['files'][name]=value
        except (Exception,KeyboardInterrupt) as error:
            result['files'][name]={'status':'unavailable','type':type(error).__name__,'reason':str(error)[:512]}
    app=result['files'].get(APP+'/CelluloidTV',{}).get('mach_header',{})
    dsym=result['files'].get(DSYM+'/Contents/Resources/DWARF/CelluloidTV',{}).get('mach_header',{})
    metadata=result['files'].get(APP+'/Info.plist',{}).get('metadata',{})
    expected={'CFBundleIdentifier':'Mango.Celluloid','CFBundleExecutable':'CelluloidTV','CFBundleName':'Celluloid','CFBundlePackageType':'APPL','CFBundleShortVersionString':'1.1','CFBundleVersion':'2','MinimumOSVersion':'17.0','CFBundleSupportedPlatforms':['AppleTVOS'],'UIDeviceFamily':[3],'DTSDKName':'appletvos27.0'}
    result['app_metadata_comparisons']={k:{'expected':v,'observed':metadata.get(k),'matches':metadata.get(k)==v} for k,v in expected.items()}
    result['header_uuid_comparison']=('same-single-nonzero' if len(app.get('uuid',[]))==1 and
        app.get('uuid')==dsym.get('uuid') and app['uuid'][0]!='00000000-0000-0000-0000-000000000000' else 'different-or-unavailable')
    return result


def collect(archive, deadline, *, clock=time.monotonic):
    end=min(deadline,clock()+MAX_SECONDS)
    return {'scope':'nonqualifying-safe-file-observation-before-strict-validation',
            'inventory':inventory(archive,end,clock=clock),
            'fixed_files':fixed_file_observations(archive,end,clock=clock)}
