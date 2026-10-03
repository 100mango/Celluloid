import XCTest
import UIKit
import CoreImage
import CryptoKit
@testable import CelluloidKit

final class AdjustmentDataTests: XCTestCase {
    // Deliberately independent of toJSON(): this is the dictionary and NSValue
    // shape emitted by JSONCodable 3 and the original version 1.0 app.
    private var legacyBubble: [String: Any] {
        return [
            "asset": "say1",
            "content": "Hello, 世界 🎬",
            "transform": NSValue(cgAffineTransform: CGAffineTransform(a: 1.5, b: 0.25, c: -0.25, d: 1.5, tx: 10, ty: -4)),
            "bounds": NSValue(cgRect: CGRect(x: 0, y: 0, width: 180, height: 96)),
            "center": NSValue(cgPoint: CGPoint(x: 240, y: 320))
        ]
    }

    private var legacySticker: [String: Any] {
        return [
            "imageName": "32",
            "transform": NSValue(cgAffineTransform: CGAffineTransform(scaleX: 0.5, y: 0.75)),
            "bounds": NSValue(cgRect: CGRect(x: 2, y: 3, width: 72, height: 80)),
            "center": NSValue(cgPoint: CGPoint(x: 44, y: -12))
        ]
    }

    private var legacyObject: [String: Any] {
        return ["filterType": "Chrome", "bubbles": [legacyBubble], "stickers": [legacySticker]]
    }

    private func legacyArchive(_ object: Any) throws -> Data {
        // Equivalent to the old archivedData(withRootObject:) API: the archive
        // was not required to use secure coding, but its contents support it.
        return try NSKeyedArchiver.archivedData(withRootObject: object, requiringSecureCoding: false)
    }

    func testLegacyArchiveRoundTripsWithoutChangingItsDictionary() throws {
        let decoded = try AdjustmentData.decode(legacyArchive(legacyObject))
        XCTAssertEqual(decoded.filterType, .Chrome)
        XCTAssertEqual(decoded.bubbles.count, 1)
        XCTAssertEqual(decoded.stickers.count, 1)
        XCTAssertEqual(decoded.bubbles[0].content, "Hello, 世界 🎬")
        XCTAssertEqual(decoded.bubbles[0].center, CGPoint(x: 240, y: 320))
        XCTAssertEqual(decoded.bubbles[0].bounds, CGRect(x: 0, y: 0, width: 180, height: 96))
        XCTAssertEqual(decoded.bubbles[0].transform, CGAffineTransform(a: 1.5, b: 0.25, c: -0.25, d: 1.5, tx: 10, ty: -4))
        XCTAssertEqual(decoded.stickers[0].center, CGPoint(x: 44, y: -12))
        XCTAssertEqual(decoded.stickers[0].bounds, CGRect(x: 2, y: 3, width: 72, height: 80))
        XCTAssertEqual(decoded.stickers[0].transform, CGAffineTransform(scaleX: 0.5, y: 0.75))
        let restored = try AdjustmentData.decode(decoded.encode())
        let dictionary = try XCTUnwrap(restored.toJSON() as? NSDictionary)
        XCTAssertTrue(dictionary.isEqual(to: legacyObject))
        XCTAssertEqual(AdjustmentData.formatIdentifier, "Mango.CelluloidPhotoExtension")
        XCTAssertEqual(AdjustmentData.formatVersion, "1.0")
        XCTAssertTrue(AdjustmentData.supportIdentifier("Mango.CelluloidPhotoExtension", version: "1.0"))
        XCTAssertFalse(AdjustmentData.supportIdentifier("Mango.CelluloidPhotoExtension", version: "2.0"))
        XCTAssertFalse(AdjustmentData.supportIdentifier("Other", version: "1.0"))
    }

    func testExportSyntheticUIKitCompatibilityFixtures() throws {
        // Contemporary UIKit-produced reproductions of the shipping dictionary,
        // not recovered user archives. Bounded output supports independent AppKit
        // compatibility tests without guessing NSValue's serialized representation.
        for name in ["legacy-points", "reference-canvas"] {
            var object = legacyObject
            if name == "reference-canvas" { object["referenceCanvasSize"] = NSValue(cgSize: CGSize(width: 480, height: 640)) }
            let input = try legacyArchive(object)
            let decoded = try AdjustmentData.decode(input)
            let bytes: Data
            if name == "legacy-points" { bytes = input }
            else { bytes = try decoded.encode() }
            let verified = try AdjustmentData.decode(bytes)
            XCTAssertTrue(try XCTUnwrap(verified.toJSON() as? NSDictionary).isEqual(to: object))
            XCTAssertEqual(verified.referenceCanvasSize, name == "legacy-points" ? nil : CGSize(width: 480, height: 640))
            XCTAssertLessThanOrEqual(bytes.count, 8_000)
            let digest = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
            let metadata: [String: Any] = ["name": name, "sha256": digest, "bytes": bytes.count,
                "runtime": UIDevice.current.systemVersion, "formatIdentifier": AdjustmentData.formatIdentifier,
                "formatVersion": AdjustmentData.formatVersion, "filterType": "Chrome",
                "bubble": ["asset": "say1", "content": "Hello, 世界 🎬", "center": [240, 320], "bounds": [0, 0, 180, 96], "transform": [1.5, 0.25, -0.25, 1.5, 10, -4]],
                "sticker": ["imageName": "32", "center": [44, -12], "bounds": [2, 3, 72, 80], "transform": [0.5, 0, 0, 0.75, 0, 0]],
                "referenceCanvasSize": name == "legacy-points" ? [] : [480, 640]]
            print("UIKIT_ARCHIVE_FIXTURE_META " + String(decoding: try JSONSerialization.data(withJSONObject: metadata, options: [.sortedKeys]), as: UTF8.self))
            print("UIKIT_ARCHIVE_FIXTURE_BEGIN:" + name)
            print(bytes.base64EncodedString())
            print("UIKIT_ARCHIVE_FIXTURE_END:" + name)
        }
    }

