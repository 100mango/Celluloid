#!/usr/bin/env python3
"""Fixed original UIKit execution accounting and first-step clock admission.

This helper never starts a process, changes Photos, or operates a simulator.
The workflow retains source, fixture, product, and command-outcome proof; this
module verifies every original named XCTest invocation and the remaining clock.
Nominal tail reservations do not promise zero process cleanup or action overhead.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import os
import re
import sys
import time

from consumer_runtime_binding import MODEL_SCALES, validate as validate_runtime, validate_raw_execution
from platform_rendering_contract import require
from mac_host_transport import load_json
from original_ios_process_guard import GuardRefusal
from validation_route import STORE_SCREENSHOTS, validate_route

ROOT = Path(__file__).resolve().parents[1]
# Exact public parent a940bcdf8a92811210bcfacf84141dceb6c3fcd3. The bound
# source bytes make the intentionally small declaration reader unambiguous.
SOURCE_HASHES = {'CelluloidTests/AdaptiveInterfaceTests.swift': 'b79b23a853bbc536e6f974eb4dfc25a1b41184afc09ecbcd91eb936e2892f573',
 'CelluloidTests/AdjustmentDataTests.swift': '5d6da7adf98e64814cbef2411c656702a73edb10f1adc4a0b320eb53b09b7086',
 'CelluloidTests/AdjustmentPreservationPhotoKitTests.swift': 'a3a05edb6cd6c66adf0b1c387d53b825416aa540b8f301f17b54ee63597007b7',
 'CelluloidTests/CelluloidTestFixtures.swift': '09a0c7c1e47d4cdd96a79f55c5ddf326e73e8e6d5cd378a7599054a45a449ed9',
 'CelluloidTests/CollageCompositionTests.swift': '07edd5f8ad2531b1792cba4057f98ce8cb5cbf862b1cc4779b7dcb0d67143c0f',
 'CelluloidTests/EditorRegressionTests.swift': '558db7be201497c738a30aeab15922a33d61495f041ff9b964845c6c7af7ee24',
 'CelluloidTests/ExportAndInteractionTests.swift': '0fc3a1a79de3feb0755d9383ada2dc7f586c96059a498f6ab76b6907720d3757',
 'CelluloidTests/LargeDecoratedExportTests.swift': '89a1adf0a0b02928caba8e981ce189987de2a9436216c26f14bce55d18b883d4',
 'CelluloidTests/MacPhotosManufacturedAdjustmentTests.swift': 'f4c7a7a16bf5414e6c2a2716bc146bdc216f7ea966a80207acce8a7667584890',
 'CelluloidTests/OverlayResizeTests.swift': '8b547bbd342bb8e52217ad49f7c6dd729625dc791e2f147f0a6aad842032a5ab',
 'CelluloidTests/PhotosOutputWriteTests.swift': '01afee7d0dd4fbdfbc89f4d6017199309346f0042aa26fd12fd46605914e2c7e',
 'CelluloidUITests/CelluloidSystemPermissionTests.swift': '7ca40d9ca8a6649a16943f304316a4536591e2aaab524de866d78b600f513f70',
 'CelluloidUITests/CelluloidUITests.swift': '94f9fffbbf2693038fe85867bd31426959bf099af7f05b681182ef6e97361256'}
SOURCE_METHODS = {
    'CelluloidTests.AdaptiveInterfaceTests': (
        'testBubbleArtworkTextHasIdenticalReadablePixelsInLightAndDark',
        'testBubbleDecorationExposesEditableTextWithoutChangingArtworkTypography',
        'testBubbleFontFittingPreservesSystemFontFamily',
        'testCaptionEditorReadableColumnAcrossCompactAndResizedPadGeometry',
        'testEditorToolbarTitlesScaleAndFitWithoutCoveringPreview',
        'testFullLocalizedTitlesFitAtNormalAndLargestTextAcrossViewports',
        'testPhotoStatusBackdropUsesExplicitNavigationAndToolbarInsets',
        'testPhotosExtensionHostBackdropAdaptsWithoutChangingPhotoCanvas',
        'testSavedScreenHidesItsUnusedNativeToolbarAfterLayout',
        'testShareDismissalFitsCompactLandscapeAndBothAppearances',
    ),
    'CelluloidTests.AdjustmentDataTests': (
        'testActualMacEncodedFixturesDecodeWithOriginalUIKitReader',
        'testAggregateRepeatedTextBudgetRejectsWithoutTruncation',
        'testEncodedByteBudgetRejectsBeforeUnarchiving',
        'testEncodingRejectsUnreopenableStateInsteadOfDroppingLayers',
        'testEveryShippingAssetAndFilterCanRoundTrip',
        'testExplicitEmptyArraysAreAlsoAccepted',
        'testExportSyntheticUIKitCompatibilityFixtures',
        'testIndividualUnicodeTextBudgetRejectsWithoutTruncation',
        'testLegacyArchiveRoundTripsWithoutChangingItsDictionary',
        'testLegacyArchivesMayOmitEmptyArrays',
        'testMalformedArchivesAndUnexpectedClassesAreRejected',
        'testMissingAndMistypedGeometryAreRejected',
        'testNonfiniteAndNegativeGeometryAreRejected',
        'testProbe32BitGeometryArchiveRepresentation',
        'testResourceBoundariesPreserveEveryLegacyLayerAndTextUnit',
        'testSmallSharedReferenceArchiveRejectsExcessiveLayers',
        'testUnknownAssetsAreRejectedBeforeTheyReachImageRendering',
        'testUnknownFilterAndInvalidCollectionsAreRejected',
    ),
    'CelluloidTests.AdjustmentPreservationPhotoKitTests': (
        'testActualBoundInputsPreserveOpaqueEditsAcrossIndependentSessions',
        'testActualPhotosOutputDestinationsIsolateLateWrites',
        'testWrongAuthorizationNeverReachesSyntheticSetup',
    ),
    'CelluloidTests.CollageCompositionTests': (
        'testDistinctAsymmetricSourcesComposeTwoThreeFourAndReorderWithoutReuse',
    ),
    'CelluloidTests.EditorRegressionTests': (
        'testCancelledExtensionNeverInvokesHostCompletion',
        'testCollageTemplatesHaveValidPolygons',
        'testEditorRendersAndRestoresWithoutDuplicatingOverlays',
        'testExtensionNegotiatesKnownFormatWithoutDecodingUnboundData',
        'testExtensionStartsRendersAndFinishesSeededPhotoWithoutLibraryMutation',
        'testExtensionWithoutInputCompletesWithFailureExactlyOnce',
        'testHomeLayoutDoesNotCollapseOrOverlapAcrossPhoneAndPadSizes',
        'testNoSourceImageIsSafe',
        'testOrientedAsymmetricSourceExportsCorrectDimensionsAndStickerPixels',
        'testPhotosLibraryBootstrapReadiness',
        'testPickerCallbacksRemainBoundToTheirOriginalEditingSession',
        'testPrivacyPolicyUsesApprovedHTTPSDestinationAndAccessibleControl',
        'testProtectedPhotosSessionDoesNotOfferDiscardingChanges',
        'testReadOnlyAdjustmentKeepsOpaqueBytesAndCurrentPixelsUntilNewInput',
        'testReconcileSyntheticPhotosAfterImport',
        'testResourceBudgetRejectsSnapshotBeforeDecodeOrRasterWithoutTruncation',
    ),
    'CelluloidTests.ExportAndInteractionTests': (
        'testAsyncDecoratedExportExcludesVisibleEditorHandles',
        'testAsyncMissingSourceCompletesWithFailureExactlyOnce',
        'testCancelledAndSupersededExportNeverReturnsStaleSuccess',
        'testDegenerateCanvasAndOverflowAreRejectedBeforeUIKitRescale',
        'testExtendedRangeSourceMatchesLegacyRendererBitmapAndPixels',
        'testFiniteComponentsWithOverflowingTransformedBoundsAreRejected',
        'testFullCanvasControlsKeepEveryStrictPixelOracle',
        'testGesturePreservesRebasedScaleAndControlsStayFortyFourScreenPoints',
        'testOffMainCompositeMatchesLegacyAffineAlphaAndColorRendering',
        'testReleasedWarmingCopyWithoutCropKeepsStrictPixels',
        'testSourceScaleAndExifDoNotChangeFullResolutionWhenDecorated',
        'testStreamingTileBoundariesAndManyOverlaysMatchLegacyPixels',
        'testTwelveMegapixelExportPreservesDimensionsAndAllowsMainQueueHeartbeat',
        'testUnevenRotatedAndScaledStripCanvasesMatchLegacyPixels',
    ),
    'CelluloidTests.FilterTests': (
        'testExifOrientationIsAppliedExactlyOnce',
        'testFacePixelationWithoutFacesIsANoOp',
        'testImageWithoutBackingPixelsDoesNotCrash',
        'testInvalidBlurRadiusIsANoOp',
        'testInvertActuallyInvertsPixels',
        'testOriginalReturnsTheSameImageAndPixels',
        'testPresetsMatchTheirShippingCoreImageFilters',
        'testUIImageFilteringPreservesScaleAndDisplayOrientation',
    ),
    'CelluloidTests.LargeDecoratedExportTests': (
        'testFortyEightMegapixelDecoratedExportAndInFlightCancellation',
        'testFullCanvasControlFortyEightMegapixelMetricsAndCancellation',
        'testReleasedWarmingCopyWithoutCropMetricsAndCancellation',
        'testTwelveMegapixelManyOverlaysKeepOnlyOneBoundedTileAndCancel',
    ),
    'CelluloidTests.MacPhotosManufacturedAdjustmentTests': (
        'testManufacturedMacArchiveThroughOriginalUIKitReaderAndCompositor',
    ),
    'CelluloidTests.OverlayResizeTests': (
        'testBubbleAndStickerIndividuallyKeepTheirRenderedPixelsAfterResize',
        'testHalvingCanvasHalvesCenterAndFullAffineTransform',
        'testLegacyArchiveKeepsAbsolutePointsAtFirstValidLayoutThenTracksResizes',
        'testNewArchiveRestoresAcrossDevicesBeforeOrAfterSourceAndLayout',
        'testOptionalReferenceCanvasRejectsWrongTypeZeroNegativeAndNonfiniteValues',
        'testOrientedSourceDecorationPixelsStayFixedAfterResize',
        'testOriginalUndecoratedOutputDoesNotRequirePreviewLayout',
        'testPhotosExtensionRestartWithoutAdjustmentClearsDecorationsFilterAndCancellation',
        'testPortraitLandscapeSplitViewAndRoundTripPreserveGeometryAndExportPixels',
        'testSourceReplacementReappliesSameFilterAndResetInputClearsOldSession',
        'testZeroSizedIntermediateLayoutRetainsLastCoordinateSpace',
    ),
    'CelluloidTests.PhotosOutputWriteTests': (
        'testCancelAfterCommitBeforeDeliveryRemovesOnlyOwnedOutput',
        'testCancelAfterDeliveryDoesNotRemovePhotosOwnedOutput',
        'testCanceledBeforeStartNeverWritesAndCompletesOnce',
        'testCancellationAtObservedPrewriteBarrierPreventsAbandonedDestination',
        'testClaimRetainsDestinationReservationUntilHostCompletionReturns',
        'testFileWriteFailureCompletesOnceWithoutAReplacement',
        'testNewWriteSucceedsAfterSupersedingPausedOldWrite',
        'testNonMissingStagingCleanupFailureIsReportedWithoutClaimingDeletion',
        'testUnexpectedDestinationReuseCannotOverwriteOrDeleteAnotherOwner',
    ),
    'CelluloidUITests.CelluloidSystemPermissionTests': (
        'testRealGrantedAccessCanSelectFixture',
        'testRealLimitedSelectionAndManagement',
        'testRealRevokedAccessClearsSelectionAndHasRecovery',
    ),
    'CelluloidUITests.CelluloidUITests': (
        'testAccessibilityGrantedPickerEditorAndSaved',
        'testAccessibilityHomeAndDeniedPicker',
        'testDeniedPhotosShowsRecoveryAndCanCancelRepeatedly',
        'testHomeChoiceGeometryInEnglishAndChineseAcrossRotation',
        'testLimitedEmptyPhotosHasManagementAndAdaptiveLayout',
        'testPrivacyPolicyEntryRemainsAccessibleAndCanClose',
        'testSeededPhotoEditingSaveAndReopen',
        'testTwoPhotoCollageZoomRotateAndSave',
    ),
}

ROWS = {
    'compact-phone': 'iPhone SE (3rd generation)',
    'large-phone': 'iPhone 18 Pro Max',
    'small-ipad': 'iPad mini (A17 Pro)',
    'large-ipad': 'iPad Pro 13-inch (M5)',
}
ROW_COUNTS = {'compact-phone': 108, 'large-phone': 102, 'small-ipad': 100, 'large-ipad': 102}
EXECUTION_SCHEMA = 'Celluloid.UIKitFullShippingExecution.1'
CLOCK_SCHEMA = 'Celluloid.UIKitFullShippingClock.1'
EXECUTION_SECONDS = 56 * 60
TAIL_SECONDS = 240 + 120 + 60 + 180 + 60
WORK_SECONDS = EXECUTION_SECONDS - TAIL_SECONDS
OUTER_JOB_SECONDS = 60 * 60
PREREQUISITES = ('producer', 'source_before', 'prepare', 'stage_fixture', 'bootstrap',
                 'product_after', 'cleanup', 'source_after')

# These names select existing workflow commands, never arbitrary commands or
# caller-chosen limits. The bootstrap cap is an outer envelope: its existing
# per-command import/probe ceilings remain in probe_photos_bootstrap.py.
WORK_CEILINGS = {
    'source-before': 60, 'release-build': 600, 'build': 900,
    'pre-boot-memory': 20, 'pre-boot-vm': 20, 'pre-boot-swap': 20,
    'boot': 60, 'bootstatus': 600, 'fixture-stage': 600,
    'registration': 45, 'privacy': 60, 'appearance': 60,
    'bootstrap': WORK_SECONDS, 'summary': 30, 'consumer-contract': 60,
    'evidence-screens': 180, 'diagnostics': 180,
    'units': 900, 'bootstrap-readiness': 360, 'bootstrap-reconcile': 360,
    'photos-integration': 900, 'permission-granted': 360,
    'permission-revoked': 360, 'permission-limited': 360,
    'preflight': 900, 'ui': 900, 'dark': 900, 'preservation': 600,
}
# (original ceiling, absolute deadline from first step). No extra minute is
# hidden in this 660-second tail; 240 seconds lie outside the 56-minute clock.
TAIL_PHASES = {
    'product-readbacks': (240, WORK_SECONDS + 240),
    'shutdown': (60, WORK_SECONDS + 300),
    'delete': (60, WORK_SECONDS + 360),
    'source-after': (60, WORK_SECONDS + 420),
    'collection': (180, WORK_SECONDS + 600),
    'upload': (60, EXECUTION_SECONDS),
}


def _case(owner, method):
    return '-[' + owner + ' ' + method + ']'


def source_inventory(root=ROOT):
    """Verify exact test bytes and every class/method, including FilterTests."""
    root = Path(root)
    paths = sorted(path for directory in ('CelluloidTests', 'CelluloidUITests')
                   for path in (root / directory).glob('*.swift'))
    require({path.relative_to(root).as_posix() for path in paths} == set(SOURCE_HASHES),
            'Original UIKit source file inventory changed')
    found = {}
    for path in paths:
        name = path.relative_to(root).as_posix()
        require(not path.is_symlink() and path.is_file() and path.stat().st_size <= 500_000,
                'Invalid original UIKit test source: ' + name)
        data = path.read_bytes()
        require(hashlib.sha256(data).hexdigest() == SOURCE_HASHES[name],
                'Original UIKit test source bytes changed: ' + name)
        owner = None
        for line in data.decode('utf8').splitlines():
            match = re.match(r'^(?:@\w+\s+)*(?:(?:private|final)\s+)*class (\w+)\s*:\s*(\w+)', line)
            if match:
                owner = path.parent.name + '.' + match[1] if match[2] == 'XCTestCase' else None
            match = re.match(r'^    func (test\w+)\s*\(', line)
            if match:
                require(owner is not None, 'Unknown original UIKit test owner')
                found.setdefault(owner, []).append(match[1])
    require({owner: tuple(sorted(methods)) for owner, methods in found.items()} == SOURCE_METHODS,
            'Original UIKit class/method inventory changed')
    cases = sorted(_case(owner, method) for owner, methods in found.items() for method in methods)
    require(len(cases) == len(set(cases)), 'Duplicate original UIKit source method')
    return cases


def expected_phases(row):
    require(type(row) is str and row in ROWS, 'Unknown original UIKit row')
    phases = ['units', 'bootstrap-readiness', 'bootstrap-reconcile', 'photos-integration']
    if row == 'compact-phone':
        phases += ['permission-granted', 'permission-revoked', 'permission-limited']
    if row == 'large-phone':
        phases += ['preflight']
    phases += ['ui']
    if row in ('compact-phone', 'large-ipad'):
        phases += ['dark']
    if row == 'compact-phone':
        phases += ['preservation']
    return phases


def expected_cases(row, root=ROOT):
    all_cases = source_inventory(root)
    editor = 'CelluloidTests.EditorRegressionTests'
    ui = 'CelluloidUITests.CelluloidUITests'
    permissions = 'CelluloidUITests.CelluloidSystemPermissionTests'
    phases = {
        'bootstrap-readiness': [_case(editor, 'testPhotosLibraryBootstrapReadiness')],
        'bootstrap-reconcile': [_case(editor, 'testReconcileSyntheticPhotosAfterImport')],
        'photos-integration': [
            _case('CelluloidTests.AdaptiveInterfaceTests', 'testFullLocalizedTitlesFitAtNormalAndLargestTextAcrossViewports'),
            _case('CelluloidTests.CollageCompositionTests', 'testDistinctAsymmetricSourcesComposeTwoThreeFourAndReorderWithoutReuse'),
            _case('CelluloidTests.OverlayResizeTests', 'testPhotosExtensionRestartWithoutAdjustmentClearsDecorationsFilterAndCancellation'),
            _case(editor, 'testExtensionStartsRendersAndFinishesSeededPhotoWithoutLibraryMutation'),
        ],
        'ui': [_case(ui, method) for method in SOURCE_METHODS[ui]],
        'permission-granted': [_case(permissions, 'testRealGrantedAccessCanSelectFixture')],
        'permission-revoked': [_case(permissions, 'testRealRevokedAccessClearsSelectionAndHasRecovery')],
        'permission-limited': [_case(permissions, 'testRealLimitedSelectionAndManagement')],
        'preflight': [_case(ui, method) for method in ('testLimitedEmptyPhotosHasManagementAndAdaptiveLayout', 'testSeededPhotoEditingSaveAndReopen')],
        'dark': [_case(ui, method) for method in ('testSeededPhotoEditingSaveAndReopen', 'testTwoPhotoCollageZoomRotateAndSave')],
        'preservation': [case for case in all_cases if case.startswith('-[CelluloidTests.AdjustmentPreservationPhotoKitTests ')],
    }
    excluded = {case for phase in ('bootstrap-readiness', 'bootstrap-reconcile', 'photos-integration', 'preservation') for case in phases[phase]}
    phases['units'] = [case for case in all_cases if case.startswith('-[CelluloidTests.') and case not in excluded]
    require(len(phases['units']) == 86, 'Original pre-import unit inventory changed')
    result = {phase: sorted(phases[phase]) for phase in expected_phases(row)}
    require(sum(map(len, result.values())) == ROW_COUNTS[row], 'Original UIKit row inventory changed')
    return result


def phase_files(phase):
    """Only these fixed, source-owned file names can supply phase evidence."""
    require(phase in {name for row in ROWS for name in expected_phases(row)}, 'Unknown test phase')
    stem = {'bootstrap-readiness': 'bootstrap-readiness-before-import',
            'bootstrap-reconcile': 'bootstrap-reconcile-all'}.get(phase, phase)
    return stem + '.log', stem + '.summary.json'


def expected_prerequisites(row):
    expected_phases(row)
    return list(PREREQUISITES) + (['release_build'] if row == 'compact-phone' else [])


def validate_context(context):
    if type(context) is dict and 'validation_route' in context:
        from original_ios_process_guard import validate_context as validate_guard_context
        return validate_guard_context(context)
    require(type(context) is dict and set(context) == {'source_sha', 'run_id', 'run_attempt', 'row'},
            'Malformed UIKit execution identity')
    require(type(context['source_sha']) is str and re.fullmatch(r'[0-9a-f]{40}', context['source_sha']) is not None,
            'Invalid UIKit source identity')
    for key in ('run_id', 'run_attempt'):
        require(type(context[key]) is str and re.fullmatch(r'[1-9][0-9]*', context[key]) is not None,
                'Invalid UIKit execution ' + key)
    expected_phases(context['row'])
    return dict(context)


def _admit_row_phase(context, phase):
    row = context['row']
    test_names = {name for key in ROWS for name in expected_phases(key)}
    # These labels are accounting keys, not model claims. Store capture's
    # separate runner binds its actual devices and two unchanged UI methods.
    allowed = {'bootstrap-readiness', 'bootstrap-reconcile', 'ui'} if context.get('validation_route') == STORE_SCREENSHOTS else set(expected_phases(row))
    require(phase not in test_names or phase in allowed, 'Command phase belongs to another UIKit row')
    require(phase != 'release-build' or row == 'compact-phone', 'Release compile belongs only to compact-phone')


def clock_status(clock, context, now_monotonic=None, now_unix=None):
    context = validate_context(context)
    keys = {'schema', *context, 'started_monotonic', 'started_unix', 'execution_budget_seconds'}
    require(type(clock) is dict and set(clock) == keys and clock['schema'] == CLOCK_SCHEMA,
            'Malformed first-step UIKit clock')
    require(all(clock[key] == value and type(clock[key]) is type(value) for key, value in context.items()),
            'First-step UIKit clock execution identity differs')
    if 'validation_route' in context:
        require(validate_route(clock['validation_route']) == STORE_SCREENSHOTS, 'Wrong capture clock route')
    require(type(clock['execution_budget_seconds']) is int and clock['execution_budget_seconds'] == EXECUTION_SECONDS,
            'Changed original UIKit execution clock')
    now_monotonic = time.monotonic() if now_monotonic is None else now_monotonic
    now_unix = time.time() if now_unix is None else now_unix
    for value in (clock['started_monotonic'], clock['started_unix'], now_monotonic, now_unix):
        require(type(value) in (int, float) and math.isfinite(value) and value > 0, 'Invalid UIKit clock time')
    elapsed = now_monotonic - clock['started_monotonic']
    require(elapsed >= 0 and now_unix >= clock['started_unix'], 'First-step UIKit clock moved backwards')
    # Monotonic time controls admission. The wall interval is reported and used
    # to bind xcresults, never to expire a producer while another row queues.
    return {'elapsed_seconds': elapsed, 'wall_elapsed_seconds': now_unix - clock['started_unix'],
            'remaining_seconds': EXECUTION_SECONDS - elapsed,
            'work_remaining_seconds': WORK_SECONDS - elapsed,
            'within_execution_clock': elapsed <= EXECUTION_SECONDS,
            'execution_budget_seconds': EXECUTION_SECONDS, 'reserved_tail_seconds': TAIL_SECONDS,
            'outside_execution_clock_seconds': OUTER_JOB_SECONDS - EXECUTION_SECONDS}


def admit_phase(clock, context, phase, now_monotonic=None, now_unix=None):
    context = validate_context(context)
    status = clock_status(clock, context, now_monotonic, now_unix)
    require(type(phase) is str and phase in set(WORK_CEILINGS) | set(TAIL_PHASES), 'Unknown fixed UIKit command phase')
    if phase not in {'source-before','source-after','collection','upload'}:
        from original_ios_process_guard import ensure_native_dispatch
        staged = ensure_native_dispatch()
        if context.get('validation_route') == STORE_SCREENSHOTS or (staged or {}).get('validation_route') == STORE_SCREENSHOTS:
            require(staged == context, 'Capture clock differs from actual source/run/row route')
    _admit_row_phase(context, phase)
    ceiling, deadline = TAIL_PHASES.get(phase, (WORK_CEILINGS.get(phase), WORK_SECONDS))
    seconds = min(ceiling, math.floor(deadline - status['elapsed_seconds']))
    require(seconds > 0, 'No remaining allocation for fixed UIKit phase: ' + phase)
    return seconds


def check_completion(clock, context, phase=None, now_monotonic=None, now_unix=None):
    context = validate_context(context)
    status = clock_status(clock, context, now_monotonic, now_unix)
    deadline = EXECUTION_SECONDS
    if phase is not None:
        require(type(phase) is str and phase in set(WORK_CEILINGS) | set(TAIL_PHASES),
                'Unknown fixed UIKit completion phase')
        _admit_row_phase(context, phase)
        deadline = TAIL_PHASES[phase][1] if phase in TAIL_PHASES else WORK_SECONDS
    require(status['elapsed_seconds'] <= deadline, 'Late UIKit phase completion: ' + str(phase))
    return dict(status, completion_phase=phase, completion_deadline_seconds=deadline)


def validate_phase(row, phase, raw_log, summary, expected_device, source_root=ROOT):
    inventory = expected_cases(row, source_root)
    require(phase in inventory, 'Unexpected UIKit execution phase')
    require(type(expected_device) is dict and set(expected_device) == {'id', 'model'}
            and type(expected_device['id']) is str and type(expected_device['model']) is str
            and expected_device['model'] == ROWS[row], 'Prepared device belongs to another UIKit row')
    require(type(raw_log) is str and type(summary) is dict, 'Missing raw log/finalized summary')
    scale = MODEL_SCALES[ROWS[row]]
    binding = validate_runtime(summary, {'scale': scale, 'profile': str(scale) + 'x'}, expected_device)
    accounting = validate_raw_execution(raw_log, summary)
    require(summary['result'] == 'Passed' and summary['failedTests'] == 0 and summary['skippedTests'] == 0
            and summary['expectedFailures'] == 0 and summary.get('testFailures') == [],
            'Failed/skipped/unknown UIKit phase cannot qualify')
    actual = re.findall(r"^\s*Test Case '([^']+)' passed \([0-9]+(?:\.[0-9]+)? seconds\)\.\s*$", raw_log, re.M)
    require(sorted(actual) == inventory[phase], 'Missing/duplicate/unexpected original UIKit method: ' + phase)
    require(not any(marker in raw_log for marker in ('BOUNDED_COMMAND_TIMEOUT', 'BOOTSTRAP_RECOVERED_', 'BOOTSTRAP_TIMEOUT_RECONCILIATION')),
            'Recovered or timed-out UIKit command remains failed')
    for line in raw_log.splitlines():
        if line.startswith('BOUNDED_COMMAND_END '):
            record = load_json(line.split(' ', 1)[1])
            require(type(record.get('exit_code')) is int and record['exit_code'] == 0,
                    'Failed enclosing UIKit command')
    return {'phase': phase, 'case_count': len(actual), 'cases': inventory[phase],
            'runtime_binding': binding, 'raw_execution_accounting': accounting,
            'raw_log_sha256': hashlib.sha256(raw_log.encode('utf8')).hexdigest()}


def _read_file(root, name, maximum):
    root = Path(root).resolve()
    path = root / name
    require(path.parent == root and not path.is_symlink() and path.is_file()
            and 0 < path.stat().st_size <= maximum, 'Missing/unsafe/unbounded UIKit evidence: ' + name)
    return path.read_text(encoding='utf8')


def verify_manifest(manifest, evidence_root, context, clock, source_root=ROOT,
                    now_monotonic=None, now_unix=None):
    context = validate_context(context)
    require('validation_route' not in context, 'Store capture cannot qualify original UIKit execution')
    if os.environ.get('CELLULOID_VALIDATION_SCOPE') == 'original-ios-release':
        from original_ios_process_guard import require_clear
        require_clear(evidence_root, context)
    require(type(manifest) is dict and set(manifest) == {'schema', *context, 'device', 'phases', 'prerequisites'}
            and manifest['schema'] == EXECUTION_SCHEMA, 'Malformed UIKit row manifest')
    require(all(manifest[key] == value and type(manifest[key]) is type(value) for key, value in context.items()),
            'UIKit manifest source/run/attempt/row differs')
    row = context['row']
    prerequisites = manifest['prerequisites']
    require(type(prerequisites) is dict and set(prerequisites) == set(expected_prerequisites(row))
            and all(type(value) is str and value == 'success' for value in prerequisites.values()),
            'Failed/missing original UIKit prerequisite or teardown')
    phases = manifest['phases']
    require(type(phases) is list and all(type(record) is dict and set(record) == {'name', 'exit_code'} for record in phases),
            'Malformed UIKit phase outcomes')
    require([record['name'] for record in phases] == expected_phases(row), 'Missing/duplicate/unexpected or reordered UIKit phases')
    require(all(type(record['exit_code']) is int and record['exit_code'] == 0 for record in phases),
            'Failed/incomplete UIKit phase command')
    status = clock_status(clock, context, now_monotonic, now_unix)
    require(status['within_execution_clock'], 'UIKit row exceeded its first-step execution clock')
    require(not list(Path(evidence_root).glob('bootstrap-reconcile-timeout-*.log')),
            'Bootstrap timeout reconciliation cannot qualify the row')
    now_unix = time.time() if now_unix is None else now_unix
    results = []
    previous_finish = clock['started_unix']
    for phase in expected_phases(row):
        log_name, summary_name = phase_files(phase)
        raw_log = _read_file(evidence_root, log_name, 30_000_000)
        summary = load_json(_read_file(evidence_root, summary_name, 2_000_000))
        result = validate_phase(row, phase, raw_log, summary, manifest['device'], source_root)
        require(previous_finish <= summary['startTime'] < summary['finishTime'] <= now_unix,
                'Stale/overlapping/future UIKit result interval: ' + phase)
        require(summary['finishTime'] <= clock['started_unix'] + WORK_SECONDS,
                'UIKit test execution exceeded the reserved work window: ' + phase)
        previous_finish = summary['finishTime']
        results.append(result)
    return {'schema': 'Celluloid.UIKitFullShippingAccounting.1', **context,
            'device': manifest['device'], 'row_execution_passed': True,
            'original_test_invocation_count': sum(item['case_count'] for item in results),
            'phases': results, 'prerequisites': prerequisites, 'clock': status,
            'release_acceptance': False,
            'scope': 'Original shipping UIKit row accounting; source/product/fixture proof is separately required'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    inventory = commands.add_parser('inventory')
    inventory.add_argument('--row', choices=ROWS, required=True)
    for command in ('admit', 'check-clock', 'verify'):
        sub = commands.add_parser(command)
        sub.add_argument('--row', choices=ROWS, required=True)
        sub.add_argument('--clock', type=Path, required=True)
        if command == 'admit':
            sub.add_argument('--phase', choices=sorted(set(WORK_CEILINGS) | set(TAIL_PHASES)), required=True)
        if command == 'check-clock':
            sub.add_argument('--phase', choices=sorted(set(WORK_CEILINGS) | set(TAIL_PHASES)))
        if command == 'verify':
            sub.add_argument('--root', type=Path, required=True)
            sub.add_argument('--manifest', type=Path, required=True)
            sub.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == 'inventory':
        print(json.dumps(expected_cases(args.row), indent=2, sort_keys=True))
        return
    context = {'source_sha': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID'),
               'run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT'), 'row': args.row}
    if os.environ.get('CELLULOID_VALIDATION_SCOPE') == STORE_SCREENSHOTS['scope']:
        from original_ios_process_guard import staged_context
        staged = staged_context()
        require(staged is not None and staged['row'] == args.row, 'Capture CLI row differs from actual route')
        context = staged
    report = None
    try:
        clock = load_json(_read_file(args.clock.parent, args.clock.name, 10_000))
        if args.command == 'admit':
            print(admit_phase(clock, context, args.phase))
            return
        if args.command == 'check-clock':
            report = check_completion(clock, context, args.phase)
        else:
            manifest = load_json(_read_file(args.manifest.parent, args.manifest.name, 100_000))
            report = verify_manifest(manifest, args.root, context, clock)
    except (ValueError, TypeError, KeyError, OSError, GuardRefusal) as error:
        if args.command == 'verify':
            report = {'schema': 'Celluloid.UIKitFullShippingAccounting.1', **context,
                      'row_execution_passed': False, 'release_acceptance': False, 'error': str(error)}
            args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
        raise SystemExit(str(error)) from error
    if args.command == 'verify':
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
