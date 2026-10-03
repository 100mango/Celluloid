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
        do {
            // Commit both metadata and owned bytes before the WC callback returns.
            // A busy renderer leaves an explicit durable pending request for the phone UI.
            try processor.inbox.stage(request, from: file.fileURL)
            lock.lock(); let shouldRender = !processing; if shouldRender { processing = true }; lock.unlock()
            guard shouldRender else { Task { @MainActor in self.changed?() }; return }
            if canDeliver(ticket) { session.transferUserInfo(["celluloid.processing.v1": metadata]) }
            Task {
                defer { finishProcessing() }
                do {
                    let (record, url) = try await processor.resumePending(request.id)
                    guard canDeliver(ticket), let ticket else {
                        try await processor.holdDelivery(record.id)
                        await MainActor.run { self.changed?() }; return
                    }
                    let attempt = try await processor.beginDelivery(record.id)
                    guard canDeliver(ticket) else {
                        try await processor.holdDelivery(record.id, attempt: attempt)
                        await MainActor.run { self.changed?() }; return
                    }
                    session.transferFile(url, metadata: ["celluloid.result.v1": try record.response.encoded(), "celluloid.session-epoch": ticket.uuidString, "celluloid.delivery-attempt": attempt.uuidString])
                    await MainActor.run { self.changed?() }
                } catch {
                    sendFailure(request, ticket: ticket, message: error.localizedDescription)
                    await MainActor.run { self.changed?() }
                }
            }
        } catch { sendFailure(request, ticket: ticket, message: error.localizedDescription) }
    }
    func session(_ session: WCSession, didFinish fileTransfer: WCSessionFileTransfer, error: Error?) {
        guard let metadata = fileTransfer.file.metadata?["celluloid.result.v1"] as? Data,
              let result = try? CompanionResult.decode(metadata),
              let attempt = (fileTransfer.file.metadata?["celluloid.delivery-attempt"] as? String).flatMap(UUID.init(uuidString:)) else { return }
        let ticket = (fileTransfer.file.metadata?["celluloid.session-epoch"] as? String).flatMap(UUID.init(uuidString:))
        Task {
            try? await processor.finishDelivery(result.requestID, attempt: attempt, failed: error != nil)
            if error != nil, canDeliver(ticket), let record = try? await processor.records().first(where: { $0.id == result.requestID }), record.deliveryAttempt == attempt, record.delivery == .failed {
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
