"""Portable parser/guard tests with labeled synthetic logs, not native UI proof."""
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import picker_native_receipt as receipt

RUN = "a530ecbd-ff51-48cc-8aeb-6123f07363b6"
INSTANCE = "d1203fb7-070b-4b3d-b907-e46963f2e650"
SHA = "a" * 40
TREE = "b" * 40
WALL = 1791513700.0
UPTIME = 1700.0


def stamp(delta, full=False):
    dt = datetime.fromtimestamp(WALL + delta, timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f+0000" if full else "%H:%M:%S.%f")


def app(event, delta, picker="none", details="", instance=INSTANCE):
    return f"PICKER_APP_TRACE run={RUN} instance={instance} event={event} picker={picker} pid=44733 uptime_seconds={UPTIME+delta:.6f} wall_seconds={WALL+delta:.6f} {details}"


def ui(event, delta, iteration=1, details="", full=False):
    return f"{stamp(delta, full)} CelluloidUITests-Runner[44681:113934] PICKER_UI_TRACE run={RUN} iteration={iteration} event={event} uptime_seconds={UPTIME+delta:.6f} wall_seconds={WALL+delta:.6f} {details}"


def ax(prop, delta, value="true", duration=.02):
    return f"{stamp(delta, True)} CelluloidUITests-Runner[44681:113934] PICKER_AX_QUERY run={RUN} iteration=1 property={prop} value={value} duration_seconds={duration} end_uptime_seconds={UPTIME+delta:.6f} wall_seconds={WALL+delta:.6f}"


def native(event, delta, pid=44733):
    return f"{stamp(delta)} CelluloidUITests-Runner[44681:113999] Received kAXUserTestingNotification from AX element pid: {pid}, elementOrHash.elementID: 0.1: {{\n    controllerClass = PHPickerViewController;\n    controllerTitle = Photos;\n    event = {event};\n}}"


def synthesis(delta):
    date = datetime.fromtimestamp(WALL + delta, timezone.utc).strftime("%Y-%m-%d %H:%M:%S +0000")
    return f"{stamp(delta)} CelluloidUITests-Runner[44681:113934] <XCTContext: 0x104e9d360> started activity <XCActivityRecord: 0x107f98d90> {date}: Synthesize event"


def identities(values):
    return "selection_base64=" + base64.b64encode(json.dumps(values).encode()).decode()


def example(selected=False, native_delay=0, ax_delay=0, queue_delay=0):
    # Synthetic clocks mirror the exact native event syntax in historical logs.
    command_time = max(3, 2.4 + ax_delay, 2 + native_delay) + queue_delay
    app_lines = [app("app-beautify-tap", 1.1+queue_delay), app("picker-construction-returned", 1.2+queue_delay, "0x123abc"),
                 app("picker-selection-delegate" if selected else "picker-cancel-delegate", command_time+.1, "0x123abc")]
    if selected:
        app_lines += [app("picker-selected-identities", command_time+.11, details=identities(["synthetic-fixture-1"])),
                      app("resolved-original-identities", command_time+.4, details=identities(["synthetic-fixture-1"]))]
    app_lines += [app("picker-representable-dismantle", command_time+.4, "0x123abc"),
                  app("picker-coordinator-released", command_time+.5),
                  app("root-cover-dismissal-completed", command_time+.9)]
    runner_lines = [ui("run-begin", 0, 0), ui("tap-command-start", 1), synthesis(1.05),
                    native("ViewDidAppear", 1.9+native_delay+queue_delay), ui("tap-command-returned", 2+ax_delay+queue_delay),
                    ax("exists", 2.1+ax_delay+queue_delay), ax("isEnabled", 2.2+ax_delay+queue_delay), ax("isHittable", 2.3+ax_delay+queue_delay),
                    ui("selection-command-start" if selected else "cancel-command-start", command_time),
                    native("ViewDidDisappear", command_time+.3)]
    if selected:
        runner_lines.append(ui("editor-interactive-after-selection", command_time+.7,
                               details="editor_exists=true editor_enabled=true editor_hittable=true picker_candidates_exist=false"))
    runner_lines += [ui("home-interactive-after-dismiss", command_time+1,
                       details=f"via={'editor' if selected else 'cancel'} home_exists=true home_hittable=true picker_exists=false"),
                     ui("run-end", command_time+2, 0),
                     "SWIFTUI_PICKER_ENTRY iteration=2 elapsed_seconds=5.265158833333317 budget_seconds=3 result=1"]
    return {"app-stdout.log": "\n".join(app_lines), "runner.log": "\n".join(runner_lines)}


class ReceiptTests(unittest.TestCase):
    def validate(self, logs=None, selected=False):
        return receipt.validate_logs(logs or example(selected), {RUN: (0, 1) if selected else (1, 0)},
                                     fixture_identifiers={"synthetic-fixture-1"} if selected else None)

    def rejects(self, logs, message=None, selected=False):
        with self.assertRaises(receipt.EvidenceError) as caught:
            self.validate(logs, selected)
        if message:
            self.assertIn(message, str(caught.exception))

    def test_valid_cancel_receipt_separates_historical_failure(self):
        result = self.validate()
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["historical_whole_xctest_seconds"], [5.265158833333317])
        self.assertFalse(result["historical_metric_is_acceptance_gate"])
        self.assertAlmostEqual(result["presentations"][0]["app_action_to_native_appearance_seconds"], .8, places=5)
        self.assertAlmostEqual(result["presentations"][0]["app_action_to_successful_hittable_upper_seconds"], 1.2)
        self.assertIn("no object pointer", result["presentations"][0]["native_instance_binding"])

    def test_selected_original_and_editor_then_home(self):
        result = self.validate(selected=True)
        self.assertEqual(result["status"], "passed")
        proof = result["presentations"][0]["selected_original_proof"]
        self.assertTrue(proof["synthetic_fixture_membership"])
        self.assertNotIn("synthetic-fixture-1", json.dumps(result))

    def test_input_delivery_queue_delay_is_never_removed_from_acceptance(self):
        result = self.validate(example(queue_delay=2.5))
        self.assertEqual(result['status'], 'not_accepted')
        presentation = result['presentations'][0]
        self.assertEqual(presentation['native_appearance_budget'], 'passed')
        self.assertEqual(presentation['input_synthesis_to_native_appearance_budget'], 'over_budget_observation')
        self.assertAlmostEqual(presentation['tap_command_to_input_synthesis_seconds'], .05, places=5)
        self.assertAlmostEqual(presentation['input_synthesis_to_app_action_seconds'], 2.55, places=5)
        self.assertAlmostEqual(presentation['input_synthesis_to_native_appearance_seconds'], 3.35, places=5)
        self.assertAlmostEqual(presentation['app_action_to_native_appearance_seconds'], .8, places=5)

    def test_missing_duplicate_foreign_or_completed_synthesis_fails(self):
        for replacement in ('', synthesis(1.05)+'\n'+synthesis(1.06),
                            synthesis(1.05).replace('[44681:', '[99999:'),
                            synthesis(1.05).replace('started activity', 'finished activity')):
            logs = example(); logs['runner.log'] = logs['runner.log'].replace(synthesis(1.05), replacement)
            self.rejects(logs, 'native input synthesis')

    def test_synthesis_after_app_action_cannot_hide_input_delay(self):
        logs = example(); logs['runner.log'] = logs['runner.log'].replace(synthesis(1.05), synthesis(1.15))
        self.rejects(logs, 'App action precedes')

    def test_app_or_xcodebuild_mirror_cannot_impersonate_synthesis_start(self):
        for process in ('Celluloid', 'xcodebuild'):
            logs = example(); logs['runner.log'] = logs['runner.log'].replace(synthesis(1.05), synthesis(1.05).replace('CelluloidUITests-Runner', process))
            self.rejects(logs, 'did not originate')

    def test_orphan_instance_remains_rejected(self):
        logs = example(); logs['app-stdout.log'] += '\n' + app('picker-coordinator-created', 1.15, instance=RUN)
        self.rejects(logs, 'Orphan app presentation instance')

    def test_input_native_budget_boundary_keeps_uncertainty(self):
        result = self.validate(example(native_delay=2.15, ax_delay=2.3))
        self.assertEqual(result['status'], 'not_accepted')
        self.assertEqual(result['presentations'][0]['input_synthesis_to_native_appearance_budget'], 'inconclusive_clock_budget')

    def test_recorded_query_start_end_and_duration_must_agree(self):
        logs = example()
        start_fields = f'start_uptime_seconds={UPTIME+2.08:.6f} start_wall_seconds={WALL+2.08:.6f}'
        old = ax('exists', 2.1)
        logs['runner.log'] = logs['runner.log'].replace(old, old+' '+start_fields)
        self.assertEqual(self.validate(logs)['status'], 'passed')
        logs['runner.log'] = logs['runner.log'].replace(f'start_uptime_seconds={UPTIME+2.08:.6f}', f'start_uptime_seconds={UPTIME+2:.6f}')
        self.rejects(logs, 'AX start/end/duration')

    def test_missing_or_disagreeing_query_start_wall_is_invalid(self):
        for start_fields in (f'start_uptime_seconds={UPTIME+2.08:.6f}',
                             f'start_uptime_seconds={UPTIME+2.08:.6f} start_wall_seconds={WALL+2.4:.6f}'):
            logs=example(); old=ax('exists', 2.1)
            logs['runner.log']=logs['runner.log'].replace(old,old+' '+start_fields)
            self.rejects(logs)

    def test_true_ax_over_budget_is_inconclusive_not_freeze(self):
        result = self.validate(example(ax_delay=2))
        self.assertEqual(result["status"], "not_accepted")
        self.assertEqual(result["presentations"][0]["native_appearance_budget"], "passed")
        self.assertEqual(result["presentations"][0]["ax_observability_budget"], "inconclusive_interactivity_budget")

    def test_native_appearance_over_budget_fails(self):
        result = self.validate(example(native_delay=2.3, ax_delay=2.4))
        self.assertEqual(result["status"], "not_accepted")
        self.assertEqual(result["presentations"][0]["native_appearance_budget"], "over_budget_observation")

    def test_exact_native_three_seconds_is_not_accepted_without_uncertainty_margin(self):
        result = self.validate(example(native_delay=2.2, ax_delay=2.3))
        self.assertEqual(result["presentations"][0]["native_appearance_budget"], "inconclusive_clock_budget")

    def test_missing_each_required_app_event_fails(self):
        for name in ("app-beautify-tap", "picker-construction-returned", "picker-cancel-delegate"):
            with self.subTest(name=name):
                logs = example(); logs["app-stdout.log"] = "\n".join(line for line in logs["app-stdout.log"].splitlines() if "event="+name not in line)
                self.rejects(logs)

    def test_missing_each_required_ui_event_fails(self):
        for name in ("run-begin", "run-end", "tap-command-start", "tap-command-returned", "cancel-command-start", "home-interactive-after-dismiss"):
            with self.subTest(name=name):
                logs = example(); logs["runner.log"] = "\n".join(line for line in logs["runner.log"].splitlines() if "event="+name not in line)
                self.rejects(logs)

    def test_missing_native_appearance_or_disappearance_fails(self):
        for name in ("ViewDidAppear", "ViewDidDisappear"):
            logs = example(); logs["runner.log"] = logs["runner.log"].replace(native(name, 1.9 if name == "ViewDidAppear" else 3.3), "")
            self.rejects(logs, "native PHPicker")

    def test_duplicate_native_or_app_event_fails(self):
        for key, line in (("runner.log", native("ViewDidAppear", 1.95)), ("app-stdout.log", app("app-beautify-tap", 1.1001))):
            logs = example(); logs[key] += "\n" + line
            self.rejects(logs)

    def test_other_picker_class_does_not_substitute_for_native(self):
        logs = example(); logs["runner.log"] = logs["runner.log"].replace("controllerClass = PHPickerViewController;", "controllerClass = FakePickerViewController;")
        self.rejects(logs, "native PHPicker")

    def test_wrong_native_app_or_runner_pid_fails(self):
        for old, new in (("pid: 44733", "pid: 99999"), ("[44681:113999]", "[77777:113999]")):
            logs = example(); logs["runner.log"] = logs["runner.log"].replace(old, new)
            self.rejects(logs, "native PHPicker")

    def test_fake_app_native_event_cannot_substitute(self):
        logs = example(); logs["runner.log"] = logs["runner.log"].replace("CelluloidUITests-Runner[44681:113999]", "Celluloid[44733:113999]")
        self.rejects(logs, "did not originate")

    def test_appearance_after_delegate_fails(self):
        logs = example(); logs["runner.log"] = logs["runner.log"].replace(native("ViewDidAppear", 1.9), native("ViewDidAppear", 3.2))
        self.rejects(logs, "ordering")

    def test_native_timestamp_clock_offset_fails(self):
        logs = example(); logs["runner.log"] = logs["runner.log"].replace(stamp(0), stamp(.2), 1)
        self.rejects(logs, "Native log clock")

    def test_app_clock_skew_fails(self):
        logs = example(); logs["app-stdout.log"] = logs["app-stdout.log"].replace(f"wall_seconds={WALL+1.1:.6f}", f"wall_seconds={WALL+1.3:.6f}")
        self.rejects(logs, "clock skew")

    def test_unprefixed_clock_anchor_fails(self):
        logs = example(); logs["runner.log"] = logs["runner.log"].replace(f"{stamp(0)} CelluloidUITests-Runner[44681:113934] ", "")
        self.rejects(logs, "NSLog anchors")

    def test_midnight_native_times_resolve_from_real_clock_anchors(self):
        global WALL
        before = WALL
        try:
            WALL = datetime(2026, 10, 9, 23, 59, 58, tzinfo=timezone.utc).timestamp()
            self.assertEqual(self.validate()["status"], "passed")
        finally:
            WALL = before

    def test_nonfinite_clock_negative_query_duration_and_duplicate_field_fail(self):
        for old, new in (("duration_seconds=0.02", "duration_seconds=-1"), ("uptime_seconds=1700.000000", "uptime_seconds=nan"), ("iteration=0", "iteration=0 iteration=0")):
            logs = example(); logs["runner.log"] = logs["runner.log"].replace(old, new)
            self.rejects(logs)

    def test_actual_ax_bool_false_or_missing_cannot_be_inferred(self):
        for prop in ("exists", "isEnabled", "isHittable"):
            logs = example(); logs["runner.log"] = logs["runner.log"].replace(f"property={prop} value=true", f"property={prop} value=false")
            self.rejects(logs, "No real consecutive")

    def test_separated_true_queries_do_not_make_success(self):
        logs = example(); logs["runner.log"] = logs["runner.log"].replace(ax("isEnabled", 2.2), ax("exists", 2.15, "false") + "\n" + ax("isEnabled", 2.2))
        self.rejects(logs, "No real consecutive")

    def test_false_return_booleans_not_event_label_prove_home(self):
        logs = example(); logs["runner.log"] = logs["runner.log"].replace("home_hittable=true", "home_hittable=false")
        self.rejects(logs, "return-state")

    def test_false_editor_booleans_fail(self):
        logs = example(True); logs["runner.log"] = logs["runner.log"].replace("editor_enabled=true", "editor_enabled=false")
        self.rejects(logs, "return-state", selected=True)

    def test_mismatched_uuid_pid_and_pointer_fail(self):
        for old, new in ((f"instance={INSTANCE} event=picker-cancel", f"instance={RUN} event=picker-cancel"), ("picker=0x123abc pid=44733", "picker=0x123abc pid=22222"), ("event=picker-cancel-delegate picker=0x123abc", "event=picker-cancel-delegate picker=0x456abc")):
            logs = example(); logs["app-stdout.log"] = logs["app-stdout.log"].replace(old, new, 1)
            self.rejects(logs)

    def test_wrong_run_fails(self):
        logs = example(); logs["app-stdout.log"] = logs["app-stdout.log"].replace(RUN, INSTANCE)
        self.rejects(logs, "run identity")

    def test_identical_trace_copies_deduplicated_distinct_repetition_rejected(self):
        logs = example(); logs["copied-console.log"] = logs["runner.log"]
        self.assertEqual(self.validate(logs)["status"], "passed")
        logs["runner.log"] += "\n" + ui("tap-command-start", 1)
        self.assertEqual(self.validate(logs)["status"], "passed")
        logs["runner.log"] += "\n" + ui("tap-command-start", 1.001)
        self.rejects(logs)

    def test_extra_native_presentation_fails(self):
        logs = example(); logs["runner.log"] += "\n" + native("ViewDidAppear", .5)
        self.rejects(logs, "Unmatched native")

    def test_wrong_expected_counts_fail(self):
        with self.assertRaisesRegex(receipt.EvidenceError, "iterations"):
            receipt.validate_logs(example(), {RUN: (3, 0)})

    def test_selection_rejects_nil_empty_duplicates_too_many_wrong_original(self):
        for values in ([None], [""], [], ["x", "x"], ["a", "b", "c", "d", "e"], ["unverified"]):
            logs = example(True); logs["app-stdout.log"] = logs["app-stdout.log"].replace(identities(["synthetic-fixture-1"]), identities(values))
            self.rejects(logs, selected=True)

    def test_selection_picker_resolved_mismatch_fails(self):
        logs = example(True); logs["app-stdout.log"] = logs["app-stdout.log"].replace(identities(["synthetic-fixture-1"]), identities(["other"]), 1)
        self.rejects(logs, "mismatch", selected=True)

    def test_selection_without_manifest_fails(self):
        with self.assertRaisesRegex(receipt.EvidenceError, "manifest"):
            receipt.validate_logs(example(True), {RUN: (0, 1)})


class IdentityExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / "test.xcresult"; self.bundle.mkdir()
        (self.bundle / "Info.plist").write_bytes(b"synthetic bundle")
        self.binary = self.root / "Celluloid"; self.binary.write_bytes(b"synthetic executable")
        self.identity = {"schema_version": 1, "source_sha": SHA, "source_tree": TREE,
                         "xcresult_sha256": receipt.bundle_digest(self.bundle), "app_binary_sha256": receipt.sha256_file(self.binary),
                         "runs": [{"run_id": RUN, "expected_cancel_count": 1, "expected_selected_count": 0}]}

    def verify(self):
        return receipt.verify_identity(self.identity, self.bundle, self.binary, SHA, TREE, {RUN: (1, 0)})

    def test_exact_identity_passes(self):
        self.assertEqual(self.verify(), {RUN: (1, 0)})

    def test_wrong_source_tree_run_or_build_hash_fails(self):
        for key in ("source_sha", "source_tree", "xcresult_sha256", "app_binary_sha256"):
            saved = self.identity[key]; self.identity[key] = "f" * len(saved)
            with self.assertRaises(receipt.EvidenceError): self.verify()
            self.identity[key] = saved
        self.identity["runs"][0]["run_id"] = INSTANCE
        with self.assertRaises(receipt.EvidenceError): self.verify()

    def test_bundle_mutation_and_symlink_fail(self):
        (self.bundle / "new").write_bytes(b"added")
        with self.assertRaisesRegex(receipt.EvidenceError, "hash"): self.verify()
        (self.bundle / "new").unlink(); (self.bundle / "link").symlink_to(self.binary)
        with self.assertRaisesRegex(receipt.EvidenceError, "Symlink"): self.verify()

    def test_modern_export_only_if_help_confirms(self):
        calls = []
        def tool(command, deadline):
            calls.append(command)
            if command[-2:] == ["help", "export"]: return "SUBCOMMANDS:\n  diagnostics Export diagnostics\n"
            if "help" in command: return "--path <path> --output-path <output-path>"
            return ""
        result = receipt.export_diagnostics(self.bundle, self.root/"out", tool)
        self.assertEqual(result["method"], "xcresulttool export diagnostics")
        self.assertEqual(len(calls), 3)

    def test_legacy_export_uses_returned_diagnostics_ref_not_guess(self):
        calls = []
        def tool(command, deadline):
            calls.append(command)
            if command[-2:] == ["help", "export"]: return "SUBCOMMANDS:\n  object\n"
            if "help" in command: return "--legacy --path --format --output-path --id --type directory"
            if "get" in command: return json.dumps({"actions": {"_values": [{"actionResult": {"diagnosticsRef": {"id": {"_value": "exact-real-ref"}}}}]}})
            return ""
        result = receipt.export_diagnostics(self.bundle, self.root/"out", tool)
        self.assertIn("legacy", result["method"])
        self.assertIn("exact-real-ref", calls[-1])
        self.assertIn("directory", calls[-1])

    def test_unsupported_export_help_fails_without_guess(self):
        with self.assertRaisesRegex(receipt.EvidenceError, "Unsupported"):
            receipt.export_diagnostics(self.bundle, self.root/"out", lambda *_: "Unknown syntax")

    def test_bounded_export_timeout_failure(self):
        with patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("xcrun", 30)):
            with self.assertRaisesRegex(receipt.EvidenceError, "timed out"):
                receipt._run_tool(["xcrun"], receipt.time.monotonic()+60)

    def test_diagnostics_raw_text_only_and_identical_stream_dedup(self):
        directory = self.root/"logs"; directory.mkdir()
        for name in ("one", "two"): (directory/name).write_text(example()["runner.log"])
        self.assertEqual(len(receipt.read_diagnostics(directory)), 1)
        (directory/"binary").write_bytes(b"\x00PICKER_APP_TRACE")
        with self.assertRaisesRegex(receipt.EvidenceError, "binary"):
            receipt.read_diagnostics(directory)

    def test_invalid_historical_evidence_cannot_pass(self):
        old = "PICKER_APP_TRACE event=app-beautify-tap instance=root uptime_seconds=1752.767753 wall_seconds=1791513778.420096"
        with self.assertRaisesRegex(receipt.EvidenceError, "UUID"):
            receipt.validate_logs({"historical.log": old+"\n"+native("ViewDidAppear", 1)}, {RUN:(1,0)})

    def test_cli_failure_still_writes_invalid_evidence_receipt(self):
        path = self.root/"identity.json"; path.write_text(json.dumps(self.identity))
        out = self.root/"receipt.json"
        args = ["--xcresult", str(self.bundle), "--identity", str(path), "--app-binary", str(self.binary),
                "--expected-source-sha", SHA, "--expected-source-tree", TREE, "--expected-run", f"{RUN}:1:0", "--runner-log-timezone", "UTC", "--output", str(out),
                "--diagnostics-output", str(self.root/'retained')]
        with patch.object(receipt, "export_diagnostics", side_effect=receipt.EvidenceError("missing native exporter")):
            self.assertEqual(receipt.main(args), 1)
        self.assertEqual(json.loads(out.read_text())["status"], "invalid_evidence")

    def test_validation_failure_retains_exact_official_logs_before_error(self):
        path = self.root/'identity.json'; path.write_text(json.dumps(self.identity))
        out = self.root/'receipt.json'; retained = self.root/'retained'
        logs = example(); logs['app-stdout.log'] += '\n' + app('picker-coordinator-created', 1.15, instance=RUN)
        def official_export(bundle, destination):
            destination.mkdir()
            for filename, content in logs.items(): (destination/filename).write_text(content)
            return {'method': 'mocked official exporter, unit test only'}
        args = ['--xcresult', str(self.bundle), '--identity', str(path), '--app-binary', str(self.binary),
                '--expected-source-sha', SHA, '--expected-source-tree', TREE, '--expected-run', f'{RUN}:1:0',
                '--runner-log-timezone', 'UTC', '--output', str(out), '--diagnostics-output', str(retained)]
        with patch.object(receipt, 'export_diagnostics', side_effect=official_export):
            self.assertEqual(receipt.main(args), 1)
        result = json.loads(out.read_text())
        self.assertIn('Orphan', result['error'])
        manifest = json.loads((retained/'retained-manifest.json').read_text())
        self.assertEqual(manifest['identity'], self.identity)
        self.assertEqual(len(manifest['logs']), len(logs))
        for item in manifest['logs']:
            self.assertEqual((retained/item['path']).read_text(), logs[item['path']])
            self.assertEqual(receipt.sha256_file(retained/item['path']), item['sha256'])

    def test_retention_rejects_stale_unsafe_or_oversized_output(self):
        destination = self.root/'retained'
        receipt.retain_diagnostics(example(), destination, {}, self.identity)
        with self.assertRaisesRegex(receipt.EvidenceError, 'fresh'):
            receipt.retain_diagnostics(example(), destination, {}, self.identity)
        with self.assertRaisesRegex(receipt.EvidenceError, 'Unsafe'):
            receipt.retain_diagnostics({'../escape': 'bad'}, self.root/'unsafe', {}, self.identity)
        with patch.object(receipt, 'MAX_LOG_BYTES', 10):
            with self.assertRaisesRegex(receipt.EvidenceError, 'bound'):
                receipt.retain_diagnostics(example(), self.root/'oversized', {}, self.identity)


