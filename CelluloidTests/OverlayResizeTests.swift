import XCTest
import UIKit
import Photos
@testable import CelluloidKit

@MainActor
final class OverlayResizeTests: XCTestCase {
    private let sourceSize = CGSize(width: 240, height: 160)

    private func image(_ color: UIColor = .white) -> UIImage {
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        return UIGraphicsImageRenderer(size: sourceSize, format: format).image { context in
            color.setFill()
            context.fill(CGRect(origin: .zero, size: sourceSize))
        }
    }

    private func layout(_ editor: UIViewController, _ size: CGSize) {
        editor.loadViewIfNeeded()
        editor.view.frame = CGRect(origin: .zero, size: size)
        editor.view.setNeedsLayout()
        editor.view.layoutIfNeeded()
        editor.viewDidLayoutSubviews()
    }

    private func editor(size: CGSize = CGSize(width: 300, height: 650), source: UIImage? = nil) -> BaseEditPhotoController {
        let editor = BaseEditPhotoController()
        editor.sourceImage = source ?? image()
        layout(editor, size)
        return editor
    }

    private func decorations(canvas: CGSize?) -> AdjustmentData {
        var state = AdjustmentData()
        state.referenceCanvasSize = canvas
        let size = canvas ?? CGSize(width: 300, height: 200)
        var bubble = BubbleModel.bubbles[4]
        bubble.content = "Hello 世界"
        bubble.bounds = CGRect(x: 0, y: 0, width: 112, height: 80)
        bubble.center = CGPoint(x: size.width * 0.30, y: size.height * 0.33)
        bubble.transform = CGAffineTransform(a: 0.80, b: 0.20, c: -0.20, d: 0.80, tx: 3, ty: -2)
        var sticker = StickerModel.stickers[0]
        sticker.bounds = CGRect(x: 0, y: 0, width: 96, height: 96)
        sticker.center = CGPoint(x: size.width * 0.70, y: size.height * 0.65)
        sticker.transform = CGAffineTransform(a: 0.65, b: -0.15, c: 0.15, d: 0.65, tx: -4, ty: 3)
        state.bubbles = [bubble]
        state.stickers = [sticker]
        return state
    }

    /// Includes relative centers, transformed dimensions and translation, not just counts.
    private func assertGeometry(_ result: AdjustmentData, matches original: AdjustmentData,
                                from originalCanvas: CGSize, file: StaticString = #filePath, line: UInt = #line) throws {
        let canvas = try XCTUnwrap(result.referenceCanvasSize, file: file, line: line)
        XCTAssertEqual(result.bubbles.count, original.bubbles.count, file: file, line: line)
        XCTAssertEqual(result.stickers.count, original.stickers.count, file: file, line: line)
        let actual = result.bubbles.map { ($0.center, $0.bounds, $0.transform) }
            + result.stickers.map { ($0.center, $0.bounds, $0.transform) }
        let expected = original.bubbles.map { ($0.center, $0.bounds, $0.transform) }
            + original.stickers.map { ($0.center, $0.bounds, $0.transform) }
        for (a, e) in zip(actual, expected) {
            XCTAssertEqual(a.0.x / canvas.width, e.0.x / originalCanvas.width, accuracy: 0.000001, file: file, line: line)
            XCTAssertEqual(a.0.y / canvas.height, e.0.y / originalCanvas.height, accuracy: 0.000001, file: file, line: line)
            XCTAssertEqual(a.1, e.1, "Preserve decoration-local layout and text metrics", file: file, line: line)
            let actualRect = a.1.applying(a.2)
            let expectedRect = e.1.applying(e.2)
            XCTAssertEqual(actualRect.width / canvas.width, expectedRect.width / originalCanvas.width, accuracy: 0.000001, file: file, line: line)
            XCTAssertEqual(actualRect.height / canvas.height, expectedRect.height / originalCanvas.height, accuracy: 0.000001, file: file, line: line)
            XCTAssertEqual(a.2.tx / canvas.width, e.2.tx / originalCanvas.width, accuracy: 0.000001, file: file, line: line)
            XCTAssertEqual(a.2.ty / canvas.height, e.2.ty / originalCanvas.height, accuracy: 0.000001, file: file, line: line)
        }
    }

    private func pixels(_ image: UIImage) throws -> [UInt8] {
        let cgImage = try XCTUnwrap(image.cgImage)
        var bytes = [UInt8](repeating: 0, count: cgImage.width * cgImage.height * 4)
        let rendered = bytes.withUnsafeMutableBytes { buffer -> Bool in
            guard let context = CGContext(data: buffer.baseAddress, width: cgImage.width, height: cgImage.height,
                                          bitsPerComponent: 8, bytesPerRow: cgImage.width * 4,
                                          space: CGColorSpaceCreateDeviceRGB(),
                                          bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return false }
            context.draw(cgImage, in: CGRect(x: 0, y: 0, width: CGFloat(cgImage.width), height: CGFloat(cgImage.height)))
            return true
        }
        XCTAssertTrue(rendered)
        return bytes
    }

