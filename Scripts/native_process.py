#!/usr/bin/env python3
"""Bounded commands in disposable native validation VMs; preserve the original failure."""
import os,signal,subprocess,sys
from pathlib import Path

def run(args,timeout=180,check=True,log_name=None,echo=True):
    args=list(map(str,args));print('+ '+' '.join(args),flush=True)
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
    if log_name:(Path(os.environ['RUNNER_TEMP'])/log_name).write_text(stdout+'\n'+stderr)
    if timed_out:raise TimeoutError(f'{args[0]} exceeded {timeout}s; partial output retained; cleanup: {cleanup or "signals completed"}')
    result=subprocess.CompletedProcess(args,process.returncode,stdout,stderr)
    if check and result.returncode:raise RuntimeError(f'{args[0]} exited {result.returncode}')
    return result
