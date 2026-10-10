import XCTest
import CryptoKit
import UIKit
import CelluloidDomain
import CelluloidRendering
@testable import CelluloidVision

final class NativeVisionTests: XCTestCase {
    func testNativeVisionDocumentImportRenderSaveReopenAndExport() throws {
        let bitmap = try RasterCodec.bitmap(width: 320, height: 240)
        bitmap.setFillColor(try XCTUnwrap(CGColor(colorSpace: RasterCodec.colorSpace, components: [0.15,0.5,0.85,1])))
        bitmap.fill(CGRect(x: 0, y: 0, width: 320, height: 240))
        let data = try RasterCodec.encode(XCTUnwrap(bitmap.makeImage()), as: .png)
        var document = NativeDocument(); try document.replaceSources([("Synthetic.png", data)])
        document.recipe.filter = .fade
        document.recipe.overlays = [Overlay(bubble: .say1, text: "Vision 世界")]
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".celluloid")
        defer { try? FileManager.default.removeItem(at: folder) }
        try document.archive().write(to: folder, options: .atomic, originalContentsURL: nil)
        let restored = try NativeDocument(wrapper: FileWrapper(url: folder, options: .immediate))
        XCTAssertEqual(restored, document)
        let output = try RecipeRenderer().render(restored.recipe, sources: restored.originals)
        let exported = try RasterCodec.encode(output, as: .png)
        let file = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".png")
        defer { try? FileManager.default.removeItem(at: file) }
        try exported.write(to: file, options: .atomic)
        XCTAssertEqual(try Data(contentsOf: file), exported)
        XCTAssertEqual(try RasterCodec.metadata(exported).pixelWidth, 320)
        print("VISION_NATIVE_DOCUMENT_PIPELINE verified import/render/package-reopen/export-readback; programmatic hosted integration, not system-picker traversal")
    }
    @MainActor func testSharedFieldMutationsRetainUnicodeAcrossBothOrdersUndoAndReopen() throws {
        let bitmap = try RasterCodec.bitmap(width: 120, height: 80)
        bitmap.setFillColor(CGColor(srgbRed: 0.1, green: 0.5, blue: 0.8, alpha: 1))
        bitmap.fill(CGRect(x: 0, y: 0, width: 120, height: 80))
        let bytes = try RasterCodec.encode(XCTUnwrap(bitmap.makeImage()), as: .png)
        for textFirst in [true, false] {
            var document = NativeDocument(); try document.replaceSources([("Synthetic.png", bytes)])
            let bubble = Overlay(bubble: .say1, text: "Hello"); document.recipe.overlays = [bubble]
            let text: RecipeMutation = { $0.editOverlay(bubble.id) { $0.text = "Vision 世界" } }
            let geometry: RecipeMutation = { $0.editOverlay(bubble.id) { $0.rotation = 15; $0.centerX = 0.51 } }
            let manager = UndoManager(); manager.groupsByEvent = false
            let undo = DocumentUndo(); undo.apply = { document = $0 }
            for mutation in textFirst ? [text, geometry] : [geometry, text] {
                let next = try document.editing(mutation)
                manager.beginUndoGrouping(); undo.change(from: document, to: next, manager: manager, name: "Synthetic edit"); manager.endUndoGrouping()
            }
            let final = document
            manager.undo()
            XCTAssertEqual(document.recipe.overlays[0].text, textFirst ? "Vision 世界" : "Hello")
            XCTAssertEqual(document.recipe.overlays[0].rotation, textFirst ? 0 : 15)
            XCTAssertEqual(document.recipe.overlays[0].centerX, textFirst ? 0.5 : 0.51)
            XCTAssertEqual(document.originals, final.originals)
            manager.redo(); XCTAssertEqual(document, final)
            XCTAssertEqual(document.recipe.overlays[0].text, "Vision 世界"); XCTAssertEqual(document.recipe.overlays[0].rotation, 15)
            let restored = try NativeDocument(wrapper: document.archive())
            XCTAssertEqual(restored, final)
            XCTAssertThrowsError(try document.editing { $0.editOverlay(bubble.id) { $0.text = String(repeating: "界", count: 6000) } })
            XCTAssertEqual(document, final)
        }
    }
    @MainActor func testPrepareVisionRemainingDocumentFixture() throws {
        // Fixture setup only; the previously passed field/Undo case is not selected.
        let bitmap = try RasterCodec.bitmap(width: 120, height: 80)
        bitmap.setFillColor(CGColor(srgbRed: 0.1, green: 0.5, blue: 0.8, alpha: 1))
        bitmap.fill(CGRect(x: 0, y: 0, width: 120, height: 80))
        let bytes = try RasterCodec.encode(XCTUnwrap(bitmap.makeImage()), as: .png)
        var seed = NativeDocument(); try seed.replaceSources([("Synthetic.png", bytes)])
        let documents = try FileManager.default.url(for: .documentDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
        let fixture = documents.appendingPathComponent("VisionRemaining.celluloid", isDirectory: true)
        guard !FileManager.default.fileExists(atPath: fixture.path) else { throw CocoaError(.fileWriteFileExists) }
        try seed.archive().write(to: fixture, options: .atomic, originalContentsURL: nil)
        let wrapper = try FileWrapper(url: fixture, options: .immediate)
        XCTAssertEqual(try NativeDocument(wrapper: wrapper), seed)
        XCTAssertEqual(Bundle.main.bundleIdentifier, "Mango.Celluloid")
        let children = try XCTUnwrap(wrapper.fileWrappers); XCTAssertEqual(children.count, 2)
        var files: [[String: Any]] = []
        for name in children.keys.sorted() {
            let data = try XCTUnwrap(children[name]?.regularFileContents)
            files.append(["name": name, "bytes": data.count,
                          "sha256": SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()])
        }
        let metadata: [String: Any] = ["schema": "Celluloid.VisionFixture.1", "bundle_identifier": Bundle.main.bundleIdentifier!,
            "data_home": NSHomeDirectory(), "documents_path": documents.path, "package_path": fixture.path,
            "package_name": "VisionRemaining.celluloid", "pixel_width": 120, "pixel_height": 80,
            "initial_overlays": 0, "files": files]
        let encoded = try JSONSerialization.data(withJSONObject: metadata, options: [.sortedKeys])
        print("VISION_REMAINING_FIXTURE_JSON " + String(decoding: encoded, as: UTF8.self))
    }
    @MainActor func testNativeVisionExecutableAndSceneAreLive() throws {
        XCTAssertEqual(Bundle.main.bundleIdentifier, "Mango.Celluloid")
        XCTAssertEqual(Bundle.main.infoDictionary?["DTPlatformName"] as? String, "xrsimulator")
        let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
        XCTAssertFalse(scenes.isEmpty)
        print("VISION_NATIVE_RUNTIME bundle=\(Bundle.main.bundleURL.path) scenes=\(scenes.count) platform=\(Bundle.main.infoDictionary?["DTPlatformName"] ?? "")")
        // VISION_FILES_DATA_DIAG_BEGIN:owned-home-identity
        // Only this host's own sandbox identity; no directory enumeration or data reads.
        let dataHome = NSHomeDirectory()
        let attributes = try FileManager.default.attributesOfItem(atPath: dataHome)
        XCTAssertEqual(attributes[.type] as? FileAttributeType, .typeDirectory)
        let device = try XCTUnwrap(attributes[.systemNumber] as? NSNumber)
        let inode = try XCTUnwrap(attributes[.systemFileNumber] as? NSNumber)
        let receipt: [String: Any] = ["schema": "Celluloid.VisionOwnedData.1",
            "bundle_identifier": "Mango.Celluloid", "data_home": dataHome,
            "device": device.uint64Value, "inode": inode.uint64Value]
        let encoded = try JSONSerialization.data(withJSONObject: receipt, options: [.sortedKeys])
        XCTAssertLessThanOrEqual(encoded.count, 4096)
        print("VISION_NATIVE_DATA_JSON " + String(decoding: encoded, as: UTF8.self))
        // VISION_FILES_DATA_DIAG_END:owned-home-identity
    }
}