    private func assertSamePixels(_ actual: UIImage, _ expected: UIImage,
                                  file: StaticString = #filePath, line: UInt = #line) throws {
        XCTAssertEqual(actual.size, expected.size, file: file, line: line)
        let a = try pixels(actual)
        let e = try pixels(expected)
        XCTAssertEqual(a.count, e.count, file: file, line: line)
        guard a.count == e.count else { return }
        let differences = zip(a, e).map { abs(Int($0.0) - Int($0.1)) }
        // Allow subpixel antialiasing rounding; a shifted or resized decoration
        // changes hundreds of pixels and easily exceeds both thresholds.
        XCTAssertLessThan(Double(differences.reduce(0, +)) / Double(a.count), 0.35, file: file, line: line)
        XCTAssertLessThan(Double(differences.filter { $0 > 3 }.count) / Double(a.count), 0.01, file: file, line: line)
    }

    func testHalvingCanvasHalvesCenterAndFullAffineTransform() throws {
        let preview = UIImageView(image: image())
        preview.contentMode = .scaleAspectFit
        preview.frame = CGRect(x: 0, y: 0, width: 300, height: 200)
        let overlay = ImageOverlayView.makeViewOverlaysImageView(preview)
        var state = decorations(canvas: CGSize(width: 300, height: 200))
        state.bubbles[0].center = CGPoint(x: 150, y: 100)
        state.stickers[0].center = CGPoint(x: 150, y: 100)
        overlay.restore(state)
        preview.frame.size = CGSize(width: 150, height: 100)
        overlay.adjustFrame()
        XCTAssertEqual(overlay.bubbleModels[0].center, CGPoint(x: 75, y: 50))
        XCTAssertEqual(overlay.stickerModels[0].center, CGPoint(x: 75, y: 50))
        XCTAssertEqual(overlay.bubbleModels[0].transform.tx, 1.5)
        XCTAssertEqual(overlay.stickerModels[0].transform.ty, 1.5)
        XCTAssertEqual(overlay.bubbleModels[0].bounds, state.bubbles[0].bounds)
        let result = overlay.bubbleModels[0].transform
        overlay.adjustFrame()
        XCTAssertEqual(overlay.bubbleModels[0].transform, result, "Repeated layout must not double-scale")
    }

    func testPortraitLandscapeSplitViewAndRoundTripPreserveGeometryAndExportPixels() throws {
        let editor = editor()
        let blank = try XCTUnwrap(editor.outputImage)
        let original = decorations(canvas: editor.preview.imageRect.size)
        editor.restoreFromData(original)
        let decorated = try XCTUnwrap(editor.outputImage)
        XCTAssertNotEqual(try pixels(blank), try pixels(decorated), "Must actually render decorations")
        let sizes = [CGSize(width: 650, height: 300), CGSize(width: 150, height: 300),
                     CGSize(width: 1032, height: 1376), CGSize(width: 1376, height: 1032),
                     CGSize(width: 320, height: 568), CGSize(width: 300, height: 650)]
        for size in sizes {
            layout(editor, size)
            let state = editor.adjustmentData
            try assertGeometry(state, matches: original, from: try XCTUnwrap(original.referenceCanvasSize))
            try assertSamePixels(try XCTUnwrap(editor.outputImage), decorated)
            editor.restoreFromData(try AdjustmentData.decode(state.encode()))
            try assertSamePixels(try XCTUnwrap(editor.outputImage), decorated)
        }
    }

    func testBubbleAndStickerIndividuallyKeepTheirRenderedPixelsAfterResize() throws {
        for isBubble in [true, false] {
            let editor = editor()
            let blank = try XCTUnwrap(editor.outputImage)
            var state = decorations(canvas: editor.preview.imageRect.size)
            if isBubble { state.stickers = [] } else { state.bubbles = [] }
            editor.restoreFromData(state)
            let decorated = try XCTUnwrap(editor.outputImage)
            XCTAssertNotEqual(try pixels(blank), try pixels(decorated))
            layout(editor, CGSize(width: 844, height: 390))
            try assertSamePixels(try XCTUnwrap(editor.outputImage), decorated)
        }
    }