class ActualHistoricalFixtureTests(unittest.TestCase):
    def fixture(self):
        return (Path(__file__).parent / "tests" / "fixtures" / "run4-native-diagnostic.log").read_text()

    def test_native_parser_recognizes_three_real_appear_disappear_pairs(self):
        evidence = receipt.extract_native_events({"historical": self.fixture()})
        self.assertEqual([n["event"] for n in evidence], ["ViewDidAppear", "ViewDidDisappear"] * 3)
        self.assertTrue(all(n["pid"] == "44733" for n in evidence))
        self.assertTrue(all(n["prefix"]["pid"] == "44681" for n in evidence))

    def test_historical_second_native_point_and_ax_upper_remain_diagnostic(self):
        import re
        text = self.fixture()
        actions = re.findall(r"PICKER_APP_TRACE event=app-beautify-tap .*?uptime_seconds=([0-9.]+) wall_seconds=([0-9.]+)", text)
        second_uptime, second_wall = map(float, actions[1])
        appearances = [n for n in receipt.extract_native_events({"historical": text}) if n["event"] == "ViewDidAppear"]
        native_wall = receipt.prefix_wall(appearances[1]["prefix"], second_wall, timezone.utc)
        ax_end = float(re.search(r"PICKER_AX_QUERY iteration=2 property=isHittable .*?end_uptime_seconds=([0-9.]+)", text)[1])
        self.assertAlmostEqual(native_wall-second_wall, .707903862, places=6)
        self.assertAlmostEqual(ax_end-second_uptime, 3.1613435833333, places=9)
        self.assertGreater(ax_end-second_uptime, receipt.BUDGET_SECONDS)
        # No retroactive pass: original logs lack required identity/anchors.
        with self.assertRaises(receipt.EvidenceError):
            receipt.validate_logs({"historical": text}, {RUN: (3, 0)})


