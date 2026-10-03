import XCTest
import CoreGraphics
import CoreImage
import ImageIO
import UniformTypeIdentifiers
import CelluloidDomain
@testable import CelluloidRendering

final class OrientationAndCropTests: XCTestCase {
    private func stripedImage(width: Int = 120, height: Int = 80) throws -> CGImage {
        let context = try RasterCodec.bitmap(width: width, height: height)
        for (index, color) in [CGColor(red: 1, green: 0, blue: 0, alpha: 1),
                               CGColor(red: 0, green: 1, blue: 0, alpha: 1),
                               CGColor(red: 0, green: 0, blue: 1, alpha: 1)].enumerated() {
            context.setFillColor(color)
            context.fill(CGRect(x: index * width / 3, y: 0, width: width / 3, height: height))
        }
        context.setFillColor(CGColor(gray: 1, alpha: 1))
        context.fill(CGRect(x: 0, y: 0, width: width / 6, height: height / 4))
        return try XCTUnwrap(context.makeImage())
    }
    private func encodeWithOrientation(_ image: CGImage, orientation: Int) throws -> Data {
        let data = NSMutableData()
        let destination = try XCTUnwrap(CGImageDestinationCreateWithData(data, UTType.tiff.identifier as CFString, 1, nil))
        CGImageDestinationAddImage(destination, image, [kCGImagePropertyOrientation: orientation] as CFDictionary)
        XCTAssertTrue(CGImageDestinationFinalize(destination))
        return data as Data
    }
    private func pixels(_ image: CGImage) throws -> [UInt8] {
        let context = try RasterCodec.bitmap(width: image.width, height: image.height)
        context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
        return Array(UnsafeBufferPointer(start: try XCTUnwrap(context.data).assumingMemoryBound(to: UInt8.self), count: image.width * image.height * 4))
    }
    func testEightExifOrientationsAreAppliedExactlyOnce() throws {
        let raw = try stripedImage()
        let context = CIContext(options: [.outputColorSpace: RasterCodec.colorSpace])
        for orientation in 1...8 {
            let encoded = try encodeWithOrientation(raw, orientation: orientation)
            let source = try RasterCodec.metadata(encoded)
            var recipe = EditRecipe(); recipe.sources = [source]
            recipe.canvasWidth = source.pixelWidth; recipe.canvasHeight = source.pixelHeight
            let actual = try RecipeRenderer().render(recipe, sources: [source.id: encoded])
            let expectedCI = CIImage(cgImage: raw).oriented(forExifOrientation: Int32(orientation))
            let expected = try XCTUnwrap(context.createCGImage(expectedCI, from: expectedCI.extent,
                                                             format: .RGBA8, colorSpace: RasterCodec.colorSpace))
            XCTAssertEqual(actual.width, orientation >= 5 ? raw.height : raw.width)
            XCTAssertEqual(actual.height, orientation >= 5 ? raw.width : raw.height)
            XCTAssertEqual(try pixels(actual), try pixels(expected), "EXIF \(orientation)")
        }
    }
    func testCropGeometryAlwaysCoversTileAndMatchesFocalDirection() throws {
        for x in [0.0, 0.5, 1.0] {
            for y in [0.0, 0.5, 1.0] {
                for zoom in [1.0, 2.0, 5.0] {
                    var crop = SourceCrop(); crop.centerX = x; crop.centerY = y; crop.zoom = zoom
                    let tile = CGRect(x: 15, y: 35, width: 300, height: 150)
                    let rect = RecipeRenderer.cropRect(imageWidth: 120, imageHeight: 80, crop: crop, in: tile)
                    XCTAssertTrue(rect.contains(tile), "\(x), \(y), \(zoom)")
                    XCTAssertEqual(rect.width / rect.height, 1.5, accuracy: 0.00001)
                }
            }
        }
        let bytes = try RasterCodec.encode(stripedImage(), as: .png)
        let source = try RasterCodec.metadata(bytes)
        var recipe = EditRecipe(); recipe.sources = [source]; recipe.canvasWidth = 60; recipe.canvasHeight = 60
        recipe.sources[0].crop.zoom = 3
        recipe.sources[0].crop.centerX = 0
        let left = try pixels(RecipeRenderer().render(recipe, sources: [source.id: bytes]))
        recipe.sources[0].crop.centerX = 1
        let right = try pixels(RecipeRenderer().render(recipe, sources: [source.id: bytes]))
        let center = (30 * 60 + 30) * 4
        XCTAssertGreaterThan(left[center], 240); XCTAssertLessThan(left[center + 2], 15)
        XCTAssertLessThan(right[center], 15); XCTAssertGreaterThan(right[center + 2], 240)
    }
    func testPreviewAndFullExportUseSameFilterAndCropGraph() throws {
        let bytes = try RasterCodec.encode(stripedImage(width: 1200, height: 800), as: .png)
        let source = try RasterCodec.metadata(bytes)
        var recipe = EditRecipe(); recipe.sources = [source]; recipe.canvasWidth = 1200; recipe.canvasHeight = 800
        recipe.sources[0].crop.zoom = 2; recipe.sources[0].crop.centerX = 0.65
        for preset in [FilterPreset.original, .fade, .invert, .sepia, .crystal] {
            recipe.filter = preset
            let renderer = RecipeRenderer()
            let full = try renderer.render(recipe, sources: [source.id: bytes])
            let preview = try renderer.render(recipe, sources: [source.id: bytes], maximumDimension: 300)
            let scaledCI = CIImage(cgImage: full).transformed(by: CGAffineTransform(scaleX: 0.25, y: 0.25))
            let reference = try XCTUnwrap(CIContext().createCGImage(scaledCI, from: scaledCI.extent, format: .RGBA8, colorSpace: RasterCodec.colorSpace))
            XCTAssertEqual(preview.width, 300); XCTAssertEqual(preview.height, 200)
            let a = try pixels(preview), b = try pixels(reference)
            XCTAssertEqual(a.count, b.count)
            // Separate sRGB8 quantization can vary by ≤2 in interior samples. Edges are
            // excluded because filtering a graph before/after rasterization resamples them.
            for y in stride(from: 10, to: 190, by: 30) {
                for x in stride(from: 10, to: 290, by: 30) {
                    for channel in 0..<4 {
                        let offset = (y * 300 + x) * 4 + channel
                        XCTAssertEqual(Double(a[offset]), Double(b[offset]), accuracy: 2, "\(preset.rawValue) \(x),\(y)")
                    }
                }
            }
        }
    }
}
