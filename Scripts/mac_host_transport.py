"""Bounded, fixed-name stdout handoff from sandboxed XCTest to its outer runner."""
import base64,hashlib,json,math,re
from pathlib import Path

PREFIX='MAC_HOST_PROOF '
SCHEMA='Celluloid.MacHostProof.1'
CASE=('CelluloidMacUITests.MacPhotosHostUITests','testInstalledExtensionIsInvokedByActualPhotos')
LABEL='actual-mac-photos-host-prerequisite'
ORDER=['transport.json','containing-process.json','photos-process.json','fixture.json','fixture-ownership.json',
       'registration-before-invoke.txt','registration-before-invoke.json','extension-process.json',
       'registration-selected.txt','registration-selected.json','prerequisite.json','outcome.json']
LIMITS={name:120_000 if name.endswith('.txt') or name=='fixture.json' else 16_000 for name in ORDER}
TOTAL=160_000
DIAGNOSTIC_NAMES={name+'.txt' for name in ['registration-before','initial','imported','single-photo','editing','extensions','manage-observed','host-editor','last-observed','missing-control-edit','missing-control-extensions']}|{'extensions.jpg','last-observed.jpg'}
ATTACHMENT_PREFIX='celluloid-host-diagnostic-'

def require(value,message):
    if not value:raise ValueError(message)
def sha(data):return hashlib.sha256(data).hexdigest()
def unique(pairs):
    result={}
    for k,v in pairs:
        require(k not in result,'Duplicate JSON key');result[k]=v
    return result

def load_json(data):
    def nonfinite(value):raise ValueError('Nonfinite JSON number: '+value)
    def finite_real(value):
        number=float(value)
        require(math.isfinite(number),'Nonfinite JSON number: '+value)
        return number
    return json.loads(data,object_pairs_hook=unique,parse_constant=nonfinite,parse_float=finite_real)

def expected_transport(context,context_hash):
    return {'schema':'Celluloid.HostTransport.1','source_sha':context['source_sha'],'context_sha256':context_hash,
        'test_source_sha256':context['test_source_sha256'],'verifier_sha256':context['script_sha256'],
        'app_executable_sha256':context['app_executable_sha256'],'extension_executable_sha256':context['extension_executable_sha256'],
        'external_writes':False,'context_validated':True}

