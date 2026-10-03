import Foundation
import WatchConnectivity
import CelluloidDomain

/// Activate from the shipping iPhone lifecycle only after explicit source integration/testing.
/// This service does not activate itself or add an account, backend, or App Group.
final class PhoneCompanionTransport: NSObject, WCSessionDelegate {
    let processor: PhoneCompanionProcessor
    var changed: (() -> Void)?
    private let lock = NSLock()
    private var processing = false
    private var epoch = CompanionSessionEpoch()
    init(processor: PhoneCompanionProcessor) { self.processor = processor; super.init() }
    func activate() {
        guard WCSession.isSupported() else { return }
        WCSession.default.delegate = self; WCSession.default.activate()
    }
    func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: Error?) {
        lock.lock(); if activationState == .activated && error == nil { epoch.activate() } else { epoch.invalidate() }; lock.unlock()
    }
    func sessionDidBecomeInactive(_ session: WCSession) { invalidate(session) }
    func sessionDidDeactivate(_ session: WCSession) { invalidate(session); session.activate() }
    private func invalidate(_ session: WCSession) {
        lock.lock(); epoch.invalidate(); lock.unlock()
        for transfer in session.outstandingFileTransfers where transfer.file.metadata?["celluloid.result.v1"] != nil { transfer.cancel() }
        for transfer in session.outstandingUserInfoTransfers where transfer.userInfo.keys.contains(where: { $0.hasPrefix("celluloid.") }) { transfer.cancel() }
    }
    private func deliveryTicket(_ session: WCSession) -> UUID? {
        lock.lock(); defer { lock.unlock() }; return session.activationState == .activated ? epoch.ticket : nil
    }
    private func canDeliver(_ ticket: UUID?) -> Bool {
        lock.lock(); defer { lock.unlock() }; return WCSession.default.activationState == .activated && epoch.canDeliver(ticket)
    }
    func session(_ session: WCSession, didReceive file: WCSessionFile) {
        guard let metadata = file.metadata?["celluloid.request.v1"] as? Data,
              let request = try? CompanionRequest.decode(metadata) else { return }
        let ticket = deliveryTicket(session)
        lock.lock()
        guard !processing else { lock.unlock(); sendFailure(request, ticket: ticket, message: NSLocalizedString("Another image is being processed. Request this image again when it finishes.", comment: "Companion")); return }
        processing = true; lock.unlock()
        do {
            let info = try file.fileURL.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
            guard info.isRegularFile == true, info.isSymbolicLink != true, info.fileSize == request.sourceBytes else { throw RecipeError.invalidDocument }
            // Own bounded bytes before WatchConnectivity removes its delivery URL.
            let bytes = try Data(contentsOf: file.fileURL)
            guard bytes.count == request.sourceBytes else { throw RecipeError.invalidDocument }
            if canDeliver(ticket) { session.transferUserInfo(["celluloid.processing.v1": metadata]) }
            Task {
                defer { finishProcessing() }
                do {
                    let (record, url) = try await processor.process(request, source: bytes)
                    guard canDeliver(ticket), let ticket else {
                        try await processor.markDelivery(record.id, .pending)
                        await MainActor.run { self.changed?() }; return
                    }
                    session.transferFile(url, metadata: ["celluloid.result.v1": try record.response.encoded(), "celluloid.session-epoch": ticket.uuidString])
                    try await processor.markDelivery(record.id, .queued)
                    await MainActor.run { self.changed?() }
                } catch { sendFailure(request, ticket: ticket, message: error.localizedDescription) }
            }
        } catch { finishProcessing(); sendFailure(request, ticket: ticket, message: error.localizedDescription) }
    }
    func session(_ session: WCSession, didFinish fileTransfer: WCSessionFileTransfer, error: Error?) {
        guard let metadata = fileTransfer.file.metadata?["celluloid.result.v1"] as? Data,
              let result = try? CompanionResult.decode(metadata) else { return }
        let ticket = (fileTransfer.file.metadata?["celluloid.session-epoch"] as? String).flatMap(UUID.init(uuidString:))
        Task {
            try? await processor.markDelivery(result.requestID, error == nil ? .transferFinished : .failed)
            if error != nil, canDeliver(ticket), let record = try? await processor.records().first(where: { $0.id == result.requestID }) {
                sendFailure(record.request, ticket: ticket, message: NSLocalizedString("The image is ready on your iPhone, but its Watch preview could not be delivered. Open the phone app to view or save it.", comment: "Companion delivery"))
            }
            await MainActor.run { self.changed?() }
        }
    }
    private func finishProcessing() { lock.lock(); processing = false; lock.unlock() }
    private func sendFailure(_ request: CompanionRequest, ticket: UUID?, message: String) {
        guard canDeliver(ticket) else { return }
        let response = CompanionResult(requestID: request.id, sourceSHA256: request.sourceSHA256, previewSHA256: nil, pixelWidth: nil, pixelHeight: nil, failure: String(message.prefix(200)))
        if let data = try? response.encoded() {
            let message: [String: Any] = ["celluloid.result.v1": data]
            WCSession.default.transferUserInfo(message)
            if WCSession.default.isReachable { WCSession.default.sendMessage(message, replyHandler: nil, errorHandler: nil) }
        }
    }
}
