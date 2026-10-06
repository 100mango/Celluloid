"""Real subprocess regressions for fixed diagnostics; no Apple/native process runs."""
import contextlib,io,unittest

FIXTURE_0 = r"""import json,os,pathlib,subprocess,sys,tempfile,time
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Scripts'))
from test_original_ios_process_guard import environment
from test_uikit_full_shipping_workflow import body
workflow=(ROOT/'.github/workflows/original-ios-release.yml').read_text()
functions=body(workflow,'Start the fixed row clock').split("<<'SHFUNCTIONS'\n",1)[1].split('\nSHFUNCTIONS',1)[0]
reports=[]
for phase,step,helper in [('evidence-screens','Export bounded synthetic UI evidence','export_permission_screenshot.py'),('diagnostics','Collect targeted failure diagnostics','collect_simulator_diagnostics.py')]:
 for scenario in ['negative','denial','ordinary65','late']:
  root=pathlib.Path(tempfile.mkdtemp(prefix='celluloid-review-v2-'+phase+'-'+scenario+'-'))
  (root/'Scripts').symlink_to(ROOT/'Scripts',target_is_directory=True);(root/'bin').mkdir()
  for name in ['TestResults-one.xcresult','TestResults-two.xcresult']:(root/name).mkdir()
  stub=root/'bin/xcrun'
  stub.write_text('#!'+sys.executable+'\nimport json,os,pathlib,signal,time\np=pathlib.Path(os.environ["RUNNER_TEMP"])/"native-stub-calls"\nn=len(p.read_text().splitlines()) if p.exists() else 0\nwith p.open("a") as f:f.write(json.dumps({"pid":os.getpid(),"pgid":os.getpgrp(),"args":__import__("sys").argv})+"\\n")\nscenario=os.environ["TEST_SCENARIO"]\nif scenario=="negative" and n==0:os.kill(os.getpid(),signal.SIGKILL)\nif scenario=="denial":time.sleep(.8)\nif scenario=="ordinary65" and n==0:raise SystemExit(65)\n')
  stub.chmod(0o755)
  env={**os.environ,**environment(root),'PATH':str(root/'bin')+os.pathsep+os.environ['PATH'],'PYTHONPATH':str(ROOT/'Scripts'),'TEST_SCENARIO':scenario}
  elapsed=0
  clock={'schema':'Celluloid.UIKitFullShippingClock.1',**{k:env[v] for k,v in [('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('run_attempt','GITHUB_RUN_ATTEMPT'),('row','CELLULOID_FULL_ROW')]},'started_monotonic':time.monotonic()-elapsed,'started_unix':time.time()-elapsed,'execution_budget_seconds':3360}
  (root/'full-shipping-clock.json').write_text(json.dumps(clock))
  wrapper=root/'wrapper.py'
  prelude='''import errno,json,os,pathlib,runpy,subprocess,time
root=pathlib.Path(os.environ['RUNNER_TEMP'])
pathlib.Path.home=classmethod(lambda cls:root)
'''
  if phase=='diagnostics':
   prelude+='''real_exists=pathlib.Path.exists
real_read_text=pathlib.Path.read_text
def exists(self):return True if str(self)=='/tmp/current-celluloid-simulator' else real_exists(self)
def read_text(self,*a,**kw):return 'synthetic-owned-device' if str(self)=='/tmp/current-celluloid-simulator' else real_read_text(self,*a,**kw)
pathlib.Path.exists=exists
pathlib.Path.read_text=read_text
'''
  if scenario=='late':prelude+='import uikit_full_shipping_gate as gate\ngate.admit_phase=lambda *a,**kw:74\n'
  if scenario=='denial':
   prelude+='''import native_process
real_communicate=subprocess.Popen.communicate
def shortened(self,*a,**kw):
    ready=root/'native-stub-calls';deadline=time.monotonic()+2
    while (not ready.exists() or ready.stat().st_size==0) and time.monotonic()<deadline:time.sleep(.005)
    if not ready.exists() or ready.stat().st_size==0:raise RuntimeError('Synthetic child did not announce readiness before fault injection')
    if kw.get('timeout') is not None:kw['timeout']=min(kw['timeout'],.03)
    return real_communicate(self,*a,**kw)
def denied(pgid,sig):
    path=root/'cleanup-attempts.jsonl'
    with path.open('a') as f:f.write(json.dumps({'pgid':pgid,'signal':int(sig),'failure':json.loads((root/'original-ios-process-failure.json').read_text()),'inflight':json.loads((root/'original-ios-process-inflight.json').read_text())})+'\\n')
    raise PermissionError(errno.EPERM,'Injected process-group signal denial')
subprocess.Popen.communicate=shortened
native_process.os.killpg=denied
'''
  wrapper.write_text(prelude+'runpy.run_path('+repr(str(ROOT/'Scripts'/helper))+',run_name="__main__")\n')
  script=body(workflow,step)
  # Preserve direct helper workflow shape; wrapper only injects the controlled fault/owned marker.
  if phase=='diagnostics' or scenario in ['denial','late']:script=script.replace('Scripts/'+helper,str(wrapper))
  result=subprocess.run(['bash','-c','set -euo pipefail\n'+functions+'\n'+script],cwd=root,env=env,capture_output=True,text=True,timeout=10)
  calls=root/'native-stub-calls';actual_calls=[json.loads(x) for x in calls.read_text().splitlines()] if calls.exists() else []
  failure=root/'original-ios-process-failure.json';inflight=root/'original-ios-process-inflight.json'
  sentinel=root/'later-device-sentinel'
  later=subprocess.run([sys.executable,str(ROOT/'Scripts/run_bounded.py'),'--seconds','5','--label','later-device-command',sys.executable,'-c','from pathlib import Path;Path('+repr(str(sentinel))+').touch()'],cwd=root,env=env,capture_output=True,text=True,timeout=10)
  report={'phase':phase,'scenario':scenario,'root':str(root),'helper_returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'native_calls':actual_calls,'failure':json.loads(failure.read_text()) if failure.exists() else None,'inflight_retained':inflight.exists(),'later_dispatched':sentinel.exists(),'later_returncode':later.returncode}
  attempts=root/'cleanup-attempts.jsonl';report['cleanup_attempts']=[json.loads(x) for x in attempts.read_text().splitlines()] if attempts.exists() else []
  if scenario in ['negative','denial']:
   assert len(actual_calls)==1,report
   assert result.returncode!=0 and not sentinel.exists() and report['failure'] is not None and report['inflight_retained'],report
   assert report['failure']['child_pid']==actual_calls[0]['pid'] and report['failure']['child_pgid']==actual_calls[0]['pgid'],report
   if scenario=='negative':assert report['failure']['failure_kind']=='unknown_termination',report
   else:
    assert len(report['cleanup_attempts'])==1 and report['failure']['failure_kind']=='timeout' and report['failure']['cleanup']['status']=='signal_denied',report
    assert report['cleanup_attempts'][0]['failure']['cleanup']['signals']==[],report
  elif scenario=='ordinary65':
   assert result.returncode==0 and len(actual_calls)==(2 if phase=='evidence-screens' else 1) and sentinel.exists() and report['failure'] is None,report
  else:
   # An admitted74-second diagnostic allowance cannot admit a45+15+15 command.
   assert not actual_calls and result.returncode!=0,report
  reports.append(report)
print(json.dumps({'source':str(ROOT),'workflow_shape':'actual direct helper invocation with synthetic clock','cases':reports},indent=2))
"""

