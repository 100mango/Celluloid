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
            let text = try MacPhotoTextRaster.make(layout, bounds: textRect.size)
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
            canvas.draw(text, in: CGRect(origin: .zero, size: destination.size))
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
    static func destinationRect(for image: CGImage, origin: CGPoint) -> CGRect {
        CGRect(origin: origin, size: CGSize(width: CGFloat(image.width) / scale, height: CGFloat(image.height) / scale))
    }
    /// Optional padding exercises the identical drawing path to expose any ink
    /// outside the normal backing. The shipping compositor always uses zero.
    static func make(_ layout: MacPhotoTextLayout, bounds: CGSize, padding: CGFloat = 0) throws -> CGImage {
        guard padding.isFinite, padding >= 0, padding <= 64,
              bounds.width.isFinite, bounds.height.isFinite, bounds.width > 0, bounds.height > 0 else { throw RecipeError.resourceLimit }
        let width = ceil((bounds.width + 2 * padding) * scale), height = ceil((bounds.height + 2 * padding) * scale)
        guard width.isFinite, height.isFinite, width > 0, height > 0,
              width <= 4096, height <= 4096, width * height <= 4_194_304 else { throw RecipeError.resourceLimit }
        let bitmap = try RasterCodec.bitmap(width: Int(width), height: Int(height))
        bitmap.scaleBy(x: scale, y: scale)
        // Keep the label's logical bounds separate from its outward-rounded
        // pixel backing. UIKit centers the text in the logical label rectangle.
        // The CT frame may need extra fitting room for descenders. Center the
        // natural line block, keeping that allocation and all CT origins intact.
        // Do not move the first baseline by half the frame's rounding margin.
        bitmap.translateBy(x: padding, y: height / scale - padding - layout.height
                           - (bounds.height - layout.typographicHeight) / 2)
        bitmap.textMatrix = .identity
        CTFrameDraw(layout.frame, bitmap)
        guard let image = bitmap.makeImage() else { throw RenderError.renderFailed }
        return image
    }
}
