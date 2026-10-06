#!/usr/bin/env python3
"""Bounded commands in disposable native validation VMs; preserve the original failure."""
import os,signal,subprocess,sys,time,json,re,math
from datetime import datetime
from pathlib import Path
from original_ios_process_guard import OwnedCommand, active

def _capture_admission(timeout, enclosing_deadline, previous=None):
    """Bind a fixed capture phase to its actual row clock; never start a clock."""
    from original_ios_process_guard import staged_context, need
    from uikit_full_shipping_gate import clock_status, WORK_SECONDS, TAIL_PHASES, _read_file
    from mac_host_transport import load_json
    from validation_route import STORE_SCREENSHOTS
    need(type(timeout) in (int,float) and math.isfinite(timeout) and timeout>0,
         'Invalid capture command allowance')
    need(type(enclosing_deadline) in (int,float) and math.isfinite(enclosing_deadline) and enclosing_deadline>0,
         'Invalid capture enclosing deadline')
    context=staged_context()
    need(context is not None and context.get('validation_route')==STORE_SCREENSHOTS,
         'Capture deadline requires the actual Store capture route')
    root=Path(os.environ['RUNNER_TEMP'])
    need(root.is_dir() and not root.is_symlink(),'Invalid capture evidence root')
    clock=load_json(_read_file(root,'full-shipping-clock.json',10_000))
    clock_status(clock,context)
    deadlines={clock['started_monotonic']+seconds for seconds in {WORK_SECONDS,*[value[1] for value in TAIL_PHASES.values()]}}
    need(enclosing_deadline in deadlines,'Capture enclosing deadline is outside fixed source-bound phases')
    binding=(context,clock,str(root.resolve()))
    need(previous is None or binding==previous,'Capture deadline source/run/row/clock binding changed before dispatch')
    now=time.monotonic()
    if now+timeout+15+5>enclosing_deadline:
        raise TimeoutError('Capture command allowance plus cleanup/finalization does not fit; no dispatch')
    return binding,now