    func testZeroSizedIntermediateLayoutRetainsLastCoordinateSpace() throws {
        let editor = editor()
        let original = decorations(canvas: editor.preview.imageRect.size)
        editor.restoreFromData(original)
        let output = try XCTUnwrap(editor.outputImage)
        editor.preview.bounds.size = .zero
        editor.overlayView.adjustFrame()
        XCTAssertEqual(editor.overlayView.referenceCanvasSize, original.referenceCanvasSize)
        XCTAssertEqual(editor.overlayView.bubbleModels[0].center, original.bubbles[0].center)
        XCTAssertEqual(editor.overlayView.stickerModels[0].transform, original.stickers[0].transform)
        layout(editor, CGSize(width: 844, height: 390))
        try assertGeometry(editor.adjustmentData, matches: original, from: try XCTUnwrap(original.referenceCanvasSize))
        try assertSamePixels(try XCTUnwrap(editor.outputImage), output)
    }

    func testNewArchiveRestoresAcrossDevicesBeforeOrAfterSourceAndLayout() throws {
        let originalEditor = editor()
        originalEditor.restoreFromData(decorations(canvas: originalEditor.preview.imageRect.size))
        let archived = try AdjustmentData.decode(originalEditor.adjustmentData.encode())
        let output = try XCTUnwrap(originalEditor.outputImage)
        for restoreBeforeLayout in [true, false] {
            let restored = BaseEditPhotoController()
            if restoreBeforeLayout {
                restored.restoreFromData(archived)
                // Layout without a source must not consume the stored canvas size.
                layout(restored, CGSize(width: 1032, height: 1376))
                XCTAssertEqual(restored.overlayView.referenceCanvasSize, archived.referenceCanvasSize)
                restored.sourceImage = image()
            } else {
                restored.sourceImage = image()
                layout(restored, CGSize(width: 1032, height: 1376))
                restored.restoreFromData(archived)
            }
            layout(restored, CGSize(width: 1032, height: 1376))
            try assertGeometry(restored.adjustmentData, matches: archived, from: try XCTUnwrap(archived.referenceCanvasSize))
            try assertSamePixels(try XCTUnwrap(restored.outputImage), output)
        }
    }

    func testLegacyArchiveKeepsAbsolutePointsAtFirstValidLayoutThenTracksResizes() throws {
        let original = decorations(canvas: nil)
        let legacyObject = original.toJSON()
        let bytes = try NSKeyedArchiver.archivedData(withRootObject: legacyObject, requiringSecureCoding: false)
        let legacy = try AdjustmentData.decode(bytes)
        XCTAssertNil(legacy.referenceCanvasSize)
        XCTAssertNil((try AdjustmentData.decode(legacy.encode()).toJSON() as? [String: Any])?["referenceCanvasSize"])
        for restoreBeforeLayout in [true, false] {
            let editor = BaseEditPhotoController()
            if restoreBeforeLayout { editor.restoreFromData(legacy) }
            editor.sourceImage = image()
            layout(editor, CGSize(width: 600, height: 900))
            if !restoreBeforeLayout { editor.restoreFromData(legacy) }
            let first = editor.adjustmentData
            // 1.0 never stored the old device width. Do not infer 300pt from
            // model positions or silently reinterpret its raw points as ratios.
            XCTAssertEqual(first.bubbles[0].center, legacy.bubbles[0].center)
            XCTAssertEqual(first.stickers[0].transform, legacy.stickers[0].transform)
            let output = try XCTUnwrap(editor.outputImage)
            layout(editor, CGSize(width: 300, height: 650))
            try assertGeometry(editor.adjustmentData, matches: first, from: try XCTUnwrap(first.referenceCanvasSize))
            try assertSamePixels(try XCTUnwrap(editor.outputImage), output)
        }
    }

    func testOptionalReferenceCanvasRejectsWrongTypeZeroNegativeAndNonfiniteValues() throws {
        let invalid: [Any] = [NSNumber(value: 1), NSValue(cgPoint: .zero), NSValue(cgSize: .zero),
                              NSValue(cgSize: CGSize(width: -1, height: 200)),
                              NSValue(cgSize: CGSize(width: 300, height: CGFloat.infinity)),
                              NSValue(cgSize: CGSize(width: CGFloat.nan, height: 200))]
        for value in invalid {
            XCTAssertThrowsError(try AdjustmentData(object: ["filterType": "Original", "referenceCanvasSize": value]))
        }
        var state = AdjustmentData()
        state.referenceCanvasSize = CGSize(width: 0, height: 100)
        XCTAssertThrowsError(try state.encode())
        state.referenceCanvasSize = CGSize(width: 300, height: 200)
        XCTAssertEqual(try AdjustmentData.decode(state.encode()).referenceCanvasSize, state.referenceCanvasSize)
    }

