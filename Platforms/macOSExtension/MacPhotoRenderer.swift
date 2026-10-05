import Foundation
import AppKit
import CoreGraphics
import CoreText
import UniformTypeIdentifiers
import CelluloidDomain
import CelluloidRendering

/// Serializes whole extension render jobs, not just filter work, to bound raster
/// allocations across superseded previews and host output preparation.
actor MacPhotoRenderQueue {
    static let shared = MacPhotoRenderQueue()
    private let renderer = MacPhotoRenderer()
    func preview(_ adjustment: MacPhotoAdjustment, source: SourceImage, bytes: Data) throws -> CGImage {
        try Task.checkCancellation()
        return try autoreleasepool { try renderer.render(adjustment, source: source, bytes: bytes, maximumDimension: 1400) }
    }
    func export(_ adjustment: MacPhotoAdjustment, source: SourceImage, bytes: Data) throws -> Data {
        try Task.checkCancellation()
        try MacPhotoRenderer.requireQualifiedPhotosOutput(adjustment)
        return try autoreleasepool {
            let image = try renderer.render(adjustment, source: source, bytes: bytes)
            try Task.checkCancellation()
            return try RasterCodec.encode(image, as: .jpeg)
        }
    }
}

/// Replays the shipped AttachView geometry: 16pt chrome inset, aspect-fit
/// artwork, full affine transform, bubbles before stickers, and the original
/// per-bubble text area. No lossy decomposition to rotation/normalized widths.
final class MacPhotoRenderer {
    private let filters = RecipeRenderer()
    #if DEBUG
    /// Test-only fault injection at the actual text compositing operations.
    /// Default nil; neither this seam nor its calls exist in Release builds.
    struct TextRenderProbe {
        var content: ((String) -> String)?
        var destination: ((CGRect, CGRect) -> CGRect)?
        var clip: ((CGRect) -> CGRect)?
    }
    var textRenderProbe: TextRenderProbe?
    #endif

    /// Keep the experimental layer compositor available to the independent
    /// UIKit qualification tests, but never replace a Photos raster with it.
    /// The actual manufactured-affine fixture failed that gate (243 > 2).
    /// Remove this restriction only after source-bound UIKit parity is proved.
    static func requireQualifiedPhotosOutput(_ adjustment: MacPhotoAdjustment) throws {
        guard adjustment.layers.isEmpty else { throw MacPhotoRenderQualificationError.layeredPhotosOutput }
    }

