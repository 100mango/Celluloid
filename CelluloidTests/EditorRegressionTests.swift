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
    func testReadOnlyAdjustmentKeepsOpaqueBytesAndCurrentPixelsUntilNewInput() throws {
        let format = UIGraphicsImageRendererFormat(); format.scale = 1
        let current = UIGraphicsImageRenderer(size: CGSize(width: 120, height: 80), format: format).image { context in
            UIColor.red.setFill(); context.fill(CGRect(x: 0, y: 0, width: 60, height: 80))
            UIColor.blue.setFill(); context.fill(CGRect(x: 60, y: 0, width: 60, height: 80))
        }
        let opaqueBytes = Data([0, 1, 2, 3])
        let opaque = PHAdjustmentData(formatIdentifier: AdjustmentData.formatIdentifier, formatVersion: "1.0", data: opaqueBytes)
        let editor = BaseEditPhotoController(); editor.loadViewIfNeeded()
        editor.view.frame = CGRect(x: 0, y: 0, width: 375, height: 667)
        editor.sourceImage = current; editor.view.layoutIfNeeded()
        editor.preserveUnreadableAdjustment(opaque, currentImage: current)
        XCTAssertTrue(editor.isAdjustmentReadOnly)
        XCTAssertTrue(editor.preservedAdjustmentData === opaque)
        XCTAssertEqual(editor.preservedAdjustmentData?.data, opaqueBytes)
        XCTAssertTrue(editor.preview.image === current)
        XCTAssertNil(editor.outputImage)
        var replacement = AdjustmentData(); replacement.filterType = .Sepia
        editor.restoreFromData(replacement)
        XCTAssertTrue(editor.preview.image === current, "An old restore call cannot alter a protected current preview")
        editor.editPhotoToolBar(editor.toolBar, didSelectFilter: .Sepia)
        editor.editPhotoToolBar(editor.toolBar, didSelectSticker: StickerModel.stickers[0])
        editor.editPhotoToolBar(editor.toolBar, didSelectBubble: BubbleModel.bubbles[0])
        XCTAssertTrue(editor.preview.image === current, "Late panel callbacks cannot edit protected state")
        XCTAssertTrue(editor.adjustmentData.stickers.isEmpty)
        XCTAssertTrue(editor.adjustmentData.bubbles.isEmpty)
        XCTAssertEqual(editor.adjustmentData.filterType, .Original)
        let rejected = expectation(description: "Read-only export fails exactly once without replacement data")
        rejected.assertForOverFulfill = true
        editor.exportPhoto { result in
            if case .failure(.invalidState) = result {} else { XCTFail("Protected opaque state produced an export") }
            rejected.fulfill()
        }
        wait(for: [rejected], timeout: 1)
        XCTAssertEqual(editor.preservedAdjustmentData?.data, opaqueBytes)
        editor.input = nil
        editor.sourceImage = current
        XCTAssertFalse(editor.isAdjustmentReadOnly)
        XCTAssertNil(editor.preservedAdjustmentData)
        XCTAssertNotNil(editor.outputImage, "A separate fresh input is not blocked by prior opaque state")
    }
    func testPickerCallbacksRemainBoundToTheirOriginalEditingSession() throws {
        let editor = BaseEditPhotoController(); editor.loadViewIfNeeded()
        let format = UIGraphicsImageRendererFormat(); format.scale = 1
        let image = UIGraphicsImageRenderer(size: CGSize(width: 120, height: 80), format: format).image { context in
            UIColor.red.setFill(); context.fill(CGRect(x: 0, y: 0, width: 120, height: 80))
        }
        editor.view.frame = CGRect(x: 0, y: 0, width: 375, height: 667)
        editor.sourceImage = image; editor.view.layoutIfNeeded()
        let opaque = PHAdjustmentData(formatIdentifier: AdjustmentData.formatIdentifier, formatVersion: "1.0", data: Data([1,2,3]))
        for kind in 0..<3 {
            editor.input = nil; editor.sourceImage = image; editor.view.layoutIfNeeded()
            let sendOldSelection: () -> Void
            switch kind {
            case 0:
                let picker = editor.toolBar.makeFilterPicker()
                sendOldSelection = { picker.delegate?.filterPickerViewController(picker, didSelectFilter: .Sepia) }
            case 1:
                let picker = editor.toolBar.makeStickerPicker()
                sendOldSelection = { picker.delegate?.stickerPickerViewController(picker, didSelectSticker: StickerModel.stickers[0]) }
            default:
                let picker = editor.toolBar.makeBubblePicker()
                sendOldSelection = { picker.delegate?.bubblePickerViewController(picker, didSelectBubble: BubbleModel.bubbles[0]) }
            }
            editor.preserveUnreadableAdjustment(opaque, currentImage: image)
            // Reset protection before the retained old callback. Each picker is
            // independently active at invalidation, rather than already replaced
            // by registration of another picker during test setup.
            editor.input = nil; editor.sourceImage = image; editor.view.layoutIfNeeded()
            sendOldSelection()
            XCTAssertEqual(editor.adjustmentData.filterType, .Original)
            XCTAssertTrue(editor.adjustmentData.stickers.isEmpty)
            XCTAssertTrue(editor.adjustmentData.bubbles.isEmpty)
            XCTAssertTrue(editor.preview.image === image)
        }
        let currentFilter = editor.toolBar.makeFilterPicker()
        currentFilter.delegate?.filterPickerViewController(currentFilter, didSelectFilter: .Sepia)
        XCTAssertEqual(editor.adjustmentData.filterType, .Sepia, "Current-session filter still works")
        currentFilter.delegate?.filterPickerViewController(currentFilter, didSelectFilter: .Original)
        XCTAssertEqual(editor.adjustmentData.filterType, .Sepia, "One selection cannot be delivered twice")
        let currentSticker = editor.toolBar.makeStickerPicker()
        currentSticker.delegate?.stickerPickerViewController(currentSticker, didSelectSticker: StickerModel.stickers[0])
        XCTAssertEqual(editor.adjustmentData.stickers.count, 1)
        currentSticker.delegate?.stickerPickerViewController(currentSticker, didSelectSticker: StickerModel.stickers[0])
        XCTAssertEqual(editor.adjustmentData.stickers.count, 1, "Duplicate sticker selection is consumed")
        let currentBubble = editor.toolBar.makeBubblePicker()
        currentBubble.delegate?.bubblePickerViewController(currentBubble, didSelectBubble: BubbleModel.bubbles[0])
        XCTAssertEqual(editor.adjustmentData.bubbles.count, 1)
        currentBubble.delegate?.bubblePickerViewController(currentBubble, didSelectBubble: BubbleModel.bubbles[0])
        XCTAssertEqual(editor.adjustmentData.bubbles.count, 1, "Duplicate bubble selection is consumed")
        let previous = editor.toolBar.makeFilterPicker()
        editor.input = nil; editor.sourceImage = image
        previous.delegate?.filterPickerViewController(previous, didSelectFilter: .Sepia)
        XCTAssertEqual(editor.adjustmentData.filterType, .Original, "Ordinary new-input reset also invalidates old panels")
    }

    func testResourceBudgetRejectsSnapshotBeforeDecodeOrRasterWithoutTruncation() throws {
        final class SnapshotEditor: BaseEditPhotoController {
            var snapshot = AdjustmentData()
            override var adjustmentData: AdjustmentData { snapshot }
        }
        let editor = SnapshotEditor(); editor.loadViewIfNeeded()
        var bubble = BubbleModel.bubbles[0]
        bubble.content = String(repeating: "界", count: AdjustmentData.maximumBubbleTextUTF16Units + 1)
        editor.snapshot.bubbles = [bubble]
        // No source image: resource rejection must precede missing-image/decode.
        let done = expectation(description: "Oversized edit rejected once before expensive export")
        done.assertForOverFulfill = true
        let task = editor.exportPhoto { result in
            if case .failure(.adjustmentTooComplex) = result {} else { XCTFail("Budget was not checked before source loading") }
            done.fulfill()
        }
        wait(for: [done], timeout: 5)
        XCTAssertEqual(task.storageStatistics.rasterizedCount, 0)
        XCTAssertEqual(editor.snapshot.bubbles.count, 1)
        XCTAssertEqual(editor.snapshot.bubbles[0].content, bubble.content)
        XCTAssertNil(editor.input)
    }

    func testExtensionNegotiatesKnownFormatWithoutDecodingUnboundData() throws {
        let editor = PhotoEditingViewController()
        let valid = try AdjustmentData().encode()
        XCTAssertTrue(editor.canHandle(PHAdjustmentData(formatIdentifier: AdjustmentData.formatIdentifier, formatVersion: "1.0", data: valid)))
        XCTAssertFalse(editor.canHandle(PHAdjustmentData(formatIdentifier: "Other", formatVersion: "1.0", data: valid)))
        // Malformed known-format data must reach the bound start-input error
        // path, rather than making Photos silently provide a flattened edit.
        XCTAssertTrue(editor.canHandle(PHAdjustmentData(formatIdentifier: AdjustmentData.formatIdentifier, formatVersion: "1.0", data: Data([0,1,2]))))
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
        func pauseActualOutputWrite() throws -> (PhotosOutputWrite, DispatchSemaphore, XCTestExpectation) {
            let entered = expectation(description: "Adapter reached actual queued output write")
            let release = DispatchSemaphore(value: 0)
            var actualWriter: PhotosOutputWrite?
            editor.outputWriterPreparedForTesting = { writer in
                actualWriter = writer
                writer.beforeWriteForTesting = { entered.fulfill(); _ = release.wait(timeout: .now() + 5) }
            }
            let oldCallback = expectation(description: "Abandoned output writer has no Photos callback")
            oldCallback.isInverted = true
            editor.finishContentEditing { _ in oldCallback.fulfill() }
            wait(for: [entered], timeout: 10)
            editor.outputWriterPreparedForTesting = nil
            guard let writer = actualWriter else { release.signal(); throw NSError(domain: "Celluloid.WriteProbe", code: 1) }
            XCTAssertFalse(FileManager.default.fileExists(atPath: writer.destination.path))
            return (writer, release, oldCallback)
        }
        func drainActualOutputWrites() {
            let drained = expectation(description: "Adapter output cleanup completed")
            PhotosOutputWrite.afterPendingWorkForTesting { drained.fulfill() }
            wait(for: [drained], timeout: 5)
        }
        editor.startContentEditing(with: input, placeholderImage: placeholder)
        let canceledWrite = try pauseActualOutputWrite()
        editor.cancelContentEditing()
        canceledWrite.1.signal(); drainActualOutputWrites()
        wait(for: [canceledWrite.2], timeout: 0.1)
        XCTAssertFalse(FileManager.default.fileExists(atPath: canceledWrite.0.destination.path))

        editor.startContentEditing(with: input, placeholderImage: placeholder)
        let replacedWrite = try pauseActualOutputWrite()
        // Exactly the same PHContentEditingInput identity starts a new session.
        editor.startContentEditing(with: input, placeholderImage: placeholder)
        let replacementWritten = expectation(description: "Replacement output completes once")
        replacementWritten.assertForOverFulfill = true
        editor.finishContentEditing { output in
            XCTAssertNotNil(output)
            if let output = output { XCTAssertNotNil(UIImage(contentsOfFile: output.renderedContentURL.path)) }
            replacementWritten.fulfill()
        }
        XCTAssertFalse(editor.view.isUserInteractionEnabled)
        replacedWrite.1.signal()
        wait(for: [replacementWritten], timeout: 10); drainActualOutputWrites()
        wait(for: [replacedWrite.2], timeout: 0.1)
        XCTAssertFalse(FileManager.default.fileExists(atPath: replacedWrite.0.destination.path))
        XCTAssertTrue(editor.view.isUserInteractionEnabled)

        editor.startContentEditing(with: input, placeholderImage: placeholder)
        let protectedReplacementWrite = try pauseActualOutputWrite()
        editor.startContentEditing(with: input, placeholderImage: placeholder)
        // This directly tests the protected adapter mode. Actual malformed-bound
        // PhotoKit input and host preservation have separate integration gates.
        editor.preserveUnreadableAdjustment(PHAdjustmentData(formatIdentifier: AdjustmentData.formatIdentifier,
            formatVersion: "1.0", data: Data([1,2,3])), currentImage: placeholder)
        let protectedDone = expectation(description: "Protected replacement yields no-change output")
        protectedDone.assertForOverFulfill = true
        editor.finishContentEditing { output in
            XCTAssertNotNil(output)
            XCTAssertNil(output?.adjustmentData)
            if let output = output { XCTAssertFalse(FileManager.default.fileExists(atPath: output.renderedContentURL.path)) }
            protectedDone.fulfill()
        }
        protectedReplacementWrite.1.signal()
        wait(for: [protectedDone], timeout: 2); drainActualOutputWrites()
        wait(for: [protectedReplacementWrite.2], timeout: 0.1)
        XCTAssertFalse(FileManager.default.fileExists(atPath: protectedReplacementWrite.0.destination.path))
        print("PHOTOS_EXTENSION_CALLBACK_CONTRACT_ASSERTIONS_COMPLETED success_cancel_supersession_repeated_finish_and_queued_write use_terminal_test_status")
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
