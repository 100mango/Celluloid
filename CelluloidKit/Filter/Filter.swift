//
//  Filter.swift
//  Celluloid
//
//  Created by Mango on 16/3/30.
//  Copyright © 2016年 Mango. All rights reserved.
//

import Foundation
import CoreImage
import UIKit
import CelluloidDomain

public typealias Filter = (CIImage) -> CIImage

precedencegroup FilterCompositionPrecedence {
    associativity: left
}
infix operator >>>: FilterCompositionPrecedence
func >>> (filter1: @escaping Filter, filter2: @escaping Filter) -> Filter {
    return { image in filter2(filter1(image)) }
}

public enum FilterType: String {
    // Raw values are persisted in Photos adjustment data. Do not rename them.
    case Original
    case Sepia
    case Chrome
    case Fade
    case Invert
    case Posterize
    case Sketch
    case Comic
    case Crystal
    case PixellateFace
}

public struct Filters {
    public static func filter(_ type: FilterType) -> Filter {
        switch type {
        case .Original:
            return { $0 }
        case .Sepia:
            return sepia
        case .Chrome:
            return chrome
        case .Fade:
            return fade
        case .Invert:
            return invert
        case .Posterize:
            return posterize
        case .Sketch:
            return sketch
        case .Comic:
            return comic
        case .Crystal:
            return crystal
        case .PixellateFace:
            return pixellateFace()
        }
    }

    private static func simpleFilter(_ name: String) -> Filter {
        return { image in
            // Construct a filter for each call: CIFilter instances are mutable and
            // must not be shared by concurrent preview/export work.
            return CIFilter(name: name, parameters: [kCIInputImageKey: image])?.outputImage ?? image
        }
    }

    public static let sepia = simpleFilter("CISepiaTone")
    public static let chrome = simpleFilter("CIPhotoEffectChrome")
    // The shipped version 1.0 Fade preset used Instant. Preserve saved edits.
    public static let fade = simpleFilter("CIPhotoEffectInstant")
    public static let invert = simpleFilter("CIColorInvert")
    public static let posterize = simpleFilter("CIColorPosterize")
    public static let sketch = simpleFilter("CILineOverlay")
    public static let comic = simpleFilter("CIComicEffect")
    public static let crystal = simpleFilter("CICrystallize")

    public static func pixellate() -> Filter {
        return { image in
            guard hasRenderableExtent(image) else { return image }
            let parameters: [String: Any] = [
                kCIInputImageKey: image,
                kCIInputScaleKey: max(1, max(image.extent.width, image.extent.height) / 60)
            ]
            return CIFilter(name: "CIPixellate", parameters: parameters)?.outputImage ?? image
        }
    }

    public static func sourceOver(_ inputImage: CIImage) -> Filter {
        return { image in
            let parameters = [
                kCIInputImageKey: inputImage,
                kCIInputBackgroundImageKey: image
            ]
            return CIFilter(name: "CISourceOverCompositing", parameters: parameters)?.outputImage ?? image
        }
    }

    static func makeRadialGradientCImage(inputRadius0: CGFloat,
                                        inputRadius1: CGFloat,
                                        inputColor0: CIColor,
                                        inputColor1: CIColor,
                                        inputCenter: CIVector) -> CIImage? {
        let parameters: [String: Any] = [
            "inputRadius0": inputRadius0,
            "inputRadius1": inputRadius1,
            "inputColor0": inputColor0,
            "inputColor1": inputColor1,
            kCIInputCenterKey: inputCenter
        ]
        return CIFilter(name: "CIRadialGradient", parameters: parameters)?.outputImage
    }

    public static func pixellateFace() -> Filter {
        return { image in
            guard hasRenderableExtent(image),
                  let detector = CIDetector(ofType: CIDetectorTypeFace, context: context,
                                            options: [CIDetectorAccuracy: CIDetectorAccuracyHigh]) else {
                return image
            }
            let masks = detector.features(in: image).compactMap { face -> CIImage? in
                let radius = min(face.bounds.width, face.bounds.height / 1.5)
                return makeRadialGradientCImage(
                    inputRadius0: radius,
                    inputRadius1: radius + 1,
                    inputColor0: CIColor(red: 1, green: 1, blue: 1, alpha: 1),
                    inputColor1: CIColor(red: 0, green: 0, blue: 0, alpha: 0),
                    inputCenter: CIVector(x: face.bounds.midX, y: face.bounds.midY))
            }
            guard let firstMask = masks.first else { return image }
            let mask = masks.dropFirst().reduce(firstMask) { sourceOver($1)($0) }
            let parameters = [
                kCIInputImageKey: pixellate()(image),
                kCIInputBackgroundImageKey: image,
                kCIInputMaskImageKey: mask.cropped(to: image.extent)
            ]
            return CIFilter(name: "CIBlendWithMask", parameters: parameters)?.outputImage?.cropped(to: image.extent) ?? image
        }
    }

