// Registered synthetic-library acceptance tests. Run only in the explicitly
// marked disposable Simulator phase, after verified Photos authorization.
import XCTest
import UIKit
import Photos
import CryptoKit
@testable import Celluloid
@testable import CelluloidKit

@MainActor
final class AdjustmentPreservationPhotoKitTests: XCTestCase {
    private var ownedIdentifiers = Set<String>()
    private var rejectedOpaqueBytes: Data?
    private let expectedCanvas = CGSize(width: 375, height: 250)
    private var receiptNumber = 0
    private struct ResourceReceipt: Codable, Equatable {
        let type: Int
        let filename: String
        let sha256: String
    }
    private struct Integrity: Codable, Equatable {
        let assetIdentifier: String
        let resources: [ResourceReceipt]
        let originalPixels: String
        let currentPixels: String
        let original: String
        let current: String
        let adjustment: String?
        let identifier: String?
        let version: String?
    }

    func testActualBoundInputsPreserveOpaqueEditsAcrossIndependentSessions() throws {
        try requireAuthorizedSyntheticProbe()
        let original = fixture(left: .red, right: .blue)
        let rendered = fixture(left: .orange, right: .purple)
        let freshPixels = fixture(left: .green, right: .yellow)
        let protectedAsset = try createOwnedAsset(original, label: "opaque")
        let freshAsset = try createOwnedAsset(freshPixels, label: "fresh")
        let pristineProtected = try integrity(protectedAsset, stage: "original-before-opaque-install")
        let pristineFresh = try integrity(freshAsset, stage: "fresh-before-any-export")
        XCTAssertEqual(pristineProtected.originalPixels, digest(try rgba(original)))
        XCTAssertEqual(pristineFresh.originalPixels, digest(try rgba(freshPixels)))
        XCTAssertNotEqual(pristineProtected.originalPixels, pristineFresh.originalPixels)
        let initial = try input(protectedAsset, handles: { _ in true })
        let shared = StickerModel.stickers[0].toJSON()
        let dictionary: NSDictionary = ["filterType": FilterType.Original.rawValue,
            "stickers": NSArray(array: Array(repeating: shared, count: AdjustmentData.maximumDecorations + 1))]
        let opaque = try NSKeyedArchiver.archivedData(withRootObject: dictionary, requiringSecureCoding: true)
        rejectedOpaqueBytes = opaque
        XCTAssertLessThan(opaque.count, AdjustmentData.maximumEncodedBytes, "Shared references expose the count guard independently of byte size")
        XCTAssertThrowsError(try AdjustmentData.decode(opaque))
        try install(PHAdjustmentData(formatIdentifier: AdjustmentData.formatIdentifier, formatVersion: "1.0", data: opaque),
                    image: rendered, asset: protectedAsset, input: initial)
        let before = try integrity(protectedAsset, stage: "opaque-installed-before-session")
        XCTAssertEqual(before.original, pristineProtected.original)
        XCTAssertEqual(before.originalPixels, pristineProtected.originalPixels)
        let expectedRenderedJPEG = try XCTUnwrap(UIImage(data: XCTUnwrap(rendered.jpegData(compressionQuality: 1))))
        XCTAssertEqual(before.currentPixels, digest(try rgba(expectedRenderedJPEG)))
        XCTAssertNotEqual(before.currentPixels, before.originalPixels)
        let protectedInput = try input(protectedAsset, handles: { AdjustmentData.supportIdentifier($0.formatIdentifier, version: $0.formatVersion) })
        let actualData = try XCTUnwrap(protectedInput.adjustmentData)
        XCTAssertEqual(actualData.data, opaque)
        let current = try currentImage(protectedAsset)
        XCTAssertEqual(try rgba(current), try rgba(expectedRenderedJPEG), "The supplied current placeholder is the actual seeded edited rendering")
        let editor = PhotoEditingViewController(); editor.loadViewIfNeeded()
        editor.view.frame = CGRect(x: 0, y: 0, width: 375, height: 667)
        // Independently authored historical dictionary: no optional canvas key,
        // nontrivial filter, text, geometry and affine sticker state.
        let legacy: [String: Any] = ["filterType": "Sepia", "bubbles": [[
            "asset": "say1", "content": "Preserve 世界", "center": NSValue(cgPoint: CGPoint(x: 75, y: 50)),
            "bounds": NSValue(cgRect: CGRect(x: 0, y: 0, width: 90, height: 60)),
            "transform": NSValue(cgAffineTransform: CGAffineTransform(rotationAngle: 0.15))]],
            "stickers": [["imageName": "32", "center": NSValue(cgPoint: CGPoint(x: 220, y: 120)),
            "bounds": NSValue(cgRect: CGRect(x: 0, y: 0, width: 70, height: 70)),
            "transform": NSValue(cgAffineTransform: CGAffineTransform(a: 0.8, b: 0.2, c: -0.2, d: 0.8, tx: 3, ty: -2))]]]
        let legacyBytes = try NSKeyedArchiver.archivedData(withRootObject: legacy, requiringSecureCoding: false)
        let valid = PHAdjustmentData(formatIdentifier: AdjustmentData.formatIdentifier, formatVersion: "1.0", data: legacyBytes)
        let expectedState = try AdjustmentData.decode(legacyBytes)
        try assertLiteralLegacy(expectedState, canvas: nil)
        let oracle = BaseEditPhotoController(); oracle.loadViewIfNeeded()
        oracle.view.frame = editor.view.frame; oracle.sourceImage = original; oracle.view.layoutIfNeeded()
        oracle.restoreFromData(expectedState)
        XCTAssertEqual(oracle.adjustmentData.referenceCanvasSize, expectedCanvas)
        let expectedOutput = try XCTUnwrap(oracle.outputImage)
        XCTAssertNotEqual(try rgba(expectedOutput), try rgba(original), "The valid restoration oracle must actually change pixels")
        let foreign = PHAdjustmentData(formatIdentifier: "example.synthetic.foreign", formatVersion: "1.0", data: opaque)
        let future = PHAdjustmentData(formatIdentifier: AdjustmentData.formatIdentifier, formatVersion: "2.0", data: opaque)
        // Negotiation about another object never assigns a session or preview.
        XCTAssertTrue(editor.canHandle(valid)); XCTAssertTrue(editor.canHandle(actualData))
        XCTAssertFalse(editor.canHandle(foreign)); XCTAssertFalse(editor.canHandle(future))
        XCTAssertNil(editor.input); XCTAssertFalse(editor.isAdjustmentReadOnly)
        editor.startContentEditing(with: protectedInput, placeholderImage: current)
        waitForSwiftUIEditor(editor)
        editor.view.layoutIfNeeded()
        XCTAssertTrue(editor.isAdjustmentReadOnly)
        XCTAssertFalse(editor.shouldShowCancelConfirmation, "Actual protected input has no unsaved edits to discard")
        XCTAssertEqual(editor.preservedAdjustmentData?.data, opaque)
        XCTAssertTrue(editor.preview.image === current)
        XCTAssertNil(editor.outputImage)
        editor.cancelContentEditing()
        let canceledBeforeAnyFinish = expectation(description: "Protected session canceled before its first finish stays silent")
        canceledBeforeAnyFinish.isInverted = true
        editor.finishContentEditing { _ in canceledBeforeAnyFinish.fulfill() }
        wait(for: [canceledBeforeAnyFinish], timeout: 0.1)
        editor.startContentEditing(with: protectedInput, placeholderImage: current)
        waitForSwiftUIEditor(editor)
        XCTAssertTrue(editor.isAdjustmentReadOnly)
        XCTAssertFalse(editor.shouldShowCancelConfirmation, "Actual protected input has no unsaved edits to discard")
        let noChange = expectation(description: "Protected Photos session returns one documented no-change output")
        noChange.assertForOverFulfill = true
        editor.finishContentEditing { output in
            guard let output = output else { XCTFail("Protected session needs a no-change output object"); noChange.fulfill(); return }
            XCTAssertNil(output.adjustmentData)
            XCTAssertFalse(FileManager.default.fileExists(atPath: output.renderedContentURL.path), "No replacement raster may be written")
            noChange.fulfill()
        }
        wait(for: [noChange], timeout: 2)
        XCTAssertEqual(try integrity(protectedAsset, stage: "opaque-after-no-change-finish"), before)
        editor.cancelContentEditing()
        let silent = expectation(description: "Canceled protected session stays silent")
        silent.isInverted = true
        editor.finishContentEditing { _ in silent.fulfill() }
        wait(for: [silent], timeout: 0.1)

        let fresh = try input(freshAsset, handles: { _ in true })
        XCTAssertNil(fresh.adjustmentData)
        editor.startContentEditing(with: fresh, placeholderImage: freshPixels)
        waitForSwiftUIEditor(editor)
        XCTAssertFalse(editor.isAdjustmentReadOnly)
        XCTAssertTrue(editor.shouldShowCancelConfirmation, "Editable bound sessions remain conservative")
        XCTAssertNil(editor.preservedAdjustmentData)
        // More unrelated negotiation must not poison the bound fresh session.
        XCTAssertTrue(editor.canHandle(actualData)); XCTAssertFalse(editor.canHandle(foreign))
        XCTAssertTrue(editor.input === fresh); XCTAssertFalse(editor.isAdjustmentReadOnly)
        try finishNormally(editor, expectedImage: freshPixels)
        XCTAssertEqual(try integrity(freshAsset, stage: "fresh-after-normal-export"), pristineFresh)
        editor.startContentEditing(with: protectedInput, placeholderImage: current)
        waitForSwiftUIEditor(editor)
        XCTAssertTrue(editor.isAdjustmentReadOnly, "Reverse ordering is bound to the actual input, not an earlier negotiation")
        XCTAssertEqual(editor.preservedAdjustmentData?.data, opaque)
        XCTAssertEqual(try integrity(protectedAsset, stage: "opaque-after-replacement-session"), before)

        // Replace metadata only through explicit synthetic setup, using the
        // original-handled input. Direct editor operations never commit edits.
        try install(valid, image: expectedOutput, asset: protectedAsset, input: protectedInput)
        let validBefore = try integrity(protectedAsset, stage: "valid-legacy-installed")
        XCTAssertEqual(validBefore.original, pristineProtected.original)
        XCTAssertEqual(validBefore.originalPixels, pristineProtected.originalPixels)
        let validInput = try input(protectedAsset, handles: { AdjustmentData.supportIdentifier($0.formatIdentifier, version: $0.formatVersion) })
        XCTAssertEqual(validInput.adjustmentData?.data, valid.data)
        editor.startContentEditing(with: validInput, placeholderImage: expectedOutput)
        waitForSwiftUIEditor(editor)
        editor.view.layoutIfNeeded()
        XCTAssertFalse(editor.isAdjustmentReadOnly)
        XCTAssertTrue(editor.shouldShowCancelConfirmation, "Editable bound sessions remain conservative")
        let restored = editor.adjustmentData
        try assertLiteralLegacy(restored, canvas: expectedCanvas)
        XCTAssertEqual(try rgba(XCTUnwrap(editor.outputImage)), try rgba(expectedOutput), "Actual bound legacy input matches the separate synchronous-compositor pixel oracle")
        try finishNormally(editor, expectedImage: expectedOutput, expectedState: expectedState)
        XCTAssertEqual(try integrity(protectedAsset, stage: "valid-legacy-after-export"), validBefore)

        var canvasLegacy = legacy
        canvasLegacy["referenceCanvasSize"] = NSValue(cgSize: expectedCanvas)
        let canvasBytes = try NSKeyedArchiver.archivedData(withRootObject: canvasLegacy, requiringSecureCoding: false)
        let canvasData = PHAdjustmentData(formatIdentifier: AdjustmentData.formatIdentifier, formatVersion: "1.0", data: canvasBytes)
        try install(canvasData, image: expectedOutput, asset: protectedAsset, input: validInput)
        let canvasBefore = try integrity(protectedAsset, stage: "canvas-legacy-installed")
        XCTAssertEqual(canvasBefore.original, pristineProtected.original)
        let canvasInput = try input(protectedAsset, handles: { _ in true })
        let canvasState = try AdjustmentData.decode(canvasBytes)
        editor.startContentEditing(with: canvasInput, placeholderImage: expectedOutput)
        waitForSwiftUIEditor(editor)
        editor.view.layoutIfNeeded()
        try assertLiteralLegacy(canvasState, canvas: expectedCanvas)
        try assertLiteralLegacy(editor.adjustmentData, canvas: expectedCanvas)
        XCTAssertEqual(try rgba(XCTUnwrap(editor.outputImage)), try rgba(expectedOutput))
        try finishNormally(editor, expectedImage: expectedOutput, expectedState: canvasState)
        XCTAssertEqual(try integrity(protectedAsset, stage: "canvas-legacy-after-export"), canvasBefore)

        // Ordinary foreign edits remain editable via PhotoKit's normal flattened
        // input contract; an unexpected directly bound foreign recipe is never
        // interpreted as our own archive merely because its keys look familiar.
        try install(foreign, image: rendered, asset: protectedAsset, input: canvasInput)
        let foreignBefore = try integrity(protectedAsset, stage: "foreign-installed")
        XCTAssertEqual(foreignBefore.original, pristineProtected.original)
        XCTAssertEqual(foreignBefore.originalPixels, pristineProtected.originalPixels)
        XCTAssertEqual(foreignBefore.currentPixels, digest(try rgba(expectedRenderedJPEG)))
        let foreignInput = try input(protectedAsset, handles: { AdjustmentData.supportIdentifier($0.formatIdentifier, version: $0.formatVersion) })
        XCTAssertNil(foreignInput.adjustmentData, "PhotoKit must provide the foreign current rendering, not an own-format handled recipe")
        let foreignCurrent = try currentImage(protectedAsset)
        XCTAssertEqual(try rgba(foreignCurrent), try rgba(expectedRenderedJPEG))
        editor.startContentEditing(with: foreignInput, placeholderImage: foreignCurrent)
        waitForSwiftUIEditor(editor)
        XCTAssertFalse(editor.isAdjustmentReadOnly)
        XCTAssertTrue(editor.shouldShowCancelConfirmation, "Editable bound sessions remain conservative")
        XCTAssertEqual(try rgba(XCTUnwrap(editor.outputImage)), try rgba(foreignCurrent), "Foreign editing uses its current version, never the original")
        try finishNormally(editor, expectedImage: foreignCurrent)
        XCTAssertEqual(try integrity(protectedAsset, stage: "foreign-after-normal-export"), foreignBefore)
        let unexpectedlyHandledForeign = try input(protectedAsset, handles: { _ in true })
        XCTAssertEqual(unexpectedlyHandledForeign.adjustmentData?.formatIdentifier, foreign.formatIdentifier)
        editor.startContentEditing(with: unexpectedlyHandledForeign, placeholderImage: try currentImage(protectedAsset))
        waitForSwiftUIEditor(editor)
        XCTAssertTrue(editor.isAdjustmentReadOnly)
        XCTAssertFalse(editor.shouldShowCancelConfirmation, "Actual protected input has no unsaved edits to discard")
        XCTAssertEqual(editor.preservedAdjustmentData?.data, opaque)
        XCTAssertEqual(try integrity(protectedAsset, stage: "foreign-after-protected-direct-input"), foreignBefore)
        XCTAssertEqual(try integrity(freshAsset, stage: "fresh-after-all-other-sessions"), pristineFresh)
        print("BOUND_INPUT_PRESERVATION_ASSERTIONS_COMPLETED use_terminal_XCTest_result_for_pass_status")
        // These two explicitly created resources remain only in this disposable
        // simulator. Never delete or edit pre-existing library assets here.
    }