    func testSourceReplacementReappliesSameFilterAndResetInputClearsOldSession() throws {
        let editor = editor(source: image(.red))
        var state = decorations(canvas: editor.preview.imageRect.size)
        state.filterType = .Invert
        editor.restoreFromData(state)
        let replacement = image(.blue)
        editor.sourceImage = replacement
        wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in !editor.isPreviewRendering }, object: nil)], timeout: 10)
        try assertSamePixels(try XCTUnwrap(editor.preview.image), replacement.filteredImage(Filters.filter(.Invert)))
        editor.restoreFromData(state) // Selecting the same filter must still use the new source.
        wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in !editor.isPreviewRendering }, object: nil)], timeout: 10)
        try assertSamePixels(try XCTUnwrap(editor.preview.image), replacement.filteredImage(Filters.filter(.Invert)))
        XCTAssertNotEqual(try pixels(try XCTUnwrap(editor.preview.image)), try pixels(replacement))
        editor.input = nil
        XCTAssertNil(editor.sourceImage)
        XCTAssertNil(editor.preview.image)
        XCTAssertNil(editor.outputImage)
        XCTAssertNil(editor.overlayView.referenceCanvasSize)
        XCTAssertEqual(editor.adjustmentData.filterType, .Original)
        XCTAssertTrue(editor.adjustmentData.bubbles.isEmpty)
        XCTAssertTrue(editor.adjustmentData.stickers.isEmpty)
        editor.sourceImage = replacement
        try assertSamePixels(try XCTUnwrap(editor.preview.image), replacement)
    }

    func testOriginalUndecoratedOutputDoesNotRequirePreviewLayout() throws {
        let editor = BaseEditPhotoController()
        editor.sourceImage = image(.purple)
        XCTAssertFalse(editor.isViewLoaded)
        let output = try XCTUnwrap(editor.outputImage)
        try assertSamePixels(output, try XCTUnwrap(editor.sourceImage))
        XCTAssertEqual(output.size, sourceSize)
    }

    func testOrientedSourceDecorationPixelsStayFixedAfterResize() throws {
        let source = image(.yellow)
        let oriented = UIImage(cgImage: try XCTUnwrap(source.cgImage), scale: 1, orientation: .right)
        let editor = editor(source: oriented)
        editor.restoreFromData(decorations(canvas: editor.preview.imageRect.size))
        let output = try XCTUnwrap(editor.outputImage)
        XCTAssertEqual(output.size, CGSize(width: 160, height: 240))
        layout(editor, CGSize(width: 844, height: 390))
        try assertSamePixels(try XCTUnwrap(editor.outputImage), output)
    }

    func testPhotosExtensionRestartWithoutAdjustmentClearsDecorationsFilterAndCancellation() throws {
        XCTAssertEqual(PHPhotoLibrary.authorizationStatus(for: .readWrite), .authorized)
        let asset = try XCTUnwrap(CelluloidTestFixtures.syntheticAsset())
        let ready = expectation(description: "Unadjusted fixture input")
        var loadedInput: PHContentEditingInput?
        let options = PHContentEditingInputRequestOptions()
        options.isNetworkAccessAllowed = false
        asset.requestContentEditingInput(with: options) { input, _ in
            DispatchQueue.main.async { loadedInput = input; ready.fulfill() }
        }
        wait(for: [ready], timeout: 15)
        let input = try XCTUnwrap(loadedInput)
        XCTAssertNil(input.adjustmentData, "The seeded fixture must remain unmodified")
        let placeholder = try XCTUnwrap(input.displaySizeImage)
        let editor = PhotoEditingViewController()
        layout(editor, CGSize(width: 390, height: 844))
        let testWindow = try mountControllerTestWindow(editor, size: editor.view.bounds.size)
        defer { testWindow.rootViewController = nil; testWindow.isHidden = true }
        editor.startContentEditing(with: input, placeholderImage: placeholder)
        waitForSwiftUIEditor(editor)
        let undecorated = try XCTUnwrap(editor.outputImage)
        var state = decorations(canvas: editor.preview.imageRect.size)
        state.filterType = .Sepia
        editor.restoreFromData(state)
        editor.cancelContentEditing()
        editor.startContentEditing(with: input, placeholderImage: placeholder)
        waitForSwiftUIEditor(editor)
        XCTAssertEqual(editor.adjustmentData.filterType, .Original)
        XCTAssertTrue(editor.adjustmentData.bubbles.isEmpty)
        XCTAssertTrue(editor.adjustmentData.stickers.isEmpty)
        try assertSamePixels(try XCTUnwrap(editor.outputImage), undecorated)
        let finished = expectation(description: "Restarted session completes")
        editor.finishContentEditing { output in
            XCTAssertNotNil(output)
            finished.fulfill()
        }
        wait(for: [finished], timeout: 10)
    }
}
