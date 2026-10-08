import XCTest
import CoreGraphics
import CoreImage
import ImageIO
import UniformTypeIdentifiers
import CelluloidDomain
@testable import CelluloidRendering

final class PixelFormatTests: XCTestCase {
    private func rgbaOracle(_ image: CGImage) -> [UInt8] {
        let bounds = CGRect(x: 0, y: 0, width: image.width, height: image.height)
        var bytes = [UInt8](repeating: 0, count: image.width * image.height * 4)
        bytes.withUnsafeMutableBytes { buffer in
            CIContext(options: [.workingColorSpace: RasterCodec.colorSpace, .outputColorSpace: RasterCodec.colorSpace])
                .render(CIImage(cgImage: image), toBitmap: buffer.baseAddress!, rowBytes: image.width * 4,
                        bounds: bounds, format: .RGBA8, colorSpace: RasterCodec.colorSpace)
        }
        return bytes
    }
    func testExplicitSRGBFixtureHasCanonicalByteValues() throws {
        let context = try RasterCodec.bitmap(width: 64, height: 48)
        let red = try XCTUnwrap(CGColor(colorSpace: RasterCodec.colorSpace, components: [1, 0, 0, 1]))
        context.setFillColor(red); context.fill(CGRect(x: 0, y: 0, width: 64, height: 48))
        let sourceImage = try XCTUnwrap(context.makeImage())
        XCTAssertEqual(Array(rgbaOracle(sourceImage).prefix(4)), [255, 0, 0, 255])
        let bytes = try RasterCodec.encode(sourceImage, as: .png)
        let source = try RasterCodec.metadata(bytes)
        var recipe = EditRecipe(); recipe.sources = [source]; recipe.canvasWidth = 64; recipe.canvasHeight = 48
        let rendered = try RecipeRenderer().render(recipe, sources: [source.id: bytes])
        let actual = Array(rgbaOracle(rendered).prefix(4))
        print("PIXEL_ORACLE explicit_srgb_red source=\(Array(rgbaOracle(sourceImage).prefix(4))) render=\(actual)")
        XCTAssertEqual(actual, [255, 0, 0, 255])
    }
    func testFreshBitmapContainsNoUninitializedPixels() throws {
        let context = try RasterCodec.bitmap(width: 97, height: 101)
        let bytes = Array(UnsafeBufferPointer(start: try XCTUnwrap(context.data).assumingMemoryBound(to: UInt8.self), count: context.bytesPerRow * context.height))
        XCTAssertTrue(bytes.allSatisfy { $0 == 0 })
    }
    func testExplicitRGBA8OracleForSourceRenderedCanvasAndPNGReadback() throws {
        let colors = [CGColor(colorSpace: RasterCodec.colorSpace, components: [1, 0, 0, 1])!, CGColor(colorSpace: RasterCodec.colorSpace, components: [0, 1, 0, 1])!,
                      CGColor(colorSpace: RasterCodec.colorSpace, components: [0, 0, 1, 1])!, CGColor(colorSpace: RasterCodec.colorSpace, components: [1, 1, 0, 1])!]
        let expected: [[UInt8]] = [[255,0,0,255],[0,255,0,255],[0,0,255,255],[255,255,0,255]]
        var recipe = EditRecipe(); var originals: [UUID: Data] = [:]
        for (index, color) in colors.enumerated() {
            let context = try RasterCodec.bitmap(width: 64, height: 48)
            context.setFillColor(color); context.fill(CGRect(x: 0, y: 0, width: 64, height: 48))
            let sourceImage = try XCTUnwrap(context.makeImage())
            let raw = Array(UnsafeBufferPointer(start: try XCTUnwrap(context.data).assumingMemoryBound(to: UInt8.self), count: 4))
            let normalized = Array(rgbaOracle(sourceImage).prefix(4))
            let png = try RasterCodec.encode(sourceImage, as: .png)
            let decodedSource = try XCTUnwrap(CGImageSourceCreateWithData(png as CFData, nil))
            let decoded = try XCTUnwrap(CGImageSourceCreateImageAtIndex(decodedSource, 0, nil))
            print("PIXEL_ORACLE source=\(index) raw=\(raw) rgba8=\(normalized) readback=\(Array(rgbaOracle(decoded).prefix(4))) inputColorSpace=\(String(describing: color.colorSpace?.name)) bitmapInfo=\(context.bitmapInfo.rawValue) alphaInfo=\(context.alphaInfo.rawValue) bytesPerRow=\(context.bytesPerRow)")
            XCTAssertEqual(normalized, expected[index])
            XCTAssertEqual(Array(rgbaOracle(decoded).prefix(4)), expected[index])
            let source = try RasterCodec.metadata(png)
            recipe.sources.append(source); originals[source.id] = png
        }
        recipe.collageTemplate = try NativeResources.templates(count: 4).first!.assetName
        let output = try RecipeRenderer().render(recipe, sources: originals)
        let png = try RasterCodec.encode(output, as: .png)
        let decodedSource = try XCTUnwrap(CGImageSourceCreateWithData(png as CFData, nil))
        let readback = try XCTUnwrap(CGImageSourceCreateImageAtIndex(decodedSource, 0, nil))
        for (name, image) in [("render",output),("export",readback)] {
            let bytes = rgbaOracle(image)
            var counts = [Int](repeating: 0, count: colors.count)
            for offset in stride(from: 0, to: bytes.count, by: 4) {
                for index in colors.indices where Array(bytes[offset..<offset+4]) == expected[index] { counts[index] += 1 }
            }
            print("PIXEL_ORACLE \(name) explicit_rgba8_source_counts=\(counts)")
            for count in counts { XCTAssertGreaterThan(count, 1000) }
        }
    }
}
