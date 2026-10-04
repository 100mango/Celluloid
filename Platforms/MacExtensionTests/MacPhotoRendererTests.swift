import XCTest
import Photos
import CoreGraphics
import CoreImage
import ImageIO
import UniformTypeIdentifiers
import CelluloidDomain
import CelluloidRendering

final class MacPhotoRendererTests: XCTestCase {
    private func source(width: Int = 240, height: Int = 320) throws -> (SourceImage, Data, CGImage) {
        let bitmap = try RasterCodec.bitmap(width: width, height: height)
        bitmap.setFillColor(CGColor(srgbRed: 0.1, green: 0.3, blue: 0.6, alpha: 1)); bitmap.fill(CGRect(x: 0, y: 0, width: width, height: height))
        // Neither horizontal/vertical reflection nor 180° rotation is symmetric.
        // Dimensions alone cannot distinguish EXIF orientations within each group.
        bitmap.setFillColor(CGColor(srgbRed: 0.9, green: 0.1, blue: 0.2, alpha: 1))
        bitmap.fill(CGRect(x: 0, y: 0, width: width / 3, height: height / 2))
        bitmap.setFillColor(CGColor(srgbRed: 0.2, green: 0.9, blue: 0.1, alpha: 1))
        bitmap.fill(CGRect(x: width / 2, y: height * 3 / 4, width: width / 4, height: height / 4))
        bitmap.setFillColor(CGColor(srgbRed: 0.9, green: 0.8, blue: 0.1, alpha: 1))
        bitmap.fill(CGRect(x: width * 4 / 5, y: height / 5, width: width / 5, height: height / 6))
        let image = try XCTUnwrap(bitmap.makeImage()), bytes = try RasterCodec.encode(image, as: .png)
        return (try RasterCodec.metadata(bytes), bytes, image)
    }
    private func pixels(_ image: CGImage) throws -> [UInt8] {
        let context = try RasterCodec.bitmap(width: image.width, height: image.height)
        context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
        return Array(UnsafeBufferPointer(start: context.data!.assumingMemoryBound(to: UInt8.self), count: context.bytesPerRow * context.height))
    }
    func testRawAffineStickerRasterMatchesIndependentFixedGeometryOracle() throws {
        let (source, bytes, base) = try source()
        var adjustment = MacPhotoAdjustment(); adjustment.referenceCanvas = CGSize(width: 240, height: 320)
        var layer = MacPhotoLayer(kind: .sticker, asset: "32", canvas: adjustment.referenceCanvas!)
        layer.bounds = CGRect(x: 2, y: 3, width: 100, height: 120)
        layer.center = CGPoint(x: 140, y: 180)
        layer.transform = CGAffineTransform(a: -1.1, b: 0.2, c: 0.35, d: 0.9, tx: 7, ty: -9)
        adjustment.stickers = [layer]
        let actual = try MacPhotoRenderer().render(adjustment, source: source, bytes: bytes)
        let expected = try RasterCodec.bitmap(width: 240, height: 320)
        expected.draw(base, in: CGRect(x: 0, y: 0, width: 240, height: 320))
        // Algebraic oracle: map local UIKit points directly to bitmap coordinates.
        // x = -1.1*x + .35*y + (147 + 1.1*52 - .35*63)
        // y = -.2*x - .9*y + (149 + .2*52 + .9*63)
        expected.concatenate(CGAffineTransform(a: -1.1, b: -0.2, c: 0.35, d: -0.9,
            tx: 147 + 1.1 * 52 - 0.35 * 63, ty: 149 + 0.2 * 52 + 0.9 * 63))
        let asset = try NativeResources.image(named: "32")
        let scale = min(68 / CGFloat(asset.width), 88 / CGFloat(asset.height))
        let width = CGFloat(asset.width) * scale, height = CGFloat(asset.height) * scale
        expected.translateBy(x: 52 - width / 2, y: 63 + height / 2); expected.scaleBy(x: 1, y: -1)
        expected.draw(asset, in: CGRect(x: 0, y: 0, width: width, height: height))
        let a = try pixels(actual), b = try pixels(XCTUnwrap(expected.makeImage()))
        XCTAssertLessThanOrEqual(zip(a,b).map { abs(Int($0)-Int($1)) }.max() ?? 0, 1)
        XCTAssertNotEqual(a, try pixels(base), "The actually rendered sticker must change the image")
    }
    func testAspectFitInsetsBoundsOriginAndBubbleBeforeStickerAreNotDiscarded() throws {
        XCTAssertEqual(MacPhotoRenderer.artworkRect(bounds: CGRect(x: 2, y: 3, width: 100, height: 120), imageWidth: 200, imageHeight: 100), CGRect(x: 18, y: 46, width: 68, height: 34))
        let (source, bytes, _) = try source()
        var adjustment = MacPhotoAdjustment(); adjustment.referenceCanvas = CGSize(width: 240, height: 320)
        adjustment.bubbles = [MacPhotoLayer(kind: .bubble, asset: "say1", canvas: adjustment.referenceCanvas!)]
        adjustment.stickers = [MacPhotoLayer(kind: .sticker, asset: "32", canvas: adjustment.referenceCanvas!)]
        XCTAssertEqual(adjustment.layers.map(\.asset), ["say1", "32"])
        let output = try MacPhotoRenderer().render(adjustment, source: source, bytes: bytes)
        XCTAssertEqual(output.width, 240); XCTAssertEqual(output.height, 320)
        let preview = try MacPhotoRenderer().render(adjustment, source: source, bytes: bytes, maximumDimension: 160)
        XCTAssertEqual(preview.width, 120); XCTAssertEqual(preview.height, 160)
        for asset in BubbleAsset.allCases {
            let legacy = try NativeResources.legacyPhotosBubbleImage(named: asset.rawValue)
            let canonical = try NativeResources.image(named: asset.rawValue)
            XCTAssertGreaterThan(legacy.width, 0); XCTAssertGreaterThan(legacy.height, 0)
            XCTAssertLessThan(legacy.width, canonical.width)
            XCTAssertLessThan(legacy.height, canonical.height)
        }
    }
    func testBubbleTextAreaUsesOriginalUIKitRoundedImageRectBeforeInsets() throws {
        let rect = try XCTUnwrap(MacPhotoRenderer.bubbleTextRect(bounds: CGRect(x: 0, y: 0, width: 180, height: 96),
            imageWidth: 800, imageHeight: 1000, area: [16, 84, 18.1, 80.6]))
        // UIImageView.imageRect is (48, 0, 51, 64) inside the 16pt inset
        // image view. Its separately rounded width is not the drawn 51.2pt.
        XCTAssertEqual(rect.minX, 77.231, accuracy: 0.000001)
        XCTAssertEqual(rect.minY, 26.24, accuracy: 0.000001)
        XCTAssertEqual(rect.width, 27.875, accuracy: 0.000001)
        XCTAssertEqual(rect.height, 43.52, accuracy: 0.000001)
        let translated = try XCTUnwrap(MacPhotoRenderer.bubbleTextRect(bounds: CGRect(x: 2, y: 3, width: 180, height: 96),
            imageWidth: 800, imageHeight: 1000, area: [16, 84, 18.1, 80.6]))
        XCTAssertEqual(translated, rect.offsetBy(dx: 2, dy: 3))
        XCTAssertNil(MacPhotoRenderer.bubbleTextRect(bounds: .zero, imageWidth: 800, imageHeight: 1000, area: [16, 84, 18.1, 80.6]))
    }
    func testProductionExportRejectsUnqualifiedLayersBeforeRasterOrEncoding() async throws {
        var adjustment = MacPhotoAdjustment(); adjustment.referenceCanvas = CGSize(width: 240, height: 320)
        XCTAssertNoThrow(try MacPhotoRenderer.requireQualifiedPhotosOutput(adjustment))
        adjustment.stickers = [MacPhotoLayer(kind: .sticker, asset: "32", canvas: adjustment.referenceCanvas!)]
        // Invalid source bytes deliberately prove the qualification check wins
        // before source decoding/allocation or any Photos writer can start.
        let source = SourceImage(displayName: "Not decoded", pixelWidth: 240, pixelHeight: 320)
        do {
            _ = try await MacPhotoRenderQueue.shared.export(adjustment, source: source, bytes: Data())
            XCTFail("Unqualified layer pixels must not replace the current Photos raster")
        } catch MacPhotoRenderQualificationError.layeredPhotosOutput { }
        catch { XCTFail("Expected the layer qualification error before rendering, got \(error)") }
    }
    func testOriginalAllOrientationsAndFilterMatchIndependentCoreImageInput() throws {
        let (_, _, image) = try source(width: 120, height: 80)
        let context = CIContext()
        for orientation in 1...8 {
            let data = NSMutableData()
            let destination = try XCTUnwrap(CGImageDestinationCreateWithData(data, UTType.tiff.identifier as CFString, 1, nil))
            CGImageDestinationAddImage(destination, image, [kCGImagePropertyOrientation: orientation] as CFDictionary)
            XCTAssertTrue(CGImageDestinationFinalize(destination))
            let bytes = data as Data, source = try RasterCodec.metadata(bytes)
            let decoded = try XCTUnwrap(CGImageSourceCreateWithData(bytes as CFData, nil))
            let cg = try XCTUnwrap(CGImageSourceCreateImageAtIndex(decoded, 0, nil))
            let raw = CIImage(cgImage: cg).oriented(forExifOrientation: Int32(orientation))
            for filter in [FilterPreset.original, .fade, .chrome] {
                var adjustment = MacPhotoAdjustment(); adjustment.filter = filter
                let graph = filter.coreImageFilterName.map { raw.applyingFilter($0).cropped(to: raw.extent) } ?? raw
                let expected = try XCTUnwrap(context.createCGImage(graph, from: raw.extent))
                let actual = try MacPhotoRenderer().render(adjustment, source: source, bytes: bytes)
                XCTAssertEqual(actual.width, expected.width); XCTAssertEqual(actual.height, expected.height)
                XCTAssertLessThanOrEqual(zip(try pixels(actual), try pixels(expected)).map { abs(Int($0)-Int($1)) }.max() ?? 0, 2)
            }
        }
    }
    func testTextHasFiniteOriginalIntegerFontSearchAndNeverTruncatesOverflow() throws {
        let layout = try MacPhotoTextLayout.make("Hello", rect: CGRect(x: 0, y: 0, width: 160, height: 50))
        XCTAssertEqual(layout.fontSize, 16)
        XCTAssertThrowsError(try MacPhotoTextLayout.make(String(repeating: "Long multiline text 你好 ", count: 300), rect: CGRect(x: 0, y: 0, width: 1, height: 1)))
        let raster = try MacPhotoTextRaster.make(layout, bounds: CGSize(width: 27.875, height: 43.52))
        XCTAssertEqual(raster.width, 56); XCTAssertEqual(raster.height, 88)
        XCTAssertThrowsError(try MacPhotoTextRaster.make(layout, bounds: CGSize(width: CGFloat.infinity, height: 20)))
        XCTAssertThrowsError(try MacPhotoTextRaster.make(layout, bounds: CGSize(width: 1_000_000, height: 1_000_000)))
    }
    @MainActor func testPrincipalControllerHostsRealEditorAndPureFormatNegotiation() throws {
        let controller = MacPhotoEditingController()
        _ = controller.view
        XCTAssertEqual(controller.children.count, 1)
        XCTAssertTrue(controller.view.subviews.first === controller.children[0].view)
        let bytes = Data([1,2,3])
        XCTAssertTrue(controller.canHandle(PHAdjustmentData(formatIdentifier: MacPhotoAdjustment.identifier, formatVersion: "1.0", data: bytes)))
        XCTAssertFalse(controller.canHandle(PHAdjustmentData(formatIdentifier: "other", formatVersion: "1.0", data: bytes)))
        XCTAssertFalse(controller.canHandle(PHAdjustmentData(formatIdentifier: MacPhotoAdjustment.identifier, formatVersion: "2.0", data: bytes)))
        var callbacks = 0
        controller.cancelContentEditing(); controller.finishContentEditing { _ in callbacks += 1 }
        XCTAssertEqual(callbacks, 0)
    }
}
