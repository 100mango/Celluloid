import XCTest
import UIKit
import ImageIO
import CryptoKit
@testable import CelluloidKit

@MainActor
final class ExportAndInteractionTests: XCTestCase {
    func testReleasedWarmingCopyWithoutCropKeepsStrictPixels() throws {
        setenv("CELLULOID_EXPORT_WARMING_ONLY_CONTROL", "1", 1)
        defer { unsetenv("CELLULOID_EXPORT_WARMING_ONLY_CONTROL") }
        print("WARMING_COPY_RELEASE_CONTROL_ORACLES crop=false")
        try testOffMainCompositeMatchesLegacyAffineAlphaAndColorRendering()
        try testStreamingTileBoundariesAndManyOverlaysMatchLegacyPixels()
        try testUnevenRotatedAndScaledStripCanvasesMatchLegacyPixels()
        try testExtendedRangeSourceMatchesLegacyRendererBitmapAndPixels()
    }

    func testFullCanvasControlsKeepEveryStrictPixelOracle() throws {
        defer { unsetenv("CELLULOID_EXPORT_FULL_CANVAS_CONTROL") }
        for mode in ["layer", "direct"] {
            setenv("CELLULOID_EXPORT_FULL_CANVAS_CONTROL", mode, 1)
            print("FULL_CANVAS_CONTROL_ORACLES mode=\(mode)")
            try testAsyncDecoratedExportExcludesVisibleEditorHandles()
            try testOffMainCompositeMatchesLegacyAffineAlphaAndColorRendering()
            try testStreamingTileBoundariesAndManyOverlaysMatchLegacyPixels()
            try testUnevenRotatedAndScaledStripCanvasesMatchLegacyPixels()
            try testExtendedRangeSourceMatchesLegacyRendererBitmapAndPixels()
            testSourceScaleAndExifDoNotChangeFullResolutionWhenDecorated()
        }
    }

    func testTwelveMegapixelExportPreservesDimensionsAndAllowsMainQueueHeartbeat() {
        let format = UIGraphicsImageRendererFormat(); format.scale = 1
        let source = UIGraphicsImageRenderer(size: CGSize(width: 4000, height: 3000), format: format).image { context in
            UIColor.red.setFill(); context.fill(CGRect(x: 0, y: 0, width: 2000, height: 3000))
            UIColor.blue.setFill(); context.fill(CGRect(x: 2000, y: 0, width: 2000, height: 3000))
        }
        let editor = BaseEditPhotoController()
        editor.loadViewIfNeeded()
        editor.view.frame = CGRect(x: 0, y: 0, width: 375, height: 667)
        editor.sourceImage = source
        editor.view.layoutIfNeeded()
        let heartbeat = expectation(description: "Main queue remains available while JPEG is prepared")
        let finished = expectation(description: "Full-resolution export")
        let started = Date()
        editor.exportPhoto { result in
            XCTAssertTrue(Thread.isMainThread)
            switch result {
            case .success(let output):
                XCTAssertEqual(output.image.cgImage?.width, 4000)
                XCTAssertEqual(output.image.cgImage?.height, 3000)
                let decoded = UIImage(data: output.jpegData)!
                XCTAssertEqual(decoded.cgImage?.width, 4000)
                XCTAssertEqual(decoded.cgImage?.height, 3000)
                XCTAssertGreaterThan(self.pixel(decoded, x: 100, y: 100)[0], 240)
                XCTAssertGreaterThan(self.pixel(decoded, x: 3900, y: 2900)[2], 240)
                print("EXPORT_12MP completed_seconds=\(Date().timeIntervalSince(started)) pixels=4000x3000 jpeg_bytes=\(output.jpegData.count)")
            case .failure(let error): XCTFail("Unexpected export error: \(error)")
            }
            finished.fulfill()
        }
        XCTAssertLessThan(Date().timeIntervalSince(started), 2, "Initiating an asynchronous export must not encode 12MP on the caller")
        DispatchQueue.main.async { heartbeat.fulfill() }
        wait(for: [heartbeat], timeout: 2)
        wait(for: [finished], timeout: 30)
    }

