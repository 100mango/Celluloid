import Foundation
import CelluloidDomain

/// Narrow Photos 1.0 bridge: no native NSPoint/NSRect values are manufactured.
/// Layered archives remain unsupported and must use Photos' rendered fallback.
enum LegacyFilterAdjustment {
    static let identifier = "Mango.CelluloidPhotoExtension"
    static let version = "1.0"
    /// A baked base cannot be replayed against the system original by old readers.
    /// Their exact 1.0 support check must decline this independent native format.
    static let bakedBaseVersion = "2.0-baked-base"
    static func outputVersion(isBakedBase: Bool) -> String { isBakedBase ? bakedBaseVersion : version }
    static func accepts(identifier candidate: String, version candidateVersion: String, data: Data) -> Bool {
        candidate == identifier && candidateVersion == version && (try? decode(data)) != nil
    }
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
              root[preservedKey] == nil, root["celluloidNativeBakedBase"] == nil,
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
    static func encode(_ filter: FilterPreset, preserving previous: Preserved? = nil, isBakedBase: Bool = false) throws -> Data {
        var root: [String: Any] = ["filterType": filter.rawValue]
        if isBakedBase || previous != nil { root["celluloidNativeBakedBase"] = true }
        if let previous {
            guard previous.data.count <= 2 * 1024 * 1024, previous.identifier.utf8.count <= 1024, previous.version.utf8.count <= 128 else { throw RecipeError.resourceLimit }
            // Opaque original bytes survive exactly. The caller advertises bakedBaseVersion,
            // so legacy readers decline rather than silently losing the baked edits.
            root[preservedKey] = ["identifier": previous.identifier, "version": previous.version, "base64": previous.data.base64EncodedString()]
        }
        let bytes = try NSKeyedArchiver.archivedData(withRootObject: root, requiringSecureCoding: true)
        guard bytes.count <= 4 * 1024 * 1024 else { throw RecipeError.resourceLimit }
        return bytes
    }
}
