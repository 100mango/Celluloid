import Foundation

/// New native document format. This is deliberately NOT a Photos adjustment 1.0 archive.
/// All geometry uses a top-left origin; sizes and centers are fractions of the canvas.
public struct EditRecipe: Codable, Equatable, Sendable {
    public static let format = "Celluloid.Document"
    public var format: String = Self.format
    public var version: Int = 1
    public var sources: [SourceImage] = []
    public var filter: FilterPreset = .original
    public var overlays: [Overlay] = []
    public var collageTemplate: String?
    public var canvasWidth: Int = 800
    public var canvasHeight: Int = 800
    public init() {}

    public func validate() throws {
        guard format == Self.format, version == 1 else { throw RecipeError.unsupportedVersion }
        guard sources.count <= 4, Set(sources.map(\.id)).count == sources.count,
              (1...16_384).contains(canvasWidth), (1...16_384).contains(canvasHeight),
              canvasWidth * canvasHeight <= 48_000_000,
              overlays.count <= 100, Set(overlays.map(\.id)).count == overlays.count else {
            throw RecipeError.invalidDocument
        }
        for source in sources { try source.validate() }
        for overlay in overlays { try overlay.validate() }
        if sources.count > 1 {
            guard let name = collageTemplate, !name.isEmpty, canvasWidth == 800, canvasHeight == 800 else {
                throw RecipeError.invalidDocument
            }
        } else if collageTemplate != nil { throw RecipeError.invalidDocument }
    }

    public func encoded() throws -> Data {
        try validate()
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
        return try encoder.encode(self)
    }

    public static func decode(_ data: Data) throws -> Self {
        guard data.count <= 2_000_000 else { throw RecipeError.resourceLimit }
        let value = try JSONDecoder().decode(Self.self, from: data)
        try value.validate()
        return value
    }
}

public enum RecipeError: Error, Equatable, LocalizedError {
    case unsupportedVersion, invalidDocument, resourceLimit, missingSource, invalidGeometry
    public var errorDescription: String? {
        switch self {
        case .unsupportedVersion: return NSLocalizedString("This document uses an unsupported Celluloid recipe version.", bundle: .module, comment: "Document error")
        case .invalidDocument: return NSLocalizedString("This Celluloid document is damaged or has invalid contents.", bundle: .module, comment: "Document error")
        case .resourceLimit: return NSLocalizedString("The image or document is too large. Use images up to 48 megapixels and keep the combined originals under 64 MB.", bundle: .module, comment: "Document error")
        case .missingSource: return NSLocalizedString("An original image is missing from this document.", bundle: .module, comment: "Document error")
        case .invalidGeometry: return NSLocalizedString("An overlay contains invalid position or size information.", bundle: .module, comment: "Document error")
        }
    }
}

public struct SourceImage: Codable, Equatable, Identifiable, Sendable {
    public let id: UUID
    public var displayName: String
    public let pixelWidth: Int
    public let pixelHeight: Int
    public var crop: SourceCrop = SourceCrop()
    /// File names are generated, never read as arbitrary user paths.
    public var filename: String { id.uuidString + ".image" }
    public init(id: UUID = UUID(), displayName: String, pixelWidth: Int, pixelHeight: Int) {
        self.id = id; self.displayName = displayName; self.pixelWidth = pixelWidth; self.pixelHeight = pixelHeight
    }
    public func validate() throws {
        guard (1...16_384).contains(pixelWidth), (1...16_384).contains(pixelHeight),
              pixelWidth * pixelHeight <= 48_000_000, displayName.utf8.count <= 1024 else {
            throw RecipeError.resourceLimit
        }
        try crop.validate()
    }
}

public struct SourceCrop: Codable, Equatable, Sendable {
    public var centerX: Double = 0.5
    public var centerY: Double = 0.5
    public var zoom: Double = 1
    public init() {}
    public func validate() throws {
        guard [centerX, centerY, zoom].allSatisfy(\.isFinite),
              (0...1).contains(centerX), (0...1).contains(centerY), (1...5).contains(zoom) else {
            throw RecipeError.invalidGeometry
        }
    }
}

public struct Overlay: Codable, Equatable, Identifiable, Sendable {
    public enum Kind: String, Codable, Sendable { case sticker, bubble }
    public let id: UUID
    public var kind: Kind
    public var asset: String
    public var text: String
    public var centerX: Double = 0.5
    public var centerY: Double = 0.5
    public var width: Double = 0.3
    public var height: Double = 0.3
    public var rotation: Double = 0
    public var mirrored: Bool = false
    /// Font size is a fraction of canvas width, so resizing a window never changes export.
    public var fontSize: Double = 0.035
    public init(id: UUID = UUID(), sticker: StickerAsset) {
        self.id = id; kind = .sticker; asset = sticker.rawValue; text = ""
    }
    public init(id: UUID = UUID(), bubble: BubbleAsset, text: String = "Hello") {
        self.id = id; kind = .bubble; asset = bubble.rawValue; self.text = text
        width = 0.4; height = 0.4
    }
    public func validate() throws {
        guard [centerX, centerY, width, height, rotation, fontSize].allSatisfy(\.isFinite),
              (-2...3).contains(centerX), (-2...3).contains(centerY),
              (0.005...4).contains(width), (0.005...4).contains(height),
              (-3600...3600).contains(rotation), (0.001...0.5).contains(fontSize),
              text.utf8.count <= 16_384 else { throw RecipeError.invalidGeometry }
        guard kind == .sticker ? StickerAsset(rawValue: asset) != nil : BubbleAsset(rawValue: asset) != nil else {
            throw RecipeError.invalidDocument
        }
    }
}
