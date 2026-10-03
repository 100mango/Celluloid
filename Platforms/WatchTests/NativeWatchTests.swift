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
        let request = CompanionRequest(sourceID: photo.id, sourceSHA256: photo.sourceSHA256, sourceBytes: bytes.count, filter: .fade)
        try await reopened.setJob(CompanionJob(request: request), for: photo.id)
        let pending = try await store.load(); XCTAssertEqual(pending.first?.job?.phase, .pending)
        let response = CompanionResult(requestID: request.id, sourceSHA256: request.sourceSHA256, previewSHA256: WatchGalleryStore.digest(bytes), pixelWidth: 64, pixelHeight: 40, failure: nil)
        try await store.receive(response, preview: bytes)
        let completed = try await reopened.load(); XCTAssertEqual(completed.first?.job?.phase, .completed)
        try await store.receive(response, preview: bytes)
        try await store.remove(photo.id); let remaining = try await reopened.load(); XCTAssertTrue(remaining.isEmpty)
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
    private func fixture() throws -> Data {
        let space = try XCTUnwrap(CGColorSpace(name: CGColorSpace.sRGB))
        let bitmap = try XCTUnwrap(CGContext(data: nil, width: 64, height: 40, bitsPerComponent: 8, bytesPerRow: 256, space: space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
        bitmap.setFillColor(CGColor(srgbRed: 0.2, green: 0.5, blue: 0.9, alpha: 1)); bitmap.fill(CGRect(x: 0, y: 0, width: 64, height: 40))
        return try WatchGalleryStore.png(XCTUnwrap(bitmap.makeImage()))
    }
}
