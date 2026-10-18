"""Portable route/scope tests. No native command is executed by this file."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import run_canonical_stock_acceptance as stock
import run_picker_acceptance as picker
import run_swiftui_acceptance as full

SOURCE = 'a' * 40
TREE = 'b' * 40


class StockRouteTests(unittest.TestCase):
    def env(self):
        return {'GITHUB_REPOSITORY': '100mango/Celluloid', 'GITHUB_REF': stock.BRANCH,
                'GITHUB_EVENT_NAME': 'push', 'GITHUB_RUN_ATTEMPT': '1',
                'RUNNER_ENVIRONMENT': 'github-hosted',
                'DEVELOPER_DIR': '/Applications/Xcode_27.app/Contents/Developer',
                'GITHUB_SHA': SOURCE, 'GITHUB_WORKFLOW_SHA': SOURCE,
                'CELLULOID_PREVIEW_CONTINUATION': ''}

    def git(self, *args):
        return {('rev-parse', 'HEAD'): SOURCE, ('rev-parse', 'HEAD^{tree}'): TREE,
                ('merge-base', stock.BASE, SOURCE): stock.BASE,
                ('diff', '--name-only', stock.BASE, SOURCE, '--'): '\n'.join(sorted(stock.CHANGED)),
                ('diff', '--name-only', 'HEAD', '--'): ''}[args]

    def test_exact_reviewed_route_and_scope(self):
        result = stock.validate_route(self.env(), self.git)
        self.assertEqual(result['source_sha'], SOURCE)
        self.assertEqual(result['source_tree'], TREE)
        self.assertEqual(result['changed_paths'], sorted(stock.CHANGED))

    def test_wrong_runner_source_branch_and_rerun_fail_before_native_dispatch(self):
        for key, value in [('RUNNER_ENVIRONMENT', 'self-hosted'), ('GITHUB_RUN_ATTEMPT', '2'),
                ('GITHUB_REF', 'refs/heads/master'), ('GITHUB_REPOSITORY', 'other/Celluloid'),
                ('GITHUB_WORKFLOW_SHA', 'c' * 40), ('GITHUB_EVENT_NAME', 'workflow_dispatch'),
                ('DEVELOPER_DIR', '/other/Xcode'), ('CELLULOID_PREVIEW_CONTINUATION', 'yes')]:
            env = self.env(); env[key] = value
            with self.assertRaises(ValueError): stock.validate_route(env, self.git)

    def test_product_change_dirty_checkout_and_foreign_baseline_are_rejected(self):
        for command, value in [
                (('merge-base', stock.BASE, SOURCE), 'c' * 40),
                (('rev-parse', 'HEAD'), 'c' * 40),
                (('diff', '--name-only', 'HEAD', '--'), 'Celluloid/SwiftUI/PhoneRootView.swift'),
                (('diff', '--name-only', stock.BASE, SOURCE, '--'), '\n'.join(sorted(stock.CHANGED | {'Celluloid/SwiftUI/PhoneRootView.swift'}))),
                (('diff', '--name-only', stock.BASE, SOURCE, '--'), '\n'.join(sorted(stock.CHANGED - {'Scripts/picker_native_receipt.py'})))]:
            with self.assertRaises(ValueError):
                stock.validate_route(self.env(), lambda *args: value if args == command else self.git(*args))

    def test_original_four_method_selection_and_receipt_are_reused(self):
        self.assertEqual(picker.STOCK, [
            'CelluloidUITests/CelluloidUITests/testBeautifyOpensSystemPickerAndCancelsRepeatedly',
            'CelluloidUITests/CelluloidUITests/testPrivacyPolicyEntryRemainsAccessibleAndCanClose',
            'CelluloidUITests/PhoneEntryDesignUITests'])
        self.assertIs(stock.StockAcceptance.picker, full.Acceptance.picker)
        self.assertIs(stock.StockAcceptance.cleanup, full.Acceptance.cleanup)
        self.assertEqual(picker.receipt.BUDGET_SECONDS, 3.0)

    def test_no_full_or_seeded_or_photos_native_execution(self):
        import inspect
        source = inspect.getsource(stock.StockAcceptance.run)
        self.assertEqual(source.count("self.picker('stock')"), 1)
        for forbidden in ('self.photos(', "self.picker('seeded')", "'test-without-building'",
                          "'swift', 'test'", 'super().run()', 'deploy_hosted_app('):
            self.assertNotIn(forbidden, source)
        self.assertEqual(source.count("'build-for-testing'"), 1)

    def test_job_clock_and_no_automatic_retries(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(full, 'OUT', Path(folder)), patch.dict(stock.os.environ, {'CELLULOID_PREVIEW_CONTINUATION': ''}):
            gate = stock.StockAcceptance()
            self.assertEqual(gate.work_seconds, 1800)
            self.assertEqual(gate.deadline - gate.started, 1800)
        path = Path(__file__).resolve().parents[1] / '.github/workflows/canonical-stock-readiness.yml'
        workflow = path.read_text()
        self.assertIn('runs-on: xcode-27', workflow)
        self.assertIn('timeout-minutes: 45', workflow)
        self.assertIn('github.run_attempt == 1', workflow)
        self.assertIn('persist-credentials: false', workflow)
        self.assertNotIn('workflow_dispatch', workflow)

    def test_late_or_negative_wrapper_is_uncertain(self):
        for code, moments in [(-9, [0, 1]), (0, [0, 11])]:
            with tempfile.TemporaryDirectory() as folder, patch.object(full, 'OUT', Path(folder)), patch.dict(stock.os.environ, {'CELLULOID_PREVIEW_CONTINUATION': ''}):
                gate = stock.StockAcceptance()
                with patch.object(full.Acceptance, 'command', return_value=(code, '')), patch.object(stock.time, 'monotonic', side_effect=moments):
                    with self.assertRaises(ValueError): gate.command('bounded', ['unused'], 10)
                self.assertTrue(gate.uncertain)

    def test_missing_command_completion_receipt_is_uncertain(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(full, 'OUT', Path(folder)), patch.dict(stock.os.environ, {'CELLULOID_PREVIEW_CONTINUATION': ''}):
            gate = stock.StockAcceptance()
            with patch.object(full.Acceptance, 'command', side_effect=RuntimeError('interrupted')):
                with self.assertRaises(RuntimeError): gate.command('bounded', ['unused'], 10)
            self.assertTrue(gate.uncertain)

    def result(self, *, uncertain=False, accepted=True, elapsed=100, warnings=0):
        fake = SimpleNamespace(
            run=lambda: None, verify_after=lambda: None, cleanup=lambda: None,
            started=0, work_seconds=1800, stock_accepted=accepted, failures=[],
            device=None, uncertain=uncertain, source=SOURCE, source_tree=TREE,
            warning_report={'other_warning_review_count': warnings})
        with tempfile.TemporaryDirectory() as folder, patch.object(full, 'OUT', Path(folder)), \
                patch.object(stock, 'StockAcceptance', return_value=fake), \
                patch.object(stock.time, 'monotonic', return_value=elapsed), \
                patch.object(stock.signal, 'signal'):
            code = stock.main()
            result = json.loads((Path(folder) / 'canonical-stock-acceptance.json').read_text())
        return code, result

    def test_passing_phase_cannot_relabel_old_full_or_release(self):
        code, result = self.result()
        self.assertEqual(code, 0)
        self.assertTrue(result['canonical_stock_phase_accepted'])
        self.assertEqual(result['historical_full_38681904126_status'], 'failed')
        self.assertFalse(result['all_required_phases_accepted'])
        self.assertFalse(result['release_qualification'])
        self.assertIn('Photos', result['not_executed'])

    def test_uncertain_cleanup_failed_stock_and_total_overrun_remain_failed(self):
        for kwargs in ({'uncertain': True}, {'accepted': False}, {'elapsed': 1981}):
            code, result = self.result(**kwargs)
            self.assertEqual(code, 1)
            self.assertEqual(result['status'], 'failed')
            self.assertFalse(result['canonical_stock_phase_accepted'])

    def test_runtime_warning_review_survives_passing_stock_counts(self):
        code, result = self.result(warnings=1)
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'review_required')
        self.assertTrue(result['runtime_warning_review_required'])


if __name__ == '__main__':
    unittest.main()
