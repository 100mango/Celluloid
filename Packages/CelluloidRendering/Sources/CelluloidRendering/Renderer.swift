import Foundation
import CoreGraphics
import CoreImage
import CoreText
import ImageIO
import UniformTypeIdentifiers
import CelluloidDomain

public enum RenderError: Error, LocalizedError {
    case invalidImage, unavailableFilter(String), missingAsset(String), renderFailed, exportFailed, textDoesNotFit, unsupportedSourceFormat
    public var errorDescription: String? {
        switch self {
        case .invalidImage: return NSLocalizedString("This file could not be decoded as an image.", bundle: .module, comment: "Rendering error")
        case .unavailableFilter(let name): return String(format: NSLocalizedString("The %@ filter is unavailable on this device.", bundle: .module, comment: "Rendering error"), name)
        case .missingAsset(let name): return String(format: NSLocalizedString("Required artwork is missing: %@.", bundle: .module, comment: "Rendering error"), name)
        case .renderFailed: return NSLocalizedString("The image could not be rendered. Your original is unchanged.", bundle: .module, comment: "Rendering error")
        case .exportFailed: return NSLocalizedString("The exported image could not be verified.", bundle: .module, comment: "Rendering error")
        case .unsupportedSourceFormat: return NSLocalizedString("RAW, ProRAW and animated images are not supported. Import a still JPEG, PNG or HEIC copy.", bundle: .module, comment: "Rendering error")
        case .textDoesNotFit: return NSLocalizedString("This bubble text does not fit. Shorten the text or make the bubble larger.", bundle: .module, comment: "Rendering error")
        }
    }
}

public enum RasterCodec {
    public static let maxSourceBytes = 64 * 1024 * 1024
    public static let colorSpace = CGColorSpace(name: CGColorSpace.sRGB)!

    public static func metadata(_ data: Data, name: String = "Photo", id: UUID = UUID(), maximumBytes: Int = maxSourceBytes) throws -> SourceImage {
        guard !data.isEmpty, data.count <= maximumBytes else { throw RecipeError.resourceLimit }
        guard let source = CGImageSourceCreateWithData(data as CFData, nil),
              let values = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
              let width = values[kCGImagePropertyPixelWidth] as? Int,
              let height = values[kCGImagePropertyPixelHeight] as? Int else { throw RenderError.invalidImage }
        guard let identifier = CGImageSourceGetType(source) as String?,
              let type = UTType(identifier), !type.conforms(to: .rawImage), CGImageSourceGetCount(source) == 1 else {
            throw RenderError.unsupportedSourceFormat
        }
        let orientation = values[kCGImagePropertyOrientation] as? Int ?? 1
        guard (1...8).contains(orientation) else { throw RenderError.invalidImage }
        let swapped = (5...8).contains(orientation)
        let result = SourceImage(id: id, displayName: name,
                                 pixelWidth: swapped ? height : width, pixelHeight: swapped ? width : height)
        try result.validate()
        return result
    }

    public static func image(_ data: Data) throws -> CIImage {
        let info = try metadata(data)
        try Task.checkCancellation()
        // UIKit's shipped filter path starts from UIImage.cgImage. The actual
        // 9b phone oracle proved ImageIO CGImage inputs exact for both native and
        // legacy graphs, while CIImage(data:) changed Sketch/Comic/face pixels.
        // Keep ImageIO lazy/non-caching, apply file orientation exactly once, and
        // retain the original bytes rather than normalizing the stored document.
        let options = [kCGImageSourceShouldCache: false, kCGImageSourceShouldCacheImmediately: false] as CFDictionary
        guard let source = CGImageSourceCreateWithData(data as CFData, options),
              let values = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
              let cg = CGImageSourceCreateImageAtIndex(source, 0, options) else { throw RenderError.invalidImage }
        let orientation = values[kCGImagePropertyOrientation] as? Int ?? 1
        guard (1...8).contains(orientation) else { throw RenderError.invalidImage }
        try Task.checkCancellation()
        var image = CIImage(cgImage: cg)
        if orientation != 1 { image = image.oriented(forExifOrientation: Int32(orientation)) }
        guard image.extent.width == CGFloat(info.pixelWidth), image.extent.height == CGFloat(info.pixelHeight) else { throw RenderError.invalidImage }
        if image.extent.minX != 0 || image.extent.minY != 0 {
            image = image.transformed(by: CGAffineTransform(translationX: -image.extent.minX, y: -image.extent.minY))
        }
        return image
    }

