import Foundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers
import CryptoKit
import CelluloidDomain

struct WatchPhoto: Codable, Equatable, Identifiable {
    let id: UUID
    let name: String
    let width: Int
    let height: Int
    let sourceSHA256: String
    var job: CompanionJob?
}

/// User-selected imports are durable application data, not purgeable thumbnails.
/// Refuse new imports at the limit; never silently delete or mirror phone deletions.
actor WatchGalleryStore {
    static let maximumBytes = 32 * 1024 * 1024
    static let maximumPhotos = 20
    static let maximumPreviewBytes = 20 * 1024 * 1024
    private let folder: URL
    init(folder: URL? = nil) throws {
        self.folder = try folder ?? FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true).appendingPathComponent("SelectedPhotos", isDirectory: true)
        try FileManager.default.createDirectory(at: self.folder, withIntermediateDirectories: true)
    }
    func load() throws -> [WatchPhoto] {
        let url = folder.appendingPathComponent("index.json")
        guard FileManager.default.fileExists(atPath: url.path) else { return [] }
        let bytes = try read(url, maximum: 128 * 1024)
        let items = try JSONDecoder().decode([WatchPhoto].self, from: bytes)
        guard items.count <= Self.maximumPhotos, Set(items.map(\.id)).count == items.count,
              items.allSatisfy({ $0.name.utf8.count <= 1024 && $0.sourceSHA256.count == 64 && $0.width > 0 && $0.height > 0 && $0.width <= 16_384 && $0.height <= 16_384 && $0.width * $0.height <= 50_000_000 }) else { throw RecipeError.invalidDocument }
        for item in items { try item.job?.validate() }
        return items
    }
    func importPhoto(_ data: Data, name: String) throws -> WatchPhoto {
        var items = try load()
        guard data.count <= 8 * 1024 * 1024, items.count < Self.maximumPhotos else { throw RecipeError.resourceLimit }
        let image = try Self.thumbnail(data)
        let preview = try Self.png(image)
        let metadata = try Self.dimensions(data)
        let item = WatchPhoto(id: UUID(), name: String(name.prefix(200)), width: metadata.0, height: metadata.1, sourceSHA256: Self.digest(data), job: nil)
        let sourceURL = url(item.id, "source"), previewURL = url(item.id, "preview")
        guard try usedBytes() + data.count + preview.count < Self.maximumBytes, try previewBytes() + preview.count <= Self.maximumPreviewBytes else { throw RecipeError.resourceLimit }
        do {
            try data.write(to: sourceURL, options: .atomic); try preview.write(to: previewURL, options: .atomic)
            items.append(item); try save(items)
        } catch {
            try? FileManager.default.removeItem(at: sourceURL); try? FileManager.default.removeItem(at: previewURL); throw error
        }
        return item
    }
    func preview(_ id: UUID, processed: Bool = false) throws -> CGImage {
        try Self.thumbnail(read(url(id, processed ? "processed" : "preview"), maximum: 2 * 1024 * 1024))
    }
    func source(_ id: UUID) throws -> (URL, Data) {
        let file = url(id, "source"), bytes = try read(url(id, "source"), maximum: 8 * 1024 * 1024)
        return (file, bytes)
    }
    /// Admission and enqueue are one actor operation: a second caller cannot pass
    /// a stale pending check, and cancel cannot run between persistence and enqueue.
    func beginRequest(_ id: UUID, filter: FilterPreset, enqueue: @Sendable (URL, CompanionRequest) throws -> Void) throws -> CompanionRequest {
        var items = try load()
        guard !items.contains(where: { $0.job?.phase == .pending || $0.job?.phase == .processing }) else {
            throw NSError(domain: "Celluloid.Companion", code: 2, userInfo: [NSLocalizedDescriptionKey: NSLocalizedString("Wait for the current phone request, or cancel it first.", comment: "Watch companion")])
        }
        guard let index = items.firstIndex(where: { $0.id == id }) else { throw RecipeError.missingSource }
        let bytes = try read(url(id, "source"), maximum: 8 * 1024 * 1024)
        guard Self.digest(bytes) == items[index].sourceSHA256 else { throw RecipeError.invalidDocument }
        let request = CompanionRequest(sourceID: id, sourceSHA256: items[index].sourceSHA256, sourceBytes: bytes.count, filter: filter)
        let previous = items[index].job
        items[index].job = CompanionJob(request: request); try save(items)
        do { try enqueue(url(id, "source"), request) }
        catch { items[index].job = previous; try save(items); throw error }
        return request
    }
    func cancelRequest(sourceID: UUID, requestID: UUID) throws -> CompanionRequest? {
        var items = try load()
        guard let index = items.firstIndex(where: { $0.id == sourceID }), var current = items[index].job,
              current.request.id == requestID, current.phase == .pending || current.phase == .processing else { return nil }
        current.cancel(); items[index].job = current; try save(items)
        return current.request
    }
    func markProcessing(_ request: CompanionRequest) throws {
        var items = try load()
        guard let index = items.firstIndex(where: { $0.id == request.sourceID }), var current = items[index].job,
              current.request == request, current.phase == .pending else { return }
        current.markProcessing(); items[index].job = current; try save(items)
    }
    func receive(_ result: CompanionResult, preview: Data?) throws {
        var items = try load()
        guard let index = items.firstIndex(where: { $0.job?.request.id == result.requestID }), var job = items[index].job else { return }
        guard job.phase != .cancelled else { return }
        try job.accept(result)
        if result.failure == nil {
            guard let preview, preview.count <= 2 * 1024 * 1024, Self.digest(preview) == result.previewSHA256 else { throw RecipeError.invalidDocument }
            let dimensions = try Self.dimensions(preview)
            guard dimensions.0 == result.pixelWidth, dimensions.1 == result.pixelHeight else { throw RecipeError.invalidDocument }
            let destination = url(items[index].id, "processed")
            let oldBytes = (try? destination.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
            guard try usedBytes() - oldBytes + preview.count <= Self.maximumBytes, try previewBytes() - oldBytes + preview.count <= Self.maximumPreviewBytes else { throw RecipeError.resourceLimit }
            try preview.write(to: destination, options: .atomic)
        }
        items[index].job = job; try save(items)
    }
    func remove(_ id: UUID) throws {
        var items = try load(); items.removeAll { $0.id == id }; try save(items)
        for suffix in ["source", "preview", "processed"] { try? FileManager.default.removeItem(at: url(id, suffix)) }
    }
    private func save(_ items: [WatchPhoto]) throws {
        let bytes = try JSONEncoder().encode(items)
        guard bytes.count <= 128 * 1024 else { throw RecipeError.resourceLimit }
        try bytes.write(to: folder.appendingPathComponent("index.json"), options: .atomic)
    }
    private func url(_ id: UUID, _ suffix: String) -> URL { folder.appendingPathComponent(id.uuidString + "." + suffix) }
    private func previewBytes() throws -> Int {
        try FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: [.fileSizeKey]).filter { ["preview", "processed"].contains($0.pathExtension) }.reduce(0) { total, file in
            total + ((try file.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0)
        }
    }
    private func usedBytes() throws -> Int {
        try FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: [.fileSizeKey]).reduce(0) { total, url in
            total + ((try url.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0)
        }
    }
    private func read(_ url: URL, maximum: Int) throws -> Data {
        let attributes = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
        guard attributes.isRegularFile == true, attributes.isSymbolicLink != true, let size = attributes.fileSize, size <= maximum else { throw RecipeError.resourceLimit }
        let bytes = try Data(contentsOf: url); guard bytes.count <= maximum else { throw RecipeError.resourceLimit }; return bytes
    }
    static func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
    static func dimensions(_ data: Data) throws -> (Int, Int) {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil), CGImageSourceGetCount(source) == 1,
              let typeID = CGImageSourceGetType(source) as String?, let type = UTType(typeID), !type.conforms(to: .rawImage),
              let values = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
              let w = values[kCGImagePropertyPixelWidth] as? Int, let h = values[kCGImagePropertyPixelHeight] as? Int,
              (1...16_384).contains(w), (1...16_384).contains(h), w * h <= 50_000_000 else { throw RecipeError.invalidDocument }
        let orientation = values[kCGImagePropertyOrientation] as? Int ?? 1
        guard (1...8).contains(orientation) else { throw RecipeError.invalidDocument }
        return (5...8).contains(orientation) ? (h,w) : (w,h)
    }
    static func thumbnail(_ data: Data) throws -> CGImage {
        _ = try dimensions(data)
        guard let source = CGImageSourceCreateWithData(data as CFData, nil),
              let image = CGImageSourceCreateThumbnailAtIndex(source, 0, [kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceCreateThumbnailWithTransform: true, kCGImageSourceThumbnailMaxPixelSize: 512] as CFDictionary) else { throw RecipeError.invalidDocument }
        return image
    }
    static func png(_ image: CGImage) throws -> Data {
        let data = NSMutableData()
        guard let target = CGImageDestinationCreateWithData(data, UTType.png.identifier as CFString, 1, nil) else { throw RecipeError.invalidDocument }
        CGImageDestinationAddImage(target, image, nil)
        guard CGImageDestinationFinalize(target), data.length <= 2 * 1024 * 1024 else { throw RecipeError.resourceLimit }
        return data as Data
    }
}