    func testLegacyArchivesMayOmitEmptyArrays() throws {
        let data = try legacyArchive(["filterType": "Original"])
        let restored = try AdjustmentData.decode(data)
        XCTAssertTrue(restored.bubbles.isEmpty)
        XCTAssertTrue(restored.stickers.isEmpty)
        XCTAssertEqual(restored.filterType, .Original)
        let dictionary = try XCTUnwrap(restored.toJSON() as? [String: Any])
        XCTAssertNil(dictionary["bubbles"])
        XCTAssertNil(dictionary["stickers"])
        let empty = try AdjustmentData.decode(AdjustmentData().encode())
        XCTAssertEqual(empty.filterType, .Original)
    }

    func testExplicitEmptyArraysAreAlsoAccepted() throws {
        let restored = try AdjustmentData(object: ["filterType": "Original", "bubbles": [], "stickers": []])
        XCTAssertTrue(restored.bubbles.isEmpty)
        XCTAssertTrue(restored.stickers.isEmpty)
    }

    func testMalformedArchivesAndUnexpectedClassesAreRejected() throws {
        XCTAssertThrowsError(try AdjustmentData.decode(Data()))
        XCTAssertThrowsError(try AdjustmentData.decode(Data("not a keyed archive".utf8)))
        XCTAssertThrowsError(try AdjustmentData.decode(legacyArchive(["wrong", "root"])))
        XCTAssertThrowsError(try AdjustmentData.decode(legacyArchive(["filterType": Date()])))
        let valid = try legacyArchive(legacyObject)
        XCTAssertThrowsError(try AdjustmentData.decode(Data(valid.prefix(valid.count / 2))))
    }

    func testUnknownFilterAndInvalidCollectionsAreRejected() throws {
        for object: [String: Any] in [
            [:],
            ["filterType": "FutureFilter"],
            ["filterType": 1],
            ["filterType": "Original", "bubbles": "invalid"],
            ["filterType": "Original", "bubbles": [1]],
            ["filterType": "Original", "stickers": NSNull()]
        ] {
            XCTAssertThrowsError(try AdjustmentData(object: object))
        }
    }

    func testUnknownAssetsAreRejectedBeforeTheyReachImageRendering() throws {
        for name in ["unknown", "bubbleButton", "image_sticker_say"] {
            var bubble = legacyBubble
            bubble["asset"] = name
            XCTAssertThrowsError(try BubbleModel(object: bubble))
        }
        for name in ["unknown", "31", "55", "032", "32.png"] {
            var sticker = legacySticker
            sticker["imageName"] = name
            XCTAssertThrowsError(try StickerModel(object: sticker))
        }
    }

    func testMissingAndMistypedGeometryAreRejected() throws {
        for key in ["transform", "bounds", "center", "content", "asset"] {
            var bubble = legacyBubble
            bubble.removeValue(forKey: key)
            XCTAssertThrowsError(try BubbleModel(object: bubble))
        }
        let invalidGeometry: [String: Any] = [
            "transform": NSNumber(value: 1),
            "bounds": NSValue(cgPoint: .zero),
            "center": NSValue(range: NSRange(location: 0, length: 1))
        ]
        for (key, value) in invalidGeometry {
            var bubble = legacyBubble
            bubble[key] = value
            XCTAssertThrowsError(try BubbleModel(object: bubble))
        }
    }

    func testNonfiniteAndNegativeGeometryAreRejected() throws {
        let invalidGeometry: [(String, NSValue)] = [
            ("transform", NSValue(cgAffineTransform: CGAffineTransform(a: .nan, b: 0, c: 0, d: 1, tx: 0, ty: 0))),
            ("bounds", NSValue(cgRect: CGRect(x: 0, y: 0, width: -1, height: 100))),
            ("bounds", NSValue(cgRect: CGRect(x: 0, y: 0, width: CGFloat.infinity, height: 100))),
            ("center", NSValue(cgPoint: CGPoint(x: CGFloat.infinity, y: 0)))
        ]
        for (key, value) in invalidGeometry {
            var bubble = legacyBubble
            bubble[key] = value
            XCTAssertThrowsError(try BubbleModel(object: bubble))
        }
        var state = AdjustmentData()
        var sticker = try StickerModel(object: legacySticker)
        sticker.center.x = .nan
        state.stickers = [sticker]
        XCTAssertThrowsError(try state.encode())
    }

