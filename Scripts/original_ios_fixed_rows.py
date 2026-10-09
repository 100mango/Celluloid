#!/usr/bin/env python3
"""Four literal historical rows from two cohorts; every receipt keeps its identity.

Row replay is file-only and never rewrites the execution environment. Metadata
uses exactly six bounded read-only GitHub artifact requests within the existing
archive setup deadline. A GitHub upload digest is reported metadata, never
described as a local ZIP hash by this module.
"""
from pathlib import Path
import hashlib
import json
import re
import shlex
import shutil
import tempfile
import time

import uikit_full_shipping_handoff as handoff
from uikit_full_shipping_gate import ROWS, ROW_COUNTS, clock_status
from validation_route import ORIGINAL_IOS, current_route

ROOT = Path(__file__).resolve().parents[1]
# Only fixed historical run records use this name. Never current routing,
# branch creation, or current-job admission.
HISTORICAL_BRANCH = 'codex/original-ios-release'
COHORTS = {
    '04d18': {'source_sha': '04d18a496b019f54706ff42128605cda1d7dea83',
              'run_id': '37432040947', 'run_attempt': '1',
              'source_tree': 'ea20b3393c2ec6f65bc19b4a7a523ce59de6003d',
              'workflow_sha256': 'fef75b2b7a06a9926259838414c5f3b0ed8531ad4cce5dd0e4ed02c902ed8d75'},
    'da9d': {'source_sha': 'da9d4abd6484ddaff469677d96caf24362645d7c',
             'run_id': '37441448096', 'run_attempt': '1',
             'source_tree': '304ee9c0e4197e4a282ae3933c9f510219b2106d',
             'workflow_sha256': 'b35a4c06656d86bed3142e0752a27f06675bbe13e8458bb0bae4f7ae24cc0118'},
}
IDENTITY_KEYS = ('source_sha', 'run_id', 'run_attempt')
# Only these reviewed row/producer pairs are selectable. No arbitrary cohort API.
ROW_BINDINGS = {'compact-phone': ('04d18', 'producer-04d18'),
                'large-phone': ('04d18', 'producer-04d18'),
                'small-ipad': ('da9d', 'producer-da9d'),
                'large-ipad': ('04d18', 'producer-04d18')}
