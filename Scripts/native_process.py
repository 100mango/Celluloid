#!/usr/bin/env python3
"""Bounded commands in disposable native validation VMs; preserve the original failure."""
import os,signal,subprocess,sys,time,json,re
from datetime import datetime
from pathlib import Path

def run(args,timeout=180,check=True,log_name=None,echo=True):
    args=list(map(str,args));print('+ '+' '.join(args),flush=True)
    started=datetime.now().astimezone(); monotonic=time.monotonic()
    process=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
    timed_out=False;cleanup=[]
    def stop(sig):
        try:os.killpg(process.pid,sig)
        except ProcessLookupError:pass
        except PermissionError as error:cleanup.append(f'own process-group signal {sig} denied: {error}')
    def decoded(value):return value.decode('utf8','replace') if isinstance(value,bytes) else value or ''
    try:stdout,stderr=process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as original:
        timed_out=True;stop(signal.SIGTERM)
        try:stdout,stderr=process.communicate(timeout=10)
        except subprocess.TimeoutExpired as remaining:
            stop(signal.SIGKILL)
            try:stdout,stderr=process.communicate(timeout=5)
            except subprocess.TimeoutExpired as final:
                stdout=decoded(final.output or remaining.output or original.output)
                stderr=decoded(final.stderr or remaining.stderr or original.stderr)
                cleanup.append('own process did not exit within bounded cleanup; VM/device cleanup remains required')
    stderr+='\n'+'\n'.join(cleanup) if cleanup else ''
    if echo:print(stdout,flush=True);print(stderr,file=sys.stderr,flush=True)
    if log_name:
        (Path(os.environ['RUNNER_TEMP'])/log_name).write_text(stdout+'\n'+stderr)
        finished=datetime.now().astimezone()
        timing={'command':args[0],'started':started.isoformat(),'finished':finished.isoformat(),
                'elapsed_seconds':round(time.monotonic()-monotonic,3),'timeout_seconds':timeout,
                'timed_out':timed_out,'return_code':process.returncode,'runner_timezone':str(started.tzinfo)}
        suites=re.findall(r"Test Suite 'All tests' (started|passed|failed) at ([0-9-]+ [0-9:.]+)\.",stdout)
        timing['xctest_suite_events']=[{'event':kind,'local_timestamp':value} for kind,value in suites[:20]]
        try:
            starts=[datetime.fromisoformat(value).replace(tzinfo=started.tzinfo) for kind,value in suites if kind=='started']
            ends=[datetime.fromisoformat(value).replace(tzinfo=started.tzinfo) for kind,value in suites if kind in ['passed','failed']]
            if starts:timing['command_to_first_suite_seconds']=round((min(starts)-started).total_seconds(),3)
            if starts and ends:timing['observed_suite_span_seconds']=round((max(ends)-min(starts)).total_seconds(),3)
            if ends:timing['last_suite_to_command_end_seconds']=round((finished-max(ends)).total_seconds(),3)
        except ValueError:timing['suite_timestamp_parse']='unavailable; raw events retained'
        (Path(os.environ['RUNNER_TEMP'])/(log_name+'.timing.json')).write_text(json.dumps(timing,indent=2)+'\n')
        print('NATIVE_PROCESS_TIMING '+json.dumps(timing),flush=True)
    if timed_out:raise TimeoutError(f'{args[0]} exceeded {timeout}s; partial output retained; cleanup: {cleanup or "signals completed"}')
    result=subprocess.CompletedProcess(args,process.returncode,stdout,stderr)
    if check and result.returncode:raise RuntimeError(f'{args[0]} exited {result.returncode}')
    return result


def optional_diagnostic(args, timeout=45):
    """A failed optional capture cannot suppress separately required app tests."""
    try:
        result=run(args,timeout=timeout,check=False)
        return {'exit_code':result.returncode,'succeeded':result.returncode==0}
    except (TimeoutError,RuntimeError,OSError) as error:
        record={'succeeded':False,'error':str(error),'scope':'optional diagnostic only; actual tests remain required'}
        print('NATIVE_OPTIONAL_DIAGNOSTIC '+json.dumps(record),flush=True)
        return record
