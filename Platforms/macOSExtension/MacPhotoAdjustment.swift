import Foundation
import CoreGraphics
import CelluloidDomain

/// The shipped Photos 1.0 dictionary and UIKit NSValue geometry. Deliberately
/// separate from normalized .celluloid documents: affine shear, translation,
/// bounds origins, layer grouping and absolute canvas points must survive.
struct MacPhotoAdjustment {
    static let identifier = "Mango.CelluloidPhotoExtension"
    static let version = "1.0"
    static let maximumArchiveBytes = 4 * 1024 * 1024
    var filter: FilterPreset = .original
    var referenceCanvas: CGSize?
    var bubbles: [MacPhotoLayer] = []
    var stickers: [MacPhotoLayer] = []
    var layers: [MacPhotoLayer] { bubbles + stickers } // Historical compositor order.

    static func supports(identifier: String, version: String) -> Bool {
        identifier == Self.identifier && version == Self.version
    }
    static func decode(_ bytes: Data) throws -> Self {
        guard !bytes.isEmpty, bytes.count <= maximumArchiveBytes else { throw RecipeError.resourceLimit }
        let allowed: [AnyClass] = [NSDictionary.self, NSArray.self, NSString.self, NSNumber.self, NSValue.self]
        guard let root = try NSKeyedUnarchiver.unarchivedObject(ofClasses: allowed, from: bytes) as? [String: Any],
              Set(root.keys).isSubset(of: ["filterType", "referenceCanvasSize", "bubbles", "stickers"]),
              let raw = root["filterType"] as? String, let filter = FilterPreset(rawValue: raw) else { throw RecipeError.invalidDocument }
        var result = Self(); result.filter = filter
        if let value = root["referenceCanvasSize"] {
            let size = try PhotoArchiveValue.read(value, kind: .size)
            result.referenceCanvas = CGSize(width: size[0], height: size[1])
        }
        func layers(_ key: String, kind: MacPhotoLayer.Kind) throws -> [MacPhotoLayer] {
            guard let value = root[key] else { return [] }
            guard let values = value as? [[String: Any]], values.count <= 100 else { throw RecipeError.resourceLimit }
            return try values.map { try MacPhotoLayer(object: $0, kind: kind) }
        }
        result.bubbles = try layers("bubbles", kind: .bubble)
        result.stickers = try layers("stickers", kind: .sticker)
        try result.validate()
        return result
    }
    func validate() throws {
        guard layers.count <= 100 else { throw RecipeError.resourceLimit }
        if let canvas = referenceCanvas {
            guard [canvas.width, canvas.height].allSatisfy({ $0.isFinite && $0 >= 1 && $0 <= 16_384 }) else { throw RecipeError.invalidGeometry }
        }
        for layer in layers { try layer.validate() }
    }
    /// No canvas is inferred for a historical layered archive. Callers retain the
    /// current Photos appearance read-only when these absolute points lack scale.
    func requireEditableCanvas() throws {
        try validate()
        guard layers.isEmpty || referenceCanvas != nil else { throw RecipeError.invalidGeometry }
    }
    func encode() throws -> Data {
        try requireEditableCanvas()
        var root: [String: Any] = ["filterType": filter.rawValue]
        if let canvas = referenceCanvas { root["referenceCanvasSize"] = PhotoArchiveValue.make([canvas.width, canvas.height], kind: .size) }
        if !bubbles.isEmpty { root["bubbles"] = bubbles.map(\.archiveObject) }
        if !stickers.isEmpty { root["stickers"] = stickers.map(\.archiveObject) }
        let bytes = try NSKeyedArchiver.archivedData(withRootObject: root, requiringSecureCoding: true)
        guard bytes.count <= Self.maximumArchiveBytes else { throw RecipeError.resourceLimit }
        return bytes
    }
    mutating func edit(_ id: UUID, _ mutation: (inout MacPhotoLayer) -> Void) {
        if let i = bubbles.firstIndex(where: { $0.id == id }) { mutation(&bubbles[i]) }
        else if let i = stickers.firstIndex(where: { $0.id == id }) { mutation(&stickers[i]) }
    }
    mutating func remove(_ id: UUID) { bubbles.removeAll { $0.id == id }; stickers.removeAll { $0.id == id } }
}

struct MacPhotoLayer: Identifiable {
    enum Kind: Equatable { case bubble, sticker }
    let id: UUID
    let kind: Kind
    let asset: String
    var text: String
    var center: CGPoint
    var bounds: CGRect
    var transform: CGAffineTransform

