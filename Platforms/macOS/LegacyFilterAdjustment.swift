import Foundation
import CelluloidDomain

/// Narrow Photos 1.0 bridge: no native NSPoint/NSRect values are manufactured.
/// Layered archives remain unsupported and must use Photos' rendered fallback.
enum LegacyFilterAdjustment {
    static let identifier = "Mango.CelluloidPhotoExtension"
    static let version = "1.0"
    private static let preservedKey = "celluloidPreservedAdjustment"
    struct Preserved {
        let identifier: String
        let version: String
        let data: Data
    }
    static func decode(_ data: Data) throws -> FilterPreset? {
        guard data.count <= 4 * 1024 * 1024 else { throw RecipeError.resourceLimit }
        let allowed: [AnyClass] = [NSDictionary.self, NSArray.self, NSString.self, NSNumber.self, NSValue.self]
        guard let root = try NSKeyedUnarchiver.unarchivedObject(ofClasses: allowed, from: data) as? [String: Any],
              root[preservedKey] == nil,
              let raw = root["filterType"] as? String, let filter = FilterPreset(rawValue: raw) else { return nil }
        for key in ["stickers", "bubbles"] {
            if let value = root[key] { guard let values = value as? [Any], values.isEmpty else { return nil } }
        }
        if let value = root["referenceCanvasSize"] {
            guard let size = value as? NSValue,
                  ["{CGSize=dd}", "{_NSSize=dd}"].contains(String(cString: size.objCType)) else { return nil }
            var values = [Double](repeating: 0, count: 2)
            values.withUnsafeMutableBytes { size.getValue($0.baseAddress!, size: $0.count) }
            guard values.allSatisfy({ $0.isFinite && $0 >= 1 && $0 <= Double.greatestFiniteMagnitude.squareRoot() }) else { return nil }
        }
        return filter
    }
    static func encode(_ filter: FilterPreset, preserving previous: Preserved? = nil) throws -> Data {
        var root: [String: Any] = ["filterType": filter.rawValue]
        if let previous {
            guard previous.data.count <= 2 * 1024 * 1024, previous.identifier.utf8.count <= 1024, previous.version.utf8.count <= 128 else { throw RecipeError.resourceLimit }
            // Opaque original bytes survive exactly. Older readers ignore this additive key;
            // our reader deliberately declines editable restoration of this baked base.
            root[preservedKey] = ["identifier": previous.identifier, "version": previous.version, "base64": previous.data.base64EncodedString()]
        }
        let bytes = try NSKeyedArchiver.archivedData(withRootObject: root, requiringSecureCoding: true)
        guard bytes.count <= 4 * 1024 * 1024 else { throw RecipeError.resourceLimit }
        return bytes
    }
}
