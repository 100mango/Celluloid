import XCTest
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers
import CelluloidDomain
@testable import CelluloidRendering

final class ImageFormatTests: XCTestCase {
    func testPNGOrientationAndColor() throws { try verify(.png) }
    func testJPEGOrientationAndColor() throws { try verify(.jpeg) }
    func testHEICOrientationAndColorWhenEncoderExists() throws { try verify(.heic) }
    func testHEIFOrientationAndColorWhenEncoderExists() throws { try verify(.heif) }

    private func verify(_ type: UTType) throws {
        let encoders = CGImageDestinationCopyTypeIdentifiers() as! [String]
        guard encoders.contains(type.identifier) else {
            print("IMAGE_FORMAT_UNVERIFIED encoder_unavailable=\(type.identifier)")
            throw XCTSkip("Runner cannot encode \(type.identifier); this is an explicit coverage gap")
        }
        let context = try RasterCodec.bitmap(width: 96, height: 64)
        context.setFillColor(try XCTUnwrap(CGColor(colorSpace: RasterCodec.colorSpace, components: [0.1, 0.65, 0.25, 1])))
        context.fill(CGRect(x: 0, y: 0, width: 96, height: 64))
        context.setFillColor(try XCTUnwrap(CGColor(colorSpace: RasterCodec.colorSpace, components: [0.8, 0.1, 0.6, 1])))
        context.fill(CGRect(x: 0, y: 0, width: 48, height: 32))
        let raw = try XCTUnwrap(context.makeImage())
        for orientation in [1, 3, 6, 8] {
            let encoded = NSMutableData()
            let destination = try XCTUnwrap(CGImageDestinationCreateWithData(encoded, type.identifier as CFString, 1, nil))
            CGImageDestinationAddImage(destination, raw, [kCGImagePropertyOrientation: orientation,
                                                         kCGImageDestinationLossyCompressionQuality: 1] as CFDictionary)
            guard CGImageDestinationFinalize(destination) else {
                XCTFail("Advertised \(type.identifier) encoder failed to encode synthetic SDR image")
                return
            }
            let sourceData = encoded as Data
            let source = try RasterCodec.metadata(sourceData)
            var recipe = EditRecipe(); recipe.sources = [source]
            recipe.canvasWidth = source.pixelWidth; recipe.canvasHeight = source.pixelHeight
            let result = try RecipeRenderer().render(recipe, sources: [source.id: sourceData])
            let decoded = try XCTUnwrap(CGImageSourceCreateWithData(sourceData as CFData, nil))
            let oracle = try XCTUnwrap(CGImageSourceCreateThumbnailAtIndex(decoded, 0, [
                kCGImageSourceCreateThumbnailFromImageAlways: true,
                kCGImageSourceCreateThumbnailWithTransform: true,
                kCGImageSourceThumbnailMaxPixelSize: 128
            ] as CFDictionary))
            XCTAssertEqual(result.width, oracle.width); XCTAssertEqual(result.height, oracle.height)
            let a = try samples(result), b = try samples(oracle)
            for index in a.indices { XCTAssertEqual(Double(a[index]), Double(b[index]), accuracy: 2, "\(type.identifier) EXIF\(orientation)") }
            XCTAssertEqual(result.colorSpace?.name, CGColorSpace.sRGB)
            print("IMAGE_FORMAT_VERIFIED type=\(type.identifier) exif=\(orientation) pixels=\(result.width)x\(result.height) output=sRGB-SDR")
        }
    }
    private func samples(_ image: CGImage) throws -> [UInt8] {
        let context = try RasterCodec.bitmap(width: image.width, height: image.height)
        context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
        let bytes = try XCTUnwrap(context.data).assumingMemoryBound(to: UInt8.self)
        return [(image.width / 4, image.height / 4), (image.width * 3 / 4, image.height / 4),
                (image.width / 4, image.height * 3 / 4), (image.width * 3 / 4, image.height * 3 / 4)].flatMap { x, y in
            Array(UnsafeBufferPointer(start: bytes + y * context.bytesPerRow + x * 4, count: 4))
        }
    }
    func testUnreadableAndOversizedInputsFailBeforeRender() throws {
        XCTAssertThrowsError(try RasterCodec.metadata(Data([0, 1, 2, 3])))
        let data = Data(repeating: 0, count: RasterCodec.maxSourceBytes + 1)
        XCTAssertThrowsError(try RasterCodec.metadata(data)) { XCTAssertEqual($0 as? RecipeError, .resourceLimit) }
        let tiny = try RasterCodec.bitmap(width: 1, height: 1)
        let png = try RasterCodec.encode(XCTUnwrap(tiny.makeImage()), as: .png)
        XCTAssertThrowsError(try RasterCodec.metadata(png, maximumBytes: png.count - 1))
        XCTAssertThrowsError(try RasterCodec.bitmap(width: 16_384, height: 16_384))
        XCTAssertThrowsError(try RasterCodec.bitmap(width: Int.max, height: Int.max))
    }
}
