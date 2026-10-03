import Foundation
import UniformTypeIdentifiers
import CoreTransferable
import CelluloidDomain
import CelluloidRendering

struct NativePickedFile: Transferable {
    let owned: OwnedImportFile
    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(importedContentType: .image) { received in
            NativePickedFile(owned: try OwnedImportFile(copying: received.file))
        }
    }
}

/// NSItemProvider file callbacks own only a temporary URL. Copy/validate its size
/// before callback return, and make cancellation resume the waiting UI immediately.
enum NativeProviderImport {
    static func read(_ provider: NSItemProvider, limit: Int) async throws -> Data {
        guard limit > 0, limit <= RasterCodec.maxSourceBytes else { throw RecipeError.resourceLimit }
        let state = ProviderReadState()
        return try await withTaskCancellationHandler {
            try Task.checkCancellation()
            return try await withCheckedThrowingContinuation { continuation in
                state.install(continuation)
                if let type = provider.registeredTypeIdentifiers.first(where: { UTType($0)?.conforms(to: .image) == true }) {
                    let progress = provider.loadFileRepresentation(forTypeIdentifier: type) { url, error in
                        guard let url else { state.complete(.failure(error ?? RenderError.invalidImage)); return }
                        state.complete(Result {
                            try state.check()
                            let owned = try OwnedImportFile(copying: url, limit: limit, check: state.check)
                            defer { owned.discard() }
                            return try NativeFileAccess.readImage(owned.url, limit: limit, check: state.check)
                        })
                    }
                    state.setProgress(progress)
                } else if provider.canLoadObject(ofClass: URL.self) {
                    let progress = provider.loadObject(ofClass: URL.self) { url, error in
                        state.complete(Result {
                            guard let url, url.isFileURL, url.absoluteString.utf8.count <= 16_384 else { throw error ?? RenderError.invalidImage }
                            try state.check()
                            return try NativeFileAccess.readImage(url, limit: limit, check: state.check)
                        })
                    }
                    state.setProgress(progress)
                } else { state.complete(.failure(RenderError.invalidImage)) }
            }
        } onCancel: { state.cancel() }
    }
}
private final class ProviderReadState: @unchecked Sendable {
    private let lock = NSLock()
    private var cancelled = false
    private var finished = false
    private var progress: Progress?
    private var continuation: CheckedContinuation<Data, Error>?
    func install(_ value: CheckedContinuation<Data, Error>) {
        lock.lock()
        if cancelled { finished = true; lock.unlock(); value.resume(throwing: CancellationError()) }
        else { continuation = value; lock.unlock() }
    }
    func setProgress(_ value: Progress) {
        lock.lock(); if !finished { progress = value }; let stop = cancelled; lock.unlock()
        if stop { value.cancel() }
    }
    func check() throws { lock.lock(); let value = cancelled; lock.unlock(); if value { throw CancellationError() } }
    func complete(_ result: Result<Data, Error>) {
        lock.lock()
        guard !finished else { lock.unlock(); return }
        finished = true; let waiting = continuation; continuation = nil; progress = nil; lock.unlock()
        waiting?.resume(with: result)
    }
    func cancel() {
        lock.lock(); cancelled = true; let current = progress; lock.unlock()
        current?.cancel(); complete(.failure(CancellationError()))
    }
}
