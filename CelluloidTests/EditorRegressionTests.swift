import XCTest
import UIKit
import Photos
@testable import Celluloid
@testable import CelluloidKit

@MainActor
final class EditorRegressionTests: XCTestCase {
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

    func testEditorRendersAndRestoresWithoutDuplicatingOverlays() throws {
        let editor = BaseEditPhotoController()
        editor.loadViewIfNeeded()
        editor.view.frame = CGRect(x: 0, y: 0, width: 390, height: 844)
        editor.sourceImage = UIGraphicsImageRenderer(size: CGSize(width: 96, height: 64)).image { context in
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
        let asset = try XCTUnwrap(PHAsset.fetchAssets(with: .image, options: nil).firstObject)
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
        editor.cancelContentEditing()
        let cancelled = expectation(description: "Cancelled extension output")
        editor.finishContentEditing { output in
            XCTAssertNil(output)
            cancelled.fulfill()
        }
        wait(for: [cancelled], timeout: 1)
        // No PHPhotoLibrary.performChanges: the synthetic library asset is never mutated here.
    }

    func testExtensionWithoutInputCompletesWithFailureExactlyOnce() {
        let editor = PhotoEditingViewController()
        let failed = expectation(description: "Missing input rejected")
        var callbacks = 0
        editor.finishContentEditing { output in
            callbacks += 1
            XCTAssertNil(output)
            failed.fulfill()
        }
        wait(for: [failed], timeout: 1)
        XCTAssertEqual(callbacks, 1)
    }

    func testCancelledExtensionNeverReturnsOutput() {
        let editor = PhotoEditingViewController()
        editor.cancelContentEditing()
        let result = expectation(description: "cancel completion")
        editor.finishContentEditing { output in XCTAssertNil(output); result.fulfill() }
        wait(for: [result], timeout: 1)
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
