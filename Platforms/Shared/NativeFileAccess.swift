import Foundation
import UniformTypeIdentifiers
import CelluloidDomain
import CelluloidRendering

/// Imported bytes must be an owned snapshot, not a mapping of an externally editable file.
enum NativeFileAccess {
    static func readImage(_ url: URL, limit: Int = RasterCodec.maxSourceBytes) throws -> Data {
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
            try Task.checkCancellation()
            let count = min(1024 * 1024, limit + 1 - result.count)
            guard let chunk = try handle.read(upToCount: count), !chunk.isEmpty else { break }
            result.append(chunk)
        }
        guard !result.isEmpty, result.count <= limit else { throw RecipeError.resourceLimit }
        return result
    }
}