    public static func blur(_ radius: Double) -> Filter {
        return { image in
            guard radius.isFinite, radius >= 0 else { return image }
            let parameters: [String: Any] = [
                kCIInputRadiusKey: radius,
                kCIInputImageKey: image
            ]
            return CIFilter(name: "CIGaussianBlur", parameters: parameters)?.outputImage ?? image
        }
    }

    public static func blurAndSepia() -> Filter {
        return blur(5) >>> sepia
    }
}

private let context = CIContext()

/// Async display-only adapter for the unchanged shipped filter graph. Own one
/// per editor. Export continues through the original full-resolution path.
/// Initialization is cheap: the shared CIContext is first touched by the worker.
/// Pass nil for an exact-size compatibility preview. Bounded SwiftUI previews
/// should lay out using original source dimensions, since raster sizes round.
public final class LegacyFilterPreviewPipeline {
    private struct Request {
        let source: UIImage
        let filter: FilterType
        let maximumDimension: Int?
    }
    private let work = LatestImageWork<Request, UIImage> { request, token in
        try autoreleasepool {
            try token.checkCancellation()
            guard request.maximumDimension.map({ (1...4096).contains($0) }) ?? true,
                  let input = request.source.filterInputImage,
                  hasRenderableExtent(input) else { throw LegacyPreviewError.invalidImage }
            // Spatial filters and face detection must run in original source
            // coordinates. Downsampling the input would change saved preset
            // meanings; only the final display raster is reduced.
            let graph = Filters.filter(request.filter)(input)
            try token.checkCancellation()
            let scale = request.maximumDimension.map { min(1, CGFloat($0) / max(input.extent.width, input.extent.height)) } ?? 1
            let transform = CGAffineTransform(scaleX: scale, y: scale)
            let sampled = graph.transformed(by: transform)
            let bounds = input.extent.applying(transform)
            guard let pixels = context.createCGImage(sampled, from: bounds) else { throw LegacyPreviewError.renderFailed }
            try token.checkCancellation()
            // Retain logical point size and UIKit orientation for the legacy
            // overlay coordinate space; the preview is never an export input.
            return UIImage(cgImage: pixels, scale: request.source.scale * scale,
                           orientation: request.source.imageOrientation)
        }
    }
    public init() {}
    @discardableResult
    public func render(source: UIImage, filter: FilterType, maximumDimension: Int? = 1400,
                       completion: @escaping (Result<UIImage, Error>) -> Void) -> ImageWorkCancellation {
        work.submit(Request(source: source, filter: filter, maximumDimension: maximumDimension), completion: completion)
    }
    public func image(source: UIImage, filter: FilterType, maximumDimension: Int? = 1400) async throws -> UIImage {
        try await work.value(for: Request(source: source, filter: filter, maximumDimension: maximumDimension))
    }
    public func cancel() { work.cancel() }
}

public enum LegacyPreviewError: Error {
    case invalidImage, renderFailed
}

private func hasRenderableExtent(_ image: CIImage) -> Bool {
    let extent = image.extent
    return !extent.isNull && !extent.isInfinite && !extent.isEmpty
        && [extent.origin.x, extent.origin.y, extent.width, extent.height].allSatisfy { $0.isFinite }
}

public extension UIImage {
    func filteredImage(_ filter: Filter) -> UIImage {
        guard let inputImage = filterInputImage, hasRenderableExtent(inputImage),
              let cgImage = context.createCGImage(filter(inputImage), from: inputImage.extent) else {
            return self
        }
        return UIImage(cgImage: cgImage, scale: scale, orientation: imageOrientation)
    }

    func filteredImage(_ orientation: Int32, filter: Filter) -> UIImage {
        guard (1...8).contains(orientation), let inputImage = filterInputImage else {
            return filteredImage(filter)
        }
        let orientedImage = inputImage.oriented(forExifOrientation: orientation)
        guard hasRenderableExtent(orientedImage),
              let cgImage = context.createCGImage(filter(orientedImage), from: orientedImage.extent) else {
            return self
        }
        return UIImage(cgImage: cgImage, scale: scale, orientation: .up)
    }
}

private extension UIImage {
    var filterInputImage: CIImage? {
        if let ciImage = ciImage { return ciImage }
        guard let cgImage = cgImage else { return nil }
        return CIImage(cgImage: cgImage)
    }
}
