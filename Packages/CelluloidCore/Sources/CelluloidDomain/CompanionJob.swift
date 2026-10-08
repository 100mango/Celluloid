import Foundation

/// Explicit paired-phone image processing. No Photos 1.0 archive or automatic sync.
public struct CompanionRequest: Codable, Equatable, Sendable {
    public var version = 1
    public let id: UUID
    public let sourceID: UUID
    public let sourceSHA256: String
    public let sourceBytes: Int
    public let filter: FilterPreset
    public init(id: UUID = UUID(), sourceID: UUID, sourceSHA256: String, sourceBytes: Int, filter: FilterPreset) {
        self.id = id; self.sourceID = sourceID; self.sourceSHA256 = sourceSHA256
        self.sourceBytes = sourceBytes; self.filter = filter
    }
    public func validate() throws {
        guard version == 1, (1...8 * 1024 * 1024).contains(sourceBytes), sourceSHA256.count == 64,
              sourceSHA256.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }) else { throw RecipeError.invalidDocument }
    }
    public func encoded() throws -> Data { try validate(); return try JSONEncoder().encode(self) }
    public static func decode(_ data: Data) throws -> Self {
        guard data.count <= 4096 else { throw RecipeError.resourceLimit }
        let value = try JSONDecoder().decode(Self.self, from: data); try value.validate(); return value
    }
}
public struct CompanionResult: Codable, Equatable, Sendable {
    public var version = 1
    public let requestID: UUID
    public let sourceSHA256: String
    public let previewSHA256: String?
    public let pixelWidth: Int?
    public let pixelHeight: Int?
    public let failure: String?
    public init(requestID: UUID, sourceSHA256: String, previewSHA256: String?, pixelWidth: Int?, pixelHeight: Int?, failure: String?) {
        self.requestID = requestID; self.sourceSHA256 = sourceSHA256; self.previewSHA256 = previewSHA256
        self.pixelWidth = pixelWidth; self.pixelHeight = pixelHeight; self.failure = failure
    }
    public func validate() throws {
        guard version == 1, sourceSHA256.count == 64, sourceSHA256.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }) else { throw RecipeError.invalidDocument }
        if let failure {
            guard !failure.isEmpty, failure.utf8.count <= 1024, previewSHA256 == nil, pixelWidth == nil, pixelHeight == nil else { throw RecipeError.invalidDocument }
        } else {
            guard let hash = previewSHA256, hash.count == 64, hash.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }), let width = pixelWidth, let height = pixelHeight,
                  (1...512).contains(width), (1...512).contains(height) else { throw RecipeError.invalidDocument }
        }
    }
    public func encoded() throws -> Data { try validate(); return try JSONEncoder().encode(self) }
    public static func decode(_ data: Data) throws -> Self {
        guard data.count <= 4096 else { throw RecipeError.resourceLimit }
        let value = try JSONDecoder().decode(Self.self, from: data); try value.validate(); return value
    }
}
public struct CompanionJob: Codable, Equatable, Sendable {
    public enum Phase: String, Codable, Sendable { case pending, processing, completed, failed, cancelled }
    public let request: CompanionRequest
    public private(set) var phase: Phase = .pending
    public private(set) var result: CompanionResult?
    public init(request: CompanionRequest) { self.request = request }
    public func validate() throws {
        try request.validate(); try result?.validate()
        if let result {
            guard result.requestID == request.id, result.sourceSHA256 == request.sourceSHA256,
                  (phase == .completed && result.failure == nil) || (phase == .failed && result.failure != nil) else { throw RecipeError.invalidDocument }
        } else { guard phase != .completed && phase != .failed else { throw RecipeError.invalidDocument } }
    }
    public mutating func accept(_ result: CompanionResult) throws {
        try request.validate(); try result.validate()
        guard result.requestID == request.id, result.sourceSHA256 == request.sourceSHA256 else { throw RecipeError.invalidDocument }
        guard phase != .cancelled else { return }
        if let previous = self.result {
            if previous == result { return }
            // A verified delivered preview may arrive after a transport error. Completion wins.
            // A delayed error must never downgrade a successfully received image.
            if previous.failure == nil && result.failure != nil { return }
            guard previous.failure != nil && result.failure == nil else { throw RecipeError.invalidDocument }
        }
        self.result = result; phase = result.failure == nil ? .completed : .failed
    }
    public mutating func markProcessing() { if phase == .pending { phase = .processing } }
    public mutating func cancel() { if phase == .pending || phase == .processing { phase = .cancelled } }
}
