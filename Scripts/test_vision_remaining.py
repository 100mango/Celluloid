#!/usr/bin/env python3
"""Focused Linux-only command doubles; these are not native product tests."""
import json
import os
import sys
import time
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from run_vision_remaining import Job, HOSTED, EDIT, PRIVACY, SELECTORS, verify_cases, pack, load_origin, environment, CLOCK, WORK_END, CLEANUP_END, BRANCH, WORKFLOW
from mac_archive_capture import capture, CaptureStopped
from vision_remaining_retention import ARCHIVE_RAW_CAP, retain_archive_output

RETENTION_FUNCTION_SHA='cbacc19d74cd92f01413bf69a5b5db668c79c58d996b3b590b068890aee426bd'
DEVICE='1141c503-1548-40a9-ac39-c1ff7f805b3b'
TYPE='com.apple.CoreSimulator.SimDeviceType.Apple-Vision-Pro-4K'
RUNTIME='com.apple.CoreSimulator.SimRuntime.xrOS-27-0'


def passed(cases):
    return '\n'.join("Test Case '-["+x.split('/')[0]+'.'+x.split('/')[1]+' '+x.split('/')[2]+"]' passed (1.0 seconds)." for x in cases)


class Fake:
    def __init__(self, bad=None, timeout=False, missing_seed=False):
        self.calls=[]; self.bad=bad; self.timeout=timeout; self.missing_seed=missing_seed
    def __call__(self,args,**kwargs):
        args=list(map(str,args))
        if args==['xcodebuild','-version']:phase='toolchain'
        elif args[0]=='swift':phase='icons'
        elif 'Scripts/verify_native_icon_inputs.py' in args:phase='icons-after' if any(p=='ui' for p,_,_ in self.calls) else 'icon-inputs'
        elif 'build-for-testing' in args:phase='build'
        elif 'archive' in args:phase='archive'
        elif 'Scripts/verify_native_release.py' in args:phase='package'
        elif 'test-without-building' in args:phase='hosted' if '-only-testing:'+HOSTED in args else 'ui'
        elif 'simctl' in args:phase=('types' if args[3]=='devicetypes' else args[3]) if args[2]=='list' else args[2]
        else:raise AssertionError('Unexpected command '+str(args))
        self.calls.append((phase,args,kwargs))
        if phase==self.bad:
            if self.timeout:raise TimeoutError('owned synthetic timeout')
            return subprocess.CompletedProcess(args,65,b'known error',b'')
        out=''
        if phase=='toolchain':out='Xcode 27.0\nBuild version 27A266a\n'
        if phase=='runtimes':out=json.dumps({'runtimes':[{'isAvailable':True,'identifier':RUNTIME,'supportedDeviceTypes':[{'identifier':TYPE}]}]})
        if phase=='types':out=json.dumps({'devicetypes':[{'identifier':TYPE}]})
        if phase=='create':out=DEVICE
        if phase=='hosted':out=passed([HOSTED])+('' if self.missing_seed else '\nVISION_REMAINING_SEED native writer/readback; fixture')
        if phase=='ui':out=passed([EDIT,PRIVACY])
        return subprocess.CompletedProcess(args,0,out.encode(),b'')