class ActualFailedRunFiveTests(unittest.TestCase):
    """Derived official failure samples; generated Photos identities sanitized."""
    def logs(self, phase):
        root = Path(__file__).parent / 'tests/fixtures'
        return {kind: (root/f'run5-{phase}-{kind}-diagnostic.log').read_text() for kind in ('app', 'runner')}

    def test_derived_stock_and_seeded_cold_identity_mismatch_stays_rejected(self):
        for phase in ('stock', 'seeded'):
            logs = self.logs(phase); traces, native_events, _ = receipt.parse_logs(logs)
            run = traces[0]['run']
            with self.assertRaisesRegex(receipt.EvidenceError, 'Orphan app presentation instance'):
                receipt.validate_logs(logs, {run: (3, 0) if phase == 'stock' else (2, 1)})
            self.assertEqual(len(native_events), 6)
            app_records = [x for x in traces if x['kind'] == 'PICKER_APP_TRACE']
            taps = [x['instance'] for x in app_records if x['event'] == 'app-beautify-tap']
            constructions = [x['instance'] for x in app_records if x['event'] == 'picker-construction-returned']
            self.assertNotEqual(taps[0], constructions[0])
            self.assertEqual(taps[1:], constructions[1:])
            selected = [x for x in app_records if x['event'] in ('picker-selected-identities', 'resolved-original-identities')]
            self.assertEqual(len(selected), 2 if phase == 'seeded' else 0)
            for record in selected:
                self.assertEqual(receipt.selected_identity(record), ['synthetic-fixture-composition-3'])

    def test_real_stock_third_input_to_hittable_overrun_stays_visible(self):
        logs = self.logs('stock'); traces, native_events, _ = receipt.parse_logs(logs)
        starts = [x for x in traces if x.get('event') == 'tap-command-start' and x['iteration'] == 3]
        start = receipt.one(starts, 'third action'); end = receipt.event(
            [x for x in traces if x.get('iteration') == 3], 'tap-command-returned')
        inputs = [(x, receipt.prefix_wall(x['prefix'], start['wall'], timezone.utc)) for x in receipt.extract_synthesis_events(logs)]
        _, input_wall = receipt.one([(x, w) for x, w in inputs if start['wall'] <= w <= end['wall']], 'third input')
        hit = receipt.one([x for x in traces if x['kind'] == 'PICKER_AX_QUERY' and x['iteration'] == 3 and x['property'] == 'isHittable'], 'third hit')
        self.assertAlmostEqual(hit['wall']-input_wall, 3.030480146, places=6)
        self.assertGreater(hit['wall']-input_wall, receipt.BUDGET_SECONDS)