    func testCancelledAndSupersededExportNeverReturnsStaleSuccess() {
        let editor = BaseEditPhotoController()
        editor.loadViewIfNeeded()
        editor.sourceImage = UIGraphicsImageRenderer(size: CGSize(width: 100, height: 50)).image { _ in }
        let cancelled = expectation(description: "Cancelled exactly once")
        var completions = 0
        let task = editor.exportPhoto { result in
            completions += 1
            if case .failure(.cancelled) = result {} else { XCTFail("Cancelled export returned stale output") }
            cancelled.fulfill()
        }
        task.cancel()
        wait(for: [cancelled], timeout: 5)
        XCTAssertEqual(completions, 1)
        let stale = expectation(description: "Source replacement cancels old export")
        editor.exportPhoto { result in
            if case .failure(.cancelled) = result {} else { XCTFail("Replaced source returned stale output") }
            stale.fulfill()
        }
        editor.sourceImage = nil
        wait(for: [stale], timeout: 5)
    }

    func testSourceScaleAndExifDoNotChangeFullResolutionWhenDecorated() {
        let format = UIGraphicsImageRendererFormat(); format.scale = 1
        let raw = UIGraphicsImageRenderer(size: CGSize(width: 480, height: 320), format: format).image { _ in UIColor.red.setFill(); UIRectFill(CGRect(x: 0, y: 0, width: 480, height: 320)) }
        for scale in [CGFloat(1), 2, 3] {
            for orientation in [UIImage.Orientation.up, .right] {
                let editor = BaseEditPhotoController()
                editor.loadViewIfNeeded(); editor.view.frame = CGRect(x: 0, y: 0, width: 375, height: 667)
                editor.sourceImage = UIImage(cgImage: raw.cgImage!, scale: scale, orientation: orientation)
                editor.view.layoutIfNeeded()
                let original = editor.outputImage!
                var data = editor.adjustmentData
                var sticker = StickerModel.stickers[0]
                sticker.center = CGPoint(x: editor.preview.imageRect.width / 2, y: editor.preview.imageRect.height / 2)
                data.stickers = [sticker]
                editor.restoreFromData(data)
                let decorated = editor.outputImage!
                XCTAssertEqual(decorated.cgImage?.width, original.cgImage?.width)
                XCTAssertEqual(decorated.cgImage?.height, original.cgImage?.height)
                XCTAssertEqual(decorated.cgImage?.width, orientation == .right ? 320 : 480)
                XCTAssertEqual(decorated.cgImage?.height, orientation == .right ? 480 : 320)
            }
        }
    }

    func testDegenerateCanvasAndOverflowAreRejectedBeforeUIKitRescale() {
        for bad in [CGFloat.leastNonzeroMagnitude, .leastNormalMagnitude, .greatestFiniteMagnitude] {
            var data = AdjustmentData()
            data.referenceCanvasSize = CGSize(width: bad, height: 100)
            XCTAssertThrowsError(try data.encode())
        }
        let editor = BaseEditPhotoController(); editor.loadViewIfNeeded()
        editor.view.frame = CGRect(x: 0, y: 0, width: 375, height: 667)
        editor.sourceImage = UIGraphicsImageRenderer(size: CGSize(width: 400, height: 300)).image { _ in }
        editor.view.layoutIfNeeded()
        var data = AdjustmentData()
        data.referenceCanvasSize = CGSize(width: 1, height: 1)
        var sticker = StickerModel.stickers[0]; sticker.center = CGPoint(x: CGFloat.greatestFiniteMagnitude, y: 1)
        data.stickers = [sticker]
        editor.restoreFromData(data)
        XCTAssertNil(editor.outputImage)
        XCTAssertTrue(editor.overlayView.stickerModels[0].center.x.isFinite)
    }

