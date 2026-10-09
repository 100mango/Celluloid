#!/usr/bin/env python3
"""Closed, source-bound one-install observation; never dispatch Photos/XCTest."""
import hashlib,json,math,os,re,signal,stat,subprocess,sys,time,uuid
from pathlib import Path
from run_ios_photos_host_diagnostic import HostDiagnostic
from run_swiftui_acceptance import ROOT,OUT,DERIVED,require,save,extract_json,owner_receipt
from run_ios_photos_host import product_control,PRODUCT_SHA,PRODUCT_CONTROL_TREE,PRODUCT_CONTROL_SHA256,PROBE_FIXED_FILES
from run_picker_acceptance import build_binding

BRANCH='cell-ios-install-diagnostic'
WORKFLOW='.github/workflows/ios-install-diagnostic.yml'
CONFIG='.github/ios-install-diagnostic.json'
BASE_SHA='5163f1c3632e3f78bb549065a31f3417efd7f94a'
BASE_TREE='550a42c24cb9a1644a952c1917b2e44db73387da'
CONTROL_PATHS=frozenset([CONFIG,WORKFLOW,'Scripts/run_ios_install_diagnostic.py','Scripts/test_ios_install_diagnostic.py','Scripts/ios_install_observer.py','Scripts/test_ios_install_observer.py','Scripts/run_bounded.py'])
EXPECTED_BINARY='e8a98ee62ee4df42bfaedc1d1e3b15c284231074237ee3dd1af48648d5439408'
EXPECTED_BUNDLE='ac903681326cd5a38786d6942e8dca129302007a95d1373bde2ac4d614537f00'
ADMISSION=ROOT/'build/install-diagnostic-source-before.json'
OBSERVATIONS=OUT/'install-observation'

def strict_json(path,limit=32768):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd);require(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and 0<info.st_size<=limit,'Unsafe/bounded control file')
        raw=os.read(fd,limit+1);after=os.fstat(fd)
        require(len(raw)==info.st_size and (info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),'Control file changed')
    finally:os.close(fd)
    def pairs(items):
        value={}
        for key,item in items:require(key not in value,'Duplicate control field');value[key]=item
        return value
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:require(False,'Nonfinite control'))

def config_check(config):
    require(type(config) is dict and set(config)=={'schema','mode','READY','sourceReady','nativeAuthorization','base_sha','base_tree','maximum_additional_spend_usd'},'Unknown install-only fields')
    require(type(config['schema']) is int and config['schema']==1 and config['mode']=='install-only','Wrong diagnostic scope')
    require(all(config[k] is True for k in ['READY','sourceReady','nativeAuthorization']),'Install diagnostic is closed')
    require(config['base_sha']==BASE_SHA and config['base_tree']==BASE_TREE,'Wrong frozen source baseline')
    require(type(config['maximum_additional_spend_usd']) is int and config['maximum_additional_spend_usd']==0,'Unapproved spend')

def context_check(env):
    expected={'GITHUB_REPOSITORY':'100mango/Celluloid','GITHUB_EVENT_NAME':'push','GITHUB_REF':'refs/heads/'+BRANCH,'GITHUB_WORKFLOW_REF':'100mango/Celluloid/'+WORKFLOW+'@refs/heads/'+BRANCH,'GITHUB_RUN_ATTEMPT':'1'}
    require(all(env.get(k)==v for k,v in expected.items()),'Wrong install-only route or retry')
    require(re.fullmatch('[0-9a-f]{40}',env.get('GITHUB_SHA','')) and env.get('GITHUB_WORKFLOW_SHA')==env['GITHUB_SHA'],'Wrong exact workflow/source')
    require(re.fullmatch('[1-9][0-9]*',env.get('GITHUB_RUN_ID','')),'Missing run identity')

