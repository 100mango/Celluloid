#!/usr/bin/env python3
"""Host-only contract/negative tests. No simulator or Apple tool invocation."""
import copy
import errno
import io
import json
import os
import plistlib
import select
import signal
import time
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import run_vision_store_capture as store
from vision_store_stream import capture as stream_capture
from mac_archive_capture import CaptureStopped

ROOT = Path(__file__).resolve().parents[1]
DEVICE = '11111111-1111-4111-8111-111111111111'
CONTAINER = '22222222-2222-4222-8222-222222222222'
OTHER = '33333333-3333-4333-8333-333333333333'
REQUEST = '44444444-4444-4444-8444-444444444444'
IMAGE = {'format': 'JPEG', 'mode': 'RGB', 'width': 3840, 'height': 2160, 'alpha': False, 'decoded': True}
BINDING = {'GITHUB_SHA': 'a'*40}

def write_container_metadata(path, bundle=store.APP_ID, metadata_uuid=None):
    (path/store.METADATA_NAME).write_bytes(plistlib.dumps({
        'MCMMetadataIdentifier': bundle, 'MCMMetadataUUID': path.name if metadata_uuid is None else metadata_uuid}, fmt=plistlib.FMT_BINARY))
    return path

def request():
    return {'schema': 'Celluloid.StoreRequest.1', 'id': REQUEST, 'bundle_identifier': store.APP_ID,
        'document': store.FIXTURE_NAME, 'locale': 'en_US', 'language': 'en', 'sample_width': 120,
        'sample_height': 80, 'preview_count': 1, 'controls': ['editor.import-files', 'editor.add-bubble', 'editor.export'],
        'ready': True, 'alerts': 0, 'sheets': 0, 'keyboards': 0, 'progress': 0}

