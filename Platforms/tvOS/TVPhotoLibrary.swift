import Foundation
import Photos
import ImageIO
import CoreGraphics
import CelluloidDomain
import CelluloidRendering

/// PhotoKit access is explicit. Original Photos assets are never modified or deleted.
enum TVPhotoError: Error, LocalizedError {
    case permission, missing, unavailable, tooMany, verification
    var errorDescription: String? {
        switch self {
        case .permission: return NSLocalizedString("Allow Photos access in Settings to import and save pictures.", comment: "TV Photos")
        case .missing: return NSLocalizedString("A source photo is no longer available. Choose it again from Photos.", comment: "TV Photos")
        case .unavailable: return NSLocalizedString("This photo is not stored on this Apple TV. Download it in Photos and try again.", comment: "TV Photos")
        case .tooMany: return NSLocalizedString("Choose between one and four images.", comment: "TV Photos")
        case .verification: return NSLocalizedString("Photos did not return a matching saved image. Check Photos before saving again.", comment: "TV Photos")
        }
    }
}

@MainActor final class TVPhotoLibrary: ObservableObject {
    @Published private(set) var assets: [PHAsset] = []
    @Published private(set) var authorization = PHPhotoLibrary.authorizationStatus(for: .readWrite)
    private let manager = PHImageManager()

    func requestAccessAndRefresh() async throws {
        authorization = await PHPhotoLibrary.requestAuthorization(for: .readWrite)
        try refresh()
    }
    func refresh() throws {
        authorization = PHPhotoLibrary.authorizationStatus(for: .readWrite)
        guard authorization == .authorized || authorization == .limited else { assets = []; throw TVPhotoError.permission }
        let options = PHFetchOptions(); options.fetchLimit = 200
        options.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: false)]
        let result = PHAsset.fetchAssets(with: .image, options: options)
        assets = (0..<result.count).map { result.object(at: $0) }
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
    func original(_ id: String) async throws -> Data {
        try Task.checkCancellation()
        let result = PHAsset.fetchAssets(withLocalIdentifiers: [id], options: nil)
        guard let asset = result.firstObject else { throw TVPhotoError.missing }
        let options = PHImageRequestOptions(); options.version = .current
        options.deliveryMode = .highQualityFormat; options.isNetworkAccessAllowed = false
        let data: Data = try await withCheckedThrowingContinuation { continuation in
            manager.requestImageDataAndOrientation(for: asset, options: options) { data, _, _, info in
                if let error = info?[PHImageErrorKey] as? Error { continuation.resume(throwing: error) }
                else if let data { continuation.resume(returning: data) }
                else { continuation.resume(throwing: TVPhotoError.unavailable) }
            }
        }
        try Task.checkCancellation()
        _ = try RasterCodec.metadata(data)
        return data
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
        do { readback = try await original(identifier) }
        catch { throw TVPhotoError.verification }
        let actual = try RasterCodec.metadata(readback)
        guard actual.pixelWidth == expected.pixelWidth, actual.pixelHeight == expected.pixelHeight,
              try Self.normalizedProof(bytes) == Self.normalizedProof(readback) else { throw TVPhotoError.verification }
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
