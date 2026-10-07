#!/usr/bin/env python3
"""Fixed three-case Vision runtime successor; preserve actual device ID spelling.

The prior db4 cohort's archive/package proof remains historical evidence. This
cohort does not repeat Release archive work and cannot relabel that old run green.
"""
import argparse
import hashlib
import math
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid
from mac_archive_capture import capture, CaptureStopped
from vision_remaining_retention import ARCHIVE_RAW_CAP, retain_archive_output

HOSTED = 'CelluloidVisionTests/NativeVisionTests/testSharedFieldMutationsRetainUnicodeAcrossBothOrdersUndoAndReopen'
EDIT = 'CelluloidVisionUITests/NativeVisionUITests/testSeededDocumentSequentialTextUndoRedoAndRelaunch'
PRIVACY = 'CelluloidVisionUITests/NativeVisionUITests/testSimplifiedChineseDocumentPrivacyAndLargeText'
SELECTORS = (HOSTED, EDIT, PRIVACY)
BASE = 'db4d719abdf11504e99e211ffc27d7555883acb3'
BASE_TREE = '324d560eb7e1b6ab7e28bfda39f7364c8916971d'
BRANCH = 'refs/heads/codex/vision-remaining'
WORKFLOW = '.github/workflows/vision-remaining.yml'
CLOCK = 'vision-remaining-clock.json'
WORK_END, CLEANUP_END, PACK_END, FINISH_END = 3000, 3150, 3200, 3360
EVIDENCE_CAP = 8_000_000
MODIFIED = (WORKFLOW,'Documentation/vision-remaining.md','Scripts/run_vision_remaining.py','Scripts/test_vision_remaining.py')
ADDED = ()
HISTORICAL_PACKAGE = {'source_sha':BASE,'run_id':37608605492,'artifact_id':11477245993,
    'artifact_sha256':'126ecef09c9fac1f8d0972071cceb82513c0f2fcba7a113a4da1fbd6fc8aa46d',
    'scope':'Historical component reference only; no archive/package execution in this runtime-only cohort'}



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
        self.binding = binding
        self.report = {'source_sha':source,'selectors':list(SELECTORS),'operations':[],
                       'binding':binding,'started_monotonic':self.started,
                       'scope':'Runtime-only: seeded intake; real text/Undo/relaunch and Chinese policy. No Files/PNG or Release archive rerun.',
                       'historical_unsigned_archive':dict(HISTORICAL_PACKAGE),'archive_executed_in_this_cohort':False,
                       'signed':False,'uploaded':False,'complete':False}
        self.folder=self.temp/'vision-remaining-evidence'; self.folder.mkdir(exist_ok=False)
        self.output=self.folder/'report.json'
        if (self.temp/'vision-remaining-device-uncertain.json').exists(): raise ValueError('Prior device uncertainty')
        self.output.write_text(json.dumps(self.report,indent=2)+'\n')

    def persist(self):
        self.output.write_text(json.dumps(self.report,indent=2)+'\n')

    def call(self, phase, command, seconds, cleanup=False):
        if self.blocked: raise RuntimeError('Device/process uncertainty blocks further commands')
        if any(x['phase']==phase for x in self.report['operations']): raise ValueError('Duplicate phase')
        boundary=self.started+(CLEANUP_END if cleanup else WORK_END)
        if self.clock()+seconds+20>boundary: raise ValueError('Insufficient original job wall time before '+phase)
        row={'phase':phase,'command':list(map(str,command)),'timeout_seconds':seconds,
             'started_monotonic':self.clock(),'cleanup_reserve_seconds':20,'complete':False}
        self.report['operations'].append(row); self.persist()
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
        except (CaptureStopped,TimeoutError,OSError,KeyboardInterrupt) as error:
            self.blocked=True; row['uncertain']=True; row['error']=str(error)
            if isinstance(error,CaptureStopped):
                stdout=getattr(error,'stdout_prefix',b''); stderr=getattr(error,'stderr_capture',b'')
                row['owned_cleanup_confirmed']=error.cleanup_confirmed
                row['cancelled_signal']=error.cancelled_signal
            (self.temp/'vision-remaining-device-uncertain.json').write_text(json.dumps(row,indent=2)+'\n')
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
        # XCTest installs/launches the actual host and writes the native fixture.
        # There is no simctl install/container lookup/launch/ps/screenshot/terminate preflight.
        hosted = self.call('hosted',test_command(self.temp,self.device,[HOSTED],'VisionRemainingHosted'),360)
        self.report['hosted'] = verify_cases(hosted,[HOSTED])
        if 'VISION_REMAINING_SEED native writer/readback;' not in hosted:
            raise ValueError('Native UI fixture writer/readback did not complete')
        ui = self.call('ui',test_command(self.temp,self.device,[EDIT,PRIVACY],'VisionRemainingUI'),900)
        self.report['ui'] = verify_cases(ui,[EDIT,PRIVACY])
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
        self.persist()


def pack(temp, binding, started, now):
    temp=Path(temp); folder=temp/'vision-remaining-evidence'
    if now>started+PACK_END: raise ValueError('Original evidence finalization deadline exceeded')
    folder.mkdir(exist_ok=True)
    report=folder/'report.json'
    if not report.exists(): report.write_text(json.dumps({'complete':False,'error':'Driver produced no final report','binding':binding})+'\n')
    # Retain existing local package/icon receipts even when later tests fail.
    for name in ('vision-release-packaging.json','native-icon-provenance-runtime.json','vision-remaining-device-uncertain.json'):
        source=temp/name
        if source.exists():
            if source.is_symlink() or not source.is_file() or source.stat().st_size>1_000_000: raise ValueError('Unsafe/oversized receipt')
            (folder/name).write_bytes(source.read_bytes())
    members=[]
    for path in sorted(folder.iterdir()):
        if path.name=='manifest.json': continue
        if path.is_symlink() or not path.is_file() or not re.fullmatch(r'[a-z0-9-]+\.(json|log)',path.name): raise ValueError('Unexpected evidence file')
        data=path.read_bytes()
        if len(data)>2_000_000: raise ValueError('Evidence file cap')
        members.append({'name':path.name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    if len(members)>64: raise ValueError('Evidence member cap')
    manifest={'binding':binding,'started_monotonic':started,'packed_monotonic':now,'members':members,'max_bytes':EVIDENCE_CAP}
    encoded=(json.dumps(manifest,indent=2)+'\n').encode()
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
        pack(temp,binding,started,time.monotonic())
        if time.monotonic()+120>started+FINISH_END: raise ValueError('Full upload/finalization reserve unavailable')
        with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('evidence_ready=true\n')
        return 0
    if args.finish_upload:
        if time.monotonic()>started+FINISH_END: raise ValueError('Original upload deadline exceeded')
        if os.environ.get('VISION_UPLOAD_OUTCOME')!='success': raise ValueError('Evidence upload did not succeed')
        report=json.loads((temp/'vision-remaining-evidence/report.json').read_text())
        return 0 if report.get('complete') else 1
    job=Job(root,temp,binding['GITHUB_SHA'],started=started,binding=binding)
    try: job.work()
    except BaseException as error: job.report['error']=str(error)
    finally: job.finish()
    return 0 if job.report['complete'] else 1

if __name__=='__main__': raise SystemExit(main())