class ContractTests(unittest.TestCase):
    def test_default_is_host_only_and_disabled(self):
        with mock.patch.object(sys, 'argv', ['runner']), mock.patch.object(store, 'capture', side_effect=AssertionError('native forbidden')), mock.patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(store.main(), 0)
            self.assertFalse(json.loads(output.getvalue())['native_execution_enabled'])
    def test_admission_disabled(self):
        disabled = {**json.loads((ROOT/'Scripts/vision_store_admission.json').read_text()), 'enabled': False}
        with mock.patch.object(store, 'json_file', return_value=disabled), self.assertRaisesRegex(ValueError, 'disabled'):
            store.admission(ROOT, {'CELLULOID_STORE_ROOT_GO_SHA': 'a'*40}, BINDING)
    def test_enabled_admission_requires_exact_evidence_and_go(self):
        evidence = {'editor_open_verified': True, 'run_id': 1, 'artifact_id': 2, 'source_sha': store.EDITOR_OPEN_SOURCE, 'artifact_sha256': 'b'*64}
        row = {'schema': 'Celluloid.StoreAdmission.1', 'enabled': True, 'editor_open_evidence': evidence}
        with mock.patch.object(store, 'json_file', return_value=row):
            self.assertEqual(store.admission(ROOT, {'CELLULOID_STORE_ROOT_GO_SHA': 'a'*40}, BINDING), row)
            with self.assertRaises(ValueError): store.admission(ROOT, {}, BINDING)
        row['editor_open_evidence'] = {**evidence, 'source_sha': 'c'*40}
        with mock.patch.object(store, 'json_file', return_value=row), self.assertRaises(ValueError):
            store.admission(ROOT, {'CELLULOID_STORE_ROOT_GO_SHA': 'a'*40}, BINDING)
    def test_wrong_cohort_rejected(self):
        with self.assertRaises(ValueError): store.environment({})
    def test_update_push_cohort_rejects_manual_or_repeated_attempt(self):
        env = {'GITHUB_REPOSITORY': '100mango/Celluloid', 'GITHUB_REF': store.BRANCH,
            'GITHUB_WORKFLOW_REF': '100mango/Celluloid/'+store.WORKFLOW+'@'+store.BRANCH,
            'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_JOB': 'vision', 'GITHUB_EVENT_NAME': 'push',
            'DEVELOPER_DIR': '/Applications/Xcode_27.app/Contents/Developer',
            'GITHUB_SHA': 'a'*40, 'GITHUB_WORKFLOW_SHA': 'a'*40, 'GITHUB_RUN_ID': '123'}
        self.assertEqual(store.environment(env), env)
        for key, value in [('GITHUB_EVENT_NAME', 'workflow_dispatch'), ('GITHUB_RUN_ATTEMPT', '2'),
                           ('GITHUB_REF', 'refs/heads/codex/vision-edit-final')]:
            with self.subTest(key=key), self.assertRaises(ValueError): store.environment({**env, key: value})
    def test_image_contract(self):
        self.assertEqual(store.validate_image(IMAGE), IMAGE)
        for key, value in [('width', 1280), ('height', 720), ('alpha', True), ('mode', 'RGBA'), ('mode', 'CMYK'), ('decoded', False), ('format', 'PNG')]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError): store.validate_image({**IMAGE, key: value})
    def test_ui_contract(self):
        store.validate_request(request(), REQUEST)
        for key, value in [('ready', False), ('bundle_identifier', 'com.mango.touchColor'), ('document', 'Personal.celluloid'), ('preview_count', 0), ('preview_count', True), ('alerts', 1), ('sheets', 1), ('keyboards', 1), ('progress', 1), ('locale', 'zh_CN')]:
            with self.subTest(key=key), self.assertRaises(ValueError): store.validate_request({**request(), key: value}, REQUEST)
    def test_split_marker(self):
        seen = []; parser = store.RequestLines(seen.append)
        marker = (store.REQUEST_PREFIX+REQUEST+'\n').encode()
        for byte in marker: parser('stdout', bytes([byte]))
        parser.finish(); self.assertEqual(seen, [REQUEST])
    def test_duplicate_marker_no_second_callback(self):
        seen = []; parser = store.RequestLines(seen.append); marker = (store.REQUEST_PREFIX+REQUEST+'\n').encode()
        parser('stdout', marker)
        with self.assertRaises(ValueError): parser('stderr', marker)
        self.assertEqual(seen, [REQUEST])
    def test_missing_malformed_and_unbounded_markers(self):
        with self.assertRaises(ValueError): store.RequestLines(lambda _: None).finish()
        for payload in [(store.REQUEST_PREFIX+'not-a-uuid\n').encode(), b'x'*131073]:
            with self.assertRaises(ValueError): store.RequestLines(lambda _: None)('stdout', payload)
    def test_unterminated_marker_never_calls_after_stream_exit(self):
        seen = []; parser = store.RequestLines(seen.append)
        parser('stdout', (store.REQUEST_PREFIX+REQUEST).encode())
        with self.assertRaisesRegex(ValueError, 'Unterminated'): parser.finish()
        self.assertEqual(seen, [])
    def test_stderr_marker_cannot_trigger_checkpoint(self):
        seen = []; parser = store.RequestLines(seen.append)
        with self.assertRaisesRegex(ValueError, 'stdout'): parser('stderr', (store.REQUEST_PREFIX+REQUEST+'\n').encode())
        self.assertEqual(seen, [])
    def test_utf8_marker_requires_exact_line(self):
        with self.assertRaises(ValueError): store.RequestLines(lambda _: None)('stdout', ('foreign '+store.REQUEST_PREFIX+REQUEST+'\n').encode())
    def test_exact_upload_budget(self):
        self.assertLessEqual(sum(store.EVIDENCE_FILES.values())+sum(store.DIAGNOSTIC_FILES.values()), store.EVIDENCE_CAP)
        workflow = (ROOT/store.WORKFLOW).read_text()
        enabled = json.loads((ROOT/'Scripts/vision_store_admission.json').read_text())['enabled']
        self.assertIs(type(enabled), bool)
        self.assertTrue(enabled)
        self.assertIn('branches: [codex/vision-store-single]', workflow)
        self.assertIn("github.event_name == 'push' && github.ref == 'refs/heads/codex/vision-store-single' && github.event.created == false", workflow)
        self.assertIn("github.event.before == '"+store.BASE+"' && github.run_attempt == 1", workflow)
        self.assertIn('github.event.deleted == false', workflow)
        self.assertNotIn('workflow_dispatch:', workflow)
        self.assertIn('CELLULOID_STORE_ROOT_GO_SHA: ${{ github.sha }}', workflow)
        paths = {line.strip().split('/')[-1] for line in workflow.splitlines() if '${{ runner.temp }}/vision-store-evidence/' in line}
        self.assertEqual(paths, set(store.EVIDENCE_FILES))
        self.assertNotIn('*.jpeg', workflow); self.assertNotIn('.xcresult', workflow)
    def test_workflow_diagnostics_independent_and_budgets_reserved(self):
        import re
        workflow = (ROOT/store.WORKFLOW).read_text()
        blocks = workflow.split('      - name: ')[1:]
        budgets = [int(re.search(r'timeout-minutes: (\d+)', block)[1]) for block in blocks]
        self.assertIn('    timeout-minutes: 42', workflow)
        # Per-step maxima need not all be consumed; job42 and original clock bind.
        self.assertEqual(budgets, [1,2,32,4,2,2,1])
        self.assertEqual(budgets[3]*60, store.PACK_END-store.CLEANUP_END)
        self.assertIn('if: always()\n', blocks[-1])
        self.assertIn("steps.pack.outcome == 'success'", blocks[4])
        paths = {line.rsplit('/',1)[-1] for line in blocks[-1].splitlines() if '${{ runner.temp }}/' in line}
        self.assertEqual(paths, set(store.DIAGNOSTIC_FILES))
        self.assertNotIn('jpeg', blocks[-1])
        self.assertLess(store.CLEANUP_END, store.PACK_END)
        self.assertEqual(store.FINISH_END-store.PACK_END, 240)
        self.assertLessEqual(store.FINISH_END+60, 42*60)
    def test_install_only_cap_and_existing_per_command_admission(self):
        import ast
        source = ast.parse((ROOT/'Scripts/run_vision_store_capture.py').read_text())
        job = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'Job')
        work = next(n for n in job.body if isinstance(n, ast.FunctionDef) and n.name == 'work')
        calls = [n for n in ast.walk(work) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
        phases = {n.args[0].value: n.args[2].value for n in calls if n.func.attr == 'call' and len(n.args) >= 3}
        self.assertEqual(phases['install'], 360)
        self.assertEqual({k: phases[k] for k in ('build','boot','ui')}, {'build':600,'boot':45,'ui':1200})
        self.assertEqual(phases['bootstatus'],240)
        # Preserve the prior host-side fixture-write guard; add no aggregate max-cap gate.
        guards = [n for n in calls if n.func.attr == 'check_active']
        self.assertEqual(len(guards), 1); self.assertEqual(guards[0].args, [])
    def test_only_capture_selector_gets_matching_xctest_case_maximum(self):
        base = store.test_command(Path('/mock'), DEVICE, [store.SELECTOR], 'VisionStoreSingle')
        command = store.capture_test_command(Path('/mock'), DEVICE)
        self.assertEqual(command, base[:-1]+['-test-timeouts-enabled','YES',
            '-maximum-test-execution-time-allowance','1200']+base[-1:])
        self.assertEqual([x for x in command if x.startswith('-only-testing:')], ['-only-testing:'+store.SELECTOR])
        self.assertNotIn('-retry-tests-on-failure', command)
        self.assertNotIn('-test-timeouts-enabled', base)
        ui = (ROOT/'Platforms/VisionUITests/NativeVisionUITests.swift').read_text()
        self.assertEqual(ui.count('executionTimeAllowance = 1200'), 1)
        self.assertLess(344+620, 1200)
        maximum = int(command[command.index('-maximum-test-execution-time-allowance')+1])
        self.assertEqual(maximum, 1200)
    def test_swift_case_has_no_edit_or_window_screenshot(self):
        text = (ROOT/'Platforms/VisionUITests/NativeVisionUITests.swift').read_text()
        case = text.split('func testStoreSingleHeldEditorCapture()', 1)[1].split('func testSeededDocument', 1)[0]
        for forbidden in ('typeText(', '.screenshot()', 'undo.tap', 'redo.tap', 'editor.export"].tap', 'add-bubble"].tap'):
            self.assertNotIn(forbidden, case)
        self.assertIn('openRemainingDocument(in: app)', case)
        self.assertIn('timeout: 620', case); self.assertIn('executionTimeAllowance = 1200', case); self.assertIn('Edited photo preview', case)
    def test_stream_preserves_owned_cleanup_with_guarded_observer(self):
        base = (ROOT/'Scripts/mac_archive_capture.py').read_text()
        current = (ROOT/'Scripts/vision_store_stream.py').read_text()
        current = current[current.index('import os'):]
        base = base[base.index('import os'):]
        start = base.index('class CaptureStopped('); end = base.index('def require(', start)
        base = base[:start]+'from mac_archive_capture import CaptureStopped\n\n'+base[end:]
        current = current.replace(', observer=None, control=None):', '):')
        start = current.index('    def check_active('); end = current.index('    try:', start)
        current = current[:start]+current[end:]
        current = current.replace('        if control is not None:\n            control(check_active)\n        check_active()\n', '')
        current = current.replace("\n                if observer is not None:\n                    check_active()\n                    observer('stdout' if key.fileobj is process.stdout else 'stderr', data)\n                    check_active()", '')
        self.assertEqual(current, base)

class FilesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
    def container(self, name=CONTAINER, kind='Data'):
        path = self.root/DEVICE/'data/Containers'/kind/'Application'/name; path.mkdir(parents=True); return path
    def test_container_exact_owner_and_relocation(self):
        first, second = self.container(), self.container(OTHER)
        self.assertEqual(store.safe_container(first, self.root, DEVICE), first)
        self.assertEqual(store.safe_container(second, self.root, DEVICE), second)
        with self.assertRaises(ValueError): store.safe_container(first, self.root, OTHER)
    def test_container_symlink_ancestor_rejected(self):
        real = self.root/'actual'; real.mkdir(); link = self.root/'linked'; link.symlink_to(real, target_is_directory=True)
        path = link/DEVICE/'data/Containers/Data/Application'/CONTAINER; path.mkdir(parents=True)
        with self.assertRaises(ValueError): store.safe_container(path, link, DEVICE)
    def test_pristine_bytes_survive_migration(self):
        a, b = self.container(), self.container(OTHER)
        meta = store.write_synthetic_fixture(a); store.write_synthetic_fixture(b)
        snapshot = store.pristine_snapshot(b, meta)
        self.assertTrue(snapshot['data_container_changed']); self.assertTrue(snapshot['fixture_contents_verified'])
    def test_modified_recipe_or_source_rejected(self):
        for filename in store.synthetic_fixture_bytes():
            with self.subTest(filename=filename):
                folder = self.root/filename; folder.mkdir(); meta = store.write_synthetic_fixture(folder)
                path = folder/'Documents'/store.FIXTURE_NAME/filename; path.write_bytes(path.read_bytes()+b' ')
                with self.assertRaises(ValueError): store.pristine_snapshot(folder, meta)
    def test_sample_overwrite_and_symlink_rejected(self):
        folder = self.container(); store.write_synthetic_fixture(folder)
        with self.assertRaises(ValueError): store.write_synthetic_fixture(folder)
        link = self.root/'unsafe'; link.symlink_to(folder, target_is_directory=True)
        with self.assertRaises(ValueError): store.write_synthetic_fixture(link)
    def test_file_cap_and_symlink(self):
        path = self.root/'test'; path.write_bytes(b'1234')
        with self.assertRaises(ValueError): store.file_record(path, 3)
        link = self.root/'link'; link.symlink_to(path)
        with self.assertRaises(ValueError): store.file_record(link, 5)
    def test_unknown_pack_member_rejected(self):
        folder = self.root/store.FOLDER; folder.mkdir(); (folder/'private.txt').write_text('unexpected')
        with self.assertRaises(ValueError): store.pack(self.root, BINDING, 1, 2)
    def test_pack_retains_exact_original_bytes(self):
        folder = self.root/store.FOLDER; folder.mkdir(); data = b'original test bytes'; (folder/'capture-original.jpeg').write_bytes(data)
        (folder/'report.json').write_text(json.dumps({'original': store.file_record(folder/'capture-original.jpeg', store.ORIGINAL_CAP)}))
        manifest = store.pack(self.root, BINDING, 1, 2)
        self.assertFalse(manifest['store_ready']); self.assertEqual((folder/'capture-original.jpeg').read_bytes(), data)
        self.assertEqual(len(manifest['members']), 2)
    def test_ack_is_complete_when_published_and_cannot_overwrite(self):
        ack = self.root/'capture.ack'; outcome = {'id': REQUEST, 'success': False}
        store.write_ack(ack, outcome)
        self.assertEqual(json.loads(ack.read_text()), outcome)
        self.assertFalse(ack.with_suffix('.ack-staged').exists())
        with self.assertRaises(ValueError): store.write_ack(ack, {'success': True})
        self.assertEqual(json.loads(ack.read_text()), outcome)
    def test_icon_receipt_symlink_rejected_before_target_write(self):
        folder = self.root/store.FOLDER; folder.mkdir()
        source = self.root/'native-icon-provenance-runtime.json'; source.write_text('{}')
        target = self.root/'untouched'; target.write_text('safe')
        (folder/source.name).symlink_to(target)
        with self.assertRaises(ValueError): store.pack(self.root, BINDING, 1, 2)
        self.assertEqual(target.read_text(), 'safe')
    def test_existing_icon_receipt_is_not_overwritten(self):
        folder = self.root/store.FOLDER; folder.mkdir()
        source = self.root/'native-icon-provenance-runtime.json'; source.write_text('{}')
        destination = folder/source.name; destination.write_text('existing')
        with self.assertRaises(ValueError): store.pack(self.root, BINDING, 1, 2)
        self.assertEqual(destination.read_text(), 'existing')
    def test_manifest_symlink_is_rejected_without_writing_target(self):
        folder = self.root/store.FOLDER; folder.mkdir(); target = self.root/'untouched'; target.write_text('safe')
        (folder/'manifest.json').symlink_to(target)
        with self.assertRaises(ValueError): store.pack(self.root, BINDING, 1, 2)
        self.assertEqual(target.read_text(), 'safe')
    def test_pack_original_deadline(self):
        (self.root/store.FOLDER).mkdir()
        with self.assertRaises(ValueError): store.pack(self.root, BINDING, 1, 1+store.PACK_END+1)

class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
    def job(self, execute): return store.Job(ROOT, self.root, BINDING, 1, execute=execute, clock=lambda: 2)
    def work_to_install(self, boot_result, readiness_result=0, control_failure=None, readiness_setup_error=None):
        app = self.root/'products/CelluloidVision.app'
        app.mkdir(parents=True)
        runner = app.parent/'CelluloidVisionUITests-Runner.app'; runner.mkdir()
        (runner/'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': store.RUNNER_ID,
            'CFBundleExecutable': 'Runner'}))
        (runner/'Runner').write_bytes(b'host-only runner fixture')
        runtime = 'com.apple.CoreSimulator.SimRuntime.xrOS-27-0'
        device_type = 'com.apple.CoreSimulator.SimDeviceType.Apple-Vision-Pro-4K'
        calls = []
        def execute(command, **options):
            calls.append(list(command))
            output = b''
            if command[:2] == ['xcodebuild', '-version']: output = b'Xcode 27.0\n'
            if command[:4] == ['xcrun', 'simctl', 'list', 'runtimes']:
                output = json.dumps({'runtimes': [{'identifier': runtime, 'isAvailable': True,
                    'supportedDeviceTypes': [{'identifier': device_type}]}]}).encode()
            if command[:4] == ['xcrun', 'simctl', 'list', 'devicetypes']:
                output = json.dumps({'devicetypes': [{'identifier': device_type}]}).encode()
            if command[:3] == ['xcrun', 'simctl', 'create']: output = DEVICE.encode()
            if command == [sys.executable,'-c',store.HOST_CONTROL_SCRIPT]:
                phase = 'host-control-after-boot' if any(c[:3] == ['xcrun','simctl','boot'] for c in calls) else 'host-control-before-boot'
                self.assertEqual(options['seconds'],30); self.assertEqual(options['cap'],1024)
                if control_failure == phase: return subprocess.CompletedProcess(command,0,b'bad receipt',b'')
                return subprocess.CompletedProcess(command,0,b'VISION_HOST_CONTROL_ENTRY 2.0\nVISION_HOST_CONTROL_EXIT 2.0\n',b'')
            if command[:3] == ['xcrun', 'simctl', 'boot']:
                self.assertEqual(command, ['xcrun', 'simctl', 'boot', DEVICE])
                self.assertEqual(options['seconds'], 45)
                if isinstance(boot_result, BaseException): raise boot_result
                if boot_result == 'late-zero':
                    job.clock = lambda: 48  # Started at 2; even zero exit after 47 fails.
                    return subprocess.CompletedProcess(command, 0, b'', b'')
                return subprocess.CompletedProcess(command, boot_result, b'', b'')
            if command[:3] == ['xcrun','simctl','bootstatus']:
                self.assertEqual(command,['xcrun','simctl','bootstatus',DEVICE,'-b'])
                self.assertEqual(options['seconds'],240)
                if isinstance(readiness_result,BaseException): raise readiness_result
                if readiness_result == 'late-zero':
                    job.clock=lambda:243
                    return subprocess.CompletedProcess(command,0,b'Device already booted, nothing to do.',b'')
                return subprocess.CompletedProcess(command,readiness_result,b'Finished',b'')
            if command[:3] == ['xcrun', 'simctl', 'install']:
                self.assertEqual(command, ['xcrun', 'simctl', 'install', DEVICE, str(app)])
                self.assertEqual(options['seconds'], 360)
                return subprocess.CompletedProcess(command, 1, b'host-only stop at install', b'')
            return subprocess.CompletedProcess(command, 0, output, b'')
        job = self.job(execute)
        if readiness_setup_error is not None:
            original_persist=job.persist;raised=[False]
            def persist():
                if 'readiness' in job.report and not raised[0]:
                    raised[0]=True;raise readiness_setup_error
                original_persist()
            job.persist=persist
        with mock.patch.object(job, 'source_identity'), mock.patch.object(store, 'built_vision_app', return_value=(app, 'b'*64)):
            with self.assertRaises((ValueError, CaptureStopped, TimeoutError, OSError, KeyboardInterrupt)) as caught:
                job.work()
        return job, calls, caught.exception
    def test_successful_controls_and_readiness_continue_same_cohort_to_exact_install(self):
        job, calls, error = self.work_to_install(0)
        device_commands = [command[2] for command in calls if command[:2] == ['xcrun', 'simctl']]
        self.assertEqual(device_commands, ['list', 'list', 'create', 'boot', 'bootstatus', 'install'])
        self.assertEqual([row['phase'] for row in job.report['host_controls']],list(store.HOST_CONTROL_PHASES))
        self.assertTrue(all(row['complete'] for row in job.report['host_controls']))
        self.assertTrue(job.report['readiness']['complete'])
        self.assertEqual(str(error), 'Known completed command failed: install')
        self.assertFalse(job.blocked)
    def test_failed_or_uncertain_boot_never_installs(self):
        for result in (1, -9, None, 'late-zero', CaptureStopped('duration-limit', True)):
            with self.subTest(result=result), tempfile.TemporaryDirectory() as folder:
                self.root = Path(folder)
                job, calls, error = self.work_to_install(result)
                self.assertFalse(any(command[:3] == ['xcrun', 'simctl', 'install'] for command in calls))
                self.assertTrue(job.blocked)
                self.assertEqual(job.device, DEVICE)
    def test_readiness_failure_or_late_exit_stops_install_and_device_cleanup(self):
        for result in (1,-9,None,'late-zero',CaptureStopped('duration-limit',True),
                       CaptureStopped('interrupted-by-signal-15',True,signal.SIGTERM)):
            with self.subTest(result=result),tempfile.TemporaryDirectory() as folder:
                self.root=Path(folder);job,calls,error=self.work_to_install(0,readiness_result=result)
                self.assertTrue(job.blocked);self.assertFalse(job.report['readiness']['complete'])
                self.assertFalse(any(c[:3] == ['xcrun','simctl','install'] for c in calls))
                count=len(calls);job.finish();self.assertEqual(len(calls),count);self.assertEqual(job.report['cleanup'],[])
    def test_control_failures_stop_remaining_device_work(self):
        for phase in store.HOST_CONTROL_PHASES:
            with self.subTest(phase=phase),tempfile.TemporaryDirectory() as folder:
                self.root=Path(folder);job,calls,error=self.work_to_install(0,control_failure=phase)
                self.assertTrue(job.blocked);self.assertFalse(job.report['readiness']['complete'])
                forbidden=('bootstatus','install') if phase.endswith('after-boot') else ('boot','bootstatus','install')
                self.assertFalse(any(c[:2] == ['xcrun','simctl'] and c[2] in forbidden for c in calls))
                count=len(calls);job.finish();self.assertEqual(len(calls),count);self.assertEqual(job.report['cleanup'],[])
    def test_readiness_initial_persist_failure_or_interrupt_stops_device_work(self):
        for error in (OSError('Injected readiness persistence failure'),KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__),tempfile.TemporaryDirectory() as folder:
                self.root=Path(folder);job,calls,caught=self.work_to_install(0,readiness_setup_error=error)
                self.assertIs(caught,error);self.assertTrue(job.blocked)
                self.assertTrue((self.root/store.BARRIER).is_file())
                self.assertEqual([c[2] for c in calls if c[:2] == ['xcrun','simctl']],['list','list','create'])
                count=len(calls);job.finish();self.assertEqual(len(calls),count);self.assertEqual(job.report['cleanup'],[])
    def test_all_fixed_container_queries_use_bounded_metadata_and_no_simctl(self):
        container = self.root/DEVICE/'data/Containers/Data/Application'/CONTAINER
        container.mkdir(parents=True); write_container_metadata(container)
        runner = container.parent/REQUEST; runner.mkdir(); write_container_metadata(runner, store.RUNNER_ID)
        bundle = self.root/DEVICE/'data/Containers/Bundle/Application'/CONTAINER
        bundle.mkdir(parents=True); write_container_metadata(bundle)
        app = bundle/'CelluloidVision.app'; app.mkdir()
        (app/'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': store.APP_ID,
            'CFBundleExecutable': 'CelluloidVision', 'DTPlatformName': 'xrsimulator'}))
        (app/'CelluloidVision').write_bytes(b'mock binary')
        caps = []
        def execute(command, **kwargs):
            caps.append(kwargs['seconds'])
            self.assertNotIn('simctl', command); self.assertNotIn('get_app_container', command)
            self.assertEqual(command[:3], [sys.executable,str(Path(store.__file__).resolve()),'--resolve-container'])
            return subprocess.CompletedProcess(command, 0, json.dumps(store.resolve_container_metadata(self.root, *command[-3:])).encode(), b'')
        job = self.job(execute); job.device = DEVICE; job.devices_root = self.root
        job.report['built_app'] = {'binary_sha256':store.file_record(app/'CelluloidVision',100)['sha256']}
        for phase, (target, kind) in store.CONTAINER_PHASES.items():
            result = job.container(phase, target, kind)
            self.assertEqual(result if kind == 'Data' else Path(result['path']), runner if target == store.RUNNER_ID else app if kind == 'Bundle' else container)
        self.assertEqual(caps, [180]*6)
    def test_seed_data_budget_still_reserves_original_wall_clock(self):
        execute = mock.Mock(side_effect=AssertionError('late native command forbidden'))
        job = store.Job(ROOT, self.root, BINDING, 1, execute=execute, clock=lambda: store.WORK_END-190)
        job.device = DEVICE
        with self.assertRaisesRegex(ValueError, 'wall-time reserve'): job.container('seed-data', store.APP_ID)
        execute.assert_not_called()
    def test_install_360_cap_still_uses_existing_original_deadline_reserve(self):
        execute = mock.Mock(return_value=subprocess.CompletedProcess(['mock'], 0, b'', b''))
        job = self.job(execute)
        job.call('install', ['mock'], 360)
        self.assertEqual(execute.call_args.kwargs['seconds'], 360)
        execute.reset_mock(); job.clock = lambda: 1+store.WORK_END-380
        with self.assertRaisesRegex(ValueError, 'wall-time reserve'): job.call('install', ['mock'], 360)
        execute.assert_not_called()
    def test_host_load_is_aggregate_finite_and_nonfatal(self):
        with mock.patch.object(store.os,'getloadavg',return_value=(1.25,2.5,3.75)):
            job = self.job(lambda *args,**kwargs: subprocess.CompletedProcess(args,0,b'',b''))
            with mock.patch('sys.stdout',new_callable=io.StringIO) as output: job.call('probe',['mock'],1)
        self.assertEqual(job.report['operations'][0]['host_load_before'],[1.25,2.5,3.75])
        start = next(line for line in output.getvalue().splitlines() if line.startswith('VISION_PHASE_START '))
        self.assertEqual(json.loads(start.split(' ',1)[1])['host_load_before'],[1.25,2.5,3.75])
        for value in ((True,1,1),(float('nan'),1,1),(float('inf'),1,1),(-1,1,1),(1,)):
            with self.subTest(value=value), mock.patch.object(store.os,'getloadavg',return_value=value):
                self.assertIsNone(store.host_loadavg())
        with mock.patch.object(store.os,'getloadavg',side_effect=OSError('private system detail')):
            self.assertIsNone(store.host_loadavg())
    def test_known_failure_is_not_uncertainty(self):
        job = self.job(lambda *a, **kw: subprocess.CompletedProcess(a, 1, b'known failure', b''))
        with self.assertRaises(ValueError): job.call('build', ['mock'], 1)
        self.assertFalse(job.blocked)
    def test_phase_and_failure_tail_are_live_bounded_and_independent(self):
        output = io.StringIO()
        def execute(*a, **kw):
            self.assertIn('VISION_PHASE_START ', output.getvalue())
            return subprocess.CompletedProcess(a, 1, b'old-prefix'+b'z'*40000, b'end-of-failure')
        job = self.job(execute)
        with mock.patch('sys.stdout', output), self.assertRaises(ValueError): job.call('compile-image-helper', ['mock'], 1)
        text = output.getvalue()
        self.assertIn('VISION_PHASE_END ', text); self.assertIn('VISION_FAILURE_TAIL ', text)
        self.assertIn('Known completed command failed: compile-image-helper', text)
        self.assertNotIn('old-prefix', text)
        tail = job.diagnostics/'failure-tail.log'
        self.assertEqual(tail.stat().st_size, store.FAILURE_TAIL_CAP)
        self.assertTrue(tail.read_bytes().endswith(b'end-of-failure'))
        self.assertEqual((job.diagnostics/'report.json').read_bytes(), (job.folder/'report.json').read_bytes())
        (job.folder/'unknown').write_bytes(b'reject strict pack')
        with self.assertRaises(ValueError): store.pack(self.root, BINDING, 1, 2)
        self.assertEqual(tail.stat().st_size, store.FAILURE_TAIL_CAP)
        self.assertEqual(json.loads((job.diagnostics/'report.json').read_text())['operations'][0]['complete'], False)
    def test_diagnostics_symlink_rejected(self):
        target = self.root/'untouched'; target.mkdir()
        (self.root/store.DIAGNOSTICS).symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Unsafe diagnostics'): self.job(lambda *a, **kw: None)
        self.assertEqual(list(target.iterdir()), [])
    def test_unknown_failure_raises_durable_barrier(self):
        def fail(*a, **kw): raise CaptureStopped('duration-limit', True)
        job = self.job(fail)
        with self.assertRaises(CaptureStopped): job.call('build', ['mock'], 1)
        self.assertTrue(job.blocked); self.assertTrue((self.root/store.BARRIER).is_file())
        with self.assertRaises(ValueError): job.call('anything', ['mock'], 1)
        job.device = DEVICE; job.finish(); self.assertEqual(job.report['cleanup'], [])
    def test_signalled_process_is_not_complete(self):
        job = self.job(lambda *a, **kw: subprocess.CompletedProcess(a, -9, b'', b''))
        with self.assertRaises(TimeoutError): job.call('build', ['mock'], 1)
        self.assertTrue(job.blocked)
    def test_zero_exit_build_error_rejected(self):
        job = self.job(lambda *a, **kw: subprocess.CompletedProcess(a, 0, b'file.swift: error: no', b''))
        with self.assertRaises(ValueError): job.call('build', ['mock'], 1)
    def test_stream_failure_hits_job_durable_barrier(self):
        job = self.job(lambda *a, **kw: (_ for _ in ()).throw(AssertionError('unexpected adapter')))
        def reject(stream, data): raise ValueError('bad held request')
        with self.assertRaises(CaptureStopped):
            job.call('ui', [sys.executable, '-c', 'import time; print("held", flush=True); time.sleep(10)'], 5, observer=reject)
        self.assertTrue(job.blocked)
        self.assertTrue((self.root/store.BARRIER).is_file())
        self.assertIn('ui.log', {path.name for path in job.folder.iterdir()})
    def test_stream_observer_reads_real_bounded_process(self):
        chunks = []
        result = stream_capture([sys.executable, '-c', 'print("held")'], seconds=5, cap=1000, observer=lambda stream, data: chunks.append((stream, data)))
        self.assertEqual(result.returncode, 0); self.assertEqual(b''.join(data for _, data in chunks), b'held\n')
    def test_stream_observer_failure_stops_owned_group(self):
        def fail(stream, data): raise ValueError('rejected request')
        with self.assertRaises(CaptureStopped) as caught:
            stream_capture([sys.executable, '-c', 'import time; print("held", flush=True); time.sleep(10)'], seconds=5, cap=1000, observer=fail)
        self.assertTrue(caught.exception.cleanup_confirmed)
    def test_stream_byte_limit_preserved(self):
        with self.assertRaises(CaptureStopped) as caught:
            stream_capture([sys.executable, '-c', 'print("x"*10000)'], seconds=5, cap=100)
        self.assertEqual(len(caught.exception.stdout_prefix), 100)
    def test_stream_timeout_preserved(self):
        with self.assertRaises(CaptureStopped) as caught:
            stream_capture([sys.executable, '-c', 'import time; time.sleep(10)'], seconds=.05, cap=100)
        self.assertTrue(caught.exception.cleanup_confirmed)

class HostControlTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
    def test_aggregate_snapshot_uses_only_bounded_builtin_values(self):
        values={'SC_PAGE_SIZE':4096,'SC_PHYS_PAGES':1000,'SC_AVPHYS_PAGES':0}
        with mock.patch.object(store.os,'cpu_count',return_value=3), \
             mock.patch.object(store.os,'sysconf',side_effect=lambda key:values[key]), \
             mock.patch.object(store.os,'getloadavg',return_value=(900.0,800.0,700.0)), \
             mock.patch.object(store.os,'open',side_effect=AssertionError('No file reads')):
            row=store.host_snapshot()
        self.assertEqual(row,{'logical_cpu_capacity':3,'physical_memory_capacity_bytes':4096000,
            'available_physical_memory_bytes':0,'load_average':[900.0,800.0,700.0]})
        self.assertLess(len(json.dumps(row)),1024)
    def test_unsupported_or_invalid_aggregate_counters_are_null_not_health_failures(self):
        for value in (None,True,-1,0,4097):
            with self.subTest(value=value),mock.patch.object(store.os,'cpu_count',return_value=value), \
                 mock.patch.object(store.os,'sysconf',side_effect=ValueError('private value')), \
                 mock.patch.object(store.os,'getloadavg',side_effect=OSError('private value')):
                self.assertEqual(store.host_snapshot(),{'logical_cpu_capacity':None,'physical_memory_capacity_bytes':None,
                    'available_physical_memory_bytes':None,'load_average':None})
        with mock.patch.object(store.os,'sysconf',side_effect=lambda key:{'SC_PAGE_SIZE':4096,'SC_PHYS_PAGES':10,'SC_AVPHYS_PAGES':11}[key]):
            self.assertIsNone(store.host_snapshot()['available_physical_memory_bytes'])
    def test_real_known_subprocess_entry_and_completion_are_retained(self):
        job=store.Job(ROOT,self.root,BINDING,time.monotonic())
        with mock.patch.object(store,'host_loadavg',return_value=[999.0,999.0,999.0]):
            job.host_control(store.HOST_CONTROL_PHASES[0])
        row=job.report['host_controls'][0]
        self.assertTrue(row['complete'])  # No CPU/load admission threshold.
        self.assertLessEqual(row['entry_delay_seconds'],row['observed_total_seconds'])
        self.assertGreaterEqual(row['child_interval_seconds'],0)
        self.assertEqual(job.report['operations'][0]['archive_log']['raw_capture_limit_bytes'],1024)
        self.assertEqual(job.report['operations'][0]['command'],[sys.executable,'-c',store.HOST_CONTROL_SCRIPT])
        self.assertFalse(job.blocked)
        with self.assertRaisesRegex(ValueError,'Duplicate'):job.host_control(store.HOST_CONTROL_PHASES[0])
        self.assertEqual(len(job.report['host_controls']),1)
    def test_malformed_future_or_noisy_receipt_blocks_device_work(self):
        good=b'VISION_HOST_CONTROL_ENTRY 2.0\nVISION_HOST_CONTROL_EXIT 2.0\n'
        for output,error in [(b'private value',b''),(good.replace(b'2.0',b'nan'),b''),
                             (good.replace(b'2.0',b'3.0'),b''),(good,b'noise')]:
            with self.subTest(output=output,error=error),tempfile.TemporaryDirectory() as folder:
                execute=mock.Mock(return_value=subprocess.CompletedProcess([],0,output,error))
                job=store.Job(ROOT,folder,BINDING,1,execute=execute,clock=lambda:2);job.device=DEVICE
                with self.assertRaises(ValueError):job.host_control(store.HOST_CONTROL_PHASES[0])
                self.assertTrue(job.blocked);job.finish();self.assertEqual(execute.call_count,1)
                self.assertEqual(job.report['cleanup'],[]);self.assertFalse(job.report['host_controls'][0]['complete'])
    def test_real_control_timeout_byte_limit_and_signal_keep_owned_stop_barrier(self):
        cases=[('import time;time.sleep(2)',.05,'duration-limit'),
            ('print("x"*2048,flush=True)',5,'byte-limit'),
            ('import os,signal,time;os.kill(os.getppid(),signal.SIGTERM);time.sleep(2)',5,'interrupted-by-signal-15')]
        for script,cap,reason in cases:
            with self.subTest(reason=reason),tempfile.TemporaryDirectory() as folder:
                job=store.Job(ROOT,folder,BINDING,time.monotonic());job.device=DEVICE
                with mock.patch.object(store,'HOST_CONTROL_SCRIPT',script),mock.patch.object(store,'HOST_CONTROL_SECONDS',cap):
                    with self.assertRaises(CaptureStopped) as caught:job.host_control(store.HOST_CONTROL_PHASES[0])
                self.assertEqual(str(caught.exception),reason);self.assertTrue(caught.exception.cleanup_confirmed)
                if reason.startswith('interrupted'):self.assertEqual(caught.exception.cancelled_signal,signal.SIGTERM)
                self.assertTrue(job.blocked);job.finish();self.assertEqual(job.report['cleanup'],[])
                self.assertEqual(len(job.report['operations']),1)
                self.assertLessEqual(job.report['operations'][0]['archive_log']['captured_total_bytes'],1024)
    def test_added_controls_and_readiness_keep_original_critical_path_admission(self):
        self.assertEqual(2*store.HOST_CONTROL_SECONDS+240,300)
        self.assertEqual((store.WORK_END,store.CLEANUP_END,store.PACK_END,store.FINISH_END),(1800,1920,2160,2400))
        for phase,seconds in [('bootstatus',240),('install',360),('ui',1200)]:
            for epsilon in (-.001,0):
                with self.subTest(phase=phase,epsilon=epsilon),tempfile.TemporaryDirectory() as folder:
                    now=1+store.WORK_END-seconds-20+epsilon
                    execute=mock.Mock(return_value=subprocess.CompletedProcess([],0,b'',b''))
                    job=store.Job(ROOT,folder,BINDING,1,execute=execute,clock=lambda:now)
                    if epsilon<0:job.call(phase,['mock'],seconds);execute.assert_called_once()
                    else:
                        with self.assertRaisesRegex(ValueError,'wall-time reserve'):job.call(phase,['mock'],seconds)
                        execute.assert_not_called()
        with tempfile.TemporaryDirectory() as folder:
            execute=mock.Mock(side_effect=AssertionError('Late control must not spawn'))
            job=store.Job(ROOT,folder,BINDING,1,execute=execute,clock=lambda:1+store.WORK_END-store.HOST_CONTROL_SECONDS-20)
            with self.assertRaisesRegex(ValueError,'wall-time reserve'):job.host_control(store.HOST_CONTROL_PHASES[0])
            execute.assert_not_called()

