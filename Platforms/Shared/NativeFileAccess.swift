import Foundation
import UniformTypeIdentifiers
import CelluloidDomain
import CelluloidRendering

/// Imported bytes must be an owned snapshot, not a mapping of an externally editable file.
enum NativeFileAccess {
    static func readImage(_ url: URL, limit: Int = RasterCodec.maxSourceBytes, check: () throws -> Void = { try Task.checkCancellation() }) throws -> Data {
        if UTType(filenameExtension: url.pathExtension)?.conforms(to: .rawImage) == true { throw RenderError.unsupportedSourceFormat }
        guard limit > 0, limit <= 256 * 1024 * 1024 else { throw RecipeError.resourceLimit }
        let accessed = url.startAccessingSecurityScopedResource()
        defer { if accessed { url.stopAccessingSecurityScopedResource() } }
        let properties = try url.resourceValues(forKeys: [.fileSizeKey, .isRegularFileKey])
        guard properties.isRegularFile == true else { throw RenderError.invalidImage }
        let size = properties.fileSize ?? 0
        guard size > 0, size <= limit else { throw RecipeError.resourceLimit }
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        var result = Data(); result.reserveCapacity(size)
        while result.count <= limit {
            try check()
            let count = min(1024 * 1024, limit + 1 - result.count)
            guard let chunk = try handle.read(upToCount: count), !chunk.isEmpty else { break }
            result.append(chunk)
        }
        guard !result.isEmpty, result.count <= limit else { throw RecipeError.resourceLimit }
        return result
    }
}

/// Owns a bounded temporary file while an async Photos/provider import is in flight.
/// It never puts user image data in defaults or retains it after the import completes.
final class OwnedImportFile: @unchecked Sendable {
    let url: URL
    init(copying source: URL, limit: Int = RasterCodec.maxSourceBytes, check: () throws -> Void = { try Task.checkCancellation() }) throws {
        let properties = try source.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey])
        guard properties.isRegularFile == true, let size = properties.fileSize, size > 0, size <= limit else { throw RecipeError.resourceLimit }
        url = FileManager.default.temporaryDirectory.appendingPathComponent("Celluloid-import-" + UUID().uuidString)
        guard FileManager.default.createFile(atPath: url.path, contents: nil) else { throw CocoaError(.fileWriteUnknown) }
        var success = false
        defer { if !success { try? FileManager.default.removeItem(at: url) } }
        let input = try FileHandle(forReadingFrom: source); defer { try? input.close() }
        let output = try FileHandle(forWritingTo: url); defer { try? output.close() }
        var count = 0
        while let chunk = try input.read(upToCount: 1024 * 1024), !chunk.isEmpty {
            try check(); count += chunk.count; guard count <= limit else { throw RecipeError.resourceLimit }
            try output.write(contentsOf: chunk)
        }
        try check(); guard count > 0 else { throw RenderError.invalidImage }; success = true
    }
    func discard() { try? FileManager.default.removeItem(at: url) }
    deinit { discard() }
}

actor NativeImportQueue {
    static let shared = NativeImportQueue()
    func read(_ urls: [URL], budget: Int = 64 * 1024 * 1024) throws -> [(String, Data)] {
        var results: [(String, Data)] = []
        var remaining = budget
        for url in urls {
            try Task.checkCancellation()
            guard remaining > 0 else { throw RecipeError.resourceLimit }
            let data = try NativeFileAccess.readImage(url, limit: remaining)
            results.append((url.lastPathComponent, data)); remaining -= data.count
        }
        return results
    }
}
