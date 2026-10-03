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
    private let delivery = CompanionDeliveryGate()
    init(processor: PhoneCompanionProcessor) { self.processor = processor; super.init() }
    func activate() {
        guard WCSession.isSupported() else { return }
        WCSession.default.delegate = self; WCSession.default.activate()
    }
    func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: Error?) {
        if activationState == .activated && error == nil { delivery.activate() }
        else { delivery.invalidate { } }
    }
    func sessionDidBecomeInactive(_ session: WCSession) { invalidate(session) }
    func sessionDidDeactivate(_ session: WCSession) { invalidate(session); session.activate() }
    private func invalidate(_ session: WCSession) {
        let transfers = delivery.invalidate {
            (session.outstandingFileTransfers.filter { $0.file.metadata?["celluloid.result.v1"] != nil },
             session.outstandingUserInfoTransfers.filter { $0.userInfo.keys.contains(where: { $0.hasPrefix("celluloid.") }) })
        }
        for transfer in transfers.0 { transfer.cancel() }
        for transfer in transfers.1 { transfer.cancel() }
    }
    private func deliveryTicket(_ session: WCSession) -> UUID? {
        delivery.ticket { session.activationState == .activated }
    }
    private func canDeliver(_ ticket: UUID?) -> Bool {
        delivery.enqueue(ticket, isSessionActive: { WCSession.default.activationState == .activated }) { }
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
            delivery.enqueue(ticket, isSessionActive: { session.activationState == .activated }) {
                session.transferUserInfo(["celluloid.processing.v1": metadata])
            }
            Task {
                defer { finishProcessing() }
                do {
                    let (record, url) = try await processor.resumePending(request.id)
                    guard canDeliver(ticket), let ticket else {
                        try await processor.holdDelivery(record.id)
                        await MainActor.run { self.changed?() }; return
                    }
                    let attempt = try await processor.beginDelivery(record.id)
                    let response = try record.response.encoded()
                    let queued = delivery.enqueue(ticket, isSessionActive: { session.activationState == .activated }) {
                        session.transferFile(url, metadata: ["celluloid.result.v1": response, "celluloid.session-epoch": ticket.uuidString, "celluloid.delivery-attempt": attempt.uuidString])
                    }
                    if !queued { try await processor.holdDelivery(record.id, attempt: attempt) }
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
        let response = CompanionResult(requestID: request.id, sourceSHA256: request.sourceSHA256, previewSHA256: nil, pixelWidth: nil, pixelHeight: nil, failure: String(message.prefix(200)))
        if let data = try? response.encoded() {
            let message: [String: Any] = ["celluloid.result.v1": data]
            delivery.enqueue(ticket, isSessionActive: { WCSession.default.activationState == .activated }) {
                WCSession.default.transferUserInfo(message)
                if WCSession.default.isReachable { WCSession.default.sendMessage(message, replyHandler: nil, errorHandler: nil) }
            }
        }
    }
}