    func testDoneWhileRecipeLoadsPreservesOpaqueStateAndNewestCompletion() throws {
        try requireAuthorizedSyntheticProbe()
        let original = fixture(left: .red, right: .blue)
        let rendered = fixture(left: .orange, right: .purple)
        let asset = try createOwnedAsset(original, label: "swiftui-loading-finish")
        let initial = try input(asset, handles: { _ in true })
        let opaque = PHAdjustmentData(formatIdentifier: AdjustmentData.formatIdentifier,
            formatVersion: AdjustmentData.formatVersion, data: Data([0, 1, 2, 3]))
        try install(opaque, image: rendered, asset: asset, input: initial)
        let bound = try input(asset, handles: { _ in true })
        let before = try integrity(asset, stage: "loading-finish-before")
        let editor = PhotoEditingViewController(); editor.loadViewIfNeeded()
        editor.view.frame = CGRect(x: 0, y: 0, width: 375, height: 667)
        editor.startContentEditing(with: bound, placeholderImage: rendered)
        XCTAssertEqual(editor.session.phase, .loading)
        let opaqueDone = expectation(description: "Done waits for opaque recipe and returns no-change")
        editor.finishContentEditing { output in
            XCTAssertNotNil(output)
            XCTAssertNil(output?.adjustmentData)
            if let output = output { XCTAssertFalse(FileManager.default.fileExists(atPath: output.renderedContentURL.path)) }
            opaqueDone.fulfill()
        }
        wait(for: [opaqueDone], timeout: 10)
        XCTAssertEqual(try integrity(asset, stage: "loading-finish-after-no-change"), before)

        editor.startContentEditing(with: bound, placeholderImage: rendered)
        let older = expectation(description: "Earlier loading finish stays silent"); older.isInverted = true
        editor.finishContentEditing { _ in older.fulfill() }
        let newest = expectation(description: "Latest loading finish completes once"); newest.assertForOverFulfill = true
        editor.finishContentEditing { output in XCTAssertNotNil(output); XCTAssertNil(output?.adjustmentData); newest.fulfill() }
        wait(for: [newest], timeout: 10)
        wait(for: [older], timeout: 0.2)

        editor.startContentEditing(with: bound, placeholderImage: rendered)
        let cancelled = expectation(description: "Cancellation while decoding suppresses Photos callback"); cancelled.isInverted = true
        editor.finishContentEditing { _ in cancelled.fulfill() }
        editor.cancelContentEditing()
        wait(for: [cancelled], timeout: 0.2)

        var recipe = AdjustmentData(); recipe.filterType = .Sepia
        recipe.referenceCanvasSize = expectedCanvas
        let valid = PHAdjustmentData(formatIdentifier: AdjustmentData.formatIdentifier,
            formatVersion: AdjustmentData.formatVersion, data: try recipe.encode())
        try install(valid, image: rendered, asset: asset, input: bound)
        let validInput = try input(asset, handles: { _ in true })
        let validBefore = try integrity(asset, stage: "loading-valid-before")
        editor.startContentEditing(with: validInput, placeholderImage: rendered)
        XCTAssertEqual(editor.session.phase, .loading)
        let validDone = expectation(description: "Done waits for valid recipe then exports that recipe")
        editor.finishContentEditing { output in
            XCTAssertNotNil(output?.adjustmentData)
            if let bytes = output?.adjustmentData?.data {
                XCTAssertEqual(try? AdjustmentData.decode(bytes).filterType, .Sepia)
            }
            validDone.fulfill()
        }
        wait(for: [validDone], timeout: 10)
        XCTAssertEqual(try integrity(asset, stage: "loading-valid-after-export"), validBefore)
    }

