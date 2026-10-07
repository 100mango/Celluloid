"""Bounded cleanup of a process group created solely by the caller."""
import os,signal,time

def group_exists(group_id):
    try:
        os.killpg(group_id,0);return True
    except ProcessLookupError:return False
    except PermissionError:return True

def stop_group(process,grace=1):
    # The caller must use start_new_session=True. A reaped leader does not prove
    # its owned descendants exited. No daemon or other group is enumerated.
    if process.pid==os.getpgrp():raise ValueError('Refusing the caller process group')
    for stop_signal in (signal.SIGTERM,signal.SIGKILL):
        process.poll()
        if not group_exists(process.pid):return process.poll() is not None
        try:os.killpg(process.pid,stop_signal)
        except ProcessLookupError:pass
        deadline=time.monotonic()+grace
        while time.monotonic()<deadline:
            process.poll()
            if not group_exists(process.pid):return process.poll() is not None
            time.sleep(min(.025,max(0,deadline-time.monotonic())))
    return process.poll() is not None and not group_exists(process.pid)
