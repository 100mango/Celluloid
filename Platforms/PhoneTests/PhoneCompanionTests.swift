import XCTest
import UIKit
import CelluloidDomain
import CelluloidRendering
@testable import CelluloidPhoneCompanion

final class PhoneCompanionTests: XCTestCase {
    @MainActor func testNativePhoneCompanionHost() {
        XCTAssertEqual(Bundle.main.infoDictionary?["DTPlatformName"] as? String, "iphonesimulator")
        XCTAssertFalse(UIApplication.shared.connectedScenes.isEmpty)
    }
    func testProductionProcessorFullRenderPreviewPersistenceAndIdempotency() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: folder) }
        let processor = try PhoneCompanionProcessor(folder: folder)
        let bitmap = try RasterCodec.bitmap(width: 1200, height: 800)
        bitmap.setFillColor(CGColor(srgbRed: 0.2, green: 0.5, blue: 0.9, alpha: 1)); bitmap.fill(CGRect(x: 0, y: 0, width: 1200, height: 800))
        let bytes = try RasterCodec.encode(XCTUnwrap(bitmap.makeImage()), as: .png)
        let request = CompanionRequest(sourceID: UUID(), sourceSHA256: PhoneCompanionProcessor.digest(bytes), sourceBytes: bytes.count, filter: .fade)
        let (record, previewURL) = try await processor.process(request, source: bytes)
        XCTAssertEqual(record.request, request)
        let preview = try Data(contentsOf: previewURL), metadata = try RasterCodec.metadata(preview)
        XCTAssertLessThanOrEqual(metadata.pixelWidth, 512); XCTAssertLessThanOrEqual(metadata.pixelHeight, 512)
        XCTAssertEqual(PhoneCompanionProcessor.digest(preview), record.response.previewSHA256)
        let reopened = try PhoneCompanionProcessor(folder: folder)
        let full = try await reopened.fullResult(request.id)
        XCTAssertEqual(try RasterCodec.metadata(full).pixelWidth, 1200); XCTAssertEqual(try RasterCodec.metadata(full).pixelHeight, 800)
        let duplicate = try await reopened.process(request, source: bytes)
        XCTAssertEqual(duplicate.0.response, record.response)
        let rows = try await reopened.records(); XCTAssertEqual(rows.count, 1)
        let stale = CompanionRequest(id: request.id, sourceID: request.sourceID, sourceSHA256: request.sourceSHA256, sourceBytes: request.sourceBytes, filter: .original)
        do { _ = try await reopened.process(stale, source: bytes); XCTFail("Same request ID must not change meaning") } catch { }
        XCTAssertTrue(try reopened.inbox.requests().isEmpty, "Rejected changed duplicate must not leave an unusable pending job")
        try await reopened.remove(request.id); let empty = try await reopened.records(); XCTAssertTrue(empty.isEmpty)
        print("PHONE_COMPANION_PIPELINE full render, bounded preview, durable readback and duplicate handling verified; WCSession transport is a separate gate")
    }
    func testDurableInboxOwnsSourceBeforeProcessingAndRefusesChangedDuplicate() throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: folder) }
        let incoming = folder.appendingPathComponent("delivered.image")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let bytes = Data([1,2,3,4]); try bytes.write(to: incoming)
        let request = CompanionRequest(sourceID: UUID(), sourceSHA256: PhoneCompanionProcessor.digest(bytes), sourceBytes: bytes.count, filter: .fade)
        let root = folder.appendingPathComponent("Store")
        let inbox = try PhoneCompanionInbox(root: root)
        try inbox.stage(request, from: incoming); try FileManager.default.removeItem(at: incoming)
        let reopened = try PhoneCompanionInbox(root: root)
        XCTAssertEqual(try reopened.requests(), [request]); XCTAssertEqual(try reopened.source(request.id), bytes)
        let changed = CompanionRequest(id: request.id, sourceID: request.sourceID, sourceSHA256: request.sourceSHA256, sourceBytes: request.sourceBytes, filter: .chrome)
        XCTAssertThrowsError(try reopened.stage(changed, bytes: bytes))
        XCTAssertEqual(try reopened.source(request.id), bytes)
    }
    func testInterruptedJobsRecoverAndDeliveryAttemptsRejectStaleCallbacks() async throws {
        let bitmap = try RasterCodec.bitmap(width: 120, height: 80)
        bitmap.setFillColor(CGColor(srgbRed: 0.2, green: 0.5, blue: 0.9, alpha: 1)); bitmap.fill(CGRect(x: 0, y: 0, width: 120, height: 80))
        let bytes = try RasterCodec.encode(XCTUnwrap(bitmap.makeImage()), as: .png)
        for interruption in [PhoneCompanionProcessor.Interruption.afterStaging, .afterFullOutput, .afterOutputBeforeIndex] {
            let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
            defer { try? FileManager.default.removeItem(at: folder) }
            let processor = try PhoneCompanionProcessor(folder: folder)
            let request = CompanionRequest(sourceID: UUID(), sourceSHA256: PhoneCompanionProcessor.digest(bytes), sourceBytes: bytes.count, filter: .fade)
            await processor.interruptOnce(at: interruption)
            do { _ = try await processor.process(request, source: bytes); XCTFail("Injected interruption must stop before completion") } catch { }
            XCTAssertEqual(try processor.inbox.source(request.id), bytes)
            let reopened = try PhoneCompanionProcessor(folder: folder)
            let pending = try await reopened.pendingRequests()
            if interruption == .afterOutputBeforeIndex {
                XCTAssertTrue(pending.isEmpty, "Verified completed journal should repair the index without rerendering")
            } else {
                XCTAssertEqual(pending, [request]); _ = try await reopened.resumePending(request.id)
            }
            let rows = try await reopened.records(); XCTAssertEqual(rows.count, 1); XCTAssertEqual(rows.first?.delivery, .pending)
            XCTAssertTrue(try reopened.inbox.requests().isEmpty)
            let full = try await reopened.fullResult(request.id); XCTAssertEqual(try RasterCodec.metadata(full).pixelWidth, 120)
            let first = try await reopened.beginDelivery(request.id), second = try await reopened.beginDelivery(request.id)
            try await reopened.finishDelivery(request.id, attempt: first, failed: true)
            let stillQueued = try await reopened.records(); XCTAssertEqual(stillQueued.first?.delivery, .queued)
            try await reopened.finishDelivery(request.id, attempt: second, failed: false)
            try await reopened.finishDelivery(request.id, attempt: second, failed: true)
            try await reopened.holdDelivery(request.id, attempt: first)
            let completed = try await reopened.records(); XCTAssertEqual(completed.first?.delivery, .transferFinished)
        }
        print("PHONE_COMPANION_DURABLE_RESTART three interruption points, explicit local resume, journal repair and delivery-attempt completion-wins verified")
    }

    func testStagingKillPointsRecoverCapacityWithoutTouchingAcceptedRecords() throws {
        let bytes = Data([1,2,3,4])
        for point in 0...3 {
            let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
            defer { try? FileManager.default.removeItem(at: root) }
            let inbox = try PhoneCompanionInbox(root: root)
            let accepted = CompanionRequest(sourceID: UUID(), sourceSHA256: PhoneCompanionProcessor.digest(bytes), sourceBytes: bytes.count, filter: .original)
            try inbox.stage(accepted, bytes: bytes)
            // An unrelated already-completed product must not be cleaned up.
            let completed = root.appendingPathComponent("existing-completed.png"); try bytes.write(to: completed)
            let completedRequest = CompanionRequest(sourceID: UUID(), sourceSHA256: accepted.sourceSHA256, sourceBytes: bytes.count, filter: .original)
            let completedResponse = CompanionResult(requestID: completedRequest.id, sourceSHA256: completedRequest.sourceSHA256, previewSHA256: completedRequest.sourceSHA256, pixelWidth: 1, pixelHeight: 1, failure: nil)
            let completedRecord = PhoneCompanionRecord(request: completedRequest, response: completedResponse, created: Date(timeIntervalSince1970: 0))
            let indexBytes = try JSONEncoder().encode([completedRecord]); let index = root.appendingPathComponent("index.json"); try indexBytes.write(to: index)
            let incoming = CompanionRequest(sourceID: UUID(), sourceSHA256: accepted.sourceSHA256, sourceBytes: bytes.count, filter: .fade)
            let temporary = root.appendingPathComponent("Pending/.staging-" + UUID().uuidString)
            try FileManager.default.createDirectory(at: temporary, withIntermediateDirectories: false)
            if point >= 1 { try incoming.encoded().write(to: temporary.appendingPathComponent("request.json"), options: .atomic) }
            if point >= 2 { try bytes.write(to: temporary.appendingPathComponent("source.image"), options: .atomic) }
            if point == 3 { try FileManager.default.moveItem(at: temporary, to: root.appendingPathComponent("Pending/" + incoming.id.uuidString)) }
            let restarted = try PhoneCompanionInbox(root: root)
            XCTAssertEqual(try restarted.source(accepted.id), bytes); XCTAssertEqual(try Data(contentsOf: completed), bytes); XCTAssertEqual(try Data(contentsOf: index), indexBytes)
            XCTAssertFalse(FileManager.default.fileExists(atPath: temporary.path))
            let requests = try restarted.requests()
            XCTAssertEqual(requests.count, point < 2 ? 1 : 2)
            if point >= 2 { XCTAssertEqual(try restarted.source(incoming.id), bytes) }
            else { XCTAssertNotNil(restarted.recoveryNotice) }
            let used = try restarted.usedBytes()
            let again = try PhoneCompanionInbox(root: root)
            XCTAssertEqual(try again.requests(), requests); XCTAssertEqual(try again.usedBytes(), used)
        }
    }
    func testValidOverflowStagingIsRetainedAndPromotedAfterExplicitCapacityRelease() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let inbox = try PhoneCompanionInbox(root: root), bytes = Data([1,2,3])
        var accepted: [CompanionRequest] = []
        for _ in 0..<PhoneCompanionInbox.maximumPending {
            let request = CompanionRequest(sourceID: UUID(), sourceSHA256: PhoneCompanionProcessor.digest(bytes), sourceBytes: bytes.count, filter: .original)
            try inbox.stage(request, bytes: bytes); accepted.append(request)
        }
        let incoming = CompanionRequest(sourceID: UUID(), sourceSHA256: accepted[0].sourceSHA256, sourceBytes: bytes.count, filter: .fade)
        let temporary = root.appendingPathComponent("Pending/.staging-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: temporary, withIntermediateDirectories: false)
        try incoming.encoded().write(to: temporary.appendingPathComponent("request.json")); try bytes.write(to: temporary.appendingPathComponent("source.image"))
        let restarted = try PhoneCompanionInbox(root: root)
        XCTAssertEqual(try restarted.requests().count, 4); XCTAssertNotNil(restarted.recoveryNotice)
        XCTAssertTrue(FileManager.default.fileExists(atPath: temporary.path))
        try restarted.complete(accepted[0].id); try restarted.reconcileStaging()
        XCTAssertEqual(try restarted.source(incoming.id), bytes); XCTAssertNil(restarted.recoveryNotice)
        XCTAssertEqual(try restarted.requests().count, 4)
    }

}
