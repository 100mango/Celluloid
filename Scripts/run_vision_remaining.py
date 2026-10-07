#!/usr/bin/env python3
"""Fixed single editing case with fixture-only setup and owned-container evidence.

The prior db4 cohort's archive/package proof remains historical evidence. This
cohort does not repeat Release archive work and cannot relabel that old run green.
"""
import argparse
import hashlib
import math
import json
import os
import plistlib
import struct
import zlib
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid
from mac_archive_capture import capture, CaptureStopped
from vision_remaining_retention import ARCHIVE_RAW_CAP, retain_archive_output

HOSTED = 'CelluloidVisionTests/NativeVisionTests/testPrepareVisionRemainingDocumentFixture'
EDIT = 'CelluloidVisionUITests/NativeVisionUITests/testSeededDocumentSequentialTextUndoRedoAndBrowserReopen'
PRIVACY = 'CelluloidVisionUITests/NativeVisionUITests/testSimplifiedChineseDocumentPrivacyAndLargeText'
SELECTORS = (EDIT,)
BASE = 'abe9fc5560b230edc93b0312ef78b26b3d3dab55'
BASE_TREE = '01b378b2c0c27191774ddb7619fb4d4091bca407'
BRANCH = 'refs/heads/codex/vision-edit-final'
WORKFLOW = '.github/workflows/vision-remaining.yml'
CLOCK = 'vision-remaining-clock.json'
WORK_END, CLEANUP_END, PACK_END, FINISH_END = 3000, 3150, 3200, 3360
EVIDENCE_CAP = 8_000_000
REPORT_CAP = 1_000_000
FAILURE_TAIL_CAP = 32_768
# Fixed producer-bounded upload set. The worst-case sum is below8MB even if
# --pack never completes. No directory glob or xcresult/archive is uploaded.
EVIDENCE_FILES = {**{name+'.log':524_298 for name in ('build','bootstatus','install','seed-before-ui','ui','seed-after-ui','shutdown','delete','create')},
                  'report.json':REPORT_CAP,'vision-remaining-device-uncertain.json':1_000_000,
                  'native-icon-provenance-runtime.json':1_000_000,'manifest.json':32_768}
MODIFIED = ('Documentation/vision-remaining.md','Scripts/run_vision_remaining.py','Scripts/test_vision_remaining.py','Platforms/VisionUITests/NativeVisionUITests.swift')
ADDED = ()
HISTORICAL_PACKAGE = {'source_sha':'db4d719abdf11504e99e211ffc27d7555883acb3','run_id':37608605492,'artifact_id':11477245993,
    'artifact_sha256':'126ecef09c9fac1f8d0972071cceb82513c0f2fcba7a113a4da1fbd6fc8aa46d',
    'scope':'Historical component reference only; no archive/package execution in this runtime-only cohort'}

HISTORICAL_RUNTIME = {'source_sha':'2cf9160fa043f7ef0f89e42d022240a8b9f77322','run_id':37612385100,'artifact_id':11479451487,
    'artifact_sha256':'bdd05d117f26f5beedf27f61050fdffd3f91db2d872829d6e900803dabe258c3',
    'scope':'Previously passed field/Undo hosted component and Chinese normal/largest policy UI; neither reruns'}
FIXTURE_NAME = 'VisionRemaining.celluloid'
# Exact source UUID and recipe bytes/hash printed by the actual native writer in
# run37637767590/artifact11490979202. That run failed on xcodebuild finalization.
NATIVE_SEED_ID = 'C669EEEC-B101-4A5B-8579-42479B800FE7'
NATIVE_RECIPE_SHA = '3fc3d7275c3e1e802dccb8daa63e688944b70c00a4d636c93d39f32f9b755b6e'
HISTORICAL_FIXTURE = {'source_sha':'997dd5a53781423ed3ff91a6e559874fd8814f7b','run_id':37637767590,'artifact_id':11490979202,
    'artifact_sha256':'dacfe58716acceb6d1cce8c45c4581a8d0de69c8b50f905906e4353568736970',
    'scope':'Native fixture case passed0.166s; xcodebuild timed out, invocation failed and UI never started'}