FINGERPRINT = '3ee65da6ddf7be2f2c42df6505bec283b96a28398736c382189fcd5570068a02'
XCODE_SHA256 = '694b44731d0b415c5b11d844151e466d7f5e200a95627efda377f232f1a6ab77'
CONTRACT_SHA256 = 'cc2c2db6140e4062ac4259092573d2085318d63baf0ce95b92d04e5582f2c481'
GENERATOR_SHA256 = 'fd0f69f467888f93e3059052234aac8f8ba8c13108a97c4edc6bbc79e0bf4bda'
FIXED_ROWS = tuple(ROW_BINDINGS)
ARTIFACTS = {
    'producer-04d18': {'artifact_id': '11397407111', 'job_id': '112164928602',
                 'manifest_sha256': '06c0a00753413ecaae1d99018f36b15a6f15ab1b886efc96ed71098493505cae',
                 'reported_upload_artifact_digest': 'd6eb17a4e240f76d1358ec4acd5ba87850f4d58434018bdcbdacee3f12c00df7'},
    'compact-phone': {'artifact_id': '11398344849', 'job_id': '112166851234',
                      'row_receipt_sha256': 'd22366cead50ce63600c979ce308f4ed982532ea7297066ad8eb5a54c4a3a602',
                      'manifest_sha256': '11bb9f402aeb05bd012544f6237e3f11fd6c86796938ea6c6d618a82142ae5e3',
                      'reported_upload_artifact_digest': 'b499c9fadfdb78e661e8987b70eb2d3adc8d195b1ba1ddc40f0963fc24663352'},
    'large-phone': {'artifact_id': '11397769097', 'job_id': '112166851227',
                    'row_receipt_sha256': '9c7b7b1ae93137e82ecb37514576764af085b39bc395f63a459a776c3ecd5c5c',
                    'manifest_sha256': 'b63050cab9b328261ce9dc10fd626374271402850b055a99a46df775afe2dd9a',
                    'reported_upload_artifact_digest': '173184cb18fa90e89c8f3ee75ed690f5a4e10f7da2c89710e59ec926ed12b1c3'},
    'large-ipad': {'artifact_id': '11400355337', 'job_id': '112166851344',
                   'row_receipt_sha256': '057ecb14390694ef6173d11dfd1a32c0c4789b0e23ce3a20c49e6616d76eb25f',
                   'manifest_sha256': '717ee1a15c302cdcc602a3fc52d44835137102a70af868d2673ad4a4bddfdd96',
                   'reported_upload_artifact_digest': '4c24b3c837cf47268239146bb3ca729cf1f08880c63bc3265e90b576d130c32c'},
    'producer-da9d': {'artifact_id': '11401547686', 'job_id': '112195919191',
                      'manifest_sha256': '44e41677f319be5679d3b1e39d89473905f19af39386e7c4fbbec8be9027de44',
                      'reported_upload_artifact_digest': '7e499558432c2df513d508cb4b4bcffcd5445c61f1ac2918da4747a18ff598c6'},
    'small-ipad': {'artifact_id': '11403055944', 'job_id': '112197875183',
                   'row_receipt_sha256': 'd0a40066dffd091e3e9f4e2ae6e7f3e2c44554cd3569d0ea6f360c9e40b3a9a4',
                   'manifest_sha256': 'c9ac983ff4cacfed0cd9fc4af11140a87dc613b41f7f9f30fac85d1f9d5428ce',
                   'reported_upload_artifact_digest': 'df00892cee35300700f02de7fe65b0f0295a7834f38257731a5b7f291545a639'},
}
COMMAND_SHA256 = {
    'mac-producer': '1e7724c4eb31e707c5fb2b42271fdbae2cf951f9b4d75b1438ade211e88d3e60',
    'uikit-regression': 'a48eb2998050fd9c4b246f67b2fb3e39ef49efdb13ad5487768a7db931c7ccc8',
    'archive': '0387a920832b49bf9ee9a1de0223359e5c18de99f0c56feae7323b79e117437b',
}
# Independently checked git-show bytes at the two immutable trees. The pinned
# artifact manifests bind the same hashes in both original source receipts.
WORKFLOW_COMMAND_SHA256 = {
    'fef75b2b7a06a9926259838414c5f3b0ed8531ad4cce5dd0e4ed02c902ed8d75': dict(COMMAND_SHA256),
    'b35a4c06656d86bed3142e0752a27f06675bbe13e8458bb0bae4f7ae24cc0118': dict(COMMAND_SHA256),
}
need = handoff.need
METADATA = 'original-ios-fixed-artifact-metadata.json'


def row_cohort(row):
    need(row in ROW_BINDINGS, 'Unreviewed fixed row')
    return dict(COHORTS[ROW_BINDINGS[row][0]])


def replay_identity(row):
    """A literal row selects its original identity, never an arbitrary cohort."""
    need(current_route() == ORIGINAL_IOS, 'Fixed replay requires original-iOS route')
    need(handoff.source_profile() == (546, FINGERPRINT), 'Fixed replay source profile changed')
    cohort = row_cohort(row)
    return {key: cohort[key] for key in IDENTITY_KEYS}


def artifact_record(key):
    need(key in ARTIFACTS, 'Unreviewed fixed artifact')
    cohort_key = {'producer-04d18': '04d18', 'producer-da9d': 'da9d'}.get(key)
    cohort = COHORTS[cohort_key] if cohort_key else row_cohort(key)
    name = 'producer' if cohort_key else key
    return {**{k: cohort[k] for k in IDENTITY_KEYS}, **ARTIFACTS[key],
            'source_tree': cohort['source_tree'],
            'name': 'celluloid-original-ios-' + name + '-' + cohort['source_sha'] + '-1'}


def verify_artifact_metadata(metadata, key):
    """Check the exact read-only artifact response used with official download."""
    fixed = artifact_record(key)
    need(type(metadata) is dict and type(metadata.get('id')) is int
         and str(metadata['id']) == fixed['artifact_id'], 'Wrong fixed artifact ID')
    need(metadata.get('name') == fixed['name'] and metadata.get('expired') is False,
         'Wrong/expired fixed artifact')
    need(metadata.get('digest') == 'sha256:' + fixed['reported_upload_artifact_digest'],
         'Wrong fixed upload digest')
    run = metadata.get('workflow_run')
    need(type(run) is dict and type(run.get('id')) is int
         and str(run['id']) == fixed['run_id']
         and run.get('head_sha') == fixed['source_sha']
         and run.get('head_branch') == HISTORICAL_BRANCH, 'Wrong fixed artifact workflow run')
    return fixed


