import XCTest
@testable import CelluloidMac

final class NativeFileAccessTests: XCTestCase {
    func testImportOwnsBytesAfterExternalSourceModificationAndDeletion() throws {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".synthetic")
        defer { try? FileManager.default.removeItem(at: url) }
        let original = Data(repeating: 137, count: 100_000)
        try original.write(to: url)
        let imported = try NativeFileAccess.readImage(url)
        let handle = try FileHandle(forWritingTo: url)
        try handle.write(contentsOf: Data(repeating: 0, count: 100_000)); try handle.close()
        XCTAssertEqual(imported, original)
        XCTAssertNotEqual(try Data(contentsOf: url), original)
        try FileManager.default.removeItem(at: url)
        XCTAssertEqual(imported, original)
    }
    func testBoundedReaderRejectsDirectoriesAndOversizedFiles() throws {
        XCTAssertThrowsError(try NativeFileAccess.readImage(FileManager.default.temporaryDirectory))
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: url) }
        try Data(repeating: 0, count: 4097).write(to: url)
        XCTAssertThrowsError(try NativeFileAccess.readImage(url, limit: 4096))
        XCTAssertEqual(try NativeFileAccess.readImage(url, limit: 4097).count, 4097)
    }
}
