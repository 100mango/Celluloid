import XCTest
import CoreGraphics
import CelluloidDomain
@testable import CelluloidWatch

final class NativeWatchTests: XCTestCase {
    func testNativeWatchExecutable() {
        XCTAssertEqual(Bundle.main.infoDictionary?["DTPlatformName"] as? String, "watchsimulator")
        print("WATCH_NATIVE_RUNTIME bundle=\(Bundle.main.bundleURL.path)")
    }
    func testOfflineGalleryImportReopenPendingCompletionAndDeleteStayLocal() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: folder) }
        let store = try WatchGalleryStore(folder: folder)
        let bytes = try fixture(), photo = try await store.importPhoto(bytes, name: "Synthetic 世界")
        let reopened = try WatchGalleryStore(folder: folder)
        let rows = try await reopened.load(); XCTAssertEqual(rows, [photo])
        let image = try await reopened.preview(photo.id); XCTAssertEqual(image.width, 64); XCTAssertEqual(image.height, 40)
        let request = try await reopened.beginRequest(photo.id, filter: .fade) { _, _ in }
        let pending = try await store.load(); XCTAssertEqual(pending.first?.job?.phase, .pending)
        let response = CompanionResult(requestID: request.id, sourceSHA256: request.sourceSHA256, previewSHA256: WatchGalleryStore.digest(bytes), pixelWidth: 64, pixelHeight: 40, failure: nil)
        try await store.receive(response, preview: bytes)
        let completed = try await reopened.load(); XCTAssertEqual(completed.first?.job?.phase, .completed)
        try await store.receive(response, preview: bytes)
        try await store.remove(photo.id); let remaining = try await reopened.load(); XCTAssertTrue(remaining.isEmpty)
    }
    func testRelaunchedCancellationSelectsOnlyOwnedTransfersAndIgnoresLateReply() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: folder) }
        let original = try WatchGalleryStore(folder: folder), bytes = try fixture()
        let photo = try await original.importPhoto(bytes, name: "Cancellation ownership fixture")
        let request = try await original.beginRequest(photo.id, filter: .fade) { _, _ in }
        let relaunched = try WatchGalleryStore(folder: folder)
        let accepted = try await relaunched.cancelRequest(sourceID: photo.id, requestID: request.id)
        let cancelled = try XCTUnwrap(accepted)
        let different = CompanionRequest(sourceID: photo.id, sourceSHA256: request.sourceSHA256, sourceBytes: bytes.count, filter: .fade)
        let wrongSource = CompanionRequest(id: request.id, sourceID: UUID(), sourceSHA256: request.sourceSHA256, sourceBytes: bytes.count, filter: .fade)
        let metadata: [[String: Any]?] = [
            ["celluloid.request.v1": try request.encoded()],
            ["celluloid.request.v1": try different.encoded()],
            ["celluloid.request.v1": try wrongSource.encoded()],
            ["unrelated.request": try request.encoded()],
            ["celluloid.request.v1": Data("malformed".utf8)],
            ["celluloid.request.v1": "wrong representation"], nil
        ]
        // These are injectable metadata handles, not physical transport evidence.
        XCTAssertEqual(metadata.enumerated().filter { WatchRequestTransfer.matches($0.element, request: cancelled) }.map(\.offset), [0])
        let late = CompanionResult(requestID: request.id, sourceSHA256: request.sourceSHA256,
            previewSHA256: WatchGalleryStore.digest(bytes), pixelWidth: 64, pixelHeight: 40, failure: nil)
        try await relaunched.receive(late, preview: bytes)
        try await relaunched.markProcessing(request)
        let persisted = try await WatchGalleryStore(folder: folder).load()
        XCTAssertEqual(persisted.first?.job?.phase, .cancelled)
        XCTAssertNil(persisted.first?.job?.result)
        XCTAssertEqual(persisted.first?.sourceSHA256, photo.sourceSHA256)
    }
    func testGalleryRefusesOverflowAndCorruptImagesWithoutEviction() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: folder) }
        let store = try WatchGalleryStore(folder: folder), bytes = try fixture()
        for index in 0..<20 { _ = try await store.importPhoto(bytes, name: "Synthetic \(index)") }
        do { _ = try await store.importPhoto(bytes, name: "Overflow"); XCTFail("Overflow must fail") } catch { }
        let rows = try await store.load(); XCTAssertEqual(rows.count, 20)
        do { _ = try await store.importPhoto(Data(repeating: 0, count: 8 * 1024 * 1024 + 1), name: "Too large"); XCTFail("Oversize must fail") } catch { }
        XCTAssertThrowsError(try WatchGalleryStore.thumbnail(Data()))
    }
    func testAtomicTransitionsRejectStaleProcessingCancelAndDoubleAdmission() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: folder) }
        let store = try WatchGalleryStore(folder: folder), bytes = try fixture()
        let photo = try await store.importPhoto(bytes, name: "Atomic fixture")
        let request = try await store.beginRequest(photo.id, filter: .fade) { _, _ in }
        let response = CompanionResult(requestID: request.id, sourceSHA256: request.sourceSHA256, previewSHA256: WatchGalleryStore.digest(bytes), pixelWidth: 64, pixelHeight: 40, failure: nil)
        try await store.receive(response, preview: bytes)
        // Model the formerly unsafe copied callbacks arriving after completion.
        try await store.markProcessing(request)
        let cancelled = try await store.cancelRequest(sourceID: photo.id, requestID: request.id)
        XCTAssertNil(cancelled)
        let completed = try await store.load(); XCTAssertEqual(completed.first?.job?.phase, .completed)
        let admitted = await withTaskGroup(of: Bool.self, returning: Int.self) { group in
            for _ in 0..<12 { group.addTask { do { _ = try await store.beginRequest(photo.id, filter: .chrome) { _, _ in }; return true } catch { return false } } }
            var count = 0; for await succeeded in group { if succeeded { count += 1 } }; return count
        }
        XCTAssertEqual(admitted, 1)
        // A stale cancellation for the earlier completed request cannot cancel the new one.
        let stale = try await store.cancelRequest(sourceID: photo.id, requestID: request.id); XCTAssertNil(stale)
        let pending = try await store.load(); XCTAssertEqual(pending.first?.job?.phase, .pending)
    }
    func testIncomingReceiptSurvivesTerminationAndInterruptedGalleryCommit() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: folder) }
        let gallery = try WatchGalleryStore(folder: folder.appendingPathComponent("Gallery"))
        let inboxFolder = folder.appendingPathComponent("Inbox"), inbox = try WatchIncomingResults(folder: inboxFolder)
        let bytes = try fixture(), photo = try await gallery.importPhoto(bytes, name: "Received fixture")
        let request = try await gallery.beginRequest(photo.id, filter: .fade) { _, _ in }
        let result = CompanionResult(requestID: request.id, sourceSHA256: request.sourceSHA256, previewSHA256: WatchGalleryStore.digest(bytes), pixelWidth: 64, pixelHeight: 40, failure: nil)
        // Kill after callback ownership and before actor application: a new instance
        // must retrieve precisely the same source-bound result and image bytes.
        let staged = try inbox.stage(result, preview: bytes)
        let relaunched = try WatchIncomingResults(folder: inboxFolder)
        XCTAssertEqual(try relaunched.pending(), [staged])
        try await gallery.receive(staged.result, preview: staged.preview)
        // Kill after gallery commit, before receipt cleanup: replay is idempotent.
        let replay = try XCTUnwrap(relaunched.pending().first)
        try await gallery.receive(replay.result, preview: replay.preview)
        try relaunched.removeIfUnchanged(replay)
        XCTAssertTrue(try relaunched.pending().isEmpty)
        let rows = try await gallery.load(); XCTAssertEqual(rows.first?.job?.phase, .completed)
        let image = try await gallery.preview(photo.id, processed: true); XCTAssertEqual(image.width, 64)
    }
    func testIncomingReceiptCompletionWinsStaleCleanupAndBudgetIsBounded() throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: folder) }
        let inbox = try WatchIncomingResults(folder: folder), bytes = try fixture(), hash = WatchGalleryStore.digest(bytes), id = UUID()
        let failure = CompanionResult(requestID: id, sourceSHA256: hash, previewSHA256: nil, pixelWidth: nil, pixelHeight: nil, failure: "Synthetic transfer failed")
        let failedReceipt = try inbox.stage(failure, preview: nil)
        let success = CompanionResult(requestID: id, sourceSHA256: hash, previewSHA256: hash, pixelWidth: 64, pixelHeight: 40, failure: nil)
        let completed = try inbox.stage(success, preview: bytes)
        try inbox.removeIfUnchanged(failedReceipt)
        XCTAssertEqual(try inbox.pending(), [completed])
        XCTAssertEqual(try inbox.stage(failure, preview: nil), completed)
        XCTAssertThrowsError(try inbox.stage(success, preview: Data(repeating: 0, count: 2 * 1024 * 1024 + 1)))
        let other = CompanionResult(requestID: UUID(), sourceSHA256: hash, previewSHA256: nil, pixelWidth: nil, pixelHeight: nil, failure: "Another synthetic failure")
        _ = try inbox.stage(other, preview: nil)
        let overflow = CompanionResult(requestID: UUID(), sourceSHA256: hash, previewSHA256: nil, pixelWidth: nil, pixelHeight: nil, failure: "Overflow")
        XCTAssertThrowsError(try inbox.stage(overflow, preview: nil))
        XCTAssertEqual(try inbox.pending().count, 2)
        try inbox.removeIfUnchanged(completed); XCTAssertEqual(try inbox.pending().count, 1)
    }
    func testIncomingPreRenameKillRecoversAndIncompleteOwnStagingIsReclaimed() throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: folder) }
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let bytes = try fixture(), hash = WatchGalleryStore.digest(bytes)
        let result = CompanionResult(requestID: UUID(), sourceSHA256: hash, previewSHA256: hash, pixelWidth: 64, pixelHeight: 40, failure: nil)
        let receipt = WatchIncomingResults.Receipt(revision: UUID(), result: result, preview: bytes)
        let encoder = PropertyListEncoder(); encoder.outputFormat = .binary
        let complete = folder.appendingPathComponent(".staging-" + UUID().uuidString)
        let partial = folder.appendingPathComponent(".staging-" + UUID().uuidString)
        try encoder.encode(receipt).write(to: complete)
        try Data("incomplete".utf8).write(to: partial)
        let unrelated = folder.appendingPathComponent("unrelated.data")
        try Data("preserve".utf8).write(to: unrelated)
        let reopened = try WatchIncomingResults(folder: folder)
        let recovered = try XCTUnwrap(reopened.pending().first)
        XCTAssertEqual(recovered.result,result); XCTAssertEqual(recovered.preview,bytes)
        XCTAssertFalse(FileManager.default.fileExists(atPath: complete.path)); XCTAssertFalse(FileManager.default.fileExists(atPath: partial.path))
        XCTAssertEqual(try Data(contentsOf: unrelated),Data("preserve".utf8))
    }
    private func fixture() throws -> Data {
        let space = try XCTUnwrap(CGColorSpace(name: CGColorSpace.sRGB))
        let bitmap = try XCTUnwrap(CGContext(data: nil, width: 64, height: 40, bitsPerComponent: 8, bytesPerRow: 256, space: space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
        bitmap.setFillColor(CGColor(srgbRed: 0.2, green: 0.5, blue: 0.9, alpha: 1)); bitmap.fill(CGRect(x: 0, y: 0, width: 64, height: 40))
        return try WatchGalleryStore.png(XCTUnwrap(bitmap.makeImage()))
    }
}
