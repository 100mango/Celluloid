import XCTest
import UIKit
import Photos
@testable import Celluloid
@testable import CelluloidKit

@MainActor
final class EditorRegressionTests: XCTestCase {
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
