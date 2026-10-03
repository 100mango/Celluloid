import XCTest
import CoreGraphics
import ImageIO
import CoreImage
import UniformTypeIdentifiers
import CelluloidDomain
@testable import CelluloidRendering

final class RenderingTests: XCTestCase {
    private func fixture(_ color: CGColor, width: Int = 64, height: Int = 48) throws -> Data {
        let context = try RasterCodec.bitmap(width: width, height: height)
        context.setFillColor(color); context.fill(CGRect(x: 0, y: 0, width: width, height: height))
        return try RasterCodec.encode(XCTUnwrap(context.makeImage()), as: .png)
    }
    private func document(_ colors: [CGColor]) throws -> (EditRecipe, [UUID: Data]) {
        var recipe = EditRecipe(); var data: [UUID: Data] = [:]
        for color in colors {
            let bytes = try fixture(color)
            let source = try RasterCodec.metadata(bytes)
            recipe.sources.append(source); data[source.id] = bytes
        }
        if colors.count == 1 { recipe.canvasWidth = 64; recipe.canvasHeight = 48 }
        else { recipe.collageTemplate = try NativeResources.templates(count: colors.count).first!.assetName }
        return (recipe, data)
    }
    func testAllOriginalResourcesPresentAndAllTemplatesParse() throws {
        for sticker in StickerAsset.all { XCTAssertGreaterThan(try NativeResources.image(named: sticker.rawValue).width, 0) }
        for bubble in BubbleAsset.allCases {
            XCTAssertGreaterThan(try NativeResources.image(named: bubble.rawValue).width, 0)
            XCTAssertEqual(try NativeResources.bubbleArea(named: bubble.rawValue).count, 4)
        }
        XCTAssertEqual(try [2, 3, 4].flatMap { try NativeResources.templates(count: $0) }.count, 25)
    }
    func testEveryPresetProducesExpectedExtentAndFadeIsInstant() throws {
        let (base, sources) = try document([CGColor(colorSpace: RasterCodec.colorSpace, components: [0.8, 0.3, 0.1, 1])!])
        for preset in FilterPreset.allCases {
            var recipe = base; recipe.filter = preset
            let image = try RecipeRenderer().render(recipe, sources: sources)
            XCTAssertEqual(image.width, 64, preset.rawValue); XCTAssertEqual(image.height, 48, preset.rawValue)
        }
        let input = try RasterCodec.image(XCTUnwrap(sources.values.first))
        let renderer = RecipeRenderer()
        let expected = try XCTUnwrap(CIFilter(name: "CIPhotoEffectInstant", parameters: [kCIInputImageKey: input])?.outputImage)
        let actual = try renderer.apply(.fade, to: input)
        let context = CIContext()
        let a = try XCTUnwrap(context.createCGImage(actual, from: input.extent))
        let b = try XCTUnwrap(context.createCGImage(expected, from: input.extent))
        XCTAssertEqual(try RasterCodec.encode(a, as: .png), try RasterCodec.encode(b, as: .png))
    }
    func testEveryCollageHasEachSourceColorAndEightHundredPixelOutput() throws {
        let colors = [CGColor(colorSpace: RasterCodec.colorSpace, components: [1, 0, 0, 1])!, CGColor(colorSpace: RasterCodec.colorSpace, components: [0, 1, 0, 1])!,
                      CGColor(colorSpace: RasterCodec.colorSpace, components: [0, 0, 1, 1])!, CGColor(colorSpace: RasterCodec.colorSpace, components: [1, 1, 0, 1])!]
        for count in 2...4 {
            let (base, data) = try document(Array(colors.prefix(count)))
            for template in try NativeResources.templates(count: count) {
                var recipe = base; recipe.collageTemplate = template.assetName
                let image = try RecipeRenderer().render(recipe, sources: data)
                XCTAssertEqual(image.width, 800); XCTAssertEqual(image.height, 800)
                let context = try RasterCodec.bitmap(width: 800, height: 800)
                context.draw(image, in: CGRect(x: 0, y: 0, width: 800, height: 800))
                let pixels = try XCTUnwrap(context.data).assumingMemoryBound(to: UInt8.self)
                var found = Set<Int>()
                for offset in stride(from: 0, to: 800 * 800 * 4, by: 4) {
                    let r = pixels[offset], g = pixels[offset+1], b = pixels[offset+2]
                    if r > 240 && g < 15 && b < 15 { found.insert(0) }
                    if r < 15 && g > 240 && b < 15 { found.insert(1) }
                    if r < 15 && g < 15 && b > 240 { found.insert(2) }
                    if r > 240 && g > 240 && b < 15 { found.insert(3) }
                }
                if found != Set(0..<count), template.assetName == (try NativeResources.templates(count: count).first?.assetName) {
                    var histogram: [String: Int] = [:]
                    for offset in stride(from: 0, to: 800 * 800 * 4, by: 400) {
                        let key = "\(pixels[offset]),\(pixels[offset+1]),\(pixels[offset+2]),\(pixels[offset+3])"
                        histogram[key, default: 0] += 1
                    }
                    print("COLLAGE_DIAGNOSTIC count=\(count) alpha=\(image.alphaInfo.rawValue) byteOrder=\(image.bitmapInfo.rawValue) pixels=\(histogram.sorted { $0.value > $1.value }.prefix(10))")
                }
                XCTAssertEqual(found, Set(0..<count), template.assetName)
            }
        }
    }
    func testOverlayMultilingualTransformAndEncodedReadback() throws {
        var (recipe, data) = try document([CGColor(gray: 0.3, alpha: 1)])
        recipe.canvasWidth = 800; recipe.canvasHeight = 600
        var bubble = Overlay(bubble: .say1, text: "你好\nمرحبا\nFamily 👨‍👩‍👧‍👦")
        bubble.rotation = 27; bubble.width = 0.6; bubble.height = 0.7
        recipe.overlays = [bubble, Overlay(sticker: StickerAsset.all[0])]
        let image = try RecipeRenderer().render(recipe, sources: data)
        for type in [UTType.png, UTType.jpeg] {
            let bytes = try RasterCodec.encode(image, as: type)
            let source = try XCTUnwrap(CGImageSourceCreateWithData(bytes as CFData, nil))
            let readback = try XCTUnwrap(CGImageSourceCreateImageAtIndex(source, 0, nil))
            XCTAssertEqual(readback.width, 800); XCTAssertEqual(readback.height, 600)
        }
        var noOverlays = recipe; noOverlays.overlays = []
        let plain = try RecipeRenderer().render(noOverlays, sources: data)
        XCTAssertNotEqual(try RasterCodec.encode(image, as: .png), try RasterCodec.encode(plain, as: .png))
    }
    func testMissingSourceAndCorruptImageFailExplicitly() throws {
        let (recipe, _) = try document([CGColor(gray: 0.5, alpha: 1)])
        XCTAssertThrowsError(try RecipeRenderer().render(recipe, sources: [:]))
        XCTAssertThrowsError(try RasterCodec.metadata(Data("not an image".utf8)))
    }
}
