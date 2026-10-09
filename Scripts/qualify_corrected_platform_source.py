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
CONFIG = '.github/corrected-native-qualification.json'
BRANCH = 'celluloid-platform-qualification'
WORKFLOW = '.github/workflows/corrected-platform-qualification.yml'
CONTROL_PATHS = frozenset((WORKFLOW, CONFIG, 'Scripts/qualify_corrected_platform_source.py'))
PLATFORMS = frozenset(('mac', 'tv', 'vision', 'watch'))


def require(value, message):
    if not value:
        raise ValueError(message)


def git(*arguments, root=ROOT):
    return subprocess.check_output(['git', *arguments], cwd=root, text=True, timeout=20).strip()


def validate(context, facts, enabled=False):
    require(enabled is True, 'Qualification route is closed')
    for key in ('product_parent_sha', 'product_parent_tree'):
        require(re.fullmatch('[0-9a-f]{40}', context.get(key, '')) is not None, 'Invalid ' + key)
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
        require(commit['changed_paths'] and set(commit['changed_paths']) <= CONTROL_PATHS, 'Product mutation in control history')
        prior = commit['sha']
    require(prior == facts['head'], 'Control chain head mismatch')
    require(facts['parent_tree'] == context['product_parent_tree'], 'Product parent tree mismatch')
    require(set(facts['changed_paths']) == CONTROL_PATHS, 'Only the three reviewed control files may differ from the product parent')
    require(not facts['dirty'], 'Tracked or untracked checkout changed')
    return {'scope': 'Independent unsigned native platform validation',
            'platform': context['platform'], 'source_sha': facts['head'], 'tree': facts['tree'],
            'control_sha': facts['head'], 'control_tree': facts['tree'],
            'product_parent_sha': context['product_parent_sha'], 'product_parent_tree': context['product_parent_tree'],
            'workflow_path': WORKFLOW, 'control_paths': sorted(CONTROL_PATHS),
            'control_commit_count': len(facts['chain']), 'full_platform_release_qualification': False,
            'deferred_gates': ['distribution signing and Store processing', 'current visual acceptance',
                               *(['sandbox runtime', 'strict current-source UIKit 2x/3x layer parity', 'actual Photos host lifecycle'] if context['platform'] == 'mac' else []),
                               *(['shipping iOS Watch embedding', 'production paired transport'] if context['platform'] == 'watch' else [])]}


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
        'workflow_platform': 'QUALIFICATION_PLATFORM', 'run_attempt': 'GITHUB_RUN_ATTEMPT'}.items()})
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
    paths = [p for p in git('ls-files', '-z').split('\0') if p and p not in CONTROL_PATHS]
    rows = [[p, hashlib.sha256((ROOT / p).read_bytes()).hexdigest()] for p in paths]
    report.update(phase=args.phase, file_count=len(rows), product_fingerprint=hashlib.sha256(json.dumps(rows, separators=(',', ':')).encode()).hexdigest(),
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
