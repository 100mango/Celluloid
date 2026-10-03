import Foundation
import Photos
import ImageIO
import CoreGraphics
import UniformTypeIdentifiers
import CelluloidDomain
import CelluloidRendering

/// PhotoKit access is explicit. Original Photos assets are never modified or deleted.
enum TVPhotoError: Error, LocalizedError {
    case permission, missing, unavailable, tooMany, verification, changed
    var errorDescription: String? {
        switch self {
        case .permission: return NSLocalizedString("Allow Photos access in Settings to import and save pictures.", comment: "TV Photos")
        case .missing: return NSLocalizedString("A source photo is no longer available. Choose it again from Photos.", comment: "TV Photos")
        case .unavailable: return NSLocalizedString("This photo is not stored on this Apple TV. Download it in Photos and try again.", comment: "TV Photos")
        case .tooMany: return NSLocalizedString("Choose between one and four images.", comment: "TV Photos")
        case .changed: return NSLocalizedString("A Photos source has changed since this recipe was saved. Your current edit is unchanged; choose the photos again to start a new composition.", comment: "TV Photos")
        case .verification: return NSLocalizedString("Photos did not return a matching saved image. Check Photos before saving again.", comment: "TV Photos")
        }
    }
}

@MainActor protocol TVPhotoDataSource {
    func currentImageData(_ id: String, limit: Int) async throws -> Data
    func saveVerifiedPNG(_ bytes: Data) async throws -> String
}

@MainActor final class TVPhotoLibrary: ObservableObject, TVPhotoDataSource {
    @Published private(set) var assets: [PHAsset] = []
    @Published private(set) var authorization = PHPhotoLibrary.authorizationStatus(for: .readWrite)
    private let manager = PHImageManager()

    func requestAccessAndRefresh() async throws {
        authorization = await PHPhotoLibrary.requestAuthorization(for: .readWrite)
        #if DEBUG
        print("TV_PHOTOS_AUTH status=\(authorization.rawValue)")
        #endif
        try refresh()
    }
    func refresh() throws {
        authorization = PHPhotoLibrary.authorizationStatus(for: .readWrite)
        guard authorization == .authorized || authorization == .limited else { assets = []; throw TVPhotoError.permission }
        let options = PHFetchOptions(); options.fetchLimit = 200
        options.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: false)]
        let result = PHAsset.fetchAssets(with: .image, options: options)
        assets = (0..<result.count).map { result.object(at: $0) }
        #if DEBUG
        print("TV_PHOTOS_FETCH count=\(assets.count)")
        #endif
    }
    func thumbnail(_ asset: PHAsset) async -> CGImage? {
        let options = PHImageRequestOptions(); options.deliveryMode = .highQualityFormat
        options.resizeMode = .fast; options.isNetworkAccessAllowed = false
        return await withCheckedContinuation { continuation in
            manager.requestImage(for: asset, targetSize: CGSize(width: 260, height: 180), contentMode: .aspectFill, options: options) { image, info in
                guard (info?[PHImageResultIsDegradedKey] as? Bool) != true else { return }
                continuation.resume(returning: image?.cgImage)
            }
        }
    }
    func currentImageData(_ id: String, limit: Int = 64 * 1024 * 1024) async throws -> Data {
        try Task.checkCancellation()
        guard limit > 0, limit <= RasterCodec.maxSourceBytes else { throw RecipeError.resourceLimit }
        let result = PHAsset.fetchAssets(withLocalIdentifiers: [id], options: nil)
        guard let asset = result.firstObject else { throw TVPhotoError.missing }
        guard asset.pixelWidth > 0, asset.pixelHeight > 0, asset.pixelWidth <= 16_384, asset.pixelHeight <= 16_384,
              asset.pixelWidth * asset.pixelHeight <= 50_000_000 else { throw RecipeError.resourceLimit }
        let resources = PHAssetResource.assetResources(for: asset)
        // .fullSizePhoto is the current adjusted rendition; otherwise .photo is the
        // still original. Do not silently substitute a pre-adjustment image or RAW preview.
        guard let resource = resources.first(where: { $0.type == .fullSizePhoto }) ?? resources.first(where: { $0.type == .photo }),
              let type = UTType(resource.uniformTypeIdentifier), !type.conforms(to: .rawImage) else { throw RenderError.unsupportedSourceFormat }
        let state = TVResourceRead(limit: limit)
        let manager = PHAssetResourceManager.default()
        let bytes: Data = try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                state.install(continuation)
                let options = PHAssetResourceRequestOptions(); options.isNetworkAccessAllowed = false
                let requestID = manager.requestData(for: resource, options: options, dataReceivedHandler: state.append) { error in
                    state.finish(error)
                }
                state.setCancellation { manager.cancelDataRequest(requestID) }
            }
        } onCancel: { state.cancel() }
        try Task.checkCancellation(); _ = try RasterCodec.metadata(bytes); return bytes
    }
    /// Completion means an actual Photos asset was fetched and decoded again.
    /// Failure after a successful write is reported distinctly; it is never auto-retried.
    func saveVerifiedPNG(_ bytes: Data) async throws -> String {
        let expected = try RasterCodec.metadata(bytes)
        let status = PHPhotoLibrary.authorizationStatus(for: .readWrite)
        guard status == .authorized || status == .limited else { throw TVPhotoError.permission }
        var identifier: String?
        try await PHPhotoLibrary.shared().performChanges {
            let request = PHAssetCreationRequest.forAsset()
            let options = PHAssetResourceCreationOptions(); options.originalFilename = "Celluloid.png"
            request.addResource(with: .photo, data: bytes, options: options)
            identifier = request.placeholderForCreatedAsset?.localIdentifier
        }
        guard let identifier else { throw TVPhotoError.verification }
        let readback: Data
        do { readback = try await currentImageData(identifier) }
        catch { throw TVPhotoError.verification }
        let actual = try RasterCodec.metadata(readback)
        guard actual.pixelWidth == expected.pixelWidth, actual.pixelHeight == expected.pixelHeight,
              try Self.normalizedProof(bytes) == Self.normalizedProof(readback) else { throw TVPhotoError.verification }
        #if DEBUG
        if ProcessInfo.processInfo.environment["CELLULOID_TV_OUTPUT_PROOF"] == "YES" {
            // A test-only copy of the actual PhotoKit-refetched bytes, not renderer
            // output. The external Core Image oracle uses independent known inputs.
            let root = try FileManager.default.url(for: .cachesDirectory, in: .userDomainMask, appropriateFor: nil, create: true).appendingPathComponent("TVOutputProof", isDirectory: true)
            try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
            let index = FileManager.default.fileExists(atPath: root.appendingPathComponent("1.json").path) ? 2 : 1
            guard readback.count <= 5_000_000, !FileManager.default.fileExists(atPath: root.appendingPathComponent("\(index).json").path) else { throw RecipeError.resourceLimit }
            try readback.write(to: root.appendingPathComponent("\(index).png"), options: .atomic)
            let metadata: [String: Any] = ["photosAssetIdentifier": identifier, "bytes": readback.count, "sha256": TVSavedRecipe.fingerprint(readback), "width": actual.pixelWidth, "height": actual.pixelHeight]
            try JSONSerialization.data(withJSONObject: metadata, options: [.sortedKeys]).write(to: root.appendingPathComponent("\(index).json"), options: .atomic)
        }
        #endif
        return identifier
    }
    /// Independent ImageIO/CoreGraphics readback, not a check of the returned placeholder alone.
    static func normalizedProof(_ data: Data) throws -> Data {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil),
              let image = CGImageSourceCreateThumbnailAtIndex(source, 0, [kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceCreateThumbnailWithTransform: true, kCGImageSourceThumbnailMaxPixelSize: 64] as CFDictionary),
              let space = CGColorSpace(name: CGColorSpace.sRGB),
              let context = CGContext(data: nil, width: 64, height: 64, bitsPerComponent: 8, bytesPerRow: 256, space: space,
                                      bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue) else { throw TVPhotoError.verification }
        context.draw(image, in: CGRect(x: 0, y: 0, width: 64, height: 64))
        guard let pointer = context.data else { throw TVPhotoError.verification }
        return Data(bytes: pointer, count: 64 * 256)
    }
}

