#!/usr/bin/env python3
"""Closed one-asset writer/Photos diagnostic; never extension or release acceptance."""
import base64,hashlib,json,math,os,plistlib,re,stat,subprocess,sys,time
from pathlib import Path
from xml.parsers.expat import ExpatError
from owned_mac_photos_runner import run
from mac_host_lifecycle_pixels import decode,compare

ROOT=Path(__file__).resolve().parents[1]
BASE='13e9a1ed63c6e7744803419f27e429a759df1209'
BASE_TREE='f2c6d0f38c026957b0b34f22b916eb80ed5b20a8'
BRANCH='celluloid-final-mac-photos-compile-observation'
WORKFLOW='.github/workflows/final-mac-photos-compile-observation.yml'
CONFIG='.github/final-mac-roundtrip.json'
MANIFEST='.github/final-mac-roundtrip-source.json'
PRODUCT='.github/final-mac-photos-product.json'
TEST='Diagnostics/MacPhotosRoundtripTests.swift'
WRITER='CelluloidPhotoExtension/PhotosOutputWrite.swift'
SCRIPT='Scripts/mac_photos_roundtrip.py'
PROJECT='CelluloidPhotosRoundtrip.xcodeproj'
SELECTION='CelluloidMacUITests/MacPhotosRoundtripTests/testOwnedWriterJPEGPhotosRoundtrip'
RAW_CASE='-[CelluloidMacUITests.MacPhotosRoundtripTests testOwnedWriterJPEGPhotosRoundtrip]'
PREFIX='MAC_PHOTOS_ROUNDTRIP_PROOF '
CAP=1_000_000
RESERVE=32_000
PAIR=('27.0.1','26A434')
OBSERVED_PAIRS=(('27.0','26A428'),PAIR)
INPUTS={
 'source':('Platforms/MacExtensionTests/Fixtures/lifecycle-source.png',19268,'6138992615dd7d5bd499b80d9f11e39a0815111feccd5d4d3e59a676f4384772'),
 'jpeg':('Diagnostics/Fixtures/intended.jpg',23586,'1f6b8bb3ea7963c0663965da27c9b41e717335b3d4a6f011a70e83762c1904ba'),
 'expected':('Diagnostics/Fixtures/lifecycle-expected-save.png',16565,'4ff9356c945d26d5feb3c7254a5181b17fb10692f15fa0f529375b3568da9979'),
 'historical':('Diagnostics/Fixtures/lifecycle-saved.png',18170,'342f7d0ff2a681687e42b2e5ada1338018ce2538aae17be115d958c98f24cde5')}
EXPECTED_RGBA='eacc2ada4af742470b52d2ed14996d07e71db7c2b68b2da4f7947efcc7f9855a'
HISTORICAL_RGBA='744dfa09d6ab997552cdb11393a53761c8e098ffd37e6a8c3a9febdfd0972c99'
NAMES=('writer-committed.jpg','photos-original.jpg','photos-roundtrip.png')
IMPORT_FAILURE='Owned import filename not uniquely selected; no import action'
IMPORT_NAMES=('writer-committed.jpg','import-ax.json','import-panel.png')
IMPORT_ERROR='failed: caught error: \"Error Domain=Celluloid.OwnedPhotosRoundtrip Code=1 \"'+IMPORT_FAILURE+'\" UserInfo={NSLocalizedDescription='+IMPORT_FAILURE+'}\"'
ADDITIONS={PRODUCT,CONFIG,MANIFEST,WORKFLOW,SCRIPT,'Scripts/owned_mac_photos_runner.py',
 'Scripts/test_mac_photos_roundtrip.py',TEST,PROJECT+'/project.pbxproj',PROJECT+'/xcshareddata/xcschemes/CelluloidMacUI.xcscheme',PROJECT+'/xcshareddata/xcschemes/CelluloidMac.xcscheme',
 *(row[0] for name,row in INPUTS.items() if name!='source')}

def require(ok,message):
 if not ok:raise ValueError(message)
def sha(data):return hashlib.sha256(data).hexdigest()
def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def load_json(raw):
 def pairs(rows):
  result={}
  for k,v in rows:
   require(k not in result,'duplicate JSON key');result[k]=v
  return result
 def real(s):
  v=float(s);require(math.isfinite(v),'nonfinite JSON');return v
 return json.loads(raw,object_pairs_hook=pairs,parse_float=real,parse_constant=lambda s:require(False,'nonfinite JSON'))
def git(*args):return subprocess.check_output(['git','-C',str(ROOT),*args],timeout=20).decode().strip()
def commit_parents(raw):
 require(type(raw) is str and '\n\n' in raw,'malformed commit')
 headers=raw.split('\n\n',1)[0].splitlines()
 require(bool(headers) and re.fullmatch('tree [0-9a-f]{40}',headers[0]),'malformed commit tree')
 rows=[r for r in headers if r.startswith('parent')]
 require(all(re.fullmatch('parent [0-9a-f]{40}',r) for r in rows),'malformed parent')
 return [r[7:] for r in rows]
def validate_route(env):
 ref='refs/heads/'+BRANCH
 require(env.get('GITHUB_REPOSITORY')=='100mango/Celluloid' and env.get('GITHUB_EVENT_NAME')=='push' and env.get('GITHUB_REF')==ref,'wrong route')
 require(env.get('CELLULOID_VALIDATION_SCOPE')=='photos-import-compile-observation','wrong scope')
 require(env.get('GITHUB_WORKFLOW_REF')=='100mango/Celluloid/'+WORKFLOW+'@'+ref,'wrong workflow')
 head=env.get('GITHUB_SHA')
 require(type(head) is str and re.fullmatch('[0-9a-f]{40}',head) and head==env.get('GITHUB_WORKFLOW_SHA'),'wrong source SHA')
 require(env.get('GITHUB_RUN_ATTEMPT')=='1' and re.fullmatch('[1-9][0-9]*',env.get('GITHUB_RUN_ID','')),'wrong run/attempt')
 return head

def owned_read(path,cap):
 path=Path(path);parent=path.parent
 require(parent==parent.resolve(strict=True) and not path.is_symlink(),'owned path alias')
 dfd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  db=os.fstat(dfd);require(db.st_uid==os.getuid(),'foreign owned directory')
  fd=os.open(path.name,os.O_RDONLY|os.O_NONBLOCK|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=dfd)
  try:
   b=os.fstat(fd);require(stat.S_ISREG(b.st_mode) and b.st_nlink==1 and b.st_uid==os.getuid() and 0<b.st_size<=cap,'owned file type/size/owner')
   raw=b''
   while len(raw)<b.st_size:
    chunk=os.read(fd,min(65536,b.st_size-len(raw)));require(bool(chunk),'truncated owned file');raw+=chunk
   require(os.read(fd,1)==b'','grown owned file')
   snap=lambda v:(v.st_dev,v.st_ino,v.st_mode,v.st_uid,v.st_nlink,v.st_size,v.st_mtime_ns,v.st_ctime_ns)
   require(snap(b)==snap(os.fstat(fd))==snap(os.stat(path.name,dir_fd=dfd,follow_symlinks=False)),'owned file changed')
   de=os.lstat(parent);require((db.st_dev,db.st_ino,db.st_uid,db.st_mode)==(de.st_dev,de.st_ino,de.st_uid,de.st_mode),'owned parent replaced')
   return raw
  finally:os.close(fd)
 finally:os.close(dfd)