def synthetic_fixture_bytes():
    # Python-authored INPUT only, not an app result or a rendered output image.
    recipe={'format':'Celluloid.Document','version':1,'filter':'Original','overlays':[],
            'canvasWidth':120,'canvasHeight':80,'sources':[{'id':NATIVE_SEED_ID,'displayName':'Synthetic.png',
            'pixelWidth':120,'pixelHeight':80,'crop':{'centerX':0.5,'centerY':0.5,'zoom':1}}]}
    encoded=json.dumps(recipe,sort_keys=True,separators=(',',':')).encode()
    if len(encoded)!=281 or hashlib.sha256(encoded).hexdigest()!=NATIVE_RECIPE_SHA: raise ValueError('Recipe differs from actual native fixture')
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',120,80,8,6,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\x1a\x80\xcc\xff'*120)*80))+chunk(b'IEND',b'')
    return {'recipe.json':encoded,NATIVE_SEED_ID+'.image':png}


def write_synthetic_fixture(container):
    container=Path(container)
    if container.is_symlink() or not container.is_dir(): raise ValueError('Unsafe app data container')
    documents=container/'Documents'
    if documents.is_symlink(): raise ValueError('Unsafe Documents link')
    documents.mkdir(exist_ok=True)
    fixture=documents/FIXTURE_NAME
    # Only a fresh, fixed-name test package is created. Never overwrite an item.
    if fixture.exists() or fixture.is_symlink(): raise ValueError('Fixture already exists')
    fixture.mkdir()
    for name,data in synthetic_fixture_bytes().items():
        with (fixture/name).open('xb') as stream:stream.write(data)
    files=[{'name':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(fixture.iterdir())]
    return validate_fixture_metadata({'schema':'Celluloid.VisionFixture.1','bundle_identifier':'Mango.Celluloid',
        'origin':'Python-generated synthetic INPUT; not a native test result or rendered output',
        'data_home':str(container),'documents_path':str(documents),'package_path':str(fixture),'package_name':FIXTURE_NAME,
        'pixel_width':120,'pixel_height':80,'initial_overlays':0,'files':files})


def built_vision_app(temp):
    app=Path(temp)/'celluloid-vision/Build/Products/Debug-xrsimulator/CelluloidVision.app'
    if app.is_symlink() or not app.is_dir(): raise ValueError('Built Vision app missing or unsafe')
    info=plistlib.loads((app/'Info.plist').read_bytes())
    if (info.get('CFBundleIdentifier'),info.get('CFBundleExecutable'),info.get('DTPlatformName'))!=('Mango.Celluloid','CelluloidVision','xrsimulator'): raise ValueError('Wrong built Vision app')
    binary=app/'CelluloidVision'
    if binary.is_symlink() or not binary.is_file(): raise ValueError('Built Vision executable missing or unsafe')
    return app,hashlib.sha256(binary.read_bytes()).hexdigest()



def fixture_metadata(log):
    prefix='VISION_REMAINING_FIXTURE_JSON '
    lines=[line[len(prefix):] for line in log.splitlines() if line.startswith(prefix)]
    if len(lines)!=1 or len(lines[0].encode())>16_384: raise ValueError('Missing/duplicate/oversized native fixture metadata')
    return validate_fixture_metadata(json.loads(lines[0]))


def validate_fixture_metadata(row):
    if row.get('schema')!='Celluloid.VisionFixture.1' or row.get('bundle_identifier')!='Mango.Celluloid': raise ValueError('Wrong native fixture owner/schema')
    if row.get('package_name')!=FIXTURE_NAME or (row.get('pixel_width'),row.get('pixel_height'),row.get('initial_overlays'))!=(120,80,0): raise ValueError('Wrong synthetic fixture')
    for key in ('data_home','documents_path','package_path'):
        if not isinstance(row.get(key),str) or len(row[key])>2048 or not Path(row[key]).is_absolute(): raise ValueError('Invalid native fixture path')
    home=Path(row['data_home']);documents=Path(row['documents_path']);package=Path(row['package_path'])
    if documents!=home/'Documents' or package!=documents/FIXTURE_NAME: raise ValueError('Native fixture escaped its own app Documents')
    files=row.get('files')
    if type(files) is not list or len(files)!=2: raise ValueError('Unexpected native fixture child count')
    names=set()
    for item in files:
        name=item.get('name')
        if type(name) is not str or (name!='recipe.json' and not re.fullmatch(r'[0-9A-Fa-f-]{36}\.image',name)): raise ValueError('Unexpected fixture child')
        if type(item.get('bytes')) is not int or not 0<item['bytes']<=2_000_000 or re.fullmatch('[0-9a-f]{64}',item.get('sha256','')) is None: raise ValueError('Invalid native fixture hash/size')
        names.add(name)
    if len(names)!=2 or 'recipe.json' not in names: raise ValueError('Duplicate/missing fixture child')
    return row


def snapshot_fixture(container, metadata, *, after_ui=False):
    container=Path(container)
    if container.is_symlink() or not container.is_dir(): raise ValueError('Unsafe app data container')
    changed=container.resolve()!=Path(metadata['data_home']).resolve()
    if changed and not after_ui: raise ValueError('Pre-UI fixture container does not match staging')
    documents=container/'Documents'
    if documents.is_symlink() or not documents.is_dir(): raise ValueError('Unsafe native Documents directory')
    package=documents/FIXTURE_NAME
    if package.is_symlink() or not package.is_dir(): raise ValueError('Native package missing or symlinked')
    expected={x['name']:x for x in metadata['files']}; children=list(package.iterdir())
    if {x.name for x in children}!=set(expected): raise ValueError('Native package child set changed')
    records=[];recipe=None
    for child in sorted(children):
        if child.is_symlink() or not child.is_file(): raise ValueError('Unsafe native package child')
        with child.open('rb') as stream:data=stream.read(2_000_001)
        if not 0<len(data)<=2_000_000: raise ValueError('Native fixture read cap')
        record={'name':child.name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}; records.append(record)
        if (not after_ui or child.name!='recipe.json') and record!=expected[child.name]: raise ValueError('Fixture changed before editing or original source changed')
        if child.name=='recipe.json':recipe=json.loads(data)
    if recipe.get('format')!='Celluloid.Document' or recipe.get('version')!=1: raise ValueError('Wrong native package format')
    sources=recipe.get('sources')
    if type(sources) is not list or len(sources)!=1: raise ValueError('Native recipe lost its original source')
    source=sources[0]
    if str(uuid.UUID(source['id'])).upper()+'.image' not in expected or (source.get('pixelWidth'),source.get('pixelHeight'))!=(120,80): raise ValueError('Native recipe original source changed')
    overlays=recipe.get('overlays')
    if type(overlays) is not list or len(overlays)>1: raise ValueError('Unexpected fixture overlays')
    if not after_ui and (overlays or (recipe.get('canvasWidth'),recipe.get('canvasHeight'))!=(120,80)): raise ValueError('Native fixture was not pristine before UI')
    return {'container':str(container),'data_container_changed':changed,'fixture_contents_verified':True,'package_path':str(package),'files':records,'overlay_texts':[x.get('text') for x in overlays],
            'source_width':recipe.get('canvasWidth'),'source_height':recipe.get('canvasHeight')}



def environment(env):
    fixed = {'GITHUB_REPOSITORY':'100mango/Celluloid','GITHUB_REF':BRANCH,
             'GITHUB_WORKFLOW_REF':'100mango/Celluloid/'+WORKFLOW+'@'+BRANCH,
             'GITHUB_RUN_ATTEMPT':'1','GITHUB_JOB':'vision','GITHUB_EVENT_NAME':'push',
             'DEVELOPER_DIR':'/Applications/Xcode_27.app/Contents/Developer'}
    if any(env.get(k)!=v for k,v in fixed.items()): raise ValueError('Wrong fixed push cohort identity')
    sha=env.get('GITHUB_SHA','')
    if re.fullmatch('[0-9a-f]{40}',sha) is None or env.get('GITHUB_WORKFLOW_SHA')!=sha: raise ValueError('Source/workflow SHA mismatch')
    if re.fullmatch('[1-9][0-9]{0,19}',env.get('GITHUB_RUN_ID','')) is None: raise ValueError('Invalid run ID')
    return {k:env[k] for k in (*fixed,'GITHUB_SHA','GITHUB_WORKFLOW_SHA','GITHUB_RUN_ID')}


def load_origin(temp, binding, now):
    row=json.loads((Path(temp)/CLOCK).read_text())
    if row.get('binding')!=binding: raise ValueError('Original clock binding mismatch')
    started=row.get('started_monotonic')
    if type(started) not in (int,float) or not math.isfinite(started) or not 0<started<=now:
        raise ValueError('Invalid original monotonic clock')
    return started



def test_command(temp, device, selectors, result_name):
    return ['xcodebuild', '-project', 'CelluloidNative.xcodeproj', '-scheme', 'CelluloidVision',
            '-destination', f'platform=visionOS Simulator,id={device}', '-derivedDataPath', str(temp/'celluloid-vision'),
            '-resultBundlePath', str(temp/(result_name+'.xcresult')), 'CODE_SIGNING_ALLOWED=NO',
            '-parallel-testing-enabled', 'NO', '-collect-test-diagnostics', 'never',
            '-maximum-concurrent-test-simulator-destinations', '1',
            *['-only-testing:'+case for case in selectors], 'test-without-building']


def verify_cases(stdout, selectors):
    actual = re.findall(r"Test Case '-\[([^ ]+) ([^\]]+)\]' (passed|failed|skipped)", stdout)
    expected = {(path.split('/')[0]+'.'+path.split('/')[1], path.split('/')[2]) for path in selectors}
    if len(actual) != len(expected) or {(a,b) for a,b,_ in actual} != expected or any(c != 'passed' for _,_,c in actual):
        raise ValueError('Selected XCTest cases did not each actually pass exactly once')
    return [{'target_class': a, 'method': b, 'outcome': c} for a,b,c in actual]


class Job:
    def __init__(self, root, temp, source, execute=capture, clock=time.monotonic, started=None, binding=None):
        self.root, self.temp, self.source = Path(root), Path(temp), source
        self.execute, self.clock = execute, clock
        self.started = clock() if started is None else started
        self.deadline = self.started + WORK_END
        self.device = None; self.blocked = False
        self.simulator_devices_root = Path.home()/'Library/Developer/CoreSimulator/Devices'
        self.binding = binding
        self.report = {'source_sha':source,'selectors':list(SELECTORS),'operations':[],
                       'binding':binding,'started_monotonic':self.started,
                       'scope':'Only real editing UI; Python synthetic input staging. No hosted XCTest, privacy or archive rerun.',
                       'historical_fixture':dict(HISTORICAL_FIXTURE),
                       'historical_runtime':dict(HISTORICAL_RUNTIME),
                       'historical_unsigned_archive':dict(HISTORICAL_PACKAGE),'archive_executed_in_this_cohort':False,
                       'signed':False,'uploaded':False,'complete':False}
        self.folder=self.temp/'vision-remaining-evidence'; self.folder.mkdir(exist_ok=False)
        self.output=self.folder/'report.json'
        if (self.temp/'vision-remaining-device-uncertain.json').exists(): raise ValueError('Prior device uncertainty')
        self.persist()

    def persist(self):
        data=(json.dumps(self.report,indent=2)+'\n').encode()
        if len(data)>REPORT_CAP: raise ValueError('Report evidence cap exceeded')
        self.output.write_bytes(data)

    def call(self, phase, command, seconds, cleanup=False):
        if self.blocked: raise RuntimeError('Device/process uncertainty blocks further commands')
        if any(x['phase']==phase for x in self.report['operations']): raise ValueError('Duplicate phase')
        boundary=self.started+(CLEANUP_END if cleanup else WORK_END)
        if self.clock()+seconds+20>boundary: raise ValueError('Insufficient original job wall time before '+phase)
        row={'phase':phase,'command':list(map(str,command)),'timeout_seconds':seconds,
             'started_monotonic':self.clock(),'cleanup_reserve_seconds':20,'complete':False}
        self.report['operations'].append(row)
        print('VISION_PHASE_START '+json.dumps({'phase':phase,'timeout_seconds':seconds,'elapsed_seconds':self.clock()-self.started,'barrier':self.blocked}),flush=True)
        self.persist()
        stdout=stderr=b''; complete=False
        try:
            result=self.execute(command,seconds=seconds,cap=ARCHIVE_RAW_CAP,cleanup_grace=10)
            stdout,stderr=result.stdout,result.stderr; complete=True
            row['return_code']=result.returncode
            if result.returncode is None or result.returncode<0 or self.clock()>row['started_monotonic']+seconds:
                raise TimeoutError('Signalled/unfinalized child or late return')
            if result.returncode: raise ValueError('Known completed command failed: '+phase)
            if phase in ('build','archive') and re.search(rb'(?im)(?:^|[ :])(?:fatal )?error:',stdout+b'\n'+stderr):
                raise ValueError('Native build emitted an error despite zero exit')
            row['complete']=True
            result_text=stdout.decode('utf-8','replace')
            if phase in ('hosted','ui'): result_text+='\n'+stderr.decode('utf-8','replace')
            return result_text
        except ValueError as error:
            row['error']=str(error); raise
        except (CaptureStopped,TimeoutError,OSError,KeyboardInterrupt) as error:
            self.blocked=True; row['uncertain']=True; row['error']=str(error)
            if isinstance(error,CaptureStopped):
                stdout=getattr(error,'stdout_prefix',b''); stderr=getattr(error,'stderr_capture',b'')
                row['owned_cleanup_confirmed']=error.cleanup_confirmed
                row['cancelled_signal']=error.cancelled_signal
            marker=(json.dumps(row,indent=2)+'\n').encode()
            if len(marker)>1_000_000: raise ValueError('Uncertainty marker evidence cap exceeded')
            (self.temp/'vision-remaining-device-uncertain.json').write_bytes(marker)
            (self.folder/'vision-remaining-device-uncertain.json').write_bytes(marker)
            raise
        finally:
            row['finished_monotonic']=self.clock()
            if phase in ('hosted','ui'):
                observed=re.findall(r"Test Case '-\[([^ ]+) ([^\]]+)\]' (passed|failed|skipped)",(stdout+b'\n'+stderr).decode('utf-8','replace'))
                row['observed_test_terminals']={'capture_complete':complete,'count':len(observed),
                    'records':[{'target_class':a,'method':b,'outcome':c} for a,b,c in observed[:8]],
                    'truncated':len(observed)>8,'scope':'Observed log markers; not invocation qualification'}
            retain_archive_output(row,stdout,stderr,capture_complete=complete)
            # Full bounded bytes are parsed before the exact mature prefix/tail
            # retention adapter. Never treat the retained 512 KiB as full capture.
            text=row.pop('stdout')+'\n[stderr]\n'+row.pop('stderr')
            print('VISION_PHASE_END '+json.dumps({'phase':phase,'complete':row['complete'],'return_code':row.get('return_code'),
                'error':row.get('error'),'barrier':self.blocked,'capture_complete':complete,
                'elapsed_seconds':row['finished_monotonic']-row['started_monotonic'],
                'observed_test_terminals':row.get('observed_test_terminals')}),flush=True)
            if not row['complete']:
                tail=(stdout+b'\n[stderr]\n'+stderr)[-FAILURE_TAIL_CAP:]
                print('VISION_FAILURE_TAIL '+json.dumps({'phase':phase,'retained_bytes':len(tail),'tail_only':True})+'\n'+tail.decode('utf-8','replace'),flush=True)
            log=self.folder/(phase+'.log'); log.write_text(text)
            row['retained_log']={'name':log.name,'bytes':log.stat().st_size,
                                 'sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
            self.persist()

    def source_identity(self, phase):
        def git(suffix,*args): return self.call(phase+'-'+suffix,['git',*args],10).strip()
        if git('head','rev-parse','HEAD')!=self.source: raise ValueError('Wrong source HEAD')
        if git('base','rev-parse',BASE+'^{tree}')!=BASE_TREE: raise ValueError('Wrong base tree')
        if git('parent','rev-list','--parents','-n','1','HEAD').split()!=[self.source,BASE]: raise ValueError('Wrong sole parent')
        if git('status','status','--porcelain','--untracked-files=all'): raise ValueError('Dirty candidate')
        actual=git('scope','diff','--name-status',BASE,'HEAD','--').splitlines()
        expected=['M\t'+p for p in MODIFIED]+['A\t'+p for p in ADDED]
        if sorted(actual)!=sorted(expected): raise ValueError('Unexpected source scope')
        self.report[phase]={'tree':git('tree','rev-parse','HEAD^{tree}'),'parent':BASE,'scope_verified':True}

    def owned_container(self, phase):
        value=self.call(phase,['xcrun','simctl','get_app_container',self.device,'Mango.Celluloid','data'],180).strip()
        container=Path(value); expected_parent=self.simulator_devices_root/self.device/'data/Containers/Data/Application'
        if not container.is_absolute() or container.is_symlink() or container.parent.resolve()!=expected_parent.resolve(): raise ValueError('Container outside owned simulator data scope')
        uuid.UUID(container.name)
        return container

    def observe_fixture(self, phase, metadata, *, after_ui=False):
        container=self.owned_container(phase)
        self.report[phase]={'observed_container':str(container),'declared_fixture_data_home':metadata['data_home'],
                            'same_container':container.resolve()==Path(metadata['data_home']).resolve()}
        self.persist()
        snapshot=snapshot_fixture(container,metadata,after_ui=after_ui)
        self.report[phase].update(snapshot);self.persist()
        return snapshot

    def work(self):
        if self.binding is not None: self.source_identity('source-before')
        toolchain=self.call('toolchain',['xcodebuild','-version'],30)
        if toolchain.splitlines()[:1]!=['Xcode 27.0']: raise ValueError('Unqualified Xcode toolchain')
        self.report['toolchain']=toolchain
        # These are hard prerequisites. A fixture test failure cannot skip icon
        # materialization and then let an iconless build continue via always().
        self.call('icons', ['swift','-swift-version','5','Scripts/materialize_native_icons.swift'], 180)
        self.call('icon-inputs', [sys.executable,'Scripts/verify_native_icon_inputs.py'], 30)
        self.call('build', ['xcodebuild','-project','CelluloidNative.xcodeproj','-scheme','CelluloidVision',
            '-destination','generic/platform=visionOS Simulator','-derivedDataPath',str(self.temp/'celluloid-vision'),
            'CODE_SIGNING_ALLOWED=NO','build-for-testing'], 600)
        runtimes = json.loads(self.call('runtimes',['xcrun','simctl','list','runtimes','--json'],60))['runtimes']
        available = [r for r in runtimes if r.get('isAvailable') and r.get('identifier') == 'com.apple.CoreSimulator.SimRuntime.xrOS-27-0']
        if len(available) != 1: raise ValueError('Expected exact available visionOS 27 runtime')
        runtime = available[0]
        types = json.loads(self.call('types',['xcrun','simctl','list','devicetypes','--json'],60))['devicetypes']
        wanted = 'com.apple.CoreSimulator.SimDeviceType.Apple-Vision-Pro-4K'
        if sum(t.get('identifier') == wanted for t in types) != 1 or wanted not in {t['identifier'] for t in runtime['supportedDeviceTypes']}:
            raise ValueError('Expected compatible Apple Vision Pro type')
        raw = self.call('create',['xcrun','simctl','create','Celluloid Vision Remaining '+self.source[:12],wanted,runtime['identifier']],60).strip()
        uuid.UUID(raw) # Validate syntax only; xcodebuild requires the returned identifier's exact spelling.
        self.device = raw
        self.report['device'] = self.device; self.report['runtime'] = runtime
        self.call('boot',['xcrun','simctl','boot',self.device],60)
        self.call('bootstatus',['xcrun','simctl','bootstatus',self.device,'-b'],240)
        # Install the exact fresh build, then stage a safe synthetic input in
        # its own Documents. No hosted XCTest or redundant app launch is needed.
        app,binary_sha=built_vision_app(self.temp)
        self.report['built_app']={'path':str(app),'binary_sha256':binary_sha};self.persist()
        self.call('install',['xcrun','simctl','install',self.device,str(app)],300)
        container=self.owned_container('seed-before-ui')
        metadata=write_synthetic_fixture(container);self.report['fixture_metadata']=metadata
        self.report['seed-before-ui']={'observed_container':str(container),'declared_fixture_data_home':metadata['data_home'],
                                      'same_container':True,**snapshot_fixture(container,metadata)}
        self.persist()
        ui_failure=None;ui=None
        try:ui=self.call('ui',test_command(self.temp,self.device,[EDIT],'VisionRemainingUI'),900)
        except ValueError as error:ui_failure=error
        ui_operation=next((x for x in self.report['operations'] if x['phase']=='ui'),None)
        if ui_operation and type(ui_operation.get('return_code')) is int and ui_operation['return_code']>=0 and not self.blocked:
            try:snapshot=self.observe_fixture('seed-after-ui',metadata,after_ui=True)
            except BaseException as error:
                self.report['seed_after_ui_error']=str(error);self.persist()
                if ui_failure is not None:raise ui_failure from error
                raise
        if ui_failure is not None:raise ui_failure
        self.report['ui'] = verify_cases(ui,[EDIT])
        if snapshot['overlay_texts']!=['Vision 世界'] or (snapshot['source_width'],snapshot['source_height'])!=(120,80):raise ValueError('Actual native package did not retain exact edited text/source dimensions')
        self.call('icons-after',[sys.executable,'Scripts/verify_native_icon_inputs.py'],30)
        if self.binding is not None: self.source_identity('source-after')
        self.report['functional_cases_passed'] = True

    def finish(self):
        self.report['cleanup'] = []
        if self.device and not self.blocked:
            for action in ['shutdown','delete']:
                try:
                    self.call(action,['xcrun','simctl',action,self.device],45,cleanup=True)
                    self.report['cleanup'].append({'action':action,'success':True})
                except BaseException as error:
                    self.report['cleanup'].append({'action':action,'success':False,'error':str(error)})
                    break
        self.report['device_uncertain'] = self.blocked
        self.report['complete'] = bool(self.report.get('functional_cases_passed') and not self.blocked and
                                       len(self.report['cleanup']) == 2 and all(x['success'] for x in self.report['cleanup']))
        self.report['elapsed_seconds'] = self.clock()-self.started
        print('VISION_JOB_END '+json.dumps({k:self.report.get(k) for k in ('source_sha','complete','device_uncertain','error','elapsed_seconds','ui')}),flush=True)
        self.persist()


def pack(temp, binding, started, now):
    temp=Path(temp); folder=temp/'vision-remaining-evidence'
    if now>started+PACK_END: raise ValueError('Original evidence finalization deadline exceeded')
    folder.mkdir(exist_ok=True)
    report=folder/'report.json'
    if not report.exists(): report.write_text(json.dumps({'complete':False,'error':'Driver produced no final report','binding':binding})+'\n')
    # Retain existing local package/icon receipts even when later tests fail.
    for name in ('native-icon-provenance-runtime.json','vision-remaining-device-uncertain.json'):
        source=temp/name
        if source.exists():
            if source.is_symlink() or not source.is_file() or source.stat().st_size>1_000_000: raise ValueError('Unsafe/oversized receipt')
            (folder/name).write_bytes(source.read_bytes())
    members=[]
    for name,cap in sorted(EVIDENCE_FILES.items()):
        if name=='manifest.json': continue
        path=folder/name
        if path.is_symlink(): raise ValueError('Unsafe evidence file')
        if not path.exists(): continue
        if not path.is_file() or path.stat().st_size>cap: raise ValueError('Evidence file cap/type')
        data=path.read_bytes()
        members.append({'name':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    if len(members)>64: raise ValueError('Evidence member cap')
    manifest={'binding':binding,'started_monotonic':started,'packed_monotonic':now,'members':members,'max_bytes':EVIDENCE_CAP}
    encoded=(json.dumps(manifest,indent=2)+'\n').encode()
    if len(encoded)>EVIDENCE_FILES['manifest.json']: raise ValueError('Manifest evidence cap')
    if sum(x['bytes'] for x in members)+len(encoded)>EVIDENCE_CAP: raise ValueError('Evidence aggregate cap')
    (folder/'manifest.json').write_bytes(encoded)
    return manifest


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--execute',action='store_true'); parser.add_argument('--pack',action='store_true'); parser.add_argument('--finish-upload',action='store_true'); args=parser.parse_args()
    if not any((args.execute,args.pack,args.finish_upload)):
        print(json.dumps({'candidate_only':True,'cases':SELECTORS,'commands_use_existing_XCTest_launch':True},indent=2)); return 0
    root=Path(__file__).resolve().parents[1]; temp=Path(os.environ['RUNNER_TEMP'])
    if Path.cwd().resolve()!=root: raise ValueError('Run from the exact candidate repository')
    binding=environment(os.environ); started=load_origin(temp,binding,time.monotonic())
    if args.pack:
        print('VISION_PACK_START '+json.dumps({'elapsed_seconds':time.monotonic()-started}),flush=True)
        try:
            pack(temp,binding,started,time.monotonic())
            if time.monotonic()>started+PACK_END or time.monotonic()+120>started+FINISH_END: raise ValueError('Original pack/upload deadline reserve unavailable')
            print('VISION_PACK_END '+json.dumps({'complete':True,'elapsed_seconds':time.monotonic()-started}),flush=True)
        except BaseException as error:
            print('VISION_PACK_FAILURE '+json.dumps({'error':str(error),'elapsed_seconds':time.monotonic()-started}),flush=True)
            raise
        return 0
    if args.finish_upload:
        if time.monotonic()>started+FINISH_END: raise ValueError('Original upload deadline exceeded')
        if os.environ.get('VISION_UPLOAD_OUTCOME')!='success': raise ValueError('Evidence upload did not succeed')
        report=json.loads((temp/'vision-remaining-evidence/report.json').read_text())
        return 0 if report.get('complete') else 1
    job=Job(root,temp,binding['GITHUB_SHA'],started=started,binding=binding)
    try: job.work()
    except BaseException as error:
        job.report['error']=str(error)
        print('VISION_JOB_FAILURE '+json.dumps({'error':str(error),'barrier':job.blocked}),flush=True)
    finally: job.finish()
    return 0 if job.report['complete'] else 1

if __name__=='__main__': raise SystemExit(main())
