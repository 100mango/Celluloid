#!/usr/bin/env python3
"""Offline contracts only; no Swift compilation, Simulator, or qualification claim."""
import copy, json, math, tempfile, unittest, uuid, os, time
from pathlib import Path
import vision_passive_focus as focus

NONCE = '45D9E626-01A4-4026-B26C-719E3E351A4E'
LAYER = 'layer.02C93E40-7275-4E2B-8BB6-13DE8D86F1B7'


def timeline():
    base = {'schema': 'Celluloid.VisionFocusPassive.1', 'nonce': NONCE, 'mode': 'target', 'pid': 123}
    rows = [dict(base, seq=1, event='start', unix_seconds=1001, system_uptime=1, initial_source_count=1, initial_overlay_count=0),
            dict(base, seq=2, event='mapping_resolved', unix_seconds=1002, system_uptime=2,
                 candidate_count=1, mapping_source='exact_native_identifier', exact_identifier_node_count=1,
                 matched_identifier='editor.bubble-text', mapped_node_text_view_count=1, view_lifetime=1)]
    for seq, uptime in [(3, 4), (4, 6), (5, 8)]:
        rows.append(dict(base, seq=seq, event='snapshot', unix_seconds=1000+uptime, system_uptime=uptime,
                         candidate_count=1, mapping_source='exact_native_identifier', view_lifetime=1,
                         is_first_responder=True, can_become_first_responder=True, is_editable=True,
                         is_selectable=True, has_window=True, window_is_key=True, text_synthetic='Hello',
                         window_lifetime=1, scene_lifetime=1, ancestor_visible=True,
                         ancestor_interactable=True, ancestor_visibility_complete=True,
                         view_is_hidden=False, view_alpha=1.0, view_is_user_interaction_enabled=True))
    return rows


def raw(rows): return b''.join(focus.packed(r).replace(b'\n', b'') + b'\n' for r in rows)


def marker(stage, mode='target', uptime=5):
    row = {'schema': 'Celluloid.VisionFocusUI.1', 'stage': stage, 'mode': mode, 'nonce': NONCE,
           'fixture': 'VisionFocusTarget' if mode == 'target' else 'VisionFocusControl',
           'unix_seconds': uptime+1000, 'system_uptime': uptime, 'runner_pid': 456,
           'native_mapping_gate': 'posthoc_only'}
    if stage not in {'before_launch', 'before_terminate'}: row['layer_identifier'] = LAYER
    return row


def log(rows): return '\n'.join('VISION_PASSIVE_FOCUS_UI_JSON ' + json.dumps(r) for r in rows)


