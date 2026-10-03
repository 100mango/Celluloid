import XCTest
import CoreGraphics
import ImageIO
import CelluloidDomain
@testable import CelluloidRendering

final class TaggedColorSpaceTests: XCTestCase {
    func testGenericAndP3TaggedSourcesMatchIndependentCoreGraphicsSRGBConversion() throws {
        for name in [CGColorSpace.genericRGB, CGColorSpace.displayP3] {
            let sourceSpace = try XCTUnwrap(CGColorSpace(name: name))
            let sourceContext = try XCTUnwrap(CGContext(data: nil, width: 24, height: 16, bitsPerComponent: 8,
                                                       bytesPerRow: 24 * 4, space: sourceSpace,
                                                       bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
            sourceContext.setFillColor(try XCTUnwrap(CGColor(colorSpace: sourceSpace, components: [0.9, 0.25, 0.6, 1])))
            sourceContext.fill(CGRect(x: 0, y: 0, width: 24, height: 16))
            let sourceImage = try XCTUnwrap(sourceContext.makeImage())
            let encoded = try RasterCodec.encode(sourceImage, as: .png)
            let imageSource = try XCTUnwrap(CGImageSourceCreateWithData(encoded as CFData, nil))
            let decoded = try XCTUnwrap(CGImageSourceCreateImageAtIndex(imageSource, 0, nil))
            let oracle = try RasterCodec.bitmap(width: 24, height: 16)
            oracle.draw(decoded, in: CGRect(x: 0, y: 0, width: 24, height: 16))
            let expected = Array(UnsafeBufferPointer(start: try XCTUnwrap(oracle.data).assumingMemoryBound(to: UInt8.self), count: 4))
            let source = try RasterCodec.metadata(encoded)
            var recipe = EditRecipe(); recipe.sources = [source]; recipe.canvasWidth = 24; recipe.canvasHeight = 16
            let rendered = try RecipeRenderer().render(recipe, sources: [source.id: encoded])
            let readback = try RasterCodec.bitmap(width: 24, height: 16)
            readback.draw(rendered, in: CGRect(x: 0, y: 0, width: 24, height: 16))
            let actual = Array(UnsafeBufferPointer(start: try XCTUnwrap(readback.data).assumingMemoryBound(to: UInt8.self), count: 4))
            print("TAGGED_COLOR_ORACLE source=\(name) cg_srgb=\(expected) rendered_srgb=\(actual)")
            for channel in 0..<4 { XCTAssertEqual(Double(actual[channel]), Double(expected[channel]), accuracy: 2) }
        }
    }
}