    func testDoneBeforeLegacyCanvasLayoutWaitsForOriginalGeometry() throws {
        try requireAuthorizedSyntheticProbe()
        let original = fixture(left: .red, right: .blue)
        let asset = try createOwnedAsset(original, label: "legacy-canvas-early-done")
        let initial = try input(asset, handles: { _ in true })
        var legacy = AdjustmentData()
        var bubble = BubbleModel.bubbles[4]; bubble.content = "Early legacy 世界"
        bubble.center = CGPoint(x: 75, y: 50)
        bubble.transform = CGAffineTransform(a: 0.8, b: 0.2, c: -0.2, d: 0.8, tx: 3, ty: -2)
        legacy.bubbles = [bubble]
        XCTAssertNil(legacy.referenceCanvasSize)
        let data = PHAdjustmentData(formatIdentifier: AdjustmentData.formatIdentifier,
            formatVersion: AdjustmentData.formatVersion, data: try legacy.encode())
        try install(data, image: original, asset: asset, input: initial)
        let bound = try input(asset, handles: { _ in true })
        let before = try integrity(asset, stage: "legacy-canvas-early-done-before")
        let oracle = BaseEditPhotoController(); oracle.loadViewIfNeeded()
        oracle.view.frame = CGRect(x: 0, y: 0, width: 375, height: 667)
        oracle.sourceImage = original; oracle.restoreFromData(legacy); oracle.view.layoutIfNeeded()
        let expected = try XCTUnwrap(oracle.outputImage)
        let expectedJPEG = try XCTUnwrap(UIImage(data: XCTUnwrap(expected.jpegData(compressionQuality: 1))))
        let editor = PhotoEditingViewController(); editor.loadViewIfNeeded()
        editor.view.frame = oracle.view.frame
        editor.startContentEditing(with: bound, placeholderImage: original)
        XCTAssertEqual(editor.session.phase, .loading)
        let done = expectation(description: "Early Done waits for original legacy canvas")
        editor.finishContentEditing { output in
            do {
                let output = try XCTUnwrap(output)
                let saved = try AdjustmentData.decode(XCTUnwrap(output.adjustmentData?.data))
                XCTAssertEqual(saved.referenceCanvasSize, self.expectedCanvas)
                XCTAssertEqual(saved.bubbles.count, 1)
                XCTAssertEqual(saved.bubbles.first?.center, bubble.center)
                XCTAssertEqual(saved.bubbles.first?.transform, bubble.transform)
                let rendered = try XCTUnwrap(UIImage(contentsOfFile: output.renderedContentURL.path))
                XCTAssertEqual(try self.rgba(rendered), try self.rgba(expectedJPEG))
            } catch { XCTFail("Legacy early-Done oracle failed: \(error)") }
            done.fulfill()
        }
        wait(for: [done], timeout: 15)
        XCTAssertEqual(try integrity(asset, stage: "legacy-canvas-early-done-after"), before)
    }