    init(id: UUID = UUID(), kind: Kind, asset: String, text: String = "", canvas: CGSize) {
        self.id = id; self.kind = kind; self.asset = asset; self.text = text
        center = CGPoint(x: canvas.width / 2, y: canvas.height / 2)
        bounds = CGRect(x: 0, y: 0, width: 160, height: 160)
        transform = .identity
    }
    init(object: [String: Any], kind: Kind) throws {
        let assetKey = kind == .bubble ? "asset" : "imageName"
        let fields: Set<String> = kind == .bubble ? ["asset", "content", "center", "bounds", "transform"] : ["imageName", "center", "bounds", "transform"]
        guard Set(object.keys) == fields, let asset = object[assetKey] as? String else { throw RecipeError.invalidDocument }
        let point = try PhotoArchiveValue.read(object["center"], kind: .point)
        let rect = try PhotoArchiveValue.read(object["bounds"], kind: .rect)
        let affine = try PhotoArchiveValue.read(object["transform"], kind: .affine)
        id = UUID(); self.kind = kind; self.asset = asset
        if kind == .bubble {
            guard let content = object["content"] as? String else { throw RecipeError.invalidDocument }; text = content
        } else { text = "" }
        center = CGPoint(x: point[0], y: point[1]); bounds = CGRect(x: rect[0], y: rect[1], width: rect[2], height: rect[3])
        transform = CGAffineTransform(a: affine[0], b: affine[1], c: affine[2], d: affine[3], tx: affine[4], ty: affine[5])
        try validate()
    }
    func validate() throws {
        guard kind == .bubble ? BubbleAsset(rawValue: asset) != nil : StickerAsset(rawValue: asset) != nil else { throw RecipeError.invalidDocument }
        let values = [center.x, center.y, bounds.minX, bounds.minY, bounds.maxX, bounds.maxY, bounds.width, bounds.height,
                      transform.a, transform.b, transform.c, transform.d, transform.tx, transform.ty]
        guard values.allSatisfy({ $0.isFinite && abs($0) <= 10_000_000 }), bounds.width >= 0, bounds.height >= 0,
              text.utf8.count <= 16_384 else { throw RecipeError.resourceLimit }
        let rect = bounds.applying(transform)
        guard [rect.minX, rect.minY, rect.maxX, rect.maxY, center.x + transform.tx - rect.width / 2,
               center.x + transform.tx + rect.width / 2, center.y + transform.ty - rect.height / 2,
               center.y + transform.ty + rect.height / 2].allSatisfy(\.isFinite) else { throw RecipeError.invalidGeometry }
    }
    var archiveObject: [String: Any] {
        var result: [String: Any] = [kind == .bubble ? "asset" : "imageName": asset,
            "center": PhotoArchiveValue.make([center.x, center.y], kind: .point),
            "bounds": PhotoArchiveValue.make([bounds.origin.x, bounds.origin.y, bounds.width, bounds.height], kind: .rect),
            "transform": PhotoArchiveValue.make([transform.a, transform.b, transform.c, transform.d, transform.tx, transform.ty], kind: .affine)]
        if kind == .bubble { result["content"] = text }
        return result
    }
}

/// Keep UIKit's explicit Objective-C structure names when manufacturing values.
/// Interoperability is separately tested by the ORIGINAL UIKit AdjustmentData reader.
enum PhotoArchiveValue {
    enum Kind: Equatable {
        case point, size, rect, affine
        var encoding: String {
            switch self {
            case .point: return "{CGPoint=dd}"
            case .size: return "{CGSize=dd}"
            case .rect: return "{CGRect={CGPoint=dd}{CGSize=dd}}"
            case .affine: return "{CGAffineTransform=dddddd}"
            }
        }
        var accepted: Set<String> {
            switch self {
            case .point: return [encoding, "{_NSPoint=dd}"]
            case .size: return [encoding, "{_NSSize=dd}"]
            case .rect: return [encoding, "{_NSRect={_NSPoint=dd}{_NSSize=dd}}"]
            case .affine: return [encoding]
            }
        }
        var count: Int { self == .rect ? 4 : self == .affine ? 6 : 2 }
    }
    static func read(_ object: Any?, kind: Kind) throws -> [CGFloat] {
        guard let value = object as? NSValue, kind.accepted.contains(String(cString: value.objCType)) else { throw RecipeError.invalidGeometry }
        var values = [Double](repeating: 0, count: kind.count)
        values.withUnsafeMutableBytes { value.getValue($0.baseAddress!, size: $0.count) }
        guard values.allSatisfy(\.isFinite) else { throw RecipeError.invalidGeometry }
        return values.map { CGFloat($0) }
    }
    static func make(_ components: [CGFloat], kind: Kind) -> NSValue {
        precondition(components.count == kind.count)
        let values = components.map { Double($0) }
        return kind.encoding.withCString { type in values.withUnsafeBytes { NSValue(bytes: $0.baseAddress!, objCType: type) } }
    }
}