def source_snapshot(root=ROOT):
 product=load_json(owned_read(root/PRODUCT,524288))
 require(product.get('schema')=='Celluloid.FinalMacPhotosSource.1' and product.get('product_sha')==BASE and product.get('product_tree')==BASE_TREE,'product binding')
 rows=product.get('files');git_rows=product.get('git_files')
 require(type(rows) is list and len(rows)==962 and rows==sorted(rows) and len({r[0] for r in rows})==962,'product inventory')
 require(type(git_rows) is list and len(git_rows)==962 and [r[0] for r in rows]==[r[0] for r in git_rows],'product Git inventory')
 require(sha(json.dumps(rows,separators=(',',':')).encode())==product['fingerprint'],'product fingerprint')
 for (rel,digest),(grel,mode,blob) in zip(rows,git_rows):
  require(rel==grel and not Path(rel).is_absolute() and '..' not in Path(rel).parts,'product path')
  raw=owned_read(root/rel,32*1024*1024);actual_mode='100755' if (root/rel).stat().st_mode&stat.S_IXUSR else '100644'
  require(sha(raw)==digest and actual_mode==mode and hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==blob,'changed product '+rel)
 manifest=load_json(owned_read(root/MANIFEST,262144))
 require(set(manifest)=={'schema','parent','files'} and manifest['schema']=='Celluloid.OwnedPhotosRoundtripSource.1' and manifest['parent']==BASE,'source manifest')
 full=manifest['files'];require(type(full) is list and full==sorted(full,key=lambda r:r['path']),'source ordering')
 names=[]
 for row in full:
  require(type(row) is dict and set(row)=={'path','mode','bytes','sha256'},'source row')
  rel=row['path'];require(type(rel) is str and rel!=MANIFEST and rel not in names and not Path(rel).is_absolute() and '..' not in Path(rel).parts,'source path');names.append(rel)
  raw=owned_read(root/rel,32*1024*1024);mode='100755' if (root/rel).stat().st_mode&stat.S_IXUSR else '100644'
  require(type(row['bytes']) is int and len(raw)==row['bytes'] and sha(raw)==row['sha256'] and mode==row['mode'],'source mismatch '+rel)
 require(set(names)|{MANIFEST}=={r[0] for r in rows}|ADDITIONS,'complete source inventory')
 for rel,n,digest in INPUTS.values():
  raw=owned_read(root/rel,65536);require(len(raw)==n and sha(raw)==digest,'fixed diagnostic input changed')
 return product,{'source_fingerprint':sha(encoded(full)),'source_manifest_sha256':sha(owned_read(root/MANIFEST,262144)),'files':len(names)+1}

def admit_source(env=None,get_git=git,root=ROOT):
 env=os.environ if env is None else env
 require(sys.flags.optimize==0 and __debug__,'normal Python required')
 config=load_json(owned_read(root/CONFIG,4096))
 require(config=={'enabled':True,'product_sha':BASE,'purpose':'compile-only owned Import diagnostic; no XCTest case, writer, Photos or release acceptance'},'CLOSED diagnostic; activation review required')
 require(sys.platform=='darwin' and env.get('GITHUB_ACTIONS')=='true' and env.get('DEVELOPER_DIR')=='/Applications/Xcode_27.app/Contents/Developer','fixed fresh native runner required')
 head=validate_route(env)
 require(get_git('rev-parse','HEAD')==head and commit_parents(get_git('cat-file','-p','HEAD'))==[BASE],'HEAD must have sole13e9 parent')
 require(get_git('rev-parse',BASE+'^{tree}')==BASE_TREE,'wrong parent tree')
 require(not get_git('status','--porcelain','--untracked-files=all'),'dirty checkout')
 require(set(get_git('diff','--name-status',BASE,'HEAD','--').splitlines())=={'A\t'+p for p in ADDITIONS},'unreviewed source delta')
 product,binding=source_snapshot(root)
 expected='\n'.join(f'{mode} blob {blob}\t{rel}' for rel,mode,blob in product['git_files'])
 require(get_git('-c','core.quotepath=false','ls-tree','-r',BASE)==expected,'manifest not actual product tree')
 require(set(get_git('-c','core.quotepath=false','ls-files').splitlines())=={r[0] for r in product['files']}|ADDITIONS,'extra/missing tracked source')
 return dict(binding,schema='Celluloid.OwnedPhotosRoundtripSourceReceipt.1',source_sha=head,tree=get_git('rev-parse','HEAD^{tree}'),parent=BASE,run_id=env['GITHUB_RUN_ID'],run_attempt=1)

def runtime_record(version,build,architecture):
 require(all(type(v) is str for v in (version,build,architecture)) and (version,build) in OBSERVED_PAIRS and architecture=='arm64','unknown/crossed runtime pair')
 require((version,build)==PAIR,'runtime differs from historical boundary; stop before Photos')
 return {'platform':'macOS','osVersion':version,'osBuildNumber':build,'architecture':architecture,'diagnostic_only':True,'qualification_equivalence':False}

def command(temp,action):
 require(action in ('build-for-testing','build','test-without-building'),'unadmitted action')
 args=['xcodebuild','-project',PROJECT,'-scheme','CelluloidMacUI' if action!='build' else 'CelluloidMac','-configuration','Debug','-destination','platform=macOS','-derivedDataPath',str(temp/'celluloid-roundtrip')]
 if action=='test-without-building':
  args+=['-resultBundlePath',str(temp/'MacPhotosRoundtrip.xcresult'),'-parallel-testing-enabled','NO','-collect-test-diagnostics','never','-maximum-test-execution-time-allowance','960','-only-testing:'+SELECTION,'CODE_SIGNING_ALLOWED=NO','CELLULOID_EXPECT_SANDBOX=YES']
 else:args+=['CODE_SIGNING_ALLOWED=YES','CODE_SIGNING_REQUIRED=YES','CODE_SIGN_IDENTITY=-','CODE_SIGN_STYLE=Manual']+(['CELLULOID_EXPECT_SANDBOX=YES'] if action=='build-for-testing' else ['ENABLE_TESTABILITY=NO'])
 return args+[action]

def app_entitlement_observation(text,action):
 require(action in ('build-for-testing','build') and type(text) is str,'app entitlement source')
 raw=text.encode();require(0<len(raw)<=8192,'app entitlement output cap')
 start=text.find('<?xml');end=text.find('</plist>',start)
 require(start>=0 and end>=start and text.count('<?xml')==text.count('</plist>')==1,'entitlement plist')
 plist=text[start:end+8].encode()
 try:rights=plistlib.loads(plist)
 except (ValueError,TypeError,OverflowError,ExpatError) as error:raise ValueError('malformed entitlement plist') from error
 require(type(rights) is dict and all(type(key) is str for key in rights),'entitlement dictionary')
 require(len(encoded(rights))<=8192,'parsed app entitlement cap')
 return {'build_action':action,'scheme':'CelluloidMacUI' if action=='build-for-testing' else 'CelluloidMac',
  'output_bytes':len(raw),'output_sha256':sha(raw),'plist_bytes':len(plist),'plist_sha256':sha(plist),'entitlements':rights}

