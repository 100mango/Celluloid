import Foundation

/// Stable identifiers from the released Photos adjustment format. The portable
/// domain does not change the legacy archive or require Core Image on watchOS.
public enum FilterPreset: String, CaseIterable, Codable, Sendable {
    case original = "Original"
    case sepia = "Sepia"
    case chrome = "Chrome"
    case fade = "Fade"
    case invert = "Invert"
    case posterize = "Posterize"
    case sketch = "Sketch"
    case comic = "Comic"
    case crystal = "Crystal"
    case pixellateFace = "PixellateFace"

    /// Original and face pixelation require their own rendering operations.
    public var coreImageFilterName: String? {
        switch self {
        case .original, .pixellateFace: return nil
        case .sepia: return "CISepiaTone"
        case .chrome: return "CIPhotoEffectChrome"
        // Version 1 called the Instant effect Fade. Preserve its actual output.
        case .fade: return "CIPhotoEffectInstant"
        case .invert: return "CIColorInvert"
        case .posterize: return "CIColorPosterize"
        case .sketch: return "CILineOverlay"
        case .comic: return "CIComicEffect"
        case .crystal: return "CICrystallize"
        }
    }
}

public enum BubbleAsset: String, CaseIterable, Codable, Sendable {
    case aside1, call1, call2, call3, say1, say2, say3, think1, think2, think3
}

public struct StickerAsset: RawRepresentable, Hashable, Codable, Sendable {
    public let rawValue: String
    public init?(rawValue: String) {
        guard let value = Int(rawValue), (32...54).contains(value), String(value) == rawValue else { return nil }
        self.rawValue = rawValue
    }

    public static var all: [Self] { (32...54).compactMap { Self(rawValue: String($0)) } }

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        let raw = try container.decode(String.self)
        guard let value = Self(rawValue: raw) else {
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Unknown Celluloid sticker")
        }
        self = value
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(rawValue)
    }
}
