import XCTest
import ImageIO
import UniformTypeIdentifiers
import CelluloidDomain
@testable import CelluloidRendering

final class RasterSourceLoaderTests: XCTestCase {
    private func fixture(orientation: Int = 1, colorSpace: CGColorSpace = RasterCodec.colorSpace) throws -> Data {
        let context = try XCTUnwrap(CGContext(data: nil, width: 600, height: 400, bitsPerComponent: 8,
                                             bytesPerRow: 600 * 4, space: colorSpace,
                                             bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
        context.setFillColor(CGColor(gray: 0.5, alpha: 1))
        context.fill(CGRect(x: 0, y: 0, width: 600, height: 400))
        let data = NSMutableData()
        let destination = try XCTUnwrap(CGImageDestinationCreateWithData(data, UTType.tiff.identifier as CFString, 1, nil))
        CGImageDestinationAddImage(destination, try XCTUnwrap(context.makeImage()), [kCGImagePropertyOrientation: orientation] as CFDictionary)
        XCTAssertTrue(CGImageDestinationFinalize(destination))
        return data as Data
    }
    func testThumbnailBoundOriginalIdentityAndEightOrientations() async throws {
        let loader = RasterSourceLoader()
        for orientation in 1...8 {
            let bytes = try fixture(orientation: orientation), identity = UUID()
            let result = try await loader.load(bytes: bytes, name: "Source", id: identity, maximumPreviewDimension: 150)
            XCTAssertEqual(result.originalBytes, bytes)
            XCTAssertEqual(result.source.id, identity)
            XCTAssertEqual(result.source.pixelWidth, orientation >= 5 ? 400 : 600)
            XCTAssertEqual(result.source.pixelHeight, orientation >= 5 ? 600 : 400)
            XCTAssertEqual(result.preview.width, orientation >= 5 ? 100 : 150)
            XCTAssertEqual(result.preview.height, orientation >= 5 ? 150 : 100)
            // Export still consumes originals rather than the downsampled image.
            var recipe = EditRecipe(); recipe.sources = [result.source]
            recipe.canvasWidth = result.source.pixelWidth; recipe.canvasHeight = result.source.pixelHeight
            let export = try await NativeRenderQueue.shared.export(recipe, sources: [identity: result.originalBytes], type: .png)
            let metadata = try RasterCodec.metadata(export)
            XCTAssertEqual(metadata.pixelWidth, result.source.pixelWidth)
            XCTAssertEqual(metadata.pixelHeight, result.source.pixelHeight)
        }
    }
    func testThumbnailRetainsTaggedDisplayP3AndOriginalFileBytes() async throws {
        let p3 = try XCTUnwrap(CGColorSpace(name: CGColorSpace.displayP3))
        let bytes = try fixture(colorSpace: p3)
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".tiff")
        try bytes.write(to: url); defer { try? FileManager.default.removeItem(at: url) }
        let result = try await RasterSourceLoader().load(fileURL: url, name: "P3", maximumPreviewDimension: 150)
        XCTAssertEqual(result.originalBytes, bytes)
        XCTAssertEqual(result.preview.colorSpace?.name as String?, CGColorSpace.displayP3 as String)
    }
    func testRejectsUnboundedPreviewAndInvalidInput() async {
        let loader = RasterSourceLoader()
        do { _ = try await loader.load(bytes: fixture(), name: "Image", maximumPreviewDimension: 8192); XCTFail("Unbounded preview accepted") }
        catch { XCTAssertTrue(error is RecipeError) }
        do { _ = try await loader.load(bytes: Data(), name: "Empty"); XCTFail("Empty bytes accepted") }
        catch { XCTAssertTrue(error is RecipeError) }
    }
}