def _metadata_projection(value):
    return {**{key: value[key] for key in ['id', 'name', 'expired', 'digest']},
            'workflow_run': {key: value['workflow_run'][key] for key in ['id', 'head_sha', 'head_branch']}}


def _setup_deadline(temp):
    from original_ios_archive import CLOCK, clock_status
    status = clock_status(handoff.read(Path(temp) / CLOCK), handoff.identity(), 'setup')
    need(status['remaining_seconds'] > 0, 'Fixed replay exceeded archive setup deadline')
    return status['deadline_monotonic']


def fetch_metadata(temp):
    """Exactly six bounded reads; an unfinished receipt blocks later retry."""
    from mac_owned_crash import bounded_optional_process
    from mac_host_transport import load_json
    temp = Path(temp)
    replay_identity('small-ipad')
    report = {'schema': 'Celluloid.OriginalIOSFixedMetadata.2', **handoff.identity(),
              'complete': False, 'observations': {}}
    handoff.write(temp / METADATA, report)
    for key in ARTIFACTS:
        deadline, now = _setup_deadline(temp), time.monotonic()
        cleanup_deadline = min(now + 17, deadline)
        command_deadline = min(now + 15, cleanup_deadline - 2)
        need(command_deadline > now, 'Fixed metadata read and cleanup do not fit setup deadline')
        # Persist uncertainty before dispatch. Even an exception cannot erase it.
        report['observations'][key] = {'finalized': False}
        (temp / METADATA).write_text(json.dumps(report, sort_keys=True) + '\n')
        command = ['gh', 'api', 'repos/100mango/Celluloid/actions/artifacts/' + ARTIFACTS[key]['artifact_id']]
        result = bounded_optional_process(command, command_deadline, cleanup_deadline, cap=8192, stop_on_signal_error=True)
        observation = {name: result[name] for name in ['return_code', 'bytes_read', 'pipe_eof', 'child_reaped',
                       'timed_out', 'overflow', 'cleanup_error', 'finalized', 'elapsed_seconds',
                       'command_deadline_monotonic', 'cleanup_deadline_monotonic']}
        report['observations'][key] = observation
        (temp / METADATA).write_text(json.dumps(report, sort_keys=True) + '\n')
        need(result['finalized'] is True and result['pipe_eof'] is True
             and result['child_reaped'] is True and result['cleanup_error'] is None
             and type(result['return_code']) is int and result['return_code'] == 0
             and result['timed_out'] is False and result['overflow'] is False,
             'Fixed metadata read did not finish safely; no later child admitted')
        metadata = load_json(result['output'])
        verify_artifact_metadata(metadata, key)
        observation['metadata'] = _metadata_projection(metadata)
        _setup_deadline(temp)
    report['complete'] = True
    (temp / METADATA).write_text(json.dumps(report, sort_keys=True) + '\n')
    return verified_metadata(temp)


def verified_metadata(temp):
    return validate_metadata(handoff.read(Path(temp) / METADATA, 16_384), handoff.identity())


def validate_metadata(value, current_identity):
    """Pure retained-metadata check with the caller's verified current identity."""
    need(type(current_identity) is dict and set(current_identity) == set(IDENTITY_KEYS),
         'Malformed fixed metadata current identity')
    for key, pattern in [('source_sha', '[0-9a-f]{40}'), ('run_id', '[1-9][0-9]*'), ('run_attempt', '[1-9][0-9]*')]:
        need(type(current_identity[key]) is str and re.fullmatch(pattern, current_identity[key]),
             'Malformed fixed metadata current ' + key)
    need(type(value) is dict and value.get('schema') == 'Celluloid.OriginalIOSFixedMetadata.2'
         and all(type(value.get(k)) is str and value[k] == v for k, v in current_identity.items())
         and value.get('complete') is True and set(value.get('observations', {})) == set(ARTIFACTS),
         'Missing/incomplete current fixed-artifact metadata')
    for key, observed in value['observations'].items():
        need(observed.get('finalized') is True and type(observed.get('return_code')) is int
             and observed['return_code'] == 0 and observed.get('pipe_eof') is True
             and observed.get('child_reaped') is True and observed.get('timed_out') is False
             and observed.get('overflow') is False and observed.get('cleanup_error') is None
             and type(observed.get('bytes_read')) is int and 0 < observed['bytes_read'] <= 8192,
             'Unfinalized fixed metadata process')
        verify_artifact_metadata(observed['metadata'], key)
    return value