def parse(log,context,context_hash,complete=False):
    require(type(log) is str and 0<len(log.encode())<=20_000_000,'Missing/oversized host transcript')
    for name,value in [('context',context_hash),('test',context['test_source_sha256']),('verifier',context['script_sha256'])]:
        require(type(value) is str and re.fullmatch('[0-9a-f]{64}',value),'Malformed '+name+' identity')
    require(re.fullmatch('[0-9a-f]{40}',context['source_sha']) is not None,'Malformed source identity')
    cases=[];records={};rows=[];total=0;starts=[];ends=[];terminals=[];timeouts=[];active=False;last_rank=-1
    case_re=re.compile(r"Test Case '-\[([\w.]+) (\w+)\]' (started\.|(passed|failed|skipped) \([0-9]+(?:\.[0-9]+)? seconds\)\.)")
    for position,line in enumerate(log.splitlines()):
        stripped=line.strip()
        if stripped.lower().startswith('test case '):
            match=case_re.fullmatch(line);require(match is not None,'Malformed host testcase event')
            require((match[1],match[2])==CASE,'Unexpected host testcase')
            state='started' if match[3]=='started.' else match[4];cases.append((state,position));active=state=='started'
        if stripped.startswith('BOUNDED_COMMAND_BEGIN'):
            require(line.startswith('BOUNDED_COMMAND_BEGIN '),'Malformed process begin')
            value=load_json(line.split(' ',1)[1]);starts.append((value,position))
        if stripped.startswith('BOUNDED_COMMAND_END'):
            require(line.startswith('BOUNDED_COMMAND_END '),'Malformed process end')
            value=load_json(line.split(' ',1)[1]);ends.append((value,position))
        if stripped.startswith(('BOUNDED_COMMAND_TIMEOUT','BOUNDED_TIMEOUT_')):timeouts.append((stripped,position))
        elif stripped.startswith('BOUNDED_COMMAND_') and not stripped.startswith(('BOUNDED_COMMAND_BEGIN ','BOUNDED_COMMAND_END ')):
            raise ValueError('Unknown/contradictory bounded process record')
        if stripped.startswith('** TEST EXECUTE '):terminals.append((stripped,position))
        if 'MAC_HOST_PROOF' not in line:continue
        require(line.startswith(PREFIX) and len(line.encode())<=220_000,'Malformed/oversized host proof record')
        require(active and len(cases)==1,'Host proof outside its exact active XCTest')
        row=load_json(line[len(PREFIX):])
        require(type(row) is dict and set(row)=={'schema','sequence','name','bytes','sha256','source_sha','context_sha256','test_source_sha256','verifier_sha256','base64'},'Unknown/missing host proof field')
        require(row['schema']==SCHEMA and type(row['sequence']) is int and row['sequence']==len(rows),'Duplicate/out-of-order host proof sequence')
        name=row['name'];require(type(name) is str and name in ORDER and name not in records,'Unexpected/duplicate host proof name')
        rank=ORDER.index(name);require(rank>last_rank and (rows or name=='transport.json'),'Out-of-order host proof name');last_rank=rank
        for key,wanted in [('source_sha',context['source_sha']),('context_sha256',context_hash),('test_source_sha256',context['test_source_sha256']),('verifier_sha256',context['script_sha256'])]:require(row[key]==wanted,'Wrong bound host proof '+key)
        require(type(row['base64']) is str and len(row['base64'])<=4*((LIMITS[name]+2)//3),'Oversized encoded host proof')
        data=base64.b64decode(row['base64'],validate=True)
        require(type(row['bytes']) is int and 0<len(data)==row['bytes']<=LIMITS[name] and row['sha256']==sha(data),'Host proof byte/hash mismatch')
        total+=len(data);require(total<=TOTAL,'Host proof total byte bound')
        if name.endswith('.json'):
            payload=load_json(data);require(type(payload) is dict,'Host proof payload is not an object')
            if name=='transport.json':
                require(payload==expected_transport(context,context_hash) and payload.get('external_writes') is False and payload.get('context_validated') is True,'First host transport validation mismatch')
        else:data.decode('utf8',errors='strict')
        records[name]=data;rows.append(row)
    require(len(starts)==len(ends)==1 and len(cases)==2 and cases[0][0]=='started' and cases[1][0] in {'passed','failed','skipped'},'Incomplete/duplicate host process or test')
    begin,bp=starts[0];end,ep=ends[0]
    require(begin.get('label')==end.get('label')==LABEL and begin.get('seconds')==720,'Wrong bounded host process')
    command=begin.get('command');require(type(command) is list and all(type(x) is str for x in command),'Malformed host command')
    require(command and command[0]=='xcodebuild' and command.count('-only-testing:'+CASE[0].split('.')[0]+'/'+CASE[0].split('.')[1]+'/'+CASE[1])==1 and command.count('test-without-building')==1,'Wrong host process/test selection')
    require(type(end.get('exit_code')) is int and type(end.get('elapsed_seconds')) in (int,float) and math.isfinite(end['elapsed_seconds']) and 0<=end['elapsed_seconds']<=735,'Unfinalized host process result')
    require(bp<cases[0][1]<cases[1][1]<ep,'Host process/test boundaries contradict')
    require(records and list(records)[0]=='transport.json','Missing first host transport validation')
    require(not timeouts or (cases[-1][0]!='passed' and end['exit_code']!=0),'Contradictory bounded process timeout')
    if complete:
        require(not timeouts,'Bounded process timeout/abort cannot grant acceptance')
        require(list(records)==ORDER,'Missing required host proof')
        require(cases[-1][0]=='passed' and end['exit_code']==0,'Host process/test did not pass')
        require(len(terminals)==1 and terminals[0][0]=='** TEST EXECUTE SUCCEEDED **' and cases[-1][1]<terminals[0][1]<ep,'Missing/contradictory finalized xcodebuild result')
    return records

def attachment_candidates(folder,manifest):
    """Only selected fixed names and direct owned export files may be copied."""
    folder=Path(folder);require(folder.is_dir() and not folder.is_symlink(),'Invalid attachment export directory')
    require(type(manifest) is list and len(manifest)<=16,'Malformed attachment manifest')
    result={};seen=set()
    for record in manifest:
        require(type(record) is dict and type(record.get('attachments')) is list and len(record['attachments'])<=64,'Malformed attachment record')
        for item in record['attachments']:
            require(type(item) is dict,'Malformed attachment item')
            name=item.get('suggestedHumanReadableName');exported=item.get('exportedFileName')
            require(type(exported) is str and Path(exported).name==exported and exported not in {'','.','..'} and exported not in seen,'Unexpected/duplicate attachment path')
            seen.add(exported);path=folder/exported
            require(path.is_file() and not path.is_symlink() and path.resolve().parent==folder.resolve(),'Unowned attachment path')
            if type(name) is not str or not name.startswith(ATTACHMENT_PREFIX):continue
            # xcresulttool appends its observed iteration/UUID/type suffix to
            # the user-set attachment name. Parse only that exact bounded form.
            suffix=re.fullmatch(re.escape(ATTACHMENT_PREFIX)+r'(.+)_(0)_([0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12})\.(txt|jpg|jpeg)',name)
            require(suffix is not None,'Unexpected host attachment display name')
            selected=suffix[1]
            require(selected in DIAGNOSTIC_NAMES and selected not in result,'Unexpected/duplicate named host attachment')
            require(record.get('testIdentifier')=='MacPhotosHostUITests/'+CASE[1]+'()','Host attachment belongs to another test')
            require((selected.endswith('.txt') and suffix[4]=='txt') or (selected.endswith('.jpg') and suffix[4] in {'jpg','jpeg'}),'Unexpected host attachment extension')
            limit=700_000 if selected.endswith('.jpg') else 120_000
            require(0<path.stat().st_size<=limit,'Oversized host diagnostic attachment')
            data=path.read_bytes()
            if selected.endswith('.jpg'):require(data.startswith(b'\xff\xd8\xff'),'Wrong diagnostic JPEG type')
            else:data.decode('utf8',errors='strict')
            result[selected]=data
    return result
