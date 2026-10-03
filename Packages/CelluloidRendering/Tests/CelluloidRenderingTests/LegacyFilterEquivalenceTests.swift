import XCTest
import CoreGraphics
import CoreImage
import ImageIO
import CelluloidDomain
@testable import CelluloidRendering

final class LegacyFilterEquivalenceTests: XCTestCase {
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