def validate_admission(config,env,facts):
    config_check(config);context_check(env)
    require(facts['head']==env['GITHUB_SHA'] and re.fullmatch('[0-9a-f]{40}',facts['tree']),'Head/tree mismatch')
    require(facts['base_tree']==BASE_TREE and not facts['dirty'] and set(facts['paths'])==CONTROL_PATHS,'Frozen source changed')
    require(0<len(facts['chain'])<=8,'Unbounded install control history');prior=BASE_SHA
    for row in facts['chain']:
        require(row['parents']==[prior] and row['paths'] and set(row['paths'])<=CONTROL_PATHS,'Unknown control mutation or merge');prior=row['sha']
    require(prior==facts['head'],'Incomplete install control history')
    return dict(schema='Celluloid.InstallOnlyAdmission.1',diagnostic_only=True,source_sha=facts['head'],source_tree=facts['tree'],base_sha=BASE_SHA,base_tree=BASE_TREE,product_sha=PRODUCT_SHA,product_tree=PRODUCT_CONTROL_TREE,run_id=env['GITHUB_RUN_ID'],run_attempt='1',release_qualification=False,host_methods_planned=0)

def fingerprint():
    return hashlib.sha256(json.dumps([[p,hashlib.sha256((ROOT/p).read_bytes()).hexdigest()] for p in sorted(CONTROL_PATHS)],separators=(',',':')).encode()).hexdigest()

def admit():
    config=strict_json(ROOT/CONFIG);config_check(config);context_check(os.environ)
    deadline=time.monotonic()+15
    def git(*args):
        remaining=min(5,deadline-time.monotonic());require(remaining>0,'Admission deadline');return subprocess.check_output(['git',*args],cwd=ROOT,text=True,timeout=remaining).strip()
    git('merge-base','--is-ancestor',BASE_SHA,'HEAD');chain=[]
    for line in git('rev-list','--reverse','--parents',BASE_SHA+'..HEAD').splitlines():
        fields=line.split();require(len(fields)==2,'Nonlinear control');chain.append(dict(sha=fields[0],parents=fields[1:],paths=git('diff','--name-only',fields[1],fields[0]).splitlines()))
    facts=dict(head=git('rev-parse','HEAD'),tree=git('rev-parse','HEAD^{tree}'),base_tree=git('rev-parse',BASE_SHA+'^{tree}'),dirty=git('status','--porcelain','--untracked-files=all'),paths=git('diff','--name-only',BASE_SHA,'HEAD').splitlines(),chain=chain)
    receipt=validate_admission(config,os.environ,facts)
    require(product_control(ROOT)==(424,PRODUCT_CONTROL_SHA256),'Corrected product differs')
    for p,digest in PROBE_FIXED_FILES.items():require(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==digest,'Frozen host test/project differs')
    receipt['control_fingerprint']=fingerprint();return receipt

def bounded_admission(label,command,seconds):
    # Called before Popen only for this exact additional route. Existing routes
    # do not import or invoke this helper and retain their original semantics.
    config_check(strict_json(ROOT/CONFIG));context_check(os.environ)
    receipt=strict_json(ADMISSION)
    require(receipt.get('source_sha')==os.environ['GITHUB_SHA'] and receipt.get('base_sha')==BASE_SHA and receipt.get('base_tree')==BASE_TREE and receipt.get('run_id')==os.environ['GITHUB_RUN_ID'] and receipt.get('run_attempt')=='1' and receipt.get('diagnostic_only') is True and receipt.get('host_methods_planned')==0 and receipt.get('control_fingerprint')==fingerprint(),'Missing/stale exact install admission')
    simple={'clean-start':(15,['git','diff','--exit-code','HEAD','--']),'toolchain':(30,['xcodebuild','-version']),'host-portable':(30,[sys.executable,'-S','Scripts/test_ios_install_diagnostic.py']),'devices-before':(20,['xcrun','simctl','list','devices','available','-j']),'devices-after-create':(20,['xcrun','simctl','list','devices','available','-j']),'create-owned-device':(60,[sys.executable,'Scripts/select_test_devices.py','iPhone SE (3rd generation)'])}
    if label in simple:expected_cap,expected=simple[label]
    else:
        owner=strict_json(OUT/'owned-simulator.json');device=owner.get('device_id');require(type(device) is str and str(uuid.UUID(device)).upper()==device,'Malformed owned device')
        require(owner.get('source_sha')==os.environ['GITHUB_SHA'] and owner.get('run_id')==os.environ['GITHUB_RUN_ID'] and owner.get('run_attempt')=='1' and owner.get('created_by_this_job') is True and owner.get('absent_before_create') is True and owner.get('runtime_id')=='com.apple.CoreSimulator.SimRuntime.iOS-27-0','Wrong fresh device ownership')
        dynamic={'boot':(60,['xcrun','simctl','boot',device]),'bootstatus':(300,['xcrun','simctl','bootstatus',device,'-b']),'install-owned-app':(120,['xcrun','simctl','install',device,str(DERIVED/'Build/Products/Debug-iphonesimulator/Celluloid.app')]),'cleanup-shutdown':(30,['xcrun','simctl','shutdown',device]),'cleanup-delete':(30,['xcrun','simctl','delete',device]),'build':(720,['xcodebuild','-project','Celluloid.xcodeproj','-scheme','Celluloid','-configuration','Debug','-destination','platform=iOS Simulator,id='+device,'-derivedDataPath',str(DERIVED),'CODE_SIGNING_ALLOWED=NO','CODE_SIGNING_REQUIRED=NO','COMPILER_INDEX_STORE_ENABLE=NO','-jobs','2','build-for-testing'])}
        require(label in dynamic,'Unknown diagnostic command');expected_cap,expected=dynamic[label]
    require(seconds==expected_cap and command==expected,'Command scope/cap mismatch')
    return dict(source_sha=receipt['source_sha'],run_id=receipt['run_id'],run_attempt='1')