class SourceIdentityAndPollingTests(unittest.TestCase):
    def test_presented_item_contains_immutable_action_id(self):
        source = (Path(__file__).resolve().parents[1]/'Celluloid/SwiftUI/PhoneRootView.swift').read_text()
        self.assertIn('case beautify(String), collage(String), privacy', source)
        self.assertIn('destination = .beautify(instance)', source)
        self.assertIn('case .beautify(let instance): PhotoSelectionFlowView(maximumSelection: 1, traceID: instance)', source)
        self.assertIn('case .collage(let instance): PhotoSelectionFlowView(maximumSelection: 4, traceID: instance)', source)
        self.assertNotIn('traceID: pickerPresentationID', source)

    def test_same_real_checks_start_immediately_with_unchanged_bound(self):
        source = (Path(__file__).resolve().parents[1]/'CelluloidUITests/CelluloidUITests.swift').read_text()
        fragment = source.split('private func observeSystemPicker',1)[1].split('func testAccessibilityHomeAndDeniedPicker',1)[0]
        for prop in ('exists','isEnabled','isHittable'):
            self.assertIn(f'measured("{prop}", {{ cancel.{prop} }})', fragment)
        self.assertIn('observationDeadline = ProcessInfo.processInfo.systemUptime + 3', fragment)
        self.assertLess(fragment.index('if observeUsablePicker()'),fragment.index('RunLoop.current.run'))
        self.assertNotIn('XCTWaiter.wait(for: [usablePicker]',fragment)
        self.assertIn('XCTAssertEqual(outcome, .completed',fragment)
        self.assertIn('start_uptime_seconds=',fragment)
        self.assertIn('start_wall_seconds=',fragment)


