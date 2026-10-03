import Foundation
import CryptoKit
import CoreGraphics
import ImageIO
import CelluloidDomain
import CelluloidRendering

struct PhoneCompanionRecord: Codable, Identifiable {
    var id: UUID { request.id }
    let request: CompanionRequest
    let response: CompanionResult
    let created: Date
    enum Delivery: String, Codable { case pending, queued, transferFinished, failed }
    var delivery: Delivery = .pending
    var deliveryAttempt: UUID? = nil
    var fullSHA256: String? = nil
}

/// The iPhone renders the selected source locally. A Watch preview is not a Photos save.
/// Completed full-size results persist until an explicit phone-side delete/export action.
actor PhoneCompanionProcessor {
    static let maximumStoredBytes = 128 * 1024 * 1024
    private let folder: URL
    nonisolated let inbox: PhoneCompanionInbox
    #if DEBUG
    enum Interruption: Equatable { case afterStaging, afterFullOutput, afterOutputBeforeIndex }
    private var interruption: Interruption?
    func interruptOnce(at point: Interruption) { interruption = point }
    private func checkpoint(_ point: Interruption) throws { if interruption == point { interruption = nil; throw CocoaError(.fileWriteUnknown) } }
    #endif
    private var isProcessing = false
    init(folder: URL? = nil) throws {
        self.folder = try folder ?? FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true).appendingPathComponent("WatchProcessingResults", isDirectory: true)
        try FileManager.default.createDirectory(at: self.folder, withIntermediateDirectories: true)
        inbox = try PhoneCompanionInbox(root: self.folder)
    }
    func records() throws -> [PhoneCompanionRecord] {
        let url = folder.appendingPathComponent("index.json")
        guard FileManager.default.fileExists(atPath: url.path) else { return [] }
        let bytes = try boundedRead(url, limit: 128 * 1024)
        let rows = try JSONDecoder().decode([PhoneCompanionRecord].self, from: bytes)
        guard rows.count <= 20, Set(rows.map(\.id)).count == rows.count else { throw RecipeError.invalidDocument }
        for row in rows { try row.request.validate(); try row.response.validate(); guard row.response.requestID == row.request.id, row.response.sourceSHA256 == row.request.sourceSHA256, row.response.failure == nil else { throw RecipeError.invalidDocument } }
        return rows
    }
    func process(_ request: CompanionRequest, source bytes: Data) async throws -> (PhoneCompanionRecord, URL) {
        try inbox.stage(request, bytes: bytes)
        #if DEBUG
        try checkpoint(.afterStaging)
        #endif
        guard !isProcessing else { throw RecipeError.resourceLimit }
        isProcessing = true; defer { isProcessing = false }
        try recoverCompleted()
        try request.validate()
        guard bytes.count == request.sourceBytes, Self.digest(bytes) == request.sourceSHA256 else { throw RecipeError.invalidDocument }
        var existing = try records()
        if let row = existing.first(where: { $0.id == request.id }) {
            guard row.request == request else { throw RecipeError.invalidDocument }
            let url = previewURL(row.id), preview = try boundedRead(url, limit: 2 * 1024 * 1024)
            guard Self.digest(preview) == row.response.previewSHA256 else { throw RecipeError.invalidDocument }
            try? inbox.complete(request.id)
            return (row, url)
        }
        guard existing.count < 20 else { throw RecipeError.resourceLimit }
        let source = try RasterCodec.metadata(bytes, name: "Watch Selected Photo")
        var recipe = EditRecipe(); recipe.sources = [source]; recipe.filter = request.filter
        recipe.canvasWidth = source.pixelWidth; recipe.canvasHeight = source.pixelHeight
        let full = try await NativeRenderQueue.shared.export(recipe, sources: [source.id: bytes], type: .png)
        try Task.checkCancellation()
        let image = try await NativeRenderQueue.shared.preview(recipe, sources: [source.id: bytes], maximumDimension: 512)
        let preview = try RasterCodec.encode(image, as: .png)
        guard full.count <= 64 * 1024 * 1024, preview.count <= 2 * 1024 * 1024 else { throw RecipeError.resourceLimit }
        let response = CompanionResult(requestID: request.id, sourceSHA256: request.sourceSHA256, previewSHA256: Self.digest(preview), pixelWidth: image.width, pixelHeight: image.height, failure: nil)
        var row = PhoneCompanionRecord(request: request, response: response, created: Date())
        row.fullSHA256 = Self.digest(full)
        let output = outputURL(row.id), small = previewURL(row.id)
        try inbox.transaction {
            let replaced = [output,small].reduce(0) { total, url in total + ((try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0) }
            guard try inbox.usedBytes() - replaced + full.count + preview.count + 16384 <= Self.maximumStoredBytes else { throw RecipeError.resourceLimit }
            try full.write(to: output, options: .atomic)
            #if DEBUG
            try checkpoint(.afterFullOutput)
            #endif
            try preview.write(to: small, options: .atomic)
            guard try boundedRead(output, limit: 64 * 1024 * 1024) == full,
                  try boundedRead(small, limit: 2 * 1024 * 1024) == preview else { throw RenderError.exportFailed }
            try inbox.writeReceipt(JSONEncoder().encode(row), id: request.id)
            #if DEBUG
            try checkpoint(.afterOutputBeforeIndex)
            #endif
            existing = try records(); existing.append(row); try save(existing)
            try inbox.complete(request.id)
        }
        return (row, small)
    }
    func pendingRequests() throws -> [CompanionRequest] { try inbox.reconcileStaging(); try recoverCompleted(); return try inbox.requests() }
    func resumePending(_ id: UUID) async throws -> (PhoneCompanionRecord, URL) {
        guard let request = try inbox.requests().first(where: { $0.id == id }) else { throw RecipeError.missingSource }
        return try await process(request, source: inbox.source(id))
    }
    /// The journal publishes completed output before the result index. Recover
    /// this exact request/hash pair after termination without routing any transfer.
    private func recoverCompleted() throws {
        try inbox.transaction {
            for request in try inbox.requests() {
                guard let bytes = try inbox.receipt(request.id) else { continue }
                let row = try JSONDecoder().decode(PhoneCompanionRecord.self, from: bytes)
                guard row.request == request, let fullHash = row.fullSHA256,
                      try Self.digest(boundedRead(outputURL(request.id), limit: 64 * 1024 * 1024)) == fullHash,
                      try Self.digest(boundedRead(previewURL(request.id), limit: 2 * 1024 * 1024)) == row.response.previewSHA256 else { throw RecipeError.invalidDocument }
                try row.response.validate()
                guard row.response.requestID == request.id, row.response.sourceSHA256 == request.sourceSHA256 else { throw RecipeError.invalidDocument }
                var rows = try records()
                if let existing = rows.first(where: { $0.id == request.id }) { guard existing.request == request else { throw RecipeError.invalidDocument } }
                else { guard rows.count < 20 else { throw RecipeError.resourceLimit }; rows.append(row); try save(rows) }
                try inbox.complete(request.id)
            }
        }
    }
    func discardPending(_ id: UUID) throws {
        guard !isProcessing else { throw RecipeError.resourceLimit }
        try inbox.complete(id)
        // Remove only unindexed partial outputs from this explicitly discarded job.
        if try !records().contains(where: { $0.id == id }) {
            try? FileManager.default.removeItem(at: outputURL(id)); try? FileManager.default.removeItem(at: previewURL(id))
        }
    }
    func beginDelivery(_ id: UUID) throws -> UUID {
        var rows = try records()
        guard let index = rows.firstIndex(where: { $0.id == id }) else { throw RecipeError.missingSource }
        let attempt = UUID(); rows[index].deliveryAttempt = attempt; rows[index].delivery = .queued; try save(rows); return attempt
    }
    func finishDelivery(_ id: UUID, attempt: UUID, failed: Bool) throws {
        var rows = try records()
        guard let index = rows.firstIndex(where: { $0.id == id }), rows[index].deliveryAttempt == attempt,
              rows[index].delivery != .transferFinished else { return }
        rows[index].delivery = failed ? .failed : .transferFinished; try save(rows)
    }
    func holdDelivery(_ id: UUID, attempt: UUID? = nil) throws {
        var rows = try records()
        guard let index = rows.firstIndex(where: { $0.id == id }), rows[index].delivery != .transferFinished,
              attempt == nil || rows[index].deliveryAttempt == attempt else { return }
        rows[index].delivery = .pending; try save(rows)
    }
    func fullResult(_ id: UUID) throws -> Data {
        guard let row = try records().first(where: { $0.id == id }) else { throw RecipeError.missingSource }
        let bytes = try boundedRead(outputURL(id), limit: 64 * 1024 * 1024)
        if let hash = row.fullSHA256 { guard Self.digest(bytes) == hash else { throw RecipeError.invalidDocument } }
        return bytes
    }
    func remove(_ id: UUID) throws {
        guard !isProcessing else { throw RecipeError.resourceLimit }
        var rows = try records(); rows.removeAll { $0.id == id }; try save(rows)
        try? FileManager.default.removeItem(at: outputURL(id)); try? FileManager.default.removeItem(at: previewURL(id))
    }
    private func outputURL(_ id: UUID) -> URL { folder.appendingPathComponent(id.uuidString + ".png") }
    private func previewURL(_ id: UUID) -> URL { folder.appendingPathComponent(id.uuidString + ".preview.png") }
    private func save(_ records: [PhoneCompanionRecord]) throws {
        let bytes = try JSONEncoder().encode(records); guard bytes.count <= 128 * 1024 else { throw RecipeError.resourceLimit }
        try bytes.write(to: folder.appendingPathComponent("index.json"), options: .atomic)
    }
    private func boundedRead(_ url: URL, limit: Int) throws -> Data { try PhoneCompanionInbox.read(url, limit: limit) }
    static func digest(_ bytes: Data) -> String { SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined() }
}
