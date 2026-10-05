"""Bounded, read-only projection of this exact Photos extension's IPS incidents.

No host acceptance, discovery, registration, permission or process mutation.
"""
from pathlib import Path
import datetime as dt
import hashlib
import errno
import json
import math
import os
import re
import stat
import selectors
import signal
import subprocess
import sys
import time
from mac_host_transport import load_json, parse as parse_transport, CASE, LABEL

NAME='CelluloidMacPhotosExtension'
EXT_ID='Mango.Celluloid.CelluloidPhotoExtension'
IDENTITY='mac-host-crash-identity.json'
OUTPUT='mac-host-owned-extension-crashes.json'
MAX_DIRECTORY_ENTRIES=256
MAX_CANDIDATES=16
MAX_INCIDENTS=4
MAX_INPUT=512*1024
MAX_TOTAL_INPUT=2*1024*1024
MAX_OUTPUT=96*1024
MAX_FRAMES=128
MAX_IMAGES=64

def check(ok,message):
    if not ok:raise ValueError(message)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def encode(row):return (json.dumps(row,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def uuid(value):
    check(type(value) is str and re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}',value),'Invalid UUID')
    return value.lower()
def integer(value):return type(value) is int and 0<=value<2**64
def number(value):return (type(value) is int and abs(value)<=2**53) or (type(value) is float and math.isfinite(value))
def text(value,limit=2048):
    check(type(value) is str and len(value.encode())<=limit,'Invalid/oversized diagnostic text')
    return value

def directory_fd(path):
    path=Path(path).absolute()
    check(all(part not in {'.','..'} for part in path.parts[1:]),'Unsafe directory component')
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            try:child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            except OSError as error:raise ValueError('Symlink or unavailable owned directory') from error
            os.close(fd);fd=child
        return fd
    except BaseException:
        os.close(fd);raise

def safe_read(path,cap):
    """Open every component without following links, then bind one file inode."""
    path=Path(path).absolute();parent=directory_fd(path.parent);fd=None
    try:
        before=os.stat(path.name,dir_fd=parent,follow_symlinks=False)
        check(not stat.S_ISLNK(before.st_mode),'Symlink input')
        check(stat.S_ISREG(before.st_mode) and 0<before.st_size<=cap,'Invalid/oversized input')
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
        opened=os.fstat(fd);check((opened.st_dev,opened.st_ino)==(before.st_dev,before.st_ino),'Input replaced before read')
        chunks=[];count=0
        while True:
            part=os.read(fd,min(65536,cap+1-count))
            if not part:break
            chunks.append(part);count+=len(part);check(count<=cap,'Input grew beyond cap')
        after=os.fstat(fd);current=os.stat(path.name,dir_fd=parent,follow_symlinks=False)
        signature=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        check(signature(before)==signature(opened)==signature(after)==signature(current) and count==before.st_size,'Input changed during read')
        return b''.join(chunks)
    finally:
        if fd is not None:os.close(fd)
        os.close(parent)

def same_path(observed,expected):
    # Apple documents USER privacy placeholders. No wildcard, suffix, traversal
    # normalization or any other substituted component is accepted here.
    check(type(expected) is str and expected.startswith('/Users/'),'Unexpected owned executable root')
    parts=expected.split('/');check(len(parts)>3 and parts[2] not in {'','USER','.','..'},'Invalid runner username')
    return type(observed) is str and observed in {expected,'/Users/USER/'+ '/'.join(parts[3:])}

def timestamp(value):
    text(value,80)
    check(re.fullmatch(r'\d{4}-\d\d-\d\d \d\d:\d\d:\d\d(?:\.\d{1,6})? [+-]\d{4}',value),'Missing/invalid incident timezone')
    return dt.datetime.strptime(value,'%Y-%m-%d %H:%M:%S.%f %z' if '.' in value else '%Y-%m-%d %H:%M:%S %z').timestamp()

def test_window(log,summary,context,context_hash):
    parse_transport(log,context,context_hash,complete=False)
    check(type(summary) is dict and summary.get('totalTestCount')==1,'Not the single host test summary')
    check(all(type(summary.get(k)) is int for k in ['totalTestCount','passedTests','failedTests','skippedTests']) and summary.get('passedTests',0)+summary.get('failedTests',0)==1 and summary.get('skippedTests')==0,'Unfinalized host testcase')
    start,end=summary.get('startTime'),summary.get('finishTime')
    check(number(start) and number(end) and 0<end-start<=735,'Invalid summary interval')
    begin=[load_json(line.split(' ',1)[1]) for line in log.splitlines() if line.startswith('BOUNDED_COMMAND_BEGIN ')][0]
    finish=[load_json(line.split(' ',1)[1]) for line in log.splitlines() if line.startswith('BOUNDED_COMMAND_END ')][0]
    command_start=dt.datetime.fromisoformat(begin['utc']);check(command_start.tzinfo is not None,'Missing process timezone')
    process_start=command_start.timestamp();process_end=process_start+finish['elapsed_seconds']
    offsets=set(re.findall(r'^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+([+-]\d{4}) CelluloidMacUITests-Runner\[',log,re.M))
    check(len(offsets)==1,'Missing/ambiguous explicit test-runner timezone')
    owner,method=CASE
    opened="Test Case '-["+owner+' '+method+"]' started."
    active=log.split(opened,1)[1]
    terminal=re.search(r"^Test Case '-\["+re.escape(owner+' '+method)+r"\]' (passed|failed) \(([0-9]+(?:\.[0-9]+)?) seconds\)\.$",active,re.M)
    check(terminal is not None,'Missing actual test terminal')
    stamps=re.findall(r'^\s+t =\s+0\.00s Start Test at (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+)$',active[:terminal.start()],re.M)
    check(len(stamps)==1,'Missing/ambiguous actual test start')
    case_start=timestamp(stamps[0]+' '+next(iter(offsets)));elapsed=float(terminal[2]);case_end=case_start+elapsed
    check(0<elapsed<=660 and process_start<=start<=case_start<case_end<=end<=process_end+0.01,'Test/summary/process intervals contradict')
    suites=re.findall(r"^Test Suite 'MacPhotosHostUITests' (?:passed|failed) at (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+)\.$",active[terminal.end():],re.M)
    check(len(suites)==1 and abs(timestamp(suites[0]+' '+next(iter(offsets)))-case_end)<=0.01,'Actual host suite terminal contradicts duration')
    return {'start':case_start,'end':case_end,'result':terminal[1],'test_log_sha256':digest(log.encode())}

class OwnedCandidatePathMismatch(ValueError):
    def __init__(self,body,binding,incident):
        observed=text(body.get('procPath'),2048);expected=text(binding['expected_executable'],2048)
        check(observed.startswith('/') and not any(ord(c)<32 or ord(c)==127 for c in observed),'Malformed observed executable path')
        self.observation={'schema':'Celluloid.OwnedPathMismatch.2','acceptance':False,'path_match':False,
            'identity_and_window_validated':True,'incident':incident,'executable_uuid':binding['executable_uuid'],
            'extension_id':EXT_ID,'observed_procPath':observed,'expected_procPath':expected,
            'captureTime':body['captureTime'],'procLaunch':body.get('procLaunch'),
            'comparison_reason':'Neither exact expected path nor sole /Users/<runner>/ to /Users/USER/ substitution'}
        super().__init__('Wrong executable path')

def projection(raw,binding,window):
    check(0<len(raw)<=MAX_INPUT,'IPS input cap')
    first,rest=raw.decode('utf8',errors='strict').split('\n',1)
    metadata=load_json(first);body=load_json(rest)
    check(type(metadata) is dict and type(body) is dict,'IPS must contain two objects')
    check(metadata.get('bug_type')=='309' and body.get('bug_type','309')=='309','Not a crash IPS')
    check(type(body.get('bundleInfo')) is dict,'Invalid bundle metadata')
    check(metadata.get('bundleID')==body['bundleInfo'].get('CFBundleIdentifier')==EXT_ID,'Wrong bundle identity')
    check(metadata.get('app_name')==body.get('procName')==NAME,'Wrong process name')
    incident=uuid(metadata.get('incident_id'));check(uuid(body.get('incident'))==incident,'Conflicting incident identity')
    check(uuid(metadata.get('slice_uuid'))==binding['executable_uuid'],'Wrong executable UUID')
    captured=timestamp(body.get('captureTime'));check(window['start']<=captured<=window['end'],'Incident outside host-test window')
    if 'procLaunch' in body:check(window['start']<=timestamp(body['procLaunch'])<=captured,'Process launched outside host-test window')
    check(integer(body.get('pid')) and body['pid']>0,'Invalid process PID')
    if not same_path(body.get('procPath'),binding['expected_executable']):
        mismatch=OwnedCandidatePathMismatch(body,binding,incident)
        try:
            detail=_project_details(raw,body,binding,incident,captured,verified_path=False)
            # This is rejected evidence. UUID attribution does not establish its
            # executable path or satisfy any host/product acceptance predicate.
            detail.update(schema='Celluloid.UUIDBoundPathUnverifiedCrash.1',acceptance=False,
                executable_path_verified=False,attribution='Exact built UUID, bundle/process, incident and test window; executable path unverified')
            mismatch.observation['uuid_bound_diagnostic']=detail
        except (ValueError,KeyError,TypeError,UnicodeError,RecursionError) as error:
            mismatch.observation['projection_error']=text(str(error),256)
        raise mismatch
    return _project_details(raw,body,binding,incident,captured,verified_path=True)

def _project_details(raw,body,binding,incident,captured,*,verified_path):
    # Caller alone establishes the exact product/incident/window binding. This
    # shared bounded projection never grants acceptance or reads reported paths.
    images=body.get('usedImages',[]);threads=body.get('threads',[])
    check(type(images) is list and len(images)<=1024 and all(type(i) is dict for i in images),'Malformed image table')
    check(type(threads) is list and len(threads)<=256 and all(type(t) is dict for t in threads),'Malformed thread table')
    triggered=[i for i,t in enumerate(threads) if t.get('triggered') is True]
    check(len(triggered)<=1 and all('triggered' not in t or type(t['triggered']) is bool for t in threads),'Ambiguous triggered thread')
    fault=body.get('faultingThread')
    if fault is not None:
        check(integer(fault) and fault<len(threads) and (not triggered or triggered==[fault]),'Invalid/contradictory faulting thread')
        triggered=[fault]
    selected=set();owned={};seen_owned=set();image_path_matches={}
    for i,img in enumerate(images):
        for key,path_key,uuid_key in [('executable','expected_executable','executable_uuid'),('debug_dylib','expected_debug_dylib','debug_dylib_uuid')]:
            path=img.get('path');matches=type(path) is str and same_path(path,binding[path_key])
            named=img.get('name')==Path(binding[path_key]).name
            identified=type(img.get('uuid')) is str and img['uuid'].lower()==binding[uuid_key]
            if matches or named or identified:
                check((matches or not verified_path) and uuid(img.get('uuid'))==binding[uuid_key] and key not in seen_owned,'Conflicting/duplicate owned image')
                if not matches:
                    text(path,2048);check(path.startswith('/') and not any(ord(c)<32 or ord(c)==127 for c in path),'Malformed UUID-bound image path')
                seen_owned.add(key);owned[key]=i;selected.add(i);image_path_matches[key]=matches
    def frames(value):
        check(type(value) is list and len(value)<=MAX_FRAMES,'Backtrace frame cap/type')
        out=[]
        for frame in value:
            check(type(frame) is dict and integer(frame.get('imageIndex')) and frame['imageIndex']<len(images),'Dangling/invalid frame image')
            check(integer(frame.get('imageOffset')),'Invalid image offset')
            row={'imageIndex':frame['imageIndex'],'imageOffset':frame['imageOffset']};selected.add(frame['imageIndex'])
            for field in ['symbol','sourceFile']:
                if field in frame:row[field]=text(frame[field])
            for field in ['symbolLocation','sourceLine']:
                if field in frame:check(integer(frame[field]),'Invalid frame scalar');row[field]=frame[field]
            out.append(row)
        return out
    crashed=[]
    for i in triggered:
        crashed.append({'originalIndex':i,'frames':frames(threads[i].get('frames',[]))})
    last=frames(body.get('lastExceptionBacktrace',[]))
    check(len(selected)<=MAX_IMAGES,'Necessary image cap')
    remap={original:i for i,original in enumerate(sorted(selected))};projected_images=[]
    for index in sorted(selected):
        img=images[index];row={'originalIndex':index,'uuid':uuid(img.get('uuid'))}
        for field in ['path','name','arch']:
            if field in img:row[field]=text(img[field])
        for field in ['base','size']:
            if field in img:check(integer(img[field]),'Invalid image scalar');row[field]=img[field]
        projected_images.append(row)
    for trace in [last]+[t['frames'] for t in crashed]:
        for frame in trace:frame['imageIndex']=remap[frame['imageIndex']]
    fields={'exception':{'type','signal','codes','rawCodes','subtype','message','note'},
            'termination':{'namespace','code','flags','indicator','byProc','byPid','reasons','details'},
            'exceptionReason':{'type','name','class','composed_message','format_string','arguments'}}
    def bounded(value,depth=0):
        check(depth<=3,'Diagnostic nesting cap')
        if type(value) is str:return text(value,4096)
        if value is None or type(value) is bool or (type(value) is int and -(2**63)<=value<2**64):return value
        if type(value) is list:
            check(len(value)<=16,'Diagnostic array cap');return [bounded(v,depth+1) for v in value]
        raise ValueError('Unsupported diagnostic value')
    detail={}
    for field,allowed in fields.items():
        if field in body:
            check(type(body[field]) is dict,'Invalid diagnostic object')
            detail[field]={key:bounded(value) for key,value in body[field].items() if key in allowed}
    check(detail.get('exception') or detail.get('termination'),'Missing exception/termination')
    asi=body.get('asi',{});check(type(asi) is dict and len(asi)<=8,'Application-specific module cap/type')
    application_specific={}
    for module,messages in asi.items():
        text(module,128);check(type(messages) is list and len(messages)<=8,'Application-specific message cap/type')
        application_specific[module]=[text(message,4096) for message in messages]
    check(len(encode(application_specific))<=16*1024,'Application-specific total byte cap')
    notes=body.get('reportNotes',[]);check(type(notes) is list and len(notes)<=16,'Report notes cap')
    result={'incident':incident,'input_sha256':digest(raw),'input_bytes':len(raw),'procPath':body['procPath'],
        'pid':body['pid'],'captureTime':body['captureTime'],'captured_unix':captured,
        'executable_uuid':binding['executable_uuid'],'debug_dylib_loaded':'debug_dylib' in owned,
        'owned_image_indexes':{k:remap[v] for k,v in owned.items()},'diagnostic':detail,
        'crashed_threads':crashed,'last_exception_backtrace':last,'images':projected_images,
        'report_notes':[text(note,2048) for note in notes],'application_specific':application_specific}
    if not verified_path:
        result['uuid_bound_image_indexes']=result.pop('owned_image_indexes')
        result['uuid_bound_image_path_matches']=image_path_matches
        result['uuid_bound_debug_dylib_loaded']=result.pop('debug_dylib_loaded')
    return result

def collect_reports(directory,binding,window):
    directory=Path(directory)
    for p in [directory,*directory.parents]:check(not p.is_symlink(),'Symlink report directory')
    if not directory.exists():return {'state':'complete','candidate_count':0,'matched_count':0,'incidents':[],'rejected':[]}
    check(directory.is_dir(),'Invalid report directory')
    candidates=[];count=0;fd=directory_fd(directory)
    try:
        with os.scandir(fd) as entries:
            for item in entries:
                count+=1;check(count<=MAX_DIRECTORY_ENTRIES,'Directory scan cap')
                if re.fullmatch(re.escape(NAME)+r'-[A-Za-z0-9_.-]+\.ips',item.name):candidates.append(directory/item.name)
                check(len(candidates)<=MAX_CANDIDATES,'Candidate scan cap')
    finally:os.close(fd)
    incidents=[];rejected=[];seen=set();read=0
    for path in sorted(candidates):
        remaining=MAX_TOTAL_INPUT-read;check(remaining>0,'Aggregate input cap before read')
        raw=safe_read(path,min(MAX_INPUT,remaining));read+=len(raw)
        try:row=projection(raw,binding,window)
        except OwnedCandidatePathMismatch as error:
            incident=error.observation['incident'];check(incident not in seen,'Duplicate incident ID');seen.add(incident)
            check(len(seen)<=MAX_INCIDENTS,'Identity-bound incident count cap')
            rejected.append({'name':path.name,'bytes':len(raw),'sha256':digest(raw),'error':str(error),
                'owned_path_mismatch':error.observation});continue
        except (ValueError,KeyError,TypeError,UnicodeError,RecursionError) as error:
            # Never publish unrelated/raw content or trust a reported filesystem
            # path. The fixed-prefix filename/hash/error is sufficient here.
            rejected.append({'name':path.name,'bytes':len(raw),'sha256':digest(raw),'error':text(str(error),256)});continue
        check(row['incident'] not in seen,'Duplicate incident ID');seen.add(row['incident']);incidents.append(row)
        check(len(seen)<=MAX_INCIDENTS,'Matching incident count cap')
    result={'state':'complete' if not rejected else 'incomplete-rejected-candidates','candidate_count':len(candidates),
        'matched_count':len(incidents),'incidents':incidents,'rejected':rejected}
    check(len(encode(result))<=MAX_OUTPUT-8192,'Projection byte cap')
    return result

def bound_product(root,context):
    app=Path(context['app_path']);expected=app/'Contents/PlugIns'/f'{NAME}.appex/Contents/MacOS'/NAME
    check(str(expected)==context['extension_executable'],'Unexpected context executable path')
    entries={row[0]:(row[1],row[2]) for row in context['bundle_manifest']}
    check(len(entries)==len(context['bundle_manifest']),'Duplicate product manifest path')
    result={}
    for label,path in [('executable',expected),('debug_dylib',Path(str(expected)+'.debug.dylib'))]:
        raw=safe_read(path,32*1024*1024);relative=str(path.relative_to(app))
        check(entries.get(relative)==(len(raw),digest(raw)),'Changed built '+label)
        if label=='executable':check(digest(raw)==context['extension_executable_sha256'],'Changed executable context hash')
        result.update({'expected_'+label:str(path),label+'_sha256':digest(raw),label+'_bytes':len(raw)})
    return result

def prepare(root,context,context_hash):
    bound=bound_product(root,context)
    for label in ['executable','debug_dylib']:
        path=bound['expected_'+label]
        value=subprocess.check_output(['/usr/bin/xcrun','dwarfdump','--uuid',path],text=True,timeout=8)
        # The qualified fresh runner/product is single-slice arm64. An unknown
        # multi-slice build is an incomplete diagnostic, never guessed identity.
        match=re.fullmatch(r'UUID: ([0-9A-Fa-f-]{36}) \(arm64\) '+re.escape(path)+r'\n?',value)
        check(match is not None,'Unexpected built Mach-O UUID record')
        bound[label+'_uuid']=uuid(match[1])
    return {'schema':'Celluloid.OwnedCrashIdentity.1','acceptance':False,'complete_host_e2e':False,'source_sha':context['source_sha'],
        'context_sha256':context_hash,'test_source_sha256':context['test_source_sha256'],
        'verifier_sha256':context['script_sha256'],'collector_sha256':digest(Path(__file__).read_bytes()),
        'extension_id':EXT_ID,**bound}

def capture(root,context,context_hash,directory):
    identity_raw=safe_read(root/IDENTITY,8192)
    identity=validate_diagnostic(identity_raw,context['source_sha'],IDENTITY)
    check(identity.get('schema')=='Celluloid.OwnedCrashIdentity.1','Missing crash identity')
    for key,wanted in [('source_sha',context['source_sha']),('context_sha256',context_hash),
        ('test_source_sha256',context['test_source_sha256']),('verifier_sha256',context['script_sha256']),
        ('collector_sha256',digest(Path(__file__).read_bytes())),('extension_id',EXT_ID)]:
        check(identity.get(key)==wanted,'Changed bound crash '+key)
    for key,wanted in bound_product(root,context).items():check(identity.get(key)==wanted,'Changed post-test product '+key)
    for label in ['executable','debug_dylib']:check(uuid(identity[label+'_uuid'])==identity[label+'_uuid'],'Invalid built UUID')
    log=safe_read(root/'mac-host-test.log',20_000_000).decode('utf8',errors='strict')
    summary_raw=safe_read(root/'mac-host-summary.json',160_000);summary=load_json(summary_raw)
    window=test_window(log,summary,context,context_hash);window['summary_sha256']=digest(summary_raw)
    result=collect_reports(directory,identity,window)
    return {'schema':'Celluloid.OwnedCrashProjection.1','acceptance':False,'complete_host_e2e':False,
        'source_sha':context['source_sha'],'identity':identity,'identity_sha256':digest(identity_raw),
        'window':window,'limits':limits(),**result}

def limits():
    return {'directory_entries':MAX_DIRECTORY_ENTRIES,'candidate_files':MAX_CANDIDATES,'matching_incidents':MAX_INCIDENTS,
        'input_file_bytes':MAX_INPUT,'total_input_bytes':MAX_TOTAL_INPUT,'output_bytes':MAX_OUTPUT,
        'frames_per_trace':MAX_FRAMES,'necessary_images':MAX_IMAGES}

def validate_diagnostic(raw,source,name):
    check(name in {IDENTITY,OUTPUT} and 0<len(raw)<=(8192 if name==IDENTITY else MAX_OUTPUT),'Diagnostic name/byte cap')
    row=load_json(raw)
    check(type(row) is dict and row.get('source_sha')==source and row.get('acceptance') is False and row.get('complete_host_e2e') is False,'Unbound/accepted crash diagnostic')
    expected='Celluloid.OwnedCrashIdentity.1' if name==IDENTITY else 'Celluloid.OwnedCrashProjection.1'
    check(row.get('schema') in {expected,'Celluloid.OwnedCrashCollectionError.1'},'Unknown crash diagnostic schema')
    if row['schema']=='Celluloid.OwnedCrashCollectionError.1':
        check(row.get('state')=='incomplete' and row.get('phase')==('prepare' if name==IDENTITY else 'capture'),'Wrong crash failure record')
        text(row.get('error'),256)
    elif name==OUTPUT:
        check(type(row.get('identity')) is dict and row['identity'].get('source_sha')==source,'Unbound crash identity')
        check(row.get('state') in {'complete','incomplete-rejected-candidates'},'Unknown crash projection state')
        check(type(row.get('incidents')) is list and type(row.get('matched_count')) is int and len(row['incidents'])==row['matched_count']<=MAX_INCIDENTS,'Projection incident cap')
    return row

def write_new(path,raw):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(raw)

def optional_budget(clock,source,action,now):
    # One actual job deadline, not a fresh timeout or a claim that the 840s
    # host step contains diagnostics. Mandatory allowances are never clipped.
    check(action in {'prepare','capture'} and type(clock) is dict,'Invalid optional budget phase')
    check(clock.get('source_sha')==source and type(clock.get('execution_budget_seconds')) is int and clock['execution_budget_seconds']==2460,'Wrong shared job clock')
    start=clock.get('started_monotonic');check(number(start) and number(now) and 0<start<=now,'Invalid shared monotonic clock')
    deadline=start+2460;reserve=1020 if action=='prepare' else 300;cleanup=12
    allowance=max(0,min(20,deadline-now-reserve-cleanup))
    if allowance<1:allowance=0
    return {'deadline_monotonic':deadline,'observed_monotonic':now,'mandatory_reserve_seconds':reserve,
            'cleanup_reserve_seconds':cleanup,'command_seconds':allowance,'admitted':allowance>0}

def error_record(source,action,error):
    return {'schema':'Celluloid.OwnedCrashCollectionError.1','acceptance':False,'complete_host_e2e':False,
            'source_sha':source,'phase':action,'state':'incomplete','limits':limits(),
            'error_type':type(error).__name__,'error':str(error)[:256]}

def bounded_optional_process(command,command_deadline,cleanup_deadline,cap=8192):
    """One owned session; finite reads and absolute deadlines, including pipe EOF.

    Do not poll/reap the leader while a descendant can retain the pipe. Its PID
    stays reserved until group cleanup, so a signal cannot target a reused PID.
    No change is made to the mandatory host command or shared run_bounded helper.
    """
    check(number(command_deadline) and number(cleanup_deadline) and time.monotonic()<command_deadline<cleanup_deadline,'Invalid/expired optional process deadlines')
    check(type(cap) is int and 0<cap<=8192,'Invalid optional output cap')
    check(signal.getsignal(signal.SIGCHLD)==signal.SIG_DFL,'Unknown child-reaping policy')
    started=time.monotonic();data=bytearray();eof=False;reaped=False;timed_out=False;overflow=False;cleanup_error=None
    process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True,bufsize=0)
    selector=None;pipe=process.stdout
    def drain(until):
        nonlocal eof,overflow
        while not eof and not overflow and time.monotonic()<until:
            if len(data)>=cap:overflow=True;break
            events=selector.select(max(0,min(0.1,until-time.monotonic())))
            for _,_ in events:
                if time.monotonic()>=until:break
                try:part=os.read(pipe.fileno(),min(4096,cap-len(data)))
                except BlockingIOError:continue
                if not part:eof=True;break
                data.extend(part)
    def signal_group(sig):
        nonlocal cleanup_error
        if reaped:return # Never signal after releasing the leader's PID.
        try:os.killpg(process.pid,sig)
        except ProcessLookupError:pass
        except OSError as error:cleanup_error=type(error).__name__
    try:
        selector=selectors.DefaultSelector()
        os.set_blocking(pipe.fileno(),False);selector.register(pipe,selectors.EVENT_READ)
        drain(command_deadline)
        if eof and not overflow:
            try:process.wait(timeout=max(0,command_deadline-time.monotonic()));reaped=True
            except subprocess.TimeoutExpired:timed_out=True
        else:timed_out=not overflow
        if not reaped:
            signal_group(signal.SIGTERM)
            term_deadline=min(cleanup_deadline,time.monotonic()+1)
            if not overflow:drain(term_deadline)
            # A completed leader may leave an ignoring descendant with the pipe.
            # Signal the same owned session before reaping that leader.
            signal_group(signal.SIGKILL)
            if not overflow:drain(cleanup_deadline)
            try:process.wait(timeout=max(0,cleanup_deadline-time.monotonic()));reaped=True
            except subprocess.TimeoutExpired:cleanup_error='direct child unreaped at absolute deadline'
    except (OSError,ValueError) as error:
        cleanup_error=type(error).__name__;signal_group(signal.SIGKILL)
        try:process.wait(timeout=max(0,cleanup_deadline-time.monotonic()));reaped=True
        except subprocess.TimeoutExpired:pass
    finally:
        if selector is not None:selector.close()
        pipe.close()
    finished=time.monotonic()
    if finished>command_deadline and not overflow:timed_out=True
    if finished>cleanup_deadline:cleanup_error='completion observed after absolute cleanup deadline'
    return {'return_code':process.returncode,'output':bytes(data),'bytes_read':len(data),'pipe_eof':eof,
        'child_reaped':reaped,'timed_out':timed_out,'overflow':overflow,'cleanup_error':cleanup_error,
        'finalized':eof and reaped and cleanup_error is None,'elapsed_seconds':finished-started,
        'command_deadline_monotonic':command_deadline,'cleanup_deadline_monotonic':cleanup_deadline}

def framework_dependencies(raw,expected_path):
    check(0<len(raw)<=8192,'Framework output cap')
    lines=raw.decode('utf8',errors='strict').splitlines()
    check(lines and lines[0]==expected_path+':' and len(lines)<=129,'Unexpected Mach-O dependency header/count')
    paths=[]
    for line in lines[1:]:
        match=re.fullmatch(r'\s+(\S+) \(compatibility version [0-9.]+, current version [0-9.]+\)',line)
        check(match is not None,'Malformed Mach-O dependency record')
        value=match[1];check(len(value.encode())<=2048 and value not in paths,'Duplicate/oversized Mach-O dependency')
        paths.append(value)
    public={name:[] for name in ['PhotosUI','Photos','AppKit']}
    for name in public:
        pattern=r'/System/Library/Frameworks/'+name+r'\.framework/(?:Versions/[A-Za-z0-9]+/)?'+name
        public[name]=[value for value in paths if re.fullmatch(pattern,value)]
        check(len(public[name])<=1,'Ambiguous public framework dependency')
    return {name:bool(values) for name,values in public.items()}

def observe_framework_links(root,context,identity,deadline):
    report={'schema':'Celluloid.OwnedFrameworkLinks.1','acceptance':False,'complete':False,
        'all_processes_finalized':True,'binaries':{},
        'scope':'Declared public framework dependencies only; not runtime load or extension-context qualification'}
    # Same bytes imply the UUID already measured by this completed identity child.
    # Recheck only exact context-derived files, never a report-provided path.
    actual=bound_product(root,context)
    for key,value in actual.items():check(identity.get(key)==value,'Changed framework-probe product '+key)
    for label in ['executable','debug_dylib']:
        check(uuid(identity[label+'_uuid'])==identity[label+'_uuid'],'Invalid framework-probe UUID')
    for label in ['executable','debug_dylib']:
        now=time.monotonic()
        if now+3>deadline:
            report['error']='Insufficient original prepare deadline';break
        path=actual['expected_'+label]
        try:result=bounded_optional_process(['/usr/bin/otool','-L',path],now+2,now+3,cap=8192)
        except FileNotFoundError as error:
            # Popen failed to exec this fixed tool and returned no child handle.
            # Do not erase a valid identity for a provably unstarted observation.
            if error.errno!=errno.ENOENT or error.filename!='/usr/bin/otool':raise
            report['binaries'][label]={'binary_sha256':actual[label+'_sha256'],'binary_uuid':identity[label+'_uuid'],
                'execution_state':'not-started','error':'Declared-dependency tool unavailable'}
            break
        except ValueError as error:
            # This exact immutable runner guard executes before Popen. All other
            # exceptions keep the conservative blocking behavior.
            if str(error)!='Invalid/expired optional process deadlines':raise
            report['binaries'][label]={'binary_sha256':actual[label+'_sha256'],'binary_uuid':identity[label+'_uuid'],
                'execution_state':'not-started','error':'Original observation deadline expired before spawn'}
            break
        row={'binary_sha256':actual[label+'_sha256'],'binary_uuid':identity[label+'_uuid'],
            'output_sha256':digest(result['output']),'process':{k:v for k,v in result.items() if k!='output'}}
        report['binaries'][label]=row
        report['all_processes_finalized']=report['all_processes_finalized'] and result['finalized']
        if not result['finalized']:
            row['error']='Framework process/pipe completion unconfirmed';break
        if result['timed_out'] or result['overflow'] or result['return_code']!=0:
            row['error']='Framework probe time/output/exit failure';break
        try:row['public_frameworks']=framework_dependencies(result['output'],path)
        except (ValueError,UnicodeError) as error:row['error']=str(error)[:128];break
    if report['all_processes_finalized']:
        for key,value in bound_product(root,context).items():check(identity.get(key)==value,'Changed post-probe product '+key)
    report['complete']=time.monotonic()<=deadline and len(report['binaries'])==2 and all('public_frameworks' in value for value in report['binaries'].values())
    return report

def optional_execute(root,context,context_hash,action):
    source=context['source_sha'];output=root/(IDENTITY if action=='prepare' else OUTPUT);decision=None;finalized=False;process_record=None
    check(not output.exists() and not output.is_symlink(),'Duplicate optional diagnostic output')
    try:
        if action=='capture':
            # No new diagnostic child after an unknown host/identity termination.
            previous=validate_diagnostic(safe_read(root/IDENTITY,8192),source,IDENTITY)
            check(previous.get('schema')=='Celluloid.OwnedCrashIdentity.1' and previous.get('optional_execution',{}).get('finalized') is True,'Unfinalized identity diagnostic')
            log=safe_read(root/'mac-host-test.log',20_000_000).decode('utf8',errors='strict')
            summary=load_json(safe_read(root/'mac-host-summary.json',160_000))
            test_window(log,summary,context,context_hash)
            product=load_json(safe_read(root/'mac-host-product-after.json',160_000))
            source_after=load_json(safe_read(root/'mac-host-source-after.json',160_000))
            check(product.get('installed_bytes_unchanged') is True and product.get('strict_signatures_unchanged') is True,'Unfinalized mandatory product work')
            check(all(product.get(key)==context[key] for key in ['app_executable_sha256','extension_executable_sha256']),'Changed mandatory product identity')
            check(source_after.get('source_sha')==source and source_after.get('phase')=='after','Unfinalized mandatory source work')
        clock_raw=safe_read(root/'mac-job-clock.json',160_000);clock=load_json(clock_raw)
        mandatory_budget=load_json(safe_read(root/'mac-host-budget.json',160_000))
        check(mandatory_budget.get('source_sha')==source and mandatory_budget.get('clock_sha256')==digest(clock_raw),'Changed mandatory job-clock binding')
        decision=optional_budget(clock,source,action,time.monotonic());decision['clock_sha256']=digest(clock_raw)
        check(decision['admitted'],'Insufficient spare job time; mandatory host/evidence reserve preserved')
        command=[sys.executable,str(Path(__file__).resolve()),action]
        # Use the admission instant, never a renewed window after slow spawning.
        command_deadline=decision['observed_monotonic']+decision['command_seconds']
        # Ten seconds for process/pipe cleanup; two of the twelve reserved seconds
        # remain for bounded receipt validation and finalization.
        result=bounded_optional_process(command,command_deadline,command_deadline+10)
        process_record={key:value for key,value in result.items() if key!='output'}
        process_record['output_sha256']=digest(result['output'])
        finalized=result['finalized']
        check(finalized,'Optional process/pipe completion unconfirmed')
        check(not result['timed_out'] and not result['overflow'] and result['return_code']==0,'Optional diagnostic failed its absolute time/output bound')
        row=validate_diagnostic(safe_read(output,8192 if action=='prepare' else MAX_OUTPUT),source,output.name)
        if action=='prepare':
            row['framework_link_observation']=observe_framework_links(root,context,row,command_deadline)
            finalized=finalized and row['framework_link_observation']['all_processes_finalized']
    except (ValueError,KeyError,TypeError,OSError,UnicodeError,subprocess.SubprocessError,RecursionError) as error:
        row=error_record(source,action,error)
    row['optional_execution']={'budget':decision,'finalized':finalized,'process':process_record}
    raw=encode(row);check(len(raw)<=(8192 if action=='prepare' else MAX_OUTPUT),'Final optional diagnostic cap')
    # Replace only this invocation's own fixed output after validating the child.
    temporary=output.with_name(output.name+'.final');write_new(temporary,raw);os.replace(temporary,output)
    return row

def main():
    import argparse
    import mac_photos_host_gate as gate
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','capture','optional-prepare','optional-capture']);args=parser.parse_args()
    gate.require_runner();root=gate.temp()
    source=os.environ['GITHUB_SHA'];output=root/(IDENTITY if args.action=='prepare' else OUTPUT)
    if args.action.startswith('optional-'):
        context=gate.context();context_hash=digest(safe_read(root/'mac-host-context.json',500_000))
        optional_execute(root,context,context_hash,args.action.removeprefix('optional-'));return
    try:
        context=gate.context();context_hash=digest(safe_read(root/'mac-host-context.json',500_000))
        if args.action=='prepare':row=prepare(root,context,context_hash)
        else:row=capture(root,context,context_hash,Path.home()/'Library/Logs/DiagnosticReports')
        raw=encode(row);check(len(raw)<=(8192 if args.action=='prepare' else MAX_OUTPUT),'Final diagnostic byte cap')
    except (ValueError,KeyError,TypeError,OSError,UnicodeError,subprocess.SubprocessError,AssertionError,RecursionError) as error:
        row={'schema':'Celluloid.OwnedCrashCollectionError.1','acceptance':False,'complete_host_e2e':False,
             'source_sha':source,'phase':args.action,'state':'incomplete','limits':limits(),
             'error_type':type(error).__name__,'error':str(error)[:256]}
        raw=encode(row)
    write_new(output,raw)
    print('MAC_HOST_OWNED_CRASH '+json.dumps({'phase':args.action,'state':row.get('state','identity-recorded'),
        'source_sha':source,'bytes':len(raw),'sha256':digest(raw),'acceptance':False},sort_keys=True))

if __name__=='__main__':main()
