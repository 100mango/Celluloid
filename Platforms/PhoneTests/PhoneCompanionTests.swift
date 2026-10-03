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
        try await reopened.remove(request.id); let empty = try await reopened.records(); XCTAssertTrue(empty.isEmpty)
        print("PHONE_COMPANION_PIPELINE full render, bounded preview, durable readback and duplicate handling verified; WCSession transport is a separate gate")
    }
}