    func testFiniteComponentsWithOverflowingTransformedBoundsAreRejected() {
        var sticker = StickerModel.stickers[0]
        sticker.bounds = CGRect(x: 0, y: 0, width: 1e200, height: 100)
        sticker.transform = CGAffineTransform(scaleX: 1e200, y: 1)
        var data = AdjustmentData(); data.stickers = [sticker]
        XCTAssertThrowsError(try data.encode())
        XCTAssertThrowsError(try StickerModel(object: sticker.toJSON() as! [String: Any]))
        var bubble = BubbleModel.bubbles[0]
        bubble.bounds = sticker.bounds; bubble.transform = sticker.transform
        XCTAssertThrowsError(try BubbleModel(object: bubble.toJSON() as! [String: Any]))
        let overlay = ImageOverlayView()
        overlay.addSticker(sticker); overlay.addBubble(bubble)
        XCTAssertTrue(overlay.subviews.isEmpty, "Reject invalid derived geometry before constructing UIKit views")
    }

    func testGesturePreservesRebasedScaleAndControlsStayFortyFourScreenPoints() {
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first!
        let window = UIWindow(windowScene: scene)
        window.frame = CGRect(x: 0, y: 0, width: 400, height: 400)
        window.rootViewController = UIViewController()
        window.makeKeyAndVisible()
        defer { window.isHidden = true }
        let root = window.rootViewController!.view!
        let attachment = StickerView(stickerModel: StickerModel.stickers[0])
        root.addSubview(attachment)
        for transform in [CGAffineTransform(scaleX: 0.5, y: 0.5), CGAffineTransform(rotationAngle: 0.4).scaledBy(x: 0.3, y: 0.6)] {
            attachment.transform = transform
            attachment.hideButtonEnable = false
            attachment.layoutIfNeeded()
            XCTAssertEqual(AttachView.transformForGesture(initial: transform, angleDelta: 0), transform)
            let rotated = AttachView.transformForGesture(initial: transform, angleDelta: .pi / 6)
            XCTAssertEqual(abs(rotated.a * rotated.d - rotated.b * rotated.c), abs(transform.a * transform.d - transform.b * transform.c), accuracy: 0.0001)
            for button in attachment.subviews.compactMap({ $0 as? UIButton }) {
                XCTAssertGreaterThanOrEqual(button.accessibilityFrame.width, 44 - 0.001)
                XCTAssertGreaterThanOrEqual(button.accessibilityFrame.height, 44 - 0.001)
                XCTAssertFalse(button.accessibilityLabel?.isEmpty ?? true)
                let expandedPoint = button.convert(CGPoint(x: -5, y: button.bounds.midY), to: attachment)
                XCTAssertTrue(attachment.point(inside: expandedPoint, with: nil))
            }
            XCTAssertGreaterThanOrEqual(attachment.imageView.accessibilityCustomActions?.count ?? 0, 8)
        }
    }

