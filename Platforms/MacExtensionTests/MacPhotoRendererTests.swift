import XCTest
import AppKit
import Photos
import CoreGraphics
import CoreImage
import CoreText
import CryptoKit
import ImageIO
import UniformTypeIdentifiers
import CelluloidDomain
import CelluloidRendering

final class MacPhotoRendererTests: XCTestCase {
    private var observedOracleLines: [[String: Any]] = []
    private var observedOracleBacking: CGImage?

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
        XCTAssertThrowsError(try MacPhotoTextRaster.make(layout, bounds: CGSize(width: 80, height: 40), padding: -1))
        XCTAssertThrowsError(try MacPhotoTextRaster.make(layout, bounds: CGSize(width: 80, height: 40), padding: CGFloat.infinity))
        XCTAssertThrowsError(try MacPhotoTextRaster.make(layout, bounds: CGSize(width: 80, height: 40), padding: 65))
    }

    private let qualifiedText = "Hello, 世界 🎬"
    private var qualifiedRect: CGRect { CGRect(x: 77.231, y: 26.24, width: 27.875, height: 43.52) }

    private func frameLines(_ layout: MacPhotoTextLayout) -> ([NSRange], [CGPoint]) {
        let lines = CTFrameGetLines(layout.frame) as! [CTLine]
        var origins = [CGPoint](repeating: .zero, count: lines.count)
        CTFrameGetLineOrigins(layout.frame, CFRange(location: 0, length: 0), &origins)
        return (lines.map { let value = CTLineGetStringRange($0); return NSRange(location: value.location, length: value.length) }, origins)
    }

    private struct QualifiedGeometry {
        var text: String
        var ranges: [NSRange]
        var baselines: [CGFloat]
        var destination: CGRect
        var fontSize: CGFloat
    }

    private func geometry(_ layout: MacPhotoTextLayout, text: String, rect: CGRect) throws -> QualifiedGeometry {
        let (ranges, origins) = frameLines(layout)
        let image = try MacPhotoTextRaster.make(layout, bounds: rect.size)
        let destination = MacPhotoTextRaster.destinationRect(for: image, origin: rect.origin)
        // Convert CT bottom-left frame baselines into the logical label. No
        // backing-size fit or inferred UIKit baseline anchor enters this math.
        let baselines = origins.map { destination.minY + (rect.height - layout.typographicHeight) / 2 + layout.height - $0.y }
        return QualifiedGeometry(text: text, ranges: ranges, baselines: baselines, destination: destination, fontSize: layout.fontSize)
    }

    private func matchesIndependent52Geometry(_ value: QualifiedGeometry) -> Bool {
        // Recorded 52bf AppKit natural pitch/centering plus original CT/UI
        // leading-space placement. These constants are not candidate pixels.
        let expected = CGRect(x: 77.231, y: 26.24, width: 28, height: 44)
        let fields = [value.destination.minX, value.destination.minY, value.destination.width, value.destination.height]
        let expectedFields = [expected.minX, expected.minY, expected.width, expected.height]
        return value.text == qualifiedText && value.fontSize == 10
            && value.ranges == [NSRange(location: 0, length: 6), NSRange(location: 6, length: 4), NSRange(location: 10, length: 2)]
            && value.baselines.count == 3
            && zip(value.baselines, [CGFloat(40), 52, 64]).allSatisfy { abs($0 - $1) <= 0.000001 }
            && zip(fields, expectedFields).allSatisfy { abs($0 - $1) <= 0.000001 }
    }

    func testNaturalNativePitchKeepsIndependentObservedBaselinesAndLegacySpans() throws {
        let layout = try MacPhotoTextLayout.make(qualifiedText, rect: qualifiedRect)
        XCTAssertEqual(layout.fontSize, 10); XCTAssertEqual(layout.typographicHeight, 36)
        XCTAssertGreaterThanOrEqual(layout.height, layout.typographicHeight,
            "CT fitting allocation must remain available instead of clipping it to the natural block")
        XCTAssertEqual(layout.lineHeight, 12)
        XCTAssertTrue(matchesIndependent52Geometry(try geometry(layout, text: qualifiedText, rect: qualifiedRect)))

        // Independently lay out natural native text using public TextKit. Its
        // whitespace wrapping is deliberately not adopted as the legacy oracle.
        let paragraph = NSMutableParagraphStyle(); paragraph.lineBreakMode = .byCharWrapping
        let storage = NSTextStorage(string: qualifiedText, attributes: [.font: NSFont.systemFont(ofSize: 10), .paragraphStyle: paragraph])
        let manager = NSLayoutManager(), container = NSTextContainer(containerSize: CGSize(width: qualifiedRect.width, height: 1000))
        container.lineFragmentPadding = 0; container.lineBreakMode = .byCharWrapping
        storage.addLayoutManager(manager); manager.addTextContainer(container); manager.ensureLayout(for: container)
        var baselineOrigins: [CGFloat] = []
        manager.enumerateLineFragments(forGlyphRange: manager.glyphRange(for: container)) { rect, _, _, range, _ in
            baselineOrigins.append(rect.minY + manager.location(forGlyphAt: range.location).y)
        }
        XCTAssertEqual(baselineOrigins, [10, 22, 34])
        XCTAssertEqual(manager.usedRect(for: container).height, 36)
    }

    func testTextBackingUsesIntrinsicPointSizeAndOneLogicalOrigin() throws {
        let layout = try MacPhotoTextLayout.make(qualifiedText, rect: qualifiedRect)
        let image = try MacPhotoTextRaster.make(layout, bounds: qualifiedRect.size)
        XCTAssertEqual(image.width, 56); XCTAssertEqual(image.height, 88)
        let actual = MacPhotoTextRaster.destinationRect(for: image, origin: qualifiedRect.origin)
        XCTAssertEqual(actual, CGRect(x: 77.231, y: 26.24, width: 28, height: 44))
        XCTAssertEqual(actual.width / CGFloat(image.width), 0.5)
        XCTAssertEqual(actual.height / CGFloat(image.height), 0.5)
        XCTAssertNotEqual(actual.size, qualifiedRect.size, "Fractional logical bounds must not squeeze the rounded backing")
        let moved = MacPhotoTextRaster.destinationRect(for: image, origin: CGPoint(x: -7.125, y: 4.75))
        XCTAssertEqual(moved, CGRect(x: -7.125, y: 4.75, width: 28, height: 44))
    }

    private var fittingCases: [(String, CGSize)] { [
        (qualifiedText, qualifiedRect.size),
        ("\nHello\n\n世界\n", CGSize(width: 120.125, height: 120.5)),
        ("\n\n", CGSize(width: 80.125, height: 88.75)),
        ("gypq j\u{0301} café", CGSize(width: 120.125, height: 56.25)),
        ("第一行\n第二行\n👩🏽‍💻", CGSize(width: 96.125, height: 88.75)),
        ("👨‍👩‍👧‍👦 👩🏽‍💻 🎬", CGSize(width: 140.25, height: 64.5)),
        ("日本語\n한국어\nHello", CGSize(width: 96.25, height: 92.125)),
        ("Narrow 文 👩‍💻", CGSize(width: 36.125, height: 150.25)),
        ("a\u{0301} e\u{0301} o\u{0308} 你好", CGSize(width: 57.25, height: 96.125))
    ] }

    private func alphaOutside(_ image: CGImage, x: Int, y: Int, width: Int, height: Int) throws -> Int {
        let rgba = try pixels(image)
        var result = 0
        for row in 0..<image.height {
            for column in 0..<image.width where column < x || column >= x + width || row < y || row >= y + height {
                result += Int(rgba[(row * image.width + column) * 4 + 3])
            }
        }
        return result
    }

    func testSamePathPaddingDoesNotClipQualifiedTextCases() throws {
        for (text, bounds) in fittingCases {
            let layout = try MacPhotoTextLayout.make(text, rect: CGRect(origin: .zero, size: bounds))
            let normal = try MacPhotoTextRaster.make(layout, bounds: bounds)
            let padded = try MacPhotoTextRaster.make(layout, bounds: bounds, padding: 8)
            let offset = Int(8 * MacPhotoTextRaster.scale)
            let crop = try XCTUnwrap(padded.cropping(to: CGRect(x: offset, y: offset, width: normal.width, height: normal.height)))
            XCTAssertEqual(try pixels(normal), try pixels(crop), "Same draw path must retain identical interior pixels: \(text)")
            let outsideAlpha = try alphaOutside(padded, x: offset, y: offset, width: normal.width, height: normal.height)
            XCTAssertEqual(outsideAlpha, 0, "Padding must not reveal clipped glyph ink: \(text)")
        }
    }

    func testUnicodeCoveragePreservesClustersWhitespaceAndRejectsOverflow() throws {
        for (text, bounds) in fittingCases {
            let layout = try MacPhotoTextLayout.make(text, rect: CGRect(origin: .zero, size: bounds))
            XCTAssertTrue((2...16).contains(Int(layout.fontSize))); XCTAssertEqual(layout.fontSize.rounded(), layout.fontSize)
            let (ranges, _) = frameLines(layout)
            XCTAssertEqual(layout.typographicHeight, CGFloat(ranges.count) * layout.lineHeight)
            XCTAssertLessThanOrEqual(layout.typographicHeight, bounds.height)
            var boundaries: Set<Int> = [0], count = 0
            for character in text { count += String(character).utf16.count; boundaries.insert(count) }
            var next = 0, replay = ""
            for range in ranges {
                XCTAssertEqual(range.location, next)
                XCTAssertTrue(boundaries.contains(range.location)); XCTAssertTrue(boundaries.contains(NSMaxRange(range)), "A line must not split a combining/emoji/ZWJ cluster")
                replay += (text as NSString).substring(with: range); next = NSMaxRange(range)
            }
            XCTAssertEqual(next, text.utf16.count); XCTAssertEqual(replay, text)
        }
        XCTAssertThrowsError(try MacPhotoTextLayout.make(String(repeating: "👩🏽‍💻 文 ", count: 100), rect: CGRect(x: 0, y: 0, width: 1, height: 1)))
    }

    func testGeometryAndSpanOracleRejectsBackingBaselineAndWhitespaceMutations() throws {
        // These are checks of the metadata oracle itself. Actual compositor
        // fault coverage is in testProductionTextMatchesIndependentNativeControlAndRejectsPathMutations.
        let layout = try MacPhotoTextLayout.make(qualifiedText, rect: qualifiedRect)
        let original = try geometry(layout, text: qualifiedText, rect: qualifiedRect)
        XCTAssertTrue(matchesIndependent52Geometry(original))
        var bad = original; bad.destination.size = qualifiedRect.size
        XCTAssertFalse(matchesIndependent52Geometry(bad), "Reject the original backing squeeze")
        bad = original; bad.baselines = [39.849890909, 51.498754545, 63.147618182]
        XCTAssertFalse(matchesIndependent52Geometry(bad), "Reject the recorded compressed baselines")
        bad = original; bad.baselines[2] += 1
        XCTAssertFalse(matchesIndependent52Geometry(bad), "Reject a shifted emoji baseline")
        bad = original; bad.ranges = [NSRange(location: 0, length: 7), NSRange(location: 7, length: 3), NSRange(location: 10, length: 2)]
        XCTAssertFalse(matchesIndependent52Geometry(bad), "Do not adopt TextKit's different wrapping-space placement")
        bad = original; bad.text = "Hello,世界 🎬"
        XCTAssertFalse(matchesIndependent52Geometry(bad), "Reject trimming source whitespace")
        bad = original; bad.ranges.removeLast()
        XCTAssertFalse(matchesIndependent52Geometry(bad), "Reject omitted emoji coverage")
        bad = original; bad.destination.origin.x += 1
        XCTAssertFalse(matchesIndependent52Geometry(bad), "Reject an unrequested placement offset")
        bad = original; bad.fontSize = 11
        XCTAssertFalse(matchesIndependent52Geometry(bad), "Reject a changed fitted font size")
        let padded = try MacPhotoTextRaster.make(layout, bounds: qualifiedRect.size, padding: 8)
        let offset = Int(8 * MacPhotoTextRaster.scale)
        XCTAssertEqual(try alphaOutside(padded, x: offset, y: offset, width: 56, height: 88), 0)
        XCTAssertGreaterThan(try alphaOutside(padded, x: offset, y: offset, width: 28, height: 88), 0,
            "The same-path clipping check must detect a backing that cuts the glyphs in half")
    }

    /// Public AppKit shapes the three reviewed legacy line strings separately.
    /// Width is unconstrained here: the expected line spans and baselines come
    /// from the original UIKit appearance and independent 52bf native evidence,
    /// never from the candidate layout, raster, or computed destination.
    private func independentLegacyTextBacking() throws -> CGImage {
        observedOracleLines = []; observedOracleBacking = nil
        let bitmap = try RasterCodec.bitmap(width: 56, height: 88)
        bitmap.translateBy(x: 0, y: 88); bitmap.scaleBy(x: 2, y: -2)
        NSGraphicsContext.saveGraphicsState()
        defer { NSGraphicsContext.restoreGraphicsState() }
        NSGraphicsContext.current = NSGraphicsContext(cgContext: bitmap, flipped: true)
        let lines = ["Hello,", " 世界 ", "🎬"]
        XCTAssertEqual(lines.joined(), qualifiedText)
        for (text, baseline) in zip(lines, [CGFloat(13.76), 25.76, 37.76]) {
            let paragraph = NSMutableParagraphStyle(); paragraph.alignment = .left
            let storage = NSTextStorage(string: text, attributes: [.font: NSFont.systemFont(ofSize: 10),
                .foregroundColor: NSColor.black, .paragraphStyle: paragraph])
            let manager = NativeOracleGlyphObserver(), container = NSTextContainer(containerSize: CGSize(width: 1000, height: 1000))
            container.lineFragmentPadding = 0
            storage.addLayoutManager(manager); manager.addTextContainer(container); manager.ensureLayout(for: container)
            let glyphRange = manager.glyphRange(for: container)
            XCTAssertEqual(manager.characterRange(forGlyphRange: glyphRange, actualGlyphRange: nil), NSRange(location: 0, length: text.utf16.count))
            XCTAssertEqual(manager.usedRect(for: container).height, 12)
            let firstGlyphLocation = manager.location(forGlyphAt: glyphRange.location)
            let lineBaseline = firstGlyphLocation.y
            let drawOrigin = CGPoint(x: 0, y: baseline - lineBaseline)
            manager.drawGlyphs(forGlyphRange: glyphRange, at: drawOrigin)
            observedOracleLines.append(["text": text, "declaredLocalBaseline": baseline,
                "firstGlyphLocation": [firstGlyphLocation.x, firstGlyphLocation.y],
                "drawOrigin": [drawOrigin.x, drawOrigin.y], "glyphRuns": manager.observations])
        }
        let image = try XCTUnwrap(bitmap.makeImage())
        observedOracleBacking = image
        return image
    }

    private func independentManufacturedComposite(source: CGImage) throws -> CGImage {
        // Historical UIKit FilterFactory.fade and the independent domain tests
        // specify Instant for the preset named Fade. Keep this literal oracle
        // independent of the candidate's filter-dispatch implementation.
        let graph = CIImage(cgImage: source).applyingFilter("CIPhotoEffectInstant")
        let context = CIContext(options: [.outputColorSpace: RasterCodec.colorSpace])
        let filtered = try XCTUnwrap(context.createCGImage(graph, from: CGRect(x: 0, y: 0, width: 480, height: 640),
            format: .RGBA8, colorSpace: RasterCodec.colorSpace))
        let bitmap = try RasterCodec.bitmap(width: 480, height: 640)
        bitmap.draw(filtered, in: CGRect(x: 0, y: 0, width: 480, height: 640))
        func drawUpright(_ image: CGImage, rect: CGRect) {
            bitmap.saveGState(); defer { bitmap.restoreGState() }
            bitmap.translateBy(x: rect.minX, y: rect.maxY); bitmap.scaleBy(x: 1, y: -1)
            bitmap.draw(image, in: CGRect(origin: .zero, size: rect.size))
        }
        bitmap.saveGState()
        // Independent fixed affine algebra, including UIKit->Quartz y mapping:
        // x=1.5*x-.25*y+127; y=640-(.25*x+1.5*y+221.5).
        bitmap.concatenate(CGAffineTransform(a: 1.5, b: -0.25, c: -0.25, d: -1.5, tx: 127, ty: 418.5))
        let bubble = try NativeResources.legacyPhotosBubbleImage(named: "say1")
        XCTAssertEqual(bubble.width, 533); XCTAssertEqual(bubble.height, 666)
        let artworkWidth = CGFloat(533) * 64 / 666
        drawUpright(bubble, rect: CGRect(x: 90 - artworkWidth / 2, y: 16, width: artworkWidth, height: 64))
        drawUpright(try independentLegacyTextBacking(), rect: CGRect(x: 77.231, y: 26.24, width: 28, height: 44))
        bitmap.restoreGState()
        bitmap.saveGState()
        // Original nonzero-bounds sticker: x=.5*x+25; y=684.25-.75*y.
        bitmap.concatenate(CGAffineTransform(a: 0.5, b: 0, c: 0, d: -0.75, tx: 25, ty: 684.25))
        drawUpright(try NativeResources.image(named: "32"), rect: CGRect(x: 18, y: 23, width: 40, height: 40))
        bitmap.restoreGState()
        return try XCTUnwrap(bitmap.makeImage())
    }

    func testProductionTextMatchesIndependentNativeControlAndRejectsPathMutations() throws {
        #if DEBUG
        let sourceBitmap = try RasterCodec.bitmap(width: 480, height: 640)
        sourceBitmap.setFillColor(CGColor(srgbRed: 0.2, green: 0.6, blue: 0.8, alpha: 1))
        sourceBitmap.fill(CGRect(x: 0, y: 0, width: 480, height: 640))
        let sourceCG = try XCTUnwrap(sourceBitmap.makeImage())
        let sourcePNG = try RasterCodec.encode(sourceCG, as: .png), source = try RasterCodec.metadata(sourcePNG)
        var adjustment = MacPhotoAdjustment(); adjustment.filter = .fade; adjustment.referenceCanvas = CGSize(width: 480, height: 640)
        var bubble = MacPhotoLayer(kind: .bubble, asset: "say1", text: qualifiedText, canvas: adjustment.referenceCanvas!)
        bubble.center = CGPoint(x: 240, y: 320); bubble.bounds = CGRect(x: 0, y: 0, width: 180, height: 96)
        bubble.transform = CGAffineTransform(a: 1.5, b: 0.25, c: -0.25, d: 1.5, tx: 10, ty: -4)
        var sticker = MacPhotoLayer(kind: .sticker, asset: "32", canvas: adjustment.referenceCanvas!)
        sticker.center = CGPoint(x: 44, y: -12); sticker.bounds = CGRect(x: 2, y: 3, width: 72, height: 80)
        sticker.transform = CGAffineTransform(a: 0.5, b: 0, c: 0, d: 0.75, tx: 0, ty: 0)
        adjustment.bubbles = [bubble]; adjustment.stickers = [sticker]
        let actualImage = try MacPhotoRenderer().render(adjustment, source: source, bytes: sourcePNG)
        let controlImage = try independentManufacturedComposite(source: sourceCG)
        let actual = try pixels(actualImage), control = try pixels(controlImage)
        func maximum(_ a: [UInt8], _ b: [UInt8]) -> Int {
            XCTAssertEqual(a.count, b.count)
            return zip(a, b).map { abs(Int($0) - Int($1)) }.max() ?? 0
        }
        func differingPixels(_ a: [UInt8], _ b: [UInt8]) -> Int {
            guard a.count == b.count else { return -1 }
            return stride(from: 0, to: a.count, by: 4).filter { index in
                (0..<4).contains { abs(Int(a[index + $0]) - Int(b[index + $0])) > 2 }
            }.count
        }
        func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
        let difference = maximum(actual, control)
        XCTAssertEqual(actual.count, 480 * 640 * 4)
        XCTAssertLessThanOrEqual(difference, 2, "Actual text-bearing production render must match the independent per-line AppKit/affine oracle")
        if difference > 2 {
            for (name, image) in [("actual", actualImage), ("independent", controlImage)] {
                let attachment = XCTAttachment(data: try RasterCodec.encode(image, as: .png), uniformTypeIdentifier: "public.png")
                attachment.name = "native-text-production-" + name; attachment.lifetime = .keepAlways; add(attachment)
            }
        }

        let layout = try MacPhotoTextLayout.make(qualifiedText, rect: qualifiedRect)
        let metadata = try geometry(layout, text: qualifiedText, rect: qualifiedRect)
        XCTAssertTrue(matchesIndependent52Geometry(metadata))
        // Observation only: retain the exact oracle backing used above and a
        // replay of the production helper at its actual computed text bounds.
        // Neither these observations nor a different renderer grants acceptance.
        let asset = try NativeResources.legacyPhotosBubbleImage(named: bubble.asset)
        let actualTextRect = try XCTUnwrap(MacPhotoRenderer.bubbleTextRect(bounds: bubble.bounds,
            imageWidth: asset.width, imageHeight: asset.height, area: NativeResources.bubbleArea(named: bubble.asset)))
        try observeGlyphBaselines(text: bubble.text, rect: actualTextRect, sourcePNG: sourcePNG,
            actualComposite: actualImage, oracle: XCTUnwrap(observedOracleBacking))
        var mutations: [[String: Any]] = []
        for name in ["shift-down-one-point", "squeeze-to-logical-bounds", "remove-wrapped-space", "clip-right-half"] {
            let renderer = MacPhotoRenderer()
            var calls = 0
            var probe = MacPhotoRenderer.TextRenderProbe(content: nil, destination: nil, clip: nil)
            switch name {
            case "shift-down-one-point": probe.destination = { destination, _ in calls += 1; return destination.offsetBy(dx: 0, dy: 1) }
            case "squeeze-to-logical-bounds": probe.destination = { _, logical in calls += 1; return logical }
            case "remove-wrapped-space": probe.content = { value in calls += 1; return value.replacingOccurrences(of: "Hello, ", with: "Hello,") }
            default: probe.clip = { destination in calls += 1; return CGRect(x: destination.minX, y: destination.minY, width: destination.width / 2, height: destination.height) }
            }
            renderer.textRenderProbe = probe
            // This is the same render entry and same CGContext text draw path
            // as above. Mutants are real output images, not changed DTOs.
            let mutated = try pixels(renderer.render(adjustment, source: source, bytes: sourcePNG))
            let controlDelta = maximum(mutated, control), actualDelta = maximum(mutated, actual)
            let controlCount = differingPixels(mutated, control), actualCount = differingPixels(mutated, actual)
            XCTAssertEqual(calls, 1, "Mutation must execute at the real text compositing operation")
            XCTAssertGreaterThan(controlDelta, 2, name); XCTAssertGreaterThan(actualDelta, 2, name)
            XCTAssertGreaterThan(controlCount, 0, name); XCTAssertGreaterThan(actualCount, 0, name)
            mutations.append(["name": name, "hookCalls": calls, "rgbaSHA256": digest(Data(mutated)),
                "maximumDifferenceFromControl": controlDelta, "maximumDifferenceFromUnmutated": actualDelta,
                "differentPixelsFromControl": controlCount, "differentPixelsFromUnmutated": actualCount])
        }
        let record: [String: Any] = ["schema": "Celluloid.NativeTextContract.1", "case": "manufactured-affine",
            "sourcePNG_SHA256": digest(sourcePNG), "actualPNG_SHA256": digest(try RasterCodec.encode(actualImage, as: .png)),
            "actualRGBA_SHA256": digest(Data(actual)), "controlRGBA_SHA256": digest(Data(control)),
            "maximumChannelDifference": difference, "differentPixels": differingPixels(actual, control), "comparedBytes": actual.count,
            "text": qualifiedText, "utf16": Array(qualifiedText.utf16).map(Int.init), "filter": "Fade", "referenceCanvas": [480, 640],
            "bubble": ["asset": "say1", "center": [240, 320], "bounds": [0, 0, 180, 96], "affine": [1.5, 0.25, -0.25, 1.5, 10, -4]] as [String: Any],
            "sticker": ["asset": "32", "center": [44, -12], "bounds": [2, 3, 72, 80], "affine": [0.5, 0, 0, 0.75, 0, 0]] as [String: Any],
            "sourceSpans": metadata.ranges.map { [$0.location, $0.length] }, "baselines": metadata.baselines,
            "fontSize": metadata.fontSize, "lineHeight": layout.lineHeight,
            "textRect": [77.231, 26.24, 27.875, 43.52], "backingPixels": [56, 88], "backingScale": 2,
            "destination": [metadata.destination.minX, metadata.destination.minY, metadata.destination.width, metadata.destination.height],
            "control": ["kind": "independent-appkit-per-line-and-literal-affine", "provenance": "52bf natural AppKit metrics plus frozen original UIKit whitespace placement",
                "api": "NSLayoutManager.drawGlyphs", "fontSize": 10, "lineText": ["Hello,", " 世界 ", "🎬"],
                "localBaselines": [13.76, 25.76, 37.76], "backingPixels": [56, 88], "backingScale": 2] as [String: Any],
            "mutations": mutations]
        print("MAC_NATIVE_TEXT_CONTRACT " + String(decoding: try JSONSerialization.data(withJSONObject: record, options: [.sortedKeys]), as: UTF8.self))
        #else
        XCTFail("The required production-path fault-injection qualification must run in Debug")
        #endif
    }
    private func observeGlyphBaselines(text: String, rect: CGRect, sourcePNG: Data,
                                       actualComposite: CGImage, oracle: CGImage) throws {
        let layout = try MacPhotoTextLayout.make(text, rect: rect)
        let replay = try MacPhotoTextRaster.make(layout, bounds: rect.size)
        let lines = CTFrameGetLines(layout.frame) as! [CTLine]
        var origins = [CGPoint](repeating: .zero, count: lines.count)
        CTFrameGetLineOrigins(layout.frame, CFRange(location: 0, length: 0), &origins)
        func matrix(_ t: CGAffineTransform) -> [CGFloat] { [t.a, t.b, t.c, t.d, t.tx, t.ty] }
        func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
        var nativeLines: [[String: Any]] = []
        for (index, line) in lines.enumerated() {
            var runs: [[String: Any]] = []
            for run in CTLineGetGlyphRuns(line) as! [CTRun] {
                let count = CTRunGetGlyphCount(run)
                guard count > 0, count <= 32 else { continue }
                var glyphs = [CGGlyph](repeating: 0, count: count)
                var positions = [CGPoint](repeating: .zero, count: count)
                var indices = [CFIndex](repeating: 0, count: count)
                CTRunGetGlyphs(run, CFRange(location: 0, length: 0), &glyphs)
                CTRunGetPositions(run, CFRange(location: 0, length: 0), &positions)
                CTRunGetStringIndices(run, CFRange(location: 0, length: 0), &indices)
                let attributes = CTRunGetAttributes(run) as NSDictionary
                let font = attributes[kCTFontAttributeName] as! CTFont
                var baselineAttributes: [String: String] = [:]
                for key in attributes.allKeys {
                    let name = String(describing: key)
                    if name.lowercased().contains("baseline"), let value = attributes[key] {
                        baselineAttributes[name] = String(String(describing: value).prefix(1000))
                    }
                }
                let range = CTRunGetStringRange(run)
                runs.append(["font": CTFontCopyPostScriptName(font) as String, "size": CTFontGetSize(font),
                    "ascent": CTFontGetAscent(font), "descent": CTFontGetDescent(font),
                    "fontMatrix": matrix(CTFontGetMatrix(font)), "runTextMatrix": matrix(CTRunGetTextMatrix(run)),
                    "range": [range.location, range.length], "glyphs": glyphs.map(Int.init),
                    "positionsFromCTRunGetPositions": positions.map { [$0.x, $0.y] },
                    "stringIndices": indices, "baselineAttributes": baselineAttributes])
            }
            let range = CTLineGetStringRange(line)
            nativeLines.append(["range": [range.location, range.length],
                "frameLineOrigin": [origins[index].x, origins[index].y], "runs": runs])
        }
        func imageRecord(_ image: CGImage, role: String) throws -> [String: Any] {
            let png = try RasterCodec.encode(image, as: .png)
            guard png.count <= 30_000 else { throw NSError(domain: "NativeGlyphObservation", code: 1) }
            return ["role": role, "width": image.width, "height": image.height,
                "bitsPerComponent": image.bitsPerComponent, "bitsPerPixel": image.bitsPerPixel,
                "alphaInfo": image.alphaInfo.rawValue, "bitmapInfo": image.bitmapInfo.rawValue,
                "colorSpace": String(describing: image.colorSpace?.name),
                "pngSHA256": digest(png), "pngBase64": png.base64EncodedString()]
        }
        let a = try pixels(replay), b = try pixels(oracle)
        XCTAssertEqual(a.count, b.count)
        var rgbMaximum = 0, alphaMaximum = 0, rgbPixels = 0, alphaPixels = 0
        for index in stride(from: 0, to: min(a.count, b.count), by: 4) {
            let alpha = abs(Int(a[index + 3]) - Int(b[index + 3]))
            let rgb = (0..<3).map { abs(Int(a[index + $0]) - Int(b[index + $0])) }.max() ?? 0
            alphaMaximum = max(alphaMaximum, alpha); rgbMaximum = max(rgbMaximum, rgb)
            if alpha > 2 { alphaPixels += 1 }; if rgb > 2 { rgbPixels += 1 }
        }
        let record: [String: Any] = ["schema": "Celluloid.NativeGlyphObservation.1", "acceptance": false,
            "text": text, "sourcePNG_SHA256": digest(sourcePNG),
            "actualCompositePNG_SHA256": digest(try RasterCodec.encode(actualComposite, as: .png)),
            "actualTextRect": [rect.minX, rect.minY, rect.width, rect.height],
            "frameAllocationHeight": layout.height, "naturalBlockHeight": layout.typographicHeight,
            "fontSize": layout.fontSize, "lineHeight": layout.lineHeight, "backingScale": MacPhotoTextRaster.scale,
            "coreTextLines": nativeLines, "oracleLines": observedOracleLines,
            "images": [try imageRecord(replay, role: "replayed-production-backing"),
                       try imageRecord(oracle, role: "exact-appkit-oracle-backing")],
            "isolatedMetrics": ["premultipliedRGBMaximum": rgbMaximum, "alphaMaximum": alphaMaximum,
                "premultipliedRGBPixelsAbove2": rgbPixels, "alphaPixelsAbove2": alphaPixels],
            "scope": "Diagnostic only. Exact oracle backing; production helper replay at actual computed bounds. Frame origins, glyph offsets and draw-hook locations are distinct observations, not interchangeable baselines."]
        let data = try JSONSerialization.data(withJSONObject: record, options: [.sortedKeys])
        guard data.count <= 100_000 else { throw NSError(domain: "NativeGlyphObservation", code: 2) }
        print("MAC_NATIVE_GLYPH_OBSERVATION " + String(decoding: data, as: UTF8.self))
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

/// Passive public draw-hook observation; always forwards the original arguments.
private final class NativeOracleGlyphObserver: NSLayoutManager {
    var observations: [[String: Any]] = []
    override func showCGGlyphs(_ glyphs: UnsafePointer<CGGlyph>, positions: UnsafePointer<CGPoint>,
        count glyphCount: Int, font: NSFont, textMatrix: CGAffineTransform,
        attributes: [NSAttributedString.Key: Any], in context: CGContext) {
        let ctm = context.ctm
        observations.append(["font": font.fontName, "size": font.pointSize,
            "ascender": font.ascender, "descender": font.descender,
            "glyphs": Array(UnsafeBufferPointer(start: glyphs, count: glyphCount)).map(Int.init),
            "positions": Array(UnsafeBufferPointer(start: positions, count: glyphCount)).map { [$0.x, $0.y] },
            "textMatrix": [textMatrix.a, textMatrix.b, textMatrix.c, textMatrix.d, textMatrix.tx, textMatrix.ty],
            "contextCTM": [ctm.a, ctm.b, ctm.c, ctm.d, ctm.tx, ctm.ty]])
        super.showCGGlyphs(glyphs, positions: positions, count: glyphCount, font: font,
            textMatrix: textMatrix, attributes: attributes, in: context)
    }
}