/// Serialized chunk intake. The limit is checked before retaining each chunk.
/// Cancellation releases accumulated data and resumes without waiting on PhotoKit.
final class TVResourceRead: @unchecked Sendable {
    private let lock = NSLock()
    private let limit: Int
    private var data = Data()
    private var continuation: CheckedContinuation<Data, Error>?
    private var completed = false
    private var terminalError: Error?
    private var cancellation: (() -> Void)?
    init(limit: Int) { self.limit = limit }
    func install(_ value: CheckedContinuation<Data, Error>) {
        lock.lock()
        if completed { let error = terminalError ?? CancellationError(); lock.unlock(); value.resume(throwing: error) }
        else { continuation = value; lock.unlock() }
    }
    func setCancellation(_ action: @escaping () -> Void) {
        lock.lock(); if !completed { cancellation = action }; let stop = completed && terminalError != nil; lock.unlock()
        if stop { action() }
    }
    func append(_ chunk: Data) {
        lock.lock()
        guard !completed else { lock.unlock(); return }
        guard chunk.count <= limit - data.count else {
            completed = true; terminalError = RecipeError.resourceLimit
            let waiting = continuation, cancel = cancellation
            continuation = nil; cancellation = nil; data = Data(); lock.unlock()
            cancel?(); waiting?.resume(throwing: RecipeError.resourceLimit); return
        }
        data.append(chunk); lock.unlock()
    }
    func finish(_ error: Error?) {
        if let error { fail(error); return }
        lock.lock()
        guard !completed else { lock.unlock(); return }
        completed = true; let waiting = continuation, result = data
        continuation = nil; cancellation = nil; data = Data(); lock.unlock()
        waiting?.resume(returning: result)
    }
    func cancel() { fail(CancellationError()) }
    private func fail(_ error: Error) {
        lock.lock()
        guard !completed else { lock.unlock(); return }
        completed = true; terminalError = error; let waiting = continuation, cancel = cancellation
        continuation = nil; cancellation = nil; data = Data(); lock.unlock()
        cancel?(); waiting?.resume(throwing: error)
    }
}