    func testUnmountedLegacyCanvasTimesOutOnceAndAbandonedHostsStaySilent() throws {
        try requireAuthorizedSyntheticProbe()
        let original = fixture(left: .red, right: .blue)
        let asset = try createOwnedAsset(original, label: "legacy-canvas-timeout")
        let initial = try input(asset, handles: { _ in true })
        var recipe = AdjustmentData(); recipe.bubbles = [BubbleModel.bubbles[4]]
        XCTAssertNil(recipe.referenceCanvasSize)
        let metadata = PHAdjustmentData(formatIdentifier: AdjustmentData.formatIdentifier,
            formatVersion: AdjustmentData.formatVersion, data: try recipe.encode())
        try install(metadata, image: original, asset: asset, input: initial)
        let bound = try input(asset, handles: { _ in true })
        let before = try integrity(asset, stage: "legacy-unmounted-before")
        func makeUnmounted() -> PhotoEditingViewController {
            let value = PhotoEditingViewController(); value.loadViewIfNeeded()
            value.view.frame = .zero
            value.preparationTimeoutForTesting = 0.03
            return value
        }
        let editor = makeUnmounted()
        editor.startContentEditing(with: bound, placeholderImage: original)
        let timedOut = expectation(description: "A live zero-sized host receives exactly one failure")
        timedOut.assertForOverFulfill = true
        var callbacks = 0
        editor.finishContentEditing { output in callbacks += 1; XCTAssertNil(output); timedOut.fulfill() }
        wait(for: [timedOut], timeout: 5)
        XCTAssertEqual(callbacks, 1)
        XCTAssertTrue(editor.view.isUserInteractionEnabled)

        editor.startContentEditing(with: bound, placeholderImage: original)
        let older = expectation(description: "Superseded zero-sized finish is silent"); older.isInverted = true
        editor.finishContentEditing { _ in older.fulfill() }
        let newest = expectation(description: "Newest zero-sized finish times out once"); newest.assertForOverFulfill = true
        editor.finishContentEditing { output in XCTAssertNil(output); newest.fulfill() }
        wait(for: [newest], timeout: 5)
        wait(for: [older], timeout: 0.1)

        editor.startContentEditing(with: bound, placeholderImage: original)
        let cancelled = expectation(description: "Canceled zero-sized host is silent"); cancelled.isInverted = true
        editor.finishContentEditing { _ in cancelled.fulfill() }
        editor.cancelContentEditing()
        wait(for: [cancelled], timeout: 0.1)

        editor.startContentEditing(with: bound, placeholderImage: original)
        let replaced = expectation(description: "Replaced input cannot receive the old timeout"); replaced.isInverted = true
        editor.finishContentEditing { _ in replaced.fulfill() }
        editor.startContentEditing(with: bound, placeholderImage: original)
        wait(for: [replaced], timeout: 0.1)

        let ended = expectation(description: "Deallocated Photos host receives no callback"); ended.isInverted = true
        var temporary: PhotoEditingViewController? = makeUnmounted()
        weak var weakHost = temporary
        temporary?.startContentEditing(with: bound, placeholderImage: original)
        temporary?.finishContentEditing { _ in ended.fulfill() }
        temporary = nil
        XCTAssertNil(weakHost)
        wait(for: [ended], timeout: 0.1)
        XCTAssertEqual(try integrity(asset, stage: "legacy-unmounted-after"), before)
    }

