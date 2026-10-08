import Foundation
import Darwin
import CelluloidDomain

/// WCSession owns the delivery URL only until its delegate returns. Commit one
/// bounded binary-plist receipt synchronously, then apply it to the actor-owned
/// gallery. An interrupted apply is replayable without asking the phone again.
final class WatchIncomingResults: @unchecked Sendable {
    struct Receipt: Codable, Equatable {
        let revision: UUID
        let result: CompanionResult
        let preview: Data?
    }
    static let maximumReceiptBytes = 2 * 1024 * 1024 + 16 * 1024
    static let maximumReceipts = 2
    private let folder: URL
    private let lock = NSRecursiveLock()
    init(folder: URL? = nil) throws {
        self.folder = try folder ?? FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true).appendingPathComponent("IncomingResults", isDirectory: true)
        try FileManager.default.createDirectory(at: self.folder, withIntermediateDirectories: true)
        try reconcileStaging()
    }
    @discardableResult func stage(_ result: CompanionResult, preview: Data?) throws -> Receipt {
        lock.lock(); defer { lock.unlock() }
        try validate(result, preview: preview)
        let destination = url(result.requestID)
        if FileManager.default.fileExists(atPath: destination.path) {
            let previous = try read(destination)
            guard previous.result.sourceSHA256 == result.sourceSHA256 else { throw RecipeError.invalidDocument }
            if previous.result == result {
                guard previous.preview == preview else { throw RecipeError.invalidDocument }
                return previous
            }
            // A late error must never overwrite a durably delivered successful result.
            if previous.result.failure == nil && result.failure != nil { return previous }
            guard previous.result.failure != nil && result.failure == nil else { throw RecipeError.invalidDocument }
        } else {
            guard try files().count < Self.maximumReceipts else { throw RecipeError.resourceLimit }
        }
        let receipt = Receipt(revision: UUID(), result: result, preview: preview)
        let encoder = PropertyListEncoder(); encoder.outputFormat = .binary
        let bytes = try encoder.encode(receipt)
        guard bytes.count <= Self.maximumReceiptBytes else { throw RecipeError.resourceLimit }
        let staging = folder.appendingPathComponent(".staging-" + receipt.revision.uuidString)
        do {
            try bytes.write(to: staging, options: .withoutOverwriting)
            guard try read(staging, staging: true) == receipt else { throw RecipeError.invalidDocument }
            guard rename(staging.path, destination.path) == 0 else { throw NSError(domain: NSPOSIXErrorDomain, code: Int(errno)) }
        } catch {
            try? FileManager.default.removeItem(at: staging)
            throw error
        }
        guard try read(destination) == receipt else { throw RecipeError.invalidDocument }
        return receipt
    }
    func pending() throws -> [Receipt] {
        lock.lock(); defer { lock.unlock() }
        try reconcileStaging()
        let paths = try files(); guard paths.count <= Self.maximumReceipts else { throw RecipeError.resourceLimit }
        return try paths.map { try read($0) }
    }
    func removeIfUnchanged(_ receipt: Receipt) throws {
        lock.lock(); defer { lock.unlock() }
        let destination = url(receipt.result.requestID)
        guard FileManager.default.fileExists(atPath: destination.path) else { return }
        guard try read(destination).revision == receipt.revision else { return }
        try FileManager.default.removeItem(at: destination)
    }
    private func reconcileStaging() throws {
        let candidates = try FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil).filter {
            $0.lastPathComponent.hasPrefix(".staging-") && UUID(uuidString: String($0.lastPathComponent.dropFirst(9))) != nil
        }
        guard candidates.count <= 8 else { throw RecipeError.resourceLimit }
        for file in candidates {
            let receipt: Receipt
            do { receipt = try read(file, staging: true) }
            catch is DecodingError { try FileManager.default.removeItem(at: file); continue }
            catch let error as RecipeError where error == .invalidDocument || error == .resourceLimit {
                // These are incomplete or invalid pre-commit files owned by this
                // namespace. Never clean accepted receipts or arbitrary files.
                try FileManager.default.removeItem(at: file); continue
            }
            // A fully written receipt killed immediately before rename is valid
            // delivery data. Re-admit it using the same completion-wins rules.
            let destination = url(receipt.result.requestID)
            if FileManager.default.fileExists(atPath: destination.path) {
                let previous = try read(destination)
                guard previous.result.sourceSHA256 == receipt.result.sourceSHA256 else { throw RecipeError.invalidDocument }
                if previous.result == receipt.result || (previous.result.failure == nil && receipt.result.failure != nil) {
                    try FileManager.default.removeItem(at: file); continue
                }
                guard previous.result.failure != nil && receipt.result.failure == nil else { throw RecipeError.invalidDocument }
            } else if try files().count >= Self.maximumReceipts {
                continue // Keep a fully valid orphan until accepted receipts free a slot.
            }
            // Reuse the complete journal file itself: recovery never creates another
            // staging copy that could multiply under repeated process termination.
            guard rename(file.path, destination.path) == 0 else { throw NSError(domain: NSPOSIXErrorDomain, code: Int(errno)) }
        }
    }
    private func url(_ id: UUID) -> URL { folder.appendingPathComponent(id.uuidString + ".receipt") }
    private func files() throws -> [URL] {
        try FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil)
            .filter { $0.pathExtension == "receipt" && UUID(uuidString: $0.deletingPathExtension().lastPathComponent) != nil }
            .sorted { $0.lastPathComponent < $1.lastPathComponent }
    }
    private func read(_ url: URL, staging: Bool = false) throws -> Receipt {
        let info = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
        guard info.isRegularFile == true, info.isSymbolicLink != true, let size = info.fileSize, size <= Self.maximumReceiptBytes else { throw RecipeError.resourceLimit }
        let bytes = try Data(contentsOf: url); guard bytes.count <= Self.maximumReceiptBytes else { throw RecipeError.resourceLimit }
        let receipt = try PropertyListDecoder().decode(Receipt.self, from: bytes)
        guard staging || url.deletingPathExtension().lastPathComponent == receipt.result.requestID.uuidString else { throw RecipeError.invalidDocument }
        try validate(receipt.result, preview: receipt.preview); return receipt
    }
    private func validate(_ result: CompanionResult, preview: Data?) throws {
        try result.validate()
        if result.failure != nil { guard preview == nil else { throw RecipeError.invalidDocument }; return }
        guard let preview, preview.count <= 2 * 1024 * 1024, WatchGalleryStore.digest(preview) == result.previewSHA256 else { throw RecipeError.invalidDocument }
        let dimensions = try WatchGalleryStore.dimensions(preview)
        guard dimensions.0 == result.pixelWidth, dimensions.1 == result.pixelHeight else { throw RecipeError.invalidDocument }
    }
}