def defer_cancellation(on_cancel=None):
    """Do not abandon owned children on SIGTERM/SIGINT; retain their caps."""
    state=[None]
    def stop(signum,frame):
        if state[0] is None:state[0]=signum
        if on_cancel is not None:on_cancel(signum)
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    return state

def logger_settled(receipt):
    if type(receipt) is not dict or receipt.get('uncertain') is not False:return False
    pid=receipt.get('host_pid')
    if pid is None:return receipt.get('outcome') in ('spawn_failed','skipped_insufficient_budget')
    return type(pid) is int and pid>0 and receipt.get('simulator_stream_settled') is True

class InstallObservation:
    """Same wrapper owns logger, exact install child and optional sampler."""
    def __init__(self,context,command,deadline,cancelled):
        from ios_install_observer import DeviceLog
        self.context=context;self.deadline=deadline;self.cancelled=cancelled;self.finished=False
        self.collector=DeviceLog(OBSERVATIONS,command[3],context['source_sha'],context['run_id'],context['run_attempt'],deadline)
        self.native=None;self.control_errors=[]
        context['device_log']=self.collector;context['cancelled']=cancelled
    def start(self):
        require(not self.cancelled() and time.monotonic()<self.deadline,'Cancelled/expired before logger dispatch')
        start=self.collector.start()
        print('INSTALL_LOG_DISPATCH',json.dumps(start,sort_keys=True),flush=True)
    def spawn(self,callback):
        return self.collector.spawn_if_certain(callback,self.deadline,self.cancelled)
    def observed(self,code,when=None):
        sample=self.context.get('sample_receipt')
        if when is None and type(sample) is dict and sample.get('install_returncode')==code and type(sample.get('install_return_monotonic')) in (float,int):when=sample['install_return_monotonic']
        when=time.monotonic() if when is None else when
        self.native={'returncode':code,'observed_monotonic':when,'deadline_monotonic':self.deadline,'within_deadline':when<=self.deadline}
    def finish(self):
        if self.finished:return
        self.finished=True
        logger=None
        try:logger=self.collector.finish()
        except BaseException as error:self.control_errors.append({'phase':'logger-finalization','error':type(error).__name__})
        sample=self.context.get('sample_receipt')
        if self.native is None and type(sample) is dict and type(sample.get('install_returncode')) is int and type(sample.get('install_return_monotonic')) in (float,int):
            self.observed(sample['install_returncode'],sample['install_return_monotonic'])
        log_safe=logger_settled(logger)
        sample_safe=type(sample) is dict and sample.get('uncertain') is False
        uncertain=not log_safe or not sample_safe or bool(self.control_errors) or bool(self.cancelled())
        result={'schema':'Celluloid.InstallWrapperObservation.1',**{k:self.context[k] for k in ['source_sha','run_id','run_attempt']},
                'native_install':self.native,'logger':logger,'sample':sample,'control_errors':self.control_errors,
                'cancelled':bool(self.cancelled()),'prohibit_further_simctl':uncertain}
        print('INSTALL_WRAPPER_OBSERVATION',json.dumps(result,sort_keys=True),flush=True)
        if uncertain:print('BOUNDED_COMMAND_CLEANUP_UNCONFIRMED install observation/cancellation',flush=True)
        try:save(OBSERVATIONS/'install-wrapper-observation.json',result)
        except (OSError,ValueError,TypeError) as error:
            print('BOUNDED_COMMAND_CLEANUP_UNCONFIRMED install observation retention '+type(error).__name__,flush=True)