    func testActualPhotosOutputDestinationsIsolateLateWrites() throws {
        try requireAuthorizedSyntheticProbe()
        let original = fixture(left: .red, right: .blue)
        let asset = try createOwnedAsset(original, label: "destination-identity")
        let value = try input(asset, handles: { _ in true })
        let before = try integrity(asset, stage: "output-destinations-before-write")
        let older = PHContentEditingOutput(contentEditingInput: value)
        let newer = PHContentEditingOutput(contentEditingInput: value)
        XCTAssertNotEqual(older.renderedContentURL.standardizedFileURL, newer.renderedContentURL.standardizedFileURL,
                          "Distinct finish outputs must not alias one staging file")
        guard older.renderedContentURL.standardizedFileURL != newer.renderedContentURL.standardizedFileURL else { return }
        let oldBytes = try XCTUnwrap(fixture(left: .green, right: .orange).jpegData(compressionQuality: 1))
        let newBytes = try XCTUnwrap(original.jpegData(compressionQuality: 1))
        // Simulate a newer result being written before a late old write. Neither
        // output is committed to Photos; only their own staging files are touched.
        try newBytes.write(to: newer.renderedContentURL, options: .atomic)
        try oldBytes.write(to: older.renderedContentURL, options: .atomic)
        XCTAssertEqual(try Data(contentsOf: newer.renderedContentURL), newBytes)
        XCTAssertEqual(try Data(contentsOf: older.renderedContentURL), oldBytes)
        XCTAssertEqual(try integrity(asset, stage: "output-destinations-after-reverse-write"), before)
        print("PHOTOS_OUTPUT_DESTINATIONS_ASSERTIONS_COMPLETED use_terminal_XCTest_result_for_pass_status")
    }

