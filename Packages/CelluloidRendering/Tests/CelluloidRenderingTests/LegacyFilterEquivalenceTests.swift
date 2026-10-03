import XCTest
import CoreGraphics
import CoreImage
import ImageIO
import CelluloidDomain
@testable import CelluloidRendering

final class LegacyFilterEquivalenceTests: XCTestCase {
    /// Regression for the actual iOS9b decoder finding. The original UIKit
    /// path consumes an ImageIO CGImage; CIImage(data:) had different nonlocal
    /// filter behavior even when an 8-bit input comparison happened to match.
    func testImageIODecodingMatchesLegacyNonlocalFiltersAndAlphaBorder() throws {
        for translucentBorder in [false, true] {
            let bitmap = try RasterCodec.bitmap(width: 120, height: 80)
            for y in 0..<80 { for x in 0..<120 {
                let border = x == 0 || x == 119 || y == 0 || y == 79
                let alpha: CGFloat = translucentBorder && border ? 243.0 / 255 : 1
                bitmap.setFillColor(CGColor(srgbRed: CGFloat(x) / 119, green: 0.4, blue: 0.8, alpha: alpha))
                bitmap.fill(CGRect(x: x, y: y, width: 1, height: 1))
            } }
            let data = try RasterCodec.encode(XCTUnwrap(bitmap.makeImage()), as: .png)
            let file = try XCTUnwrap(CGImageSourceCreateWithData(data as CFData, nil))
            let cg = try XCTUnwrap(CGImageSourceCreateImageAtIndex(file, 0, [kCGImageSourceShouldCache: false] as CFDictionary))
            let legacyInput = CIImage(cgImage: cg), read = CIContext()
            let metadata = try RasterCodec.metadata(data)
            var recipe = EditRecipe(); recipe.sources = [metadata]; recipe.canvasWidth = 120; recipe.canvasHeight = 80
            func normalized(_ image: CIImage) -> [UInt8] {
                var result = [UInt8](repeating: 0, count: 120 * 80 * 4)
                result.withUnsafeMutableBytes { read.render(image, toBitmap: $0.baseAddress!, rowBytes: 120 * 4,
                    bounds: legacyInput.extent, format: .RGBA8, colorSpace: RasterCodec.colorSpace) }
                return result
            }
            for (preset, name) in [(FilterPreset.sketch, "CILineOverlay"), (.comic, "CIComicEffect")] {
                recipe.filter = preset
                let expected = try XCTUnwrap(read.createCGImage(legacyInput.applyingFilter(name), from: legacyInput.extent))
                let actual = try RecipeRenderer().render(recipe, sources: [metadata.id: data])
                let maximum = zip(normalized(CIImage(cgImage: expected)), normalized(CIImage(cgImage: actual))).map { abs(Int($0) - Int($1)) }.max() ?? 255
                print("LEGACY_FILTER_DECODER_REGRESSION filter=\(preset.rawValue) alphaBorder=\(translucentBorder) maximum=\(maximum)")
                XCTAssertLessThanOrEqual(maximum, 2)
            }
        }
    }
    /// The frozen UIKit implementation calls CIContext() and creates its CGImage using
    /// the default overload. This oracle exercises that actual context path, not just names.
    func testActualNativeOutputsMatchLegacyDefaultContextForGradientAlphaAndP3() throws {
        let spaces = [RasterCodec.colorSpace, try XCTUnwrap(CGColorSpace(name: CGColorSpace.displayP3))]
        for (spaceIndex, space) in spaces.enumerated() {
            let context = try XCTUnwrap(CGContext(data: nil, width: 128, height: 96, bitsPerComponent: 8,
                                                 bytesPerRow: 512, space: space,
                                                 bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
            context.clear(CGRect(x: 0, y: 0, width: 128, height: 96))
            for x in 0..<128 {
                let t = CGFloat(x) / 127
                context.setFillColor(try XCTUnwrap(CGColor(colorSpace: space, components: [t, 1-t, 0.2 + t/2, 0.3 + t*0.7])))
                context.fill(CGRect(x: x, y: 0, width: 1, height: 96))
            }
            let original = try XCTUnwrap(context.makeImage())
            let data = try RasterCodec.encode(original, as: .png)
            let decoder = try XCTUnwrap(CGImageSourceCreateWithData(data as CFData, nil))
            let decodedCG = try XCTUnwrap(CGImageSourceCreateImageAtIndex(decoder, 0, nil))
            let input = CIImage(cgImage: decodedCG)
            let metadata = try RasterCodec.metadata(data)
            var recipe = EditRecipe(); recipe.sources = [metadata]; recipe.canvasWidth = 128; recipe.canvasHeight = 96
            let legacyContext = CIContext()
            for preset in FilterPreset.allCases where preset != .pixellateFace {
                recipe.filter = preset
                let legacyGraph: CIImage
                if let name = preset.coreImageFilterName {
                    legacyGraph = try XCTUnwrap(CIFilter(name: name, parameters: [kCIInputImageKey: input])?.outputImage)
                } else { legacyGraph = input }
                let expectedImage = try XCTUnwrap(legacyContext.createCGImage(legacyGraph, from: input.extent))
                let actualImage = try RecipeRenderer().render(recipe, sources: [metadata.id: data])
                let expected = try pixels(expectedImage), actual = try pixels(actualImage)
                let differences = zip(expected, actual).map { abs(Int($0) - Int($1)) }
                let maximum = differences.max() ?? 0
                let mean = Double(differences.reduce(0,+)) / Double(differences.count)
                print("LEGACY_FILTER_PIXELS space=\(spaceIndex) filter=\(preset.rawValue) max=\(maximum) mean=\(mean)")
                XCTAssertLessThanOrEqual(maximum, 2, "\(preset.rawValue) space \(spaceIndex)")
            }
        }
    }
    private func pixels(_ image: CGImage) throws -> [UInt8] {
        let context = try RasterCodec.bitmap(width: image.width, height: image.height)
        context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
        return Array(UnsafeBufferPointer(start: try XCTUnwrap(context.data).assumingMemoryBound(to: UInt8.self), count: image.width * image.height * 4))
    }
}
