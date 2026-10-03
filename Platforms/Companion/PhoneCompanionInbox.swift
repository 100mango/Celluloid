import Foundation
import CryptoKit
import CelluloidDomain

/// Synchronous durable ownership before WCSession removes a received delivery URL.
/// Only this app's bounded synthetic/user-requested processing files live here.
final class PhoneCompanionInbox: @unchecked Sendable {
    static let maximumPending = 4
    static let maximumStoredBytes = 128 * 1024 * 1024
    let root: URL
    private let lock = NSRecursiveLock()
    private var discardedStaging = 0
    private var parkedStaging = 0
    private var folder: URL { root.appendingPathComponent("Pending", isDirectory: true) }
    init(root: URL) throws {
        self.root = root
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        try reconcileStaging()
    }
    var recoveryNotice: String? {
        transaction {
            if parkedStaging > 0 { return String(format: NSLocalizedString("%d interrupted requests are retained and waiting for pending capacity. Resume or discard a pending request to make room.", comment: "Phone inbox recovery"), parkedStaging) }
            if discardedStaging > 0 { return NSLocalizedString("An incomplete request was interrupted before acceptance. Its temporary copy was cleared; request it again from your Watch.", comment: "Phone inbox recovery") }
            return nil
        }
    }
    /// Reconcile only our own UUID staging namespace. Accepted requests and
    /// completed output/index files are never removed or rewritten by this pass.
    func reconcileStaging() throws {
        try transaction {
            let all = try FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: [.isDirectoryKey,.isSymbolicLinkKey])
            let staging = all.filter { url in
                let name = url.lastPathComponent
                return name.hasPrefix(".staging-") && UUID(uuidString: String(name.dropFirst(".staging-".count))) != nil
            }.sorted { $0.lastPathComponent < $1.lastPathComponent }
            guard staging.count <= 64 else { throw RecipeError.resourceLimit }
            var acceptedCount = all.filter { !$0.lastPathComponent.hasPrefix(".") }.count
            parkedStaging = 0
            for temporary in staging {
                let info = try temporary.resourceValues(forKeys: [.isDirectoryKey,.isSymbolicLinkKey])
                guard info.isDirectory == true, info.isSymbolicLink != true else { throw RecipeError.invalidDocument }
                let recovered: (CompanionRequest, Data)?
                do {
                    let request = try CompanionRequest.decode(Self.read(temporary.appendingPathComponent("request.json"), limit: 4096))
                    let bytes = try Self.read(temporary.appendingPathComponent("source.image"), limit: 8 * 1024 * 1024)
                    guard bytes.count == request.sourceBytes, Self.digest(bytes) == request.sourceSHA256 else { throw RecipeError.invalidDocument }
                    recovered = (request, bytes)
                } catch {
                    // A transient protection/permission error must not erase data.
                    let cocoa = error as? CocoaError
                    guard error is DecodingError || (error as? RecipeError) == .invalidDocument || (error as? RecipeError) == .resourceLimit || cocoa?.code == .fileReadNoSuchFile || cocoa?.code == .fileReadCorruptFile else { throw error }
                    // This directory was never published as an accepted request.
                    try FileManager.default.removeItem(at: temporary); discardedStaging += 1; continue
                }
                guard let (request, bytes) = recovered else { throw RecipeError.invalidDocument }
                let destination = jobURL(request.id)
                if FileManager.default.fileExists(atPath: destination.path) {
                    guard try requestAt(destination) == request, try source(request.id) == bytes else { throw RecipeError.invalidDocument }
                    try FileManager.default.removeItem(at: temporary); continue
                }
                guard acceptedCount < Self.maximumPending else { parkedStaging += 1; continue }
                try FileManager.default.moveItem(at: temporary, to: destination); acceptedCount += 1
            }
        }
    }
    func transaction<T>(_ body: () throws -> T) rethrows -> T { lock.lock(); defer { lock.unlock() }; return try body() }
    @discardableResult func stage(_ request: CompanionRequest, from url: URL) throws -> CompanionRequest {
        let data = try Self.read(url, limit: 8 * 1024 * 1024)
        return try stage(request, bytes: data)
    }
    @discardableResult func stage(_ request: CompanionRequest, bytes: Data) throws -> CompanionRequest {
        try transaction {
            try request.validate()
            guard bytes.count == request.sourceBytes, Self.digest(bytes) == request.sourceSHA256 else { throw RecipeError.invalidDocument }
            let index = root.appendingPathComponent("index.json")
            if FileManager.default.fileExists(atPath: index.path) {
                let rows = try JSONDecoder().decode([PhoneCompanionRecord].self, from: Self.read(index, limit: 128 * 1024))
                if let previous = rows.first(where: { $0.id == request.id }) { guard previous.request == request else { throw RecipeError.invalidDocument } }
            }
            let destination = jobURL(request.id)
            if FileManager.default.fileExists(atPath: destination.path) {
                guard try requestAt(destination) == request, try Self.digest(source(request.id)) == request.sourceSHA256 else { throw RecipeError.invalidDocument }
                return request
            }
            guard try requests().count < Self.maximumPending,
                  try usedBytes() + bytes.count + 8192 <= Self.maximumStoredBytes else { throw RecipeError.resourceLimit }
            let temporary = folder.appendingPathComponent(".staging-" + UUID().uuidString, isDirectory: true)
            try FileManager.default.createDirectory(at: temporary, withIntermediateDirectories: false)
            defer { try? FileManager.default.removeItem(at: temporary) }
            try request.encoded().write(to: temporary.appendingPathComponent("request.json"), options: .atomic)
            try bytes.write(to: temporary.appendingPathComponent("source.image"), options: .atomic)
            guard try Self.read(temporary.appendingPathComponent("source.image"), limit: 8 * 1024 * 1024) == bytes else { throw RecipeError.invalidDocument }
            try FileManager.default.moveItem(at: temporary, to: destination)
            return request
        }
    }
    func requests() throws -> [CompanionRequest] {
        try transaction {
            let folders = try FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: [.isDirectoryKey,.isSymbolicLinkKey])
                .filter { !$0.lastPathComponent.hasPrefix(".") }
            guard folders.count <= Self.maximumPending else { throw RecipeError.resourceLimit }
            return try folders.map { try requestAt($0) }.sorted { $0.id.uuidString < $1.id.uuidString }
        }
    }
    func source(_ id: UUID) throws -> Data {
        try transaction {
            let request = try requestAt(jobURL(id)), bytes = try Self.read(jobURL(id).appendingPathComponent("source.image"), limit: 8 * 1024 * 1024)
            guard bytes.count == request.sourceBytes, Self.digest(bytes) == request.sourceSHA256 else { throw RecipeError.invalidDocument }
            return bytes
        }
    }
    func receipt(_ id: UUID) throws -> Data? {
        try transaction {
            let url = jobURL(id).appendingPathComponent("completed.json")
            guard FileManager.default.fileExists(atPath: url.path) else { return nil }
            return try Self.read(url, limit: 8192)
        }
    }
    func writeReceipt(_ bytes: Data, id: UUID) throws {
        try transaction {
            guard bytes.count <= 8192 else { throw RecipeError.resourceLimit }
            try bytes.write(to: jobURL(id).appendingPathComponent("completed.json"), options: .atomic)
        }
    }
    func complete(_ id: UUID) throws { try transaction { try FileManager.default.removeItem(at: jobURL(id)) } }
    func usedBytes() throws -> Int {
        try transaction {
            guard let files = FileManager.default.enumerator(at: root, includingPropertiesForKeys: [.isRegularFileKey,.isSymbolicLinkKey,.fileSizeKey]) else { throw RecipeError.invalidDocument }
            var total = 0
            for case let url as URL in files {
                let info = try url.resourceValues(forKeys: [.isRegularFileKey,.isSymbolicLinkKey,.fileSizeKey])
                guard info.isSymbolicLink != true else { throw RecipeError.invalidDocument }
                if info.isRegularFile == true { total += info.fileSize ?? 0 }
            }
            return total
        }
    }
    private func jobURL(_ id: UUID) -> URL { folder.appendingPathComponent(id.uuidString, isDirectory: true) }
    private func requestAt(_ url: URL) throws -> CompanionRequest {
        let info = try url.resourceValues(forKeys: [.isDirectoryKey,.isSymbolicLinkKey])
        guard info.isDirectory == true, info.isSymbolicLink != true else { throw RecipeError.invalidDocument }
        let request = try CompanionRequest.decode(Self.read(url.appendingPathComponent("request.json"), limit: 4096))
        guard request.id.uuidString == url.lastPathComponent else { throw RecipeError.invalidDocument }
        return request
    }
    static func read(_ url: URL, limit: Int) throws -> Data {
        let info = try url.resourceValues(forKeys: [.isRegularFileKey,.isSymbolicLinkKey,.fileSizeKey])
        guard info.isRegularFile == true, info.isSymbolicLink != true, let size = info.fileSize, size >= 0, size <= limit else { throw RecipeError.resourceLimit }
        let file = try FileHandle(forReadingFrom: url); defer { try? file.close() }
        var bytes = Data()
        while let chunk = try file.read(upToCount: 64 * 1024), !chunk.isEmpty {
            guard chunk.count <= limit - bytes.count else { throw RecipeError.resourceLimit }; bytes.append(chunk)
        }
        return bytes
    }
    static func digest(_ bytes: Data) -> String { SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined() }
}
