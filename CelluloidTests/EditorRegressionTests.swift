import XCTest
import UIKit
import Photos
import CryptoKit
@testable import Celluloid
@testable import CelluloidKit

@MainActor
final class EditorRegressionTests: XCTestCase {
    func testPhotosLibraryBootstrapReadiness() throws {
        try recordSyntheticLibraryState(hashResources: false)
    }

    func testReconcileSyntheticPhotosAfterImport() throws {
        try recordSyntheticLibraryState(hashResources: true)
    }

    private func recordSyntheticLibraryState(hashResources: Bool) throws {
        let started = ProcessInfo.processInfo.systemUptime
        let authorization = PHPhotoLibrary.authorizationStatus(for: .readWrite)
        XCTAssertEqual(authorization, .authorized, "Real simulator Photos grant must be effective before readiness is claimed")
        guard authorization == .authorized else { return }
        let assets = PHAsset.fetchAssets(with: .image, options: nil)
        var rows: [[String: Any]] = []
        for index in 0..<min(assets.count, 64) {
            let asset = assets.object(at: index)
            guard let resource = PHAssetResource.assetResources(for: asset).first(where: {
                $0.type == .photo && ($0.originalFilename.hasPrefix("celluloid-fixture") || $0.originalFilename.hasPrefix("celluloid-composition-"))
            }) else { continue }
            var row: [String: Any] = ["identifier": asset.localIdentifier, "filename": resource.originalFilename,
                "width": asset.pixelWidth, "height": asset.pixelHeight]
            if hashResources {
                let done = expectation(description: "Read only generated synthetic resource")
                var data = Data()
                var failure: Error?
                let lock = NSLock()
                let options = PHAssetResourceRequestOptions(); options.isNetworkAccessAllowed = false
                PHAssetResourceManager.default().requestData(for: resource, options: options, dataReceivedHandler: { chunk in
                    lock.lock(); data.append(chunk); lock.unlock()
                }, completionHandler: { error in failure = error; done.fulfill() })
                wait(for: [done], timeout: 30)
                if let error = failure { throw error }
                row["bytes"] = data.count
                row["sha256"] = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
            }
            rows.append(row)
        }
        let result: [String: Any] = ["authorization": authorization.rawValue, "asset_count": assets.count,
            "synthetic": rows, "hash_resources": hashResources,
            "elapsed_seconds": ProcessInfo.processInfo.systemUptime - started,
            "library_mutation": false]
        print("PHOTOS_LIBRARY_READINESS " + String(decoding: try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys]), as: UTF8.self))
    }

    func testPrivacyPolicyUsesApprovedHTTPSDestinationAndAccessibleControl() {
        XCTAssertEqual(AppLinks.privacyPolicyURL.absoluteString, "https://100mango.github.io/app-privacy/")
        XCTAssertEqual(AppLinks.privacyPolicyURL.scheme, "https")
        let entrance = EntranceViewController()
        entrance.loadViewIfNeeded()
        entrance.view.frame = CGRect(x: 0, y: 0, width: 390, height: 844)
        entrance.view.layoutIfNeeded()
        XCTAssertEqual(entrance.privacyPolicyButton.accessibilityIdentifier, "privacy-policy")
        XCTAssertFalse(entrance.privacyPolicyButton.currentTitle?.isEmpty ?? true)
        XCTAssertGreaterThanOrEqual(entrance.privacyPolicyButton.bounds.height, 44)
        XCTAssertTrue(entrance.privacyPolicyButton.isEnabled)
    }

    func testHomeLayoutDoesNotCollapseOrOverlapAcrossPhoneAndPadSizes() {
        let entrance = EntranceViewController()
        entrance.loadViewIfNeeded()
        for category in [UIContentSizeCategory.large, .accessibilityExtraExtraExtraLarge] {
            let traits = UITraitCollection(preferredContentSizeCategory: category)
            entrance.privacyPolicyButton.titleLabel?.font = .preferredFont(forTextStyle: .footnote, compatibleWith: traits)
            entrance.editPhotoButton.label.font = .preferredFont(forTextStyle: .body, compatibleWith: traits)
            entrance.makeCollageButton.label.font = .preferredFont(forTextStyle: .body, compatibleWith: traits)
            for size in [CGSize(width: 320, height: 568), CGSize(width: 568, height: 320),
                         CGSize(width: 390, height: 844), CGSize(width: 844, height: 390),
                         CGSize(width: 1032, height: 1376), CGSize(width: 1376, height: 1032)] {
                entrance.view.frame = CGRect(origin: .zero, size: size)
                entrance.view.setNeedsLayout()
                entrance.view.layoutIfNeeded()
                entrance.viewDidLayoutSubviews()
                entrance.view.layoutIfNeeded()
                let edit = entrance.editPhotoButton.convert(entrance.editPhotoButton.bounds, to: entrance.view)
                let collage = entrance.makeCollageButton.convert(entrance.makeCollageButton.bounds, to: entrance.view)
                let editContent = entrance.editPhotoButton.stackView.convert(entrance.editPhotoButton.stackView.bounds, to: entrance.view)
                let collageContent = entrance.makeCollageButton.stackView.convert(entrance.makeCollageButton.stackView.bounds, to: entrance.view)
                let footer = entrance.privacyPolicyButton.frame
                XCTAssertGreaterThanOrEqual(edit.height, 120, "\(size), \(category)")
                XCTAssertGreaterThanOrEqual(collage.height, 120, "\(size), \(category)")
                XCTAssertGreaterThanOrEqual(edit.width, 150, "\(size), \(category)")
                XCTAssertGreaterThanOrEqual(collage.width, 150, "\(size), \(category)")
                XCTAssertFalse(edit.intersects(collage), "Primary choices overlap at \(size)")
                XCTAssertTrue(edit.insetBy(dx: -1, dy: -1).contains(editContent), "Edit content escapes its choice at \(size), \(category)")
                XCTAssertTrue(collage.insetBy(dx: -1, dy: -1).contains(collageContent), "Collage content escapes its choice at \(size), \(category)")
                XCTAssertFalse(editContent.intersects(collageContent), "Icons/text overlap at \(size)")
                XCTAssertGreaterThan(footer.minY, size.height * 0.60)
                XCTAssertGreaterThanOrEqual(footer.minY, max(edit.maxY, collage.maxY))
                let textHeight = entrance.privacyPolicyButton.titleLabel?.sizeThatFits(CGSize(width: size.width - 32, height: .greatestFiniteMagnitude)).height ?? 0
                XCTAssertEqual(footer.height, max(44, textHeight + 16), accuracy: 1)
            }
        }
    }

    func testEditorRendersAndRestoresWithoutDuplicatingOverlays() throws {
        let editor = BaseEditPhotoController()
        editor.loadViewIfNeeded()
        editor.view.frame = CGRect(x: 0, y: 0, width: 390, height: 844)
        let format = UIGraphicsImageRendererFormat(); format.scale = 1
        editor.sourceImage = UIGraphicsImageRenderer(size: CGSize(width: 96, height: 64), format: format).image { context in
            UIColor.red.setFill(); context.fill(CGRect(x: 0, y: 0, width: 96, height: 64))
        }
        editor.view.layoutIfNeeded()
        var state = AdjustmentData()
        state.bubbles = [BubbleModel.bubbles[0]]
        state.stickers = [StickerModel.stickers[0]]
        state.filterType = .Chrome
        editor.restoreFromData(state)
        editor.restoreFromData(state)
        XCTAssertEqual(editor.adjustmentData.bubbles.count, 1)
        XCTAssertEqual(editor.adjustmentData.stickers.count, 1)
        let output = try XCTUnwrap(editor.outputImage)
        XCTAssertEqual(output.size, CGSize(width: 96, height: 64))
        XCTAssertNotNil(output.jpegData(compressionQuality: 1))
        XCTAssertEqual(try AdjustmentData.decode(editor.adjustmentData.encode()).filterType, .Chrome)
    }
    func testOrientedAsymmetricSourceExportsCorrectDimensionsAndStickerPixels() throws {
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        let source = UIGraphicsImageRenderer(size: CGSize(width: 160, height: 80), format: format).image { context in
            UIColor.red.setFill(); context.fill(CGRect(x: 0, y: 0, width: 80, height: 80))
            UIColor.blue.setFill(); context.fill(CGRect(x: 80, y: 0, width: 80, height: 80))
        }
        let editor = BaseEditPhotoController()
        editor.loadViewIfNeeded()
        editor.view.frame = CGRect(x: 0, y: 0, width: 390, height: 844)
        editor.sourceImage = UIImage(cgImage: try XCTUnwrap(source.cgImage), scale: 1, orientation: .right)
        editor.view.layoutIfNeeded()
        let original = try XCTUnwrap(editor.outputImage)
        XCTAssertEqual(original.cgImage?.width, 80)
        XCTAssertEqual(original.cgImage?.height, 160)
        XCTAssertEqual(original.imageOrientation, .up)
        var state = AdjustmentData()
        var sticker = StickerModel.stickers[0]
        sticker.center = CGPoint(x: editor.preview.imageRect.width / 2, y: editor.preview.imageRect.height / 2)
        state.stickers = [sticker]
        editor.restoreFromData(state)
        let decorated = try XCTUnwrap(editor.outputImage)
        XCTAssertNotEqual(original.pngData(), decorated.pngData(), "The actual export pixels must contain the sticker")
    }

    func testNoSourceImageIsSafe() {
        let editor = BaseEditPhotoController()
        editor.loadViewIfNeeded()
        XCTAssertNil(editor.outputImage)
    }
    func testExtensionRejectsUnsupportedOrCorruptAdjustments() throws {
        let editor = PhotoEditingViewController()
        let valid = try AdjustmentData().encode()
        XCTAssertTrue(editor.canHandle(PHAdjustmentData(formatIdentifier: AdjustmentData.formatIdentifier, formatVersion: "1.0", data: valid)))
        XCTAssertFalse(editor.canHandle(PHAdjustmentData(formatIdentifier: "Other", formatVersion: "1.0", data: valid)))
        XCTAssertFalse(editor.canHandle(PHAdjustmentData(formatIdentifier: AdjustmentData.formatIdentifier, formatVersion: "1.0", data: Data([0,1,2]))))
    }
    func testExtensionStartsRendersAndFinishesSeededPhotoWithoutLibraryMutation() throws {
        XCTAssertEqual(PHPhotoLibrary.authorizationStatus(for: .readWrite), .authorized,
                       "The integration suite requires simulator Photos access to its synthetic fixtures")
        let asset = try XCTUnwrap(CelluloidTestFixtures.syntheticAsset())
        let loaded = expectation(description: "Photos editing input")
        var editingInput: PHContentEditingInput?
        let options = PHContentEditingInputRequestOptions()
        options.isNetworkAccessAllowed = false
        asset.requestContentEditingInput(with: options) { input, _ in
            DispatchQueue.main.async { editingInput = input; loaded.fulfill() }
        }
        wait(for: [loaded], timeout: 15)
        let input = try XCTUnwrap(editingInput)
        let placeholder = try XCTUnwrap(input.displaySizeImage)
        let editor = PhotoEditingViewController()
        editor.loadViewIfNeeded()
        editor.view.frame = CGRect(x: 0, y: 0, width: 390, height: 844)
        editor.startContentEditing(with: input, placeholderImage: placeholder)
        editor.view.layoutIfNeeded()
        var adjustment = AdjustmentData()
        adjustment.filterType = .Sepia
        editor.restoreFromData(adjustment)
        var callbacks = 0
        let finished = expectation(description: "Extension rendered output")
        finished.assertForOverFulfill = true
        editor.finishContentEditing { output in
            callbacks += 1
            XCTAssertNotNil(output)
            if let output = output {
                XCTAssertNotNil(UIImage(contentsOfFile: output.renderedContentURL.path))
                XCTAssertEqual(output.adjustmentData?.formatIdentifier, AdjustmentData.formatIdentifier)
                XCTAssertEqual(output.adjustmentData?.formatVersion, "1.0")
                if let bytes = output.adjustmentData?.data {
                    XCTAssertEqual(try? AdjustmentData.decode(bytes).filterType, .Sepia)
                } else { XCTFail("Missing reversible adjustment archive") }
            }
            finished.fulfill()
        }
        wait(for: [finished], timeout: 10)
        XCTAssertEqual(callbacks, 1)
        XCTAssertTrue(editor.view.isUserInteractionEnabled)
        editor.cancelContentEditing()
        let cancelledBeforeFinish = expectation(description: "Photos canceled before finish: no host callback")
        cancelledBeforeFinish.isInverted = true
        editor.finishContentEditing { _ in cancelledBeforeFinish.fulfill() }
        XCTAssertNil(editor.input)

        editor.startContentEditing(with: input, placeholderImage: placeholder)
        let cancelledDuringRender = expectation(description: "Photos canceled during preparation: suppress pending host callback")
        cancelledDuringRender.isInverted = true
        editor.finishContentEditing { _ in cancelledDuringRender.fulfill() }
        XCTAssertFalse(editor.view.isUserInteractionEnabled, "Editing controls are disabled while Photos output is prepared")
        // The asynchronous export has been requested, while its completion cannot
        // yet execute on this main-thread stack. This is deterministic cancellation
        // during preparation, not a race against an arbitrary elapsed delay.
        editor.cancelContentEditing()
        XCTAssertNil(editor.input)
        XCTAssertTrue(editor.view.isUserInteractionEnabled)

        editor.startContentEditing(with: input, placeholderImage: placeholder)
        editor.view.layoutIfNeeded()
        var renderedState = editor.adjustmentData
        let canvas = try XCTUnwrap(renderedState.referenceCanvasSize)
        var sticker = StickerModel.stickers[0]
        sticker.center = CGPoint(x: canvas.width / 2, y: canvas.height / 2)
        renderedState.stickers = [sticker]
        editor.restoreFromData(renderedState)
        let cancelledAfterRaster = expectation(description: "Photos canceled after a consumed strip: no host callback")
        cancelledAfterRaster.isInverted = true
        let rasterCancellation = expectation(description: "Actual raster progress triggers host cancellation")
        editor.finishContentEditing { _ in cancelledAfterRaster.fulfill() }
        let pending = try XCTUnwrap(editor.activeExportForTesting)
        pending.consumedRasterObserverForTesting = { [weak pending] in
            let acknowledged = DispatchSemaphore(value: 0)
            DispatchQueue.main.async {
                if let pending = pending {
                    XCTAssertGreaterThan(pending.storageStatistics.consumedRasterCount, 0)
                    XCTAssertEqual(pending.storageStatistics.completedOverlayCount, 0)
                } else { XCTFail("Rendering task disappeared before cancellation") }
                editor.cancelContentEditing()
                rasterCancellation.fulfill()
                acknowledged.signal()
            }
            // Pause only this DEBUG test at its observed strip boundary. This
            // avoids mistaking a50ms decode delay for cancellation during render.
            _ = acknowledged.wait(timeout: .now() + 5)
        }
        wait(for: [rasterCancellation], timeout: 10)
        pending.consumedRasterObserverForTesting = nil
        XCTAssertTrue(pending.isCancelled)

        editor.startContentEditing(with: input, placeholderImage: placeholder)
        let superseded = expectation(description: "Superseded Photos session must not invoke its host completion")
        superseded.isInverted = true
        var staleCallbacks = 0
        editor.finishContentEditing { _ in
            staleCallbacks += 1
            superseded.fulfill()
        }
        // Same PHContentEditingInput object, new host session: object identity alone
        // must not authorize an older asynchronous completion.
        editor.startContentEditing(with: input, placeholderImage: placeholder)
        XCTAssertTrue(editor.view.isUserInteractionEnabled)
        let replacement = expectation(description: "Replacement Photos session completes successfully once")
        replacement.assertForOverFulfill = true
        var replacementCallbacks = 0
        editor.finishContentEditing { output in
            replacementCallbacks += 1
            XCTAssertNotNil(output)
            replacement.fulfill()
        }
        // Completing a later export also drains the shared serial export work;
        // canceled/superseded operations must remain silent throughout it.
        wait(for: [replacement], timeout: 10)
        wait(for: [cancelledBeforeFinish, cancelledDuringRender, cancelledAfterRaster, superseded], timeout: 0.25)
        XCTAssertEqual(staleCallbacks, 0)
        XCTAssertEqual(replacementCallbacks, 1)
        XCTAssertTrue(editor.view.isUserInteractionEnabled)

        editor.startContentEditing(with: input, placeholderImage: placeholder)
        editor.restoreFromData(renderedState)
        let earlierFinish = expectation(description: "Repeated finish supersedes the older host completion")
        earlierFinish.isInverted = true
        editor.finishContentEditing { _ in earlierFinish.fulfill() }
        let newestFinish = expectation(description: "Newest finish succeeds exactly once")
        newestFinish.assertForOverFulfill = true
        var newestCallbacks = 0
        editor.finishContentEditing { output in
            newestCallbacks += 1
            XCTAssertNotNil(output)
            XCTAssertTrue(editor.view.isUserInteractionEnabled)
            newestFinish.fulfill()
        }
        XCTAssertFalse(editor.view.isUserInteractionEnabled)
        let latestTask = try XCTUnwrap(editor.activeExportForTesting)
        let newestStillPreparing = expectation(description: "Older cancellation does not enable UI during the newer render")
        latestTask.consumedRasterObserverForTesting = {
            let acknowledged = DispatchSemaphore(value: 0)
            DispatchQueue.main.async {
                XCTAssertFalse(editor.view.isUserInteractionEnabled)
                newestStillPreparing.fulfill()
                acknowledged.signal()
            }
            _ = acknowledged.wait(timeout: .now() + 5)
        }
        wait(for: [newestStillPreparing, newestFinish], timeout: 10)
        latestTask.consumedRasterObserverForTesting = nil
        wait(for: [earlierFinish], timeout: 0.25)
        XCTAssertEqual(newestCallbacks, 1)
        print("PHOTOS_EXTENSION_CALLBACK_CONTRACT_PASS success_once cancel_before_finish_silent cancel_during_preparation_silent cancel_after_consumed_strip_silent superseded_session_silent repeated_finish_silent newest_finish_success_once controls_disabled_until_current_finish")
        // No PHPhotoLibrary.performChanges: the synthetic library asset is never mutated here.
    }

    func testExtensionWithoutInputCompletesWithFailureExactlyOnce() {
        let editor = PhotoEditingViewController()
        let failed = expectation(description: "Missing input rejected")
        failed.assertForOverFulfill = true
        var callbacks = 0
        editor.finishContentEditing { output in
            callbacks += 1
            XCTAssertNil(output)
            failed.fulfill()
        }
        wait(for: [failed], timeout: 1)
        XCTAssertEqual(callbacks, 1)
    }

    func testCancelledExtensionNeverInvokesHostCompletion() {
        let editor = PhotoEditingViewController()
        editor.cancelContentEditing()
        let result = expectation(description: "Canceled Photos session must not receive a completion")
        result.isInverted = true
        editor.finishContentEditing { _ in result.fulfill() }
        wait(for: [result], timeout: 0.25)
        XCTAssertNil(editor.input)
    }
    func testCollageTemplatesHaveValidPolygons() {
        for count in [CollageImageCount.two, .three, .four] {
            let models = CollageModel.collageModels(count)
            XCTAssertFalse(models.isEmpty)
            for model in models {
                XCTAssertEqual(model.areas.count, count.rawValue)
                for polygon in model.areas {
                    XCTAssertGreaterThanOrEqual(polygon.count, 3)
                    XCTAssertTrue(polygon.allSatisfy { $0.x.isFinite && $0.y.isFinite })
                    XCTAssertFalse(polygon.frameWithNewSize(CGSize(width: 800, height: 800)).isEmpty)
                }
            }
        }
    }
}