def admit_log_prefix(log,event,context,context_bytes,bundle):
 require(type(log) is str and 0<len(log.encode())<=256000,'native log cap')
 require(event.get('returned_without_timeout') is True and type(event.get('return_code')) is int and event['return_code'] in (0,65)
  and type(event.get('elapsed_seconds')) in (int,float) and 0<event['elapsed_seconds']<=1020,'native command not finalized')
 rows=log.splitlines();cases=[(i,r.strip()) for i,r in enumerate(rows) if r.strip().lower().startswith('test case ')]
 state='passed' if event['return_code']==0 else 'failed'
 require(len(cases)==2 and cases[0][1]=="Test Case '"+RAW_CASE+"' started." and re.fullmatch(re.escape("Test Case '"+RAW_CASE+"' "+state)+r' \([0-9]+(?:\.[0-9]+)? seconds\)\.',cases[1][1]),'wrong/missing native case')
 ends=[(i,r.strip()) for i,r in enumerate(rows) if re.match(r'^\*\* TEST(?: EXECUTE)?\b',r.strip(),re.I)]
 require(len(ends)==1 and ends[0][1]=='** TEST EXECUTE '+('SUCCEEDED' if state=='passed' else 'FAILED')+' **' and cases[1][0]<ends[0][0],'native terminal mismatch')
 paths=[r.strip() for r in rows if r.strip().startswith('/') and r.strip().endswith('.xcresult')]
 require(paths in ([bundle],[bundle,bundle]),'wrong native result path')
 proofs=[(i,r) for i,r in enumerate(rows) if 'MAC_PHOTOS_ROUNDTRIP_PROOF' in r]
 require(len(proofs)==1 and cases[0][0]<proofs[0][0]<cases[1][0] and proofs[0][1].startswith(PREFIX),'missing/duplicate/outside-case proof')
 envelope=load_json(proofs[0][1][len(PREFIX):])
 keys={'schema','source_sha','context_sha256','test_source_sha256','writer_source_sha256','script_sha256','bytes','sha256','base64'}
 require(type(envelope) is dict and set(envelope)==keys and envelope['schema']=='Celluloid.OwnedPhotosRoundtripProof.1','wrong proof envelope')
 for k in ('source_sha','test_source_sha256','writer_source_sha256','script_sha256'):require(envelope[k]==context[k],'unbound proof '+k)
 require(envelope['context_sha256']==sha(context_bytes),'unbound context')
 require(type(envelope['base64']) is str and len(envelope['base64'])<=4*((32000+2)//3),'proof encoding cap')
 raw=base64.b64decode(envelope['base64'],validate=True)
 require(type(envelope['bytes']) is int and 0<len(raw)==envelope['bytes']<=32000 and sha(raw)==envelope['sha256'],'proof bytes/hash')
 proof=load_json(raw);require(type(proof) is dict and proof.get('schema')=='Celluloid.OwnedPhotosRoundtripReceipt.1','receipt schema')
 for k in ('source_sha','run_id','run_attempt','runtime'):require(proof.get(k)==context[k] and type(proof.get(k)) is type(context[k]),'receipt binding '+k)
 require(proof.get('context_sha256')==sha(context_bytes),'receipt context')
 return raw,proof

def admit_log(log,event,context,context_bytes,bundle):
 raw,proof=admit_log_prefix(log,event,context,context_bytes,bundle)
 rows=log.splitlines()
 require(proof.get('complete') is True and proof.get('stage')=='png-exported','incomplete diagnostic; no post-failure attachment operation')
 require(proof.get('actual_extension_writer_observed') is False and proof.get('actual_photos_callback_observed') is False and proof.get('qualification_equivalence') is False,'unproven acceptance claim')
 for key,wanted in [('allowed_max_channel_delta',2),('writer_start_count',1),('initial_asset_count',0),('imported_asset_count',1)]:
  require(type(proof.get(key)) is int and proof[key]==wanted,'wrong exact diagnostic count '+key)
 for key in ('inputs_checked','writer_claim_succeeded','writer_reservation_completed','binary_scalar_self_tested'):require(proof.get(key) is True,'missing diagnostic check '+key)
 require(type(proof.get('case_elapsed_seconds')) in (int,float) and 0<proof['case_elapsed_seconds']<=900,'test deadline')
 require(proof.get('phases')==['reference','writer-committed','imported','original-exported','png-exported'],'phase sequence')
 require(proof.get('source_fixture_sha256')==INPUTS['source'][2] and all(proof.get(k)==INPUTS['jpeg'][2] for k in ('jpeg_sha256','writer_committed_sha256','unmodified_original_sha256')),'input/writer/original mismatch')
 require(proof.get('expected_rgba_sha256')==EXPECTED_RGBA and proof.get('historical_rgba_sha256')==HISTORICAL_RGBA,'reference binding')
 require(type(proof.get('max_channel_delta')) is int and 0<=proof['max_channel_delta']<=255 and type(proof.get('pixel_contract_passed')) is bool and proof['pixel_contract_passed']==(proof['max_channel_delta']<=2),'pixel gate contradiction')
 require(type(proof.get('historical_rgba_equal')) is bool,'historical comparison type')
 require(proof.get('failure') is None if proof['pixel_contract_passed'] else proof.get('failure')=='ROUNDTRIP_PNG_PIXEL_GATE','unexpected native failure')
 selection=proof.get('import_selection')
 require(type(selection) is dict and set(selection)=={'panel_identifier','panel_label','full_path_readback','filename','file_cell_count','all_cell_count','total_selected_cell_count','selected','guard_native_reachability_previously_qualified'},'import selection receipt')
 require(selection['panel_identifier']=='open-panel' and type(selection['panel_label']) is str and len(selection['panel_label'].encode())<=1024
  and type(selection['full_path_readback']) is str and len(selection['full_path_readback'].encode())<=512 and Path(selection['full_path_readback']).name=='Celluloid-Owned-Roundtrip.jpg'
  and type(selection['all_cell_count']) is int and 1<=selection['all_cell_count']<=128 and type(selection['total_selected_cell_count']) is int and selection['total_selected_cell_count']==1
  and selection['filename']=='Celluloid-Owned-Roundtrip.jpg' and type(selection['file_cell_count']) is int and selection['file_cell_count']==1 and selection['selected'] is True and selection['guard_native_reachability_previously_qualified'] is False,'owned import selection mismatch')
 require(type(proof.get('asset_label')) is str and 0<len(proof['asset_label'].encode())<=300,'asset label')
 identity=proof.get('photos_identity');require(type(identity) is dict and set(identity)=={'pid','bundle','executable'} and type(identity['pid']) is int and identity['pid']>0 and identity['bundle']=='/System/Applications/Photos.app' and identity['executable']=='/System/Applications/Photos.app/Contents/MacOS/Photos','Photos identity')
 require(type(proof.get('control_catalog')) is list and 0<len(proof['control_catalog'])<=100,'control catalog')
 for row in proof['control_catalog']:
  require(type(row) is list and len(row)==9 and all(type(v) is str and len(v.encode())<=1024 for v in row[:6]) and type(row[6]) is int and row[6]==1 and row[7] is True and row[8] is True,'invalid UI control observation')
 require(type(proof.get('export_option_bindings')) is list and 0<len(proof['export_option_bindings'])<=12,'export bindings')
 require(type(proof.get('binary_states')) is list and 0<len(proof['binary_states'])<=12,'binary states')
 require(proof.get('single_photo_topologies') in (['collection-present'],['collection-absent'],['collection-present','collection-absent'],['collection-absent','collection-present']),'single asset topology')
 require((event['return_code']==0)==proof['pixel_contract_passed'],'native return/proof gate mismatch')
 blocked=[r for r in rows if r.startswith('ROUNDTRIP_BLOCKED') or 'ROUNDTRIP_DENIED_STOP' in r]
 require(blocked==([] if proof['pixel_contract_passed'] else ['ROUNDTRIP_BLOCKED stage=png-exported reason=ROUNDTRIP_PNG_PIXEL_GATE']),'unknown/denied native failure')
 return raw,proof

def admit_import_observation_log(log,event,context,context_bytes,bundle):
 raw,proof=admit_log_prefix(log,event,context,context_bytes,bundle)
 require(event['return_code']==65 and event.get('cleanup_unconfirmed',False) is False
  and event.get('cancelled',False) is False and event.get('timed_out',False) is False
  and proof.get('complete') is False and proof.get('stage')=='writer-committed'
  and proof.get('failure')==IMPORT_FAILURE,'not the exact observed import-selection failure')
 require(proof.get('phases')==['reference','writer-committed'] and proof.get('inputs_checked') is True
  and type(proof.get('writer_start_count')) is int and proof['writer_start_count']==1 and proof.get('writer_claim_succeeded') is True
  and proof.get('writer_reservation_completed') is False and type(proof.get('initial_asset_count')) is int and proof['initial_asset_count']==0,'unbound pre-import writer/library state')
 require(type(proof.get('case_elapsed_seconds')) in (int,float) and 0<proof['case_elapsed_seconds']<=min(900,event['elapsed_seconds']),'import observation case deadline')
 for key in ('actual_extension_writer_observed','actual_photos_callback_observed','qualification_equivalence','pixel_contract_passed'):require(proof.get(key) is False,'import failure cannot become acceptance')
 require(type(proof.get('allowed_max_channel_delta')) is int and proof['allowed_max_channel_delta']==2,'changed strict gate')
 require(all(proof.get(key)==INPUTS['jpeg'][2] for key in ('jpeg_sha256','writer_committed_sha256')),'import writer hash')
 require(proof.get('source_fixture_sha256')==INPUTS['source'][2] and proof.get('expected_rgba_sha256')==EXPECTED_RGBA and proof.get('historical_rgba_sha256')==HISTORICAL_RGBA,'import fixed inputs')
 require(proof.get('images')=={'writer-committed.jpg':{'bytes':INPUTS['jpeg'][1],'sha256':INPUTS['jpeg'][2]}},'unexpected pre-import image set')
 identity=proof.get('photos_identity');require(type(identity) is dict and set(identity)=={'pid','bundle','executable'}
  and type(identity['pid']) is int and identity['pid']>0 and identity['bundle']=='/System/Applications/Photos.app'
  and identity['executable']=='/System/Applications/Photos.app/Contents/MacOS/Photos','unowned import Photos process')
 selection=proof.get('import_selection');require(type(selection) is dict,'missing import selection')
 require(selection.get('panel_identifier')=='open-panel' and type(selection.get('panel_label')) is str and 0<len(selection['panel_label'].encode())<=1024
  and selection.get('filename')=='Celluloid-Owned-Roundtrip.jpg' and type(selection.get('full_path_readback')) is str
  and 0<len(selection['full_path_readback'].encode())<=512 and Path(selection['full_path_readback']).name==selection['filename']
  and selection.get('guard_native_reachability_previously_qualified') is False,'unbound owned import panel')
 for key,limit in [('all_cell_count',128),('file_cell_count',128),('total_selected_cell_count',128)]:require(type(selection.get(key)) is int and 0<=selection[key]<=limit,'unbounded selection count')
 require(selection['all_cell_count']>0 and type(selection.get('selected')) is bool
  and not (selection['file_cell_count']==selection['total_selected_cell_count']==1 and selection['selected']),'selection does not explain failed guard')
 observation=proof.get('import_observation');require(type(observation) is dict and observation.get('schema')=='Celluloid.OwnedImportObservation.1'
  and observation.get('complete') is True and observation.get('scope')=='owned-open-panel-only','missing bounded import observation')
 for key,value in [('source_sha',context['source_sha']),('context_sha256',sha(context_bytes)),('photos_pid',identity['pid']),('initial_asset_count',0),('fixture_sha256',INPUTS['jpeg'][2]),('panel_identifier','open-panel'),('panel_label',selection['panel_label']),('selection_guard_unchanged',True),('no_import_confirmation',True)]:
  require(type(observation.get(key)) is type(value) and observation[key]==value,'import observation binding '+key)
 ax=observation.get('ax');shot=observation.get('screenshot')
 for metadata,cap in [(ax,32768),(shot,65536)]:
  require(type(metadata) is dict and type(metadata.get('bytes')) is int and 0<metadata['bytes']<=cap
   and type(metadata.get('sha256')) is str and re.fullmatch('[0-9a-f]{64}',metadata['sha256']),'import attachment metadata')
 require(type(ax.get('node_count')) is int and 0<ax['node_count']<=256,'import AX node cap')
 require(shot.get('type')=='public.png' and shot.get('resized_panel_preview') is True and type(shot.get('maximum_side')) is int and shot['maximum_side']==640,'wrong panel screenshot kind')
 for key,limit in [('width',640),('height',640),('source_width',4096),('source_height',4096)]:require(type(shot.get(key)) is int and 0<shot[key]<=limit,'panel screenshot geometry')
 scale=min(1,640/max(shot['source_width'],shot['source_height']))
 require((shot['width'],shot['height'])==tuple(max(1,int(shot[key]*scale)) for key in ('source_width','source_height')),'incorrect panel preview scale')
 require(ax['bytes']+shot['bytes']+INPUTS['jpeg'][1]<=131072,'import raw aggregate cap')
 blocked=[row for row in log.splitlines() if row.startswith('ROUNDTRIP_BLOCKED') or 'ROUNDTRIP_DENIED_STOP' in row]
 require(blocked==['ROUNDTRIP_BLOCKED stage=writer-committed reason='+IMPORT_FAILURE],'unknown/denied import failure')
 errors=[row for row in log.splitlines() if re.search(r'(?i)(?:^|[\s:])(?:fatal )?error:',row)]
 wanted=re.escape(context['test_source_path'])+r':[1-9][0-9]*: error: '+re.escape(RAW_CASE+' : '+IMPORT_ERROR)
 require(len(errors)==1 and re.fullmatch(wanted,errors[0]) is not None,'additional/wrong native error')
 require(not re.search(r'(?i)permission denied|operation not permitted|access denied|ROUNDTRIP_PROOF_FAILED|ROUNDTRIP_DENIED_STOP|\b(?:timed[ -]?out|time[ -]?out|cancelled|canceled)\b|cleanup.unconfirmed',log),'denied/cancelled/unknown native failure')
 return raw,proof

def admit_import_observation_summary(summary,event,context):
 require(type(summary) is dict and summary.get('runtimeWarnings')==[] and summary.get('result')=='Failed','import official result')
 counts={'totalTestCount':1,'passedTests':0,'failedTests':1,'skippedTests':0,'expectedFailures':0}
 for key,value in counts.items():require(type(summary.get(key)) is int and summary[key]==value,'import official count '+key)
 for key in ('startTime','finishTime'):require(type(summary.get(key)) in (int,float) and math.isfinite(summary[key]),'import official interval')
 require(event['started_unix']<=summary['startTime']<summary['finishTime']<=event['finished_unix'] and summary['finishTime']-summary['startTime']<=event['elapsed_seconds'],'import summary outside native event')
 configs=summary.get('devicesAndConfigurations');require(type(configs) is list and len(configs)==1,'import official device count')
 config=configs[0];device=config.get('device');require(type(device) is dict,'import official device')
 for key in ('platform','osVersion','osBuildNumber','architecture'):require(device.get(key)==context['runtime'][key],'import early/official runtime mismatch')
 for key,value in counts.items():
  if key!='totalTestCount':require(type(config.get(key)) is int and config[key]==value,'import device counts')
 failures=summary.get('testFailures');require(type(failures) is list and len(failures)==1,'import additional failures')
 failure=failures[0];require(failure.get('targetName')=='CelluloidMacUITests' and failure.get('testIdentifierString')=='MacPhotosRoundtripTests/testOwnedWriterJPEGPhotosRoundtrip()'
  and failure.get('failureText')==IMPORT_ERROR,'not sole exact import failure')
 return device

def admit_import_export_help(text):
 require(type(text) is str and 0<len(text.encode())<=16384,'xcresult attachment help cap')
 require(re.search(r'(?mi)^USAGE: .*export attachments\b',text) is not None,'wrong attachment help command')
 for option in ('--path','--output-path','--test-id'):
  require(re.search(r'(?m)^  '+re.escape(option)+r' <[a-z-]+>(?:\s|$)',text) is not None,'missing attachment help option '+option)
 require('test' in text.lower() and not re.search(r'(?i)permission denied|operation not permitted|access denied|error:',text),'attachment help denied/error')
 return {'schema':'Celluloid.ImportExportCapability.1','help_sha256':sha(text.encode()),'bytes':len(text.encode()),'verified_options':['--path','--output-path','--test-id'],'test_identifier_url':'test://com.apple.xcode/CelluloidPhotosRoundtrip/'+SELECTION}

def import_export_inventory(folder):
 # Post-return admission, not a hard quota during xcresulttool writes.
 require(folder==folder.resolve(strict=True) and not folder.is_symlink(),'import export folder alias')
 before=folder.stat();require(stat.S_ISDIR(before.st_mode) and before.st_uid==os.getuid(),'foreign import export folder')
 count=total=0;names=set()
 with os.scandir(folder) as entries:
  for entry in entries:
   count+=1;require(count<=1025,'import temporary file-count cap')
   state=entry.stat(follow_symlinks=False)
   require(stat.S_ISREG(state.st_mode) and state.st_uid==os.getuid() and state.st_nlink==1,'import temporary file type/owner')
   require(state.st_size>=0,'import temporary file size');total+=state.st_size;require(total<=16*1024*1024,'import temporary aggregate cap')
   names.add(entry.name)
 after=folder.stat();require((before.st_dev,before.st_ino,before.st_mode,before.st_uid)==(after.st_dev,after.st_ino,after.st_mode,after.st_uid),'import export folder changed')
 require('manifest.json' in names,'import temporary manifest missing')
 return {'files':count,'bytes':total,'post_export_file_limit':1025,'post_export_byte_limit':16*1024*1024,'during_export_hard_quota':False},names

def import_observation_attachments(folder,manifest,device,summary,proof,context_bytes):
 require(type(manifest) is list and len(manifest)==1,'import attachment case count')
 record=manifest[0];require(record.get('testIdentifier')=='MacPhotosRoundtripTests/testOwnedWriterJPEGPhotosRoundtrip()'
  and record.get('testIdentifierURL')=='test://com.apple.xcode/CelluloidPhotosRoundtrip/'+SELECTION,'import attachment case identity')
 rows=record.get('attachments');require(type(rows) is list and 0<len(rows)<=1024,'import attachment list cap')
 expected={'writer-committed.jpg':proof['images']['writer-committed.jpg'],'import-ax.json':proof['import_observation']['ax'],'import-panel.png':proof['import_observation']['screenshot']}
 result={};seen=set()
 for row in rows:
  require(type(row) is dict,'import attachment row');label=row.get('suggestedHumanReadableName','')
  if type(label) is not str or not label.startswith('celluloid-roundtrip-'):continue
  match=re.fullmatch(r'celluloid-roundtrip-(writer-committed|import-ax|import-panel)_0_([0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12})\.(jpg|jpeg|json|png)',label)
  require(match is not None,'unexpected named import attachment')
  name=match[1]+('.jpg' if match[3] in ('jpg','jpeg') else '.'+match[3]);require(name in IMPORT_NAMES and name not in result,'duplicate/wrong import attachment')
  exported=row.get('exportedFileName');require(type(exported) is str and exported not in seen and Path(exported).name==exported and exported not in ('','.','..'),'unsafe import attachment path');seen.add(exported)
  require(row.get('deviceId')==device.get('deviceId') and row.get('deviceName')==device.get('deviceName') and row.get('configurationName')=='Test Scheme Action','import attachment runtime')
  require(type(row.get('timestamp')) in (int,float) and summary['startTime']<=row['timestamp']<=summary['finishTime'],'import attachment interval')
  raw=owned_read(folder/exported,32768 if name=='import-ax.json' else 65536)
  require(len(raw)==expected[name]['bytes'] and sha(raw)==expected[name]['sha256'] and sum(map(len,result.values()))+len(raw)<=131072,'import actual attachment hash/cap');result[name]=raw
 require(set(result)==set(IMPORT_NAMES),'missing import observation attachment')
 require(result['writer-committed.jpg']==owned_read(ROOT/INPUTS['jpeg'][0],65536),'import W differs from J')
 ax=load_json(result['import-ax.json']);observation=proof['import_observation'];selection=proof['import_selection']
 require(type(ax) is dict and ax.get('schema')=='Celluloid.OwnedImportAX.1','import AX schema')
 for key,value in [('source_sha',proof['source_sha']),('context_sha256',sha(context_bytes)),('photos_pid',proof['photos_identity']['pid']),('initial_asset_count',0),('fixture_path',selection['full_path_readback']),('fixture_sha256',INPUTS['jpeg'][2]),('panel_identifier','open-panel'),('panel_label',selection['panel_label']),('selection_guard_unchanged',True),('no_import_confirmation',True)]:
  require(type(ax.get(key)) is type(value) and ax[key]==value,'import AX binding '+key)
 require(ax.get('columns')==['index','parent','role','identifier','label','title','value','selected','frame','truncated_attributes'],'import AX columns')
 nodes=ax.get('nodes');require(type(nodes) is list and len(nodes)==observation['ax']['node_count'],'import AX node count')
 for index,node in enumerate(nodes):
  require(type(node) is list and len(node)==10 and type(node[0]) is int and node[0]==index and type(node[1]) is int,'import AX node shape')
  require(node[1]==-1 if index==0 else 0<=node[1]<index,'import AX tree ownership')
  require(all(type(value) is str and len(value.encode())<=640 for value in node[2:7]) and type(node[7]) is bool,'import AX attribute bounds')
  require(type(node[8]) is list and len(node[8])==4 and all(type(value) in (int,float) and math.isfinite(value) for value in node[8]),'import AX frame')
  require(type(node[9]) is list and len(node[9])==4 and all(type(value) is bool for value in node[9]),'import AX truncation marks')
 require(nodes[0][2:5]==['sheet','open-panel',selection['panel_label']] and nodes[0][9][:2]==[False,False],'import AX root panel')
 shot=observation['screenshot'];decode(result['import-panel.png'],shot.get('srgb_icc_reference'),dimensions=(shot['width'],shot['height']))
 return result,ax

def admit_native(log,event,summary,context,context_bytes,bundle):
 raw,proof=admit_log(log,event,context,context_bytes,bundle)
 # Official result is independently bound to this same one case and exact host.
 require(type(summary) is dict and summary.get('runtimeWarnings')==[],'native runtime warnings')
 passed=proof['pixel_contract_passed'];counts={'totalTestCount':1,'passedTests':int(passed),'failedTests':int(not passed),'skippedTests':0,'expectedFailures':0}
 for key,wanted in counts.items():require(type(summary.get(key)) is int and summary[key]==wanted,'official result count '+key)
 require(summary.get('result')==('Passed' if passed else 'Failed') and (event['return_code']==0)==passed,'official result/gate mismatch')
 for key in ('startTime','finishTime'):require(type(summary.get(key)) in (int,float) and math.isfinite(summary[key]),'official test interval')
 require(event['started_unix']<=summary['startTime']<summary['finishTime']<=event['finished_unix'] and summary['finishTime']-summary['startTime']<=event['elapsed_seconds'],'official summary outside original native event')
 configs=summary.get('devicesAndConfigurations');require(type(configs) is list and len(configs)==1,'official device count')
 config=configs[0];device=config.get('device');require(type(device) is dict,'missing official device')
 for key in ('platform','osVersion','osBuildNumber','architecture'):require(device.get(key)==context['runtime'][key],'early/official runtime mismatch')
 for key in counts:
  if key!='totalTestCount':require(type(config.get(key)) is int and config[key]==counts[key],'device result count')
 failures=summary.get('testFailures',[])
 if passed:require(failures==[],'unexpected failure')
 else:
  require(type(failures) is list and len(failures)==1,'additional native failures')
  failure=failures[0];require(failure.get('targetName')=='CelluloidMacUITests' and failure.get('testIdentifierString')=='MacPhotosRoundtripTests/testOwnedWriterJPEGPhotosRoundtrip()' and 'ROUNDTRIP_PNG_PIXEL_GATE' in failure.get('failureText',''),'failure was not sole strict pixel gate')
 return raw,proof,device

def attachments(folder,manifest,device,summary):
 require(type(manifest) is list and len(manifest)==1,'attachment testcase count')
 record=manifest[0];require(record.get('testIdentifier')=='MacPhotosRoundtripTests/testOwnedWriterJPEGPhotosRoundtrip()' and record.get('testIdentifierURL')=='test://com.apple.xcode/CelluloidPhotosRoundtrip/'+SELECTION,'attachment testcase identity')
 rows=record.get('attachments');require(type(rows) is list and 0<len(rows)<=1024,'attachment item cap')
 result={};seen=set()
 for row in rows:
  require(type(row) is dict,'attachment row')
  label=row.get('suggestedHumanReadableName','')
  if type(label) is not str or not label.startswith('celluloid-roundtrip-'):continue
  match=re.fullmatch(r'celluloid-roundtrip-(writer-committed|photos-original|photos-roundtrip)_0_([0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12})\.(jpg|jpeg|png)',label)
  require(match is not None,'unknown named roundtrip attachment')
  name=match[1]+('.png' if match[3]=='png' else '.jpg');require(name in NAMES and name not in result,'duplicate/wrong attachment name')
  exported=row.get('exportedFileName');require(type(exported) is str and exported not in seen and Path(exported).name==exported and exported not in ('','.','..'),'unsafe/duplicate attachment path');seen.add(exported)
  require(row.get('deviceId')==device.get('deviceId') and row.get('deviceName')==device.get('deviceName') and row.get('configurationName')=='Test Scheme Action','attachment runtime identity')
  require(type(row.get('timestamp')) in (int,float) and summary['startTime']<=row['timestamp']<=summary['finishTime'],'attachment interval')
  raw=owned_read(folder/exported,65536);require(sum(map(len,result.values()))+len(raw)<=131072,'observed raw aggregate cap');result[name]=raw
 require(set(result)==set(NAMES),'missing required raw boundary attachment')
 return result

def replay(raws,proof,root=ROOT):
 require(set(raws)==set(NAMES) and sum(map(len,raws.values()))<=131072,'raw evidence set/cap')
 images=proof.get('images');require(type(images) is dict and set(images)==set(NAMES),'image metadata set')
 for name,raw in raws.items():
  metadata=images[name];require(type(metadata) is dict and type(metadata.get('bytes')) is int and 0<len(raw)==metadata['bytes']<=65536 and sha(raw)==metadata.get('sha256'),'actual attachment hash mismatch')
 jpeg=owned_read(root/INPUTS['jpeg'][0],65536)
 require(raws['writer-committed.jpg']==raws['photos-original.jpg']==jpeg,'writer/original exact byte failure')
 expected=decode(owned_read(root/INPUTS['expected'][0],65536),proof.get('srgb_icc_reference'))
 historical=decode(owned_read(root/INPUTS['historical'][0],65536),proof.get('srgb_icc_reference'))
 actual=decode(raws['photos-roundtrip.png'],proof.get('srgb_icc_reference'))
 require(expected['rgba_sha256']==EXPECTED_RGBA and historical['rgba_sha256']==HISTORICAL_RGBA,'fixed image decode drift')
 require(actual['rgba_sha256']==proof.get('png_rgba_sha256')==images['photos-roundtrip.png'].get('rgba_sha256'),'native/offline PNG disagreement')
 result=compare(actual,expected);delta=result['maximum_channel_difference'];equal=actual['rgba']==historical['rgba']
 require(delta==proof['max_channel_delta'] and (delta<=2)==proof['pixel_contract_passed'] and equal==proof['historical_rgba_equal'],'native/offline comparison mismatch')
 histogram={};channel_hist=[{} for _ in range(4)];above=[]
 a,b=actual['rgba'],expected['rgba'];square=0
 for p in range(1200*800):
  changes=[a[4*p+k]-b[4*p+k] for k in range(4)];maximum=max(map(abs,changes));histogram[maximum]=histogram.get(maximum,0)+1
  for k,d in enumerate(changes):channel_hist[k][abs(d)]=channel_hist[k].get(abs(d),0)+1
  square+=sum(d*d for d in changes[:3])
  if maximum>2 and len(above)<32:above.append({'x':p%1200,'y':p//1200,'signed_delta_rgba':changes})
 return dict(result,max_channel_histogram=histogram,channel_histograms_rgba=channel_hist,first_above_two=above,rgb_rmse=math.sqrt(square/(1200*800*3)),historical_rgba_equal=equal,pixel_contract_passed=delta<=2,actual_extension_writer_observed=False,actual_photos_callback_observed=False,qualification_equivalence=False)

def build_identity(temp):
 products=temp/'celluloid-roundtrip/Build/Products/Debug'
 paths={'app':products/'CelluloidMac.app/Contents/MacOS/CelluloidMac',
  'extension':products/'CelluloidMac.app/Contents/PlugIns/CelluloidMacPhotosExtension.appex/Contents/MacOS/CelluloidMacPhotosExtension',
  'extension_debug_dylib':products/'CelluloidMac.app/Contents/PlugIns/CelluloidMacPhotosExtension.appex/Contents/MacOS/CelluloidMacPhotosExtension.debug.dylib',
  'test':products/'CelluloidMacUITests-Runner.app/Contents/PlugIns/CelluloidMacUITests.xctest/Contents/MacOS/CelluloidMacUITests'}
 result={}
 for name,path in paths.items():
  raw=owned_read(path,64*1024*1024);result[name]={'path':str(path),'bytes':len(raw),'sha256':sha(raw)}
 return result

def make_context(before,runtime,identity,root=ROOT):
 result={'schema':'Celluloid.OwnedPhotosRoundtripContext.1','source_sha':before['source_sha'],'tree':before['tree'],'parent':BASE,
  'run_id':before['run_id'],'run_attempt':1,'repository_root':str(root),'runtime':runtime,'case_seconds':900,'build_identity':identity}
 for name,rel in [('test_source',TEST),('writer_source',WRITER),('script',SCRIPT)]:
  result[name+'_path']=str(root/rel);result[name+'_sha256']=sha(owned_read(root/rel,2*1024*1024))
 result['inputs']={name:{'path':str(root/rel),'bytes':n,'sha256':digest} for name,(rel,n,digest) in INPUTS.items()}
 return result

def compiler_diagnostics(text,source_root):
 # Pure projection of the complete already-returned build stream. Never dispatch.
 require(type(text) is str and type(source_root) is str,'compiler projection input')
 raw=text.encode();lines=text.splitlines();counts={'error':0,'warning':0};indices={'error':[],'warning':[]}
 pattern=re.compile(r'^(?:(?P<path>/[^\r\n]+?):(?P<line>[0-9]+)(?::(?P<column>[0-9]+))?:\s*)?(?P<severity>fatal error|error|warning):\s*(?P<message>.*)$',re.I)
 for index,line in enumerate(lines):
  found=pattern.fullmatch(line.strip())
  if found is not None:match=found.groupdict()
  else:
   found=re.match(r'^(?:(?:---[ \t]+)?xcodebuild:[ \t]+|[0-9]{4}-[0-9]{2}-[0-9]{2}[ T][0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,9})?[ \t]+[A-Za-z0-9_.-]{1,80}\[[0-9]+:[0-9A-Fa-f]+\][ \t]+)(?P<severity>fatal error|error|warning):[ \t]*',line.strip(),re.I)
   if found is None:continue
   match={'path':None,'line':None,'column':None,'severity':found['severity']}
  kind='error' if match['severity'].casefold() in ('error','fatal error') else 'warning'
  counts[kind]+=1
  # At most this many full records could fit in the 32KB projection anyway.
  if len(indices[kind])<64:indices[kind].append((index,match))
 def clipped(value,limit):
  b=value.encode();return {'text':b[:limit].decode('utf8','ignore'),'bytes':len(b),'sha256':sha(b),'truncated':len(b)>limit}
 result={'schema':'Celluloid.CompilerDiagnostics.1','source_root':source_root,'source_sha':None,
  'full_output_bytes':len(raw),'full_output_sha256':sha(raw),'full_output_lines':len(lines),'total_diagnostics':counts,
  'retained_diagnostics':{'error':0,'warning':0},'omitted_diagnostics':dict(counts),'context_radius':2,
  'maximum_projection_bytes':32768,'diagnostic_line_limit_bytes':2048,'context_line_limit_bytes':512,
  'source_path_limit_bytes':1024,'prioritize_errors':True,'entries':[]}
 for kind in ('error','warning'):
  for index,match in indices[kind]:
   path=match['path'];entry={'output_line':index+1,'severity':kind,'compiler_severity':match['severity'],
    'source_path':None if path is None else clipped(path,1024),'source_line':None if match['line'] is None else int(match['line']),
    'source_column':None if match['column'] is None else int(match['column']),
    'source_scope':'no-file' if path is None else 'repository' if path.startswith(source_root.rstrip('/')+'/') else 'outside-repository',
    'diagnostic':clipped(lines[index],2048),'context':[dict(output_line=i+1,**clipped(lines[i],512)) for i in range(max(0,index-2),min(len(lines),index+3)) if i!=index]}
   result['entries'].append(entry);result['retained_diagnostics'][kind]+=1;result['omitted_diagnostics'][kind]-=1
   if len(encoded(result))>32000:
    result['entries'].pop();result['retained_diagnostics'][kind]-=1;result['omitted_diagnostics'][kind]+=1
 result['truncated']=any(result['omitted_diagnostics'].values()) or any(e['diagnostic']['truncated'] or (e['source_path'] or {}).get('truncated',False) or any(c['truncated'] for c in e['context']) for e in result['entries'])
 require(len(encoded(result))<=32768,'compiler projection cap')
 return result

def main():
 # Config is checked before subprocesses, environment use, directory creation or any native action.
 config=load_json(owned_read(ROOT/CONFIG,4096))
 require(config.get('enabled') is True,'CLOSED diagnostic; root must review separate activation')
 require(Path.cwd().resolve()==ROOT,'driver must execute from exact source root')
 before=admit_source()
 supplied=Path(os.environ['RUNNER_TEMP']);require(supplied.is_dir() and not supplied.is_symlink(),'invalid runner temp')
 temp=supplied.resolve(strict=True);output=temp/'celluloid-photos-roundtrip-evidence'
 require(not output.exists() and not output.is_symlink(),'stale evidence');output.mkdir()
 files={};deadline=work_deadline=tail_deadline=None
 report={'schema':'Celluloid.OwnedPhotosRoundtripRun.1','source_sha':before['source_sha'],'run_id':before['run_id'],'run_attempt':1,
  'stage':'source-admitted','compile_only':True,'diagnostic_complete':False,'pixel_contract_passed':False,'actual_extension_writer_observed':False,
  'actual_photos_callback_observed':False,'qualification_equivalence':False,'release_qualified':False,'events':[]}
 def retain(name,raw,cap):
  require(name not in files and Path(name).name==name and 0<len(raw)<=cap,'evidence name/cap')
  require(sum(r['bytes'] for r in files.values())+len(raw)<=CAP-RESERVE,'original1MB evidence cap')
  path=output/name
  with path.open('xb') as stream:stream.write(raw)
  files[name]={'bytes':len(raw),'sha256':sha(raw)}
 def check_time(label,reserve=0):
  require(work_deadline is not None and time.monotonic()+reserve<min(work_deadline,tail_deadline or work_deadline),'original work/tail deadline: '+label)
 def invoke(args,seconds,label,check=True,retain_tail=False):
  check_time(label,seconds+15)
  event={'stage':label,'command':list(map(str,args)),'limit_seconds':seconds,'started_unix':time.time(),'started_monotonic':time.monotonic()};report['events'].append(event)
  wrapped=['/bin/sh','-c','exec "$@" 2>&1','celluloid-owned-roundtrip',*map(str,args)]
  value=run(wrapped,timeout=seconds,check=False,echo=False,log_name='roundtrip-'+label+'.log')
  event.update(return_code=value.returncode,finished_unix=time.time(),elapsed_seconds=time.monotonic()-event['started_monotonic'],returned_without_timeout=True)
  raw=(value.stdout+value.stderr).encode()
  if retain_tail:retain(label+'.tail.txt',raw[-24000:] or b'(empty)',24000);event['full_log_sha256']=sha(raw);event['full_log_bytes']=len(raw)
  if label=='ui-build':
   projection=compiler_diagnostics(value.stdout+value.stderr,str(ROOT));projection['source_sha']=before['source_sha']
   retain('ui-build.diagnostics.json',encoded(projection),32768);event['compiler_diagnostic_counts']=projection['total_diagnostics']
   checked={'source_sha':before['source_sha'],'clean_git_rechecked':False,'source_bytes_rechecked':False}
   try:
    current=source_snapshot()[1];checked['observed_source_binding']=current
    checked['source_bytes_rechecked']=current=={k:before[k] for k in ('source_fingerprint','source_manifest_sha256','files')}
   except (OSError,ValueError,KeyError,TypeError) as error:
    checked['error']=type(error).__name__+': '+str(error)[:1000]
    retain('source-after.json',encoded(checked),4096);raise
   retain('source-after.json',encoded(checked),4096)
   require(checked['source_bytes_rechecked'],'compile-only build changed source')
  require(not check or value.returncode==0,'required command failed: '+label)
  return value,event
 try:
  retain('source-before.json',encoded(before),4096)
  clock_raw=owned_read(temp/'mac-job-clock.json',4096);clock=load_json(clock_raw)
  require(clock.get('source_sha')==before['source_sha'] and type(clock.get('execution_budget_seconds')) is int and clock['execution_budget_seconds']==2460,'original job clock')
  for key in ('started_monotonic','started_unix'):require(type(clock.get(key)) in (int,float) and math.isfinite(clock[key]) and clock[key]>0,'clock number')
  require(clock['started_monotonic']<=time.monotonic(),'future clock')
  deadline=clock['started_monotonic']+2460;work_deadline=deadline-300;retain('mac-job-clock.json',clock_raw,4096)
  report['budgets']={'job_minutes':45,'original_clock_seconds':2460,'upload_reserve_seconds':300,'case_seconds':900,'test_seconds':960,'native_process_seconds':1020,'native_cleanup_seconds':15,'tail_seconds':360,'before_prepare_seconds':1980,'before_host_seconds':1740,'artifact_cap_bytes':CAP,'raw_cap_bytes':131072}
  for name in ('celluloid-roundtrip','MacPhotosRoundtrip.xcresult','roundtrip-attachments','roundtrip-context.json','roundtrip-debug-entitlements.plist'):
   require(not (temp/name).exists() and not (temp/name).is_symlink(),'stale owned work path')
  require(not (temp/'sandbox.log').exists(),'unadmitted pre-seeded library')
  report['stage']='runtime-preflight'
  version,_=invoke(['/usr/bin/sw_vers','-productVersion'],10,'runtime-version');build,_=invoke(['/usr/bin/sw_vers','-buildVersion'],10,'runtime-build')
  observed={'platform':'macOS','osVersion':version.stdout.strip(),'osBuildNumber':build.stdout.strip(),'architecture':os.uname().machine}
  report['runtime_observation']={key:value[:128] for key,value in observed.items()}
  runtime=runtime_record(observed['osVersion'],observed['osBuildNumber'],observed['architecture'])
  retain('runtime-before.json',encoded(runtime),2048)
  report['stage']='toolchain';value,_=invoke(['xcodebuild','-version'],20,'toolchain');require('Xcode 27.0' in value.stdout.splitlines(),'wrong Xcode');report['toolchain']=value.stdout[:1024]
  report['stage']='import-export-capability'
  help_value,_=invoke(['xcrun','xcresulttool','help','export','attachments'],10,'import-export-help')
  capability=admit_import_export_help(help_value.stdout);retain('import-export-help.txt',help_value.stdout.encode(),16384);retain('import-export-capability.json',encoded(capability),2048)
  report['stage']='portable';invoke([sys.executable,'-m','unittest','discover','-s','Scripts','-p','test_mac_photos_roundtrip.py','-v'],240,'portable',retain_tail=True)
  require(source_snapshot()[1]=={k:before[k] for k in ('source_fingerprint','source_manifest_sha256','files')},'portable changed source')
  report['stage']='icons';invoke(['swift','-swift-version','5','Scripts/materialize_native_icons.swift'],30,'icons');invoke([sys.executable,'Scripts/verify_native_icon_inputs.py'],10,'icon-check')
  report['stage']='ui-build';invoke(command(temp,'build-for-testing'),480,'ui-build',retain_tail=True)
  # This source-bound compile-only lane ends here even if compilation succeeds.
  report.update(stage='compile-only-ui-build-succeeded',compile_only=True,ui_build_succeeded=True)
  return 1
  app=temp/'celluloid-roundtrip/Build/Products/Debug/CelluloidMac.app'
  def observe_app_rights(action,label):
   value,event=invoke(['/usr/bin/codesign','-d','--entitlements',':-',str(app)],20,label)
   raw=value.stdout.encode();event.update(output_bytes=len(raw),output_sha256=sha(raw))
   observation=app_entitlement_observation(value.stdout,action)
   observation.update(source_sha=before['source_sha'],command_stage=label)
   retain(label+'.json',encoded(observation),16384)
   return observation['entitlements']
  report['stage']='ui-build-entitlements';observe_app_rights('build-for-testing','app-entitlements-ui-build')
  # Reuse the observed boundary lane's ordinary app build after the UI-test build.
  # Both commands consume the same original clock; neither executes a test or Photos.
  report['stage']='app-build';invoke(command(temp,'build'),300,'app-build',retain_tail=True)
  require(deadline-time.monotonic()>=1980,'original before-prepare reserve exhausted')
  report['stage']='prepare'
  # The same fresh-runner ad-hoc Debug entitlements as the current boundary lane; no credential or persistent access.
  rights=observe_app_rights('build','app-entitlements-app-build')
  require(rights=={'com.apple.security.app-sandbox':True,'com.apple.security.files.user-selected.read-write':True},'unexpected app entitlements')
  rights['com.apple.security.get-task-allow']=True;path=temp/'roundtrip-debug-entitlements.plist';path.write_bytes(plistlib.dumps(rights))
  invoke(['/usr/bin/codesign','--force','--sign','-','--entitlements',str(path),'--timestamp=none',str(app)],20,'debug-sign-app')
  invoke(['/usr/bin/codesign','--verify','--deep','--strict',str(app)],20,'verify-app-signature')
  identity=build_identity(temp);retain('build-before.json',encoded(identity),8192)
  context=make_context(before,runtime,identity);context_bytes=encoded(context);context_path=temp/'roundtrip-context.json';context_path.write_bytes(context_bytes);retain('context.json',context_bytes,32000)
  require(source_snapshot()[1]=={k:before[k] for k in ('source_fingerprint','source_manifest_sha256','files')},'pretest source changed')
  require(deadline-time.monotonic()>=1740,'original before-host reserve exhausted')
  os.environ['TEST_RUNNER_CELLULOID_PHOTOS_ROUNDTRIP_PREREQUISITE']='1';os.environ['TEST_RUNNER_CELLULOID_PHOTOS_ROUNDTRIP_CONTEXT']=str(context_path)
  report['stage']='one-roundtrip-case';native,event=invoke(command(temp,'test-without-building'),1020,'single-case',check=False)
  log=native.stdout+native.stderr;retain('native.log',log.encode(),256000)
  # Pure full native event/case/terminal/envelope/receipt admission before any new command.
  bundle=str(temp/'MacPhotosRoundtrip.xcresult')
  try:admit_log(log,event,context,context_bytes,bundle)
  except ValueError as original:
   if str(original)!='incomplete diagnostic; no post-failure attachment operation':raise
   # Only the exact known pre-import failure with finished xcodebuild/case may
   # export its already-recorded owned-panel evidence. No Photos action follows.
   # This is not evidence that every Photos process has exited.
   raw,proof=admit_import_observation_log(log,event,context,context_bytes,bundle)
   tail_deadline=min(work_deadline,time.monotonic()+360,event['started_monotonic']+1020+360)
   report['stage']='import-observation-summary'
   summary_result,_=invoke(['xcrun','xcresulttool','get','test-results','summary','--path',bundle],30,'import-summary')
   summary=load_json(summary_result.stdout);retain('import-summary.json',summary_result.stdout.encode(),32000)
   device=admit_import_observation_summary(summary,event,context)
   retain('import-failure-receipt.json',raw,32000)
   require(build_identity(temp)==identity,'import failure build bytes changed')
   require(sum(row['bytes'] for row in files.values())+131072+128000+8192+RESERVE<=CAP,'insufficient original import-evidence cap')
   report['stage']='import-observation-attachments';folder=temp/'roundtrip-attachments'
   invoke(['xcrun','xcresulttool','export','attachments','--path',bundle,'--test-id',capability['test_identifier_url'],'--output-path',str(folder)],60,'import-attachments')
   inventory,names=import_export_inventory(folder);report['temporary_export_admission']=inventory
   manifest_raw=owned_read(folder/'manifest.json',128000);manifest=load_json(manifest_raw)
   raws,ax=import_observation_attachments(folder,manifest,device,summary,proof,context_bytes)
   require(names=={'manifest.json'}|{row['exportedFileName'] for row in manifest[0]['attachments']},'unmanifested temporary attachment')
   filtered=[dict(manifest[0],attachments=[row for row in manifest[0]['attachments'] if row.get('suggestedHumanReadableName','').startswith('celluloid-roundtrip-')])]
   retain('import-attachment-manifest.json',encoded(filtered),128000)
   for name,data in raws.items():retain(name,data,32768 if name=='import-ax.json' else 65536)
   require(source_snapshot()[1]=={key:before[key] for key in ('source_fingerprint','source_manifest_sha256','files')},'import observation source changed')
   retain('source-after.json',encoded(dict(before,source_bytes_rechecked=True,clean_git_rechecked=False)),4096)
   report.update(stage='completed-import-selection-observation-failed',import_observation_complete=True,
    observed_failure=IMPORT_FAILURE,settled_scope='original owned xcodebuild returned/reaped and exact case ended; not all Photos processes',
    import_ax_nodes=len(ax['nodes']),import_action_performed=False,writer_complete_delivery_performed=False,
    U_P_export_or_pixel_comparison_performed=False,diagnostic_complete=False,pixel_contract_passed=False)
   return 1
  tail_deadline=min(work_deadline,time.monotonic()+360,event['started_monotonic']+1020+360)
  report['stage']='official-summary';bundle=str(temp/'MacPhotosRoundtrip.xcresult');summary_result,_=invoke(['xcrun','xcresulttool','get','test-results','summary','--path',bundle],30,'summary')
  summary=load_json(summary_result.stdout);retain('summary.json',summary_result.stdout.encode(),32000)
  raw,proof,device=admit_native(log,event,summary,context,context_bytes,bundle);retain('receipt.json',raw,32000)
  report['stage']='post-build-identity';require(build_identity(temp)==identity,'same-job build bytes changed')
  invoke(['/usr/bin/codesign','--verify','--deep','--strict',str(app)],20,'verify-post-signature');retain('build-after.json',encoded(identity),8192)
  require(sum(r['bytes'] for r in files.values())+131072+128000+8192+sum(row[1] for row in INPUTS.values())+4096+RESERVE<=CAP,'insufficient original cap before attachments')
  report['stage']='attachments';folder=temp/'roundtrip-attachments';invoke(['xcrun','xcresulttool','export','attachments','--path',bundle,'--output-path',str(folder)],60,'attachments')
  manifest_raw=owned_read(folder/'manifest.json',128000);retain('attachment-manifest.json',manifest_raw,128000)
  raws=attachments(folder,load_json(manifest_raw),device,summary)
  for name,data in raws.items():retain(name,data,65536)
  report['stage']='offline-replay';check_time('pixel replay',30);result=replay(raws,proof);check_time('pixel replay completion')
  retain('comparison.json',encoded(result),8192)
  for name,(rel,_,_) in INPUTS.items():retain('fixed-'+name+Path(rel).suffix,owned_read(ROOT/rel,65536),65536)
  require(build_identity(temp)==identity,'final build bytes changed')
  require(source_snapshot()[1]=={k:before[k] for k in ('source_fingerprint','source_manifest_sha256','files')},'final source changed')
  head,_=invoke(['git','rev-parse','HEAD'],10,'final-head');status,_=invoke(['git','status','--porcelain','--untracked-files=all'],10,'final-status')
  require(head.stdout.strip()==before['source_sha'] and not status.stdout.strip(),'final Git identity changed')
  retain('source-after.json',encoded(dict(before,clean_git_rechecked=True)),4096)
  report.update(stage='completed' if result['pixel_contract_passed'] else 'completed-strict-pixel-gate-failed',diagnostic_complete=True,pixel_contract_passed=result['pixel_contract_passed'],comparison=result)
 except (OSError,ValueError,RuntimeError,TimeoutError,KeyError,TypeError,subprocess.SubprocessError) as error:
  report['error']=type(error).__name__+': '+str(error)[:1800]
  if isinstance(error,TimeoutError) or getattr(error,'cleanup_unconfirmed',False):report['cleanup_unconfirmed']=True
 finally:
  # Pure owned file finalization only. No cleanup command, retry, discovery or permission expansion.
  raw=encoded(report);require(len(raw)<=24000,'final run receipt cap')
  (output/'run.json').write_bytes(raw);files['run.json']={'bytes':len(raw),'sha256':sha(raw)}
  manifest=encoded({'schema':'Celluloid.OwnedPhotosRoundtripArtifact.1','source_sha':before['source_sha'],'run_id':before['run_id'],'run_attempt':1,'files':files})
  require(sum(r['bytes'] for r in files.values())+len(manifest)<=CAP,'final artifact cap');(output/'manifest.json').write_bytes(manifest)
  print(json.dumps(report,sort_keys=True),flush=True)
 return 0 if report['diagnostic_complete'] and report['pixel_contract_passed'] else 1

if __name__=='__main__':sys.exit(main())