def _bytes(path, maximum):
    path = Path(path)
    need(path.is_file() and not path.is_symlink() and path.stat().st_nlink == 1
         and 0 < path.stat().st_size <= maximum, 'Unsafe/unbounded fixed input: ' + path.name)
    data = path.read_bytes()
    need(len(data) <= maximum, 'Fixed input grew while reading')
    return data


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _command_fingerprints(source, jobs=tuple(COMMAND_SHA256)):
    result = {}
    for name in jobs:
        match = re.search(r'^  ' + re.escape(name) + r':\n(.*?)(?=^  [a-z][a-z-]*:\n|\Z)', source, re.M | re.S)
        need(match is not None, 'Missing fixed native job declaration')
        commands = []
        for line in match.group(1).splitlines():
            if 'xcodebuild -project ' in line:
                command = line[line.index('xcodebuild -project '):]
                commands.append(shlex.split(re.split(r' 2>&1| \| tee|; then ', command)[0]))
        need(commands, 'Missing fixed native command')
        result[name] = _digest(json.dumps(commands, separators=(',', ':')).encode())
    return result


def source_applicability(temp, row, root=ROOT):
    """Current protected inputs, deterministic generator and command declarations."""
    temp, root = Path(temp), Path(root)
    original = replay_identity(row)
    cohort = row_cohort(row)
    current = handoff.identity()
    source = handoff.source_proof(temp)
    need(all(current['source_sha'] != value['source_sha'] and current['run_id'] != value['run_id']
             for value in COHORTS.values()), 'Fixed replay cannot relabel its original run')
    raw = _bytes(root / 'Scripts/original-ios-source-contract.json', 200_000)
    need(_digest(raw) == CONTRACT_SHA256, 'Fixed protected source contract changed')
    contract = json.loads(raw)
    need(len(contract['files']) == 546 and contract['fingerprint'] == FINGERPRINT,
         'Fixed protected source membership changed')
    for path, digest in contract['files']:
        need(_digest(_bytes(root / path, 30_000_000)) == digest, 'Fixed protected source changed: ' + path)
    generator = _bytes(root / 'Scripts/generate_project.py', 200_000)
    need(_digest(generator) == GENERATOR_SHA256, 'Fixed project generator changed')
    # The generator is already byte-pinned. Its existing parser removes writes.
    from original_ios_source_contract import graph, emitted
    need(emitted(graph(generator, root)) == _bytes(root / 'Celluloid.xcodeproj/project.pbxproj', 2_000_000),
         'Fixed generated project differs')
    commands = _command_fingerprints(_bytes(root / ORIGINAL_IOS['workflow_path'], 200_000).decode(), ('archive',))
    need(commands == {'archive': COMMAND_SHA256['archive']}, 'Fixed archive command declaration changed')
    xcode = _bytes(temp / 'full-shipping-xcode.txt', 1000)
    need(_digest(xcode) == XCODE_SHA256, 'Current actual Xcode build differs from fixed evidence')
    return {'schema': 'Celluloid.OriginalIOSFixedApplicability.1',
            'current': {**current, 'source_tree': source['tree']},
            'original': {**original, 'source_tree': cohort['source_tree']},
            'protected_files': 546, 'protected_fingerprint': FINGERPRINT,
            'generator_sha256': GENERATOR_SHA256, 'native_command_sha256': COMMAND_SHA256,
            'historical_workflow_sha256': cohort['workflow_sha256'],
            'historical_native_commands_bound_by': 'pinned_original_source_receipts',
            'historical_workflow_bytes_reread': False,
            'current_archive_command_sha256': commands['archive'],
            'actual_xcode_sha256': XCODE_SHA256, 'source_applicability_verified': True,
            'native_reexecution': False, 'release_acceptance': False}