class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.devices = self.root/'home/Library/Developer/CoreSimulator/Devices'
        self.base = self.devices/DEVICE/'data/Containers/Data/Application'
        self.target = self.base/CONTAINER; self.target.mkdir(parents=True)
        write_container_metadata(self.target)
    def resolve(self): return store.resolve_container_metadata(self.devices, DEVICE, store.APP_ID, 'Data')
    def reject(self):
        with self.assertRaisesRegex(ValueError, 'Owned-device container metadata lookup rejected'):
            self.resolve()
    def test_exact_identity_without_reading_unrelated_app_data(self):
        unrelated = self.base/OTHER; unrelated.mkdir(); write_container_metadata(unrelated, 'other.private.application')
        secret = unrelated/'Documents'; secret.symlink_to(self.root/'missing-private-target')
        opened = []; ordinary = os.open
        def inspect(path, *args, **kwargs):
            opened.append(str(path)); self.assertNotIn('Documents', str(path))
            return ordinary(path, *args, **kwargs)
        with mock.patch.object(store.os, 'open', side_effect=inspect): result = self.resolve()
        self.assertEqual(result['path'], str(self.target)); self.assertEqual(result['entries_examined'], 2)
        self.assertNotIn('other.private.application', json.dumps(result)); self.assertNotIn(OTHER, json.dumps(result))
        self.assertEqual(store.validate_container_receipt(result, self.devices, DEVICE, store.APP_ID, 'Data'), self.target)
    def test_missing_match_rejected(self):
        write_container_metadata(self.target, 'other.private.application'); self.reject()
    def test_ambiguous_match_rejected(self):
        another = self.base/OTHER; another.mkdir(); write_container_metadata(another); self.reject()
    def test_other_device_is_never_searched(self):
        write_container_metadata(self.target, 'other.private.application')
        another = self.devices/OTHER/'data/Containers/Data/Application'/CONTAINER
        another.mkdir(parents=True); write_container_metadata(another); self.reject()
    def test_wrong_device_bundle_kind_rejected(self):
        for device, bundle, kind in [('../outside',store.APP_ID,'Data'),(DEVICE,'other.private.application','Data'),
                                   (DEVICE,store.RUNNER_ID,'Bundle'),(DEVICE,store.APP_ID,'Shared')]:
            with self.subTest(device=device,bundle=bundle,kind=kind), self.assertRaises(ValueError):
                store.resolve_container_metadata(self.devices,device,bundle,kind)
    def test_symlink_ancestor_rejected(self):
        moved = self.root/'real-devices'; self.devices.rename(moved); self.devices.symlink_to(moved); self.reject()
    def test_symlink_container_rejected(self):
        moved = self.root/'real-container'; self.target.rename(moved); self.target.symlink_to(moved); self.reject()
    def test_symlink_metadata_rejected(self):
        path = self.target/store.METADATA_NAME; moved = self.root/'real-metadata'; path.rename(moved); path.symlink_to(moved); self.reject()
    def test_hardlinked_metadata_rejected(self):
        os.link(self.target/store.METADATA_NAME,self.root/'metadata-hardlink'); self.reject()
    def test_nonregular_metadata_rejected_without_blocking(self):
        path = self.target/store.METADATA_NAME; path.unlink(); os.mkfifo(path); self.reject()
    def test_missing_or_oversized_metadata_rejected(self):
        path = self.target/store.METADATA_NAME; path.unlink(); self.reject()
        path.write_bytes(b'x'*(store.METADATA_CAP+1)); self.reject()
    def test_invalid_uuid_directory_and_identity_rejected(self):
        path = self.target/store.METADATA_NAME
        path.write_bytes(plistlib.dumps({'MCMMetadataIdentifier':store.APP_ID,'MCMMetadataUUID':'not-a-uuid'})); self.reject()
        write_container_metadata(self.target); self.target.rename(self.base/'not-a-uuid'); self.reject()
    def test_separate_valid_uuid_fields_are_bound_to_exact_metadata(self):
        write_container_metadata(self.target,metadata_uuid=OTHER)
        row=self.resolve()
        self.assertEqual(row['container_uuid'],CONTAINER)
        self.assertEqual(row['metadata']['uuid'],OTHER)
        self.assertEqual(row['metadata']['sha256'],store.hashlib.sha256((self.target/store.METADATA_NAME).read_bytes()).hexdigest())
        self.assertEqual(store.validate_container_receipt(row,self.devices,DEVICE,store.APP_ID,'Data'),self.target)
        for metadata_uuid in (CONTAINER,OTHER.lower()):
            write_container_metadata(self.target,metadata_uuid=metadata_uuid)
            row=self.resolve()
            self.assertEqual(row['metadata']['uuid'],metadata_uuid)
            self.assertEqual(store.validate_container_receipt(row,self.devices,DEVICE,store.APP_ID,'Data'),self.target)
    def test_separate_uuid_still_rejects_wrong_device_bundle_and_multiple_matches(self):
        write_container_metadata(self.target,metadata_uuid=OTHER)
        row=self.resolve()
        for device,bundle in ((OTHER,store.APP_ID),(DEVICE,store.RUNNER_ID)):
            with self.subTest(device=device,bundle=bundle),self.assertRaises(ValueError):
                store.validate_container_receipt(row,self.devices,device,bundle,'Data')
        write_container_metadata(self.target,'other.private.application',metadata_uuid=OTHER)
        outside=self.devices/OTHER/'data/Containers/Data/Application'/CONTAINER
        outside.mkdir(parents=True);write_container_metadata(outside,metadata_uuid=DEVICE)
        self.reject()  # The same bundle on another device cannot satisfy this lookup.
        write_container_metadata(self.target,metadata_uuid=OTHER)
        duplicate=self.base/OTHER;duplicate.mkdir();write_container_metadata(duplicate,metadata_uuid=DEVICE)
        self.reject()  # Distinct valid metadata UUIDs do not disambiguate a bundle.
    def test_separate_uuid_receipt_tampering_and_metadata_mutation_rejected(self):
        write_container_metadata(self.target,metadata_uuid=OTHER);row=self.resolve()
        for field,value in [('uuid',CONTAINER),('sha256','0'*64),('inode',row['metadata']['inode']+1)]:
            changed=copy.deepcopy(row);changed['metadata'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                store.validate_container_receipt(changed,self.devices,DEVICE,store.APP_ID,'Data')
        write_container_metadata(self.target,metadata_uuid=DEVICE)
        with self.assertRaises(ValueError):store.validate_container_receipt(row,self.devices,DEVICE,store.APP_ID,'Data')
        row=self.resolve();path=self.target/store.METADATA_NAME;data=path.read_bytes()
        path.rename(self.root/'old-metadata');path.write_bytes(data)
        with self.assertRaises(ValueError):store.validate_container_receipt(row,self.devices,DEVICE,store.APP_ID,'Data')
    def test_separate_uuid_does_not_change_other_app_data_access(self):
        write_container_metadata(self.target,metadata_uuid=OTHER)
        unrelated=self.base/OTHER;unrelated.mkdir()
        write_container_metadata(unrelated,'other.private.application',metadata_uuid=DEVICE)
        (unrelated/'Documents').symlink_to(self.root/'private-data')
        ordinary=os.open;opened=[]
        def inspect(path,*args,**kwargs):
            opened.append(str(path));self.assertNotIn('Documents',str(path));return ordinary(path,*args,**kwargs)
        with mock.patch.object(store.os,'open',side_effect=inspect):row=self.resolve()
        self.assertEqual(row['path'],str(self.target));self.assertEqual(row['metadata']['uuid'],OTHER)
        self.assertNotIn('other.private.application',json.dumps(row))
        self.assertNotIn(str(unrelated),json.dumps(row))
    def test_malformed_identity_and_duplicate_keys_rejected(self):
        path = self.target/store.METADATA_NAME
        for row in [{}, {'MCMMetadataIdentifier':True,'MCMMetadataUUID':CONTAINER},
                    {'MCMMetadataIdentifier':store.APP_ID,'MCMMetadataUUID':True}, []]:
            with self.subTest(row=row): path.write_bytes(plistlib.dumps(row)); self.reject()
        path.write_bytes(('<plist><dict><key>MCMMetadataIdentifier</key><string>'+store.APP_ID+'</string>'
            '<key>MCMMetadataIdentifier</key><string>'+store.APP_ID+'</string>'
            '<key>MCMMetadataUUID</key><string>'+CONTAINER+'</string></dict></plist>').encode()); self.reject()
        path.write_bytes(b'<plist><dict><key>malformed'); self.reject()
    def test_entry_and_aggregate_caps_rejected(self):
        another = self.base/OTHER; another.mkdir(); write_container_metadata(another,'other.private.application')
        with mock.patch.object(store,'METADATA_ENTRIES',1): self.reject()
        with mock.patch.object(store,'METADATA_TOTAL_CAP',(self.target/store.METADATA_NAME).stat().st_size): self.reject()
    def test_growing_plist_cannot_read_past_remaining_byte_budget(self):
        path = self.target/store.METADATA_NAME; budget = path.stat().st_size
        ordinary = os.read; consumed = []; changed = [False]
        def grow(fd, count):
            if not changed[0]:
                changed[0] = True; path.write_bytes(b'x'*store.METADATA_CAP)
            chunk = ordinary(fd,count); consumed.append(len(chunk)); return chunk
        fd = store.open_directory(self.target)
        try:
            with mock.patch.object(store.os,'read',side_effect=grow), self.assertRaises(ValueError):
                store.metadata_identity(fd,CONTAINER,budget)
        finally: os.close(fd)
        self.assertLessEqual(sum(consumed),budget)
    def test_failure_diagnostic_never_exposes_unrelated_identity(self):
        another = self.base/OTHER; another.mkdir()
        (another/store.METADATA_NAME).write_bytes(b'<plist>other.private.application')
        with self.assertRaises(ValueError) as result: self.resolve()
        for forbidden in ('other.private.application',OTHER,str(another)):
            self.assertNotIn(forbidden,str(result.exception))
    def test_receipt_rejects_tampering_and_metadata_replacement(self):
        receipt = self.resolve()
        for key,value in [('device',OTHER),('bundle_identifier',store.RUNNER_ID),('kind','Bundle'),
                          ('container_uuid',OTHER),('path',str(self.root)),('entries_examined',True)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                store.validate_container_receipt({**receipt,key:value},self.devices,DEVICE,store.APP_ID,'Data')
        write_container_metadata(self.target,'other.private.application')
        with self.assertRaises(ValueError): store.validate_container_receipt(receipt,self.devices,DEVICE,store.APP_ID,'Data')
    def test_migration_is_rediscovered_not_cached(self):
        first = self.resolve(); self.target.rename(self.root/'retired-container')
        new = self.base/OTHER; new.mkdir(); write_container_metadata(new)
        second = self.resolve(); self.assertNotEqual(first['path'],second['path'])
        with self.assertRaises(ValueError): store.validate_container_receipt(first,self.devices,DEVICE,store.APP_ID,'Data')
        self.assertEqual(store.validate_container_receipt(second,self.devices,DEVICE,store.APP_ID,'Data'),new)
    def operation_report(self):
        folder = self.root/store.FOLDER; folder.mkdir(exist_ok=True)
        command = [sys.executable,str(Path(store.__file__).resolve()),'--resolve-container',DEVICE,store.APP_ID,'Data']
        report = {'binding':BINDING,'started_monotonic':1,'device':DEVICE,
            'source-before':{'base':store.BASE,'unchanged_product_scope':True},
            'operations':[{'phase':phase,'complete':True,'return_code':0} for phase in ('create',*store.HOST_CONTROL_PHASES,'boot','bootstatus','install')]
                +[{'phase':'seed-data','complete':False,'seconds':store.METADATA_SECONDS,'command':command}]}
        return folder/'report.json',report
    def test_lookup_requires_persisted_fresh_device_and_exact_operation(self):
        path,report = self.operation_report(); path.write_text(json.dumps(report))
        store.validate_metadata_operation(self.root,BINDING,1,DEVICE,store.APP_ID,'Data')
        for change in ('binding','device','create',*store.HOST_CONTROL_PHASES,'boot','bootstatus','install','uncertain','phase','command','complete','source'):
            row = copy.deepcopy(report)
            if change in ('binding','device'): row[change] = 'wrong'
            elif change in ('create',*store.HOST_CONTROL_PHASES,'boot','bootstatus','install'): row['operations'] = [r for r in row['operations'] if r['phase'] != change]
            elif change == 'uncertain': row['operations'][1]['uncertain'] = True
            elif change == 'source': row['source-before']['base'] = 'f'*40
            else: row['operations'][-1][change] = True if change == 'complete' else 'wrong'
            path.write_text(json.dumps(row))
            with self.subTest(change=change), self.assertRaises(ValueError):
                store.validate_metadata_operation(self.root,BINDING,1,DEVICE,store.APP_ID,'Data')
        path.write_text(json.dumps(report)); (self.root/store.BARRIER).write_text('{}')
        with self.assertRaises(ValueError): store.validate_metadata_operation(self.root,BINDING,1,DEVICE,store.APP_ID,'Data')
    def test_main_lookup_only_reads_metadata_and_never_executes_native(self):
        path,report = self.operation_report(); path.write_text(json.dumps(report))
        (self.root/store.CLOCK).write_text(json.dumps({'binding':BINDING,'started_monotonic':1}))
        with mock.patch.object(sys,'argv',['runner','--resolve-container',DEVICE,store.APP_ID,'Data']), \
             mock.patch.object(store,'environment',return_value=BINDING), mock.patch.object(store,'admission',return_value={}), \
             mock.patch.dict(os.environ,{'RUNNER_TEMP':str(self.root),'HOME':str(self.root/'home')}), \
             mock.patch.object(store.time,'monotonic',return_value=2), \
             mock.patch.object(store,'capture',side_effect=AssertionError('native forbidden')), \
             mock.patch('sys.stdout',new_callable=io.StringIO) as output:
            self.assertEqual(store.main(),0)
        self.assertEqual(json.loads(output.getvalue())['path'],str(self.target))
    def test_uncertain_lookup_never_falls_back_to_cli_or_cleanup(self):
        execute = mock.Mock(side_effect=CaptureStopped('duration-limit',True))
        job = store.Job(ROOT,self.root,BINDING,1,execute=execute,clock=lambda:2); job.device = DEVICE
        with self.assertRaises(CaptureStopped): job.container('seed-data',store.APP_ID)
        self.assertTrue(job.blocked); self.assertEqual(execute.call_count,1)
        self.assertNotIn('simctl',execute.call_args.args[0]); job.finish()
        self.assertEqual(execute.call_count,1); self.assertEqual(job.report['cleanup'],[])
    def cli_fixture(self):
        source = self.root/'minimal-source'; scripts = source/'Scripts'; scripts.mkdir(parents=True)
        driver = scripts/'run_vision_store_capture.py'; driver.write_bytes(Path(store.__file__).read_bytes())
        (scripts/'vision_store_admission.json').write_bytes((ROOT/'Scripts/vision_store_admission.json').read_bytes())
        temp = self.root/'runner-temp'; folder = temp/store.FOLDER; folder.mkdir(parents=True)
        binding = {'GITHUB_REPOSITORY':'100mango/Celluloid','GITHUB_REF':store.BRANCH,
            'GITHUB_WORKFLOW_REF':'100mango/Celluloid/'+store.WORKFLOW+'@'+store.BRANCH,
            'GITHUB_RUN_ATTEMPT':'1','GITHUB_JOB':'vision','GITHUB_EVENT_NAME':'push',
            'DEVELOPER_DIR':'/Applications/Xcode_27.app/Contents/Developer',
            'GITHUB_SHA':'a'*40,'GITHUB_WORKFLOW_SHA':'a'*40,'GITHUB_RUN_ID':'123'}
        started = time.monotonic()
        command = [sys.executable,str(driver),'--resolve-container',DEVICE,store.APP_ID,'Data']
        report = {'binding':binding,'started_monotonic':started,'device':DEVICE,
            'source-before':{'base':store.BASE,'unchanged_product_scope':True},'complete':False,
            'operations':[{'phase':phase,'complete':True,'return_code':0} for phase in ('create',*store.HOST_CONTROL_PHASES,'boot','bootstatus','install')]
                +[{'phase':'seed-data','complete':False,'seconds':store.METADATA_SECONDS,'command':command}]}
        (folder/'report.json').write_text(json.dumps(report))
        (temp/store.CLOCK).write_text(json.dumps({'binding':binding,'started_monotonic':started}))
        env = {**binding,'RUNNER_TEMP':str(temp),'HOME':str(self.root/'home'),'CELLULOID_STORE_ROOT_GO_SHA':'a'*40}
        return source,driver,env
    def test_real_resolver_cli_has_stages_without_native_helper_modules(self):
        source,driver,env = self.cli_fixture()
        for flags in ([],['-O']):
            with self.subTest(flags=flags):
                result = subprocess.run([sys.executable,*flags,str(driver),'--resolve-container',DEVICE,store.APP_ID,'Data'],
                    cwd=source,env=env,capture_output=True,timeout=10)
                self.assertEqual(result.returncode,0,result.stderr.decode())
                self.assertEqual(json.loads(result.stdout)['path'],str(self.target))
                lines = result.stderr.decode().splitlines()
                self.assertLessEqual(len(lines),store.RESOLVER_STAGE_LIMIT)
                self.assertLessEqual(len(result.stderr),store.RESOLVER_STAGE_CAP)
                stages = [json.loads(line.removeprefix('VISION_RESOLVER_STAGE ')) for line in lines]
                self.assertEqual([r['stage'] for r in stages],['script-entry','stdlib-ready','binding-start',
                    'binding-ready','root-open','root-ready','scan-count','match-complete'])
                for row in stages:
                    self.assertLessEqual(set(row),{'stage','elapsed_seconds','entries_seen','metadata_bytes','matches'})
                    self.assertGreaterEqual(row['elapsed_seconds'],0)
                for forbidden in (str(self.root),DEVICE,CONTAINER,store.APP_ID,'argv','environ'):
                    self.assertNotIn(forbidden,result.stderr.decode())
        self.assertFalse((source/'Scripts/mac_archive_capture.py').exists())
    def test_real_resolver_entry_is_flushed_before_blocked_stdlib_import(self):
        source,driver,env = self.cli_fixture()
        # A controlled local shim pauses the first nontrivial stdlib import.
        # No -u flag: this witnesses the explicit entry flush before imports.
        (source/'Scripts/argparse.py').write_text(
            "import time\nfrom pathlib import Path\n"
            "Path('stdlib-import-entered').touch()\ntime.sleep(60)\n")
        process = subprocess.Popen([sys.executable,str(driver),'--resolve-container',DEVICE,store.APP_ID,'Data'],
            cwd=source,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic()+5
            while not (source/'stdlib-import-entered').exists() and time.monotonic()<deadline:
                time.sleep(0.005)
            self.assertTrue((source/'stdlib-import-entered').is_file())
            self.assertIsNone(process.poll())
            ready,_,_ = select.select([process.stderr],[],[],1)
            self.assertEqual(ready,[process.stderr])
            self.assertEqual(process.stderr.readline(),store._RESOLVER_ENTRY.encode())
            self.assertEqual(select.select([process.stderr],[],[],0.05)[0],[])
        finally:
            process.kill(); stdout,stderr = process.communicate(timeout=5)
        self.assertEqual(stdout,b''); self.assertEqual(stderr,b'')
    def test_real_resolver_failure_has_bounded_stages_and_no_identities(self):
        write_container_metadata(self.target,'other.private.application')
        source,driver,env = self.cli_fixture()
        result = subprocess.run([sys.executable,str(driver),'--resolve-container',DEVICE,store.APP_ID,'Data'],
            cwd=source,env=env,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,1); self.assertEqual(result.stdout,b'')
        self.assertIn('lookup-failed',result.stderr.decode()); self.assertIn('failed',result.stderr.decode())
        self.assertLessEqual(len(result.stderr),store.RESOLVER_STAGE_CAP)
        for forbidden in ('other.private.application',str(self.root),DEVICE,store.APP_ID):
            self.assertNotIn(forbidden,result.stderr.decode())
    def assert_reason_cli(self, source, driver, env, step, reason, error_number=None):
        result = subprocess.run([sys.executable,str(driver),'--resolve-container',DEVICE,store.APP_ID,'Data'],
            cwd=source,env=env,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,1); self.assertEqual(result.stdout,b'')
        lines = result.stderr.decode().splitlines()
        self.assertLessEqual(len(lines),store.RESOLVER_STAGE_LIMIT)
        self.assertLessEqual(len(result.stderr),store.RESOLVER_STAGE_CAP)
        rows = [json.loads(line.removeprefix('VISION_RESOLVER_STAGE ')) for line in lines]
        failures = [row for row in rows if row['stage']=='lookup-failed']
        self.assertEqual(len(failures),1,result.stderr.decode()); failure=failures[0]
        self.assertEqual({key:failure[key] for key in ('failure_step','reason','errno')},
            {'failure_step':step,'reason':reason,'errno':error_number})
        for row in rows:
            self.assertLessEqual(set(row),{'stage','elapsed_seconds','entries_seen','metadata_bytes','matches',
                'failure_step','reason','errno'})
        for forbidden in ('other.private.application','private-value',str(self.root),DEVICE,CONTAINER,OTHER,store.APP_ID):
            self.assertNotIn(forbidden,result.stderr.decode())
        return failure
    def test_real_failure_reasons_for_metadata_shape_and_values(self):
        source,driver,env = self.cli_fixture(); path=self.target/store.METADATA_NAME
        cases = [
            (b'', 'metadata-size', 'unsafe-metadata'),
            (b'x'*(store.METADATA_CAP+1), 'metadata-size', 'unsafe-metadata'),
            (b'<plist><dict>private-value', 'metadata-parse', 'plist-invalid'),
            (plistlib.dumps({'MCMMetadataIdentifier':True,'MCMMetadataUUID':CONTAINER}),
                'metadata-identifier','identity-malformed'),
            (plistlib.dumps({'MCMMetadataIdentifier':store.APP_ID}), 'metadata-uuid','invalid-uuid'),
            (plistlib.dumps({'MCMMetadataIdentifier':store.APP_ID,'MCMMetadataUUID':'private-value'}),
                'metadata-uuid','invalid-uuid'),
            (b'<plist><dict><key>MCMMetadataIdentifier</key><string>private-value</string>'
                b'<key>MCMMetadataIdentifier</key><string>private-value</string></dict></plist>',
                'metadata-parse','duplicate-key')]
        for data,step,reason in cases:
            with self.subTest(step=step,reason=reason):
                path.write_bytes(data)
                failure=self.assert_reason_cli(source,driver,env,step,reason)
                # Even a fully read plist rejected later is absent from the
                # successful-identity byte total; zero is not proof of no read.
                self.assertEqual(failure['metadata_bytes'],0)
    def test_real_cli_retains_distinct_metadata_uuid_only_in_owned_receipt(self):
        write_container_metadata(self.target,metadata_uuid=OTHER)
        source,driver,env=self.cli_fixture()
        result=subprocess.run([sys.executable,str(driver),'--resolve-container',DEVICE,store.APP_ID,'Data'],
            cwd=source,env=env,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr.decode())
        row=json.loads(result.stdout)
        self.assertEqual(row['container_uuid'],CONTAINER);self.assertEqual(row['metadata']['uuid'],OTHER)
        self.assertEqual(store.validate_container_receipt(row,self.devices,DEVICE,store.APP_ID,'Data'),self.target)
        for forbidden in (OTHER,CONTAINER,DEVICE,store.APP_ID,str(self.root)):
            self.assertNotIn(forbidden,result.stderr.decode())
    def test_real_failure_reasons_for_metadata_file_safety(self):
        source,driver,env = self.cli_fixture(); path=self.target/store.METADATA_NAME
        path.unlink(); self.assert_reason_cli(source,driver,env,'metadata-open','os-error',errno.ENOENT)
        os.mkfifo(path); self.assert_reason_cli(source,driver,env,'metadata-type','unsafe-metadata')
        path.unlink(); write_container_metadata(self.target)
        hardlink=self.root/'private-value';os.link(path,hardlink)
        self.assert_reason_cli(source,driver,env,'metadata-links','unsafe-metadata')
        hardlink.unlink();path.rename(hardlink);path.symlink_to(hardlink)
        self.assert_reason_cli(source,driver,env,'metadata-open','os-error',errno.ELOOP)
    def test_real_failure_reasons_for_entry_and_target(self):
        source,driver,env = self.cli_fixture()
        write_container_metadata(self.target,'other.private.application')
        self.assert_reason_cli(source,driver,env,'target-missing','target-count')
        write_container_metadata(self.target)
        another=self.base/OTHER;another.mkdir();write_container_metadata(another)
        self.assert_reason_cli(source,driver,env,'target-ambiguous','target-count')
        (another/store.METADATA_NAME).unlink();another.rmdir()
        invalid=self.base/'private-value';self.target.rename(invalid)
        self.assert_reason_cli(source,driver,env,'entry-uuid','invalid-uuid')
        invalid.rename(self.target);moved=self.root/'private-value';self.target.rename(moved);self.target.symlink_to(moved)
        self.assert_reason_cli(source,driver,env,'entry-type','entry-symlink')
    def test_failure_detail_classifies_read_and_stability_without_raw_error(self):
        fd=store.open_directory(self.target); events=[]
        try:
            with mock.patch.object(store.os,'read',side_effect=OSError(errno.EIO,'private-value',str(self.target))):
                with self.assertRaises(OSError):
                    store.metadata_identity(fd,CONTAINER,failure=lambda step,error: events.append(store.resolver_failure(step,error)))
            self.assertEqual(events,[{'failure_step':'metadata-read','reason':'os-error','errno':errno.EIO}])
            events.clear(); ordinary=store.os.read
            def mutate(handle,count):
                data=ordinary(handle,count);write_container_metadata(self.target,'other.private.application');return data
            with mock.patch.object(store.os,'read',side_effect=mutate), self.assertRaises(ValueError):
                store.metadata_identity(fd,CONTAINER,failure=lambda step,error: events.append(store.resolver_failure(step,error)))
            self.assertEqual(events,[{'failure_step':'metadata-stability','reason':'metadata-changed','errno':None}])
        finally: os.close(fd)
    def test_failure_enum_and_errno_whitelist_reject_raw_details(self):
        self.assertEqual(store.resolver_failure('entry-stat',OSError(errno.EACCES,'private-value','/private/path')),
            {'failure_step':'entry-stat','reason':'os-error','errno':errno.EACCES})
        self.assertEqual(store.resolver_failure('entry-uuid',ValueError('private-value'))['reason'],'invalid-uuid')
        self.assertEqual(store.resolver_failure('metadata-parse',RuntimeError('private-value'))['reason'],'plist-invalid')
        for number in (True,0,-1,4096,'private-value'):
            error=OSError();error.errno=number
            self.assertIsNone(store.resolver_failure('entry-open',error)['errno'])
        with self.assertRaises(ValueError):store.resolver_failure('private-value',ValueError())
        valid={'failure_step':'entry-stat','reason':'os-error','errno':errno.EIO}
        invalid=[{**valid,'failure_step':'private-value'},{**valid,'reason':'private-value'},
            {**valid,'errno':True},{**valid,'errno':4096},{**valid,'path':'/private/path'}]
        with mock.patch.object(store,'_RESOLVER_MODE',True), mock.patch('sys.stderr',new_callable=io.StringIO) as output:
            for failure in invalid:
                with self.assertRaises(ValueError):store.resolver_stage('lookup-failed',failure=failure)
            with self.assertRaises(ValueError):store.resolver_stage('scan-count',failure=valid)
            self.assertEqual(output.getvalue(),'')
    def test_failure_detail_fits_the_existing_line_and_byte_caps(self):
        with mock.patch.object(store,'_RESOLVER_MODE',True), mock.patch.object(store,'_RESOLVER_STAGE_COUNT',0), \
             mock.patch.object(store,'_RESOLVER_STAGE_BYTES',0), mock.patch('sys.stderr',new_callable=io.StringIO) as output:
            for count in range(store.RESOLVER_STAGE_LIMIT-1):store.resolver_stage('scan-count',count)
            store.resolver_stage('lookup-failed',failure=store.resolver_failure('metadata-stability',ValueError('Metadata changed during read')))
            with self.assertRaisesRegex(ValueError,'diagnostic cap'):store.resolver_stage('failed')
            self.assertEqual(len(output.getvalue().splitlines()),store.RESOLVER_STAGE_LIMIT)
            self.assertLessEqual(len(output.getvalue().encode()),store.RESOLVER_STAGE_CAP)
    def test_default_pack_and_verdict_cli_do_not_import_native_helpers(self):
        source,driver,env = self.cli_fixture()
        default = subprocess.run([sys.executable,str(driver)],cwd=source,env=env,capture_output=True,timeout=10)
        self.assertEqual(default.returncode,0,default.stderr.decode())
        self.assertFalse(json.loads(default.stdout)['native_execution_enabled'])
        packed = subprocess.run([sys.executable,str(driver),'--pack'],cwd=source,env=env,capture_output=True,timeout=10)
        self.assertEqual(packed.returncode,0,packed.stderr.decode())
        verdict = subprocess.run([sys.executable,str(driver),'--finish-upload'],cwd=source,
            env={**env,'VISION_UPLOAD_OUTCOME':'success'},capture_output=True,timeout=10)
        self.assertEqual(verdict.returncode,1)  # The synthetic report remains incomplete.
        self.assertNotIn('ModuleNotFoundError',verdict.stderr.decode())
    def test_stage_limits_reject_extra_output_and_unknown_fields(self):
        with mock.patch.object(store,'_RESOLVER_MODE',True), mock.patch.object(store,'_RESOLVER_STAGE_COUNT',0), \
             mock.patch.object(store,'_RESOLVER_STAGE_BYTES',0), mock.patch('sys.stderr',new_callable=io.StringIO) as output:
            for count in range(store.RESOLVER_STAGE_LIMIT): store.resolver_stage('scan-count',count,0,0)
            with self.assertRaisesRegex(ValueError,'diagnostic cap'): store.resolver_stage('scan-count')
            self.assertLessEqual(len(output.getvalue().encode()),store.RESOLVER_STAGE_CAP)
            with self.assertRaises(ValueError): store.resolver_stage('other.private.application')
    def test_scan_progress_is_sampled_even_at_maximum_entry_count(self):
        for count in range(store.METADATA_ENTRIES-1): (self.base/('private-name-'+str(count))).touch()
        events = []
        result = store.resolve_container_metadata(self.devices,DEVICE,store.APP_ID,'Data',
            progress=lambda *event: events.append(event))
        self.assertEqual(result['entries_examined'],store.METADATA_ENTRIES)
        self.assertEqual(sum(event[0]=='scan-count' for event in events),17)
        self.assertLess(len(events)+5,store.RESOLVER_STAGE_LIMIT)
        self.assertFalse(any('private-name' in str(event) for event in events))
    def test_prior_lookup_ceiling_preserves_held_and_work_bounds(self):
        self.assertEqual(store.METADATA_SECONDS,180)
        self.assertLess(3*store.METADATA_SECONDS+15+10+20,600)
        self.assertEqual((store.WORK_END,store.CLEANUP_END,store.PACK_END,store.FINISH_END),(1800,1920,2160,2400))


class CheckpointTests(unittest.TestCase):
    # Mocked image bytes below are never native UI evidence or delivered assets.
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.devices = self.root/'devices'
        self.calls = []
        self.job = store.Job(ROOT, self.root, BINDING, 1, execute=self.execute, clock=lambda: 2)
        self.job.devices_root = self.devices; self.job.device = DEVICE
        self.job.image_helper = self.root/'image-helper'
        self.app_data = self.container(CONTAINER)
        metadata = store.write_synthetic_fixture(self.app_data)
        self.app_data.rename(self.root/'retired-app-data')
        self.migrated = self.container(OTHER); store.write_synthetic_fixture(self.migrated)
        self.job.report['sample_input'] = metadata
        app_parent = self.container(CONTAINER, 'Bundle'); self.app = app_parent/'CelluloidVision.app'; self.app.mkdir()
        (self.app/'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': store.APP_ID, 'CFBundleExecutable': 'CelluloidVision', 'DTPlatformName': 'xrsimulator'}))
        (self.app/'CelluloidVision').write_bytes(b'mock binary')
        self.job.report['built_app'] = {'binary_sha256': store.file_record(self.app/'CelluloidVision', 100)['sha256']}
        self.runner = self.container(REQUEST); (self.runner/'tmp').mkdir()
        self.request = self.runner/'tmp'/('Celluloid-store-'+REQUEST+'.json'); self.request.write_text(json.dumps(request()))
        self.ack = self.request.with_suffix('.ack')
    def container(self, name, kind='Data'):
        path = self.devices/DEVICE/'data/Containers'/kind/'Application'/name; path.mkdir(parents=True)
        return write_container_metadata(path, store.RUNNER_ID if name == REQUEST else store.APP_ID)
    def execute(self, command, **kwargs):
        self.calls.append(command)
        if '--resolve-container' in command:
            output = json.dumps(store.resolve_container_metadata(self.devices, *command[-3:])).encode()
        elif 'screenshot' in command:
            Path(command[-1]).write_bytes(b'mocked raw JPEG bytes, not an image'); output = b''
        elif '--inspect' in command: output = json.dumps(IMAGE).encode()
        else: raise AssertionError(command)
        return subprocess.CompletedProcess(command, 0, output, b'')
    def test_single_checkpoint_and_migration_byte_binding(self):
        self.job.checkpoint(REQUEST)
        self.assertEqual(sum('screenshot' in c for c in self.calls), 1)
        ack = json.loads(self.ack.read_text()); self.assertTrue(ack['success'])
        self.assertTrue(self.job.report['sample_at_checkpoint']['data_container_changed'])
        original = self.job.folder/'capture-original.jpeg'
        self.assertEqual(original.read_bytes(), (self.root/'capture-original.jpeg').read_bytes())
        self.assertEqual(ack['original_sha256'], store.file_record(original, 1000)['sha256'])
        self.assertFalse(self.job.report['store_ready'])
        with self.assertRaises(ValueError): self.job.checkpoint(REQUEST)
        self.assertEqual(sum('screenshot' in c for c in self.calls), 1)
    def run_observer(self, callback, seconds=1200):
        parser = store.RequestLines(callback)
        script = 'import time; print('+repr(store.REQUEST_PREFIX+REQUEST)+', flush=True); time.sleep(10)'
        with self.assertRaises(CaptureStopped):
            self.job.call('ui', [sys.executable, '-c', script], seconds, observer=parser)
        self.assertTrue(self.job.blocked)
        self.assertTrue((self.root/store.BARRIER).is_file())
        self.assertFalse(self.ack.exists())
        count = len(self.calls); self.job.finish()
        self.assertEqual(self.job.report['cleanup'], [])
        self.assertEqual(len(self.calls), count)
    def test_held_full_command_budgets_fit_and_after_data_is_outside_hold(self):
        now = [2.0]; self.job.clock = lambda: now[0]
        caps = []; ordinary = self.job.execute
        def execute(command, **kwargs):
            caps.append(kwargs['seconds'])
            result = ordinary(command, **kwargs)
            now[0] += kwargs['seconds'] - .01
            return result
        self.job.execute = execute
        self.job.checkpoint(REQUEST)
        self.assertEqual(caps, [180, 180, 180, 15, 10])
        self.assertTrue(json.loads(self.ack.read_text())['success'])
        self.assertLess(now[0], 2+600-20)
        self.assertIsNone(self.job.checkpoint_deadline)
        # The later lookup remains allowed after the held checkpoint has ended.
        now[0] = 603
        self.job.container('after-data', store.APP_ID)
        self.assertEqual(caps, [180, 180, 180, 15, 10, 180])
        self.assertGreater(now[0], 2+600)
    def test_remaining_held_budget_blocks_full_data_cap_before_spawn(self):
        now = [2.0]; self.job.clock = lambda: now[0]
        # Simulate bounded host validation taking extra time after the first call.
        real_container = self.job.container
        def container(phase, bundle, kind='Data'):
            result = real_container(phase, bundle, kind)
            if phase == 'capture-installed': now[0] = 2+401
            return result
        with mock.patch.object(self.job, 'container', side_effect=container), self.assertRaises(ValueError):
            self.job.checkpoint(REQUEST)
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(self.ack.exists())
        self.assertTrue(self.job.blocked)
    def test_exited_producer_cannot_trigger_held_checkpoint(self):
        def callback(request_id):
            time.sleep(.1)
            self.job.checkpoint(request_id)
        parser = store.RequestLines(callback)
        script = 'print('+repr(store.REQUEST_PREFIX+REQUEST)+', flush=True)'
        with self.assertRaises(CaptureStopped):
            self.job.call('ui', [sys.executable, '-c', script], 60, observer=parser)
        self.assertEqual(self.calls, [])
        self.assertFalse(self.ack.exists())
        self.assertTrue(self.job.blocked)
    def test_signal_inside_observer_blocks_all_checkpoint_side_effects(self):
        def callback(request_id):
            os.kill(os.getpid(), signal.SIGTERM)
            self.job.checkpoint(request_id)
        self.run_observer(callback)
        self.assertEqual(self.calls, [])
    def test_synchronous_observer_outer_deadline_blocks_all_side_effects(self):
        def callback(request_id):
            time.sleep(.08)
            self.job.checkpoint(request_id)
        self.run_observer(callback, seconds=.05)
        self.assertEqual(self.calls, [])
    def test_signal_between_each_checkpoint_command_blocks_next_command_and_ack(self):
        ordinary = self.job.execute
        for stop_after in range(1, 6):
            with self.subTest(stop_after=stop_after):
                if stop_after > 1: self.setUp()
                ordinary = self.job.execute
                def execute(command, **kwargs):
                    result = ordinary(command, **kwargs)
                    if len(self.calls) == stop_after: os.kill(os.getpid(), signal.SIGTERM)
                    return result
                self.job.execute = execute
                self.run_observer(self.job.checkpoint)
                self.assertEqual(len(self.calls), stop_after)
    def test_held_deadline_after_inspection_blocks_ack(self):
        now = [2]; self.job.clock = lambda: now[0]
        ordinary = self.job.execute
        def execute(command, **kwargs):
            result = ordinary(command, **kwargs)
            if '--inspect' in command: now[0] = 603
            return result
        self.job.execute = execute
        self.run_observer(self.job.checkpoint)
        self.assertEqual(len(self.calls), 5)
    def test_signal_during_ack_staging_blocks_atomic_publication(self):
        fsync = os.fsync
        def interrupt(fd):
            fsync(fd); os.kill(os.getpid(), signal.SIGTERM)
        with mock.patch.object(store.os, 'fsync', side_effect=interrupt):
            self.run_observer(self.job.checkpoint)
        self.assertEqual(len(self.calls), 5)
        self.assertFalse(self.ack.with_suffix('.ack-staged').exists())
        self.assertFalse(self.job.report['capture']['success'])
    def test_original_mutated_during_ack_staging_never_publishes_success(self):
        fsync = os.fsync
        def mutate(fd):
            fsync(fd); (self.job.folder/'capture-original.jpeg').write_bytes(b'tampered during staging')
        with mock.patch.object(store.os, 'fsync', side_effect=mutate), self.assertRaisesRegex(ValueError, 'Original changed'):
            self.job.checkpoint(REQUEST)
        self.assertFalse(self.ack.exists())
        self.assertFalse(self.job.report['capture']['success'])
    def test_hash_failure_before_ack_marks_capture_failure(self):
        ordinary = self.job.persist
        def mutate_after_success():
            ordinary()
            if self.job.report.get('capture', {}).get('success'):
                (self.job.folder/'capture-original.jpeg').write_bytes(b'tampered before ack')
        self.job.persist = mutate_after_success
        with self.assertRaisesRegex(ValueError, 'Original changed'): self.job.checkpoint(REQUEST)
        self.assertFalse(self.job.report['capture']['success'])
        self.assertFalse(json.loads(self.ack.read_text())['success'])
    def test_checkpoint_raw_mutation_before_delivery_rejected(self):
        self.job.checkpoint(REQUEST)
        (self.job.folder/'capture-original.jpeg').write_bytes(b'changed after acknowledged checkpoint')
        with self.assertRaisesRegex(ValueError, 'hash or size changed'): self.job.select_delivery()
        self.job.persist()
        with self.assertRaisesRegex(ValueError, 'hash or size changed'): store.pack(self.root, BINDING, 1, 2)
        self.assertFalse((self.job.folder/'manifest.json').exists())
    def test_mutated_source_blocks_before_capture(self):
        source = next((self.migrated/'Documents'/store.FIXTURE_NAME).glob('*.image')); source.write_bytes(b'wrong')
        with self.assertRaises(ValueError): self.job.checkpoint(REQUEST)
        self.assertFalse(any('screenshot' in c for c in self.calls)); self.assertFalse(self.ack.exists())
    def test_wrong_installed_binary_blocks_before_capture(self):
        (self.app/'CelluloidVision').write_bytes(b'wrong')
        with self.assertRaises(ValueError): self.job.checkpoint(REQUEST)
        self.assertFalse(any('screenshot' in c for c in self.calls))
    def test_stale_ack_blocks_before_capture(self):
        self.ack.write_text('{}')
        with self.assertRaises((ValueError, FileExistsError)): self.job.checkpoint(REQUEST)
        self.assertFalse(any('screenshot' in c for c in self.calls))
    def test_unknown_capture_process_blocks_ack_and_device_cleanup(self):
        ordinary = self.job.execute
        def stopped(command, **kwargs):
            if 'screenshot' in command: raise CaptureStopped('duration-limit', True)
            return ordinary(command, **kwargs)
        self.job.execute = stopped
        with self.assertRaises(CaptureStopped): self.job.checkpoint(REQUEST)
        self.assertTrue(self.job.blocked); self.assertFalse(self.ack.exists())
        self.job.finish(); self.assertEqual(self.job.report['cleanup'], [])
    def test_raw_copy_survives_wrong_dimensions_failure(self):
        ordinary = self.job.execute
        def wrong(command, **kwargs):
            if '--inspect' in command: return subprocess.CompletedProcess(command, 0, json.dumps({**IMAGE, 'width': 1280}).encode(), b'')
            return ordinary(command, **kwargs)
        self.job.execute = wrong
        with self.assertRaises(ValueError): self.job.checkpoint(REQUEST)
        self.assertTrue((self.job.folder/'capture-original.jpeg').is_file())
        self.assertFalse(json.loads(self.ack.read_text())['success'])

class EncodingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.qualities = []; self.sizes = {65: 150, 45: 80, 30: 60}
        self.job = store.Job(ROOT, self.root, BINDING, 1, execute=self.execute, clock=lambda: 2)
        self.job.image_helper = self.root/'image-helper'
        self.original = self.job.folder/'capture-original.jpeg'; self.original.write_bytes(b'r'*200)
        self.job.report['original'] = store.file_record(self.original, 1000)
    def execute(self, command, **kwargs):
        quality = int(command[-1]); self.qualities.append(quality)
        Path(command[-2]).write_bytes(b'd'*self.sizes[quality])
        return subprocess.CompletedProcess(command, 0, json.dumps({**IMAGE, 'quality': quality}).encode(), b'')
    def test_quality_ladder_stops_at_first_fitting_same_size_derivative(self):
        with mock.patch.object(store, 'STORE_CAP', 100): self.job.select_delivery()
        self.assertEqual(self.qualities, [65, 45]); self.assertEqual(self.original.read_bytes(), b'r'*200)
        self.assertEqual(self.job.report['delivery_image']['kind'], 'same-size lossy derivative')
        self.assertEqual(self.job.report['delivery_image']['width'], 3840)
    def test_all_qualities_oversized_fail_without_recapture(self):
        self.sizes = {65: 150, 45: 140, 30: 120}
        with mock.patch.object(store, 'STORE_CAP', 100), self.assertRaises(ValueError): self.job.select_delivery()
        self.assertEqual(self.qualities, [65, 45, 30]); self.assertEqual(self.original.read_bytes(), b'r'*200)
        self.assertFalse((self.job.folder/'store-image.jpeg').exists())
    def test_small_original_skips_lossy_encoding(self):
        self.job.select_delivery(); self.assertEqual(self.qualities, [])
        self.assertEqual(self.job.report['delivery_image']['kind'], 'unchanged native original')

    def test_large_original_mutation_before_encoding_rejected(self):
        self.original.write_bytes(b'x'*200)
        with mock.patch.object(store, 'STORE_CAP', 100), self.assertRaisesRegex(ValueError, 'hash or size changed'):
            self.job.select_delivery()
        self.assertEqual(self.qualities, [])
    def test_original_mutation_after_delivery_rejected_by_pack(self):
        self.job.select_delivery(); self.job.persist()
        self.original.write_bytes(b'x'*200)
        with self.assertRaisesRegex(ValueError, 'hash or size changed'): store.pack(self.root, BINDING, 1, 2)
    def test_derivative_mutation_after_selection_rejected_by_pack(self):
        with mock.patch.object(store, 'STORE_CAP', 100): self.job.select_delivery()
        self.job.persist(); (self.job.folder/'store-image.jpeg').write_bytes(b'x'*80)
        with self.assertRaisesRegex(ValueError, 'hash or size changed'): store.pack(self.root, BINDING, 1, 2)
    def test_derivative_wrong_parent_hash_rejected(self):
        with mock.patch.object(store, 'STORE_CAP', 100): self.job.select_delivery()
        self.job.report['delivery_image']['original_sha256'] = 'f'*64; self.job.persist()
        with self.assertRaisesRegex(ValueError, 'Derivative checkpoint hash mismatch'): store.pack(self.root, BINDING, 1, 2)
    def test_pack_and_final_verdict_revalidate_original_and_derivative(self):
        with mock.patch.object(store, 'STORE_CAP', 100): self.job.select_delivery()
        self.job.persist(); store.pack(self.root, BINDING, 1, 2)
        store.verify_packed_images(self.root, BINDING, 1)
        (self.job.folder/'store-image.jpeg').write_bytes(b'x'*80)
        with self.assertRaisesRegex(ValueError, 'Packed evidence hash or size changed'): store.verify_packed_images(self.root, BINDING, 1)
    def test_unbound_raw_or_derivative_rejected(self):
        self.job.report.pop('original'); self.job.persist()
        with self.assertRaisesRegex(ValueError, 'Missing image provenance'): store.pack(self.root, BINDING, 1, 2)

if __name__ == '__main__': unittest.main()