def run(args,timeout=180,check=True,log_name=None,echo=True,*,capture_deadline=None):
    args=list(map(str,args))
    capture_binding=None
    if capture_deadline is not None:
        capture_binding,_=_capture_admission(timeout,capture_deadline)
    owner=OwnedCommand(args[0],log_name or args[0],timeout)
    print('+ '+' '.join(args),flush=True)
    started=datetime.now().astimezone(); monotonic=time.monotonic()
    deadline=monotonic+timeout
    cleanup_deadline=None
    try:
        if capture_binding is not None:
            from original_ios_process_guard import need
            need(owner.enabled and owner.context==capture_binding[0],'Capture process owner differs from admitted route')
            _,admitted=_capture_admission(timeout,capture_deadline,capture_binding)
            # Ownership setup is already charged to the enclosing phase. The
            # actual spawn and every following operation consume these fixed
            # deadlines; no post-Popen reset grants fresh command time.
            deadline=admitted+timeout
            cleanup_deadline=min(deadline+15,capture_deadline-5)
        process=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
        owner.started(process)
    except BaseException as original:
        owner.failed(original)
        raise
    timed_out=False;cleanup=[];timeout_error=None
    def stop(sig):
        try:os.killpg(process.pid,sig)
        except ProcessLookupError:pass
        except PermissionError as error:cleanup.append(f'own process-group signal {sig} denied: {error}')
    def decoded(value):return value.decode('utf8','replace') if isinstance(value,bytes) else value or ''
    try:
        if owner.enabled:
            remaining=deadline-time.monotonic()
            if remaining<=0:raise subprocess.TimeoutExpired(args,timeout)
            stdout,stderr=process.communicate(timeout=remaining)
            if time.monotonic()>deadline:
                raise subprocess.TimeoutExpired(args,timeout,output=stdout,stderr=stderr)
        else:
            stdout,stderr=process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as original:
        timed_out=True;timeout_error=original
        if owner.enabled:
            owner.failed(original,timed_out=True)
            stdout,stderr=decoded(original.output),decoded(original.stderr)
            reaped=process.poll()
            if type(reaped) is int:
                owner.cleanup_result('child_reaped',reaped)
            else:
                for sig,seconds in [(signal.SIGTERM,10),(signal.SIGKILL,5)]:
                    name=signal.Signals(sig).name
                    if cleanup_deadline is not None and time.monotonic()>=cleanup_deadline:
                        owner.cleanup_result('bounded_cleanup_expired')
                        break
                    try:
                        os.killpg(process.pid,sig)
                        owner.cleanup_result('unconfirmed',signal_name=name,outcome='sent')
                    except ProcessLookupError:
                        owner.cleanup_result('unconfirmed',signal_name=name,outcome='absent')
                    except OSError as error:
                        denied=isinstance(error,PermissionError)
                        owner.cleanup_result('signal_denied' if denied else 'signal_error',signal_name=name,
                                             outcome='denied' if denied else 'error',error=error)
                        cleanup.append(f'own process-group {name} {"denied" if denied else "failed"}: {error}; termination unconfirmed')
                        break  # No other signal, wait, retry, or route after denial.
                    if cleanup_deadline is not None:
                        seconds=min(seconds,cleanup_deadline-time.monotonic())
                        if seconds<=0:
                            owner.cleanup_result('bounded_cleanup_expired')
                            break
                    try:
                        stdout,stderr=process.communicate(timeout=seconds)
                    except subprocess.TimeoutExpired as remaining:
                        stdout=decoded(remaining.output or stdout);stderr=decoded(remaining.stderr or stderr)
                        owner.cleanup_result('bounded_cleanup_expired')
                    except BaseException as error:
                        owner.cleanup_result('wait_failed')
                        cleanup.append(f'bounded child wait failed: {type(error).__name__}: {error}; termination unconfirmed')
                        break
                    else:
                        owner.cleanup_result('child_reaped',process.returncode)
                        break
            cleanup.append('row stopped after timeout; process-group cleanup is not confirmed; pure file evidence retention only')
        else:
            stop(signal.SIGTERM)
            try:stdout,stderr=process.communicate(timeout=10)
            except subprocess.TimeoutExpired as remaining:
                stop(signal.SIGKILL)
                try:stdout,stderr=process.communicate(timeout=5)
                except subprocess.TimeoutExpired as final:
                    stdout=decoded(final.output or remaining.output or original.output)
                    stderr=decoded(final.stderr or remaining.stderr or original.stderr)
                    cleanup.append('own process did not exit within bounded cleanup; VM/device cleanup remains required')
    except BaseException as original:
        owner.failed(original)
        raise
    else:
        owner.completed(process.returncode)
    stderr+='\n'+'\n'.join(cleanup) if cleanup else ''
    if echo:print(stdout,flush=True);print(stderr,file=sys.stderr,flush=True)
    if log_name:
        (Path(os.environ['RUNNER_TEMP'])/log_name).write_text(stdout+'\n'+stderr)
        finished=datetime.now().astimezone()
        timing={'command':args[0],'started':started.isoformat(),'finished':finished.isoformat(),
                'elapsed_seconds':round(time.monotonic()-monotonic,3),'timeout_seconds':timeout,
                'timed_out':timed_out,'return_code':process.returncode,'runner_timezone':str(started.tzinfo)}
        if capture_binding is not None:
            timing.update(capture_enclosing_deadline_monotonic=capture_deadline,
                          capture_command_deadline_monotonic=deadline,
                          capture_cleanup_deadline_monotonic=cleanup_deadline,
                          capture_finalization_seconds=5)
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
    if timed_out:
        error=TimeoutError(f'{args[0]} exceeded {timeout}s; partial output retained; cleanup: {cleanup or "signals completed"}')
        if owner.enabled:raise error from timeout_error
        raise error
    result=subprocess.CompletedProcess(args,process.returncode,stdout,stderr)
    if check and result.returncode:raise RuntimeError(f'{args[0]} exited {result.returncode}')
    return result


def optional_diagnostic(args, timeout=45):
    """A failed optional capture cannot suppress separately required app tests."""
    try:
        result=run(args,timeout=timeout,check=False)
        return {'exit_code':result.returncode,'succeeded':result.returncode==0}
    except (TimeoutError,RuntimeError,OSError) as error:
        scope='row stopped; pure file evidence retention only' if active() else 'optional diagnostic only; actual tests remain required'
        record={'succeeded':False,'error':str(error),'scope':scope}
        print('NATIVE_OPTIONAL_DIAGNOSTIC '+json.dumps(record),flush=True)
        return record
