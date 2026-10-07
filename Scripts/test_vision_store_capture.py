#!/usr/bin/env python3
"""Host-only contract/negative tests. No simulator or Apple tool invocation."""
import copy
import io
import json
import os
import plistlib
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

def write_container_metadata(path, bundle=store.APP_ID):
    (path/store.METADATA_NAME).write_bytes(plistlib.dumps({
        'MCMMetadataIdentifier': bundle, 'MCMMetadataUUID': path.name}, fmt=plistlib.FMT_BINARY))
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
        self.assertEqual(sum(budgets), 42)
        self.assertEqual(budgets, [1,2,32,2,2,2,1])
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
        self.assertNotIn('bootstatus', phases)
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
    def work_to_install(self, boot_result):
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
            if command[:3] == ['xcrun', 'simctl', 'boot']:
                self.assertEqual(command, ['xcrun', 'simctl', 'boot', DEVICE])
                self.assertEqual(options['seconds'], 45)
                if isinstance(boot_result, BaseException): raise boot_result
                if boot_result == 'late-zero':
                    job.clock = lambda: 48  # Started at 2; even zero exit after 47 fails.
                    return subprocess.CompletedProcess(command, 0, b'', b'')
                return subprocess.CompletedProcess(command, boot_result, b'', b'')
            if command[:3] == ['xcrun', 'simctl', 'install']:
                self.assertEqual(command, ['xcrun', 'simctl', 'install', DEVICE, str(app)])
                self.assertEqual(options['seconds'], 360)
                return subprocess.CompletedProcess(command, 1, b'host-only stop at install', b'')
            return subprocess.CompletedProcess(command, 0, output, b'')
        job = self.job(execute)
        with mock.patch.object(job, 'source_identity'), mock.patch.object(store, 'built_vision_app', return_value=(app, 'b'*64)):
            with self.assertRaises((ValueError, CaptureStopped, TimeoutError)) as caught:
                job.work()
        return job, calls, caught.exception
    def test_fresh_successful_boot_proceeds_directly_to_exact_install(self):
        job, calls, error = self.work_to_install(0)
        device_commands = [command[2] for command in calls if command[:2] == ['xcrun', 'simctl']]
        self.assertEqual(device_commands, ['list', 'list', 'create', 'boot', 'install'])
        self.assertEqual(str(error), 'Known completed command failed: install')
        self.assertFalse(job.blocked)
    def test_failed_or_uncertain_boot_never_installs(self):
        for result in (1, -9, None, 'late-zero', CaptureStopped('duration-limit', True)):
            with self.subTest(result=result), tempfile.TemporaryDirectory() as folder:
                self.root = Path(folder)
                job, calls, error = self.work_to_install(result)
                self.assertFalse(any(command[:3] == ['xcrun', 'simctl', 'install'] for command in calls))
                self.assertEqual(job.blocked, result != 1)
                self.assertEqual(job.device, DEVICE)
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
        self.assertEqual(caps, [30]*6)
    def test_seed_data_budget_still_reserves_original_wall_clock(self):
        execute = mock.Mock(side_effect=AssertionError('late native command forbidden'))
        job = store.Job(ROOT, self.root, BINDING, 1, execute=execute, clock=lambda: store.WORK_END-40)
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
        path.write_bytes(plistlib.dumps({'MCMMetadataIdentifier':store.APP_ID,'MCMMetadataUUID':OTHER})); self.reject()
        write_container_metadata(self.target); self.target.rename(self.base/'not-a-uuid'); self.reject()
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
            'operations':[{'phase':phase,'complete':True,'return_code':0} for phase in ('create','boot','install')]
                +[{'phase':'seed-data','complete':False,'seconds':store.METADATA_SECONDS,'command':command}]}
        return folder/'report.json',report
    def test_lookup_requires_persisted_fresh_device_and_exact_operation(self):
        path,report = self.operation_report(); path.write_text(json.dumps(report))
        store.validate_metadata_operation(self.root,BINDING,1,DEVICE,store.APP_ID,'Data')
        for change in ('binding','device','create','boot','install','uncertain','phase','command','complete','source'):
            row = copy.deepcopy(report)
            if change in ('binding','device'): row[change] = 'wrong'
            elif change in ('create','boot','install'): row['operations'] = [r for r in row['operations'] if r['phase'] != change]
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
        self.assertEqual(caps, [30, 30, 30, 15, 10])
        self.assertTrue(json.loads(self.ack.read_text())['success'])
        self.assertLess(now[0], 2+600-20)
        self.assertIsNone(self.job.checkpoint_deadline)
        # The later lookup remains allowed after the held checkpoint has ended.
        now[0] = 603
        self.job.container('after-data', store.APP_ID)
        self.assertEqual(caps, [30, 30, 30, 15, 10, 30])
        self.assertGreater(now[0], 2+600)
    def test_remaining_held_budget_blocks_full_data_cap_before_spawn(self):
        now = [2.0]; self.job.clock = lambda: now[0]
        # Simulate bounded host validation taking extra time after the first call.
        real_container = self.job.container
        def container(phase, bundle, kind='Data'):
            result = real_container(phase, bundle, kind)
            if phase == 'capture-installed': now[0] = 2+551
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