def owned_inventory_projection(before,after,owner):
    """Public proof contains only the admitted new device, never other rows."""
    device=owner['device_id'];runtime=owner['runtime_id']
    prior=[item for group in before['devices'].values() for item in group if item.get('udid')==device]
    current=[(rt,item) for rt,group in after['devices'].items() for item in group if item.get('udid')==device]
    require(not prior and len(current)==1,'Owned inventory projection is not fresh/unique')
    rt,item=current[0]
    require(rt==runtime=='com.apple.CoreSimulator.SimRuntime.iOS-27-0' and item.get('name')=='Celluloid iOS27 iPhone SE (3rd generation)' and item.get('state')=='Shutdown' and item.get('isAvailable') is True,'Owned inventory projection differs')
    require(owner.get('created_by_this_job') is True and owner.get('absent_before_create') is True,'Unadmitted owned projection')
    def digest(value):return hashlib.sha256((json.dumps(value,indent=2,sort_keys=True)+'\n').encode()).hexdigest()
    return {'schema':'Celluloid.OwnedInventoryProjection.1',**{k:owner[k] for k in ['source_sha','run_id','run_attempt','device_id','runtime_id']},
            'before_owned_matches':[], 'after_owned_matches':[{'runtime_id':rt,**{k:item[k] for k in ['udid','name','state','isAvailable']}}],
            'local_full_inventory_sha256':{'before':digest(before),'after':digest(after)},'full_inventory_publicly_retained':False}

def known_runtime_metadata(owner):
    require(owner.get('runtime_id')=='com.apple.CoreSimulator.SimRuntime.iOS-27-0','Wrong admitted runtime identity')
    return {'identifier':owner['runtime_id'],**{k:owner[k] for k in ['source_sha','run_id','run_attempt']},
            'exact_runtime_build':None,'exact_runtime_build_status':'unavailable_no_additional_query'}

def pressure_snapshot():
    value={'monotonic':time.monotonic(),'cpu_count':os.cpu_count(),'memory_bytes':None,'memory_status':'unavailable_no_additional_query'}
    try:value['load_average']=list(os.getloadavg())
    except OSError as error:value['load_error']=type(error).__name__
    return value

