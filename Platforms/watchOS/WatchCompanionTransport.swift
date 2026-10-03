import Foundation
import WatchConnectivity
import CelluloidDomain

/// One explicit request at a time. Sending/queuing is never reported as completion.
final class WatchCompanionTransport: NSObject, WCSessionDelegate {
    private let store: WatchGalleryStore
    private let incoming: WatchIncomingResults
    var changed: (() -> Void)?
    var failure: ((String) -> Void)?
    init(store: WatchGalleryStore, incoming: WatchIncomingResults? = nil) throws { self.store = store; self.incoming = try incoming ?? WatchIncomingResults(); super.init() }
    func activate() {
        guard WCSession.isSupported() else { return }
        WCSession.default.delegate = self; WCSession.default.activate()
        Task { await recoverIncoming() }
    }
    func request(_ photo: WatchPhoto, filter: FilterPreset) async throws {
        let session = WCSession.default
        guard session.activationState == .activated, session.isCompanionAppInstalled else {
            throw NSError(domain: "Celluloid.Companion", code: 1, userInfo: [NSLocalizedDescriptionKey: NSLocalizedString("Open Celluloid on your paired iPhone, then try again.", comment: "Watch companion")])
        }
        _ = try await store.beginRequest(photo.id, filter: filter) { url, request in
            guard session.activationState == .activated, session.isCompanionAppInstalled else {
                throw NSError(domain: "Celluloid.Companion", code: 1, userInfo: [NSLocalizedDescriptionKey: NSLocalizedString("Open Celluloid on your paired iPhone, then try again.", comment: "Watch companion")])
            }
            session.transferFile(url, metadata: ["celluloid.request.v1": try request.encoded()])
        }
        await notify()
    }
    func cancel(_ photo: WatchPhoto) async throws {
        guard let previous = photo.job,
              let cancelled = try await store.cancelRequest(sourceID: photo.id, requestID: previous.request.id) else { return }
        for transfer in WCSession.default.outstandingFileTransfers {
            if let bytes = transfer.file.metadata?["celluloid.request.v1"] as? Data,
               let request = try? CompanionRequest.decode(bytes), request.id == cancelled.id { transfer.cancel() }
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
            // Persist the bounded receipt before WCSession deletes this callback-owned URL.
            let bytes = try Data(contentsOf: file.fileURL)
            guard bytes.count <= 2 * 1024 * 1024 else { throw RecipeError.resourceLimit }
            try incoming.stage(result, preview: bytes)
            Task { await recoverIncoming() }
        } catch { report(error) }
    }
    func session(_ session: WCSession, didReceiveUserInfo userInfo: [String: Any] = [:]) {
        if let data = userInfo["celluloid.result.v1"] as? Data {
            do {
                let result = try CompanionResult.decode(data)
                guard result.failure != nil else { throw RecipeError.invalidDocument }
                try incoming.stage(result, preview: nil)
                Task { await recoverIncoming() }
            } catch { report(error) }
        }
        if let data = userInfo["celluloid.processing.v1"] as? Data {
            Task {
                do {
                    let request = try CompanionRequest.decode(data)
                    try await store.markProcessing(request); await notify()
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
    func recoverIncoming() async {
        do {
            for receipt in try incoming.pending() {
                try await store.receive(receipt.result, preview: receipt.preview)
                // A new success may have replaced a failed receipt during the actor await.
                try incoming.removeIfUnchanged(receipt)
            }
            await notify()
        } catch { report(error) } // Keep accepted receipts on a failed gallery write.
    }
    private func notify() async { await MainActor.run { self.changed?() } }
    private func report(_ error: Error) { Task { @MainActor in self.failure?(error.localizedDescription) } }
}
