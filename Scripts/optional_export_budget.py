"""One finite aggregate window for optional Mac evidence exporters only."""
import json,math,subprocess,time
from pathlib import Path
from native_process import run as run_process

class OptionalExportError(RuntimeError):pass

class OptionalExportBudget:
    def __init__(self,clock_path=None,source=None):
        self.started=time.monotonic();self.deadline=self.started+180;self.events=[];self.cleanup_unconfirmed=False
        self.clock_status='no job clock available; local aggregate cap only'
        if clock_path is not None and Path(clock_path).exists():
            try:
                from mac_photos_host_gate import read_receipt,validate_clock
                clock=read_receipt(clock_path);job_deadline=validate_clock(clock,source)
                self.deadline=min(self.deadline,job_deadline-120)
                self.clock_status='source-bound job clock; two minutes retained for final proof/upload'
            except Exception as error:
                self.deadline=self.started
                self.clock_status='invalid clock; optional exporters withheld: '+type(error).__name__+': '+str(error)
    def run(self,args,timeout):
        if self.cleanup_unconfirmed:raise OptionalExportError('Earlier optional exporter cleanup unconfirmed; later exporters withheld')
        remaining=self.deadline-time.monotonic()
        if remaining<=15:
            self.events.append({'target':str(args[-1]),'state':'skipped aggregate budget','remaining_seconds':remaining})
            raise OptionalExportError('Optional exporter aggregate3min/job-tail budget exhausted')
        if type(timeout) not in (int,float) or not math.isfinite(timeout) or timeout<=0:raise ValueError('Invalid exporter timeout')
        limit=min(timeout,remaining-15) # native_process retains at most15s for owned process-group cleanup.
        event={'target':str(args[-1]),'timeout_seconds':limit};self.events.append(event)
        try:
            result=run_process(args,timeout=limit,check=False,echo=False)
            event.update(state='returned',exit_code=result.returncode)
            # Keep collector's existing byte-oriented interfaces unchanged.
            return subprocess.CompletedProcess(result.args,result.returncode,result.stdout.encode(),result.stderr.encode())
        except (TimeoutError,RuntimeError,OSError) as error:
            self.cleanup_unconfirmed=True
            event.update(state='export failed; cleanup unconfirmed',error=(type(error).__name__+': '+str(error))[:2000])
            raise OptionalExportError(event['error']) from error
    def report(self):
        return {'aggregate_limit_seconds':180,'process_cleanup_reserve_seconds':15,'final_proof_upload_reserve_seconds':120,
                'clock_status':self.clock_status,'elapsed_seconds':time.monotonic()-self.started,'events':self.events,
                'scope':'Optional export budget only. Missing or unconfirmed evidence never grants acceptance.'}