    public static func bitmap(width: Int, height: Int) throws -> CGContext {
        guard width > 0, height > 0, width <= 16_384, height <= 16_384,
              width * height <= 50_000_000,
              let context = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8,
                                      bytesPerRow: width * 4, space: colorSpace,
                                      bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
            throw RenderError.renderFailed
        }
        context.interpolationQuality = .high
        return context
    }

    /// Encodes and decodes the actual bytes; callers write atomically and read back separately.
    public static func encode(_ image: CGImage, as type: UTType) throws -> Data {
        guard type == .png || type == .jpeg else { throw RenderError.exportFailed }
        var output = image
        if type == .jpeg {
            let context = try bitmap(width: image.width, height: image.height)
            context.setFillColor(CGColor(gray: 1, alpha: 1))
            context.fill(CGRect(x: 0, y: 0, width: image.width, height: image.height))
            context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
            guard let flattened = context.makeImage() else { throw RenderError.exportFailed }
            output = flattened
        }
        let data = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(data, type.identifier as CFString, 1, nil) else {
            throw RenderError.exportFailed
        }
        CGImageDestinationAddImage(destination, output, [kCGImageDestinationLossyCompressionQuality: 0.95] as CFDictionary)
        guard CGImageDestinationFinalize(destination),
              let decoded = CGImageSourceCreateWithData(data as CFData, nil),
              let readback = CGImageSourceCreateImageAtIndex(decoded, 0, nil),
              readback.width == image.width, readback.height == image.height else { throw RenderError.exportFailed }
        return data as Data
    }
}

public enum NativeResources {
    public static func templates(count: Int) throws -> [CollageTemplate] {
        guard let url = Bundle.module.url(forResource: "collage", withExtension: "json") else {
            throw RenderError.missingAsset("collage.json")
        }
        return try CollageTemplates.decode(Data(contentsOf: url), imageCount: count)
    }
    public static func image(named name: String) throws -> CGImage {
        guard StickerAsset(rawValue: name) != nil || BubbleAsset(rawValue: name) != nil,
              let url = Bundle.module.url(forResource: name, withExtension: "png"),
              let source = CGImageSourceCreateWithURL(url as CFURL, nil),
              let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else { throw RenderError.missingAsset(name) }
        return image
    }
    public static func bubbleArea(named name: String) throws -> [Double] {
        guard let url = Bundle.module.url(forResource: "bubble", withExtension: "json"),
              let areas = try? JSONDecoder().decode([String: [Double]].self, from: Data(contentsOf: url)),
              let area = areas[name], area.count == 4, area.allSatisfy({ $0.isFinite && (0...100).contains($0) }) else {
            throw RenderError.missingAsset(name + " text area")
        }
        return area
    }
}

/// No global mutable CIFilter. A render owns its own context and filter graph.
public final class RecipeRenderer {
    private let context = CIContext(options: [.outputColorSpace: RasterCodec.colorSpace, .cacheIntermediates: false])
    private let testFaceRegions: ((CIImage) throws -> [CGRect])?
    public init() { testFaceRegions = nil }
    /// Controlled geometry seam for mask-composition tests; production uses CIDetector.
    init(faceRegions: @escaping (CIImage) throws -> [CGRect]) { testFaceRegions = faceRegions }