    func testAsyncDecoratedExportExcludesVisibleEditorHandles() throws {
        let editor = BaseEditPhotoController(); editor.loadViewIfNeeded()
        editor.view.frame = CGRect(x: 0, y: 0, width: 375, height: 667)
        let format = UIGraphicsImageRendererFormat(); format.scale = 1
        editor.sourceImage = UIGraphicsImageRenderer(size: CGSize(width: 240, height: 160), format: format).image { context in
            UIColor.white.setFill(); context.fill(CGRect(x: 0, y: 0, width: 240, height: 160))
        }
        editor.view.layoutIfNeeded()
        let blank = try XCTUnwrap(editor.outputImage?.pngData())
        var data = editor.adjustmentData
        var sticker = StickerModel.stickers[0]
        sticker.center = CGPoint(x: editor.preview.imageRect.width / 2, y: editor.preview.imageRect.height / 2)
        data.stickers = [sticker]
        editor.restoreFromData(data)
        let reference = try XCTUnwrap(editor.outputImage)
        let expected = try XCTUnwrap(reference.pngData())
        XCTAssertNotEqual(blank, expected)
        editor.overlayView.subviews.compactMap { $0 as? AttachView }.forEach { $0.hideButtonEnable = false }
        let completed = expectation(description: "Decorated snapshot without controls")
        var count = 0
        editor.exportPhoto { result in
            count += 1
            if case .success(let output) = result {
                let actual = output.image.pngData()!
                let decodedActual = self.rgba(UIImage(data: actual)!)
                let decodedExpected = self.rgba(UIImage(data: expected)!)
                var maximum = 0, changed = 0
                for (a, b) in zip(decodedActual, decodedExpected) { let delta = abs(Int(a) - Int(b)); maximum = max(maximum, delta); if delta != 0 { changed += 1 } }
                let wrapped = UIImage(cgImage: reference.cgImage!, scale: reference.scale, orientation: reference.imageOrientation).pngData()!
                print("HANDLE_PNG_PIXEL_DIAGNOSTIC max_delta=\(maximum) changed_channels=\(changed) actual_bytes=\(actual.count) reference_bytes=\(expected.count) matches_rewrapped_reference=\(actual == wrapped)")
                print("HANDLE_PNG_REFERENCE " + self.pngSummary(expected, image: reference))
                print("HANDLE_PNG_ACTUAL " + self.pngSummary(actual, image: output.image))
                XCTAssertEqual(output.image.pngData(), expected)
            }
            else { XCTFail("Decorated export failed") }
            completed.fulfill()
        }
        wait(for: [completed], timeout: 10)
        XCTAssertEqual(count, 1)
    }

    func testAsyncMissingSourceCompletesWithFailureExactlyOnce() {
        let editor = BaseEditPhotoController()
        let failed = expectation(description: "No source returns failure")
        var count = 0
        editor.exportPhoto { result in
            count += 1
            if case .failure(.missingImage) = result {} else { XCTFail("Expected missing image failure") }
            failed.fulfill()
        }
        wait(for: [failed], timeout: 5)
        XCTAssertEqual(count, 1)
    }

