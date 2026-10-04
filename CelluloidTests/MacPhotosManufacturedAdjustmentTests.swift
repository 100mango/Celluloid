import XCTest
import UIKit
import CryptoKit
@testable import CelluloidKit

/// Consumes actual native-macOS-produced bytes, never a UIKit substitute archive.
/// Fixture delivery is a separately admitted, source/hash-bound test-only step.
@MainActor final class MacPhotosManufacturedAdjustmentTests: XCTestCase {
    private struct Fixture: Decodable {
        let name: String, identifier: String, version: String, sha256: String, base64: String
        let sourceSHA256: String, sourceBase64: String, renderedSHA256: String, renderedBase64: String
        let components: [Component]?
    }
    private struct Component: Decodable { let name: String, sha256: String, base64: String }
    func testManufacturedMacArchiveThroughOriginalUIKitReaderAndCompositor() throws {
        let url = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("mac-layer-fixture.json")
        guard FileManager.default.fileExists(atPath: url.path) else {
            throw XCTSkip("Requires the exact source-bound MAC_LAYER_ADJUSTMENT_FIXTURE from an admitted Mac run; interoperability and text pixel parity are not yet proved")
        }
        let contents = try Data(contentsOf: url)
        XCTAssertLessThanOrEqual(contents.count, 500_000)
        let fixture = try JSONDecoder().decode(Fixture.self, from: contents)
        XCTAssertEqual(fixture.name, "manufactured-affine")
        XCTAssertEqual(fixture.identifier, "Mango.CelluloidPhotoExtension"); XCTAssertEqual(fixture.version, "1.0")
        func data(_ base64: String, _ hash: String) throws -> Data {
            let data = try XCTUnwrap(Data(base64Encoded: base64))
            XCTAssertEqual(SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined(), hash)
            return data
        }
        let archive = try data(fixture.base64, fixture.sha256)
        let decoded = try AdjustmentData.decode(archive)
        XCTAssertEqual(decoded.filterType, .Fade); XCTAssertEqual(decoded.referenceCanvasSize, CGSize(width: 480, height: 640))
        XCTAssertEqual(decoded.bubbles.count, 1); XCTAssertEqual(decoded.stickers.count, 1)
        let bubble = try XCTUnwrap(decoded.bubbles.first), sticker = try XCTUnwrap(decoded.stickers.first)
        XCTAssertEqual(bubble.content, "Hello, 世界 🎬")
        XCTAssertEqual(bubble.center, CGPoint(x: 240, y: 320)); XCTAssertEqual(bubble.bounds, CGRect(x: 0, y: 0, width: 180, height: 96))
        XCTAssertEqual(bubble.transform, CGAffineTransform(a: 1.5, b: 0.25, c: -0.25, d: 1.5, tx: 10, ty: -4))
        XCTAssertEqual(sticker.center, CGPoint(x: 44, y: -12)); XCTAssertEqual(sticker.bounds, CGRect(x: 2, y: 3, width: 72, height: 80))
        XCTAssertEqual(sticker.transform, CGAffineTransform(a: 0.5, b: 0, c: 0, d: 0.75, tx: 0, ty: 0))
        let reencoded = try AdjustmentData.decode(decoded.encode())
        XCTAssertEqual(reencoded.bubbles[0].transform, bubble.transform)
        XCTAssertEqual(reencoded.stickers[0].bounds, sticker.bounds)
        let source = try XCTUnwrap(UIImage(data: data(fixture.sourceBase64, fixture.sourceSHA256)))
        let native = try XCTUnwrap(UIImage(data: data(fixture.renderedBase64, fixture.renderedSHA256)))
        let editor = BaseEditPhotoController(); editor.loadViewIfNeeded()
        editor.view.frame = CGRect(x: 0, y: 0, width: 480, height: 850)
        editor.sourceImage = source; editor.view.layoutIfNeeded(); editor.restoreFromData(decoded)
        let expected = try XCTUnwrap(editor.outputImage)
        XCTAssertEqual(expected.cgImage?.width, 480); XCTAssertEqual(expected.cgImage?.height, 640)
        XCTAssertEqual(native.cgImage?.width, 480); XCTAssertEqual(native.cgImage?.height, 640)
        let actual = try pixels(native), oracle = try pixels(expected)
        XCTAssertEqual(actual.count, oracle.count)
        let maximum = zip(actual, oracle).map { abs(Int($0) - Int($1)) }.max() ?? 0
        print("MAC_LAYER_UIKIT_COMPOSITOR archiveSHA256=\(fixture.sha256) sourceSHA256=\(fixture.sourceSHA256) nativeSHA256=\(fixture.renderedSHA256) maximumChannelDifference=\(maximum)")
        XCTAssertLessThanOrEqual(maximum, 2, "Original UIKit compositor is independent of the new Mac renderer; geometry/text differences must be fixed, not hidden by archive roundtrips")
        diagnose(name: "full", actual: actual, oracle: oracle, expected: expected)
        let view = BubbleView(bubbleModel: bubble); view.layoutIfNeeded()
        let label = view.bubbleLabel, image = try XCTUnwrap(view.imageView.image)
        print("MAC_LAYER_UIKIT_COMPOSITOR_UIKIT_LAYOUT asset=\(image.cgImage?.width ?? 0)x\(image.cgImage?.height ?? 0) imageScale=\(image.scale) textRect=\(label.frame) font=\(label.font.fontName) fontSize=\(label.font.pointSize) lineHeight=\(label.font.lineHeight) contentsScale=\(label.layer.contentsScale) referenceCanvas=\(editor.adjustmentData.referenceCanvasSize.debugDescription)")
        if let components = fixture.components {
            XCTAssertEqual(components.count, 4)
            XCTAssertEqual(Set(components.map(\.name)), ["filtered-base", "bubble-artwork", "sticker-artwork", "all-artwork"])
            for component in components {
                var adjustment = decoded
                adjustment.bubbles = adjustment.bubbles.map { var model = $0; model.content = ""; return model }
                if component.name == "filtered-base" || component.name == "sticker-artwork" { adjustment.bubbles = [] }
                if component.name == "filtered-base" || component.name == "bubble-artwork" { adjustment.stickers = [] }
                let componentNative = try XCTUnwrap(UIImage(data: data(component.base64, component.sha256)))
                // Always call the original UIKit controller/compositor. Do not
                // replace it with the Mac renderer or reconstructed CG paths.
                let controller = BaseEditPhotoController(); controller.loadViewIfNeeded()
                controller.view.frame = CGRect(x: 0, y: 0, width: 480, height: 850)
                controller.sourceImage = source; controller.view.layoutIfNeeded(); controller.restoreFromData(adjustment)
                let componentExpected = try XCTUnwrap(controller.outputImage)
                XCTAssertEqual(componentNative.cgImage?.width, 480); XCTAssertEqual(componentNative.cgImage?.height, 640)
                let a = try pixels(componentNative), b = try pixels(componentExpected)
                XCTAssertEqual(a.count, b.count)
                let difference = zip(a, b).map { abs(Int($0) - Int($1)) }.max() ?? 0
                print("MAC_LAYER_UIKIT_COMPOSITOR_COMPONENT name=\(component.name) nativeSHA256=\(component.sha256) maximumChannelDifference=\(difference)")
                XCTAssertLessThanOrEqual(difference, 2, "Independent UIKit component: \(component.name)")
                diagnose(name: component.name, actual: a, oracle: b, expected: componentExpected)
                if component.name == "all-artwork", a.count == actual.count, b.count == oracle.count {
                    let textDifference = actual.indices.map { abs((Int(actual[$0]) - Int(a[$0])) - (Int(oracle[$0]) - Int(b[$0]))) }.max() ?? 0
                    print("MAC_LAYER_UIKIT_COMPOSITOR_TEXT_CONTRIBUTION maximumChannelDifference=\(textDifference)")
                }
            }
        } else {
            print("MAC_LAYER_UIKIT_COMPOSITOR_COMPONENTS absent-in-historical-fixture; full strict oracle still enforced")
        }
    }
    private func diagnose(name: String, actual: [UInt8], oracle: [UInt8], expected: UIImage) {
        guard actual.count == oracle.count, let cg = expected.cgImage else { return }
        var count = 0, minX = cg.width, minY = cg.height, maxX = -1, maxY = -1
        for offset in stride(from: 0, to: actual.count, by: 4) {
            if (0..<4).contains(where: { abs(Int(actual[offset + $0]) - Int(oracle[offset + $0])) > 2 }) {
                count += 1
                let x = (offset / 4) % cg.width, y = (offset / 4) / cg.width
                minX = min(minX, x); minY = min(minY, y); maxX = max(maxX, x); maxY = max(maxY, y)
            }
        }
        let png = expected.pngData() ?? Data()
        let hash = SHA256.hash(data: png).map { String(format: "%02x", $0) }.joined()
        print("MAC_LAYER_UIKIT_COMPOSITOR_DIAGNOSTIC name=\(name) oraclePNG_SHA256=\(hash) differingPixels=\(count) bitmapBounds=\(minX),\(minY),\(maxX),\(maxY)")
        if count > 0 {
            // Native PNGs are already in the hash-bound fixture. Retain at most
            // five small independent UIKit images, within the existing 8-image
            // attachment selector and unchanged aggregate evidence byte budget.
            let attachment = XCTAttachment(data: png, uniformTypeIdentifier: "public.png")
            attachment.name = "native-mac-layer-\(name)-uikit"; attachment.lifetime = .keepAlways
            add(attachment)
        }
    }
    private func pixels(_ image: UIImage) throws -> [UInt8] {
        let cg = try XCTUnwrap(image.cgImage), space = try XCTUnwrap(CGColorSpace(name: CGColorSpace.sRGB))
        let bitmap = try XCTUnwrap(CGContext(data: nil, width: cg.width, height: cg.height, bitsPerComponent: 8,
            bytesPerRow: cg.width * 4, space: space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
        bitmap.draw(cg, in: CGRect(x: 0, y: 0, width: cg.width, height: cg.height))
        return Array(UnsafeBufferPointer(start: bitmap.data!.assumingMemoryBound(to: UInt8.self), count: bitmap.bytesPerRow * bitmap.height))
    }
}
