import XCTest
import UIKit
@testable import CelluloidKit

@MainActor
final class ExportAndInteractionTests: XCTestCase {
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
        let expected = try XCTUnwrap(editor.outputImage?.pngData())
        XCTAssertNotEqual(blank, expected)
        editor.overlayView.subviews.compactMap { $0 as? AttachView }.forEach { $0.hideButtonEnable = false }
        let completed = expectation(description: "Decorated snapshot without controls")
        var count = 0
        editor.exportPhoto { result in
            count += 1
            if case .success(let output) = result { XCTAssertEqual(output.image.pngData(), expected) }
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

    private func pixel(_ image: UIImage, x: Int, y: Int) -> [UInt8] {
        let part = image.cgImage!.cropping(to: CGRect(x: x, y: y, width: 1, height: 1))!
        var bytes = [UInt8](repeating: 0, count: 4)
        let context = CGContext(data: &bytes, width: 1, height: 1, bitsPerComponent: 8, bytesPerRow: 4,
            space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
        context.draw(part, in: CGRect(x: 0, y: 0, width: 1, height: 1))
        return bytes
    }
}