def _checked_artifact(folder, key):
    folder = Path(folder)
    fixed = artifact_record(key)
    need(folder.is_dir() and not folder.is_symlink(), 'Missing fixed artifact folder')
    need(_digest(_bytes(folder / 'manifest.json', 100_000)) == fixed['manifest_sha256'],
         'Changed fixed artifact manifest')
    manifest = handoff.read(folder / 'manifest.json', 100_000)
    producer = key in {'producer-04d18', 'producer-da9d'}
    limit = 2_000_000 if producer else 1_500_000
    need(manifest.get('source_sha') == fixed['source_sha']
         and str(manifest.get('run_id')) == fixed['run_id']
         and manifest.get('platform') == ('mac' if producer else key), 'Wrong fixed artifact source/run/profile')
    need(type(manifest.get('limits', {}).get('total_bytes')) is int
         and manifest['limits']['total_bytes'] == limit, 'Changed fixed artifact allocation')
    rows = manifest.get('files')
    need(type(rows) is list and 0 < len(rows) <= 160, 'Oversized fixed artifact inventory')
    names = set()
    total = (folder / 'manifest.json').stat().st_size
    for record in rows:
        need(type(record) is dict, 'Malformed fixed artifact member')
        name, count = record.get('name'), record.get('bytes')
        need(type(name) is str and Path(name).name == name
             and name not in {'', '.', '..', 'manifest.json'} and name not in names, 'Unsafe fixed artifact member')
        need(type(count) is int and 0 < count <= limit - total, 'Fixed artifact exceeds allocation')
        raw = _bytes(folder / name, count)
        need(len(raw) == count and _digest(raw) == record.get('sha256'), 'Changed fixed artifact bytes')
        names.add(name)
        total += count
    need({p.name for p in folder.iterdir()} == names | {'manifest.json'}, 'Unlisted fixed artifact member')
    return fixed


def verify_fixed_row(temp, row, folder, producer_folder):
    """Replay original bytes and return their original receipt, never a new run."""
    need(row in FIXED_ROWS, 'Unreviewed fixed row')
    temp, folder, producer_folder = Path(temp), Path(folder), Path(producer_folder)
    _setup_deadline(temp)
    verified_metadata(temp)
    applicability = source_applicability(temp, row)
    _setup_deadline(temp)
    artifact = _checked_artifact(folder, row)
    producer_artifact = _checked_artifact(producer_folder, ROW_BINDINGS[row][1])
    context = {**replay_identity(row), 'row': row}
    stored = handoff.read(folder / 'full-shipping-row.json')
    need(stored.get('row_checks_passed') is True, 'Incomplete fixed row')
    index = handoff.read(folder / handoff.LOG_INDEX, 16_000)
    need(index.get('producer_complete') is True, 'Interrupted fixed row log producer')
    logs = handoff.unpack_phase_logs(folder, index, context)
    for old, producer in [('consumer-mac-layer-fixture.json', 'mac-layer-fixture.json'),
                          ('consumer-mac-layer-manifest.json', 'manifest.json')]:
        need((folder / old).read_bytes() == (producer_folder / producer).read_bytes(), 'Fixed row used another producer')
    clock = handoff.read(folder / 'full-shipping-clock.json')
    recorded = handoff.read(folder / 'full-shipping-accounting.json')['clock']
    observation = {'now_monotonic': clock['started_monotonic'] + recorded['elapsed_seconds'],
                   'now_unix': clock['started_unix'] + recorded['wall_elapsed_seconds']}
    need(recorded == clock_status(clock, context, **observation)
         and recorded['within_execution_clock'] is True, 'Invalid fixed execution interval')
    with tempfile.TemporaryDirectory(prefix='fixed-original-row-', dir=temp) as scratch:
        replay = Path(scratch)
        for path in folder.iterdir():
            shutil.copyfile(path, replay / path.name)
        for name, data in logs.items():
            need(not (replay / name).exists(), 'Raw fixed log collides with retained member')
            (replay / name).write_bytes(data)
        shutil.copytree(producer_folder, replay / 'mac-fixture-evidence')
        shutil.copyfile(temp / 'full-shipping-xcode.txt', replay / 'full-shipping-xcode.txt')
        old_transfer = handoff.read(replay / 'full-shipping-transfer.json')
        (replay / 'full-shipping-transfer.json').unlink()
        handoff.transfer(replay, producer_artifact['artifact_id'], producer_artifact['manifest_sha256'],
                         producer_artifact['reported_upload_artifact_digest'], fixed_original_replay=True, fixed_original_row=row)
        need(handoff.same_json(old_transfer, handoff.read(replay / 'full-shipping-transfer.json')),
             'Fixed producer transfer replay differs')
        for phase in ['before', 'after']:
            original = handoff.source_proof(replay / 'mac-fixture-evidence', phase, fixed_original_replay=True, fixed_original_row=row)
            need(handoff.same_json(original['original_ios_source'],
                                   handoff.source_proof(temp)['original_ios_source']), 'Fixed producer protected source proof differs')
        actual = handoff.accept_row(replay, row=row, recorded_observation=observation, fixed_original_replay=True)
    _setup_deadline(temp)
    need(handoff.same_json(stored, actual) and actual['source_tree'] == row_cohort(row)['source_tree']
         and actual['device']['model'] == ROWS[row]
         and actual['original_test_invocation_count'] == ROW_COUNTS[row], 'Fixed native row replay differs')
    summary = handoff.read(producer_folder / 'full-shipping-mac-summary.json')
    accounting = handoff.read(producer_folder / 'full-shipping-mac-accounting.json')['accounting']
    need(summary['totalTestCount'] == summary['passedTests'] == 67
         and accounting['case_counts'] == {'failed': 0, 'passed': 67, 'skipped': 0}, 'Fixed enclosing producer count differs')
    return {'original': actual, 'applicability': applicability, 'artifact': artifact,
            'producer': {**producer_artifact, 'retained_enclosing_cases': 67, 'retained_required_cases': 42,
                         'retained_evidence_verified': True, 'raw_producer_log_replayed': False},
            'row_receipt_sha256': handoff.sha(folder / 'full-shipping-row.json'),
            'native_reexecution': False, 'release_acceptance': False}


