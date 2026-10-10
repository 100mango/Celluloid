#!/usr/bin/env python3
"""Closed, exact-source admission only; native assertions remain in existing scripts."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CONFIG = '.github/final-vision-wave.json'
BRANCH = 'celluloid-final-vision-wave'
WORKFLOW = '.github/workflows/final-vision-wave.yml'
CONTROL_PATHS = frozenset((WORKFLOW, CONFIG, 'Scripts/qualify_final_vision_wave_source.py', 'Scripts/final_vision_wave.py', 'Scripts/test_final_vision_wave.py'))

DIAGNOSTIC_TEST = 'Platforms/VisionUITests/NativeVisionUITests.swift'
DIAGNOSTIC_TEST_SHA256 = '7d0e9c3174e36ab34644d8e08cb7612578a6370974cd8c8ec6b7eb476e0b4c6e'
ORIGINAL_TEST_SHA256 = 'ad973878bf33ae77d634679d76af545d2d0c1206fe3d1dfebff55c172746677d'
QUALIFICATION_PATHS = CONTROL_PATHS | {DIAGNOSTIC_TEST}
HOSTED_DIAGNOSTIC_TEST = 'Platforms/VisionTests/NativeVisionTests.swift'
HOSTED_DIAGNOSTIC_TEST_SHA256 = '92c56ed2c018052f235f3fc64b9cf116ae361079aaa483af37d17a21ee4cbb5e'
HOSTED_ORIGINAL_TEST_SHA256 = '7ab4d6811af3cff725aa08a0b52efc7dc7b5b02ede5589ae695c0930aa5a1ecc'
HOSTED_DIAGNOSTIC_ADDITION = '        // VISION_FILES_DATA_DIAG_BEGIN:owned-home-identity\n        // Only this host\'s own sandbox identity; no directory enumeration or data reads.\n        let dataHome = NSHomeDirectory()\n        let attributes = try FileManager.default.attributesOfItem(atPath: dataHome)\n        XCTAssertEqual(attributes[.type] as? FileAttributeType, .typeDirectory)\n        let device = try XCTUnwrap(attributes[.systemNumber] as? NSNumber)\n        let inode = try XCTUnwrap(attributes[.systemFileNumber] as? NSNumber)\n        let receipt: [String: Any] = ["schema": "Celluloid.VisionOwnedData.1",\n            "bundle_identifier": "Mango.Celluloid", "data_home": dataHome,\n            "device": device.uint64Value, "inode": inode.uint64Value]\n        let encoded = try JSONSerialization.data(withJSONObject: receipt, options: [.sortedKeys])\n        XCTAssertLessThanOrEqual(encoded.count, 4096)\n        print("VISION_NATIVE_DATA_JSON " + String(decoding: encoded, as: UTF8.self))\n        // VISION_FILES_DATA_DIAG_END:owned-home-identity\n'
QUALIFICATION_PATHS = QUALIFICATION_PATHS | {HOSTED_DIAGNOSTIC_TEST}
UNCHANGED_ORIGINAL_FILE_COUNT = 960
DIAGNOSTIC_REPLACEMENTS = [('        // VISION_FILES_DIAG_BEGIN:failure-receipts\n        // Diagnostics observe this same document and never replace its original assertions.\n        func filesDiagnosticFailure(_ stage: String) {\n            let full = app.debugDescription\n            let bytes = Array(full.utf8), cap = 65536\n            let complete = bytes.count <= cap\n            let bounded = complete ? full : String(decoding: bytes.prefix(cap / 2), as: UTF8.self)\n                + "\\n[bounded middle omission]\\n" + String(decoding: bytes.suffix(cap / 2), as: UTF8.self)\n            let attachment = XCTAttachment(string: bounded)\n            attachment.name = "vision-files-diag-" + stage + "-ax"\n            attachment.lifetime = .keepAlways; add(attachment)\n            print("VISION_FILES_DIAGNOSTIC_AX stage=\\(stage) complete=\\(complete) fullBytes=\\(bytes.count) retainedBytes=\\(bounded.utf8.count)")\n            capture(app, name: "vision-files-diag-" + stage + "-screen")\n        }\n        // VISION_FILES_DIAG_END:failure-receipts\n', ''), ('        // VISION_FILES_DIAG_BEGIN:fixture-identity\n        XCTAssertTrue(text.waitForExistence(timeout: 10))\n        let diagnosticLayers = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH \'layer.\'"))\n        if diagnosticLayers.count != 1 { filesDiagnosticFailure("identity") }\n        XCTAssertEqual(diagnosticLayers.count, 1, "A fresh Files document must identify exactly its inserted layer")\n        let diagnosticLayerIdentifier = diagnosticLayers.firstMatch.identifier\n        XCTAssertTrue(diagnosticLayerIdentifier.hasPrefix("layer."))\n        XCTAssertNotNil(UUID(uuidString: String(diagnosticLayerIdentifier.dropFirst(6))))\n        let fixtureReceipt: [String: Any] = ["schema": "Celluloid.VisionFilesFixture.1", "document_name": documentName, "layer_identifier": diagnosticLayerIdentifier]\n        let fixtureReceiptBytes = try JSONSerialization.data(withJSONObject: fixtureReceipt, options: [.sortedKeys])\n        print("VISION_FILES_FIXTURE_JSON " + String(decoding: fixtureReceiptBytes, as: UTF8.self))\n        text.tap()\n        // VISION_FILES_DIAG_END:fixture-identity\n', '        XCTAssertTrue(text.waitForExistence(timeout: 10)); text.tap()\n'), ('        // VISION_FILES_DIAG_BEGIN:post-redo-model\n        let diagnosticModelRow = app.buttons.matching(identifier: diagnosticLayerIdentifier).firstMatch\n        let diagnosticExpectedLabel = "Select layer: Vision 世界"\n        let diagnosticModelMatched = XCTWaiter.wait(for: [expectation(for: NSPredicate(format: "exists == true AND label == %@", diagnosticExpectedLabel), evaluatedWith: diagnosticModelRow)], timeout: 10) == .completed\n        let modelReceipt: [String: Any] = ["schema": "Celluloid.VisionFilesModel.1", "stage": "post-redo", "document_name": documentName, "layer_identifier": diagnosticLayerIdentifier, "expected_text": "Vision 世界", "matched": diagnosticModelMatched, "actual_label": diagnosticModelRow.exists ? String(diagnosticModelRow.label.prefix(256)) : "missing layer"]\n        let modelReceiptBytes = try JSONSerialization.data(withJSONObject: modelReceipt, options: [.sortedKeys])\n        print("VISION_FILES_MODEL_JSON " + String(decoding: modelReceiptBytes, as: UTF8.self))\n        if !diagnosticModelMatched { filesDiagnosticFailure("post-redo") }\n        XCTAssertTrue(diagnosticModelMatched, "The same recipe-backed layer UUID must retain exact multilingual text after Redo")\n        // Documents exposes no observed disk-save completion. Keep the original\n        // navigation/termination below; do not add a delay or claim a save barrier.\n        // VISION_FILES_DIAG_END:post-redo-model\n', ''), ('        // VISION_FILES_DIAG_BEGIN:reopen-failure\n        let diagnosticReopenedMatched = layer.waitForExistence(timeout: 10)\n        if !diagnosticReopenedMatched { filesDiagnosticFailure("reopen-layer") }\n        XCTAssertTrue(diagnosticReopenedMatched)\n        if layer.identifier != diagnosticLayerIdentifier { filesDiagnosticFailure("reopen-identity") }\n        XCTAssertEqual(layer.identifier, diagnosticLayerIdentifier, "Reopen must retain the same document layer identity")\n        layer.tap()\n        // VISION_FILES_DIAG_END:reopen-failure\n', '        XCTAssertTrue(layer.waitForExistence(timeout: 10)); layer.tap()\n')]

def verify_diagnostic_test(raw):
    require(hashlib.sha256(raw).hexdigest() == DIAGNOSTIC_TEST_SHA256, 'Unreviewed diagnostic test bytes')
    source = raw.decode('utf8')
    for added, original in DIAGNOSTIC_REPLACEMENTS:
        require(source.count(added) == 1, 'Diagnostic inverse block missing or duplicated')
        source = source.replace(added, original)
    restored = source.encode('utf8')
    require(hashlib.sha256(restored).hexdigest() == ORIGINAL_TEST_SHA256, 'Diagnostic inverse does not restore fixed original test')
    return restored

def verify_hosted_diagnostic_test(raw):
    require(hashlib.sha256(raw).hexdigest() == HOSTED_DIAGNOSTIC_TEST_SHA256, 'Unreviewed hosted diagnostic test bytes')
    text = raw.decode('utf8')
    require(text.count(HOSTED_DIAGNOSTIC_ADDITION) == 1, 'Hosted diagnostic block missing or duplicated')
    restored = text.replace(HOSTED_DIAGNOSTIC_ADDITION, '').encode('utf8')
    require(hashlib.sha256(restored).hexdigest() == HOSTED_ORIGINAL_TEST_SHA256, 'Hosted inverse does not restore fixed original test')
    return restored

PLATFORMS = frozenset(('vision',))
SOURCE = '13e9a1ed63c6e7744803419f27e429a759df1209'
TREE = 'f2c6d0f38c026957b0b34f22b916eb80ed5b20a8'
UI_METHODS = ('testNativeDocumentBrowserLaunchAndNewDocument', 'testRealFilesImportBubbleAndPNGExport', 'testSeededDocumentSequentialTextUndoRedoAndBrowserReopen', 'testSimplifiedChineseDocumentPrivacyAndLargeText')


def require(value, message):
    if not value:
        raise ValueError(message)


def git(*arguments, root=ROOT):
    return subprocess.check_output(['git', *arguments], cwd=root, text=True, timeout=20).strip()


def validate(context, facts, enabled=False):
    require(enabled is True, 'Qualification route is closed')
    for key in ('product_parent_sha', 'product_parent_tree'):
        require(re.fullmatch('[0-9a-f]{40}', context.get(key, '')) is not None, 'Invalid ' + key)
    require(context.get('product_parent_sha') == SOURCE and context.get('product_parent_tree') == TREE, 'Wrong fixed final product')
    require(context.get('selected_method') == 'testRealFilesImportBubbleAndPNGExport' and context.get('workflow_selected_method') == context.get('selected_method'), 'Select exactly one matching whole UI method')
    require(context.get('repository') == '100mango/Celluloid', 'Wrong repository')
    require(context.get('event') == 'push', 'Exact branch/path push required')
    require(context.get('ref') == 'refs/heads/' + BRANCH, 'Wrong qualification branch')
    require(context.get('workflow_ref') == '100mango/Celluloid/' + WORKFLOW + '@refs/heads/' + BRANCH, 'Wrong workflow')
    require(context.get('platform') in PLATFORMS, 'Select exactly one native platform')
    require(context.get('confirmation') == 'RUN_ONE_UNSIGNED_PLATFORM_ZERO_USD', 'Wrong confirmation')
    require(context.get('run_attempt') == '1', 'A retry requires a fresh reviewed push')
    require(re.fullmatch('[0-9a-f]{40}', facts['head']) is not None and re.fullmatch('[0-9a-f]{40}', facts['tree']) is not None, 'Malformed actual control identity')
    require(context.get('github_sha') == context.get('workflow_sha') == facts['head'], 'Control SHA mismatch')
    require(context.get('maximum_additional_spend_usd') == 0, 'Nonzero cost is not admitted')
    require(context.get('workflow_platform') == context['platform'], 'Regenerate workflow from selected config')
    require(0 < len(facts['chain']) <= 32, 'Control chain must contain 1 to 32 commits')
    prior = context['product_parent_sha']
    for commit in facts['chain']:
        require(commit['parents'] == [prior], 'Control history must be linear from the corrected product')
        require(commit['changed_paths'] and set(commit['changed_paths']) <= QUALIFICATION_PATHS, 'Product mutation in control history')
        prior = commit['sha']
    require(prior == facts['head'], 'Control chain head mismatch')
    require(facts['parent_tree'] == context['product_parent_tree'], 'Product parent tree mismatch')
    require(set(facts['changed_paths']) == QUALIFICATION_PATHS, 'Only five controls and two exact reversible diagnostic tests may differ')
    require(not facts['dirty'], 'Tracked or untracked checkout changed')
    return {'scope': 'Independent unsigned native platform validation',
            'platform': context['platform'], 'source_sha': facts['head'], 'tree': facts['tree'],
            'control_sha': facts['head'], 'control_tree': facts['tree'],
            'product_parent_sha': context['product_parent_sha'], 'product_parent_tree': context['product_parent_tree'],
            'workflow_path': WORKFLOW, 'control_paths': sorted(CONTROL_PATHS), 'qualification_paths': sorted(QUALIFICATION_PATHS), 'diagnostic_test_path': DIAGNOSTIC_TEST,
            'control_commit_count': len(facts['chain']), 'selected_method': context['selected_method'], 'omitted_ui_methods': [m for m in UI_METHODS if m != context['selected_method']], 'full_platform_release_qualification': False,
            'deferred_gates': ['distribution signing and Store processing', 'current visual acceptance',
                               *(['sandbox runtime', 'strict current-source UIKit 2x/3x layer parity', 'actual Photos host lifecycle'] if context['platform'] == 'mac' else []),
                               *(['shipping iOS Watch embedding', 'production paired transport'] if context['platform'] == 'watch' else [])]}


def verify_diagnostic_history(chain, read_blob):
    transitions = []
    for commit in chain:
        if DIAGNOSTIC_TEST not in commit['changed_paths']:
            continue
        previous = read_blob(commit['parents'][0], DIAGNOSTIC_TEST)
        current = read_blob(commit['sha'], DIAGNOSTIC_TEST)
        require(hashlib.sha256(previous).hexdigest() == ORIGINAL_TEST_SHA256, 'Unreviewed earlier diagnostic test history')
        require(hashlib.sha256(current).hexdigest() == DIAGNOSTIC_TEST_SHA256, 'Unreviewed diagnostic transition')
        transitions.append(commit['sha'])
    require(len(transitions) == 1, 'Exactly one original-to-reviewed diagnostic test transition required')
    return transitions[0]


def verify_hosted_diagnostic_history(chain, read_blob):
    transitions = []
    for commit in chain:
        if HOSTED_DIAGNOSTIC_TEST not in commit['changed_paths']:
            continue
        previous = read_blob(commit['parents'][0], HOSTED_DIAGNOSTIC_TEST)
        current = read_blob(commit['sha'], HOSTED_DIAGNOSTIC_TEST)
        require(hashlib.sha256(previous).hexdigest() == HOSTED_ORIGINAL_TEST_SHA256, 'Unreviewed earlier hosted test history')
        require(hashlib.sha256(current).hexdigest() == HOSTED_DIAGNOSTIC_TEST_SHA256, 'Unreviewed hosted diagnostic transition')
        transitions.append(commit['sha'])
    require(len(transitions) == 1, 'Exactly one original-to-reviewed hosted diagnostic transition required')
    return transitions[0]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', required=True, choices=['before', 'after'])
    args = parser.parse_args()
    env = os.environ
    config = json.loads((ROOT / CONFIG).read_text())
    require(config.get('schema') == 1 and config.get('READY') is True, 'Qualification route is closed')
    context = dict(config)
    context.update({key: env.get(name, '') for key, name in {
        'repository': 'GITHUB_REPOSITORY', 'event': 'GITHUB_EVENT_NAME', 'ref': 'GITHUB_REF',
        'workflow_ref': 'GITHUB_WORKFLOW_REF', 'github_sha': 'GITHUB_SHA', 'workflow_sha': 'GITHUB_WORKFLOW_SHA',
        'workflow_platform': 'QUALIFICATION_PLATFORM', 'workflow_selected_method': 'VISION_WAVE_METHOD', 'run_attempt': 'GITHUB_RUN_ATTEMPT'}.items()})
    parent = context['product_parent_sha']
    require(re.fullmatch('[0-9a-f]{40}', parent) is not None, 'Invalid product parent')
    git('merge-base', '--is-ancestor', parent, 'HEAD')
    rows = git('rev-list', '--reverse', '--parents', parent + '..HEAD').splitlines()
    require(0 < len(rows) <= 32, 'Bounded control history unavailable')
    chain = []
    for row in rows:
        parts = row.split()
        require(len(parts) == 2, 'Merge or missing product parent is not admitted')
        chain.append({'sha': parts[0], 'parents': parts[1:],
                      'changed_paths': git('diff', '--name-only', parts[1], parts[0]).splitlines()})
    facts = {'head': git('rev-parse', 'HEAD'), 'tree': git('rev-parse', 'HEAD^{tree}'), 'chain': chain,
             'parent_tree': git('rev-parse', parent + '^{tree}'),
             'changed_paths': git('diff', '--name-only', parent, 'HEAD').splitlines(),
             'dirty': git('status', '--porcelain', '--untracked-files=all')}
    report = validate(context, facts, enabled=config['READY'])
    report['diagnostic_transition_commit'] = verify_diagnostic_history(chain, lambda revision, path: subprocess.check_output(['git', 'show', revision + ':' + path], cwd=ROOT, timeout=20))
    diagnostic = (ROOT / DIAGNOSTIC_TEST).read_bytes()
    restored = verify_diagnostic_test(diagnostic)
    original = subprocess.check_output(['git', 'show', parent + ':' + DIAGNOSTIC_TEST], cwd=ROOT, timeout=20)
    require(original == restored, 'Inverse test differs from fixed product parent')
    require(git('ls-tree', 'HEAD', '--', DIAGNOSTIC_TEST).split()[0] == git('ls-tree', parent, '--', DIAGNOSTIC_TEST).split()[0] == '100644', 'Diagnostic test mode changed')
    report['hosted_diagnostic_transition_commit'] = verify_hosted_diagnostic_history(chain, lambda revision, path: subprocess.check_output(['git', 'show', revision + ':' + path], cwd=ROOT, timeout=20))
    hosted = (ROOT / HOSTED_DIAGNOSTIC_TEST).read_bytes()
    hosted_restored = verify_hosted_diagnostic_test(hosted)
    require(hosted_restored == subprocess.check_output(['git', 'show', parent + ':' + HOSTED_DIAGNOSTIC_TEST], cwd=ROOT, timeout=20), 'Hosted inverse differs from fixed original test')
    require(git('ls-tree', 'HEAD', '--', HOSTED_DIAGNOSTIC_TEST).split()[0] == git('ls-tree', parent, '--', HOSTED_DIAGNOSTIC_TEST).split()[0] == '100644', 'Hosted diagnostic test mode changed')
    report.update(hosted_diagnostic_test_path=HOSTED_DIAGNOSTIC_TEST, hosted_diagnostic_test_sha256=HOSTED_DIAGNOSTIC_TEST_SHA256, hosted_diagnostic_test_inverse_sha256=HOSTED_ORIGINAL_TEST_SHA256)
    paths = [p for p in git('ls-files', '-z').split('\0') if p and p not in QUALIFICATION_PATHS]
    require(len(paths) == UNCHANGED_ORIGINAL_FILE_COUNT, 'Unexpected unchanged original file count')
    rows = [[p, hashlib.sha256((ROOT / p).read_bytes()).hexdigest()] for p in paths]
    report.update(phase=args.phase, file_count=len(rows), original_total_file_count=962, unchanged_original_file_count=len(rows), diagnostic_test_sha256=DIAGNOSTIC_TEST_SHA256, diagnostic_test_inverse_sha256=ORIGINAL_TEST_SHA256, product_compiled_inputs_unchanged=True, product_fingerprint=hashlib.sha256(json.dumps(rows, separators=(',', ':')).encode()).hexdigest(),
                  workflow_sha256=hashlib.sha256((ROOT / WORKFLOW).read_bytes()).hexdigest(),
                  run_id=env['GITHUB_RUN_ID'], run_attempt=env['GITHUB_RUN_ATTEMPT'])
    temp = Path(env['RUNNER_TEMP'])
    if args.phase == 'after':
        before = json.loads((temp / 'combined-source-before.json').read_text())
        require({k: v for k, v in report.items() if k != 'phase'} == {k: v for k, v in before.items() if k != 'phase'}, 'Source/control identity changed during native work')
    (temp / ('combined-source-' + args.phase + '.json')).write_text(json.dumps(report, indent=2) + '\n')
    print('CORRECTED_PLATFORM_SOURCE ' + json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