    func render(_ adjustment: MacPhotoAdjustment, source: SourceImage, bytes: Data, maximumDimension: Int? = nil) throws -> CGImage {
        try adjustment.requireEditableCanvas(); try Task.checkCancellation()
        var base = EditRecipe(); base.sources = [source]; base.canvasWidth = source.pixelWidth
        base.canvasHeight = source.pixelHeight; base.filter = adjustment.filter
        let filtered = try filters.render(base, sources: [source.id: bytes], maximumDimension: maximumDimension)
        guard !adjustment.layers.isEmpty else { return filtered }
        guard let reference = adjustment.referenceCanvas else { throw RecipeError.invalidGeometry }
        let canvas = try RasterCodec.bitmap(width: filtered.width, height: filtered.height)
        canvas.draw(filtered, in: CGRect(x: 0, y: 0, width: filtered.width, height: filtered.height))
        canvas.translateBy(x: 0, y: CGFloat(filtered.height)); canvas.scaleBy(x: 1, y: -1)
        canvas.scaleBy(x: CGFloat(filtered.width) / reference.width, y: CGFloat(filtered.height) / reference.height)
        for layer in adjustment.layers {
            try Task.checkCancellation()
            try draw(layer, in: canvas)
        }
        try Task.checkCancellation()
        guard let result = canvas.makeImage() else { throw RenderError.renderFailed }
        return result
    }
    static func artworkRect(bounds: CGRect, imageWidth: Int, imageHeight: Int) -> CGRect? {
        let box = bounds.insetBy(dx: 16, dy: 16)
        guard box.width > 0, box.height > 0, imageWidth > 0, imageHeight > 0 else { return nil }
        let scale = min(box.width / CGFloat(imageWidth), box.height / CGFloat(imageHeight))
        let size = CGSize(width: CGFloat(imageWidth) * scale, height: CGFloat(imageHeight) * scale)
        return CGRect(x: box.midX - size.width / 2, y: box.midY - size.height / 2, width: size.width, height: size.height)
    }
    /// BubbleLabel uses UIImageView.imageRect, not the fractional rectangle that
    /// UIImageView uses to draw its artwork. Match that helper's Float scale and
    /// independently rounded local origin/size before applying the text insets.
    static func bubbleTextRect(bounds: CGRect, imageWidth: Int, imageHeight: Int, area: [Double]) -> CGRect? {
        let box = bounds.insetBy(dx: 16, dy: 16)
        guard box.width > 0, box.height > 0, imageWidth > 0, imageHeight > 0,
              area.count == 4, area.allSatisfy(\.isFinite) else { return nil }
        let scale = CGFloat(min(Float(box.width / CGFloat(imageWidth)), Float(box.height / CGFloat(imageHeight))))
        let width = CGFloat(imageWidth) * scale, height = CGFloat(imageHeight) * scale
        let rect = CGRect(x: box.minX + ((box.width - width) / 2).rounded(),
                          y: box.minY + ((box.height - height) / 2).rounded(),
                          width: width.rounded(), height: height.rounded())
        return CGRect(x: rect.minX + rect.width * area[2] / 100 + 4,
                      y: rect.minY + rect.height * area[0] / 100,
                      width: rect.width * (area[3] - area[2]) / 100 - 4,
                      height: rect.height * (area[1] - area[0]) / 100)
    }
    private func draw(_ layer: MacPhotoLayer, in canvas: CGContext) throws {
        let image: CGImage
        if layer.kind == .bubble { image = try NativeResources.legacyPhotosBubbleImage(named: layer.asset) }
        else { image = try NativeResources.image(named: layer.asset) }
        guard let rect = Self.artworkRect(bounds: layer.bounds, imageWidth: image.width, imageHeight: image.height) else { return }
        canvas.saveGState(); defer { canvas.restoreGState() }
        canvas.translateBy(x: layer.center.x, y: layer.center.y)
        canvas.concatenate(layer.transform)
        canvas.translateBy(x: -layer.bounds.midX, y: -layer.bounds.midY)
        canvas.saveGState()
        canvas.translateBy(x: rect.minX, y: rect.maxY); canvas.scaleBy(x: 1, y: -1)
        canvas.draw(image, in: CGRect(origin: .zero, size: rect.size))
        canvas.restoreGState()
        if layer.kind == .bubble && !layer.text.isEmpty {
            let area = try NativeResources.bubbleArea(named: layer.asset)
            guard let textRect = Self.bubbleTextRect(bounds: layer.bounds, imageWidth: image.width,
                                               imageHeight: image.height, area: area) else { throw RecipeError.invalidGeometry }
            #if DEBUG
            let content = textRenderProbe?.content?(layer.text) ?? layer.text
            #else
            let content = layer.text
            #endif
            let layout = try MacPhotoTextLayout.make(content, rect: textRect)
            let text = try MacPhotoTextRaster.makeBacking(layout, bounds: textRect.size)
            let intrinsic = MacPhotoTextRaster.destinationRect(for: text, origin: textRect.origin)
            #if DEBUG
            let destination = textRenderProbe?.destination?(intrinsic, textRect) ?? intrinsic
            #else
            let destination = intrinsic
            #endif
            canvas.saveGState(); defer { canvas.restoreGState() }
            #if DEBUG
            if let clip = textRenderProbe?.clip { canvas.clip(to: clip(destination)) }
            #endif
            // Allocation rounds outward to whole backing pixels. Preserve their
            // intrinsic point size: fitting 28x44pt into 27.875x43.52pt would add
            // an unrequested scale and compress every subsequent baseline.
            // The layout was already centered in its logical text rectangle.
            canvas.translateBy(x: destination.minX, y: destination.maxY)
            canvas.scaleBy(x: 1, y: -1)
            canvas.draw(text.image, in: CGRect(origin: .zero, size: destination.size))
        }
    }
}

