import XCTest
import AppKit
import UniformTypeIdentifiers
import CelluloidRendering
@testable import CelluloidMac

final class NativeProviderImportTests: XCTestCase {
    func testProviderUsesBoundedFileRepresentationAndOwnsBytes() async throws {
        let file = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".png")
        defer { try? FileManager.default.removeItem(at: file) }
        let original = Data(repeating: 74, count: 4096); try original.write(to: file)
        let provider = NSItemProvider()
        provider.registerFileRepresentation(forTypeIdentifier: UTType.png.identifier, fileOptions: [], visibility: .all) { completion in
            completion(file, false, nil); return nil
        }
        let imported = try await NativeProviderImport.read(provider, limit: 4096)
        try Data(repeating: 0, count: 4096).write(to: file)
        XCTAssertEqual(imported, original)
    }
    func testOversizedPromisedFileRejectedBeforeImageDecodeAndDocumentMutation() async throws {
        let file = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".png")
        defer { try? FileManager.default.removeItem(at: file) }
        FileManager.default.createFile(atPath: file.path, contents: nil)
        let handle = try FileHandle(forWritingTo: file); try handle.truncate(atOffset: UInt64(64 * 1024 * 1024 + 1)); try handle.close()
        let provider = NSItemProvider()
        provider.registerFileRepresentation(forTypeIdentifier: UTType.png.identifier, fileOptions: [], visibility: .all) { completion in completion(file, false, nil); return nil }
        let bitmap = try RasterCodec.bitmap(width: 16, height: 16)
        bitmap.setFillColor(CGColor(srgbRed: 1, green: 0, blue: 0, alpha: 1)); bitmap.fill(CGRect(x: 0, y: 0, width: 16, height: 16))
        var document = NativeDocument(); try document.replaceSources([("Original.png", RasterCodec.encode(XCTUnwrap(bitmap.makeImage()), as: .png))])
        let previous = document
        do {
            let bytes = try await NativeProviderImport.read(provider, limit: 64 * 1024 * 1024)
            try document.replaceSources([("Too large.png", bytes)]); XCTFail("Oversized file must be rejected")
        } catch { }
        XCTAssertEqual(document, previous)
    }
    func testCancellationResumesWithoutWaitingForAProviderCallback() async throws {
        let started = expectation(description: "Provider request began")
        let provider = NSItemProvider()
        provider.registerFileRepresentation(forTypeIdentifier: UTType.png.identifier, fileOptions: [], visibility: .all) { _ in
            started.fulfill(); return Progress(totalUnitCount: 1)
        }
        let task = Task { try await NativeProviderImport.read(provider, limit: 4096) }
        await fulfillment(of: [started], timeout: 5)
        task.cancel()
        do { _ = try await task.value; XCTFail("Canceled import must not finish successfully") }
        catch is CancellationError { }
        catch { XCTFail("Expected explicit cancellation: \(error)") }
    }
}
