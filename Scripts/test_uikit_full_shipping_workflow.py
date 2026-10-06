#!/usr/bin/env python3
"""Fixed workflow source and shell orchestration checks; no Apple tools execute."""
from pathlib import Path
import contextlib
import hashlib
import io
from datetime import datetime, timezone
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from unittest.mock import patch

from test_native_workflow_syntax import run_blocks
import uikit_full_shipping_gate as gate
from test_uikit_full_shipping_gate import execution, DEVICE

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/uikit-full-shipping.yml'
ORIGINAL = ROOT / '.github/workflows/apple-platforms.yml'
UNCHANGED = {
    '.github/workflows/apple-platforms.yml': '40fe18118e1f3996717354e56d55e167dff29b8fbe87455c832386e9a1c36f91',
    'Scripts/select_matrix_device.sh': '3afb9187e1c5aa761be31b4cf5cefba11f73663f4df12980408311ff2cca89d1',
    'Scripts/create_fixture.py': '67f78821d35b5b2e76d06c0e1d03c343d7141d1ad804a342010a3652e7eddeae',
}


def job(source, name):
    match = re.search(r'^  ' + re.escape(name) + r':\n(.*?)(?=^  [a-z][a-z-]*:\n|\Z)', source, re.M | re.S)
    if match is None: raise ValueError('Missing job: ' + name)
    return match.group(1)


def step(source, name):
    match = re.search(r'^(\s*)- name: ' + re.escape(name) + r'\n', source, re.M)
    if match is None: raise ValueError('Missing step: ' + name)
    rest = source[match.end():]
    following = re.search(r'^' + re.escape(match.group(1)) + r'- (?:name|uses):', rest, re.M)
    return source[match.start():match.end()] + (rest[:following.start()] if following else rest)


def body(source, name):
    blocks = list(run_blocks(step(source, name)))
    if len(blocks) != 1: raise ValueError('Expected one shell block: ' + name)
    return blocks[0][1]


def xcode_commands(source):
    commands = []
    for line in source.splitlines():
        if 'xcodebuild -project ' not in line: continue
        command = line[line.index('xcodebuild -project '):]
        command = re.split(r' 2>&1| \| tee|; then ', command)[0]
        commands.append(shlex.split(command))
    return commands


class FixedWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text()
        cls.row = job(cls.source, 'uikit-regression')
        cls.mac = job(cls.source, 'mac-producer')

    def test_original_workflow_fixture_actions_and_test_sources_are_unchanged(self):
        for name, digest in UNCHANGED.items():
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), digest)
        self.assertEqual(sum(gate.ROW_COUNTS.values()), 412)
        self.assertEqual(len(gate.source_inventory()), 106)

    def test_all_original_uikit_build_commands_and_test_selections_are_identical(self):
        original = job(ORIGINAL.read_text(), 'uikit-regression')
        self.assertEqual(xcode_commands(self.row), xcode_commands(original))
        self.assertEqual(len(xcode_commands(self.row)), 9)
        for text in (
            'granted) action=grant; method=testRealGrantedAccessCanSelectFixture',
            'revoked) action=revoke; method=testRealRevokedAccessClearsSelectionAndHasRecovery',
            'limited) action=reset; method=testRealLimitedSelectionAndManagement',
            'xcrun simctl privacy "$id" grant photos Mango.Celluloid',
            'xcrun simctl ui "$id" appearance light',
            'xcrun simctl ui "$id" appearance dark',
            'python3 -u Scripts/probe_photos_bootstrap.py "$id" --already-prepared',
            'TEST_RUNNER_CELLULOID_SYNTHETIC_PROBE=1 TEST_RUNNER_CELLULOID_PROBE_SOURCE_SHA="$GITHUB_SHA"',
        ):
            with self.subTest(action=text):
                self.assertIn(text, self.row)
                self.assertIn(text, original)

    def test_original_conditions_preserve_independent_rows_and_phase_failures(self):
        original = job(ORIGINAL.read_text(), 'uikit-regression')
        names = ['Run pure unit and decorated export regressions before import',
                 'Require actual original UIKit manufactured-layer consumer',
                 'Verify PhotoKit readiness and reconcile pristine fixtures',
                 'Run pristine Photos integration regressions', 'Run real Photos permission transitions',
                 'Run strict landscape preflight', 'Run core and official accessibility UI regressions',
                 'Run Dark Mode editing and collage regressions',
                 'Verify actual PhotoKit opaque preservation and output destinations']
        for name in names:
            expected = re.search(r'^\s+if: (.+)$', step(original, name), re.M).group(1)
            actual = re.search(r'^\s+if: (.+)$', step(self.row, name), re.M).group(1)
            with self.subTest(name=name):
                # Canonical staging was inside prepare; preserve its effective prerequisite.
                self.assertEqual(actual, expected.replace("steps.prepare.conclusion == 'success'",
                    "steps.prepare.conclusion == 'success' && steps.stage_fixture.conclusion == 'success'"))
        self.assertNotIn('continue-on-error', self.source)
        self.assertNotIn('|| true', self.source)

    def test_one_push_only_route_two_jobs_and_four_serial_fresh_rows(self):
        self.assertEqual(re.findall(r'^  ([a-z][a-z-]*):$', self.source[self.source.index('jobs:\n'):], re.M),
                         ['mac-producer', 'uikit-regression'])
        self.assertIn('on:\n  push:\n    branches:\n    - codex/uikit-full-shipping\n', self.source)
        for forbidden in ('workflow_dispatch', 'pull_request', 'workflow_run', 'schedule:', 'repository_dispatch',
                          'native-mac-host', 'archive:', 'strategy.fail-fast', 'fromJSON(', 'run-id:'):
            self.assertNotIn(forbidden, self.source)
        self.assertIn('needs: mac-producer', self.row)
        self.assertIn("if: always() && needs.mac-producer.result == 'success'", self.row)
        self.assertIn('fail-fast: false\n      max-parallel: 1', self.row)
        self.assertEqual(re.findall(r'^        - key: (.+)$', self.row, re.M), list(gate.ROWS))
        self.assertEqual(re.findall(r'^          device: (.+)$', self.row, re.M), list(gate.ROWS.values()))
        self.assertEqual(self.source.count('runs-on: xcode-27'), 2)
        self.assertIn('timeout-minutes: 45\n', self.mac)
        self.assertIn('timeout-minutes: 60\n', self.row)
        self.assertIn('cancel-in-progress: false', self.source)
        self.assertIn('group: celluloid-platforms-refs/heads/codex/apple-platforms', self.source)

    def test_same_source_run_attempt_artifact_id_manifest_hash_and_unchanged_mac600(self):
        original = body(ORIGINAL.read_text(), 'Native Mac document tests')
        self.assertEqual(xcode_commands(self.mac), xcode_commands(original))
        self.assertIn('run_bounded.py --seconds 600 --label same-job-Mac-producer xcodebuild', self.mac)
        self.assertIn('verify_required_interoperability.py mac --platform-contract', self.mac)
        self.assertIn('artifact-ids: ${{ needs.mac-producer.outputs.artifact_id }}', self.row)
        self.assertIn('PRODUCER_MANIFEST_SHA: ${{ needs.mac-producer.outputs.manifest_sha256 }}', self.row)
        self.assertIn('--manifest-sha256 "$PRODUCER_MANIFEST_SHA"', self.row)
        self.assertEqual(self.source.count('ref: ${{ github.sha }}'), 2)
        self.assertEqual(self.source.count('fetch-depth: 3'), 2)
        self.assertEqual(self.source.count('persist-credentials: false'), 2)
        self.assertNotRegex(self.source, r'(?:export\s+|env\s+)?GITHUB_(?:SHA|RUN_ID|RUN_ATTEMPT|WORKFLOW_SHA)=')
        self.assertNotRegex(self.source, r'(?i)(?:queue.*(?:21600|6\s*\*\s*3600)|max[_-]age|created_at)')
        self.assertIn('mac_clock 0', self.mac)

    def test_exact_pinned_actions_and_retention_remain_bounded(self):
        uses = re.findall(r'^\s+(?:- )?uses: (.+)$', self.source, re.M)
        expected = ['actions/checkout@11d5960a326750d5838078e36cf38b85af677262',
                    'actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02',
                    'actions/checkout@11d5960a326750d5838078e36cf38b85af677262',
                    'actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093',
                    'actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02']
        self.assertEqual(uses, expected)
        self.assertEqual(self.source.count('retention-days: 1'), 2)
        self.assertEqual(self.source.count('if-no-files-found: error'), 2)
        self.assertNotIn('.xcresult/\n', self.source)

    def test_first_step_clock_before_checkout_and_every_test_uses_fixed_admission(self):
        self.assertLess(self.row.index('full-shipping-clock.json'), self.row.index('uses: actions/checkout@'))
        self.assertIn("'execution_budget_seconds':3360", self.row)
        self.assertIn('seconds=$(full_gate admit --phase "$phase") || return $?', self.row)
        self.assertIn('run_bounded.py --seconds "$seconds" --label "$label" "$@" || status=$?', self.row)
        self.assertIn('full_gate check-clock --phase "$phase"', self.row)
        for line in self.row.splitlines():
            if 'xcodebuild -project' in line:
                with self.subTest(line=line): self.assertRegex(line, r'(?:test_phase |bounded (?:release-build|build) )')
        for phase in ('shutdown', 'delete', 'source-after', 'collection'):
            self.assertIn('bounded ' + phase + ' ', self.row)
        self.assertIn('test "$(full_gate admit --phase upload)" -eq 60', self.row)
        self.assertIn('bounded evidence-screens evidence-screens', self.row)
        self.assertIn('bounded diagnostics diagnostics', self.row)

    def test_nested_owned_helpers_have_no_new_outer_kill_wrapper(self):
        staging=body(self.row,'Stage exact original consumer fixture')
        consumer=body(self.row,'Require actual original UIKit manufactured-layer consumer')
        product=body(self.row,'Verify installed shipping product after all tests')
        mac_collection=body(self.mac,'Export within the unchanged2MB Mac evidence allocation')
        for text in (staging,consumer,product,mac_collection):
            self.assertNotIn('run_bounded.py',text)
            self.assertNotRegex(text,r'(?m)^bounded ')
        self.assertIn('admit --phase fixture-stage)" -eq 600',staging)
        self.assertIn('<=600',staging)
        self.assertIn('check-clock --phase fixture-stage',staging)
        self.assertIn('admit --phase consumer-contract)" -eq 60',consumer)
        self.assertIn('<=60',consumer)
        self.assertIn('check-clock --phase consumer-contract',consumer)
        self.assertIn('check-clock --phase product-readbacks',product)
        collector=(ROOT/'Scripts/collect_native_evidence.py').read_text()
        self.assertIn('COLLECTION_STARTED+150',collector)
        self.assertIn("time.monotonic()-COLLECTION_STARTED>180",collector)
        handoff=(ROOT/'Scripts/uikit_full_shipping_handoff.py').read_text()
        self.assertIn(">=timeout+15",handoff)
        self.assertIn("check_completion(clock,context,'product-readbacks')",handoff)

    def test_device_is_bound_immediately_and_both_owned_cleanup_commands_are_strict(self):
        prepare = body(self.row, 'Select build and boot isolated test simulator')
        self.assertLess(prepare.index('select_matrix_device.sh'), prepare.index('full-shipping-device.json'))
        self.assertLess(prepare.index('full-shipping-device.json'), prepare.index('bounded build '))
        self.assertIn("'run_attempt':os.environ['GITHUB_RUN_ATTEMPT']", prepare)
        self.assertIn("'device':{'id':udid,'model':os.environ['DEVICE_NAME']}", prepare)
        for action, name in [('shutdown', 'Shut down owned simulator'), ('delete', 'Delete owned simulator')]:
            current = step(self.row, name)
            self.assertIn('if: always()', current)
            self.assertIn('id=$(owned_device)', current)
            self.assertIn('xcrun simctl ' + action + ' "$id"', current)
            self.assertIn('record_cleanup ' + action + ' "$status"', current)
            self.assertIn('exit "$status"', current)
        self.assertLess(self.row.index('id: product_after'), self.row.index('id: shutdown'))
        self.assertLess(self.row.index('id: shutdown'), self.row.index('id: delete'))
        self.assertLess(self.row.index('id: delete'), self.row.index('id: source_after'))
        self.assertIn("prerequisites['cleanup']='success' if outcome('shutdown')==outcome('delete')=='success' else 'failure'", self.row)

    def test_phase_logs_summaries_actual_results_and_missing_outcomes_fail_closed(self):
        self.assertIn('2>&1 | tee "$RUNNER_TEMP/$phase.log" || status=$?', self.row)
        self.assertIn('record_phase "$phase" "$status"', self.row)
        self.assertIn('extract_summary "$bundle" "$phase" || summary_status=$?', self.row)
        self.assertIn('"$RUNNER_TEMP/$stem.summary.json"', self.row)
        self.assertIn("'exit_code':phase_codes.get(name)", self.row)
        self.assertIn("'outcome','skipped'", self.row)
        self.assertNotIn("'exit_code':0", self.row)
        for phase in ('bootstrap-readiness', 'bootstrap-reconcile'):
            log, summary = gate.phase_files(phase)
            self.assertIn('stem=' + log[:-4] + ';', self.row)
            self.assertEqual(summary, log[:-4] + '.summary.json')
        self.assertIn("timing=read(log_name+'.timing.json');code=timing.get('return_code')", self.row)
        self.assertIn("assert code==0 and timing['timed_out'] is False", self.row)
        self.assertIn('record_bootstrap_phase "$phase"', self.row)
        self.assertNotIn('BOUNDED_COMMAND_END ', body(self.row, 'Verify PhotoKit readiness and reconcile pristine fixtures'))
        self.assertIn('FULL_STAGE_OUTCOMES: ${{ toJSON(steps) }}', self.row)

    def test_accounting_and_completion_follow_product_source_collection_and_upload(self):
        accounting = body(self.row, 'Account for every original test and prerequisite')
        self.assertIn('full_gate verify --root "$RUNNER_TEMP"', accounting)
        self.assertIn('python3 Scripts/uikit_full_shipping_handoff.py accept-row', accounting)
        ordered = ['id: product_after', 'id: shutdown', 'id: delete', 'id: source_after', 'id: accounting',
                   'id: bounded_evidence', 'id: upload_admission', 'id: row_artifact',
                   'name: Require completed collection upload and final row clock']
        self.assertEqual([self.row.index(s) for s in ordered], sorted(self.row.index(s) for s in ordered))
        final = body(self.row, 'Require completed collection upload and final row clock')
        self.assertIn('full_gate verify ', final)
        self.assertIn('full_gate check-clock --phase upload || status=$?', final)
        self.assertIn('full_gate check-clock || status=$?', final)
        for name in ('ACCOUNTING_OUTCOME', 'COLLECTION_OUTCOME', 'UPLOAD_OUTCOME'):
            self.assertIn('test "$' + name + '" = success || status=1', final)
        self.assertIn('exit "$status"', final)

    def test_all_literal_shell_and_embedded_python_blocks_parse_without_execution(self):
        blocks = list(run_blocks(self.source))
        self.assertGreaterEqual(len(blocks), 37)
        for line, shell in blocks:
            with self.subTest(line=line):
                result = subprocess.run(['bash', '-n'], input=shell, text=True, capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                for match in re.finditer(r"<<'(PY\w*)'(?: \|\| return \$\?)?\n(.*?)^\1$", shell, re.M | re.S):
                    compile(textwrap.dedent(match.group(2)), WORKFLOW.name + ':' + str(line), 'exec')


class ShellOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.temp = Path(self.directory.name)
        source = WORKFLOW.read_text()
        clock_step = body(source, 'Start the fixed row clock')
        self.helper = re.search(r"<<'SHFUNCTIONS'\n(.*?)^SHFUNCTIONS$", clock_step, re.M | re.S).group(1)
        self.env = dict(PATH=os.environ.get('PATH', os.defpath), RUNNER_TEMP=str(self.temp), GITHUB_SHA='a' * 40,
                        GITHUB_RUN_ID='12345', GITHUB_RUN_ATTEMPT='1', CELLULOID_FULL_ROW='compact-phone',
                        DEVICE_NAME=gate.ROWS['compact-phone'], GITHUB_STEP_SUMMARY=str(self.temp / 'step-summary'))
        self.observed_monotonic = 100_000.125
        self.clock = {'schema': gate.CLOCK_SCHEMA, 'source_sha': self.env['GITHUB_SHA'],
                      'run_id': '12345', 'run_attempt': '1', 'row': 'compact-phone',
                      'started_monotonic': 100_000.125, 'started_unix': time.time(),
                      'execution_budget_seconds': gate.EXECUTION_SECONDS}
        self.write_clock()
        self.summary_stub = '''extract_summary() {
  printf '{"synthetic":true}\\n' > "$RUNNER_TEMP/$2.summary.json"
  return "${SUMMARY_STATUS:-0}"
}
'''

    def write_clock(self):
        (self.temp / 'full-shipping-clock.json').write_text(json.dumps(self.clock))

    def run_shell(self, script, helper=None):
        helper = self.helper if helper is None else helper
        # Only gate observations use synthetic time. Actual shell commands and
        # their subprocess timeout/cleanup machinery retain the real clock.
        code = "import sys,time;sys.path.insert(0,'Scripts');from uikit_full_shipping_gate import main;time.monotonic=lambda:" + repr(self.observed_monotonic) + ";main()"
        helper = helper.replace('python3 Scripts/uikit_full_shipping_gate.py', 'python3 -c ' + shlex.quote(code))
        helper = helper.replace('import json,math,os,sys,time\n', 'import json,math,os,sys,time\ntime.monotonic=lambda:' + repr(self.observed_monotonic) + '\n')
        return subprocess.run(['bash', '--noprofile', '--norc', '-c', 'set -euo pipefail\n' +
                               helper + '\n' + script],
                              cwd=ROOT, env=self.env, text=True, capture_output=True, timeout=15)

    def outcomes(self):
        return json.loads((self.temp / 'full-shipping-phase-outcomes.json').read_text())

    def test_failed_command_keeps_actual_pipeline_code_and_still_extracts_summary(self):
        result = self.run_shell(self.summary_stub + '''test_phase units fake.xcresult synthetic python3 -c 'import sys;print("raw stdout");print("raw stderr",file=sys.stderr);sys.exit(7)' ''')
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertEqual(self.outcomes(), [{'name': 'units', 'exit_code': 7}])
        self.assertIn('raw stdout', (self.temp / 'units.log').read_text())
        self.assertIn('raw stderr', (self.temp / 'units.log').read_text())
        self.assertTrue((self.temp / 'units.summary.json').is_file())

    def test_summary_failure_cannot_turn_step_green_or_rewrite_actual_test_success(self):
        self.env['SUMMARY_STATUS'] = '9'
        result = self.run_shell(self.summary_stub + 'test_phase units fake.xcresult synthetic python3 -c "print(123)"')
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertEqual(self.outcomes(), [{'name': 'units', 'exit_code': 0}])

    def test_tee_failure_is_recorded_and_summary_is_still_attempted(self):
        result = self.run_shell(self.summary_stub + '''tee() { cat > /dev/null; return 13; }
test_phase units fake.xcresult synthetic python3 -c 'print(123)'
''')
        self.assertEqual(result.returncode, 13, result.stderr)
        self.assertEqual(self.outcomes(), [{'name': 'units', 'exit_code': 13}])
        self.assertTrue((self.temp / 'units.summary.json').is_file())

    def test_exhausted_clock_prevents_command_execution_and_records_failure(self):
        self.observed_monotonic = self.clock['started_monotonic'] + gate.WORK_SECONDS + 1
        self.clock['started_unix'] -= gate.WORK_SECONDS + 1
        self.write_clock()
        result = self.run_shell(self.summary_stub + '''test_phase units fake.xcresult synthetic python3 -c 'import os,pathlib;pathlib.Path(os.environ["RUNNER_TEMP"],"executed").write_text("bad")' ''')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('No remaining allocation', result.stdout + result.stderr)
        self.assertFalse((self.temp / 'executed').exists())
        self.assertNotEqual(self.outcomes()[0]['exit_code'], 0)

    def test_fresh_uptime_and_inherited_ci_cannot_change_synthetic_clock_outcomes(self):
        for uptime in (0, .125, 29.5, 299.5, 2700, 2701):
            with self.subTest(uptime=uptime), patch.object(time, 'monotonic', return_value=uptime), patch.dict(os.environ, {
                    'GITHUB_REF': 'refs/heads/unrelated-live-run', 'GITHUB_WORKFLOW_SHA': 'f' * 40,
                    'CELLULOID_VALIDATION_SCOPE': 'unrelated-live-scope', 'BASH_ENV': '/must-not-source'}):
                fixture = ShellOutcomeTests()
                try:
                    fixture.setUp()
                    for name in ('GITHUB_REF', 'GITHUB_WORKFLOW_SHA', 'CELLULOID_VALIDATION_SCOPE', 'BASH_ENV'):
                        self.assertNotIn(name, fixture.env)
                    fixture.bootstrap_fixture()
                    result = fixture.run_shell('record_bootstrap_phase bootstrap-readiness || exit "$?"')
                    self.assertEqual(result.returncode, 0, result.stderr)
                    (fixture.temp / 'full-shipping-phase-outcomes.json').unlink()
                    fixture.test_exhausted_clock_prevents_command_execution_and_records_failure()
                finally:
                    fixture.doCleanups()

    def test_late_completion_cannot_promote_failed_or_successful_command(self):
        stub = '''full_gate() { if [[ "$1" == admit ]]; then echo 1; else return 23; fi; }
'''
        for code in (0, 7):
            with self.subTest(code=code):
                result = self.run_shell(stub + 'bounded units synthetic python3 -c "import sys;sys.exit(' + str(code) + ')"')
                self.assertEqual(result.returncode, 7 if code else 1)

    def test_duplicate_phase_receipt_cannot_overwrite_first_failure(self):
        result = self.run_shell('record_phase units 7\nrecord_phase units 0\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.outcomes(), [{'name': 'units', 'exit_code': 7}])

    def test_summary_json_is_separate_from_bounded_runner_telemetry(self):
        binary = self.temp / 'bin'
        binary.mkdir()
        command = binary / 'xcrun'
        command.write_text('#!/usr/bin/env python3\nimport json,sys\nprint(json.dumps({"arguments":sys.argv[1:]}))\n')
        command.chmod(0o700)
        self.env['PATH'] = str(binary) + os.pathsep + self.env['PATH']
        result = self.run_shell('extract_summary fake.xcresult units\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads((self.temp / 'units.summary.json').read_text())
        self.assertEqual(summary['arguments'], ['xcresulttool', 'get', 'test-results', 'summary', '--path', 'fake.xcresult'])
        self.assertNotIn('BOUNDED_COMMAND', (self.temp / 'units.summary.json').read_text())
        self.assertEqual((self.temp / 'step-summary').read_text(), (self.temp / 'units.summary.json').read_text())

    def test_cleanup_records_real_failure_and_does_not_rewrite_prior_action(self):
        result = self.run_shell('record_cleanup shutdown 124\nrecord_cleanup delete 0\nrecord_cleanup shutdown 0\n')
        self.assertNotEqual(result.returncode, 0)
        actions = json.loads((self.temp / 'full-shipping-cleanup-actions.json').read_text())
        self.assertEqual(actions, [{'action': 'shutdown', 'exit_code': 124}, {'action': 'delete', 'exit_code': 0}])

    def test_owned_cleanup_rejects_changed_source_run_attempt_row_model_or_id(self):
        marker = self.temp / 'current-simulator'
        identifier = 'AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE'
        marker.write_text(identifier + '\n')
        helper = self.helper.replace("Path('/tmp/current-celluloid-simulator')", 'Path(' + repr(str(marker)) + ')')
        original = {'schema': 'Celluloid.FullShippingDevice.1', 'source_sha': 'a' * 40,
                    'run_id': '12345', 'run_attempt': '1', 'row': 'compact-phone',
                    'device': {'id': identifier, 'model': gate.ROWS['compact-phone']}}
        receipt = self.temp / 'full-shipping-device.json'
        receipt.write_text(json.dumps(original))
        valid = self.run_shell('owned_device\n', helper)
        self.assertEqual(valid.returncode, 0, valid.stderr)
        self.assertEqual(valid.stdout.strip(), identifier)
        for key, changed in [('source_sha', 'b' * 40), ('run_id', '2'), ('run_attempt', '2'),
                             ('row', 'large-phone'), ('model', gate.ROWS['large-phone']),
                             ('id', 'FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF')]:
            value = json.loads(json.dumps(original))
            (value['device'] if key in ('model', 'id') else value)[key] = changed
            receipt.write_text(json.dumps(value))
            with self.subTest(key=key): self.assertNotEqual(self.run_shell('owned_device\n', helper).returncode, 0)

    def bootstrap_fixture(self, phase='bootstrap-readiness', mutate=None):
        now = time.time()
        self.clock['started_monotonic'] = 100_000.125
        self.observed_monotonic = self.clock['started_monotonic'] + 30
        self.clock['started_unix'] = now - 30
        self.write_clock()
        raw, summary = execution(gate.expected_cases('compact-phone')[phase], start=now - 20)
        timing = {'command': 'xcodebuild', 'timeout_seconds': 360, 'elapsed_seconds': 3.0,
                  'return_code': 0, 'timed_out': False,
                  'started': datetime.fromtimestamp(now - 21, timezone.utc).isoformat(),
                  'finished': datetime.fromtimestamp(now - 18, timezone.utc).isoformat()}
        device = {'schema': 'Celluloid.FullShippingDevice.1', 'source_sha': 'a' * 40,
                  'run_id': '12345', 'run_attempt': '1', 'row': 'compact-phone',
                  'device': {'id': DEVICE, 'model': gate.ROWS['compact-phone']}}
        method, label = {'bootstrap-readiness': ('testPhotosLibraryBootstrapReadiness', 'readiness-before-import'),
                         'bootstrap-reconcile': ('testReconcileSyntheticPhotosAfterImport', 'reconcile-all')}[phase]
        command = ('+ xcodebuild -project Celluloid.xcodeproj -scheme Celluloid -configuration Debug '
                   '-destination platform=iOS Simulator,id=' + DEVICE + ' -derivedDataPath .build '
                   '-resultBundlePath ' + str(self.temp / ('Bootstrap-' + label + '.xcresult')) +
                   ' -parallel-testing-enabled NO -collect-test-diagnostics never '
                   '-only-testing:CelluloidTests/EditorRegressionTests/' + method +
                   ' test-without-building CODE_SIGNING_ALLOWED=NO')
        if mutate: mutate(timing, summary, device)
        log_name, summary_name = gate.phase_files(phase)
        (self.temp / log_name).write_text(raw)
        (self.temp / (log_name + '.timing.json')).write_text(json.dumps(timing))
        (self.temp / summary_name).write_text(json.dumps(summary))
        (self.temp / 'full-shipping-device.json').write_text(json.dumps(device))
        (self.temp / 'bootstrap.log').write_text(command + '\nNATIVE_PROCESS_TIMING ' + json.dumps(timing) + '\n')
        return command, timing

    def test_bootstrap_real_native_timing_and_exact_case_match_are_required(self):
        for phase in ('bootstrap-readiness', 'bootstrap-reconcile'):
            self.bootstrap_fixture(phase)
            with self.subTest(phase=phase):
                result = self.run_shell('record_bootstrap_phase ' + phase + ' || exit "$?"')
                self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.outcomes(), [{'name': 'bootstrap-readiness', 'exit_code': 0},
                                          {'name': 'bootstrap-reconcile', 'exit_code': 0}])

    def test_bootstrap_failed_timed_out_wrong_command_or_stale_receipts_stay_red(self):
        changes = [lambda t, s, d: t.update(return_code=7),
                   lambda t, s, d: t.update(return_code=False),
                   lambda t, s, d: t.update(timed_out=True),
                   lambda t, s, d: t.update(command='xcrun'),
                   lambda t, s, d: t.update(timeout_seconds=359),
                   lambda t, s, d: t.update(elapsed_seconds=float('nan')),
                   lambda t, s, d: t.update(unused=float('nan')),
                   lambda t, s, d: t.update(unused=float('inf')),
                   lambda t, s, d: t.update(unused=float('-inf')),
                   lambda t, s, d: t.update(started=datetime.fromtimestamp(time.time() - 100, timezone.utc).isoformat()),
                   lambda t, s, d: t.update(finished=datetime.fromtimestamp(time.time() + 100, timezone.utc).isoformat()),
                   lambda t, s, d: d.update(run_attempt='2'),
                   lambda t, s, d: s.update(result='Failed')]
        for change in changes:
            outcome_path = self.temp / 'full-shipping-phase-outcomes.json'
            if outcome_path.exists(): outcome_path.unlink()
            self.bootstrap_fixture(mutate=change)
            result = self.run_shell('record_bootstrap_phase bootstrap-readiness || exit "$?"')
            with self.subTest(change=change): self.assertNotEqual(result.returncode, 0)
            if outcome_path.exists() and self.outcomes()[0]['exit_code'] == 7:
                self.assertEqual(self.outcomes(), [{'name': 'bootstrap-readiness', 'exit_code': 7}])

    def test_bootstrap_timing_must_match_one_actual_outer_command_and_receipt(self):
        for mutation in ('missing-command', 'duplicate-command', 'changed-method', 'missing-timing', 'duplicate-timing', 'changed-timing'):
            outcome_path = self.temp / 'full-shipping-phase-outcomes.json'
            if outcome_path.exists(): outcome_path.unlink()
            command, timing = self.bootstrap_fixture()
            lines = [command, 'NATIVE_PROCESS_TIMING ' + json.dumps(timing)]
            if mutation == 'missing-command': lines.pop(0)
            elif mutation == 'duplicate-command': lines.insert(0, command)
            elif mutation == 'changed-method': lines[0] = command.replace('testPhotosLibraryBootstrapReadiness', 'testReconcileSyntheticPhotosAfterImport')
            elif mutation == 'missing-timing': lines.pop()
            elif mutation == 'duplicate-timing': lines.append(lines[-1])
            else:
                timing['return_code'] = 7
                lines[-1] = 'NATIVE_PROCESS_TIMING ' + json.dumps(timing)
            (self.temp / 'bootstrap.log').write_text('\n'.join(lines) + '\n')
            with self.subTest(mutation=mutation):
                self.assertNotEqual(self.run_shell('record_bootstrap_phase bootstrap-readiness || exit "$?"').returncode, 0)

    def test_manifest_keeps_failed_missing_and_unexecuted_prerequisites_red(self):
        script = body(WORKFLOW.read_text(), 'Account for every original test and prerequisite')
        script = script.split('full_gate verify ', 1)[0]
        self.env['FULL_PRODUCER_RESULT'] = 'success'
        self.env['FULL_STAGE_OUTCOMES'] = json.dumps({
            'source_before': {'outcome': 'failure'}, 'prepare': {'outcome': 'success'},
            'shutdown': {'outcome': 'failure'}, 'delete': {'outcome': 'success'}})
        (self.temp / 'full-shipping-phase-outcomes.json').write_text(json.dumps([
            {'name': 'units', 'exit_code': 7}, {'name': 'ui', 'exit_code': 0}]))
        (self.temp / 'full-shipping-cleanup-actions.json').write_text(json.dumps([
            {'action': 'shutdown', 'exit_code': 124}, {'action': 'delete', 'exit_code': 0}]))
        result = self.run_shell(script)
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((self.temp / 'full-shipping-execution.json').read_text())
        self.assertEqual([entry['name'] for entry in manifest['phases']], gate.expected_phases('compact-phone'))
        phases = {entry['name']: entry['exit_code'] for entry in manifest['phases']}
        self.assertEqual(phases['units'], 7)
        self.assertEqual(phases['ui'], 0)
        self.assertIsNone(phases['preservation'])
        self.assertIsNone(phases['bootstrap-readiness'])
        self.assertEqual(manifest['prerequisites']['source_before'], 'failure')
        self.assertEqual(manifest['prerequisites']['producer'], 'failure')
        self.assertEqual(manifest['prerequisites']['cleanup'], 'failure')
        self.assertEqual(manifest['prerequisites']['release_build'], 'skipped')
        self.assertEqual(manifest['device']['id'], '')
        cleanup = json.loads((self.temp / 'full-shipping-cleanup.json').read_text())
        self.assertEqual(cleanup['actions'][0]['exit_code'], 124)
        self.assertEqual(cleanup['source_sha'], self.env['GITHUB_SHA'])
        self.assertEqual(cleanup['run_attempt'], '1')

    def test_final_step_rejects_failed_skipped_or_missing_collection_upload_accounting(self):
        final = body(WORKFLOW.read_text(), 'Require completed collection upload and final row clock')
        stub = 'full_gate() { printf "%s\\n" "$*" >> "$RUNNER_TEMP/final-calls"; return 0; }\n'
        for key in ('ACCOUNTING_OUTCOME', 'COLLECTION_OUTCOME', 'UPLOAD_OUTCOME'):
            for value in ('failure', 'skipped', ''):
                self.env.update(ACCOUNTING_OUTCOME='success', COLLECTION_OUTCOME='success', UPLOAD_OUTCOME='success')
                self.env[key] = value
                with self.subTest(key=key, value=value):
                    self.assertNotEqual(self.run_shell(stub + final).returncode, 0)
        calls = (self.temp / 'final-calls').read_text()
        self.assertIn('check-clock --phase upload', calls)
        self.assertIn('verify --root', calls)
        self.assertIn('check-clock\n', calls)


class ClockRepairLineageTests(unittest.TestCase):
    @unittest.skipUnless(__debug__, 'Source binding is intentionally invoked under normal Python')
    def test_exact_successor_lineage_and_repair_delta_over_actual_protected_bytes(self):
        import verify_combined_source as source
        from staged_test_fixtures import historical_checkout
        with historical_checkout() as root,patch.dict(globals(),ROOT=root),patch.object(source,'ROOT',root):
            self._assert_historical_exact_successor_lineage()

    def _assert_historical_exact_successor_lineage(self):
        import verify_combined_source as source
        from validation_route import UIKIT_FULL, UIKIT_FULL_BASE, UIKIT_FULL_PREDECESSOR, UIKIT_FULL_REPAIR_PATHS, UIKIT_FULL_DRIVER_PATHS
        contract = json.loads((ROOT / 'Scripts/combined-source-contract.json').read_text())
        self.assertEqual(len(contract['files']), 547)
        actual_paths = subprocess.check_output(['git', 'ls-files', '-z', '--', *contract['roots']], cwd=ROOT, text=True)
        head = 'c' * 40
        predecessor = UIKIT_FULL_PREDECESSOR['commit']
        base = UIKIT_FULL_BASE['commit']
        responses = {
            ('rev-parse', 'HEAD'): head,
            ('status', '--porcelain', '--untracked-files=all'): '',
            ('ls-files', '-z', '--', *contract['roots']): actual_paths,
            ('ls-files', '--', '.github/release-controller'): '',
            ('ls-files', '--', '.github/workflows/cloud-release.yml'): '',
            ('rev-parse', 'HEAD^{tree}'): 'd' * 40,
            ('rev-list', '--parents', '-n', '1', 'HEAD'): head + ' ' + predecessor,
            ('rev-list', '--parents', '-n', '1', predecessor): predecessor + ' ' + base,
            ('rev-parse', predecessor + '^{tree}'): UIKIT_FULL_PREDECESSOR['tree'],
            ('diff', '--name-only', predecessor, 'HEAD'): '\n'.join(sorted(UIKIT_FULL_REPAIR_PATHS)),
            ('rev-parse', base + '^{tree}'): UIKIT_FULL_BASE['tree'],
            ('diff', '--name-only', base, 'HEAD'): '\n'.join(sorted(UIKIT_FULL_DRIVER_PATHS)),
        }
        changes = [None,
            (('rev-list', '--parents', '-n', '1', 'HEAD'), head + ' ' + base),
            (('rev-list', '--parents', '-n', '1', 'HEAD'), head + ' ' + predecessor + ' ' + base),
            (('rev-list', '--parents', '-n', '1', predecessor), predecessor + ' ' + 'e' * 40),
            (('rev-parse', predecessor + '^{tree}'), 'e' * 40),
            (('diff', '--name-only', predecessor, 'HEAD'), '\n'.join(sorted(UIKIT_FULL_REPAIR_PATHS - {'Scripts/test_uikit_full_shipping_bootstrap.py'}))),
            (('diff', '--name-only', predecessor, 'HEAD'), '\n'.join(sorted(UIKIT_FULL_REPAIR_PATHS | {'Scripts/uikit_full_shipping_gate.py'}))),
            (('diff', '--name-only', base, 'HEAD'), '\n'.join(sorted(UIKIT_FULL_DRIVER_PATHS | {'unreviewed-source.swift'}))),
        ]
        with tempfile.TemporaryDirectory() as folder:
            ref = 'refs/heads/' + UIKIT_FULL['branch']
            env = {'GITHUB_REPOSITORY': '100mango/Celluloid', 'GITHUB_EVENT_NAME': 'push',
                   'GITHUB_SHA': head, 'GITHUB_WORKFLOW_SHA': head, 'GITHUB_REF': ref,
                   'GITHUB_WORKFLOW_REF': '100mango/Celluloid/' + UIKIT_FULL['workflow_path'] + '@' + ref,
                   'CELLULOID_VALIDATION_SCOPE': UIKIT_FULL['scope'], 'RUNNER_TEMP': folder}
            for change in changes:
                replies = dict(responses)
                if change: replies[change[0]] = change[1]
                def git(command, **kwargs):
                    self.assertEqual(command[0], 'git')
                    return replies[tuple(command[1:])]
                output = Path(folder) / 'combined-source-before.json'
                if output.exists(): output.unlink()
                with self.subTest(change=change), patch.dict(os.environ, env, clear=True), patch.object(sys, 'argv', ['verify_combined_source.py', '--phase', 'before']), patch.object(source.subprocess, 'check_output', side_effect=git), contextlib.redirect_stdout(io.StringIO()):
                    if change:
                        with self.assertRaises(AssertionError): source.main()
                        self.assertFalse(output.exists())
                    else:
                        source.main()
                        report = json.loads(output.read_text())
                        self.assertEqual(report['file_count'], 547)
                        self.assertEqual(report['source_fingerprint'], UIKIT_FULL_BASE['fingerprint'])
                        self.assertEqual(report['full_shipping_source']['clock_repair_paths'], sorted(UIKIT_FULL_REPAIR_PATHS))


if __name__ == '__main__':
    unittest.main()
