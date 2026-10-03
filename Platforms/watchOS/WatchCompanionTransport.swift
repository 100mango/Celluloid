import Foundation
import WatchConnectivity
import CelluloidDomain

/// One explicit request at a time. Sending/queuing is never reported as completion.
final class WatchCompanionTransport: NSObject, WCSessionDelegate {
    private let store: WatchGalleryStore
    var changed: (() -> Void)?
    var failure: ((String) -> Void)?
    init(store: WatchGalleryStore) { self.store = store; super.init() }
    func activate() {
        guard WCSession.isSupported() else { return }
        WCSession.default.delegate = self; WCSession.default.activate()
    }
    func request(_ photo: WatchPhoto, filter: FilterPreset) async throws {
        let session = WCSession.default
        guard session.activationState == .activated, session.isCompanionAppInstalled else {
            throw NSError(domain: "Celluloid.Companion", code: 1, userInfo: [NSLocalizedDescriptionKey: NSLocalizedString("Open Celluloid on your paired iPhone, then try again.", comment: "Watch companion")])
        }
        let items = try await store.load()
        guard !items.contains(where: { $0.job?.phase == .pending || $0.job?.phase == .processing }) else {
            throw NSError(domain: "Celluloid.Companion", code: 2, userInfo: [NSLocalizedDescriptionKey: NSLocalizedString("Wait for the current phone request, or cancel it first.", comment: "Watch companion")])
        }
        let (url, bytes) = try await store.source(photo.id)
        guard WatchGalleryStore.digest(bytes) == photo.sourceSHA256 else { throw RecipeError.invalidDocument }
        let request = CompanionRequest(sourceID: photo.id, sourceSHA256: photo.sourceSHA256, sourceBytes: bytes.count, filter: filter)
        try await store.setJob(CompanionJob(request: request), for: photo.id)
        session.transferFile(url, metadata: ["celluloid.request.v1": try request.encoded()])
        await notify()
    }
    func cancel(_ photo: WatchPhoto) async throws {
        guard var job = photo.job else { return }
        job.cancel(); try await store.setJob(job, for: photo.id)
        for transfer in WCSession.default.outstandingFileTransfers {
            if let bytes = transfer.file.metadata?["celluloid.request.v1"] as? Data,
               let request = try? CompanionRequest.decode(bytes), request.id == job.request.id { transfer.cancel() }
        }
        // Cancellation stops applying late responses. The phone may already have processed it.
        await notify()
    }
    func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: Error?) {
        if let error { report(error) }; Task { await notify() }
    }
    func session(_ session: WCSession, didReceive file: WCSessionFile) {
        do {
            guard let envelope = file.metadata?["celluloid.result.v1"] as? Data else { throw RecipeError.invalidDocument }
            let result = try CompanionResult.decode(envelope)
            let info = try file.fileURL.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey, .isSymbolicLinkKey])
            guard info.isRegularFile == true, info.isSymbolicLink != true, let size = info.fileSize, size <= 2 * 1024 * 1024 else { throw RecipeError.resourceLimit }
            // WCSession deletes the incoming URL after this callback. Own the bounded bytes now.
            let bytes = try Data(contentsOf: file.fileURL)
            guard bytes.count <= 2 * 1024 * 1024 else { throw RecipeError.resourceLimit }
            Task {
                do { try await store.receive(result, preview: bytes); await notify() }
                catch { report(error) }
            }
        } catch { report(error) }
    }
    func session(_ session: WCSession, didReceiveUserInfo userInfo: [String: Any] = [:]) {
        if let data = userInfo["celluloid.result.v1"] as? Data {
            Task {
                do {
                    let result = try CompanionResult.decode(data)
                    guard result.failure != nil else { throw RecipeError.invalidDocument }
                    try await store.receive(result, preview: nil); await notify()
                } catch { report(error) }
            }
        }
        if let data = userInfo["celluloid.processing.v1"] as? Data {
            Task {
                do {
                    let request = try CompanionRequest.decode(data)
                    let items = try await store.load()
                    guard let photo = items.first(where: { $0.job?.request == request }), var job = photo.job else { return }
                    job.markProcessing(); try await store.setJob(job, for: photo.id); await notify()
                } catch { report(error) }
            }
        }
    }
    func session(_ session: WCSession, didReceiveMessage message: [String: Any]) {
        self.session(session, didReceiveUserInfo: message)
    }
    func session(_ session: WCSession, didFinish fileTransfer: WCSessionFileTransfer, error: Error?) {
        guard let error, let envelope = fileTransfer.file.metadata?["celluloid.request.v1"] as? Data,
              let request = try? CompanionRequest.decode(envelope) else { return }
        let result = CompanionResult(requestID: request.id, sourceSHA256: request.sourceSHA256, previewSHA256: nil, pixelWidth: nil, pixelHeight: nil,
                                     failure: NSLocalizedString("The phone transfer failed. You can request processing again.", comment: "Watch companion"))
        Task {
            do { try await store.receive(result, preview: nil); await notify() } catch { report(error) }
        }
        report(error)
    }
    private func notify() async { await MainActor.run { self.changed?() } }
    private func report(_ error: Error) { Task { @MainActor in self.failure?(error.localizedDescription) } }
}