class FixtureManifestTests(unittest.TestCase):
    def manifest(self, baseline_count=6):
        baseline = [f"baseline-{i}" for i in range(baseline_count)]
        added = [f"fixture-{i}" for i in range(6)]
        filenames = ["celluloid-fixture.png", "celluloid-fixture-2.png"] + [f"celluloid-composition-{i}.png" for i in range(4)]
        return {"schema": "celluloid.swiftui.seeded-library.v1", "source_sha": SHA, "device_id": "synthetic-device", "run_id": "123", "run_attempt": "1",
                "authorization_read_write": "authorized", "baseline_asset_count": len(baseline), "seeded_asset_count": len(baseline)+6,
                "baseline_asset_ids": sorted(baseline), "seeded_asset_ids": sorted(baseline+added), "added_asset_ids": sorted(added),
                "fixture_count": 6, "baseline_id_set_preserved": True,
                "fixtures": [{"identifier": asset, "filename": name, "sha256": "c"*64, "width": 400, "height": 300, "creation_date_utc": "2026-10-09T00:00:00Z"} for asset, name in zip(added, filenames)]}

    def validate(self, manifest):
        identity = {"source_sha": SHA, "device_id": "synthetic-device", "ci_run_id": "123", "ci_run_attempt": "1"}
        return receipt.validate_fixture_manifest(manifest, identity)

    def test_actual_nonzero_or_zero_baseline_not_assumed(self):
        for count in (0, 6, 19):
            self.assertEqual(len(self.validate(self.manifest(count))), 6)

    def test_every_identity_binding_is_required(self):
        for field in ("source_sha", "device_id", "run_id", "run_attempt"):
            manifest = self.manifest(); manifest[field] = "wrong"
            with self.assertRaises(receipt.EvidenceError): self.validate(manifest)

    def test_bad_counts_permissions_baseline_or_fixture_count_fail(self):
        for field, value in (("baseline_asset_count", 0), ("seeded_asset_count", 6), ("fixture_count", 5), ("baseline_id_set_preserved", False), ("authorization_read_write", "limited")):
            manifest = self.manifest(); manifest[field] = value
            with self.assertRaises(receipt.EvidenceError): self.validate(manifest)

    def test_missing_baseline_extra_asset_and_duplicate_ids_fail(self):
        for field, mutation in (("seeded_asset_ids", lambda ids: ids[1:]), ("added_asset_ids", lambda ids: ids+["extra"]), ("baseline_asset_ids", lambda ids: ids+[ids[0]])):
            manifest = self.manifest(); manifest[field] = mutation(manifest[field])
            with self.assertRaises(receipt.EvidenceError): self.validate(manifest)

    def test_wrong_fixture_id_filename_hash_dimensions_fail(self):
        for field, value in (("identifier", "outside-new-assets"), ("filename", "not-controlled.png"), ("sha256", "bad"), ("width", 0), ("height", False), ("creation_date_utc", ""), ("creation_date_utc", "not-a-date"), ("creation_date_utc", "2026-10-09T00:00:00")):
            manifest = self.manifest(); manifest["fixtures"][0][field] = value
            with self.assertRaises(receipt.EvidenceError): self.validate(manifest)


