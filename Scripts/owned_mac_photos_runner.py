"""One owned process group; original deadline, bounded cleanup and denial stop.

Derived narrowly from runtime-v2's reviewed runner. SIGINT/SIGTERM/caller
KeyboardInterrupt are failures, never permission for detached native work.
Temporary signal handlers are restored after this one command.
"""
import os,signal,subprocess,sys,time
from pathlib import Path

class OwnedCommandCancelled(RuntimeError):pass

def run(args,timeout=180,check=True,log_name=None,echo=True):
    args=list(map(str,args));started=time.monotonic();deadline=started+timeout
    process=None;stdout=stderr='';failure=None;cleanup=[];pending=None;cleaning=False;handlers={}
    def decoded(value):return value.decode('utf8','replace') if isinstance(value,bytes) else value or ''
    def cancelled(number,frame):
        nonlocal pending
        pending=number
        # During Popen keep the cancellation pending until its returned owned
        # process handle exists. Do not abandon an untracked start_new_session.
        # During cleanup, a second cancellation cannot reset its deadline.
        if process is not None and not cleaning:raise OwnedCommandCancelled('owned command cancelled by '+signal.Signals(number).name)
    def stop_owned():
        nonlocal stdout,stderr,cleaning
        cleaning=True;limit=min(deadline+15,time.monotonic()+15)
        if process is None:
            cleanup.append('no returned owned process handle; cleanup unconfirmed');return
        try:alive=process.poll() is None
        except OSError as error:
            cleanup.append('owned poll denied/failed: '+str(error)+'; no signal or wait');return
        if not alive:return
        for sig,seconds in [(signal.SIGTERM,10),(signal.SIGKILL,5)]:
            remaining=min(seconds,limit-time.monotonic())
            if remaining<=0:cleanup.append('original cleanup deadline exhausted');break
            try:os.killpg(process.pid,sig)
            except ProcessLookupError:
                cleanup.append('owned process group absent; cleanup unconfirmed');break
            except OSError as error:
                cleanup.append('owned '+signal.Signals(sig).name+' denied/failed: '+str(error)+'; no further signal or wait');break
            remaining=min(seconds,limit-time.monotonic())
            if remaining<=0:cleanup.append('original cleanup deadline exhausted');break
            try:stdout,stderr=process.communicate(timeout=remaining)
            except subprocess.TimeoutExpired as error:stdout,stderr=decoded(error.output or stdout),decoded(error.stderr or stderr)
            except OSError as error:
                cleanup.append('owned process read denied/failed: '+str(error)+'; no further signal or wait');break
            else:break
    try:
        # All admitted commands are invoked on the driver's main thread. Failure
        # to install a handler stops before Popen; there is no alternate runner.
        for number in (signal.SIGINT,signal.SIGTERM):
            handlers[number]=signal.getsignal(number);signal.signal(number,cancelled)
        process=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
        if pending is not None:raise OwnedCommandCancelled('owned command cancelled during launch by '+signal.Signals(pending).name)
        remaining=deadline-time.monotonic()
        if remaining<=0:raise subprocess.TimeoutExpired(args,timeout)
        stdout,stderr=process.communicate(timeout=remaining)
        if time.monotonic()>deadline:raise subprocess.TimeoutExpired(args,timeout,output=stdout,stderr=stderr)
    except subprocess.TimeoutExpired as original:
        stdout,stderr=decoded(original.output or stdout),decoded(original.stderr or stderr);stop_owned()
        cleanup.append('native command timed out; cleanup unconfirmed; pure file retention only')
        failure=TimeoutError(str(args[0])+' exceeded '+str(timeout)+'s; '+'; '.join(cleanup))
    except (OwnedCommandCancelled,KeyboardInterrupt) as original:
        stop_owned();cleanup.append('native command cancelled; cleanup unconfirmed; pure file retention only')
        failure=OwnedCommandCancelled(str(original)+'; '+'; '.join(cleanup));failure.cleanup_unconfirmed=True
    except OSError as error:
        # A permission/read failure is not permission to signal, wait, retry or relocate.
        error.cleanup_unconfirmed=True;failure=error
        cleanup.append('owned process read/start denied/failed; no further signal or wait; cleanup unconfirmed')
    finally:
        for number,previous in handlers.items():signal.signal(number,previous)
    stderr+='\n'+'\n'.join(cleanup) if cleanup else ''
    if log_name:(Path(os.environ['RUNNER_TEMP'])/log_name).write_text(stdout+'\n'+stderr)
    if echo:print(stdout,flush=True);print(stderr,file=sys.stderr,flush=True)
    if failure is not None:raise failure
    result=subprocess.CompletedProcess(args,process.returncode,stdout,stderr)
    if check and result.returncode:raise RuntimeError(str(args[0])+' exited '+str(result.returncode))
    return result
