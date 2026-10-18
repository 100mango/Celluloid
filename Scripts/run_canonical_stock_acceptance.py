#!/usr/bin/env python3
"""Repair only the failed canonical stock-picker phase, using its original runner.

One fresh hosted job, one build, one owned simulator and one four-method stock
invocation. This does not rerun or retroactively qualify historical Full/Photos.
"""
from pathlib import Path
import json
import os
import re
import signal
import subprocess
import sys
import time

import run_swiftui_acceptance as full
from run_picker_acceptance import build_binding, check_build

BASE = '8cea3da33309fd00c34a35ceec751cb9366c207f'
BRANCH = 'refs/heads/cell-ios-canonical-readiness-20261018'
CHANGED = {
    'CelluloidUITests/CelluloidUITests.swift',
    'Scripts/picker_native_receipt.py',
    'Scripts/test_picker_native_receipt.py',
    'Scripts/run_canonical_stock_acceptance.py',
    'Scripts/test_canonical_stock_acceptance.py',
    '.github/workflows/canonical-stock-readiness.yml',
}
need = full.require


def validate_route(env, git):
    need(env.get('GITHUB_REPOSITORY') == '100mango/Celluloid'
         and env.get('GITHUB_REF') == BRANCH
         and env.get('GITHUB_EVENT_NAME') == 'push'
         and env.get('GITHUB_RUN_ATTEMPT') == '1', 'Wrong stock repair route or automatic retry')
    need(env.get('RUNNER_ENVIRONMENT') == 'github-hosted', 'Fresh hosted runner required')
    need(env.get('DEVELOPER_DIR') == '/Applications/Xcode_27.app/Contents/Developer', 'Wrong Xcode')
    need(not env.get('CELLULOID_PREVIEW_CONTINUATION'), 'No preview continuation in stock repair')
    source = env.get('GITHUB_SHA', '')
    need(re.fullmatch('[0-9a-f]{40}', source) and env.get('GITHUB_WORKFLOW_SHA') == source, 'Wrong workflow source')
    need(git('rev-parse', 'HEAD') == source, 'Wrong checkout')
    need(git('merge-base', BASE, source) == BASE, 'Wrong reviewed baseline')
    need(set(git('diff', '--name-only', BASE, source, '--').splitlines()) == CHANGED, 'Unexpected source changes')
    need(git('diff', '--name-only', 'HEAD', '--') == '', 'Dirty tracked source')
    return {'source_sha': source, 'source_tree': git('rev-parse', 'HEAD^{tree}'),
            'baseline_sha': BASE, 'changed_paths': sorted(CHANGED)}