class RemainingTests(unittest.TestCase):
    def exercise(self, fake):
        with tempfile.TemporaryDirectory() as d:
            job=Job(Path(__file__).resolve().parents[1],d,'f'*40,execute=fake,clock=lambda:10.0)
            try:job.work()
            except (ValueError,TimeoutError,CaptureStopped):pass
            job.finish();return job.report
    def test_exact_three_cases_direct_xctest_launch(self):
        fake=Fake(); report=self.exercise(fake)
        self.assertTrue(report['complete'])
        tests=[args for _,args,_ in fake.calls if 'test-without-building' in args]
        self.assertEqual(len(tests),2)
        self.assertEqual([x[len('-only-testing:'):] for args in tests for x in args if x.startswith('-only-testing:')],list(SELECTORS))
        self.assertFalse(any(any(x in args for x in ['launch','install','get_app_container','terminate','screenshot']) for _,args,_ in fake.calls))
        self.assertEqual([p for p,_,_ in fake.calls][:5],['toolchain','icons','icon-inputs','build','archive'])
    def test_icon_materialization_and_validation_are_build_hard_dependencies(self):
        for failed in ['icons','icon-inputs']:
            with self.subTest(failed=failed):
                fake=Fake(bad=failed);report=self.exercise(fake)
                self.assertFalse(report['complete']);self.assertNotIn('build',[p for p,_,_ in fake.calls])
    def test_bad_package_does_not_create_device(self):
        fake=Fake(bad='package');self.exercise(fake)
        self.assertNotIn('create',[p for p,_,_ in fake.calls])
    def test_hosted_failure_or_missing_real_fixture_prevents_ui(self):
        for fake in [Fake(bad='hosted'),Fake(missing_seed=True)]:
            report=self.exercise(fake); self.assertFalse(report['complete'])
            self.assertNotIn('ui',[p for p,_,_ in fake.calls])
    def test_every_native_timeout_stops_all_subsequent_commands(self):
        for phase in ['toolchain','icons','icon-inputs','build','archive','package','runtimes','types','create','boot','bootstatus','hosted','ui','icons-after','shutdown','delete']:
            with self.subTest(phase=phase):
                fake=Fake(bad=phase,timeout=True);report=self.exercise(fake)
                self.assertTrue(report['device_uncertain']);self.assertFalse(report['complete'])
                self.assertEqual(fake.calls[-1][0],phase)
    def test_missing_failed_skipped_duplicate_or_additional_native_test_never_passes(self):
        logs=['',passed([EDIT]),passed([EDIT,PRIVACY]).replace('passed','failed',1),passed([EDIT,PRIVACY]).replace('passed','skipped',1),passed([EDIT,PRIVACY,PRIVACY]),passed([EDIT,PRIVACY,HOSTED])]
        for log in logs:
            with self.subTest(log=log):
                with self.assertRaises(ValueError):verify_cases(log,[EDIT,PRIVACY])
    def test_job_budget_refuses_new_command_without_resetting_deadline(self):
        with tempfile.TemporaryDirectory() as d:
            clock=[10.0];fake=Fake();job=Job('.',d,'f'*40,execute=fake,clock=lambda:clock[0]);deadline=job.deadline
            clock[0]=deadline-100
            with self.assertRaises(ValueError):job.call('ui',['xcodebuild'],900)
            self.assertEqual(job.deadline,deadline);self.assertEqual(fake.calls,[])
    def test_durable_uncertainty_prevents_same_directory_retry(self):
        with tempfile.TemporaryDirectory() as d:
            fake=Fake(bad='build',timeout=True);job=Job('.',d,'f'*40,execute=fake,clock=lambda:10.0)
            with self.assertRaises(TimeoutError):job.work()
            self.assertTrue((Path(d)/'vision-remaining-device-uncertain.json').exists())
            with self.assertRaises((ValueError,FileExistsError)):Job('.',d,'f'*40,execute=Fake(),clock=lambda:10.0)

    def test_real_historical_vision_stdout_format_and_failure(self):
        rows=json.loads((Path(__file__).parent/'fixtures/vision-historical-xctest.json').read_text())
        cases=['CelluloidVisionTests/NativeVisionTests/testNativeVisionDocumentImportRenderSaveReopenAndExport',
               'CelluloidVisionTests/NativeVisionTests/testNativeVisionExecutableAndSceneAreLive',
               'CelluloidVisionUITests/NativeVisionUITests/testNativeDocumentBrowserLaunchAndNewDocument',
               'CelluloidVisionUITests/NativeVisionUITests/testRealFilesImportBubbleAndPNGExport']
        self.assertEqual(len(verify_cases('\n'.join(rows[0]['lines']),cases)),4)
        with self.assertRaises(ValueError):verify_cases('\n'.join(rows[1]['lines']),cases)
        # Only the module-qualified spelling observed in the real Vision logs.
        with self.assertRaises(ValueError):verify_cases(passed([EDIT,PRIVACY]).replace('CelluloidVisionUITests.',''),[EDIT,PRIVACY])
    def test_real_capture_accepts_573kib_normal_output_with_bounded_retention(self):
        total=573*1024
        result=capture([sys.executable,'-c',f'import sys;sys.stdout.buffer.write(b"x"*{total})'],seconds=10,cap=ARCHIVE_RAW_CAP,cleanup_grace=10)
        self.assertEqual(result.returncode,0);self.assertEqual(len(result.stdout),total)
        row={};retain_archive_output(row,result.stdout,result.stderr,capture_complete=True)
        self.assertTrue(row['archive_log']['capture_complete']);self.assertTrue(row['archive_log']['truncated'])
        self.assertLessEqual(row['archive_log']['retained_utf8_bytes'],512*1024)
        self.assertEqual(row['archive_log']['full_sha256'],hashlib.sha256(result.stdout).hexdigest())
    def test_capture_stopped_prefix_retained_and_no_further_native_command(self):
        with tempfile.TemporaryDirectory() as d:
            error=CaptureStopped('duration-limit',True);error.stdout_prefix=b'earlier real output';error.stderr_capture=b'partial stderr'
            def stopped(*args,**kwargs):raise error
            job=Job('.',d,'f'*40,execute=stopped,clock=lambda:10.0)
            with self.assertRaises(CaptureStopped):job.call('ui',['xcodebuild'],900)
            job.device=DEVICE;job.finish()
            self.assertEqual(len(job.report['operations']),1);self.assertFalse(job.report['complete'])
            row=job.report['operations'][0];self.assertFalse(row['archive_log']['capture_complete'])
            self.assertIn('earlier real output',(Path(d)/'vision-remaining-evidence/ui.log').read_text())
    def test_old_origin_spends_work_time_but_preserves_cleanup_and_failure_pack(self):
        with tempfile.TemporaryDirectory() as d:
            fake=Fake();clock=[10+WORK_END-5]
            job=Job('.',d,'f'*40,execute=fake,clock=lambda:clock[0],started=10)
            job.device=DEVICE
            with self.assertRaises(ValueError):job.call('ui',['xcodebuild'],900)
            job.finish()
            self.assertEqual([p for p,_,_ in fake.calls],['shutdown','delete'])
            manifest=pack(d,{'synthetic':True},10,clock[0])
            self.assertTrue(any(x['name']=='report.json' for x in manifest['members']))
            self.assertFalse(json.loads((Path(d)/'vision-remaining-evidence/report.json').read_text())['complete'])
    def test_bound_origin_rejects_reset_or_other_run(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/CLOCK;path.write_text(json.dumps({'started_monotonic':10,'binding':{'run':'one'}}))
            self.assertEqual(load_origin(d,{'run':'one'},20),10)
            with self.assertRaises(ValueError):load_origin(d,{'run':'two'},20)
            with self.assertRaises(ValueError):load_origin(d,{'run':'one'},9)
    def test_fixed_single_push_workflow_has_original_clock_and_failure_retention(self):
        path=Path(__file__).resolve().parents[1]/WORKFLOW;text=path.read_text()
        self.assertIn('timeout-minutes: 60',text);self.assertNotIn('workflow_dispatch',text);self.assertNotIn('strategy:',text)
        self.assertLess(text.index('started_monotonic'),text.index('actions/checkout@'))
        self.assertIn('if: always()',text);self.assertIn('--pack',text);self.assertIn('--finish-upload',text)
        self.assertNotIn('summary',text);self.assertNotIn('xcrun',text)

    def test_workflow_clock_executes_once_and_matches_runtime_binding(self):
        import yaml
        workflow=yaml.safe_load((Path(__file__).resolve().parents[1]/WORKFLOW).read_text())
        run=workflow['jobs']['vision']['steps'][0]['run']
        identity={'GITHUB_REPOSITORY':'100mango/Celluloid','GITHUB_REF':BRANCH,
                  'GITHUB_WORKFLOW_REF':'100mango/Celluloid/'+WORKFLOW+'@'+BRANCH,
                  'GITHUB_RUN_ATTEMPT':'1','GITHUB_JOB':'vision','GITHUB_EVENT_NAME':'push',
                  'DEVELOPER_DIR':'/Applications/Xcode_27.app/Contents/Developer',
                  'GITHUB_SHA':'f'*40,'GITHUB_WORKFLOW_SHA':'f'*40,'GITHUB_RUN_ID':'1234'}
        with tempfile.TemporaryDirectory() as d:
            env=dict(os.environ,**identity,RUNNER_TEMP=d)
            first=subprocess.run(['bash','-c',run],env=env,capture_output=True,text=True)
            self.assertEqual(first.returncode,0,first.stderr)
            before=(Path(d)/CLOCK).read_bytes()
            started=load_origin(d,environment(identity),time.monotonic())
            self.assertLessEqual(started,time.monotonic())
            second=subprocess.run(['bash','-c',run],env=env,capture_output=True,text=True)
            self.assertNotEqual(second.returncode,0);self.assertEqual((Path(d)/CLOCK).read_bytes(),before)
    def test_retention_helper_is_exact_mature_function(self):
        # The expected function digest pins the adopted helper, not a mutable remote.
        from vision_remaining_retention import retain_archive_output
        import inspect
        self.assertEqual(hashlib.sha256(inspect.getsource(retain_archive_output).encode()).hexdigest(),RETENTION_FUNCTION_SHA)

    def test_complete_capture_parses_either_native_output_stream(self):
        with tempfile.TemporaryDirectory() as d:
            def stderr_result(argv,**kwargs):return subprocess.CompletedProcess(argv,0,b'',passed([EDIT,PRIVACY]).encode())
            job=Job('.',d,'f'*40,execute=stderr_result,clock=lambda:10)
            value=job.call('ui',['xcodebuild'],900)
            self.assertEqual(len(verify_cases(value,[EDIT,PRIVACY])),2)
    def test_late_pack_retains_existing_files_without_clock_reset(self):
        with tempfile.TemporaryDirectory() as d:
            fake=Fake(bad='hosted');job=Job('.',d,'f'*40,execute=fake,clock=lambda:10)
            try:job.work()
            except ValueError:pass
            job.finish();before=(Path(d)/'vision-remaining-evidence/report.json').read_bytes()
            with self.assertRaises(ValueError):pack(d,{},10,4000)
            self.assertEqual((Path(d)/'vision-remaining-evidence/report.json').read_bytes(),before)

    def test_failed_native_invocation_keeps_actual_completed_cases(self):
        with tempfile.TemporaryDirectory() as d:
            def failed(argv,**kwargs):return subprocess.CompletedProcess(argv,65,passed([PRIVACY]).encode(),b'error: editing failed')
            job=Job('.',d,'f'*40,execute=failed,clock=lambda:10)
            with self.assertRaises(ValueError):job.call('ui',['xcodebuild'],900)
            job.finish();row=job.report['operations'][0]
            self.assertEqual(row['observed_test_terminals']['records'][0]['method'],PRIVACY.split('/')[-1])
            self.assertTrue(row['observed_test_terminals']['capture_complete']);self.assertFalse(job.report['complete'])
    def test_signalled_child_sets_device_barrier_even_with_closed_capture(self):
        with tempfile.TemporaryDirectory() as d:
            def signalled(argv,**kwargs):return subprocess.CompletedProcess(argv,-9,b'prefix',b'')
            job=Job('.',d,'f'*40,execute=signalled,clock=lambda:10)
            with self.assertRaises(TimeoutError):job.call('ui',['xcodebuild'],900)
            job.device=DEVICE;job.finish()
            self.assertTrue(job.report['device_uncertain']);self.assertEqual(len(job.report['operations']),1)

if __name__=='__main__':unittest.main()
