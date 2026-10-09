import Foundation
import CoreGraphics
import ImageIO
import CelluloidDomain

/// The thumbnail is display-only. Documents and exports keep the exact original
/// bytes and stable caller-provided identity, including embedded color profiles.
public struct ImportedRasterSource {
    public let source: SourceImage
    public let originalBytes: Data
    public let preview: CGImage
}

/// One instance per selected source slot. Calling load again replaces pending
/// work; cancel on dismissal/source replacement. Load an ordered batch serially
/// or use one instance per slot. No Photos library enumeration is performed.
public final class RasterSourceLoader {
    private struct Request {
        enum Input { case file(URL), bytes(Data) }
        let input: Input
        let name: String
        let id: UUID
        let maximumDimension: Int
    }
    private let work = LatestImageWork<Request, ImportedRasterSource> { request, token in
        try autoreleasepool {
            try token.checkCancellation()
            let bytes: Data
            switch request.input {
            case .file(let url): bytes = try RasterSourceLoader.readBounded(url, token: token)
            case .bytes(let data): bytes = data
            }
            try token.checkCancellation()
            let source = try RasterCodec.metadata(bytes, name: request.name, id: request.id)
            let preview = try RasterSourceLoader.thumbnail(bytes, maximumDimension: request.maximumDimension, token: token)
            try token.checkCancellation()
            return ImportedRasterSource(source: source, originalBytes: bytes, preview: preview)
        }
    }
    public init() {}

    /// The caller owns the URL and any security-scoped grant for the duration of
    /// this await. An NSItemProvider temporary URL must first be copied while its
    /// callback is alive; never pass that borrowed URL beyond its callback.
    public func load(fileURL: URL, name: String, id: UUID = UUID(), maximumPreviewDimension: Int = 1400) async throws -> ImportedRasterSource {
        try await work.value(for: Request(input: .file(fileURL), name: name, id: id, maximumDimension: maximumPreviewDimension))
    }
    public func load(bytes: Data, name: String, id: UUID = UUID(), maximumPreviewDimension: Int = 1400) async throws -> ImportedRasterSource {
        try await work.value(for: Request(input: .bytes(bytes), name: name, id: id, maximumDimension: maximumPreviewDimension))
    }
    public func cancel() { work.cancel() }

    private static func readBounded(_ url: URL, token: ImageWorkCancellation) throws -> Data {
        guard url.isFileURL,
              let stream = InputStream(url: url) else { throw RenderError.invalidImage }
        stream.open(); defer { stream.close() }
        var result = Data()
        var buffer = [UInt8](repeating: 0, count: 64 * 1024)
        while true {
            try token.checkCancellation()
            let count = stream.read(&buffer, maxLength: buffer.count)
            if count == 0 { break }
            guard count > 0 else { throw stream.streamError ?? RenderError.invalidImage }
            guard result.count <= RasterCodec.maxSourceBytes - count else { throw RecipeError.resourceLimit }
            result.append(contentsOf: buffer.prefix(count))
        }
        return result
    }

    private static func thumbnail(_ bytes: Data, maximumDimension: Int, token: ImageWorkCancellation) throws -> CGImage {
        guard (1...4096).contains(maximumDimension) else { throw RecipeError.resourceLimit }
        try token.checkCancellation()
        let sourceOptions = [kCGImageSourceShouldCache: false] as CFDictionary
        guard let source = CGImageSourceCreateWithData(bytes as CFData, sourceOptions) else { throw RenderError.invalidImage }
        // Transform applies EXIF once. ImageIO retains the source color profile;
        // do not convert/encode the original just to make a UI thumbnail.
        let options: [CFString: Any] = [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceThumbnailMaxPixelSize: maximumDimension,
            kCGImageSourceShouldCacheImmediately: true
        ]
        guard let image = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary),
              image.width > 0, image.height > 0,
              max(image.width, image.height) <= maximumDimension else { throw RenderError.invalidImage }
        try token.checkCancellation()
        return image
    }
}