class RepeatedPresentationTests(unittest.TestCase):
    def repeated(self, spacing=10):
        global WALL, UPTIME
        baseline_wall, baseline_uptime = WALL, UPTIME
        app_lines, runner_lines = [], []
        try:
            for iteration in range(1, 4):
                WALL = baseline_wall + (iteration-1)*spacing
                UPTIME = baseline_uptime + (iteration-1)*spacing
                logs = example()
                this_instance = f"d1203fb7-070b-4b3d-b907-e46963f2e65{iteration}"
                app_lines.append(logs["app-stdout.log"].replace(INSTANCE, this_instance))
                for line in logs["runner.log"].splitlines():
                    if iteration != 1 and "event=run-begin" in line: continue
                    if iteration != 3 and "event=run-end" in line: continue
                    runner_lines.append(line.replace("iteration=1", f"iteration={iteration}"))
        finally:
            WALL, UPTIME = baseline_wall, baseline_uptime
        return {"app": "\n".join(app_lines), "runner": "\n".join(runner_lines)}

    def test_three_serial_presentations_and_reused_public_object_address(self):
        result = receipt.validate_logs(self.repeated(), {RUN: (3, 0)})
        self.assertEqual(result["status"], "passed")
        self.assertEqual(len(result["presentations"]), 3)
        self.assertEqual(len({r["presentation_id"] for r in result["presentations"]}), 3)

    def test_overlapping_presentations_fail(self):
        with self.assertRaises(receipt.EvidenceError):
            receipt.validate_logs(self.repeated(spacing=2), {RUN: (3, 0)})


if __name__ == "__main__":
    unittest.main()