enum MacPhotoRenderQualificationError: Error, LocalizedError {
    case layeredPhotosOutput
    var errorDescription: String? {
        NSLocalizedString("Sticker and bubble editing is temporarily unavailable in Photos while cross-platform rendering is verified. Existing edits and the original photo are unchanged.", comment: "Unqualified Photos layer rendering")
    }
}

/// Matches the finite 16...2pt search in the shipped BubbleLabel. Platform font
/// rasterization/UILabel vertical metrics remain an independent UIKit oracle gate.
struct MacPhotoTextLayout {
    let frame: CTFrame
    let height: CGFloat // Core Text frame allocation, including its fitting margin.
    let typographicHeight: CGFloat // Natural line block; independent of frame allocation.
    let fontSize: CGFloat
    let font: CTFont
    let lineHeight: CGFloat
    static func make(_ text: String, rect: CGRect) throws -> Self {
        guard text.utf8.count <= 16_384, rect.width > 0, rect.height > 0 else { throw RenderError.textDoesNotFit }
        let nativeMetrics = NSLayoutManager()
        nativeMetrics.backgroundLayoutEnabled = false
        for size in stride(from: 16, through: 2, by: -1) {
            try Task.checkCancellation()
            let font = CTFontCreateUIFontForLanguage(.system, CGFloat(size), nil) ?? CTFontCreateWithName("Helvetica" as CFString, CGFloat(size), nil)
            // Use the native typesetter's natural pitch rather than adding raw
            // font ascent/descent. Independent AppKit evidence reports 12pt at
            // 10pt; the raw 11.77734375 sum visibly crowded later lines/emoji.
            // Keep CoreText's legacy character wrapping and whitespace spans.
            let lineHeight = nativeMetrics.defaultLineHeight(for: NSFont.systemFont(ofSize: CGFloat(size)))
            guard lineHeight.isFinite, lineHeight > 0 else { throw RenderError.textDoesNotFit }
            func setter(centered: Bool) -> CTFramesetter {
                var wrap = CTLineBreakMode.byCharWrapping
                var alignment: CTTextAlignment = centered ? .center : .left
                var fixedLineHeight = lineHeight
                let paragraph = withUnsafePointer(to: &wrap) { wrapPointer in
                    withUnsafePointer(to: &alignment) { alignmentPointer in
                        withUnsafePointer(to: &fixedLineHeight) { heightPointer in
                            let settings = [CTParagraphStyleSetting(spec: .lineBreakMode, valueSize: MemoryLayout<CTLineBreakMode>.size, value: wrapPointer),
                                            CTParagraphStyleSetting(spec: .alignment, valueSize: MemoryLayout<CTTextAlignment>.size, value: alignmentPointer),
                                            CTParagraphStyleSetting(spec: .minimumLineHeight, valueSize: MemoryLayout<CGFloat>.size, value: heightPointer),
                                            CTParagraphStyleSetting(spec: .maximumLineHeight, valueSize: MemoryLayout<CGFloat>.size, value: heightPointer)]
                            return CTParagraphStyleCreate(settings, settings.count)
                        }
                    }
                }
                let string = NSAttributedString(string: text, attributes: [
                    NSAttributedString.Key(kCTFontAttributeName as String): font,
                    NSAttributedString.Key(kCTForegroundColorAttributeName as String): CGColor(gray: 0, alpha: 1),
                    NSAttributedString.Key(kCTParagraphStyleAttributeName as String): paragraph])
                return CTFramesetterCreateWithAttributedString(string as CFAttributedString)
            }
            var framesetter = setter(centered: false)
            let measured = CTFramesetterSuggestFrameSizeWithConstraints(framesetter, CFRange(location: 0, length: 0), nil,
                CGSize(width: rect.width, height: 1_000_000), nil)
            guard measured.height < rect.height || size == 2 else { continue }
            let height = ceil(measured.height)
            guard height > 0, height <= rect.height else { throw RenderError.textDoesNotFit }
            if floor(measured.height / lineHeight) == 1 { framesetter = setter(centered: true) }
            let frame = CTFramesetterCreateFrame(framesetter, CFRange(location: 0, length: 0), CGPath(rect: CGRect(x: 0, y: 0, width: rect.width, height: height), transform: nil), nil)
            guard CTFrameGetVisibleStringRange(frame).length == (text as NSString).length else { throw RenderError.textDoesNotFit }
            let typographicHeight = CGFloat(CFArrayGetCount(CTFrameGetLines(frame))) * lineHeight
            guard typographicHeight.isFinite, typographicHeight > 0, typographicHeight <= rect.height else { continue }
            return Self(frame: frame, height: height, typographicHeight: typographicHeight,
                        fontSize: CGFloat(size), font: font, lineHeight: lineHeight)
        }
        throw RenderError.textDoesNotFit
    }
}