    func testEveryShippingAssetAndFilterCanRoundTrip() throws {
        let filters: [FilterType] = [.Original, .Sepia, .Chrome, .Fade, .Invert, .Posterize, .Sketch, .Comic, .Crystal, .PixellateFace]
        for filter in filters {
            var state = AdjustmentData()
            state.filterType = filter
            state.bubbles = BubbleModel.bubbles
            state.stickers = StickerModel.stickers
            let restored = try AdjustmentData.decode(state.encode())
            XCTAssertEqual(restored.filterType, filter)
            XCTAssertEqual(restored.bubbles.count, 10)
            XCTAssertEqual(restored.stickers.count, 23)
        }
    }
}

final class FilterTests: XCTestCase {
    private let context = CIContext(options: [.workingColorSpace: NSNull(), .outputColorSpace: NSNull()])
    private let extent = CGRect(x: 0, y: 0, width: 16, height: 12)

    private var input: CIImage {
        return CIImage(color: CIColor(red: 0.25, green: 0.5, blue: 0.75)).cropped(to: extent)
    }

    private func pixels(_ image: CIImage) -> [UInt8] {
        let rowBytes = Int(extent.width) * 4
        var bytes = [UInt8](repeating: 0, count: rowBytes * Int(extent.height))
        bytes.withUnsafeMutableBytes { buffer in
            context.render(image, toBitmap: buffer.baseAddress!, rowBytes: rowBytes,
                           bounds: extent, format: .RGBA8, colorSpace: nil)
        }
        return bytes
    }

    func testOriginalReturnsTheSameImageAndPixels() {
        let original = input
        let result = Filters.filter(.Original)(original)
        XCTAssertTrue(result === original)
        XCTAssertEqual(pixels(result), pixels(original))
    }

    func testInvertActuallyInvertsPixels() {
        let result = pixels(Filters.filter(.Invert)(input))
        XCTAssertEqual(Double(result[0]), 191, accuracy: 1)
        XCTAssertEqual(Double(result[1]), 128, accuracy: 1)
        XCTAssertEqual(Double(result[2]), 64, accuracy: 1)
        XCTAssertEqual(result[3], 255)
    }

    func testPresetsMatchTheirShippingCoreImageFilters() throws {
        let names: [(FilterType, String)] = [
            (.Sepia, "CISepiaTone"), (.Chrome, "CIPhotoEffectChrome"),
            (.Fade, "CIPhotoEffectInstant"), (.Invert, "CIColorInvert"),
            (.Posterize, "CIColorPosterize"), (.Sketch, "CILineOverlay"),
            (.Comic, "CIComicEffect"), (.Crystal, "CICrystallize")
        ]
        for (type, name) in names {
            let expected = try XCTUnwrap(CIFilter(name: name, parameters: [kCIInputImageKey: input])?.outputImage)
            XCTAssertEqual(pixels(Filters.filter(type)(input)), pixels(expected), name)
        }
    }

    func testFacePixelationWithoutFacesIsANoOp() {
        let original = input
        let result = Filters.filter(.PixellateFace)(original)
        XCTAssertTrue(result === original)
    }

    func testInvalidBlurRadiusIsANoOp() {
        let original = input
        XCTAssertTrue(Filters.blur(.nan)(original) === original)
        XCTAssertTrue(Filters.blur(-1)(original) === original)
    }

    func testUIImageFilteringPreservesScaleAndDisplayOrientation() throws {
        let cgImage = try XCTUnwrap(context.createCGImage(input, from: extent))
        let image = UIImage(cgImage: cgImage, scale: 2, orientation: .right)
        let result = image.filteredImage(Filters.filter(.Original))
        XCTAssertEqual(result.scale, 2)
        XCTAssertEqual(result.imageOrientation, .right)
        XCTAssertEqual(result.size, image.size)
    }

    func testExifOrientationIsAppliedExactlyOnce() throws {
        let cgImage = try XCTUnwrap(context.createCGImage(input, from: extent))
        let image = UIImage(cgImage: cgImage, scale: 2, orientation: .right)
        let result = image.filteredImage(6, filter: Filters.filter(.Original))
        XCTAssertEqual(result.scale, 2)
        XCTAssertEqual(result.imageOrientation, .up)
        XCTAssertEqual(result.cgImage?.width, cgImage.height)
        XCTAssertEqual(result.cgImage?.height, cgImage.width)
    }

    func testImageWithoutBackingPixelsDoesNotCrash() {
        let image = UIImage()
        XCTAssertTrue(image.filteredImage(Filters.filter(.Sepia)) === image)
        XCTAssertTrue(image.filteredImage(6, filter: Filters.filter(.Sepia)) === image)
    }
}