    public func render(_ recipe: EditRecipe, sources: [UUID: Data], maximumDimension: Int? = nil) throws -> CGImage {
        try recipe.validate()
        defer { context.clearCaches() }
        guard !recipe.sources.isEmpty else { throw RecipeError.missingSource }
        let scale = maximumDimension.map { min(1, Double(max(1, $0)) / Double(max(recipe.canvasWidth, recipe.canvasHeight))) } ?? 1
        let width = max(1, Int((Double(recipe.canvasWidth) * scale).rounded()))
        let height = max(1, Int((Double(recipe.canvasHeight) * scale).rounded()))
        let canvas = try RasterCodec.bitmap(width: width, height: height)
        let bounds = CGRect(x: 0, y: 0, width: width, height: height)
        let template: CollageTemplate?
        if recipe.sources.count > 1 {
            template = try NativeResources.templates(count: recipe.sources.count).first { $0.assetName == recipe.collageTemplate }
            guard template != nil else { throw RecipeError.invalidDocument }
        } else { template = nil }
        for (index, source) in recipe.sources.enumerated() {
            try autoreleasepool {
            try Task.checkCancellation()
            guard let data = sources[source.id] else { throw RecipeError.missingSource }
            let info = try RasterCodec.metadata(data)
            guard info.pixelWidth == source.pixelWidth, info.pixelHeight == source.pixelHeight else { throw RecipeError.invalidDocument }
            let input = try RasterCodec.image(data)
            let filtered = try apply(recipe.filter, to: input)
            canvas.saveGState()
            defer { canvas.restoreGState(); context.clearCaches() }
            var rect = bounds
            if let polygon = template?.polygons[index] {
                let path = CGMutablePath()
                let points = polygon.map { CGPoint(x: $0.x / 100 * Double(width), y: (1 - $0.y / 100) * Double(height)) }
                path.addLines(between: points); path.closeSubpath()
                rect = path.boundingBoxOfPath
                canvas.addPath(path); canvas.clip()
            }
            let destination = Self.cropRect(imageWidth: source.pixelWidth, imageHeight: source.pixelHeight,
                                            crop: source.crop, in: rect)
            let transform = CGAffineTransform(a: destination.width / input.extent.width, b: 0,
                                              c: 0, d: destination.height / input.extent.height,
                                              tx: destination.minX, ty: destination.minY)
            // Transform and clip the lazy CI graph before materialization. Even at 5× crop,
            // a preview allocates only the visible tile, never the full 48MP intermediary.
            let materializedBounds = rect.integral.intersection(bounds)
            let sampled = filtered.transformed(by: transform).cropped(to: materializedBounds)
            guard let image = context.createCGImage(sampled, from: materializedBounds, format: .RGBA8,
                                                    colorSpace: RasterCodec.colorSpace) else { throw RenderError.renderFailed }
            canvas.draw(image, in: materializedBounds)
            }
        }
        for overlay in recipe.overlays {
            try Task.checkCancellation()
            try draw(overlay, in: canvas, width: Double(width), height: Double(height))
        }
        guard let image = canvas.makeImage() else { throw RenderError.renderFailed }
        return image
    }

    public func apply(_ preset: FilterPreset, to image: CIImage) throws -> CIImage {
        if preset == .original { return image }
        if preset == .pixellateFace { return try pixelateFaces(image) }
        guard let name = preset.coreImageFilterName,
              let output = CIFilter(name: name, parameters: [kCIInputImageKey: image])?.outputImage else {
            throw RenderError.unavailableFilter(preset.rawValue)
        }
        return output.cropped(to: image.extent)
    }

