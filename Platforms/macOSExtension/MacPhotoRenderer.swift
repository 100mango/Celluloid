import Foundation
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
            try Self.draw(layer, in: canvas)
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
    private static func draw(_ layer: MacPhotoLayer, in canvas: CGContext) throws {
        let image = try NativeResources.image(named: layer.asset)
        guard let rect = artworkRect(bounds: layer.bounds, imageWidth: image.width, imageHeight: image.height) else { return }
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
            let textRect = CGRect(x: rect.minX + rect.width * area[2] / 100 + 4,
                                  y: rect.minY + rect.height * area[0] / 100,
                                  width: rect.width * (area[3] - area[2]) / 100 - 4,
                                  height: rect.height * (area[1] - area[0]) / 100)
            let layout = try MacPhotoTextLayout.make(layer.text, rect: textRect)
            canvas.saveGState(); defer { canvas.restoreGState() }
            canvas.translateBy(x: textRect.minX, y: textRect.midY + layout.height / 2)
            canvas.scaleBy(x: 1, y: -1); canvas.textMatrix = .identity
            CTFrameDraw(layout.frame, canvas)
        }
    }
}

/// Matches the finite 16...2pt search in the shipped BubbleLabel. Platform font
/// rasterization/UILabel vertical metrics remain an independent UIKit oracle gate.
struct MacPhotoTextLayout {
    let frame: CTFrame
    let height: CGFloat
    let fontSize: CGFloat
    static func make(_ text: String, rect: CGRect) throws -> Self {
        guard text.utf8.count <= 16_384, rect.width > 0, rect.height > 0 else { throw RenderError.textDoesNotFit }
        for size in stride(from: 16, through: 2, by: -1) {
            try Task.checkCancellation()
            let font = CTFontCreateUIFontForLanguage(.system, CGFloat(size), nil) ?? CTFontCreateWithName("Helvetica" as CFString, CGFloat(size), nil)
            func setter(centered: Bool) -> CTFramesetter {
                var wrap = CTLineBreakMode.byCharWrapping
                var alignment: CTTextAlignment = centered ? .center : .left
                let paragraph = withUnsafePointer(to: &wrap) { wrapPointer in
                    withUnsafePointer(to: &alignment) { alignmentPointer in
                        let settings = [CTParagraphStyleSetting(spec: .lineBreakMode, valueSize: MemoryLayout<CTLineBreakMode>.size, value: wrapPointer),
                                        CTParagraphStyleSetting(spec: .alignment, valueSize: MemoryLayout<CTTextAlignment>.size, value: alignmentPointer)]
                        return CTParagraphStyleCreate(settings, settings.count)
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
            let lineHeight = CTFontGetAscent(font) + CTFontGetDescent(font) + CTFontGetLeading(font)
            if floor(measured.height / lineHeight) == 1 { framesetter = setter(centered: true) }
            let frame = CTFramesetterCreateFrame(framesetter, CFRange(location: 0, length: 0), CGPath(rect: CGRect(x: 0, y: 0, width: rect.width, height: height), transform: nil), nil)
            guard CTFrameGetVisibleStringRange(frame).length == (text as NSString).length else { throw RenderError.textDoesNotFit }
            return Self(frame: frame, height: height, fontSize: CGFloat(size))
        }
        throw RenderError.textDoesNotFit
    }
}
