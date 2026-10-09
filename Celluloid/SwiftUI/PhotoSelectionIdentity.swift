import Foundation

/// The only identifiers the app may resolve are the user's confirmed selection.
/// Neither a missing identifier nor a deleted/limited asset means "import a copy".
struct PhotoSelectionIdentity: Equatable {
    let orderedIdentifiers: [String]

    init(identifiers: [String?], maximumSelection: Int) throws {
        guard (1...4).contains(maximumSelection), !identifiers.isEmpty,
              identifiers.count <= maximumSelection else { throw PhotoSelectionError.invalidSelection }
        var seen = Set<String>()
        orderedIdentifiers = try identifiers.map { identifier in
            guard let identifier, !identifier.isEmpty else { throw PhotoSelectionError.originalIdentityMissing }
            guard seen.insert(identifier).inserted else { throw PhotoSelectionError.invalidSelection }
            return identifier
        }
    }

    func ordered<Value>(_ available: [Value], identifier: (Value) -> String) throws -> [Value] {
        var byIdentifier: [String: Value] = [:]
        for value in available { byIdentifier[identifier(value)] = value }
        return try orderedIdentifiers.map {
            guard let value = byIdentifier[$0] else { throw PhotoSelectionError.originalUnavailable }
            return value
        }
    }
}

enum PhotoSelectionError: Error, Equatable {
    case invalidSelection
    case originalUnavailable
    case originalIdentityMissing
    case accessRequired
}
