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
}

/// The iPhone renders the selected source locally. A Watch preview is not a Photos save.
/// Completed full-size results persist until an explicit phone-side delete/export action.
actor PhoneCompanionProcessor {
    static let maximumStoredBytes = 128 * 1024 * 1024
    private let folder: URL
    private var isProcessing = false
    init(folder: URL? = nil) throws {
        self.folder = try folder ?? FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true).appendingPathComponent("WatchProcessingResults", isDirectory: true)
        try FileManager.default.createDirectory(at: self.folder, withIntermediateDirectories: true)
    }
    func records() throws -> [PhoneCompanionRecord] {
        let url = folder.appendingPathComponent("index.json")
        guard FileManager.default.fileExists(atPath: url.path) else { return [] }
        let bytes = try boundedRead(url, limit: 128 * 1024)
        let rows = try JSONDecoder().decode([PhoneCompanionRecord].self, from: bytes)
        guard rows.count <= 20, Set(rows.map(\.id)).count == rows.count else { throw RecipeError.invalidDocument }
        for row in rows { try row.request.validate(); try row.response.validate(); guard row.response.requestID == row.request.id else { throw RecipeError.invalidDocument } }
        return rows
    }
    func process(_ request: CompanionRequest, source bytes: Data) async throws -> (PhoneCompanionRecord, URL) {
        guard !isProcessing else { throw RecipeError.resourceLimit }
        isProcessing = true; defer { isProcessing = false }
        try request.validate()
        guard bytes.count == request.sourceBytes, Self.digest(bytes) == request.sourceSHA256 else { throw RecipeError.invalidDocument }
        var existing = try records()
        if let row = existing.first(where: { $0.id == request.id }) {
            guard row.request == request else { throw RecipeError.invalidDocument }
            let url = previewURL(row.id), preview = try boundedRead(url, limit: 2 * 1024 * 1024)
            guard Self.digest(preview) == row.response.previewSHA256 else { throw RecipeError.invalidDocument }
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
        guard full.count <= 64 * 1024 * 1024, preview.count <= 2 * 1024 * 1024,
              try usedBytes() + full.count + preview.count + 8192 <= Self.maximumStoredBytes else { throw RecipeError.resourceLimit }
        let response = CompanionResult(requestID: request.id, sourceSHA256: request.sourceSHA256, previewSHA256: Self.digest(preview), pixelWidth: image.width, pixelHeight: image.height, failure: nil)
        let row = PhoneCompanionRecord(request: request, response: response, created: Date())
        let output = outputURL(row.id), small = previewURL(row.id)
        do {
            try full.write(to: output, options: .atomic); try preview.write(to: small, options: .atomic)
            guard try boundedRead(output, limit: 64 * 1024 * 1024) == full,
                  try boundedRead(small, limit: 2 * 1024 * 1024) == preview else { throw RenderError.exportFailed }
            existing = try records(); existing.append(row); try save(existing)
        } catch { try? FileManager.default.removeItem(at: output); try? FileManager.default.removeItem(at: small); throw error }
        return (row, small)
    }
    func markDelivery(_ id: UUID, _ delivery: PhoneCompanionRecord.Delivery) throws {
        var rows = try records()
        guard let index = rows.firstIndex(where: { $0.id == id }) else { return }
        rows[index].delivery = delivery; try save(rows)
    }
    func fullResult(_ id: UUID) throws -> Data {
        guard try records().contains(where: { $0.id == id }) else { throw RecipeError.missingSource }
        return try boundedRead(outputURL(id), limit: 64 * 1024 * 1024)
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
    private func usedBytes() throws -> Int {
        try FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: [.fileSizeKey]).reduce(0) { total, file in total + ((try file.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0) }
    }
    private func boundedRead(_ url: URL, limit: Int) throws -> Data {
        let info = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
        guard info.isRegularFile == true, info.isSymbolicLink != true, let size = info.fileSize, size <= limit else { throw RecipeError.resourceLimit }
        let bytes = try Data(contentsOf: url); guard bytes.count <= limit else { throw RecipeError.resourceLimit }; return bytes
    }
    static func digest(_ bytes: Data) -> String { SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined() }
}