FIXTURE_1 = r"""import json,os,pathlib,subprocess,sys,tempfile,time
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Scripts'))
from test_original_ios_process_guard import environment
reports=[]
for scenario in ['negative','denial','ordinary65']:
 root=pathlib.Path(tempfile.mkdtemp(prefix='celluloid-review-v2-host-'+scenario+'-'));(root/'bin').mkdir();(root/'Scripts').symlink_to(ROOT/'Scripts',target_is_directory=True)
 code='#!'+sys.executable+'\nimport json,os,pathlib,signal,sys,time\np=pathlib.Path(os.environ["RUNNER_TEMP"])/"stub-calls"\nname=pathlib.Path(sys.argv[0]).name\nwith p.open("a") as f:f.write(json.dumps({"name":name,"pid":os.getpid(),"pgid":os.getpgrp()})+"\\n")\nif name=="vm_stat":\n if os.environ["TEST_SCENARIO"]=="negative":os.kill(os.getpid(),signal.SIGKILL)\n if os.environ["TEST_SCENARIO"]=="denial":time.sleep(.8)\n if os.environ["TEST_SCENARIO"]=="ordinary65":raise SystemExit(65)\nif name=="xcrun":raise SystemExit(65)\n'
 for tool in ['vm_stat','memory_pressure','sysctl','df','ps','xcrun']:
  p=root/'bin'/tool;p.write_text(code);p.chmod(0o755)
 env={**os.environ,**environment(root),'PATH':str(root/'bin')+os.pathsep+os.environ['PATH'],'PYTHONPATH':str(ROOT/'Scripts'),'TEST_SCENARIO':scenario}
 (root/'full-shipping-clock.json').write_text(json.dumps({'schema':'Celluloid.UIKitFullShippingClock.1',**{k:env[v] for k,v in [('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('run_attempt','GITHUB_RUN_ATTEMPT'),('row','CELLULOID_FULL_ROW')]},'started_monotonic':time.monotonic(),'started_unix':time.time(),'execution_budget_seconds':3360}))
 wrapper=root/'wrapper.py';text='import runpy,sys\nsys.argv=["probe_photos_bootstrap.py","synthetic-device","--already-prepared"]\n'
 if scenario=='denial':
  text+='''import errno,json,os,pathlib,subprocess,native_process,time
root=pathlib.Path(os.environ['RUNNER_TEMP'])
actual=subprocess.Popen.communicate
def shorter(self,*a,**kw):
 ready=root/'stub-calls';deadline=time.monotonic()+2
 while (not ready.exists() or ready.stat().st_size==0) and time.monotonic()<deadline:time.sleep(.005)
 if not ready.exists() or ready.stat().st_size==0:raise RuntimeError('Synthetic child did not announce readiness before fault injection')
 if kw.get('timeout') is not None:kw['timeout']=min(kw['timeout'],.03)
 return actual(self,*a,**kw)
def denied(pgid,sig):
 with (root/'denial.jsonl').open('a') as f:f.write(json.dumps({'pgid':pgid,'signal':int(sig),'failure':json.loads((root/'original-ios-process-failure.json').read_text())})+'\\n')
 raise PermissionError(errno.EPERM,'Injected host cleanup denial')
subprocess.Popen.communicate=shorter
native_process.os.killpg=denied
'''
 text+='runpy.run_path('+repr(str(ROOT/'Scripts/probe_photos_bootstrap.py'))+',run_name="__main__")\n';wrapper.write_text(text)
 result=subprocess.run([sys.executable,str(wrapper)],cwd=root,env=env,capture_output=True,text=True,timeout=10)
 calls=[json.loads(x) for x in (root/'stub-calls').read_text().splitlines()];f=root/'original-ios-process-failure.json';failure=json.loads(f.read_text()) if f.exists() else None
 report={'scenario':scenario,'root':str(root),'returncode':result.returncode,'calls':calls,'failure':failure,'stdout':result.stdout,'stderr':result.stderr}
 if scenario in ['negative','denial']:
  assert len(calls)==1 and calls[0]['name']=='vm_stat' and failure is not None,report
  assert failure['child_pid']==calls[0]['pid'] and failure['child_pgid']==calls[0]['pgid'],report
  if scenario=='denial':assert len((root/'denial.jsonl').read_text().splitlines())==1,report
 else:assert calls[-1]['name']=='xcrun' and failure is None,report
 reports.append(report)
print(json.dumps(reports,indent=2))
"""

class DiagnosticOwnershipTests(unittest.TestCase):
    def replay(self,source):
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(source,'fixed-owned-subprocess-regression','exec',optimize=0),{'__file__':__file__,'__name__':'__main__'})
    def test_two_diagnostics_signal_denial_normal_nonzero_and_remaining_budget(self):self.replay(FIXTURE_0)
    def test_bootstrap_host_signal_denial_and_normal_nonzero(self):self.replay(FIXTURE_1)

if __name__=='__main__':unittest.main()