enum MacPhotoTextRaster {
    static let scale: CGFloat = 2
    struct Backing {
        let image: CGImage
        /// Top-left of the retained pixels in the original logical label space.
        /// A negative value is allocation compensation, never a baseline offset.
        let origin: CGPoint
    }

    static func destinationRect(for backing: Backing, origin: CGPoint) -> CGRect {
        CGRect(x: origin.x + backing.origin.x, y: origin.y + backing.origin.y,
               width: CGFloat(backing.image.width) / scale, height: CGFloat(backing.image.height) / scale)
    }

    /// Retain the logical backing plus every painted pixel. Measure using the
    /// identical glyph path on a bounded, pixel-aligned guard surface, then crop
    /// without resampling. No font fitting, shaping, positions or baselines change.
    static func makeBacking(_ layout: MacPhotoTextLayout, bounds: CGSize) throws -> Backing {
        let padding = try backingPadding(layout, bounds: bounds)
        return try autoreleasepool {
            let expanded = try make(layout, bounds: bounds, padding: padding)
            let ink = try inkPixelBounds(expanded)
            let full = CGRect(x: 0, y: 0, width: expanded.width, height: expanded.height)
            // Public metrics are a conservative probe envelope, not a claim that
            // outline bounds equal raster coverage (especially for color fonts).
            // Fail closed if the probe itself shows any possible edge clipping.
            guard ink.isNull || full.insetBy(dx: 1, dy: 1).contains(ink) else { throw RecipeError.resourceLimit }
            let logical = CGRect(x: padding * scale, y: padding * scale,
                                 width: ceil(bounds.width * scale), height: ceil(bounds.height * scale))
            // Keep one fully transparent edge pixel around measured ink so
            // transformed image interpolation cannot clamp a nonzero edge.
            let retained = logical.union(ink.isNull ? ink : ink.insetBy(dx: -1, dy: -1))
            guard let image = expanded.cropping(to: retained) else { throw RenderError.renderFailed }
            return Backing(image: image, origin: CGPoint(x: (retained.minX - logical.minX) / scale,
                                                        y: (retained.minY - logical.minY) / scale))
        }
    }

    /// Bound the probe with the actual run fonts and glyphs, including the whole
    /// font box for non-outline/color glyphs. Two extra pixels cover raster edges;
    /// only measured nonzero alpha, not this conservative box, expands the result.
    static func backingPadding(_ layout: MacPhotoTextLayout, bounds: CGSize) throws -> CGFloat {
        guard bounds.width.isFinite, bounds.height.isFinite, bounds.width > 0, bounds.height > 0,
              bounds.width * scale <= 4096, bounds.height * scale <= 4096,
              ceil(bounds.width * scale) * ceil(bounds.height * scale) <= 4_194_304 else { throw RecipeError.resourceLimit }
        let logical = CGRect(x: 0, y: 0, width: ceil(bounds.width * scale) / scale,
                             height: ceil(bounds.height * scale) / scale)
        var envelope = logical
        for run in try glyphRuns(layout, bounds: bounds, padding: 0) {
            try Task.checkCancellation()
            for (glyph, position) in zip(run.glyphs, run.positions) {
                let box = run.font.boundingRectForFont.union(run.font.boundingRect(forCGGlyph: glyph))
                    .applying(run.textMatrix).offsetBy(dx: position.x, dy: position.y)
                guard !box.isNull, !box.isInfinite,
                      [box.minX, box.minY, box.maxX, box.maxY].allSatisfy(\.isFinite) else { throw RecipeError.resourceLimit }
                envelope = envelope.union(box)
            }
        }
        let overhang = [CGFloat(0), -envelope.minX, -envelope.minY,
                        envelope.maxX - logical.maxX, envelope.maxY - logical.maxY].max() ?? 0
        let padding = ceil(overhang * scale + 2) / scale
        guard padding.isFinite, padding <= 64 else { throw RecipeError.resourceLimit }
        return padding
    }