class StockAcceptance(full.Acceptance):
    def __init__(self):
        super().__init__()
        self.work_seconds = 1800
        self.deadline = self.started + self.work_seconds
        self.source_proof = None
        self.binding = None
        self.binary = None
        self.stock_accepted = False
        self.warning_report = None

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=full.ROOT, text=True, timeout=10).strip()

    def command(self, name, command, seconds, **kwargs):
        # Preserve the canonical runner, and fail closed on a negative child
        # exit or a wrapper that returned beyond its advertised phase ceiling.
        began = time.monotonic()
        try:
            code, log = super().command(name, command, seconds, **kwargs)
        except BaseException:
            if not self.events or self.events[-1].get('phase') != name:
                self.uncertain = True
            raise
        if type(code) is not int or code < 0 or time.monotonic() - began > seconds:
            self.uncertain = True
            raise ValueError('Unknown or over-deadline command outcome: ' + name)
        return code, log

    def run(self):
        need(sys.platform == 'darwin', 'Native stock gate requires xcode-27')
        self.source_proof = validate_route(os.environ, self.git)
        self.source_tree = self.source_proof['source_tree']
        full.save(full.OUT / 'stock-source-before.json', self.source_proof)
        _, version = self.command('toolchain', ['xcodebuild', '-version'], 30)
        need(version.strip().splitlines() == ['Xcode 27.0', 'Build version 27A266a'], 'Wrong stable Xcode')
        for filename in ['test_picker_native_receipt.py', 'test_canonical_stock_acceptance.py']:
            self.command(filename[:-3], [sys.executable, '-S', 'Scripts/' + filename], 30)
        _, before_text = self.command('devices-before', ['xcrun', 'simctl', 'list', 'devices', 'available', '-j'], 20, simulator=True)
        before = full.extract_json(before_text, 'devices')
        full.save(full.OUT / 'devices-before.json', before)
        try:
            _, created = self.command('create-owned-device', [sys.executable, 'Scripts/select_test_devices.py', 'iPhone SE (3rd generation)'], 60, simulator=True)
            matches = re.findall(r'^([0-9A-Fa-f-]{36}) iPhone SE \(3rd generation\)$', created, re.M)
            need(len(matches) == 1, 'Missing or ambiguous creation receipt; do not retry')
            device = matches[0]
            _, after_text = self.command('devices-after-create', ['xcrun', 'simctl', 'list', 'devices', 'available', '-j'], 20, simulator=True)
            after = full.extract_json(after_text, 'devices')
            full.save(full.OUT / 'devices-after-create.json', after)
            owner = full.owner_receipt(before, after, device, os.environ, self.source, self.started, self.deadline)
        except BaseException:
            self.uncertain = True
            raise
        self.device = device
        full.save(full.OUT / 'owned-simulator.json', owner)
        base = ['xcodebuild', '-project', 'Celluloid.xcodeproj', '-scheme', 'Celluloid', '-configuration', 'Debug',
                '-destination', 'platform=iOS Simulator,id=' + device, '-derivedDataPath', str(full.DERIVED),
                'CODE_SIGNING_ALLOWED=NO', 'CODE_SIGNING_REQUIRED=NO', 'COMPILER_INDEX_STORE_ENABLE=NO']
        self.command('build', [*base, '-jobs', '2', 'build-for-testing'], 720, simulator=True)
        self.binary = full.DERIVED / 'Build/Products/Debug-iphonesimulator/Celluloid.app/Celluloid'
        self.binding = build_binding(self.binary, self.source, self.source_tree)
        full.save(full.OUT / 'build-binding.json', self.binding)
        self.command('boot', ['xcrun', 'simctl', 'boot', device], 60, simulator=True)
        self.command('bootstatus', ['xcrun', 'simctl', 'bootstatus', device, '-b'], 300, simulator=True)
        # The canonical stock runner retains all four methods, exact XCTest
        # accounting, three picker cycles, native receipts and actual Cancel.
        code = self.picker('stock')
        check_build(self.binding, self.binary, self.source, self.source_tree)
        receipt = json.loads((full.OUT / 'picker-stock-acceptance.json').read_text())
        self.stock_accepted = code == 0 and receipt.get('accepted') is True and not self.uncertain
        need(self.stock_accepted, 'Canonical stock phase did not pass')
        self.warning_report = json.loads((full.OUT / 'picker-stock-runtime-warnings.json').read_text())
        need(type(self.warning_report.get('other_warning_review_count')) is int
             and self.warning_report['other_warning_review_count'] >= 0,
             'Missing canonical runtime-warning accounting')

    def verify_after(self):
        if self.source_proof is not None:
            after = validate_route(os.environ, self.git)
            need(after == self.source_proof, 'Source changed during stock repair')
            full.save(full.OUT / 'stock-source-after.json', after)
        if self.binding is not None:
            check_build(self.binding, self.binary, self.source, self.source_tree)


def main():
    os.chdir(full.ROOT)
    os.environ['TZ'] = 'UTC'
    if hasattr(time, 'tzset'): time.tzset()
    gate = StockAcceptance()
    error = None
    def stop(signum, frame):
        gate.uncertain = True
        raise KeyboardInterrupt('Canonical stock repair interrupted')
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        gate.run()
    except BaseException as failure:
        error = str(failure)
    finally:
        try:
            gate.verify_after()
        except BaseException as failure:
            error = error or str(failure)
        try:
            gate.cleanup()  # Existing helper acts only on this run's proven device.
        except BaseException as failure:
            gate.uncertain = True
            error = error or str(failure)
        elapsed = time.monotonic() - gate.started
        accepted = error is None and gate.stock_accepted and not gate.failures and not gate.device and not gate.uncertain and elapsed <= gate.work_seconds + 180
        review_count = (gate.warning_report or {}).get('other_warning_review_count', 0)
        full.save(full.OUT / 'canonical-stock-acceptance.json', {
            'status': ('review_required' if review_count else 'passed') if accepted else 'failed',
            'validation_scope': 'canonical_stock_phase_repair',
            'canonical_stock_phase_accepted': accepted,
            'historical_full_38681904126_status': 'failed',
            'all_required_phases_accepted': False, 'release_qualification': False,
            'source_sha': gate.source, 'source_tree': gate.source_tree, 'baseline_sha': BASE,
            'run_id': os.environ.get('GITHUB_RUN_ID'), 'run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
            'work_budget_seconds': 1800, 'maximum_job_seconds': 2700,
            'elapsed_seconds': elapsed, 'automatic_retries': 0,
            'runtime_warning_review_required': review_count > 0,
            'runtime_warning_report': gate.warning_report,
            'error': error, 'failed_phases': gate.failures, 'pending_owned_device': gate.device,
            'simulator_uncertain': gate.uncertain,
            'not_executed': ['Full', 'package suites', 'unit suite', 'Photos', 'seeded picker', 'archive', 'Vision'],
        })
    return 0 if accepted else 1


if __name__ == '__main__':
    raise SystemExit(main())