    private func pixelateFaces(_ image: CIImage) throws -> CIImage {
        let faces: [CGRect]
        if let testFaceRegions { faces = try testFaceRegions(image) }
        else {
            guard let detector = CIDetector(ofType: CIDetectorTypeFace, context: context,
                                            options: [CIDetectorAccuracy: CIDetectorAccuracyHigh]) else {
                throw RenderError.unavailableFilter(FilterPreset.pixellateFace.rawValue)
            }
            faces = detector.features(in: image).map(\.bounds)
        }
        if faces.isEmpty { return image }
        var mask: CIImage?
        for face in faces {
            let radius = min(face.width, face.height / 1.5)
            guard let circle = CIFilter(name: "CIRadialGradient", parameters: [
                "inputRadius0": radius, "inputRadius1": radius + 1,
                "inputColor0": CIColor(red: 1, green: 1, blue: 1, alpha: 1),
                "inputColor1": CIColor(red: 0, green: 0, blue: 0, alpha: 0),
                kCIInputCenterKey: CIVector(x: face.midX, y: face.midY)
            ])?.outputImage else { throw RenderError.unavailableFilter("CIRadialGradient") }
            mask = mask.map { circle.composited(over: $0) } ?? circle
        }
        guard let mask, let pixels = CIFilter(name: "CIPixellate", parameters: [
            kCIInputImageKey: image, kCIInputScaleKey: max(1, max(image.extent.width, image.extent.height) / 60)
        ])?.outputImage,
              let output = CIFilter(name: "CIBlendWithMask", parameters: [
                kCIInputImageKey: pixels, kCIInputBackgroundImageKey: image,
                kCIInputMaskImageKey: mask.cropped(to: image.extent)
              ])?.outputImage else { throw RenderError.unavailableFilter("PixellateFace") }
        return output.cropped(to: image.extent)
    }

    static func cropRect(imageWidth: Int, imageHeight: Int, crop: SourceCrop, in rect: CGRect) -> CGRect {
        let scale = max(rect.width / CGFloat(imageWidth), rect.height / CGFloat(imageHeight)) * crop.zoom
        let size = CGSize(width: CGFloat(imageWidth) * scale, height: CGFloat(imageHeight) * scale)
        // Clamp the desired focal point so every polygon remains covered by its image.
        let x = min(rect.minX, max(rect.maxX - size.width, rect.midX - size.width * crop.centerX))
        let y = min(rect.minY, max(rect.maxY - size.height, rect.midY - size.height * (1 - crop.centerY)))
        return CGRect(x: x, y: y, width: size.width, height: size.height)
    }

    private func draw(_ overlay: Overlay, in canvas: CGContext, width: Double, height: Double) throws {
        let asset = try NativeResources.image(named: overlay.asset)
        let box = CGSize(width: overlay.width * width, height: overlay.height * height)
        let scale = min(box.width / CGFloat(asset.width), box.height / CGFloat(asset.height))
        let size = CGSize(width: CGFloat(asset.width) * scale, height: CGFloat(asset.height) * scale)
        let rect = CGRect(x: -size.width / 2, y: -size.height / 2, width: size.width, height: size.height)
        canvas.saveGState(); defer { canvas.restoreGState() }
        canvas.translateBy(x: overlay.centerX * width, y: (1 - overlay.centerY) * height)
        canvas.rotate(by: -overlay.rotation * .pi / 180)
        canvas.scaleBy(x: overlay.mirrored ? -1 : 1, y: 1)
        canvas.draw(asset, in: rect)
        if overlay.kind == .bubble && !overlay.text.isEmpty {
            let area = try NativeResources.bubbleArea(named: overlay.asset)
            let textRect = CGRect(x: rect.minX + rect.width * area[2] / 100,
                                  y: rect.minY + rect.height * (100 - area[1]) / 100,
                                  width: rect.width * (area[3] - area[2]) / 100,
                                  height: rect.height * (area[1] - area[0]) / 100)
            try drawText(overlay.text, maximumFont: overlay.fontSize * width, in: textRect, canvas: canvas)
        }
    }

    private func drawText(_ text: String, maximumFont: Double, in rect: CGRect, canvas: CGContext) throws {
        let layout = try BoundedTextLayout.make(text: text, maximumFont: maximumFont, rect: rect)
        canvas.textMatrix = .identity
        CTFrameDraw(layout.frame, canvas)
    }
}