class InstallDiagnostic(HostDiagnostic):
    def command(self,*args,**kwargs):
        require(not getattr(self,'cancel_signal',None),'Cancelled install-only route refuses further dispatch')
        return super().command(*args,**kwargs)

    def cancel(self,signum):
        self.cancel_signal=signum;self.uncertain=True

    def cleanup(self):
        if not self.device or self.uncertain:return
        deadline=min(self.started+2370,time.monotonic()+90)
        for action in ['shutdown','delete']:
            if self.uncertain or getattr(self,'cancel_signal',None) or deadline-time.monotonic()<35:return
            dispatched=time.monotonic();path=OUT/('cleanup-'+action+'.log')
            command=[sys.executable,'-S','Scripts/run_bounded.py','--seconds','30','--label','cleanup-'+action,
                     '--deadline-monotonic',str(dispatched+30),'xcrun','simctl',action,self.device]
            try:
                with path.open('wb') as stream:code=subprocess.call(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
            except BaseException:self.uncertain=True;raise
            elapsed=time.monotonic()-dispatched;late=elapsed>30
            save(OUT/('cleanup-'+action+'-dispatch-timing.json'),{'phase':'cleanup-'+action,'elapsed_seconds':elapsed,'limit_seconds':30,'returned_exit_code':code,'late_completion':late})
            if code or late or self.uncertain or getattr(self,'cancel_signal',None):self.uncertain=True;return
        self.device=None

    def run(self):
        require(sys.platform=='darwin' and os.environ.get('DEVELOPER_DIR')=='/Applications/Xcode_27.app/Contents/Developer','Wrong Xcode27 host')
        self.source_tree=self.admission['source_tree'];self.install_result=None;self.observation=None;self.diagnostic_errors=[]
        self.command('clean-start',['git','diff','--exit-code','HEAD','--'],15)
        _,version=self.command('toolchain',['xcodebuild','-version'],30);require('Xcode 27.0' in version.splitlines(),'Wrong toolchain')
        self.command('host-portable',[sys.executable,'-S','Scripts/test_ios_install_diagnostic.py'],30)
        _,raw=self.command('devices-before',['xcrun','simctl','list','devices','available','-j'],20,simulator=True);before=extract_json(raw,'devices');save(OUT/'devices-before.json',before)
        _,raw=self.command('create-owned-device',[sys.executable,'Scripts/select_test_devices.py','iPhone SE (3rd generation)'],60,simulator=True);devices=re.findall(r'^([0-9A-Fa-f-]{36}) iPhone SE \(3rd generation\)$',raw,re.M);require(len(devices)==1,'Ambiguous owned create');device=devices[0]
        _,raw=self.command('devices-after-create',['xcrun','simctl','list','devices','available','-j'],20,simulator=True);after=extract_json(raw,'devices');save(OUT/'devices-after-create.json',after)
        owner=owner_receipt(before,after,device,os.environ,self.source,self.started,self.deadline);self.device=device;save(OUT/'owned-simulator.json',owner);save(OUT/'owned-inventory-projection.json',owned_inventory_projection(before,after,owner))
        base=['xcodebuild','-project','Celluloid.xcodeproj','-scheme','Celluloid','-configuration','Debug','-destination','platform=iOS Simulator,id='+device,'-derivedDataPath',str(DERIVED),'CODE_SIGNING_ALLOWED=NO','CODE_SIGNING_REQUIRED=NO','COMPILER_INDEX_STORE_ENABLE=NO']
        self.command('build',[*base,'-jobs','2','build-for-testing'],720)
        binary=DERIVED/'Build/Products/Debug-iphonesimulator/Celluloid.app/Celluloid';binding=build_binding(binary,self.source,self.source_tree);save(OUT/'build-binding.json',binding)
        require(binding['app_binary_sha256']==EXPECTED_BINARY and binding['app_bundle_sha256']==EXPECTED_BUNDLE,'Built install payload differs from successful and failed historical payloads')
        self.command('boot',['xcrun','simctl','boot',device],60,simulator=True);self.command('bootstatus',['xcrun','simctl','bootstatus',device,'-b'],300,simulator=True)
        save(OUT/'owned-runtime.json',known_runtime_metadata(owner))
        self.pressure_before=pressure_snapshot();save(OUT/'install-pressure-before.json',self.pressure_before)
        require(not self.uncertain and self.deadline-time.monotonic()>=255,'Collector/install/cleanup reserves do not fit')
        self.install_attempted=True
        try:
            code,raw=self.command('install-owned-app',['xcrun','simctl','install',device,str(binary.parent)],120,simulator=True,allow_failure=True)
            self.install_result={'returned_exit_code':code,'parent_dispatch':strict_json(OUT/'install-owned-app-dispatch-timing.json'),'outcome':'wrapper_passed' if code==0 else 'wrapper_failed','observation_or_simulator_uncertain':self.uncertain}
        finally:
            # Preserve any failed/unknown install before independently finalizing
            # logging. Finalization never starts another simulator command.
            if self.install_result is None:
                event=next((x for x in self.events if x['phase']=='install-owned-app'),None)
                self.install_result={'returned_exit_code':event['exit_code'] if event else None,'outcome':'failed_or_unknown','phase_evidence':event,'parent_dispatch':None}
                try:self.install_result['parent_dispatch']=strict_json(OUT/'install-owned-app-dispatch-timing.json')
                except (OSError,ValueError) as error:self.diagnostic_errors.append({'phase':'install-dispatch-retention','error':type(error).__name__})
            self.finalize_observation()
            native=self.observation.get('native_install') if type(self.observation) is dict else None
            self.install_result['native_install']=native
            if type(native) is dict and type(native.get('returncode')) is int:
                self.install_result['outcome']='passed' if native['returncode']==0 and native.get('within_deadline') is True else 'failed_or_late'
            else:self.install_result['outcome']='native_result_unknown'
            # The bounded summary in Actions survives a separate evidence-file
            # failure; observation failures never replace the install outcome.
            print('INSTALL_ONLY_OUTCOME',json.dumps(self.install_result,sort_keys=True),flush=True)
            try:
                save(OUT/'install-result.json',self.install_result);save(OUT/'install-pressure-after.json',pressure_snapshot())
            except (OSError,ValueError) as error:self.diagnostic_errors.append({'phase':'install-result-retention','error':type(error).__name__})
        # Intentional terminal boundary: no bootstrap, test-without-building,
        # Photos UI, permissions, signing, package or release qualification.

    def finalize_observation(self):
        if not getattr(self,'install_attempted',False):return
        try:
            receipt=strict_json(OBSERVATIONS/'install-wrapper-observation.json',65536)
            require(type(receipt) is dict and receipt.get('schema')=='Celluloid.InstallWrapperObservation.1' and receipt.get('source_sha')==self.source and receipt.get('run_id')==os.environ['GITHUB_RUN_ID'] and receipt.get('run_attempt')=='1','Stale/missing wrapper observation identity')
            self.observation=receipt
            if receipt.get('prohibit_further_simctl') is not False:self.uncertain=True
            logger=receipt.get('logger');sample=receipt.get('sample')
            for item,kind in [(logger,'device_log'),(sample,'install_sample')]:
                require(type(item) is dict and item.get('schema')=='Celluloid.InstallObserver.1' and item.get('kind')==kind and item.get('source_sha')==self.source and item.get('run_id')==os.environ['GITHUB_RUN_ID'] and item.get('run_attempt')=='1','Malformed/stale nested observer identity')
            require(logger.get('device')==self.device,'Observer device differs from exact owned install')
            require(logger_settled(logger),'Logger is not positively settled')
            require(type(sample) is dict and sample.get('uncertain') is False,'Sample is not settled')
        except (OSError,ValueError,KeyError,TypeError) as error:
            self.uncertain=True;self.diagnostic_errors.append({'phase':'observation-finalization','error':type(error).__name__})

def main():
    admission=admit();require(strict_json(ADMISSION)==admission,'Workflow source admission differs')
    os.chdir(ROOT);os.environ['TZ']='UTC'
    if hasattr(time,'tzset'):time.tzset()
    gate=InstallDiagnostic();gate.admission=admission;gate.install_result=None;gate.observation=None;gate.diagnostic_errors=[];error=None
    gate.cancel_signal=None;defer_cancellation(gate.cancel)
    try:gate.run()
    except BaseException as failure:error=type(failure).__name__+': '+str(failure)
    finally:
        try:gate.cleanup()
        except BaseException as cleanup_error:
            gate.uncertain=True;gate.diagnostic_errors.append({'phase':'owned-device-cleanup','error':type(cleanup_error).__name__})
        result={'schema':'Celluloid.InstallOnlyResult.1','diagnostic_only':True,'source_admission':admission,'install_result':gate.install_result,'diagnostic_errors':gate.diagnostic_errors,'error':error,'phases':gate.events,'simulator_uncertain':gate.uncertain,'pending_owned_device':gate.device,'work_budget_seconds':2280,'elapsed_seconds':time.monotonic()-gate.started,'bootstrap':'unrun','native_host_stages':{k:'unrun' for k in ['prepare','save-ui','saved','cancel-ui','cancelled']},'actual_host_qualified':False,'release_qualification':False}
        save(OUT/'install-only-result.json',result)
    return 0 if error is None and gate.install_result and gate.install_result['outcome']=='passed' and not gate.uncertain and gate.device is None else 1

if __name__=='__main__':
    if sys.argv[1:]==['--admit-only']:print(json.dumps(admit(),sort_keys=True))
    else:raise SystemExit(main())