class FocusContracts(unittest.TestCase):
    def test_closed_config_only(self):
        value = focus.decode(focus.read(focus.ROOT / focus.CONFIG, 16384))
        value['READY'] = False  # Test both states independently of activation state.
        focus.config(value, False)
        with self.assertRaises(ValueError): focus.config(value)
        value['READY'] = True; focus.config(value)

    def test_no_qualification_config(self):
        value = focus.decode(focus.read(focus.ROOT / focus.CONFIG, 16384)); value['READY'] = True
        for key, new in [('qualification_eligible', True), ('maximum_additional_spend_usd', 1), ('ui_seconds', 601),
                         ('whole_seconds', 1801), ('automatic_rerun_allowed', True), ('diagnostic_only', False), ('READY', 1)]:
            bad = dict(value); bad[key] = new
            with self.subTest(key=key), self.assertRaises(ValueError): focus.config(bad)

    def test_original_sources_restore_exactly(self):
        for rel in focus.MODIFIED:
            actual = (focus.ROOT / rel).read_bytes(); baseline = focus.git('show', focus.BASE + ':' + rel)
            self.assertEqual(focus.inverse(actual), baseline)
        ui = (focus.ROOT / focus.MODIFIED[1]).read_bytes()
        self.assertTrue(ui.startswith(focus.git('show', focus.BASE + ':' + focus.MODIFIED[1])))

    def test_minimal_ui_source(self):
        ui = (focus.ROOT / focus.MODIFIED[1]).read_text().split('// VISION_PASSIVE_FOCUS_BEGIN:ui-tests\n', 1)[1]
        self.assertEqual(ui.count('.typeText("A")'), 1)
        self.assertEqual(focus.METHODS, ('testVisionPassiveFocus01Target', 'testVisionPassiveFocus02Control'))
        for name in focus.METHODS: self.assertIn('func ' + name + '() throws', ui)
        self.assertNotIn('for mode in ["target", "control"]', ui)
        self.assertIn('continueAfterFailure = true', ui)
        for forbidden in ['.typeText("B")', 'XCTExpectFailure', '.screenshot(', '.paste(', 'UIPasteboard', 'becomeFirstResponder(', 'CFNotificationCenter']:
            self.assertNotIn(forbidden, ui)

    def test_passive_app_source(self):
        source = (focus.ROOT / focus.MODIFIED[0]).read_text()
        added = source[source.index('// VISION_PASSIVE_FOCUS_BEGIN:implementation'):]
        for forbidden in ['becomeFirstResponder(', 'resignFirstResponder(', 'endEditing(', 'insertText(', 'sendAction(', 'value(forKey:', 'CFNotificationCenter', '.delegate =', '.selectedRange =']:
            self.assertNotIn(forbidden, added)
        for required in ['view.isFirstResponder', 'view.isEditable', 'view.isSelectable', 'weak var textView',
                         'mapping_unresolved', 'exact_native_identifier', 'withoutOverwriting', 'maximumBytes = 524288']:
            self.assertIn(required, added)

    def test_deadlines_low_high_and_one_ulp(self):
        for start in (17.123456789, 8000000.123456789):
            at = start + focus.LATEST_UI_START
            self.assertEqual(focus.admit_ui(start, at), start + focus.NATIVE_SECONDS - 165)
            with self.assertRaises(ValueError): focus.admit_ui(start, math.nextafter(at, math.inf))
            self.assertEqual(focus.admit_ui(start, start), start + focus.NATIVE_SECONDS - 165)
        for bad in (True, float('nan'), float('inf'), -1):
            with self.assertRaises(ValueError): focus.admit_ui(bad, 1)

    def test_clock_identity_and_expiry(self):
        env = {'GITHUB_SHA': 'a'*40, 'GITHUB_RUN_ID': '12'}
        value = dict(schema='Celluloid.VisionPassiveFocusClock.1', control_sha='a'*40,
                     run_id='12', run_attempt='1', started_monotonic=10.0, started_unix=1000.0)
        focus.clock(value, env, 11)
        with self.assertRaises(ValueError): focus.clock(value, env, 1750)
        value['run_attempt'] = '2'
        with self.assertRaises(ValueError): focus.clock(value, env, 11)

    def test_timeline_without_stop_and_without_image_is_valid(self):
        rows = focus.validate_timeline(raw(timeline()), NONCE, 'target')
        result = focus.interpret(rows, [marker('before_A'), marker('after_A', uptime=7)])
        self.assertTrue(result['direct_evidence_usable']); self.assertEqual(result['visual_state'], 'unknown')
        self.assertFalse(result['qualification_eligible']); self.assertFalse(result['product_cause_proven'])

    def test_timeline_identity_strict(self):
        for field, value in [('nonce', str(uuid.uuid4())), ('mode', 'control'), ('pid', True), ('seq', 8), ('system_uptime', float('inf'))]:
            rows = timeline(); rows[2][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): focus.validate_timeline(raw(rows), NONCE, 'target')

    def test_mapping_requires_exact_native_proof(self):
        for field, value in [('candidate_count', 2), ('candidate_count', True), ('mapping_source', 'AX_first'),
                             ('matched_identifier', 'other'), ('mapped_node_text_view_count', 2), ('view_lifetime', 0)]:
            rows = timeline(); rows[1][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): focus.validate_timeline(raw(rows), NONCE, 'target')

    def test_snapshot_must_follow_mapped_lifetime(self):
        rows = timeline(); rows[2]['view_lifetime'] = 2
        with self.assertRaises(ValueError): focus.validate_timeline(raw(rows), NONCE, 'target')
        rows = timeline(); rows[2]['is_first_responder'] = 1
        with self.assertRaises(ValueError): focus.validate_timeline(raw(rows), NONCE, 'target')

    def test_unknown_mapping_is_inconclusive(self):
        rows = timeline(); rows.append(dict(rows[0], seq=6, event='mapping_unresolved', system_uptime=9, unix_seconds=1009))
        result = focus.interpret(focus.validate_timeline(raw(rows), NONCE, 'target'), [marker('before_A'), marker('after_A', uptime=7)])
        self.assertFalse(result['mapping_proven']); self.assertFalse(result['direct_evidence_usable'])

    def test_missing_or_stale_key_window_is_inconclusive(self):
        rows = focus.validate_timeline(raw(timeline()), NONCE, 'target')
        self.assertFalse(focus.interpret(rows, [])['direct_evidence_usable'])
        self.assertFalse(focus.interpret(rows, [marker('before_A', uptime=20), marker('after_A', uptime=21)])['direct_evidence_usable'])

    def test_early_disappearance_and_truncated_heartbeat_are_inconclusive(self):
        rows = timeline()[:3]
        rows.append(dict(rows[0], seq=4, event='stop', reason='inspector_disappeared', system_uptime=4.5, unix_seconds=1004.5))
        result = focus.interpret(focus.validate_timeline(raw(rows), NONCE, 'target'), [marker('before_A'), marker('after_A', uptime=94)])
        self.assertFalse(result['direct_evidence_usable']); self.assertTrue(result['critical_window_capped_or_stopped'])
        self.assertFalse(focus.interpret(timeline()[:3], [marker('before_A'), marker('after_A', uptime=7)])['direct_evidence_usable'])

    def test_critical_gap_and_lifetime_change_are_inconclusive(self):
        rows = timeline(); rows[-1].update(system_uptime=99, unix_seconds=1099)
        result = focus.interpret(rows, [marker('before_A'), marker('after_A', uptime=98)])
        self.assertFalse(result['direct_evidence_usable']); self.assertGreater(result['maximum_critical_sample_gap_seconds'], 2.5)
        rows = timeline(); rows[-1]['view_lifetime'] = 2
        self.assertFalse(focus.interpret(rows, [marker('before_A'), marker('after_A', uptime=7)])['direct_evidence_usable'])
        for key, value in [('window_lifetime', 2), ('scene_lifetime', 2), ('ancestor_visible', False),
                           ('ancestor_interactable', False), ('ancestor_visibility_complete', False)]:
            rows = timeline(); rows[-1][key] = value
            with self.subTest(key=key):
                self.assertFalse(focus.interpret(rows, [marker('before_A'), marker('after_A', uptime=7)])['direct_evidence_usable'])

    def test_synthetic_text_only(self):
        rows = timeline(); rows[2]['text_synthetic'] = 'unexpected private text'
        with self.assertRaises(ValueError): focus.validate_timeline(raw(rows), NONCE, 'target')
        rows[2].update(text_synthetic='redacted', text_is_synthetic=False)
        focus.validate_timeline(raw(rows), NONCE, 'target')

    def test_partial_timeline_rejected(self):
        with self.assertRaises(ValueError): focus.validate_timeline(raw(timeline())[:-1], NONCE, 'target')
        with self.assertRaises(ValueError): focus.validate_timeline(b'{}\n' * (focus.CAP//3+1), NONCE, 'target')

    def test_ui_marker_order_and_single_key(self):
        stages = ['before_launch', 'before_tap', 'after_tap', 'before_A', 'after_A', 'observed_after_A', 'before_terminate']
        rows = [marker(s, arm, i+1+10*n) for n, arm in enumerate(('target','control')) for i,s in enumerate(stages)]
        result = focus.ui_markers(log(rows), NONCE)
        self.assertEqual(len(result['target']), 7); self.assertEqual(len(result['control']), 7)
        for bad in [rows[7:] + rows[:7], rows[:4] + [rows[3]] + rows[4:]]:
            with self.assertRaises(ValueError): focus.ui_markers(log(bad), NONCE)
        with self.assertRaises(ValueError): focus.ui_markers(log([rows[0], rows[3]]), NONCE)
        rows[3]['native_mapping_gate'] = 'ack'
        with self.assertRaises(ValueError): focus.ui_markers(log(rows), NONCE)

    def test_fixture_copies_exclusive_and_equal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); original = root/'Documents/VisionRemaining.celluloid'; original.mkdir(parents=True)
            files = []
            for name, data in [('recipe.json', b'{"overlays":[]}'), ('x.image', b'generated')]:
                (original/name).write_bytes(data); files.append({'name':name,'bytes':len(data),'sha256':focus.sha(data)})
            result = focus.copy_fixtures({'files': files}, root)
            self.assertEqual(result['target']['files'], result['control']['files'])
            with self.assertRaises(FileExistsError): focus.copy_fixtures({'files': files}, root)

    def test_checkout_preserves_three_generation_source_lineage(self):
        workflow = (focus.ROOT/focus.WORKFLOW).read_text()
        self.assertIn('fetch-depth: 3', workflow)
        self.assertNotEqual(focus.PARENT, focus.BASE)
        self.assertEqual(focus.git('show', '-s', '--format=%P', focus.PARENT).decode().strip(), focus.BASE)

    def test_current_container_exact_owned_device_only(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory).resolve(); device = str(uuid.uuid4()).upper()
            parent = home/'Library/Developer/CoreSimulator/Devices'/device/'data/Containers/Data/Application'
            stale = parent/str(uuid.uuid4()).upper(); stale.mkdir(parents=True)
            current = parent/str(uuid.uuid4()).upper(); current.mkdir()
            stale.rmdir() # Match the observed stale producer UUID without guessing why it vanished.
            self.assertEqual(focus.owned_container(str(current), device, home), current)
            with self.assertRaises(FileNotFoundError): focus.owned_container(str(stale), device, home)
            with self.assertRaises((OSError, ValueError)): focus.owned_container(str(current), str(uuid.uuid4()), home)
            wrong = parent/'not-a-uuid'; wrong.mkdir()
            with self.assertRaises(ValueError): focus.owned_container(str(wrong), device, home)

    def test_current_container_query_follows_ui_before_cleanup(self):
        source = (focus.ROOT/'Scripts/vision_passive_focus.py').read_text()
        ui = source.index("report['ui_exit_code'] =")
        query = source.index("'current-container', 45")
        timeline = source.index("path = current_container / 'Library/Caches/CelluloidVisionFocus'")
        cleanup = source.index("for action in ('shutdown', 'delete'):")
        self.assertTrue(ui < query < timeline < cleanup)
        self.assertEqual(source.count("'current-container', 45"), 1)
        self.assertIn('deadline=native_end - 120', source)

    def empty_receipt(self):
        return dict(label='focus-offline-1-boot', log='boot.log', log_bytes=0, bytes_read=0,
                    log_sha256=focus.sha(b''), return_code=0, finalized=True, child_reaped=True,
                    pipe_eof=True, timed_out=False, overflow=False, cleanup_error=None)

    def test_owned_empty_log_is_verified_without_weakening_reader(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory).resolve()/'boot.log'; p.write_bytes(b'')
            self.assertEqual(focus.empty_command_log(p, self.empty_receipt()), b'')
            with self.assertRaises(ValueError): focus.read(p, 1024)
            p.write_bytes(b'x')
            with self.assertRaises(ValueError): focus.empty_command_log(p, self.empty_receipt())

    def test_empty_log_receipts_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory).resolve()/'boot.log'; p.write_bytes(b'')
            for key, value in [('log_bytes', False), ('bytes_read', False), ('log_sha256', '0'*64),
                               ('return_code', 65), ('finalized', False), ('pipe_eof', False),
                               ('timed_out', True), ('overflow', True), ('cleanup_error', 'unknown'), ('log', 'other.log')]:
                receipt = self.empty_receipt(); receipt[key] = value
                with self.subTest(key=key), self.assertRaises(ValueError): focus.empty_command_log(p, receipt)

    def test_empty_log_symlinks_and_hardlinks_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); real = root/'real'; real.mkdir(); p = real/'boot.log'; p.write_bytes(b'')
            alias = root/'alias'; alias.symlink_to(real, target_is_directory=True)
            with self.assertRaises((OSError, ValueError)): focus.empty_command_log(alias/'boot.log', self.empty_receipt())
            link = root/'boot.log'; link.symlink_to(p)
            with self.assertRaises((OSError, ValueError)): focus.empty_command_log(link, self.empty_receipt())
            os.link(p, root/'hard')
            with self.assertRaises(ValueError): focus.empty_command_log(p, self.empty_receipt())

    def test_collect_retains_verified_empty_command_and_failure_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory).resolve(); env = {'RUNNER_TEMP':str(temp), 'GITHUB_SHA':'a'*40, 'GITHUB_RUN_ID':'1'}
            c = dict(schema='Celluloid.VisionPassiveFocusClock.1', control_sha='a'*40, run_id='1', run_attempt='1',
                     started_monotonic=time.monotonic(), started_unix=time.time())
            (temp/focus.CLOCK).write_bytes(focus.packed(c))
            for phase in ('before', 'after'): (temp/('focus-source-'+phase+'.json')).write_bytes(focus.packed({'offline': True}))
            report = {'control_sha':'a'*40, 'qualification_eligible':False, 'commands':[self.empty_receipt()],
                      'arms':{'target':{'interpretation':'inconclusive'}}, 'ui_exit_code':65}
            (temp/'focus-report.json').write_bytes(focus.packed(report)); (temp/'boot.log').write_bytes(b'')
            manifest = focus.collect(env); output = temp/'focus-evidence'
            self.assertEqual((output/'boot.log').read_bytes(), b'')
            entry = next(r for r in manifest['files'] if r['name']=='boot.log')
            self.assertEqual(entry, {'name':'boot.log','bytes':0,'sha256':focus.sha(b''),'kind':'verified-empty-command-output'})
            self.assertEqual(focus.decode((output/'focus-report.json').read_bytes())['ui_exit_code'], 65)
            self.assertTrue((output/'manifest.json').is_file())

    def test_missing_control_or_after_A_never_becomes_complete(self):
        rows = [marker('before_launch', uptime=1), marker('before_tap', uptime=2), marker('after_tap', uptime=3), marker('before_A', uptime=4)]
        result = focus.ui_markers(log(rows), NONCE)
        self.assertEqual(result['control'], [])
        self.assertFalse(focus.interpret(timeline(), result['target'])['direct_evidence_usable'])
        self.assertFalse(focus.interpret(timeline(), result['control'])['direct_evidence_usable'])

    def test_strict_reader_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); (root/'real').write_text('x'); (root/'alias').symlink_to(root/'real')
            self.assertEqual(focus.read(root/'real', 1), b'x')
            with self.assertRaises((OSError, ValueError)): focus.read(root/'alias', 1)

if __name__ == '__main__': unittest.main()