    /// Validate only bytes addressed by RGBA pixels, not unused trailing padding.
    /// A cropped subimage may retain the parent's row stride without a complete
    /// final padding row. No pixel access occurs until this checked span fits.
    static func rgbaStorageSpan(width: Int, height: Int, bytesPerRow: Int, dataCount: Int) throws -> Int {
        guard width > 0, height > 0, width <= 4096, height <= 4096,
              width * height <= 4_194_304, bytesPerRow > 0, dataCount >= 0 else { throw RecipeError.resourceLimit }
        let (pixelBytes, pixelOverflow) = width.multipliedReportingOverflow(by: 4)
        guard !pixelOverflow, bytesPerRow >= pixelBytes else { throw RenderError.renderFailed }
        let (prefix, prefixOverflow) = (height - 1).multipliedReportingOverflow(by: bytesPerRow)
        let (span, spanOverflow) = prefix.addingReportingOverflow(pixelBytes)
        guard !prefixOverflow, !spanOverflow, span <= 4_194_304 * 4, dataCount >= span else { throw RenderError.renderFailed }
        return span
    }

    /// The owned bitmap is 8-bit integer premultiplied RGBA. Read image rows in
    /// their declared stride so the result uses CGImage cropping coordinates.
    static func inkPixelBounds(_ image: CGImage) throws -> CGRect {
        let order = image.bitmapInfo.intersection(.byteOrderMask)
        guard image.bitsPerComponent == 8, image.bitsPerPixel == 32, image.alphaInfo == .premultipliedLast,
              !image.bitmapInfo.contains(.floatComponents), order == .byteOrderDefault || order == .byteOrder32Big,
              let data = image.dataProvider?.data, let bytes = CFDataGetBytePtr(data) else { throw RenderError.renderFailed }
        _ = try rgbaStorageSpan(width: image.width, height: image.height, bytesPerRow: image.bytesPerRow,
                                dataCount: CFDataGetLength(data))
        var left = image.width, top = image.height, right = 0, bottom = 0
        for row in 0..<image.height {
            try Task.checkCancellation()
            for column in 0..<image.width where bytes[row * image.bytesPerRow + column * 4 + 3] != 0 {
                left = min(left, column); top = min(top, row)
                right = max(right, column + 1); bottom = max(bottom, row + 1)
            }
        }
        return right > left && bottom > top ? CGRect(x: left, y: top, width: right - left, height: bottom - top) : .null
    }

