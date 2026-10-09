import Foundation
import Photos

@MainActor protocol SelectedPhotoLibraryAccess {
    var authorizationStatus: PHAuthorizationStatus { get }
    func requestOriginalEditingAccess() async -> PHAuthorizationStatus
    func resolve(_ identity: PhotoSelectionIdentity) async throws -> [PHAsset]
}

/// Metadata-only lookup on a serial worker. There is deliberately no all-assets
/// fetch, image request, provider read, decode, render, or file IO here.
@MainActor struct SelectedPhotoLibrary: SelectedPhotoLibraryAccess {
    private nonisolated static let queue = DispatchQueue(label: "Mango.Celluloid.selected-assets", qos: .userInitiated)

    var authorizationStatus: PHAuthorizationStatus { Self.effectiveAuthorization }

    private nonisolated static var effectiveAuthorization: PHAuthorizationStatus {
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("--photos-denied") { return .denied }
        if ProcessInfo.processInfo.arguments.contains("--photos-limited-empty") { return .limited }
        #endif
        return PHPhotoLibrary.authorizationStatus(for: .readWrite)
    }

    func requestOriginalEditingAccess() async -> PHAuthorizationStatus {
        await withCheckedContinuation { continuation in
            PHPhotoLibrary.requestAuthorization(for: .readWrite) { continuation.resume(returning: $0) }
        }
    }

    func resolve(_ identity: PhotoSelectionIdentity) async throws -> [PHAsset] {
        try Task.checkCancellation()
        let request = SelectedPhotoLookup()
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                request.install(continuation)
                Self.queue.async {
                    guard !request.isCancelled else { return }
                    let status = Self.effectiveAuthorization
                    guard status == .authorized || status == .limited else {
                        request.complete(.failure(PhotoSelectionError.accessRequired)); return
                    }
                    #if DEBUG
                    if ProcessInfo.processInfo.arguments.contains("--photos-limited-empty") {
                        request.complete(.failure(PhotoSelectionError.originalUnavailable)); return
                    }
                    #endif
                    let fetched = PHAsset.fetchAssets(withLocalIdentifiers: identity.orderedIdentifiers, options: nil)
                    var assets: [PHAsset] = []
                    // Cardinality is bounded by 4 even for a 100,000-photo library.
                    for index in 0..<fetched.count {
                        guard !request.isCancelled else { return }
                        let asset = fetched.object(at: index)
                        if asset.mediaType == .image { assets.append(asset) }
                    }
                    request.complete(Result { try identity.ordered(assets, identifier: { $0.localIdentifier }) })
                }
            }
        } onCancel: { request.cancel() }
    }
}

/// Cancellation resumes the suspended caller immediately, including while a
/// Photos metadata query is in flight; its late callback has no delivery rights.
private final class SelectedPhotoLookup: @unchecked Sendable {
    private let lock = NSLock()
    private var cancelled = false
    private var completed = false
    private var continuation: CheckedContinuation<[PHAsset], Error>?

    var isCancelled: Bool { lock.lock(); defer { lock.unlock() }; return cancelled }

    func install(_ value: CheckedContinuation<[PHAsset], Error>) {
        lock.lock()
        if cancelled { completed = true; lock.unlock(); value.resume(throwing: CancellationError()) }
        else { continuation = value; lock.unlock() }
    }

    func complete(_ result: Result<[PHAsset], Error>) {
        lock.lock()
        guard !completed else { lock.unlock(); return }
        completed = true
        let waiting = continuation; continuation = nil
        lock.unlock()
        waiting?.resume(with: result)
    }

    func cancel() {
        lock.lock(); cancelled = true; lock.unlock()
        complete(.failure(CancellationError()))
    }
}