    func testOffMainCompositeMatchesLegacyAffineAlphaAndColorRendering() throws {
        let variants: [(CFString, Bool, UIImage.Orientation, CGFloat)] = [
            (CGColorSpace.sRGB, false, .up, 1),
            (CGColorSpace.sRGB, true, .up, 2),
            (CGColorSpace.displayP3, true, .right, 3)
        ]
        for (index, variant) in variants.enumerated() {
            let space = try XCTUnwrap(CGColorSpace(name: variant.0))
            let context = try XCTUnwrap(CGContext(data: nil, width: 480, height: 320, bitsPerComponent: 8,
                bytesPerRow: 480 * 4, space: space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
            context.setFillColor(try XCTUnwrap(CGColor(colorSpace: space, components: [1, 0.1, 0.2, variant.1 ? 0.35 : 1])))
            context.fill(CGRect(x: 0, y: 0, width: 240, height: 320))
            context.setFillColor(try XCTUnwrap(CGColor(colorSpace: space, components: [0.1, 0.7, 1, variant.1 ? 0.8 : 1])))
            context.fill(CGRect(x: 240, y: 0, width: 240, height: 320))
            let source = UIImage(cgImage: try XCTUnwrap(context.makeImage()), scale: variant.3, orientation: variant.2)
            for clipped in [false, true] {
                let editor = BaseEditPhotoController()
                editor.loadViewIfNeeded(); editor.view.frame = CGRect(x: 0, y: 0, width: 375, height: 667)
                editor.sourceImage = source
                editor.view.layoutIfNeeded()
                var data = editor.adjustmentData
                let canvas = try XCTUnwrap(data.referenceCanvasSize)
                var bubble = BubbleModel.bubbles[4]
                bubble.content = "Sharp文字"
                bubble.bounds = CGRect(x: 0, y: 0, width: 128, height: 104)
                bubble.center = CGPoint(x: canvas.width * 0.43 + 0.3, y: canvas.height * 0.53 + 0.7)
                bubble.transform = CGAffineTransform(a: 0.94, b: 0.24, c: -0.2, d: 1.12, tx: 3.2, ty: -4.6)
                var sticker = StickerModel.stickers[0]
                sticker.center = clipped ? CGPoint(x: -8.4, y: 2.6) : CGPoint(x: canvas.width * 0.6, y: canvas.height * 0.5)
                sticker.transform = CGAffineTransform(rotationAngle: -0.27).scaledBy(x: 1.14, y: 0.86)
                data.bubbles = [bubble]; data.stickers = [sticker]
                editor.restoreFromData(data)
                // The synchronous compatibility implementation remains the old
                // full-canvas UIKit renderer, an independent reference here.
                let reference = try XCTUnwrap(editor.outputImage)
                let referencePixels = rgba(reference)
                let finished = expectation(description: "Affine/alpha/color equivalence \(index)/\(clipped)")
                editor.exportPhoto { result in
                    switch result {
                    case .failure(let error): XCTFail("Equivalence export failed: \(error)")
                    case .success(let output):
                        XCTAssertEqual(output.image.cgImage?.width, reference.cgImage?.width)
                        XCTAssertEqual(output.image.cgImage?.height, reference.cgImage?.height)
                        XCTAssertNotNil(reference.cgImage?.colorSpace?.name)
                        XCTAssertEqual(String(describing: output.image.cgImage?.colorSpace?.name), String(describing: reference.cgImage?.colorSpace?.name))
                        XCTAssertEqual(output.image.cgImage?.bitsPerComponent, reference.cgImage?.bitsPerComponent)
                        XCTAssertEqual(output.image.cgImage?.alphaInfo, reference.cgImage?.alphaInfo)
                        let actual = self.rgba(output.image)
                        let differences = zip(actual, referencePixels).map { abs(Int($0.0) - Int($0.1)) }
                        let maximum = differences.max() ?? 0
                        let changed = differences.filter { $0 != 0 }.count
                        print("COMPOSITE_EQUIVALENCE variant=\(index) clipped=\(clipped) maximum_channel_delta=\(maximum) changed_channels=\(changed) total_channels=\(differences.count)")
                        XCTAssertEqual(actual.count, referencePixels.count)
                        XCTAssertEqual(maximum, 0, "Full-resolution affine artwork and alpha/color semantics must match the reference")
                    }
                    finished.fulfill()
                }
                wait(for: [finished], timeout: 15)
            }
        }
    }

    func testStreamingTileBoundariesAndManyOverlaysMatchLegacyPixels() throws {
        try assertManyOverlaysMatchLegacyPixels(width: 1600, height: 1200, scale: 1, orientation: .up)
    }

    func testUnevenRotatedAndScaledStripCanvasesMatchLegacyPixels() throws {
        try assertManyOverlaysMatchLegacyPixels(width: 1603, height: 1207, scale: 2, orientation: .up)
        try assertManyOverlaysMatchLegacyPixels(width: 1603, height: 1207, scale: 3, orientation: .right)
    }

    private func assertManyOverlaysMatchLegacyPixels(width: Int, height: Int, scale: CGFloat, orientation: UIImage.Orientation) throws {
        let format = UIGraphicsImageRendererFormat(); format.scale = 1
        let raster = UIGraphicsImageRenderer(size: CGSize(width: width, height: height), format: format).image { context in
            UIColor(red: 0.8, green: 0.2, blue: 0.1, alpha: 0.4).setFill(); context.fill(CGRect(x: 0, y: 0, width: width / 2, height: height))
            UIColor(displayP3Red: 0.1, green: 0.8, blue: 0.3, alpha: 0.7).setFill(); context.fill(CGRect(x: width / 2, y: 0, width: width - width / 2, height: height))
        }
        let source = UIImage(cgImage: try XCTUnwrap(raster.cgImage), scale: scale, orientation: orientation)
        let editor = BaseEditPhotoController()
        editor.loadViewIfNeeded(); editor.view.frame = CGRect(x: 0, y: 0, width: 375, height: 667)
        editor.sourceImage = source; editor.view.layoutIfNeeded()
        var data = editor.adjustmentData
        let canvas = try XCTUnwrap(data.referenceCanvasSize)
        for index in 0..<6 {
            var bubble = BubbleModel.bubbles[index % BubbleModel.bubbles.count]
            bubble.content = "Tile boundary 文字 \(index)"
            bubble.bounds = CGRect(x: 0, y: 0, width: 340, height: 310)
            bubble.center = CGPoint(x: canvas.width / 2 + CGFloat(index * 4), y: canvas.height / 2 - CGFloat(index * 3))
            bubble.transform = CGAffineTransform(a: 1.12, b: 0.13, c: -0.07, d: 0.94, tx: 0.3, ty: -0.7)
            data.bubbles.append(bubble)
            var sticker = StickerModel.stickers[index]
            sticker.bounds = CGRect(x: 0, y: 0, width: 340, height: 320)
            sticker.center = CGPoint(x: canvas.width / 2 - CGFloat(index * 5), y: canvas.height / 2 + CGFloat(index * 3))
            sticker.transform = CGAffineTransform(rotationAngle: CGFloat(index) * 0.035).scaledBy(x: 1.1, y: 1.05)
            data.stickers.append(sticker)
        }
        editor.restoreFromData(data)
        let reference = try XCTUnwrap(editor.outputImage)
        let expected = rgba(reference)
        let pixelWidth = try XCTUnwrap(reference.cgImage).width
        let pixelHeight = try XCTUnwrap(reference.cgImage).height
        let finished = expectation(description: "Streaming tile seams and twelve overlays")
        editor.exportPhoto { result in
            switch result {
            case .failure(let error): XCTFail("Streaming comparison failed: \(error)")
            case .success(let output):
                XCTAssertEqual(output.image.cgImage?.bitsPerComponent, reference.cgImage?.bitsPerComponent)
                XCTAssertEqual(output.image.cgImage?.bitsPerPixel, reference.cgImage?.bitsPerPixel)
                XCTAssertEqual(output.image.cgImage?.alphaInfo, reference.cgImage?.alphaInfo)
                XCTAssertEqual(String(describing: output.image.cgImage?.colorSpace?.name), String(describing: reference.cgImage?.colorSpace?.name))
                let actual = self.rgba(output.image)
                XCTAssertEqual(actual.count, expected.count)
                XCTAssertEqual(output.image.cgImage?.width, pixelWidth)
                XCTAssertEqual(output.image.cgImage?.height, pixelHeight)
                XCTAssertEqual(try? AdjustmentData.decode(output.adjustmentData).bubbles.count, 6)
                XCTAssertEqual(try? AdjustmentData.decode(output.adjustmentData).stickers.count, 6)
                var maximum = 0, changed = 0
                var samples: [[String: Int]] = []
                for (index, pair) in zip(actual, expected).enumerated() {
                    let delta = abs(Int(pair.0) - Int(pair.1)); maximum = max(maximum, delta)
                    if delta != 0 {
                        changed += 1
                        if samples.count < 16 { samples.append(["x": (index / 4) % pixelWidth, "y": (index / 4) / pixelWidth,
                            "channel": index % 4, "actual": Int(pair.0), "reference": Int(pair.1)]) }
                    }
                }
                if !samples.isEmpty { print("SPATIAL_PIXEL_DIFFERENCE_LOCATIONS " + String(decoding: try! JSONSerialization.data(withJSONObject: samples, options: [.sortedKeys]), as: UTF8.self)) }
                print("STREAMING_MANY_OVERLAY_EQUIVALENCE width=\(pixelWidth) height=\(pixelHeight) source_scale=\(scale) source_orientation=\(orientation.rawValue) maximum_channel_delta=\(maximum) changed_channels=\(changed) channels=\(actual.count)")
                if maximum != 0 {
                    // Diagnose coordinate/clip behavior without changing the strict oracle.
                    let regions = [("full-canvas", CGRect(x: 0, y: 0, width: pixelWidth, height: pixelHeight)),
                                   ("lower-left", CGRect(x: 0, y: pixelHeight - 182, width: min(1022, pixelWidth), height: 182)),
                                   ("full-height-left", CGRect(x: 0, y: 0, width: pixelWidth / 2, height: pixelHeight)),
                                   ("full-height-right", CGRect(x: pixelWidth / 2, y: 0, width: pixelWidth - pixelWidth / 2, height: pixelHeight)),
                                   ("full-width-bottom", CGRect(x: 0, y: pixelHeight - 182, width: pixelWidth, height: 182))]
                    for (name, region) in regions {
                        guard let cropped = reference.cgImage?.cropping(to: region) else { XCTFail("Diagnostic crop missing"); continue }
                        let expectedRegion = self.rgba(UIImage(cgImage: cropped, scale: 1, orientation: .up))
                        for boundsAPI in [false, true] {
                            guard let tile = editor.diagnosticSpatialRender(rect: region, globalBounds: boundsAPI) else { XCTFail("Diagnostic renderer failed"); continue }
                            let actualRegion = self.rgba(tile)
                            var count = 0, delta = 0
                            for pair in zip(actualRegion, expectedRegion) {
                                let d = abs(Int(pair.0) - Int(pair.1)); delta = max(delta, d); if d != 0 { count += 1 }
                            }
                            print("SPATIAL_COORDINATE_PROBE region=\(name) bounds_api=\(boundsAPI) actual_channels=\(actualRegion.count) reference_channels=\(expectedRegion.count) changed=\(count) max_delta=\(delta)")
                        }
                    }
                }
                XCTAssertEqual(maximum, 0, "Do not accept tile seams or altered overlapping alpha/text pixels")
            }
            finished.fulfill()
        }
        wait(for: [finished], timeout: 60)
    }

    func testExtendedRangeSourceMatchesLegacyRendererBitmapAndPixels() throws {
        let space = try XCTUnwrap(CGColorSpace(name: CGColorSpace.extendedLinearDisplayP3))
        let bitmap = CGBitmapInfo.floatComponents.rawValue | CGBitmapInfo.byteOrder16Little.rawValue | CGImageAlphaInfo.premultipliedLast.rawValue
        let context = try XCTUnwrap(CGContext(data: nil, width: 1603, height: 1207, bitsPerComponent: 16,
            bytesPerRow: 1603 * 8, space: space, bitmapInfo: bitmap))
        context.setFillColor(try XCTUnwrap(CGColor(colorSpace: space, components: [1.5, 0.2, 0.1, 0.7])))
        context.fill(CGRect(x: 0, y: 0, width: 1603, height: 1207))
        let editor = BaseEditPhotoController(); editor.loadViewIfNeeded()
        editor.view.frame = CGRect(x: 0, y: 0, width: 375, height: 667)
        editor.sourceImage = UIImage(cgImage: try XCTUnwrap(context.makeImage()))
        editor.view.layoutIfNeeded()
        var data = editor.adjustmentData
        var bubble = BubbleModel.bubbles[4]; bubble.content = "Extended color"
        bubble.center = CGPoint(x: editor.preview.imageRect.width / 2, y: editor.preview.imageRect.height / 2)
        data.bubbles = [bubble]; editor.restoreFromData(data)
        let reference = try XCTUnwrap(editor.outputImage)
        let expected = extendedRGBA(reference)
        let finished = expectation(description: "Extended source legacy output contract")
        editor.exportPhoto { result in
            switch result {
            case .failure(let error): XCTFail("Extended source export failed: \(error)")
            case .success(let output):
                XCTAssertEqual(output.image.cgImage?.bitsPerComponent, reference.cgImage?.bitsPerComponent)
                XCTAssertEqual(output.image.cgImage?.bitsPerPixel, reference.cgImage?.bitsPerPixel)
                XCTAssertEqual(output.image.cgImage?.alphaInfo, reference.cgImage?.alphaInfo)
                XCTAssertEqual(String(describing: output.image.cgImage?.colorSpace?.name), String(describing: reference.cgImage?.colorSpace?.name))
                let actual = self.extendedRGBA(output.image)
                XCTAssertEqual(actual.count, expected.count)
                XCTAssertTrue(actual == expected, "Exact extended-linear float pixels must retain legacy range/alpha/color semantics")
                print("EXTENDED_SOURCE_EQUIVALENCE width=1603 height=1207 output_bpc=\(output.image.cgImage?.bitsPerComponent ?? 0) output_bpp=\(output.image.cgImage?.bitsPerPixel ?? 0) profile=\(String(describing: output.image.cgImage?.colorSpace?.name))")
            }
            finished.fulfill()
        }
        wait(for: [finished], timeout: 30)
    }

    private func pngSummary(_ data: Data, image: UIImage) -> String {
        var chunks: [[String: Any]] = []
        var offset = 8
        while offset + 12 <= data.count {
            let length = data[offset..<(offset + 4)].reduce(0) { ($0 << 8) | Int($1) }
            guard length <= data.count - offset - 12 else { break }
            let type = String(decoding: data[(offset + 4)..<(offset + 8)], as: UTF8.self)
            let payload = data[(offset + 8)..<(offset + 8 + length)]
            chunks.append(["type": type, "bytes": length, "sha256": SHA256.hash(data: payload).map { String(format: "%02x", $0) }.joined()])
            offset += length + 12
        }
        let cg = image.cgImage!
        let fields: [String: Any] = ["chunks": chunks, "width": cg.width, "height": cg.height,
            "bpc": cg.bitsPerComponent, "bpp": cg.bitsPerPixel, "bitmap_info": cg.bitmapInfo.rawValue,
            "row_bytes": cg.bytesPerRow, "profile": String(describing: cg.colorSpace?.name),
            "alpha_info": cg.alphaInfo.rawValue, "rendering_intent": cg.renderingIntent.rawValue,
            "scale": image.scale, "orientation": image.imageOrientation.rawValue]
        return String(decoding: try! JSONSerialization.data(withJSONObject: fields, options: [.sortedKeys]), as: UTF8.self)
    }

    private func extendedRGBA(_ image: UIImage) -> Data {
        let cg = image.cgImage!
        var bytes = Data(count: cg.width * cg.height * 16)
        bytes.withUnsafeMutableBytes { buffer in
            let info = CGBitmapInfo.floatComponents.rawValue | CGBitmapInfo.byteOrder32Little.rawValue | CGImageAlphaInfo.premultipliedLast.rawValue
            let context = CGContext(data: buffer.baseAddress, width: cg.width, height: cg.height, bitsPerComponent: 32,
                bytesPerRow: cg.width * 16, space: CGColorSpace(name: CGColorSpace.extendedLinearDisplayP3)!, bitmapInfo: info)!
            context.draw(cg, in: CGRect(x: 0, y: 0, width: cg.width, height: cg.height))
        }
        return bytes
    }

    private func rgba(_ image: UIImage) -> [UInt8] {
        let cg = image.cgImage!
        var result = [UInt8](repeating: 0, count: cg.width * cg.height * 4)
        let context = CGContext(data: &result, width: cg.width, height: cg.height, bitsPerComponent: 8,
            bytesPerRow: cg.width * 4, space: CGColorSpace(name: CGColorSpace.sRGB)!,
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue)!
        context.draw(cg, in: CGRect(x: 0, y: 0, width: cg.width, height: cg.height))
        return result
    }

    private func pixel(_ image: UIImage, x: Int, y: Int) -> [UInt8] {
        let part = image.cgImage!.cropping(to: CGRect(x: x, y: y, width: 1, height: 1))!
        var bytes = [UInt8](repeating: 0, count: 4)
        let context = CGContext(data: &bytes, width: 1, height: 1, bitsPerComponent: 8, bytesPerRow: 4,
            space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
        context.draw(part, in: CGRect(x: 0, y: 0, width: 1, height: 1))
        return bytes
    }
}