    /// Raw same-path surface for the coverage probe and native diagnostics.
    /// Compositing must use makeBacking so retained overhang carries its origin.
    static func make(_ layout: MacPhotoTextLayout, bounds: CGSize, padding: CGFloat = 0) throws -> CGImage {
        guard padding.isFinite, padding >= 0, padding <= 64,
              bounds.width.isFinite, bounds.height.isFinite, bounds.width > 0, bounds.height > 0 else { throw RecipeError.resourceLimit }
        let width = ceil((bounds.width + 2 * padding) * scale), height = ceil((bounds.height + 2 * padding) * scale)
        guard width.isFinite, height.isFinite, width > 0, height > 0,
              width <= 4096, height <= 4096, width * height <= 4_194_304 else { throw RecipeError.resourceLimit }
        return try autoreleasepool {
            let bitmap = try RasterCodec.bitmap(width: Int(width), height: Int(height))
            let runs = try glyphRuns(layout, bounds: bounds, padding: padding)
            bitmap.translateBy(x: 0, y: height); bitmap.scaleBy(x: scale, y: -scale)
            let graphics = NSGraphicsContext(cgContext: bitmap, flipped: true)
            NSGraphicsContext.saveGraphicsState()
            defer { NSGraphicsContext.restoreGraphicsState() }
            NSGraphicsContext.current = graphics
            // Apple permits isolated layout managers on secondary threads when
            // background layout is off and no text view is attached. No object
            // escapes this synchronous render or is shared with another job.
            let manager = NSLayoutManager(); manager.backgroundLayoutEnabled = false
            for run in runs {
                try Task.checkCancellation()
                bitmap.saveGState(); defer { bitmap.restoreGState() }
                run.font.set(in: graphics)
                bitmap.setFillColor(CGColor(gray: 0, alpha: 1))
                bitmap.textMatrix = run.textMatrix
                let attributes: [NSAttributedString.Key: Any] = [.font: run.font, .foregroundColor: NSColor.black]
                run.glyphs.withUnsafeBufferPointer { glyphs in
                    run.positions.withUnsafeBufferPointer { positions in
                        manager.showCGGlyphs(glyphs.baseAddress!, positions: positions.baseAddress!, count: glyphs.count,
                            font: run.font, textMatrix: run.textMatrix, attributes: attributes, in: bitmap)
                    }
                }
            }
            guard let image = bitmap.makeImage() else { throw RenderError.renderFailed }
            return image
        }
    }

    struct GlyphRun {
        let font: NSFont
        let glyphs: [CGGlyph]
        let positions: [CGPoint]
        let textMatrix: CGAffineTransform
        let sourceRange: CFRange
        let stringIndices: [CFIndex]
    }

    /// Reuse the shaped CoreText stream. Never slice/re-layout strings: that can
    /// change contextual forms, bidi levels, variation selectors or ZWJ clusters.
    static func glyphRuns(_ layout: MacPhotoTextLayout, bounds: CGSize, padding: CGFloat) throws -> [GlyphRun] {
        let lines = CTFrameGetLines(layout.frame) as! [CTLine]
        var origins = [CGPoint](repeating: .zero, count: lines.count)
        CTFrameGetLineOrigins(layout.frame, CFRange(location: 0, length: 0), &origins)
        let top = padding + layout.height + (bounds.height - layout.typographicHeight) / 2
        var result: [GlyphRun] = []
        for (index, line) in lines.enumerated() {
            try Task.checkCancellation()
            for run in CTLineGetGlyphRuns(line) as! [CTRun] {
                let count = CTRunGetGlyphCount(run)
                if count == 0 { continue } // Blank/control-only lines retain layout and consume no ink.
                let attributes = CTRunGetAttributes(run) as NSDictionary
                // CTFont and NSFont are documented toll-free counterparts; do
                // not recreate a font by name and lose fallback/variation data.
                guard let font = attributes[kCTFontAttributeName] as? NSFont else { throw RenderError.renderFailed }
                var glyphs = [CGGlyph](repeating: 0, count: count)
                var positions = [CGPoint](repeating: .zero, count: count)
                var indices = [CFIndex](repeating: 0, count: count)
                CTRunGetGlyphs(run, CFRange(location: 0, length: 0), &glyphs)
                CTRunGetPositions(run, CFRange(location: 0, length: 0), &positions)
                CTRunGetStringIndices(run, CFRange(location: 0, length: 0), &indices)
                positions = positions.map { CGPoint(x: padding + origins[index].x + $0.x, y: top - origins[index].y - $0.y) }
                let source = CTRunGetTextMatrix(run)
                // AppKit text space is reflected under its flipped user space.
                // showCGGlyphs uses supplied positions instead of matrix tx/ty.
                let matrix = CGAffineTransform(a: source.a, b: -source.b, c: source.c, d: -source.d, tx: 0, ty: 0)
                result.append(GlyphRun(font: font, glyphs: glyphs, positions: positions,
                    textMatrix: matrix, sourceRange: CTRunGetStringRange(run), stringIndices: indices))
            }
        }
        return result
    }

}
