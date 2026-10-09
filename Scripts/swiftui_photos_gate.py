#!/usr/bin/env python3
"""Small admission/evidence contract for the shared-build seeded PhotoKit phases."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import math
import uuid

FIXTURES = {'celluloid-fixture.png': (640, 480), 'celluloid-fixture-2.png': (640, 480),
            **{f'celluloid-composition-{i}.png': (800 + i, 600) for i in range(4)}}
LEGACY = {
    'AdjustmentDataTests': [
        'testEncodedByteBudgetRejectsBeforeUnarchiving', 'testSmallSharedReferenceArchiveRejectsExcessiveLayers',
        'testAggregateRepeatedTextBudgetRejectsWithoutTruncation', 'testIndividualUnicodeTextBudgetRejectsWithoutTruncation',
        'testEncodingRejectsUnreopenableStateInsteadOfDroppingLayers', 'testExportSyntheticUIKitCompatibilityFixtures',
        'testActualMacEncodedFixturesDecodeWithOriginalUIKitReader', 'testProbe32BitGeometryArchiveRepresentation',
        'testLegacyArchivesMayOmitEmptyArrays', 'testExplicitEmptyArraysAreAlsoAccepted',
        'testUnknownFilterAndInvalidCollectionsAreRejected', 'testUnknownAssetsAreRejectedBeforeTheyReachImageRendering',
        'testMissingAndMistypedGeometryAreRejected', 'testNonfiniteAndNegativeGeometryAreRejected',
        'testEveryShippingAssetAndFilterCanRoundTrip'],
    'OverlayResizeTests': [
        'testHalvingCanvasHalvesCenterAndFullAffineTransform',
        'testPortraitLandscapeSplitViewAndRoundTripPreserveGeometryAndExportPixels',
        'testBubbleAndStickerIndividuallyKeepTheirRenderedPixelsAfterResize',
        'testZeroSizedIntermediateLayoutRetainsLastCoordinateSpace',
        'testNewArchiveRestoresAcrossDevicesBeforeOrAfterSourceAndLayout',
        'testLegacyArchiveKeepsAbsolutePointsAtFirstValidLayoutThenTracksResizes',
        'testOptionalReferenceCanvasRejectsWrongTypeZeroNegativeAndNonfiniteValues',
        'testSourceReplacementReappliesSameFilterAndResetInputClearsOldSession',
        'testOriginalUndecoratedOutputDoesNotRequirePreviewLayout', 'testOrientedSourceDecorationPixelsStayFixedAfterResize'],
    'EditorRegressionTests': [
        'testEditorRendersAndRestoresWithoutDuplicatingOverlays', 'testOrientedAsymmetricSourceExportsCorrectDimensionsAndStickerPixels',
        'testNoSourceImageIsSafe', 'testProtectedPhotosSessionDoesNotOfferDiscardingChanges',
        'testReadOnlyAdjustmentKeepsOpaqueBytesAndCurrentPixelsUntilNewInput',
        'testPickerCallbacksRemainBoundToTheirOriginalEditingSession',
        'testResourceBudgetRejectsSnapshotBeforeDecodeOrRasterWithoutTruncation',
        'testExtensionNegotiatesKnownFormatWithoutDecodingUnboundData',
        'testExtensionWithoutInputCompletesWithFailureExactlyOnce', 'testCancelledExtensionNeverInvokesHostCompletion',
        'testCollageTemplatesHaveValidPolygons'],
    'ExportAndInteractionTests': [
        'testTwelveMegapixelExportPreservesDimensionsAndAllowsMainQueueHeartbeat',
        'testCancelledAndSupersededExportNeverReturnsStaleSuccess',
        'testSourceScaleAndExifDoNotChangeFullResolutionWhenDecorated',
        'testDegenerateCanvasAndOverflowAreRejectedBeforeUIKitRescale',
        'testFiniteComponentsWithOverflowingTransformedBoundsAreRejected',
        'testGesturePreservesRebasedScaleAndControlsStayFortyFourScreenPoints',
        'testAsyncDecoratedExportExcludesVisibleEditorHandles', 'testAsyncMissingSourceCompletesWithFailureExactlyOnce',
        'testOffMainCompositeMatchesLegacyAffineAlphaAndColorRendering',
        'testStreamingTileBoundariesAndManyOverlaysMatchLegacyPixels',
        'testUnevenRotatedAndScaledStripCanvasesMatchLegacyPixels',
        'testExtendedRangeSourceMatchesLegacyRendererBitmapAndPixels']}
PRISTINE = {
    'PhotoSelectionSessionTests': ['testRealSelectedLookupPreservesOrderAndIdentity'],
    'CollageCompositionTests': ['testDistinctAsymmetricSourcesComposeTwoThreeFourAndReorderWithoutReuse'],
    'OverlayResizeTests': ['testPhotosExtensionRestartWithoutAdjustmentClearsDecorationsFilterAndCancellation'],
    'EditorRegressionTests': ['testExtensionStartsRendersAndFinishesSeededPhotoWithoutLibraryMutation',
                              'testReconcileSyntheticPhotosAfterImport']}
PRESERVATION = {'AdjustmentPreservationPhotoKitTests': [
    'testActualBoundInputsPreserveOpaqueEditsAcrossIndependentSessions',
    'testDoneWhileRecipeLoadsPreservesOpaqueStateAndNewestCompletion',
    'testDoneBeforeLegacyCanvasLayoutWaitsForOriginalGeometry',
    'testUnmountedLegacyCanvasTimesOutOnceAndAbandonedHostsStaySilent',
    'testActualPhotosOutputDestinationsIsolateLateWrites', 'testWrongAuthorizationNeverReachesSyntheticSetup']}
STAGES = {'legacy': LEGACY, 'pristine': PRISTINE, 'preservation': PRESERVATION}


def methods(stage):
    return [f'CelluloidTests/{suite}/{method}' for suite, names in STAGES[stage].items() for method in names]


def load(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 1_000_000:
        raise ValueError('Missing/unsafe evidence file: ' + str(path))
    return json.loads(path.read_text())


def dump(path, value):
    path = Path(path)
    if path.exists():
        raise ValueError('Refuse to replace prior gate evidence: ' + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def validate_owner(receipt, device, environment, observed, expected_ref='refs/heads/swiftui-first-native'):
    source = environment.get('GITHUB_SHA', '')
    if not re.fullmatch(r'[0-9a-f]{40}', source): raise ValueError('Exact source SHA is absent')
    if environment.get('GITHUB_REPOSITORY') != '100mango/Celluloid': raise ValueError('Wrong repository')
    if expected_ref not in ['refs/heads/swiftui-first-native', 'refs/heads/cell-ios-photos-host-final']:
        raise ValueError('Unknown reviewed route')
    if environment.get('GITHUB_REF') != expected_ref: raise ValueError('Wrong reviewed route')
    if environment.get('GITHUB_EVENT_NAME') != 'push': raise ValueError('Wrong event')
    if environment.get('GITHUB_WORKFLOW_SHA') != source: raise ValueError('Workflow source differs')
    if str(uuid.UUID(device)).upper() != device.upper(): raise ValueError('Invalid simulator identity')
    expected = {'schema': 'celluloid.swiftui.owned-simulator.v1', 'device_id': device,
                'source_sha': source, 'run_id': environment.get('GITHUB_RUN_ID'),
                'run_attempt': environment.get('GITHUB_RUN_ATTEMPT'),
                'created_by_this_job': True, 'absent_before_create': True}
    for key, value in expected.items():
        if receipt.get(key) != value: raise ValueError('Owned simulator mismatch: ' + key)
    if not re.fullmatch(r'[1-9][0-9]*', str(receipt.get('run_id'))): raise ValueError('Invalid run identity')
    if not re.fullmatch(r'[1-9][0-9]*', str(receipt.get('run_attempt'))): raise ValueError('Invalid attempt identity')
    if any(type(receipt.get(key)) is not bool for key in ['created_by_this_job', 'absent_before_create']): raise ValueError('Ownership booleans are malformed')
    if not receipt.get('device_name', '').startswith('Celluloid iOS27 '): raise ValueError('Not a newly owned test device')
    if receipt.get('runtime_id') != 'com.apple.CoreSimulator.SimRuntime.iOS-27-0': raise ValueError('Wrong runtime')
    matches = [(runtime, item) for runtime, items in observed['devices'].items() for item in items if item.get('udid') == device]
    if len(matches) != 1: raise ValueError('Observed simulator is ambiguous or absent')
    runtime, item = matches[0]
    if runtime != receipt['runtime_id'] or item.get('name') != receipt['device_name'] or item.get('state') != 'Booted' or item.get('isAvailable') is not True:
        raise ValueError('Observed owned simulator differs or is not booted')
    return {key: receipt[key] for key in ['device_id', 'source_sha', 'run_id', 'run_attempt']}



def phase_budget(stage, receipt, now=None):
    now = time.monotonic() if now is None else now
    start = receipt.get('job_started_monotonic'); deadline = receipt.get('work_deadline_monotonic')
    if any(type(value) not in [int, float] or not math.isfinite(value) for value in [start, deadline]):
        raise ValueError('Missing finite shared job clock')
    if not 0 <= start <= now < deadline <= start + 2610:
        raise ValueError('Shared work clock expired or would exceed the fixed 45-minute job reserve')
    remaining = deadline - now - 15
    if remaining <= 0: raise ValueError('Shared work deadline has no cleanup allowance')
    if stage == 'bootstrap' and remaining < 720: raise ValueError('Shared work deadline cannot admit the full bootstrap phase')
    return min(720 if stage == 'bootstrap' else 600, remaining)


def fresh_owned_device_observation(output):
    """One fresh query; no cache, filtering guess, retry or expanded20s cap."""
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    log=output/'owned-device-observation.log';receipt=output/'owned-device-observation.json'
    if log.exists() or receipt.exists():raise ValueError('Refuse stale owned-device observation')
    started=time.monotonic();deadline=started+20
    command=[sys.executable,'Scripts/run_bounded.py','--seconds','20','--label','photos-owned-device-observation',
             '--deadline-monotonic',str(deadline),'xcrun','simctl','list','devices','available','-j']
    with log.open('wb') as stream:
        code=subprocess.call(command,stdout=stream,stderr=subprocess.STDOUT)
    elapsed=time.monotonic()-started;raw=log.read_text(errors='replace')
    late=elapsed>20;unsafe=(code!=0 or late or 'BOUNDED_COMMAND_TIMEOUT' in raw or 'CLEANUP_UNCONFIRMED' in raw)
    dump(receipt,{'schema':'Celluloid.PhotosOwnedDeviceObservation.1','source_sha':os.environ.get('GITHUB_SHA'),
         'run_id':os.environ.get('GITHUB_RUN_ID'),'run_attempt':os.environ.get('GITHUB_RUN_ATTEMPT'),
         'started_monotonic':started,'deadline_monotonic':deadline,'elapsed_seconds':elapsed,'limit_seconds':20,
         'exit_code':code,'late_completion':late,'prohibit_further_native':unsafe,
         'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'fresh_query_count':1})
    if unsafe:raise ValueError('Fresh owned-device query failed or exceeded its parent20s deadline; no further native work')
    rows=[]
    for match in re.finditer(r'^\s*\{',raw,re.M):
        try:value,_=json.JSONDecoder().raw_decode(raw[match.start():].lstrip())
        except json.JSONDecodeError:continue
        if isinstance(value,dict) and 'devices' in value:rows.append(value)
    if len(rows)!=1:raise ValueError('Missing/ambiguous fresh device observation')
    return rows[0]


def admission(stage, device, derived, output, receipt_path, expected_ref='refs/heads/swiftui-first-native'):
    repository = Path.cwd().resolve()
    derived = Path(derived).resolve(); output = Path(output).resolve()
    derived.relative_to(repository / '.build'); output.relative_to(repository / 'build')
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if source != os.environ.get('GITHUB_SHA'): raise ValueError('Checked-out source differs')
    subprocess.run(['git', 'diff', '--exit-code', 'HEAD', '--'], check=True)
    receipt = load(receipt_path)
    phase_budget(stage, receipt)
    if expected_ref == 'refs/heads/cell-ios-photos-host-final':
        observed = fresh_owned_device_observation(output)
    else:
        observed = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', 'available', '-j'], text=True, timeout=20))
    if expected_ref == 'refs/heads/cell-ios-photos-host-final' and stage != 'bootstrap':
        raise ValueError('Dedicated host route may only reuse the fixture bootstrap')
    binding = validate_owner(receipt, device, os.environ, observed, expected_ref=expected_ref)
    phase_budget(stage, receipt)
    if stage == 'bootstrap' and (output / 'verified-library.json').exists(): raise ValueError('Bootstrap already succeeded; do not import twice')
    if stage in ['pristine', 'preservation']:
        manifest = load(output / 'verified-library.json')
        for key, value in binding.items():
            if manifest.get(key) != value: raise ValueError('Seeded manifest binding differs: ' + key)
        if manifest.get('authorization_read_write') != 'authorized': raise ValueError('Missing actual full Photos grant')
    dump(output / f'{stage}-admission.json', {**binding, 'stage': stage, 'source_ref': expected_ref, 'derived_data': str(derived),
         'only_owned_simulator': True, 'expected_methods': methods(stage) if stage in STAGES else []})


def fixture_files():
    paths = [Path('/tmp/celluloid-fixture.png'), Path('/tmp/celluloid-fixture-2.png')] + sorted(Path('/tmp').glob('celluloid-composition-*.png'))
    if {p.name for p in paths} != set(FIXTURES) or len(paths) != 6: raise ValueError('Unexpected fixture file set; no import allowed')
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def readiness_rows(log):
    return [json.loads(line.split('PHOTOS_LIBRARY_READINESS ', 1)[1]) for line in log.splitlines() if line.startswith('PHOTOS_LIBRARY_READINESS ')]


def reconcile_library(before, after, hashes, binding):
    if before.get('authorization') != 3 or after.get('authorization') != 3: raise ValueError('Actual PhotoKit authorization is not full read/write')
    for row in [before, after]:
        if type(row.get('asset_count')) is not int or not 0 <= row['asset_count'] <= 64: raise ValueError('Invalid bounded library count')
        if not isinstance(row.get('asset_identifiers'), list) or not all(isinstance(v, str) and v for v in row['asset_identifiers']): raise ValueError('Missing real asset identity list')
    before_ids = before.get('asset_identifiers', []); after_ids = after.get('asset_identifiers', [])
    if len(before_ids) != before.get('asset_count') or len(set(before_ids)) != len(before_ids): raise ValueError('Invalid observed baseline identities')
    if len(after_ids) != after.get('asset_count') or len(set(after_ids)) != len(after_ids): raise ValueError('Invalid observed final identities')
    if before.get('synthetic') != []: raise ValueError('Controlled fixture names were already present; do not retry imports')
    fixtures = after.get('synthetic', [])
    if len(fixtures) != 6 or {r['filename'] for r in fixtures} != set(FIXTURES): raise ValueError('Not exactly six controlled fixtures')
    if set(before_ids) - set(after_ids): raise ValueError('Baseline stock identities disappeared')
    added_ids = set(after_ids) - set(before_ids)
    if len(added_ids) != 6 or {r['identifier'] for r in fixtures} != added_ids: raise ValueError('Imported identity delta differs')
    for row in fixtures:
        if row.get('sha256') != hashes[row['filename']]: raise ValueError('Fixture bytes differ')
        if (row.get('width'), row.get('height')) != FIXTURES[row['filename']]: raise ValueError('Fixture dimensions differ')
        if not isinstance(row.get('creation_date_utc'), str): raise ValueError('Missing actual fixture date')
    return {'schema': 'celluloid.swiftui.seeded-library.v1', **binding,
            'authorization_read_write': 'authorized', 'baseline_asset_count': len(before_ids),
            'seeded_asset_count': len(after_ids), 'baseline_asset_ids': sorted(before_ids),
            'seeded_asset_ids': sorted(after_ids), 'added_asset_ids': sorted(added_ids), 'fixture_count': 6,
            'fixtures': sorted(fixtures, key=lambda item: item['filename']), 'baseline_id_set_preserved': True,
            'scope': 'Real PhotoKit library in one owned simulator; not Photos application extension-host UI.'}


from run_picker_acceptance import qualify_runtime_warnings, runtime_warning_report

def verify_summary(stage, summary, log):
    expected = methods(stage)
    for key, value in {'totalTestCount': len(expected), 'passedTests': len(expected), 'failedTests': 0,
                       'skippedTests': 0, 'expectedFailures': 0}.items():
        if type(summary.get(key)) is not int or summary[key] != value: raise ValueError('Terminal XCTest count differs: ' + key)
    if summary.get('result') != 'Passed' or summary.get('testFailures'): raise ValueError('Terminal XCTest result is not clean')
    qualify_runtime_warnings(summary)
    passed = re.findall(r"Test Case '-\[(CelluloidTests)\.([A-Za-z0-9_]+) ([A-Za-z0-9_]+)\]' passed", log)
    actual = ['/'.join(item) for item in passed]
    if len(actual) != len(expected) or set(actual) != set(expected): raise ValueError('Actual passed test identities differ')


def verify_pristine(manifest, row):
    if row.get('authorization') != 3: raise ValueError('Photos grant changed')
    expected = set(manifest['baseline_asset_ids']) | {item['identifier'] for item in manifest['fixtures']}
    if set(row.get('asset_identifiers', [])) != expected or row.get('asset_count') != len(expected): raise ValueError('Pristine library identities changed')
    actual = {(r['identifier'], r['filename'], r.get('sha256')) for r in row.get('synthetic', [])}
    intended = {(r['identifier'], r['filename'], r['sha256']) for r in manifest['fixtures']}
    if actual != intended: raise ValueError('Pristine fixture resources changed')



def safety_record(phase, status, log):
    timeout = status == 124 or 'BOUNDED_COMMAND_TIMEOUT' in log
    uncertain = any(marker in log for marker in ['CLEANUP_UNCONFIRMED', 'signal_denied', 'wait_failed'])
    exhausted = any(marker in log for marker in ['Shared Photos bootstrap', 'Shared work clock expired', 'Shared work deadline'])
    return {'phase': phase, 'exit_code': status, 'timeout_observed': timeout,
            'cleanup_uncertain_observed': uncertain, 'shared_deadline_exhausted': exhausted,
            'prohibit_further_simctl': timeout or uncertain or exhausted or (phase == 'bootstrap' and status != 0)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['admit', 'budget', 'selectors', 'fixture-files', 'finish-bootstrap', 'payload', 'verify', 'safety'])
    parser.add_argument('arguments', nargs='*')
    options = parser.parse_args(); args = options.arguments
    if options.action == 'admit': admission(*args)
    elif options.action == 'safety':
        phase, status, folder = args; output = Path(folder)
        paths = [output / f'{phase}.log', output / f'{phase}-summary-collection.log']
        if phase == 'bootstrap': paths += [output / 'registration.log', output / 'photos-grant.log', output / 'fixture-generation.log']
        log = '\n'.join(p.read_text(errors='replace') if p.stat().st_size <= 80_000_000 else 'CLEANUP_UNCONFIRMED oversized log' for p in paths if p.is_file())
        dump(output / f'{phase}-safety.json', safety_record(phase, int(status), log))
    elif options.action == 'budget':
        stage, receipt_path, kind = args
        now = time.monotonic(); seconds = phase_budget(stage, load(receipt_path), now=now)
        print(now + seconds if kind == 'deadline' else seconds)
    elif options.action == 'selectors':
        for item in methods(args[0]): print('-only-testing:' + item)
    elif options.action == 'fixture-files': print(json.dumps(fixture_files(), sort_keys=True))
    elif options.action == 'finish-bootstrap':
        output = Path(args[0]); admission_record = load(output / 'bootstrap-admission.json')
        rows = readiness_rows((output / 'bootstrap.log').read_text())
        if len(rows) != 2: raise ValueError('Bootstrap has missing/ambiguous readiness records')
        binding = {key: admission_record[key] for key in ['device_id', 'source_sha', 'run_id', 'run_attempt']}
        dump(output / 'verified-library.json', reconcile_library(rows[0], rows[1], load(output / 'fixture-files.json'), binding))
    elif options.action == 'payload':
        manifest = load(Path(args[0]) / 'verified-library.json')
        print(json.dumps({'source_sha': manifest['source_sha'], 'fixtures': manifest['fixtures']}, separators=(',', ':')))
    elif options.action == 'verify':
        stage, folder = args; output = Path(folder); log = (output / f'{stage}.log').read_text()
        summary = load(output / f'{stage}-summary.json')
        dump(output / f'{stage}-runtime-warnings.json', runtime_warning_report(summary))
        verify_summary(stage, summary, log)
        if stage == 'pristine':
            rows = readiness_rows(log)
            if len(rows) != 1: raise ValueError('Pristine reconciliation is missing')
            verify_pristine(load(output / 'verified-library.json'), rows[0])
        dump(output / f'{stage}-verified.json', {'source_sha': os.environ['GITHUB_SHA'], 'stage': stage,
             'passed_count': len(methods(stage)), 'actual_methods_verified': methods(stage), 'native_result': 'Passed'})


if __name__ == '__main__': main()
