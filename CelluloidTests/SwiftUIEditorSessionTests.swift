import XCTest
import Photos
import SwiftUI
@testable import CelluloidKit

@MainActor
final class SwiftUIEditorSessionTests: XCTestCase {
    private func image(size: CGSize = CGSize(width: 300, height: 200)) -> UIImage {
        let format = UIGraphicsImageRendererFormat(); format.scale = 1
        return UIGraphicsImageRenderer(size: size, format: format).image { context in
            UIColor.red.setFill(); context.fill(CGRect(origin: .zero, size: size))
        }
    }
    func testReadOnlyRecipeIsOpaqueAndRejectsEveryMutation() {
        let session = CelluloidEditingSession()
        session.startCopy(image: image())
        let bytes = Data([0, 1, 2, 3])
        let opaque = PHAdjustmentData(formatIdentifier: "future.editor", formatVersion: "99", data: bytes)
        let current = image()
        session.preserve(opaque, currentImage: current)
        session.selectFilter(.Sepia)
        session.addBubble(BubbleModel.bubbles[0])
        session.addSticker(StickerModel.stickers[0])
        session.restore(AdjustmentData())
        XCTAssertTrue(session.isReadOnly)
        XCTAssertTrue(session.previewImage === current)
        XCTAssertEqual(session.preservedAdjustmentData?.data, bytes)
        XCTAssertEqual(session.preservedAdjustmentData?.formatIdentifier, "future.editor")
        XCTAssertTrue(session.adjustment.bubbles.isEmpty)
        XCTAssertTrue(session.adjustment.stickers.isEmpty)
        XCTAssertEqual(session.adjustment.filterType, .Original)
        let done = expectation(description: "Read-only export refused")
        session.export { result in
            guard case .failure(.invalidState) = result else { XCTFail("Opaque state must not export"); done.fulfill(); return }
            done.fulfill()
        }
        wait(for: [done], timeout: 1)
    }
    func testLayerEditsPreserveAffineTranslationAndCompleteCaption() throws {
        let session = CelluloidEditingSession(); session.startCopy(image: image())
        session.establishCanvas(CGSize(width: 300, height: 200), revision: session.revision)
        var bubble = BubbleModel.bubbles[4]
        bubble.transform = CGAffineTransform(a: 0.8, b: 0.2, c: -0.3, d: 0.9, tx: 3, ty: -2)
        session.addBubble(bubble)
        let originalTransform = session.adjustment.bubbles[0].transform
        session.resizeSelectedLayer(by: 1.1)
        XCTAssertEqual(session.adjustment.bubbles[0].transform, originalTransform)
        let caption = "Hello 世界\n" + String(repeating: "🌈", count: 300)
        session.updateText(caption, layer: .bubble(0), session: session.sessionIdentity)
        session.moveSelectedLayer(x: 9, y: -7)
        let decoded = try AdjustmentData.decode(session.adjustment.encode())
        XCTAssertEqual(decoded.bubbles[0].content, caption)
        XCTAssertEqual(decoded.bubbles[0].transform, originalTransform)
        XCTAssertEqual(decoded.bubbles[0].center, CGPoint(x: 159, y: 93))
        XCTAssertEqual(decoded.referenceCanvasSize, CGSize(width: 300, height: 200))
    }
    func testStaleCaptionCannotAttachToReplacementSession() {
        let session = CelluloidEditingSession(); session.startCopy(image: image())
        session.establishCanvas(CGSize(width: 300, height: 200), revision: session.revision)
        session.addBubble(BubbleModel.bubbles[0])
        let oldToken = session.sessionIdentity
        session.startCopy(image: image())
        session.establishCanvas(CGSize(width: 300, height: 200), revision: session.revision)
        session.addBubble(BubbleModel.bubbles[1])
        session.updateText("Wrong photo", layer: .bubble(0), session: oldToken)
        XCTAssertEqual(session.adjustment.bubbles[0].content, "")
    }
    func testCanvasResizeDoesNotRewriteCanonicalRecipe() throws {
        let session = CelluloidEditingSession(); session.startCopy(image: image())
        session.establishCanvas(CGSize(width: 300, height: 200), revision: session.revision)
        session.addBubble(BubbleModel.bubbles[4]); session.addSticker(StickerModel.stickers[0])
        let original = session.adjustment
        let surface = CelluloidCanvasSurface()
        for size in [CGSize(width: 600, height: 500), CGSize(width: 320, height: 250), CGSize(width: 800, height: 400)] {
            surface.frame = CGRect(origin: .zero, size: size)
            surface.update(image: session.previewImage, recipe: session.adjustment, revision: session.revision)
            surface.layoutIfNeeded()
        }
        XCTAssertEqual(session.adjustment.referenceCanvasSize, original.referenceCanvasSize)
        XCTAssertEqual(session.adjustment.bubbles[0].center, original.bubbles[0].center)
        XCTAssertEqual(session.adjustment.bubbles[0].transform, original.bubbles[0].transform)
        XCTAssertEqual(session.adjustment.stickers[0].center, original.stickers[0].center)
    }
    func testCopyExportKeepsOriginalResolutionAndAdjustmentWireFormat() throws {
        let session = CelluloidEditingSession()
        session.startCopy(image: image(size: CGSize(width: 1800, height: 1200)))
        session.selectFilter(.Sepia)
        let done = expectation(description: "Full resolution copy export")
        session.export { result in
            switch result {
            case .failure(let error): XCTFail("Export failed: \(error)")
            case .success(let export):
                XCTAssertEqual(export.image.cgImage?.width, 1800)
                XCTAssertEqual(export.image.cgImage?.height, 1200)
                XCTAssertEqual(try? AdjustmentData.decode(export.adjustmentData).filterType, .Sepia)
            }
            done.fulfill()
        }
        wait(for: [done], timeout: 10)
        XCTAssertEqual(AdjustmentData.formatIdentifier, "Mango.CelluloidPhotoExtension")
        XCTAssertEqual(AdjustmentData.formatVersion, "1.0")
    }
    func testOddSizedPreviewRasterDoesNotChangeLogicalCanvas() {
        let surface = CelluloidCanvasSurface()
        surface.frame = CGRect(x: 0, y: 0, width: 375, height: 600)
        let source = image(size: CGSize(width: 3001, height: 2003))
        surface.update(image: source, recipe: AdjustmentData(), revision: UUID(), logicalImageSize: source.size)
        surface.layoutIfNeeded()
        let originalFrame = surface.imageView.frame
        // Deliberately rounded, mismatching preview aspect ratio.
        let preview = image(size: CGSize(width: 1400, height: 935))
        surface.update(image: preview, recipe: AdjustmentData(), revision: UUID(), logicalImageSize: source.size)
        surface.layoutIfNeeded()
        XCTAssertEqual(surface.imageView.frame, originalFrame)
    }
    func testCancelledSessionDropsPendingUICompletion() {
        let session = CelluloidEditingSession(); session.startCopy(image: image())
        let stale = expectation(description: "Retired UI cannot consume old export"); stale.isInverted = true
        session.export { _ in stale.fulfill() }
        let task = session.activeExportForTesting
        session.cancel()
        XCTAssertTrue(task?.isCancelled == true)
        XCTAssertEqual(session.phase, .empty)
        XCTAssertNil(session.input)
        wait(for: [stale], timeout: 0.2)
    }
}