    private func finishNormally(_ editor: PhotoEditingViewController, expectedImage: UIImage? = nil, expectedState: AdjustmentData? = nil) throws {
        let finished = expectation(description: "Ordinary independent session completes exactly once")
        finished.assertForOverFulfill = true
        editor.finishContentEditing { output in
            XCTAssertNotNil(output?.adjustmentData)
            if let output = output {
                XCTAssertNotNil(UIImage(contentsOfFile: output.renderedContentURL.path))
                do {
                    if let expectedImage = expectedImage {
                        let actual = try XCTUnwrap(UIImage(contentsOfFile: output.renderedContentURL.path))
                        let independentlyEncoded = try XCTUnwrap(UIImage(data: XCTUnwrap(expectedImage.jpegData(compressionQuality: 1))))
                        XCTAssertEqual(try self.rgba(actual), try self.rgba(independentlyEncoded), "Decoded full output pixels, not PNG/JPEG container metadata")
                    }
                    let metadata = try XCTUnwrap(output.adjustmentData)
                    XCTAssertEqual(metadata.formatIdentifier, "Mango.CelluloidPhotoExtension")
                    XCTAssertEqual(metadata.formatVersion, "1.0")
                    XCTAssertNotEqual(metadata.data, self.rejectedOpaqueBytes)
                    let saved = try AdjustmentData.decode(metadata.data)
                    if expectedState != nil {
                        try self.assertLiteralLegacy(saved, canvas: self.expectedCanvas)
                    } else {
                        XCTAssertEqual(saved.filterType, .Original)
                        XCTAssertTrue(saved.bubbles.isEmpty)
                        XCTAssertTrue(saved.stickers.isEmpty)
                        XCTAssertEqual(saved.referenceCanvasSize, self.expectedCanvas)
                    }
                } catch { XCTFail("Exact valid legacy output verification failed: \(error)") }
            }
            finished.fulfill()
        }
        let boundInput = editor.input
        let boundPreview = editor.preview.image
        let pending = editor.activeExportForTesting
        XCTAssertTrue(editor.canHandle(PHAdjustmentData(formatIdentifier: AdjustmentData.formatIdentifier, formatVersion: "1.0", data: Data([1,2,3]))))
        XCTAssertFalse(editor.canHandle(PHAdjustmentData(formatIdentifier: "example.synthetic.foreign", formatVersion: "1.0", data: Data([1,2,3]))))
        XCTAssertTrue(editor.input === boundInput)
        XCTAssertTrue(editor.preview.image === boundPreview)
        XCTAssertTrue(editor.activeExportForTesting === pending, "Unrelated negotiation cannot cancel or replace the bound export")
        wait(for: [finished], timeout: 15)
    }
    /// Literal semantic oracle independent of AdjustmentData.decode and the
    /// renderer. Missing fields/layers fail by throwing instead of array traps.
    private func assertLiteralLegacy(_ state: AdjustmentData, canvas: CGSize?) throws {
        XCTAssertEqual(state.filterType, .Sepia)
        XCTAssertEqual(state.referenceCanvasSize, canvas)
        guard state.bubbles.count == 1, state.stickers.count == 1 else {
            XCTFail("Literal legacy state must contain exactly one bubble and one sticker")
            throw failureValue("Legacy layer count mismatch")
        }
        let bubble = try XCTUnwrap(state.bubbles.first)
        let sticker = try XCTUnwrap(state.stickers.first)
        XCTAssertEqual(bubble.content, "Preserve 世界")
        XCTAssertEqual(bubble.center, CGPoint(x: 75, y: 50))
        XCTAssertEqual(bubble.bounds, CGRect(x: 0, y: 0, width: 90, height: 60))
        XCTAssertEqual(bubble.transform, CGAffineTransform(rotationAngle: 0.15))
        XCTAssertEqual((bubble.toJSON() as? NSDictionary)?["asset"] as? String, "say1")
        XCTAssertEqual(sticker.center, CGPoint(x: 220, y: 120))
        XCTAssertEqual(sticker.bounds, CGRect(x: 0, y: 0, width: 70, height: 70))
        XCTAssertEqual(sticker.transform, CGAffineTransform(a: 0.8, b: 0.2, c: -0.2, d: 0.8, tx: 3, ty: -2))
        XCTAssertEqual((sticker.toJSON() as? NSDictionary)?["imageName"] as? String, "32")
    }
    private func fixture(left: UIColor, right: UIColor) -> UIImage {
        let format = UIGraphicsImageRendererFormat(); format.scale = 1
        return UIGraphicsImageRenderer(size: CGSize(width: 192, height: 128), format: format).image { context in
            left.setFill(); context.fill(CGRect(x: 0, y: 0, width: 96, height: 128))
            right.setFill(); context.fill(CGRect(x: 96, y: 0, width: 96, height: 128))
        }
    }
    private func changes(_ block: @escaping () -> Void) throws {
        try requireAuthorizedSyntheticProbe()
        let done = expectation(description: "Explicit test-owned Photos setup")
        var success = false; var failure: Error?
        PHPhotoLibrary.shared().performChanges(block) { value, error in
            DispatchQueue.main.async { success = value; failure = error; done.fulfill() }
        }
        guard XCTWaiter.wait(for: [done], timeout: 30) == .completed else { throw failureValue("Synthetic Photos setup timed out") }
        if let failure = failure { throw failure }
        guard success else { throw failureValue("Synthetic Photos setup was rejected") }
    }
    private func createOwnedAsset(_ image: UIImage, label: String) throws -> PHAsset {
        let filename = "celluloid-guard-\(label)-\(UUID().uuidString).png"
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(filename)
        try XCTUnwrap(image.pngData()).write(to: url)
        var identifier: String?
        try changes {
            let request = PHAssetCreationRequest.forAsset()
            let options = PHAssetResourceCreationOptions(); options.originalFilename = filename
            request.addResource(with: .photo, fileURL: url, options: options)
            identifier = request.placeholderForCreatedAsset?.localIdentifier
        }
        let asset = try XCTUnwrap(PHAsset.fetchAssets(withLocalIdentifiers: [try XCTUnwrap(identifier)], options: nil).firstObject)
        guard PHAssetResource.assetResources(for: asset).contains(where: { $0.originalFilename == filename }) else {
            throw failureValue("Created resource identity differs from the explicit synthetic filename")
        }
        ownedIdentifiers.insert(asset.localIdentifier)
        print("BOUND_INPUT_OWNED_FIXTURE \(asset.localIdentifier) \(filename)")
        return asset
    }
    private func input(_ asset: PHAsset, handles: @escaping (PHAdjustmentData) -> Bool) throws -> PHContentEditingInput {
        let ready = expectation(description: "Real bound PhotoKit input")
        let options = PHContentEditingInputRequestOptions(); options.isNetworkAccessAllowed = false
        options.canHandleAdjustmentData = handles
        var value: PHContentEditingInput?
        let currentAsset = try freshOwnedAsset(asset)
        let id = currentAsset.requestContentEditingInput(with: options) { result, _ in
            DispatchQueue.main.async { value = result; ready.fulfill() }
        }
        guard XCTWaiter.wait(for: [ready], timeout: 15) == .completed else {
            currentAsset.cancelContentEditingInputRequest(id); throw failureValue("Bound PhotoKit input timed out")
        }
        return try XCTUnwrap(value)
    }
    private func currentImage(_ asset: PHAsset) throws -> UIImage {
        let options = PHImageRequestOptions(); options.version = .current
        options.isSynchronous = true; options.isNetworkAccessAllowed = false
        var bytes: Data?
        PHImageManager.default().requestImageDataAndOrientation(for: try freshOwnedAsset(asset), options: options) { data, _, _, _ in bytes = data }
        return try XCTUnwrap(UIImage(data: try XCTUnwrap(bytes)))
    }
    private func install(_ data: PHAdjustmentData, image: UIImage, asset: PHAsset, input: PHContentEditingInput) throws {
        let output = PHContentEditingOutput(contentEditingInput: input)
        output.adjustmentData = data
        try XCTUnwrap(image.jpegData(compressionQuality: 1)).write(to: output.renderedContentURL, options: .atomic)
        let currentAsset = try freshOwnedAsset(asset)
        try changes { PHAssetChangeRequest(for: currentAsset).contentEditingOutput = output }
    }
    private func freshOwnedAsset(_ asset: PHAsset) throws -> PHAsset {
        guard ownedIdentifiers.contains(asset.localIdentifier) else { throw failureValue("Asset is not explicitly test-created") }
        return try XCTUnwrap(PHAsset.fetchAssets(withLocalIdentifiers: [asset.localIdentifier], options: nil).firstObject)
    }
    private func requireAuthorizedSyntheticProbe() throws {
        #if targetEnvironment(simulator)
        let candidate = ProcessInfo.processInfo.environment["CELLULOID_PROBE_SOURCE_SHA"] ?? ""
        guard candidate.count == 40, candidate.allSatisfy({ "0123456789abcdef".contains($0) }) else {
            throw failureValue("Exact reviewed probe source SHA is absent")
        }
        try requireAuthorization(PHPhotoLibrary.authorizationStatus(for: .readWrite),
            syntheticMarker: ProcessInfo.processInfo.environment["CELLULOID_SYNTHETIC_PROBE"] == "1")
        #else
        throw failureValue("Synthetic mutation probe cannot run on a physical device")
        #endif
    }
    private func requireAuthorization(_ status: PHAuthorizationStatus, syntheticMarker: Bool) throws {
        guard status == .authorized, syntheticMarker else { throw failureValue("Pre-granted disposable synthetic-library prerequisite is absent") }
    }
    func testWrongAuthorizationNeverReachesSyntheticSetup() throws {
        for status in [PHAuthorizationStatus.notDetermined, .restricted, .denied, .limited] {
            var setupCalls = 0
            do { try requireAuthorization(status, syntheticMarker: true); setupCalls += 1; XCTFail("Unexpected status admitted") }
            catch { XCTAssertEqual(setupCalls, 0) }
        }
        XCTAssertThrowsError(try requireAuthorization(.authorized, syntheticMarker: false))
        XCTAssertNoThrow(try requireAuthorization(.authorized, syntheticMarker: true))
    }
    private func resourceBytes(_ resource: PHAssetResource) throws -> Data {
        let ready = expectation(description: "Read only explicit owned resource")
        let options = PHAssetResourceRequestOptions(); options.isNetworkAccessAllowed = false
        var bytes = Data(); let lock = NSLock(); var error: Error?
        let id = PHAssetResourceManager.default().requestData(for: resource, options: options, dataReceivedHandler: { chunk in
            lock.lock(); bytes.append(chunk); lock.unlock()
        }, completionHandler: { failure in error = failure; ready.fulfill() })
        guard XCTWaiter.wait(for: [ready], timeout: 15) == .completed else {
            PHAssetResourceManager.default().cancelDataRequest(id); throw failureValue("Owned resource read timed out")
        }
        if let error = error { throw error }
        return bytes
    }
    private func integrity(_ asset: PHAsset, stage: String) throws -> Integrity {
        let asset = try freshOwnedAsset(asset)
        let resources = PHAssetResource.assetResources(for: asset)
        var receipts: [ResourceReceipt] = []
        var originalBytes: Data?; var editedBytes: Data?
        for resource in resources {
            let bytes = try resourceBytes(resource)
            receipts.append(ResourceReceipt(type: resource.type.rawValue, filename: resource.originalFilename, sha256: digest(bytes)))
            if resource.type == .photo { originalBytes = bytes }
            if resource.type == .fullSizePhoto { editedBytes = bytes }
        }
        let original = try XCTUnwrap(originalBytes)
        let representedCurrent = editedBytes ?? original
        let handled = try input(asset, handles: { _ in true })
        let current = try input(asset, handles: { _ in false })
        let currentInputBytes = try Data(contentsOf: XCTUnwrap(current.fullSizeImageURL))
        XCTAssertEqual(digest(currentInputBytes), digest(representedCurrent), "Current input URL belongs to the enumerated current resource")
        let receipt = Integrity(assetIdentifier: asset.localIdentifier,
            resources: receipts.sorted { ($0.type, $0.filename, $0.sha256) < ($1.type, $1.filename, $1.sha256) },
            originalPixels: digest(try rgba(XCTUnwrap(UIImage(data: original)))),
            currentPixels: digest(try rgba(XCTUnwrap(UIImage(data: representedCurrent)))),
            original: digest(original), current: digest(representedCurrent),
            adjustment: handled.adjustmentData.map { digest($0.data) }, identifier: handled.adjustmentData?.formatIdentifier,
            version: handled.adjustmentData?.formatVersion)
        receiptNumber += 1
        let encoded = try JSONEncoder().encode(receipt)
        let candidate = ProcessInfo.processInfo.environment["CELLULOID_PROBE_SOURCE_SHA"] ?? "UNSET"
        print("BOUND_INPUT_RESOURCE_RECEIPT candidate=\(candidate) stage=\(stage) sequence=\(receiptNumber) " + String(decoding: encoded, as: UTF8.self))
        return receipt
    }
    private func rgba(_ image: UIImage) throws -> Data {
        let cg = try XCTUnwrap(image.cgImage)
        let context = try XCTUnwrap(CGContext(data: nil, width: cg.width, height: cg.height, bitsPerComponent: 8,
            bytesPerRow: cg.width * 4, space: CGColorSpace(name: CGColorSpace.sRGB)!,
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
        context.draw(cg, in: CGRect(x: 0, y: 0, width: CGFloat(cg.width), height: CGFloat(cg.height)))
        return Data(bytes: try XCTUnwrap(context.data), count: cg.height * context.bytesPerRow)
    }
    private func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
    private func failureValue(_ message: String) -> NSError { NSError(domain: "Celluloid.SyntheticAdjustmentProbe", code: 1, userInfo: [NSLocalizedDescriptionKey: message]) }
}