def validate_fixed_summary(payload, current_identity, current_source_tree):
    """Pure final-packet check; exact old receipt hashes bind the full receipts."""
    need(type(payload) is dict and set(payload) == set(FIXED_ROWS), 'Wrong fixed predecessor rows')
    need(type(current_identity) is dict and set(current_identity) == set(IDENTITY_KEYS)
         and all(current_identity['source_sha'] != value['source_sha'] and current_identity['run_id'] != value['run_id']
                 for value in COHORTS.values()), 'Invalid current applicability identity')
    for row, value in payload.items():
        need(type(value) is dict and set(value) == {'original', 'applicability', 'artifact', 'producer',
                                                   'row_receipt_sha256', 'native_reexecution', 'release_acceptance'},
             'Malformed fixed row summary')
        artifact = artifact_record(row)
        cohort = row_cohort(row)
        original_identity = {key: cohort[key] for key in IDENTITY_KEYS}
        need(handoff.same_json(value['artifact'], artifact), 'Changed fixed row artifact binding')
        original = value['original']
        raw = (json.dumps(original, indent=2, sort_keys=True) + '\n').encode()
        need(_digest(raw) == artifact['row_receipt_sha256']
             and value['row_receipt_sha256'] == artifact['row_receipt_sha256'], 'Changed original row receipt')
        need(original['row'] == row and original['row_checks_passed'] is True
             and all(original.get(k) == v for k, v in original_identity.items())
             and original['source_tree'] == cohort['source_tree'] and original['device']['model'] == ROWS[row]
             and original['original_test_invocation_count'] == ROW_COUNTS[row], 'Changed original row identity')
        expected = {'schema': 'Celluloid.OriginalIOSFixedApplicability.1',
                    'current': {**current_identity, 'source_tree': current_source_tree},
                    'original': {**original_identity, 'source_tree': cohort['source_tree']},
                    'protected_files': 546, 'protected_fingerprint': FINGERPRINT,
                    'generator_sha256': GENERATOR_SHA256, 'native_command_sha256': COMMAND_SHA256,
                    'historical_workflow_sha256': cohort['workflow_sha256'],
                    'historical_native_commands_bound_by': 'pinned_original_source_receipts',
                    'historical_workflow_bytes_reread': False,
                    'current_archive_command_sha256': COMMAND_SHA256['archive'],
                    'actual_xcode_sha256': XCODE_SHA256, 'source_applicability_verified': True,
                    'native_reexecution': False, 'release_acceptance': False}
        need(handoff.same_json(value['applicability'], expected), 'Changed fixed source applicability')
        producer = {**artifact_record(ROW_BINDINGS[row][1]), 'retained_enclosing_cases': 67, 'retained_required_cases': 42,
                    'retained_evidence_verified': True, 'raw_producer_log_replayed': False}
        need(handoff.same_json(value['producer'], producer), 'Changed fixed producer retained-evidence claim')
        need(value['native_reexecution'] is False and value['release_acceptance'] is False,
             'Fixed replay cannot claim new native execution/release')
    return payload


if __name__ == '__main__':
    import argparse
    import os
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['metadata'])
    parser.parse_args()
    print(json.dumps(fetch_metadata(Path(os.environ['RUNNER_TEMP']).resolve()), sort_keys=True))
